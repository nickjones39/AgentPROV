"""Mapper ``inspect.eval``: one Inspect AI ``EvalSample`` member object -> AER ``aer/0.1`` (docs/architecture D.9.2).

One sample member object (``samples/<id>_epoch_<n>.json``) is one execution; the log's ``header.json`` member object is
its auxiliary artefact ``a1`` (``ctx.open_auxiliary("header")``). The mapping follows the normative table of D.9.2 row
by row; its implementation resolutions are recorded in D.9.5. What it relies on:

* **References are resolved, never re-grounded.** ``attachment://<hash>`` strings are replaced whole by the sample's
  ``attachments`` entry; ``ModelEvent.input_refs`` ``[start, end)`` ranges are expanded over ``events_data.messages``.
  A dangling reference raises ``dangling_source_ref`` and the affected field becomes ``unk`` (``lost``): no input,
  message or content is fabricated.
* **Message identity is the Inspect message id.** The same message held in ``messages``, ``events_data.messages``, a
  model event's inline input or a model output choice is one AER message when the ids are equal and the resolved
  contents are identical (JCS); otherwise it is a separate record.
* **Order comes from references and timestamps only** (``inspect.no_order_from_event_list@1``): causal ``after`` edges
  from ``generated_by``/``call``/``subject``, ``proto`` edges between successive state patches, and ``time`` edges
  between activities whose recorded intervals do not overlap (C.8.6). No ``pos`` edge is emitted: solvers insert
  messages into ``TaskState.messages``, so list position is not creation order.
* **Roles come from spans.** A model event in a span of a judge-role type (profile ``span_roles``) is an auxiliary
  call of a ``judge`` actor; every other model event is an agent call.

Pure (A-2): the output is a function of the unit's bytes, the header bytes, this code, the profile and the catalogues.
"""

from __future__ import annotations

import hashlib
import heapq
import json
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Final

from agentprov.adapters.code_verification import TWIN_SUFFIX, code_commits, rule_class
from agentprov.adapters.inspect.redact import RULE as REDACT_RULE
from agentprov.adapters.inspect.redact import Redactor, observed_model_ids, parse_redact_rules
from agentprov.adapters.surrogates import scrub_keys, surrogates
from agentprov.adapters.inspect.dialect import DIALECT_ID, FLAG_HEADER_NONFINITE, FLAG_MESSAGE_POOL, VARIANT, load_header
from agentprov.adapters.protocols import AerRecord, MappingContext
from agentprov.adapters.types import ExecutionUnit
from agentprov.aer.canon import LexHints, encode_value, json_pointer
from agentprov.aer.ids import part_id
from agentprov.errors import AgentProvError, IngestError, MalformedArtefact, UnsupportedVariant
from agentprov.ingest.limits import MIB
from agentprov.io.canonical import jcs_bytes

__all__ = ["ADAPTER_ID", "ADAPTER_VERSION", "CATALOGUES", "NAMESPACES", "InspectEvalMapper", "tool_status"]

ADAPTER_ID: Final = "inspect.eval"
ADAPTER_VERSION: Final = "0.1.0"
#: Catalogues this mapper cites; the header lists them at the shipped versions (C.3.1 ``rules``).
CATALOGUES: Final = ("aer", "inspect")
NAMESPACES: Final = {"inspect": "https://w3id.org/agentprov/ns/inspect#"}
ATTACHMENT: Final = "attachment://"
_RFC3339: Final = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?(Z|[+-][0-9]{2}:[0-9]{2})")
_HEX40: Final = re.compile(r"[0-9a-f]{40}")
_EVENT_POINTER: Final = re.compile(r"^/events/(0|[1-9][0-9]*)(?:/|$)")
#: regeneration-batch item 133 (pre-check PC-04): a cached model call's output in another scope is that scope's message
R_CACHED_OWN: Final = "inspect.cached_output_own_message@1"
_MEMBER_LABEL: Final = re.compile(r"samples/(.+)_epoch_[0-9]+\.json")
#: ToolCallError.type -> tool_execution.status (inspect.tool_error_status@1); ``approval`` is a denial, not a status.
_INVALID_TYPES: Final = frozenset({"parsing"})
#: Usage keys of ModelOutput.usage -> AER Usage (C.3.12).
_USAGE: Final = {
    "input_tokens": "input_tokens",
    "output_tokens": "output_tokens",
    "total_tokens": "total_tokens",
    "reasoning_tokens": "reasoning_tokens",
    "input_tokens_cache_read": "cache_read_tokens",
    "input_tokens_cache_write": "cache_write_tokens",
}
#: Approval / review decisions -> decision.verdict (inspect.approval_decision@1).
_VERDICTS: Final = {"approve": "allow", "modify": "modify", "reject": "deny", "escalate": "escalate",
                    "terminate": "terminate", "continue": "allow"}
#: Event types kept in ext.inspect.events of their host record (inspect.event_kept_in_ext@1); ``info`` is observed in
#: the band, the others raise ``inspect.unmapped_event``.
_KEPT_OBSERVED: Final = frozenset({"info"})
_KEPT_UNOBSERVED: Final = frozenset({"logger", "checkpoint", "anchor", "step", "subtask", "input", "interrupt", "error"})
_HANDLED: Final = frozenset({"span_begin", "span_end", "sample_init", "model", "tool", "state", "store", "score",
                             "score_edit", "sample_limit", "approval", "review", "compaction", "branch", "sandbox"})
_REF_FIELDS: Final = ("scope", "parent", "actor", "generated_by", "tools", "call", "subject", "authorised_by", "cause",
                      "revises", "spawned_by", "on_behalf_of", "retry_of", "original")


def tool_status(error: object) -> str | None:
    """``inspect.tool_error_status@1``: ``ok``, ``invalid``, ``error``; ``None`` for an approval denial."""
    if not isinstance(error, Mapping):
        return "ok"
    kind = error.get("type")
    if kind == "approval":
        return None
    return "invalid" if kind in _INVALID_TYPES else "error"


#: An inspect_ai release (optionally ``.devN`` and a local ``+...``), for the producer-version gate of item 25.
_RELEASE: Final = re.compile(r"(\d+)\.(\d+)\.(\d+)(?:\.dev\d+)?(?:\+[0-9A-Za-z.]+)?")
#: The last inspect_ai release whose ToolEvent has no ``message_id`` field (0.3.113 adds it; regeneration-batch item 25).
_LAST_WITHOUT_MESSAGE_ID: Final = (0, 3, 112)


def without_message_id(producer: object) -> bool:
    """``inspect.tool_event_no_message_id@1``: the producer is inspect_ai 0.3.112 or earlier, whose tool events carry no
    ``message_id``. A later or unparsable version is ``False`` (from 0.3.113 an absent key means ``None``: the log is
    written with ``exclude_none``)."""
    m = _RELEASE.fullmatch(producer) if isinstance(producer, str) else None
    return m is not None and tuple(int(g) for g in m.groups()) <= _LAST_WITHOUT_MESSAGE_ID


#: inspect_ai's ``DEFAULT_LOG_MODEL_API_CALLS`` (``_util/constants.py`` l. 46 at 53c1fa98; U6-b).
_LOG_MODEL_API_CALLS: Final = 5
#: The local ``+g<commit>`` of an inspect_ai development version (abbreviated hex).
_PRODUCER_COMMIT: Final = re.compile(r"\+g([0-9a-f]{7,40})(?:\.|$)")
#: Rules of regeneration-batch item 12 and U6 cited at D only for a producer their code list names, else through their
#: ``_unverified`` twin (D-24; D-375). The older rules of this catalogue keep their citations.
_PRODUCER_VERIFIED_RULES: Final = frozenset({
    "inspect.sample_run_by_harness@1", "inspect.tool_span_by_runtime@1", "inspect.sample_input_from_benchmark@1",
    "inspect.model_api_call_retention@1", "inspect.agent_model_from_role@1"})
#: Span types the eval runner opens itself (``_eval/task/run.py``; an untyped span's type is its name).
_RUN_SPANS: Final = frozenset({"init", "solvers", "scorers"})


#: The C.7.3 deny-list of placeholder strings (the AER validator's AER-V17 list).
_SENTINELS: Final = frozenset({"", "0", "unknown", "none", "null", "n/a", "na", "-"})


def _ambiguous_tool_names(records: Sequence[dict[str, Any]]) -> None:
    """Bug pass BF-22: a tool whose real name is on the C.7.3 deny-list (``none``, ``-``, ``unknown``, ...) keeps its
    verbatim name, declared ``unk ambiguous`` (C.7.2(2): a present value whose meaning cannot be told from a
    placeholder), instead of failing AER-V17 and collapsing the sample into an ``adapter_defect`` AER."""
    for rec in records:
        pointers: list[str] = []
        if rec.get("k") == "tool_execution" and isinstance(rec.get("name"), str) and rec["name"].lower() in _SENTINELS:
            pointers.append("/name")
        if rec.get("k") == "message":
            for k, part in enumerate(rec.get("parts") or ()):
                if (isinstance(part, dict) and part.get("t") in ("tool_call", "tool_result")
                        and isinstance(part.get("name"), str) and part["name"].lower() in _SENTINELS):
                    pointers.append(f"/parts/{k}/name")
        if pointers:
            unk = rec.setdefault("unk", {})
            for pointer in pointers:
                unk.setdefault(pointer, "ambiguous")


def producer_commit(producer: object) -> str | None:
    """The abbreviated commit of an inspect_ai development version (``0.3.247.dev69+g53c1fa98b`` -> ``53c1fa98b``)."""
    m = _PRODUCER_COMMIT.search(producer) if isinstance(producer, str) else None
    return m.group(1) if m else None


def verified_rule(rule_id: str, producer: object) -> str:
    """``rule_id`` when its catalogue code list names the producer's commit, else its I twin (D-24, D.5.4)."""
    if rule_id not in _PRODUCER_VERIFIED_RULES:
        return rule_id
    commit = producer_commit(producer)
    if commit is not None and any(c.startswith(commit) for c in code_commits("inspect").get(rule_id, ())):
        return rule_id
    name, _, version = rule_id.partition("@")
    return f"{name}{TWIN_SUFFIX}@{version}"


#: ``inspect.content_not_inlined@1`` (regeneration-batch item 28): a string whose UTF-8 encoding exceeds 1 MiB (C.2.1(6))
R_NOT_INLINED: Final = "inspect.content_not_inlined@1"
#: the eval fields the execution header keeps under ``ext.inspect`` (each located at ``a1`` ``/eval/<name>``)
_EVAL_HEADER_EXT: Final = ("run_id", "eval_id", "task_args")
_DATA_URI: Final = re.compile(r"data:([^;,]+)[;,]")


def _big(value: object) -> bool:
    return isinstance(value, str) and len(value) > MIB // 4 and len(value.encode("utf-8", "surrogatepass")) > MIB


def _not_inlined(value: str) -> dict[str, Any]:
    """``{"not_inlined": {sha256, bytes, media?}}`` of a string's UTF-8 bytes; ``media`` from a ``data:`` URI."""
    raw = value.encode("utf-8", "surrogatepass")
    out: dict[str, Any] = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    m = _DATA_URI.match(value)
    if m is not None:
        out["media"] = m.group(1)
    return {"not_inlined": out}


def _slim(value: object, pointer: str = "") -> tuple[Any, list[str]]:
    """``value`` with every string over 1 MiB replaced by :func:`_not_inlined`, and the replaced pointers."""
    if _big(value):
        assert isinstance(value, str)
        return _not_inlined(value), [pointer]
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        found: list[str] = []
        for k, v in value.items():
            out[k], sub = _slim(v, f"{pointer}/{json_pointer(str(k)).lstrip('/')}")
            found += sub
        return out, found
    if isinstance(value, list):
        items: list[Any] = []
        found = []
        for i, v in enumerate(value):
            item, sub = _slim(v, f"{pointer}/{i}")
            items.append(item)
            found += sub
        return items, found
    return value, []


def _p(*tokens: str | int) -> str:
    return json_pointer(*tokens)


def _utc(value: object) -> tuple[str | None, bool]:
    """(the recorded instant in UTC with ``Z``, whether it was converted from another offset); ``(None, False)`` when
    it is not an RFC 3339 instant. ``+00:00`` is re-encoded as ``Z``; any other offset is converted to UTC (C.8.3,
    regeneration-batch item 82, CD-25), keeping exactly the source's fractional digits (an offset is whole minutes)."""
    m = _RFC3339.fullmatch(value) if isinstance(value, str) else None
    if m is None:
        return None, False
    assert isinstance(value, str)
    offset = m.group(2)
    if offset == "Z":
        return value, False
    if offset == "+00:00":
        return value[:-6] + "Z", False
    try:
        whole = datetime.fromisoformat(value[:19] + offset).astimezone(UTC)
    except (ValueError, OverflowError):
        return None, False
    return whole.replace(tzinfo=None).isoformat(timespec="seconds") + (m.group(1) or "") + "Z", True


def _z(value: object) -> str | None:
    """A recorded instant in UTC with ``Z`` (C.8.3); ``None`` when it is not one."""
    return _utc(value)[0]


def _when(value: object) -> datetime | None:
    z = _z(value)
    if z is None:
        return None
    try:
        return datetime.fromisoformat(z.replace("Z", "+00:00"))
    except ValueError:
        return None


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _pmap(value: object) -> Mapping[str, Any]:
    """A profile table (profiles are frozen: ``MappingProxyType``)."""
    return value if isinstance(value, Mapping) else {}


