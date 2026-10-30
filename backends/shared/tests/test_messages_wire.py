"""D-656: the Anthropic Messages wire without the SDK (K.5.7(8)). The SSE reader and stream assembly, response facts,
the stock-rendering wire count, the Messages mode of ``ScriptedTransport``, the async recording transport and the
Messages-aware ``WireRecorder``. Plain ``httpx2`` clients stand in for the SDK; the SDK-driven tests (``AsyncAnthropic``
under AgentDojo's stock ``AnthropicLLM``) run in the backend environments. No benchmark package is imported."""

from __future__ import annotations

import asyncio
import json

import pytest

from agentprov_backend import messages as m
from agentprov_backend._http import sdk_httpx
from agentprov_backend.gateway import WireRecorder
from agentprov_backend.session import CaptureSession
from agentprov_backend.testing import MessagesFail, MessagesReply, ScriptedTransport, ScriptError, load_script
from agentprov_backend.testing.messages import render_messages_response
from agentprov_backend.transport import AsyncRecordingTransport

httpx = sdk_httpx()
URL = "https://scripted.invalid/v1/messages"

HEADER = {
    "cell": {"benchmark": "agentdojo", "task_id": "t"},
    "backend": {"id": "agentdojo", "version": "0.1.0"},
    "runtime": {"python": "3.12", "platform": "test", "lock_sha256": "0" * 64},
    "actors": {"agent": {"kind": "llm_agent"}},
    "config_sha256": "0" * 64,
    "instrumentation": [{"id": "agentdojo.transport_scripted@1", "kind": "test_only", "recorded": "full"}],
    "identity": {"benchmark": {"name": "agentdojo", "dist": "agentdojo", "dist_version": "0.1.35"},
                 "harness": {"dist": "agentprov-backend", "version": "0.1.0"},
                 "agent": {"model_requested": "m", "provider": "anthropic", "endpoint_host": "scripted.invalid",
                           "sdk": {"name": "httpx2", "version": "test"}}},
}
#: AgentDojo-shaped messages: system, user, assistant with a tool call, two tool results, a user follow-up
NATIVE = [{"role": "system"}, {"role": "user"}, {"role": "assistant"}, {"role": "tool"}, {"role": "tool"},
          {"role": "user"}]


def _body(n_wire: int, *, system: bool = True, stream: bool = True) -> dict:
    wire = [{"role": "user" if i % 2 == 0 else "assistant", "content": [{"type": "text", "text": f"w{i}"}]}
            for i in range(n_wire)]
    body: dict = {"max_tokens": 1024, "messages": wire, "model": "claude-test", "temperature": 0.0}
    if system:
        body["system"] = "You are scripted."
    if stream:
        body["stream"] = True
    return body


def _render(step, *, stream=True):
    return render_messages_response(step, 0, stream=stream)


# ------------------------------------------------------------------------------------------------ SSE reader
def test_parse_sse_follows_the_sdk_decoder():
    body = (b": comment\r\nevent: a\r\ndata: one\r\ndata:two\r\n\r\n"
            b"data: {\"x\": 1}\n\nevent: torn\ndata: never dispatched")
    events, torn = m.parse_sse(body)
    assert events == [m.SseEvent("a", "one\ntwo"), m.SseEvent("message", '{"x": 1}')]
    assert torn is True
    # a BOM is not stripped (the SDK keeps it: the first field name is then unknown)
    assert m.parse_sse("\ufeffevent: a\ndata: x\n\n".encode()) == ([m.SseEvent("message", "x")], False)


@pytest.mark.parametrize("eol", [b"\n", b"\r", b"\r\n"])
def test_a_final_event_ended_by_one_line_terminator_is_torn(eol):
    """Rebuild-window review R1-1: only a blank line dispatches, so this stream is incomplete (note stream_incomplete)."""
    stop = b'event: message_stop' + eol + b'data: {"type": "message_stop"}' + eol
    events, torn = m.parse_sse(stop)
    assert events == [] and torn is True
    events, torn = m.parse_sse(stop + eol)
    assert [e.event for e in events] == ["message_stop"] and torn is False


def test_parse_sse_is_bounded(monkeypatch):
    monkeypatch.setattr(m, "MAX_SSE_EVENTS", 3)
    events, truncated = m.parse_sse(b"data: 1\n\n" * 10)
    assert len(events) == 3 and truncated


