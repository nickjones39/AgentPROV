"""K.5.1 items 1, 5 and 6: every kind and part type is constructible; enum members and the ``other`` escape."""

from __future__ import annotations

from typing import Any

import pytest
from aer_support import codes_of, edit, example_records, insert_after, validate_example

from agentprov.aer.canon import dumps_line


def run(records: list[dict[str, Any]], **kw: Any) -> list[str]:
    return codes_of(validate_example(records, **kw))


def d(rec: dict[str, Any], rule: str = "tst.d@1") -> dict[str, Any]:
    return {**rec, "ev": "D", "rule": [rule]}


def test_every_part_type_is_constructible_and_serialisable() -> None:
    parts: list[dict[str, Any]] = [
        {"t": "text", "text": "x"},
        {"t": "text", "text": None},
        {"t": "reasoning", "text": "think", "signature": "s", "redacted": False, "provider_id": "p"},
        {"t": "tool_call", "name": "f", "args": {"a": 1}, "args_raw": "{\"a\":1}", "provider_call_id": None},
        {"t": "tool_result", "responds_to": "m1#1", "value": {"k": [1, 2]}, "error": None, "name": "f"},
        {"t": "blob", "data": {"$blob": "sha256:" + "a" * 64, "bytes": 3}, "media": "image/png"},
        {"t": "file", "name": "n", "media": "text/plain", "ref": "file-1"},
        {"t": "uri", "uri": "https://example.invalid/x", "media": "text/html"},
        {"t": "refusal", "text": "no"},
        {"t": "other", "type": "tst.thing", "value": [1, "x"]},
    ]
    for part in parts:
        recs = edit(example_records(), "m3", parts=[part])
        if part["t"] == "tool_result":
            recs = edit(recs, "m3", parts=[part])
        found = [c for c in run(recs, with_store=False) if c.startswith("aer.schema")]
        assert found == [], (part["t"], found)
        dumps_line(recs[-1])


@pytest.mark.parametrize(
    "part",
    [
        {"t": "text"},
        {"t": "text", "text": 5},
        {"t": "mystery", "text": "x"},
        {"text": "x"},
        {"t": "tool_call", "name": "f"},
        {"t": "tool_call", "args": {}},
        {"t": "tool_result", "responds_to": "m1#1"},  # neither text nor value
        {"t": "tool_result", "responds_to": "m1#1", "text": "a", "value": 1},  # both
        {"t": "tool_result", "responds_to": "m1", "text": "a"},  # not a part id
        {"t": "blob", "data": {"$blob": "sha256:x", "bytes": 1}, "media": "m"},
        {"t": "blob", "data": "x", "media": "m"},
        {"t": "file"},
        {"t": "uri"},
        {"t": "refusal", "text": None},
        {"t": "other", "type": "x"},
        {"t": "text", "text": "x", "extra": 1},
    ],
)
def test_malformed_parts_are_rejected(part: dict[str, Any]) -> None:
    found = run(edit(example_records(), "m3", parts=[part]))
    assert {"aer.schema.required", "aer.schema.pattern", "aer.schema.oneof", "aer.schema.additional", "aer.blob.ref"} & set(found)


def test_null_text_is_kept_as_null() -> None:
    recs = edit(example_records(), "m1", parts=[{"t": "text", "text": None}, {"t": "tool_call", "name": "lookup", "args": {}}])
    assert run(recs) == []


@pytest.mark.parametrize(
    ("record_id", "member", "good", "bad"),
    [
        ("agent", "kind", ["llm_agent", "user", "simulated_user", "attacker", "defense", "judge", "tool_runtime",
                           "environment", "harness", "benchmark"], ["planner", "generator", "memory", ""]),
        ("run", None, None, None),
        ("att0", "kind", ["attempt", "agent_invocation", "subagent", "thread"], ["workflow", "step", "branch"]),
        ("mc0", "role", ["agent", "auxiliary"], ["judge", "main"]),
        ("mc0", "status", ["kept", "discarded", "error", "cached"], ["retried", "ok"]),
        ("te0", "status", ["ok", "error", "invalid"], ["denied", "not_dispatched", "unknown", "validation_error"]),
    ],
)
def test_closed_enumerations(record_id: str, member: str | None, good: list[str] | None, bad: list[str] | None) -> None:
    if member is None:
        return
    for value in good or []:
        found = run(edit(example_records(), record_id, **{member: value}))
        assert not [c for c in found if c in ("aer.schema.pattern", "aer.subtype.missing")], (member, value, found)
    for value in bad or []:
        assert "aer.schema.pattern" in run(edit(example_records(), record_id, **{member: value})), (member, value)


def test_model_call_input_items_and_sent_transforms() -> None:
    ok = edit(example_records(), "mc1", input=["m0", {"id": "m1", "sent": ["error_substitution"], "sent_sha256": "a" * 64}, "m2"],
              evf={"/input": "I"}, rule=["tst.d@1", "tst.i@1#/input"])
    assert run(ok) == []
    for transform in ("error_substitution", "role_rewrite", "reasoning_passback", "formatting", "truncation", "other"):
        recs = edit(ok, "mc1", input=["m0", {"id": "m1", "sent": [transform]}, "m2"])
        assert run(recs) == [], transform
    assert "aer.schema.pattern" in run(edit(ok, "mc1", input=["m0", {"id": "m1", "sent": ["defence"]}, "m2"]))
    assert "aer.schema.pattern" in run(edit(ok, "mc1", input=["m0", {"id": "m1"}, "m2"]))  # `sent` is required in the object form
    assert "aer.schema.pattern" in run(edit(ok, "mc1", input=[{"base": "mc0", "plus": ["m1"]}]))


