"""The access ticket half of talking to ARCA.

Every method of the padrón service except `dummy` needs a `token` and a `sign`
that come from WSAA. Getting them means signing an XML request with an X.509
certificate, and the rules below are not invented: they come from ARCA's
"Especificación Técnica del WebService de Autenticación y Autorización"
version 1.2.2, and each test names the rule it pins.

Nothing here talks to ARCA. The signing and the transport are injected, which
is what lets the rules be tested at all.
"""

from datetime import UTC, datetime, timedelta

import pytest

from copiloto.arca.wsaa import (
    HOMOLOGACION,
    PRODUCCION,
    AccessTicket,
    WsaaError,
    build_tra,
    parse_login_response,
    parse_ticket,
    request_ticket,
)
from tests.arca.recorded import (
    LOGIN_CMS_RESPONSE,
    LOGIN_EXPIRES,
    LOGIN_SIGN,
    LOGIN_TOKEN,
)

# The example response from the technical specification, section "Extracción y
# validación del TA", with the dates written as the XSD requires.
TA_XML = """<?xml version="1.0" encoding="UTF-8"?>
<loginTicketResponse version="1.0">
  <header>
    <source>cn=wsaa,o=afip,c=ar,serialNumber=CUIT 33693450239</source>
    <destination>cn=srv1,ou=facturacion,o=empresa s.a.,c=ar,serialNumber=CUIT 30123456789</destination>
    <uniqueId>383953094</uniqueId>
    <generationTime>2001-12-31T12:00:02-03:00</generationTime>
    <expirationTime>2002-01-01T00:00:02-03:00</expirationTime>
  </header>
  <credentials>
    <token>cES0SSuWIIPlfe5/dLtb0Qeg2jQuvYuuSEDOrz+w2EnAQiEeS86gzYf7ehiU3UaYit5FRb9z/3zq</token>
    <sign>a6QSSZBgLf0TTcktSNteeSg3qXsMVjo/F5py/Gtw7xucTrUWbsrVCdIoGE8Cm1bixpuVPlr58k6n</sign>
  </credentials>
</loginTicketResponse>"""

NOW = datetime(2026, 9, 24, 10, 0, tzinfo=UTC)


class TestBuildTra:
    def test_it_names_the_service_being_asked_for(self) -> None:
        tra = build_tra("ws_sr_constancia_inscripcion", now=NOW)

        assert "<service>ws_sr_constancia_inscripcion</service>" in tra

    def test_production_destination_is_the_documented_dn(self) -> None:
        """Spec: "cn=wsaa,o=afip,c=ar,serialNumber=CUIT 33693450239"."""
        tra = build_tra("ws_sr_constancia_inscripcion", now=NOW, environment=PRODUCCION)

        assert "cn=wsaa,o=afip,c=ar,serialNumber=CUIT 33693450239" in tra

    def test_testing_destination_is_the_other_documented_dn(self) -> None:
        tra = build_tra("ws_sr_constancia_inscripcion", now=NOW, environment=HOMOLOGACION)

        assert "cn=wsaahomo,o=afip,c=ar,serialNumber=CUIT 33693450239" in tra

    def test_the_times_sit_inside_the_accepted_tolerance(self) -> None:
        """Spec: generation up to 24h back, expiration up to 24h forward."""
        tra = build_tra("ws_sr_constancia_inscripcion", now=NOW)

        generated = datetime.fromisoformat(_tag(tra, "generationTime"))
        expires = datetime.fromisoformat(_tag(tra, "expirationTime"))

        assert NOW - timedelta(hours=24) < generated <= NOW
        assert NOW < expires < NOW + timedelta(hours=24)

    def test_the_request_is_not_stale_the_moment_it_is_built(self) -> None:
        tra = build_tra("ws_sr_constancia_inscripcion", now=NOW)

        assert datetime.fromisoformat(_tag(tra, "expirationTime")) > NOW

    def test_two_requests_are_told_apart(self) -> None:
        """Spec: uniqueId plus generationTime identify the requirement."""
        first = build_tra("ws_sr_constancia_inscripcion", now=NOW)
        second = build_tra("ws_sr_constancia_inscripcion", now=NOW)

        assert _tag(first, "uniqueId") != _tag(second, "uniqueId")

    def test_the_unique_id_fits_in_the_documented_field(self) -> None:
        """Spec: unsigned 32-bit integer."""
        unique = int(_tag(build_tra("ws_sr_constancia_inscripcion", now=NOW), "uniqueId"))

        assert 0 <= unique <= 2**32 - 1

    def test_it_is_parseable_xml(self) -> None:
        from defusedxml import ElementTree

        root = ElementTree.fromstring(build_tra("ws_sr_constancia_inscripcion", now=NOW))

        assert root.tag == "loginTicketRequest"


class TestParseTicket:
    def test_it_reads_the_credentials(self) -> None:
        ticket = parse_ticket(TA_XML)

        assert ticket.token.startswith("cES0SSuWIIPlfe5")
        assert ticket.sign.startswith("a6QSSZBgLf0TTckt")

    def test_it_reads_when_the_ticket_stops_being_valid(self) -> None:
        ticket = parse_ticket(TA_XML)

        assert ticket.expires_at == datetime.fromisoformat("2002-01-01T00:00:02-03:00")

    def test_a_response_without_credentials_is_an_error(self) -> None:
        with pytest.raises(WsaaError):
            parse_ticket("<loginTicketResponse><header/></loginTicketResponse>")

    def test_something_that_is_not_xml_is_an_error(self) -> None:
        with pytest.raises(WsaaError):
            parse_ticket("no soy xml")


