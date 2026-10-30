"""Assessment rules ``aprov.a_*`` of ``agentprov-prov/0.1``: one assessment bundle per SEM document (EF E.7).

The bundle holds non-PROV claims only (E.7.2 item 5): mention entities (labels of entities), ``apv:Assessment`` entities
(labels of activities, payload containment, authorship, exposure, taint), the bundle's policy-evaluation activity, the
generation of each assessment by that activity, its association with the engine under the semantics profile, and one
``mentionOf`` per mention. It never holds ``used``, ``wasDerivedFrom``, ``wasInformedBy``, ``wasAttributedTo`` or
``wasInfluencedBy`` (NE-10).

Classes follow the weakest-premise rule (E.1.5 item 2; F.1.4): the rule ceiling (or a per-path cap), the SEM annotation's
``ev`` (its method set being the I-class rules it cites), its AER premise fields and target, the existence of the nodes
named and the classes of premise statements. Statements are not routed by class: every class lives in the assessment
bundle. Names follow E.4.2 and E.10 items 12 and 14: mentions ``x:L(t).mn-<h12>`` over (dk, annotation id); assessments
``x:as-<h16>`` over (dk, rule id, subject, object or ``-``, claim), with the annotation id as discriminator only when
those repeat.

Exposure (``aprov.a_exposure@1``) states context membership only: subject the request part ``p``, object a context
member ``m`` of the invocation that generated ``p``, premises the ``aprov.use_context@1`` and ``aprov.gen_part@1``
statements. Pairs are materialised for requests whose roles are not exactly ``neutral`` and members whose integrity is
not ``trusted``; unlabelled roles and integrity read as ``unknown`` (fail-closed, C.14.3). A ``tool_execution`` without a
request part has no generating invocation and gets no exposure; it is counted (``exposure_no_request``).
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final

from agentprov.aer.ids import is_part_id
from agentprov.aer.rules import RULE_REF_RE, RuleRegistry, rule_id_of
from agentprov.io.canonical import jcs_bytes
from agentprov.prov import iri
from agentprov.prov._ir import Field, Stmt, dbl, q
from agentprov.prov.evidence import LETTER, EvidenceClass
from agentprov.sem.types import ANNOTATION_TYPES, INTEGRITY_VALUES, MARKER_STATUSES, ROLE_VALUES

if TYPE_CHECKING:
    from agentprov.prov.engine import Ctx, _Classifier
    from agentprov.sem.types import SemanticsProfile, SemDocument

__all__ = ["AssessmentResult", "build"]

I: Final = EvidenceClass.INFERRED  # noqa: E741
INTEGRITY: Final = {"trusted": "apv:Trusted", "untrusted": "apv:Untrusted", "unknown": "apv:IntegrityUnknown"}
ROLES: Final = {
    "write_sink": "apv:WriteSink",
    "send_sink": "apv:SendSink",
    "execute_sink": "apv:ExecuteSink",
    "egress_read": "apv:EgressRead",
    "response_sink": "apv:ResponseSink",
    "content_source": "apv:ContentSource",
    "endorser": "apv:Endorser",
    "neutral": "apv:Neutral",
    "unknown": "apv:RoleUnknown",
}
LABEL_TYPES: Final = frozenset({"integrity", "role", "channel", "outcome"})
NS_TYPE_RE: Final = re.compile(r"[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*")
# @2 (D-930): a premise field declared unknown is not cited (NE-12); @1 stays in the catalogue for stored documents
RULE_LABEL: Final = "aprov.a_label@2"
RULE_PAYLOAD: Final = "aprov.a_payload@2"
RULE_AUTHOR: Final = "aprov.a_author@2"
RULE_EXPOSURE: Final = "aprov.a_exposure@1"
RULE_TAINT: Final = "aprov.a_taint@1"
RULE_EVALUATION: Final = "aprov.a_evaluation@1"
ENGINE_AGENT: Final = "sw:agentprov"
assert set(INTEGRITY) == set(INTEGRITY_VALUES) and set(ROLES) == set(ROLE_VALUES)  # one vocabulary (sem.types)
assert LABEL_TYPES | {"injection_marker", "author"} == set(ANNOTATION_TYPES)


@dataclass(slots=True)
class AssessmentResult:
    """The content of one assessment bundle, its statement counts and the report counters."""

    content: dict[str, dict[str, Any]]
    classes: Counter[str]  # evidence-class letter -> statements (elements and identified relations)
    rules: Counter[tuple[str, str]]  # (rule, letter) -> statements
    counts: dict[str, int]


@dataclass(slots=True)
class _Item:
    """An ``apv:Assessment`` before naming (premises may name assessments, so bodies render after naming)."""

    stmt: Stmt
    subject: str  # node local name
    obj: str | None
    claim: str
    props: dict[str, Any]
    ann: dict[str, Any] | None
    extra_basis: tuple[str, ...] = ()
    disc: str = ""


@dataclass(slots=True)
class _Builder:
    ctx: Ctx
    classifier: _Classifier
    sem: SemDocument
    profile: SemanticsProfile
    dk: str
    bundle_iri: str
    node_bundles: Mapping[str, str]
    registry: RuleRegistry
    slug: str = ""
    sem_declared: dict[str, int] = field(default_factory=dict)
    content: dict[str, dict[str, Any]] = field(default_factory=dict)
    items: list[_Item] = field(default_factory=list)
    mentions: list[tuple[Stmt, Mapping[str, Any], str, dict[str, Any]]] = field(default_factory=list)
    by_ann: dict[str, list[Stmt]] = field(default_factory=dict)
    order: dict[str, int] = field(default_factory=dict)
    counts: Counter[str] = field(default_factory=Counter)
    classes: Counter[str] = field(default_factory=Counter)
    rules: Counter[tuple[str, str]] = field(default_factory=Counter)

    # ------------------------------------------------------------------------------------------ helpers
    def fail(self, message: str, code: str = "prov.sem_invalid") -> Exception:
        from agentprov.prov.engine import ProvDerivationError

        return ProvDerivationError(message, code=code)

    @property
    def activity(self) -> str:
        return f"assess.{self.slug}"

    def put(self, section: str, key: str, body: dict[str, Any]) -> None:
        sec = self.content.setdefault(section, {})
        if key in sec:
            raise self.fail(f"duplicate identifier {key} in {self.bundle_iri}", "prov.statement_collision")
        sec[key] = body
        cls = body.get("apv:evidenceClass")
        if not key.startswith("_:") and isinstance(cls, dict):
            letter = {"apv:Observed": "O", "apv:Derived": "D", "apv:Inferred": "I"}[cls["$"]]
            self.classes[letter] += 1
            self.rules[(str(body.get("apv:rule")), letter)] += 1

    def target_field(self, target: str) -> Field:
        if self.ctx.kind(target) is None:
            raise self.fail(f"SEM target {target} is not an AER record or part", "prov.unresolved_reference")
        if is_part_id(target):
            mid, _, k = target.partition("#")
            return Field(mid, f"/parts/{k}")
        return Field(target, "")

    def premise_field(self, pid: str, ptr: str) -> Field:
        if is_part_id(pid):
            mid, _, k = pid.partition("#")
            f = Field(mid, f"/parts/{k}{ptr}")
        else:
            f = Field(pid, ptr)
        self.ctx.val(f.rid, f.ptr)  # prov.unresolved_pointer when it does not resolve
        return f

    def sem_class(self, ann: Mapping[str, Any]) -> tuple[EvidenceClass, frozenset[str]]:
        ev = ann.get("ev")
        if ev not in LETTER:
            raise self.fail(f"annotation {ann.get('id')} has no evidence class")
        c = LETTER[str(ev)]
        if c != I:
            return c, frozenset()
        methods = frozenset(
            rule_id_of(str(r)) for r in ann["rule"]
            if (e := self.registry.lookup(rule_id_of(str(r)), self.sem_declared)) is not None and e.cls == "I"
        )
        # An annotation INFERRED by propagation (C.6.5 rule 3: an I premise under a D rule, e.g. an outcome over a judgement
        # whose origin rests on an _unverified twin, D.5.4) names no I rule of its own: its method set is its premises',
        # which every caller passes as the statement's fields and premise statements. If none of them is INFERRED either,
        # the classifier refuses the statement (prov.method_set_empty), as before.
        return c, methods

    def premises(self, ann: Mapping[str, Any]) -> tuple[list[Field], list[Stmt]]:
        """The annotation's AER premise fields (its target first) and the statements of the earlier annotations it
        names (C.14.2 ``premises``). A premise field declared unknown in its record is not cited and is counted
        (``premise_field_unknown``): SEM may rest a label on it (SEM-V06), PROV may not (E.1.5 item 1, NE-12; D-930)."""
        fields = [self.target_field(str(ann["target"]))]
        stmts: list[Stmt] = []
        own = self.order[str(ann["id"])]
        for p in ann["premises"]:
            if not isinstance(p, dict) or not isinstance(p.get("id"), str) or not isinstance(p.get("p", ""), str):
                raise self.fail(f"annotation {ann['id']} has a malformed premise")
            pid, ptr = p["id"], p.get("p", "")
            if self.ctx.kind(pid) is not None:
                f = self.premise_field(pid, ptr)
                if self.ctx.unk_reason(f.rid, f.ptr) is not None:
                    self.counts["premise_field_unknown"] += 1
                else:
                    fields.append(f)
            elif pid in self.order and self.order[pid] < own:
                found = self.by_ann.get(pid, [])
                if not found:
                    self.counts["premise_annotation_without_statement"] += 1
                stmts += found
            else:
                raise self.fail(f"annotation {ann['id']} names {pid}, neither an AER id nor an earlier annotation",
                                "prov.unresolved_reference")
        return list(dict.fromkeys(fields)), list(dict.fromkeys(stmts))

    def stmt(self, rule: str, *, fields: Sequence[Field] = (), nodes: Sequence[str], prem: Sequence[Stmt] = (),
             sem: Sequence[tuple[EvidenceClass, frozenset[str]]] = (), path: str | None = None) -> Stmt:
        prule = self.ctx.spec.rule(rule)
        s = Stmt(rule=rule, section="entity", args={}, fields=list(fields), nodes=list(nodes), prem=list(prem),
                 ceiling=prule.cap(path), assumptions=prule.assumptions_by_path.get(path or "", ()), sem=list(sem))
        self.classifier.stmt(s)
        return s

    def evidence(self, s: Stmt, anns: Iterable[Mapping[str, Any]] = (), extra_basis: Iterable[str] = ()) -> dict[str, Any]:
        """E.1.5 item 6 for an assessment-bundle statement: the engine's evidence attributes of its AER premises, plus
        the rules cited by its D or I SEM annotations (and a marker's normaliser) as ``apv:basisRule`` /
        ``apv:rulePointer``, and their catalogues' assumptions."""
        from agentprov.prov.engine import _evidence, _multi, assumption_attrs

        out = _evidence(self.ctx, s)
        basis: list[Any] = _values(out.get("apv:basisRule"))
        scoped: list[Any] = _values(out.get("apv:rulePointer"))
        assumptions: list[str] = [v["$"] if isinstance(v, dict) else str(v) for v in _values(out.get("apv:assumption"))]
        assumptions += [str(v) for v in _values(out.get("apv:adapterAssumption"))]
        refs: list[str] = list(extra_basis)
        for ann in anns:
            if ann.get("ev") in ("D", "I"):
                refs += [str(r) for r in ann["rule"]]
        for ref in refs:
            if RULE_REF_RE.fullmatch(ref) is None:
                continue
            rid = rule_id_of(ref)
            basis.append(rid)
            if "#" in ref:
                scoped.append(ref)
            entry = self.registry.lookup(rid, self.sem_declared)
            if entry is not None:
                assumptions += list(entry.assumptions)
        for key, values in (("apv:basisRule", basis), ("apv:rulePointer", scoped)):
            if values:
                out[key] = _multi(values)
        out.update(assumption_attrs(assumptions))  # core QNames and adapter strings apart (D-501)
        return out

    # ------------------------------------------------------------------------------------------ the bundle
    def evaluation(self) -> None:
        """E.7.2 item 2: the policy-evaluation activity and its association with the engine under the profile."""
        act = "x:" + self.activity
        self.put("activity", act, {"prov:type": q("apv:PolicyEvaluation"), "apv:evidenceClass": q("apv:Observed"),
                                   "apv:rule": RULE_EVALUATION})
        plan = f"rules:{self.profile.id}.{self.profile.version}"
        args = {"prov:activity": act, "prov:agent": ENGINE_AGENT, "prov:plan": plan}
        name = iri.statement_name(self.dk, RULE_EVALUATION, [args["prov:activity"], args["prov:agent"], args["prov:plan"]])
        self.put("wasAssociatedWith", "x:" + name, {**args, "apv:evidenceClass": q("apv:Observed"),
                                                    "apv:rule": RULE_EVALUATION})

    def mention(self, s: Stmt, ann: Mapping[str, Any], target: str, props: Mapping[str, Any]) -> None:
        """E.7.2 item 3: one mention per (subject, annotation), exactly one ``mentionOf``; the subject is not
        re-declared here. Rendered in :meth:`finish`, once every premise statement is named."""
        ann_id = str(ann["id"])
        s.name = f"{target}.mn-{iri.h(self.dk + chr(10) + ann_id, 12)}"
        self.mentions.append((s, ann, target, dict(props)))
        self.by_ann.setdefault(ann_id, []).append(s)

    def render_mention(self, s: Stmt, ann: Mapping[str, Any], target: str, props: dict[str, Any]) -> None:
        from agentprov.prov.engine import _multi

        body = dict(props)
        body.update(self.evidence(s, [ann]))
        body["apv:annotationId"] = str(ann["id"])
        if s.prem:
            body["apv:premise"] = _multi([q("x:" + str(p.name)) for p in s.prem])
        self.put("entity", "x:" + str(s.name), body)
        args = {"prov:specificEntity": "x:" + str(s.name), "prov:generalEntity": "x:" + target,
                "prov:bundle": self.node_bundles[target]}
        key = "_:" + iri.statement_name(self.dk, s.rule, [args["prov:specificEntity"], args["prov:generalEntity"],
                                                          args["prov:bundle"]])
        self.put("mentionOf", key, args)

    def assessment(self, item: _Item) -> None:
        self.items.append(item)
        if item.ann is not None:
            self.by_ann.setdefault(str(item.ann["id"]), []).append(item.stmt)

    # ------------------------------------------------------------------------------------------ SEM annotations
    def annotations(self) -> None:
        annotations = self.sem.annotations
        for index, ann in enumerate(annotations):
            if not isinstance(ann, dict) or ann.get("k") != "ann" or not isinstance(ann.get("id"), str):
                raise self.fail("a SEM record is not an annotation")
            if not isinstance(ann.get("target"), str) or not isinstance(ann.get("rule"), list) or not ann["rule"] \
                    or not isinstance(ann.get("premises"), list) or "value" not in ann:
                raise self.fail(f"annotation {ann['id']} is malformed")
            if ann["id"] in self.order:
                raise self.fail(f"annotation id {ann['id']} repeats")
            self.order[ann["id"]] = index
        for ann in annotations:
            typ = ann.get("type")
            if typ == "injection_marker":
                self.payload(ann)
            elif typ == "author":
                self.author(ann)
            elif typ in LABEL_TYPES or (isinstance(typ, str) and NS_TYPE_RE.fullmatch(typ)):
                self.label(ann)
            else:
                raise self.fail(f"annotation {ann['id']} has an unknown type")

    def node_of(self, ann: Mapping[str, Any]) -> tuple[str, Stmt] | None:
        target = str(ann["target"])
        self.target_field(target)
        name = iri.local(target)
        node = self.ctx.node(name)
        if node is None:
            self.counts["label_target_without_node"] += 1
            return None
        return name, node

    def label(self, ann: dict[str, Any]) -> None:
        """``aprov.a_label@2``: integrity, role, channel, outcome and namespaced labels (E.7.3)."""
        typ, value, target = str(ann["type"]), ann["value"], str(ann["target"])
        if typ == "outcome":
            if self.ctx.kind(target) != "judgement":
                raise self.fail(f"outcome annotation {ann['id']} does not target a judgement")
            if self.ctx.present(target, "/origin") and self.ctx.val(target, "/origin") == "harness_default":
                self.counts["outcome_harness_default"] += 1  # C.14.3: not emitted
                return
        props = self.label_props(ann, typ, value)
        found = self.node_of(ann)
        if found is None:
            return
        name, node = found
        fields, prem = self.premises(ann)
        sem = [self.sem_class(ann)]
        self.counts["labels"] += 1
        if node.section == "entity":
            s = self.stmt(RULE_LABEL, fields=fields, nodes=[name], prem=prem, sem=sem)
            self.mention(s, ann, name, props)
        else:  # an activity or agent: an apv:Assessment (R-21; NE-19)
            s = self.stmt(RULE_LABEL, fields=fields, nodes=[name], prem=[node, *prem], sem=sem)
            self.assessment(_Item(s, name, None, "apv:Labelled", props, ann))

    def label_props(self, ann: Mapping[str, Any], typ: str, value: Any) -> dict[str, Any]:
        from agentprov.prov.engine import _multi

        if typ == "integrity" and value in INTEGRITY:
            return {"apv:integrity": q(INTEGRITY[value])}
        if typ == "role" and isinstance(value, list) and value and all(v in ROLES for v in value):
            return {"apv:securityRole": _multi([q(ROLES[v]) for v in value])}
        if typ == "channel" and isinstance(value, str) and value:
            return {"apv:sourceChannel": value}
        if typ == "outcome" and isinstance(value, dict) and isinstance(value.get("claim"), str) and value["claim"]:
            props: dict[str, Any] = {"apv:outcomeClaim": value["claim"]}
            holds, score, scale = value.get("holds"), value.get("score"), value.get("scale")
            if "holds" in value:
                if not isinstance(holds, bool):
                    raise self.fail(f"outcome annotation {ann['id']} has a non-boolean holds")
                props["apv:outcomeHolds"] = holds
            if "score" in value:
                if isinstance(score, bool) or not isinstance(score, int | float):
                    raise self.fail(f"outcome annotation {ann['id']} has a non-numeric score")
                props["apv:outcomeScore"] = dbl(score)
            if "scale" in value:
                if not isinstance(scale, str):
                    raise self.fail(f"outcome annotation {ann['id']} has a non-string scale")
                props["apv:outcomeScale"] = scale
            return props
        if NS_TYPE_RE.fullmatch(typ) and typ not in ANNOTATION_TYPES:
            return {"apv:annotationType": typ, "apv:annotationValue": jcs_bytes(value).decode("utf-8")}
        raise self.fail(f"annotation {ann['id']} has a value outside its type's vocabulary")

    def payload(self, ann: dict[str, Any]) -> None:
        """``aprov.a_payload@2``: ``present`` -> ContainsPayload (DERIVED cap); ``ambiguous`` -> the same claim with
        ``apv:markerStatus apv:Ambiguous`` (INFERRED); ``absent`` and ``gap`` -> no statement, counted."""
        value = ann["value"]
        if not isinstance(value, dict) or value.get("status") not in MARKER_STATUSES:
            raise self.fail(f"injection_marker annotation {ann['id']} has no marker status")
        status = str(value["status"])
        if status in ("absent", "gap"):
            self.target_field(str(ann["target"]))
            self.counts[f"payload_{status}"] += 1
            return
        fixture, normaliser = value.get("fixture"), value.get("normaliser")
        if not isinstance(fixture, str) or not isinstance(normaliser, str):
            raise self.fail(f"injection_marker annotation {ann['id']} lacks its fixture or normaliser")
        found = self.node_of(ann)
        if found is None:
            return
        name, node = found
        fx = iri.local(fixture)
        fx_node = self.ctx.node(fx)
        if self.ctx.kind(fixture) != "fixture" or fx_node is None or node.section != "entity":
            self.counts["payload_fixture_unresolved"] += 1
            return
        if status == "ambiguous" and not self.declared_assumptions([*map(str, ann["rule"]), normaliser]):
            # E.7.3: an ambiguous marker carries an assumption. The assumption is the SEM profile's (declared by its
            # marker rule or normaliser in the profile's catalogue), not a core term (D-17), so it is a string on
            # apv:adapterAssumption (apv 0.2.0, D-501).
            raise self.fail(f"ambiguous injection marker {ann['id']} cites no rule that declares its assumption (E.7.3)",
                            "prov.sem_invalid")
        fields, prem = self.premises(ann)
        path = "ambiguous" if status == "ambiguous" else None
        s = self.stmt(RULE_PAYLOAD, fields=fields, nodes=[name, fx], prem=[node, fx_node, *prem],
                      sem=[self.sem_class(ann)], path=path)
        props: dict[str, Any] = {}
        if status == "ambiguous":
            props["apv:markerStatus"] = q("apv:Ambiguous")
        props.update(self.span(ann))
        self.counts[f"payload_{status}"] += 1
        self.assessment(_Item(s, name, fx, "apv:ContainsPayload", props, ann, (normaliser,)))

    def declared_assumptions(self, refs: Iterable[str]) -> list[str]:
        """The assumptions the catalogues of the SEM header declare for the rules ``refs``."""
        out: list[str] = []
        for ref in refs:
            if RULE_REF_RE.fullmatch(ref) is None:
                continue
            entry = self.registry.lookup(rule_id_of(ref), self.sem_declared)
            if entry is not None:
                out += list(entry.assumptions)
        return out

    def span(self, ann: Mapping[str, Any]) -> dict[str, Any]:
        span = ann.get("span")
        if span is None:
            return {}
        if not (isinstance(span, list) and len(span) == 2 and all(isinstance(v, int) and not isinstance(v, bool)
                                                                   for v in span) and 0 <= span[0] <= span[1]):
            raise self.fail(f"annotation {ann['id']} has a malformed span")
        return {"apv:spanStart": span[0], "apv:spanEnd": span[1]}

    def author(self, ann: dict[str, Any]) -> None:
        """``aprov.a_author@2``: the declared sender as a mention (a parse fact, DERIVED cap), plus an INFERRED
        authorship assessment whose premise is the mention (never ``wasAttributedTo``: NE-4, NE-10)."""
        value = ann["value"]
        actor: str | None = None
        if isinstance(value, str) and value:
            sender = value
        elif isinstance(value, dict) and isinstance(value.get("actor"), str) and value["actor"]:
            sender = actor = str(value["actor"])
        else:
            raise self.fail(f"author annotation {ann['id']} has no author")
        found = self.node_of(ann)
        if found is None:
            return
        name, node = found
        if node.section != "entity":
            raise self.fail(f"author annotation {ann['id']} targets an activity or agent")
        fields, prem = self.premises(ann)
        sem = [self.sem_class(ann)]
        mention = self.stmt(RULE_AUTHOR, fields=fields, nodes=[name], prem=prem, sem=sem)
        self.mention(mention, ann, name, {"apv:declaredSender": sender})
        obj: str | None = None
        nodes = [name]
        if actor is not None and self.ctx.kind(actor) == "actor" and self.ctx.node(iri.local(actor)) is not None:
            obj = iri.local(actor)
            nodes.append(obj)
        s = self.stmt(RULE_AUTHOR, fields=fields, nodes=nodes, prem=[mention], sem=sem, path="authorship")
        props = {"apv:authorName": sender, **self.span(ann)}
        self.counts["authorship"] += 1
        self.assessment(_Item(s, name, obj, "apv:QuotesAuthoredContent", props, ann))

    # ------------------------------------------------------------------------------------------ exposure and taint
    def labels_on(self, target: str, typ: str) -> tuple[list[Any], list[Stmt]]:
        values: list[Any] = []
        stmts: list[Stmt] = []
        for ann in self.sem.on(target, typ):
            values.append(ann["value"])
            stmts += self.by_ann.get(str(ann["id"]), [])
        return values, stmts

    def request_roles(self, pid: str, executions: Sequence[str]) -> tuple[frozenset[str], list[Stmt]]:
        """The roles of request ``pid``: its own role labels and those of the executions whose ``call`` it is;
        ``{"unknown"}`` when unlabelled (fail-closed)."""
        roles: set[str] = set()
        stmts: list[Stmt] = []
        for target in (pid, *executions):
            values, found = self.labels_on(target, "role")
            for v in values:
                roles.update(str(r) for r in v)
            stmts += found
        return frozenset(roles or {"unknown"}), stmts

    def message_integrity(self, mid: str) -> tuple[str, list[Stmt]]:
        """The integrity of a context member: the meet (untrusted < unknown < trusted) over its parts, each part
        unknown when unlabelled (fail-closed); a message without parts is unknown."""
        record = self.ctx.rec(mid) or {}
        raw_parts = record.get("parts")
        parts: list[Any] = raw_parts if isinstance(raw_parts, list) else []
        own, stmts = self.labels_on(mid, "integrity")
        levels: list[str] = []
        for k in range(len(parts)):
            values, found = self.labels_on(f"{mid}#{k}", "integrity")
            stmts += found
            values = values or own
            levels.append("untrusted" if "untrusted" in values else "trusted" if values and set(values) == {"trusted"}
                          else "unknown")
        if "untrusted" in levels:
            return "untrusted", stmts
        if levels and set(levels) == {"trusted"}:
            return "trusted", stmts
        return "unknown", stmts

    def exposures(self) -> None:
        """``aprov.a_exposure@1`` and ``aprov.a_taint@1`` (E.7.3 items 1-2)."""
        gen_part: dict[str, list[Stmt]] = {}
        uses: dict[str, list[Stmt]] = {}
        for s in self.ctx.stmts:
            if s.rule == "aprov.gen_part@1":
                gen_part.setdefault(s.args["prov:entity"], []).append(s)
            elif s.rule == "aprov.use_context@1":
                uses.setdefault(s.args["prov:activity"], []).append(s)
        executions: dict[str, list[str]] = {}
        for record in self.ctx.records:
            if record.get("k") != "tool_execution":
                continue
            te = str(record["id"])
            if self.ctx.present(te, "/call"):
                executions.setdefault(str(record["call"]), []).append(te)
            else:  # no request part, hence no generating invocation (EF E.7.3; ruling over D.12.2 / K.6.4)
                self.counts["exposure_no_request"] += 1
        policy = self.profile.taint_policy
        for record in self.ctx.records:
            if record.get("k") != "message" or not isinstance(record.get("parts"), list):
                continue
            mid = str(record["id"])
            for k, part in enumerate(record["parts"]):
                if not isinstance(part, dict) or part.get("t") != "tool_call":
                    continue
                pid = f"{mid}#{k}"
                pname = iri.local(pid)
                gens = [g for g in gen_part.get("x:" + pname, ())
                        if self.ctx.kind(g.args["prov:activity"][2:]) == "model_call"]
                if not gens:
                    self.counts["exposure_no_invocation"] += 1
                    continue
                roles, role_stmts = self.request_roles(pid, executions.get(pid, ()))
                if roles == {"neutral"}:
                    self.counts["exposure_neutral_request"] += 1
                    continue
                members: dict[str, list[Stmt]] = {}
                for u in uses.get(gens[0].args["prov:activity"], ()):
                    members.setdefault(u.args["prov:entity"][2:], []).append(u)
                if not members:
                    self.counts["exposure_context_unknown"] += 1
                    continue
                for member, used in members.items():
                    integrity, integrity_stmts = self.message_integrity(member)
                    if integrity == "trusted":
                        self.counts["exposure_trusted_object"] += 1
                        continue
                    exposure = self.stmt(RULE_EXPOSURE, nodes=[pname, member], prem=[*used, gens[0]])
                    self.assessment(_Item(exposure, pname, member, "apv:ExposedTo", {}, None))
                    self.counts["exposures"] += 1
                    if policy is None or not roles & policy.subject_roles or integrity not in policy.object_integrity:
                        continue
                    prem = list(dict.fromkeys([exposure, *role_stmts, *integrity_stmts]))
                    taint = self.stmt(RULE_TAINT, nodes=[pname, member], prem=prem)
                    self.assessment(_Item(taint, pname, member, "apv:PotentiallyInfluencedBy",
                                          {"apv:policy": policy.rule}, None))
                    self.counts["taints"] += 1

    # ------------------------------------------------------------------------------------------ naming and output
    def finish(self) -> AssessmentResult:
        from agentprov.prov.engine import _multi

        groups: dict[tuple[str, str, str, str], list[_Item]] = {}
        for item in self.items:
            key = (item.stmt.rule, "x:" + item.subject, "x:" + item.obj if item.obj else "-", item.claim)
            groups.setdefault(key, []).append(item)
        for key, members in groups.items():
            for item in members:
                if len(members) > 1:
                    if item.ann is None:
                        raise self.fail(f"assessment collision under {key[0]}", "prov.statement_collision")
                    item.disc = f"annotation={item.ann['id']}"
                text = "\n".join([self.dk, *key]) + ("\n" + item.disc if item.disc else "")
                item.stmt.name = "as-" + iri.h(text, 16)
        for mention in self.mentions:
            self.render_mention(*mention)
        activity = "x:" + self.activity
        for item in self.items:
            s = item.stmt
            ident = "x:" + str(s.name)
            evidence = self.evidence(s, [item.ann] if item.ann is not None else [], item.extra_basis)
            body: dict[str, Any] = {"prov:type": q("apv:Assessment"), "apv:claim": q(item.claim),
                                    "apv:subject": q("x:" + item.subject)}
            if item.obj is not None:
                body["apv:object"] = q("x:" + item.obj)
            body.update(item.props)
            body.update(evidence)
            if item.ann is not None:
                body["apv:annotationId"] = str(item.ann["id"])
            body["apv:premise"] = _multi([q("x:" + str(p.name)) for p in s.prem])
            self.put("entity", ident, body)
            args = {"prov:entity": ident, "prov:activity": activity}
            name = iri.statement_name(self.dk, s.rule, [ident, activity])
            self.put("wasGeneratedBy", "x:" + name, {**args, **evidence, "apv:premise": q(ident)})
        return AssessmentResult(self.content, self.classes, self.rules, dict(sorted(self.counts.items())))


def _values(value: Any) -> list[Any]:
    if value is None:
        return []
    return list(value) if isinstance(value, list) else [value]


def build(
    ctx: Ctx,
    classifier: _Classifier,
    sem: SemDocument,
    profile: SemanticsProfile,
    *,
    dk: str,
    bundle_iri: str,
    node_bundles: Mapping[str, str],
    registry: RuleRegistry,
) -> AssessmentResult:
    """The assessment bundle of one SEM document (E.7.2): call after the core and inference statements are classified
    and named, since exposures cite them as premises."""
    rules = sem.header.get("rules", {})
    if not isinstance(rules, dict) or not all(isinstance(k, str) and isinstance(v, int) and not isinstance(v, bool)
                                              for k, v in rules.items()):
        from agentprov.prov.engine import ProvDerivationError

        raise ProvDerivationError("the SEM header's rules are malformed", code="prov.sem_invalid")
    builder = _Builder(ctx, classifier, sem, profile, dk, bundle_iri, node_bundles, registry,
                       slug=iri.profile_slug(profile.id, profile.version), sem_declared=dict(rules))
    builder.evaluation()
    builder.annotations()
    builder.exposures()
    return builder.finish()
