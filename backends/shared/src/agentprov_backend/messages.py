"""The Anthropic Messages wire format, as the recorder needs it (D-656; design note §1). Standard library only: no SDK.

* :func:`parse_sse` splits a ``text/event-stream`` body into events as the SDK's ``SSEDecoder`` does (``event:``/
  ``data:`` fields, ``:`` comments, CR/LF/CRLF line ends, only a blank line dispatches, no BOM stripping), bounded by
  :data:`MAX_SSE_EVENTS`; a body that ends inside an event or a line is torn.
* :func:`assemble_stream` rebuilds the ``Message`` a stream carries, the way the SDK's ``get_final_message`` does:
  ``message_start`` gives the id, model and first usage; ``content_block_start``/``_delta``/``_stop`` build the blocks
  (text, thinking with signature, redacted thinking, tool use with the concatenated ``partial_json`` kept verbatim);
  ``message_delta`` gives the stop reason and the later usage (a key reported later wins, as the SDK's accumulator);
  an ``error`` event is a provider error, and a stream without ``message_stop`` is incomplete.
* :func:`messages_response_facts` gives the ``llm.response`` facts (``usage`` in AER names, ``finish_reason``,
  ``served_model``, ``response_id``) of a JSON or SSE body, as the provider reported them: nothing is computed (no
  ``total_tokens``; thinking tokens are inside ``output_tokens``, so no ``reasoning_tokens``).
* :func:`stock_wire_count` is the number of wire messages AgentDojo 0.1.35's ``AnthropicLLM`` sends for a native
  message list (``_conversation_to_anthropic``: a leading system message is lifted into ``system``; consecutive
  non-assistant messages are merged into one user turn by ``_merge_tool_result_messages``).

Nothing here interprets content, and nothing raises on hostile input: a body that does not parse gives no facts.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

__all__ = [
    "MAX_SSE_EVENTS",
    "USAGE_KEYS",
    "AssembledMessage",
    "SseEvent",
    "assemble_stream",
    "decode_messages_body",
    "is_event_stream",
    "messages_response_facts",
    "parse_sse",
    "stock_wire_count",
]

#: At most this many events are parsed from one body; the rest are ignored and the stream reported incomplete.
MAX_SSE_EVENTS: Final = 200_000

#: Messages API usage members -> AER ``Usage`` members (the D-283 ``anthropic-messages`` mapping).
USAGE_KEYS: Final[Mapping[str, str]] = {
    "input_tokens": "input_tokens",
    "output_tokens": "output_tokens",
    "cache_read_input_tokens": "cache_read_tokens",
    "cache_creation_input_tokens": "cache_write_tokens",
}


@dataclass(frozen=True, slots=True)
class SseEvent:
    """One dispatched event: its ``event`` field (``"message"`` when absent) and its ``data`` lines joined by LF."""

    event: str
    data: str


@dataclass(slots=True)
class AssembledMessage:
    """The message a body carries. ``content`` blocks are plain dicts in the API's shape; a streamed ``tool_use``
    block also carries ``input_json`` (the concatenated ``partial_json``, verbatim) and its ``input`` is the parsed
    value, or ``None`` when that text is not JSON. ``error`` is the provider error object of an ``error`` event (or of
    an error body); ``complete`` is false for a stream that ended without ``message_stop``."""

    id: str | None = None
    model: str | None = None
    stop_reason: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    content: list[dict[str, Any]] = field(default_factory=list)
    error: dict[str, Any] | None = None
    complete: bool = False
    streamed: bool = False


def _reject_constant(name: str) -> Any:
    raise ValueError(name)


def _json(text: str | bytes) -> Any:
    """Strict JSON (no NaN/Infinity); ``None`` when it is not JSON."""
    try:
        if isinstance(text, bytes):
            text = text.decode("utf-8")
        return json.loads(text, parse_constant=_reject_constant)
    except (UnicodeDecodeError, ValueError, RecursionError):
        return None


def is_event_stream(media: str | None) -> bool:
    return isinstance(media, str) and media.split(";", 1)[0].strip().lower() == "text/event-stream"


_LINE: Final = re.compile(r"([^\r\n]*)(\r\n|\r|\n)")
#: The events the SDK accumulates, by SSE event name (``Stream.__stream__``); other names (``ping``) are ignored.
_ACCUMULATED: Final = frozenset({"message_start", "message_delta", "message_stop", "content_block_start",
                                 "content_block_delta", "content_block_stop"})


def parse_sse(body: bytes) -> tuple[list[SseEvent], bool]:
    """``(events, torn)``: the dispatched events of ``body`` in order, as the SDK's ``SSEDecoder`` dispatches them
    (only a blank line dispatches; an event with data or a name is dispatched; text after the last line terminator is
    not read; a BOM is not stripped). ``torn`` is true when the body ends inside an event or a line, or the event cap
    was reached. Invalid UTF-8 is replaced (the recorded bytes are the evidence; this is a reading of them)."""
    text = body.decode("utf-8", errors="replace")
    events: list[SseEvent] = []
    name = ""
    data: list[str] = []
    end = 0
    for match in _LINE.finditer(text):
        line = match.group(1)
        end = match.end()
        if line == "":
            if data or name:
                events.append(SseEvent(name or "message", "\n".join(data)))
                if len(events) >= MAX_SSE_EVENTS:
                    return events, True
            name, data = "", []
            continue
        if line.startswith(":"):
            continue
        key, sep, value = line.partition(":")
        if sep and value.startswith(" "):
            value = value[1:]
        if key == "event":
            name = value
        elif key == "data":
            data.append(value)
    return events, bool(data) or bool(name) or text[end:] != ""


def _merge_usage(target: dict[str, Any], usage: object) -> None:
    if isinstance(usage, Mapping):
        for k, v in usage.items():
            if v is not None:
                target[k] = v


def assemble_stream(events: Sequence[SseEvent]) -> AssembledMessage:
    """Rebuild the streamed message (see the module docstring), keyed on the SSE event name as the SDK is. Events
    that do not decode, or whose payload type disagrees with their name, are skipped (the core mapper reports such a
    stream; the harness only extracts facts). Pieces are joined once, at the end."""
    msg = AssembledMessage(streamed=True)
    blocks: dict[int, dict[str, Any]] = {}
    pieces: dict[int, dict[str, list[str]]] = {}
    for ev in events:
        if ev.event == "error":
            payload = _json(ev.data)
            err = payload.get("error") if isinstance(payload, dict) else None
            msg.error = dict(err) if isinstance(err, dict) else {"type": "unknown"}
            break
        if ev.event not in _ACCUMULATED:
            continue
        payload = _json(ev.data)
        if not isinstance(payload, dict) or payload.get("type") != ev.event:
            continue
        kind = ev.event
        if kind == "message_start":
            m = payload.get("message")
            if isinstance(m, dict):
                msg.id = m.get("id") if isinstance(m.get("id"), str) else msg.id
                msg.model = m.get("model") if isinstance(m.get("model"), str) else msg.model
                _merge_usage(msg.usage, m.get("usage"))
        elif kind == "content_block_start":
            index, block = payload.get("index"), payload.get("content_block")
            if isinstance(index, int) and isinstance(block, dict):
                blocks[index] = {k: v for k, v in block.items() if k != "input_json"}  # the SDK's JSON buffer is its own
                pieces[index] = {}
        elif kind == "content_block_delta":
            index, delta = payload.get("index"), payload.get("delta")
            if not isinstance(index, int) or index not in blocks or not isinstance(delta, dict):
                continue
            for dtype, member, key in (("text_delta", "text", "text"), ("input_json_delta", "input_json", "partial_json"),
                                       ("thinking_delta", "thinking", "thinking"), ("signature_delta", "signature",
                                                                                     "signature")):
                if delta.get("type") == dtype and isinstance(delta.get(key), str):
                    pieces[index].setdefault(member, []).append(delta[key])
        elif kind == "message_delta":
            delta = payload.get("delta")
            if isinstance(delta, dict) and isinstance(delta.get("stop_reason"), str):
                msg.stop_reason = delta["stop_reason"]
            _merge_usage(msg.usage, payload.get("usage"))
        elif kind == "message_stop":
            msg.complete = True
    for index in sorted(blocks):
        block = blocks[index]
        for member, parts in pieces[index].items():
            if member == "signature":
                block[member] = parts[-1]
            else:
                block[member] = ("" if member == "input_json" else str(block.get(member) or "")) + "".join(parts)
        if block.get("type") == "tool_use" and block.get("input_json"):
            block["input"] = _json(block["input_json"])
        msg.content.append(block)
    return msg


def decode_messages_body(body: bytes, media: str | None) -> AssembledMessage | None:
    """The message of a Messages API response body (SSE or JSON); ``None`` when the body is neither."""
    if is_event_stream(media):
        events, torn = parse_sse(body)
        msg = assemble_stream(events)
        if torn:
            msg.complete = False
        return msg
    decoded = _json(body)
    if not isinstance(decoded, dict):
        return None
    msg = AssembledMessage(complete=True)
    if decoded.get("type") == "error":
        err = decoded.get("error")
        msg.error = dict(err) if isinstance(err, dict) else {"type": "unknown"}
        return msg
    msg.id = decoded.get("id") if isinstance(decoded.get("id"), str) else None
    msg.model = decoded.get("model") if isinstance(decoded.get("model"), str) else None
    msg.stop_reason = decoded.get("stop_reason") if isinstance(decoded.get("stop_reason"), str) else None
    _merge_usage(msg.usage, decoded.get("usage"))
    content = decoded.get("content")
    msg.content = [dict(b) for b in content if isinstance(b, dict)] if isinstance(content, list) else []
    return msg


def _nonneg_int(v: Any) -> int | None:
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else None


def messages_response_facts(msg: AssembledMessage | None) -> dict[str, Any]:
    """``usage``, ``finish_reason``, ``served_model`` and ``response_id`` as the provider reported them."""
    out: dict[str, Any] = {}
    if msg is None or msg.error is not None:
        return out
    if msg.id is not None:
        out["response_id"] = msg.id
    if msg.model is not None:
        out["served_model"] = msg.model
    if msg.stop_reason is not None:
        out["finish_reason"] = msg.stop_reason
    usage = {dst: v for src, dst in USAGE_KEYS.items() if (v := _nonneg_int(msg.usage.get(src))) is not None}
    if usage:
        out["usage"] = usage
    return out


def stock_wire_count(roles: Sequence[object]) -> int:
    """Wire messages the stock ``AnthropicLLM`` sends for native messages with these roles (see the module
    docstring): a leading ``system`` is lifted out, and each maximal run of non-assistant messages is one turn."""
    rest = list(roles[1:]) if roles and roles[0] == "system" else list(roles)
    count = 0
    previous: object = None
    for i, role in enumerate(rest):
        if i == 0 or role == "assistant" or previous == "assistant":
            count += 1
        previous = role
    return count
