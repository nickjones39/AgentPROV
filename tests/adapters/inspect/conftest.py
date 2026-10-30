"""Fixtures for the ``inspect.eval`` adapter tests (docs/architecture D.9.4; K.6.4).

The committed fixture is one complete survey AgentHarm log (``restricted_use``; K.4.1(5)) plus the two investigation
member samples of the gptoss_benign log. The other five logs are read from the pinned survey clone
(``$AGENTPROV_SURVEY_CLONE``) by the tests that need all six, which skip with the reason when it is absent. AgentHarm
holds harmful requests by design: no fixture or helper here prints their content (R-42).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import inspect_support as support  # noqa: E402


@pytest.fixture(scope="session")
def committed(tmp_path_factory: pytest.TempPathFactory) -> support.Imported:
    """The committed complete log, imported once per session."""
    path = support.committed_log()
    if not path.is_file():
        pytest.skip("the committed Inspect fixture log is absent")
    return support.import_log(path.read_bytes(), tmp_path_factory.mktemp("committed-raw"), path=support.COMMITTED_LOG)
