"""Reading a taxpayer's registered category out of ARCA's constancia.

The service is `ws_sr_constancia_inscripcion`, documented in ARCA's manual for
developers version 3.4 (08/05/23). It returns a `personaReturn` carrying
`datosGenerales`, and then `datosMonotributo` or `datosRegimenGeneral`
depending on what the taxpayer is, or an `errorConstancia` when the CUIT does
not exist.

The copilot reads exactly one thing from all of that: the letter of the
monotributo category. The rest is somebody's fiscal profile and is none of its
business, so it is not stored, not logged and not passed on.

One judgement call, stated because it is the kind of thing that rots quietly:
the category arrives twice, as `idCategoria` (a number, 36 in the manual's
example) and as `descripcionCategoria` ("B LOCACIONES DE SERVICIO"). The
manual publishes no table for the numeric id, so the letter is read from the
description, where it is the first word. A mapping for `idCategoria` would be
a guess, and a guess about somebody's category is exactly what this project
refuses to make.
"""

import re

from defusedxml import ElementTree

from copiloto.cuit import is_valid_cuit, normalize_cuit
from copiloto.models import TaxpayerProfile

# The scale runs A to K. A description that starts with anything else means
# the published contract moved, and guessing past that helps nobody.
_CATEGORY = re.compile(r"^([A-K])\b")


class PadronError(RuntimeError):
    """The padrón answered something this copilot cannot read."""


def _formatted_cuit(digits: str) -> str:
    """ARCA sends eleven bare digits; everything here uses the dashed form."""
    if not is_valid_cuit(digits):
        raise PadronError(f"The padrón returned a CUIT that fails its check digit: {digits}")
    clean = normalize_cuit(digits)
    return f"{clean[:2]}-{clean[2:10]}-{clean[10]}"


def _category_letter(description: str) -> str:
    found = _CATEGORY.match(description.strip())
    if not found:
        raise PadronError(
            f"The category {description!r} does not start with a letter from A to K, "
            "so the copilot cannot tell which one it is."
        )
    return found.group(1)


def parse_persona(response_xml: str) -> TaxpayerProfile | None:
    """The taxpayer's monotributo profile, or None if they are not in it.

    Returns None rather than raising for the two ordinary cases: a CUIT that
    does not exist, and somebody registered in the régimen general. Neither is
    a failure, and neither is something this copilot has anything to say about.
    """
    try:
        root = ElementTree.fromstring(response_xml)
    except Exception as error:
        raise PadronError(f"The padrón answered something that is not XML: {error}") from error

    if root.find(".//errorConstancia") is not None:
        return None

    monotributo = root.find(".//datosMonotributo")
    if monotributo is None:
        return None

    category_node = monotributo.find(".//categoriaMonotributo/descripcionCategoria")
    if category_node is None or not category_node.text:
        raise PadronError(
            "The response carries datosMonotributo without a categoriaMonotributo, "
            "so there is no category to report."
        )

    generales = root.find(".//datosGenerales")
    if generales is None:
        raise PadronError("The response has no datosGenerales.")

    return TaxpayerProfile(
        cuit=_formatted_cuit(_text(generales, "idPersona")),
        name=_name(generales),
        category=_category_letter(category_node.text),
    )


def _name(generales) -> str:
    """A person's name and surname, or a company's razón social."""
    razon_social = _optional(generales, "razonSocial")
    if razon_social:
        return razon_social

    parts = [_optional(generales, "nombre"), _optional(generales, "apellido")]
    return " ".join(p for p in parts if p)


def _text(node, name: str) -> str:
    found = node.find(name)
    if found is None or not found.text:
        raise PadronError(f"The response has no <{name}>.")
    return found.text.strip()


def _optional(node, name: str) -> str:
    found = node.find(name)
    return found.text.strip() if found is not None and found.text else ""
