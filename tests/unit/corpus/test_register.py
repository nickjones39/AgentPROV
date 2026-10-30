"""``register.jsonl`` (HL H.6; G.3.9)."""

from __future__ import annotations

import base64
import hashlib

import pytest

from agentprov.corpus.register import (
    RegisterEntry,
    RegisterError,
    RegisterLog,
    decode_register,
    encode_register,
    is_known_code,
)
from agentprov.io.canonical import jcs_bytes
from agentprov.raw.members import ExpandEvent

EX = "ex_7uz2oys57hugtsueixylme4fl5"


def entry(code="ingest.archive.traversal", path="a/b", snapshot="s1", stage="ingest", sev="error", disp="not_imported", **kw):
    return RegisterEntry({"snapshot_id": snapshot, "path": path}, code, sev, stage, disp, **kw)


def test_rid_is_the_documented_hash_of_subject_code_and_stage():
    e = entry()
    preimage = b"agentprov-reg/1\n" + jcs_bytes({"code": e.code, "stage": e.stage, "subject": {"snapshot_id": "s1", "path": "a/b"}})
    expected = "r_" + base64.b32encode(hashlib.sha256(preimage).digest()).decode().lower().rstrip("=")[:20]
    assert e.rid == expected and len(e.rid) == 22
    assert entry(path="other").rid != e.rid and entry(detail="changed").rid == e.rid  # detail is not part of the identity


def test_row_shape_has_all_twelve_members():
    row = entry(detail="container=x").to_json()
    assert sorted(row) == ["code", "detail", "disposition", "ids", "owner", "previous", "rid", "rule", "severity", "stage", "subject", "subject_key"]
    assert row["subject_key"] == "s1:a/b" and row["rule"] is None and row["owner"] is None and row["ids"] == []
    assert RegisterEntry({"ex": EX}, "map.no_execution_observed", "warning", "map", "sealed", rule="aer.x@1", ids=("m2", "m1")).to_json()["ids"] == ["m1", "m2"]


def test_subject_key_by_subject_kind():
    assert RegisterEntry({"ex": EX}, "validate.failed", "error", "validate", "failed").subject_key == EX
    assert RegisterEntry({"source_key": "sha256:ab#{}"}, "select.dialect_planned", "info", "select", "not_imported").subject_key == "sha256:ab#{}"


@pytest.mark.parametrize(
    "code",
    ["select.owned_elsewhere", "select.out_of_scope", "select.redaction_pending", "ingest.size.file", "ingest.interpreter.unpatched", "expand.failed", "map.no_execution_observed", "map.agentdojo.pipeline_name_mismatch",
     "worker.limit.cpu", "time.implausible", "capture.quarantined", "sem.failed", "prov.failed", "validate.failed", "dedup.collapsed", "release.withheld",
     "rules.mismatch", "rules.unavailable", "raw.reference.unpinned_origin", "raw.origin.unpinned", "raw.origin.blob_mismatch"],
)
def test_h63_codes_are_known(code):
    assert is_known_code(code)


@pytest.mark.parametrize("code", ["", "ingest", "ingest.made.up", "worker.limit.disk", "map.", "expand.A", "x.y", "select.other"])
def test_unknown_codes_are_refused(code):
    assert not is_known_code(code)
    with pytest.raises(RegisterError):
        RegisterEntry({"ex": EX}, code, "error", "ingest", "failed")


def test_validation_of_enumerations_stage_and_detail():
    bad = [
        dict(stage="nowhere"), dict(sev="fatal"), dict(disp="deleted"),
        dict(code="expand.failed"),  # a stage-area code on the wrong stage
        dict(disp="withheld"),  # withheld goes with release.withheld only
        dict(detail="x" * 201), dict(detail="two\nlines"), dict(rule=""),
        dict(owner={"corpus_id": "c"}), dict(previous={"corpus_version": "1"}), dict(previous={"corpus_version": "1", "rid": "bad"}),
    ]
    for kwargs in bad:
        with pytest.raises(RegisterError):
            entry(**kwargs)
    entry(detail="x" * 200)
    RegisterEntry({"snapshot_id": "s", "path": "p"}, "release.withheld", "info", "package", "withheld")
    for subject in ({}, {"ex": "nope"}, {"ex": EX, "path": "p"}, {"snapshot_id": "s"}, {"source_key": ""}):
        with pytest.raises(RegisterError):
            RegisterEntry(subject, "validate.failed", "error", "validate", "failed")


def test_worker_limit_codes_may_come_from_any_stage():
    for stage in ("map", "expand", "sem"):
        RegisterEntry({"ex": EX}, "worker.limit.rss", "error", stage, "failed")


