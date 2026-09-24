"""Rendering synthetic invoices as text.

Every invoice in this repository is made up. The rendered text imitates the
labels of a real Argentine invoice in Spanish, because that is the domain data
an extractor has to cope with, while the CUITs and names are obviously
fabricated.

Note the line items print a quantity and a unit price but no line total, which
is how most invoices actually look. Discovering that a real CLI answers with an
empty field when asked for one is why the schema derives it instead.
"""

from decimal import Decimal

from copiloto.models import ExtractedInvoice


def _amount(value: Decimal) -> str:
    """Format like an invoice does: thousands with dots, cents with a comma."""
    return f"{value:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")


def render_invoice(invoice: ExtractedInvoice) -> str:
    """Render an invoice the way a printed comprobante reads."""
    point_of_sale, number = (
        invoice.number.split("-", 1) if "-" in invoice.number else ("0001", invoice.number)
    )

    lines = [
        "FACTURA C",
        f"Punto de venta {point_of_sale} - Comprobante {number}",
        f"CUIT emisor: {invoice.issuer_cuit}",
        f"Fecha de emision: {invoice.issue_date.strftime('%d/%m/%Y')}",
        "",
        "Detalle:",
    ]
    lines += [
        f"- {item.description} | Cantidad {_amount(item.quantity)} "
        f"| Precio unitario {_amount(item.unit_price)}"
        for item in invoice.items
    ]
    lines += ["", f"TOTAL: $ {_amount(invoice.total)}"]

    return "\n".join(lines)
