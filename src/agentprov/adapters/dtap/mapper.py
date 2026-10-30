"""Mapper ``dtap.trajectory``: one DTap-Bench run (or a judge-only directory) -> AER ``aer/0.1`` (docs/architecture
D.16.3-D.16.8; DECISIONS D-28, D-29).

One trajectory-bearing file is one execution (content-addressed id; byte-identical copies collapse in the runner). The
unit's auxiliary artefacts are the directory's ``judge_result.json`` (``judge``), the other attempts of a re-run
directory (``attempt:<n>``) and the joined configuration of the ``tasks`` pin (``config``). What the mapper writes, in
record order (backward references only, C.5.2):

1. the header: task coordinates from the path (O, origin locator), ``ext.dtap`` (path facets, ids kept verbatim, the
   join, the re-run group, the judge link);
2. actors ``bench``, ``harness``, ``user``, ``agent``, ``env``, ``att``, ``judge`` (those that apply);
3. scopes ``run`` (end time I, status) and ``att0``;
4. fixtures: the task prompt (no user step logged), the attack goal(s), the logged system prompt and tool list, and the
   configured payloads of a tier-A ``direct``/``indirect`` run (existence I, content D: a verbatim copy of the joined
   configuration located by the path rule);
5. the steps in array order: per segment of agent model-output steps one ``model_call`` (I), agent messages (role
   ``agent`` verbatim), tool executions (I) paired per harness (all class I, D.16.7), meta-steps and harness errors as
   generic activities with their artefacts;
6. the judgements (values O, ``checker`` origin I; the audit pair; the judge-to-attempt link D by content, I by
   co-location, or no judgement when a re-run group is unresolved).

Nothing is invented: no timestamp, no start time, no per-step time, no user message, no tool status, no call id. A
configuration is read only through the allowlist of :mod:`agentprov.adapters.dtap.join` (no ``env_vars``).

Pure (A-2): the output is a function of the unit's bytes, the auxiliary bytes, this code, the profile and the catalogues.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from agentprov.adapters.dtap import ADAPTER_ID, DIALECT_ID, VARIANT
from agentprov.adapters.dtap.dialect import (
    FLAG_JUDGE_ONLY,
    JUDGE_KEYS,
    LFS_HEADER,
    PathFacets,
    config_path,
    file_class,
    parse_path,
    state_form,
)
from agentprov.adapters.dtap.join import Join, allowlisted, attack_steps, verify
from agentprov.adapters.dtap.matcher import JUDGE_LINK_MIN, normalise, serialise, strings
from agentprov.adapters.dtap.pairing import Pairing, pair, step_kind
from agentprov.adapters.dtap.redact import ISSUE as I_REDACTED, RULE as R_REDACTED, Redactor, parse_redact_rules
from agentprov.adapters.protocols import AerRecord, MappingContext
from agentprov.adapters.types import ArtefactRef, ExecutionUnit
from agentprov.aer.canon import LexHints, encode_value, json_pointer
from agentprov.aer.ids import import_execution_id, part_id
from agentprov.errors import AgentProvError, IngestError, MalformedArtefact
from agentprov.ingest import yamlsafe
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads

__all__ = ["ADAPTER_ID", "ADAPTER_VERSION", "CATALOGUES", "NAMESPACES", "DtapMapper"]

ADAPTER_VERSION: Final = "0.1.0"
#: Catalogues this mapper cites; the header lists them at the shipped versions (C.3.1 ``rules``).
CATALOGUES: Final = ("aer", "dtap")
NAMESPACES: Final = {"dtap": "https://w3id.org/agentprov/ns/dtap#"}
_AWARE: Final = re.compile(r"([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?)(?:Z|\+00:00)")
_NAIVE: Final = re.compile(r"[0-9]{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])T(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](?:\.[0-9]+)?")
#: Typed strings the validator treats as placeholders (C.7.3): never written into a typed tool name.
_SENTINELS: Final = frozenset({"unknown", "none", "null", "n/a", "na", "", "undefined", "nan"})
_TRUNCATION: Final = "[truncated"
_MODEL_CALL_UNKNOWN: Final = ("/finish_reason", "/params", "/request", "/response", "/t", "/usage")

# rule ids (catalogue dtap, version 1)
R_MODEL: Final = "dtap.path_model_identity@1"
R_HARNESS: Final = "dtap.path_harness_identity@1"
R_USER: Final = "dtap.user_is_simulated_unverified@1"
R_AUTO: Final = "dtap.auto_execution_unverified@1"
R_ORDER: Final = "dtap.steps_append_ordered_unverified@1"
R_AGENT_OUT: Final = "dtap.agent_step_is_model_output_unverified@1"
R_SEGMENT: Final = "dtap.agent_segment_one_turn_unverified@1"
R_CONTEXT: Final = "dtap.context_is_logged_prefix_unverified@1"
R_TOOL_EXEC: Final = "dtap.tool_step_is_execution_unverified@1"
R_UNANSWERED: Final = "dtap.call_without_result@1"
R_META: Final = "dtap.list_mcp_tools_harness_step@1"
R_ERROR: Final = "dtap.harness_error_step@1"
R_ECHO: Final = "dtap.harness_error_echo@1"
R_TOOLS: Final = "dtap.logged_tools_offered_unverified@1"
R_END: Final = "dtap.timestamp_is_run_end_unverified@1"
R_DURATION: Final = "dtap.duration_no_clock@1"
R_PATH_JOIN: Final = "dtap.config_path_join@1"
R_TIER: Final = "dtap.config_join_tier@1"
R_TIER_A: Final = "dtap.config_content_tier_a@1"
R_OFFSET: Final = "dtap.task_id_offset_medical@1"
R_REFORMAT: Final = "dtap.task_id_reformatted@1"
R_ATTACKER: Final = "dtap.config_payload_attacker_unverified@1"
R_DIRECT_PROMPT: Final = "dtap.direct_prompt_no_injection@1"
R_CONTROL: Final = "dtap.control_split_no_attack@1"
R_CUT: Final = "dtap.instruction_cut_500@1"
R_CUT_UNVERIFIED: Final = "dtap.instruction_length_500_unverified@1"
R_EVAL_GOAL: Final = "dtap.goal_rewritten_at_eval@1"
R_NO_USER: Final = "dtap.user_step_not_logged@1"
R_FINAL: Final = "dtap.final_response_copy@1"
R_SRC_TRUNC: Final = "dtap.source_truncation_marker@1"
R_RERUN: Final = "dtap.rerun_group@1"
R_EMPTY: Final = "dtap.empty_trajectory@1"
R_PARTIAL: Final = "dtap.partial_file_name@1"
R_JUDGE: Final = "dtap.judge_recorded_unverified@1"
R_BY_CONTENT: Final = "dtap.judge_attempt_by_content@1"
R_COLOCATED: Final = "dtap.judge_dir_colocation@1"
R_JUDGE_ONLY: Final = "dtap.judge_without_trajectory@1"
R_AUDIT: Final = "dtap.audit_correction_effective@1"
R_NOT_APPLICABLE: Final = "dtap.direct_task_eval_not_applicable@1"
R_BENIGN_ATTACK: Final = "dtap.benign_attack_not_judged@1"
R_JUDGE_ERROR: Final = "dtap.judge_error@1"
R_NO_PARAMS: Final = "dtap.no_params_empty_args@1"
R_FIELDS: Final = "dtap.path_field_check@1"
R_COUNTERS: Final = "dtap.acc.counters@1"
R_GEN: Final = "aer.output_after_generator@1"
R_AFTER_CALL: Final = "aer.execution_after_call@1"
#: D-934: a string whose UTF-8 encoding exceeds 1 MiB is not inlined (C.2.1(6), AER-V01), as Inspect's item 28 and D-832
R_NOT_INLINED: Final = "dtap.content_not_inlined@1"
I_NOT_INLINED: Final = "dtap.content_not_inlined"
_MIB: Final = 1 << 20
_FIELDS: Final = frozenset({"k", "id", "ev", "by", "evf", "rule", "src", "unk", "after"})


def _p(*tokens: str | int) -> str:
    return json_pointer(*tokens)


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _slim(node: Any, tokens: tuple[str, ...], found: list[str]) -> Any:
    """``node`` with every string whose UTF-8 encoding exceeds 1 MiB replaced by its digest object (D-934); ``found``
    collects the replaced pointers."""
    if isinstance(node, str):
        if len(node) <= _MIB // 4:
            return node
        raw = node.encode("utf-8", "surrogatepass")
        if len(raw) <= _MIB:
            return node
        found.append(json_pointer(*tokens))
        return {"not_inlined": {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}}
    if isinstance(node, dict):
        return {k: _slim(v, (*tokens, str(k)), found) for k, v in node.items()}
    if isinstance(node, list):
        return [_slim(v, (*tokens, str(i)), found) for i, v in enumerate(node)]
    return node


def _retype(record: dict[str, Any], pointer: str) -> str:
    """A replaced ``/parts/<k>/text`` cannot stay a typed string field (D-934): a tool result keeps the digest as its
    value, a text part becomes an ``other`` part of type ``text``. Returns the digest's pointer."""
    tokens = pointer.split("/")[1:]
    if len(tokens) != 3 or tokens[0] != "parts" or tokens[2] != "text" or not tokens[1].isdigit():
        return pointer
    part = record["parts"][int(tokens[1])]
    value = part.pop("text")
    if part.get("t") == "text":
        record["parts"][int(tokens[1])] = {"t": "other", "type": "text", "value": value}
    else:
        part["value"] = value
    return f"/parts/{tokens[1]}/value"


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
        """``ext.dtap.<key>`` (encoded)."""
        self.ext[key] = self.enc(value, _p("ext", "dtap", key))

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
            ext["dtap"] = dict(self.ext)
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
class _Attempt:
    """One trajectory of the unit's directory (the primary or an ``attempt:<n>`` auxiliary)."""

    label: str
    sha256: str
    value: dict[str, Any]
    own: bool
    hay: list[tuple[str, str]] = field(default_factory=list)  # (pointer, normalised text) per step and final response


