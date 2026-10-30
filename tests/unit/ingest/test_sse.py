"""``agentprov.ingest.sse``: bounded reading of an untrusted event stream (D-656). Limits are read from
``IngestLimits`` and probed at limit - 1, limit and limit + 1 (K.5.6); nothing is hard-coded."""

from __future__ import annotations

import dataclasses

import pytest

from agentprov.errors import IngestError
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.sse import SseEvent, parse_event_stream


def test_whatwg_fields_line_ends_and_comments():
    body = b": keep-alive\r\nevent: a\r\ndata: one\r\ndata:two\r\nid: 7\r\n\r\ndata: {\"x\": 1}\r\rdata: z\n\n"
    stream = parse_event_stream(body)
    assert stream.events == (SseEvent("a", "one\ntwo"), SseEvent("message", '{"x": 1}'), SseEvent("message", "z"))
    assert stream.torn is False


def test_name_only_events_dispatch_and_a_torn_one_is_reported():
    stream = parse_event_stream(b"event: ping\n\n\ndata: a\n\nevent: x\ndata: never ends")
    assert stream.events == (SseEvent("ping", ""), SseEvent("message", "a")) and stream.torn is True
    assert parse_event_stream(b"").events == () and not parse_event_stream(b"").torn
    assert parse_event_stream(b"id: 3\nretry: 5\n\n").events == ()  # neither data nor a name: skipped


@pytest.mark.parametrize("eol", [b"\n", b"\r", b"\r\n"])
def test_a_final_event_ended_by_one_line_terminator_is_not_dispatched(eol):
    """Rebuild-window review R1-1: only a blank line dispatches; the SDK never dispatches this event."""
    stream = parse_event_stream(b"data: a" + eol + eol + b"data: x" + eol)
    assert stream.events == (SseEvent("message", "a"),) and stream.torn is True
    stream = parse_event_stream(b"data: a" + eol + eol + b"data: x")
    assert stream.events == (SseEvent("message", "a"),) and stream.torn is True
    assert parse_event_stream(b"data: a" + eol + eol).torn is False


def test_a_byte_order_mark_is_kept_as_the_sdk_keeps_it():
    stream = parse_event_stream("\ufeffevent: a\ndata: x\n\n".encode())
    assert stream.events == (SseEvent("message", "x"),)  # the BOM makes the first field name unknown


def test_not_utf8_is_refused():
    with pytest.raises(IngestError) as exc:
        parse_event_stream(b"data: \xff\n\n")
    assert exc.value.code == "ingest.json.encoding"


def _limits(**kw):
    return dataclasses.replace(IngestLimits(), **kw)


def test_body_size_bound():
    body = b"data: x\n\n"
    lim = _limits(max_json_bytes=len(body))
    assert len(parse_event_stream(body, lim).events) == 1
    with pytest.raises(IngestError) as exc:
        parse_event_stream(body + b"\n", lim)
    assert exc.value.code == "ingest.size.file"


@pytest.mark.parametrize("n, ok", [(2, True), (3, True), (4, False)])
def test_event_count_bound(n, ok):
    lim = _limits(max_json_elements=3)
    body = b"data: x\n\n" * n
    if ok:
        assert len(parse_event_stream(body, lim).events) == n
    else:
        with pytest.raises(IngestError) as exc:
            parse_event_stream(body, lim)
        assert exc.value.code == "ingest.json.elements"


@pytest.mark.parametrize("lines, ok", [(1, True), (2, True), (3, False)])
def test_event_data_bound(lines, ok):
    lim = _limits(max_jsonl_line_bytes=9)
    body = b"data: abc\n" * lines + b"\n"  # 4 data bytes per line (3 + the joining LF)
    if lines * 4 <= 9:
        assert parse_event_stream(body, lim).events[0].data == "\n".join(["abc"] * lines)
    else:
        with pytest.raises(IngestError) as exc:
            parse_event_stream(body, lim)
        assert exc.value.code == "ingest.size.record"
    assert ok == (lines * 4 <= 9)


@pytest.mark.parametrize("size, ok", [(9, True), (10, True), (11, False)])
def test_line_bound(size, ok):
    lim = _limits(max_jsonl_line_bytes=10)
    body = b": " + b"x" * (size - 2) + b"\n" + b"data: y\n\n"
    if ok:
        assert parse_event_stream(body, lim).events == (SseEvent("message", "y"),)
    else:
        with pytest.raises(IngestError) as exc:
            parse_event_stream(body, lim)
        assert exc.value.code == "ingest.size.record"
    with pytest.raises(IngestError):  # the unterminated tail is bounded too
        parse_event_stream(b"x" * 11, lim)


def _sdk_reference(body: bytes) -> list[tuple[str, str]]:
    """The algorithm of anthropic 1.11.0 ``SSEDecoder.iter_bytes`` (chunks end at a blank line; lines by
    ``bytes.splitlines``; ``decode`` dispatches on an empty line when an event name or data is pending), for events
    with data or a name; written here because the core never imports the SDK."""
    out: list[tuple[str, str]] = []
    chunks, data_ = [], b""
    for line in body.splitlines(keepends=True):
        data_ += line
        if data_.endswith((b"\r\r", b"\n\n", b"\r\n\r\n")):
            chunks.append(data_)
            data_ = b""
    if data_:
        chunks.append(data_)
    event, data = None, []
    for chunk in chunks:
        for raw in chunk.splitlines():
            line = raw.decode("utf-8")
            if not line:
                if event or data:
                    out.append((event or "message", "\n".join(data)))
                event, data = None, []
                continue
            if line.startswith(":"):
                continue
            name, _, value = line.partition(":")
            value = value[1:] if value.startswith(" ") else value
            if name == "event":
                event = value
            elif name == "data":
                data.append(value)
    return out


def test_differential_against_the_sdk_algorithm():
    """A seeded random differential (2,000 streams over the grammar's corner cases) against :func:`_sdk_reference`."""
    import random

    rng = random.Random(656)
    atoms = [b"data: a", b"data:b", b"data: ", b"event: e", b"event:", b": c", b"id: 1", b"x", b"",
             b"\n", b"\r", b"\r\n", b"\n\n", b"\r\n\r\n"]
    for _ in range(2000):
        body = b"".join(rng.choice(atoms) for _ in range(rng.randrange(0, 12)))
        got = [(e.event, e.data) for e in parse_event_stream(body).events]
        assert got == _sdk_reference(body), body
