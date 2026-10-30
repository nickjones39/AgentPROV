"""Fixtures for the workflow tools (``tools/session_status.py``, ``queue_status.py``, ``reserve_id.py``; D-423, D-428).

Every test works in a temporary git repository under ``tmp_path`` with the user's global and system git configuration
switched off, and with ``AGENTPROV_HOME`` and the tools' own directories pointed into ``tmp_path``. No test reads or
writes the real repository or ``~/.agentprov``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
TOOLS = REPO / "tools"
_HERE = str(Path(__file__).resolve().parent)
for _p in (_HERE, str(TOOLS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from wf_support import commit, git, write  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "agentprov-home"
    empty = tmp_path / "empty.gitconfig"
    empty.write_text("", encoding="utf-8")
    monkeypatch.setenv("AGENTPROV_HOME", str(home))
    for var in ("AGENTPROV_SESSIONS_DIR", "AGENTPROV_IDS_DIR", "AGENTPROV_SUITE_QUEUE_DIR", "AGENTPROV_SESSION_NAME"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{role}_NAME", "Test")
        monkeypatch.setenv(f"GIT_{role}_EMAIL", "test@example.invalid")
    return home


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repository on branch ``main`` with one commit, and ``origin/main`` pointing at it (no remote needed)."""
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    write(root, "README.md", "test repository\n")
    sha = commit(root, "base")
    git(root, "update-ref", "refs/remotes/origin/main", sha)
    return root
