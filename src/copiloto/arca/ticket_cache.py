"""Keeping the WSAA access ticket on disk, so it outlives the process.

WSAA issues one ticket per certificate and service and refuses a second one
with `coe.alreadyAuthenticated` until the first expires, twelve hours later. A
ticket held only in memory dies with the process that asked for it, and the
next process is locked out for the rest of those twelve hours.

The file holds a credential, so three rules:

- It is readable only by its owner, and written through a temporary file
  with a fresh, unpredictable name that replaces the old one in a single
  step. A crash mid-write leaves the previous ticket, never half of one, and
  nobody can plant a path for the credential to be written through.
- It records the environment, the service and the certificate each ticket was
  issued for. WSAA binds a ticket to all three: a homologación ticket is
  refused by production, and one certificate's ticket is refused for another.
  Asking with the wrong one wastes a call against a daily limit.
- One file holds one ticket per environment, service and certificate. Two
  registries sharing a file must not evict each other's ticket, or each
  would keep logging in and being refused.
- Anything in it that cannot be read or does not match is treated as absent.
  The cache may save a login; it must never be the reason one fails.

The first version of this file held a single ticket and did not record the
certificate. Such a file is still read, on the assumption the previous
version made: that it belongs to the one certificate in use. Discarding it
would ask WSAA again and be refused until the ticket expires.
"""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

from copiloto.arca.wsaa import AccessTicket


class TicketCache:
    """One ticket for one environment, service and certificate, in one file.

    `certificate` is any stable identifier of the certificate the ticket was
    requested with; `signing.certificate_fingerprint` is the one the client
    uses.
    """

    def __init__(self, path: Path, *, environment: str, service: str, certificate: str) -> None:
        self._path = path
        self._environment = environment
        self._service = service
        self._certificate = certificate

    def load(self) -> AccessTicket | None:
        """The saved ticket, or None when there is none worth using.

        Expiry is not checked here: whether a ticket is still usable depends
        on the moment of the call, and `AccessTicket.is_valid` decides that.
        """
        tickets = self._read()
        entry = tickets.get(self._key(self._certificate))
        if entry is None:
            # Written before certificates were recorded; see the module note.
            entry = tickets.get(self._key(None))
        return _ticket_from(entry) if entry is not None else None

    def save(self, ticket: AccessTicket) -> None:
        """Record this ticket for this certificate, keeping the others, atomically."""
        tickets = self._read()
        tickets[self._key(self._certificate)] = {
            "token": ticket.token,
            "sign": ticket.sign,
            "expires_at": ticket.expires_at.isoformat(),
        }
        self._write(json.dumps({"tickets": tickets}))

    def _key(self, certificate: str | None) -> str:
        return json.dumps([self._environment, self._service, certificate])

    def _read(self) -> dict[str, object]:
        """Every entry in the file by key, in either format. Unreadable is empty."""
        try:
            saved = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(saved, dict):
            return {}
        tickets = saved.get("tickets")
        if isinstance(tickets, dict):
            return dict(tickets)
        if "token" in saved:
            # The single-ticket format, with or without a certificate.
            key = json.dumps([saved.get("environment"), saved.get("service"), saved.get("certificate")])
            return {key: saved}
        return {}

    def _write(self, payload: str) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # mkstemp picks a name nobody could have planted, creates it with
        # O_EXCL and owner-only permissions from the start, and never follows
        # a symlink. There is no moment the credential is readable by others
        # or written somewhere other than here.
        descriptor, name = tempfile.mkstemp(
            dir=self._path.parent, prefix=f".{self._path.name}.", suffix=".tmp"
        )
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                # On disk before it replaces the old one: a crash right after
                # must find this ticket, not an empty file where it was.
                os.fsync(handle.fileno())
            os.replace(temporary, self._path)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        _fsync_directory(self._path.parent)


def _ticket_from(entry: object) -> AccessTicket | None:
    """A ticket out of one saved entry, or None if any of it is not trustworthy."""
    if not isinstance(entry, dict):
        return None
    token, sign, expires = entry.get("token"), entry.get("sign"), entry.get("expires_at")
    if not isinstance(token, str) or not isinstance(sign, str) or not token or not sign:
        return None
    if not isinstance(expires, str):
        return None
    try:
        expires_at = datetime.fromisoformat(expires)
    except ValueError:
        return None
    if expires_at.tzinfo is None:
        # An aware clock cannot be compared with it; refusing here beats a
        # TypeError in the middle of a lookup.
        return None
    return AccessTicket(token=token, sign=sign, expires_at=expires_at)


def _fsync_directory(directory: Path) -> None:
    """Make the rename itself durable. Not every filesystem allows it; then it is skipped."""
    try:
        descriptor = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)