@dataclass
class _Link:
    """The judge-to-attempt decision of D.16.8 for the unit's directory."""

    method: str  # content | colocation | unresolved | judge_only | none
    winner: str | None = None  # sha256 of the judged attempt
    judge_pointer: str | None = None
    attempt_pointer: str | None = None
    group_size: int = 1


class DtapMapper:
    """``Mapper`` for ``dtap.trajectory`` (D.2.4, D.16)."""

    mapper_id: Final = ADAPTER_ID
    version: Final = ADAPTER_VERSION
    accepts: Final = frozenset({(DIALECT_ID, VARIANT)})
    namespaces: Final = NAMESPACES
    catalogues: Final = CATALOGUES

    def map(self, unit: ExecutionUnit, ctx: MappingContext) -> Iterator[AerRecord]:
        yield from _Build(unit, ctx).run()

    @staticmethod
    def prov_primary(flags: frozenset[str]) -> str:
        """Trajectories are written by the producing harness and judge files by the benchmark's judge: ``native``."""
        return "native"

    def degenerate_header(self, unit: ExecutionUnit, ctx: MappingContext, *, issue_code: str, detail: str) -> dict[str, Any]:
        """The header of a degenerate AER (D.2.8 case 3): the task from the path (O, origin locator)."""
        artefact = unit.primary.artefact
        facets, origin_key = _facets_of(artefact)
        if facets is None:
            raise MalformedArtefact("the artefact's path is outside the DTap path grammar: no task can be named")
        header = _header_base(unit, ctx, facets, origin_key, "agent_execution", [artefact.to_json()])
        ctx.issue(issue_code, ids=["exec"], rule=ctx.rule(R_HARNESS), severity="error", detail=detail)
        return header


def _facets_of(artefact: ArtefactRef) -> tuple[PathFacets | None, str]:
    data = artefact.origin.data
    for key in ("path", "label"):
        value = data.get(key)
        if isinstance(value, str):
            return parse_path(value), key
    return None, "path"


def _task(facets: PathFacets) -> dict[str, Any]:
    attack = None if facets.split == "benign" or facets.threat == "direct_no_attack" else facets.threat
    return {
        "benchmark": "dtap",
        "suite": facets.domain,
        "task_id": facets.task_path,
        "attack_id": attack,
        "attack_target_id": facets.risk_category,
    }


