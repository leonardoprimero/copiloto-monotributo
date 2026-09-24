"""The command line demo.

Everything a person sees here is in Spanish, because the person reading it is
an Argentine monotributista. The code, the identifiers and the README stay in
English; the product speaks the language of whoever uses it.

When the graph pauses, this is what plays the accountant: it shows the alert,
asks for a verdict, and resumes the run with the answer.
"""

import argparse
import os
import sys
from collections.abc import Callable
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from pydantic import ValidationError

from copiloto.analysis import RiskPolicy
from copiloto.cuit import is_valid_cuit
from copiloto.evals.schema import EvalCase
from copiloto.extractors.api import ApiExtractor
from copiloto.extractors.cli import CliExtractor, run_subprocess
from copiloto.extractors.fake import FakeExtractor
from copiloto.extractors.protocol import ExtractionError, InvoiceExtractor
from copiloto.extractors.resolve import resolve_cli_argv
from copiloto.graph.builder import build_graph
from copiloto.models import DeclaredParameters, ExtractedInvoice, TaxpayerProfile
from copiloto.registry import MockArcaRegistry
from copiloto.scales import Scales, load_scales
from copiloto.sources import SourceError, load_invoice_texts

_RISK_LABELS = {
    "low": "bajo",
    "medium": "medio",
    "high": "alto",
    "exclusion": "riesgo de exclusión",
}

_REASONS = {
    "NEAR_REGISTERED_CAP": "estás cerca del tope de tu categoría registrada",
    "CATEGORY_MISMATCH": "tus ingresos corresponden a una categoría distinta de la registrada",
    "PROJECTION_ABOVE_REGISTERED_CAP": "al ritmo actual vas a superar el tope de tu categoría",
    "NEAR_TOP_CAP": "estás cerca del tope de la categoría más alta",
    "PROJECTION_ABOVE_TOP_CAP": "al ritmo actual vas a superar el tope del régimen",
    "INCOME_ABOVE_TOP_CAP": "tus ingresos superan el tope de la categoría más alta",
    "UNIT_PRICE_ABOVE_MAX": "hay un producto por encima del precio unitario máximo",
    "SURFACE_ABOVE_REGISTERED_CAP": "la superficie declarada supera la de tu categoría registrada",
    "ENERGY_ABOVE_REGISTERED_CAP": "la energía declarada supera la de tu categoría registrada",
    "RENT_ABOVE_REGISTERED_CAP": "los alquileres declarados superan los de tu categoría registrada",
    "SURFACE_ABOVE_TOP_CAP": "la superficie declarada supera el máximo del régimen",
    "ENERGY_ABOVE_TOP_CAP": "la energía declarada supera el máximo del régimen",
    "RENT_ABOVE_TOP_CAP": "los alquileres declarados superan el máximo del régimen",
}

_PARAMETER_FLAGS = {
    "surface_m2": "--surface-m2 (superficie)",
    "annual_energy_kwh": "--energy-kwh (energía)",
    "annual_rent": "--annual-rent (alquileres)",
}

_VERDICTS = {"confirmado": "confirmed", "descartado": "dismissed"}


def _fake_for(case: EvalCase | None) -> FakeExtractor:
    if case is None:
        # Guarded by the argument checks; kept so the failure is explicit
        # rather than an AttributeError deep inside a node.
        raise ExtractionError(
            "El extractor `fake` solo funciona con --case: no puede leer facturas reales."
        )
    return FakeExtractor(
        dict(
            zip(
                case.invoice_texts,
                [ExtractedInvoice.model_validate(i) for i in case.invoices],
                strict=True,
            )
        )
    )


def build_extractor_factory(mode: str) -> Callable[[EvalCase | None], InvoiceExtractor]:
    """Build the extractor factory for the requested mode.

    The `cli` and `api` extractors ignore the case entirely: they read whatever
    text they are handed, which is what lets the same graph run on eval cases
    and on a folder of real invoices.
    """
    if mode == "fake":
        return _fake_for
    if mode == "cli":
        argv = resolve_cli_argv(env=dict(os.environ))
        return lambda _case: CliExtractor(run=run_subprocess, argv=argv)
    return lambda _case: ApiExtractor.from_env(env=dict(os.environ))


def _registry(case: EvalCase) -> MockArcaRegistry:
    if case.registry_entry is None:
        return MockArcaRegistry({})
    entry = case.registry_entry
    return MockArcaRegistry(
        {
            entry.cuit: TaxpayerProfile(
                cuit=entry.cuit, name=entry.name, category=entry.category
            )
        }
    )


