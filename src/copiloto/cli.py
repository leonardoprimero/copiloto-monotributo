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
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from copiloto.analysis import RiskPolicy
from copiloto.cuit import is_valid_cuit
from copiloto.evals.schema import EvalCase
from copiloto.extractors.protocol import ExtractionError
from copiloto.extractors.select import build_extractor_factory
from copiloto.graph.checkpoints import open_checkpointer
from copiloto.models import DeclaredParameters, HumanDecision, TaxpayerProfile, Verdict
from copiloto.ocr import default_ocr
from copiloto.registry import MockArcaRegistry
from copiloto.scales import Scales, load_scales
from copiloto.service import CaseAlreadyExists, Copilot, PendingReview
from copiloto.sources import SourceError, load_invoice_sources, ocr_issue

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

_VERDICTS: dict[str, Verdict] = {"confirmado": "confirmed", "descartado": "dismissed"}


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


def _ask_accountant() -> HumanDecision:
    """Ask for the verdict, defaulting to the safer answer.

    Pressing enter confirms the alert rather than dismissing it: an accountant
    who walks away should not silently clear the case.
    """
    answer = input("Veredicto [confirmado/descartado] (confirmado): ").strip().lower()
    verdict = _VERDICTS.get(answer, "confirmed")
    notes = input("Notas (opcional): ").strip()
    return HumanDecision(verdict=verdict, notes=notes, reviewer="accountant")


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

    if args.arca:
        if not (args.arca_cert and args.arca_key and args.arca_cuit):
            return (
                "Con --arca necesito el certificado (--arca-cert), la clave privada "
                "(--arca-key) y el CUIT representado (--arca-cuit), o las variables "
                "COPILOTO_ARCA_*."
            )
        try:
            import copiloto.arca.client  # noqa: F401
        except ImportError:
            return "El cliente de ARCA requiere instalar el extra opcional: uv sync --extra arca"

        if args.category:
            names = [c.name for c in scales.categories]
            if args.category not in names:
                return f"La categoría {args.category} no existe. Son: {', '.join(names)}."
    else:
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
            sources = load_invoice_sources(Path(args.invoices_dir), ocr=default_ocr())
        except SourceError as error:
            print(str(error), file=sys.stderr)
            return 1

        raw_invoices = tuple(s.text for s in sources)
        scanned = ocr_issue(sources)
        source_issues = (scanned,) if scanned else ()
        case = None
        taxpayer_cuit = args.cuit
        if args.arca:
            from copiloto.arca.client import build_registry, default_ticket_cache_path

            if args.no_arca_ticket_cache:
                cache_path = None
            elif args.arca_ticket_cache:
                cache_path = (
                    None
                    if args.arca_ticket_cache.lower() in ("none", "0", "false")
                    else Path(args.arca_ticket_cache)
                )
            else:
                cache_path = default_ticket_cache_path()

            registry = build_registry(
                cert_path=Path(args.arca_cert),
                key_path=Path(args.arca_key),
                represented_cuit=args.arca_cuit,
                environment=args.arca_env,
                ticket_cache=cache_path,
                passphrase=args.arca_passphrase.encode() if args.arca_passphrase else None,
            )
        else:
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
        source_issues = ()
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
    case_id = args.case_id or f"{thread}-{uuid4().hex[:8]}"
    service = _service(args.state_db)

    try:
        outcome = service.start(
            case_id=case_id,
            taxpayer_cuit=taxpayer_cuit,
            raw_invoices=raw_invoices,
            extractor=factory(case),
            registry=registry,
            today=today,
            declared=declared,
            source_issues=source_issues,
        )
    except CaseAlreadyExists:
        print(f"Ya existe un caso {case_id}. Elegí otro --case-id.", file=sys.stderr)
        return 2

    if isinstance(outcome, PendingReview):
        _print_alert(outcome.alert)

        if args.no_wait:
            print(f"Caso pendiente: {case_id}")
            print(
                "Quedó guardado. Cuando el contador lo revise:\n"
                f"  copiloto review --state-db {args.state_db} --case-id {case_id}"
            )
            return 3

        if args.auto_resume:
            decision = HumanDecision(
                verdict="confirmed",
                notes="Reanudación automática; nadie revisó el caso.",
                reviewer="auto",
            )
            print("Reanudación automática: ningún contador revisó este caso.\n")
        else:
            decision = _ask_accountant()

        outcome = service.resume(case_id, decision)

    print(outcome.report)
    return 0


