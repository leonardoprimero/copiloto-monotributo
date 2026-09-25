"""The web interface: the copilot a person opens in a browser.

Server-rendered pages, in Spanish, over the same `Copilot` service the CLI
uses. There is no JavaScript to speak of: a form starts a case, a page shows
either the report or the alert with a verdict form, and the verdict form
resumes the case. Every page can be reloaded, bookmarked and opened later by
someone else, because the state lives in the checkpointer and not in the
session.

`create_app` takes its settings explicitly so the tests can run it in memory
with a fake extractor, and `serve` can run it on SQLite with a real one.
"""

import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markdown_it import MarkdownIt
from markupsafe import Markup
from pydantic import ValidationError

from copiloto.analysis import RiskPolicy
from copiloto.cuit import is_valid_cuit
from copiloto.evals.schema import EvalCase
from copiloto.extractors.protocol import ExtractionError
from copiloto.extractors.select import ExtractorFactory, build_extractor_factory, fake_for
from copiloto.graph.checkpoints import open_checkpointer
from copiloto.models import DeclaredParameters, HumanDecision, TaxpayerProfile, Verdict
from copiloto.registry import MockArcaRegistry, TaxpayerRegistry
from copiloto.report import DISCLAIMER_ES, REASON_LABELS, RISK_LABELS, format_money
from copiloto.scales import load_scales
from copiloto.service import CaseSummary, Copilot, Finished, PendingReview
from copiloto.ocr import default_ocr
from copiloto.web.auth import (
    COOKIE_MAX_AGE,
    COOKIE_NAME,
    session_is_valid,
    session_value,
    token_matches,
)
from copiloto.sources import InvoiceSource, SourceError, load_invoice_sources, ocr_issue

ROOT = Path(__file__).resolve().parents[3]
CASES_DIR = ROOT / "evals" / "cases"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"

VERDICTS: dict[str, Verdict] = {"confirmado": "confirmed", "descartado": "dismissed"}
STATUS_LABELS = {"pending": "pendiente", "done": "cerrado", "incomplete": "incompleto"}

# `html: False` makes the renderer escape any tag found in the source, so the
# only markup that reaches a page is what markdown itself produces. That is
# what makes wrapping its output in `Markup` safe below: accountant notes and
# model-extracted text end up in the report, and neither may inject HTML.
_markdown = MarkdownIt("commonmark", {"html": False})


def _default_arca_registry() -> TaxpayerRegistry | None:
    if os.environ.get("COPILOTO_ARCA") == "1" or os.environ.get("COPILOTO_ARCA_CERT"):
        cert = os.environ.get("COPILOTO_ARCA_CERT")
        key = os.environ.get("COPILOTO_ARCA_KEY")
        cuit = os.environ.get("COPILOTO_ARCA_CUIT")
        if cert and key and cuit:
            try:
                from copiloto.arca.client import build_registry

                env = os.environ.get("COPILOTO_ARCA_ENV", "produccion")
                cache = os.environ.get("COPILOTO_ARCA_TICKET_CACHE")
                passphrase = os.environ.get("COPILOTO_ARCA_PASSPHRASE")
                return build_registry(
                    cert_path=Path(cert),
                    key_path=Path(key),
                    represented_cuit=cuit,
                    environment=env,
                    ticket_cache=Path(cache) if cache else None,
                    passphrase=passphrase.encode() if passphrase else None,
                )
            except ImportError:
                return None
    return None


@dataclass(frozen=True)
class WebSettings:
    """Everything the app needs that is not code.

    `extractor_factory` overrides the mode when given; the tests use it to
    read uploads with a fake. Otherwise the factory is built from the mode on
    each upload, so a missing tool or key becomes a message on the form rather
    than a crash at startup.

    `ocr` reads scanned PDFs. It defaults to whatever this machine can do:
    the real engine when the extra and tesseract are installed, and None
    otherwise, which makes a scan a clear error instead of a dropped invoice.
    """

    state_db: Path | None = None
    extractor_mode: str = "fake"
    extractor_factory: ExtractorFactory | None = None
    clock: Callable[[], date] = date.today
    cases_dir: Path = CASES_DIR
    policy: RiskPolicy = field(default_factory=RiskPolicy)
    ocr: Callable[[Path], str] | None = field(default_factory=default_ocr)
    access_token: str | None = None
    arca_registry: TaxpayerRegistry | None = field(default_factory=_default_arca_registry)


