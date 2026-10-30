"""D-222: ``string_value_at`` returns a string only when the strict loader proves it, and the same string a whole parse
resolves; anything it cannot prove is ``None`` (the caller parses the region whole)."""

from __future__ import annotations

import hashlib
import json

import pytest

from agentprov.ingest.jsonspan import string_value_at
from agentprov.ingest.limits import IngestLimits


def test_a_member_string_is_found_by_its_span():
    data = b'{"a": 1, "b": {"c": [true, "x", "y\\u00e9\\"]"]}, "d": "z"}'
    assert string_value_at(data, "/b/c/2") == 'yé"]'
    assert string_value_at(data, "/d") == "z"


def test_brackets_quotes_and_colons_inside_strings_are_not_structure():
    data = b'{"k:[{": "\\"}]", "t": ["],", {"u": "{["}], "v": "ok"}'
    assert string_value_at(data, "/v") == "ok"
    assert string_value_at(data, "/t/1/u") == "{["
    assert string_value_at(data, "/k:[{") == '"}]'


def test_member_names_are_decoded_and_pointer_tokens_unescaped():
    data = json.dumps({"a/b": {"m~n": "v", "é": "w"}}, ensure_ascii=True).encode()
    assert string_value_at(data, "/a~1b/m~0n") == "v"
    assert string_value_at(data, "/a~1b/é") == "w"


def test_the_root_string_and_whitespace():
    assert string_value_at(b' \n"hello"\t', "") == "hello"
    assert string_value_at(b'{ "a" :\n[ "x" ,\t"y" ] }', "/a/1") == "y"


@pytest.mark.parametrize(("data", "pointer"), [
    (b'{"a": 1}', "/a"),  # not a string
    (b'{"a": "x"}', "/b"),  # absent member
    (b'["x"]', "/1"),  # index out of range
    (b'["x", "y"]', "/01"),  # a non-canonical index
    (b'{"a": "x", "a": "y"}', "/a"),  # duplicate key: the strict loader refuses the envelope
    (b'{"a": "x",}', "/a"),  # trailing comma
    (b'{"a": "x"', "/a"),  # truncated
    (b'{"a": "x\\q"}', "/a"),  # an invalid escape in the token
    (b'{"a": "x\x01"}', "/a"),  # a raw control character in the token
    (b'{"a": "x", "b": "\\q"}', "/a"),  # an invalid escape elsewhere
    (b'{"a": "x", "b": 01}', "/a"),  # a malformed number elsewhere
    (b'{"a": "\xff"}', "/a"),  # invalid UTF-8 in the token
    (b'{"a": "x", "b": "\xff"}', "/a"),  # invalid UTF-8 elsewhere
    (b'\xef\xbb\xbf{"a": "x"}', "/a"),  # a BOM
    (b'{"a": "x"} {}', "/a"),  # trailing data
    (b'{"a": {"b": "x"]}', "/a/b"),  # mismatched brackets
    (b'{"a": "x"}', "a"),  # not a pointer
    (b'{"a": NaN, "b": "x"}', "/b"),  # a non-finite constant under the strict profile
])
def test_whatever_cannot_be_proven_is_none(data, pointer):
    assert string_value_at(data, pointer) is None


def test_the_depth_limit_is_kept():
    limits = IngestLimits(max_json_depth=4)
    assert string_value_at(b'[[[["x"]]]]', "/0/0/0/0", limits) == "x"  # depth 4: at the limit
    assert string_value_at(b'[[[[["x"]]]]]', "/0/0/0/0/0", limits) is None  # the pointer walks past the limit
    assert string_value_at(b'["x", [[[["deep"]]]]]', "/0", limits) is None  # a sibling past the limit: the envelope fails


def test_the_size_caps_are_the_loaders():
    limits = IngestLimits(max_json_bytes=1 << 10, max_jsonl_line_bytes=1 << 9)
    doc = json.dumps({"a": "x" * 600}).encode()
    assert string_value_at(doc, "/a", limits) == "x" * 600
    assert string_value_at(doc, "/a", limits, record=True) is None  # over the record cap


def test_a_lone_surrogate_escape_is_returned_as_the_loader_reads_it():
    assert string_value_at(b'{"a": "\\ud800"}', "/a") == "\ud800"


def test_a_value_spelling_the_placeholder_cannot_stand_in_for_the_located_one():
    # the placeholder carries the region's own digest, so no string of the region can equal it
    base = b'{"a": "x", "b": "PLACEHOLDER"}'
    guess = "agentprov.carve.span:" + hashlib.sha256(base).hexdigest()
    data = base.replace(b"PLACEHOLDER", guess.encode())
    assert string_value_at(data, "/a") == "x"
    assert string_value_at(data, "/b") == guess
