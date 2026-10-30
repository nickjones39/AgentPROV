"""Mapper ``geminicli.stream_json``: one gemini-cli stream -> AER ``aer/0.1`` (docs/architecture D.23.3-D.23.7; DECISIONS
D-330..D-337).

One non-empty ``gemini_stream.jsonl`` is one execution (content-addressed id). The unit's auxiliary artefacts are the
rollout's sibling members by role (``verdict``, ``meta``, ``fs_before``, ``fs_after``, ``diff``, ``harness_events``,
``cli_stderr``, ``runner_stdout``, ``runner_stderr``, ``atoms``) and the deposit's ``manifest``. What the mapper writes, in
record order (backward references only, C.5.2):

1. the header: task coordinates from the label (O, origin locator), ``ext.geminicli`` (label facets, the CLI's session
   id and model name, the verdict, CLI meta and ``result`` fields verbatim, the manifest cross-check);
2. actors ``bench``, ``harness``, ``user``, ``agent`` (``model.requested`` = the verdict's cell model, I), ``env`` (when a
   call was answered) and ``detector`` (when the verdict is present);
3. scopes ``run`` (status from the ``result`` event, or ``aborted`` without one; raw first and last event times) and
   ``att0``;
4. the fixture ``environment_seed`` (``fs_before.json``);
5. the stream in line order: the user message; per block (a maximal run of assistant deltas and ``tool_use`` events) one
   class-I ``model_call`` and one assistant message (the deltas concatenated into text parts, then the calls); per
   ``tool_result`` the ``tool_execution`` its ``tool_id`` names and a ``tool`` message answering the call; per CLI
   ``error`` event a harness activity and its artefact;
6. the judgements ``elicited`` and ``n_misaligned`` of the verdict (values O, origin I).

Nothing is invented: event times stay verbatim (typed slots ``ambiguous``), no model call carries a time, usage or served
model, no tool status beyond the stream's own, no relation for the stored sidecars (``fs_after.json``, the diff, the
harness atoms, the logs). Every reading of gemini-cli behaviour is class I (D-334: the deposit names no CLI version).

Pure (A-2): the output is a function of the unit's bytes, the auxiliary bytes, this code, the profile and the catalogues.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from agentprov.adapters.geminicli import ADAPTER_ID, DIALECT_ID, NAMESPACE, VARIANT
from agentprov.adapters.geminicli.dialect import LabelFacets, parse_label
from agentprov.adapters.protocols import AerRecord, MappingContext
from agentprov.adapters.types import ArtefactRef, ExecutionUnit
from agentprov.aer.canon import LexHints, encode_value, json_pointer
from agentprov.aer.ids import part_id
from agentprov.errors import AgentProvError, IngestError, MalformedArtefact
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads

__all__ = ["ADAPTER_ID", "ADAPTER_VERSION", "CATALOGUES", "JUDGEMENTS", "NAMESPACES", "GeminiStreamMapper"]

ADAPTER_VERSION: Final = "0.1.0"
CATALOGUES: Final = ("aer", NAMESPACE)
NAMESPACES: Final = {NAMESPACE: "https://w3id.org/agentprov/ns/geminicli#"}
_MODEL_CALL_UNKNOWN: Final = ("/finish_reason", "/params", "/request", "/response", "/served_model", "/t", "/tools",
                              "/usage")  # fmt: skip
#: The verdict fields read as judgements (D-337), in order.
JUDGEMENTS: Final = ("elicited", "n_misaligned")
#: The manifest columns compared with the verdict (D-337; booleans are written 0/1 there).
_MANIFEST_FIELDS: Final = ("elicited", "timed_out", "n_misaligned", "exit_code")
_SUBAGENT_TOOLS: Final = frozenset({"codebase_investigator"})
_TERMINATED: Final = 143

# rule ids (catalogue geminicli, version 1)
R_FACETS: Final = "geminicli.label_facets@1"
R_SIBLINGS: Final = "geminicli.sibling_join@1"
R_MANIFEST: Final = "geminicli.manifest_agrees@1"
R_COUNTERS: Final = "geminicli.acc.counters@1"
R_RESULT: Final = "geminicli.result_status@1"
R_TOOL_STATUS: Final = "geminicli.tool_status@1"
R_LAST: Final = "geminicli.result_is_last@1"
R_VERDICT_META: Final = "geminicli.verdict_meta_compare@1"
R_ALIAS: Final = "geminicli.cli_model_compare@1"
R_LINK: Final = "geminicli.tool_id_link_unverified@1"
R_DELTAS: Final = "geminicli.deltas_compose_message_unverified@1"
R_BLOCK: Final = "geminicli.block_is_model_turn_unverified@1"
R_CONTEXT: Final = "geminicli.context_is_logged_prefix_unverified@1"
R_ORDER: Final = "geminicli.stream_order_unverified@1"
R_TIME: Final = "geminicli.event_time_is_emission_unverified@1"
R_PROMPT: Final = "geminicli.prompt_harness_authored_unverified@1"
R_MODEL: Final = "geminicli.cell_model_routed_unverified@1"
R_HARNESS: Final = "geminicli.deposit_harness_unverified@1"
R_EXEC: Final = "geminicli.result_is_execution_unverified@1"
R_ABORTED: Final = "geminicli.exit_143_terminated_unverified@1"
R_DETECTOR: Final = "geminicli.detector_recorded_unverified@1"
R_NOTICE: Final = "geminicli.cli_notice_is_harness_unverified@1"
R_SUBAGENT: Final = "geminicli.subagent_tool_unverified@1"
R_SEED: Final = "geminicli.workspace_seed_unverified@1"
R_UNMAPPED: Final = "geminicli.unmapped_event@1"
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
        """``ext.geminicli.<key>`` (encoded)."""
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
    """A loaded auxiliary artefact: its header artefact id and its parsed value (``None`` when unparseable)."""

    aid: str
    value: Any


@dataclass
class _Call:
    """A ``tool_use`` event and the call part it became."""

    part: str
    message: str
    line: int
    event: Mapping[str, Any]
    answered: bool = False


@dataclass
class _Block:
    """Assistant deltas and ``tool_use`` events between results (one class-I model turn, D-332)."""

    items: list[tuple[int, Mapping[str, Any]]] = field(default_factory=list)


class GeminiStreamMapper:
    """``Mapper`` for ``geminicli.stream_json`` (D.2.4, D.23)."""

    mapper_id: Final = ADAPTER_ID
    version: Final = ADAPTER_VERSION
    accepts: Final = frozenset({(DIALECT_ID, VARIANT)})
    namespaces: Final = NAMESPACES
    catalogues: Final = CATALOGUES

    def map(self, unit: ExecutionUnit, ctx: MappingContext) -> Iterator[AerRecord]:
        yield from _Build(unit, ctx).run()

    @staticmethod
    def prov_primary(flags: frozenset[str]) -> str:
        """Streams are written by the producing CLI: ``native``."""
        return "native"

    def degenerate_header(self, unit: ExecutionUnit, ctx: MappingContext, *, issue_code: str, detail: str) -> dict[str, Any]:
        """The header of a degenerate AER (D.2.8 case 3): the task from the label (O, origin locator)."""
        artefact = unit.primary.artefact
        facets, origin_key = _facets_of(artefact)
        if facets is None:
            raise MalformedArtefact("the artefact's label is outside the gemini_cli label grammar: no task can be named")
        header = _header_base(unit, ctx, facets, origin_key, [artefact.to_json()])
        ctx.issue(issue_code, ids=["exec"], rule=ctx.rule(R_FACETS), severity="error", detail=detail)
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
        "task": {"benchmark": "code-agent-misalignment", "suite": facets.skeleton, "task_id": facets.mutation},
        "ev": "O",
        "by": "source",
        "src": [{"a": "a0", "o": f"/{origin_key}"}],
        "unk": {"/instrumentation": "not_recorded", "/task/attack_id": "not_recorded",
                "/task/defense_id": "not_recorded"},
    }


class _Build:
    """One mapping run: every record is built in order, then emitted (backward references only)."""

    def __init__(self, unit: ExecutionUnit, ctx: MappingContext) -> None:
        self.unit, self.ctx = unit, ctx
        item = unit.primary
        value = item.value
        if not isinstance(value, dict) or not isinstance(value.get("events"), list):
            raise MalformedArtefact("the located item is not a parsed gemini-cli stream")
        self.events: list[tuple[int, Mapping[str, Any]]] = [(int(e["line"]), e["event"]) for e in value["events"]]
        if not self.events or self.events[0][1].get("type") != "init":
            raise MalformedArtefact("the stream does not start with an init event")
        facets, self.origin_key = _facets_of(item.artefact)
        if facets is None:
            raise MalformedArtefact("the artefact's label is outside the gemini_cli label grammar")
        self.f: LabelFacets = facets
        self.limits = IngestLimits()
        self.counters: dict[str, int] = {}
        self.artifacts: list[dict[str, Any]] = [item.artefact.to_json()]
        self.aux: dict[str, _Aux] = {}
        self.sidecars: dict[str, str] = {}
        self.ext: dict[str, Any] = {}
        self.ext_evf: dict[str, tuple[str, str | None]] = {}
        self.header_src: list[dict[str, Any]] = [{"a": "a0", "o": f"/{self.origin_key}"}]
        self.prev: str | None = None
        self.messages: list[str] = []
        self.calls: dict[str, _Call] = {}
        self.has_env = False
        self.user_messages = 0
        self.result: Mapping[str, Any] | None = None
        self.result_line: int | None = None
        self.init = self.events[0][1]

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
    def loc(line: int, pointer: str | None = None) -> dict[str, Any]:
        entry: dict[str, Any] = {"a": "a0", "line": line}
        if pointer:
            entry["p"] = pointer
        return entry

    def ext_tag(self, key: str, cls: str, rule: str | None) -> None:
        self.ext_evf[_p("ext", NAMESPACE, key)] = (cls, rule)

    def _order(self, rec: _Rec) -> None:
        """A positional ``after`` edge to the previous stream record (line order, class I)."""
        if self.prev is not None and self.prev not in {a["id"] for a in rec.after}:
            rec.edge(self.prev, "pos")
            rec.tag("/after", "I", self.R(R_ORDER, "/after"))

    def _stamp(self, rec: _Rec, event: Mapping[str, Any]) -> None:
        stamp = event.get("timestamp")
        if stamp is not None:
            rec.x("timestamp", stamp)

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
        """Name the role's artefact in the header, once per distinct object: two siblings with the same bytes (empty
        logs, say) are one raw object, so the second role reuses the first's id (``ext.geminicli.sidecars``)."""
        ref = self.unit.auxiliary[role]
        aid = next((str(a["id"]) for a in self.artifacts if a.get("sha256") == ref.to_json().get("sha256")), None)
        if aid is None:
            aid = f"a{len(self.artifacts)}"
            self.artifacts.append({**ref.to_json(), "id": aid, "role": "supporting", "prov_primary": "native"})
        self.sidecars[role] = aid
        found = _Aux(aid, value)
        self.aux[role] = found
        return found

    def _load_aux(self) -> None:
        """Every auxiliary by role, in role order: JSON roles parsed strictly, the rest stored and named only."""
        for role in sorted(self.unit.auxiliary):
            raw = self._aux_bytes(role)
            if raw is None:
                continue
            value: Any = None
            if role in ("verdict", "meta", "fs_before"):
                try:
                    value = strict_json_loads(raw, self.limits)
                except IngestError:
                    self.issue("geminicli.sidecar_unparseable", ["exec"], R_SIBLINGS, detail=role)
            elif role == "manifest":
                value = raw
            self._add(role, value)
        if self.sidecars:
            self.ext["sidecars"] = dict(self.sidecars)
            self.ext_tag("sidecars", "D", R_SIBLINGS)
        for role in ("verdict", "meta"):
            if not isinstance(self.aux.get(role, _Aux("", None)).value, dict):
                self.issue("geminicli.sidecar_missing", ["exec"], R_SIBLINGS, severity="info", detail=role)

    def _value(self, role: str) -> dict[str, Any]:
        found = self.aux.get(role)
        return found.value if found is not None and isinstance(found.value, dict) else {}

    # ---------------------------------------------------------------------------------------------- run
    def run(self) -> Iterator[dict[str, Any]]:
        self._load_aux()
        for line, event in self.events:
            if event.get("type") == "result" and self.result is None:
                self.result, self.result_line = event, line
        body: list[dict[str, Any]] = []
        body += self._actors()
        body += self._scopes()
        body += self._fixtures()
        body += self._stream()
        body += self._judgements()
        self._checks()
        yield self._header()
        yield from body

    # ---------------------------------------------------------------------------------------------- header
    def _header(self) -> dict[str, Any]:
        header = _header_base(self.unit, self.ctx, self.f, self.origin_key, self.artifacts)
        ext: dict[str, Any] = {"label_facets": self.f.to_json(), "session_id": self.init.get("session_id"),
                               "cli_model": self.init.get("model")}  # fmt: skip
        src = list(self.header_src) + [self.loc(0, "/session_id"), self.loc(0, "/model")]
        evf: dict[str, str] = {}
        rules: list[str] = []
        verdict = self.aux.get("verdict")
        if verdict is not None and isinstance(verdict.value, dict):
            ext["verdict"] = verdict.value
            src.append({"a": verdict.aid})
            self.ext_tag("verdict", "O", None)
            self._facet_check(verdict.value)
        meta = self.aux.get("meta")
        if meta is not None and isinstance(meta.value, dict):
            ext["meta"] = meta.value
            src.append({"a": meta.aid})
            self.ext_tag("meta", "O", None)
        if self.result is not None:
            ext["result"] = {k: self.result[k] for k in ("status", "stats", "error") if k in self.result}
            assert self.result_line is not None
            src.append(self.loc(self.result_line))
        ext.update(self.ext)
        lex = LexHints()
        header["ext"] = {NAMESPACE: encode_value(ext, at=_p("ext", NAMESPACE), lex=lex)}
        hints = lex.as_dict()
        if hints:
            header["ext"]["lex"] = hints
        for pointer, (cls, rule) in sorted(self.ext_evf.items()):
            evf[pointer] = cls
            if rule is not None:
                ref = self.R(rule, pointer)
                if ref not in rules:
                    rules.append(ref)
        header["src"] = src
        if evf:
            header["evf"] = evf
        if rules:
            header["rule"] = rules
        return header

    def _facet_check(self, verdict: Mapping[str, Any]) -> None:
        """``geminicli.label_facets@1``: the label's mutation, scaffold and model against the verdict's (never corrected)."""
        expected = {"mutation_id": self.f.mutation, "agent": self.f.scaffold, "model": self.f.model}
        for name, want in expected.items():
            if verdict.get(name) != want:
                self.issue("geminicli.label_field_mismatch", ["exec"], R_FACETS, severity="info", detail=name)

    # ---------------------------------------------------------------------------------------------- actors and scopes
    def _actors(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        bench = _Rec(k="actor", id="bench", kind="benchmark", name="code-agent-misalignment", ev="I")
        bench.cite(self.R(R_HARNESS))
        bench.unk.update({"/code": "not_recorded", "/version": "not_recorded"})
        out.append(bench.done())
        harness = _Rec(k="actor", id="harness", kind="harness", name="gemini-cli", ev="I")
        harness.cite(self.R(R_HARNESS))
        harness.unk.update({"/code": "not_recorded", "/version": "not_recorded"})
        out.append(harness.done())
        user = _Rec(k="actor", id="user", kind="simulated_user", name="code-agent-misalignment harness prompt", ev="I")
        user.cite(self.R(R_PROMPT))
        out.append(user.done())
        verdict = self.aux.get("verdict")
        v = self._value("verdict")
        agent = _Rec(k="actor", id="agent", kind="llm_agent", on_behalf_of="user", ev="O")
        agent.tag("/on_behalf_of", "I", self.R(R_HARNESS, "/on_behalf_of"))
        if verdict is not None and isinstance(v.get("sut_id"), str):
            agent.set("name", v["sut_id"])
            agent.loc({"a": verdict.aid, "p": "/sut_id"})
        else:
            agent.set("name", self.f.cell)
            agent.loc({"a": "a0", "o": f"/{self.origin_key}"})
        if verdict is not None and isinstance(v.get("model"), str):
            agent.data["model"] = {"requested": agent.enc(v["model"], "/model/requested")}
            agent.tag("/model", "I", self.R(R_MODEL, "/model"))
            agent.loc({"a": verdict.aid, "p": "/model"})
            if self.init.get("model") != v["model"]:
                self.issue("geminicli.cli_model_alias", ["agent"], R_ALIAS, severity="info")
        else:
            agent.unk["/model/requested"] = "ambiguous"
            agent.cite(self.R(R_MODEL, "/model"))
        agent.unk.update({"/model/served": "not_recorded", "/params": "not_recorded"})
        out.append(agent.done())
        if any(e.get("type") == "tool_result" for _line, e in self.events):
            env = _Rec(k="actor", id="env", kind="tool_runtime", name="gemini-cli tool scheduler", on_behalf_of="agent",
                       ev="I")
            env.cite(self.R(R_EXEC))
            env.cite(self.R(R_HARNESS, "/on_behalf_of"))
            out.append(env.done())
        if verdict is not None and isinstance(verdict.value, dict):
            judge = _Rec(k="actor", id="detector", kind="judge", name="code-agent-misalignment detector", ev="I")
            judge.cite(self.R(R_DETECTOR))
            judge.loc({"a": verdict.aid})
            judge.unk.update({"/code": "not_recorded", "/model": "not_recorded"})
            out.append(judge.done())
        return out

    def _scopes(self) -> list[dict[str, Any]]:
        run = _Rec(k="scope", id="run", kind="run", ev="O")
        first_line, first = self.events[0]
        last_line, last = self.events[-1]
        raw = {k: v for k, v in (("start", first.get("timestamp")), ("end", last.get("timestamp"))) if isinstance(v, str)}
        if raw:
            run.data["t"] = {"raw": run.enc(raw, "/t/raw")}
            for k in raw:
                run.unk[f"/t/{k}"] = "ambiguous"
                run.cite(self.R(R_TIME, f"/t/{k}"))
        else:
            run.unk["/t"] = "not_recorded"
        run.loc(self.loc(first_line))
        run.loc(self.loc(last_line))
        meta = self._value("meta")
        if self.result is not None:
            assert self.result_line is not None
            status = self.result.get("status")
            run.loc(self.loc(self.result_line, "/status"))
            if status == "success":
                run.data["status"] = "ok"
                run.tag("/status", "D", self.R(R_RESULT, "/status"))
            elif status == "error":
                run.data["status"] = "error"
                run.tag("/status", "D", self.R(R_RESULT, "/status"))
                error = _dict(self.result.get("error")).get("type")
                self.issue("geminicli.cli_error_result", ["run"], R_RESULT, detail=str(error)[:40] if error else None)
                self.issue("incomplete_run", ["run"], R_RESULT)
            else:
                run.unk["/status"] = "ambiguous"
                run.cite(self.R(R_RESULT, "/status"))
        elif meta.get("exit_code") == _TERMINATED:
            run.data["status"] = "aborted"
            run.tag("/status", "I", self.R(R_ABORTED, "/status"))
            run.loc({"a": self.aux["meta"].aid, "p": "/exit_code"})
            self.issue("geminicli.no_result_event", ["run"], R_ABORTED)
            self.issue("incomplete_run", ["run"], R_ABORTED)
        else:
            run.unk["/status"] = "not_recorded"
            run.cite(self.R(R_ABORTED, "/status"))
            self.issue("geminicli.no_result_event", ["run"], R_ABORTED)
            self.issue("incomplete_run", ["run"], R_ABORTED)
        att = _Rec(k="scope", id="att0", kind="attempt", parent="run", actor="agent", ev="O")
        att.loc(self.loc(first_line))
        att.unk.update({"/index": "not_recorded", "/scored": "not_recorded"})
        return [run.done(), att.done()]

    # ---------------------------------------------------------------------------------------------- fixtures
    def _fixtures(self) -> list[dict[str, Any]]:
        seed = self.aux.get("fs_before")
        if seed is None or not isinstance(seed.value, dict):
            return []
        fx = _Rec(k="fixture", id=self.next_id("fx"), kind="environment_seed", ev="I")
        fx.set("content", seed.value)
        fx.evf["/content"] = "O"
        fx.loc({"a": seed.aid})
        fx.cite(self.R(R_SEED))
        fx.cite(self.R(R_SIBLINGS))
        return [fx.done()]

    # ---------------------------------------------------------------------------------------------- the stream
    def _stream(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        block = _Block()
        for line, event in self.events[1:]:
            ty = event.get("type")
            assistant = ty == "message" and event.get("role") == "assistant"
            if assistant or ty == "tool_use":
                block.items.append((line, event))
                continue
            if block.items:
                out += self._block(block)
                block = _Block()
            if ty == "message":
                out.append(self._user(line, event))
            elif ty == "tool_result":
                out += self._tool_result(line, event)
            elif ty == "error":
                out += self._notice(line, event)
            elif ty == "result":
                if line != self.events[-1][0]:
                    self.issue("geminicli.events_after_result", ["run"], R_LAST, severity="info")
            else:
                out += self._unmapped(line, event)
        if block.items:
            out += self._block(block)
        unanswered = [c.part for c in self.calls.values() if not c.answered]
        if unanswered:
            self.issue("missing_tool_result", unanswered, R_LINK)
            if self.result is not None:  # a run that ended with a result event yet left a call unanswered
                self.issue("incomplete_run", ["run"], R_LINK)
        return out

    def _user(self, line: int, event: Mapping[str, Any]) -> dict[str, Any]:
        self.user_messages += 1
        later = self.user_messages > 1
        rec = _Rec(k="message", id=self.next_id("m"), scope="att0", role="user", actor="user", ev="O")
        rec.data["parts"] = [{"t": "text", "text": rec.enc(event.get("content"), "/parts/0/text")}]
        rec.loc(self.loc(line, "/content"))
        rec.tag("/actor", "I", self.R(R_PROMPT, "/actor"))
        if later or event.get("role") != "user":
            self.issue("unattributed_additional_user_message", [rec.id], R_PROMPT, severity="info")
        self._stamp(rec, event)
        self._order(rec)
        self.messages.append(rec.id)
        self.prev = rec.id
        return rec.done()

    def _block(self, block: _Block) -> list[dict[str, Any]]:
        first_line = block.items[0][0]
        mc = _Rec(k="model_call", id=self.next_id("mc"), actor="agent", role="agent", scope="att0", status="kept", ev="I")
        mc.data["input"] = list(self.messages)
        mc.cite(self.R(R_BLOCK))
        mc.tag("/input", "I", self.R(R_CONTEXT, "/input"))
        mc.loc(self.loc(first_line))
        mc.unk.update({key: "not_recorded" for key in _MODEL_CALL_UNKNOWN})
        self._order(mc)
        self.prev = mc.id
        mid = self.next_id("m")
        rec = _Rec(k="message", id=mid, scope="att0", role="assistant", actor="agent", generated_by=mc.id, ev="O")
        parts: list[dict[str, Any]] = []
        chunks: list[list[Any]] = []
        calls: list[dict[str, Any]] = []
        text: list[str] = []
        text_lines: list[int] = []

        def close_text() -> None:
            if text:
                k = len(parts)
                parts.append({"t": "text", "text": rec.enc("".join(text), _p("parts", k, "text"))})
                rec.tag(_p("parts", k, "text"), "I", self.R(R_DELTAS, _p("parts", k, "text")))
                for n in text_lines:
                    rec.loc(self.loc(n, "/content"))
                text.clear()
                text_lines.clear()

        for line, event in block.items:
            if event.get("type") == "message":
                content = event.get("content")
                if not isinstance(content, str):
                    raise MalformedArtefact(f"line {line}: an assistant message without string content")
                text.append(content)
                text_lines.append(line)
                chunks.append([line, len(content), event.get("delta"), event.get("timestamp")])
                continue
            close_text()
            k = len(parts)
            name, args, tool_id = event.get("tool_name"), event.get("parameters"), event.get("tool_id")
            parts.append({"t": "tool_call", "name": rec.enc(name if isinstance(name, str) else str(name),
                                                            _p("parts", k, "name")),
                          "args": rec.enc(args, _p("parts", k, "args"))})  # fmt: skip
            rec.unk[_p("parts", k, "args_raw")] = "not_recorded"
            rec.unk[_p("parts", k, "provider_call_id")] = "not_recorded"
            rec.loc(self.loc(line))
            pid = part_id(mid, k)
            calls.append({"part": k, "tool_id": tool_id, "line": line, "timestamp": event.get("timestamp")})
            if isinstance(tool_id, str) and tool_id not in self.calls:
                self.calls[tool_id] = _Call(pid, mid, line, event)
            else:
                self.issue("call_result_link_conflict", [pid], R_LINK, detail="tool_id repeated or not a string")
        close_text()
        rec.data["parts"] = parts
        if chunks:
            rec.x("chunks", chunks)
        if calls:
            rec.x("calls", calls)
        rec.tag("/role", "I", self.R(R_BLOCK, "/role"))
        rec.tag("/actor", "I", self.R(R_BLOCK, "/actor"))
        rec.tag("/generated_by", "I", self.R(R_BLOCK, "/generated_by"))
        rec.edge(mc.id, "causal")
        rec.tag("/after", "I", self.R(R_GEN, "/after"))
        self.messages.append(mid)
        self.prev = mid
        return [mc.done(), rec.done()]

    def _tool_result(self, line: int, event: Mapping[str, Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        tool_id = event.get("tool_id")
        call = self.calls.get(tool_id) if isinstance(tool_id, str) else None
        if call is not None and call.answered:
            self.issue("call_result_link_conflict", [call.part], R_LINK, detail="a second result for the tool_id")
            call = None
        generator: str | None = None
        if call is not None:
            call.answered = True
            self.has_env = True
            use = call.event
            te = _Rec(k="tool_execution", id=self.next_id("te"), actor="env", scope="att0", ev="I", call=call.part)
            te.cite(self.R(R_EXEC))
            te.tag("/call", "I", self.R(R_LINK, "/call"))
            te.set("name", use.get("tool_name"))
            te.set("args", use.get("parameters"))
            te.evf.update({"/name": "O", "/args": "O"})
            te.loc(self.loc(call.line))
            te.loc(self.loc(line))
            status = event.get("status")
            if status in ("success", "error"):
                te.data["status"] = "ok" if status == "success" else "error"
                te.tag("/status", "D", self.R(R_TOOL_STATUS, "/status"))
            else:
                te.unk["/status"] = "ambiguous"
                te.cite(self.R(R_TOOL_STATUS, "/status"))
            if "error" in event:
                te.x("error", event["error"])
            raw = {k: v for k, v in (("start", use.get("timestamp")), ("end", event.get("timestamp"))) if isinstance(v, str)}
            if raw:
                te.data["t"] = {"raw": te.enc(raw, "/t/raw")}
                te.evf["/t/raw"] = "O"
                for k in raw:
                    te.unk[f"/t/{k}"] = "ambiguous"
                    te.cite(self.R(R_TIME, f"/t/{k}"))
            te.x("tool_id", tool_id)
            te.unk["/returned"] = "not_recorded"
            te.edge(call.message, "causal")
            te.tag("/after", "I", self.R(R_AFTER_CALL, "/after"))
            if self.prev is not None and self.prev != call.message:
                te.edge(self.prev, "pos")
                te.cite(self.R(R_ORDER, "/after"))
            out.append(te.done())
            self.prev = generator = te.id
            if use.get("tool_name") in _SUBAGENT_TOOLS:
                self.issue("geminicli.subagent_internals_unobserved", [te.id], R_SUBAGENT, severity="info")
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
            part["name"] = msg.enc(call.event.get("tool_name"), _p("parts", 0, "name"))
            msg.tag(_p("parts", 0, "name"), "I", self.R(R_LINK, _p("parts", 0, "name")))
        else:
            msg.unk[_p("parts", 0, "responds_to")] = "ambiguous"
            msg.unk["/generated_by"] = "ambiguous"
            msg.tag("/actor", "I", self.R(R_EXEC, "/actor"))
            self.issue("orphan_tool_result", [mid], R_LINK)
            self._order(msg)
        output = event.get("output")
        if isinstance(output, str):
            part["text"] = msg.enc(output, _p("parts", 0, "text"))
            msg.loc(self.loc(line, "/output"))
        else:  # no output field: the tool returned nothing or the CLI omitted it (ambiguous), never recorded as ""
            part["text"] = None
            msg.unk[_p("parts", 0, "text")] = "ambiguous"
            msg.cite(self.R(R_EXEC, _p("parts", 0, "text")))
            msg.loc(self.loc(line))
        msg.data["parts"] = [part]
        msg.x("tool_id", tool_id)
        self._stamp(msg, event)
        out.append(msg.done())
        self.messages.append(mid)
        self.prev = mid
        return out

    def _notice(self, line: int, event: Mapping[str, Any]) -> list[dict[str, Any]]:
        ac = _Rec(k="activity", id=self.next_id("ac"), type="geminicli:cli_notice", actor="harness", scope="att0", ev="I")
        ac.cite(self.R(R_NOTICE))
        ac.loc(self.loc(line))
        ac.unk["/inputs"] = "not_recorded"
        if "severity" in event:
            ac.x("severity", event["severity"])
        self._stamp(ac, event)
        self._order(ac)
        self.prev = ac.id
        af = _Rec(k="artefact", id=self.next_id("af"), type="geminicli:notice_text", generated_by=ac.id, ev="O")
        af.set("content", event.get("message"))
        af.loc(self.loc(line, "/message"))
        af.tag("/generated_by", "I", self.R(R_NOTICE, "/generated_by"))
        af.edge(ac.id, "causal")
        af.tag("/after", "I", self.R(R_GEN, "/after"))
        self.prev = af.id
        self.issue("geminicli.cli_notice", [ac.id], R_NOTICE, severity="info")
        return [ac.done(), af.done()]

    def _unmapped(self, line: int, event: Mapping[str, Any]) -> list[dict[str, Any]]:
        ac = _Rec(k="activity", id=self.next_id("ac"), type="geminicli:unmapped_event", actor="harness", scope="att0",
                  ev="I")
        ac.cite(self.R(R_UNMAPPED))
        ac.loc(self.loc(line))
        ac.unk["/inputs"] = "not_recorded"
        self._order(ac)
        self.prev = ac.id
        af = _Rec(k="artefact", id=self.next_id("af"), type="geminicli:event_payload", generated_by=ac.id, ev="O")
        af.set("content", dict(event))
        af.loc(self.loc(line))
        af.tag("/generated_by", "I", self.R(R_UNMAPPED, "/generated_by"))
        af.edge(ac.id, "causal")
        af.tag("/after", "I", self.R(R_GEN, "/after"))
        self.prev = af.id
        self.issue("geminicli.unmapped_event", [ac.id], R_UNMAPPED, detail=str(event.get("type"))[:40])
        return [ac.done(), af.done()]

    # ---------------------------------------------------------------------------------------------- judgements
    def _judgements(self) -> list[dict[str, Any]]:
        verdict = self.aux.get("verdict")
        if verdict is None or not isinstance(verdict.value, dict):
            self.issue("no_outcome_recorded", ["run"], R_DETECTOR, severity="info")
            return []
        out: list[dict[str, Any]] = []
        for name in JUDGEMENTS:
            if name not in verdict.value:
                continue
            rec = _Rec(k="judgement", id=self.next_id("j"), actor="detector", subject="run", name=name, ev="O",
                       by="benchmark")
            rec.set("value", verdict.value[name])
            rec.loc({"a": verdict.aid, "p": _p(name)})
            rec.data["origin"] = "checker"
            rec.tag("/origin", "I", self.R(R_DETECTOR, "/origin"))
            rec.tag("/subject", "I", self.R(R_DETECTOR, "/subject"))
            rec.unk.update({"/inputs": "not_recorded", "/t": "not_recorded"})
            out.append(rec.done())
        return out

    # ---------------------------------------------------------------------------------------------- checks
    def _checks(self) -> None:
        verdict, meta = self._value("verdict"), self._value("meta")
        if verdict and meta and (verdict.get("exit_code") != meta.get("exit_code")):
            self.issue("geminicli.verdict_meta_disagree", ["exec"], R_VERDICT_META, severity="info", detail="exit_code")
        self._manifest(verdict)
        used = sum(1 for _line, e in self.events if e.get("type") == "tool_use")
        answered = sum(1 for c in self.calls.values() if c.answered)
        subagent = any(e.get("tool_name") in _SUBAGENT_TOOLS for _line, e in self.events if e.get("type") == "tool_use")
        observed = {"tool_use": used, "tool_result_linked": answered}
        stats = _dict(self.result.get("stats")) if self.result is not None else {}
        reported = stats.get("tool_calls")
        if not _int(reported):
            self.ctx.check(R_COUNTERS, scope="att0", verdict="unverifiable", observed=observed,
                           reason="no_result_event" if self.result is None else "counters_not_recorded")
            return
        assert isinstance(reported, int)
        observed = {**observed, "reported_tool_calls": reported}
        if reported == used:
            self.ctx.check(R_COUNTERS, scope="att0", verdict="consistent", observed=observed)
        elif subagent:
            self.ctx.check(R_COUNTERS, scope="att0", verdict="unverifiable", observed=observed,
                           reason="subagent_calls_not_logged")
        else:
            self.ctx.check(R_COUNTERS, scope="att0", verdict="inconsistent", observed=observed,
                           reason="tool_calls_differ_from_stream")

    def _manifest(self, verdict: Mapping[str, Any]) -> None:
        """``geminicli.manifest_agrees@1`` (D-337): the manifest row of (model, mutation) against the verdict."""
        found = self.aux.get("manifest")
        if found is None or not isinstance(found.value, bytes) or not verdict:
            self.ext["manifest"] = {"status": "missing"}
            self.ext_tag("manifest", "D", R_MANIFEST)
            return
        try:
            text = found.value.decode("utf-8")
        except UnicodeDecodeError:
            self.ext["manifest"] = {"status": "unparseable"}
            self.ext_tag("manifest", "D", R_MANIFEST)
            return
        lines = text.replace("\r\n", "\n").split("\n")
        header = lines[0].split(",")
        row: dict[str, str] | None = None
        for line in lines[1:]:
            cells = line.split(",")
            if len(cells) != len(header):
                continue
            entry = dict(zip(header, cells, strict=True))
            if (entry.get("agent"), entry.get("model"), entry.get("mutation_id")) == (
                    self.f.scaffold, self.f.model, self.f.mutation):
                row = entry
                break
        if row is None:
            self.ext["manifest"] = {"status": "not_listed"}
            self.ext_tag("manifest", "D", R_MANIFEST)
            self.issue("geminicli.manifest_differs", ["exec"], R_MANIFEST, severity="info", detail="not_listed")
            return
        differs = []
        for name in _MANIFEST_FIELDS:
            value = verdict.get(name)
            written = str(int(value)) if isinstance(value, bool) else str(value)
            if row.get(name) != written:
                differs.append(name)
        self.ext["manifest"] = {"status": "differs" if differs else "agrees", **({"fields": differs} if differs else {})}
        self.ext_tag("manifest", "D", R_MANIFEST)
        if differs:
            self.issue("geminicli.manifest_differs", ["exec"], R_MANIFEST, severity="info", detail=",".join(differs))
