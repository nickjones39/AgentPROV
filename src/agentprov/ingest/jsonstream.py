"""JSON documents larger than ``max_json_bytes``, read by streaming declared arrays (docs/architecture G.3.3; D-242).

Some sources ship one JSON document per model of 100 MB or more (MCPHunt: up to 110.9 MB), most of it in one or two
arrays. :func:`open_json_stream` reads such a document without holding it, as long as the caller **declares** which
arrays to stream, as JSON Pointers made of object member names only (``"/messages"``, ``"/events"``; ``""`` for a
top-level array). Nothing is streamed implicitly.

How the strict rules stay identical: a byte-level scanner (regular expressions over 1 MiB chunks; strings are matched
whole, so brackets, commas and colons inside strings never count) finds each declared array and cuts it at its
top-level commas into **element slices**; it never builds a value. Every slice is parsed by
:func:`agentprov.ingest.loaders.strict_json_loads` itself, and so is the **envelope**: the document with every streamed
array replaced by ``[]``. Duplicate keys, numbers, ``NaN``, depth, encoding and lone surrogates are therefore checked by
the same code as for any other document, and a document is accepted exactly when :func:`strict_json_loads` would accept
it (the property tests check this): the document is the envelope with ``[e1,...,en]`` in place of ``[]``, which is
valid JSON exactly when the envelope is valid and every ``ei`` is one valid value. Whole-document rules run on the first
bytes (BOM, UTF-16/32); a slice ends at an ASCII structural byte, which never occurs inside a UTF-8 multi-byte sequence,
so UTF-8 validity is unchanged by the cut. Error offsets are absolute.

**Two passes, fail closed** (as the tar reader, D-57): opening the stream validates the whole document (every element
parsed and dropped, the envelope parsed); only then does iteration re-read the source and yield elements. A defect
anywhere means nothing is yielded. The source is ``bytes`` or a seekable binary handle (for example
``JobContext.open_input``), never read whole.

Limits: ``max_json_stream_bytes`` (the document; ``ingest.size.file``), ``max_json_element_bytes`` (one element, and the
envelope; ``ingest.size.record``), ``max_json_elements`` (``ingest.json.elements``), ``max_json_depth`` (counted from
the document root: an element's own depth limit is reduced by its array's depth). At most one element and the envelope
are parsed at a time, so memory is bounded by twice the element limit times the parse amplification, not by the
document.
"""

from __future__ import annotations

import bisect
import io
import re
from collections.abc import Generator, Iterator, Sequence
from dataclasses import dataclass
from typing import IO, Any, Final

from agentprov.errors import IngestError, IngestFinding
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import JSON_PROFILES, PROFILE_LENIENT_BOM, strict_json_loads

__all__ = ["MAX_STREAMED_ARRAYS", "JsonStream", "JsonStreamItem", "open_json_stream", "parse_pointer"]

#: At most this many declared arrays per document.
MAX_STREAMED_ARRAYS: Final = 16
_CHUNK: Final = 1 << 20
_BOM: Final = b"\xef\xbb\xbf"
_WS: Final = b" \t\n\r"
_STRING: Final = rb'"[^"\\]*+(?:\\.[^"\\]*+)*+"'
#: Envelope tokens: a whole string, a structural byte, or a lone quote (a string not yet complete in the buffer).
_ENV_TOKEN: Final = re.compile(_STRING + rb'|[\[\]{},:]|"', re.DOTALL)
#: Inside a streamed array at element depth 0: skip to the next bracket, comma or lone quote (or the buffer end).
_SKIP_TOP: Final = re.compile(rb'(?:[^"\[\]{},]++|' + _STRING + rb')*+([\[\]{},"]|\Z)', re.DOTALL)
#: Deeper inside an element: only brackets matter.
_SKIP_DEEP: Final = re.compile(rb'(?:[^"\[\]{}]++|' + _STRING + rb')*+([\[\]{}"]|\Z)', re.DOTALL)
#: The body of a string (the inside of :data:`_STRING`): it stops before the closing quote, at a backslash that is the
#: buffer's last byte, or at the buffer end. A string longer than the buffer is resumed from there after each refill,
#: never re-matched from its opening quote (which would cost the square of its length).
_BODY: Final = re.compile(rb'[^"\\]*+(?:\\.[^"\\]*+)*+', re.DOTALL)
_SUMMED: Final = {
    "ingest.json.lone_surrogate": "{n} string(s) with an escaped lone surrogate",
    "ingest.number.nonfinite": "{n} non-finite constant(s) mapped to $float",
}


