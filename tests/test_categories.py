"""Mapping an amount of income to a monotributo category.

Pure arithmetic over the loaded scales: no invoices, no graph, no model.
Every boundary is tested to the cent, because the caps are published with
cents and a category change is what the whole report hangs on.
"""

from decimal import Decimal

import pytest

from copiloto.categories import category_for_income
from copiloto.scales import Scales, load_scales


@pytest.fixture(scope="module")
def scales():
    return load_scales()


def category_name(income: str, scales: Scales) -> str:
    """Resolve a category and fail loudly if none matched.

    Tests that expect no category call `category_for_income` directly; this
    helper is for the cases where a missing category is itself a failure.
    """
    category = category_for_income(Decimal(income), scales)
    assert category is not None, f"expected a category for {income}"
    return category.name


def test_zero_income_falls_in_the_lowest_category(scales) -> None:
    assert category_name("0", scales) == "A"


def test_income_inside_a_band_selects_that_category(scales) -> None:
    assert category_name("20000000", scales) == "C"


@pytest.mark.parametrize(
    ("income", "expected"),
    [
        ("12009410.45", "A"),
        ("12009410.46", "B"),
        ("17595182.74", "B"),
        ("17595182.75", "C"),
        ("81924660.37", "H"),
        ("81924660.38", "I"),
        ("126610838.75", "K"),
    ],
)
def test_caps_are_inclusive_to_the_cent(income: str, expected: str, scales) -> None:
    # "Hasta X" means income <= X, so the cap itself still belongs to its
    # category and a single cent above it moves to the next one.
    assert category_name(income, scales) == expected


def test_income_above_the_top_category_has_no_category(scales) -> None:
    # One cent over the category K cap: no category fits, which is what the
    # risk rules read as exclusion by income.
    assert category_for_income(Decimal("126610838.76"), scales) is None


def test_negative_income_is_rejected(scales) -> None:
    with pytest.raises(ValueError):
        category_for_income(Decimal("-1"), scales)


def test_every_category_is_reachable(scales) -> None:
    # Guards against an off-by-one that would make a band unreachable.
    reached = {category_name(str(c.income_cap), scales) for c in scales.categories}

    assert reached == {c.name for c in scales.categories}
