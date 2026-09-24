"""The web interface: the copilot a person actually opens.

Server-rendered pages in Spanish over the same service the CLI uses. The
graph, the validations and the report are tested elsewhere; these tests cover
what the browser sees: the form, the handoff to an accountant, the report, and
the errors a person can cause.
"""

import re
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from copiloto.extractors.fake import FakeExtractor
from copiloto.models import ExtractedInvoice, InvoiceItem
from copiloto.report import DISCLAIMER_ES
from copiloto.web.app import WebSettings, create_app

TODAY = date(2026, 9, 24)

INVOICE_TEXT = """FACTURA C
Punto de venta 0001 - Comprobante 0000000{n}
CUIT emisor: 20-11111111-2
Fecha de emision: 15/0{m}/2026

Detalle:
- Consultoria | Cantidad 1,00 | Precio unitario 800.000,00

TOTAL: $ 800.000,00"""


def rendered_texts() -> list[str]:
    return [INVOICE_TEXT.format(n=i, m=m) for i, m in enumerate([7, 8, 9], start=1)]


def mapping_for(texts: list[str]) -> dict[str, ExtractedInvoice]:
    amount = Decimal("800000.00")
    item = InvoiceItem(
        description="Consultoria", quantity=Decimal("1"), unit_price=amount, total=amount, kind="service"
    )
    return {
        text: ExtractedInvoice(
            number=f"0001-0000000{i}",
            issuer_cuit="20-11111111-2",
            issue_date=date(2026, month, 15),
            items=(item,),
            total=amount,
        )
        for i, (text, month) in enumerate(zip(texts, [7, 8, 9][: len(texts)], strict=True), start=1)
    }


def plain(text: str) -> str:
    """Strip tags and markdown emphasis so the disclaimer compares as prose."""
    return " ".join(re.sub(r"<[^>]+>", "", text).replace("**", "").split())


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    settings = WebSettings(
        state_db=None,
        extractor_mode="cli",
        extractor_factory=lambda _case: FakeExtractor(mapping_for(rendered_texts())),
        clock=lambda: TODAY,
    )
    return TestClient(create_app(settings), follow_redirects=True)


def upload(client: TestClient, texts: list[str], **fields):
    files = [("invoices", (f"factura-{i}.txt", text, "text/plain")) for i, text in enumerate(texts)]
    data = {"cuit": "20-11111111-2", "category": "A", **fields}
    return client.post("/casos", data=data, files=files)


class TestHome:
    def test_opens_in_spanish_with_the_disclaimer(self, client: TestClient) -> None:
        page = client.get("/")

        assert page.status_code == 200
        assert "Copiloto de monotributo" in page.text
        assert plain(DISCLAIMER_ES) in plain(page.text)

    def test_offers_the_example_cases(self, client: TestClient) -> None:
        page = client.get("/")

        assert "all_in_order" in page.text
        assert "category_change" in page.text

    def test_the_form_asks_for_what_the_cli_asks(self, client: TestClient) -> None:
        page = client.get("/")

        for field in ("cuit", "category", "invoices", "surface_m2", "energy_kwh", "annual_rent"):
            assert f'name="{field}"' in page.text


class TestExamples:
    def test_a_calm_example_lands_on_its_report(self, client: TestClient) -> None:
        page = client.post("/casos/ejemplo/all_in_order")

        assert page.status_code == 200
        assert "Informe de monotributo" in page.text
        assert "Categoría estimada" in page.text
        assert plain(DISCLAIMER_ES) in plain(page.text)

    def test_a_derived_example_lands_on_the_review_form(self, client: TestClient) -> None:
        page = client.post("/casos/ejemplo/category_change")

        assert page.status_code == 200
        assert "Derivamos este caso a un contador" in page.text
        assert 'name="verdict"' in page.text
        assert "categoría distinta de la registrada" in page.text

    def test_an_unknown_example_is_404(self, client: TestClient) -> None:
        assert client.post("/casos/ejemplo/no-such-case").status_code == 404


class TestReview:
    def test_the_accountant_resumes_the_case_from_the_form(self, client: TestClient) -> None:
        pending = client.post("/casos/ejemplo/category_change")
        case_url = str(pending.url)

        page = client.post(
            f"{case_url}/revision",
            data={"verdict": "confirmado", "notes": "Corresponde recategorizar."},
        )

        assert page.status_code == 200
        assert "Revisado por un contador" in page.text
        assert "Corresponde recategorizar." in page.text
        assert 'name="verdict"' not in page.text

    def test_a_dismissed_verdict_is_recorded(self, client: TestClient) -> None:
        pending = client.post("/casos/ejemplo/category_change")

        page = client.post(f"{pending.url}/revision", data={"verdict": "descartado"})

        assert "descartado" in page.text

    def test_notes_are_escaped_not_rendered(self, client: TestClient) -> None:
        """Whatever a person types ends up on a page other people open."""
        pending = client.post("/casos/ejemplo/category_change")

        page = client.post(
            f"{pending.url}/revision",
            data={"verdict": "confirmado", "notes": "<script>alert(1)</script>"},
        )

        assert "<script>" not in page.text
        assert "&lt;script&gt;" in page.text

    def test_a_finished_case_cannot_be_reviewed_again(self, client: TestClient) -> None:
        done = client.post("/casos/ejemplo/all_in_order")

        page = client.post(f"{done.url}/revision", data={"verdict": "confirmado"})

        assert page.status_code == 409

    def test_the_review_page_survives_a_reload(self, client: TestClient) -> None:
        pending = client.post("/casos/ejemplo/category_change")

        again = client.get(str(pending.url))

        assert "Derivamos este caso a un contador" in again.text


