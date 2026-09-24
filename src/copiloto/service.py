"""The copilot as a service: start, look up, resume and list cases.

The CLI and the web interface both need the same four operations, and neither
should know how a LangGraph thread is configured, how an interrupt surfaces,
or how a checkpoint is read back. That knowledge lives here, once.

Every operation goes through the checkpointer, so two instances over the same
SQLite file see the same cases: the taxpayer's process starts a case and the
accountant's process, hours later, resumes it.
"""

from dataclasses import dataclass
from datetime import date
from typing import Literal

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import Command, StateSnapshot

from copiloto.analysis import RiskPolicy
from copiloto.extractors.protocol import ExtractionError, InvoiceExtractor
from copiloto.graph.builder import build_graph
from copiloto.models import DeclaredParameters, ExtractedInvoice, HumanDecision
from copiloto.registry import TaxpayerRegistry, UnavailableRegistry
from copiloto.scales import Scales

CaseStatus = Literal["pending", "done", "incomplete"]


class CaseAlreadyExists(RuntimeError):
    """A case id was reused.

    Invoking a thread that already ran would merge the new input into the old
    state and append to its issues, so the service refuses instead.
    """


class CaseNotPending(RuntimeError):
    """The case does not exist or is not waiting for a decision."""


@dataclass(frozen=True, slots=True)
class PendingReview:
    """A case paused for an accountant, with what they need to decide."""

    case_id: str
    alert: dict
    created_at: str | None


@dataclass(frozen=True, slots=True)
class Finished:
    """A case with its report written."""

    case_id: str
    report: str
    human_decision: HumanDecision | None
    created_at: str | None


@dataclass(frozen=True, slots=True)
class CaseSummary:
    """One row of the case list."""

    case_id: str
    status: CaseStatus
    taxpayer_cuit: str
    registered_category: str | None
    risk_level: str | None
    created_at: str | None


class _UnavailableExtractor:
    """An extractor for graphs that must never read anything.

    Resuming, reading and listing never reach the extraction node; if one did,
    this makes it a loud failure rather than a silent re-read.
    """

    def extract(self, raw: str) -> ExtractedInvoice:
        raise ExtractionError("The extractor was called on a graph that must not read invoices.")


class Copilot:
    """The four operations a copilot exposes, over one checkpointer."""

    def __init__(
        self, *, scales: Scales, policy: RiskPolicy, checkpointer: BaseCheckpointSaver
    ) -> None:
        self._scales = scales
        self._policy = policy
        self._checkpointer = checkpointer

    def start(
        self,
        *,
        case_id: str,
        taxpayer_cuit: str,
        raw_invoices: tuple[str, ...],
        extractor: InvoiceExtractor,
        registry: TaxpayerRegistry,
        today: date,
        declared: DeclaredParameters | None = None,
    ) -> PendingReview | Finished:
        """Run a new case up to its report or its pause."""
        if self._snapshot(case_id).values:
            raise CaseAlreadyExists(f"Case {case_id!r} already exists.")

        graph = build_graph(
            extractor=extractor,
            registry=registry,
            scales=self._scales,
            today=today,
            policy=self._policy,
            checkpointer=self._checkpointer,
        )
        graph.invoke(
            {"taxpayer_cuit": taxpayer_cuit, "raw_invoices": raw_invoices, "declared": declared},
            self._config(case_id),
        )
        outcome = self.get(case_id)
        assert outcome is not None  # the thread was just written
        return outcome

    def resume(self, case_id: str, decision: HumanDecision) -> Finished:
        """Answer the accountant's pause and finish the case."""
        if not isinstance(self.get(case_id), PendingReview):
            raise CaseNotPending(f"Case {case_id!r} is not waiting for a decision.")

        self._dormant_graph().invoke(
            Command(resume=decision.model_dump()), self._config(case_id)
        )
        outcome = self.get(case_id)
        assert isinstance(outcome, Finished)  # the resume either finishes or raises
        return outcome

    def get(self, case_id: str) -> PendingReview | Finished | None:
        """What the case looks like right now, or None if it does not exist."""
        snapshot = self._snapshot(case_id)
        if not snapshot.values:
            return None
        if snapshot.interrupts:
            return PendingReview(
                case_id=case_id,
                alert=snapshot.interrupts[0].value,
                created_at=snapshot.created_at,
            )
        if "report" in snapshot.values:
            return Finished(
                case_id=case_id,
                report=snapshot.values["report"],
                human_decision=snapshot.values.get("human_decision"),
                created_at=snapshot.created_at,
            )
        return None

    def list_cases(self) -> list[CaseSummary]:
        """Every case on file, newest first."""
        seen: dict[str, None] = {}
        for checkpoint in self._checkpointer.list(None):
            thread_id = checkpoint.config.get("configurable", {}).get("thread_id")
            if thread_id:
                seen.setdefault(str(thread_id), None)

        summaries = [self._summarize(case_id, self._snapshot(case_id)) for case_id in seen]
        return sorted(summaries, key=lambda s: s.created_at or "", reverse=True)

    def _summarize(self, case_id: str, snapshot: StateSnapshot) -> CaseSummary:
        values = snapshot.values
        analysis = values.get("analysis")
        status: CaseStatus = (
            "pending" if snapshot.interrupts else "done" if "report" in values else "incomplete"
        )
        return CaseSummary(
            case_id=case_id,
            status=status,
            taxpayer_cuit=values.get("taxpayer_cuit", ""),
            registered_category=analysis.registered_category if analysis else None,
            risk_level=analysis.risk_level if analysis else None,
            created_at=snapshot.created_at,
        )

    def _snapshot(self, case_id: str) -> StateSnapshot:
        return self._dormant_graph().get_state(self._config(case_id))

    def _dormant_graph(self):
        """A graph that can read and resume, but must not extract or look up.

        Both nodes ran before the pause and their results are in the
        checkpoint, so their dependencies fail loudly rather than answer.
        """
        return build_graph(
            extractor=_UnavailableExtractor(),
            registry=UnavailableRegistry(),
            scales=self._scales,
            today=date.min,
            policy=self._policy,
            checkpointer=self._checkpointer,
        )

    @staticmethod
    def _config(case_id: str) -> RunnableConfig:
        return {"configurable": {"thread_id": case_id}}
