"""``agentprov.corpus.purge`` (MN N.2.15; G.9.6; HL H.1.2, H.6.3; D-46): tombstones, register entries, planning, idempotence."""

from __future__ import annotations

import os
import stat

import pytest
import purge_support as ps

from agentprov.corpus import purge
from agentprov.corpus.layout import SealedCorpusError
from agentprov.corpus.register import decode_register
from agentprov.testing import fs_guard

DAY = "2026-10-11"


def _today() -> str:
    return DAY


# ------------------------------------------------------------------------------------------------ tombstones
def test_tombstone_rows_are_sorted_canonical_and_round_trip():
    rows = [purge.Tombstone("bb" * 32, "secret", DAY), purge.Tombstone("aa" * 32, "personal_data", DAY)]
    data = purge.encode_tombstones(rows)
    assert data.splitlines()[0].startswith(b'{"date":"2026-10-11","reason":"personal_data","sha256":"sha256:aaaa')
    assert purge.decode_tombstones(data) == sorted(rows, key=lambda r: r.sha256)
    assert purge.encode_tombstones([rows[0], purge.Tombstone("bb" * 32, "personal_data", "2026-01-01")]) == purge.encode_tombstones([rows[0]])  # first wins


@pytest.mark.parametrize(
    "bad",
    [b'{"sha256":"sha256:' + b"aa" * 32 + b'","reason":"secret"}\n',  # missing date
     b'{"date":"2026-13-01","reason":"secret","sha256":"sha256:' + b"aa" * 32 + b'"}\n',
     b'{"date":"2026-10-11","reason":"licence","sha256":"sha256:' + b"aa" * 32 + b'"}\n',
     b'{"date":"2026-10-11","reason":"secret","sha256":"' + b"aa" * 32 + b'"}\n',
     purge.encode_tombstones([purge.Tombstone("bb" * 32, "secret", DAY), purge.Tombstone("aa" * 32, "secret", DAY)])[::-1]],
)
def test_malformed_tombstone_files_are_refused(bad):
    with pytest.raises(purge.PurgeError):
        purge.decode_tombstones(bad)


def test_digest_syntax():
    assert purge.parse_digest("sha256:" + "ab" * 32) == "ab" * 32
    for bad in ("ab" * 32, "sha256:" + "AB" * 32, "sha256:abc", "md5:" + "ab" * 16):
        with pytest.raises(purge.UsageError) as exc:
            purge.parse_digest(bad)
        assert exc.value.exit_code == 2


# ------------------------------------------------------------------------------------------------ corpus
def test_resolution_follows_n15(tmp_path):
    ps.build_working(tmp_path / "c.partial")
    assert purge.resolve_working_corpus(tmp_path / "c") == tmp_path / "c.partial"
    assert purge.resolve_working_corpus(tmp_path / "c.partial") == tmp_path / "c.partial"
    with pytest.raises(purge.UsageError):
        purge.resolve_working_corpus(tmp_path / "absent")
    ps.build_working(tmp_path / "s", sealed=True)
    with pytest.raises(SealedCorpusError) as exc:
        purge.resolve_working_corpus(tmp_path / "s")
    assert exc.value.exit_code == 4
    (tmp_path / "plain").mkdir()
    with pytest.raises(purge.PurgeError):
        purge.resolve_working_corpus(tmp_path / "plain")  # not sealed, no .partial beside it


def test_plan_reads_only_and_names_the_citing_executions(tmp_path):
    c = ps.build_working(tmp_path / "c.partial")
    with fs_guard.unchanged(c["root"]):
        plan = purge.plan_corpus(c["root"], c["leak"], "secret", today=_today)
    assert plan.affected == (ps.EX_LEAK,) and plan.new_register_entries == 1
    assert plan.object_label == f"objects/{c['leak'][:2]}/{c['leak']}.json" and plan.size and plan.date == DAY
    assert not plan.already_tombstoned and plan.member_objects == () and plan.container_objects == ()


def test_unknown_object_and_bad_reason(tmp_path):
    c = ps.build_working(tmp_path / "c.partial")
    with pytest.raises(purge.UnknownObjectError) as exc:
        purge.plan_corpus(c["root"], "ee" * 32, "secret")
    assert exc.value.exit_code == 2
    with pytest.raises(purge.UsageError):
        purge.plan_corpus(c["root"], c["leak"], "licence")


