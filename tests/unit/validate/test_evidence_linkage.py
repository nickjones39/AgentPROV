"""Evidence linkage and the entry point on synthetic inputs (K.10 ``test_evidence_linkage.py``): pointer resolution
under RFC 6901, the existence rule (R-22), INFERRED statements and their method sets, and the totality of
``validate_prov`` on bytes that are not a canonical JSON object."""

from __future__ import annotations

from typing import Any

import pytest

from agentprov.io.canonical import jcs_bytes
from agentprov.validate import linkage, profiles, validate_prov
from agentprov.validate._provdoc import ProvView
from validate_support import ev, minimal_aer, minimal_doc, q

AER = minimal_aer(
    {"k": "message", "id": "m0", "ev": "O", "role": "user", "parts": [{"t": "text", "text": None}], "a/b": 1},
    {"k": "tool_execution", "id": "te0", "ev": "D", "call": "m0#0", "name": "t"},
)


def _linkage(core: dict[str, Any]) -> dict[str, set[str]]:
    return {o.id: o.codes() for o in linkage.check(ProvView.parse(minimal_doc(core)), AER)}


@pytest.mark.parametrize(("pointer", "ok"), [
    ("m0", True), ("m0/parts/0", True), ("m0/parts/0/text", True), ("m0/a~1b", True), ("seal/n_records", True),
    ("m0/parts/1", False), ("m0/parts/00", False), ("m9", False), ("m0/nope", False), ("m0/parts/x", False),
])
def test_resolve_pointer(pointer: str, ok: bool) -> None:
    assert (linkage.resolve_pointer(AER, pointer) is not None) is ok


def test_clean_statement() -> None:
    core = {"entity": {"x:m0": ev(rule="aprov.n_message@1", **{"apv:sourcePointer": "m0"})}}
    # the synthetic document has no AER entity, derive activity or catalogue plan, so pv.linkage.aer_binding (D-621,
    # tests/unit/prov/test_tier4_bindings.py) reports it; every other linkage check is clean
    assert not any(v for k, v in _linkage(core).items() if k != "pv.linkage.aer_binding")


def test_unresolved_pointer_and_missing_pointer() -> None:
    core = {"entity": {"x:m0": ev(rule="aprov.n_message@1", **{"apv:sourcePointer": "m0/nope"}),
                       "x:m0-0": ev(rule="aprov.n_part@1")}}
    codes = _linkage(core)["pv.linkage.source_pointer"]
    assert codes == {"prov.link.unresolved", "pv.linkage.pointer_missing"}


def test_field_weaker_than_statement() -> None:
    core = {"activity": {"x:te0": ev("Observed", **{"apv:sourcePointer": "te0"})}}
    assert _linkage(core)["pv.linkage.source_pointer"] == {"pv.linkage.field_weaker"}


def test_existence_rule() -> None:
    core = {"entity": {"x:m0-0": ev("Observed", "aprov.n_part@1", **{"apv:sourcePointer": "m0/parts/0"})},
            "activity": {"x:te0": ev("Derived", **{"apv:sourcePointer": "te0"})},
            "used": {"x:use_request.aaaaaaaaaaaaaaaa": {"prov:activity": "x:te0", "prov:entity": "x:m0-0",
                                                        **ev("Observed", "aprov.use_request@1",
                                                             **{"apv:sourcePointer": "m0/parts/0"})}}}
    assert _linkage(core)["pv.linkage.existence"] == {"pv.linkage.existence"}


def test_inferred_in_core_without_method() -> None:
    core = {"entity": {"x:m0": ev("Inferred", "aprov.n_message@1", **{"apv:sourcePointer": "m0"})}}
    codes = _linkage(core)
    assert codes["pv.linkage.method"] == {"pv.linkage.method_missing"}
    assert codes["pv.linkage.class_bundle"] == {"pv.linkage.class_bundle"}


def test_unknown_rule_and_top_evidence() -> None:
    doc = minimal_doc({"entity": {"x:m0": ev(rule="aprov.nope@1", **{"apv:sourcePointer": "m0"})}})
    next(iter(doc["entity"].values()))["apv:sourcePointer"] = "m0"
    codes = {o.id: o.codes() for o in linkage.check(ProvView.parse(doc), AER)}
    assert codes["pv.linkage.rule"] == {"pv.linkage.rule_unknown"}
    assert codes["pv.linkage.evidence_attributes"] == {"pv.linkage.top_evidence"}


def test_ne21_generic_rules_follow_the_aer() -> None:
    aer = minimal_aer(
        {"k": "message", "id": "m0", "ev": "O", "role": "user", "parts": []},
        {"k": "message", "id": "m1", "ev": "O", "role": "user", "parts": []},
        {"k": "activity", "id": "ac0", "ev": "O", "type": "foo:plan", "inputs": ["m0"]},
    )
    core = {"entity": {"x:m0": ev(rule="aprov.n_message@1"), "x:m1": ev(rule="aprov.n_message@1")},
            "activity": {"x:ac0": ev(rule="aprov.g_act@1", **{"prov:type": [q("apv:GenericActivity"),
                                                                              q("apv:ToolExecution")]})},
            "used": {"x:g_use.aaaaaaaaaaaaaaaa": {"prov:activity": "x:ac0", "prov:entity": "x:m1",
                                                  **ev(rule="aprov.g_use@1")}}}
    out = {o.id: o for o in profiles.check(ProvView.parse(minimal_doc(core)), aer, migration=True)}
    assert out["PV-NE-21"].codes() == {"pv.profiles.generic_beyond_aer", "pv.profiles.generic_missing"}
    assert out["pv.profiles.migration_generic"].codes() == {"pv.profiles.migration_generic"}


