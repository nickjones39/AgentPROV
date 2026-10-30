"""K.8.1 under provider ``anthropic`` (D-656): real AgentDojo 0.1.35 suite tasks driven by AgentDojo's
``AnthropicLLM`` (as the declared port ``AnthropicPortLLM``) on a real ``AsyncAnthropic`` client, with ``ScriptedTransport`` (Messages mode) as the HTTP transport
under the async recording transport (no network, no keys). The scripted replies are synthetic.

Every produced session must verify sealed, every ``llm.request`` must carry ``input_at`` (verified against the stock
Messages rendering) and ``n_messages``, and the recorded request bodies must be the bytes the server received.

**Finding (2026-10-22).** The locked ``anthropic`` 1.11.0 SDK has no ``temperature``/``top_p``/``top_k`` parameters,
and AgentDojo 0.1.35's ``chat_completion_request`` always passes ``temperature=`` (``NOT_GIVEN`` when unset), so the
stock element raises ``TypeError`` before anything is sent (``test_the_stock_element_cannot_run_on_the_locked_sdk``).
The user chose a declared port (2026-10-22): ``temperature`` goes through ``extra_body`` when set; the port is
otherwise the stock code, checked here by AST."""

from __future__ import annotations

import json

import pytest

import ast
import asyncio
import inspect
import textwrap

from agentprov_backend.runner import (
    ANTHROPIC_HARNESS_MAX_TOKENS,
    AgentConfig,
    UnsupportedConfiguration,
    check_anthropic_params,
    messages_roles_verdict,
)
from agentprov_backend.testing import MessagesFail, MessagesReply
from agentprov_backend.testing.messages import render_messages_response
from agentprov_backend.testing.scenarios import SCENARIOS, benign_cell
from support import assert_capture_invariants, pass_message_lists, run_cell

ANTHROPIC = {"model_requested": "claude-scripted", "provider": "anthropic", "endpoint": "scripted", "api_key_env": None,
             "params": {"max_tokens": 4096, "max_tokens_mode": "explicit"}, "llm_element": "native",
             "transport": "scripted", "script": "script.json", "base_url": None}
CELL = benign_cell("banking", "user_task_1")
READ = {"name": "get_most_recent_transactions", "args": {"n": 100}}
ANSWER = "You spent 1050 in March 2022."


def _statuses(run):
    return [(e["data"]["call"], e["data"]["status"], e["data"].get("reason")) for e in run.of("llm.response")]


def _requests(run):
    return [run.json_blob(e["data"]["request"]) for e in run.of("llm.request")]


BENIGN = {
    "banking": ("user_task_1", {"name": "get_balance", "args": {}}),
    "workspace": ("user_task_0", {"name": "get_current_day", "args": {}}),
    "travel": ("user_task_0", {"name": "get_user_information", "args": {}}),
    "slack": ("user_task_0", {"name": "get_channels", "args": {}}),
}


@pytest.mark.parametrize("suite", sorted(BENIGN))
def test_one_benign_cell_per_suite(tmp_path, suite):
    task, call = BENIGN[suite]
    steps = [MessagesReply.tool_use([call], thinking="", signature="c2lnLTE="), MessagesReply.text("Done.")]
    run = run_cell(tmp_path, benign_cell(suite, task), ANTHROPIC, steps)
    assert run.result.status == "complete", run.of("error")
    assert_capture_invariants(run)
    assert [e["data"]["n_messages"] for e in run.of("llm.request")] == [2, 4]
    assert run.of("tool.result")[0]["data"]["status"] == "ok"
    first, second = _requests(run)
    # the stock rendering: system lifted out, streaming, max_tokens from the run, no temperature sent
    assert first["stream"] is True and isinstance(first["system"], str) and first["max_tokens"] == 4096
    assert "temperature" not in first and [m["role"] for m in first["messages"]] == ["user"]
    assert [m["role"] for m in second["messages"]] == ["user", "assistant", "user"]
    # the thinking block (display "omitted": empty text) is sent back with its signature, unchanged
    assert second["messages"][1]["content"][0] == {"type": "thinking", "thinking": "", "signature": "c2lnLTE="}
    assert second["messages"][2]["content"][0]["type"] == "tool_result"
    resp = run.of("llm.response")[0]["data"]
    assert resp["response"]["media"] == "text/event-stream" and resp["finish_reason"] == "tool_use"
    assert resp["usage"] == {"input_tokens": 100, "output_tokens": 20, "cache_read_tokens": 0, "cache_write_tokens": 0}
    ident = run.of("identity")[0]["data"]["agent"]
    assert ident["provider"] == "anthropic" and ident["sdk"]["name"] == "anthropic"
    (dump,) = pass_message_lists(run)
    assert json.dumps(dump, sort_keys=True) == json.dumps(run.native()["messages"], sort_keys=True)
    assert dump[2]["content"][0] == {"type": "thinking", "content": "", "id": "c2lnLTE="}


