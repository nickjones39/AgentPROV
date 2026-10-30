"""Edge rules of ``agentprov-prov/0.1`` (EF E.1.4), including G-USE, G-GEN and G-ASSOC (AD-15).

A rule fires only when every required pointer resolves and none is declared unknown (E.1.5 item 1; ``ctx.present``).
Relations name their AER premise fields; classes, routing and statement ids are computed by the engine. The
communication closure (``aprov.comm@1``) is not here: it is computed by the engine from the finished usages and
generations (E.1.6).
"""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING, Any, Final

from agentprov.aer.ids import is_part_id
from agentprov.prov._ir import Attr, Field, q
from agentprov.prov.iri import local
from agentprov.prov.rules.nodes import blob_digest

if TYPE_CHECKING:
    from agentprov.prov.engine import Ctx

__all__ = ["after_attributes", "apply", "decision_nodes", "state_predecessors"]

TRANSFORMS: Final = {
    "error_substitution": "apv:ErrorSubstitution",
    "role_rewrite": "apv:RoleRewrite",
    "reasoning_passback": "apv:ReasoningPassback",
    "formatting": "apv:Formatting",
    "truncation": "apv:Truncation",
    "other": "apv:OtherTransform",
}
AFTER_PROPS: Final = {"causal": "apv:afterCausal", "time": "apv:afterTime", "pos": "apv:afterPos", "proto": "apv:afterProto"}
ENTITY_KINDS: Final = frozenset({"message", "fixture", "artefact", "judgement"})
CHECKER_ASSUMPTIONS: Final = (
    "apv:CheckerUsesOutput",
    "apv:CheckerUsesPreState",
    "apv:CheckerUsesPostState",
    "apv:CheckerUsesCallTrace",
)


def role(qname: str) -> Attr:
    return Attr("prov:role", q(qname))


# --------------------------------------------------------------------------------------------- prepasses
def decision_nodes(ctx: Ctx) -> None:
    """The pre-decision entities ``x:L(te).out`` / ``x:L(P).pre`` of decisions about produced output (E.1.2, R-21)."""
    for record in ctx.records:
        if record.get("k") != "decision" or not ctx.present(str(record["id"]), "/subject"):
            continue
        dc = str(record["id"])
        subject = str(record["subject"])
        name = None
        if ctx.kind(subject) == "tool_execution":
            name = f"{local(subject)}.out"
        elif is_part_id(subject) and (ctx.part(subject) or {}).get("t") == "tool_result":
            name = f"{local(subject)}.pre"
        if name is None or ctx.node(name) is not None:
            continue
        attrs: list[Attr] = []
        original = record.get("original")
        if ctx.present(dc, "/original") and blob_digest(original):
            attrs.append(Attr("apv:contentSha256", blob_digest(original), (Field(dc, "/original"),)))
        base = subject.split("#", 1)[0]
        ctx.add_node(name, "entity", "aprov.decision@1", [], None, attrs, fields=[Field(dc, "/subject")],
                     nodes=[local(dc), local(base)])
        ctx.register_subject_node(dc, name)


def _after_closure(ctx: Ctx, rid: str) -> list[list[str]]:
    """Breadth-first layers of the records ``rid`` is (transitively) after, following AER ``after`` edges only."""
    seen = {rid}
    layers: list[list[str]] = []
    frontier = [rid]
    while frontier:
        nxt: list[str] = []
        for cur in frontier:
            rec = ctx.rec(cur)
            for edge in (rec or {}).get("after", ()) if rec is not None and ctx.present(cur, "/after") else ():
                target = edge.get("id") if isinstance(edge, dict) else None
                if isinstance(target, str) and target not in seen:
                    seen.add(target)
                    nxt.append(target)
        if nxt:
            layers.append(sorted(nxt, key=lambda t: -ctx.pos(t)))
        frontier = nxt
    return layers


def _nearest(ctx: Ctx, rid: str, accept: Any) -> str | None:
    for layer in _after_closure(ctx, rid):
        for cand in layer:
            if accept(cand):
                return cand
    return None


def _same_target(ctx: Ctx, cand: str, target: object, *, patched: bool, after: object = None) -> bool:
    other = ctx.rec(cand)
    if other is None or other.get("k") != "state_change" or other.get("target") != target:
        return False
    if patched:
        return "patch" in other and "after_sha256" not in other
    return bool(other.get("after_sha256") == after)


