"""The fuzz layer of K.11.1: helper modules on the path (``--import-mode=importlib``) and the F-3 guard.

The Hypothesis budgets live in ``fuzz_support`` (``AGENTPROV_FUZZ=thorough`` for the manually dispatched job); no global
Hypothesis profile is loaded here, so other suites keep their own settings.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_TESTS = Path(__file__).resolve().parents[1]
for _path in (_TESTS / "fuzz", _TESTS / "unit" / "aer", _TESTS / "adapters", _TESTS / "adapters" / "agentdojo",
              _TESTS / "unit" / "raw", _TESTS / "security"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))


@pytest.fixture(autouse=True, scope="module")
def fs_guard(tmp_path_factory: pytest.TempPathFactory):
    """F-3: every fuzz module runs in an empty working directory and must leave it empty."""
    work = tmp_path_factory.mktemp("fuzz-cwd")
    before = Path.cwd()
    os.chdir(work)
    try:
        yield work
    finally:
        os.chdir(before)
    assert sorted(p.name for p in work.iterdir()) == []
