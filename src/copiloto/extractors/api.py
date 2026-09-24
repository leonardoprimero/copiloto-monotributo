"""Reading invoices through a provider API.

The mode for deployments that produce reports at scale. `with_structured_output`
makes the provider return the schema, so the JSON hunting, validation loop and
single retry that the `cli` extractor needs are simply absent here.

That is the shape of the trade-off worth knowing: the paid path is the shorter
code, and the free path is the one that costs work. The provider packages are
an optional extra, so a fresh clone still runs its tests with nothing installed.
"""

from collections.abc import Callable, Mapping
from importlib import import_module
from typing import Any, Protocol

from copiloto.extractors.protocol import ExtractionError
from copiloto.extractors.schema import RawInvoice, build_prompt, to_invoice
from copiloto.models import ExtractedInvoice

Importer = Callable[[str], Any]

# Each provider: the package that must be installed, and the class to use.
_PROVIDERS = {
    "anthropic": ("langchain_anthropic", "ChatAnthropic"),
    "openai": ("langchain_openai", "ChatOpenAI"),
}

_DEFAULT_PROVIDER = "anthropic"


class StructuredModel(Protocol):
    """A chat model already bound to the invoice schema."""

    def invoke(self, prompt: str) -> RawInvoice: ...


def build_chat_model(*, env: Mapping[str, str], importer: Importer = import_module):
    """Build the provider's chat model from the environment.

    Raises rather than guessing: an unusable configuration must be reported
    before any invoice is read, not silently downgraded.
    """
    provider = env.get("COPILOTO_API_PROVIDER", _DEFAULT_PROVIDER).strip().lower()
    if provider not in _PROVIDERS:
        raise ExtractionError(
            f"Unknown COPILOTO_API_PROVIDER={provider!r}. Supported providers: "
            f"{', '.join(_PROVIDERS)}."
        )

    package, class_name = _PROVIDERS[provider]
    try:
        module = importer(package)
    except ImportError as error:
        raise ExtractionError(
            f"The {provider} provider needs {package}, which ships in an optional "
            f"extra. Install it with: uv sync --extra api"
        ) from error

    model_id = env.get("COPILOTO_MODEL", "").strip()
    chat_model = getattr(module, class_name)
    return chat_model(model=model_id) if model_id else chat_model()


class ApiExtractor:
    """Extract invoices through a provider that guarantees the answer's shape."""

    def __init__(self, structured_model: StructuredModel) -> None:
        self._model = structured_model

    @classmethod
    def from_env(
        cls, *, env: Mapping[str, str], importer: Importer = import_module
    ) -> "ApiExtractor":
        model = build_chat_model(env=env, importer=importer)
        return cls(model.with_structured_output(RawInvoice))

    def extract(self, raw: str) -> ExtractedInvoice:
        try:
            answer = self._model.invoke(build_prompt(raw))
        except ExtractionError:
            raise
        except Exception as error:
            # Rate limits, timeouts, auth failures: the graph only knows
            # ExtractionError, and records it as an issue for a human.
            raise ExtractionError(f"The provider call failed: {error}") from error

        return to_invoice(answer.model_dump())
