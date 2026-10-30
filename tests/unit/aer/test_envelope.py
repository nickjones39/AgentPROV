"""K.5.1 items 1-5 and 12: kinds, closed core fields, the envelope, evidence obligations, header members."""

from __future__ import annotations

import copy
from typing import Any

import pytest
from aer_support import (
    VECTOR_NAMES,
    codes_of,
    edit,
    example_records,
    make_registry,
    validate_example,
    vector_path,
    vector_registry,
)

from agentprov import aer
from agentprov.aer.validate import validate_file


def run(records: list[dict[str, Any]], **kw: Any) -> list[str]:
    return codes_of(validate_example(records, **kw))


def test_the_example_is_valid_and_vectors_are_valid() -> None:
    report = validate_example(example_records())
    assert report.ok, report.findings
    registry = vector_registry()
    for name in VECTOR_NAMES:
        result = validate_file(vector_path(name), store=None, catalogues=registry, mode="release")
        assert result.ok and not result.findings, (name, result.findings)


def test_thirteen_kinds() -> None:
    assert len(aer.RECORD_KINDS) == 13
    assert aer.AER_VERSION == "0.2" and aer.AER_FORMAT_ID == "aer/0.2" and aer.READABLE_VERSIONS == ("0.1", "0.2")
    assert {"activity", "artefact", "seal", "execution"} <= aer.RECORD_KINDS


def test_a_fourteenth_kind_is_aer_schema_kind() -> None:
    recs = edit(example_records(), "m0", k="plan")
    assert "aer.schema.kind" in run(recs)


@pytest.mark.parametrize(
    ("record_id", "member"),
    [("m0", "bogus"), ("agent", "as_sent_of"), ("agent", "transform"), ("mc0", "output"), ("te0", "result"),
     ("te0", "spawns"), ("mc0", "replacement"), ("exec", "adapter_extra"), ("run", "valid"), ("run", "meaning")],
)
def test_unknown_core_members_are_schema_additional(record_id: str, member: str) -> None:
    assert "aer.schema.additional" in run(edit(example_records(), record_id, **{member: 1}))


def test_removed_members_of_resolutions_are_additional() -> None:
    recs = example_records()
    cases = [
        ("exec", {"task": {"benchmark": "tst", "task_id": "t", "benchmark_version": "v1"}}),
        ("exec", {"adapter": {"id": "tst.adapter", "version": "0.1.0", "code_sha256": "0" * 64}}),
        ("te0", {"args_requested": {}}),
        ("te0", {"result_raw": "x"}),
        ("mc0", {"input": [{"base": "mc0", "plus": ["m1"]}]}),
        ("run", {"t": {"clock": "wall"}}),
        ("run", {"t": {"res": 1}}),
        ("m2", {"parts": [{"t": "tool_result", "responds_to": "m1#1", "text": "x", "sha256": "0" * 64}]}),
    ]
    for rid, change in cases:
        found = run(edit(recs, rid, **change))
        assert "aer.schema.additional" in found or "aer.schema.pattern" in found, (rid, change, found)


def test_framework_data_only_under_declared_ext_namespaces() -> None:
    ok = edit(example_records(), "m0", ext={"tst": {"extra": 1}})
    assert run(ok) == []
    assert "aer.ext.undeclared" in run(edit(example_records(), "m0", ext={"zzz": {"extra": 1}}))
    # a reserved prefix cannot be redeclared
    header_ns = {"tst": "https://example.invalid/ns/tst#", "apv": "https://example.invalid/apv#"}
    assert "aer.ext.undeclared" in run(edit(example_records(), "exec", ns=header_ns))


def test_ext_members_may_not_shadow_core_slots() -> None:
    recs = edit(example_records(), "m0", ext={"tst": {"role": "assistant"}})
    assert "aer.ext.shadows_core" in run(recs)
    dev = validate_example(recs, mode="dev")
    assert dev.ok and "aer.ext.shadows_core" in codes_of(dev, errors_only=False)


def test_ev_is_required_and_closed() -> None:
    assert "aer.schema.required" in run(edit(example_records(), "m0", ev=None))
    assert "aer.schema.pattern" in run(edit(example_records(), "m0", ev="X"))


