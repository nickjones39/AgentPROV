"""Mapper ``agentops.trace``: one AgentOps-Bench run -> AER ``aer/0.1`` (docs/architecture D.18.3-D.18.8; DECISIONS
D-193..D-198).

One run file is one execution (content-addressed id). The unit's auxiliary artefact is the joined task definition of the
``tasks`` pin (``task``). What the mapper writes, in record order (backward references only, C.5.2):

1. the header: task coordinates from the record (O), ``ext.agentops`` (label facets, the agent id, totals, the final
   output, the join);
2. actors ``bench``, ``harness``, ``agent``, ``env`` (when a call was dispatched), ``att`` (adversarial condition) and
   ``judge``;
3. scopes ``run`` (status; times not recorded) and ``att0``;
4. fixtures: the task prompt and ground truth (joined), and one ``injection_payload`` per injected result;
5. per step: one ``model_call`` (I) with the step's usage, one assistant message (text, then the calls), and per call a
   ``tool_execution`` (I) and the tool message, or, for an injected failure, a harness ``decision`` and no execution;
   an injected payload adds an attacker ``decision`` (``modify``) between the execution and its message;
6. the judgements (the recorded scores; values O, origin I).

A post-pass applies the profile's ``[[family.agentops.redact]]`` rules to the tool messages' values (D-608, principle
D-604; :mod:`agentprov.adapters.agentops.redact`): a third-party account path in tool output is replaced by a salted
label, model text stays verbatim; one info issue ``agentops.value_redacted`` counts the redacted pointers.

Nothing is invented: no time but the recorded call timestamps (kept raw), no user or system message, no call id, no tool
status. ``aer/0.1`` forbids a generic activity generating a message (C.3.13), so the harness's fault and payload
injections are decisions, following C.5.5 (D-196, implementation note).

Pure (A-2): the output is a function of the unit's bytes, the auxiliary bytes, this code, the profile and the catalogues.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator, Mapping, Sequence
from typing import Any, Final

from agentprov.adapters.agentops import ADAPTER_ID, DIALECT_ID, VARIANT
from agentprov.adapters.agentops.dialect import (
    CALL_KEYS,
    RESULT_KEYS,
    STEP_KEYS,
    LabelFacets,
    parse_label,
    task_files,
)
from agentprov.adapters.agentops.join import TaskJoin, allowlisted, prompt_of
from agentprov.adapters.agentops.pairing import RULE as R_PAIR
from agentprov.adapters.agentops.pairing import pair_step
from agentprov.adapters.agentops.redact import RULE as R_REDACT
from agentprov.adapters.agentops.redact import Redactor, parse_redact_rules
from agentprov.adapters.protocols import AerRecord, MappingContext
from agentprov.adapters.types import ArtefactRef, ExecutionUnit
from agentprov.aer.canon import LexHints, encode_value, json_pointer
from agentprov.aer.ids import part_id
from agentprov.errors import AgentProvError, IngestError, MalformedArtefact
from agentprov.ingest import yamlsafe
from agentprov.ingest.limits import IngestLimits

__all__ = ["ADAPTER_ID", "ADAPTER_VERSION", "CATALOGUES", "NAMESPACES", "AgentOpsMapper"]

ADAPTER_VERSION: Final = "0.1.0"
#: Catalogues this mapper cites; the header lists them at the shipped versions (C.3.1 ``rules``).
CATALOGUES: Final = ("aer", "agentops")
NAMESPACES: Final = {"agentops": "https://w3id.org/agentprov/ns/agentops#"}
#: Placeholder values a typed field never holds (C.7.3), as the validator lists them (aer.validate); such a tool name is
#: kept verbatim with unk "ambiguous" (regen item 34, bug pass BF-23).
_SENTINELS: Final = frozenset({"", "0", "unknown", "none", "null", "n/a", "na", "-", "undefined", "nan"})
_MODEL_CALL_UNKNOWN: Final = ("/finish_reason", "/params", "/request", "/response", "/served_model", "/t", "/tools")
_ERROR_PREFIX: Final = "Error: "
_SUFFIX_SEPARATOR: Final = "\n\n"

# rule ids (catalogue agentops, version 1)
R_FACETS: Final = "agentops.label_facets@1"
R_IDENTITY: Final = "agentops.agent_id_identity_unverified@1"
R_HARNESS: Final = "agentops.deposit_harness_unverified@1"
R_STEP: Final = "agentops.step_is_one_model_call_unverified@1"
R_CONTEXT: Final = "agentops.context_is_logged_prefix_unverified@1"
R_ORDER: Final = "agentops.steps_append_ordered_unverified@1"
R_TEXT_FIRST: Final = "agentops.text_before_calls_unverified@1"
R_EXEC: Final = "agentops.call_is_execution_unverified@1"
R_CALL_TIME: Final = "agentops.call_timestamp_is_dispatch_unverified@1"
R_DURATION: Final = "agentops.duration_no_clock@1"
R_FAULT: Final = "agentops.fault_injection_unverified@1"
R_PAYLOAD: Final = "agentops.payload_injection_unverified@1"
R_SUFFIX: Final = "agentops.payload_suffix@1"
R_ATTACKER: Final = "agentops.payload_attacker_unverified@1"
R_ADVERSARIAL: Final = "agentops.adversarial_condition_unverified@1"
R_JOIN: Final = "agentops.task_join@1"
R_PROMPT: Final = "agentops.prompt_composition_unverified@1"
R_NO_USER: Final = "agentops.user_message_not_logged@1"
R_LIMIT: Final = "agentops.iteration_cap_unverified@1"
R_ERROR: Final = "agentops.run_error@1"
R_EMPTY: Final = "agentops.empty_trace@1"
R_FINAL: Final = "agentops.final_output_copy@1"
R_UNLISTED: Final = "agentops.unlisted_tool_name@1"
R_DISPATCH_ERROR: Final = "agentops.dispatch_error_text@1"
R_SCORES: Final = "agentops.scores_recorded_unverified@1"
R_SAFETY_DEFAULT: Final = "agentops.safety_default_unverified@1"
R_COUNTERS: Final = "agentops.acc.counters@1"
R_GEN: Final = "aer.output_after_generator@1"
R_AFTER_CALL: Final = "aer.execution_after_call@1"
R_AFTER_SUBJECT: Final = "aer.decision_after_subject@1"
#: The judgement order and the scores they read (verbatim metric names; C.3.10).
JUDGEMENTS: Final = ("completion", "safety", "efficiency", "cost", "cost_normalized_accuracy")


def _p(*tokens: str | int) -> str:
    return json_pointer(*tokens)


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


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
        """``ext.agentops.<key>`` (encoded)."""
        self.ext[key] = self.enc(value, _p("ext", "agentops", key))

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
            ext["agentops"] = dict(self.ext)
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


class AgentOpsMapper:
    """``Mapper`` for ``agentops.trace`` (D.2.4, D.18)."""

    mapper_id: Final = ADAPTER_ID
    version: Final = ADAPTER_VERSION
    accepts: Final = frozenset({(DIALECT_ID, VARIANT)})
    namespaces: Final = NAMESPACES
    catalogues: Final = CATALOGUES

    def map(self, unit: ExecutionUnit, ctx: MappingContext) -> Iterator[AerRecord]:
        yield from _Build(unit, ctx).run()

    @staticmethod
    def prov_primary(flags: frozenset[str]) -> str:
        """Run files are written by the producing harness: ``native``."""
        return "native"

    def degenerate_header(self, unit: ExecutionUnit, ctx: MappingContext, *, issue_code: str, detail: str) -> dict[str, Any]:
        """The header of a degenerate AER (D.2.8 case 3): the task from the label (O, origin locator)."""
        artefact = unit.primary.artefact
        facets, origin_key = _facets_of(artefact)
        if facets is None:
            raise MalformedArtefact("the artefact's label is outside the AgentOps-Bench label grammar: no task can be named")
        task = {"benchmark": "agentops-bench", "suite": facets.domain, "environment": facets.condition,
                "task_id": facets.task_id}
        header = _header_base(unit, ctx, origin_key, "agent_execution", [artefact.to_json()], task)
        header["src"] = [{"a": "a0", "o": f"/{origin_key}"}]
        header["unk"]["/task/attack_id"] = "not_recorded"
        ctx.issue(issue_code, ids=["exec"], rule=ctx.rule(R_FACETS), severity="error", detail=detail)
        return header


def _facets_of(artefact: ArtefactRef) -> tuple[LabelFacets | None, str]:
    data = artefact.origin.data
    for key in ("label", "path"):
        value = data.get(key)
        if isinstance(value, str):
            return parse_label(value), key
    return None, "label"


def _header_base(unit: ExecutionUnit, ctx: MappingContext, origin_key: str, kind: str,
                 artifacts: list[dict[str, Any]], task: dict[str, Any]) -> dict[str, Any]:
    return {
        "k": "execution",
        "id": "exec",
        "aer": "0.1",
        "ex": ctx.ex,
        "mode": unit.mode,
        "unit": kind,
        "source_key": {"sha256": unit.primary.artefact.sha256, "loc": unit.primary.locator.key()},
        "artifacts": artifacts,
        "adapter": {"id": ADAPTER_ID, "version": ADAPTER_VERSION},
        "dialect": {"id": DIALECT_ID, "variant": VARIANT},
        "profile": ctx.profile.header(),
        "rules": ctx.catalogue_versions(CATALOGUES),
        "ns": dict(NAMESPACES),
        "canon": "jcs-rfc8785",
        "hash": "sha256",
        "task": task,
        "ev": "O",
        "by": "source",
        "unk": {"/instrumentation": "not_recorded", "/task/defense_id": "not_recorded"},
    }


def _number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


class _Build:
    """One mapping run: every record is built in order, then emitted (backward references only)."""

    def __init__(self, unit: ExecutionUnit, ctx: MappingContext) -> None:
        self.unit, self.ctx = unit, ctx
        item = unit.primary
        if not isinstance(item.value, dict):
            raise MalformedArtefact("the located item is not an AgentOps-Bench JSON object")
        self.v: dict[str, Any] = item.value
        facets, self.origin_key = _facets_of(item.artefact)
        if facets is None:
            raise MalformedArtefact("the artefact's label is outside the AgentOps-Bench label grammar")
        self.f: LabelFacets = facets
        self.limits = IngestLimits()
        self.counters: dict[str, int] = {}
        self.artifacts: list[dict[str, Any]] = [item.artefact.to_json()]
        self.ext: dict[str, Any] = {}
        self.ext_evf: dict[str, tuple[str, str | None]] = {}
        self.prev: str | None = None
        self.messages: list[str] = []
        self.payload_fixture: dict[tuple[int, int], str] = {}
        #: tool message id -> (its payload decision record, the suffix length): the offset follows a redaction (D-608)
        self.suffix_of: dict[str, tuple[dict[str, Any], int]] = {}
        self.listed_tools = frozenset(str(t) for t in ctx.profile.family_table().get("tools", ()))
        self._check_shape()
        self.t: dict[str, Any] = self.v["trace"]
        self.steps: list[dict[str, Any]] = self.t["steps"]
        self.outcome_only = len(self.steps) == 0
        self.adversarial = self.v["condition"] == "adversarial"

    # ---------------------------------------------------------------------------------------------- helpers
    def R(self, rule_id: str, pointer: str | None = None) -> str:  # noqa: N802 - mirrors MappingContext.rule
        return self.ctx.rule(rule_id, pointer)

    def issue(self, code: str, ids: Sequence[str], rule: str, *, severity: str = "warning", detail: str | None = None) -> None:
        self.ctx.issue(code, ids=list(ids), rule=self.R(rule), severity=severity, detail=detail)  # type: ignore[arg-type]

    def next_id(self, prefix: str) -> str:
        n = self.counters.get(prefix, 0)
        self.counters[prefix] = n + 1
        return f"{prefix}{n}"

    @staticmethod
    def loc(pointer: str) -> dict[str, Any]:
        return {"a": "a0", "p": pointer}

    def ext_tag(self, key: str, cls: str, rule: str | None) -> None:
        self.ext_evf[_p("ext", "agentops", *key.split("/"))] = (cls, rule)

    def _pos(self, rec: _Rec) -> None:
        if self.prev is not None:
            rec.edge(self.prev, "pos")
            rec.tag("/after", "I", self.R(R_ORDER, "/after"))

    def _check_shape(self) -> None:
        """The structure the mapper relies on (the sniff checked the top-level and trace keys)."""
        trace = _dict(self.v.get("trace"))
        steps = trace.get("steps")
        if not isinstance(steps, list) or not all(isinstance(s, dict) and set(s) == STEP_KEYS for s in steps):
            raise MalformedArtefact("trace.steps is not an array of step objects with the v1 keys")
        for s in steps:
            calls, results = s["tool_calls"], s["tool_results"]
            if not isinstance(calls, list) or not isinstance(results, list):
                raise MalformedArtefact("a step's tool_calls or tool_results is not an array")
            if not all(isinstance(c, dict) and set(c) == CALL_KEYS for c in calls):
                raise MalformedArtefact("a tool call does not have the v1 keys")
            if not all(isinstance(r, dict) and set(r) == RESULT_KEYS for r in results):
                raise MalformedArtefact("a tool result does not have the v1 keys")
        if not isinstance(self.v.get("scores"), dict):
            raise MalformedArtefact("scores is not an object")

    # ---------------------------------------------------------------------------------------------- run
    def run(self) -> Iterator[dict[str, Any]]:
        self.join = self._join()
        body: list[dict[str, Any]] = []
        body += self._actors()
        body += self._scopes()
        body += self._fixtures()
        if not self.outcome_only:
            body += self._steps()
        body += self._judgements()
        self._redact(body)
        self._checks()
        self._header_issues()
        yield self._header()
        yield from body

    # ---------------------------------------------------------------------------------------------- join
    def _join(self) -> TaskJoin:
        task_id = self.v.get("task_id")
        row = task_files().get(task_id) if isinstance(task_id, str) else None
        ref = self.unit.auxiliary.get("task")
        if row is None:
            self.issue("agentops.task_join_missing", ["exec"], R_JOIN, severity="info", detail="not_listed")
            return TaskJoin(task_id, None, "not_listed")
        if ref is None:
            self.issue("agentops.task_join_missing", ["exec"], R_JOIN, severity="info", detail="missing")
            return TaskJoin(task_id, row.label, "missing")
        try:
            raw = self.ctx.open_auxiliary("task")
        except AgentProvError:
            self.issue("agentops.task_join_missing", ["exec"], R_JOIN, severity="info", detail="missing")
            return TaskJoin(task_id, row.label, "missing")
        if len(raw) != ref.bytes or hashlib.sha256(raw).hexdigest() != ref.sha256:
            raise MalformedArtefact("the task auxiliary does not match its digest")
        if ref.sha256 != row.sha256 or ref.bytes != row.bytes:
            self.issue("agentops.task_join_missing", ["exec"], R_JOIN, detail="digest_mismatch")
            return TaskJoin(task_id, row.label, "digest_mismatch")
        self.aid_task = f"a{len(self.artifacts)}"
        self.artifacts.append({**ref.to_json(), "id": self.aid_task, "role": "supporting", "prov_primary": "native"})
        try:
            document = yamlsafe.safe_load(raw, self.limits)
        except (IngestError, yamlsafe.YAMLError):
            self.issue("agentops.task_join_missing", ["exec"], R_JOIN, detail="unparseable")
            return TaskJoin(task_id, row.label, "unparseable")
        task = allowlisted(document)
        if task is None:
            self.issue("agentops.task_join_missing", ["exec"], R_JOIN, detail="unparseable")
            return TaskJoin(task_id, row.label, "unparseable")
        if task.get("id") != task_id:
            self.issue("agentops.task_join_missing", ["exec"], R_JOIN, detail="id_differs")
            return TaskJoin(task_id, row.label, "id_differs")
        return TaskJoin(task_id, row.label, "joined", task)

    # ---------------------------------------------------------------------------------------------- header
    def _task(self) -> tuple[dict[str, Any], dict[str, str], list[str]]:
        task: dict[str, Any] = {"benchmark": "agentops-bench", "task_id": self.v["task_id"],
                                "environment": self.v["condition"], "attack_id": "adversarial" if self.adversarial else None}
        evf: dict[str, str] = {"/task/attack_id": "I"}
        rules = [self.R(R_ADVERSARIAL, "/task/attack_id")]
        domain = self.join.task.get("domain") if self.join.task is not None else None
        if isinstance(domain, str):
            task["suite"] = domain
            evf["/task/suite"] = "D"
            rules.append(self.R(R_JOIN, "/task/suite"))
        return task, evf, rules

    def _header(self) -> dict[str, Any]:
        unit = "outcome_only" if self.outcome_only else "agent_execution"
        task, evf, rules = self._task()
        header = _header_base(self.unit, self.ctx, self.origin_key, unit, self.artifacts, task)
        header["src"] = [self.loc("/task_id"), self.loc("/condition")]
        ext: dict[str, Any] = {
            "label_facets": self.f.to_json(),
            "agent_id": self.v["agent_id"],
            "run_number": self.v["run_number"],
            "completed": self.t["completed"],
            "totals": {k: self.t[k] for k in ("total_input_tokens", "total_output_tokens", "total_cost_usd")},
        }
        if self.t["final_output"] is not None:
            ext["final_output"] = self.t["final_output"]
        ext["join"] = self.join.to_json()
        ext.update(self.ext)
        lex = LexHints()
        header["ext"] = {"agentops": encode_value(ext, at="/ext/agentops", lex=lex)}
        hints = lex.as_dict()
        if hints:
            header["ext"]["lex"] = hints
        self.ext_tag("join", "D", R_JOIN)
        for pointer, (cls, rule) in sorted(self.ext_evf.items()):
            evf[pointer] = cls
            if rule is not None:
                ref = self.R(rule, pointer)
                if ref not in rules:
                    rules.append(ref)
        header["evf"] = evf
        header["rule"] = rules
        return header

    def _header_issues(self) -> None:
        f = self.f
        mismatches = []
        if f.condition != self.v["condition"] or f.condition != self.t["condition"]:
            mismatches.append("condition")
        if f.task_id != self.v["task_id"] or self.t["task_id"] != self.v["task_id"]:
            mismatches.append("task_id")
        if f.run != self.v["run_number"]:
            mismatches.append("run_number")
        if f.model_dir != str(self.v["agent_id"]).replace("/", "_") or self.t["agent_id"] != self.v["agent_id"]:
            mismatches.append("agent_id")
        for name in mismatches:
            self.issue("agentops.label_field_mismatch", ["exec"], R_FACETS, severity="info", detail=name)
        final = self.t["final_output"]
        if isinstance(final, str) and self.steps and final != (self.steps[-1]["reasoning"] or ""):
            self.issue("agentops.final_output_differs", ["exec"], R_FINAL, severity="info")
        if self.join.status == "joined" and not self.outcome_only:
            self.issue("agentops.user_message_not_logged", ["exec"], R_NO_USER, severity="info")

    # ---------------------------------------------------------------------------------------------- actors and scopes
    def _actors(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        bench = _Rec(k="actor", id="bench", kind="benchmark", name="agentops-bench", ev="I")
        bench.cite(self.R(R_HARNESS))
        bench.unk.update({"/code": "not_recorded", "/version": "not_recorded"})
        out.append(bench.done())
        harness = _Rec(k="actor", id="harness", kind="harness", name="agentops_bench", ev="I")
        harness.cite(self.R(R_HARNESS))
        harness.unk.update({"/code": "not_recorded", "/version": "not_recorded"})
        out.append(harness.done())
        agent_id = str(self.v["agent_id"])
        route, _, requested = agent_id.partition("/")
        agent = _Rec(k="actor", id="agent", kind="llm_agent", ev="O")
        agent.set("name", agent_id)
        agent.loc(self.loc("/agent_id"))
        if requested:
            agent.data["model"] = {"provider": agent.enc(route, "/model/provider"),
                                   "requested": agent.enc(requested, "/model/requested")}
            agent.tag("/model", "I", self.R(R_IDENTITY, "/model"))
        else:
            agent.unk["/model/requested"] = "ambiguous"
            agent.cite(self.R(R_IDENTITY, "/model"))
        agent.unk.update({"/model/served": "not_recorded", "/params": "not_recorded"})
        out.append(agent.done())
        if any(not r["injected_failure"] for s in self.steps for r in s["tool_results"]):
            env = _Rec(k="actor", id="env", kind="tool_runtime", name="agentops_bench.InstrumentedToolServer",
                       on_behalf_of="agent", ev="I")
            env.cite(self.R(R_EXEC))
            env.cite(self.R(R_HARNESS, "/on_behalf_of"))
            out.append(env.done())
        # the attacker: the adversarial condition arms it; outside it, a tool result that carries an injected payload
        # (with no failure) still names it as the payload's source, so the run keeps its records (regen item 37, bug
        # pass BF-26: a fixture or decision naming an actor that was never emitted made the whole run adapter_defect)
        payloads = [(i, j) for i, step in enumerate(self.steps) for j, result in enumerate(step["tool_results"])
                    if result["injected_payload"] is not None and result["injected_failure"] is None]  # fmt: skip
        if self.adversarial or payloads:
            att = _Rec(k="actor", id="att", kind="attacker", name="agentops_bench.PROMPT_INJECTIONS", ev="I")
            if self.adversarial:
                att.cite(self.R(R_ADVERSARIAL))
                att.loc(self.loc("/condition"))
            else:
                i, j = payloads[0]
                att.cite(self.R(R_PAYLOAD))
                att.loc(self.loc(_p("trace", "steps", i, "tool_results", j, "injected_payload")))
                self.issue("agentops.payload_outside_adversarial", ["att"], R_PAYLOAD, severity="info",
                           detail=f"{len(payloads)} payload(s) in a {self.v['condition']} run")
            out.append(att.done())
        judge = _Rec(k="actor", id="judge", kind="judge", name="agentops_bench.scoring", ev="I")
        judge.cite(self.R(R_SCORES))
        judge.unk.update({"/code": "not_recorded", "/model": "not_recorded"})
        out.append(judge.done())
        return out

    def _scopes(self) -> list[dict[str, Any]]:
        run = _Rec(k="scope", id="run", kind="run", ev="O")
        run.loc(self.loc("/trace"))
        error = self.t["error"]
        if isinstance(error, str):
            run.data["status"] = "error"
            run.loc(self.loc("/trace/error"))
            run.x("error", error)
            head = error.split(":", 1)[0][:40]
            self.issue("agentops.run_error", ["run"], R_ERROR, detail=head)
            self.issue("incomplete_run", ["run"], R_ERROR)
        elif self.t["completed"] is True:
            run.data["status"] = "ok"
            run.loc(self.loc("/trace/completed"))
        elif self.steps:
            run.data["status"] = "limit"
            run.tag("/status", "I", self.R(R_LIMIT, "/status"))
            self.issue("agentops.iteration_limit", ["run"], R_LIMIT)
            self.issue("incomplete_run", ["run"], R_LIMIT)
        else:
            run.unk["/status"] = "not_recorded"
        run.x("wall_time_seconds", self.t["wall_time_seconds"])
        run.unk.update({"/t/dur_s": "ambiguous", "/t/end": "not_recorded", "/t/start": "not_recorded"})
        run.cite(self.R(R_DURATION, "/t/dur_s"))
        out = [run.done()]
        if not self.outcome_only:
            att = _Rec(k="scope", id="att0", kind="attempt", parent="run", actor="agent", ev="O")
            att.loc(self.loc("/trace/steps"))
            att.unk.update({"/index": "not_recorded", "/scored": "not_recorded"})
            out.append(att.done())
        return out

    # ---------------------------------------------------------------------------------------------- fixtures
    def _fixtures(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        task = self.join.task
        if task is not None:
            prompt, composed = prompt_of(task)
            fx = _Rec(k="fixture", id=self.next_id("fx"), kind="task_prompt", ev="D")
            fx.set("content", prompt)
            fx.cite(self.R(R_JOIN))
            fx.loc({"a": self.aid_task})
            if composed:
                fx.tag("/content", "I", self.R(R_PROMPT, "/content"))
            fx.x("task_fields", {k: task[k] for k in ("difficulty", "optimal_steps", "tags", "tools_available") if k in task})
            out.append(fx.done())
            if "expected_output" in task and task["expected_output"] is not None:
                gt = _Rec(k="fixture", id=self.next_id("fx"), kind="ground_truth", ev="D")
                gt.set("content", task["expected_output"])
                gt.cite(self.R(R_JOIN))
                gt.loc({"a": self.aid_task})
                out.append(gt.done())
        for i, step in enumerate(self.steps):
            for j, result in enumerate(step["tool_results"]):
                payload = result["injected_payload"]
                if payload is None or result["injected_failure"] is not None:
                    continue
                fx = _Rec(k="fixture", id=self.next_id("fx"), kind="injection_payload", ev="O")
                fx.set("content", payload)
                fx.loc(self.loc(_p("trace", "steps", i, "tool_results", j, "injected_payload")))
                fx.data["actor"] = "att"
                fx.tag("/actor", "I", self.R(R_ATTACKER, "/actor"))
                fx.data["vector"] = "agentops.tool_result_suffix"
                fx.tag("/vector", "I", self.R(R_PAYLOAD, "/vector"))
                fx.x("at", {"step": i, "result": j})
                self.payload_fixture[(i, j)] = fx.id
                out.append(fx.done())
        return out

    # ---------------------------------------------------------------------------------------------- steps
    def _steps(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for i, step in enumerate(self.steps):
            base = _p("trace", "steps", i)
            if step["step_number"] != i + 1:
                raise MalformedArtefact("trace.steps step_number is not the 1-based index")
            mc = _Rec(k="model_call", id=self.next_id("mc"), actor="agent", role="agent", scope="att0", status="kept",
                      ev="I")
            mc.data["input"] = list(self.messages)
            mc.cite(self.R(R_STEP))
            mc.tag("/input", "I", self.R(R_CONTEXT, "/input"))
            mc.data["usage"] = {"input_tokens": mc.enc(step["llm_input_tokens"], "/usage/input_tokens"),
                                "output_tokens": mc.enc(step["llm_output_tokens"], "/usage/output_tokens")}
            mc.tag("/usage", "O")
            mc.loc(self.loc(base))
            self._pos(mc)
            mc.unk.update({key: "not_recorded" for key in _MODEL_CALL_UNKNOWN})
            out.append(mc.done())
            self.prev = mc.id
            msg, call_parts = self._assistant(i, step, mc.id)
            out.append(msg)
            pairing = pair_step(step["tool_calls"], step["tool_results"])
            if pairing.conflict is not None:
                self.issue("call_result_link_conflict", list(call_parts), R_PAIR, detail=pairing.conflict)
            elif pairing.repeated_names:
                self.issue("agentops.repeated_tool_names", list(call_parts), R_PAIR, severity="info")
            for j, result in enumerate(step["tool_results"]):
                linked = j in pairing.links
                call_part = call_parts[j] if linked else None
                out += self._result(i, j, step, result, call_part, msg["id"])
        return out

    def _assistant(self, i: int, step: Mapping[str, Any], mc_id: str) -> tuple[dict[str, Any], list[str]]:
        base = _p("trace", "steps", i)
        mid = self.next_id("m")
        rec = _Rec(k="message", id=mid, scope="att0", role="assistant", actor="agent", generated_by=mc_id, ev="O")
        parts: list[dict[str, Any]] = []
        reasoning = step["reasoning"]
        if reasoning is not None:
            parts.append({"t": "text", "text": rec.enc(reasoning, _p("parts", 0, "text"))})
        call_parts: list[str] = []
        for call in step["tool_calls"]:
            k = len(parts)
            name = call["tool_name"]
            if not isinstance(name, str) or name.lower() in _SENTINELS:
                rec.unk[_p("parts", k, "name")] = "ambiguous"
            parts.append({"t": "tool_call", "name": rec.enc(name, _p("parts", k, "name")),
                          "args": rec.enc(call["arguments"], _p("parts", k, "args"))})
            rec.unk[_p("parts", k, "args_raw")] = "not_recorded"
            rec.unk[_p("parts", k, "provider_call_id")] = "not_recorded"
            call_parts.append(part_id(mid, k))
            if self.listed_tools and name not in self.listed_tools:
                self.issue("agentops.unlisted_tool_name", [part_id(mid, k)], R_UNLISTED, severity="info")
        rec.data["parts"] = parts
        if reasoning is not None and call_parts:
            rec.cite(self.R(R_TEXT_FIRST, "/parts"))
        rec.loc(self.loc(base))
        rec.tag("/role", "I", self.R(R_STEP, "/role"))
        rec.tag("/actor", "I", self.R(R_STEP, "/actor"))
        rec.tag("/generated_by", "I", self.R(R_STEP, "/generated_by"))
        rec.edge(mc_id, "causal")
        rec.tag("/after", "I", self.R(R_GEN, "/after"))
        self.messages.append(mid)
        self.prev = mid
        return rec.done(), call_parts

    def _result(self, i: int, j: int, step: Mapping[str, Any], result: Mapping[str, Any],
                call_part: str | None, step_msg: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        base = _p("trace", "steps", i, "tool_results", j)
        call = step["tool_calls"][j] if j < len(step["tool_calls"]) else None
        call_base = _p("trace", "steps", i, "tool_calls", j)
        failure, payload = result["injected_failure"], result["injected_payload"]
        if failure is not None and payload is not None:
            self.issue("agentops.failure_with_payload", [call_part or "exec"], R_FAULT)
        generator: str
        actor = "env"
        if failure is not None:
            dc = _Rec(k="decision", id=self.next_id("dc"), actor="harness", scope="att0", verdict="other",
                      subtype="agentops.fault_injection", ev="I")
            dc.cite(self.R(R_FAULT))
            if call_part is not None:
                dc.data["subject"] = call_part
                dc.tag("/subject", "I", self.R(R_PAIR, "/subject"))
                dc.edge(call_part.split("#", 1)[0], "causal")
                dc.tag("/after", "I", self.R(R_AFTER_SUBJECT, "/after"))
                self.issue("unexecuted_tool_call", [call_part], R_FAULT)
            else:  # the step's calls and results do not pair: the decision is about the step's message, never an
                # earlier result's tool message (regen item 36, bug pass BF-25)
                dc.data["subject"] = step_msg
                dc.tag("/subject", "I", self.R(R_PAIR, "/subject"))
            if self.prev is not None and (call_part is None or self.prev != call_part.split("#", 1)[0]):
                dc.edge(self.prev, "pos")
                dc.cite(self.R(R_ORDER, "/after"))
            dc.x("injected_failure", failure)
            dc.x("latency_ms", result["latency_ms"])
            dc.unk.update({"/reason": "not_recorded", "/t": "not_recorded"})
            dc.loc(self.loc(_p(*base.strip("/").split("/"), "injected_failure")))
            out.append(dc.done())
            self.prev = generator = dc.id
            actor = "harness"
        else:
            te = _Rec(k="tool_execution", id=self.next_id("te"), actor="env", scope="att0", ev="I")
            te.cite(self.R(R_EXEC))
            if call is not None:
                te.set("name", call["tool_name"])
                te.set("args", call["arguments"])
                if not isinstance(call["tool_name"], str) or call["tool_name"].lower() in _SENTINELS:
                    te.unk["/name"] = "ambiguous"
                te.evf.update({"/name": "O", "/args": "O"})
                te.loc(self.loc(call_base))
                te.data["t"] = {"raw": {"start": te.enc(call["timestamp"], "/t/raw/start")}}
                te.evf["/t/raw"] = "O"
                te.unk["/t/start"] = "ambiguous"
                te.cite(self.R(R_CALL_TIME, "/t/start"))
            else:
                te.set("name", result["tool_name"])
                te.evf["/name"] = "O"
                if not isinstance(result["tool_name"], str) or result["tool_name"].lower() in _SENTINELS:
                    te.unk["/name"] = "ambiguous"
                te.unk.update({"/args": "ambiguous", "/t/start": "not_recorded"})
            if call_part is not None:
                te.data["call"] = call_part
                te.tag("/call", "I", self.R(R_PAIR, "/call"))
                te.edge(call_part.split("#", 1)[0], "causal")
                te.tag("/after", "I", self.R(R_AFTER_CALL, "/after"))
                if self.prev is not None and self.prev != call_part.split("#", 1)[0]:
                    te.edge(self.prev, "pos")
                    te.cite(self.R(R_ORDER, "/after"))
            else:
                te.unk["/call"] = "ambiguous"
                te.cite(self.R(R_PAIR, "/call"))
                self._pos(te)
            te.x("latency_ms", result["latency_ms"])
            te.unk.update({"/returned": "not_recorded", "/status": "not_recorded", "/t/dur_s": "ambiguous",
                           "/t/end": "not_recorded"})
            te.cite(self.R(R_DURATION, "/t/dur_s"))
            te.loc(self.loc(_p(*base.strip("/").split("/"), "latency_ms")))
            out.append(te.done())
            self.prev = generator = te.id
            if payload is not None:
                dc = _Rec(k="decision", id=self.next_id("dc"), actor="att", scope="att0", subject=te.id, verdict="modify",
                          ev="I")
                dc.cite(self.R(R_PAYLOAD))
                dc.edge(te.id, "causal")
                dc.tag("/after", "I", self.R(R_AFTER_SUBJECT, "/after"))
                dc.loc(self.loc(_p(*base.strip("/").split("/"), "injected_payload")))
                dc.unk.update({"/reason": "not_recorded", "/t": "not_recorded"})
                fixture = self.payload_fixture.get((i, j))
                if fixture is not None:
                    dc.x("payload_fixture", fixture)
                text = result["result"]
                suffix = _SUFFIX_SEPARATOR + payload
                suffixed = isinstance(text, str) and text.endswith(suffix)
                if suffixed:
                    dc.x("suffix_offset", len(text) - len(suffix))
                    dc.tag("/ext/agentops/suffix_offset", "D", self.R(R_SUFFIX, "/ext/agentops/suffix_offset"))
                else:
                    self.issue("agentops.payload_suffix_mismatch", [dc.id], R_SUFFIX)
                decision = dc.done()
                out.append(decision)
                if suffixed:  # the tool message below gets the next "m" id
                    self.suffix_of[f"m{self.counters.get('m', 0)}"] = (decision, len(suffix))
                self.prev = generator = dc.id
        mid = self.next_id("m")
        msg = _Rec(k="message", id=mid, scope="att0", role="tool", actor=actor, generated_by=generator, ev="O")
        part: dict[str, Any] = {"t": "tool_result"}
        if call_part is not None:
            part["responds_to"] = call_part
            msg.tag(_p("parts", 0, "responds_to"), "I", self.R(R_PAIR, _p("parts", 0, "responds_to")))
        else:
            msg.unk[_p("parts", 0, "responds_to")] = "ambiguous"
            msg.cite(self.R(R_PAIR, _p("parts", 0, "responds_to")))
        value = result["result"]
        if isinstance(value, str):
            part["text"] = msg.enc(value, _p("parts", 0, "text"))
            if value.startswith(_ERROR_PREFIX) and failure is None:
                self.issue("agentops.dispatch_error_result", [mid], R_DISPATCH_ERROR, severity="info")
        else:
            part["value"] = msg.enc(value, _p("parts", 0, "value"))
        part["name"] = msg.enc(result["tool_name"], _p("parts", 0, "name"))
        if not isinstance(result["tool_name"], str) or result["tool_name"].lower() in _SENTINELS:
            msg.unk[_p("parts", 0, "name")] = "ambiguous"
        msg.data["parts"] = [part]
        msg.loc(self.loc(base))
        rule = R_FAULT if failure is not None else (R_PAYLOAD if payload is not None else R_EXEC)
        msg.tag("/role", "I", self.R(R_FAULT if failure is not None else R_EXEC, "/role"))
        msg.tag("/actor", "I", self.R(rule, "/actor"))
        msg.tag("/generated_by", "I", self.R(rule, "/generated_by"))
        msg.edge(generator, "causal")
        msg.tag("/after", "I", self.R(R_GEN, "/after"))
        out.append(msg.done())
        self.messages.append(mid)
        self.prev = mid
        return out

    # ---------------------------------------------------------------------------------------------- redaction
    def _redact(self, records: Sequence[dict[str, Any]]) -> None:
        """D-608: the profile's ``[[family.agentops.redact]]`` rules over the finished tool messages; a recorded payload
        suffix is kept verbatim and its decision's offset follows the redacted text."""
        rules = parse_redact_rules(self.ctx.profile.family_table().get("redact", ()), f"profile {self.ctx.profile.id!r}")
        redactor = Redactor(self.ctx.profile.id, self.ctx.profile.version, rules)
        if not redactor.active:
            return
        changed: list[str] = []
        count = 0
        for record in records:
            mid = str(record.get("id"))
            suffix = self.suffix_of.get(mid)
            keep: dict[str, int] = {}
            if suffix is not None:
                keep[_p("parts", 0, "text")] = int(suffix[0]["ext"]["agentops"]["suffix_offset"])
            done = redactor.apply(record, lambda p: self.R(R_REDACT, p), keep)
            if not done:
                continue
            changed.append(mid)
            count += len(done)
            if suffix is not None:
                decision, length = suffix
                decision["ext"]["agentops"]["suffix_offset"] = len(record["parts"][0]["text"]) - length
        if changed:
            self.issue("agentops.value_redacted", changed, R_REDACT, severity="info",
                       detail=f"{count} values redacted by the profile's redact rules (D-608)")

    # ---------------------------------------------------------------------------------------------- judgements
    def _judgements(self) -> list[dict[str, Any]]:
        scores = self.v["scores"]
        out: list[dict[str, Any]] = []
        safety = _dict(scores.get("safety"))
        default_safety = self.outcome_only or safety.get("injections_present") == 0
        for name in JUDGEMENTS:
            if name not in scores:
                continue
            rec = _Rec(k="judgement", id=self.next_id("j"), actor="judge", subject="run", name=name, ev="O",
                       by="benchmark")
            rec.set("value", scores[name])
            rec.loc(self.loc(_p("scores", name)))
            if name == "safety" and default_safety:
                rec.data["origin"] = "harness_default"
                rec.tag("/origin", "I", self.R(R_SAFETY_DEFAULT, "/origin"))
                rec.loc(self.loc("/scores/safety/injections_present"))
            else:
                rec.data["origin"] = "checker"
                rec.tag("/origin", "I", self.R(R_SCORES, "/origin"))
                if name == "completion":
                    rec.unk["/generated_by"] = "not_recorded"
                rec.unk["/inputs"] = "not_recorded"
            rec.tag("/subject", "I", self.R(R_SCORES, "/subject"))
            rec.unk["/t"] = "not_recorded"
            out.append(rec.done())
        return out

    # ---------------------------------------------------------------------------------------------- checks
    def _checks(self) -> None:
        if self.outcome_only:
            self.issue("no_execution_observed", ["run"], R_EMPTY)
            self.issue("agentops.empty_trace", ["run"], R_EMPTY)
        scores = self.v["scores"]
        efficiency, cost = _dict(scores.get("efficiency")), _dict(scores.get("cost"))
        calls = sum(len(s["tool_calls"]) for s in self.steps)
        observed = {
            "steps": len(self.steps),
            "calls": calls,
            "input_tokens": sum(int(s["llm_input_tokens"]) for s in self.steps if _number(s["llm_input_tokens"])),
            "output_tokens": sum(int(s["llm_output_tokens"]) for s in self.steps if _number(s["llm_output_tokens"])),
        }
        reported = {
            "total_tool_calls": efficiency.get("total_tool_calls"),
            "step_breakdown": len(cost["step_breakdown"]) if isinstance(cost.get("step_breakdown"), list) else None,
            "total_input_tokens": self.t["total_input_tokens"],
            "total_output_tokens": self.t["total_output_tokens"],
        }
        scope = "run" if self.outcome_only else "att0"
        if not all(isinstance(v, int) and not isinstance(v, bool) for v in reported.values()):
            self.ctx.check(R_COUNTERS, scope=scope, verdict="unverifiable", observed=observed, reason="counters_not_recorded")
            return
        ok = (reported["total_tool_calls"] == calls and reported["step_breakdown"] == len(self.steps)
              and reported["total_input_tokens"] == observed["input_tokens"]
              and reported["total_output_tokens"] == observed["output_tokens"])
        self.ctx.check(R_COUNTERS, scope=scope, verdict="consistent" if ok else "inconsistent",
                       observed={**observed, **{f"reported_{k}": int(v) for k, v in reported.items()}},
                       reason=None if ok else "counters_differ_from_steps")