def test_tool_execution_has_exactly_one_of_call_requested_by_or_unk() -> None:
    base = example_records()
    assert "aer.schema.oneof" in run(edit(base, "te0", call=None))
    assert "aer.schema.oneof" in run(edit(base, "te0", requested_by="agent"))
    assert "aer.schema.oneof" not in run(edit(base, "te0", call=None, requested_by="agent"))
    ambiguous = edit(base, "te0", call=None, unk={"/call": "ambiguous"})
    assert "aer.schema.oneof" not in run(ambiguous)
    assert "aer.schema.oneof" in run(edit(base, "te0", call=None, unk={"/call": "lost"}))
    assert "aer.schema.oneof" in run(edit(base, "te0", unk={"/call": "ambiguous"}))  # call present and declared unknown


def test_enum_escape_needs_a_declared_subtype() -> None:
    other_actor = d({"k": "actor", "id": "weird", "kind": "other", "subtype": "tst.sub"})
    recs = insert_after(example_records(), "env", other_actor)
    assert run(recs) == []
    no_sub = insert_after(example_records(), "env", d({"k": "actor", "id": "weird", "kind": "other"}))
    assert "aer.subtype.missing" in run(no_sub)
    stray = insert_after(example_records(), "env", d({"k": "actor", "id": "weird", "kind": "user", "subtype": "tst.sub"}))
    assert "aer.subtype.missing" in run(stray)
    undeclared = insert_after(example_records(), "env", d({"k": "actor", "id": "weird", "kind": "other", "subtype": "tst.nope"}))
    assert "aer.subtype.undeclared" in run(undeclared)
    wrong_ns = insert_after(example_records(), "env", d({"k": "actor", "id": "weird", "kind": "other", "subtype": "zzz.sub"}))
    assert "aer.ext.undeclared" in run(wrong_ns)
    reserved = insert_after(example_records(), "env", d({"k": "actor", "id": "weird", "kind": "other", "subtype": "aer.sub"}))
    assert "aer.ext.undeclared" in run(reserved)
    assert "aer.schema.pattern" in run(insert_after(example_records(), "env", d({"k": "actor", "id": "weird", "kind": "other", "subtype": "nodot"})))


@pytest.mark.parametrize(
    ("kind", "field", "base"),
    [
        ("scope", "kind", {"id": "sc0", "parent": "run"}),
        ("decision", "verdict", {"id": "dc0", "actor": "agent", "subject": "te0"}),
        ("state_change", "target", {"id": "st0", "scope": "att0"}),
        ("fixture", "kind", {"id": "fx0"}),
    ],
)
def test_the_other_escape_on_the_remaining_enums(kind: str, field: str, base: dict[str, Any]) -> None:
    anchor = "te0"
    good = insert_after(example_records(), anchor, d({"k": kind, **base, field: "other", "subtype": "tst.sub", **({"content": "x"} if kind == "fixture" else {})}))
    assert "aer.subtype.missing" not in run(good) and "aer.subtype.undeclared" not in run(good), run(good)
    missing = insert_after(example_records(), anchor, d({"k": kind, **base, field: "other", **({"content": "x"} if kind == "fixture" else {})}))
    assert "aer.subtype.missing" in run(missing)


def test_scope_rules_run_scope_and_parents() -> None:
    base = example_records()
    assert "aer.schema.required" in run(edit(base, "att0", parent=None))
    assert "aer.schema.additional" in run(edit(base, "run", parent="att0"))
    assert "aer.schema.pattern" in run(edit(base, "run", kind="attempt", parent="run"))
    second = d({"k": "scope", "id": "run2", "kind": "run"})
    assert "aer.schema.pattern" in run(insert_after(base, "run", second))
    assert "aer.schema.oneof" in run([r for r in base if r["id"] != "run" and r["id"] != "att0" and r["k"] not in ("message", "model_call", "tool_execution")])


def test_state_change_digests_need_their_canonicalisation() -> None:
    sc = d({"k": "state_change", "id": "st0", "scope": "att0", "cause": "te0", "target": "environment",
            "before_sha256": "a" * 64, "after_sha256": "b" * 64, "changed": True, "canon": "jcs-rfc8785"})
    recs = insert_after(example_records(), "te0", sc)
    assert run(recs) == []
    assert "aer.schema.required" in run(edit(recs, "st0", canon=None))
    assert "aer.schema.pattern" in run(edit(recs, "st0", before_sha256="xyz"))
    patch = [{"op": "replace", "path": "/a/b", "value": 3}]
    assert run(edit(recs, "st0", patch=patch)) == []
    assert "aer.schema.pattern" in run(edit(recs, "st0", patch=[{"op": "frob", "path": "/a"}]))
    assert "aer.schema.required" in run(edit(recs, "st0", patch=[{"op": "add"}]))
    assert "aer.ref.kind" not in run(edit(recs, "st0", cause="mc0"))  # a model call may be the cause (R-35)
    assert "aer.ref.kind" in run(edit(recs, "st0", cause="m0"))


def test_judgement_origin_closed_list() -> None:
    j = d({"k": "judgement", "id": "j0", "actor": "env", "subject": "run", "name": "utility", "value": None, "origin": "checker"})
    recs = insert_after(example_records(), "m3", j)
    assert run(recs) == []  # value null is asserted, not missing
    for origin in ("harness_default", "harness_rule", "recomputed"):
        assert run(edit(recs, "j0", origin=origin)) == []
    assert "aer.schema.pattern" in run(edit(recs, "j0", origin="guess"))
    assert "aer.schema.additional" in run(edit(recs, "j0", valid=True))
    assert "aer.schema.additional" in run(edit(recs, "j0", meaning="lower_is_better"))
    assert "aer.schema.required" in run(edit(recs, "j0", value=None))  # absent, unlike an asserted null
