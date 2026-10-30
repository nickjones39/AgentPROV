"""The writer reproduces the C.13.8 synthetic test vector byte for byte; the verifier accepts it."""

from __future__ import annotations

import hashlib
from pathlib import Path

from cap_support import SESSION, VECTOR_HEAD, VECTOR_PATH, VECTOR_SHA256, new_log, replay_vector, vector_lines

from agentprov_capture.verify import line_hash, verify_file


def test_writer_reproduces_the_vector_byte_for_byte(tmp_path: Path) -> None:
    log = new_log(tmp_path)
    head = replay_vector(log)
    produced = log.path.read_bytes()
    assert produced == VECTOR_PATH.read_bytes()
    assert hashlib.sha256(produced).hexdigest() == VECTOR_SHA256
    assert head == VECTOR_HEAD == line_hash(vector_lines()[-1])
    assert log.n_events == 13 and log.closed and log.head == head


def test_blobs_are_content_addressed_and_match_the_vector_references(tmp_path: Path) -> None:
    import json

    log = new_log(tmp_path)
    replay_vector(log)
    refs = []
    for line in vector_lines():
        data = json.loads(line)["data"]
        for key in ("request", "response", "messages"):
            if key in data:
                refs.append(data[key])
    assert len(refs) == 5
    for ref in refs:
        hexdigest = ref["$blob"].removeprefix("sha256:")
        blob = tmp_path / "raw" / "blobs" / "sha256" / hexdigest[:2] / hexdigest
        data = blob.read_bytes()
        assert hashlib.sha256(data).hexdigest() == hexdigest and len(data) == ref["bytes"]
    leftovers = [p for p in (tmp_path / "raw" / "blobs").rglob("*") if p.is_file() and p.suffix == ".tmp"]
    assert leftovers == []


def test_verifier_accepts_the_vector_and_the_written_log(tmp_path: Path) -> None:
    for path in (VECTOR_PATH, _written(tmp_path)):
        report = verify_file(path)
        assert report.sealed and report.issues == ()
        assert report.n_verified == 13 and report.head == VECTOR_HEAD
        assert report.status == "complete" and report.appended_by == "worker"


def _written(tmp_path: Path) -> Path:
    log = new_log(tmp_path)
    replay_vector(log)
    return log.path


def test_session_id_in_the_vector() -> None:
    assert SESSION in VECTOR_PATH.read_text(encoding="utf-8")
