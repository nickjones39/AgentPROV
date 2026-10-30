"""Declared nested archives in the ``expand`` stage (ingest-formats-3; D-381 (a), D-382, D-383, D-384).

Raise-only per-pattern limits under fixed ceilings, the selection tree and its digest, streamed members (commit on verify,
``end``/``abort`` frames, no spool left by a crash), depth and ratio bombs, CRC defects at inner levels, chain labels, and
the same outcome in process and in real worker processes. Archives are built here; nothing is read from fixtures.
"""

from __future__ import annotations

import hashlib
import io
import os
import zipfile
from collections.abc import Mapping
from typing import Any

import pytest

from agentprov.adapters.profiles import parse_profile
from agentprov.errors import ProfileError
from agentprov.ingest.limits import (
    KIB,
    MIB,
    NESTED_MAX_DEPTH,
    NESTED_MAX_MEMBER_BYTES,
    NESTED_MAX_RATIO,
    NESTED_RAISE_FIELDS,
    IngestLimits,
    NestedRaises,
    depth_limit,
    nested_raises,
)
from agentprov.io.workers import Job, MemberOutput, WorkerPool
from agentprov.raw.members import (
    ContainerSpec,
    MembersError,
    Nested,
    Selection,
    _parse_outputs,
    expand_containers,
    nested_selection,
)
from agentprov.raw.store import RawObjectStore

SMALL = IngestLimits(max_member_bytes=16 * KIB, ratio_floor_bytes=4 * KIB)
RAISE = NestedRaises(max_member_bytes=IngestLimits().max_member_bytes, max_depth=3)
PAD = b"".join(hashlib.sha256(i.to_bytes(4, "big")).digest() for i in range(12 * 32))  # 12 KiB, incompressible


