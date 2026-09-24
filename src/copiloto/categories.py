"""Map an amount of gross income to a monotributo category.

This is the first piece of real tax logic, and it is deliberately plain code:
the model never decides a category, it only reads invoices.
"""

from decimal import Decimal

from copiloto.scales import Category, Scales


def category_for_income(income: Decimal, scales: Scales) -> Category | None:
    """Return the lowest category whose cap covers `income`.

    Caps are inclusive: the published wording is "hasta X", so income equal to
    a cap still belongs to that category. Income above the highest cap returns
    None, which the risk rules read as exclusion by income rather than as a
    category of its own.
    """
    if income < 0:
        raise ValueError(f"Income cannot be negative: {income}")

    for category in scales.categories:
        if income <= category.income_cap:
            return category
    return None
