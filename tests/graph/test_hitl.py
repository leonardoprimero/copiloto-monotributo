"""Handing a case to an accountant, and picking it up again.

Pinned against the behaviour measured in `test_langgraph_api.py`: resuming
re-runs the node from its first line. The review node therefore builds a pure
payload before pausing and writes nothing until the answer comes back.
"""

from datetime import date
from decimal import Decimal

import pytest
from langgraph.types import Command

from copiloto.analysis import Analysis, RiskPolicy
from copiloto.extractors.fake import FakeExtractor
from copiloto.graph.builder import build_graph
from copiloto.graph.nodes import build_review_alert
from copiloto.graph.state import CopilotState
from copiloto.models import ExtractedInvoice, InvoiceItem, Issue
from copiloto.registry import default_registry
from copiloto.scales import load_scales

TODAY = date(2026, 9, 24)
SCALES = load_scales()
CUIT = "20-11111111-2"
MONTHS = [date(2026, m, 15) for m in range(9, 0, -1)] + [
    date(2025, m, 15) for m in (12, 11, 10)
]


def invoice(total: str, number: str, issue_date: date, cuit: str = CUIT) -> ExtractedInvoice:
    amount = Decimal(total)
    item = InvoiceItem(
        description="Consultoria",
        quantity=Decimal("1"),
        unit_price=amount,
        total=amount,
        kind="service",
    )
    return ExtractedInvoice(
        number=number, issuer_cuit=cuit, issue_date=issue_date, items=(item,), total=amount
    )


def twelve(total: str, cuit: str = CUIT) -> dict[str, ExtractedInvoice]:
    return {
        f"text-{i}": invoice(total, f"0001-{i:08d}", d, cuit) for i, d in enumerate(MONTHS)
    }


@pytest.fixture
def graph():
    return build_graph(
        extractor=FakeExtractor(twelve("1200000")),
        registry=default_registry(),
        scales=SCALES,
        today=TODAY,
        policy=RiskPolicy(),
    )


def start(graph, thread: str, mapping=None) -> dict:
    texts = tuple(mapping if mapping is not None else twelve("1200000"))
    return graph.invoke(
        {"taxpayer_cuit": CUIT, "raw_invoices": texts},
        {"configurable": {"thread_id": thread}},
    )


class TestPausing:
    def test_a_category_change_pauses_for_an_accountant(self, graph) -> None:
        """12 x 1,200,000 = 14,400,000: category B, while A is on file."""
        result = start(graph, "pause-1")

        assert "__interrupt__" in result

    def test_a_paused_run_has_not_written_a_report_yet(self, graph) -> None:
        result = start(graph, "pause-2")

        assert "report" not in result

    def test_no_invoices_at_all_pauses_instead_of_reporting_all_clear(self, graph) -> None:
        result = start(graph, "pause-3", mapping={})

        assert "__interrupt__" in result

    def test_a_doubtful_invoice_pauses_even_when_the_income_is_calm(self) -> None:
        mapping = twelve("800000", cuit="20-11111111-3")
        calm = build_graph(
            extractor=FakeExtractor(mapping),
            registry=default_registry(),
            scales=SCALES,
            today=TODAY,
            policy=RiskPolicy(),
        )

        result = start(calm, "pause-4", mapping=mapping)

        assert "__interrupt__" in result


class TestAlertPayload:
    def test_the_alert_tells_the_accountant_why(self, graph) -> None:
        payload = start(graph, "payload-1")["__interrupt__"][0].value

        assert payload["risk_level"] == "medium"
        assert "CATEGORY_MISMATCH" in payload["reasons"]

    def test_the_alert_carries_the_figures_behind_the_verdict(self, graph) -> None:
        payload = start(graph, "payload-2")["__interrupt__"][0].value

        assert payload["accumulated_12m"] == "14400000"
        assert payload["computed_category"] == "B"
        assert payload["registered_category"] == "A"

    def test_the_alert_only_lists_issues_worth_a_human_look(self) -> None:
        """Informational issues are noise in an alert; they stay in the report."""
        state: CopilotState = {
            "analysis": Analysis(
                accumulated_12m=Decimal("1"),
                projected_12m=Decimal("1"),
                computed_category="A",
                registered_category="A",
                risk_level="low",
                reasons=(),
            ),
            "issues": [
                Issue(code="OUTSIDE_WINDOW", severity="info", message="m"),
                Issue(code="INVALID_CUIT", severity="warning", message="m"),
            ],
        }

        codes = [i["code"] for i in build_review_alert(state)["issues"]]

        assert codes == ["INVALID_CUIT"]


