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
from decimal import Decimal

from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from copiloto.analysis import RiskPolicy
from copiloto.evals.runner import ExtractorFactory
from copiloto.evals.schema import EvalCase
from copiloto.extractors.api import ApiExtractor
from copiloto.extractors.cli import CliExtractor, run_subprocess
from copiloto.extractors.fake import FakeExtractor
from copiloto.extractors.protocol import ExtractionError
from copiloto.extractors.resolve import resolve_cli_argv
from copiloto.graph.builder import build_graph
from copiloto.models import ExtractedInvoice, TaxpayerProfile
from copiloto.registry import MockArcaRegistry
from copiloto.scales import load_scales

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
}

_VERDICTS = {"confirmado": "confirmed", "descartado": "dismissed"}


def build_extractor_factory(mode: str) -> ExtractorFactory:
    """Build the extractor factory for the requested mode."""
    if mode == "fake":
        return lambda case: FakeExtractor(
            dict(
                zip(
                    case.invoice_texts,
                    [ExtractedInvoice.model_validate(i) for i in case.invoices],
                    strict=True,
                )
            )
        )
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


def _money(amount: str) -> str:
    """Format an amount the way the report does: dots for thousands, comma for cents."""
    value = Decimal(amount)
    return f"$ {value:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")


def _print_alert(payload: dict) -> None:
    print("\n" + "=" * 68)
    print("Derivamos este caso a un contador antes de cerrar el informe.")
    print("=" * 68)
    print(f"Nivel de riesgo: {_RISK_LABELS.get(payload['risk_level'], payload['risk_level'])}")

    if payload["registered_category"] or payload["computed_category"]:
        print(
            f"Categoría registrada: {payload['registered_category'] or 'sin dato'}"
            f"  ->  estimada por ingresos: {payload['computed_category'] or 'ninguna'}"
        )
    if payload["accumulated_12m"] is not None:
        # Same formatting as the report: an alert that shows raw digits next to
        # a formatted report looks like two different systems talking.
        print(f"Acumulado 12 meses: {_money(payload['accumulated_12m'])}")
        print(f"Proyección anual  : {_money(payload['projected_12m'])}")

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


def _run_case(args: argparse.Namespace) -> int:
    try:
        case = EvalCase.model_validate_json(
            open(args.case, encoding="utf-8").read()  # noqa: SIM115
        )
    except OSError as error:
        print(f"No pude leer el caso: {error}", file=sys.stderr)
        return 1

    try:
        factory = build_extractor_factory(args.extractor)
    except ExtractionError as error:
        print(f"No pude preparar el lector de facturas:\n{error}", file=sys.stderr)
        return 1

    today = date.fromisoformat(args.today) if args.today else date.fromisoformat(case.today)
    graph = build_graph(
        extractor=factory(case),
        registry=_registry(case),
        scales=load_scales(),
        today=today,
        policy=RiskPolicy(),
    )
    config: RunnableConfig = {"configurable": {"thread_id": f"cli-{case.id}"}}

    state = graph.invoke(
        {"taxpayer_cuit": case.taxpayer_cuit, "raw_invoices": case.invoice_texts}, config
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

    run = sub.add_parser("run", help="Analizar un caso sintético.")
    run.add_argument("--case", required=True, help="Ruta a un caso de evals/cases.")
    run.add_argument(
        "--extractor",
        choices=("fake", "cli", "api"),
        default=os.environ.get("COPILOTO_EXTRACTOR", "fake"),
        help="fake: sin red. cli: tu herramienta de IA. api: con clave de proveedor.",
    )
    run.add_argument("--today", help="Fecha de corte YYYY-MM-DD.")
    run.add_argument(
        "--auto-resume",
        action="store_true",
        help="Reanudar sin preguntar. El informe aclara que nadie lo revisó.",
    )

    args = parser.parse_args(argv)
    return _run_case(args)


if __name__ == "__main__":
    sys.exit(main())
