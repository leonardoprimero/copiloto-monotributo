"""Reading invoices through a provider API.

The mode for deployments that bill for reports. `with_structured_output` makes
the provider guarantee the shape of the answer, so everything the `cli`
extractor has to do by hand — locating JSON, retrying, correcting — disappears.

These tests need no key: the structured model is a stub. The one test that
does talk to a provider is skipped unless a key is present.
"""

import os
from datetime import date
from decimal import Decimal

import pytest

from copiloto.extractors.api import ApiExtractor, build_chat_model
from copiloto.extractors.protocol import ExtractionError, InvoiceExtractor
from copiloto.extractors.schema import RawInvoice, RawItem

TEXT = "FACTURA C 0001-00000042 - CUIT 20-11111111-2 - 15/09/2026 - TOTAL 800000,00"

ANSWER = RawInvoice(
    number="0001-00000042",
    issuer_cuit="20-11111111-2",
    issue_date="2026-09-15",
    total="800000.00",
    items=[
        RawItem(
            description="Consultoria",
            quantity="1",
            unit_price="800000.00",
            total="800000.00",
            kind="service",
        )
    ],
)


class StubModel:
    """Stands in for a chat model already bound to the schema."""

    def __init__(self, answer: RawInvoice) -> None:
        self.answer = answer
        self.prompts: list[str] = []

    def invoke(self, prompt: str) -> RawInvoice:
        self.prompts.append(prompt)
        return self.answer


class FailingModel:
    """A provider that is down, rate limited or unauthenticated."""

    def __init__(self, error: Exception) -> None:
        self.error = error

    def invoke(self, prompt: str) -> RawInvoice:
        raise self.error


class TestExtraction:
    def test_converts_the_structured_answer_into_an_invoice(self) -> None:
        invoice = ApiExtractor(StubModel(ANSWER)).extract(TEXT)

        assert invoice.number == "0001-00000042"
        assert invoice.issue_date == date(2026, 9, 15)
        assert invoice.total == Decimal("800000.00")

    def test_money_arrives_as_decimal(self) -> None:
        invoice = ApiExtractor(StubModel(ANSWER)).extract(TEXT)

        assert isinstance(invoice.total, Decimal)

    def test_the_prompt_carries_the_invoice_text(self) -> None:
        model = StubModel(ANSWER)

        ApiExtractor(model).extract(TEXT)

        assert TEXT in model.prompts[0]

    def test_it_satisfies_the_extractor_protocol(self) -> None:
        assert isinstance(ApiExtractor(StubModel(ANSWER)), InvoiceExtractor)

    def test_an_item_without_a_kind_stays_unknown(self) -> None:
        answer = ANSWER.model_copy(
            update={"items": [ANSWER.items[0].model_copy(update={"kind": ""})]}
        )

        assert ApiExtractor(StubModel(answer)).extract(TEXT).items[0].kind == "unknown"

    def test_an_omitted_line_total_is_derived_here_too(self) -> None:
        """Same rule as the cli extractor: shared conversion, one behaviour."""
        item = ANSWER.items[0].model_copy(
            update={"quantity": "2", "unit_price": "400000.00", "total": ""}
        )
        answer = ANSWER.model_copy(update={"items": [item]})

        assert ApiExtractor(StubModel(answer)).extract(TEXT).items[0].total == Decimal(
            "800000.00"
        )


class TestFailures:
    def test_a_provider_error_becomes_an_extraction_error(self) -> None:
        """The graph only knows ExtractionError; provider details stay here."""
        with pytest.raises(ExtractionError) as error:
            ApiExtractor(FailingModel(RuntimeError("rate limited"))).extract(TEXT)

        assert "rate limited" in str(error.value)

    def test_an_unreadable_amount_is_rejected(self) -> None:
        answer = ANSWER.model_copy(update={"total": "ochocientos mil"})

        with pytest.raises(ExtractionError):
            ApiExtractor(StubModel(answer)).extract(TEXT)


class TestProviderSelection:
    def test_an_unknown_provider_lists_the_supported_ones(self) -> None:
        with pytest.raises(ExtractionError) as error:
            build_chat_model(env={"COPILOTO_API_PROVIDER": "nope"})

        assert "anthropic" in str(error.value)
        assert "openai" in str(error.value)

    def test_a_missing_provider_package_explains_how_to_install_it(self) -> None:
        """The extra is optional: the offline path must never require it."""
        with pytest.raises(ExtractionError) as error:
            build_chat_model(
                env={"COPILOTO_API_PROVIDER": "anthropic"},
                importer=lambda name: (_ for _ in ()).throw(ImportError(name)),
            )

        assert "--extra api" in str(error.value)


@pytest.mark.skipif(
    not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY")),
    reason="no provider key configured",
)
class TestAgainstARealProvider:
    def test_reads_a_synthetic_invoice_end_to_end(self) -> None:
        invoice = ApiExtractor.from_env(env=dict(os.environ)).extract(
            "FACTURA C\nComprobante 0001-00000042\nCUIT emisor: 20-11111111-2\n"
            "Fecha de emision: 15/09/2026\n"
            "Consultoria - Cantidad 1 - Precio unitario 800000,00\nTOTAL: $ 800000,00"
        )

        assert invoice.issuer_cuit.replace("-", "") == "20111111112"
        assert invoice.issue_date == date(2026, 9, 15)
