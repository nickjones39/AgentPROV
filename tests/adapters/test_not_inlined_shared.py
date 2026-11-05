"""The shared not-inlined pass of the wave-2 mappers (``agentprov.adapters.not_inlined``; D-934, D-1063; reviews UC-38,
AU-RC-1, AU-RC-2, AU-NC-307): a string over 1 MiB of UTF-8 becomes ``{not_inlined: {sha256, bytes}}``, typed fields move
it, and everything that named a moved pointer follows it. Synthetic records only."""

from __future__ import annotations

import base64
import hashlib
from typing import Any

from agentprov.adapters.not_inlined import MIB, cited, moved_pointer, not_inlined, relink, retype, slim

BIG = "x" * (MIB + 1)


def _digest(text: str) -> dict[str, Any]:
    raw = text.encode("utf-8", "surrogatepass")
    return {"not_inlined": {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}}


def _utf16(text: str) -> dict[str, str]:
    """The C.11.3 form of a string holding a lone surrogate (what ``encode_value`` writes in a ``Json`` position)."""
    return {"$utf16": base64.b64encode(text.encode("utf-16-be", "surrogatepass")).decode("ascii")}


def _cite(pointer: str) -> str:
    return f"ns.content_not_inlined@1#{pointer}"


def test_strings_up_to_1_mib_are_kept_and_longer_ones_digested():
    found: list[str] = []
    assert slim({"a": "x" * MIB, "b": [BIG]}, ("value",), found) == {"a": "x" * MIB, "b": [_digest(BIG)]}
    assert found == ["/value/b/0"]


def test_a_utf16_value_is_measured_as_a_whole():
    """AU-RC-2: never a digest inside the wrapper. Kept while both its decoded text and its base64 fit in 1 MiB."""
    small = _utf16("a" * 1000 + "\ud800")
    found: list[str] = []
    assert slim(small, ("value",), found) == small and found == []
    mid = "a" * 400_000 + "\ud800"  # decoded 400,003 bytes of UTF-8, base64 over 1 MiB (the writer measures the base64)
    wrapped = _utf16(mid)
    assert set(wrapped) == {"$utf16"} and len(wrapped["$utf16"]) > MIB
    assert slim(wrapped, ("value",), found) == _digest(mid) and found == ["/value"]
    big = BIG + "\ud800"
    found = []
    assert slim(_utf16(big), ("value",), found) == _digest(big) and found == ["/value"]


def test_a_utf16_member_of_a_literal_body_is_a_source_key():
    body = {"$lit": {"$utf16": BIG}}
    found: list[str] = []
    assert slim(body, ("value",), found) == {"$lit": {"$utf16": _digest(BIG)}} and found == ["/value/$lit/$utf16"]


def test_a_utf16_form_that_is_not_base64_is_left_for_the_writer():
    odd = {"$utf16": "!" * (MIB + 10)}
    found: list[str] = []
    assert slim(odd, ("value",), found) == odd and found == []


def test_moved_pointers_and_citations_follow():
    moved = {"/parts/0/text": "/parts/0/value"}
    assert moved_pointer("/parts/0/text", moved) == "/parts/0/value"
    assert moved_pointer("/parts/0/textual", moved) == "/parts/0/textual"
    assert moved_pointer("/parts/1/text", moved) == "/parts/1/text"
    assert cited("ns.rule@1#/parts/0/text", moved) == "ns.rule@1#/parts/0/value" and cited("ns.rule@1", moved) == "ns.rule@1"


