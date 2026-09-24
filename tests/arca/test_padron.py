"""Reading a monotributista's category out of ARCA's constancia de inscripción.

The fixtures below are the response examples printed in ARCA's manual for
`ws_sr_constancia_inscripcion`, version 3.4 (08/05/23), trimmed to the parts
this copilot reads. Using the documented responses rather than invented ones
is the whole point: the contract is theirs, not mine.

The one judgement call worth naming: the category arrives twice, as
`idCategoria` (36) and as `descripcionCategoria` ("B LOCACIONES DE SERVICIO").
The numeric id is an internal code and the manual publishes no table for it,
so the letter is read from the description, which carries it as its first
word. Inventing a mapping for `idCategoria` would be guessing.
"""

import pytest

from copiloto.arca.padron import ConstanciaUnavailable, PadronError, parse_persona
from copiloto.models import TaxpayerProfile
from tests.arca.recorded import PERSONA_BLOCKED, PERSONA_MONOTRIBUTISTA
from tests.arca.responses import JURIDICA, MONOTRIBUTISTA, NO_EXISTE, REGIMEN_GENERAL


def found(response: str) -> TaxpayerProfile:
    """Parse a response that must describe a monotributista."""
    profile = parse_persona(response)
    assert profile is not None, "expected a monotributo profile"
    return profile


class TestAMonotributista:
    def test_the_category_is_the_letter_in_the_description(self) -> None:
        assert found(MONOTRIBUTISTA).category == "B"

    def test_the_cuit_comes_back_formatted_the_way_this_project_writes_it(self) -> None:
        """ARCA sends 11 bare digits; everything here uses the dashed form."""
        assert found(MONOTRIBUTISTA).cuit == "27-01594221-0"

    def test_the_name_is_readable(self) -> None:
        assert found(MONOTRIBUTISTA).name == "JAZMIN JAZMIN"


class TestACompany:
    def test_the_razon_social_is_used_as_the_name(self) -> None:
        assert found(JURIDICA).name == "UNA SOCIEDAD SA"

    def test_its_category_is_read_the_same_way(self) -> None:
        assert found(JURIDICA).category == "D"


class TestWhoIsNotAMonotributista:
    def test_a_taxpayer_in_the_general_regime_is_not_one(self) -> None:
        """Not an error: the copilot simply has nothing to say about them."""
        assert parse_persona(REGIMEN_GENERAL) is None

    def test_a_cuit_that_does_not_exist_is_not_one_either(self) -> None:
        """The manual's form of "does not exist". The wire uses a fault."""
        assert parse_persona(NO_EXISTE) is None


class TestWhatTheWireSends:
    """Responses recorded from homologación, not copied from the manual."""

    def test_a_real_monotributista_reads_the_same_as_the_manual_one(self) -> None:
        profile = found(PERSONA_MONOTRIBUTISTA)

        assert (profile.cuit, profile.category) == ("27-01594221-0", "B")

    def test_a_risk_caracterizacion_is_not_mistaken_for_the_category(self) -> None:
        """The same response says "CATEGORÍA A: MUY BAJO RIESGO". That is a
        risk rating, not the monotributo category, which is B."""
        assert "CATEGORÍA A" in PERSONA_MONOTRIBUTISTA
        assert found(PERSONA_MONOTRIBUTISTA).category == "B"


class TestAConstanciaThatCannotBeIssued:
    """The CUIT exists, but ARCA will not certify anything about it.

    Recorded: a CUIT cancelled for not constituting its electronic fiscal
    domicile, whose constancia is also blocked until biometric data is
    registered. Reporting that as "not a monotributista" would hide exactly
    the situation somebody needs to hear about.
    """

    def test_it_is_an_error_not_an_absence(self) -> None:
        with pytest.raises(ConstanciaUnavailable):
            parse_persona(PERSONA_BLOCKED)

    def test_it_carries_every_reason_arca_gave(self) -> None:
        with pytest.raises(ConstanciaUnavailable) as error:
            parse_persona(PERSONA_BLOCKED)

        assert len(error.value.reasons) == 3
        assert any("biométricos" in reason for reason in error.value.reasons)

    def test_the_reasons_are_in_the_message(self) -> None:
        with pytest.raises(ConstanciaUnavailable, match="fue cancelada"):
            parse_persona(PERSONA_BLOCKED)

    def test_it_is_still_a_padron_error(self) -> None:
        """Callers already handling PadronError keep handling this one."""
        with pytest.raises(PadronError):
            parse_persona(PERSONA_BLOCKED)

    def test_a_missing_id_persona_leaves_no_hole_in_the_message(self) -> None:
        response = (
            "<personaReturn><errorConstancia><error>Un motivo</error>"
            "</errorConstancia></personaReturn>"
        )

        with pytest.raises(ConstanciaUnavailable) as error:
            parse_persona(response)

        assert error.value.cuit == ""
        assert "for :" not in str(error.value)
        assert "Un motivo" in str(error.value)

    def test_the_message_keeps_arca_s_words_to_one_bounded_line(self) -> None:
        """The reasons are kept verbatim; the message is what ends up in a log,
        so it is one line and it stops somewhere."""
        long_reason = "linea uno\nlinea dos " + "x" * 5000
        response = (
            "<personaReturn><errorConstancia><idPersona>20111111112</idPersona>"
            f"<error>{long_reason}</error></errorConstancia></personaReturn>"
        )

        with pytest.raises(ConstanciaUnavailable) as error:
            parse_persona(response)

        assert error.value.reasons == (long_reason,)
        assert "\n" not in str(error.value)
        assert len(str(error.value)) < 400


class TestBrokenResponses:
    def test_something_that_is_not_xml_is_an_error(self) -> None:
        with pytest.raises(PadronError):
            parse_persona("no soy xml")

    def test_a_category_description_without_a_letter_is_an_error(self) -> None:
        """Better to stop than to report a category nobody can act on."""
        broken = MONOTRIBUTISTA.replace(
            "B LOCACIONES DE SERVICIO", "SIN CATEGORIA ASIGNADA"
        )

        with pytest.raises(PadronError):
            parse_persona(broken)

    def test_a_category_outside_a_to_k_is_an_error(self) -> None:
        """The scale runs A to K; an M would mean the contract moved."""
        broken = MONOTRIBUTISTA.replace("B LOCACIONES", "M LOCACIONES")

        with pytest.raises(PadronError):
            parse_persona(broken)

    def test_monotributo_data_without_a_category_is_an_error(self) -> None:
        broken = MONOTRIBUTISTA.replace("<categoriaMonotributo>", "<otraCosa>").replace(
            "</categoriaMonotributo>", "</otraCosa>"
        )

        with pytest.raises(PadronError):
            parse_persona(broken)

    def test_an_invalid_cuit_in_the_response_is_an_error(self) -> None:
        """If the check digit fails, something is wrong upstream, not here."""
        broken = MONOTRIBUTISTA.replace("27015942210", "27015942211")

        with pytest.raises(PadronError):
            parse_persona(broken)
