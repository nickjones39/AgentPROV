"""SEC-05/07/09: a zip stored as byte parts is one logical zip by declared order and pinned digests (D-243, D-244).

Order never comes from names: the caller declares ``(sha256, size)`` per part. A reordered, truncated or resized part is
refused by the declaration gate or the unchanged zip structure checks, and the container identity (the split descriptor)
changes with any change of order or bytes. Nothing is extracted.
"""

from __future__ import annotations

import hashlib
import io
import os
import zipfile
import zlib
from pathlib import Path

import pytest
from format_support import split, zip_bytes

from agentprov.errors import IngestError
from agentprov.ingest.archives import iter_zip_members, open_split_zip, open_zip
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.parts import PartsView
from agentprov.io.workers import Job, WorkerPool
from agentprov.raw.members import (
    ContainerSpec,
    MembersError,
    Selection,
    decode_split_descriptor,
    expand_containers,
    split_descriptor,
    store_split_descriptor,
)
from agentprov.raw.store import RawObjectStore

LIMITS = IngestLimits()
MEMBERS = [(f"logs/run_{i}.eval", os.urandom(3000) + b"%d" % i) for i in range(12)]
ZIP = zip_bytes(MEMBERS, zipfile.ZIP_STORED)  # stored: member data crosses part boundaries byte for byte
PARTS = split(ZIP, 4096)


def members_of(parts: list[bytes], limits: IngestLimits = LIMITS):
    handles = [io.BytesIO(p) for p in parts]
    with open_split_zip(handles, [len(p) for p in parts], limits, release=False) as z:
        return [(m.label, z.read_member(m)) for m in iter_zip_members(z, None, limits)]


def code_of(parts: list[bytes], sizes: list[int] | None = None, limits: IngestLimits = LIMITS) -> str:
    handles = [io.BytesIO(p) for p in parts]
    with pytest.raises(IngestError) as err:
        z = open_split_zip(handles, sizes or [len(p) for p in parts], limits, release=False)
        [z.read_member(m) for m in iter_zip_members(z, None, limits) if m.disposition == "selected"]
    return err.value.code


# --------------------------------------------------------------------------------------------- the logical zip
def test_the_parts_read_as_the_unsplit_zip_member_for_member():
    assert len(PARTS) > 8
    with open_zip(io.BytesIO(ZIP), LIMITS, release=False) as whole:
        expected = [(m.label, whole.read_member(m)) for m in iter_zip_members(whole, None, LIMITS)]
    assert members_of(PARTS) == expected == MEMBERS


def test_a_member_that_crosses_a_part_boundary_is_crc_checked():
    parts = split(ZIP, 1500)  # every 3 KB member spans several parts (within max_split_parts, D-461)
    assert len(parts) <= LIMITS.max_split_parts
    assert members_of(parts) == MEMBERS


def test_the_view_reads_across_boundaries_and_seeks_like_a_file():
    view = PartsView([io.BytesIO(p) for p in PARTS], [len(p) for p in PARTS])
    assert view.read(len(ZIP) + 10) == ZIP
    view.seek(4090)
    assert view.read(20) == ZIP[4090:4110]
    assert view.seek(-22, io.SEEK_END) == len(ZIP) - 22 and view.read() == ZIP[-22:]
    assert view.read(5) == b""


# ------------------------------------------------------------------------------------------ declaration gate
def test_sec05_parts_out_of_order_never_form_a_valid_zip():
    for order in ([1, 0, *range(2, len(PARTS))], [*range(len(PARTS) - 2), len(PARTS) - 1, len(PARTS) - 2],
                  list(reversed(range(len(PARTS))))):  # fmt: skip
        code = code_of([PARTS[i] for i in order])
        assert code in ("ingest.archive.format", "ingest.archive.cd", "ingest.archive.overlap", "ingest.archive.prefix",
                        "ingest.archive.crc"), code  # fmt: skip


def test_sec05_a_part_left_out_or_repeated_is_refused():
    assert code_of(PARTS[:3] + PARTS[4:]) != "ok"
    assert code_of(PARTS[:4] + PARTS[3:]) != "ok"


@pytest.mark.parametrize(("sizes", "why"), [
    ("short", "a part is shorter than declared"),
    ("long", "a part is longer than declared"),
    ("zero", "an empty part"),
])  # fmt: skip
def test_sizes_must_match_the_declaration(sizes, why):
    declared = [len(p) for p in PARTS]
    if sizes == "short":
        declared[2] += 1
    elif sizes == "long":
        declared[2] -= 1
    else:
        declared[2] = 0
    assert code_of(PARTS, declared) == "ingest.archive.parts", why


def test_part_count_and_logical_size_limits():
    assert code_of([ZIP]) == "ingest.archive.parts"  # one part is not a split archive
    assert code_of(PARTS, limits=LIMITS.replace(max_split_parts=len(PARTS) - 1)) == "ingest.archive.parts"
    assert members_of(PARTS, LIMITS.replace(max_split_parts=len(PARTS))) == MEMBERS
    assert code_of(PARTS, limits=LIMITS.replace(max_split_bytes=len(ZIP) - 1)) == "ingest.archive.parts"
    assert members_of(PARTS, LIMITS.replace(max_split_bytes=len(ZIP))) == MEMBERS


def test_a_prefix_in_the_first_part_is_refused():
    assert code_of([b"MZ" + PARTS[0], *PARTS[1:]]) == "ingest.archive.format"
    assert code_of([ZIP[:4] + b"x" + ZIP[4:4096], *split(ZIP[4096:], 4096)]) in (
        "ingest.archive.format", "ingest.archive.cd", "ingest.archive.prefix")


