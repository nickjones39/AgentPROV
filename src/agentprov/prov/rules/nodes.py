"""Node rules of ``agentprov-prov/0.1`` (EF E.1.3), including G-ACT and the generic-artefact entity rule (AD-15).

Each rule declares PROV nodes with their structural attributes and the AER fields they restate. Classes and routing
are the engine's job; a rule only names premises. Status attributes from ``unk`` and gap entities are added by
:func:`statuses` after every node exists (``aprov.status@1``, ``aprov.n_gap@1``).
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any, Final

from agentprov.io.canonical import jcs_bytes, sha256_of_ref
from agentprov.prov._ir import Attr, Field, q
from agentprov.prov.evidence import EvidenceClass
from agentprov.prov.iri import local

if TYPE_CHECKING:
    from agentprov.prov.engine import Ctx

__all__ = ["apply", "statuses"]

D: Final = EvidenceClass.DERIVED

ACTOR_TYPES: Final[dict[str, tuple[str, ...]]] = {
    "llm_agent": ("apv:AgentSystem", "prov:SoftwareAgent"),
    "user": ("apv:User", "prov:Person"),
    "simulated_user": ("apv:SimulatedUser", "prov:SoftwareAgent"),
    "attacker": ("apv:Attacker",),
    "defense": ("apv:Defence", "prov:SoftwareAgent"),
    "judge": ("apv:Judge", "prov:SoftwareAgent"),
    "tool_runtime": ("apv:ToolRuntime", "prov:SoftwareAgent"),
    "environment": ("apv:EnvironmentActor", "prov:SoftwareAgent"),
    "harness": ("apv:Harness", "prov:SoftwareAgent"),
    "benchmark": ("apv:Benchmark", "prov:SoftwareAgent"),
    "other": ("prov:Agent",),
}
ROLE_TYPES: Final = {"planner": "apv:Planner", "generator": "apv:Generator"}
SCOPE_TYPES: Final = {
    "run": "apv:Run",
    "attempt": "apv:Pass",
    "agent_invocation": "apv:AgentInvocation",
    "subagent": "apv:SubagentInvocation",
    "other": "apv:Step",
}
MESSAGE_ROLE_TYPES: Final = {
    "system": "apv:SystemMessage",
    "user": "apv:UserMessage",
    "assistant": "apv:AssistantMessage",
    "tool": "apv:ToolMessage",
    "developer": "apv:DeveloperMessage",
}
PART_TYPES: Final = {
    "text": "apv:TextPart",
    "reasoning": "apv:ReasoningPart",
    "tool_call": "apv:ToolCallRequest",
    "tool_result": "apv:ToolResult",
    "blob": "apv:BlobPart",
    "file": "apv:FilePart",
    "uri": "apv:UriPart",
    "refusal": "apv:RefusalPart",
    "other": "apv:OtherPart",
}
CALL_STATUS: Final = {"kept": "apv:Kept", "discarded": "apv:Discarded", "error": "apv:Error", "cached": "apv:Cached"}
EXEC_STATUS: Final = {"ok": "apv:Ok", "error": "apv:Error", "invalid": "apv:Invalid"}
VERDICTS: Final = {
    "allow": "apv:VerdictAllow",
    "deny": "apv:VerdictDeny",
    "modify": "apv:VerdictModify",
    "redact": "apv:VerdictRedact",
    "escalate": "apv:VerdictEscalate",
    "terminate": "apv:VerdictTerminate",
    "other": "apv:VerdictOther",
}
STATE_TYPES: Final = {
    "environment": "apv:EnvironmentState",
    "agent_store": "apv:StoreState",
    "sandbox": "apv:SandboxState",
    "other": "apv:State",
}
FIXTURE_TYPES: Final[dict[str, tuple[str, ...]]] = {
    "injection_payload": ("apv:InjectionPayload",),
    "environment_seed": ("apv:EnvironmentSeed",),
    "attack_plan": ("apv:AttackPlan", "prov:Plan"),
    "task_prompt": ("apv:TaskPrompt",),
    "system_prompt": ("apv:SystemPrompt",),
    "tool_definitions": ("apv:ToolDefinitions",),
    "ground_truth": ("apv:GroundTruth",),
    "other": (),
}
ORIGINS: Final = {
    "checker": "apv:OriginChecker",
    "harness_default": "apv:OriginHarnessDefault",
    "harness_rule": "apv:OriginHarnessRule",
    "recomputed": "apv:OriginRecomputed",
}
UNK_STATUS: Final = {
    "not_recorded": "apv:NotRecorded",
    "lost": "apv:Lost",
    "overwritten": "apv:Overwritten",
    "withheld": "apv:Withheld",
    "ambiguous": "apv:Ambiguous",
    "not_captured": "apv:NotCaptured",
    "not_applicable": "apv:NotApplicable",
}
#: The fixed status-property map of E.4.5 for record-level pointers (part pointers are handled apart).
STATUS_PROPS: Final[dict[str, tuple[str, ...]]] = {
    "/t": ("apv:startTimeStatus", "apv:endTimeStatus"),
    "/t/start": ("apv:startTimeStatus",),
    "/t/end": ("apv:endTimeStatus",),
    "/input": ("apv:contextStatus",),
    "/request": ("apv:requestStatus",),
    "/response": ("apv:responseStatus",),
    "/usage": ("apv:usageStatus",),
    "/params": ("apv:paramsStatus",),
    "/finish_reason": ("apv:finishReasonStatus",),
    "/model/requested": ("apv:requestedModelStatus",),
    "/model/served": ("apv:servedModelStatus",),
    "/served_model": ("apv:servedModelStatus",),
    "/args_effective": ("apv:effectiveArgsStatus",),
    "/index": ("apv:indexStatus",),
    "/after": ("apv:orderStatus",),
}
PART_STATUS_PROPS: Final = {
    "text": "apv:contentStatus",
    "value": "apv:contentStatus",
    "provider_call_id": "apv:providerCallIdStatus",
    "args_raw": "apv:argsRawStatus",
}
TEXT_PARTS: Final = frozenset({"text", "reasoning", "refusal", "tool_result"})


def lit(value: Any) -> Any:
    """An AER value as a PROV-JSON attribute value: strings, integers and booleans natively, floats as
    ``xsd:double``, an asserted ``null`` as ``apv:RecordedNull`` and objects or arrays as their JCS string.

    :func:`opt` never passes a null to an ``apv:`` data property: it states it on the property's status sibling."""
    if value is None:
        return q("apv:RecordedNull")
    if isinstance(value, bool | int | str):
        return value
    if isinstance(value, float):
        from agentprov.prov._ir import dbl

        return dbl(value)
    return jcs_bytes(value).decode("utf-8")


def sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha_json(value: Any) -> str:
    return hashlib.sha256(jcs_bytes(value)).hexdigest()


def blob_digest(value: Any) -> str | None:
    if isinstance(value, dict) and isinstance(value.get("$blob"), str):
        try:
            return sha256_of_ref(value["$blob"])
        except ValueError:
            return None
    return None


def times(ctx: Ctx, rid: str) -> list[Attr]:
    """``prov:startTime``/``prov:endTime`` under the E.5.3 item 7 predicate, else the lexical form; ``dur_s``.

    An inferred time is never a PROV time (D-28 addendum): a ``/t/start`` or ``/t/end`` whose class is I gives no
    attribute at all (neither the PROV time nor its lexical form) and a disclosure ``inferred_time_omitted``; the AER
    keeps the value and its reading."""
    from agentprov.prov._ir import dbl
    from agentprov.prov.serialise.time import prov_time

    out: list[Attr] = []
    for end, prop, lex in (("start", "prov:startTime", "apv:startTimeLexical"), ("end", "prov:endTime", "apv:endTimeLexical")):
        ptr = f"/t/{end}"
        if ctx.present(rid, ptr) and ctx.field_class(Field(rid, ptr)) == EvidenceClass.INFERRED:
            ctx.disclose("inferred_time_omitted", f"{rid}{ptr}", "an I-class time is not a PROV time (D-28 addendum)")
        elif ctx.present(rid, ptr):
            value = ctx.val(rid, ptr)
            iso = prov_time(value)
            out.append(Attr(prop, iso, (Field(rid, ptr),)) if iso else Attr(lex, value, (Field(rid, ptr),)))
        elif ctx.present(rid, f"/t/{end}_naive"):
            out.append(Attr(lex, ctx.val(rid, f"/t/{end}_naive"), (Field(rid, f"/t/{end}_naive"),)))
    if ctx.present(rid, "/t/dur_s"):
        dur = ctx.val(rid, "/t/dur_s")
        if isinstance(dur, int | float) and not isinstance(dur, bool):
            out.append(Attr("apv:durationSeconds", dbl(float(dur)), (Field(rid, "/t/dur_s"),)))
    return out


