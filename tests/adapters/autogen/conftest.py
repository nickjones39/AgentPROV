"""Fixtures for the ``autogen`` adapter tests (docs/architecture D.19.12; K.6.4).

The committed AutoGen guard-placement fixtures hold injection passages by design (CC-BY-4.0 data, MIT code; private
repository): no fixture or helper here prints their content. ``staged`` maps rows of the staged deposit zip and skips
when it is absent (CI has no staging directory).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import autogen_support as support  # noqa: E402


@pytest.fixture(scope="session")
def tool_arm() -> dict[str, support.Mapped]:
    """Every run of the committed InjecAgent tool-block arm, mapped once with SEM and PROV, keyed by run_id."""
    if not (support.FIXTURES / "SOURCE.json").is_file():
        pytest.skip("the committed AutoGen fixtures are absent")
    return support.map_file(support.TOOL_ARM, support.fixture_members(), sem=True, prov=True)


@pytest.fixture(scope="session")
def staged():
    """The staged deposit's members, or skip."""
    members = support.staged_members()
    if members is None:
        pytest.skip("the staged deposit zip (Zenodo 23025259 v1.0) is absent")
    return members