def test_instrumentation_declares_the_max_tokens_mode_and_temperature(tmp_path):
    run = run_cell(tmp_path, CELL, ANTHROPIC, [MessagesReply.text(ANSWER)])
    items = {i["id"]: i for i in run.of("instrumentation")[0]["data"]["items"]}
    assert items["agentdojo.anthropic_max_tokens@1"]["params"] == {"max_tokens": 4096, "mode": "explicit",
                                                                   "stock_default": 1024}
    assert items["agentdojo.anthropic_max_tokens@1"]["kind"] == "harness_policy"
    assert items["agentdojo.temperature_not_transmitted@1"]["params"] == {"configured": None}
    assert items["agentdojo.recording_transport@1"]["params"]["sdk"] == "anthropic"
    assert items["agentdojo.recording_transport@1"]["params"]["mode"] == "async"
    assert "agentdojo.role_rewrite_developer_to_system@1" not in items
    default = {**ANTHROPIC, "params": {"max_tokens": ANTHROPIC_HARNESS_MAX_TOKENS, "max_tokens_mode": "harness_default",
                                       "temperature": 0.5}}
    run = run_cell(tmp_path / "b", CELL, default, [MessagesReply.text(ANSWER)])
    items = {i["id"]: i for i in run.of("instrumentation")[0]["data"]["items"]}
    assert items["agentdojo.anthropic_max_tokens@1"]["params"]["mode"] == "harness_default"
    assert "agentdojo.temperature_not_transmitted@1" not in items
    (req,) = _requests(run)
    assert req["max_tokens"] == 16000 and req["temperature"] == 0.5


@pytest.mark.parametrize("params", [
    {},
    {"max_tokens": 1024},
    {"max_tokens": 0, "max_tokens_mode": "explicit"},
    {"max_tokens": 4096, "max_tokens_mode": "harness_default"},
    {"max_tokens": 4096, "max_tokens_mode": "explicit", "reasoning_effort": "high"},
    {"max_tokens": 4096, "max_tokens_mode": "explicit", "temperature": "hot"},
])
def test_anthropic_params_are_checked(params):
    with pytest.raises(UnsupportedConfiguration):
        check_anthropic_params(params)


def test_a_cell_without_max_tokens_is_refused_and_sealed(tmp_path):
    run = run_cell(tmp_path, CELL, {**ANTHROPIC, "params": {}}, [MessagesReply.text(ANSWER)])
    assert run.result.status == "errored"
    assert run.of("llm.request") == []
    assert "max_tokens" in run.of("error")[0]["data"]["exception"]["message"]


def test_provider_anthropic_runs_the_stock_element_only():
    with pytest.raises(ValueError):
        AgentConfig.from_json({**ANTHROPIC, "llm_element": "gateway_compat"})
    with pytest.raises(ValueError):
        AgentConfig.from_json({**ANTHROPIC, "provider": "bedrock"})


def test_foreign_sdk_credentials_are_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "not-a-real-token-value")
    run = run_cell(tmp_path, CELL, ANTHROPIC, [MessagesReply.text(ANSWER)])
    assert run.result.status == "errored" and run.of("llm.request") == []
    assert "ANTHROPIC_AUTH_TOKEN" in run.of("error")[0]["data"]["exception"]["message"]


def test_the_key_goes_out_as_x_api_key_and_nowhere_else(tmp_path):
    sentinel = "sk-ant-agentprov-sentinel-4f1c9e"
    agent = {**ANTHROPIC, "api_key_env": "ANTHROPIC_API_KEY", "endpoint": "anthropic"}   # the registry's header allowlist
    run = run_cell(tmp_path, CELL, agent, [MessagesReply.tool_use([READ]), MessagesReply.text(ANSWER)],
                   environ={"ANTHROPIC_API_KEY": sentinel})
    assert run.result.status == "complete"
    headers = run.transport.requests[0].headers
    assert headers["x-api-key"] == sentinel and "authorization" not in headers
    assert headers["anthropic-version"]
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert sentinel.encode() not in path.read_bytes(), path.name
    note = run.notes("wire_headers")[0]
    assert "x-api-key" in note["dropped"] and "anthropic-version" not in note["dropped"]


