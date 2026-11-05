"""Fixtures for the D-1065 update tests (the fakes are in ``update_support``)."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "aphome"
    path.mkdir()
    monkeypatch.setenv("AGENTPROV_HOME", str(path))
    return path


@pytest.fixture
def no_keys(tmp_path: Path) -> Path:
    """An allowed-signers file that lists no key (the package as shipped before a key is added)."""
    path = tmp_path / "allowed_signers.empty"
    path.write_text("# no key\n")
    return path
