"""Fixtures for the ``geminicli`` adapter tests (docs/architecture D.23.11; K.6.4).

The committed gemini-cli fixtures are agentic-misalignment rollouts (CC-BY-4.0, private repository only): their task files,
prompts and agent output hold manipulative text by design. No fixture or helper here prints their content.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import geminicli_support as support  # noqa: E402


@pytest.fixture(scope="session")
def mapped() -> dict[str, support.Mapped]:
    """Every stream fixture, mapped once with SEM and PROV, keyed by its first selection criterion."""
    if not (support.FIXTURES / "SOURCE.json").is_file():
        pytest.skip("the committed gemini-cli fixtures are absent")
    return {crit: support.map_dir(d, sem=True, prov=True) for crit, d in support.streams().items()}
