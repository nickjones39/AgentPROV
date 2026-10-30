"""Property tests share the helpers of ``tests/unit/aer`` (``aer_support``, ``schema_builder``) and the ingest-format
builders of ``tests/security`` (``format_support``)."""

from __future__ import annotations

import sys
from pathlib import Path

for _SUPPORT in (str(Path(__file__).resolve().parents[1] / "unit" / "aer"),
                 str(Path(__file__).resolve().parents[1] / "security")):  # fmt: skip
    if _SUPPORT not in sys.path:
        sys.path.insert(0, _SUPPORT)
