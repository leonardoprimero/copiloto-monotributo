"""Turning a model's JSON answer into a domain invoice.

Found by running a real CLI against a realistic invoice: most invoices print a
quantity and a unit price per line, but no line total. Demanding one made the
model answer with an empty string, which failed both attempts on a document a
person reads without trouble.

A line total that is not printed is arithmetic, and arithmetic belongs to the
code. Anything that is genuinely unreadable still fails loudly.
"""

from datetime import date
from decimal import Decimal

import pytest

from copiloto.extractors.protocol import ExtractionError
from copiloto.extractors.schema import SYSTEM_PROMPT, to_invoice


def payload(**item_overrides) -> dict:
    item = {
        "description": "Consultoria",
        "quantity": "1",
        "unit_price": "800000.00",
        "total": "800000.00",
        "kind": "service",
    }
    item.update(item_overrides)
    return {
        "number": "0001-00000042",
        "issuer_cuit": "20-11111111-2",
        "issue_date": "2026-09-15",
        "total": "800000.00",
        "items": [item],
    }


class TestConversion:
    def test_strings_become_decimals_and_dates(self) -> None:
        invoice = to_invoice(payload())

        assert invoice.total == Decimal("800000.00")
        assert invoice.issue_date == date(2026, 9, 15)

    def test_an_unrecognised_kind_becomes_unknown_rather_than_failing(self) -> None:
        """The invoice is still readable; "unknown" already escalates on its own."""
        assert to_invoice(payload(kind="producto")).items[0].kind == "unknown"


class TestMissingLineTotal:
    def test_an_empty_line_total_is_computed_from_the_printed_figures(self) -> None:
        data = payload(quantity="3", unit_price="1000.00", total="")
        data["total"] = "3000.00"

        assert to_invoice(data).items[0].total == Decimal("3000.00")

    def test_an_absent_line_total_is_computed_too(self) -> None:
        data = payload(quantity="3", unit_price="1000.00")
        del data["items"][0]["total"]
        data["total"] = "3000.00"

        assert to_invoice(data).items[0].total == Decimal("3000.00")

    def test_the_computed_total_is_exact_to_the_cent(self) -> None:
        data = payload(quantity="3", unit_price="716840.77", total="")
        data["total"] = "2150522.31"

        assert to_invoice(data).items[0].total == Decimal("2150522.31")

    def test_it_cannot_be_computed_without_a_quantity(self) -> None:
        with pytest.raises(ExtractionError):
            to_invoice(payload(quantity="", total=""))

    def test_the_invoice_total_is_never_invented(self) -> None:
        """The document total is the one figure that must be transcribed."""
        data = payload()
        data["total"] = ""

        with pytest.raises(ExtractionError):
            to_invoice(data)


class TestFailingLoudly:
    def test_an_unreadable_amount_is_rejected(self) -> None:
        with pytest.raises(ExtractionError) as error:
            to_invoice(payload(unit_price="ochocientos mil"))

        assert "unit_price" in str(error.value)

    def test_an_unreadable_date_is_rejected(self) -> None:
        data = payload()
        data["issue_date"] = "15/09/2026"

        with pytest.raises(ExtractionError) as error:
            to_invoice(data)

        assert "date" in str(error.value).lower()

    def test_a_missing_field_is_rejected(self) -> None:
        data = payload()
        del data["issuer_cuit"]

        with pytest.raises(ExtractionError):
            to_invoice(data)


class TestPrompt:
    def test_the_prompt_allows_omitting_a_line_total(self) -> None:
        assert "omit" in SYSTEM_PROMPT.lower()

    def test_the_prompt_forbids_recalculating(self) -> None:
        assert "never recalculate" in SYSTEM_PROMPT.lower()

    def test_the_prompt_asks_for_unknown_rather_than_a_guess(self) -> None:
        assert "unknown" in SYSTEM_PROMPT
