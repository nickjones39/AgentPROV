"""The working-corpus writer: guards, files, determinism across worker counts (PQ phase 3; HL H.1.5, H.6.1; K.5.7)."""

from __future__ import annotations

import errno
import hashlib
import json
import os

import pytest

from agentprov.corpus.dedup import source_key
from agentprov.corpus.index import ExecutionEntry, RawRef, StageOutput
from agentprov.corpus.layout import SealedCorpusError
from agentprov.corpus.register import RegisterEntry
from agentprov.corpus import writer as writer_module
from agentprov.corpus.writer import CorpusWriter, CorpusWriterError
from agentprov.envinfo import InterpreterUnpatchedWarning
from agentprov.io.atomic import DestinationExistsError, LockHeldError
from agentprov.io.workers import WorkerPool
from agentprov.raw.members import ContainerSpec, Selection
from agentprov.raw.origins import Origin, OriginError
from raw_support import build_zip

C40 = "c274885610efaaafec38b6d3eb07152ba7ff3f94"
B40 = "4cbf084087345a813c6d93e99aa2d37eec2ca507"
EX = "ex_7uz2oys57hugtsueixylme4fl5"
FILES = ("raw/origins.jsonl", "raw/members.jsonl", "register.jsonl", "executions.jsonl")


def git_origin(name="deposit.zip"):
    return Origin.zenodo("10.5281/zenodo.12528189", name)


def pool_for(writer, **kw):
    return WorkerPool(store_root=writer.store.objects_dir, **kw)


def entry(sha, ex=EX, issues=(), **kw):
    base = dict(
        ex=ex, mode="import", unit="agent_execution", source_id="agentdojo", snapshot_ids=["s1"], source_key=source_key(sha, {"p": ""}),
        raw=[RawRef(sha, "primary", True)], adapter="agentdojo.tracelogger@0.1.0", profile="agentdojo-upstream@1", aer_digest="cd" * 32,
        stages={"raw": "ok", "aer": "ok"}, completeness="unverifiable", execution_observed=True, issues=list(issues),
    )
    base.update(kw)
    return ExecutionEntry(**base)


def test_empty_corpus_writes_four_zero_byte_files(tmp_path):
    with CorpusWriter(tmp_path / "c"):
        pass
    root = tmp_path / "c.partial"
    for rel in FILES:
        assert (root / rel).read_bytes() == b""
    assert (root / "raw" / "objects").is_dir() and not (tmp_path / "c").exists()


def test_a_corpus_without_a_final_swap_leaves_the_working_tree_and_releases_the_lock(tmp_path):
    with CorpusWriter(tmp_path / "c"):
        assert (tmp_path / "c.partial" / ".agentprov.lock").exists()
    assert not (tmp_path / "c.partial" / ".agentprov.lock").exists()


def test_objects_need_an_origin_and_release_mode_refuses_local_origins(tmp_path):
    with CorpusWriter(tmp_path / "c") as w:
        with pytest.raises(OriginError) as exc:
            w.add_object(b"x", None)  # type: ignore[arg-type]
        assert exc.value.code == "raw.origin.missing" and list(w.store.digests()) == []
        put = w.add_object(b"x", Origin.local("/tmp/dev"))
        assert w.origins.count(put.sha256) == 1
    with CorpusWriter(tmp_path / "r", release=True) as w:
        with pytest.raises(OriginError) as exc:
            w.add_object(b"x", Origin.local("/tmp/dev"))
        assert exc.value.code == "raw.origin.local_in_release"
        w.add_object(b"x", git_origin())


def test_add_origin_records_mirrors_of_stored_objects_only(tmp_path):
    with CorpusWriter(tmp_path / "c") as w:
        put = w.add_object(b"x", git_origin("a.zip"))
        assert w.add_origin(put.sha256, Origin.url("https://mirror.example/a.zip", "2026-10-08")) is True
        assert w.origins.count(put.sha256) == 2
        with pytest.raises(CorpusWriterError):
            w.add_origin("0" * 64, git_origin())


def test_guards_run_before_anything_is_created(tmp_path):
    (tmp_path / "exists").mkdir()
    with pytest.raises(DestinationExistsError):
        CorpusWriter(tmp_path / "exists").open()
    (tmp_path / "sealed").mkdir()
    (tmp_path / "sealed" / "corpus.json").write_text('{"sealed": true}')
    with pytest.raises(SealedCorpusError):
        CorpusWriter(tmp_path / "sealed" / "inner").open()
    assert not (tmp_path / "sealed" / "inner.partial").exists()


