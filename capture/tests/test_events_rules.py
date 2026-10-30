"""The event model (vocabulary, envelope, rejected names), the `cap` rule catalogue as data, and package data."""

from __future__ import annotations

import re
import tomllib
from datetime import UTC, datetime, timedelta, timezone
from importlib import resources
from typing import Any

import pytest

from agentprov_capture import events, redact, verify

TYPES = [
    "session.start", "instrumentation", "identity", "fixture", "pass.start", "llm.request", "llm.response",
    "tool.dispatch", "tool.result", "decision", "state", "pass.end", "outcome", "native.log", "note", "error", "session.end",
]


def test_vocabulary_is_the_seventeen_names_of_c13_3() -> None:
    assert list(events.EVENT_TYPES) == TYPES
    assert set(events.DATA_MEMBERS) == set(TYPES)
    for rejected in ("llm.exchange", "llm.span", "exception", "artefact", "completed"):
        assert rejected not in events.EVENT_TYPES and events.data_problem(rejected, {}) is not None
    assert events.SESSION_STATUSES == ("complete", "incomplete", "errored", "aborted")
    assert events.APPENDED_BY == ("worker", "parent")


def test_every_type_allows_redactions_and_requires_the_documented_members() -> None:
    for name, (required, optional) in events.DATA_MEMBERS.items():
        assert "redactions" in optional and not required & optional, name
    assert events.DATA_MEMBERS["llm.request"][0] == {"attempt", "call", "endpoint", "params", "request", "role"}
    assert events.DATA_MEMBERS["session.end"][0] == {"appended_by", "n_events", "status"}
    assert "n_messages" in events.DATA_MEMBERS["llm.request"][1] and "input_at" in events.DATA_MEMBERS["llm.request"][1]
    assert "plan_sha256" not in events.DATA_MEMBERS["session.start"][0] | events.DATA_MEMBERS["session.start"][1]


def good_event(**over: Any) -> dict[str, Any]:
    event: dict[str, Any] = {
        "seq": 1, "type": "note", "ts": "2026-10-07T12:00:00.000000Z", "mono_ns": 0, "pass": None, "actor": None,
        "prev": "a" * 64, "data": {},
    }
    event.update(over)
    return event


def test_envelope_accepts_the_canonical_shape_and_optional_lex() -> None:
    assert events.envelope_problem(good_event()) is None
    assert events.envelope_problem(good_event(lex={"flt": ["/x"]})) is None
    assert events.envelope_problem(good_event(seq=0, prev=None)) is None


@pytest.mark.parametrize(
    "event",
    [
        good_event(seq=0),  # prev must be null at seq 0
        good_event(prev=None),
        good_event(prev="A" * 64),
        good_event(prev="a" * 63),
        good_event(ts="2026-10-07T12:00:00Z"),
        good_event(ts="2026-10-07T12:00:00.0Z"),
        good_event(ts="2026-10-07T12:00:00.000000+00:00"),
        good_event(ts="2026-13-07T12:00:00.000000Z"),
        good_event(mono_ns=-1),
        good_event(mono_ns=1.0),
        good_event(mono_ns=True),
        good_event(seq=-1),
        good_event(seq=1.0),
        good_event(**{"pass": -1}),
        good_event(**{"pass": "0"}),
        good_event(actor="Agent"),
        good_event(actor=""),
        good_event(type="llm.exchange"),
        good_event(data=None),
        good_event(lex=[]),
        {**good_event(), "pass_no": 0},
        {**good_event(), "monotonic_ns": 1},
        {k: v for k, v in good_event().items() if k != "prev"},
        "not an object",
    ],
)
def test_envelope_rejections(event: Any) -> None:
    assert events.envelope_problem(event) is not None


def test_pass_no_and_monotonic_ns_are_not_envelope_members() -> None:
    assert "pass_no" not in events.ENVELOPE_FIELDS and "monotonic_ns" not in events.ENVELOPE_FIELDS
    assert events.ENVELOPE_FIELDS == {"seq", "type", "ts", "mono_ns", "pass", "actor", "prev", "data"}


@pytest.mark.parametrize("member", ["completed", "by", "accounting"])
def test_session_end_rejects_pre_review_members(member: str) -> None:
    data = {"status": "complete", "n_events": 3, "appended_by": "worker", member: True}
    assert events.data_problem("session.end", data) is not None
    assert events.data_problem("session.end", {"status": "complete", "n_events": 3, "appended_by": "worker"}) is None


def test_session_end_value_checks() -> None:
    base = {"status": "complete", "n_events": 3, "appended_by": "worker"}
    for bad in ({"status": "completed"}, {"appended_by": "by"}, {"n_events": 0}, {"n_events": True}, {"n_events": "3"}):
        assert events.data_problem("session.end", {**base, **bad}) is not None


def test_format_ts() -> None:
    assert events.format_ts(datetime(2026, 10, 7, 12, 0, 0, tzinfo=UTC)) == "2026-10-07T12:00:00.000000Z"
    assert events.format_ts(datetime(2026, 10, 7, 14, 0, 0, 7, tzinfo=timezone(timedelta(hours=2)))) == "2026-10-07T12:00:00.000007Z"
    with pytest.raises(ValueError):
        events.format_ts(datetime(2026, 10, 7))
    assert events.TS_RE.fullmatch(events.format_ts(datetime.now(UTC)))


# ------------------------------------------------------------------------------------------------ the cap catalogue


def catalogue() -> dict[str, Any]:
    raw = resources.files("agentprov_capture").joinpath("rules", "cap.rules.toml").read_bytes()
    return tomllib.loads(raw.decode("utf-8"))


RULE_NAME = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+")


def test_cap_catalogue_header_and_rules() -> None:
    doc = catalogue()
    head = doc["catalogue"]
    assert head["id"] == "cap" and head["version"] == 1 and head["format"] == "agentprov-rule-catalogue/0.1"
    ids = [(r["id"], r["version"]) for r in doc["rule"]]
    assert len(set(ids)) == len(ids)
    assert ("cap.context_alignment", 1) in ids
    for rule in doc["rule"]:
        assert RULE_NAME.fullmatch(rule["id"]) and rule["id"].startswith("cap.")
        assert rule["class"] == "D" and rule["status"] == "active" and rule["assumptions"] == []
        assert rule["statement"].strip()


def test_redaction_rules_are_exactly_the_redactor_kinds() -> None:
    names = {r["id"] for r in catalogue()["rule"] if r["id"].startswith("cap.secret.")}
    assert names == {f"cap.secret.{k}" for k in redact.KINDS}
    for kind in redact.KINDS:
        assert re.fullmatch(r"cap\.secret\.[a-z][a-z0-9_]*@[1-9][0-9]*", redact.rule_id(kind))
    with pytest.raises(ValueError):
        redact.rule_id("nope")


def test_issue_codes_are_the_verifier_codes() -> None:
    declared = {f"cap.{c}" for c in catalogue()["catalogue"]["issue_codes"]}
    assert declared == set(verify.ISSUE_CODES)


def test_package_data_is_reachable_through_importlib_resources() -> None:
    root = resources.files("agentprov_capture")
    for name in ("endpoints.toml", "redact_allowlist.toml", "rules/cap.rules.toml", "py.typed"):
        node = root.joinpath(*name.split("/"))
        assert node.is_file() and node.read_bytes() is not None, name
