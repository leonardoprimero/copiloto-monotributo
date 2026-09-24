"""The contract every extractor honours.

The extractor is the only place where a model participates: it turns invoice
text into a structured invoice, and it decides nothing. Keeping it behind a
Protocol is what lets `fake`, `cli` and `api` be swapped without the graph,
the validations or the evals changing at all.
"""

from typing import Protocol, runtime_checkable

from copiloto.models import ExtractedInvoice


class ExtractionError(RuntimeError):
    """The invoice could not be read.

    Raised instead of returning a partial or invented invoice: the calling node
    records the failure as an issue, which sends the case to a human.
    """


@runtime_checkable
class InvoiceExtractor(Protocol):
    """Turn raw invoice text into a structured invoice."""

    def extract(self, raw: str) -> ExtractedInvoice: ...