class FormError(ValueError):
    """Something the person can fix on the form."""


def load_examples(cases_dir: Path) -> dict[str, EvalCase]:
    """The eval cases, offered as examples so the copilot can be tried offline."""
    cases = (
        EvalCase.model_validate_json(path.read_text(encoding="utf-8"))
        for path in sorted(cases_dir.glob("*.json"))
    )
    return {case.id: case for case in cases}


def registry_for(case: EvalCase) -> MockArcaRegistry:
    entry = case.registry_entry
    if entry is None:
        return MockArcaRegistry({})
    return MockArcaRegistry(
        {entry.cuit: TaxpayerProfile(cuit=entry.cuit, name=entry.name, category=entry.category)}
    )


def declared_registry(cuit: str, category: str) -> MockArcaRegistry:
    """What the taxpayer says about themselves: the only lookup this app does."""
    return MockArcaRegistry(
        {cuit: TaxpayerProfile(cuit=cuit, name="Contribuyente declarado", category=category)}
    )


def parse_declared(surface_m2: str, energy_kwh: str, annual_rent: str) -> DeclaredParameters:
    """Turn the optional form fields into declared parameters, or explain why not."""
    labels = {"surface_m2": "superficie", "annual_energy_kwh": "energía", "annual_rent": "alquileres"}
    try:
        return DeclaredParameters(
            surface_m2=int(surface_m2) if surface_m2.strip() else None,
            annual_energy_kwh=int(energy_kwh) if energy_kwh.strip() else None,
            annual_rent=Decimal(annual_rent.replace(",", ".")) if annual_rent.strip() else None,
        )
    except ValueError as error:
        if isinstance(error, ValidationError):
            fields = sorted({labels[str(e["loc"][0])] for e in error.errors() if str(e["loc"][0]) in labels})
        else:
            fields = ["superficie, energía o alquileres"]
        raise FormError(
            f"Revisá {', '.join(fields)}: tiene que ser un número mayor o igual a cero."
        ) from error
    except InvalidOperation as error:
        raise FormError("Revisá alquileres: tiene que ser un número mayor o igual a cero.") from error


def alert_view(alert: dict) -> dict:
    """The interrupt payload, with labels and money the way the report shows them."""

    def money(value: str | None) -> str | None:
        return format_money(Decimal(value)) if value is not None else None

    def headroom(value: str | None, scope: str) -> tuple[str, str] | None:
        """A label and an amount; a passed cap is explained, never shown negative."""
        if value is None:
            return None
        amount = Decimal(value)
        if amount >= 0:
            return (f"Margen en {scope}", format_money(amount))
        return (f"Tope de {scope} superado por", format_money(-amount))

    return {
        "risk_label": RISK_LABELS.get(alert["risk_level"], alert["risk_level"]),
        "risk_level": alert["risk_level"],
        "registered_category": alert.get("registered_category"),
        "computed_category": alert.get("computed_category"),
        "accumulated_12m": money(alert.get("accumulated_12m")),
        "projected_12m": money(alert.get("projected_12m")),
        "headroom_registered": headroom(alert.get("headroom_registered"), "tu categoría"),
        "headroom_top": headroom(alert.get("headroom_top"), "el régimen"),
        "reasons": [REASON_LABELS.get(r, r) for r in alert.get("reasons", [])],
        "issues": alert.get("issues", []),
    }


def summary_view(summary: CaseSummary) -> dict:
    return {
        "case_id": summary.case_id,
        "status": STATUS_LABELS.get(summary.status, summary.status),
        "pending": summary.status == "pending",
        "taxpayer_cuit": summary.taxpayer_cuit,
        "registered_category": summary.registered_category or "-",
        "risk": RISK_LABELS.get(summary.risk_level or "", summary.risk_level or "-"),
        "created_at": (summary.created_at or "")[:16].replace("T", " "),
    }


