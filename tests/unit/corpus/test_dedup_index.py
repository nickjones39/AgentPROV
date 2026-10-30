"""``source_key`` (H.7.1) and the phase-3 execution index (H.3)."""

from __future__ import annotations

import json

import pytest

from agentprov.corpus.dedup import source_key
from agentprov.corpus.index import (
    ExecutionEntry,
    IndexError_,
    IndexLog,
    IndexRow,
    RawRef,
    compute_status,
    decode_index,
    encode_index,
)
from agentprov.corpus.layout import CorpusLayout

EX = "ex_7uz2oys57hugtsueixylme4fl5"
EX2 = "ex_" + "a" * 26
H = "ab" * 32
LAYOUT = CorpusLayout("/x")


def test_source_key_vectors():
    assert source_key(H, {}) == f"sha256:{H}#{{}}"
    assert source_key(H, {"p": ""}) == f'sha256:{H}#{{"p":""}}'
    assert source_key(H, {"line": 3}) == f'sha256:{H}#{{"line":3}}'
    assert source_key(H, {"line": 3, "p": "/a"}) == f'sha256:{H}#{{"line":3,"p":"/a"}}'  # JCS member order
    for bad_digest in ("", "AB" * 32, H[:-1]):
        with pytest.raises(ValueError):
            source_key(bad_digest, {})
    for bad_loc in ({"a": "a0"}, {"p": "no-slash"}, {"line": -1}, {"bytes": [1, 2], "p": ""}):
        with pytest.raises(ValueError):
            source_key(H, bad_loc)


def row(ex=EX, **kw) -> IndexRow:
    base = dict(
        ex=ex, mode="import", unit="agent_execution", source_id="agentdojo", snapshot_ids=("2024-06",), source_key=source_key(H, {"p": ""}),
        raw=(RawRef(H, "primary", True),), n_origins=1, adapter="agentdojo.tracelogger@0.1.0", profile="agentdojo-upstream@1", aer_digest="cd" * 32,
        aer_path=LAYOUT.aer_relpath(ex), stages={"raw": "ok", "aer": "ok"}, status="ok", completeness="unverifiable", execution_observed=True, issues=(), attempt=None,
    )
    base.update(kw)
    return IndexRow(**base)


def test_row_has_exactly_the_phase3_members_and_no_placeholders():
    j = row(issues=("map.accounting_unverifiable",), status="ok_with_issues").to_json()
    assert sorted(j) == ["adapter", "attempt", "completeness", "digests", "ex", "execution_observed", "issues", "mode", "n_origins", "paths", "profile",
                         "raw", "snapshot_ids", "source_id", "source_key", "stages", "status", "unit"]
    assert j["digests"] == {"aer": "sha256:" + "cd" * 32} and j["paths"] == {"aer": LAYOUT.aer_relpath(EX)} and j["stages"] == {"aer": "ok", "raw": "ok"}
    assert j["raw"] == [{"included": True, "role": "primary", "sha256": "sha256:" + H}]
    # later-phase members are omitted, never written as null or empty placeholders
    for omitted in ("facets", "ev", "logical_key", "cell", "oracles"):
        assert omitted not in j
    assert "sem" not in j["digests"] and "prov" not in j["paths"] and "sem" not in j["stages"]


def test_round_trip_and_path_recomputation():
    r = row()
    assert IndexRow.from_json(json.loads(r.line()), LAYOUT) == r
    tampered = json.loads(r.line())
    tampered["paths"]["aer"] = "aer/00/" + EX + ".aer.jsonl"
    with pytest.raises(IndexError_) as exc:
        IndexRow.from_json(tampered, LAYOUT)
    assert exc.value.code == "corpus.index.path"
    IndexRow.from_json(tampered)  # without a layout the path is not checked


@pytest.mark.parametrize(
    "kw",
    [
        dict(ex="ex_bad"), dict(mode="replay"), dict(unit="x"), dict(completeness="complete"), dict(status="fine"),
        dict(source_id="Bad Id"), dict(snapshot_ids=()), dict(snapshot_ids=("b", "a")), dict(snapshot_ids=("a", "a")),
        dict(source_key="nope"), dict(source_key=f"sha256:{H}#not json"), dict(source_key=f'sha256:{H}#{{ "p": "" }}'),  # not in JCS form
        dict(raw=()), dict(raw=(RawRef(H, "supporting", True),)), dict(raw=(RawRef(H, "primary", True), RawRef("1" * 64, "primary", True))),
        dict(n_origins=0), dict(n_origins=True), dict(adapter="agentdojo.tracelogger"), dict(profile="p@0"), dict(aer_digest="short"),
        dict(stages={"raw": "ok"}), dict(stages={"raw": "ok", "aer": "ok", "sem": "ok"}), dict(stages={"raw": "ok", "aer": "done"}),
        dict(issues=("map.b", "map.a")), dict(issues=("made.up",)), dict(attempt=0),  # an import has no attempt
        dict(mode="live"),  # a live execution needs one
        dict(execution_observed="yes"),
    ],
)
def test_invalid_rows_are_refused(kw):
    with pytest.raises((IndexError_, ValueError)):
        row(**kw)


