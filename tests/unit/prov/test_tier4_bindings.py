"""D-621: tier 4 binds unidentified relations, the capture-profile exemption and source pointers to what justifies them
(pre-round review ``def-review.md`` E-1..E-3, #20-#22; the review's probes, on the engine's generic derivation).

- E-1 (E.5.1 item 3): a ``specializationOf`` or ``alternateOf`` forged into the core, a top-level ``alternateOf``, a
  missing ``aprov.t_spec@1`` ``specializationOf`` and a forged top-level one each fail ``pv.prov_structure.relations``.
- E-2 (E.10): an Observed message or artefact that claims ``aprov.n_capture_profile@1`` and drops its pointers fails
  (``pv.linkage.pointer_missing`` and ``pv.profiles.rule_section``); ``x:capture-profile`` itself still passes.
- E-3 (E.10 item 11, K.10): ``x:m0`` citing ``m1``, and a generation citing another generation's field, fail
  ``pv.linkage.pointer_unbound``.
Each case passed tier 4 at c4d7b785 (the integration head the fix starts from). The underived document passes.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import prov_support as ps  # noqa: E402

from agentprov.ingest.loaders import strict_json_loads  # noqa: E402
from agentprov.io.canonical import jcs_bytes  # noqa: E402
from agentprov.prov.engine import derive  # noqa: E402
from agentprov.validate.prov import validate_prov  # noqa: E402


@pytest.fixture(scope="module")
def generic(tmp_path_factory: pytest.TempPathFactory) -> tuple[Any, Any, dict[str, Any]]:
    aer = ps.write_aer(ps.generic_records(), tmp_path_factory.mktemp("bindings") / "g.aer.jsonl")
    registry = ps.registry()
    return aer, registry, strict_json_loads(derive(aer, registry=registry).prov_json)


def failures(generic: tuple[Any, Any, dict[str, Any]], doc: dict[str, Any]) -> dict[str, set[str]]:
    aer, registry, _ = generic
    report = validate_prov(jcs_bytes(doc), aer, registry=registry)
    assert report.passed == (not report.failed())
    return {o.id: o.codes() for o in report.failed()}


def core_of(doc: dict[str, Any]) -> str:
    return next(k for k in doc["bundle"] if ".core." in k)


def test_the_derived_document_passes(generic):
    assert failures(generic, generic[2]) == {}


# ------------------------------------------------------------------------------------------------ E-1
@pytest.mark.parametrize("section,args", [
    ("specializationOf", lambda a, b: {"prov:specificEntity": a, "prov:generalEntity": b}),
    ("alternateOf", lambda a, b: {"prov:alternate1": a, "prov:alternate2": b}),
])
def test_an_unidentified_relation_forged_into_the_core_fails(generic, section, args):
    doc = copy.deepcopy(generic[2])
    core = core_of(doc)
    a, b = sorted(doc["bundle"][core]["entity"])[:2]
    doc["bundle"][core].setdefault(section, {})["_:forged.aaaaaaaaaaaaaaaa"] = args(a, b)
    assert failures(generic, doc) == {"pv.prov_structure.relations": {"pv.prov_structure.unidentified_placement"}}


def test_a_top_level_alternate_of_fails(generic):
    doc = copy.deepcopy(generic[2])
    a, b = sorted(doc["entity"])[:2]
    doc["alternateOf"] = {"_:forged.aaaaaaaaaaaaaaaa": {"prov:alternate1": a, "prov:alternate2": b}}
    assert failures(generic, doc) == {"pv.prov_structure.relations": {"pv.prov_structure.unidentified_placement"}}


def test_a_missing_t_spec_fails(generic):
    doc = copy.deepcopy(generic[2])
    del doc["specializationOf"]
    assert failures(generic, doc) == {"pv.prov_structure.relations": {"pv.prov_structure.unidentified_placement"}}


def test_a_forged_top_level_specialization_fails(generic):
    doc = copy.deepcopy(generic[2])
    raw = next(k for k in sorted(doc["entity"]) if k.startswith("raw:"))
    doc["specializationOf"]["_:t_spec.aaaaaaaaaaaaaaaa"] = {"prov:specificEntity": "xd:provenance",
                                                            "prov:generalEntity": raw}
    assert failures(generic, doc) == {"pv.prov_structure.relations": {"pv.prov_structure.unidentified_placement"}}


def test_a_mention_in_the_core_fails(generic):
    doc = copy.deepcopy(generic[2])
    core = core_of(doc)
    doc["bundle"][core]["mentionOf"] = {"_:forged.aaaaaaaaaaaaaaaa": {
        "prov:specificEntity": "x:m0", "prov:generalEntity": "x:m1", "prov:bundle": core}}
    assert "pv.prov_structure.unidentified_placement" in failures(generic, doc)["pv.prov_structure.relations"]


# ------------------------------------------------------------------------------------------------ E-2
@pytest.mark.parametrize("key", ["x:m0", "x:af0"])
def test_claiming_the_capture_profile_rule_does_not_exempt_a_node(generic, key):
    doc = copy.deepcopy(generic[2])
    body = doc["bundle"][core_of(doc)]["entity"][key]
    body["apv:rule"] = "aprov.n_capture_profile@1"
    for attr in ("apv:sourcePointer", "apv:basisRule", "apv:rulePointer"):
        body.pop(attr, None)
    found = failures(generic, doc)
    assert "pv.linkage.pointer_missing" in found["pv.linkage.source_pointer"]
    assert found["pv.profiles.rule_section"] == {"pv.profiles.rule_section"}


def test_the_capture_profile_keeps_its_exemption(generic):
    body = generic[2]["bundle"][core_of(generic[2])]["entity"]["x:capture-profile"]
    assert body["apv:rule"] == "aprov.n_capture_profile@1" and "apv:sourcePointer" not in body


# ------------------------------------------------------------------------------------------------ E-3
def test_a_node_citing_another_record_fails(generic):
    doc = copy.deepcopy(generic[2])
    doc["bundle"][core_of(doc)]["entity"]["x:m0"]["apv:sourcePointer"] = "m1"
    assert failures(generic, doc) == {"pv.linkage.source_pointer": {"pv.linkage.pointer_unbound"}}


def test_a_generation_citing_another_generation_fails(generic):
    doc = copy.deepcopy(generic[2])
    gens = sorted(doc["bundle"][core_of(doc)]["wasGeneratedBy"].items())
    (k1, v1), (_, v2) = next((a, b) for a, b in zip(gens, gens[1:], strict=False)
                             if a[1]["apv:rule"] == b[1]["apv:rule"] == "aprov.g_gen@1")
    assert v1["apv:sourcePointer"] != v2["apv:sourcePointer"]
    doc["bundle"][core_of(doc)]["wasGeneratedBy"][k1]["apv:sourcePointer"] = v2["apv:sourcePointer"]
    assert failures(generic, doc) == {"pv.linkage.source_pointer": {"pv.linkage.pointer_unbound"}}


@pytest.mark.parametrize("rule,section", [("aprov.assoc_tool@1", "actedOnBehalfOf"), ("aprov.decision@1", "used"),
                                          ("aprov.gen_result@1", "wasGeneratedBy"), ("aprov.n_model@1", "entity"),
                                          ("aprov.n_part@1", "entity")])
def test_a_linked_rule_binds_no_record_outside_its_premise_links(generic, rule, section):
    """V-3 (pre-round verification): a linked rule's statement citing only a record that is neither one of its anchors
    nor reached through the rule's premise links (scope, run and actor records included) fails; at c4d7b785..8af8adc3
    one-hop links accepted 17/27 (assoc_tool), 12/29 (decision, n_model), 7/29 (gen_result) and 4/29 (n_part)."""
    from agentprov.validate import linkage
    from agentprov.validate._provdoc import ProvView

    aer, registry, base = generic
    iri, key = next((i, k) for i, b in base["bundle"].items() for k, v in b.get(section, {}).items()
                    if v.get("apv:rule") == rule and "apv:sourcePointer" in v)
    view = ProvView.parse(base)
    anchors = linkage._anchors(view, next(s for s in view.bundles[iri].statements if s.key == key))
    accepted = []
    for rid in [r["id"] for r in aer.records if isinstance(r.get("id"), str)]:
        doc = copy.deepcopy(base)
        doc["bundle"][iri][section][key]["apv:sourcePointer"] = rid
        report = validate_prov(jcs_bytes(doc), aer, registry=registry, roundtrip=False)
        if "pv.linkage.pointer_unbound" not in report.get("pv.linkage.source_pointer").codes():
            accepted.append(rid)
    assert accepted and set(accepted) <= anchors


# ------------------------------------------------------------------------------------------------ #16 (engine)
@pytest.mark.parametrize("rid,ptr,activity,entity", [("mc1", "/input/2", "x:mc1", "x:m2"),
                                                     ("ac0", "/inputs/0", "x:ac0", "x:m1")])
def test_an_unknown_input_item_fires_no_usage(tmp_path, rid, ptr, activity, entity):
    """#16 (E.1.5 item 1): an item declared unk gets its gap and no ``used``; the derivation passes tier 4."""
    records = ps.generic_records()
    next(r for r in records if r.get("id") == rid)["unk"] = {ptr: "ambiguous"}
    aer = ps.write_aer(records, tmp_path / "unk.aer.jsonl")
    registry = ps.registry()
    assert ps.check_valid(aer, registry) == []
    result = derive(aer, registry=registry)
    used = [k for b in result.document["bundle"].values() for k, v in b.get("used", {}).items()
            if v.get("prov:activity") == activity and v.get("prov:entity") == entity]
    assert used == []
    assert validate_prov(result.prov_json, aer, registry=registry).passed


