"""Choosing an extractor by mode.

The CLI and the web interface both take a mode name and need an extractor
back. `fake` needs the eval case to know which invoices its texts map to; `cli`
and `api` ignore the case and read whatever they are handed, which is what
lets the same graph run on eval cases and on a folder of real invoices.
"""

import os
from collections.abc import Callable

from copiloto.evals.schema import EvalCase
from copiloto.extractors.api import ApiExtractor
from copiloto.extractors.cli import CliExtractor, run_subprocess
from copiloto.extractors.fake import FakeExtractor
from copiloto.extractors.protocol import ExtractionError, InvoiceExtractor
from copiloto.extractors.resolve import resolve_cli_argv
from copiloto.models import ExtractedInvoice

MODES = ("fake", "cli", "api")

ExtractorFactory = Callable[[EvalCase | None], InvoiceExtractor]


def fake_for(case: EvalCase | None) -> FakeExtractor:
    """The offline extractor, mapping a case's texts to its ground truth."""
    if case is None:
        # Guarded by the callers' argument checks; kept so the failure is
        # explicit rather than an AttributeError deep inside a node.
        raise ExtractionError(
            "El extractor `fake` solo funciona con un caso de ejemplo: no puede leer facturas reales."
        )
    return FakeExtractor(
        dict(
            zip(
                case.invoice_texts,
                [ExtractedInvoice.model_validate(i) for i in case.invoices],
                strict=True,
            )
        )
    )


def build_extractor_factory(mode: str, env: dict[str, str] | None = None) -> ExtractorFactory:
    """Build the extractor factory for the requested mode.

    Resolving `cli` and `api` happens here, up front, so a missing tool or key
    fails before any invoice is read rather than inside the graph.
    """
    env = dict(os.environ) if env is None else env
    if mode == "fake":
        return fake_for
    if mode == "cli":
        argv = resolve_cli_argv(env=env)
        return lambda _case: CliExtractor(run=run_subprocess, argv=argv)
    if mode == "api":
        return lambda _case: ApiExtractor.from_env(env=env)
    raise ExtractionError(f"Modo de extractor desconocido: {mode!r}. Son: {', '.join(MODES)}.")
