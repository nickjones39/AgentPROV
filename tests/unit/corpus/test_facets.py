"""Index facets, the generic cell, evidence classes, oracles and completeness (HL H.3.2, H.3.3, H.7.4; D-34).

HL-T18 (generic kinds: facets ``n.activities``, ``n.artefacts``, ``generic_types``) and the row half of HL-T19
(``unit``/``execution_observed``/``completeness`` flags, compat outputs flagged ``apv:RegressionOracle``).
"""

from __future__ import annotations

import base64
import copy
import hashlib
import itertools
import json
from pathlib import Path

import pytest
from facet_support import AER_DIGEST, EX, aer, header, outcome_sem, records, sem

from agentprov.aer.reader import load_aer
from agentprov.corpus import facets as F
from agentprov.corpus.index import CORE_FACET_TYPES, FacetMembers, check_corpus_json, logical_key
from agentprov.io.canonical import jcs_bytes
from agentprov.sem.reader import load_sem

VECTORS = Path(__file__).resolve().parents[3] / "docs" / "architecture" / "examples" / "C"


def b32(data: bytes) -> str:
    return base64.b32encode(data).decode("ascii").lower().rstrip("=")


def expected_fw() -> str:
    core = {"distribution": "foobench", "source": {"commit": "a" * 40, "repo": "https://example.invalid/foo"},
            "source_tree_sha256": None, "suite_set": "v2"}
    return "fw_" + b32(hashlib.sha256(b"aer-fw/1\n" + jcs_bytes(core)).digest())[:16]


# ------------------------------------------------------------------------------------------------ facets (H.3.3)
def test_core_facets_follow_h33_with_sem_polarity():
    facets, ev = F.compute_facets(aer(), {"foo.sem@1": outcome_sem()})
    assert set(facets) == set(CORE_FACET_TYPES)
    assert facets["task"] == {"benchmark": "foobench", "suite": "s1", "task_id": "t1", "attack_id": "a1", "defense_id": None}
    assert facets["framework"] == expected_fw()
    assert facets["model.requested"] == ["m-1"]  # the judge's model is not the agent's
    assert facets["model.served"] == ["m-1-a", "m-1-b"]  # actor /model/served and agent-role calls; not auxiliary
    assert {k: facets[k] for k in F.COUNT_FACETS} == {
        "n.messages": 2, "n.model_calls": 2, "n.tool_executions": 1, "n.decisions": 1, "n.judgements": 2,
        "n.state_changes": 1, "n.activities": 2, "n.artefacts": 1}  # fmt: skip
    assert facets["generic_types"] == ["foo:file", "foo:memory_read", "foo:plan"]
    assert facets["outcome"] == [
        {"name": "score", "value": {"$dec": "0.25"}, "origin": "checker", "claim": "foo.score", "holds": None,
         "score": {"$dec": "0.25"}, "scale": "unit_interval",
         "ev": {"name": "O", "value": "O", "origin": "D", "claim": "I", "score": "I", "scale": "I"}},
        {"name": "refusal", "value": 1, "origin": "checker", "claim": "foo.refusal", "holds": True, "score": None,
         "scale": None, "ev": {"name": "O", "value": "O", "origin": "O", "claim": "D", "holds": "D"}},
    ]  # fmt: skip
    # the weakest class of the inputs: defense_id is I, code.dist is D, an agent-role call is D, one activity is I
    assert ev == {
        "task": "I", "framework": "D", "model.requested": "O", "model.served": "D", "n.messages": "O",
        "n.model_calls": "D", "n.tool_executions": "D", "n.decisions": "O", "n.judgements": "O", "n.state_changes": "O",
        "n.activities": "I", "n.artefacts": "D", "generic_types": "I", "outcome": "I"}  # fmt: skip
    check_corpus_json(facets)  # no float anywhere (H.1.4(3))


def test_without_sem_the_polarity_members_are_null():
    facets, ev = F.compute_facets(aer())
    assert [(o["claim"], o["holds"], o["score"], o["scale"]) for o in facets["outcome"]] == [(None,) * 4] * 2
    assert ev["outcome"] == "D"  # j0's origin is D


def test_hl_t18_generic_kinds_yield_their_facets():
    recs = [r for r in records() if r["k"] not in ("activity", "artefact")]
    facets, ev = F.compute_facets(aer(recs))
    assert facets["n.activities"] == facets["n.artefacts"] == 0 and facets["generic_types"] == []
    assert "n.activities" not in ev and "generic_types" not in ev  # a facet on no field has no class
    facets, _ = F.compute_facets(aer())
    assert (facets["n.activities"], facets["n.artefacts"]) == (2, 1)


