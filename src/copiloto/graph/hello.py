"""A two-node walking skeleton used to pin down the LangGraph construction API.

Kept deliberately tiny: it proves the wiring, not the domain.
"""

import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph


class HelloState(TypedDict):
    # Annotated with a reducer, so every node appends to the list instead of
    # replacing it. This is the same mechanism the real graph uses for issues.
    steps: Annotated[list[str], operator.add]


def _extract(state: HelloState) -> HelloState:
    return {"steps": ["extract"]}


def _report(state: HelloState) -> HelloState:
    return {"steps": ["report"]}


def build_hello_graph():
    workflow = StateGraph(HelloState)
    workflow.add_node("extract", _extract)
    workflow.add_node("report", _report)
    workflow.add_edge(START, "extract")
    workflow.add_edge("extract", "report")
    workflow.add_edge("report", END)
    return workflow.compile()
