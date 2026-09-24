"""Scoring the graph against the synthetic cases.

Two measurements, kept apart on purpose. Decision accuracy asks whether the
copilot reached the right conclusion; extraction accuracy asks whether it read
the document correctly. A model can misread a date and still land on the right
category, and a single number is not allowed to hide that.
"""

from datetime import date
from decimal import Decimal

import pytest

from copiloto.evals.dataset import build_cases
from copiloto.evals.runner import run_all, run_case
from copiloto.evals.schema import EvalCase
from copiloto.extractors.fake import FakeExtractor
from copiloto.models import ExtractedInvoice

CASES = build_cases()
BY_ID = {c.id: c for c in CASES}


def fake_factory(case: EvalCase):
    """The extractor the offline suite uses: text in, ground truth out."""
    return FakeExtractor(
        dict(
            zip(
                case.invoice_texts,
                [ExtractedInvoice.model_validate(i) for i in case.invoices],
                strict=True,
            )
        )
    )


def misreading_dates(case: EvalCase):
    """An extractor that shifts every issue date by one day.

    The shift is small enough that no invoice leaves the window, so every
    decision stays correct while every date is wrong.
    """
    invoices = [ExtractedInvoice.model_validate(i) for i in case.invoices]
    shifted = [
        i.model_copy(update={"issue_date": i.issue_date + (date(2026, 9, 2) - date(2026, 9, 1))})
        for i in invoices
    ]
    return FakeExtractor(dict(zip(case.invoice_texts, shifted, strict=True)))


class TestDecisionAccuracy:
    @pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
    def test_every_case_is_answered_correctly(self, case: EvalCase) -> None:
        """The offline suite must be perfect: it is deterministic."""
        result = run_case(case, fake_factory)

        assert result.decision_correct, result.explain()

    def test_the_report_scores_the_whole_dataset(self) -> None:
        report = run_all(CASES, fake_factory)

        assert report.decision_accuracy == 1.0
        assert report.total == 14

    def test_a_wrong_expectation_is_detected(self) -> None:
        """Proves the runner can fail, not just pass."""
        broken = BY_ID["all_in_order"].model_copy(
            update={
                "expected": BY_ID["all_in_order"].expected.model_copy(
                    update={"risk_level": "exclusion"}
                )
            }
        )

        assert not run_case(broken, fake_factory).decision_correct

    def test_the_explanation_names_what_differed(self) -> None:
        broken = BY_ID["all_in_order"].model_copy(
            update={
                "expected": BY_ID["all_in_order"].expected.model_copy(
                    update={"route": "review"}
                )
            }
        )

        assert "route" in run_case(broken, fake_factory).explain()


class TestExtractionAccuracy:
    @pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
    def test_reading_the_ground_truth_scores_perfectly(self, case: EvalCase) -> None:
        result = run_case(case, fake_factory)

        assert all(score == 1.0 for score in result.field_accuracy.values())

    def test_a_misread_date_counts_as_an_error_even_when_the_decision_holds(self) -> None:
        """The measurement the critique asked for.

        Every date is off by a day, yet route, risk, category and issues are
        unchanged. Decision accuracy alone would call this a perfect run.
        """
        result = run_case(BY_ID["all_in_order"], misreading_dates)

        assert result.decision_correct
        assert result.field_accuracy["issue_date"] == 0.0
        assert result.field_accuracy["issuer_cuit"] == 1.0
        assert result.field_accuracy["total"] == 1.0

    def test_the_overall_report_surfaces_the_misreading(self) -> None:
        report = run_all([BY_ID["all_in_order"]], misreading_dates)

        assert report.decision_accuracy == 1.0
        assert report.extraction_accuracy < 1.0

    def test_a_case_without_invoices_does_not_distort_the_average(self) -> None:
        """Nothing was read, so nothing is scored: no free perfect marks."""
        result = run_case(BY_ID["empty_input"], fake_factory)

        assert result.fields_compared == 0


class TestHumanInTheLoop:
    def test_a_paused_case_is_resumed_automatically(self) -> None:
        result = run_case(BY_ID["category_change"], fake_factory)

        assert result.route == "review"
        assert result.report != ""

    def test_the_automatic_resume_is_labelled_in_the_report(self) -> None:
        """The runner is not an accountant and the report must not pretend."""
        result = run_case(BY_ID["category_change"], fake_factory)

        assert "Ningún contador revisó este caso" in result.report

    def test_an_unpaused_case_still_produces_a_report(self) -> None:
        result = run_case(BY_ID["all_in_order"], fake_factory)

        assert result.route == "ok"
        assert "# Informe de monotributo" in result.report


class TestReport:
    def test_lists_every_case_with_its_outcome(self) -> None:
        report = run_all(CASES, fake_factory)

        assert {r.case_id for r in report.results} == {c.id for c in CASES}

    def test_renders_a_readable_table(self) -> None:
        rendered = run_all(CASES, fake_factory).render()

        assert "all_in_order" in rendered
        assert "decision accuracy" in rendered.lower()
        assert "extraction accuracy" in rendered.lower()

    def test_an_empty_dataset_scores_zero_not_one(self) -> None:
        """Vacuously perfect is the wrong answer for "nothing was measured"."""
        report = run_all([], fake_factory)

        assert report.decision_accuracy == 0.0
        assert report.total == 0


class TestDeterminism:
    def test_two_runs_agree(self) -> None:
        first = run_all(CASES, fake_factory)
        second = run_all(CASES, fake_factory)

        assert first.decision_accuracy == second.decision_accuracy
        assert [r.case_id for r in first.results] == [r.case_id for r in second.results]

    def test_the_accumulated_figures_are_decimals(self) -> None:
        result = run_case(BY_ID["all_in_order"], fake_factory)

        assert result.analysis is not None
        assert isinstance(result.analysis.accumulated_12m, Decimal)
