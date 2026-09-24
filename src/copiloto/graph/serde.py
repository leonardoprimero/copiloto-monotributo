"""Checkpoint serialization for this project's own types.

Pausing for an accountant writes the state to a checkpoint; resuming reads it
back. langgraph 1.2.12 deserializes unregistered types with a warning and
announces it will block them; with `LANGGRAPH_STRICT_MSGPACK=true` it already
returns plain dicts instead of our models, which fails far from the cause.

Declaring the allowlist here makes the round trip exact today and keeps the
human-in-the-loop branch working when the permissive default disappears.
"""

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from copiloto.analysis import Analysis
from copiloto.models import (
    ExtractedInvoice,
    HumanDecision,
    InvoiceItem,
    Issue,
    TaxpayerProfile,
)

# Every type that can appear in CopilotState. A test asserts this set matches
# the state, so adding a field without registering its type fails loudly.
ALLOWED_TYPES = (
    InvoiceItem,
    ExtractedInvoice,
    Issue,
    TaxpayerProfile,
    HumanDecision,
    Analysis,
)


def copilot_serde() -> JsonPlusSerializer:
    """A serializer that knows this project's types and nothing else."""
    return JsonPlusSerializer(allowed_msgpack_modules=None).with_msgpack_allowlist(
        ALLOWED_TYPES
    )
