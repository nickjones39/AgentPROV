"""SEC-01 (K.12.3): encodings. Invalid UTF-8, UTF-16/32, BOM, NUL, escaped lone surrogates; nothing is silently replaced."""

from __future__ import annotations

import pytest

from agentprov.errors import IngestError, IngestFinding
from agentprov.ingest.loaders import strict_json_loads


def code_of(data: bytes, **kw) -> str:
    with pytest.raises(IngestError) as info:
        strict_json_loads(data, **kw)
    return info.value.code


@pytest.mark.parametrize(
    "data",
    [
        b'"\xc0\x80"',  # overlong NUL
        b'"\xc0\xaf"',  # overlong slash
        b'"\xe0\x80\xaf"',
        b'"\xff"',
        b'"\xfe"',
        b'"\xc3"',  # truncated sequence
        b'"\xe2\x82"',
        b'"\xf8\x88\x80\x80\x80"',  # 5-byte form
        b'"\xf4\x90\x80\x80"',  # above U+10FFFF
        b'"\xed\xa0\x80"',  # UTF-8 encoded surrogate U+D800
        b'"\xed\xbf\xbf"',  # UTF-8 encoded surrogate U+DFFF
        b'"\x80"',  # stray continuation byte
    ],
)
def test_sec01_invalid_utf8_gives_the_encoding_code_with_an_offset(data):
    with pytest.raises(IngestError) as info:
        strict_json_loads(data)
    assert info.value.code == "ingest.json.encoding"
    assert 1 <= info.value.offset <= len(data)


@pytest.mark.parametrize("codec", ["utf-16", "utf-16-le", "utf-16-be", "utf-32", "utf-32-le", "utf-32-be"])
def test_sec01_utf16_and_utf32_are_never_auto_detected(codec):
    document = '{"a": [1, 2, 3]}'
    assert code_of(document.encode(codec)) == "ingest.json.encoding"  # with BOM (utf-16/utf-32) or without
    assert code_of(document.encode(codec), profile="lenient-bom") == "ingest.json.encoding"


def test_sec01_utf8_bom_rejected_strict_and_stripped_with_a_finding_when_lenient():
    assert code_of(b"\xef\xbb\xbf[]") == "ingest.json.bom"
    findings: list[IngestFinding] = []
    assert strict_json_loads(b"\xef\xbb\xbf[]", profile="lenient-bom", findings=findings) == []
    assert [(f.code, f.severity) for f in findings] == [("ingest.json.bom", "warning")]
    assert code_of(b"\xef\xbb\xbf\xef\xbb\xbf[]", profile="lenient-bom") == "ingest.json.syntax"  # only one is stripped


def test_sec01_nul_bytes():
    assert code_of(b'["a\x00b"]') == "ingest.json.syntax"  # raw control character inside a string
    assert code_of(b"[\x00]") == "ingest.json.encoding"  # NUL in the first two bytes: UTF-16/32 pattern


def test_sec01_escaped_lone_surrogate_is_a_finding_and_the_code_units_are_recoverable():
    findings: list[IngestFinding] = []
    value = strict_json_loads(b'"a\\ud800b"', findings=findings)
    assert value == "a" + chr(0xD800) + "b"
    assert [(f.code, f.severity) for f in findings] == [("ingest.json.lone_surrogate", "info")]
    assert value.encode("utf-16-be", "surrogatepass") == b"\x00a\xd8\x00\x00b"  # nothing replaced with U+FFFD
    assert chr(0xFFFD) not in value
    strict = strict_json_loads(b'"\\udc00\\ud800"')  # reversed pair: two lone surrogates, still no rejection
    assert strict == chr(0xDC00) + chr(0xD800)


def test_sec01_valid_unusual_content_passes_byte_identically():
    escapes = b'"\\u202e\\u200b\\u001b[2J\\u0007\\u0000\\u2028\\u0085 \\ud83d\\ude00"'
    value = strict_json_loads(escapes)
    expected = chr(0x202E) + chr(0x200B) + chr(0x1B) + "[2J" + chr(7) + chr(0) + chr(0x2028) + chr(0x85) + " " + chr(0x1F600)
    assert value == expected
    raw = ('"' + chr(0x202E) + chr(0x200B) + chr(0x2028) + chr(0x85) + chr(0x1F600) + '"').encode("utf-8")
    assert strict_json_loads(raw) == raw[1:-1].decode("utf-8")


def test_sec01_error_for_invalid_utf8_does_not_echo_bytes():
    with pytest.raises(IngestError) as info:
        strict_json_loads(b'"SECRET' + b"\xff" + b'"')
    assert "SECRET" not in str(info.value)
