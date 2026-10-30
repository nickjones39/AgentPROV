"""``CaptureSession`` + ``LlmSpan`` + ``WireRecorder`` + the recording transport, without a benchmark package
(K.5.7(8)): spans record ``input_at``/``n_messages`` and never touch requests; 2xx replies are kept or discarded by
their fate; errors are recorded at once; the log written through ``agentprov_capture`` verifies sealed."""

from __future__ import annotations

import json

import openai
import pytest

from agentprov_backend.gateway import WireRecorder
from agentprov_backend.session import CaptureSession
from agentprov_backend.testing import Fail, Reply, ScriptedTransport
from agentprov_backend.transport import RecordingTransport

HEADER = {
    "cell": {"benchmark": "agentdojo", "task_id": "t"},
    "backend": {"id": "agentdojo", "version": "0.1.0"},
    "runtime": {"python": "3.12", "platform": "test", "lock_sha256": "0" * 64},
    "actors": {"agent": {"kind": "llm_agent"}},
    "config_sha256": "0" * 64,
    "instrumentation": [{"id": "agentdojo.transport_scripted@1", "kind": "test_only", "recorded": "full"}],
    "identity": {"benchmark": {"name": "agentdojo", "dist": "agentdojo", "dist_version": "0.1.35"},
                 "harness": {"dist": "agentprov-backend", "version": "0.1.0"},
                 "agent": {"model_requested": "m", "provider": "openai_compatible", "endpoint_host": "scripted.invalid",
                           "sdk": {"name": "openai", "version": openai.__version__}}},
}
MSGS = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]


def _session(tmp_path, steps, max_retries=0):
    session = CaptureSession(tmp_path / "s")
    session.start(HEADER)
    tr = ScriptedTransport(steps)
    http = openai.DefaultHttpx2Client(transport=RecordingTransport(tr, WireRecorder(session, configured_params={"temperature": 0.0})))
    client = openai.OpenAI(api_key="not-a-secret-value", base_url="https://scripted.invalid/v1", http_client=http,
                           max_retries=max_retries)
    return session, client, tr


def _events(session):
    return [json.loads(x) for x in session.capture_path.read_bytes().splitlines()]


def test_spans_bracket_requests_and_decide_reply_fates(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    session, client, tr = _session(tmp_path, [Reply.text("a"), Fail.http(503), Reply.text("b"), Reply.text("c"),
                                              Reply.text("d")], max_retries=2)
    with session.span("agent", "agent", MSGS):
        client.chat.completions.create(model="m", messages=MSGS)
    with session.span("agent", "agent", MSGS):                       # an SDK retry inside the span
        client.chat.completions.create(model="m", messages=MSGS)
    with pytest.raises(ValueError):
        with session.span("agent", "agent", MSGS):                   # the element raises after the reply
            client.chat.completions.create(model="m", messages=MSGS)
            raise ValueError("parse failure")
    with session.span("agent", "agent", MSGS + [{"role": "user", "content": "x"}]):
        client.chat.completions.create(model="m", messages=MSGS)    # sends fewer messages than it was given
    head = session.close("complete")
    events = _events(session)
    reqs = [e["data"] for e in events if e["type"] == "llm.request"]
    resps = [e["data"] for e in events if e["type"] == "llm.response"]
    assert [r["call"] for r in reqs] == ["c0", "c1", "c2", "c3", "c4"]
    assert [r.get("retry_of") for r in reqs] == [None, None, "c1", None, None]
    assert [r["attempt"] for r in reqs] == [0, 0, 1, 0, 0]
    assert [r.get("input_at") for r in reqs] == [[0, 1]] * 4 + [None]
    assert [r["n_messages"] for r in reqs] == [2, 2, 2, 2, 3]
    assert all(r["params"] == {"configured": {"temperature": 0}, "transmitted": {}} for r in reqs)
    assert [(r["call"], r["status"], r.get("reason")) for r in resps] == [
        ("c0", "kept", None), ("c1", "error", "http_503"), ("c2", "kept", None),
        ("c3", "discarded", "element_raised:ValueError"), ("c4", "kept", None)]
    notes = [e["data"] for e in events if e["type"] == "note" and e["data"]["kind"] == "input_at_unverified"]
    assert [n["payload"]["call"] for n in notes] == ["c4"]
    headers = [e["data"]["payload"] for e in events if e["type"] == "note" and e["data"]["kind"] == "wire_headers"]
    assert [(h["call"], h["direction"]) for h in headers][:2] == [("c0", "request"), ("c0", "response")]
    assert "authorization" in headers[0]["dropped"] and "authorization" not in headers[0]["kept"]
    assert headers[0]["kept"]["content-type"] == "application/json"
    # request blobs are the exact bodies sent
    blobs = tmp_path / "s" / "raw" / "blobs" / "sha256"
    for r, body in zip(reqs, tr.bodies, strict=True):
        h = r["request"]["$blob"].split(":", 1)[1]
        assert (blobs / h[:2] / h).read_bytes() == body
    from agentprov_capture.verify import verify_file

    report = verify_file(session.capture_path)
    assert report.sealed and report.head == head and not report.issues


def test_explicit_marks_and_transport_errors(tmp_path):
    session, client, _ = _session(tmp_path, [Reply.text("a"), Fail.connection()])
    with session.span("agent", "agent", MSGS) as span:
        client.chat.completions.create(model="m", messages=MSGS)
        span.mark_discarded(span.pending_call, "resampled for a test")
    with pytest.raises(openai.APIConnectionError):
        with session.span("agent", "agent", MSGS):
            client.chat.completions.create(model="m", messages=MSGS)
    session.close("errored")
    resps = [e["data"] for e in _events(session) if e["type"] == "llm.response"]
    assert resps[0]["status"] == "discarded" and resps[0]["reason"] == "resampled for a test"
    assert resps[1]["status"] == "error" and resps[1]["exception"]["type"] == "ConnectError"