def _service(state_db: str | None) -> Copilot:
    path = Path(state_db) if state_db else None
    return Copilot(scales=load_scales(), policy=RiskPolicy(), checkpointer=open_checkpointer(path))


def _review(args: argparse.Namespace) -> int:
    service = _service(args.state_db)
    found = service.get(args.case_id)

    if not isinstance(found, PendingReview):
        state = "ya fue revisado" if found is not None else "no existe"
        print(
            f"El caso {args.case_id} {state}. `copiloto cases --state-db {args.state_db}` "
            "lista los que hay.",
            file=sys.stderr,
        )
        return 1

    _print_alert(found.alert)
    if args.verdict:
        decision = HumanDecision(
            verdict=_VERDICTS[args.verdict], notes=args.notes or "", reviewer="accountant"
        )
    else:
        decision = _ask_accountant()

    print(service.resume(args.case_id, decision).report)
    return 0


_STATUS_LABELS = {"pending": "pendiente", "done": "cerrado", "incomplete": "incompleto"}
DEFAULT_STATE_DB = "copiloto-state.sqlite"


def _serve(args: argparse.Namespace) -> int:
    """Run the web interface. Imported here so the CLI stays fast without it."""
    import uvicorn  # noqa: PLC0415

    from copiloto.web.app import WebSettings, create_app  # noqa: PLC0415

    token = os.environ.get("COPILOTO_TOKEN") or None
    settings = WebSettings(
        state_db=Path(args.state_db), extractor_mode=args.extractor, access_token=token
    )
    print(f"Copiloto de monotributo en http://{args.host}:{args.port}")
    print(f"Casos guardados en {args.state_db}. Lector de facturas: {args.extractor}.")
    if args.extractor == "fake":
        print("En modo fake solo corren los ejemplos; para facturas reales usá --extractor cli o api.")
    if token:
        print("Protegido con la clave de COPILOTO_TOKEN.")
    elif args.host not in ("127.0.0.1", "localhost", "::1"):
        # Binding to anything else publishes every case on the network, and a
        # case page is somebody's income. Say it where it cannot be missed.
        print(
            f"⚠  Escuchando en {args.host} SIN clave: cualquiera que llegue al puerto "
            "puede leer todos los casos. Definí COPILOTO_TOKEN para protegerlo.",
            file=sys.stderr,
        )
    uvicorn.run(create_app(settings), host=args.host, port=args.port, log_level="warning")
    return 0