def test_file_is_sorted_by_subject_key_then_code_and_collapses_repeats():
    es = [entry(path="b"), entry(path="a", code="ingest.archive.link"), entry(path="a", code="ingest.archive.crc"), entry(path="b", detail="z")]
    data = encode_register(es)
    parsed = decode_register(data)
    assert [(e.subject_key, e.code) for e in parsed] == [("s1:a", "ingest.archive.crc"), ("s1:a", "ingest.archive.link"), ("s1:b", "ingest.archive.traversal")]
    assert encode_register(reversed(es)) == data  # insertion order is irrelevant, also for the collapsed repeat
    assert encode_register([]) == b"" and decode_register(b"") == []


def test_decode_rejects_noncanonical_files():
    data = encode_register([entry(path="a"), entry(path="b")])
    first, second = data.splitlines(keepends=True)
    for bad in (second + first, data + first, data.rstrip(b"\n"), data.replace(b"\n", b"\r\n")):
        with pytest.raises(RegisterError):
            decode_register(bad)
    with pytest.raises(RegisterError):
        decode_register(data.replace(b'"severity":"error"', b'"severity":"fatal"'))
    with pytest.raises(RegisterError):
        decode_register(data.replace(first[first.index(b'"rid":"') + 7 : first.index(b'"rid":"') + 12], b"aaaaa", 1))  # rid no longer matches


def test_from_event_builds_the_ingest_entry():
    event = ExpandEvent("s1", "x.json", "ingest.archive.crc", "ingest", "error", "not_imported", "container=a; reason")
    e = RegisterEntry.from_event(event)
    assert (e.subject, e.code, e.stage, e.severity, e.disposition, e.detail) == (
        {"snapshot_id": "s1", "path": "x.json"}, "ingest.archive.crc", "ingest", "error", "not_imported", "container=a; reason",
    )


def test_register_log_accumulates_writes_and_loads(tmp_path):
    log = RegisterLog([entry(path="b")])
    log.extend([entry(path="a"), RegisterEntry({"ex": EX}, "map.accounting_unverifiable", "info", "map", "sealed")])
    assert [e.subject_key for e in log.entries()] == [EX, "s1:a", "s1:b"]
    assert [e.code for e in log.for_execution(EX)] == ["map.accounting_unverifiable"] and log.for_execution("ex_" + "a" * 26) == []
    assert log.severity_counts() == {"error": 2, "info": 1}
    path = tmp_path / "register.jsonl"
    log.write(path)
    assert path.read_bytes() == log.serialise() and RegisterLog.load(path).entries() == log.entries()
    RegisterLog().write(path)
    assert path.read_bytes() == b""


def test_an_empty_id_is_refused_as_the_published_schema_requires():
    """HL-T1 finding of phase 11: ``ids`` holds non-empty strings (corpus-0.1 schema)."""
    with pytest.raises(RegisterError):
        RegisterEntry({"ex": EX}, "map.no_execution_observed", "warning", "map", "sealed", ids=("m1", ""))
    row = RegisterEntry({"ex": EX}, "map.no_execution_observed", "warning", "map", "sealed", ids=("m1",)).to_json()
    assert RegisterEntry.from_json(row).ids == ("m1",)
    row["ids"] = ["m1", ""]
    with pytest.raises(RegisterError):
        RegisterEntry.from_json(row)


#: CB-2: members of untrusted JSON with the wrong type; each was a builtins.TypeError (exit 70 in ``verify``).
WRONG_TYPES = {
    "code": ["x"],
    "stage": [],
    "severity": {},
    "disposition": [],
    "previous": {"corpus_version": "1", "rid": 5},
    "previous-version": {"corpus_version": 1, "rid": "r_" + "a" * 20},
    "previous-list": ["corpus_version", "rid"],
    "owner": 5,
    "owner-list": ["corpus_id", "source_id"],
    "owner-values": {"corpus_id": 1, "source_id": None},
    "rule": 5,
    "detail": 5,
}


@pytest.mark.parametrize(("member", "value"), WRONG_TYPES.items(), ids=list(WRONG_TYPES))
def test_a_member_of_the_wrong_type_is_a_register_error_not_a_type_error(member, value):
    row = RegisterEntry({"ex": EX}, "map.no_execution_observed", "warning", "map", "sealed").to_json()
    row[member.split("-")[0]] = value
    with pytest.raises(RegisterError):
        RegisterEntry.from_json(row)
    with pytest.raises(RegisterError):
        decode_register(jcs_bytes(row) + b"\n")