def test_a_part_that_shrinks_after_the_gate_is_truncated():
    class Shrinking(io.BytesIO):
        def readinto(self, b):  # type: ignore[override]
            return 0

    handles = [io.BytesIO(p) for p in PARTS]
    handles[-1] = Shrinking(PARTS[-1])
    with pytest.raises(IngestError) as err:
        open_split_zip(handles, [len(p) for p in PARTS], LIMITS, release=False)
    assert err.value.code in ("ingest.stream.truncated", "ingest.archive.format")


# --------------------------------------------------------------------------------- identity and the expand stage
def test_the_descriptor_names_order_and_bytes_and_is_canonical():
    parts = [(hashlib.sha256(p).hexdigest(), len(p)) for p in PARTS]
    desc = split_descriptor(parts)
    assert decode_split_descriptor(desc) == tuple(parts)
    swapped = [parts[1], parts[0], *parts[2:]]
    assert hashlib.sha256(split_descriptor(swapped)).digest() != hashlib.sha256(desc).digest()
    with pytest.raises(MembersError):
        decode_split_descriptor(desc.replace(b'{"archive"', b'{ "archive"'))  # not canonical
    with pytest.raises(MembersError):
        split_descriptor(parts[:1])


@pytest.fixture
def workspace(tmp_path: Path):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    return sandbox, RawObjectStore(sandbox / "raw")


def _store_parts(store: RawObjectStore, parts: list[bytes]) -> tuple[str, tuple[tuple[str, int], ...]]:
    declared = tuple((store.put(p, ext="bin").sha256, len(p)) for p in parts)
    return store_split_descriptor(store, declared), declared


def test_expand_reads_a_split_zip_and_records_the_descriptor_as_container(workspace):
    sandbox, store = workspace
    sha, declared = _store_parts(store, PARTS)
    spec = ContainerSpec(sha, "snap", "logs.zip", (Selection(include=("logs/*.eval",)),), parts=declared)
    results = []
    for workers in (1, 3):
        pool = WorkerPool(workers=workers, store_root=store.objects_dir)
        results.append(expand_containers(store, [spec], pool=pool))
    first, second = results
    assert [r.to_json() for r in first.rows] == [r.to_json() for r in second.rows]
    assert first.events == [] and first.containers == [sha]
    assert [(r.label, r.disposition, r.container) for r in first.rows] == [(n, "selected", sha) for n, _ in MEMBERS]
    for row, (_name, data) in zip(first.rows, MEMBERS, strict=True):
        assert row.crc32 == f"{zlib.crc32(data):08x}" and store.read_bytes(row.sha256) == data
        assert row.origin().data["container"] == sha
    assert all(p == "raw" or p.startswith("raw/") for p in (str(q.relative_to(sandbox)) for q in sandbox.rglob("*")))


def test_a_spec_whose_digest_is_not_the_descriptor_of_its_parts_is_refused(workspace):
    _sandbox, store = workspace
    sha, declared = _store_parts(store, PARTS)
    with pytest.raises(MembersError):
        ContainerSpec(sha, "snap", "logs.zip", (Selection(include=("**",)),), parts=(declared[1], declared[0], *declared[2:]))
    with pytest.raises(MembersError):
        ContainerSpec("0" * 64, "snap", "logs.zip", (Selection(include=("**",)),), parts=declared)


def test_a_missing_part_is_an_event_not_a_partial_expansion(workspace):
    _sandbox, store = workspace
    sha, declared = _store_parts(store, PARTS)
    other = RawObjectStore(_sandbox / "raw2")
    for part in PARTS[:-1]:
        other.put(part, ext="bin")
    store_split_descriptor(other, declared)
    spec = ContainerSpec(sha, "snap", "logs.zip", (Selection(include=("**",)),), parts=declared)
    out = expand_containers(other, [spec], pool=WorkerPool(workers=1, store_root=other.objects_dir))
    assert out.rows == [] and [e.code for e in out.events] == ["expand.container_missing"]
    assert "part not in the raw store" in out.events[0].detail


def test_the_worker_refuses_inputs_that_are_not_the_descriptor_parts_in_order(workspace):
    _sandbox, store = workspace
    sha, declared = _store_parts(store, PARTS)
    inputs = [{"sha256": sha, "role": "container"}] + [{"sha256": s, "role": "part"} for s, _ in declared]
    inputs[1], inputs[2] = inputs[2], inputs[1]
    params = {"limits": LIMITS.to_json(), "include": ["**"], "nested": [], "depth": 1, "release": False, "split": True}
    pool = WorkerPool(workers=1, store_root=store.objects_dir)
    (result,) = list(pool.run([Job("1:x", "expand", inputs=tuple(inputs), params=params)]))
    try:
        assert result.error is not None and result.error.code in ("expand.protocol", "worker.job.error")
        assert not result.outputs
    finally:
        result.close()


def test_a_nested_eval_in_a_split_zip_is_expanded_at_level_2(workspace):
    _sandbox, store = workspace
    inner = zip_bytes([("header.json", b"{}"), ("samples/1_epoch_1.json", b'{"id": 1}')])
    outer = zip_bytes([("logs/a.eval", inner), ("README.md", b"r")], zipfile.ZIP_STORED)
    sha, declared = _store_parts(store, split(outer, 300))
    spec = ContainerSpec(sha, "snap", "logs.zip", (Selection(nested=("logs/*.eval",)), Selection(include=("samples/*.json",))),
                         parts=declared)  # fmt: skip
    out = expand_containers(store, [spec], pool=WorkerPool(workers=1, store_root=store.objects_dir))
    level2 = [r for r in out.rows if r.container != sha]
    assert [(r.label, r.disposition) for r in level2] == [("header.json", "not_selected"), ("samples/1_epoch_1.json", "selected")]
    assert out.events == []