def opt(ctx: Ctx, rid: str, ptr: str, prop: str, conv: Any = lit) -> list[Attr]:
    """``prop`` restating the field ``ptr`` when it is present.

    An asserted ``null`` under the default converter is ``<prop>Status apv:RecordedNull`` instead, and ``prop`` is
    omitted: an ``apv:`` data property never takes an IRI object (E.5 item 5, E.4.5; apv 0.2.0, D-500)."""
    if not ctx.present(rid, ptr):
        return []
    value = ctx.val(rid, ptr)
    if value is None and conv is lit and prop.startswith("apv:"):
        return [Attr(f"{prop}Status", q("apv:RecordedNull"), (Field(rid, ptr),))]
    return [Attr(prop, conv(value), (Field(rid, ptr),))]


def ref_attr(ctx: Ctx, rid: str, ptr: str, prop: str, rule: str | None = None) -> list[Attr]:
    """An attribute whose value is the QName of the node of the referenced AER id."""
    if not ctx.present(rid, ptr):
        return []
    target = ctx.val(rid, ptr)
    if not isinstance(target, str) or ctx.node(local(target)) is None:
        ctx.skipped(rid, ptr, "reference to a record without a node")
        return []
    return [Attr(prop, q("x:" + local(target)), (Field(rid, ptr),), rule=rule)]


# --------------------------------------------------------------------------------------------- the rules
def apply(ctx: Ctx) -> None:
    for record in ctx.records:
        kind = record.get("k")
        rid = str(record.get("id"))
        handler = _HANDLERS.get(str(kind))
        if handler is not None:
            handler(ctx, rid, record)


def _header(ctx: Ctx, rid: str, r: dict[str, Any]) -> None:
    attrs = [Attr("apv:executionId", r["ex"]), Attr("apv:mode", r["mode"]), Attr("apv:executionUnit", r["unit"])]
    for name, prop in (
        ("benchmark", "apv:benchmark"),
        ("environment", "apv:environment"),
        ("task_id", "apv:taskId"),
        ("attack_id", "apv:attackId"),
        ("attack_target_id", "apv:attackTargetId"),
        ("defense_id", "apv:defenceId"),
    ):
        attrs += opt(ctx, rid, f"/task/{name}", prop)
    if ctx.present(rid, "/instrumentation"):
        for i, item in enumerate(r.get("instrumentation", [])):
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                attrs.append(Attr("apv:instrumentation", item["id"], (Field(rid, f"/instrumentation/{i}"),)))
    ctx.add_node("exec", "entity", "aprov.n_header@1", ["apv:ExecutionDescription"], rid, attrs)


def _actor(ctx: Ctx, rid: str, r: dict[str, Any]) -> None:
    kind = str(r.get("kind", "other")) if ctx.present(rid, "/kind") else "other"
    types = list(ACTOR_TYPES.get(kind, ("prov:Agent",)))
    attrs: list[Attr] = []
    if isinstance(r.get("role"), str) and r["role"] in ROLE_TYPES and ctx.present(rid, "/role"):
        attrs.append(Attr("prov:type", q(ROLE_TYPES[r["role"]]), (Field(rid, "/role"),)))
    attrs += opt(ctx, rid, "/name", "apv:name") + opt(ctx, rid, "/role", "apv:actorRole")
    attrs += opt(ctx, rid, "/subtype", "apv:subtype") + opt(ctx, rid, "/version", "apv:version")
    lid = local(rid)
    ctx.add_node(lid, "agent", "aprov.n_actor@1", types, rid, attrs)
    if ctx.present(rid, "/model"):
        mattrs = opt(ctx, rid, "/model/requested", "apv:requestedModel")
        mattrs += opt(ctx, rid, "/model/served", "apv:servedModel") + opt(ctx, rid, "/model/provider", "apv:provider")
        ctx.add_node(f"{lid}.model", "entity", "aprov.n_model@1", ["apv:Model"], None, mattrs,
                     fields=[Field(rid, "/model")], nodes=[lid])


