"""Assessment bundles in the structure and profile checks (EF E.3.1-E.3.2, E.7.2 item 5; K.10 NE-10), on synthetic,
builder-independent documents."""

from __future__ import annotations

from typing import Any

from agentprov.validate import profiles, prov_structure
from agentprov.validate._provdoc import ProvView
from agentprov.validate.tiers import CheckOutcome

from validate_support import CORE, ev, minimal_aer, minimal_doc, q, t_spec

DK = "b" * 26
ASSESS = f"xd:bundle.assess.semtest-suites-v1.{DK}"
ACT = "x:assess.semtest-suites-v1"


def _codes(outcomes: list[CheckOutcome]) -> set[str]:
    return {f.code for o in outcomes for f in o.findings}


def doc_with_assessment(**extra: Any) -> dict[str, Any]:
    doc = minimal_doc({"entity": {"x:m0": ev(rule="aprov.n_message@1")}})
    doc["agent"] = {"sw:agentprov": {"prov:type": q("apv:ProvEngine"), **ev(rule="aprov.t_agents@1")}}
    doc["entity"]["rules:semtest.suites.1"] = {"prov:type": [q("apv:SemanticsProfile"), q("prov:Plan")],
                                               **ev(rule="aprov.t_plans@1")}
    doc["entity"][ASSESS] = {"prov:type": [q("apv:AssessmentBundle"), q("prov:Bundle")], "apv:derivationKey": DK,
                             "apv:profile": "semtest.suites@1", **ev(rule="aprov.t_derive@1")}
    doc["bundle"][ASSESS] = {
        "activity": {ACT: {"prov:type": q("apv:PolicyEvaluation"), **ev(rule="aprov.a_evaluation@1")}},
        "wasAssociatedWith": {"x:a_evaluation.aaaaaaaaaaaaaaaa": {
            "prov:activity": ACT, "prov:agent": "sw:agentprov", "prov:plan": "rules:semtest.suites.1",
            **ev(rule="aprov.a_evaluation@1")}},
        "entity": {"x:m0.mn-aaaaaaaaaaaa": {"apv:integrity": q("apv:Trusted"), "apv:annotationId": "a0",
                                            **ev("Derived", rule="aprov.a_label@1")}},
        "mentionOf": {"_:a_label.aaaaaaaaaaaaaaaa": {"prov:specificEntity": "x:m0.mn-aaaaaaaaaaaa",
                                                     "prov:generalEntity": "x:m0", "prov:bundle": CORE}},
        **extra,
    }
    return t_spec(doc)


def test_assessment_bundle_kind_and_scope() -> None:
    view = ProvView.parse(doc_with_assessment())
    (bundle,) = view.assessment()
    assert bundle.kind == "assessment" and bundle.profile == "semtest.suites@1" and bundle.methods is None
    assert {b.iri for b in view.visible(ASSESS)} == {CORE, ASSESS}


def test_assessment_bundle_structure_is_clean() -> None:
    outcomes = prov_structure.check(doc_with_assessment())
    assert [(o.id, sorted(o.codes())) for o in outcomes if o.status != "pass"] == []


def test_assessment_bundle_entity_needs_its_profile() -> None:
    doc = doc_with_assessment()
    doc["entity"][ASSESS]["apv:profile"] = "other.profile@1"
    assert "pv.prov_structure.bundle_entity" in _codes(prov_structure.check(doc))
    del doc["entity"][ASSESS]["apv:profile"]
    assert "pv.prov_structure.bundle_entity" in _codes(prov_structure.check(doc))


def test_allowed_forms() -> None:
    clean = profiles.check(ProvView.parse(doc_with_assessment()), minimal_aer({"k": "message", "id": "m0"}))
    assert "pv.profiles.assessment_form" not in _codes(clean)
    bad = doc_with_assessment(used={"x:a_label.bbbbbbbbbbbbbbbb": {
        "prov:activity": ACT, "prov:entity": "x:m0", **ev("Derived", rule="aprov.a_label@1")}})
    codes = _codes(profiles.check(ProvView.parse(bad), minimal_aer({"k": "message", "id": "m0"})))
    assert "pv.profiles.assessment_form" in codes


def test_assessment_rule_outside_its_bundle() -> None:
    doc = doc_with_assessment()
    doc["bundle"][CORE]["entity"]["x:m0"]["apv:integrity"] = q("apv:Trusted")
    codes = _codes(profiles.check(ProvView.parse(doc), minimal_aer({"k": "message", "id": "m0"})))
    assert {"pv.profiles.assessment_outside", "pv.profiles.interpretation_in_core"} <= codes
