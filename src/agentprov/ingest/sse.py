"""Bounded reading of an untrusted ``text/event-stream`` body (server-sent events; D-656).

A live capture stores a streamed model reply as the entity body it received, byte for byte (C.13.10 item 22). This
module splits such a body into its dispatched events **as the SDK that consumed it did** (``anthropic`` 1.11.0
``SSEDecoder``, the WHATWG event-stream rules): a line is terminated by CR, LF or CRLF; a line starting with ``:`` is
a comment; ``field: value`` (one leading space of the value removed) sets ``event`` or appends to ``data``; a blank
line dispatches the pending event when it has data or an event name (an event with neither is skipped). Text after the last line terminator is an unterminated line and is not read,
and an event with no terminating blank line is not dispatched: both make the stream *torn*
(:attr:`EventStream.torn`). A leading byte-order mark is not stripped (the SDK does not strip one; it makes the first
field name unknown). Other fields (``id``, ``retry``) are ignored.

Bounds (``IngestLimits``): the body at most ``max_json_bytes`` (``ingest.size.file``), the events at most
``max_json_elements`` (``ingest.json.elements``), one line and one event's data at most ``max_jsonl_line_bytes``
(``ingest.size.record``). The body must be UTF-8 (``ingest.json.encoding``). Lines are read one at a time, without a
second copy of the body. Event data is returned as text: a consumer that reads it as JSON uses
:func:`agentprov.ingest.loaders.strict_json_loads`. Standard library only; nothing here interprets content.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from agentprov.errors import IngestError
from agentprov.ingest.limits import IngestLimits

__all__ = ["EventStream", "SseEvent", "parse_event_stream"]

#: One terminated line: its text and its terminator (CRLF before CR so that it counts once).
_LINE: Final = re.compile(r"([^\r\n]*)(\r\n|\r|\n)")


@dataclass(frozen=True, slots=True)
class SseEvent:
    """One dispatched event: ``event`` (``"message"`` when the field is absent) and its data lines joined by LF (``""``
    when it had none)."""

    event: str
    data: str


@dataclass(frozen=True, slots=True)
class EventStream:
    events: tuple[SseEvent, ...]
    #: the body ended inside an event or inside a line: an event or line that was not dispatched follows the last one
    torn: bool


def _too_long(text: str, limit: int) -> bool:
    return len(text) > limit or (len(text) * 4 > limit and len(text.encode("utf-8")) > limit)


def parse_event_stream(body: bytes, limits: IngestLimits | None = None) -> EventStream:
    """The dispatched events of ``body`` (see the module docstring). Raises :class:`IngestError`."""
    lim = limits or IngestLimits()
    if len(body) > lim.max_json_bytes:
        raise IngestError("ingest.size.file", "event stream exceeds max_json_bytes", limit=lim.max_json_bytes)
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise IngestError("ingest.json.encoding", "event stream is not UTF-8", offset=exc.start) from None
    events: list[SseEvent] = []
    name = ""
    data: list[str] = []
    size = 0
    end = 0
    for match in _LINE.finditer(text):
        line = match.group(1)
        end = match.end()
        if _too_long(line, lim.max_jsonl_line_bytes):
            raise IngestError("ingest.size.record", "an event-stream line exceeds max_jsonl_line_bytes",
                              limit=lim.max_jsonl_line_bytes)
        if line == "":
            if data or name:
                if len(events) >= lim.max_json_elements:
                    raise IngestError("ingest.json.elements", "too many events in an event stream",
                                      limit=lim.max_json_elements)
                events.append(SseEvent(name or "message", "\n".join(data)))
            name, data, size = "", [], 0
            continue
        if line.startswith(":"):
            continue
        key, sep, value = line.partition(":")
        if sep and value.startswith(" "):
            value = value[1:]
        if key == "event":
            name = value
        elif key == "data":
            size += len(value.encode("utf-8")) + 1
            if size > lim.max_jsonl_line_bytes:
                raise IngestError("ingest.size.record", "an event's data exceeds max_jsonl_line_bytes",
                                  limit=lim.max_jsonl_line_bytes)
            data.append(value)
    tail = text[end:]
    if _too_long(tail, lim.max_jsonl_line_bytes):
        raise IngestError("ingest.size.record", "an event-stream line exceeds max_jsonl_line_bytes",
                          limit=lim.max_jsonl_line_bytes)
    return EventStream(tuple(events), bool(data) or bool(name) or tail != "")
