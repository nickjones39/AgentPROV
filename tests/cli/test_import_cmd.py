"""``agentprov import`` (MN N.2.2; N.1.3-N.1.9; N.3; K.15): the product import path through the CLI.

The pinned commits of the real profiles cannot exist in a test cache, so the positive runs seed a temporary fetch cache
with a local repository (the test seam of ``raw.fetch``, no network) and point the profile pin at its commit
(``_pin`` is patched). Everything else (status gate, acquisition, pipeline, corpus files, summary) is the real code.
"""

from __future__ import annotations

import json
import sys
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
    """A fetch cache holding a local commit of the golden native logs under ``runs/``, and the agentdojo pin pointed at it."""
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


def _rows(partial: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in (partial / "executions.jsonl").read_text().splitlines()]


# ------------------------------------------------------------------------------------------------ positive runs
@needs_git
def test_fetch_imports_the_cached_pin_end_to_end(cli, tmp_path, seeded, check_summary):
    out = tmp_path / "corpus"
    run = cli("import", "agentdojo", "--snapshot", "2024-06", "--fetch", "--allow-network", "--cache-dir", str(seeded["cache"]), "--corpus", str(out),
              "--jobs", "2", "--json")
    assert run.code == 0, run.err
    summary = run.json()
    check_summary(summary)
    c = summary["counters"]
    assert (c["seen"], c["mapped"], c["derived"], c["validated"], c["degenerate"], c["failed"]) == (4, 4, 4, 4, 0, 0)
    assert summary["corpus"]["state"] == "working" and summary["corpus"]["corpus_id"] == "agentdojo-upstream"
    assert any("2024-06 (partial)" in n or "2024-06 (supported)" in n for n in summary["notices"])
    partial = tmp_path / "corpus.partial"
    for name in ("corpus.json", "derivation.json", "executions.jsonl", "register.jsonl", "raw/origins.jsonl",
                 "raw/members.jsonl", "validation/results.jsonl", "validation/summary.json"):
        assert (partial / name).is_file(), name
    rows = _rows(partial)
    assert len(rows) == 4 and {r["stages"]["validation"] for r in rows} == {"ok"}
    assert all(r["stages"]["prov"] == {"agentprov-prov/0.1": "ok"} and (partial / r["paths"]["prov"]["agentprov-prov/0.1"]["json"]).is_file()
               for r in rows)
    origins = [json.loads(line)["origin"] for line in (partial / "raw" / "origins.jsonl").read_text().splitlines()]
    assert {(o["kind"], o["commit"]) for o in origins} == {("git", seeded["commit"])}
    derivation = json.loads((partial / "derivation.json").read_text())
    stages = {s["stage"]: s for s in derivation["stages"]}
    assert set(stages) == {"aer", "sem", "prov", "validation"}
    assert stages["prov"]["engine"] == "agentprov@0.1.0" and stages["prov"]["engine_code_sha256"].startswith("sha256:")
    assert all(s["fn_digest"].startswith("sha256:") for s in derivation["stages"])
    manifest = json.loads((partial / "corpus.json").read_text())
    assert manifest["sealed"] is False and manifest["partial"] is False and manifest["counts"]["executions"] == 4


@needs_git
def test_summary_and_tree_are_byte_identical_across_jobs(cli, tmp_path, seeded):
    trees, summaries = [], []
    for jobs in ("1", "3"):
        out = tmp_path / f"c{jobs}"
        run = cli("import", "agentdojo", "--snapshot", "2024-06", "--fetch", "--allow-network", "--cache-dir", str(seeded["cache"]), "--corpus", str(out),
                  "--jobs", jobs, "--json")
        assert run.code == 0
        summary = run.json()
        summary["options"].pop("jobs"), summary["options"].pop("corpus"), summary["corpus"].pop("root")
        summaries.append(summary)
        trees.append(support.tree_bytes(tmp_path / f"c{jobs}.partial"))
    assert summaries[0] == summaries[1] and trees[0] == trees[1]


