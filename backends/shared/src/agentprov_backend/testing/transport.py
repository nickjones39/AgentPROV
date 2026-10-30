"""``ScriptedTransport``: a scripted OpenAI-compatible chat-completions server as an HTTP transport (K.3.2; AD-01(e)).

It is installed as the *inner* transport under the recording transport of the real SDK client that the stock LLM
element uses, so the request the SDK builds and the response it parses are genuine wire bytes (K.8.1). It is built on
the ``MockTransport`` of the httpx-family module the installed SDK uses (``httpx2`` for ``openai`` 3.x; see
``agentprov_backend._http``).

A script is a list of steps, one per wire request, consumed in order:

* ``Reply.tool_calls([...])``, ``Reply.text(str)``, ``Reply.null()``, ``Reply.refusal(str)``, ``Reply.reasoning(...)``;
* ``Fail.http(status)``, ``Fail.malformed_args(raw)``, ``Fail.no_choices()``, ``Fail.finish_error()``,
  ``Fail.context_length()``, ``Fail.connection()``.

Each step may carry ``expect=lambda request: bool``, checked against the wire request; a failed expectation raises
``ScriptExpectationFailed``. Exhausting the script raises ``ScriptExhausted`` (the test fails instead of hanging).
``requests`` and ``bodies`` keep every request verbatim. A script can also be loaded from a JSON file
(``load_script``), which is how the worker receives one (``AgentConfig.script``, a label inside the session).

The responses are deterministic: ids ``scripted-<n>``, ``created: 0``, the model ``scripted-fake`` unless a step names
another, and usage ``{prompt_tokens: 100, completion_tokens: 20, total_tokens: 120}`` unless a step says otherwise
(``usage=None`` omits it, as DeepSeek-style providers do).

Anthropic Messages steps (``testing.messages``; D-656) are steps with ``api = "anthropic_messages"``, rendered per
request (SSE when the request streams, else JSON). A JSON script for them is ``{"api": "anthropic_messages", "steps":
[...]}``. The transport serves sync and async clients alike (``MockTransport``), so the stock async element runs on its
normal code path.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agentprov_backend._http import sdk_httpx

__all__ = [
    "DEFAULT_USAGE",
    "Fail",
    "Reply",
    "Script",
    "ScriptError",
    "ScriptExhausted",
    "ScriptExpectationFailed",
    "ScriptedTransport",
    "Step",
    "load_script",
    "render_response",
    "step_from_dict",
]

_httpx = sdk_httpx()

DEFAULT_USAGE: Mapping[str, int] = {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}
_UNSET: Any = object()
MAX_SCRIPT_BYTES = 4 * 1024 * 1024


class ScriptError(ValueError):
    """A malformed script."""


class ScriptExhausted(Exception):
    """More wire requests were made than the script has steps."""


class ScriptExpectationFailed(AssertionError):
    """A step's ``expect`` predicate rejected the wire request."""


@dataclass(frozen=True)
class Step:
    """One scripted wire response. ``status`` and ``body`` are what the server returns; ``raise_connect`` makes the
    transport raise a connection error instead (no response)."""

    status: int
    body: Any  # a JSON value (dict) or raw bytes
    headers: Mapping[str, str] = field(default_factory=dict)
    expect: Callable[[Any], bool] | None = None
    raise_connect: str | None = None
    label: str = ""
    #: seconds the transport blocks before answering (test-only: a forced-kill scenario needs a cell that is still
    #: running when the parent kills the worker); an ``Event.wait``, so patched sleeps do not shorten it
    stall_s: float = 0.0
    #: the wire format the step answers in: ``openai_chat`` or ``anthropic_messages`` (``testing.messages``)
    api: str = "openai_chat"
    #: Messages streams only: an ``error`` event of this type replaces the content (HTTP 200)
    stream_error: str | None = None
    #: Messages streams only: stop after this many events (no ``message_stop``)
    stream_cut: int | None = None


Script = list[Step]


def _usage(usage: Any) -> Any:
    return dict(DEFAULT_USAGE) if usage is _UNSET else usage


def _completion(message: dict[str, Any], *, finish: str | None, usage: Any, model: str | None,
                extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "id": None,  # filled per request with scripted-<n>
        "object": "chat.completion",
        "created": 0,
        "model": model,
        "choices": [{"index": 0, "finish_reason": finish, "message": message}],
    }
    u = _usage(usage)
    if u is not None:
        body["usage"] = u
    if extra:
        body.update(extra)
    return body


