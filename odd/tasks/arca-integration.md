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

- [x] `T1`: Handle `ConstanciaUnavailable` and `PadronError` in `make_lookup_node` (`src/copiloto/graph/nodes.py`)
  - Route: Direct inline (single non-trivial file + focused test).
  - RED: Test in `tests/graph/test_nodes_lookup_analyze_report.py` and `tests/graph/test_builder.py` asserting warning issue and accountant review interruption.
  - GREEN: Extracted zero-dependency exceptions to `copiloto.arca.exceptions` and caught in `make_lookup_node`.
  - Evidence: Commit `0aa24fc`, 20 tests pass, pyright 0 errors.

- [x] `T2`: Wire `ArcaRegistry` into `copiloto.cli`
  - Route: Delegated direct (touches `src/copiloto/cli.py` and `tests/test_cli_own_invoices.py`).
  - RED: Tests in `tests/test_cli_own_invoices.py` for `--arca` flag, credentials validation, optional category, and build_registry invocation.
  - GREEN: Added `--arca*` flags, validation, and ARCA registry factory in `src/copiloto/cli.py`.
  - Evidence: Commit `1f1014c`, 19 tests pass, pyright 0 errors.
  - Review: Lineage `review-586b4ff2b6df7b24` (tier medium, lens `review-reliability`) APPROVED and acknowledged. Reviewed boundary advanced to `1f1014c`. 1 advisory SUGGESTION (persistent default for ticket cache in CLI).

- [x] `T3`: Wire `ArcaRegistry` into `copiloto.web.app`
  - Route: Delegated direct (touches `src/copiloto/web/app.py`, `src/copiloto/web/templates/home.html` and `tests/web/test_app.py`).
  - RED: Tests in `tests/web/test_app.py` for optional category with ARCA and ConstanciaUnavailable accountant routing.
  - GREEN: Added `arca_registry` to `WebSettings`, updated `/casos` to use ARCA when configured, and made category select optional in `home.html`.
  - Evidence: Commit `af9deda`, 26 tests pass, pyright 0 errors.

- [x] `T4`: Update documentation
  - Route: Direct inline (`docs/configuration.md` and `docs/arca-padron.md`).
  - Documented `--arca` flag, `COPILOTO_ARCA_*` environment variables, and the accountant routing behavior on `ConstanciaUnavailable`. Updated CHANGELOG.md.
  - Evidence: Commit `0cfc6af`, full suite 851 tests pass, pyright 0 errors.