def _header_base(unit: ExecutionUnit, ctx: MappingContext, facets: PathFacets, origin_key: str, kind: str,
                 artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    src: list[dict[str, Any]] = [{"a": "a0", "o": f"/{origin_key}"}]
    if "repo" in unit.primary.artefact.origin.data:
        src.append({"a": "a0", "o": "/repo"})
    rules: list[str] = []
    evf: dict[str, str] = {}
    if facets.threat == "direct_no_attack":
        evf["/task/attack_id"] = "I"
        rules.append(ctx.rule(R_CONTROL, "/task/attack_id"))
    header: dict[str, Any] = {
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
        "task": _task(facets),
        "ev": "O",
        "by": "source",
        "src": src,
        "unk": {"/instrumentation": "not_recorded", "/task/defense_id": "not_recorded"},
    }
    if evf:
        header["evf"] = evf
    if rules:
        header["rule"] = rules
    return header


class _Build:
    """One mapping run: every record is built in order, then emitted (backward references only)."""

    def __init__(self, unit: ExecutionUnit, ctx: MappingContext) -> None:
        self.unit, self.ctx = unit, ctx
        item = unit.primary
        if not isinstance(item.value, dict):
            raise MalformedArtefact("the located item is not a DTap JSON object")
        self.v: dict[str, Any] = item.value
        self.judge_only = FLAG_JUDGE_ONLY in item.flags
        facets, self.origin_key = _facets_of(item.artefact)
        if facets is None:
            raise MalformedArtefact("the artefact's path is outside the DTap path grammar")
        self.f: PathFacets = facets
        if self.judge_only and file_class(facets.relpath.rsplit("/", 1)[-1]) != "judge":
            # D.16.8 gives judge-only status to judge_result.json alone; a judge-shaped file under another name (picked
            # as an other_json primary) would cite dtap.judge_without_trajectory@1 on a false premise (regen item 53)
            raise MalformedArtefact("judge-shaped JSON under a file name other than judge_result.json")
        self.harness = facets.framework
        rules = parse_redact_rules(ctx.profile.family_table().get("redact", ()), f"profile {ctx.profile.id!r}")
        self.redactor = Redactor(ctx.profile.id, ctx.profile.version, rules)  # D-607: listed account paths
        self.limits = IngestLimits()
        self.records: list[dict[str, Any]] = []
        self.counters: dict[str, int] = {}
        self.artifacts: list[dict[str, Any]] = [item.artefact.to_json()]
        self.aid: dict[str, str] = {}  # auxiliary role -> header artefact id
        self.ext: dict[str, Any] = {}
        self.ext_evf: dict[str, tuple[str, str | None]] = {}  # ext pointer -> (class, rule)
        self.header_rules: list[str] = []
        self.issues: list[tuple[str, list[str], str, str, str | None]] = []
        self.prev: str | None = None
        self.messages: list[str] = []
        self.tools_fixture: str | None = None
        self.ti: dict[str, Any] = {}
        self.tj: dict[str, Any] = {}
        self.steps: list[dict[str, Any]] = []
        self.kinds: list[str] = []
        self.meta: dict[str, Any] = {}

    # ---------------------------------------------------------------------------------------------- helpers
    def R(self, rule_id: str, pointer: str | None = None) -> str:  # noqa: N802 - mirrors MappingContext.rule
        return self.ctx.rule(rule_id, pointer)

    def issue(self, code: str, ids: Sequence[str], rule: str, *, severity: str = "warning", detail: str | None = None) -> None:
        self.ctx.issue(code, ids=list(ids), rule=self.R(rule), severity=severity, detail=detail)  # type: ignore[arg-type]

    def next_id(self, prefix: str) -> str:
        n = self.counters.get(prefix, 0)
        self.counters[prefix] = n + 1
        return f"{prefix}{n}"

    def loc(self, pointer: str) -> dict[str, Any]:
        return {"a": "a0", "p": pointer}

    def add_artefact(self, role: str, ref: ArtefactRef) -> str:
        aid = f"a{len(self.artifacts)}"
        self.aid[role] = aid
        self.artifacts.append({**ref.to_json(), "id": aid, "role": "supporting", "prov_primary": "native"})
        return aid

    def aux_bytes(self, role: str) -> bytes | None:
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

    def ext_tag(self, key: str, cls: str, rule: str | None) -> None:
        self.ext_evf[_p("ext", "dtap", *key.split("/"))] = (cls, rule)

    # ---------------------------------------------------------------------------------------------- run
    def run(self) -> Iterator[dict[str, Any]]:
        if self.judge_only:
            yield from self._judge_only()
            return
        ti, tj, steps = self.v.get("task_info"), self.v.get("traj_info"), self.v.get("trajectory")
        if not isinstance(ti, dict) or not isinstance(tj, dict) or not isinstance(steps, list):
            raise MalformedArtefact("task_info, traj_info and trajectory are not an object, an object and an array")
        if not all(isinstance(s, dict) for s in steps):
            raise MalformedArtefact("a trajectory step is not an object")
        self.ti, self.tj, self.steps = ti, tj, steps
        self.kinds = [step_kind(s) for s in self.steps]
        if "unknown" in self.kinds:
            raise MalformedArtefact("a trajectory step has an unknown role or shape")
        self.meta = _dict(self.tj.get("metadata"))
        self.outcome_only = len(self.steps) == 0
        self.judge = self._load_judge()
        self.attempts = self._attempts()
        self.join = self._join()
        self.link = self._link()
        self.has_user = "user" in self.kinds
        self.attack = _task(self.f)["attack_id"] is not None
        self.pairing: Pairing = pair(self.steps, self.harness)
        self.has_tool_exec = any(k == "tool" and self._tool_target(i) != "meta" for i, k in enumerate(self.kinds))
        own = self.unit.primary.artefact.sha256
        writes_judgements = self.judge is not None and (
            self.link.method == "colocation" or (self.link.method == "content" and self.link.winner == own))
        body: list[dict[str, Any]] = []
        body += self._actors(writes_judgements)
        body += self._scopes()
        body += self._fixtures()
        if not self.outcome_only:
            body += self._steps()
        if writes_judgements:
            body += self._judgements()
        self._checks()
        self._header_issues()
        yield from self._not_inlined(self._redacted([self._header(), *body]))

    def _redacted(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """The post-pass of D-607: the profile's listed account paths redacted over every string of every record
        (:mod:`agentprov.adapters.dtap.redact`), with one info issue naming the count of redacted values."""
        count = sum(len(self.redactor.apply(record, lambda p: self.R(R_REDACTED, p))) for record in records)
        if count:
            self.issue(I_REDACTED, ["exec"], R_REDACTED, severity="info", detail=str(count))
        return records

    def _not_inlined(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """D-934, after redaction: every string over 1 MiB becomes ``{"not_inlined": {sha256, bytes}}`` of its UTF-8 bytes
        (C.2.1(6)). A tool result's text becomes the part's value; a message's text part becomes an ``other`` part of type
        ``text``. Each such pointer is DERIVED under ``dtap.content_not_inlined@1``; one info issue names the records."""
        ids: list[str] = []
        for record in records:
            found: list[str] = []
            for key in [k for k in record if k not in _FIELDS]:
                record[key] = _slim(record[key], (key,), found)
            if not found:
                continue
            moved = {f: _retype(record, f) for f in found}
            evf = {moved.get(k, k): v for k, v in (record.get("evf") or {}).items()}
            rules = record.setdefault("rule", [])
            floor = "I" if record.get("ev") == "I" else "D"
            for pointer in moved.values():
                evf[pointer] = "I" if evf.get(pointer) == "I" else floor
                ref = self.R(R_NOT_INLINED, pointer)
                if ref not in rules:
                    rules.append(ref)
            record["evf"] = evf
            ids.append(str(record["id"]))
        if ids:
            self.issue(I_NOT_INLINED, sorted(set(ids)), R_NOT_INLINED, severity="info")
        return records

    # ---------------------------------------------------------------------------------------------- inputs
    def _load_judge(self) -> dict[str, Any] | None:
        raw = self.aux_bytes("judge")
        if raw is None:
            return None
        try:
            value = strict_json_loads(raw, self.limits)
        except IngestError as exc:
            raise MalformedArtefact("the directory's judge_result.json is not strict JSON") from exc
        if not isinstance(value, dict):
            raise MalformedArtefact("the directory's judge_result.json is not an object")
        if not ({"task_success", "attack_success"} <= set(value) <= JUDGE_KEYS):  # as the sniff (regen item 52): no
            raise MalformedArtefact(  # judgement value is ever read from a key the judge did not write
                "the directory's judge_result.json lacks task_success or attack_success, or has keys a judge never writes")
        self.add_artefact("judge", self.unit.auxiliary["judge"])
        return value

    def _attempts(self) -> list[_Attempt]:
        """The distinct trajectories of the directory (``dtap.rerun_group@1``): the primary first, then the other
        attempts in label order; byte-identical copies, LFS pointers, unparseable and synthetic files are not attempts."""
        own = _Attempt(self.f.relpath, self.unit.primary.artefact.sha256, self.v, True)
        out = [own]
        seen = {own.sha256}
        unreadable: list[str] = []  # distinct siblings that are no attempt: they still bar co-location (regen item 51)
        for role in sorted((r for r in self.unit.auxiliary if r.startswith("attempt:")), key=lambda r: int(r.split(":")[1])):
            ref = self.unit.auxiliary[role]
            if ref.sha256 in seen:
                continue
            raw = self.aux_bytes(role)
            if raw is None or raw.startswith(LFS_HEADER):
                unreadable.append(role)
                continue
            try:
                value = strict_json_loads(raw, self.limits)
            except IngestError:
                unreadable.append(role)
                continue
            if not isinstance(value, dict) or not isinstance(value.get("trajectory"), list):
                if not isinstance(value, dict) or "trajectory" in value:  # a broken trajectory file; an object with no
                    unreadable.append(role)  # trajectory member (a judge-shaped copy) is no trajectory at all
                continue
            if _dict(value.get("task_info")).get("synthetic") is True or \
                    _dict(_dict(value.get("traj_info")).get("metadata")).get("synthetic") is True:
                unreadable.append(role)
                continue
            seen.add(ref.sha256)
            label = str(ref.origin.data.get("path", ref.origin.data.get("label", role)))
            out.append(_Attempt(label, ref.sha256, value, False))
            self.add_artefact(role, ref)
        self.unreadable_attempts = len(unreadable)
        if len(out) > 1:
            stems = sorted(parse_path(a.label).file_stem if parse_path(a.label) else a.label for a in out)  # type: ignore[union-attr]
            self.ext["rerun"] = {"group_size": len(out), "stems": stems}
            self.ext_tag("rerun", "D", R_RERUN)
        else:
            for role, aid in list(self.aid.items()):
                if role.startswith("attempt:"):
                    del self.aid[role]
                    self.artifacts = [a for a in self.artifacts if a["id"] != aid]
        for role in unreadable:  # cited as supporting: they are why the judge is not linked by co-location
            self.add_artefact(role, self.unit.auxiliary[role])
        return out

    def _join(self) -> Join:
        path = config_path(self.f)
        raw = self.aux_bytes("config")
        if raw is None:
            join = Join(path, "missing")
            self.issue("dtap.config_missing", ["exec"], R_PATH_JOIN, severity="info", detail="no configuration at the path")
            return join
        aid = self.add_artefact("config", self.unit.auxiliary["config"])
        try:
            document = yamlsafe.safe_load(raw, self.limits)
        except (IngestError, yamlsafe.YAMLError):
            join = Join(path, "unparseable")
            self.issue("dtap.config_unparseable", ["exec"], R_PATH_JOIN, detail=f"artefact {aid}")
            return join
        config, converted = allowlisted(document)
        if config is None:
            self.issue("dtap.config_unparseable", ["exec"], R_PATH_JOIN, detail=f"artefact {aid}: not a mapping")
            return Join(path, "unparseable")
        tier, ins, goal, tid = verify(self.f, self.ti, config)
        join = Join(path, "joined", tier, ins, goal, tid, converted, config)
        if tier != "A":
            self.issue("dtap.config_join_unverified", ["exec"], R_TIER, detail=f"tier {tier}")
        return join

    # ---------------------------------------------------------------------------------------------- judge link
    def _link(self) -> _Link:
        if self.judge is None:
            return _Link("none", group_size=len(self.attempts))
        needles = _judge_needles(self.judge)
        for attempt in self.attempts:
            attempt.hay = _haystacks(attempt.value)
        unique: dict[str, tuple[str, str]] = {}  # attempt sha -> (judge pointer, attempt pointer) of its first unique needle
        for pointer, needle in needles:
            holders = []
            for attempt in self.attempts:
                found = next((p for p, text in attempt.hay if needle in text), None)
                if found is not None:
                    holders.append((attempt, found))
            if len(holders) == 1 and holders[0][0].sha256 not in unique:
                unique[holders[0][0].sha256] = (pointer, holders[0][1])
        size = len(self.attempts)
        if len(unique) == 1:
            sha, (jp, ap) = next(iter(unique.items()))
            return _Link("content", sha, jp, ap, size)
        if size == 1 and not self.unreadable_attempts:  # a single-trajectory directory only (dtap.judge_dir_colocation@1)
            return _Link("colocation", self.attempts[0].sha256, group_size=1)
        return _Link("unresolved", group_size=size)

    # ---------------------------------------------------------------------------------------------- header
    def _header(self) -> dict[str, Any]:
        unit = "outcome_only" if self.outcome_only else "agent_execution"
        header = _header_base(self.unit, self.ctx, self.f, self.origin_key, unit, self.artifacts)
        ext: dict[str, Any] = {"path_facets": self.f.to_json(), "file_stem": self.f.file_stem}
        if not self.judge_only:
            ext["task_info_task_id"] = self.ti.get("task_id")
            if "trace_id" in self.meta:
                ext["trace_id"] = self.meta["trace_id"]
            if "framework" in self.meta:
                ext["framework_field"] = self.meta["framework"]
            if "success" in self.tj:
                ext["traj_info_success"] = self.tj["success"]
            if "agent_final_response" in self.tj:
                ext["final_response"] = self.tj["agent_final_response"]
        ext.update(self.ext)
        lex = LexHints()
        header["ext"] = {"dtap": encode_value(ext, at="/ext/dtap", lex=lex)}
        hints = lex.as_dict()
        if hints:
            header["ext"]["lex"] = hints
        evf = dict(header.get("evf", {}))
        rules = list(header.get("rule", []))
        for pointer, (cls, rule) in sorted(self.ext_evf.items()):
            evf[pointer] = cls
            if rule is not None:
                ref = self.R(rule, pointer)
                if ref not in rules:
                    rules.append(ref)
        for ref in self.header_rules:
            if ref not in rules:
                rules.append(ref)
        if evf:
            header["evf"] = evf
        if rules:
            header["rule"] = rules
        return header

    def _header_issues(self) -> None:
        domain = self.ti.get("domain")
        if isinstance(domain, str) and domain != self.f.domain:
            self.issue("dtap.path_field_mismatch", ["exec"], R_FIELDS, severity="info", detail="task_info.domain")
        risk = self.ti.get("risk_category")
        if isinstance(risk, str) and risk != self.f.risk_category:
            self.issue("dtap.path_field_mismatch", ["exec"], R_FIELDS, severity="info", detail="task_info.risk_category")
        if self.f.file == "partial_trajectory.json":
            self.issue("dtap.partial_trajectory", ["exec"], R_PARTIAL)
            self.issue("incomplete_run", ["run"], R_PARTIAL)
        final = self.tj.get("agent_final_response")
        last = next((s for s, k in zip(reversed(self.steps), reversed(self.kinds), strict=True) if k == "message"), None)
        if isinstance(final, str) and last is not None:
            message = _dict(last.get("metadata")).get("message")
            if message != final:
                self.issue("dtap.final_response_differs", ["exec"], R_FINAL, severity="info")
        if any(_TRUNCATION in text for text in strings(self.v.get("trajectory"))):
            self.issue("dtap.source_truncation_marker", ["exec"], R_SRC_TRUNC, severity="info")
        if self.join.status == "joined":
            self.ext["join"] = self.join.to_json()
        else:
            self.ext["join"] = self.join.to_json()
        self.ext_tag("join", "D", R_TIER if self.join.status == "joined" else R_PATH_JOIN)
        if self.join.task_id in ("offset_medical", "reformatted"):  # an evidenced normalisation: the reading is I
            self.ext_tag("join/task_id", "I", R_OFFSET if self.join.task_id == "offset_medical" else R_REFORMAT)
        self.ext.update(self._judge_link_ext())

    def _judge_link_ext(self) -> dict[str, Any]:
        if self.judge is None:
            return {}
        sha = self.unit.auxiliary["judge"].sha256
        link: dict[str, Any] = {"judge_sha256": sha, "method": self.link.method, "group_size": self.link.group_size}
        if self.link.method == "content":
            link["resolved"] = True
            if self.link.winner != self.unit.primary.artefact.sha256:
                link["resolved_to"] = import_execution_id(self.ctx.mapping_id, str(self.link.winner), {"p": ""})
            self.ext_tag("judge_link", "D", R_BY_CONTENT)
        elif self.link.method == "colocation":
            link["resolved"] = True
            self.ext_tag("judge_link", "I", R_COLOCATED)
        else:
            link["resolved"] = False
            self.ext_tag("judge_link", "D", R_RERUN)
        return {"judge_link": link}

    # ---------------------------------------------------------------------------------------------- actors and scopes
    def _origin_src(self) -> list[dict[str, Any]]:
        return [{"a": "a0", "o": f"/{self.origin_key}"}]

    def _actors(self, writes_judgements: bool) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        bench = _Rec(k="actor", id="bench", kind="benchmark", name="dtap", ev="O")
        for entry in self._origin_src():
            bench.loc(entry)
        if "repo" in self.unit.primary.artefact.origin.data:
            bench.loc({"a": "a0", "o": "/repo"})
        bench.unk.update({"/code": "not_recorded", "/version": "not_recorded"})
        out.append(bench.done())
        harness = _Rec(k="actor", id="harness", kind="harness", name=self.harness, ev="O")
        for entry in self._origin_src():
            harness.loc(entry)
        harness.tag("/name", "I", self.R(R_HARNESS, "/name"))
        if "framework" in self.meta:
            harness.loc(self.loc("/traj_info/metadata/framework"))
        harness.unk.update({"/code": "not_recorded", "/version": "not_recorded"})
        out.append(harness.done())
        if not self.outcome_only:
            user = _Rec(k="actor", id="user", kind="simulated_user", ev="I")
            user.cite(self.R(R_USER))
            out.append(user.done())
        agent = _Rec(k="actor", id="agent", kind="llm_agent", ev="I", model={"requested": self.f.model})
        agent.cite(self.R(R_MODEL))
        for entry in self._origin_src():
            agent.loc(entry)
        if not self.outcome_only:
            agent.data["on_behalf_of"] = "user"
            agent.cite(self.R(R_USER, "/on_behalf_of"))
        agent.unk.update({"/model/provider": "not_recorded", "/model/served": "not_recorded", "/params": "not_recorded"})
        out.append(agent.done())
        if self.has_tool_exec:
            env = _Rec(k="actor", id="env", kind="tool_runtime", name="mcp", on_behalf_of="agent", ev="I")
            env.cite(self.R(R_TOOL_EXEC))
            env.cite(self.R(R_AUTO, "/on_behalf_of"))
            out.append(env.done())
        if self.attack:
            att = _Rec(k="actor", id="att", kind="attacker", name=str(self.f.threat), ev="O")
            for entry in self._origin_src():
                att.loc(entry)
            out.append(att.done())
        if writes_judgements:
            judge = _Rec(k="actor", id="judge", kind="judge", ev="O", by="benchmark")
            judge.loc({"a": self.aid["judge"]})
            judge.unk["/model"] = "not_recorded"
            out.append(judge.done())
        return out

    def _scopes(self) -> list[dict[str, Any]]:
        run = _Rec(k="scope", id="run", kind="run", ev="O")
        run.loc(self.loc(""))
        self._run_time(run)
        error_steps = [i for i, k in enumerate(self.kinds) if k == "error"]
        if error_steps:
            run.data["status"] = "error"
            run.loc(self.loc(f"/trajectory/{error_steps[0]}"))
        elif self.outcome_only and isinstance(self.meta.get("error"), str):
            run.data["status"] = "error"
            run.loc(self.loc("/traj_info/metadata/error"))
        else:
            run.unk["/status"] = "not_recorded"
        if "duration" in self.tj:
            run.x("duration", self.tj["duration"])
            run.unk["/t/dur_s"] = "ambiguous"
            run.cite(self.R(R_DURATION, "/t/dur_s"))
        out = [run.done()]
        if not self.outcome_only:
            att = _Rec(k="scope", id="att0", kind="attempt", parent="run", actor="agent", ev="O")
            att.loc(self.loc("/trajectory"))
            att.unk.update({"/index": "not_recorded", "/scored": "not_recorded"})
            out.append(att.done())
        return out

    def _run_time(self, run: _Rec) -> None:
        stamp = self.tj.get("timestamp")
        if not isinstance(stamp, str):
            run.unk["/t"] = "not_recorded"
            return
        # D.16.18 correction 1: the reading "timestamp = run end" is class I, and an I-class t.end (or t.end_naive) is
        # emitted by agentprov-prov/0.1 as an inference-bundle assessment entity carrying prov:endTime, which the tier-4
        # validators refuse (NE-6, pv.prov_structure). The value is therefore kept verbatim in t.raw.end (O) and the
        # typed slot is declared ambiguous under the I rule; whether the value has a zone is recorded in ext.dtap.
        run.data["t"] = {"raw": {"end": stamp}}
        run.unk["/t/end"] = "ambiguous"
        run.cite(self.R(R_END, "/t/end"))
        run.x("timestamp_zone", "utc" if _AWARE.fullmatch(stamp) else "none" if _NAIVE.fullmatch(stamp) else "unparsed")
        run.loc(self.loc("/traj_info/timestamp"))
        run.unk["/t/start"] = "not_recorded"

    # ---------------------------------------------------------------------------------------------- fixtures
    def _fixtures(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        ti = self.ti
        original = ti.get("original_instruction")
        if not self.has_user and isinstance(original, str):
            fx = _Rec(k="fixture", id=self.next_id("fx"), kind="task_prompt", ev="O")
            fx.set("content", original)
            fx.loc(self.loc("/task_info/original_instruction"))
            out.append(fx.done())
            if not self.outcome_only:
                self.issue("dtap.user_step_not_logged", [fx.id], R_NO_USER, severity="info")
        if isinstance(original, str) and len(original) == 500:
            cut = self.join.status == "joined" and self.join.instruction == "prefix_500"
            self.issue("dtap.task_info_truncated", ["exec"], R_CUT if cut else R_CUT_UNVERIFIED, severity="info")
        goal = ti.get("malicious_instruction")
        if isinstance(goal, str) and goal:
            out.append(self._goal_fixture("dtap.attack_goal", goal, "/task_info/malicious_instruction"))
        at_eval = ti.get("malicious_instruction_at_eval")
        if isinstance(at_eval, str):
            fx_rec = self._goal_fixture("dtap.attack_goal_at_eval", at_eval, "/task_info/malicious_instruction_at_eval",
                                        updated=ti.get("goal_text_updated"))
            out.append(fx_rec)
            self.issue("dtap.goal_rewritten_at_eval", [str(fx_rec["id"])], R_EVAL_GOAL, severity="info")
        debug = _dict(self.v.get("debug"))
        if "system_prompt" in debug:
            fx = _Rec(k="fixture", id=self.next_id("fx"), kind="system_prompt", ev="O")
            fx.set("content", debug["system_prompt"])
            fx.loc(self.loc("/debug/system_prompt"))
            out.append(fx.done())
        tools, where = None, None
        if "tool_descriptions" in debug:
            tools, where = debug["tool_descriptions"], "/debug/tool_descriptions"
        elif "mcp_tools" in self.meta:
            tools, where = self.meta["mcp_tools"], "/traj_info/metadata/mcp_tools"
        if where is not None:
            fx = _Rec(k="fixture", id=self.next_id("fx"), kind="tool_definitions", ev="O")
            fx.set("content", tools)
            fx.loc(self.loc(where))
            fx.x("logged_at", where)
            out.append(fx.done())
            self.tools_fixture = fx.id
        out += self._payloads()
        return out

    def _goal_fixture(self, subtype: str, text: str, pointer: str, *, updated: object = None) -> dict[str, Any]:
        fx = _Rec(k="fixture", id=self.next_id("fx"), kind="other", subtype=subtype, ev="O")
        fx.set("content", text)
        fx.loc(self.loc(pointer))
        if self.attack:
            fx.data["actor"] = "att"
            fx.tag("/actor", "I", self.R(R_ATTACKER, "/actor"))
        else:
            fx.unk["/actor"] = "not_recorded"
        if updated is not None:
            fx.x("goal_text_updated", updated)
            fx.loc(self.loc("/task_info/goal_text_updated"))
        return fx.done()

    def _payloads(self) -> list[dict[str, Any]]:
        """D.16.6: one ``injection_payload`` fixture per configured attack step of a tier-A ``direct``/``indirect`` run."""
        threat = self.f.threat
        if self.outcome_only or self.join.status != "joined" or self.join.tier != "A" or threat not in ("direct", "indirect"):
            if self.join.status == "joined" and threat == "direct_prompt":
                self.header_rules.append(self.R(R_DIRECT_PROMPT))
            return []
        assert self.join.config is not None
        aid = self.aid["config"]
        out: list[dict[str, Any]] = []
        for turn, index, step in attack_steps(self.join.config):
            kind = step.get("type")
            # <channel>:<field value> and the step's content member. A step without the field (or with a non-string
            # one) has no vector, and one without the content member has no content: each is unk not_recorded
            # (C.3.9), never a placeholder such as 'environment:None' or a D-tagged null (regen item 54)
            if kind == "environment":
                field, content_key = step.get("injection_mcp_tool"), "kwargs"
            elif kind == "tool":
                field, content_key = step.get("injected_tool"), "content"
            elif kind == "skill":
                field, content_key = step.get("skill_name"), "content"
            elif kind == "prompt":
                field, content_key = step.get("mode"), "content"
            else:
                field, content_key = kind, "content" if "content" in step else "kwargs"
            channel = kind if kind in ("environment", "tool", "skill", "prompt") else "other"
            vector = f"{channel}:{field}" if isinstance(field, str) else None
            fx = _Rec(k="fixture", id=self.next_id("fx"), kind="injection_payload", ev="I", actor="att")
            if vector is not None:
                fx.set("vector", vector)
            if content_key in step:  # an explicit null is recorded, so it stays an observed value
                fx.set("content", step[content_key])
            fx.cite(self.R(R_TIER_A))
            if content_key in step:
                fx.tag("/content", "D", self.R(R_PATH_JOIN, "/content"))
            else:
                fx.unk["/content"] = "not_recorded"
                fx.cite(self.R(R_PATH_JOIN, "/content"))
            if vector is not None:
                fx.tag("/vector", "D", self.R(R_PATH_JOIN, "/vector"))
            else:
                fx.unk["/vector"] = "not_recorded"
                fx.cite(self.R(R_PATH_JOIN, "/vector"))
            fx.tag("/actor", "I", self.R(R_ATTACKER, "/actor"))
            fx.loc({"a": aid})
            fx.x("config_pointer", _p("Attack", "attack_turns", turn, "attack_steps", index))
            fx.x("step", {k: step[k] for k in ("type", "mode", "injected_tool", "injection_mcp_tool", "skill_name")
                          if k in step and isinstance(step[k], str)} | {"turn": turn, "index": index})
            out.append(fx.done())
        return out

    # ---------------------------------------------------------------------------------------------- steps
    def _tool_target(self, i: int) -> str:
        """``meta`` when tool step ``i`` is linked to a meta-step, else ``tool``. Only links count, as in ``_steps``: a
        result of a name-conflicted batch links nothing and is an unlinked execution (D.16.7; regen item 50)."""
        call = self.pairing.links.get(i)
        return "meta" if call is not None and self.kinds[call] == "meta" else "tool"

    def _segments(self) -> dict[int, int]:
        """Step index of each model-output agent step -> its segment ordinal (D.16.3; meta, error and echo steps are
        harness steps and break a segment)."""
        out: dict[int, int] = {}
        n = -1
        open_segment = False
        for i, kind in enumerate(self.kinds):
            model_output = kind == "call" or (kind == "message" and not self._is_echo(i))
            if model_output:
                if not open_segment:
                    n += 1
                    open_segment = True
                out[i] = n
            else:
                open_segment = False
        return out

    def _is_echo(self, i: int) -> bool:
        return i > 0 and self.kinds[i - 1] == "error" and self.kinds[i] == "message"

    def _steps(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        segments = self._segments()
        mc_of: dict[int, str] = {}
        meta_ac: dict[int, str] = {}  # meta call step -> activity id
        users = 0
        for i, step in enumerate(self.steps):
            kind = self.kinds[i]
            base = f"/trajectory/{i}"
            if kind == "user":
                users += 1
                out.append(self._user(i, step, users))
            elif kind in ("call", "message") and i in segments:
                seg = segments[i]
                if seg not in mc_of:
                    mc_id = self.next_id("mc")
                    mc_of[seg] = mc_id
                    out.append(self._model_call(mc_id, i))
                out.append(self._agent(i, step, kind, mc_of[seg]))
            elif kind == "message":  # the echo of a harness error
                out.append(self._echo(i, step))
            elif kind == "meta":
                ac = _Rec(k="activity", id=self.next_id("ac"), type="dtap:list_mcp_tools", actor="harness", scope="att0",
                          inputs=[], ev="O")
                action = step.get("action")
                if isinstance(action, str):
                    ac.set("label", action)
                ac.loc(self.loc(base))
                answer = next((t for t, c in self.pairing.links.items() if c == i), None)
                if answer is not None:
                    ac.loc(self.loc(f"/trajectory/{answer}"))
                ac.tag("/actor", "I", self.R(R_META, "/actor"))
                self._pos(ac)
                meta_ac[i] = ac.id
                out.append(ac.done())
                self.prev = ac.id
            elif kind == "error":
                out += self._error(i, step)
            elif kind == "tool":
                call = self.pairing.links.get(i)
                if call is not None and self.kinds[call] == "meta":
                    out.append(self._meta_result(i, step, meta_ac[call]))
                else:
                    out += self._tool(i, step, call)
        self._step_issues()
        return out

    def _pos(self, rec: _Rec) -> None:
        if self.prev is not None:
            rec.edge(self.prev, "pos")
            rec.tag("/after", "I", self.R(R_ORDER, "/after"))

    def _user(self, i: int, step: Mapping[str, Any], n: int) -> dict[str, Any]:
        mid = f"m{i}"
        rec = _Rec(k="message", id=mid, scope="att0", role="user", actor="user", ev="O")
        state = step.get("state")
        if isinstance(state, str):
            rec.data["parts"] = [{"t": "text", "text": rec.enc(state, "/parts/0/text")}]
        else:
            rec.data["parts"] = [{"t": "other", "type": "dtap.user_state", "value": rec.enc(state, "/parts/0/value")}]
        rec.loc(self.loc(f"/trajectory/{i}"))
        rec.tag("/actor", "I", self.R(R_USER, "/actor"))
        self._pos(rec)
        if n > 1:
            self.issue("unattributed_additional_user_message", [mid], R_USER)
        self.messages.append(mid)
        self.prev = mid
        return rec.done()

    def _model_call(self, mc_id: str, i: int) -> dict[str, Any]:
        mc = _Rec(k="model_call", id=mc_id, actor="agent", role="agent", scope="att0", status="kept", ev="I")
        mc.data["input"] = list(self.messages)
        mc.cite(self.R(R_SEGMENT))
        mc.tag("/input", "I", self.R(R_CONTEXT, "/input"))
        if self.tools_fixture is not None:
            mc.data["tools"] = self.tools_fixture
            mc.tag("/tools", "I", self.R(R_TOOLS, "/tools"))
        mc.loc(self.loc(f"/trajectory/{i}"))
        self._pos(mc)
        mc.unk.update({key: "not_recorded" for key in _MODEL_CALL_UNKNOWN})
        self.prev = mc_id
        return mc.done()

    def _agent(self, i: int, step: Mapping[str, Any], kind: str, mc_id: str) -> dict[str, Any]:
        mid = f"m{i}"
        meta = _dict(step.get("metadata"))
        rec = _Rec(k="message", id=mid, scope="att0", role="agent", actor="agent", generated_by=mc_id, ev="O")
        if kind == "call":
            name = meta.get("tool_name")
            part: dict[str, Any] = {"t": "tool_call", "name": rec.enc(name, "/parts/0/name")}
            if "tool_params" in meta:
                part["args"] = rec.enc(meta["tool_params"], "/parts/0/args")
            else:
                action = step.get("action")
                empty = isinstance(action, str) and isinstance(name, str) and action == f"{name}()"
                part["args"] = {} if empty else None
                rec.tag("/parts/0/args", "D", self.R(R_NO_PARAMS, "/parts/0/args"))
                if not empty:
                    rec.unk["/parts/0/args"] = "ambiguous"
            rec.data["parts"] = [part]
            rec.unk["/parts/0/args_raw"] = "not_recorded"
            if isinstance(name, str) and name.lower() in _SENTINELS:
                rec.unk["/parts/0/name"] = "ambiguous"
                rec.cite(self.R(R_AGENT_OUT, "/parts/0/name"))
            if "action" in step:
                rec.x("action", step["action"])
            if "server" in meta:
                rec.x("server", meta["server"])
        else:
            message = meta.get("message")
            if isinstance(message, str):
                rec.data["parts"] = [{"t": "text", "text": rec.enc(message, "/parts/0/text")}]
            else:
                rec.data["parts"] = [{"t": "other", "type": "dtap.agent_message", "value": rec.enc(message, "/parts/0/value")}]
            if meta.get("synthetic") is not None:
                rec.x("synthetic", meta.get("synthetic"))
        rec.loc(self.loc(f"/trajectory/{i}"))
        rec.tag("/actor", "I", self.R(R_AGENT_OUT, "/actor"))
        rec.tag("/generated_by", "I", self.R(R_SEGMENT, "/generated_by"))
        rec.edge(mc_id, "causal")
        rec.tag("/after", "I", self.R(R_GEN, "/after"))
        if self.prev is not None and self.prev != mc_id:
            rec.edge(self.prev, "pos")
            rec.cite(self.R(R_ORDER, "/after"))
        self.messages.append(mid)
        self.prev = mid
        return rec.done()

    def _echo(self, i: int, step: Mapping[str, Any]) -> dict[str, Any]:
        mid = f"m{i}"
        rec = _Rec(k="message", id=mid, scope="att0", role="agent", ev="O")
        message = _dict(step.get("metadata")).get("message")
        if isinstance(message, str):
            rec.data["parts"] = [{"t": "text", "text": rec.enc(message, "/parts/0/text")}]
        else:
            rec.data["parts"] = [{"t": "other", "type": "dtap.agent_message", "value": rec.enc(message, "/parts/0/value")}]
        rec.unk.update({"/actor": "ambiguous", "/generated_by": "not_recorded"})
        rec.cite(self.R(R_ECHO, "/actor"))
        rec.loc(self.loc(f"/trajectory/{i}"))
        self._pos(rec)
        self.messages.append(mid)
        self.prev = mid
        return rec.done()

    def _error(self, i: int, step: Mapping[str, Any]) -> list[dict[str, Any]]:
        ac = _Rec(k="activity", id=self.next_id("ac"), type="dtap:harness_error", actor="harness", scope="att0",
                  inputs=[], status="error", ev="O")
        ac.loc(self.loc(f"/trajectory/{i}"))
        ac.tag("/actor", "I", self.R(R_ERROR, "/actor"))
        self._pos(ac)
        self.prev = ac.id
        af = _Rec(k="artefact", id=self.next_id("af"), type="dtap:error_text", generated_by=ac.id, ev="O")
        af.set("content", _dict(step.get("metadata")).get("error"))
        af.loc(self.loc(f"/trajectory/{i}/metadata/error"))
        self._pos(af)
        self.prev = af.id
        self.issue("dtap.harness_failure", [ac.id], R_ERROR)
        return [ac.done(), af.done()]

    def _meta_result(self, i: int, step: Mapping[str, Any], ac_id: str) -> dict[str, Any]:
        af = _Rec(k="artefact", id=self.next_id("af"), type="dtap:tool_name_list", generated_by=ac_id, ev="O")
        af.set("content", step.get("state"))
        af.loc(self.loc(f"/trajectory/{i}/state"))
        af.tag("/generated_by", "I", self.R(str(self.pairing.rule), "/generated_by"))
        self._pos(af)
        self.prev = af.id
        return af.done()

    def _tool(self, i: int, step: Mapping[str, Any], call: int | None) -> list[dict[str, Any]]:
        meta = _dict(step.get("metadata"))
        rule = self.pairing.rule or R_TOOL_EXEC
        te = _Rec(k="tool_execution", id=self.next_id("te"), actor="env", scope="att0", ev="I")
        te.cite(self.R(R_TOOL_EXEC))
        if call is not None:
            cmeta = _dict(self.steps[call].get("metadata"))
            te.data["call"] = part_id(f"m{call}", 0)
            te.tag("/call", "I", self.R(rule, "/call"))
            called = cmeta.get("tool_name")
            te.set("name", called)
            te.evf["/name"] = "O"
            if not isinstance(called, str) or called.lower() in _SENTINELS:  # never a placeholder in a typed name (C.7.3)
                te.unk["/name"] = "ambiguous"
                te.cite(self.R(rule, "/name"))
            if "tool_params" in cmeta:
                te.set("args", cmeta["tool_params"])
                te.evf["/args"] = "O"
            else:
                te.unk["/args"] = "not_recorded"
            te.loc(self.loc(f"/trajectory/{call}/metadata"))
            te.edge(f"m{call}", "causal")
            te.tag("/after", "I", self.R(R_AFTER_CALL, "/after"))
            if self.prev is not None and self.prev != f"m{call}":
                te.edge(self.prev, "pos")
                te.cite(self.R(R_ORDER, "/after"))
        else:
            name = meta.get("tool_name")
            te.set("name", name if isinstance(name, str) and name.lower() not in _SENTINELS else str(name))
            if not isinstance(name, str) or name.lower() in _SENTINELS:
                te.unk["/name"] = "ambiguous"
            else:
                te.evf["/name"] = "O"
            te.unk.update({"/call": "ambiguous", "/args": "ambiguous"})
            te.cite(self.R(rule, "/call"))
            self._pos(te)
        te.loc(self.loc(f"/trajectory/{i}/metadata"))
        te.unk.update({"/returned": "not_recorded", "/status": "not_recorded"})
        if "duration_s" in meta:
            te.x("duration_s", meta["duration_s"])
            te.unk.update({"/t/dur_s": "ambiguous", "/t/end": "not_recorded", "/t/start": "not_recorded"})
            te.cite(self.R(R_DURATION, "/t/dur_s"))
        else:
            te.unk["/t"] = "not_recorded"
        self.prev = te.id
        mid = f"m{i}"
        msg = _Rec(k="message", id=mid, scope="att0", role="tool", actor="env", generated_by=te.id, ev="O")
        state = step.get("state")
        part: dict[str, Any] = {"t": "tool_result"}
        if call is not None:
            part["responds_to"] = part_id(f"m{call}", 0)
            msg.tag("/parts/0/responds_to", "I", self.R(rule, "/parts/0/responds_to"))
        else:
            reason = "ambiguous" if i in self.pairing.conflicted else "not_recorded"
            msg.unk["/parts/0/responds_to"] = reason
            msg.cite(self.R(rule, "/parts/0/responds_to"))
        form = state_form(state)
        if isinstance(state, str):
            part["text"] = msg.enc(state, "/parts/0/text")
        else:
            part["value"] = msg.enc(state, "/parts/0/value")
        name = meta.get("tool_name")
        if isinstance(name, str) and name.lower() not in _SENTINELS:
            part["name"] = msg.enc(name, "/parts/0/name")
        else:
            msg.x("result_tool_name", name)
            msg.unk["/parts/0/name"] = "ambiguous"
            msg.cite(self.R(rule, "/parts/0/name"))
        msg.data["parts"] = [part]
        if form in ("python_repr", "brace_text"):
            msg.x("state_form", form)
        if "server" in meta:
            msg.x("server", meta["server"])
        msg.loc(self.loc(f"/trajectory/{i}"))
        msg.tag("/actor", "I", self.R(R_AUTO, "/actor"))
        msg.tag("/generated_by", "I", self.R(R_TOOL_EXEC, "/generated_by"))
        msg.edge(te.id, "causal")
        msg.tag("/after", "I", self.R(R_GEN, "/after"))
        self.messages.append(mid)
        self.prev = mid
        return [te.done(), msg.done()]

    def _step_issues(self) -> None:
        rule = self.pairing.rule or R_TOOL_EXEC
        te_of: dict[int, str] = {}
        n = 0
        for i, kind in enumerate(self.kinds):
            if kind == "tool" and self._tool_target(i) != "meta":
                te_of[i] = f"te{n}"
                n += 1
        for batch in self.pairing.batches:
            calls = [part_id(f"m{c}", 0) for c in batch.calls if self.kinds[c] == "call"]
            tes = [te_of[r] for r in batch.results if r in te_of]
            if batch.conflict is not None:
                self.issue("call_result_link_conflict", calls + tes, rule, detail=batch.conflict)
            elif batch.multi:
                self.issue("dtap.pairing_ambiguous_batch", calls + tes, rule, severity="info", detail=batch.detail)
        unanswered = [part_id(f"m{c}", 0) for c in self.pairing.unanswered if self.kinds[c] == "call"]
        if unanswered:
            self.issue("unexecuted_tool_call", unanswered, R_UNANSWERED)
        orphans = [f"m{r}" for r in self.pairing.orphans]
        if orphans:
            self.issue("orphan_tool_result", orphans, rule)

    # ---------------------------------------------------------------------------------------------- judgements
    def _judgements(self) -> list[dict[str, Any]]:
        assert self.judge is not None
        aid = self.aid["judge"]
        if self.link.method == "content":
            subject = ("D", R_BY_CONTENT, [{"a": aid, "p": str(self.link.judge_pointer)}, self._attempt_loc()])
        else:
            subject = ("I", R_COLOCATED, [])
        return self._judgement_records(aid, subject)

    def _attempt_loc(self) -> dict[str, Any]:
        if self.link.winner == self.unit.primary.artefact.sha256:
            return {"a": "a0", "p": str(self.link.attempt_pointer)}
        return {"a": "a0"}

    def _judgement_records(self, aid: str, subject: tuple[str, str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
        judge = self.judge
        assert judge is not None
        threat = self.f.threat
        split = self.f.split_label
        out: list[dict[str, Any]] = []

        def make(name: str, value: object, pointer: str, origin: str, origin_rule: str, origin_cls: str,
                 extra: Mapping[str, object]) -> _Rec:
            rec = _Rec(k="judgement", id=self.next_id("j"), actor="judge", subject="run", name=name, ev="O", by="benchmark")
            rec.set("value", value)
            rec.data["origin"] = origin
            rec.loc({"a": aid, "p": pointer})
            rec.tag("/origin", origin_cls, self.R(origin_rule, "/origin"))
            cls, srule, locs = subject
            rec.tag("/subject", cls, self.R(srule, "/subject"))
            for entry in locs:
                rec.loc(entry)
            rec.unk["/t"] = "not_recorded"
            if origin == "checker":
                rec.unk["/inputs"] = "not_recorded"
            rec.x("judge", dict(extra))
            return rec

        task_extra: dict[str, object] = {k: judge[k] for k in ("task_message", "task_metadata", "error") if k in judge}
        attack_extra: dict[str, object] = {k: judge[k] for k in ("attack_message", "attack_metadata", "error") if k in judge}
        ts = judge.get("task_success")
        if split in ("direct", "direct_prompt") and (split == "direct_prompt" or ts is None):
            j0 = make("task_success", ts, "/task_success", "harness_default", R_NOT_APPLICABLE, "I", task_extra)
        else:
            j0 = make("task_success", ts, "/task_success", "checker", R_JUDGE, "I", task_extra)
        out.append(j0.done())
        audit = judge.get("audit_correction")
        attack = judge.get("attack_success")
        if split == "benign" and attack is None:
            out.append(make("attack_success", attack, "/attack_success", "harness_default", R_BENIGN_ATTACK, "I",
                            attack_extra).done())
        elif isinstance(audit, dict) and "original_attack_success" in audit:
            j1 = make("attack_success", audit["original_attack_success"], "/audit_correction/original_attack_success",
                      "checker", R_JUDGE, "I", {k: v for k, v in attack_extra.items() if k == "error"}
                      | {"original_metadata": audit.get("original_metadata")})
            out.append(j1.done())
            j2 = make("attack_success", attack, "/attack_success", "recomputed", R_AUDIT, "D", attack_extra)
            j2.data["revises"] = j1.id
            j2.tag("/revises", "D", self.R(R_AUDIT, "/revises"))
            j2.loc({"a": aid, "p": "/audit_correction"})
            j2.x("audit", {k: audit[k] for k in ("patch_id", "patch_reason") if k in audit})
            out.append(j2.done())
        else:
            out.append(make("attack_success", attack, "/attack_success", "checker", R_JUDGE, "I", attack_extra).done())
        if judge.get("error") is not None:
            self.issue("dtap.judge_error", [str(r["id"]) for r in out], R_JUDGE_ERROR)
        if self.has_error_step():
            self.issue("dtap.judgement_on_failed_run", [str(r["id"]) for r in out], R_ERROR)
        del threat
        return out

    def has_error_step(self) -> bool:
        return "error" in getattr(self, "kinds", [])

    # ---------------------------------------------------------------------------------------------- checks
    def _checks(self) -> None:
        if self.outcome_only:
            self.issue("no_execution_observed", ["run"], R_EMPTY)
            self.issue("dtap.empty_trajectory", ["run"], R_EMPTY)
        if self.judge is None:
            self.issue("no_outcome_recorded", ["run"], R_JUDGE)
        elif self.link.method == "unresolved":
            unreadable = f", {self.unreadable_attempts} unreadable sibling(s)" if self.unreadable_attempts else ""
            self.issue("dtap.judge_attempt_unresolved", ["exec"], R_RERUN, detail=f"{self.link.group_size} attempts{unreadable}")
        elif self.link.method == "content" and self.link.winner != self.unit.primary.artefact.sha256:
            self.issue("dtap.unjudged_attempt", ["exec"], R_BY_CONTENT, severity="info")
        counters = {k: self.tj.get(k) for k in ("step_count", "actions_count", "tool_count", "user_turn")}
        observed = {
            "steps": len(self.steps),
            "agent_steps": sum(1 for k in self.kinds if k in ("call", "meta", "message", "error")),
            "tool_steps": self.kinds.count("tool"),
            "user_steps": self.kinds.count("user"),
        }
        scope = "run" if self.outcome_only else "att0"
        if not all(isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in counters.values()):
            self.ctx.check(R_COUNTERS, scope=scope, verdict="unverifiable", observed=observed, reason="counters_not_recorded")
            return
        ok = (counters["step_count"] == observed["steps"] and counters["actions_count"] == observed["agent_steps"]
              and counters["tool_count"] == observed["tool_steps"] and counters["user_turn"] == observed["user_steps"])
        self.ctx.check(R_COUNTERS, scope=scope, verdict="consistent" if ok else "inconsistent",
                       observed={**observed, **{k: int(v) for k, v in counters.items()}},  # type: ignore[arg-type]
                       reason=None if ok else "counters_differ_from_steps")

    # ---------------------------------------------------------------------------------------------- judge-only units
    def _judge_only(self) -> Iterator[dict[str, Any]]:
        """D.16.8: a directory with a judge and no trajectory-bearing file is an ``outcome_only`` unit whose primary
        artefact is the judge file (``dtap.judge_without_trajectory@1``)."""
        self.judge = self.v
        self.aid["judge"] = "a0"
        self.attack = _task(self.f)["attack_id"] is not None
        self.outcome_only = True
        self.meta, self.ti, self.tj, self.kinds, self.steps = {}, {}, {}, [], []
        self.link = _Link("judge_only")
        body: list[dict[str, Any]] = []
        bench = _Rec(k="actor", id="bench", kind="benchmark", name="dtap", ev="O")
        for entry in self._origin_src():
            bench.loc(entry)
        if "repo" in self.unit.primary.artefact.origin.data:
            bench.loc({"a": "a0", "o": "/repo"})
        bench.unk.update({"/code": "not_recorded", "/version": "not_recorded"})
        body.append(bench.done())
        harness = _Rec(k="actor", id="harness", kind="harness", name=self.harness, ev="O")
        for entry in self._origin_src():
            harness.loc(entry)
        harness.tag("/name", "I", self.R(R_HARNESS, "/name"))
        harness.unk.update({"/code": "not_recorded", "/version": "not_recorded"})
        body.append(harness.done())
        agent = _Rec(k="actor", id="agent", kind="llm_agent", ev="I", model={"requested": self.f.model})
        agent.cite(self.R(R_MODEL))
        for entry in self._origin_src():
            agent.loc(entry)
        agent.unk.update({"/model/provider": "not_recorded", "/model/served": "not_recorded", "/params": "not_recorded"})
        body.append(agent.done())
        if self.attack:
            att = _Rec(k="actor", id="att", kind="attacker", name=str(self.f.threat), ev="O")
            for entry in self._origin_src():
                att.loc(entry)
            body.append(att.done())
        judge = _Rec(k="actor", id="judge", kind="judge", ev="O", by="benchmark")
        judge.loc({"a": "a0"})
        judge.unk["/model"] = "not_recorded"
        body.append(judge.done())
        run = _Rec(k="scope", id="run", kind="run", ev="O")
        run.loc({"a": "a0"})
        run.unk.update({"/status": "not_recorded", "/t": "not_recorded"})
        body.append(run.done())
        body += self._judgement_records("a0", ("D", R_JUDGE_ONLY, []))
        self.issue("no_execution_observed", ["run"], R_JUDGE_ONLY)
        header = _header_base(self.unit, self.ctx, self.f, self.origin_key, "outcome_only", self.artifacts)
        header["ext"] = {"dtap": {"path_facets": encode_value(self.f.to_json(), at="/ext/dtap/path_facets", lex=LexHints()),
                                  "file_stem": self.f.file_stem}}
        yield from self._redacted([header, *body])


# -------------------------------------------------------------------------------------------------- judge linkage
def _judge_needles(judge: Mapping[str, Any]) -> list[tuple[str, str]]:
    """``(pointer, normalised text)`` of every judge string of at least :data:`JUDGE_LINK_MIN` normalised characters in
    the judge's messages and metadata, in pointer order of first occurrence; duplicates removed."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()

    def walk(value: object, pointer: str) -> None:
        if isinstance(value, str):
            norm = normalise(value)
            if len(norm) >= JUDGE_LINK_MIN and norm not in seen:
                seen.add(norm)
                out.append((pointer, norm))
        elif isinstance(value, dict):
            for key, item in value.items():
                walk(item, f"{pointer}/{str(key).replace('~', '~0').replace('/', '~1')}")
        elif isinstance(value, list):
            for i, item in enumerate(value):
                walk(item, f"{pointer}/{i}")

    for key in ("task_message", "attack_message", "task_metadata", "attack_metadata"):
        if key in judge:
            walk(judge[key], f"/{key}")
    return out


def _haystacks(value: Mapping[str, Any]) -> list[tuple[str, str]]:
    """The normalised logged content of one attempt: one haystack per step and one for the final response."""
    out: list[tuple[str, str]] = []
    steps = value.get("trajectory")
    for i, step in enumerate(steps if isinstance(steps, list) else []):
        out.append((f"/trajectory/{i}", normalise(serialise(step))))
    final = _dict(value.get("traj_info")).get("agent_final_response")
    if isinstance(final, str):
        out.append(("/traj_info/agent_final_response", normalise(final)))
    return out
