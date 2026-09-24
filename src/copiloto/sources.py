"""Reading invoices a person actually has.

Text files and PDFs. ARCA's comprobantes normally carry embedded text, so
pulling it out is enough and no OCR is involved. A scanned PDF has no text to
pull, and this module says so instead of skipping the file: a silently dropped
invoice would understate the income, which is the one error this project must
never make.

`read_pdf` is a parameter rather than a module-level default, so a test can
replace it. A default bound at import time cannot be.
"""

from collections.abc import Callable
from pathlib import Path

PdfReader = Callable[[Path], str]

TEXT_SUFFIXES = (".txt", ".text")
PDF_SUFFIXES = (".pdf",)
SUPPORTED = TEXT_SUFFIXES + PDF_SUFFIXES


class SourceError(RuntimeError):
    """An invoice could not be read from disk."""


def read_pdf_text(path: Path) -> str:
    """Extract the embedded text of a PDF."""
    from pypdf import PdfReader as _PdfReader  # noqa: PLC0415  (optional at import time)

    reader = _PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _read_one(path: Path, read_pdf: PdfReader) -> str:
    if path.suffix.lower() in PDF_SUFFIXES:
        try:
            text = read_pdf(path)
        except Exception as error:
            raise SourceError(f"No pude leer el PDF {path.name}: {error}") from error

        if not text.strip():
            raise SourceError(
                f"El PDF {path.name} no tiene texto: parece una imagen escaneada. "
                "Esta versión no hace OCR. Pasalo a texto y volvé a intentar."
            )
        return text

    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise SourceError(f"El archivo {path.name} está vacío.")
    return text


def load_invoice_texts(
    path: Path, *, read_pdf: PdfReader | None = None
) -> tuple[str, ...]:
    """Read every invoice under `path`, which may be a folder or a single file.

    Files are read in alphabetical order so two runs over the same folder
    produce the same result.
    """
    read_pdf = read_pdf or read_pdf_text

    if not path.exists():
        raise SourceError(f"No encontré {path}.")

    if path.is_file():
        return (_read_one(path, read_pdf),)

    files = sorted(p for p in path.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED)
    if not files:
        raise SourceError(
            f"No hay facturas en {path}. Esperaba archivos "
            f"{', '.join(SUPPORTED)}."
        )

    return tuple(_read_one(p, read_pdf) for p in files)
