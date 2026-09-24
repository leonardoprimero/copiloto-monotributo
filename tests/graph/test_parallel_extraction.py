"""Reading twelve invoices at once instead of one after the other.

Extraction is the only step that calls a model, and it is the slow one: twelve
invoices used to mean twelve round trips in a row. They are independent, so the
graph fans them out with `Send` and LangGraph runs them in one superstep.

Two properties are worth protecting, and both are tested against the installed
package rather than assumed:

- the result is chronological no matter what order the tasks finish in, and
- a failure does not discard the work of the invoices that succeeded.
"""

import contextlib
import time
from datetime import date
from decimal import Decimal

from langchain_core.runnables import RunnableConfig

from copiloto.analysis import RiskPolicy
from copiloto.extractors.protocol import ExtractionError, InvoiceExtractor
from copiloto.graph.builder import build_graph
from copiloto.graph.checkpoints import open_checkpointer
from copiloto.models import ExtractedInvoice, InvoiceItem
from copiloto.registry import default_registry
from copiloto.scales import load_scales

TODAY = date(2026, 9, 24)
SCALES = load_scales()
CUIT = "20-11111111-2"


def invoice_for(month: int) -> ExtractedInvoice:
    amount = Decimal("100000.00")
    item = InvoiceItem(
        description="Consultoria",
        quantity=Decimal("1"),
        unit_price=amount,
        total=amount,
        kind="service",
    )
    return ExtractedInvoice(
        number=f"0001-{month:08d}",
        issuer_cuit=CUIT,
        issue_date=date(2026, month, 15),
        items=(item,),
        total=amount,
    )


class SlowExtractor:
    """Stands in for a model: every read costs wall-clock time."""

    def __init__(self, delay: float = 0.25) -> None:
        self.delay = delay

    def extract(self, raw: str) -> ExtractedInvoice:
        time.sleep(self.delay)
        return invoice_for(int(raw))


class ReverseOrderExtractor:
    """Finishes the last invoice first, to scramble completion order."""

    def __init__(self, count: int) -> None:
        self.count = count

    def extract(self, raw: str) -> ExtractedInvoice:
        month = int(raw)
        time.sleep(0.02 * (self.count - month))
        return invoice_for(month)


class FailingExtractor:
    """Fails one invoice until told otherwise, and records every attempt."""

    def __init__(self, failing: str) -> None:
        self.failing = failing
        self.armed = True
        self.attempts: list[str] = []

    def extract(self, raw: str) -> ExtractedInvoice:
        self.attempts.append(raw)
        if raw == self.failing and self.armed:
            raise RuntimeError("the provider hung up")
        return invoice_for(int(raw))


def run(extractor: InvoiceExtractor, months: list[int], checkpointer=None, config=None):
    graph = build_graph(
        extractor=extractor,
        registry=default_registry(),
        scales=SCALES,
        today=TODAY,
        policy=RiskPolicy(),
        checkpointer=checkpointer or open_checkpointer(None),
    )
    return graph, graph.invoke(
        {"taxpayer_cuit": CUIT, "raw_invoices": tuple(str(m) for m in months)},
        config or {"configurable": {"thread_id": "parallel"}},
    )


class TestItRunsInParallel:
    def test_twelve_invoices_take_about_one_round_trip(self) -> None:
        """Sequentially this is 3 seconds; concurrently it is one delay."""
        months = list(range(1, 13))

        started = time.perf_counter()
        _, state = run(SlowExtractor(delay=0.25), months)
        elapsed = time.perf_counter() - started

        assert len(state["invoices"]) == 12
        assert elapsed < 1.5, f"took {elapsed:.2f}s, so the reads were not concurrent"


class TestTheOrderIsChronological:
    def test_the_result_does_not_depend_on_which_task_finishes_first(self) -> None:
        """Two runs over the same folder must produce the same report."""
        months = list(range(1, 7))

        _, state = run(ReverseOrderExtractor(count=6), months)

        assert [i.issue_date.month for i in state["invoices"]] == months


class TestFailureDoesNotDiscardTheRest:
    def test_an_unreadable_invoice_becomes_an_issue_and_the_others_survive(self) -> None:
        extractor = FailingExtractor(failing="3")

        _, state = run(extractor, [1, 2, 3, 4])

        assert [i.issue_date.month for i in state["invoices"]] == [1, 2, 4]
        assert [i.code for i in state["issues"] if i.code == "EXTRACTION_FAILED"] == [
            "EXTRACTION_FAILED"
        ]

    def test_the_failure_names_the_invoice_it_could_not_read(self) -> None:
        _, state = run(FailingExtractor(failing="2"), [1, 2, 3])

        failed = [i for i in state["issues"] if i.code == "EXTRACTION_FAILED"]
        assert len(failed) == 1


class TestExtractionErrorsAreHandledToo:
    def test_a_declared_extraction_error_is_recorded_like_any_other(self) -> None:
        class Refuses:
            def extract(self, raw: str) -> ExtractedInvoice:
                if raw == "2":
                    raise ExtractionError("the model returned nothing usable")
                return invoice_for(int(raw))

        _, state = run(Refuses(), [1, 2, 3])

        assert len(state["invoices"]) == 2
        assert any(i.code == "EXTRACTION_FAILED" for i in state["issues"])


class TestNoInvoices:
    def test_an_empty_folder_is_still_reported_as_missing_data(self) -> None:
        """Zero invoices resolve to category A, which reads like 'all good'."""
        _, state = run(SlowExtractor(), [])

        assert state["invoices"] == ()
        assert any(i.code == "NO_INVOICES" for i in state["issues"])


class TestACrashDoesNotReReadWhatWasAlreadyRead:
    """Reads cost money with a paid provider, so a resume must not repeat them.

    LangGraph persists the writes of the tasks that finished even when a
    sibling takes the process down, and replays them instead of re-running
    the task. This pins that behaviour against the installed package, because
    it is the reason extraction fans out rather than running in a thread pool.
    """

    def test_only_the_interrupted_invoice_is_read_again(self, tmp_path) -> None:
        reads: list[str] = []

        class Interrupted:
            def __init__(self, crash_on: str | None) -> None:
                self.crash_on = crash_on

            def extract(self, raw: str) -> ExtractedInvoice:
                reads.append(raw)
                if raw == self.crash_on:
                    # Not an ExtractionError and not even an Exception: this
                    # is the process going down, which the node cannot catch.
                    raise KeyboardInterrupt("the process was stopped")
                return invoice_for(int(raw))

        checkpointer = open_checkpointer(tmp_path / "cases.sqlite")
        config: RunnableConfig = {"configurable": {"thread_id": "crashed"}}
        months = [1, 2, 3, 4, 5, 6]

        with contextlib.suppress(KeyboardInterrupt):
            run(Interrupted(crash_on="4"), months, checkpointer, config)
        assert sorted(reads, key=int) == ["1", "2", "3", "4", "5", "6"]

        reads.clear()
        graph = build_graph(
            extractor=Interrupted(crash_on=None),
            registry=default_registry(),
            scales=SCALES,
            today=TODAY,
            policy=RiskPolicy(),
            checkpointer=checkpointer,
        )
        state = graph.invoke(None, config)

        assert reads == ["4"], "the five that succeeded were charged twice"
        assert [i.issue_date.month for i in state["invoices"]] == months