def _pseq(value: object) -> tuple[Any, ...]:
    """A profile array (profiles are frozen: tuples)."""
    return tuple(value) if isinstance(value, list | tuple) else ()


def _same(a: object, b: object) -> bool:
    try:
        return jcs_bytes(_jcsable(a)) == jcs_bytes(_jcsable(b))
    except (TypeError, ValueError):
        return False


def _jcsable(value: object) -> object:
    """``value`` with every number made I-JSON safe (JCS comparison only; never written)."""
    lex = LexHints()
    return encode_value(value, at="", lex=lex)


class _Resolver:
    """``attachment://`` resolution over one sample (inspect_ai ``resolve_sample_attachments`` semantics)."""

    def __init__(self, attachments: Mapping[str, Any]) -> None:
        self.attachments = attachments

    def resolve(self, value: object) -> tuple[Any, list[str], bool]:
        """``(resolved value, attachment hashes used, dangling?)``. Only whole strings are references."""
        used: list[str] = []
        dangling = False

        def walk(v: object) -> object:
            nonlocal dangling
            if isinstance(v, str):
                if v.startswith(ATTACHMENT):
                    key = v[len(ATTACHMENT):]
                    target = self.attachments.get(key)
                    if isinstance(target, str):
                        if key not in used:
                            used.append(key)
                        return target
                    dangling = True
                return v
            if isinstance(v, dict):
                return {k: walk(x) for k, x in v.items()}
            if isinstance(v, list):
                return [walk(x) for x in v]
            return v

        return walk(value), used, dangling


class _Rec:
    """A record under construction: fields, evidence overrides, scoped rules, unknowns and lexical hints."""

    def __init__(self, **fields: Any) -> None:
        self.data: dict[str, Any] = dict(fields)
        self.lex = LexHints()
        self.evf: dict[str, str] = {}
        self.rules: list[str] = []
        self.unk: dict[str, str] = {}
        self.src: list[dict[str, Any]] = []
        self.ext: dict[str, Any] = {}
        self.after: list[dict[str, str]] = []
        self.t_src: dict[str, object] = {}  # the verbatim instant behind each typed t slot (item 82)

    @property
    def id(self) -> str:
        return str(self.data["id"])

    def enc(self, value: object, pointer: str) -> Any:
        return encode_value(value, at=pointer, lex=self.lex)

    def set(self, name: str, value: object) -> None:
        self.data[name] = self.enc(value, "/" + name)

    def tag(self, pointer: str, cls: str, rule: str | None = None) -> None:
        self.evf[pointer] = cls
        if rule is not None and rule not in self.rules:
            self.rules.append(rule)

    def cite(self, rule: str) -> None:
        if rule not in self.rules:
            self.rules.append(rule)

    def loc(self, a: str, pointer: str) -> None:
        entry = {"a": a, "p": pointer}
        if entry not in self.src:
            self.src.append(entry)

    def x(self, key: str, value: object) -> None:
        """``ext.inspect.<key>`` (encoded)."""
        self.ext[key] = self.enc(value, _p("ext", "inspect", key))

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
            ext["inspect"] = dict(self.ext)
        if self.lex.flt:
            ext["lex"] = {"flt": sorted(self.lex.flt)}
        if ext:
            out["ext"] = ext
        if not _has_bare_o(out):
            out.pop("by", None)
        return out


def _has_bare_o(record: Mapping[str, Any]) -> bool:
    """Whether some effective tag of ``record`` is a bare ``O`` (then ``by`` is required, C.6.2)."""
    evf = record.get("evf") or {}
    return record.get("ev") == "O" or any(v == "O" for v in evf.values())


@dataclass
class _Msg:
    """One AER message: its local id, the Inspect value (resolved) and where it is recorded."""

    local: str
    value: dict[str, Any]
    src: list[str] = field(default_factory=list)
    attachments: list[str] = field(default_factory=list)
    generated_by: str | None = None
    generator_kind: str | None = None  # "agent" | "judge" | "tool" | "decision"
    scope: str | None = None
    consumer_key: tuple[Any, ...] | None = None
    emitted: bool = False
    #: an extra rule the ``generated_by`` link rests on (the call-id fallback of regeneration-batch item 16 (b))
    link_rule: str | None = None
    #: the scope of the first model event whose output holds this message (regeneration-batch item 133)
    produced_scope: str | None = None
    #: the scope a cached model call returned this copy in, when another scope's call produced the message (item 133)
    split_scope: str | None = None


@dataclass
class _Node:
    rec: _Rec
    key: tuple[Any, ...]
    activity: bool = False
    start: datetime | None = None
    end: datetime | None = None


class InspectEvalMapper:
    """``Mapper`` for ``inspect.eval`` (D.2.4, D.9.2)."""

    mapper_id: Final = ADAPTER_ID
    version: Final = ADAPTER_VERSION
    accepts: Final = frozenset({(DIALECT_ID, VARIANT)})
    namespaces: Final = NAMESPACES
    catalogues: Final = CATALOGUES

    def map(self, unit: ExecutionUnit, ctx: MappingContext) -> Iterator[AerRecord]:
        yield from _Build(unit, ctx).run()

    @staticmethod
    def prov_primary(flags: frozenset[str]) -> str:
        """Sample member objects are written by the producing harness (inspect_ai): ``native`` (R-22)."""
        return "native"

    def degenerate_header(self, unit: ExecutionUnit, ctx: MappingContext, *, issue_code: str, detail: str) -> dict[str, Any]:
        """The header of a degenerate AER (D.2.8 case 3), with its error issue reported through ``ctx``."""
        artifacts = [unit.primary.artefact.to_json()]
        artifacts += [ref.to_json() for _role, ref in sorted(unit.auxiliary.items())]
        family = ctx.profile.family_table()
        benchmark = family.get("benchmark")
        task: dict[str, Any] = {"benchmark": str(benchmark)} if isinstance(benchmark, str) else {}
        unk = {"/instrumentation": "not_recorded"}
        evf: dict[str, str] = {}
        rules = [ctx.rule("inspect.header_applies_to_samples@1", "/task/benchmark")]
        value = unit.primary.value
        sample_id = value.get("id") if isinstance(value, dict) else None
        src: list[dict[str, Any]] = []
        if isinstance(sample_id, int | str) and not isinstance(sample_id, bool) and sample_id != "":
            task["task_id"] = str(sample_id)
            src.append({"a": "a0", "p": "/id"})
        else:
            label = str(unit.primary.artefact.origin.data.get("label", ""))
            match = _MEMBER_LABEL.fullmatch(label)
            if match is None:
                raise MalformedArtefact("a sample unit's member label does not name a sample")
            task["task_id"] = match.group(1)
            evf["/task/task_id"] = "D"
            rules.append(ctx.rule("inspect.sample_member_label@1", "/task/task_id"))
            src.append({"a": "a0", "o": "/label"})
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
            "evf": {"/task/benchmark": "D", **evf},
            "rule": rules,
            "src": src,
            "unk": unk,
        }
        ctx.issue(issue_code, ids=["exec"], rule=ctx.rule("inspect.model_event_is_call@1"), severity="error", detail=detail)
        return header


