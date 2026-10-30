"""``agentprov purge`` (MN N.2.15; G.9.6; K.15): usage, refusals, confirmation, dry run, tombstones, summary."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

_CORPUS_TESTS = Path(__file__).resolve().parents[1] / "unit" / "corpus"
if str(_CORPUS_TESTS) not in sys.path:
    sys.path.insert(0, str(_CORPUS_TESTS))

import purge_support as ps  # noqa: E402

from agentprov.cli import purge as purge_cmd  # noqa: E402
from agentprov.corpus.purge import decode_tombstones  # noqa: E402
from agentprov.testing import fs_guard  # noqa: E402


@pytest.fixture
def work(tmp_path):
    built = ps.build_working(tmp_path / "c.partial")
    built["final"] = tmp_path / "c"
    return built


def digest_arg(sha: str) -> str:
    return f"sha256:{sha}"


# ------------------------------------------------------------------------------------------------ usage
def test_help_names_the_synopsis(cli):
    run = cli("purge", "--help")
    assert run.code == 0
    for text in ("--reason", "--corpus", "--cache", "--yes", "--dry-run", "sha256:HEX"):
        assert text in run.out


def test_usage_errors_exit_2_and_change_nothing(cli, work, tmp_path):
    ok = digest_arg(work["leak"])
    plain = tmp_path / "plain"
    plain.mkdir()
    with fs_guard.unchanged(work["root"]):
        assert cli("purge", ok, "--corpus", str(work["final"])).code == 2  # no --reason
        assert cli("purge", ok, "--reason", "licence", "--corpus", str(work["final"])).code == 2
        assert cli("purge", ok, "--reason", "secret").code == 2  # neither --corpus nor --cache
        assert cli("purge", ok, "--reason", "secret", "--corpus", str(work["final"]), "--cache").code == 2
        assert cli("purge", work["leak"], "--reason", "secret", "--corpus", str(work["final"]), "--yes").code == 2  # no sha256: prefix
        assert cli("purge", "sha256:abc", "--reason", "secret", "--corpus", str(work["final"]), "--yes").code == 2
        assert cli("purge", ok, "--reason", "secret", "--corpus", str(tmp_path / "absent"), "--yes").code == 2
        # CC-11: a directory that is no corpus is a wrong-type path, like a missing one
        assert cli("purge", ok, "--reason", "secret", "--corpus", str(plain), "--yes").code == 2
        assert cli("purge", ok, "--reason", "secret", "--corpus", str(work["final"]), "--cache-dir", str(tmp_path)).code == 2


def test_an_unknown_object_exits_2(cli, work):
    with fs_guard.unchanged(work["root"]):
        run = cli("purge", digest_arg("ee" * 32), "--reason", "secret", "--corpus", str(work["final"]), "--yes")
    assert run.code == 2 and "no object with this digest" in run.err


# ------------------------------------------------------------------------------------------------ refusals (4)
def test_a_sealed_corpus_is_never_modified(cli, tmp_path):
    sealed = ps.build_working(tmp_path / "s", sealed=True)
    with fs_guard.unchanged(sealed["root"]):
        run = cli("purge", digest_arg(sealed["leak"]), "--reason", "secret", "--corpus", str(sealed["root"]), "--yes", "--json")
    assert run.code == 4 and run.json()["outcome"] == "refused" and "sealed" in run.err.lower()
    dry = cli("purge", digest_arg(sealed["leak"]), "--reason", "secret", "--corpus", str(sealed["root"]), "--dry-run")
    assert dry.code == 4  # a dry run gives the exit code of the real run


def test_non_interactive_without_yes_is_refused(cli, work):
    with fs_guard.unchanged(work["root"]):
        run = cli("purge", digest_arg(work["leak"]), "--reason", "secret", "--corpus", str(work["final"]), "--json")
    assert run.code == 4 and "needs confirmation" in run.err and run.json()["exit_code"] == 4


def test_interactive_confirmation(cli, work, monkeypatch):
    monkeypatch.setattr(purge_cmd, "_interactive", lambda: True)
    args = ("purge", digest_arg(work["leak"]), "--reason", "secret", "--corpus", str(work["final"]))
    monkeypatch.setattr(purge_cmd, "_ask", lambda prompt: "no")
    with fs_guard.unchanged(work["root"]):
        assert cli(*args).code == 4
    asked: list[str] = []
    monkeypatch.setattr(purge_cmd, "_ask", lambda prompt: asked.append(prompt) or work["leak"][:8])
    run = cli(*args)
    assert run.code == 0 and asked and work["leak"][:8] in asked[0]
    assert (work["root"] / "raw" / "tombstones.jsonl").is_file()


# ------------------------------------------------------------------------------------------------ the purge
def test_dry_run_prints_the_plan_and_writes_nothing(cli, work, monkeypatch):
    monkeypatch.setattr(purge_cmd, "_ask", lambda prompt: pytest.fail("a dry run asks nothing"))
    with fs_guard.unchanged(work["root"]):
        run = cli("purge", digest_arg(work["leak"]), "--reason", "secret", "--corpus", str(work["final"]), "--dry-run", "--json")
    assert run.code == 0
    summary = run.json()
    assert summary["dry_run"] is True and summary["counters"] == {"executions_withheld": 1, "objects_removed": 1, "tombstones_written": 1}
    assert "would remove" in run.err and ps.EX_LEAK in run.err and "release.withheld" in run.err
    assert not (work["root"] / ".agentprov.lock").exists()


def test_purge_removes_tombstones_and_withholds(cli, work, check_summary):
    run = cli("purge", digest_arg(work["leak"]), "--reason", "secret", "--corpus", str(work["final"]), "--yes", "--json")
    assert run.code == 0, run.err
    summary = run.json()
    check_summary(summary)
    assert summary["counters"] == {"executions_withheld": 1, "objects_removed": 1, "tombstones_written": 1}
    assert summary["issues_by_code"] == {"release.withheld": 1} and summary["corpus"]["state"] == "working"
    assert summary["corpus"]["corpus_id"] == "tst-corpus"
    rows = decode_tombstones((work["root"] / "raw" / "tombstones.jsonl").read_bytes())
    assert [(r.sha256, r.reason) for r in rows] == [(work["leak"], "secret")]
    assert ps.SENTINEL not in run.out + run.err  # nothing printed holds the value
    assert not list((work["root"] / "raw" / "objects" / work["leak"][:2]).glob(f"{work['leak']}.*"))
    again = cli("purge", digest_arg(work["leak"]), "--reason", "secret", "--corpus", str(work["final"]), "--yes", "--json")
    assert again.code == 0 and again.json()["counters"] == {"executions_withheld": 0, "objects_removed": 0, "tombstones_written": 0}


def test_a_container_purge_lists_the_members_that_stay(cli, work):
    run = cli("purge", digest_arg(work["container"]), "--reason", "personal_data", "--corpus", str(work["final"]), "--yes")
    assert run.code == 0 and f"sha256:{work['member']}" in run.err and "stay stored" in run.err


def test_summary_is_byte_stable(cli, work, tmp_path):
    other = ps.build_working(tmp_path / "d.partial")
    first = cli("purge", digest_arg(work["leak"]), "--reason", "secret", "--corpus", str(work["final"]), "--dry-run", "--json").json()
    second = cli("purge", digest_arg(other["leak"]), "--reason", "secret", "--corpus", str(tmp_path / "d"), "--dry-run", "--json").json()
    for doc in (first, second):
        doc["options"].pop("corpus"), doc["corpus"].pop("root")
    assert first == second


# ------------------------------------------------------------------------------------------------ the fetch cache
def _cache(tmp_path):
    cache = tmp_path / "cache"
    (cache / "hf" / "o--r" / "rev").mkdir(parents=True)
    data = b"downloaded-" + ps.SENTINEL.encode()
    (cache / "hf" / "o--r" / "rev" / "logs.zip").write_bytes(data)
    return cache, hashlib.sha256(data).hexdigest()


def test_cache_purge(cli, tmp_path):
    cache, sha = _cache(tmp_path)
    args = ("purge", digest_arg(sha), "--reason", "secret", "--cache", "--cache-dir", str(cache))
    with fs_guard.unchanged(cache):
        assert cli(*args, "--dry-run").code == 0
        assert cli(*args).code == 4  # not confirmed
    run = cli(*args, "--yes", "--json")
    assert run.code == 0 and run.json()["corpus"] is None
    assert not (cache / "hf" / "o--r" / "rev" / "logs.zip").exists()
    assert [r.sha256 for r in decode_tombstones((cache / "tombstones.jsonl").read_bytes())] == [sha]
    assert cli("purge", digest_arg("ee" * 32), "--reason", "secret", "--cache", "--cache-dir", str(cache), "--yes").code == 2


def test_cache_defaults_to_the_agentprov_home_cache(cli, tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("AGENTPROV_HOME", str(home))
    cache = home / "cache"
    (cache / "url").mkdir(parents=True)
    (cache / "url" / ("ab" * 32)).write_bytes(b"x")
    run = cli("purge", digest_arg("ab" * 32), "--reason", "personal_data", "--cache", "--yes")
    assert run.code == 0 and not (cache / "url" / ("ab" * 32)).exists()


def test_cache_purge_refuses_while_a_fetch_writes_the_cache(cli, tmp_path):
    """CLI robustness item 3 (G6a): the purge takes the fetch cache's write lock; a live writer refuses it."""
    import json
    import platform
    import subprocess

    cache, sha = _cache(tmp_path)
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    try:
        (cache / ".agentprov.lock").write_text(json.dumps(
            {"command": "fetch", "host": platform.node(), "pid": child.pid, "started": "2026-10-14T10:00:00Z"}))
        run = cli("purge", digest_arg(sha), "--reason", "secret", "--cache", "--cache-dir", str(cache), "--yes")
    finally:
        child.kill()
        child.wait()
    assert run.code == 4 and "fetch cache" in run.err and f"pid {child.pid}" in run.err, run.err
    assert (cache / "hf" / "o--r" / "rev" / "logs.zip").exists() and not (cache / "tombstones.jsonl").exists()