def parse_pointer(pointer: str) -> tuple[str, ...]:
    """The member names of a JSON Pointer (RFC 6901; ``~1`` is ``/``, ``~0`` is ``~``). ``""`` is the root."""
    if not isinstance(pointer, str):
        raise ValueError("a pointer is a string")
    if pointer == "":
        return ()
    if not pointer.startswith("/"):
        raise ValueError("a JSON Pointer starts with '/'")
    tokens = []
    for raw in pointer[1:].split("/"):
        if re.search(r"~(?![01])", raw):
            raise ValueError("invalid '~' escape in a JSON Pointer")
        tokens.append(raw.replace("~1", "/").replace("~0", "~"))
    return tuple(tokens)


@dataclass(frozen=True, slots=True)
class JsonStreamItem:
    """One element of a streamed array: its declared pointer, its index in that array, its byte offset, its value, and the
    offset just past its last byte (D-323): ``source[offset:end]`` is exactly the element's JSON text (no surrounding
    whitespace), so a D-218 carve locator ``{"bytes": [offset, end], "p": ...}`` parses only this element. Both offsets
    are relative to the source's position when the stream was opened (a stored object opened at 0: absolute)."""

    pointer: str
    index: int
    offset: int
    value: Any
    end: int | None = None


@dataclass(slots=True)
class _Frame:
    kind: int  # ord("{") or ord("[")
    path: tuple[str, ...] | None  # tracked path of an object reachable through objects only, else None
    expect_key: bool = False
    key: str | None = None


class _Sink:
    """A byte accumulator with a cap (an element, or the envelope)."""

    __slots__ = ("cap", "data", "what")

    def __init__(self, cap: int, what: str) -> None:
        self.cap, self.data, self.what = cap, bytearray(), what

    def add(self, chunk: bytes | bytearray | memoryview, offset: int) -> None:
        self.data += chunk
        if len(self.data) > self.cap:
            raise IngestError("ingest.size.record", f"{self.what} exceeds max_json_element_bytes", offset=offset,
                              limit=self.cap)  # fmt: skip