def test_by_is_required_for_a_bare_observed_tag_and_from_the_closed_list() -> None:
    assert "aer.schema.required" in run(edit(example_records(), "m0", by=None))
    assert "aer.schema.pattern" in run(edit(example_records(), "m0", by="someone"))
    # by without any bare O is an error ("present iff")
    assert "aer.schema.additional" in run(edit(example_records(), "agent", by="source"))


def test_observed_records_need_a_locator() -> None:
    assert "aer.schema.required" in run(edit(example_records(), "m0", src=None))
    assert "aer.schema.required" in run(edit(example_records(), "m0", src=[]))
    # O:<party> counts as observed too
    recs = edit(example_records(), "m0", ev="D", rule=["tst.d@1"], evf={"/parts": "O:provider"}, by=None, src=None)
    assert "aer.schema.required" in run(recs)


def test_evf_resolution_is_longest_prefix_and_may_name_party_tags() -> None:
    recs = edit(
        example_records(), "m1",
        evf={"/generated_by": "D", "/parts/1": "O:provider"},
        rule=["tst.d@1#/generated_by"],
    )
    assert run(recs) == []
    # evf pointers must resolve to a present field or a declared unknown
    assert "aer.ref.dangling" in run(edit(example_records(), "m1", evf={"/nothing": "D"}, rule=["tst.d@1"]))
    assert "aer.schema.pattern" in run(edit(example_records(), "m1", evf={"/parts": "O:everyone"}))
    assert "aer.schema.pattern" in run(edit(example_records(), "m1", evf={"parts": "D"}))


def test_every_d_or_i_assertion_needs_an_applicable_rule() -> None:
    assert "aer.rule.missing" in run(edit(example_records(), "agent", rule=None))
    # a scoped rule that does not cover the pointer leaves it uncovered
    recs = edit(example_records(), "te0", rule=["tst.d@1#/name"])
    assert "aer.rule.missing" in run(recs)


def test_rule_references_must_match_the_grammar_and_the_catalogue() -> None:
    assert "aer.schema.pattern" in run(edit(example_records(), "agent", rule=["not a rule"]))
    assert "aer.rule.missing" in run(edit(example_records(), "agent", rule=["tst.unknown@1"]))
    assert "aer.rule.missing" in run(edit(example_records(), "agent", rule=["other.rule@1"]))  # namespace undeclared
    assert "aer.rule.missing" in run(edit(example_records(), "agent", rule=["tst.d@2"]))


def test_class_rules_of_c64() -> None:
    # an I rule applicable to a D pointer
    assert "aer.rule.class" in run(edit(example_records(), "agent", rule=["tst.i@1"]))
    # an I pointer must cite an I-class rule (the stated assumption)
    recs = edit(example_records(), "agent", evf={"/name": "I"}, rule=["tst.d@1"])
    assert "aer.rule.class" in run(recs)
    recs = edit(example_records(), "agent", evf={"/name": "I"}, rule=["tst.d@1", "tst.i@1#/name"])
    assert run(recs) == []
    # a scoped reference on an observed value is an error
    assert "aer.rule.class" in run(edit(example_records(), "m0", rule=["tst.d@1#/role"]))
    # ... but a scoped reference may justify an ambiguous declaration
    ok = edit(example_records(), "m3", parts=[{"t": "text", "text": ""}], unk={"/parts/0/text": "ambiguous"},
              rule=["tst.d@1#/parts/0/text"])
    assert run(ok) == []


def test_applicable_rule_set_prefers_the_most_specific_scope() -> None:
    # I rule scoped at /input, D rule unscoped: /input is I-tagged and covered by the scoped I rule
    recs = edit(example_records(), "mc0", evf={"/input": "I"}, rule=["tst.d@1", "tst.i@1#/input"])
    assert run(recs) == []
    # the D pointer /status falls back to the unscoped D rule, so the I rule scoped elsewhere does not apply to it
    assert "aer.rule.class" not in run(recs)


