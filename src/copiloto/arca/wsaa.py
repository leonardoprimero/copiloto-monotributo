"""Getting an access ticket from ARCA's authentication service.

Every method of the padrón service except `dummy` needs a `token` and a `sign`.
They come from WSAA, and the price of admission is an X.509 certificate issued
by ARCA's certifying authority: you build a small XML request, sign it as a
CMS message with your private key, and send it base64-encoded.

Everything in this module follows ARCA's "Especificación Técnica del
WebService de Autenticación y Autorización" version 1.2.2. Three rules from it
shape the code and are worth stating out loud:

- A ticket is valid for twelve hours, and the spec says to keep using it while
  it lasts. Asking for another one is not merely wasteful: the service answers
  `coe.alreadyAuthenticated`, which is an error. Caching is mandatory.
- `generationTime` may be up to 24 hours in the past and `expirationTime` up
  to 24 hours in the future. Outside that the request is rejected, and a
  machine with a wrong clock is the usual reason.
- The certificate is the caller's own. The taxpayer never hands over their
  clave fiscal; they delegate the service to this CUIT from their own
  Administrador de Relaciones, and can revoke it the same way.

Signing and transport arrive as arguments. That keeps this module free of
cryptography and sockets, and it is what makes the rules above testable.
"""

import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from xml.sax.saxutils import escape

from defusedxml import ElementTree

# The DN of each WSAA, from the specification. They differ only in the CN.
PRODUCCION = "produccion"
HOMOLOGACION = "homologacion"

_DESTINATIONS = {
    PRODUCCION: "cn=wsaa,o=afip,c=ar,serialNumber=CUIT 33693450239",
    HOMOLOGACION: "cn=wsaahomo,o=afip,c=ar,serialNumber=CUIT 33693450239",
}

_ENDPOINTS = {
    PRODUCCION: "https://wsaa.afip.gov.ar/ws/services/LoginCms",
    HOMOLOGACION: "https://wsaahomo.afip.gov.ar/ws/services/LoginCms",
}

# Comfortably inside the documented 24-hour tolerance on both sides, and long
# enough that a slow round trip does not arrive expired.
_BACKDATE = timedelta(minutes=10)
_VALID_FOR = timedelta(hours=10)

# A ticket about to expire will expire mid-request. Treat the last minute of
# its life as already gone.
_EXPIRY_MARGIN = timedelta(minutes=1)

# The namespace the WSAA WSDL declares for the `loginCms` element, which is
# not the service's own target namespace. Getting it wrong is a silent way to
# be misunderstood.
_LOGIN_NAMESPACE = "http://wsaa.view.sua.dvadac.desein.afip.gov"

SignCms = Callable[[str], str]
Send = Callable[[str, str], str]


class WsaaError(RuntimeError):
    """The authentication service refused, or answered something unusable."""


@dataclass(frozen=True, slots=True)
class AccessTicket:
    """The `token` and `sign` every padrón call has to carry."""

    token: str
    sign: str
    expires_at: datetime

    def is_valid(self, *, at: datetime) -> bool:
        """Whether this ticket can still be used, with a margin for the trip."""
        return at + _EXPIRY_MARGIN < self.expires_at


def build_tra(
    service: str, *, now: datetime, environment: str = PRODUCCION
) -> str:
    """The `LoginTicketRequest.xml` for one service, ready to be signed."""
    if environment not in _DESTINATIONS:
        raise WsaaError(f"Unknown environment {environment!r}.")

    # uniqueId is an unsigned 32-bit integer that, with generationTime,
    # identifies the request. Random rather than a counter so two processes
    # sharing a certificate do not collide.
    unique_id = secrets.randbelow(2**32)

    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<loginTicketRequest version="1.0">'
        "<header>"
        f"<destination>{_DESTINATIONS[environment]}</destination>"
        f"<uniqueId>{unique_id}</uniqueId>"
        f"<generationTime>{(now - _BACKDATE).isoformat()}</generationTime>"
        f"<expirationTime>{(now + _VALID_FOR).isoformat()}</expirationTime>"
        "</header>"
        f"<service>{service}</service>"
        "</loginTicketRequest>"
    )


def build_login_envelope(cms: str) -> str:
    """The `loginCms` SOAP call carrying one signed request."""
    return (
        '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" '
        f'xmlns:wsaa="{_LOGIN_NAMESPACE}">'
        f"<soapenv:Header/><soapenv:Body><wsaa:loginCms><in0>{escape(cms)}</in0>"
        "</wsaa:loginCms></soapenv:Body></soapenv:Envelope>"
    )


def parse_login_response(envelope_xml: str) -> AccessTicket:
    """Read the ticket out of what `loginCms` actually answers.

    The specification describes `LoginTicketResponse.xml` and its example is
    that bare document. On the wire it arrives as the escaped text of
    `loginCmsReturn`: a document inside a string inside an envelope. Reading
    it as elements finds nothing, and by then ARCA has already issued a ticket
    it will not issue again until this one expires.
    """
    try:
        root = ElementTree.fromstring(envelope_xml)
    except Exception as error:
        raise WsaaError(f"WSAA answered something that is not XML: {error}") from error

    found = root.find(f".//{{{_LOGIN_NAMESPACE}}}loginCmsReturn")
    if found is None or not found.text:
        raise WsaaError("The WSAA response has no loginCmsReturn to read the ticket from.")
    return parse_ticket(found.text)


def parse_ticket(response_xml: str) -> AccessTicket:
    """Read the credentials out of a `LoginTicketResponse.xml`."""
    try:
        root = ElementTree.fromstring(response_xml)
    except Exception as error:
        raise WsaaError(f"WSAA answered something that is not XML: {error}") from error

    def required(name: str) -> str:
        found = root.find(f".//{name}")
        if found is None or not found.text:
            raise WsaaError(f"The WSAA response has no <{name}>.")
        return found.text.strip()

    return AccessTicket(
        token=required("token"),
        sign=required("sign"),
        expires_at=datetime.fromisoformat(required("expirationTime")),
    )


def request_ticket(
    service: str,
    *,
    sign_cms: SignCms,
    send: Send,
    now: datetime,
    environment: str = PRODUCCION,
) -> AccessTicket:
    """Build, sign, send and read back one access ticket.

    `sign_cms` turns the request into a base64 CMS message and `send` posts an
    envelope and returns the raw answer, so this function stays pure enough to
    test without a certificate or a socket.
    """
    tra = build_tra(service, now=now, environment=environment)
    try:
        response = send(_ENDPOINTS[environment], build_login_envelope(sign_cms(tra)))
    except WsaaError:
        raise
    except Exception as error:
        # The specification's fault codes (coe.notAuthorized, cms.cert.expired,
        # xml.generationTime.invalid...) are the useful part of a refusal, so
        # they travel intact instead of being flattened into "request failed".
        raise WsaaError(f"WSAA refused the request: {error}") from error

    return parse_login_response(response)
