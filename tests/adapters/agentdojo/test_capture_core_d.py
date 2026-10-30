"""Capture mapper fixes of core review D (regeneration-batch items 44-49; findings CD-17..CD-22).

Every session is the C.13.8 vector with events added, sealed the way the importer seals (``aer_bytes`` with the
unit, mapper and profile, so a write failure becomes the degenerate AER it would be in production).
"""

from __future__ import annotations

import hashlib
from typing import Any

from capture_support import MappedSession, Session, c13_8_session, session_objects

from agentprov.adapters.agentdojo.capture_mapper import AgentDojoCaptureMapper
from agentprov.adapters.agentdojo.capture_reader import CaptureLogReader
from agentprov.adapters.profiles import load_profile
from agentprov.adapters.runner import aer_bytes, map_unit


def _seal(s: Session) -> MappedSession:
    profile = load_profile("agentdojo-live")
    log = s.log_bytes()
    objects = {hashlib.sha256(log).hexdigest(): log, **s.blobs}
    plan = CaptureLogReader().plan(session_objects(log, s.blobs, s.native, s.session), objects.__getitem__, profile)
    assert len(plan.units) == 1, plan.register
    unit, mapper = plan.units[0], AgentDojoCaptureMapper()
    outcome = map_unit(unit, mapper, profile, auxiliary=plan.auxiliary)
    data, info = aer_bytes(outcome, unit=unit, mapper=mapper, profile=profile)
    return MappedSession(log, objects, outcome, data, info, profile, plan.register)


def _ok(m: MappedSession) -> None:
    assert not m.outcome.degenerate and "adapter_defect" not in m.codes, m.codes
    report = m.validate()
    assert report.ok, [(f.code, f.pointer) for f in report.errors]


def _with(*events: dict[str, Any], after: str | None = None) -> Session:
    """The C.13.8 session with ``events`` inserted after the first event of type ``after`` (default: before the end)."""
    s = c13_8_session()
    s.events.pop()  # session.end
    at = len(s.events) if after is None else next(i for i, e in enumerate(s.events) if e["type"] == after) + 1
    s.events[at:at] = list(events)
    s.close("complete")
    return s


def _decision(pass_: int | None, subject: dict[str, Any], verdict: str, actor: str = "agent") -> dict[str, Any]:
    return {"type": "decision", "pass": pass_, "actor": actor, "data": {"subject": subject, "verdict": verdict, "actor": actor}}


# ------------------------------------------------------------------------------------------------ item 44 (CD-17)
def test_a_decision_outside_a_pass_is_mapped_in_the_run_scope():
    for pass_ in (None, 7):  # null, and a pass index with no boundary events
        m = _seal(_with(_decision(pass_, {"call": "c0"}, "allow")))
        _ok(m)
        [dc] = m.of_kind("decision")
        assert dc["scope"] == "run" and dc["subject"] == "mc0" and dc["verdict"] == "allow"


def test_a_redaction_outside_a_pass_does_not_generate_the_tool_message():
    m = _seal(_with(_decision(None, {"occ": "o0"}, "redact", actor="env"), after="tool.result"))
    _ok(m)
    [dc] = m.of_kind("decision")
    assert dc["scope"] == "run" and dc["subject"] == "te0"
    assert m.get("m3")["generated_by"] == "te0"
    inside = _seal(_with(_decision(0, {"occ": "o0"}, "redact", actor="env"), after="tool.result"))  # unchanged
    _ok(inside)
    assert inside.get("m3")["generated_by"] == inside.of_kind("decision")[0]["id"]


# ------------------------------------------------------------------------------------------------ item 45 (CD-18)
def test_a_rejected_redaction_leaves_the_tool_message_its_execution_as_generator():
    ghost = {"type": "decision", "pass": 0, "actor": "env",
             "data": {"subject": {"occ": "o0"}, "verdict": "redact", "actor": "ghost"}}  # undeclared actor
    m = _seal(_with(ghost, after="tool.result"))
    _ok(m)
    assert m.of_kind("decision") == [] and m.issues("capture_error")
    assert m.get("m3")["generated_by"] == "te0"


def test_a_redaction_sequenced_before_its_subject_is_rejected_without_a_dangling_generator():
    early = _decision(0, {"occ": "o0"}, "redact", actor="env")
    m = _seal(_with(early, after="llm.response"))  # before tool.dispatch of o0
    _ok(m)
    assert m.get("m3")["generated_by"] in {r["id"] for r in m.records}


