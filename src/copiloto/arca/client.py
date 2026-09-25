"""Assembling the pieces into a registry the graph can use.

Four modules meet here: `wsaa` builds and reads the access ticket, `signing`
signs it with the certificate, `soap` builds the envelopes and sends them, and
`registry` answers the Protocol the graph depends on.

Nothing in this file is clever. It exists so that someone with a certificate
writes one call instead of wiring four, and so the wiring itself is somewhere
it can be read.
"""

import os
import warnings
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from copiloto.arca.padron import NOT_FOUND, PadronError, PersonNotFound
from copiloto.arca.registry import ArcaRegistry, utc_now
from copiloto.arca.signing import certificate_fingerprint, load_signer, sign_tra
from copiloto.arca.soap import (
    ENDPOINTS,
    SoapError,
    build_dummy_envelope,
    build_persona_envelope,
    parse_dummy,
    post_soap,
)
from copiloto.arca.ticket_cache import TicketCache
from copiloto.arca.wsaa import PRODUCCION, AccessTicket, request_ticket

SERVICE = "ws_sr_constancia_inscripcion"

Post = Callable[[str, str], str]


def _default_post(url: str, envelope: str) -> str:
    return post_soap(url, envelope)


def service_status(
    environment: str = PRODUCCION, *, post: Post = _default_post
) -> dict[str, str]:
    """Ask the padrón whether it is up. The one call that needs no certificate.

    Returns the three components ARCA reports, each "OK" or "ERROR". Useful
    before blaming your own certificate for a failure.
    """
    return parse_dummy(post(ENDPOINTS[environment], build_dummy_envelope()))


def _says_not_found(fault: str) -> bool:
    """Whether a fault is ARCA's "no such person", read the way a person would.

    The exact wording was recorded from the live service once. Case, spacing
    and a trailing period are the kind of thing that drifts, and treating the
    drifted version as a failure would turn "unknown CUIT" into an error.
    """
    return _normalised(fault) == _normalised(NOT_FOUND)


def _normalised(text: str) -> str:
    return " ".join(text.split()).rstrip(".").casefold()


def default_ticket_cache_path() -> Path:
    """The default path to persist WSAA tickets for CLI and Web.

    Respects XDG_CACHE_HOME if set, otherwise ~/.cache/copiloto/tickets.json.
    """
    cache_home = os.environ.get("XDG_CACHE_HOME")
    base = Path(cache_home) if cache_home else Path.home() / ".cache"
    return base / "copiloto" / "tickets.json"


def build_registry(
    *,
    cert_path: Path,
    key_path: Path,
    represented_cuit: str,
    environment: str = PRODUCCION,
    passphrase: bytes | None = None,
    post: Post = _default_post,
    clock: Callable[[], datetime] = utc_now,
    ticket_cache: Path | None = None,
) -> ArcaRegistry:
    """A registry that looks taxpayers up in ARCA, using your certificate.

    `represented_cuit` is the CUIT whose Administrador de Relaciones delegated
    `ws_sr_constancia_inscripcion` to the certificate's CUIT. Without that
    delegation WSAA answers `coe.notAuthorized`, which is the system working
    as intended.

    `ticket_cache` is a file to keep the access ticket in. Without one, the
    ticket lives as long as this registry, and a second process started
    within twelve hours is refused with `coe.alreadyAuthenticated`.
    """
    certificate, key = load_signer(cert_path, key_path, passphrase=passphrase)

    def sign_cms(tra: str) -> str:
        return sign_tra(tra, certificate, key)

    cache = (
        TicketCache(
            ticket_cache,
            environment=environment,
            service=SERVICE,
            certificate=certificate_fingerprint(certificate),
        )
        if ticket_cache is not None
        else None
    )

    def get_ticket(now: datetime) -> AccessTicket:
        saved = cache.load() if cache is not None else None
        if saved is not None and saved.is_valid(at=now):
            return saved

        ticket = request_ticket(
            SERVICE,
            sign_cms=sign_cms,
            send=post,
            now=now,
            environment=environment,
        )
        if cache is not None:
            # WSAA has already issued this ticket and will not issue another for
            # twelve hours. A cache that cannot be written must not lose it.
            try:
                cache.save(ticket, now=now)
            except OSError as error:
                warnings.warn(
                    f"The access ticket could not be saved to {ticket_cache}: {error}. "
                    "It stays in memory, but a new process will be locked out until it expires.",
                    RuntimeWarning,
                    stacklevel=2,
                )
        return ticket

    def call_padron(token: str, sign: str, cuit: str) -> str:
        envelope = build_persona_envelope(
            token=token,
            sign=sign,
            cuit_representada=represented_cuit.replace("-", ""),
            id_persona=cuit,
        )
        try:
            return post(ENDPOINTS[environment], envelope)
        except SoapError as error:
            # The live service says "does not exist" with a fault, not with the
            # errorConstancia the manual shows. It is an answer, not a failure.
            if _says_not_found(str(error)):
                raise PersonNotFound(cuit) from error
            raise PadronError(f"La consulta al padrón falló: {error}") from error
        except Exception as error:
            raise PadronError(f"La consulta al padrón falló: {error}") from error

    return ArcaRegistry(
        represented_cuit=represented_cuit,
        request_ticket=get_ticket,
        call_padron=call_padron,
        clock=clock,
    )