def test_a_second_writer_on_the_same_tree_is_refused(tmp_path):
    with CorpusWriter(tmp_path / "c"):
        with pytest.raises(LockHeldError):
            CorpusWriter(tmp_path / "c").open()


def test_git_work_tree_is_refused_unless_ignored(tmp_path):
    (tmp_path / "repo" / ".git").mkdir(parents=True)
    with pytest.raises(Exception) as exc:
        CorpusWriter(tmp_path / "repo" / "out").open()
    assert getattr(exc.value, "exit_code", None) == 4
    with CorpusWriter(tmp_path / "repo" / "out2", git_ignored=lambda tree, path: True):
        pass


def test_git_work_tree_refusal_leaves_no_partial_tree_behind(tmp_path):
    # RC-1: the guard ran after mkdir, so a refused open left an empty out.partial/ (and any missing parents) in the tree.
    (tmp_path / "repo" / ".git").mkdir(parents=True)
    with pytest.raises(Exception) as exc:
        CorpusWriter(tmp_path / "repo" / "a" / "b" / "out").open()
    assert getattr(exc.value, "code", None) == "corpus.in_git_work_tree"
    assert sorted(p.name for p in (tmp_path / "repo").iterdir()) == [".git"]


def test_expand_requires_an_origin_for_every_container(tmp_path):
    with CorpusWriter(tmp_path / "c") as w:
        sha = w.store.put(build_zip([("a.json", b"1")]), ext="zip").sha256  # stored behind the writer's back: no origin
        with pytest.raises(CorpusWriterError) as exc:
            w.expand([ContainerSpec(sha, "s1", "d.zip", (Selection(include=("**",)),))], pool_for(w, in_process=True))
        assert exc.value.code == "raw.origin.missing"


def full_run(root, **pool_kwargs):
    """Container with nested and hostile members, member origins, register events, one AER and one index row."""
    inner = build_zip([("header.json", b"{}"), ("samples/a_epoch_1.json", b'{"a":1}')])
    outer = build_zip([("x/one.eval", inner), ("a.json", b"1"), ("../evil", b"e"), ("notes.md", b"n")])
    sel = (Selection(include=("*.json",), nested=("**/*.eval",)), Selection(include=("header.json", "samples/*.json")))
    with CorpusWriter(root) as w:
        put = w.add_object(outer, git_origin(), ext="zip")
        w.add_origin(put.sha256, Origin.url("https://mirror.example/deposit.zip", "2026-10-08"))
        outcome = w.expand([ContainerSpec(put.sha256, "s1", "deposit.zip", sel)], pool_for(w, **pool_kwargs))
        member = next(r for r in outcome.rows if r.label == "a.json")
        w.add_origin(member.sha256, Origin.git("https://github.com/o/r", C40, "runs/a.json", B40))
        w.add_register(RegisterEntry({"ex": EX}, "map.accounting_unverifiable", "info", "map", "sealed", rule="aer.acc@1"))
        w.write_aer(EX, b'{"k":"seal"}\n')
        w.add_execution(entry(member.sha256, issues=["map.accounting_unverifiable"]))
        return w


def snapshot(root):
    base = root.parent / (root.name + ".partial")
    files = {rel: (base / rel).read_bytes() for rel in FILES}
    files["objects"] = sorted(str(p.relative_to(base)) for p in (base / "raw" / "objects").rglob("*") if p.is_file())
    return files


