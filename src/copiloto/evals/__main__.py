"""Run the eval suite from the command line.

    uv run python -m copiloto.evals                      # offline, deterministic
    uv run python -m copiloto.evals --extractor cli      # your own AI CLI
    uv run python -m copiloto.evals --extractor api      # a provider key

The offline run must be perfect and gates the suite. The cli and api runs
measure a model and are reported, not enforced: a provider having a bad day is
not a reason to block a commit.
"""

import argparse
import os
import sys

from copiloto.evals.dataset import build_cases
from copiloto.evals.runner import ExtractorFactory, run_all
from copiloto.evals.schema import EvalCase
from copiloto.extractors.api import ApiExtractor
from copiloto.extractors.cli import CliExtractor, run_subprocess
from copiloto.extractors.fake import FakeExtractor
from copiloto.extractors.resolve import resolve_cli_argv
from copiloto.models import ExtractedInvoice

# Offline runs are deterministic, so anything below perfect is a bug.
FAKE_THRESHOLD = 1.0
# Model-backed runs are measured, not gated.
MODEL_THRESHOLD = 0.0


def _fake_factory(case: EvalCase) -> FakeExtractor:
    return FakeExtractor(
        dict(
            zip(
                case.invoice_texts,
                [ExtractedInvoice.model_validate(i) for i in case.invoices],
                strict=True,
            )
        )
    )


def _make_factory(mode: str) -> ExtractorFactory:
    if mode == "fake":
        return _fake_factory
    if mode == "cli":
        argv = resolve_cli_argv(env=dict(os.environ))
        return lambda _case: CliExtractor(run=run_subprocess, argv=argv)
    return lambda _case: ApiExtractor.from_env(env=dict(os.environ))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="copiloto.evals")
    parser.add_argument(
        "--extractor",
        choices=("fake", "cli", "api"),
        default=os.environ.get("COPILOTO_EXTRACTOR", "fake"),
    )
    parser.add_argument(
        "--threshold",
        type=float,
        help="Minimum decision accuracy required to exit successfully.",
    )
    args = parser.parse_args(argv)

    threshold = args.threshold
    if threshold is None:
        threshold = FAKE_THRESHOLD if args.extractor == "fake" else MODEL_THRESHOLD

    report = run_all(build_cases(), _make_factory(args.extractor))
    print(report.render())

    if report.decision_accuracy < threshold:
        print(f"\nBelow the required {threshold:.0%} decision accuracy.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
