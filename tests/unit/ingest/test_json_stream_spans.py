"""Element spans of declared-array streaming (D-323 for RB-3): ``JsonStreamItem.end``.

``source[item.offset:item.end]`` is exactly one element's JSON text, so a D-218 carve locator
``{"bytes": [offset, end], "p": ...}`` parses only that element (not the whole document) and carves the same string as a
whole-document locator would. Pinned on a document with whitespace, nested arrays, a BOM-free envelope after the array,
and on a handle opened at a non-zero position (offsets are relative to it).
"""

from __future__ import annotations

import io
import json

from agentprov.ingest.jsonstream import open_json_stream
from agentprov.ingest.loaders import strict_json_loads
from agentprov.raw.carve import carve

DOC = (b'{"schema_version": "v2", "traces": [ \n {"id": "a", "out": "first", "steps": [1, [2, 3]]},'
       b'\t{"id": "b", "out": "second \\u00e9 \\"q\\"", "steps": []}  ,\n{"id": "c", "out": "", "steps": [{"x": "]"}]}\n ],'
       b' "tail": {"n": 3}}')


def _items(source):
    return list(open_json_stream(source, arrays=["/traces"]))


def test_each_span_is_exactly_its_element():
    items = _items(DOC)
    assert [i.value["id"] for i in items] == ["a", "b", "c"]
    for item in items:
        text = DOC[item.offset : item.end]
        assert text[:1] == b"{" and text[-1:] == b"}" and text == text.strip()
        assert strict_json_loads(text) == item.value


def test_a_bytes_locator_carves_the_same_string_as_the_whole_document():
    for n, item in enumerate(_items(DOC)):
        by_span = carve(DOC, {"bytes": [item.offset, item.end], "p": "/out"}, "utf8")
        whole = carve(DOC, {"p": f"/traces/{n}/out"}, "utf8")
        assert by_span.data == whole.data == item.value["out"].encode()


def test_spans_are_relative_to_the_handle_position():
    prefix = b"x" * 17
    handle = io.BytesIO(prefix + DOC)
    handle.seek(len(prefix))
    shifted = _items(handle)
    assert [(i.offset, i.end) for i in shifted] == [(i.offset, i.end) for i in _items(DOC)]
    assert json.loads(DOC[shifted[1].offset : shifted[1].end]) == shifted[1].value
