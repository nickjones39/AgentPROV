"""The stdlib JSON-Schema subset shared below the adapter layer (``agentprov.io.jsonschema_subset``; C.14.4)."""

from __future__ import annotations

import pytest

from agentprov.io.jsonschema_subset import check_against_schema, pattern_matches, unsupported_keywords

SCHEMA = {
    "type": "object",
    "properties": {
        "n": {"type": "integer", "minimum": 0},
        "tags": {"type": "array", "items": {"type": "string", "enum": ["a", "b"]}},
        "nothing": {"type": "null"},
        "name": {"type": "string", "pattern": "^x"},
    },
    "required": ["n"],
    "additionalProperties": False,
    "description": "annotation keywords constrain nothing",
}


def test_conforming_values() -> None:
    assert unsupported_keywords(SCHEMA) == []
    assert check_against_schema({"n": 0, "tags": ["a"], "nothing": None, "name": "xy"}, SCHEMA) == []


@pytest.mark.parametrize(
    "value",
    [{}, {"n": -1}, {"n": True}, {"n": 1.5}, {"n": 1, "tags": ["c"]}, {"n": 1, "nothing": 0}, {"n": 1, "name": "y"},
     {"n": 1, "extra": 0}, []],
)
def test_violations(value: object) -> None:
    assert check_against_schema(value, SCHEMA)


def test_patterns_can_be_left_unevaluated() -> None:
    skipped: list[str] = []
    assert check_against_schema({"n": 1, "name": "y"}, SCHEMA, patterns=False, skipped=skipped) == []
    assert skipped == ["/name"]


@pytest.mark.parametrize(
    "schema",
    [[], {"oneOf": []}, {"type": "date"}, {"properties": []}, {"items": 1}, {"required": "n"}, {"enum": "a"},
     {"pattern": 1}, {"minimum": "0"}, {"additionalProperties": 1}, {"properties": {"x": {"$ref": "#"}}}],
)
def test_unsupported_schemas_are_reported(schema: object) -> None:
    assert unsupported_keywords(schema)


@pytest.mark.parametrize(
    ("pattern", "value", "expected"),
    [
        ("^m[0-9]+$", "m12", True), ("^m[0-9]+$", "m12\n", False), ("^m[0-9]+$", "m12\n\n", False),
        ("^m[0-9]+$", "m12\r", False), ("^m[0-9]+$", "\nm12", False),
        ("^a$|^b$", "b\n", False), ("^(a|b$)", "b", True), ("^[$]+$", "$$", True), ("^[$]+$", "$$\n", False),
        (r"^a\$$", "a$", True), (r"^a\$$", "a$\n", False), (r"^a\\$", "a\\", True), ("^[]$]$", "$", True),
        ("^[^$]$", "x", True), ("^[^]$]$", "x", True), ("^[^]$]$", "$", False),
        ("^x", "x\n", True), ("x", "ax\ny", True),  # unanchored and start-anchored patterns keep their meaning
    ],
)  # fmt: skip
def test_dollar_matches_only_at_the_end_of_the_input(pattern: str, value: str, expected: bool) -> None:
    """Escaping audit F-06: Python's ``$`` also matches before a trailing newline; JSON Schema's (ECMA-262) does not."""
    assert pattern_matches(pattern, value) is expected
    schema = {"type": "string", "pattern": pattern}
    assert (check_against_schema(value, schema) == []) is expected


def test_the_agentdojo_family_checker_applies_the_same_rule() -> None:
    from agentprov.adapters.agentdojo.profile import check_against_schema as family_check

    schema = {"type": "string", "pattern": "^m[0-9]+$"}
    assert family_check("m12", schema) == []
    assert family_check("m12\n", schema) != []


@pytest.mark.parametrize(
    ("value", "enum"),
    [(True, [1]), (False, [0]), (1, [True]), (0, [False]), ([True], [[1]]), ({"a": False}, [{"a": 0}]),
     (1.0, [True]), ([1, [True]], [[1, [1]]])],
)  # fmt: skip
def test_enum_keeps_booleans_apart_from_numbers(value: object, enum: list[object]) -> None:
    """CA-11: enum compares JSON values, under which ``true`` is not ``1`` (Python's ``True == 1`` is not JSON equality)."""
    assert check_against_schema(value, {"enum": enum}) == ["/: not one of the enumerated values"]


@pytest.mark.parametrize(
    ("value", "enum"),
    [(1, [1.0]), (1.0, [1]), (True, [True]), (None, [None]), ("a", ["a"]), ([1, {"b": [False]}], [[1.0, {"b": [False]}]]),
     ({"x": 1, "y": True}, [{"y": True, "x": 1}])],
)  # fmt: skip
def test_enum_still_matches_equal_json_values(value: object, enum: list[object]) -> None:
    assert check_against_schema(value, {"enum": enum}) == []


@pytest.mark.parametrize("type_value", [["string", "null"], {"a": 1}, 3, None, True])
def test_a_non_string_type_is_reported_not_raised(type_value) -> None:
    """Pre-round review D #7: an untrusted SEM header's ``ns`` schema with a list- or object-valued ``type`` is an
    unsupported schema (a finding), never a TypeError from the set lookup."""
    assert unsupported_keywords({"type": type_value}) == ["/type"]
    assert unsupported_keywords({"type": "object", "properties": {"p": {"type": type_value}}}) == ["/properties/p/type"]
