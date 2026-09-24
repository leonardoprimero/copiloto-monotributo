"""Physical parameters: surface, energy and rent, as declared by the taxpayer.

ARCA places a monotributista in the category of their highest parameter, and
exceeding the top category's cap on any of them is a cause of exclusion. The
income caps come from invoices; the other three come from the taxpayer, who
declares them and is told so in the report.

Every parameter is optional. A service provider without premises has no
surface and no energy to declare, and an undeclared parameter is reported as
not evaluated rather than assumed to be zero.
"""

from datetime import date
from decimal import Decimal

import pytest

from copiloto.analysis import RiskPolicy, analyze
from copiloto.categories import (
    category_for_energy,
    category_for_parameters,
    category_for_rent,
    category_for_surface,
)
from copiloto.models import DeclaredParameters, ExtractedInvoice, InvoiceItem, TaxpayerProfile
from copiloto.scales import load_scales

TODAY = date(2026, 9, 24)
SCALES = load_scales()
POLICY = RiskPolicy()

REGISTERED_A = TaxpayerProfile(cuit="20-11111111-2", name="Synthetic One", category="A")
REGISTERED_G = TaxpayerProfile(cuit="30-44444444-0", name="Synthetic Four", category="G")

RECENT = [date(2026, 7, 15), date(2026, 8, 15), date(2026, 9, 15)]


def invoice(issue_date: date, total: str, number: str) -> ExtractedInvoice:
    amount = Decimal(total)
    item = InvoiceItem(
        description="Item", quantity=Decimal("1"), unit_price=amount, total=amount, kind="service"
    )
    return ExtractedInvoice(
        number=number, issuer_cuit="20-11111111-2", issue_date=issue_date, items=(item,), total=amount
    )


def recent(amount: str) -> tuple[ExtractedInvoice, ...]:
    return tuple(invoice(d, amount, f"0001-{i:08d}") for i, d in enumerate(RECENT))


def analysis(
    invoices,
    *,
    declared: DeclaredParameters | None,
    taxpayer: TaxpayerProfile | None = REGISTERED_A,
):
    return analyze(
        invoices,
        issues=(),
        taxpayer=taxpayer,
        today=TODAY,
        scales=SCALES,
        policy=POLICY,
        declared=declared,
    )


def name(category) -> str | None:
    return category.name if category else None


class TestCategoryBySurface:
    @pytest.mark.parametrize(
        ("m2", "expected"),
        [(0, "A"), (30, "A"), (31, "B"), (45, "B"), (110, "E"), (150, "F"), (200, "G")],
    )
    def test_caps_are_inclusive(self, m2: int, expected: str) -> None:
        assert name(category_for_surface(m2, SCALES)) == expected

    def test_above_the_top_cap_has_no_category(self) -> None:
        """201 m2 exceeds every category: exclusion by surface."""
        assert category_for_surface(201, SCALES) is None

    def test_negative_surface_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            category_for_surface(-1, SCALES)


class TestCategoryByEnergy:
    @pytest.mark.parametrize(
        ("kwh", "expected"),
        [(0, "A"), (3330, "A"), (3331, "B"), (10000, "D"), (20000, "G")],
    )
    def test_caps_are_inclusive(self, kwh: int, expected: str) -> None:
        assert name(category_for_energy(kwh, SCALES)) == expected

    def test_above_the_top_cap_has_no_category(self) -> None:
        assert category_for_energy(20001, SCALES) is None


class TestCategoryByRent:
    @pytest.mark.parametrize(
        ("rent", "expected"),
        [
            ("0", "A"),
            ("2792886.15", "A"),
            # A and B share a cap, so one cent over it lands in C.
            ("2792886.16", "C"),
            ("3816944.41", "C"),
            ("8378658.45", "H"),
        ],
    )
    def test_caps_are_inclusive_to_the_cent(self, rent: str, expected: str) -> None:
        assert name(category_for_rent(Decimal(rent), SCALES)) == expected

    def test_above_the_top_cap_has_no_category(self) -> None:
        assert category_for_rent(Decimal("8378658.46"), SCALES) is None