# ------------------------------------------------------------------------------------------------ #23
@pytest.mark.parametrize("key", ["x:exec.gap-0", "x:capture-profile", "x:agent.model"])
def test_a_class_above_its_rule_ceiling_fails(generic, key):
    doc = copy.deepcopy(generic[2])
    doc["bundle"][core_of(doc)]["entity"][key]["apv:evidenceClass"] = {"$": "apv:Observed", "type": "prov:QUALIFIED_NAME"}
    assert "pv.linkage.ceiling" in failures(generic, doc)["pv.linkage.existence"]


# ------------------------------------------------------------------------------------------------ #24, #25 (views)
Q = {"type": "prov:QUALIFIED_NAME"}
INF = "xd:bundle.inf.t-i-v1." + "a" * 26
ASS = "xd:bundle.assess.p-v1." + "a" * 26
CORE = "xd:bundle.core." + "a" * 26


def _view(inf: dict[str, Any], ass: dict[str, Any]) -> Any:
    from agentprov.validate._provdoc import ProvView

    return ProvView.parse({
        "prefix": {"x": "urn:x#", "xd": "urn:xd#", "apv": "urn:apv#"},
        "entity": {INF: {"prov:type": [{**Q, "$": "prov:Bundle"}, {**Q, "$": "apv:InferenceBundle"}], "apv:method": "t.i@1"},
                   ASS: {"prov:type": [{**Q, "$": "prov:Bundle"}, {**Q, "$": "apv:AssessmentBundle"}], "apv:profile": "p@1"},
                   CORE: {"prov:type": [{**Q, "$": "prov:Bundle"}, {**Q, "$": "apv:CoreBundle"}]}},
        "bundle": {CORE: {"entity": {"x:e": {}}}, INF: inf, ASS: ass},
    })