def _service_agents(ctx: Ctx) -> None:
    """``x:L(a).svc`` for actors whose served model or provider is recorded, on the actor or on any of its calls."""
    witnesses: dict[str, list[Field]] = {}
    for record in ctx.records:
        rid = str(record.get("id"))
        if record.get("k") == "actor":
            for ptr in ("/model/served", "/model/provider"):
                if ctx.present(rid, ptr):
                    witnesses.setdefault(rid, []).append(Field(rid, ptr))
        elif record.get("k") == "model_call" and ctx.present(rid, "/served_model") and ctx.present(rid, "/actor"):
            witnesses.setdefault(str(record["actor"]), []).append(Field(rid, "/served_model"))
    for actor, fields in witnesses.items():
        if ctx.node(local(actor)) is None:
            continue
        best = max(fields, key=lambda f: (ctx.field_class(f), -ctx.pos(f.rid)))  # strongest witness, earliest record
        ctx.add_node(f"{local(actor)}.svc", "agent", "aprov.n_model@1", ["prov:SoftwareAgent", "apv:ModelService"],
                     None, [], fields=[best], nodes=[local(actor)], path="service")


def _scope(ctx: Ctx, rid: str, r: dict[str, Any]) -> None:
    kind = str(r.get("kind"))
    if kind == "thread":
        return
    attrs = [*times(ctx, rid)]
    if kind == "other":
        attrs += opt(ctx, rid, "/subtype", "apv:subtype")
    attrs += opt(ctx, rid, "/index", "apv:index") + opt(ctx, rid, "/scored", "apv:scored")
    attrs += opt(ctx, rid, "/status", "apv:scopeStatus")
    ctx.add_node(local(rid), "activity", "aprov.n_scope@1", [SCOPE_TYPES.get(kind, "apv:Step")], rid, attrs)


def _message(ctx: Ctx, rid: str, r: dict[str, Any]) -> None:
    role = r.get("role")
    types = ["apv:Message"]
    attrs: list[Attr] = []
    if isinstance(role, str) and role in MESSAGE_ROLE_TYPES:
        attrs.append(Attr("prov:type", q(MESSAGE_ROLE_TYPES[role]), (Field(rid, "/role"),)))
    elif isinstance(role, str):
        attrs.append(Attr("prov:type", q("apv:OtherRoleMessage"), (Field(rid, "/role"),)))
        attrs.append(Attr("apv:messageRole", role, (Field(rid, "/role"),)))
    parts: list[Any] = r["parts"] if isinstance(r.get("parts"), list) else []
    if any(isinstance(p, dict) and p.get("t") == "tool_call" for p in parts):
        types.append("prov:Collection")
    if ctx.present(rid, "/parts"):
        attrs.append(Attr("apv:contentSha256", sha_json(parts), (Field(rid, "/parts"),)))
        attrs.append(Attr("apv:partCount", len(parts), (Field(rid, "/parts"),)))
    lid = local(rid)
    ctx.add_node(lid, "entity", "aprov.n_message@2", types, rid, attrs)  # its /scope: message_scopes (after all nodes)
    for k, part in enumerate(parts):
        if isinstance(part, dict):
            _part(ctx, rid, k, part)


