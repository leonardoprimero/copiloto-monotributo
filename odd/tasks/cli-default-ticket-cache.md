# Feature: Default Persistent Ticket Cache for ARCA in CLI and Web

## Objective
Provide a sensible, persistent default path for the WSAA ticket cache (`~/.cache/copiloto/tickets.json` or `$XDG_CACHE_HOME/copiloto/tickets.json`) in `copiloto run --arca` and the web server, avoiding 12-hour `coe.alreadyAuthenticated` lockouts across CLI invocations without requiring manual `--arca-ticket-cache` specification.

## Problem & Context
When running `copiloto run --arca` without `--arca-ticket-cache`, `build_registry` currently defaults to an in-memory cache that dies with the process. If a user runs the CLI twice in a row, the second invocation requests a fresh ticket from WSAA while the previous one is still valid, triggering `coe.alreadyAuthenticated` from ARCA.
A persistent default path solves this seamlessly, while `--no-arca-ticket-cache` provides an explicit opt-out.

## Scope & Constraints
- Keep `build_registry` safe: the library function continues to take `ticket_cache: Path | None = None` so low-level unit tests never write to the filesystem unexpectedly.
- Provide `default_ticket_cache_path() -> Path` in `copiloto.arca.client`.
- In `cli.py` and `web/app.py`, resolve cache path: if explicitly given use it; if disabled (`--no-arca-ticket-cache` or `COPILOTO_ARCA_TICKET_CACHE="none"` / `"0"`) use `None`; otherwise use `default_ticket_cache_path()`.
- TDD: strict RED -> GREEN -> REFACTOR on every task.
- Verification commands: `uv run python -m pytest`, `uv run --with pyright pyright`.

## Tasks

- [x] `T1`: Define and test `default_ticket_cache_path()` in `src/copiloto/arca/client.py`
  - Route: Direct inline (`src/copiloto/arca/client.py` and `tests/arca/test_client.py`).
  - RED: Tests in `tests/arca/test_client.py` verifying fallback to `~/.cache/copiloto/tickets.json` and honoring `XDG_CACHE_HOME`.
  - GREEN: Implement `default_ticket_cache_path()`.
  - Evidence: Commit `58dadcb`, 2 tests pass, pyright 0 errors.

- [ ] `T2`: Wire default cache into CLI and Web with opt-out
  - Route: Delegated direct (`src/copiloto/cli.py`, `src/copiloto/web/app.py`, `tests/test_cli_own_invoices.py`, `tests/web/test_app.py`).
  - RED: Tests asserting default cache path passed to `build_registry` and `--no-arca-ticket-cache` passing `None`.
  - GREEN: Update CLI argument parsing and WebSettings initialization.
  - Checks: pytest + pyright. Commit unit.

- [ ] `T3`: Documentation & Changelog
  - Route: Direct inline (`docs/configuration.md`, `docs/arca-padron.md`, `CHANGELOG.md`).
  - Document the default ticket cache path and `--no-arca-ticket-cache` flag.
  - Checks: full pytest suite + pyright. Commit unit.
