"""Dates and the rolling twelve-month window.

The window is `(today - 1 year, today]`: the last twelve months counted
backwards from today, not the calendar year. `today` is always injected so the
suite gives the same answer whenever it runs.
"""

from datetime import date
from decimal import Decimal

from copiloto.dates import one_year_before, within_window
from copiloto.models import ExtractedInvoice, InvoiceItem
from copiloto.validation import validate_invoice_dates

TODAY = date(2026, 9, 24)
WINDOW_START = date(2025, 9, 24)


def an_invoice(issue_date: date) -> ExtractedInvoice:
    item = InvoiceItem(
        description="Item",
        quantity=Decimal("1"),
        unit_price=Decimal("100.00"),
        total=Decimal("100.00"),
        kind="service",
    )
    return ExtractedInvoice(
        number="0001-00000001",
        issuer_cuit="20-11111111-2",
        issue_date=issue_date,
        items=(item,),
        total=Decimal("100.00"),
    )


def codes(issue_date: date) -> list[str]:
    return [i.code for i in validate_invoice_dates(an_invoice(issue_date), today=TODAY)]


class TestOneYearBefore:
    def test_subtracts_a_calendar_year(self) -> None:
        assert one_year_before(TODAY) == WINDOW_START

    def test_february_29_falls_back_to_february_28(self) -> None:
        """2028 is a leap year; 2027 is not, so Feb 29 has no counterpart."""
        assert one_year_before(date(2028, 2, 29)) == date(2027, 2, 28)


class TestWindowBoundaries:
    def test_today_is_inside_the_window(self) -> None:
        assert within_window(TODAY, today=TODAY) is True

    def test_the_day_after_the_start_is_inside(self) -> None:
        assert within_window(date(2025, 9, 25), today=TODAY) is True

    def test_the_start_date_itself_is_outside(self) -> None:
        """The window is half-open, so exactly one year ago is already out."""
        assert within_window(WINDOW_START, today=TODAY) is False

    def test_an_older_date_is_outside(self) -> None:
        assert within_window(date(2025, 1, 1), today=TODAY) is False


class TestValidation:
    def test_an_invoice_inside_the_window_raises_nothing(self) -> None:
        assert codes(date(2026, 9, 15)) == []

    def test_a_future_invoice_is_flagged(self) -> None:
        assert "DATE_IN_FUTURE" in codes(date(2026, 12, 15))

    def test_an_invoice_outside_the_window_is_reported_as_information(self) -> None:
        """Not an error: old invoices are legitimate, they just do not count."""
        issues = validate_invoice_dates(an_invoice(date(2025, 9, 15)), today=TODAY)

        assert [i.code for i in issues] == ["OUTSIDE_WINDOW"]
        assert issues[0].severity == "info"

    def test_a_future_invoice_is_an_error_not_information(self) -> None:
        issues = validate_invoice_dates(an_invoice(date(2026, 12, 15)), today=TODAY)

        assert issues[0].severity == "error"

    def test_a_future_invoice_is_not_also_reported_as_outside_the_window(self) -> None:
        assert codes(date(2026, 12, 15)) == ["DATE_IN_FUTURE"]
