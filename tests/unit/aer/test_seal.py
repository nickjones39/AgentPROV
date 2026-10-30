"""C.11.6 / C.12.4 / AER-V24, V25: the seal, the writer, the reader, and byte-exact reproduction of the C.16 vectors."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pytest
from aer_support import (
    KAT1_EX,
    VECTOR_NAMES,
    codes_of,
    edit,
    example_records,
    example_store,
    make_registry,
    vector_bytes,
    vector_records,
    vector_registry,
)

from agentprov.aer.reader import (
    AerFormatError,
    AerIntegrityError,
    iter_records,
    load_aer,
    read_header,
    read_seal,
)
from agentprov.aer.validate import validate_file, validate_records
from agentprov.aer.writer import AerWriteError, AerWriter


def write(tmp_path: Path, records: list[dict[str, Any]], registry: Any = None, issues: Any = ()) -> tuple[Path, Any]:
    path = tmp_path / "x.aer.jsonl"
    writer = AerWriter(path, records[0], catalogues=registry or make_registry())
    for rec in records[1:]:
        writer.add(rec)
    return path, writer.seal(issues=list(issues))


# ------------------------------------------------------------------------------------------ vectors (C.16)
@pytest.mark.parametrize("name", VECTOR_NAMES)
def test_writer_reproduces_each_vector_byte_for_byte(name: str, tmp_path: Path) -> None:
    """The writer seals ``aer/0.2`` (D-212): it reproduces the ``aer/0.2`` reseal of each C.16 vector byte for byte, and
    the reseal differs from the frozen ``aer/0.1`` vector only in the header's ``aer`` member and the seal."""
    from aer_support import vector_path

    records = vector_records(name)
    given = [i for i in records[-1]["issues"] if not i["code"].startswith("accounting_")]  # mirrors are the writer's job
    path, info = write(tmp_path, records[:-1], vector_registry(), given)
    resealed = vector_path(name, "0.2")
    if os.environ.get("AGENTPROV_REGENERATE_GOLDEN") == "1":
        resealed.parent.mkdir(parents=True, exist_ok=True)
        resealed.write_bytes(path.read_bytes())
    assert path.read_bytes() == resealed.read_bytes()
    assert info.file_sha256 == hashlib.sha256(resealed.read_bytes()).hexdigest()
    assert info.n_records == len(records)
    new_lines, old_lines = resealed.read_bytes().splitlines(), vector_bytes(name).splitlines()
    assert new_lines[1:-1] == old_lines[1:-1]
    new_header, old_header = json.loads(new_lines[0]), json.loads(old_lines[0])
    assert (new_header.pop("aer"), old_header.pop("aer")) == ("0.2", "0.1") and new_header == old_header


def test_kat_vector_digest_of_c161() -> None:
    records = vector_records("agentdojo_2024_pi_detector")
    assert records[0]["ex"] == KAT1_EX
    assert records[-1]["records_sha256"] == "7ae9e35abb0cec5b803f7f24ade0e7fc7c81b918989bba3c05c9151366934cc2"


@pytest.mark.parametrize("name", VECTOR_NAMES)
def test_reader_verifies_the_vectors(name: str) -> None:
    from aer_support import vector_path

    doc = load_aer(vector_path(name))
    assert doc.execution_digest == doc.seal["records_sha256"]
    assert doc.file_sha256 == hashlib.sha256(vector_bytes(name)).hexdigest()
    assert doc.ex.startswith("ex_") and doc.header["k"] == "execution"
    assert doc.get("exec") is doc.header


# ------------------------------------------------------------------------------------------ writer
def test_writer_output_is_deterministic(tmp_path: Path) -> None:
    a, info_a = write(tmp_path, example_records())
    first = a.read_bytes()
    b = tmp_path / "second.aer.jsonl"
    writer = AerWriter(b, example_records()[0], catalogues=make_registry())
    for rec in example_records()[1:]:
        writer.add(rec)
    writer.seal(issues=[])
    assert b.read_bytes() == first
    assert info_a.execution_digest == hashlib.sha256(first[: first.rindex(b"\n", 0, len(first) - 1) + 1]).hexdigest()


def test_the_written_file_validates_and_ends_with_the_seal(tmp_path: Path) -> None:
    path, info = write(tmp_path, example_records())
    data = path.read_bytes()
    assert data.endswith(b"\n") and b"\r" not in data and not data.startswith(b"\xef\xbb\xbf")
    seal = json.loads(data.splitlines()[-1])
    assert seal["k"] == "seal" and seal["n_records"] == len(data.splitlines())
    assert validate_file(path, store=example_store(), catalogues=make_registry()).ok
    assert info.accounting.status == "unverifiable" and info.issues[-1]["code"] == "accounting_unverifiable"


