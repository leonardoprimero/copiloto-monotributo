"""The extractor Protocol and its test double.

The extractor is the only component that reads with a model. Defining it as a
Protocol is what lets the whole tax logic be tested offline, and what will let
`cli` and `api` modes drop in later without the graph noticing.
"""

from datetime import date
from decimal import Decimal

import pytest

from copiloto.extractors.fake import FakeExtractor
from copiloto.extractors.protocol import ExtractionError, InvoiceExtractor
from copiloto.models import ExtractedInvoice, InvoiceItem

INVOICE = ExtractedInvoice(
    number="0001-00000001",
    issuer_cuit="20-11111111-2",
    issue_date=date(2026, 9, 15),
    items=(
        InvoiceItem(
            description="Consultoria",
            quantity=Decimal("1"),
            unit_price=Decimal("800000.00"),
            total=Decimal("800000.00"),
            kind="service",
        ),
    ),
    total=Decimal("800000.00"),
)

TEXT = "FACTURA C 0001-00000001 - CUIT 20-11111111-2 - 15/09/2026 - TOTAL 800000,00"


@pytest.fixture
def extractor() -> FakeExtractor:
    return FakeExtractor({TEXT: INVOICE})


class TestProtocol:
    def test_the_fake_satisfies_the_extractor_protocol(self, extractor) -> None:
        assert isinstance(extractor, InvoiceExtractor)

    def test_the_protocol_is_the_only_thing_callers_need(self, extractor) -> None:
        """Typed against the Protocol, not the implementation."""
        reader: InvoiceExtractor = extractor

        assert reader.extract(TEXT) == INVOICE


class TestExtraction:
    def test_returns_the_invoice_mapped_to_a_known_text(self, extractor) -> None:
        assert extractor.extract(TEXT) == INVOICE

    def test_raises_extraction_error_for_an_unknown_text(self, extractor) -> None:
        """A double must fail loudly rather than invent an invoice."""
        with pytest.raises(ExtractionError):
            extractor.extract("something it was never given")

    def test_the_error_names_the_text_it_could_not_read(self, extractor) -> None:
        with pytest.raises(ExtractionError) as error:
            extractor.extract("unmapped")

        assert "unmapped" in str(error.value)

    def test_is_deterministic(self, extractor) -> None:
        assert extractor.extract(TEXT) is extractor.extract(TEXT)


class TestConstruction:
    def test_can_be_built_from_a_list_of_invoices_and_their_texts(self) -> None:
        """Convenience for eval cases, which carry both sides of the mapping."""
        built = FakeExtractor.from_pairs(((TEXT, INVOICE),))

        assert built.extract(TEXT) == INVOICE

    def test_an_empty_extractor_reads_nothing(self) -> None:
        with pytest.raises(ExtractionError):
            FakeExtractor({}).extract(TEXT)