def state_predecessors(ctx: Ctx) -> None:
    """Carry-over predecessors of digest state changes (``aprov.env_pass@1``) and patch predecessors (``state_patch``).

    The predecessor is chosen along ``after`` edges, never by file order or digest equality alone (R-54)."""
    for record in ctx.records:
        if record.get("k") != "state_change":
            continue
        sc, target = str(record["id"]), record.get("target")
        if ctx.present(sc, "/before_sha256"):
            refs = ctx.citing_assumption(sc, "apv:EnvironmentCarriedOver")
            if refs:
                before = record["before_sha256"]
                pred = _nearest(ctx, sc, lambda c, t=target, b=before: _same_target(ctx, c, t, patched=False, after=b))
                if pred is not None:
                    ctx.set_carry(sc, pred, refs)
        elif ctx.present(sc, "/patch"):
            pred = _nearest(ctx, sc, lambda c, t=target: _same_target(ctx, c, t, patched=True))
            if pred is not None:
                ctx.set_patch_pred(sc, pred)


# --------------------------------------------------------------------------------------------- the rules
def apply(ctx: Ctx) -> None:
    handlers = {
        "message": _message,
        "model_call": _model_call,
        "tool_execution": _tool_execution,
        "scope": _scope,
        "actor": _actor,
        "fixture": _fixture,
        "decision": _decision,
        "state_change": _state_change,
        "judgement": _judgement,
        "activity": _activity,
        "artefact": _artefact,
    }
    for record in ctx.records:
        handler = handlers.get(str(record.get("k")))
        if handler is not None:
            handler(ctx, str(record["id"]), record)
    _rerun(ctx)


def _message(ctx: Ctx, m: str, r: dict[str, Any]) -> None:
    parts: list[Any] = r["parts"] if isinstance(r.get("parts"), list) else []
    lm = local(m)
    for k, part in enumerate(parts):
        if isinstance(part, dict) and part.get("t") == "tool_call":
            ctx.rel("hadMember", "aprov.member_request@1", {"prov:collection": lm, "prov:entity": f"{lm}-{k}"},
                    fields=[Field(m, f"/parts/{k}")])
    if ctx.present(m, "/generated_by"):
        g = str(r["generated_by"])
        gen = [Field(m, "/generated_by")]
        ctx.rel("wasGeneratedBy", "aprov.gen_message@1", {"prov:entity": lm, "prov:activity": local(g)}, fields=gen)
        for k, part in enumerate(parts):
            if not isinstance(part, dict):
                continue
            pk = f"{lm}-{k}"
            if part.get("t") != "tool_result":
                ctx.rel("wasGeneratedBy", "aprov.gen_part@1", {"prov:entity": pk, "prov:activity": local(g)}, fields=gen)
                continue
            _gen_result(ctx, m, k, part, g, gen)
    elif ctx.present(m, "/actor") and ctx.unk_reason(m, "/generated_by") is None:
        # E.1.4 attr_message needs /generated_by ABSENT; an unk one is unknown, not absent (E.1.5 item 1; D-621 #15,
        # user decision 2026-10-22): the message's gap records it and nothing is attributed
        ctx.rel("wasAttributedTo", "aprov.attr_message@1", {"prov:entity": lm, "prov:agent": local(str(r["actor"]))},
                fields=[Field(m, "/actor")])