def test_the_writer_never_writes_time_paths_hosts_or_versions(tmp_path: Path) -> None:
    path, _ = write(tmp_path, example_records())
    text = path.read_text(encoding="utf-8")
    for needle in (str(tmp_path), "agentprov-", "hostname", "pid", "T12:", "2026-10-08T"):
        assert needle not in text


def test_mirror_issues_are_added_once(tmp_path: Path) -> None:
    mirrored = {"code": "accounting_unverifiable", "ids": ["att0"], "rule": "aer.acc.agent_calls_vs_assistant@1"}
    _, info = write(tmp_path, example_records(), issues=[mirrored])
    assert [i["code"] for i in info.issues].count("accounting_unverifiable") == 1


def test_a_failed_add_poisons_the_writer_and_leaves_no_file(tmp_path: Path) -> None:
    path = tmp_path / "x.aer.jsonl"
    recs = example_records()
    writer = AerWriter(path, recs[0], catalogues=make_registry())
    for rec in recs[1:6]:
        writer.add(rec)
    with pytest.raises(AerWriteError) as info:
        writer.add({"k": "message", "id": "m0", "ev": "O"})
    assert info.value.findings
    with pytest.raises(AerWriteError):
        writer.add(recs[6])
    with pytest.raises(AerWriteError):
        writer.seal(issues=[])
    assert not path.exists()
    assert not list(tmp_path.iterdir())


def test_forward_and_duplicate_and_noncanonical_records_are_refused(tmp_path: Path) -> None:
    recs = example_records()
    for bad in (
        edit(recs, "mc0", input=["m5"])[7],  # references a later record
        {**recs[6], "id": "agent"},  # duplicate id
        {**recs[6], "x": float("nan")},  # not canonicalisable
    ):
        writer = AerWriter(tmp_path / "y.aer.jsonl", recs[0], catalogues=make_registry())
        for rec in recs[1:6]:
            writer.add(rec)
        with pytest.raises(AerWriteError):
            writer.add(bad)


def test_the_header_and_seal_are_not_added_as_records(tmp_path: Path) -> None:
    recs = example_records()
    writer = AerWriter(tmp_path / "z.aer.jsonl", recs[0], catalogues=make_registry())
    with pytest.raises(AerWriteError):
        writer.add(recs[0])
    with pytest.raises(AerWriteError):
        writer.add({"k": "seal", "id": "seal"})
    with pytest.raises(AerWriteError):
        AerWriter(tmp_path / "w.aer.jsonl", recs[1], catalogues=make_registry())


def test_sealing_twice_is_refused(tmp_path: Path) -> None:
    recs = example_records()
    writer = AerWriter(tmp_path / "a.aer.jsonl", recs[0], catalogues=make_registry())
    for rec in recs[1:]:
        writer.add(rec)
    writer.seal(issues=[])
    with pytest.raises(AerWriteError):
        writer.seal(issues=[])
    with pytest.raises(AerWriteError):
        writer.add(recs[1])


# ------------------------------------------------------------------------------------------ seal checks
def check(records: list[dict[str, Any]], seal: dict[str, Any]) -> list[str]:
    return codes_of(validate_records([*records, seal], store=None, catalogues=make_registry()))


def good_seal() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from aer_support import seal_record

    recs = example_records()
    return recs, seal_record(recs)


def test_seal_count_and_digest_are_checked() -> None:
    recs, seal = good_seal()
    assert check(recs, seal) == []
    assert "aer.seal.count" in check(recs, {**seal, "n_records": seal["n_records"] + 1})
    assert "aer.seal.digest" in check(recs, {**seal, "records_sha256": "0" * 64})
    tampered = edit(recs, "m0", parts=[{"t": "text", "text": "HELLO"}])
    assert "aer.seal.digest" in check(tampered, seal)


def test_accounting_is_recomputed_and_must_equal_the_seal() -> None:
    recs, seal = good_seal()
    bad_checks = json.loads(json.dumps(seal))
    bad_checks["accounting"]["checks"][1]["observed"]["tool_calls"] = 9
    assert "aer.seal.accounting" in check(recs, bad_checks)
    claim = json.loads(json.dumps(seal))
    claim["accounting"]["status"] = "consistent"
    assert "aer.seal.accounting" in check(recs, claim)
    dropped = json.loads(json.dumps(seal))
    dropped["accounting"]["checks"].pop(1)
    assert "aer.seal.accounting" in check(recs, dropped)
    forged = json.loads(json.dumps(seal))
    forged["accounting"]["checks"][0].update(verdict="consistent")
    forged["accounting"]["status"] = "consistent"
    assert "aer.seal.accounting" in check(recs, forged)


def test_non_consistent_verdicts_must_be_mirrored_as_issues() -> None:
    recs, seal = good_seal()
    unmirrored = {**seal, "issues": []}
    assert "aer.seal.accounting" in check(recs, unmirrored)