class _Scanner:
    """One pass over the document: yields ``(target, index, offset, bytes)`` per element; the envelope is kept."""

    def __init__(self, stream: IO[bytes], start: int, size: int, targets: Sequence[tuple[str, ...]],
                 limits: IngestLimits) -> None:  # fmt: skip
        self._stream, self._size, self._limits = stream, size, limits
        self._targets = {path: i for i, path in enumerate(targets)}
        self._buf = bytearray()
        self._base = start  # absolute offset of _buf[0]
        self._read = start
        self.envelope = _Sink(limits.max_json_element_bytes, "the envelope (the document outside streamed arrays)")
        self.segments: list[tuple[int, int]] = [(0, start)]  # (envelope offset, document offset) at each resumption
        self.depths: list[int] = []  # per streamed array met, its depth from the root (the array itself included)

    # -- buffer --
    def _more(self, keep_from: int) -> bool:
        """Drop the buffer before ``keep_from`` (absolute) and read one more chunk; ``False`` at the end."""
        if self._read >= self._size:
            return False
        drop = keep_from - self._base
        if drop > 0:
            del self._buf[:drop]
            self._base = keep_from
        if len(self._buf) > self._limits.max_json_element_bytes:  # one token (a string) longer than any element may be
            raise IngestError("ingest.size.record", "a JSON string exceeds max_json_element_bytes", offset=keep_from,
                              limit=self._limits.max_json_element_bytes)  # fmt: skip
        data = self._stream.read(min(_CHUNK, self._size - self._read))
        if not data:
            raise IngestError("ingest.stream.truncated", "the JSON source ended early", offset=self._read)
        self._read += len(data)
        self._buf += data
        return True

    def _slice(self, start: int, end: int) -> memoryview:
        return memoryview(self._buf)[start - self._base : end - self._base]

    # -- the walk --
    def run(self) -> Iterator[tuple[int, int, int, bytes]]:
        stack: list[_Frame] = []
        streamed: set[tuple[str, ...]] = set()  # declared paths already streamed: a second one is a duplicate key
        max_depth = self._limits.max_json_depth
        mark = self._base  # bytes from mark go to the current sink
        pos = self._base
        value_start: int | None = self._base  # where a value may start at a tracked path (the root first)
        value_path: tuple[str, ...] | None = ()
        quote: int | None = None  # the opening quote of a string not yet complete in the buffer (absolute)
        resume = 0  # how far its body has been matched (absolute)
        while True:
            span: tuple[int, int] | None = None
            if quote is not None:
                close = _body_end(self._buf, resume - self._base)
                if close < len(self._buf) and self._buf[close] == 0x22:
                    span, quote = (quote, self._base + close + 1), None
                elif self._read < self._size:
                    resume = self._base + close
                    self._more(quote)
                    continue
                else:  # the source ends inside the string: the token scan below takes the lone quote, as JSON says
                    pos, quote = quote, None
            if span is None:
                m = _ENV_TOKEN.search(self._buf, pos - self._base)
                if m is None or (m.group() == b'"' and self._read < self._size):
                    stop = self._base + (len(self._buf) if m is None else m.start())
                    if value_start is not None and bytes(self._slice(value_start, stop)).strip(_WS):
                        value_start = None
                    self.envelope.add(self._slice(mark, stop), mark)
                    mark = pos = stop
                    if value_start is not None:
                        value_start = stop
                    if m is not None:
                        quote, resume = stop, stop + 1
                    if not self._more(stop):
                        if m is not None:  # a lone quote at the end: the document is not valid JSON; the parse says so
                            self.envelope.add(self._slice(stop, self._base + len(self._buf)), stop)
                        return
                    continue
                span = (self._base + m.start(), self._base + m.end())
            at, pos = span
            c = self._buf[at - self._base]
            if c == 0x22:  # a string
                top = stack[-1] if stack else None
                if top is not None and top.kind == 0x7B and top.expect_key:
                    top.key = _key(bytes(self._slice(at, pos)))
                    top.expect_key = False
                value_start = None
                continue
            if c == 0x3A:  # ':'
                top = stack[-1] if stack else None
                if top is not None and top.kind == 0x7B and top.path is not None and top.key is not None:
                    value_start, value_path = pos, (*top.path, top.key)
                else:
                    value_start = None
                continue
            if c == 0x2C:  # ','
                if stack and stack[-1].kind == 0x7B:
                    stack[-1].expect_key, stack[-1].key = True, None
                value_start = None
                continue
            ws_only = value_start is not None and not bytes(self._slice(value_start, at)).strip(_WS)
            path = value_path if ws_only else None
            value_start = None
            # The scanner's own state is bounded as the parse of the finished envelope would bound it: depth and
            # duplicate declared arrays are refused here, before a frame or a segment is kept (pre-round review D #0).
            if c in (0x5B, 0x7B) and len(stack) + 1 > max_depth:
                raise IngestError("ingest.json.depth", "nesting exceeds the depth limit", offset=at, limit=max_depth)
            if c == 0x5B and path is not None and path in self._targets:  # a declared array
                if path in streamed:  # a path through objects only names one place: the key is repeated
                    raise IngestError("ingest.json.duplicate_key", "duplicate object key", offset=at)
                streamed.add(path)
                self.envelope.add(self._slice(mark, pos), mark)  # up to and including '['
                self.depths.append(len(stack) + 1)
                close = yield from self._array(self._targets[path], pos)
                self.segments.append((len(self.envelope.data), close))
                mark, pos = close, close + 1  # the closing ']' goes to the envelope; scanning resumes after it
                continue
            if c in (0x5B, 0x7B):
                stack.append(_Frame(c, path if c == 0x7B else None, expect_key=c == 0x7B))
            elif stack:
                stack.pop()

    def _array(self, target: int, pos: int) -> Generator[tuple[int, int, int, bytes], None, int]:
        """Inside a declared array: cut elements; returns the absolute offset of the closing ``]``."""
        depth = 0
        index = 0
        commas = 0
        sink = _Sink(self._limits.max_json_element_bytes, "a streamed element")
        mark = start = pos
        quote: int | None = None  # as in run(): a string not yet complete in the buffer, resumed after each refill
        resume = 0
        while True:
            if quote is not None:
                close = _body_end(self._buf, resume - self._base)
                if close < len(self._buf) and self._buf[close] == 0x22:
                    pos, quote = self._base + close + 1, None
                else:
                    resume = self._base + close
                    if not self._more(quote):
                        raise IngestError("ingest.json.syntax", "unterminated streamed array", offset=quote)
                    continue
            m = (_SKIP_TOP if depth == 0 else _SKIP_DEEP).match(self._buf, pos - self._base)
            assert m is not None  # the pattern always matches (possibly empty, at the buffer end)
            c = m.group(1)
            hit = self._base + m.start(1)
            if not c or c == b'"':  # the buffer end, or a string not yet complete in it
                sink.add(self._slice(mark, hit), start)
                mark = pos = hit
                if c:
                    quote, resume = hit, hit + 1
                if not self._more(hit):
                    raise IngestError("ingest.json.syntax", "unterminated streamed array", offset=hit)
                continue
            pos = hit + 1
            if c in b"[{":
                depth += 1
                continue
            if depth:
                if c in b"]}":
                    depth -= 1
                continue
            if c == b"}":
                raise IngestError("ingest.json.syntax", "mismatched bracket in a streamed array", offset=hit)
            sink.add(self._slice(mark, hit), start)
            data = bytes(sink.data)
            lead = len(data) - len(data.lstrip(_WS))
            body = data.strip(_WS)
            if body:
                yield target, index, start + lead, body
                index += 1
            elif c == b"," or commas or index:
                raise IngestError("ingest.json.syntax", "empty element in a streamed array", offset=hit)
            if c == b"]":
                return hit
            commas += 1
            sink = _Sink(self._limits.max_json_element_bytes, "a streamed element")
            mark = start = pos


