"""Map each parameter to a monotributo category, and pick the highest.

This is the first piece of real tax logic, and it is deliberately plain code:
the model never decides a category, it only reads invoices.

ARCA categorizes by the highest parameter: gross income, surface, electric
energy and rent each map to a category on their own, and the taxpayer belongs
to the highest of them. Exceeding the top category on any parameter leaves no
category at all, which the risk rules read as exclusion.
"""

from decimal import Decimal

from copiloto.models import DeclaredParameters, ParameterName
from copiloto.scales import Category, Scales


def _lowest_category_covering(value: Decimal | int, *, cap_of, scales: Scales) -> Category | None:
    """The lowest category whose cap is at least `value`; None above the top.

    Caps are inclusive: the published wording is "hasta X", so a value equal to
    a cap still belongs to that category.
    """
    if value < 0:
        raise ValueError(f"A parameter cannot be negative: {value}")

    for category in scales.categories:
        if value <= cap_of(category):
            return category
    return None


def category_for_income(income: Decimal, scales: Scales) -> Category | None:
    """Return the lowest category whose income cap covers `income`.

    Income above the highest cap returns None, which the risk rules read as
    exclusion by income rather than as a category of its own.
    """
    return _lowest_category_covering(income, cap_of=lambda c: c.income_cap, scales=scales)


def category_for_surface(surface_m2: int, scales: Scales) -> Category | None:
    """The lowest category whose surface cap covers `surface_m2`."""
    return _lowest_category_covering(
        surface_m2, cap_of=lambda c: c.surface_cap_m2, scales=scales
    )


def category_for_energy(annual_kwh: int, scales: Scales) -> Category | None:
    """The lowest category whose annual energy cap covers `annual_kwh`."""
    return _lowest_category_covering(
        annual_kwh, cap_of=lambda c: c.annual_energy_cap_kwh, scales=scales
    )


def category_for_rent(annual_rent: Decimal, scales: Scales) -> Category | None:
    """The lowest category whose annual rent cap covers `annual_rent`."""
    return _lowest_category_covering(
        annual_rent, cap_of=lambda c: c.annual_rent_cap, scales=scales
    )


def categories_by_parameter(
    income: Decimal, *, declared: DeclaredParameters | None, scales: Scales
) -> dict[ParameterName, Category | None]:
    """Resolve every evaluated parameter to its own category.

    Income is always present. The others appear only when declared: an absent
    parameter is not evaluated, which is different from evaluating it as zero.
    """
    resolved: dict[ParameterName, Category | None] = {
        "income": category_for_income(income, scales)
    }
    if declared is None:
        return resolved
    if declared.surface_m2 is not None:
        resolved["surface"] = category_for_surface(declared.surface_m2, scales)
    if declared.annual_energy_kwh is not None:
        resolved["energy"] = category_for_energy(declared.annual_energy_kwh, scales)
    if declared.annual_rent is not None:
        resolved["rent"] = category_for_rent(declared.annual_rent, scales)
    return resolved


def category_for_parameters(
    income: Decimal, *, declared: DeclaredParameters | None, scales: Scales
) -> tuple[Category | None, ParameterName]:
    """The category the taxpayer belongs to, and the parameter that set it.

    The highest parameter wins. A parameter with no category (over the top
    cap) beats every other, and the first such parameter is reported as the
    binding one so the report can say which limit was exceeded.
    """
    resolved = categories_by_parameter(income, declared=declared, scales=scales)
    order = [c.name for c in scales.categories]

    binding: ParameterName = "income"
    highest: Category | None = resolved["income"]
    for parameter, category in resolved.items():
        if highest is None:
            break
        if category is None or order.index(category.name) > order.index(highest.name):
            highest, binding = category, parameter
    return highest, binding
