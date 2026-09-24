"""The shapes that travel through the graph.

These models only describe data. They do not decide anything: whether a CUIT is
valid, whether a total adds up, or which category applies is the job of the
validation and analysis modules.
"""

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from copiloto.models import (
    DeclaredParameters,
    ExtractedInvoice,
    HumanDecision,
    InvoiceItem,
    Issue,
    ItemKind,
    Severity,
    TaxpayerProfile,
    Verdict,
)


def an_item(**overrides) -> InvoiceItem:
    return InvoiceItem(
        **{
            "description": "Consultoria",
            "quantity": Decimal("1"),
            "unit_price": Decimal("100.00"),
            "total": Decimal("100.00"),
            **overrides,
        }
    )


class TestDeclaredParameters:
    def test_everything_is_optional(self) -> None:
        """A service provider without premises has nothing to declare."""
        declared = DeclaredParameters()

        assert declared.surface_m2 is None
        assert declared.annual_energy_kwh is None
        assert declared.annual_rent is None

    def test_rent_is_decimal(self) -> None:
        assert DeclaredParameters(annual_rent="1000.50").annual_rent == Decimal("1000.50")  # pyright: ignore[reportArgumentType]

    @pytest.mark.parametrize(
        "field", ["surface_m2", "annual_energy_kwh", "annual_rent"]
    )
    def test_negative_values_are_rejected(self, field: str) -> None:
        with pytest.raises(ValidationError):
            DeclaredParameters(**{field: -1})  # pyright: ignore[reportArgumentType]

    def test_declared_returns_the_parameters_that_were_given(self) -> None:
        declared = DeclaredParameters(surface_m2=40, annual_rent=Decimal("10"))

        assert declared.declared() == ("surface", "rent")


class TestInvoiceItem:
    def test_unclassified_items_are_unknown_not_service(self) -> None:
        """An item whose kind was not reported must not pass as a service.

        The maximum unit price only applies to "venta de cosas muebles", so
        defaulting to "service" would let an over-priced item slip through
        unchecked. "unknown" keeps the ambiguity visible.
        """
        assert an_item().kind == "unknown"

    @pytest.mark.parametrize("kind", ["service", "good", "unknown"])
    def test_accepts_the_three_known_kinds(self, kind: ItemKind) -> None:
        assert an_item(kind=kind).kind == kind

    def test_rejects_an_unknown_kind(self) -> None:
        with pytest.raises(ValidationError):
            an_item(kind="something-else")  # pyright: ignore[reportArgumentType]

    def test_money_is_parsed_as_decimal_from_strings(self) -> None:
        item = an_item(unit_price="716840.77", total="716840.77")

        assert item.unit_price == Decimal("716840.77")
        assert isinstance(item.unit_price, Decimal)


class TestExtractedInvoice:
    def test_holds_what_the_model_read_without_judging_it(self) -> None:
        """Extraction records an invalid CUIT as-is; validation flags it later."""
        invoice = ExtractedInvoice(
            number="0001-00000001",
            issuer_cuit="20-11111111-3",
            issue_date=date(2026, 9, 15),
            items=(an_item(),),
            total=Decimal("100.00"),
        )

        assert invoice.issuer_cuit == "20-11111111-3"
        assert invoice.issue_date == date(2026, 9, 15)

    def test_is_immutable_once_extracted(self) -> None:
        invoice = ExtractedInvoice(
            number="0001-00000001",
            issuer_cuit="20-11111111-2",
            issue_date=date(2026, 9, 15),
            items=(an_item(),),
            total=Decimal("100.00"),
        )

        with pytest.raises(ValidationError):
            invoice.total = Decimal("1")


class TestIssue:
    @pytest.mark.parametrize("severity", ["info", "warning", "error"])
    def test_accepts_the_three_severities(self, severity: Severity) -> None:
        assert Issue(code="X", severity=severity, message="m").severity == severity

    def test_rejects_an_unknown_severity(self) -> None:
        with pytest.raises(ValidationError):
            Issue(code="X", severity="critical", message="m")  # pyright: ignore[reportArgumentType]

    def test_can_point_at_the_invoice_that_caused_it(self) -> None:
        issue = Issue(
            code="INVALID_CUIT",
            severity="warning",
            message="m",
            invoice_number="0001-00000001",
        )

        assert issue.invoice_number == "0001-00000001"


class TestHumanDecision:
    def test_records_who_decided_not_only_what(self) -> None:
        """An automatic resume must never be reported as an accountant review."""
        auto = HumanDecision(verdict="confirmed", notes="demo", reviewer="auto")
        accountant = HumanDecision(verdict="confirmed", notes="checked")

        assert auto.reviewer == "auto"
        assert accountant.reviewer == "accountant"

    def test_rejects_an_unknown_reviewer(self) -> None:
        with pytest.raises(ValidationError):
            HumanDecision(verdict="confirmed", notes="", reviewer="robot")  # pyright: ignore[reportArgumentType]

    @pytest.mark.parametrize("verdict", ["confirmed", "dismissed"])
    def test_accepts_the_two_verdicts(self, verdict: Verdict) -> None:
        assert HumanDecision(verdict=verdict, notes="").verdict == verdict


class TestTaxpayerProfile:
    def test_carries_the_registered_category(self) -> None:
        profile = TaxpayerProfile(
            cuit="20-11111111-2", name="Synthetic Taxpayer One", category="A"
        )

        assert profile.category == "A"
