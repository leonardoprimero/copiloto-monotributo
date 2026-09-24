"""Pin down the LangGraph 1.x behaviour the design depends on.

These tests are executable documentation. They assert against the installed
package instead of trusting remembered API shapes, and they are the reason the
real review node keeps every side effect after `interrupt()`.

Observed on langgraph 1.2.12 / langchain-core 1.6.4 (2026-09-24).
"""

import operator
from typing import Annotated, TypedDict

import pytest
from langgraph.checkpoint.memory import InMemorySaver, MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt


class ReviewState(TypedDict):
    steps: Annotated[list[str], operator.add]
    verdict: str


@pytest.fixture
def pausing_graph():
    """A one-node graph that pauses, plus the list of its recorded executions."""
    executions: list[str] = []

    def review(state: ReviewState) -> ReviewState:
        executions.append("entered")
        answer = interrupt({"reason": "needs accountant"})
        return {"steps": ["review"], "verdict": answer["verdict"]}

    workflow = StateGraph(ReviewState)
    workflow.add_node("review", review)
    workflow.add_edge(START, "review")
    workflow.add_edge("review", END)
    return workflow.compile(checkpointer=InMemorySaver()), executions


def test_memory_saver_is_an_alias_of_in_memory_saver() -> None:
    # Both names are exported and refer to the same class, so either import
    # works. The project uses InMemorySaver as the canonical spelling.
    assert MemorySaver is InMemorySaver


def test_paused_run_reports_the_interrupt_in_its_result(pausing_graph) -> None:
    graph, _ = pausing_graph

    result = graph.invoke({"steps": []}, {"configurable": {"thread_id": "t1"}})

    assert "__interrupt__" in result
    assert result["__interrupt__"][0].value == {"reason": "needs accountant"}


def test_resuming_replays_the_node_from_its_first_line(pausing_graph) -> None:
    """The finding that shapes the review node: resuming re-runs the whole node.

    Anything a node does before calling `interrupt()` happens twice. The real
    `request_accountant_review` therefore only builds its payload (a pure
    function) before pausing, and writes nothing until after the resume.
    """
    graph, executions = pausing_graph
    config = {"configurable": {"thread_id": "t2"}}

    graph.invoke({"steps": []}, config)
    assert executions == ["entered"]

    final = graph.invoke(Command(resume={"verdict": "confirmed"}), config)

    assert executions == ["entered", "entered"]
    assert final["verdict"] == "confirmed"
    assert final["steps"] == ["review"]


def test_compiled_graph_renders_a_mermaid_diagram(pausing_graph) -> None:
    graph, _ = pausing_graph

    diagram = graph.get_graph().draw_mermaid()

    assert "review" in diagram
    assert diagram.strip() != ""