def _tool_call(call: Mapping[str, Any], i: int) -> dict[str, Any]:
    if "arguments" in call:
        arguments = call["arguments"]
        if not isinstance(arguments, str):
            raise ScriptError("tool call 'arguments' must be the raw JSON string")
    else:
        arguments = json.dumps(call.get("args", {}))
    name = call.get("name")
    if not isinstance(name, str):
        raise ScriptError("tool call needs a 'name'")
    cid = call.get("id", f"call_{i}")
    return {"id": cid, "type": "function", "function": {"name": name, "arguments": arguments}}


def _assistant(content: Any, *, tool_calls: list[dict[str, Any]] | None = None, refusal: str | None = None,
               reasoning: str | None = None, reasoning_field: str = "reasoning",
               reasoning_details: Any = None) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if tool_calls:
        message["tool_calls"] = tool_calls
    if refusal is not None:
        message["refusal"] = refusal
    if reasoning is not None:
        message[reasoning_field] = reasoning
    if reasoning_details is not None:
        message["reasoning_details"] = reasoning_details
    return message


class Reply:
    """Successful (HTTP 200) chat-completion replies."""

    @staticmethod
    def tool_calls(calls: Sequence[Mapping[str, Any]], *, content: str | None = None, reasoning: str | None = None,
                   reasoning_details: Any = None, usage: Any = _UNSET, finish: str = "tool_calls",
                   model: str | None = None, expect: Callable[[Any], bool] | None = None) -> Step:
        tcs = [_tool_call(c, i) for i, c in enumerate(calls)]
        msg = _assistant(content, tool_calls=tcs, reasoning=reasoning, reasoning_details=reasoning_details)
        return Step(200, _completion(msg, finish=finish, usage=usage, model=model), expect=expect, label="tool_calls")

    @staticmethod
    def text(content: str, *, reasoning: str | None = None, reasoning_details: Any = None, usage: Any = _UNSET,
             finish: str = "stop", model: str | None = None, extra: Mapping[str, Any] | None = None,
             expect: Callable[[Any], bool] | None = None) -> Step:
        msg = _assistant(content, reasoning=reasoning, reasoning_details=reasoning_details)
        return Step(200, _completion(msg, finish=finish, usage=usage, model=model, extra=extra), expect=expect,
                    label="text")

    @staticmethod
    def null(*, usage: Any = _UNSET, finish: str = "stop", model: str | None = None,
             expect: Callable[[Any], bool] | None = None) -> Step:
        """A reply with ``content: null`` and no tool calls (AgentDojo then re-runs the pipeline)."""
        return Step(200, _completion(_assistant(None), finish=finish, usage=usage, model=model), expect=expect,
                    label="null")

    @staticmethod
    def refusal(text: str, *, usage: Any = _UNSET, model: str | None = None,
                expect: Callable[[Any], bool] | None = None) -> Step:
        msg = _assistant(None, refusal=text)
        return Step(200, _completion(msg, finish="stop", usage=usage, model=model), expect=expect, label="refusal")

    @staticmethod
    def reasoning(content: str | None, reasoning: str, *, field: str = "reasoning", details: Any = None,
                  usage: Any = _UNSET, model: str | None = None,
                  expect: Callable[[Any], bool] | None = None) -> Step:
        """A text reply carrying provider reasoning (``reasoning`` as OpenRouter, ``reasoning_content`` as
        DeepSeek), optionally with ``reasoning_details``."""
        msg = _assistant(content, reasoning=reasoning, reasoning_field=field, reasoning_details=details)
        return Step(200, _completion(msg, finish="stop", usage=usage, model=model), expect=expect, label="reasoning")