def _gen_result(ctx: Ctx, m: str, k: int, part: dict[str, Any], g: str, gen: list[Field]) -> None:
    pk = f"{local(m)}-{k}"
    gkind = ctx.kind(g)
    if gkind == "tool_execution":
        call = ctx.val(g, "/call") if ctx.present(g, "/call") else None
        responds = part.get("responds_to") if ctx.present(m, f"/parts/{k}/responds_to") else None
        if call is not None and responds is not None and call != responds:
            ctx.disclose("gen_result_link_mismatch", f"{m}#{k}", "tool_result responds_to differs from the execution's call")
        ctx.rel("wasGeneratedBy", "aprov.gen_result@1", {"prov:entity": pk, "prov:activity": local(g)}, fields=gen)
        return
    ctx.rel("wasGeneratedBy", "aprov.gen_result@1", {"prov:entity": pk, "prov:activity": local(g)}, fields=gen)
    if gkind != "decision" or not ctx.present(g, "/subject"):
        return
    subject = str(ctx.val(g, "/subject"))
    if ctx.kind(subject) == "tool_execution":
        pre, te = f"{local(subject)}.out", subject
    elif subject == f"{m}#{k}":
        return  # the subject cannot be the decision's own result (backward references)
    else:
        return
    if ctx.node(pre) is not None and ctx.node(local(te)) is not None:
        ctx.rel("wasGeneratedBy", "aprov.gen_result@1", {"prov:entity": pre, "prov:activity": local(te)},
                fields=[*gen, Field(g, "/subject")], once=True)


def _model_call(ctx: Ctx, mc: str, r: dict[str, Any]) -> None:
    lmc = local(mc)
    if ctx.present(mc, "/input"):
        for i, item in enumerate(r.get("input", [])):
            mid = item if isinstance(item, str) else item.get("id") if isinstance(item, dict) else None
            if not isinstance(mid, str) or not ctx.present(mc, f"/input/{i}"):
                continue  # D-621 (#16): an item declared unk fires nothing (E.1.5 item 1); its gap records it
            attrs = [role("apv:ContextMessage"), Attr("apv:contextIndex", i)]
            if isinstance(item, dict):
                for t in item.get("sent", []) if ctx.present(mc, f"/input/{i}/sent") else []:
                    attrs.append(Attr("apv:sentTransform", q(TRANSFORMS.get(str(t), "apv:OtherTransform")),
                                      (Field(mc, f"/input/{i}/sent"),), rule="aprov.a_sent_transform@1"))
                if ctx.present(mc, f"/input/{i}/sent_sha256"):
                    attrs.append(Attr("apv:asSentSha256", item["sent_sha256"], (Field(mc, f"/input/{i}/sent_sha256"),),
                                      rule="aprov.a_sent_transform@1"))
            ctx.rel("used", "aprov.use_context@1", {"prov:activity": lmc, "prov:entity": local(mid)}, attrs,
                    fields=[Field(mc, f"/input/{i}")], disc=f"contextIndex={i}")
    status = r.get("status") if ctx.present(mc, "/status") else None
    actor = str(r["actor"]) if ctx.present(mc, "/actor") else None
    if status in ("kept", "discarded"):
        if ctx.present(mc, "/served_model") and ctx.node(f"{lmc}.model") is not None:
            ctx.rel("used", "aprov.use_model@1", {"prov:activity": lmc, "prov:entity": f"{lmc}.model"},
                    [role("apv:ModelInput")], fields=[Field(mc, "/served_model")])
        elif actor is not None and ctx.node(f"{local(actor)}.model") is not None:
            ctx.rel("used", "aprov.use_model@1", {"prov:activity": lmc, "prov:entity": f"{local(actor)}.model"},
                    [role("apv:ModelInput")], fields=[Field(mc, "/actor")], path="per_actor")
    if ctx.present(mc, "/tools"):
        ctx.rel("used", "aprov.use_tools@1", {"prov:activity": lmc, "prov:entity": local(str(r["tools"]))},
                [role("apv:ToolDefinitionsInput")], fields=[Field(mc, "/tools")])
    if actor is not None:
        ctx.rel("wasAssociatedWith", "aprov.assoc_model_call@1", {"prov:activity": lmc, "prov:agent": local(actor)},
                [role("apv:AgentSystemRole")], fields=[Field(mc, "/actor")])
        svc = f"{local(actor)}.svc"
        if status in ("kept", "discarded") and ctx.node(svc) is not None:
            fields = [Field(mc, "/actor")] + ([Field(mc, "/served_model")] if ctx.present(mc, "/served_model") else [])
            ctx.rel("wasAssociatedWith", "aprov.assoc_model_call@1", {"prov:activity": lmc, "prov:agent": svc},
                    [role("apv:InferenceProvider")], fields=fields)