def test_apply_removes_the_object_and_writes_tombstone_and_register(tmp_path):
    c = ps.build_working(tmp_path / "c.partial")
    plan = purge.plan_corpus(c["root"], c["leak"], "secret", today=_today)
    result = purge.apply(plan)
    assert result.removed and result.tombstone_written and result.register_entries_written == 1
    assert not list(c["root"].joinpath("raw", "objects", c["leak"][:2]).glob(f"{c['leak']}.*"))
    assert (c["root"] / "raw" / "objects" / c["other"][:2]).is_dir()
    tombstones = (c["root"] / "raw" / "tombstones.jsonl").read_bytes()
    assert tombstones == (b'{"date":"2026-10-11","reason":"secret","sha256":"sha256:' + c["leak"].encode() + b'"}\n')
    entries = decode_register((c["root"] / "register.jsonl").read_bytes())
    assert [(e.subject["ex"], e.code, e.stage, e.disposition, e.severity) for e in entries] == [
        (ps.EX_LEAK, "release.withheld", "package", "withheld", "info")]
    assert entries[0].detail == purge.WITHHELD_DETAIL
    assert ps.SENTINEL not in "".join(p.read_bytes().decode("utf-8", "replace") for p in c["root"].rglob("*")
                                      if p.is_file() and "objects" not in p.parts[-4:-1])
    assert not (c["root"] / ".agentprov.lock").exists()  # the lock is released


def test_apply_prunes_the_emptied_shard_directory_and_the_tree_stays_closed_world(tmp_path):
    from agentprov.corpus.layout import iter_tree

    c = ps.build_working(tmp_path / "c.partial")
    if c["leak"][:2] == c["other"][:2]:
        pytest.skip("the two fixture objects share a shard")
    purge.apply(purge.plan_corpus(c["root"], c["leak"], "secret", today=_today))
    assert not (c["root"] / "raw" / "objects" / c["leak"][:2]).exists()  # pruned, never left empty
    assert (c["root"] / "raw" / "objects").is_dir() and (c["root"] / "raw" / "objects" / c["other"][:2]).is_dir()
    assert "corpus.tree.empty_dir" not in {f.code for f in iter_tree(c["root"]).findings}


def test_a_second_purge_is_idempotent_and_the_tombstone_is_kept(tmp_path):
    c = ps.build_working(tmp_path / "c.partial")
    purge.apply(purge.plan_corpus(c["root"], c["leak"], "secret", today=_today))
    before = ps.tree_text(c["root"])
    again = purge.plan_corpus(c["root"], c["leak"], "personal_data", today=lambda: "2030-01-01")
    assert again.already_tombstoned and again.object_label is None and again.reason == "secret" and again.date == DAY
    result = purge.apply(again)
    assert not result.removed and not result.tombstone_written and result.register_entries_written == 0
    assert ps.tree_text(c["root"]) == before


def test_a_crash_after_the_tombstone_is_finished_by_running_the_purge_again(tmp_path):
    c = ps.build_working(tmp_path / "c.partial")
    path = c["root"] / "raw" / "tombstones.jsonl"
    path.write_bytes(purge.encode_tombstones([purge.Tombstone(c["leak"], "secret", DAY)]))  # the first step only
    plan = purge.plan_corpus(c["root"], c["leak"], "secret", today=lambda: "2031-01-01")
    assert plan.already_tombstoned and plan.object_label is not None and plan.date == DAY
    result = purge.apply(plan)
    assert result.removed and not result.tombstone_written and result.register_entries_written == 1


def test_purging_a_container_withholds_the_executions_of_its_members(tmp_path):
    c = ps.build_working(tmp_path / "c.partial")
    plan = purge.plan_corpus(c["root"], c["container"], "secret", today=_today)
    assert plan.affected == (ps.EX_MEMBER,) and plan.member_objects == (c["member"],)
    result = purge.apply(plan)
    assert result.removed and result.register_entries_written == 1
    assert (c["root"] / "raw" / "objects" / c["member"][:2]).is_dir()  # the member object stays; the plan listed it