class _Build:
    """One mapping run: every record is built first, then ordered topologically (C.2.1 item 5)."""

    def __init__(self, unit: ExecutionUnit, ctx: MappingContext) -> None:
        item = unit.primary
        if not isinstance(item.value, dict):
            raise MalformedArtefact("the located item is not an Inspect EvalSample object")
        if FLAG_MESSAGE_POOL in item.flags:
            raise UnsupportedVariant("interim message_pool sample shape: its references are not re-grounded")
        self.unit = unit
        self.ctx = ctx
        sample, keys_s = scrub_keys(item.value)  # item 7 (F-01, D-378): keys cannot be $utf16-wrapped
        self.s: dict[str, Any] = sample
        ref = unit.auxiliary.get("header")
        try:
            raw = ctx.open_auxiliary("header")
            if ref is None or len(raw) != ref.bytes or hashlib.sha256(raw).hexdigest() != ref.sha256:
                raise MalformedArtefact("header.json bytes do not match the unit's auxiliary artefact a1")
            header, _nonfinite = load_header(raw)  # RH-1: a NaN metric under /results is tolerated, never mapped
        except (AgentProvError, IngestError) as exc:
            raise MalformedArtefact("the log's header.json is unavailable or unreadable") from exc
        if not isinstance(header, dict) or not isinstance(header.get("eval"), dict):
            raise MalformedArtefact("header.json is not an Inspect log header")
        header, keys_h = scrub_keys(header)
        self.surrogate_keys = keys_s or keys_h
        self.h: dict[str, Any] = header
        self.ev: dict[str, Any] = header["eval"]
        self.family = ctx.profile.family_table()
        events = self.s.get("events")
        if not isinstance(events, list) or not all(isinstance(e, dict) and isinstance(e.get("event"), str) for e in events):
            raise MalformedArtefact("events is not an array of event objects")
        self.events: list[dict[str, Any]] = events
        attachments = self.s.get("attachments", {})
        if not isinstance(attachments, dict):
            raise MalformedArtefact("attachments is not an object")
        self.res = _Resolver(attachments)
        self.nodes: dict[str, _Node] = {}
        self.order: list[str] = []
        self.counters: dict[str, int] = {}
        self.issues: list[tuple[str, list[str], str, str, str | None]] = []
        self.roles: dict[str, str] = {str(k): str(v) for k, v in _pmap(self.family.get("span_roles")).items()}
        if FLAG_HEADER_NONFINITE in item.flags:  # RH-1 (D.9.5): reported, never mapped
            self.defer("inspect.header_nonfinite", ["run"], "inspect.header_applies_to_samples@1", severity="info",
                       detail=f"header.json holds {_nonfinite} non-finite number(s) under /results or /stats (Inspect "
                              "writes NaN for an undefined metric); parsed as $float, not mapped")
        #: the react agent's submit tool names (profile ``submit_tools``; regeneration-batch item 16 (c))
        self.submit_tools: frozenset[str] = frozenset(str(n) for n in _pseq(self.family.get("submit_tools")))
        #: records with a string over 1 MiB not inlined (item 28; one info issue lists them)
        self.not_inlined: list[str] = []
        self.header_ext: list[tuple[str, object]] = []
        #: tool events have no ``message_id`` at this producer version (regeneration-batch item 25 (a))
        self.no_message_id = without_message_id(_dict(self.ev.get("packages")).get("inspect_ai"))
        self.producer = _dict(self.ev.get("packages")).get("inspect_ai")

    # ---------------------------------------------------------------------------------------------- helpers
    def R(self, rule_id: str, pointer: str | None = None) -> str:  # noqa: N802 - mirrors MappingContext.rule
        return self.ctx.rule(rule_id, pointer)

    def V(self, rule_id: str) -> str:  # noqa: N802
        """``rule_id`` or its twin for this log's producer (:func:`verified_rule`)."""
        return verified_rule(rule_id, self.producer)

    def C(self, rule_id: str) -> str:  # noqa: N802
        """The class of :meth:`V`'s rule."""
        return rule_class(self.V(rule_id))

    def issue(self, code: str, ids: Sequence[str], rule: str, *, severity: str = "warning", detail: str | None = None) -> None:
        self.ctx.issue(code, ids=list(ids), rule=self.R(rule), severity=severity, detail=detail)  # type: ignore[arg-type]

    def next_id(self, prefix: str) -> str:
        n = self.counters.get(prefix, 0)
        self.counters[prefix] = n + 1
        return f"{prefix}{n}"

    def add(self, rec: _Rec, key: tuple[Any, ...], *, activity: bool = False) -> _Node:
        node = _Node(rec, key, activity)
        self.nodes[rec.id] = node
        return node

    def d(self, rec: _Rec, pointer: str, rule: str) -> None:
        """Tag ``pointer`` D under ``rule`` scoped to it."""
        rec.tag(pointer, "D", self.R(rule, pointer))

    def json(self, rec: _Rec, value: object, pointer: str) -> Any:
        """A Json-position value, encoded, with its strings over 1 MiB not inlined (item 28; each tagged D)."""
        slim, replaced = _slim(value)
        for rel in replaced:
            self.d(rec, pointer + rel, R_NOT_INLINED)
        if replaced:
            self.not_inlined.append(rec.id)
        return rec.enc(slim, pointer)

    def big_part(self, rec: _Rec, kind: str, value: str, at: str) -> dict[str, Any]:
        """A part whose typed string exceeds 1 MiB: an ``other`` part of the source ``kind`` whose value is the digest
        (item 28; a typed field cannot hold it, and only ``ambiguous`` may stand beside a null)."""
        return {"t": "other", "type": kind, "value": self.json(rec, value, f"{at}/value")}

    def t(self, rec: _Rec, start: object, end: object, base: str, start_key: str, end_key: str | None) -> None:
        """``t {start, end}`` from recorded instants; unparseable values go to ``t.raw`` and are declared unknown."""
        for slot, value, key in (("start", start, start_key), ("end", end, end_key)):
            if key is None:
                continue
            if value is None:
                rec.unk[f"/t/{slot}"] = "not_recorded"
                continue
            self.t_slot(rec, slot, value, f"{base}/{key}")

    def t_slot(self, rec: _Rec, slot: str, value: object, pointer: str) -> None:
        """One recorded instant at ``t.<slot>``: in UTC, with the verbatim value in ``t.raw`` when it was converted from
        another offset; a value that is not an instant goes to ``t.raw`` only, declared unknown (C.8.3). An absent value
        adds nothing (the callers declare it where the slot is expected)."""
        if value is None:
            return
        z, converted = _utc(value)
        t = rec.data.setdefault("t", {})
        if z is None or converted:
            t.setdefault("raw", {})[slot] = rec.enc(value, f"/t/raw/{slot}")
        if z is None:
            rec.unk[f"/t/{slot}"] = "not_recorded"
            return
        t[slot] = z
        rec.t_src[slot] = value
        rec.loc("a0", pointer)

    def ts_key(self, value: object) -> float:
        when = _when(value)
        return when.timestamp() if when is not None else float("inf")

    # ---------------------------------------------------------------------------------------------- run
    def run(self) -> Iterator[dict[str, Any]]:
        self._index_spans()
        self._messages()
        self._actors()
        self._scopes()
        self._fixtures()
        self._events()
        self._messages_out()
        self._scores_without_events()
        self._accounting_issues()
        self.header_ext = self._header_ext()
        if any(_slim(value)[1] for _name, value in self.header_ext):
            self.not_inlined.append("exec")  # the header is built last; its ids join the issue before it is deferred
        if self.not_inlined:
            self.defer("inspect.content_not_inlined", sorted(set(self.not_inlined)), R_NOT_INLINED, severity="info")
        self._contradictory_times()
        self._order()
        self._time_edges()
        header = self._header()
        records = [header, *(self.nodes[rid].rec.done() for rid in self.order)]
        _ambiguous_tool_names(records)
        self._redact(records)
        surrogates(self, records, "inspect")
        for code, ids, rule, severity, detail in self.issues:
            self.ctx.issue(code, ids=ids, rule=rule, severity=severity, detail=detail)  # type: ignore[arg-type]
        yield from records

    def _redact(self, records: Sequence[dict[str, Any]]) -> None:
        """D-182 (with R-10p-3): the profile's ``[[family.inspect.redact]]`` rules over the finished records
        (:mod:`agentprov.adapters.inspect.redact`); one info issue counts the redacted pointers."""
        rules = parse_redact_rules(_pseq(self.family.get("redact")), f"profile {self.ctx.profile.id!r}")
        if not rules:
            return
        pool = _dict(self.s.get("events_data")).get("messages")
        messages = [*_list(self.s.get("messages")), *(_list(pool) if pool is not None else [])]
        for e in self.events:
            if e["event"] == "model":
                messages += [c.get("message") for c in _list(_dict(e.get("output")).get("choices")) if isinstance(c, dict)]
        redactor = Redactor(self.ctx.profile.id, self.ctx.profile.version, rules,
                            observed_model_ids(self.h, self.events, [m for m in messages if isinstance(m, dict)]))
        changed: list[str] = []
        n = 0
        for record in records:
            done = redactor.apply(record, lambda p: self.R(REDACT_RULE, p))
            if done:
                changed.append(str(record["id"]))
                n += len(done)
        if changed:
            self.defer("inspect.value_redacted", changed, REDACT_RULE, severity="info",
                       detail=f"{n} values redacted by the profile's redact rules (D-182)")

    def defer(self, code: str, ids: Sequence[str], rule: str, *, severity: str = "warning", detail: str | None = None) -> None:
        """Seal issues are reported in a deterministic order after mapping (ids are known only then)."""
        self.issues.append((code, list(ids), self.R(rule), severity, detail))

    # ---------------------------------------------------------------------------------------------- spans
    def _index_spans(self) -> None:
        self.spans: dict[str, dict[str, Any]] = {}  # span id -> {"begin": k, "end": k|None, "scope": local id}
        for k, e in enumerate(self.events):
            if e["event"] == "span_begin" and isinstance(e.get("id"), str) and e["id"] not in self.spans:
                self.spans[e["id"]] = {"begin": k, "end": None, "scope": self.next_id("sc")}
        for k, e in enumerate(self.events):
            if e["event"] == "span_end" and isinstance(e.get("id"), str) and e["id"] in self.spans:
                if self.spans[e["id"]]["end"] is None:
                    self.spans[e["id"]]["end"] = k
        self.tool_spawned: dict[str, int] = {}  # span id -> tool event index (agent_span_id)
        for k, e in enumerate(self.events):
            if (e["event"] == "tool" and isinstance(e.get("agent_span_id"), str) and e["agent_span_id"] in self.spans
                    and tool_status(e.get("error")) is not None):
                self.tool_spawned.setdefault(e["agent_span_id"], k)

    def span_type(self, span_id: object) -> str | None:
        span = self.spans.get(span_id) if isinstance(span_id, str) else None
        if span is None:
            return None
        value = self.events[span["begin"]].get("type")
        return value if isinstance(value, str) else None

    def role_of(self, span_id: object) -> str | None:
        """The profile role (``agent``/``judge``) of the nearest span (itself included) whose type has one."""
        seen: set[str] = set()
        cursor = span_id
        while isinstance(cursor, str) and cursor in self.spans and cursor not in seen:
            seen.add(cursor)
            role = self.roles.get(self.span_type(cursor) or "")
            if role is not None:
                return role
            cursor = self.events[self.spans[cursor]["begin"]].get("parent_id")
        return None

    def scope_of(self, event: Mapping[str, Any]) -> str:
        span_id = event.get("span_id")
        span = self.spans.get(span_id) if isinstance(span_id, str) else None
        return span["scope"] if span is not None else "run"

    # ---------------------------------------------------------------------------------------------- messages
    def _register(self, value: object, pointer: str, prefix: str, *, cached_in: str | None = None) -> _Msg | None:
        """The AER message for one recorded ChatMessage (by Inspect id and identical resolved content).

        Regeneration-batch item 133 (``inspect.cached_output_own_message@1``): the output of a model event served from
        the cache (``cached_in``, its scope) whose message another scope's model event produced is that scope's own
        message, generated by the cached call; later holders in that scope resolve to it."""
        if not isinstance(value, dict) or not isinstance(value.get("role"), str):
            raise MalformedArtefact("a chat message is not an object with a role")
        resolved, used, dangling = self.res.resolve(value)
        if dangling:
            return None
        mid = resolved.get("id")
        here = self._pointer_scope(pointer)
        if isinstance(mid, str):
            own = self.split.get((mid, here)) if here is not None else None
            if own is not None and _same(own.value, resolved):
                self._hold(own, pointer, used)
                return own
            for msg in self.by_inspect_id.get(mid, []):
                if _same(msg.value, resolved):
                    if cached_in is not None and msg.produced_scope not in (None, cached_in):
                        copy = _Msg(self.next_id(prefix), resolved, [pointer], list(used), produced_scope=cached_in,
                                    split_scope=cached_in)
                        self.msgs.append(copy)
                        self.split[(mid, cached_in)] = copy
                        return copy
                    self._hold(msg, pointer, used)
                    if prefix == "o" and msg.produced_scope is None:
                        msg.produced_scope = here
                    return msg
        msg = _Msg(self.next_id(prefix), resolved, [pointer], list(used), produced_scope=here if prefix == "o" else None)
        self.msgs.append(msg)
        if isinstance(mid, str):
            self.by_inspect_id.setdefault(mid, []).append(msg)
        return msg

    @staticmethod
    def _hold(msg: _Msg, pointer: str, used: Sequence[str]) -> None:
        if pointer not in msg.src:
            msg.src.append(pointer)
        for h in used:
            if h not in msg.attachments:
                msg.attachments.append(h)

    def _pointer_scope(self, pointer: str) -> str | None:
        """The scope of the event a ``/events/<k>/...`` pointer is in; ``None`` for any other pointer."""
        m = _EVENT_POINTER.match(pointer)
        return self.scope_of(self.events[int(m.group(1))]) if m is not None else None

    def _scoped(self, msg: _Msg, scope: str) -> _Msg:
        """``msg``, or the copy a cached model call returned it as in ``scope`` (item 133)."""
        mid = msg.value.get("id")
        return self.split.get((mid, scope), msg) if isinstance(mid, str) else msg

    def _messages(self) -> None:
        self.msgs: list[_Msg] = []
        self.by_inspect_id: dict[str, list[_Msg]] = {}
        self.split: dict[tuple[str, str], _Msg] = {}  # (Inspect id, scope) -> a cached call's own copy (item 133)
        messages = self.s.get("messages")
        if not isinstance(messages, list):
            raise MalformedArtefact("messages is not an array")
        for i, value in enumerate(messages):
            msg = self._register(value, _p("messages", i), "m")
            if msg is None:
                self.defer("dangling_source_ref", ["run"], "inspect.model_event_is_call@1", detail=f"/messages/{i}")
        data = _dict(self.s.get("events_data"))
        pool = data.get("messages", [])
        if "events_data" in self.s and not isinstance(pool, list):
            raise MalformedArtefact("events_data.messages is not an array")
        self.pool: list[_Msg | None] = []
        for j, value in enumerate(pool or []):
            self.pool.append(self._register(value, _p("events_data", "messages", j), "p"))
        # inline inputs and output choices of model events are registered before any event is mapped, so that every
        # tool call part is known when tool, approval and review events are (D.9.5)
        self.inline: dict[tuple[int, int], _Msg | None] = {}
        self.outputs: dict[tuple[int, int], _Msg | None] = {}
        for k, e in enumerate(self.events):
            if e["event"] != "model":
                continue
            if e.get("input_refs") is None and isinstance(e.get("input"), list):
                for i, value in enumerate(e["input"]):
                    self.inline[(k, i)] = self._register(value, _p("events", k, "input", i), "p")
            choices = _list(_dict(e.get("output")).get("choices"))
            if e.get("error") is not None and not choices:
                continue
            cached_in = self.scope_of(e) if e.get("cache") == "read" else None
            for c, choice in enumerate(choices):
                if isinstance(choice, dict):
                    pointer = _p("events", k, "output", "choices", c, "message")
                    self.outputs[(k, c)] = self._register(choice.get("message"), pointer, "o", cached_in=cached_in)

    # ---------------------------------------------------------------------------------------------- actors
    def _actors(self) -> None:
        ev = self.ev
        agent = _Rec(k="actor", id="agent", kind="llm_agent", ev="O", by="config")
        role = self._agent_model_role()
        if role is not None:  # R-10p-2: the agent's calls use one model role (get_model(role=...)); its model is the role's
            role_cfg = ev["model_roles"][role]
            rule = self.V("inspect.agent_model_from_role@1")
            agent.data["model"] = {"requested": role_cfg["model"]}
            agent.loc("a1", _p("eval", "model_roles", role, "model"))
            agent.tag("/model", rule_class(rule), self.R(rule, "/model"))
            if isinstance(role_cfg.get("config"), dict):
                agent.set("params", role_cfg["config"])
                agent.loc("a1", _p("eval", "model_roles", role, "config"))
                agent.tag("/params", rule_class(rule), self.R(rule, "/params"))
            else:
                agent.unk["/params"] = "not_recorded"
        else:
            model = ev.get("model")
            if isinstance(model, str) and model:
                agent.data["model"] = {"requested": model}
                agent.loc("a1", "/eval/model")
            else:
                agent.unk["/model"] = "not_recorded"
            config = ev.get("model_generate_config")
            if isinstance(config, dict):
                agent.set("params", config)
                agent.loc("a1", "/eval/model_generate_config")
            else:
                agent.unk["/params"] = "not_recorded"
        if not agent.src:
            agent.data["ev"] = "D"
            agent.cite(self.R("inspect.header_applies_to_samples@1"))
        self.add(agent, (0, 0))

        harness = _Rec(k="actor", id="harness", kind="harness", name="inspect_ai", ev="O", by="source")
        packages = _dict(ev.get("packages"))
        producer = packages.get("inspect_ai")
        if isinstance(producer, str):
            harness.data["code"] = {"dist": "inspect_ai", "dist_version": producer}
            harness.loc("a1", "/eval/packages/inspect_ai")
            harness.unk["/code/commit"] = "not_recorded"
        else:
            harness.unk["/code"] = "not_recorded"
            harness.data["ev"] = "D"
            harness.cite(self.R("inspect.header_applies_to_samples@1"))
        self.add(harness, (0, 1))

        bench = _Rec(k="actor", id="bench", kind="benchmark", ev="O", by="source")
        benchmark = self.family.get("benchmark")
        if isinstance(benchmark, str):
            bench.data["name"] = benchmark
            self.d(bench, "/name", "inspect.header_applies_to_samples@1")
        code: dict[str, Any] = {}
        evals = packages.get("inspect_evals")
        if isinstance(evals, str):
            code["dist"] = "inspect_evals"
            code["dist_version"] = evals
            bench.loc("a1", "/eval/packages/inspect_evals")
        revision = ev.get("revision")
        if isinstance(revision, dict):
            origin, commit = revision.get("origin"), revision.get("commit")
            if isinstance(origin, str) and origin:
                code["repo"] = origin
            if isinstance(commit, str) and _HEX40.fullmatch(commit):
                code["commit"] = commit
            elif isinstance(commit, str):
                bench.unk["/code/commit"] = "ambiguous"  # abbreviated: does not identify a commit (D.9.5)
                bench.cite(self.R("inspect.header_applies_to_samples@1", "/code/commit"))
            bench.x("revision", revision)
            bench.loc("a1", "/eval/revision")
        if code:
            bench.data["code"] = code
        else:
            bench.unk["/code"] = "not_recorded"
        task_version = ev.get("task_version")
        if isinstance(task_version, str) and task_version and task_version != "0":  # U6-a: the task's version label
            bench.data["version"] = task_version
            bench.loc("a1", "/eval/task_version")
        elif isinstance(task_version, int) and not isinstance(task_version, bool) and task_version > 0:
            bench.data["version"] = str(task_version)
            bench.loc("a1", "/eval/task_version")
            self.d(bench, "/version", "inspect.task_version_label@1")
        else:  # absent, or the producer's default 0, which is no label (C.7.3)
            bench.unk["/version"] = "not_recorded"
            if "task_version" in ev:
                bench.x("task_version", ev["task_version"])
                bench.loc("a1", "/eval/task_version")
            bench.cite(self.R("inspect.task_version_label@1", "/version"))
        if not bench.src:
            bench.loc("a1", "/eval")
        self.add(bench, (0, 2))

        self.judges: dict[str, str] = {}  # judge model string -> actor id
        n_tools = sum(1 for e in self.events if e["event"] in ("tool", "sandbox"))
        self._has_runtime = bool(n_tools or any(m.value.get("role") == "tool" for m in self.msgs))
        if self._has_runtime:
            env = _Rec(k="actor", id="env", kind="tool_runtime", name="inspect_ai", ev="D")
            env.cite(self.R("inspect.tool_event_is_execution@1"))
            self.add(env, (0, 3))
        for k, e in enumerate(self.events):
            if e["event"] == "model" and self.role_of(e.get("span_id")) == "judge":
                model_name = e.get("model")
                if not isinstance(model_name, str) or not model_name:
                    raise MalformedArtefact("a judge model event names no model")
                if model_name not in self.judges:
                    jid = f"judge{len(self.judges)}"
                    self.judges[model_name] = jid
                    judge = _Rec(k="actor", id=jid, kind="judge", model={"requested": model_name}, ev="O", by="source")
                    judge.loc("a0", _p("events", k, "model"))
                    self.d(judge, "/kind", "inspect.span_is_scope@1")
                    judge.unk["/code"] = "not_recorded"  # U6-a: the scorer's code and version are not logged
                    judge.unk["/version"] = "not_recorded"
                    self.add(judge, (0, 4 + len(self.judges)))
        self.users: set[str] = set()

    def _agent_model_role(self) -> str | None:
        """R-10p-2: the one model role every agent model event of the sample names, when ``eval.model_roles`` gives it a
        model (else ``None``: the agent's model is ``eval.model``)."""
        roles = {e.get("role") for e in self.events if e["event"] == "model" and self.role_of(e.get("span_id")) != "judge"}
        if len(roles) != 1:
            return None
        (role,) = roles
        config = _dict(_dict(self.ev.get("model_roles")).get(role)) if isinstance(role, str) else {}
        return role if isinstance(role, str) and isinstance(config.get("model"), str) and config["model"] else None

    def _approver(self, name: object) -> str:
        """The actor of an approval/review: ``user`` for a human approver, else the harness (a policy approver)."""
        if name == "human":
            if "user" not in self.nodes:
                user = _Rec(k="actor", id="user", kind="user", name="human", ev="D")
                user.cite(self.R("inspect.approval_decision@1"))
                self.add(user, (0, 100))
            return "user"
        return "harness"

    # ---------------------------------------------------------------------------------------------- scopes
    def _scopes(self) -> None:
        s = self.s
        run = _Rec(k="scope", id="run", kind="run", ev="O", by="source")
        run.data["actor"] = "harness"  # item 12 (c3): task_run_sample runs the sample
        run.tag("/actor", self.C("inspect.sample_run_by_harness@1"), self.R(self.V("inspect.sample_run_by_harness@1"), "/actor"))
        self.t(run, s.get("started_at"), s.get("completed_at"), "", "started_at", "completed_at")
        total = s.get("total_time")
        if isinstance(total, int | float) and not isinstance(total, bool) and total >= 0:
            run.data.setdefault("t", {})["dur_s"] = run.enc(total, "/t/dur_s")
            run.data["t"]["dur_clock"] = "monotonic"
            run.loc("a0", "/total_time")
        for key in ("working_time", "model_usage", "role_usage", "turn_count", "error_retries"):
            if key in s:
                run.x(key, s[key])
        if not run.src:
            run.loc("a0", "")
        self.run_scope = run
        self.add(run, (1, -1))
        for span_id, span in self.spans.items():
            k = span["begin"]
            e = self.events[k]
            stype = e.get("type")
            role = self.roles.get(stype) if isinstance(stype, str) else None
            rec = _Rec(k="scope", id=span["scope"], ev="O", by="source")
            rec.loc("a0", _p("events", k))
            if span_id in self.tool_spawned:
                rec.data["kind"] = "subagent"
                rec.data["spawned_by"] = f"__te{self.tool_spawned[span_id]}"  # patched once the execution has its id
                self.d(rec, "/kind", "inspect.agent_span_is_subagent@1")
                self.d(rec, "/spawned_by", "inspect.agent_span_is_subagent@1")
                rec.data["actor"] = "agent"
                self.d(rec, "/actor", "inspect.agent_span_is_subagent@1")
            elif role == "agent":
                rec.data["kind"] = "agent_invocation"
                rec.data["actor"] = "agent"
                self.d(rec, "/kind", "inspect.span_is_scope@1")
                self.d(rec, "/actor", "inspect.span_is_scope@1")
            elif role == "judge":
                rec.data["kind"] = "other"
                rec.data["subtype"] = "inspect.scorer"
                self.d(rec, "/kind", "inspect.span_is_scope@1")
                self.d(rec, "/subtype", "inspect.span_is_scope@1")
            else:
                rec.data["kind"] = "other"
                rec.data["subtype"] = "inspect.span"
                self.d(rec, "/kind", "inspect.span_is_scope@1")
                self.d(rec, "/subtype", "inspect.span_is_scope@1")
            actor_rule = None
            if span_id not in self.tool_spawned and role != "agent":  # item 12 (c3): who performs the span
                if stype == "scorer" or (stype in _RUN_SPANS and e.get("name") == stype):
                    actor_rule, actor = "inspect.sample_run_by_harness@1", "harness"
                elif stype == "tool" and self._has_runtime:
                    actor_rule, actor = "inspect.tool_span_by_runtime@1", "env"
            if actor_rule is not None:
                rec.data["actor"] = actor
                rec.tag("/actor", self.C(actor_rule), self.R(self.V(actor_rule), "/actor"))
            parent = e.get("parent_id")
            if isinstance(parent, str) and parent in self.spans:
                rec.data["parent"] = self.spans[parent]["scope"]
                rec.loc("a0", _p("events", k, "parent_id"))
            else:
                rec.data["parent"] = "run"
                self.d(rec, "/parent", "inspect.span_is_scope@1")
                if isinstance(parent, str):
                    self.defer("dangling_source_ref", [span["scope"]], "inspect.span_is_scope@1",
                               detail=_p("events", k, "parent_id"))
            end = span["end"]
            self.t(rec, e.get("timestamp"), self.events[end].get("timestamp") if end is not None else None,
                   _p("events", k), "timestamp", None)
            if end is not None:
                self.t_slot(rec, "end", self.events[end].get("timestamp"), _p("events", end, "timestamp"))
            else:
                rec.unk["/t/end"] = "not_recorded"
            rec.x("span", {"id": span_id, "name": e.get("name"), "type": stype})
            self.add(rec, (1, k))

    def host_scope(self, event: Mapping[str, Any]) -> _Rec:
        return self.nodes[self.scope_of(event)].rec

    # ---------------------------------------------------------------------------------------------- fixtures
    def _fixtures(self) -> None:
        s = self.s
        init = next((k for k, e in enumerate(self.events) if e["event"] == "sample_init"), None)
        self.fx_tools: str | None = None
        self.fx_tools_value: Any = None
        if "input" in s:
            value, used, dangling = self.res.resolve(s["input"])
            if dangling:
                self.defer("dangling_source_ref", ["run"], "inspect.sample_init_fixtures@1", detail="/input")
            else:
                fx = _Rec(k="fixture", id=self.next_id("fx"), kind="task_prompt", actor="bench", ev="O", by="benchmark")
                fx.set("content", value)
                fx.loc("a0", "/input")
                for h in used:
                    fx.loc("a0", _p("attachments", h))
                if init is not None:
                    fx.loc("a0", _p("events", init, "sample", "input"))
                self.d(fx, "/kind", "inspect.sample_init_fixtures@1")
                self.d(fx, "/actor", "inspect.sample_init_fixtures@1")
                self.add(fx, (2, 0))
        first = next((k for k, e in enumerate(self.events)
                      if e["event"] == "model" and self.role_of(e.get("span_id")) != "judge" and isinstance(e.get("tools"), list)),
                     None)
        if first is not None:
            value, used, dangling = self.res.resolve(self.events[first]["tools"])
            if dangling:
                self.defer("dangling_source_ref", ["run"], "inspect.sample_init_fixtures@1", detail=_p("events", first, "tools"))
            else:
                fx = _Rec(k="fixture", id=self.next_id("fx"), kind="tool_definitions", ev="O", by="source")
                fx.set("content", value)
                fx.loc("a0", _p("events", first, "tools"))
                for h in used:
                    fx.loc("a0", _p("attachments", h))
                self.d(fx, "/kind", "inspect.sample_init_fixtures@1")
                self.add(fx, (2, 1))
                self.fx_tools, self.fx_tools_value = fx.id, value
        keys = [str(k) for k in _pseq(self.family.get("ground_truth_metadata"))]
        metadata = _dict(s.get("metadata"))
        present = [k for k in keys if k in metadata]
        self.gt_fixture = False
        if present:
            value, used, dangling = self.res.resolve({k: metadata[k] for k in present})
            if dangling:
                # Regeneration-batch item 83 (CD-26): as for the siblings above, and the keys stay in the header's
                # sample_metadata (as far as they resolve) instead of vanishing with the fixture.
                self.defer("dangling_source_ref", ["run"], "inspect.sample_init_fixtures@1", detail="/metadata")
            else:
                self.gt_fixture = True
                fx = _Rec(k="fixture", id=self.next_id("fx"), kind="ground_truth", actor="bench", ev="O", by="benchmark")
                fx.set("content", value)
                for k in present:
                    fx.loc("a0", _p("metadata", k))
                for h in used:
                    fx.loc("a0", _p("attachments", h))
                self.d(fx, "/kind", "inspect.sample_init_fixtures@1")
                self.d(fx, "/actor", "inspect.sample_init_fixtures@1")
                self.add(fx, (2, 2))

    # ---------------------------------------------------------------------------------------------- events
    def _events(self) -> None:
        self.calls_by_tool_id: dict[str, list[str]] = {}  # ToolCall.id -> tool_call part ids (filled in _messages_out)
        self.split_calls: dict[tuple[str, str], str | None] = {}  # (ToolCall.id, scope) -> a cached copy's part (item 133)
        self.shared_call: dict[str, str] = {}  # ToolCall.id held by copies of one message -> the produced copy's part
        self.copy_parts: set[str] = set()  # the other copies' parts of a shared call (not separate calls)
        self.decisions_by_call: dict[str, str] = {}  # ToolCall.id -> decision id (approval/review)
        self.executed_parts: set[str] = set()
        self.denied_parts: set[str] = set()
        self.state_prev: dict[str, str] = {}
        self.model_calls_in_scope: dict[str, list[str]] = {}
        self.te_of_event: dict[int, str] = {}
        self.limit = False
        self.errored = False
        self._index_tool_calls()
        state_events = sorted(
            (k for k, e in enumerate(self.events) if e["event"] in ("state", "store")),
            key=lambda k: (self.ts_key(self.events[k].get("timestamp")), k),
        )
        for k in sorted(range(len(self.events)), key=lambda k: (self.events[k]["event"] not in ("approval", "review"), k)):
            e = self.events[k]
            kind = e["event"]
            if kind == "model":
                self._model(k, e)
            elif kind == "tool":
                self._tool(k, e)
            elif kind in ("approval", "review"):
                self._approval(k, e)
            elif kind == "sandbox":
                self._sandbox(k, e)
            elif kind == "sample_limit":
                self.limit = True
                self.run_scope.x("limit", {key: e[key] for key in ("type", "limit", "message") if key in e})
                self.run_scope.loc("a0", _p("events", k))
                self.defer("inspect.sample_limit", ["run"], "inspect.sample_limit@1", severity="info")
            elif kind in ("score", "score_edit"):
                pass  # after the scopes' judge calls are known (_scores)
            elif kind in ("span_begin", "span_end", "sample_init", "state", "store", "compaction"):
                pass
            elif kind == "branch":
                self._keep(k, e)
                self.defer("inspect.branch_unsupported", [self.scope_of(e)], "inspect.event_kept_in_ext@1")
            else:
                self._keep(k, e)
                if kind == "error":
                    self.errored = True
                if kind not in _KEPT_OBSERVED:
                    self.defer("inspect.unmapped_event", [self.scope_of(e)], "inspect.event_kept_in_ext@1", severity="info",
                               detail=kind if kind in _KEPT_UNOBSERVED else "unknown event type")
        for k in state_events:
            self._state(k, self.events[k])
        for k, e in enumerate(self.events):
            if e["event"] == "compaction":
                self._compaction(k, e)
        self._scores()
        self._run_status()

    def _keep(self, k: int, e: Mapping[str, Any]) -> None:
        host = self.host_scope(e)
        value, _used, _dangling = self.res.resolve(e)
        events = host.ext.setdefault("events", [])
        events.append(self.json(host, {"index": k, "event": value}, _p("ext", "inspect", "events", len(events))))
        host.loc("a0", _p("events", k))

    def _run_status(self) -> None:
        run = self.run_scope
        if self.errored or self.s.get("error") is not None:
            run.data["status"] = "error"
            if self.s.get("error") is not None:
                run.loc("a0", "/error")
                run.x("error", self.s["error"])
            else:
                self.d(run, "/status", "inspect.event_kept_in_ext@1")
        elif self.limit or self.s.get("limit") is not None:
            run.data["status"] = "limit"
            if self.s.get("limit") is not None:
                run.loc("a0", "/limit")
                run.x("sample_limit", self.s["limit"])
            self.d(run, "/status", "inspect.sample_limit@1")
        else:
            run.unk["/status"] = "not_recorded"

    # ---------------------------------------------------------------------------------------------- model events
    def _input_messages(self, k: int, e: Mapping[str, Any], mc: _Rec) -> list[str] | None:
        """The call's input as message ids, or ``None`` when a reference dangles (``unk /input lost``)."""
        refs = e.get("input_refs")
        out: list[str] = []
        if refs is not None:
            if not isinstance(refs, list):
                raise MalformedArtefact("input_refs is not an array")
            for r in refs:
                if (not isinstance(r, list) or len(r) != 2 or not all(isinstance(x, int) and not isinstance(x, bool) for x in r)
                        or not 0 <= r[0] <= r[1] <= len(self.pool)):
                    return None
                for j in range(r[0], r[1]):
                    msg = self.pool[j]
                    if msg is None:
                        return None
                    own = self._scoped(msg, self.scope_of(e))
                    if own is not msg:  # the pooled value is the cached call's own copy in this scope (item 133)
                        self._hold(own, _p("events_data", "messages", j), [])
                    out.append(own.local)
            mc.loc("a0", _p("events", k, "input_refs"))
            return out
        inline = e.get("input")
        if not isinstance(inline, list):
            raise MalformedArtefact("a model event has neither input_refs nor an input array")
        for i in range(len(inline)):
            msg = self.inline.get((k, i))
            if msg is None:
                return None
            out.append(msg.local)
        mc.loc("a0", _p("events", k, "input"))
        return out

    def _model(self, k: int, e: Mapping[str, Any]) -> None:
        base = _p("events", k)
        judge = self.role_of(e.get("span_id")) == "judge"
        scope = self.scope_of(e)
        mc = _Rec(k="model_call", id=self.next_id("mc"), ev="O", by="source")
        mc.loc("a0", base)
        if judge:
            mc.data["actor"] = self.judges[str(e.get("model"))]
            mc.data["role"] = "auxiliary"
            self.d(mc, "/actor", "inspect.span_is_scope@1")
            self.d(mc, "/role", "inspect.span_is_scope@1")
        else:
            mc.data["actor"] = "agent"
            mc.data["role"] = "agent"
            self.d(mc, "/actor", "inspect.model_event_is_call@1")
            self.d(mc, "/role", "inspect.model_event_is_call@1")
        mc.data["scope"] = scope
        self.d(mc, "/scope", "inspect.span_is_scope@1")
        consumer_key = (3, 1, self.ts_key(e.get("timestamp")), k, 0)
        inputs = self._input_messages(k, e, mc)
        if inputs is None:
            mc.unk["/input"] = "lost"
            self.defer("dangling_source_ref", [mc.id], "inspect.model_event_is_call@1", detail=base)
        else:
            mc.data["input"] = inputs
            for local in inputs:
                msg = self.msg_by_local(local)
                if msg.consumer_key is None:
                    msg.consumer_key = consumer_key
                    if not msg.local.startswith("m"):  # the sample's own messages stay in the run scope
                        msg.scope = msg.scope or scope
        tools = e.get("tools")
        if self.fx_tools is not None and isinstance(tools, list) and tools:
            value, _used, dangling = self.res.resolve(tools)
            if not dangling and _same(value, self.fx_tools_value):
                mc.data["tools"] = self.fx_tools
                self.d(mc, "/tools", "inspect.sample_init_fixtures@1")
        params: dict[str, Any] = {}
        config = e.get("config")
        if isinstance(config, dict):
            params["configured"] = self.json(mc, self.res.resolve(config)[0], "/params/configured")
        call = e.get("call")
        if isinstance(call, dict) and isinstance(call.get("request"), dict):
            key = call.get("call_key") if isinstance(call.get("call_key"), str) else "messages"
            request = {name: v for name, v in call["request"].items() if not (call.get("call_refs") and name == key)}
            params["transmitted"] = self.json(mc, self.res.resolve(request)[0], "/params/transmitted")
            response = call.get("response")
            rid = response.get("id") if isinstance(response, dict) else None
            if isinstance(rid, str) and rid:
                mc.data["response_id"] = rid
                mc.tag("/response_id", "O:provider")
            mc.x("call", {name: call[name] for name in ("time", "call_key", "call_refs") if name in call})
        else:  # U6-b: the request is not in the log
            self._transmitted_absent(k, e, mc)
        if params:
            mc.data["params"] = params
        output = _dict(e.get("output"))
        choices = [c for c in _list(output.get("choices")) if isinstance(c, dict)]
        error = e.get("error")
        if e.get("cache") == "read":
            mc.data["status"] = "cached"
            self.d(mc, "/status", "inspect.cache_read@1")
        elif error is not None and not choices:
            mc.data["status"] = "error"
            self.d(mc, "/status", "inspect.model_error@1")
            mc.unk["/reason"] = "not_recorded"
        else:
            mc.data["status"] = "kept"
            self.d(mc, "/status", "inspect.model_event_is_call@1")
        for name in ("error", "retries", "cache", "role", "requested_model", "working_time", "working_start", "uuid",
                     "tool_choice"):
            if name in e and e[name] is not None and not (name == "cache" and e[name] == "read"):
                mc.x("model_role" if name == "role" else name, e[name])
        if choices and isinstance(choices[0].get("stop_reason"), str):
            mc.data["finish_reason"] = choices[0]["stop_reason"]
            mc.tag("/finish_reason", "O:provider")
        usage = _dict(output.get("usage"))
        typed = {_USAGE[name]: v for name, v in usage.items()
                 if name in _USAGE and isinstance(v, int) and not isinstance(v, bool) and v >= 0}
        extra = {name: v for name, v in usage.items() if name not in _USAGE or _USAGE[name] not in typed}
        if typed:
            mc.data["usage"] = typed
            mc.tag("/usage", "O:provider")
        if extra:
            mc.x("usage_extra", extra)
        if isinstance(output.get("model"), str) and output["model"]:
            mc.data["served_model"] = output["model"]
            mc.tag("/served_model", "O:provider")
        self.t(mc, e.get("timestamp"), e.get("completed"), base, "timestamp", "completed")
        node = self.add(mc, consumer_key, activity=True)
        node.start, node.end = _when(e.get("timestamp")), _when(e.get("completed"))
        self.model_calls_in_scope.setdefault(scope, []).append(mc.id)
        if mc.data["status"] == "error":
            return
        for c, choice in enumerate(_list(output.get("choices"))):
            if not isinstance(choice, dict):
                continue
            out_msg = self.outputs.get((k, c))
            if out_msg is None:
                self.defer("dangling_source_ref", [mc.id], "inspect.model_event_is_call@1",
                           detail=_p("events", k, "output", "choices", c, "message"))
                continue
            if out_msg.generated_by is None:
                out_msg.generated_by = mc.id
                out_msg.generator_kind = "judge" if judge else "agent"
                out_msg.scope = scope

    def msg_by_local(self, local: str) -> _Msg:
        for msg in self.msgs:
            if msg.local == local:
                return msg
        raise KeyError(local)

    # ---------------------------------------------------------------------------------------------- tool events
    def _index_tool_calls(self) -> None:
        """ToolCall.id -> the AER part ids holding it (assistant messages' tool calls, in message order)."""
        held: dict[str, list[tuple[_Msg, dict[str, Any]]]] = {}
        for msg in self.msgs:
            for c, call in enumerate(_list(msg.value.get("tool_calls"))):
                if isinstance(call, dict) and isinstance(call.get("id"), str):
                    if msg.split_scope is not None:  # the scope's own call (item 133); a repeated id stays ambiguous
                        key = (call["id"], msg.split_scope)
                        self.split_calls[key] = None if key in self.split_calls else f"{msg.local}#{c}"
                        continue
                    self.calls_by_tool_id.setdefault(call["id"], []).append(f"{msg.local}#{c}")
                    held.setdefault(call["id"], []).append((msg, call))
        for tool_id, copies in held.items():
            if len(copies) > 1:
                produced = self._produced_copy(copies)
                if produced is not None:
                    parts = self.calls_by_tool_id[tool_id]
                    self.shared_call[tool_id] = produced
                    self.copy_parts.update(p for p in parts if p != produced)

    def _produced_copy(self, copies: Sequence[tuple[_Msg, dict[str, Any]]]) -> str | None:
        """Regeneration-batch item 16 (a), ``inspect.message_copies_share_calls@1``: one ``ToolCall.id`` in several
        messages is one call when every holder has the same Inspect message id and the calls are identical (Inspect's
        ``model_copy`` keeps ``id`` and ``tool_calls``; ``_remove_submit_tool`` and ``resolve_reasoning_history`` change
        only content). The call is the copy the model produced: an output choice's, else the ``messages`` copy's, never
        a replayed input's. Anything else stays ambiguous (fail-closed)."""
        ids = {msg.value.get("id") for msg, _ in copies}
        if len(ids) != 1 or not isinstance(next(iter(ids)), str):
            return None
        first = json.dumps(copies[0][1], sort_keys=True)
        if any(json.dumps(call, sort_keys=True) != first for _, call in copies[1:]):
            return None
        for produced_in in (lambda p: p.startswith("/events/") and "/output/" in p, lambda p: p.startswith("/messages/")):
            chosen = [(msg, call) for msg, call in copies if any(produced_in(p) for p in msg.src)]
            if len(chosen) == 1:
                msg, call = chosen[0]
                c = _list(msg.value.get("tool_calls")).index(call)
                return f"{msg.local}#{c}"
            if chosen:
                return None
        return None

    def call_part(self, tool_id: object, scope: str | None = None) -> str | None:
        """The one tool_call part with ``ToolCall.id == tool_id`` (resolved to its final part index later): in ``scope``,
        the call of the copy a cached model call returned there (item 133); else the only holder, or the produced copy
        of a call several copies of one message hold (item 16 (a))."""
        if isinstance(tool_id, str) and scope is not None and (tool_id, scope) in self.split_calls:
            return self.split_calls[(tool_id, scope)]
        parts = self.calls_by_tool_id.get(tool_id, []) if isinstance(tool_id, str) else []
        if len(parts) == 1:
            return parts[0]
        return self.shared_call.get(tool_id) if isinstance(tool_id, str) else None

    def _tool(self, k: int, e: Mapping[str, Any]) -> None:
        base = _p("events", k)
        scope = self.scope_of(e)
        part = self.call_part(e.get("id"), scope)
        error = e.get("error")
        status = tool_status(error)
        key = (3, 1, self.ts_key(e.get("timestamp")), k, 0)
        message = self._tool_message(e)
        if status is None:  # approval denial: no execution (RF-3)
            dc_id = self.decisions_by_call.get(str(e.get("id")))
            if dc_id is None:
                dc = _Rec(k="decision", id=self.next_id("dc"), actor="harness", scope=scope, verdict="deny", ev="O", by="source")
                dc.loc("a0", base)
                self.d(dc, "/actor", "inspect.tool_error_status@1")
                self.d(dc, "/verdict", "inspect.tool_error_status@1")
                self._subject(dc, part, base)
                dc.unk["/reason"] = "not_recorded"
                dc.x("error", error)
                self.t(dc, e.get("timestamp"), e.get("completed"), base, "timestamp", "completed")
                self.add(dc, key)
                dc_id = dc.id
            if part is not None:
                self.denied_parts.add(part)
            if message is not None and message.generated_by is None:
                message.generated_by, message.generator_kind, message.scope = dc_id, "decision", scope
            return
        te = _Rec(k="tool_execution", id=self.next_id("te"), actor="env", scope=scope, ev="O", by="source")
        self.te_of_event[k] = te.id
        te.loc("a0", base)
        self.d(te, "/actor", "inspect.tool_event_is_execution@1")
        self.d(te, "/scope", "inspect.span_is_scope@1")
        if part is not None:
            te.data["call"] = part
            self.d(te, "/call", "inspect.tool_call_id_match@1")
            if (e.get("id"), scope) in self.split_calls:
                self.d(te, "/call", R_CACHED_OWN)
            elif e.get("id") in self.shared_call:
                self.d(te, "/call", "inspect.message_copies_share_calls@1")
            self.executed_parts.add(part)
            te.after.append({"b": "causal", "id": part.split("#", 1)[0]})
            self.d(te, "/after", "aer.execution_after_call@1")
        else:
            te.unk["/call"] = "ambiguous"
            te.cite(self.R("inspect.tool_call_id_match@1", "/call"))
            self.defer("call_result_link_conflict" if self.calls_by_tool_id.get(str(e.get("id"))) else "orphan_tool_result",
                       [te.id], "inspect.tool_call_id_match@1", detail=_p("events", k, "id"))
        name = e.get("function")
        if not isinstance(name, str) or not name:
            raise MalformedArtefact("a tool event names no function")
        te.data["name"] = name
        args, used, dangling = self.res.resolve(e.get("arguments", {}))
        if dangling:
            te.unk["/args"] = "lost"
            self.defer("dangling_source_ref", [te.id], "inspect.tool_event_is_execution@1", detail=_p("events", k, "arguments"))
        else:
            te.set("args", args)
            for h in used:
                te.loc("a0", _p("attachments", h))
        te.data["status"] = status
        self.d(te, "/status", "inspect.tool_error_status@1")
        dc_id = self.decisions_by_call.get(str(e.get("id")))
        if dc_id is not None and self.nodes[dc_id].rec.data.get("verdict") in ("allow", "modify"):
            te.data["authorised_by"] = dc_id
            self.d(te, "/authorised_by", "inspect.approval_decision@1")
        te.unk["/args_effective"] = "not_recorded"
        for field_name in ("error", "failed", "agent", "working_time", "working_start", "uuid", "truncated", "events"):
            if field_name in e and e[field_name] not in (None, []):
                te.x(field_name, self.res.resolve(e[field_name])[0])
        self.t(te, e.get("timestamp"), e.get("completed"), base, "timestamp", "completed")
        node = self.add(te, key, activity=True)
        node.start, node.end = _when(e.get("timestamp")), _when(e.get("completed"))
        generator, kind = te.id, "tool"
        if e.get("truncated") is not None:
            dc = _Rec(k="decision", id=self.next_id("dc"), actor="harness", scope=scope, subject=te.id, verdict="modify",
                      ev="O", by="source")
            dc.loc("a0", _p("events", k, "truncated"))
            self.d(dc, "/actor", "inspect.tool_output_truncated@1")
            self.d(dc, "/verdict", "inspect.tool_output_truncated@1")
            self.d(dc, "/subject", "inspect.tool_output_truncated@1")
            dc.after.append({"b": "causal", "id": te.id})
            self.d(dc, "/after", "aer.decision_after_subject@1")
            dc.unk["/original"] = "overwritten"
            dc.unk["/reason"] = "not_recorded"
            dc.unk["/t"] = "not_recorded"
            dc.cite(self.R("inspect.tool_output_truncated@1", "/original"))
            self.add(dc, (3, 1, self.ts_key(e.get("timestamp")), k, 1))
            generator, kind = dc.id, "decision"
        if message is None and name in self.submit_tools and "result" in e:
            self._submit_result(k, e, generator)
        elif message is None:
            self.defer("dangling_source_ref", [te.id], "inspect.tool_event_is_execution@1", detail=_p("events", k, "message_id"))
            self.defer("missing_tool_result", [te.id], "inspect.tool_event_is_execution@1")
        elif message.generated_by is None:
            message.generated_by, message.generator_kind, message.scope = generator, kind, scope

    def _submit_result(self, k: int, e: Mapping[str, Any], generator: str) -> None:
        """Regeneration-batch item 16 (c), ``inspect.react_submit_message_removed@1``: the react agent's
        ``_remove_submit_tool`` (``keep_in_messages=False``, the default) drops the submit tool message from
        ``messages`` once the agent completes, while the tool event keeps the returned value in ``result``. The value is
        mapped as an artefact the execution generated; no result message is invented (the model never saw one), and the
        removal is the harness's design, not a loss, so no ``missing_tool_result`` is raised."""
        rule = "inspect.react_submit_message_removed@1"
        # declared, not lost: the execution has no result message (accounting reads the listed issue), its value is kept
        self.defer("missing_tool_result", [self.te_of_event[k]], rule)
        af = _Rec(k="artefact", id=self.next_id("af"), type="inspect:tool_result", generated_by=generator, ev="O",
                  by="source")
        self.d(af, "/type", rule)
        self.d(af, "/generated_by", rule)
        value, used, dangling = self.res.resolve(e.get("result"))
        if dangling:
            af.unk["/content"] = "lost"
            af.loc("a0", _p("events", k, "result"))
            self.defer("dangling_source_ref", [af.id], rule, detail=_p("events", k, "result"))
        else:
            af.set("content", value)
            af.loc("a0", _p("events", k, "result"))
            for h in used:
                af.loc("a0", _p("attachments", h))
        self.add(af, (3, 1, self.ts_key(e.get("timestamp")), k, 2))

    def _tool_message(self, e: Mapping[str, Any]) -> _Msg | None:
        """The result message of a tool event: the tool message ``message_id`` names. Where that message answers another
        call, the event carries the first-of-batch defect (regeneration-batch item 16 (b),
        ``inspect.tool_event_message_id_first_of_batch@1``: from at least 0.3.130 to 0.3.159.dev20, ``execute_tools``
        gives every event of a parallel batch the first call's result message id), and the result is the one tool
        message whose ``tool_call_id`` is the event's ``id``. A ``message_id`` that names no message stays unlinked
        (fail-closed: that is not the defect's signature). Before 0.3.113 the event has no ``message_id`` at all
        (item 25 (a), ``inspect.tool_event_no_message_id@1``): the result is the one tool message answering the event."""
        tool_id = e.get("id")
        mid = e.get("message_id")
        if "message_id" not in e and self.no_message_id and isinstance(tool_id, str):
            return self._by_call(tool_id, "inspect.tool_event_no_message_id@1")
        if not isinstance(mid, str):
            return None
        found = [m for m in self.by_inspect_id.get(mid, []) if m.value.get("role") == "tool"]
        if len(found) != 1:
            return None
        answered = found[0].value.get("tool_call_id")
        if answered in (tool_id, None) or not isinstance(tool_id, str):
            return found[0]
        return self._by_call(tool_id, "inspect.tool_event_message_id_first_of_batch@1")

    def _by_call(self, tool_id: str, rule: str) -> _Msg | None:
        """The one tool message whose ``tool_call_id`` is ``tool_id``, its link cited under ``rule``; else ``None``."""
        by_call = [m for m in self.msgs if m.value.get("role") == "tool" and m.value.get("tool_call_id") == tool_id]
        if len(by_call) != 1:
            return None
        if by_call[0].generated_by is None:
            by_call[0].link_rule = rule
        return by_call[0]

    def _subject(self, dc: _Rec, part: str | None, base: str) -> None:
        if part is not None:
            dc.data["subject"] = part
            self.d(dc, "/subject", "inspect.tool_call_id_match@1")
            dc.after.append({"b": "causal", "id": part.split("#", 1)[0]})
            self.d(dc, "/after", "aer.decision_after_subject@1")
        else:
            dc.unk["/subject"] = "not_recorded"
            self.defer("dangling_source_ref", [dc.id], "inspect.tool_call_id_match@1", detail=base)

    def _approval(self, k: int, e: Mapping[str, Any]) -> None:
        base = _p("events", k)
        call = _dict(e.get("call"))
        verdict = _VERDICTS.get(str(e.get("decision")))
        if verdict is None:
            raise MalformedArtefact("an approval or review event has an unknown decision")
        actor = self._approver(e.get("approver") if e["event"] == "approval" else e.get("reviewer"))
        dc = _Rec(k="decision", id=self.next_id("dc"), actor=actor, scope=self.scope_of(e), verdict=verdict, ev="O", by="source")
        dc.loc("a0", base)
        self.d(dc, "/actor", "inspect.approval_decision@1")
        self.d(dc, "/verdict", "inspect.approval_decision@1")
        self._subject(dc, self.call_part(call.get("id"), self.scope_of(e)), base)
        explanation = e.get("explanation")
        if isinstance(explanation, str):
            dc.data["reason"] = explanation
        else:
            dc.unk["/reason"] = "not_recorded"
        for name in ("approver", "reviewer", "modified", "message", "decision"):
            if name in e and e[name] is not None:
                dc.x(name, self.res.resolve(e[name])[0])
        self.t_slot(dc, "start", e.get("timestamp"), _p("events", k, "timestamp"))
        self.add(dc, (3, 1, self.ts_key(e.get("timestamp")), k, 0))
        if isinstance(call.get("id"), str):
            self.decisions_by_call[call["id"]] = dc.id
            if verdict == "deny":
                part = self.call_part(call["id"], self.scope_of(e))
                if part is not None:
                    self.denied_parts.add(part)

    def _sandbox(self, k: int, e: Mapping[str, Any]) -> None:
        base = _p("events", k)
        action = e.get("action")
        if action not in ("exec", "read_file", "write_file"):
            raise MalformedArtefact("a sandbox event has an unknown action")
        ac = _Rec(k="activity", id=self.next_id("ac"), type=f"inspect:sandbox_{action}", actor="env", scope=self.scope_of(e),
                  ev="O", by="source")
        ac.loc("a0", base)
        self.d(ac, "/type", "inspect.sandbox_activity@1")
        self.d(ac, "/actor", "inspect.sandbox_activity@1")
        ac.unk["/inputs"] = "not_recorded"
        result = e.get("result")
        if isinstance(result, int) and not isinstance(result, bool):
            ac.data["status"] = "ok" if result == 0 else "error"
            self.d(ac, "/status", "inspect.sandbox_activity@1")
        else:
            ac.unk["/status"] = "not_recorded"
        ac.data["label"] = str(action)
        for name in ("cmd", "file", "options", "input", "result"):
            if name in e and e[name] is not None:
                ac.x(name, e[name])
        self.t(ac, e.get("timestamp"), e.get("completed"), base, "timestamp", "completed")
        node = self.add(ac, (3, 1, self.ts_key(e.get("timestamp")), k, 0), activity=True)
        node.start, node.end = _when(e.get("timestamp")), _when(e.get("completed"))
        # R-10p-7: an output artefact only when the event records an output string (an empty one included). Without
        # one (write_file, or an exec whose output is null) the source records no generated entity, so none is
        # emitted: an artefact asserting only D fields under by=source is AER-V12 by_without_bare_O.
        if not isinstance(e.get("output"), str):
            return
        af = _Rec(k="artefact", id=self.next_id("af"), type="inspect:sandbox_output", generated_by=ac.id, ev="O", by="source")
        self.d(af, "/type", "inspect.sandbox_activity@1")
        self.d(af, "/generated_by", "inspect.sandbox_activity@1")
        af.set("content", e["output"])
        af.loc("a0", _p("events", k, "output"))
        self.add(af, (3, 1, self.ts_key(e.get("timestamp")), k, 1))

    # ---------------------------------------------------------------------------------------------- state
    def _state(self, k: int, e: Mapping[str, Any]) -> None:
        target = "other" if e["event"] == "state" else "agent_store"
        changes = e.get("changes")
        if not isinstance(changes, list):
            raise MalformedArtefact("a state event has no changes array")
        scope = self.scope_of(e)
        st = _Rec(k="state_change", id=self.next_id("st"), scope=scope, target=target, ev="O", by="source")
        st.loc("a0", _p("events", k, "changes"))
        self.d(st, "/target", "inspect.state_event@1")
        if target == "other":
            st.data["subtype"] = "inspect.task_state"
            self.d(st, "/subtype", "inspect.state_event@1")
        if scope != "run":
            st.data["cause"] = scope
            self.d(st, "/cause", "inspect.state_event@1")
        patch, used, dangling = self.res.resolve(changes)
        if dangling:
            st.unk["/patch"] = "lost"
            self.defer("dangling_source_ref", [st.id], "inspect.state_event@1", detail=_p("events", k, "changes"))
        else:
            st.data["patch"] = self.json(st, patch, "/patch")  # strings over 1 MiB are not inlined (item 28)
            for h in used:
                st.loc("a0", _p("attachments", h))
        self.t_slot(st, "end", e.get("timestamp"), _p("events", k, "timestamp"))
        if "end" in st.data.get("t", {}):
            self.d(st, "/t", "inspect.state_event@1")
        prev = self.state_prev.get(target)
        if prev is not None:
            st.after.append({"b": "proto", "id": prev})
            self.d(st, "/after", "inspect.state_event@1")
        self.state_prev[target] = st.id
        self.add(st, (3, 1, self.ts_key(e.get("timestamp")), k, 0))

    def _compaction(self, k: int, e: Mapping[str, Any]) -> None:
        span = e.get("span_id")
        calls = [self.nodes[mc_id].rec for mc_id in self.model_calls_in_scope.get(self.scope_of(e), [])]
        value = self.res.resolve(e)[0]
        if isinstance(span, str) and self.scope_of(e) != "run" and len(calls) == 1:
            mc = calls[0]
            mc.cite(self.R("inspect.compaction@1"))
            mc.x("compaction", {"index": k, "event": value})
            mc.loc("a0", _p("events", k))
        else:
            host = self.host_scope(e)
            host.x("compaction", {"index": k, "event": value})
            host.loc("a0", _p("events", k))
            self.defer("inspect.compaction_unmodelled", [host.id], "inspect.compaction@1")

    # ---------------------------------------------------------------------------------------------- scores
    def _scores(self) -> None:
        self.judgement_names: dict[str, str] = {}
        self.scored: set[str] = set()
        for k, e in enumerate(self.events):
            if e["event"] == "score":
                self._score(k, e)
        for k, e in enumerate(self.events):
            if e["event"] == "score_edit":
                self._score_edit(k, e)

    def _judge_of_scope(self, scope: str) -> tuple[str, str | None]:
        """(judgement actor, the only judge call of the scope or ``None``)."""
        calls = [self.nodes[c].rec for c in self.model_calls_in_scope.get(scope, [])]
        judges = {c.data["actor"] for c in calls if c.data.get("role") == "auxiliary"}
        only = calls[0].id if len(calls) == 1 and calls[0].data.get("role") == "auxiliary" else None
        return (judges.pop() if len(judges) == 1 else "bench"), only

    def scorer_span(self, span_id: object) -> int | None:
        """The ``span_begin`` index of the nearest span (itself included) of type ``scorer`` with a string name."""
        seen: set[str] = set()
        cursor = span_id
        while isinstance(cursor, str) and cursor in self.spans and cursor not in seen:
            seen.add(cursor)
            begin = self.spans[cursor]["begin"]
            if self.events[begin].get("type") == "scorer" and isinstance(self.events[begin].get("name"), str):
                return int(begin)
            cursor = self.events[begin].get("parent_id")
        return None

    def _score(self, k: int, e: Mapping[str, Any]) -> None:
        score = _dict(e.get("score"))
        # Regeneration-batch item 81 (CD-24): inspect_ai writes `scorer` on score events only from 0.3.217. Before, the
        # event is produced in its scorer's span (inspect.score_event@1), whose name is the scorer's; with no such span
        # the name stays the literal "score", declared ambiguous (C.7.2(2)), not paired with a sample.scores key.
        named_by: int | None = None
        if isinstance(e.get("scorer"), str):
            scorer = e["scorer"]
        else:
            named_by = self.scorer_span(e.get("span_id"))
            scorer = self.events[named_by]["name"] if named_by is not None else "score"
        assert isinstance(scorer, str)
        scope = self.scope_of(e)
        actor, only = self._judge_of_scope(scope)
        value = score.get("value")
        items = list(value.items()) if isinstance(value, dict) else [(None, value)]
        recorded = _dict(_dict(_dict(self.s.get("scores")).get(scorer)).get("value"))
        for key, v in items:
            name = f"{scorer}.{key}" if key is not None else scorer
            j = _Rec(k="judgement", id=self.next_id("j"), actor=actor, subject="run", name=name, origin="checker",
                     ev="O", by="benchmark")
            j.set("value", v)
            vp = _p("events", k, "score", "value", key) if key is not None else _p("events", k, "score", "value")
            j.loc("a0", vp)
            if key is not None and key in recorded and _same(recorded[key], v):
                j.loc("a0", _p("scores", scorer, "value", key))
            self.d(j, "/actor", "inspect.score_event@1")
            self.d(j, "/subject", "inspect.score_event@1")
            self.d(j, "/name", "inspect.score_event@1")
            if named_by is not None:
                j.loc("a0", _p("events", named_by, "name"))
            elif not isinstance(e.get("scorer"), str):
                j.unk["/name"] = "ambiguous"
            self.d(j, "/origin", "inspect.score_event@1")
            if scope != "run" or only is not None:
                j.data["generated_by"] = only if only is not None else scope
                self.d(j, "/generated_by", "inspect.score_event@1")
            j.unk["/inputs"] = "not_recorded"
            for name_ in ("explanation", "metadata", "answer", "history"):
                if name_ in score and score[name_] not in (None, []):
                    j.x(name_, self.res.resolve(score[name_])[0])
            for name_ in ("intermediate", "target", "scorer_args"):
                if name_ in e and e[name_] is not None:
                    j.x(name_, self.res.resolve(e[name_])[0])
            self.add(j, (4, k, len(self.judgement_names)))
            self.judgement_names.setdefault(name, j.id)
        self.scored.add(scorer)

    def _score_edit(self, k: int, e: Mapping[str, Any]) -> None:
        name = e.get("score_name")
        edit = _dict(e.get("edit"))
        if not isinstance(name, str):
            raise MalformedArtefact("a score_edit event names no score")
        value = edit.get("value")
        items = list(value.items()) if isinstance(value, dict) else [(None, value)]
        for key, v in items:
            jname = f"{name}.{key}" if key is not None else name
            j = _Rec(k="judgement", id=self.next_id("j"), actor="bench", subject="run", name=jname, origin="recomputed",
                     ev="O", by="source")
            j.set("value", v)
            j.loc("a0", _p("events", k, "edit", "value", key) if key is not None else _p("events", k, "edit", "value"))
            self.d(j, "/actor", "inspect.score_event@1")
            self.d(j, "/subject", "inspect.score_event@1")
            self.d(j, "/name", "inspect.score_event@1")
            self.d(j, "/origin", "inspect.score_event@1")
            revised = self.judgement_names.get(jname)
            if revised is not None:
                j.data["revises"] = revised
                self.d(j, "/revises", "inspect.score_event@1")
            for name_ in ("explanation", "metadata", "provenance", "answer"):
                if name_ in edit and edit[name_] is not None:
                    j.x(name_, self.res.resolve(edit[name_])[0])
            self.add(j, (4, k, 1000 + len(self.judgement_names)))
            self.judgement_names[jname] = j.id

    def _scores_without_events(self) -> None:
        """sample.scores entries of scorers with no score event (an older log shape)."""
        for scorer, entry in _dict(self.s.get("scores")).items():
            if scorer in self.scored or not isinstance(entry, dict):
                continue
            value = entry.get("value")
            items = list(value.items()) if isinstance(value, dict) else [(None, value)]
            for key, v in items:
                j = _Rec(k="judgement", id=self.next_id("j"), actor="bench", subject="run",
                         name=f"{scorer}.{key}" if key is not None else str(scorer), origin="checker", ev="O", by="benchmark")
                j.set("value", v)
                j.loc("a0", _p("scores", scorer, "value", key) if key is not None else _p("scores", scorer, "value"))
                for pointer in ("/actor", "/subject", "/name", "/origin"):
                    self.d(j, pointer, "inspect.score_event@1")
                j.unk["/inputs"] = "not_recorded"
                for name_ in ("explanation", "metadata"):
                    if entry.get(name_) is not None:
                        j.x(name_, self.res.resolve(entry[name_])[0])
                self.add(j, (4, 10**6, len(self.judgement_names)))
                self.judgement_names.setdefault(j.data["name"], j.id)

    # ---------------------------------------------------------------------------------------------- messages out
    def _messages_out(self) -> None:
        """Build the message records (parts, links, scopes) once every generator is known."""
        self.part_index: dict[str, str] = {}  # provisional "<local>#<c>" (tool call c) -> final part id
        built: list[tuple[_Msg, _Rec]] = []
        for msg in self.msgs:
            rec = self._message(msg)
            built.append((msg, rec))
        for msg, rec in built:
            self._link_result(msg, rec)
            if msg.generated_by is not None:
                gen = self.nodes[msg.generated_by]
                key = (*gen.key[:4], 2 + int(msg.local.lstrip("mpo") or 0) / 10**6)
            elif msg.consumer_key is not None:
                key = (*msg.consumer_key[:4], -1)
            else:
                key = (3, 0, 0.0, 0, int(msg.local.lstrip("mpo") or 0))
            self.add(rec, key)
        # patch provisional part ids now that every message's parts are numbered
        for node in self.nodes.values():
            data = node.rec.data
            for name in ("call", "subject"):
                if isinstance(data.get(name), str) and data[name] in self.part_index:
                    data[name] = self.part_index[data[name]]
            if isinstance(data.get("spawned_by"), str) and data["spawned_by"].startswith("__te"):
                k = int(data["spawned_by"][4:])
                data["spawned_by"] = self.te_of_event.get(k, data["spawned_by"])
        self.executed_parts = {self.part_index.get(p, p) for p in self.executed_parts}
        self.denied_parts = {self.part_index.get(p, p) for p in self.denied_parts}

    def _transmitted_absent(self, k: int, e: Mapping[str, Any], mc: _Rec) -> None:
        """U6-b: a model event without ``call``. ``lost`` when the transcript's retention policy discarded it
        (``inspect.model_api_call_retention@1``: ``log_model_api`` unset or false, a non-error, non-cached call after the
        model's first 5 kept calls in the sample), else ``not_recorded`` (C.7.2(3))."""
        policy = _dict(self.ev.get("config")).get("log_model_api")
        retained = sum(1 for prior in self.events[:k]
                       if prior["event"] == "model" and prior.get("model") == e.get("model")
                       and isinstance(prior.get("call"), dict) and not _dict(prior.get("call")).get("error"))
        if (e.get("cache") != "read" and e.get("error") is None and policy in (None, False)
                and (policy is False or retained >= _LOG_MODEL_API_CALLS)):
            rule = self.V("inspect.model_api_call_retention@1")
            mc.unk["/params/transmitted"] = "lost"
            mc.cite(self.R(rule, "/params/transmitted"))
        else:
            mc.unk["/params/transmitted"] = "not_recorded"

    def _message(self, msg: _Msg) -> _Rec:
        v = msg.value
        role = v["role"]
        rec = _Rec(k="message", id=msg.local, scope=msg.scope or "run", role=role, ev="O", by="source")
        for pointer in msg.src:
            rec.loc("a0", pointer)
        for h in msg.attachments:
            rec.loc("a0", _p("attachments", h))
        parts: list[dict[str, Any]] = []
        parts_extra: dict[str, Any] = {}
        content = v.get("content")
        base = "/parts"
        if isinstance(content, str):
            if role == "tool" and _big(content):  # over 1 MiB: the result's Json value is the digest (item 28)
                parts.append({"t": "tool_result", "value": self.json(rec, content, f"{base}/0/value")})
            elif role == "tool":
                parts.append({"t": "tool_result", "text": rec.enc(content, f"{base}/0/text")})
            elif _big(content):
                parts.append(self.big_part(rec, "text", content, f"{base}/0"))
            else:
                parts.append({"t": "text", "text": rec.enc(content, f"{base}/0/text")})
        elif isinstance(content, list):
            if role == "tool":
                parts.append({"t": "tool_result", "value": self.json(rec, content, f"{base}/0/value")})
            else:
                for item in content:
                    self._content_part(rec, item, parts, parts_extra)
        elif content is not None:
            raise MalformedArtefact("a chat message's content is neither a string nor a list")
        calls = _list(v.get("tool_calls"))
        for c, call in enumerate(calls):
            if not isinstance(call, dict) or not isinstance(call.get("function"), str):
                raise MalformedArtefact("a tool call is not an object with a function")
            n = len(parts)
            part: dict[str, Any] = {"t": "tool_call", "name": call["function"],
                                    "args": self.json(rec, call.get("arguments", {}), f"{base}/{n}/args")}
            if "id" in call:
                part["provider_call_id"] = call["id"] if isinstance(call["id"], str) else None
            parts.append(part)
            self.part_index[f"{msg.local}#{c}"] = part_id(msg.local, n)
            extra = {key: val for key, val in call.items() if key not in ("function", "arguments", "id")}
            if extra:
                parts_extra[str(n)] = extra
        if role == "assistant":
            for n, part in enumerate(parts):
                if part.get("t") == "text" and part.get("text") == "":
                    rec.unk[f"/parts/{n}/text"] = "ambiguous"  # '' records a provider null too (D.9.5)
                    rec.cite(self.R("inspect.message_content_parts@1", f"/parts/{n}/text"))
        rec.data["parts"] = parts
        if parts_extra:
            rec.x("part_extra", parts_extra)
        for name in ("id", "source", "model", "metadata", "function", "tool_call_id", "error"):
            if name in v and v[name] is not None:
                rec.x(name, v[name])
        if role == "tool" and parts and parts[0]["t"] == "tool_result":
            if isinstance(v.get("function"), str):
                parts[0]["name"] = v["function"]
            error = v.get("error")
            if isinstance(error, dict) and isinstance(error.get("message"), str):
                parts[0]["error"] = rec.enc(error["message"], f"{base}/0/error")
        gen = msg.generated_by
        if gen is not None:
            rec.data["generated_by"] = gen
            rec.after.append({"b": "causal", "id": gen})
            rule = {"agent": "inspect.model_event_is_call@1", "judge": "inspect.model_event_is_call@1",
                    "tool": "inspect.tool_event_is_execution@1",
                    "decision": "inspect.tool_output_truncated@1"}[msg.generator_kind or "agent"]
            gen_rec = self.nodes[gen].rec
            if msg.generator_kind == "decision" and gen_rec.data.get("verdict") == "deny":
                rule = "inspect.tool_error_status@1"
            self.d(rec, "/generated_by", rule)
            if msg.link_rule is not None:
                self.d(rec, "/generated_by", msg.link_rule)
            if msg.split_scope is not None:
                self.d(rec, "/generated_by", R_CACHED_OWN)
            self.d(rec, "/after", "aer.output_after_generator@1")
            actor = {"agent": "agent", "tool": "env"}.get(msg.generator_kind or "")
            if msg.generator_kind == "judge":
                actor = gen_rec.data["actor"]
            elif msg.generator_kind == "decision":
                actor = str(gen_rec.data["actor"])
            if actor is not None:
                rec.data["actor"] = actor
                self.d(rec, "/actor", rule)
        elif role == "user" and v.get("source") == "input" and (msg.scope or "run") == "run":
            rule = self.V("inspect.sample_input_from_benchmark@1")  # item 12 (c4): Sample.input
            rec.data["actor"] = "bench"
            rec.tag("/actor", rule_class(rule), self.R(rule, "/actor"))
        elif role == "system" and (msg.scope or "run") == "run" and _list(_dict(self.h.get("plan")).get("steps")):
            rec.data["actor"] = "bench"  # item 12 (c4): inserted by a solver of the task's logged plan (class I)
            rec.tag("/actor", "I", self.R("inspect.system_message_from_task_plan@1", "/actor"))
            rec.loc("a1", "/plan/steps")
        else:
            rec.unk["/actor"] = "not_recorded"
        if msg.scope is not None and msg.scope != "run":
            self.d(rec, "/scope", "inspect.span_is_scope@1")
        return rec

    def _content_part(self, rec: _Rec, item: object, parts: list[dict[str, Any]], extra: dict[str, Any]) -> None:
        if not isinstance(item, dict) or not isinstance(item.get("type"), str):
            raise MalformedArtefact("a content item has no type")
        n = len(parts)
        kind = item["type"]
        at = f"/parts/{n}"
        rest: dict[str, Any] = {}
        if kind in ("text", "reasoning") and _big(item.get(kind)):  # over 1 MiB: not inlined (item 28)
            parts.append(self.big_part(rec, kind, item[kind], at))
            rest = {k: v for k, v in item.items() if k not in ("type", kind)}
        elif kind == "text" and isinstance(item.get("text"), str):
            parts.append({"t": "text", "text": rec.enc(item["text"], f"{at}/text")})
            rest = {k: v for k, v in item.items() if k not in ("type", "text")}
        elif kind == "reasoning" and isinstance(item.get("reasoning"), str):
            part: dict[str, Any] = {"t": "reasoning", "text": rec.enc(item["reasoning"], f"{at}/text")}
            if isinstance(item.get("signature"), str):
                part["signature"] = item["signature"]
            if isinstance(item.get("redacted"), bool):
                part["redacted"] = item["redacted"]
            parts.append(part)
            rest = {k: v for k, v in item.items() if k not in ("type", "reasoning", "signature", "redacted")}
        elif kind in ("image", "audio", "video") and _big(item.get(kind)):  # over 1 MiB: not inlined (item 28)
            parts.append(self.big_part(rec, kind, item[kind], at))
            rest = {k: v for k, v in item.items() if k not in ("type", kind)}
        elif kind in ("image", "audio", "video") and isinstance(item.get(kind), str):  # audio, video: item 25 (b)
            parts.append({"t": "uri", "uri": rec.enc(item[kind], f"{at}/uri")})
            rest = {k: v for k, v in item.items() if k not in ("type", kind)}
        elif kind == "data":
            parts.append({"t": "other", "type": "inspect.content_data", "value": self.json(rec, item.get("data"), f"{at}/value")})
            rest = {k: v for k, v in item.items() if k not in ("type", "data")}
        elif kind == "tool_use":
            body = {k: v for k, v in item.items() if k != "type"}
            parts.append({"t": "other", "type": "inspect.tool_use", "value": self.json(rec, body, f"{at}/value")})
        else:
            body = {k: v for k, v in item.items() if k != "type"}
            parts.append({"t": "other", "type": kind, "value": self.json(rec, body, f"{at}/value")})
            self.defer("inspect.unknown_content_type", [rec.id], "inspect.message_content_parts@1", detail=at)
        rest = {k: v for k, v in rest.items() if v is not None}
        if rest:
            extra.setdefault(str(n), {}).update(rest)  # beside a not_inlined digest (item 28)

    def _link_result(self, msg: _Msg, rec: _Rec) -> None:
        """``tool_result.responds_to`` from ``tool_call_id`` (inspect.tool_call_id_match@1)."""
        parts = rec.data["parts"]
        if msg.value["role"] != "tool" or not parts or parts[0].get("t") != "tool_result":
            return
        tool_id = msg.value.get("tool_call_id")
        own = (tool_id, rec.data.get("scope"))
        if isinstance(tool_id, str) and own in self.split_calls:  # the scope's cached copy holds the call (item 133)
            part = self.split_calls[own]
            if part is None:
                rec.unk["/parts/0/responds_to"] = "ambiguous"
                rec.cite(self.R("inspect.tool_call_id_match@1", "/parts/0/responds_to"))
                self.defer("call_result_link_conflict", [rec.id], "inspect.tool_call_id_match@1")
            else:
                parts[0]["responds_to"] = self.part_index[part]
                self.d(rec, "/parts/0/responds_to", "inspect.tool_call_id_match@1")
                self.d(rec, "/parts/0/responds_to", R_CACHED_OWN)
            return
        # regeneration-batch item 84 (CD-27): a non-string id (a list or object is unhashable) takes the orphan path
        provisional = self.calls_by_tool_id.get(tool_id, []) if isinstance(tool_id, str) else []
        shared = self.shared_call.get(tool_id) if isinstance(tool_id, str) else None
        if len(provisional) == 1:
            parts[0]["responds_to"] = self.part_index[provisional[0]]
            self.d(rec, "/parts/0/responds_to", "inspect.tool_call_id_match@1")
        elif shared is not None:
            parts[0]["responds_to"] = self.part_index[shared]
            self.d(rec, "/parts/0/responds_to", "inspect.tool_call_id_match@1")
            self.d(rec, "/parts/0/responds_to", "inspect.message_copies_share_calls@1")
        elif provisional:
            rec.unk["/parts/0/responds_to"] = "ambiguous"
            rec.cite(self.R("inspect.tool_call_id_match@1", "/parts/0/responds_to"))
            self.defer("call_result_link_conflict", [rec.id], "inspect.tool_call_id_match@1")
        else:
            rec.unk["/parts/0/responds_to"] = "not_recorded"
            self.defer("orphan_tool_result", [rec.id], "inspect.tool_call_id_match@1")

    # ---------------------------------------------------------------------------------------------- accounting
    def _accounting_issues(self) -> None:
        copies = {self.part_index.get(p, p) for p in self.copy_parts}  # copies of a call, not separate calls (item 16 (a))
        pending = [part for part in self.part_index.values()
                   if part not in self.executed_parts and part not in self.denied_parts]
        lost = [part for part in pending if part not in copies]
        if lost:
            self.defer("unexecuted_tool_call", sorted(lost, key=_part_order), "inspect.tool_event_is_execution@1")
        copied = [part for part in pending if part in copies]
        if copied:  # declared: each copy's part is not executed itself; the call's one execution is the produced copy's
            self.defer("unexecuted_tool_call", sorted(copied, key=_part_order), "inspect.message_copies_share_calls@1")
        if not any(e["event"] in ("model", "tool") for e in self.events):
            self.unit_kind = "outcome_only"
            self.defer("no_execution_observed", ["exec"], "inspect.model_event_is_call@1")
        else:
            self.unit_kind = "agent_execution"

    # ---------------------------------------------------------------------------------------------- order
    def _deps(self, rec: _Rec) -> set[str]:
        data = rec.data
        deps: set[str] = set()
        for name in _REF_FIELDS:
            value = data.get(name)
            if isinstance(value, str):
                deps.add(value.split("#", 1)[0])
        for item in _list(data.get("input")):
            deps.add(item if isinstance(item, str) else str(_dict(item).get("id")))
        for item in _list(data.get("inputs")):
            if isinstance(item, str):
                deps.add(item.split("#", 1)[0])
        for part in _list(data.get("parts")):
            if isinstance(part, dict) and isinstance(part.get("responds_to"), str):
                deps.add(part["responds_to"].split("#", 1)[0])
        for edge in rec.after:
            deps.add(edge["id"])
        deps.discard(rec.id)
        return {d for d in deps if d in self.nodes}

    def _order(self) -> None:
        """Kahn's algorithm over the reference graph, ties broken by the documented key (C.2.1 item 5)."""
        deps = {rid: self._deps(node.rec) for rid, node in self.nodes.items()}
        users: dict[str, list[str]] = {}
        for rid, ds in deps.items():
            for dep in ds:
                users.setdefault(dep, []).append(rid)
        waiting = {rid: len(ds) for rid, ds in deps.items()}
        heap = [(self.nodes[rid].key, rid) for rid, n in waiting.items() if n == 0]
        heapq.heapify(heap)
        while heap:
            _key, rid = heapq.heappop(heap)
            self.order.append(rid)
            for user in users.get(rid, []):
                waiting[user] -= 1
                if waiting[user] == 0:
                    heapq.heappush(heap, (self.nodes[user].key, user))
        if len(self.order) != len(self.nodes):
            raise MalformedArtefact("the sample's references form a cycle")

    def _contradictory_times(self) -> None:
        """A record whose recorded start is later than its recorded end (seen in whistlebench logs at one local offset):
        neither instant is asserted, both stay verbatim in ``t.raw`` declared ``ambiguous`` (C.7.2(2)), and the node takes
        no part in time edges (C.8.6). Item 82: before the UTC conversion these values were all declared unknown."""
        for node in self.nodes.values():
            rec = node.rec
            t = rec.data.get("t")
            if isinstance(t, dict) and isinstance(t.get("start"), str) and isinstance(t.get("end"), str):
                start, end = _when(t["start"]), _when(t["end"])
                if start is not None and end is not None and start > end:
                    raw = t.setdefault("raw", {})
                    for slot in ("start", "end"):
                        del t[slot]
                        raw.setdefault(slot, rec.enc(rec.t_src.get(slot), f"/t/raw/{slot}"))
                        rec.unk[f"/t/{slot}"] = "ambiguous"
            if node.start is not None and node.end is not None and node.start > node.end:
                node.start = node.end = None

    def _time_edges(self) -> None:
        """``after {b: time}`` to the immediate predecessors among activities with recorded intervals (C.8.6)."""
        position = {rid: i for i, rid in enumerate(self.order)}
        acts = [(rid, n) for rid, n in self.nodes.items() if n.activity and n.start is not None and n.end is not None]
        for rid, node in acts:
            assert node.start is not None
            before = [(x, n) for x, n in acts if n.end is not None and n.end < node.start and position[x] < position[rid]]
            immediate = [x for x, n in before if not any(n.end is not None and o.start is not None and n.end < o.start
                                                         for y, o in before if y != x)]
            if not immediate:
                continue
            rec = node.rec
            for x in sorted(immediate, key=lambda r: position[r]):
                rec.after.append({"b": "time", "id": x})
            rec.tag("/after", "D", self.R("aer.time_order@1", "/after"))

    # ---------------------------------------------------------------------------------------------- header
    def _header_ext(self) -> list[tuple[str, object]]:
        """The header's ``ext.inspect`` values in order: eval fields, sample fields, then the sample metadata (resolved;
        the ground-truth keys a fixture holds are left out)."""
        s, ev = self.s, self.ev
        out: list[tuple[str, object]] = [(name, ev[name]) for name in _EVAL_HEADER_EXT if name in ev]
        out += [(name, s[name]) for name in ("epoch", "uuid", "target") if name in s]
        keys = set(_pseq(self.family.get("ground_truth_metadata"))) if self.gt_fixture else set()
        metadata = {k: v for k, v in _dict(s.get("metadata")).items() if k not in keys}
        if metadata:
            out.append(("sample_metadata", self.res.resolve(metadata)[0]))
        return out

    def _header(self) -> dict[str, Any]:
        s, ev = self.s, self.ev
        h = _Rec(k="execution", id="exec", ev="O", by="config")
        art = self.unit.primary.artefact
        sample_id = s.get("id")
        if isinstance(sample_id, bool) or not isinstance(sample_id, int | str) or sample_id == "":
            raise MalformedArtefact("the sample has no id")
        task: dict[str, Any] = {"task_id": str(sample_id)}
        h.loc("a0", "/id")
        suite = ev.get("task")
        if isinstance(suite, str) and suite:
            task["suite"] = suite
            h.loc("a1", "/eval/task")
        benchmark = self.family.get("benchmark")
        if isinstance(benchmark, str):
            task["benchmark"] = benchmark
            self.d(h, "/task/benchmark", "inspect.header_applies_to_samples@1")
        else:
            raise MalformedArtefact("the profile names no benchmark")
        if self.family.get("no_attack") is True:
            task["attack_id"] = None
            self.d(h, "/task/attack_id", "inspect.header_applies_to_samples@1")
        h.data["task"] = task
        h.unk["/instrumentation"] = "not_recorded"
        for name, value in self.header_ext:  # strings over 1 MiB are not inlined (item 28; C.2.1(6), AER-V01 under aer/0.2)
            h.ext[name] = self.json(h, value, _p("ext", "inspect", name))
            if name in _EVAL_HEADER_EXT:
                h.loc("a1", _p("eval", name))
        artifacts = [art.to_json()] + [ref.to_json() for _role, ref in sorted(self.unit.auxiliary.items())]
        h.data.update(
            {
                "aer": "0.1",
                "ex": self.ctx.ex,
                "mode": "import",
                "unit": self.unit_kind,
                "source_key": {"sha256": art.sha256, "loc": {"p": ""}},
                "artifacts": artifacts,
                "adapter": {"id": ADAPTER_ID, "version": ADAPTER_VERSION},
                "dialect": {"id": DIALECT_ID, "variant": VARIANT},
                "profile": self.ctx.profile.header(),
                "rules": self.ctx.catalogue_versions(CATALOGUES),
                "ns": dict(NAMESPACES),
                "canon": "jcs-rfc8785",
                "hash": "sha256",
            }
        )
        return h.done()


def _part_order(part: str) -> tuple[str, int]:
    message, _, k = part.partition("#")
    return message, int(k or 0)
