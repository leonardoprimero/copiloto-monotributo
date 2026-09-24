"""Smoke test: the project is importable on the pinned interpreter.

This guards the single environment decision that everything else rests on:
langchain-core warns about Pydantic V1 internals on Python 3.14, so the
project is pinned to 3.12.
"""

import sys


def test_runs_on_pinned_python_312() -> None:
    assert sys.version_info[:2] == (3, 12)


def test_package_is_importable() -> None:
    import copiloto

    assert copiloto.__name__ == "copiloto"


def test_langgraph_is_installed() -> None:
    import langgraph

    assert langgraph is not None
