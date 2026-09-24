"""OCR for invoices that exist only as images.

ARCA comprobantes normally carry a text layer, and that text is exact. A
scanned or photographed invoice does not, and the only way to read it is to
recognize the pixels. That is a guess by construction: a 3 can come back as an
8. So OCR is a fallback, never a replacement, and whoever uses it is told
which files went through it so a person looks at those numbers.

Optional on purpose: `uv sync --extra ocr` plus the tesseract binary. Without
them `ocr_available()` is False and nothing here is called.
"""

import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

Render = Callable[[Path, int], list[Any]]
Recognize = Callable[[Any, str], str]

DEFAULT_LANG = "spa"
DEFAULT_DPI = 300


class OcrUnavailable(RuntimeError):
    """The OCR engine or its Python bindings are not installed."""


def _modules_importable() -> bool:
    try:
        import pypdfium2  # noqa: F401, PLC0415
        import pytesseract  # noqa: F401, PLC0415
    except ImportError:
        return False
    return True


def ocr_available() -> bool:
    """Whether a scanned PDF can be read on this machine."""
    return shutil.which("tesseract") is not None and _modules_importable()


def _render_with_pdfium(path: Path, dpi: int) -> list[Any]:
    import pypdfium2  # noqa: PLC0415

    document = pypdfium2.PdfDocument(str(path))
    try:
        # A scale factor, not a DPI: pdfium's canvas unit is 1/72in. The package
        # ships no stubs, so pyright infers `int` from the default `scale = 1`,
        # while the documented type is float.
        scale = dpi / 72
        return [
            page.render(scale=scale).to_pil()  # pyright: ignore[reportArgumentType]
            for page in document
        ]
    finally:
        document.close()


def _recognize_with_tesseract(image: Any, lang: str) -> str:
    import pytesseract  # noqa: PLC0415

    return pytesseract.image_to_string(image, lang=lang)


def ocr_pdf_text(
    path: Path,
    *,
    lang: str = DEFAULT_LANG,
    render: Render | None = None,
    recognize: Recognize | None = None,
) -> str:
    """Render every page and recognize its text, in reading order.

    `render` and `recognize` are parameters rather than module defaults so a
    test can replace them; the real ones are resolved here, at call time.
    """
    if render is None or recognize is None:
        if not ocr_available():
            raise OcrUnavailable(
                "OCR no disponible: instalá tesseract y corré `uv sync --extra ocr`."
            )
        render = render or _render_with_pdfium
        recognize = recognize or _recognize_with_tesseract

    pages = render(path, DEFAULT_DPI)
    return "\n".join(recognize(page, lang).strip() for page in pages)


def default_ocr() -> Callable[[Path], str] | None:
    """The OCR reader to hand to `load_invoice_sources`, or None if there is none."""
    return ocr_pdf_text if ocr_available() else None
