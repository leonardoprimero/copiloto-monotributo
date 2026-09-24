"""CUIT check-digit validation.

Weights 5-4-3-2-7-6-5-4-3-2 over the first ten digits, then
`dv = 11 - (sum % 11)`, where 11 means 0 and 10 means the number admits no
valid check digit.

This only proves a number is well formed. It says nothing about whether the
CUIT was ever issued, or to whom: the registry lookup is a separate step.
Every CUIT in this repository is synthetic.
"""

import pytest

from copiloto.cuit import is_valid_cuit, normalize_cuit


class TestValidCuits:
    @pytest.mark.parametrize(
        "cuit",
        [
            "20-11111111-2",  # sum 42, remainder 9, dv 2
            "27-22222222-8",  # sum 102, remainder 3, dv 8
            "23-33333333-3",  # sum 118, remainder 8, dv 3
            "30-44444444-0",  # sum 143, remainder 0, dv 11 -> 0
        ],
    )
    def test_accepts_synthetic_cuits_with_a_correct_check_digit(self, cuit: str) -> None:
        assert is_valid_cuit(cuit) is True

    def test_accepts_the_remainder_zero_edge_case(self) -> None:
        """Remainder 0 yields dv 11, which must collapse to 0, not stay 11."""
        assert is_valid_cuit("30-44444444-0") is True

    def test_accepts_an_unformatted_cuit(self) -> None:
        assert is_valid_cuit("20111111112") is True


class TestInvalidCuits:
    def test_rejects_a_wrong_check_digit(self) -> None:
        assert is_valid_cuit("20-11111111-3") is False

    def test_rejects_a_number_whose_remainder_is_one(self) -> None:
        """Remainder 1 yields dv 10: no single digit can satisfy it."""
        assert all(is_valid_cuit(f"20-00000001-{d}") is False for d in range(10))

    @pytest.mark.parametrize(
        "cuit",
        [
            "",
            "20-1111111-2",  # too short
            "20-111111111-2",  # too long
            "20-1111111A-2",  # not digits
            "not a cuit",
        ],
    )
    def test_rejects_malformed_input(self, cuit: str) -> None:
        assert is_valid_cuit(cuit) is False


class TestNormalize:
    def test_strips_separators_and_whitespace(self) -> None:
        assert normalize_cuit(" 20-11111111-2 ") == "20111111112"

    def test_leaves_an_unformatted_cuit_untouched(self) -> None:
        assert normalize_cuit("20111111112") == "20111111112"
