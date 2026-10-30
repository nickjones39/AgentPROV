"""Fixtures for the ``dtap`` adapter tests (docs/architecture D.16.14; K.6.4).

The committed DTap fixtures hold prompt-injection payloads and jailbreak text by design (Apache-2.0, private repository
only): no fixture or helper here prints their content.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import dtap_support as support  # noqa: E402


@pytest.fixture(scope="session")
def mapped() -> dict[str, support.Mapped]:
    """Every fixture that is an execution, mapped once with SEM and PROV."""
    if not (support.FIXTURES / "SOURCE.json").is_file():
        pytest.skip("the committed DTap fixtures are absent")
    return {fid: support.map_label(support.F[fid], sem=True, prov=True) for fid in support.MAPPED}