def _declared_registry(cuit: str, category: str) -> MockArcaRegistry:
    """Build a registry from what the taxpayer says about themselves.

    The only thing an ARCA lookup would provide is the registered category, and
    the taxpayer already knows that letter. Asking for it keeps the project
    away from anyone's fiscal credentials without losing anything.
    """
    return MockArcaRegistry(
        {cuit: TaxpayerProfile(cuit=cuit, name="Contribuyente declarado", category=category)}
    )


def _money(amount: str) -> str:
    """Format an amount the way the report does: dots for thousands, comma for cents."""
    value = Decimal(amount)
    return f"$ {value:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")


def _headroom_line(scope: str, amount: str) -> str:
    """Margin left, or by how much the cap was passed; never a negative amount."""
    value = Decimal(amount)
    if value >= 0:
        return f"Margen en {scope}: {_money(amount)}"
    return f"Tope de {scope} superado por: {_money(str(-value))}"


def _print_alert(payload: dict) -> None:
    print("\n" + "=" * 68)
    print("Derivamos este caso a un contador antes de cerrar el informe.")
    print("=" * 68)
    print(f"Nivel de riesgo: {_RISK_LABELS.get(payload['risk_level'], payload['risk_level'])}")

    if payload["registered_category"] or payload["computed_category"]:
        print(
            f"Categoría registrada: {payload['registered_category'] or 'sin dato'}"
            f"  ->  estimada: {payload['computed_category'] or 'ninguna'}"
        )
    if payload["accumulated_12m"] is not None:
        # Same formatting as the report: an alert that shows raw digits next to
        # a formatted report looks like two different systems talking.
        print(f"Acumulado 12 meses: {_money(payload['accumulated_12m'])}")
        print(f"Proyección anual  : {_money(payload['projected_12m'])}")
    if payload.get("headroom_registered") is not None:
        print(_headroom_line("categoría", payload["headroom_registered"]))
    if payload.get("headroom_top") is not None:
        print(_headroom_line("régimen", payload["headroom_top"]))

    for reason in payload["reasons"]:
        print(f"  - {_REASONS.get(reason, reason)}")
    for issue in payload["issues"]:
        print(f"  - [{issue['severity']}] {issue['code']}: {issue['message']}")
    print()


def _ask_accountant() -> dict:
    """Ask for the verdict, defaulting to the safer answer.

    Pressing enter confirms the alert rather than dismissing it: an accountant
    who walks away should not silently clear the case.
    """
    answer = input("Veredicto [confirmado/descartado] (confirmado): ").strip().lower()
    verdict = _VERDICTS.get(answer, "confirmed")
    notes = input("Notas (opcional): ").strip()
    return {"verdict": verdict, "notes": notes, "reviewer": "accountant"}


def _declared_from_args(args: argparse.Namespace) -> DeclaredParameters:
    """Build the declared parameters, raising a readable message on bad input."""
    hint = "tiene que ser un número mayor o igual a cero."
    try:
        rent = Decimal(args.annual_rent) if args.annual_rent is not None else None
    except InvalidOperation as error:
        raise ValueError(f"Revisá {_PARAMETER_FLAGS['annual_rent']}: {hint}") from error

    try:
        return DeclaredParameters(
            surface_m2=args.surface_m2, annual_energy_kwh=args.energy_kwh, annual_rent=rent
        )
    except ValidationError as error:
        fields = sorted(
            {
                _PARAMETER_FLAGS[str(e["loc"][0])]
                for e in error.errors()
                if str(e["loc"][0]) in _PARAMETER_FLAGS
            }
        )
        raise ValueError(f"Revisá {', '.join(fields)}: {hint}") from error


def _validate_own_invoice_args(args: argparse.Namespace, scales: Scales) -> str | None:
    """Check the flags that only make sense with a folder of real invoices.

    Every problem here is caught before a single document is read, so a typo in
    a CUIT does not come back as twelve identical complaints about invoices.
    """
    if not args.cuit:
        return "Con --invoices-dir necesito --cuit: el CUIT del contribuyente."
    if not is_valid_cuit(args.cuit):
        return f"El CUIT {args.cuit} no pasa el dígito verificador."
    if not args.category:
        return (
            "Con --invoices-dir necesito --category: la categoría en la que estás "
            "registrado. La tenés en tu credencial o en el pago mensual."
        )

    names = [c.name for c in scales.categories]
    if args.category not in names:
        return f"La categoría {args.category} no existe. Son: {', '.join(names)}."

    if args.extractor == "fake":
        return (
            "El extractor `fake` solo conoce los textos de los casos de eval y no "
            "puede leer una factura real. Usá --extractor cli o --extractor api."
        )
    return None