def test_end_to_end_files_and_cross_references(tmp_path):
    full_run(tmp_path / "c", in_process=True)
    base = tmp_path / "c.partial"
    origins = [json.loads(line) for line in (base / "raw/origins.jsonl").read_text().splitlines()]
    members = [json.loads(line) for line in (base / "raw/members.jsonl").read_text().splitlines()]
    register = [json.loads(line) for line in (base / "register.jsonl").read_text().splitlines()]
    index = [json.loads(line) for line in (base / "executions.jsonl").read_text().splitlines()]
    # every selected member has an object and a member origin; every origin names a stored object
    stored = {p.name.split(".")[0] for p in (base / "raw/objects").rglob("*") if p.is_file()}
    assert {o["sha256"][7:] for o in origins} <= stored
    selected = [m for m in members if m["disposition"] == "selected"]
    assert {m["sha256"][7:] for m in selected} <= stored and len(selected) == 4
    assert sum(1 for o in origins if o["origin"]["kind"] == "member") == len(selected)
    assert sorted(r["code"] for r in register) == ["ingest.archive.traversal", "map.accounting_unverifiable"]
    row = index[0]
    assert row["ex"] == EX and row["status"] == "ok" and row["issues"] == ["map.accounting_unverifiable"]  # an info issue does not change status
    assert row["n_origins"] == 2 and row["paths"]["aer"].endswith(f"/{EX}.aer.jsonl")
    assert (base / row["paths"]["aer"]).read_bytes() == b'{"k":"seal"}\n'
    for rel in FILES:
        text = (base / rel).read_bytes()
        assert text.endswith(b"\n") and b"\r" not in text
    # nothing but the documented tree exists: no extraction, no stray files
    assert sorted(os.listdir(base)) == ["aer", "executions.jsonl", "raw", "register.jsonl"]
    assert sorted(os.listdir(base / "raw")) == ["members.jsonl", "objects", "origins.jsonl", "tmp"]
    assert os.listdir(base / "raw" / "tmp") == []


def test_one_and_three_workers_in_process_and_repeat_runs_write_identical_bytes(tmp_path):
    runs = {}
    for name, kwargs in (("w1", dict(workers=1)), ("w3", dict(workers=3)), ("ip", dict(in_process=True)), ("w3b", dict(workers=3, jobs_per_worker=1))):
        full_run(tmp_path / name, **kwargs)
        runs[name] = snapshot(tmp_path / name)
    reference = runs["w1"]
    assert reference["raw/members.jsonl"] and reference["register.jsonl"]
    for name, snap in runs.items():
        assert snap == reference, name


def test_resume_reloads_the_logs_and_a_second_flush_is_identical(tmp_path):
    full_run(tmp_path / "c", in_process=True)
    first = snapshot(tmp_path / "c")
    # a new writer on the same working tree loads what is there; nothing changes
    sha = hashlib.sha256(b"unused").hexdigest()
    with CorpusWriter(tmp_path / "c") as w:
        assert len(w.index) == 1 and len(w.origins) >= 4 and len(w.members) > 0
        assert w.add_object(b"unused", git_origin("u.zip")).sha256 == sha
    after = snapshot(tmp_path / "c")
    assert after["raw/members.jsonl"] == first["raw/members.jsonl"] and after["executions.jsonl"] == first["executions.jsonl"]
    assert after["register.jsonl"] == first["register.jsonl"] and after["raw/origins.jsonl"] != first["raw/origins.jsonl"]


def test_a_flush_that_fails_on_the_validation_files_leaves_no_index_row_without_its_validation_row(tmp_path, monkeypatch):
    # CB-3: executions.jsonl is the resume commit point, so it is written last. Before the fix an ENOSPC on
    # validation/results.jsonl left the index row on disk without its validation row; a resume then skipped the execution
    # and the validation row was lost for good.
    real = writer_module.atomic_write_bytes

    def no_space_for_results(path, data, *args, **kwargs):
        if path.name == "results.jsonl":
            raise OSError(errno.ENOSPC, "No space left on device")
        return real(path, data, *args, **kwargs)

    w = CorpusWriter(tmp_path / "c").open()
    try:
        sha = w.add_object(b"{}", git_origin("p.json"), ext="json").sha256
        w.write_aer(EX, b"x\n")
        digest = w.add_validation(EX, {"checks": {"c1": "pass"}, "verdict": "pass"})
        w.add_execution(entry(sha, validation=StageOutput("ok", digest)))
        monkeypatch.setattr(writer_module, "atomic_write_bytes", no_space_for_results)
        with pytest.raises(OSError):
            w.flush()
    finally:
        w.close()
    monkeypatch.setattr(writer_module, "atomic_write_bytes", real)
    base = tmp_path / "c.partial"
    index_path = base / "executions.jsonl"
    assert not index_path.exists() or EX.encode("ascii") not in index_path.read_bytes()
    with CorpusWriter(tmp_path / "c") as w:  # the resume re-processes the execution: no index row yet
        assert w.has_execution(EX) is None
        w.add_validation(EX, {"checks": {"c1": "pass"}, "verdict": "pass"})
        w.add_execution(entry(sha, validation=StageOutput("ok", digest)))
    index = [json.loads(line) for line in (base / "executions.jsonl").read_text().splitlines()]
    results = {json.loads(line)["ex"] for line in (base / "validation" / "results.jsonl").read_text().splitlines()}
    assert [row["ex"] for row in index] == [EX] and results == {EX}