@needs_git
def test_size_hints_change_no_byte_and_charge_prov_jobs_from_the_previous_version(cli, tmp_path, seeded, monkeypatch):
    """D-554: ``--size-hints`` only sets memory charges. A corpus imported with hints from a previous version is
    byte-identical to one imported without them, and every prov job was charged from a hint, not at the cap."""
    from agentprov.io import workers

    base = ("import", "agentdojo", "--snapshot", "2024-06", "--fetch", "--allow-network", "--cache-dir", str(seeded["cache"]),
            "--jobs", "2")
    assert cli(*base, "--corpus", str(tmp_path / "plain")).code == 0
    charged: list[tuple[str, int]] = []
    real = workers.WorkerPool.__init__

    def recording(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        real(self, *args, **kwargs)
        policy = self.charge
        if policy is not None:
            def spy(job, root):  # type: ignore[no-untyped-def]
                value = policy(job, root)
                charged.append((job.kind, value))
                return value
            self.charge = spy

    monkeypatch.setattr(workers.WorkerPool, "__init__", recording)
    run = cli(*base, "--corpus", str(tmp_path / "hinted"), "--size-hints", str(tmp_path / "plain.partial"))
    assert run.code == 0, run.err
    assert support.tree_bytes(tmp_path / "plain.partial") == support.tree_bytes(tmp_path / "hinted.partial")
    prov = [value for kind, value in charged if kind == "prov"]
    assert prov and all(value < workers.KIND_RSS_BYTES["prov"] for value in prov)  # every prov job found its hint
    assert workers._DEFAULT_CHARGE is None  # cleared after the import


@needs_git
def test_a_second_run_resumes_and_leaves_the_tree_unchanged(cli, tmp_path, seeded):
    args = ("import", "agentdojo", "--snapshot", "2024-06", "--fetch", "--allow-network", "--cache-dir", str(seeded["cache"]), "--corpus", str(tmp_path / "c"),
            "--in-process", "--json")
    assert cli(*args).code == 0
    before = support.tree_bytes(tmp_path / "c.partial")
    again = cli(*args)
    assert again.code == 0 and again.json()["counters"]["skipped_resume"] == 4 and again.json()["counters"]["mapped"] == 0
    assert support.tree_bytes(tmp_path / "c.partial") == before  # K.15(7): idempotent


@needs_git
def test_verify_against_pin_records_the_git_origin_for_an_input_tree(cli, tmp_path, seeded):
    run = cli("import", "agentdojo", "--snapshot", "2024-06", "--input", str(seeded["upstream"]), "--verify-against-pin", "--cache-dir", str(seeded["cache"]),
              "--corpus", str(tmp_path / "c"), "--in-process", "--until", "aer", "--json")
    assert run.code == 0, run.err
    assert run.json()["counters"]["mapped"] == 4
    rows = _rows(tmp_path / "c.partial")
    assert all("prov" not in r["stages"] and "validation" not in r["stages"] for r in rows)  # --until aer
    origins = [json.loads(line)["origin"] for line in (tmp_path / "c.partial" / "raw" / "origins.jsonl").read_text().splitlines()]
    assert {o["kind"] for o in origins} == {"git"}


@needs_git
def test_dry_run_writes_nothing_and_reports_the_real_counters(cli, tmp_path, seeded):
    args = ("import", "agentdojo", "--snapshot", "2024-06", "--fetch", "--allow-network", "--cache-dir", str(seeded["cache"]), "--in-process", "--json")
    dry = cli(*args, "--corpus", str(tmp_path / "dry"), "--dry-run")
    assert dry.code == 0 and dry.json()["dry_run"] is True
    assert not (tmp_path / "dry.partial").exists() and not (tmp_path / "dry").exists()
    real = cli(*args, "--corpus", str(tmp_path / "real"))
    assert dry.json()["counters"] == real.json()["counters"]


@needs_git
def test_limit_and_select_make_a_partial_corpus(cli, tmp_path, seeded):
    run = cli("import", "agentdojo", "--snapshot", "2024-06", "--fetch", "--allow-network", "--cache-dir", str(seeded["cache"]), "--corpus", str(tmp_path / "c"),
              "--in-process", "--until", "aer", "--limit", "1", "--json")
    assert run.code == 0 and run.json()["counters"]["mapped"] == 1
    assert any("partial working corpus" in n for n in run.json()["notices"])
    assert json.loads((tmp_path / "c.partial" / "corpus.json").read_text())["partial"] is True
    sel = cli("import", "agentdojo", "--snapshot", "2024-06", "--fetch", "--allow-network", "--cache-dir", str(seeded["cache"]), "--corpus", str(tmp_path / "s"),
              "--in-process", "--until", "aer", "--select", "suite=no-such-suite", "--json")
    assert sel.code == 0 and sel.json()["counters"]["filtered"] == 4 and sel.json()["counters"]["mapped"] == 0


@needs_git
def test_until_sem_writes_the_sem_files_and_stops_before_prov(cli, tmp_path, seeded):
    run = cli("import", "agentdojo", "--snapshot", "2024-06", "--fetch", "--allow-network", "--cache-dir", str(seeded["cache"]), "--corpus", str(tmp_path / "c"),
              "--in-process", "--until", "sem", "--json")
    counters = run.json()["counters"]
    assert run.code == 0 and counters["annotated"] >= 1 and counters["derived"] == 0
    partial = tmp_path / "c.partial"
    assert sorted(p.name for p in (partial / "sem").iterdir()) == ["agentdojo.suites-2"]
    assert len(list((partial / "sem").rglob("*.sem.jsonl"))) == counters["annotated"]
    assert not (partial / "prov").exists()
    manifest = json.loads((partial / "corpus.json").read_text())
    assert manifest["formats"]["sem"] == "sem/0.1" and manifest["profiles"]["semantics"] == [{"id": "agentdojo.suites", "version": 2}]
    stages = [s["stage"] for s in json.loads((partial / "derivation.json").read_text())["stages"]]
    assert stages == ["aer", "sem"]


# ------------------------------------------------------------------------------------------------ refusals and guards
def test_foobench_is_refused_by_the_status_gate(cli, tmp_path, check_summary):
    run = cli("import", "foobench", "--corpus", str(tmp_path / "c"), "--input", str(tmp_path), "--json")
    assert run.code == 5
    document = run.json()
    check_summary(document)
    assert document["refusal"]["id"] == "foobench" and "no import capability" in document["refusal"]["status"]
    assert "agentprov: cannot import 'foobench'" in run.err
    assert [p.name for p in tmp_path.iterdir()] == []


def test_a_compat_oracle_part_is_refused(cli, tmp_path):
    run = cli("import", "adprov-v1", "--snapshot", "converted-legacy", "--corpus", str(tmp_path / "c"), "--input", str(tmp_path), "--json")
    assert run.code == 5 and "compat_oracle" in run.json()["refusal"]["status"]


def test_unknown_and_unregistered_source_ids(cli, tmp_path):
    assert cli("import", "agentdojox", "--corpus", str(tmp_path / "c"), "--input", str(tmp_path)).code == 2
    assert "did you mean" in cli("import", "agentdojox", "--corpus", str(tmp_path / "c"), "--input", str(tmp_path)).err
    run = cli("import", "midojo", "--corpus", str(tmp_path / "c"), "--input", str(tmp_path), "--json")
    assert run.code == 5 and run.json()["refusal"]["status"] == "not registered in this build"


def test_compat_prov_spec_pipeline_filter_and_unknown_select_key(cli, tmp_path):
    base = ("import", "agentdojo", "--snapshot", "2024-06", "--corpus", str(tmp_path / "c"), "--input", str(tmp_path))
    assert cli(*base, "--prov-spec", "adprov-v2.3-compat").code == 5
    assert cli(*base, "--prov-spec", "nonsense/1").code == 2
    assert cli(*base, "--pipeline", "gpt-4o").code == 5
    assert cli(*base, "--select", "colour=blue").code == 2


def test_an_input_without_a_pin_check_is_refused(cli, tmp_path):
    support.agentdojo_tree(tmp_path / "in", count=1)
    run = cli("import", "agentdojo", "--snapshot", "2024-06", "--corpus", str(tmp_path / "c"), "--input", str(tmp_path / "in"), "--json")
    assert run.code == 4 and "--verify-against-pin" in run.err
    assert not (tmp_path / "c.partial").exists()


def test_verify_against_pin_without_the_listing_needs_the_network(cli, tmp_path):
    support.agentdojo_tree(tmp_path / "in", count=1)
    base = ("import", "agentdojo", "--snapshot", "2024-06", "--corpus", str(tmp_path / "c"), "--input", str(tmp_path / "in"), "--verify-against-pin",
            "--cache-dir", str(tmp_path / "empty-cache"))
    run = cli(*base)
    assert run.code == 4 and "--allow-network" in run.err
    dry = cli(*base, "--dry-run", "--json")
    assert dry.code == 0 and dry.json()["counters"] == {"seen": 0} and "would fetch" in dry.err
    assert not (tmp_path / "c.partial").exists() and not (tmp_path / "empty-cache").exists()


@pytest.mark.parametrize("where", ["sealed", "inside_sealed", "git_work_tree"])
def test_a_dry_run_applies_the_output_tree_guards_of_the_real_run(cli, tmp_path, where):
    """CC-9: the dry run refuses what the real run refuses (N.1.6(5)): an existing final directory, a tree inside a
    sealed corpus (G1), a tree inside a git work tree (G3). Exit 4 in both, and the dry run creates nothing."""
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "a.json").write_text("{}")
    sealed = tmp_path / "sealed"
    sealed.mkdir()
    (sealed / "corpus.json").write_text('{"sealed": true}')
    (tmp_path / "repo" / ".git").mkdir(parents=True)
    corpus = {"sealed": sealed, "inside_sealed": sealed / "sub", "git_work_tree": tmp_path / "repo" / "out"}[where]
    argv = ("import", "adprov-v1", "--input", str(tmp_path / "in"), "--verify-against-pin", "--corpus", str(corpus))
    dry = cli(*argv, "--dry-run")
    assert dry.code == 4
    assert not (corpus.parent / (corpus.name + ".partial")).exists()
    assert cli(*argv).code == 4


