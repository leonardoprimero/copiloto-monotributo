"""Taxpayer registry lookups, behind a Protocol.

The only thing the graph needs from ARCA is the category a taxpayer is
registered in. The MVP answers that from an in-memory table of synthetic CUITs:
it never contacts ARCA, and it never asks anyone for a fiscal password.

A production lookup would be a second implementation of `TaxpayerRegistry`,
deployed privately, authenticating as itself under ARCA's delegation model so
that the taxpayer grants and revokes access without handing over credentials.
The exact mechanism must be verified against official documentation before it
is built; nothing here assumes it.
"""

from typing import Protocol, runtime_checkable

from copiloto.cuit import normalize_cuit
from copiloto.models import TaxpayerProfile


@runtime_checkable
class TaxpayerRegistry(Protocol):
    """Resolve a CUIT to a registered profile, or report that it is unknown."""

    def lookup(self, cuit: str) -> TaxpayerProfile | None: ...

    def known_cuits(self) -> tuple[str, ...]: ...


class MockArcaRegistry:
    """An in-memory registry keyed by normalized CUIT."""

    def __init__(self, profiles: dict[str, TaxpayerProfile]) -> None:
        self._profiles = {normalize_cuit(cuit): p for cuit, p in profiles.items()}

    def lookup(self, cuit: str) -> TaxpayerProfile | None:
        return self._profiles.get(normalize_cuit(cuit))

    def known_cuits(self) -> tuple[str, ...]:
        return tuple(self._profiles)


class UnavailableRegistry:
    """A registry for graphs that must never look anything up.

    A case resumed after a pause already carries its taxpayer in the checkpoint,
    and the lookup node does not run again. Whoever resumes may not have the
    declared category at hand, so instead of inventing one, the resume graph
    gets a registry that fails loudly if any node consults it.
    """

    def lookup(self, cuit: str) -> TaxpayerProfile | None:
        raise RuntimeError(
            f"The registry was consulted for {cuit} on a graph that must not look up anyone."
        )

    def known_cuits(self) -> tuple[str, ...]:
        return ()


# Synthetic taxpayers used by the demo and the eval cases. The repeated digit
# patterns make it obvious at a glance that none of these belong to a person;
# each one still carries a correct check digit so validation exercises the real
# algorithm. "23-33333333-3" is deliberately absent: it is the valid-but-unknown
# case.
_SYNTHETIC = {
    "20-11111111-2": TaxpayerProfile(
        cuit="20-11111111-2", name="Synthetic Taxpayer One", category="A"
    ),
    "27-22222222-8": TaxpayerProfile(
        cuit="27-22222222-8", name="Synthetic Taxpayer Two", category="K"
    ),
    "30-44444444-0": TaxpayerProfile(
        cuit="30-44444444-0", name="Synthetic Taxpayer Four", category="H"
    ),
}


def default_registry() -> MockArcaRegistry:
    """The registry used by the demo, the eval runner and the tests."""
    return MockArcaRegistry(_SYNTHETIC)
