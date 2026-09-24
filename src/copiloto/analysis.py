"""Income analysis: what the last twelve months add up to, and what that implies.

Plain arithmetic over already-extracted invoices. No model participates here,
which is what makes the conclusions auditable and the tests offline.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from copiloto.categories import category_for_income
from copiloto.dates import within_window
from copiloto.models import ExtractedInvoice, Issue, TaxpayerProfile
from copiloto.scales import Category, Scales

RiskLevel = Literal["low", "medium", "high", "exclusion"]

_ORDER: tuple[RiskLevel, ...] = ("low", "medium", "high", "exclusion")
_CENTS = Decimal("0.01")


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


def _registered_cap(taxpayer: TaxpayerProfile | None, scales: Scales) -> Decimal | None:
    if taxpayer is None:
        return None
    for category in scales.categories:
        if category.name == taxpayer.category:
            return category.income_cap
    return None


def analyze(
    invoices: tuple[ExtractedInvoice, ...],
    *,
    issues: tuple[Issue, ...],
    taxpayer: TaxpayerProfile | None,
    today: date,
    scales: Scales,
    policy: RiskPolicy,
) -> Analysis:
    """Turn invoices and issues into a risk level with its reasons.

    When several conditions apply the highest level wins, but every reason is
    kept so the report can explain the verdict instead of asserting it.
    """
    accumulated = accumulated_income(invoices, today=today)
    projected = projected_income(invoices, today=today, policy=policy)
    computed = category_for_income(accumulated, scales)
    top_cap = scales.top_category.income_cap
    registered_cap = _registered_cap(taxpayer, scales)

    reasons: list[str] = []
    level: RiskLevel = "low"

    def raise_to(candidate: RiskLevel, reason: str) -> None:
        nonlocal level
        reasons.append(reason)
        if _ORDER.index(candidate) > _ORDER.index(level):
            level = candidate

    # Conditions that need a registered category are skipped when the taxpayer
    # is not in the registry: there is simply nothing to compare against.
    if registered_cap is not None and taxpayer is not None:
        if accumulated >= registered_cap * policy.near_cap_ratio:
            raise_to("medium", "NEAR_REGISTERED_CAP")
        if computed is not None and computed.name != taxpayer.category:
            raise_to("medium", "CATEGORY_MISMATCH")
        if projected > registered_cap:
            raise_to("medium", "PROJECTION_ABOVE_REGISTERED_CAP")

    if accumulated >= top_cap * policy.near_cap_ratio:
        raise_to("high", "NEAR_TOP_CAP")
    if projected > top_cap:
        raise_to("high", "PROJECTION_ABOVE_TOP_CAP")

    if accumulated > top_cap:
        raise_to("exclusion", "INCOME_ABOVE_TOP_CAP")
    if any(issue.code == "UNIT_PRICE_ABOVE_MAX" for issue in issues):
        raise_to("exclusion", "UNIT_PRICE_ABOVE_MAX")

    return Analysis(
        accumulated_12m=accumulated,
        projected_12m=projected,
        computed_category=computed.name if computed else None,
        registered_category=taxpayer.category if taxpayer else None,
        risk_level=level,
        reasons=tuple(reasons),
    )
