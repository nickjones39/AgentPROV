"""D8 tier 4 on the golden scope (J.3.5 gate D; K.10): every golden derivation passes every tier-4 check in release
mode, and each check fires its specific finding code on a targeted mutation of a real derived document.

Mutations work on the decoded document and are re-serialised as JCS, so the canonical-bytes check stays green and the
finding under test is the only intended defect. Assertion messages carry check ids and finding codes only (R-42).

Two subjects carry the mutations. The golden subject (the smallest golden derivation, migration mode) has the inference
bundles, the raw secondary artefact and the v1 context bundle. Its core holds no ``used`` and no ``wasInformedBy``:
since the D-24 ``_unverified`` twins (regeneration-batch item 3) every v1 ``comm@1`` and ``use_request@1`` is inferred,
and ``adprov.call_id_unique_match`` cites no code, so it stays inferred (D-27 c6). Mutations of core communications and
core tool-call usage run on the synthetic generic subject (``tests/unit/prov/prov_support.py``: ``tst`` D rules, so
those relations are derived and in the core), validated against its own registry outside migration mode.
"""

from __future__ import annotations

import dataclasses
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

_UNIT = Path(__file__).resolve().parents[1] / "unit"
for _path in (_UNIT / "aer", _UNIT / "prov"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import prov_support as ps  # noqa: E402

from agentprov.aer.reader import AerDocument  # noqa: E402
from agentprov.aer.rules import RuleRegistry  # noqa: E402
from agentprov.io.canonical import jcs_bytes  # noqa: E402
from agentprov.prov.engine import derive  # noqa: E402
from agentprov.validate import Tier4Report, validate_prov  # noqa: E402

Doc = dict[str, Any]


def _failures(report: Tier4Report) -> list[tuple[str, str, list[str]]]:
    return [(o.id, o.status, sorted(o.codes())) for o in report.outcomes if o.status in ("fail", "skipped")]


# ============================================================================================================ golden
def test_golden_derivation_passes_tier4(golden_derivations: dict[str, Any], golden_id: str) -> None:
    g = golden_derivations[golden_id]
    report = validate_prov(g.prov_json, g.aer, migration=True)
    assert _failures(report) == []
    assert report.passed and report.ok
    assert report.diagnostics == []
    assert {o.id for o in report.outcomes if o.status == "not_applicable"} == {
        "PV-NE-9", "PV-NE-16", "pv.roundtrip.unqualified_layer"}


def test_golden_validation_is_deterministic(golden_derivations: dict[str, Any]) -> None:
    g = _smallest(golden_derivations)
    first = validate_prov(g.prov_json, g.aer, migration=True).as_json()
    assert validate_prov(g.prov_json, g.aer, migration=True).as_json() == first


def test_roundtrip_disabled_is_skipped_not_passed(golden_derivations: dict[str, Any]) -> None:
    g = _smallest(golden_derivations)
    report = validate_prov(g.prov_json, g.aer, migration=True, roundtrip=False)
    assert report.ok and not report.passed
    assert {o.id for o in report.skipped()} >= {"pv.roundtrip.model_equality", "pv.roundtrip.completeness"}


def test_migration_checks_not_applicable_by_default(golden_derivations: dict[str, Any]) -> None:
    g = _smallest(golden_derivations)
    report = validate_prov(g.prov_json, g.aer, roundtrip=False)
    assert report.get("pv.profiles.migration_context").status == "not_applicable"  # type: ignore[union-attr]
    assert report.get("pv.profiles.migration_generic").status == "not_applicable"  # type: ignore[union-attr]


# ============================================================================================================ helpers
def _smallest(derivations: dict[str, Any]) -> Any:
    return min(derivations.values(), key=lambda g: len(g.prov_json))


def _core(doc: Doc) -> str:
    return next(k for k in doc["bundle"] if k.startswith("xd:bundle.core."))


def _find(doc: Doc, section: str, rule: str | None = None, *, core: bool | None = None,
          where: Callable[[Doc], bool] = lambda _b: True) -> tuple[str, str, Doc]:
    for iri, bundle in doc["bundle"].items():
        if core is not None and iri.startswith("xd:bundle.core.") != core:
            continue
        for key, body in bundle.get(section, {}).items():
            if (rule is None or body.get("apv:rule") == rule) and where(body):
                return iri, key, body
    raise LookupError(f"no {section} {rule}")


def _q(name: str) -> dict[str, str]:
    return {"$": name, "type": "prov:QUALIFIED_NAME"}


@dataclasses.dataclass(frozen=True, slots=True)
class Subject:
    """A derived document to mutate, its AER and the validation settings it is clean under."""

    aer: AerDocument
    prov_json: bytes
    migration: bool
    registry: RuleRegistry | None = None

    def document(self) -> Doc:
        doc = json.loads(self.prov_json)
        assert isinstance(doc, dict)
        return doc

    def validate(self, doc: Doc, aer: AerDocument, *, roundtrip: bool = False) -> Tier4Report:
        return validate_prov(jcs_bytes(doc), aer, migration=self.migration, roundtrip=roundtrip, registry=self.registry)


#: The statements each subject must hold for its mutations: (section, rule, in the core).
GOLDEN_FEATURES: tuple[tuple[str, str | None, bool], ...] = (
    ("used", "aprov.use_context@1", False), ("hadMember", None, True), ("wasInformedBy", "aprov.comm@1", False))
GENERIC_FEATURES: tuple[tuple[str, str | None, bool], ...] = (
    ("wasInformedBy", "aprov.comm@1", True), ("used", "aprov.use_request@1", True))


def _missing(doc: Doc, features: tuple[tuple[str, str | None, bool], ...]) -> list[str]:
    out = []
    for section, rule, core in features:
        try:
            _find(doc, section, rule, core=core)
        except LookupError:
            out.append(f"{'core' if core else 'non-core'} {section} {rule or ''}".rstrip())
    return out


def _subject_doc(derivations: dict[str, Any]) -> Any:
    """The smallest golden derivation with every feature the golden-subject mutations need. Its absence is a failure,
    not a skip: a silent skip hid the D-24 loss of the core features from regeneration-batch item 3 on."""
    def usable(g: Any) -> bool:
        doc = g.document()
        return not _missing(doc, GOLDEN_FEATURES) and any(
            v.get("apv:provPrimary") == "secondary" for k, v in doc.get("entity", {}).items() if k.startswith("raw:"))

    candidates = sorted((g for g in derivations.values() if usable(g)), key=lambda g: len(g.prov_json))
    if not candidates:
        pytest.fail("no golden derivation has every feature the golden-subject mutation tests need")
    return candidates[0]


@pytest.fixture(scope="module")
def golden_subject(golden_derivations: dict[str, Any]) -> Subject:
    g = _subject_doc(golden_derivations)
    return Subject(g.aer, g.prov_json, migration=True)


@pytest.fixture(scope="module")
def generic_subject(tmp_path_factory: pytest.TempPathFactory) -> Subject:
    """The synthetic F.2.6 execution (``tst`` D rules): derived core communications and tool-call usage."""
    registry = ps.registry()
    aer = ps.write_aer(ps.generic_records(), tmp_path_factory.mktemp("tier4-generic") / "g.aer.jsonl")
    subject = Subject(aer, derive(aer, registry=registry).prov_json, migration=False, registry=registry)
    assert _missing(subject.document(), GENERIC_FEATURES) == []
    return subject


def _activities(doc: Doc, bundle: str, type_: str) -> list[str]:
    def types(v: Doc) -> list[Any]:
        t = v.get("prov:type")
        return t if isinstance(t, list) else [t]

    return sorted(k for k, v in doc["bundle"][bundle].get("activity", {}).items() if _q(type_) in types(v))


# ============================================================================================================ mutations
def m_use_context_into_core(doc: Doc, aer: AerDocument) -> tuple[Doc, AerDocument]:
    iri, key, body = _find(doc, "used", "aprov.use_context@1", core=False)
    del doc["bundle"][iri]["used"][key]
    doc["bundle"][_core(doc)].setdefault("used", {})[key] = body
    return doc, aer


def m_influence(doc: Doc, aer: AerDocument) -> tuple[Doc, AerDocument]:
    core = _core(doc)
    _, _, u = _find(doc, "used", "aprov.use_request@1", core=True)
    doc["bundle"][core]["wasInfluencedBy"] = {"x:comm.aaaaaaaaaaaaaaaa": {
        "prov:influencee": u["prov:activity"], "prov:influencer": u["prov:entity"],
        "apv:evidenceClass": _q("apv:Derived"), "apv:rule": "aprov.comm@1"}}
    return doc, aer


def m_self_communication(doc: Doc, aer: AerDocument) -> tuple[Doc, AerDocument]:
    _, _, body = _find(doc, "wasInformedBy", "aprov.comm@1", core=True)
    body["prov:informant"] = body["prov:informed"]
    return doc, aer


def m_drop_source_pointer(doc: Doc, aer: AerDocument) -> tuple[Doc, AerDocument]:
    _, _, body = _find(doc, "used", "aprov.use_request@1", core=True)
    del body["apv:sourcePointer"]
    return doc, aer


def m_unresolved_pointer(doc: Doc, aer: AerDocument) -> tuple[Doc, AerDocument]:
    _, _, body = _find(doc, "used", "aprov.use_request@1", core=True)
    pointer = body["apv:sourcePointer"]
    first = pointer[0] if isinstance(pointer, list) else pointer
    body["apv:sourcePointer"] = first.partition("/")[0] + "/no_such_field"
    return doc, aer


def m_used_activity(doc: Doc, aer: AerDocument) -> tuple[Doc, AerDocument]:
    core = _core(doc)
    _, _, body = _find(doc, "used", "aprov.use_request@1", core=True)
    other = next(a for a in doc["bundle"][core]["activity"] if a != body["prov:activity"])
    doc["bundle"][core]["used"]["x:use_request.aaaaaaaaaaaaaaaa"] = {**body, "prov:entity": other}
    return doc, aer


def m_mention_of_activity(doc: Doc, aer: AerDocument) -> tuple[Doc, AerDocument]:
    core = _core(doc)
    iri, _, _ = _find(doc, "used", "aprov.use_context@1", core=False)
    activity = sorted(doc["bundle"][core]["activity"])[0]
    doc["bundle"][iri].setdefault("mentionOf", {})["_:after.aaaaaaaaaaaaaaaa"] = {
        "prov:specificEntity": activity, "prov:generalEntity": activity, "prov:bundle": core}
    return doc, aer


def m_extra_communication(doc: Doc, aer: AerDocument) -> tuple[Doc, AerDocument]:
    core = _core(doc)
    _, _, body = _find(doc, "wasInformedBy", "aprov.comm@1", core=True)
    scopes = _activities(doc, core, "apv:Run")
    doc["bundle"][core]["wasInformedBy"]["x:comm.aaaaaaaaaaaaaaaa"] = {**body, "prov:informed": scopes[0]}
    return doc, aer


def m_remove_communication(doc: Doc, aer: AerDocument) -> tuple[Doc, AerDocument]:
    core = _core(doc)
    _, key, _ = _find(doc, "wasInformedBy", "aprov.comm@1", core=True)
    del doc["bundle"][core]["wasInformedBy"][key]
    if not doc["bundle"][core]["wasInformedBy"]:
        del doc["bundle"][core]["wasInformedBy"]
    return doc, aer


def m_remove_inference_communication(doc: Doc, aer: AerDocument) -> tuple[Doc, AerDocument]:
    iri, key, _ = _find(doc, "wasInformedBy", "aprov.comm@1", core=False)
    del doc["bundle"][iri]["wasInformedBy"][key]
    return doc, aer


def m_inference_communication_into_core(doc: Doc, aer: AerDocument) -> tuple[Doc, AerDocument]:
    iri, key, body = _find(doc, "wasInformedBy", "aprov.comm@1", core=False)
    del doc["bundle"][iri]["wasInformedBy"][key]
    doc["bundle"][_core(doc)].setdefault("wasInformedBy", {})[key] = {k: v for k, v in body.items() if k != "apv:method"} | {
        "apv:evidenceClass": _q("apv:Derived")}
    return doc, aer


def m_relation_time(doc: Doc, aer: AerDocument) -> tuple[Doc, AerDocument]:
    _, _, body = _find(doc, "used", "aprov.use_request@1", core=True)
    body["prov:time"] = "2026-10-08T00:00:00+00:00"
    return doc, aer


def m_primary_source_secondary(doc: Doc, aer: AerDocument) -> tuple[Doc, AerDocument]:
    key, body = next((k, v) for k, v in doc["wasDerivedFrom"].items() if v.get("apv:rule") == "aprov.t_primary@1")
    doc["wasDerivedFrom"]["xd:t_primary.aaaaaaaaaaaaaaaa"] = {**body, "prov:type": _q("prov:PrimarySource")}
    return doc, aer


def m_unsorted_multi_value(doc: Doc, aer: AerDocument) -> tuple[Doc, AerDocument]:
    for bundle in doc["bundle"].values():
        for section in bundle.values():
            for body in section.values():
                for attr, value in body.items():
                    if isinstance(value, list) and len(value) > 1:
                        body[attr] = list(reversed(value))
                        return doc, aer
    raise LookupError("no multi-valued attribute")


def m_tool_uses_message(doc: Doc, aer: AerDocument) -> tuple[Doc, AerDocument]:
    core = _core(doc)
    _, _, body = _find(doc, "used", "aprov.use_request@1", core=True)
    message = next(k for k, v in doc["bundle"][core]["entity"].items() if v.get("apv:rule") == "aprov.n_message@2")
    doc["bundle"][core]["used"]["x:use_request.aaaaaaaaaaaaaaaa"] = {**body, "prov:entity": message}
    return doc, aer


def m_inferred_in_core(doc: Doc, aer: AerDocument) -> tuple[Doc, AerDocument]:
    _, _, body = _find(doc, "used", "aprov.use_request@1", core=True)
    body["apv:evidenceClass"] = _q("apv:Inferred")
    return doc, aer


def m_time_without_aer(doc: Doc, aer: AerDocument) -> tuple[Doc, AerDocument]:
    core = _core(doc)
    te = _activities(doc, core, "apv:ToolExecution")[0]
    doc["bundle"][core]["activity"][te]["prov:startTime"] = "2026-10-08T00:00:00+00:00"
    return doc, aer


def m_sentinel_time(doc: Doc, aer: AerDocument) -> tuple[Doc, AerDocument]:
    core = _core(doc)
    te = _activities(doc, core, "apv:ToolExecution")[0]
    doc["bundle"][core]["activity"][te]["prov:endTime"] = "0"
    return doc, aer


def m_statement_id(doc: Doc, aer: AerDocument) -> tuple[Doc, AerDocument]:
    core = _core(doc)
    _, key, body = _find(doc, "used", "aprov.use_request@1", core=True)
    del doc["bundle"][core]["used"][key]
    doc["bundle"][core]["used"]["x:use_model." + key.rsplit(".", 1)[1]] = body
    return doc, aer


def m_rule_unknown(doc: Doc, aer: AerDocument) -> tuple[Doc, AerDocument]:
    _, _, body = _find(doc, "used", "aprov.use_request@1", core=True)
    body["apv:rule"] = "aprov.use_request@9"
    return doc, aer


def m_existence(doc: Doc, aer: AerDocument) -> tuple[Doc, AerDocument]:
    core = _core(doc)
    derived = {k for k, v in doc["bundle"][core]["activity"].items() if v["apv:evidenceClass"] == _q("apv:Derived")}
    _, _, body = _find(doc, "wasAssociatedWith", core=True, where=lambda b: b["prov:activity"] in derived)
    body["apv:evidenceClass"] = _q("apv:Observed")
    return doc, aer


def m_generic_use(doc: Doc, aer: AerDocument) -> tuple[Doc, AerDocument]:
    core = _core(doc)
    _, _, body = _find(doc, "used", "aprov.use_request@1", core=True)
    doc["bundle"][core]["used"]["x:g_use.aaaaaaaaaaaaaaaa"] = {
        **{k: v for k, v in body.items() if k != "prov:role"}, "apv:rule": "aprov.g_use@1"}
    return doc, aer


def m_generic_use_on_migration_aer(doc: Doc, aer: AerDocument) -> tuple[Doc, AerDocument]:
    """A G-USE in the core of a migration AER, built from an inferred tool-call usage (the golden core has none)."""
    _, _, body = _find(doc, "used", "aprov.use_request@1", core=False)
    doc["bundle"][_core(doc)].setdefault("used", {})["x:g_use.aaaaaaaaaaaaaaaa"] = {
        **{k: v for k, v in body.items() if k not in ("prov:role", "apv:method")}, "apv:rule": "aprov.g_use@1",
        "apv:evidenceClass": _q("apv:Derived")}
    return doc, aer


def m_vocabulary(doc: Doc, aer: AerDocument) -> tuple[Doc, AerDocument]:
    _, _, body = _find(doc, "used", "aprov.use_request@1", core=True)
    body["apv:notATerm"] = 1
    return doc, aer


def m_drop_premise(doc: Doc, aer: AerDocument) -> tuple[Doc, AerDocument]:
    _, _, body = _find(doc, "wasInformedBy", "aprov.comm@1", core=True)
    del body["apv:premise"]
    return doc, aer


def m_member_not_request(doc: Doc, aer: AerDocument) -> tuple[Doc, AerDocument]:
    core = _core(doc)
    _, _, body = _find(doc, "hadMember", core=True)
    collection = body["prov:collection"]
    text = next(k for k, v in doc["bundle"][core]["entity"].items()
                if v.get("apv:rule") == "aprov.n_part@1" and _q("apv:ToolCallRequest") not in v.get("prov:type", []))
    doc["bundle"][core]["hadMember"]["_:member_request.aaaaaaaaaaaaaaaa"] = {
        "prov:collection": collection, "prov:entity": text}
    return doc, aer


def m_modify_decision(doc: Doc, aer: AerDocument) -> tuple[Doc, AerDocument]:
    _, _, body = _find(doc, "used", "aprov.use_request@1", core=True)
    part = body["prov:entity"].removeprefix("x:")
    subject = part[: part.rindex("-")] + "#" + part[part.rindex("-") + 1:]
    decision = {"k": "decision", "id": "dc99", "ev": "O", "verdict": "modify", "subject": subject}
    records = [*aer.records, decision]
    index = {str(r.get("id")): r for r in records if isinstance(r.get("id"), str)}
    return doc, dataclasses.replace(aer, records=records, _index=index)


def m_empty_inference_bundle(doc: Doc, aer: AerDocument) -> tuple[Doc, AerDocument]:
    iri, _, _ = _find(doc, "used", "aprov.use_context@1", core=False)
    empty = iri.rsplit(".", 1)[0].replace("adprov-context_is_prefix-v1", "adprov-other-v1") + ".aaaaaaaaaaaaaaaaaaaaaaaaaa"
    doc["bundle"][empty] = {}
    return doc, aer


def m_reserved_prefix(doc: Doc, aer: AerDocument) -> tuple[Doc, AerDocument]:
    doc["prefix"]["prov"] = "http://www.w3.org/ns/prov#"
    return doc, aer


def m_basis_not_cited(doc: Doc, aer: AerDocument) -> tuple[Doc, AerDocument]:
    _, _, body = _find(doc, "used", "aprov.use_request@1", core=True, where=lambda b: "apv:basisRule" in b)
    body["apv:basisRule"] = "adprov.not_cited_here@1"
    return doc, aer


def m_method_missing(doc: Doc, aer: AerDocument) -> tuple[Doc, AerDocument]:
    _, _, body = _find(doc, "used", "aprov.use_context@1", core=False)
    del body["apv:method"]
    return doc, aer


def m_activity_conflation(doc: Doc, aer: AerDocument) -> tuple[Doc, AerDocument]:
    core = _core(doc)
    te = _activities(doc, core, "apv:ToolExecution")[0]
    doc["bundle"][core]["activity"][te]["prov:type"] = [_q("apv:ModelInvocation"), _q("apv:ToolExecution")]
    return doc, aer


#: (mutation, subject, check id, finding code); the subject is the fixture ``<subject>_subject``.
MUTATIONS: list[tuple[Callable[[Doc, AerDocument], tuple[Doc, AerDocument]], str, str, str]] = [
    (m_use_context_into_core, "golden", "pv.profiles.migration_context", "pv.profiles.migration_context"),
    (m_use_context_into_core, "golden", "PV-NE-11", "pv.profiles.inferred_in_core"),
    (m_use_context_into_core, "golden", "pv.linkage.class_bundle", "pv.linkage.class_bundle"),
    (m_influence, "generic", "PV-NE-5", "pv.profiles.influence"),
    (m_self_communication, "generic", "pv.constraints.self_communication", "pv.constraints.self_communication"),
    (m_drop_source_pointer, "generic", "pv.linkage.source_pointer", "pv.linkage.pointer_missing"),
    (m_unresolved_pointer, "generic", "pv.linkage.source_pointer", "prov.link.unresolved"),
    (m_used_activity, "generic", "PV-NE-19", "pv.prov_structure.used_activity"),
    (m_used_activity, "generic", "pv.constraints.typing", "pv.constraints.disjoint"),
    (m_mention_of_activity, "golden", "PV-NE-19", "pv.prov_structure.mention_not_entity"),
    (m_extra_communication, "generic", "PV-NE-7", "pv.profiles.closure_extra"),
    (m_remove_communication, "generic", "PV-NE-7", "pv.profiles.closure_missing"),
    (m_remove_inference_communication, "golden", "PV-NE-7", "pv.profiles.closure_missing"),
    (m_inference_communication_into_core, "golden", "PV-NE-7", "pv.profiles.closure_extra"),
    (m_inference_communication_into_core, "golden", "pv.linkage.premise", "pv.linkage.premise_scope"),
    (m_relation_time, "generic", "PV-NE-6", "pv.profiles.relation_time"),
    (m_primary_source_secondary, "golden", "PV-NE-20", "pv.profiles.primary_source"),
    (m_unsorted_multi_value, "golden", "pv.prov_structure.values", "pv.prov_structure.multi_value_order"),
    (m_tool_uses_message, "generic", "PV-NE-2", "pv.profiles.tool_usage"),
    (m_inferred_in_core, "generic", "PV-NE-11", "pv.profiles.inferred_in_core"),
    (m_time_without_aer, "golden", "PV-NE-6", "pv.profiles.time_without_aer"),
    (m_sentinel_time, "golden", "PV-NE-6", "pv.profiles.sentinel_time"),
    (m_statement_id, "generic", "pv.prov_structure.identifiers", "pv.prov_structure.statement_id"),
    (m_rule_unknown, "generic", "pv.linkage.rule", "pv.linkage.rule_unknown"),
    (m_existence, "golden", "pv.linkage.existence", "pv.linkage.existence"),
    (m_generic_use, "generic", "PV-NE-21", "pv.profiles.generic_beyond_aer"),
    (m_generic_use_on_migration_aer, "golden", "pv.profiles.migration_generic", "pv.profiles.migration_generic"),
    (m_vocabulary, "generic", "pv.profiles.vocabulary", "pv.profiles.vocabulary"),
    (m_drop_premise, "generic", "pv.linkage.premise", "pv.linkage.premise_missing"),
    (m_drop_premise, "generic", "PV-NE-7", "pv.profiles.closure_premise"),
    (m_member_not_request, "golden", "pv.profiles.membership", "pv.profiles.membership"),
    (m_modify_decision, "generic", "PV-NE-18", "pv.profiles.modified_request_used"),
    (m_empty_inference_bundle, "golden", "pv.prov_structure.bundles", "pv.prov_structure.empty_bundle"),
    (m_reserved_prefix, "golden", "pv.prov_structure.prefixes", "pv.prov_structure.reserved_prefix"),
    (m_basis_not_cited, "generic", "pv.linkage.basis_rule", "pv.linkage.basis_not_cited"),
    (m_method_missing, "golden", "pv.linkage.method", "pv.linkage.method_missing"),
    (m_activity_conflation, "golden", "PV-NE-14", "pv.profiles.activity_conflation"),
]


@pytest.mark.parametrize(("mutate", "subject", "check_id", "code"), MUTATIONS,
                         ids=[f"{m.__name__.removeprefix('m_')}-{c.rsplit('.', 1)[-1]}" for m, _, _, c in MUTATIONS])
def test_mutation_fires_its_finding(request: pytest.FixtureRequest, mutate: Any, subject: str, check_id: str,
                                    code: str) -> None:
    s: Subject = request.getfixturevalue(f"{subject}_subject")
    doc, aer = mutate(s.document(), s.aer)
    report = s.validate(doc, aer)
    found = report.get(check_id)
    assert found is not None, check_id
    assert found.status == "fail", (check_id, found.status)
    assert code in found.codes(), (check_id, sorted(found.codes()))
    assert not report.ok


@pytest.mark.parametrize("subject", ["golden", "generic"])
def test_unmutated_subject_is_clean(request: pytest.FixtureRequest, subject: str) -> None:
    s: Subject = request.getfixturevalue(f"{subject}_subject")
    report = s.validate(s.document(), s.aer)
    assert report.ok, _failures(report)


def test_roundtrip_completeness_catches_a_non_isoformat_time(golden_subject: Subject) -> None:
    """Negative control (C3, C8): the library rewrites a ``Z`` time, which only the typed completeness check sees."""
    doc = golden_subject.document()
    t_derive = next(k for k, v in doc["activity"].items() if v.get("apv:rule") == "aprov.t_derive@1")
    doc["activity"][t_derive]["prov:startTime"] = "2026-10-08T00:00:00Z"
    report = golden_subject.validate(doc, golden_subject.aer, roundtrip=True)
    completeness = report.get("pv.roundtrip.completeness")
    assert completeness is not None and "pv.roundtrip.literal_form" in completeness.codes()
    assert report.get("pv.roundtrip.model_equality").status == "pass"  # type: ignore[union-attr]
    assert "pv.profiles.time_without_aer" in report.codes()
