"""The SOAP envelopes for the padrón service.

Built from the WSDL published at
`https://aws.afip.gov.ar/sr-padron/webservices/personaServiceA5?WSDL`, which
declares five operations — `getPersona`, `getPersonaList`, `getPersona_v2`,
`getPersonaList_v2` and `dummy` — and types `getPersona_v2` as taking `token`
and `sign` as `xs:string` and `cuitRepresentada` and `idPersona` as `xs:long`.
The last two are why CUITs travel here as bare digits.

Building the envelope is separate from sending it. The shape is the part that
is easy to get wrong and easy to check; the sending is HTTP, with timeouts and
retries that belong to whoever deploys this, not to a library.

`dummy` is worth its own function: the manual says it is the one method that
needs no authentication, which makes it the only thing here that can be
verified against the live service by someone without a certificate.
"""

from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from xml.sax.saxutils import escape

from defusedxml import ElementTree

from copiloto.arca.wsaa import HOMOLOGACION, PRODUCCION

A5_NAMESPACE = "http://a5.soap.ws.server.puc.sr/"

ENDPOINTS = {
    PRODUCCION: "https://aws.afip.gov.ar/sr-padron/webservices/personaServiceA5",
    HOMOLOGACION: "https://awshomo.afip.gov.ar/sr-padron/webservices/personaServiceA5",
}

_ENVELOPE = (
    '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" '
    f'xmlns:a5="{A5_NAMESPACE}">'
    "<soapenv:Header/><soapenv:Body>{body}</soapenv:Body>"
    "</soapenv:Envelope>"
)


def build_dummy_envelope() -> str:
    """The health check. Carries no credentials, because it needs none."""
    return _ENVELOPE.format(body="<a5:dummy/>")


def build_persona_envelope(
    *, token: str, sign: str, cuit_representada: str, id_persona: str
) -> str:
    """A `getPersona_v2` call for one CUIT.

    `getPersona` still exists for compatibility, but the manual asks for the
    `_v2` methods, which include every monotributo activity and the current
    caracterizaciones.
    """
    for name, value in (("cuitRepresentada", cuit_representada), ("idPersona", id_persona)):
        if not value.isdigit():
            raise ValueError(f"{name} tiene que ser solo dígitos, sin separadores: {value!r}")

    body = (
        "<a5:getPersona_v2>"
        f"<token>{escape(token)}</token>"
        f"<sign>{escape(sign)}</sign>"
        f"<cuitRepresentada>{cuit_representada}</cuitRepresentada>"
        f"<idPersona>{id_persona}</idPersona>"
        "</a5:getPersona_v2>"
    )
    return _ENVELOPE.format(body=body)


def parse_dummy(response_xml: str) -> dict[str, str]:
    """The three components' status, each "OK" or "ERROR"."""
    root = ElementTree.fromstring(response_xml)
    return {
        name: (found.text or "").strip()
        for name in ("appserver", "authserver", "dbserver")
        if (found := root.find(f".//{name}")) is not None
    }


def parse_fault(response_xml: str) -> str | None:
    """The SOAP fault message, or None when the response is a normal one."""
    root = ElementTree.fromstring(response_xml)
    found = root.find(".//faultstring")
    return found.text.strip() if found is not None and found.text else None


class SoapError(RuntimeError):
    """The service refused the call, or could not be reached."""


def post_soap(url: str, envelope: str, *, timeout: float = 30) -> str:
    """Send one envelope and return the body, turning faults into errors.

    A deliberately plain default. It has one timeout and no retries, because
    retry policy depends on what is around it — and because ARCA's own
    specification asks callers not to retry after most failures until the
    cause is fixed. Pass your own transport when you need more.
    """
    if not url.startswith("https://"):
        raise SoapError(f"Refusing to send credentials over {url!r}.")

    request = Request(  # noqa: S310  (guarded above)
        url,
        data=envelope.encode("utf-8"),
        headers={"Content-Type": "text/xml;charset=UTF-8", "SOAPAction": '""'},
    )
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310
            return response.read().decode("utf-8")
    except HTTPError as error:
        # A SOAP fault arrives as a 500 with the reason in the body, and that
        # reason is the useful part: "Certificado no emitido por AC de
        # confianza" says something a stack trace never would.
        fault = parse_fault(error.read().decode("utf-8", errors="replace"))
        raise SoapError(fault or f"HTTP {error.code}") from error
    except URLError as error:
        raise SoapError(f"No pude llegar a {url}: {error.reason}") from error
