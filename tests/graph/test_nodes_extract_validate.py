"""The first steps: the AI reads, the code judges.

Reading is the only place a model participates, and it happens once per
invoice in parallel. `extract` below runs those tasks and the collector the
way the graph does, so these tests keep describing the step as a whole.
Everything it produces is then checked by `validate_invoices`, which decides
nothing about risk yet — it only records what does not add up.
"""

from datetime import date
from decimal import Decimal


from copiloto.extractors.fake import FakeExtractor
from copiloto.graph.nodes import (
    collect_invoices,
    make_extract_one_node,
    make_validate_node,
)
from copiloto.models import ExtractedInvoice, InvoiceItem
from copiloto.scales import load_scales

TODAY = date(2026, 9, 24)
SCALES = load_scales()
CUIT = "20-11111111-2"


def invoice(cuit: str = CUIT, issue_date: date = date(2026, 9, 15)) -> ExtractedInvoice:
    item = InvoiceItem(
        description="Consultoria",
        quantity=Decimal("1"),
        unit_price=Decimal("800000.00"),
        total=Decimal("800000.00"),
        kind="service",
    )
    return ExtractedInvoice(
        number="0001-00000001",
        issuer_cuit=cuit,
        issue_date=issue_date,
        items=(item,),
        total=Decimal("800000.00"),
    )


def extract(raw_invoices: tuple[str, ...], mapping=None) -> dict:
    """Fan out, then collect, merging writes the way the reducers do."""
    one = make_extract_one_node(FakeExtractor(mapping if mapping is not None else {}))

    extracted: list[ExtractedInvoice] = []
    issues = []
    for raw in raw_invoices:
        written = one({"raw": raw})
        extracted += written.get("extracted", [])
        issues += written.get("issues", [])

    collected = collect_invoices(
        {"taxpayer_cuit": CUIT, "raw_invoices": raw_invoices, "extracted": extracted}
    )
    return {
        "invoices": collected["invoices"],
        "issues": issues + collected.get("issues", []),
    }


def validate(invoices: tuple[ExtractedInvoice, ...]) -> list[str]:
    node = make_validate_node(scales=SCALES, today=TODAY)
    result = node({"taxpayer_cuit": CUIT, "invoices": invoices})
    return [issue.code for issue in result["issues"]]


class TestExtractNode:
    def test_reads_every_invoice_it_is_given(self) -> None:
        result = extract(("text-a",), {"text-a": invoice()})

        assert result["invoices"] == (invoice(),)
        assert result["issues"] == []

    def test_a_failed_extraction_becomes_an_issue_and_the_rest_continues(self) -> None:
        """One unreadable invoice must not abort the other eleven."""
        result = extract(("good", "bad"), {"good": invoice()})

        assert len(result["invoices"]) == 1
        assert [i.code for i in result["issues"]] == ["EXTRACTION_FAILED"]

    def test_a_failed_extraction_is_a_warning_so_a_human_looks_at_it(self) -> None:
        result = extract(("bad",), {})

        assert result["issues"][0].severity == "warning"

    def test_no_invoices_is_missing_data_not_a_clean_result(self) -> None:
        """Zero invoices would otherwise accumulate zero and look like category A."""
        result = extract((), {})

        assert [i.code for i in result["issues"]] == ["NO_INVOICES"]
        assert result["issues"][0].severity == "warning"
        assert result["invoices"] == ()

    def test_the_node_never_decides_anything_about_risk(self) -> None:
        result = extract(("text-a",), {"text-a": invoice()})

        assert "analysis" not in result
        assert "report" not in result


class TestValidateNode:
    def test_a_clean_invoice_raises_nothing(self) -> None:
        assert validate((invoice(),)) == []

    def test_an_invalid_cuit_is_flagged(self) -> None:
        assert "INVALID_CUIT" in validate((invoice(cuit="20-11111111-3"),))

    def test_an_issuer_that_is_not_the_taxpayer_is_flagged(self) -> None:
        """A valid CUIT belonging to somebody else is still the wrong invoice."""
        assert "ISSUER_MISMATCH" in validate((invoice(cuit="27-22222222-8"),))

    def test_an_invalid_cuit_is_not_also_reported_as_a_mismatch(self) -> None:
        assert validate((invoice(cuit="20-11111111-3"),)) == ["INVALID_CUIT"]

    def test_a_future_date_is_flagged(self) -> None:
        assert "DATE_IN_FUTURE" in validate((invoice(issue_date=date(2026, 12, 15)),))

    def test_an_invoice_outside_the_window_is_reported(self) -> None:
        assert "OUTSIDE_WINDOW" in validate((invoice(issue_date=date(2025, 9, 15)),))

    def test_collects_issues_from_every_invoice(self) -> None:
        codes = validate(
            (invoice(cuit="20-11111111-3"), invoice(issue_date=date(2026, 12, 15)))
        )

        assert set(codes) == {"INVALID_CUIT", "DATE_IN_FUTURE"}

    def test_validating_nothing_raises_nothing(self) -> None:
        """The empty case is already reported by the extract node."""
        assert validate(()) == []


class TestStateContract:
    def test_a_successful_task_writes_only_its_invoice(self) -> None:
        """One task, one write: the reducer does the merging."""
        one = make_extract_one_node(FakeExtractor({"text-a": invoice()}))

        assert set(one({"raw": "text-a"})) == {"extracted"}

    def test_a_failed_task_writes_only_its_issue(self) -> None:
        one = make_extract_one_node(FakeExtractor({}))

        assert set(one({"raw": "bad"})) == {"issues"}

    def test_the_collector_writes_only_invoices(self) -> None:
        assert set(collect_invoices({"raw_invoices": ("a",), "extracted": [invoice()]})) == {
            "invoices"
        }

    def test_the_collector_reports_the_empty_case(self) -> None:
        assert set(collect_invoices({"raw_invoices": (), "extracted": []})) == {
            "invoices",
            "issues",
        }

    def test_validate_writes_only_issues(self) -> None:
        node = make_validate_node(scales=SCALES, today=TODAY)

        result = node({"taxpayer_cuit": CUIT, "invoices": (invoice(),)})

        assert set(result) == {"issues"}
