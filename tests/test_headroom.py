"""Headroom: how much can still be invoiced, and how soon the cap arrives.

A category and a risk level describe where the taxpayer stands. Headroom
describes what they can still do about it, which is the question a copilot is
actually asked. Plain arithmetic over numbers the analysis already has.
"""

from datetime import date
from decimal import Decimal

from copiloto.analysis import RiskPolicy, analyze
from copiloto.models import ExtractedInvoice, InvoiceItem, TaxpayerProfile
from copiloto.scales import load_scales

TODAY = date(2026, 9, 24)
SCALES = load_scales()
POLICY = RiskPolicy()

A_CAP = Decimal("12009410.45")
K_CAP = Decimal("126610838.75")

REGISTERED_A = TaxpayerProfile(cuit="20-11111111-2", name="Synthetic One", category="A")

OLD = date(2026, 1, 15)  # inside the year, outside the last 90 days
RECENT = [date(2026, 7, 15), date(2026, 8, 15), date(2026, 9, 15)]


def invoice(issue_date: date, total: str, number: str = "0001-00000001") -> ExtractedInvoice:
    amount = Decimal(total)
    item = InvoiceItem(
        description="Item", quantity=Decimal("1"), unit_price=amount, total=amount, kind="service"
    )
    return ExtractedInvoice(
        number=number, issuer_cuit="20-11111111-2", issue_date=issue_date, items=(item,), total=amount
    )


def recent(amount: str) -> tuple[ExtractedInvoice, ...]:
    return tuple(invoice(d, amount, f"0001-{i:08d}") for i, d in enumerate(RECENT))


def analysis(invoices, *, taxpayer: TaxpayerProfile | None = REGISTERED_A):
    return analyze(
        invoices, issues=(), taxpayer=taxpayer, today=TODAY, scales=SCALES, policy=POLICY
    )


class TestHeadroomToTheRegisteredCap:
    def test_is_the_cap_minus_the_accumulated_income(self) -> None:
        # 3 x 1,000,000 = 3,000,000 -> 12,009,410.45 - 3,000,000
        result = analysis(recent("1000000"))

        assert result.headroom_registered == Decimal("9009410.45")

    def test_is_zero_exactly_at_the_cap(self) -> None:
        """Caps are inclusive: sitting on the cap leaves nothing, but is not over."""
        result = analysis((invoice(OLD, str(A_CAP)),))

        assert result.headroom_registered == Decimal("0")

    def test_goes_negative_once_the_cap_is_exceeded(self) -> None:
        """A negative headroom is the amount by which the cap was passed."""
        result = analysis((invoice(OLD, "12009510.45"),))

        assert result.headroom_registered == Decimal("-100.00")

    def test_is_unknown_without_a_registered_category(self) -> None:
        result = analysis(recent("1000000"), taxpayer=None)

        assert result.headroom_registered is None


class TestHeadroomToTheTopCap:
    def test_is_the_top_cap_minus_the_accumulated_income(self) -> None:
        result = analysis(recent("1000000"))

        assert result.headroom_top == K_CAP - Decimal("3000000")

    def test_exists_even_without_a_registered_category(self) -> None:
        """Exclusion by income threatens everyone, registered or not."""
        result = analysis(recent("1000000"), taxpayer=None)

        assert result.headroom_top == K_CAP - Decimal("3000000")


class TestMonthsUntilTheRegisteredCap:
    def test_divides_the_headroom_by_the_monthly_pace(self) -> None:
        # Pace: 3 x 1,000,000 in 90 days -> projected 12,166,666.67 -> 1,013,888.89 per month.
        # Headroom 9,009,410.45 / 1,013,888.89 = 8.886... -> 8.9 months
        result = analysis(recent("1000000"))

        assert result.months_to_registered_cap == Decimal("8.9")

    def test_is_zero_once_the_cap_is_reached(self) -> None:
        """Nothing left to run down: the cap is already here."""
        result = analysis((invoice(RECENT[0], str(A_CAP)),))

        assert result.months_to_registered_cap == Decimal("0")

    def test_is_unknown_when_nothing_was_invoiced_recently(self) -> None:
        """No pace, no estimate. Reporting 'never' would be a guess."""
        result = analysis((invoice(OLD, "1000000"),))

        assert result.months_to_registered_cap is None

    def test_is_unknown_without_a_registered_category(self) -> None:
        result = analysis(recent("1000000"), taxpayer=None)

        assert result.months_to_registered_cap is None


class TestMonthsUntilTheTopCap:
    def test_divides_the_headroom_by_the_monthly_pace(self) -> None:
        # Headroom 123,610,838.75 / 1,013,888.89 = 121.917... -> 121.9 months
        result = analysis(recent("1000000"))

        assert result.months_to_top_cap == Decimal("121.9")

    def test_is_zero_once_the_regime_cap_is_reached(self) -> None:
        result = analysis((invoice(RECENT[0], str(K_CAP)),))

        assert result.months_to_top_cap == Decimal("0")

    def test_is_unknown_when_nothing_was_invoiced_recently(self) -> None:
        result = analysis((invoice(OLD, "1000000"),))

        assert result.months_to_top_cap is None
