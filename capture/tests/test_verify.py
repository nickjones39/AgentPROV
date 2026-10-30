"""The hash-chain verifier: the C.13.8 vector and one test per tamper class (issue code and ``n_verified``)."""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from cap_support import VECTOR_HEAD, vector_lines

from agentprov_capture import verify
from agentprov_capture.errors import CaptureLogError
from agentprov_capture.verify import ISSUE_CODES, VerifyReport, line_hash, split_lines, strict_loads, verify_chain, verify_file

LINES = vector_lines()


def events_of(lines: list[bytes]) -> list[dict[str, Any] | None]:
    complete = [ln for ln in lines if ln.endswith(b"\n")]
    return [strict_loads(ln[:-1]) for ln in complete]


def run(lines: list[bytes]) -> VerifyReport:
    return verify_chain(lines, events_of(lines))


def rebuild(events: list[dict[str, Any]], *, fix_seq: bool = False) -> list[bytes]:
    """JCS lines for ``events`` with a correct ``prev`` chain (and optionally renumbered ``seq``)."""
    import rfc8785

    out: list[bytes] = []
    prev: str | None = None
    for index, event in enumerate(events):
        event = copy.deepcopy(event)
        event["prev"] = prev
        if fix_seq:
            event["seq"] = index
        line = rfc8785.dumps(event) + b"\n"
        out.append(line)
        prev = line_hash(line)
    return out


def vector_events() -> list[dict[str, Any]]:
    return [json.loads(ln) for ln in LINES]


def codes(report: VerifyReport) -> list[str]:
    return [i.code for i in report.issues]


def test_vector_verifies() -> None:
    report = run(LINES)
    assert report.sealed and report.issues == () and report.n_verified == 13
    assert report.head == VECTOR_HEAD and report.status == "complete" and report.appended_by == "worker"


def test_issue_codes_are_a_closed_documented_set() -> None:
    assert len(set(ISSUE_CODES)) == len(ISSUE_CODES) == 17
    assert all(code.startswith("cap.chain.") for code in ISSUE_CODES)
    doc = verify.__doc__ or ""
    assert all(code in doc for code in ISSUE_CODES)


def test_empty_log() -> None:
    report = verify_chain([], [])
    assert codes(report) == ["cap.chain.empty"] and not report.sealed and report.n_verified == 0 and report.head is None


def test_flipped_byte_that_keeps_the_line_valid_is_found_by_the_next_line() -> None:
    lines = list(LINES)
    assert b"12:00:05.000000Z" in lines[5]
    lines[5] = lines[5].replace(b"12:00:05.000000Z", b"12:00:06.000000Z")
    report = run(lines)
    assert codes(report) == ["cap.chain.prev_mismatch"]
    assert report.issues[0].seq == 6
    assert report.n_verified == 5 and report.head == line_hash(lines[4]) and not report.sealed


def test_flipped_byte_that_breaks_the_line() -> None:
    lines = list(LINES)
    lines[5] = lines[5][:20] + bytes([lines[5][20] ^ 0x01]) + lines[5][21:]
    report = run(lines)
    assert report.issues[0].seq == 5 and report.issues[0].code in ISSUE_CODES  # which code depends on the byte hit
    assert report.n_verified == 5 and not report.sealed


def test_flip_in_the_prev_member_itself() -> None:
    lines = list(LINES)
    original = line_hash(lines[7])
    flipped = ("0" if original[0] != "0" else "1") + original[1:]
    lines[8] = lines[8].replace(original.encode(), flipped.encode())
    report = run(lines)
    assert codes(report) == ["cap.chain.prev_mismatch"] and report.issues[0].seq == 8 and report.n_verified == 7


def test_removed_line() -> None:
    lines = LINES[:5] + LINES[6:]
    report = run(lines)
    assert codes(report) == ["cap.chain.seq_gap"] and report.issues[0].seq == 5
    assert report.n_verified == 5 and report.head == line_hash(LINES[4]) and not report.sealed