def test_purging_a_member_points_at_its_container(tmp_path):
    c = ps.build_working(tmp_path / "c.partial")
    plan = purge.plan_corpus(c["root"], c["member"], "secret", today=_today)
    assert plan.container_objects == (c["container"],) and plan.affected == (ps.EX_MEMBER,)


def _with_links(c, *, carved: bool = False, split: bool = False) -> dict:
    """Add D-315 linked objects to the purge_support corpus: a value carved from ``leak`` (D-218) and/or a split archive
    (a descriptor and two byte parts, D-244), with their raw/origins.jsonl rows."""
    from agentprov.raw.origins import Origin, OriginRow, encode_origins
    from agentprov.raw.store import RawObjectStore

    store = RawObjectStore(c["layout"].raw)
    rows: list[OriginRow] = []
    out = dict(c)
    if carved:
        blob = store.put(ps.SENTINEL.encode(), ext="bin").sha256  # the leaked value, carved from leak's JSON string
        rows.append(OriginRow(blob, Origin.carved(c["leak"], {"p": "/key"}, "utf8")))
        out["blob"] = blob
    if split:
        part1 = store.put(b"PK-part-one-" + ps.SENTINEL.encode(), ext="bin").sha256
        part2 = store.put(b"-part-two", ext="bin").sha256
        descriptor = store.put(b'{"archive": "zip", "parts": 2}', ext="json").sha256
        rows.append(OriginRow(descriptor, Origin.split("deposit.zip", [part1, part2])))
        rows += [OriginRow(p, Origin.local(f"/tmp/deposit.zip.part-{i}")) for i, p in enumerate((part1, part2))]
        out.update(descriptor=descriptor, part1=part1, part2=part2)
    (c["root"] / "raw" / "origins.jsonl").write_bytes(encode_origins(rows))
    return out


def test_purging_a_source_lists_the_value_carved_from_it_and_leaves_it_stored(tmp_path):
    """Ultrareview raw-withhold #4: a carved blob (D-218) holds the same leaked value as its source. The plan lists it
    (D-315, the seal planner's own groups), both ways, and the purge leaves it stored, as it does a member object."""
    c = _with_links(ps.build_working(tmp_path / "c.partial"), carved=True)
    plan = purge.plan_corpus(c["root"], c["leak"], "secret", today=_today)
    assert plan.linked_objects == (c["blob"],) and plan.affected == (ps.EX_LEAK,)  # the closure withholds no execution
    assert purge.plan_corpus(c["root"], c["blob"], "secret", today=_today).linked_objects == (c["leak"],)
    result = purge.apply(plan)
    assert result.removed and result.plan.linked_objects == (c["blob"],)
    assert list(c["root"].joinpath("raw", "objects", c["blob"][:2]).glob(f"{c['blob']}.*"))  # listed, still stored


def test_purging_a_split_part_or_descriptor_lists_the_rest_of_the_split_archive(tmp_path):
    """Ultrareview raw-withhold #4: a split descriptor and its byte parts are one archive (D-244, D-315): purging any of
    them lists the others."""
    c = _with_links(ps.build_working(tmp_path / "c.partial"), split=True)
    parts = sorted((c["part1"], c["part2"]))
    assert purge.plan_corpus(c["root"], c["descriptor"], "secret", today=_today).linked_objects == tuple(parts)
    plan = purge.plan_corpus(c["root"], c["part1"], "secret", today=_today)
    assert plan.linked_objects == tuple(sorted((c["descriptor"], c["part2"])))
    assert plan.member_objects == () and plan.container_objects == () and plan.affected == ()
    purge.apply(plan)
    for sha in (c["descriptor"], c["part2"]):
        assert list(c["root"].joinpath("raw", "objects", sha[:2]).glob(f"{sha}.*"))


def test_without_linked_origins_the_plan_lists_no_linked_object(tmp_path):
    c = ps.build_working(tmp_path / "c.partial")
    assert purge.plan_corpus(c["root"], c["leak"], "secret", today=_today).linked_objects == ()