def _part(ctx: Ctx, mid: str, k: int, p: dict[str, Any]) -> None:
    base = f"/parts/{k}"
    t = str(p.get("t"))
    attrs = [Attr("prov:type", q(PART_TYPES.get(t, "apv:OtherPart"))), Attr("apv:partIndex", k)]
    if t in TEXT_PARTS and "text" in p:
        ptr = f"{base}/text"
        if ctx.present(mid, ptr):  # a value under `unk` (even `ambiguous`) is not restated; its status is
            text = p.get("text")
            if text is None:
                attrs.append(Attr("apv:contentStatus", q("apv:RecordedNull"), (Field(mid, ptr),)))
            elif isinstance(text, str):
                attrs.append(Attr("apv:contentSha256", sha_text(text), (Field(mid, ptr),)))
                attrs.append(Attr("apv:contentLength", len(text), (Field(mid, ptr),)))
                if ctx.options.emit_content:
                    attrs.append(Attr("apv:text", text, (Field(mid, ptr),)))
    if "value" in p and ctx.present(mid, f"{base}/value"):
        attrs.append(Attr("apv:contentSha256", sha_json(p["value"]), (Field(mid, f"{base}/value"),)))
    if t == "tool_call":
        attrs += opt(ctx, mid, f"{base}/name", "apv:toolName") + opt(ctx, mid, f"{base}/args", "apv:args", _jcs)
        attrs += opt(ctx, mid, f"{base}/provider_call_id", "apv:providerCallId")
        attrs += opt(ctx, mid, f"{base}/args_raw", "apv:argsRawSha256", sha_text)
    elif t == "tool_result":
        attrs += opt(ctx, mid, f"{base}/error", "apv:error") + opt(ctx, mid, f"{base}/name", "apv:toolName")
    elif t == "other":
        attrs += opt(ctx, mid, f"{base}/type", "apv:subtype")
    elif t == "blob":
        digest = blob_digest(p.get("data"))
        if digest and ctx.present(mid, f"{base}/data"):
            attrs.append(Attr("apv:contentSha256", digest, (Field(mid, f"{base}/data"),)))
        attrs += opt(ctx, mid, f"{base}/media", "apv:mediaType")
    elif t == "file":
        attrs += opt(ctx, mid, f"{base}/media", "apv:mediaType")
    pid = f"{mid}#{k}"
    if t != "tool_call":
        attrs += [Attr("apv:partOf", q("x:" + local(mid)), (Field(mid, base),), rule="aprov.part_of@1")]
    dispatch = ctx.dispatch_status(pid)
    if dispatch is not None:
        attrs.append(dispatch)
    ctx.add_node(local(pid), "entity", "aprov.n_part@1", ["apv:MessagePart"], None, attrs,
                 fields=[Field(mid, base)], nodes=[local(mid)])


def _jcs(value: Any) -> str:
    return jcs_bytes(value).decode("utf-8")


def _model_call(ctx: Ctx, rid: str, r: dict[str, Any]) -> None:
    status = r.get("status") if ctx.present(rid, "/status") else None
    types = ["apv:CacheRead"] if status == "cached" else ["apv:ModelInvocation"]
    attrs = [*times(ctx, rid)]
    if status in CALL_STATUS:
        attrs.append(Attr("apv:callStatus", q(CALL_STATUS[str(status)]), (Field(rid, "/status"),)))
    if ctx.unk_reason(rid, "/status") == "lost":
        attrs.append(Attr("apv:outputStatus", q("apv:Lost"), (Field(rid, "/status"),), ceiling=D))
    attrs += opt(ctx, rid, "/role", "apv:callRole") + opt(ctx, rid, "/reason", "apv:reason")
    attrs += ref_attr(ctx, rid, "/retry_of", "apv:retryOf")
    attrs += opt(ctx, rid, "/finish_reason", "apv:finishReason") + opt(ctx, rid, "/usage", "apv:usage", _jcs)
    attrs += opt(ctx, rid, "/params/configured", "apv:paramsConfigured", _jcs)
    attrs += opt(ctx, rid, "/params/transmitted", "apv:paramsTransmitted", _jcs)
    attrs += opt(ctx, rid, "/response_id", "apv:responseId")
    for ptr, prop in (("/request", "apv:requestBlob"), ("/response", "apv:responseBlob")):
        if ctx.present(rid, ptr) and isinstance(r.get(ptr[1:]), dict) and isinstance(r[ptr[1:]].get("$blob"), str):
            attrs.append(Attr(prop, r[ptr[1:]]["$blob"], (Field(rid, ptr),)))
    attrs += _scope_ref(ctx, rid)
    lid = local(rid)
    ctx.add_node(lid, "activity", "aprov.n_model_call@1", types, rid, attrs)
    if ctx.present(rid, "/served_model"):
        ctx.add_node(f"{lid}.model", "entity", "aprov.n_model@1", ["apv:Model"], None,
                     opt(ctx, rid, "/served_model", "apv:servedModel"), fields=[Field(rid, "/served_model")], nodes=[lid])


