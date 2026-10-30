"""Fixtures for the ``openhands`` adapter tests (docs/architecture D.17.12; K.6.4).

The committed fixtures hold harmful task text, NPC dialogue and agent output by design (MIT and CC-BY-4.0, private
repository only): no fixture or helper here prints their content.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import openhands_support as support  # noqa: E402


@pytest.fixture(scope="session")
def mapped() -> dict[str, support.Mapped]:
    """Every fixture run, mapped once with SEM and PROV."""
    if not (support.FIXTURES / "SOURCE.json").is_file():
        pytest.skip("the committed OpenHands fixtures are absent")
    return {fid: support.map_fixture(fid, sem=True, prov=True) for fid in support.F}
