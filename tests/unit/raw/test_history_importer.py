"""The importer puts ``introduced_in_commit`` on a pinned file's git origin when the history index is cached, and only then (D.6.16)."""

from __future__ import annotations

import hashlib

from fetch_support import REPO_URL, needs_git
from history_support import make_history

from agentprov.adapters.runner.importer import GitPinTree, PinCheck
from agentprov.adapters.types import CandidateArtefact
from agentprov.raw.fetch import Fetcher, Recipe


def _fetcher(history, cache, **kwargs) -> Fetcher:
    return Fetcher(cache, remote_urls={REPO_URL: history.url}, file_protocol=True, **kwargs)


def _blob_sha1(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data, usedforsecurity=False).hexdigest()  # noqa: S324 - git object id


@needs_git
def test_a_fetched_tree_walks_with_and_without_the_index(tmp_path):
    history = make_history(tmp_path)
    recipe = Recipe(kind="git", repo=REPO_URL, commit=history.head, paths=("runs/",))
    fetcher = _fetcher(history, tmp_path / "cache", allow_network=True)
    fetcher.fetch(recipe)
    plain = {c.label: c.origin.data for c in GitPinTree(fetcher, recipe).walk()}
    assert plain and all("introduced_in_commit" not in o for o in plain.values())
    fetcher.fetch_history(recipe)
    indexed = {c.label: c.origin.data for c in GitPinTree(fetcher, recipe).walk()}
    assert {p: o["introduced_in_commit"] for p, o in indexed.items()} == {
        p: history.commits[n] for p, n in history.expect.items() if p.startswith("runs/")
    }
    for path, origin in indexed.items():  # everything else about the origin is unchanged
        assert {k: v for k, v in origin.items() if k != "introduced_in_commit"} == plain[path]


@needs_git
def test_an_input_tree_checked_against_the_pin_gets_the_commit_per_blob(tmp_path):
    history = make_history(tmp_path)
    recipe = Recipe(kind="git", repo=REPO_URL, commit=history.head, paths=("runs/",))
    fetcher = _fetcher(history, tmp_path / "cache", allow_network=True)
    fetcher.fetch(recipe)
    index = fetcher.fetch_history(recipe).index
    entries, _ = fetcher.git_tree(recipe)
    listing = {e.path: e.oid for e in entries if e.is_blob}
    pin = {"kind": "git", "commit": history.head}
    check = PinCheck("blob", pin, listing=listing, repo=REPO_URL, history=index)
    data = (history.path / "runs/a.json").read_bytes()
    assert _blob_sha1(data) == listing["runs/a.json"]
    origin = check.origin_for(CandidateArtefact("runs/a.json", len(data), None), data)  # type: ignore[arg-type]
    assert origin is not None and origin.data["introduced_in_commit"] == history.commits["c3"]
    # the same bytes under another label are not vouched for: no origin, hence no commit
    assert check.origin_for(CandidateArtefact("runs/other.json", len(data), None), data) is None  # type: ignore[arg-type]
    plain = PinCheck("blob", pin, listing=listing, repo=REPO_URL)
    origin = plain.origin_for(CandidateArtefact("runs/a.json", len(data), None), data)  # type: ignore[arg-type]
    assert origin is not None and "introduced_in_commit" not in origin.data
