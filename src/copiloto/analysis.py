"""Income analysis: what the last twelve months add up to, and what that implies.

Plain arithmetic over already-extracted invoices. No model participates here,
which is what makes the conclusions auditable and the tests offline.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from copiloto.categories import category_for_income, category_for_parameters
from copiloto.dates import within_window
from copiloto.models import (
    DeclaredParameters,
    ExtractedInvoice,
    Issue,
    ParameterName,
    TaxpayerProfile,
)
from copiloto.scales import Category, Scales

RiskLevel = Literal["low", "medium", "high", "exclusion"]

_ORDER: tuple[RiskLevel, ...] = ("low", "medium", "high", "exclusion")
_CENTS = Decimal("0.01")
_TENTHS = Decimal("0.1")
_MONTHS_PER_YEAR = Decimal(12)


@dataclass(frozen=True, slots=True)
class RiskPolicy:
    """How this application interprets the numbers.

    These thresholds are product decisions, not published rules, which is why
    they live here and not in the ARCA config. `review_levels` encodes the
    chosen contract: anything that is not `low` goes to an accountant.
    """

    near_cap_ratio: Decimal = Decimal("0.9")
    projection_days: int = 90
    review_levels: frozenset[str] = field(
        default_factory=lambda: frozenset({"medium", "high", "exclusion"})
    )


@dataclass(frozen=True, slots=True)
class Analysis:
    """Everything the report and the router need, and nothing they must infer."""

    accumulated_12m: Decimal
    projected_12m: Decimal
    computed_category: str | None
    registered_category: str | None
    risk_level: RiskLevel
    reasons: tuple[str, ...]
    # Headroom: what can still be invoiced before each cap. Negative once the
    # cap is passed, by exactly the amount it was passed by. The registered
    # figures are None when there is no registered category to measure against.
    headroom_registered: Decimal | None
    headroom_top: Decimal
    # Months of the recent pace until each cap, to one decimal. None when there
    # is no pace to extrapolate from or no registered cap; zero once reached.
    months_to_registered_cap: Decimal | None
    months_to_top_cap: Decimal | None
    # Which parameter placed the taxpayer in `computed_category`, and which
    # ones were looked at. Income is the baseline: with nothing declared, the
    # category is by income alone and the report says exactly that.
    binding_parameter: ParameterName = "income"
    evaluated_parameters: tuple[ParameterName, ...] = ("income",)

    def __post_init__(self) -> None:
        # Checkpoint deserialization hands back lists, so an Analysis restored
        # after a pause would not compare equal to the one that was saved.
        # Normalizing here makes the type hold whatever the source was.
        if not isinstance(self.reasons, tuple):
            object.__setattr__(self, "reasons", tuple(self.reasons))
        if not isinstance(self.evaluated_parameters, tuple):
            object.__setattr__(self, "evaluated_parameters", tuple(self.evaluated_parameters))


def invoices_in_window(
    invoices: tuple[ExtractedInvoice, ...], *, today: date
) -> tuple[ExtractedInvoice, ...]:
    """The invoices that fall inside `(today - 1 year, today]`."""
    return tuple(i for i in invoices if within_window(i.issue_date, today=today))


def accumulated_income(
    invoices: tuple[ExtractedInvoice, ...], *, today: date
) -> Decimal:
    """Total invoiced inside the rolling window.

    Invoices carrying issues are still summed. Their issue already sends the
    case to a human, and silently dropping them would understate the income
    rather than surface the problem.
    """
    return sum(
        (invoice.total for invoice in invoices_in_window(invoices, today=today)),
        Decimal("0"),
    )


def computed_category(
    invoices: tuple[ExtractedInvoice, ...], *, today: date, scales: Scales
) -> Category | None:
    """The category implied by the accumulated income.

    Income only. Surface, energy, rent and the number of activities are not
    evaluated by this MVP, and the report says so rather than presenting this
    as a complete assessment.
    """
    return category_for_income(accumulated_income(invoices, today=today), scales)


def projected_income(
    invoices: tuple[ExtractedInvoice, ...], *, today: date, policy: RiskPolicy
) -> Decimal:
    """Annualize the recent invoicing pace.

    Takes the last `projection_days` and scales them to 365. This is the
    application's own heuristic for "if you keep going like this", not a
    criterion published by ARCA, and the report says so.
    """
    start = today - timedelta(days=policy.projection_days)
    recent = sum(
        (i.total for i in invoices if start < i.issue_date <= today), Decimal("0")
    )
    projected = recent * Decimal(365) / Decimal(policy.projection_days)
    return projected.quantize(_CENTS, rounding=ROUND_HALF_UP)


def months_until(headroom: Decimal | None, *, projected_12m: Decimal) -> Decimal | None:
    """How many months of the projected pace it takes to consume `headroom`.

    Zero once the cap is reached, None when there is nothing to measure: no
    cap, or no recent invoicing. "Never" would be a guess, so it is not said.
    """
    if headroom is None or projected_12m <= 0:
        return None
    if headroom <= 0:
        return Decimal("0")
    months = headroom * _MONTHS_PER_YEAR / projected_12m
    return months.quantize(_TENTHS, rounding=ROUND_HALF_UP)


def _registered_category(taxpayer: TaxpayerProfile | None, scales: Scales) -> Category | None:
    if taxpayer is None:
        return None
    for category in scales.categories:
        if category.name == taxpayer.category:
            return category
    return None


def _physical_values(
    declared: DeclaredParameters | None,
) -> list[tuple[str, Decimal | int, Callable[[Category], Decimal | int]]]:
    """The declared physical parameters, each with the cap it is measured against."""
    if declared is None:
        return []
    values: list[tuple[str, Decimal | int, Callable[[Category], Decimal | int]]] = []
    if declared.surface_m2 is not None:
        values.append(("SURFACE", declared.surface_m2, lambda c: c.surface_cap_m2))
    if declared.annual_energy_kwh is not None:
        values.append(("ENERGY", declared.annual_energy_kwh, lambda c: c.annual_energy_cap_kwh))
    if declared.annual_rent is not None:
        values.append(("RENT", declared.annual_rent, lambda c: c.annual_rent_cap))
    return values


def analyze(
    invoices: tuple[ExtractedInvoice, ...],
    *,
    issues: tuple[Issue, ...],
    taxpayer: TaxpayerProfile | None,
    today: date,
    scales: Scales,
    policy: RiskPolicy,
    declared: DeclaredParameters | None = None,
) -> Analysis:
    """Turn invoices, issues and declared parameters into a risk level with reasons.

    When several conditions apply the highest level wins, but every reason is
    kept so the report can explain the verdict instead of asserting it.
    """
    accumulated = accumulated_income(invoices, today=today)
    projected = projected_income(invoices, today=today, policy=policy)
    computed, binding = category_for_parameters(accumulated, declared=declared, scales=scales)
    top = scales.top_category
    top_cap = top.income_cap
    registered = _registered_category(taxpayer, scales)
    registered_cap = registered.income_cap if registered else None
    physical = _physical_values(declared)

    reasons: list[str] = []
    level: RiskLevel = "low"

    def raise_to(candidate: RiskLevel, reason: str) -> None:
        nonlocal level
        reasons.append(reason)
        if _ORDER.index(candidate) > _ORDER.index(level):
            level = candidate

    # Conditions that need a registered category are skipped when the taxpayer
    # is not in the registry: there is simply nothing to compare against.
    if registered is not None and registered_cap is not None and taxpayer is not None:
        if accumulated >= registered_cap * policy.near_cap_ratio:
            raise_to("medium", "NEAR_REGISTERED_CAP")
        if computed is not None and computed.name != taxpayer.category:
            raise_to("medium", "CATEGORY_MISMATCH")
        if projected > registered_cap:
            raise_to("medium", "PROJECTION_ABOVE_REGISTERED_CAP")
        for name, value, cap_of in physical:
            if value > cap_of(registered):
                raise_to("medium", f"{name}_ABOVE_REGISTERED_CAP")

    if accumulated >= top_cap * policy.near_cap_ratio:
        raise_to("high", "NEAR_TOP_CAP")
    if projected > top_cap:
        raise_to("high", "PROJECTION_ABOVE_TOP_CAP")

    if accumulated > top_cap:
        raise_to("exclusion", "INCOME_ABOVE_TOP_CAP")
    if any(issue.code == "UNIT_PRICE_ABOVE_MAX" for issue in issues):
        raise_to("exclusion", "UNIT_PRICE_ABOVE_MAX")
    # A physical parameter over the top category's cap excludes on its own,
    # however modest the income.
    for name, value, cap_of in physical:
        if value > cap_of(top):
            raise_to("exclusion", f"{name}_ABOVE_TOP_CAP")

    headroom_registered = registered_cap - accumulated if registered_cap is not None else None
    headroom_top = top_cap - accumulated

    return Analysis(
        accumulated_12m=accumulated,
        projected_12m=projected,
        computed_category=computed.name if computed else None,
        registered_category=taxpayer.category if taxpayer else None,
        risk_level=level,
        reasons=tuple(reasons),
        headroom_registered=headroom_registered,
        headroom_top=headroom_top,
        months_to_registered_cap=months_until(headroom_registered, projected_12m=projected),
        months_to_top_cap=months_until(headroom_top, projected_12m=projected),
        binding_parameter=binding,
        evaluated_parameters=("income", *(declared.declared() if declared else ())),
    )
