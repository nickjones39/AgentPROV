"""``CaptureLog``: ordering, append-only behaviour, write discipline, canonical form, ``append_terminal``."""

from __future__ import annotations

import json
import os
import threading
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from cap_support import ENV_DIGEST, SESSION, new_log, replay_vector, scripted_clock, scripted_mono, start

from agentprov_capture import log as log_module
from agentprov_capture.errors import CaptureLogError, CaptureWriteError
from agentprov_capture.log import CaptureLog, append_terminal
from agentprov_capture.verify import line_hash, split_lines, strict_loads, verify_file

PASS_START = {"env": {"sha256": ENV_DIGEST, "canon": "jcs-rfc8785"}}


def partial_log(tmp_path: Path, name: str = "p") -> CaptureLog:
    """start + instrumentation + pass.start, then the 'worker dies' (file handle dropped, not sealed)."""
    log = new_log(tmp_path, name=name)
    start(log)
    log.emit("pass.start", PASS_START, pass_=0)
    log.abandon()
    return log


# ----------------------------------------------------------------------------------------------- append-only


def test_refuses_to_open_an_existing_non_empty_log(tmp_path: Path) -> None:
    log = new_log(tmp_path)
    start(log)
    before = log.path.read_bytes()
    with pytest.raises(CaptureLogError) as exc:
        new_log(tmp_path)  # same path again
    assert exc.value.code == "cap.log.exists"
    assert log.path.read_bytes() == before  # not truncated, not extended
    log.close("complete")
    sealed = log.path.read_bytes()
    with pytest.raises(CaptureLogError):
        new_log(tmp_path)
    assert log.path.read_bytes() == sealed


def test_refuses_any_non_empty_file_without_modifying_it(tmp_path: Path) -> None:
    path = tmp_path / "x.capture.jsonl"
    path.write_bytes(b"not a log\n")
    with pytest.raises(CaptureLogError) as exc:
        CaptureLog(path, SESSION, blobs_dir=tmp_path / "b")
    assert exc.value.code == "cap.log.exists" and path.read_bytes() == b"not a log\n"


def test_an_existing_empty_file_may_be_opened(tmp_path: Path) -> None:
    path = tmp_path / "x.capture.jsonl"
    path.write_bytes(b"")
    log = CaptureLog(path, SESSION, blobs_dir=tmp_path / "b", clock=scripted_clock(), mono_ns=scripted_mono())
    start(log)
    assert path.stat().st_size > 0