def test_empty_final_reply_is_a_single_pass(tmp_path):
    """Stock behaviour differs from the OpenAI element: AgentDojo re-runs a pass only when the final content is None,
    and the stock AnthropicLLM always returns a list (here empty), so there is no silent re-run."""
    steps = [MessagesReply.tool_use([READ]), MessagesReply.empty()]
    run = run_cell(tmp_path, CELL, ANTHROPIC, steps)
    assert run.result.status == "complete"
    assert_capture_invariants(run)
    assert [e["pass"] for e in run.of("pass.end")] == [0]
    assert [e["data"]["n_messages"] for e in run.of("llm.request")] == [2, 4]
    (dump,) = pass_message_lists(run)
    assert dump[-1]["role"] == "assistant" and dump[-1]["content"] == []


def test_tool_results_and_follow_up_are_one_turn(tmp_path):
    """Two tool calls in one reply: both tool results go back in one user turn (the stock merge), and input_at is
    still verified."""
    calls = [READ, {"name": "get_balance", "args": {}}]
    run = run_cell(tmp_path, CELL, ANTHROPIC, [MessagesReply.tool_use(calls), MessagesReply.text(ANSWER)])
    assert run.result.status == "complete"
    assert_capture_invariants(run)
    second = _requests(run)[1]
    assert [m["role"] for m in second["messages"]] == ["user", "assistant", "user"]
    assert [b["type"] for b in second["messages"][2]["content"]] == ["tool_result", "tool_result"]
    assert run.of("llm.request")[1]["data"]["n_messages"] == 5


@pytest.mark.parametrize("failure", [MessagesFail.http(529), MessagesFail.http(500), MessagesFail.http(429, retry_after="0")])
def test_retryable_statuses_are_retried_and_recorded(tmp_path, failure):
    run = run_cell(tmp_path, CELL, ANTHROPIC, [failure, MessagesReply.text(ANSWER)])
    assert run.result.status == "complete"
    assert_capture_invariants(run)
    assert _statuses(run) == [("c0", "error", f"http_{failure.status}"), ("c1", "kept", None)]
    assert run.of("llm.request")[1]["data"]["retry_of"] == "c0"


def test_a_400_is_not_retried(tmp_path):
    run = run_cell(tmp_path, CELL, ANTHROPIC, [MessagesFail.http(400), MessagesReply.text(ANSWER)])
    assert _statuses(run) == [("c0", "error", "http_400")]
    assert run.transport.remaining == 1


def test_a_stream_error_is_an_error_not_a_reply(tmp_path):
    run = run_cell(tmp_path, CELL, ANTHROPIC, [MessagesFail.stream_error(), MessagesReply.text(ANSWER)])
    assert run.result.status == "complete"
    assert_capture_invariants(run)
    assert _statuses(run)[0] == ("c0", "error", "stream_error:overloaded_error")
    assert run.of("llm.response")[0]["data"]["http_status"] == 200


def test_refusal_stop_reason(tmp_path):
    run = run_cell(tmp_path, CELL, ANTHROPIC, [MessagesReply.refusal()])
    assert run.result.status == "complete"
    assert [e["data"]["finish_reason"] for e in run.of("llm.response")] == ["refusal"]
    assert len(run.of("pass.end")) == 1    # content [] is not None: no re-run


def test_max_tokens_with_a_partial_tool_call_drops_the_call(tmp_path):
    """Stock behaviour: tool calls are parsed only when stop_reason == "tool_use"; the wire keeps the block."""
    run = run_cell(tmp_path, CELL, ANTHROPIC, [MessagesReply.tool_use([READ], stop="max_tokens")] * 3)
    assert run.of("tool.dispatch") == []
    body = run.blob(run.of("llm.response")[0]["data"]["response"]).decode()
    assert "input_json_delta" in body and '"stop_reason":"max_tokens"' in body


