"""Rendering the report.

Written in Spanish because monotributo is an Argentine regime and the people
who read this are in Argentina; the code and the identifiers stay in English.
The register is professional: a report that warns someone about losing their
tax regime should not sound casual.

`DISCLAIMER_ES` is the single source of truth for that warning. The README
quotes it verbatim and a test compares them, so it cannot be trimmed in one
place and survive in the other.

A pure function from data to text. It reads no clock and no file, so it renders
the same bytes for the same input, and it is tested without the graph.
"""

from decimal import Decimal

from copiloto.analysis import Analysis
from copiloto.models import DeclaredParameters, HumanDecision, Issue, ParameterName, TaxpayerProfile
from copiloto.scales import Scales

SCOPE_NOTE_ES = (
    "Este informe está escrito en español rioplatense porque el monotributo es "
    "un régimen argentino y este copiloto se usa en Argentina."
)

DISCLAIMER_ES = (
    # Phrased to read correctly both above a report and at the top of the
    # README, because it is quoted verbatim in both and a test compares them.
    "**Aviso.** Este copiloto es orientativo y tiene fines informativos y educativos. "
    "No es asesoramiento impositivo ni legal, y no reemplaza a un contador matriculado. "
    "Nunca presenta trámites ante ARCA: no declara, no recategoriza y no hace ninguna "
    "gestión en tu nombre. Todas las facturas, CUIT y contribuyentes de este proyecto "
    "son sintéticos."
)

# What this project does not look at unless the taxpayer declares it. Listed
# in every report so that a low risk level is not read as a complete
# assessment; a declared parameter leaves the list because it was evaluated.
NOT_EVALUATED = (
    "superficie afectada a la actividad",
    "energía eléctrica consumida",
    "alquileres devengados",
    "cantidad de actividades y unidades de explotación",
    "gastos y adquisiciones no justificados",
    "las excepciones por tamaño de la localidad donde está el local",
)

_EVALUATED_BY: dict[ParameterName, str] = {
    "surface": "superficie afectada a la actividad",
    "energy": "energía eléctrica consumida",
    "rent": "alquileres devengados",
}

_PARAMETER_LABELS: dict[ParameterName, str] = {
    "income": "ingresos",
    "surface": "superficie",
    "energy": "energía eléctrica",
    "rent": "alquileres",
}

RISK_LABELS = {
    "low": "bajo",
    "medium": "medio",
    "high": "alto",
    "exclusion": "riesgo de exclusión",
}

# Internal values never reach the reader untranslated.
_VERDICT_LABELS = {"confirmed": "confirmado", "dismissed": "descartado"}

REASON_LABELS = {
    "NEAR_REGISTERED_CAP": "Estás cerca del tope de tu categoría registrada.",
    "CATEGORY_MISMATCH": "Tus ingresos corresponden a una categoría distinta de la registrada.",
    "PROJECTION_ABOVE_REGISTERED_CAP": (
        "Si seguís facturando a este ritmo, vas a superar el tope de tu categoría."
    ),
    "NEAR_TOP_CAP": "Estás cerca del tope de la categoría más alta del régimen.",
    "PROJECTION_ABOVE_TOP_CAP": (
        "Si seguís facturando a este ritmo, vas a superar el tope del régimen."
    ),
    "INCOME_ABOVE_TOP_CAP": "Tus ingresos superan el tope de la categoría más alta.",
    "UNIT_PRICE_ABOVE_MAX": (
        "Hay un producto facturado por encima del precio unitario máximo permitido."
    ),
    "SURFACE_ABOVE_REGISTERED_CAP": (
        "La superficie declarada está por encima de lo que admite tu categoría registrada."
    ),
    "ENERGY_ABOVE_REGISTERED_CAP": (
        "La energía declarada está por encima de lo que admite tu categoría registrada."
    ),
    "RENT_ABOVE_REGISTERED_CAP": (
        "Los alquileres declarados están por encima de lo que admite tu categoría registrada."
    ),
    "SURFACE_ABOVE_TOP_CAP": "La superficie declarada supera el máximo del régimen.",
    "ENERGY_ABOVE_TOP_CAP": "La energía declarada supera el máximo del régimen.",
    "RENT_ABOVE_TOP_CAP": "Los alquileres declarados superan el máximo del régimen.",
}