def test_a_fetch_cache_inside_a_sealed_corpus_is_refused(cli, tmp_path, monkeypatch):
    """CC-8: ``--cache-dir`` inside a sealed corpus is refused (G1), in a dry run too (N.1.6(5)), before a fetcher exists."""
    import agentprov.raw.fetch as raw_fetch

    def no_fetcher(*args, **kwargs):
        raise AssertionError("a fetcher was built")

    monkeypatch.setattr(raw_fetch, "Fetcher", no_fetcher)
    sealed = tmp_path / "sealed"
    sealed.mkdir()
    (sealed / "corpus.json").write_text('{"sealed": true}')
    for mode in ("--dry-run", "--allow-network"):
        run = cli("import", "agentdojo", "--snapshot", "2024-06", "--fetch", mode, "--cache-dir", str(sealed / "cache"),
                  "--corpus", str(tmp_path / "c"))
        assert run.code == 4 and not (sealed / "cache").exists()


def test_fetch_dry_run_prints_the_plan_without_network_or_writes(cli, tmp_path):
    run = cli("import", "agentdojo-upstream", "--snapshot", "2024-06", "--fetch", "--dry-run", "--cache-dir", str(tmp_path / "cache"), "--corpus",
              str(tmp_path / "c"), "--json")
    assert run.code == 0 and "would fetch" in run.err
    assert any("alias agentdojo-upstream resolves to source agentdojo" in n for n in run.json()["notices"])
    assert sorted(p.name for p in tmp_path.iterdir()) == []


