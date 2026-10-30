"""Makes the sibling helper ``capture_schema_builder`` importable (pytest runs with ``--import-mode=importlib``)."""

from __future__ import annotations

import sys
from pathlib import Path

# capture/tests is on the path for its `cap_support` helper (the writer replays the C.13.8 session in the core tests too)
for _dir in (
    Path(__file__).resolve().parent,
    Path(__file__).resolve().parents[1] / "aer",
    Path(__file__).resolve().parents[3] / "capture" / "tests",
):
    if str(_dir) not in sys.path:
        sys.path.insert(0, str(_dir))
