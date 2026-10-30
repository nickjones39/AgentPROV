"""Fixtures for the ``agentops`` adapter tests (docs/architecture D.18.12; K.6.4).

The committed AgentOps-Bench fixtures hold prompt-injection payloads by design (Apache-2.0, private repository only): no
fixture or helper here prints their content.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import agentops_support as support  # noqa: E402


@pytest.fixture(scope="session")
def mapped() -> dict[str, support.Mapped]:
    """Every run fixture, mapped once with SEM and PROV, keyed by its selection criterion."""
    if not (support.FIXTURES / "SOURCE.json").is_file():
        pytest.skip("the committed AgentOps-Bench fixtures are absent")
    return {crit: support.map_label(label, sem=True, prov=True) for crit, label in support.F.items()}
