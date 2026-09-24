"""The shared state that travels through the graph.

Only `issues` carries a reducer. Three different nodes contribute issues and
none of them may overwrite another's, so the channel appends. Every other key
is written exactly once, by exactly one node, so a plain value is correct and
cheaper to reason about.
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


class CopilotState(TypedDict, total=False):
    # Inputs
    taxpayer_cuit: str
    raw_invoices: tuple[str, ...]
    # Optional input: surface, energy and rent as declared by the taxpayer.
    declared: DeclaredParameters | None

    # Written by extract_invoices
    invoices: tuple[ExtractedInvoice, ...]

    # Appended by extract_invoices, validate_invoices and lookup_taxpayer
    issues: Annotated[list[Issue], operator.add]

    # Written by lookup_taxpayer, analyze_income, request_accountant_review
    # and write_report respectively
    taxpayer: TaxpayerProfile | None
    analysis: Analysis | None
    human_decision: HumanDecision | None
    report: str
