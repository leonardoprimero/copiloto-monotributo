"""The rolling twelve-month window.

Exclusion is assessed over the last twelve months counted backwards from a
given day, not over a calendar year. `today` is a parameter everywhere instead
of a call to `date.today()`, so results are reproducible and tests do not
expire.
"""

from datetime import date


def one_year_before(today: date) -> date:
    """The same calendar day one year earlier.

    February 29 has no counterpart in a non-leap year, so it falls back to
    February 28.
    """
    try:
        return today.replace(year=today.year - 1)
    except ValueError:
        return today.replace(year=today.year - 1, day=28)


def within_window(day: date, *, today: date) -> bool:
    """Whether `day` falls in `(today - 1 year, today]`.

    Half-open on purpose: the window spans exactly twelve months, so the day
    one year ago belongs to the previous period, and today counts.
    """
    return one_year_before(today) < day <= today
