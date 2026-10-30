"""Pre-round review #28: under ``aer/0.2`` the reserved ``$utf16`` and ``$lit`` forms are accepted only in their C.11.3 shape.

``encode_value`` writes ``{"$utf16": base64}`` only for a string that is not a valid Unicode scalar sequence (whole UTF-16BE
code units), and ``{"$lit": object}`` only around an object with a member name beginning with ``$``. Before, the structural
check accepted any base64 (an odd byte count then crashed ``decode_value`` on a validated AER) and any wrapped object.
"""

from __future__ import annotations

import base64
from typing import Any

import pytest
from aer_support import example_records, make_registry, seal_record

from agentprov.aer.canon import LexHints, decode_value, encode_value
from agentprov.aer.validate import validate_records


def _codes(args: Any, version: str = "0.2") -> list[tuple[str, str]]:
    recs = example_records()
    recs[0]["aer"] = version
    next(r for r in recs if r["id"] == "m1")["parts"][1]["args"] = args
    report = validate_records([*recs, seal_record(recs)], store=None, catalogues=make_registry())
    return [(f.code, f.pointer) for f in report.errors]


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


@pytest.mark.parametrize(("args", "why"), [
    ({"x": {"$utf16": _b64(b"\x00a\x00")}}, "odd byte count: decode_value cannot read it"),
    ({"x": {"$utf16": _b64("abc".encode("utf-16-be"))}}, "a valid string is written plain"),
    ({"$lit": {"a": 1}}, "no member name beginning with $: written plain"),
])
def test_a_non_canonical_reserved_form_is_refused(args: Any, why: str) -> None:
    assert any(code == "aer.schema.pattern" for code, _p in _codes(args)), why


def test_aer_01_keeps_its_frozen_rules_for_the_reserved_forms() -> None:
    """aer/0.1's structural rules and its published schema are frozen (D-163): the shape check is aer/0.2's. No stored
    corpus holds a $utf16 or $lit form at all (regen item 162), and the writer never writes a non-canonical one."""
    assert _codes({"$lit": {"a": 1}}, version="0.1") == []


def test_the_canonical_forms_are_valid_and_decode() -> None:
    lone = "a\ud800b"
    encoded = encode_value({"x": lone, "$k": 1}, at="/parts/1/args", lex=LexHints())
    assert encoded["$lit"]["x"] == {"$utf16": _b64(lone.encode("utf-16-be", "surrogatepass"))}
    assert _codes(encoded) == []
    assert decode_value(encoded, at="/parts/1/args", lex=None) == {"x": lone, "$k": 1}