@pytest.mark.parametrize("data", [b"", b"not json", b"[1]", b"\xff", b'{"a": 1, "a": 2}'])
def test_validate_prov_is_total(data: bytes) -> None:
    report = validate_prov(data, AER)
    assert not report.ok
    assert report.codes() <= {"pv.prov_structure.not_json", "pv.prov_structure.not_object"}


def test_non_canonical_bytes() -> None:
    data = jcs_bytes(minimal_doc()) + b"\n"
    report = validate_prov(data, AER, roundtrip=False)
    assert "pv.prov_structure.canonical_bytes" in report.codes()


@pytest.mark.parametrize(("attrs", "bad"), [
    ({"apv:assumption": q("apv:AutoExecution")}, False),
    ({"apv:assumption": "tst:Undeclared"}, True),  # a string on the object property: the CA-22 defect (D-501)
    ({"apv:assumption": q("apv:NotACoreIndividual")}, True),
    ({"apv:adapterAssumption": q("apv:AutoExecution")}, True),  # a QName on the data property
    ({"apv:adapterAssumption": "nons:Undeclared"}, True),  # no declared catalogue declares it
    ({"apv:adapterAssumption": "NoNamespace"}, True),
])
def test_assumption_attributes_by_kind(attrs: dict[str, Any], bad: bool) -> None:
    """apv:assumption holds core QNames, apv:adapterAssumption declared ``<ns>:<Name>`` strings (E.10 item 11)."""
    core = {"entity": {"x:m0": ev(rule="aprov.n_message@1", **{"apv:sourcePointer": "m0", **attrs})}}
    codes = set().union(*_linkage(core).values())
    assert ("pv.linkage.assumption" in codes) is bad


def test_top_level_statements_carry_no_adapter_assumption() -> None:
    doc = minimal_doc({"entity": {"x:m0": ev(rule="aprov.n_message@1", **{"apv:sourcePointer": "m0"})}})
    next(iter(doc["entity"].values()))["apv:adapterAssumption"] = "tst:Thing"
    codes = {o.id: o.codes() for o in linkage.check(ProvView.parse(doc), AER)}
    assert codes["pv.linkage.evidence_attributes"] == {"pv.linkage.top_evidence"}


#: An AER whose header declares the package ``rope`` catalogue (version 2), which declares rope:GuardDeniesBeforeDispatch.
ROPE_AER = minimal_aer(
    {"k": "message", "id": "m0", "ev": "O", "role": "user", "parts": [{"t": "text", "text": "hi"}]},
)
ROPE_AER.header["rules"]["rope"] = 2
DERIVE = "xd:derive." + "a" * 26


def _versioned_linkage(version: str | None, attrs: dict[str, Any]) -> set[str]:
    """Linkage codes of a document whose derive activity declares ``apv:vocabularyVersion`` = ``version`` (E.4.6)."""
    doc = minimal_doc({"entity": {"x:m0": ev(rule="aprov.n_message@1", **{"apv:sourcePointer": "m0", **attrs})}})
    if version is not None:
        doc["activity"] = {DERIVE: {"prov:type": q("apv:ProvDerivation"), "apv:vocabularyVersion": version,
                                    **ev(rule="aprov.t_derive@1")}}
    return set().union(*(o.codes() for o in linkage.check(ProvView.parse(doc), ROPE_AER)))


ADAPTER_ON_ASSUMPTION = {"apv:assumption": "rope:GuardDeniesBeforeDispatch"}


def test_an_apv_0_1_0_document_may_carry_an_adapter_string_on_apv_assumption() -> None:
    """D-17 / E.10 item 11 as of apv 0.1.0: the stored 0.1.0 documents were correct for their vocabulary version."""
    assert "pv.linkage.assumption" not in _versioned_linkage("0.1.0", ADAPTER_ON_ASSUMPTION)
    assert "pv.linkage.assumption" not in _versioned_linkage("0.1.0", {"apv:assumption": q("apv:AutoExecution")})
    assert "pv.linkage.assumption" in _versioned_linkage("0.1.0", {"apv:assumption": "nons:Undeclared"})
    # apv:adapterAssumption does not exist in 0.1.0
    assert "pv.linkage.assumption" in _versioned_linkage(
        "0.1.0", {"apv:adapterAssumption": "rope:GuardDeniesBeforeDispatch"})


def test_an_apv_0_2_0_document_states_adapter_assumptions_on_apv_adapter_assumption() -> None:
    assert "pv.linkage.assumption" in _versioned_linkage("0.2.0", ADAPTER_ON_ASSUMPTION)
    assert "pv.linkage.assumption" not in _versioned_linkage(
        "0.2.0", {"apv:adapterAssumption": "rope:GuardDeniesBeforeDispatch"})


@pytest.mark.parametrize("version", [None, "9.9.9"])
def test_an_absent_or_unknown_vocabulary_version_gets_the_current_rule(version: str | None) -> None:
    """The validator has no finding of its own for a missing or unsupported version: the strict 0.2.0 rule applies."""
    assert "pv.linkage.assumption" in _versioned_linkage(version, ADAPTER_ON_ASSUMPTION)
    assert "pv.linkage.assumption" not in _versioned_linkage(
        version, {"apv:adapterAssumption": "rope:GuardDeniesBeforeDispatch"})
