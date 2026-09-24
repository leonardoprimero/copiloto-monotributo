"""CUIT check-digit validation.

Structural validation only: it proves the number is internally consistent, not
that it was ever issued or that it belongs to the person on the invoice.
Confirming identity is what the registry lookup is for.
"""

_WEIGHTS = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
_LENGTH = 11
_SEPARATORS = str.maketrans("", "", "- .")


def normalize_cuit(cuit: str) -> str:
    """Strip the usual separators and surrounding whitespace."""
    return cuit.strip().translate(_SEPARATORS)


def is_valid_cuit(cuit: str) -> bool:
    """Return whether `cuit` carries a correct check digit."""
    digits = normalize_cuit(cuit)
    if len(digits) != _LENGTH or not digits.isdigit():
        return False

    # Only the first ten digits are weighted; the eleventh is the check digit
    # being verified. `strict=True` makes that pairing explicit, so a change to
    # either length fails loudly instead of silently truncating.
    body, expected = digits[:-1], int(digits[-1])
    total = sum(w * int(d) for w, d in zip(_WEIGHTS, body, strict=True))
    check = 11 - (total % 11)
    if check == 11:
        check = 0
    elif check == 10:
        # No single digit satisfies the algorithm, so no valid CUIT exists for
        # these first ten digits.
        return False

    return check == expected
