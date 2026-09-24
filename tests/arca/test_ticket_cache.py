"""Keeping the access ticket on disk.

WSAA issues one ticket per certificate and service, and answers a second
request with `coe.alreadyAuthenticated` until the first one expires, twelve
hours later. A ticket held only in memory dies with the process, and the next
process is locked out. So the ticket lives in a file.

The file holds a credential. It is written atomically, readable only by its
owner, and anything in it that does not match what is being asked for is
treated as absent rather than trusted.
"""

import json
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from copiloto.arca.ticket_cache import TicketCache
from copiloto.arca.wsaa import HOMOLOGACION, PRODUCCION, AccessTicket

NOW = datetime(2026, 9, 24, 21, 0, tzinfo=UTC)
SERVICE = "ws_sr_constancia_inscripcion"
TICKET = AccessTicket(
    token="un-token",  # noqa: S106
    sign="una-firma",
    expires_at=NOW + timedelta(hours=12),
)


@pytest.fixture
def path(tmp_path: Path) -> Path:
    return tmp_path / "ticket.json"


def cache(path: Path, *, environment: str = HOMOLOGACION, service: str = SERVICE) -> TicketCache:
    return TicketCache(path, environment=environment, service=service)


class TestRoundTrip:
    def test_a_saved_ticket_comes_back_intact(self, path: Path) -> None:
        cache(path).save(TICKET)

        assert cache(path).load() == TICKET

    def test_nothing_saved_yet_is_nothing(self, path: Path) -> None:
        assert cache(path).load() is None

    def test_a_new_ticket_replaces_the_old_one(self, path: Path) -> None:
        newer = AccessTicket(token="otro", sign="otra", expires_at=NOW + timedelta(hours=24))  # noqa: S106

        cache(path).save(TICKET)
        cache(path).save(newer)

        assert cache(path).load() == newer


class TestItIsACredential:
    def test_only_its_owner_can_read_it(self, path: Path) -> None:
        cache(path).save(TICKET)

        assert stat.S_IMODE(path.stat().st_mode) == 0o600

    def test_no_temporary_file_is_left_behind(self, path: Path) -> None:
        cache(path).save(TICKET)

        assert [p.name for p in path.parent.iterdir()] == [path.name]


class TestItIsNotTrustedBlindly:
    def test_a_ticket_for_the_other_environment_is_not_used(self, path: Path) -> None:
        """A homologación ticket sent to production is refused, and wastes a call."""
        cache(path, environment=HOMOLOGACION).save(TICKET)

        assert cache(path, environment=PRODUCCION).load() is None

    def test_a_ticket_for_another_service_is_not_used(self, path: Path) -> None:
        cache(path, service=SERVICE).save(TICKET)

        assert cache(path, service="wsfe").load() is None

    def test_a_corrupt_file_is_treated_as_absent(self, path: Path) -> None:
        path.write_text("{no es json")

        assert cache(path).load() is None

    def test_a_file_missing_fields_is_treated_as_absent(self, path: Path) -> None:
        path.write_text(json.dumps({"environment": HOMOLOGACION, "service": SERVICE}))

        assert cache(path).load() is None
