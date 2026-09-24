"""Regenerate docs/graph.mmd from the compiled graph.

Run after changing nodes or edges:

    uv run python scripts/export_graph.py

A test compares the committed file against a fresh render, so forgetting this
turns the suite red rather than shipping a stale picture.
"""

from datetime import date

from copiloto.analysis import RiskPolicy
from copiloto.extractors.fake import FakeExtractor
from copiloto.graph.builder import build_graph
from copiloto.graph.diagram import export_diagram
from copiloto.registry import default_registry
from copiloto.scales import load_scales


def main() -> None:
    # The dependencies do not affect the shape, so the cheapest ones will do.
    graph = build_graph(
        extractor=FakeExtractor({}),
        registry=default_registry(),
        scales=load_scales(),
        today=date(2026, 9, 24),
        policy=RiskPolicy(),
    )

    print(f"Wrote {export_diagram(graph)}")


if __name__ == "__main__":
    main()