def test_an_inference_statement_resting_on_an_assessment_fails():
    """#24: policy claims stay in their assessment bundle (invariant 2); the routing-scope check covers them."""
    from agentprov.validate import linkage

    view = _view({"wasGeneratedBy": {"x:gen.aaaaaaaaaaaaaaaa": {"prov:entity": "x:e",
                                                                "apv:premise": {**Q, "$": "x:as-aaaaaaaaaaaaaaaa"}}}},
                 {"entity": {"x:as-aaaaaaaaaaaaaaaa": {}}})
    assert {f.code for f in linkage._premises(view)} == {"pv.linkage.premise_scope"}


def test_a_reflexive_mention_fails():
    """#25: mentionOf is a specialization, so mentionOf(e, e, b) breaks Constraint 52."""
    from agentprov.validate import constraints

    view = _view({"entity": {"x:e.mn-aaaaaaaaaaaa": {}},
                  "mentionOf": {"_:m.aaaaaaaaaaaaaaaa": {"prov:specificEntity": "x:e.mn-aaaaaaaaaaaa",
                                                         "prov:generalEntity": "x:e.mn-aaaaaaaaaaaa", "prov:bundle": INF}}},
                 {})
    outcomes, _ = constraints.check(view)
    assert "pv.constraints.specialization_reflexive" in {f.code for o in outcomes for f in o.findings}