def _run(args: argparse.Namespace) -> int:
    scales = load_scales()

    try:
        declared = _declared_from_args(args)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2

    if args.invoices_dir:
        problem = _validate_own_invoice_args(args, scales)
        if problem:
            print(problem, file=sys.stderr)
            return 2
        try:
            raw_invoices = load_invoice_texts(Path(args.invoices_dir))
        except SourceError as error:
            print(str(error), file=sys.stderr)
            return 1

        case = None
        taxpayer_cuit = args.cuit
        registry = _declared_registry(args.cuit, args.category)
        thread = f"cli-{Path(args.invoices_dir).name}"
        default_today = date.today()
    else:
        try:
            case = EvalCase.model_validate_json(
                Path(args.case).read_text(encoding="utf-8")
            )
        except OSError as error:
            print(f"No pude leer el caso: {error}", file=sys.stderr)
            return 1

        raw_invoices = case.invoice_texts
        taxpayer_cuit = case.taxpayer_cuit
        registry = _registry(case)
        thread = f"cli-{case.id}"
        default_today = date.fromisoformat(case.today)

    try:
        factory = build_extractor_factory(args.extractor)
    except ExtractionError as error:
        print(f"No pude preparar el lector de facturas:\n{error}", file=sys.stderr)
        return 1

    today = date.fromisoformat(args.today) if args.today else default_today
    graph = build_graph(
        extractor=factory(case),
        registry=registry,
        scales=scales,
        today=today,
        policy=RiskPolicy(),
    )
    config: RunnableConfig = {"configurable": {"thread_id": thread}}

    state = graph.invoke(
        {"taxpayer_cuit": taxpayer_cuit, "raw_invoices": raw_invoices, "declared": declared},
        config,
    )

    if "__interrupt__" in state:
        payload = state["__interrupt__"][0].value
        _print_alert(payload)

        if args.auto_resume:
            decision = {
                "verdict": "confirmed",
                "notes": "Reanudación automática; nadie revisó el caso.",
                "reviewer": "auto",
            }
            print("Reanudación automática: ningún contador revisó este caso.\n")
        else:
            decision = _ask_accountant()

        state = graph.invoke(Command(resume=decision), config)

    print(state["report"])
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="copiloto",
        description="Copiloto de monotributo. Orientativo: no reemplaza a un contador.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Analizar facturas y armar el informe.")

    source = run.add_mutually_exclusive_group(required=True)
    source.add_argument("--case", help="Ruta a un caso sintético de evals/cases.")
    source.add_argument(
        "--invoices-dir",
        help="Carpeta con tus facturas (.txt o .pdf). Requiere --cuit y --category.",
    )

    run.add_argument("--cuit", help="Tu CUIT. Solo con --invoices-dir.")
    run.add_argument(
        "--category",
        help="La categoría en la que estás registrado (A a K). Solo con --invoices-dir.",
    )
    run.add_argument(
        "--extractor",
        choices=("fake", "cli", "api"),
        default=os.environ.get("COPILOTO_EXTRACTOR", "fake"),
        help="fake: sin red. cli: tu herramienta de IA. api: con clave de proveedor.",
    )
    run.add_argument(
        "--surface-m2",
        type=int,
        help="Superficie afectada a la actividad, en m². Solo si tenés local.",
    )
    run.add_argument(
        "--energy-kwh",
        type=int,
        help="Energía eléctrica consumida en los últimos 12 meses, en kWh. Solo si tenés local.",
    )
    run.add_argument(
        "--annual-rent",
        help="Alquileres devengados en los últimos 12 meses, en pesos.",
    )
    run.add_argument("--today", help="Fecha de corte YYYY-MM-DD.")
    run.add_argument(
        "--auto-resume",
        action="store_true",
        help="Reanudar sin preguntar. El informe aclara que nadie lo revisó.",
    )

    args = parser.parse_args(argv)
    return _run(args)


if __name__ == "__main__":
    sys.exit(main())