class TestHighestParameterWins:
    def test_income_alone_when_nothing_is_declared(self) -> None:
        category, binding = category_for_parameters(
            Decimal("3000000"), declared=None, scales=SCALES
        )

        assert name(category) == "A"
        assert binding == "income"

    def test_the_highest_parameter_sets_the_category(self) -> None:
        """Income says A, surface says E: the taxpayer is E."""
        category, binding = category_for_parameters(
            Decimal("3000000"),
            declared=DeclaredParameters(surface_m2=100),
            scales=SCALES,
        )

        assert name(category) == "E"
        assert binding == "surface"

    def test_income_stays_binding_when_it_is_the_highest(self) -> None:
        category, binding = category_for_parameters(
            Decimal("20000000"),
            declared=DeclaredParameters(surface_m2=20, annual_energy_kwh=1000),
            scales=SCALES,
        )

        assert name(category) == "C"
        assert binding == "income"

    def test_a_parameter_over_the_top_cap_means_no_category(self) -> None:
        category, binding = category_for_parameters(
            Decimal("3000000"),
            declared=DeclaredParameters(annual_energy_kwh=20001),
            scales=SCALES,
        )

        assert category is None
        assert binding == "energy"

    def test_undeclared_parameters_are_not_treated_as_zero(self) -> None:
        """Declaring nothing must be indistinguishable from passing None."""
        empty = DeclaredParameters()

        assert category_for_parameters(Decimal("3000000"), declared=empty, scales=SCALES) == (
            category_for_parameters(Decimal("3000000"), declared=None, scales=SCALES)
        )


class TestAnalysisWithDeclaredParameters:
    def test_records_which_parameters_were_evaluated(self) -> None:
        result = analysis(
            recent("1000000"), declared=DeclaredParameters(surface_m2=20, annual_rent=Decimal("1"))
        )

        assert result.evaluated_parameters == ("income", "surface", "rent")
        assert result.binding_parameter == "income"

    def test_income_only_when_nothing_is_declared(self) -> None:
        result = analysis(recent("1000000"), declared=None)

        assert result.evaluated_parameters == ("income",)
        assert result.computed_category == "A"

    def test_a_declared_parameter_can_raise_the_category(self) -> None:
        result = analysis(recent("1000000"), declared=DeclaredParameters(surface_m2=100))

        assert result.computed_category == "E"
        assert result.binding_parameter == "surface"

    def test_surface_over_the_registered_cap_is_medium_and_says_which_parameter(self) -> None:
        """Category A allows 30 m2; declaring 31 breaks the registered category."""
        result = analysis(recent("1000000"), declared=DeclaredParameters(surface_m2=31))

        assert result.risk_level == "medium"
        assert "SURFACE_ABOVE_REGISTERED_CAP" in result.reasons
        assert "CATEGORY_MISMATCH" in result.reasons

    def test_energy_over_the_registered_cap_is_medium(self) -> None:
        result = analysis(recent("1000000"), declared=DeclaredParameters(annual_energy_kwh=3331))

        assert result.risk_level == "medium"
        assert "ENERGY_ABOVE_REGISTERED_CAP" in result.reasons

    def test_rent_over_the_registered_cap_is_medium(self) -> None:
        result = analysis(
            recent("1000000"), declared=DeclaredParameters(annual_rent=Decimal("2792886.16"))
        )

        assert result.risk_level == "medium"
        assert "RENT_ABOVE_REGISTERED_CAP" in result.reasons

    def test_a_parameter_inside_the_registered_cap_adds_no_reason(self) -> None:
        """Sitting exactly on every A cap is still A: caps are inclusive."""
        result = analysis(
            recent("900000"),
            declared=DeclaredParameters(
                surface_m2=30, annual_energy_kwh=3330, annual_rent=Decimal("2792886.15")
            ),
        )

        assert result.risk_level == "low"
        assert result.reasons == ()

    @pytest.mark.parametrize(
        ("declared", "reason"),
        [
            (DeclaredParameters(surface_m2=201), "SURFACE_ABOVE_TOP_CAP"),
            (DeclaredParameters(annual_energy_kwh=20001), "ENERGY_ABOVE_TOP_CAP"),
            (DeclaredParameters(annual_rent=Decimal("8378658.46")), "RENT_ABOVE_TOP_CAP"),
        ],
    )
    def test_exceeding_the_top_cap_on_any_parameter_is_exclusion(
        self, declared: DeclaredParameters, reason: str
    ) -> None:
        result = analysis(recent("1000000"), declared=declared, taxpayer=REGISTERED_G)

        assert result.risk_level == "exclusion"
        assert reason in result.reasons
        assert result.computed_category is None

    def test_registered_comparisons_are_skipped_for_an_unknown_taxpayer(self) -> None:
        result = analysis(recent("1000000"), declared=DeclaredParameters(surface_m2=100), taxpayer=None)

        assert result.risk_level == "low"
        assert result.computed_category == "E"
