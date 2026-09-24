"""Reading invoices through whichever AI CLI is already installed.

No API key and no provider SDK: the prompt goes to a subprocess and the answer
comes back as plain text. That is the trade-off of this mode — a provider API
guarantees the shape of its answer, a console does not. So the work a provider
would do for us is done here: find the JSON in the reply, validate it, and
retry once with a corrective message before giving up.

Giving up raises `ExtractionError`, which the graph records as an issue and
routes to a human. It never returns a half-read invoice.
"""

import json
import subprocess
from collections.abc import Callable

from copiloto.extractors.protocol import ExtractionError
from copiloto.extractors.schema import RETRY_PROMPT, build_prompt, to_invoice
from copiloto.models import ExtractedInvoice

Runner = Callable[[list[str], str], str]

_TIMEOUT_SECONDS = 120


def extract_first_json_object(answer: str) -> dict:
    """Find the first balanced JSON object inside an arbitrary reply.

    CLIs wrap answers in prose or code fences, so locating the object is the
    caller's problem. Scanning for balanced braces while respecting strings is
    enough, and far more predictable than a regular expression.
    """
    depth = 0
    start = -1
    in_string = False
    escaped = False

    for index, char in enumerate(answer):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0 and start != -1:
                try:
                    return json.loads(answer[start : index + 1])
                except json.JSONDecodeError:
                    start = -1  # keep looking for a later, well-formed object

    raise ExtractionError("The answer contained no readable JSON object.")


def run_subprocess(argv: list[str], prompt: str) -> str:
    """Send `prompt` to a CLI and return its stdout."""
    completed = subprocess.run(
        argv,
        input=prompt,
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_SECONDS,
        check=False,
    )
    if completed.returncode != 0:
        raise OSError(
            f"{argv[0]} exited with {completed.returncode}: {completed.stderr.strip()[:200]}"
        )
    return completed.stdout


class CliExtractor:
    """Extract invoices by talking to a local AI CLI."""

    def __init__(self, *, run: Runner, argv: list[str]) -> None:
        self._run = run
        self._argv = list(argv)

    def extract(self, raw: str) -> ExtractedInvoice:
        prompt = build_prompt(raw)

        try:
            return self._attempt(prompt)
        except ExtractionError as first_failure:
            # Exactly one retry, and it names the actual problem: telling a
            # model "that was wrong" without saying why tends to produce the
            # same answer again. A second failure means a person should look at
            # the document, so there is never a third attempt.
            try:
                return self._attempt(f"{prompt}\n\n{RETRY_PROMPT}{first_failure}")
            except ExtractionError as second_failure:
                raise ExtractionError(
                    f"Could not read the invoice after two attempts. "
                    f"First: {first_failure}. Second: {second_failure}."
                ) from second_failure

    def _attempt(self, prompt: str) -> ExtractedInvoice:
        try:
            answer = self._run(self._argv, prompt)
        except (OSError, subprocess.SubprocessError) as error:
            raise ExtractionError(f"The CLI could not be run: {error}") from error

        return to_invoice(extract_first_json_object(answer))
