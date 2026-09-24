"""Reading invoices a person actually has.

Text files and PDFs. ARCA's comprobantes normally carry embedded text, so
pulling it out is enough and it is exact. A scanned PDF has no text to pull;
with OCR available it is recognized from its pixels and flagged as such, and
without it the file is refused rather than skipped: a silently dropped invoice
would understate the income, which is the one error this project must never
make.

`read_pdf` and `ocr` are parameters rather than module-level defaults, so a
test can replace them. A default bound at import time cannot be.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from copiloto.models import Issue

PdfReader = Callable[[Path], str]
Ocr = Callable[[Path], str]

TEXT_SUFFIXES = (".txt", ".text")
PDF_SUFFIXES = (".pdf",)
SUPPORTED = TEXT_SUFFIXES + PDF_SUFFIXES


class SourceError(RuntimeError):
    """An invoice could not be read from disk."""


@dataclass(frozen=True, slots=True)
class InvoiceSource:
    """One invoice's text and where it came from."""

    name: str
    text: str
    via_ocr: bool = False


def read_pdf_text(path: Path) -> str:
    """Extract the embedded text of a PDF."""
    from pypdf import PdfReader as _PdfReader  # noqa: PLC0415  (optional at import time)

    reader = _PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _read_pdf(path: Path, read_pdf: PdfReader, ocr: Ocr | None) -> InvoiceSource:
    try:
        text = read_pdf(path)
    except Exception as error:
        raise SourceError(f"No pude leer el PDF {path.name}: {error}") from error

    if text.strip():
        return InvoiceSource(name=path.name, text=text)

    if ocr is None:
        raise SourceError(
            f"El PDF {path.name} no tiene texto: parece una imagen escaneada. "
            "Para leerlo hace falta OCR: instalá tesseract y corré `uv sync --extra ocr`."
        )

    try:
        recognized = ocr(path)
    except Exception as error:
        raise SourceError(f"El OCR falló con {path.name}: {error}") from error

    if not recognized.strip():
        raise SourceError(
            f"El PDF {path.name} no tiene texto y el OCR tampoco pudo leerlo. "
            "Probá con un escaneo más nítido."
        )
    return InvoiceSource(name=path.name, text=recognized, via_ocr=True)


def _read_one(path: Path, read_pdf: PdfReader, ocr: Ocr | None) -> InvoiceSource:
    if path.suffix.lower() in PDF_SUFFIXES:
        return _read_pdf(path, read_pdf, ocr)

    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise SourceError(f"El archivo {path.name} está vacío.")
    return InvoiceSource(name=path.name, text=text)


def load_invoice_sources(
    path: Path, *, read_pdf: PdfReader | None = None, ocr: Ocr | None = None
) -> tuple[InvoiceSource, ...]:
    """Read every invoice under `path`, which may be a folder or a single file.

    Files are read in alphabetical order so two runs over the same folder
    produce the same result. OCR, when given, is used only for PDFs without a
    text layer, and the result says so.
    """
    read_pdf = read_pdf or read_pdf_text

    if not path.exists():
        raise SourceError(f"No encontré {path}.")

    if path.is_file():
        return (_read_one(path, read_pdf, ocr),)

    files = sorted(p for p in path.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED)
    if not files:
        raise SourceError(
            f"No hay facturas en {path}. Esperaba archivos "
            f"{', '.join(SUPPORTED)}."
        )

    return tuple(_read_one(p, read_pdf, ocr) for p in files)


def load_invoice_texts(
    path: Path, *, read_pdf: PdfReader | None = None, ocr: Ocr | None = None
) -> tuple[str, ...]:
    """The texts alone, for callers that do not care where they came from."""
    return tuple(s.text for s in load_invoice_sources(path, read_pdf=read_pdf, ocr=ocr))


def ocr_issue(sources: tuple[InvoiceSource, ...]) -> Issue | None:
    """A warning naming the invoices that were read by OCR, or None.

    A warning, not a note: OCR misreads digits, and a misread total changes
    the accumulated income. Those invoices need a person's eyes, so the case
    goes to one.
    """
    names = [s.name for s in sources if s.via_ocr]
    if not names:
        return None
    return Issue(
        code="OCR_USED",
        severity="warning",
        message=(
            f"{len(names)} factura(s) se leyeron con OCR y los números pueden estar mal "
            f"reconocidos: {', '.join(names)}. Conviene cotejarlas contra el original."
        ),
    )
