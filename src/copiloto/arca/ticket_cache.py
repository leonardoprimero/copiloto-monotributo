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
- It records the environment, the service and the certificate it was issued
  for. WSAA binds a ticket to all three: a homologación ticket is refused by
  production, and one certificate's ticket is refused for another. Asking
  with the wrong one wastes a call against a daily limit.
- Anything in it that cannot be read or does not match is treated as absent.
  The cache may save a login; it must never be the reason one fails.
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
        try:
            saved = json.loads(self._path.read_text(encoding="utf-8"))
            issued_for = (saved["environment"], saved["service"], saved["certificate"])
            if issued_for != (self._environment, self._service, self._certificate):
                return None
            token, sign = saved["token"], saved["sign"]
            if not isinstance(token, str) or not isinstance(sign, str) or not token or not sign:
                return None
            expires_at = datetime.fromisoformat(saved["expires_at"])
            if expires_at.tzinfo is None:
                # An aware clock cannot be compared with it; refusing here
                # beats a TypeError in the middle of a lookup.
                return None
            return AccessTicket(token=token, sign=sign, expires_at=expires_at)
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def save(self, ticket: AccessTicket) -> None:
        """Replace whatever was saved with this ticket, atomically."""
        payload = json.dumps(
            {
                "environment": self._environment,
                "service": self._service,
                "certificate": self._certificate,
                "token": ticket.token,
                "sign": ticket.sign,
                "expires_at": ticket.expires_at.isoformat(),
            }
        )
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