class TestParseLoginResponse:
    """What WSAA actually sends, recorded from homologación.

    The ticket does not arrive as XML elements. It arrives as the escaped text
    of `loginCmsReturn`, a document inside a string inside an envelope.
    Reading it as elements finds nothing, and by then ARCA has already issued
    a ticket it will not issue again for twelve hours.
    """

    def test_it_reads_the_credentials_out_of_the_envelope(self) -> None:
        ticket = parse_login_response(LOGIN_CMS_RESPONSE)

        assert (ticket.token, ticket.sign) == (LOGIN_TOKEN, LOGIN_SIGN)

    def test_it_reads_when_the_ticket_expires(self) -> None:
        ticket = parse_login_response(LOGIN_CMS_RESPONSE)

        assert ticket.expires_at == datetime.fromisoformat(LOGIN_EXPIRES)

    def test_an_envelope_without_a_login_return_is_an_error(self) -> None:
        envelope = LOGIN_CMS_RESPONSE.replace("loginCmsReturn", "otraCosa")

        with pytest.raises(WsaaError, match="loginCmsReturn"):
            parse_login_response(envelope)

    def test_something_that_is_not_xml_is_an_error(self) -> None:
        with pytest.raises(WsaaError):
            parse_login_response("no soy xml")


class TestAccessTicketExpiry:
    def _ticket(self, expires_at: datetime) -> AccessTicket:
        return AccessTicket(token="un-token", sign="una-firma", expires_at=expires_at)  # noqa: S106

    def test_a_ticket_in_the_future_is_usable(self) -> None:
        assert self._ticket(NOW + timedelta(hours=6)).is_valid(at=NOW) is True

    def test_a_ticket_already_past_is_not(self) -> None:
        assert self._ticket(NOW - timedelta(minutes=1)).is_valid(at=NOW) is False

    def test_it_is_retired_before_it_actually_expires(self) -> None:
        """A ticket valid for five more seconds expires mid-request."""
        assert self._ticket(NOW + timedelta(seconds=5)).is_valid(at=NOW) is False


class TestRequestTicket:
    """The flow: build, sign, send, parse — with signing and transport injected."""

    def test_it_returns_the_ticket_the_service_handed_back(self) -> None:
        ticket = request_ticket(
            "ws_sr_constancia_inscripcion",
            sign_cms=lambda tra: f"firmado:{tra}",
            send=lambda _url, _cms: LOGIN_CMS_RESPONSE,
            now=NOW,
        )

        assert ticket.token == LOGIN_TOKEN

    def test_what_gets_signed_is_the_request_that_was_built(self) -> None:
        signed: list[str] = []

        request_ticket(
            "ws_sr_constancia_inscripcion",
            sign_cms=lambda tra: signed.append(tra) or "cms",
            send=lambda _url, _cms: LOGIN_CMS_RESPONSE,
            now=NOW,
        )

        assert "<service>ws_sr_constancia_inscripcion</service>" in signed[0]

    def test_it_posts_the_signed_message_to_the_documented_endpoint(self) -> None:
        sent: list[tuple[str, str]] = []

        request_ticket(
            "ws_sr_constancia_inscripcion",
            sign_cms=lambda _tra: "el-cms-firmado",
            send=lambda url, body: sent.append((url, body)) or LOGIN_CMS_RESPONSE,
            now=NOW,
            environment=PRODUCCION,
        )

        [(url, body)] = sent
        assert url == "https://wsaa.afip.gov.ar/ws/services/LoginCms"
        assert "<in0>el-cms-firmado</in0>" in body

    def test_the_signed_message_travels_in_the_login_cms_element(self) -> None:
        """The WSDL puts `loginCms` in its own namespace, not the service's."""
        sent: list[str] = []

        request_ticket(
            "ws_sr_constancia_inscripcion",
            sign_cms=lambda _tra: "cms",
            send=lambda _url, body: sent.append(body) or LOGIN_CMS_RESPONSE,
            now=NOW,
        )

        from defusedxml import ElementTree

        call = ElementTree.fromstring(sent[0]).find(
            ".//{http://wsaa.view.sua.dvadac.desein.afip.gov}loginCms/in0"
        )
        assert call is not None and call.text == "cms"

    def test_the_testing_environment_has_its_own_endpoint(self) -> None:
        sent: list[str] = []

        request_ticket(
            "ws_sr_constancia_inscripcion",
            sign_cms=lambda _tra: "cms",
            send=lambda url, _cms: sent.append(url) or LOGIN_CMS_RESPONSE,
            now=NOW,
            environment=HOMOLOGACION,
        )

        assert sent == ["https://wsaahomo.afip.gov.ar/ws/services/LoginCms"]

    def test_a_refusal_from_arca_is_reported_with_its_code(self) -> None:
        """The spec's fault codes are the useful part of a failure."""

        def refuse(_url: str, _cms: str) -> str:
            raise RuntimeError("coe.notAuthorized: CEE no autorizado")

        with pytest.raises(WsaaError) as error:
            request_ticket(
                "ws_sr_constancia_inscripcion",
                sign_cms=lambda _tra: "cms",
                send=refuse,
                now=NOW,
            )

        assert "coe.notAuthorized" in str(error.value)


def _tag(xml: str, name: str) -> str:
    from defusedxml import ElementTree

    found = ElementTree.fromstring(xml).find(f".//{name}")
    assert found is not None and found.text
    return found.text
