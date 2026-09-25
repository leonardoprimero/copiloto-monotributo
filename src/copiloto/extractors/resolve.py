"""Deciding which AI CLI to talk to.

The invocations below were read from each tool's own `--help` on a machine
where all four were installed (2026-09-24). None of them were written from
memory, which is the same rule this project applies to the LangGraph API and
to the ARCA scales.

Verified:
- codex  : `codex exec` runs non-interactively and reads instructions from stdin
- claude : `-p/--print` runs non-interactively
- agy    : `-p/--print` runs in print mode
- gemini : `-p/--prompt` runs headless, appending stdin to the prompt

Any other tool is reachable through COPILOTO_EXTRACTOR_CMD without this file
changing at all.
"""

import os
import shlex
import shutil
from collections.abc import Callable, Mapping

from copiloto.extractors.protocol import ExtractionError

Which = Callable[[str], str | None]

# Order matters: it is the autodetection order, and it is stable so two
# machines with the same tools installed resolve identically.
KNOWN_CLI_ADAPTERS: dict[str, list[str]] = {
    "codex": ["codex", "exec"],
    "claude": ["claude", "-p"],
    "agy": ["agy", "-p"],
    "gemini": ["gemini", "-p"],
}

_NO_CLI_MESSAGE = (
    "No AI CLI was found for COPILOTO_EXTRACTOR=cli. Either install one of "
    f"{', '.join(KNOWN_CLI_ADAPTERS)}, point COPILOTO_EXTRACTOR_CMD at the "
    "command you use, or switch to COPILOTO_EXTRACTOR=api with a provider key. "
    "Refusing to fall back to the offline fake extractor, which would suggest "
    "a model read your invoices when none did."
)


def resolve_cli_argv(*, env: Mapping[str, str], which: Which | None = None) -> list[str]:
    """Return the command to invoke, or explain why none could be chosen.

    `which` is resolved at call time rather than bound as a default argument.
    A default evaluated at import time cannot be replaced by a test, which
    would quietly turn an offline test into a real subprocess call.
    """
    which = which or shutil.which

    explicit = env.get("COPILOTO_EXTRACTOR_CMD", "").strip()
    if explicit:
        return shlex.split(explicit)

    chosen = env.get("COPILOTO_CLI", "").strip()
    if chosen:
        if chosen not in KNOWN_CLI_ADAPTERS:
            raise ExtractionError(
                f"Unknown COPILOTO_CLI={chosen!r}. Known adapters: "
                f"{', '.join(KNOWN_CLI_ADAPTERS)}. Use COPILOTO_EXTRACTOR_CMD "
                "for anything else."
            )
        if which(chosen) is None:
            raise ExtractionError(
                f"COPILOTO_CLI={chosen!r} was requested but {chosen} is not on PATH."
            )
        return list(KNOWN_CLI_ADAPTERS[chosen])

    for name, argv in KNOWN_CLI_ADAPTERS.items():
        if which(name) is not None:
            return list(argv)

    raise ExtractionError(_NO_CLI_MESSAGE)


def detected_cli_name(
    *, env: Mapping[str, str] | None = None, which: Which | None = None
) -> str | None:
    """Return the name of the AI CLI that would be used, if any."""
    env = os.environ if env is None else env
    which = which or shutil.which

    explicit_cmd = env.get("COPILOTO_EXTRACTOR_CMD", "").strip()
    if explicit_cmd:
        parts = shlex.split(explicit_cmd)
        return parts[0] if parts else None

    chosen = env.get("COPILOTO_CLI", "").strip()
    if chosen:
        if chosen in KNOWN_CLI_ADAPTERS and which(chosen) is not None:
            return chosen
        return None

    for name in KNOWN_CLI_ADAPTERS:
        if which(name) is not None:
            return name

    return None


def default_extractor_mode(
    *, env: Mapping[str, str] | None = None, which: Which | None = None
) -> str:
    """Determine the default extractor mode ('cli' or 'fake').

    Respects COPILOTO_EXTRACTOR if set. Otherwise, defaults to 'cli' if
    any known AI CLI is found on PATH (or COPILOTO_EXTRACTOR_CMD is set),
    or 'fake' if none is found.
    """
    env = os.environ if env is None else env

    explicit = env.get("COPILOTO_EXTRACTOR", "").strip().lower()
    if explicit:
        return explicit

    if detected_cli_name(env=env, which=which) is not None:
        return "cli"

    return "fake"

