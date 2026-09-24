"""The report: the only thing the taxpayer actually reads.

Written in Spanish because monotributo is an Argentine regime and this is read
in Argentina, while the code and the README stay in English. The report must
also be honest about its own limits: the estimated category comes from income
alone, and several causes of exclusion are never evaluated.
"""

from datetime import date
from decimal import Decimal

from copiloto.analysis import Analysis
from copiloto.models import HumanDecision, Issue, TaxpayerProfile
from copiloto.report import (
    DISCLAIMER_ES,
    NOT_EVALUATED,
    SCOPE_NOTE_ES,
    render_report,
)
from copiloto.scales import load_scales

SCALES = load_scales()
TAXPAYER = TaxpayerProfile(cuit="20-11111111-2", name="Synthetic Taxpayer One", category="A")

CALM = Analysis(
    accumulated_12m=Decimal("9600000"),
    projected_12m=Decimal("9733333.33"),
    computed_category="A",
    registered_category="A",
    risk_level="low",
    reasons=(),
    headroom_registered=Decimal("2409410.45"),
    headroom_top=Decimal("117010838.75"),
    months_to_registered_cap=Decimal("3.0"),
    months_to_top_cap=Decimal("144.3"),
)

RISKY = Analysis(
    accumulated_12m=Decimal("14400000"),
    projected_12m=Decimal("14600000.00"),
    computed_category="B",
    registered_category="A",
    risk_level="medium",
    reasons=("CATEGORY_MISMATCH",),
    headroom_registered=Decimal("-2390589.55"),
    headroom_top=Decimal("112210838.75"),
    months_to_registered_cap=Decimal("0"),
    months_to_top_cap=Decimal("92.2"),
)


def section(body: str, heading: str) -> str:
    """The text between `heading` and the next heading."""
    _, _, rest = body.partition(heading)
    text, _, _ = rest.partition("\n## ")
    return text


def report(analysis=CALM, issues=(), decision=None, invoice_count=12) -> str:
    return render_report(
        analysis,
        issues=issues,
        taxpayer=TAXPAYER,
        scales=SCALES,
        human_decision=decision,
        invoice_count=invoice_count,
    )


class TestDisclaimers:
    def test_the_report_always_carries_the_disclaimer(self) -> None:
        assert DISCLAIMER_ES in report()

    def test_the_spanish_disclaimer_keeps_the_three_clauses(self) -> None:
        text = DISCLAIMER_ES.lower()

        assert "orientativo" in text
        assert "no reemplaza a un contador" in text
        assert "nunca presenta trámites" in text

    def test_the_report_never_claims_to_file_or_recategorize(self) -> None:
        body = report(analysis=RISKY).lower()

        assert "presentamos" not in body
        assert "te recategorizamos" not in body


class TestLanguage:
    def test_the_report_opens_with_the_argentina_scope_note(self) -> None:
        assert report().startswith(SCOPE_NOTE_ES)

    def test_the_report_is_written_in_spanish(self) -> None:
        body = report(analysis=RISKY)

        for heading in ("Ingresos", "Proyección", "Riesgo", "Revisión", "No evaluado"):
            assert heading in body


class TestFigures:
    def test_shows_the_accumulated_and_projected_income(self) -> None:
        body = report()

        assert "9600000" in body.replace(".", "").replace(",", "")
        assert "9733333" in body.replace(".", "").replace(",", "")

    def test_states_which_scales_it_used_and_since_when(self) -> None:
        body = report()

        assert "2026-08-01" in body
        assert SCALES.source in body

    def test_distinguishes_the_registered_from_the_estimated_category(self) -> None:
        """A 'B' on screen must never be mistaken for what ARCA has on file."""
        body = report(analysis=RISKY)

        assert "Categoría registrada" in body
        assert "Categoría estimada" in body
        assert "solo por ingresos" in body