# ------------------------------------------------------------------------------------------------ #26
def test_a_document_validated_against_another_aer_fails(generic, tmp_path):
    aer, registry, doc = generic
    records = ps.generic_records()
    m0 = next(r for r in records if r.get("id") == "m0")
    m0["parts"][0]["text"] = "a different user message"
    other = ps.write_aer(records, tmp_path / "other.aer.jsonl")
    report = validate_prov(jcs_bytes(doc), other, registry=registry)
    assert {o.id: o.codes() for o in report.failed()} == {"pv.linkage.aer_binding": {"pv.linkage.aer_binding"}}


# ------------------------------------------------------------------------------------------------ #15, #18 (engine)
def test_an_unknown_generator_is_not_an_absent_one(tmp_path):
    """#15 (user decision 2026-10-22): attr_message needs /generated_by absent; an unk one does not fire it."""
    records = ps.generic_records()
    m5 = next(r for r in records if r.get("id") == "m5")
    del m5["generated_by"]
    m5["unk"] = {"/generated_by": "not_recorded"}
    aer = ps.write_aer(records, tmp_path / "unk.aer.jsonl")
    registry = ps.registry()
    assert ps.check_valid(aer, registry) == []
    result = derive(aer, registry=registry)
    attributed = [k for b in result.document["bundle"].values() for k, v in b.get("wasAttributedTo", {}).items()
                  if v.get("prov:entity") == "x:m5"]
    assert attributed == []
    assert validate_prov(result.prov_json, aer, registry=registry).passed


TWIN_VALUES = {"role": ("primary", "supporting"), "prov_primary": ("native", "secondary")}


@pytest.mark.parametrize("field,prop", [("role", "apv:artefactRole"), ("prov_primary", "apv:provPrimary")])
def test_identical_header_artifacts_share_one_raw_entity(tmp_path, field, prop):
    """#18 (user decision 2026-10-22): one raw entity per digest, per-artifact attributes multi-valued and sorted.
    V-2: twins that differ in ``prov_primary`` (native and secondary) pass PV-NE-20, the raw entity is a primary source,
    and a stated value set that differs from the twins' fails it."""
    records = ps.generic_records()
    header = records[0]
    first, second = TWIN_VALUES[field]
    header["artifacts"][0][field] = first
    twin = copy.deepcopy(header["artifacts"][0])
    twin["id"] = "a1"
    twin[field] = second
    header["artifacts"].append(twin)
    aer = ps.write_aer(records, tmp_path / "dup.aer.jsonl")
    registry = ps.registry()
    assert ps.check_valid(aer, registry) == []
    result = derive(aer, registry=registry)
    raw = f"raw:sha256-{twin['sha256']}"
    assert [k for k in result.document["entity"] if k.startswith("raw:")] == [raw]
    assert result.document["entity"][raw][prop] == sorted([first, second])
    assert validate_prov(result.prov_json, aer, registry=registry).passed
    primary = [v for v in result.document.get("wasDerivedFrom", {}).values()
               if v.get("prov:usedEntity") == raw and "prov:type" in v]
    assert primary  # hadPrimarySource: one of the twins is native
    if field == "prov_primary":
        doc = strict_json_loads(result.prov_json)
        doc["entity"][raw][prop] = "secondary"
        report = validate_prov(jcs_bytes(doc), aer, registry=registry, roundtrip=False)
        assert "pv.profiles.primary_source" in {f.code for o in report.failed() for f in o.findings}


# ------------------------------------------------------------------------------------------------ #17 (engine, catalogue v2)
def test_messages_carry_their_scope_under_n_message_2(generic):
    """#17 (user decision 2026-10-22; E.1.3, E.1.4): a message node states its /scope (apv:partOf a non-thread scope,
    apv:thread a thread) under aprov.n_message@2, which supersedes @1 (D-31 owner ruling 2026-10-22)."""
    entities = generic[2]["bundle"][core_of(generic[2])]["entity"]
    messages = {k: v for k, v in entities.items() if str(v.get("apv:rule", "")).startswith("aprov.n_message")}
    assert messages and {v["apv:rule"] for v in messages.values()} == {"aprov.n_message@2"}
    assert all("apv:partOf" in v or "apv:thread" in v for v in messages.values())


