"""The shape a model must answer with, and the prompt that asks for it.

Shared by the `cli` and `api` extractors. Money and dates travel as strings
because providers handle plain JSON far more reliably than typed numbers, and
because a float would already have lost cents by the time it arrives. The
conversion to `Decimal` and `date` happens here, in code.
"""

from datetime import date
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, ValidationError

from copiloto.extractors.protocol import ExtractionError
from copiloto.models import ExtractedInvoice, InvoiceItem

SYSTEM_PROMPT = """You extract data from Argentine invoices. You do not compute, \
correct or interpret anything: you transcribe exactly what the document says.

Answer with a single JSON object and nothing else. No prose, no code fences.

Schema:
{
  "number": "invoice number as printed",
  "issuer_cuit": "issuer CUIT as printed",
  "issue_date": "YYYY-MM-DD",
  "total": "decimal as a string, dot as decimal separator",
  "items": [
    {
      "description": "item description",
      "quantity": "decimal as a string",
      "unit_price": "decimal as a string",
      "total": "decimal as a string",
      "kind": "service" | "good" | "unknown"
    }
  ]
}

Rules:
- Copy amounts exactly. Never round, never recalculate a total.
- Use "unknown" for kind whenever the document does not make it clear. Saying \
"unknown" is always better than guessing.
- Most invoices do not print a total per line. Omit an item's "total" when the \
document does not show one; it will be derived from quantity and unit price.
- "number", "issuer_cuit", "issue_date" and the invoice "total" are always \
printed. Transcribe them; never leave them blank and never invent them."""

RETRY_PROMPT = (
    "That answer could not be used. Reply with the single JSON object described "
    "above and nothing else: no prose, no code fences. The problem was: "
)


class RawItem(BaseModel):
    description: str
    quantity: str
    unit_price: str
    # Optional because most invoices print a quantity and a unit price per line
    # but no line total. Found by running a real CLI against a realistic
    # invoice: demanding the field made the model answer with an empty string.
    total: str = ""
    kind: str = "unknown"


class RawInvoice(BaseModel):
    """What the model is asked to produce, before any conversion."""

    number: str
    issuer_cuit: str
    issue_date: str
    total: str
    items: list[RawItem]


def build_prompt(raw: str) -> str:
    return f"{SYSTEM_PROMPT}\n\nInvoice:\n{raw}"


def _decimal(value: str, field: str) -> Decimal:
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError) as error:
        raise ExtractionError(f"{field} is not a valid amount: {value!r}") from error


def _to_item(item: RawItem) -> InvoiceItem:
    quantity = _decimal(item.quantity, "quantity")
    unit_price = _decimal(item.unit_price, "unit_price")

    # A line total that was never printed is arithmetic on two figures that
    # were. Multiplying them is the code deciding, not the model guessing, and
    # it keeps the model from inventing a number to fill the field.
    total = _decimal(item.total, "item total") if item.total else quantity * unit_price

    return InvoiceItem(
        description=item.description,
        quantity=quantity,
        unit_price=unit_price,
        total=total,
        # An unrecognised kind is treated as unknown rather than rejected: the
        # invoice is still readable, and "unknown" already escalates.
        kind=item.kind if item.kind in ("service", "good") else "unknown",
    )


def to_invoice(payload: dict) -> ExtractedInvoice:
    """Validate a model's answer and convert it into a domain invoice."""
    try:
        raw = RawInvoice.model_validate(payload)
    except ValidationError as error:
        raise ExtractionError(f"The answer does not match the schema: {error}") from error

    items = tuple(_to_item(item) for item in raw.items)

    try:
        issue_date = date.fromisoformat(raw.issue_date)
    except ValueError as error:
        raise ExtractionError(f"Invalid issue date: {raw.issue_date!r}") from error

    return ExtractedInvoice(
        number=raw.number,
        issuer_cuit=raw.issuer_cuit,
        issue_date=issue_date,
        items=items,
        total=_decimal(raw.total, "invoice total"),
    )
