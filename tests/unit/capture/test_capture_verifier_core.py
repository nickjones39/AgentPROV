"""The core side of `agentprov-capture` (a uv workspace member of the core environment): the C.13.8 vector parsed with
the core's strict loader and fed to ``verify_chain``; everything the writer produces validates against the published
schema; ``DATA_MEMBERS`` is pinned to that schema; the ``cap`` catalogue loads through the core's loader."""

from __future__ import annotations

import io
import json
from importlib import resources
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from cap_support import (
    CELL,
    ENDPOINT,
    ENV_DIGEST,
    VECTOR_HEAD,
    VECTOR_PATH,
    new_log,
    replay_vector,
    start,
)

from agentprov.aer.canon import loads_strict
from agentprov.aer.rules import load_catalogue, parse_catalogue
from agentprov.errors import IngestError
from agentprov.ingest.loaders import iter_jsonl, strict_json_loads
from agentprov_capture import events, redact, verify
from agentprov_capture.log import CaptureLog, append_terminal
from agentprov_capture.redact import Redactor, Secret
from agentprov_capture.verify import split_lines, verify_chain

SCHEMA = json.loads(resources.files("agentprov").joinpath("schemas/capture-0.1.schema.json").read_bytes())
VALIDATOR = jsonschema.Draft202012Validator(SCHEMA)


def core_events(lines: list[bytes]) -> list[Any]:
    """Parse the complete lines the way core does: the strict ingest loader, one record per line."""
    return [strict_json_loads(line[:-1], record=True) for line in lines if line.endswith(b"\n")]


def test_vector_parsed_by_the_core_loader_verifies() -> None:
    lines = split_lines(VECTOR_PATH.read_bytes())
    report = verify_chain(lines, core_events(lines))
    assert report.sealed and report.issues == () and report.n_verified == 13
    assert report.head == VECTOR_HEAD and report.status == "complete" and report.appended_by == "worker"


def test_core_jsonl_iterator_and_verifier_agree() -> None:
    data = VECTOR_PATH.read_bytes()
    parsed = [value for _n, _off, value in iter_jsonl(io.BytesIO(data))]
    lines = split_lines(data)
    assert parsed == core_events(lines)
    assert verify_chain(lines, parsed).sealed


def test_core_loader_failure_is_reported_as_bad_json() -> None:
    lines = split_lines(VECTOR_PATH.read_bytes())
    lines[4] = lines[4].replace(b'"seq":4', b'"seq":4,"seq":4')
    parsed: list[Any] = []
    for line in lines:
        try:
            parsed.append(strict_json_loads(line[:-1], record=True))
        except IngestError:
            parsed.append(None)
    report = verify_chain(lines, parsed)
    assert report.codes == ("cap.chain.bad_json",) and report.n_verified == 4


