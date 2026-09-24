"""The assembled graph, end to end.

Uses the fake extractor and a fixed clock, so these run offline and always
give the same answer. The review branch is wired here; the pause itself is
covered separately.
"""

from datetime import date
from decimal import Decimal

from copiloto.analysis import RiskPolicy
from copiloto.extractors.fake import FakeExtractor
from copiloto.graph.builder import build_graph
from copiloto.models import ExtractedInvoice, InvoiceItem
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
        number=number,
        issuer_cuit=cuit,
        issue_date=issue_date,
        items=(item,),
        total=amount,
    )


def twelve(total: str, cuit: str = CUIT) -> dict[str, ExtractedInvoice]:
    return {
        f"text-{i}": invoice(total, f"0001-{i:08d}", d, cuit)
        for i, d in enumerate(MONTHS)
    }


def run(mapping: dict[str, ExtractedInvoice], policy: RiskPolicy | None = None) -> dict:
    graph = build_graph(
        extractor=FakeExtractor(mapping),
        registry=default_registry(),
        scales=SCALES,
        today=TODAY,
        policy=policy or RiskPolicy(),
    )
    return graph.invoke(
        {"taxpayer_cuit": CUIT, "raw_invoices": tuple(mapping)},
        {"configurable": {"thread_id": "test"}},
    )


class TestHappyPath:
    def test_a_calm_taxpayer_reaches_the_report_without_stopping(self) -> None:
        result = run(twelve("800000"))

        assert "__interrupt__" not in result
        assert "# Informe de monotributo" in result["report"]

    def test_the_report_carries_the_computed_figures(self) -> None:
        result = run(twelve("800000"))

        assert result["analysis"].accumulated_12m == Decimal("9600000")
        assert result["analysis"].risk_level == "low"

    def test_the_taxpayer_was_looked_up(self) -> None:
        result = run(twelve("800000"))

        assert result["taxpayer"] is not None
        assert result["taxpayer"].category == "A"


class TestReviewBranch:
    """Routing into the review branch. The pause itself is covered by the
    human-in-the-loop tests, which need the real `interrupt()`."""

    def test_the_lenient_policy_lets_a_category_change_through(self) -> None:
        lenient = RiskPolicy(review_levels=frozenset({"high", "exclusion"}))

        result = run(twelve("1200000"), policy=lenient)

        assert "__interrupt__" not in result
        assert "# Informe de monotributo" in result["report"]


class TestIssueAccumulation:
    def test_issues_from_different_nodes_are_kept_together(self) -> None:
        """The reducer on `issues` is what stops one node erasing another's.

        An unknown taxpayer (lookup), a bad CUIT (validate) and an unreadable
        text (extract) all contribute, and all three must survive.
        """
        mapping = twelve("800000", cuit="20-11111111-3")
        graph = build_graph(
            extractor=FakeExtractor(mapping),
            registry=default_registry(),
            scales=SCALES,
            today=TODAY,
            policy=RiskPolicy(),
        )

        result = graph.invoke(
            {
                "taxpayer_cuit": "23-33333333-3",
                "raw_invoices": (*mapping, "never-mapped"),
            },
            {"configurable": {"thread_id": "accumulation"}},
        )

        codes = {i.code for i in result["issues"]}
        assert "EXTRACTION_FAILED" in codes  # from extract_invoices
        assert "INVALID_CUIT" in codes  # from validate_invoices
        assert "TAXPAYER_NOT_FOUND" in codes  # from lookup_taxpayer


class TestStructure:
    def test_the_graph_exposes_its_nodes(self) -> None:
        graph = build_graph(
            extractor=FakeExtractor({}),
            registry=default_registry(),
            scales=SCALES,
            today=TODAY,
            policy=RiskPolicy(),
        )

        nodes = set(graph.get_graph().nodes)

        assert {
            "extract_one",
            "collect_invoices",
            "validate_invoices",
            "lookup_taxpayer",
            "analyze_income",
            "request_accountant_review",
            "write_report",
        } <= nodes