def test_two_purges_withhold_one_execution_once(tmp_path):
    c = ps.build_working(tmp_path / "c.partial")
    purge.apply(purge.plan_corpus(c["root"], c["member"], "secret", today=_today))
    result = purge.apply(purge.plan_corpus(c["root"], c["container"], "personal_data", today=_today))
    assert result.register_entries_written == 0
    assert len(decode_register((c["root"] / "register.jsonl").read_bytes())) == 1
    assert [t.sha256 for t in purge.decode_tombstones((c["root"] / "raw" / "tombstones.jsonl").read_bytes())] == sorted(
        [c["member"], c["container"]])


def test_a_sealed_tree_is_refused_at_apply_time_too(tmp_path):
    c = ps.build_working(tmp_path / "c.partial")
    plan = purge.plan_corpus(c["root"], c["leak"], "secret", today=_today)
    manifest = c["root"] / "corpus.json"
    manifest.write_bytes(manifest.read_bytes().replace(b'"sealed": false', b'"sealed": true'))
    with pytest.raises(SealedCorpusError):
        purge.apply(plan)
    assert (c["root"] / "raw" / "objects" / c["leak"][:2]).is_dir() and not (c["root"] / "raw" / "tombstones.jsonl").exists()


def test_the_object_files_are_read_only_but_the_purge_removes_them(tmp_path):
    c = ps.build_working(tmp_path / "c.partial")
    path = c["root"] / "raw" / "objects" / c["leak"][:2] / f"{c['leak']}.json"
    assert stat.S_IMODE(os.lstat(path).st_mode) == 0o444
    purge.apply(purge.plan_corpus(c["root"], c["leak"], "secret", today=_today))
    assert not path.exists()


# ------------------------------------------------------------------------------------------------ cache
def _cache(tmp_path):
    import hashlib

    cache = tmp_path / "cache"
    data = b"downloaded-bytes-" + ps.SENTINEL.encode()
    sha = hashlib.sha256(data).hexdigest()
    (cache / "zenodo" / "123").mkdir(parents=True)
    (cache / "zenodo" / "123" / "logs.zip").write_bytes(data)
    (cache / "url").mkdir()
    (cache / "url" / ("ff" * 32)).write_bytes(b"other")
    (cache / "git" / "github.com" / "o").mkdir(parents=True)
    (cache / "git" / "github.com" / "o" / "r.git").write_bytes(b"not searched")
    return cache, sha


def test_cache_purge_removes_a_downloaded_file_and_writes_a_cache_tombstone(tmp_path):
    cache, sha = _cache(tmp_path)
    plan = purge.plan_cache(cache, sha, "secret", today=_today)
    assert plan.object_label == "zenodo/123/logs.zip" and plan.tombstone_label == "tombstones.jsonl"
    result = purge.apply(plan)
    assert result.removed and result.tombstone_written
    assert not (cache / "zenodo" / "123" / "logs.zip").exists() and (cache / "url" / ("ff" * 32)).exists()
    assert purge.decode_tombstones((cache / "tombstones.jsonl").read_bytes())[0] == purge.Tombstone(sha, "secret", DAY)
    assert purge.apply(purge.plan_cache(cache, sha, "secret")).tombstone_written is False  # already purged: a no-op


def test_cache_purge_removes_every_cached_copy_of_the_bytes(tmp_path):
    """Ultrareview raw-withhold #5: the same bytes pinned twice (a Zenodo file and its URL or HF mirror) are cached at
    two paths. The plan lists both and the purge unlinks both; it used to stop at the first match."""
    cache, sha = _cache(tmp_path)
    data = (cache / "zenodo" / "123" / "logs.zip").read_bytes()
    (cache / "url" / sha).write_bytes(data)
    (cache / "hf" / "o" / "r" / "rev1").mkdir(parents=True)
    (cache / "hf" / "o" / "r" / "rev1" / "logs.zip").write_bytes(data)
    plan = purge.plan_cache(cache, sha, "secret", today=_today)
    labels = {plan.object_label, *plan.other_labels}
    assert labels == {"zenodo/123/logs.zip", f"url/{sha}", "hf/o/r/rev1/logs.zip"} and len(plan.other_labels) == 2
    result = purge.apply(plan)
    assert result.removed
    assert not any((cache / label).exists() for label in labels)
    assert (cache / "url" / ("ff" * 32)).exists()  # other bytes stay
    again = purge.plan_cache(cache, sha, "secret")
    assert again.object_label is None and again.other_labels == () and again.already_tombstoned


