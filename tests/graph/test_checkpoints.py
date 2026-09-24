"""Checkpoints on disk: a paused case outlives the process that paused it.

The in-memory saver is enough for a demo where the same process asks the
accountant and resumes. A copilot that hands a case to someone else has to
survive a restart in between, so the pause is written to SQLite and the resume
happens on a fresh graph, in what could be another process, hours later.

Every test here builds two independent graphs over the same file, because a
single graph resuming its own pause proves nothing about persistence.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from copiloto.analysis import Analysis, RiskPolicy
from copiloto.extractors.fake import FakeExtractor
from copiloto.graph.builder import build_graph
from copiloto.graph.checkpoints import open_checkpointer
from copiloto.models import ExtractedInvoice, InvoiceItem
from copiloto.registry import UnavailableRegistry, default_registry
from copiloto.scales import load_scales

TODAY = date(2026, 9, 24)
SCALES = load_scales()
CUIT = "20-11111111-2"
MONTHS = [date(2026, m, 15) for m in range(9, 0, -1)] + [
    date(2025, m, 15) for m in (12, 11, 10)
]


def invoice(total: str, number: str, issue_date: date) -> ExtractedInvoice:
    amount = Decimal(total)
    item = InvoiceItem(
        description="Consultoria", quantity=Decimal("1"), unit_price=amount, total=amount, kind="service"
    )
    return ExtractedInvoice(
        number=number, issuer_cuit=CUIT, issue_date=issue_date, items=(item,), total=amount
    )


# 12 x 1,200,000 = 14,400,000: category B while A is on file, so it pauses.
TWELVE = {f"text-{i}": invoice("1200000", f"0001-{i:08d}", d) for i, d in enumerate(MONTHS)}


def graph_on(db: Path, registry=None):
    return build_graph(
        extractor=FakeExtractor(TWELVE),
        registry=registry or default_registry(),
        scales=SCALES,
        today=TODAY,
        policy=RiskPolicy(),
        checkpointer=open_checkpointer(db),
    )


def config(thread: str) -> RunnableConfig:
    return {"configurable": {"thread_id": thread}}


@pytest.fixture
def db(tmp_path: Path) -> Path:
    return tmp_path / "copiloto.sqlite"


class TestSurvivingTheProcess:
    def test_a_pause_written_by_one_graph_is_resumed_by_another(self, db: Path) -> None:
        first = graph_on(db)
        paused = first.invoke({"taxpayer_cuit": CUIT, "raw_invoices": tuple(TWELVE)}, config("t1"))
        assert "__interrupt__" in paused

        second = graph_on(db)
        decision = {"verdict": "confirmed", "notes": "Recategorizar.", "reviewer": "accountant"}
        finished = second.invoke(Command(resume=decision), config("t1"))

        assert "Revisado por un contador" in finished["report"]
        assert "Recategorizar." in finished["report"]

    def test_the_restored_state_keeps_its_types(self, db: Path) -> None:
        """The allowlisted serializer must reach the SQLite saver too."""
        graph_on(db).invoke({"taxpayer_cuit": CUIT, "raw_invoices": tuple(TWELVE)}, config("t2"))

        restored = graph_on(db).get_state(config("t2")).values

        assert isinstance(restored["analysis"], Analysis)
        assert restored["analysis"].reasons == ("NEAR_REGISTERED_CAP", "CATEGORY_MISMATCH", "PROJECTION_ABOVE_REGISTERED_CAP")
        assert isinstance(restored["invoices"][0].total, Decimal)

    def test_a_paused_thread_reports_what_it_is_waiting_for(self, db: Path) -> None:
        graph_on(db).invoke({"taxpayer_cuit": CUIT, "raw_invoices": tuple(TWELVE)}, config("t3"))

        snapshot = graph_on(db).get_state(config("t3"))

        assert snapshot.next == ("request_accountant_review",)
        assert snapshot.interrupts[0].value["risk_level"] == "medium"

    def test_a_finished_thread_has_nothing_pending(self, db: Path) -> None:
        graph_on(db).invoke({"taxpayer_cuit": CUIT, "raw_invoices": tuple(TWELVE)}, config("t4"))
        graph_on(db).invoke(
            Command(resume={"verdict": "confirmed", "notes": "", "reviewer": "accountant"}),
            config("t4"),
        )

        snapshot = graph_on(db).get_state(config("t4"))

        assert snapshot.next == ()
        assert "report" in snapshot.values

    def test_an_unknown_thread_is_empty_not_an_error(self, db: Path) -> None:
        snapshot = graph_on(db).get_state(config("never-started"))

        assert snapshot.values == {}
        assert snapshot.next == ()


class TestResumingWithoutTheRegistry:
    def test_resuming_never_consults_the_registry(self, db: Path) -> None:
        """The lookup ran before the pause and its result is in the checkpoint.

        Whoever resumes later may not have the declared category at hand, so
        the resume graph carries a registry that refuses to answer. If a node
        asked it, this test would raise.
        """
        graph_on(db).invoke({"taxpayer_cuit": CUIT, "raw_invoices": tuple(TWELVE)}, config("t5"))

        finished = graph_on(db, registry=UnavailableRegistry()).invoke(
            Command(resume={"verdict": "dismissed", "notes": "", "reviewer": "accountant"}),
            config("t5"),
        )

        assert "Categoría registrada: A" in finished["report"]

    def test_the_unavailable_registry_refuses_loudly(self) -> None:
        with pytest.raises(RuntimeError):
            UnavailableRegistry().lookup(CUIT)


class TestOpeningTheCheckpointer:
    def test_without_a_path_it_is_in_memory(self) -> None:
        from langgraph.checkpoint.memory import InMemorySaver

        assert isinstance(open_checkpointer(None), InMemorySaver)

    def test_with_a_path_it_creates_the_file(self, db: Path) -> None:
        open_checkpointer(db)

        assert db.exists()

    def test_the_parent_folder_is_created(self, tmp_path: Path) -> None:
        nested = tmp_path / "deeper" / "still" / "state.sqlite"

        open_checkpointer(nested)

        assert nested.exists()
