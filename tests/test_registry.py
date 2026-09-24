"""The taxpayer registry, behind a Protocol.

The MVP ships one implementation: an in-memory registry of synthetic CUITs.
It never contacts ARCA and never asks anyone for credentials. A real lookup
would be another implementation of the same Protocol, in a private deployment,
using ARCA's delegation model rather than a user's fiscal password.
"""

import pytest

from copiloto.cuit import is_valid_cuit
from copiloto.registry import MockArcaRegistry, TaxpayerRegistry, default_registry
from copiloto.scales import load_scales


class TestProtocol:
    def test_the_mock_satisfies_the_registry_protocol(self) -> None:
        assert isinstance(MockArcaRegistry({}), TaxpayerRegistry)


class TestLookup:
    def test_finds_a_known_synthetic_taxpayer(self) -> None:
        profile = default_registry().lookup("20-11111111-2")

        assert profile is not None
        assert profile.category == "A"

    def test_returns_none_for_an_unknown_cuit(self) -> None:
        """Absence is reported, not invented. The caller raises the issue."""
        assert default_registry().lookup("23-33333333-3") is None

    def test_lookup_ignores_formatting(self) -> None:
        registry = default_registry()

        assert registry.lookup("20111111112") == registry.lookup("20-11111111-2")

    def test_an_invalid_cuit_is_never_found(self) -> None:
        assert default_registry().lookup("20-11111111-3") is None


class TestSyntheticData:
    def test_every_registered_cuit_is_structurally_valid(self) -> None:
        assert all(is_valid_cuit(cuit) for cuit in default_registry().known_cuits())

    def test_every_registered_category_exists_in_the_scales(self) -> None:
        names = {c.name for c in load_scales().categories}
        registry = default_registry()

        for cuit in registry.known_cuits():
            profile = registry.lookup(cuit)
            assert profile is not None
            assert profile.category in names

    @pytest.mark.parametrize(
        ("cuit", "category"),
        [("20-11111111-2", "A"), ("27-22222222-8", "K"), ("30-44444444-0", "H")],
    )
    def test_the_fixture_taxpayers_cover_the_eval_scenarios(
        self, cuit: str, category: str
    ) -> None:
        profile = default_registry().lookup(cuit)

        assert profile is not None
        assert profile.category == category

    def test_names_are_obviously_synthetic(self) -> None:
        registry = default_registry()

        for cuit in registry.known_cuits():
            profile = registry.lookup(cuit)
            assert profile is not None
            assert "Synthetic" in profile.name