def _tool_execution(ctx: Ctx, te: str, r: dict[str, Any]) -> None:
    lte = local(te)
    call = str(r["call"]) if ctx.present(te, "/call") else None
    authorised = str(r["authorised_by"]) if ctx.present(te, "/authorised_by") else None
    # D-621 #15 (user decision 2026-10-22): an unk /authorised_by is unknown, not absent, so the negative condition of
    # start_tool (AutoExecution) and of the AutoExecution delegation does not hold (E.1.4, E.1.5 item 1)
    unauthorised = authorised is None and ctx.unk_reason(te, "/authorised_by") is None
    if call is not None:
        if call in ctx.modified_requests:
            ctx.add_gap(lte, te, "/call", "apv:NotRecorded", rule="aprov.use_request@1")
            ctx.disclose("ne18_modified_request", te, "used(te, request) suppressed: a modify decision has the request as subject")
        else:
            ctx.rel("used", "aprov.use_request@1", {"prov:activity": lte, "prov:entity": local(call)},
                    [role("apv:CallRequestInput")], fields=[Field(te, "/call")])
    auto = ctx.citing_assumption(te, "apv:AutoExecution")
    if not auto and ctx.present(te, "/actor"):
        auto = ctx.citing_assumption(str(r["actor"]), "apv:AutoExecution")
    message = call.split("#", 1)[0] if call is not None else None
    generator = str(ctx.val(message, "/generated_by")) if message and ctx.present(message, "/generated_by") else None
    if call is not None and unauthorised and auto:
        args = {"prov:activity": lte, "prov:trigger": local(call)}
        fields = [Field(te, "/call")]
        if generator is not None and ctx.node(local(generator)) is not None and ctx.kind(generator) != "actor":
            args["prov:starter"] = local(generator)
            fields.append(Field(str(message), "/generated_by"))
        ctx.rel("wasStartedBy", "aprov.start_tool@1", args, fields=fields, cited=auto)
    if authorised is not None:
        ctx.rel("wasStartedBy", "aprov.authorise@1", {"prov:activity": lte, "prov:starter": local(authorised)},
                fields=[Field(te, "/authorised_by")])
    if not ctx.present(te, "/actor"):
        return
    runtime = local(str(r["actor"]))
    ctx.rel("wasAssociatedWith", "aprov.assoc_tool@1", {"prov:activity": lte, "prov:agent": runtime},
            [role("apv:ExecutingRuntime")], fields=[Field(te, "/actor")])
    requester: str | None = None
    fields = [Field(te, "/actor")]
    cited: tuple[Any, ...] = ()
    if call is not None and message is not None:
        if generator is not None and ctx.present(generator, "/actor"):
            requester = str(ctx.val(generator, "/actor"))
            fields += [Field(te, "/call"), Field(message, "/generated_by"), Field(generator, "/actor")]
        elif generator is None and ctx.present(message, "/actor") and "generated_by" not in (ctx.rec(message) or {}) \
                and ctx.unk_reason(message, "/generated_by") is None:  # D-621 #15: unknown is not absent
            requester = str(ctx.val(message, "/actor"))
            fields += [Field(te, "/call"), Field(message, "/actor")]
        if requester is not None:
            if authorised is not None:
                fields.append(Field(te, "/authorised_by"))
            elif auto and unauthorised:
                cited = auto
            else:
                requester = None
    elif ctx.present(te, "/requested_by"):
        requester = str(r["requested_by"])
        fields.append(Field(te, "/requested_by"))
    if requester is not None and ctx.node(local(requester)) is not None:
        ctx.rel("actedOnBehalfOf", "aprov.assoc_tool@1",
                {"prov:delegate": runtime, "prov:responsible": local(requester), "prov:activity": lte},
                fields=fields, path="delegation", cited=cited)


def _scope(ctx: Ctx, s: str, r: dict[str, Any]) -> None:
    if r.get("kind") == "thread":
        return
    ls = local(s)
    if ctx.present(s, "/actor"):
        ctx.rel("wasAssociatedWith", "aprov.assoc_scope@1", {"prov:activity": ls, "prov:agent": local(str(r["actor"]))},
                fields=[Field(s, "/actor")])
    if ctx.present(s, "/spawned_by"):
        ctx.rel("wasStartedBy", "aprov.spawn@1", {"prov:activity": ls, "prov:starter": local(str(r["spawned_by"]))},
                fields=[Field(s, "/spawned_by")])


