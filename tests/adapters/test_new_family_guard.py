"""``new_family_guard``: the base the "new family touches only the family" guards diff against.

Temporary repositories only. A worktree's local ``main`` is often stale; after the branch merges ``origin/main``, the
guard must not count main's own commits as the branch's changes.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from new_family_guard import branch_changes, changed_or_skip, merge_base  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    empty = tmp_path / "empty.gitconfig"
    empty.write_text("", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{role}_NAME", "Test")
        monkeypatch.setenv(f"GIT_{role}_EMAIL", "test@example.invalid")


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()


def _commit(repo: Path, rel: str, text: str) -> str:
    (repo / rel).parent.mkdir(parents=True, exist_ok=True)
    (repo / rel).write_text(text, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", rel)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _commit(root, "README.md", "base\n")
    return root


def test_a_stale_local_main_does_not_count_merged_commits_as_the_branchs(repo: Path) -> None:
    stale = _git(repo, "rev-parse", "HEAD")  # the local main stays here, as in a worktree
    _git(repo, "switch", "-q", "-c", "upstream")
    _commit(repo, "src/agentprov/aer/core_change_on_main.py", "x\n")  # main moved on (another session)
    _git(repo, "update-ref", "refs/remotes/origin/main", _git(repo, "rev-parse", "HEAD"))
    _git(repo, "switch", "-q", "-c", "family", stale)
    _commit(repo, "src/agentprov/adapters/newfam/mapper.py", "y\n")
    _git(repo, "merge", "-q", "--no-edit", "origin/main")  # the session merges origin/main
    assert _git(repo, "rev-parse", "main") == stale
    changed, how = branch_changes(repo)
    assert changed == {"src/agentprov/adapters/newfam/mapper.py"} and how == "merge base with origin/main"


def test_a_local_main_ahead_of_origin_is_the_base(repo: Path) -> None:
    _git(repo, "update-ref", "refs/remotes/origin/main", _git(repo, "rev-parse", "HEAD"))
    _commit(repo, "docs/merged_not_pushed.md", "z\n")  # local main ahead of origin/main
    _git(repo, "switch", "-q", "-c", "family")
    _commit(repo, "src/agentprov/adapters/newfam/mapper.py", "y\n")
    changed, how = branch_changes(repo)
    assert changed == {"src/agentprov/adapters/newfam/mapper.py"} and how == "merge base with main"


def test_only_a_local_main(repo: Path) -> None:
    _git(repo, "switch", "-q", "-c", "family")
    _commit(repo, "a.txt", "a\n")
    (repo / "untracked.txt").write_text("u\n", encoding="utf-8")
    changed, how = branch_changes(repo)
    assert changed == {"a.txt", "untracked.txt"} and how == "merge base with main"


def test_no_base_skips_with_the_reason(tmp_path: Path) -> None:
    root = tmp_path / "solo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "trunk")
    _commit(root, "a.txt", "a\n")
    base, how = merge_base(root)
    assert base is None and "no origin/main or main" in how
    with pytest.raises(pytest.skip.Exception, match="needs a base to compare with: no origin/main or main"):
        changed_or_skip(root)
    base, how = merge_base(tmp_path / "not-a-repo-at-all")
    assert base is None and "not a git checkout" in how