def _scope_ref(ctx: Ctx, rid: str) -> list[Attr]:
    """``apv:partOf`` the scope activity (non-thread), else ``apv:thread`` (the thread's local id)."""
    if not ctx.present(rid, "/scope"):
        return []
    scope = str(ctx.val(rid, "/scope"))
    if ctx.node(local(scope)) is not None:
        return [Attr("apv:partOf", q("x:" + local(scope)), (Field(rid, "/scope"),), rule="aprov.part_of@1")]
    rec = ctx.rec(scope)
    if rec is not None and rec.get("kind") == "thread":
        return [Attr("apv:thread", local(scope), (Field(rid, "/scope"),), rule="aprov.part_of@1")]
    return []


def _tool_execution(ctx: Ctx, rid: str, r: dict[str, Any]) -> None:
    attrs = [*times(ctx, rid)] + opt(ctx, rid, "/name", "apv:toolName")
    if ctx.present(rid, "/status") and r.get("status") in EXEC_STATUS:
        attrs.append(Attr("apv:execStatus", q(EXEC_STATUS[str(r["status"])]), (Field(rid, "/status"),)))
    if ctx.present(rid, "/args_effective"):
        request_args = ctx.call_args(rid)
        if request_args is None or jcs_bytes(request_args) != jcs_bytes(r["args_effective"]):
            attrs += opt(ctx, rid, "/args_effective", "apv:argsEffective", _jcs)
    attrs += opt(ctx, rid, "/exception", "apv:exception", _jcs) + _scope_ref(ctx, rid)
    ctx.add_node(local(rid), "activity", "aprov.n_tool_execution@1", ["apv:ToolExecution"], rid, attrs)


def _decision(ctx: Ctx, rid: str, r: dict[str, Any]) -> None:
    attrs = [*times(ctx, rid)]
    if ctx.present(rid, "/verdict") and r.get("verdict") in VERDICTS:
        attrs.append(Attr("apv:verdict", q(VERDICTS[str(r["verdict"])]), (Field(rid, "/verdict"),)))
        if r["verdict"] == "other":
            attrs += opt(ctx, rid, "/subtype", "apv:subtype")
    attrs += opt(ctx, rid, "/reason", "apv:reason") + _scope_ref(ctx, rid)
    subject = r.get("subject") if ctx.present(rid, "/subject") else None
    if isinstance(subject, str) and ctx.kind(subject) == "model_call":
        attrs += ref_attr(ctx, rid, "/subject", "apv:decisionSubject")  # an activity subject: attribute only (NE-19)
    ctx.add_node(local(rid), "activity", "aprov.n_decision@1", ["apv:Decision"], rid, attrs)


