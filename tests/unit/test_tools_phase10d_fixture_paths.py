"""Upstream tree paths are labels, never paths (audit AU-TRS-11).

``tools/agentdojo/phase10d_fixtures.py`` named its output files after the pinned tree's paths, and ``phase10d_trial.py
seed`` (also used by ``phase10j_trial.py seed``) stored a clone's objects without the product fetch's object checks, so a
tree entry ``..`` reached the scratch cache and the builder wrote outside ``tests/fixtures/<NAME>``. The seed now indexes
the pack with ``--fsck-objects`` and the builder refuses any path that is not a plain relative path before writing.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[2]
TOOLS = REPO / "tools" / "agentdojo"

_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.invalid", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
        "PATH": os.environ.get("PATH", "")}


@pytest.fixture(scope="module")
def tools():
    sys.path.insert(0, str(TOOLS))
    try:
        import phase10d_fixtures
        import phase10d_trial

        yield phase10d_trial, phase10d_fixtures
    finally:
        sys.path.remove(str(TOOLS))


def _git(repo: Path, *args: str, data: bytes | None = None) -> str:
    done = subprocess.run(["git", "-C", str(repo), *args], input=data, capture_output=True, env=_ENV, check=True)
    return done.stdout.decode().strip()


def _clone_with(tmp_path: Path, middle: str) -> tuple[Path, str]:
    """A bare repo whose commit holds runs/<middle>/settings.json, built with mktree (git refuses '..' otherwise)."""
    clone = tmp_path / "clone.git"
    subprocess.run(["git", "init", "-q", "--bare", str(clone)], env=_ENV, check=True)
    blob = _git(clone, "hash-object", "-w", "--stdin", data=b'{"attack_type": null, "messages": []}')
    tree = _git(clone, "mktree", data=f"100644 blob {blob}\tsettings.json\n".encode())
    tree = _git(clone, "mktree", data=f"040000 tree {tree}\t{middle}\n".encode())
    tree = _git(clone, "mktree", data=f"040000 tree {tree}\truns\n".encode())
    return clone, _git(clone, "commit-tree", tree, "-m", "x")


@pytest.mark.parametrize("middle", ["..", ".git"])
def test_seed_refuses_a_tree_entry_the_product_fetch_would_refuse(tools, tmp_path, monkeypatch, middle) -> None:
    trial, _ = tools
    clone, commit = _clone_with(tmp_path, middle)
    recipe = SimpleNamespace(commit=commit, cache_path=lambda cache: cache / "store.git")
    monkeypatch.setattr(trial, "_recipe", lambda _pid: (None, recipe, {}))
    with pytest.raises(SystemExit, match="index-pack failed"):
        trial.seed("any", clone, tmp_path / "cache")


def test_seed_keeps_a_plain_tree(tools, tmp_path, monkeypatch) -> None:
    trial, _ = tools
    clone, commit = _clone_with(tmp_path, "sub")
    recipe = SimpleNamespace(commit=commit, cache_path=lambda cache: cache / "store.git")
    monkeypatch.setattr(trial, "_recipe", lambda _pid: (None, recipe, {}))
    assert trial.seed("any", clone, tmp_path / "cache")["blobs"] == 1


@pytest.mark.parametrize("path", ["", "/etc/x.json", "runs/../x.json", "runs/./x.json", "runs//x.json", "runs/a\\b.json",
                                  "runs/a\0.json", "runs/.GIT/x.json", "runs/"])
def test_unsafe_tree_paths(tools, path) -> None:
    _, fixtures = tools
    assert fixtures.unsafe_tree_path(path)


def test_write_fixture_stays_inside_the_root_and_never_follows_a_symlink(tools, tmp_path) -> None:
    _, fixtures = tools
    root = tmp_path / "fixtures" / "NAME"
    root.mkdir(parents=True)
    fixtures.write_fixture(root, "runs/a/b.json", b"{}")
    assert (root / "runs" / "a" / "b.json").read_bytes() == b"{}"
    with pytest.raises(SystemExit):
        fixtures.write_fixture(root, "runs/../../escape.json", b"{}")
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "link").symlink_to(outside)
    with pytest.raises(SystemExit):
        fixtures.write_fixture(root, "link/x.json", b"{}")
    (root / "leaf.json").symlink_to(outside / "leaf.json")
    with pytest.raises(SystemExit):
        fixtures.write_fixture(root, "leaf.json", b"{}")
    assert not any(outside.iterdir())
    assert not (tmp_path / "fixtures" / "escape.json").exists()


def _fake_cache(paths: list[str]) -> tuple[object, object]:
    entries = [SimpleNamespace(path=p, is_blob=True, oid=f"{i:040x}") for i, p in enumerate(paths)]
    entries.append(SimpleNamespace(path="LICENSE", is_blob=True, oid="f" * 40))
    data = b'{"attack_type": null, "user_task_id": "user_task_0", "messages": []}'
    fetcher = SimpleNamespace(
        git_tree=lambda _recipe: (entries, None),
        iter_git_blobs=lambda _recipe, wanted: (SimpleNamespace(entry=e, data=data) for e in wanted))
    return fetcher, SimpleNamespace(repo="https://example.invalid/r", commit="0" * 40)


def test_build_refuses_a_dotdot_tree_path_and_writes_nothing(tools, tmp_path, monkeypatch) -> None:
    trial, fixtures = tools
    from agentprov.adapters.profiles import load_profile

    profile = load_profile("melon-agentdojo")
    fetcher, recipe = _fake_cache(["runs/../../../../.claude/settings.json"])
    monkeypatch.setattr(trial, "_fetcher_recipe", lambda _pid, _cache: (profile, fetcher, recipe, {}, []))
    monkeypatch.setattr(fixtures, "REPO", tmp_path / "repo")
    (tmp_path / "repo" / "tests" / "fixtures" / "LICENSES").mkdir(parents=True)
    with pytest.raises(SystemExit, match="not plain relative paths"):
        fixtures.build("melon-agentdojo", tmp_path / "cache", "NAME", "LICENSE", "L.txt", (), False, 40_000)
    written = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert written == []


def test_build_writes_a_plain_tree_path_under_the_fixture_root(tools, tmp_path, monkeypatch) -> None:
    trial, fixtures = tools
    from agentprov.adapters.profiles import load_profile

    profile = load_profile("melon-agentdojo")
    fetcher, recipe = _fake_cache(["runs/m/s/u/i/a.json"])
    monkeypatch.setattr(trial, "_fetcher_recipe", lambda _pid, _cache: (profile, fetcher, recipe, {}, []))
    monkeypatch.setattr(fixtures, "REPO", tmp_path / "repo")
    (tmp_path / "repo" / "tests" / "fixtures" / "LICENSES").mkdir(parents=True)
    rows = fixtures.build("melon-agentdojo", tmp_path / "cache", "NAME", "LICENSE", "L.txt", (), False, 40_000)
    assert [r["path"] for r in rows] == ["runs/m/s/u/i/a.json"]
    assert (tmp_path / "repo" / "tests" / "fixtures" / "NAME" / "runs" / "m" / "s" / "u" / "i" / "a.json").is_file()
