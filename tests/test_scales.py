"""The ARCA scales are configuration, not constants buried in the logic.

They change every semester, so the loader must expose where the numbers came
from and when they took effect, and the report has to be able to say so.
"""

import dataclasses
from decimal import Decimal
from pathlib import Path

import pytest

from copiloto.scales import ScalesError, load_scales


@pytest.fixture(scope="module")
def scales():
    return load_scales()


def test_scales_declare_their_source_and_effective_date(scales) -> None:
    assert scales.effective_from.isoformat() == "2026-08-01"
    assert scales.retrieved_on.isoformat() == "2026-09-24"
    assert scales.source == "https://www.arca.gob.ar/monotributo/categorias.asp"


def test_scales_cover_the_eleven_categories_in_order(scales) -> None:
    assert [c.name for c in scales.categories] == list("ABCDEFGHIJK")


def test_income_caps_match_the_official_table(scales) -> None:
    # Transcribed from the official page, valid from 2026-08-01.
    expected = {
        "A": "12009410.45",
        "B": "17595182.74",
        "C": "24670494.31",
        "D": "30628651.43",
        "E": "36028231.33",
        "F": "45151659.41",
        "G": "53995798.87",
        "H": "81924660.37",
        "I": "91699761.90",
        "J": "105012519.20",
        "K": "126610838.75",
    }

    assert {c.name: str(c.income_cap) for c in scales.categories} == expected


def test_amounts_are_decimals_never_floats(scales) -> None:
    for category in scales.categories:
        assert isinstance(category.income_cap, Decimal)
        assert isinstance(category.annual_rent_cap, Decimal)
    assert isinstance(scales.max_unit_price, Decimal)


def test_max_unit_price_is_shared_by_every_category(scales) -> None:
    assert scales.max_unit_price == Decimal("716840.77")


def test_income_caps_are_strictly_increasing(scales) -> None:
    caps = [c.income_cap for c in scales.categories]

    assert caps == sorted(caps)
    assert len(set(caps)) == len(caps)


def test_highest_category_is_the_exclusion_threshold(scales) -> None:
    assert scales.top_category.name == "K"
    assert scales.top_category.income_cap == Decimal("126610838.75")


def test_income_caps_do_not_depend_on_activity(scales) -> None:
    """Resolves the open domain question, with the official table as evidence.

    The published table splits "locaciones y prestaciones de servicios" from
    "venta de cosas muebles" only in the monthly tax columns. The gross income
    caps are a single column shared by both activities across A-K, so category
    H-K is reachable by a service provider too.
    """
    assert scales.income_caps_depend_on_activity is False


def test_scales_are_immutable(scales) -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        scales.categories[0].income_cap = Decimal("1")


def test_missing_config_fails_with_an_actionable_error(tmp_path: Path) -> None:
    missing = tmp_path / "nope.json"

    with pytest.raises(ScalesError) as error:
        load_scales(missing)

    assert str(missing) in str(error.value)


def test_malformed_config_fails_with_an_actionable_error(tmp_path: Path) -> None:
    broken = tmp_path / "broken.json"
    broken.write_text('{"source": "x"}', encoding="utf-8")

    with pytest.raises(ScalesError):
        load_scales(broken)