def _cases(args: argparse.Namespace) -> int:
    summaries = _service(args.state_db).list_cases()
    if not summaries:
        print("No hay casos en este archivo.")
        return 0

    print(f"{'caso':<28} {'estado':<11} {'CUIT':<14} {'cat.':<5} {'riesgo':<20} creado")
    for s in summaries:
        risk = _RISK_LABELS.get(s.risk_level or "", s.risk_level or "-")
        created = (s.created_at or "")[:19].replace("T", " ")
        print(
            f"{s.case_id:<28} {_STATUS_LABELS[s.status]:<11} {s.taxpayer_cuit:<14} "
            f"{s.registered_category or '-':<5} {risk:<20} {created}"
        )
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
    run.add_argument(
        "--arca",
        action="store_true",
        default=os.environ.get("COPILOTO_ARCA") == "1",
        help="Consultar el padrón real de ARCA en vez de usar la categoría declarada.",
    )
    run.add_argument(
        "--arca-cert",
        default=os.environ.get("COPILOTO_ARCA_CERT"),
        help="Ruta al certificado X.509.",
    )
    run.add_argument(
        "--arca-key",
        default=os.environ.get("COPILOTO_ARCA_KEY"),
        help="Ruta a la clave privada.",
    )
    run.add_argument(
        "--arca-cuit",
        default=os.environ.get("COPILOTO_ARCA_CUIT"),
        help="CUIT representado.",
    )
    run.add_argument(
        "--arca-env",
        choices=("produccion", "homologacion"),
        default=os.environ.get("COPILOTO_ARCA_ENV", "produccion"),
        help="Ambiente de ARCA (produccion o homologacion).",
    )
    run.add_argument(
        "--arca-ticket-cache",
        default=os.environ.get("COPILOTO_ARCA_TICKET_CACHE"),
        help="Ruta al archivo donde guardar el ticket de acceso WSAA (por defecto ~/.cache/copiloto/tickets.json).",
    )
    run.add_argument(
        "--no-arca-ticket-cache",
        action="store_true",
        help="No guardar el ticket en disco, manteniéndolo solo en memoria durante la ejecución.",
    )
    run.add_argument(
        "--arca-passphrase",
        default=os.environ.get("COPILOTO_ARCA_PASSPHRASE"),
        help="Contraseña de la clave privada, si tiene.",
    )
    _add_state_arguments(run)
    run.add_argument(
        "--no-wait",
        action="store_true",
        help="Si el caso se deriva, dejarlo guardado y salir en vez de preguntar. Requiere --state-db.",
    )

    review = sub.add_parser("review", help="Retomar un caso pendiente y darle el veredicto.")
    _add_state_arguments(review, required=True)
    review.add_argument(
        "--verdict", choices=tuple(_VERDICTS), help="Si falta, se pregunta por teclado."
    )
    review.add_argument("--notes", help="Notas del contador para el informe.")

    cases = sub.add_parser("cases", help="Listar los casos guardados y su estado.")
    cases.add_argument("--state-db", required=True, help="Archivo SQLite con los casos.")

    serve = sub.add_parser("serve", help="Levantar la interfaz web.")
    serve.add_argument("--host", default=os.environ.get("COPILOTO_HOST", "127.0.0.1"))
    serve.add_argument("--port", type=int, default=int(os.environ.get("COPILOTO_PORT", "8000")))
    serve.add_argument(
        "--state-db",
        default=os.environ.get("COPILOTO_STATE_DB", DEFAULT_STATE_DB),
        help=f"Archivo SQLite con los casos. Por defecto {DEFAULT_STATE_DB} en la carpeta actual.",
    )
    serve.add_argument(
        "--extractor",
        choices=("fake", "cli", "api"),
        default=os.environ.get("COPILOTO_EXTRACTOR", "fake"),
        help="fake: solo ejemplos. cli: tu herramienta de IA. api: con clave de proveedor.",
    )

    args = parser.parse_args(argv)

    if args.command == "review":
        return _review(args)
    if args.command == "cases":
        return _cases(args)
    if args.command == "serve":
        return _serve(args)
    if args.no_wait and not args.state_db:
        print(
            "--no-wait necesita --state-db: sin un archivo, el caso pendiente se pierde "
            "cuando termina el proceso.",
            file=sys.stderr,
        )
        return 2
    return _run(args)


def _add_state_arguments(parser: argparse.ArgumentParser, *, required: bool = False) -> None:
    parser.add_argument(
        "--state-db",
        required=required,
        default=None if required else os.environ.get("COPILOTO_STATE_DB") or None,
        help="Archivo SQLite donde guardar los casos. Sin él, todo vive en memoria.",
    )
    parser.add_argument(
        "--case-id",
        required=required,
        help="Identificador del caso." + ("" if required else " Por defecto se genera uno."),
    )


if __name__ == "__main__":
    sys.exit(main())
