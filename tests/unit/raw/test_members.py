"""The ``expand`` stage: gate, selection, nested archives, rows, origins, events (AD-12; G.3.1(3), G.3.5; K.5.7(3))."""

from __future__ import annotations

import io
import json
import struct
import zipfile

import pytest

from agentprov.envinfo import InterpreterUnpatchedError, InterpreterUnpatchedWarning
from agentprov.errors import AgentProvError
from agentprov.ingest.limits import IngestLimits
from agentprov.io.workers import JOB_KINDS, WorkerCrashError, WorkerJobError, WorkerLimitError, WorkerPool, preload_job_kinds
from agentprov.raw.members import (
    ContainerSpec,
    MemberLog,
    MemberRow,
    MembersConflictError,
    MembersError,
    Selection,
    _failure_event,
    _member_path,
    decode_members,
    encode_members,
    engine_code_sha256,
    expand_containers,
    expand_fn_digest,
)
from agentprov.raw.store import RawObjectStore
from raw_support import build_zip, symlink_info


@pytest.fixture
def store(tmp_path):
    return RawObjectStore(tmp_path / "raw")


@pytest.fixture
def pool(store):
    return WorkerPool(in_process=True, store_root=store.objects_dir)


def put_container(store, data: bytes) -> str:
    return store.put(data, ext="zip").sha256


def spec_for(sha: str, *selections: Selection, snapshot="snap", path="dep.zip") -> ContainerSpec:
    return ContainerSpec(sha, snapshot, path, selections or (Selection(include=("**",)),))


def by_label(rows):
    return {r.label: r for r in rows if r.label is not None}


def test_selected_members_become_objects_with_member_origins(store, pool):
    zbytes = build_zip([("a.json", b'{"x":1}'), ("dir/b.jsonl", b"{}\n"), ("empty", b"")])
    sha = put_container(store, zbytes)
    out = expand_containers(store, [spec_for(sha)], pool=pool)
    assert out.events == [] and out.containers == [sha] and out.advisory is None
    rows = by_label(out.rows)
    assert [r.label for r in out.rows] == ["a.json", "dir/b.jsonl", "empty"]  # central-directory order
    assert all(r.disposition == "selected" and r.container == sha and r.method == 8 for r in out.rows)
    assert store.read_bytes(rows["a.json"].sha256) == b'{"x":1}'
    assert rows["empty"].size == 0 and store.read_bytes(rows["empty"].sha256) == b""
    assert store.path_for(rows["dir/b.jsonl"].sha256, "jsonl").is_file()  # extension from the label suffix
    origins = {sha_: o for sha_, o in out.origins}
    origin = origins[rows["a.json"].sha256].to_json()
    assert origin == {"kind": "member", "container": sha, "label": "a.json", "method": 8, "crc32": rows["a.json"].crc32, "size": 7}
    assert rows["a.json"].crc32 == f"{zlib_crc(b'{\"x\":1}'):08x}"


def zlib_crc(data: bytes) -> int:
    import zlib

    return zlib.crc32(data)


def test_unselected_members_are_recorded_and_never_decompressed_or_stored(store, pool):
    zbytes = build_zip([("keep.json", b"1"), ("skip.txt", b"2" * 100), ("deep/skip2.bin", b"3")])
    sha = put_container(store, zbytes)
    out = expand_containers(store, [spec_for(sha, Selection(include=("*.json",)))], pool=pool)
    rows = by_label(out.rows)
    assert rows["keep.json"].disposition == "selected"
    for name in ("skip.txt", "deep/skip2.bin"):
        assert rows[name].disposition == "not_selected" and rows[name].sha256 is None and rows[name].size is not None
    assert len(list(store.digests())) == 2  # the container and keep.json only
    assert out.events == []  # not_selected is not a register event


def test_without_a_selection_every_member_is_not_selected(store, pool):
    sha = put_container(store, build_zip([("a.json", b"1")]))
    out = expand_containers(store, [ContainerSpec(sha, "s", "p.zip", ())], pool=pool)
    assert [r.disposition for r in out.rows] == ["not_selected"] and out.origins == []