def test_stream_assembly_rebuilds_the_message():
    step = MessagesReply.tool_use([{"name": "send_money", "args": {"recipient": "x" * 40, "amount": 1}}],
                                  content="Paying now, with a long sentence.", thinking="I should pay.",
                                  signature="sig==", usage={"input_tokens": 7, "output_tokens": 30,
                                                            "cache_read_input_tokens": 5,
                                                            "cache_creation_input_tokens": 2})
    status, headers, body = _render(step)
    assert status == 200 and headers["content-type"].startswith("text/event-stream")
    msg = m.decode_messages_body(body, headers["content-type"])
    assert msg is not None and msg.streamed and msg.complete and msg.error is None
    assert (msg.id, msg.model, msg.stop_reason) == ("msg_scripted_0", "scripted-fake", "tool_use")
    thinking, text, tool = msg.content
    assert thinking == {"type": "thinking", "thinking": "I should pay.", "signature": "sig=="}
    assert text == {"type": "text", "text": "Paying now, with a long sentence."}
    assert tool["name"] == "send_money" and tool["id"] == "toolu_scripted_0_0"
    assert tool["input"] == {"recipient": "x" * 40, "amount": 1}
    assert json.loads(tool["input_json"]) == tool["input"]       # the raw partial_json text, concatenated
    # the later usage wins per key, as the SDK's accumulator does (output_tokens 1 at start, 30 at the end)
    assert m.messages_response_facts(msg) == {
        "response_id": "msg_scripted_0", "served_model": "scripted-fake", "finish_reason": "tool_use",
        "usage": {"input_tokens": 7, "output_tokens": 30, "cache_read_tokens": 5, "cache_write_tokens": 2}}


def test_json_and_stream_forms_carry_the_same_facts():
    step = MessagesReply.text("hello", thinking="", signature="opaque")      # display "omitted": empty thinking
    s_status, s_headers, s_body = _render(step, stream=True)
    j_status, j_headers, j_body = _render(step, stream=False)
    streamed = m.decode_messages_body(s_body, s_headers["content-type"])
    plain = m.decode_messages_body(j_body, j_headers["content-type"])
    assert m.messages_response_facts(streamed) == m.messages_response_facts(plain)
    assert [b["type"] for b in plain.content] == ["thinking", "text"]
    assert streamed.content[0] == plain.content[0] == {"type": "thinking", "thinking": "", "signature": "opaque"}
    assert "total_tokens" not in m.messages_response_facts(plain)["usage"]


def test_malformed_streamed_arguments_are_kept_raw():
    step = MessagesReply.tool_use([{"name": "f", "arguments": '{"a": 1'}])
    _, headers, body = _render(step)
    msg = m.decode_messages_body(body, headers["content-type"])
    assert msg.content[0]["input_json"] == '{"a": 1' and msg.content[0]["input"] is None
    with pytest.raises(ScriptError):
        _render(step, stream=False)


def test_errors_and_incomplete_streams():
    _, headers, body = _render(MessagesFail.stream_error("overloaded_error"))
    msg = m.decode_messages_body(body, headers["content-type"])
    assert msg.error == {"type": "overloaded_error", "message": "scripted stream error"}
    assert m.messages_response_facts(msg) == {}
    _, headers, body = _render(MessagesFail.truncated(MessagesReply.text("abc"), after=4))
    msg = m.decode_messages_body(body, headers["content-type"])
    assert msg.error is None and not msg.complete and msg.id == "msg_scripted_0"
    status, headers, body = _render(MessagesFail.http(529, retry_after="2"))
    assert status == 529 and headers["retry-after"] == "2"
    msg = m.decode_messages_body(body, headers["content-type"])
    assert msg.error == {"type": "overloaded_error", "message": "scripted HTTP 529"}
    assert m.decode_messages_body(b"not json", "application/json") is None


@pytest.mark.parametrize("roles, n", [
    ([], 0),
    (["system"], 0),
    (["system", "user"], 1),
    (["user", "user"], 1),
    (["system", "user", "assistant", "tool", "tool", "user"], 3),   # tool results and the follow-up are one turn
    (["system", "user", "assistant", "assistant", "tool"], 4),
    (["user", "system"], 1),                                       # only a LEADING system message is lifted
])
def test_stock_wire_count(roles, n):
    assert m.stock_wire_count(roles) == n


