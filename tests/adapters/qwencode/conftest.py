"""Fixtures for the ``qwencode`` adapter tests (docs/architecture D.24.10; K.6.4).

The committed fixtures are RedCode-Exec runs (CC-BY-4.0, private repository only): the requests ask agents to run risky
code by design, and outputs echo it. No fixture or helper here prints their content.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import qwencode_support as support  # noqa: E402


@pytest.fixture(scope="session")
def mapped() -> dict[str, support.Mapped]:
    """Every non-empty run fixture, mapped once with SEM and PROV, keyed by its first criterion."""
    if not (support.FIXTURES / "SOURCE.json").is_file():
        pytest.skip("the committed qwencode fixtures are absent")
    return {crit: support.map_run(label, sem=True, prov=True) for crit, label in support.runs().items()}
