"""Phase-3 exit gate (C.17, D8 tier 7): the published JSON Schema and the in-code structural validator agree.

Hypothesis mutates structurally valid records of all 13 kinds (delete, replace, add members at any depth with
hostile values) and requires ``jsonschema`` and ``agentprov.aer._structure`` to give the same verdict; it also builds
valid records from independent field pools and requires both to accept them. A second group checks that the
streaming validator never raises on arbitrary bytes and is deterministic.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Iterator
from importlib import resources
from typing import Any

import jsonschema
from aer_support import ARTEFACT_SHA, make_registry, structural_templates
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from agentprov.aer import _structure
from agentprov.aer.validate import AerValidator

SCHEMA = json.loads(resources.files("agentprov").joinpath("schemas/aer-0.1.schema.json").read_bytes())
VALIDATOR = jsonschema.Draft202012Validator(SCHEMA)
TEMPLATES = structural_templates()
SETTINGS = settings(max_examples=400, deadline=None, derandomize=True, suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large])

DOLLAR_KEYS = ["$int", "$lit", "$blob", "$float", "$utf16", "$x", "$"]
KEYS = st.one_of(st.sampled_from(DOLLAR_KEYS + ["bytes", "media", "a", "p", "t", "text", "id", "unk", "/x"]), st.text(max_size=6))
LEAVES = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-(2**70), max_value=2**70),
    st.floats(allow_nan=False, allow_infinity=False),
    st.text(max_size=10),
    st.sampled_from(
        [
            "m1", "m1\n", "m1#0", "", "O", "D", "I", "O:source", "tst.d@1", "tst.d@1#/x", "/x", "a0", "sha256:" + "a" * 64,
            "a" * 64, "a" * 40, "2026-10-08T12:00:00Z", "2026-10-08T12:00:00", "tst:plan", "tst.sub", "other", "kept", "run",
            "not_recorded", "causal", "agent", "ex_aaaaaaaaaaaaaaaaaaaaaaaaaa", "0.1", "1.2.3", "attempt", "unknown", "$x",
        ]
    ),
)
JSON_VALUES = st.recursive(
    LEAVES,
    lambda children: st.one_of(
        st.lists(children, max_size=3),
        st.dictionaries(KEYS, children, max_size=3),
        st.fixed_dictionaries({"$blob": st.just("sha256:" + "b" * 64), "bytes": st.integers(-1, 5)}),
        st.fixed_dictionaries({"$int": st.text(alphabet="-0123456789", max_size=4)}),
    ),
    max_leaves=6,
)


def paths(value: Any, prefix: tuple[Any, ...] = ()) -> Iterator[tuple[Any, ...]]:
    yield prefix
    if isinstance(value, dict):
        for key, child in value.items():
            yield from paths(child, (*prefix, key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from paths(child, (*prefix, index))


def resolve(root: Any, path: tuple[Any, ...]) -> Any:
    for step in path:
        root = root[step]
    return root


@st.composite
def mutated_records(draw: st.DrawFn) -> dict[str, Any]:
    record = copy.deepcopy(draw(st.sampled_from(TEMPLATES)))
    for _ in range(draw(st.integers(1, 3))):
        all_paths = list(paths(record))
        path = draw(st.sampled_from(all_paths))
        op = draw(st.sampled_from(["delete", "replace", "add"]))
        if op == "delete" and path:
            parent = resolve(record, path[:-1])
            if isinstance(parent, dict):
                parent.pop(path[-1], None)
            else:
                parent.pop(path[-1])
        elif op == "replace" and path:
            resolve(record, path[:-1])[path[-1]] = draw(JSON_VALUES)
        else:
            target = resolve(record, path)
            if isinstance(target, dict):
                target[draw(KEYS)] = draw(JSON_VALUES)
            elif isinstance(target, list):
                target.insert(draw(st.integers(0, len(target))), draw(JSON_VALUES))
    return record


@settings(parent=SETTINGS, max_examples=1500)
@given(mutated_records())
def test_schema_and_validator_agree_on_mutated_records(record: dict[str, Any]) -> None:
    schema_valid = VALIDATOR.is_valid(record)
    findings = _structure.check_record(record)
    assert schema_valid == (not findings), (record, findings, [e.message[:90] for e in list(VALIDATOR.iter_errors(record))[:3]])


@SETTINGS
@given(st.sampled_from(TEMPLATES), st.sampled_from(["m", "agent", "a0", "exec", "x1"]))
def test_templates_are_valid_in_both_and_id_changes_agree(record: dict[str, Any], new_id: str) -> None:
    assert VALIDATOR.is_valid(record) and not _structure.check_record(record)
    changed = {**record, "id": new_id}
    assert VALIDATOR.is_valid(changed) == (not _structure.check_record(changed))


# ------------------------------------------------------------------------------------------ valid by construction
OPTIONAL_POOL: dict[str, dict[str, list[Any]]] = {
    "actor": {
        "name": ["n"], "role": ["planner"], "model": [{"requested": "m"}, {}], "params": [{"t": 1}, None, 3],
        "version": ["v1"], "code": [{"dist": "d", "commit": "abc"}], "on_behalf_of": ["agent"], "ext": [{"tst": {"a": 1}}],
        "evf": [{"/name": "I"}], "rule": [["tst.d@1"]], "src": [[{"a": "a0", "p": "/x"}]], "unk": [{"/code": "lost"}],
    },
    "scope": {
        "actor": ["agent"], "index": [0, 5], "scored": [True, False], "spawned_by": ["te0"], "status": ["ok", "limit"],
        "usage": [{"calls": 2}], "t": [{"start": "2026-10-08T12:00:00Z", "end": "2026-10-08T12:00:01Z"}, {"dur_s": 2, "dur_clock": "wall"}],
        "after": [[{"id": "m0", "b": "time"}]],
    },
    "message": {
        "actor": ["user"], "generated_by": ["mc0"], "after": [[{"id": "m0", "b": "pos"}]], "ext": [{"lex": {"flt": ["/parts/0/args/a"]}}],
        "unk": [{"/actor": "not_recorded"}],
    },
    "model_call": {
        "input": [["m0"], [{"id": "m0", "sent": ["other"]}]], "tools": ["fx0"], "params": [{"configured": {"t": 0.1}}],
        "reason": ["r"], "retry_of": ["mc0"], "finish_reason": ["stop"], "usage": [{"input_tokens": 1, "output_tokens": 2}],
        "served_model": ["m"], "response_id": ["r"], "request": [{"$blob": "sha256:" + "a" * 64, "bytes": 1}],
        "t": [{"start_naive": "2026-10-08T12:00:00.5"}],
    },
    "tool_execution": {
        "authorised_by": ["dc0"], "args": [{"a": [1, 2]}, None], "args_effective": [{"a": 1}], "exception": [{"type": "E", "message": "m"}],
        "returned": [{"$lit": {"$k": 1}}], "t": [{"mono_start_ns": 0}],
    },
    "decision": {"scope": ["att0"], "reason": ["r"], "original": ["m1#0", {"$blob": "sha256:" + "a" * 64, "bytes": 0}], "t": [{"end": "2026-10-08T12:00:01Z"}]},
    "state_change": {
        "cause": ["te0"], "changed": [True], "patch": [[{"op": "remove", "path": "/a"}]],
        "diff": [{"format": "f", "value": None, "truncated": True}], "snapshot_after": [{"$blob": "sha256:" + "a" * 64, "bytes": 1}],
        "before_sha256": ["a" * 64], "canon": ["jcs-rfc8785"],
    },
    "fixture": {"vector": ["v"], "media": ["m"], "actor": ["agent"]},
    "judgement": {"revises": ["j0"], "generated_by": ["mc1"], "inputs": [["m1", "m1#0"]], "t": [{"start": "2026-10-08T12:00:00Z"}]},
    "activity": {"actor": ["agent"], "inputs": [[], ["m0"]], "t": [{"start": "2026-10-08T12:00:00Z"}], "status": ["error"], "label": ["l"]},
    "artefact": {"media": ["m"], "sha256": ["a" * 64], "generated_by": ["ac0"]},
}
BASES: dict[str, dict[str, Any]] = {}
for _rec in TEMPLATES:
    BASES.setdefault(_rec["k"], _rec)


@SETTINGS
@given(st.data())
def test_records_built_from_independent_field_pools_are_valid_in_both(data: st.DataObject) -> None:
    kind = data.draw(st.sampled_from(sorted(OPTIONAL_POOL)))
    pool = OPTIONAL_POOL[kind]
    record = copy.deepcopy(BASES[kind])
    for member in data.draw(st.lists(st.sampled_from(sorted(pool)), unique=True, max_size=len(pool))):
        record[member] = copy.deepcopy(data.draw(st.sampled_from(pool[member])))
    assert VALIDATOR.is_valid(record) and not _structure.check_record(record), (record, _structure.check_record(record))


# ------------------------------------------------------------------------------------------ streaming validator
@SETTINGS
@given(st.lists(st.binary(max_size=200), max_size=6))
def test_validator_never_raises_on_arbitrary_lines_and_is_deterministic(raw_lines: list[bytes]) -> None:
    def run() -> tuple[tuple[str, ...], int]:
        v = AerValidator(store=None, catalogues=make_registry(), mode="release")
        for line in raw_lines:
            v.feed(line + b"\n")
        report = v.finish()
        return tuple(f"{f.code}@{f.line}:{f.pointer}" for f in report.findings), report.n_records

    assert run() == run()


@SETTINGS
@given(st.sampled_from(TEMPLATES), st.sampled_from(TEMPLATES))
def test_validator_is_deterministic_on_structured_input_and_never_echoes_artefact_digest_text(a: dict[str, Any], b: dict[str, Any]) -> None:
    from agentprov.aer.canon import dumps_line

    def run() -> list[str]:
        v = AerValidator(store=None, catalogues=make_registry(), mode="dev")
        for rec in (a, b):
            v.feed(dumps_line(rec))
        return [repr(f.to_json()) for f in v.finish().findings]

    first = run()
    assert first == run()
    assert ARTEFACT_SHA not in "".join(first)