def test_selection_patterns_use_glob_semantics_over_the_label():
    from agentprov.raw.members import _compile

    rx = _compile(["**/*.eval", "samples/*_epoch_*.json", "header.json", ".hidden", "?.md"])
    ok = ["a.eval", "x/y/a.eval", "samples/s_epoch_1.json", "header.json", ".hidden", "a.md", "dir/.eval"]
    no = ["samples/deep/s_epoch_1.json", "x/header.json", "ab.md", "a.eval.bak", "a.md/x"]
    assert all(rx.match(label) for label in ok), [label for label in ok if not rx.match(label)]
    assert not any(rx.match(label) for label in no), [label for label in no if rx.match(label)]
    assert _compile([]) is None


@pytest.mark.parametrize("bad", ["", "a\\b", "x" * 300, "a\nb"])
def test_invalid_selection_patterns_are_refused(bad):
    with pytest.raises(MembersError):
        Selection(include=(bad,))


def test_selection_digest_ignores_pattern_order_and_duplicates():
    a = Selection(include=("b", "a", "a"), nested=("z",))
    assert a == Selection(include=("a", "b"), nested=("z",)) and a.digest() == Selection(include=("a", "b"), nested=("z",)).digest()
    assert a.digest() != Selection(include=("a", "b")).digest()


def test_nested_archives_expand_with_the_selection_of_their_level(store, pool):
    inner = build_zip([("header.json", b"{}"), ("samples/a_epoch_1.json", b'{"x":1}'), ("junk.bin", b"j")])
    outer = build_zip([("res/one.eval", inner), ("notes.md", b"hi")])
    sha = put_container(store, outer)
    sel1 = Selection(nested=("**/*.eval",))
    sel2 = Selection(include=("header.json", "samples/*_epoch_*.json"))
    out = expand_containers(store, [spec_for(sha, sel1, sel2)], pool=pool)
    inner_sha = next(r.sha256 for r in out.rows if r.label == "res/one.eval")
    assert inner_sha is not None and store.read_bytes(inner_sha) == inner
    assert sorted(out.containers) == sorted([sha, inner_sha])
    inner_rows = {r.label: r for r in out.rows if r.container == inner_sha}
    assert inner_rows["header.json"].disposition == "selected" and inner_rows["junk.bin"].disposition == "not_selected"
    assert {r.fn_digest for r in out.rows if r.container == sha} != {r.fn_digest for r in out.rows if r.container == inner_sha}
    assert next(r for r in out.rows if r.label == "notes.md").disposition == "not_selected"


def test_a_container_beyond_max_archive_depth_is_stored_but_never_opened(store, pool):
    level3 = build_zip([("c.json", b"3")])
    level2 = build_zip([("l3.zip", level3)])
    level1 = build_zip([("l2.zip", level2)])
    sha = put_container(store, level1)
    sel = Selection(include=("*.json",), nested=("*.zip",))
    out = expand_containers(store, [spec_for(sha, sel, sel, sel)], pool=pool)
    l2 = next(r.sha256 for r in out.rows if r.label == "l2.zip")
    l3 = next(r.sha256 for r in out.rows if r.label == "l3.zip")
    assert store.has(l3) and l3 not in out.containers and l2 in out.containers
    assert [(e.code, e.stage, e.disposition, e.path) for e in out.events] == [
        ("ingest.archive.depth", "ingest", "not_imported", "l2.zip!/l3.zip")
    ]
    assert "limit=max_archive_depth:2" in out.events[0].detail and out.events[0].detail.startswith("sha256=" + l3)
    assert not any(r.label == "c.json" for r in out.rows)


def test_identical_nested_bytes_are_expanded_once(store, pool):
    inner = build_zip([("a.json", b"1")])
    sha = put_container(store, build_zip([("x/one.zip", inner), ("y/two.zip", inner)]))
    sel = Selection(nested=("**/*.zip",))
    out = expand_containers(store, [spec_for(sha, sel, Selection(include=("*.json",)))], pool=pool)
    assert sum(1 for r in out.rows if r.label == "a.json") == 1
    assert [r.label for r in out.rows if r.container == sha] == ["x/one.zip", "y/two.zip"]  # both members recorded
    assert len({o[0] for o in out.origins}) == 2  # the inner archive and a.json; two origins for the inner object
    assert sum(1 for s, _ in out.origins if s == out.rows[0].sha256) == 2