# ------------------------------------------------------------------------------------------------ scripts
def test_messages_script_file(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"api": "anthropic_messages", "steps": [
        {"reply": "tool_use", "calls": [{"name": "get_balance", "args": {}}], "thinking": ""},
        {"reply": "text", "content": "done", "usage": None},
        {"reply": "text", "content": "cut", "cut_after": 3},
        {"fail": "http", "status": 429, "retry_after": "1"},
        {"fail": "stream_error"}, {"fail": "connection"}, {"reply": "refusal"}, {"reply": "empty"}]}))
    steps = load_script(path)
    assert [s.label for s in steps] == ["tool_use", "text", "truncated", "http_429", "stream_error", "connection",
                                        "refusal", "empty"]
    assert all(s.api == "anthropic_messages" for s in steps)
    path.write_text(json.dumps({"api": "grpc", "steps": []}))
    with pytest.raises(ScriptError):
        load_script(path)


# ------------------------------------------------------------------------------------------------ recording
class Observer:
    def __init__(self, fail_on_request: bool = False) -> None:
        self.events: list[tuple] = []
        self.fail = fail_on_request

    def on_request(self, request, body):
        if self.fail:
            raise RuntimeError("capture write failed")
        self.events.append(("request", body))
        return len(self.events)

    def on_response(self, token, status, headers, body):
        self.events.append(("response", status, body))

    def on_error(self, token, exc):
        self.events.append(("error", type(exc).__name__))


async def _post(transport, bodies):
    async with httpx.AsyncClient(transport=transport) as client:
        out = []
        for body in bodies:
            try:
                out.append(await client.post(URL, json=body, headers={"x-api-key": "not-a-secret-value",
                                                                       "anthropic-version": "2023-06-01"}))
            except httpx.ConnectError as exc:
                out.append(exc)
        return out


def test_async_transport_records_and_passes_bytes_through():
    scripted = ScriptedTransport([MessagesReply.text("a"), MessagesFail.connection()])
    obs = Observer()
    responses = asyncio.run(_post(AsyncRecordingTransport(scripted, obs, module=httpx), [_body(1), _body(1)]))
    assert responses[0].status_code == 200 and isinstance(responses[1], httpx.ConnectError)
    assert [e[0] for e in obs.events] == ["request", "response", "request", "error"]
    assert obs.events[0][1] == scripted.bodies[0]                 # the request body as sent
    assert obs.events[1][2] == responses[0].content               # the response body as the client read it


def test_async_transport_sends_nothing_it_could_not_record():
    scripted = ScriptedTransport([MessagesReply.text("a")])
    with pytest.raises(RuntimeError):
        asyncio.run(_post(AsyncRecordingTransport(scripted, Observer(fail_on_request=True), module=httpx), [_body(1)]))
    assert scripted.requests == []


def _session(tmp_path):
    session = CaptureSession(tmp_path / "s")
    session.start(HEADER)
    return session


def _events(session):
    return [json.loads(x) for x in session.capture_path.read_bytes().splitlines()]


