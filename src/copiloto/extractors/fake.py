"""A deterministic extractor for tests, evals and the offline demo.

It maps known invoice texts to known invoices, so the whole pipeline after
extraction can be measured against an answer that is certain. This is what
makes `uv run pytest` work on a fresh clone with no key, no AI CLI and no
network.
"""

from collections.abc import Iterable

from copiloto.extractors.protocol import ExtractionError
from copiloto.models import ExtractedInvoice


class FakeExtractor:
    """Return the invoice mapped to a text, or fail."""

    def __init__(self, mapping: dict[str, ExtractedInvoice]) -> None:
        self._mapping = dict(mapping)

    @classmethod
    def from_pairs(
        cls, pairs: Iterable[tuple[str, ExtractedInvoice]]
    ) -> "FakeExtractor":
        """Build from (text, invoice) pairs, the shape an eval case carries."""
        return cls(dict(pairs))

    def extract(self, raw: str) -> ExtractedInvoice:
        try:
            return self._mapping[raw]
        except KeyError:
            # Never guess. A double that invents an invoice would quietly turn
            # a broken test setup into a passing run.
            raise ExtractionError(f"No invoice mapped to the text: {raw!r}") from None
