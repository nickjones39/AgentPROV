"""SEC-04: JSON documents above ``max_json_bytes`` are read by streaming declared arrays under per-element limits (D-242).

The strict rules are those of ``strict_json_loads`` (each element and the envelope go through it); these cases probe the
stream-level bounds: document, element, envelope, a single long string, element count and depth, plus fail-closed
two-pass behaviour (nothing is yielded from a document with a defect anywhere) and bounded memory.
"""

from __future__ import annotations

import io
import json
import tracemalloc

import pytest

from agentprov.errors import IngestError
from agentprov.ingest import jsonstream
from agentprov.ingest.jsonstream import MAX_STREAMED_ARRAYS, open_json_stream, parse_pointer
from agentprov.ingest.limits import KIB, MIB, IngestLimits
from agentprov.ingest.loaders import strict_json_loads

LIMITS = IngestLimits()


def doc(n: int = 3, *, pad: int = 10) -> bytes:
    return json.dumps({"model": "m", "messages": [{"role": "user", "content": "x" * pad} for _ in range(n)],
                       "events": [{"tool": "t", "i": i} for i in range(n)]}).encode()  # fmt: skip


def code_of(data: bytes, limits: IngestLimits = LIMITS, arrays=("/messages", "/events"), **kw) -> str:
    with pytest.raises(IngestError) as err:
        list(open_json_stream(data, limits, arrays=arrays, **kw))
    return err.value.code


def test_declarations_are_checked():
    for bad in ([], ["/a", "/a"], ["", "/a"], ["/a", "/a/b"], ["a"], ["/a~2"], [f"/{i}" for i in range(MAX_STREAMED_ARRAYS + 1)]):
        with pytest.raises(ValueError):
            open_json_stream(b"{}", arrays=bad)
    assert parse_pointer("/a~1b/~0c") == ("a/b", "~c")


@pytest.mark.parametrize(("delta", "ok"), [(-1, False), (0, True), (1, True)])
def test_document_size_probes(delta, ok):
    data = doc()
    limits = LIMITS.replace(max_json_stream_bytes=len(data) + delta)
    if ok:
        assert open_json_stream(data, limits, arrays=["/messages"]).counts == {"/messages": 3}
    else:
        assert code_of(data, limits) == "ingest.size.file"


def test_element_size_probes():
    element = json.dumps({"role": "user", "content": "y" * 1000}).encode()
    data = b'{"messages": [' + element + b"]}"
    at = LIMITS.replace(max_json_element_bytes=len(element))
    assert [i.value["content"] for i in open_json_stream(data, at, arrays=["/messages"])] == ["y" * 1000]
    assert code_of(data, LIMITS.replace(max_json_element_bytes=len(element) - 1), ("/messages",)) == "ingest.size.record"


def test_the_envelope_is_bounded_like_an_element():
    data = json.dumps({"meta": "z" * 5000, "messages": []}).encode()
    assert code_of(data, LIMITS.replace(max_json_element_bytes=4 * KIB), ("/messages",)) == "ingest.size.record"


def test_a_long_string_is_never_buffered_beyond_the_element_limit():
    """A 40 MiB string inside a streamed array stops at the element limit, without holding the string."""
    data = b'{"messages": ["' + b"s" * (40 * MIB) + b'"]}'
    limits = LIMITS.replace(max_json_element_bytes=1 * MIB)
    tracemalloc.start()
    try:
        assert code_of(data, limits, ("/messages",)) == "ingest.size.record"
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert peak < 8 * MIB, peak


def test_element_count_probes():
    data = doc(5)
    assert sum(open_json_stream(data, LIMITS.replace(max_json_elements=10), arrays=["/messages", "/events"]).counts.values()) == 10
    assert code_of(data, LIMITS.replace(max_json_elements=9)) == "ingest.json.elements"


def test_depth_counts_from_the_root():
    limits = LIMITS.replace(max_json_depth=8)
    at = "[" * 7 + "]" * 7  # inside the root array: 1 + 7 = 8
    assert [i.value for i in open_json_stream(f"[{at}]".encode(), limits, arrays=[""])] == [json.loads(at)]
    assert code_of(f"[[{at}]]".encode(), limits, ("",)) == "ingest.json.depth"
    assert code_of(f'{{"messages": [{at}]}}'.encode(), limits, ("/messages",)) == "ingest.json.depth"  # 2 + 7 = 9
    assert code_of(b'{"a":' * 9 + b"1" + b"}" * 9, limits, ("/messages",)) == "ingest.json.depth"  # in the envelope