def test_symlink_is_refused(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.write_bytes(b"")
    link = tmp_path / "link.capture.jsonl"
    link.symlink_to(target)
    with pytest.raises(CaptureLogError) as exc:
        CaptureLog(link, SESSION, blobs_dir=tmp_path / "b")
    assert exc.value.code == "cap.log.symlink" and target.read_bytes() == b""
    with pytest.raises(CaptureLogError):
        append_terminal(link, "aborted")


def test_closed_log_accepts_nothing_and_is_not_reopened(tmp_path: Path) -> None:
    log = new_log(tmp_path)
    start(log)
    log.close("complete")
    with pytest.raises(CaptureLogError) as exc:
        log.emit("note", {"kind": "k", "ns": "x", "payload": {}})
    assert exc.value.code == "cap.log.closed"
    with pytest.raises(CaptureLogError):
        log.close("complete")
    with pytest.raises(CaptureLogError):
        log.put_blob(b"x", "text/plain")


# ----------------------------------------------------------------------------------------------- model rules


def test_first_events_and_order(tmp_path: Path) -> None:
    log = new_log(tmp_path)
    with pytest.raises(CaptureWriteError):
        log.emit("pass.start", PASS_START, pass_=0)  # not session.start first
    from cap_support import session_start_data

    log.emit("session.start", session_start_data())
    with pytest.raises(CaptureWriteError):
        log.emit("session.start", session_start_data())
    with pytest.raises(CaptureWriteError):
        log.emit("pass.start", PASS_START, pass_=0)  # instrumentation must be second
    log.emit("instrumentation", {"items": []})
    with pytest.raises(CaptureWriteError):
        log.emit("instrumentation", {"items": []})
    assert log.n_events == 2


@pytest.mark.parametrize("name", ["llm.exchange", "llm.span", "exception", "artefact", "completed", "pass_no"])
def test_rejected_event_types(tmp_path: Path, name: str) -> None:
    log = new_log(tmp_path)
    start(log)
    size = log.path.stat().st_size
    with pytest.raises(CaptureWriteError):
        log.emit(name, {})
    assert log.path.stat().st_size == size


def test_session_end_only_through_close(tmp_path: Path) -> None:
    log = new_log(tmp_path)
    start(log)
    with pytest.raises(CaptureWriteError):
        log.emit("session.end", {"status": "complete", "n_events": 3, "appended_by": "worker"})
    with pytest.raises(CaptureWriteError):
        log.close("completed")  # type: ignore[arg-type]
    with pytest.raises(CaptureWriteError):
        log.close("complete", appended_by="by")


def test_data_members_are_closed(tmp_path: Path) -> None:
    log = new_log(tmp_path)
    start(log)
    with pytest.raises(CaptureWriteError):
        log.emit("pass.start", {**PASS_START, "plan_sha256": "0" * 64}, pass_=0)
    with pytest.raises(CaptureWriteError):
        log.emit("pass.start", {}, pass_=0)


def test_session_start_checks(tmp_path: Path) -> None:
    from cap_support import session_start_data

    for bad in ({"session": "other"}, {"capture": "0.2"}, {"actors": {}}, {"actors": {"Bad": {"kind": "x"}}}):
        log = new_log(tmp_path, name="s" + str(len(str(bad))) + str(sorted(bad)))
        with pytest.raises(CaptureWriteError):
            log.emit("session.start", session_start_data(**bad))
        assert log.n_events == 0
    log = new_log(tmp_path, name="ok")
    with pytest.raises(CaptureWriteError):
        log.emit("session.start", session_start_data(), actor="agent")


def test_actor_and_pass_validation(tmp_path: Path) -> None:
    log = new_log(tmp_path)
    start(log)
    with pytest.raises(CaptureWriteError):
        log.emit("pass.start", PASS_START, pass_=0, actor="ghost")
    for bad in (-1, True, "0", 1.5):
        with pytest.raises(CaptureWriteError):
            log.emit("pass.start", PASS_START, pass_=bad)  # type: ignore[arg-type]
    assert log.emit("pass.start", PASS_START, pass_=0, actor="agent") == 2


def test_not_canonicalisable_values_write_nothing(tmp_path: Path) -> None:
    log = new_log(tmp_path)
    start(log)
    size = log.path.stat().st_size
    for bad in (float("nan"), float("inf"), 2**60, b"bytes", {1: "int key"}):
        with pytest.raises(CaptureWriteError) as exc:
            log.emit("outcome", {"judgements": [{"name": "u", "value": bad, "origin": "checker"}]})
        assert exc.value.code == "cap.write.not_canonical"
    assert log.path.stat().st_size == size and log.n_events == 2
    assert log.emit("outcome", {"judgements": []}) == 2  # the log is still usable


def test_caller_data_is_not_mutated(tmp_path: Path) -> None:
    from agentprov_capture.redact import Redactor, Secret

    log = new_log(tmp_path, redactor=Redactor([Secret("K", "sk-secretsecret1234")]))
    start(log)
    data = {"kind": "k", "ns": "x", "payload": {"v": "sk-secretsecret1234"}}
    log.emit("note", data)
    assert data["payload"]["v"] == "sk-secretsecret1234" and "redactions" not in data


# ----------------------------------------------------------------------------------------------- time


def test_timestamps_and_monotonic_origin(tmp_path: Path) -> None:
    moments = iter(
        [datetime(2026, 10, 7, 12, 0, 0, 5, tzinfo=UTC), datetime(2026, 10, 7, 14, 0, 1, 123456, tzinfo=timezone(timedelta(hours=2)))]
        + [datetime(2026, 10, 7, 12, 0, 2, tzinfo=UTC)] * 5
    )
    monos = iter([10_000_000_000, 10_000_000_007, 10_000_000_100, 10_000_000_200, 10_000_000_300])
    log = CaptureLog(
        tmp_path / "a.jsonl", SESSION, blobs_dir=tmp_path / "b", clock=lambda: next(moments), mono_ns=lambda: next(monos)
    )
    start(log)
    log.close("complete")
    events = [json.loads(ln) for ln in (tmp_path / "a.jsonl").read_bytes().splitlines()]
    assert [e["ts"] for e in events[:2]] == ["2026-10-07T12:00:00.000005Z", "2026-10-07T12:00:01.123456Z"]
    assert [e["mono_ns"] for e in events] == [0, 7, 100]  # origin = first call, at session.start


def test_naive_clock_is_refused(tmp_path: Path) -> None:
    log = CaptureLog(tmp_path / "a.jsonl", SESSION, blobs_dir=tmp_path / "b", clock=lambda: datetime(2026, 1, 1))
    from cap_support import session_start_data

    with pytest.raises(CaptureWriteError):
        log.emit("session.start", session_start_data())
    assert log.n_events == 0


def test_real_clocks_produce_a_valid_sealed_log(tmp_path: Path) -> None:
    log = new_log(tmp_path, scripted=False)
    start(log)
    log.emit("pass.start", PASS_START, pass_=0)
    log.close("incomplete")
    report = verify_file(log.path)
    assert report.sealed and report.status == "incomplete"
    monos = [json.loads(ln)["mono_ns"] for ln in log.path.read_bytes().splitlines()]
    assert monos[0] == 0 and monos == sorted(monos)


# ----------------------------------------------------------------------------------------------- write discipline


def test_fsync_on_pass_end_and_session_end_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []
    real = os.fsync
    monkeypatch.setattr(log_module.os, "fsync", lambda fd: (calls.append(fd), real(fd))[1])
    log = new_log(tmp_path)
    start(log)
    log.emit("pass.start", PASS_START, pass_=0)
    log.emit("state", {"env": {"sha256": ENV_DIGEST, "canon": "jcs-rfc8785"}}, pass_=0)
    assert calls == []
    messages = {"$blob": "sha256:" + "0" * 64, "bytes": 0}
    with pytest.raises(CaptureWriteError):  # a missing blob is refused before anything is written
        log.emit("pass.end", {"aborted": False, "messages": messages, "env": {"sha256": ENV_DIGEST, "canon": "x", "changed": False}}, pass_=0)
    ref = log.put_blob(b"[]", "application/json")
    n_after_blob = len(calls)  # the blob itself is fsynced before its rename
    assert n_after_blob == 1
    log.emit("pass.end", {"aborted": False, "messages": ref, "env": {"sha256": ENV_DIGEST, "canon": "x", "changed": False}}, pass_=0)
    assert len(calls) == n_after_blob + 1
    log.close("complete")
    assert len(calls) >= n_after_blob + 2


def test_blob_is_written_before_the_event_and_atomically(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = new_log(tmp_path)
    start(log)
    ref = log.put_blob(b'{"a":1}', "application/json")
    hexdigest = ref["$blob"].removeprefix("sha256:")
    target = tmp_path / "raw" / "blobs" / "sha256" / hexdigest[:2] / hexdigest
    assert target.read_bytes() == b'{"a":1}' and ref["bytes"] == 7 and ref["media"] == "application/json"
    assert not list(target.parent.glob("*.tmp"))
    assert log.put_blob(b'{"a":1}', "application/json") == ref  # idempotent
    # a failing rename leaves neither the target nor a temporary file
    def boom(*_a: Any, **_k: Any) -> None:
        raise OSError("disk")

    monkeypatch.setattr(log_module.os, "replace", boom)
    with pytest.raises(OSError):
        log.put_blob(b"other", "text/plain")
    monkeypatch.undo()
    other = tmp_path / "raw" / "blobs" / "sha256"
    assert [p.name for p in other.rglob("*") if p.is_file()] == [hexdigest]


def test_event_can_only_reference_stored_blobs(tmp_path: Path) -> None:
    log = new_log(tmp_path)
    start(log)
    size = log.path.stat().st_size
    forged = {"$blob": "sha256:" + "ab" * 32, "bytes": 3, "media": "text/plain"}
    with pytest.raises(CaptureWriteError) as exc:
        log.emit("fixture", {"kind": "injection_payload", "content": forged})
    assert exc.value.code == "cap.blob.missing" and log.path.stat().st_size == size
    ref = log.put_blob(b"abc", "text/plain")
    wrong_size = {**ref, "bytes": 4}
    with pytest.raises(CaptureWriteError):
        log.emit("fixture", {"kind": "injection_payload", "content": wrong_size})
    with pytest.raises(CaptureWriteError):
        log.emit("fixture", {"kind": "injection_payload", "content": {"$blob": "md5:zz", "bytes": 3}})
    log.emit("fixture", {"kind": "injection_payload", "content": ref})


def test_blob_collision_with_different_bytes_is_refused(tmp_path: Path) -> None:
    log = new_log(tmp_path)
    start(log)
    ref = log.put_blob(b"abc", "text/plain")
    hexdigest = ref["$blob"].removeprefix("sha256:")
    (tmp_path / "raw" / "blobs" / "sha256" / hexdigest[:2] / hexdigest).write_bytes(b"tampered!")
    with pytest.raises(CaptureWriteError) as exc:
        log.put_blob(b"abc", "text/plain")
    assert exc.value.code == "cap.blob.collision"


def test_blob_argument_checks(tmp_path: Path) -> None:
    log = new_log(tmp_path)
    for data, media in (("str", "text/plain"), (b"x", ""), (b"x", None)):
        with pytest.raises(CaptureWriteError):
            log.put_blob(data, media)  # type: ignore[arg-type]


def test_concurrent_emits_keep_one_consistent_chain(tmp_path: Path) -> None:
    log = new_log(tmp_path, scripted=False)
    start(log)

    def work(n: int) -> None:
        for i in range(40):
            log.emit("note", {"kind": "k", "ns": "x", "payload": {"t": n, "i": i}})

    threads = [threading.Thread(target=work, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    log.close("complete")
    report = verify_file(log.path)
    assert report.sealed and report.n_verified == 2 + 8 * 40 + 1


def test_head_property_tracks_the_last_line(tmp_path: Path) -> None:
    log = new_log(tmp_path)
    assert log.head is None
    start(log)
    assert log.head == line_hash(split_lines(log.path.read_bytes())[-1])


# ----------------------------------------------------------------------------------------------- append_terminal


@pytest.mark.parametrize("status", ["aborted", "errored"])
def test_append_terminal_seals_an_unsealed_log(tmp_path: Path, status: str) -> None:
    log = partial_log(tmp_path)
    before = log.path.read_bytes()
    assert not verify_file(log.path).sealed
    moment = datetime(2026, 10, 7, 13, 30, 0, 250000, tzinfo=UTC)
    head = append_terminal(log.path, status, clock=lambda: moment)  # type: ignore[arg-type]
    after = log.path.read_bytes()
    assert after.startswith(before) and head == line_hash(split_lines(after)[-1])
    report = verify_file(log.path)
    assert report.sealed and report.status == status and report.appended_by == "parent" and report.head == head
    assert report.n_verified == 4
    last = strict_loads(split_lines(after)[-1][:-1])
    assert last is not None
    assert last["data"] == {"status": status, "n_events": 4, "appended_by": "parent"}
    assert last["ts"] == "2026-10-07T13:30:00.250000Z" and last["seq"] == 3 and last["pass"] is None and last["actor"] is None
    assert last["mono_ns"] == strict_loads(split_lines(before)[-1][:-1])["mono_ns"]  # type: ignore[index]


def test_append_terminal_refuses_a_sealed_log(tmp_path: Path) -> None:
    log = new_log(tmp_path)
    replay_vector(log)
    before = log.path.read_bytes()
    assert append_terminal(log.path, "errored") is None
    assert log.path.read_bytes() == before


def test_append_terminal_refuses_after_a_parent_seal(tmp_path: Path) -> None:
    log = partial_log(tmp_path)
    assert append_terminal(log.path, "aborted") is not None
    sealed = log.path.read_bytes()
    assert append_terminal(log.path, "errored") is None and log.path.read_bytes() == sealed


def test_append_terminal_refuses_a_torn_log(tmp_path: Path) -> None:
    log = partial_log(tmp_path)
    data = log.path.read_bytes()
    log.path.write_bytes(data + b'{"seq":3,"type":"no')
    assert append_terminal(log.path, "aborted") is None
    assert log.path.read_bytes() == data + b'{"seq":3,"type":"no'
    log.path.write_bytes(data[:-1])  # only the LF missing
    assert append_terminal(log.path, "aborted") is None and log.path.read_bytes() == data[:-1]


def test_append_terminal_refuses_empty_and_garbage(tmp_path: Path) -> None:
    empty = tmp_path / "e.jsonl"
    empty.write_bytes(b"")
    assert append_terminal(empty, "aborted") is None and empty.read_bytes() == b""
    garbage = tmp_path / "g.jsonl"
    garbage.write_bytes(b"this is not json\n")
    assert append_terminal(garbage, "aborted") is None and garbage.read_bytes() == b"this is not json\n"
    wrong_seq = tmp_path / "w.jsonl"
    log = partial_log(tmp_path, "w2")
    lines = split_lines(log.path.read_bytes())
    wrong_seq.write_bytes(b"".join(lines[:1] + lines[2:]))  # a line is missing: last seq != index
    assert append_terminal(wrong_seq, "aborted") is None


def test_append_terminal_rejects_other_statuses(tmp_path: Path) -> None:
    log = partial_log(tmp_path)
    with pytest.raises(ValueError):
        append_terminal(log.path, "complete")  # type: ignore[arg-type]


def test_parent_append_after_a_torn_write_leaves_the_prefix_verifiable(tmp_path: Path) -> None:
    """The crash story end to end: worker dies mid-line, the verifier reports the torn tail, the prefix maps."""
    log = partial_log(tmp_path)
    data = log.path.read_bytes()
    log.path.write_bytes(data + data.splitlines()[-1][:30])
    report = verify_file(log.path)
    assert [i.code for i in report.issues] == ["cap.chain.torn_tail", "cap.chain.unsealed"] and report.n_verified == 3


def test_every_write_descriptor_is_opened_in_binary_mode() -> None:
    """On Windows ``os.open`` defaults to text mode and ``os.write`` would turn LF into CRLF, breaking the line hashes
    and blob sizes (CI, phase 8). Every write-mode ``os.open`` in the writer must add ``_BINARY``."""
    import ast
    import inspect

    from agentprov_capture import log as log_module

    tree = ast.parse(inspect.getsource(log_module))
    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and ast.unparse(node.func) == "os.open" and "O_WRONLY" in ast.unparse(node)
    ]
    assert calls, "the writer opens files with os.open"
    for call in calls:
        assert "_BINARY" in ast.unparse(call.args[1]), ast.unparse(call)
