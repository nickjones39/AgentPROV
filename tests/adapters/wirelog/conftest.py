"""Fixtures for the ``wirelog`` adapter tests (docs/architecture D.20.12; K.6.4).

The committed Zenodo 21944598 fixtures hold prompt-injection payloads by design (CC-BY-4.0): no fixture or helper here
prints their content.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import wirelog_support as support  # noqa: E402


@pytest.fixture(scope="session")
def mapped() -> dict[str, support.Mapped]:
    """Every run fixture, mapped once with SEM and PROV, keyed by its selection criterion."""
    if not (support.FIXTURES / "SOURCE.json").is_file():
        pytest.skip("the committed Zenodo 21944598 fixtures are absent")
    return {crit: support.map_run(crit, sem=True, prov=True) for crit in support.F}