def test_reordered_lines() -> None:
    lines = list(LINES)
    lines[5], lines[6] = lines[6], lines[5]
    report = run(lines)
    assert codes(report) == ["cap.chain.seq_gap"] and report.issues[0].seq == 5 and report.n_verified == 5


def test_duplicated_line() -> None:
    lines = LINES[:6] + [LINES[5]] + LINES[6:]
    report = run(lines)
    assert codes(report) == ["cap.chain.seq_gap"] and report.issues[0].seq == 6 and report.n_verified == 6


def test_torn_tail_mid_line() -> None:
    lines = LINES[:12] + [LINES[12][:40]]
    report = run(lines)
    assert codes(report) == ["cap.chain.torn_tail", "cap.chain.unsealed"]
    assert report.issues[0].seq == 12 and report.issues[1].seq is None
    assert report.n_verified == 12 and report.head == line_hash(LINES[11]) and not report.sealed
    assert report.status is None


def test_torn_tail_missing_only_the_lf() -> None:
    lines = LINES[:12] + [LINES[12][:-1]]
    report = run(lines)
    assert codes(report) == ["cap.chain.torn_tail", "cap.chain.unsealed"] and report.n_verified == 12


def test_missing_session_end_is_unsealed_but_fully_verified() -> None:
    report = run(LINES[:12])
    assert codes(report) == ["cap.chain.unsealed"] and report.n_verified == 12
    assert report.head == line_hash(LINES[11]) and not report.sealed and report.status is None


def test_log_of_one_event_is_unsealed() -> None:
    assert codes(run(LINES[:1])) == ["cap.chain.unsealed"] and run(LINES[:1]).n_verified == 1


def test_non_jcs_line() -> None:
    lines = list(LINES)
    lines[3] = (json.dumps(json.loads(lines[3])) + "\n").encode()  # spaces after separators: valid JSON, not JCS
    report = run(lines)
    assert codes(report) == ["cap.chain.not_jcs"] and report.issues[0].seq == 3 and report.n_verified == 3


def test_unsorted_members_are_not_jcs() -> None:
    lines = list(LINES)
    event = json.loads(lines[3])
    lines[3] = (json.dumps({"seq": event["seq"], **event}, separators=(",", ":")) + "\n").encode()
    assert codes(run(lines)) == ["cap.chain.not_jcs"]


def test_wrong_n_events() -> None:
    events = vector_events()
    events[12]["data"]["n_events"] = 14
    report = run(rebuild(events))
    assert codes(report) == ["cap.chain.n_events_mismatch"] and report.issues[0].seq == 12
    assert report.n_verified == 12 and not report.sealed and report.status is None


def test_extra_line_after_session_end() -> None:
    events = vector_events()
    events.append({**events[9], "seq": 13, "type": "note", "data": {"kind": "k", "ns": "x", "payload": {}}})
    report = run(rebuild(events))
    assert codes(report) == ["cap.chain.after_end"] and report.issues[0].seq == 13
    assert report.n_verified == 13 and report.head == line_hash(LINES[12]) and not report.sealed


def test_torn_bytes_after_session_end() -> None:
    report = run([*LINES, b'{"seq":13'])
    assert codes(report) == ["cap.chain.after_end"] and report.n_verified == 13 and not report.sealed


def test_undeclared_actor() -> None:
    events = vector_events()
    events[4]["actor"] = "ghost"
    report = run(rebuild(events))
    assert codes(report) == ["cap.chain.undeclared_actor"] and report.issues[0].seq == 4 and report.n_verified == 4


def test_declared_actor_is_accepted() -> None:
    events = vector_events()
    events[4]["actor"] = "env"
    assert run(rebuild(events)).sealed


def test_first_event_must_be_session_start() -> None:
    events = vector_events()[1:]
    report = run(rebuild(events, fix_seq=True))
    assert codes(report) == ["cap.chain.bad_first_event"] and report.n_verified == 0 and report.head is None


