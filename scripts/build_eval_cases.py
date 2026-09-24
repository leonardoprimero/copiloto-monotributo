"""Regenerate the committed eval cases.

    uv run python scripts/build_eval_cases.py

The dataset itself lives in `copiloto.evals.dataset`, so it can be imported and
tested like any other module. This file only runs it.
"""

from copiloto.evals.dataset import CASES_DIR, write_cases


def main() -> None:
    print(f"Wrote {write_cases()} cases to {CASES_DIR}")


if __name__ == "__main__":
    main()
