"""The eval dataset itself.

These do not run the graph: they check that the committed cases are
well formed, synthetic, and that their hand-written expectations are
internally coherent. Scoring the graph against them is the runner's job.
"""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from copiloto.cuit import is_valid_cuit
from copiloto.evals.dataset import build_cases
from copiloto.evals.schema import EvalCase
from copiloto.scales import load_scales

CASES_DIR = Path(__file__).resolve().parents[2] / "evals" / "cases"
EXPECTED_IDS = {
    "all_in_order",
    "near_cap",
    "category_change",
    "boundary_exact_cap",
    "date_outside_window",
    "invalid_cuit",
    "date_in_future",
    "total_mismatch",
    "unit_price_above_max",
    "unit_price_kind_unknown",
    "exclusion_by_income",
    "projected_exclusion",
    "unknown_taxpayer",
    "empty_input",
}


def load_cases() -> list[EvalCase]:
    return [
        EvalCase.model_validate_json(p.read_text(encoding="utf-8"))
        for p in sorted(CASES_DIR.glob("*.json"))
    ]


CASES = load_cases()


class TestDataset:
    def test_every_file_validates_against_the_schema(self) -> None:
        assert len(CASES) == len(EXPECTED_IDS)

    def test_the_required_scenarios_are_all_covered(self) -> None:
        assert {c.id for c in CASES} == EXPECTED_IDS

    def test_the_file_name_matches_the_case_id(self) -> None:
        for path in sorted(CASES_DIR.glob("*.json")):
            case = EvalCase.model_validate_json(path.read_text(encoding="utf-8"))
            assert path.stem == case.id

    @pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
    def test_ground_truth_and_rendered_text_line_up(self, case: EvalCase) -> None:
        assert len(case.invoices) == len(case.invoice_texts)

    @pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
    def test_every_case_is_frozen_to_the_same_day(self, case: EvalCase) -> None:
        """A moving clock would make yesterday's expectations wrong today."""
        assert case.today == "2026-09-24"


class TestSyntheticData:
    @pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
    def test_the_registry_entry_agrees_with_the_taxpayer(self, case: EvalCase) -> None:
        if case.registry_entry is not None:
            assert case.registry_entry.cuit == case.taxpayer_cuit
            assert "Synthetic" in case.registry_entry.name

    def test_only_the_invalid_cuit_case_contains_a_bad_cuit(self) -> None:
        for case in CASES:
            bad = [i for i in case.invoices if not is_valid_cuit(i["issuer_cuit"])]
            assert bool(bad) == (case.id == "invalid_cuit"), case.id

    def test_every_cuit_follows_the_obviously_fake_pattern(self) -> None:
        """Repeated digits make it clear at a glance that nobody owns these."""
        for case in CASES:
            for invoice in case.invoices:
                body = invoice["issuer_cuit"].split("-")[1]
                assert len(set(body)) == 1, invoice["issuer_cuit"]


class TestExpectationsAreCoherent:
    @pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
    def test_every_expectation_records_its_arithmetic(self, case: EvalCase) -> None:
        """A case you cannot argue with is a case you cannot debug."""
        assert len(case.expected.rationale) > 60

    @pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
    def test_the_route_is_never_ok_when_something_is_wrong(self, case: EvalCase) -> None:
        escalating = set(case.expected.issue_codes) - {"OUTSIDE_WINDOW"}
        if escalating or case.expected.risk_level != "low":
            assert case.expected.route == "review", case.id

    @pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
    def test_a_computed_category_is_a_real_category(self, case: EvalCase) -> None:
        names = {c.name for c in load_scales().categories}

        assert case.expected.computed_category in names | {None}

    def test_the_empty_case_really_is_empty(self) -> None:
        empty = next(c for c in CASES if c.id == "empty_input")

        assert empty.invoices == ()
        assert empty.expected.route == "review"

    def test_the_exclusion_case_really_exceeds_the_top_cap(self) -> None:
        case = next(c for c in CASES if c.id == "exclusion_by_income")
        total = sum(Decimal(i["total"]) for i in case.invoices)

        assert total > load_scales().top_category.income_cap
        assert case.expected.computed_category is None

    def test_the_boundary_case_totals_the_cap_to_the_cent(self) -> None:
        case = next(c for c in CASES if c.id == "boundary_exact_cap")
        total = sum(Decimal(i["total"]) for i in case.invoices)

        assert total == Decimal("12009410.45")


class TestRenderedText:
    @pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
    def test_the_text_carries_what_an_extractor_must_read(self, case: EvalCase) -> None:
        for invoice, text in zip(case.invoices, case.invoice_texts, strict=True):
            assert invoice["number"].split("-")[1] in text
            assert invoice["issuer_cuit"] in text

    def test_the_text_does_not_print_a_line_total(self) -> None:
        """Real invoices rarely do, which is why the schema derives it."""
        case = next(c for c in CASES if c.id == "all_in_order")

        assert case.invoice_texts[0].count("TOTAL") == 1


class TestReproducibility:
    def test_regenerating_produces_identical_files(self) -> None:
        """The dataset is generated, so it must not drift between runs."""
        rebuilt = {c.id: json.loads(c.model_dump_json()) for c in build_cases()}
        committed = {c.id: json.loads(c.model_dump_json()) for c in CASES}

        assert rebuilt == committed
