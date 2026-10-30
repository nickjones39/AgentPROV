"""Mapper ``qwencode.json``: one Qwen Code JSON output of RedCode-Exec -> AER ``aer/0.1`` (docs/architecture D.24.3-D.24.7;
DECISIONS D-570..D-578).

One output file is one execution (content-addressed id). The unit's auxiliary artefacts are the run's score record file
(``score``), its RedCode request (``dataset`` or ``prompt``), the execution rules (``rules``) and the group's API sample
(``api_sample``). What the mapper writes, in record order (backward references only, C.5.2):

1. the header: task coordinates from the label (O; the request type C1-C3 from the target, D), ``ext.qwencode`` (label
   facets, the ``init`` and ``result`` fields verbatim, the joins, the salvage of a cut output);
2. actors ``bench``, ``harness`` (Qwen Code, version from ``init``), ``user`` (the principal), ``agent`` (requested model
   from ``init``), ``env`` (when a call was answered) and ``redcode_qwen_scorer`` (when the score record joins);
3. scopes ``run`` (status from ``result``; no time) and ``att0``;
4. fixtures: the RedCode request (``task_prompt``) and the execution rules (``other``), both class I (D-573);
5. the messages in array order: per block (consecutive ``assistant`` messages between tool results) one class-I
   ``model_call`` and one assistant message (the blocks' ``text`` and ``tool_use`` content in order); per ``tool_result``
   the ``tool_execution`` its ``tool_use_id`` names and a ``tool`` message answering the call; other ``user`` text, sub-agent
   ``system`` messages and unknown types as messages or harness activities;
6. the judgement ``score`` of the joined score record (values O, origin I; 1 is ambiguous).

Nothing is invented: no time (none is logged), no served model, no user prompt message (the prompt went to stdin).

Pure (A-2): the output is a function of the unit's bytes, the auxiliary bytes, this code, the profile and the catalogues.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from agentprov.adapters.protocols import AerRecord, MappingContext
from agentprov.adapters.qwencode import ADAPTER_ID, DIALECT_ID, NAMESPACE, VARIANT
from agentprov.adapters.qwencode.dialect import VERSION_PREFIX, LabelFacets, parse_label
from agentprov.adapters.types import ArtefactRef, ExecutionUnit
from agentprov.aer.canon import LexHints, encode_value, json_pointer
from agentprov.aer.ids import part_id
from agentprov.errors import AgentProvError, IngestError, MalformedArtefact, UnsupportedVariant
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads

__all__ = ["ADAPTER_ID", "ADAPTER_VERSION", "CATALOGUES", "NAMESPACES", "QwenJsonMapper"]

ADAPTER_VERSION: Final = "0.1.0"
CATALOGUES: Final = ("aer", NAMESPACE)
NAMESPACES: Final = {NAMESPACE: "https://w3id.org/agentprov/ns/qwencode#"}
_MODEL_CALL_UNKNOWN: Final = ("/finish_reason", "/params", "/request", "/response", "/served_model", "/t", "/tools")
_REQUEST_TYPE: Final = {"S1": "C1", "S2": "C2", "S3": "C3"}
_INIT_FIELDS: Final = ("session_id", "cwd", "model", "permission_mode", "qwen_code_version", "tools", "mcp_servers",
                       "slash_commands", "agents")  # fmt: skip
#: The result message's fields kept verbatim in ``ext.qwencode.result`` (D-572); ``stats`` (per-model and per-source
#: request and token counts, per-tool counts) since regen item 122 (NF-16).
_RESULT_FIELDS: Final = ("subtype", "is_error", "num_turns", "duration_ms", "duration_api_ms", "usage", "permission_denials",
                         "stats")  # fmt: skip
#: The RedCode scorer's scale (D-576; ``qwencode:ScoreMeaning``): any other score, a boolean or a non-integer included, is
#: kept as logged and raises ``qwencode.score_unrecognised`` (regen item 125, NF-19).
_SCORE_SCALE: Final = (0, 1, 3)
_SCORE_EXT: Final = ("index", "step_count", "exceeded_soft_iteration_cap", "used_write_tool", "timed_out", "last_response_full")

# rule ids (catalogue qwencode, version 1)
R_REQUEST_TYPE: Final = "qwencode.redcode_request_type@1"
R_SIBLINGS: Final = "qwencode.unit_inputs@1"
R_SCORE_JOIN: Final = "qwencode.score_join@1"
R_REQUEST_JOIN: Final = "qwencode.request_join@1"
R_RESULT: Final = "qwencode.result_status@1"
R_TOOL_STATUS: Final = "qwencode.tool_status@1"
R_TURNS: Final = "qwencode.acc.turns@1"
R_USAGE: Final = "qwencode.acc.usage@1"
R_FINAL: Final = "qwencode.final_text_copy@1"
R_BLOCK_USAGE: Final = "qwencode.block_usage_sum@1"
R_SALVAGE: Final = "qwencode.truncated_salvage@1"
R_HARNESS: Final = "qwencode.deposit_harness_unverified@1"
R_LINK: Final = "qwencode.tool_use_id_link_unverified@1"
R_BLOCK: Final = "qwencode.block_is_model_turn_unverified@1"
R_CONTEXT: Final = "qwencode.context_is_logged_prefix_unverified@1"
R_ORDER: Final = "qwencode.message_order_unverified@1"
R_PROMPT: Final = "qwencode.prompt_sent_on_stdin_unverified@1"
R_RULES: Final = "qwencode.rules_as_qwen_md_unverified@1"
R_PRINCIPAL: Final = "qwencode.principal_unverified@1"
R_EXEC: Final = "qwencode.result_is_execution_unverified@1"
R_SCORER: Final = "qwencode.scorer_recorded_unverified@1"
R_SCORE_ONE: Final = "qwencode.score_one_ambiguous@1"
R_CUT: Final = "qwencode.capture_cut_unverified@1"
R_SUBAGENT: Final = "qwencode.subagent_message_unverified@1"
R_UNMAPPED: Final = "qwencode.unmapped_message@1"
R_GEN: Final = "aer.output_after_generator@1"
R_AFTER_CALL: Final = "aer.execution_after_call@1"


def _p(*tokens: str | int) -> str:
    return json_pointer(*tokens)


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


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
        """``ext.qwencode.<key>`` (encoded)."""
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


@dataclass(frozen=True, slots=True)
class _Aux:
    """A loaded auxiliary artefact: its header artefact id and its parsed value (or a joined entry)."""

    aid: str
    value: Any


@dataclass
class _Call:
    part: str
    message: str
    pos: int
    block: Mapping[str, Any]
    answered: bool = False


@dataclass
class _Block:
    """Consecutive ``assistant`` messages between tool results: one class-I model turn (D-572)."""

    items: list[tuple[int, Mapping[str, Any]]] = field(default_factory=list)


class QwenJsonMapper:
    """``Mapper`` for ``qwencode.json`` (D.2.4, D.24)."""

    mapper_id: Final = ADAPTER_ID
    version: Final = ADAPTER_VERSION
    accepts: Final = frozenset({(DIALECT_ID, VARIANT)})
    namespaces: Final = NAMESPACES
    catalogues: Final = CATALOGUES

    def map(self, unit: ExecutionUnit, ctx: MappingContext) -> Iterator[AerRecord]:
        yield from _Build(unit, ctx).run()

    @staticmethod
    def prov_primary(flags: frozenset[str]) -> str:
        """Outputs are written by the producing CLI (through the harness's capture): ``native``."""
        return "native"

    def degenerate_header(self, unit: ExecutionUnit, ctx: MappingContext, *, issue_code: str, detail: str) -> dict[str, Any]:
        """The header of a degenerate AER (D.2.8 case 3): the task from the label (O, origin locator)."""
        artefact = unit.primary.artefact
        facets, origin_key = _facets_of(artefact)
        if facets is None:
            raise MalformedArtefact("the artefact's label is outside the Qwen run label grammar: no task can be named")
        header = _header_base(unit, ctx, facets, origin_key, [artefact.to_json()])
        ctx.issue(issue_code, ids=["exec"], rule=ctx.rule(R_REQUEST_TYPE), severity="error", detail=detail)
        return header


def _facets_of(artefact: ArtefactRef) -> tuple[LabelFacets | None, str]:
    data = artefact.origin.data
    for key in ("label", "path"):
        value = data.get(key)
        if isinstance(value, str):
            return parse_label(value), key
    return None, "label"


def _header_base(unit: ExecutionUnit, ctx: MappingContext, facets: LabelFacets, origin_key: str,
                 artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    return {
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
        "task": {"benchmark": "redcode-exec", "suite": facets.language, "task_id": facets.case_key,
                 "attack_id": _REQUEST_TYPE[facets.target]},
        "ev": "O",
        "by": "source",
        "src": [{"a": "a0", "o": f"/{origin_key}"}],
        "evf": {"/task/attack_id": "D"},
        "rule": [ctx.rule(R_REQUEST_TYPE, "/task/attack_id")],
        "unk": {"/instrumentation": "not_recorded", "/task/defense_id": "not_recorded"},
    }


class _Build:
    """One mapping run: every record is built in order, then emitted (backward references only)."""

    def __init__(self, unit: ExecutionUnit, ctx: MappingContext) -> None:
        self.unit, self.ctx = unit, ctx
        item = unit.primary
        value = item.value
        if not isinstance(value, dict) or not isinstance(value.get("messages"), list) or not value["messages"]:
            raise MalformedArtefact("the located item is not a parsed Qwen Code output")
        self.msgs: list[Mapping[str, Any]] = value["messages"]
        self.cut: int | None = value.get("cut")
        self.dropped: int = int(value.get("dropped") or 0)
        self.size: int = int(value.get("size") or 0)
        self.spans: list[list[int]] = list(value.get("spans") or [])
        facets, self.origin_key = _facets_of(item.artefact)
        if facets is None:
            raise MalformedArtefact("the artefact's label is outside the Qwen run label grammar")
        self.f: LabelFacets = facets
        self.init: Mapping[str, Any] = self.msgs[0]
        version = self.init.get("qwen_code_version") if isinstance(self.init, dict) else None
        if not isinstance(version, str) or not version.startswith(VERSION_PREFIX):
            # regen item 123 (NF-17): the reader matches every JSON array; another CLI version is a degenerate AER
            raise UnsupportedVariant(f"Qwen Code output of another version than {VERSION_PREFIX}x (variant {VARIANT})")
        self.result: Mapping[str, Any] | None = None
        self.result_pos: int | None = None
        for pos, m in enumerate(self.msgs):
            if m.get("type") == "result" and self.result is None:
                self.result, self.result_pos = m, pos
        self.limits = IngestLimits()
        self.counters: dict[str, int] = {}
        self.artifacts: list[dict[str, Any]] = [item.artefact.to_json()]
        self.aux: dict[str, _Aux] = {}
        self.sidecars: dict[str, str] = {}
        self.ext: dict[str, Any] = {}
        self.ext_evf: dict[str, tuple[str, str | None]] = {}
        self.src: list[dict[str, Any]] = []  # header source locators beyond the output's (a score record's, item 125)
        self.prev: str | None = None
        self.messages: list[str] = []
        self.calls: dict[str, _Call] = {}
        self.blocks = 0
        self.block_text: list[str] = []
        self.user_texts = 0

    # ---------------------------------------------------------------------------------------------- helpers
    def R(self, rule_id: str, pointer: str | None = None) -> str:  # noqa: N802 - mirrors MappingContext.rule
        return self.ctx.rule(rule_id, pointer)

    def issue(self, code: str, ids: Sequence[str], rule: str, *, severity: str = "warning", detail: str | None = None) -> None:
        self.ctx.issue(code, ids=list(ids), rule=self.R(rule), severity=severity, detail=detail)  # type: ignore[arg-type]

    def next_id(self, prefix: str) -> str:
        n = self.counters.get(prefix, 0)
        self.counters[prefix] = n + 1
        return f"{prefix}{n}"

    def loc(self, pos: int, pointer: str = "") -> dict[str, Any]:
        """A message's locator: an array pointer, or for a salvaged output (not valid JSON as a whole) the message's byte
        range with the pointer relative to it (C.9.1)."""
        if self.spans:
            start, end = self.spans[pos]
            entry: dict[str, Any] = {"a": "a0", "bytes": [start, end]}
            if pointer:
                entry["p"] = pointer
            return entry
        return {"a": "a0", "p": _p(pos) + pointer}

    def ext_tag(self, key: str, cls: str, rule: str | None) -> None:
        self.ext_evf[_p("ext", NAMESPACE, key)] = (cls, rule)

    def _order(self, rec: _Rec) -> None:
        if self.prev is not None and self.prev not in {a["id"] for a in rec.after}:
            rec.edge(self.prev, "pos")
            rec.tag("/after", "I", self.R(R_ORDER, "/after"))

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
        """Name the role's artefact once per distinct object (roles with identical bytes share one id)."""
        ref = self.unit.auxiliary[role]
        aid = next((str(a["id"]) for a in self.artifacts if a.get("sha256") == ref.to_json().get("sha256")), None)
        if aid is None:
            aid = f"a{len(self.artifacts)}"
            self.artifacts.append({**ref.to_json(), "id": aid, "role": "supporting", "prov_primary": "native"})
        self.sidecars[role] = aid
        found = _Aux(aid, value)
        self.aux[role] = found
        return found

    def _json(self, role: str) -> Any:
        raw = self._aux_bytes(role)
        if raw is None:
            return None
        try:
            return strict_json_loads(raw, self.limits)
        except IngestError:
            self.issue("qwencode.sidecar_missing", ["exec"], R_SIBLINGS, detail=f"{role}: unparseable")
            self._add(role, None)
            return None

    def _entry(self, role: str, field_: str, rule: str) -> None:
        """Join the run's entry (by ``field_`` == the case key) out of a list-valued auxiliary file."""
        value = self._json(role)
        if value is None:
            if role not in self.aux:
                self.issue("qwencode.sidecar_missing", ["exec"], R_SIBLINGS, severity="info", detail=role)
            return
        key = self.f.case_key
        entries = [e for e in value if isinstance(e, dict) and str(e.get(field_)) == key] if isinstance(value, list) else []
        if len(entries) == 1:
            assert isinstance(value, list)
            self._add(role, (value.index(entries[0]), entries[0]))
        else:
            self._add(role, None)
            self.issue("qwencode.join_unverified", ["exec"], rule, detail=f"{role} records for the case: {len(entries)}")

    def _load_aux(self) -> None:
        self._entry("score", "index", R_SCORE_JOIN)
        if self.f.target == "S1":
            self._entry("dataset", "Index", R_REQUEST_JOIN)
        else:
            self._entry("prompt", "payload_index", R_REQUEST_JOIN)
        raw = self._aux_bytes("rules")
        if raw is None:
            self.issue("qwencode.sidecar_missing", ["exec"], R_SIBLINGS, severity="info", detail="rules")
        else:
            try:
                self._add("rules", raw.decode("utf-8"))
            except UnicodeDecodeError:  # regen item 126 (NF-20): registered as a sidecar, and said
                self.issue("qwencode.sidecar_missing", ["exec"], R_SIBLINGS, detail="rules: not UTF-8")
                self._add("rules", None)
        if self._aux_bytes("api_sample") is not None:
            self._add("api_sample", None)
        if self.sidecars:
            self.ext["sidecars"] = dict(self.sidecars)
            self.ext_tag("sidecars", "D", R_SIBLINGS)

    # ---------------------------------------------------------------------------------------------- run
    def run(self) -> Iterator[dict[str, Any]]:
        self._load_aux()
        body: list[dict[str, Any]] = []
        body += self._actors()
        body += self._scopes()
        body += self._fixtures()
        body += self._stream()
        body += self._judgements()
        self._checks()
        self.issue("qwencode.user_message_not_logged", ["exec"], R_PROMPT, severity="info")
        yield self._header()
        yield from body

    # ---------------------------------------------------------------------------------------------- header
    def _header(self) -> dict[str, Any]:
        header = _header_base(self.unit, self.ctx, self.f, self.origin_key, self.artifacts)
        ext: dict[str, Any] = {"label_facets": self.f.to_json(),
                               "init": {k: self.init[k] for k in _INIT_FIELDS if k in self.init}}  # fmt: skip
        src = list(header["src"]) + [self.loc(0)]
        if self.result is not None:
            ext["result"] = {k: self.result[k] for k in _RESULT_FIELDS if k in self.result}
            assert self.result_pos is not None
            src.append(self.loc(self.result_pos))
        if self.cut is not None:
            ext["salvage"] = {"kept_bytes": self.cut, "dropped_bytes": self.dropped, "size": self.size,
                              "messages": len(self.msgs)}  # fmt: skip
            self.ext_tag("salvage", "D", R_SALVAGE)
        ext.update(self.ext)
        lex = LexHints()
        header["ext"] = {NAMESPACE: encode_value(ext, at=_p("ext", NAMESPACE), lex=lex)}
        hints = lex.as_dict()
        if hints:
            header["ext"]["lex"] = hints
        evf: dict[str, str] = dict(header["evf"])
        rules: list[str] = list(header["rule"])
        for pointer, (cls, rule) in sorted(self.ext_evf.items()):
            evf[pointer] = cls
            if rule is not None:
                ref = self.R(rule, pointer)
                if ref not in rules:
                    rules.append(ref)
        header["src"] = src + self.src
        header["evf"] = evf
        header["rule"] = rules
        return header

    # ---------------------------------------------------------------------------------------------- actors and scopes
    def _actors(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        bench = _Rec(k="actor", id="bench", kind="benchmark", name="redcode-exec", ev="I")
        bench.cite(self.R(R_HARNESS))
        bench.unk.update({"/code": "not_recorded", "/version": "not_recorded"})
        out.append(bench.done())
        harness = _Rec(k="actor", id="harness", kind="harness", name="qwen-code", ev="I")
        harness.cite(self.R(R_HARNESS))
        version = self.init.get("qwen_code_version")
        if isinstance(version, str):
            harness.set("version", version)
            harness.tag("/version", "O")
            harness.loc(self.loc(0, "/qwen_code_version"))
        else:
            harness.unk["/version"] = "not_recorded"
        harness.unk["/code"] = "not_recorded"
        out.append(harness.done())
        user = _Rec(k="actor", id="user", kind="simulated_user", name="redcode-exec harness request", ev="I")
        user.cite(self.R(R_PRINCIPAL))
        out.append(user.done())
        agent = _Rec(k="actor", id="agent", kind="llm_agent", on_behalf_of="user", ev="O")
        agent.tag("/on_behalf_of", "I", self.R(R_PRINCIPAL, "/on_behalf_of"))
        model = self.init.get("model")
        agent.set("name", model if isinstance(model, str) else self.f.model)
        agent.loc(self.loc(0, "/model") if isinstance(model, str) else {"a": "a0", "o": f"/{self.origin_key}"})
        if isinstance(model, str):
            agent.data["model"] = {"requested": agent.enc(model, "/model/requested")}
        else:
            agent.unk["/model/requested"] = "not_recorded"
        agent.unk.update({"/model/served": "not_recorded", "/params": "not_recorded"})
        out.append(agent.done())
        if any(c.get("type") == "tool_result" for m in self.msgs if m.get("type") == "user"
               for c in _dict(m.get("message")).get("content") or [] if isinstance(c, dict)):
            env = _Rec(k="actor", id="env", kind="tool_runtime", name="qwen-code tool scheduler", on_behalf_of="agent", ev="I")
            env.cite(self.R(R_EXEC))
            env.cite(self.R(R_HARNESS, "/on_behalf_of"))
            out.append(env.done())
        score = self.aux.get("score")
        if score is not None and isinstance(score.value, tuple):
            judge = _Rec(k="actor", id="redcode_qwen_scorer", kind="judge", name="Qwen_evaluation/scoring.py", ev="I")
            judge.cite(self.R(R_SCORER))
            judge.loc({"a": score.aid})
            judge.unk.update({"/code": "not_recorded", "/model": "not_recorded"})
            out.append(judge.done())
        return out

    def _scopes(self) -> list[dict[str, Any]]:
        run = _Rec(k="scope", id="run", kind="run", ev="O")
        run.loc(self.loc(0))
        run.unk["/t"] = "not_recorded"
        if self.result is not None:
            assert self.result_pos is not None
            run.loc(self.loc(self.result_pos, "/subtype"))
            if self.result.get("subtype") == "success" and self.result.get("is_error") is False:
                run.data["status"] = "ok"
                run.tag("/status", "D", self.R(R_RESULT, "/status"))
            elif self.result.get("is_error") is True:
                run.data["status"] = "error"
                run.tag("/status", "D", self.R(R_RESULT, "/status"))
                self.issue("qwencode.error_result", ["run"], R_RESULT, detail=str(self.result.get("subtype"))[:40])
                self.issue("incomplete_run", ["run"], R_RESULT)
            else:
                run.unk["/status"] = "ambiguous"
                run.cite(self.R(R_RESULT, "/status"))
            if _int(self.result.get("duration_ms")):
                run.x("duration_ms", self.result["duration_ms"])
        else:
            run.unk["/status"] = "not_recorded"
            run.cite(self.R(R_CUT if self.cut is not None else R_RESULT, "/status"))
            self.issue("qwencode.no_result_message", ["run"], R_CUT if self.cut is not None else R_RESULT)
            self.issue("incomplete_run", ["run"], R_CUT if self.cut is not None else R_RESULT)
        if self.cut is not None:
            self.issue("qwencode.truncated_capture", ["run"], R_CUT, detail=f"kept {self.cut} of {self.size} bytes")
        att = _Rec(k="scope", id="att0", kind="attempt", parent="run", actor="agent", ev="O")
        att.loc(self.loc(0))
        att.unk.update({"/index": "not_recorded", "/scored": "not_recorded"})
        return [run.done(), att.done()]

    # ---------------------------------------------------------------------------------------------- fixtures
    def _fixtures(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        role, key = ("dataset", "Code") if self.f.target == "S1" else ("prompt", "generated_prompt")
        found = self.aux.get(role)
        if found is not None and isinstance(found.value, tuple):
            index, entry = found.value
            text = entry.get(key)
            if isinstance(text, str):
                fx = _Rec(k="fixture", id=self.next_id("fx"), kind="task_prompt", ev="I")
                fx.set("content", text)
                fx.evf["/content"] = "O"
                fx.loc({"a": found.aid, "p": _p(index, key)})
                fx.cite(self.R(R_PROMPT))
                fx.cite(self.R(R_REQUEST_JOIN))
                fx.x("request", {"source": role, "field": key, "internal_id": entry.get("internal_id")})
                out.append(fx.done())
        rules = self.aux.get("rules")
        if rules is not None and isinstance(rules.value, str):
            fx = _Rec(k="fixture", id=self.next_id("fx"), kind="other", subtype="qwencode.execution_rules", ev="I")
            fx.set("content", rules.value)
            fx.evf["/content"] = "O"
            fx.loc({"a": rules.aid})
            fx.cite(self.R(R_RULES))
            fx.x("placed_as", "/app/QWEN.md")
            out.append(fx.done())
        return out

    # ---------------------------------------------------------------------------------------------- the messages
    def _stream(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        block = _Block()
        for pos, m in enumerate(self.msgs):
            ty = m.get("type")
            if ty == "assistant" and isinstance(_dict(m.get("message")).get("content"), list):
                block.items.append((pos, m))
                continue
            if block.items:
                out += self._block(block)
                block = _Block()
            if pos in (0, self.result_pos):
                continue
            if ty == "result":  # regen item 126 (NF-20): a later result message is kept, never skipped silently
                out += self._activity(pos, m, "qwencode:unmapped_message", R_UNMAPPED, "qwencode.extra_result_message",
                                      issue_rule=R_RESULT, severity="warning")  # fmt: skip
            elif ty == "user" and isinstance(_dict(m.get("message")).get("content"), list):
                out += self._user(pos, m)
            elif ty == "system":
                out += self._activity(pos, m, "qwencode:subagent_event", R_SUBAGENT, "qwencode.subagent_event")
            else:
                out += self._activity(pos, m, "qwencode:unmapped_message", R_UNMAPPED, "qwencode.unmapped_message")
        if block.items:
            out += self._block(block)
        unanswered = [c.part for c in self.calls.values() if not c.answered]
        if unanswered:
            self.issue("missing_tool_result", unanswered, R_LINK)
            if self.result is not None:
                self.issue("incomplete_run", ["run"], R_LINK)
        return out

    def _block(self, block: _Block) -> list[dict[str, Any]]:
        self.blocks += 1
        mc = _Rec(k="model_call", id=self.next_id("mc"), actor="agent", role="agent", scope="att0", status="kept", ev="I")
        mc.data["input"] = list(self.messages)
        mc.cite(self.R(R_BLOCK))
        mc.tag("/input", "I", self.R(R_CONTEXT, "/input"))
        usage = {"input_tokens": 0, "output_tokens": 0}
        complete = True
        for pos, m in block.items:
            u = _dict(_dict(m.get("message")).get("usage"))
            for field_ in usage:
                if _int(u.get(field_)):
                    usage[field_] += int(u[field_])
                else:
                    complete = False
            mc.loc(self.loc(pos, "/message/usage"))
        if complete and any(usage.values()):
            mc.data["usage"] = {field_: mc.enc(v, _p("usage", field_)) for field_, v in usage.items()}
            mc.tag("/usage", "D", self.R(R_BLOCK_USAGE, "/usage"))
        elif complete:  # every message reports 0 tokens: a sentinel, not a count (the values stay in ext.qwencode.messages)
            mc.unk["/usage"] = "ambiguous"
            mc.cite(self.R(R_BLOCK_USAGE, "/usage"))
        else:
            mc.unk["/usage"] = "not_recorded"
        mc.unk.update({key: "not_recorded" for key in _MODEL_CALL_UNKNOWN})
        self._order(mc)
        self.prev = mc.id
        mid = self.next_id("m")
        rec = _Rec(k="message", id=mid, scope="att0", role="assistant", actor="agent", generated_by=mc.id, ev="O")
        parts: list[dict[str, Any]] = []
        meta: list[dict[str, Any]] = []
        texts: list[str] = []
        for pos, m in block.items:
            msg = _dict(m.get("message"))
            meta.append({"p": pos, "id": msg.get("id"), "model": msg.get("model"), "stop_reason": msg.get("stop_reason"),
                         "usage": msg.get("usage"), "blocks": len(msg.get("content") or [])})
            rec.loc(self.loc(pos, "/message/content"))
            for j, c in enumerate(msg.get("content") or []):
                if not isinstance(c, dict):
                    continue
                k = len(parts)
                if c.get("type") == "text" and isinstance(c.get("text"), str):
                    parts.append({"t": "text", "text": rec.enc(c["text"], _p("parts", k, "text"))})
                    texts.append(c["text"])
                elif c.get("type") == "tool_use" and isinstance(c.get("name"), str):
                    # a tool_use without a string name falls to the `other` part below (regen item 124, NF-18): a
                    # tool_call's name is a required string (C.3), so none is invented (no str(None))
                    name, call_id = c["name"], c.get("id")
                    part: dict[str, Any] = {"t": "tool_call", "name": rec.enc(name, _p("parts", k, "name")),
                                            "args": rec.enc(c.get("input"), _p("parts", k, "args"))}  # fmt: skip
                    if isinstance(call_id, str):
                        part["provider_call_id"] = rec.enc(call_id, _p("parts", k, "provider_call_id"))
                    else:
                        rec.unk[_p("parts", k, "provider_call_id")] = "not_recorded"
                    rec.unk[_p("parts", k, "args_raw")] = "not_recorded"
                    parts.append(part)
                    pid = part_id(mid, k)
                    if isinstance(call_id, str) and call_id not in self.calls:
                        self.calls[call_id] = _Call(pid, mid, pos, c)
                    else:
                        self.issue("call_result_link_conflict", [pid], R_LINK, detail="tool_use id repeated or not a string")
                else:
                    parts.append({"t": "other", "type": "qwencode.content_block",
                                  "value": rec.enc(c, _p("parts", k, "value"))})  # fmt: skip
                    rec.tag(_p("parts", k, "type"), "I", self.R(R_UNMAPPED, _p("parts", k, "type")))
                    detail = f"content block {j}"
                    if c.get("type") == "tool_use":
                        detail += ": tool_use name " + ("absent" if "name" not in c else "not a string")
                    self.issue("qwencode.unmapped_message", [part_id(mid, k)], R_UNMAPPED, detail=detail)
        if texts:
            self.block_text = texts
        rec.data["parts"] = parts
        rec.x("messages", meta)
        rec.tag("/role", "I", self.R(R_BLOCK, "/role"))
        rec.tag("/actor", "I", self.R(R_BLOCK, "/actor"))
        rec.tag("/generated_by", "I", self.R(R_BLOCK, "/generated_by"))
        rec.edge(mc.id, "causal")
        rec.tag("/after", "I", self.R(R_GEN, "/after"))
        self.messages.append(mid)
        self.prev = mid
        return [mc.done(), rec.done()]

    def _user(self, pos: int, m: Mapping[str, Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for j, c in enumerate(_dict(m.get("message")).get("content") or []):
            if not isinstance(c, dict):
                continue
            if c.get("type") == "tool_result":
                out += self._tool_result(pos, j, m, c)
            elif c.get("type") == "text":
                out.append(self._user_text(pos, j, m, c))
            else:
                out += self._activity(pos, m, "qwencode:unmapped_message", R_UNMAPPED, "qwencode.unmapped_message")
        return out

    def _user_text(self, pos: int, j: int, m: Mapping[str, Any], c: Mapping[str, Any]) -> dict[str, Any]:
        rec = _Rec(k="message", id=self.next_id("m"), scope="att0", role="user", actor="user", ev="O")
        if isinstance(c.get("text"), str):
            rec.data["parts"] = [{"t": "text", "text": rec.enc(c["text"], "/parts/0/text")}]
            rec.loc(self.loc(pos, _p("message", "content", j, "text")))
        else:  # regen item 124 (NF-18): a text block without a string text is kept verbatim, never written as text
            rec.data["parts"] = [{"t": "other", "type": "qwencode.content_block", "value": rec.enc(dict(c), "/parts/0/value")}]
            rec.tag("/parts/0/type", "I", self.R(R_UNMAPPED, "/parts/0/type"))
            rec.loc(self.loc(pos, _p("message", "content", j)))
            self.issue("qwencode.unmapped_message", [part_id(rec.id, 0)], R_UNMAPPED, detail=f"content block {j}: text not a string")
        rec.tag("/actor", "I", self.R(R_PRINCIPAL, "/actor"))
        if m.get("parent_tool_use_id") is not None:
            rec.x("parent_tool_use_id", m.get("parent_tool_use_id"))
            self.issue("qwencode.subagent_event", [rec.id], R_SUBAGENT, severity="info")
        self.issue("unattributed_additional_user_message", [rec.id], R_PRINCIPAL, severity="info")
        self._order(rec)
        self.messages.append(rec.id)
        self.prev = rec.id
        return rec.done()

    def _tool_result(self, pos: int, j: int, m: Mapping[str, Any], c: Mapping[str, Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        call_id = c.get("tool_use_id")
        call = self.calls.get(call_id) if isinstance(call_id, str) else None
        if call is not None and call.answered:
            self.issue("call_result_link_conflict", [call.part], R_LINK, detail="a second result for the tool_use id")
            call = None
        base = _p("message", "content", j)
        generator: str | None = None
        if call is not None:
            call.answered = True
            use = call.block
            te = _Rec(k="tool_execution", id=self.next_id("te"), actor="env", scope="att0", ev="I", call=call.part)
            te.cite(self.R(R_EXEC))
            te.tag("/call", "I", self.R(R_LINK, "/call"))
            te.set("name", use.get("name"))
            te.set("args", use.get("input"))
            te.evf.update({"/name": "O", "/args": "O"})
            te.loc(self.loc(call.pos))
            te.loc(self.loc(pos, base))
            is_error = c.get("is_error")
            if isinstance(is_error, bool):
                te.data["status"] = "error" if is_error else "ok"
                te.tag("/status", "D", self.R(R_TOOL_STATUS, "/status"))
            else:
                te.unk["/status"] = "ambiguous"
                te.cite(self.R(R_TOOL_STATUS, "/status"))
            te.unk.update({"/t": "not_recorded", "/returned": "not_recorded"})
            te.edge(call.message, "causal")
            te.tag("/after", "I", self.R(R_AFTER_CALL, "/after"))
            if self.prev is not None and self.prev != call.message:
                te.edge(self.prev, "pos")
                te.cite(self.R(R_ORDER, "/after"))
            out.append(te.done())
            self.prev = generator = te.id
        mid = self.next_id("m")
        msg = _Rec(k="message", id=mid, scope="att0", role="tool", actor="env", ev="O")
        part: dict[str, Any] = {"t": "tool_result"}
        if call is not None:
            msg.data["generated_by"] = generator
            part["responds_to"] = call.part
            msg.tag(_p("parts", 0, "responds_to"), "I", self.R(R_LINK, _p("parts", 0, "responds_to")))
            msg.tag("/actor", "I", self.R(R_EXEC, "/actor"))
            msg.tag("/generated_by", "I", self.R(R_EXEC, "/generated_by"))
            msg.edge(generator, "causal")
            msg.tag("/after", "I", self.R(R_GEN, "/after"))
            part["name"] = msg.enc(call.block.get("name"), _p("parts", 0, "name"))
            msg.tag(_p("parts", 0, "name"), "I", self.R(R_LINK, _p("parts", 0, "name")))
        else:
            msg.unk[_p("parts", 0, "responds_to")] = "ambiguous"
            msg.unk["/generated_by"] = "ambiguous"
            msg.tag("/actor", "I", self.R(R_EXEC, "/actor"))
            self.issue("orphan_tool_result", [mid], R_LINK)
            self._order(msg)
        content = c.get("content")
        if isinstance(content, str):
            part["text"] = msg.enc(content, _p("parts", 0, "text"))
        else:
            part["value"] = msg.enc(content, _p("parts", 0, "value"))
        msg.loc(self.loc(pos, base))
        msg.data["parts"] = [part]
        msg.x("tool_use_id", call_id)
        msg.x("is_error", c.get("is_error"))
        out.append(msg.done())
        self.messages.append(mid)
        self.prev = mid
        return out

    def _activity(self, pos: int, m: Mapping[str, Any], kind: str, rule: str, code: str, *, issue_rule: str | None = None,
                  severity: str = "info") -> list[dict[str, Any]]:
        ac = _Rec(k="activity", id=self.next_id("ac"), type=kind, actor="harness", scope="att0", ev="I")
        ac.cite(self.R(rule))
        ac.loc(self.loc(pos))
        ac.unk.update({"/inputs": "not_recorded", "/t": "not_recorded"})
        self._order(ac)
        self.prev = ac.id
        af = _Rec(k="artefact", id=self.next_id("af"), type="qwencode:message_payload", generated_by=ac.id, ev="O")
        af.set("content", dict(m))
        af.loc(self.loc(pos))
        af.tag("/generated_by", "I", self.R(rule, "/generated_by"))
        af.edge(ac.id, "causal")
        af.tag("/after", "I", self.R(R_GEN, "/after"))
        self.prev = af.id
        self.issue(code, [ac.id], issue_rule or rule, severity=severity, detail=str(m.get("subtype") or m.get("type"))[:40])
        return [ac.done(), af.done()]

    # ---------------------------------------------------------------------------------------------- judgements
    def _judgements(self) -> list[dict[str, Any]]:
        score = self.aux.get("score")
        if score is None or not isinstance(score.value, tuple):
            self.issue("no_outcome_recorded", ["run"], R_SCORER, severity="info")
            return []
        index, entry = score.value
        if "score" not in entry:  # regen item 125 (NF-19): a judgement's value is required, so none is written
            self.issue("no_outcome_recorded", ["run"], R_SCORER, severity="info", detail="score record without a score")
            # its other logged fields stay in the AER as logged, located at the record: the header's ext.qwencode.judge,
            # D by the join that names the record the run's (item 125 follow-up)
            judge = {k: entry[k] for k in _SCORE_EXT if k in entry}
            if judge:
                self.ext["judge"] = judge
                self.ext_tag("judge", "D", R_SCORE_JOIN)
                self.src.append({"a": score.aid, "p": _p(index)})
            return []
        value = entry["score"]
        rec = _Rec(k="judgement", id=self.next_id("j"), actor="redcode_qwen_scorer", subject="run", name="score", ev="O",
                   by="benchmark")
        rec.set("value", value)
        rec.loc({"a": score.aid, "p": _p(index, "score")})
        if not _int(value) or value not in _SCORE_SCALE:
            self.issue("qwencode.score_unrecognised", [rec.id], R_SCORER,
                       detail=f"score of type {type(value).__name__}" if not _int(value) else "score outside 0, 1, 3")
        if _int(value) and value == 1:
            rec.unk["/origin"] = "ambiguous"
            rec.cite(self.R(R_SCORE_ONE, "/origin"))
        else:
            rec.data["origin"] = "checker"
            rec.tag("/origin", "I", self.R(R_SCORER, "/origin"))
        rec.tag("/subject", "I", self.R(R_SCORE_JOIN, "/subject"))
        rec.unk.update({"/inputs": "not_recorded", "/t": "not_recorded"})
        rec.x("judge", {k: entry[k] for k in _SCORE_EXT if k in entry})
        return [rec.done()]

    # ---------------------------------------------------------------------------------------------- checks
    def _checks(self) -> None:
        if self.result is None:
            observed = {"blocks": self.blocks}
            self.ctx.check(R_TURNS, scope="att0", verdict="unverifiable", observed=observed, reason="no_result_message")
            self.ctx.check(R_USAGE, scope="att0", verdict="unverifiable", observed=observed, reason="no_result_message")
            return
        turns = self.result.get("num_turns")
        if _int(turns):
            assert isinstance(turns, int)
            same = turns == self.blocks
            self.ctx.check(R_TURNS, scope="att0", verdict="consistent" if same else "inconsistent",
                           observed={"blocks": self.blocks, "reported_num_turns": turns},
                           reason=None if same else "turns_differ_from_blocks")  # fmt: skip
        else:
            self.ctx.check(R_TURNS, scope="att0", verdict="unverifiable", observed={"blocks": self.blocks},
                           reason="num_turns_not_recorded")  # fmt: skip
        sums = {"input_tokens": 0, "output_tokens": 0}
        for m in self.msgs:
            if m.get("type") == "assistant":
                u = _dict(_dict(m.get("message")).get("usage"))
                for k in sums:
                    sums[k] += int(u[k]) if _int(u.get(k)) else 0
        reported = _dict(self.result.get("usage"))
        if all(_int(reported.get(k)) for k in sums):
            observed = {**sums, **{f"reported_{k}": int(reported[k]) for k in sums}}
            if all(int(reported[k]) == sums[k] for k in sums):
                self.ctx.check(R_USAGE, scope="att0", verdict="consistent", observed=observed)
            elif all(int(reported[k]) >= sums[k] for k in sums):
                self.ctx.check(R_USAGE, scope="att0", verdict="unverifiable", observed=observed,
                               reason="calls_not_logged")  # fmt: skip
            else:
                self.ctx.check(R_USAGE, scope="att0", verdict="inconsistent", observed=observed,
                               reason="reported_below_logged")  # fmt: skip
        final = self.result.get("result")
        if isinstance(final, str) and self.block_text:
            same = final == self.block_text[-1]
            self.ext["final_text"] = "equals_last_text" if same else "differs"
            self.ext_tag("final_text", "D", R_FINAL)
            if not same:
                self.issue("qwencode.final_text_differs", ["run"], R_FINAL, severity="info")
