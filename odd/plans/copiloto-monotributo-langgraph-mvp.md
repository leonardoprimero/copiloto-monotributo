# plan-final.md — Copiloto Monotributo (MVP con LangGraph 1.x)

Fecha: 2026-09-24. Síntesis única de `plan.md` (borrador) y `critique.md`. Este documento es autocontenido: no hace falta leer el borrador ni la crítica.

Estado de verificación, dicho sin vueltas:

- **Verificado contra archivos reales:** memoria del proyecto, índice `MEMORY.md`, `.gitignore`, estado del repo (sin commits, sin remote, sin `pyproject.toml`).
- **Consultado en vivo por el paso de exploración (digest, 2026-09-24), NO re-verificado por la crítica ni por esta síntesis:** `langgraph` 1.2.12 y `langchain-core` 1.6.4 en PyPI; la tabla ARCA vigente desde 2026-08-01 en https://www.arca.gob.ar/monotributo/categorias.asp.
- **No verificado por nadie todavía:** nombre exacto del checkpointer en memoria (`InMemorySaver` vs `MemorySaver`), presencia de la clave `__interrupt__` en el resultado de `invoke`, semántica de re-ejecución del nodo al reanudar, y formato de `draw_mermaid()` para aristas condicionales.

Por eso las tareas T2 y T3 son **verificaciones en vivo** contra el paquete instalado y contra arca.gob.ar. Son parte del trabajo, no supuestos. Si algo difiere, el código y este plan se ajustan ahí, con el resultado registrado en tests y en el README.

## 0. Decisiones confirmadas por el humano (2026-09-24)

Las seis preguntas abiertas de la síntesis quedaron respondidas antes de escribir código. Este plan ya las incorpora; §9 conserva el registro de qué se preguntó y qué se decidió.

| # | Pregunta | Decisión |
|---|---|---|
| 1 | Contrato de derivación (BLOCKING C1) | **Lectura literal: todo nivel distinto de `low` deriva a contador.** `RiskPolicy.review_levels = {medium, high, exclusion}`. |
| 2 | Publicación y licencia | Repo **público** en la cuenta de GitHub del humano, al final del MVP (T24), licencia **MIT**. |
| 3 | Proveedor de IA | **Tres modos de extractor:** `fake` (tests), `cli` (el CLI de IA que cada uno tenga instalado, sin API key) y `api` (proveedor con key, para quien quiera vender el servicio). |
| 4 | Ventana de 12 meses | **Móvil**: `(hoy − 1 año, hoy]`. |
| 5 | Categorías altas y tipo de actividad | **Mantener el supuesto de tabla única A–K para servicios y cosas muebles, documentado como tal.** T3 lo verifica en vivo contra arca.gob.ar; si la fuente muestra tablas separadas por actividad, se frena y se agrega `activity` al contribuyente. |
| 6 | Idioma de la salida al usuario | **Español rioplatense** para el informe, la CLI **y el README** (revisado durante T23: el público que consume esto es argentino, así que la documentación también va en su idioma). Código, identificadores, docstrings y mensajes de commit siguen en inglés. |

## 1. Objective (Objetivo)

Construir en un fin de semana un MVP público, en Python 3.12 con LangGraph 1.x, que lea facturas sintéticas con IA, valide con código (CUIT, montos, fechas), consulte un padrón ARCA simulado, calcule ingresos de los últimos 12 meses, categoría, proyección y riesgo de exclusión, y termine en un informe simple o en una derivación a contador con human-in-the-loop. Incluye evals sintéticos con respuesta conocida y README en inglés con diagrama y disclaimer.

Objetivo secundario, según la memoria del proyecto: convertir "estudié LangGraph" en "lo usé", con cada decisión defendible en una entrevista.

## 2. Problem (Problema)

- El repo `~/copiloto-monotributo` está en `main` sin commits, sin remote y sin `pyproject.toml`. Solo existe un `.gitignore` con `.atl/`.
- El Python por defecto es 3.14 y `langchain-core` advierte incompatibilidad con Pydantic V1 internals en 3.14. Hay `python3.12` y `uv 0.12.16` disponibles.
- No hay `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` ni `GOOGLE_API_KEY` en el entorno, y por decisión 3 **no se van a exigir**: tests y evals corren sin red, y el uso real por defecto es el CLI de IA que el usuario ya tenga.
- La API de LangGraph cambió en 1.0: `interrupt()` + `Command(resume=...)` reemplazan a `interrupt_before` y `update_state`. Lo que se recuerda de versiones viejas no sirve.
- Los topes del monotributo se actualizan cada semestre. La tabla vigente no puede quedar hardcodeada en la lógica.
- La memoria confirma que Leo no tiene código con LangChain/LangGraph y que varias vacantes lo piden como filtro.

## 3. Scope (Alcance)

In scope (fin de semana):

- Repo Python 3.12 gestionado con `uv`, layout `src/`, tests con `pytest`.
- Verificación en vivo de la API de LangGraph instalada (T2) y de la tabla ARCA (T3), con resultado registrado.
- Tabla ARCA A–K como config JSON versionada con `effective_from`, `retrieved_on` y `source`.
- Modelos de dominio con Pydantic v2 y `Decimal`. Los ítems distinguen `service`, `good` y `unknown`.
- Validaciones en código: dígito verificador de CUIT, coherencia de montos, precio unitario máximo, fechas, ventana móvil de 12 meses, y entrada vacía.
- Padrón ARCA mock con CUITs sintéticos, detrás de un `Protocol`.
- Extractor de facturas detrás de un `Protocol`, con **tres implementaciones**: `FakeExtractor` (tests y evals, sin red), `CliExtractor` (habla por subprocess con el CLI de IA instalado: codex, agy, claude u otro) y `ApiExtractor` (proveedor con API key y `with_structured_output`).
- Grafo LangGraph: 6 nodos, 1 arista condicional, 1 `interrupt()` para derivar a contador, checkpointer en memoria.
- Informe en markdown **en español rioplatense**, con disclaimer, nota de alcance argentino, base del cálculo (solo ingresos), causales no evaluadas y origen de la decisión (contador vs. reanudación automática).
- CLI **en español rioplatense** para correr un caso de eval con cualquiera de los tres extractores, con revisión interactiva del contador o reanudación automática etiquetada.
- Dataset de 14 casos sintéticos con respuesta conocida, runner de evals con accuracy de decisión y exactitud por campo de extracción.
- Diagrama Mermaid generado desde el grafo, con test de igualdad entre grafo, archivo y README.
- Publicación del repo como público, previa confirmación explícita.

Out of scope (v2, explícitamente):

- Facturas en PDF o imagen (OCR). El MVP recibe texto plano sintético.
- Modo `--invoices-dir` de la CLI (leer una carpeta de textos con IA). Movido a v2 para compensar el trabajo agregado por la crítica; los modos con IA se demuestran con `--case FILE --extractor cli|api`, que usan los `invoice_texts` del caso.
- Parámetros físicos (superficie, energía, alquileres), más de 3 actividades, gastos no justificados. La config los guarda; la lógica no los usa; el informe lo dice.
- Persistencia en disco con `SqliteSaver`. Solo checkpointer en memoria.
- Extractor determinístico por regex.
- Paralelizar extracción (Send API), reintentos con backoff, tracing con LangSmith.
- Interfaz web, multiusuario, autenticación, i18n del informe.
- **CI con GitHub Actions.** Movida a v2 para compensar los 20 min que agrega el tercer modo de extractor (decisión 3). No aporta ni al producto ni a la defensa en entrevista.
- Adaptadores de CLI para herramientas que no estén instaladas en esta máquina: quedan documentados en el README, sin inventar sus flags.
- Cualquier interacción con ARCA real o datos de clientes.

## 4. Architecture decisions (Decisiones de arquitectura)

### 4.1 Python 3.12 anclado con uv

Decisión: `uv init --python 3.12`, `.python-version` = `3.12`, `requires-python = ">=3.12,<3.13"`.
Razón: `langchain-core` advierte incompatibilidad en 3.14 y `python3.12` está instalado en `/opt/homebrew/bin/python3.12`.
Rechazado: Python 3.14 (advertencias de Pydantic V1). Python 3.13 (3.12 es la opción más probada para LangChain 1.x). Poetry o pip (no instalados; `uv` sí).

### 4.2 Estructura de paquetes (src layout)

```
copiloto-monotributo/
├── pyproject.toml
├── .python-version              # 3.12
├── docs/configuration.md        # COPILOTO_EXTRACTOR, COPILOTO_CLI, COPILOTO_EXTRACTOR_CMD,
│                                # COPILOTO_API_PROVIDER, COPILOTO_MODEL, <PROVIDER>_API_KEY
├── README.md
├── config/
│   └── monotributo_scales.json  # tabla ARCA vigente + effective_from + retrieved_on + source
├── docs/
│   └── graph.mmd                # generado con draw_mermaid()
├── evals/
│   └── cases/*.json             # 14 casos sintéticos con respuesta esperada
├── scripts/
│   ├── export_graph.py
│   └── build_eval_cases.py
├── src/copiloto/
│   ├── models.py                # InvoiceItem, ExtractedInvoice, Issue, TaxpayerProfile, Analysis, HumanDecision
│   ├── scales.py                # load_scales(), Scales.category_for_income()
│   ├── dates.py                 # one_year_before(), rolling_window()
│   ├── validation.py            # is_valid_cuit(), validate_invoice_amounts(), validate_invoice_dates()
│   ├── analysis.py              # accumulated_income(), projected_income(), assess_risk(), analyze(), RiskPolicy
│   ├── report.py                # render_report(), DISCLAIMER, NOT_EVALUATED
│   ├── synthetic.py             # render_invoice(), monthly_invoices()
│   ├── extractors/{protocol,fake,cli,api,resolve}.py
│   ├── arca/{protocol,mock}.py
│   ├── graph/{state,nodes,routing,builder,hitl}.py
│   ├── evals/{schema,runner,__main__}.py
│   └── cli.py
└── tests/                       # espejo de src/
```

Razón: separa dominio puro (validation, analysis, scales) del framework (graph/) y de los adaptadores (extractors/, arca/). El dominio se testea sin LangGraph ni red. `graph/hitl.py` encapsula cómo se detecta una interrupción, para que el resto del código no dependa del detalle que T2 verifica.
Rechazado: un solo `app.py` (mezcla capas). Layout plano sin `src/` (esconde errores de packaging).

### 4.3 "La IA lee, el código decide"

Decisión: el LLM solo transforma texto en un `ExtractedInvoice` estructurado. Toda decisión (CUIT válido, montos coherentes, ventana de fechas, categoría, riesgo, ruta del grafo) la toma código determinístico y testeado.
Razón: la memoria del proyecto lo fija como regla de diseño. Sin decisiones en el LLM, los evals con `FakeExtractor` prueban el 100 % de la lógica sin API key.
Rechazado: un agente con tools que decide categoría y riesgo (no auditable, no determinístico, imposible de defender ante un contador).

### 4.4 Tabla ARCA como config versionada con fecha de vigencia