def test_a_listing_pin_that_does_not_match_registers_every_file(cli, tmp_path):
    labels = support.adprov_tree(tmp_path / "in")
    run = cli("import", "adprov-v1", "--input", str(tmp_path / "in"), "--verify-against-pin", "--corpus", str(tmp_path / "c"),
              "--in-process", "--json")
    assert run.code == 1  # 10 golden files are not the 17,664-file release tree the pin's listing digest names
    summary = run.json()
    assert summary["counters"]["registered"] == len(labels) and summary["counters"]["mapped"] == 0
    assert summary["issues_by_code"] == {"raw.origin.blob_mismatch": len(labels)}


def test_the_corpus_may_not_overlap_the_input(cli, tmp_path):
    support.adprov_tree(tmp_path / "in")
    run = cli("import", "adprov-v1", "--input", str(tmp_path / "in"), "--verify-against-pin", "--corpus", str(tmp_path / "in" / "c"))
    assert run.code == 4 and "G2" in run.err


def test_an_archive_input_under_a_git_pin_is_refused(cli, tmp_path):
    (tmp_path / "x.zip").write_bytes(b"PK\x05\x06" + b"\0" * 18)
    run = cli("import", "agentdojo", "--snapshot", "2024-06", "--input", str(tmp_path / "x.zip"), "--verify-against-pin", "--corpus", str(tmp_path / "c"))
    assert run.code == 5 and "deferred" in run.err


