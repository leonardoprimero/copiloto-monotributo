"""Loader for the ARCA monotributo scales.

The numbers live in `config/monotributo_scales.json` rather than in the logic,
because ARCA updates them every semester. Keeping them as data means the report
can state which table it used and when that table took effect.
"""

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from functools import cache
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "monotributo_scales.json"


class ScalesError(RuntimeError):
    """The scales table is missing or unusable.

    Raised instead of a bare OSError or KeyError so the operator is told which
    file to fix. Without a valid table there is no category and no risk level,
    so failing loudly is the only safe behaviour.
    """


@dataclass(frozen=True, slots=True)
class Category:
    """One monotributo category, as published."""

    name: str
    income_cap: Decimal
    surface_cap_m2: int
    annual_energy_cap_kwh: int
    annual_rent_cap: Decimal


@dataclass(frozen=True, slots=True)
class Scales:
    """A published scales table, together with its provenance."""

    source: str
    effective_from: date
    retrieved_on: date
    max_unit_price: Decimal
    categories: tuple[Category, ...]
    income_caps_depend_on_activity: bool

    @property
    def top_category(self) -> Category:
        """The highest category; exceeding its cap means exclusion."""
        return self.categories[-1]


def _parse(payload: dict) -> Scales:
    categories = tuple(
        Category(
            name=entry["name"],
            income_cap=Decimal(entry["income_cap"]),
            surface_cap_m2=entry["surface_cap_m2"],
            annual_energy_cap_kwh=entry["annual_energy_cap_kwh"],
            annual_rent_cap=Decimal(entry["annual_rent_cap"]),
        )
        for entry in payload["categories"]
    )
    return Scales(
        source=payload["source"],
        effective_from=date.fromisoformat(payload["effective_from"]),
        retrieved_on=date.fromisoformat(payload["retrieved_on"]),
        max_unit_price=Decimal(payload["max_unit_price"]),
        categories=categories,
        income_caps_depend_on_activity=payload["income_caps_depend_on_activity"],
    )


@cache
def load_scales(path: Path = CONFIG_PATH) -> Scales:
    """Read the scales table from disk. Cached: the file does not change at runtime."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ScalesError(f"Cannot read the monotributo scales at {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise ScalesError(f"The monotributo scales at {path} are not valid JSON: {error}") from error

    try:
        return _parse(payload)
    except (KeyError, TypeError, ValueError, InvalidOperation) as error:
        raise ScalesError(f"The monotributo scales at {path} are malformed: {error}") from error
