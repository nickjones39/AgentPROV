"""The baseline byte layout of a stored graph (glue; docs/architecture EF E.8.3, J.3.3).

The baseline wrote every graph as ``json.dumps(doc, indent=2)`` through ``Path.write_text(..., encoding="utf-8")``
(``generate.py:468`` -> ``transcript.atomic_write_text``): default ``ensure_ascii=True``, no ``sort_keys``, member order as
inserted, separators ``(",", ": ")``, no trailing newline, and ``\\n`` line breaks. The call is spelled out in full here so
that no ambient default can change the bytes. Gate B compares ``serialise(build_prov(view))`` with the stored bytes.
"""

from __future__ import annotations

import json
from typing import Any


def serialise(doc: dict[str, Any]) -> bytes:
    """``doc`` as the bytes the baseline stored: ``json.dumps(doc, indent=2)``, UTF-8, no trailing newline."""
    text = json.dumps(
        doc,
        indent=2,
        ensure_ascii=True,
        sort_keys=False,
        allow_nan=True,
        separators=(",", ": "),
    )
    return text.encode("utf-8")
