"""Mapper ``autogen.runs``: one AutoGen guard-placement run row -> AER ``aer/0.1`` (docs/architecture D.19.3-D.19.8;
DECISIONS D-300..D-306).

One run row (one line of a phase's ``runs.jsonl``) is one execution (content-addressed id over the file digest and the
line locator). Its per-unit inputs (dialect :data:`~agentprov.adapters.autogen.dialect.AUXILIARY_FILES`) are the
phase's event log and guard log and the deposit's probe sets, InjecAgent cases, ``config.json`` and phase-0 capture.
What the mapper writes, in record order (backward references only, C.5.2):

1. the header: task coordinates from the row and the probe join, ``ext.autogen`` (label facets, run settings, the
   attempt, the join);
2. actors: ``bench``, ``harness``, ``user``, the agents that spoke or were called (``researcher``, ``writer``,
   ``selector``), ``ingest`` (entry ``agent``), ``env`` (when a tool ran), ``att`` (an attack probe or case) and one
   ``guard_<name>`` per guard whose verdicts the run's events hold;
3. scopes ``run`` and ``att0``;
4. fixtures: the probe document (``other``, ``autogen.probe_document``), the injection payload (attack probes and
   InjecAgent cases), the task prompt (the harness's template, checked by digest) and one system prompt per agent (from
   its first logged request);
5. the TaskResult stream in order: each message preceded by the model call that generated it (from the event log's
   request/response pair), tool executions and their result messages (one per result item), a guard ``decision`` where
   a block replaced a recorded text, and memory queries as an activity with its artefact; model calls that generated no
   recorded message (the selector's) follow;
6. guard decisions whose effect is only in the request log, then one ``judgement`` per guard verdict.

Nothing is invented: no time is typed (the wall-clock values stay in ``ext``), no relation comes from order, and a guard
digest is only ever compared with the digest of a recorded text (D-304).

Pure (A-2): the output is a function of the unit's bytes, the auxiliary bytes, this code, the profile and the catalogues.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from typing import Any, Final

from agentprov.adapters.autogen import ADAPTER_ID, DIALECT_ID, VARIANTS
from agentprov.adapters.autogen.citation import citations
from agentprov.adapters.autogen.dialect import LabelFacets, parse_label, parse_rows
from agentprov.adapters.autogen.events import Event, RunEvents, load_run_events, sha16
from agentprov.adapters.protocols import AerRecord, MappingContext
from agentprov.adapters.types import ArtefactRef, ExecutionUnit
from agentprov.aer.canon import LexHints, encode_value, json_pointer
from agentprov.aer.ids import part_id
from agentprov.errors import AgentProvError, IngestError, MalformedArtefact
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads

__all__ = ["ADAPTER_ID", "ADAPTER_VERSION", "CATALOGUES", "NAMESPACES", "WITHHELD", "AutoGenMapper"]

ADAPTER_VERSION: Final = "0.1.0"
CATALOGUES: Final = ("aer", "autogen")
NAMESPACES: Final = {"autogen": "https://w3id.org/agentprov/ns/autogen#"}
#: The harness's replacement text for a blocked text (``WITHHELD`` in harness.py); a constant, compared verbatim.
WITHHELD: Final = "[content withheld by guard]"
BENCHMARK: Final = "autogen-guard-placement"
AGENTS: Final = ("researcher", "writer", "selector")
_MAX_STOP: Final = "Maximum number of messages"
_TEXT_STOP: Final = "Text '"

# rule ids (catalogue autogen, version 1)
R_FACETS: Final = "autogen.label_facets@1"
R_HARNESS: Final = "autogen.deposit_harness_unverified@1"
R_AUTOGEN_VERSION: Final = "autogen.autogen_version_unverified@1"
R_MODEL: Final = "autogen.config_agent_model_unverified@1"
R_SETTINGS: Final = "autogen.run_settings_unverified@1"
R_TASK_AUTHOR: Final = "autogen.task_is_harness_template_unverified@1"
R_TASK_DIGEST: Final = "autogen.task_template_digest@1"
R_INGEST: Final = "autogen.ingest_agent_unverified@1"
R_ORDER: Final = "autogen.taskresult_order@1"
R_ATTEMPT: Final = "autogen.event_attempt@1"
R_REQUEST_SEQ: Final = "autogen.request_seq@1"
R_REQUEST_INPUT: Final = "autogen.request_log_is_model_input_unverified@1"
R_SYSTEM_PROMPT: Final = "autogen.system_prompt_from_request@1"
R_TEXT_EQUAL: Final = "autogen.response_text_equal@1"
R_THOUGHT: Final = "autogen.thought_equal@1"
R_CALL_IDS: Final = "autogen.response_call_ids@1"
R_CALL_LINK: Final = "autogen.call_id_link@1"
R_EXEC: Final = "autogen.execution_result_status@1"
R_ARGS: Final = "autogen.arguments_decoded@1"
R_NOT_ENTERED: Final = "autogen.tool_body_not_entered_unverified@1"
R_MEMORY: Final = "autogen.memory_query_is_harness@1"
R_PROBE: Final = "autogen.probe_join@1"
R_PASSAGE: Final = "autogen.passage_in_document@1"
R_ATTACKER: Final = "autogen.probe_passage_attacker_unverified@1"
R_GUARD: Final = "autogen.guard_verdict_unverified@1"
R_GUARD_DIGEST: Final = "autogen.guard_text_digest@1"
R_GUARD_RAW: Final = "autogen.guard_raw_join@1"
R_BLOCK: Final = "autogen.block_replaces_text_unverified@1"
R_TOOL_BLOCK: Final = "autogen.tool_block_link_unverified@1"
R_NO_DECISION: Final = "autogen.block_without_decision@1"
R_STOP: Final = "autogen.stop_reason_status_unverified@1"
R_TIMES: Final = "autogen.wall_clock_times@1"
R_NO_CALL: Final = "autogen.no_model_call@1"
R_SIDE_LIST: Final = "autogen.acc.side_list@1"
R_GEN: Final = "aer.output_after_generator@1"
R_AFTER_CALL: Final = "aer.execution_after_call@1"
R_AFTER_SUBJECT: Final = "aer.decision_after_subject@1"
_MODEL_CALL_UNKNOWN: Final = ("/params", "/request", "/response", "/served_model", "/tools")


def _p(*tokens: str | int) -> str:
    return json_pointer(*tokens)


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
        """``ext.autogen.<key>`` (encoded)."""
        self.ext[key] = self.enc(value, _p("ext", "autogen", key))

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
            ext["autogen"] = dict(self.ext)
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


class AutoGenMapper:
    """``Mapper`` for ``autogen.runs`` (D.2.4, D.19)."""

    mapper_id: Final = ADAPTER_ID
    version: Final = ADAPTER_VERSION
    accepts: Final = frozenset((DIALECT_ID, v) for v in VARIANTS)
    namespaces: Final = NAMESPACES
    catalogues: Final = CATALOGUES
    #: The profile's context artefacts (event and guard logs, probe sets, InjecAgent cases, config, capture) are read
    #: through the reader's per-unit plan, so the import selects and stores them; for an archive input this is what puts
    #: them in the expand selection (D-200).
    consumes_context: Final = True

    def map(self, unit: ExecutionUnit, ctx: MappingContext) -> Iterator[AerRecord]:
        yield from _Build(unit, ctx).run()

    @staticmethod
    def prov_primary(flags: frozenset[str]) -> str:
        """Run files are written by the producing harness: ``native``."""
        return "native"

    def degenerate_header(self, unit: ExecutionUnit, ctx: MappingContext, *, issue_code: str, detail: str) -> dict[str, Any]:
        """The header of a degenerate AER (D.2.8 case 3): for a run row the task id is its ``probe_id`` or ``case_id``
        (O, row locator); for a whole file the strict loader rejected, its phase label (O, origin pointer). The
        environment is the file's phase (D, label)."""
        item = unit.primary
        value = item.value if isinstance(item.value, dict) else {}
        key = "case_id" if isinstance(value.get("case_id"), str) else "probe_id"
        facets, origin_key = _facets_of(item.artefact)
        if facets is None:
            raise MalformedArtefact("the artefact's label is outside the AutoGen run-file grammar: no task can be named")
        environment = f"phase{facets.phase}" + (f"/{facets.arm}" if facets.arm else "")
        row_task = item.locator.line is not None and isinstance(value.get(key), str)
        # a whole file the strict loader rejected (document-root locator) is named by its phase, as credleak names a
        # cell by its channel; a run row by its probe or case id
        task = {"benchmark": BENCHMARK, "task_id": value[key] if row_task else environment, "environment": environment}
        header: dict[str, Any] = {
            "k": "execution", "id": "exec", "aer": "0.1", "ex": ctx.ex, "mode": unit.mode, "unit": "agent_execution",
            "source_key": {"sha256": item.artefact.sha256, "loc": item.locator.key()},
            "artifacts": [item.artefact.to_json()], "adapter": {"id": ADAPTER_ID, "version": ADAPTER_VERSION},
            "dialect": {"id": DIALECT_ID, "variant": item.variant}, "profile": ctx.profile.header(),
            "rules": ctx.catalogue_versions(CATALOGUES), "ns": dict(NAMESPACES), "canon": "jcs-rfc8785", "hash": "sha256",
            "task": task, "ev": "O", "by": "source", "evf": {"/task/environment": "D"},
            "rule": [ctx.rule(R_FACETS, "/task/environment")],
            "unk": {"/instrumentation": "not_recorded", "/task/attack_id": "not_recorded",
                    "/task/defense_id": "not_recorded"},
            "src": ([{"a": "a0", "line": item.locator.line, "p": "/" + key}] if row_task else []) + [{"a": "a0", "o": f"/{origin_key}"}],
        }
        ctx.issue(issue_code, ids=["exec"], rule=ctx.rule(R_FACETS), severity="error", detail=detail)
        return header