def test_live_rows_carry_an_attempt():
    live_raw = (RawRef(H, "capture_log", True), RawRef("ef" * 32, "native_log", True))
    assert row(mode="live", attempt=2, raw=live_raw, source_key=source_key(H, {})).to_json()["attempt"] == 2


def test_the_primary_of_a_live_row_is_its_capture_log():
    """H.3.1/H.7.1: a live execution's source key names its capture log; a live AER has no ``primary`` artefact."""
    with pytest.raises(IndexError_):
        row(mode="live", attempt=0, raw=(RawRef(H, "native_log", True),))
    with pytest.raises(IndexError_):
        row(raw=(RawRef(H, "capture_log", True),))  # an import row still needs its primary artefact


@pytest.mark.parametrize(
    ("stages", "severities", "status"),
    [
        ({"raw": "ok", "aer": "ok"}, [], "ok"),
        ({"raw": "ok", "aer": "ok"}, ["info", "info"], "ok"),  # info issues document source limitations; no change
        ({"raw": "ok", "aer": "ok"}, ["info", "warning"], "ok_with_issues"),
        ({"raw": "ok", "aer": "ok"}, ["warning", "error"], "failed"),
        ({"raw": "ok", "aer": "failed"}, [], "failed"),
    ],
)
def test_status_follows_h32(stages, severities, status):
    assert compute_status(stages, severities) == status


def test_file_is_sorted_by_ex_with_one_row_per_execution(tmp_path):
    rows = [row(EX2), row(EX)]
    data = encode_index(rows)
    assert [r.ex for r in decode_index(data, LAYOUT)] == sorted([EX, EX2])
    assert encode_index(reversed(rows)) == data and encode_index([]) == b"" and decode_index(b"") == []
    with pytest.raises(IndexError_):
        encode_index([row(), row()])
    first, second = data.splitlines(keepends=True)
    with pytest.raises(IndexError_):
        decode_index(second + first)
    with pytest.raises(IndexError_):
        decode_index(data.replace(b'"mode":"import"', b'"mode":"import","extra":1', 1))
    log = IndexLog(rows)
    log.add(row(EX))  # an identical row is idempotent
    with pytest.raises(IndexError_):
        log.add(row(EX, completeness="known_incomplete"))
    path = tmp_path / "executions.jsonl"
    log.write(path)
    assert IndexLog.load(path, LAYOUT).rows() == log.rows() and len(log) == 2


def test_execution_entry_is_plain_data():
    entry = ExecutionEntry(EX, "import", "agent_execution", "s", ["a"], "k", [RawRef(H, "primary", True)], "x.y@0.1.0", "p@1", "0" * 64, {"raw": "ok", "aer": "ok"}, "unverifiable", True)
    assert entry.issues == () and entry.attempt is None


def test_sem_stage_round_trips_with_profile_keyed_digests_and_paths():
    """Phase 7 (H.3.4): ``stages.sem``, ``digests.sem`` and ``paths.sem`` are keyed by ``<profile id>@<version>``."""
    from agentprov.corpus.index import StageOutput

    ref = "agentdojo.suites@1"
    r = row(sem={ref: StageOutput("ok", "ef" * 32)}, sem_paths={ref: LAYOUT.sem_relpath(ref, EX)})
    j = r.to_json()
    assert j["stages"]["sem"] == {ref: "ok"} and j["digests"]["sem"] == {ref: "sha256:" + "ef" * 32}
    assert j["paths"]["sem"] == {ref: f"sem/agentdojo.suites-1/{LAYOUT.aer_relpath(EX).split('/')[1]}/{EX}.sem.jsonl"}
    assert IndexRow.from_json(json.loads(r.line()), LAYOUT) == r
    failed = row(sem={ref: StageOutput("failed")}, sem_paths={})
    back = IndexRow.from_json(json.loads(failed.line()), LAYOUT)
    assert back.sem == {ref: StageOutput("failed")} and "sem" not in failed.to_json()["paths"]
    tampered = json.loads(r.line())
    tampered["paths"]["sem"][ref] = "sem/x/00/" + EX + ".sem.jsonl"
    with pytest.raises(IndexError_) as exc:
        IndexRow.from_json(tampered, LAYOUT)
    assert exc.value.code == "corpus.index.path"
    for bad in (dict(sem={}), dict(sem={"suites@1": StageOutput("ok")}), dict(sem={ref: StageOutput("ok", "ef" * 32)}),
                dict(sem_paths={ref: "x"})):
        with pytest.raises(IndexError_):
            row(**bad)