def test_catalogue_must_be_declared_in_the_header() -> None:
    recs = edit(example_records(), "exec", rules={"aer": 1})
    assert "aer.rule.missing" in run(recs)
    recs = edit(example_records(), "exec", rules={"aer": 1, "tst": 7})
    assert "aer.rule.missing" in run(recs)


def test_header_members() -> None:
    base = example_records()
    assert "aer.schema.required" in run(edit(base, "exec", unit=None))
    assert "aer.schema.pattern" in run(edit(base, "exec", unit="trace"))
    for unit in ("agent_execution", "outcome_only", "scenario"):
        assert run(edit(base, "exec", unit=unit)) == []
    assert "aer.schema.pattern" in run(edit(base, "exec", profile={"id": "p", "version": "1", "sha256": "0" * 64}))
    assert "aer.schema.pattern" in run(edit(base, "exec", rules={"aer": "1", "tst": 1}))
    assert "aer.schema.pattern" in run(edit(base, "exec", aer="0.3"))  # 0.1 and 0.2 are readable (D-212)
    assert "aer.schema.pattern" in run(edit(base, "exec", canon="jcs"))
    assert "aer.schema.required" in run(edit(base, "exec", task=None))
    assert "aer.schema.additional" in run(edit(base, "exec", capture={"session": "x", "log": "a0", "attempt": 0}))


def test_instrumentation_items_have_the_merged_shape() -> None:
    base = example_records()
    good = {"id": "tst.rewrite@1", "kind": "request_modifying", "recorded": "full", "params": {"max": 8}}
    assert run(edit(base, "exec", unk=None, instrumentation=[good], evf={"/instrumentation": "I"},
                    rule=["tst.i@1#/instrumentation"])) == []
    for bad in (
        {**good, "changes_behaviour": True},
        {**good, "kind": "behaviour"},
        {**good, "recorded": "yes"},
        {**good, "id": "tst.rewrite(max=8)@1"},
        {k: v for k, v in good.items() if k != "kind"},
    ):
        recs = edit(base, "exec", unk=None, instrumentation=[bad], evf={"/instrumentation": "I"},
                    rule=["tst.i@1#/instrumentation"])
        assert {"aer.schema.additional", "aer.schema.pattern", "aer.schema.required"} & set(run(recs))


def test_artefact_descriptors_need_role_and_prov_primary() -> None:
    base = example_records()
    art = copy.deepcopy(base[0]["artifacts"][0])
    for role in ("primary", "capture_log", "native_log", "supporting"):
        assert "aer.schema.pattern" not in run(edit(base, "exec", artifacts=[{**art, "role": role}]))
    assert "aer.schema.pattern" in run(edit(base, "exec", artifacts=[{**art, "role": "mirror"}]))
    assert "aer.schema.required" in run(edit(base, "exec", artifacts=[{k: v for k, v in art.items() if k != "prov_primary"}]))
    assert "aer.schema.pattern" in run(edit(base, "exec", artifacts=[{**art, "prov_primary": "maybe"}]))
    member = {"kind": "member", "container": "0" * 64, "label": "samples/1.json", "method": 8, "crc32": "deadbeef", "size": 3}
    assert "aer.schema.pattern" not in run(edit(base, "exec", artifacts=[{**art, "origin": member}]))
    assert "aer.schema.pattern" in run(edit(base, "exec", artifacts=[{**art, "origin": {**member, "method": 9}}]))


def test_local_origin_is_rejected_in_release_mode_only() -> None:
    base = example_records()
    art = {**base[0]["artifacts"][0], "origin": {"kind": "local", "path": "/tmp/x"}}
    assert "aer.schema.pattern" in run(edit(base, "exec", artifacts=[art]))
    dev = validate_example(edit(base, "exec", artifacts=[art]), mode="dev")
    assert dev.ok and "aer.schema.pattern" in codes_of(dev, errors_only=False)


