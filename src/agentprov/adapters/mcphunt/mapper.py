"""Mapper ``mcphunt.trace``: one MCPHunt trace -> AER ``aer/0.1`` (docs/architecture D.21.3-D.21.8; DECISIONS D-287..D-289).

One element of a document's ``/traces`` is one execution (locator ``/traces/<i>``; content-addressed id from the document
digest and the locator). What the mapper writes, in record order (backward references only, C.5.2):

1. the header: task coordinates (task id, risk mechanism, environment type, defence label), ``ext.mcphunt`` (the envelope,
   the split, the labels and the measurement record verbatim);
2. actors ``bench``, ``harness``, ``user``, ``agent``, one ``srv_<server>`` runtime per MCP server the events name, ``def``
   (a defence arm) and ``judge``;
3. scopes ``run`` and ``att0``; fixtures: the environment snapshot and the offered tool set;
4. the system and user messages; per ``turn_log`` entry *k*: ``mc<k>``, then assistant message *k* (or, for the last entry,
   ``final_message``), then per call: the guard's ``decision`` (defence arms), the ``tool_execution`` of its event and the
   tool message;
5. the judgements: the harness's outcome and risk labels (origin ``checker``, I).

Tool messages answer calls by ``tool_call_id`` (D); events carry no call id and answer the calls of their recorded turn by
position, guarded by the tool name (I). A canary-flagged event raises ``mcphunt.canary_flagged``, the D-289 withholding
basis; no canary value is read, compared or copied anywhere but the verbatim content the AER must hold.

Pure (A-2): the output is a function of the unit's bytes, this code, the profile and the catalogues.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from typing import Any, Final

from agentprov.adapters.mcphunt import ADAPTER_ID, DIALECT_ID, VARIANT
from agentprov.adapters.mcphunt.dialect import split_of
from agentprov.adapters.protocols import AerRecord, MappingContext
from agentprov.adapters.types import ExecutionUnit
from agentprov.aer.canon import LexHints, encode_value, json_pointer
from agentprov.aer.ids import part_id
from agentprov.errors import IngestError, MalformedArtefact
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads

__all__ = ["ADAPTER_ID", "ADAPTER_VERSION", "CATALOGUES", "NAMESPACES", "McpHuntMapper"]

ADAPTER_VERSION: Final = "0.1.0"
CATALOGUES: Final = ("aer", "mcphunt")
NAMESPACES: Final = {"mcphunt": "https://w3id.org/agentprov/ns/mcphunt#"}
#: Judgements: (name, JSON Pointer into the trace).
JUDGEMENTS: Final = (("outcome", "/outcome"), ("outcome_crs_stratified", "/outcome_crs_stratified"),
                     ("task_completed", "/task_completed"), ("any_risk", "/labeling/any_risk"),
                     ("strict_leakage", "/labeling/strict_leakage"), ("data_flow_risk", "/labeling/data_flow_risk"),
                     ("signals_fired", "/labeling/signals_fired"))
_TRACE_KEYS_MIN: Final = frozenset({"task_id", "task_prompt", "model", "messages", "events", "turn_log", "labeling",
                                    "measurement", "env_snapshot", "final_message", "env_type", "defense"})
_EVENT_KEYS: Final = frozenset({"args", "canary_in_args", "canary_in_result", "canary_visible_to_llm", "error",
                                "latency_ms", "result_chars", "result_full", "result_preview", "result_truncated",
                                "server", "success", "timestamp", "tool", "turn"})
_EVENT_OPTIONAL: Final = frozenset({"args_parse_error", "args_raw", "sanitized_args", "taint_blocked", "taint_report"})
#: The largest string an AER line holds inline (C.2.1(6): 1 MiB of UTF-8); a longer tool result is carved (D-218, RB-3).
INLINE_MAX: Final = 1 << 20

# rule ids (catalogue mcphunt, version 1)
R_TOOL_MSG: Final = "mcphunt.tool_call_id_match@1"
R_TURN: Final = "mcphunt.turn_alignment@1"
R_PAIR: Final = "mcphunt.event_pairs_call_unverified@1"
R_COUNTERS: Final = "mcphunt.acc.counters@1"
R_TASK: Final = "mcphunt.task_prompt_copy@1"
R_DEFENCE: Final = "mcphunt.defence_label@1"
R_RESULT: Final = "mcphunt.result_full_vs_message@1"
R_RESULT_DIFFERS: Final = "mcphunt.result_message_differs@1"
R_ARGS_RAW: Final = "mcphunt.args_unparsed@1"
R_ARGS_JSON: Final = "mcphunt.call_arguments_json@1"
R_EMPTY: Final = "mcphunt.empty_assistant_text@1"
R_UNKNOWN_SERVER: Final = "mcphunt.unknown_server@1"
R_CANARY: Final = "mcphunt.canary_flagged@1"
R_DURATION: Final = "mcphunt.duration_no_clock@1"
R_HARNESS: Final = "mcphunt.deposit_harness_unverified@1"
R_MODEL: Final = "mcphunt.model_identity_unverified@1"
R_USER: Final = "mcphunt.user_is_task_unverified@1"
R_SYSTEM: Final = "mcphunt.system_prompt_by_harness_unverified@1"
R_CONTEXT: Final = "mcphunt.context_is_message_prefix_unverified@1"
R_UNPLACED: Final = "mcphunt.unplaced_message@1"
R_TOOLSET: Final = "mcphunt.tool_set_offered_unverified@1"
R_SERVER_PKG: Final = "mcphunt.server_package_unverified@1"
R_EVENT_TIME: Final = "mcphunt.event_timestamp_unverified@1"
R_COLLECTED: Final = "mcphunt.collection_time_unverified@1"
R_RUN_END: Final = "mcphunt.run_end_unverified@1"
R_GUARD: Final = "mcphunt.taint_guard_unverified@1"
R_LABELS: Final = "mcphunt.labels_recorded_unverified@1"
R_DOCUMENT: Final = "mcphunt.unreadable_document@1"
R_GEN: Final = "aer.output_after_generator@1"
R_AFTER_CALL: Final = "aer.execution_after_call@1"
R_AFTER_SUBJECT: Final = "aer.decision_after_subject@1"

_RUN_STATUS: Final = {"stop": "ok", "error": "error", "length": "limit", "tool_calls": "limit"}


def _p(*tokens: str | int) -> str:
    return json_pointer(*tokens)


def _dict(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


class _Rec:
    """A record under construction (as in the other families): fields, evidence, rules, unknowns, sources, ext, lex."""

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
        self.ext[key] = self.enc(value, _p("ext", "mcphunt", key))

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
            ext["mcphunt"] = dict(self.ext)
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


class McpHuntMapper:
    """``Mapper`` for ``mcphunt.traces`` (D.2.4, D.21)."""

    mapper_id: Final = ADAPTER_ID
    version: Final = ADAPTER_VERSION
    accepts: Final = frozenset({(DIALECT_ID, VARIANT)})
    namespaces: Final = NAMESPACES
    catalogues: Final = CATALOGUES

    def map(self, unit: ExecutionUnit, ctx: MappingContext) -> Iterator[AerRecord]:
        yield from _Build(unit, ctx).run()

    @staticmethod
    def prov_primary(flags: frozenset[str]) -> str:
        """Trace documents are written by the producing harness: ``native``."""
        return "native"

    def degenerate_header(self, unit: ExecutionUnit, ctx: MappingContext, *, issue_code: str, detail: str) -> dict[str, Any]:
        """The header of a degenerate AER (D.2.8 case 3): a document the reader refuses is one execution named by its
        label; none of its traces is mapped (the streaming reader fails closed, D-242)."""
        artefact = unit.primary.artefact
        origin_key = next((k for k in ("label", "path") if isinstance(artefact.origin.data.get(k), str)), None)
        if origin_key is None:
            raise MalformedArtefact("the artefact's origin names no label: no document can be named")
        label = str(artefact.origin.data[origin_key])
        header: dict[str, Any] = {
            "k": "execution", "id": "exec", "aer": "0.1", "ex": ctx.ex, "mode": unit.mode, "unit": "agent_execution",
            "source_key": {"sha256": artefact.sha256, "loc": unit.primary.locator.key()},
            "artifacts": [artefact.to_json()], "adapter": {"id": ADAPTER_ID, "version": ADAPTER_VERSION},
            "dialect": {"id": DIALECT_ID, "variant": VARIANT}, "profile": ctx.profile.header(),
            "rules": ctx.catalogue_versions(CATALOGUES), "ns": dict(NAMESPACES), "canon": "jcs-rfc8785", "hash": "sha256",
            "task": {"benchmark": "mcphunt", "task_id": f"document:{label}"}, "ev": "O", "by": "source",
            "evf": {"/task/task_id": "D"}, "rule": [ctx.rule(R_DOCUMENT, "/task/task_id")],
            "unk": {"/instrumentation": "not_recorded", "/task/attack_id": "not_applicable"},
            "src": [{"a": "a0", "o": f"/{origin_key}"}],
        }
        ctx.issue(issue_code, ids=["exec"], rule=ctx.rule(R_DOCUMENT), severity="error", detail=detail)
        return header


def server_actor(server: str) -> str:
    """The local id of the runtime actor of an MCP server label (``srv_<label>``, non-id characters as ``_``)."""
    return "srv_" + "".join(c if c.isascii() and (c.isalnum() or c == "_") else "_" for c in server.lower())[:40]


class _Build:
    def __init__(self, unit: ExecutionUnit, ctx: MappingContext) -> None:
        self.unit, self.ctx = unit, ctx
        item = unit.primary
        value = item.value
        if not isinstance(value, dict) or not isinstance(value.get("trace"), dict):
            raise MalformedArtefact("the located item is not an MCPHunt trace view")
        self.envelope: dict[str, Any] = _dict(value.get("envelope"))
        self.t: dict[str, Any] = value["trace"]
        self.base = str(item.locator.p or "")
        self.span = item.locator.bytes  # the trace's byte range: every locator into the trace is that slice (item 149)
        self.envelope_spans: dict[str, Any] = _dict(value.get("envelope_spans"))
        if not _TRACE_KEYS_MIN <= set(self.t):
            raise MalformedArtefact("the trace lacks the keys the v2.0.0 schema writes")
        self.family = ctx.profile.family_table()
        self.limits = IngestLimits()
        self.counters: dict[str, int] = {}
        self.messages: list[str] = []
        self.servers: dict[str, str] = {}
        self.aligned = True
        self.guarded = False
        self.final_after_error: str | None = None
        self.canary_flagged: list[str] = []  # executions of canary-flagged events (D-289)
        self.canary_paired: set[int] = set()  # indexes of the flagged events that paired with a call
        self.reused_ids: set[str] = set()  # call ids that name more than one call or tool message in the trace
        self.placed: set[int] = set()  # indexes of the source messages already emitted
        label = item.artefact.origin.data.get("label", item.artefact.origin.data.get("path"))
        self.split = split_of(str(label)) if isinstance(label, str) else None
        self._check_shape()

    # ---------------------------------------------------------------------------------------------- helpers
    def R(self, rule_id: str, pointer: str | None = None) -> str:  # noqa: N802 - mirrors MappingContext.rule
        return self.ctx.rule(rule_id, pointer)

    def issue(self, code: str, ids: Sequence[str], rule: str, *, severity: str = "warning", detail: str | None = None) -> None:
        self.ctx.issue(code, ids=list(ids), rule=self.R(rule), severity=severity, detail=detail)  # type: ignore[arg-type]

    def next_id(self, prefix: str) -> str:
        n = self.counters.get(prefix, 0)
        self.counters[prefix] = n + 1
        return f"{prefix}{n}"

    def loc(self, *tokens: str | int) -> dict[str, Any]:
        """A locator into the trace: the C.9.1 byte-range form ``{"a", "bytes": [start, end], "p": <inside the trace>}``,
        so resolution parses that slice alone (regen item 149); the document pointer only without a byte range."""
        if self.span is None:
            return {"a": "a0", "p": self.base + _p(*tokens)}
        pointer = _p(*tokens)
        return {"a": "a0", "bytes": [self.span[0], self.span[1]], **({"p": pointer} if pointer else {})}

    def envelope_loc(self, name: str) -> dict[str, Any]:
        """A locator of an envelope member: its own byte range when the reader found it, else the document pointer."""
        span = self.envelope_spans.get(name)
        if isinstance(span, list) and len(span) == 2 and all(isinstance(n, int) for n in span):
            return {"a": "a0", "bytes": [span[0], span[1]]}
        return {"a": "a0", "p": _p(name)}

    def carved(self, value: object, *tokens: str | int) -> dict[str, Any] | None:
        """A ``$blob`` for a string over :data:`INLINE_MAX` bytes of UTF-8 at ``tokens`` inside the trace, else ``None``
        (the value stays inline). The bytes are carved from the stored document by the trace's own byte range,
        ``{"bytes": [start, end], "p": <pointer inside the trace>}`` (D-218, RB-3; D-323): only that element is parsed,
        never the whole document, and the value is unchanged (``utf8``: the string's own UTF-8 bytes)."""
        if not isinstance(value, str) or len(value) * 4 <= INLINE_MAX \
                or len(value.encode("utf-8", "surrogatepass")) <= INLINE_MAX:
            return None
        span = self.unit.primary.locator.bytes
        carve: Callable[..., dict[str, Any]] | None = getattr(self.ctx, "carve", None)
        if span is None or not callable(carve):
            raise MalformedArtefact("a tool result over 1 MiB needs the trace's byte range to be carved")
        return carve({"bytes": [span[0], span[1]], "p": _p(*tokens)}, "utf8")

    def _check_shape(self) -> None:
        t = self.t
        for key in ("messages", "events", "turn_log"):
            if not isinstance(t[key], list) or not all(isinstance(x, dict) for x in t[key]):
                raise MalformedArtefact(f"trace.{key} is not an array of objects")
        for e in t["events"]:
            if not _EVENT_KEYS <= set(e) or set(e) - _EVENT_KEYS - _EVENT_OPTIONAL:
                raise MalformedArtefact("an event does not have the v2.0.0 keys")
        for m in t["messages"]:
            if not isinstance(m.get("role"), str) or "content" not in m:
                raise MalformedArtefact("a message has no role or content")

    # ---------------------------------------------------------------------------------------------- run
    def run(self) -> Iterator[dict[str, Any]]:
        body: list[dict[str, Any]] = []
        conversation = self._conversation()
        body += self._actors()
        body += self._scopes()
        body += self._fixtures()
        body += conversation
        body += self._judgements()
        self._checks()
        yield self._header()
        yield from body

    # ---------------------------------------------------------------------------------------------- header
    def _header(self) -> dict[str, Any]:
        t = self.t
        task: dict[str, Any] = {"benchmark": "mcphunt", "task_id": t["task_id"]}
        evf: dict[str, str] = {}
        rules: list[str] = []
        unk = {"/instrumentation": "not_recorded", "/task/attack_id": "not_applicable"}
        if isinstance(t.get("risk_mechanism"), str) and t["risk_mechanism"]:
            task["suite"] = t["risk_mechanism"]
        if isinstance(t.get("env_type"), str) and t["env_type"]:
            task["environment"] = t["env_type"]
        defence, mitigation = t.get("defense"), t.get("mitigation_level")
        if isinstance(defence, str) and defence.lower() != "none":
            task["defense_id"] = defence
        elif isinstance(mitigation, str) and mitigation.lower() != "none":
            task["defense_id"] = f"mitigation_prompt:{mitigation}"
        else:
            task["defense_id"] = None
        evf["/task/defense_id"] = "D"
        rules.append(self.R(R_DEFENCE, "/task/defense_id"))
        rules.append(self.R(R_HARNESS, "/task/attack_id"))
        profile = self.ctx.profile
        header: dict[str, Any] = {
            "k": "execution", "id": "exec", "aer": "0.1", "ex": self.ctx.ex, "mode": self.unit.mode,
            "unit": "agent_execution",
            "source_key": {"sha256": self.unit.primary.artefact.sha256, "loc": self.unit.primary.locator.key()},
            "artifacts": [self.unit.primary.artefact.to_json()],
            "adapter": {"id": ADAPTER_ID, "version": ADAPTER_VERSION},
            "dialect": {"id": DIALECT_ID, "variant": VARIANT},
            "profile": profile.header(), "rules": self.ctx.catalogue_versions(CATALOGUES), "ns": dict(NAMESPACES),
            "canon": "jcs-rfc8785", "hash": "sha256", "task": task, "ev": "O", "by": "source", "unk": unk,
            "src": [self.loc("task_id"), self.loc("env_type"), self.loc("defense")],
        }
        ext: dict[str, Any] = {"envelope": self.envelope, "split": self.split,
                               "trace": {k: t[k] for k in ("trace_id", "task_category", "risk_category", "risk_type",
                                                           "expected_risk", "sink_policy", "ablation_profile", "wire_api",
                                                           "mitigation", "mitigation_level", "defense", "truncated",
                                                           "api_errors", "tool_errors", "num_events", "num_turns",
                                                           "servers_used", "canary_read_servers", "actual_data_path")
                                         if k in t},
                               "labeling": t["labeling"], "completion_checks": t.get("completion_checks"),
                               "measurement": t["measurement"]}
        lex = LexHints()
        header["ext"] = {"mcphunt": encode_value(ext, at="/ext/mcphunt", lex=lex)}
        hints = lex.as_dict()
        if hints:
            header["ext"]["lex"] = hints
        header["evf"] = evf
        header["rule"] = rules
        return header

    # ---------------------------------------------------------------------------------------------- actors and scopes
    def _actors(self) -> list[dict[str, Any]]:
        t = self.t
        out: list[dict[str, Any]] = []
        for aid, kind, name in (("bench", "benchmark", "mcphunt"), ("harness", "harness", "mcphunt harness")):
            rec = _Rec(k="actor", id=aid, kind=kind, name=name, ev="I")
            rec.cite(self.R(R_HARNESS))
            commit = self.envelope.get("pipeline_git_commit")
            rec.unk.update({"/code": "not_recorded", "/version": "not_recorded"})
            if aid == "harness" and isinstance(commit, str):
                rec.x("pipeline_git_commit", commit)
            out.append(rec.done())
        user = _Rec(k="actor", id="user", kind="simulated_user", name="task prompt", ev="I")
        user.cite(self.R(R_USER))
        out.append(user.done())
        agent = _Rec(k="actor", id="agent", kind="llm_agent", ev="O", on_behalf_of="user")
        agent.set("name", t["model"])
        agent.data["model"] = {"requested": agent.enc(t["model"], "/model/requested")}
        agent.tag("/model", "I", self.R(R_MODEL, "/model"))
        agent.tag("/on_behalf_of", "I", self.R(R_USER, "/on_behalf_of"))
        agent.loc(self.loc("model"))
        m = _dict(t.get("measurement"))
        params = {k: m[k] for k in ("generation_temperature", "generation_max_tokens", "max_turns") if k in m}
        if params:
            agent.data["params"] = agent.enc(params, "/params")
            agent.loc(self.loc("measurement"))
        agent.unk["/model/served"] = "not_recorded"
        agent.unk["/model/provider"] = "not_recorded"
        out.append(agent.done())
        versions = _dict(m.get("mcp_versions"))
        packages = _dict(self.family.get("server_packages"))
        for server, aid in sorted(self.servers.items(), key=lambda kv: kv[1]):
            rec = _Rec(k="actor", id=aid, kind="tool_runtime", name=server, on_behalf_of="agent", ev="O")
            rec.loc(self.loc("events"))
            rec.tag("/on_behalf_of", "I", self.R(R_PAIR, "/on_behalf_of"))
            names = [p for p in packages.get(server, []) if p in versions]
            if len(names) == 1:
                rec.data["code"] = {"dist": rec.enc(names[0], "/code/dist"),
                                    "dist_version": rec.enc(versions[names[0]], "/code/dist_version")}
                rec.tag("/code/dist", "I", self.R(R_SERVER_PKG, "/code/dist"))
                rec.loc(self.loc("measurement", "mcp_versions", names[0]))
            else:
                rec.unk["/code"] = "not_recorded"
                rec.cite(self.R(R_UNKNOWN_SERVER if server not in packages else R_SERVER_PKG, "/code"))
            out.append(rec.done())
        if self.guarded:
            d = _Rec(k="actor", id="def", kind="defense", name=str(t.get("defense")), ev="I")
            d.cite(self.R(R_GUARD))
            d.loc(self.loc("defense"))
            out.append(d.done())
        judge = _Rec(k="actor", id="judge", kind="judge", name="mcphunt labeler", ev="I")
        judge.cite(self.R(R_LABELS))
        judge.unk.update({"/code": "not_recorded", "/model": "not_recorded"})
        rules_version = self.envelope.get("labeling_rules_version")
        if isinstance(rules_version, str):
            judge.set("version", rules_version)
            judge.tag("/version", "O")
            judge.loc(self.envelope_loc("labeling_rules_version"))
        out.append(judge.done())
        return out

    def _scopes(self) -> list[dict[str, Any]]:
        t = self.t
        run = _Rec(k="scope", id="run", kind="run", ev="O")
        run.loc(self.loc())
        tl = t["turn_log"]
        finish = tl[-1].get("finish_reason") if tl else None
        status = _RUN_STATUS.get(str(finish)) if finish is not None else None
        if status is not None:
            run.data["status"] = status
            run.tag("/status", "I", self.R(R_RUN_END, "/status"))
            run.loc(self.loc("turn_log", len(tl) - 1, "finish_reason"))
            if status != "ok":
                self.issue("incomplete_run", ["run"], R_RUN_END, severity="info", detail=str(finish)[:20])
        else:
            run.unk["/status"] = "not_recorded"
        stamp = t.get("collection_timestamp")
        if isinstance(stamp, str):
            run.data["t"] = {"raw": {"end": run.enc(stamp, "/t/raw/end")}}
            run.tag("/t/raw", "O")
            run.unk.update({"/t/end": "ambiguous", "/t/start": "not_recorded", "/t/dur_s": "ambiguous"})
            run.cite(self.R(R_COLLECTED, "/t/end"))
        else:
            run.unk["/t"] = "not_recorded"
        if self.final_after_error is not None:
            run.x("final_message", self.final_after_error)
            run.loc(self.loc("final_message"))
        if "duration_s" in t:
            run.x("duration_s", t["duration_s"])
            run.cite(self.R(R_DURATION, "/t/dur_s"))
        out = [run.done()]
        att = _Rec(k="scope", id="att0", kind="attempt", parent="run", actor="agent", ev="O")
        att.loc(self.loc("messages"))
        att.unk.update({"/index": "not_recorded", "/scored": "not_recorded"})
        out.append(att.done())
        return out

    def _fixtures(self) -> list[dict[str, Any]]:
        t = self.t
        seed = _Rec(k="fixture", id="fx0", kind="environment_seed", ev="O")
        seed.set("content", t["env_snapshot"])
        seed.loc(self.loc("env_snapshot"))
        tools = _Rec(k="fixture", id="fx1", kind="tool_definitions", ev="O")
        m = _dict(t["measurement"])
        tools.set("content", {k: m[k] for k in ("servers_available", "tool_set") if k in m})
        tools.loc(self.loc("measurement"))
        tools.x("names_only", True)
        return [seed.done(), tools.done()]

    # ---------------------------------------------------------------------------------------------- conversation
    def _conversation(self) -> list[dict[str, Any]]:
        t = self.t
        out: list[dict[str, Any]] = []
        msgs = t["messages"]
        # a call id links a call and a tool message (class D) only when it names exactly one of each in the trace; a
        # reused id (providers restart them per turn) links nothing, and each of its messages is emitted once, as an
        # orphan (regen item 39, bug pass BF-29)
        by_id: dict[str, list[tuple[int, dict[str, Any]]]] = {}
        for i, m in enumerate(msgs):
            if m["role"] == "tool" and isinstance(m.get("tool_call_id"), str):
                by_id.setdefault(m["tool_call_id"], []).append((i, m))
        call_ids: dict[str, int] = {}
        for m in msgs:
            if m["role"] == "assistant":
                for call in m.get("tool_calls") or []:
                    if isinstance(_dict(call).get("id"), str):
                        call_ids[call["id"]] = call_ids.get(call["id"], 0) + 1
        tool_msgs = {cid: found[0] for cid, found in by_id.items() if len(found) == 1 and call_ids.get(cid) == 1}
        self.reused_ids = {cid for cid in set(by_id) | set(call_ids)
                           if len(by_id.get(cid, ())) > 1 or call_ids.get(cid, 0) > 1}  # fmt: skip
        used_tool_msgs: set[int] = set()  # indexes of the tool messages emitted for a call
        events_by_turn: dict[int, list[tuple[int, dict[str, Any]]]] = {}
        for j, e in enumerate(t["events"]):
            events_by_turn.setdefault(int(e["turn"]) if isinstance(e["turn"], int) else -1, []).append((j, e))
            server = e["server"] if isinstance(e["server"], str) and e["server"] else "unknown"
            self.servers.setdefault(server, server_actor(server))
        self.guarded = any(e.get("sanitized_args") is not None or e.get("taint_blocked") for e in t["events"])
        # the leading system and user messages
        for i, m in enumerate(msgs):
            if m["role"] not in ("system", "user"):
                break
            out.append(self._plain(i, m))
        assistants = [(i, m) for i, m in enumerate(msgs) if m["role"] == "assistant"]
        tl = t["turn_log"]
        aligned = len(tl) in (len(assistants), len(assistants) + 1) and all(
            tl[k].get("n_tool_calls") == len(m.get("tool_calls") or []) and tl[k].get("has_text") == (m.get("content") not in ("", None))
            for k, (_i, m) in enumerate(assistants))
        self.aligned = aligned
        if not aligned:
            self.issue("mcphunt.turn_misaligned", ["att0"], R_TURN, detail=f"turns={len(tl)} assistants={len(assistants)}")
        for k, entry in enumerate(tl):
            mc = self._model_call(k, entry)
            out.append(mc)
            if k < len(assistants):
                i, m = assistants[k]
                rec, calls = self._assistant(i, m, mc["id"], aligned)
                out.append(rec)
                events = events_by_turn.get(k + 1, [])
                out += self._calls(k, calls, events, tool_msgs, used_tool_msgs)
            elif k == len(assistants) and isinstance(t.get("final_message"), str):
                if entry.get("finish_reason") == "error":
                    self.final_after_error = t["final_message"]  # an errored call produced no answer: kept in ext
                else:
                    out.append(self._final(mc["id"], aligned and entry.get("n_tool_calls") == 0))
        if len(tl) < len(assistants):
            for i, m in assistants[len(tl):]:
                rec, calls = self._assistant(i, m, None, False)
                out.append(rec)
        orphans = [(i, m) for found in by_id.values() for i, m in found if i not in used_tool_msgs]
        for i, m in sorted(orphans, key=lambda o: o[0]):
            rec = self._plain(i, m)
            out.append(rec)
            self.issue("orphan_tool_result", [rec["id"]], R_TOOL_MSG)
        # every source message is kept: one the layout has no place for (a user or system message after the first
        # assistant turn, a tool message without a call id) follows, in source order, with an issue; no position among
        # the turns is inferred for it (regen item 40, bug pass BF-30)
        for i, m in enumerate(msgs):
            if i not in self.placed:
                rec = self._plain(i, m)
                out.append(rec)
                if m["role"] == "tool":
                    self.issue("orphan_tool_result", [rec["id"]], R_TOOL_MSG)
                else:
                    self.issue("mcphunt.unplaced_message", [rec["id"]], R_UNPLACED)
        # one issue per trace: the withholding trigger of D-289 (RW-1); counts only, never a value. It is read from the
        # raw events, so a flagged event that pairs with no call (another name form, an off-by-one turn) still raises
        # it: the ids are the paired events' executions, and the attempt when a flagged event paired with none
        # (regen item 38, bug pass BF-27).
        flagged = [j for j, e in enumerate(t["events"])
                   if e.get("canary_in_args") is True or e.get("canary_in_result") is True]  # fmt: skip
        if flagged:
            ids = list(self.canary_flagged)
            if any(j not in self.canary_paired for j in flagged):
                ids.append("att0")
            self.issue("mcphunt.canary_flagged", ids, R_CANARY, severity="info",
                       detail=f"{len(flagged)} canary-flagged event(s)")
        return out

    def _result(self, rec: _Rec, content: object, i: int) -> dict[str, Any]:
        """A tool message's content: ``text`` inline, or ``value`` holding a ``$blob`` when it is carved (``text`` is
        typed ``str``; a ``value`` is a JSON position, C.11.5)."""
        ref = self.carved(content, "messages", i, "content")
        return {"text": rec.enc(content, "/parts/0/text")} if ref is None else {"value": ref}

    def _plain(self, i: int, m: Mapping[str, Any]) -> dict[str, Any]:
        mid = self.next_id("m")
        role = m["role"]
        rec = _Rec(k="message", id=mid, scope="att0", role=role, ev="O")
        content = m.get("content")
        if role == "tool":
            rec.data["parts"] = [{"t": "tool_result", **self._result(rec, content, i)}]
            rec.unk.update({"/parts/0/responds_to": "ambiguous", "/actor": "ambiguous", "/generated_by": "not_recorded"})
            rec.cite(self.R(R_TOOL_MSG, "/parts/0/responds_to"))
        else:
            rec.data["parts"] = [{"t": "text", "text": rec.enc(content, "/parts/0/text")}] if content not in ("", None) else []
            if role == "system":
                rec.data["actor"] = "harness"
                rec.tag("/actor", "I", self.R(R_SYSTEM, "/actor"))
            elif role == "user":
                rec.data["actor"] = "user"
                rec.tag("/actor", "I", self.R(R_USER, "/actor"))
                if content != self.t["task_prompt"]:
                    self.issue("mcphunt.task_prompt_differs", [mid], R_TASK, severity="info")
                else:
                    rec.x("task_prompt_copy", True)
                    rec.tag("/ext/mcphunt/task_prompt_copy", "D", self.R(R_TASK, "/ext/mcphunt/task_prompt_copy"))
            else:
                rec.unk["/actor"] = "ambiguous"
                rec.cite(self.R(R_CONTEXT, "/actor"))
        rec.loc(self.loc("messages", i))
        self.messages.append(mid)
        self.placed.add(i)
        return rec.done()

    def _model_call(self, k: int, entry: Mapping[str, Any]) -> dict[str, Any]:
        mc = _Rec(k="model_call", id=self.next_id("mc"), actor="agent", role="agent", scope="att0", status="kept", ev="O")
        mc.data["input"] = list(self.messages)
        mc.tag("/input", "I", self.R(R_CONTEXT, "/input"))
        mc.data["tools"] = "fx1"
        mc.tag("/tools", "I", self.R(R_TOOLSET, "/tools"))
        usage: dict[str, Any] = {}
        for src, dst in (("prompt_tokens", "input_tokens"), ("completion_tokens", "output_tokens")):
            v = entry.get(src)
            if isinstance(v, int) and not isinstance(v, bool) and v >= 0:
                usage[dst] = v
        if usage and any(usage.values()):
            mc.data["usage"] = usage
            mc.tag("/usage", "O:provider")
        elif usage:  # all zero (an errored turn): a placeholder, kept verbatim in ext (C.7.3)
            mc.x("usage_reported", usage)
            mc.unk["/usage"] = "ambiguous"
            mc.cite(self.R(R_TURN, "/usage"))
        if isinstance(entry.get("finish_reason"), str):
            mc.set("finish_reason", entry["finish_reason"])
            mc.tag("/finish_reason", "O:provider")
            if entry["finish_reason"] == "error":
                mc.data["status"] = "error"
        if self.aligned:
            mc.tag("/status", "D", self.R(R_TURN, "/status"))
        else:
            mc.tag("/status", "I", self.R(R_CONTEXT, "/status"))
        mc.unk.update({"/request": "not_recorded", "/response": "not_recorded", "/served_model": "not_recorded",
                       "/params": "not_recorded", "/t": "not_recorded"})
        mc.x("turn", entry.get("turn"))
        mc.loc(self.loc("turn_log", k))
        if self.messages:
            mc.edge(self.messages[-1], "causal")
            mc.tag("/after", "I", self.R(R_CONTEXT, "/after"))
        return mc.done()

    def _assistant(self, i: int, m: Mapping[str, Any], mc_id: str | None, aligned: bool) -> tuple[dict[str, Any], list[tuple[str, Mapping[str, Any], int]]]:
        mid = self.next_id("m")
        rec = _Rec(k="message", id=mid, scope="att0", role="assistant", actor="agent", ev="O")
        parts: list[dict[str, Any]] = []
        content = m.get("content")
        if content not in ("", None):
            parts.append({"t": "text", "text": rec.enc(content, "/parts/0/text")})
        elif content == "":
            rec.x("empty_text", True)
            rec.tag("/ext/mcphunt/empty_text", "D", self.R(R_EMPTY, "/ext/mcphunt/empty_text"))
        calls: list[tuple[str, Mapping[str, Any], int]] = []
        for c_index, call in enumerate(m.get("tool_calls") or []):
            k = len(parts)
            fn = _dict(_dict(call).get("function"))
            name, raw = fn.get("name"), fn.get("arguments")
            part: dict[str, Any] = {"t": "tool_call", "name": rec.enc(name if isinstance(name, str) else str(name), _p("parts", k, "name"))}
            args: Any = None
            parsed = False
            if isinstance(raw, str):
                try:
                    args = strict_json_loads(raw.encode("utf-8"), self.limits)
                    parsed = True
                except (IngestError, UnicodeEncodeError):
                    parsed = False
            if parsed:
                part["args"] = rec.enc(args, _p("parts", k, "args"))
                rec.tag(_p("parts", k, "args"), "D", self.R(R_ARGS_JSON, _p("parts", k, "args")))
            else:
                part["args"] = rec.enc(None, _p("parts", k, "args"))
                rec.unk[_p("parts", k, "args")] = "ambiguous"
                rec.cite(self.R(R_ARGS_JSON, _p("parts", k, "args")))
            if isinstance(raw, str):
                part["args_raw"] = rec.enc(raw, _p("parts", k, "args_raw"))
            cid = _dict(call).get("id")
            if isinstance(cid, str):
                part["provider_call_id"] = rec.enc(cid, _p("parts", k, "provider_call_id"))
            parts.append(part)
            calls.append((part_id(mid, k), _dict(call), c_index))
        rec.data["parts"] = parts
        rec.loc(self.loc("messages", i))
        self.placed.add(i)
        if mc_id is not None:
            rec.data["generated_by"] = mc_id
            rec.tag("/generated_by", "D" if aligned else "I", self.R(R_TURN if aligned else R_CONTEXT, "/generated_by"))
            rec.edge(mc_id, "causal")
            rec.tag("/after", "D", self.R(R_GEN, "/after"))
        else:
            rec.unk["/generated_by"] = "not_recorded"
            rec.cite(self.R(R_TURN, "/generated_by"))
        self.messages.append(mid)
        return rec.done(), calls

    def _final(self, mc_id: str, aligned: bool) -> dict[str, Any]:
        mid = self.next_id("m")
        rec = _Rec(k="message", id=mid, scope="att0", role="assistant", actor="agent", generated_by=mc_id, ev="O")
        text = self.t["final_message"]
        rec.data["parts"] = [{"t": "text", "text": rec.enc(text, "/parts/0/text")}] if text != "" else []
        if text == "":
            rec.x("empty_text", True)
            rec.tag("/ext/mcphunt/empty_text", "D", self.R(R_EMPTY, "/ext/mcphunt/empty_text"))
        rec.loc(self.loc("final_message"))
        rec.tag("/generated_by", "D" if aligned else "I", self.R(R_TURN if aligned else R_CONTEXT, "/generated_by"))
        rec.edge(mc_id, "causal")
        rec.tag("/after", "D", self.R(R_GEN, "/after"))
        rec.x("wire_field", "final_message")
        self.messages.append(mid)
        return rec.done()

    def _calls(self, k: int, calls: list[tuple[str, Mapping[str, Any], int]], events: list[tuple[int, dict[str, Any]]],
               tool_msgs: Mapping[str, tuple[int, dict[str, Any]]], used: set[int]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        names_ok = len(calls) == len(events) and all(
            _name_matches(_dict(call.get("function")).get("name"), e) for (_p_id, call, _c), (_j, e) in zip(calls, events, strict=False))
        if (calls or events) and not names_ok:
            self.issue("call_result_link_conflict", [c[0] for c in calls] or ["att0"], R_PAIR,
                       detail="length" if len(calls) != len(events) else "names")
        for n, (call_part, call, _c) in enumerate(calls):
            event = events[n] if names_ok else None
            cid = call.get("id")
            tool_msg = tool_msgs.get(cid) if isinstance(cid, str) else None
            if isinstance(cid, str) and cid in self.reused_ids:
                self.issue("call_result_link_conflict", [call_part], R_PAIR, detail="call_id_not_unique")
            generator: str | None = None
            runtime: str | None = None
            if event is not None:
                j, e = event
                server = e["server"] if isinstance(e["server"], str) and e["server"] else "unknown"
                runtime = self.servers[server]
                if server not in _dict(self.family.get("server_packages")):
                    self.issue("mcphunt.unknown_server", [call_part], R_UNKNOWN_SERVER, severity="info")
                prev = call_part.split("#", 1)[0]
                decision: str | None = None
                if e.get("sanitized_args") is not None or e.get("taint_blocked"):
                    dc = _Rec(k="decision", id=self.next_id("dc"), actor="def", scope="att0", subject=call_part,
                              verdict="modify", ev="O")
                    dc.tag("/actor", "I", self.R(R_GUARD, "/actor"))
                    dc.tag("/subject", "I", self.R(R_PAIR, "/subject"))
                    dc.loc(self.loc("events", j))
                    if "taint_report" in e:
                        dc.x("taint_report", e["taint_report"])
                    if "taint_blocked" in e:
                        dc.x("taint_blocked", e["taint_blocked"])
                    dc.unk.update({"/reason": "not_recorded", "/t": "not_recorded"})
                    dc.edge(prev, "causal")
                    dc.tag("/after", "D", self.R(R_AFTER_SUBJECT, "/after"))
                    out.append(dc.done())
                    decision = dc.id
                te = _Rec(k="tool_execution", id=self.next_id("te"), actor=runtime, scope="att0", ev="O")
                te.data["call"] = call_part
                te.tag("/call", "I", self.R(R_PAIR, "/call"))
                te.set("name", e["tool"])
                if "args_raw" in e or "args_parse_error" in e:
                    te.unk["/args"] = "ambiguous"
                    te.x("args_raw", e.get("args_raw"))
                    te.x("args_parse_error", e.get("args_parse_error"))
                    te.cite(self.R(R_ARGS_RAW, "/args"))
                    self.issue("mcphunt.args_unparsed", [call_part], R_ARGS_RAW, severity="info")
                else:
                    te.set("args", e["args"])
                if e.get("sanitized_args") is not None:
                    te.set("args_effective", e["sanitized_args"])
                if decision is not None:
                    te.data["authorised_by"] = decision
                    te.tag("/authorised_by", "I", self.R(R_GUARD, "/authorised_by"))
                te.data["status"] = "ok" if e["success"] is True else "error"
                ref = self.carved(e["result_full"], "events", j, "result_full")
                if ref is None:
                    te.set("returned", e["result_full"])
                else:
                    te.data["returned"] = ref
                if e["success"] is not True and isinstance(e.get("error"), str) and e["error"]:
                    te.x("error", e["error"])
                te.x("timestamp", e["timestamp"])
                te.x("latency_ms", e["latency_ms"])
                te.x("canary", {"in_args": e["canary_in_args"], "in_result": e["canary_in_result"],
                                "visible_to_llm": e["canary_visible_to_llm"]})
                te.x("result_chars", e["result_chars"])
                te.x("result_truncated", e["result_truncated"])
                te.unk.update({"/t/start": "ambiguous", "/t/end": "not_recorded", "/t/dur_s": "ambiguous"})
                te.cite(self.R(R_EVENT_TIME, "/t/start"))
                te.cite(self.R(R_DURATION, "/t/dur_s"))
                te.loc(self.loc("events", j))
                te.edge(prev, "causal")
                te.tag("/after", "D", self.R(R_AFTER_CALL, "/after"))
                if decision is not None:
                    te.edge(decision, "causal")
                out.append(te.done())
                generator = te.id
                if e["canary_in_args"] is True or e["canary_in_result"] is True:
                    self.canary_flagged.append(te.id)
                    self.canary_paired.add(j)
            if tool_msg is None:
                if event is None:
                    self.issue("unexecuted_tool_call", [call_part], R_TOOL_MSG)
                continue
            i, m = tool_msg
            used.add(i)
            mid = self.next_id("m")
            msg = _Rec(k="message", id=mid, scope="att0", role="tool", ev="O")
            part = {"t": "tool_result", "responds_to": call_part, **self._result(msg, m.get("content"), i)}
            msg.tag("/parts/0/responds_to", "D", self.R(R_TOOL_MSG, "/parts/0/responds_to"))
            msg.data["parts"] = [part]
            if generator is not None and runtime is not None:
                msg.data["actor"] = runtime
                msg.data["generated_by"] = generator
                msg.tag("/actor", "I", self.R(R_PAIR, "/actor"))
                msg.tag("/generated_by", "I", self.R(R_PAIR, "/generated_by"))
                msg.edge(generator, "causal")
                msg.tag("/after", "D", self.R(R_GEN, "/after"))
                _j, e = event  # type: ignore[misc]
                content, full = m.get("content"), e["result_full"]
                if content != full:
                    if e["result_truncated"] is True and isinstance(content, str) and isinstance(full, str):
                        self.issue("mcphunt.result_truncated_in_message", [mid], R_RESULT, severity="info")
                    else:
                        self.issue("mcphunt.result_differs", [mid], R_RESULT_DIFFERS, severity="info")
            else:
                msg.unk.update({"/actor": "ambiguous", "/generated_by": "not_recorded"})
                msg.cite(self.R(R_PAIR, "/generated_by"))
            msg.loc(self.loc("messages", i))
            self.messages.append(mid)
            self.placed.add(i)
            out.append(msg.done())
        return out

    # ---------------------------------------------------------------------------------------------- judgements
    def _judgements(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for name, pointer in JUDGEMENTS:
            node: Any = self.t
            for token in pointer.strip("/").split("/"):
                node = node.get(token) if isinstance(node, dict) else None
            if node is None:
                continue
            rec = _Rec(k="judgement", id=self.next_id("j"), actor="judge", subject="run", name=name, ev="O",
                       by="benchmark")
            rec.set("value", node)
            rec.data["origin"] = "checker"
            rec.tag("/origin", "I", self.R(R_LABELS, "/origin"))
            rec.loc(self.loc(*pointer.strip("/").split("/")))
            rec.unk.update({"/inputs": "not_recorded", "/t": "not_recorded"})
            out.append(rec.done())
        return out

    # ---------------------------------------------------------------------------------------------- checks
    def _checks(self) -> None:
        t = self.t
        tl, events, msgs = t["turn_log"], t["events"], t["messages"]
        calls = sum(len(m.get("tool_calls") or []) for m in msgs if m["role"] == "assistant")
        tools = sum(1 for m in msgs if m["role"] == "tool")
        m = _dict(t["measurement"])
        prompt, prompt_ok = _counter_sum(tl, "prompt_tokens")
        completion, completion_ok = _counter_sum(tl, "completion_tokens")
        observed = {"events": len(events), "tool_calls": calls, "tool_messages": tools, "turns": len(tl),
                    "prompt_tokens": prompt, "completion_tokens": completion}
        reported = {"num_events": t.get("num_events"), "num_turns": t.get("num_turns"),
                    "prompt_tokens": m.get("prompt_tokens"), "completion_tokens": m.get("completion_tokens")}
        if not (prompt_ok and completion_ok):  # a counter that is not an integer: a data problem, never a crash
            self.ctx.check(R_COUNTERS, scope="att0", verdict="unverifiable", observed=observed,
                           reason="counters_not_integers")  # fmt: skip
            return
        if not all(isinstance(v, int) and not isinstance(v, bool) for v in reported.values()):
            self.ctx.check(R_COUNTERS, scope="att0", verdict="unverifiable", observed=observed, reason="counters_not_recorded")
            return
        ok = (reported["num_events"] == len(events) == calls == tools and reported["num_turns"] == len(tl)
              and reported["prompt_tokens"] == observed["prompt_tokens"]
              and reported["completion_tokens"] == observed["completion_tokens"])
        self.ctx.check(R_COUNTERS, scope="att0", verdict="consistent" if ok else "inconsistent",
                       observed={**observed, **{f"reported_{k}": v for k, v in reported.items() if isinstance(v, int)}},
                       reason=None if ok else "counters_differ")


def _counter_sum(turn_log: Sequence[Mapping[str, Any]], key: str) -> tuple[int, bool]:
    """The sum of ``key`` over the turn log, and whether every present value is an integer (``None`` or absent counts
    as 0, as before). The source is untrusted: a string, a list or a bool is reported, never passed to ``int``
    (regen item 41, bug pass BF-31)."""
    values = [x.get(key) for x in turn_log]
    ok = all(v is None or (isinstance(v, int) and not isinstance(v, bool)) for v in values)
    return sum(v for v in values if isinstance(v, int) and not isinstance(v, bool)), ok


def _name_matches(call_name: object, event: Mapping[str, Any]) -> bool:
    """A call names ``<server>__<tool>`` (or the bare tool); the event records the server and the tool."""
    if not isinstance(call_name, str):
        return False
    tool, server = event.get("tool"), event.get("server")
    return call_name == tool or call_name == f"{server}__{tool}" or (isinstance(tool, str) and call_name.endswith("__" + tool))
