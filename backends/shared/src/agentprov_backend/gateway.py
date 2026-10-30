"""LLM spans and the opt-in ``gateway_compat`` element (D.10.1, D.10.5; AD-09; C.13.3 ``llm.request``/``llm.response``).

* ``LlmSpan`` brackets one invocation of an LLM element. On entry it records ``n_messages`` (the length of the pass's
  native message list the element was given) and ``input_at`` (the positions of the messages the request was built
  from). It never touches a request.
* ``WireRecorder`` is the observer of the recording transport (``transport.RecordingTransport``): it turns each wire
  exchange into an ``llm.request`` (before the send) and an ``llm.response`` event, attaching the active span's
  ``input_at``/``n_messages``, the retry index and ``retry_of``.
* ``SpannedLLM`` is the pipeline element written ``LlmSpan(llm)`` in D.10.5: it wraps the LLM element and opens a
  span around each call.
* ``GatewayLLM`` is the faithful port of the baseline ``_CompatLLM`` (``agentdojo_prov/runtime.py:121-393`` at
  ``579a908``), used only under ``llm_element = "gateway_compat"`` and declared as instrumentation (D.10.7).

``SpannedLLM`` and ``GatewayLLM`` subclass AgentDojo classes and are imported lazily (``agentprov_backend._llm``), so
this module itself imports no benchmark code.

**Kept/discarded/error** (``llm.response.status``). A non-2xx reply or a transport failure is ``error`` at once. A 2xx
reply is decided when its fate is known: ``kept`` when the element returns normally with it, ``discarded`` when another
request follows it inside the same span (``superseded_by_retry``) or when the element raises after receiving it
(``element_raised:<Type>``); ``GatewayLLM`` decides explicitly with ``mark_kept``/``mark_discarded`` and a reason. The
``llm.response`` event of a 2xx reply is therefore emitted when its status is decided, which is after the element has
parsed it (D.10.10 item 4).

**input_at.** The stock OpenAI element and ``GatewayLLM`` build the request from every message they are given, in
order, so ``input_at`` is ``[0, ..., n_messages-1]``. The recorder checks this against the decoded wire request: when
the request does not carry exactly ``n_messages`` messages, ``input_at`` is omitted (``n_messages`` is kept) and a note
``input_at_unverified`` is written, so context membership falls back to the alignment rule (C.13.7) instead of being
claimed as observed.

**The Messages wire (D-656).** ``WireRecorder(api="anthropic_messages")`` records the Anthropic Messages API. The
request's ``system`` member is content, not a parameter, so it is left out of ``params.transmitted`` as ``messages`` is.
``input_at`` is verified against the stock ``AnthropicLLM`` rendering (``messages.stock_wire_count``: the leading system
message is lifted into ``system`` and runs of user/tool messages are merged into one turn), not against a one-to-one
count. Response facts come from the JSON body or the rebuilt ``text/event-stream`` (``messages``). A 2xx body that
carries a provider error (an ``error`` event in a stream, or an error object) is no model reply: it is ``error`` at
once, with reason ``stream_error:<type>`` or ``error_object:<type>``. A stream that ends without ``message_stop`` gets a
note ``stream_incomplete``; its fate decides its status as for any 2xx reply.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from agentprov_backend import messages as _messages
from agentprov_backend._jsonval import encode_value, escape_text

__all__ = ["GatewayLLM", "LlmSpan", "SpannedLLM", "WireRecorder", "decode_json_body", "response_facts"]  # noqa: F822

_NON_PARAM_KEYS = frozenset({"model", "messages", "tools"})
#: The Messages API carries the system prompt in its own member: content, not a parameter.
_NON_PARAM_KEYS_MESSAGES = _NON_PARAM_KEYS | {"system"}
_API_KINDS = ("openai_chat", "anthropic_messages")
_ERROR_TYPE = re.compile(r"[a-z][a-z0-9_]{0,63}")


def __getattr__(name: str) -> Any:  # PEP 562: the AgentDojo-dependent classes load on first use
    if name in ("GatewayLLM", "SpannedLLM"):
        from agentprov_backend import _llm

        return getattr(_llm, name)
    raise AttributeError(name)


def _reject_constant(name: str) -> Any:
    raise ValueError(name)


def decode_json_body(body: bytes) -> Any:
    """Strictly decode a JSON body (no NaN/Infinity); ``None`` when it is not JSON."""
    try:
        return json.loads(body.decode("utf-8"), parse_constant=_reject_constant)
    except (UnicodeDecodeError, ValueError, RecursionError):
        return None


def _nonneg_int(v: Any) -> int | None:
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else None


def response_facts(decoded: Any) -> dict[str, Any]:
    """``usage``, ``finish_reason``, ``served_model`` and ``response_id`` of a decoded chat-completion body, as the
    provider reported them (AER usage names; C.13.3)."""
    out: dict[str, Any] = {}
    if not isinstance(decoded, Mapping):
        return out
    if isinstance(decoded.get("id"), str):
        out["response_id"] = decoded["id"]
    if isinstance(decoded.get("model"), str):
        out["served_model"] = decoded["model"]
    choices = decoded.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], Mapping):
        fr = choices[0].get("finish_reason")
        if isinstance(fr, str):
            out["finish_reason"] = fr
    usage = decoded.get("usage")
    if isinstance(usage, Mapping):
        u: dict[str, int] = {}
        for src, dst in (("prompt_tokens", "input_tokens"), ("completion_tokens", "output_tokens"),
                         ("total_tokens", "total_tokens")):
            v = _nonneg_int(usage.get(src))
            if v is not None:
                u[dst] = v
        ctd = usage.get("completion_tokens_details")
        if isinstance(ctd, Mapping) and _nonneg_int(ctd.get("reasoning_tokens")) is not None:
            u["reasoning_tokens"] = ctd["reasoning_tokens"]
        ptd = usage.get("prompt_tokens_details")
        if isinstance(ptd, Mapping) and _nonneg_int(ptd.get("cached_tokens")) is not None:
            u["cache_read_tokens"] = ptd["cached_tokens"]
        if u:
            out["usage"] = u
    return out


def _media(headers: Any, default: str) -> str:
    try:
        ct = headers.get("content-type")
    except Exception:  # noqa: BLE001
        ct = None
    if isinstance(ct, str) and ct:
        return ct.split(";", 1)[0].strip().lower() or default
    return default


class LlmSpan:
    """Brackets one LLM-element invocation (D.10.1 ``LlmSpan`` protocol)."""

    def __init__(self, session: Any, role: str, actor: str, messages: Sequence[Any] = ()) -> None:
        self.session = session
        self.role = role
        self.actor = actor
        self.n_messages = len(messages)
        #: the roles of the messages the element was given (the Messages-format ``input_at`` check reads them)
        self.roles: list[object] = [m.get("role") if isinstance(m, Mapping) else None for m in messages]
        self.input_at: list[int] = list(range(self.n_messages))
        self.n_wire = 0
        self.last_call: str | None = None
        self.calls: list[str] = []
        self._pending: dict[str, Any] | None = None

    def __enter__(self) -> LlmSpan:
        self.session.current_span = self
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        try:
            if self._pending is not None and not self.session.poisoned:
                if exc_type is None:
                    self._flush("kept", None)
                else:
                    self._flush("discarded", f"element_raised:{exc_type.__name__}")
        finally:
            if self.session.current_span is self:
                self.session.current_span = None
        return False

    # explicit decisions (GatewayLLM)
    def mark_kept(self, call: str) -> None:
        if self._pending is not None and self._pending["call"] == call:
            self._flush("kept", None)

    def mark_discarded(self, call: str, reason: str) -> None:
        if self._pending is not None and self._pending["call"] == call:
            self._flush("discarded", reason)

    @property
    def pending_call(self) -> str | None:
        return None if self._pending is None else self._pending["call"]

    def _flush(self, status: str, reason: str | None) -> None:
        pending, self._pending = self._pending, None
        if pending is None:
            return
        data = {"call": pending["call"], "status": status, "http_status": pending["http_status"],
                "response": pending["response"], **pending["facts"]}
        if reason is not None:
            data["reason"] = reason
        self.session.emit("llm.response", data, actor=self.actor)
        if pending.get("after") is not None:
            pending["after"]()
        self.session.step("model_call", call=pending["call"], status=status)

    def _set_pending(self, call: str, http_status: int, blob: Mapping[str, Any], facts: Mapping[str, Any],
                     after: Any = None) -> None:
        self._flush("discarded", "superseded_by_retry")
        self._pending = {"call": call, "http_status": http_status, "response": dict(blob), "facts": dict(facts),
                         "after": after}


class WireRecorder:
    """The recording transport's observer for one capture session (``transport.WireObserver``)."""

    def __init__(self, session: Any, *, configured_params: Mapping[str, Any] | None = None,
                 endpoint: Any = None, api: str | None = None) -> None:
        self.session = session
        self.configured = encode_value(dict(configured_params or {}))
        self.endpoint = endpoint
        #: the wire format: ``api`` when given, else the endpoint's, else ``openai_chat``
        self.api = api or getattr(endpoint, "api", None) or _API_KINDS[0]
        if self.api not in _API_KINDS:
            raise ValueError(f"unknown wire format {self.api!r}")

    @property
    def is_messages(self) -> bool:
        return self.api == "anthropic_messages"

    def _input_verified(self, span: LlmSpan, decoded: Any, n_sent: int | None) -> bool:
        """Whether the wire request carries the span's messages as the element renders them (module docstring)."""
        if not self.is_messages:
            return n_sent == span.n_messages
        if n_sent is None or n_sent != _messages.stock_wire_count(span.roles):
            return False
        lifted = bool(span.roles) and span.roles[0] == "system"
        return lifted or not (isinstance(decoded, Mapping) and "system" in decoded)

    def headers_note(self, call: str, direction: str, headers: Any) -> None:
        """Filtered headers as a note ``agentdojo/wire_headers`` (C.13.10 item 13): allowlisted values (scanned by the
        redactor) and the names of every other header. No ``capture/0.1`` event has a headers member."""
        from agentprov_capture import redact

        try:
            items = list(headers.multi_items()) if hasattr(headers, "multi_items") else list(dict(headers).items())
        except Exception:  # noqa: BLE001
            items = []
        red = getattr(self.session, "redactor", None)
        if red is not None:
            result = red.filter_headers(items, direction=direction, endpoint=self.endpoint)
        else:
            result = redact.filter_headers(items, direction=direction, endpoint=self.endpoint)
        self.session.note("agentdojo", "wire_headers", {"call": call, "direction": direction, "kept": dict(result.kept),
                                                         "dropped": list(result.dropped)})

    def on_request(self, request: Any, body: bytes) -> object:
        s = self.session
        span: LlmSpan | None = s.current_span
        if span is not None:
            span._flush("discarded", "superseded_by_retry")
        call = s.next_call()
        decoded = decode_json_body(body)
        transmitted: dict[str, Any] = {}
        n_sent: int | None = None
        if isinstance(decoded, Mapping):
            skip = _NON_PARAM_KEYS_MESSAGES if self.is_messages else _NON_PARAM_KEYS
            transmitted = {k: v for k, v in decoded.items() if k not in skip}
            msgs = decoded.get("messages")
            if isinstance(msgs, list):
                n_sent = len(msgs)
        blob = s.put_blob(body, _media(request.headers, "application/json"))
        url = request.url
        data: dict[str, Any] = {
            "call": call,
            "role": span.role if span is not None else "auxiliary",
            "attempt": span.n_wire if span is not None else 0,
            "endpoint": {"host": str(url.host), "path": str(url.path)},
            "params": {"configured": self.configured, "transmitted": encode_value(transmitted)},
            "request": blob,
        }
        # a request built from no message list (a defence's embeddings call, D-670) has no `messages` member
        if n_sent is None and span is not None and span.n_messages == 0 and isinstance(decoded, Mapping) \
                and not self.is_messages:
            n_sent = 0
        verified = span is not None and self._input_verified(span, decoded, n_sent)
        if span is not None:
            data["n_messages"] = span.n_messages
            if verified:
                data["input_at"] = list(span.input_at)
            if span.last_call is not None:
                data["retry_of"] = span.last_call
        s.emit("llm.request", data, actor=span.actor if span is not None else None)
        self.headers_note(call, "request", request.headers)
        if span is None:
            s.note("agentdojo", "unbracketed_request", {"call": call})
        elif not verified and span.n_messages > 0:  # n_messages 0: a detached span (no pass positions, D-670)
            payload: dict[str, Any] = {"call": call, "n_messages": span.n_messages, "n_sent": n_sent}
            if self.is_messages:
                payload["n_expected"] = _messages.stock_wire_count(span.roles)
            s.note("agentdojo", "input_at_unverified", payload)
        if span is not None:
            span.n_wire += 1
            span.last_call = call
            span.calls.append(call)
        return (call, span)

    def on_response(self, token: object, status: int, headers: Any, body: bytes) -> None:
        call, span = token  # type: ignore[misc]
        s = self.session
        media = _media(headers, "application/octet-stream")
        blob = s.put_blob(body, media)
        if self.is_messages:
            message = _messages.decode_messages_body(body, media)
            facts = _messages.messages_response_facts(message)
            if 200 <= status < 300 and message is not None and message.error is not None:
                self._provider_error(call, span, status, blob, headers, message)
                return
            if 200 <= status < 300 and message is not None and message.streamed and not message.complete:
                s.note("agentdojo", "stream_incomplete", {"call": call})
        else:
            facts = response_facts(decode_json_body(body))
        if 200 <= status < 300 and span is not None:
            span._set_pending(call, status, blob, facts, lambda: self.headers_note(call, "response", headers))
            return
        data: dict[str, Any] = {"call": call, "status": "error" if not 200 <= status < 300 else "kept",
                                "http_status": status, "response": blob, **facts}
        if not 200 <= status < 300:
            data["reason"] = f"http_{status}"
        s.emit("llm.response", data, actor=span.actor if span is not None else None)
        self.headers_note(call, "response", headers)
        s.step("model_call", call=call, status=data["status"])

    def _provider_error(self, call: str, span: LlmSpan | None, status: int, blob: Mapping[str, Any], headers: Any,
                        message: Any) -> None:
        """A 2xx Messages body carrying a provider error: recorded as ``error`` at once (module docstring)."""
        etype = message.error.get("type") if isinstance(message.error, Mapping) else None
        etype = etype if isinstance(etype, str) and _ERROR_TYPE.fullmatch(etype) else "unknown"
        prefix = "stream_error" if message.streamed else "error_object"
        data: dict[str, Any] = {"call": call, "status": "error", "http_status": status, "response": dict(blob),
                                "reason": f"{prefix}:{etype}"}
        self.session.emit("llm.response", data, actor=span.actor if span is not None else None)
        self.headers_note(call, "response", headers)
        self.session.step("model_call", call=call, status="error")

    def on_error(self, token: object, exc: BaseException) -> None:
        call, span = token  # type: ignore[misc]
        s = self.session
        if s.closed or not s.started or s.poisoned:
            return
        data = {"call": call, "status": "error", "reason": "transport_error",
                "exception": {"type": type(exc).__name__, "message": escape_text(str(exc))}}
        s.emit("llm.response", data, actor=span.actor if span is not None else None)
        s.step("model_call", call=call, status="error")
