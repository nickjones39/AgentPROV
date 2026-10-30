"""The SEM reader (C.14.1 with the AER line rules of C.2.1 and C.11): round trip, canonical lines, framing, seal."""

from __future__ import annotations

import hashlib
import json

import pytest
from sem_support import EXAMPLE_SEM, example_sem

from agentprov.aer.canon import dumps_line
from agentprov.sem.engine import dumps_sem
from agentprov.sem.reader import SemFormatError, SemIntegrityError, load_sem, load_sem_bytes


def _lines() -> list[bytes]:
    return dumps_sem(example_sem()).splitlines(keepends=True)


def _reseal(lines: list[bytes]) -> bytes:
    """Recompute the seal over ``lines`` (header and annotations): a consistent file with edited content."""
    body = b"".join(lines)
    seal = {"k": "seal", "id": "seal", "n_records": len(lines) + 1, "records_sha256": hashlib.sha256(body).hexdigest()}
    return body + dumps_line(seal)


def test_round_trip_through_a_file(tmp_path) -> None:
    doc = example_sem()
    path = tmp_path / "x.sem.jsonl"
    path.write_bytes(dumps_sem(doc))
    back = load_sem(path)
    assert back.header == doc.header and back.records == doc.records and back.seal == doc.seal
    assert back.digest == doc.digest and back.file_sha256 == doc.file_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert dumps_sem(back) == path.read_bytes()
    assert load_sem_bytes(EXAMPLE_SEM.read_bytes()).digest == doc.digest


def test_non_canonical_line_is_rejected() -> None:
    lines = _lines()
    record = json.loads(lines[1])
    lines[1] = json.dumps(record, indent=None, separators=(", ", ": ")).encode() + b"\n"  # insignificant whitespace
    with pytest.raises(SemFormatError):
        load_sem_bytes(_reseal(lines[:-1]))
    reordered = json.dumps(dict(reversed(list(record.items()))), separators=(",", ":")).encode() + b"\n"
    with pytest.raises(SemFormatError):
        load_sem_bytes(_reseal([lines[0], reordered, *lines[2:-1]]))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda b: b[:-1],  # no final LF
        lambda b: b.replace(b"\n", b"\r\n", 1),  # CR
        lambda b: b.replace(b"\n", b"\n\n", 1),  # blank line
        lambda b: b"\xef\xbb\xbf" + b,  # BOM
        lambda b: b"",  # empty
    ],
)
def test_framing_is_strict(mutate) -> None:
    with pytest.raises(SemFormatError):
        load_sem_bytes(mutate(dumps_sem(example_sem())))


def test_record_kinds_and_order() -> None:
    lines = _lines()
    with pytest.raises(SemFormatError):  # header not first
        load_sem_bytes(_reseal([lines[1], lines[0], *lines[2:-1]]))
    with pytest.raises(SemFormatError):  # seal not last
        load_sem_bytes(b"".join([*lines[:2], lines[-1], *lines[2:-1]]))
    with pytest.raises(SemFormatError):  # an AER record inside a SEM file
        load_sem_bytes(_reseal([lines[0], dumps_line({"k": "message", "id": "m0"}), *lines[1:-1]]))
    with pytest.raises(SemFormatError):  # an annotation without a target
        load_sem_bytes(_reseal([lines[0], dumps_line({"k": "ann", "id": "a0"})]))
    with pytest.raises(SemFormatError):  # no seal
        load_sem_bytes(b"".join(lines[:-1]))
    with pytest.raises(SemFormatError):  # duplicate member names (strict parse)
        load_sem_bytes(_reseal([lines[0], b'{"id":"a0","id":"a1","k":"ann","target":"m0"}\n']))


def test_seal_tampering_is_detected() -> None:
    lines = _lines()
    seal = json.loads(lines[-1])
    tampered_value = lines[1].replace(b'"untrusted"', b'"trusted"')
    assert tampered_value != lines[1]
    with pytest.raises(SemIntegrityError) as digest:
        load_sem_bytes(b"".join([lines[0], tampered_value, *lines[2:]]))
    assert digest.value.code == "sem.seal.digest"
    with pytest.raises(SemIntegrityError) as count:
        load_sem_bytes(b"".join(lines[:-1]) + dumps_line({**seal, "n_records": seal["n_records"] + 1}))
    assert count.value.code == "sem.seal.count"
    with pytest.raises(SemIntegrityError):  # an annotation dropped
        load_sem_bytes(b"".join([*lines[:1], *lines[2:]]))
    assert load_sem_bytes(b"".join([lines[0], tampered_value, *lines[2:]]), verify=False).seal == seal