def test_two_different_selections_for_one_container_conflict(store, pool):
    inner = build_zip([("a.json", b"1")])
    outer = build_zip([("one.zip", inner)])
    sha = put_container(store, outer)
    sel = Selection(nested=("*.zip",))
    inner_sha = store.put(inner).sha256
    with pytest.raises(MembersConflictError):
        # the inner container is also a root, with another level-1 selection than the one it gets as a nested level-2
        expand_containers(store, [spec_for(sha, sel, Selection(include=("*.json",))), spec_for(inner_sha, Selection(include=("*",)))], pool=pool)


def test_nested_archive_reached_again_with_another_selection_is_a_register_event(store, pool):
    # CB-22: archive content (not the caller) reaches one inner archive at two declared levels (D-382 ``under`` chain);
    # the second reach is an ``expand.conflict`` event for that subject, and the rest of the archive still imports
    from agentprov.corpus.register import RegisterEntry
    from agentprov.raw.members import nested_selection

    x = build_zip([("a.json", b'{"a":1}')])
    y = build_zip([("inner/x.zip", x)])
    sha = put_container(store, build_zip([("x.zip", x), ("y.zip", y), ("ok.json", b"{}")]))
    sel = nested_selection(("*.json",), [{"id": "A", "pattern": "*.zip"},
                                         {"id": "B", "pattern": "inner/*.zip", "under": "A", "max_depth": 3}])
    out = expand_containers(store, [ContainerSpec(sha, "snap", "dep.zip", (sel,), prefixed=True)], pool=pool)
    x_sha = store.put(x).sha256
    conflicts = [e for e in out.events if e.code == "expand.conflict"]
    assert len(conflicts) == 1 and conflicts[0].path == "dep.zip!/y.zip!/inner/x.zip"
    assert RegisterEntry.from_event(conflicts[0]).stage == "expand"  # a valid register entry
    assert out.containers.count(x_sha) == 1 and out.placed[x_sha].chain == ("x.zip",)  # the first expansion stands
    assert {r.label for r in out.rows if r.disposition == "selected" and r.container == sha} >= {"ok.json", "x.zip"}
    assert [r.label for r in out.rows if r.container == x_sha] == ["a.json"]


def test_member_level_defects_reject_that_member_only(store, pool):
    members = [
        ("ok.json", b"1"),
        ("A.json", b"upper"),
        ("a.json", b"lower"),  # case-colliding names: both rejected (G.3.5)
        ("../evil", b"x"),
        (symlink_info("link"), b"target"),
        ("also-ok.json", b"2"),
    ]
    sha = put_container(store, build_zip(members))
    out = expand_containers(store, [spec_for(sha)], pool=pool)
    codes = {(r.label, r.code) for r in out.rows if r.disposition == "rejected"}
    assert codes == {("A.json", "ingest.archive.duplicate"), ("a.json", "ingest.archive.duplicate"),
                     (None, "ingest.archive.traversal"), ("link", "ingest.archive.link")}
    assert {r.label for r in out.rows if r.disposition == "selected"} == {"ok.json", "also-ok.json"}
    assert all(r.sha256 is None for r in out.rows if r.disposition == "rejected")
    paths = sorted(e.path for e in out.events)
    assert paths == sorted(["A.json", "a.json", "#3", "link"])  # a rejected name has no label: its position names it
    assert all(e.code.startswith("ingest.archive.") and e.stage == "ingest" and e.severity == "error" and e.disposition == "not_imported" for e in out.events)