def test_sem_must_annotate_this_aer_and_profiles_must_agree():
    with pytest.raises(F.FacetError):
        F.compute_facets(aer(), {"foo.sem@1": sem(aer_digest="00" * 32)})
    other = sem({"target": "j1", "type": "outcome", "ev": "D", "value": {"claim": "foo.refusal", "holds": False}}, profile="bar.sem")
    with pytest.raises(F.FacetError):
        F.compute_facets(aer(), {"foo.sem@1": outcome_sem(), "bar.sem@1": other})
    same = sem({"target": "j1", "type": "outcome", "ev": "D", "value": {"claim": "foo.refusal", "holds": True}}, profile="bar.sem")
    facets, _ = F.compute_facets(aer(), {"foo.sem@1": outcome_sem(), "bar.sem@1": same})
    assert facets["outcome"][1]["holds"] is True


def test_framework_identity_h24():
    identity = F.framework_identity(aer())
    assert identity == {
        "distribution": "foobench", "ev": {"distribution": "D", "reported_version": "O", "source": "O", "suite_set": "O"},
        "fw": expected_fw(), "reported_version": "1.0", "source": {"commit": "a" * 40, "repo": "https://example.invalid/foo"},
        "source_tree_sha256": None, "suite_set": "v2"}  # fmt: skip
    recs = records()
    recs[1] = {**recs[1], "unk": {"/code": "not_recorded", "/version": "not_recorded"}}
    assert F.framework_identity(aer(recs)) is None  # nothing identifies it: no id over nothing
    two = records()
    two.insert(2, {**two[1], "id": "bench2"})
    assert F.framework_identity(aer(two)) is None
    assert F.compute_facets(aer(two))[0]["framework"] is None


# ------------------------------------------------------------------------------------------------ cell (H.7.4)
def expected_cell() -> dict:
    params = "sha256:" + hashlib.sha256(jcs_bytes([{"id": "foo.display@1", "params": {"display_name": "M"}}])).hexdigest()
    return {"benchmark": "foobench", "suite": "s1", "task_id": "t1", "attack_id": "a1", "defense_id": None,
            "suite_set": "v2", "model": "m-1", "attack_params_sha256": params, "repeat": None}


def test_generic_cell_and_logical_key():
    cell, ev = F.compute_cell(aer())
    assert cell == expected_cell()
    assert ev == {"cell.benchmark": "O", "cell.suite": "O", "cell.task_id": "O", "cell.attack_id": "O",
                  "cell.defense_id": "I", "cell.suite_set": "O", "cell.model": "O", "cell.attack_params_sha256": "O"}
    lk = "lk_" + b32(hashlib.sha256(b"aer-lk/1\n" + jcs_bytes(cell)).digest())[:26]
    assert logical_key(cell) == lk and F.facet_members(aer()).logical_key == lk


@pytest.mark.parametrize(
    ("change", "member", "reason"),
    [
        (lambda r: r[0].update(unk={"/task/suite": "withheld"}), "suite", "withheld"),
        (lambda r: r[0]["task"].pop("task_id"), "task_id", "not_recorded"),  # a required member that is absent
        (lambda r: r[1].update(unk={"/version": "lost"}) or r[1].pop("version"), "suite_set", "lost"),
        (lambda r: r[2].update(unk={"/model": "not_recorded"}) or r[2].pop("model"), "model", "not_recorded"),
        (lambda r: r.pop(2), "model", "not_recorded"),  # no agent actor
        (lambda r: r[0]["instrumentation"][0].pop("params"), "attack_params_sha256", "not_recorded"),
        (lambda r: r.insert(2, {**r[1], "id": "bench2"}), "suite_set", "ambiguous"),
    ],
)
def test_an_unknown_cell_member_nulls_the_logical_key(change, member, reason):
    recs = copy.deepcopy(records())
    change(recs)
    members = F.facet_members(aer(recs))
    assert members.cell[member] == {"$unk": reason}
    assert members.logical_key is None and f"cell.{member}" not in members.ev


def test_absent_optional_members_are_not_coordinates():
    recs = records(task={"benchmark": "foobench", "task_id": "t1"}, instrumentation=None)
    recs = [r for r in recs if r.get("kind") != "benchmark"]
    cell, _ = F.compute_cell(aer(recs))
    assert cell == {"benchmark": "foobench", "task_id": "t1", "model": "m-1", "repeat": None}
    assert F.facet_members(aer(recs)).logical_key is not None


def test_several_agents_with_different_models_give_a_sorted_array():
    recs = records()
    recs.insert(3, {"k": "actor", "id": "agent2", "kind": "llm_agent", "ev": "I", "rule": ["tst.i@1"], "model": {"requested": "a-0"}})
    cell, ev = F.compute_cell(aer(recs))
    assert cell["model"] == ["a-0", "m-1"] and ev["cell.model"] == "I"


