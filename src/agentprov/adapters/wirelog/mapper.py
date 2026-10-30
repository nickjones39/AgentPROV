"""Mapper ``wirelog.run_dir``: one run directory of a wire log -> AER ``aer/0.1`` (docs/architecture D.20.3-D.20.8;
DECISIONS D-281..D-284).

One response log is one execution (content-addressed id; a request log can repeat across trials, D-281 addendum). The
unit's auxiliary artefacts are the run directory's other files (``request``, ``meta``, ``dispatch``, ``outcome``,
``outcome_v2``, ``final_*``) and the deposit's tables (``results``, ``attacks``). What the mapper writes, in record order (backward references only, C.5.2):

1. the header: task coordinates (task id from the profile's prompt table, D; arm and context condition from the
   results table, O), ``ext.wirelog`` (label facets, ``meta.json`` and the results row verbatim);
2. actors ``bench``, ``harness``, ``user``, ``agent``, ``env`` (when a tool ran), ``att`` (an arm with an attack) and
   ``judge``;
3. scopes ``run`` (status from the last stop reason, I; the save timestamp kept raw) and ``att0``;
4. fixtures: the tool configuration (``tool_definitions``, O) and the arm's payload from ``attacks.json`` (join D);
5. per request *i*: the conversation items first seen in it (system prompt, task, and the tool results, each result
   block its own message preceded by the ``tool_execution`` it answers, D-281 c), then ``mc<i>`` whose ``input`` lists
   every item of request *i* in recorded order, then the assistant message of response *i*;
6. the judgements: the results table's columns (``checker``), ``outcome.txt`` (``harness_rule``) and ``outcome_v2.txt``
   (``recomputed``, revising it).

Identity across requests is by JCS equality (``wirelog.request_prefix@1``), the response-to-request link by the echo of
the response in the next request (``wirelog.response_echo@1``), and call-to-result links by provider call id
(``wirelog.call_id_unique_match@1``); position alone links nothing. No time but the save timestamp (kept raw) is used.

Pure (A-2): the output is a function of the unit's bytes, the auxiliary bytes, this code, the profile and the catalogues.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from agentprov.adapters.protocols import AerRecord, MappingContext
from agentprov.adapters.types import ArtefactRef, ExecutionUnit
from agentprov.adapters.wirelog import ADAPTER_ID, DIALECT_ID, VARIANT_ANTHROPIC, VARIANT_CONVERSE, VARIANTS
from agentprov.adapters.wirelog.dialect import SIBLINGS, LabelFacets, parse_label
from agentprov.adapters.wirelog.wire import (
    Block,
    WireMessage,
    WireRequest,
    WireResponse,
    echo_form,
    parse_requests,
    parse_responses,
)
from agentprov.aer.canon import LexHints, encode_value, json_pointer
from agentprov.aer.ids import part_id
from agentprov.errors import AgentProvError, IngestError, MalformedArtefact
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads
from agentprov.io.canonical import jcs_bytes

__all__ = ["ADAPTER_ID", "ADAPTER_VERSION", "CATALOGUES", "NAMESPACES", "WireLogMapper"]

ADAPTER_VERSION: Final = "0.1.0"
#: Catalogues this mapper cites; the header lists them at the shipped versions (C.3.1 ``rules``).
CATALOGUES: Final = ("aer", "wirelog")
NAMESPACES: Final = {"wirelog": "https://w3id.org/agentprov/ns/wirelog#"}
#: The order of the results-table judgements (verbatim column names).
JUDGED_COLUMNS: Final = ("hijack", "exfiltration", "silent", "call_order")

# rule ids (catalogue wirelog, version 1)
R_LAYOUT: Final = "wirelog.run_dir_layout@1"
R_PREFIX: Final = "wirelog.request_prefix@1"
R_ECHO: Final = "wirelog.response_echo@1"
R_LAST: Final = "wirelog.last_response_by_position_unverified@1"
R_CALL_ID: Final = "wirelog.call_id_unique_match@1"
R_SPLIT: Final = "wirelog.result_block_message@1"
R_NO_RESULT: Final = "wirelog.call_without_result@1"
R_TOOLS: Final = "wirelog.tool_config_stable@1"
R_AFTER_CONTEXT: Final = "wirelog.call_after_context@1"
R_LATENCY: Final = "wirelog.latency_no_clock@1"
R_UNKNOWN_BLOCK: Final = "wirelog.unknown_block@1"
R_HARNESS: Final = "wirelog.deposit_harness_unverified@1"
R_MODEL: Final = "wirelog.request_model_identity_unverified@1"
R_USER: Final = "wirelog.user_is_harness_task_unverified@1"
R_SYSTEM: Final = "wirelog.system_prompt_by_harness_unverified@1"
R_SYNTHETIC: Final = "wirelog.synthetic_tool_runtime_unverified@1"
R_DISPATCH: Final = "wirelog.dispatch_logged@1"
R_RUN_END: Final = "wirelog.run_end_unverified@1"
R_SAVE_TIME: Final = "wirelog.save_timestamp_unverified@1"
R_ATTACKER: Final = "wirelog.arm_attacker_unverified@1"
R_CLEAN: Final = "wirelog.clean_arm_unverified@1"
R_TASK: Final = "wirelog.task_prompt_table@1"
R_RESULTS: Final = "wirelog.results_row_join@1"
R_PAYLOAD: Final = "wirelog.payload_table@1"
R_LOCATED: Final = "wirelog.payload_located@1"
R_SCORES: Final = "wirelog.results_scored_unverified@1"
R_OUTCOME: Final = "wirelog.outcome_file_unverified@1"
R_RECLASSIFIED: Final = "wirelog.reclassified_unverified@1"
R_META_REWRITTEN: Final = "wirelog.meta_rewritten@1"
R_FINAL_ABSENT: Final = "wirelog.final_texts_not_logged@1"
R_TEXT_FILE: Final = "wirelog.text_file_utf8@1"
R_ACC_DISPATCH: Final = "wirelog.acc.dispatcher_log@1"
R_ACC_USAGE: Final = "wirelog.acc.usage_totals@1"
R_UNREADABLE: Final = "wirelog.unreadable_run@1"
R_ACC_HIJACK: Final = "wirelog.acc.recorded_hijack@1"
R_ACC_FINAL: Final = "wirelog.acc.final_text@1"
R_GEN: Final = "aer.output_after_generator@1"
R_AFTER_CALL: Final = "aer.execution_after_call@1"

_SHORT_VERSION: Final = re.compile(r"-v\d+:\d+$")
_SHORT_DATE: Final = re.compile(r"-\d{8}$")


def _p(*tokens: str | int) -> str:
    return json_pointer(*tokens)


def _jcs(value: object) -> bytes:
    return jcs_bytes(value)


def short_model(model: str) -> str:
    """The harness's short model name (its ``short()``): last dotted segment, without ``-vN:M`` and an 8-digit date."""
    return _SHORT_DATE.sub("", _SHORT_VERSION.sub("", model.split(".")[-1]))


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
        """``ext.wirelog.<key>`` (encoded)."""
        self.ext[key] = self.enc(value, _p("ext", "wirelog", key))

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
            ext["wirelog"] = dict(self.ext)
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
class _Call:
    """A ``tool_use`` block of a response: its part id and the source pointer of the block."""

    part: str
    message: str
    response: int
    pointer: str
    block: Block
    answered_by: str | None = None  # the tool_execution, once a result names it


