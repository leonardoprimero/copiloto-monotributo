"""The README is the first thing anyone reads, so it is kept under test.

Documentation rots quietly: a diagram keeps its node names while an edge moves,
a disclaimer gets trimmed, a quickstart forgets a step. These checks make that
rot fail the suite instead of shipping.

It is written in Spanish because the people who use this are in Argentina.
"""

from pathlib import Path

import pytest

from copiloto.graph.diagram import DIAGRAM_PATH
from copiloto.report import DISCLAIMER_ES
from copiloto.scales import load_scales

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")
SCALES = load_scales()


def plain(text: str) -> str:
    """Strip markdown emphasis and blockquote markers before comparing."""
    return " ".join(text.replace("**", "").replace(">", "").split())


def mermaid_block() -> str:
    _, _, rest = README.partition("```mermaid")
    block, _, _ = rest.partition("```")
    return block.strip()


class TestDisclaimer:
    def test_the_readme_carries_the_exact_disclaimer(self) -> None:
        """One source of truth, shared with the report the taxpayer reads."""
        assert plain(DISCLAIMER_ES) in plain(README)

    @pytest.mark.parametrize(
        "clause",
        [
            "orientativo",
            "no reemplaza a un contador",
            "nunca presenta trámites",
        ],
    )
    def test_the_three_clauses_survive(self, clause: str) -> None:
        assert clause in README.lower()

    def test_it_appears_before_anything_else(self) -> None:
        """A disclaimer below the fold is a disclaimer nobody reads."""
        assert README.index("Aviso") < README.index("## Qué hace")


class TestDiagram:
    def test_the_published_diagram_is_the_exported_one(self) -> None:
        """Byte for byte: an edge can move while every node name stays."""
        exported = DIAGRAM_PATH.read_text(encoding="utf-8").strip()

        assert mermaid_block() == exported

    def test_the_diagram_shows_both_branches(self) -> None:
        block = mermaid_block()

        assert "request_accountant_review" in block
        assert "write_report" in block


class TestExtractorModes:
    @pytest.mark.parametrize("mode", ["fake", "cli", "api"])
    def test_every_mode_is_documented(self, mode: str) -> None:
        assert f"`{mode}`" in README

    def test_the_selecting_variable_is_named(self) -> None:
        assert "COPILOTO_EXTRACTOR" in README

    def test_the_escape_hatch_is_documented(self) -> None:
        assert "COPILOTO_EXTRACTOR_CMD" in README

    def test_the_optional_extra_is_in_the_quickstart(self) -> None:
        assert "uv sync --extra api" in README

    def test_it_says_the_default_needs_no_key(self) -> None:
        assert "Sin API key" in README


class TestArcaHonesty:
    """The padrón client is the one piece that was never run for real."""

    def test_the_readme_says_it_never_ran_against_arca(self) -> None:
        assert "Nunca se ejecutó contra ARCA" in README

    def test_the_integration_guide_exists_and_is_linked(self) -> None:
        assert "docs/arca-padron.md" in README
        assert (ROOT / "docs" / "arca-padron.md").exists()

    def test_the_guide_names_its_sources(self) -> None:
        """A contract copied from memory is worth nothing; cite the manuals."""
        guide = (ROOT / "docs" / "arca-padron.md").read_text(encoding="utf-8")

        assert "ws_sr_constancia_inscripcion" in guide
        assert "1.2.2" in guide
        assert "3.4" in guide

    def test_the_guide_keeps_the_promise_about_the_clave_fiscal(self) -> None:
        guide = (ROOT / "docs" / "arca-padron.md").read_text(encoding="utf-8")

        assert "nunca pide la clave fiscal" in guide
        assert "Administrador de Relaciones" in guide

    def test_the_guide_says_what_is_not_implemented(self) -> None:
        guide = (ROOT / "docs" / "arca-padron.md").read_text(encoding="utf-8")

        assert "**No implementado**" in guide


class TestOcrAndParallel:
    def test_the_ocr_extra_is_documented(self) -> None:
        assert "uv sync --extra ocr" in README

    def test_it_says_a_scan_is_never_skipped_silently(self) -> None:
        assert "nunca saltea una" in README

    def test_it_says_ocr_sends_the_case_to_a_person(self) -> None:
        """The whole safety argument for OCR rests on this."""
        assert "contador aunque los números den tranquilos" in README

    def test_the_parallel_reading_is_described(self) -> None:
        assert "en paralelo" in README


class TestWebAndHandoff:
    def test_the_web_command_is_in_the_quickstart(self) -> None:
        assert "uv run copiloto serve" in README

    def test_the_handoff_commands_are_documented(self) -> None:
        for command in ("--no-wait", "copiloto cases", "copiloto review"):
            assert command in README

    def test_the_state_variable_is_named(self) -> None:
        assert "COPILOTO_STATE_DB" in README

    def test_the_access_token_is_documented_where_it_is_configured(self) -> None:
        config = (ROOT / "docs" / "configuration.md").read_text(encoding="utf-8")

        assert "COPILOTO_TOKEN" in config
        assert "not an identity system" in config

    def test_the_declared_parameters_are_documented_with_their_flags(self) -> None:
        for flag in ("--surface-m2", "--energy-kwh", "--annual-rent"):
            assert flag in README


class TestScales:
    def test_the_effective_date_matches_the_config(self) -> None:
        assert SCALES.effective_from.isoformat() in README

    def test_the_physical_caps_match_the_config(self) -> None:
        """The physical table is data too, and it rots the same way."""
        for category in SCALES.categories:
            assert f"{category.annual_rent_cap:,.2f}" in README
            assert f"{category.annual_energy_cap_kwh:,}" in README

    def test_the_source_is_cited(self) -> None:
        assert SCALES.source in README

    def test_the_top_cap_matches_the_config(self) -> None:
        """A stale figure in the README is the exact failure this project fears."""
        assert f"{SCALES.top_category.income_cap:,.2f}" in README

    def test_the_maximum_unit_price_matches_the_config(self) -> None:
        assert f"{SCALES.max_unit_price:,.2f}" in README

    def test_the_retrieval_date_is_stated(self) -> None:
        assert SCALES.retrieved_on.isoformat() in README


class TestHonesty:
    def test_it_lists_what_is_not_evaluated(self) -> None:
        assert "Qué NO evalúa" in README

    def test_it_explains_the_language_choice(self) -> None:
        assert "rioplatense" in README.lower()

    def test_it_states_that_all_data_is_synthetic(self) -> None:
        assert "sintéticos" in README

    def test_it_records_what_was_verified_against_the_installed_packages(self) -> None:
        assert "Verificado contra" in README
        assert "1.2.12" in README

    def test_it_says_the_cli_mode_never_falls_back_silently(self) -> None:
        assert "nunca** cae a `fake`" in README or "nunca cae a `fake`" in README


class TestLicense:
    def test_the_license_file_exists_and_is_mit(self) -> None:
        license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")

        assert "MIT License" in license_text

    def test_the_readme_declares_it(self) -> None:
        assert "MIT" in README