Decisión: `config/monotributo_scales.json` con `source`, `effective_from`, `retrieved_on`, `max_unit_price`, `notes` y las 11 categorías. Montos como strings para parsear a `Decimal`. Un loader (`scales.py`) la expone como dataclasses inmutables.

Valores tomados del digest (fuente https://www.arca.gob.ar/monotributo/categorias.asp, vigencia 1 de agosto de 2026, consultada 2026-09-24). **T3 los re-verifica en vivo antes de commitearlos.**

| Cat | Ingresos brutos anuales | Superficie | Energía anual | Alquileres anuales |
|:--:|--:|:--:|:--:|--:|
| A | 12.009.410,45 | 30 m² | 3.330 Kw | 2.792.886,15 |
| B | 17.595.182,74 | 45 m² | 5.000 Kw | 2.792.886,15 |
| C | 24.670.494,31 | 60 m² | 6.700 Kw | 3.816.944,41 |
| D | 30.628.651,43 | 85 m² | 10.000 Kw | 3.816.944,41 |
| E | 36.028.231,33 | 110 m² | 13.000 Kw | 4.841.002,66 |
| F | 45.151.659,41 | 150 m² | 16.500 Kw | 4.841.002,66 |
| G | 53.995.798,87 | 200 m² | 20.000 Kw | 5.771.964,69 |
| H | 81.924.660,37 | 200 m² | 20.000 Kw | 8.378.658,45 |
| I | 91.699.761,90 | 200 m² | 20.000 Kw | 8.378.658,45 |
| J | 105.012.519,20 | 200 m² | 20.000 Kw | 8.378.658,45 |
| K | 126.610.838,75 | 200 m² | 20.000 Kw | 8.378.658,45 |

Precio unitario máximo (venta de cosas muebles): 716.840,77 para todas las categorías.

**Supuesto de dominio declarado (riesgo abierto, ver §6):** el MVP asume que las 11 categorías aplican a cualquier actividad (servicios o venta de cosas muebles), porque la tabla digerida es única y no tiene columnas por tipo de actividad. Históricamente las categorías altas estuvieron limitadas a venta de cosas muebles; este plan no afirma ni niega que siga así. T3 lo verifica contra la página en vivo y, si hay una división por actividad, se escala antes de T4.

Razón: los valores cambian cada semestre; el informe y el README muestran la fecha de vigencia usada; actualizar es editar un JSON y correr los tests.
Rechazado: constantes en `analysis.py`. Scrapear ARCA en runtime.

### 4.5 Extractor y padrón detrás de Protocols

Decisión: `InvoiceExtractor` (`extract(raw: str) -> ExtractedInvoice`) y `TaxpayerRegistry` (`lookup(cuit) -> TaxpayerProfile | None`) como `typing.Protocol` con `@runtime_checkable`. Padrón: `MockArcaRegistry`.
Razón: tests y evals sin API key. Un Protocol permite inyectar el fake sin herencia.
Rechazado: clase base abstracta. Monkeypatch del cliente LLM en cada test.

### 4.5.1 Tres modos de extractor (decisión 3)

El mismo `Protocol`, tres implementaciones. Se elige con `COPILOTO_EXTRACTOR` o con el flag `--extractor` de la CLI.

| Modo | Para quién | Implementación | Dependencias |
|---|---|---|---|
| `fake` (default) | Tests y evals | `FakeExtractor(mapping)`: texto conocido → factura conocida | Ninguna. Sin red. |
| `cli` | El dueño del repo y cualquiera que lo clone | `CliExtractor`: `subprocess` contra el CLI de IA instalado | Ninguna de Python. Solo el binario que ya tenga el usuario. |
| `api` | Un contador que quiera vender el servicio | `ApiExtractor`: chat model de LangChain con `with_structured_output` | Extra opcional `api` + API key |

**Modo `cli` — agnóstico de proveedor.** Un registro de adaptadores mapea binario conocido → invocación no interactiva:

```python
KNOWN_CLI_ADAPTERS = {"codex": ..., "agy": ..., "claude": ...}   # forma exacta resuelta en T19
```

Resolución, en orden:

1. `COPILOTO_EXTRACTOR_CMD` — escape hatch genérico. El prompt va por `stdin`, la respuesta se lee de `stdout`. Sirve para cualquier herramienta, presente o futura.
2. `COPILOTO_CLI` — el humano elige explícitamente entre los adaptadores conocidos.
3. Autodetección con `shutil.which()` sobre `KNOWN_CLI_ADAPTERS`, en orden estable y documentado.
4. Si no hay ninguno: error claro que nombra las tres opciones. **Nunca cae en silencio a `fake`**, porque un fallback mudo daría la ilusión de que un modelo leyó las facturas.

**Lo que se pierde en `cli` y hay que programar a mano:** sin `with_structured_output` no hay garantía de forma. `CliExtractor` pide JSON con el esquema en el prompt, extrae el primer objeto JSON balanceado de la respuesta (tolerando preámbulo y vallas de markdown), valida con Pydantic y **reintenta una sola vez** con un mensaje correctivo. Si el segundo intento falla, levanta `ExtractionError` y el nodo emite `EXTRACTION_FAILED`, que ya deriva a contador.

**Los flags exactos de cada CLI no se escriben de memoria.** T19 los resuelve probando `--help` contra los binarios realmente instalados en la máquina. Los que no estén instalados quedan documentados como adaptadores pendientes en el README, sin inventar su invocación. Es la misma disciplina que se aplica a LangGraph (T2) y a ARCA (T3).

**Modo `api` — el camino de producción.** `COPILOTO_API_PROVIDER=anthropic|openai` selecciona el chat model; `COPILOTO_MODEL` fija el identificador. Extra opcional: `uv sync --extra api`. Es el único modo con forma garantizada, paralelizable y con versión de modelo trazable — requisito real si alguien va a cobrar por los informes.

Razón de fondo: el repo público no debe exigir una API key para demostrar nada. Con `fake` corren todos los tests y evals recién clonado; con `cli` cualquiera lo prueba con su propia herramienta; con `api` se vuelve un servicio. **El grafo, los nodos, las validaciones y los evals no se enteran de cuál está abajo**, y esa es la justificación concreta de haber puesto un Protocol ahí.
Rechazado: acoplar el MVP a un único proveedor; caer a `fake` cuando no hay CLI (engañoso); parsear la respuesta del CLI con regex por campo en lugar de JSON + Pydantic.

### 4.6 Inyección de dependencias por closures en los nodos

Decisión: cada nodo se crea con una fábrica (`make_extract_node(extractor)`, `make_analyze_node(scales, today, policy)`, `make_report_node(scales)`) y `build_graph(extractor=..., registry=..., scales=..., today=..., policy=..., checkpointer=None)` arma y compila el grafo. El router también se crea con `make_router(policy)`.
Razón: `add_node(node, action)` acepta cualquier callable; las closures no requieren APIs adicionales.
Rechazado: pasar dependencias por `config["configurable"]` o por el contexto de runtime (no verificados; más conceptos que explicar).

### 4.7 Decimal para dinero y reloj inyectado

Decisión: todos los montos son `Decimal` con 2 decimales; `today: date` es parámetro explícito de validación, análisis y grafo.
Razón: los topes tienen centavos y el límite es inclusivo; con `today` inyectado, tests y evals son reproducibles cualquier día.
Rechazado: float, `datetime.now()` dentro de la lógica.

### 4.8 Diseño del grafo LangGraph

APIs usadas, según el digest (langgraph 1.2.12, langchain-core 1.6.4). Las marcadas con (T2) se confirman en vivo:

| Uso | API |
|---|---|
| Construcción | `StateGraph(State)`, `START`, `END`, `add_node`, `add_edge`, `add_conditional_edges(source, path, path_map)`, `compile(checkpointer=...)` |
| Estado | `TypedDict` + `Annotated[list[Issue], operator.add]` |
| Human-in-the-loop | `langgraph.types.interrupt(payload)` dentro del nodo; reanudar con `graph.invoke(Command(resume=...), config)` |
| Checkpointer | `langgraph.checkpoint.memory.InMemorySaver` esperado; `MemorySaver` como alternativa (T2) |
| Detección de pausa | `"__interrupt__"` en el resultado de `invoke` esperado; alternativa `graph.get_state(config).tasks[*].interrupts` (T2). Encapsulado en `graph/hitl.py::pending_interrupt(graph, config, result)` |
| Diagrama | `graph.get_graph().draw_mermaid()` |
| Extracción | `model.with_structured_output(PydanticSchema)` |

APIs prohibidas (deprecadas según el digest): `compile(interrupt_before=..., interrupt_after=...)`, `graph.update_state(...)` + `graph.invoke(None)`, `ToolExecutor`, importar `SqliteSaver` sin instalar `langgraph-checkpoint-sqlite`.

Estado:

```python
class CopilotState(TypedDict, total=False):
    taxpayer_cuit: str                              # input
    raw_invoices: list[str]                         # input: textos sintéticos
    invoices: list[ExtractedInvoice]                # extract_invoices (pisa)
    issues: Annotated[list[Issue], operator.add]    # varios nodos agregan; reducer concatena
    taxpayer: TaxpayerProfile | None                # lookup_taxpayer
    analysis: Analysis | None                       # analyze_income
    human_decision: HumanDecision | None            # request_accountant_review (tras resume)
    report: str                                     # write_report
```

Nodos:

| Nodo | Lee | Escribe | Responsabilidad |
|---|---|---|---|
| `extract_invoices` | `raw_invoices` | `invoices`, `issues` | Llama al extractor por cada texto. Si falla uno, agrega `EXTRACTION_FAILED` (error) y sigue. Si `raw_invoices` está vacío, agrega `NO_INVOICES` (warning). IA lee. |
| `validate_invoices` | `invoices`, `taxpayer_cuit` | `issues` | CUIT (`INVALID_CUIT`, `ISSUER_MISMATCH`), montos (`TOTAL_MISMATCH`, `NON_POSITIVE_AMOUNT`, `UNIT_PRICE_ABOVE_MAX`, `UNIT_PRICE_KIND_UNKNOWN`), fechas (`DATE_IN_FUTURE`, `OUTSIDE_WINDOW`). Código decide. |
| `lookup_taxpayer` | `taxpayer_cuit` | `taxpayer`, `issues` | Padrón mock. Si no existe, `TAXPAYER_NOT_FOUND` (warning). |
| `analyze_income` | `invoices`, `issues`, `taxpayer` | `analysis` | Acumulado 12 meses, categoría calculada, proyección, nivel de riesgo y razones. |
| `request_accountant_review` | `analysis`, `issues` | `human_decision` | Arma la alerta y llama `interrupt(alert)`. Al reanudar, guarda la decisión. |
| `write_report` | todo | `report` | Adapta el estado a `render_report(...)` y escribe `{"report": ...}`. |

Aristas:

```
START → extract_invoices → validate_invoices → lookup_taxpayer → analyze_income
analyze_income ──(route_after_analysis)──► "ok"     → write_report
                                        └► "review" → request_accountant_review → write_report
write_report → END
```

Arista condicional: `add_conditional_edges("analyze_income", make_router(policy), {"ok": "write_report", "review": "request_accountant_review"})`.

Router (función pura): devuelve `"review"` si `analysis.risk_level ∈ policy.review_levels` o existe algún issue con severidad `warning` o `error`; si no, `"ok"`. Los issues `info` (por ejemplo `OUTSIDE_WINDOW`) no derivan.

Dónde va el `interrupt()`: dentro de `request_accountant_review`, después de armar el payload con una función pura y antes de cualquier efecto. Payload: `{"risk_level", "reasons", "issues", "accumulated_12m", "computed_category", "registered_category"}`. Reanudación: `graph.invoke(Command(resume={"verdict": "confirmed" | "dismissed", "notes": str, "reviewer": "accountant" | "auto"}), config)`.

Checkpointer: obligatorio para `interrupt()`. En memoria por defecto en `build_graph`, con `config={"configurable": {"thread_id": ...}}` en cada invocación. La CLI mantiene el proceso vivo entre pausa y reanudación.

Rechazado: segunda arista condicional después de `validate_invoices` para cortar temprano (más ramas; el contador se beneficia de ver el análisis parcial). Ciclos o agentes con tools.

### 4.9 Política de riesgo y ruteo

| Nivel | Condición | Ruta (default) |
|---|---|---|
| `low` | Nada de lo siguiente | ok |
| `medium` | acumulado ≥ 90 % del tope de la categoría registrada, o categoría calculada ≠ registrada, o proyección > tope registrado | **review** (ver pregunta 1) |
| `high` | proyección 12 meses > tope K, o acumulado ≥ 90 % del tope K | review |
| `exclusion` | acumulado 12 meses > tope K, o algún `UNIT_PRICE_ABOVE_MAX` | review |

Cuando aplican varias condiciones, gana el nivel más alto. Cualquier issue `warning`/`error` fuerza `review` sin importar el nivel. Sin contribuyente en el padrón no se evalúan las condiciones que dependen de la categoría registrada.

**Contrato de derivación (resuelve C1).** El pedido original dice: "riesgo o dato dudoso → alerta y derivar a un contador". El default del plan sigue esa lectura literal: **todo nivel distinto de `low` deriva.** El conjunto vive en `RiskPolicy.review_levels = frozenset({"medium", "high", "exclusion"})`. Si el humano prefiere que `medium` termine en informe con aviso, se cambia esa línea, se regeneran los evals con el script y cambian tres expectativas (`near_cap`, `category_change`, `boundary_exact_cap`). Los tests de ruteo se parametrizan sobre la política, así ninguna de las dos respuestas queda "fijada" en el código.

Definiciones:
- Ventana móvil: `(one_year_before(today), today]`; 29 de febrero se lleva a 28.
- Acumulado: suma de `total` de las facturas dentro de la ventana (las facturas con issues se suman igual; el issue ya deriva a revisión).
- Proyección: suma de los últimos 90 días ÷ 90 × 365, redondeada a 2 decimales. Política de la app, no fórmula de ARCA.
- Tope inclusivo: "hasta X" significa `ingreso <= X`.
- Entrada vacía: `NO_INVOICES` (warning) → review. Cero facturas no es "todo en orden"; es falta de datos.
- Umbrales (`near_cap_ratio = 0.9`, `projection_days = 90`, `review_levels`) viven en `RiskPolicy` en `analysis.py`, no en la config de ARCA.

### 4.10 Diseño de evals

Estructura de cada caso (`evals/cases/<id>.json`, validado por `EvalCase`):

```json
{
  "id": "near_cap",
  "description": "Twelve monthly invoices at 95% of the category A cap",
  "today": "2026-09-24",
  "taxpayer_cuit": "20-11111111-2",
  "registry_entry": {"cuit": "20-11111111-2", "name": "Synthetic Taxpayer One", "category": "A"},
  "invoices": [ { "...ExtractedInvoice ground truth..." } ],
  "invoice_texts": [ "FACTURA C ... (rendered text, same order)" ],
  "expected": {"route": "review", "risk_level": "medium", "computed_category": "A", "issue_codes": []}
}
```

Los 14 casos, todos con `today = 2026-09-24`, facturas el día 15 de cada mes, generados por `scripts/build_eval_cases.py`. Salvo que se indique otra cosa, cada caso parte de la base `all_in_order` (12 × 800.000, contribuyente A `20-11111111-2`) con una sola modificación, así el `risk_level` de los casos de "dato dudoso" es verificable: el acumulado se mantiene en 9.600.000 o menos, lejos del 90 % de A (10.808.469,41).

| ID | Escenario | Cat. registrada | Esperado (route, risk, computed, issues) |
|---|---|---|---|
| `all_in_order` | 12 × 800.000 | A | ok, low, A, [] |
| `near_cap` | 12 × 950.000 (11,4 M ≥ 90 % de A) | A | review, medium, A, [] |
| `category_change` | 12 × 1.200.000 (14,4 M > tope A) | A | review, medium, B, [] |
| `boundary_exact_cap` | suma exacta 12.009.410,45 | A | review, medium, A, [] |
| `date_outside_window` | base + factura 2025-09-15 de 5 M | A | ok, low, A, [OUTSIDE_WINDOW] |
| `invalid_cuit` | una factura con emisor `20-11111111-3` | A | review, low, A, [INVALID_CUIT] |
| `date_in_future` | una factura fechada 2026-12-15 | A | review, low, A, [DATE_IN_FUTURE] |
| `total_mismatch` | una factura con total 800.000 e ítems que suman 700.000 | A | review, low, A, [TOTAL_MISMATCH] |
| `unit_price_above_max` | base + factura con un ítem `good`, qty 1, a 716.840,78 | A | review, exclusion, A, [UNIT_PRICE_ABOVE_MAX] |
| `unit_price_kind_unknown` | igual que el anterior pero con `kind` omitido | A | review, low, A, [UNIT_PRICE_KIND_UNKNOWN] |
| `exclusion_by_income` | 12 × 11.000.000 = 132 M > K | K (`27-22222222-8`) | review, exclusion, null, [] |
| `projected_exclusion` | 9 × 5 M + 3 × 12 M (proyección 146 M) | H (`30-44444444-0`) | review, high, H, [] |
| `unknown_taxpayer` | CUIT válido `23-33333333-3` sin entrada en padrón | ninguna | review, low, A, [TAXPAYER_NOT_FOUND] |
| `empty_input` | `raw_invoices = []` | A | review, low, A, [NO_INVOICES] |

Aritmética verificada por la crítica: `near_cap` 11.400.000 / proyección 11.558.333,33; `category_change` 14.400.000 / 14.600.000; `exclusion_by_income` 132.000.000; `projected_exclusion` 81.000.000 ≤ 81.924.660,37 → H, proyección 36.000.000 ÷ 90 × 365 = 146.000.000; `716.840,78` supera el máximo por un centavo.

CUITs sintéticos con dígito verificador válido (módulo 11, pesos 5-4-3-2-7-6-5-4-3-2), verificados a mano por la crítica: `20-11111111-2`, `27-22222222-8`, `23-33333333-3`, `30-44444444-0` (caso "resto 11 → 0"). `20-00000001-X` es inválido para cualquier X (resto 10).

Métrica de decisión: un caso "acierta" si coinciden `route`, `risk_level`, `computed_category` y el conjunto de `issue_codes`. Accuracy = aciertos / total, con tabla por caso. La ruta se observa con `pending_interrupt(...)`; el runner reanuda con una decisión enlatada `reviewer="auto"` para verificar que el informe se produce.

Métrica de extracción (resuelve C5): por cada factura, el runner compara `issuer_cuit`, `issue_date` y `total` extraídos contra el ground truth del caso y reporta exactitud por campo. Una lectura incorrecta cuenta como error de extracción aunque no cambie la decisión. Con fake es trivialmente 100 %; con LLM es la medida real de lectura. Un test lo demuestra con un extractor que devuelve una fecha corrida un día.

Umbrales:
- `--extractor fake`: 100 % de decisión obligatorio. Corre dentro de `pytest`.
- `--extractor cli` o `--extractor api`: ≥ 90 % de decisión, más el reporte de exactitud por campo. Informativo, depende de la herramienta o la key disponible, **no bloquea** ni el commit ni la publicación.

### 4.11 README en inglés

Estructura:

1. Título y una línea: "Copiloto Monotributo — a LangGraph copilot for Argentine monotributistas".
2. Disclaimer en blockquote, inmediatamente debajo del título, texto exacto:

> **Disclaimer.** This project is for informational and educational purposes only. It is not tax or legal advice and does not replace a licensed accountant. It never files anything with ARCA: it does not submit returns, recategorize, or perform any procedure on your behalf. All invoices, CUITs and taxpayers in this repository are synthetic.

3. What it does (5 bullets: extract, validate, look up, analyze, report or escalate).
4. The graph: bloque ` ```mermaid ` con el contenido exacto de `docs/graph.mmd`, tabla de nodos, reglas de ruteo, cómo funciona la pausa y la reanudación.
5. Design principles: "The AI reads, the code decides"; versioned ARCA scales (effective 2026-08-01, source URL, retrieved date real de T3); swappable extractor via Protocol; synthetic data only; injected clock. Sub-sección "Verified against": versión de `langgraph` instalada y fecha, resultado de T2 (nombre del checkpointer, detección de interrupt, re-ejecución del nodo).
6. What it does NOT evaluate: parámetros físicos, actividades, gastos no justificados, y la aclaración de que la categoría estimada se basa solo en ingresos.
7. **Choosing an extractor** (decisión 3), con la tabla de §4.5.1 y las variables de entorno:

   ```
   COPILOTO_EXTRACTOR=fake   # default: tests and evals, no network
   COPILOTO_EXTRACTOR=cli    # use whichever AI CLI you already have
   COPILOTO_EXTRACTOR=api    # bring your own API key (service deployments)
   ```

   Con la aclaración de que el modo `cli` autodetecta el binario, que `COPILOTO_EXTRACTOR_CMD` acepta cualquier herramienta, y la lista de adaptadores verificados vs. pendientes según lo que T19 haya podido probar.
8. Quickstart: requisitos (uv, Python 3.12); `uv sync`; demo offline (`uv run copiloto run --case evals/cases/all_in_order.json`); demo con revisión (`... exclusion_by_income.json`); demo sin teclado (`--auto-resume`, explicando que el informe lo marca como no revisado); demo con el CLI propio (`COPILOTO_EXTRACTOR=cli`, sin instalar nada extra); uso con API (`uv sync --extra api`, `COPILOTO_API_PROVIDER`, la key del proveedor, `--extractor api`).
9. **Report language**: una línea explicando que la CLI y el informe salen en español rioplatense porque el producto se consume en Argentina, mientras que el código y esta documentación están en inglés.
10. Tests and evals: comandos, qué mide cada modo, última accuracy.
11. Monotributo scales used: tabla A–K, precio unitario máximo, fuente, fecha de vigencia y de consulta.
12. Project layout.
13. Roadmap / out of scope (lista v2 de §3).
14. License: MIT (decisión 2), con `LICENSE` en la raíz a nombre del humano.

La misma cadena del disclaimer vive en `report.DISCLAIMER_EN` y un test (T23) verifica que el README la contenga y que el bloque Mermaid sea idéntico a `docs/graph.mmd`.

### 4.12 Convenciones de trabajo

- TDD estricto por tarea: test primero (rojo), implementación mínima (verde), refactor con tests verdes, commit.
- Un commit por tarea, conventional commits en inglés, sin trailers de atribución de IA.
- Commits directo en `main` (repo nuevo, una persona, un fin de semana).
- Código, identificadores, comentarios, commits y README en inglés. Los textos de facturas sintéticas imitan etiquetas reales en castellano porque son datos de dominio.
- Cada tarea trae una explicación en castellano simple, pensada para defenderla en entrevista.

### 4.13 Idioma de la salida al usuario (decisión 6)

Dos idiomas, con una frontera clara:

| Superficie | Idioma | Por qué |
|---|---|---|
| Código, identificadores, comentarios, docstrings, commits | Inglés | Convención técnica; el código lo leen desarrolladores |
| **Informe, CLI y README** | **Español rioplatense** | **El público que consume esto es argentino** |

Revisión durante T23: el pedido original ponía el README en inglés. Se cambió a español con un argumento mejor — un monotributista no lee documentación en inglés, y el idioma de un producto lo define quién lo usa, no la costumbre. `DISCLAIMER_EN` se eliminó al quedar sin consumidor.

El informe abre con una nota de alcance antes del disclaimer:

> Este informe está escrito en español rioplatense porque el monotributo es un régimen argentino y este copiloto se usa en Argentina.

**Registro:** voseo y naturalidad, **tono profesional, cero slang.** Un informe que avisa "estás a un paso de quedar excluido del régimen" no puede sonar a chiste. Los términos fiscales se escriben como los escribe ARCA ("ingresos brutos", "recategorización", "exclusión"), no en versión coloquial.

Implementación: todas las cadenas de usuario viven en `report.py` y `cli.py`. `DISCLAIMER_ES` es la fuente de verdad del informe; `DISCLAIMER_EN` es su traducción para el README. Un test (T12) verifica que ambas conserven las tres cláusulas obligatorias: orientativo, no reemplaza a un contador, nunca presenta trámites.

## 5. Task breakdown (Desglose de tareas)

Cada tarea sigue el ciclo rojo → verde → refactor → commit. Tiempos en minutos. **Total: 890 min (14 h 50 min).** Sábado T1–T13 (415 min ≈ 6 h 55 min), domingo T14–T24 (475 min ≈ 7 h 55 min).

De dónde sale el número:

| Etapa | Total |
|---|---:|
| Borrador original | 740 |
| + hallazgos aceptados de la crítica | +110 |
| − modo `--invoices-dir` a v2 | −15 |
| Plan sintetizado | **835** |
| + tres modos de extractor, decisión 3 (T19: 45 → 90) | +45 |
| + selección de extractor y mensajes en español en la CLI, decisiones 3 y 6 (T22: 30 → 40) | +10 |
| **Plan final** | **890** |

La CI con GitHub Actions (ex T25, 20 min) salió del alcance hacia v2, pero ya era opcional, así que **no descuenta del total.**

Dicho sin maquillaje: **el domingo son casi 8 horas.** Eso entra, pero no deja margen para imprevistos. Si el sábado se estira o T3 obliga a agregar `activity`, hay que usar el recorte de emergencia del final de esta sección **sin culpa** — está ordenado justamente para que lo primero que se caiga sea lo que menos duele.

### T1 — Bootstrap del proyecto con uv y Python 3.12
- Commit: `chore: bootstrap project with uv and python 3.12`
- Test primero: `tests/test_smoke.py::test_package_imports_under_python_312` asserta `import copiloto`, `import langgraph` y `sys.version_info[:2] == (3, 12)`. El rojo real es `ModuleNotFoundError` en `copiloto` y `langgraph`, no un fallo del runner: primero se instala `pytest` solo, se corre y se ve ese error concreto.
- Implementación mínima: `uv init --python 3.12` con layout `src/copiloto/`; `uv add "langgraph>=1.2,<2" "pydantic>=2,<3"`; `uv add --dev pytest`; `requires-python = ">=3.12,<3.13"`; `.python-version`; `.gitignore` con `.venv/`, `__pycache__/`, `.pytest_cache/`, `.env`, `*.db` (conservar `.atl/`); `.env.example`.
- Aceptación: `uv run pytest` verde; `uv run python -c "import sys; print(sys.version)"` imprime 3.12.x; `git log --oneline` muestra un commit.
- 25 min.
- Explicación: `uv` es el gestor de entorno y dependencias; con `.python-version` fijamos 3.12 porque LangChain todavía no está cómodo en 3.14. El test de humo garantiza que cualquiera que clone el repo arranque con el mismo intérprete y las mismas librerías.

### T2 — Grafo esqueleto y verificación en vivo de la API 1.x
- Commit: `feat(graph): add walking skeleton and verify langgraph 1.x interrupt semantics`
- Test primero, `tests/graph/test_hello_graph.py`:
  - `test_two_nodes_run_in_order_and_accumulate_steps`: `build_hello_graph().invoke({"steps": []})["steps"] == ["extract", "report"]`.
  - `test_in_memory_checkpointer_import`: `from langgraph.checkpoint.memory import InMemorySaver`. Si falla, se prueba `MemorySaver` y se deja el nombre que funcione en `graph/hitl.py::make_checkpointer()`.
  - `test_invoke_exposes_pending_interrupt`: grafo de dos nodos donde el segundo llama `interrupt("question")`; se invoca con `thread_id`; asserta que `pending_interrupt(graph, config, result)` devuelve el payload. Primero se intenta `result["__interrupt__"]`; si no existe, `graph.get_state(config).tasks[*].interrupts`. La implementación de `pending_interrupt` queda con la variante que funcione.
  - `test_resume_returns_value_inside_node_and_reruns_node`: el nodo incrementa un contador (inyectado) antes de `interrupt()`; tras `invoke(Command(resume="answer"), config)` asserta que el nodo recibió `"answer"` y registra cuántas veces corrió. Se espera 2 (re-ejecución desde el inicio). El valor observado se documenta en el test y en el README.
- Implementación mínima: `src/copiloto/graph/hello.py` con `HelloState(TypedDict)` (`steps: Annotated[list[str], operator.add]`), dos nodos, `StateGraph`, `add_edge(START, ...)`, `compile()`; `src/copiloto/graph/hitl.py` con `make_checkpointer()` y `pending_interrupt(graph, config, result)`. Se anota `importlib.metadata.version("langgraph")` en el cuerpo del commit.
- Aceptación: los cuatro tests verdes contra el paquete realmente instalado; `hitl.py` refleja lo observado, no lo recordado.
- 40 min.
- Explicación: un grafo de LangGraph tiene tres cosas: un estado compartido (un dict tipado), nodos (funciones que reciben el estado y devuelven solo lo que cambió) y aristas (quién sigue a quién). Antes de meter negocio, probamos con un mini-grafo las dos cosas que más cambiaron en la versión 1.0: cómo se pausa (`interrupt`) y cómo se reanuda (`Command(resume=...)`). Así, lo que después le digas a un entrevistador lo viste correr en tu máquina, no lo leíste.

### T3 — Tabla ARCA como config versionada, verificada en vivo
- Commit: `feat(scales): add ARCA monotributo scales as versioned config`
- Paso previo (sin código): abrir https://www.arca.gob.ar/monotributo/categorias.asp y comparar, fila por fila, las 11 categorías, los cuatro parámetros, el precio unitario máximo y la fecha de vigencia con la tabla de §4.4. Confirmar además si la página muestra una tabla única o separada por tipo de actividad (servicios vs. venta de cosas muebles). Si algún valor difiere, la página gana; el cuerpo del commit dice qué cambió. Si la tabla está dividida por actividad, se frena y se escala (ver §6 y pregunta 5).
- Test primero: `tests/test_scales.py::test_load_scales_reads_effective_date_and_eleven_categories` asserta `effective_from == date(2026, 8, 1)` (o la fecha vista en vivo), 11 categorías `A..K` en orden, `by_code("K").max_annual_income == Decimal("126610838.75")`, `max_unit_price == Decimal("716840.77")`, `source` empieza con `https://www.arca.gob.ar`, `retrieved_on` es una fecha.
- Implementación mínima: `config/monotributo_scales.json` con los valores confirmados como strings, `retrieved_on` = fecha real de la consulta, `notes` con el supuesto de actividad única; `scales.py` con dataclasses `Category`, `Scales` y `load_scales(path=DEFAULT_PATH)`.
- Aceptación: test verde; el JSON tiene `source`, `effective_from`, `retrieved_on`, `notes`.
- 40 min.
- Explicación: los topes cambian cada semestre, así que son datos, no código. Los miramos en la página oficial el mismo día que los guardamos y dejamos escrita la fecha. Guardarlos en un JSON con vigencia y fuente permite actualizarlos sin tocar la lógica y mostrar en el informe qué tabla se usó. Los montos van como texto para que `Decimal` no herede errores de float.

### T4 — Categoría a partir del ingreso anual
- Commit: `feat(scales): resolve category from rolling annual income`
- Test primero: `tests/test_scales.py::test_category_for_income_boundaries` parametrizado: `0 → A`, `12009410.45 → A`, `12009410.46 → B`, `126610838.75 → K`, `126610838.76 → None`.
- Implementación mínima: `Scales.category_for_income(income)` devuelve la primera categoría con `income <= max_annual_income`; `None` si supera K.
- Aceptación: test verde con los cinco bordes.
- 20 min.
- Explicación: la categoría es la primera cuyo tope alcanza al ingreso acumulado; "hasta" es inclusivo. Devolver `None` cuando se supera K deja explícito el caso de exclusión en vez de esconderlo en una excepción.

### T5 — Modelos de dominio
- Commit: `feat(models): add invoice, issue and taxpayer domain models`
- Test primero: `tests/test_models.py::test_invoice_items_total_sums_quantity_times_unit_price`, `test_invoice_parses_money_and_dates_from_strings`, `test_item_kind_defaults_to_unknown_when_omitted`, `test_human_decision_reviewer_defaults_to_accountant`.
- Implementación mínima: `models.py` con `InvoiceItem` (`description`, `quantity`, `unit_price`, `kind: Literal["service", "good", "unknown"] = "unknown"`), `ExtractedInvoice` (`invoice_number`, `issue_date`, `issuer_cuit`, `items`, `total`, propiedad `items_total`), `Issue` (`code`, `severity: Literal["info","warning","error"]`, `message`, `invoice_number | None`), `TaxpayerProfile` (`cuit`, `name`, `category`), `Analysis`, `HumanDecision` (`verdict: Literal["confirmed","dismissed"]`, `notes`, `reviewer: Literal["accountant","auto"] = "accountant"`).
- Aceptación: tests verdes; sin restricciones de signo en montos (los negativos se reportan como issues en T7).
- 25 min.
- Explicación: los modelos son el contrato entre la IA y el código. Pydantic valida tipos y convierte strings a `Decimal` y `date`. Que el tipo de ítem por defecto sea "desconocido" y no "servicio" es a propósito: si la IA no lo supo, el código no debe adivinar a favor del contribuyente. Que un monto negativo no rompa el modelo también es a propósito: queremos un issue que derive a revisión, no un crash.

### T6 — Validación de CUIT
- Commit: `feat(validation): validate CUIT check digit`
- Test primero: `tests/test_validation_cuit.py::test_is_valid_cuit` parametrizado: válidos `20-11111111-2`, `27-22222222-8`, `30-44444444-0`, `20111111112`; inválidos `20-11111111-3`, `20-00000001-0`, `123`, `20-1111111A-2`.
- Implementación mínima: `is_valid_cuit(cuit)` normaliza, exige 11 dígitos, aplica pesos `5,4,3,2,7,6,5,4,3,2`, `r = 11 - (suma % 11)`, `r == 11 → 0`, `r == 10 → inválido`, compara con el último dígito.
- Aceptación: test verde incluyendo "resto 11 → 0" y "resto 10 → inválido".
- 30 min.
- Explicación: el CUIT trae un dígito verificador calculado con módulo 11. Validarlo en código es barato, determinístico y atrapa la mayoría de los errores de lectura de la IA. Es un ejemplo perfecto de "el código decide".

### T7 — Validación de montos y precio unitario máximo
- Commit: `feat(validation): validate invoice amounts against scales`
- Test primero, `tests/test_validation_amounts.py`: `test_total_mismatch_yields_warning`, `test_non_positive_amount_yields_error`, `test_good_unit_price_above_max_yields_error` (716840.78 `good` → error; 716840.77 `good` → sin issue), `test_service_unit_price_above_max_yields_nothing`, `test_unknown_kind_unit_price_above_max_yields_warning` (716840.78 `unknown` → `UNIT_PRICE_KIND_UNKNOWN` warning; 716840.77 `unknown` → sin issue).
- Implementación mínima: `validate_invoice_amounts(invoice, scales) -> list[Issue]` con tolerancia `Decimal("0.01")`.
- Aceptación: tests verdes, con el borde inclusivo para `good` y para `unknown`.
- 40 min.
- Explicación: el LLM puede leer mal un total o inventar un ítem; el código recalcula y compara. El precio unitario máximo solo aplica a bienes, por eso cada ítem lleva `kind`. Si es un bien y se pasa, es causal de exclusión (`error`). Si no sabemos qué es y se pasa, no lo dejamos pasar en silencio: lo marcamos como duda (`warning`) y lo mira un contador.

### T8 — Validación de fechas y ventana móvil de 12 meses
- Commit: `feat(validation): validate dates and rolling 12-month window`
- Test primero: `tests/test_dates.py::test_one_year_before_handles_leap_day` (2028-02-29 → 2027-02-28); `tests/test_validation_dates.py::test_window_is_exclusive_start_inclusive_end` (con `today = 2026-09-24`: 2025-09-24 → `OUTSIDE_WINDOW`, 2025-09-25 → sin issue, 2026-09-24 → sin issue); `test_future_date_yields_warning_only` (2026-12-15 → solo `DATE_IN_FUTURE`).
- Implementación mínima: `dates.py` con `one_year_before`, `rolling_window(today)`, `is_in_window`; `validate_invoice_dates(invoice, today) -> list[Issue]`.
- Aceptación: tests verdes; `today` siempre es parámetro.
- 35 min.
- Explicación: el monotributo mira los últimos 12 meses móviles, no el año calendario. Definimos la ventana con precisión (inicio exclusivo, fin inclusivo) y la testeamos en los bordes. Recibir `today` por parámetro hace que los tests no caduquen.

### T9 — Padrón ARCA simulado
- Commit: `feat(arca): add mock taxpayer registry with synthetic CUITs`
- Test primero: `tests/arca/test_mock_registry.py::test_known_synthetic_cuit_returns_profile`, `test_unknown_cuit_returns_none`, `test_lookup_normalizes_hyphens`, `test_mock_registry_satisfies_protocol`.
- Implementación mínima: `arca/protocol.py` con `TaxpayerRegistry` (`@runtime_checkable`), `arca/mock.py` con `MockArcaRegistry(entries)` y `MockArcaRegistry.with_defaults()` (tres CUITs sintéticos: A, K, H).
- Aceptación: tests verdes; ningún CUIT real.
- 20 min.
- Explicación: no consultamos ARCA de verdad. Un padrón falso detrás de un Protocol permite testear el grafo entero y, si algún día se conecta el servicio real, cambia solo el adaptador.

### T10 — Ingreso acumulado y categoría calculada
- Commit: `feat(analysis): compute rolling 12-month income and category`
- Test primero: `tests/test_analysis.py::test_accumulated_income_ignores_invoices_outside_window`, `test_accumulated_income_ignores_future_invoices`, `test_computed_category_uses_scales` (9.600.000 → `A`).
- Implementación mínima: `accumulated_income(invoices, today) -> Decimal` usando `rolling_window`; categoría con `scales.category_for_income`.
- Aceptación: tests verdes.
- 30 min.
- Explicación: sumamos solo las facturas dentro de la ventana y traducimos ese total a una letra con la tabla vigente. Es aritmética pura, sin IA, y por eso se puede auditar línea por línea.

### T11 — Proyección y nivel de riesgo
- Commit: `feat(analysis): add income projection and exclusion risk levels`
- Test primero, `tests/test_analysis.py`:
  - `test_projection_annualizes_last_90_days` (3 × 800.000 → `Decimal("9733333.33")`).
  - `test_risk_low_when_far_from_caps`.
  - `test_risk_medium_boundary_at_90_percent_of_registered_cap` parametrizado: 10.808.469,41 → medium; 10.808.469,40 → low (contribuyente A).
  - `test_risk_medium_when_computed_category_differs`.
  - `test_risk_medium_when_projection_exceeds_registered_cap` (acumulado bajo, últimos 90 días altos).
  - `test_risk_high_when_projection_exceeds_k`.
  - `test_risk_high_boundary_at_90_percent_of_k` parametrizado: acumulado 113.949.754,88 con proyección baja → high; 113.949.754,87 → no high (contribuyente K: queda medium).
  - `test_risk_exclusion_when_income_exceeds_k`.
  - `test_risk_exclusion_when_unit_price_issue_present`.
  - `test_risk_takes_highest_level_when_several_apply`.
  - `test_risk_skips_registered_checks_when_taxpayer_unknown`.
- Implementación mínima: `RiskPolicy` (`near_cap_ratio=Decimal("0.9")`, `projection_days=90`, `review_levels=frozenset({"medium","high","exclusion"})`), `projected_income`, `assess_risk` que devuelve `(level, reasons)`, `analyze(invoices, issues, taxpayer, scales, today, policy) -> Analysis`.
- Aceptación: todos los tests verdes; cada condición de §4.9 tiene un test que la aísla y su borde; cada nivel tiene al menos una razón legible en `reasons`.
- 50 min.
- Explicación: la proyección responde "si seguís facturando como los últimos 90 días, ¿dónde terminás en un año?". El riesgo se escalona en cuatro niveles con reglas explícitas y umbrales configurables, para que el informe diga por qué y no solo qué. Cada regla tiene su propio test de borde: que los evals den 100 % no alcanza para demostrar que una regla existe.

### T12 — Informe con disclaimer, base del cálculo y origen de la decisión
- Commit: `feat(report): render markdown report with disclaimer and analysis limits`
- Test primero, `tests/test_report.py`: `test_report_contains_disclaimer_and_key_figures`, `test_report_lists_issues`, `test_report_states_scales_effective_date`, `test_report_distinguishes_registered_and_income_estimated_category`, `test_report_lists_not_evaluated_causes` (superficie, energía, alquileres, actividades, gastos no justificados; y la frase de que `low` no es una comprobación integral), `test_report_shows_accountant_decision_when_reviewer_is_accountant`, `test_report_labels_auto_resume_as_not_reviewed` (`reviewer="auto"` → el informe dice que ningún contador revisó el caso y no atribuye la decisión a una persona), `test_report_states_no_invoices_when_input_empty`, y por la decisión 6: `test_report_is_written_in_spanish` (secciones esperadas: "Ingresos", "Proyección", "Riesgo", "Revisión", "No evaluado"), `test_report_opens_with_argentina_scope_note`, `test_both_disclaimers_keep_the_three_clauses` (`DISCLAIMER_ES` y `DISCLAIMER_EN` contienen orientativo / no reemplaza a un contador / nunca presenta trámites).
- Implementación mínima: `report.py` con `SCOPE_NOTE_ES`, `DISCLAIMER_ES` (fuente de verdad), `DISCLAIMER_EN` (para el README), `NOT_EVALUATED` (lista fija en español) y `render_report(analysis, issues, taxpayer, scales, human_decision=None) -> str` en markdown **en español rioplatense, registro profesional**, con secciones: Nota de alcance, Aviso, Contribuyente (categoría registrada), Ingresos (últimos 12 meses móviles, categoría estimada "solo por ingresos"), Proyección, Riesgo y motivos, Observaciones, Revisión (decisión del contador / reanudación automática / ninguna), No evaluado, Escalas usadas.
- Aceptación: tests verdes; el informe nunca dice que presenta trámites ni recategoriza; siempre lista las causales no evaluadas; sale íntegramente en español.
- 40 min.
- Explicación: el informe es la salida del sistema y lleva siempre el aviso. Va en español rioplatense porque lo lee un monotributista argentino, aunque el código y el README estén en inglés: el idioma del producto y el idioma del repo son decisiones distintas. Además tiene que ser honesto sobre sus límites: la categoría que calculamos sale solo de los ingresos, y hay causales de exclusión que no miramos. Un "riesgo bajo" sin esa aclaración sería engañoso. También dice quién decidió: un contador de verdad o una reanudación automática de demo. Es una función pura de datos a texto, así que se testea sin grafo.

### T13 — Protocol de extractor y extractor falso
- Commit: `feat(extractors): define extractor protocol and fake extractor`
- Test primero: `tests/extractors/test_fake.py::test_fake_extractor_returns_mapped_invoice_for_text`, `test_fake_extractor_raises_for_unknown_text`, `test_fake_extractor_satisfies_protocol`.
- Implementación mínima: `extractors/protocol.py` con `InvoiceExtractor` (`@runtime_checkable`, `extract(raw: str) -> ExtractedInvoice`), `extractors/fake.py` con `FakeExtractor(mapping: dict[str, ExtractedInvoice])`.
- Aceptación: tests verdes.
- 20 min.
- Explicación: el extractor es la única pieza que "lee". Definimos su forma (un Protocol) y un doble de prueba que devuelve facturas conocidas. Así, todo lo que sigue se testea sin API key y sin red.

### T14 — Estado del grafo y nodos de extracción y validación
- Commit: `feat(graph): add copilot state and extraction/validation nodes`
- Test primero, `tests/graph/test_nodes.py`: `test_extract_node_returns_invoices_and_reports_failures` (2 textos, 1 desconocido → 1 factura + 1 `EXTRACTION_FAILED`), `test_extract_node_flags_empty_input` (`raw_invoices=[]` → `NO_INVOICES` warning, `invoices=[]`), `test_validate_node_collects_issues_from_all_validators` (CUIT inválido + fecha futura → ambos códigos), `test_validate_node_flags_issuer_mismatch` (CUIT válido distinto del contribuyente → `ISSUER_MISMATCH` warning).
- Implementación mínima: `graph/state.py` con `CopilotState`; `graph/nodes.py` con `make_extract_node(extractor)` y `make_validate_node(scales, today)`. `ISSUER_MISMATCH` solo si el CUIT es válido, para no duplicar con `INVALID_CUIT`.
- Aceptación: tests verdes invocando los nodos como funciones simples.
- 40 min.
- Explicación: un nodo es una función que recibe el estado y devuelve un dict con lo que cambió. Como las dependencias entran por closure, cada nodo se prueba a mano, sin compilar el grafo. Cero facturas no es "todo en orden": es falta de datos, y lo marcamos como duda para que derive.

### T15 — Nodos de padrón, análisis e informe
- Commit: `feat(graph): add taxpayer lookup, income analysis and report nodes`
- Test primero: `test_lookup_node_returns_profile_for_known_cuit`, `test_lookup_node_emits_not_found_warning`, `test_analyze_node_produces_analysis_from_state`, `test_report_node_writes_report_from_state` (estado con análisis, issues, contribuyente y sin decisión → `{"report": str}` que contiene el disclaimer), `test_report_node_passes_human_decision_when_present`.
- Implementación mínima: `make_lookup_node(registry)`, `make_analyze_node(scales, today, policy)`, `make_report_node(scales)` que toma `analysis`, `issues`, `taxpayer`, `human_decision` del estado, llama `render_report(...)` y devuelve `{"report": ...}`.
- Aceptación: tests verdes.
- 40 min.
- Explicación: son adaptadores finos: uno consulta el padrón (mock), otro llama a `analyze`, y el tercero convierte el estado en argumentos de `render_report`. Toda la lógica sigue en módulos puros ya testeados; los nodos solo traducen "estado del grafo" a "argumentos de función" y de vuelta.

### T16 — Ruteo condicional y cableado del grafo
- Commit: `feat(graph): wire pipeline with conditional routing to report or review`
- Test primero: `tests/graph/test_routing.py::test_route_after_analysis` parametrizado sobre `(policy, risk_level, issues, esperado)`: con la política por defecto, low sin issues → `ok`; medium → `review`; high → `review`; exclusion → `review`; low + warning → `review`; low + info → `ok`; con `review_levels={"high","exclusion"}`, medium → `ok`. `tests/graph/test_graph.py::test_happy_path_ends_with_report_without_interrupt` (invoke con `thread_id` → `report` presente y `pending_interrupt(...) is None`), `test_empty_input_routes_to_review`, `test_graph_declares_expected_nodes` (los seis nombres en `graph.get_graph().nodes`).
- Implementación mínima: `graph/routing.py` con `make_router(policy)`; `graph/builder.py` con `build_graph(...)` que compila con `make_checkpointer()` por defecto; `request_accountant_review` como stub que devuelve `{}` (estado transitorio declarado; se implementa en T17). Refactor: borrar `hello.py` y su test, conservando los tests de verificación de T2 movidos a `tests/graph/test_hitl.py`.
- Aceptación: tests verdes; `grep -r "interrupt_before\|update_state" src/` no devuelve nada.
- 40 min.
- Explicación: `add_conditional_edges` conecta un nodo con una función que devuelve una etiqueta y un mapa etiqueta → nodo siguiente. La función es pura, recibe la política por closure y se testea sola con las dos políticas posibles. El grafo se compila con checkpointer porque en la próxima tarea vamos a pausarlo.

### T17 — Human-in-the-loop con interrupt y Command
- Commit: `feat(graph): pause risky cases for accountant review with interrupt`
- Test primero, `tests/graph/test_review.py`: `test_risky_case_pauses_with_alert_payload` (caso exclusión → `pending_interrupt(...)` devuelve payload con `risk_level == "exclusion"`, `reasons` e `issues`; `result.get("report") is None`), `test_resume_with_accountant_decision_completes_report` (`Command(resume={"verdict": "confirmed", "notes": "Checked manually", "reviewer": "accountant"})` → informe contiene `Checked manually`), `test_resume_does_not_duplicate_issues` (tras reanudar, `issues` tiene la misma longitud que antes de la pausa).
- Implementación mínima: `request_accountant_review(state)` arma `alert = build_alert(state)` (pura), llama `decision = interrupt(alert)` y devuelve `{"human_decision": HumanDecision.model_validate(decision)}`. Sin efectos antes de `interrupt()`, por la re-ejecución verificada en T2.
- Aceptación: tests verdes; sin `interrupt_before` ni `update_state`.
- 45 min.
- Explicación: `interrupt()` pausa el grafo, guarda el estado en el checkpointer y expone un payload (la alerta). Cuando el contador decide, `Command(resume=...)` reanuda el mismo `thread_id` y ese valor es lo que `interrupt()` devuelve dentro del nodo. Como el nodo vuelve a correr desde el principio al reanudar (lo comprobamos en T2), no hacemos nada con efectos antes de la pausa.

### T18 — Diagrama Mermaid generado desde el grafo
- Commit: `docs: export graph diagram to mermaid`
- Test primero, `tests/test_export_graph.py`: `test_exported_mermaid_matches_live_graph` (el contenido de `docs/graph.mmd` es igual, tras `strip()`, a `build_graph(fakes...).get_graph().draw_mermaid()`), `test_mermaid_declares_both_routes_from_analyze` (regex laxa: `analyze_income` aparece en una línea con `write_report` y en otra con `request_accountant_review`).
- Implementación mínima: `scripts/export_graph.py` construye el grafo con fakes y escribe `docs/graph.mmd`; se commitea el archivo generado.
- Aceptación: tests verdes; si el grafo cambia sin regenerar el archivo, el test falla.
- 20 min.
- Explicación: el diagrama no se dibuja a mano: sale del grafo real con `get_graph().draw_mermaid()`. El test de igualdad hace que un diagrama viejo rompa la build, así el README nunca miente sobre las aristas.

### T19 — Extractores reales: modo `cli` (sin key) y modo `api`
- Commit: `feat(extractors): add provider-agnostic cli extractor and api extractor`
- **Esta tarea tiene dos mitades y se commitea en dos** (excepción declarada al "un commit por tarea", porque son dos unidades de trabajo independientes y cada una queda verde por su cuenta):
  - `feat(extractors): add provider-agnostic cli extractor` (50 min)
  - `feat(extractors): add api extractor with structured output` (40 min)
- Esquema compartido primero: `LLMInvoiceSchema` (Pydantic, strings para dinero y fecha, `kind` opcional con instrucción de usar `unknown` si no se puede determinar) y el prompt de sistema en inglés: extraer tal cual, no calcular ni corregir.

**T19a — `CliExtractor` (50 min)**
- Test primero, `tests/extractors/test_cli.py`: `test_cli_extractor_parses_json_from_plain_answer`, `test_cli_extractor_parses_json_wrapped_in_markdown_fence`, `test_cli_extractor_ignores_preamble_before_json`, `test_cli_extractor_retries_once_with_corrective_message`, `test_cli_extractor_raises_extraction_error_after_second_failure`, `test_cli_extractor_maps_missing_kind_to_unknown`, `test_cli_extractor_prompt_includes_raw_invoice_text`, `test_resolver_prefers_env_cmd_over_autodetection`, `test_resolver_raises_when_no_cli_available` (y **no** cae a `fake`). El runner del subprocess se inyecta como callable (`run: Callable[[list[str], str], str]`), así los tests no lanzan procesos.
- Implementación mínima: `extractors/cli.py` con `CliExtractor(run, argv)`, `extract_first_json_object(text)`, reintento único con mensaje correctivo, `ExtractionError`; `extractors/resolve.py` con `KNOWN_CLI_ADAPTERS` y el orden de resolución de §4.5.1.
- **Verificación en vivo (como T2 y T3):** `shutil.which()` sobre `codex`, `agy`, `claude`; para cada binario presente se corre su `--help` y se registra la invocación no interactiva real en el adaptador y en el README. Los ausentes quedan documentados como pendientes, sin inventar flags.
- Aceptación: tests verdes sin red ni binarios; al menos un adaptador verificado contra un CLI realmente instalado.

**T19b — `ApiExtractor` (40 min)**
- Test primero, `tests/extractors/test_api.py`: `test_api_extractor_converts_structured_answer_to_invoice` (runnable stub devuelve `LLMInvoiceSchema` con montos como texto → `ExtractedInvoice` con `Decimal` y `date`), `test_api_extractor_maps_missing_kind_to_unknown`, `test_build_chat_model_selects_provider_from_env`, `test_api_extractor_reads_synthetic_invoice_end_to_end` marcado `skipif` sin key.
- Implementación mínima: `extractors/api.py` con `ApiExtractor(structured_model)` y `ApiExtractor.from_env()`; extra opcional `api` en `pyproject.toml` con `langchain-anthropic` y `langchain-openai`; `COPILOTO_API_PROVIDER` elige el chat model y `COPILOTO_MODEL` el identificador. El identificador por defecto se confirma con el test de integración si hay key; si no, queda declarado como no verificado en el README.
- Aceptación: tests unitarios verdes sin key; el de integración se salta limpiamente; `uv sync` sin el extra no rompe nada.

- **90 min en total.**
- Explicación: acá se ve para qué sirvió el `Protocol`. El modo `api` usa `with_structured_output`, que obliga al modelo a responder con el esquema Pydantic que le damos: la IA devuelve datos, no prosa. El modo `cli` no tiene esa garantía, porque le hablamos por consola a la herramienta que tengas instalada y lo que vuelve es texto suelto — así que pedimos JSON, lo buscamos dentro de la respuesta, lo validamos y reintentamos una vez. La paradoja que vale contar en una entrevista: **el modo pago es el más fácil de programar y el gratis es el que da trabajo.** Y si no hay ningún CLI, fallamos con un error claro en vez de caer al extractor falso, porque un fallback mudo haría creer que un modelo leyó las facturas cuando no las leyó nadie.

### T20 — Dataset sintético de evals
- Commit: `test(evals): add synthetic eval cases with known answers`
- Test primero, `tests/evals/test_cases.py`: `test_all_case_files_validate_against_schema`, `test_case_ids_cover_required_scenarios` (los 14 IDs de §4.10), `test_invoice_texts_match_invoices_one_to_one`, `test_only_invalid_cuit_case_contains_invalid_cuits`, `test_empty_input_case_has_no_invoices`.
- Implementación mínima: `synthetic.py` con `render_invoice(inv) -> str` (plantilla tipo "FACTURA C") y `monthly_invoices(...)`; `evals/schema.py` con `EvalCase` y `Expected`; `scripts/build_eval_cases.py` genera los 14 JSON de forma determinística, calculando `expected` con la misma `RiskPolicy` por defecto; se commitean los JSON.
- Aceptación: tests verdes; `uv run python scripts/build_eval_cases.py` reproduce los mismos archivos.
- 60 min.
- Explicación: un eval es un caso con entrada y respuesta correcta conocida. Los generamos por script para que sean reproducibles y cubran los bordes que importan: tope exacto, cambio de categoría, CUIT inválido, fecha fuera de ventana, precio unitario excedido con tipo conocido y desconocido, exclusión, y entrada vacía.

### T21 — Runner de evals con métrica de decisión y de extracción
- Commit: `feat(evals): add eval runner with decision and extraction accuracy`
- Test primero, `tests/evals/test_runner.py`: `test_runner_scores_all_cases_correct_with_fake_extractor` (decision accuracy `== 1.0`, extraction accuracy `== 1.0`), `test_runner_marks_case_incorrect_when_expectation_differs`, `test_runner_auto_resumes_interrupts_with_auto_reviewer`, `test_runner_reports_field_mismatch_even_when_decision_matches` (extractor que devuelve `issue_date` corrida un día → decisión correcta, `issue_date` accuracy < 1).
- Implementación mínima: `evals/runner.py` con `run_case(case, extractor_factory) -> CaseResult` (fake desde el ground truth, registry desde `registry_entry`, invoke, `pending_interrupt`, resume enlatado con `reviewer="auto"`, comparación por campo de `issuer_cuit`, `issue_date`, `total`), `run_all(cases_dir, ...) -> EvalReport`; `evals/__main__.py` para `uv run python -m copiloto.evals --extractor fake|cli|api --threshold 1.0`.
- Aceptación: el comando imprime tabla por caso, decision accuracy y extraction accuracy por campo; sale con código 1 si la decisión no llega al umbral.
- 50 min.
- Explicación: el runner ejecuta el grafo real por cada caso y compara con lo esperado en dos planos: qué decidió (ruta, riesgo, categoría, issues) y qué leyó (CUIT, fecha, total por factura). Así separamos "leyó mal" de "decidió mal", y una fecha corrida cuenta como error aunque no cambie la decisión fiscal.

### T22 — CLI con revisión interactiva del contador
- Commit: `feat(cli): add run command with interactive accountant review`
- Test primero, `tests/test_cli.py`: `test_run_case_prints_report_when_all_in_order` (capsys), `test_run_risky_case_prompts_accountant_and_prints_final_report` (monkeypatch de `input` → veredicto y notas; la salida contiene la alerta, las notas y "contador"), `test_run_auto_resume_labels_report_as_not_reviewed` (`--auto-resume` → sin `input`, el informe dice que ningún contador revisó el caso), `test_cli_prompts_are_in_spanish`, `test_extractor_flag_selects_each_of_the_three_modes` (parametrizado sobre `fake`, `cli`, `api`, con las fábricas mockeadas), `test_cli_mode_without_available_tool_fails_with_actionable_message` (nombra las tres opciones y `COPILOTO_EXTRACTOR_CMD`).
- Implementación mínima: `cli.py` con argparse: `copiloto run --case FILE [--extractor fake|cli|api] [--today YYYY-MM-DD] [--auto-resume]`; default tomado de `COPILOTO_EXTRACTOR`, y `fake` si no está seteada; `[project.scripts] copiloto = "copiloto.cli:main"`. Con `--extractor cli|api` usa los `invoice_texts` del caso. **Todos los mensajes, prompts y errores en español rioplatense profesional** (decisión 6). Al detectar pausa: imprime la alerta, pide veredicto y notas, reanuda con `reviewer="accountant"`; con `--auto-resume`, reanuda con `verdict="confirmed"`, `notes="Reanudación automática (demo); ningún contador revisó este caso."`, `reviewer="auto"`.
- Aceptación: `uv run copiloto run --case evals/cases/all_in_order.json` imprime el informe en español; con `exclusion_by_income.json` pausa, pregunta y termina; con `--auto-resume` termina sin preguntar y el informe lo dice; los tres modos de extractor se seleccionan y el modo `cli` sin herramienta falla con un mensaje que dice qué hacer.
- 40 min.
- Explicación: la CLI es la demo: corre el grafo, y si el grafo se pausa, hace de "contador" pidiendo la decisión por teclado y reanudando. Habla en español porque es lo que ve el usuario final. El flag `--extractor` es el único lugar donde se elige el modelo, y eso es posible justamente porque abajo hay un `Protocol`: el grafo no cambia una línea. La reanudación automática existe solo para demos y scripts, y el informe lo deja escrito para que nadie crea que un contador miró el caso.

### T23 — README en inglés con diagrama y disclaimer
- Commit: `docs: write README with graph diagram and disclaimer`
- Test primero, `tests/test_readme.py`: `test_readme_has_exact_disclaimer` (contra `report.DISCLAIMER_EN`), `test_readme_mermaid_block_equals_exported_graph` (el bloque ` ```mermaid ` del README es idéntico, tras `strip()`, al contenido de `docs/graph.mmd`), `test_readme_states_scales_effective_date` (lee `effective_from` de la config), `test_readme_documents_three_extractor_modes` (menciona `fake`, `cli` y `api` y la variable `COPILOTO_EXTRACTOR`), `test_readme_quickstart_mentions_api_extra` (contiene `uv sync --extra api`), `test_readme_explains_report_language` (explica que la salida al usuario va en español).
- Implementación mínima: README con la estructura de §4.11, incrustando `docs/graph.mmd`, la sección "Verified against" con lo observado en T2, T3 y T19a (adaptadores de CLI verificados vs. pendientes), y `LICENSE` MIT en la raíz.
- Aceptación: tests verdes; el README explica cómo correr demo, tests y evals **sin instalar ni pagar nada**, cómo usar el CLI propio, y cómo activar el extra `api`.
- 40 min.
- Explicación: el README es lo primero que ve un reclutador. Los tests evitan que el disclaimer desaparezca, que el diagrama publicado difiera del grafo real, o que el quickstart deje afuera un paso. Que el repo arranque sin API key no es un detalle: es lo que hace que alguien lo pruebe en vez de cerrarlo.

### T24 — Publicar el repo como público (requiere OK explícito)
- Commit: ninguno; es `git push`.
- Pre-flight: `uv run pytest` verde; `uv run python -m copiloto.evals --extractor fake` en 100 %; `git log --format=%B | grep -i "co-authored-by"` vacío; `.env` no trackeado; `LICENSE` MIT presente; ningún dato real ni key en el historial.
- Acción: `gh repo create <owner>/copiloto-monotributo --public --source=. --remote=origin --push` (o creación manual y `git remote add`), en la cuenta de GitHub del humano (decisión 2).
- Aceptación: el repo público muestra README con diagrama y disclaimer; un clon limpio corre `uv sync && uv run pytest` en verde sin API key.
- 10 min.
- Explicación: publicar es irreversible en la práctica (se indexa), por eso va último y con checklist. Solo se hace con la confirmación explícita del humano. MIT es la licencia más corta y la que menos fricción genera si esto después se vuelve producto.

Recorte de emergencia si el domingo se acorta, en este orden:

1. El test de integración de T19b (el que necesita key real).
2. **T19b completo** — el modo `api` queda en v2. El repo sigue siendo demostrable con `cli` y `fake`.
3. El prompt interactivo de T22 (dejar solo `--auto-resume`).
4. **T19a completo** — solo `fake`. Último recurso: el repo sigue probando toda la lógica fiscal, pero deja de demostrar la parte de IA.

Nunca se recortan T2, T3, los evals ni el README. La CI ya salió del alcance (§3).

## 6. Risks & edge cases (Riesgos y mitigaciones)

- **API de LangGraph no certificada de forma independiente.** El digest la consultó en vivo; la crítica y esta síntesis no pudieron. Mitigación: T2 verifica contra el paquete instalado el nombre del checkpointer, la detección de interrupción y la re-ejecución del nodo, y `graph/hitl.py` encapsula las dos primeras para que un cambio no toque el resto. Resultado registrado en tests y README.
- **Tabla ARCA no certificada de forma independiente.** Mismo caso. Mitigación: T3 abre la página oficial antes de commitear el JSON, corrige si difiere y guarda `retrieved_on` real. Los valores caducan el próximo semestre; actualizar es editar el JSON.
- **Riesgo de dominio: aplicabilidad de las categorías H–K a servicios.** Supuesto del MVP: las 11 categorías aplican a cualquier actividad, porque la tabla digerida es única. Ni el digest ni la crítica pudieron confirmar o refutar que las categorías altas sigan restringidas a venta de cosas muebles. Mitigación: el supuesto queda escrito en `notes` del JSON, en la sección "Not evaluated" del informe y en el README; T3 verifica en la página si hay una tabla por actividad; si la hay, se frena y se escala (pregunta 5) antes de T4, porque `category_for_income` necesitaría un parámetro de actividad.
- **Python 3.14 por defecto.** Mitigación: `.python-version` y `requires-python` fijan 3.12 (T1); el test de humo lo verifica.
- **Sin API key.** El camino LLM queda sin prueba real. Mitigación: unit test con runnable stub, integración `skipif`, evals con fake bloqueantes y con LLM informativos.
- **`with_structured_output` con `Decimal` y `date`.** Mitigación: `LLMInvoiceSchema` con strings, conversión en código (T19).
- **Semántica de `interrupt()`.** Requiere checkpointer y `thread_id`; el nodo se re-ejecuta al reanudar (a confirmar en T2). Mitigación: `build_graph` compila siempre con checkpointer; el nodo de revisión es puro antes de `interrupt()`; T17 testea que no se duplican issues.
- **Ítem sin tipo.** Si el LLM no dice si un ítem es bien o servicio, el default es `unknown`; un precio unitario por encima del máximo con tipo desconocido deriva a revisión (T7). Sigue existiendo el riesgo de que el LLM clasifique mal un bien como servicio; se acepta como límite del MVP y se documenta.
- **Entrada vacía.** `NO_INVOICES` deriva a revisión; nunca se emite "todo en orden" sin facturas (T14, eval `empty_input`).
- **Precisión monetaria y bordes inclusivos.** `Decimal` en todo el dominio, montos como strings en JSON, tests de borde en T4, T7, T11 y T20.
- **Ventana móvil y 29 de febrero.** Ventana `(hoy − 1 año, hoy]` con ajuste de bisiesto (T8). Queda pregunta 4 si se prefieren meses calendario.
- **Informe que aparenta más de lo que evalúa.** Mitigación: sección fija "Not evaluated" y etiqueta "estimated from income only" (T12).
- **Decisión automática confundida con decisión humana.** Mitigación: `reviewer` en `HumanDecision`, etiqueta explícita en el informe (T12, T22).
- **Diagrama desactualizado.** Mitigación: igualdad grafo ↔ `docs/graph.mmd` ↔ README (T18, T23). El formato de `draw_mermaid()` para aristas condicionales no está verificado; el test de aristas es laxo y el de igualdad es estricto.
- **Concentración de trabajo en T20 y T21.** Son las tareas más largas del domingo. Mitigación: el generador de casos calcula `expected` con la misma política que el código, así un cambio de política no exige editar 14 JSON a mano.
- **Sin margen para preguntas abiertas.** El plan pide las respuestas antes de empezar (§9). Si no llegan, se aplican los defaults declarados.
- **Higiene del repo público.** `.env` ignorado, sin trailers de IA, checklist de T24 antes del push.

## 7. Acceptance criteria (Criterios de aceptación y Definition of Done)

Un revisor confirma el plan si:

1. `uv run python -c "import sys; print(sys.version)"` imprime 3.12.x y `uv run pytest` está verde.
2. `tests/graph/test_hitl.py` pasa contra el `langgraph` instalado y documenta: nombre del checkpointer usado, mecanismo de detección de interrupción y cantidad de ejecuciones del nodo al reanudar. El README repite esos tres datos con la versión y la fecha.
3. `config/monotributo_scales.json` contiene la tabla A–K con `effective_from`, `source`, `retrieved_on` (fecha real de la consulta en T3) y `notes`; el informe y el README muestran la fecha de vigencia.
4. `git log --oneline` muestra un commit por tarea T1–T23 (T19 aporta dos, por su división declarada) con formato conventional commits y sin atribución de IA.
5. `uv run python -m copiloto.evals --extractor fake` imprime 100 % de decisión y 100 % de extracción sobre 14 casos que incluyen tope exacto, cambio de categoría, CUIT inválido, fecha fuera de ventana, precio unitario excedido (tipo conocido y desconocido), exclusión, contribuyente desconocido y entrada vacía.
6. Cada condición de §4.9 tiene al menos un test unitario que la aísla, incluido su borde.
7. `uv run copiloto run --case evals/cases/all_in_order.json` imprime un informe **en español rioplatense** con la nota de alcance argentino, el aviso, la categoría "estimada solo por ingresos" y la sección "No evaluado"; `... exclusion_by_income.json` pausa, muestra la alerta, acepta veredicto y notas, y termina con el informe; `... --auto-resume` termina sin preguntar y el informe dice que ningún contador lo revisó.
8. `grep -rn "interrupt_before\|interrupt_after\|update_state\|ToolExecutor" src/ tests/` no devuelve resultados.
9. `README.md` está en inglés, incluye el bloque Mermaid idéntico a `docs/graph.mmd` (que a su vez es idéntico a `draw_mermaid()` del grafo real), el disclaimer exacto de §4.11, la tabla de los tres modos de extractor y el paso `uv sync --extra api`.
10. Ningún archivo del repo contiene facturas, nombres o CUITs reales; `.env` no está trackeado; **el repo no versiona ninguna plantilla `.env*`** (las variables se documentan en `docs/configuration.md`, así nadie llena un template con una key real y lo commitea); no hay ninguna API key en el historial.
11. **Los tres modos de extractor funcionan y están testeados:** `fake` sin red; `cli` con tests que inyectan el runner del subprocess, más al menos un adaptador verificado contra un binario realmente instalado; `api` con tests unitarios sin key y un test de integración que se salta limpiamente. El modo `cli` sin herramienta disponible falla con un mensaje accionable y **nunca cae en silencio a `fake`**.
12. Un clon limpio corre `uv sync && uv run pytest && uv run python -m copiloto.evals --extractor fake` en verde **sin API key, sin CLI de IA y sin red**.
13. `LICENSE` contiene MIT a nombre del humano y el README lo declara.
14. El repo es público solo después de la confirmación explícita del humano (T24).

## 8. Critique disposition (Disposición de la crítica)

Los 10 hallazgos se aceptan. Ninguno se rechaza: todos aportaron evidencia concreta contra el borrador y se resuelven con cambios acotados (+110 min brutos, compensados parcialmente moviendo `--invoices-dir` a v2).

| ID | Severidad | Disposición | Qué cambia en el plan |
|---|---|---|---|
| C1 | BLOCKING | **ACCEPT** (resuelto con default + escalado) | El default pasa a la lectura literal del pedido: `medium` deriva a contador. `RiskPolicy.review_levels` hace la política configurable en una línea; tests de ruteo parametrizados sobre ambas políticas (T16); el generador de evals calcula `expected` desde la política (T20), así cambiar la respuesta regenera tres casos. Escalado como pregunta 1 porque es decisión de producto. |
| C2 | ADVISORY | **ACCEPT** | T15 pasa a "Nodos de padrón, análisis e informe" e incluye `make_report_node(scales)` con dos tests (+10 min). |
| C3 | ADVISORY | **ACCEPT** | `kind` default `unknown` (T5). Precio unitario > máximo con `unknown` emite `UNIT_PRICE_KIND_UNKNOWN` (warning → review) (T7). El esquema LLM instruye `unknown` si no se puede determinar (T19). Nuevo eval `unit_price_kind_unknown` (T20). |
| C4 | ADVISORY | **ACCEPT** | T12 agrega tests y secciones: categoría registrada vs. "estimated from income only", lista fija "Not evaluated", frase de que `low` no es comprobación integral. README con sección "What it does NOT evaluate". Criterio 7. |
| C5 | ADVISORY | **ACCEPT** | T21 agrega comparación por campo (`issuer_cuit`, `issue_date`, `total`) contra el ground truth y el test con fecha corrida un día que sigue acertando la decisión pero baja la exactitud de extracción. Criterio 5. |
| C6 | ADVISORY | **ACCEPT** | Regla: `raw_invoices=[]` → `NO_INVOICES` (warning) → review (§4.9). Test en T14, test de grafo en T16, eval `empty_input` (T20), informe lo dice (T12). |
| C7 | ADVISORY | **ACCEPT** | T11 agrega tests discriminantes con borde para cada condición de §4.9, incluido `acumulado ≥ 90 % de K` (113.949.754,88 / ,87), proyección > tope registrado, y "gana el nivel más alto". Criterio 6. |
| C8 | ADVISORY | **ACCEPT** | T18 testea igualdad entre `docs/graph.mmd` y `draw_mermaid()` del grafo real; T23 testea igualdad entre el bloque Mermaid del README y `docs/graph.mmd`. Criterio 9. |
| C9 | ADVISORY | **ACCEPT** | Quickstart incluye `uv sync --extra api` antes de `--extractor api` (§4.11); test `test_readme_quickstart_mentions_api_extra` en T23. Con la decisión 3 el hallazgo pierde filo: el modo `cli` no necesita instalar nada, así que el camino por defecto del README ya no depende de un extra. |
| C10 | ADVISORY | **ACCEPT** | `HumanDecision.reviewer: "accountant" \| "auto"` (T5). Flag renombrado a `--auto-resume` con semántica definida: mantiene la alerta, no la aprueba, y el informe dice que ningún contador revisó el caso (T12, T22). El runner de evals usa `reviewer="auto"` (T21). |

Notas sobre las comprobaciones sin hallazgo de la crítica, también incorporadas: T1 distingue el rojo real (`ModuleNotFoundError`) de la preparación del runner; los casos de "dato dudoso" de §4.10 ahora declaran sus montos (base `all_in_order` + una modificación) para que `risk_level=low` sea verificable; el identificador `claude-sonnet-5` queda como default configurable por `COPILOTO_MODEL` y se confirma con el test de integración si hay key; las tareas más cargadas (T19, T20, T22) se reequilibraron: T22 perdió `--invoices-dir`, T20 subió a 60 min con generación automática de `expected`.

## 9. Decisiones tomadas y lo que sigue abierto

Las seis preguntas de la síntesis fueron respondidas por el humano el 2026-09-24 y ya están incorporadas al cuerpo del plan (§0 tiene el resumen). Se conserva acá el registro de qué se preguntó, qué se decidió y qué cambió.

| # | Pregunta | Decisión | Impacto en el plan |
|---|---|---|---|
| 1 | ¿`medium` deriva a contador o termina en informe con aviso? (BLOCKING C1) | **Deriva.** Lectura literal del pedido. | `RiskPolicy.review_levels = {medium, high, exclusion}` (§4.9). Tests de ruteo parametrizados sobre la política; los evals calculan `expected` desde ella, así cambiar de opinión sigue costando una línea. |
| 2 | Cuenta, nombre y licencia del repo | **Cuenta del humano, `copiloto-monotributo`, MIT, publicación al final.** | T24 con checklist de pre-flight; `LICENSE` MIT; criterio 13. |
| 3 | ¿Qué proveedor de IA? | **Ninguno fijo: tres modos.** `fake` para tests, `cli` para el modelo que cada uno ya tenga, `api` para quien venda el servicio. | §4.5.1 nueva; T19 se divide en T19a/T19b y pasa de 45 a 90 min; T22 con `--extractor fake\|cli\|api`; README con tabla de modos; criterios 11 y 12. |
| 4 | ¿Ventana móvil o 12 meses calendario? | **Móvil:** `(hoy − 1 año, hoy]`. | Sin cambios: ya era el default (§4.9, T8, T10). |
| 5 | ¿Las 11 categorías aplican igual a servicios y a cosas muebles? | **Mantener el supuesto de tabla única, documentado, y verificarlo en T3.** | Sin cambios de diseño. Queda como riesgo de dominio vivo (abajo). |
| 6 | ¿Idioma del informe y la CLI? | **Español rioplatense**, con nota de alcance argentino al inicio del informe. README y código siguen en inglés. | §4.13 nueva; T12 con tests de idioma y `DISCLAIMER_ES` / `DISCLAIMER_EN`; T22 con mensajes en español; criterio 7. |

### Lo que sigue abierto (no bloquea el arranque)

Ninguno de estos puntos impide empezar por T1. Los tres se resuelven **con evidencia durante la ejecución**, no con una decisión previa. Están acá para que nadie los dé por cerrados.

1. **Tipo de actividad y categorías altas (riesgo de dominio, decisión 5).** El MVP asume que A–K aplica igual a servicios y a venta de cosas muebles. Si históricamente el techo dependía de la actividad y eso sigue vigente, un informe podría decir "todo en orden" a alguien ya excluido — el peor error posible en este producto. **T3 lo verifica en vivo contra arca.gob.ar antes de que el cálculo de categoría dependa de nada.** Si la fuente muestra tablas separadas, se frena y se agrega `activity` al contribuyente (≈40 min, sale del recorte de emergencia). El supuesto queda escrito en el informe y en el README hasta que T3 lo confirme.

2. **Nombres exactos de la API de LangGraph.** `InMemorySaver` vs `MemorySaver`, la clave `__interrupt__` en el resultado de `invoke`, la semántica de re-ejecución del nodo al reanudar y el formato de `draw_mermaid()` para aristas condicionales. **T2 los resuelve contra el paquete instalado** y el resultado queda en un test y en la sección "Verified against" del README.

3. **Invocación no interactiva de cada CLI de IA.** Los flags de `codex`, `agy` y `claude` no se escriben de memoria: **T19a los prueba contra los binarios realmente instalados.** Los que no estén en la máquina quedan documentados como adaptadores pendientes, y `COPILOTO_EXTRACTOR_CMD` cubre cualquier herramienta no contemplada.

### Próximo paso

T1 — Bootstrap del proyecto con uv y Python 3.12. Rojo primero.