class WireLogMapper:
    """``Mapper`` for ``wirelog.request_response`` (D.2.4, D.20)."""

    mapper_id: Final = ADAPTER_ID
    version: Final = ADAPTER_VERSION
    accepts: Final = frozenset((DIALECT_ID, v) for v in VARIANTS)
    namespaces: Final = NAMESPACES
    catalogues: Final = CATALOGUES

    def map(self, unit: ExecutionUnit, ctx: MappingContext) -> Iterator[AerRecord]:
        yield from _Build(unit, ctx).run()

    @staticmethod
    def prov_primary(flags: frozenset[str]) -> str:
        """Response logs are written by the producing harness: ``native``."""
        return "native"

    def degenerate_header(self, unit: ExecutionUnit, ctx: MappingContext, *, issue_code: str, detail: str) -> dict[str, Any]:
        """The header of a degenerate AER (D.2.8 case 3): a response log that cannot be mapped (refused by the strict
        loader, or a crashed or limited job) is one execution named by its label; nothing of the run is mapped."""
        artefact = unit.primary.artefact
        origin_key = next((k for k in ("label", "path") if isinstance(artefact.origin.data.get(k), str)), None)
        if origin_key is None:
            raise MalformedArtefact("the artefact's origin names no label: no run can be named")
        label = str(artefact.origin.data[origin_key])
        header: dict[str, Any] = {
            "k": "execution", "id": "exec", "aer": "0.1", "ex": ctx.ex, "mode": unit.mode, "unit": "agent_execution",
            "source_key": {"sha256": artefact.sha256, "loc": unit.primary.locator.key()},
            "artifacts": [artefact.to_json()], "adapter": {"id": ADAPTER_ID, "version": ADAPTER_VERSION},
            "dialect": {"id": DIALECT_ID, "variant": unit.primary.variant}, "profile": ctx.profile.header(),
            "rules": ctx.catalogue_versions(CATALOGUES), "ns": dict(NAMESPACES), "canon": "jcs-rfc8785", "hash": "sha256",
            "task": {"benchmark": str(ctx.profile.family_table().get("benchmark", "wirelog")), "task_id": f"run:{label}"},
            "ev": "O", "by": "source", "evf": {"/task/task_id": "D"}, "rule": [ctx.rule(R_UNREADABLE, "/task/task_id")],
            "unk": {"/instrumentation": "not_recorded", "/task/attack_id": "not_recorded"},
            "src": [{"a": "a0", "o": f"/{origin_key}"}],
        }
        ctx.issue(issue_code, ids=["exec"], rule=ctx.rule(R_UNREADABLE), severity="error", detail=detail)
        return header


def _facets_of(artefact: ArtefactRef) -> tuple[LabelFacets | None, str]:
    data = artefact.origin.data
    for key in ("label", "path"):
        value = data.get(key)
        if isinstance(value, str):
            return parse_label(value), key
    return None, "label"