def test_invalid_tool_name_is_filtered_by_the_stock_element(tmp_path):
    bad = {"name": "not a valid name!", "args": {}}
    run = run_cell(tmp_path, CELL, ANTHROPIC, [MessagesReply.tool_use([bad, READ]), MessagesReply.text(ANSWER)])
    dispatched = [d["data"]["name"] for d in run.of("tool.dispatch")]
    assert dispatched == [READ["name"]]


def test_payload_fidelity_wire_capture_native(tmp_path):
    sc = SCENARIOS["injection_important_instructions"]
    run = run_cell(tmp_path, sc.cell, ANTHROPIC, [MessagesReply.tool_use([READ]), MessagesReply.text(ANSWER)],
                   patch=sc.patch, backend_config=sc.backend_config)
    assert run.result.status == "complete"
    assert_capture_invariants(run)
    payloads = {f["data"]["vector"]: f["data"]["content"] for f in run.of("fixture")}
    assert payloads == run.native()["injections"]
    second = _requests(run)[1]
    (result,) = [b for b in second["messages"][2]["content"] if b["type"] == "tool_result"]
    native_tool = [m for m in run.native()["messages"] if m["role"] == "tool"][0]
    assert result["content"][0]["text"] == native_tool["content"][0]["content"]


def test_preflight_verdict_on_the_messages_wire():
    ok = MessagesReply.tool_use([{"name": "get_probe_value", "args": {"key": "q7f3-probe"}}])
    for stream in (True, False):
        status, headers, body = render_messages_response(ok, 0, stream=stream)
        assert messages_roles_verdict(status, body, headers["content-type"]) == ("accepted", "instruction_followed")
    status, headers, body = render_messages_response(MessagesReply.text("hello"), 0, stream=True)
    assert messages_roles_verdict(status, body, headers["content-type"]) == ("unconfirmed", "instruction_not_evidenced")
    status, headers, body = render_messages_response(MessagesFail.stream_error(), 0, stream=True)
    assert messages_roles_verdict(status, body, headers["content-type"]) == ("refused", "error_object")
    status, headers, body = render_messages_response(MessagesFail.http(400), 0, stream=True)
    assert messages_roles_verdict(status, body, headers["content-type"]) == ("refused", "http_400")
    assert messages_roles_verdict(None, None, None) == ("unknown", "no_reply")


# ------------------------------------------------------------------ the port (D-656)


def _def(obj):
    return ast.parse(textwrap.dedent(inspect.getsource(obj))).body[0]


def test_the_stock_element_cannot_run_on_the_locked_sdk():
    """Why the port exists: the locked SDK's stream() has no `temperature`, and the stock request passes one always."""
    import anthropic
    from agentdojo.agent_pipeline.llms import anthropic_llm as stock
    from anthropic.resources.messages import AsyncMessages

    assert "temperature" not in inspect.signature(AsyncMessages.stream).parameters
    client = anthropic.AsyncAnthropic(api_key="not-a-secret-value", base_url="https://scripted.invalid")
    request = stock.chat_completion_request.retry_with(stop=stock.stop_after_attempt(1), reraise=True)
    with pytest.raises(TypeError, match="temperature"):
        asyncio.run(request(client, "m", [{"role": "user", "content": "x"}], [], max_tokens=1, temperature=None))


def test_the_port_query_is_the_stock_query():
    from agentdojo.agent_pipeline.llms.anthropic_llm import AnthropicLLM

    from agentprov_backend._anthropic_llm import AnthropicPortLLM

    assert ast.dump(_def(AnthropicPortLLM.query)) == ast.dump(_def(AnthropicLLM.query))
    assert AnthropicPortLLM.__init__ is AnthropicLLM.__init__ and AnthropicPortLLM.__bases__ == (AnthropicLLM,)


def test_the_port_request_differs_from_the_stock_one_only_in_temperature():
    from agentdojo.agent_pipeline.llms import anthropic_llm as stock

    from agentprov_backend import _anthropic_llm as port

    expected = _def(stock.chat_completion_request)
    (call,) = [n for n in ast.walk(expected) if isinstance(n, ast.Call) and getattr(n.func, "attr", None) == "stream"]
    (i,) = [k for k, kw in enumerate(call.keywords) if kw.arg == "temperature"]
    call.keywords[i] = ast.parse('f(extra_body={"temperature": temperature} if temperature is not None else None)'
                                 ).body[0].value.keywords[0]
    assert ast.dump(_def(port.chat_completion_request)) == ast.dump(expected)


