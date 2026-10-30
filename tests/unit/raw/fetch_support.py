"""Test doubles for ``agentprov.raw.fetch``: a local upstream repository and a fake HTTP layer. No test touches the network.

The upstream repository is created with ``git`` in a temporary directory and fetched through ``file://`` with the test seam
of :class:`~agentprov.raw.fetch.Fetcher` (``remote_urls`` and ``file_protocol``); the recipe still names an https repository,
exactly as a profile does.
"""

from __future__ import annotations

import functools
import hashlib
import os
import shutil
import subprocess
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from agentprov.raw.fetch import Fetcher, Recipe

REPO_URL = "https://example.invalid/acme/runs"
_ENV = {
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z", "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z",
}  # fmt: skip

FILES: dict[str, bytes] = {
    "README.md": b"readme\n",
    "runs/a/one.json": b'{"n": 1}\n',
    "runs/a/two.json": b'{"n": 2}\n',
    "runs/b/three.json": b'{"n": 3}\n',
    "other/skip.txt": b"not under runs\n",
}
SYMLINK_TARGET = "../../etc/passwd"
GITLINK_SHA = "1" * 40


def have_git() -> bool:
    return shutil.which("git") is not None


needs_git = pytest.mark.skipif(not have_git(), reason="git is not installed")


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True, env={**os.environ, **_ENV}
    )
    return done.stdout.strip()


@dataclass
class Upstream:
    path: Path
    commit: str
    later_commit: str
    blob_ids: dict[str, str] = field(default_factory=dict)

    @property
    def url(self) -> str:
        return f"file://{self.path}"

    def recipe(self, **changes: object) -> Recipe:
        base: dict[str, object] = {"kind": "git", "repo": REPO_URL, "commit": self.commit, "paths": ("runs/",)}
        base.update(changes)
        return Recipe(**base)  # type: ignore[arg-type]

    def fetcher(self, cache: Path, **kwargs: object) -> Fetcher:
        kwargs.setdefault("remote_urls", {REPO_URL: self.url})
        kwargs.setdefault("file_protocol", True)
        return Fetcher(cache, **kwargs)  # type: ignore[arg-type]


def make_upstream(root: Path) -> Upstream:
    """Two commits: the first holds FILES, a symlink and a gitlink; the second adds one more run file.

    The repository is built once per process (13 git calls; the commit ids are fixed by ``_ENV``'s dates) and each call
    gets its own copy, symlink included, so a test that changes its repository (config, hooks) changes only its own."""
    template, first, later, ids = _template()
    repo = root / "upstream"
    shutil.copytree(template, repo, symlinks=True)
    return Upstream(repo, first, later, dict(ids))


@functools.cache
def _template() -> tuple[Path, str, str, dict[str, str]]:
    repo = Path(tempfile.mkdtemp(prefix="upstream-template-")) / "upstream"  # under the test process's private TMPDIR
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    for rel, data in FILES.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_bytes(data)
    os.symlink(SYMLINK_TARGET, repo / "runs" / "link.json")
    git(repo, "add", "-A")
    git(repo, "update-index", "--add", "--cacheinfo", f"160000,{GITLINK_SHA},runs/sub")
    git(repo, "commit", "-q", "-m", "first")
    first = git(repo, "rev-parse", "HEAD")
    (repo / "runs/b/four.json").write_bytes(b'{"n": 4}\n')
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "second")
    later = git(repo, "rev-parse", "HEAD")
    ids = {rel: git(repo, "rev-parse", f"{first}:{rel}") for rel in FILES}
    return repo, first, later, ids


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class FakeResponse:
    """A minimal ``HttpResponse``: reads the body in the sizes asked for."""

    def __init__(self, body: bytes, *, status: int = 200, headers: Mapping[str, str] | None = None, url: str = "") -> None:
        self.status = status
        self.headers = dict(headers or {})
        self.url = url
        self._body = body
        self._pos = 0
        self.closed = False

    def read(self, n: int = -1, /) -> bytes:
        end = len(self._body) if n < 0 else self._pos + n
        chunk = self._body[self._pos : end]
        self._pos += len(chunk)
        return chunk

    def close(self) -> None:
        self.closed = True


@dataclass
class Call:
    url: str
    headers: dict[str, str]
    unredirected: dict[str, str]
    timeout: float
    allowed_hosts: frozenset[str]


class FakeTransport:
    """Serves ``routes`` (URL to ``FakeResponse`` factory arguments) and records every call."""

    def __init__(self, routes: Mapping[str, bytes | tuple[bytes, int, Mapping[str, str]]]) -> None:
        self.routes = dict(routes)
        self.calls: list[Call] = []
        self.responses: list[FakeResponse] = []

    def open(self, url: str, *, headers: Mapping[str, str], unredirected: Mapping[str, str], timeout: float, allowed_hosts: frozenset[str]) -> FakeResponse:
        self.calls.append(Call(url, dict(headers), dict(unredirected), timeout, allowed_hosts))
        route = self.routes[url]
        if isinstance(route, bytes):
            response = FakeResponse(route, url=url)
        else:
            body, status, extra = route
            response = FakeResponse(body, status=status, headers=extra, url=url)
        self.responses.append(response)
        return response