def _zip(members: Mapping[str, bytes], *, level: int = 0) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        for name, data in members.items():
            info = zipfile.ZipInfo(name, (2026, 6, 10, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data, compresslevel=level)
    return buf.getvalue()


def _inner(tag: bytes = b"x") -> bytes:
    """A nested zip above SMALL's member bound (two 12 KiB pads) with two small leaves."""
    return _zip({"logs/a.json": b'{"a": "' + tag + b'"}', "logs/b.json": b'{"b": 1}', "pad-1.bin": PAD,
                 "pad-2.bin": PAD[::-1]})  # fmt: skip


def _tree(*, depth: int | None = 3, pattern: str = "logs/*.zip") -> Selection:
    leaf = Selection(include=("**/*.json",))
    return Selection(include=("**/*.json",), children=(Nested(pattern, leaf, NestedRaises(
        max_member_bytes=IngestLimits().max_member_bytes, max_depth=depth)),))


@pytest.fixture
def store(tmp_path):
    return RawObjectStore(tmp_path / "raw")


def _expand(store: RawObjectStore, outer: bytes, selection: Selection, *, limits: IngestLimits = SMALL,
            pool: WorkerPool | None = None) -> Any:  # fmt: skip
    sha = store.put(outer, ext="zip").sha256
    pool = pool or WorkerPool(in_process=True, store_root=store.objects_dir, spool_dir=store.tmp_dir)
    return expand_containers(store, [ContainerSpec(sha, "snap", "in.zip", (selection,), prefixed=True)], pool=pool,
                             limits=limits)  # fmt: skip


def _events(out: Any) -> dict[str, str]:
    return {e.path: e.code for e in out.events}


# ------------------------------------------------------------------------------------------------ raises (D-382)
@pytest.mark.parametrize(("name", "ceiling"), [("max_member_bytes", NESTED_MAX_MEMBER_BYTES),
                                               ("max_ratio", NESTED_MAX_RATIO), ("max_depth", NESTED_MAX_DEPTH)])
def test_a_raise_is_accepted_up_to_its_ceiling_and_refused_above_it(name, ceiling):
    assert getattr(nested_raises({name: ceiling - 1}), name) == ceiling - 1
    assert getattr(nested_raises({name: ceiling}), name) == ceiling
    with pytest.raises(ValueError, match="ceiling"):
        nested_raises({name: ceiling + 1})


def test_a_raise_never_lowers_a_global_limit_and_is_typed():
    defaults = IngestLimits()
    for name, below in (("max_member_bytes", defaults.max_member_bytes - 1), ("max_ratio", defaults.max_ratio - 1),
                        ("max_depth", defaults.max_archive_depth - 1)):
        with pytest.raises(ValueError, match="only raises"):
            nested_raises({name: below})
    for bad in ({"max_member_bytes": True}, {"max_depth": 3.0}, {"max_member_bytes": "1"}):
        with pytest.raises(ValueError):
            nested_raises(bad)
    assert nested_raises({"max_ratio": 250.5}).max_ratio == 250.5
    assert NESTED_RAISE_FIELDS == {"max_member_bytes", "max_ratio", "max_depth"}


def test_the_depth_limit_is_bounded_both_ways():
    limits = IngestLimits()
    assert depth_limit(limits, None) == limits.max_archive_depth
    assert depth_limit(limits, 1) == limits.max_archive_depth  # never below the global value
    assert depth_limit(limits, 3) == 3
    assert depth_limit(limits, 99) == NESTED_MAX_DEPTH  # never above the fixed ceiling


# ------------------------------------------------------------------------------------------------ the selection tree
def test_a_selection_without_children_keeps_its_digest():
    plain = Selection(include=("**/*.eval",))
    assert plain.digest() == hashlib.sha256(b'{"include":["**/*.eval"],"nested":[]}').hexdigest()
    assert _tree().digest() != plain.digest() and _tree().children[0].selection.digest() == Selection(
        include=("**/*.json",)).digest()


def test_nested_selection_builds_the_tree_and_refuses_bad_declarations():
    tree = nested_selection(("**/*.eval",), [
        {"id": "outer", "pattern": "logs/*.zip", "max_depth": 3, "note": "x"},
        {"id": "deeper", "under": "outer", "pattern": "run/*.zip"},
    ])
    (child,) = tree.children
    assert child.pattern == "logs/*.zip" and child.raises.max_depth == 3
    assert [c.pattern for c in child.selection.children] == ["run/*.zip"] and child.selection.include == ("**/*.eval",)
    assert [n.digest() for n in tree.nodes()] == [tree.digest(), child.selection.digest(),
                                                  child.selection.children[0].selection.digest()]
    bad = [
        [{"id": "a", "pattern": "x.zip", "limit": 1}],  # unknown key
        [{"pattern": "x.zip"}],  # no id
        [{"id": "a", "pattern": "x.zip"}, {"id": "a", "pattern": "y.zip"}],  # duplicate id
        [{"id": "a", "pattern": "x.zip", "under": "b"}],  # unknown under
        [{"id": "a", "pattern": "x.zip", "under": "b"}, {"id": "b", "pattern": "y.zip", "under": "a"}],  # cycle
        [{"id": "a", "pattern": "*a*b*c.zip"}],  # three '*' in a segment (F-08)
        [{"id": "a", "pattern": "x.zip", "max_member_bytes": NESTED_MAX_MEMBER_BYTES + 1}],  # above the ceiling
        [{"id": "a", "pattern": "x.zip"}, {"id": "b", "pattern": "y.zip", "under": "a"}],  # level 3 without allowance
        [{"id": "a", "pattern": "x.zip", "max_depth": 3}, {"id": "b", "pattern": "y.zip", "under": "a"},
         {"id": "c", "pattern": "z.zip", "under": "b"}],  # level 4: above any allowance
    ]
    for entries in bad:
        with pytest.raises(MembersError):
            nested_selection(("**/*.eval",), entries)


def test_a_profile_declares_nested_archives_in_its_import_table():
    text = (
        '[profile]\nid = "t"\nversion = 1\nformat = "agentprov-source-profile/0.1"\nsource_id = "t"\nfamily = "inspect"\n'
        '[source]\n[licence]\nspdx = "MIT"\n[lineage]\n[import]\ndialect = "inspect.eval"\nmapper = "inspect.eval"\n'
        'include = ["**/*.eval"]\n[[import.nested]]\nid = "z"\npattern = "logs/*.zip"\nmax_depth = 3\n'
    )
    assert parse_profile(text.encode()).data["import"]["nested"][0]["pattern"] == "logs/*.zip"
    for broken in (text.replace("max_depth = 3", "max_depth = 4"), text.replace('id = "z"\n', ""),
                   text.replace("[[import.nested]]\n", "[import.nested]\n")):
        with pytest.raises(ProfileError):
            parse_profile(broken.encode())


# ------------------------------------------------------------------------------------------------ streaming (D-383)
def test_a_declared_nested_zip_is_streamed_stored_and_expanded_with_its_own_selection(store):
    inner = _inner()
    assert len(inner) > SMALL.max_member_bytes
    out = _expand(store, _zip({"logs/run.zip": inner, "top.json": b"{}"}), _tree())
    assert not [e for e in out.events if e.disposition != "sealed"], _events(out)
    assert store.has(hashlib.sha256(inner).hexdigest())
    inner_sha = hashlib.sha256(inner).hexdigest()
    placed = out.placed[inner_sha]
    assert placed.chain == ("logs/run.zip",) and placed.depth == 2 and placed.max_depth == 3
    labels = {(r.container, r.label) for r in out.rows if r.disposition == "selected"}
    assert (inner_sha, "logs/a.json") in labels and (inner_sha, "logs/b.json") in labels
    assert out.nested_members == {(next(iter(out.placed)), "logs/run.zip")}


def test_the_same_outcome_in_process_and_in_worker_processes(tmp_path):
    outer = _zip({"logs/run.zip": _inner(), "logs/two.zip": _inner(b"y"), "top.json": b"{}"})
    results = []
    for name, kwargs in (("a", {"in_process": True}), ("b", {"workers": 2})):
        store = RawObjectStore(tmp_path / name)
        pool = WorkerPool(store_root=store.objects_dir, spool_dir=store.tmp_dir, **kwargs)
        out = _expand(store, outer, _tree(), pool=pool)
        results.append(([r.to_json() for r in out.rows], [(s, o.to_json()) for s, o in out.origins],
                        [(e.path, e.code) for e in out.events], sorted(os.listdir(store.objects_dir))))
    assert results[0] == results[1]


def test_identical_nested_zips_are_expanded_once_and_listed_twice(store):
    inner = _inner()
    out = _expand(store, _zip({"logs/a.zip": inner, "logs/b.zip": inner}), _tree())
    root = next(iter(out.placed))
    assert {r.label for r in out.rows if r.container == root} == {"logs/a.zip", "logs/b.zip"}
    inner_sha = hashlib.sha256(inner).hexdigest()
    assert out.containers.count(inner_sha) == 1 and out.placed[inner_sha].chain == ("logs/a.zip",)


def test_a_crc_defect_in_a_streamed_nested_zip_aborts_it_and_publishes_nothing(store):
    inner = _inner()
    outer = bytearray(_zip({"logs/run.zip": inner, "top.json": b"{}"}))
    at = bytes(outer).index(PAD[100:132])  # level-0 deflate keeps the inner bytes verbatim: still decodable
    outer[at] ^= 0x01
    out = _expand(store, bytes(outer), _tree())
    assert _events(out)["in.zip!/logs/run.zip"] == "ingest.archive.crc"
    assert not store.has(hashlib.sha256(inner).hexdigest())
    assert {r.label for r in out.rows if r.disposition == "selected"} == {"top.json"}
    assert not [p for p in store.tmp_dir.iterdir()]


def test_a_crc_defect_one_level_deeper_rejects_that_member_only(store):
    inner = bytearray(_inner())
    at = bytes(inner).index(b'{"a": "x"}')
    inner[at + 1] ^= 0x01  # inside logs/a.json, stored verbatim by level-0 deflate
    out = _expand(store, _zip({"logs/run.zip": bytes(inner)}), _tree())
    assert _events(out) == {"in.zip!/logs/run.zip!/logs/a.json": "ingest.archive.crc"}
    assert {r.label for r in out.rows if r.disposition == "selected"} == {"logs/run.zip", "logs/b.json"}


def test_a_nested_zip_above_its_raise_or_its_ratio_is_rejected_unread(store):
    big = _zip({"logs/huge.zip": _inner()})
    out = _expand(store, big, Selection(include=("**/*.json",), children=(Nested("logs/*.zip", Selection(),
                  NestedRaises(max_member_bytes=SMALL.max_member_bytes)),)))  # fmt: skip
    assert _events(out) == {"in.zip!/logs/huge.zip": "ingest.archive.size"}
    zeros = _zip({"logs/zeros.zip": _zip({"z.json": b"0" * (2 * MIB)}, level=9)}, level=9)
    out = _expand(RawObjectStore(store.root.parent / "r2"), zeros, _tree(), limits=IngestLimits(ratio_floor_bytes=1024))
    assert _events(out) == {"in.zip!/logs/zeros.zip!/z.json": "ingest.archive.ratio"}  # the leaf, under global limits
    padded = _zip({"logs/pad.zip": _zip({"z.json": b"0" * (2 * MIB)}, level=0)}, level=9)  # the nested zip itself
    out = _expand(RawObjectStore(store.root.parent / "r3"), padded, _tree(), limits=IngestLimits(ratio_floor_bytes=1024))
    assert _events(out) == {"in.zip!/logs/pad.zip": "ingest.archive.ratio"}
    raised = Selection(include=("**/*.json",), children=(Nested("logs/*.zip", Selection(include=("**/*.json",)),
                       NestedRaises(max_ratio=NESTED_MAX_RATIO)),))  # fmt: skip
    out = _expand(RawObjectStore(store.root.parent / "r4"), padded, raised, limits=IngestLimits(ratio_floor_bytes=1024))
    assert _events(out) == {} and "z.json" in {r.label for r in out.rows if r.disposition == "selected"}  # raised


def test_a_depth_bomb_stops_at_the_allowance_and_is_never_opened(store):
    level4 = _zip({"x/deep.json": b"{}"})
    level3 = _zip({"x/l4.zip": level4})
    level2 = _zip({"x/l3.zip": level3})
    leaf = Selection(include=("**/*.json",))
    chain = Selection(include=("**/*.json",), children=(Nested("x/*.zip", leaf, NestedRaises(max_depth=3)),))
    chain = Selection(include=("**/*.json",), children=(Nested("x/*.zip", chain, NestedRaises(max_depth=3)),))
    chain = Selection(include=("**/*.json",), children=(Nested("x/*.zip", chain, NestedRaises(max_depth=3)),))
    out = _expand(store, _zip({"x/l2.zip": level2}), chain, limits=IngestLimits())
    assert _events(out) == {"in.zip!/x/l2.zip!/x/l3.zip!/x/l4.zip": "ingest.archive.depth"}
    assert hashlib.sha256(level4).hexdigest() not in out.containers


def test_a_member_separator_in_a_chain_label_is_refused(store):
    inner = _zip({"logs/a!/b.json": b"{}", "logs/ok.json": b"{}"})
    out = _expand(store, _zip({"logs/run.zip": inner, "c!/top.json": b"{}"}), _tree(), limits=IngestLimits())
    assert _events(out) == {"in.zip!/logs/run.zip!/logs/a!/b.json": "ingest.name.invalid"}
    assert "c!/top.json" in {r.label for r in out.rows if r.disposition == "selected"}  # level 1: unchanged


# ------------------------------------------------------------------------------------------------ protocol (D-383)
def _member(index: int, size: int, data: bytes, *, streamed: bool = True, nested: bool = True) -> MemberOutput:
    header: dict[str, Any] = {"index": index, "label": f"m{index}.zip", "method": 8, "crc32": "00000000", "size": size,
                              "nested": nested}  # fmt: skip
    if streamed:
        header["streamed"] = True
    out = MemberOutput(header)
    out._append(data)
    return out


def test_a_streamed_member_is_closed_by_its_end_or_its_abort():
    (item,) = _parse_outputs([_member(0, 3, b"abc"), {"end": {"index": 0}}])[1]
    assert item.disposition == "selected" and item.output is not None
    (item,) = _parse_outputs([_member(1, 9, b"ab"), {"abort": {"index": 1, "code": "ingest.archive.crc", "reason": "x"}}])[1]
    assert item.disposition == "rejected" and item.code == "ingest.archive.crc" and item.output is None
    bad = [
        [_member(0, 3, b"abc")],  # no closing frame
        [_member(0, 3, b"abc"), {"end": {"index": 1}}],  # another member's end
        [_member(0, 4, b"abc"), {"end": {"index": 0}}],  # short
        [_member(0, 3, b"abc"), {"abort": {"index": 0, "code": "worker.limit.rss", "reason": "x"}}],  # not ingest.*
        [_member(0, 3, b"abc", nested=False), {"end": {"index": 0}}],  # only a nested archive is streamed
        [_member(0, 3, b"abc"), _member(1, 3, b"abc"), {"end": {"index": 1}}],  # a member instead of the closing frame
        [{"end": {"index": 0}}],  # a closing frame with no streamed member
    ]
    for outputs in bad:
        with pytest.raises(MembersError):
            _parse_outputs(outputs)


def test_a_worker_killed_in_the_middle_of_a_streamed_member_leaves_no_spool_and_no_object(store):
    inner = _inner()
    sha = store.put(_zip({"logs/run.zip": inner}), ext="zip").sha256
    pool = WorkerPool(store_root=store.objects_dir, spool_dir=store.tmp_dir, workers=1, test_kinds=True)
    selection = _tree()
    job = Job("1:" + sha, "test.expand_crash", inputs=({"sha256": sha, "role": "container"},), params={
        "limits": SMALL.to_json(), "include": list(selection.include), "nested": [], "depth": 1, "release": False,
        "children": [{"pattern": "logs/*.zip", "max_member_bytes": RAISE.max_member_bytes}], "crash_after_chunks": 1})
    before = sorted(p.name for p in store.objects_dir.rglob("*"))
    (result,) = pool.run([job])
    assert result.error is not None
    result.close()
    assert sorted(p.name for p in store.objects_dir.rglob("*")) == before
    assert not list(store.tmp_dir.iterdir())  # the spool was an unnamed file, closed with the failed job


def test_a_partial_store_temporary_of_a_dead_process_is_swept_when_the_store_opens_again(store):
    from agentprov.io.atomic import tmp_path_for

    stale = tmp_path_for(store.tmp_dir / "half-published-member", pid=999_999)  # a pid that is not alive
    stale.write_bytes(b"part of a member that was never published")
    RawObjectStore(store.root)  # the next run (or a resume) opens the store
    assert not stale.exists()


def test_a_job_holds_at_most_its_spool_budget_of_returned_members_in_memory(store, monkeypatch):
    import agentprov.io.workers as workers

    monkeypatch.setattr(workers, "SPOOL_MEMORY_PER_JOB", 20 * KIB)  # about two of these 12 KiB members
    out = _expand(store, _zip({f"m/{k}.json": PAD[k:] + PAD[:k] for k in range(6)}),
                  Selection(include=("**/*.json",)), pool=WorkerPool(workers=1, store_root=store.objects_dir))
    assert len([r for r in out.rows if r.disposition == "selected"]) == 6
    held = MemberOutput({"size": 1}, spool_max=0)
    held._append(b"x")
    assert held._spool._rolled and held.read_bytes() == b"x"  # spool_max 0: on disk from the first byte
    held.close()


def test_nested_raises_and_profile_wide_limits_are_disjoint():
    # D-387: a nested raise is scoped to a pattern and must never become a profile-wide limit (D-323's allowlist)
    from agentprov.ingest.profile_limits import PROFILE_RAISABLE

    assert not set(PROFILE_RAISABLE) & (NESTED_RAISE_FIELDS | {"max_archive_depth"})