def _actor(ctx: Ctx, a: str, r: dict[str, Any]) -> None:
    if ctx.present(a, "/on_behalf_of") and a in ctx.scope_actors:
        ctx.rel("actedOnBehalfOf", "aprov.deleg_user@1",
                {"prov:delegate": local(a), "prov:responsible": local(str(r["on_behalf_of"]))},
                fields=[Field(a, "/on_behalf_of")])


def _fixture(ctx: Ctx, fx: str, r: dict[str, Any]) -> None:
    if ctx.present(fx, "/actor"):
        ctx.rel("wasAttributedTo", "aprov.attr_fixture@1", {"prov:entity": local(fx), "prov:agent": local(str(r["actor"]))},
                fields=[Field(fx, "/actor")])
    if r.get("kind") == "injection_payload" and ctx.present(fx, "/vector"):
        cited = ctx.citing_assumption(fx, "apv:InjectionPlacement")
        first = ctx.first_state() if cited else None
        if first is not None:
            sc, entity = first
            ctx.rel("wasDerivedFrom", "aprov.inj_placement@1",
                    {"prov:generatedEntity": entity, "prov:usedEntity": local(fx)},
                    [Attr("prov:type", q("apv:InjectionPlacementDerivation"))],
                    fields=[Field(fx, "/vector"), Field(sc, "/before_sha256")], cited=cited)


def _decision(ctx: Ctx, dc: str, r: dict[str, Any]) -> None:
    ldc = local(dc)
    if ctx.present(dc, "/actor"):
        actor = str(r["actor"])
        kind = (ctx.rec(actor) or {}).get("kind")
        ctx.rel("wasAssociatedWith", "aprov.decision@1", {"prov:activity": ldc, "prov:agent": local(actor)},
                [role("apv:DefenceRole" if kind == "defense" else "apv:DeciderRole")], fields=[Field(dc, "/actor")])
    if not ctx.present(dc, "/subject"):
        return
    subject = str(r["subject"])
    skind = ctx.kind(subject)
    if skind == "model_call":
        return  # an activity subject: apv:decisionSubject only, no used (NE-19)
    entity = ctx.subject_node(dc) or local(subject)
    if ctx.node(entity) is None:
        ctx.skipped(dc, "/subject", "subject without an entity node")
        return
    ctx.rel("used", "aprov.decision@1", {"prov:activity": ldc, "prov:entity": entity}, [role("apv:DecisionSubject")],
            fields=[Field(dc, "/subject")])
    verdict = r.get("verdict") if ctx.present(dc, "/verdict") else None
    if verdict not in ("modify", "redact"):
        return
    kind = "apv:DefenceModification" if verdict == "modify" else "apv:DefenceRedaction"
    for m in ctx.generated_messages(dc):
        for k, part in enumerate((ctx.rec(m) or {}).get("parts", [])):
            if isinstance(part, dict):
                ctx.rel("wasDerivedFrom", "aprov.decision@1",
                        {"prov:generatedEntity": f"{local(m)}-{k}", "prov:usedEntity": entity}, [Attr("prov:type", q(kind))],
                        fields=[Field(dc, "/subject"), Field(dc, "/verdict"), Field(m, "/generated_by")])