def test_execution_id_is_checked_against_the_source_key() -> None:
    base = example_records()
    assert "aer.id.execution" in run(edit(base, "exec", ex="ex_aaaaaaaaaaaaaaaaaaaaaaaaaa"))
    assert "aer.id.execution" in run(edit(base, "exec", source_key={"sha256": "1" * 64, "loc": {"p": ""}}))
    assert "aer.id.execution" in run(edit(base, "exec", source_key={**base[0]["source_key"], "loc": {"p": "/0"}}))
    # the loc must be in canonical key form
    assert "aer.id.execution" in run(edit(base, "exec", source_key={**base[0]["source_key"], "loc": {"p": "x"}}))
    # a different profile id changes the id
    assert "aer.id.execution" in run(edit(base, "exec", profile={"id": "other", "version": 1, "sha256": "0" * 64}))


def test_each_record_kind_has_a_constructible_example() -> None:
    kinds = {r["k"] for r in example_records()}
    assert kinds >= {"execution", "actor", "scope", "message", "model_call", "tool_execution"}


def test_registry_is_required_for_catalogue_checks() -> None:
    assert make_registry().has("tst", 1)


SESSION = "0190a6e0-1d5c-7a3b-8c4d-123456789abc"


def live_header() -> list[dict[str, Any]]:
    base = example_records()
    art = {**base[0]["artifacts"][0], "role": "capture_log", "origin": {"kind": "capture", "session": SESSION}}
    return edit(
        base, "exec", mode="live", ex="ex_" + SESSION, source_key={"sha256": art["sha256"], "loc": {}}, artifacts=[art],
        capture={"session": SESSION, "log": "a0", "attempt": 0}, unk=None,
        instrumentation=[{"id": "tst.native@1", "kind": "behaviour_preserving", "recorded": "full"}],
        evf={"/instrumentation": "I"}, rule=["tst.i@1#/instrumentation"],
    )


def test_live_headers_need_capture_and_instrumentation_and_a_session_id() -> None:
    assert run(live_header()) == []
    assert "aer.schema.required" in run(edit(live_header(), "exec", capture=None))
    assert "aer.schema.required" in run(edit(live_header(), "exec", instrumentation=None, unk=None, evf=None, rule=None))
    assert "aer.id.execution" in run(edit(live_header(), "exec", ex="ex_" + SESSION.replace("a", "b", 1)))
    assert "aer.id.execution" in run(edit(live_header(), "exec", source_key={**live_header()[0]["source_key"], "loc": {"p": ""}}))
    assert "aer.ref.dangling" in run(edit(live_header(), "exec", capture={"session": SESSION, "log": "a5", "attempt": 0}))
    assert "aer.schema.pattern" in run(edit(live_header(), "exec", capture={"session": "x", "log": "a0", "attempt": 0}))


def test_live_time_may_carry_monotonic_offsets() -> None:
    assert run(edit(live_header(), "run", t={"mono_start_ns": 1, "mono_end_ns": 5})) == []
    assert "aer.order.time" in run(edit(live_header(), "run", t={"mono_start_ns": 9, "mono_end_ns": 5}))


def test_duplicate_and_reserved_ids() -> None:
    recs = example_records()
    assert "aer.id.duplicate" in run([*recs[:3], {**recs[2]}, *recs[3:]])
    for bad in ("exec", "seal", "as", "a0"):
        assert "aer.schema.pattern" in run(edit(recs, "m0", id=bad))
    assert "aer.schema.pattern" in run(edit(recs, "att0", id="run"))  # `run` only for the run scope
    assert "aer.schema.pattern" in run(edit(recs, "run", id="main"))  # the run scope is fixed to `run`


def test_exactly_one_run_scope() -> None:
    recs = [r for r in example_records() if r["id"] not in ("run", "att0", "m0", "mc0", "m1", "te0", "m2", "mc1", "m3")]
    assert "aer.schema.oneof" in run(recs)


