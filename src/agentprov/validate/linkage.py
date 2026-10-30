"""Evidence linkage of ``agentprov-prov/0.1`` output to its AER (D8 tier 4; EF E.1.5 items 2-6, F.1; K.10
``test_evidence_linkage.py``; J.3.5 gate D "evidence linkage").

Checks:

* ``pv.linkage.evidence_attributes`` - every bundle statement carries exactly one ``apv:evidenceClass`` and one
  ``apv:rule``; top-level statements carry those two evidence attributes only (E.1.5 item 6);
* ``pv.linkage.rule`` - ``apv:rule`` follows the rule-id grammar and names a rule of the ``aprov`` catalogue
  (``aprov.t_*`` at the top level only);
* ``pv.linkage.source_pointer`` - every statement with AER premises carries at least one ``apv:sourcePointer``; each
  ``"<record id><RFC 6901 pointer>"`` resolves in the AER, the pointers are ordered by record position then pointer,
  and no resolved field is weaker than the statement (EV-5). Each pointer is *bound* to the statement (E.10 item 11,
  K.10 "the field that justifies it"; D-621): in an assessment bundle it is the target or an AER premise of an
  annotation the statement, an endpoint or a premise statement names; elsewhere its record is the statement's node, an
  endpoint, its ``apv:subject`` or a premise statement's node or endpoint, or, for the rules whose evidence reaches
  further (:data:`PREMISE_LINKS`), a record reached from those through the record kinds and fields the rule's premise
  names (D-621; V-3). The pointer exemption of ``aprov.n_capture_profile@1`` holds for the core entity
  ``x:capture-profile`` typed ``apv:CaptureProfile`` only (D-621);
* ``pv.linkage.basis_rule`` - every ``apv:basisRule`` and ``apv:rulePointer`` is cited by a pointed record;
  ``apv:attestedBy`` and ``apv:assumption`` take values from their closed lists (F.1.3, F.1.5 item 6). The
  assumption rule follows the document's ``apv:vocabularyVersion`` (on the derive activity, E.4.6 item 1): from apv
  0.2.0 an ``apv:assumption`` is a core ``apv:`` individual (a QName) and an ``apv:adapterAssumption`` an
  adapter-declared ``<ns>:<Name>`` string of a declared catalogue (E.10 item 11, D-501); an apv 0.1.0 document
  carries both forms on ``apv:assumption`` and has no ``apv:adapterAssumption`` (D-17). An absent or unknown
  version gets the current rule (no finding of its own exists for it);
* ``pv.linkage.existence`` - a statement's class never exceeds the existence class of an endpoint node (R-22), nor its
  rule's ceiling (E.1.5 item 2; a per-path cap is never above it), nor, for the node ``x:L(id)`` or ``x:L(id)-k`` of an
  AER record or part, that record's existence class (D-621, pre-round review #23);
* ``pv.linkage.method`` - INFERRED statements carry a non-empty ``apv:method`` of I-class catalogue rules (T-I1, T-I2);
  no other statement carries one;
* ``pv.linkage.premise`` - ``apv:premise`` QNames resolve to statements within the statement's routing scope;
  every ``aprov.comm@1`` statement cites at least one;
* ``pv.linkage.class_bundle`` - the core holds only OBSERVED and DERIVED statements, inference bundles only INFERRED
  ones whose ``apv:method`` equals the bundle's method set (communications) or is contained in it (E.1.5 item 4);
* ``pv.linkage.aer_binding`` - the document belongs to the AER it is validated against (D-621, pre-round review #26):
  one top-level ``apv:ExecutionRecord`` entity ``xd:aer.<records_sha256>`` whose ``apv:sha256`` and
  ``apv:executionId`` are the AER's, and every bundle's derivation key recomputed from that AER digest, the spec, the
  ``aprov`` catalogue digest the document records (its ``apv:RuleCatalogue`` plan; catalogue drift is D-460's, not
  this check's), the recorded profile options, the bundle kind and slug and (assessment) the SEM digest (E.3.4);
* ``pv.linkage.annotation`` - every assessment bundle has its SEM document (passed by the caller, matched by the digest
  of the top-level ``wasDerivedFrom(bundle, xd:sem.<slug>.<digest>)``); every ``apv:annotationId`` names an annotation
  of it whose target is the mention's subject (``mentionOf`` general entity) or the assessment's ``apv:subject``, and
  every mention of an assessment bundle carries one (E.7.2 item 3).

In assessment bundles (E.7) the SEM rules count as cited: ``apv:basisRule`` / ``apv:rulePointer`` may name the rules
(and a marker's normaliser) of the annotations the statement or its premise statements name, ``apv:method`` and
``apv:adapterAssumption`` resolve in the catalogues the SEM header declares as well as the AER's, and ``apv:method`` may name an
``aprov`` rule whose ceiling is INFERRED (``aprov.a_taint@1``, the authorship and ambiguous-marker paths). Exposures,
taints and the evaluation activity rest on statements only, so they carry no ``apv:sourcePointer``.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping, Sequence
from typing import TYPE_CHECKING, Any, Final

from agentprov.aer.reader import AerDocument
from agentprov.aer.rules import RULE_ID_RE, RULE_REF_RE, CatalogueUnavailableError, RuleRegistry, rule_id_of
from agentprov.prov.evidence import PARTY_QNAME, LETTER, cls
from agentprov.prov.iri import local
from agentprov.prov.specs import ProvSpec, load_spec
from agentprov.prov.vocab import INDIVIDUALS
from agentprov.validate._provdoc import RANK, ProvView, St, as_list, qname_value, qname_values
from agentprov.validate.prov_structure import labels
from agentprov.validate.tiers import CheckOutcome, Finding, outcome

if TYPE_CHECKING:
    from agentprov.sem.types import SemDocument

__all__ = ["NO_RECORD_PREMISE_RULES", "check", "resolve_pointer"]

M: Final = "pv.linkage"
#: K.5 `test_evidence_linkage.py` names this code; the other linkage codes follow `pv.linkage.<check>`.
LINK_UNRESOLVED = "prov.link.unresolved"
#: Rules whose statements rest on no AER record field: the closure (its premises are statements, E.1.6) and the
#: capture profile (package-resource source profile plus seal accounting; E.1.3 states no record pointer for it).
#: Exposure and taint assessments and an assessment bundle's evaluation activity likewise rest on statements only (E.7).
NO_RECORD_PREMISE_RULES: Final = frozenset({"aprov.comm@1", "aprov.n_capture_profile@1", "aprov.a_exposure@1",
                                            "aprov.a_taint@1", "aprov.a_evaluation@1"})
CAPTURE_PROFILE_RULE: Final = "aprov.n_capture_profile@1"
CAPTURE_PROFILE_NODE: Final = "x:capture-profile"
#: Rules whose AER premises reach records beyond the statement's node and endpoints (D-621; the engine's citations), as
#: the links a pointer's record may be bound through, ``(direction, kind, field, pointers)``: ``"out"`` - a bound record
#: of ``kind`` names it in ``field``; ``"in"`` - it is of ``kind`` and names a bound record (a part's node binds its part
#: id, ``m#k``) in ``field``; ``pointers``, when given, are the only pointers into it the link binds. ``assoc_tool``: the
#: request message a tool execution's ``call`` names and that message's generator (delegation); ``start_tool``: the tool
#: execution's actor (its AutoExecution citation); ``decision``: a decision about the statement's entity; ``gen_result``:
#: that decision and a message it generated; ``outcome``: the scope a checked message belongs to (``/scored``);
#: ``n_model``: a model call of the service's actor; ``n_part``: the decision or seal issue (``ids``) about the part
#: (dispatch status). Scope, run and actor records bind through these links only (pre-round verification V-3).
#: ``"after"`` - the pointed record is of ``kind`` and a bound record of that kind lies in its transitive ``after``
#: closure: a carried-over state change (``apv:EnvironmentCarriedOver``) cites its own fields for its predecessor's state,
#: which the engine chooses along ``after`` edges (R-54), in ``env_call``/``env_pass`` and in a checker's post-state
#: usage (``outcome``, the record itself; D-621 amendment 3).
_Link = tuple[str, str, str, tuple[str, ...] | None]
PREMISE_LINKS: Final[Mapping[str, tuple[_Link, ...]]] = {
    "aprov.assoc_tool@1": (("out", "tool_execution", "call", ("/generated_by", "/actor")),
                           ("out", "message", "generated_by", ("/actor",))),
    "aprov.start_tool@1": (("out", "tool_execution", "actor", None),),
    "aprov.decision@1": (("in", "decision", "subject", None),),
    "aprov.gen_result@1": (("in", "decision", "subject", ("/subject",)), ("in", "message", "generated_by", ("/generated_by",))),
    "aprov.outcome@1": (("out", "message", "scope", ("/scored",)), ("after", "state_change", "after", ("",))),
    "aprov.env_call@1": (("after", "state_change", "after", None),),
    "aprov.env_pass@1": (("after", "state_change", "after", None),),
    "aprov.n_model@1": (("in", "model_call", "actor", ("/served_model",)),),
    "aprov.n_part@1": (("in", "decision", "subject", ("/subject", "/verdict")), ("in", "seal", "ids", None)),
}
LINKED_PREMISE_RULES: Final = frozenset(PREMISE_LINKS)
#: ``x:L(id)[-k][.<q>...]`` -> the AER record id ``id`` (E.1.2) and, for a part's node, its index ``k``.
_NODE_RECORD_RE: Final = re.compile(r"x:([a-z][a-z0-9_]{0,31})(?:-([0-9]+))?(?:\..*)?")
EVIDENCE_ATTRS: Final = (
    "apv:sourcePointer", "apv:basisRule", "apv:rulePointer", "apv:attestedBy", "apv:assumption",
    "apv:adapterAssumption", "apv:premise", "apv:confidence", "apv:threshold",
)  # fmt: skip
_MISSING: Final = object()


def resolve_pointer(aer: AerDocument, text: str) -> tuple[dict[str, Any], str, Any] | None:
    """Resolve ``"<record id><RFC 6901 pointer>"``: (record, pointer, value), or ``None``. The seal is ``seal``."""
    rid, slash, rest = text.partition("/")
    pointer = slash + rest
    record = aer.seal if rid == "seal" else aer.get(rid)
    if not isinstance(record, dict):
        return None
    value: Any = record
    if pointer:
        for token in pointer.split("/")[1:]:
            token = token.replace("~1", "/").replace("~0", "~")
            if isinstance(value, dict) and token in value:
                value = value[token]
            elif isinstance(value, list) and token.isascii() and token.isdigit() and not (len(token) > 1 and token[0] == "0") \
                    and int(token) < len(value):
                value = value[int(token)]
            else:
                return None
    return record, pointer, value


class _Sems:
    """The SEM document of each assessment bundle and the declared catalogues per bundle."""

    def __init__(self, view: ProvView, aer: AerDocument, sems: Sequence[SemDocument]) -> None:
        self.view = view
        self.aer_declared: dict[str, int] = {str(k): int(v) for k, v in dict(aer.header.get("rules", {})).items()
                                             if isinstance(v, int)}
        by_digest = {str(sem.digest): sem for sem in sems}
        self.of: dict[str, SemDocument | None] = {}
        for b in view.assessment():
            found: SemDocument | None = None
            for st in view.top:
                used = st.arg("prov:usedEntity") or ""
                if st.section == "wasDerivedFrom" and st.arg("prov:generatedEntity") == b.iri and used.startswith("xd:sem."):
                    found = by_digest.get(used.rsplit(".", 1)[-1])
            self.of[b.iri] = found

    def declared(self, bundle: str | None) -> dict[str, int]:
        sem = self.of.get(bundle or "")
        if sem is None:
            return self.aer_declared
        rules = sem.header.get("rules", {})
        extra = {str(k): int(v) for k, v in dict(rules).items() if isinstance(v, int)} if isinstance(rules, dict) else {}
        return {**extra, **self.aer_declared}

    def cited(self, s: St, depth: int = 0, seen: set[str] | None = None) -> set[str] | None:
        """The rule references of the annotations ``s`` and its premise statements name (``None`` outside an assessment
        bundle or without its SEM)."""
        sem = self.of.get(s.bundle or "")
        if sem is None:
            return None
        seen = seen if seen is not None else set()
        if s.key in seen or depth > 16:
            return set()
        seen.add(s.key)
        refs: set[str] = set()
        ann = sem.get(s.attrs["apv:annotationId"]) if isinstance(s.attrs.get("apv:annotationId"), str) else None
        if ann is not None:
            refs |= {r for r in ann.get("rule", ()) if isinstance(r, str)}
            value = ann.get("value")
            if isinstance(value, dict) and isinstance(value.get("normaliser"), str):
                refs.add(value["normaliser"])
        for p in qname_values(s.attrs.get("apv:premise")):
            target = self.view.by_key.get(p)
            if target is not None and target.bundle == s.bundle:
                refs |= self.cited(target, depth + 1, seen) or set()
        return refs

    def pointers(self, s: St, aer: AerDocument) -> set[str] | None:
        """The AER premise fields, as ``apv:sourcePointer`` strings, of the annotations that ``s``, its endpoints and its
        premise statements name (``None`` outside an assessment bundle or without its SEM). The engine cites exactly
        these for an assessment-bundle statement (``prov/rules/assess.py``, ``premises``)."""
        sem = self.of.get(s.bundle or "")
        if sem is None:
            return None
        names: set[str] = set()
        todo: list[St] = [s]
        seen: set[str] = set()
        while todo:
            st = todo.pop()
            if st.key in seen or len(seen) > 4096:
                continue
            seen.add(st.key)
            if isinstance(st.attrs.get("apv:annotationId"), str):
                names.add(st.attrs["apv:annotationId"])
            for key in [*st.args().values(), *qname_values(st.attrs.get("apv:premise"))]:
                target = self.view.by_key.get(key)
                if target is not None and target.bundle == s.bundle:
                    todo.append(target)
        out: set[str] = set()
        for name in names:
            ann = sem.get(name)
            if ann is None:
                continue
            if isinstance(ann.get("target"), str):
                out.add(_field(str(ann["target"]), ""))
            for p in ann.get("premises", ()):
                if isinstance(p, dict) and isinstance(p.get("id"), str) and sem.get(p["id"]) is None:
                    out.add(_field(p["id"], p.get("p", "") if isinstance(p.get("p", ""), str) else ""))
        return out


def _field(aer_id: str, ptr: str) -> str:
    """The ``apv:sourcePointer`` string of an AER id (a part id ``m#k`` is ``m/parts/k``) and a pointer below it."""
    mid, hash_, k = aer_id.partition("#")
    return f"{mid}/parts/{k}{ptr}" if hash_ else f"{aer_id}{ptr}"


def check(view: ProvView, aer: AerDocument, *, spec: ProvSpec | None = None,
          registry: RuleRegistry | None = None, sems: Sequence[SemDocument] = ()) -> list[CheckOutcome]:
    spec = spec or load_spec()
    registry = registry or RuleRegistry.default()
    semctx = _Sems(view, aer, sems)
    positions = {str(r.get("id")): i for i, r in enumerate(aer.records)}
    positions["seal"] = len(aer.records)
    return [
        outcome(f"{M}.evidence_attributes", _evidence_attributes(view)),
        outcome(f"{M}.rule", _rules(view, spec)),
        outcome(f"{M}.source_pointer", _source_pointers(view, aer, positions, semctx)),
        outcome(f"{M}.basis_rule", _basis(view, aer, registry, semctx)),
        outcome(f"{M}.existence", _existence(view, aer, spec)),
        outcome(f"{M}.method", _methods(view, registry, semctx, spec)),
        outcome(f"{M}.premise", _premises(view)),
        outcome(f"{M}.class_bundle", _class_bundle(view)),
        outcome(f"{M}.annotation", _annotations(view, semctx)),
        outcome(f"{M}.aer_binding", _aer_binding(view, aer, spec)),
    ]


def _evidence_attributes(view: ProvView) -> Iterator[Finding]:
    for s in view.all_statements():
        if not s.is_identified:
            continue
        ec = s.attrs.get("apv:evidenceClass")
        if s.cls is None:
            detail = "several values" if isinstance(ec, list) else "missing or not apv:Observed|Derived|Inferred"
            yield Finding(f"{M}.evidence_class", s.where, f"apv:evidenceClass {detail}")
        if not isinstance(s.attrs.get("apv:rule"), str):
            yield Finding(f"{M}.rule_missing", s.where, "apv:rule missing or not exactly one string")
        if s.bundle is None:
            extra = [k for k in EVIDENCE_ATTRS if k in s.attrs]
            if extra:
                yield Finding(f"{M}.top_evidence", s.where, f"top-level statements carry only class and rule: {labels(extra)}")
            if s.cls not in (None, "O"):
                yield Finding(f"{M}.top_evidence", s.where, "top-level statements are OBSERVED (E.3.3)")


def _rules(view: ProvView, spec: ProvSpec) -> Iterator[Finding]:
    for s in view.all_statements():
        rule = s.rule
        if rule is None:
            continue
        if RULE_ID_RE.fullmatch(rule) is None or not rule.startswith("aprov."):
            yield Finding(f"{M}.rule_grammar", s.where, "apv:rule is not an aprov rule id")
        elif rule not in spec.rules:
            yield Finding(f"{M}.rule_unknown", s.where, f"{rule} is not in the {spec.catalogue_id} catalogue")
        elif (s.bundle is None) != rule.startswith("aprov.t_"):
            yield Finding(f"{M}.rule_placement", s.where, f"{rule} {'outside' if s.bundle is None else 'inside'} a bundle")


def _pointers(s: St) -> list[Any]:
    return as_list(s.attrs["apv:sourcePointer"]) if "apv:sourcePointer" in s.attrs else []


def is_capture_profile(view: ProvView, s: St) -> bool:
    """``s`` is the core entity ``x:capture-profile`` typed ``apv:CaptureProfile`` (E.10; D-621)."""
    bundle = view.bundles.get(s.bundle or "")
    return (s.section == "entity" and s.key == CAPTURE_PROFILE_NODE and "apv:CaptureProfile" in s.types
            and bundle is not None and bundle.kind == "core")


def _exempt(view: ProvView, s: St) -> bool:
    """A statement whose rule rests on no AER record field (no ``apv:sourcePointer``); the capture-profile rule only
    for the capture-profile node."""
    if s.rule not in NO_RECORD_PREMISE_RULES:
        return False
    return s.rule != CAPTURE_PROFILE_RULE or is_capture_profile(view, s)


def _source_pointers(view: ProvView, aer: AerDocument, positions: Mapping[str, int], semctx: _Sems) -> Iterator[Finding]:
    for s in view.bundle_statements():
        if not s.is_identified:
            continue
        pointers = _pointers(s)
        if not pointers:
            if not _exempt(view, s):
                yield Finding(f"{M}.pointer_missing", s.where, f"no apv:sourcePointer ({s.rule})")
            continue
        if s.rule == CAPTURE_PROFILE_RULE and not is_capture_profile(view, s):
            yield Finding(f"{M}.pointer_missing", s.where, f"{s.rule} is exempt for {CAPTURE_PROFILE_NODE} only")
        keys: list[tuple[int, str]] = []
        resolved_pointers: list[str] = []
        for p in pointers:
            if not isinstance(p, str):
                yield Finding(LINK_UNRESOLVED, s.where, "apv:sourcePointer is not a string")
                continue
            resolved = resolve_pointer(aer, p)
            if resolved is None:
                yield Finding(LINK_UNRESOLVED, s.where, "apv:sourcePointer does not resolve in the AER")
                continue
            record, pointer, _ = resolved
            rid = p.partition("/")[0]
            resolved_pointers.append(p)
            keys.append((positions.get(rid, len(positions)), pointer))
            if s.cls is not None and rid != "seal":
                try:
                    field_cls = cls(record, pointer).letter
                except (KeyError, ValueError, TypeError):
                    field_cls = None
                if field_cls is not None and RANK[field_cls] < RANK[s.cls]:
                    yield Finding(f"{M}.field_weaker", s.where, f"a premise field is {field_cls}, the statement {s.cls}")
        if keys != sorted(keys):
            yield Finding(f"{M}.pointer_order", s.where, "apv:sourcePointer not sorted by record position, then pointer")
        yield from _bindings(view, aer, semctx, s, resolved_pointers)


def _record_of(key: str) -> str | None:
    m = _NODE_RECORD_RE.fullmatch(key)
    return m.group(1) if m is not None else None


def _anchor_keys(view: ProvView, s: St) -> list[str]:
    """The node keys behind the statement: its node or endpoints, ``apv:subject`` and premise statements (their node
    or endpoints)."""
    keys: list[str] = [s.key] if s.is_element else [v for v in s.args().values() if v in view.elements]
    keys += qname_values(s.attrs.get("apv:subject"))
    for p in qname_values(s.attrs.get("apv:premise")) if "apv:premise" in s.attrs else []:
        target = view.by_key.get(p)
        if target is not None:
            keys += [target.key] if target.is_element else [v for v in target.args().values() if v in view.elements]
    return keys


def _anchors(view: ProvView, s: St) -> set[str]:
    """The AER record ids behind :func:`_anchor_keys`."""
    return {rid for k in _anchor_keys(view, s) if (rid := _record_of(k)) is not None}


class _Bound:
    """The records a statement's pointers may name: whole records (a record's node, or reached through a link) and
    parts (``m#k``, from a part's node ``x:m-k``)."""

    def __init__(self, keys: Sequence[str]) -> None:
        self.whole: set[str] = set()
        self.parts: set[str] = set()
        for k in keys:
            m = _NODE_RECORD_RE.fullmatch(k)
            if m is not None and m.group(2) is None:
                self.whole.add(m.group(1))
            elif m is not None:
                self.parts.add(f"{m.group(1)}#{m.group(2)}")

    def records(self) -> set[str]:
        return self.whole | {p.partition("#")[0] for p in self.parts}

    def named(self, value: Any) -> bool:
        """``value`` (a string or a list of strings) names a bound record or part (a part of a whole record counts)."""
        for v in value if isinstance(value, list) else [value]:
            if isinstance(v, str) and (v in self.whole or v in self.parts or ("#" in v and v.partition("#")[0] in self.whole)):
                return True
        return False


def _linked(aer: AerDocument, pointer: str, bound: _Bound, links: Sequence[_Link]) -> bool:
    """The pointer's record (for the seal: the pointed issue) is bound through one of the rule's ``links``."""
    rid, slash, path = pointer.partition("/")
    path = slash + path
    if rid == "seal":
        resolved = resolve_pointer(aer, pointer)
        item = resolved[2] if resolved is not None else None
        return isinstance(item, dict) and any(bound.named(item.get(f)) for d, k, f, _ in links if d == "in" and k == "seal")
    record = aer.get(rid)
    if not isinstance(record, dict):
        return False
    for direction, kind, field, pointers in links:
        if pointers is not None and path not in pointers:
            continue
        if direction == "in" and record.get("k") == kind and bound.named(record.get(field)):
            return True
        if direction == "after" and record.get("k") == kind and any(
                (aer.get(b) or {}).get("k") == kind for b in _after_closure(aer, rid) & bound.records()):
            return True
        if direction == "out":
            for b in bound.records():
                other = aer.get(b)
                if isinstance(other, dict) and other.get("k") == kind and any(
                        isinstance(v, str) and v.partition("#")[0] == rid for v in as_list(other.get(field))):
                    return True
    return False


def _after_closure(aer: AerDocument, rid: str) -> set[str]:
    """The records ``rid`` is (transitively) after, along ``after`` edges that are not declared unknown (as the engine
    follows them)."""
    seen: set[str] = set()
    frontier = [rid]
    while frontier:
        nxt: list[str] = []
        for cur in frontier:
            rec = aer.get(cur)
            if not isinstance(rec, dict) or not isinstance(rec.get("after"), list):
                continue
            unk = rec.get("unk")
            if isinstance(unk, dict) and ("" in unk or "/after" in unk):
                continue
            for edge in rec["after"]:
                target = edge.get("id") if isinstance(edge, dict) else None
                if isinstance(target, str) and target != rid and target not in seen:
                    seen.add(target)
                    nxt.append(target)
        frontier = nxt
    return seen


def _bindings(view: ProvView, aer: AerDocument, semctx: _Sems, s: St, pointers: Sequence[str]) -> Iterator[Finding]:
    """E.10 item 11 (D-621): every resolved pointer names a premise of this statement (see the module docstring)."""
    bundle = view.bundles.get(s.bundle or "")
    if bundle is not None and bundle.kind == "assessment":
        allowed = semctx.pointers(s, aer)
        if allowed is None:
            return  # no SEM document: pv.linkage.annotation reports it
        for p in pointers:
            if p not in allowed:
                yield Finding(f"{M}.pointer_unbound", s.where,
                              "apv:sourcePointer is no premise field of an annotation the statement rests on")
        return
    keys = _anchor_keys(view, s)
    anchors = {rid for k in keys if (rid := _record_of(k)) is not None}
    pending = [p for p in pointers if p.partition("/")[0] not in anchors]
    links = PREMISE_LINKS.get(s.rule or "")
    if pending and links:
        bound = _Bound(keys)
        changed = True
        while changed and pending:
            changed = False
            for p in list(pending):
                rid = p.partition("/")[0]
                if _linked(aer, p, bound, links):
                    if rid != "seal":
                        bound.whole.add(rid)
                    pending.remove(p)
                    changed = True
    for _ in pending:
        yield Finding(f"{M}.pointer_unbound", s.where,
                      "apv:sourcePointer names a record that is not the statement's node, an endpoint or a premise of "
                      "its rule")


#: apv versions whose documents put adapter-declared ``<ns>:<Name>`` strings on ``apv:assumption`` (before D-501).
LEGACY_ASSUMPTION_VERSIONS: Final = frozenset({"0.1.0"})


def vocabulary_version(view: ProvView) -> str | None:
    """The document's ``apv:vocabularyVersion`` (stated on the top-level derive activity, E.4.6 item 1): the one
    string value the top level states, else ``None`` (absent, not a string, or several different values)."""
    found = {s.attrs["apv:vocabularyVersion"] for s in view.top if isinstance(s.attrs.get("apv:vocabularyVersion"), str)}
    return next(iter(found)) if len(found) == 1 else None


def _basis(view: ProvView, aer: AerDocument, registry: RuleRegistry, semctx: _Sems) -> Iterator[Finding]:
    legacy = vocabulary_version(view) in LEGACY_ASSUMPTION_VERSIONS
    for s in view.bundle_statements():
        if not s.is_identified:
            continue
        declared = semctx.declared(s.bundle)
        refs: set[str] = set()
        for p in _pointers(s):
            resolved = resolve_pointer(aer, p) if isinstance(p, str) else None
            if resolved is not None:
                refs |= {r for r in resolved[0].get("rule", ()) if isinstance(r, str)}
                if resolved[0] is aer.seal and isinstance(resolved[2], dict) and isinstance(resolved[2].get("rule"), str):
                    refs.add(resolved[2]["rule"])  # a seal issue cites one rule, as a string
        sem_refs = semctx.cited(s)
        if sem_refs is None and s.bundle in semctx.of:
            continue  # an assessment bundle without its SEM document: pv.linkage.annotation reports it
        refs |= sem_refs or set()
        cited_ids = {rule_id_of(r) for r in refs}
        basis = as_list(s.attrs.get("apv:basisRule")) if "apv:basisRule" in s.attrs else []
        for b in basis:
            if not isinstance(b, str) or RULE_ID_RE.fullmatch(b) is None:
                yield Finding(f"{M}.basis_grammar", s.where, "apv:basisRule is not a rule id string")
            elif b not in cited_ids:
                yield Finding(f"{M}.basis_not_cited", s.where, f"{b} is not cited by a pointed record")
        scoped = as_list(s.attrs.get("apv:rulePointer")) if "apv:rulePointer" in s.attrs else []
        for r in scoped:
            if not isinstance(r, str) or RULE_REF_RE.fullmatch(r) is None or "#" not in r:
                yield Finding(f"{M}.rule_pointer", s.where, "apv:rulePointer is not a scoped rule reference")
            elif r not in refs:
                yield Finding(f"{M}.rule_pointer", s.where, "apv:rulePointer is not cited by a pointed record")
            elif rule_id_of(r) not in basis:
                yield Finding(f"{M}.rule_pointer", s.where, "apv:rulePointer without its apv:basisRule")
        for v in as_list(s.attrs.get("apv:attestedBy")) if "apv:attestedBy" in s.attrs else []:
            if qname_value(v) not in PARTY_QNAME.values():
                yield Finding(f"{M}.attested_by", s.where, "apv:attestedBy outside the attesting-party list")
        for v in as_list(s.attrs.get("apv:assumption")) if "apv:assumption" in s.attrs else []:
            if legacy:  # apv 0.1.0: a core QName or a declared adapter string (D-17)
                if not (_core_assumption_ok(v) or _adapter_assumption_ok(v, registry, declared)):
                    yield Finding(f"{M}.assumption", s.where, "apv:assumption is neither a core individual nor declared")
            elif not _core_assumption_ok(v):
                yield Finding(f"{M}.assumption", s.where, "apv:assumption is not a core apv: individual (QName)")
        if legacy and "apv:adapterAssumption" in s.attrs:
            yield Finding(f"{M}.assumption", s.where, "apv:adapterAssumption in an apv 0.1.0 document")
        elif "apv:adapterAssumption" in s.attrs:
            for v in as_list(s.attrs["apv:adapterAssumption"]):
                if not _adapter_assumption_ok(v, registry, declared):
                    yield Finding(f"{M}.assumption", s.where, "apv:adapterAssumption is not a declared <ns>:<Name> string")


def _core_assumption_ok(value: Any) -> bool:
    """``apv:assumption``: a QName of a core ``apv:`` individual. An adapter term here is the CA-22 defect (D-501)."""
    q = qname_value(value)
    return q is not None and q.startswith("apv:") and q[4:] in INDIVIDUALS


def _adapter_assumption_ok(value: Any, registry: RuleRegistry, declared: Mapping[str, int]) -> bool:
    """``apv:adapterAssumption``: a ``<ns>:<Name>`` string that a declared catalogue of the statement declares."""
    if not isinstance(value, str) or ":" not in value:
        return False
    ns = value.split(":", 1)[0]
    if ns not in declared:
        return False
    try:
        catalogue = registry.get(ns, declared[ns])
    except CatalogueUnavailableError:
        return False
    return value in catalogue.assumptions or any(value in e.assumptions for e in catalogue.rules.values())


#: The node of an AER record or part, exactly (derived nodes ``x:L(id).<q>`` carry their own rule's class).
_RECORD_NODE_RE: Final = re.compile(r"x:([a-z][a-z0-9_]{0,31})(?:-([0-9]+))?")


def _existence(view: ProvView, aer: AerDocument, spec: ProvSpec) -> Iterator[Finding]:
    for s in view.bundle_statements():
        if not s.is_identified or s.cls is None:
            continue
        rule = spec.rules.get(s.rule or "")
        if rule is not None and RANK[s.cls] > int(rule.ceiling):
            yield Finding(f"{M}.ceiling", s.where, f"class {s.cls} above the ceiling {rule.ceiling.letter} of {s.rule} "
                                                   "(E.1.5 item 2)")
        if s.is_element:
            m = _RECORD_NODE_RE.fullmatch(s.key)
            record = (aer.part(f"{m.group(1)}#{m.group(2)}") if m.group(2) is not None else aer.get(m.group(1))) \
                if m is not None else None
            ev = record.get("ev") if isinstance(record, dict) else None
            if isinstance(ev, str) and ev in RANK and RANK[s.cls] > RANK[ev]:
                yield Finding(f"{M}.existence", s.where, f"class {s.cls} above its record's existence class {ev} (R-22)")
            continue
        for k, v in s.args().items():
            node = view.elements.get(v)
            if node is None or node.cls is None:
                continue
            if RANK[s.cls] > RANK[node.cls]:
                yield Finding(f"{M}.existence", s.where, f"class {s.cls} above endpoint {k} class {node.cls} (R-22)")


def _methods(view: ProvView, registry: RuleRegistry, semctx: _Sems, spec: ProvSpec) -> Iterator[Finding]:
    engine_inferred = {r for r, rule in spec.rules.items()  # an INFERRED ceiling, on the rule or one of its paths
                       if rule.ceiling == LETTER["I"] or LETTER["I"] in rule.caps.values()}
    for s in view.bundle_statements():
        if not s.is_identified:
            continue
        declared = semctx.declared(s.bundle)
        methods = as_list(s.attrs.get("apv:method")) if "apv:method" in s.attrs else []
        if s.cls == "I":
            if not methods:
                yield Finding(f"{M}.method_missing", s.where, "INFERRED statement without apv:method (T-I2)")
            for m in methods:
                if not isinstance(m, str) or RULE_ID_RE.fullmatch(m) is None:
                    yield Finding(f"{M}.method_rule", s.where, "apv:method value is not a rule id")
                    continue
                if s.bundle in semctx.of and m in engine_inferred:
                    continue  # an INFERRED-ceiling engine rule of the assessment bundle (a_taint, authorship, ambiguous)
                entry = registry.lookup(m, declared)
                if entry is None or entry.cls != "I":
                    yield Finding(f"{M}.method_rule", s.where, f"{m} is not an I-class rule of a declared catalogue")
        elif methods:
            yield Finding(f"{M}.method_on_non_inferred", s.where, "apv:method on a non-INFERRED statement")


def _premises(view: ProvView) -> Iterator[Finding]:
    for s in view.bundle_statements():
        premises = qname_values(s.attrs.get("apv:premise")) if "apv:premise" in s.attrs else []
        if "apv:premise" in s.attrs and len(premises) != len(as_list(s.attrs["apv:premise"])):
            yield Finding(f"{M}.premise_unresolved", s.where, "apv:premise value is not a QName")
        if s.rule == "aprov.comm@1" and not premises:
            yield Finding(f"{M}.premise_missing", s.where, "aprov.comm@1 without apv:premise (E.1.6)")
        own = view.methods(s.bundle)
        for p in premises:
            target = view.by_key.get(p)
            if target is None or target.bundle is None:  # elements are statements too (E.0.4)
                yield Finding(f"{M}.premise_unresolved", s.where, f"{p} is not a statement of a bundle")
                continue
            theirs = view.methods(target.bundle)
            if own is not None and theirs is not None and not theirs <= own:
                yield Finding(f"{M}.premise_scope", s.where, f"{p} lies outside the statement's routing scope")
            elif _assessment_scope_breach(view, s.bundle, target.bundle):
                yield Finding(f"{M}.premise_scope", s.where, f"{p} lies outside the statement's routing scope")


def _assessment_scope_breach(view: ProvView, citing: str | None, cited: str) -> bool:
    """D-621 (pre-round review #24): an assessment bundle's statements are premises only within that bundle (policy
    claims stay out of the core and inference bundles, invariant 2), and an assessment statement rests on the core,
    the inference bundles and its own bundle only (its application view, E.7)."""
    kind = {iri: b.kind for iri, b in view.bundles.items()}
    if kind.get(cited) == "assessment" and cited != citing:
        return True
    return kind.get(citing or "") == "assessment" and cited != citing and kind.get(cited) not in ("core", "inference")


def _class_bundle(view: ProvView) -> Iterator[Finding]:
    for b in view.bundles.values():
        for s in b.statements:
            if not s.is_identified or s.cls is None:
                continue
            if b.kind == "core" and s.cls == "I":
                yield Finding(f"{M}.class_bundle", s.where, "INFERRED statement in the core bundle")
            elif b.kind == "inference":
                if s.cls != "I":
                    yield Finding(f"{M}.class_bundle", s.where, f"class {s.cls} in an inference bundle")
                    continue
                methods = frozenset(m for m in as_list(s.attrs.get("apv:method")) if isinstance(m, str)) \
                    if "apv:method" in s.attrs else frozenset()
                if b.methods is None or not methods:
                    continue
                if s.rule == "aprov.comm@1" and methods != b.methods:
                    yield Finding(f"{M}.method_bundle", s.where, "communication apv:method differs from the bundle's method set")
                elif not methods <= b.methods:
                    yield Finding(f"{M}.method_bundle", s.where, "apv:method not contained in the bundle's method set")


def _annotations(view: ProvView, semctx: _Sems) -> Iterator[Finding]:
    for b in view.assessment():
        sem = semctx.of.get(b.iri)
        if sem is None:
            yield Finding(f"{M}.sem_missing", b.iri, "no SEM document matches the assessment bundle (pass sems=)")
            continue
        general = {st.arg("prov:specificEntity"): st.arg("prov:generalEntity") for st in b.statements
                   if st.section == "mentionOf"}
        for st in b.statements:
            if not st.is_element or not st.is_identified:
                continue
            ann_id = st.attrs.get("apv:annotationId")
            if ann_id is None:
                if ".mn-" in st.key:
                    yield Finding(f"{M}.annotation", st.where, "a mention without apv:annotationId (E.7.2 item 3)")
                continue
            ann = sem.get(ann_id) if isinstance(ann_id, str) else None
            if ann is None or not isinstance(ann.get("target"), str):
                yield Finding(f"{M}.annotation", st.where, "apv:annotationId names no annotation of the SEM document")
                continue
            subject = general.get(st.key) if ".mn-" in st.key else qname_value(st.attrs.get("apv:subject"))
            if subject != "x:" + local(ann["target"]):
                yield Finding(f"{M}.annotation", st.where, "the annotation's target is not the statement's subject")


def _aer_binding(view: ProvView, aer: AerDocument, spec: ProvSpec) -> Iterator[Finding]:
    """D-621 (#26): the document's AER entity and bundle derivation keys are those of ``aer`` (E.3.3, E.3.4)."""
    import json

    from agentprov.prov.iri import derivation_key

    code = f"{M}.aer_binding"
    digest = str(aer.seal.get("records_sha256", "")) if isinstance(aer.seal, dict) else ""
    records = [s for s in view.top if s.section == "entity" and "apv:ExecutionRecord" in s.types]
    if len(records) != 1:
        yield Finding(code, "top", f"{len(records)} apv:ExecutionRecord entities (exactly one)")
    for s in records:
        if s.key != f"xd:aer.{digest}" or s.attrs.get("apv:sha256") != digest:
            yield Finding(code, s.where, "the AER entity does not carry the digest of the AER validated against")
        if s.attrs.get("apv:executionId") != aer.ex:
            yield Finding(code, s.where, "the AER entity's apv:executionId is not the AER's execution id")
    options: Any = None
    for s in view.top:
        raw = s.attrs.get("apv:profileOptions") if s.section == "activity" else None
        if isinstance(raw, str):
            try:
                options = json.loads(raw)
            except ValueError:
                options = None
    if not isinstance(options, dict):
        if view.bundles:
            yield Finding(code, "top", "no derive activity with apv:profileOptions (E.4.6 item 1)")
        return
    catalogue = next((st.attrs.get("apv:sha256") for st in view.top
                      if st.section == "entity" and "apv:RuleCatalogue" in st.types
                      and st.attrs.get("apv:catalogueId") == spec.catalogue_id), None)
    if not isinstance(catalogue, str):
        if view.bundles:
            yield Finding(code, "top", f"no {spec.catalogue_id} rule-catalogue plan with apv:sha256 (E.3.3)")
        return
    sem_digest: dict[str, str] = {}
    for st in view.top:
        used = st.arg("prov:usedEntity") or ""
        if st.section == "wasDerivedFrom" and used.startswith("xd:sem."):
            sem_digest[st.arg("prov:generatedEntity") or ""] = used.rsplit(".", 1)[-1]
    for iri, b in view.bundles.items():
        head, _, dk = iri.rpartition(".")
        kind = {"core": "core", "inference": "inference", "assessment": "assessment"}.get(b.kind)
        if kind is None:
            continue  # an unknown bundle kind: pv.prov_structure.bundles reports it
        slug = head.split(".", 2)[2] if kind != "core" and head.count(".") >= 2 else None
        expected = derivation_key(spec_id=spec.id, catalogue_sha256=catalogue, aer_digest=digest,
                                  sem_digest=sem_digest.get(iri) if kind == "assessment" else None, kind=kind,
                                  key=slug, options=options)
        if dk != expected:
            yield Finding(code, iri, "the bundle's derivation key is not that of the AER validated against (E.3.4)")

