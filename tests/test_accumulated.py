"""Accumulated income over the rolling window, and the category it implies.

Only invoices inside the window count. Invoices that carry issues still count:
the issue already routes the case to a human, and dropping their amounts would
understate the income instead of flagging it.
"""

from datetime import date
from decimal import Decimal

from copiloto.analysis import accumulated_income, computed_category
from copiloto.models import ExtractedInvoice, InvoiceItem
from copiloto.scales import load_scales

TODAY = date(2026, 9, 24)
SCALES = load_scales()


def an_invoice(issue_date: date, total: str, number: str = "0001-00000001") -> ExtractedInvoice:
    amount = Decimal(total)
    item = InvoiceItem(
        description="Item",
        quantity=Decimal("1"),
        unit_price=amount,
        total=amount,
        kind="service",
    )
    return ExtractedInvoice(
        number=number,
        issuer_cuit="20-11111111-2",
        issue_date=issue_date,
        items=(item,),
        total=amount,
    )


def monthly(amount: str, months: int = 12) -> tuple[ExtractedInvoice, ...]:
    """`months` invoices, one on the 15th of each month ending in September 2026."""
    dates = [
        date(2026, m, 15) if m <= 9 else date(2025, m, 15)
        for m in [*range(9, 0, -1), 12, 11, 10][:months]
    ]
    return tuple(an_invoice(d, amount, f"0001-{i:08d}") for i, d in enumerate(dates))


class TestAccumulatedIncome:
    def test_no_invoices_accumulate_zero(self) -> None:
        assert accumulated_income((), today=TODAY) == Decimal("0")

    def test_sums_invoices_inside_the_window(self) -> None:
        assert accumulated_income(monthly("800000"), today=TODAY) == Decimal("9600000")

    def test_ignores_invoices_outside_the_window(self) -> None:
        inside = monthly("800000")
        stale = an_invoice(date(2025, 9, 15), "5000000", "0001-00000099")

        assert accumulated_income((*inside, stale), today=TODAY) == Decimal("9600000")

    def test_keeps_cents_exact(self) -> None:
        invoices = (
            an_invoice(TODAY, "0.10", "0001-00000001"),
            an_invoice(TODAY, "0.20", "0001-00000002"),
        )

        # 0.1 + 0.2 != 0.3 in binary floating point. With Decimal it does.
        assert accumulated_income(invoices, today=TODAY) == Decimal("0.30")

    def test_an_invoice_dated_today_counts(self) -> None:
        assert accumulated_income((an_invoice(TODAY, "100"),), today=TODAY) == Decimal("100")


class TestComputedCategory:
    def test_maps_the_accumulated_income_to_a_category(self) -> None:
        category = computed_category(monthly("800000"), today=TODAY, scales=SCALES)

        assert category is not None
        assert category.name == "A"

    def test_crossing_a_cap_moves_up_a_category(self) -> None:
        # 12 x 1,200,000 = 14,400,000, above the category A cap.
        category = computed_category(monthly("1200000"), today=TODAY, scales=SCALES)

        assert category is not None
        assert category.name == "B"

    def test_above_the_top_cap_there_is_no_category(self) -> None:
        # 12 x 11,000,000 = 132,000,000, above the category K cap.
        assert computed_category(monthly("11000000"), today=TODAY, scales=SCALES) is None

    def test_no_invoices_still_yields_the_lowest_category(self) -> None:
        """Zero income maps to A; whether that is meaningful is the risk rules' call."""
        category = computed_category((), today=TODAY, scales=SCALES)

        assert category is not None
        assert category.name == "A"
