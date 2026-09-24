"""Projection and risk level.

Every condition in the policy gets a test that isolates it, plus a test at its
boundary. Passing the eval suite is not evidence that a rule is implemented:
several rules can produce the same level, so only an isolating test proves the
rule itself exists.

The projection is this project's own heuristic, not an ARCA formula.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from copiloto.analysis import RiskPolicy, analyze, projected_income
from copiloto.models import ExtractedInvoice, InvoiceItem, Issue, TaxpayerProfile
from copiloto.scales import load_scales

TODAY = date(2026, 9, 24)
SCALES = load_scales()
POLICY = RiskPolicy()

A_CAP = Decimal("12009410.45")
H_CAP = Decimal("81924660.37")
K_CAP = Decimal("126610838.75")
NINETY_PERCENT_OF_K = Decimal("113949754.875")

REGISTERED_A = TaxpayerProfile(cuit="20-11111111-2", name="Synthetic One", category="A")
REGISTERED_H = TaxpayerProfile(cuit="30-44444444-0", name="Synthetic Four", category="H")
REGISTERED_K = TaxpayerProfile(cuit="27-22222222-8", name="Synthetic Two", category="K")

OLD = date(2026, 1, 15)  # inside the year, outside the last 90 days
RECENT = [date(2026, 7, 15), date(2026, 8, 15), date(2026, 9, 15)]


def invoice(issue_date: date, total: str, number: str = "0001-00000001") -> ExtractedInvoice:
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


def recent(amount: str) -> tuple[ExtractedInvoice, ...]:
    return tuple(invoice(d, amount, f"0001-{i:08d}") for i, d in enumerate(RECENT))


def assess(invoices, *, taxpayer=None, issues=()) -> tuple[str, tuple[str, ...]]:
    result = analyze(
        invoices, issues=issues, taxpayer=taxpayer, today=TODAY, scales=SCALES, policy=POLICY
    )
    return result.risk_level, result.reasons


class TestProjection:
    def test_no_invoices_project_zero(self) -> None:
        assert projected_income((), today=TODAY, policy=POLICY) == Decimal("0")

    def test_annualizes_the_last_ninety_days(self) -> None:
        # 3 x 12,000,000 = 36,000,000 over 90 days -> x 365/90 = 146,000,000
        assert projected_income(recent("12000000"), today=TODAY, policy=POLICY) == Decimal(
            "146000000.00"
        )

    def test_rounds_to_two_decimals(self) -> None:
        # 3,000,000 / 90 * 365 = 12,166,666.666...
        assert projected_income(recent("1000000"), today=TODAY, policy=POLICY) == Decimal(
            "12166666.67"
        )

    def test_ignores_invoices_older_than_the_projection_window(self) -> None:
        assert projected_income((invoice(OLD, "50000000"),), today=TODAY, policy=POLICY) == Decimal(
            "0"
        )

    def test_the_projection_window_edge_is_half_open(self) -> None:
        edge = TODAY - timedelta(days=POLICY.projection_days)

        assert projected_income((invoice(edge, "100"),), today=TODAY, policy=POLICY) == Decimal("0")
        assert projected_income(
            (invoice(edge + timedelta(days=1), "100"),), today=TODAY, policy=POLICY
        ) > Decimal("0")


class TestLowRisk:
    def test_comfortable_income_is_low(self) -> None:
        level, reasons = assess(recent("100000"), taxpayer=REGISTERED_A)

        assert level == "low"
        assert reasons == ()

    def test_an_unknown_taxpayer_skips_every_registered_comparison(self) -> None:
        """Without a registered category there is nothing to compare against."""
        level, _ = assess((invoice(OLD, "11400000"),), taxpayer=None)

        assert level == "low"


class TestMediumRisk:
    def test_near_the_registered_cap(self) -> None:
        level, reasons = assess((invoice(OLD, "11400000"),), taxpayer=REGISTERED_A)

        assert level == "medium"
        assert reasons == ("NEAR_REGISTERED_CAP",)

    def test_near_the_registered_cap_boundary(self) -> None:
        # 90% of the category A cap is 10,808,469.405, which is not a whole
        # number of cents. The threshold is the exact product, so an invoice
        # cannot land on it: the nearest cents fall on either side.
        assert A_CAP * Decimal("0.9") == Decimal("10808469.405")

        above = assess((invoice(OLD, "10808469.41"),), taxpayer=REGISTERED_A)
        below = assess((invoice(OLD, "10808469.40"),), taxpayer=REGISTERED_A)

        assert above[0] == "medium"
        assert below[0] == "low"

    def test_the_computed_category_differs_from_the_registered_one(self) -> None:
        # 14,400,000 lands in B while the taxpayer is registered in A.
        level, reasons = assess((invoice(OLD, "14400000"),), taxpayer=REGISTERED_A)

        assert level == "medium"
        assert "CATEGORY_MISMATCH" in reasons

    def test_the_projection_exceeds_the_registered_cap(self) -> None:
        """Isolated: income is comfortable, only the recent pace is a problem."""
        level, reasons = assess(recent("1000000"), taxpayer=REGISTERED_A)

        assert level == "medium"
        assert reasons == ("PROJECTION_ABOVE_REGISTERED_CAP",)


class TestHighRisk:
    def test_the_projection_exceeds_the_top_cap(self) -> None:
        level, reasons = assess(recent("12000000"), taxpayer=REGISTERED_H)

        assert level == "high"
        assert "PROJECTION_ABOVE_TOP_CAP" in reasons

    def test_accumulated_income_near_the_top_cap(self) -> None:
        """Isolated from the projection: the invoice is old, so the pace is zero."""
        level, reasons = assess(
            (invoice(OLD, "113949754.88"),), taxpayer=REGISTERED_K
        )

        assert level == "high"
        assert "NEAR_TOP_CAP" in reasons

    def test_accumulated_income_near_the_top_cap_boundary(self) -> None:
        # 90% of the category K cap is 113,949,754.875
        assert K_CAP * Decimal("0.9") == NINETY_PERCENT_OF_K

        above = assess((invoice(OLD, "113949754.88"),), taxpayer=REGISTERED_K)
        below = assess((invoice(OLD, "113949754.87"),), taxpayer=REGISTERED_K)

        assert above[0] == "high"
        assert "NEAR_TOP_CAP" not in below[1]


class TestExclusionRisk:
    def test_accumulated_income_above_the_top_cap(self) -> None:
        level, reasons = assess((invoice(OLD, "126610838.76"),), taxpayer=REGISTERED_K)

        assert level == "exclusion"
        assert "INCOME_ABOVE_TOP_CAP" in reasons

    def test_exactly_the_top_cap_is_not_exclusion(self) -> None:
        level, _ = assess((invoice(OLD, "126610838.75"),), taxpayer=REGISTERED_K)

        assert level == "high"  # at the cap, so still within the regime but near it

    def test_an_item_priced_above_the_maximum_is_exclusion_on_its_own(self) -> None:
        """A single over-priced good is a cause of exclusion regardless of income."""
        over_priced = Issue(
            code="UNIT_PRICE_ABOVE_MAX", severity="error", message="m", invoice_number="x"
        )

        level, reasons = assess(recent("100000"), taxpayer=REGISTERED_A, issues=(over_priced,))

        assert level == "exclusion"
        assert "UNIT_PRICE_ABOVE_MAX" in reasons


class TestLevelPrecedence:
    def test_the_highest_applicable_level_wins(self) -> None:
        """Income above the top cap also satisfies the medium conditions."""
        level, reasons = assess((invoice(OLD, "126610838.76"),), taxpayer=REGISTERED_A)

        assert level == "exclusion"
        assert len(reasons) > 1

    @pytest.mark.parametrize(
        ("level", "derives"),
        [("low", False), ("medium", True), ("high", True), ("exclusion", True)],
    )
    def test_every_level_except_low_is_routed_to_an_accountant(
        self, level: str, derives: bool
    ) -> None:
        """The contract chosen by the human: "risk or doubtful data" goes to a person."""
        assert (level in POLICY.review_levels) is derives


class TestAnalysisPayload:
    def test_reports_both_categories_so_the_report_can_compare_them(self) -> None:
        result = analyze(
            (invoice(OLD, "14400000"),),
            issues=(),
            taxpayer=REGISTERED_A,
            today=TODAY,
            scales=SCALES,
            policy=POLICY,
        )

        assert result.registered_category == "A"
        assert result.computed_category == "B"
        assert result.accumulated_12m == Decimal("14400000")

    def test_income_above_the_top_cap_has_no_computed_category(self) -> None:
        result = analyze(
            (invoice(OLD, "126610838.76"),),
            issues=(),
            taxpayer=REGISTERED_K,
            today=TODAY,
            scales=SCALES,
            policy=POLICY,
        )

        assert result.computed_category is None
