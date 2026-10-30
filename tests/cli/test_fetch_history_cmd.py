"""``agentprov fetch --profile ID --history`` (D.6.16): the blobless full history and the introducing-commit index.

The real network is never reached: the CLI's ``Fetcher`` is replaced by one that fetches from a local synthetic repository
through ``file://`` (the Fetcher's test seam), and the profile lookup by a source table naming it.
"""

from __future__ import annotations

import json
import socket
import sys
from pathlib import Path
from typing import Any

import pytest

_RAW_TESTS = Path(__file__).resolve().parents[1] / "unit" / "raw"
if str(_RAW_TESTS) not in sys.path:
    sys.path.insert(0, str(_RAW_TESTS))

from fetch_support import REPO_URL, needs_git  # noqa: E402
from history_support import make_history  # noqa: E402

from agentprov.cli import fetch as fetch_cmd  # noqa: E402
from agentprov.raw.fetch import Fetcher  # noqa: E402


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_a: object, **_k: object) -> None:
        raise AssertionError("a test tried to use the network")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)


@pytest.fixture
def cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.delenv("AGENTPROV_UPSTREAM_CACHE", raising=False)
    return tmp_path / "cache"


def local_history(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    history = make_history(tmp_path)
    source = {
        "canonical_repo": REPO_URL,
        "pins": [{"role": "head", "kind": "git", "commit": history.head, "tree": "runs/", "primary": True}],
    }
    monkeypatch.setattr(fetch_cmd, "_source_table", lambda profile_id: source)

    def seamed(cache_dir: Path, **kwargs: Any) -> Fetcher:
        return Fetcher(cache_dir, remote_urls={REPO_URL: history.url}, file_protocol=True, **kwargs)

    monkeypatch.setattr(fetch_cmd, "Fetcher", seamed)
    return history


def test_history_is_a_documented_option():
    from agentprov.cli.main import build_parser

    sub = next(a for a in build_parser()._actions if a.__class__.__name__ == "_SubParsersAction")
    assert "--history" in {o for action in sub.choices["fetch"]._actions for o in action.option_strings}


def test_history_goes_with_a_profile_and_not_with_paths(cli, cache):
    assert cli("fetch", "--corpus", ".", "--history", "--dry-run").code == 2
    assert cli("fetch", "--profile", "adprov-v1", "--history", "--path", "runs/", "--dry-run").code == 2


def test_history_without_allow_network_exits_4(cli, cache):
    run = cli("fetch", "--profile", "adprov-v1", "--history", "--cache-dir", str(cache))
    assert run.code == 4 and not cache.exists()


def test_history_dry_run_names_the_blobless_fetch_and_writes_nothing(cli, cache):
    run = cli("fetch", "--profile", "adprov-v1", "--history", "--cache-dir", str(cache), "--dry-run")
    assert run.code == 0 and "would fetch the blobless history" in run.err and not cache.exists()


@needs_git
def test_history_mode_end_to_end_then_cached(cli, tmp_path, cache, monkeypatch, check_summary):
    history = local_history(tmp_path, monkeypatch)
    run = cli("fetch", "--profile", "whatever", "--history", "--allow-network", "--cache-dir", str(cache), "--json")
    assert run.code == 0, run.err
    summary = run.json()
    check_summary(summary)
    assert summary["counters"]["fetched"] == 1 and summary["counters"]["indexed_blobs"] == len(history.expect)
    (row,) = [json.loads(line) for line in (cache / "acquisitions.jsonl").read_text().splitlines()]
    assert row["mode"] == "bare-full-history-blobless" and row["consent"] == "--allow-network"
    again = cli("fetch", "--profile", "whatever", "--history", "--allow-network", "--cache-dir", str(cache), "--json")
    assert again.code == 0 and again.json()["counters"]["cached"] == 1 and again.json()["counters"]["fetched"] == 0
    assert len((cache / "acquisitions.jsonl").read_text().splitlines()) == 1
    plan = cli("fetch", "--profile", "whatever", "--history", "--cache-dir", str(cache), "--dry-run")
    assert plan.code == 0 and "index cached" in plan.err
