"""The graph nodes.

Each node is built by a factory that closes over its dependencies, so the
graph can be assembled with a fake extractor and a fixed clock without any
LangGraph-specific injection machinery.

Nodes are thin: they move data between the state and the pure functions in
`validation`, `analysis` and `report`. The logic being tested elsewhere is what
keeps these small enough to read in one go.
"""

from datetime import date

from langgraph.types import Send, interrupt

from copiloto.analysis import RiskPolicy, analyze
from copiloto.extractors.protocol import InvoiceExtractor
from copiloto.graph.state import CopilotState, ExtractionTask
from copiloto.models import HumanDecision, Issue
from copiloto.registry import TaxpayerRegistry
from copiloto.report import render_report
from copiloto.scales import Scales
from copiloto.validation import (
    validate_invoice_amounts,
    validate_invoice_dates,
    validate_invoice_identity,
)


def fan_out_invoices(state: CopilotState) -> list[Send] | str:
    """Send every invoice to its own extraction task.

    Reading an invoice is the only step that calls a model, and it is the slow
    one. The invoices are independent, so they go out as one `Send` each and
    LangGraph runs them together in a single superstep.

    With no invoices there is nothing to fan out, and the empty case is routed
    straight to the collector, which reports the missing data.
    """
    raw_invoices = state.get("raw_invoices", ())
    if not raw_invoices:
        return "collect_invoices"
    return [Send("extract_one", {"raw": raw}) for raw in raw_invoices]


def make_extract_one_node(extractor: InvoiceExtractor):
    """Build the task that reads a single invoice with a model.

    It reads and records; it never judges. An invoice that cannot be read
    becomes an issue and the others still go through, because one unreadable
    document should not hide the other eleven. The catch is deliberately
    broad: a provider that hangs up raises its own transport error, not
    `ExtractionError`, and one bad invoice must not take the run down.

    Note the payload: a `Send` hands the node its own dict, not the graph
    state. What it returns is merged into the state through the reducers.
    """

    def extract_one(state: ExtractionTask) -> dict:
        raw = state["raw"]
        try:
            return {"extracted": [extractor.extract(raw)]}
        except Exception as error:  # noqa: BLE001
            return {
                "issues": [
                    Issue(
                        code="EXTRACTION_FAILED",
                        severity="warning",
                        message=f"An invoice could not be read: {error}",
                    )
                ]
            }

    return extract_one


def collect_invoices(state: CopilotState) -> dict:
    """Put the parallel results back in a fixed order.

    Sorted by issue date, then by number. Tasks may finish in any order, and
    the same folder must always produce the same report; sorting on the
    invoices themselves makes that true regardless of how the framework
    happens to schedule them.
    """
    extracted = state.get("extracted", [])
    if not extracted and not state.get("raw_invoices", ()):
        # Zero invoices would accumulate zero and resolve to category A, which
        # reads exactly like "all good". It is missing data instead.
        return {
            "invoices": (),
            "issues": [
                Issue(
                    code="NO_INVOICES",
                    severity="warning",
                    message="No invoices were provided, so nothing could be assessed.",
                )
            ],
        }

    return {
        "invoices": tuple(sorted(extracted, key=lambda i: (i.issue_date, i.number)))
    }


def make_validate_node(*, scales: Scales, today: date):
    """Build the node where the code checks what the model read."""

    def validate_invoices(state: CopilotState) -> dict:
        taxpayer_cuit = state.get("taxpayer_cuit", "")
        issues: list[Issue] = []

        for invoice in state.get("invoices", ()):
            issues += validate_invoice_identity(invoice, taxpayer_cuit)
            issues += validate_invoice_amounts(invoice, scales)
            issues += validate_invoice_dates(invoice, today=today)

        return {"issues": issues}

    return validate_invoices


