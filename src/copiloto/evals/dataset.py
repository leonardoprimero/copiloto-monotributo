"""The synthetic eval dataset.

Regenerate the committed files with:

    uv run python scripts/build_eval_cases.py

Inputs are built here so they stay reproducible. Expectations are NOT: every
`Expected` below was worked out by hand from the ARCA table, with the
arithmetic recorded in its rationale. Deriving them from the code under test
would make every case pass by construction.

Reference figures (effective 2026-08-01):
    category A cap   12,009,410.45      90% = 10,808,469.405
    category H cap   81,924,660.37      90% = 73,732,194.333
    category K cap  126,610,838.75      90% = 113,949,754.875
    max unit price      716,840.77
"""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from copiloto.evals.schema import EvalCase, Expected, RegistryEntry
from copiloto.models import ExtractedInvoice, InvoiceItem
from copiloto.synthetic import render_invoice

TODAY = date(2026, 9, 24)
CASES_DIR = Path(__file__).resolve().parents[3] / "evals" / "cases"

CUIT_A = "20-11111111-2"  # registered in category A
CUIT_K = "27-22222222-8"  # registered in category K
CUIT_H = "30-44444444-0"  # registered in category H
CUIT_UNKNOWN = "23-33333333-3"  # valid check digit, absent from the registry
CUIT_INVALID = "20-11111111-3"  # wrong check digit

REGISTERED = {
    CUIT_A: RegistryEntry(cuit=CUIT_A, name="Synthetic Taxpayer One", category="A"),
    CUIT_K: RegistryEntry(cuit=CUIT_K, name="Synthetic Taxpayer Two", category="K"),
    CUIT_H: RegistryEntry(cuit=CUIT_H, name="Synthetic Taxpayer Four", category="H"),
}

# The 15th of each month, most recent first. The three most recent fall inside
# the 90-day projection window; all twelve fall inside the rolling year.
MONTHS = [date(2026, m, 15) for m in range(9, 0, -1)] + [
    date(2025, m, 15) for m in (12, 11, 10)
]


def invoice(
    *,
    index: int,
    issue_date: date,
    amount: str,
    cuit: str,
    kind: str = "service",
    total_override: str | None = None,
    description: str = "Servicios de consultoria en software",
) -> ExtractedInvoice:
    value = Decimal(amount)
    item = InvoiceItem(
        description=description,
        quantity=Decimal("1"),
        unit_price=value,
        total=value,
        kind=kind,  # pyright: ignore[reportArgumentType]
    )
    return ExtractedInvoice(
        number=f"0001-{index:08d}",
        issuer_cuit=cuit,
        issue_date=issue_date,
        items=(item,),
        total=Decimal(total_override) if total_override else value,
    )


def monthly(amount: str, cuit: str = CUIT_A) -> list[ExtractedInvoice]:
    return [
        invoice(index=i, issue_date=d, amount=amount, cuit=cuit)
        for i, d in enumerate(MONTHS)
    ]


def case(
    case_id: str,
    description: str,
    invoices: list[ExtractedInvoice],
    taxpayer_cuit: str,
    expected: Expected,
) -> EvalCase:
    return EvalCase(
        id=case_id,
        description=description,
        today=TODAY.isoformat(),
        taxpayer_cuit=taxpayer_cuit,
        registry_entry=REGISTERED.get(taxpayer_cuit),
        invoices=tuple(json.loads(i.model_dump_json()) for i in invoices),
        invoice_texts=tuple(render_invoice(i) for i in invoices),
        expected=expected,
    )