def create_app(settings: WebSettings) -> FastAPI:
    """Assemble the application over one service and one checkpointer."""
    scales = load_scales()
    service = Copilot(
        scales=scales, policy=settings.policy, checkpointer=open_checkpointer(settings.state_db)
    )
    examples = load_examples(settings.cases_dir)
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    categories = [c.name for c in scales.categories]

    app = FastAPI(title="Copiloto de monotributo", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    token = settings.access_token
    # Reachable without a session: the login itself, and the stylesheet, which
    # holds nothing and whose absence would only make the login page ugly.
    open_paths = ("/entrar", "/static")

    if token:

        @app.middleware("http")
        async def require_session(request: Request, call_next):
            """One door in front of everything that is not the door itself."""
            path = request.url.path
            if path.startswith(open_paths) or session_is_valid(
                token, request.cookies.get(COOKIE_NAME)
            ):
                return await call_next(request)
            return RedirectResponse("/entrar", status_code=303)

        @app.get("/entrar", response_class=HTMLResponse)
        def login_form(request: Request):
            return render(request, "login.html", authenticated=False)

        @app.post("/entrar", response_class=HTMLResponse)
        def login(request: Request, token_field: str = Form("", alias="token")):
            if not token_matches(token, token_field):
                # Deliberately the same message for an empty field and a wrong
                # guess: which one it was is not the guesser's business.
                return render(
                    request,
                    "login.html",
                    status=401,
                    authenticated=False,
                    error="La clave no es correcta.",
                )
            entered = RedirectResponse("/", status_code=303)
            entered.set_cookie(
                COOKIE_NAME,
                session_value(token),
                max_age=COOKIE_MAX_AGE,
                httponly=True,
                samesite="lax",
            )
            return entered

        @app.post("/salir")
        def logout():
            left = RedirectResponse("/entrar", status_code=303)
            left.delete_cookie(COOKIE_NAME)
            return left

    def render(request: Request, template: str, status: int = 200, **context) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            template,
            {
                "disclaimer": Markup(_markdown.renderInline(DISCLAIMER_ES)),
                # Drives the "Salir" link: there is nothing to leave when the
                # copilot was never locked.
                "authenticated": settings.access_token is not None,
                **context,
            },
            status_code=status,
        )

    def home(request: Request, *, status: int = 200, error: str | None = None, form: dict | None = None):
        return render(
            request,
            "home.html",
            status=status,
            error=error,
            form=form or {},
            categories=categories,
            examples=list(examples.values()),
            cases=[summary_view(s) for s in service.list_cases()],
            extractor_mode=settings.extractor_mode,
            offline=settings.extractor_factory is None and settings.extractor_mode == "fake",
            arca_enabled=settings.arca_registry is not None,
        )

    def extractor_for_uploads():
        if settings.extractor_factory is not None:
            return settings.extractor_factory(None)
        if settings.extractor_mode == "fake":
            raise FormError(
                "El extractor `fake` solo conoce los casos de ejemplo y no puede leer una "
                "factura real. Arrancá el servidor con COPILOTO_EXTRACTOR=cli o =api."
            )
        try:
            return build_extractor_factory(settings.extractor_mode)(None)
        except ExtractionError as error:
            raise FormError(f"No pude preparar el lector de facturas: {error}") from error

    def read_uploads(uploads: list[UploadFile]) -> tuple[InvoiceSource, ...]:
        uploads = [u for u in uploads if u.filename]
        if not uploads:
            raise FormError("Subí al menos una factura en .txt o .pdf.")
        with tempfile.TemporaryDirectory() as folder:
            for index, upload in enumerate(uploads):
                name = Path(upload.filename or "factura").name
                (Path(folder) / f"{index:04d}-{name}").write_bytes(upload.file.read())
            try:
                return load_invoice_sources(Path(folder), ocr=settings.ocr)
            except SourceError as error:
                raise FormError(str(error)) from error

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        return home(request)

    @app.post("/casos", response_class=HTMLResponse)
    def start_case(
        request: Request,
        cuit: str = Form(""),
        category: str = Form(""),
        surface_m2: str = Form(""),
        energy_kwh: str = Form(""),
        annual_rent: str = Form(""),
        invoices: list[UploadFile] = File(default=[]),
    ):
        form = {
            "cuit": cuit,
            "category": category,
            "surface_m2": surface_m2,
            "energy_kwh": energy_kwh,
            "annual_rent": annual_rent,
        }
        try:
            cuit = cuit.strip()
            if not is_valid_cuit(cuit):
                raise FormError(f"El CUIT {cuit or '(vacío)'} no pasa el dígito verificador.")
            if settings.arca_registry is not None:
                if category and category not in categories:
                    raise FormError(
                        f"La categoría {category} no existe. Son: {', '.join(categories)}."
                    )
                case_registry = settings.arca_registry
            else:
                if not category or category not in categories:
                    raise FormError(
                        f"La categoría {category or '(vacía)'} no existe. Son: {', '.join(categories)}."
                    )
                case_registry = declared_registry(cuit, category)
            declared = parse_declared(surface_m2, energy_kwh, annual_rent)
            extractor = extractor_for_uploads()
            sources = read_uploads(invoices)
        except FormError as error:
            return home(request, status=400, error=str(error), form=form)

        scanned = ocr_issue(sources)
        case_id = uuid4().hex[:12]
        service.start(
            case_id=case_id,
            taxpayer_cuit=cuit,
            raw_invoices=tuple(s.text for s in sources),
            source_issues=(scanned,) if scanned else (),
            extractor=extractor,
            registry=case_registry,
            today=settings.clock(),
            declared=declared,
        )
        return RedirectResponse(f"/casos/{case_id}", status_code=303)

    @app.post("/casos/ejemplo/{example_id}", response_class=HTMLResponse)
    def start_example(request: Request, example_id: str):
        case = examples.get(example_id)
        if case is None:
            return render(request, "missing.html", status=404, what="ese ejemplo")

        case_id = f"ejemplo-{case.id}-{uuid4().hex[:6]}"
        service.start(
            case_id=case_id,
            taxpayer_cuit=case.taxpayer_cuit,
            raw_invoices=case.invoice_texts,
            extractor=fake_for(case),
            registry=registry_for(case),
            today=date.fromisoformat(case.today),
        )
        return RedirectResponse(f"/casos/{case_id}", status_code=303)

    @app.get("/casos/{case_id}", response_class=HTMLResponse)
    def show_case(request: Request, case_id: str):
        found = service.get(case_id)
        if found is None:
            return render(request, "missing.html", status=404, what="ese caso")
        if isinstance(found, PendingReview):
            return render(
                request,
                "review.html",
                case_id=case_id,
                alert=alert_view(found.alert),
                created_at=(found.created_at or "")[:16].replace("T", " "),
            )
        assert isinstance(found, Finished)
        return render(
            request,
            "report.html",
            case_id=case_id,
            report=Markup(_markdown.render(found.report)),
            decision=found.human_decision,
        )

    @app.post("/casos/{case_id}/revision", response_class=HTMLResponse)
    def review_case(request: Request, case_id: str, verdict: str = Form(""), notes: str = Form("")):
        found = service.get(case_id)
        if found is None:
            return render(request, "missing.html", status=404, what="ese caso")
        if not isinstance(found, PendingReview):
            return render(request, "missing.html", status=409, what="una revisión pendiente para este caso")

        # An unknown verdict confirms: an accountant who submits without
        # choosing must not silently clear the case.
        decision = HumanDecision(
            verdict=VERDICTS.get(verdict, "confirmed"), notes=notes.strip(), reviewer="accountant"
        )
        service.resume(case_id, decision)
        return RedirectResponse(f"/casos/{case_id}", status_code=303)

    return app