class Fail:
    """Failures as a provider produces them."""

    @staticmethod
    def http(status: int, *, body: Any = None, headers: Mapping[str, str] | None = None, code: str | None = None,
             expect: Callable[[Any], bool] | None = None) -> Step:
        if body is None:
            err: dict[str, Any] = {"message": f"scripted HTTP {status}", "type": "scripted_error"}
            if code is not None:
                err["code"] = code
            body = {"error": err}
        return Step(status, body, headers=dict(headers or {}), expect=expect, label=f"http_{status}")

    @staticmethod
    def context_length(*, expect: Callable[[Any], bool] | None = None) -> Step:
        """HTTP 400 with ``code: context_length_exceeded``: the error AgentDojo's runner catches and imposes an
        outcome for (``benchmark.py:120-131``)."""
        return Fail.http(400, code="context_length_exceeded", expect=expect)

    @staticmethod
    def malformed_args(raw: str, *, name: str = "get_most_recent_transactions", call_id: str = "call_1",
                       usage: Any = _UNSET, expect: Callable[[Any], bool] | None = None) -> Step:
        step = Reply.tool_calls([{"name": name, "arguments": raw, "id": call_id}], usage=usage, expect=expect)
        return Step(step.status, step.body, expect=expect, label="malformed_args")

    @staticmethod
    def no_choices(*, error: Any = _UNSET, expect: Callable[[Any], bool] | None = None) -> Step:
        """A 200 with no ``choices`` and a top-level ``error`` (OpenRouter's upstream failure)."""
        err = {"code": 502, "message": "upstream provider unavailable"} if error is _UNSET else error
        body: dict[str, Any] = {"id": None, "object": "chat.completion", "created": 0, "model": None,
                                "choices": None}
        if err is not None:
            body["error"] = err
        return Step(200, body, expect=expect, label="no_choices")

    @staticmethod
    def finish_error(content: str = "partial", *, expect: Callable[[Any], bool] | None = None) -> Step:
        """A 200 whose choice has ``finish_reason: "error"`` (an upstream failure with partial content)."""
        step = Reply.text(content, finish="error", expect=expect)
        return Step(step.status, step.body, expect=expect, label="finish_error")

    @staticmethod
    def connection(message: str = "scripted connection failure",
                   *, expect: Callable[[Any], bool] | None = None) -> Step:
        return Step(0, None, expect=expect, raise_connect=message, label="connection")


def step_from_dict(d: Mapping[str, Any]) -> Step:
    """A step from its JSON form (the worker's script file). Forms::

        {"reply": "tool_calls", "calls": [{"name": ..., "args": {...}} | {"name": ..., "arguments": "<raw>"}], ...}
        {"reply": "text", "content": "..."}     {"reply": "null"}     {"reply": "refusal", "refusal": "..."}
        {"reply": "reasoning", "content": "...", "reasoning": "...", "field": "reasoning"|"reasoning_content"}
        {"fail": "http", "status": 503}          {"fail": "context_length"}    {"fail": "malformed_args", "raw": "..."}
        {"fail": "no_choices"}                   {"fail": "finish_error"}      {"fail": "connection"}
        {"raw": {"status": 200, "json": {...}, "headers": {...}}}
        {"stall": 600}        (test only: block that many seconds, then fail as a connection error)

    Optional members of replies: ``usage`` (an object, or ``null`` for none), ``model``, ``finish``.
    """
    if not isinstance(d, Mapping):
        raise ScriptError("a step must be an object")
    usage = d["usage"] if "usage" in d else _UNSET
    model = d.get("model")
    if "reply" in d:
        kind = d["reply"]
        if kind == "tool_calls":
            calls = d.get("calls")
            if not isinstance(calls, list) or not calls:
                raise ScriptError("tool_calls needs a non-empty 'calls' list")
            return Reply.tool_calls(calls, content=d.get("content"), reasoning=d.get("reasoning"),
                                    reasoning_details=d.get("reasoning_details"), usage=usage,
                                    finish=d.get("finish", "tool_calls"), model=model)
        if kind == "text":
            content = d.get("content")
            if not isinstance(content, str):
                raise ScriptError("text needs a string 'content'")
            return Reply.text(content, reasoning=d.get("reasoning"), reasoning_details=d.get("reasoning_details"),
                              usage=usage, finish=d.get("finish", "stop"), model=model)
        if kind == "null":
            return Reply.null(usage=usage, finish=d.get("finish", "stop"), model=model)
        if kind == "refusal":
            return Reply.refusal(str(d.get("refusal", "")), usage=usage, model=model)
        if kind == "reasoning":
            return Reply.reasoning(d.get("content"), str(d.get("reasoning", "")), field=d.get("field", "reasoning"),
                                   details=d.get("reasoning_details"), usage=usage, model=model)
        raise ScriptError(f"unknown reply kind {kind!r}")
    if "fail" in d:
        kind = d["fail"]
        if kind == "http":
            status = d.get("status")
            if not isinstance(status, int) or isinstance(status, bool) or not 400 <= status <= 599:
                raise ScriptError("http failure needs a 4xx/5xx 'status'")
            return Fail.http(status, body=d.get("body"), headers=d.get("headers"), code=d.get("code"))
        if kind == "context_length":
            return Fail.context_length()
        if kind == "malformed_args":
            return Fail.malformed_args(str(d.get("raw", "")), name=d.get("name", "get_most_recent_transactions"),
                                       call_id=d.get("id", "call_1"), usage=usage)
        if kind == "no_choices":
            return Fail.no_choices(error=d["error"] if "error" in d else _UNSET)
        if kind == "finish_error":
            return Fail.finish_error(d.get("content", "partial"))
        if kind == "connection":
            return Fail.connection()
        raise ScriptError(f"unknown failure kind {kind!r}")
    if "stall" in d:
        seconds = d["stall"]
        if not isinstance(seconds, (int, float)) or isinstance(seconds, bool) or not 0 < seconds <= 3600:
            raise ScriptError("stall needs a number of seconds in (0, 3600]")
        return Step(0, None, raise_connect="scripted stall elapsed", label="stall", stall_s=float(seconds))
    if "raw" in d:
        raw = d["raw"]
        if not isinstance(raw, Mapping) or not isinstance(raw.get("status"), int):
            raise ScriptError("raw needs a 'status'")
        return Step(raw["status"], raw.get("json"), headers=dict(raw.get("headers") or {}), label="raw")
    raise ScriptError("a step needs 'reply', 'fail' or 'raw'")