class TestReplaySafety:
    def test_building_the_alert_is_pure(self, graph) -> None:
        """Resuming re-runs the node, so everything before the pause runs twice.

        Calling the builder repeatedly must be indistinguishable from calling
        it once. Anything with an effect belongs after the resume.
        """
        state: CopilotState = {
            "analysis": Analysis(
                accumulated_12m=Decimal("14400000"),
                projected_12m=Decimal("14600000.00"),
                computed_category="B",
                registered_category="A",
                risk_level="medium",
                reasons=("CATEGORY_MISMATCH",),
            ),
            "issues": [],
        }

        assert build_review_alert(state) == build_review_alert(state)

    def test_resuming_produces_exactly_one_report(self, graph) -> None:
        start(graph, "replay-1")

        final = graph.invoke(
            Command(resume={"verdict": "confirmed", "notes": "Lo vi.", "reviewer": "accountant"}),
            {"configurable": {"thread_id": "replay-1"}},
        )

        assert final["report"].count("# Informe de monotributo") == 1


class TestResuming:
    def test_the_accountant_decision_reaches_the_report(self, graph) -> None:
        start(graph, "resume-1")

        final = graph.invoke(
            Command(
                resume={
                    "verdict": "confirmed",
                    "notes": "Corresponde recategorizar.",
                    "reviewer": "accountant",
                }
            ),
            {"configurable": {"thread_id": "resume-1"}},
        )

        assert final["human_decision"].reviewer == "accountant"
        assert "Corresponde recategorizar." in final["report"]
        assert "Revisado por un contador" in final["report"]

    def test_a_dismissed_case_still_ends_with_a_report(self, graph) -> None:
        start(graph, "resume-2")

        final = graph.invoke(
            Command(resume={"verdict": "dismissed", "notes": "Está bien así."}),
            {"configurable": {"thread_id": "resume-2"}},
        )

        assert "descartado" in final["report"]

    def test_an_automatic_resume_is_never_presented_as_a_review(self, graph) -> None:
        start(graph, "resume-3")

        final = graph.invoke(
            Command(resume={"verdict": "confirmed", "notes": "", "reviewer": "auto"}),
            {"configurable": {"thread_id": "resume-3"}},
        )

        assert "Ningún contador revisó este caso" in final["report"]

    def test_the_reviewer_defaults_to_the_accountant(self, graph) -> None:
        start(graph, "resume-4")

        final = graph.invoke(
            Command(resume={"verdict": "confirmed", "notes": "ok"}),
            {"configurable": {"thread_id": "resume-4"}},
        )

        assert final["human_decision"].reviewer == "accountant"


class TestThreadIsolation:
    def test_two_taxpayers_do_not_share_a_paused_case(self, graph) -> None:
        """The thread_id is what keeps one person's pause out of another's run."""
        start(graph, "thread-a")
        start(graph, "thread-b")

        finished_a = graph.invoke(
            Command(resume={"verdict": "confirmed", "notes": "caso A"}),
            {"configurable": {"thread_id": "thread-a"}},
        )
        finished_b = graph.invoke(
            Command(resume={"verdict": "dismissed", "notes": "caso B"}),
            {"configurable": {"thread_id": "thread-b"}},
        )

        assert "caso A" in finished_a["report"]
        assert "caso A" not in finished_b["report"]
        assert "caso B" in finished_b["report"]
