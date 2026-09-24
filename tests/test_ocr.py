"""OCR for scanned invoices: optional, injected, and honest about its limits.

The engine is tesseract through pytesseract and pypdfium2, installed with
`uv sync --extra ocr` plus the system binary. The unit tests inject a fake
renderer and recognizer so they run anywhere; one integration test draws an
invoice into an image-only PDF and reads it back with the real engine, and it
skips itself where the engine is missing.
"""

from pathlib import Path

import pytest

from copiloto.ocr import OcrUnavailable, ocr_available, ocr_pdf_text


class FakeImage:
    def __init__(self, label: str) -> None:
        self.label = label


def render_two_pages(_path: Path, _dpi: int) -> list[FakeImage]:
    return [FakeImage("page-1"), FakeImage("page-2")]


def recognize(image: FakeImage, lang: str) -> str:
    return f"{image.label} in {lang}"


class TestOcrPdfText:
    def test_recognizes_every_page_and_joins_them(self, tmp_path: Path) -> None:
        text = ocr_pdf_text(tmp_path / "x.pdf", render=render_two_pages, recognize=recognize)

        assert text == "page-1 in spa\npage-2 in spa"

    def test_the_language_is_spanish_by_default(self, tmp_path: Path) -> None:
        """ARCA comprobantes are in Spanish; the wrong model misreads accents and commas."""
        text = ocr_pdf_text(tmp_path / "x.pdf", render=render_two_pages, recognize=recognize)

        assert "in spa" in text

    def test_the_language_can_be_changed(self, tmp_path: Path) -> None:
        text = ocr_pdf_text(
            tmp_path / "x.pdf", lang="eng", render=render_two_pages, recognize=recognize
        )

        assert "in eng" in text

    def test_renders_at_a_resolution_tesseract_can_read(self, tmp_path: Path) -> None:
        seen: list[int] = []

        def spy(_path: Path, dpi: int) -> list[FakeImage]:
            seen.append(dpi)
            return []

        ocr_pdf_text(tmp_path / "x.pdf", render=spy, recognize=recognize)

        assert seen == [300]


class TestAvailability:
    def test_unavailable_when_the_binary_is_missing(self, monkeypatch) -> None:
        monkeypatch.setattr("copiloto.ocr.shutil.which", lambda _name: None)

        assert ocr_available() is False

    def test_using_it_without_the_engine_fails_loudly(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr("copiloto.ocr.shutil.which", lambda _name: None)

        with pytest.raises(OcrUnavailable):
            ocr_pdf_text(tmp_path / "x.pdf")


@pytest.mark.skipif(not ocr_available(), reason="tesseract or the ocr extra is not installed")
class TestWithTheRealEngine:
    def test_reads_an_invoice_that_exists_only_as_an_image(self, tmp_path: Path) -> None:
        """The whole point: a PDF with no text layer still yields its numbers."""
        from PIL import Image, ImageDraw, ImageFont

        page = Image.new("RGB", (1400, 600), "white")
        draw = ImageDraw.Draw(page)
        font = ImageFont.load_default(size=44)
        lines = ["FACTURA C", "CUIT emisor: 20-11111111-2", "TOTAL: $ 800.000,00"]
        for index, line in enumerate(lines):
            draw.text((60, 60 + index * 110), line, fill="black", font=font)
        scanned = tmp_path / "escaneada.pdf"
        page.save(scanned, "PDF", resolution=150)

        text = ocr_pdf_text(scanned)

        assert "20-11111111-2" in text
        assert "800.000,00" in text
