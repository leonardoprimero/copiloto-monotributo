"""Amount checks: internal consistency and the published maximum unit price.

The maximum unit price applies to "venta de cosas muebles" only. An item whose
kind was never determined is not silently excused: it raises a warning so a
human looks at it.
"""

from datetime import date
from decimal import Decimal

import pytest

from copiloto.models import ExtractedInvoice, InvoiceItem, ItemKind
from copiloto.scales import load_scales
from copiloto.validation import validate_invoice_amounts

MAX_UNIT_PRICE = Decimal("716840.77")


@pytest.fixture(scope="module")
def scales():
    return load_scales()


def an_item(**overrides) -> InvoiceItem:
    defaults = {
        "description": "Item",
        "quantity": Decimal("1"),
        "unit_price": Decimal("100.00"),
        "total": Decimal("100.00"),
        "kind": "service",
    }
    return InvoiceItem(**{**defaults, **overrides})


def an_invoice(items: tuple[InvoiceItem, ...], total: Decimal) -> ExtractedInvoice:
    return ExtractedInvoice(
        number="0001-00000001",
        issuer_cuit="20-11111111-2",
        issue_date=date(2026, 9, 15),
        items=items,
        total=total,
    )


def codes(invoice: ExtractedInvoice, scales) -> list[str]:
    return [issue.code for issue in validate_invoice_amounts(invoice, scales)]


class TestConsistency:
    def test_a_coherent_invoice_raises_nothing(self, scales) -> None:
        invoice = an_invoice((an_item(),), Decimal("100.00"))

        assert codes(invoice, scales) == []

    def test_total_must_equal_the_sum_of_its_items(self, scales) -> None:
        invoice = an_invoice((an_item(), an_item()), Decimal("100.00"))

        assert "TOTAL_MISMATCH" in codes(invoice, scales)

    def test_a_one_cent_difference_is_still_a_mismatch(self, scales) -> None:
        """Decimal, not float: the cent is the unit that matters here."""
        invoice = an_invoice((an_item(),), Decimal("100.01"))

        assert "TOTAL_MISMATCH" in codes(invoice, scales)

    def test_item_total_must_equal_quantity_times_unit_price(self, scales) -> None:
        item = an_item(quantity=Decimal("3"), unit_price=Decimal("100"), total=Decimal("100"))
        invoice = an_invoice((item,), Decimal("100"))

        assert "ITEM_TOTAL_MISMATCH" in codes(invoice, scales)

    @pytest.mark.parametrize("amount", ["0", "-1"])
    def test_non_positive_amounts_are_flagged(self, amount: str, scales) -> None:
        item = an_item(unit_price=Decimal(amount), total=Decimal(amount))
        invoice = an_invoice((item,), Decimal(amount))

        assert "NON_POSITIVE_AMOUNT" in codes(invoice, scales)


class TestMaximumUnitPrice:
    def test_a_good_at_exactly_the_cap_is_allowed(self, scales) -> None:
        """The published wording is a maximum, so the cap itself is valid."""
        item = an_item(kind="good", unit_price=MAX_UNIT_PRICE, total=MAX_UNIT_PRICE)
        invoice = an_invoice((item,), MAX_UNIT_PRICE)

        assert codes(invoice, scales) == []

    def test_a_good_one_cent_above_the_cap_is_flagged(self, scales) -> None:
        over = MAX_UNIT_PRICE + Decimal("0.01")
        item = an_item(kind="good", unit_price=over, total=over)
        invoice = an_invoice((item,), over)

        assert "UNIT_PRICE_ABOVE_MAX" in codes(invoice, scales)

    def test_a_service_above_the_cap_is_not_flagged(self, scales) -> None:
        """The cap does not apply to services, so this must stay silent."""
        over = MAX_UNIT_PRICE + Decimal("0.01")
        item = an_item(kind="service", unit_price=over, total=over)
        invoice = an_invoice((item,), over)

        assert codes(invoice, scales) == []

    def test_an_unclassified_item_above_the_cap_is_escalated(self, scales) -> None:
        """The gap a default of "service" would have hidden.

        Nobody said this item was a service; the kind was simply never
        determined. Rather than excuse it, report that the cap could not be
        applied and let a human decide.
        """
        over = MAX_UNIT_PRICE + Decimal("0.01")
        item = an_item(kind="unknown", unit_price=over, total=over)
        invoice = an_invoice((item,), over)

        assert "UNIT_PRICE_KIND_UNKNOWN" in codes(invoice, scales)

    def test_an_unclassified_item_below_the_cap_stays_quiet(self, scales) -> None:
        item = an_item(kind="unknown")
        invoice = an_invoice((item,), Decimal("100.00"))

        assert codes(invoice, scales) == []


class TestSeverities:
    @pytest.mark.parametrize(
        ("kind", "expected_code", "expected_severity"),
        [
            ("good", "UNIT_PRICE_ABOVE_MAX", "error"),
            ("unknown", "UNIT_PRICE_KIND_UNKNOWN", "warning"),
        ],
    )
    def test_price_issues_carry_the_right_severity(
        self, kind: ItemKind, expected_code: str, expected_severity: str, scales
    ) -> None:
        over = MAX_UNIT_PRICE + Decimal("0.01")
        item = an_item(kind=kind, unit_price=over, total=over)
        invoice = an_invoice((item,), over)

        issue = next(i for i in validate_invoice_amounts(invoice, scales) if i.code == expected_code)

        assert issue.severity == expected_severity

    def test_issues_name_the_invoice_they_came_from(self, scales) -> None:
        invoice = an_invoice((an_item(), an_item()), Decimal("100.00"))

        issues = validate_invoice_amounts(invoice, scales)

        assert all(issue.invoice_number == "0001-00000001" for issue in issues)
