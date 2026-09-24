"""Skip the whole ARCA suite when its extra is not installed.

The README promises that a fresh clone runs everything with no extras, so
these modules cannot fail at import time. `collect_ignore_glob` decides that
before pytest tries to import them, which a `skipif` on a class cannot do:
by then the top-level `from defusedxml import ...` has already raised.

Install them with `uv sync --extra arca`.
"""

from importlib.util import find_spec

collect_ignore_glob = [] if find_spec("defusedxml") else ["test_*.py"]
