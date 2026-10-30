"""K.5.1 item 7 (Addendum B, AD-15): the generic ``activity`` and ``artefact`` kinds."""

from __future__ import annotations

from typing import Any

import pytest
from aer_support import codes_of, edit, example_records, insert_after, validate_example

from agentprov.aer.ids import LOCAL_ID_PREFIXES, LOCAL_ID_RE

BLOB = {"$blob": "sha256:" + "a" * 64, "bytes": 67, "media": "image/png"}


def run(records: list[dict[str, Any]], **kw: Any) -> list[str]:
    return codes_of(validate_example(records, **kw))


def activity(**kw: Any) -> dict[str, Any]:
    rec = {"k": "activity", "id": "ac0", "ev": "D", "rule": ["tst.d@1"], "type": "tst:plan", "actor": "agent", "scope": "att0",
           "inputs": ["m0"], "status": "ok", "label": "plan"}
    rec.update(kw)
    return rec


def artefact(**kw: Any) -> dict[str, Any]:
    rec = {"k": "artefact", "id": "af0", "ev": "D", "rule": ["tst.d@1"], "type": "tst:note", "content": {"steps": ["a"]},
           "generated_by": "ac0", "media": "application/json"}
    rec.update(kw)
    return rec


def build(*extra: dict[str, Any]) -> list[dict[str, Any]]:
    recs = example_records()
    anchor = "m0"
    for rec in extra:
        recs = insert_after(recs, anchor, rec)
        anchor = rec["id"]
    return recs


def test_activity_and_artefact_are_valid_with_declared_namespace_and_types() -> None:
    assert run(build(activity(), artefact())) == []


def test_undeclared_namespace_is_ext_undeclared_and_malformed_type_is_pattern() -> None:
    assert "aer.ext.undeclared" in run(build(activity(type="foo:plan")))
    assert "aer.ext.undeclared" in run(build(activity(type="aer:plan")))  # reserved prefix
    assert "aer.schema.pattern" in run(build(activity(type="plan")))
    assert "aer.schema.pattern" in run(build(activity(type="tst.plan")))
    assert "aer.subtype.undeclared" in run(build(activity(type="tst:undeclared")))


@pytest.mark.parametrize("name", ["message", "model_call", "tool_execution", "decision", "state_change", "fixture", "judgement"])
def test_specialised_kinds_come_first(name: str) -> None:
    assert "aer.activity.shadows_kind" in run(build(activity(type=f"tst:{name}")))


def test_artefact_has_exactly_one_of_content_content_ref_or_unk() -> None:
    both = artefact(content_ref=BLOB, sha256="a" * 64)
    assert "aer.schema.oneof" in run(build(activity(), both), with_store=False)
    neither = {k: v for k, v in artefact().items() if k != "content"}
    assert "aer.schema.oneof" in run(build(activity(), neither))
    unknown = {**neither, "unk": {"/content": "withheld"}}
    assert "aer.schema.oneof" not in run(build(activity(), unknown))
    as_blob = {**neither, "content_ref": BLOB, "sha256": "a" * 64}
    assert "aer.schema.oneof" not in run(build(activity(), as_blob), with_store=False)


def test_artefact_sha256_must_equal_the_content_ref_digest() -> None:
    bad = {**{k: v for k, v in artefact().items() if k != "content"}, "content_ref": BLOB, "sha256": "b" * 64}
    assert "aer.blob.digest" in run(build(activity(), bad), with_store=False)


def test_generated_by_and_inputs_are_kind_checked() -> None:
    assert "aer.ref.kind" in run(build(activity(), artefact(generated_by="m0")))
    for target in ("mc0", "te0"):
        recs = example_records()
        recs = insert_after(recs, "m3", artefact(generated_by=target))
        assert "aer.ref.kind" not in run(recs), target
    # an activity input that is an activity (or any non-entity-like record) is ref.kind (a `used` object is never an activity)
    assert "aer.ref.kind" in run(build(activity(), activity(id="ac1", inputs=["ac0"])))
    assert "aer.ref.kind" in run(build(activity(inputs=["agent"])))
    assert "aer.ref.kind" in run(insert_after(example_records(), "m2", activity(inputs=["te0"])))
    ok = build(activity(), artefact(), activity(id="ac1", type="tst:memory_read", inputs=["af0"], evf={"/inputs/0": "D"},
                                                 rule=["tst.d@1", "tst.d2@1#/inputs/0"]))
    assert run(ok) == []


def test_input_links_are_tagged_per_item() -> None:
    recs = build(activity(ev="O", by="source", src=[{"a": "a0", "p": "/messages/0"}], rule=None, inputs=["m0"],
                          evf={"/inputs/0": "D"}))
    assert "aer.rule.missing" in run(recs)
    fixed = build(activity(ev="O", by="source", src=[{"a": "a0", "p": "/messages/0"}], rule=["tst.d@1#/inputs/0"], inputs=["m0"],
                           evf={"/inputs/0": "D"}))
    assert run(fixed) == []


def test_artefact_and_header_artefact_ids_cannot_collide() -> None:
    assert LOCAL_ID_PREFIXES["activity"] == "ac" and LOCAL_ID_PREFIXES["artefact"] == "af"
    for rid in (f"{LOCAL_ID_PREFIXES['artefact']}0", f"{LOCAL_ID_PREFIXES['activity']}7"):
        assert LOCAL_ID_RE.fullmatch(rid)
    assert not LOCAL_ID_RE.fullmatch("a0")  # the header's raw-artefact id grammar
    assert "aer.schema.pattern" in run(build(activity(), artefact(id="a0")))
    assert "aer.schema.pattern" in run(build(activity(), artefact(id="m9")))  # prefix of the kind is fixed
    assert "aer.schema.pattern" in run(build(activity(id="af0")))


def test_artefact_has_no_actor_and_activity_status_is_closed() -> None:
    assert "aer.schema.additional" in run(build(activity(), artefact(actor="agent")))
    assert "aer.schema.pattern" in run(build(activity(status="limit")))
    for status in ("ok", "error", "aborted"):
        assert run(build(activity(status=status))) == []


def test_outputs_of_an_activity_are_artefacts_that_name_it_later() -> None:
    forward = insert_after(example_records(), "m0", artefact(generated_by="ac0"))
    forward = insert_after(forward, "af0", activity())
    assert "aer.ref.forward" in run(forward)


def test_other_kinds_are_not_replaced_by_the_generic_ones() -> None:
    assert "aer.schema.additional" in run(edit(example_records(), "m0", type="tst:plan"))
