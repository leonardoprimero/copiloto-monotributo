"""The command line: the demo a person actually runs.

It speaks Spanish because that is what the taxpayer reads, while the code
around it stays in English. When the graph pauses, the CLI plays the part of
the accountant: it shows the alert, asks, and resumes.
"""

import pytest

from copiloto.cli import main

CASES = "evals/cases"


def run(args: list[str], answers: list[str] | None = None, monkeypatch=None) -> int:
    if answers is not None and monkeypatch is not None:
        replies = iter(answers)
        monkeypatch.setattr("builtins.input", lambda _prompt="": next(replies))
    return main(args)


class TestCalmCase:
    def test_prints_the_report_and_exits_cleanly(self, capsys) -> None:
        code = run(["run", "--case", f"{CASES}/all_in_order.json"])

        assert code == 0
        assert "# Informe de monotributo" in capsys.readouterr().out

    def test_does_not_ask_anything(self, capsys, monkeypatch) -> None:
        """A calm case must never block waiting for a keyboard."""
        monkeypatch.setattr(
            "builtins.input", lambda _p="": pytest.fail("should not have asked")
        )

        assert run(["run", "--case", f"{CASES}/all_in_order.json"]) == 0


class TestReviewCase:
    def test_shows_the_alert_and_asks_the_accountant(self, capsys, monkeypatch) -> None:
        code = run(
            ["run", "--case", f"{CASES}/category_change.json"],
            answers=["confirmado", "Corresponde recategorizar."],
            monkeypatch=monkeypatch,
        )
        out = capsys.readouterr().out

        assert code == 0
        assert "Derivamos este caso a un contador" in out
        assert "Corresponde recategorizar." in out
        assert "Revisado por un contador" in out

    def test_the_alert_explains_why(self, capsys, monkeypatch) -> None:
        run(
            ["run", "--case", f"{CASES}/category_change.json"],
            answers=["confirmado", ""],
            monkeypatch=monkeypatch,
        )
        out = capsys.readouterr().out

        assert "categoría distinta de la registrada" in out

    def test_an_empty_verdict_defaults_to_confirmed(self, capsys, monkeypatch) -> None:
        code = run(
            ["run", "--case", f"{CASES}/category_change.json"],
            answers=["", ""],
            monkeypatch=monkeypatch,
        )

        assert code == 0
        assert "confirmado" in capsys.readouterr().out

    def test_a_dismissed_verdict_is_recorded(self, capsys, monkeypatch) -> None:
        run(
            ["run", "--case", f"{CASES}/category_change.json"],
            answers=["descartado", "Está bien así."],
            monkeypatch=monkeypatch,
        )

        assert "descartado" in capsys.readouterr().out


class TestAutoResume:
    def test_never_asks_and_says_nobody_reviewed(self, capsys, monkeypatch) -> None:
        monkeypatch.setattr(
            "builtins.input", lambda _p="": pytest.fail("should not have asked")
        )

        code = run(["run", "--case", f"{CASES}/category_change.json", "--auto-resume"])

        assert code == 0
        assert "Ningún contador revisó este caso" in capsys.readouterr().out


class TestExtractorSelection:
    def test_defaults_to_the_offline_extractor(self, capsys) -> None:
        """A fresh clone runs with no key, no CLI and no network."""
        assert run(["run", "--case", f"{CASES}/all_in_order.json"]) == 0

    @pytest.mark.parametrize("mode", ["fake", "cli", "api"])
    def test_the_flag_selects_the_requested_mode(self, mode: str, monkeypatch) -> None:
        """Only the selection is under test; the extractors have their own suites."""
        from copiloto.cli import build_extractor_factory

        requested: list[str] = []

        def spy(chosen: str):
            requested.append(chosen)
            return build_extractor_factory("fake")

        monkeypatch.setattr("copiloto.cli.build_extractor_factory", spy)

        code = run(["run", "--case", f"{CASES}/all_in_order.json", "--extractor", mode])

        assert code == 0
        assert requested == [mode]

    def test_cli_mode_without_a_tool_explains_what_to_do(self, capsys, monkeypatch) -> None:
        monkeypatch.setenv("COPILOTO_EXTRACTOR_CMD", "")
        monkeypatch.setenv("COPILOTO_CLI", "")
        monkeypatch.setattr("copiloto.extractors.resolve.shutil.which", lambda _n: None)

        code = run(["run", "--case", f"{CASES}/all_in_order.json", "--extractor", "cli"])
        printed = capsys.readouterr()

        assert code == 1
        assert "COPILOTO_EXTRACTOR_CMD" in printed.out + printed.err


class TestArguments:
    def test_a_missing_case_file_is_reported_not_crashed(self, capsys) -> None:
        assert run(["run", "--case", "evals/cases/nope.json"]) == 1

    def test_the_clock_can_be_pinned(self, capsys) -> None:
        """Same input, a different day: the report must state the day it used."""
        assert run(["run", "--case", f"{CASES}/all_in_order.json", "--today", "2026-09-24"]) == 0


class TestLanguage:
    def test_the_prompts_are_in_spanish(self, capsys, monkeypatch) -> None:
        prompts: list[str] = []
        monkeypatch.setattr(
            "builtins.input", lambda p="": (prompts.append(p), "confirmado")[1]
        )

        run(["run", "--case", f"{CASES}/category_change.json"])

        assert any("Veredicto" in p for p in prompts)
        assert any("Notas" in p for p in prompts)