def test_issue_codes_need_register_entries_and_decide_the_status(tmp_path):
    with CorpusWriter(tmp_path / "c") as w:
        sha = w.add_object(b"{}", git_origin("p.json"), ext="json").sha256
        w.write_aer(EX, b"x\n")
        w.add_execution(entry(sha, issues=["map.incomplete_run"]))
        with pytest.raises(CorpusWriterError) as exc:
            w.flush()
        assert exc.value.code == "corpus.index.issue_unregistered"
        w._pending.clear()
        w.add_register(RegisterEntry({"ex": EX}, "map.incomplete_run", "warning", "map", "sealed"))
        w.add_execution(entry(sha, issues=["map.incomplete_run"]))
        w.flush()
        assert w.index.rows()[0].status == "ok_with_issues"
    with CorpusWriter(tmp_path / "d") as w:
        sha = w.add_object(b"{}", git_origin("p.json"), ext="json").sha256
        w.write_aer(EX, b"x\n")
        w.add_register(RegisterEntry({"ex": EX}, "map.adapter_defect", "error", "map", "failed"))
        w.add_execution(entry(sha, issues=["map.adapter_defect"]))
        w.flush()
        assert w.index.rows()[0].status == "failed"


def test_index_rows_are_checked_against_the_store_and_origins(tmp_path):
    with CorpusWriter(tmp_path / "c") as w:
        w.write_aer(EX, b"x\n")
        w.add_execution(entry("1" * 64))  # primary object not stored
        with pytest.raises(CorpusWriterError):
            w.flush()
        w._pending.clear()
        sha = w.store.put(b"{}").sha256  # stored without an origin
        w.add_execution(entry(sha))
        with pytest.raises(CorpusWriterError) as exc:
            w.flush()
        assert exc.value.code == "raw.origin.missing"
        w._pending.clear()
        w.add_origin(sha, git_origin("p.json"))
        w.add_execution(entry(sha, raw=[RawRef(sha, "supporting", True)]))  # no primary
        with pytest.raises(CorpusWriterError):
            w.flush()
        w._pending.clear()
        w.add_execution(entry(sha))
        w.flush()
        assert len(w.index) == 1


def test_missing_aer_file_is_refused(tmp_path):
    with CorpusWriter(tmp_path / "c") as w:
        sha = w.add_object(b"{}", git_origin("p.json")).sha256
        w.add_execution(entry(sha))
        with pytest.raises(CorpusWriterError) as exc:
            w.flush()
        assert exc.value.code == "corpus.writer.aer_missing"
        w._pending.clear()


def test_a_sealed_tree_stops_a_running_writer_at_flush(tmp_path):
    w = CorpusWriter(tmp_path / "c").open()
    try:
        (tmp_path / "c.partial" / "corpus.json").write_text('{"sealed": true}')
        with pytest.raises(SealedCorpusError):
            w.flush()
    finally:
        w.close()


def test_dev_mode_advisory_is_kept_for_the_manifest_producer_block(tmp_path, monkeypatch):
    monkeypatch.setattr("agentprov.envinfo._running_version", lambda: (3, 14, 6))
    with CorpusWriter(tmp_path / "c") as w:
        put = w.add_object(build_zip([("a.json", b"1")]), git_origin(), ext="zip")
        with pytest.warns(InterpreterUnpatchedWarning):
            w.expand([ContainerSpec(put.sha256, "s1", "d.zip", (Selection(include=("**",)),))], pool_for(w, in_process=True))
        assert w.interpreter_advisory is not None and w.interpreter_advisory.floor == "3.14.8"
    register = [json.loads(line) for line in (tmp_path / "c.partial" / "register.jsonl").read_text().splitlines()]
    assert [(r["code"], r["stage"], r["severity"], r["disposition"]) for r in register] == [("ingest.interpreter.unpatched", "ingest", "warning", "sealed")]


def test_methods_refuse_use_after_close(tmp_path):
    w = CorpusWriter(tmp_path / "c").open()
    w.close()
    with pytest.raises(CorpusWriterError):
        w.add_object(b"x", git_origin())