def test_disallowed_method_encrypted_flag_and_ratio_are_rejected_without_decompression(store, pool):
    bomb = b"\x00" * (3 << 20)  # compresses far beyond max_ratio and is above ratio_floor_bytes
    # bz.json uses bzip2 (method 12), outside the allowed {0, 8, 93}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(zipfile.ZipInfo("bz.json", (2020, 1, 1, 0, 0, 0)), b"x" * 100, compress_type=zipfile.ZIP_BZIP2)
        z.writestr(zipfile.ZipInfo("bomb.json", (2020, 1, 1, 0, 0, 0)), bomb, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr(zipfile.ZipInfo("fine.json", (2020, 1, 1, 0, 0, 0)), b"1", compress_type=zipfile.ZIP_DEFLATED)
    sha = put_container(store, buf.getvalue())
    out = expand_containers(store, [spec_for(sha, Selection(include=("fine.json",)))], pool=pool)  # bomb is NOT selected
    rows = by_label(out.rows)
    assert (rows["bz.json"].disposition, rows["bz.json"].code) == ("rejected", "ingest.archive.method")
    assert (rows["bomb.json"].disposition, rows["bomb.json"].code) == ("rejected", "ingest.archive.ratio")  # gate precedes selection
    assert rows["fine.json"].disposition == "selected"
    details = {e.code: e.detail for e in out.events}
    assert "limit=zip_methods:0,8,93" in details["ingest.archive.method"]
    assert f"size={len(bomb)}" in details["ingest.archive.ratio"] and "limit=max_ratio:200" in details["ingest.archive.ratio"]


def test_member_larger_than_max_member_bytes_is_rejected_with_the_effective_limit(store, pool):
    sha = put_container(store, build_zip([("big.json", b"x" * 5000), ("small.json", b"y")]))
    limits = IngestLimits().replace(max_member_bytes=4096)
    out = expand_containers(store, [spec_for(sha)], pool=pool, limits=limits)
    big = by_label(out.rows)["big.json"]
    assert (big.disposition, big.code, big.size) == ("rejected", "ingest.archive.size", 5000)
    assert "size=5000; limit=max_member_bytes:4096" in out.events[0].detail
    assert by_label(out.rows)["small.json"].disposition == "selected"


def test_total_limit_counts_selected_members_only(store, pool):
    sha = put_container(store, build_zip([("a.json", b"x" * 600), ("b.json", b"y" * 600), ("c.txt", b"z" * 600)]))
    limits = IngestLimits().replace(max_total_bytes=1000)
    out = expand_containers(store, [spec_for(sha, Selection(include=("*.json",)))], pool=pool, limits=limits)
    rows = by_label(out.rows)
    assert [rows[k].disposition for k in ("a.json", "b.json", "c.txt")] == ["selected", "rejected", "not_selected"]
    assert "limit=max_total_bytes:1000" in out.events[0].detail


def test_crc_failure_while_reading_rejects_that_member_and_keeps_the_rest(store, pool):
    payload = b"unique-payload-bytes"
    raw = bytearray(build_zip([("good.json", b"1"), ("bad.json", payload)], method=zipfile.ZIP_STORED))
    at = bytes(raw).index(payload)
    raw[at] ^= 0xFF
    sha = put_container(store, bytes(raw))
    out = expand_containers(store, [spec_for(sha)], pool=pool)
    rows = by_label(out.rows)
    assert (rows["bad.json"].disposition, rows["bad.json"].code, rows["bad.json"].sha256) == ("rejected", "ingest.archive.crc", None)
    assert rows["good.json"].disposition == "selected"
    assert [e.code for e in out.events] == ["ingest.archive.crc"]
    assert not store.has(__import__("hashlib").sha256(bytes(raw[at : at + len(payload)])).hexdigest())  # no partial bytes stored


def test_a_lying_zip64_size_beyond_two_to_the_53_does_not_break_the_corpus_encoding(store, pool):
    base = build_zip([("big.json", b"x" * 10), ("ok.json", b"1")], method=zipfile.ZIP_STORED)
    sha = put_container(store, patch_first_cd_size(base, 2**60))
    out = expand_containers(store, [spec_for(sha)], pool=pool)
    rows = by_label(out.rows)
    assert (rows["big.json"].disposition, rows["big.json"].code, rows["big.json"].size) == ("rejected", "ingest.archive.size", None)
    assert rows["ok.json"].disposition == "selected"
    assert MemberLog(out.rows).serialise()  # JCS-encodable: the size is null, not 2**60


def patch_first_cd_size(blob: bytes, size: int) -> bytes:
    """Rewrite the first central-directory record to declare ``size`` through a zip64 extra field."""
    cd = blob.index(b"PK\x01\x02")
    eocd = blob.rindex(b"PK\x05\x06")
    name_len, extra_len, comment_len = struct.unpack_from("<HHH", blob, cd + 28)
    head_len = 46 + name_len + extra_len + comment_len
    record = bytearray(blob[cd : cd + head_len])
    struct.pack_into("<L", record, 24, 0xFFFFFFFF)  # uncompressed size -> read it from the zip64 extra
    extra = struct.pack("<HHQ", 1, 8, size)
    struct.pack_into("<H", record, 30, extra_len + len(extra))
    record[46 + name_len : 46 + name_len + extra_len] = blob[cd + 46 + name_len : cd + 46 + name_len + extra_len] + extra
    grown = len(extra)
    new = bytearray(blob[:cd] + bytes(record) + blob[cd + head_len :])
    new_eocd = eocd + grown
    cd_size = struct.unpack_from("<L", new, new_eocd + 12)[0]
    struct.pack_into("<L", new, new_eocd + 12, cd_size + grown)
    return bytes(new)


def test_structural_defect_rejects_the_whole_container_but_keeps_its_object(store, pool):
    not_zip = store.put(b"this is not an archive", ext="bin").sha256
    gz = store.put(b"\x1f\x8b\x08\x00" + b"\x00" * 20, ext="bin").sha256
    tar = store.put(b"x" * 257 + b"ustar" + b"\x00" * 300, ext="bin").sha256
    out = expand_containers(store, [spec_for(not_zip, path="a"), spec_for(gz, path="b"), spec_for(tar, path="c")], pool=pool)
    assert out.rows == [] and out.containers == []
    assert sorted((e.path, e.code, e.stage, e.disposition) for e in out.events) == [
        ("a", "ingest.archive.format", "ingest", "not_imported"),
        ("b", "ingest.stream.codec", "ingest", "not_imported"),
        ("c", "ingest.archive.format", "ingest", "not_imported"),
    ]
    assert store.has(not_zip) and store.has(gz) and store.has(tar)
    assert all(e.detail.startswith("sha256=") and "size=" in e.detail for e in out.events)


def test_central_directory_and_member_count_limits_are_effective_and_named(store, pool):
    sha = put_container(store, build_zip([(f"m{i}.json", b"1") for i in range(5)]))
    out = expand_containers(store, [spec_for(sha)], pool=pool, limits=IngestLimits().replace(max_members=4))
    assert [e.code for e in out.events] == ["ingest.archive.members"] and "limit=max_members:4" in out.events[0].detail
    out = expand_containers(store, [spec_for(sha)], pool=pool, limits=IngestLimits().replace(max_cd_bytes=64))
    assert [e.code for e in out.events] == ["ingest.archive.cd"] and "limit=max_cd_bytes:64" in out.events[0].detail


def test_trailing_bytes_are_a_warning_finding_not_a_rejection(store, pool):
    sha = put_container(store, build_zip([("a.json", b"1")]) + b"TRAILING")
    out = expand_containers(store, [spec_for(sha)], pool=pool)
    assert [r.disposition for r in out.rows] == ["selected"]
    assert [(e.code, e.severity, e.disposition, e.stage) for e in out.events] == [("ingest.archive.trailing", "warning", "sealed", "ingest")]


def test_missing_container_is_an_expand_event(store, pool):
    out = expand_containers(store, [spec_for("0" * 64)], pool=pool)
    assert [(e.code, e.stage, e.disposition) for e in out.events] == [("expand.container_missing", "expand", "failed")]


def test_pool_must_read_the_same_store(store, tmp_path):
    other = WorkerPool(in_process=True, store_root=tmp_path / "elsewhere")
    with pytest.raises(ValueError):
        expand_containers(store, [], pool=other)
    with pytest.raises(ValueError):
        expand_containers(store, [], pool=WorkerPool(in_process=True))


def test_dev_mode_below_the_floor_warns_and_records_an_event_per_root(store, pool, monkeypatch):
    monkeypatch.setattr("agentprov.envinfo._running_version", lambda: (3, 14, 7))
    sha = put_container(store, build_zip([("a.json", b"1")]))
    with pytest.warns(InterpreterUnpatchedWarning):
        out = expand_containers(store, [spec_for(sha, path="one.zip")], pool=pool)
    assert out.advisory is not None and out.advisory.python_version == "3.14.7"
    event = next(e for e in out.events if e.code == "ingest.interpreter.unpatched")
    assert (event.stage, event.severity, event.disposition, event.path) == ("ingest", "warning", "sealed", "one.zip")
    assert [r.disposition for r in out.rows] == ["selected"]  # dev mode continues


def test_release_mode_below_the_floor_refuses_before_any_object_is_opened(store, monkeypatch):
    monkeypatch.setattr("agentprov.envinfo._running_version", lambda: (3, 14, 7))
    sha = put_container(store, build_zip([("a.json", b"1")]))

    class NeverRun(WorkerPool):
        def run(self, jobs):  # pragma: no cover - must not be reached
            raise AssertionError("no job may be submitted")

    with pytest.raises(InterpreterUnpatchedError) as exc:
        expand_containers(store, [spec_for(sha)], pool=NeverRun(in_process=True, store_root=store.objects_dir), release=True)
    assert exc.value.exit_code == 3


@pytest.mark.parametrize(
    ("error", "code", "stage", "disposition"),
    [
        (WorkerLimitError("rss"), "worker.limit.rss", "expand", "failed"),
        (WorkerLimitError("wall"), "worker.limit.wall", "expand", "failed"),
        (WorkerCrashError("boom"), "expand.failed", "expand", "failed"),
        (WorkerJobError("x", code="worker.input.missing"), "expand.failed", "expand", "failed"),
        (WorkerJobError("x", code="ingest.archive.cd"), "ingest.archive.cd", "ingest", "not_imported"),
        (AgentProvError("x"), "expand.failed", "expand", "failed"),
    ],
)
def test_failed_jobs_map_to_register_events(error, code, stage, disposition):
    event = _failure_event(spec_for("a" * 64), "p", error, IngestLimits(), 10)
    assert (event.code, event.stage, event.disposition, event.severity) == (code, stage, disposition, "error")
    assert event.detail.startswith("sha256=" + "a" * 64) and "size=10" in event.detail and len(event.detail) <= 200


def test_member_path_rule():
    assert _member_path("p.zip", 1, "a/b.json", 4) == "a/b.json"
    assert _member_path("p.zip", 1, None, 4) == "#4"
    assert _member_path("p.zip!/x.eval", 2, "m.json", 0) == "p.zip!/x.eval!/m.json"
    assert _member_path("p.zip!/x.eval", 2, None, 7) == "p.zip!/x.eval!/#7"


def test_expand_job_is_in_the_closed_kind_table_and_resolves():
    assert JOB_KINDS["expand"] == "agentprov.raw.members:job_expand"
    assert callable(preload_job_kinds({"expand": JOB_KINDS["expand"]})["expand"])


def test_function_identity_depends_on_limits_and_selection_only():
    a = expand_fn_digest(IngestLimits(), Selection(include=("**",)))
    assert a == expand_fn_digest(IngestLimits(), Selection(include=("**",))) and len(a) == 64
    assert a != expand_fn_digest(IngestLimits().replace(max_member_bytes=1 << 20), Selection(include=("**",)))
    assert a != expand_fn_digest(IngestLimits(), Selection(include=("*.json",)))
    assert engine_code_sha256() == engine_code_sha256() and len(engine_code_sha256()) == 64


# ---- members.jsonl --------------------------------------------------------------------------------------------


def sel_row(container="1" * 64, label="a", sha="2" * 64, fn="3" * 64) -> MemberRow:
    return MemberRow(container, fn, label, 8, "0000000a", 1, sha, "selected")


def test_row_shape_and_validation():
    row = sel_row()
    assert row.to_json() == {
        "container": "sha256:" + "1" * 64, "crc32": "0000000a", "disposition": "selected", "fn_digest": "sha256:" + "3" * 64,
        "label": "a", "method": 8, "sha256": "sha256:" + "2" * 64, "size": 1,
    }
    rejected = MemberRow("1" * 64, "3" * 64, None, 8, "0000000a", None, None, "rejected", "ingest.archive.traversal")
    assert rejected.to_json()["code"] == "ingest.archive.traversal" and rejected.to_json()["label"] is None
    assert MemberRow.from_json(json.loads(row.line())) == row and MemberRow.from_json(json.loads(rejected.line())) == rejected
    for kwargs in (
        dict(disposition="selected", sha256=None),  # selected needs an object
        dict(disposition="not_selected"),  # not_selected has none
        dict(disposition="rejected", sha256=None),  # rejected needs a code
        dict(code="ingest.archive.crc"),  # only rejected carries a code
        dict(disposition="rejected", sha256=None, code="not.a.code"),
        dict(crc32="DEADBEEF"),
        dict(method=True),
        dict(size=2**53),
        dict(label=""),
        dict(disposition="gone"),
    ):
        with pytest.raises(MembersError):
            MemberRow(**{**dict(container="1" * 64, fn_digest="3" * 64, label="a", method=8, crc32="0000000a", size=1, sha256="2" * 64, disposition="selected"), **kwargs})
    with pytest.raises(MembersError):
        MemberRow.from_json({"container": "x"})


@pytest.mark.parametrize("change", [
    {"disposition": "rejected", "sha256": None, "code": []},
    {"disposition": "rejected", "sha256": None, "code": {"ingest.archive.crc": 1}},
    {"disposition": []},
    {"disposition": {"selected": True}},
])  # fmt: skip
def test_a_member_row_field_of_the_wrong_type_is_members_error_not_type_error(change):
    """Regen item 157 (ultra raw-withhold #10): a closed-vocabulary field holding an array or object (untrusted
    ``raw/members.jsonl``) is ``raw.members.invalid``; it used to raise ``TypeError`` (unhashable) from the frozenset."""
    row = {"container": "sha256:" + "1" * 64, "crc32": "0000000a", "disposition": "selected", "fn_digest": "sha256:" + "3" * 64,
           "label": "a", "method": 8, "sha256": "sha256:" + "2" * 64, "size": 1, **change}
    with pytest.raises(MembersError) as err:
        MemberRow.from_json(row)
    assert err.value.code == "raw.members.invalid"
    with pytest.raises(MembersError):
        decode_members(json.dumps(row).encode() + b"\n")


def test_file_is_sorted_by_container_and_keeps_member_order():
    a = [sel_row("a" * 64, "z"), sel_row("a" * 64, "a")]
    b = [sel_row("1" * 64, "m")]
    data = encode_members(a + b)
    parsed = decode_members(data)
    assert [(r.container[0], r.label) for r in parsed] == [("1", "m"), ("a", "z"), ("a", "a")]
    assert encode_members(b + a) == data
    assert decode_members(b"") == [] and encode_members([]) == b""
    interleaved = a[:1] + b + a[1:]
    with pytest.raises(MembersError):
        decode_members(b"".join(r.line() for r in interleaved))
    with pytest.raises(MembersError):
        decode_members(data.rstrip(b"\n"))


def test_member_log_is_idempotent_and_refuses_a_different_second_expansion(tmp_path):
    log = MemberLog()
    rows = [sel_row("a" * 64, "x"), sel_row("a" * 64, "y")]
    assert log.add_container("a" * 64, rows) is True and log.add_container("a" * 64, rows) is False
    with pytest.raises(MembersConflictError):
        log.add_container("a" * 64, rows[:1])
    with pytest.raises(MembersError):
        log.add_container("b" * 64, rows)
    log.add_container("c" * 64, [sel_row("c" * 64, "m"), MemberRow("c" * 64, "3" * 64, "n", 0, "00000000", 4, None, "not_selected")])
    assert log.counts() == {"containers": 2, "selected": 3, "not_selected": 1} and len(log) == 4
    path = tmp_path / "members.jsonl"
    log.write(path)
    assert MemberLog.load(path).rows() == log.rows() and path.read_bytes() == log.serialise()