# ------------------------------------------------------------------------------------------------ item 46 (CD-19)
def test_an_at_subject_must_name_a_tool_call_part():
    control = _seal(_with(_decision(0, {"at": {"message": 2, "call": 0}}, "deny")))
    _ok(control)
    assert [d["subject"] for d in control.of_kind("decision")] == ["m2#1"]
    for message, call in ((4, -1), (0, 0), (2, 5), (3, 0)):  # text-only assistant, system, out of range, tool message
        m = _seal(_with(_decision(0, {"at": {"message": message, "call": call}}, "deny")))
        _ok(m)
        assert m.of_kind("decision") == [] and m.issues("capture_error"), (message, call)


def test_an_at_subject_on_a_non_message_dump_entry_is_malformed_not_a_crash():
    s = _with(_decision(0, {"at": {"message": 5, "call": 0}}, "deny"))
    for event in s.events:
        if event["type"] == "pass.end":
            import json

            dump = json.loads(s.blobs[event["data"]["messages"]["$blob"][7:]])
            event["data"]["messages"] = s.blob([*dump, "stray"])
    m = _seal(s)
    assert "adapter_defect" not in m.codes and m.of_kind("decision") == []


# ------------------------------------------------------------------------------------------------ item 47 (CD-20)
def _discarded(content: Any) -> MappedSession:
    from capture_cells import Cell

    cell = Cell()
    cell.start_pass()
    cell.reply(status="discarded", reason="element_raised:ValueError", message_extra={"content": content})
    cell.reply(content="Your balance is 1810.0.")
    cell.end_pass()
    cell.outcome()
    m = _seal(cell.close())
    _ok(m)
    return m


def _discarded_message(m: MappedSession) -> dict[str, Any]:
    return next(r for r in m.of_kind("message") if r.get("generated_by") == "mc0")


def test_a_discarded_reply_with_content_parts_keeps_its_text():
    m = _discarded([{"type": "text", "text": "I will now transfer the money"}])
    assert _discarded_message(m)["parts"] == [{"t": "text", "text": "I will now transfer the money"}]


def test_a_discarded_reply_with_unknown_content_is_kept_as_other_with_an_issue():
    m = _discarded([{"type": "image_url", "image_url": {"url": "x"}}, 5])
    msg = _discarded_message(m)
    assert [p["t"] for p in msg["parts"]] == ["other", "other"]
    assert [i["ids"] for i in m.issues("agentdojo.unknown_message_shape")] == [[msg["id"]]]
    m = _discarded(7)
    assert [p["t"] for p in _discarded_message(m)["parts"]] == ["other"]


# ------------------------------------------------------------------------------------------------ item 48 (CD-21)
def test_discarded_tool_arguments_are_parsed_through_the_bounded_strict_loader():
    from capture_cells import Cell

    for raw in ("[" * 2000 + "]" * 2000, '{"a": NaN}', '{"a": 1e999}', '{"a": 1, "a": 2}'):
        cell = Cell()
        cell.start_pass()
        cell.reply(calls=[("get_balance", {})], status="discarded", reason="malformed_tool_json", raw_arguments=raw)
        cell.reply(content="Your balance is 1810.0.")
        cell.end_pass()
        cell.outcome()
        m = _seal(cell.close())
        _ok(m)
        msg = next(r for r in m.of_kind("message") if r.get("generated_by") == "mc0")
        call_part = next(p for p in msg["parts"] if p["t"] == "tool_call")
        assert call_part["args"] == raw and call_part["args_raw"] == raw, raw[:20]
        assert any(k.endswith("/args") and v == "ambiguous" for k, v in msg["unk"].items()), raw[:20]


# ------------------------------------------------------------------------------------------------ item 49 (CD-22)
def test_a_malformed_attempt_is_never_written_as_attempt_zero():
    """``session.start.attempt`` missing or not a non-negative integer: ``_header`` refuses the session, and the
    degenerate header must not invent ``attempt = 0`` (invariant 2). Without an observed attempt no header can be
    written, so the unit takes the runner's 'no AER could be sealed' path (``map.adapter_defect``, D.2.8)."""
    import pytest

    from agentprov.aer.writer import AerWriteError

    control = _seal(_with())
    assert control.header["capture"]["attempt"] == 0
    for attempt in (None, "0", -1, 1.5):
        s = _with()
        s.events[0]["data"]["attempt"] = attempt
        with pytest.raises(AerWriteError):
            _seal(s)