def test_repeat_is_null_for_imports_and_the_ledger_index_for_live():
    live = records(mode="live")
    assert F.compute_cell(aer(live), repeat=3)[0]["repeat"] == 3
    assert F.compute_cell(aer(live), repeat=3)[1]["cell.repeat"] == "O"
    assert F.compute_cell(aer(live))[0]["repeat"] == {"$unk": "not_recorded"}
    assert F.facet_members(aer(live)).logical_key is None
    assert F.facet_members(aer(live), repeat=0).logical_key != F.facet_members(aer(live), repeat=1).logical_key
    with pytest.raises(F.FacetError):
        F.compute_cell(aer(), repeat=0)
    with pytest.raises(F.FacetError):
        F.compute_cell(aer(live), repeat=-1)


def test_facets_are_a_pure_function_of_the_documents():
    first = F.facet_members(aer(), {"foo.sem@1": outcome_sem()}, prov_specs=["agentprov-prov/0.1"])
    shuffled = records()
    shuffled[0] = dict(reversed(list(shuffled[0].items())))
    second = F.facet_members(aer(shuffled), {"foo.sem@1": outcome_sem()}, prov_specs=["agentprov-prov/0.1"])
    assert jcs_bytes(first.to_json()) == jcs_bytes(second.to_json())


# ------------------------------------------------------------------------------------------------ members, oracles
def test_facet_members_validate_and_flag_regression_oracles():
    members = F.facet_members(aer(), {"foo.sem@1": outcome_sem()}, prov_specs=["agentprov-prov/0.1", "adprov-v2.3-compat"],
                              gate_reports={"adprov-v2.3-compat": "sha256:" + "0" * 64})
    assert isinstance(members, FacetMembers)
    assert members.oracles == {"adprov-v2.3-compat": {"gate_report": "sha256:" + "0" * 64, "status": "apv:RegressionOracle"}}
    assert F.oracles_for(["agentprov-prov/0.1"]) == {}
    assert F.oracles_for(["adprov-v2.3-compat"]) == {"adprov-v2.3-compat": {"gate_report": None, "status": "apv:RegressionOracle"}}
    assert json.loads(jcs_bytes(members.to_json())) == members.to_json()


def test_corpus_value_keeps_non_integral_numbers_exactly_without_floats():
    assert F.corpus_value({"a": [0.1, 2, 1e21, -0.5, True, None]}) == {
        "a": [{"$dec": "0.1"}, 2, {"$dec": "1e+21"}, {"$dec": "-0.5"}, True, None]}
    with pytest.raises(ValueError):
        check_corpus_json({"a": 0.5})
    with pytest.raises(ValueError):
        check_corpus_json({"$dec": "abc"})
    with pytest.raises(ValueError):
        check_corpus_json({"a": 2**53})


def test_core_facet_schema_declares_every_core_facet():
    schema = F.facet_schema()
    assert [d["name"] for d in schema] == list(CORE_FACET_TYPES)
    assert all(d["core"] is True and isinstance(d["from"], str) and set(d) == {"name", "type", "from", "may_be_inferred", "core"}
               for d in schema)
    assert schema[0]["from"] == "/task" and {d["type"] for d in schema} <= {"string", "integer", "boolean", "string[]", "object", "object[]"}
    schema[0]["name"] = "changed"
    assert F.facet_schema()[0]["name"] == "task"  # a copy


def test_spec_vectors_give_facets():
    """The four C.16 vectors (verified AERs) and the C.14.5 SEM document."""
    results = {}
    for name in ("agentdojo_2024_pi_detector", "adprov_v1_llama_injecagent", "stac_case_223", "rope_denial_qwen_autodojo"):
        document = load_aer(VECTORS / f"{name}.aer.jsonl")
        sem_docs = {"agentdojo.suites@1": load_sem(VECTORS / f"{name}.sem.jsonl")} if name.startswith("adprov") else {}
        results[name] = F.facet_members(document, sem_docs)
    adprov = results["adprov_v1_llama_injecagent"]
    assert [(o["name"], o["claim"], o["holds"]) for o in adprov.facets["outcome"]] == [
        ("utility", "user_task_solved", False), ("security", "attack_succeeded", True)]
    # adprov v1 declares an attack parameter (the display name) without recording it: the cell is not determined
    assert adprov.cell["attack_params_sha256"] == {"$unk": "not_recorded"} and adprov.logical_key is None
    assert results["stac_case_223"].cell["model"] == {"$unk": "not_recorded"}
    rope = results["rope_denial_qwen_autodojo"]
    assert rope.logical_key is not None and rope.cell["defense_id"] == "rope" and rope.facets["framework"].startswith("fw_")


