"""Keeping the WSAA access ticket on disk, so it outlives the process.

WSAA issues one ticket per certificate and service and refuses a second one
with `coe.alreadyAuthenticated` until the first expires, twelve hours later. A
ticket held only in memory dies with the process that asked for it, and the
next process is locked out for the rest of those twelve hours.

The file holds a credential, so three rules:

- It is readable only by its owner, and written through a temporary file
  that replaces the old one in a single step. A crash mid-write leaves the
  previous ticket, never half of one.
- It records the environment and the service it was issued for. A
  homologación ticket is refused by production, and asking with it wastes a
  call against a daily limit.
- Anything in it that cannot be read or does not match is treated as absent.
  The cache may save a login; it must never be the reason one fails.
"""

import json
import os
from datetime import datetime
from pathlib import Path

from copiloto.arca.wsaa import AccessTicket


class TicketCache:
    """One ticket for one environment and service, kept in one file."""

    def __init__(self, path: Path, *, environment: str, service: str) -> None:
        self._path = path
        self._environment = environment
        self._service = service

    def load(self) -> AccessTicket | None:
        """The saved ticket, or None when there is none worth using.

        Expiry is not checked here: whether a ticket is still usable depends
        on the moment of the call, and `AccessTicket.is_valid` decides that.
        """
        try:
            saved = json.loads(self._path.read_text(encoding="utf-8"))
            if saved["environment"] != self._environment or saved["service"] != self._service:
                return None
            return AccessTicket(
                token=saved["token"],
                sign=saved["sign"],
                expires_at=datetime.fromisoformat(saved["expires_at"]),
            )
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def save(self, ticket: AccessTicket) -> None:
        """Replace whatever was saved with this ticket, atomically."""
        payload = json.dumps(
            {
                "environment": self._environment,
                "service": self._service,
                "token": ticket.token,
                "sign": ticket.sign,
                "expires_at": ticket.expires_at.isoformat(),
            }
        )
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_name(f".{self._path.name}.tmp")
        # Created with owner-only permissions from the start, rather than
        # written and then restricted, so there is no moment it is readable.
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(payload)
            os.replace(temporary, self._path)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
