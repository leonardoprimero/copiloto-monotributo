"""Choosing which AI CLI to talk to.

Resolution is explicit before it is clever: an env-provided command wins, then
a named adapter, then autodetection. When nothing resolves it fails with an
actionable message — never a silent fall back to the fake extractor, which
would suggest a model read the invoices when nothing did.
"""

import pytest

from copiloto.extractors.protocol import ExtractionError
from copiloto.extractors.resolve import KNOWN_CLI_ADAPTERS, resolve_cli_argv


def only(*available: str):
    """A `which` stand-in that reports just these binaries as installed."""
    return lambda name: f"/usr/local/bin/{name}" if name in available else None


class TestExplicitCommand:
    def test_an_explicit_command_wins_over_everything(self) -> None:
        argv = resolve_cli_argv(
            env={"COPILOTO_EXTRACTOR_CMD": "my-tool --batch", "COPILOTO_CLI": "codex"},
            which=only("codex", "claude"),
        )

        assert argv == ["my-tool", "--batch"]

    def test_an_explicit_command_works_with_nothing_installed(self) -> None:
        """The escape hatch for any tool this project has never heard of."""
        argv = resolve_cli_argv(
            env={"COPILOTO_EXTRACTOR_CMD": "whatever run"}, which=only()
        )

        assert argv == ["whatever", "run"]


class TestNamedAdapter:
    @pytest.mark.parametrize("name", sorted(KNOWN_CLI_ADAPTERS))
    def test_each_known_adapter_can_be_chosen_by_name(self, name: str) -> None:
        argv = resolve_cli_argv(env={"COPILOTO_CLI": name}, which=only(name))

        assert argv[0] == name

    def test_choosing_a_tool_that_is_not_installed_fails_clearly(self) -> None:
        with pytest.raises(ExtractionError) as error:
            resolve_cli_argv(env={"COPILOTO_CLI": "codex"}, which=only("claude"))

        assert "codex" in str(error.value)

    def test_choosing_an_unknown_name_lists_the_known_ones(self) -> None:
        with pytest.raises(ExtractionError) as error:
            resolve_cli_argv(env={"COPILOTO_CLI": "nope"}, which=only())

        assert "codex" in str(error.value)


class TestAutodetection:
    def test_picks_the_installed_tool(self) -> None:
        assert resolve_cli_argv(env={}, which=only("gemini"))[0] == "gemini"

    def test_the_order_is_stable_and_documented(self) -> None:
        """Two tools installed must always resolve the same way."""
        first = resolve_cli_argv(env={}, which=only("claude", "codex"))
        again = resolve_cli_argv(env={}, which=only("codex", "claude"))

        assert first == again
        assert first[0] == next(iter(KNOWN_CLI_ADAPTERS))


class TestNothingAvailable:
    def test_fails_instead_of_falling_back_to_the_fake_extractor(self) -> None:
        """The single most important behaviour in this module."""
        with pytest.raises(ExtractionError):
            resolve_cli_argv(env={}, which=only())

    def test_the_message_says_what_to_do_about_it(self) -> None:
        with pytest.raises(ExtractionError) as error:
            resolve_cli_argv(env={}, which=only())

        message = str(error.value)
        assert "COPILOTO_EXTRACTOR_CMD" in message
        assert "COPILOTO_EXTRACTOR=api" in message


class TestAdapterDefinitions:
    def test_every_adapter_invokes_its_own_binary(self) -> None:
        for name, argv in KNOWN_CLI_ADAPTERS.items():
            assert argv[0] == name

    def test_every_adapter_is_non_interactive(self) -> None:
        """Verified against each tool's --help on 2026-09-24."""
        assert KNOWN_CLI_ADAPTERS["codex"] == ["codex", "exec"]
        assert KNOWN_CLI_ADAPTERS["claude"] == ["claude", "-p"]
        assert KNOWN_CLI_ADAPTERS["agy"] == ["agy", "-p"]
        assert KNOWN_CLI_ADAPTERS["gemini"] == ["gemini", "-p"]