def test_stdlib_and_core_strict_parsers_agree_on_rejections() -> None:
    samples = [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":1e999}', b'{"a":"\\ud800"}', b"\xef\xbb\xbf{}", b'{"a":"\xff"}', b"[]"]
    for sample in samples:
        stdlib = verify.strict_loads(sample)
        try:
            core = strict_json_loads(sample, record=True)
        except IngestError:
            core = None
        # the stdlib twin is at least as strict as the core loader (a lone surrogate is only a finding in core)
        assert stdlib is None or core is not None, sample
    assert verify.strict_loads(b'{"a":"\\ud800"}') is None


def test_canonical_form_agrees_with_the_aer_canon_module() -> None:
    from agentprov.aer.canon import dumps_line

    for line in split_lines(VECTOR_PATH.read_bytes()):
        assert dumps_line(loads_strict(line[:-1])) == line  # type: ignore[arg-type]


# ----------------------------------------------------------------------------------------------- schema consistency


def test_data_members_are_pinned_to_the_published_schema() -> None:
    assert tuple(SCHEMA["properties"]["type"]["enum"]) == tuple(sorted(events.EVENT_TYPES))
    for name in events.EVENT_TYPES:
        definition = SCHEMA["$defs"]["data_" + name.replace(".", "_")]
        required = frozenset(definition.get("required", []))
        optional = frozenset(definition["properties"]) - required
        assert events.DATA_MEMBERS[name] == (required, optional), name
    envelope = set(SCHEMA["properties"])
    assert envelope == set(events.ENVELOPE_FIELDS) | {"lex"}


def test_envelope_rules_agree_with_the_schema() -> None:
    base = json.loads(split_lines(VECTOR_PATH.read_bytes())[3])
    cases: list[dict[str, Any]] = []

    def variant(**over: Any) -> dict[str, Any]:
        return {**base, **over}

    cases += [variant(ts="2026-10-07T12:00:03Z"), variant(ts="2026-10-07T12:00:03.0000000Z"), variant(mono_ns=-1), variant(mono_ns=1.5)]
    cases += [variant(prev=None), variant(prev="G" * 64), variant(actor="Agent"), variant(type="llm.exchange"), variant(seq=-1)]
    cases += [variant(**{"pass": -1}), {**base, "pass_no": 0}, {**base, "extra": 1}, {k: v for k, v in base.items() if k != "ts"}]
    cases += [variant(), variant(actor="agent"), variant(**{"pass": 3})]
    for case in cases:
        ours = events.envelope_problem(case) is None
        theirs = VALIDATOR.is_valid(case)
        assert ours == theirs, case


# ----------------------------------------------------------------------------------------------- writer output vs schema


def kitchen_sink(tmp_path: Path) -> CaptureLog:
    """One session using every event type, with redaction, flags, blobs and a traceback."""
    secret = "sk-live-sentinel-0123456789"
    redactor = Redactor([Secret("OPENAI_API_KEY", secret)], home="/Users/tester", host="tester-host")
    log = new_log(tmp_path, redactor=redactor)
    start(log)
    log.emit("identity", {
        "benchmark": {"name": "agentdojo", "dist": "agentdojo", "dist_version": "0.1.35"},
        "harness": {"dist": "agentprov-backend", "version": "0.1.0"},
        "agent": {"model_requested": "m", "provider": "openai_compatible", "endpoint_host": "h.example", "sdk": {"name": "openai", "version": "1"}},
    })
    log.emit("fixture", {"kind": "injection_payload", "vector": "v0", "content": f"ignore previous; key {secret} AKIAABCDEFGHIJKLMNOP"})
    log.emit("pass.start", {"env": {"sha256": ENV_DIGEST, "canon": "jcs-rfc8785"}}, pass_=0)
    request = log.put_blob(json.dumps({"messages": [{"role": "user", "content": f"hi {secret} sk-abcdefghijklmnopqrstuvwx"}]}).encode(), "application/json")
    log.emit("llm.request", {"call": "c0", "role": "agent", "attempt": 0, "endpoint": ENDPOINT, "params": {"configured": {}, "transmitted": {}}, "request": request, "n_messages": 1}, pass_=0, actor="agent")
    log.emit("llm.response", {"call": "c0", "status": "error", "http_status": 401, "reason": f"unauthorised {secret}",
                              "exception": {"type": "HTTPStatusError", "message": f"401 for https://u:p@h.example/v1?key={secret}"}}, pass_=0, actor="agent")
    log.emit("llm.request", {"call": "c1", "role": "agent", "attempt": 1, "retry_of": "c0", "endpoint": ENDPOINT, "params": {"configured": {}, "transmitted": {}}, "request": request}, pass_=0, actor="agent")
    log.emit("llm.response", {"call": "c1", "status": "kept", "response": log.put_blob(b'{"id":"r"}', "application/json"), "finish_reason": "stop"}, pass_=0, actor="agent")
    log.emit("tool.dispatch", {"occ": "o0", "provider_call_id": "call_0", "name": "send_money", "args": {"to": "x"}, "args_raw": "{}"}, pass_=0, actor="env")
    log.emit("decision", {"actor": "agent", "subject": {"occ": "o0"}, "verdict": "deny", "reason": f"blocked {secret}"}, pass_=0, actor="agent")
    log.emit("tool.result", {"occ": "o0", "status": "ok", "rendered": "done", "model_visible": "done"}, pass_=0, actor="env")
    log.emit("state", {"occ": "o0", "env": {"sha256": ENV_DIGEST, "canon": "jcs-rfc8785"}}, pass_=0, actor="env")
    log.emit("pass.end", {"aborted": True, "messages": log.put_blob(b"[]", "application/json"),
                          "env": {"sha256": ENV_DIGEST, "canon": "jcs-rfc8785", "changed": False}}, pass_=0)
    log.emit("outcome", {"judgements": [{"name": "utility", "value": False, "origin": "checker"}]})
    log.emit("native.log", {"path": "raw/capture/x.native.json", "sha256": "ab" * 32, "bytes": 3})
    traceback = log.put_blob(f"Traceback\n  File '/Users/tester/x.py'\nValueError: {secret} sk-abcdefghijklmnopqrstuvwx on tester-host\n".encode(), "text/x-python-traceback")
    log.emit("error", {"where": "agent.run", "exception": {"type": "ValueError", "message": f"{secret}"}, "traceback": traceback, "fatal": True})
    log.emit("note", {"ns": "capture", "kind": "wire_headers", "payload": {"authorization": f"Bearer {secret}"}})
    log.close("errored")
    return log


def test_everything_the_writer_produces_validates_against_the_published_schema(tmp_path: Path) -> None:
    for log in (kitchen_sink(tmp_path / "a"), _vector_log(tmp_path / "b")):
        lines = split_lines(log.path.read_bytes())
        parsed = core_events(lines)
        for event in parsed:
            errors = sorted(VALIDATOR.iter_errors(event), key=str)
            assert not errors, (event["type"], [e.message for e in errors][:3])
        report = verify_chain(lines, parsed)
        assert report.sealed and report.n_verified == len(lines), report.issues
    types = {e["type"] for e in core_events(split_lines(kitchen_sink(tmp_path / "c").path.read_bytes()))}
    assert types == set(events.EVENT_TYPES)


def _vector_log(tmp_path: Path) -> CaptureLog:
    log = new_log(tmp_path)
    replay_vector(log)
    return log


def test_kitchen_sink_session_leaks_nothing(tmp_path: Path) -> None:
    kitchen_sink(tmp_path)
    blob = b"\n".join(p.read_bytes() for p in tmp_path.rglob("*") if p.is_file())
    assert b"sk-live-sentinel" not in blob and b"tester" not in blob
    assert b"sk-abcdefghijklmnopqrstuvwx" in blob  # in the content blob it is flagged, never rewritten
    log_path = next(tmp_path.rglob("*.capture.jsonl"))
    parsed = core_events(split_lines(log_path.read_bytes()))
    flags = [e for e in parsed if e["type"] == "note" and e["data"]["kind"] == "secret_pattern"]
    assert flags and all(e["data"]["ns"] == "capture" for e in flags)
    rules = {r["rule"] for e in parsed for r in e["data"].get("redactions", [])}
    assert rules >= {"cap.secret.env_value@1", "cap.secret.pattern@1", "cap.secret.url_component@1", "cap.secret.home_path@1", "cap.secret.host_name@1"}


def test_parent_terminal_event_validates_against_the_schema(tmp_path: Path) -> None:
    log = new_log(tmp_path)
    start(log)
    log.abandon()
    assert append_terminal(log.path, "aborted") is not None
    lines = split_lines(log.path.read_bytes())
    parsed = core_events(lines)
    assert not list(VALIDATOR.iter_errors(parsed[-1]))
    assert verify_chain(lines, parsed).status == "aborted"


def test_cell_shape_used_by_the_helpers_is_the_schema_cell() -> None:
    assert not list(VALIDATOR.iter_errors({**json.loads(split_lines(VECTOR_PATH.read_bytes())[0]), "data": {**json.loads(split_lines(VECTOR_PATH.read_bytes())[0])["data"], "cell": CELL}}))


# ----------------------------------------------------------------------------------------------- the cap catalogue


def test_cap_catalogue_loads_through_the_core_loader() -> None:
    catalogue = load_catalogue("cap", package="agentprov_capture")
    assert catalogue.namespace == "cap" and catalogue.version == 1
    entry = catalogue.get("cap.context_alignment@1")
    assert entry is not None and entry.cls == "D" and entry.citable and entry.assumptions == ()
    for kind in redact.KINDS:
        rule = catalogue.get(redact.rule_id(kind))
        assert rule is not None and rule.cls == "D", kind
    assert {code for code in verify.ISSUE_CODES if not catalogue.declares_issue_code(code)} == set()
    raw = resources.files("agentprov_capture").joinpath("rules", "cap.rules.toml").read_bytes()
    assert parse_catalogue(raw).digest == catalogue.digest


@pytest.mark.parametrize("kind", redact.KINDS)
def test_redaction_rule_ids_match_the_schema_pattern(kind: str) -> None:
    sample = {"field": "x", "p": "", "rule": redact.rule_id(kind)}
    schema = {**SCHEMA["$defs"]["redactions"]}
    assert not list(jsonschema.Draft202012Validator({**schema, "$defs": SCHEMA["$defs"]}).iter_errors([sample]))