class _QuoteRestarts:
    """Wraps a scanner pattern and adds up ``len(buffer) - pos`` for every scan that starts at an opening quote: the
    work of re-matching a string from its start."""

    def __init__(self, pattern, total):
        self.pattern, self.total = pattern, total

    def _count(self, buf, pos):
        if pos < len(buf) and buf[pos] == 0x22:
            self.total[0] += len(buf) - pos

    def search(self, buf, pos):
        self._count(buf, pos)
        return self.pattern.search(buf, pos)

    def match(self, buf, pos):
        self._count(buf, pos)
        return self.pattern.match(buf, pos)


@pytest.mark.parametrize("where", ["element", "envelope", "nested"])
def test_a_string_longer_than_the_buffer_is_not_rescanned_from_its_start(monkeypatch, where):
    """A string longer than one read is resumed after each refill, not re-matched from its opening quote (which costs
    the square of its length: about 30 s of CPU for a 64 MiB element; bug pass BF-16)."""
    chunk, n = 4 * KIB, 512 * KIB
    monkeypatch.setattr(jsonstream, "_CHUNK", chunk)
    total = [0]
    for name in ("_ENV_TOKEN", "_SKIP_TOP", "_SKIP_DEEP"):
        monkeypatch.setattr(jsonstream, name, _QuoteRestarts(getattr(jsonstream, name), total))
    long = "x" * n + '\\"\\\\'
    value = {"element": {"messages": [long, 1]}, "envelope": {"model": long, "messages": [1]},
             "nested": {"messages": [{"content": [long]}]}}[where]
    data = json.dumps(value).encode()
    assert [i.value for i in open_json_stream(data, LIMITS, arrays=["/messages"])] == value["messages"]
    assert total[0] < 16 * chunk  # was about n * n / chunk (two passes)


_BOUNDARY_DOCS = [
    b'{"messages": ["a\\"b", "c\\\\", "\\\\\\"", {"k\\"": "v\\\\"}], "model": "m\\\\\\"x"}',
    b'{"messages": ["\\u00e9\xc3\xa9\\ud83d\\ude00", [["]"], "[{,"]], "e\\\\": "\\"}\\""}',
    b'{"m\\"essages": [1], "messages": ["x", "y\\\\"]}',
    b'{"messages": ["unterminated]}',
    b'{"messages": ["a\\"], "b": 1}',
    b'{"messages": ["a"], "model": "unterminated}',
    b'{"messages": ["a\\\\"]',
    b'{"messages": ["bad \\x escape"]}',
    b'{"messages": ["ok"], "model": "\\"\\\\\\""}',
]


def _streamed(data):
    try:
        stream = open_json_stream(data, LIMITS, arrays=["/messages"])
        return [(i.index, i.offset, i.end, i.value) for i in stream], stream.envelope
    except IngestError as exc:
        return exc.code, exc.offset


@pytest.mark.parametrize("data", _BOUNDARY_DOCS)
def test_strings_cut_at_every_refill_boundary_read_as_in_one_buffer(monkeypatch, data):
    """Every chunk size, so that every string, escape and quote of these documents meets a buffer end: the result (or
    the error and its offset) is the one the scanner gives when the whole document fits one buffer."""
    whole = _streamed(data)
    for chunk in (1, 2, 3, 5, 7, 11, 16):
        monkeypatch.setattr(jsonstream, "_CHUNK", chunk)
        assert _streamed(data) == whole, chunk


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_a_mapped_constant_at_the_depth_limit_is_refused_as_in_the_whole_document(constant):
    """python-json maps a non-finite constant to a one-level ``{"$float": ...}``, which counts toward the depth: an
    element of an array at exactly the depth limit is refused, as the whole-document loader does (bug pass BF-17)."""
    limits = LIMITS.replace(max_json_depth=3)
    data = f'{{"a": {{"messages": [{constant}, 1]}}}}'.encode()
    with pytest.raises(IngestError) as whole:
        strict_json_loads(data, limits, profile="python-json")
    assert whole.value.code == "ingest.json.depth"
    assert code_of(data, limits, ("/a/messages",), profile="python-json") == "ingest.json.depth"
    one_up = f'{{"messages": [{constant}, 1]}}'.encode()  # one level less: accepted by both
    assert strict_json_loads(one_up, limits, profile="python-json")["messages"][1] == 1
    assert [i.value for i in open_json_stream(one_up, limits, arrays=["/messages"], profile="python-json")][1] == 1


