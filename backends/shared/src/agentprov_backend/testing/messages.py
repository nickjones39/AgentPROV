"""Scripted Anthropic Messages API replies for ``ScriptedTransport`` (K.3.2; D-656). Synthetic: every byte is built
here, from the documented shapes of the Messages API; nothing was captured from the real API.

A Messages step is a :class:`~agentprov_backend.testing.transport.Step` with ``api = "anthropic_messages"``. It is
rendered per request: as a ``text/event-stream`` when the request body has ``"stream": true`` (AgentDojo's stock
``AnthropicLLM`` always streams), else as a JSON ``Message``. Builders:

* ``MessagesReply.text(str)``, ``.tool_use([...])``, ``.refusal()``, ``.empty()``; each may carry a leading thinking
  block (``thinking=``, with ``signature=``; ``thinking=""`` is what display ``omitted`` returns) or a
  ``redacted_thinking=`` block, and ``stop=`` overrides the stop reason (``max_tokens`` with a partial tool call);
* ``MessagesFail.http(status)`` (the Anthropic error body; ``retry_after=`` adds the header),
  ``.stream_error(type)`` (HTTP 200, then an ``error`` event mid-stream), ``.truncated(step, after=k)`` (the stream
  stops after k events, no ``message_stop``), ``.connection()``.

Deterministic: ids ``msg_scripted_<n>`` and ``toolu_scripted_<n>_<i>``; model ``scripted-fake`` unless the step names
one; usage ``{input_tokens: 100, output_tokens: 20, cache_read_input_tokens: 0, cache_creation_input_tokens: 0}``
unless the step says otherwise (``usage=None`` omits it). Text and JSON deltas are split into chunks of 16 characters,
so the SDK's accumulation is exercised.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Final

from agentprov_backend.testing.transport import ScriptError, Step

__all__ = [
    "API",
    "DEFAULT_MESSAGES_USAGE",
    "MessagesFail",
    "MessagesReply",
    "messages_step_from_dict",
    "render_messages_response",
]

API: Final = "anthropic_messages"
DEFAULT_MESSAGES_USAGE: Final[Mapping[str, int]] = {
    "input_tokens": 100, "output_tokens": 20, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
CHUNK: Final = 16
_UNSET: Any = object()

#: The error ``type`` the Messages API documents for each status.
ERROR_TYPES: Final[Mapping[int, str]] = {
    400: "invalid_request_error", 401: "authentication_error", 403: "permission_error", 404: "not_found_error",
    413: "request_too_large", 429: "rate_limit_error", 500: "api_error", 529: "overloaded_error",
}


def _reply(blocks: list[dict[str, Any]], *, stop: str, usage: Any, model: str | None, label: str,
           expect: Callable[[Any], bool] | None, thinking: str | None, signature: str | None,
           redacted_thinking: str | None) -> Step:
    lead: list[dict[str, Any]] = []
    if thinking is not None:
        lead.append({"type": "thinking", "thinking": thinking, "signature": signature or "c2NyaXB0ZWQtc2lnbmF0dXJl"})
    if redacted_thinking is not None:
        lead.append({"type": "redacted_thinking", "data": redacted_thinking})
    body = {"content": lead + blocks, "stop_reason": stop, "model": model,
            "usage": dict(DEFAULT_MESSAGES_USAGE) if usage is _UNSET else usage}
    return Step(200, body, expect=expect, label=label, api=API)


def _tool_block(call: Mapping[str, Any], i: int) -> dict[str, Any]:
    name = call.get("name")
    if not isinstance(name, str):
        raise ScriptError("tool call needs a 'name'")
    block: dict[str, Any] = {"type": "tool_use", "id": call.get("id"), "name": name, "input": call.get("args", {})}
    if "arguments" in call:  # raw partial_json text, streamed verbatim (may be malformed)
        if not isinstance(call["arguments"], str):
            raise ScriptError("tool call 'arguments' must be the raw JSON string")
        block["arguments"] = call["arguments"]
    block["_i"] = i
    return block


class MessagesReply:
    """Successful (HTTP 200) Messages replies."""

    @staticmethod
    def text(content: str, *, thinking: str | None = None, signature: str | None = None,
             redacted_thinking: str | None = None, usage: Any = _UNSET, stop: str = "end_turn",
             model: str | None = None, expect: Callable[[Any], bool] | None = None) -> Step:
        return _reply([{"type": "text", "text": content}], stop=stop, usage=usage, model=model, label="text",
                      expect=expect, thinking=thinking, signature=signature, redacted_thinking=redacted_thinking)

    @staticmethod
    def tool_use(calls: Sequence[Mapping[str, Any]], *, content: str | None = None, thinking: str | None = None,
                 signature: str | None = None, redacted_thinking: str | None = None, usage: Any = _UNSET,
                 stop: str = "tool_use", model: str | None = None,
                 expect: Callable[[Any], bool] | None = None) -> Step:
        blocks = [{"type": "text", "text": content}] if content is not None else []
        blocks += [_tool_block(c, i) for i, c in enumerate(calls)]
        return _reply(blocks, stop=stop, usage=usage, model=model, label="tool_use", expect=expect,
                      thinking=thinking, signature=signature, redacted_thinking=redacted_thinking)

    @staticmethod
    def refusal(*, content: str | None = None, usage: Any = _UNSET, model: str | None = None,
                expect: Callable[[Any], bool] | None = None) -> Step:
        """``stop_reason: "refusal"``: the Messages API sends no refusal text, only what was written before it."""
        blocks = [{"type": "text", "text": content}] if content is not None else []
        return _reply(blocks, stop="refusal", usage=usage, model=model, label="refusal", expect=expect,
                      thinking=None, signature=None, redacted_thinking=None)

    @staticmethod
    def empty(*, usage: Any = _UNSET, model: str | None = None, expect: Callable[[Any], bool] | None = None) -> Step:
        """No content blocks (AgentDojo then re-runs the pipeline)."""
        return _reply([], stop="end_turn", usage=usage, model=model, label="empty", expect=expect,
                      thinking=None, signature=None, redacted_thinking=None)


class MessagesFail:
    """Failures as the Messages API produces them."""

    @staticmethod
    def http(status: int, *, error_type: str | None = None, retry_after: str | None = None, should_retry: str | None = None,
             expect: Callable[[Any], bool] | None = None) -> Step:
        etype = error_type or ERROR_TYPES.get(status, "api_error")
        body = {"type": "error", "error": {"type": etype, "message": f"scripted HTTP {status}"}}
        headers: dict[str, str] = {}
        if retry_after is not None:
            headers["retry-after"] = retry_after
        if should_retry is not None:
            headers["x-should-retry"] = should_retry
        return Step(status, body, headers=headers, expect=expect, label=f"http_{status}", api=API)

    @staticmethod
    def stream_error(error_type: str = "overloaded_error", *, expect: Callable[[Any], bool] | None = None) -> Step:
        """HTTP 200 with ``message_start`` and ``ping``, then an ``error`` event (the stream then ends)."""
        step = MessagesReply.text("partial", expect=expect)
        return Step(200, step.body, expect=expect, label="stream_error", api=API, stream_error=error_type)

    @staticmethod
    def truncated(step: Step, *, after: int) -> Step:
        """``step`` streamed, but cut after ``after`` events (no ``message_stop``)."""
        if step.api != API or step.status != 200 or after < 1:
            raise ScriptError("truncated needs a Messages reply and after >= 1")
        return Step(200, step.body, expect=step.expect, label="truncated", api=API, stream_cut=after)

    @staticmethod
    def connection(message: str = "scripted connection failure", *,
                   expect: Callable[[Any], bool] | None = None) -> Step:
        return Step(0, None, expect=expect, raise_connect=message, label="connection", api=API)


# ------------------------------------------------------------------------------------------------ rendering
def _chunks(text: str) -> list[str]:
    return [text[i:i + CHUNK] for i in range(0, len(text), CHUNK)] or [""]


def _final_blocks(content: Sequence[Mapping[str, Any]], n: int) -> list[dict[str, Any]]:
    out = []
    for block in content:
        b = {k: v for k, v in block.items() if k not in ("_i", "arguments")}
        if b.get("type") == "tool_use":
            if b.get("id") is None:
                b["id"] = f"toolu_scripted_{n}_{block['_i']}"
            if "arguments" in block:
                raise ScriptError("a raw-arguments tool call can only be streamed")
        out.append(b)
    return out


def _sse(event: str, payload: Mapping[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n"


def _stream_events(body: Mapping[str, Any], n: int, model: str) -> list[str]:
    usage = body.get("usage")
    start_usage = None
    if isinstance(usage, Mapping):
        start_usage = {k: v for k, v in usage.items() if k != "output_tokens"} | {"output_tokens": 1}
    message: dict[str, Any] = {"id": f"msg_scripted_{n}", "type": "message", "role": "assistant", "content": [],
                               "model": body.get("model") or model, "stop_reason": None, "stop_sequence": None}
    if start_usage is not None:
        message["usage"] = start_usage
    events = [_sse("message_start", {"type": "message_start", "message": message}), _sse("ping", {"type": "ping"})]
    for index, block in enumerate(body.get("content") or []):
        kind = block.get("type")
        if kind == "text":
            events.append(_sse("content_block_start", {"type": "content_block_start", "index": index,
                                                       "content_block": {"type": "text", "text": ""}}))
            for piece in _chunks(block.get("text") or ""):
                events.append(_sse("content_block_delta", {"type": "content_block_delta", "index": index,
                                                           "delta": {"type": "text_delta", "text": piece}}))
        elif kind == "thinking":
            events.append(_sse("content_block_start", {"type": "content_block_start", "index": index,
                                                       "content_block": {"type": "thinking", "thinking": "",
                                                                         "signature": ""}}))
            if block.get("thinking"):
                for piece in _chunks(block["thinking"]):
                    events.append(_sse("content_block_delta", {"type": "content_block_delta", "index": index,
                                                               "delta": {"type": "thinking_delta", "thinking": piece}}))
            events.append(_sse("content_block_delta", {"type": "content_block_delta", "index": index,
                                                       "delta": {"type": "signature_delta",
                                                                 "signature": block.get("signature", "")}}))
        elif kind == "tool_use":
            tid = block.get("id") or f"toolu_scripted_{n}_{block['_i']}"
            events.append(_sse("content_block_start", {"type": "content_block_start", "index": index,
                                                       "content_block": {"type": "tool_use", "id": tid,
                                                                         "name": block["name"], "input": {}}}))
            raw = block["arguments"] if "arguments" in block else json.dumps(block.get("input", {}),
                                                                               separators=(",", ":"))
            for piece in _chunks(raw):
                events.append(_sse("content_block_delta", {"type": "content_block_delta", "index": index,
                                                           "delta": {"type": "input_json_delta",
                                                                     "partial_json": piece}}))
        else:  # redacted_thinking and anything else: the whole block at start
            events.append(_sse("content_block_start", {"type": "content_block_start", "index": index,
                                                       "content_block": dict(block)}))
        events.append(_sse("content_block_stop", {"type": "content_block_stop", "index": index}))
    delta: dict[str, Any] = {"type": "message_delta",
                             "delta": {"stop_reason": body.get("stop_reason"), "stop_sequence": None}}
    if isinstance(usage, Mapping) and "output_tokens" in usage:
        delta["usage"] = {"output_tokens": usage["output_tokens"]}
    events.append(_sse("message_delta", delta))
    events.append(_sse("message_stop", {"type": "message_stop"}))
    return events


def render_messages_response(step: Step, n: int, *, stream: bool,
                             model: str = "scripted-fake") -> tuple[int, dict[str, str], bytes]:
    """The exact response ``ScriptedTransport`` serves for a Messages ``step`` as the ``n``-th wire request."""
    if step.raise_connect is not None:
        raise ValueError("a connection-failure step has no response")
    body = step.body
    if step.status != 200:
        payload = dict(body) | {"request_id": f"req_scripted_{n}"}
        return step.status, {"content-type": "application/json", "request-id": f"req_scripted_{n}", **step.headers}, \
            json.dumps(payload, separators=(",", ":")).encode("utf-8")
    if not stream:
        if step.stream_error is not None or step.stream_cut is not None:
            raise ScriptError(f"step {step.label!r} can only answer a streaming request")
        message = {"id": f"msg_scripted_{n}", "type": "message", "role": "assistant",
                   "model": body.get("model") or model, "content": _final_blocks(body.get("content") or [], n),
                   "stop_reason": body.get("stop_reason"), "stop_sequence": None}
        if body.get("usage") is not None:
            message["usage"] = body["usage"]
        return 200, {"content-type": "application/json", "request-id": f"req_scripted_{n}", **step.headers}, \
            json.dumps(message, separators=(",", ":")).encode("utf-8")
    events = _stream_events(body, n, model)
    if step.stream_error is not None:
        events = events[:2] + [_sse("error", {"type": "error", "error": {"type": step.stream_error,
                                                                         "message": "scripted stream error"}})]
    elif step.stream_cut is not None:
        events = events[:step.stream_cut]
    headers = {"content-type": "text/event-stream; charset=utf-8", "request-id": f"req_scripted_{n}", **step.headers}
    return 200, headers, "".join(events).encode("utf-8")


# ------------------------------------------------------------------------------------------------ JSON scripts
def messages_step_from_dict(d: Mapping[str, Any]) -> Step:
    """A Messages step from its JSON form (a script with ``"api": "anthropic_messages"``). Forms::

        {"reply": "text", "content": "..."}       {"reply": "tool_use", "calls": [{"name": ..., "args": {...}}
        {"reply": "refusal"}  {"reply": "empty"}    | {"name": ..., "arguments": "<raw>"}], "content"?: "..."}
        {"fail": "http", "status": 529, "retry_after"?: "1"}   {"fail": "stream_error", "error"?: "overloaded_error"}
        {"fail": "connection"}   {"stall": 600}

    Optional members of replies: ``thinking`` (+ ``signature``), ``redacted_thinking``, ``usage`` (an object, or
    ``null`` for none), ``model``, ``stop``, ``cut_after`` (stream only: stop after that many events).
    """
    from agentprov_backend.testing.transport import step_from_dict

    if not isinstance(d, Mapping):
        raise ScriptError("a step must be an object")
    if "stall" in d:
        return step_from_dict(d)
    usage = d["usage"] if "usage" in d else _UNSET
    common = {"usage": usage, "model": d.get("model")}
    lead = {"thinking": d.get("thinking"), "signature": d.get("signature"), "redacted_thinking": d.get("redacted_thinking")}
    for key in ("thinking", "signature", "redacted_thinking", "model", "stop"):
        if d.get(key) is not None and not isinstance(d[key], str):
            raise ScriptError(f"{key} must be a string")
    if "reply" in d:
        kind = d["reply"]
        if kind == "text":
            if not isinstance(d.get("content"), str):
                raise ScriptError("text needs a string 'content'")
            step = MessagesReply.text(d["content"], stop=d.get("stop", "end_turn"), **lead, **common)
        elif kind == "tool_use":
            calls = d.get("calls")
            if not isinstance(calls, list) or not calls or not all(isinstance(c, Mapping) for c in calls):
                raise ScriptError("tool_use needs a non-empty 'calls' list")
            step = MessagesReply.tool_use(calls, content=d.get("content"), stop=d.get("stop", "tool_use"), **lead,
                                          **common)
        elif kind == "refusal":
            step = MessagesReply.refusal(content=d.get("content"), **common)
        elif kind == "empty":
            step = MessagesReply.empty(**common)
        else:
            raise ScriptError(f"unknown reply kind {kind!r}")
        if "cut_after" in d:
            after = d["cut_after"]
            if not isinstance(after, int) or isinstance(after, bool):
                raise ScriptError("cut_after must be an integer")
            step = MessagesFail.truncated(step, after=after)
        return step
    if "fail" in d:
        kind = d["fail"]
        if kind == "http":
            status = d.get("status")
            if not isinstance(status, int) or isinstance(status, bool) or not 400 <= status <= 599:
                raise ScriptError("http failure needs a 4xx/5xx 'status'")
            return MessagesFail.http(status, error_type=d.get("error"), retry_after=d.get("retry_after"))
        if kind == "stream_error":
            return MessagesFail.stream_error(d.get("error", "overloaded_error"))
        if kind == "connection":
            return MessagesFail.connection()
        raise ScriptError(f"unknown failure kind {kind!r}")
    raise ScriptError("a step needs 'reply', 'fail' or 'stall'")
