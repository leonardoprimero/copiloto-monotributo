"""Exporting the graph as a Mermaid diagram.

The picture in the README is generated from the compiled graph, never drawn by
hand, and a test compares the committed file against a fresh render. A diagram
that can drift from the code is worse than no diagram: it is documentation
that lies with confidence.
"""

from pathlib import Path

DIAGRAM_PATH = Path(__file__).resolve().parents[3] / "docs" / "graph.mmd"


def render_diagram(graph) -> str:
    """Render the compiled graph as Mermaid source."""
    return graph.get_graph().draw_mermaid()


def export_diagram(graph, path: Path = DIAGRAM_PATH) -> Path:
    """Write the rendered diagram to disk and return where it went."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_diagram(graph), encoding="utf-8")
    return path