class TestOwnInvoices:
    def test_uploaded_text_invoices_produce_a_report(self, client: TestClient) -> None:
        page = upload(client, rendered_texts())

        assert page.status_code == 200
        assert "Informe de monotributo" in page.text
        assert "Facturas analizadas: 3" in page.text

    def test_declared_parameters_reach_the_report(self, client: TestClient) -> None:
        page = upload(client, rendered_texts(), surface_m2="25", energy_kwh="3000", annual_rent="1000000")

        assert "Parámetros declarados" in page.text
        assert "25 m²" in page.text

    def test_an_invalid_cuit_is_rejected_with_the_form_again(self, client: TestClient) -> None:
        page = upload(client, rendered_texts(), cuit="20-11111111-3")

        assert page.status_code == 400
        assert "dígito verificador" in page.text
        assert 'name="cuit"' in page.text

    def test_an_unknown_category_is_rejected(self, client: TestClient) -> None:
        page = upload(client, rendered_texts(), category="Z")

        assert page.status_code == 400
        assert "Z" in page.text

    def test_no_files_is_rejected(self, client: TestClient) -> None:
        page = client.post("/casos", data={"cuit": "20-11111111-2", "category": "A"})

        assert page.status_code == 400
        assert "factura" in page.text.lower()

    def test_a_negative_parameter_is_rejected(self, client: TestClient) -> None:
        page = upload(client, rendered_texts(), surface_m2="-5")

        assert page.status_code == 400
        assert "superficie" in page.text.lower()

    def test_a_scanned_pdf_is_refused_not_skipped(self, client: TestClient, tmp_path: Path) -> None:
        from pypdf import PdfWriter

        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        blank = tmp_path / "escaneada.pdf"
        with blank.open("wb") as handle:
            writer.write(handle)

        page = client.post(
            "/casos",
            data={"cuit": "20-11111111-2", "category": "A"},
            files=[("invoices", ("escaneada.pdf", blank.read_bytes(), "application/pdf"))],
        )

        assert page.status_code == 400
        assert "OCR" in page.text

    def test_the_offline_extractor_refuses_real_invoices(self, tmp_path: Path) -> None:
        offline = TestClient(
            create_app(WebSettings(state_db=None, extractor_mode="fake", clock=lambda: TODAY)),
            follow_redirects=True,
        )

        page = upload(offline, rendered_texts())

        assert page.status_code == 400
        assert "COPILOTO_EXTRACTOR" in page.text


class TestCases:
    def test_started_cases_are_listed_on_the_home_page(self, client: TestClient) -> None:
        client.post("/casos/ejemplo/category_change")
        client.post("/casos/ejemplo/all_in_order")

        page = client.get("/")

        assert "pendiente" in page.text
        assert "cerrado" in page.text

    def test_an_unknown_case_is_404(self, client: TestClient) -> None:
        assert client.get("/casos/ghost").status_code == 404

    def test_cases_survive_a_new_app_over_the_same_file(self, tmp_path: Path) -> None:
        db = tmp_path / "state.sqlite"
        first = TestClient(create_app(WebSettings(state_db=db, clock=lambda: TODAY)), follow_redirects=True)
        pending = first.post("/casos/ejemplo/category_change")

        second = TestClient(create_app(WebSettings(state_db=db, clock=lambda: TODAY)), follow_redirects=True)
        page = second.post(f"{pending.url}/revision", data={"verdict": "confirmado"})

        assert "Revisado por un contador" in page.text


class TestScannedUploads:
    """A scanned PDF is read when the machine can, and refused when it cannot."""

    def _client(self, text: str, ocr, monkeypatch) -> TestClient:
        monkeypatch.setattr("copiloto.sources.read_pdf_text", lambda _p: "")
        settings = WebSettings(
            state_db=None,
            extractor_mode="cli",
            extractor_factory=lambda _case: FakeExtractor(mapping_for([text])),
            clock=lambda: TODAY,
            ocr=ocr,
        )
        return TestClient(create_app(settings), follow_redirects=True)

    def test_a_scan_is_read_with_ocr_and_waits_for_a_person(self, monkeypatch) -> None:
        text = rendered_texts()[0]
        client = self._client(text, lambda _p: text, monkeypatch)

        page = client.post(
            "/casos",
            data={"cuit": "20-11111111-2", "category": "A"},
            files=[("invoices", ("escaneada.pdf", b"%PDF-1.4 fake", "application/pdf"))],
        )

        assert page.status_code == 200
        assert "OCR" in page.text
        assert "escaneada.pdf" in page.text

    def test_without_ocr_the_form_says_so_instead_of_dropping_it(self, monkeypatch) -> None:
        client = self._client(rendered_texts()[0], None, monkeypatch)

        page = client.post(
            "/casos",
            data={"cuit": "20-11111111-2", "category": "A"},
            files=[("invoices", ("escaneada.pdf", b"%PDF-1.4 fake", "application/pdf"))],
        )

        assert page.status_code == 400
        assert "escaneada.pdf" in page.text