def test_verified_assumptions_need_the_recorded_framework_identity() -> None:
    from agentprov.aer.rules import RuleCatalogue, RuleEntry, Verification

    commit = "c" * 40
    verified = RuleEntry(
        "tst.v", 1, "D", "active", "s", assumptions=("apv:LastPassOnlyLogging",),
        verification=(Verification("apv:LastPassOnlyLogging", "verified", ("git:https://example.invalid/r@" + commit,), "c.py", "t.py"),),
    )
    registry = make_registry()
    registry.add(
        RuleCatalogue("tst", 1, "agentprov-rule-catalogue/0.1", frozenset({"odd_thing"}), frozenset({"tst.sub"}),
                      frozenset({"tst:plan"}), {"tst.d@1": RuleEntry("tst.d", 1, "D", "active", "s"),
                                                "tst.i@1": RuleEntry("tst.i", 1, "I", "active", "s"), "tst.v@1": verified})
    )
    from aer_support import seal_record

    from agentprov.aer.validate import validate_records

    def codes(records: list[dict[str, Any]], mode: str = "release") -> list[str]:
        report = validate_records([*records, seal_record(records)], store=None, catalogues=registry, mode=mode)  # type: ignore[arg-type]
        return codes_of(report)

    base = edit(example_records(), "agent", rule=["tst.v@1"])
    assert "aer.rule.class" in codes(base)  # no framework identity recorded
    wrong = edit(base, "agent", code={"commit": "d" * 40})
    assert "aer.rule.class" in codes(wrong)  # a different commit; a version string never verifies
    right = edit(base, "agent", code={"commit": commit})
    assert "aer.rule.class" not in codes(right)
    assert "aer.rule.class" not in codes(base, "dev")  # (R): a warning in dev mode


def test_a_scoped_i_rule_below_a_derived_value_is_refused_without_an_evf_key_f1() -> None:
    """Pre-round review F-1 (#37): C.6.4 holds for a scoped rule's own pointer. ``mc1`` is derived (ev D); an I-class rule
    scoped at ``/input/2`` with no ``evf`` key there would make that D value rest on an I rule, which tier 4 then states as
    a core ``apv:Derived`` used() with an I basis. Before the fix only top-level fields and evf keys were evaluated."""
    recs = edit(example_records(), "mc1", rule=["tst.d@1", "tst.i@1#/input/2"])
    assert "aer.rule.class" in run(recs)
    # the control: with the value tagged I by an evf key, the I rule is the stated assumption and the record is valid
    control = edit(example_records(), "mc1", evf={"/input/2": "I"}, rule=["tst.d@1", "tst.i@1#/input/2"])
    assert run(control) == []
    # a scoped D rule below a derived value stays valid
    assert run(edit(example_records(), "mc1", rule=["tst.d@1", "tst.d2@1#/input/2"])) == []


def test_a_scoped_i_rule_may_justify_an_absent_declared_value_f1() -> None:
    """F-1 stays within C.6.4: a scoped I rule on a pointer that holds no value but an unk declaration (the converted
    adprov actor's ``/model/requested``, declared ambiguous) justifies the declaration, not a derived value."""
    recs = edit(example_records(), "agent", rule=["tst.d@1", "tst.i@1#/model/requested"],
                unk={"/model/requested": "ambiguous"})
    assert "aer.rule.class" not in run(recs)


def test_an_accounting_mirror_without_its_check_is_refused_27() -> None:
    """Pre-round review #27: an ``accounting_<verdict>`` seal issue mirrors a check of that id, scope and verdict
    (C.12.3). Before, the validator (and so the writer) accepted mirrors that no check produced."""
    def mirror_codes(issue: dict) -> list[tuple[str, str]]:
        report = validate_example(example_records(), issues=[issue])
        return [(f.code, f.detail) for f in report.errors if f.code == "aer.seal.accounting"]

    # the check is consistent: nothing to mirror
    assert mirror_codes({"code": "accounting_inconsistent", "ids": ["att0"],
                         "rule": "aer.acc.tool_calls_dispatched@1"}) == [("aer.seal.accounting", "mirror_without_check")]
    # a consistent verdict has no mirror at all
    assert mirror_codes({"code": "accounting_consistent", "ids": ["att0"],
                         "rule": "aer.acc.tool_calls_dispatched@1"}) == [("aer.seal.accounting", "mirror_without_check")]
    # the writer's own mirror of the unverifiable check is valid
    assert validate_example(example_records()).ok
