"""Handing a case to an accountant who is not at this keyboard.

With a state file, `run --no-wait` leaves the case on disk and exits, `cases`
shows what is waiting, and `review` resumes it, from another process, whenever
the accountant gets to it. This is what turns the demo into a copilot: the
pause is a handoff, not a prompt.
"""

from pathlib import Path

import pytest

from copiloto.cli import main

CHANGE = "evals/cases/category_change.json"
CALM = "evals/cases/all_in_order.json"


@pytest.fixture
def db(tmp_path: Path) -> str:
    return str(tmp_path / "state.sqlite")


def never_ask(monkeypatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _p="": pytest.fail("should not have asked"))


class TestLeavingACasePending:
    def test_no_wait_prints_the_alert_and_exits_pending(self, db, capsys, monkeypatch) -> None:
        never_ask(monkeypatch)

        code = main(["run", "--case", CHANGE, "--state-db", db, "--no-wait", "--case-id", "c1"])
        out = capsys.readouterr().out

        assert code == 3
        assert "Derivamos este caso a un contador" in out
        assert "c1" in out
        assert "copiloto review" in out
        assert "# Informe" not in out

    def test_no_wait_needs_a_state_file(self, capsys) -> None:
        """Without a file the case dies with the process; refusing is honest."""
        code = main(["run", "--case", CHANGE, "--no-wait"])

        assert code == 2
        assert "--state-db" in capsys.readouterr().err

    def test_a_calm_case_never_pauses_even_with_no_wait(self, db, capsys) -> None:
        code = main(["run", "--case", CALM, "--state-db", db, "--no-wait"])

        assert code == 0
        assert "# Informe de monotributo" in capsys.readouterr().out

    def test_a_case_id_cannot_be_reused(self, db, capsys) -> None:
        main(["run", "--case", CALM, "--state-db", db, "--case-id", "same"])

        code = main(["run", "--case", CALM, "--state-db", db, "--case-id", "same"])

        assert code == 2
        assert "same" in capsys.readouterr().err


class TestListingCases:
    def test_shows_each_case_with_its_status(self, db, capsys) -> None:
        main(["run", "--case", CHANGE, "--state-db", db, "--no-wait", "--case-id", "waiting"])
        main(["run", "--case", CALM, "--state-db", db, "--case-id", "closed"])

        code = main(["cases", "--state-db", db])
        out = capsys.readouterr().out

        assert code == 0
        assert "waiting" in out and "pendiente" in out
        assert "closed" in out and "cerrado" in out

    def test_says_so_when_there_is_nothing(self, db, capsys) -> None:
        code = main(["cases", "--state-db", db])

        assert code == 0
        assert "No hay casos" in capsys.readouterr().out


class TestReviewingLater:
    def test_review_resumes_with_the_verdict_and_prints_the_report(
        self, db, capsys, monkeypatch
    ) -> None:
        never_ask(monkeypatch)
        main(["run", "--case", CHANGE, "--state-db", db, "--no-wait", "--case-id", "c1"])
        capsys.readouterr()

        code = main(
            [
                "review",
                "--state-db",
                db,
                "--case-id",
                "c1",
                "--verdict",
                "confirmado",
                "--notes",
                "Corresponde recategorizar.",
            ]
        )
        out = capsys.readouterr().out

        assert code == 0
        assert "Revisado por un contador" in out
        assert "Corresponde recategorizar." in out

    def test_review_asks_when_no_verdict_is_given(self, db, capsys, monkeypatch) -> None:
        main(["run", "--case", CHANGE, "--state-db", db, "--no-wait", "--case-id", "c1"])
        replies = iter(["descartado", "Está bien así."])
        monkeypatch.setattr("builtins.input", lambda _p="": next(replies))

        code = main(["review", "--state-db", db, "--case-id", "c1"])
        out = capsys.readouterr().out

        assert code == 0
        assert "descartado" in out
        assert "Está bien así." in out

    def test_review_shows_the_alert_again_before_asking(self, db, capsys, monkeypatch) -> None:
        """Hours later, the accountant needs the context back, not just a prompt."""
        main(["run", "--case", CHANGE, "--state-db", db, "--no-wait", "--case-id", "c1"])
        capsys.readouterr()

        main(["review", "--state-db", db, "--case-id", "c1", "--verdict", "confirmado"])

        assert "Derivamos este caso a un contador" in capsys.readouterr().out

    def test_a_reviewed_case_cannot_be_reviewed_twice(self, db, capsys) -> None:
        main(["run", "--case", CHANGE, "--state-db", db, "--no-wait", "--case-id", "c1"])
        main(["review", "--state-db", db, "--case-id", "c1", "--verdict", "confirmado"])

        code = main(["review", "--state-db", db, "--case-id", "c1", "--verdict", "confirmado"])

        assert code == 1
        assert "c1" in capsys.readouterr().err

    def test_an_unknown_case_is_reported(self, db, capsys) -> None:
        code = main(["review", "--state-db", db, "--case-id", "ghost", "--verdict", "confirmado"])

        assert code == 1
        assert "ghost" in capsys.readouterr().err
