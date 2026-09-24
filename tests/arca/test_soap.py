"""The SOAP envelopes, and the one call that needs no certificate.

`dummy` is the only method of the padrón that works without authentication,
which makes it the only part of this client that can be checked against the
live service. The last test does exactly that, against homologación, and is
skipped unless `COPILOTO_ARCA_LIVE=1` asks for it: a test suite must not
depend on a government service being up.

The envelopes are built from the WSDL at
`https://aws.afip.gov.ar/sr-padron/webservices/personaServiceA5?WSDL`, where
`getPersona_v2` takes token, sign, cuitRepresentada and idPersona, the last
two as `xs:long`.
"""

import os

import pytest
from defusedxml import ElementTree

from copiloto.arca.soap import (
    A5_NAMESPACE,
    ENDPOINTS,
    build_dummy_envelope,
    build_persona_envelope,
    parse_dummy,
    parse_fault,
)
from copiloto.arca.wsaa import HOMOLOGACION, PRODUCCION

DUMMY_OK = """<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <ns2:dummyResponse xmlns:ns2="http://a5.soap.ws.server.puc.sr/">
      <return><appserver>OK</appserver><authserver>OK</authserver><dbserver>OK</dbserver></return>
    </ns2:dummyResponse>
  </soap:Body>
</soap:Envelope>"""

DUMMY_DEGRADED = DUMMY_OK.replace("<dbserver>OK</dbserver>", "<dbserver>ERROR</dbserver>")

FAULT = """<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <soap:Fault>
      <faultcode>soap:Server</faultcode>
      <faultstring>Token invalido</faultstring>
    </soap:Fault>
  </soap:Body>
</soap:Envelope>"""


class TestEndpoints:
    def test_production_is_the_documented_url(self) -> None:
        assert ENDPOINTS[PRODUCCION] == (
            "https://aws.afip.gov.ar/sr-padron/webservices/personaServiceA5"
        )

    def test_testing_is_the_other_one(self) -> None:
        assert ENDPOINTS[HOMOLOGACION] == (
            "https://awshomo.afip.gov.ar/sr-padron/webservices/personaServiceA5"
        )


class TestTheDummyEnvelope:
    def test_it_is_valid_xml(self) -> None:
        assert ElementTree.fromstring(build_dummy_envelope()) is not None

    def test_it_uses_the_namespace_from_the_wsdl(self) -> None:
        assert A5_NAMESPACE == "http://a5.soap.ws.server.puc.sr/"
        assert A5_NAMESPACE in build_dummy_envelope()

    def test_it_carries_no_credentials(self) -> None:
        """dummy is the one method that needs none."""
        envelope = build_dummy_envelope()

        assert "token" not in envelope
        assert "sign" not in envelope


class TestThePersonaEnvelope:
    def _envelope(self) -> str:
        return build_persona_envelope(
            token="un-token", sign="una-firma",  # noqa: S106
            cuit_representada="20111111112", id_persona="27015942210",
        )

    def test_it_is_valid_xml(self) -> None:
        assert ElementTree.fromstring(self._envelope()) is not None

    def test_it_calls_the_method_the_manual_recommends(self) -> None:
        """getPersona still exists for compatibility; _v2 is the current one."""
        assert "getPersona_v2" in self._envelope()

    def test_it_carries_the_four_documented_parameters(self) -> None:
        envelope = self._envelope()

        for parameter in ("token", "sign", "cuitRepresentada", "idPersona"):
            assert f"<{parameter}>" in envelope

    def test_the_cuits_travel_as_bare_digits(self) -> None:
        """The WSDL types them as xs:long, so no dashes."""
        envelope = self._envelope()

        assert "<cuitRepresentada>20111111112</cuitRepresentada>" in envelope
        assert "<idPersona>27015942210</idPersona>" in envelope

    def test_a_cuit_with_separators_is_refused(self) -> None:
        with pytest.raises(ValueError, match="d.gitos"):
            build_persona_envelope(
                token="t", sign="s",  # noqa: S106
                cuit_representada="20-11111111-2", id_persona="27015942210",
            )

    def test_the_credentials_are_escaped(self) -> None:
        """A token is base64 and can carry characters XML cares about."""
        envelope = build_persona_envelope(
            token="a<b&c", sign="s", cuit_representada="20111111112",  # noqa: S106
            id_persona="27015942210",
        )

        assert "a<b&c" not in envelope
        assert ElementTree.fromstring(envelope) is not None


class TestParsingTheDummy:
    def test_everything_ok_is_reported_as_ok(self) -> None:
        assert parse_dummy(DUMMY_OK) == {
            "appserver": "OK", "authserver": "OK", "dbserver": "OK"
        }

    def test_a_degraded_component_is_visible(self) -> None:
        assert parse_dummy(DUMMY_DEGRADED)["dbserver"] == "ERROR"


class TestParsingAFault:
    def test_a_fault_is_reported_with_its_message(self) -> None:
        assert parse_fault(FAULT) == "Token invalido"

    def test_a_normal_response_carries_no_fault(self) -> None:
        assert parse_fault(DUMMY_OK) is None


@pytest.mark.skipif(
    os.environ.get("COPILOTO_ARCA_LIVE") != "1",
    reason="set COPILOTO_ARCA_LIVE=1 to call ARCA's testing environment",
)
class TestAgainstTheLiveService:
    """The only call this client can make without being a registered CEE."""

    def test_homologacion_answers_the_documented_shape(self) -> None:
        from urllib.request import Request, urlopen

        request = Request(  # noqa: S310  (a constant https URL from the manual)
            ENDPOINTS[HOMOLOGACION],
            data=build_dummy_envelope().encode("utf-8"),
            headers={"Content-Type": "text/xml;charset=UTF-8", "SOAPAction": '""'},
        )
        with urlopen(request, timeout=30) as response:  # noqa: S310
            body = response.read().decode("utf-8")

        status = parse_dummy(body)

        assert set(status) == {"appserver", "authserver", "dbserver"}