def test_the_aprov_v1_and_v2_catalogues_are_archived_byte_exact():
    """D-31: stored corpora record aprov v1 (79b0a1e7...) or v2 (99b6511a..., the round-1 seal and wave 2); the archives
    keep both verifiable after the v3 bump (D-930)."""
    from agentprov.corpus.authority import _catalogue_digest, prov_catalogue_version
    from agentprov.prov.specs import archived_catalogue_sha256, load_spec

    v1 = "79b0a1e78dc7d9c057c7918792dc13ec32e330a070e34696a7875dedb39c6442"
    v2 = "99b6511a2d5e05072c02d5cd5ceb883a20d94a3f3621b03755761fb1d99dbe73"
    assert archived_catalogue_sha256(1) == v1 == _catalogue_digest("aprov", 1)
    assert archived_catalogue_sha256(2) == v2 == _catalogue_digest("aprov", 2)
    assert prov_catalogue_version({"rules_sha256": f"sha256:{v2}"}) == 2
    spec = load_spec()
    assert spec.catalogue_version == 3 and _catalogue_digest("aprov", 3) == spec.catalogue_sha256 not in (v1, v2)
    assert {"aprov.n_message@1", "aprov.n_message@2"} <= set(spec.rules)
    assert {f"aprov.{r}@{n}" for r in ("a_label", "a_payload", "a_author") for n in (1, 2)} <= set(spec.rules)


# ------------------------------------------------------------------------------------------------ V-6: #15, #24 branches
@pytest.mark.parametrize("cited_by", ["te0", "env"])
@pytest.mark.parametrize("authorised", ["absent", "unk"])
def test_an_unknown_authorisation_fires_no_auto_execution(tmp_path, authorised, cited_by):
    """#15 (start_tool half): with AutoExecution cited (by the execution or by its runtime actor), an absent
    /authorised_by fires start_tool and the AutoExecution delegation; an unk one fires neither. Both pass tier 4 (the
    runtime's citation binds through the start_tool link, V-3)."""
    records = ps.generic_records()
    te0 = next(r for r in records if r.get("id") == "te0")
    del te0["authorised_by"]
    if authorised == "unk":
        te0["unk"] = {"/authorised_by": "not_recorded"}
    citing = next(r for r in records if r.get("id") == cited_by)
    citing["rule"] = [*citing.get("rule", []), "tst.auto@1"]
    aer = ps.write_aer(records, tmp_path / "auth.aer.jsonl")
    registry = ps.registry()
    assert ps.check_valid(aer, registry) == []
    result = derive(aer, registry=registry)
    fired = sorted((sec, v["apv:rule"]) for b in result.document["bundle"].values()
                   for sec in ("wasStartedBy", "actedOnBehalfOf") for v in b.get(sec, {}).values()
                   if v.get("prov:activity") == "x:te0")
    assert fired == ([] if authorised == "unk" else
                     [("actedOnBehalfOf", "aprov.assoc_tool@1"), ("wasStartedBy", "aprov.start_tool@1")])
    assert validate_prov(result.prov_json, aer, registry=registry).passed


@pytest.mark.parametrize("generator", ["absent", "unk"])
def test_an_unknown_generator_names_no_requester(tmp_path, generator):
    """#15 (requester half): the request message's /actor is the requester only when its /generated_by is absent; an
    unk one names none, so the authorised execution gets no delegation."""
    records = ps.generic_records()
    m1 = next(r for r in records if r.get("id") == "m1")
    del m1["generated_by"]
    if generator == "unk":
        m1["unk"] = {**m1.get("unk", {}), "/generated_by": "not_recorded"}
    aer = ps.write_aer(records, tmp_path / "req.aer.jsonl")
    registry = ps.registry()
    assert ps.check_valid(aer, registry) == []
    result = derive(aer, registry=registry)
    delegations = [v for b in result.document["bundle"].values() for v in b.get("actedOnBehalfOf", {}).values()
                   if v.get("prov:activity") == "x:te0"]
    assert [v["prov:responsible"] for v in delegations] == ([] if generator == "unk" else ["x:agent"])
    assert validate_prov(result.prov_json, aer, registry=registry).passed


AS2 = "xd:bundle.assess.q-v1." + "b" * 26


