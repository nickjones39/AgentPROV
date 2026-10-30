"""K.5.7(8): the recording transport never modifies a request (byte-compare the request the SDK built with the one
sent), records every wire exchange including the SDK's own retries, and sends nothing it could not record.
``ScriptedTransport`` (K.3.2) behaviour. No benchmark package is imported."""

from __future__ import annotations

import json

import openai
import pytest

from agentprov_backend._http import sdk_httpx
from agentprov_backend.testing import (
    Fail,
    Reply,
    ScriptedTransport,
    ScriptError,
    ScriptExhausted,
    ScriptExpectationFailed,
    load_script,
    step_from_dict,
)
from agentprov_backend.transport import RecordingTransport, recording_transport_class

httpx = sdk_httpx()


class Observer:
    def __init__(self, fail_on_request: bool = False) -> None:
        self.events: list[tuple] = []
        self.fail = fail_on_request

    def on_request(self, request, body):
        if self.fail:
            raise RuntimeError("capture write failed")
        self.events.append(("request", request, body))
        return len(self.events)

    def on_response(self, token, status, headers, body):
        self.events.append(("response", token, status, body))

    def on_error(self, token, exc):
        self.events.append(("error", token, type(exc).__name__))


class SpyInner(httpx.BaseTransport):
    def __init__(self, inner):
        self.inner = inner
        self.seen: list = []

    def handle_request(self, request):
        self.seen.append((request, bytes(request.read()), list(request.headers.raw)))
        return self.inner.handle_request(request)


def _client(inner, observer, *, max_retries=2):
    http_client = openai.DefaultHttpx2Client(transport=RecordingTransport(inner, observer)) \
        if hasattr(openai, "DefaultHttpx2Client") else httpx.Client(transport=RecordingTransport(inner, observer))
    return openai.OpenAI(api_key="test-key-not-secret", base_url="https://scripted.invalid/v1",
                         http_client=http_client, max_retries=max_retries)


def test_the_sdk_uses_the_module_we_record_with():
    assert httpx.__name__ in ("httpx2", "httpx")
    assert issubclass(recording_transport_class(), httpx.BaseTransport)