# ------------------------------------------------------------------------------------------------ offline --fetch (D-220)
@pytest.fixture
def no_sockets(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """Every attempt to open a network connection fails the test (and is recorded)."""
    import socket

    attempts: list[Any] = []

    def refuse(*args: Any, **kwargs: Any) -> Any:
        attempts.append(args)
        raise AssertionError("a network connection was attempted")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    return attempts


@needs_git
def test_fetch_without_allow_network_imports_a_cached_pin_offline(cli, tmp_path, seeded, no_sockets):
    log = seeded["cache"] / "acquisitions.jsonl"
    before = log.read_bytes() if log.exists() else b""
    run = cli("import", "agentdojo", "--snapshot", "2024-06", "--fetch", "--cache-dir", str(seeded["cache"]),
              "--corpus", str(tmp_path / "c"), "--in-process", "--json")
    assert run.code == 0, run.err
    assert len(_rows(tmp_path / "c.partial")) == len(seeded["entries"])
    assert (log.read_bytes() if log.exists() else b"") == before  # a cache hit writes no acquisitions row
    assert no_sockets == []


@needs_git
def test_fetch_without_allow_network_refuses_a_pin_the_cache_lacks(cli, tmp_path, seeded, monkeypatch, no_sockets):
    from agentprov.cli import import_

    missing = {"role": "2024-06", "part": "2024-06", "primary": True, "kind": "git", "commit": "f" * 40, "tree": "runs/"}
    monkeypatch.setattr(import_, "_pin", lambda profile, args, part: missing)
    run = cli("import", "agentdojo", "--snapshot", "2024-06", "--fetch", "--cache-dir", str(seeded["cache"]),
              "--corpus", str(tmp_path / "c"), "--json")
    assert run.code == 4 and "[raw.fetch.not_cached]" in run.err, run.err
    assert no_sockets == [] and not (tmp_path / "c.partial").exists()


def test_a_fetch_that_used_the_network_is_noted_once_with_its_expectation_problems_once(monkeypatch):
    """CC-10: ``import --fetch`` fetches the pin once. The network notice (N.1.11(1)) is in the summary, and each pin
    expectation problem is listed once (no fetch, no network: a fake fetcher)."""
    import argparse
    from types import SimpleNamespace

    from agentprov.adapters.profiles import load_profile
    from agentprov.adapters.registry import get_source
    from agentprov.cli import import_ as imp
    from agentprov.cli.common import CommandResult, Context

    class FakeFetcher:
        cached, calls = False, 0

        def plan(self, recipe):
            return SimpleNamespace(cached=self.cached, host="github.com")

        def fetch(self, recipe):
            self.calls += 1
            used, self.cached = not self.cached, True
            return SimpleNamespace(problems=("expected 3 files, found 2",), network_used=used, path=None, sha256=None,
                                   bytes=None)

        def git_tree(self, recipe):
            return [], 0

        def history_index(self, recipe):
            return None

    capability = next(c for c in get_source("agentdojo").capabilities if c.import_status)
    profile = load_profile(capability.profile)
    pin = imp._pin(profile, argparse.Namespace(pin=None), capability.part)
    fake = FakeFetcher()
    monkeypatch.setattr(imp, "_fetcher", lambda args, ctx: fake)
    args = argparse.Namespace(fetch=True, dry_run=False, allow_network=True, input=None, cache_dir=None)
    result = CommandResult()
    imp._tree(args, Context(args=args), profile, pin, None, result)
    assert fake.calls == 1
    assert sum("pin expectation" in n for n in result.notices) == 1
    assert sum(n.endswith("(network)") for n in result.notices) == 1


# ------------------------------------------------------------------------------------------------ --sample (D-529)
@needs_git
def test_sample_through_the_cli_records_the_sample_and_refuses_bad_combinations(cli, tmp_path, seeded):
    base = ("import", "agentdojo", "--snapshot", "2024-06", "--fetch", "--cache-dir", str(seeded["cache"]),
            "--in-process", "--until", "aer")
    run = cli(*base, "--corpus", str(tmp_path / "c"), "--sample", "2", "--sample-mode", "random", "--seed", "s", "--json")
    assert run.code == 0, run.err
    assert run.json()["counters"]["mapped"] == 2 and run.json()["counters"]["sampled_out"] == 2
    assert any("--sample was given" in n for n in run.json()["notices"])
    manifest = json.loads((tmp_path / "c.partial" / "corpus.json").read_text())
    assert manifest["selection"]["sample"]["seed"] == "s" and manifest["partial"] is True
    for extra in (("--sample", "2", "--limit", "1"), ("--sample-mode", "first"), ("--seed", "s"),
                  ("--sample", "2", "--sample-mode", "random"), ("--sample", "2", "--seed", "s"),
                  ("--sample", "0"), ("--sample", "2", "--release")):
        assert cli(*base, "--corpus", str(tmp_path / "x"), *extra).code == 2, extra
    spread = cli(*base, "--corpus", str(tmp_path / "y"), "--sample", "2", "--sample-mode", "spread")
    assert spread.code == 5 and "names no stratum" in spread.err

# ------------------------------------------------------------------------------------------------ interruption
@needs_git
@pytest.mark.skipif(not hasattr(__import__("signal"), "SIGHUP"), reason="the host has no SIGHUP")
def test_a_hang_up_flushes_the_index_and_releases_the_lock(cli, tmp_path, seeded, monkeypatch):
    """CLI robustness item 1: SIGHUP mid-import takes the SIGINT path (N.1.10(2)). Before the fix the default action
    killed the process: a stale ``.agentprov.lock`` and no index rows. ``fallback`` stands in for that default, so a
    regression fails here instead of killing the test worker."""
    import signal

    from agentprov.cli.feedback import FeedbackSink

    unhandled: list[int] = []
    previous = signal.signal(signal.SIGHUP, lambda signum, frame: unhandled.append(signum))
    real_emit = FeedbackSink.emit
    seen = {"done": 0}

    def emit(self: FeedbackSink, event: Any) -> None:
        real_emit(self, event)
        if event.kind == "unit_done":
            seen["done"] += 1
            if seen["done"] == 2:
                signal.raise_signal(signal.SIGHUP)

    monkeypatch.setattr(FeedbackSink, "emit", emit)
    args = ("import", "agentdojo", "--snapshot", "2024-06", "--fetch", "--cache-dir", str(seeded["cache"]),
            "--corpus", str(tmp_path / "c"), "--in-process", "--until", "aer", "--progress", "status", "--json")
    try:
        run = cli(*args)
    finally:
        signal.signal(signal.SIGHUP, previous)
    assert unhandled == [] and run.code == 130, run.err
    assert "interrupted (SIGHUP)" in run.json()["notices"]
    partial = tmp_path / "c.partial"
    assert not (partial / ".agentprov.lock").exists()
    assert len(_rows(partial)) == 2
    monkeypatch.setattr(FeedbackSink, "emit", real_emit)
    resumed = cli(*args)
    assert resumed.code == 0 and resumed.json()["counters"]["skipped_resume"] == 2, resumed.err