def _state_change(ctx: Ctx, rid: str, r: dict[str, Any]) -> None:
    target = str(r.get("target", "other"))
    types = [STATE_TYPES.get(target, "apv:State")]
    extra = opt(ctx, rid, "/subtype", "apv:subtype") if target == "other" else []
    lid = local(rid)
    before = r.get("before_sha256") if ctx.present(rid, "/before_sha256") else None
    after = r.get("after_sha256") if ctx.present(rid, "/after_sha256") else None
    patch_attrs: list[Attr] = []
    if ctx.present(rid, "/patch"):
        patch_attrs.append(Attr("apv:patchSha256", sha_json(r["patch"]), (Field(rid, "/patch"),)))
    elif ctx.present(rid, "/diff/value"):
        patch_attrs.append(Attr("apv:patchSha256", sha_json(r["diff"]["value"]), (Field(rid, "/diff/value"),)))
    patch_attrs += opt(ctx, rid, "/diff/truncated", "apv:truncated")
    if before is not None or after is not None:
        if before is not None and not ctx.carried_over(rid):
            ctx.add_node(f"{lid}.before", "entity", "aprov.n_state@1", types, None,
                         [Attr("apv:stateSha256", before, (Field(rid, "/before_sha256"),)), *extra],
                         fields=[Field(rid, "/before_sha256")], nodes=[])
        if after is not None and after != before:
            ctx.add_node(f"{lid}.after", "entity", "aprov.n_state@1", types, None,
                         [Attr("apv:stateSha256", after, (Field(rid, "/after_sha256"),)), *extra, *patch_attrs],
                         fields=[Field(rid, "/after_sha256")], nodes=[])
    elif ctx.present(rid, "/patch"):
        ctx.add_node(f"{lid}.after", "entity", "aprov.state_patch@1", types, None, [*extra, *patch_attrs],
                     fields=[Field(rid, "/patch")], nodes=[])


def _fixture(ctx: Ctx, rid: str, r: dict[str, Any]) -> None:
    kind = str(r.get("kind", "other"))
    types = ["apv:Fixture", *FIXTURE_TYPES.get(kind, ())]
    attrs = opt(ctx, rid, "/subtype", "apv:subtype") if kind == "other" else []
    attrs += opt(ctx, rid, "/vector", "apv:vector") + opt(ctx, rid, "/media", "apv:mediaType")
    if ctx.present(rid, "/content"):
        digest = blob_digest(r["content"]) or sha_json(r["content"])
        attrs.append(Attr("apv:contentSha256", digest, (Field(rid, "/content"),)))
    ctx.add_node(local(rid), "entity", "aprov.n_fixture@1", types, rid, attrs)


def _judgement(ctx: Ctx, rid: str, r: dict[str, Any]) -> None:
    attrs = opt(ctx, rid, "/name", "apv:outcomeName") + opt(ctx, rid, "/value", "apv:outcomeValue")
    if ctx.present(rid, "/origin") and r.get("origin") in ORIGINS:
        attrs.append(Attr("apv:outcomeOrigin", q(ORIGINS[str(r["origin"])]), (Field(rid, "/origin"),)))
    ctx.add_node(local(rid), "entity", "aprov.n_judgement@1", ["apv:Outcome"], rid, attrs)


def _artefact(ctx: Ctx, rid: str, r: dict[str, Any]) -> None:
    ctx.refuse_generic_misuse(rid, r)
    attrs = opt(ctx, rid, "/type", "apv:artefactType") + opt(ctx, rid, "/media", "apv:mediaType")
    if ctx.present(rid, "/sha256"):
        attrs.append(Attr("apv:contentSha256", r["sha256"], (Field(rid, "/sha256"),)))
    elif ctx.present(rid, "/content_ref") and blob_digest(r["content_ref"]):
        attrs.append(Attr("apv:contentSha256", blob_digest(r["content_ref"]), (Field(rid, "/content_ref"),)))
    elif ctx.present(rid, "/content"):
        attrs.append(Attr("apv:contentSha256", sha_json(r["content"]), (Field(rid, "/content"),)))
    ctx.add_node(local(rid), "entity", "aprov.n_artefact@1", ["apv:GenericArtefact"], rid, attrs)


def _activity(ctx: Ctx, rid: str, r: dict[str, Any]) -> None:
    ctx.refuse_generic_misuse(rid, r)
    attrs = [*times(ctx, rid)] + opt(ctx, rid, "/type", "apv:activityType") + opt(ctx, rid, "/label", "prov:label")
    attrs += opt(ctx, rid, "/status", "apv:activityStatus") + _scope_ref(ctx, rid)
    ctx.add_node(local(rid), "activity", "aprov.g_act@1", ["apv:GenericActivity"], rid, attrs)


_HANDLERS: Final = {
    "execution": _header,
    "actor": _actor,
    "scope": _scope,
    "message": _message,
    "model_call": _model_call,
    "tool_execution": _tool_execution,
    "decision": _decision,
    "state_change": _state_change,
    "fixture": _fixture,
    "judgement": _judgement,
    "artefact": _artefact,
    "activity": _activity,
}