def test_live_checks_from_the_capture_mapper_are_accepted_but_not_recomputed() -> None:
    recs, seal = good_seal()
    extra = {"id": "aer.acc.passes_closed@1", "scope": "run", "verdict": "consistent", "observed": {"passes": 1}}
    seal = json.loads(json.dumps(seal))
    seal["accounting"]["checks"].append(extra)
    assert check(recs, seal) == []
    seal["accounting"]["checks"][-1]["verdict"] = "inconsistent"
    seal["accounting"]["status"] = "inconsistent"
    assert "aer.seal.accounting" in check(recs, seal)  # not mirrored
    seal["issues"].append({"code": "accounting_inconsistent", "ids": ["run"], "rule": "aer.acc.passes_closed@1"})
    assert check(recs, seal) == []


def test_issue_codes_ids_and_rules_are_checked() -> None:
    recs, seal = good_seal()

    def with_issue(issue: dict[str, Any]) -> list[str]:
        return check(recs, {**seal, "issues": [*seal["issues"], issue]})

    assert with_issue({"code": "no_outcome_recorded", "ids": ["run"], "rule": "tst.d@1"}) == []
    assert "aer.schema.pattern" in with_issue({"code": "made_up_code", "ids": ["run"], "rule": "tst.d@1"})
    assert "aer.ref.dangling" in with_issue({"code": "no_outcome_recorded", "ids": ["nowhere"], "rule": "tst.d@1"})
    assert "aer.rule.missing" in with_issue({"code": "no_outcome_recorded", "ids": ["run"], "rule": "tst.zzz@1"})
    assert with_issue({"code": "tst.odd_thing", "ids": ["m1#1"], "rule": "tst.d@1"}) == []
    assert "aer.subtype.undeclared" in with_issue({"code": "tst.unlisted", "ids": ["run"], "rule": "tst.d@1"})
    assert "aer.schema.additional" in check(recs, {**seal, "ev": "O"})  # no envelope evidence members on the seal


# ------------------------------------------------------------------------------------------ reader
def test_reader_rejects_tampered_and_malformed_files(tmp_path: Path) -> None:
    path, _ = write(tmp_path, example_records())
    good = path.read_bytes()
    parts = good.splitlines(keepends=True)

    def attempt(data: bytes) -> None:
        p = tmp_path / "t.aer.jsonl"
        p.write_bytes(data)
        list(iter_records(p))

    attempt(good)
    with pytest.raises(AerIntegrityError) as info:
        attempt(b"".join([parts[0], parts[1].replace(b"agent-under-test", b"agent-under-tesT"), *parts[2:]]))
    assert info.value.code == "aer.seal.digest"
    with pytest.raises(AerIntegrityError) as count:
        attempt(b"".join([*parts[:3], *parts[4:]]))
    assert count.value.code in ("aer.seal.count", "aer.seal.digest")
    for bad in (
        good[:-1],  # no final LF
        good.replace(b"\n", b"\r\n", 1),
        b"".join([parts[0], b"\n", *parts[1:]]),
        b"".join([parts[0].replace(b'"id":"exec"', b'"id": "exec"'), *parts[1:]]),
        b"".join(parts[1:]),
        b"".join(parts[:-1]),
        b"",
        parts[0],
    ):
        with pytest.raises(AerFormatError):
            attempt(bad)


def test_reader_unverified_mode_and_ends(tmp_path: Path) -> None:
    path, info = write(tmp_path, example_records())
    parts = path.read_bytes().splitlines(keepends=True)
    tampered = tmp_path / "bad.aer.jsonl"
    tampered.write_bytes(b"".join([parts[0], parts[1].replace(b"agent-under-test", b"agent-under-tesT"), *parts[2:]]))
    assert len(list(iter_records(tampered, verify=False))) == len(parts)
    assert read_header(path)["ex"] == example_records()[0]["ex"]
    assert read_seal(path)["records_sha256"] == info.execution_digest


def test_document_index_and_part_lookup(tmp_path: Path) -> None:
    path, _ = write(tmp_path, example_records())
    doc = load_aer(path)
    assert doc.get("m1")["role"] == "assistant"  # type: ignore[index]
    assert doc.part("m1#1")["t"] == "tool_call"  # type: ignore[index]
    assert doc.part("m1#9") is None and doc.part("te0#0") is None and doc.part("nope#0") is None
    assert [r["id"] for r in doc.of_kind("model_call")] == ["mc0", "mc1"]
    assert doc.get("seal") is None


def test_duplicate_ids_are_a_format_error(tmp_path: Path) -> None:
    from aer_support import seal_record

    from agentprov.aer.canon import dumps_line

    recs = example_records()
    dup = [*recs, {**recs[1]}]
    data = b"".join(dumps_line(r) for r in [*dup, seal_record(dup)])
    path = tmp_path / "dup.aer.jsonl"
    path.write_bytes(data)
    with pytest.raises(AerFormatError):
        load_aer(path)
