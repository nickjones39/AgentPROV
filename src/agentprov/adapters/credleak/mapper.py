"""Mapper ``credleak.cell``: one run of a credential-leak cell -> AER ``aer/0.1`` (docs/architecture D.19.3-D.19.7;
DECISIONS D-260..D-264).

One run (``runs[<i>]`` of a cell) is one execution; its source key is the cell's digest plus the locator
``{"p": "/runs/<i>"}`` (HL H.7.1). What the mapper writes, in record order (backward references only, C.5.2):

1. the header: task coordinates from the cell (``technique``, ``scenario``, ``defence``; O), ``ext.credleak`` (path
   facets, the run's index and repetition, the cell's ``runId``, ``timestamp``, ``config``, ``summary`` and ``__note``,
   the run's duration and its other fields verbatim);
2. actors ``bench``, ``harness``, ``user``, ``agent`` (``model.requested`` = the run's ``model`` verbatim, O), ``env``
   (when a tool was called), ``att`` (the scenario's injection) and ``det`` (the harness's detectors);
3. scopes ``run`` (status from ``invocationError``), ``att0`` and one ``agent_invocation`` scope per turn (``inv<k>``),
   whose time is declared ambiguous: the turn timestamp is kept verbatim in ``ext.credleak`` (D-263);
4. per turn: the user message; per ``toolCalls[]`` entry an agent message with one ``tool_call`` part, the tool
   execution (I) and the tool result, linked to its call **by co-location in the same entry** (D,
   ``credleak.pair_same_entry@1``); then the turn's assistant text, ordered after the user message only (its position
   relative to the calls is not recorded);
5. the detector signals as ``judgement`` records (values O, origin ``checker`` I).

Nothing is invented (D-261..D-263): no model call (boundaries are not recorded; agent messages declare
``generated_by`` not recorded with the core issue ``missing_generated_by``), no typed time, no tool status, no call id,
no served model, no harness name. Content is copied verbatim, with one exception: third-party account paths in tool
output are replaced by salted labels as the profile's ``[[family.credleak.redact]]`` rules specify (D-605, applying
D-604; :mod:`~agentprov.adapters.credleak.redact`). The planted credentials some runs hold are withheld at sealing by
the profile's ``[withhold]`` policy (D-235, D-265), never by this module; so is model-authored text, which is never
redacted, wherever that policy names what it holds.

Pure (A-2): the output is a function of the unit's bytes, this code, the profile and the catalogues.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from typing import Any, Final

from agentprov.adapters.credleak import ADAPTER_ID, DIALECT_ID, VARIANT
from agentprov.adapters.credleak.dialect import PathFacets, parse_path
from agentprov.adapters.credleak.redact import ISSUE as REDACTED_ISSUE
from agentprov.adapters.credleak.redact import RULE as R_REDACTED
from agentprov.adapters.credleak.redact import Redactor, parse_redact_rules
from agentprov.adapters.protocols import AerRecord, MappingContext
from agentprov.adapters.types import ArtefactRef, ExecutionUnit
from agentprov.aer.canon import LexHints, encode_value, json_pointer
from agentprov.aer.ids import part_id
from agentprov.errors import MalformedArtefact

__all__ = ["ADAPTER_ID", "ADAPTER_VERSION", "BENCHMARK", "CATALOGUES", "JUDGED", "NAMESPACES", "CredleakMapper"]

ADAPTER_VERSION: Final = "0.1.0"
#: Catalogues this mapper cites; the header lists them at the shipped versions (C.3.1 ``rules``).
CATALOGUES: Final = ("aer", "credleak")
NAMESPACES: Final = {"credleak": "https://w3id.org/agentprov/ns/credleak#"}
BENCHMARK: Final = "credleak-p15b"
#: Run-level detector fields written as judgements, in this order (D-264). Every other run field except the structural
#: ones goes verbatim to ``ext.credleak.run_fields``.
JUDGED: Final = (
    "hijackSucceeded", "exfiltrationDetected", "exfiltrationCount", "egressChannel", "agentDetected", "displayedToUser",
    "maliciousArtifactEmitted", "scriptAudited", "payloadDelivered", "taskEngaged", "t0Completed", "truncated", "ges",
    "gesDisplayed", "gesExfil",
)  # fmt: skip
_STRUCTURAL: Final = frozenset({"turns", "model", "scenarioId", "scenarioName", "repetition", "durationMs"})
#: Typed strings the validator treats as placeholders (C.7.3): never written into a typed tool name unflagged.
#: Placeholder values a typed field never holds (C.7.3): the validator's list (aer.validate) and this family's extras
#: (regen item 34, bug pass BF-23: "0" and "-" were missing, so such a name turned the run into an adapter_defect).
_SENTINELS: Final = frozenset({"", "0", "unknown", "none", "null", "n/a", "na", "-", "undefined", "nan"})

# rule ids (catalogue credleak, version 2; R_REDACTED, credleak.value_redacted@1, is D-605's)
R_FIELDS: Final = "credleak.cell_field_roles@1"
R_MODEL: Final = "credleak.model_label_is_requested@1"
R_USER: Final = "credleak.user_is_scripted_unverified@1"
R_ATTACK: Final = "credleak.scenario_is_injection_unverified@1"
R_CALL_OUT: Final = "credleak.call_entry_is_model_output_unverified@1"
R_RESPONSE: Final = "credleak.response_is_model_output_unverified@1"
R_TOOL_EXEC: Final = "credleak.tool_entry_is_execution_unverified@1"
R_AUTO: Final = "credleak.auto_execution_unverified@1"
R_PAIR: Final = "credleak.pair_same_entry@1"
R_CALL_ORDER: Final = "credleak.calls_in_entry_order_unverified@1"
R_TURN_ORDER: Final = "credleak.turns_in_array_order_unverified@1"
R_RESPONSE_AFTER: Final = "credleak.response_after_user_message_unverified@1"
R_TURN_TIME: Final = "credleak.turn_timestamp_role@1"
R_DURATION: Final = "credleak.duration_no_clock@1"
R_NO_GENERATOR: Final = "credleak.model_calls_not_recorded@1"
R_DETECTOR: Final = "credleak.detector_signal_unverified@1"
R_ERROR: Final = "credleak.invocation_error_status@1"
R_TURN_INDEX: Final = "credleak.turn_number_index@1"
R_COUNT: Final = "credleak.acc.tool_call_count@1"
R_CELL: Final = "credleak.cell_run_agreement@1"
R_PATH: Final = "credleak.path_facets@1"
R_GEN: Final = "aer.output_after_generator@1"
R_AFTER_CALL: Final = "aer.execution_after_call@1"


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
        """``ext.credleak.<key>`` (encoded)."""
        self.ext[key] = self.enc(value, _p("ext", "credleak", key))

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
            ext["credleak"] = dict(self.ext)
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


def _origin_key(artefact: ArtefactRef) -> str | None:
    data = artefact.origin.data
    for key in ("label", "path"):
        if isinstance(data.get(key), str):
            return key
    return None


def _facets(artefact: ArtefactRef) -> PathFacets | None:
    key = _origin_key(artefact)
    return parse_path(str(artefact.origin.data[key])) if key is not None else None


def _str_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _task(cell: Mapping[str, Any]) -> dict[str, Any]:
    scenario = _str_or_none(cell.get("scenario"))
    if scenario is None:
        raise MalformedArtefact("the cell has no scenario string: no task can be named")
    task: dict[str, Any] = {"benchmark": BENCHMARK, "task_id": scenario, "attack_id": scenario,
                            "defense_id": _str_or_none(cell.get("defence"))}
    technique = _str_or_none(cell.get("technique"))
    if technique is not None:
        task["suite"] = technique
    return task


class CredleakMapper:
    """``Mapper`` for ``credleak.cell`` (D.2.4, D.19)."""

    mapper_id: Final = ADAPTER_ID
    version: Final = ADAPTER_VERSION
    accepts: Final = frozenset({(DIALECT_ID, VARIANT)})
    namespaces: Final = NAMESPACES
    catalogues: Final = CATALOGUES

    def map(self, unit: ExecutionUnit, ctx: MappingContext) -> Iterator[AerRecord]:
        yield from _Build(unit, ctx).run()

    @staticmethod
    def prov_primary(flags: frozenset[str]) -> str:
        """Cells are written by the study's harness: ``native``."""
        return "native"

    def degenerate_header(self, unit: ExecutionUnit, ctx: MappingContext, *, issue_code: str, detail: str) -> dict[str, Any]:
        """The header of a degenerate AER (D.2.8 case 3): the task from the cell when it parses, else from the path."""
        value = unit.primary.value
        if isinstance(value, dict) and isinstance(value.get("scenario"), str):
            task = _task(value)
        else:
            facets = _facets(unit.primary.artefact)
            if facets is None:
                raise MalformedArtefact("neither the cell nor its path names a scenario: no task can be named")
            task = {"benchmark": BENCHMARK, "task_id": facets.channel, "attack_id": None, "defense_id": None}
        header = _header_base(unit, ctx, task, [unit.primary.artefact.to_json()], cell_fields=False)
        ctx.issue(issue_code, ids=["exec"], rule=ctx.rule(R_FIELDS), severity="error", detail=detail)
        return header


