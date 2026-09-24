"""Walking skeleton: the smallest graph that exercises the 1.x construction API.

This is not domain logic. It exists to prove, against the installed package,
that StateGraph / START / END / add_node / add_edge / compile behave as the plan
assumes before any real node is written.
"""

from copiloto.graph.hello import build_hello_graph


def test_two_nodes_run_in_order_and_accumulate_steps() -> None:
    graph = build_hello_graph()

    result = graph.invoke({"steps": []})

    assert result["steps"] == ["extract", "report"]


def test_reducer_appends_instead_of_overwriting() -> None:
    graph = build_hello_graph()

    result = graph.invoke({"steps": ["seed"]})

    assert result["steps"] == ["seed", "extract", "report"]
