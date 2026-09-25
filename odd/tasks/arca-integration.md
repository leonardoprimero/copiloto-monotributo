# Feature: Wire ArcaRegistry to Graph, CLI, and Web

## Objective
Wire the real `ArcaRegistry` into the copilot execution pipeline (CLI and Web) and update the `lookup_taxpayer` graph node to gracefully catch `ConstanciaUnavailable` and `PadronError`, routing to accountant review instead of crashing.

## Problem & Context
The project already implements a complete, live-verified ARCA client (`copiloto.arca`) with WSAA ticket caching and padrón lookup. However:
1. `make_lookup_node` in `copiloto.graph.nodes` assumes `registry.lookup(cuit)` only returns `TaxpayerProfile` or `None`. When ARCA refuses to issue a constancia (`ConstanciaUnavailable`) or the service fails (`PadronError`), the unhandled exception crashes the graph execution.
2. `copiloto.cli` only instantiates `MockArcaRegistry` and requires `--category` when processing real invoices (`--invoices-dir`), even though ARCA padrón can provide the registered category.
3. `copiloto.web.app` only uses `MockArcaRegistry` and does not provide an option to use real ARCA lookups.

## Scope & Constraints
- Keep `arca` optional: importing or running the core copilot without `arca` dependencies must not fail.
- When `ConstanciaUnavailable` is caught, record an `Issue(code="CONSTANCIA_UNAVAILABLE", severity="warning", ...)` and leave `taxpayer=None`. The warning severity automatically routes the case to accountant review.
- When other `PadronError` occurs, record an `Issue(code="PADRON_ERROR", severity="warning", ...)` and leave `taxpayer=None`.
- For CLI and Web, allow selecting ARCA via `--arca` / env vars (`COPILOTO_ARCA_*`). Make `--category` optional when ARCA is active.
- TDD: strict RED -> GREEN -> REFACTOR on every task.
- Verification commands: `uv run python -m pytest`, `uv run --with pyright pyright`.

## Tasks

- [ ] `T1`: Handle `ConstanciaUnavailable` and `PadronError` in `make_lookup_node` (`src/copiloto/graph/nodes.py`)
  - Route: Direct inline (single non-trivial file + focused test).
  - RED: Test in `tests/graph/test_nodes.py` asserting that when `registry.lookup` raises `ConstanciaUnavailable` or `PadronError`, `lookup_taxpayer` emits a warning issue and leaves taxpayer as None.
  - GREEN: Catch exceptions gracefully in `make_lookup_node`, preserving optionality of `arca`.
  - REFACTOR / Checks: `uv run python -m pytest tests/graph/test_nodes.py`. Commit unit.

- [ ] `T2`: Wire `ArcaRegistry` into `copiloto.cli`
  - Route: Delegated direct (touches `src/copiloto/cli.py` and `tests/test_cli.py`).
  - RED: Tests in `tests/test_cli.py` for `--arca` flag, optional `--category`, env vars, missing extra error message, and execution with mocked ArcaRegistry.
  - GREEN: Implement ARCA resolution and factory wiring in `cli.py`.
  - REFACTOR / Checks: `uv run python -m pytest tests/test_cli.py`. Commit unit.

- [ ] `T3`: Wire `ArcaRegistry` into `copiloto.web.app`
  - Route: Delegated direct (touches `src/copiloto/web/app.py` and `tests/web/test_app.py`).
  - RED: Tests in `tests/web/test_app.py` for optional category and ARCA registry integration.
  - GREEN: Update `WebSettings` and `/casos` endpoint in `web/app.py` to support ARCA lookups.
  - REFACTOR / Checks: `uv run python -m pytest tests/web/test_app.py`. Commit unit.

- [ ] `T4`: Update documentation
  - Route: Direct inline (`docs/configuration.md` and `docs/arca-padron.md`).
  - Document `--arca` flag, `COPILOTO_ARCA_*` environment variables, and the accountant routing behavior on `ConstanciaUnavailable`.
  - Checks: full test suite + pyright. Commit unit.