def _header_base(unit: ExecutionUnit, ctx: MappingContext, task: dict[str, Any], artifacts: list[dict[str, Any]], *,
                 cell_fields: bool) -> dict[str, Any]:
    src: list[dict[str, Any]] = []
    if cell_fields:
        src += [{"a": "a0", "p": "/scenario"}, {"a": "a0", "p": "/technique"}, {"a": "a0", "p": "/defence"}]
    key = _origin_key(unit.primary.artefact)
    if key is not None:
        src.append({"a": "a0", "o": f"/{key}"})
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
        "dialect": {"id": DIALECT_ID, "variant": VARIANT},
        "profile": ctx.profile.header(),
        "rules": ctx.catalogue_versions(CATALOGUES),
        "ns": dict(NAMESPACES),
        "canon": "jcs-rfc8785",
        "hash": "sha256",
        "task": task,
        "ev": "O",
        "by": "source",
        "src": src,
        "unk": {"/instrumentation": "not_recorded"},
    }
    if task.get("defense_id") is None:
        header["unk"]["/task/defense_id"] = "not_recorded"
        del task["defense_id"]
    return header


class _Build:
    """One mapping run: every record is built in order, then emitted (backward references only)."""

    def __init__(self, unit: ExecutionUnit, ctx: MappingContext) -> None:
        self.unit, self.ctx = unit, ctx
        item = unit.primary
        pointer = item.locator.p
        if not isinstance(item.value, dict) or not isinstance(pointer, str) or not pointer.startswith("/runs/"):
            raise MalformedArtefact("the located item is not a run of a credential-leak cell")
        runs = item.value.get("runs")
        try:
            index = int(pointer[len("/runs/"):])
        except ValueError:
            raise MalformedArtefact("the run locator is not /runs/<i>") from None
        if not isinstance(runs, list) or not 0 <= index < len(runs) or pointer != f"/runs/{index}":
            raise MalformedArtefact("the run locator does not name a run of the cell")
        self.cell: dict[str, Any] = item.value
        self.index = index
        self.P = pointer
        run = runs[index]
        if not isinstance(run, dict) or not isinstance(run.get("turns"), list):
            raise MalformedArtefact("the run is not an object with a turns array")
        for turn in run["turns"]:
            if not isinstance(turn, dict) or not isinstance(turn.get("toolCalls", []), list):
                raise MalformedArtefact("a turn is not an object with a toolCalls array")
            if not all(isinstance(tc, dict) for tc in turn.get("toolCalls", [])):
                raise MalformedArtefact("a tool call is not an object")
        self.run_v: dict[str, Any] = run
        self.turns: list[dict[str, Any]] = run["turns"]
        self.facets = _facets(item.artefact)
        self.origin_key = _origin_key(item.artefact)
        self.counters: dict[str, int] = {}
        self.agent_messages: list[str] = []
        self.n_calls = sum(len(t.get("toolCalls", [])) for t in self.turns)
        rules = parse_redact_rules(ctx.profile.family_table().get("redact", ()), f"profile {ctx.profile.id!r}")
        self.redactor = Redactor(ctx.profile.id, ctx.profile.version, rules)
        self.n_redacted = 0

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
        return {"a": "a0", "p": self.P + _p(*tokens)}

    # ---------------------------------------------------------------------------------------------- run
    def run(self) -> Iterator[dict[str, Any]]:
        body: list[dict[str, Any]] = []
        judged = [k for k in JUDGED if k in self.run_v]
        body += self._actors(bool(judged))
        body += self._scopes()
        body += self._turns()
        body += self._judgements(judged)
        self._checks()
        if self.n_redacted:
            self.issue(REDACTED_ISSUE, ["exec"], R_REDACTED, severity="info", detail=str(self.n_redacted))
        yield self._header()
        yield from body

    # ---------------------------------------------------------------------------------------------- header
    def _header(self) -> dict[str, Any]:
        header = _header_base(self.unit, self.ctx, _task(self.cell), [self.unit.primary.artefact.to_json()],
                              cell_fields=True)
        ext: dict[str, Any] = {"run_index": self.index}
        if self.facets is not None:
            ext["path_facets"] = self.facets.to_json()
        else:
            self.issue("credleak.path_outside_grammar", ["exec"], R_PATH, severity="info")
        for key, name in (("repetition", "repetition"), ("scenarioName", "scenario_name"), ("durationMs", "run_duration_ms")):
            if key in self.run_v:
                ext[name] = self.run_v[key]
        for key, name in (("runId", "cell_run_id"), ("timestamp", "cell_timestamp"), ("config", "config"),
                          ("summary", "cell_summary"), ("__note", "cell_note")):
            if key in self.cell:
                ext[name] = self.cell[key]
        rest = {k: v for k, v in self.run_v.items() if k not in _STRUCTURAL and k not in JUDGED}
        if rest:
            ext["run_fields"] = rest
        lex = LexHints()
        header["ext"] = {"credleak": encode_value(ext, at="/ext/credleak", lex=lex)}
        hints = lex.as_dict()
        if hints:
            header["ext"]["lex"] = hints
        header["src"].insert(0, {"a": "a0", "p": self.P})
        return header

    # ---------------------------------------------------------------------------------------------- actors and scopes
    def _origin_src(self) -> list[dict[str, Any]]:
        return [{"a": "a0", "o": f"/{self.origin_key}"}] if self.origin_key is not None else []

    def _actors(self, has_judgements: bool) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        bench = _Rec(k="actor", id="bench", kind="benchmark", name=BENCHMARK, ev="O")
        for entry in self._origin_src():
            bench.loc(entry)
        bench.unk.update({"/code": "not_recorded", "/version": "not_recorded"})
        out.append(bench.done())
        harness = _Rec(k="actor", id="harness", kind="harness", ev="O")
        harness.loc({"a": "a0", "p": "/config"})
        harness.unk.update({"/name": "not_recorded", "/code": "not_recorded", "/version": "not_recorded"})
        out.append(harness.done())
        user = _Rec(k="actor", id="user", kind="simulated_user", ev="I")
        user.cite(self.R(R_USER))
        out.append(user.done())
        model = self.run_v.get("model")
        agent = _Rec(k="actor", id="agent", kind="llm_agent", ev="O")
        if isinstance(model, str) and model.lower() not in _SENTINELS:
            agent.data["model"] = {"requested": agent.enc(model, "/model/requested")}
            agent.cite(self.R(R_MODEL))  # the value is O; the rule states its reading (requested), unscoped (AER-V14)
            agent.loc(self.loc("model"))
            agent.loc({"a": "a0", "p": "/model"})
            agent.unk.update({"/model/provider": "not_recorded", "/model/served": "not_recorded"})
        else:  # no usable model: the actor is still observed in the run (AER-V13 needs a locator; regen item 35, BF-24)
            agent.unk["/model"] = "not_recorded"
            agent.loc({"a": "a0", "p": self.P})
        agent.unk["/params"] = "not_recorded"
        agent.data["on_behalf_of"] = "user"
        agent.tag("/on_behalf_of", "I", self.R(R_USER, "/on_behalf_of"))
        out.append(agent.done())
        if self.n_calls:
            env = _Rec(k="actor", id="env", kind="tool_runtime", on_behalf_of="agent", ev="I")
            env.cite(self.R(R_TOOL_EXEC))
            env.cite(self.R(R_AUTO, "/on_behalf_of"))
            out.append(env.done())
        att = _Rec(k="actor", id="att", kind="attacker", ev="I")
        technique = _str_or_none(self.cell.get("technique"))
        if technique is not None:
            att.set("name", technique)
        att.loc({"a": "a0", "p": "/technique"})
        att.cite(self.R(R_ATTACK))
        out.append(att.done())
        if has_judgements:
            det = _Rec(k="actor", id="det", kind="judge", role="detector", ev="I")
            det.cite(self.R(R_DETECTOR))
            det.unk.update({"/name": "not_recorded", "/code": "not_recorded", "/version": "not_recorded"})
            out.append(det.done())
        return out

    def _scopes(self) -> list[dict[str, Any]]:
        run = _Rec(k="scope", id="run", kind="run", ev="O")
        run.loc(self.loc())
        if self.run_v.get("invocationError") is True:
            run.data["status"] = "error"
            run.tag("/status", "I", self.R(R_ERROR, "/status"))
            run.loc(self.loc("invocationError"))
            if isinstance(self.run_v.get("errorDetail"), str):
                run.loc(self.loc("errorDetail"))
            self.issue("credleak.invocation_error", ["run"], R_ERROR, severity="info")
        else:
            run.unk["/status"] = "not_recorded"
        self._duration(run, self.run_v)
        att = _Rec(k="scope", id="att0", kind="attempt", parent="run", actor="agent", ev="O")
        att.loc(self.loc("turns"))
        att.unk.update({"/index": "not_recorded", "/scored": "not_recorded"})
        return [run.done(), att.done()]

    def _duration(self, rec: _Rec, source: Mapping[str, Any]) -> None:
        duration = source.get("durationMs")
        if duration is None:
            rec.unk["/t"] = "not_recorded"
            return
        rec.x("duration_ms", duration)
        rec.unk.update({"/t/dur_s": "ambiguous", "/t/start": "not_recorded", "/t/end": "not_recorded"})
        rec.cite(self.R(R_DURATION, "/t/dur_s"))

    # ---------------------------------------------------------------------------------------------- turns
    def _turns(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        previous: list[str] = []  # the records of the previous turn that end it (its last result and its response)
        for k, turn in enumerate(self.turns):
            records, previous = self._turn(k, turn, previous)
            out += records
        if self.agent_messages:
            self.issue("missing_generated_by", self.agent_messages, R_NO_GENERATOR, severity="info")
        return out

    def _turn(self, k: int, turn: Mapping[str, Any], previous: Sequence[str]) -> tuple[list[dict[str, Any]], list[str]]:
        out: list[dict[str, Any]] = []
        sid = f"inv{k}"
        scope = _Rec(k="scope", id=sid, kind="agent_invocation", parent="att0", actor="agent", ev="O")
        scope.loc(self.loc("turns", k))
        number = turn.get("turnNumber")
        if isinstance(number, int) and not isinstance(number, bool) and number == k:
            scope.data["index"] = k
            scope.tag("/index", "D", self.R(R_TURN_INDEX, "/index"))
        else:
            scope.unk["/index"] = "ambiguous"
            scope.cite(self.R(R_TURN_INDEX, "/index"))
            self.issue("credleak.turn_number_mismatch", [sid], R_TURN_INDEX, severity="info")
        scope.unk["/t"] = "ambiguous"
        scope.cite(self.R(R_TURN_TIME, "/t"))
        if "timestamp" in turn:
            scope.x("timestamp", turn["timestamp"])
        if "durationMs" in turn:
            scope.x("duration_ms", turn["durationMs"])
        if "canaryDetected" in turn:
            scope.x("canary_detected", turn["canaryDetected"])
        found = turn.get("canariesFound")
        if isinstance(found, list):
            scope.x("canaries_found_count", len(found))  # D-264: the count only; the labels embed the tag
        out.append(scope.done())

        user = _Rec(k="message", id=self.next_id("m"), scope=sid, role="user", actor="user", ev="O")
        self._content(user, turn.get("userMessage"), "userMessage")
        user.loc(self.loc("turns", k, "userMessage"))
        user.tag("/role", "D", self.R(R_FIELDS, "/role"))
        user.tag("/actor", "I", self.R(R_USER, "/actor"))
        for target in previous:
            user.edge(target, "pos")
        if previous:
            user.tag("/after", "I", self.R(R_TURN_ORDER, "/after"))
        out.append(user.done())

        last = user.id
        for j, entry in enumerate(turn.get("toolCalls", [])):
            records, last = self._call(k, j, sid, entry, last)
            out += records

        response = _Rec(k="message", id=self.next_id("m"), scope=sid, role="assistant", actor="agent", ev="O")
        self._content(response, turn.get("assistantResponse"), "assistantResponse")
        response.loc(self.loc("turns", k, "assistantResponse"))
        response.tag("/role", "D", self.R(R_FIELDS, "/role"))
        response.tag("/actor", "I", self.R(R_RESPONSE, "/actor"))
        response.unk["/generated_by"] = "not_recorded"
        response.cite(self.R(R_NO_GENERATOR, "/generated_by"))
        response.edge(user.id, "pos")
        response.tag("/after", "I", self.R(R_RESPONSE_AFTER, "/after"))
        self.agent_messages.append(response.id)
        out.append(response.done())
        ends = [last, response.id] if last != user.id else [response.id]
        return out, ends

    def _content(self, rec: _Rec, value: object, field: str) -> None:
        if value == "" and field == "assistantResponse":
            rec.data["parts"] = []  # known empty (C.3.4); an empty assistant text part would read as a null placeholder
        elif isinstance(value, str):
            rec.data["parts"] = [{"t": "text", "text": rec.enc(value, "/parts/0/text")}]
        elif value is None and field == "assistantResponse":
            rec.data["parts"] = [{"t": "text", "text": None}]
        else:
            rec.data["parts"] = [{"t": "other", "type": f"credleak.{field}", "value": rec.enc(value, "/parts/0/value")}]

    def _call(self, k: int, j: int, sid: str, entry: Mapping[str, Any], prev: str) -> tuple[list[dict[str, Any]], str]:
        name = entry.get("tool")
        typed_name = isinstance(name, str) and name.lower() not in _SENTINELS
        call = _Rec(k="message", id=self.next_id("m"), scope=sid, role="assistant", actor="agent", ev="O")
        part: dict[str, Any] = {"t": "tool_call", "name": call.enc(name if isinstance(name, str) else str(name),
                                                                    "/parts/0/name")}
        part["args"] = call.enc(entry.get("input"), "/parts/0/args")
        if "input" not in entry:
            call.unk["/parts/0/args"] = "not_recorded"
        if not typed_name:
            call.unk["/parts/0/name"] = "ambiguous"
            call.cite(self.R(R_CALL_OUT, "/parts/0/name"))
        call.data["parts"] = [part]
        call.loc(self.loc("turns", k, "toolCalls", j))
        call.tag("/role", "I", self.R(R_CALL_OUT, "/role"))
        call.tag("/actor", "I", self.R(R_CALL_OUT, "/actor"))
        call.unk["/generated_by"] = "not_recorded"
        call.cite(self.R(R_NO_GENERATOR, "/generated_by"))
        call.edge(prev, "pos")
        call.tag("/after", "I", self.R(R_CALL_ORDER, "/after"))
        self.agent_messages.append(call.id)
        call_part = part_id(call.id, 0)

        te = _Rec(k="tool_execution", id=self.next_id("te"), actor="env", scope=sid, ev="I")
        te.cite(self.R(R_TOOL_EXEC))
        te.data["call"] = call_part
        te.tag("/call", "D", self.R(R_PAIR, "/call"))
        te.set("name", name if isinstance(name, str) else str(name))
        if typed_name:
            te.evf["/name"] = "O"
        else:
            te.unk["/name"] = "ambiguous"
            te.cite(self.R(R_PAIR, "/name"))
        if "input" in entry:
            te.set("args", entry["input"])
            te.evf["/args"] = "O"
        else:
            te.unk["/args"] = "not_recorded"
        te.loc(self.loc("turns", k, "toolCalls", j))
        te.unk.update({"/returned": "not_recorded", "/status": "not_recorded"})
        self._duration(te, entry)
        for key, ext in (("canaryInInput", "canary_in_input"), ("canaryInOutput", "canary_in_output")):
            if key in entry:
                te.x(ext, entry[key])
        te.edge(call.id, "causal")
        te.tag("/after", "I", self.R(R_AFTER_CALL, "/after"))

        result = _Rec(k="message", id=self.next_id("m"), scope=sid, role="tool", actor="env", generated_by=te.id, ev="O")
        rpart: dict[str, Any] = {"t": "tool_result", "responds_to": call_part}
        output = entry.get("output")
        at = "/parts/0/text" if isinstance(output, str) else "/parts/0/value"
        output, redacted = self.redactor.tool_output(output, at)  # D-605: before encoding, so every copy is redacted
        rpart[at.rsplit("/", 1)[1]] = result.enc(output, at)
        if "output" not in entry:
            result.unk["/parts/0/value"] = "not_recorded"
        if typed_name:
            rpart["name"] = result.enc(name, "/parts/0/name")
        result.data["parts"] = [rpart]
        result.tag("/parts/0/responds_to", "D", self.R(R_PAIR, "/parts/0/responds_to"))
        result.loc(self.loc("turns", k, "toolCalls", j, "output"))
        result.tag("/role", "D", self.R(R_FIELDS, "/role"))
        result.tag("/actor", "I", self.R(R_AUTO, "/actor"))
        result.tag("/generated_by", "I", self.R(R_TOOL_EXEC, "/generated_by"))
        result.edge(te.id, "causal")
        result.tag("/after", "I", self.R(R_GEN, "/after"))
        for pointer, _rid in redacted:
            result.tag(pointer, "D", self.R(R_REDACTED, pointer))
        if redacted:
            result.x("redacted", [{"p": pointer, "rule": self.redactor.ref(rid)} for pointer, rid in redacted])
            self.n_redacted += len(redacted)
        return [call.done(), te.done(), result.done()], result.id

    # ---------------------------------------------------------------------------------------------- judgements
    def _judgements(self, judged: Sequence[str]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for name in judged:
            rec = _Rec(k="judgement", id=self.next_id("j"), actor="det", subject="run", name=name, ev="O")
            rec.set("value", self.run_v[name])
            rec.data["origin"] = "checker"
            rec.tag("/origin", "I", self.R(R_DETECTOR, "/origin"))
            rec.loc(self.loc(name))
            rec.unk.update({"/t": "not_recorded", "/inputs": "not_recorded"})
            out.append(rec.done())
        if not out:
            self.issue("no_outcome_recorded", ["run"], R_DETECTOR)
        return out

    # ---------------------------------------------------------------------------------------------- checks
    def _checks(self) -> None:
        model, scenario = self.run_v.get("model"), self.run_v.get("scenarioId")
        if (isinstance(model, str) and model != self.cell.get("model")) or (
                isinstance(scenario, str) and scenario != self.cell.get("scenario")):
            self.issue("credleak.cell_run_disagree", ["exec"], R_CELL, detail="model" if model != self.cell.get("model")
                       else "scenario")
        count = self.run_v.get("toolCallCount")
        observed = {"tool_calls": self.n_calls, "turns": len(self.turns)}
        if not (isinstance(count, int) and not isinstance(count, bool) and count >= 0):
            self.ctx.check(R_COUNT, scope="att0", verdict="unverifiable", observed=observed, reason="count_not_recorded")
            return
        ok = count == self.n_calls
        self.ctx.check(R_COUNT, scope="att0", verdict="consistent" if ok else "inconsistent",
                       observed={**observed, "tool_call_count": count}, reason=None if ok else "count_differs")
