"""Keeping the access ticket on disk.

WSAA issues one ticket per certificate and service, and answers a second
request with `coe.alreadyAuthenticated` until the first one expires, twelve
hours later. A ticket held only in memory dies with the process, and the next
process is locked out. So the ticket lives in a file.

The file holds a credential. It is written atomically, readable only by its
owner, and anything in it that does not match what is being asked for is
treated as absent rather than trusted.
"""

import fcntl
import json
import stat
import threading
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


def cache(
    path: Path,
    *,
    environment: str = HOMOLOGACION,
    service: str = SERVICE,
    certificate: str = "huella-1",
) -> TicketCache:
    return TicketCache(path, environment=environment, service=service, certificate=certificate)


def saved_fields(**changes: object) -> str:
    """A well-formed file, with some fields replaced."""
    fields: dict[str, object] = {
        "environment": HOMOLOGACION,
        "service": SERVICE,
        "certificate": "huella-1",
        "token": TICKET.token,
        "sign": TICKET.sign,
        "expires_at": TICKET.expires_at.isoformat(),
    }
    fields.update(changes)
    return json.dumps(fields)


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
        """Only the ticket and the lock that serialises writers remain."""
        cache(path).save(TICKET)

        assert sorted(p.name for p in path.parent.iterdir()) == [f".{path.name}.lock", path.name]

    def test_the_lock_file_holds_no_secret_and_is_owner_only(self, path: Path) -> None:
        cache(path).save(TICKET)
        lock = path.with_name(f".{path.name}.lock")

        assert lock.read_bytes() == b""
        assert stat.S_IMODE(lock.stat().st_mode) == 0o600

    def test_a_planted_temporary_path_is_not_followed(self, path: Path) -> None:
        """A predictable temporary name is an invitation: whoever plants a
        symlink there first gets the credential written wherever they chose."""
        victim = path.parent / "victima"
        victim.write_text("intacto")
        (path.parent / f".{path.name}.tmp").symlink_to(victim)

        cache(path).save(TICKET)

        assert victim.read_text() == "intacto"
        assert cache(path).load() == TICKET


class TestItIsNotTrustedBlindly:
    def test_a_ticket_for_the_other_environment_is_not_used(self, path: Path) -> None:
        """A homologación ticket sent to production is refused, and wastes a call."""
        cache(path, environment=HOMOLOGACION).save(TICKET)

        assert cache(path, environment=PRODUCCION).load() is None

    def test_a_ticket_for_another_service_is_not_used(self, path: Path) -> None:
        cache(path, service=SERVICE).save(TICKET)

        assert cache(path, service="wsfe").load() is None

    def test_a_ticket_issued_to_another_certificate_is_not_used(self, path: Path) -> None:
        """WSAA binds the ticket to the certificate that signed the request.
        Reusing it with another one is refused, and wastes the call."""
        cache(path, certificate="huella-1").save(TICKET)

        assert cache(path, certificate="huella-2").load() is None

    def test_two_certificates_share_the_file_without_evicting_each_other(
        self, path: Path
    ) -> None:
        """If saving one certificate's ticket threw the other's away, two
        registries alternating on one file would lock each other out."""
        other = AccessTicket(token="otro", sign="otra", expires_at=NOW + timedelta(hours=6))  # noqa: S106

        cache(path, certificate="huella-1").save(TICKET)
        cache(path, certificate="huella-2").save(other)

        assert cache(path, certificate="huella-1").load() == TICKET
        assert cache(path, certificate="huella-2").load() == other

    def test_a_file_from_before_certificates_were_recorded_is_still_used(
        self, path: Path
    ) -> None:
        """The previous version wrote one ticket with no certificate. Discarding
        it would ask WSAA again and be refused until it expires."""
        legacy = {
            "environment": HOMOLOGACION,
            "service": SERVICE,
            "token": TICKET.token,
            "sign": TICKET.sign,
            "expires_at": TICKET.expires_at.isoformat(),
        }
        path.write_text(json.dumps(legacy))

        assert cache(path).load() == TICKET

    def test_two_processes_saving_at_once_do_not_lose_a_ticket(self, path: Path) -> None:
        """Read, add, write: without a lock two processes read the same file
        and the second write drops the first one's ticket. The lock is what
        `save` holds; this test holds it first and watches `save` wait."""
        other = AccessTicket(token="otro", sign="otra", expires_at=NOW + timedelta(hours=6))  # noqa: S106
        lock = path.with_name(f".{path.name}.lock")
        lock.touch()
        saved = threading.Event()

        with lock.open() as held:
            fcntl.flock(held, fcntl.LOCK_EX)
            worker = threading.Thread(
                target=lambda: (cache(path, certificate="huella-2").save(other), saved.set())
            )
            worker.start()
            assert not saved.wait(0.3), "save went ahead while another writer held the lock"
            fcntl.flock(held, fcntl.LOCK_UN)

        worker.join(timeout=5)
        assert saved.is_set()
        cache(path, certificate="huella-1").save(TICKET)
        assert cache(path, certificate="huella-1").load() == TICKET
        assert cache(path, certificate="huella-2").load() == other

    @pytest.mark.parametrize(
        "content",
        [
            json.dumps({"tickets": "no es un mapa"}),
            json.dumps({"tickets": {"clave": "no es una entrada"}}),
            json.dumps(["una", "lista"]),
        ],
        ids=["tickets-not-a-map", "entry-not-an-object", "file-not-an-object"],
    )
    def test_a_malformed_map_is_treated_as_absent(self, path: Path, content: str) -> None:
        path.write_text(content)

        assert cache(path).load() is None

    def test_a_legacy_file_survives_a_save_for_another_certificate(self, path: Path) -> None:
        legacy = {
            "environment": HOMOLOGACION,
            "service": SERVICE,
            "token": TICKET.token,
            "sign": TICKET.sign,
            "expires_at": TICKET.expires_at.isoformat(),
        }
        path.write_text(json.dumps(legacy))
        other = AccessTicket(token="otro", sign="otra", expires_at=NOW + timedelta(hours=6))  # noqa: S106

        cache(path, certificate="huella-2").save(other)

        assert cache(path, certificate="huella-1").load() == TICKET
        assert cache(path, certificate="huella-2").load() == other

    def test_an_expiry_without_a_timezone_is_treated_as_absent(self, path: Path) -> None:
        """Comparing it with an aware clock would raise, far from here."""
        path.write_text(saved_fields(expires_at="2026-09-25T09:00:00"))

        assert cache(path).load() is None

    @pytest.mark.parametrize(
        "changes",
        [{"token": 123}, {"sign": None}, {"token": ""}, {"expires_at": 20260925}],
        ids=["token-not-text", "sign-null", "token-empty", "expiry-not-text"],
    )
    def test_fields_of_the_wrong_type_are_treated_as_absent(
        self, path: Path, changes: dict[str, object]
    ) -> None:
        path.write_text(saved_fields(**changes))

        assert cache(path).load() is None

    def test_a_corrupt_file_is_treated_as_absent(self, path: Path) -> None:
        path.write_text("{no es json")

        assert cache(path).load() is None

    def test_a_file_missing_fields_is_treated_as_absent(self, path: Path) -> None:
        path.write_text(json.dumps({"environment": HOMOLOGACION, "service": SERVICE}))

        assert cache(path).load() is None