def _body_end(buf: bytearray, pos: int) -> int:
    """Where the string body starting at ``pos`` stops (see :data:`_BODY`)."""
    m = _BODY.match(buf, pos)
    assert m is not None  # the pattern always matches (possibly empty)
    return m.end()


def _key(token: bytes) -> str | None:
    """The member name of a key token, or ``None`` if it is not a valid JSON string (the envelope parse refuses it)."""
    try:
        value = strict_json_loads(token, record=True)
    except IngestError:
        return None
    return value if isinstance(value, str) else None


def _merge(findings: list[IngestFinding]) -> list[IngestFinding]:
    """One finding per summed code (the totals ``strict_json_loads`` would report for the whole document)."""
    totals: dict[str, int] = {}
    severity: dict[str, Any] = {}
    out: list[IngestFinding] = []
    for f in findings:
        if f.code in _SUMMED and f.detail:
            totals[f.code] = totals.get(f.code, 0) + int(f.detail.split(" ", 1)[0])
            severity[f.code] = f.severity
        else:
            out.append(f)
    out.extend(IngestFinding(code, severity[code], detail=_SUMMED[code].format(n=n)) for code, n in totals.items())
    return out


class JsonStream:
    """A validated streamed document (pass 1 done at construction): ``envelope``, ``counts``, ``findings``; iterate for
    the elements (pass 2)."""

    def __init__(
        self,
        source: bytes | IO[bytes],
        limits: IngestLimits | None = None,
        *,
        arrays: Sequence[str],
        profile: str = "strict",
    ) -> None:
        if profile not in JSON_PROFILES:
            raise ValueError(f"unknown JSON profile: {profile!r}")
        if isinstance(arrays, str):
            raise ValueError("arrays is a sequence of JSON Pointers")
        self.limits = limits or IngestLimits()
        self.pointers = tuple(arrays)
        paths = [parse_pointer(p) for p in self.pointers]
        if not paths or len(paths) > MAX_STREAMED_ARRAYS or len(set(paths)) != len(paths):
            raise ValueError(f"declare between 1 and {MAX_STREAMED_ARRAYS} distinct arrays to stream")
        for a in paths:
            for b in paths:
                if a != b and b[: len(a)] == a:
                    raise ValueError("a streamed array cannot contain another")
        self._paths = paths
        self._profile = profile
        self._element_limits: dict[int, IngestLimits] = {}
        if isinstance(source, bytes | bytearray | memoryview):
            self._stream: IO[bytes] = io.BytesIO(bytes(source))
        else:
            self._stream = source
        self._origin = self._stream.tell()
        self.size = self._stream.seek(0, io.SEEK_END) - self._origin
        if self.size > self.limits.max_json_stream_bytes:
            raise IngestError("ingest.size.file", f"document of {self.size} bytes exceeds the limit",
                              limit=self.limits.max_json_stream_bytes)  # fmt: skip
        self.findings: list[IngestFinding] = []
        self._start = self._head()
        self.counts: dict[str, int] = dict.fromkeys(self.pointers, 0)
        found: list[IngestFinding] = []
        scanner = self._scanner()
        total = 0
        for target, _index, offset, data in scanner.run():  # pass 1: parse and drop
            total += 1
            if total > self.limits.max_json_elements:
                raise IngestError("ingest.json.elements", "the document has more streamed elements than the limit",
                                  offset=offset - self._origin, limit=self.limits.max_json_elements)  # fmt: skip
            self._parse(data, offset, scanner.depths[-1], found)
            self.counts[self.pointers[target]] += 1
        self._envelope_data = bytes(scanner.envelope.data)
        self.envelope = self._envelope(scanner, found)
        self.findings.extend(_merge(found))

    def _head(self) -> int:
        """Whole-document checks on the first bytes (G.3.3 rules 2-3); returns the absolute offset parsing starts at."""
        self._stream.seek(self._origin)
        head = self._stream.read(4)
        start = self._origin
        if head.startswith(_BOM):
            if self._profile != PROFILE_LENIENT_BOM:
                raise IngestError("ingest.json.bom", "UTF-8 byte order mark", offset=0)
            self.findings.append(IngestFinding("ingest.json.bom", "warning", offset=0, detail="UTF-8 BOM stripped"))
            head, start = head[3:], start + 3
        if (len(head) >= 1 and head[0] == 0) or (len(head) >= 2 and head[1] == 0):
            raise IngestError("ingest.json.encoding", "UTF-16 or UTF-32 input", offset=0)
        return start

    def _scanner(self) -> _Scanner:
        self._stream.seek(self._start)
        return _Scanner(self._stream, self._start, self._origin + self.size, self._paths, self.limits)

    def _json_profile(self) -> str:
        return "strict" if self._profile == PROFILE_LENIENT_BOM else self._profile  # the BOM is already handled

    def _parse(self, data: bytes, offset: int, array_depth: int, found: list[IngestFinding] | None) -> Any:
        own = self.limits.max_json_depth - array_depth
        if own < 0 or (own == 0 and data[:1] in (b"[", b"{")):
            raise IngestError("ingest.json.depth", "nesting exceeds the depth limit", offset=offset,
                              limit=self.limits.max_json_depth)  # fmt: skip
        limits = self._element_limits.get(own)
        if limits is None:  # one derived record per array depth (replace() validates every field: not per element)
            limits = self.limits.replace(max_json_depth=max(own, 1), max_jsonl_line_bytes=self.limits.max_json_element_bytes)
            self._element_limits[own] = limits
        try:
            value = strict_json_loads(data, limits, profile=self._json_profile(), record=True, findings=found)
        except IngestError as exc:
            raise _shifted(exc, offset, self._origin) from None
        if own == 0 and isinstance(value, dict | list):  # a scalar mapped to a container (python-json ``$float``)
            raise IngestError("ingest.json.depth", "nesting exceeds the depth limit", offset=offset - self._origin,
                              limit=self.limits.max_json_depth)  # fmt: skip
        return value

    def _envelope(self, scanner: _Scanner, found: list[IngestFinding]) -> Any:
        data = bytes(scanner.envelope.data)
        limits = self.limits.replace(max_jsonl_line_bytes=self.limits.max_json_element_bytes)
        try:
            return strict_json_loads(data, limits, profile=self._json_profile(), record=True, findings=found)
        except IngestError as exc:
            if exc.offset is None:
                raise
            starts = [s[0] for s in scanner.segments]
            env, doc = scanner.segments[bisect.bisect_right(starts, exc.offset) - 1]
            raise _shifted(exc, doc + (exc.offset - env), self._origin, absolute=True) from None

    def __iter__(self) -> Iterator[JsonStreamItem]:
        """Pass 2: re-read the source and yield every element, in document order, parsed by ``strict_json_loads``."""
        scanner = self._scanner()
        seen = dict.fromkeys(self.pointers, 0)
        for target, index, offset, data in scanner.run():
            pointer = self.pointers[target]
            seen[pointer] += 1
            yield JsonStreamItem(pointer, index, offset - self._origin, self._parse(data, offset, scanner.depths[-1], None),
                                 offset - self._origin + len(data))
        if seen != self.counts or bytes(scanner.envelope.data) != self._envelope_data:
            raise IngestError("ingest.json.syntax", "the source changed between the two passes")


def _shifted(exc: IngestError, offset: int, origin: int, *, absolute: bool = False) -> IngestError:
    """``exc`` with its offset made absolute within the document (relative to ``origin``)."""
    base = offset - origin
    return IngestError(exc.code, exc.reason, offset=base if absolute else base + (exc.offset or 0), limit=exc.limit)


def open_json_stream(
    source: bytes | IO[bytes],
    limits: IngestLimits | None = None,
    *,
    arrays: Sequence[str],
    profile: str = "strict",
) -> JsonStream:
    """Validate a JSON document by streaming the declared ``arrays`` (pass 1) and return it ready to iterate (D-242).

    Raises :class:`~agentprov.errors.IngestError` with a closed code (and an absolute offset where one exists) before
    anything is yielded; ``ValueError`` for a malformed declaration. See the module documentation.
    """
    return JsonStream(source, limits, arrays=arrays, profile=profile)