@pytest.mark.parametrize("temperature, sent", [(None, None), (0.0, 0.0), (0.7, 0.7)])
def test_the_port_sends_temperature_exactly_when_the_stock_element_would(tmp_path, temperature, sent):
    agent = {**ANTHROPIC, "params": {**ANTHROPIC["params"], "temperature": temperature}}
    run = run_cell(tmp_path, CELL, agent, [MessagesReply.text(ANSWER)])
    (req,) = _requests(run)
    assert req.get("temperature") == sent and (("temperature" in req) == (sent is not None))
    items = {i["id"]: i for i in run.of("instrumentation")[0]["data"]["items"]}
    assert items["agentdojo.anthropic_element_port@1"]["kind"] == "behaviour_preserving"


def test_the_harness_sse_reader_matches_the_sdk_decoder():
    """Rebuild-window review R1-1: the harness parse_sse dispatches exactly the events the pinned SDK's SSEDecoder
    dispatches (20,000 seeded random streams over the grammar's corner cases)."""
    import random

    from anthropic._streaming import SSEDecoder

    from agentprov_backend.messages import parse_sse

    rng = random.Random(656)
    atoms = [b"data: a", b"data:b", b"data: ", b"event: e", b"event:", b": c", b"id: 1", b"retry: 2", b"x", b"",
             b"\n", b"\r", b"\r\n", b"\n\n", b"\r\n\r\n", "\ufeff".encode()]
    for _ in range(20_000):
        body = b"".join(rng.choice(atoms) for _ in range(rng.randrange(0, 14)))
        # an empty unnamed event is never accumulated by either reader: the SDK also dispatches one after an `id:`
        # line (it keeps the last event id), the harness does not read `id`; they are left out on both sides
        expected = [(e.event or "message", e.data) for e in SSEDecoder().iter_bytes(iter([body]))
                    if (e.event or "message", e.data) != ("message", "")]
        got = [(e.event, e.data) for e in parse_sse(body)[0] if (e.event, e.data) != ("message", "")]
        assert got == expected, body


def _serve_messages_on_loopback():
    """An HTTP/1.1 keep-alive server on 127.0.0.1 answering every request with a scripted Messages stream."""
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self):
            self.rfile.read(int(self.headers["content-length"]))
            status, headers, body = render_messages_response(MessagesReply.text("hi"), 0, stream=True)
            self.send_response(status)
            for k, v in headers.items():
                self.send_header(k, v)
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_the_inner_transport_keeps_no_connection_across_event_loops():
    """D-656 R-1 (confirmed by the live pilot's Part B): the stock element runs each query under a new asyncio.run with
    one AsyncAnthropic, so a kept-alive connection from a closed loop fails the next query. The SDK's default pool
    reproduces that against a loopback server; the harness's inner transport (no keep-alive) does not. The socket
    guard is lifted for this test only, for 127.0.0.1, and restored."""
    import anthropic

    from agentprov_backend._http import anthropic_httpx
    from agentprov_backend.testing import netguard
    from agentprov_backend.transport import default_async_inner_transport

    httpx = anthropic_httpx()
    harness = default_async_inner_transport(httpx)
    assert harness._pool._max_keepalive_connections == 0

    def run_three(transport, port):
        client = anthropic.AsyncAnthropic(api_key="not-a-secret-value", base_url=f"http://127.0.0.1:{port}",
                                          max_retries=0, http_client=anthropic.DefaultAsyncHttpxClient(transport=transport))

        async def call():
            async with client.messages.stream(model="m", max_tokens=8, messages=[{"role": "user", "content": "x"}]) as s:
                return await s.get_final_message()

        outcomes = []
        for _ in range(3):
            try:
                asyncio.run(call())
                outcomes.append("ok")
            except anthropic.APIConnectionError:
                outcomes.append("error")
        return outcomes

    from anthropic._constants import DEFAULT_CONNECTION_LIMITS

    netguard.uninstall()
    server = _serve_messages_on_loopback()
    try:
        port = server.server_address[1]
        stock = run_three(httpx.AsyncHTTPTransport(limits=DEFAULT_CONNECTION_LIMITS), port)
        assert stock == ["ok", "error", "ok"]  # the defect the pilot saw (c1 error, c2 ok)
        assert run_three(harness, port) == ["ok"] * 3
    finally:
        server.shutdown()
        server.server_close()
        netguard.install()
