"""``expand`` output is byte-identical across worker counts, isolation modes and runs (G.4.8; K RPR-6, RPR-8; invariant 4)."""

from __future__ import annotations

import os
import zipfile

import pytest

from agentprov.io.workers import WorkerPool
from agentprov.ingest.limits import IngestLimits
from agentprov.raw.members import ContainerSpec, MemberLog, Selection, expand_containers
from agentprov.raw.origins import OriginLog
from agentprov.raw.store import RawObjectStore
from raw_support import build_zip, symlink_info

SEL = (Selection(include=("*.json", "samples/*_epoch_*.json"), nested=("**/*.eval", "*.zip")), Selection(include=("header.json", "samples/*.json")))


def corpus_inputs() -> list[tuple[str, bytes]]:
    """Several containers: nested, rejected members, a not-an-archive, shared nested bytes."""
    inner = build_zip([("header.json", b"{}"), ("samples/a_epoch_1.json", b'{"a":1}'), ("junk.bin", b"j")])
    inner2 = build_zip([("header.json", b'{"two":2}'), ("samples/b_epoch_1.json", b"[]")])
    zs = [
        ("c0.zip", build_zip([("x/one.eval", inner), ("y/two.eval", inner2), ("notes.md", b"n"), ("a.json", b"1")])),
        ("c1.zip", build_zip([("x/dup.eval", inner), ("../evil.json", b"e"), ("A.json", b"u"), ("a.json", b"l")])),
        ("c2.zip", build_zip([(symlink_info("lnk.json"), b"t"), ("ok.json", b"o"), ("big.json", b"B" * 5000)])),
        ("c3.zip", build_zip([(f"m{i:02d}.json", bytes([i]) * (i + 1)) for i in range(12)])),
        ("c4.zip", build_zip([("a.json", b"1")], method=zipfile.ZIP_STORED) + b"TRAIL"),
        ("c5.bin", b"definitely not an archive"),
    ]
    return zs


def run(tmp_path, name: str, **pool_kwargs):
    store = RawObjectStore(tmp_path / name / "raw")
    pool = WorkerPool(store_root=store.objects_dir, **pool_kwargs)
    specs = []
    for label, data in corpus_inputs():
        specs.append(ContainerSpec(store.put(data, ext="zip").sha256, "snap", label, SEL))
    limits = IngestLimits().replace(max_member_bytes=4096)
    outcome = expand_containers(store, list(reversed(specs)), pool=pool, limits=limits)  # submission order must not matter
    objects = sorted(str(p.relative_to(store.root)) for p in store.objects_dir.rglob("*") if p.is_file())
    origins = OriginLog()
    for sha, origin in outcome.origins:
        origins.add(sha, origin)
    events = sorted((e.snapshot_id, e.path, e.code, e.stage, e.severity, e.disposition, e.detail) for e in outcome.events)
    return MemberLog(outcome.rows).serialise(), origins.serialise(), events, objects, sorted(outcome.containers)


def test_the_corpus_input_exercises_nesting_rejections_and_findings(tmp_path):
    members, _origins, events, objects, containers = run(tmp_path, "probe", in_process=True)
    codes = {e[2] for e in events}
    assert {"ingest.archive.traversal", "ingest.archive.duplicate", "ingest.archive.link", "ingest.archive.size",
            "ingest.archive.trailing", "ingest.archive.format"} <= codes
    assert len(containers) >= 6 and len(objects) >= 15 and members.count(b"\n") >= 25


@pytest.mark.parametrize("workers", [1, 3])
def test_worker_runs_match_the_in_process_run_byte_for_byte(tmp_path, workers):
    assert run(tmp_path, f"w{workers}", workers=workers) == run(tmp_path, f"ip{workers}", in_process=True)


def test_one_and_three_workers_and_repeated_runs_are_identical(tmp_path):
    first = run(tmp_path, "a", workers=1)
    assert first == run(tmp_path, "b", workers=3)
    assert first == run(tmp_path, "c", workers=3, jobs_per_worker=1)  # a fresh process (fresh hash seed) for every job
    assert first == run(tmp_path, "d", workers=2)


def test_the_worker_run_leaves_nothing_but_store_objects_on_disk(tmp_path):
    run(tmp_path, "only", workers=2)
    found = sorted(str(p.relative_to(tmp_path / "only")) for p in (tmp_path / "only").rglob("*") if p.is_file())
    assert found and all(f.startswith(os.path.join("raw", "objects") + os.sep) for f in found)
