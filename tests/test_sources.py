"""Reading a folder of real invoices.

This is what turns the project from a demo into something a person can use:
their own documents, in the formats they actually have them.

The PDF reader is injected, so these tests never need a PDF fixture and never
depend on how a particular file was produced.
"""

from pathlib import Path

import pytest

from copiloto.sources import (
    InvoiceSource,
    SourceError,
    load_invoice_sources,
    load_invoice_texts,
    ocr_issue,
)

TEXT = "FACTURA C\nCUIT emisor: 20-11111111-2\nTOTAL: $ 800.000,00"


def write(directory: Path, name: str, content: str = TEXT) -> Path:
    path = directory / name
    path.write_text(content, encoding="utf-8")
    return path


class TestReadingAFolder:
    def test_reads_text_invoices(self, tmp_path: Path) -> None:
        write(tmp_path, "factura-1.txt")

        assert load_invoice_texts(tmp_path) == (TEXT,)

    def test_reads_every_invoice_in_the_folder(self, tmp_path: Path) -> None:
        write(tmp_path, "a.txt", "primera")
        write(tmp_path, "b.txt", "segunda")

        assert len(load_invoice_texts(tmp_path)) == 2

    def test_the_order_is_stable(self, tmp_path: Path) -> None:
        """Alphabetical, so two runs over the same folder agree."""
        write(tmp_path, "z.txt", "ultima")
        write(tmp_path, "a.txt", "primera")

        assert load_invoice_texts(tmp_path) == ("primera", "ultima")

    def test_ignores_files_that_are_not_invoices(self, tmp_path: Path) -> None:
        write(tmp_path, "factura.txt")
        write(tmp_path, "notas.md", "no es una factura")
        (tmp_path / "subcarpeta").mkdir()

        assert load_invoice_texts(tmp_path) == (TEXT,)

    def test_accepts_a_single_file_too(self, tmp_path: Path) -> None:
        path = write(tmp_path, "factura.txt")

        assert load_invoice_texts(path) == (TEXT,)


class TestPdf:
    def test_reads_a_pdf_through_the_injected_reader(self, tmp_path: Path) -> None:
        (tmp_path / "factura.pdf").write_bytes(b"%PDF-1.4 fake")

        texts = load_invoice_texts(tmp_path, read_pdf=lambda _p: TEXT)

        assert texts == (TEXT,)

    def test_mixes_pdf_and_text_invoices(self, tmp_path: Path) -> None:
        write(tmp_path, "a.txt", "desde texto")
        (tmp_path / "b.pdf").write_bytes(b"%PDF-1.4 fake")

        texts = load_invoice_texts(tmp_path, read_pdf=lambda _p: "desde pdf")

        assert texts == ("desde texto", "desde pdf")

    def test_a_pdf_without_embedded_text_is_reported_not_skipped(
        self, tmp_path: Path
    ) -> None:
        """A scanned PDF needs OCR; without it, the file is refused, never skipped.

        Skipping it would silently drop income from the total, which is the one
        error this project cannot make.
        """
        (tmp_path / "escaneada.pdf").write_bytes(b"%PDF-1.4 fake")

        with pytest.raises(SourceError) as error:
            load_invoice_texts(tmp_path, read_pdf=lambda _p: "   ")

        assert "escaneada.pdf" in str(error.value)
        assert "--extra ocr" in str(error.value)


class TestOcr:
    def test_a_scanned_pdf_is_read_with_ocr_when_available(self, tmp_path: Path) -> None:
        (tmp_path / "escaneada.pdf").write_bytes(b"%PDF-1.4 fake")

        sources = load_invoice_sources(
            tmp_path, read_pdf=lambda _p: "", ocr=lambda _p: "leido por ocr"
        )

        assert sources == (InvoiceSource(name="escaneada.pdf", text="leido por ocr", via_ocr=True),)

    def test_ocr_is_not_used_when_the_pdf_has_text(self, tmp_path: Path) -> None:
        """Embedded text is exact; OCR is a fallback, never a replacement."""
        (tmp_path / "digital.pdf").write_bytes(b"%PDF-1.4 fake")

        def never(_path: Path) -> str:
            pytest.fail("OCR must not run on a PDF with a text layer")

        sources = load_invoice_sources(tmp_path, read_pdf=lambda _p: TEXT, ocr=never)

        assert sources[0].via_ocr is False

    def test_a_scan_that_ocr_cannot_read_either_is_reported(self, tmp_path: Path) -> None:
        (tmp_path / "borrosa.pdf").write_bytes(b"%PDF-1.4 fake")

        with pytest.raises(SourceError) as error:
            load_invoice_sources(tmp_path, read_pdf=lambda _p: "", ocr=lambda _p: "  ")

        assert "borrosa.pdf" in str(error.value)
        assert "OCR" in str(error.value)

    def test_an_ocr_failure_names_the_file(self, tmp_path: Path) -> None:
        (tmp_path / "rara.pdf").write_bytes(b"%PDF-1.4 fake")

        def exploding(_path: Path) -> str:
            raise RuntimeError("tesseract crashed")

        with pytest.raises(SourceError) as error:
            load_invoice_sources(tmp_path, read_pdf=lambda _p: "", ocr=exploding)

        assert "rara.pdf" in str(error.value)

    def test_text_files_are_never_ocr_sources(self, tmp_path: Path) -> None:
        write(tmp_path, "factura.txt")

        sources = load_invoice_sources(tmp_path, ocr=lambda _p: "nope")

        assert sources == (InvoiceSource(name="factura.txt", text=TEXT, via_ocr=False),)


class TestOcrIssue:
    def test_names_the_files_that_were_read_with_ocr(self) -> None:
        """OCR misreads digits. A person has to look at those invoices."""
        sources = (
            InvoiceSource(name="a.txt", text="x"),
            InvoiceSource(name="b.pdf", text="y", via_ocr=True),
            InvoiceSource(name="c.pdf", text="z", via_ocr=True),
        )

        issue = ocr_issue(sources)

        assert issue is not None
        assert issue.code == "OCR_USED"
        assert issue.severity == "warning"
        assert "b.pdf" in issue.message and "c.pdf" in issue.message

    def test_nothing_when_no_ocr_was_involved(self) -> None:
        assert ocr_issue((InvoiceSource(name="a.txt", text="x"),)) is None

    def test_an_unreadable_pdf_names_the_file(self, tmp_path: Path) -> None:
        (tmp_path / "rota.pdf").write_bytes(b"not a pdf at all")

        def exploding(_path: Path) -> str:
            raise ValueError("cannot parse")

        with pytest.raises(SourceError) as error:
            load_invoice_texts(tmp_path, read_pdf=exploding)

        assert "rota.pdf" in str(error.value)


class TestEmptyAndMissing:
    def test_a_folder_without_invoices_is_reported(self, tmp_path: Path) -> None:
        with pytest.raises(SourceError) as error:
            load_invoice_texts(tmp_path)

        assert ".pdf" in str(error.value)

    def test_a_missing_path_is_reported(self, tmp_path: Path) -> None:
        with pytest.raises(SourceError):
            load_invoice_texts(tmp_path / "no-existe")

    def test_an_empty_text_file_is_reported(self, tmp_path: Path) -> None:
        write(tmp_path, "vacia.txt", "   \n  ")

        with pytest.raises(SourceError) as error:
            load_invoice_texts(tmp_path)

        assert "vacia.txt" in str(error.value)