def scope_parents(ctx: Ctx) -> None:
    """``apv:partOf`` from a scope to its parent (``aprov.part_of@1``); after every scope node exists."""
    for record in ctx.records:
        if record.get("k") == "scope" and record.get("kind") != "thread":
            rid = str(record["id"])
            node = ctx.node(local(rid))
            if node is not None:
                node.attrs += ref_attr(ctx, rid, "/parent", "apv:partOf", rule="aprov.part_of@1")


def message_scopes(ctx: Ctx) -> None:
    """``apv:partOf`` / ``apv:thread`` of each message node from its ``/scope`` (``aprov.n_message@2``, E.1.3, E.1.4;
    D-621 #17, user decision 2026-10-22), after every scope node exists, as ``scope_parents`` does."""
    for record in ctx.records:
        if record.get("k") == "message":
            rid = str(record["id"])
            node = ctx.node(local(rid))
            if node is not None:
                node.attrs += _scope_ref(ctx, rid)


def capture_profile(ctx: Ctx) -> None:
    """``x:capture-profile`` with the seal's accounting status and issue codes (DERIVED, core)."""
    seal = ctx.seal
    attrs: list[Attr] = []
    accounting = seal.get("accounting")
    if isinstance(accounting, dict) and isinstance(accounting.get("status"), str):
        attrs.append(Attr("apv:accounting", accounting["status"]))
    for issue in seal.get("issues", []):
        if isinstance(issue, dict) and isinstance(issue.get("code"), str):
            attrs.append(Attr("apv:issue", issue["code"]))
    ctx.add_node("capture-profile", "entity", "aprov.n_capture_profile@1", ["apv:CaptureProfile"], None, attrs,
                 fields=[], nodes=[])


def model_services(ctx: Ctx) -> None:
    _service_agents(ctx)


# --------------------------------------------------------------------------------------------- statuses and gaps
def statuses(ctx: Ctx) -> None:
    """``aprov.status@1`` and ``aprov.n_gap@1`` for every ``unk`` pointer of a record with a node (E.4.5)."""
    for record in ctx.records:
        rid = str(record.get("id"))
        unk = record.get("unk")
        if not isinstance(unk, dict) or not unk:
            continue
        for ptr in sorted(unk):
            reason = unk[ptr]
            status = UNK_STATUS.get(str(reason))
            if status is None:
                continue
            target, props = _status_target(ctx, rid, record, ptr)
            if target is None:
                ctx.skipped(rid, ptr, "unknown on a record without a node")
                continue
            fields = (Field(rid, ptr),)
            if props:
                for prop in props:
                    target.attrs.append(Attr(prop, q(status), fields, rule="aprov.status@1", ceiling=D))
            else:
                ctx.add_gap(target.name or "", rid, ptr, status)


def _status_target(ctx: Ctx, rid: str, record: dict[str, Any], ptr: str) -> tuple[Any, tuple[str, ...]]:
    lid = "exec" if record.get("k") == "execution" else local(rid)
    tokens = ptr.split("/")
    if record.get("k") == "message" and len(tokens) >= 4 and tokens[1] == "parts" and tokens[2].isascii() and tokens[2].isdigit():
        node = ctx.node(f"{lid}-{tokens[2]}")
        prop = PART_STATUS_PROPS.get(tokens[3]) if len(tokens) == 4 else None
        return node, ((prop,) if prop else ())
    if ptr in ("/model/requested", "/model/served") and ctx.node(f"{lid}.model") is not None:
        return ctx.node(f"{lid}.model"), STATUS_PROPS[ptr]
    if ptr == "/original" and record.get("k") == "decision":
        for derived in ctx.decision_subject_nodes(rid):
            return derived, ("apv:contentStatus",)
        return ctx.node(lid), ()
    if ptr == "/args" and record.get("k") == "tool_execution":
        return ctx.node(lid), ("apv:requestedArgsStatus",)
    if ptr.startswith("/params"):
        return ctx.node(lid), ("apv:paramsStatus",)
    return ctx.node(lid), STATUS_PROPS.get(ptr, ())
