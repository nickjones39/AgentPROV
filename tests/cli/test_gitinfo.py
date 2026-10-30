"""``agentprov.cli.gitinfo``: the commit of the AgentPROV checkout that runs a command (HL H.2.7; D-780).

The tests make small real git repositories under a temporary directory (the suite's autouse fixture otherwise replaces
the per-process facts with a fixed commit, so no other test runs git for this). Checked: a clean and a dirty tree, the
cwd never used, a directory that is not a git checkout (no commit, never another repository's), an enclosing repository
that must not be mistaken for the checkout (a virtual environment inside a project), git missing or failing, the
caller's ``GIT_*`` variables ignored, the facts read once per process, and the step the CLI hands the writer.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from agentprov.cli import gitinfo
from agentprov.corpus.buildstep import BuildStep

ORIGINAL_FACTS = gitinfo._facts  # taken at collection, before the autouse fixture replaces it

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


def git(repo: Path, *args: str) -> str:
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@example.invalid", "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin", "HOME": str(repo)}
    done = subprocess.run(["git", "-c", "commit.gpgsign=false", "-C", str(repo), *args], capture_output=True, text=True,
                          env=env, check=True)
    return done.stdout.strip()


def make_checkout(root: Path) -> tuple[Path, str]:
    root.mkdir(parents=True)
    (root / "src" / "agentprov").mkdir(parents=True)
    (root / "src" / "agentprov" / "__init__.py").write_text("")
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "one")
    return root, git(root, "rev-parse", "HEAD")


def test_a_clean_checkout_gives_its_head_and_clean(tmp_path):
    repo, head = make_checkout(tmp_path / "repo")
    assert gitinfo.checkout_state(repo) == (head, True, None)
    assert gitinfo.git_facts(repo) == (head, True)


def test_a_dirty_tree_is_reported_not_hidden(tmp_path):
    repo, head = make_checkout(tmp_path / "repo")
    (repo / "src" / "agentprov" / "__init__.py").write_text("# edited\n")
    assert gitinfo.checkout_state(repo) == (head, False, None)
    (repo / "src" / "agentprov" / "__init__.py").write_text("")
    (repo / "untracked.txt").write_text("x")
    assert gitinfo.checkout_state(repo)[1] is False


def test_the_commit_is_the_checkouts_not_the_current_directorys(tmp_path, monkeypatch):
    repo, head = make_checkout(tmp_path / "repo")
    other, other_head = make_checkout(tmp_path / "other")
    (other / "second.txt").write_text("2")
    git(other, "add", "-A")
    git(other, "commit", "-q", "-m", "two")
    monkeypatch.chdir(other)
    assert gitinfo.checkout_state(repo)[0] == head != git(other, "rev-parse", "HEAD")


def test_a_directory_that_is_no_git_checkout_has_no_commit_and_a_reason(tmp_path):
    plain = tmp_path / "site-packages-parent"
    (plain / "src" / "agentprov").mkdir(parents=True)
    (plain / "src" / "agentprov" / "__init__.py").write_text("")
    assert gitinfo.checkout_state(plain) == (None, False, "not_a_source_checkout")


def test_an_enclosing_repository_is_never_mistaken_for_the_checkout(tmp_path):
    outer, _ = make_checkout(tmp_path / "project")
    inside = outer / ".venv" / "lib" / "python3.14"  # an installed wheel: the source root sits inside someone's project
    (inside / "src" / "agentprov").mkdir(parents=True)
    (inside / "src" / "agentprov" / "__init__.py").write_text("")
    assert gitinfo.checkout_state(inside) == (None, False, "not_a_source_checkout")
    bare = outer / "docs"
    bare.mkdir()
    assert gitinfo.checkout_state(bare)[2] == "not_a_source_checkout"  # no package source there either


def test_the_callers_git_variables_cannot_name_another_repository(tmp_path, monkeypatch):
    repo, head = make_checkout(tmp_path / "repo")
    other, _ = make_checkout(tmp_path / "other")
    monkeypatch.setenv("GIT_DIR", str(other / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(other))
    assert gitinfo.checkout_state(repo) == (head, True, None)


def test_git_missing_or_failing_is_a_reason_never_a_guess(tmp_path, monkeypatch):
    repo, _ = make_checkout(tmp_path / "repo")
    monkeypatch.setattr(gitinfo.shutil, "which", lambda name: None)
    assert gitinfo.checkout_state(repo) == (None, False, "git_unavailable")
    monkeypatch.undo()
    real = gitinfo._git
    monkeypatch.setattr(gitinfo, "_git", lambda r, *a: None if a[:1] == ("status",) else real(r, *a))
    assert gitinfo.checkout_state(repo) == (None, False, "git_failed")


def test_git_facts_of_an_unknown_tree_is_none_and_not_clean(tmp_path):
    assert gitinfo.git_facts(tmp_path) == (None, False)


def test_the_step_for_a_commit_and_for_a_missing_checkout(monkeypatch):
    monkeypatch.setattr(gitinfo, "_facts", lambda: ("f" * 40, False, None, None))
    assert gitinfo.build_step("derive") == BuildStep("derive", gitinfo.__version__, git_commit="f" * 40, git_tree_clean=False)
    monkeypatch.setattr(gitinfo, "_facts", lambda: (None, False, "git_unavailable", "sha256:" + "1" * 64))
    step = gitinfo.build_step("import")
    assert step.git_commit is None and step.git_commit_absent_reason == "git_unavailable"
    assert step.distributions_sha256 == "sha256:" + "1" * 64


def test_the_facts_are_read_once_per_process(monkeypatch):
    calls = []
    monkeypatch.setattr(gitinfo, "_facts", ORIGINAL_FACTS)
    ORIGINAL_FACTS.cache_clear()
    monkeypatch.setattr(gitinfo, "checkout_state", lambda: calls.append(1) or ("a" * 40, True, None))
    first, second = gitinfo.build_step("import"), gitinfo.build_step("run")
    assert len(calls) == 1 and first.git_commit == second.git_commit == "a" * 40
    ORIGINAL_FACTS.cache_clear()


def test_the_distributions_digest_has_the_sealing_form():
    digest = gitinfo.distributions_sha256()
    assert digest.startswith("sha256:") and len(digest) == 71


def test_the_real_checkout_under_test_answers_with_a_commit_or_a_reason():
    commit, _clean, reason = gitinfo.checkout_state()
    assert (commit is not None and len(commit) == 40 and reason is None) or (commit is None and reason is not None)
