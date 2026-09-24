"""The graph nodes.

Each node is built by a factory that closes over its dependencies, so the
graph can be assembled with a fake extractor and a fixed clock without any
LangGraph-specific injection machinery.

Nodes are thin: they move data between the state and the pure functions in
`validation`, `analysis` and `report`. The logic being tested elsewhere is what
keeps these small enough to read in one go.
"""

from datetime import date

from copiloto.extractors.protocol import ExtractionError, InvoiceExtractor
from copiloto.graph.state import CopilotState
from copiloto.models import ExtractedInvoice, Issue
from copiloto.scales import Scales
from copiloto.validation import (
    validate_invoice_amounts,
    validate_invoice_dates,
    validate_invoice_identity,
)


def make_extract_node(extractor: InvoiceExtractor):
    """Build the only node that reads with a model.

    It reads and records; it never judges. An invoice that cannot be read
    becomes an issue and the remaining invoices are still processed, because
    one unreadable document should not hide the other eleven.
    """

    def extract_invoices(state: CopilotState) -> dict:
        raw_invoices = state.get("raw_invoices", ())
        if not raw_invoices:
            # Zero invoices would accumulate zero and resolve to category A,
            # which reads exactly like "all good". It is missing data instead.
            return {
                "invoices": (),
                "issues": [
                    Issue(
                        code="NO_INVOICES",
                        severity="warning",
                        message="No invoices were provided, so nothing could be assessed.",
                    )
                ],
            }

        invoices: list[ExtractedInvoice] = []
        issues: list[Issue] = []
        for raw in raw_invoices:
            try:
                invoices.append(extractor.extract(raw))
            except ExtractionError as error:
                issues.append(
                    Issue(
                        code="EXTRACTION_FAILED",
                        severity="warning",
                        message=f"An invoice could not be read: {error}",
                    )
                )

        return {"invoices": tuple(invoices), "issues": issues}


    return extract_invoices


def make_validate_node(*, scales: Scales, today: date):
    """Build the node where the code checks what the model read."""

    def validate_invoices(state: CopilotState) -> dict:
        taxpayer_cuit = state.get("taxpayer_cuit", "")
        issues: list[Issue] = []

        for invoice in state.get("invoices", ()):
            issues += validate_invoice_identity(invoice, taxpayer_cuit)
            issues += validate_invoice_amounts(invoice, scales)
            issues += validate_invoice_dates(invoice, today=today)

        return {"issues": issues}

    return validate_invoices
