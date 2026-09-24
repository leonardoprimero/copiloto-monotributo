"""The shape of an eval case.

A case is an input plus the answer a person worked out by hand. The expected
values are never derived from the code under test: an expectation computed by
the same logic it checks would pass by construction and prove nothing.
"""

from pydantic import BaseModel, ConfigDict


class Expected(BaseModel):
    """The hand-computed answer for a case."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    route: str  # "ok" or "review"
    risk_level: str
    computed_category: str | None
    issue_codes: tuple[str, ...]
    # The arithmetic behind the numbers, so a failing case can be argued with
    # rather than just re-run.
    rationale: str


class RegistryEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    cuit: str
    name: str
    category: str


class EvalCase(BaseModel):
    """One synthetic scenario with a known correct answer."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    description: str
    today: str
    taxpayer_cuit: str
    registry_entry: RegistryEntry | None
    # Ground truth and the rendered text, in the same order. The fake extractor
    # maps one to the other; the cli and api extractors read the text and are
    # scored against the ground truth field by field.
    invoices: tuple[dict, ...]
    invoice_texts: tuple[str, ...]
    expected: Expected
