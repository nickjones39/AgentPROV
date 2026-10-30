"""C.11.1-C.11.3: canonical lines, ``$``-escapes and the strict line parser."""

from __future__ import annotations

import math

import pytest

from agentprov.aer.canon import (
    I_JSON_MAX,
    CanonError,
    LexHints,
    decode_value,
    dumps_line,
    encode_value,
    loads_strict,
    pointer_escape,
    pointer_unescape,
)


def enc(value: object) -> object:
    return encode_value(value, at="/v", lex=LexHints())


def test_dumps_line_is_jcs_plus_lf() -> None:
    assert dumps_line({"b": 1, "a": [True, None, "x"]}) == b'{"a":[true,null,"x"],"b":1}\n'


def test_dumps_line_independent_of_member_insertion_order() -> None:
    assert dumps_line({"z": 1, "a": 2}) == dumps_line({"a": 2, "z": 1})


@pytest.mark.parametrize("bad", [{"a": float("nan")}, {"a": 2**53}, {"a": "\ud800"}, {"a": (1, 2)}, {"a": b"x"}, {1: 2}, {"a": {1, 2}}])
def test_dumps_line_rejects_non_i_json_values(bad: dict[object, object]) -> None:
    with pytest.raises(CanonError):
        dumps_line(bad)  # type: ignore[arg-type]


def test_strings_are_byte_faithful() -> None:
    nasty = "e\u0301 \u00e9\r\n\t\u2028 \u0000"
    line = dumps_line({"s": nasty})
    assert loads_strict(line[:-1]) == {"s": nasty}  # no normalisation, no newline conversion


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (2**53, {"$int": str(2**53)}),
        (-(2**53), {"$int": str(-(2**53))}),
        (I_JSON_MAX, I_JSON_MAX),
        (float("nan"), {"$float": "NaN"}),
        (float("inf"), {"$float": "Infinity"}),
        (float("-inf"), {"$float": "-Infinity"}),
        (-0.0, {"$float": "-0"}),
        (0.0, 0.0),
        ("\ud800x", {"$utf16": "2AAAeA=="}),
        ({"$ref": 1}, {"$lit": {"$ref": 1}}),
        ({"a": {"$b": 1}}, {"a": {"$lit": {"$b": 1}}}),
    ],
)
def test_encode_escapes(value: object, expected: object) -> None:
    assert enc(value) == expected


@pytest.mark.parametrize(
    "value",
    [2**53 + 7, -(10**30), float("inf"), -0.0, "\ud800", "a\udfffb", {"$x": [1, {"$y": 2}]}, [{"$lit": 3}], 3.5, {"k": [1.0]}],
)
def test_encode_decode_roundtrip(value: object) -> None:
    lex = LexHints()
    encoded = encode_value(value, at="/v", lex=lex)
    line = dumps_line({"v": encoded})
    parsed = loads_strict(line[:-1])
    assert isinstance(parsed, dict)
    back = decode_value(parsed["v"], at="/v", lex=lex)
    assert repr(back) == repr(value)  # repr distinguishes 1 from 1.0 and -0.0 from 0.0


def test_integral_floats_beyond_the_safe_range_roundtrip_as_floats() -> None:
    for value in (2.0**53, 1e20, 1e21, 1e300):
        lex = LexHints()
        encoded = encode_value(value, at="/v", lex=lex)
        parsed = loads_strict(dumps_line({"v": encoded})[:-1])
        assert isinstance(parsed, dict)
        back = decode_value(parsed["v"], at="/v", lex=lex)
        assert isinstance(back, float) and back == value


def test_non_json_types_are_rejected_by_encode() -> None:
    for bad in ((1, 2), b"x", {1, 2}, {1: 2}, object()):
        with pytest.raises(CanonError):
            enc(bad)


def test_decode_rejects_malformed_reserved_objects() -> None:
    for bad in (
        {"$int": 5},
        {"$int": "x"},
        {"$float": "nan"},
        {"$utf16": "!!"},
        {"$utf16": "AA=="},  # one byte: not whole UTF-16 code units
        {"$lit": 3},
        {"$unknown": 1},
        {"$int": "1", "x": 2},
    ):
        with pytest.raises(CanonError):
            decode_value(bad, at="/v", lex=None)  # type: ignore[arg-type]


def test_blob_references_pass_through_decode() -> None:
    ref = {"$blob": "sha256:" + "a" * 64, "bytes": 3}
    assert decode_value(ref, at="/v", lex=None) == ref


@pytest.mark.parametrize(
    ("data", "code"),
    [
        (b"\xef\xbb\xbf{}", "ingest.json.bom"),
        (b'{"a":1,"a":2}', "ingest.json.duplicate_key"),
        (b'{"a":NaN}', "ingest.number.nonfinite"),
        (b'{"a":1e999}', "ingest.number.nonfinite"),
        (b'{"a":', "ingest.json.syntax"),
        (b"\xff", "ingest.json.encoding"),
        (b"[" * 300 + b"]" * 300, "ingest.json.depth"),
    ],
)
def test_loads_strict_failures_carry_closed_ingest_codes(data: bytes, code: str) -> None:
    with pytest.raises(CanonError) as info:
        loads_strict(data)
    assert info.value.code == code


def test_pointer_escaping() -> None:
    assert pointer_escape("a/b~c") == "a~1b~0c"
    assert pointer_unescape(pointer_escape("a/b~c~1")) == "a/b~c~1"
    assert not math.isnan(1.0)