def test_second_event_must_be_instrumentation() -> None:
    events = vector_events()
    del events[1]
    report = run(rebuild(events, fix_seq=True))
    assert codes(report) == ["cap.chain.bad_second_event"] and report.issues[0].seq == 1 and report.n_verified == 1


def test_session_start_and_instrumentation_only_at_their_place() -> None:
    events = vector_events()
    events.insert(3, copy.deepcopy(events[0]))
    assert codes(run(rebuild(events, fix_seq=True))) == ["cap.chain.misplaced_event"]
    events = vector_events()
    events.insert(3, copy.deepcopy(events[1]))
    assert codes(run(rebuild(events, fix_seq=True))) == ["cap.chain.misplaced_event"]


def test_session_start_needs_capture_version_and_actors() -> None:
    events = vector_events()
    events[0]["data"]["capture"] = "0.2"
    assert codes(run(rebuild(events))) == ["cap.chain.bad_session_start"]
    events = vector_events()
    events[0]["data"]["actors"] = {}
    assert codes(run(rebuild(events))) == ["cap.chain.bad_session_start"]


@pytest.mark.parametrize(
    "mutate, code",
    [
        (lambda e: e.__setitem__("pass_no", 0), "cap.chain.bad_envelope"),
        (lambda e: (e.pop("mono_ns"), e.__setitem__("monotonic_ns", 1)), "cap.chain.bad_envelope"),
        (lambda e: e.__setitem__("ts", "2026-10-07T12:00:03Z"), "cap.chain.bad_envelope"),
        (lambda e: e.__setitem__("ts", "2026-10-07T12:00:03.000000+00:00"), "cap.chain.bad_envelope"),
        (lambda e: e.__setitem__("mono_ns", -1), "cap.chain.bad_envelope"),
        (lambda e: e.__setitem__("pass", "0"), "cap.chain.bad_envelope"),
        (lambda e: e.__setitem__("actor", "Agent"), "cap.chain.bad_envelope"),
        (lambda e: e.__setitem__("seq", True), "cap.chain.bad_envelope"),
        (lambda e: e.__setitem__("data", []), "cap.chain.bad_envelope"),
        (lambda e: e.__setitem__("type", "llm.exchange"), "cap.chain.bad_type"),
        (lambda e: e.__setitem__("type", "llm.span"), "cap.chain.bad_type"),
        (lambda e: e.__setitem__("type", "exception"), "cap.chain.bad_type"),
        (lambda e: e.__setitem__("type", "artefact"), "cap.chain.bad_type"),
    ],
)
def test_rejected_envelope_forms(mutate: Callable[[dict[str, Any]], object], code: str) -> None:
    events = vector_events()
    mutate(events[3])
    report = run(rebuild(events))
    assert codes(report) == [code] and report.issues[0].seq == 3 and report.n_verified == 3


def test_prev_of_the_first_event_must_be_null() -> None:
    import rfc8785

    event = vector_events()[0]
    event["prev"] = "0" * 64
    report = run([rfc8785.dumps(event) + b"\n"])
    assert codes(report) == ["cap.chain.prev_mismatch"] and report.n_verified == 0


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.pop("status"),
        lambda d: d.__setitem__("status", "completed"),
        lambda d: d.__setitem__("completed", True),
        lambda d: d.__setitem__("by", "worker"),
        lambda d: d.__setitem__("appended_by", "somebody"),
        lambda d: d.__setitem__("n_events", "13"),
        lambda d: d.update(appended_by="parent", status="complete"),
        lambda d: d.update(appended_by="parent", status="incomplete"),
    ],
)
def test_bad_session_end(mutate: Callable[[dict[str, Any]], object]) -> None:
    events = vector_events()
    mutate(events[12]["data"])
    report = run(rebuild(events))
    assert codes(report) == ["cap.chain.bad_session_end"] and report.n_verified == 12 and not report.sealed


