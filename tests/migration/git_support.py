"""A synthetic baseline for the migration tests: a tiny git repository with the same shape as the real one (no real data)."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from agentprov.migration.lock import LOCK_FORMAT, PREDICATES, TREE_SPECS, tree_listing

_ENV = {
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
}
TRACKED = {"README.md": b"readme\n", "pkg/mod.py": b"x = 1\n"}
TAG = "baseline-tag"
OLD_TAGS = ("pub-1", "pub-2")


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True, env={**os.environ, **_ENV})
    return done.stdout.strip()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_repo(root: Path) -> Path:
    """A repo with 2 tracked files, an annotated baseline tag, two annotated published tags and the five gitignored trees."""
    repo = root / "old-repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "master")
    (repo / ".gitignore").write_text("corpus/\nruns/\n")
    for rel, data in TRACKED.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_bytes(data)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "first")
    for name in OLD_TAGS:
        git(repo, "tag", "-a", name, "-m", name)
    git(repo, "tag", "-a", TAG, "-m", "frozen")
    for stem, root_rel in (("a", "corpus/corpus-prov/m1"), ("b", "corpus/corpus-og-agentdojo-runs-prov/m2")):
        base = repo / root_rel / "prov" / "atk"
        base.mkdir(parents=True)
        (base / f"{stem}.transcript.json").write_bytes(b'{"t": "' + stem.encode() + b'"}\n')
        (base / f"{stem}.json").write_bytes(b'{"g": "' + stem.encode() + b'"}')
        (repo / root_rel / "manifest.json").write_bytes(b"{}")  # matches no predicate but `json`-style ones elsewhere
    (repo / "runs" / "pipe" / "suite").mkdir(parents=True)
    (repo / "runs" / "pipe" / "suite" / "log.json").write_bytes(b'{"log": 1}')
    return repo


def make_lock(repo: Path, **env_hashes: str | None) -> dict[str, Any]:
    commit = git(repo, "rev-parse", "HEAD")
    trees = {}
    for name, (root, predicate) in TREE_SPECS.items():
        listing = tree_listing(repo / root, PREDICATES[predicate])
        trees[name] = {"root": root, "predicate": predicate, "files": listing.files, "listing_sha256": listing.listing_sha256}
    return {
        "lock": LOCK_FORMAT,
        "frozen_on": "2026-10-07",
        "framework": {
            "remote": "git@example.invalid:x/y.git",
            "commit": commit,
            "describe": "synthetic",
            "tag": {"name": TAG, "object": git(repo, "rev-parse", TAG), "pushed": False},
            "existing_tags": {name: git(repo, "rev-parse", f"{name}^{{commit}}") for name in OLD_TAGS},
            "package": {"name": "p", "version": "1"},
            "tracked_files": {rel: sha(data) for rel, data in TRACKED.items()},
        },
        "environment": {
            "python": "3.12.14", "uv": "0.12.18", "agentdojo": "0.1.35", "pip_freeze_sha256": "0" * 64, "packages": {"prov": "3.2.2"},
            "requirements_lock_sha256": env_hashes.get("requirements_lock_sha256"),
            "baseline_wheel_sha256": env_hashes.get("baseline_wheel_sha256"),
        },
        "results": {"pytest": {"passed": 1}},
        "trees": trees,
        "investigation_record": {"BASELINE.md": "1" * 64},
    }


def write_lock(path: Path, lock: dict[str, Any]) -> Path:
    path.write_text(json.dumps(lock, indent=2) + "\n")
    return path


def snapshot(root: Path) -> dict[str, tuple[int, int]]:
    """Every file under ``root`` (including ``.git``) with size and mtime: equal before and after means nothing was written."""
    return {
        p.relative_to(root).as_posix(): (p.stat().st_size, p.stat().st_mtime_ns)
        for p in sorted(root.rglob("*")) if p.is_file() and not p.is_symlink()
    }
