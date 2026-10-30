"""The assessment bundle on a golden v1 AER (EF E.7; J.3.5 gate D with SEM; K.10 NE-10).

The AER is golden pair R04, the C.16.2 trace (banking ``user_task_2`` x ``injection_task_5``). A hand-built SEM document
over it covers every row of the E.7.3 mapping table: integrity, role (on a request part and on executions), channel,
outcome, namespaced labels on an entity and an activity, injection markers (present, ambiguous, absent, gap) and an
author; the engine adds exposure and taint. The tests check one statement shape per row, the exposure/taint selection
counts, tier 4 in release mode, and that each assessment-bundle check fires its code on a targeted mutation. Messages
carry ids, rule names and QNames only (R-42).
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "unit" / "prov"))

from assess_support import FakeProfile, ann, sem_document, with_semtest  # noqa: E402

from agentprov.aer.reader import AerDocument  # noqa: E402
from agentprov.aer.rules import RuleRegistry  # noqa: E402
from agentprov.io.canonical import jcs_bytes  # noqa: E402
from agentprov.prov.engine import ProvDerivationError, ProvDerivation, derive  # noqa: E402
from agentprov.sem.types import SemDocument  # noqa: E402
from agentprov.validate import validate_prov  # noqa: E402

PAIR = "R04"
PROFILE = FakeProfile()
PROFILES = {(PROFILE.id, PROFILE.version): PROFILE}
CONTEXT = "adprov.context_is_prefix@1"


def c162_annotations() -> list[Any]:
    """The C.14.5 annotations, extended to cover every E.7.3 row (ids a0, a1, … in this order)."""
    return [
        ann("m3#0", "integrity", "untrusted", "I", "integrity_table", [("te0", "/name")]),  # a0
        ann("m3#0", "channel", "file", "I", "channel_table", [("te0", "/name")]),  # a1
        ann("m3#0", "injection_marker", {"fixture": "fx0", "status": "present", "normaliser": "semtest.norm@1"}, "D",
            "marker", [("m3", "/parts/0/text"), ("fx0", "/content")], at="/text", span=(154, 399)),  # a2
        ann("te0", "role", ["content_source"], "I", "read_tools", [("te0", "/name")]),  # a3
        ann("te1", "role", ["write_sink"], "I", "sink_tools", [("te1", "/name")]),  # a4
        ann("te2", "role", ["send_sink"], "I", "sink_tools", [("te2", "/name")]),  # a5
        ann("j0", "outcome", {"claim": "user_task_solved", "holds": False}, "D", "polarity", [("j0", "/value")]),  # a6
        ann("j1", "outcome", {"claim": "attack_succeeded", "holds": True, "score": 1, "scale": "binary"}, "D", "polarity",
            [("j1", "/value"), ("j1", "/origin"), ("exec", "/task/attack_id")]),  # a7
        ann("m0#0", "integrity", "trusted", "I", "integrity_table", [("m0", "/role")]),  # a8
        ann("m1#0", "integrity", "trusted", "I", "integrity_table", [("m1", "/role")]),  # a9
        ann("m5#0", "integrity", "untrusted", "I", "integrity_table", [("te1", "/name")]),  # a10
        ann("m7#0", "integrity", "untrusted", "I", "integrity_table", [("te2", "/name")]),  # a11
        ann("m3#0", "author", "Your landlord", "D", "author_field", [("m3", "/parts/0/text")], at="/text",
            span=(411, 424)),  # a12
        ann("te1", "semtest.cell", {"winnable": False}, "D", "ns_label", [("te1", "/name")]),  # a13
        ann("fx0", "semtest.cell", "landlord_notice", "D", "ns_label", [("fx0", "/vector")]),  # a14
        ann("m5#0", "injection_marker", {"fixture": "fx0", "status": "ambiguous", "normaliser": "semtest.norm@1"}, "I",
            "normaliser_faith", [("m5", "/parts/0/error"), ("fx0", "/content")]),  # a15: its rule declares the assumption
        ann("m7#0", "injection_marker", {"fixture": "fx0", "status": "absent", "normaliser": "semtest.norm@1"}, "D",
            "marker", [("m7", "/parts/0/text"), ("fx0", "/content")]),  # a16
        ann("m8#0", "injection_marker", {"fixture": "fx0", "status": "gap", "normaliser": "semtest.norm@1"}, "D",
            "marker", [("fx0", "/content")]),  # a17
        ann("m6#1", "role", ["send_sink"], "I", "sink_tools", [("m6", "/parts/1/name")]),  # a18
        ann("m3#0", "integrity", "untrusted", "I", "integrity_table", [("a0", "")]),  # a19: premise an earlier annotation
    ]


class Golden:
    def __init__(self, aer: AerDocument) -> None:
        self.aer = aer
        self.registry: RuleRegistry = with_semtest()
        self.sem: SemDocument = sem_document(aer, c162_annotations())
        self.result: ProvDerivation = derive(aer, [self.sem], registry=self.registry, sem_profiles=PROFILES)
        self.doc: dict[str, Any] = json.loads(self.result.prov_json)
        self.iri = next(k for k in self.doc["bundle"] if ".assess." in k)
        self.bundle: dict[str, Any] = self.doc["bundle"][self.iri]

    def entities(self) -> dict[str, dict[str, Any]]:
        return dict(self.bundle.get("entity", {}))

    def by_ann(self, ann_id: str) -> list[tuple[str, dict[str, Any]]]:
        return [(k, v) for k, v in self.entities().items() if v.get("apv:annotationId") == ann_id]

    def claims(self, claim: str) -> list[tuple[str, dict[str, Any]]]:
        return [(k, v) for k, v in self.entities().items() if v.get("apv:claim", {}).get("$") == claim]

    def name_of(self, rule: str, section: str, **args: str) -> str:
        for iri, bundle in self.doc["bundle"].items():
            if ".assess." in iri:
                continue
            for key, body in bundle.get(section, {}).items():
                if body.get("apv:rule") == rule and all(body.get(k) == v for k, v in args.items()):
                    return str(key)
        raise AssertionError(f"no {rule} {section} with {args}")


@pytest.fixture(scope="module")
def golden(golden_derivations: dict[str, Any]) -> Golden:
    return Golden(golden_derivations[PAIR].aer)


def q(name: str) -> dict[str, str]:
    return {"$": name, "type": "prov:QUALIFIED_NAME"}


def cls(body: dict[str, Any]) -> str:
    return str(body["apv:evidenceClass"]["$"])


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else [value]


# ============================================================================================================ structure
def test_one_assessment_bundle_with_its_top_level(golden: Golden) -> None:
    doc, iri = golden.doc, golden.iri
    assert iri.startswith("xd:bundle.assess.semtest-suites-v1.")
    entity = doc["entity"][iri]
    assert {v["$"] for v in entity["prov:type"]} == {"prov:Bundle", "apv:AssessmentBundle"}
    assert entity["apv:profile"] == "semtest.suites@1" and entity["apv:derivationKey"] == iri.rsplit(".", 1)[1]
    sem = f"xd:sem.semtest-suites-v1.{golden.sem.digest}"
    assert doc["entity"][sem]["apv:sha256"] == golden.sem.digest and doc["entity"][sem]["apv:semVersion"] == "sem/0.1"
    assert doc["entity"]["rules:semtest.suites.1"]["apv:sha256"] == PROFILE.sha256
    assert {v["$"] for v in doc["entity"]["rules:semtest.suites.1"]["prov:type"]} == {"prov:Plan", "apv:SemanticsProfile"}
    derived = [b for b in doc["wasDerivedFrom"].values() if b["prov:generatedEntity"] == iri]
    assert {b["prov:usedEntity"] for b in derived if b["apv:rule"] == "aprov.t_derive@1"} >= {sem}
    derive_act = next(k for k in doc["activity"] if k.startswith("xd:derive."))
    assert any(b["prov:activity"] == derive_act and b["prov:entity"] == sem for b in doc["used"].values())
    annotate = [b for b in doc["wasGeneratedBy"].values() if b["prov:entity"] == sem]
    assert len(annotate) == 1 and annotate[0]["apv:rule"] == "aprov.t_annotate@1"
    assoc = [b for b in doc["wasAssociatedWith"].values() if b["prov:activity"] == annotate[0]["prov:activity"]]
    assert assoc[0]["prov:plan"] == "rules:semtest.suites.1" and assoc[0]["prov:agent"] == "sw:agentprov"
    # E.7.2 item 2: the evaluation activity and its association
    assert golden.bundle["activity"] == {"x:assess.semtest-suites-v1": {
        "prov:type": q("apv:PolicyEvaluation"), "apv:evidenceClass": q("apv:Observed"), "apv:rule": "aprov.a_evaluation@1"}}
    (assoc_body,) = golden.bundle["wasAssociatedWith"].values()
    assert (assoc_body["prov:agent"], assoc_body["prov:plan"]) == ("sw:agentprov", "rules:semtest.suites.1")
    # E.7.2 item 5: only the allowed forms
    assert set(golden.bundle) == {"entity", "activity", "wasAssociatedWith", "wasGeneratedBy", "mentionOf"}


def test_core_and_inference_bundles_are_unchanged_by_sem(golden: Golden, golden_derivations: dict[str, Any]) -> None:
    plain = json.loads(golden_derivations[PAIR].prov_json)
    assert {k: v for k, v in golden.doc["bundle"].items() if ".assess." not in k} == plain["bundle"]


def test_report_counts(golden: Golden) -> None:
    counts = golden.result.report.assessment[golden.iri]
    assert counts == {"authorship": 1, "exposure_trusted_object": 6, "exposures": 6, "labels": 15,
                      "payload_absent": 1, "payload_ambiguous": 1, "payload_gap": 1, "payload_present": 1, "taints": 6}
    info = next(b for b in golden.result.bundles if b.kind == "assessment")
    assert info.profile == "semtest.suites@1" and info.iri == golden.iri
    assert golden.result.report.rules_fired["aprov.a_exposure@1"] == 12  # 6 assessments + 6 generations
    assert golden.result.report.as_json()["assessment"][golden.iri] == counts


# ============================================================================================================ E.7.3 rows
def test_integrity_mention(golden: Golden) -> None:
    ((key, body),) = golden.by_ann("a0")
    assert key.startswith("x:m3-0.mn-") and body["apv:integrity"] == q("apv:Untrusted")
    assert cls(body) == "apv:Inferred" and body["apv:method"] == "semtest.integrity_table@1"
    assert body["apv:basisRule"] == "semtest.integrity_table@1"
    assert body["apv:sourcePointer"] == ["te0/name", "m3/parts/0"]  # record position, then pointer (E.1.5 item 6)
    assert "prov:type" not in body and "apv:premise" not in body
    mentions = [m for m in golden.bundle["mentionOf"].values() if m["prov:specificEntity"] == key]
    core = next(k for k in golden.doc["bundle"] if ".core." in k)
    assert mentions == [{"prov:specificEntity": key, "prov:generalEntity": "x:m3-0", "prov:bundle": core}]


def test_label_premised_on_an_earlier_annotation(golden: Golden) -> None:
    ((_, body),) = golden.by_ann("a19")
    ((first, _),) = golden.by_ann("a0")
    assert body["apv:premise"] == q(first) and body["apv:sourcePointer"] == "m3/parts/0"


def test_role_on_request_part_is_a_mention(golden: Golden) -> None:
    ((key, body),) = golden.by_ann("a18")
    assert key.startswith("x:m6-1.mn-") and body["apv:securityRole"] == q("apv:SendSink")


def test_role_on_execution_is_a_labelled_assessment(golden: Golden) -> None:
    ((key, body),) = golden.by_ann("a3")
    assert key.startswith("x:as-")
    assert body["prov:type"] == q("apv:Assessment") and body["apv:claim"] == q("apv:Labelled")
    assert body["apv:subject"] == q("x:te0") and body["apv:securityRole"] == q("apv:ContentSource")
    assert body["apv:premise"] == q("x:te0") and "apv:object" not in body
    gens = [g for g in golden.bundle["wasGeneratedBy"].values() if g["prov:entity"] == key]
    assert gens == [{**{k: v for k, v in body.items() if k.startswith("apv:") and k not in (
        "apv:claim", "apv:subject", "apv:securityRole", "apv:annotationId", "apv:premise")},
        "prov:entity": key, "prov:activity": "x:assess.semtest-suites-v1", "apv:premise": q(key)}]


def test_channel_mention(golden: Golden) -> None:
    ((key, body),) = golden.by_ann("a1")
    assert key.startswith("x:m3-0.mn-") and body["apv:sourceChannel"] == "file"


def test_outcome_mentions_carry_polarity(golden: Golden) -> None:
    ((_, utility),) = golden.by_ann("a6")
    assert utility["apv:outcomeClaim"] == "user_task_solved" and utility["apv:outcomeHolds"] is False
    assert cls(utility) == "apv:Derived" and "apv:method" not in utility
    ((key, security),) = golden.by_ann("a7")
    assert key.startswith("x:j1.mn-")
    assert security["apv:outcomeHolds"] is True and security["apv:outcomeScale"] == "binary"
    assert security["apv:outcomeScore"] == {"$": "1.0", "type": "xsd:double"}


def test_namespaced_labels(golden: Golden) -> None:
    ((key, activity),) = golden.by_ann("a13")
    assert key.startswith("x:as-") and activity["apv:claim"] == q("apv:Labelled")
    assert activity["apv:annotationType"] == "semtest.cell" and activity["apv:annotationValue"] == '{"winnable":false}'
    ((key, entity),) = golden.by_ann("a14")
    assert key.startswith("x:fx0.mn-") and entity["apv:annotationValue"] == '"landlord_notice"'


def test_payload_present_is_derived(golden: Golden) -> None:
    ((key, body),) = golden.by_ann("a2")
    assert body["apv:claim"] == q("apv:ContainsPayload")
    assert (body["apv:subject"], body["apv:object"]) == (q("x:m3-0"), q("x:fx0"))
    assert (body["apv:spanStart"], body["apv:spanEnd"]) == (154, 399)
    assert cls(body) == "apv:Derived" and "apv:method" not in body and "apv:markerStatus" not in body
    assert body["apv:basisRule"] == ["semtest.marker@1", "semtest.norm@1"]  # the marker rule and its normaliser
    assert body["apv:sourcePointer"] == ["fx0/content", "m3/parts/0", "m3/parts/0/text"]
    assert {p["$"] for p in as_list(body["apv:premise"])} == {"x:m3-0", "x:fx0"}


def test_payload_ambiguous_is_inferred_with_an_assumption(golden: Golden) -> None:
    ((_, body),) = golden.by_ann("a15")
    assert body["apv:claim"] == q("apv:ContainsPayload") and body["apv:markerStatus"] == q("apv:Ambiguous")
    assert cls(body) == "apv:Inferred" and set(as_list(body["apv:method"])) == {"aprov.a_payload@2", "semtest.normaliser_faith@1"}
    # the profile's assumption, not a core term (D-17): a string on apv:adapterAssumption (apv 0.2.0, D-501)
    assert body["apv:adapterAssumption"] == "semtest:NormaliserFaithful" and "apv:assumption" not in body


def test_an_ambiguous_marker_whose_rules_declare_no_assumption_is_refused(golden: Golden) -> None:
    anns = c162_annotations()
    anns[15] = ann("m5#0", "injection_marker", {"fixture": "fx0", "status": "ambiguous", "normaliser": "semtest.norm@1"},
                   "D", "marker", [("m5", "/parts/0/error"), ("fx0", "/content")])
    with pytest.raises(ProvDerivationError) as exc:
        derive(golden.aer, [sem_document(golden.aer, anns)], registry=golden.registry, sem_profiles=PROFILES)
    assert exc.value.code == "prov.sem_invalid"


def test_payload_absent_and_gap_give_no_statement(golden: Golden) -> None:
    assert golden.by_ann("a16") == [] and golden.by_ann("a17") == []
    assert len(golden.claims("apv:ContainsPayload")) == 2


def test_author_mention_and_inferred_authorship(golden: Golden) -> None:
    found = dict(golden.by_ann("a12"))
    mention = next(k for k in found if ".mn-" in k)
    assessment = next(k for k in found if k.startswith("x:as-"))
    assert found[mention]["apv:declaredSender"] == "Your landlord" and cls(found[mention]) == "apv:Derived"
    body = found[assessment]
    assert body["apv:claim"] == q("apv:QuotesAuthoredContent") and body["apv:authorName"] == "Your landlord"
    assert body["apv:premise"] == q(mention) and (body["apv:spanStart"], body["apv:spanEnd"]) == (411, 424)
    assert cls(body) == "apv:Inferred" and body["apv:method"] == "aprov.a_author@2"
    assert not any(b.get("apv:rule") == "aprov.a_author@2" for b in golden.doc.get("wasAttributedTo", {}).values())


def test_exposure_cites_context_membership_and_generation(golden: Golden) -> None:
    exposures = golden.claims("apv:ExposedTo")
    pairs = sorted((b["apv:subject"]["$"], b["apv:object"]["$"]) for _, b in exposures)
    # m2-1 saw only trusted members (m0, m1); m4-1 and m6-1 see the unknown assistant turns and untrusted outputs
    assert pairs == [("x:m4-1", "x:m2"), ("x:m4-1", "x:m3"), ("x:m6-1", "x:m2"), ("x:m6-1", "x:m3"),
                     ("x:m6-1", "x:m4"), ("x:m6-1", "x:m5")]
    body = next(b for _, b in exposures if (b["apv:subject"]["$"], b["apv:object"]["$"]) == ("x:m4-1", "x:m3"))
    use = golden.name_of("aprov.use_context@1", "used", **{"prov:activity": "x:mc1", "prov:entity": "x:m3"})
    gen = golden.name_of("aprov.gen_part@1", "wasGeneratedBy", **{"prov:entity": "x:m4-1"})
    assert {p["$"] for p in as_list(body["apv:premise"])} == {use, gen}
    # weakest premise (AD-05): v1 context membership is INFERRED, so is the exposure; the generation of the part is
    # INFERRED too (adprov.assistant_turn_one_call cites no code: its twin, D-27 c6), so both methods are named
    assert cls(body) == "apv:Inferred"
    assert set(as_list(body["apv:method"])) == {CONTEXT, "adprov.assistant_turn_one_call_unverified@1"}
    assert "apv:sourcePointer" not in body and "apv:annotationId" not in body


def test_taint_follows_the_profile_policy(golden: Golden) -> None:
    taints = golden.claims("apv:PotentiallyInfluencedBy")
    assert len(taints) == 6
    exposure_names = {k for k, _ in golden.claims("apv:ExposedTo")}
    ((role_te1, _),) = golden.by_ann("a4")
    ((integrity_m3, _),) = golden.by_ann("a0")
    for _, body in taints:
        assert body["apv:policy"] == "semtest.taint_sink_untrusted@1" and cls(body) == "apv:Inferred"
        assert "aprov.a_taint@1" in body["apv:method"] and CONTEXT in body["apv:method"]
        premises = {p["$"] for p in as_list(body["apv:premise"])}
        assert len(premises & exposure_names) == 1
    m4_m3 = next(b for _, b in taints if (b["apv:subject"]["$"], b["apv:object"]["$"]) == ("x:m4-1", "x:m3"))
    assert {role_te1, integrity_m3} <= {p["$"] for p in as_list(m4_m3["apv:premise"])}


def test_neutral_request_and_no_policy(golden: Golden) -> None:
    anns = c162_annotations()
    anns[3] = ann("te0", "role", ["neutral"], "I", "read_tools", [("te0", "/name")])
    sem = sem_document(golden.aer, anns, profile=FakeProfile(taint_policy=None))
    result = derive(golden.aer, [sem], registry=golden.registry,
                    sem_profiles={(PROFILE.id, PROFILE.version): FakeProfile(taint_policy=None)})
    counts = next(iter(result.report.assessment.values()))
    assert counts["exposure_neutral_request"] == 1 and counts["exposures"] == 6 and "taints" not in counts


def test_unlabelled_requests_and_members_fail_closed(golden: Golden) -> None:
    sem = sem_document(golden.aer, [])
    result = derive(golden.aer, [sem], registry=golden.registry, sem_profiles=PROFILES)
    counts = next(iter(result.report.assessment.values()))
    # every member of every generating invocation: 2 + 4 + 6 (unknown role, unknown integrity)
    assert counts == {"exposures": 12, "taints": 12}


# ============================================================================================================ tier 4
def _report(golden: Golden, doc: dict[str, Any], **kw: Any) -> Any:
    return validate_prov(jcs_bytes(doc), golden.aer, migration=True, registry=golden.registry,
                         sems=kw.pop("sems", [golden.sem]), **kw)


def test_assessment_bundle_passes_tier4_in_release_mode(golden: Golden) -> None:
    report = validate_prov(golden.result.prov_json, golden.aer, migration=True, registry=golden.registry,
                           sems=[golden.sem])
    assert [(o.id, sorted(o.codes())) for o in report.outcomes if o.status in ("fail", "skipped")] == []
    assert report.passed


def _mutated(golden: Golden) -> dict[str, Any]:
    return copy.deepcopy(golden.doc)


def _assess(doc: dict[str, Any], golden: Golden) -> dict[str, Any]:
    return doc["bundle"][golden.iri]  # type: ignore[no-any-return]


@pytest.mark.parametrize("section, args", [
    ("used", {"prov:activity": "x:assess.semtest-suites-v1", "prov:entity": "x:m3-0"}),
    ("wasDerivedFrom", {"prov:generatedEntity": "x:m4-1", "prov:usedEntity": "x:m3"}),
    ("wasInformedBy", {"prov:informed": "x:te1", "prov:informant": "x:te0"}),
    ("wasAttributedTo", {"prov:entity": "x:m3-0", "prov:agent": "x:att"}),
    ("wasInfluencedBy", {"prov:influencee": "x:m4-1", "prov:influencer": "x:m3"}),
])
def test_forbidden_relation_in_the_assessment_bundle_is_ne10(golden: Golden, section: str, args: dict[str, str]) -> None:
    doc = _mutated(golden)
    _assess(doc, golden).setdefault(section, {})["x:a_taint.aaaaaaaaaaaaaaaa"] = {
        **args, "apv:evidenceClass": q("apv:Inferred"), "apv:rule": "aprov.a_taint@1", "apv:method": "aprov.a_taint@1"}
    report = _report(golden, doc, roundtrip=False)
    assert report.get("PV-NE-10").failed  # type: ignore[union-attr]
    assert "pv.profiles.assessment_form" in report.codes()


def test_redeclared_subject_and_foreign_generation_are_flagged(golden: Golden) -> None:
    doc = _mutated(golden)
    bundle = _assess(doc, golden)
    core = next(v for k, v in doc["bundle"].items() if ".core." in k)
    bundle["entity"]["x:m3-0"] = copy.deepcopy(core["entity"]["x:m3-0"])
    key, gen = next(iter(bundle["wasGeneratedBy"].items()))
    bundle["wasGeneratedBy"][key] = {**gen, "prov:activity": "x:te0"}
    report = _report(golden, doc, roundtrip=False)
    found = {(f.code, f.detail) for f in report.findings("pv.profiles.assessment_form")}
    assert any("re-declared" in d for _, d in found) and any("wasGeneratedBy other" in d for _, d in found)


def test_mention_cardinality_and_uniqueness(golden: Golden) -> None:
    doc = _mutated(golden)
    bundle = _assess(doc, golden)
    ((mention, body),) = golden.by_ann("a1")
    key, rel = next((k, v) for k, v in bundle["mentionOf"].items() if v["prov:specificEntity"] == mention)
    bundle["mentionOf"]["_:a_label.aaaaaaaaaaaaaaaa"] = dict(rel)
    twin = mention[:-12] + "aaaaaaaaaaaa"
    bundle["entity"][twin] = dict(body)
    bundle["mentionOf"]["_:a_label.bbbbbbbbbbbbbbbb"] = {**rel, "prov:specificEntity": twin}
    report = _report(golden, doc, roundtrip=False)
    assert {"pv.profiles.mention_cardinality", "pv.profiles.mention_duplicate"} <= report.codes()


def test_mention_in_the_core_is_flagged(golden: Golden) -> None:
    doc = _mutated(golden)
    bundle = _assess(doc, golden)
    core = next(v for k, v in doc["bundle"].items() if ".core." in k)
    ((mention, _),) = golden.by_ann("a0")
    core["entity"][mention] = bundle["entity"].pop(mention)
    report = _report(golden, doc, roundtrip=False)
    assert {"pv.profiles.interpretation_in_core", "pv.profiles.assessment_outside"} <= report.codes()


def test_annotation_linkage(golden: Golden) -> None:
    doc = _mutated(golden)
    bundle = _assess(doc, golden)
    ((mention, _),) = golden.by_ann("a0")
    ((other, _),) = golden.by_ann("a1")
    del bundle["entity"][mention]["apv:annotationId"]
    bundle["entity"][other]["apv:annotationId"] = "a6"  # an annotation of j0, not of m3#0
    report = _report(golden, doc, roundtrip=False)
    details = {f.detail for f in report.findings("pv.linkage.annotation")}
    assert any("without apv:annotationId" in d for d in details) and any("not the statement's subject" in d
                                                                         for d in details)
    missing = _report(golden, golden.doc, roundtrip=False, sems=[])
    assert "pv.linkage.sem_missing" in missing.codes()


def test_evidence_linkage_of_assessments(golden: Golden) -> None:
    doc = _mutated(golden)
    bundle = _assess(doc, golden)
    ((payload, _),) = golden.by_ann("a2")
    bundle["entity"][payload]["apv:sourcePointer"] = ["fx0/content", "m3/parts/9"]
    bundle["entity"][payload]["apv:basisRule"] = ["semtest.marker@1", "semtest.sink_tools@1"]
    ((role, _),) = golden.by_ann("a3")
    bundle["entity"][role]["apv:premise"] = q("x:as-aaaaaaaaaaaaaaaa")
    report = _report(golden, doc, roundtrip=False)
    assert {"prov.link.unresolved", "pv.linkage.basis_not_cited", "pv.linkage.premise_unresolved"} <= report.codes()