def _reject_constant(name: str) -> Any:
    raise ScriptError(f"non-standard JSON constant {name}")


def load_script(path: Path) -> Script:
    """Load a JSON script file: a list of step objects, or ``{"steps": [...]}``. Bounded and strict (no NaN, no
    duplicate keys)."""
    data = Path(path).read_bytes()
    if len(data) > MAX_SCRIPT_BYTES:
        raise ScriptError("script file too large")

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for k, v in items:
            if k in out:
                raise ScriptError(f"duplicate key {k!r}")
            out[k] = v
        return out

    doc = json.loads(data.decode("utf-8"), object_pairs_hook=pairs, parse_constant=_reject_constant)
    steps = doc.get("steps") if isinstance(doc, dict) else doc
    if not isinstance(steps, list):
        raise ScriptError("a script is a list of steps")
    api = doc.get("api", "openai_chat") if isinstance(doc, dict) else "openai_chat"
    if api == "anthropic_messages":
        from agentprov_backend.testing.messages import messages_step_from_dict

        return [messages_step_from_dict(s) for s in steps]
    if api != "openai_chat":
        raise ScriptError(f"unknown script api {api!r}")
    return [step_from_dict(s) for s in steps]


class ScriptedTransport(_httpx.MockTransport):  # type: ignore[misc, name-defined]
    """An httpx-family transport answering each wire request with the next scripted step."""

    def __init__(self, script: Sequence[Step], *, model: str = "scripted-fake") -> None:
        self.script: list[Step] = list(script)
        self.model = model
        self.requests: list[Any] = []
        self.bodies: list[bytes] = []
        self.position = 0
        super().__init__(self._handle)

    @property
    def remaining(self) -> int:
        return len(self.script) - self.position

    def _handle(self, request: Any) -> Any:
        body = request.read()
        self.requests.append(request)
        self.bodies.append(bytes(body))
        if self.position >= len(self.script):
            raise ScriptExhausted(f"script exhausted after {len(self.script)} steps")
        n = self.position
        step = self.script[n]
        self.position += 1
        if step.expect is not None and not step.expect(request):
            raise ScriptExpectationFailed(f"step {n} ({step.label}) rejected the request")
        if step.stall_s > 0:
            import threading

            threading.Event().wait(step.stall_s)
        if step.raise_connect is not None:
            raise _httpx.ConnectError(step.raise_connect, request=request)
        if step.api == "anthropic_messages":
            from agentprov_backend.testing.messages import render_messages_response

            try:
                sent = json.loads(bytes(body).decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                sent = None
            stream = isinstance(sent, dict) and sent.get("stream") is True
            status, headers, content = render_messages_response(step, n, stream=stream, model=self.model)
            return _httpx.Response(status, headers=headers, content=content)
        status, headers, content = render_response(step, n, model=self.model)
        return _httpx.Response(status, headers=headers, content=content)


def render_response(step: Step, n: int, *, model: str = "scripted-fake") -> tuple[int, dict[str, str], bytes]:
    """The exact response ``ScriptedTransport`` serves for ``step`` as the ``n``-th (0-based) wire request: status,
    headers and body bytes (a chat completion gets ``id = scripted-<n>`` and, when it names none, ``model``). Gate C6
    serves the same bytes to the baseline package (``tools/migration/baseline_probe.py``). A ``raise_connect`` step has
    no response (``ValueError``)."""
    if step.raise_connect is not None:
        raise ValueError("a connection-failure step has no response")
    headers = {"content-type": "application/json", **step.headers}
    if isinstance(step.body, (bytes, bytearray)):
        content = bytes(step.body)
    else:
        payload = step.body
        if isinstance(payload, dict) and payload.get("object") == "chat.completion":
            payload = dict(payload)
            payload["id"] = f"scripted-{n}"
            if payload.get("model") is None and "choices" in payload and payload["choices"] is not None:
                payload["model"] = model
        content = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return step.status, headers, content