def build_cases() -> list[EvalCase]:
    cases: list[EvalCase] = []

    cases.append(
        case(
            "all_in_order",
            "Twelve steady months well inside category A.",
            monthly("800000"),
            CUIT_A,
            Expected(
                route="ok",
                risk_level="low",
                computed_category="A",
                issue_codes=(),
                rationale=(
                    "12 x 800,000 = 9,600,000, below 90% of the A cap "
                    "(10,808,469.405). Projection: 3 x 800,000 over 90 days "
                    "= 9,733,333.33, below the A cap. Nothing applies."
                ),
            ),
        )
    )

    cases.append(
        case(
            "near_cap",
            "Approaching the category A cap.",
            monthly("950000"),
            CUIT_A,
            Expected(
                route="review",
                risk_level="medium",
                computed_category="A",
                issue_codes=(),
                rationale=(
                    "12 x 950,000 = 11,400,000, at or above 90% of the A cap "
                    "(10,808,469.405) and still below it, so category A with "
                    "NEAR_REGISTERED_CAP. Medium is escalated by the chosen contract."
                ),
            ),
        )
    )

    cases.append(
        case(
            "category_change",
            "Income has outgrown the registered category.",
            monthly("1200000"),
            CUIT_A,
            Expected(
                route="review",
                risk_level="medium",
                computed_category="B",
                issue_codes=(),
                rationale=(
                    "12 x 1,200,000 = 14,400,000, above the A cap (12,009,410.45) "
                    "and below the B cap (17,595,182.74), so category B while A is "
                    "on file: CATEGORY_MISMATCH."
                ),
            ),
        )
    )

    # One invoice carries the remainder so the year totals the cap exactly.
    exact = monthly("1000000")[:11]
    exact.append(
        invoice(index=11, issue_date=MONTHS[11], amount="1009410.45", cuit=CUIT_A)
    )
    cases.append(
        case(
            "boundary_exact_cap",
            "The year totals the category A cap to the cent.",
            exact,
            CUIT_A,
            Expected(
                route="review",
                risk_level="medium",
                computed_category="A",
                issue_codes=(),
                rationale=(
                    "11 x 1,000,000 + 1,009,410.45 = 12,009,410.45, exactly the A "
                    "cap. Caps are inclusive, so the category is still A, and the "
                    "amount is above 90% of it: NEAR_REGISTERED_CAP."
                ),
            ),
        )
    )

    stale = monthly("800000")
    stale.append(
        invoice(index=12, issue_date=date(2025, 9, 15), amount="5000000", cuit=CUIT_A)
    )
    cases.append(
        case(
            "date_outside_window",
            "An old invoice that must not count towards the year.",
            stale,
            CUIT_A,
            Expected(
                route="ok",
                risk_level="low",
                computed_category="A",
                issue_codes=("OUTSIDE_WINDOW",),
                rationale=(
                    "The 2025-09-15 invoice sits before the window start "
                    "(2025-09-24), so the total stays 9,600,000. OUTSIDE_WINDOW is "
                    "informational and does not escalate on its own."
                ),
            ),
        )
    )

    bad_cuit = monthly("800000")
    bad_cuit[0] = invoice(
        index=0, issue_date=MONTHS[0], amount="800000", cuit=CUIT_INVALID
    )
    cases.append(
        case(
            "invalid_cuit",
            "One invoice whose issuing CUIT fails the check digit.",
            bad_cuit,
            CUIT_A,
            Expected(
                route="review",
                risk_level="low",
                computed_category="A",
                issue_codes=("INVALID_CUIT",),
                rationale=(
                    "Income is unchanged at 9,600,000, so the risk is low. The "
                    "doubtful invoice escalates on its own: 20-11111111-3 has "
                    "weighted sum 42, remainder 9, check digit 2, not 3."
                ),
            ),
        )
    )

    future = monthly("800000")
    future[0] = invoice(
        index=0, issue_date=date(2026, 12, 15), amount="800000", cuit=CUIT_A
    )
    cases.append(
        case(
            "date_in_future",
            "One invoice dated after today.",
            future,
            CUIT_A,
            Expected(
                route="review",
                risk_level="low",
                computed_category="A",
                issue_codes=("DATE_IN_FUTURE",),
                rationale=(
                    "The future invoice falls outside the window, so the total is "
                    "11 x 800,000 = 8,800,000, still category A and low risk. "
                    "DATE_IN_FUTURE is an error and escalates."
                ),
            ),
        )
    )

    mismatch = monthly("800000")
    mismatch[0] = invoice(
        index=0,
        issue_date=MONTHS[0],
        amount="800000",
        cuit=CUIT_A,
        total_override="900000",
    )
    cases.append(
        case(
            "total_mismatch",
            "An invoice whose total does not match its items.",
            mismatch,
            CUIT_A,
            Expected(
                route="review",
                risk_level="low",
                computed_category="A",
                issue_codes=("TOTAL_MISMATCH",),
                rationale=(
                    "The stated total 900,000 does not equal the single item's "
                    "800,000. The figure is still summed (9,700,000, category A, "
                    "low), and the mismatch escalates."
                ),
            ),
        )
    )

    over_priced = monthly("800000")
    over_priced[0] = invoice(
        index=0,
        issue_date=MONTHS[0],
        amount="716840.78",
        cuit=CUIT_A,
        kind="good",
        description="Equipo de computacion",
    )
    cases.append(
        case(
            "unit_price_above_max",
            "A good priced one cent above the maximum unit price.",
            over_priced,
            CUIT_A,
            Expected(
                route="review",
                risk_level="exclusion",
                computed_category="A",
                issue_codes=("UNIT_PRICE_ABOVE_MAX",),
                rationale=(
                    "716,840.78 exceeds the maximum unit price of 716,840.77 by one "
                    "cent. That is a cause of exclusion regardless of income, which "
                    "totals 9,516,840.78 and would otherwise be category A."
                ),
            ),
        )
    )

    unclear = monthly("800000")
    unclear[0] = invoice(
        index=0,
        issue_date=MONTHS[0],
        amount="716840.78",
        cuit=CUIT_A,
        kind="unknown",
        description="Item sin clasificar",
    )
    cases.append(
        case(
            "unit_price_kind_unknown",
            "An over-priced item whose kind was never determined.",
            unclear,
            CUIT_A,
            Expected(
                route="review",
                risk_level="low",
                computed_category="A",
                issue_codes=("UNIT_PRICE_KIND_UNKNOWN",),
                rationale=(
                    "The maximum unit price only governs goods, so it cannot be "
                    "applied to an unclassified item. Not exclusion, but not "
                    "excused either: the warning sends it to a person."
                ),
            ),
        )
    )

    cases.append(
        case(
            "exclusion_by_income",
            "Income above the highest category.",
            monthly("11000000", cuit=CUIT_K),
            CUIT_K,
            Expected(
                route="review",
                risk_level="exclusion",
                computed_category=None,
                issue_codes=(),
                rationale=(
                    "12 x 11,000,000 = 132,000,000, above the K cap "
                    "(126,610,838.75). No category contains it, so the computed "
                    "category is absent rather than K."
                ),
            ),
        )
    )

    # Nine calm months, then three at more than double the pace.
    accelerating = [
        invoice(index=i, issue_date=d, amount="12000000" if i < 3 else "5000000", cuit=CUIT_H)
        for i, d in enumerate(MONTHS)
    ]
    cases.append(
        case(
            "projected_exclusion",
            "A recent surge that projects past the regime.",
            accelerating,
            CUIT_H,
            Expected(
                route="review",
                risk_level="high",
                computed_category="H",
                issue_codes=(),
                rationale=(
                    "Accumulated: 3 x 12,000,000 + 9 x 5,000,000 = 81,000,000, "
                    "within the H cap (81,924,660.37). The last 90 days hold "
                    "36,000,000, so 36,000,000 / 90 x 365 = 146,000,000, above the "
                    "K cap: PROJECTION_ABOVE_TOP_CAP."
                ),
            ),
        )
    )

    cases.append(
        case(
            "unknown_taxpayer",
            "A valid CUIT that is not in the registry.",
            monthly("800000", cuit=CUIT_UNKNOWN),
            CUIT_UNKNOWN,
            Expected(
                route="review",
                risk_level="low",
                computed_category="A",
                issue_codes=("TAXPAYER_NOT_FOUND",),
                rationale=(
                    "23-33333333-3 passes the check digit (sum 118, remainder 8, "
                    "digit 3) but is absent from the registry. Without a registered "
                    "category the comparisons are skipped, leaving low risk, and "
                    "the missing profile escalates."
                ),
            ),
        )
    )

    cases.append(
        case(
            "empty_input",
            "No invoices at all.",
            [],
            CUIT_A,
            Expected(
                route="review",
                risk_level="low",
                computed_category="A",
                issue_codes=("NO_INVOICES",),
                rationale=(
                    "Zero income maps to category A and no risk condition applies, "
                    "which reads exactly like a clean result. It is missing data, "
                    "so NO_INVOICES escalates instead."
                ),
            ),
        )
    )

    return cases


def write_cases(directory: Path = CASES_DIR) -> int:
    """Write every case to disk and return how many were written."""
    directory.mkdir(parents=True, exist_ok=True)
    cases = build_cases()
    for built in cases:
        (directory / f"{built.id}.json").write_text(
            built.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
    return len(cases)