@pytest.mark.parametrize("premise,breach", [("x:as-bbbbbbbbbbbbbbbb", True), ("x:o", True), ("x:e", False),
                                            ("x:e.mn-aaaaaaaaaaaa", False), ("x:as-cccccccccccccccc", False)])
def test_an_assessment_statement_rests_on_the_core_inference_and_its_own_bundle_only(premise, breach):
    """#24 (assessment half): another assessment bundle and a bundle of unknown kind are out of an assessment
    statement's scope; the core, an inference bundle and its own bundle are in it."""
    from agentprov.validate import linkage
    from agentprov.validate._provdoc import ProvView

    view = ProvView.parse({
        "prefix": {"x": "urn:x#", "xd": "urn:xd#", "apv": "urn:apv#"},
        "entity": {INF: {"prov:type": [{**Q, "$": "prov:Bundle"}, {**Q, "$": "apv:InferenceBundle"}], "apv:method": "t.i@1"},
                   ASS: {"prov:type": [{**Q, "$": "prov:Bundle"}, {**Q, "$": "apv:AssessmentBundle"}], "apv:profile": "p@1"},
                   AS2: {"prov:type": [{**Q, "$": "prov:Bundle"}, {**Q, "$": "apv:AssessmentBundle"}], "apv:profile": "q@1"},
                   CORE: {"prov:type": [{**Q, "$": "prov:Bundle"}, {**Q, "$": "apv:CoreBundle"}]}},
        "bundle": {CORE: {"entity": {"x:e": {}}}, INF: {"entity": {"x:e.mn-aaaaaaaaaaaa": {}}},
                   ASS: {"entity": {"x:as-aaaaaaaaaaaaaaaa": {"apv:premise": {**Q, "$": premise}},
                                    "x:as-cccccccccccccccc": {}}},
                   AS2: {"entity": {"x:as-bbbbbbbbbbbbbbbb": {}}}, "xd:bundle.other": {"entity": {"x:o": {}}}},
    })
    assert {f.code for f in linkage._premises(view)} == ({"pv.linkage.premise_scope"} if breach else set())


# ------------------------------------------------------------------------------------------------ D-621 amendment 3
A64, B64 = "a" * 64, "b" * 64


def _carried(tmp_path: Path, chain: int, changed: bool, *, same_cause: bool = False,
             fork: bool = False) -> tuple[Any, Any, Any]:
    """``st0`` changes the environment A -> B; ``st1``..``st<chain>`` (caused by ``te1``, ``te2``, or all by ``te1``
    when ``same_cause``) each carry it over (``apv:EnvironmentCarriedOver``, after the previous one, or all after
    ``st0`` when ``fork``), the last ending at A when ``changed`` (every one when ``fork``), else unchanged; a checker
    judgement uses the post state (``apv:CheckerUsesPostState``); ``st9`` is an unrelated state change after
    nothing."""
    from aer_support import derived

    from agentprov.aer.rules import RuleEntry

    extra = {"tst.carry@1": RuleEntry("tst.carry", 1, "D", "active", "carry", assumptions=("apv:EnvironmentCarriedOver",)),
             "tst.post@1": RuleEntry("tst.post", 1, "D", "active", "post", assumptions=("apv:CheckerUsesPostState",))}
    sc = {"scope": "att0", "target": "environment", "canon": "tst-canon"}
    records = ps.generic_records()
    records.append(derived({"k": "state_change", "id": "st9", **sc, "cause": "te2", "before_sha256": B64,
                            "after_sha256": A64}))
    records.append(derived({"k": "state_change", "id": "st0", **sc, "cause": "te0", "before_sha256": A64,
                            "after_sha256": B64}))
    for i in range(1, chain + 1):
        ends_at_a = changed and (fork or i == chain)
        records.append(derived({"k": "state_change", "id": f"st{i}", **sc, "cause": "te1" if same_cause else f"te{i}",
                                "before_sha256": B64, "after_sha256": A64 if ends_at_a else B64,
                                "after": [{"id": "st0" if fork else f"st{i - 1}", "b": "pos"}]}, "tst.carry@1"))
    records.append(derived({"k": "judgement", "id": "j0", "actor": "human", "subject": "att0", "name": "utility",
                            "value": True, "origin": "checker"}, "tst.post@1"))
    aer = ps.write_aer(records, tmp_path / "carry.aer.jsonl")
    registry = ps.registry(extra)
    assert ps.check_valid(aer, registry) == []
    return aer, registry, derive(aer, registry=registry)


