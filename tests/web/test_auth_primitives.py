"""The three functions the door is built from.

Tested apart from the app because the properties that matter here are about
the values themselves: what the cookie reveals, and what a changed token does
to the sessions handed out under the old one.
"""

from copiloto.web.auth import session_is_valid, session_value, token_matches

TOKEN = "un-secreto-largo-y-dificil"  # noqa: S105  (a fixture, not a credential)


class TestSessionValue:
    def test_it_does_not_contain_the_token(self) -> None:
        assert TOKEN not in session_value(TOKEN)

    def test_it_is_the_same_for_the_same_token(self) -> None:
        """Otherwise every request would need shared state to verify it."""
        assert session_value(TOKEN) == session_value(TOKEN)

    def test_a_different_token_gives_a_different_session(self) -> None:
        assert session_value(TOKEN) != session_value("otro-secreto")

    def test_it_looks_like_nothing_in_particular(self) -> None:
        value = session_value(TOKEN)

        assert len(value) == 64
        assert all(c in "0123456789abcdef" for c in value)


class TestTokenMatches:
    def test_the_exact_token_matches(self) -> None:
        assert token_matches(TOKEN, TOKEN) is True

    def test_anything_else_does_not(self) -> None:
        assert token_matches(TOKEN, "adivinado") is False

    def test_a_prefix_does_not_match(self) -> None:
        """A prefix is what a guesser finds first; it must be worth nothing."""
        assert token_matches(TOKEN, TOKEN[:-1]) is False

    def test_the_empty_string_does_not_match(self) -> None:
        assert token_matches(TOKEN, "") is False


class TestSessionIsValid:
    def test_a_session_issued_for_this_token_is_valid(self) -> None:
        assert session_is_valid(TOKEN, session_value(TOKEN)) is True

    def test_a_session_from_another_token_is_not(self) -> None:
        assert session_is_valid(TOKEN, session_value("otro-secreto")) is False

    def test_no_cookie_is_not_a_session(self) -> None:
        assert session_is_valid(TOKEN, None) is False

    def test_an_empty_cookie_is_not_a_session(self) -> None:
        assert session_is_valid(TOKEN, "") is False

    def test_the_token_itself_is_not_a_session(self) -> None:
        """Pasting the token into the cookie must not work either."""
        assert session_is_valid(TOKEN, TOKEN) is False