def _state_change(ctx: Ctx, sc: str, r: dict[str, Any]) -> None:
    lsc = local(sc)
    if ctx.present(sc, "/before_sha256") or ctx.present(sc, "/after_sha256"):
        cause = str(r["cause"]) if ctx.present(sc, "/cause") else None
        if cause is not None and ctx.kind(cause) == "tool_execution":
            rule, activity, afield = "aprov.env_call@1", local(cause), Field(sc, "/cause")
        elif cause is not None and ctx.kind(cause) == "scope" and ctx.node(local(cause)) is not None:
            rule, activity, afield = "aprov.env_pass@1", local(cause), Field(sc, "/cause")
        elif ctx.present(sc, "/scope") and ctx.node(local(str(r["scope"]))) is not None:
            rule, activity, afield = "aprov.env_pass@1", local(str(r["scope"])), Field(sc, "/scope")
        else:
            return
        carry = ctx.carry(sc)
        if carry is not None:
            before, cited, path = ctx.current_state(carry[0]), carry[1], "carry_over"
            bfields = [afield, Field(sc, "/before_sha256"), Field(sc, "/after")]
        elif ctx.node(f"{lsc}.before") is not None:
            before, cited, path = f"{lsc}.before", (), None
            bfields = [afield, Field(sc, "/before_sha256")]
        else:
            before = None
        after = f"{lsc}.after" if ctx.node(f"{lsc}.after") is not None else None
        # carried-over state changes with one cause and one predecessor state support one usage (and, when they
        # change it, one invalidation): one statement citing each of them, not a collision (regen item 165)
        merge = carry is not None
        if before is not None:
            ctx.rel("used", rule, {"prov:activity": activity, "prov:entity": before}, [role("apv:InitialState")],
                    fields=bfields, path=path, cited=cited, merge=merge)
        if after is not None:
            afields = [afield, Field(sc, "/after_sha256")]
            ctx.rel("wasGeneratedBy", rule, {"prov:entity": after, "prov:activity": activity}, fields=afields)
            if before is not None:
                ctx.rel("wasDerivedFrom", rule, {"prov:generatedEntity": after, "prov:usedEntity": before},
                        [Attr("prov:type", q("prov:Revision"))], fields=[*afields, *bfields[1:]], path=path, cited=cited)
                if rule == "aprov.env_call@1":
                    ctx.rel("wasInvalidatedBy", rule, {"prov:entity": before, "prov:activity": activity},
                            fields=[*afields, *bfields[1:]], path=path, cited=cited, merge=merge)
    elif ctx.present(sc, "/patch") and ctx.node(f"{lsc}.after") is not None:
        after = f"{lsc}.after"
        if ctx.present(sc, "/cause"):
            cause = str(r["cause"])
            if ctx.kind(cause) in ("tool_execution", "scope", "decision", "model_call") and ctx.node(local(cause)):
                ctx.rel("wasGeneratedBy", "aprov.state_patch@1", {"prov:entity": after, "prov:activity": local(cause)},
                        fields=[Field(sc, "/patch"), Field(sc, "/cause")])
        pred = ctx.patch_pred(sc)
        if pred is not None and ctx.node(f"{local(pred)}.after") is not None:
            ctx.rel("wasDerivedFrom", "aprov.state_patch@1",
                    {"prov:generatedEntity": after, "prov:usedEntity": f"{local(pred)}.after"},
                    [Attr("prov:type", q("prov:Revision"))], fields=[Field(sc, "/patch"), Field(sc, "/after")])


def _entity_of(ctx: Ctx, target: str) -> str | None:
    """The entity node an input reference denotes (G-USE, checker inputs); ``None`` for non-entities (NE-19)."""
    if is_part_id(target):
        return local(target) if ctx.node(local(target)) is not None else None
    kind = ctx.kind(target)
    if kind in ENTITY_KINDS:
        return local(target)
    if kind == "state_change":
        return ctx.current_state(target)
    return None