def make_lookup_node(registry: TaxpayerRegistry):
    """Build the node that asks the registry which category is on file."""

    def lookup_taxpayer(state: CopilotState) -> dict:
        cuit = state.get("taxpayer_cuit", "")
        profile = registry.lookup(cuit)
        if profile is None:
            # Absence is reported, never filled in with a guess: without a
            # registered category there is nothing to compare against, and the
            # analysis skips those rules rather than inventing them.
            return {
                "taxpayer": None,
                "issues": [
                    Issue(
                        code="TAXPAYER_NOT_FOUND",
                        severity="warning",
                        message=f"CUIT {cuit} is not in the registry, so the "
                        "registered category is unknown.",
                    )
                ],
            }
        return {"taxpayer": profile, "issues": []}

    return lookup_taxpayer


def make_analyze_node(*, scales: Scales, today: date, policy: RiskPolicy):
    """Build the node that turns invoices and issues into a risk level."""

    def analyze_income(state: CopilotState) -> dict:
        return {
            "analysis": analyze(
                state.get("invoices", ()),
                issues=tuple(state.get("issues", [])),
                taxpayer=state.get("taxpayer"),
                today=today,
                scales=scales,
                policy=policy,
                declared=state.get("declared"),
            )
        }

    return analyze_income


def build_review_alert(state: CopilotState) -> dict:
    """Summarize why a case needs a person.

    Deliberately pure. The review node calls this *before* pausing, and a
    resumed node re-runs from its first line, so everything that happens before
    the pause must be safe to run twice.
    """
    analysis = state.get("analysis")
    issues = state.get("issues", [])
    return {
        "risk_level": analysis.risk_level if analysis else "unknown",
        "reasons": list(analysis.reasons) if analysis else [],
        "accumulated_12m": str(analysis.accumulated_12m) if analysis else None,
        "projected_12m": str(analysis.projected_12m) if analysis else None,
        "computed_category": analysis.computed_category if analysis else None,
        "registered_category": analysis.registered_category if analysis else None,
        "headroom_registered": (
            str(analysis.headroom_registered)
            if analysis and analysis.headroom_registered is not None
            else None
        ),
        "headroom_top": str(analysis.headroom_top) if analysis else None,
        "issues": [
            {"code": i.code, "severity": i.severity, "message": i.message}
            for i in issues
            if i.severity in ("warning", "error")
        ],
    }


def make_review_node():
    """Build the node that hands the case to an accountant.

    `interrupt()` suspends the run, persists a checkpoint and surfaces the
    payload to whoever invoked the graph. The caller resumes with
    `Command(resume=...)`, and that value is what `interrupt()` returns here.

    Measured against langgraph 1.2.12: resuming re-runs this function from its
    first line. Only the pure alert builder may run before the pause; the
    decision is written after it, so nothing happens twice.
    """

    def request_accountant_review(state: CopilotState) -> dict:
        answer = interrupt(build_review_alert(state))

        return {
            "human_decision": HumanDecision(
                verdict=answer["verdict"],
                notes=answer.get("notes", ""),
                # Defaults to the accountant: an automatic resume has to say so
                # explicitly rather than inherit a human's authority by omission.
                reviewer=answer.get("reviewer", "accountant"),
            )
        }

    return request_accountant_review


def make_report_node(*, scales: Scales):
    """Build the node that renders the analysis for the taxpayer.

    The node only adapts state to arguments; the rendering itself is a pure
    function tested on its own.
    """

    def write_report(state: CopilotState) -> dict:
        analysis = state.get("analysis")
        if analysis is None:  # pragma: no cover - the graph always analyses first
            raise RuntimeError("write_report reached without an analysis")

        return {
            "report": render_report(
                analysis,
                issues=tuple(state.get("issues", [])),
                taxpayer=state.get("taxpayer"),
                scales=scales,
                human_decision=state.get("human_decision"),
                invoice_count=len(state.get("invoices", ())),
                declared=state.get("declared"),
            )
        }

    return write_report
