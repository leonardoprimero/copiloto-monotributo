"""Reading invoices through whichever AI CLI the user already has.

No API key, no provider SDK: the prompt goes to a subprocess and the answer
comes back as text. That text carries no guarantee of shape, so this extractor
has to find the JSON inside it, validate it, and retry once before giving up.

The subprocess runner is injected, so these tests spawn no processes.
"""

from datetime import date
from decimal import Decimal

import pytest

from copiloto.extractors.cli import CliExtractor, extract_first_json_object
from copiloto.extractors.protocol import ExtractionError, InvoiceExtractor

PAYLOAD = """{
  "number": "0001-00000001",
  "issuer_cuit": "20-11111111-2",
  "issue_date": "2026-09-15",
  "total": "800000.00",
  "items": [
    {"description": "Consultoria", "quantity": "1", "unit_price": "800000.00",
     "total": "800000.00", "kind": "service"}
  ]
}"""

TEXT = "FACTURA C 0001-00000001 - CUIT 20-11111111-2 - 15/09/2026 - TOTAL 800000,00"


def answering(*responses: str):
    """A fake runner that replies with each response in turn, recording calls."""
    calls: list[tuple[list[str], str]] = []
    remaining = list(responses)

    def run(argv: list[str], prompt: str) -> str:
        calls.append((argv, prompt))
        return remaining.pop(0)

    run.calls = calls  # pyright: ignore[reportFunctionMemberAccess]
    return run


def extractor(*responses: str) -> CliExtractor:
    return CliExtractor(run=answering(*responses), argv=["fake-cli"])


class TestFindingTheJson:
    def test_a_bare_json_object(self) -> None:
        assert extract_first_json_object(PAYLOAD)["number"] == "0001-00000001"

    def test_json_inside_a_markdown_fence(self) -> None:
        answer = f"```json\n{PAYLOAD}\n```"

        assert extract_first_json_object(answer)["issuer_cuit"] == "20-11111111-2"

    def test_json_after_a_conversational_preamble(self) -> None:
        """CLIs like to say "Sure, here you go:" before answering."""
        answer = f"Claro, ahi va la factura:\n\n{PAYLOAD}\n\nEspero que sirva."

        assert extract_first_json_object(answer)["total"] == "800000.00"

    def test_braces_inside_strings_do_not_break_the_scan(self) -> None:
        answer = '{"description": "a } b", "n": 1}'

        assert extract_first_json_object(answer)["description"] == "a } b"

    def test_an_answer_without_json_is_rejected(self) -> None:
        with pytest.raises(ExtractionError):
            extract_first_json_object("No pude leer la factura.")

    def test_unbalanced_json_is_rejected(self) -> None:
        with pytest.raises(ExtractionError):
            extract_first_json_object('{"number": "1"')


class TestExtraction:
    def test_reads_an_invoice_from_a_clean_answer(self) -> None:
        invoice = extractor(PAYLOAD).extract(TEXT)

        assert invoice.number == "0001-00000001"
        assert invoice.issue_date == date(2026, 9, 15)
        assert invoice.total == Decimal("800000.00")

    def test_money_arrives_as_decimal_not_float(self) -> None:
        invoice = extractor(PAYLOAD).extract(TEXT)

        assert isinstance(invoice.total, Decimal)
        assert invoice.items[0].unit_price == Decimal("800000.00")

    def test_an_item_without_a_kind_stays_unknown(self) -> None:
        payload = PAYLOAD.replace(', "kind": "service"', "")

        assert extractor(payload).extract(TEXT).items[0].kind == "unknown"

    def test_the_prompt_carries_the_invoice_text(self) -> None:
        run = answering(PAYLOAD)
        CliExtractor(run=run, argv=["fake-cli"]).extract(TEXT)

        assert TEXT in run.calls[0][1]  # pyright: ignore[reportFunctionMemberAccess]

    def test_it_satisfies_the_extractor_protocol(self) -> None:
        assert isinstance(extractor(PAYLOAD), InvoiceExtractor)


class TestRetrying:
    def test_retries_once_when_the_first_answer_has_no_json(self) -> None:
        invoice = extractor("No entendi.", PAYLOAD).extract(TEXT)

        assert invoice.number == "0001-00000001"

    def test_the_retry_tells_the_model_what_went_wrong(self) -> None:
        run = answering("No entendi.", PAYLOAD)
        CliExtractor(run=run, argv=["fake-cli"]).extract(TEXT)

        second_prompt = run.calls[1][1]  # pyright: ignore[reportFunctionMemberAccess]
        assert "JSON" in second_prompt

    def test_gives_up_after_the_second_failure(self) -> None:
        """Bounded: two attempts, then an issue and a human. Never a third."""
        run = answering("nada", "tampoco")

        with pytest.raises(ExtractionError):
            CliExtractor(run=run, argv=["fake-cli"]).extract(TEXT)

        assert len(run.calls) == 2  # pyright: ignore[reportFunctionMemberAccess]

    def test_retries_when_the_json_does_not_match_the_schema(self) -> None:
        broken = '{"number": "1"}'

        invoice = extractor(broken, PAYLOAD).extract(TEXT)

        assert invoice.issuer_cuit == "20-11111111-2"

    def test_a_subprocess_failure_becomes_an_extraction_error(self) -> None:
        def exploding(argv: list[str], prompt: str) -> str:
            raise OSError("command not found")

        with pytest.raises(ExtractionError):
            CliExtractor(run=exploding, argv=["fake-cli"]).extract(TEXT)
