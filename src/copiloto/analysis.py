"""Income analysis: what the last twelve months add up to, and what that implies.

Plain arithmetic over already-extracted invoices. No model participates here,
which is what makes the conclusions auditable and the tests offline.
"""

from datetime import date
from decimal import Decimal

from copiloto.categories import category_for_income
from copiloto.dates import within_window
from copiloto.models import ExtractedInvoice
from copiloto.scales import Category, Scales


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
