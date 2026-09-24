"""Assembling the pieces into a registry the graph can use.

Four modules meet here: `wsaa` builds and reads the access ticket, `signing`
signs it with the certificate, `soap` builds the envelopes and sends them, and
`registry` answers the Protocol the graph depends on.

Nothing in this file is clever. It exists so that someone with a certificate
writes one call instead of wiring four, and so the wiring itself is somewhere
it can be read.
"""

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from copiloto.arca.padron import PadronError
from copiloto.arca.registry import ArcaRegistry
from copiloto.arca.signing import signer_from_files
from copiloto.arca.soap import (
    ENDPOINTS,
    build_dummy_envelope,
    build_persona_envelope,
    parse_dummy,
    post_soap,
)
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


def build_registry(
    *,
    cert_path: Path,
    key_path: Path,
    represented_cuit: str,
    environment: str = PRODUCCION,
    passphrase: bytes | None = None,
    post: Post = _default_post,
) -> ArcaRegistry:
    """A registry that looks taxpayers up in ARCA, using your certificate.

    `represented_cuit` is the CUIT whose Administrador de Relaciones delegated
    `ws_sr_constancia_inscripcion` to the certificate's CUIT. Without that
    delegation WSAA answers `coe.notAuthorized`, which is the system working
    as intended.
    """
    sign_cms = signer_from_files(cert_path, key_path, passphrase=passphrase)

    def get_ticket(now: datetime) -> AccessTicket:
        return request_ticket(
            SERVICE,
            sign_cms=sign_cms,
            send=lambda url, cms: post(url, _login_envelope(cms)),
            now=now,
            environment=environment,
        )

    def call_padron(token: str, sign: str, cuit: str) -> str:
        envelope = build_persona_envelope(
            token=token,
            sign=sign,
            cuit_representada=represented_cuit.replace("-", ""),
            id_persona=cuit,
        )
        try:
            return post(ENDPOINTS[environment], envelope)
        except Exception as error:
            raise PadronError(f"La consulta al padrón falló: {error}") from error

    return ArcaRegistry(
        represented_cuit=represented_cuit,
        request_ticket=get_ticket,
        call_padron=call_padron,
    )


def _login_envelope(cms: str) -> str:
    """The `loginCms` call.

    The namespace is the one the WSAA WSDL declares for the element, which is
    not the service's own target namespace. Getting it wrong is a silent way
    to be misunderstood.
    """
    from xml.sax.saxutils import escape  # noqa: PLC0415

    return (
        '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" '
        'xmlns:wsaa="http://wsaa.view.sua.dvadac.desein.afip.gov">'
        f"<soapenv:Header/><soapenv:Body><wsaa:loginCms><in0>{escape(cms)}</in0>"
        "</wsaa:loginCms></soapenv:Body></soapenv:Envelope>"
    )
