"""Assembling the graph.

A directed pipeline with one fork: extract, validate, look up, analyse, and
then either write the report or hand the case to an accountant first.

Dependencies arrive as arguments and are captured by the node factories, so the
same builder produces the offline demo graph, the eval graph and a graph backed
by a real model without any of the nodes knowing the difference.
"""

from datetime import date

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from copiloto.analysis import RiskPolicy
from copiloto.extractors.protocol import InvoiceExtractor
from copiloto.graph.nodes import (
    make_analyze_node,
    make_extract_node,
    make_lookup_node,
    make_report_node,
    make_review_node,
    make_validate_node,
)
from copiloto.graph.checkpoints import open_checkpointer
from copiloto.graph.routing import make_router
from copiloto.graph.state import CopilotState
from copiloto.registry import TaxpayerRegistry
from copiloto.scales import Scales


def build_graph(
    *,
    extractor: InvoiceExtractor,
    registry: TaxpayerRegistry,
    scales: Scales,
    today: date,
    policy: RiskPolicy,
    checkpointer: BaseCheckpointSaver | None = None,
):
    """Wire and compile the copilot graph.

    A checkpointer is always present because `interrupt()` requires one. The
    default is in memory, enough while the process stays alive between the
    pause and the resume; pass the SQLite one from `open_checkpointer` when the
    resume may happen from another process.
    """
    workflow = StateGraph(CopilotState)

    workflow.add_node("extract_invoices", make_extract_node(extractor))
    workflow.add_node("validate_invoices", make_validate_node(scales=scales, today=today))
    workflow.add_node("lookup_taxpayer", make_lookup_node(registry))
    workflow.add_node(
        "analyze_income", make_analyze_node(scales=scales, today=today, policy=policy)
    )
    workflow.add_node("request_accountant_review", make_review_node())
    workflow.add_node("write_report", make_report_node(scales=scales))

    workflow.add_edge(START, "extract_invoices")
    workflow.add_edge("extract_invoices", "validate_invoices")
    workflow.add_edge("validate_invoices", "lookup_taxpayer")
    workflow.add_edge("lookup_taxpayer", "analyze_income")

    # The single fork. Both branches converge on the report, so an escalated
    # case still ends with a document rather than silence.
    workflow.add_conditional_edges(
        "analyze_income",
        make_router(policy),
        {"ok": "write_report", "review": "request_accountant_review"},
    )
    workflow.add_edge("request_accountant_review", "write_report")
    workflow.add_edge("write_report", END)

    return workflow.compile(checkpointer=checkpointer or open_checkpointer(None))
