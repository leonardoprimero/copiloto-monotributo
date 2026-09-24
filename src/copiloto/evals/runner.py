"""Running the graph against the eval cases and scoring the outcome.

Two measurements, deliberately not merged into one number:

- decision accuracy: did the copilot reach the right conclusion?
- extraction accuracy: did it read the document correctly?

A model can misread a date and still land on the right category. Averaging
those together would let a reading error disappear behind a correct verdict,
which is exactly the failure this project cannot afford.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from copiloto.analysis import Analysis, RiskPolicy
from copiloto.evals.schema import EvalCase
from copiloto.extractors.protocol import InvoiceExtractor
from copiloto.graph.builder import build_graph
from copiloto.models import ExtractedInvoice, TaxpayerProfile
from copiloto.registry import MockArcaRegistry
from copiloto.scales import load_scales

ExtractorFactory = Callable[[EvalCase], InvoiceExtractor]

# The fields scored per invoice: the identity, the date and the amount that
# every downstream decision depends on.
SCORED_FIELDS = ("issuer_cuit", "issue_date", "total")


@dataclass(frozen=True, slots=True)
class CaseResult:
    case_id: str
    route: str
    risk_level: str
    computed_category: str | None
    issue_codes: tuple[str, ...]
    expected_route: str
    expected_risk_level: str
    expected_computed_category: str | None
    expected_issue_codes: tuple[str, ...]
    field_accuracy: dict[str, float]
    fields_compared: int
    report: str
    analysis: Analysis | None

    @property
    def decision_correct(self) -> bool:
        return not self.differences()

    def differences(self) -> list[str]:
        """Which parts of the answer differ, named so a failure is readable."""
        checks = (
            ("route", self.route, self.expected_route),
            ("risk_level", self.risk_level, self.expected_risk_level),
            ("computed_category", self.computed_category, self.expected_computed_category),
            ("issue_codes", set(self.issue_codes), set(self.expected_issue_codes)),
        )
        return [f"{name}: got {got!r}, expected {want!r}" for name, got, want in checks if got != want]

    def explain(self) -> str:
        if self.decision_correct:
            return f"{self.case_id}: correct"
        return f"{self.case_id}: " + "; ".join(self.differences())


@dataclass(frozen=True, slots=True)
class EvalReport:
    results: list[CaseResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def decision_accuracy(self) -> float:
        # Zero cases scores zero, not one: "nothing was measured" must never
        # read as "everything passed".
        if not self.results:
            return 0.0
        return sum(r.decision_correct for r in self.results) / len(self.results)

    @property
    def extraction_accuracy(self) -> float:
        compared = sum(r.fields_compared for r in self.results)
        if not compared:
            return 0.0
        matched = sum(
            score * r.fields_compared / len(SCORED_FIELDS)
            for r in self.results
            for score in r.field_accuracy.values()
        )
        return matched / compared

    def field_accuracy(self) -> dict[str, float]:
        """Accuracy per field, so a systematic misreading is visible."""
        scored = [r for r in self.results if r.fields_compared]
        if not scored:
            return dict.fromkeys(SCORED_FIELDS, 0.0)
        return {
            name: sum(r.field_accuracy[name] for r in scored) / len(scored)
            for name in SCORED_FIELDS
        }

    def render(self) -> str:
        lines = [f"{'case':<26} {'decision':<10} {'route':<8} {'risk':<10}"]
        lines += [
            f"{r.case_id:<26} {'ok' if r.decision_correct else 'WRONG':<10} "
            f"{r.route:<8} {r.risk_level:<10}"
            for r in self.results
        ]
        lines.append("")
        lines.append(f"decision accuracy   {self.decision_accuracy:.1%} ({self.total} cases)")
        lines.append(f"extraction accuracy {self.extraction_accuracy:.1%}")
        lines += [f"  {name:<14} {score:.1%}" for name, score in self.field_accuracy().items()]

        wrong = [r for r in self.results if not r.decision_correct]
        if wrong:
            lines += ["", "Incorrect:"] + [f"  {r.explain()}" for r in wrong]
        return "\n".join(lines)


def _registry(case: EvalCase) -> MockArcaRegistry:
    if case.registry_entry is None:
        return MockArcaRegistry({})
    entry = case.registry_entry
    return MockArcaRegistry(
        {entry.cuit: TaxpayerProfile(cuit=entry.cuit, name=entry.name, category=entry.category)}
    )


def _field_value(invoice: ExtractedInvoice, name: str):
    value = getattr(invoice, name)
    return str(value) if isinstance(value, (Decimal, date)) else value


def _score_extraction(
    read: Sequence[ExtractedInvoice], truth: Sequence[ExtractedInvoice]
) -> tuple[dict[str, float], int]:
    """Compare what was read against the known answer, field by field.

    An invoice the extractor failed to produce is not silently skipped: it
    counts as wrong for every field, because it was not read.
    """
    if not truth:
        return dict.fromkeys(SCORED_FIELDS, 1.0), 0

    by_number = {i.number: i for i in read}
    accuracy: dict[str, float] = {}
    for name in SCORED_FIELDS:
        matches = sum(
            1
            for expected in truth
            if (got := by_number.get(expected.number)) is not None
            and _field_value(got, name) == _field_value(expected, name)
        )
        accuracy[name] = matches / len(truth)

    return accuracy, len(truth) * len(SCORED_FIELDS)


def run_case(case: EvalCase, extractor_factory: ExtractorFactory) -> CaseResult:
    """Run one case end to end, resuming any pause automatically."""
    truth = [ExtractedInvoice.model_validate(i) for i in case.invoices]

    graph = build_graph(
        extractor=extractor_factory(case),
        registry=_registry(case),
        scales=load_scales(),
        today=date.fromisoformat(case.today),
        policy=RiskPolicy(),
    )
    config: RunnableConfig = {"configurable": {"thread_id": f"eval-{case.id}"}}

    state = graph.invoke(
        {"taxpayer_cuit": case.taxpayer_cuit, "raw_invoices": case.invoice_texts},
        config,
    )

    route = "review" if "__interrupt__" in state else "ok"
    if route == "review":
        # The runner is not an accountant. `reviewer="auto"` is what makes the
        # report say so instead of crediting a person who never looked.
        state = graph.invoke(
            Command(
                resume={
                    "verdict": "confirmed",
                    "notes": "Reanudación automática del runner de evals.",
                    "reviewer": "auto",
                }
            ),
            config,
        )

    analysis: Analysis | None = state.get("analysis")
    accuracy, compared = _score_extraction(state.get("invoices", ()), truth)

    return CaseResult(
        case_id=case.id,
        route=route,
        risk_level=analysis.risk_level if analysis else "unknown",
        computed_category=analysis.computed_category if analysis else None,
        issue_codes=tuple(sorted({i.code for i in state.get("issues", [])})),
        expected_route=case.expected.route,
        expected_risk_level=case.expected.risk_level,
        expected_computed_category=case.expected.computed_category,
        expected_issue_codes=case.expected.issue_codes,
        field_accuracy=accuracy,
        fields_compared=compared,
        report=state.get("report", ""),
        analysis=analysis,
    )


def run_all(cases: Sequence[EvalCase], extractor_factory: ExtractorFactory) -> EvalReport:
    """Run every case and collect the scores."""
    return EvalReport([run_case(case, extractor_factory) for case in cases])
