"""The published JSON Schema ``schemas/capture-0.1.schema.json`` (C.13, MN M.1.x; frozen at phase 6, AD-06).

Freshness against the builder, validity as Draft 2020-12, the C.13.8 synthetic vector (every event validates, the
lines are JCS, the hash chain and ``n_events`` verify, and the file digest and chain head are the published ones), and
fixed negative cases for the closed envelope and closed per-type data.
"""

from __future__ import annotations

import copy
import hashlib
import json
from importlib import resources
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from capture_schema_builder import EVENT_TYPES, OUT, render

from agentprov.aer.canon import dumps_line, loads_strict

VECTOR = Path(__file__).resolve().parents[3] / "docs" / "architecture" / "examples" / "C" / "synthetic.capture.jsonl"
VECTOR_SHA256 = "0e22300b8729440fea35f5d8271d82ea0916431493cd6ec315e4d0d045990add"
VECTOR_HEAD = "c6c44c6c4b0fe31667b6c58aa8dc31e26f5c2aaf89cb3aa3c354e2d7d5442437"


def load_schema() -> dict[str, Any]:
    data = resources.files("agentprov").joinpath("schemas/capture-0.1.schema.json").read_bytes()
    return json.loads(data)  # type: ignore[no-any-return]


SCHEMA = load_schema()
VALIDATOR = jsonschema.Draft202012Validator(SCHEMA)
LINES = VECTOR.read_bytes().splitlines(keepends=True)
EVENTS = [loads_strict(line.rstrip(b"\n")) for line in LINES]


def by_type(name: str) -> dict[str, Any]:
    return copy.deepcopy(next(e for e in EVENTS if e["type"] == name))  # type: ignore[index]


def test_committed_schema_is_exactly_the_builder_output() -> None:
    assert OUT.read_text(encoding="utf-8") == render()


def test_schema_is_a_valid_draft_2020_12_schema_with_a_stable_id() -> None:
    jsonschema.Draft202012Validator.check_schema(SCHEMA)
    assert SCHEMA["$id"] == "https://w3id.org/agentprov/schemas/capture-0.1.schema.json"
    assert tuple(sorted(SCHEMA["properties"]["type"]["enum"])) == tuple(sorted(EVENT_TYPES))
    assert len(EVENT_TYPES) == 17


def test_vector_file_is_the_published_one() -> None:
    assert hashlib.sha256(VECTOR.read_bytes()).hexdigest() == VECTOR_SHA256
    assert len(LINES) == 13


@pytest.mark.parametrize("index", range(13))
def test_every_vector_event_validates(index: int) -> None:
    errors = sorted(VALIDATOR.iter_errors(EVENTS[index]), key=str)
    assert not errors, [e.message for e in errors]


def test_vector_lines_are_jcs_and_the_chain_verifies() -> None:
    prev = None
    for seq, (line, event) in enumerate(zip(LINES, EVENTS, strict=True)):
        assert dumps_line(event) == line  # JCS + LF (C.13.2)
        assert event["seq"] == seq and event["prev"] == prev  # type: ignore[index]
        prev = hashlib.sha256(line).hexdigest()
    assert prev == VECTOR_HEAD
    first, last = EVENTS[0], EVENTS[-1]
    assert first["type"] == "session.start" and EVENTS[1]["type"] == "instrumentation"  # type: ignore[index]
    assert last["type"] == "session.end" and last["data"]["n_events"] == len(LINES)  # type: ignore[index]


def test_every_event_type_has_closed_data() -> None:
    for name in EVENT_TYPES:
        schema = SCHEMA["$defs"]["data_" + name.replace(".", "_")]
        assert schema["additionalProperties"] is False, name
        assert "redactions" in schema["properties"], name


def _invalid(event: dict[str, Any]) -> bool:
    return not VALIDATOR.is_valid(event)


def test_closed_envelope() -> None:
    event = by_type("outcome")
    event["extra"] = 1
    assert _invalid(event)
    for name in ("seq", "type", "ts", "mono_ns", "pass", "actor", "prev", "data"):
        event = by_type("outcome")
        del event[name]
        assert _invalid(event), name


def test_envelope_values() -> None:
    cases = [
        ("type", "llm.stream"),          # new event types wait for capture/0.2
        ("ts", "2026-10-07T12:00:11Z"),  # microseconds are required
        ("ts", "2026-10-07T12:00:11.000000+00:00"),
        ("mono_ns", -1),
        ("prev", None),                  # only seq 0 has a null prev
        ("prev", "ABC"),
        ("actor", "Agent"),
    ]
    for field, value in cases:
        event = by_type("outcome")
        event[field] = value
        assert _invalid(event), (field, value)
    first = by_type("session.start")
    first["prev"] = "0" * 64
    assert _invalid(first)


def test_closed_data_and_required_members() -> None:
    event = by_type("llm.request")
    event["data"]["plan_sha256"] = "0" * 64
    assert _invalid(event)
    event = by_type("session.start")
    event["data"]["mode"] = "test"  # removed at review: test sessions use the test_only instrumentation item
    assert _invalid(event)
    event = by_type("session.end")
    event["data"]["accounting"] = {}  # the log carries no accounting (C.12.4)
    assert _invalid(event)
    event = by_type("tool.dispatch")
    del event["data"]["occ"]
    assert _invalid(event)


def test_enumerations() -> None:
    event = by_type("session.end")
    event["data"]["status"] = "done"
    assert _invalid(event)
    event = by_type("llm.response")
    event["data"]["status"] = "retried"
    assert _invalid(event)
    event = by_type("tool.result")
    event["data"]["status"] = "denied"  # denied needs decided_by
    assert _invalid(event)
    event["data"]["decided_by"] = "def0"
    assert not _invalid(event)
    event = by_type("tool.result")
    event["data"]["decided_by"] = "def0"  # only for denied
    assert _invalid(event)


def test_blob_references() -> None:
    event = by_type("llm.request")
    event["data"]["request"]["$blob"] = "md5:abc"
    assert _invalid(event)
    event = by_type("pass.end")
    del event["data"]["messages"]["bytes"]
    assert _invalid(event)


def test_redactions_shape() -> None:
    event = by_type("llm.request")
    event["data"]["redactions"] = [{"blob": event["data"]["request"]["$blob"], "p": "/headers/x", "rule":
                                    "cap.secret.env_value@1"}]
    assert not _invalid(event)
    event["data"]["redactions"] = [{"p": "/x", "rule": "cap.secret.env_value@1"}]  # neither blob nor field
    assert _invalid(event)
    event["data"]["redactions"] = [{"field": "/x", "p": "/x", "rule": "aer.secret@1"}]
    assert _invalid(event)


def test_decision_subject_and_escape() -> None:
    base = {"actor": "def0", "subject": {"occ": "o0"}, "verdict": "deny"}
    event = by_type("outcome")
    event["type"], event["data"] = "decision", dict(base)
    assert not _invalid(event)
    event["data"] = {**base, "subject": {"occ": "o0", "call": "c0"}}
    assert _invalid(event)
    event["data"] = {**base, "verdict": "other"}
    assert _invalid(event)  # other needs a declared subtype
    event["data"] = {**base, "verdict": "other", "subtype": "x.quarantine"}
    assert not _invalid(event)