@pytest.mark.parametrize(("data", "code"), [
    (b'{"messages": [1], "messages": [2]}', "ingest.json.duplicate_key"),
    (b'{"messages": [1, 2], "x": {"y": 1, "y": 2}}', "ingest.json.duplicate_key"),
    (b'{"messages": [1, NaN]}', "ingest.number.nonfinite"),
    (b'{"messages": [1, ' + b"9" * 1001 + b"]}", "ingest.number.digits"),
    (b'{"messages": [1, "\xc3\x28"]}', "ingest.json.encoding"),
    (b'\xef\xbb\xbf{"messages": [1]}', "ingest.json.bom"),
    (b'{\x00"messages": [1]}', "ingest.json.encoding"),
    (b'{"messages": [1,]}', "ingest.json.syntax"),
    (b'{"messages": [1 2]}', "ingest.json.syntax"),
    (b'{"messages": [1]', "ingest.json.syntax"),
    (b'{"messages": [1]} []', "ingest.json.syntax"),
    (b'{"messages": [1]}', None),
])  # fmt: skip
def test_strict_rules_and_codes_are_those_of_the_whole_document_loader(data, code):
    if code is None:
        assert [i.value for i in open_json_stream(data, arrays=["/messages"])] == [1]
        return
    assert code_of(data, arrays=("/messages",)) == code
    with pytest.raises(IngestError) as err:
        strict_json_loads(data)
    assert err.value.code == code


def test_nothing_is_yielded_when_a_defect_follows_valid_elements():
    data = doc(50)[:-1] + b', "events": []}'  # a duplicate key at the very end
    stream_items: list[object] = []
    with pytest.raises(IngestError) as err:
        stream = open_json_stream(data, arrays=["/messages", "/events"])
        stream_items.extend(stream)
    assert err.value.code == "ingest.json.duplicate_key" and stream_items == []


def test_offsets_are_absolute():
    data = b'{"pad": "' + b"p" * 100 + b'", "messages": [1, {"a": 1, "a": 2}]}'
    with pytest.raises(IngestError) as err:
        open_json_stream(data, arrays=["/messages"])
    assert err.value.offset is not None and data[err.value.offset : err.value.offset + 1] in (b"{", b"}", b'"', b",")
    items = list(open_json_stream(b'{"pad": 0, "messages": [10, 20]}', arrays=["/messages"]))
    assert [(i.index, i.offset) for i in items] == [(0, 24), (1, 28)]


def test_a_source_that_changes_between_passes_is_refused():
    data = doc(3)
    source = io.BytesIO(data)
    stream = open_json_stream(source, arrays=["/messages"])
    source.seek(0)
    source.write(data.replace(b'"messages": [', b'"messages": [{}, ', 1)[: len(data)])
    with pytest.raises(IngestError):
        list(stream)


def test_a_declared_pointer_that_is_not_an_array_stays_in_the_envelope():
    stream = open_json_stream(b'{"messages": {"a": [1]}, "events": [1]}', arrays=["/messages", "/events"])
    assert stream.envelope == {"messages": {"a": [1]}, "events": []} and stream.counts == {"/messages": 0, "/events": 1}


@pytest.mark.slow
def test_a_document_above_max_json_bytes_streams_in_bounded_memory():
    """80 MiB (above the 64 MiB whole-document cap), messages/events shape: peak Python memory stays far below it."""
    element = json.dumps({"role": "assistant", "content": "c" * 600, "tool_calls": [{"name": "fs.read", "args": {"p": "/x"}}]})
    n = (80 * MIB) // (len(element) + 2)
    data = ('{"model": "m", "messages": [' + ",".join([element] * n) + '], "events": []}').encode()
    assert len(data) > LIMITS.max_json_bytes
    with pytest.raises(IngestError):
        strict_json_loads(data)
    tracemalloc.start()
    try:
        stream = open_json_stream(data, arrays=["/messages", "/events"])
        count = sum(1 for _ in stream)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert count == n == stream.counts["/messages"]
    assert peak < 16 * MIB + len(data) // 1000, peak  # the source bytes are the caller's; parsing holds one element


@pytest.mark.parametrize(("data", "code"), [
    pytest.param(b'{"m":[1],"x":' + b"[" * 1_000_000, "ingest.json.depth", id="envelope-brackets"),
    pytest.param(b"{" + b'"m":[],' * 150_000 + b'"z":1}', "ingest.json.duplicate_key", id="repeated-declared-array"),
])
def test_the_scanner_refuses_depth_and_repeated_arrays_before_holding_state(data: bytes, code: str) -> None:
    """Pre-round review D #0: pass 1 kept one frame per envelope bracket and one segment per repeat of a declared array
    before the envelope parse refused them (about 73x memory: past the T1 map cap under a 64 MiB envelope raise). Now
    both are refused when met, in memory independent of the input's length."""
    tracemalloc.start()
    try:
        with pytest.raises(IngestError) as exc:
            for _ in open_json_stream(data, LIMITS, arrays=["/m"]):
                pass
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert exc.value.code == code
    assert peak < 8 * MIB, peak
