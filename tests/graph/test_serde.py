"""Checkpoint serialization of this project's own types.

Pausing writes the state to a checkpoint and resuming reads it back. langgraph
1.2.12 accepts unregistered types with a warning today and says it will block
them later; under `LANGGRAPH_STRICT_MSGPACK=true` it already degrades them to
plain dicts instead of raising, which would surface far from the cause.

Declaring the allowlist explicitly makes the round trip exact and keeps the
graph working when the permissive default goes away.
"""

from datetime import date
from decimal import Decimal

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from copiloto.analysis import Analysis
from copiloto.graph.serde import ALLOWED_TYPES, copilot_serde
from copiloto.models import ExtractedInvoice, HumanDecision, InvoiceItem, Issue, TaxpayerProfile

ITEM = InvoiceItem(
    description="Consultoria",
    quantity=Decimal("1"),
    unit_price=Decimal("800000.00"),
    total=Decimal("800000.00"),
    kind="service",
)
INVOICE = ExtractedInvoice(
    number="0001-00000001",
    issuer_cuit="20-11111111-2",
    issue_date=date(2026, 9, 15),
    items=(ITEM,),
    total=Decimal("800000.00"),
)
ANALYSIS = Analysis(
    accumulated_12m=Decimal("9600000"),
    projected_12m=Decimal("9733333.33"),
    computed_category="A",
    registered_category="A",
    risk_level="low",
    reasons=("NEAR_REGISTERED_CAP",),
    headroom_registered=Decimal("2409410.45"),
    headroom_top=Decimal("117010838.75"),
    months_to_registered_cap=Decimal("3.0"),
    months_to_top_cap=Decimal("144.3"),
)


def round_trip(value, serde=None):
    serde = serde or copilot_serde()
    return serde.loads_typed(serde.dumps_typed(value))


class TestRoundTrip:
    def test_every_state_type_survives_a_checkpoint(self) -> None:
        values = [
            ITEM,
            INVOICE,
            ANALYSIS,
            Issue(code="X", severity="warning", message="m"),
            TaxpayerProfile(cuit="20-11111111-2", name="Synthetic One", category="A"),
            HumanDecision(verdict="confirmed", notes="ok", reviewer="accountant"),
        ]

        for value in values:
            assert round_trip(value) == value

    def test_decimals_keep_their_exact_value(self) -> None:
        """A cent lost in serialization is a cent lost in the category."""
        restored = round_trip(INVOICE)

        assert restored.total == Decimal("800000.00")
        assert isinstance(restored.total, Decimal)


class TestAllowlistCompleteness:
    def test_the_allowlist_covers_every_type_the_state_carries(self) -> None:
        names = {t.__name__ for t in ALLOWED_TYPES}

        assert names == {
            "InvoiceItem",
            "ExtractedInvoice",
            "Issue",
            "TaxpayerProfile",
            "HumanDecision",
            "DeclaredParameters",
            "Analysis",
        }


class TestWithoutTheAllowlist:
    def test_a_strict_serializer_silently_degrades_our_types(self) -> None:
        """Documents why the allowlist exists: this fails quietly, not loudly."""
        strict = JsonPlusSerializer(allowed_msgpack_modules=None)

        restored = round_trip(INVOICE, serde=strict)

        assert restored != INVOICE
        assert isinstance(restored, dict)