class TestHeadroom:
    """The one section that answers "and now what?"."""

    def test_says_how_much_can_still_be_invoiced_in_the_registered_category(self) -> None:
        body = report()

        assert "## Margen" in body
        assert "2.409.410,45" in body

    def test_says_how_much_is_left_before_leaving_the_regime(self) -> None:
        body = report()

        assert "117.010.838,75" in body

    def test_estimates_the_months_left_at_the_recent_pace(self) -> None:
        body = report()

        assert "3,0 meses" in body

    def test_says_by_how_much_a_passed_cap_was_passed(self) -> None:
        """A negative margin is not printed as a negative number: it is explained."""
        body = report(analysis=RISKY)

        assert "superaste" in body.lower()
        assert "2.390.589,55" in body
        assert "-2.390.589,55" not in body

    def test_does_not_estimate_months_without_a_pace(self) -> None:
        still = Analysis(
            accumulated_12m=Decimal("9600000"),
            projected_12m=Decimal("0"),
            computed_category="A",
            registered_category="A",
            risk_level="low",
            reasons=(),
            headroom_registered=Decimal("2409410.45"),
            headroom_top=Decimal("117010838.75"),
            months_to_registered_cap=None,
            months_to_top_cap=None,
        )

        margin = section(report(analysis=still), "## Margen")

        assert "meses" not in margin
        assert "sin facturación reciente" in margin.lower()

    def test_skips_the_registered_margin_when_there_is_no_registered_category(self) -> None:
        unknown = Analysis(
            accumulated_12m=Decimal("9600000"),
            projected_12m=Decimal("9733333.33"),
            computed_category="A",
            registered_category=None,
            risk_level="low",
            reasons=(),
            headroom_registered=None,
            headroom_top=Decimal("117010838.75"),
            months_to_registered_cap=None,
            months_to_top_cap=Decimal("144.3"),
        )

        body = render_report(
            unknown, issues=(), taxpayer=None, scales=SCALES, invoice_count=12
        )

        assert "categoría registrada" not in section(body, "## Margen").lower()
        assert "117.010.838,75" in body


class TestLimits:
    def test_lists_everything_it_does_not_evaluate(self) -> None:
        body = report()

        assert all(cause in body for cause in NOT_EVALUATED)

    def test_says_that_low_risk_is_not_a_full_check(self) -> None:
        body = report()

        assert "no es una verificación integral" in body


class TestIssues:
    def test_lists_the_issues_it_was_given(self) -> None:
        issue = Issue(
            code="INVALID_CUIT",
            severity="warning",
            message="El CUIT no supera el dígito verificador.",
            invoice_number="0001-00000001",
        )

        body = report(issues=(issue,))

        assert "INVALID_CUIT" in body
        assert "0001-00000001" in body

    def test_says_so_when_there_were_no_invoices(self) -> None:
        """Zero invoices is missing data, never a clean bill of health."""
        body = report(invoice_count=0)

        assert "No se recibió ninguna factura" in body


class TestReviewAttribution:
    def test_shows_the_accountant_decision(self) -> None:
        decision = HumanDecision(
            verdict="confirmed", notes="Revisé los comprobantes.", reviewer="accountant"
        )

        body = report(analysis=RISKY, decision=decision)

        assert "Revisé los comprobantes." in body
        assert "contador" in body.lower()

    def test_the_verdict_is_translated_not_leaked_in_english(self) -> None:
        """`confirmed` is an internal value; the taxpayer reads Spanish."""
        decision = HumanDecision(verdict="confirmed", notes="", reviewer="accountant")

        body = report(analysis=RISKY, decision=decision)

        assert "confirmado" in body
        assert "confirmed" not in body

    def test_a_dismissed_verdict_is_translated_too(self) -> None:
        decision = HumanDecision(verdict="dismissed", notes="", reviewer="accountant")

        body = report(analysis=RISKY, decision=decision)

        assert "descartado" in body
        assert "dismissed" not in body

    def test_an_automatic_resume_is_never_presented_as_a_review(self) -> None:
        decision = HumanDecision(verdict="confirmed", notes="demo", reviewer="auto")

        body = report(analysis=RISKY, decision=decision)

        assert "Ningún contador revisó este caso" in body

    def test_without_a_decision_the_review_section_says_so(self) -> None:
        body = report(analysis=RISKY)

        assert "Sin revisión" in body


class TestDeterminism:
    def test_the_same_input_always_renders_the_same_report(self) -> None:
        assert report() == report()

    def test_does_not_read_the_clock(self) -> None:
        """No `date.today()` anywhere: the report states dates it was given."""
        assert date.today().isoformat() not in report() or "2026-08-01" in report()
