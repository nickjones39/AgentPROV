"""Shared pieces of the security suites (K.12): helper modules on the path and the ``cwd_guard`` of K.11.1 F-3.

pytest runs with ``--import-mode=importlib``, so the sibling helper modules are put on the path here, as
``tests/property/conftest.py`` and ``tests/adapters/runner/conftest.py`` do.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TESTS = Path(__file__).resolve().parents[1]
# aer_support (tests/unit/aer), import_support (tests/adapters), agentdojo_support (tests/adapters/agentdojo),
# fetch_support (tests/unit/raw) and this directory's import_harness
for _path in (_TESTS / "unit" / "aer", _TESTS / "adapters", _TESTS / "adapters" / "agentdojo", _TESTS / "unit" / "raw",
              _TESTS / "security"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))


@pytest.fixture
def cwd_guard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """F-3: run in an empty working directory and fail if anything was created there."""
    work = tmp_path / "cwd"
    work.mkdir()
    monkeypatch.chdir(work)
    yield work
    assert sorted(p.name for p in work.iterdir()) == []
