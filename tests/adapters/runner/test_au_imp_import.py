"""2026-11-05 review findings of the import pipeline (``AU-IMP-*``; D-1063, regen-batch item 173): each test reproduces
one finding over small synthetic AgentDojo-shaped logs (built here, never read from a source) and pins the fix."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import import_support as support
from fetch_support import _ENV, REPO_URL, Upstream, git, needs_git

from agentprov.adapters.runner.importer import LocalTree, import_source
from agentprov.corpus.writer import CorpusWriter
from agentprov.ingest.limits import IngestLimits


def _log(task: str, *, text: str = "hello") -> dict[str, Any]:
    """A minimal native AgentDojo log (JSON depth 3: object, list of messages, message object)."""
    messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": "do it"},
                {"role": "assistant", "content": text, "tool_calls": None}]
    return {"suite_name": "banking", "pipeline_name": "scripted-fake", "user_task_id": task, "injection_task_id": None,
            "attack_type": None, "injections": {}, "messages": messages, "error": None, "utility": True,
            "security": True, "duration": 1.25, "agentdojo_package_version": "0.1.35", "benchmark_version": "v1.2.2",
            "evaluation_timestamp": "2026-10-07 14:00:12"}


def _label(task: str) -> str:
    return f"runs/scripted-fake/banking/{task}/none/none.json"


def _tree(root: Path, files: dict[str, Any]) -> Path:
    for rel, value in files.items():
        path = root.joinpath(*rel.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value if isinstance(value, bytes) else json.dumps(value).encode())
    return root


def _snapshot(partial: Path) -> dict[str, Any]:
    return json.loads((partial / "corpus.json").read_text())["sources"][0]["snapshots"][0]


# ------------------------------------------------------------------------------------------------ AU-IMP-2
def test_a_lowered_json_depth_limits_the_inputs_not_the_corpus_s_own_aer(tmp_path):
    """Before, _seal re-parsed the sealed AER header (one level deeper than the input) under the user's
    --max-json-depth: every input passed the reader, then the import stopped at the first seal (ingest.json.depth)."""
    root = _tree(tmp_path / "in", {_label(f"user_task_{i}"): _log(f"user_task_{i}") for i in range(2)})
    limits = IngestLimits().replace(max_json_depth=3)
    with CorpusWriter(tmp_path / "c") as corpus:
        report = import_source("agentdojo", LocalTree(root, limits=limits), corpus=corpus, part="2024-06",
                               pin_check=support.vouch(root), in_process=True, limits=limits, until="aer")
    assert report.exit_code == 0 and report.counters["mapped"] == 2 and report.counters["sealed_clean"] + report.counters[
        "sealed_with_issues"] == 2
    snapshot = _snapshot(tmp_path / "c.partial")
    assert snapshot.get("incomplete") is None and snapshot["counts"]["executions"] == 2


def test_the_lowered_depth_still_refuses_a_deeper_input(tmp_path):
    """The input limit keeps governing the reader: an input deeper than --max-json-depth is still refused."""
    deep = _log("user_task_0")
    deep["injections"] = {"a": {"b": {"c": 1}}}  # depth 4
    root = _tree(tmp_path / "in", {_label("user_task_0"): deep, _label("user_task_1"): _log("user_task_1")})
    limits = IngestLimits().replace(max_json_depth=3)
    with CorpusWriter(tmp_path / "c") as corpus:
        report = import_source("agentdojo", LocalTree(root, limits=limits), corpus=corpus, part="2024-06",
                               pin_check=support.vouch(root), in_process=True, limits=limits, until="aer")
    assert report.counters["mapped"] == 2 and report.counters["degenerate"] == 1
    assert "map.unparseable_artefact" in report.issues_by_code


# ------------------------------------------------------------------------------------------------ AU-IMP-3, AU-IMP-4
def _pinned_repo(tmp_path: Path, extra: Any = None, *, indexed: tuple[bytes, bytes] | None = None) -> tuple[Any, Any, Path]:
    """A local upstream whose ``runs/`` tree holds three logs, plus what ``extra(repo)`` adds to the working tree and an
    ``indexed`` ``(raw path, bytes)`` blob added to the index only, fetched into a cache through the test seam of
    ``raw.fetch`` (no network): ``(fetcher, recipe, repo)``."""
    from agentprov.raw.fetch import Recipe

    repo = tmp_path / "upstream"
    repo.mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    _tree(repo, {_label(f"user_task_{i}"): _log(f"user_task_{i}") for i in range(3)})
    if extra is not None:
        extra(repo)
    git(repo, "add", "-A")
    if indexed is not None:
        _index_blob(repo, *indexed)
    git(repo, "commit", "-q", "-m", "c")
    commit = git(repo, "rev-parse", "HEAD")
    recipe = Recipe(kind="git", repo=REPO_URL, commit=commit, paths=("runs/",))
    fetcher = Upstream(repo, commit, commit).fetcher(tmp_path / "cache", allow_network=True)
    fetcher.fetch(recipe)
    return fetcher, recipe, repo


def _index_blob(repo: Path, raw_path: bytes, data: bytes) -> None:
    """Add a blob at a path the index accepts but a file system may not (an undecodable or control-character name)."""
    env = {**os.environ, **_ENV}
    blob = subprocess.run(["git", "-C", str(repo), "hash-object", "-w", "--stdin"], input=data, capture_output=True,
                          check=True, env=env).stdout.strip()
    subprocess.run(["git", "-C", str(repo), "update-index", "--add", "-z", "--index-info"],
                   input=b"100644 " + blob + b"\t" + raw_path + b"\0", check=True, env=env)


def _fetch_import(out: Path, fetcher: Any, recipe: Any) -> Any:
    from agentprov.adapters.runner.importer import GitPinTree

    with CorpusWriter(out / "c") as corpus:
        return import_source("agentdojo", GitPinTree(fetcher, recipe), corpus=corpus, part="2024-06", in_process=True,
                             until="aer")


def _ingest_rows(report: Any) -> list[tuple[str, str, str]]:
    return sorted((r["code"], r["subject"]["path"], r["disposition"]) for r in report.register
                  if r["code"].startswith("ingest."))


@needs_git
def test_a_fetched_name_with_a_control_character_is_one_candidate_s_ingest_name_invalid(tmp_path):
    """Before, the name reached Origin.git and raw.origin.invalid aborted the whole import with nothing stored."""
    bad = "runs/scripted-fake/banking/user_task_7/none/none\x1b[31m.json"
    fetcher, recipe, _repo = _pinned_repo(tmp_path, indexed=(bad.encode(), json.dumps(_log("user_task_7")).encode()))
    report = _fetch_import(tmp_path, fetcher, recipe)
    assert report.exit_code == 0 and report.counters["mapped"] == 3 and report.counters["registered"] == 1
    assert _ingest_rows(report) == [("ingest.name.invalid", bad, "not_imported")]


@needs_git
def test_a_fetched_name_that_is_not_utf8_is_registered_never_dropped(tmp_path):
    """Before, parse_ls_tree skipped the path and GitPinTree discarded the count: no register entry, no notice."""
    fetcher, recipe, _repo = _pinned_repo(tmp_path, indexed=(b"runs/scripted-fake/banking/user_task_7/none/none\xff.json",
                                                             json.dumps(_log("user_task_7")).encode()))
    report = _fetch_import(tmp_path, fetcher, recipe)
    assert report.exit_code == 0 and report.counters["mapped"] == 3
    assert _ingest_rows(report) == [
        ("ingest.name.invalid", "runs/scripted-fake/banking/user_task_7/none/none\\xff.json", "not_imported")]
    assert _snapshot(tmp_path / "c.partial")["counts"]["not_imported"] == 1


def test_parse_ls_tree_named_names_what_parse_ls_tree_counts():
    from agentprov.raw.fetch import parse_ls_tree, parse_ls_tree_named

    oid = "a" * 40
    data = f"100644 blob {oid} 3\tok.json".encode() + b"\0" + f"100644 blob {oid} 3\t".encode() + b"b\xfe.json\0"
    entries, names = parse_ls_tree_named(data)
    assert [e.path for e in entries] == ["ok.json"] and names == ["b\\xfe.json"]
    assert parse_ls_tree(data) == (entries, 1)


@needs_git
def test_a_symlink_in_the_pin_gives_the_same_corpus_by_fetch_and_by_input(tmp_path):
    """Before, --fetch mapped the link's target text as a degenerate execution (exit 1) while --input registered the same
    entry ingest.path.symlink."""
    from agentprov.adapters.runner.importer import PinCheck

    link = "runs/scripted-fake/banking/user_task_5/none/none.json"

    def add_link(repo: Path) -> None:
        (repo / link).parent.mkdir(parents=True)
        os.symlink("../../user_task_0/none/none.json", repo / link)

    fetcher, recipe, repo = _pinned_repo(tmp_path, add_link)
    fetched = _fetch_import(tmp_path / "f", fetcher, recipe)
    entries, _ = fetcher.git_tree(recipe)
    check = PinCheck("blob", {"commit": recipe.commit, "role": "t"}, listing={e.path: e.oid for e in entries if e.is_blob},
                     repo=recipe.repo)
    with CorpusWriter(tmp_path / "i" / "c") as corpus:
        local = import_source("agentdojo", LocalTree(repo), corpus=corpus, part="2024-06", in_process=True,
                              pin_check=check, until="aer")
    for report in (fetched, local):
        assert report.exit_code == 0 and report.counters["mapped"] == 3 and report.counters["degenerate"] == 0
        assert _ingest_rows(report) == [("ingest.path.symlink", link, "not_imported")]
    assert (tmp_path / "f" / "c.partial" / "executions.jsonl").read_bytes() == (
        tmp_path / "i" / "c.partial" / "executions.jsonl").read_bytes()


# ------------------------------------------------------------------------------------------------ AU-IMP-5
def test_a_listing_pin_vouches_only_for_the_bytes_its_check_hashed(tmp_path, monkeypatch):
    """Before, a file changed between PinCheck.prepare's read and the read that stores it (a concurrent writer) was stored
    with the frozen-corpus origin and counted verified."""
    from agentprov.adapters.profiles import load_profile
    from agentprov.adapters.registry import READERS, get_source
    from agentprov.adapters.runner import resolve_factory
    from agentprov.adapters.runner.importer import PinCheck, listing_sha256
    from agentprov.io.canonical import sha256_hex

    root = tmp_path / "in"
    files = {f"m/prov/a/run{i}.transcript.json": json.dumps({"n": i}).encode() for i in range(3)}
    _tree(root, files)
    pin = {"kind": "listing", "role": "release", "commit": "0" * 40, "tree": "corpus/corpus-prov",
           "listing_sha256": listing_sha256((k, sha256_hex(v)) for k, v in files.items()), "expected_files": 3}
    profile = next(c.profile for c in get_source("adprov-v1").capabilities if c.profile)
    reader = resolve_factory(READERS[str(load_profile(profile).data["import"]["dialect"])])()
    check = PinCheck("listing", pin, listing_origin=reader.listing_origin)
    changed = b'{"n": "changed after the listing check"}'
    prepare = PinCheck.prepare

    def prepare_then_change(self: Any, tree: Any, candidates: Any) -> None:
        prepare(self, tree, candidates)
        (root / "m/prov/a/run1.transcript.json").write_bytes(changed)

    monkeypatch.setattr(PinCheck, "prepare", prepare_then_change)
    with CorpusWriter(tmp_path / "c") as corpus:
        report = import_source("adprov-v1", LocalTree(root), corpus=corpus, profile_id=profile, pin_check=check,
                               in_process=True, until="raw")
    assert check.listing_ok and (check.verified, check.unverified) == (2, 1)
    assert [(r["code"], r["subject"]["path"]) for r in report.register] == [
        ("raw.origin.blob_mismatch", "m/prov/a/run1.transcript.json")]
    origins = (tmp_path / "c.partial" / "raw" / "origins.jsonl").read_text()
    assert sha256_hex(changed) not in origins and origins.count("AgentDojo-PROV") == 2


# ------------------------------------------------------------------------------------------------ AU-IMP-6
def test_an_interrupt_does_not_wait_for_the_in_flight_prov_batch(tmp_path, monkeypatch):
    """Before, leaving the executor joined the background prov batch (up to --batch-size PROV derivations) before the
    flush; a second signal in that wait took os._exit(130) with nothing flushed, no incomplete mark and the lock held.
    The prov batch here blocks until the test releases it: the interrupt must reach the caller, with the snapshot marked
    incomplete and the writer closed, while it is still blocked."""
    import threading
    import time

    import pytest

    from agentprov.adapters.runner import importer as imp

    root = _tree(tmp_path / "in", {_label(f"user_task_{i}"): _log(f"user_task_{i}") for i in range(4)})
    release, entered = threading.Event(), threading.Event()
    run_prov, seal = imp._Pipeline.run_prov, imp._Pipeline._seal
    seals = {"n": 0}

    def blocked_prov(self: Any, staged: Any) -> Any:
        entered.set()
        release.wait(60)
        return run_prov(self, staged)

    def interrupting_seal(self: Any, *args: Any, **kwargs: Any) -> Any:
        seals["n"] += 1
        if seals["n"] == 3:  # batch 2 maps while batch 1's prov jobs run
            assert entered.wait(10)
            raise KeyboardInterrupt
        return seal(self, *args, **kwargs)

    monkeypatch.setattr(imp._Pipeline, "run_prov", blocked_prov)
    monkeypatch.setattr(imp._Pipeline, "_seal", interrupting_seal)
    started = time.monotonic()
    try:
        with pytest.raises(KeyboardInterrupt), CorpusWriter(tmp_path / "c") as corpus:
            import_source("agentdojo", LocalTree(root), corpus=corpus, part="2024-06", pin_check=support.vouch(root),
                          in_process=True, batch_size=2)
        assert not release.is_set() and time.monotonic() - started < 30
        assert _snapshot(tmp_path / "c.partial")["incomplete"]["reason"] == "interrupted"
        assert not (tmp_path / "c.partial" / ".agentprov.lock").exists()
    finally:
        release.set()


def test_abort_pool_stops_a_running_batch_as_its_own_join_does():
    import threading

    from agentprov.adapters.runner.importer import _abort_pool

    class _Worker:
        killed = 0

        def hard_kill(self) -> None:
            type(self).killed += 1

    class _Admission:
        woken = 0

        def wake(self) -> None:
            type(self).woken += 1

    pool = type("Pool", (), {})()
    pool._abort, pool._active_lock, pool._active, pool._admission = threading.Event(), threading.Lock(), {_Worker(),
                                                                                                         _Worker()}, _Admission()
    _abort_pool(pool)  # type: ignore[arg-type]
    assert pool._abort.is_set() and _Worker.killed == 2 and _Admission.woken == 1


# ------------------------------------------------------------------------------------------------ AU-IMP-8
def _import(root: Path, out: Path, **kwargs: Any) -> Any:
    with CorpusWriter(out) as corpus:
        return import_source("agentdojo", LocalTree(root), corpus=corpus, part="2024-06", pin_check=support.vouch(root),
                             in_process=True, **kwargs)


def test_retry_failed_never_remaps_a_purged_primary(tmp_path, monkeypatch):
    """Before, --retry-failed discarded the failed row of a purged primary, mapped the object the store refused to write
    back, overwrote its AER with a degenerate one and failed at the final flush (CorpusWriterError corpus.writer.raw),
    leaving an index digest that no longer matched the AER (verify failed)."""
    from agentprov.adapters.runner import importer as imp
    from agentprov.corpus.purge import apply, plan_corpus
    from agentprov.corpus.verify import verify_corpus
    from agentprov.io.canonical import sha256_hex

    files = {_label(f"user_task_{i}"): _log(f"user_task_{i}", text=f"reply {i}") for i in range(3)}
    root = _tree(tmp_path / "in", files)
    prov_result = imp._Pipeline._prov_result

    def flaky(self: Any, unit: Any, result: Any) -> Any:
        if unit.header["task"]["task_id"] == "user_task_1":
            return self._prov_failed(unit, "worker.limit.rss"), None
        return prov_result(self, unit, result)

    monkeypatch.setattr(imp._Pipeline, "_prov_result", flaky)
    _import(root, tmp_path / "c")
    monkeypatch.setattr(imp._Pipeline, "_prov_result", prov_result)
    partial = tmp_path / "c.partial"
    target = sha256_hex((root / _label("user_task_1")).read_bytes())
    apply(plan_corpus(partial, target, "secret"))
    rows = (partial / "executions.jsonl").read_bytes()
    (failed,) = [json.loads(line) for line in rows.splitlines() if json.loads(line)["status"] == "failed"]
    aer = (partial / failed["paths"]["aer"]).read_bytes()

    report = _import(root, tmp_path / "c", retry_failed=True)
    assert report.exit_code == 0 and report.counters["mapped"] == 0 and report.counters["skipped_resume"] == 3
    assert (partial / "executions.jsonl").read_bytes() == rows and (partial / failed["paths"]["aer"]).read_bytes() == aer
    assert _snapshot(partial).get("incomplete") is None
    assert not verify_corpus(partial, level="chain", in_process=True).failures


def test_a_purged_file_no_execution_holds_is_withheld_never_stored_again(tmp_path):
    """A candidate whose bytes are tombstoned and that no execution of the corpus holds (stored by an earlier run that
    never indexed it, then purged) is registered release.withheld; nothing of it is stored, recorded or mapped."""
    from agentprov.corpus.purge import Tombstone, encode_tombstones
    from agentprov.io.canonical import sha256_hex

    files = {_label(f"user_task_{i}"): _log(f"user_task_{i}") for i in range(3)}
    root = _tree(tmp_path / "in", files)
    target = sha256_hex((root / _label("user_task_2")).read_bytes())
    with CorpusWriter(tmp_path / "c"):
        pass
    tombstones = tmp_path / "c.partial" / "raw" / "tombstones.jsonl"
    tombstones.parent.mkdir(parents=True, exist_ok=True)
    tombstones.write_bytes(encode_tombstones([Tombstone(target, "secret", "2026-11-05")]))
    report = _import(root, tmp_path / "c", until="aer")
    assert report.exit_code == 0 and report.counters["mapped"] == 2 and report.counters["registered"] == 1
    assert [(r["code"], r["subject"]["path"], r["disposition"]) for r in report.register
            if not r["code"].startswith("map.")] == [("release.withheld", _label("user_task_2"), "withheld")]
    assert target not in (tmp_path / "c.partial" / "raw" / "origins.jsonl").read_text()


# ------------------------------------------------------------------------------------------------ AU-IMP-9
def test_an_archive_member_over_the_file_limit_is_one_candidate_s_ingest_size_file(tmp_path):
    """Before, expand stored a member admitted under max_member_bytes, then _store stored it again under the smaller
    --max-file-bytes and the store's IngestError aborted the whole import (and every rerun) at that member."""
    import hashlib
    import io
    import zipfile

    from agentprov.adapters.profiles import load_profile
    from agentprov.adapters.runner.importer import ArchiveTree

    pin = dict(load_profile("dca-agentdojo").data["source"]["pins"][0])
    top = "DCA_AgentDojo_artifact_v1_20260612/results/logs/m/run/pipe/banking"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{top}/user_task_0/none/none.json", json.dumps(_log("user_task_0")))
        # 120 kB of hex text: deflated to about half (the ratio gate passes), over the 100 kB file limit when stored
        archive.writestr(f"{top}/user_task_1/none/none.json", json.dumps(_log("user_task_1", text=os.urandom(60_000).hex())))
    data = buffer.getvalue()
    (tmp_path / pin["file"]).write_bytes(data)
    pin.update(sha256=hashlib.sha256(data).hexdigest(), size=len(data))
    limits = IngestLimits().replace(max_artefact_bytes=100_000)
    assert len(data) < limits.max_artefact_bytes
    tree = ArchiveTree(tmp_path / pin["file"], pin=pin, sha256=pin["sha256"], size=len(data), limits=limits)
    with CorpusWriter(tmp_path / "c", limits=limits) as writer:  # the CLI gives the writer the same limits
        report = import_source("dca-agentdojo", tree, corpus=writer, profile_id="dca-agentdojo", part="v1", pin=pin,
                               in_process=True, limits=limits, until="aer")
    assert report.counters["seen"] == 2 and report.counters["mapped"] == 1 and report.counters["registered"] == 1
    assert [(r["code"], r["disposition"], r["subject"]["path"].rsplit("/", 3)[-3]) for r in report.register
            if r["code"].startswith("ingest.")] == [("ingest.size.file", "not_imported", "user_task_1")]
    assert _snapshot(tmp_path / "c.partial").get("incomplete") is None