def test_the_pass_retypes_parts_and_moves_everything_that_names_them():
    records: list[dict[str, Any]] = [
        {"k": "message", "id": "m1", "ev": "O", "rule": ["ns.value_redacted@1#/parts/0/text", "ns.x@1#/actor"],
         "evf": {"/parts/0/text": "D"}, "unk": {"/parts/1/text/extra": "ambiguous"},
         "parts": [{"t": "tool_result", "responds_to": "m0#0", "text": BIG}, {"t": "text", "text": BIG}],
         "ext": {"ns": {"redacted": [{"p": "/parts/0/text", "rule": "prof@1#acct"}]}}},
        {"k": "message", "id": "m2", "ev": "I", "parts": [{"t": "tool_call", "name": "w", "args": {"q": "a"}, "args_raw": BIG}]},
        {"k": "message", "id": "m3", "ev": "O", "parts": [{"t": "text", "text": "short"}]},
    ]
    assert not_inlined(records, "ns", _cite) == ["m1", "m2"]
    m1, m2, m3 = records
    assert m1["parts"] == [{"t": "tool_result", "responds_to": "m0#0", "value": _digest(BIG)},
                           {"t": "other", "type": "text", "value": _digest(BIG)}]
    assert m1["rule"] == ["ns.value_redacted@1#/parts/0/value", "ns.x@1#/actor", _cite("/parts/0/value"), _cite("/parts/1/value")]
    assert m1["evf"] == {"/parts/0/value": "D", "/parts/1/value": "D"}
    assert m1["unk"] == {"/parts/1/value/extra": "ambiguous"}
    assert m1["ext"]["ns"]["redacted"] == [{"p": "/parts/0/value", "rule": "prof@1#acct"}]
    # AU-NC-307: args_raw is a typed string; its digest stands in ext, the decoded args are untouched
    assert m2["parts"] == [{"t": "tool_call", "name": "w", "args": {"q": "a"}}]
    assert m2["ext"] == {"ns": {"args_raw_not_inlined": {"0": _digest(BIG)}}}
    assert m2["evf"] == {"/ext/ns/args_raw_not_inlined/0": "I"} and m2["rule"] == [_cite("/ext/ns/args_raw_not_inlined/0")]
    assert m3 == {"k": "message", "id": "m3", "ev": "O", "parts": [{"t": "text", "text": "short"}]}


def test_a_utf16_value_whose_text_exceeds_1_mib_is_digested_though_its_base64_does_not():
    """Regen-batch row 186: one rule for every family. 350,001 code units (CJK and a lone surrogate) are 700,002 bytes
    of UTF-16, 933,336 base64 digits (under 1 MiB), but 1,050,003 bytes of UTF-8 (over it): digested. Row 181's pass
    (``adapters/inline_limit.py``, now merged here) measured only the base64 and kept this wrapper."""
    text = "中" * 350_000 + "\ud800"
    wrapped = _utf16(text)
    assert len(wrapped["$utf16"]) <= MIB < len(text.encode("utf-8", "surrogatepass"))
    found: list[str] = []
    assert slim(wrapped, ("value",), found) == _digest(text) and found == ["/value"]


def test_a_part_with_more_than_text_is_left_for_the_writer():
    """Nothing is dropped to make a digest fit: a reasoning part with a signature keeps its typed ``text`` (the writer
    refuses it, as before), never an ``other`` part without the signature (row 182's pass dropped the signature)."""
    record: dict[str, Any] = {"k": "message", "id": "m1", "ev": "O",
                              "parts": [{"t": "reasoning", "text": BIG, "signature": "sig"}]}
    assert not_inlined([record], "ns", _cite) == ["m1"]
    assert record["parts"] == [{"t": "reasoning", "text": _digest(BIG), "signature": "sig"}]
    assert record["evf"] == {"/parts/0/text": "D"} and record["rule"] == [_cite("/parts/0/text")]


def test_without_a_namespace_args_raw_stays_in_place():
    """The AgentDojo family's use (no ``ext`` member for ``args_raw``): the digest stays where the writer refuses it."""
    record: dict[str, Any] = {"k": "message", "id": "m1", "ev": "O",
                              "parts": [{"t": "tool_call", "name": "w", "args": {}, "args_raw": BIG}]}
    found: list[str] = []
    record["parts"] = slim(record["parts"], ("parts",), found)
    moved = {f: retype(record, f, None) for f in found}
    assert moved == {"/parts/0/args_raw": "/parts/0/args_raw"} and "ext" not in record
    relink(record, moved, "ns", _cite)
    assert record["parts"][0]["args_raw"] == _digest(BIG) and record["rule"] == [_cite("/parts/0/args_raw")]


def test_the_ids_are_sorted_and_distinct():
    records: list[dict[str, Any]] = [{"k": "message", "id": i, "ev": "O", "value": BIG} for i in ("m2", "m10")]
    assert not_inlined(records, "ns", _cite) == ["m10", "m2"]
