"""Generic PROV-JSON structure (K.10 ``test_prov_structure.py``): totality on malformed input (baseline V1), unknown
sections and prefixes (V2), canonical value forms (E.5.3), and the R-21 checks (NE-19)."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from agentprov.validate import prov_structure
from agentprov.validate.tiers import CheckOutcome

from validate_support import CORE, ev, minimal_doc, q


def _codes(outcomes: list[CheckOutcome]) -> set[str]:
    return {f.code for o in outcomes for f in o.findings}


def test_minimal_document_is_clean() -> None:
    assert all(o.status == "pass" for o in prov_structure.check(minimal_doc()))


@pytest.mark.parametrize("value", [None, 7, True, 3.5, "used", []])
def test_scalar_relation_section_is_a_finding_not_an_exception(value: Any) -> None:
    doc = minimal_doc()
    doc["used"] = value
    doc["bundle"][CORE]["wasGeneratedBy"] = value
    assert "pv.prov_structure.section_not_object" in _codes(prov_structure.check(doc))


@pytest.mark.parametrize("doc", [None, 3, "x", [], {"bundle": 5}, {"prefix": 1, "entity": {"x:a": 1}}])
def test_any_json_value_is_total(doc: Any) -> None:
    outcomes = prov_structure.check(doc)
    assert any(o.status == "fail" for o in outcomes)


def test_unknown_section_and_member_are_reported() -> None:
    doc = minimal_doc()
    doc["bundle"][CORE]["wasGeneratedby"] = {}
    doc["foo"] = {}
    codes = _codes(prov_structure.check(doc))
    assert "pv.prov_structure.top_member" in codes


def test_reserved_and_undeclared_prefixes() -> None:
    doc = minimal_doc({"entity": {"x:m0": ev(rule="aprov.n_message@1", **{"foo:bar": 1, "apv:about": q("zz:y")})}})
    doc["prefix"]["xsd"] = "http://www.w3.org/2001/XMLSchema#"
    codes = _codes(prov_structure.check(doc))
    assert {"pv.prov_structure.reserved_prefix", "pv.prov_structure.undeclared_prefix"} <= codes


def test_bundles_do_not_nest_or_declare_prefixes() -> None:
    doc = minimal_doc()
    doc["bundle"][CORE]["prefix"] = {"y": "http://y/"}
    doc["bundle"][CORE]["bundle"] = {}
    codes = _codes(prov_structure.check(doc))
    assert {"pv.prov_structure.bundle_prefix", "pv.prov_structure.nested_bundle"} <= codes


def test_exactly_one_core_bundle() -> None:
    doc = minimal_doc()
    del doc["bundle"][CORE]
    assert "pv.prov_structure.core_count" in _codes(prov_structure.check(doc))


@pytest.mark.parametrize(("value", "code"), [
    ([q("apv:Message")], "pv.prov_structure.singleton_array"),
    ([q("apv:Message"), q("apv:Message")], "pv.prov_structure.multi_value_duplicate"),
    ([q("apv:UserMessage"), q("apv:Message")], "pv.prov_structure.multi_value_order"),
    (1.5, "pv.prov_structure.value_form"),
    ({"$": "1.50", "type": "xsd:double"}, "pv.prov_structure.value_form"),
    (2**60, "pv.prov_structure.value_form"),
])
def test_value_forms(value: Any, code: str) -> None:
    doc = minimal_doc({"entity": {"x:m0": ev(rule="aprov.n_message@1", **{"prov:type": value})}})
    assert code in _codes(prov_structure.check(doc))


def test_relation_arguments_are_required_and_typed() -> None:
    core = {"entity": {"x:m0": ev(rule="aprov.n_message@1")},
            "wasGeneratedBy": {"x:gen_message.aaaaaaaaaaaaaaaa": {"prov:activity": 5, **ev(rule="aprov.gen_message@1")}}}
    codes = _codes(prov_structure.check(minimal_doc(core)))
    assert {"pv.prov_structure.missing_argument", "pv.prov_structure.argument_type"} <= codes


def test_statement_ids_and_blank_nodes() -> None:
    core = {"entity": {"x:m0": ev(rule="aprov.n_message@1"), "x:M-0": ev(rule="aprov.n_message@1")},
            "activity": {"x:te0": ev()},
            "used": {"_:use_request.aaaaaaaaaaaaaaaa": {"prov:activity": "x:te0", "prov:entity": "x:m0",
                                                        **ev(rule="aprov.use_request@1")},
                     "x:use_model.bbbbbbbbbbbbbbbb": {"prov:activity": "x:te0", "prov:entity": "x:m0",
                                                      **ev(rule="aprov.use_request@1")}}}
    codes = _codes(prov_structure.check(minimal_doc(core)))
    assert {"pv.prov_structure.blank_node", "pv.prov_structure.statement_id", "pv.prov_structure.node_name"} <= codes


def test_core_declares_every_node_it_references() -> None:
    core = {"activity": {"x:te0": ev()},
            "used": {"x:use_request.aaaaaaaaaaaaaaaa": {"prov:activity": "x:te0", "prov:entity": "x:m9",
                                                        **ev(rule="aprov.use_request@1")}}}
    assert "pv.prov_structure.core_undeclared" in _codes(prov_structure.check(minimal_doc(core)))


def test_ne19_used_activity_and_mention_of_activity() -> None:
    core = {"activity": {"x:te0": ev(), "x:te1": ev()},
            "used": {"x:use_request.aaaaaaaaaaaaaaaa": {"prov:activity": "x:te0", "prov:entity": "x:te1",
                                                        **ev(rule="aprov.use_request@1")}},
            "mentionOf": {"_:after.aaaaaaaaaaaaaaaa": {"prov:specificEntity": "x:te0", "prov:generalEntity": "x:te1",
                                                       "prov:bundle": CORE}}}
    outcomes = prov_structure.check(minimal_doc(core))
    ne19 = next(o for o in outcomes if o.id == "PV-NE-19")
    assert ne19.codes() == {"pv.prov_structure.used_activity", "pv.prov_structure.mention_not_entity"}


def test_unidentified_relations_carry_no_attributes() -> None:
    core = {"entity": {"x:m0": ev(rule="aprov.n_message@1"), "x:m0-0": ev(rule="aprov.n_part@1")},
            "hadMember": {"_:member_request.aaaaaaaaaaaaaaaa": {"prov:collection": "x:m0", "prov:entity": "x:m0-0",
                                                                "apv:rule": "aprov.member_request@1"}}}
    assert "pv.prov_structure.unidentified_attribute" in _codes(prov_structure.check(minimal_doc(core)))


def test_input_is_not_mutated() -> None:
    doc = minimal_doc()
    before = copy.deepcopy(doc)
    prov_structure.check(doc)
    assert doc == before
