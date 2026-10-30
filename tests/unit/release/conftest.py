"""Makes ``release_support`` and the sealing helpers of ``tests/unit/corpus`` importable (``--import-mode=importlib``)."""

from __future__ import annotations

import sys
from pathlib import Path

_UNIT = Path(__file__).resolve().parents[1]
for _here in (str(_UNIT / "raw"), str(_UNIT / "corpus"), str(Path(__file__).resolve().parent)):
    if _here not in sys.path:
        sys.path.insert(0, _here)
