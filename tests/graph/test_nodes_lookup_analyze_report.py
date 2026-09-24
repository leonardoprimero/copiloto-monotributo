"""The remaining pipeline nodes: registry lookup, analysis and report.

Together with the two extraction nodes these cover everything except the
human-in-the-loop pause, which needs a checkpointer and is tested separately.
"""

from datetime import date
from decimal import Decimal

from copiloto.analysis import RiskPolicy
from copiloto.graph.nodes import make_analyze_node, make_lookup_node, make_report_node
from copiloto.graph.state import CopilotState
from copiloto.models import ExtractedInvoice, HumanDecision, InvoiceItem, Issue
from copiloto.registry import default_registry
from copiloto.scales import load_scales

TODAY = date(2026, 9, 24)
SCALES = load_scales()
POLICY = RiskPolicy()
KNOWN_CUIT = "20-11111111-2"
VALID_UNKNOWN_CUIT = "23-33333333-3"


def invoice(total: str, issue_date: date = date(2026, 9, 15)) -> ExtractedInvoice:
    amount = Decimal(total)
    item = InvoiceItem(
        description="Consultoria",
        quantity=Decimal("1"),
        unit_price=amount,
        total=amount,
        kind="service",
    )
    return ExtractedInvoice(
        number="0001-00000001",
        issuer_cuit=KNOWN_CUIT,
        issue_date=issue_date,
        items=(item,),
        total=amount,
    )


class TestLookupNode:
    def test_finds_a_registered_taxpayer(self) -> None:
        node = make_lookup_node(default_registry())

        result = node({"taxpayer_cuit": KNOWN_CUIT})

        assert result["taxpayer"] is not None
        assert result["taxpayer"].category == "A"
        assert result["issues"] == []

    def test_an_unknown_taxpayer_is_reported_not_invented(self) -> None:
        node = make_lookup_node(default_registry())

        result = node({"taxpayer_cuit": VALID_UNKNOWN_CUIT})

        assert result["taxpayer"] is None
        assert [i.code for i in result["issues"]] == ["TAXPAYER_NOT_FOUND"]

    def test_an_unknown_taxpayer_is_a_warning_so_a_human_looks_at_it(self) -> None:
        node = make_lookup_node(default_registry())

        result = node({"taxpayer_cuit": VALID_UNKNOWN_CUIT})

        assert result["issues"][0].severity == "warning"


class TestAnalyzeNode:
    def test_produces_the_analysis_from_invoices_issues_and_taxpayer(self) -> None:
        node = make_analyze_node(scales=SCALES, today=TODAY, policy=POLICY)

        result = node(
            {
                "invoices": (invoice("800000"),),
                "issues": [],
                "taxpayer": default_registry().lookup(KNOWN_CUIT),
            }
        )

        assert result["analysis"].risk_level == "low"
        assert result["analysis"].registered_category == "A"

    def test_reads_the_issues_the_earlier_nodes_appended(self) -> None:
        """An over-priced good is exclusion, and that arrives as an issue."""
        node = make_analyze_node(scales=SCALES, today=TODAY, policy=POLICY)
        over_priced = Issue(code="UNIT_PRICE_ABOVE_MAX", severity="error", message="m")

        result = node(
            {
                "invoices": (invoice("800000"),),
                "issues": [over_priced],
                "taxpayer": default_registry().lookup(KNOWN_CUIT),
            }
        )

        assert result["analysis"].risk_level == "exclusion"

    def test_writes_only_the_analysis(self) -> None:
        node = make_analyze_node(scales=SCALES, today=TODAY, policy=POLICY)

        result = node({"invoices": (), "issues": [], "taxpayer": None})

        assert set(result) == {"analysis"}


def rendered(state: CopilotState) -> str:
    """Run analyze then write_report, the way the graph chains them."""
    analyze = make_analyze_node(scales=SCALES, today=TODAY, policy=POLICY)
    report = make_report_node(scales=SCALES)
    state.update(analyze(state))
    return report(state)["report"]


class TestReportNode:
    def test_renders_the_report_into_the_state(self) -> None:
        analyze = make_analyze_node(scales=SCALES, today=TODAY, policy=POLICY)
        report = make_report_node(scales=SCALES)
        state: CopilotState = {
            "invoices": (invoice("800000"),),
            "issues": [],
            "taxpayer": default_registry().lookup(KNOWN_CUIT),
        }
        state.update(analyze(state))

        result = report(state)

        assert set(result) == {"report"}
        assert "# Informe de monotributo" in result["report"]

    def test_counts_the_invoices_it_actually_analysed(self) -> None:
        state: CopilotState = {"invoices": (), "issues": [], "taxpayer": None}

        assert "No se recibió ninguna factura" in rendered(state)

    def test_carries_the_human_decision_into_the_report(self) -> None:
        state: CopilotState = {
            "invoices": (invoice("800000"),),
            "issues": [],
            "taxpayer": default_registry().lookup(KNOWN_CUIT),
            "human_decision": HumanDecision(
                verdict="confirmed", notes="Lo revisé.", reviewer="accountant"
            ),
        }

        assert "Lo revisé." in rendered(state)

    def test_an_automatic_resume_is_labelled_in_the_report(self) -> None:
        state: CopilotState = {
            "invoices": (invoice("800000"),),
            "issues": [],
            "taxpayer": default_registry().lookup(KNOWN_CUIT),
            "human_decision": HumanDecision(verdict="confirmed", notes="", reviewer="auto"),
        }

        assert "Ningún contador revisó este caso" in rendered(state)