def test_request_bytes_and_object_are_passed_through_unchanged(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    scripted = ScriptedTransport([Fail.http(503), Reply.text("hi")])
    spy = SpyInner(scripted)
    obs = Observer()
    client = _client(spy, obs)
    built: list = []
    original = client._client.send

    def send(request, **kw):
        built.append((request, bytes(request.read()), list(request.headers.raw)))
        return original(request, **kw)

    client._client.send = send
    out = client.chat.completions.create(model="m", messages=[{"role": "user", "content": "x"}])
    assert out.choices[0].message.content == "hi"
    requests = [e for e in obs.events if e[0] == "request"]
    assert len(requests) == len(spy.seen) == len(built) == 2          # the SDK's retry is a second exchange
    for (_, req, body), (sreq, sbody, sheaders), (breq, bbody, bheaders) in zip(requests, spy.seen, built, strict=True):
        assert req is sreq is breq                                   # the same object reached the wire
        assert body == sbody == bbody                                # byte-identical body
        assert sheaders == bheaders                                  # headers untouched
    statuses = [e[2] for e in obs.events if e[0] == "response"]
    assert statuses == [503, 200]
    assert json.loads(obs.events[-1][3])["choices"][0]["message"]["content"] == "hi"


def test_nothing_is_sent_when_the_request_cannot_be_recorded():
    scripted = ScriptedTransport([Reply.text("hi")])
    client = _client(scripted, Observer(fail_on_request=True), max_retries=0)
    with pytest.raises(Exception, match="capture write failed"):
        client.chat.completions.create(model="m", messages=[{"role": "user", "content": "x"}])
    assert scripted.bodies == []


def test_transport_errors_are_reported_and_re_raised(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    obs = Observer()
    client = _client(ScriptedTransport([Fail.connection()]), obs, max_retries=0)
    with pytest.raises(openai.APIConnectionError):
        client.chat.completions.create(model="m", messages=[{"role": "user", "content": "x"}])
    assert [e[0] for e in obs.events] == ["request", "error"] and obs.events[1][2] == "ConnectError"


def test_scripted_transport_steps_and_exhaustion():
    tr = ScriptedTransport([
        Reply.tool_calls([{"name": "f", "args": {"a": 1}}], usage=None),
        Reply.null(),
        Reply.refusal("no"),
        Reply.reasoning("ans", "why", field="reasoning_content"),
        Fail.no_choices(),
        Fail.malformed_args('{"n": 5'),
        Fail.finish_error(),
        Fail.context_length(),
    ])
    client = _client(tr, Observer(), max_retries=0)
    first = client.chat.completions.create(model="m", messages=[{"role": "user", "content": "x"}])
    assert first.choices[0].message.tool_calls[0].function.arguments == '{"a": 1}' and first.usage is None
    assert first.id == "scripted-0" and first.model == "scripted-fake"
    assert client.chat.completions.create(model="m", messages=[]).choices[0].message.content is None
    assert client.chat.completions.create(model="m", messages=[]).choices[0].message.refusal == "no"
    r = client.chat.completions.create(model="m", messages=[])
    assert r.choices[0].message.model_extra["reasoning_content"] == "why"
    assert client.chat.completions.create(model="m", messages=[]).choices is None
    bad = client.chat.completions.create(model="m", messages=[])
    assert bad.choices[0].message.tool_calls[0].function.arguments == '{"n": 5'
    assert client.chat.completions.create(model="m", messages=[]).choices[0].finish_reason == "error"
    with pytest.raises(openai.BadRequestError) as exc:
        client.chat.completions.create(model="m", messages=[])
    assert exc.value.code == "context_length_exceeded"
    with pytest.raises(ScriptExhausted):
        client.chat.completions.create(model="m", messages=[])
    assert len(tr.requests) == len(tr.bodies) == 9 and tr.remaining == 0


def test_expectations_are_checked_against_the_wire_request():
    tr = ScriptedTransport([Reply.text("a", expect=lambda req: b'"model":"m"' in req.read()),
                            Reply.text("b", expect=lambda req: False)])
    client = _client(tr, Observer(), max_retries=0)
    client.chat.completions.create(model="m", messages=[])
    with pytest.raises(ScriptExpectationFailed):
        client.chat.completions.create(model="m", messages=[])


def test_script_files(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps([{"reply": "tool_calls", "calls": [{"name": "f", "arguments": "{}"}]},
                             {"reply": "text", "content": "x", "usage": None},
                             {"fail": "http", "status": 503}, {"fail": "context_length"},
                             {"raw": {"status": 200, "json": {"anything": 1}}}]))
    steps = load_script(p)
    assert [s.status for s in steps] == [200, 200, 503, 400, 200]
    assert "usage" not in steps[1].body
    for bad in ('[{"reply": "nope"}]', '[{"fail": "http", "status": 200}]', '{"steps": 1}',
                '[{"reply": "text", "content": "a", "content": "b"}]', '[{"reply": "text", "content": NaN}]', '[1]'):
        p.write_text(bad)
        with pytest.raises((ScriptError, ValueError)):
            load_script(p)
    with pytest.raises(ScriptError):
        step_from_dict({"reply": "tool_calls", "calls": [{"name": "f", "arguments": {"not": "raw"}}]})


# ------------------------------------------------------------------------------------------------ egress proxy (D-664)
def test_the_sync_inner_transport_follows_the_egress_proxy(monkeypatch):
    """D-664: the recording transport's real inner transport tunnels through T0's egress proxy when T0 set it, and
    is direct without it (scripted runs, loopback endpoints); a malformed value fails closed, never falls back."""
    import pytest

    from agentprov_backend.transport import default_inner_transport

    monkeypatch.delenv("AGENTPROV_EGRESS_PROXY", raising=False)
    assert type(default_inner_transport()._pool).__name__ == "ConnectionPool"
    monkeypatch.setenv("AGENTPROV_EGRESS_PROXY", "http://127.0.0.1:8899")
    assert type(default_inner_transport()._pool).__name__ == "HTTPProxy"
    monkeypatch.setenv("AGENTPROV_EGRESS_PROXY", "http://10.0.0.1:8899")
    with pytest.raises(ValueError):
        default_inner_transport()
