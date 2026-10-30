"""``tools/seed_git_cache.py``: offline seeding never lazily fetches, and refuses an incomplete clone with a typed code (R2).

The clone is a local repository; its promisor remote (for the partial clone) is another local repository, so a lazy fetch
would be visible as blobs appearing in the clone. No test touches the network.
"""

from __future__ import annotations

import importlib.util
import os
import socket
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from fetch_support import REPO_URL, git, make_upstream, needs_git

from agentprov.adapters import profiles as profiles_mod

_TOOL = Path(__file__).resolve().parents[3] / "tools" / "seed_git_cache.py"
_spec = importlib.util.spec_from_file_location("seed_git_cache_tool", _TOOL)
assert _spec is not None and _spec.loader is not None
seed = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed)


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_a: object, **_k: object) -> None:
        raise AssertionError("a test tried to use the network")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)


def _profile(monkeypatch: pytest.MonkeyPatch, commit: str) -> None:
    source = {"canonical_repo": REPO_URL, "pins": [{"role": "head", "kind": "git", "commit": commit, "tree": "runs/"}]}
    monkeypatch.setattr(profiles_mod, "load_profile", lambda pid: SimpleNamespace(id=pid, data={"source": source}))


def _has_blob(repo: Path, oid: str) -> bool:
    env = {**os.environ, "GIT_NO_LAZY_FETCH": "1", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    return subprocess.run(["git", "-C", str(repo), "cat-file", "-e", oid], env=env, capture_output=True).returncode == 0


@needs_git
def test_seeding_from_a_complete_clone_works_offline(tmp_path, monkeypatch, capsys):
    up = make_upstream(tmp_path)
    _profile(monkeypatch, up.commit)
    cache = tmp_path / "cache"
    assert seed.main(["--profile", "p", "--pin", "head", "--clone", str(up.path), "--cache", str(cache)]) == 0
    assert f"commit {up.commit}" in capsys.readouterr().out
    assert (cache / "git" / "example.invalid" / "acme" / "runs.git" / "objects").is_dir()


@needs_git
def test_seeding_from_a_partial_clone_is_refused_with_a_typed_code_and_fetches_nothing(tmp_path, monkeypatch, capsys):
    up = make_upstream(tmp_path)
    git(up.path, "config", "uploadpack.allowFilter", "true")
    partial = tmp_path / "partial"
    git(tmp_path, "-c", "protocol.file.allow=always", "clone", "-q", "--filter=blob:none", "--no-checkout", up.url, str(partial))
    oid = up.blob_ids["runs/a/one.json"]
    assert not _has_blob(partial, oid)
    _profile(monkeypatch, up.commit)
    cache = tmp_path / "cache"
    code = seed.main(["--profile", "p", "--pin", "head", "--clone", str(partial), "--cache", str(cache)])
    err = capsys.readouterr().err
    assert code == 1 and err.startswith("raw.fetch.") and "partial clone" in err
    assert "Traceback" not in err
    assert not _has_blob(partial, oid), "the partial clone fetched an absent blob from its promisor remote"
    assert not (cache / "acquisitions.jsonl").exists()


def test_a_partial_clone_is_recognised_from_its_config_text(tmp_path):
    full, part = tmp_path / "full", tmp_path / "part"
    for root, text in ((full, "[core]\n\tbare = false\n"), (part, '[remote "origin"]\n\tpromisor = true\n')):
        (root / ".git").mkdir(parents=True)
        (root / ".git" / "config").write_text(text)
    assert not seed._is_partial_clone(full) and seed._is_partial_clone(part)
    assert not seed._is_partial_clone(tmp_path / "missing")
