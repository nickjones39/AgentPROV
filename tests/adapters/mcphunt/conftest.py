"""Fixtures for the ``mcphunt`` adapter tests (docs/architecture D.21.12; K.6.4).

The committed MCPHunt fixtures are canary-free traces (CC-BY-4.0): no fixture or helper here
prints their content.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import mcphunt_support as support  # noqa: E402


@pytest.fixture(scope="session")
def mapped() -> dict[str, support.Mapped]:
    """Every fixture trace, mapped once with SEM and PROV, keyed by its selection criterion."""
    if not (support.FIXTURES / "SOURCE.json").is_file():
        pytest.skip("the committed MCPHunt fixtures are absent")
    return {crit: support.map_trace(crit, sem=True, prov=True) for crit in support.criteria()}
