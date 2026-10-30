"""Fixtures for the ``credleak`` adapter tests (docs/architecture D.19.12; K.6.4).

The committed credleak fixtures hold prompt-injection payloads by design (CC-BY-4.0, unedited cells without planted
credentials): no fixture or helper here prints their content.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import credleak_support as support  # noqa: E402


@pytest.fixture(scope="session")
def mapped() -> dict[str, list[support.Mapped]]:
    """Every fixture cell, every run mapped once with SEM and PROV, keyed by the cell's path."""
    if not (support.FIXTURES / "SOURCE.json").is_file():
        pytest.skip("the committed credleak fixtures are absent")
    return {e["path"]: support.map_entry(e) for e in support.source_entries()}
