"""The published JSON Schema ``schemas/aer-0.1.schema.json`` (C.17): freshness, validity, and fixed differential cases.

The Hypothesis differential test (phase-3 exit gate) is ``tests/property/test_validator_props.py``.
"""

from __future__ import annotations

import copy
import json
from importlib import resources
from typing import Any

import jsonschema
import pytest
from aer_support import structural_templates
from schema_builder import KINDS, OUT, render

from agentprov.aer import RECORD_KINDS, _structure


def load_schema() -> dict[str, Any]:
    data = resources.files("agentprov").joinpath("schemas/aer-0.1.schema.json").read_bytes()
    return json.loads(data)  # type: ignore[no-any-return]


SCHEMA = load_schema()
VALIDATOR = jsonschema.Draft202012Validator(SCHEMA)


def distinct_templates() -> list[dict[str, Any]]:
    """One template per (kind, member set): enough variety, a fraction of the cost."""
    seen: set[tuple[str, tuple[str, ...]]] = set()
    out = []
    for record in structural_templates():
        key = (record["k"], tuple(sorted(record)))
        if key not in seen:
            seen.add(key)
            out.append(record)
    return out


def schema_ok(record: Any) -> bool:
    return VALIDATOR.is_valid(record)


def code_ok(record: Any) -> bool:
    return not _structure.check_record(record)


def test_committed_schema_is_exactly_the_builder_output() -> None:
    assert OUT.read_text(encoding="utf-8") == render()


def test_schema_is_a_valid_draft_2020_12_schema_with_a_stable_id() -> None:
    jsonschema.Draft202012Validator.check_schema(SCHEMA)
    assert SCHEMA["$id"].endswith("aer-0.1.schema.json")
    assert SCHEMA["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_schema_covers_the_thirteen_kinds() -> None:
    assert set(KINDS) == RECORD_KINDS
    assert set(SCHEMA["properties"]["k"]["enum"]) == RECORD_KINDS
    assert {f"record_{k}" for k in KINDS} <= set(SCHEMA["$defs"])


def test_every_template_is_valid_in_both() -> None:
    for record in structural_templates():
        assert schema_ok(record) and code_ok(record), (record["k"], record["id"])


def test_a_fourteenth_kind_is_invalid_in_both() -> None:
    record = {"k": "plan", "id": "x", "ev": "O"}
    assert not schema_ok(record) and not code_ok(record)
    assert _structure.check_record(record)[0][0] == "aer.schema.kind"


def test_schema_enforces_the_removed_members_and_the_oneof_rules() -> None:
    by_id = {r["id"]: r for r in structural_templates()}
    te = copy.deepcopy(by_id["te0"])
    assert schema_ok(te)
    for mutation in (
        {"result": "m3"},
        {"call": None, "requested_by": None},
        {"requested_by": "agent"},
        {"status": "denied"},
    ):
        bad = {**te, **mutation}
        bad = {k: v for k, v in bad.items() if v is not None}
        assert not schema_ok(bad) and not code_ok(bad), mutation
    af = copy.deepcopy(by_id["af0"])
    both = {**af, "content": {"a": 1}}
    assert not schema_ok(both) and not code_ok(both)


# Fixed disagreement hunters: values on which a careless implementation differs.
TRICKY = [
    "m1\n", "m1 ", "", "M1", "m1#", "m1#01", "a0", "as", "exec", "seal", "run", "é", "m" * 33, "m" * 32,
    0, 1, -1, 1.0, 1.5, True, False, None, [], {}, {"$lit": 1}, {"$int": "5"}, {"$int": "0"}, {"$float": "NaN"},
    {"$blob": "sha256:" + "a" * 64}, {"$blob": "sha256:" + "a" * 64, "bytes": 1.0}, {"$x": 1}, {"": 1},
    "2026-10-08T12:00:00Z", "2026-10-08T12:00:00Z\n", "2026-13-08T12:00:00Z", "2026-10-08T24:00:00Z", "2026-10-08T12:00:60Z",
]


@pytest.mark.parametrize("value", TRICKY, ids=repr)
def test_tricky_values_agree_on_every_field_of_every_template(value: Any) -> None:
    for record in distinct_templates():
        for member in list(record):
            if member in ("k",):
                continue
            mutated = copy.deepcopy(record)
            mutated[member] = value
            assert schema_ok(mutated) == code_ok(mutated), (record["k"], record["id"], member, value)


@pytest.mark.slow
def test_tricky_values_agree_one_level_down() -> None:
    for record in distinct_templates():
        for member, inner in list(record.items()):
            if isinstance(inner, dict) and member not in ("ext", "params"):
                for key in list(inner):
                    for value in TRICKY:
                        mutated = copy.deepcopy(record)
                        mutated[member][key] = value
                        assert schema_ok(mutated) == code_ok(mutated), (record["id"], member, key, value)
            elif isinstance(inner, list) and inner and isinstance(inner[0], dict):
                for key in list(inner[0]):
                    for value in TRICKY:
                        mutated = copy.deepcopy(record)
                        mutated[member][0][key] = value
                        assert schema_ok(mutated) == code_ok(mutated), (record["id"], member, key, value)
