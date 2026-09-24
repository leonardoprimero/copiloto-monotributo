"""The published diagram must be the graph, not a drawing of it.

Checking that the six node names appear is not enough: redirecting an edge
keeps every name and still makes the picture a lie. So the committed file is
compared byte for byte against what the compiled graph renders.
"""

from datetime import date
from pathlib import Path

from copiloto.analysis import RiskPolicy
from copiloto.extractors.fake import FakeExtractor
from copiloto.graph.builder import build_graph
from copiloto.graph.diagram import DIAGRAM_PATH, render_diagram
from copiloto.registry import default_registry
from copiloto.scales import load_scales

NODES = (
    "extract_invoices",
    "validate_invoices",
    "lookup_taxpayer",
    "analyze_income",
    "request_accountant_review",
    "write_report",
)


def a_graph():
    return build_graph(
        extractor=FakeExtractor({}),
        registry=default_registry(),
        scales=load_scales(),
        today=date(2026, 9, 24),
        policy=RiskPolicy(),
    )


class TestRendering:
    def test_renders_mermaid_from_the_compiled_graph(self) -> None:
        diagram = render_diagram(a_graph())

        assert diagram.strip() != ""
        assert all(node in diagram for node in NODES)

    def test_shows_both_branches_of_the_fork(self) -> None:
        diagram = render_diagram(a_graph())

        assert "ok" in diagram
        assert "review" in diagram

    def test_is_deterministic(self) -> None:
        assert render_diagram(a_graph()) == render_diagram(a_graph())

    def test_does_not_depend_on_the_injected_dependencies(self) -> None:
        """The shape is the shape, whichever extractor or clock is wired in."""
        other = build_graph(
            extractor=FakeExtractor({"x": None}),  # pyright: ignore[reportArgumentType]
            registry=default_registry(),
            scales=load_scales(),
            today=date(2020, 1, 1),
            policy=RiskPolicy(review_levels=frozenset({"exclusion"})),
        )

        assert render_diagram(other) == render_diagram(a_graph())


class TestCommittedFile:
    def test_the_committed_diagram_matches_the_real_graph(self) -> None:
        """The check that actually protects the README.

        Regenerate with: uv run python scripts/export_graph.py
        """
        committed = Path(DIAGRAM_PATH).read_text(encoding="utf-8")

        assert committed.strip() == render_diagram(a_graph()).strip()

    def test_the_diagram_lives_where_the_readme_expects_it(self) -> None:
        assert Path(DIAGRAM_PATH).name == "graph.mmd"
        assert Path(DIAGRAM_PATH).parent.name == "docs"
