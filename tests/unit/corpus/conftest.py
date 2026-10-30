"""Makes the sibling helper modules ``raw_support`` and ``facet_support`` importable (pytest runs with
``--import-mode=importlib``)."""

from __future__ import annotations

import sys
from pathlib import Path

for _here in (str(Path(__file__).resolve().parents[1] / "raw"), str(Path(__file__).resolve().parent)):
    if _here not in sys.path:
        sys.path.insert(0, _here)