def _facets_of(artefact: ArtefactRef) -> tuple[LabelFacets | None, str]:
    data = artefact.origin.data
    for key in ("label", "path"):
        value = data.get(key)
        if isinstance(value, str):
            return parse_label(value), key
    return None, "label"


def _str(value: object) -> str | None:
    return value if isinstance(value, str) else None


_ROWS: dict[str, tuple[tuple[int, Any], ...]] = {}


def _rows(data: bytes, limits: IngestLimits) -> tuple[tuple[int, Any], ...]:
    """The parsed rows of a JSONL input, cached by content digest (pure: equal bytes give equal rows)."""
    key = hashlib.sha256(data).hexdigest()
    hit = _ROWS.get(key)
    if hit is None:
        hit = parse_rows(data, limits).rows
        if len(_ROWS) >= 8:
            _ROWS.pop(next(iter(_ROWS)))
        _ROWS[key] = hit
    return hit


class _Build:
    """One mapping run: every record is built in order, then emitted (backward references only)."""

    def __init__(self, unit: ExecutionUnit, ctx: MappingContext) -> None:
        self.unit, self.ctx = unit, ctx
        item = unit.primary
        if not isinstance(item.value, dict) or item.locator.line is None:
            raise MalformedArtefact("the located item is not an AutoGen run row with a line locator")
        self.v: dict[str, Any] = item.value
        self.line: int = item.locator.line
        self.variant = item.variant
        facets, self.origin_key = _facets_of(item.artefact)
        if facets is None:
            raise MalformedArtefact("the artefact's label is outside the AutoGen run-file grammar")
        self.f: LabelFacets = facets
        self.fam: Mapping[str, Any] = ctx.profile.family_table()
        self.cite_policy = citations(self.fam, {"variant": self.variant}, f"profile {ctx.profile.id!r}")
        self.limits = IngestLimits()
        self.counters: dict[str, int] = {}
        self.artifacts: list[dict[str, Any]] = [item.artefact.to_json()]
        self.aid: dict[str, str] = {}
        self.msgs: list[dict[str, Any]] = self.v["messages"]
        if not isinstance(self.msgs, list) or not all(isinstance(m, dict) and isinstance(m.get("raw"), dict)
                                                       for m in self.msgs):
            raise MalformedArtefact("messages is not an array of AutoGen message dumps")
        self.prev: str | None = None
        self.emitted: set[str] = set()
        self.digest_ids: dict[str, list[str]] = {}
        self._parts_args: dict[str, Any] = {}
        self.executed: Counter[tuple[str, str]] = Counter()
        self.decided: set[int] = set()
        self.actor_of: dict[str, str] = {}

    # ---------------------------------------------------------------------------------------------- helpers
    def R(self, rule_id: str, pointer: str | None = None) -> str:  # noqa: N802 - mirrors MappingContext.rule
        return self.ctx.rule(self.cite_policy.cite(rule_id), pointer)

    def cls(self, rule_id: str) -> str:
        return self.cite_policy.cls(rule_id)

    def issue(self, code: str, ids: Sequence[str], rule: str, *, severity: str = "warning", detail: str | None = None) -> None:
        self.ctx.issue(code, ids=list(ids), rule=self.R(rule), severity=severity, detail=detail)  # type: ignore[arg-type]

    def next_id(self, prefix: str) -> str:
        n = self.counters.get(prefix, 0)
        self.counters[prefix] = n + 1
        return f"{prefix}{n}"

    def row_loc(self, *tokens: str | int) -> dict[str, Any]:
        out: dict[str, Any] = {"a": "a0", "line": self.line}
        if tokens:
            out["p"] = _p(*tokens)
        return out

    def ev_loc(self, e: Event, *tokens: str | int) -> dict[str, Any]:
        out: dict[str, Any] = {"a": self.aid["events"], "line": e.line}
        if tokens:
            out["p"] = _p(*tokens)
        return out

    def note_digest(self, text: object, rid: str) -> None:
        if isinstance(text, str):
            ids = self.digest_ids.setdefault(sha16(text), [])
            if rid not in ids:
                ids.append(rid)

    # ---------------------------------------------------------------------------------------------- inputs
    def _aux(self, role: str, *, required: bool) -> bytes | None:
        ref = self.unit.auxiliary.get(role)
        if ref is None:
            if required:
                raise MalformedArtefact(f"the per-unit input {role!r} is missing")
            return None
        try:
            raw = self.ctx.open_auxiliary(role)
        except AgentProvError:
            if required:
                raise MalformedArtefact(f"the per-unit input {role!r} was not supplied") from None
            return None
        if len(raw) != ref.bytes or hashlib.sha256(raw).hexdigest() != ref.sha256:
            raise MalformedArtefact(f"the per-unit input {role!r} does not match its digest")
        aid = f"a{len(self.artifacts)}"
        self.aid[role] = aid
        self.artifacts.append({**ref.to_json(), "id": aid, "role": "supporting", "prov_primary": "native"})
        return raw

    def _load_inputs(self) -> None:
        call_ids = [[str(c.get("id")) for c in m["raw"].get("content", []) if isinstance(c, dict)]
                    for m in self.msgs if m.get("type") == "ToolCallRequestEvent"]
        texts = [(str(m.get("source")), m["text"]) for m in self.msgs
                 if m.get("type") == "TextMessage" and m.get("source") in AGENTS and isinstance(m.get("text"), str)]
        events = self._aux("events", required=True)
        assert events is not None
        self.ev: RunEvents = load_run_events(events, str(self.v["run_id"]), self.limits, call_ids=call_ids, texts=texts)
        guard_raw = self._aux("guard_raw", required=False)
        self.guard_raw: dict[tuple[str, str], tuple[int, dict[str, Any]]] = {}
        if guard_raw is not None:
            for line, value in _rows(guard_raw, self.limits):
                if not isinstance(value, dict):
                    continue
                text, key = value.get("text"), (str(value.get("guard")), str(value.get("text_sha")))
                if isinstance(text, str) and sha16(text) == key[1] and key not in self.guard_raw:
                    self.guard_raw[key] = (line, value)
        self.config = self._json_aux("config")
        self.capture = self._json_aux("capture")
        self.probe, self.probe_role = self._probe()

    def _json_aux(self, role: str) -> dict[str, Any] | None:
        raw = self._aux(role, required=False)
        if raw is None:
            return None
        try:
            value = strict_json_loads(raw, self.limits)
        except IngestError:
            return None
        return value if isinstance(value, dict) else None

    def _probe(self) -> tuple[dict[str, Any] | None, str | None]:
        """The probe (or InjecAgent case) the row names, joined by id (``autogen.probe_join@1``)."""
        roles: tuple[str, ...]
        if self.variant == "injecagent":
            key, roles = self.v.get("case_id"), ("injecagent_cases",)
        else:
            key, roles = self.v.get("probe_id"), ("probes", "keyword_probes")
        for role in roles:
            raw = self._aux(role, required=False)
            if raw is None:
                continue
            for line, value in _rows(raw, self.limits):
                if isinstance(value, dict) and value.get("id") == key:
                    self.probe_line = line
                    return value, role
        self.issue("autogen.probe_join_missing", ["exec"], R_PROBE, severity="info")
        return None, None

    # ---------------------------------------------------------------------------------------------- run settings
    def _modes(self) -> tuple[dict[str, str], bool]:
        """The placement modes: the row's ``modes`` (O), else every placement observing (harness code, I)."""
        modes = self.v.get("modes")
        if isinstance(modes, dict) and all(isinstance(v, str) for v in modes.values()):
            return {str(k): str(v) for k, v in modes.items()}, True
        return {pl: "observe" for pl in ("model", "bus", "tool")}, False

    def _block_guard(self) -> tuple[str | None, bool]:
        """The guard whose verdict can change a text: the row's ``block_guard`` (O), else the profile's per-phase value
        (harness code, I)."""
        bg = self.v.get("block_guard")
        if isinstance(bg, str):
            return bg, True
        table = self.fam.get("block_guard_by_phase", {})
        value = table.get(str(self.v.get("phase"))) if isinstance(table, Mapping) else None
        return (str(value) if isinstance(value, str) else None), False

    # ---------------------------------------------------------------------------------------------- run
    def run(self) -> Iterator[dict[str, Any]]:
        self._load_inputs()
        self.modes, self.modes_recorded = self._modes()
        self.block_guard, self.block_guard_recorded = self._block_guard()
        self.requests = self.ev.requests()
        self.responses = self.ev.response_of()
        self.outcome_only = not self.requests
        self.guard_names = sorted({str(g) for e in self.ev.of("guard") for g in (e.value.get("flags") or {})})
        body: list[dict[str, Any]] = []
        body += self._actors()
        body += self._scopes()
        body += self._fixtures()
        body += self._stream()
        body += self._late_decisions()
        body += self._judgements()
        self._checks()
        if self.ev.aborted:
            self.issue("autogen.aborted_attempt_events", ["run"], R_ATTEMPT, severity="info",
                       detail=str(sum(len(a) for a in self.ev.aborted)))
        if self.outcome_only:
            self.issue("no_execution_observed", ["run"], R_NO_CALL)
        yield self._header()
        yield from body

    # ---------------------------------------------------------------------------------------------- header
    def _task(self) -> tuple[dict[str, Any], dict[str, str], list[str], dict[str, str]]:
        key = self.v.get("case_id") if self.variant == "injecagent" else self.v.get("probe_id")
        task: dict[str, Any] = {"benchmark": BENCHMARK, "task_id": str(key),
                                "suite": str(self.v["entry"]),
                                "environment": f"phase{self.f.phase}" + (f"/{self.f.arm}" if self.f.arm else "")}
        evf: dict[str, str] = {"/task/environment": "D"}
        rules = [self.R(R_FACETS, "/task/environment")]
        unk: dict[str, str] = {}
        if self.probe is not None:
            if self.variant == "injecagent":
                task["attack_id"] = "injecagent"
            else:
                task["attack_id"] = _str(self.probe.get("template")) if self.probe.get("label") == "attack" else None
            evf["/task/attack_id"] = "D"
            rules.append(self.R(R_PROBE, "/task/attack_id"))
        else:
            unk["/task/attack_id"] = "not_recorded"
        defense = self._defense_id()
        task["defense_id"] = defense
        evf["/task/defense_id"] = "I"
        rules.append(self.R(R_SETTINGS, "/task/defense_id"))
        return task, evf, rules, unk

    def _defense_id(self) -> str | None:
        parts = []
        dfn = self.v.get("defense")
        if isinstance(dfn, str):
            parts.append(f"prompt:{dfn}")
        for placement in ("model", "bus", "tool"):
            if self.modes.get(placement) == "block":
                parts.append(f"block:{placement}:{self.block_guard}")
        return "+".join(parts) if parts else None

    def _header(self) -> dict[str, Any]:
        task, evf, rules, unk = self._task()
        header: dict[str, Any] = {
            "k": "execution", "id": "exec", "aer": "0.1", "ex": self.ctx.ex, "mode": self.unit.mode,
            "unit": "outcome_only" if self.outcome_only else "agent_execution",
            "source_key": {"sha256": self.unit.primary.artefact.sha256, "loc": self.unit.primary.locator.key()},
            "artifacts": self.artifacts,
            "adapter": {"id": ADAPTER_ID, "version": ADAPTER_VERSION},
            "dialect": {"id": DIALECT_ID, "variant": self.variant},
            "profile": self.ctx.profile.header(),
            "rules": self.ctx.catalogue_versions(CATALOGUES),
            "ns": dict(NAMESPACES), "canon": "jcs-rfc8785", "hash": "sha256", "task": task, "ev": "O", "by": "source",
            "unk": {"/instrumentation": "not_recorded", **unk},
            "src": [self.row_loc("run_id"), self.row_loc("entry"), {"a": "a0", "o": f"/{self.origin_key}"}],
        }
        settings = {k: self.v[k] for k in ("run_id", "phase", "entry", "condition", "defense", "carrier_id", "termination",
                                           "keyword", "block_at", "stop_reason", "wall_s") if k in self.v}
        ext: dict[str, Any] = {
            "label_facets": self.f.to_json(),
            "settings": settings,
            "modes": self.modes,
            "modes_recorded": self.modes_recorded,
            "block_guard": self.block_guard,
            "block_guard_recorded": self.block_guard_recorded,
            "attempt": {"events": len(self.ev.attempt), "aborted_attempts": len(self.ev.aborted)},
        }
        if self.probe is not None:
            ext["probe"] = {"role": self.probe_role,
                            **{k: self.probe[k] for k in ("group", "label", "template", "goal_kind", "source", "carrier_id",
                                                          "attack_type", "user_tool") if k in self.probe}}
        lex = LexHints()
        header["ext"] = {"autogen": encode_value(ext, at="/ext/autogen", lex=lex)}
        hints = lex.as_dict()
        if hints:
            header["ext"]["lex"] = hints
        header["evf"] = evf
        header["rule"] = rules
        return header

    # ---------------------------------------------------------------------------------------------- actors and scopes
    def _actors(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        bench = _Rec(k="actor", id="bench", kind="benchmark", name=BENCHMARK, ev="I")
        bench.cite(self.R(R_HARNESS))
        bench.unk.update({"/code": "not_recorded", "/version": "not_recorded"})
        out.append(bench.done())
        harness = _Rec(k="actor", id="harness", kind="harness", name="autogen-agentchat", ev="I")
        harness.cite(self.R(R_HARNESS))
        versions = (self.capture or {}).get("packages") if isinstance(self.capture, dict) else None
        if isinstance(versions, dict) and isinstance(versions.get("autogen-agentchat"), str):
            harness.data["code"] = {"dist": "autogen-agentchat",
                                    "dist_version": harness.enc(versions["autogen-agentchat"], "/code/dist_version")}
            harness.tag("/code", "I", self.R(R_AUTOGEN_VERSION, "/code"))
            harness.loc({"a": self.aid["capture"], "p": "/packages/autogen-agentchat"})
        else:
            harness.unk["/code"] = "not_recorded"
        out.append(harness.done())
        user = _Rec(k="actor", id="user", kind="simulated_user", name="harness task", ev="I")
        user.cite(self.R(R_TASK_AUTHOR))
        out.append(user.done())
        model = (self.config or {}).get("agent_model") if isinstance(self.config, dict) else None
        spoke = {str(m.get("source")) for m in self.msgs} | {str(e.value.get("agent")) for e in self.ev.of("llm_request")}
        for name in AGENTS:
            if name not in spoke:
                continue
            agent = _Rec(k="actor", id=name, kind="llm_agent", name=name, ev="O")
            agent.loc(self.row_loc("messages"))
            if name == "selector":
                agent.data["role"] = "speaker_selector"
            if isinstance(model, str):
                agent.data["model"] = {"requested": agent.enc(model, "/model/requested")}
                agent.tag("/model", "I", self.R(R_MODEL, "/model"))
                agent.loc({"a": self.aid["config"], "p": "/agent_model"})
            else:
                agent.unk["/model/requested"] = "not_recorded"
            agent.unk.update({"/model/served": "not_recorded", "/params": "not_recorded"})
            if isinstance(self.capture, dict) and "agent_model_echoed" in self.capture:
                agent.x("phase0_echo", self.capture.get("agent_model_echoed"))
                agent.tag("/ext/autogen/phase0_echo", "I", self.R(R_MODEL, "/ext/autogen/phase0_echo"))
            out.append(agent.done())
        if "ingest" in spoke:
            ingest = _Rec(k="actor", id="ingest", kind="harness", name="ingest", role="ingest_agent", ev="I")
            ingest.cite(self.R(R_INGEST))
            out.append(ingest.done())
        if any(m.get("type") == "ToolCallExecutionEvent" for m in self.msgs):
            env = _Rec(k="actor", id="env", kind="tool_runtime", name="autogen_core.tools", ev=self.cls(R_EXEC))
            env.cite(self.R(R_EXEC))
            out.append(env.done())
        if self.probe is not None and (self.variant == "injecagent" or self.probe.get("label") == "attack"):
            att = _Rec(k="actor", id="att", kind="attacker", name="probe passage author", ev="I")
            att.cite(self.R(R_ATTACKER))
            out.append(att.done())
        guards = ((self.config or {}).get("guards") or {}) if isinstance(self.config, dict) else {}
        for g in self.guard_names:
            rec = _Rec(k="actor", id=f"guard_{g}", kind="defense", name=g, ev="I")
            rec.cite(self.R(R_GUARD))
            spec = guards.get(g) if isinstance(guards, dict) else None
            if isinstance(spec, dict) and isinstance(spec.get("model"), str):
                rec.data["model"] = {"requested": rec.enc(spec["model"], "/model/requested")}
                rec.tag("/model", "I", self.R(R_MODEL, "/model"))
                rec.loc({"a": self.aid["config"], "p": _p("guards", g)})
                if isinstance(spec.get("revision"), str):
                    rec.x("revision", spec["revision"])
            out.append(rec.done())
        return out

    def _scopes(self) -> list[dict[str, Any]]:
        run = _Rec(k="scope", id="run", kind="run", ev="O")
        run.loc(self.row_loc())
        stop = self.v.get("stop_reason")
        if isinstance(stop, str) and stop.startswith(_MAX_STOP):
            run.data["status"] = "limit"
            run.tag("/status", "I", self.R(R_STOP, "/status"))
            run.loc(self.row_loc("stop_reason"))
        elif isinstance(stop, str) and stop.startswith(_TEXT_STOP):
            run.data["status"] = "ok"
            run.tag("/status", "I", self.R(R_STOP, "/status"))
            run.loc(self.row_loc("stop_reason"))
        else:
            run.unk["/status"] = "not_recorded"
        run.x("wall_s", self.v.get("wall_s"))
        run.unk.update({"/t/dur_s": "ambiguous", "/t/end": "not_recorded", "/t/start": "not_recorded"})
        run.cite(self.R(R_TIMES, "/t/dur_s"))
        att = _Rec(k="scope", id="att0", kind="attempt", parent="run", ev="O")
        att.loc(self.row_loc("messages"))
        att.unk.update({"/index": "not_recorded", "/scored": "not_recorded"})
        return [run.done(), att.done()]

    # ---------------------------------------------------------------------------------------------- fixtures
    def _fixtures(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        self.fx_task: str | None = None
        self._fx_task_text: str | None = None
        p = self.probe
        if p is not None:
            role = self.probe_role or "probes"
            doc_field = "tool_response" if self.variant == "injecagent" else "text"
            if isinstance(p.get(doc_field), str):
                fx = _Rec(k="fixture", id=self.next_id("fx"), kind="other", subtype="autogen.probe_document", ev="D")
                fx.set("content", p[doc_field])
                fx.cite(self.R(R_PROBE))
                fx.loc({"a": self.aid[role], "line": self.probe_line, "p": _p(doc_field)})
                if isinstance(p.get("canary"), str) and self.variant != "injecagent":
                    fx.x("canary", p["canary"])
                out.append(fx.done())
                self.note_digest(p[doc_field], fx.id)
            pass_field = "attacker_instruction" if self.variant == "injecagent" else "passage"
            attack = self.variant == "injecagent" or p.get("label") == "attack"
            if attack and isinstance(p.get(pass_field), str):
                fx = _Rec(k="fixture", id=self.next_id("fx"), kind="injection_payload", ev="D")
                fx.set("content", p[pass_field])
                fx.cite(self.R(R_PROBE))
                fx.loc({"a": self.aid[role], "line": self.probe_line, "p": _p(pass_field)})
                fx.data["actor"] = "att"
                fx.tag("/actor", "I", self.R(R_ATTACKER, "/actor"))
                document = p.get(doc_field)
                if isinstance(document, str) and p[pass_field].strip()[:60] in document:
                    fx.x("in_document", True)
                    fx.tag("/ext/autogen/in_document", "D", self.R(R_PASSAGE, "/ext/autogen/in_document"))
                else:
                    self.issue("autogen.passage_not_in_document", [fx.id], R_PASSAGE, severity="info")
                for k in ("template", "goal_kind", "canary", "attack_type", "attacker_tools"):
                    if k in p:
                        fx.x(k, p[k])
                out.append(fx.done())
            out += self._task_fixture(p)
        out += self._system_prompts()
        return out

    def _task_text(self, p: Mapping[str, Any]) -> str | None:
        """The harness's task for this run: its template for the entry point with the (defended) document, or the
        InjecAgent case's user instruction (``autogen.task_is_harness_template_unverified@1``, templates in the profile)."""
        if self.variant == "injecagent":
            return _str(p.get("user_instruction"))
        templates = self.fam.get("task_templates", {})
        template = templates.get(str(self.v.get("entry"))) if isinstance(templates, Mapping) else None
        text = p.get("text")
        if not isinstance(template, str) or not isinstance(text, str):
            return None
        dfn = self.v.get("defense")
        defenses = self.fam.get("prompt_defenses", {})
        spec = defenses.get(dfn) if isinstance(dfn, str) and isinstance(defenses, Mapping) else None
        if isinstance(spec, Mapping):
            if spec.get("kind") == "datamark" and isinstance(spec.get("marker"), str):
                text = spec["marker"].join(text.split())
            elif spec.get("kind") == "suffix" and isinstance(spec.get("note"), str):
                text = text + spec["note"]
        return template.replace("{text}", text)

    def _task_fixture(self, p: Mapping[str, Any]) -> list[dict[str, Any]]:
        composed = self._task_text(p)
        if composed is None:
            return []
        task_msg = next((m for m in self.msgs if m.get("type") == "TextMessage" and m.get("source") == "user"), None)
        recorded = task_msg.get("text") if task_msg is not None else None
        guard_shas = {str(e.value.get("text_sha")) for e in self.ev.of("guard")
                      if str(e.value.get("msg_kind", "")).startswith("GroupChatStart")}
        if composed == recorded:
            basis = "task_message"
        elif self.task_decisions_pending() and sha16(composed) in guard_shas:
            basis = "guard_digest"
        else:
            self.issue("autogen.task_template_mismatch", ["exec"], R_TASK_DIGEST, severity="info")
            return []
        fx = _Rec(k="fixture", id=self.next_id("fx"), kind="task_prompt", ev="I")
        fx.set("content", composed)
        fx.cite(self.R(R_TASK_AUTHOR))
        fx.data["actor"] = "user"
        fx.x("checked_against", basis)
        fx.tag("/ext/autogen/checked_against", "D", self.R(R_TASK_DIGEST, "/ext/autogen/checked_against"))
        role = self.probe_role or "probes"
        fx.loc({"a": self.aid[role], "line": self.probe_line})
        if task_msg is not None:
            fx.loc(self.row_loc("messages", self.msgs.index(task_msg), "text"))
        self.fx_task = fx.id
        self._fx_task_text = composed
        if basis == "guard_digest":
            self.note_digest(composed, fx.id)
        return [fx.done()]

    def _system_prompts(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        self.fx_system: dict[str, str] = {}
        for e in sorted(self.requests.values(), key=lambda x: x.seq):
            agent = str(e.value.get("agent"))
            if agent in self.fx_system:
                continue
            first = (e.value.get("messages") or [None])[0]
            if not isinstance(first, dict) or first.get("type") != "SystemMessage" or not isinstance(first.get("text"), str):
                continue
            fx = _Rec(k="fixture", id=self.next_id("fx"), kind="system_prompt", ev="O")
            fx.set("content", first["text"])
            fx.loc(self.ev_loc(e, "messages", 0, "text"))
            fx.data["actor"] = "harness"
            fx.tag("/actor", "I", self.R(R_HARNESS, "/actor"))
            fx.cite(self.R(R_SYSTEM_PROMPT))
            fx.x("agent", agent)
            out.append(fx.done())
            self.fx_system[agent] = fx.id
            self.note_digest(first["text"], fx.id)
        return out

    # ---------------------------------------------------------------------------------------------- stream
    def _responses_by(self) -> tuple[dict[tuple[str, str], list[Event]], dict[tuple[str, ...], list[Event]],
                                     dict[tuple[str, str], list[Event]]]:
        by_text: dict[tuple[str, str], list[Event]] = {}
        by_ids: dict[tuple[str, ...], list[Event]] = {}
        by_thought: dict[tuple[str, str], list[Event]] = {}
        for e in self.ev.of("llm_response"):
            agent, content = str(e.value.get("agent")), e.value.get("content")
            if isinstance(content, str):
                by_text.setdefault((agent, content), []).append(e)
            elif isinstance(content, list):
                ids = tuple(str(c.get("id")) for c in content if isinstance(c, dict))
                by_ids.setdefault(ids, []).append(e)
            thought = e.value.get("thought")
            if isinstance(thought, str) and thought:
                by_thought.setdefault((agent, thought), []).append(e)
        return by_text, by_ids, by_thought

    def _stream(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        self.mc_of: dict[int, str] = {}  # request seq -> model call id
        self.msg_ids: list[str] = []  # message ids emitted, in order
        self.text_of: dict[str, str] = {}  # recorded text -> first message id with it (model-call input match)
        self.call_part: dict[str, str] = {}  # call id -> tool_call part id
        self.result_msg: dict[str, str] = {}  # call id -> tool message id
        self.request_msg: dict[str, str] = {}  # call id -> the request message id
        self.te_by_call: dict[str, str] = {}
        by_text, by_ids, by_thought = self._responses_by()
        self.task_decisions = self._task_block_rows()
        self.tool_blocks = self._tool_block_rows()
        entered = Counter((str(e.value.get("agent")), str(e.value.get("tool"))) for e in self.ev.of("tool_call"))
        ok_results = Counter((str(m.get("source")), str(c.get("name"))) for m in self.msgs
                             if m.get("type") == "ToolCallExecutionEvent" and isinstance(m["raw"].get("content"), list)
                             for c in m["raw"]["content"] if isinstance(c, dict) and c.get("is_error") is False)
        # bodies entered by calls that returned an error: events of the tool minus its successful results (order-free)
        entered = Counter({k: max(0, n - ok_results[k]) for k, n in entered.items()})
        self.fold = self._thought_folds(by_text, by_ids, by_thought)
        folded = set(self.fold.values())
        for i, m in enumerate(self.msgs):
            mtype, source = str(m.get("type")), str(m.get("source"))
            if i in folded:
                continue
            if mtype == "TextMessage" and source == "user":
                out += self._task_message(i, m)
            elif mtype == "TextMessage" and source == "ingest":
                out += self._plain_message(i, m, "ingest", R_INGEST)
            elif mtype == "TextMessage" and source in AGENTS:
                hits = by_text.get((source, str(m.get("text"))), []) if isinstance(m.get("text"), str) else []
                out += self._generated(i, m, source, hits, R_TEXT_EQUAL, [("text", m.get("text"))])
            elif mtype == "ThoughtEvent" and source in AGENTS:
                hits = by_thought.get((source, str(m.get("text"))), []) if isinstance(m.get("text"), str) else []
                out += self._generated(i, m, source, hits, R_THOUGHT, [("reasoning", m.get("text"))])
            elif mtype == "ToolCallRequestEvent" and source in AGENTS:
                content = m["raw"].get("content")
                ids = tuple(str(c.get("id")) for c in content if isinstance(c, dict)) if isinstance(content, list) else ()
                out += self._generated(i, m, source, by_ids.get(ids, []), R_CALL_IDS, None)
            elif mtype == "ToolCallExecutionEvent" and source in AGENTS:
                out += self._executions(i, m, source, entered)
            elif mtype == "MemoryQueryEvent":
                out += self._memory(i, m)
            else:
                raise MalformedArtefact("a TaskResult message of an unknown type or source")
        for seq in sorted(self.requests):
            if seq not in self.mc_of:
                out.append(self._model_call(self.requests[seq]))
        return out

    def _response_of(self, m: Mapping[str, Any], by_text: Mapping[tuple[str, str], list[Event]],
                     by_ids: Mapping[tuple[str, ...], list[Event]]) -> Event | None:
        source, mtype = str(m.get("source")), m.get("type")
        if mtype == "TextMessage" and isinstance(m.get("text"), str):
            hits = by_text.get((source, m["text"]), [])
        elif mtype == "ToolCallRequestEvent" and isinstance(m["raw"].get("content"), list):
            hits = by_ids.get(tuple(str(c.get("id")) for c in m["raw"]["content"] if isinstance(c, dict)), [])
        else:
            hits = []
        return hits[0] if len(hits) == 1 else None

    def _thought_folds(self, by_text: Mapping[tuple[str, str], list[Event]], by_ids: Mapping[tuple[str, ...], list[Event]],
                       by_thought: Mapping[tuple[str, str], list[Event]]) -> dict[int, int]:
        """Target message index -> ThoughtEvent index. AutoGen yields a ThoughtEvent and then the message of the same
        model result (``_assistant_agent.py``); both come from one logged response (``autogen.thought_equal@1``), so the
        thought becomes that message's ``reasoning`` part: one model output, one assistant turn."""
        out: dict[int, int] = {}
        used: list[Event] = []
        for i, m in enumerate(self.msgs):
            if m.get("type") != "ThoughtEvent" or not isinstance(m.get("text"), str):
                continue
            hits = by_thought.get((str(m.get("source")), m["text"]), [])
            for j in range(i + 1, len(self.msgs)):
                if j in out or self.msgs[j].get("source") != m.get("source"):
                    continue
                resp = self._response_of(self.msgs[j], by_text, by_ids)
                if resp is not None and any(resp is h for h in hits) and not any(resp is u for u in used):
                    out[j] = i
                    used.append(resp)
                    break
        return out

    def _base_message(self, i: int, m: Mapping[str, Any], role: str, actor: str) -> _Rec:
        mid = self.next_id("m")
        rec = _Rec(k="message", id=mid, scope="att0", role=role, actor=actor, ev="O")
        rec.loc(self.row_loc("messages", i))
        raw = m["raw"]
        rec.x("message", {"type": m.get("type"), "id": raw.get("id"), "created_at": raw.get("created_at")})
        if isinstance(raw.get("models_usage"), dict):
            rec.x("models_usage", raw["models_usage"])
        if self.prev is not None:
            rec.edge(self.prev, "pos")
            rec.tag("/after", "I", self.R(R_ORDER, "/after"))
        return rec

    def _finish_message(self, rec: _Rec, text: object) -> dict[str, Any]:
        self.actor_of[rec.id] = str(rec.data.get("actor"))
        self.prev = rec.id
        self.msg_ids.append(rec.id)
        if isinstance(text, str):
            self.text_of.setdefault(text, rec.id)
            self.note_digest(text, rec.id)
        return rec.done()

    def _task_message(self, i: int, m: Mapping[str, Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        rec = self._base_message(i, m, "user", "user")
        rec.tag("/actor", "I", self.R(R_TASK_AUTHOR, "/actor"))
        text = m.get("text")
        rec.data["parts"] = [{"t": "text", "text": rec.enc(text, _p("parts", 0, "text"))}]
        if self.task_decisions and (text == WITHHELD or (self.fx_task is not None and text != self._fx_task_text)):
            # the replaced start message has no recorded original to be a decision's subject (C.3.7): the guard is the
            # author of the withheld copy (I), the block is disclosed, and no generator is invented
            rec.data["actor"] = f"guard_{self.block_guard or 'unknown'}"
            rec.tag("/actor", "I", self.R(R_BLOCK, "/actor"))
            rec.unk["/generated_by"] = "not_recorded"
            for e in self.task_decisions:
                self.decided.add(e.line)
            self.issue("autogen.block_subject_not_recorded", [rec.id], R_NO_DECISION, severity="info", detail="bus:GroupChatStart")
        out.append(self._finish_message(rec, text))
        return out

    def _plain_message(self, i: int, m: Mapping[str, Any], actor: str, rule: str) -> list[dict[str, Any]]:
        rec = self._base_message(i, m, "assistant", actor)
        rec.tag("/actor", "I", self.R(rule, "/actor"))
        rec.data["parts"] = [{"t": "text", "text": rec.enc(m.get("text"), _p("parts", 0, "text"))}]
        return [self._finish_message(rec, m.get("text"))]

    def _generated(self, i: int, m: Mapping[str, Any], agent: str, hits: list[Event], rule: str,
                   parts_spec: list[tuple[str, object]] | None) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        mc_id: str | None = None
        if len(hits) == 1:
            e = hits[0]
            rs = e.value.get("request_seq")
            if isinstance(rs, int) and rs in self.requests:
                if rs not in self.mc_of:
                    out.append(self._model_call(self.requests[rs]))
                mc_id = self.mc_of[rs]
        rec = self._base_message(i, m, "assistant", agent)
        parts: list[dict[str, Any]] = []
        thought = self.fold.get(i)
        if thought is not None:
            t = self.msgs[thought]
            parts.append({"t": "reasoning", "text": rec.enc(t.get("text"), _p("parts", 0, "text"))})
            rec.loc(self.row_loc("messages", thought))
            rec.tag(_p("parts", 0), self.cls(R_THOUGHT), self.R(R_THOUGHT, _p("parts", 0)))
            rec.x("thought_message", {"id": t["raw"].get("id"), "created_at": t["raw"].get("created_at"), "index": thought})
        if parts_spec is not None:
            parts += [{"t": t_, "text": rec.enc(v, _p("parts", len(parts) + k, "text"))} for k, (t_, v) in enumerate(parts_spec)]
        else:
            parts += self._call_parts(rec, m, offset=len(parts))
        rec.data["parts"] = parts
        if mc_id is not None:
            rec.data["generated_by"] = mc_id
            rec.tag("/generated_by", self.cls(rule), self.R(rule, "/generated_by"))
            rec.edge(mc_id, "causal")
            rec.tag("/after", "I" if rec.evf.get("/after") == "I" else self.cls(rule), self.R(R_GEN, "/after"))
        else:
            rec.unk["/generated_by"] = "ambiguous" if hits else "not_recorded"
            rec.cite(self.R(rule, "/generated_by"))
            self.issue("autogen.response_unmatched", [rec.id], rule, severity="info",
                       detail="ambiguous" if hits else "none")
        return [*out, self._finish_message(rec, m.get("text"))]

    def _call_parts(self, rec: _Rec, m: Mapping[str, Any], *, offset: int = 0) -> list[dict[str, Any]]:
        parts: list[dict[str, Any]] = []
        content = m["raw"].get("content")
        if not isinstance(content, list):
            raise MalformedArtefact("a ToolCallRequestEvent has no list content")
        for k0, c in enumerate(content):
            k = k0 + offset
            if not isinstance(c, dict) or not isinstance(c.get("arguments"), str):
                raise MalformedArtefact("a FunctionCall has no string arguments")
            part: dict[str, Any] = {"t": "tool_call", "name": rec.enc(c.get("name"), _p("parts", k, "name"))}
            try:
                args = strict_json_loads(c["arguments"].encode("utf-8"), self.limits)
                part["args"] = rec.enc(args, _p("parts", k, "args"))
                self._parts_args[part_id(rec.id, k)] = args
                rec.tag(_p("parts", k, "args"), self.cls(R_ARGS), self.R(R_ARGS, _p("parts", k, "args")))
            except IngestError:
                part["args"] = rec.enc(c["arguments"], _p("parts", k, "args"))
                self.issue("autogen.arguments_not_json", [part_id(rec.id, k)], R_ARGS, severity="info")
            part["args_raw"] = rec.enc(c["arguments"], _p("parts", k, "args_raw"))
            part["provider_call_id"] = rec.enc(c.get("id"), _p("parts", k, "provider_call_id"))
            parts.append(part)
            cid = str(c.get("id"))
            self.call_part[cid] = part_id(rec.id, k)
            self.request_msg[cid] = rec.id
        return parts

    def _model_call(self, req: Event) -> dict[str, Any]:
        agent = str(req.value.get("agent"))
        resp = self.responses.get(req.seq)
        mc = _Rec(k="model_call", id=self.next_id("mc"), actor=agent,
                  role="auxiliary" if agent == "selector" else "agent", scope="att0", ev="O")
        mc.loc(self.ev_loc(req))
        inputs, unmatched = self._inputs(req)
        mc.data["input"] = inputs
        mc.tag("/input", "I", self.R(R_REQUEST_INPUT, "/input"))
        if resp is not None:
            mc.loc(self.ev_loc(resp))
            mc.data["status"] = "kept"
            mc.tag("/status", self.cls(R_REQUEST_SEQ), self.R(R_REQUEST_SEQ, "/status"))
            if isinstance(resp.value.get("finish_reason"), str):
                mc.set("finish_reason", resp.value["finish_reason"])
            usage = resp.value.get("usage")
            if isinstance(usage, dict):
                u = {}
                for src_key, dst in (("prompt_tokens", "input_tokens"), ("completion_tokens", "output_tokens")):
                    if isinstance(usage.get(src_key), int) and not isinstance(usage.get(src_key), bool):
                        u[dst] = usage[src_key]
                if u:
                    mc.data["usage"] = mc.enc(u, "/usage")
            if agent == "selector" and isinstance(resp.value.get("content"), str):
                mc.x("selected", resp.value["content"])
            mc.x("logged_t", {"request": req.value.get("t"), "response": resp.value.get("t")})
        else:
            mc.unk["/status"] = "not_recorded"
            mc.x("logged_t", {"request": req.value.get("t")})
        mc.x("seq", req.seq)
        if unmatched:
            mc.x("input_unmatched", unmatched)
        mc.unk.update({key: "not_recorded" for key in _MODEL_CALL_UNKNOWN})
        mc.unk["/t"] = "ambiguous"
        mc.cite(self.R(R_TIMES, "/t"))
        self.mc_of[req.seq] = mc.id
        return mc.done()

    def _inputs(self, req: Event) -> tuple[list[str], dict[str, int]]:
        """The request's messages matched to recorded messages: user texts by equality, assistant calls and function
        results by call id; system and memory messages and withheld copies are counted, never matched."""
        out: list[str] = []
        unmatched: Counter[str] = Counter()
        for item in req.value.get("messages") or []:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("type"))
            raw: dict[str, Any] = item["raw"] if isinstance(item.get("raw"), dict) else {}
            ids: list[str] = []
            if kind == "UserMessage" and isinstance(item.get("text"), str) and item["text"] in self.text_of:
                ids = [self.text_of[item["text"]]]
            elif kind == "AssistantMessage" and isinstance(raw.get("content"), list):
                ids = list(dict.fromkeys(self.request_msg[str(c.get("id"))] for c in raw["content"]
                                         if isinstance(c, dict) and str(c.get("id")) in self.request_msg))
            elif kind == "FunctionExecutionResultMessage" and isinstance(raw.get("content"), list):
                ids = [self.result_msg[str(c.get("call_id"))] for c in raw["content"]
                       if isinstance(c, dict) and str(c.get("call_id")) in self.result_msg]
            if ids:
                out.extend(x for x in ids if x not in out)
            else:
                unmatched[kind] += 1
        return out, dict(sorted(unmatched.items()))

    def _executions(self, i: int, m: Mapping[str, Any], agent: str, entered: Counter[tuple[str, str]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        content = m["raw"].get("content")
        if not isinstance(content, list):
            raise MalformedArtefact("a ToolCallExecutionEvent has no list content")
        for k, item in enumerate(content):
            if not isinstance(item, dict):
                raise MalformedArtefact("a FunctionExecutionResult is not an object")
            cid, name = str(item.get("call_id")), str(item.get("name"))
            call = self.call_part.get(cid)
            te = _Rec(k="tool_execution", id=self.next_id("te"), actor="env", scope="att0", ev="O")
            te.cite(self.R(R_EXEC))
            te.set("name", name)
            te.loc(self.row_loc("messages", i, "raw", "content", k))
            if call is not None:
                te.data["call"] = call
                te.tag("/call", self.cls(R_CALL_LINK), self.R(R_CALL_LINK, "/call"))
                te.edge(call.split("#", 1)[0], "causal")
                te.tag("/after", self.cls(R_CALL_LINK), self.R(R_AFTER_CALL, "/after"))
                args = self._call_args(call)
                if args is not None:
                    te.data["args"] = te.enc(args, "/args")
                    te.tag("/args", self.cls(R_ARGS), self.R(R_ARGS, "/args"))
            else:
                te.unk["/call"] = "ambiguous"
                te.cite(self.R(R_CALL_LINK, "/call"))
                self.issue("orphan_tool_result", [te.id], R_CALL_LINK)
            if item.get("is_error") is False:
                te.data["status"] = "ok"
                te.tag("/status", self.cls(R_EXEC), self.R(R_EXEC, "/status"))
                self.executed[(agent, name)] += 1
            elif entered[(agent, name)] <= 0:
                te.data["status"] = "invalid"
                te.tag("/status", "I", self.R(R_NOT_ENTERED, "/status"))
                self.issue("autogen.tool_error_result", [te.id], R_NOT_ENTERED, severity="info", detail="not_entered")
            else:
                te.unk["/status"] = "ambiguous"
                te.cite(self.R(R_EXEC, "/status"))
                entered[(agent, name)] -= 1
                self.issue("autogen.tool_error_result", [te.id], R_EXEC, severity="info", detail="entered")
            te.unk.update({"/returned": "not_recorded", "/t": "not_recorded"})
            out.append(te.done())
            if call is not None:
                self.te_by_call[cid] = te.id
            generator, gen_rule, actor = te.id, R_CALL_LINK, "env"
            result = item.get("content")
            row = self._tool_block_for(agent, name, result)
            if row is not None:
                dc = self._decision(row, subject=te.id, subject_rule=R_TOOL_BLOCK)
                out.append(dc)
                generator, gen_rule, actor = dc["id"], R_BLOCK, dc["actor"]
            mid = self.next_id("m")
            msg = _Rec(k="message", id=mid, scope="att0", role="tool", actor=actor, generated_by=generator, ev="O")
            msg.loc(self.row_loc("messages", i, "raw", "content", k))
            part: dict[str, Any] = {"t": "tool_result"}
            if call is not None:
                part["responds_to"] = call
                msg.tag(_p("parts", 0, "responds_to"), self.cls(R_CALL_LINK), self.R(R_CALL_LINK, _p("parts", 0, "responds_to")))
            else:
                msg.unk[_p("parts", 0, "responds_to")] = "ambiguous"
                msg.cite(self.R(R_CALL_LINK, _p("parts", 0, "responds_to")))
            part["text"] = msg.enc(result, _p("parts", 0, "text")) if isinstance(result, str) else None
            part["name"] = msg.enc(name, _p("parts", 0, "name"))
            msg.data["parts"] = [part]
            msg.tag("/actor", self.cls(gen_rule), self.R(gen_rule, "/actor"))
            msg.tag("/generated_by", self.cls(gen_rule), self.R(gen_rule, "/generated_by"))
            msg.edge(generator, "causal")
            msg.tag("/after", self.cls(gen_rule), self.R(R_GEN, "/after"))
            raw = m["raw"]
            msg.x("message", {"type": m.get("type"), "id": raw.get("id"), "created_at": raw.get("created_at"), "item": k,
                              "is_error": item.get("is_error")})
            if self.prev is not None and self.prev != generator:
                msg.edge(self.prev, "pos")
                msg.tag("/after", "I", self.R(R_ORDER, "/after"))
            self.result_msg[cid] = mid
            out.append(self._finish_message(msg, result))
        if len(content) > 1:
            self.note_digest(m.get("text"), "run")  # a joined multi-result text names no single record
        return out

    def _call_args(self, call: str) -> Any:
        return self._parts_args.get(call)

    def _memory(self, i: int, m: Mapping[str, Any]) -> list[dict[str, Any]]:
        ac = _Rec(k="activity", id=self.next_id("ac"), type="autogen:memory_query", actor="harness", scope="att0", ev="O")
        ac.data["inputs"] = []
        ac.tag("/inputs", "I", self.R(R_MEMORY, "/inputs"))
        ac.tag("/actor", "I", self.R(R_MEMORY, "/actor"))
        ac.loc(self.row_loc("messages", i))
        ac.unk["/t"] = "not_recorded"
        raw = m["raw"]
        ac.x("message", {"type": m.get("type"), "id": raw.get("id"), "created_at": raw.get("created_at"),
                         "source": m.get("source")})
        if self.prev is not None:
            ac.edge(self.prev, "pos")
            ac.tag("/after", "I", self.R(R_ORDER, "/after"))
        af = _Rec(k="artefact", id=self.next_id("af"), type="autogen:memory_content", generated_by=ac.id, ev="O")
        af.set("content", raw.get("content"))
        af.loc(self.row_loc("messages", i, "raw", "content"))
        af.tag("/generated_by", "I", self.R(R_MEMORY, "/generated_by"))
        self.note_digest(m.get("text"), af.id)
        self.prev = ac.id
        return [ac.done(), af.done()]

    # ---------------------------------------------------------------------------------------------- guards
    def _block_rows(self) -> list[Event]:
        """Guard rows whose verdict changed a text: the block guard flagged it at a placement in block mode, and (on the
        bus) the scanned message was delivered (the output-stream copy is never redacted; harness code)."""
        out = []
        for e in self.ev.of("guard"):
            v = e.value
            placement = str(v.get("placement"))
            if v.get("flag") is True and self.modes.get(placement) == "block" and v.get("delivered") is not False:
                out.append(e)
        return out

    def _task_block_rows(self) -> list[Event]:
        return [e for e in self._block_rows() if e.value.get("placement") == "bus"
                and str(e.value.get("msg_kind", "")).startswith("GroupChatStart")]

    def _tool_block_rows(self) -> dict[str, list[Event]]:
        out: dict[str, list[Event]] = {}
        for e in self._block_rows():
            if e.value.get("placement") == "tool":
                out.setdefault(str(e.value.get("agent")), []).append(e)
        return out

    def task_decisions_pending(self) -> bool:
        """A block-guard flag on the start message at a bus in block mode (the fixture is built before the stream)."""
        return bool(self._task_block_rows())

    def _tool_block_for(self, agent: str, name: str, result: object) -> Event | None:
        """The agent's next flagged tool-placement scan of this tool, when the delivered result differs from the text it
        scanned (by digest): the guard replaced it (withheld) or changed it (keyword stripped). One to one, in order
        (``autogen.tool_block_link_unverified@1``)."""
        queue = self.tool_blocks.get(agent) or []
        if not queue or str(queue[0].value.get("msg_kind")) != name:
            return None
        if isinstance(result, str) and sha16(result) == queue[0].value.get("text_sha"):
            return None
        return queue.pop(0)

    def _decision(self, e: Event, *, subject: str, subject_rule: str = R_GUARD_DIGEST) -> dict[str, Any]:
        guard = self.block_guard or "unknown"
        dc = _Rec(k="decision", id=self.next_id("dc"), actor=f"guard_{guard}", scope="att0", subject=subject,
                  verdict="modify", ev="I")
        dc.cite(self.R(R_BLOCK))
        dc.tag("/subject", self.cls(subject_rule), self.R(subject_rule, "/subject"))
        dc.loc(self.ev_loc(e))
        if subject != "run":
            dc.edge(subject, "causal")
            dc.tag("/after", "I", self.R(R_AFTER_SUBJECT, "/after"))
        dc.unk.update({"/original": "overwritten", "/reason": "not_recorded", "/t": "not_recorded"})
        dc.x("guard_row", {"placement": e.value.get("placement"), "msg_kind": e.value.get("msg_kind"),
                           "text_sha": e.value.get("text_sha"), "seq": e.seq})
        self.decided.add(e.line)
        return dc.done()

    def _candidates(self, row: Mapping[str, Any]) -> list[str]:
        sha = row.get("text_sha")
        ids = self.digest_ids.get(str(sha), []) if isinstance(sha, str) else []
        return [] if "run" in ids else list(ids)

    def _subject_of(self, row: Mapping[str, Any]) -> str | None:
        """The one record whose recorded text has the row's digest (``autogen.guard_text_digest@1``): a message before a
        fixture or artefact with the same text; on the bus, among equal messages, the one the row's agent sent (a bus
        row names the sender). Several remaining candidates leave the subject ambiguous."""
        real = self._candidates(row)
        if len(real) == 1:
            return real[0]
        msgs = [i for i in real if i.startswith("m")]
        if len(msgs) > 1 and row.get("placement") == "bus" and isinstance(row.get("agent"), str):
            msgs = [i for i in msgs if self.actor_of.get(i) == row["agent"]]
        return msgs[0] if len(msgs) == 1 else None

    def _late_decisions(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for e in self._block_rows():
            if e.line in self.decided:
                continue
            subject = self._subject_of(e.value)
            placement = str(e.value.get("placement"))
            if subject is None or not subject.startswith(("m", "te", "mc")):
                # C.3.7: a decision is about a message, a call part, an execution or a model call; a blocked system
                # prompt, memory content or unjoined text is disclosed instead (the guard's judgement stays)
                self.issue("autogen.block_subject_not_recorded", ["run"], R_NO_DECISION, severity="info", detail=placement)
                continue
            out.append(self._decision(e, subject=subject))
            self.issue("autogen.block_effect_in_request_log", [out[-1]["id"]], R_BLOCK, severity="info", detail=placement)
        return out

    def _judgements(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        unjoined = 0
        for e in self.ev.of("guard"):
            v = e.value
            flags: dict[str, Any] = v["flags"] if isinstance(v.get("flags"), dict) else {}
            subject = self._subject_of(v)
            candidates = len(self._candidates(v))
            if subject is None:
                unjoined += 1
            for g in sorted(flags):
                j = _Rec(k="judgement", id=self.next_id("j"), actor=f"guard_{g}", subject=subject or "run",
                         name="injection_flag", ev="O", by="source")
                j.set("value", flags[g])
                j.loc(self.ev_loc(e, "flags", g))
                j.data["origin"] = "checker"
                j.tag("/origin", "I", self.R(R_GUARD, "/origin"))
                if subject is not None:
                    j.tag("/subject", "D", self.R(R_GUARD_DIGEST, "/subject"))
                else:
                    j.unk["/subject"] = "ambiguous"
                    j.cite(self.R(R_GUARD_DIGEST, "/subject"))
                detail = self.guard_raw.get((g, str(v.get("text_sha"))))
                info: dict[str, Any] = {k: v.get(k) for k in ("placement", "msg_kind", "agent", "delivered", "text_sha",
                                                              "chars", "contains_passage", "contains_canary", "seq", "t")
                                        if k in v}
                if detail is not None:
                    line, row = detail
                    info["verdict"] = {k: row.get(k) for k in ("label", "score", "raw", "latency_s", "tokens", "truncated",
                                                               "parse_ok") if k in row}
                    j.loc({"a": self.aid["guard_raw"], "line": line})
                    j.tag("/ext/autogen/guard/verdict", "D", self.R(R_GUARD_RAW, "/ext/autogen/guard/verdict"))
                if subject is None:
                    info["candidates"] = candidates
                j.x("guard", info)
                j.unk.update({"/inputs": "not_recorded", "/t": "ambiguous"})
                j.cite(self.R(R_TIMES, "/t"))
                out.append(j.done())
        if unjoined:
            self.issue("autogen.guard_text_unjoined", ["run"], R_GUARD_DIGEST, severity="info", detail=str(unjoined))
        return out

    # ---------------------------------------------------------------------------------------------- checks
    def _checks(self) -> None:
        side = self.v.get("tool_calls")
        if not isinstance(side, list):
            self.ctx.check(R_SIDE_LIST, scope="att0", verdict="unverifiable", observed={}, reason="side_list_absent")
            return
        listed = Counter((str(c.get("agent")), str(c.get("tool"))) for c in side if isinstance(c, dict))
        attacker = {str(t) for t in ((self.probe or {}).get("attacker_tools") or [])}
        expected = Counter({k: n for k, n in self.executed.items() if k[1] == "save_note" or k[1] in attacker})
        ok = listed == expected
        self.ctx.check(R_SIDE_LIST, scope="att0", verdict="consistent" if ok else "inconsistent",
                       observed={"listed": sum(listed.values()), "recorded": sum(expected.values())},
                       reason=None if ok else "side_list_differs")
