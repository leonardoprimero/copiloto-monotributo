# Configuration

Every setting is an environment variable. The defaults are chosen so that a fresh
clone runs its tests and evals offline, with no API key and no AI CLI installed.

## Choosing an extractor

The extractor is the only component that reads invoices with a model. Everything
else — validation, category, projection, risk, routing — is deterministic code.

| `COPILOTO_EXTRACTOR` | Who it is for | Requirements |
| --- | --- | --- |
| `fake` (default) | Tests and evals | None. Runs offline. |
| `cli` | Anyone with an AI CLI already installed | The CLI binary itself. No API key. |
| `api` | Service deployments | `uv sync --extra api` and a provider key |

If no extractor is configured, `fake` is used. It never reads a real invoice: it
maps known synthetic texts to known results, which is what makes the test suite
deterministic.

## `cli` mode

Resolution order:

1. `COPILOTO_EXTRACTOR_CMD` — a full command line. The prompt is written to the
   process stdin, the answer is read from stdout. Use this for any tool that is
   not one of the known adapters.
2. `COPILOTO_CLI` — pick a known adapter explicitly by name.
3. Autodetection — the first known adapter found on `PATH`.

If none of the three resolves, the run fails with an actionable error. It never
falls back to `fake`: a silent fallback would suggest a model read the invoices
when in fact nothing did.

```sh
export COPILOTO_EXTRACTOR=cli
# optional, when several CLIs are installed:
export COPILOTO_CLI=codex
# optional, for any other tool:
export COPILOTO_EXTRACTOR_CMD="my-tool --non-interactive"
```

Known adapters and their verified invocations are listed in the README.

## `api` mode

```sh
uv sync --extra api
export COPILOTO_EXTRACTOR=api
export COPILOTO_API_PROVIDER=anthropic   # or: openai
export COPILOTO_MODEL=...                # optional, provider default otherwise
export ANTHROPIC_API_KEY=...             # or: OPENAI_API_KEY
```

This is the only mode with provider-guaranteed structured output, so it is the
one to use when reports are produced at scale.

## Secrets

Keys are read from the environment. This repository does not ship a `.env`
template on purpose, so that no one fills one in with a real key and commits it
by accident. `.env` is listed in `.gitignore`; export the variables in your shell
or use your own secret manager.

## Case state

| Variable | Default | Used by |
| --- | --- | --- |
| `COPILOTO_STATE_DB` | `copiloto-state.sqlite` for `serve`; in memory for `run` | `run --state-db`, `review`, `cases`, `serve` |
| `COPILOTO_HOST` | `127.0.0.1` | `serve` |
| `COPILOTO_PORT` | `8000` | `serve` |

The state file holds every case's checkpoints: inputs, extracted invoices,
analysis, the pause waiting for an accountant, and the report. Two processes
pointing at the same file see the same cases, which is how a case started on
the CLI or the web is resumed later by someone else. Delete the file to forget
every case. It is ignored by git.

The web server binds to localhost on purpose. It has no users, no
authentication and no rate limiting: anyone who can reach it can open every
case. Put it behind something that does those jobs before exposing it.

## Access token

| Variable | Default | Used by |
| --- | --- | --- |
| `COPILOTO_TOKEN` | unset, meaning no login | `serve` |

Unset, the web interface is open. That is the right default for a tool on your
own laptop, and it is why the server binds to localhost. Set it, and every page
except the login and the stylesheet needs a session first.

One shared token is not an identity system: it answers whether somebody is
allowed in, not who they are. Serving off localhost without it prints a warning
naming what gets published, because a case page is somebody's income.

Over plain HTTP the token travels in the clear. Put TLS in front of it before
it crosses anything you do not control.

## Optional extras

| Extra | Brings | Needed for |
| --- | --- | --- |
| `ocr` | pypdfium2, pytesseract, pillow | Reading scanned PDFs. Also needs the `tesseract` binary with Spanish data. |
| `arca` | defusedxml, cryptography | The real padrón client in `copiloto.arca`. |
| `api` | langchain-anthropic, langchain-openai | Extracting with a provider API. |

None of them are needed by the copilot itself. Without `ocr` a scanned invoice
is refused rather than skipped; without `arca` nothing changes, since the
default registry is the mock one.