def _judgement(ctx: Ctx, j: str, r: dict[str, Any]) -> None:
    lj = local(j)
    origin = r.get("origin") if ctx.present(j, "/origin") else None
    actor = local(str(r["actor"])) if ctx.present(j, "/actor") else None
    inputs = list(r.get("inputs", [])) if ctx.present(j, "/inputs") else None
    of = Field(j, "/origin")
    if origin == "checker" and ctx.present(j, "/generated_by"):
        g = local(str(r["generated_by"]))
        ctx.rel("wasGeneratedBy", "aprov.outcome@1", {"prov:entity": lj, "prov:activity": g},
                fields=[Field(j, "/generated_by"), of])
        _inputs(ctx, j, g, inputs, "apv:CheckedInput")
    elif origin == "checker":
        check = f"{lj}.check"
        ctx.add_node(check, "activity", "aprov.outcome@1", ["apv:CheckerRun"], None, [], fields=[of], nodes=[lj],
                     path="checker_run")
        ctx.rel("wasGeneratedBy", "aprov.outcome@1", {"prov:entity": lj, "prov:activity": check}, fields=[of],
                path="checker_run")
        if actor is not None:
            ctx.rel("wasAssociatedWith", "aprov.outcome@1", {"prov:activity": check, "prov:agent": actor},
                    [role("apv:CheckerRole")], fields=[of, Field(j, "/actor")], path="checker_run")
        if inputs is not None:
            _inputs(ctx, j, check, inputs, "apv:CheckedInput")
        else:
            _assumed_inputs(ctx, j, check)
    elif origin == "harness_default" and actor is not None:
        ctx.rel("wasAttributedTo", "aprov.outcome@1", {"prov:entity": lj, "prov:agent": actor},
                fields=[of, Field(j, "/actor")])
    elif origin == "harness_rule":
        ev = f"{lj}.rule"
        ctx.add_node(ev, "activity", "aprov.outcome@1", ["apv:HarnessRuleEvaluation"], None, [], fields=[of],
                     nodes=[lj], path="checker_run")
        ctx.rel("wasGeneratedBy", "aprov.outcome@1", {"prov:entity": lj, "prov:activity": ev}, fields=[of],
                path="checker_run")
        if actor is not None:
            ctx.rel("wasAssociatedWith", "aprov.outcome@1", {"prov:activity": ev, "prov:agent": actor},
                    fields=[of, Field(j, "/actor")], path="checker_run")
        for k, item in enumerate(inputs or []):
            if isinstance(item, str) and ctx.kind(item) == "judgement" and ctx.present(j, f"/inputs/{k}"):
                fk = Field(j, f"/inputs/{k}")
                ctx.rel("used", "aprov.outcome@1", {"prov:activity": ev, "prov:entity": local(item)},
                        [role("apv:RuleInput")], fields=[of, fk], path="checker_run", disc=f"input={k}")
                ctx.rel("wasDerivedFrom", "aprov.outcome@1",
                        {"prov:generatedEntity": lj, "prov:usedEntity": local(item), "prov:activity": ev},
                        fields=[of, fk], path="checker_run", disc=f"input={k}")
    elif origin == "recomputed":
        if ctx.present(j, "/revises"):
            ctx.rel("wasDerivedFrom", "aprov.outcome@1", {"prov:generatedEntity": lj, "prov:usedEntity": local(str(r["revises"]))},
                    [Attr("prov:type", q("prov:Revision"))], fields=[of, Field(j, "/revises")])
        if actor is not None:
            ctx.rel("wasAttributedTo", "aprov.outcome@1", {"prov:entity": lj, "prov:agent": actor},
                    fields=[of, Field(j, "/actor")])


def _inputs(ctx: Ctx, j: str, activity: str, inputs: list[Any] | None, role_q: str) -> None:
    for k, item in enumerate(inputs or []):
        if not ctx.present(j, f"/inputs/{k}"):
            continue  # D-621 (#16): an item declared unk fires nothing (E.1.5 item 1); its gap records it
        entity = _entity_of(ctx, item) if isinstance(item, str) else None
        if entity is None:
            ctx.skipped(j, f"/inputs/{k}", "checker input is not an entity (no used of an activity, NE-19)")
            continue
        ctx.rel("used", "aprov.outcome@1", {"prov:activity": activity, "prov:entity": entity}, [role(role_q)],
                fields=[Field(j, f"/inputs/{k}")], disc=f"input={k}")


def _assumed_inputs(ctx: Ctx, j: str, check: str) -> None:
    """Checker usages from the checker-input assumptions of the rules the judgement cites (ceiling D, AD-05)."""
    for assumption in CHECKER_ASSUMPTIONS:
        cited = ctx.citing_assumption(j, assumption)
        if not cited:
            continue
        for entity, fields, role_q in ctx.checker_targets(assumption):
            # One entity can fill two checker roles: an unchanged environment is both the pre-state and the post-state
            # (a digest state change whose after equals its before has no `.after` node). The role discriminates the
            # two usages; it enters a statement name only when the (rule, arguments) pair repeats (E.4.2), so records
            # where the roles fall on distinct entities keep their names (phase 8, D.10.4a).
            ctx.rel("used", "aprov.outcome@1", {"prov:activity": check, "prov:entity": entity}, [role(role_q)],
                    fields=[Field(j, "/origin"), *fields], path="assumed_inputs", cited=cited,
                    disc=f"role={role_q}")