def test_recorder_on_the_messages_wire(tmp_path):
    session = _session(tmp_path)
    scripted = ScriptedTransport([
        MessagesReply.tool_use([{"name": "get_balance", "args": {}}], thinking="", signature="s1"),   # c0 kept
        MessagesFail.http(529),                                                                       # c1 error
        MessagesFail.stream_error("overloaded_error"),                                                # c2 error
        MessagesFail.truncated(MessagesReply.text("partial"), after=3),                               # c3 note
        MessagesReply.text("x"),                                                                      # c4 unverified
    ])
    rec = WireRecorder(session, configured_params={"max_tokens": 1024}, api="anthropic_messages")
    transport = AsyncRecordingTransport(scripted, rec, module=httpx)
    for body, native in ((_body(3), NATIVE), (_body(3), NATIVE), (_body(3), NATIVE), (_body(3), NATIVE),
                         (_body(2), NATIVE)):
        with session.span("agent", "agent", native):
            asyncio.run(_post(transport, [body]))
    session.close("complete")
    events = _events(session)
    reqs = [e["data"] for e in events if e["type"] == "llm.request"]
    resps = [e["data"] for e in events if e["type"] == "llm.response"]
    assert reqs[0]["endpoint"] == {"host": "scripted.invalid", "path": "/v1/messages"}
    # system is content, not a parameter
    assert reqs[0]["params"] == {"configured": {"max_tokens": 1024},
                                 "transmitted": {"max_tokens": 1024, "stream": True, "temperature": 0}}
    assert [r.get("input_at") for r in reqs] == [list(range(6))] * 4 + [None]
    assert [(r["call"], r["status"], r.get("reason"), r.get("http_status")) for r in resps] == [
        ("c0", "kept", None, 200), ("c1", "error", "http_529", 529), ("c2", "error", "stream_error:overloaded_error", 200),
        ("c3", "kept", None, 200), ("c4", "kept", None, 200)]
    assert resps[0]["finish_reason"] == "tool_use" and resps[0]["served_model"] == "scripted-fake"
    assert resps[0]["usage"] == {"input_tokens": 100, "output_tokens": 20, "cache_read_tokens": 0,
                                 "cache_write_tokens": 0}
    assert resps[0]["response"]["media"] == "text/event-stream"
    notes = {(e["data"]["kind"], e["data"]["payload"]["call"]): e["data"]["payload"] for e in events
             if e["type"] == "note" and e["data"]["kind"] in ("stream_incomplete", "input_at_unverified")}
    assert set(notes) == {("stream_incomplete", "c3"), ("input_at_unverified", "c4")}
    assert notes[("input_at_unverified", "c4")] == {"call": "c4", "n_messages": 6, "n_sent": 2, "n_expected": 3}
    headers = [e["data"]["payload"] for e in events if e["type"] == "note" and e["data"]["kind"] == "wire_headers"]
    assert all("x-api-key" not in h["kept"] for h in headers)
    assert "x-api-key" in headers[0]["dropped"]


def test_system_without_a_leading_system_message_is_unverified(tmp_path):
    session = _session(tmp_path)
    rec = WireRecorder(session, api="anthropic_messages")
    transport = AsyncRecordingTransport(ScriptedTransport([MessagesReply.text("x")]), rec, module=httpx)
    with session.span("agent", "agent", [{"role": "user"}]):
        asyncio.run(_post(transport, [_body(1, system=True)]))
    session.close("complete")
    reqs = [e["data"] for e in _events(session) if e["type"] == "llm.request"]
    assert "input_at" not in reqs[0]


def test_recorder_api_comes_from_the_endpoint():
    from agentprov_capture.endpoints import get_endpoint

    assert WireRecorder(None, endpoint=get_endpoint("anthropic")).is_messages
    assert not WireRecorder(None, endpoint=get_endpoint("openai")).is_messages
    assert not WireRecorder(None).is_messages
    with pytest.raises(ValueError):
        WireRecorder(None, api="grpc")


# ------------------------------------------------------------------------------------------------ egress proxy (D-664)
@pytest.mark.parametrize("value", ["http://127.0.0.1:8899", "http://localhost:1", "http://[::1]:65535/"])
def test_egress_proxy_accepts_loopback_http(monkeypatch, value):
    from agentprov_backend.transport import default_async_inner_transport, egress_proxy

    monkeypatch.setenv("AGENTPROV_EGRESS_PROXY", value)
    assert egress_proxy() == value
    assert type(default_async_inner_transport(httpx)._pool).__name__ == "AsyncHTTPProxy"


@pytest.mark.parametrize("value", ["https://127.0.0.1:8899", "http://10.0.0.1:8899", "http://example.com:80",
                                   "http://u:p@127.0.0.1:8899", "http://127.0.0.1", "http://127.0.0.1:0",
                                   "http://127.0.0.1:8899/x", "http://127.0.0.1:8899?a=1", "http://127.0.0.1:99999",
                                   "socks5://127.0.0.1:1080", "not a url"])
def test_egress_proxy_fails_closed(monkeypatch, value):
    from agentprov_backend.transport import default_async_inner_transport, egress_proxy

    monkeypatch.setenv("AGENTPROV_EGRESS_PROXY", value)
    with pytest.raises(ValueError):
        egress_proxy()
    with pytest.raises(ValueError):
        default_async_inner_transport(httpx)


def test_no_egress_proxy_leaves_the_transport_direct(monkeypatch):
    from agentprov_backend.transport import default_async_inner_transport, egress_proxy

    monkeypatch.delenv("AGENTPROV_EGRESS_PROXY", raising=False)
    assert egress_proxy() is None
    monkeypatch.setenv("AGENTPROV_EGRESS_PROXY", "")
    assert egress_proxy() is None
    assert type(default_async_inner_transport(httpx)._pool).__name__ == "AsyncConnectionPool"
