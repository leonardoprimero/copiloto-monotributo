"""Code-side checks over what the model read.

The model extracts; this module judges. Every function here is pure and
deterministic, which is why the whole tax logic can be tested without a model,
a key or a network.
"""

from datetime import date
from decimal import Decimal

from copiloto.cuit import is_valid_cuit, normalize_cuit
from copiloto.dates import one_year_before, within_window
from copiloto.models import ExtractedInvoice, InvoiceItem, Issue
from copiloto.scales import Scales


def _issue(code: str, severity, message: str, invoice: ExtractedInvoice) -> Issue:
    return Issue(
        code=code, severity=severity, message=message, invoice_number=invoice.number
    )


def _check_unit_price(
    item: InvoiceItem, invoice: ExtractedInvoice, scales: Scales
) -> Issue | None:
    """Apply the maximum unit price, which only governs "venta de cosas muebles".

    An item of unknown kind is neither excused nor condemned: the check cannot
    be applied, and saying so out loud is what sends the case to a human.
    """
    if item.unit_price <= scales.max_unit_price:
        return None

    if item.kind == "good":
        return _issue(
            "UNIT_PRICE_ABOVE_MAX",
            "error",
            f"Item '{item.description}' is priced at {item.unit_price}, above the "
            f"maximum unit price for goods ({scales.max_unit_price}).",
            invoice,
        )
    if item.kind == "unknown":
        return _issue(
            "UNIT_PRICE_KIND_UNKNOWN",
            "warning",
            f"Item '{item.description}' is priced at {item.unit_price}, above the "
            f"maximum unit price for goods ({scales.max_unit_price}), but its kind "
            "was not determined. The limit could not be applied.",
            invoice,
        )
    return None


def validate_invoice_identity(invoice: ExtractedInvoice, taxpayer_cuit: str) -> list[Issue]:
    """Check the issuing CUIT: well formed first, then the right person.

    A malformed CUIT is reported once and not also as a mismatch. Two issues
    for one problem would make the report read as if there were two.
    """
    if not is_valid_cuit(invoice.issuer_cuit):
        return [
            _issue(
                "INVALID_CUIT",
                "warning",
                f"The issuing CUIT {invoice.issuer_cuit} does not pass the check digit.",
                invoice,
            )
        ]

    if normalize_cuit(invoice.issuer_cuit) != normalize_cuit(taxpayer_cuit):
        return [
            _issue(
                "ISSUER_MISMATCH",
                "warning",
                f"The invoice was issued by {invoice.issuer_cuit}, not by the "
                f"taxpayer under analysis ({taxpayer_cuit}).",
                invoice,
            )
        ]

    return []


def validate_invoice_dates(invoice: ExtractedInvoice, *, today: date) -> list[Issue]:
    """Check the issue date against today and against the rolling window.

    A future date is an error: it cannot be a real invoice. A date before the
    window is merely information, because old invoices are perfectly legitimate
    and simply do not count towards these twelve months.
    """
    if invoice.issue_date > today:
        return [
            _issue(
                "DATE_IN_FUTURE",
                "error",
                f"Invoice is dated {invoice.issue_date}, which is after {today}.",
                invoice,
            )
        ]

    if not within_window(invoice.issue_date, today=today):
        return [
            _issue(
                "OUTSIDE_WINDOW",
                "info",
                f"Invoice is dated {invoice.issue_date}, before the rolling window "
                f"that starts after {one_year_before(today)}. It does not count "
                "towards the last twelve months.",
                invoice,
            )
        ]

    return []


def validate_invoice_amounts(invoice: ExtractedInvoice, scales: Scales) -> list[Issue]:
    """Check that the amounts are positive, add up, and respect the price cap."""
    issues: list[Issue] = []

    for item in invoice.items:
        if item.unit_price <= 0 or item.total <= 0 or item.quantity <= 0:
            issues.append(
                _issue(
                    "NON_POSITIVE_AMOUNT",
                    "warning",
                    f"Item '{item.description}' has a non-positive amount.",
                    invoice,
                )
            )
            continue

        if item.total != item.quantity * item.unit_price:
            issues.append(
                _issue(
                    "ITEM_TOTAL_MISMATCH",
                    "warning",
                    f"Item '{item.description}' totals {item.total}, but "
                    f"{item.quantity} x {item.unit_price} is "
                    f"{item.quantity * item.unit_price}.",
                    invoice,
                )
            )

        price_issue = _check_unit_price(item, invoice, scales)
        if price_issue is not None:
            issues.append(price_issue)

    if invoice.total <= 0:
        issues.append(
            _issue("NON_POSITIVE_AMOUNT", "warning", "Invoice total is not positive.", invoice)
        )
        return issues

    items_total: Decimal = sum((item.total for item in invoice.items), Decimal("0"))
    if invoice.total != items_total:
        issues.append(
            _issue(
                "TOTAL_MISMATCH",
                "warning",
                f"Invoice totals {invoice.total}, but its items add up to {items_total}.",
                invoice,
            )
        )

    return issues
