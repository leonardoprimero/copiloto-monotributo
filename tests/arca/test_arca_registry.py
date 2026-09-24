"""The real padrón behind the same Protocol the mock implements.

The graph asks a `TaxpayerRegistry` for a category and does not care where the
answer came from. This is the implementation that would ask ARCA, assembled
from the two verified halves: a WSAA ticket and a constancia lookup.

No test here opens a socket. The ticket source and the SOAP call are injected,
which is also how a deployment would swap in a real transport.
"""

from datetime import UTC, datetime, timedelta

import pytest

from copiloto.arca.padron import PadronError
from copiloto.arca.registry import ArcaRegistry
from copiloto.arca.wsaa import AccessTicket
from copiloto.registry import TaxpayerRegistry
from tests.arca.responses import MONOTRIBUTISTA, NO_EXISTE, REGIMEN_GENERAL

NOW = datetime(2026, 9, 24, 10, 0, tzinfo=UTC)
CUIT = "27-01594221-0"


def ticket(expires_in: timedelta = timedelta(hours=8)) -> AccessTicket:
    return AccessTicket(token="un-token", sign="una-firma", expires_at=NOW + expires_in)  # noqa: S106


class Calls:
    """Records every lookup and answers with a canned response."""

    def __init__(self, response: str = MONOTRIBUTISTA) -> None:
        self.response = response
        self.seen: list[tuple[str, str, str]] = []

    def __call__(self, token: str, sign: str, cuit: str) -> str:
        self.seen.append((token, sign, cuit))
        return self.response


def a_registry(
    *, response: str = MONOTRIBUTISTA, tickets=None, represented: str = "20-11111111-2"
) -> tuple[ArcaRegistry, Calls, list[datetime]]:
    asked: list[datetime] = []
    calls = Calls(response)

    def get_ticket(now: datetime) -> AccessTicket:
        asked.append(now)
        return (tickets or (lambda _n: ticket()))(now)

    registry = ArcaRegistry(
        represented_cuit=represented,
        request_ticket=get_ticket,
        call_padron=calls,
        clock=lambda: NOW,
    )
    return registry, calls, asked


class TestItSatisfiesTheProtocol:
    def test_it_is_a_taxpayer_registry(self) -> None:
        """The graph must not be able to tell this apart from the mock."""
        registry, _, _ = a_registry()

        assert isinstance(registry, TaxpayerRegistry)

    def test_it_does_not_pretend_to_know_who_exists(self) -> None:
        """The mock can list its CUITs; ARCA's padrón cannot be enumerated."""
        registry, _, _ = a_registry()

        assert registry.known_cuits() == ()


class TestLookingSomebodyUp:
    def test_it_returns_the_registered_category(self) -> None:
        registry, _, _ = a_registry()

        found = registry.lookup(CUIT)

        assert found is not None
        assert found.category == "B"

    def test_it_sends_the_credentials_and_the_cuit_without_separators(self) -> None:
        """ARCA's idPersona is eleven digits, not the dashed form."""
        registry, calls, _ = a_registry()

        registry.lookup(CUIT)

        assert calls.seen == [("un-token", "una-firma", "27015942210")]

    def test_somebody_in_the_general_regime_is_simply_unknown(self) -> None:
        registry, _, _ = a_registry(response=REGIMEN_GENERAL)

        assert registry.lookup(CUIT) is None

    def test_a_cuit_that_does_not_exist_is_unknown(self) -> None:
        registry, _, _ = a_registry(response=NO_EXISTE)

        assert registry.lookup(CUIT) is None

    def test_an_invalid_cuit_is_refused_before_arca_is_bothered(self) -> None:
        """A bad check digit is a local mistake; do not spend a call on it."""
        registry, calls, _ = a_registry()

        with pytest.raises(PadronError):
            registry.lookup("20-11111111-3")

        assert calls.seen == []


class TestTheTicketIsReused:
    """The spec says to keep a valid ticket: asking again is an error."""

    def test_a_second_lookup_does_not_ask_for_another_ticket(self) -> None:
        registry, _, asked = a_registry()

        registry.lookup(CUIT)
        registry.lookup(CUIT)

        assert len(asked) == 1, "a second ticket request answers coe.alreadyAuthenticated"

    def test_an_expired_ticket_is_replaced(self) -> None:
        registry, _, asked = a_registry(
            tickets=lambda _now: ticket(expires_in=timedelta(seconds=-1))
        )

        registry.lookup(CUIT)
        registry.lookup(CUIT)

        assert len(asked) == 2

    def test_a_ticket_about_to_expire_is_replaced_too(self) -> None:
        """Valid for five more seconds means expired halfway through the call."""
        registry, _, asked = a_registry(
            tickets=lambda _now: ticket(expires_in=timedelta(seconds=5))
        )

        registry.lookup(CUIT)
        registry.lookup(CUIT)

        assert len(asked) == 2


class TestWhatItRepresents:
    def test_the_represented_cuit_must_be_valid(self) -> None:
        """It is the CUIT the taxpayer delegated the service to."""
        with pytest.raises(ValueError, match="CUIT"):
            ArcaRegistry(
                represented_cuit="20-11111111-3",
                request_ticket=lambda _now: ticket(),
                call_padron=Calls(),
            )