class _Build:
    """One mapping run: every record is built in order, then emitted (backward references only)."""

    def __init__(self, unit: ExecutionUnit, ctx: MappingContext) -> None:
        self.unit, self.ctx = unit, ctx
        item = unit.primary
        self.variant = item.variant
        if self.variant not in VARIANTS:
            raise MalformedArtefact(f"unknown wire variant {self.variant!r}")
        facets, self.origin_key = _facets_of(item.artefact)
        if facets is None:
            raise MalformedArtefact("the artefact's label is outside the wire-log run-directory layout")
        self.f: LabelFacets = facets
        self.limits = IngestLimits()
        self.family = ctx.profile.family_table()
        self.counters: dict[str, int] = {}
        self.artifacts: list[dict[str, Any]] = [item.artefact.to_json()]
        self.aid: dict[str, str] = {}
        self.same_bytes: dict[str, str] = {}  # auxiliary role -> the artefact with the same bytes it shares
        self.raw: dict[str, bytes] = {}
        self.aid["response"] = "a0"  # the primary: the response log identifies the run (D-281 addendum)
        self.responses: list[WireResponse] = parse_responses(item.value, self.variant)
        self.requests: list[WireRequest] = parse_requests(self._json_aux("request", required=True), self.variant)
        meta = self._json_aux("meta", required=False)
        self.meta: dict[str, Any] = meta if isinstance(meta, dict) else {}
        self.row = self._results_row()
        self.attacks = self._json_aux("attacks", required=False)
        self.calls: dict[str, _Call] = {}  # call id -> the call (first occurrence)
        self.call_ids_repeated: set[str] = set()
        self.calls_by_response: dict[int, list[_Call]] = {}
        self.result_count: dict[str, int] = {}
        self.messages_ids: list[str] = []
        self.user_ids: set[str] = set()
        self.echo_ids: dict[int, str] = {}  # response index -> its assistant message
        self.executions = 0
        self.fixtures: list[dict[str, Any]] = []
        self.payload_missing: str | None = None

    # ---------------------------------------------------------------------------------------------- helpers
    def R(self, rule_id: str, pointer: str | None = None) -> str:  # noqa: N802 - mirrors MappingContext.rule
        return self.ctx.rule(rule_id, pointer)

    def issue(self, code: str, ids: Sequence[str], rule: str, *, severity: str = "warning", detail: str | None = None) -> None:
        self.ctx.issue(code, ids=list(ids), rule=self.R(rule), severity=severity, detail=detail)  # type: ignore[arg-type]

    def next_id(self, prefix: str) -> str:
        n = self.counters.get(prefix, 0)
        self.counters[prefix] = n + 1
        return f"{prefix}{n}"

    def rq(self, pointer: str) -> dict[str, Any]:
        """A locator into the request log."""
        return {"a": self.aid["request"], "p": pointer}

    def at(self, role: str, pointer: str | None = None) -> dict[str, Any]:
        out: dict[str, Any] = {"a": self.aid[role]}
        if pointer is not None:
            out["p"] = pointer
        return out

    def _aux(self, role: str) -> bytes | None:
        """The bytes of auxiliary ``role`` (checked against its digest) and its artefact entry, or ``None`` if absent."""
        if role in self.raw:
            return self.raw[role]
        ref = self.unit.auxiliary.get(role)
        if ref is None:
            return None
        try:
            data = self.ctx.open_auxiliary(role)
        except AgentProvError:
            return None
        if len(data) != ref.bytes or hashlib.sha256(data).hexdigest() != ref.sha256:
            raise MalformedArtefact(f"the {role} auxiliary does not match its digest")
        same = next((a["id"] for a in self.artifacts if a["sha256"] == ref.sha256), None)
        if same is not None:  # byte-identical files (an empty final text, an unchanged outcome) are one raw artefact
            self.aid[role] = str(same)
            self.same_bytes[role] = str(same)
        else:
            self.aid[role] = f"a{len(self.artifacts)}"
            self.artifacts.append({**ref.to_json(), "id": self.aid[role], "role": "supporting", "prov_primary": "native"})
        self.raw[role] = data
        return data

    def _json_aux(self, role: str, *, required: bool) -> Any:
        data = self._aux(role)
        if data is None:
            if required:
                raise MalformedArtefact(f"the run directory has no {SIBLINGS.get(role, role)}")
            return None
        try:
            return strict_json_loads(data, self.limits)
        except IngestError as exc:
            if required:
                raise MalformedArtefact(f"the {role} auxiliary is not valid JSON ({exc.code})") from None
            self.issue("wirelog.unreadable_auxiliary", ["exec"], R_TEXT_FILE, detail=role)
            return None

    def _text_aux(self, role: str) -> str | None:
        data = self._aux(role)
        if data is None:
            return None
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            self.issue("wirelog.unreadable_auxiliary", ["exec"], R_TEXT_FILE, detail=role)
            return None

    def _results_row(self) -> dict[str, str] | None:
        text = self._text_aux("results")
        if text is None:
            return None
        rows = [r for r in csv.DictReader(io.StringIO(text, newline="")) if r.get("run_id") == self.f.run_dir]
        if len(rows) != 1:
            self.issue("wirelog.results_row_missing", ["exec"], R_RESULTS, severity="info",
                       detail="missing" if not rows else "repeated")
            return None
        return {k: v for k, v in rows[0].items() if isinstance(k, str)}

    # ---------------------------------------------------------------------------------------------- run
    def run(self) -> Iterator[dict[str, Any]]:
        if len(self.requests) != len(self.responses):
            raise MalformedArtefact("the request and response logs differ in length")
        self.arm = self.row.get("arm") if self.row is not None else self.f.arm
        self.no_attack = self.arm in set(self.family.get("no_attack_arms", ()))
        self.task_id, self.task_listed = self._task_id()
        body: list[dict[str, Any]] = []
        conversation = self._conversation()  # builds self.env_needed etc.; records emitted after the fixtures
        body += self._actors()
        body += self._scopes()
        body += self.fixtures
        body += conversation
        body += self._judgements()
        self._checks()
        self._header_issues()
        yield self._header()
        yield from body

    # ---------------------------------------------------------------------------------------------- header
    def _task_id(self) -> tuple[str, bool]:
        first = next((b.text for m in self.requests[0].messages[:1] for b in m.blocks if b.kind == "text"), None)
        digest = hashlib.sha256((first or "").encode("utf-8")).hexdigest()
        for row in self.family.get("tasks", ()):
            if row.get("sha256") == digest:
                return str(row["id"]), True
        return f"sha256:{digest}", False

    def _header(self) -> dict[str, Any]:
        task: dict[str, Any] = {"benchmark": str(self.family.get("benchmark", "wirelog")), "task_id": self.task_id}
        evf: dict[str, str] = {"/task/task_id": "D"}
        rules = [self.R(R_TASK, "/task/task_id")]
        src = [self.rq(_p(0, "messages", 0))]
        unk = {"/instrumentation": "not_recorded", "/task/defense_id": "not_recorded"}
        if self.row is not None:
            src.append(self.at("results"))
            condition = self.row.get("context_condition")
            if condition and condition.lower() != "none":
                task["environment"] = condition
                evf["/task/environment"] = "O:benchmark"
            else:  # "none": the run has no context condition (the value stays verbatim in ext.wirelog.results_row)
                unk["/task/environment"] = "not_applicable" if condition else "not_recorded"
                rules.append(self.R(R_RESULTS, "/task/environment"))
        else:
            src.append({"a": "a0", "o": f"/{self.origin_key}"})  # the arm from the run directory's name
            unk["/task/environment"] = "not_recorded"
        if self.no_attack:
            task["attack_id"] = None
            evf["/task/attack_id"] = "I"
            rules.append(self.R(R_CLEAN, "/task/attack_id"))
        else:
            task["attack_id"] = self.arm
            if self.row is not None:
                evf["/task/attack_id"] = "O:benchmark"
        header: dict[str, Any] = {
            "k": "execution",
            "id": "exec",
            "aer": "0.1",
            "ex": self.ctx.ex,
            "mode": self.unit.mode,
            "unit": "agent_execution",
            "source_key": {"sha256": self.unit.primary.artefact.sha256, "loc": self.unit.primary.locator.key()},
            "artifacts": self.artifacts,
            "adapter": {"id": ADAPTER_ID, "version": ADAPTER_VERSION},
            "dialect": {"id": DIALECT_ID, "variant": self.variant},
            "profile": self.ctx.profile.header(),
            "rules": self.ctx.catalogue_versions(CATALOGUES),
            "ns": dict(NAMESPACES),
            "canon": "jcs-rfc8785",
            "hash": "sha256",
            "task": task,
            "ev": "O",
            "by": "source",
            "unk": unk,
            "src": src,
        }
        ext: dict[str, Any] = {"label_facets": self.f.to_json()}
        if self.meta:
            ext["meta"] = self.meta
        if self.row is not None:
            ext["results_row"] = self.row
        if self.same_bytes:
            ext["same_bytes"] = dict(sorted(self.same_bytes.items()))
        if not self.task_listed:
            ext["task_prompt_sha256"] = self.task_id.removeprefix("sha256:")
        lex = LexHints()
        header["ext"] = {"wirelog": encode_value(ext, at="/ext/wirelog", lex=lex)}
        hints = lex.as_dict()
        if hints:
            header["ext"]["lex"] = hints
        evf["/ext/wirelog/label_facets"] = "D"  # parsed from the member label and compared (wirelog.run_dir_layout@1)
        rules.append(self.R(R_LAYOUT, "/ext/wirelog/label_facets"))
        header["evf"] = evf
        header["rule"] = rules
        return header

    def _header_issues(self) -> None:
        if not self.task_listed:
            self.issue("wirelog.task_prompt_unlisted", ["exec"], R_TASK, severity="info")
        model = self.requests[0].model
        mismatches = []
        if isinstance(model, str) and short_model(model) != self.f.model:
            mismatches.append("model")
        if self.meta:
            if self.meta.get("run_id") != self.f.run_dir:
                mismatches.append("run_id")
            if self.meta.get("model") != model:
                mismatches.append("meta_model")
            arm = self.meta.get("attack", self.meta.get("variant"))
            if arm != self.f.arm:
                mismatches.append("arm")
        if self.row is not None and self.row.get("arm") != self.f.arm:
            mismatches.append("results_arm")
        for name in mismatches:
            self.issue("wirelog.label_field_mismatch", ["exec"], R_LAYOUT, severity="info", detail=name)
        if "source_dir" in self.meta:
            self.issue("wirelog.meta_rewritten", ["exec"], R_META_REWRITTEN, severity="info")
        if "final_user_text" not in self.unit.auxiliary and "final_reasoning" not in self.unit.auxiliary:
            self.issue("wirelog.final_texts_not_logged", ["exec"], R_FINAL_ABSENT, severity="info")

    # ---------------------------------------------------------------------------------------------- actors and scopes
    def _actors(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        bench = _Rec(k="actor", id="bench", kind="benchmark", name=str(self.family.get("benchmark", "wirelog")), ev="I")
        bench.cite(self.R(R_HARNESS))
        bench.unk.update({"/code": "not_recorded", "/version": "not_recorded"})
        out.append(bench.done())
        harness = _Rec(k="actor", id="harness", kind="harness", name=str(self.family.get("harness", "harness")), ev="I")
        harness.cite(self.R(R_HARNESS))
        harness.unk.update({"/code": "not_recorded", "/version": "not_recorded"})
        out.append(harness.done())
        user = _Rec(k="actor", id="user", kind="simulated_user", name="task prompt", ev="I")
        user.cite(self.R(R_USER))
        out.append(user.done())
        model = self.requests[0].model
        agent = _Rec(k="actor", id="agent", kind="llm_agent", ev="O", on_behalf_of="user")
        agent.set("name", model)
        agent.loc(self.rq(_p(0, "model")))
        agent.data["model"] = {"requested": agent.enc(model, "/model/requested")}
        provider = self.family.get("provider")
        if isinstance(provider, str):
            agent.data["model"]["provider"] = provider
            agent.tag("/model/provider", "I", self.R(R_MODEL, "/model/provider"))
        agent.tag("/on_behalf_of", "I", self.R(R_USER, "/on_behalf_of"))
        agent.unk.update({"/model/served": "not_recorded", "/params": "not_recorded"})
        out.append(agent.done())
        if self.executions:
            env = _Rec(k="actor", id="env", kind="tool_runtime", name=str(self.family.get("tool_runtime", "dispatcher")),
                       on_behalf_of="agent", ev="I")
            env.cite(self.R(R_SYNTHETIC))
            env.x("synthetic", bool(self.family.get("synthetic_tools", False)))
            env.tag("/ext/wirelog/synthetic", "I", self.R(R_SYNTHETIC, "/ext/wirelog/synthetic"))
            out.append(env.done())
        if not self.no_attack:
            att = _Rec(k="actor", id="att", kind="attacker", name=str(self.arm), ev="I")
            att.cite(self.R(R_ATTACKER))
            if self.row is not None:
                att.loc(self.at("results"))
            else:
                att.loc({"a": "a0", "o": f"/{self.origin_key}"})
            out.append(att.done())
        judge = _Rec(k="actor", id="judge", kind="judge", name=str(self.family.get("scorer", "scorer")), ev="I")
        judge.cite(self.R(R_SCORES))
        judge.unk.update({"/code": "not_recorded", "/model": "not_recorded"})
        out.append(judge.done())
        return out

    def _scopes(self) -> list[dict[str, Any]]:
        run = _Rec(k="scope", id="run", kind="run", ev="O")
        run.loc(self.rq(""))
        last = self.responses[-1]
        cap = self.family.get("max_requests")
        if last.stop_reason == self.family.get("final_stop_reason", "end_turn"):
            run.data["status"] = "ok"
            run.tag("/status", "I", self.R(R_RUN_END, "/status"))
            run.loc(self.at("response", _p(last.index)))
        elif isinstance(cap, int) and len(self.requests) >= cap:
            run.data["status"] = "limit"
            run.tag("/status", "I", self.R(R_RUN_END, "/status"))
            self.issue("wirelog.turn_limit", ["run"], R_RUN_END)
            self.issue("incomplete_run", ["run"], R_RUN_END)
        else:
            run.unk["/status"] = "ambiguous"
            run.cite(self.R(R_RUN_END, "/status"))
        stamp = self.meta.get("timestamp")
        if isinstance(stamp, str):
            run.data["t"] = {"raw": {"end": run.enc(stamp, "/t/raw/end")}}
            run.tag("/t/raw", "O")
            run.loc(self.at("meta", "/timestamp"))
            run.unk.update({"/t/end": "ambiguous", "/t/start": "not_recorded"})
            run.cite(self.R(R_SAVE_TIME, "/t/end"))
        else:
            run.unk["/t"] = "not_recorded"
        out = [run.done()]
        att = _Rec(k="scope", id="att0", kind="attempt", parent="run", actor="agent", ev="O")
        att.loc(self.rq(""))
        att.unk.update({"/index": "not_recorded", "/scored": "not_recorded"})
        out.append(att.done())
        return out

    # ---------------------------------------------------------------------------------------------- fixtures
    def _tools_fixture(self, i: int, rq: WireRequest) -> dict[str, Any]:
        fx = _Rec(k="fixture", id=self.next_id("fx"), kind="tool_definitions", ev="O")
        fx.set("content", rq.tools)
        fx.loc(self.rq(_p(i, str(rq.tools_key))))
        return fx.done()

    def _payload_fixture(self) -> dict[str, Any] | None:
        if self.no_attack or self.arm in set(self.family.get("code_only_payload_arms", ())):
            return None  # no payload, or one that exists only in the harness code (SEM recognises its document)
        key = dict(self.family.get("payloads", {})).get(str(self.arm))
        table = self.attacks.get("retargeted_payloads") if isinstance(self.attacks, dict) else None
        if not isinstance(key, str) or not isinstance(table, dict) or not isinstance(table.get(key), str):
            self.issue("wirelog.payload_entry_missing", ["exec"], R_PAYLOAD, severity="info",
                       detail="no_table_entry" if not isinstance(key, str) else "not_in_attacks_json")
            return None
        payload = table[key]
        fx = _Rec(k="fixture", id=self.next_id("fx"), kind="injection_payload", actor="att", ev="D")
        fx.set("content", payload)
        fx.tag("/content", "O:benchmark")
        fx.tag("/actor", "I", self.R(R_ATTACKER, "/actor"))
        fx.cite(self.R(R_PAYLOAD))
        fx.loc(self.at("attacks", _p("retargeted_payloads", key)))
        if self.row is not None and self.row.get("channel"):
            fx.set("vector", self.row["channel"])
            fx.tag("/vector", "O:benchmark")
            fx.loc(self.at("results"))
        fx.x("payload_key", key)
        found = self._locate(payload)
        if found is None:
            self.payload_missing = fx.id
        else:
            fx.x("found_in", found)
            fx.tag("/ext/wirelog/found_in", "D", self.R(R_LOCATED, "/ext/wirelog/found_in"))
        return fx.done()

    def _locate(self, payload: str) -> dict[str, Any] | None:
        """The first place the request log carries ``payload`` verbatim: the tool configuration of a request, else a tool
        result block, in request order; the pointer names the string and ``offset`` the character offset in it."""
        for i, rq in enumerate(self.requests):
            if rq.tools_key is not None:
                hit = _find_string(rq.tools, payload, _p(i, rq.tools_key))
                if hit is not None:
                    return {"channel": "tool_definitions", "request": i, "pointer": hit[0], "offset": hit[1]}
            for k, m in enumerate(rq.messages):
                for b in m.blocks:
                    if b.kind == "tool_result":
                        hit = _find_string(b.content, payload, _p(i, "messages", k) + b.pointer + _content_suffix(self.variant))
                        if hit is not None:
                            return {"channel": "tool_result", "request": i, "pointer": hit[0], "offset": hit[1]}
        return None

    # ---------------------------------------------------------------------------------------------- conversation
    def _conversation(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        tools_fx: tuple[bytes, str] | None = None
        system: tuple[bytes, str] | None = None
        prev_items: list[tuple[bytes, list[str]]] = []
        for i, rq in enumerate(self.requests):
            reused = False
            input_ids: list[str] = []
            # tool configuration
            tools_id: str | None = None
            if rq.tools_key is not None:
                canon = _jcs(rq.tools)
                if tools_fx is not None and tools_fx[0] == canon:
                    tools_id = tools_fx[1]
                else:
                    if tools_fx is not None:
                        self.issue("wirelog.context_diverges", ["exec"], R_TOOLS, detail=f"tools@{i}")
                    rec = self._tools_fixture(i, rq)
                    (self.fixtures if tools_fx is None else out).append(rec)
                    tools_id = rec["id"]
                    tools_fx = (canon, tools_id)
            # system prompt
            if rq.system is not None:
                canon = _jcs(rq.system)
                if system is not None and system[0] == canon:
                    input_ids.append(system[1])
                    reused = True
                else:
                    if system is not None:
                        self.issue("wirelog.context_diverges", ["exec"], R_PREFIX, detail=f"system@{i}")
                    rec = self._system_message(i, rq)
                    out.append(rec)
                    system = (canon, rec["id"])
                    input_ids.append(rec["id"])
            elif system is not None:
                self.issue("wirelog.context_diverges", ["exec"], R_PREFIX, detail=f"system_dropped@{i}")
            # messages
            expected = list(prev_items)
            if i > 0:
                echo = self.echo_ids.get(i - 1)
                expected.append((_jcs(echo_form(self.responses[i - 1], self.variant)), [echo] if echo else []))
            items: list[tuple[bytes, list[str]]] = []
            for k, wm in enumerate(rq.messages):
                canon = _jcs(wm.raw)
                if k < len(expected) and expected[k][0] == canon and expected[k][1]:
                    ids = expected[k][1]
                    reused = True
                else:
                    if k < len(expected):
                        self.issue("wirelog.context_diverges", ["exec"], R_PREFIX, detail=f"messages@{i}/{k}")
                    records, ids = self._new_item(i, k, wm)
                    out += records
                items.append((canon, ids))
                input_ids += ids
            prev_items = items
            out += self._model_call(i, rq, input_ids, tools_id, reused)
        # calls that no later request answered
        unanswered = [c.part for c in self.calls.values() if c.answered_by is None]
        if unanswered:
            self.issue("unexecuted_tool_call", unanswered, R_NO_RESULT)
        payload = self._payload_fixture()
        if payload is not None:
            self.fixtures.append(payload)
        if self.payload_missing is not None:
            self.issue("wirelog.payload_not_delivered", [self.payload_missing], R_LOCATED, severity="info")
        return out

    def _system_message(self, i: int, rq: WireRequest) -> dict[str, Any]:
        mid = self.next_id("m")
        msg = _Rec(k="message", id=mid, scope="att0", role="system", actor="harness", ev="O")
        if rq.system_texts is not None:
            msg.data["parts"] = [{"t": "text", "text": msg.enc(t, _p("parts", k, "text"))} for k, t in enumerate(rq.system_texts)]
        else:
            msg.data["parts"] = [{"t": "other", "type": "wirelog.system", "value": msg.enc(rq.system, _p("parts", 0, "value"))}]
        msg.loc(self.rq(_p(i, "system")))
        msg.tag("/actor", "I", self.R(R_SYSTEM, "/actor"))
        msg.x("wire_field", "system")
        self.messages_ids.append(mid)
        return msg.done()

    def _parts(self, rec: _Rec, wm: WireMessage, base: str) -> list[dict[str, Any]]:
        """The AER parts of a text or assistant message (no tool results)."""
        parts: list[dict[str, Any]] = []
        extras: dict[str, Any] = {}
        for b in wm.blocks:
            k = len(parts)
            if b.kind == "text":
                parts.append({"t": "text", "text": rec.enc(b.text, _p("parts", k, "text"))})
            elif b.kind == "tool_use":
                parts.append({"t": "tool_call", "name": rec.enc(b.name, _p("parts", k, "name")),
                              "args": rec.enc(b.input, _p("parts", k, "args")),
                              "provider_call_id": rec.enc(b.call_id, _p("parts", k, "provider_call_id"))})
            else:
                parts.append({"t": "other", "type": str(b.type), "value": rec.enc(b.raw, _p("parts", k, "value"))})
                self.issue("wirelog.unknown_block", [part_id(rec.id, k)], R_UNKNOWN_BLOCK, severity="info",
                           detail=str(b.type)[:40])
            if b.extra:
                extras[str(k)] = dict(b.extra)
        if extras:
            rec.x("block_extra", extras)
        if wm.string_content:
            rec.x("string_content", True)
        return parts

    def _new_item(self, i: int, k: int, wm: WireMessage) -> tuple[list[dict[str, Any]], list[str]]:
        """Records for a conversation item first seen in request ``i`` at position ``k``: result blocks become one message
        each (preceded by the execution they answer), other blocks one message."""
        base = _p(i, "messages", k)
        out: list[dict[str, Any]] = []
        ids: list[str] = []
        results = [b for b in wm.blocks if b.kind == "tool_result"]
        others = [b for b in wm.blocks if b.kind != "tool_result"]
        if others or not results:
            mid = self.next_id("m")
            role = wm.role
            msg = _Rec(k="message", id=mid, scope="att0", role=role, ev="O")
            plain = WireMessage(role, tuple(others), wm.raw, wm.string_content)
            msg.data["parts"] = self._parts(msg, plain, base)
            msg.loc(self.rq(base))
            if role == "user":
                msg.data["actor"] = "user"
                msg.tag("/actor", "I", self.R(R_USER, "/actor"))
                if self.user_ids:
                    self.issue("unattributed_additional_user_message", [mid], R_USER)
                self.user_ids.add(mid)
            else:
                msg.unk["/actor"] = "ambiguous"
                msg.cite(self.R(R_PREFIX, "/actor"))
                self.issue("wirelog.context_diverges", [mid], R_PREFIX, detail=f"unechoed_{str(role)[:20]}@{i}/{k}")
            if results:
                msg.x("wire_message", {"request": i, "index": k, "blocks": len(wm.blocks)})
                msg.tag("/ext/wirelog/wire_message", "D", self.R(R_SPLIT, "/ext/wirelog/wire_message"))
            self.messages_ids.append(mid)
            out.append(msg.done())
            ids.append(mid)
        for b in results:
            records, mid = self._result(i, k, wm, b)
            out += records
            ids.append(mid)
        return out, ids

    def _result(self, i: int, k: int, wm: WireMessage, b: Block) -> tuple[list[dict[str, Any]], str]:
        out: list[dict[str, Any]] = []
        base = _p(i, "messages", k) + b.pointer
        call_id = b.call_id
        call = self.calls.get(call_id) if isinstance(call_id, str) and call_id not in self.call_ids_repeated else None
        if call is not None and call.response != i - 1:
            call = None  # a result answers a call of the immediately preceding response only (C.5.4)
        conflict = call is not None and call.answered_by is not None
        mid = self.next_id("m")
        msg = _Rec(k="message", id=mid, scope="att0", role=wm.role, ev="O")
        part: dict[str, Any] = {"t": "tool_result"}
        if call is not None and not conflict:
            te = self._execution(i, call, base)
            out.append(te)
            call.answered_by = te["id"]
            msg.data["actor"] = "env"
            msg.tag("/actor", "I", self.R(R_SYNTHETIC, "/actor"))
            msg.data["generated_by"] = te["id"]
            msg.tag("/generated_by", "D", self.R(R_CALL_ID, "/generated_by"))
            part["responds_to"] = call.part
            msg.tag("/parts/0/responds_to", "D", self.R(R_CALL_ID, "/parts/0/responds_to"))
            msg.edge(te["id"], "causal")
            msg.tag("/after", "D", self.R(R_GEN, "/after"))
        else:
            msg.unk.update({"/actor": "ambiguous", "/generated_by": "not_recorded", "/parts/0/responds_to": "ambiguous"})
            msg.cite(self.R(R_CALL_ID, "/parts/0/responds_to"))
            if conflict:
                assert call is not None
                self.issue("call_result_link_conflict", [call.part, mid], R_CALL_ID, detail="answered_twice")
            else:
                self.issue("orphan_tool_result", [mid], R_CALL_ID)
        content = b.content
        single = _single_text(content, self.variant)
        if single is not None:
            part["text"] = msg.enc(single, "/parts/0/text")
        else:
            part["value"] = msg.enc(content, "/parts/0/value")
        msg.data["parts"] = [part]
        if b.extra:
            msg.x("block_extra", {"0": dict(b.extra)})
        msg.loc(self.rq(base))
        msg.x("wire_message", {"request": i, "index": k, "block": int(b.pointer.rsplit("/", 1)[1]), "blocks": len(wm.blocks)})
        msg.tag("/ext/wirelog/wire_message", "D", self.R(R_SPLIT, "/ext/wirelog/wire_message"))
        self.messages_ids.append(mid)
        out.append(msg.done())
        return out, mid

    def _execution(self, i: int, call: _Call, result_pointer: str) -> dict[str, Any]:
        te = _Rec(k="tool_execution", id=self.next_id("te"), actor="env", scope="att0", ev="O")
        self.executions += 1
        te.data["call"] = call.part
        te.tag("/call", "D", self.R(R_CALL_ID, "/call"))
        te.set("name", call.block.name)
        te.set("args", call.block.input)
        te.loc(self.at("response", _p(call.response) + self._response_message_pointer(call.response) + call.block.pointer))
        te.loc(self.rq(result_pointer))
        if "dispatch" in self.unit.auxiliary and self._aux("dispatch") is not None:
            te.loc(self.at("dispatch"))
        te.cite(self.R(R_DISPATCH))
        te.unk.update({"/returned": "not_recorded", "/status": "not_recorded", "/t": "not_recorded"})
        te.edge(call.message, "causal")
        te.tag("/after", "D", self.R(R_AFTER_CALL, "/after"))
        return te.done()

    def _response_message_pointer(self, index: int) -> str:
        return self.responses[index].message_pointer

    def _model_call(self, i: int, rq: WireRequest, input_ids: list[str], tools_id: str | None,
                    reused: bool) -> list[dict[str, Any]]:
        rs = self.responses[i]
        mc = _Rec(k="model_call", id=self.next_id("mc"), actor="agent", role="agent", scope="att0", ev="O")
        mc.data["input"] = list(input_ids)
        if reused:
            mc.tag("/input", "D", self.R(R_PREFIX, "/input"))
        if tools_id is not None:
            mc.data["tools"] = tools_id
            if i > 0:
                mc.tag("/tools", "D", self.R(R_TOOLS, "/tools"))
        else:
            mc.unk["/tools"] = "not_recorded"
        if rq.params:
            mc.data["params"] = {"transmitted": mc.enc(dict(rq.params), "/params/transmitted")}
        if rs.stop_reason is not None:
            mc.set("finish_reason", rs.stop_reason)
            mc.tag("/finish_reason", "O:provider")
        else:
            mc.unk["/finish_reason"] = "not_recorded"
        if rs.usage:
            mc.data["usage"] = {k: mc.enc(v, _p("usage", k)) for k, v in rs.usage.items()}
            mc.tag("/usage", "O:provider")
        else:
            mc.unk["/usage"] = "not_recorded"
        if isinstance(rs.served_model, str):
            mc.set("served_model", rs.served_model)
            mc.tag("/served_model", "O:provider")
        else:
            mc.unk["/served_model"] = "not_recorded"
        if isinstance(rs.response_id, str):
            mc.set("response_id", rs.response_id)
            mc.tag("/response_id", "O:provider")
        if rs.usage_extra:
            mc.x("usage_extra", dict(rs.usage_extra))
        if rs.extra:
            mc.x("response_extra", dict(rs.extra))
        if rq.extra:
            mc.x("request_extra", dict(rq.extra))
        echoed = i + 1 < len(self.requests) and rs.message is not None and \
            _echoes(self.requests[i + 1], len(rq.messages), rs, self.variant)
        if rs.message is None:
            mc.data["status"] = "error"
            mc.tag("/status", "I", self.R(R_LAST, "/status"))
        else:
            mc.data["status"] = "kept"
            mc.tag("/status", "D" if echoed else "I", self.R(R_ECHO if echoed else R_LAST, "/status"))
        mc.unk.update({"/request": "not_recorded", "/response": "not_recorded"})
        if rs.latency_ms is not None:
            mc.x("latency_ms", rs.latency_ms)
            mc.unk.update({"/t/start": "not_recorded", "/t/end": "not_recorded", "/t/dur_s": "ambiguous"})
            mc.cite(self.R(R_LATENCY, "/t/dur_s"))
        else:
            mc.unk["/t"] = "not_recorded"
        mc.loc(self.rq(_p(i)))
        mc.loc(self.at("response", _p(i)))
        if input_ids:
            mc.edge(input_ids[-1], "causal")
            mc.tag("/after", "D", self.R(R_AFTER_CONTEXT, "/after"))
        out = [mc.done()]
        if rs.message is None:
            return out
        mid = self.next_id("m")
        msg = _Rec(k="message", id=mid, scope="att0", role=rs.message.role, actor="agent", generated_by=mc.id, ev="O")
        msg.data["parts"] = self._parts(msg, rs.message, rs.message_pointer)
        msg.loc(self.at("response", _p(i) + rs.message_pointer))
        if echoed:
            msg.loc(self.rq(_p(i + 1, "messages", len(self.requests[i].messages))))
            msg.tag("/generated_by", "D", self.R(R_ECHO, "/generated_by"))
        else:
            msg.tag("/generated_by", "I", self.R(R_LAST, "/generated_by"))
            if "final_message" in self.unit.auxiliary and self._aux("final_message") is not None:
                msg.loc(self.at("final_message"))
        msg.edge(mc.id, "causal")
        msg.tag("/after", "D", self.R(R_GEN, "/after"))
        self.echo_ids[i] = mid
        self.messages_ids.append(mid)
        calls: list[_Call] = []
        for k, b in enumerate(rs.message.blocks):
            if b.kind != "tool_use":
                continue
            call = _Call(part_id(mid, k), mid, i, b.pointer, b)
            calls.append(call)
            if not isinstance(b.call_id, str) or b.call_id in self.calls:
                if isinstance(b.call_id, str):
                    self.call_ids_repeated.add(b.call_id)
                self.issue("call_result_link_conflict", [call.part], R_CALL_ID, detail="call_id_not_unique")
                continue
            self.calls[b.call_id] = call
        self.calls_by_response[i] = calls
        out.append(msg.done())
        return out

    # ---------------------------------------------------------------------------------------------- judgements
    def _judgements(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if self.row is not None:
            for name in JUDGED_COLUMNS:
                if name not in self.row:
                    continue
                rec = _Rec(k="judgement", id=self.next_id("j"), actor="judge", subject="run", name=name, ev="O",
                           by="benchmark")
                rec.set("value", self.row[name])
                rec.loc(self.at("results"))
                if name == "silent":
                    for role in ("final_user_text", "final_reasoning"):
                        if role in self.unit.auxiliary and self._aux(role) is not None:
                            rec.loc(self.at(role))
                rec.data["origin"] = "checker"
                rec.tag("/origin", "I", self.R(R_SCORES, "/origin"))
                rec.unk.update({"/inputs": "not_recorded", "/t": "not_recorded"})
                out.append(rec.done())
        outcome_id: str | None = None
        for role, name, origin, rule in (("outcome", "outcome", "harness_rule", R_OUTCOME),
                                         ("outcome_v2", "outcome_v2", "recomputed", R_RECLASSIFIED)):
            text = self._text_aux(role)
            if text is None:
                continue
            rec = _Rec(k="judgement", id=self.next_id("j"), actor="judge", subject="run", name=name, ev="O")
            rec.set("value", text)
            rec.loc(self.at(role))
            rec.data["origin"] = origin
            rec.tag("/origin", "I", self.R(rule, "/origin"))
            if role == "outcome_v2" and outcome_id is not None:
                rec.data["revises"] = outcome_id
                rec.tag("/revises", "I", self.R(R_RECLASSIFIED, "/revises"))
            rec.unk.update({"/inputs": "not_recorded", "/t": "not_recorded"})
            out.append(rec.done())
            if role == "outcome":
                outcome_id = rec.id
        if not out:
            self.ctx.issue("no_outcome_recorded", ids=["run"], rule=self.R(R_RESULTS), severity="info")
        return out

    # ---------------------------------------------------------------------------------------------- checks
    def _checks(self) -> None:
        calls = [c.block for i in sorted(self.calls_by_response) for c in self.calls_by_response[i]]
        # dispatcher log: one line "<name> <JSON input, sorted keys>" per call (written in text mode: LF as CRLF)
        log = self._text_aux("dispatch")
        if log is None:
            self.ctx.check(R_ACC_DISPATCH, scope="att0", verdict="unverifiable", observed={"tool_calls": len(calls)},
                           reason="dispatcher_log_not_recorded")
        else:
            lines = [ln for ln in log.replace("\r\n", "\n").split("\n") if ln]
            expected = [f"{b.name} {json.dumps(b.input, sort_keys=True)}" for b in calls]
            ok = lines == expected
            self.ctx.check(R_ACC_DISPATCH, scope="att0", verdict="consistent" if ok else "inconsistent",
                           observed={"tool_calls": len(calls), "log_lines": len(lines)},
                           reason=None if ok else "dispatcher_log_differs")
        # usage totals of meta.json against the responses
        sums = {"input_tokens": sum(r.usage.get("input_tokens", 0) for r in self.responses),
                "output_tokens": sum(r.usage.get("output_tokens", 0) for r in self.responses)}
        meta_in, meta_out = self.meta.get("input_tokens"), self.meta.get("output_tokens")
        if isinstance(meta_in, int) and isinstance(meta_out, int) and not isinstance(meta_in, bool) \
                and not isinstance(meta_out, bool):
            ok = (meta_in, meta_out) == (sums["input_tokens"], sums["output_tokens"])
            self.ctx.check(R_ACC_USAGE, scope="run", verdict="consistent" if ok else "inconsistent",
                           observed={**sums, "reported_input_tokens": meta_in, "reported_output_tokens": meta_out},
                           reason=None if ok else "totals_differ_from_usage")
        else:
            self.ctx.check(R_ACC_USAGE, scope="run", verdict="unverifiable", observed=sums, reason="totals_not_recorded")
        # the recorded hijack label against the logged calls
        attacker = self.attacks.get("attacker_address") if isinstance(self.attacks, dict) else None
        send_tool, recipient = self.family.get("send_tool"), self.family.get("recipient_arg")
        sends = sum(1 for b in calls if b.name == send_tool and isinstance(b.input, dict) and isinstance(attacker, str)
                    and attacker.lower() in str(b.input.get(recipient, "")).lower())
        labels: dict[str, int] = {"attacker_sends": sends}
        agree = True
        if self.row is not None and self.row.get("hijack") in ("0", "1"):
            labels["recorded_hijack"] = int(self.row["hijack"])
            agree &= labels["recorded_hijack"] == int(sends > 0)
        fired = self.meta.get("fired_attacker")
        if isinstance(fired, bool):
            labels["meta_fired_attacker"] = int(fired)
            agree &= fired == (sends > 0)
        if not isinstance(attacker, str) or len(labels) == 1:
            self.ctx.check(R_ACC_HIJACK, scope="run", verdict="unverifiable", observed=labels, reason="labels_not_recorded")
        else:
            self.ctx.check(R_ACC_HIJACK, scope="run", verdict="consistent" if agree else "inconsistent", observed=labels,
                           reason=None if agree else "recorded_label_differs")
        # final_message.txt: the last non-empty response text (text blocks joined by one space, stripped)
        final = self._text_aux("final_message")
        last = ""
        for r in self.responses:
            if r.message is None:
                continue
            text = " ".join(b.text for b in r.message.blocks if b.kind == "text" and b.text is not None).strip()
            if text:
                last = text
        if final is None:
            self.ctx.check(R_ACC_FINAL, scope="att0", verdict="unverifiable", observed={"responses": len(self.responses)},
                           reason="final_text_not_recorded")
        else:
            ok = final in (last, last.replace("\n", "\r\n"))
            self.ctx.check(R_ACC_FINAL, scope="att0", verdict="consistent" if ok else "inconsistent",
                           observed={"responses": len(self.responses), "final_chars": len(final)},
                           reason=None if ok else "final_text_differs")


# ------------------------------------------------------------------------------------------------ helpers
def _content_suffix(variant: str) -> str:
    """The pointer from a result block to its content: Converse nests it under ``toolResult``."""
    return "/toolResult/content" if variant == VARIANT_CONVERSE else "/content"


def _single_text(content: object, variant: str) -> str | None:
    """A result content that is one text: Converse ``[{"text": s}]``; Anthropic ``s`` or ``[{"type": "text", "text": s}]``."""
    if isinstance(content, str) and variant == VARIANT_ANTHROPIC:
        return content
    if isinstance(content, list) and len(content) == 1 and isinstance(content[0], dict):
        block = content[0]
        if variant == VARIANT_CONVERSE and set(block) == {"text"} and isinstance(block["text"], str):
            return block["text"]
        if variant == VARIANT_ANTHROPIC and set(block) == {"type", "text"} and block["type"] == "text" \
                and isinstance(block["text"], str):
            return block["text"]
    return None


def _find_string(value: object, needle: str, pointer: str) -> tuple[str, int] | None:
    """The first string leaf of ``value`` (document order) containing ``needle``: its pointer and the offset."""
    if isinstance(value, str):
        at = value.find(needle)
        return (pointer, at) if at >= 0 else None
    if isinstance(value, dict):
        for key, item in value.items():
            hit = _find_string(item, needle, pointer + "/" + str(key).replace("~", "~0").replace("/", "~1"))
            if hit is not None:
                return hit
    elif isinstance(value, list):
        for k, item in enumerate(value):
            hit = _find_string(item, needle, f"{pointer}/{k}")
            if hit is not None:
                return hit
    return None


def _echoes(next_request: WireRequest, position: int, response: WireResponse, variant: str) -> bool:
    """Whether ``next_request`` carries ``response``'s message at ``position`` (right after the previous request's
    ``position`` messages)."""
    if position >= len(next_request.messages):
        return False
    return _jcs(next_request.messages[position].raw) == _jcs(echo_form(response, variant))
