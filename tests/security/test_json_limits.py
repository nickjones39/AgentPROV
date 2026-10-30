"""SEC-01, SEC-02, SEC-04 (K.12.2): hostile JSON values, depth and size caps. Limits come from IngestLimits()."""

from __future__ import annotations

import json
import sys
import time

import pytest

from agentprov.errors import IngestError
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads

LIMITS = IngestLimits()


def code_of(data: bytes, limits: IngestLimits = LIMITS, **kw) -> str:
    with pytest.raises(IngestError) as info:
        strict_json_loads(data, limits, **kw)
    return info.value.code


@pytest.mark.parametrize("depth", [1, 2, 5, 50, 255])
def test_sec01_duplicate_keys_at_every_depth(depth):
    inner = b'{"k":1,"k":2}'
    doc = b'{"a":' * depth + inner + b"}" * depth
    assert code_of(doc) == "ingest.json.duplicate_key"
    doc_list = b"[" * depth + inner + b"]" * depth
    assert code_of(doc_list) == "ingest.json.duplicate_key"


def test_sec01_duplicate_key_that_differs_only_by_escape_is_still_a_duplicate():
    assert code_of(b'{"a":1,"\\u0061":2}') == "ingest.json.duplicate_key"


@pytest.mark.parametrize("literal", [b"NaN", b"Infinity", b"-Infinity", b"nan", b"inf"])
def test_sec01_nonfinite_literals(literal):
    code = code_of(b"[" + literal + b"]")
    assert code in {"ingest.number.nonfinite", "ingest.json.syntax"}
    if literal[:1] in (b"N", b"I", b"-"):
        assert code == "ingest.number.nonfinite"


def test_sec01_overflowing_float_and_enormous_integer_have_typed_codes():
    assert code_of(b"1e400") == "ingest.number.nonfinite"
    assert code_of(b"1" * 1_000_000) == "ingest.number.digits"  # before CPython's own int-string limit (obs-G4)
    assert code_of(b"-" + b"9" * (LIMITS.max_int_digits + 1)) == "ingest.number.digits"
    assert code_of(b"[" + b"9" * 20_000 + b"]") == "ingest.number.digits"


def test_sec01_digit_cap_below_cpython_limit_so_the_typed_error_fires_first():
    cpython_limit = sys.get_int_max_str_digits()
    assert cpython_limit == 0 or LIMITS.max_int_digits < cpython_limit


@pytest.mark.parametrize("n", [LIMITS.max_json_depth + 1, 1000, 5000, 100_000, 200_000])
def test_sec02_depth_over_the_cap_is_a_typed_error_never_recursionerror(n):
    for opener, closer in ((b"[", b"]"), (b'{"a":', b"}")):
        start = time.monotonic()
        assert code_of(opener * n + closer * n) == "ingest.json.depth"
        assert time.monotonic() - start < 5
    assert code_of(b"[" * n) == "ingest.json.depth"  # unterminated: the pre-scan fires before the parser


def test_sec02_depth_257_and_the_200kb_file():
    assert code_of(b"[" * (LIMITS.max_json_depth + 1) + b"]" * (LIMITS.max_json_depth + 1)) == "ingest.json.depth"
    assert code_of(b"[" * 200_000) == "ingest.json.depth"


def test_sec02_depth_cap_holds_with_a_tiny_recursion_limit():
    old = sys.getrecursionlimit()
    try:
        sys.setrecursionlimit(max(old // 4, 400))
        depth = LIMITS.max_json_depth
        assert strict_json_loads(b"[" * depth + b"]" * depth) is not None
        assert code_of(b"[" * (depth + 1) + b"]" * (depth + 1)) == "ingest.json.depth"
    finally:
        sys.setrecursionlimit(old)


def test_sec02_unterminated_string_hiding_brackets_cannot_bypass_the_pre_scan():
    depth = LIMITS.max_json_depth + 10
    assert code_of(b"[" * depth + b'"abc') == "ingest.json.depth"
    assert code_of(b'"' + b"[" * depth) == "ingest.json.syntax"  # nothing was nested: the parser rejects at once


def test_sec02_quote_escape_patterns_do_not_make_the_prescan_quadratic():
    start = time.monotonic()
    code_of(b'"' + b'\\"' * 3_000_000)
    assert time.monotonic() - start < 5


@pytest.mark.parametrize("delta", [-1, 0, 1])
def test_sec04_document_size_is_decided_before_decoding_or_parsing(delta, monkeypatch):
    limits = LIMITS.replace(max_json_bytes=1024)
    data = b" " * (limits.max_json_bytes + delta - 1) + b"1"
    if delta > 0:
        monkeypatch.setattr(json, "loads", lambda *a, **k: pytest.fail("parsed an over-size document"))
        assert code_of(data, limits) == "ingest.size.file"
    else:
        assert strict_json_loads(data, limits) == 1


def test_sec04_default_file_cap_rejects_64mib_plus_one_without_parsing(monkeypatch):
    monkeypatch.setattr(json, "loads", lambda *a, **k: pytest.fail("parsed an over-size document"))
    assert code_of(b" " * (LIMITS.max_json_bytes + 1)) == "ingest.size.file"


@pytest.mark.parametrize("delta", [-1, 0, 1])
def test_sec04_record_cap(delta):
    limits = LIMITS.replace(max_jsonl_line_bytes=200)
    data = b'"' + b"x" * (limits.max_jsonl_line_bytes - 2 + delta) + b'"'
    if delta > 0:
        assert code_of(data, limits, record=True) == "ingest.size.record"
    else:
        assert strict_json_loads(data, limits, record=True)


def test_sec01_hostile_but_valid_values_survive_byte_identically():
    payload = {"k": chr(0x202E) + "x" + chr(0x200B) + chr(0x1B) + "[2J" + chr(0xE0041)}
    text = json.dumps(payload)  # escapes everything; the loader must restore it exactly
    assert strict_json_loads(text.encode()) == payload
