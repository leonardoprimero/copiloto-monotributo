"""The copilot service: one object the CLI and the web share.

It owns the checkpointer and hides the graph mechanics: start a case, see
whether it is waiting for an accountant, resume it with a verdict, list what
is on file. Every operation works across process boundaries because the
state lives in the checkpointer, not in the object.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from copiloto.analysis import RiskPolicy
from copiloto.extractors.fake import FakeExtractor
from copiloto.graph.checkpoints import open_checkpointer
from copiloto.models import DeclaredParameters, ExtractedInvoice, HumanDecision, InvoiceItem
from copiloto.registry import default_registry
from copiloto.scales import load_scales
from copiloto.service import (
    CaseAlreadyExists,
    CaseNotPending,
    Copilot,
    Finished,
    PendingReview,
)

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


def twelve(total: str) -> dict[str, ExtractedInvoice]:
    return {f"text-{i}": invoice(total, f"0001-{i:08d}", d) for i, d in enumerate(MONTHS)}


CALM = twelve("800000")  # 9,600,000: A, low
CHANGE = twelve("1200000")  # 14,400,000: B while A is on file


def copilot(db: Path | None = None) -> Copilot:
    return Copilot(
        scales=SCALES, policy=RiskPolicy(), checkpointer=open_checkpointer(db)
    )


def start(service: Copilot, case_id: str, mapping: dict, declared=None):
    return service.start(
        case_id=case_id,
        taxpayer_cuit=CUIT,
        raw_invoices=tuple(mapping),
        extractor=FakeExtractor(mapping),
        registry=default_registry(),
        today=TODAY,
        declared=declared,
    )


class TestStarting:
    def test_a_calm_case_finishes_with_a_report(self) -> None:
        outcome = start(copilot(), "calm", CALM)

        assert isinstance(outcome, Finished)
        assert "# Informe de monotributo" in outcome.report
        assert outcome.case_id == "calm"

    def test_a_risky_case_is_pending_review_with_the_alert(self) -> None:
        outcome = start(copilot(), "change", CHANGE)

        assert isinstance(outcome, PendingReview)
        assert outcome.alert["risk_level"] == "medium"
        assert outcome.alert["computed_category"] == "B"

    def test_declared_parameters_reach_the_analysis(self) -> None:
        outcome = start(copilot(), "declared", CALM, declared=DeclaredParameters(surface_m2=100))

        assert isinstance(outcome, PendingReview)
        assert outcome.alert["computed_category"] == "E"

    def test_a_case_id_cannot_be_reused(self) -> None:
        """Invoking a finished thread again would append issues to its state."""
        service = copilot()
        start(service, "once", CALM)

        with pytest.raises(CaseAlreadyExists):
            start(service, "once", CALM)


class TestResuming:
    def test_resumes_with_the_decision_and_returns_the_report(self) -> None:
        service = copilot()
        start(service, "change", CHANGE)

        outcome = service.resume(
            "change", HumanDecision(verdict="confirmed", notes="Recategorizar.")
        )

        assert isinstance(outcome, Finished)
        assert "Recategorizar." in outcome.report
        assert outcome.human_decision is not None
        assert outcome.human_decision.reviewer == "accountant"

    def test_a_case_that_is_not_pending_cannot_be_resumed(self) -> None:
        service = copilot()
        start(service, "calm", CALM)

        with pytest.raises(CaseNotPending):
            service.resume("calm", HumanDecision(verdict="confirmed"))

    def test_an_unknown_case_cannot_be_resumed(self) -> None:
        with pytest.raises(CaseNotPending):
            copilot().resume("nope", HumanDecision(verdict="confirmed"))

    def test_resuming_from_another_service_instance_on_the_same_file(self, tmp_path: Path) -> None:
        """The accountant's process is not the taxpayer's process."""
        db = tmp_path / "state.sqlite"
        start(copilot(db), "change", CHANGE)

        outcome = copilot(db).resume("change", HumanDecision(verdict="dismissed"))

        assert isinstance(outcome, Finished)
        assert "descartado" in outcome.report


class TestLookingUp:
    def test_a_pending_case_is_returned_with_its_alert(self) -> None:
        service = copilot()
        start(service, "change", CHANGE)

        found = service.get("change")

        assert isinstance(found, PendingReview)
        assert found.alert["registered_category"] == "A"

    def test_a_finished_case_is_returned_with_its_report(self) -> None:
        service = copilot()
        start(service, "calm", CALM)

        found = service.get("calm")

        assert isinstance(found, Finished)
        assert "Sin revisión" in found.report

    def test_an_unknown_case_is_none(self) -> None:
        assert copilot().get("nope") is None


class TestListing:
    def test_lists_every_case_with_its_status(self) -> None:
        service = copilot()
        start(service, "calm", CALM)
        start(service, "change", CHANGE)

        summaries = {s.case_id: s for s in service.list_cases()}

        assert summaries["calm"].status == "done"
        assert summaries["calm"].risk_level == "low"
        assert summaries["change"].status == "pending"
        assert summaries["change"].risk_level == "medium"
        assert summaries["change"].taxpayer_cuit == CUIT
        assert summaries["change"].registered_category == "A"

    def test_each_case_appears_once_despite_many_checkpoints(self) -> None:
        service = copilot()
        start(service, "change", CHANGE)
        service.resume("change", HumanDecision(verdict="confirmed"))

        assert [s.case_id for s in service.list_cases()] == ["change"]

    def test_newest_first(self) -> None:
        service = copilot()
        start(service, "first", CALM)
        start(service, "second", CALM)

        assert [s.case_id for s in service.list_cases()] == ["second", "first"]

    def test_empty_when_nothing_was_started(self) -> None:
        assert copilot().list_cases() == []
