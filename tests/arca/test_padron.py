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

from copiloto.arca.padron import PadronError, parse_persona
from copiloto.models import TaxpayerProfile
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
        assert parse_persona(NO_EXISTE) is None


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