# ------------------------------------------------------------------------------------------------ completeness (B2)
def test_completeness_equals_the_importers_rule():
    from agentprov.adapters.runner import importer

    assert F.DEGENERATE_CODES == importer._DEGENERATE_CODES and F.LOSS_CODES == importer._LOSS_CODES
    codes = ["incomplete_run", "retry_passes_inferred", "aborted_attempt", "missing_tool_result", "accounting_unverifiable",
             "no_execution_observed",
             "adapter_defect", "validate.failed"]
    seal_sets = [frozenset(), *(frozenset({c}) for c in codes), frozenset(codes[:2]), frozenset(codes[3:5])]
    for degenerate, accounting, checks, unit, seal_codes in itertools.product(
        (False, True), ("consistent", "inconsistent", "unverifiable", ""), (0, 1, 4),
        ("agent_execution", "outcome_only", "scenario"), seal_sets,
    ):
        args = dict(degenerate=degenerate, accounting=accounting, checks_evaluated=checks, unit_kind=unit, seal_codes=seal_codes)
        assert F.index_completeness(**args) == importer.index_completeness(**args), args


def test_completeness_is_read_from_the_seal():
    one_check = [{"id": "aer.acc.x@1", "scope": "run", "verdict": "consistent", "observed": {}}]
    assert F.completeness_of(aer(accounting={"status": "consistent", "checks": one_check})) == "verified_complete"
    assert F.completeness_of(aer(accounting={"status": "consistent", "checks": []})) == "unverifiable"  # vacuous
    assert F.completeness_of(aer(accounting={"status": "inconsistent", "checks": one_check})) == "known_incomplete"
    loss = [{"code": "incomplete_run", "ids": ["run"], "rule": "tst.d@1"}]
    assert F.completeness_of(aer(issues=loss, accounting={"status": "consistent", "checks": one_check})) == "known_incomplete"
    degenerate = [{"code": "unparseable_artefact", "ids": ["run"], "rule": "tst.d@1"}]
    assert F.completeness_of(aer(issues=degenerate, accounting={"status": "inconsistent", "checks": one_check})) == "unverifiable"
    outcome_only = records(unit="outcome_only")
    assert F.completeness_of(aer(outcome_only, accounting={"status": "consistent", "checks": one_check})) == "unverifiable"


def test_completeness_counts_only_a_loss_a_class_d_rule_proves():
    """D-372: derive and recompute apply the importer's D-24/B6 reading (an inferred retry is unverifiable)."""
    from agentprov.adapters.runner import importer

    one_check = [{"id": "aer.acc.x@1", "scope": "run", "verdict": "consistent", "observed": {}}]
    acc = {"status": "consistent", "checks": one_check}
    d_retry = [{"code": "retry_passes_inferred", "ids": ["run"], "rule": "agentdojo.null_final_implies_three_passes@1"}]
    i_retry = [{"code": "retry_passes_inferred", "ids": ["run"],
                "rule": "agentdojo.null_final_implies_three_passes_unverified@1"}]
    assert F.completeness_of(aer(issues=d_retry, accounting=acc)) == "known_incomplete"
    assert F.completeness_of(aer(issues=i_retry, accounting=acc)) == "verified_complete"
    assert importer.proven_loss_codes(i_retry) == F.proven_loss_codes(i_retry, importer.rule_class) == frozenset()
    assert importer.proven_loss_codes(d_retry) == frozenset({"retry_passes_inferred"})


def test_missing_tool_result_is_a_loss_unless_the_result_is_kept():
    """Item 11 (E2-b2): a declared missing result proves loss; a declared removal whose execution generated an
    artefact (item 16's react submit) does not."""
    one_check = [{"id": "aer.acc.x@1", "scope": "run", "verdict": "consistent", "observed": {}}]
    acc = {"status": "consistent", "checks": one_check}
    missing = [{"code": "missing_tool_result", "ids": ["te0"], "rule": "inspect.tool_event_is_execution@1"}]
    assert F.completeness_of(aer(issues=missing, accounting=acc)) == "known_incomplete"
    removed = [{"code": "missing_tool_result", "ids": ["te0"], "rule": "inspect.react_submit_message_removed@1"}]
    kept = [*records(), {"k": "artefact", "id": "af0", "type": "inspect:tool_result", "generated_by": "te0", "ev": "O",
                         "by": "source"}]
    assert F.completeness_of(aer(kept, issues=removed, accounting=acc)) == "verified_complete"
    assert F.completeness_of(aer(issues=removed, accounting=acc)) == "known_incomplete"  # no artefact: lost


def test_support_documents_are_consistent():
    assert aer().ex == EX and aer().execution_digest == AER_DIGEST and header()["ex"] == EX