def _activity(ctx: Ctx, ac: str, r: dict[str, Any]) -> None:
    lac = local(ac)
    if ctx.present(ac, "/actor"):
        ctx.rel("wasAssociatedWith", "aprov.g_assoc@1", {"prov:activity": lac, "prov:agent": local(str(r["actor"]))},
                [role("apv:PerformerRole")], fields=[Field(ac, "/actor")])
    if ctx.present(ac, "/inputs"):
        for i, item in enumerate(r.get("inputs", [])):
            if not ctx.present(ac, f"/inputs/{i}"):
                continue  # D-621 (#16): an item declared unk fires nothing (E.1.5 item 1); its gap records it
            entity = _entity_of(ctx, item) if isinstance(item, str) else None
            if entity is None:
                ctx.skipped(ac, f"/inputs/{i}", "generic input without an entity node")
                continue
            ctx.rel("used", "aprov.g_use@1", {"prov:activity": lac, "prov:entity": entity},
                    [role("apv:ActivityInput"), Attr("apv:inputIndex", i)], fields=[Field(ac, f"/inputs/{i}")],
                    disc=f"inputIndex={i}")


def _artefact(ctx: Ctx, af: str, r: dict[str, Any]) -> None:
    if ctx.present(af, "/generated_by"):
        ctx.rel("wasGeneratedBy", "aprov.g_gen@1", {"prov:entity": local(af), "prov:activity": local(str(r["generated_by"]))},
                fields=[Field(af, "/generated_by")])


def _rerun(ctx: Ctx) -> None:
    """``aprov.rerun@1``: consecutive passes with known indices, the earlier ending in a null-content reply."""
    passes: dict[str | None, list[tuple[int, str]]] = {}
    for record in ctx.records:
        if record.get("k") == "scope" and record.get("kind") == "attempt" and ctx.present(str(record["id"]), "/index"):
            parent = record.get("parent")
            passes.setdefault(parent if isinstance(parent, str) else None, []).append((int(record["index"]), str(record["id"])))
    for group in passes.values():
        group.sort()
        for (i, p), (i2, p2) in zip(group, group[1:], strict=False):
            if i2 != i + 1:
                continue
            cited = ctx.citing_assumption(p2, "apv:RerunOnEmptyReply") or ctx.citing_assumption(p, "apv:RerunOnEmptyReply")
            last = ctx.last_message(p) if cited else None
            if last is None:
                continue
            parts = (ctx.rec(last) or {}).get("parts", [])
            nulls = [k for k, x in enumerate(parts) if isinstance(x, dict) and x.get("t") == "text" and x.get("text") is None]
            if not nulls or any(isinstance(x, dict) and x.get("t") == "tool_call" for x in parts):
                continue
            args = {"prov:activity": local(p2), "prov:trigger": local(last)}
            fields = [Field(p, "/index"), Field(p2, "/index"), Field(last, f"/parts/{nulls[0]}/text")]
            if ctx.present(last, "/generated_by"):
                args["prov:starter"] = local(str(ctx.val(last, "/generated_by")))
                fields.append(Field(last, "/generated_by"))
            ctx.rel("wasStartedBy", "aprov.rerun@1", args, fields=fields, cited=cited)


# --------------------------------------------------------------------------------------------- order attributes
def after_attributes(ctx: Ctx) -> None:
    """``aprov.after@1``: one ``apv:after<Basis>`` value per ``after`` edge, at the class of ``/after/<i>`` (R-53)."""
    for record in ctx.records:
        rid = str(record.get("id"))
        if not ctx.present(rid, "/after"):
            continue
        node = ctx.node(local(rid))
        if node is None:
            continue
        for i, edge in enumerate(record.get("after", [])):
            if not isinstance(edge, dict):
                continue
            target, basis = edge.get("id"), edge.get("b")
            if not isinstance(target, str) or basis not in AFTER_PROPS:
                continue
            tnode = "exec" if ctx.kind(target) == "execution" else local(target)
            if ctx.node(tnode) is None:
                ctx.skipped(rid, f"/after/{i}", "after edge to a record without a node")
                continue
            node.attrs.append(Attr(AFTER_PROPS[str(basis)], q("x:" + tnode), (Field(rid, f"/after/{i}"),),
                                   rule="aprov.after@1"))


_ = deque  # reserved for a streaming variant of the after-closure
