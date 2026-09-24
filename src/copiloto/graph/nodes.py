"""The graph nodes.

Each node is built by a factory that closes over its dependencies, so the
graph can be assembled with a fake extractor and a fixed clock without any
LangGraph-specific injection machinery.

Nodes are thin: they move data between the state and the pure functions in
`validation`, `analysis` and `report`. The logic being tested elsewhere is what
keeps these small enough to read in one go.
"""

from datetime import date

from copiloto.analysis import RiskPolicy, analyze
from copiloto.extractors.protocol import ExtractionError, InvoiceExtractor
from copiloto.graph.state import CopilotState
from copiloto.models import ExtractedInvoice, Issue
from copiloto.registry import TaxpayerRegistry
from copiloto.report import render_report
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


def make_lookup_node(registry: TaxpayerRegistry):
    """Build the node that asks the registry which category is on file."""

    def lookup_taxpayer(state: CopilotState) -> dict:
        cuit = state.get("taxpayer_cuit", "")
        profile = registry.lookup(cuit)
        if profile is None:
            # Absence is reported, never filled in with a guess: without a
            # registered category there is nothing to compare against, and the
            # analysis skips those rules rather than inventing them.
            return {
                "taxpayer": None,
                "issues": [
                    Issue(
                        code="TAXPAYER_NOT_FOUND",
                        severity="warning",
                        message=f"CUIT {cuit} is not in the registry, so the "
                        "registered category is unknown.",
                    )
                ],
            }
        return {"taxpayer": profile, "issues": []}

    return lookup_taxpayer


def make_analyze_node(*, scales: Scales, today: date, policy: RiskPolicy):
    """Build the node that turns invoices and issues into a risk level."""

    def analyze_income(state: CopilotState) -> dict:
        return {
            "analysis": analyze(
                state.get("invoices", ()),
                issues=tuple(state.get("issues", [])),
                taxpayer=state.get("taxpayer"),
                today=today,
                scales=scales,
                policy=policy,
            )
        }

    return analyze_income


def make_report_node(*, scales: Scales):
    """Build the node that renders the analysis for the taxpayer.

    The node only adapts state to arguments; the rendering itself is a pure
    function tested on its own.
    """

    def write_report(state: CopilotState) -> dict:
        analysis = state.get("analysis")
        if analysis is None:  # pragma: no cover - the graph always analyses first
            raise RuntimeError("write_report reached without an analysis")

        return {
            "report": render_report(
                analysis,
                issues=tuple(state.get("issues", [])),
                taxpayer=state.get("taxpayer"),
                scales=scales,
                human_decision=state.get("human_decision"),
                invoice_count=len(state.get("invoices", ())),
            )
        }

    return write_report