@pytest.mark.parametrize("chain,changed", [(1, True), (1, False), (2, False)])
def test_a_carried_over_state_binds_to_its_predecessor(tmp_path, chain, changed):
    """D-621 amendment 3: a carried-over state change cites its own fields for the predecessor state the engine chose
    along ``after`` edges (``env_call`` usage and invalidation, and the checker's post-state usage of an unchanged
    carried state). At 122fade2 these failed ``pv.linkage.pointer_unbound`` on the engine's output."""
    aer, registry, result = _carried(tmp_path, chain, changed)
    statements = [(s, v) for b in result.document["bundle"].values() for s in ("used", "wasInvalidatedBy")
                  for v in b.get(s, {}).values()]
    carry = [v for s, v in statements if v.get("apv:rule") == "aprov.env_call@1" and v.get("prov:entity") == "x:st0.after"]
    post = [v for s, v in statements if v.get("apv:rule") == "aprov.outcome@1" and v.get("prov:activity") == "x:j0.check"]
    assert {p for v in carry for p in as_pointers(v) if "/" not in p} == {f"st{i}" for i in range(1, chain + 1)}
    assert [v["prov:entity"] for v in post] == [f"x:st{chain}.after" if changed else "x:st0.after"]
    assert validate_prov(result.prov_json, aer, registry=registry).passed


@pytest.mark.parametrize("fork,changed", [(False, False), (False, True), (True, False), (True, True)])
def test_carried_over_state_changes_with_one_cause_share_one_statement(tmp_path, fork, changed):
    """Regen item 165: two carried-over state changes with the same cause and the same predecessor state (a chain
    whose first link is unchanged, or a fork) both support ``used(cause, predecessor state)`` (and, when both change
    it in a fork, its invalidation). The engine states each fact once, citing every supporting state change, instead
    of refusing the derivation with ``prov.statement_collision``; it adds no relation that a record does not support."""
    aer, registry, result = _carried(tmp_path, 2, changed, same_cause=True, fork=fork)
    rels = [(s, v) for b in result.document["bundle"].values() for s in ("used", "wasInvalidatedBy", "wasGeneratedBy")
            for v in b.get(s, {}).values() if v.get("apv:rule") == "aprov.env_call@1"]
    used = [v for s, v in rels if s == "used" and v["prov:activity"] == "x:te1"]
    assert [v["prov:entity"] for v in used] == ["x:st0.after"]
    assert {p for p in as_pointers(used[0]) if "/" not in p} == {"st1", "st2"}
    invalidated = [v for s, v in rels if s == "wasInvalidatedBy" and v["prov:activity"] == "x:te1"]
    assert [{p for p in as_pointers(v) if "/" not in p} for v in invalidated] == (
        [{"st1", "st2"} if fork else {"st2"}] if changed else [])
    generated = sorted(v["prov:entity"] for s, v in rels if s == "wasGeneratedBy" and v["prov:activity"] == "x:te1")
    assert generated == (["x:st1.after", "x:st2.after"] if fork and changed else ["x:st2.after"] if changed else [])
    assert validate_prov(result.prov_json, aer, registry=registry).passed


def test_a_state_change_outside_the_after_closure_does_not_bind(tmp_path):
    aer, registry, result = _carried(tmp_path, 1, False)
    doc = strict_json_loads(result.prov_json)
    iri, key = next((i, k) for i, b in doc["bundle"].items() for k, v in b.get("used", {}).items()
                    if v.get("apv:rule") == "aprov.outcome@1" and v.get("prov:entity") == "x:st0.after")
    doc["bundle"][iri]["used"][key]["apv:sourcePointer"] = ["st9", "j0", "j0/origin"]
    report = validate_prov(jcs_bytes(doc), aer, registry=registry, roundtrip=False)
    assert "pv.linkage.pointer_unbound" in report.get("pv.linkage.source_pointer").codes()


def as_pointers(body: dict[str, Any]) -> list[str]:
    value = body.get("apv:sourcePointer")
    return value if isinstance(value, list) else [value]
