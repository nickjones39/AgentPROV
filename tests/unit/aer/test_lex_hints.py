"""C.11.4 (AD-02): sparse ``ext.lex`` hints written only by ``canon.lex_hints``."""

from __future__ import annotations

import json

from agentprov.aer.canon import LexHints, decode_value, dumps_line, encode_value, lex_hints, loads_strict

SOURCE_TEXT = '{"id": 1, "amount": 1.0, "recipient": "x", "date": "d", "nested": {"z": 1, "a": 2.0}}'


def test_hints_record_member_order_and_integral_floats() -> None:
    source = json.loads(SOURCE_TEXT)
    hints = lex_hints(source, "/args")
    assert hints == {
        "ord": {"/args": ["id", "amount", "recipient", "date", "nested"], "/args/nested": ["z", "a"]},
        "flt": ["/args/amount", "/args/nested/a"],
    }


def test_no_hints_when_source_matches_jcs_form() -> None:
    assert lex_hints({"a": 1, "b": [2.5, "x"]}, "/args") == {}


def test_hints_are_deterministic_and_sorted() -> None:
    a = lex_hints({"b": 1.0, "a": 2.0}, "/x")
    assert a == {"ord": {"/x": ["b", "a"]}, "flt": ["/x/a", "/x/b"]}
    assert lex_hints({"b": 1.0, "a": 2.0}, "/x") == a


def test_source_text_is_regenerated_exactly_from_canonical_line_and_hints() -> None:
    source = json.loads(SOURCE_TEXT)
    lex = LexHints()
    encoded = encode_value(source, at="/args", lex=lex)
    line = dumps_line({"args": encoded, "ext": {"lex": lex.as_dict()}})
    parsed = loads_strict(line[:-1])
    assert isinstance(parsed, dict)
    back = decode_value(parsed["args"], at="/args", lex=LexHints.from_dict(parsed["ext"]["lex"]))
    assert json.dumps(back) == json.dumps(source)  # Python spelling: 1.0, member order


def test_without_hints_order_and_float_spelling_are_lost() -> None:
    source = json.loads(SOURCE_TEXT)
    parsed = loads_strict(dumps_line({"args": encode_value(source, at="/args", lex=LexHints())})[:-1])
    assert isinstance(parsed, dict)
    back = decode_value(parsed["args"], at="/args", lex=None)
    assert json.dumps(back) != json.dumps(source)


def test_dollar_wrapped_objects_use_the_wrapped_pointer() -> None:
    source = {"$k": 1, "b": 2.0, "a": 1}
    hints = lex_hints(source, "/args")
    assert hints["ord"] == {"/args/$lit": ["$k", "b", "a"]}
    assert hints["flt"] == ["/args/$lit/b"]


def test_from_dict_roundtrip_and_empty() -> None:
    hints = LexHints.from_dict({"ord": {"/x": ["b", "a"]}, "flt": ["/y"]})
    assert hints.as_dict() == {"ord": {"/x": ["b", "a"]}, "flt": ["/y"]}
    assert not LexHints.from_dict(None) and LexHints().as_dict() == {}


def test_validator_checks_lex_hints_against_the_record() -> None:
    from aer_support import codes_of, edit, example_records, validate_example

    parts = [{"t": "text", "text": None}, {"t": "tool_call", "name": "lookup", "args": {"b": 1, "a": 2.0}}]
    good = {"ord": {"/parts/1/args": ["b", "a"]}, "flt": ["/parts/1/args/a"]}
    ok = edit(example_records(), "m1", parts=parts, ext={"lex": good})
    assert codes_of(validate_example(ok)) == []

    def codes(lex: dict[str, object]) -> list[str]:
        return codes_of(validate_example(edit(example_records(), "m1", parts=parts, ext={"lex": lex})))

    assert "aer.ref.dangling" in codes({"ord": {"/parts/9/args": ["b", "a"]}})
    assert "aer.ref.dangling" in codes({"ord": {"/parts/0/text": ["b", "a"]}})  # not an object
    assert "aer.schema.pattern" in codes({"ord": {"/parts/1/args": ["b", "z"]}})  # not a permutation
    assert "aer.schema.pattern" in codes({"ord": {"/parts/1/args": ["a", "b"]}})  # equals JCS order: no hint needed
    assert "aer.ref.dangling" in codes({"flt": ["/parts/1/nope"]})
    assert "aer.ref.dangling" in codes({"flt": ["/parts/1/name"]})  # a string, not a number
    assert "aer.schema.pattern" in codes({})  # an empty lex object must be omitted