def test_cache_url_files_are_found_by_name_and_git_stores_are_not_searched(tmp_path):
    cache, _sha = _cache(tmp_path)
    assert purge.plan_cache(cache, "ff" * 32, "personal_data", today=_today).object_label == f"url/{'ff' * 32}"
    with pytest.raises(purge.UnknownObjectError) as exc:
        purge.plan_cache(cache, "ee" * 32, "secret")
    assert exc.value.exit_code == 2 and "git objects" in str(exc.value)
    with pytest.raises(purge.UsageError):
        purge.plan_cache(tmp_path / "nocache", "ee" * 32, "secret")


def _nested_working(root):
    """outer.zip > inner.zip > log.json, every level stored, one execution citing the log (the CB-1 shape)."""
    import zlib

    from agentprov.corpus.index import ExecutionEntry, RawRef
    from agentprov.corpus.writer import CorpusWriter
    from agentprov.raw.members import MemberRow
    from agentprov.raw.origins import Origin

    def crc(data: bytes) -> str:
        return f"{zlib.crc32(data):08x}"

    fn, ex = "f" * 64, "ex_" + "b" * 26
    log, inner, outer = b'{"leak": "x"}', b"INNER-archive", b"OUTER-archive"
    with CorpusWriter(root, git_ignored=lambda _tree, _path: True) as w:
        po = w.add_object(outer, Origin.local("/tmp/outer.zip"), ext="zip")
        pi = w.add_object(inner, Origin.member(po.sha256, "inner.zip", 8, crc(inner), len(inner)), ext="zip")
        pl = w.add_object(log, Origin.member(pi.sha256, "log.json", 8, crc(log), len(log)), ext="json")
        w.members.add_container(po.sha256, [MemberRow(po.sha256, fn, "inner.zip", 8, crc(inner), len(inner), pi.sha256,
                                                      "selected")])
        w.members.add_container(pi.sha256, [MemberRow(pi.sha256, fn, "log.json", 8, crc(log), len(log), pl.sha256,
                                                      "selected")])
        w.write_aer(ex, b"{}\n")
        w.add_execution(ExecutionEntry(
            ex=ex, mode="import", unit="agent_execution", source_id="s", snapshot_ids=("s1",),
            source_key="sha256:" + pl.sha256 + "#{}", raw=(RawRef(pl.sha256, "primary", True),), adapter="a.b@0.1.0",
            profile="p@1", aer_digest="1" * 64, stages={"aer": "ok", "raw": "ok"}, completeness="unverifiable",
            execution_observed=True))
    return root.with_name(root.name + ".partial"), po.sha256, pi.sha256, pl.sha256, ex


def test_purging_an_outer_archive_withholds_the_executions_of_nested_members_and_the_seal_agrees(tmp_path):
    """CB-1: purge and the seal planner follow raw/members.jsonl through every nesting level, with one closure, so the
    purge registers the nested log's execution and the seal explains that register entry (no
    corpus.withhold.unexplained)."""
    from agentprov.corpus.reader import CorpusReader
    from agentprov.corpus.withhold import plan_withholding

    work, outer, inner, log, ex = _nested_working(tmp_path / "c")
    plan = purge.plan_corpus(work, outer, "secret", today=_today)
    assert plan.affected == (ex,) and set(plan.member_objects) == {inner, log}
    purge.apply(plan)
    reader = CorpusReader(work, state="working", used_partial=True)
    assert [e.subject for e in reader.register() if e.code == "release.withheld"] == [{"ex": ex}]
    tombstones = purge.decode_tombstones((work / "raw" / "tombstones.jsonl").read_bytes())
    sealed = plan_withholding(rows=list(reader.iter_index()), register=reader.register(), members=reader.members(),
                              origins=reader.origins(), present={}, tombstones=tombstones, snapshots={},
                              stream=lambda _label: iter(()), derived=lambda _row: [], artefacts=lambda _row: [])
    assert sealed.executions == {ex}
