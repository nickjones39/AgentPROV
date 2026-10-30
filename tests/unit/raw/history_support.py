"""A synthetic upstream with a small, awkward history for the introducing-commit index (D.6.16). No network.

The history (committer dates are set per commit; ``c1``..``c14`` name the commits in :class:`History`)::

    c1  2024-05-01  a.json=A b.json=B e.json=E0 README
    side   c2 2024-05-02 +c.json=C      c3 2024-05-03 a.json -> A2
    main   c4 2024-05-04 +d.json=D, rename b.json -> b2.json (identical blob B), +:odd.json, +"sp ace é.json"
           c5 2024-05-05 -d.json        c6 2024-05-06 +d.json=D again (a re-add of an identical blob)
    c7  2024-05-07  merge side (clean: c.json and a.json=A2 were introduced by c2 and c3, not by the merge)
    x      c8 2024-05-08 e.json -> E1   main c9 2024-05-09 e.json -> E2
    c10 2024-05-10  merge x with a conflict resolved to E3 (neither parent holds it: the merge introduces it)
    y      c11 2024-05-11 +f.json=F     main c12 2024-05-12 +f.json=F, with a *later* merge of y
    c13 2024-05-13  merge y (clean; f.json=F was introduced by c11, the earlier date, even though c12 is on main)
    c14 2024-05-14  g.json=G1 -> G2 -> G1 within one commit chain: c14 g=G1, c15 g=G2, c16 g=G1 (a revert restores an old blob)
"""

from __future__ import annotations

import functools
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from fetch_support import REPO_URL

_ENV = {
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
}  # fmt: skip


def _git(repo: Path, *args: str, date: str | None = None, check: bool = True) -> str:
    env = {**os.environ, **_ENV}
    if date is not None:
        env["GIT_COMMITTER_DATE"] = env["GIT_AUTHOR_DATE"] = date
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=check, env=env)
    return done.stdout.strip()


@dataclass
class History:
    path: Path
    head: str
    commits: dict[str, str] = field(default_factory=dict)  # name (c1..) -> commit id
    dates: dict[str, str] = field(default_factory=dict)  # name -> RFC 3339 UTC date
    expect: dict[str, str] = field(default_factory=dict)  # path at head -> name of the introducing commit

    @property
    def url(self) -> str:
        return f"file://{self.path}"


def make_history(root: Path) -> History:
    """The history above, built once per process (about 57 git calls; every commit date is fixed, so the ids are too)
    and copied for each caller."""
    template = _template()
    repo = root / "history-upstream"
    shutil.copytree(template.path, repo, symlinks=True)
    return History(repo, template.head, dict(template.commits), dict(template.dates), dict(template.expect))


@functools.cache
def _template() -> History:
    repo = Path(tempfile.mkdtemp(prefix="history-template-")) / "history-upstream"  # the process's private TMPDIR
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "uploadpack.allowFilter", "true")
    _git(repo, "config", "uploadpack.allowAnySHA1InWant", "true")
    out = History(repo, "")

    def write(rel: str, text: str | None) -> None:
        target = repo / rel
        if text is None:
            target.unlink()
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text)

    def commit(name: str, date: str) -> None:
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", name, date=f"{date}T10:00:00Z")
        out.commits[name] = _git(repo, "rev-parse", "HEAD")
        out.dates[name] = f"{date}T10:00:00Z"

    def merge(name: str, date: str, other: str, *, resolve: dict[str, str] | None = None) -> None:
        done = subprocess.run(
            ["git", "-C", str(repo), "merge", "-q", "--no-ff", "--no-edit", "-m", name, other],
            capture_output=True, text=True, check=False,
            env={**os.environ, **_ENV, "GIT_COMMITTER_DATE": f"{date}T10:00:00Z", "GIT_AUTHOR_DATE": f"{date}T10:00:00Z"},
        )  # fmt: skip
        if resolve is not None:
            assert done.returncode != 0, "the merge was expected to conflict"
            for rel, text in resolve.items():
                (repo / rel).write_text(text)
            _git(repo, "add", "-A")
            _git(repo, "commit", "-q", "-m", name, date=f"{date}T10:00:00Z")
        else:
            assert done.returncode == 0, done.stderr
        out.commits[name] = _git(repo, "rev-parse", "HEAD")
        out.dates[name] = f"{date}T10:00:00Z"

    def at(rel: str, text: str | None) -> None:
        write(rel, text)

    at("README.md", "readme\n")
    at("runs/a.json", "A\n")
    at("runs/b.json", "B\n")
    at("runs/e.json", "E0\nline\n")
    commit("c1", "2024-05-01")
    _git(repo, "checkout", "-q", "-b", "side")
    at("runs/c.json", "C\n")
    commit("c2", "2024-05-02")
    at("runs/a.json", "A2\n")
    commit("c3", "2024-05-03")
    _git(repo, "checkout", "-q", "main")
    _git(repo, "branch", "x", "main")
    _git(repo, "branch", "y", "main")
    at("runs/d.json", "D\n")
    _git(repo, "mv", "runs/b.json", "runs/b2.json")
    at("runs/:odd.json", "odd\n")
    at("runs/sp ace é.json", "sp\n")
    commit("c4", "2024-05-04")
    at("runs/d.json", None)
    commit("c5", "2024-05-05")
    at("runs/d.json", "D\n")
    commit("c6", "2024-05-06")
    merge("c7", "2024-05-07", "side")
    _git(repo, "checkout", "-q", "x")
    at("runs/e.json", "E1\nline\n")
    commit("c8", "2024-05-08")
    _git(repo, "checkout", "-q", "main")
    at("runs/e.json", "E2\nline\n")
    commit("c9", "2024-05-09")
    merge("c10", "2024-05-10", "x", resolve={"runs/e.json": "E3\nline\n"})
    _git(repo, "checkout", "-q", "y")
    at("runs/f.json", "F\n")
    commit("c11", "2024-05-11")
    _git(repo, "checkout", "-q", "main")
    at("runs/f.json", "F\n")
    commit("c12", "2024-05-12")
    merge("c13", "2024-05-13", "y")
    at("runs/g.json", "G1\n")
    commit("c14", "2024-05-14")
    at("runs/g.json", "G2\n")
    commit("c15", "2024-05-15")
    at("runs/g.json", "G1\n")
    commit("c16", "2024-05-16")
    out.head = out.commits["c16"]
    out.expect = {
        "README.md": "c1",
        "runs/a.json": "c3",
        "runs/b2.json": "c4",
        "runs/c.json": "c2",
        "runs/d.json": "c4",
        "runs/e.json": "c10",
        "runs/f.json": "c11",
        "runs/g.json": "c14",
        "runs/:odd.json": "c4",
        "runs/sp ace é.json": "c4",
    }
    return out


def recipe_kwargs(history: History) -> dict[str, object]:
    return {"kind": "git", "repo": REPO_URL, "commit": history.head, "paths": ("runs/",)}
