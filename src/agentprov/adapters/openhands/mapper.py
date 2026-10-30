"""Mapper ``openhands.events``: one OpenHands event list -> AER ``aer/0.1`` (docs/architecture D.17.3-D.17.8; DECISIONS
D-170-D-179).

One trajectory file is one execution (content-addressed id). Records, in order (backward references only, C.5.2):

1. the header: task coordinates from the path (O, origin locator; RedCode's request type C1-C3 from the target, D),
   ``ext.openhands`` (path facets, variant, version fields, id gaps, first and last event times, joins, state fields);
2. actors ``bench``, ``harness``, ``user``, ``fake_user`` (OpenAgentSafety simulated-user replies), ``agent``, ``env``,
   ``npc<k>`` (OpenAgentSafety chat partners) and one judge per judging source;
3. scopes ``run`` (raw first and last event times, status) and ``att0``;
4. fixtures: the logged system prompt and tool list (``oh-1.5``), the task prompt (RedCode: the deposit's request, D by
   the join; OpenAgentSafety: ``task.md`` at the pin, I);
5. the events in array order. Each distinct ``model_response`` is a ``model_call`` (O) followed by one assistant message
   holding its reasoning, text and every tool call (``finish`` kept verbatim as an ``openhands.finish_call`` part); a
   text reply without a response object is a class-I call and its message; an observation whose ``cause`` names a tool
   action is that action's ``tool_execution`` and a ``tool`` message answering its call; recall steps, controller
   notices and uncaused errors are harness activities with their artefacts;
6. the judgements (OpenAgentSafety checkpoints and LLM-judge entries, RedCode scores; values verbatim).

A post-pass applies the profile's ``[[family.openhands.redact]]`` rules to the finished tool messages (D-604, D-606;
:mod:`agentprov.adapters.openhands.redact`): third-party account segments in tool output become salted labels, with one
info issue ``openhands.value_redacted``. Model-authored text is never redacted.

The D rules that rest on OpenHands behaviour are cited at D only where the profile's ``verified_code`` names a commit
their catalogue entry cites, else through their ``_unverified`` twins (:mod:`agentprov.adapters.openhands.citation`).
Nothing is invented: no time is converted or placed (naive event times stay verbatim in ``ext``), no call id, no model
id, no status. Strings over 1 MiB and set-of-marks screenshots are not inlined (D-179).

Pure (A-2): the output is a function of the unit's bytes, the auxiliary bytes, this code, the profile and the catalogues.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from agentprov.adapters.openhands import ADAPTER_ID, DIALECT_ID, NAMESPACE, VARIANT_OH15, VARIANTS
from agentprov.adapters.openhands.citation import citations
from agentprov.adapters.openhands.dialect import OAS, PathFacets, event_kind, parse_path
from agentprov.adapters.openhands.redact import RULE as R_REDACTED
from agentprov.adapters.openhands.redact import Redactor, parse_redact_rules
from agentprov.adapters.protocols import AerRecord, MappingContext
from agentprov.adapters.types import ArtefactRef, ExecutionUnit
from agentprov.aer.canon import LexHints, encode_value, json_pointer
from agentprov.aer.ids import part_id
from agentprov.errors import AgentProvError, IngestError, MalformedArtefact
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads

__all__ = ["ADAPTER_ID", "ADAPTER_VERSION", "CATALOGUES", "NAMESPACES", "OpenHandsMapper", "STATE_FIELDS"]

ADAPTER_VERSION: Final = "0.1.0"
CATALOGUES: Final = ("aer", NAMESPACE)
NAMESPACES: Final = {NAMESPACE: "https://w3id.org/agentprov/ns/openhands#"}
MIB: Final = 1 << 20
#: Placeholder values a typed field never holds (C.7.3): the validator's list (aer.validate) and this family's extras
#: (regen item 34, bug pass BF-23: "0" and "-" were missing, so such a name turned the run into an adapter_defect).
_SENTINELS: Final = frozenset({"", "0", "unknown", "none", "null", "n/a", "na", "-", "undefined", "nan"})
_WS: Final = re.compile(r"\s+")
#: The declared regular expressions over the OpenAgentSafety state repr string (``openhands.state_repr_fields@1``).
STATE_FIELDS: Final = {
    "agent_state": re.compile(r"agent_state=<AgentState\.[A-Z_]{1,40}: '([a-z_]{1,40})'>"),
    "max_iterations": re.compile(r"\bmax_iterations=([0-9]{1,6})\b"),
}
#: The harness's rewrite of RedCode prompts before they reach the agent (``OH_evaluation/OH.py``
#: ``_remap_sys_kernel_paths``; ``openhands.redcode_prompt_join@1``).
_SYS_KERNEL: Final = re.compile(r"(?<!/app)/sys/kernel")

# rule ids (catalogue openhands, version 2; openhands.value_redacted@1 is imported from the redact module)
R_CAUSE: Final = "openhands.cause_link@1"
R_EXEC: Final = "openhands.observation_is_execution@1"
R_FROM_CALL: Final = "openhands.action_from_tool_call@1"
R_RECALL_CAUSE: Final = "openhands.recall_cause@1"
R_NOTICE: Final = "openhands.not_executed_notice@1"
R_ORDER: Final = "openhands.event_order@1"
R_TIME: Final = "openhands.event_time_naive_local@1"
R_RESPONSE: Final = "openhands.response_message@1"
R_KEPT: Final = "openhands.response_kept@1"
R_USAGE: Final = "openhands.usage_fields@1"
R_ARGS: Final = "openhands.arguments_decoded@1"
R_SERVED: Final = "openhands.served_model@1"
R_FINISH: Final = "openhands.finish_control_call@1"
R_GAPS: Final = "openhands.filtered_events@1"
R_FIXED: Final = "openhands.fixed_reply_digest@1"
R_NOT_INLINED: Final = "openhands.content_not_inlined@1"
R_OAS_EVAL: Final = "openhands.oas_eval_path_join@1"
R_OAS_SUMMARY: Final = "openhands.oas_summary_join@1"
R_OAS_TASK: Final = "openhands.oas_task_dir_join@1"
R_SEEN: Final = "openhands.task_text_seen@1"
R_STATE: Final = "openhands.state_repr_fields@1"
R_RC_SCORE: Final = "openhands.redcode_score_join@1"
R_RC_PROMPT: Final = "openhands.redcode_prompt_join@1"
R_RC_TYPE: Final = "openhands.redcode_request_type@1"
R_CONTEXT: Final = "openhands.context_is_logged_prefix_unverified@1"
R_TOOLS: Final = "openhands.logged_tools_offered_unverified@1"
R_TEXT_MODEL: Final = "openhands.text_message_is_model_output_unverified@1"
R_FIRST_USER: Final = "openhands.first_message_harness_authored_unverified@1"
R_FAKE_USER: Final = "openhands.fake_user_reply_unverified@1"
R_NPC: Final = "openhands.npc_reply_unverified@1"
R_RECALL: Final = "openhands.recall_is_harness_step@1"
R_LOCK: Final = "openhands.oas_harness_lock_unverified@1"
R_CHECKER: Final = "openhands.checker_recorded_unverified@1"
R_SCORE_ONE: Final = "openhands.redcode_score_one_ambiguous@1"
R_TASK_MD: Final = "openhands.oas_task_md_at_pin_unverified@1"
R_UNCAUSED: Final = "openhands.uncaused_error_is_harness@1"
R_PRINCIPAL: Final = "openhands.simulated_user_principal@1"
R_STATE_STATUS: Final = "openhands.state_run_status@1"
R_GEN: Final = "aer.output_after_generator@1"
R_AFTER_CALL: Final = "aer.execution_after_call@1"

_MODEL_CALL_UNKNOWN: Final = ("/params", "/request", "/response", "/t")
_REQUEST_TYPE: Final = {"S1": "C1", "S2": "C2", "S3": "C3"}


def _p(*tokens: str | int) -> str:
    return json_pointer(*tokens)


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _norm(text: str) -> str:
    return _WS.sub(" ", text).strip()


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()


def _big(value: object) -> bool:
    return isinstance(value, str) and len(value) > MIB // 4 and len(value.encode("utf-8", "surrogatepass")) > MIB


def _not_inlined(value: str, media: str | None = None) -> dict[str, Any]:
    raw = value.encode("utf-8", "surrogatepass")
    out: dict[str, Any] = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    if media is not None:
        out["media"] = media
    return {"not_inlined": out}


def _slim(value: object, pointer: str = "") -> tuple[Any, list[str]]:
    """A copy of ``value`` for an AER field in which every string over 1 MiB is replaced by its digest and size, and the
    JSON pointers (relative to ``value``) of the replacements."""
    if _big(value):
        assert isinstance(value, str)
        return _not_inlined(value), [pointer]
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        found: list[str] = []
        for k, v in value.items():
            out[k], sub = _slim(v, f"{pointer}/{str(k).replace('~', '~0').replace('/', '~1')}")
            found += sub
        return out, found
    if isinstance(value, list):
        items = []
        found = []
        for i, v in enumerate(value):
            item, sub = _slim(v, f"{pointer}/{i}")
            items.append(item)
            found += sub
        return items, found
    return value, []


class _Rec:
    """A record under construction: fields, evidence overrides, scoped rules, unknowns, sources, ext and lex hints."""

    def __init__(self, **fields: Any) -> None:
        self.data: dict[str, Any] = dict(fields)
        self.lex = LexHints()
        self.evf: dict[str, str] = {}
        self.rules: list[str] = []
        self.unk: dict[str, str] = {}
        self.src: list[dict[str, Any]] = []
        self.ext: dict[str, Any] = {}
        self.after: list[dict[str, str]] = []

    @property
    def id(self) -> str:
        return str(self.data["id"])

    def enc(self, value: object, pointer: str) -> Any:
        return encode_value(value, at=pointer, lex=self.lex)

    def set(self, name: str, value: object) -> None:
        self.data[name] = self.enc(value, "/" + name)

    def tag(self, pointer: str, cls: str, rule: str | None = None) -> None:
        self.evf[pointer] = cls
        if rule is not None:
            self.cite(rule)

    def cite(self, rule: str) -> None:
        if rule not in self.rules:
            self.rules.append(rule)

    def loc(self, entry: Mapping[str, Any]) -> None:
        item = dict(entry)
        if item not in self.src:
            self.src.append(item)

    def x(self, key: str, value: object) -> None:
        """``ext.openhands.<key>`` (encoded)."""
        self.ext[key] = self.enc(value, _p("ext", NAMESPACE, key))

    def edge(self, target: str | None, basis: str) -> None:
        if target is not None and {"b": basis, "id": target} not in self.after:
            self.after.append({"b": basis, "id": target})

    def done(self) -> dict[str, Any]:
        out = dict(self.data)
        if self.after:
            out["after"] = list(self.after)
        if self.evf:
            out["evf"] = dict(self.evf)
        if self.rules:
            out["rule"] = list(self.rules)
        if self.src:
            out["src"] = list(self.src)
        if self.unk:
            out["unk"] = dict(self.unk)
        ext: dict[str, Any] = {}
        if self.ext:
            ext[NAMESPACE] = dict(self.ext)
        lex = self.lex.as_dict()
        if lex:
            ext["lex"] = lex
        if ext:
            out["ext"] = ext
        bare_o = out.get("ev") == "O" or any(v == "O" for v in out.get("evf", {}).values())
        if bare_o:
            out.setdefault("by", "source")
        else:
            out.pop("by", None)
        return out


@dataclass
class _Response:
    """One distinct model response: its model call, its assistant message and its tool-call parts by call id."""

    mc: str
    message: str
    parts: dict[str, str] = field(default_factory=dict)  # provider call id -> part id


@dataclass
class _Aux:
    """A loaded auxiliary artefact: header id and the parsed value (or text)."""

    aid: str
    value: Any


class OpenHandsMapper:
    """``Mapper`` for ``openhands.events`` (D.2.4, D.17)."""

    mapper_id: Final = ADAPTER_ID
    version: Final = ADAPTER_VERSION
    accepts: Final = frozenset((DIALECT_ID, v) for v in VARIANTS)
    namespaces: Final = NAMESPACES
    catalogues: Final = CATALOGUES

    def map(self, unit: ExecutionUnit, ctx: MappingContext) -> Iterator[AerRecord]:
        yield from _Build(unit, ctx).run()

    @staticmethod
    def prov_primary(flags: frozenset[str]) -> str:
        """Trajectories are written by the producing harness: ``native``."""
        return "native"

    def degenerate_header(self, unit: ExecutionUnit, ctx: MappingContext, *, issue_code: str, detail: str) -> dict[str, Any]:
        """The header of a degenerate AER (D.2.8 case 3): the task from the path (O, origin locator)."""
        artefact = unit.primary.artefact
        facets, origin_key = _facets_of(artefact)
        if facets is None:
            raise MalformedArtefact("the artefact's path is outside the OpenHands path grammars: no task can be named")
        header = _header_base(unit, ctx, facets, origin_key, [artefact.to_json()], unit.primary.variant or VARIANTS[0])
        ctx.issue(issue_code, ids=["exec"], rule=ctx.rule("openhands.event_order_unverified@1"), severity="error",
                  detail=detail)
        return header


def _facets_of(artefact: ArtefactRef) -> tuple[PathFacets | None, str]:
    data = artefact.origin.data
    for key in ("path", "label"):
        value = data.get(key)
        if isinstance(value, str):
            return parse_path(value), key
    return None, "path"


def _task(facets: PathFacets) -> tuple[dict[str, Any], dict[str, str], list[str]]:
    """``(task, unk, rule pointers)`` of the header (D.17.3)."""
    if facets.source == OAS:
        return ({"benchmark": "openagentsafety", "task_id": str(facets.task)},
                {"/task/attack_id": "not_recorded", "/task/defense_id": "not_recorded"}, [])
    task: dict[str, Any] = {"benchmark": "redcode-exec", "suite": str(facets.language), "task_id": str(facets.case_key),
                            "attack_id": _REQUEST_TYPE[str(facets.target)]}
    return task, {"/task/defense_id": "not_recorded"}, ["/task/attack_id"]


def _header_base(unit: ExecutionUnit, ctx: MappingContext, facets: PathFacets, origin_key: str,
                 artifacts: list[dict[str, Any]], variant: str) -> dict[str, Any]:
    src: list[dict[str, Any]] = [{"a": "a0", "o": f"/{origin_key}"}]
    if "repo" in unit.primary.artefact.origin.data:
        src.append({"a": "a0", "o": "/repo"})
    task, unk, derived = _task(facets)
    header: dict[str, Any] = {
        "k": "execution",
        "id": "exec",
        "aer": "0.1",
        "ex": ctx.ex,
        "mode": unit.mode,
        "unit": "agent_execution",
        "source_key": {"sha256": unit.primary.artefact.sha256, "loc": unit.primary.locator.key()},
        "artifacts": artifacts,
        "adapter": {"id": ADAPTER_ID, "version": ADAPTER_VERSION},
        "dialect": {"id": DIALECT_ID, "variant": variant},
        "profile": ctx.profile.header(),
        "rules": ctx.catalogue_versions(CATALOGUES),
        "ns": dict(NAMESPACES),
        "canon": "jcs-rfc8785",
        "hash": "sha256",
        "task": task,
        "ev": "O",
        "by": "source",
        "src": src,
        "unk": {"/instrumentation": "not_recorded", **unk},
    }
    if derived:
        header["evf"] = {p: "D" for p in derived}
        header["rule"] = [ctx.rule(R_RC_TYPE, p) for p in derived]
    return header


class _Build:
    """One mapping run: every record is built in order, then emitted (backward references only)."""

    def __init__(self, unit: ExecutionUnit, ctx: MappingContext) -> None:
        self.unit, self.ctx = unit, ctx
        item = unit.primary
        if not isinstance(item.value, list):
            raise MalformedArtefact("the located item is not an OpenHands event list")
        if not all(isinstance(e, dict) for e in item.value):
            raise MalformedArtefact("an OpenHands event is not an object")
        self.events: list[dict[str, Any]] = item.value
        self.variant = item.variant
        facets, self.origin_key = _facets_of(item.artefact)
        if facets is None:
            raise MalformedArtefact("the artefact's path is outside the OpenHands path grammars")
        self.f: PathFacets = facets
        self.oas = facets.source == OAS
        self.fam = ctx.profile.family_table()
        self.cite = citations(self.fam, {"variant": self.variant, "source": facets.source}, f"profile {ctx.profile.id!r}")
        self.limits = IngestLimits()
        self.counters: dict[str, int] = {}
        self.artifacts: list[dict[str, Any]] = [item.artefact.to_json()]
        self.aux: dict[str, _Aux] = {}
        self.ext: dict[str, Any] = {}
        self.ext_evf: dict[str, tuple[str, str | None]] = {}
        self.prev: str | None = None
        self.messages: list[str] = []
        self.tools_fixture: str | None = None
        self.npc: dict[str, str] = {}  # npc name -> actor id
        self.responses: dict[str, _Response] = {}
        self.call_of: dict[int, str | None] = {}  # action id -> call part id (None: finish or not in its response)
        self.recall_of: dict[int, str] = {}  # recall action id -> activity id
        self.answered: set[int] = set()
        self.unexecuted: list[str] = []
        self.not_inlined: list[str] = []
        self.user_messages = 0
        self.has_env = False

    # ---------------------------------------------------------------------------------------------- helpers
    def R(self, rule_id: str, pointer: str | None = None) -> str:  # noqa: N802 - mirrors MappingContext.rule
        return self.ctx.rule(self.cite.cite(rule_id), pointer)

    def cls(self, rule_id: str) -> str:
        return self.cite.cls(rule_id)

    def issue(self, code: str, ids: Sequence[str], rule: str, *, severity: str = "warning", detail: str | None = None) -> None:
        self.ctx.issue(code, ids=list(ids), rule=self.R(rule), severity=severity, detail=detail)  # type: ignore[arg-type]

    def next_id(self, prefix: str) -> str:
        n = self.counters.get(prefix, 0)
        self.counters[prefix] = n + 1
        return f"{prefix}{n}"

    def loc(self, pointer: str) -> dict[str, Any]:
        return {"a": "a0", "p": pointer}

    def ext_tag(self, key: str, cls: str, rule: str | None) -> None:
        self.ext_evf[_p("ext", NAMESPACE, *key.split("/"))] = (cls, rule)

    def _order(self, rec: _Rec) -> None:
        """A positional edge to the previous stream record (``openhands.event_order@1``)."""
        if self.prev is not None and self.prev not in {a["id"] for a in rec.after}:
            rec.edge(self.prev, "pos")
            rec.tag("/after", self.cls(R_ORDER), self.R(R_ORDER, "/after"))

    def _stamp(self, rec: _Rec, event: Mapping[str, Any]) -> None:
        stamp = event.get("timestamp")
        if stamp is not None:
            rec.x("timestamp", stamp)
        rec.x("event_id", event.get("id"))

    # ---------------------------------------------------------------------------------------------- auxiliaries
    def _aux_bytes(self, role: str) -> bytes | None:
        ref = self.unit.auxiliary.get(role)
        if ref is None:
            return None
        try:
            raw = self.ctx.open_auxiliary(role)
        except AgentProvError:
            return None
        if len(raw) != ref.bytes or hashlib.sha256(raw).hexdigest() != ref.sha256:
            raise MalformedArtefact(f"auxiliary artefact {role!r} does not match its digest")
        return raw

    def _add(self, role: str, value: Any) -> _Aux:
        aid = f"a{len(self.artifacts)}"
        self.artifacts.append({**self.unit.auxiliary[role].to_json(), "id": aid, "role": "supporting", "prov_primary": "native"})
        found = _Aux(aid, value)
        self.aux[role] = found
        return found

    def _load_json(self, role: str) -> Any:
        raw = self._aux_bytes(role)
        if raw is None:
            return None
        try:
            return strict_json_loads(raw, self.limits)
        except IngestError:
            self._add(role, None)
            self.issue("openhands.join_unverified", ["exec"], self._join_rule(role), detail=f"{role}: not strict JSON")
            return None

    def _join_rule(self, role: str) -> str:
        if role in ("eval", "state"):
            return R_OAS_EVAL
        if role == "llm_judge":
            return R_OAS_SUMMARY
        if role in ("task_md", "checkpoints", "scenarios", "evaluator"):
            return R_OAS_TASK
        if role == "score":
            return R_RC_SCORE
        return R_RC_PROMPT

    def _load_aux(self) -> None:
        if self.oas:
            value = self._load_json("eval")
            if isinstance(value, dict):
                self._add("eval", value)
            elif "eval" not in self.aux:
                self.issue("openhands.eval_missing", ["run"], R_OAS_EVAL, severity="info")
            value = self._load_json("state")
            if isinstance(value, str):
                self._add("state", value)
            elif "state" not in self.aux:
                self.issue("openhands.state_missing", ["run"], R_OAS_EVAL, severity="info")
            value = self._load_json("llm_judge")
            entry = _dict(value).get(str(self.f.task)) if isinstance(value, dict) else None
            if isinstance(entry, dict):
                self._add("llm_judge", entry)
            elif isinstance(value, dict):
                self.issue("openhands.summary_entry_missing", ["run"], R_OAS_SUMMARY, severity="info")
            raw = self._aux_bytes("task_md")
            if raw is not None:
                try:
                    self._add("task_md", raw.decode("utf-8"))
                except UnicodeDecodeError:
                    self._add("task_md", None)
            for role in ("checkpoints", "scenarios", "evaluator"):
                if self._aux_bytes(role) is not None:
                    self._add(role, None)
            return
        key = str(self.f.case_key)
        value = self._load_json("score")
        entries = [e for e in value if isinstance(e, dict) and str(e.get("index")) == key] if isinstance(value, list) else []
        if len(entries) == 1:
            assert isinstance(value, list)
            self._add("score", (value.index(entries[0]), entries[0]))
        elif value is not None:
            self.issue("openhands.join_unverified", ["exec"], R_RC_SCORE, detail=f"score records for the case: {len(entries)}")
        role, field_ = ("dataset", "Index") if self.f.target == "S1" else ("prompt", "payload_index")
        value = self._load_json(role)
        entries = [e for e in value if isinstance(e, dict) and str(e.get(field_)) == key] if isinstance(value, list) else []
        if len(entries) == 1:
            assert isinstance(value, list)
            self._add(role, (value.index(entries[0]), entries[0]))
        elif value is not None:
            self.issue("openhands.join_unverified", ["exec"], R_RC_PROMPT, detail=f"{role} records for the case: {len(entries)}")

    # ---------------------------------------------------------------------------------------------- run
    def run(self) -> Iterator[dict[str, Any]]:
        if not self.events:
            raise MalformedArtefact("an empty OpenHands event list is not a run")
        self.by_id: dict[int, tuple[int, dict[str, Any]]] = {}
        for pos, event in enumerate(self.events):
            eid = event.get("id")
            if not isinstance(eid, int) or isinstance(eid, bool) or eid in self.by_id:
                raise MalformedArtefact("an event id is not a unique integer")
            self.by_id[eid] = (pos, event)
        self._load_aux()
        self._prescan()
        body: list[dict[str, Any]] = []
        body += self._actors()
        body += self._scopes()
        body += self._fixtures()
        body += self._stream()
        body += self._judgements()
        self._redact(body)
        self._issues()
        yield self._header()
        yield from body

    def _prescan(self) -> None:
        ids = [int(e["id"]) for e in self.events]
        self.gaps = (max(ids) - min(ids) + 1) - len(ids) if ids else 0
        self.ordered = all(b > a for a, b in zip(ids, ids[1:], strict=False))
        self.served: list[str] = []
        self.requested: list[str] = []
        self.later_users = 0
        firsts = 0
        for event in self.events:
            kind, name = event_kind(event)
            tcm = _dict(event.get("tool_call_metadata"))
            model = _dict(tcm.get("model_response")).get("model")
            if kind == "action" and isinstance(model, str) and model not in self.served:
                self.served.append(model)
            usages = _dict(event.get("llm_metrics")).get("token_usages")
            if isinstance(usages, list) and usages and isinstance(usages[-1], dict):
                req = usages[-1].get("model")
                if isinstance(req, str) and req not in self.requested:
                    self.requested.append(req)
            if kind == "action" and name == "message" and event.get("source") == "user":
                firsts += 1
            if kind == "action" and name == "chat":
                npc = _dict(event.get("args")).get("npc_name")
                if isinstance(npc, str) and npc and npc not in self.npc:
                    self.npc[npc] = f"npc{len(self.npc)}"
        self.later_users = max(firsts - 1, 0)
        last = self.events[-1]
        self.ends_in_harness_error = event_kind(last) == ("observation", "error") and "cause" not in last
        self.has_env = any(event_kind(e)[0] == "observation" and isinstance(e.get("cause"), int)
                           and _dict(self.by_id.get(int(e["cause"]), (0, {}))[1]).get("tool_call_metadata") is not None
                           for e in self.events)

    # ---------------------------------------------------------------------------------------------- header
    def _header(self) -> dict[str, Any]:
        header = _header_base(self.unit, self.ctx, self.f, self.origin_key, self.artifacts, self.variant)
        ext: dict[str, Any] = {"path_facets": self.f.to_json(), "events": len(self.events), "id_gaps": self.gaps}
        first, last = self.events[0].get("timestamp"), self.events[-1].get("timestamp")
        ext["first_event_timestamp"], ext["last_event_timestamp"] = first, last
        if self.variant == VARIANT_OH15:
            args = _dict(self.events[0].get("args"))
            ext["openhands_version"] = args.get("openhands_version")
            if "agent_class" in args:
                ext["agent_class"] = args.get("agent_class")
        if self.served:
            ext["served_models"] = list(self.served)
        ext.update(self.ext)
        lex = LexHints()
        header["ext"] = {NAMESPACE: encode_value(ext, at=_p("ext", NAMESPACE), lex=lex)}
        hints = lex.as_dict()
        if hints:
            header["ext"]["lex"] = hints
        src = list(header["src"])
        src.append({"a": "a0", "p": ""})
        header["src"] = src
        evf = dict(header.get("evf", {}))
        rules = list(header.get("rule", []))
        for pointer, (cls, rule) in sorted(self.ext_evf.items()):
            evf[pointer] = cls
            if rule is not None:
                ref = self.R(rule, pointer)
                if ref not in rules:
                    rules.append(ref)
        if evf:
            header["evf"] = evf
        if rules:
            header["rule"] = rules
        return header

    # ---------------------------------------------------------------------------------------------- actors and scopes
    def _origin_src(self) -> list[dict[str, Any]]:
        return [{"a": "a0", "o": f"/{self.origin_key}"}]

    def _actors(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        bench = _Rec(k="actor", id="bench", kind="benchmark", name="openagentsafety" if self.oas else "redcode-exec", ev="O")
        for entry in self._origin_src():
            bench.loc(entry)
        bench.unk.update({"/code": "not_recorded", "/version": "not_recorded"})
        out.append(bench.done())
        harness = _Rec(k="actor", id="harness", kind="harness", name="openhands", ev="O")
        harness.loc(self.loc(""))
        if self.variant == VARIANT_OH15:
            version = _dict(self.events[0].get("args")).get("openhands_version")
            harness.set("version", version)
            harness.loc(self.loc("/0/args/openhands_version"))
        elif isinstance(self.fam.get("harness_version"), str):
            harness.set("version", self.fam["harness_version"])
            harness.tag("/version", "I", self.R(R_LOCK, "/version"))
        else:
            harness.unk["/version"] = "not_recorded"
        harness.unk["/code"] = "not_recorded"
        out.append(harness.done())
        user = _Rec(k="actor", id="user", kind="simulated_user", ev="I")
        user.cite(self.R(R_FIRST_USER))
        out.append(user.done())
        if self.oas and self.later_users:
            fake = _Rec(k="actor", id="fake_user", kind="simulated_user", role="fake_user", ev="I")
            fake.cite(self.R(R_FAKE_USER))
            fake_model = self.fam.get("fake_user_model")
            if isinstance(fake_model, str):
                fake.data["model"] = {"requested": fake.enc(fake_model, "/model/requested")}
            else:
                fake.unk["/model"] = "not_recorded"
            out.append(fake.done())
        agent = _Rec(k="actor", id="agent", kind="llm_agent", ev="O", on_behalf_of="user")
        agent.loc(self.loc(""))
        agent.tag("/on_behalf_of", "I", self.R(R_PRINCIPAL, "/on_behalf_of"))
        model: dict[str, Any] = {}
        if len(self.served) == 1:
            model["served"] = self.served[0]
            agent.tag("/model/served", "D", self.R(R_SERVED, "/model/served"))
            if self.served[0].lower() in _SENTINELS:  # a placeholder is kept verbatim, never typed as known (C.7.3)
                agent.unk["/model/served"] = "ambiguous"
        else:
            agent.unk["/model/served"] = "ambiguous" if self.served else "not_recorded"
            if len(self.served) > 1:
                agent.cite(self.R(R_SERVED, "/model/served"))
        if len(self.requested) == 1:
            model["requested"] = self.requested[0]
            agent.evf["/model/requested"] = "O"
            if self.requested[0].lower() in _SENTINELS:
                agent.unk["/model/requested"] = "ambiguous"
        else:
            agent.unk["/model/requested"] = "ambiguous" if self.requested else "not_recorded"
        if model:
            agent.data["model"] = agent.enc(model, "/model")
        agent.unk.update({"/model/provider": "not_recorded", "/params": "not_recorded"})
        out.append(agent.done())
        if self.has_env:
            env = _Rec(k="actor", id="env", kind="tool_runtime", name="openhands-runtime", on_behalf_of="agent",
                       ev=self.cls(R_EXEC))
            env.cite(self.R(R_EXEC))
            env.loc(self.loc(""))
            out.append(env.done())
        for name, aid in self.npc.items():
            npc = _Rec(k="actor", id=aid, kind="simulated_user", role="npc", ev="I")
            npc.set("name", name)
            npc.cite(self.R(R_NPC))
            npc.unk["/model"] = "not_recorded"
            out.append(npc.done())
        for role, aid, name in (("eval", "oas_checker", "evaluator.py"), ("llm_judge", "oas_llm_judge", "llm_as_judge.py"),
                                ("score", "redcode_scorer", "OH_evaluation/scoring.py")):
            if role in self.aux and self.aux[role].value is not None:
                judge = _Rec(k="actor", id=aid, kind="judge", name=name, ev="O", by="benchmark")
                judge.loc({"a": self.aux[role].aid})
                judge.unk["/code"] = "not_recorded"
                if role == "llm_judge":
                    judge.unk["/model"] = "not_recorded"
                out.append(judge.done())
        return out

    def _scopes(self) -> list[dict[str, Any]]:
        run = _Rec(k="scope", id="run", kind="run", ev="O")
        run.loc(self.loc(""))
        first, last = self.events[0].get("timestamp"), self.events[-1].get("timestamp")
        raw = {k: v for k, v in (("start", first), ("end", last)) if isinstance(v, str)}
        if raw:
            # The first and last event times bound the logged events, not the run; naive local times are never placed
            # as typed instants (C.8.5; D.16.18 correction 1): they stay verbatim in t.raw, the typed slots ambiguous.
            run.data["t"] = {"raw": raw}
            for k in raw:
                run.unk[f"/t/{k}"] = "ambiguous"
            run.cite(self.R(R_TIME, "/t"))
            run.loc(self.loc("/0/timestamp"))
        else:
            run.unk["/t"] = "not_recorded"
        state = self.aux.get("state")
        agent_state = None
        if state is not None and isinstance(state.value, str):
            fields: dict[str, Any] = {}
            for name, pattern in STATE_FIELDS.items():
                found = pattern.findall(state.value)
                if found:
                    fields[name] = found[-1] if name == "agent_state" else int(found[0])
            self.ext["state"] = fields
            self.ext_tag("state", "D", R_STATE)
            agent_state = fields.get("agent_state")
        if self.ends_in_harness_error:
            run.data["status"] = "error"
            run.loc(self.loc(f"/{len(self.events) - 1}"))
            run.tag("/status", "I", self.R(R_UNCAUSED, "/status"))
        elif agent_state == "error":
            assert state is not None
            run.data["status"] = "error"
            run.loc({"a": state.aid})
            run.tag("/status", "I", self.R(R_STATE_STATUS, "/status"))
        else:
            run.unk["/status"] = "not_recorded"
        att = _Rec(k="scope", id="att0", kind="attempt", parent="run", actor="agent", ev="O")
        att.loc(self.loc(""))
        att.unk.update({"/index": "not_recorded", "/scored": "not_recorded"})
        return [run.done(), att.done()]

    # ---------------------------------------------------------------------------------------------- fixtures
    def _fixtures(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if self.variant == VARIANT_OH15:
            args = _dict(self.events[0].get("args"))
            if "content" in args:
                fx = _Rec(k="fixture", id=self.next_id("fx"), kind="system_prompt", ev="O")
                self._fixture_content(fx, args["content"], "/0/args/content")
                out.append(fx.done())
            if "tools" in args:
                fx = _Rec(k="fixture", id=self.next_id("fx"), kind="tool_definitions", ev="O")
                self._fixture_content(fx, args["tools"], "/0/args/tools")
                out.append(fx.done())
                self.tools_fixture = fx.id
        first = next((e for e in self.events if event_kind(e) == ("action", "message") and e.get("source") == "user"), None)
        first_text = _dict(first.get("args")).get("content") if first is not None else None
        if self.oas:
            task = self.aux.get("task_md")
            self.ext["task_join"] = {"task_dir": f"workspaces/tasks/{self.f.task}/",
                                     "files": sorted(r for r in ("task_md", "checkpoints", "scenarios", "evaluator") if r in self.aux)}
            self.ext_tag("task_join", "D", R_OAS_TASK)
            if task is not None and isinstance(task.value, str):
                fx = _Rec(k="fixture", id=self.next_id("fx"), kind="task_prompt", ev="I")
                fx.set("content", task.value)
                fx.evf["/content"] = "O"
                fx.loc({"a": task.aid})
                fx.cite(self.R(R_TASK_MD))
                seen = self._seen(task.value)
                fx.x("seen_in", seen)
                fx.tag(_p("ext", NAMESPACE, "seen_in"), "D", self.R(R_SEEN, _p("ext", NAMESPACE, "seen_in")))
                if seen is None:
                    self.issue("openhands.task_text_not_seen", [fx.id], R_SEEN, severity="info")
                out.append(fx.done())
            return out
        role = "dataset" if self.f.target == "S1" else "prompt"
        found = self.aux.get(role)
        if found is None or not isinstance(found.value, tuple):
            return out
        index, entry = found.value
        key = "Code" if role == "dataset" else "generated_prompt"
        text = entry.get(key)
        tier = self._prompt_tier(text, first_text)
        self.ext["request_join"] = {"source": role, "tier": tier, "internal_id": entry.get("internal_id")}
        self.ext_tag("request_join", "D", R_RC_PROMPT)
        if tier == "not_contained":
            self.issue("openhands.join_unverified", ["exec"], R_RC_PROMPT, detail=f"{role}: the request is not in the first user message")
            return out
        if tier == "contained_after_declared_rewrite":
            self.issue("openhands.join_after_rewrite", ["exec"], R_RC_PROMPT, severity="info", detail="/sys/kernel -> /app/sys/kernel")
        fx = _Rec(k="fixture", id=self.next_id("fx"), kind="task_prompt", ev="D")
        fx.set("content", text)
        fx.evf["/content"] = "O"
        fx.loc({"a": found.aid, "p": _p(index, key)})
        fx.cite(self.R(R_RC_PROMPT))
        out.append(fx.done())
        return out

    def _fixture_content(self, fx: _Rec, value: object, pointer: str) -> None:
        if _big(value):
            assert isinstance(value, str)
            fx.unk["/content"] = "not_recorded"
            fx.x("content", _not_inlined(value))
            fx.tag(_p("ext", NAMESPACE, "content"), "D", self.R(R_NOT_INLINED, _p("ext", NAMESPACE, "content")))
            self.not_inlined.append(fx.id)
        else:
            fx.set("content", value)
        fx.loc(self.loc(pointer))

    def _seen(self, task_text: str) -> str | None:
        """The first logged observation whose content holds the task text (whitespace-normalised)."""
        needle = _norm(task_text)
        if not needle:
            return None
        for pos, event in enumerate(self.events):
            content = event.get("content")
            if event_kind(event)[0] == "observation" and isinstance(content, str) and needle in _norm(content):
                return f"/{pos}"
        return None

    @staticmethod
    def _prompt_tier(text: object, first: object) -> str:
        if not isinstance(text, str) or not isinstance(first, str):
            return "not_contained"
        if text == first:
            return "exact"
        if _norm(text) in _norm(first):
            return "contained"
        if _norm(_SYS_KERNEL.sub("/app/sys/kernel", text)) in _norm(first):
            return "contained_after_declared_rewrite"
        return "not_contained"

    # ---------------------------------------------------------------------------------------------- the event stream
    def _stream(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for pos, event in enumerate(self.events):
            kind, name = event_kind(event)
            tcm = event.get("tool_call_metadata")
            if kind == "action":
                if name == "system" and pos == 0 and self.variant == VARIANT_OH15:
                    continue
                if isinstance(tcm, dict):
                    out += self._tool_action(pos, event, tcm)
                elif name == "message" and event.get("source") == "user":
                    out.append(self._user(pos, event))
                elif name == "message" and event.get("source") == "agent":
                    out += self._text_reply(pos, event)
                elif name == "recall":
                    out.append(self._recall(pos, event))
                else:
                    out += self._unmapped(pos, event)
            else:
                cause = event.get("cause")
                target = self.by_id.get(cause) if isinstance(cause, int) and not isinstance(cause, bool) else None
                if target is not None and target[0] < pos:
                    out += self._observation(pos, event, target[0], target[1])
                elif name == "error" and "cause" not in event:
                    out += self._harness_error(pos, event)
                else:
                    out += self._unmapped(pos, event, lone=True)
        for aid in sorted(self.call_of):
            part = self.call_of[aid]
            if part is not None and aid not in self.answered:
                self.unexecuted.append(part)
        return out

    def _user(self, pos: int, event: Mapping[str, Any]) -> dict[str, Any]:
        self.user_messages += 1
        later = self.user_messages > 1
        actor = "fake_user" if later and self.oas else "user"
        rec = _Rec(k="message", id=f"m{pos}", scope="att0", role="user", actor=actor, ev="O")
        content = _dict(event.get("args")).get("content")
        rec.data["parts"] = [{"t": "text", "text": rec.enc(content, "/parts/0/text")}]
        rec.loc(self.loc(f"/{pos}"))
        rec.tag("/actor", "I", self.R(R_FAKE_USER if later else R_FIRST_USER, "/actor"))
        if later and isinstance(content, str):
            fixed = _sha(content) in set(self.fam.get("fixed_replies", ()) or ())
            rec.x("reply_form", "fixed_text" if fixed else "generated")
            rec.tag(_p("ext", NAMESPACE, "reply_form"), "D", self.R(R_FIXED, _p("ext", NAMESPACE, "reply_form")))
        images = _dict(event.get("args")).get("image_urls")
        if images:
            rec.x("image_urls", images)
        self._stamp(rec, event)
        self._order(rec)
        self.messages.append(rec.id)
        self.prev = rec.id
        return rec.done()

    def _model_call(self, mc_id: str, pos: int, response: Mapping[str, Any] | None, event: Mapping[str, Any]) -> dict[str, Any]:
        if response is not None:
            mc = _Rec(k="model_call", id=mc_id, actor="agent", role="agent", scope="att0", status="kept", ev="O")
            mc.tag("/actor", self.cls(R_FROM_CALL), self.R(R_FROM_CALL, "/actor"))
            mc.tag("/status", "D", self.R(R_KEPT, "/status"))
            if isinstance(response.get("model"), str):
                mc.set("served_model", response["model"])
                if response["model"].lower() in _SENTINELS:
                    mc.unk["/served_model"] = "ambiguous"
            else:
                mc.unk["/served_model"] = "not_recorded"
            if isinstance(response.get("id"), str):
                mc.set("response_id", response["id"])
            choices = response.get("choices")
            c0 = _dict(choices[0]) if isinstance(choices, list) and choices else {}
            if isinstance(c0.get("finish_reason"), str):
                mc.set("finish_reason", c0["finish_reason"])
            else:
                mc.unk["/finish_reason"] = "not_recorded"
            usage = _usage(response.get("usage"))
            if usage:
                mc.data["usage"] = usage
                mc.tag("/usage", "D", self.R(R_USAGE, "/usage"))
            else:
                mc.unk["/usage"] = "not_recorded"
            for key in ("created", "system_fingerprint", "service_tier", "object"):
                if key in response:
                    mc.x(key, response[key])
            if isinstance(response.get("usage"), dict):
                mc.x("usage_raw", response["usage"])
            mc.loc(self.loc(f"/{pos}/tool_call_metadata/model_response"))
        else:
            mc = _Rec(k="model_call", id=mc_id, actor="agent", role="agent", scope="att0", status="kept", ev="I")
            mc.cite(self.R(R_TEXT_MODEL))
            usages = _dict(event.get("llm_metrics")).get("token_usages")
            last = _dict(usages[-1]) if isinstance(usages, list) and usages else {}
            if isinstance(last.get("response_id"), str):
                mc.set("response_id", last["response_id"])
                mc.evf["/response_id"] = "O"
                mc.loc(self.loc(f"/{pos}/llm_metrics/token_usages/{len(usages) - 1}/response_id"))  # type: ignore[arg-type]
            else:
                mc.unk["/response_id"] = "not_recorded"
            mc.unk.update({"/finish_reason": "not_recorded", "/served_model": "not_recorded", "/usage": "not_recorded"})
            mc.loc(self.loc(f"/{pos}"))
        mc.data["input"] = list(self.messages)
        mc.tag("/input", "I", self.R(R_CONTEXT, "/input"))
        if self.tools_fixture is not None:
            mc.data["tools"] = self.tools_fixture
            mc.tag("/tools", "I", self.R(R_TOOLS, "/tools"))
        mc.unk.update({key: "not_recorded" for key in _MODEL_CALL_UNKNOWN})
        self._order(mc)
        self.prev = mc_id
        return mc.done()

    def _tool_action(self, pos: int, event: Mapping[str, Any], tcm: Mapping[str, Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        response = tcm.get("model_response")
        rid = _dict(response).get("id")
        key = rid if isinstance(rid, str) else f"#{pos}"
        found = self.responses.get(key)
        if found is None:
            mc_id = self.next_id("mc")
            out.append(self._model_call(mc_id, pos, response if isinstance(response, dict) else None, event))
            message, parts = self._assistant(pos, _dict(response), mc_id, event)
            found = self.responses[key] = _Response(mc_id, str(message["id"]), parts)
            out.append(message)
        eid = int(event["id"])
        call_id = tcm.get("tool_call_id")
        if event.get("action") == "finish":
            self.call_of[eid] = None
            return out
        part = found.parts.get(call_id) if isinstance(call_id, str) else None
        if part is None:
            self.issue("openhands.call_not_in_response", [found.message], R_FROM_CALL, detail=f"event {eid}")
        self.call_of[eid] = part
        return out

    def _assistant(self, pos: int, response: Mapping[str, Any], mc_id: str,
                   event: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
        mid = f"m{pos}"
        rec = _Rec(k="message", id=mid, scope="att0", role="assistant", actor="agent", generated_by=mc_id, ev="O")
        rec.tag("/actor", self.cls(R_FROM_CALL), self.R(R_FROM_CALL, "/actor"))
        rec.tag("/generated_by", "D", self.R(R_RESPONSE, "/generated_by"))
        rec.edge(mc_id, "causal")
        rec.tag("/after", "D", self.R(R_GEN, "/after"))
        choices = response.get("choices")
        msg = _dict(_dict(choices[0]).get("message")) if isinstance(choices, list) and choices else {}
        parts: list[dict[str, Any]] = []
        calls: dict[str, str] = {}
        reasoning = msg.get("reasoning_content")
        if isinstance(reasoning, str) and reasoning:
            parts.append({"t": "reasoning", "text": rec.enc(reasoning, f"/parts/{len(parts)}/text")})
        content = msg.get("content")
        if isinstance(content, str) and content:
            k = len(parts)
            if _big(content):
                parts.append({"t": "text", "text": None})
                rec.unk[f"/parts/{k}/text"] = "ambiguous"
                rec.x("text_not_inlined", _not_inlined(content))
                rec.cite(self.R(R_NOT_INLINED, f"/parts/{k}/text"))
                rec.tag(_p("ext", NAMESPACE, "text_not_inlined"), "D", self.R(R_NOT_INLINED, _p("ext", NAMESPACE, "text_not_inlined")))
                self.not_inlined.append(mid)
            else:
                parts.append({"t": "text", "text": rec.enc(content, f"/parts/{k}/text")})
        else:
            rec.x("response_content", "null" if content is None else "empty")
        tool_calls = msg.get("tool_calls")
        finish_names = set(self.fam.get("control_calls", ("finish",)) or ("finish",))
        for call in tool_calls if isinstance(tool_calls, list) else []:
            call = _dict(call)
            fn = _dict(call.get("function"))
            name, raw = fn.get("name"), fn.get("arguments")
            k = len(parts)
            args, decoded = None, False
            if isinstance(raw, str):
                try:
                    args, decoded = strict_json_loads(raw.encode("utf-8", "surrogatepass"), self.limits), True
                except (IngestError, UnicodeEncodeError):
                    args = None
            elif isinstance(raw, dict):
                args, decoded = raw, True
            if name in finish_names:
                value = {"name": name, "args": args, "provider_call_id": call.get("id")}
                if isinstance(raw, str):
                    value["args_raw"] = raw
                parts.append({"t": "other", "type": "openhands.finish_call", "value": rec.enc(value, f"/parts/{k}/value")})
                rec.tag(f"/parts/{k}/type", "D", self.R(R_FINISH, f"/parts/{k}/type"))
                continue
            part: dict[str, Any] = {"t": "tool_call", "name": rec.enc(name if isinstance(name, str) else str(name), f"/parts/{k}/name")}
            part["args"] = rec.enc(args, f"/parts/{k}/args")
            if isinstance(raw, str):
                part["args_raw"] = rec.enc(raw, f"/parts/{k}/args_raw")
            if isinstance(call.get("id"), str):
                part["provider_call_id"] = rec.enc(call["id"], f"/parts/{k}/provider_call_id")
                calls[call["id"]] = part_id(mid, k)
            rec.tag(f"/parts/{k}/args", "D", self.R(R_ARGS, f"/parts/{k}/args"))
            if not decoded:
                rec.unk[f"/parts/{k}/args"] = "ambiguous"
            if not isinstance(name, str) or name.lower() in _SENTINELS:
                rec.unk[f"/parts/{k}/name"] = "ambiguous"
            parts.append(part)
        rec.data["parts"] = parts
        rec.loc(self.loc(f"/{pos}/tool_call_metadata/model_response/choices/0/message"))
        self._stamp(rec, event)
        self._order(rec)
        self.messages.append(mid)
        self.prev = mid
        return rec.done(), calls

    def _text_reply(self, pos: int, event: Mapping[str, Any]) -> list[dict[str, Any]]:
        mc_id = self.next_id("mc")
        out = [self._model_call(mc_id, pos, None, event)]
        mid = f"m{pos}"
        rec = _Rec(k="message", id=mid, scope="att0", role="assistant", actor="agent", generated_by=mc_id, ev="O")
        content = _dict(event.get("args")).get("content")
        if isinstance(content, str) and content:
            rec.data["parts"] = [{"t": "text", "text": rec.enc(content, "/parts/0/text")}]
        else:
            rec.data["parts"] = []
            rec.x("response_content", "null" if content is None else "empty")
        rec.loc(self.loc(f"/{pos}/args/content"))
        rec.tag("/actor", "I", self.R(R_TEXT_MODEL, "/actor"))
        rec.tag("/generated_by", "I", self.R(R_TEXT_MODEL, "/generated_by"))
        rec.edge(mc_id, "causal")
        rec.tag("/after", "I", self.R(R_GEN, "/after"))
        if "wait_for_response" in _dict(event.get("args")):
            rec.x("wait_for_response", _dict(event.get("args")).get("wait_for_response"))
        self._stamp(rec, event)
        self.messages.append(mid)
        self.prev = mid
        out.append(rec.done())
        return out

    def _recall(self, pos: int, event: Mapping[str, Any]) -> dict[str, Any]:
        args = _dict(event.get("args"))
        ac = _Rec(k="activity", id=self.next_id("ac"), type="openhands:recall", actor="harness", scope="att0", ev="O")
        if isinstance(args.get("recall_type"), str):
            ac.set("label", args["recall_type"])
        ac.loc(self.loc(f"/{pos}"))
        ac.tag("/actor", "I", self.R(R_RECALL, "/actor"))
        ac.unk["/inputs"] = "not_recorded"
        ac.x("source", event.get("source"))
        self._stamp(ac, event)
        self._order(ac)
        self.recall_of[int(event["id"])] = ac.id
        self.prev = ac.id
        return ac.done()

    def _observation(self, pos: int, event: Mapping[str, Any], tpos: int, target: Mapping[str, Any]) -> list[dict[str, Any]]:
        tkind, tname = event_kind(target)
        tid = int(target["id"])
        if tkind == "action" and tname == "recall" and tid in self.recall_of:
            return [self._recall_result(pos, event, self.recall_of[tid])]
        if tkind == "action" and tid in self.call_of:
            if event.get("observation") == "error" and event.get("content") in set(self.fam.get("not_executed_notices", ()) or ()):
                return self._notice(pos, event, tid)
            part = self.call_of[tid]
            if part is not None:
                self.answered.add(tid)
                return self._tool_result(pos, event, tpos, target, part)
        return self._unmapped(pos, event, lone=True, target=tid)

    def _recall_result(self, pos: int, event: Mapping[str, Any], ac_id: str) -> dict[str, Any]:
        extras = _dict(event.get("extras"))
        kind = "openhands:workspace_context" if extras.get("recall_type") == "workspace_context" else "openhands:recall_result"
        af = _Rec(k="artefact", id=self.next_id("af"), type=kind, generated_by=ac_id, ev="O")
        body, replaced = _slim({"content": event.get("content"), "extras": extras})
        af.set("content", body)
        for rel in replaced:
            af.tag("/content" + rel, "D", self.R(R_NOT_INLINED, "/content" + rel))
        if replaced:
            self.not_inlined.append(af.id)
        af.loc(self.loc(f"/{pos}"))
        af.tag("/generated_by", self.cls(R_RECALL_CAUSE), self.R(R_RECALL_CAUSE, "/generated_by"))
        af.edge(ac_id, "causal")
        af.tag("/after", self.cls(R_RECALL_CAUSE), self.R(R_GEN, "/after"))
        self._stamp(af, event)
        self._order(af)
        self.prev = af.id
        return af.done()

    def _notice(self, pos: int, event: Mapping[str, Any], tid: int) -> list[dict[str, Any]]:
        part = self.call_of.get(tid)
        ac = _Rec(k="activity", id=self.next_id("ac"), type="openhands:controller_notice", actor="harness", scope="att0",
                  ev=self.cls(R_NOTICE))
        ac.cite(self.R(R_NOTICE))
        ac.loc(self.loc(f"/{pos}"))
        ac.unk["/inputs"] = "not_recorded"
        ac.x("cause", tid)
        self._stamp(ac, event)
        self._order(ac)
        self.prev = ac.id
        af = _Rec(k="artefact", id=self.next_id("af"), type="openhands:notice_text", generated_by=ac.id, ev="O")
        af.set("content", event.get("content"))
        af.loc(self.loc(f"/{pos}/content"))
        af.tag("/generated_by", self.cls(R_NOTICE), self.R(R_NOTICE, "/generated_by"))
        af.edge(ac.id, "causal")
        af.tag("/after", self.cls(R_NOTICE), self.R(R_GEN, "/after"))
        self.prev = af.id
        if part is not None:
            self.answered.add(tid)
            self.unexecuted.append(part)
            self.issue("openhands.not_executed_notice", [ac.id, part], R_NOTICE, severity="info")
        return [ac.done(), af.done()]

    def _tool_result(self, pos: int, event: Mapping[str, Any], tpos: int, target: Mapping[str, Any],
                     part: str) -> list[dict[str, Any]]:
        self.has_env = True
        error = event.get("observation") == "error"
        tcm = _dict(target.get("tool_call_metadata"))
        te = _Rec(k="tool_execution", id=self.next_id("te"), actor="env", scope="att0", ev=self.cls(R_EXEC))
        te.cite(self.R(R_EXEC))
        te.data["call"] = part
        te.tag("/call", self.cls(R_FROM_CALL), self.R(R_FROM_CALL, "/call"))
        name = tcm.get("function_name")
        te.set("name", name if isinstance(name, str) else str(name))
        te.evf["/name"] = "O"
        if not isinstance(name, str) or name.lower() in _SENTINELS:
            te.unk["/name"] = "ambiguous"
            te.cite(self.R(R_FROM_CALL, "/name"))
        args, replaced = _slim(target.get("args"))
        te.set("args", args)
        te.evf["/args"] = "O"
        for rel in replaced:
            te.tag("/args" + rel, "D", self.R(R_NOT_INLINED, "/args" + rel))
        if replaced:
            self.not_inlined.append(te.id)
        if error:
            te.unk["/status"] = "ambiguous"
            te.cite(self.R(R_EXEC, "/status"))
        else:
            te.data["status"] = "ok"
            te.tag("/status", self.cls(R_EXEC), self.R(R_EXEC, "/status"))
        te.unk.update({"/returned": "not_recorded", "/t": "not_recorded"})
        te.loc(self.loc(f"/{tpos}"))
        te.loc(self.loc(f"/{pos}/cause"))
        te.x("action", target.get("action"))
        te.x("action_event_id", target.get("id"))
        te.x("action_timestamp", target.get("timestamp"))
        if target.get("action") == "chat":
            npc = _dict(target.get("args")).get("npc_name")
            if isinstance(npc, str) and npc in self.npc:
                te.x("npc", self.npc[npc])
        call_message = part.split("#", 1)[0]
        te.edge(call_message, "causal")
        te.tag("/after", self.cls(R_FROM_CALL), self.R(R_AFTER_CALL, "/after"))
        self._order(te)
        self.prev = te.id
        mid = f"m{pos}"
        msg = _Rec(k="message", id=mid, scope="att0", role="tool", actor="env", generated_by=te.id, ev="O")
        result: dict[str, Any] = {"t": "tool_result", "responds_to": part}
        content = event.get("content")
        if _big(content):
            assert isinstance(content, str)
            result["text"] = None
            msg.unk["/parts/0/text"] = "ambiguous"
            msg.x("text_not_inlined", _not_inlined(content))
            msg.cite(self.R(R_NOT_INLINED, "/parts/0/text"))
            msg.tag(_p("ext", NAMESPACE, "text_not_inlined"), "D", self.R(R_NOT_INLINED, _p("ext", NAMESPACE, "text_not_inlined")))
            self.not_inlined.append(mid)
        elif isinstance(content, str):
            result["text"] = msg.enc(content, "/parts/0/text")
        else:
            result["value"] = msg.enc(content, "/parts/0/value")
        rname = _dict(event.get("tool_call_metadata")).get("function_name")
        if isinstance(rname, str) and rname.lower() not in _SENTINELS:
            result["name"] = msg.enc(rname, "/parts/0/name")
        msg.data["parts"] = [result]
        msg.tag("/parts/0/responds_to", self.cls(R_CAUSE), self.R(R_CAUSE, "/parts/0/responds_to"))
        msg.tag("/generated_by", self.cls(R_EXEC), self.R(R_EXEC, "/generated_by"))
        msg.tag("/actor", self.cls(R_EXEC), self.R(R_EXEC, "/actor"))
        msg.edge(te.id, "causal")
        msg.tag("/after", self.cls(R_EXEC), self.R(R_GEN, "/after"))
        msg.loc(self.loc(f"/{pos}"))
        msg.x("observation", event.get("observation"))
        if "success" in event:
            msg.x("success", event.get("success"))
        extras = event.get("extras")
        if isinstance(extras, dict):
            slim: dict[str, Any] = {}
            slimmed: list[str] = []
            for key, value in extras.items():
                at = _p("ext", NAMESPACE, "extras", key)
                if key == "set_of_marks" and isinstance(value, str) and value:
                    slim[key] = _not_inlined(value, "image/png" if value.startswith("data:image/png") else None)
                    slimmed.append(at)
                else:
                    slim[key], sub = _slim(value)
                    slimmed += [at + rel for rel in sub]
            msg.x("extras", slim)
            for at in slimmed:
                msg.tag(at, "D", self.R(R_NOT_INLINED, at))
            if slimmed:
                self.not_inlined.append(mid)
        self._stamp(msg, event)
        self.messages.append(mid)
        self.prev = mid
        return [te.done(), msg.done()]

    def _harness_error(self, pos: int, event: Mapping[str, Any]) -> list[dict[str, Any]]:
        ac = _Rec(k="activity", id=self.next_id("ac"), type="openhands:harness_error", actor="harness", scope="att0",
                  status="error", ev="O")
        ac.loc(self.loc(f"/{pos}"))
        ac.tag("/actor", "I", self.R(R_UNCAUSED, "/actor"))
        ac.unk["/inputs"] = "not_recorded"
        self._stamp(ac, event)
        self._order(ac)
        self.prev = ac.id
        af = _Rec(k="artefact", id=self.next_id("af"), type="openhands:error_text", generated_by=ac.id, ev="O")
        af.set("content", event.get("content"))
        af.loc(self.loc(f"/{pos}/content"))
        af.edge(ac.id, "causal")
        af.tag("/after", "D", self.R(R_GEN, "/after"))
        self.prev = af.id
        self.issue("openhands.harness_error", [ac.id], R_UNCAUSED, severity="info")
        return [ac.done(), af.done()]

    def _unmapped(self, pos: int, event: Mapping[str, Any], *, lone: bool = False, target: int | None = None) -> list[dict[str, Any]]:
        kind, name = event_kind(event)
        ac = _Rec(k="activity", id=self.next_id("ac"), type="openhands:unmapped_event", actor="harness", scope="att0", ev="O")
        ac.set("label", f"{kind}:{name}")
        ac.loc(self.loc(f"/{pos}"))
        ac.tag("/actor", "I", self.R(R_UNCAUSED, "/actor"))
        ac.unk["/inputs"] = "not_recorded"
        self._stamp(ac, event)
        self._order(ac)
        self.prev = ac.id
        af = _Rec(k="artefact", id=self.next_id("af"), type="openhands:event_payload", generated_by=ac.id, ev="O")
        body, replaced = _slim({k: v for k, v in event.items() if k not in ("id", "timestamp", "source", "tool_call_metadata", "llm_metrics")})
        af.set("content", body)
        for rel in replaced:
            af.tag("/content" + rel, "D", self.R(R_NOT_INLINED, "/content" + rel))
        af.loc(self.loc(f"/{pos}"))
        af.edge(ac.id, "causal")
        af.tag("/after", "D", self.R(R_GEN, "/after"))
        self.prev = af.id
        code = "openhands.unexpected_cause_target" if target is not None else ("openhands.lone_observation" if lone else "openhands.unmapped_event")
        self.issue(code, [ac.id], R_ORDER, severity="info", detail=f"{kind}:{name}")
        return [ac.done(), af.done()]

    # ---------------------------------------------------------------------------------------------- judgements
    def _judge(self, actor: str, name: str, value: object, aid: str, pointer: str, subject_rule: str) -> _Rec:
        rec = _Rec(k="judgement", id=self.next_id("j"), actor=actor, subject="run", name=name, ev="O", by="benchmark")
        rec.set("value", value)
        rec.data["origin"] = "checker"
        rec.tag("/origin", "I", self.R(R_CHECKER, "/origin"))
        rec.tag("/subject", "D", self.R(subject_rule, "/subject"))
        rec.loc({"a": aid, "p": pointer})
        rec.unk.update({"/t": "not_recorded", "/inputs": "not_recorded"})
        return rec

    def _judgements(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        ev = self.aux.get("eval")
        if ev is not None and isinstance(ev.value, dict):
            checkpoints = ev.value.get("checkpoints")
            for k, cp in enumerate(checkpoints if isinstance(checkpoints, list) else []):
                out.append(self._judge("oas_checker", f"checkpoint/{k}", cp, ev.aid, f"/checkpoints/{k}", R_OAS_EVAL).done())
            if "final_score" in ev.value:
                out.append(self._judge("oas_checker", "final_score", ev.value["final_score"], ev.aid, "/final_score",
                                       R_OAS_EVAL).done())
        summary = self.aux.get("llm_judge")
        if summary is not None and isinstance(summary.value, dict):
            base = _p(str(self.f.task))
            for key in ("llm_label", "rule_based_score"):
                if key in summary.value:
                    out.append(self._judge("oas_llm_judge", key, summary.value[key], summary.aid, f"{base}/{key}",
                                           R_OAS_SUMMARY).done())
        score = self.aux.get("score")
        if score is not None and isinstance(score.value, tuple):
            index, entry = score.value
            rec = self._judge("redcode_scorer", "score", entry.get("score"), score.aid, _p(index, "score"), R_RC_SCORE)
            if entry.get("score") == 1:
                del rec.data["origin"]
                rec.evf.pop("/origin", None)
                rec.unk["/origin"] = "ambiguous"
                rec.cite(self.R(R_SCORE_ONE, "/origin"))
            rec.x("judge", {k: entry[k] for k in ("index", "last_response_full") if k in entry})
            out.append(rec.done())
        if not out:
            self.issue("no_outcome_recorded", ["run"], R_OAS_EVAL if self.oas else R_RC_SCORE)
        return out

    # ---------------------------------------------------------------------------------------------- redaction (D-606)
    def _redact(self, records: Sequence[dict[str, Any]]) -> None:
        """D-604/D-606: the profile's ``[[family.openhands.redact]]`` rules over the finished tool messages; one info
        issue counts the redacted texts."""
        entries = self.fam.get("redact", ())
        rules = parse_redact_rules(entries if isinstance(entries, (list, tuple)) else (), f"profile {self.ctx.profile.id!r}")
        if not rules:
            return
        redactor = Redactor(self.ctx.profile.id, self.ctx.profile.version, rules)
        changed: list[str] = []
        n = 0
        for record in records:
            done = redactor.apply(record, lambda p: self.R(R_REDACTED, p))
            if done:
                changed.append(str(record["id"]))
                n += len(done)
        if changed:
            self.issue("openhands.value_redacted", changed, R_REDACTED, severity="info",
                       detail=f"{n} tool-output texts redacted by the profile's redact rules (D-606)")

    # ---------------------------------------------------------------------------------------------- issues
    def _issues(self) -> None:
        if self.gaps:
            self.issue("openhands.filtered_events", ["exec"], R_GAPS, severity="info", detail=f"{self.gaps} ids absent")
        if not self.ordered:
            self.issue("openhands.unmapped_event", ["exec"], R_ORDER, detail="event ids are not increasing in array order")
        if len(self.served) > 1:
            self.issue("openhands.served_model_varies", ["agent"], R_SERVED, severity="info", detail=", ".join(self.served))
        if self.not_inlined:
            self.issue("openhands.content_not_inlined", sorted(set(self.not_inlined)), R_NOT_INLINED, severity="info")
        if self.unexecuted:
            self.issue("unexecuted_tool_call", sorted(set(self.unexecuted)), R_CAUSE)


def _usage(value: object) -> dict[str, int]:
    """The C.3.12 ``Usage`` of a provider usage object (``openhands.usage_fields@1``); only non-negative integers."""
    usage = _dict(value)
    out: dict[str, int] = {}

    def put(name: str, raw: object) -> None:
        if isinstance(raw, int) and not isinstance(raw, bool) and raw >= 0 and name not in out:
            out[name] = raw

    put("input_tokens", usage.get("prompt_tokens"))
    put("output_tokens", usage.get("completion_tokens"))
    put("total_tokens", usage.get("total_tokens"))
    put("reasoning_tokens", _dict(usage.get("completion_tokens_details")).get("reasoning_tokens"))
    put("cache_read_tokens", usage.get("cache_read_input_tokens"))
    put("cache_read_tokens", usage.get("prompt_cache_hit_tokens"))
    put("cache_read_tokens", _dict(usage.get("prompt_tokens_details")).get("cached_tokens"))
    put("cache_write_tokens", usage.get("cache_creation_input_tokens"))
    return out
