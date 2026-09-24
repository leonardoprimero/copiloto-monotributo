"""The shared state that travels through the graph.

Two keys carry a reducer, and both for the same reason: they have more than
one writer. `issues` collects from several nodes, and `extracted` collects
from the parallel extraction tasks. Every other key is written exactly once,
by exactly one node, so a plain value is correct and cheaper to reason about.
"""

import operator
from typing import Annotated, TypedDict

from copiloto.analysis import Analysis
from copiloto.models import (
    DeclaredParameters,
    ExtractedInvoice,
    HumanDecision,
    Issue,
    TaxpayerProfile,
)


class ExtractionTask(TypedDict):
    """What one parallel extraction task receives.

    A `Send` hands its node this payload instead of the graph state, so the
    task sees exactly one invoice and nothing else.
    """

    raw: str


class CopilotState(TypedDict, total=False):
    # Inputs
    taxpayer_cuit: str
    raw_invoices: tuple[str, ...]
    # Optional input: surface, energy and rent as declared by the taxpayer.
    declared: DeclaredParameters | None

    # Appended by extract_one, which runs once per invoice and in parallel.
    # A channel rather than a value because there are many writers, and the
    # order they finish in is not the order they were sent in.
    extracted: Annotated[list[ExtractedInvoice], operator.add]

    # Written by collect_invoices: `extracted`, sorted chronologically.
    invoices: tuple[ExtractedInvoice, ...]

    # Appended by extract_invoices, validate_invoices and lookup_taxpayer
    issues: Annotated[list[Issue], operator.add]

    # Written by lookup_taxpayer, analyze_income, request_accountant_review
    # and write_report respectively
    taxpayer: TaxpayerProfile | None
    analysis: Analysis | None
    human_decision: HumanDecision | None
    report: str