def test_parent_appended_session_end_is_sealed() -> None:
    events = vector_events()
    events[12]["data"] = {"status": "aborted", "n_events": 13, "appended_by": "parent"}
    report = run(rebuild(events))
    assert report.sealed and report.status == "aborted" and report.appended_by == "parent"


def test_unparsed_complete_line_is_bad_json() -> None:
    events = events_of(LINES)
    events[4] = None
    report = verify_chain(LINES, events)
    assert codes(report) == ["cap.chain.bad_json"] and report.issues[0].seq == 4 and report.n_verified == 4


def test_misaligned_arguments_are_a_caller_bug() -> None:
    with pytest.raises(ValueError):
        verify_chain(LINES, events_of(LINES)[:-1])
    with pytest.raises(ValueError):
        verify_chain([b"a", b"b\n"], [None])  # only the last line may lack its LF


# ------------------------------------------------------------------------------------------ verify_file / parser


def test_split_lines_splits_on_lf_only() -> None:
    data = b'{"a":"\xe2\x80\xa8"}\n{"b":1}\r\n{"c"'
    lines = split_lines(data)
    assert lines == [b'{"a":"\xe2\x80\xa8"}\n', b'{"b":1}\r\n', b'{"c"']
    assert split_lines(b"") == [] and split_lines(b"x\n") == [b"x\n"]


@pytest.mark.parametrize(
    "line",
    [
        b'{"a":1,"a":2}',  # duplicate key
        b'{"a":NaN}',
        b'{"a":Infinity}',
        b'{"a":1e999}',
        b'{"a":"\\ud800"}',  # lone surrogate
        b'{"\\udc00":1}',
        b"\xef\xbb\xbf{}",  # BOM
        b'{"a":"\xff"}',  # invalid UTF-8
        b"[1]",  # not an object
        b'{"a":' + b"[" * 100_000 + b"]" * 100_000 + b"}",  # nesting
        b"",
    ],
)
def test_strict_parser_rejects(line: bytes) -> None:
    assert strict_loads(line) is None


def test_strict_parser_bounds_nesting_without_relying_on_recursion() -> None:
    # The object itself is depth 1: 255 nested lists reach 256 (accepted), 256 reach 257 (rejected), on every platform.
    assert strict_loads(b'{"a":' + b"[" * 255 + b"]" * 255 + b"}") is not None
    assert strict_loads(b'{"a":' + b"[" * 256 + b"]" * 256 + b"}") is None
    assert strict_loads(b'{"a":"' + b"[" * 1000 + b'"}') == {"a": "[" * 1000}  # brackets in strings do not count


def test_strict_parser_accepts_paired_surrogates_and_unicode() -> None:
    assert strict_loads(b'{"a":"\\ud83d\\ude00 \xc3\xa9"}') == {"a": "\U0001f600 é"}


def test_verify_file_reports_strictness_failures_as_bad_json(tmp_path: Path) -> None:
    lines = list(LINES)
    lines[2] = b'{"seq":2,"seq":2}\n'
    path = tmp_path / "x.jsonl"
    path.write_bytes(b"".join(lines))
    report = verify_file(path)
    assert codes(report) == ["cap.chain.bad_json"] and report.n_verified == 2


def test_verify_file_max_bytes(tmp_path: Path) -> None:
    path = tmp_path / "x.jsonl"
    path.write_bytes(b"".join(LINES))
    assert verify_file(path, max_bytes=path.stat().st_size).sealed
    with pytest.raises(CaptureLogError) as exc:
        verify_file(path, max_bytes=path.stat().st_size - 1)
    assert exc.value.code == "cap.verify.too_large"


def test_verifier_never_parses_json_itself() -> None:
    import ast

    tree = ast.parse(Path(verify.__file__).read_text(encoding="utf-8"))
    func = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "verify_chain")
    names = {n.attr for n in ast.walk(func) if isinstance(n, ast.Attribute)} | {
        n.id for n in ast.walk(func) if isinstance(n, ast.Name)
    }
    assert "loads" not in names and "json" not in names
