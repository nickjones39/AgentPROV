"""Profile rules of ``agentprov-prov/0.1``: the never-emit checks ``PV-NE-1`` ... ``PV-NE-21`` that are decidable on the
output (with its AER where needed), the rule/section table, membership (AD-19(a)), the vocabulary and the gate-D
migration checks (D8 tier 4; EF E.1.3-E.1.6, E.2, E.4; J.3.5; K.10 ``test_never_emit_props.py``).

The Inference-6 check (``PV-NE-7``) recomputes the closure independently from the ``used`` and ``wasGeneratedBy``
statements of the output, per routing scope, and asserts equality, not inclusion (E.1.6 item 4): the core holds
exactly ``C(∅)``; the inference bundle of method set ``M`` holds exactly ``C(M)`` minus ``C(M')`` for every occurring
``M' ⊊ M``; each statement's class, ``apv:viaEntity`` and ``apv:premise`` are those of its best witnesses.

``PV-NE-10`` also enforces the allowed forms of assessment bundles (E.7.2 item 5): only entity, activity and agent
declarations (mentions, ``apv:Assessment`` entities and the bundle's evaluation activity ``x:assess.<profile-slug>``),
``wasGeneratedBy`` of an assessment by that activity, ``wasAssociatedWith`` of that activity with the engine
``sw:agentprov`` and ``mentionOf``; every statement under an ``aprov.a_*`` assessment rule; no subject re-declared. Outside
assessment bundles no ``aprov.a_*`` assessment rule, policy claim or SEM label property appears.
``pv.profiles.mentions`` checks mention cardinality (AD-19(b)): each mention entity occurs in exactly one ``mentionOf``,
whose ``prov:bundle`` declares the subject, and an assessment bundle holds one mention per (subject, annotation).

``PV-NE-19`` lives in :mod:`agentprov.validate.prov_structure` (it is a structural R-21 check). ``PV-NE-9`` and
``PV-NE-16`` are not decidable on the output beyond the rule/section table and are reported ``not_applicable`` with the
reason.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any, Final

from agentprov.aer.evidence import is_prefix
from agentprov.aer.reader import AerDocument
from agentprov.prov.serialise.time import prov_time
from agentprov.prov.specs import ProvSpec, load_spec
from agentprov.prov.vocab import CLASSES, INDIVIDUALS, PROPERTIES
from agentprov.validate._provdoc import RANK, RELATION_ARGS, ProvView, St, as_list, qname_value, qname_values
from agentprov.validate.linkage import CAPTURE_PROFILE_NODE, CAPTURE_PROFILE_RULE, is_capture_profile, resolve_pointer
from agentprov.validate.tiers import CheckOutcome, Finding, outcome

__all__ = ["ALLOWED_RULES", "GENERIC_RULES", "check"]

M: Final = "pv.profiles"


def _r(*names: str) -> frozenset[str]:
    return frozenset(f"aprov.{n}@1" for n in names)


#: aprov.a_label@2, a_payload@2 and a_author@2 (D-930) supersede @1, which stored documents still cite
A_RULES_V2: Final = frozenset({"aprov.a_label@2", "aprov.a_payload@2", "aprov.a_author@2"})
#: Section -> the engine rules that may emit it (E.1.3, E.1.4). Mentions and assessments (split attributes, E.1.5
#: item 5) are entities and may carry any catalogue rule.
ALLOWED_RULES: Final[Mapping[str, frozenset[str]]] = {
    # aprov.n_message@2 (D-621) supersedes @1, which stored documents still cite
    "entity": _r("n_header", "n_model", "n_message", "n_part", "n_state", "n_fixture", "n_judgement", "n_artefact",
                 "n_capture_profile", "n_gap", "decision", "state_patch") | {"aprov.n_message@2"},
    "activity": _r("n_scope", "n_model_call", "n_tool_execution", "n_decision", "g_act", "outcome", "a_evaluation"),
    "agent": _r("n_actor", "n_model"),
    "used": _r("use_context", "use_model", "use_tools", "use_request", "decision", "env_pass", "env_call", "outcome",
               "g_use"),
    "wasGeneratedBy": _r("gen_message", "gen_part", "gen_result", "env_pass", "env_call", "state_patch", "outcome",
                         "g_gen", "a_label", "a_payload", "a_author", "a_exposure", "a_taint") | A_RULES_V2,
    "wasInformedBy": _r("comm"),
    "wasStartedBy": _r("start_tool", "authorise", "rerun", "spawn"),
    "wasInvalidatedBy": _r("env_call"),
    "wasDerivedFrom": _r("decision", "env_pass", "env_call", "state_patch", "inj_placement", "outcome"),
    "wasAttributedTo": _r("attr_message", "attr_fixture", "outcome"),
    "wasAssociatedWith": _r("assoc_model_call", "assoc_tool", "assoc_scope", "decision", "outcome", "g_assoc",
                            "a_evaluation"),
    "actedOnBehalfOf": _r("assoc_tool", "deleg_user"),
}
GENERIC_RULES: Final = _r("g_act", "g_use", "g_gen", "g_assoc")
#: The rules of assessment bundles (E.7); they emit nothing elsewhere.
ASSESSMENT_RULES: Final = _r("a_evaluation", "a_label", "a_payload", "a_author", "a_exposure", "a_taint") | A_RULES_V2
#: Policy claims (E.4.5) that only assessment bundles state (NE-10).
POLICY_CLAIMS: Final = frozenset({"apv:ExposedTo", "apv:PotentiallyInfluencedBy", "apv:ContainsPayload",
                                  "apv:QuotesAuthoredContent"})
#: SEM label properties of mentions and assessments (E.7.1), stated only in assessment bundles.
LABEL_PROPERTIES: Final = frozenset({
    "apv:integrity", "apv:securityRole", "apv:sourceChannel", "apv:declaredSender", "apv:annotationType",
    "apv:annotationValue", "apv:markerStatus", "apv:annotationId", "apv:outcomeClaim", "apv:outcomeHolds",
    "apv:outcomeScore", "apv:outcomeScale", "apv:authorName", "apv:policy",
})  # fmt: skip
ASSESS_ACTIVITY_RE: Final = re.compile(r"xd:bundle\.assess\.([a-z0-9_\-]+)\.[a-z2-7]{26}")
#: Attribute and assessment rules: never the rule of a PROV relation (NE-1, NE-10).
NON_RELATION_RULES: Final = _r("after", "status", "part_of", "a_sent_transform")
#: Occurrence classes of activities; an activity carries exactly one (NE-14).
OCCURRENCE_CLASSES: Final = frozenset({
    "apv:ModelInvocation", "apv:CacheRead", "apv:ToolExecution", "apv:Decision", "apv:CheckerRun",
    "apv:HarnessRuleEvaluation", "apv:GenericActivity", "apv:Run", "apv:Pass", "apv:AgentInvocation",
    "apv:SubagentInvocation", "apv:Step", "apv:PolicyEvaluation",
})  # fmt: skip
SPECIALISED_ACTIVITY: Final = frozenset(
    {"apv:ModelInvocation", "apv:CacheRead", "apv:ToolExecution", "apv:Decision", "apv:CheckerRun"}
)
#: SEM-dependent interpretation properties that never appear in the core (NE-17).
SEM_PROPERTIES: Final = frozenset({"apv:integrity", "apv:markerStatus", "apv:claim", "apv:annotationId",
                                   "apv:annotationType", "apv:annotationValue", "apv:securityRole"})
TIME_ATTRS: Final = {"prov:startTime": "start", "prov:endTime": "end",
                     "apv:startTimeLexical": "start", "apv:endTimeLexical": "end"}
PRIMARY: Final = frozenset({"native", "byte_derived"})
AER_NODE_RE: Final = re.compile(r"x:([a-z][a-z0-9_]{0,31})(?:-([0-9]+))?(?:\..*)?")
CONTEXT_METHOD: Final = "adprov.context_is_prefix@1"


def check(view: ProvView, aer: AerDocument, *, migration: bool = False, spec: ProvSpec | None = None) -> list[CheckOutcome]:
    spec = spec or load_spec()
    ctx = _Ctx(view, aer)
    na_reason = "not decidable on the output beyond the rule/section table (PV-NE-1, pv.profiles.rule_section)"
    out = [
        outcome(f"{M}.rule_section", _rule_section(ctx, spec)),
        outcome("PV-NE-1", _ne1(ctx)),
        outcome("PV-NE-2", _ne2(ctx)),
        outcome("PV-NE-3", _ne3(ctx)),
        outcome("PV-NE-4", _ne4(ctx)),
        outcome("PV-NE-5", _ne5(ctx)),
        outcome("PV-NE-6", _ne6(ctx)),
        outcome("PV-NE-7", _ne7(ctx)),
        outcome("PV-NE-8", _ne8(ctx)),
        CheckOutcome("PV-NE-9", "not_applicable", reason="negative facts have no PROV or apv form; " + na_reason),
        outcome("PV-NE-10", _ne10(ctx)),
        outcome("PV-NE-11", _ne11(ctx)),
        outcome("PV-NE-12", _ne12(ctx)),
        outcome("PV-NE-13", _ne13(ctx)),
        outcome("PV-NE-14", _ne14(ctx)),
        outcome("PV-NE-15", _ne15(ctx)),
        CheckOutcome("PV-NE-16", "not_applicable", reason="non-PROV inference rules leave no trace; " + na_reason),
        outcome("PV-NE-17", _ne17(ctx)),
        outcome("PV-NE-18", _ne18(ctx)),
        outcome("PV-NE-20", _ne20(ctx)),
        outcome("PV-NE-21", _ne21(ctx)),
        outcome(f"{M}.membership", _membership(ctx)),
        outcome(f"{M}.mentions", _mentions(ctx)),
        outcome(f"{M}.vocabulary", _vocabulary(ctx)),
    ]
    if migration:
        out.append(outcome(f"{M}.migration_context", _migration_context(ctx)))
        out.append(outcome(f"{M}.migration_generic", _migration_generic(ctx)))
    else:
        reason = "migration checks apply to the v1-import AERs of gate D only (migration=False)"
        out.append(CheckOutcome(f"{M}.migration_context", "not_applicable", reason=reason))
        out.append(CheckOutcome(f"{M}.migration_generic", "not_applicable", reason=reason))
    return out


# ============================================================================================================ context
class _Ctx:
    def __init__(self, view: ProvView, aer: AerDocument) -> None:
        self.view = view
        self.aer = aer
        self.types: dict[str, set[str]] = {}
        for k, s in view.elements.items():
            self.types.setdefault(k, set()).update(s.types)
        self.relations = [s for s in view.bundle_statements() if not s.is_element]

    def node(self, aer_id: str) -> str:
        return "x:" + aer_id.replace("#", "-")

    def aer_id(self, key: str) -> str | None:
        """The AER id behind a node name ``x:L(id)[.<q>...]`` (E.1.2), or ``None``."""
        m = AER_NODE_RE.fullmatch(key)
        if m is None:
            return None
        return m.group(1) + (f"#{m.group(2)}" if m.group(2) is not None else "")

    def record(self, aer_id: str | None) -> dict[str, Any] | None:
        if aer_id is None:
            return None
        if "#" in aer_id:
            return self.aer.part(aer_id)
        return self.aer.get(aer_id)

    def present(self, record: Mapping[str, Any] | None, ptr: str) -> bool:
        if record is None:
            return False
        value: Any = record
        for token in ptr.split("/")[1:]:
            token = token.replace("~1", "/").replace("~0", "~")
            if isinstance(value, dict) and token in value:
                value = value[token]
            elif isinstance(value, list) and token.isascii() and token.isdigit() and int(token) < len(value):
                value = value[int(token)]
            else:
                return False
        return self.unk(record, ptr) is None

    @staticmethod
    def unk(record: Mapping[str, Any], ptr: str) -> str | None:
        unk = record.get("unk")
        if not isinstance(unk, dict):
            return None
        for key, reason in unk.items():
            if isinstance(key, str) and is_prefix(key, ptr):
                return str(reason)
        return None

    def of(self, *sections: str) -> Iterator[St]:
        for s in self.relations:
            if s.section in sections:
                yield s


# ============================================================================================================ rule table
def _rule_section(ctx: _Ctx, spec: ProvSpec) -> Iterator[Finding]:
    for s in ctx.view.bundle_statements():
        rule = s.rule
        if not s.is_identified or rule is None:
            continue
        if s.section == "entity" and (".mn-" in s.key or s.key.startswith("x:as-")):
            if rule not in spec.rules:
                yield Finding(f"{M}.rule_section", s.where, f"{rule} is not a catalogue rule")
            continue
        allowed = ALLOWED_RULES.get(s.section)
        if allowed is None or rule not in allowed:
            yield Finding(f"{M}.rule_section", s.where, f"{rule} does not emit {s.section}")
        elif (rule == CAPTURE_PROFILE_RULE) != (s.key == CAPTURE_PROFILE_NODE) or (
                rule == CAPTURE_PROFILE_RULE and not is_capture_profile(ctx.view, s)):
            # D-621: the rule emits only the core entity x:capture-profile typed apv:CaptureProfile (E.10), which no other
            # rule emits; its pointer exemption (pv.linkage.source_pointer) belongs to that node alone
            yield Finding(f"{M}.rule_section", s.where,
                          f"{CAPTURE_PROFILE_RULE} emits {CAPTURE_PROFILE_NODE} (apv:CaptureProfile, core) and nothing else")


def _ne1(ctx: _Ctx) -> Iterator[Finding]:
    for s in ctx.of("used", "wasInformedBy"):
        if s.rule not in ALLOWED_RULES[s.section]:
            yield Finding(f"{M}.ne1_rule", s.where, f"{s.section} under {s.rule} (not an edge rule)")


# ============================================================================================================ NE-2/3/4/5
def _ne2(ctx: _Ctx) -> Iterator[Finding]:
    for s in ctx.of("used"):
        te = s.arg("prov:activity")
        if te is None or "apv:ToolExecution" not in ctx.types.get(te, set()):
            continue
        role = qname_values(s.attrs.get("prov:role"))
        entity = s.arg("prov:entity")
        if s.rule == "aprov.use_request@1" and role == ["apv:CallRequestInput"]:
            record = ctx.record(ctx.aer_id(te))
            call = record.get("call") if record is not None else None
            if isinstance(call, str) and entity != ctx.node(call):
                yield Finding(f"{M}.tool_usage", s.where, "a tool execution uses a request other than its own")
            continue
        if s.rule == "aprov.env_call@1" and role == ["apv:InitialState"]:
            continue
        yield Finding(f"{M}.tool_usage", s.where, f"a tool execution uses {entity} under {s.rule} (NE-2)")


def _ne3(ctx: _Ctx) -> Iterator[Finding]:
    for s in ctx.of("wasDerivedFrom"):
        if s.rule not in ALLOWED_RULES["wasDerivedFrom"]:
            yield Finding(f"{M}.derivation_rule", s.where, f"wasDerivedFrom under {s.rule} (NE-3)")


def _ne4(ctx: _Ctx) -> Iterator[Finding]:
    for s in ctx.of("wasAttributedTo"):
        entity, agent = s.arg("prov:entity"), s.arg("prov:agent")
        if entity is None or agent is None:
            continue
        types = ctx.types.get(entity, set())
        if "apv:MessagePart" in types:
            yield Finding(f"{M}.composite_attribution", s.where, "attribution of a message part (NE-4)")
            continue
        record = ctx.record(ctx.aer_id(entity))
        actor = record.get("actor") if record is not None else None
        if not isinstance(actor, str) or agent != ctx.node(actor):
            yield Finding(f"{M}.composite_attribution", s.where, "attributed agent is not the record's actor (NE-4)")
            continue
        if s.rule == "aprov.attr_message@1" and record is not None and ctx.present(record, "/generated_by"):
            gen = ctx.aer.get(str(record["generated_by"]))
            if gen is None or gen.get("k") != "actor":
                yield Finding(f"{M}.composite_attribution", s.where, "a generated message attributed to an agent (NE-4)")


def _ne5(ctx: _Ctx) -> Iterator[Finding]:
    for s in ctx.view.all_statements():
        if s.section == "wasInfluencedBy":
            yield Finding(f"{M}.influence", s.where, "wasInfluencedBy is never emitted (NE-5)")


# ============================================================================================================ NE-6 times
def _ne6(ctx: _Ctx) -> Iterator[Finding]:
    for s in ctx.view.all_statements():
        if not s.is_element:
            if "prov:time" in s.attrs:
                yield Finding(f"{M}.relation_time", s.where, "relations carry no time in agentprov-prov/0.1")
            continue
        for attr, end in TIME_ATTRS.items():
            if attr not in s.attrs:
                continue
            value = s.attrs[attr]
            if value in ("0", "", 0) or (isinstance(value, dict) and value.get("$") in ("0", "")):
                yield Finding(f"{M}.sentinel_time", s.where, f"{attr} is a sentinel")
                continue
            if s.section != "activity":
                yield Finding(f"{M}.time_on_non_activity", s.where, f"{attr} on an {s.section}")
                continue
            aer_id = ctx.aer_id(s.key) if s.bundle is not None and "." not in s.key else None
            record = ctx.record(aer_id)
            if record is None:
                yield Finding(f"{M}.time_without_aer", s.where, f"{attr} on a node without an AER t value")
                continue
            if not _time_matches(ctx, record, attr, end, value):
                yield Finding(f"{M}.time_without_aer", s.where, f"{attr} is not the AER /t/{end} value")


def _time_matches(ctx: _Ctx, record: Mapping[str, Any], attr: str, end: str, value: Any) -> bool:
    t = record.get("t")
    if not isinstance(t, dict):
        return False
    if ctx.present(record, f"/t/{end}"):
        iso = prov_time(t[end])
        if attr.startswith("prov:"):
            return iso is not None and value == iso
        return iso is None and value == t[end]
    if ctx.present(record, f"/t/{end}_naive"):
        return attr.startswith("apv:") and value == t[f"{end}_naive"]
    return False


# ============================================================================================================ NE-7 closure
@dataclass(frozen=True, slots=True)
class _Witness:
    u: str
    g: str
    entity: str
    methods: frozenset[str]
    cls: int


def _ne7(ctx: _Ctx) -> Iterator[Finding]:
    view = ctx.view
    activities = {k for k, s in view.elements.items() if s.section == "activity"}
    gens: dict[str, list[St]] = {}
    for s in ctx.of("wasGeneratedBy"):
        if (e := s.arg("prov:entity")) is not None:
            gens.setdefault(e, []).append(s)
    witnesses: dict[tuple[str, str], list[_Witness]] = {}
    for u in ctx.of("used"):
        a2, e = u.arg("prov:activity"), u.arg("prov:entity")
        mu = view.methods(u.bundle)
        if a2 is None or e is None or a2 not in activities or mu is None or u.cls is None:
            continue
        for g in gens.get(e, ()):
            a1 = g.arg("prov:activity")
            mg = view.methods(g.bundle)
            if a1 is None or a1 == a2 or a1 not in activities or mg is None or g.cls is None:
                continue
            witnesses.setdefault((a2, a1), []).append(_Witness(u.key, g.key, e, mu | mg, min(RANK[u.cls], RANK[g.cls])))
    occurring = [b.methods for b in view.inference() if b.methods is not None]

    def closure(methods: frozenset[str]) -> set[tuple[str, str]]:
        return {pair for pair, ws in witnesses.items() if any(w.methods <= methods for w in ws)}

    asserted_anywhere: set[tuple[str, str]] = set()
    for b in view.bundles.values():
        if b.methods is None:
            continue
        expected = closure(b.methods)
        for smaller in [frozenset[str](), *occurring]:
            if smaller < b.methods:
                expected -= closure(smaller)
        asserted: dict[tuple[str, str], list[St]] = {}
        for s in b.statements:
            if s.section == "wasInformedBy" and (a2 := s.arg("prov:informed")) and (a1 := s.arg("prov:informant")):
                asserted.setdefault((a2, a1), []).append(s)
        asserted_anywhere |= set(asserted)
        for pair, stmts in sorted(asserted.items()):
            if len(stmts) > 1:
                yield Finding(f"{M}.closure_duplicate", f"{b.iri}:{pair[0]}<-{pair[1]}", f"{len(stmts)} statements")
            if pair not in expected:
                for s in stmts:
                    yield Finding(f"{M}.closure_extra", s.where, f"{pair[0]} <- {pair[1]} is not in this bundle's closure")
                continue
            for s in stmts:
                yield from _comm_attributes(s, b.kind == "core", b.methods, witnesses[pair])
        for pair in sorted(expected - set(asserted)):
            yield Finding(f"{M}.closure_missing", b.iri, f"{pair[0]} <- {pair[1]} is entailed but not asserted")
    for pair in sorted(set(witnesses) - asserted_anywhere):
        yield Finding(f"{M}.closure_incomplete", "document", f"{pair[0]} <- {pair[1]} asserted in no bundle")


def _comm_attributes(s: St, core: bool, methods: frozenset[str], ws: list[_Witness]) -> Iterator[Finding]:
    inside = [w for w in ws if w.methods <= methods]
    if core:
        best = min(max(w.cls for w in inside), RANK["D"])
        chosen = [w for w in inside if w.cls >= best]
        want_cls = "D" if best == RANK["D"] else "I" if best == RANK["I"] else "O"
    else:
        chosen, want_cls = inside, "I"
    if s.cls != want_cls:
        yield Finding(f"{M}.closure_class", s.where, f"class {s.cls}, the best witness gives {want_cls}")
    premises = set(qname_values(s.attrs.get("apv:premise")))
    if premises != {w.u for w in chosen} | {w.g for w in chosen}:
        yield Finding(f"{M}.closure_premise", s.where, "apv:premise differs from the best witnesses")
    via = set(qname_values(s.attrs.get("apv:viaEntity")))
    if via != {w.entity for w in chosen}:
        yield Finding(f"{M}.closure_premise", s.where, "apv:viaEntity differs from the best witnesses")


# ============================================================================================================ NE-8..15
def _ne8(ctx: _Ctx) -> Iterator[Finding]:
    for s in ctx.of("used"):
        e = s.arg("prov:entity")
        if s.rule == "aprov.use_context@1" and e is not None and "apv:Message" not in ctx.types.get(e, set()):
            yield Finding(f"{M}.member_usage", s.where, "context usage of a non-message entity (NE-8)")


def _ne10(ctx: _Ctx) -> Iterator[Finding]:
    for s in ctx.view.bundle_statements():
        if s.is_element or not s.is_identified:
            continue
        if s.rule in NON_RELATION_RULES:
            yield Finding(f"{M}.policy_relation", s.where, f"{s.rule} never emits a PROV relation (NE-10)")
        claims = [t for t in qname_values(s.attrs.get("prov:type")) if t == "apv:Assessment"]
        if claims or "apv:claim" in s.attrs:
            yield Finding(f"{M}.policy_relation", s.where, "an assessment expressed as a PROV relation (NE-10)")
    for b in ctx.view.bundles.values():
        if b.kind == "assessment":
            yield from _assessment_forms(ctx, b.iri, b.statements)
            continue
        for s in b.statements:
            if s.rule in ASSESSMENT_RULES:
                yield Finding(f"{M}.assessment_outside", s.where, f"{s.rule} outside an assessment bundle (E.7.2)")
            if set(qname_values(s.attrs.get("apv:claim"))) & POLICY_CLAIMS:
                yield Finding(f"{M}.assessment_outside", s.where, "a policy claim outside an assessment bundle (NE-10)")
            for k in s.attrs:
                if k in LABEL_PROPERTIES:
                    yield Finding(f"{M}.assessment_outside", s.where, f"{k} outside an assessment bundle (NE-10)")


def _assessment_forms(ctx: _Ctx, iri: str, statements: list[St]) -> Iterator[Finding]:
    """E.7.2 item 5: the only statement forms of an assessment bundle."""
    m = ASSESS_ACTIVITY_RE.fullmatch(iri)
    activity = f"x:assess.{m.group(1)}" if m else None
    elsewhere = {s.key for b in ctx.view.bundles.values() if b.iri != iri for s in b.statements if s.is_element}
    assessments = {s.key for s in statements if s.section == "entity" and "apv:Assessment" in s.types}
    code = f"{M}.assessment_form"
    for s in statements:
        if s.is_identified and s.rule not in ASSESSMENT_RULES:
            yield Finding(code, s.where, f"{s.rule} is not an assessment rule (E.7.3)")
        if s.is_element:
            if s.key in elsewhere:
                yield Finding(code, s.where, "a node of another bundle re-declared in the assessment bundle (E.7.2 item 3)")
            elif s.section == "entity" and not (".mn-" in s.key or s.key in assessments):
                yield Finding(code, s.where, "an entity that is neither a mention nor an apv:Assessment")
            elif s.section == "activity" and (s.key != activity or s.types != {"apv:PolicyEvaluation"}):
                yield Finding(code, s.where, "an activity other than the bundle's apv:PolicyEvaluation")
            continue
        if s.section == "wasGeneratedBy":
            if s.arg("prov:entity") not in assessments or s.arg("prov:activity") != activity:
                yield Finding(code, s.where, "wasGeneratedBy other than an assessment by the evaluation activity")
        elif s.section == "wasAssociatedWith":
            if s.arg("prov:activity") != activity or s.arg("prov:agent") != "sw:agentprov":
                yield Finding(code, s.where, "wasAssociatedWith other than the evaluation activity with the engine")
        elif s.section != "mentionOf":
            yield Finding(code, s.where, f"{s.section} in an assessment bundle (E.7.2 item 5; NE-10)")


def _mentions(ctx: _Ctx) -> Iterator[Finding]:
    """AD-19(b): each mention entity in exactly one ``mentionOf`` whose bundle declares the subject; one mention per
    (subject, annotation) in an assessment bundle."""
    view = ctx.view
    count: dict[str, int] = {}
    general: dict[str, str | None] = {}
    for b in view.bundles.values():
        for s in b.statements:
            if s.section != "mentionOf":
                continue
            supra, infra, bundle = s.arg("prov:specificEntity"), s.arg("prov:generalEntity"), s.arg("prov:bundle")
            if supra is None:
                continue
            count[supra] = count.get(supra, 0) + 1
            general[supra] = infra
            target = view.bundles.get(bundle or "")
            if target is None or infra not in {t.key for t in target.statements if t.is_element}:
                yield Finding(f"{M}.mention_bundle", s.where, "prov:bundle does not declare the mentioned entity")
    for b in view.bundles.values():
        seen: dict[tuple[str | None, Any], str] = {}
        for s in b.statements:
            if s.section != "entity" or ".mn-" not in s.key:
                continue
            if count.get(s.key, 0) != 1:
                yield Finding(f"{M}.mention_cardinality", s.where, f"in {count.get(s.key, 0)} mentionOf (exactly one)")
            if b.kind == "assessment":
                key = (general.get(s.key), s.attrs.get("apv:annotationId"))
                prev = seen.setdefault(key, s.key)
                if prev != s.key:
                    yield Finding(f"{M}.mention_duplicate", s.where, f"a second mention of one (subject, annotation): {prev}")


def _ne11(ctx: _Ctx) -> Iterator[Finding]:
    core = ctx.view.core
    if core is None:
        return
    for s in core.statements:
        if s.cls == "I":
            yield Finding(f"{M}.inferred_in_core", s.where, "INFERRED statement in the core (NE-11)")
        if qname_value(s.attrs.get("apv:afterEvidenceClass")) == "apv:Inferred":
            yield Finding(f"{M}.inferred_in_core", s.where, "INFERRED after attribute in the core (NE-11)")
        for p in qname_values(s.attrs.get("apv:premise")):
            target = ctx.view.by_key.get(p)
            if target is not None and target.cls == "I":
                yield Finding(f"{M}.inferred_in_core", s.where, f"premise {p} is INFERRED (NE-11)")


#: Activity class -> the AER kind its node comes from (NE-12, NE-14).
ACTIVITY_KIND: Final = {"apv:ModelInvocation": "model_call", "apv:CacheRead": "model_call",
                        "apv:ToolExecution": "tool_execution", "apv:Decision": "decision",
                        "apv:GenericActivity": "activity", "apv:Run": "scope", "apv:Pass": "scope",
                        "apv:AgentInvocation": "scope", "apv:SubagentInvocation": "scope", "apv:Step": "scope"}


def _ne12(ctx: _Ctx) -> Iterator[Finding]:
    for key, s in ctx.view.elements.items():
        if key in ("x:capture-profile",) or key.startswith(("x:as-", "x:assess.")):
            continue
        aer_id = ctx.aer_id(key)
        record = ctx.record(aer_id)
        if record is None:
            yield Finding(f"{M}.node_without_record", s.where, "node name resolves to no AER record (NE-12)")
            continue
        if s.section == "activity" and "." not in key:
            for t in s.types & set(ACTIVITY_KIND):
                if record.get("k") != ACTIVITY_KIND[t]:
                    yield Finding(f"{M}.node_without_record", s.where, f"{t} node from a {record.get('k')} record")
    for s in ctx.relations:
        if not s.is_identified:
            continue
        for p in as_list(s.attrs.get("apv:sourcePointer")) if "apv:sourcePointer" in s.attrs else []:
            resolved = resolve_pointer(ctx.aer, p) if isinstance(p, str) else None
            if resolved is not None and resolved[1] and ctx.unk(resolved[0], resolved[1]) is not None:
                yield Finding(f"{M}.unk_premise", s.where, "a relation rests on a field declared unknown (NE-12)")


def _ne13(ctx: _Ctx) -> Iterator[Finding]:
    scripted: set[str] = set()
    for r in ctx.aer.records:
        if r.get("k") == "actor" and (r.get("kind") == "attacker" or r.get("role") == "context_fabricator"):
            scripted.add(str(r.get("id")))
    if not scripted:
        return
    for r in ctx.aer.records:
        if r.get("k") != "message" or r.get("actor") not in scripted:
            continue
        mine = {ctx.node(str(r["id"]))} | {f"{ctx.node(str(r['id']))}-{k}" for k in range(len(r.get("parts", [])))}
        for s in ctx.of("wasGeneratedBy", "wasAttributedTo"):
            if s.arg("prov:entity") not in mine:
                continue
            other = s.arg("prov:activity") or s.arg("prov:agent") or ""
            if ctx.types.get(other, set()) & {"apv:ModelInvocation", "apv:AgentSystem", "apv:ModelService"}:
                yield Finding(f"{M}.scripted_attribution", s.where, "a scripted turn attributed to an LLM (NE-13)")


def _ne14(ctx: _Ctx) -> Iterator[Finding]:
    for s in ctx.view.elements.values():
        if s.section != "activity":
            continue
        n = len(s.types & OCCURRENCE_CLASSES)
        if n != 1:
            yield Finding(f"{M}.activity_conflation", s.where, f"{n} occurrence classes (NE-14)")


def _ne15(ctx: _Ctx) -> Iterator[Finding]:
    apv = ctx.view.prefixes.get("apv", "")
    for s in ctx.view.all_statements():
        if s.key.startswith("apv:"):
            yield Finding(f"{M}.vocab_instance", s.where, "an instance in the vocabulary namespace (NE-15)")
        for v in s.args().values() if not s.is_element else ():
            if v.startswith("apv:"):
                yield Finding(f"{M}.vocab_instance", s.where, "an argument in the vocabulary namespace (NE-15)")
    for prefix, iri in ctx.view.prefixes.items():
        if prefix != "apv" and apv and iri.startswith(apv):
            yield Finding(f"{M}.vocab_instance", f"prefix:{prefix}", "an instance namespace inside apv (NE-15)")


def _ne17(ctx: _Ctx) -> Iterator[Finding]:
    core = ctx.view.core
    if core is None:
        return
    for s in core.statements:
        if s.section == "mentionOf" or "apv:Assessment" in s.types or ".mn-" in s.key:
            yield Finding(f"{M}.interpretation_in_core", s.where, "mention or assessment in the core (NE-17)")
        for k in s.attrs:
            if k in SEM_PROPERTIES:
                yield Finding(f"{M}.interpretation_in_core", s.where, f"{k} in the core (NE-17)")


def _ne18(ctx: _Ctx) -> Iterator[Finding]:
    modified = {ctx.node(str(r["subject"])) for r in ctx.aer.records
                if r.get("k") == "decision" and r.get("verdict") == "modify" and isinstance(r.get("subject"), str)
                and "#" in str(r.get("subject"))}
    for s in ctx.of("used"):
        a = s.arg("prov:activity")
        if s.arg("prov:entity") in modified and a is not None and "apv:ToolExecution" in ctx.types.get(a, set()):
            yield Finding(f"{M}.modified_request_used", s.where, "used(te, p) with a modify decision on p (NE-18)")


def _ne20(ctx: _Ctx) -> Iterator[Finding]:
    # one raw entity per digest (D-621 #18): artefacts with identical bytes share it, so its apv:provPrimary is the set
    # of their values (multi-valued when they differ) and it is a primary source when any of them is (V-2)
    artefacts: dict[str, set[str]] = {}
    for a in ctx.aer.header.get("artifacts", []):
        if isinstance(a, dict):
            values = artefacts.setdefault(f"raw:sha256-{a.get('sha256')}", set())
            if isinstance(a.get("prov_primary"), str):
                values.add(a["prov_primary"])
    for key, s in ctx.view.top_elements.items():
        stated = [v for v in as_list(s.attrs.get("apv:provPrimary")) if v is not None]
        if key in artefacts and (not all(isinstance(v, str) for v in stated) or set(stated) != artefacts[key]):
            yield Finding(f"{M}.primary_source", s.where, "apv:provPrimary differs from the AER artefact")
    for s in ctx.view.all_statements():
        if s.section != "wasDerivedFrom" or "prov:PrimarySource" not in qname_values(s.attrs.get("prov:type")):
            continue
        used = s.arg("prov:usedEntity")
        if s.bundle is not None or used not in artefacts or not artefacts[used] & PRIMARY:
            yield Finding(f"{M}.primary_source", s.where, "hadPrimarySource on a secondary or unknown artefact (NE-20)")


def _ne21(ctx: _Ctx) -> Iterator[Finding]:
    aer = ctx.aer
    for s in ctx.view.elements.values():
        if s.rule == "aprov.g_act@1" and s.section == "activity" and (
                s.types & SPECIALISED_ACTIVITY or "apv:GenericActivity" not in s.types):
            yield Finding(f"{M}.generic_beyond_aer", s.where, "G-ACT node typed with a specialised class (NE-21)")
        if "apv:GenericActivity" in s.types and s.rule != "aprov.g_act@1":
            yield Finding(f"{M}.generic_beyond_aer", s.where, "apv:GenericActivity outside G-ACT")
    seen_use: set[tuple[str, str]] = set()
    seen_gen: set[tuple[str, str]] = set()
    for s in ctx.relations:
        if s.rule not in GENERIC_RULES:
            continue
        a = s.arg("prov:activity")
        record = ctx.record(ctx.aer_id(a)) if a is not None else None
        if s.rule == "aprov.g_use@1":
            if record is None or record.get("k") != "activity" or "." in (a or ""):
                yield Finding(f"{M}.generic_beyond_aer", s.where, "G-USE from a non-activity record (NE-21)")
                continue
            entity = s.arg("prov:entity") or ""
            inputs = [i for i in record.get("inputs", []) if isinstance(i, str)] if ctx.present(record, "/inputs") else []
            if not any(_input_node(ctx, i, entity) for i in inputs):
                yield Finding(f"{M}.generic_beyond_aer", s.where, "G-USE of an entity not in activity.inputs (NE-21)")
            seen_use.add((a or "", entity))
        elif s.rule == "aprov.g_gen@1":
            entity = s.arg("prov:entity") or ""
            art = ctx.record(ctx.aer_id(entity))
            if art is None or art.get("k") != "artefact" or "." in entity or not ctx.present(art, "/generated_by") \
                    or a != ctx.node(str(art["generated_by"])):
                yield Finding(f"{M}.generic_beyond_aer", s.where, "G-GEN other than artefact.generated_by (NE-21)")
            seen_gen.add((entity, a or ""))
        elif s.rule == "aprov.g_assoc@1":
            agent = s.arg("prov:agent")
            if record is None or record.get("k") != "activity" or not ctx.present(record, "/actor") \
                    or agent != ctx.node(str(record["actor"])):
                yield Finding(f"{M}.generic_beyond_aer", s.where, "G-ASSOC other than activity.actor (NE-21)")
    elements = ctx.view.elements
    for r in aer.records:
        rid = str(r.get("id"))
        if r.get("k") == "activity" and ctx.node(rid) in elements and ctx.present(r, "/inputs"):
            for i, target in enumerate(r.get("inputs", [])):
                if not isinstance(target, str) or not ctx.present(r, f"/inputs/{i}"):
                    continue
                nodes = [n for n in elements if _input_node(ctx, target, n)]
                if nodes and not any((ctx.node(rid), n) in seen_use for n in nodes):
                    yield Finding(f"{M}.generic_missing", f"{rid}/inputs/{i}", "declared input without its G-USE usage")
        elif r.get("k") == "artefact" and ctx.present(r, "/generated_by"):
            g = ctx.node(str(r["generated_by"]))
            if ctx.node(rid) in elements and g in elements and (ctx.node(rid), g) not in seen_gen:
                yield Finding(f"{M}.generic_missing", f"{rid}/generated_by", "artefact.generated_by without G-GEN")


def _input_node(ctx: _Ctx, target: str, node: str) -> bool:
    """``node`` is the entity of the input ``target``: ``x:L(target)``, or a state entity of a ``state_change``."""
    if node == ctx.node(target):
        return True
    record = ctx.record(target)
    if record is not None and record.get("k") == "state_change":
        return any(t.endswith("State") for t in ctx.types.get(node, set())) and node.startswith("x:")
    return False


# ============================================================================================================ membership
def _membership(ctx: _Ctx) -> Iterator[Finding]:
    members: dict[str, set[str]] = {}
    for b in ctx.view.bundles.values():
        local = {s.key for s in b.statements if s.is_element}
        for s in b.statements:
            if s.section != "hadMember":
                continue
            c, e = s.arg("prov:collection"), s.arg("prov:entity")
            if c is None or e is None:
                continue
            members.setdefault(c, set()).add(e)
            if not {"prov:Collection", "apv:Message"} <= ctx.types.get(c, set()):
                yield Finding(f"{M}.membership", s.where, "hadMember collection is not a message typed prov:Collection")
            if "apv:ToolCallRequest" not in ctx.types.get(e, set()):
                yield Finding(f"{M}.membership", s.where, "hadMember member is not a tool-call request part")
            if not e.startswith(c + "-"):
                yield Finding(f"{M}.membership", s.where, "the member is not a part of the collection")
            if e not in local:
                yield Finding(f"{M}.membership", s.where, "hadMember is not in the bundle of the request part")
    for key, s in ctx.view.elements.items():
        if "apv:ToolCallRequest" in s.types:
            parent = key.rsplit("-", 1)[0]
            if key not in members.get(parent, set()):
                yield Finding(f"{M}.membership", s.where, "tool-call request without hadMember (AD-19(a))")
        if "apv:Message" in s.types and ("prov:Collection" in s.types) != bool(members.get(key)):
            yield Finding(f"{M}.membership", s.where, "prov:Collection iff the message has request members")


# ============================================================================================================ vocabulary
def _vocabulary(ctx: _Ctx) -> Iterator[Finding]:
    terms = CLASSES | PROPERTIES | INDIVIDUALS
    for s in ctx.view.all_statements():
        for k, v in s.attrs.items():
            if k.startswith("apv:") and k[4:] not in PROPERTIES:
                yield Finding(f"{M}.vocabulary", s.where, f"{k} is not an apv property")
            if not s.is_element and k in RELATION_ARGS[s.section]:
                continue
            for item in as_list(v):
                q = qname_value(item)
                if q is not None and q.startswith("apv:") and q[4:] not in terms:
                    yield Finding(f"{M}.vocabulary", s.where, f"{q} is not an apv term")
                if isinstance(item, dict) and isinstance(item.get("type"), str) and item["type"].startswith("apv:") \
                        and item["type"][4:] not in terms:
                    yield Finding(f"{M}.vocabulary", s.where, f"datatype {item['type']} is not an apv term")


# ============================================================================================================ migration
def _migration_context(ctx: _Ctx) -> Iterator[Finding]:
    for b in ctx.view.bundles.values():
        for s in b.statements:
            if s.rule != "aprov.use_context@1":
                continue
            if b.kind != "inference" or b.methods is None or CONTEXT_METHOD not in b.methods:
                yield Finding(f"{M}.migration_context", s.where,
                              "context membership outside inf.adprov-context_is_prefix-v1 (AD-05; R-05)")


def _migration_generic(ctx: _Ctx) -> Iterator[Finding]:
    for s in ctx.view.bundle_statements():
        if s.rule in GENERIC_RULES:
            yield Finding(f"{M}.migration_generic", s.where, f"{s.rule} statement on a migration AER (AD-15)")
    for r in ctx.aer.records:
        if r.get("k") in ("activity", "artefact"):
            yield Finding(f"{M}.migration_generic", str(r.get("id")), f"{r.get('k')} record on a migration AER (AD-15)")