def format_money(amount: Decimal) -> str:
    return f"$ {amount:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")


def _integer(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def _category_line(analysis: Analysis) -> str:
    estimated = analysis.computed_category or "ninguna (supera el tope del régimen)"
    if analysis.evaluated_parameters == ("income",):
        return f"- Categoría estimada: {estimated} — calculada solo por ingresos."

    evaluated = ", ".join(_PARAMETER_LABELS[p] for p in analysis.evaluated_parameters)
    binding = _PARAMETER_LABELS[analysis.binding_parameter]
    return (
        f"- Categoría estimada: {estimated} — definida por {binding}, el parámetro más "
        f"alto entre los evaluados ({evaluated})."
    )


def _declared_section(declared: DeclaredParameters) -> list[str]:
    lines = [
        "Estos valores los declaraste vos; no fueron verificados contra ningún comprobante.",
    ]
    if declared.surface_m2 is not None:
        lines.append(f"- Superficie afectada: {_integer(declared.surface_m2)} m²")
    if declared.annual_energy_kwh is not None:
        lines.append(f"- Energía eléctrica anual: {_integer(declared.annual_energy_kwh)} kWh")
    if declared.annual_rent is not None:
        lines.append(f"- Alquileres anuales: {format_money(declared.annual_rent)}")
    return lines


def _months(months: Decimal) -> str:
    return f"{months:.1f}".replace(".", ",") + " meses"


def _headroom_section(analysis: Analysis, scales: Scales) -> list[str]:
    """How much can still be invoiced, and how soon that runs out.

    A passed cap is explained ("superaste ... por") rather than printed as a
    negative amount, and months are only estimated when there is a recent pace
    to extrapolate from.
    """
    lines: list[str] = []

    registered = analysis.headroom_registered
    if registered is not None:
        label = f"tu categoría registrada ({analysis.registered_category})"
        if registered >= 0:
            lines.append(f"- Hasta el tope de {label}: {format_money(registered)}")
        else:
            lines.append(f"- Superaste el tope de {label} por {format_money(-registered)}.")

    top_label = f"el tope del régimen ({scales.top_category.name})"
    if analysis.headroom_top >= 0:
        lines.append(f"- Hasta {top_label}: {format_money(analysis.headroom_top)}")
    else:
        lines.append(f"- Superaste {top_label} por {format_money(-analysis.headroom_top)}.")

    if analysis.projected_12m <= 0:
        lines.append(
            "- Sin facturación reciente no podemos estimar cuándo llegarías a un tope."
        )
        return lines

    months_registered = analysis.months_to_registered_cap
    if months_registered is not None and months_registered > 0:
        lines.append(
            f"- Al ritmo reciente, llegás al tope de tu categoría en {_months(months_registered)}."
        )
    months_top = analysis.months_to_top_cap
    if months_top is not None and months_top > 0:
        lines.append(
            f"- Al ritmo reciente, llegás al tope del régimen en {_months(months_top)}."
        )
    if (months_registered is not None and months_registered > 0) or (
        months_top is not None and months_top > 0
    ):
        lines.append(
            "- Los meses son una estimación propia: suponen que seguís al ritmo de los "
            "últimos 90 días y no descuentan las facturas que van saliendo de la ventana."
        )
    return lines


def _review_section(decision: HumanDecision | None) -> list[str]:
    if decision is None:
        return ["Sin revisión: este caso no fue derivado a una persona."]

    if decision.reviewer == "auto":
        # The demo and the eval runner resume the graph without asking anyone.
        # Saying so is the whole point of tracking who reviewed.
        return [
            "Ningún contador revisó este caso: la ejecución se reanudó de forma "
            "automática para la demostración.",
            f"Resultado registrado: {_VERDICT_LABELS[decision.verdict]}.",
        ]

    lines = [f"Revisado por un contador. Resultado: {_VERDICT_LABELS[decision.verdict]}."]
    if decision.notes:
        lines.append(f"Notas: {decision.notes}")
    return lines


def render_report(
    analysis: Analysis,
    *,
    issues: tuple[Issue, ...],
    taxpayer: TaxpayerProfile | None,
    scales: Scales,
    human_decision: HumanDecision | None = None,
    invoice_count: int,
    declared: DeclaredParameters | None = None,
) -> str:
    """Render the analysis as markdown, in Spanish."""
    declared = declared if declared and declared.declared() else None
    lines: list[str] = [SCOPE_NOTE_ES, "", DISCLAIMER_ES, "", "# Informe de monotributo", ""]

    lines += ["## Contribuyente", ""]
    if taxpayer is None:
        lines.append("No encontramos este CUIT en el padrón, así que no podemos comparar "
                     "tus ingresos con una categoría registrada.")
    else:
        lines.append(f"- {taxpayer.name} ({taxpayer.cuit})")
        lines.append(f"- Categoría registrada: {taxpayer.category}")
    lines.append("")

    lines += ["## Ingresos", ""]
    if invoice_count == 0:
        lines.append(
            "No se recibió ninguna factura. Sin comprobantes no podemos estimar nada: "
            "esto es falta de datos, no un resultado favorable."
        )
    else:
        lines.append(f"- Facturas analizadas: {invoice_count}")
    lines.append(f"- Acumulado de los últimos 12 meses móviles: {format_money(analysis.accumulated_12m)}")
    lines.append(_category_line(analysis))
    lines.append("")

    if declared is not None:
        lines += ["## Parámetros declarados", "", *_declared_section(declared), ""]

    lines += [
        "## Proyección",
        "",
        f"- Proyección anual al ritmo reciente: {format_money(analysis.projected_12m)}",
        "- Es una estimación propia de esta herramienta, no una fórmula de ARCA.",
        "",
    ]

    lines += ["## Margen", "", *_headroom_section(analysis, scales), ""]

    lines += ["## Riesgo", "", f"- Nivel: {RISK_LABELS[analysis.risk_level]}", ""]
    if analysis.reasons:
        lines.append("Motivos:")
        lines += [f"- {REASON_LABELS.get(r, r)}" for r in analysis.reasons]
    else:
        lines.append("No detectamos motivos de alerta en lo que revisamos.")
    lines.append("")

    lines += ["## Observaciones", ""]
    if issues:
        lines += [
            f"- [{i.severity}] {i.code}"
            + (f" (factura {i.invoice_number})" if i.invoice_number else "")
            + f": {i.message}"
            for i in issues
        ]
    else:
        lines.append("Sin observaciones sobre los comprobantes.")
    lines.append("")

    lines += ["## Revisión", "", *_review_section(human_decision), ""]

    evaluated = {_EVALUATED_BY[p] for p in analysis.evaluated_parameters if p in _EVALUATED_BY}
    scope = (
        "Este informe mira solamente tus ingresos."
        if not evaluated
        else "Este informe mira tus ingresos y los parámetros que declaraste."
    )
    lines += [
        "## No evaluado",
        "",
        f"{scope} No evaluamos:",
        *[f"- {cause}" for cause in NOT_EVALUATED if cause not in evaluated],
        "",
        "Por eso un riesgo bajo no es una verificación integral de tu situación: "
        "hay causales de exclusión que esta herramienta no mira.",
        "",
    ]

    lines += [
        "## Escalas usadas",
        "",
        f"- Vigentes desde: {scales.effective_from.isoformat()}",
        f"- Consultadas el: {scales.retrieved_on.isoformat()}",
        f"- Fuente: {scales.source}",
        "",
    ]

    return "\n".join(lines)
