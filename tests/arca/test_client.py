"""The assembled client, fed the responses ARCA really sends.

Every other ARCA test checks one piece against the manual. This one wires the
pieces together the way `build_registry` does and answers with responses
recorded from homologación. It exists because each piece passed its own tests
while the whole failed on its first real call: the manual's example ticket is
bare XML, and the wire's is an envelope.

The transport is the only fake. The certificate is real, self-signed, and the
signature is really computed.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from copiloto.arca.client import build_registry
from copiloto.arca.padron import ConstanciaUnavailable, PadronError
from copiloto.arca.soap import SoapError
from copiloto.arca.wsaa import HOMOLOGACION
from tests.arca.certificates import write_self_signed
from tests.arca.recorded import (
    LOGIN_CMS_RESPONSE,
    LOGIN_SIGN,
    LOGIN_TOKEN,
    PERSONA_BLOCKED,
    PERSONA_MONOTRIBUTISTA,
    PERSONA_NOT_FOUND_FAULT,
)

# The evening the responses were recorded. The recorded ticket expires the next
# morning, so a test on the real clock would start failing then.
NOW = datetime(2026, 9, 24, 21, 0, tzinfo=UTC)


class RecordedArca:
    """Answers each endpoint with its recorded response, and remembers the calls."""

    def __init__(self, persona: str = PERSONA_MONOTRIBUTISTA) -> None:
        self.persona = persona
        self.calls: list[tuple[str, str]] = []

    def __call__(self, url: str, envelope: str) -> str:
        self.calls.append((url, envelope))
        if url.endswith("/LoginCms"):
            return LOGIN_CMS_RESPONSE
        return self.persona

    def to(self, suffix: str) -> list[str]:
        return [envelope for url, envelope in self.calls if url.endswith(suffix)]


@pytest.fixture
def credentials(tmp_path: Path) -> tuple[Path, Path]:
    return write_self_signed(tmp_path)


def a_registry(
    credentials: tuple[Path, Path],
    arca: RecordedArca,
    *,
    ticket_cache: Path | None = None,
    now: datetime = NOW,
):
    cert_path, key_path = credentials
    return build_registry(
        cert_path=cert_path,
        key_path=key_path,
        represented_cuit="20-11111111-2",
        environment=HOMOLOGACION,
        post=arca,
        clock=lambda: now,
        ticket_cache=ticket_cache,
    )


class TestARealRoundTrip:
    def test_a_monotributista_comes_back_with_their_category(
        self, credentials: tuple[Path, Path]
    ) -> None:
        profile = a_registry(credentials, RecordedArca()).lookup("27-01594221-0")

        assert profile is not None
        assert (profile.cuit, profile.category) == ("27-01594221-0", "B")

    def test_the_padron_call_carries_the_ticket_wsaa_issued(
        self, credentials: tuple[Path, Path]
    ) -> None:
        arca = RecordedArca()

        a_registry(credentials, arca).lookup("27-01594221-0")

        [padron_call] = arca.to("/personaServiceA5")
        assert f"<token>{LOGIN_TOKEN}</token>" in padron_call
        assert f"<sign>{LOGIN_SIGN}</sign>" in padron_call

    def test_it_logs_in_once_for_two_lookups(self, credentials: tuple[Path, Path]) -> None:
        arca = RecordedArca()
        registry = a_registry(credentials, arca)

        registry.lookup("27-01594221-0")
        registry.lookup("27-01594221-0")

        assert len(arca.to("/LoginCms")) == 1


class TestTheTicketOutlivesTheProcess:
    """A second process must not ask WSAA again while the first ticket lasts."""

    def test_a_second_registry_reuses_the_saved_ticket(
        self, credentials: tuple[Path, Path], tmp_path: Path
    ) -> None:
        arca = RecordedArca()
        saved = tmp_path / "ticket.json"

        a_registry(credentials, arca, ticket_cache=saved).lookup("27-01594221-0")
        a_registry(credentials, arca, ticket_cache=saved).lookup("27-01594221-0")

        assert len(arca.to("/LoginCms")) == 1
        [_, second] = arca.to("/personaServiceA5")
        assert f"<token>{LOGIN_TOKEN}</token>" in second

    def test_an_expired_saved_ticket_is_replaced(
        self, credentials: tuple[Path, Path], tmp_path: Path
    ) -> None:
        arca = RecordedArca()
        saved = tmp_path / "ticket.json"
        a_registry(credentials, arca, ticket_cache=saved).lookup("27-01594221-0")

        the_day_after = NOW + timedelta(days=1)
        a_registry(credentials, arca, ticket_cache=saved, now=the_day_after).lookup(
            "27-01594221-0"
        )

        assert len(arca.to("/LoginCms")) == 2

    def test_without_a_cache_nothing_is_written(
        self, credentials: tuple[Path, Path], tmp_path: Path
    ) -> None:
        before = set((tmp_path).iterdir())

        a_registry(credentials, RecordedArca()).lookup("27-01594221-0")

        assert set(tmp_path.iterdir()) == before


class FaultingArca(RecordedArca):
    """Logs in normally, then answers the padrón with a SOAP fault."""

    def __init__(self, fault: str) -> None:
        super().__init__()
        self.fault = fault

    def __call__(self, url: str, envelope: str) -> str:
        if url.endswith("/personaServiceA5"):
            self.calls.append((url, envelope))
            raise SoapError(self.fault)
        return super().__call__(url, envelope)


class TestWhenThePadronSaysNo:
    def test_a_cuit_that_does_not_exist_is_unknown(
        self, credentials: tuple[Path, Path]
    ) -> None:
        """On the wire, "does not exist" is a fault, not an errorConstancia."""
        registry = a_registry(credentials, FaultingArca(PERSONA_NOT_FOUND_FAULT))

        assert registry.lookup("27-01594221-0") is None

    def test_any_other_fault_is_still_an_error(self, credentials: tuple[Path, Path]) -> None:
        registry = a_registry(credentials, FaultingArca("Error interno"))

        with pytest.raises(PadronError, match="Error interno"):
            registry.lookup("27-01594221-0")

    def test_a_blocked_constancia_reaches_the_caller_with_its_reasons(
        self, credentials: tuple[Path, Path]
    ) -> None:
        registry = a_registry(credentials, RecordedArca(persona=PERSONA_BLOCKED))

        with pytest.raises(ConstanciaUnavailable) as error:
            registry.lookup("20-00000051-6")

        assert error.value.reasons
