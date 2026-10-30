"""``agentprov import --dry-run --artefacts`` (MN N.2.2; D.15.4): the per-class artefact table, nothing left behind.

The positive runs seed a temporary fetch cache with a local repository of the golden native logs, as ``test_import_cmd``
does (no network); everything else is the real import pipeline.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

_TESTS = Path(__file__).resolve().parents[1]
for _path in (_TESTS / "adapters", _TESTS / "unit" / "raw"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import import_support as support  # noqa: E402
from fetch_support import git, needs_git  # noqa: E402

AGENTDOJO = "https://github.com/ethz-spylab/agentdojo"


@pytest.fixture
def seeded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    from agentprov.cli import import_
    from agentprov.raw.fetch import Fetcher, Recipe

    upstream = tmp_path / "upstream"
    entries = support.agentdojo_tree(upstream, count=4)
    git(upstream, "init", "-q", "-b", "main")
    git(upstream, "add", "-A")
    git(upstream, "commit", "-q", "-m", "runs")
    commit = git(upstream, "rev-parse", "HEAD")
    cache = tmp_path / "cache"
    fetcher = Fetcher(cache, allow_network=True, remote_urls={AGENTDOJO: f"file://{upstream}"}, file_protocol=True)
    fetcher.fetch(Recipe(kind="git", repo=AGENTDOJO, commit=commit, paths=("runs/",)))
    pin = {"role": "2024-06", "part": "2024-06", "primary": True, "kind": "git", "commit": commit, "tree": "runs/",
           "expected_files": len(entries)}
    real = import_._pin
    monkeypatch.setattr(import_, "_pin", lambda profile, args, part: pin if profile.id == "agentdojo-upstream" else real(profile, args, part))
    return {"cache": cache, "commit": commit, "entries": entries, "upstream": upstream}


def _args(seeded: dict[str, Any], corpus: Path) -> tuple[str, ...]:
    return ("import", "agentdojo", "--snapshot", "2024-06", "--fetch", "--allow-network", "--cache-dir", str(seeded["cache"]),
            "--in-process", "--until", "aer", "--corpus", str(corpus))


def test_artefacts_needs_dry_run(cli, tmp_path, seeded):
    run = cli(*_args(seeded, tmp_path / "c"), "--artefacts")
    assert run.code == 2 and "--artefacts goes with --dry-run" in run.err
    assert not (tmp_path / "c.partial").exists()


@needs_git
def test_the_table_is_printed_and_nothing_is_written(cli, tmp_path, seeded, monkeypatch, check_summary):
    scratch = tmp_path / "tmp"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    out = tmp_path / "corpus"
    run = cli(*_args(seeded, out), "--dry-run", "--artefacts", "--json")
    assert run.code == 0, run.err
    summary = run.json()
    check_summary(summary)
    assert summary["dry_run"] is True and summary["counters"]["mapped"] == 4 and summary["counters"]["artefact_scanned"] == 4
    assert "artefact table: 4 execution(s) scanned" in run.err
    assert not (tmp_path / "corpus.partial").exists() and not out.exists()  # the requested corpus is never created
    assert list(scratch.iterdir()) == []  # the private temporary corpus is gone
    assert any("private temporary corpus" in n for n in summary["notices"])


@needs_git
def test_the_table_document_goes_to_stdout_without_json_and_is_stable(cli, tmp_path, seeded):
    first = cli(*_args(seeded, tmp_path / "a"), "--dry-run", "--artefacts")
    second = cli(*_args(seeded, tmp_path / "b"), "--dry-run", "--artefacts")
    assert first.code == 0 and first.out == second.out
    document = json.loads(first.out)
    assert document["format"] == "agentprov-artefact-table/0.1" and document["n_executions"] == 4 and document["rows"]
    assert all({"artefact_id", "executions", "first", "handling", "hits", "proportion"} <= set(r) for r in document["rows"])
    assert all(len(r["first"]) <= 5 and all(ex.startswith("ex_") for ex in r["first"]) for r in document["rows"])


@needs_git
def test_the_counters_match_a_plain_dry_run(cli, tmp_path, seeded):
    plain = cli(*_args(seeded, tmp_path / "a"), "--dry-run", "--json").json()["counters"]
    scanned = cli(*_args(seeded, tmp_path / "b"), "--dry-run", "--artefacts", "--json").json()["counters"]
    assert {k: v for k, v in scanned.items() if not k.startswith("artefact_")} == plain
