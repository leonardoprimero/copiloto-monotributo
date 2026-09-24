"""Domain models: the shapes that travel through the graph.

These types describe data, never conclusions. An `ExtractedInvoice` records
what the model read, including values that turn out to be wrong; deciding
whether they are wrong belongs to validation and analysis.

Money is `Decimal` everywhere. The published caps carry cents and are
inclusive, so a float rounding error is enough to move someone into the wrong
category.
"""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ItemKind = Literal["service", "good", "unknown"]
Severity = Literal["info", "warning", "error"]
Verdict = Literal["confirmed", "dismissed"]
Reviewer = Literal["accountant", "auto"]


class Frozen(BaseModel):
    """Immutable base: once read, a value is evidence and does not change."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class InvoiceItem(Frozen):
    description: str
    quantity: Decimal
    unit_price: Decimal
    total: Decimal
    # Defaults to "unknown" on purpose. The maximum unit price only applies to
    # "venta de cosas muebles", so silently assuming "service" would let an
    # over-priced item skip that check. An unclassified item stays visible.
    kind: ItemKind = "unknown"


class ExtractedInvoice(Frozen):
    number: str
    issuer_cuit: str
    issue_date: date
    items: tuple[InvoiceItem, ...]
    total: Decimal


class Issue(Frozen):
    """Something worth telling the taxpayer, or the accountant, about."""

    code: str
    severity: Severity
    message: str
    invoice_number: str | None = None


ParameterName = Literal["income", "surface", "energy", "rent"]


class DeclaredParameters(Frozen):
    """The physical parameters, as declared by the taxpayer.

    Income comes from invoices; surface, energy and rent can only come from the
    person, so they are declared and the report says so. Every field is optional
    because a service provider without premises has nothing to declare, and an
    undeclared parameter is reported as not evaluated, never assumed to be zero.
    """

    surface_m2: int | None = Field(default=None, ge=0)
    annual_energy_kwh: int | None = Field(default=None, ge=0)
    annual_rent: Decimal | None = Field(default=None, ge=0)

    def declared(self) -> tuple[ParameterName, ...]:
        """The names of the parameters that were actually given."""
        names: list[ParameterName] = []
        if self.surface_m2 is not None:
            names.append("surface")
        if self.annual_energy_kwh is not None:
            names.append("energy")
        if self.annual_rent is not None:
            names.append("rent")
        return tuple(names)


class TaxpayerProfile(Frozen):
    """What the (mocked) ARCA registry knows about a taxpayer."""

    cuit: str
    name: str
    category: str


class HumanDecision(Frozen):
    """The outcome of a review.

    `reviewer` exists so a report can never present an automatic demo resume as
    an accountant's opinion.
    """

    verdict: Verdict
    notes: str = Field(default="")
    reviewer: Reviewer = "accountant"
