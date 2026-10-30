"""Mapper ``agentdojo.capture``: live ``capture/0.1`` sessions of the AgentDojo backend -> AER ``aer/0.1``
(docs/architecture C.13.7, D.10.4; implementation resolutions D.10.4a).

The reader (:mod:`agentprov.adapters.agentdojo.capture_reader`) hands over the **verifiable prefix** of the hash-chained
event log (C.13.2) with the blobs it references and the native TraceLogger JSON as auxiliary bytes. This mapper emits:

* the ``execution`` header (``mode: live``; ``source_key`` = the log digest with ``loc {}``; ``capture {session, log,
  attempt}``; ``task`` from ``session.start.cell``; ``instrumentation`` copied from the ``instrumentation`` event, O by
  capture);
* the actors: ``bench`` and ``harness`` with the ``identity`` event's code identity (O by capture), ``user``, the actors
  declared in ``session.start.actors`` (the agent's model from the cell and the ``identity`` event), and ``att`` for an
  attacked cell;
* the ``run`` scope (status from ``session.end``; ``error`` for an unsealed log or a fatal ``error`` event) and one
  ``att<k>`` scope per pass (``index`` O by capture; ``status: aborted`` for an aborted pass; the last pass scored);
* one ``fixture`` per ``fixture`` event;
* per pass, the messages decoded from the ``pass.end`` dump (``src`` = the blob with the position) interleaved with the
  ``model_call`` records of the ``llm.request``/``llm.response`` pairs (context from ``input_at``, O; else aligned under
  ``cap.context_alignment@1``, D; sent transforms computed from the wire request), the ``tool_execution`` records of the
  ``tool.dispatch``/``tool.result`` pairs (a ``denied`` result is a ``decision`` only, C.5.5), the ``decision`` records of
  defence hooks, the messages of discarded replies, and the ``state_change`` records (per pass, ``cause`` the attempt;
  per ``state`` event, ``cause`` the execution);
* the ``judgement`` records of the ``outcome`` event (``by: benchmark``, origin as recorded by the harness).

A session whose ``identity.agent.provider`` is ``anthropic`` (D-656) recorded the Anthropic Messages wire: its sent
forms, reply agreement and discarded replies are read by :mod:`agentprov.adapters.agentdojo.messages_wire` under the
``anthropic_messages`` catalogue, which only such a session's header cites, and a reasoning part that the provider
returned as an empty thinking block with a signature (display ``omitted``) has its text withheld
(``anthropic_messages.thinking_omitted@1``). Every other session is read exactly as before.

The live accounting checks of C.12.2 that need the capture (``passes_closed``, ``dispatch_vs_results``,
``env_recorded``, ``capture_chain``) are passed to the writer through ``ctx.check``; the core checks are the writer's. The
native TraceLogger JSON is mapped with ``agentdojo.tracelogger`` under the same profile and the two common projections
are compared (D.10.4): a difference is the seal issue ``live_native_divergence`` naming the differing pointers.

Pure (A-2): the output is a function of the session's bytes, this code, the profile and the catalogues. Untrusted bytes
(blobs, the native log) are parsed only through :mod:`agentprov.ingest`. No time, host or path enters the AER.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from agentprov.adapters.agentdojo import messages_wire as mw
from agentprov.adapters.agentdojo.capture_reader import DIALECT_ID, VARIANT, CaptureLogView
from agentprov.adapters.agentdojo.dialect import TraceLoggerReader
from agentprov.adapters.agentdojo.mapper import ADAPTER_ID as TRACELOGGER_ID
from agentprov.adapters.agentdojo.mapper import TraceLoggerMapper, content_block_parts, single_text_block
from agentprov.adapters.agentdojo.profile import family_table
from agentprov.adapters.projection import common_projection, projection_bytes, projection_differences
from agentprov.adapters.protocols import AerRecord, MappingContext
from agentprov.adapters.types import ArtefactRef, ExecutionUnit
from agentprov.aer.canon import LexHints, encode_value, json_pointer
from agentprov.aer.ids import LOCAL_ID_RE, import_execution_id, mapping_id, part_id
from agentprov.aer.types import (
    ACTOR_KINDS,
    DECISION_VERDICTS,
    FIXTURE_KINDS,
    INSTRUMENTATION_KINDS,
    INSTRUMENTATION_RECORDED,
    JUDGEMENT_ORIGINS,
    MODEL_CALL_STATUS,
)
from agentprov.errors import AgentProvError, IngestError, MalformedArtefact, UnsupportedVariant
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads
from agentprov.io.canonical import jcs_bytes

__all__ = ["ADAPTER_ID", "ADAPTER_VERSION", "CATALOGUES", "NAMESPACES", "AgentDojoCaptureMapper", "native_comparable"]

ADAPTER_ID: Final = "agentdojo.capture"
ADAPTER_VERSION: Final = "0.1.0"
#: Catalogues this mapper cites; the header lists them at the shipped versions (C.3.1 ``rules``).
CATALOGUES: Final = ("aer", "agentdojo", "cap")
NAMESPACES: Final = {"agentdojo": "https://w3id.org/agentprov/ns/agentdojo#"}

_TS: Final = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?Z")
_HEX64: Final = re.compile(r"[0-9a-f]{64}")
_DIGEST: Final = re.compile(r"sha256:([0-9a-f]{64})")
_RULE_ID: Final = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+@[1-9][0-9]*")
_USAGE_KEYS: Final = ("input_tokens", "output_tokens", "total_tokens", "reasoning_tokens", "cache_read_tokens",
                      "cache_write_tokens", "calls")
_MODEL_KEYS: Final = ("requested", "served", "provider", "endpoint")
_CODE_KEYS: Final = ("repo", "commit", "wheel_sha256")
_INSTRUMENTATION_KEYS: Final = frozenset({"id", "kind", "recorded", "params", "detail", "code_ref"})
_CODE_REF_KEYS: Final = frozenset({"repo", "commit", "path", "lines"})
#: Members a sent assistant message may carry besides those the stock rendering writes (OpenAI chat format).
#: D-685 (b): the quirk under which a reply's unconvertible tool calls are recognised as dropped by the harness
#: (declared by the ``agentdyn-live`` profile only) and the rule that lists them.
DROPPED_CALL_QUIRK: Final = "agentdojo.malformed_tool_call_dropped"
DROPPED_CALL_RULE: Final = "agentdyn.malformed_tool_call_dropped@1"
_WIRE_KEYS: Final = frozenset({"role", "content", "tool_calls", "name", "tool_call_id", "refusal"})
_REASONING_KEYS: Final = frozenset({"reasoning", "reasoning_content", "reasoning_details"})
_ROLE_REWRITE: Final = "agentdojo.role_rewrite_developer_to_system@1"
#: D-656: the catalogue of the Anthropic Messages wire, cited only by provider-``anthropic`` sessions.
_MSG_NS: Final = "anthropic_messages"
_MSG_SENT: Final = "anthropic_messages.sent_form@1"
_MSG_DISCARDED: Final = "anthropic_messages.discarded_reply@1"
_MSG_THINKING: Final = "anthropic_messages.thinking_omitted@1"
_MSG_STREAM: Final = "anthropic_messages.stream_read@1"
_SESSION_STATUS: Final = {"complete": "ok", "errored": "error", "aborted": "aborted"}
_SENTINELS: Final = frozenset({"", "0", "unknown", "none", "null", "n/a", "na", "-"})


# ------------------------------------------------------------------------------------------------ small helpers
def _lexical(value: object) -> str:
    """Lexical form of a decoded JSON value (member order and int/float kept; ASCII-escaped)."""
    return json.dumps(value, ensure_ascii=True, allow_nan=True, separators=(",", ":"))


def _int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _blob_hex(ref: object) -> str | None:
    """The hex digest of a well-formed BlobRef (``{"$blob": "sha256:<hex>", "bytes": int, "media"?: str}``)."""
    if not isinstance(ref, dict) or not set(ref) <= {"$blob", "bytes", "media"}:
        return None
    match = _DIGEST.fullmatch(str(ref.get("$blob")))
    if match is None or _int(ref.get("bytes")) is None or ("media" in ref and not isinstance(ref["media"], str)):
        return None
    return match.group(1)


def _typed(value: object) -> bool:
    """A string fit for a typed field (C.7.3: never a deny-listed placeholder)."""
    return isinstance(value, str) and value.strip().lower() not in _SENTINELS


class _Rec:
    """A record under construction: fields plus its lexical hints (C.11.4)."""

    def __init__(self, **fields: Any) -> None:
        self.data: dict[str, Any] = dict(fields)
        self.lex = LexHints()

    def enc(self, value: object, pointer: str) -> Any:
        return encode_value(value, at=pointer, lex=self.lex)

    def add(self, key: str, *items: Any) -> None:
        self.data.setdefault(key, []).extend(items)

    def tag(self, pointer: str, cls: str) -> None:
        self.data.setdefault("evf", {})[pointer] = cls

    def unk(self, pointer: str, reason: str) -> None:
        self.data.setdefault("unk", {})[pointer] = reason

    def ext(self) -> dict[str, Any]:
        ext = self.data.setdefault("ext", {})
        agentdojo: dict[str, Any] = ext.setdefault("agentdojo", {})
        return agentdojo

    def done(self) -> dict[str, Any]:
        out = dict(self.data)
        if self.lex:
            ext = dict(out.get("ext") or {})
            ext["lex"] = self.lex.as_dict()
            out["ext"] = ext
        return out


def _time(start: Mapping[str, Any] | None, end: Mapping[str, Any] | None) -> dict[str, Any]:
    """A ``Time`` object from the envelopes of the opening and closing events (C.8.3, C.8.4): the wall-clock ``ts``
    verbatim (microseconds, ``Z``) and the session-relative monotonic offsets."""
    t: dict[str, Any] = {}
    for event, wall, mono in ((start, "start", "mono_start_ns"), (end, "end", "mono_end_ns")):
        if event is None:
            continue
        ts = event.get("ts")
        if isinstance(ts, str) and _TS.fullmatch(ts):
            t[wall] = ts
        mono_ns = _int(event.get("mono_ns"))
        if mono_ns is not None and mono_ns >= 0:
            t[mono] = mono_ns
    return t


@dataclass
class _Call:
    seq: int
    event: Mapping[str, Any]
    data: dict[str, Any]
    pass_: int | None
    resp_seq: int | None = None
    resp_event: Mapping[str, Any] | None = None
    resp: dict[str, Any] = field(default_factory=dict)
    id: str = ""
    inputs: list[int] | None = None  # dump positions of the input, when known
    input_class: str | None = None  # "O" (input_at), "D" (alignment) or "invalid" (input_at naming no dump position)
    output: int | None = None  # dump position of the reply, when linked
    discarded_msg: str | None = None
    #: wire tool calls of the linked reply that the harness dropped (indices into its tool_calls; D-685 (b))
    dropped: list[int] = field(default_factory=list)


@dataclass
class _Tool:
    seq: int
    event: Mapping[str, Any]
    data: dict[str, Any]
    pass_: int | None
    res_seq: int | None = None
    res_event: Mapping[str, Any] | None = None
    res: dict[str, Any] = field(default_factory=dict)
    id: str = ""
    part: str | None = None  # the linked call part
    part_pos: int | None = None  # dump position of the assistant message holding it
    result_pos: int | None = None  # dump position of the tool message it generated
    lexical_args: Any = None  # the linked call's args as the dump holds them (source member order and number types)


@dataclass
class _Pass:
    index: int
    start: tuple[int, Mapping[str, Any]] | None = None
    end: tuple[int, Mapping[str, Any]] | None = None
    dump: list[Any] | None = None
    dump_hex: str | None = None
    offset: int = 0


class _SubContext:
    """The mapping context of the native log's TraceLogger mapping (the live-versus-native check): rules resolve as in
    the outer context, issues and checks are kept apart (they belong to the native AER, which is never sealed)."""

    def __init__(self, outer: Any, mapping: str, ex: str) -> None:
        self.profile = outer.profile
        self.rules = outer.rules
        self.mapping_id = mapping
        self.ex = ex
        self._outer = outer
        self.issues: list[dict[str, Any]] = []

    def rule(self, rule_id: str, pointer: str | None = None) -> str:
        result: str = self._outer.rule(rule_id, pointer)
        return result

    def catalogue_versions(self, namespaces: Sequence[str]) -> dict[str, int]:
        result: dict[str, int] = self._outer.catalogue_versions(namespaces)
        return result

    def issue(self, code: str, **kwargs: Any) -> None:
        self.issues.append({"code": code, **kwargs})

    def check(self, check_id: str, **kwargs: Any) -> None:
        return None

    def open_auxiliary(self, role: str) -> bytes:
        raise AgentProvError("the native log has no auxiliary artefacts", code="adapter.auxiliary_missing")


# ------------------------------------------------------------------------------------------------ the mapper
class AgentDojoCaptureMapper:
    """``Mapper`` for ``agentdojo.capture`` (D.2.4, D.10.4)."""

    mapper_id: Final = ADAPTER_ID
    version: Final = ADAPTER_VERSION
    accepts: Final = frozenset({(DIALECT_ID, VARIANT)})
    namespaces: Final = NAMESPACES
    catalogues: Final = CATALOGUES

    def map(self, unit: ExecutionUnit, ctx: MappingContext) -> Iterator[AerRecord]:
        yield from _Live(unit, ctx).run()

    @staticmethod
    def prov_primary(flags: frozenset[str]) -> str:
        """A capture log is AgentPROV's own first-hand record of the execution (D.10.4: ``prov_primary: native``)."""
        return "native"

    def degenerate_header(self, unit: ExecutionUnit, ctx: MappingContext, *, issue_code: str, detail: str) -> dict[str, Any]:
        """The header of a degenerate AER (D.2.8 case 3). The reader admits only a log whose ``session.start`` verifies,
        so the session and cell are known; everything else is declared unknown. An attempt that is not a non-negative
        integer is left out rather than written as 0, so the header is refused and the unit is registered
        ``map.adapter_defect`` (D.2.8; regeneration-batch item 49)."""
        view = unit.primary.value if isinstance(unit.primary.value, CaptureLogView) else None
        start = _dict(view.events[0].get("data")) if view is not None and view.events else {}
        session = view.session if view is not None else None
        attempt = _int(start.get("attempt"))
        cell = _dict(start.get("cell"))
        header: dict[str, Any] = {
            "k": "execution", "id": "exec", "aer": "0.1", "ex": ctx.ex, "mode": "live", "unit": "agent_execution",
            "source_key": {"sha256": unit.primary.artefact.sha256, "loc": {}},
            "artifacts": [unit.primary.artefact.to_json()],
            "adapter": {"id": ADAPTER_ID, "version": ADAPTER_VERSION},
            "dialect": {"id": DIALECT_ID, "variant": VARIANT},
            "profile": ctx.profile.header(),
            "rules": ctx.catalogue_versions(CATALOGUES),
            "ns": dict(NAMESPACES), "canon": "jcs-rfc8785", "hash": "sha256",
            "capture": {"session": session, "log": "a0"},
            "task": {"benchmark": "agentdojo"},
            "ev": "D",
            # no instrumentation event was mapped: the member is omitted, not captured (aer/0.2, D-210)
            "unk": {"/instrumentation": "not_captured", "/task/task_id": "not_recorded"},
        }
        if attempt is not None and attempt >= 0:  # never a placeholder (item 49): no observed attempt, no header
            header["capture"]["attempt"] = attempt
        if _typed(cell.get("benchmark")) and _typed(cell.get("task_id")):
            lex = LexHints()
            header["task"] = {"benchmark": encode_value(cell["benchmark"], at="/task/benchmark", lex=lex),
                              "task_id": encode_value(cell["task_id"], at="/task/task_id", lex=lex)}
            del header["unk"]["/task/task_id"]
            header.update(ev="O", by="config", src=[{"a": "a0", "line": 0, "p": "/data/cell"}])
        ctx.issue(issue_code, ids=["exec"], rule=ctx.rule("agentdojo.capture_status@1"), severity="error", detail=detail)
        return header


class _Live:
    """One mapping run over one session."""

    def __init__(self, unit: ExecutionUnit, ctx: MappingContext) -> None:
        view = unit.primary.value
        if not isinstance(view, CaptureLogView) or view.session is None:
            raise MalformedArtefact("not a capture log view with a verified session.start")
        self.unit = unit
        self.ctx = ctx
        self.view = view
        self.events = list(view.events)
        self.session = view.session
        self.limits = IngestLimits()
        self.fam = family_table(ctx.profile)
        self.live = _dict(self.fam.data.get("live"))  # checked against family.schema.json
        self.body: list[Any] = []
        self._blobs: dict[str, bytes | None] = {}
        self._pending: list[tuple[str, list[str], str, str, str | None]] = []
        self.redactions: dict[int, list[dict[str, Any]]] = {}
        self.redacted_ids: dict[int, list[str]] = {}
        self._emitted: set[str] = {"exec"}
        self._records: dict[str, _Rec] = {}
        self._authors: dict[str, str] = {}
        #: a redact/modify decision's id -> the generator it replaced, used when the decision is not emitted (item 45)
        self._replaced_generator: dict[str, tuple[str, str]] = {}
        self._current_dump: list[Any] = []
        self._first_user_seen = False
        self._abort_pos: int | None = None
        self.role_rewrite = False
        self.attack: str | None = None
        self._replies: dict[str, mw.WireReply | None] = {}

    @property
    def messages_api(self) -> bool:
        """The session recorded the Anthropic Messages wire (``identity.agent.provider == "anthropic"``, O by capture)."""
        ident = getattr(self, "identity", None)
        return ident is not None and _dict(ident[1].get("agent")).get("provider") == "anthropic"

    def messages_reply(self, call: _Call) -> mw.WireReply | None:
        """The decoded Messages reply of a call's response blob (cached), or ``None``."""
        ref = call.resp.get("response")
        hexdigest = _blob_hex(ref)
        if hexdigest is None:
            return None
        if hexdigest not in self._replies:
            data = self.blob_bytes(hexdigest)
            self._replies[hexdigest] = None if data is None else mw.decode_reply(data, _dict(ref).get("media"), self.limits)
        return self._replies[hexdigest]

    # ------------------------------------------------------------------------------------------ helpers
    def R(self, rule_id: str, pointer: str | None = None) -> str:  # noqa: N802 - mirrors MappingContext.rule
        return self.ctx.rule(rule_id, pointer)

    def issue(self, code: str, ids: Sequence[str], rule: str, *, severity: str = "warning", detail: str | None = None) -> None:
        """Collect a seal issue; issues reach the context when the records are complete (:meth:`_flush_issues`)."""
        entry = (code, list(ids), rule, severity, detail)
        if entry not in self._pending:
            self._pending.append(entry)

    def _flush_issues(self) -> None:
        """Hand the issues to the context. An id that names no emitted record (a record dropped as malformed) is
        replaced by ``exec``: a seal issue never names a dangling id (C.3.11)."""
        emitted = {"exec"} | {r.data["id"] if isinstance(r, _Rec) else r["id"] for r in self.body}
        for code, ids, rule, severity, detail in self._pending:
            named = [i if i.partition("#")[0] in emitted else "exec" for i in ids]
            named = list(dict.fromkeys(named))
            self.ctx.issue(code, ids=named, rule=rule, severity=severity, detail=detail)  # type: ignore[arg-type]

    @staticmethod
    def L(seq: int, pointer: str = "") -> dict[str, Any]:  # noqa: N802 - locator constructor
        return {"a": "a0", "line": seq, "p": pointer}

    @staticmethod
    def B(hexdigest: str, pointer: str = "") -> dict[str, Any]:  # noqa: N802 - locator constructor
        return {"blob": f"sha256:{hexdigest}", "p": pointer}

    def BP(self, hexdigest: str, pointer: str | None) -> dict[str, Any]:  # noqa: N802 - locator constructor
        """A blob locator at ``pointer``, or the whole blob (no ``p``) for ``None`` (an event stream is not JSON)."""
        return self.B(hexdigest, pointer) if pointer is not None else {"blob": f"sha256:{hexdigest}"}

    def blob_bytes(self, hexdigest: str) -> bytes | None:
        if hexdigest not in self._blobs:
            try:
                data = self.ctx.open_auxiliary(f"blob:{hexdigest}")
            except AgentProvError:
                data = None
            self._blobs[hexdigest] = data if data is not None and hashlib.sha256(data).hexdigest() == hexdigest else None
        return self._blobs[hexdigest]

    def blob_json(self, ref: object) -> Any:
        """The parsed JSON of a referenced blob (strict loader), or ``None`` when absent or not JSON."""
        hexdigest = _blob_hex(ref)
        data = self.blob_bytes(hexdigest) if hexdigest is not None else None
        if data is None:
            return None
        try:
            return strict_json_loads(data, self.limits)
        except IngestError:
            return None

    def _json_text(self, text: str) -> Any:
        """A JSON document held in a string of the capture (tool-call ``arguments``), parsed by the bounded strict
        loader: ``IngestError`` (or ``UnicodeError`` for a lone surrogate) when it is not strict JSON within the limits."""
        return strict_json_loads(text.encode("utf-8"), self.limits)

    # ------------------------------------------------------------------------------------------ collect
    def _collect(self) -> None:
        self.start = _dict(self.events[0].get("data"))
        self.instr: tuple[int, dict[str, Any]] | None = None
        self.identity: tuple[int, dict[str, Any]] | None = None
        self.fixtures: list[tuple[int, dict[str, Any]]] = []
        self.passes: dict[int, _Pass] = {}
        self.calls: dict[str, _Call] = {}
        self.call_order: list[_Call] = []
        self.tools: dict[str, _Tool] = {}
        self.tool_order: list[_Tool] = []
        self.orphan_results: list[tuple[int, Mapping[str, Any]]] = []
        self.decisions: list[tuple[int, Mapping[str, Any]]] = []
        self.states: list[tuple[int, Mapping[str, Any]]] = []
        self.outcomes: list[tuple[int, dict[str, Any]]] = []
        self.native_seq: int | None = None
        self.errors: list[tuple[int, dict[str, Any]]] = []
        self.end: tuple[int, dict[str, Any]] | None = None
        self.observed: tuple[int, dict[str, Any]] | None = None  # D.10.10 item 6 note
        self.run_error_note: tuple[int, dict[str, Any]] | None = None
        # D-670 (defended pipelines): the harness's defence recorders' notes
        self.defence_msgs: dict[tuple[int, int], tuple[int, dict[str, Any]]] = {}  # (pass, at) -> (seq, payload)
        self.denial_matches: dict[str, int] = {}  # occ -> seq of its defence_denial_match note
        self.post_hoc: set[str] = set()  # occurrences a gate's recorder dispatched after the defence decided
        self.detached_calls: dict[str, int] = {}  # wire call -> seq of its defence_detached_input note
        self.replaced_calls: dict[str, int] = {}  # agent call -> seq of the modify decision that replaced its reply
        self.defence_identity: tuple[int, dict[str, Any]] | None = None
        backend = _dict(self.start.get("backend")).get("id")
        self.backend_id: str | None = backend if isinstance(backend, str) and backend else None
        for seq, event in enumerate(self.events):
            kind, data = event.get("type"), _dict(event.get("data"))
            p = _int(event.get("pass"))
            p = p if p is not None and p >= 0 else None
            redactions = data.get("redactions")
            if isinstance(redactions, list) and redactions:
                self.redactions[seq] = [r for r in redactions if isinstance(r, dict)]
            if seq == 0:
                continue
            if kind == "instrumentation" and seq == 1:
                self.instr = (seq, data)
            elif kind == "identity" and self.identity is None:
                self.identity = (seq, data)
            elif kind == "fixture":
                self.fixtures.append((seq, data))
            elif kind in ("pass.start", "pass.end") and p is not None:
                entry = self.passes.setdefault(p, _Pass(p))
                slot = "start" if kind == "pass.start" else "end"
                if getattr(entry, slot) is not None:
                    self._malformed(seq, "duplicate pass boundary")
                else:
                    setattr(entry, slot, (seq, event))
            elif kind == "llm.request":
                call = _str(data.get("call"))
                if call is None or call in self.calls or not isinstance(event.get("actor"), str) \
                        or data.get("role") not in ("agent", "auxiliary"):
                    self._malformed(seq, "llm.request")
                    continue
                self.calls[call] = _Call(seq, event, data, p)
                self.call_order.append(self.calls[call])
            elif kind == "llm.response":
                target = self.calls.get(str(data.get("call")))
                if target is None or target.resp_event is not None:
                    self._malformed(seq, "llm.response")
                    continue
                target.resp_seq, target.resp_event, target.resp = seq, event, data
            elif kind == "tool.dispatch":
                occ = _str(data.get("occ"))
                if occ is None or occ in self.tools or not isinstance(event.get("actor"), str) or not _str(data.get("name")):
                    self._malformed(seq, "tool.dispatch")
                    continue
                self.tools[occ] = _Tool(seq, event, data, p)
                self.tool_order.append(self.tools[occ])
            elif kind == "tool.result":
                target_tool = self.tools.get(str(data.get("occ")))
                if target_tool is None or target_tool.res_event is not None:
                    self.orphan_results.append((seq, event))
                    continue
                target_tool.res_seq, target_tool.res_event, target_tool.res = seq, event, data
            elif kind == "decision":
                self.decisions.append((seq, event))
                subject = _dict(data.get("subject"))
                if data.get("verdict") == "modify" and isinstance(subject.get("call"), str):
                    self.replaced_calls.setdefault(subject["call"], seq)  # D-670: a defence replaced this call's reply
            elif kind == "state":
                self.states.append((seq, event))
            elif kind == "outcome":
                self.outcomes.append((seq, data))
            elif kind == "native.log":
                self.native_seq = seq
            elif kind == "error":
                self.errors.append((seq, data))
            elif kind == "session.end":
                self.end = (seq, data)
            elif kind == "note" and data.get("ns") == "agentdojo" and data.get("kind") == "instrumentation_observed" \
                    and isinstance(data.get("payload"), dict):
                self.observed = (seq, data["payload"])
            elif kind == "note" and data.get("ns") == "agentdojo" and data.get("kind") in DEFENCE_NOTES \
                    and isinstance(data.get("payload"), dict):
                self._defence_note(seq, p, str(data["kind"]), data["payload"])
            elif kind == "note" and data.get("kind") == "run_error_imposed" and isinstance(data.get("payload"), dict) \
                    and data.get("ns") in ("agentdojo", self.backend_id) and self.run_error_note is None:
                self.run_error_note = (seq, data["payload"])  # D.11.7 item 7: the backend's reading of the run error
            elif kind not in ("note", "session.start", "instrumentation", "identity"):
                self._malformed(seq, "event type")
        offset = 0
        for index in sorted(self.passes):
            entry = self.passes[index]
            entry.offset = offset
            if entry.end is not None:
                ref = _dict(entry.end[1].get("data")).get("messages")
                dump = self.blob_json(ref)
                if isinstance(dump, list):
                    entry.dump, entry.dump_hex = dump, _blob_hex(ref)
                else:
                    self.issue("capture_error", [f"att{index}"], self.R("agentdojo.capture_status@1"),
                               detail=f"pass {index}: native message dump unavailable (seq {entry.end[0]})")
            offset += len(entry.dump or [])
        self.n_dump = offset
        for n, ordered in enumerate(sorted(self.call_order, key=lambda c: c.seq)):
            ordered.id = f"mc{n}"
        executed = [t for t in self.tool_order if t.res.get("status") != "denied"]
        for n, tool in enumerate(executed):
            tool.id = f"te{n}"

    def _defence_note(self, seq: int, p: int | None, kind: str, payload: Mapping[str, Any]) -> None:
        """D-670: what a defence recorder observed (``agentprov_backend.defences``). Notes are adapter facts (C.13.3);
        a malformed one is reported and ignored, never guessed at."""
        if kind == "defence_message":
            at, actor = _int(payload.get("at")), payload.get("actor")
            if p is None or at is None or at < 0 or not isinstance(actor, str) or (p, at) in self.defence_msgs:
                self._malformed(seq, "defence_message note")
                return
            self.defence_msgs[(p, at)] = (seq, dict(payload))
        elif kind == "defence_denial_match":
            occ = _str(payload.get("occ"))
            if occ is None or occ in self.denial_matches:
                self._malformed(seq, "defence_denial_match note")
                return
            self.denial_matches[occ] = seq
        elif kind == "defence_gate_post_hoc":
            occs = payload.get("occs")
            if not isinstance(occs, list) or not all(isinstance(o, str) for o in occs):
                self._malformed(seq, "defence_gate_post_hoc note")
                return
            self.post_hoc.update(occs)
        elif kind == "defence_detached_input":
            calls = payload.get("calls")
            if not isinstance(calls, list) or not all(isinstance(c, str) for c in calls):
                self._malformed(seq, "defence_detached_input note")
                return
            for call in calls:
                self.detached_calls[call] = seq
        elif kind == "defence_identity" and self.defence_identity is None:
            self.defence_identity = (seq, dict(payload))  # the first one; a later one is ignored

    def _malformed(self, seq: int, what: str) -> None:
        self.issue("capture_error", ["run"], self.R("agentdojo.capture_status@1"),
                   detail=f"seq {seq}: malformed or unexpected {what} event, not mapped")

    # ------------------------------------------------------------------------------------------ run
    def run(self) -> Iterator[dict[str, Any]]:
        self._collect()
        header = self._header()
        self.h = header
        self._backend_identity()
        self._actors()
        self._scopes()
        self._fixtures()
        self.dc_ids: dict[int, str] = {}
        dc_seqs = sorted([t.res_seq for t in self.tool_order if t.res.get("status") == "denied" and t.res_seq is not None]
                         + [s for s, _e in self.decisions])
        for n, seq in enumerate(dc_seqs):
            self.dc_ids[seq] = f"dc{n}"
        st_seqs = sorted([(p.end or p.start)[0] for p in self.passes.values() if (p.end or p.start) is not None]  # type: ignore[index]
                         + [s for s, _e in self.states])
        self.st_ids = {seq: f"st{n}" for n, seq in enumerate(st_seqs)}
        self.n_discarded = 0
        for index in sorted(self.passes):
            self._pass(self.passes[index])
        self._outside_passes()
        self._judgements()
        self._session_issues()
        self._redaction_issues()
        self._checks()
        records = [header.done()] + [r.done() if isinstance(r, _Rec) else r for r in self.body]
        self._native_check(records)
        self._flush_issues()
        yield from records

    # ------------------------------------------------------------------------------------------ header
    def _header(self) -> _Rec:
        h = _Rec()
        cell = _dict(self.start.get("cell"))
        attempt = _int(self.start.get("attempt"))
        if not (_typed(cell.get("benchmark")) and _typed(cell.get("task_id"))) or attempt is None or attempt < 0:
            raise MalformedArtefact("session.start without a cell benchmark, task id or attempt")
        if self.start.get("ex") != f"ex_{self.session}":
            raise MalformedArtefact("session.start ex is not ex_<session>")
        task: dict[str, Any] = {"benchmark": h.enc(cell["benchmark"], "/task/benchmark"),
                                "task_id": h.enc(cell["task_id"], "/task/task_id")}
        for key in ("suite", "environment"):
            if _typed(cell.get(key)):
                task[key] = h.enc(cell[key], f"/task/{key}")
        for key in ("attack_id", "attack_target_id", "defense_id"):
            if key in cell and (cell[key] is None or _typed(cell[key])):
                task[key] = h.enc(cell[key], f"/task/{key}")
        self.attack = cell.get("attack_id") if _typed(cell.get("attack_id")) else None
        src = [self.L(0, "/data/cell")]
        evf: dict[str, str] = {}
        rules: list[str] = []
        unk: dict[str, str] = {}
        catalogues = set(CATALOGUES)
        if self.fam.quirk(DROPPED_CALL_QUIRK) is not None:
            catalogues.add("agentdyn")  # D-685 (b): a dropped call cites agentdyn.malformed_tool_call_dropped@1 in any suite
        if self.messages_api:
            catalogues.add(_MSG_NS)
        ext: dict[str, Any] = {}
        # regeneration-batch item 27 (a): the benchmark of the cell's suite from the profile's suites map, as the
        # TraceLogger mapper reads it (D.6.5 step 1); AutoDojo names every cell "agentdojo". Only an AgentDyn suite of
        # the fork has a rule (agentdyn.suite_benchmark@1); the cell's value stays in ext.agentdojo.cell_benchmark.
        suite = cell.get("suite")
        if _typed(suite) and str(suite) in _dict(self.fam.benchmark.get("suites")):
            derived = self.fam.benchmark_of(str(suite))
            if derived == "agentdyn" and derived != cell["benchmark"]:
                task["benchmark"] = derived
                evf["/task/benchmark"] = "D"
                rules.append(self.R("agentdyn.suite_benchmark@1", "/task/benchmark"))
                catalogues.add("agentdyn")
                ext["cell_benchmark"] = h.enc(cell["benchmark"], "/ext/agentdojo/cell_benchmark")
        if self.defence_identity is not None or self.defence_msgs or self.denial_matches:
            catalogues.add("defence")  # D-670, D-677: the defence rules live in their own catalogue
        items: list[Any] = []
        if self.instr is not None:
            items = self._instrumentation(h, self.instr)
            evf["/instrumentation"] = "O:capture"
            src.append(self.L(self.instr[0], "/data/items"))
            if self.observed is not None:
                src.append(self.L(self.observed[0], "/data/payload"))
        else:  # the prefix ends before the instrumentation event: omitted, not captured (aer/0.2, D-210; D.10.4a item 5)
            unk["/instrumentation"] = "not_captured"
        artefacts = [self.unit.primary.artefact.to_json()]
        native = self.unit.auxiliary.get("native_log")
        if isinstance(native, ArtefactRef):
            artefacts.append(native.to_json())
        cache = self.unit.auxiliary.get("attack_cache")
        if isinstance(cache, ArtefactRef):  # D.11.9: the replayed attack cache (supporting)
            artefacts.append(cache.to_json())
        h.data.update(
            {
                "k": "execution", "id": "exec", "aer": "0.1", "ex": self.ctx.ex, "mode": "live",
                "unit": "agent_execution",
                "source_key": {"sha256": self.unit.primary.artefact.sha256, "loc": {}},
                "artifacts": artefacts,
                "adapter": {"id": ADAPTER_ID, "version": ADAPTER_VERSION},
                "dialect": {"id": DIALECT_ID, "variant": VARIANT},
                "profile": self.ctx.profile.header(),
                "rules": self.ctx.catalogue_versions(sorted(catalogues)),
                "ns": dict(NAMESPACES), "canon": "jcs-rfc8785", "hash": "sha256",
                "capture": {"session": self.session, "log": "a0", "attempt": attempt},
                "task": task,
                **({"instrumentation": items} if self.instr is not None else {}),
                "ev": "O", "by": "config", "src": src,
            }
        )
        if self.defence_identity is not None:  # D-670: the defence's registry entry and digests, as recorded (O)
            seq, payload = self.defence_identity
            ext["defence"] = h.enc(payload, "/ext/agentdojo/defence")
            src.append(self.L(seq, "/data/payload"))
        if ext:
            h.data["ext"] = {"agentdojo": ext}
        if evf:
            h.data["evf"] = evf
        if rules:
            h.data["rule"] = rules
        if unk:
            h.data["unk"] = unk
        return h

    def _instrumentation(self, h: _Rec, instr: tuple[int, dict[str, Any]]) -> list[Any]:
        """The items of the ``instrumentation`` event in the closed AD-03 shape; any other item is reported."""
        seq, data = instr
        accepted = {str(i) for i in self.live.get("instrumentation_accepted", ())}
        accepted |= {str(i) for i in self.live.get("instrumentation_extra", ())}
        out: list[Any] = []
        raw = data.get("items")
        for k, item in enumerate(raw if isinstance(raw, list) else []):
            ok = (isinstance(item, dict) and set(item) <= _INSTRUMENTATION_KEYS
                  and isinstance(item.get("id"), str) and _RULE_ID.fullmatch(item["id"]) is not None
                  and item.get("kind") in INSTRUMENTATION_KINDS and item.get("recorded") in INSTRUMENTATION_RECORDED
                  and ("detail" not in item or isinstance(item["detail"], str))
                  and ("code_ref" not in item or self._code_ref_ok(item["code_ref"])))
            if not ok:
                self.issue("capture_error", ["exec"], self.R("agentdojo.capture_instrumentation@1"),
                           detail=f"seq {seq}: instrumentation item {k} is not in the AD-03 shape, not copied")
                continue
            observed = self.observed[1].get(item["id"]) if self.observed is not None else None
            if isinstance(observed, dict) and all(isinstance(v, int) and not isinstance(v, bool) and v >= 0
                                                  for v in observed.values()):
                # D.10.7: per-execution counts in params.observed (written by the harness as a note, D.10.10 item 6)
                params = item.get("params")
                item = dict(item, params=dict(params if isinstance(params, dict) else {}, observed=observed))
            out.append(h.enc(item, f"/instrumentation/{len(out)}"))
            if item["id"] not in accepted:
                self.issue("agentdojo.instrumentation_unrecognised", ["exec"], self.R("agentdojo.capture_instrumentation@1"),
                           detail=str(item["id"]))
        self.role_rewrite = any(isinstance(i, dict) and i.get("id") == _ROLE_REWRITE for i in out)
        return out

    @staticmethod
    def _code_ref_ok(value: object) -> bool:
        return (isinstance(value, dict) and set(value) <= _CODE_REF_KEYS and {"repo", "commit", "path"} <= set(value)
                and all(isinstance(v, str) for v in value.values()) and re.fullmatch(r"[0-9a-f]{40}", value["commit"]) is not None)

    # ------------------------------------------------------------------------------------------ actors
    def _actors(self) -> None:
        declared = _dict(self.start.get("actors"))
        for tag, spec in declared.items():
            if not isinstance(tag, str) or LOCAL_ID_RE.fullmatch(tag) is None or tag in ("exec", "run", "seal") \
                    or re.fullmatch(r"(m|mc|te|dc|st|fx|j|ac|af|att)[0-9]+", tag) or not isinstance(spec, dict) \
                    or spec.get("kind") not in ACTOR_KINDS or spec.get("kind") == "other":
                raise MalformedArtefact("session.start declares an actor tag or kind outside the AER grammar")
        self.actor_kind = {tag: str(spec["kind"]) for tag, spec in declared.items()}
        agents = [t for t, k in self.actor_kind.items() if k == "llm_agent"]
        self.agent = agents[0] if agents else None
        users = [t for t, k in self.actor_kind.items() if k in ("user", "simulated_user")]
        # one benchmark actor: a declared one (the harness declares ``bench``) receives the identity's versions
        benches = [t for t, k in self.actor_kind.items() if k == "benchmark"]
        self.bench = benches[0] if benches else ("bench" if "bench" not in declared else "bench0")
        self.body.append(self._bench_actor(declared.get(self.bench)))
        if self.identity is not None and isinstance(self.identity[1].get("harness"), dict) and "harness" not in declared:
            self.body.append(self._harness_actor())
        self.user = users[0] if users else ("user" if "user" not in declared else "user0")
        if not users:
            self.body.append({"k": "actor", "id": self.user, "kind": "simulated_user", "ev": "D",
                              "rule": [self.R("agentdojo.user_is_simulated@1")]})
        order = [t for t in declared if self.actor_kind[t] in ("user", "simulated_user")]
        order += [t for t in declared if self.actor_kind[t] == "llm_agent"]
        order += [t for t in declared if t not in order]
        for tag in order:
            if tag != self.bench:
                self.body.append(self._declared_actor(tag, declared[tag]))
        self.attacker: str | None = next((t for t, k in self.actor_kind.items() if k == "attacker"), None)
        if self.attack is not None and self.attacker is None and "att" not in declared:
            att = _Rec(k="actor", id="att", kind="attacker", ev="O", by="config", src=[self.L(0, "/data/cell/attack_id")])
            att.data["name"] = att.enc(self.attack, "/name")
            self.body.append(att)
            self.attacker = "att"
            self.actor_kind["att"] = "attacker"

    def _bench_actor(self, spec: Mapping[str, Any] | None = None) -> _Rec:
        """The benchmark actor: the identity event's benchmark (``O`` by capture) merged into the declared benchmark
        actor when ``session.start`` declares one (its ``name``/``role`` kept, its line cited), else a new actor."""
        bench = _Rec(k="actor", id=self.bench, kind="benchmark")
        ident = _dict(self.identity[1].get("benchmark")) if self.identity is not None else {}
        cell = _dict(self.start.get("cell"))
        declared = _dict(spec)
        if _typed(ident.get("name")):
            name = ident["name"]
        elif _typed(declared.get("name")):
            name = declared["name"]
        else:
            name = cell["benchmark"]
        bench.data["name"] = bench.enc(name, "/name")
        if _typed(declared.get("role")):
            bench.data["role"] = bench.enc(declared["role"], "/role")
        config_src = [self.L(0, json_pointer("data", "actors", self.bench))] if spec is not None else []
        if not ident:
            bench.data.update(ev="O", by="config", src=config_src or [self.L(0, "/data/cell/benchmark")],
                              unk={"/code": "not_captured", "/version": "not_captured"})
            return bench
        assert self.identity is not None
        seq = self.identity[0]
        bench.data.update(ev="O", by="capture", src=[*config_src, self.L(seq, "/data/benchmark")])
        if _typed(ident.get("suite_set")):
            bench.data["version"] = bench.enc(ident["suite_set"], "/version")
            suite = cell.get("suite")
            meaning = self.fam.version_label_semantics(str(suite)) if _typed(suite) else "suite_version"
            if meaning != "suite_version":  # D.6.12 item 5, as the TraceLogger mapper reads it (item 27 (b))
                bench.ext()["version_label_semantics"] = meaning
                bench.tag("/ext/agentdojo/version_label_semantics", "I")
                bench.add("rule", self.R("agentdojo.version_label_semantics@1", "/ext/agentdojo/version_label_semantics"))
        else:
            bench.unk("/version", "not_recorded")
        code = self._code(bench, ident, "dist_version")
        if code:
            bench.data["code"] = code
        return bench

    def _code(self, rec: _Rec, ident: Mapping[str, Any], version_key: str) -> dict[str, Any]:
        """``Code`` (C.3.12, closed) from an identity object: ``dist``, ``dist_version`` and the optional members."""
        code: dict[str, Any] = {}
        if _typed(ident.get("dist")):
            code["dist"] = rec.enc(ident["dist"], "/code/dist")
        if _typed(ident.get(version_key)):
            code["dist_version"] = rec.enc(ident[version_key], "/code/dist_version")
        for key in _CODE_KEYS:
            value = ident.get(key)
            if key == "repo" and _typed(value):
                code[key] = rec.enc(value, f"/code/{key}")
            elif key == "commit" and isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value):
                code[key] = value
            elif key == "wheel_sha256" and isinstance(value, str) and _HEX64.fullmatch(value):
                code[key] = value
        return code

    def _harness_actor(self) -> _Rec:
        assert self.identity is not None
        seq, data = self.identity
        ident = _dict(data.get("harness"))
        rec = _Rec(k="actor", id="harness", kind="harness", ev="O", by="capture", src=[self.L(seq, "/data/harness")])
        if _typed(ident.get("dist")):
            rec.data["name"] = rec.enc(ident["dist"], "/name")
        code = self._code(rec, ident, "version")
        if code:
            rec.data["code"] = code
        self.actor_kind["harness"] = "harness"
        return rec

    def _declared_actor(self, tag: str, spec: Mapping[str, Any]) -> _Rec:
        kind = self.actor_kind[tag]
        rec = _Rec(k="actor", id=tag, kind=kind, ev="O", by="config", src=[self.L(0, json_pointer("data", "actors", tag))])
        for key in ("name", "role"):
            if _typed(spec.get(key)):
                rec.data[key] = rec.enc(spec[key], f"/{key}")
        rules: list[str] = []
        if kind == "llm_agent":
            model = {k: rec.enc(v, f"/model/{k}") for k, v in _dict(spec.get("model")).items() if k in _MODEL_KEYS and _typed(v)}
            agent = _dict(self.identity[1].get("agent")) if self.identity is not None and tag == self.agent else {}
            if agent:
                assert self.identity is not None
                if "requested" not in model and _typed(agent.get("model_requested")):
                    model["requested"] = rec.enc(agent["model_requested"], "/model/requested")
                    rec.tag("/model/requested", "O:capture")
                for key, src_key in (("provider", "provider"), ("endpoint", "endpoint_host")):
                    if key not in model and _typed(agent.get(src_key)):
                        model[key] = rec.enc(agent[src_key], f"/model/{key}")
                        rec.tag(f"/model/{key}", "O:capture")
                rec.add("src", self.L(self.identity[0], "/data/agent"))
            if model:
                rec.data["model"] = dict(sorted(model.items()))
            rec.data["on_behalf_of"] = self.user
            rec.tag("/on_behalf_of", "D")
            rules.append(self.R("agentdojo.user_is_simulated@1", "/on_behalf_of"))
        elif kind == "tool_runtime" and self.agent is not None:
            rec.data["on_behalf_of"] = self.agent
            rec.tag("/on_behalf_of", "I")
            rules.append(self.R("agentdojo.auto_execution_unverified@1", "/on_behalf_of"))
        if rules:
            rec.data["rule"] = rules
        return rec

    # ------------------------------------------------------------------------------------------ scopes
    def _scopes(self) -> None:
        run = _Rec(k="scope", id="run", kind="run", ev="O", by="capture", src=[self.L(0, "/data")])
        if self.agent is not None:
            run.data["actor"] = self.agent
        end_event = self.events[self.end[0]] if self.end is not None else None
        t = _time(self.events[0], end_event)
        if t:
            run.data["t"] = t
        rules: list[str] = []
        fatal = [seq for seq, data in self.errors if data.get("fatal") is True]
        status = _SESSION_STATUS.get(str(self.end[1].get("status"))) if self.end is not None else None
        if self.end is not None:
            run.add("src", self.L(self.end[0], "/data"))
        if not self.view.sealed or self.end is None:
            run.data["status"] = "error"
            run.tag("/status", "D")
            rules.append(self.R("agentdojo.capture_status@1", "/status"))
            if self.end is None:
                run.unk("/t/end", "not_captured")
        elif fatal and status != "error":
            run.data["status"] = "error"
            run.tag("/status", "D")
            rules.append(self.R("agentdojo.capture_status@1", "/status"))
        elif status is not None:
            run.data["status"] = status
        else:  # `incomplete` (or an unknown value): no scope status expresses it
            run.unk("/status", "ambiguous")
            rules.append(self.R("agentdojo.capture_status@1", "/status"))
            self.issue("incomplete_run", ["run"], self.R("agentdojo.capture_status@1"))
        if rules:
            run.data["rule"] = rules
        self.body.append(run)
        last = max(self.passes) if self.passes else None
        for index in sorted(self.passes):
            entry = self.passes[index]
            att = _Rec(k="scope", id=f"att{index}", kind="attempt", parent="run", index=index, ev="O", by="capture")
            if self.agent is not None:
                att.data["actor"] = self.agent
            att.data["src"] = [self.L(b[0], "/data") for b in (entry.start, entry.end) if b is not None]
            t = _time(entry.start[1] if entry.start else None, entry.end[1] if entry.end else None)
            if t:
                att.data["t"] = t
            if entry.start is None:
                att.unk("/t/start", "not_captured")
            att.data["scored"] = index == last
            att.tag("/scored", "D")
            att_rules = [self.R("agentdojo.capture_last_pass_scored@1", "/scored")]
            if entry.end is None:
                att.unk("/t/end", "not_captured")
                att.unk("/status", "not_captured")
            elif _dict(entry.end[1].get("data")).get("aborted") is True:
                att.data["status"] = "aborted"
                self.issue("aborted_attempt", [f"att{index}"], self.R("agentdojo.capture_status@1"))
            elif _dict(entry.end[1].get("data")).get("aborted") is False:
                att.data["status"] = "ok"
            else:
                att.unk("/status", "not_captured")
            att.data["rule"] = att_rules
            self.body.append(att)

    # ------------------------------------------------------------------------------------------ fixtures
    def _fixtures(self) -> None:
        n = 0
        for seq, data in self.fixtures:
            kind = data.get("kind")
            if kind not in FIXTURE_KINDS or kind == "other" or "content" not in data:
                self._malformed(seq, "fixture")
                continue
            rec = _Rec(k="fixture", id=f"fx{n}", kind=kind, ev="O", by="benchmark", src=[self.L(seq, "/data")])
            n += 1
            if isinstance(data.get("vector"), str):
                rec.data["vector"] = rec.enc(data["vector"], "/vector")
            content = data["content"]
            rec.data["content"] = content if _blob_hex(content) is not None else rec.enc(content, "/content")
            if self.attacker is not None and kind == "injection_payload":
                rec.data.update(actor=self.attacker, evf={"/actor": "I"},
                                rule=[self.R("agentdojo.payload_attributed_to_attacker@1", "/actor")])
            self.body.append(rec)

    # ------------------------------------------------------------------------------------------ passes
    def _mid(self, entry: _Pass, pos: int) -> str:
        return f"m{entry.offset + pos}"

    def _pass(self, entry: _Pass) -> None:
        scope = f"att{entry.index}"
        dump = entry.dump or []
        self._current_dump = dump
        self._first_user_seen = False  # every pass starts a new message list (run_task_with_pipeline queries afresh)
        calls = [c for c in self.call_order if c.pass_ == entry.index]
        tools = [t for t in self.tool_order if t.pass_ == entry.index]
        n = len(dump)
        shapes = [self._shape(m) for m in dump]
        content_parts = [self._content_len(m) if s is not None else 1 for m, s in zip(dump, shapes, strict=True)]
        # inputs and outputs of the calls
        for call in calls:
            call.inputs = self._input_positions(entry, call)
        self._link_outputs(entry, calls, shapes)
        self._abort_pos = self._abort_message(entry, calls, shapes)
        # tool calls of the dump and the linking of executions
        call_parts: dict[str, tuple[int, int]] = {}  # part id -> (message position, call index)
        for i, (message, shape) in enumerate(zip(dump, shapes, strict=True)):
            if shape == "assistant":
                for j, _call in enumerate(message.get("tool_calls") or []):
                    call_parts[part_id(self._mid(entry, i), content_parts[i] + j)] = (i, j)
        self._link_tools(entry, tools, dump, shapes, content_parts, call_parts)
        responds = self._link_results(entry, dump, shapes, content_parts)
        generators: dict[int, tuple[str, str]] = {}  # tool message position -> (generator id, its evidence tag)
        denied_parts: set[str] = set()
        for tool in tools:
            if tool.part is None:
                continue
            target = next((pos for pos, (part, _tag, _rule) in responds.items() if part == tool.part and pos not in generators),
                          None)
            if tool.res.get("status") == "denied":
                denied_parts.add(tool.part)
                gid = self.dc_ids.get(tool.res_seq or -1)
            else:
                gid = tool.id
            if target is not None and gid is not None and target > (tool.part_pos or 0):
                generators[target] = (gid, responds[target][1])
                tool.result_pos = target
        for seq, event in self.decisions:  # a decision whose subject is an execution generates that execution's result
            subject = _dict(_dict(event.get("data")).get("subject"))
            subject_tool = self.tools.get(str(subject.get("occ"))) if "occ" in subject else None
            data = _dict(event.get("data"))
            if _int(event.get("pass")) == entry.index and subject_tool is not None and subject_tool.pass_ == entry.index \
                    and subject_tool.result_pos is not None and data.get("verdict") in ("redact", "modify"):
                self._replaced_generator[self.dc_ids[seq]] = generators[subject_tool.result_pos]
                generators[subject_tool.result_pos] = (self.dc_ids[seq], generators[subject_tool.result_pos][1])
        # order: each activity in the slot of the message it generates, else after its last premise
        items: list[tuple[tuple[int, int, float], Any]] = []
        for call in calls:
            deps = call.inputs or []
            slot = call.output if call.output is not None else ((max(deps) + 1) if deps else 0)
            items.append(((slot, 0, call.seq), ("call", call)))
        for tool in tools:
            if tool.res.get("status") == "denied":
                if tool.part is None or tool.res_seq not in self.dc_ids:
                    self._malformed(tool.res_seq or tool.seq, "denied tool.result without a linkable call")
                    continue
                slot = tool.result_pos if tool.result_pos is not None else (tool.part_pos or 0) + 1
                items.append(((slot, 0, tool.res_seq or tool.seq), ("denial", tool)))
                continue
            slot = tool.result_pos if tool.result_pos is not None else ((tool.part_pos + 1) if tool.part_pos is not None else n)
            items.append(((slot, 0, tool.seq), ("tool", tool)))
        for seq, event in self.decisions:
            if _int(event.get("pass")) != entry.index:
                continue
            items.append(((self._decision_slot(event, entry, calls, n), 0, seq), ("decision", (seq, event))))
        for seq, event in self.states:
            if _int(event.get("pass")) != entry.index:
                continue
            cause = self.tools.get(str(_dict(event.get("data")).get("occ")))
            slot = n
            if cause is not None and cause.pass_ == entry.index and cause.id:
                slot = cause.result_pos if cause.result_pos is not None else (
                    (cause.part_pos + 1) if cause.part_pos is not None else n)
            items.append(((slot, 0, seq), ("state", (seq, event))))
        for i in range(n):
            items.append(((i, 1, 0), ("message", i)))
        items.append(((n, 2, 0), ("pass_state", None)))
        items.sort(key=lambda x: x[0])
        self._unexecuted(entry, dump, shapes, content_parts, call_parts, tools, denied_parts)
        prev: str | None = None
        for _key, (what, obj) in items:
            if what == "call":
                self._model_call(entry, obj, scope, shapes)
            elif what == "tool":
                self._tool_execution(obj, scope)
            elif what == "denial":
                self._denial(obj, scope)
            elif what == "decision":
                self._decision_event(obj[0], obj[1], scope)
            elif what == "state":
                self._state_event(obj[0], obj[1], scope)
            elif what == "message":
                mid = self._message(entry, obj, scope, shapes, content_parts, responds, generators, prev)
                prev = mid
            else:
                self._pass_state(entry, scope)

    @staticmethod
    def _shape(message: object) -> str | None:
        """The role of a message of a known ChatMessage shape (0.1.35 ``types.py``), else ``None``."""
        if not isinstance(message, dict):
            return None
        role = message.get("role")
        if role not in ("system", "user", "assistant", "tool"):
            return None
        content = message.get("content")
        if not (content is None or isinstance(content, str) or (isinstance(content, list) and all(isinstance(b, dict) for b in content))):
            return None
        if role == "assistant":
            calls = message.get("tool_calls")
            if calls is not None and not (isinstance(calls, list) and all(_call_ok(c) for c in calls)):
                return None
        if role == "tool" and (not _call_ok(message.get("tool_call"))
                               or not (message.get("error") is None or isinstance(message.get("error"), str))):
            return None
        return str(role)

    @staticmethod
    def _content_len(message: Mapping[str, Any]) -> int:
        if message.get("role") == "tool":
            return 1
        content = message.get("content")
        if content is None or isinstance(content, str):
            return 1
        return len(content) if isinstance(content, list) else 0

    # ------------------------------------------------------------------------------------------ context
    def _wire_messages(self, call: _Call) -> list[Any] | None:
        request = self.blob_json(call.data.get("request"))
        messages = request.get("messages") if isinstance(request, dict) else None
        return messages if isinstance(messages, list) else None

    def _input_positions(self, entry: _Pass, call: _Call) -> list[int] | None:
        """Dump positions of the call's input: ``input_at`` (O) when recorded and valid, else the unique alignment of the
        decoded wire request with the dump prefix (D, ``cap.context_alignment@1``), else ``None``."""
        dump = entry.dump
        if dump is None:
            return None
        at = call.data.get("input_at")
        if isinstance(at, list):
            if all(_int(p) is not None and 0 <= p < len(dump) for p in at) and at == sorted(set(at)):
                call.input_class = "O"
                return [int(p) for p in at]
            call.input_class = "invalid"
            return None
        wire = None if self.messages_api else self._wire_messages(call)  # no Messages alignment rule (design §3.1)
        limit = _int(call.data.get("n_messages"))
        candidates = dump[:limit] if limit is not None and 0 <= limit <= len(dump) else dump
        call.input_class = "D"
        if wire is None:
            return None
        return _unique_alignment(candidates, wire, lambda n, w: self._sent(n, w)[0])

    def _sent(self, native: object, wire: object) -> tuple[bool, list[str]]:
        """Whether ``wire`` is a faithful rendering of the recorded ``native`` message, and the declared transforms
        (``agentdojo.capture_sent_form@1``)."""
        if not isinstance(native, dict) or not isinstance(wire, dict):
            return False, []
        role, wrole = native.get("role"), wire.get("role")
        transforms: list[str] = []
        if role == "system":
            if wrole not in ("system", "developer"):
                return False, []
            if wrole == "system" and getattr(self, "role_rewrite", False):
                transforms.append("role_rewrite")
        elif role != wrole:
            return False, []
        extra = set(wire) - _WIRE_KEYS
        if role == "assistant" and extra & _REASONING_KEYS:
            transforms.append("reasoning_passback")
            extra -= _REASONING_KEYS
        if extra:
            return False, []
        native_text, wire_text = _native_texts(native.get("content")), _wire_texts(wire.get("content"))
        if wire_text is _BAD:
            return False, []
        if role == "tool":
            call = _dict(native.get("tool_call"))
            if wire.get("tool_call_id") != native.get("tool_call_id") or ("name" in wire and wire["name"] != call.get("function")):
                return False, []
            error = native.get("error")
            if isinstance(error, str) and error and wire_text == [error]:
                if native_text != [error]:
                    transforms.append("error_substitution")
                return True, transforms
        if native_text != wire_text:
            return False, []
        if role == "assistant":
            ncalls = native.get("tool_calls") or []
            wcalls = wire.get("tool_calls") or []
            if not isinstance(wcalls, list) or len(ncalls) != len(wcalls):
                return False, []
            for nc, wc in zip(ncalls, wcalls, strict=True):
                function = _dict(_dict(wc).get("function"))
                if function.get("name") != nc.get("function"):
                    return False, []
                if nc.get("id") is not None and _dict(wc).get("id") != nc.get("id"):
                    return False, []
                arguments = function.get("arguments")
                try:  # untrusted wire text: the bounded strict loader (item 48), never stdlib json
                    decoded = self._json_text(arguments) if isinstance(arguments, str) else _BAD
                except (IngestError, UnicodeError):
                    decoded = _BAD
                if decoded is _BAD or _lexical(decoded) != _lexical(nc.get("args")):
                    return False, []
        return True, transforms

    # ------------------------------------------------------------------------------------------ outputs
    def _link_outputs(self, entry: _Pass, calls: list[_Call], shapes: list[str | None]) -> None:
        """``agentdojo.capture_reply_appended@1``: the reply of each kept or cached agent call."""
        dump = entry.dump or []
        assistants = [i for i, s in enumerate(shapes) if s == "assistant"]
        used: set[int] = set()
        cursor = 0
        for call in calls:
            if call.data.get("role") != "agent" or call.resp.get("status") not in ("kept", "cached"):
                continue
            if str(call.data.get("call")) in self.replaced_calls:
                continue  # D-670: a defence replaced this reply; it is a discarded message, not the dump's
            position = _int(call.data.get("n_messages"))
            if position is None:
                free = [i for i in assistants if i not in used and i >= cursor]
                position = free[0] if free else None
            ok = (position is not None and 0 <= position < len(dump) and shapes[position] == "assistant"
                  and position not in used and all(p < position for p in (call.inputs or []))
                  and self._reply_agrees(dump[position], call))
            if ok:
                assert position is not None
                call.output = position
                used.add(position)
                cursor = position + 1
            elif entry.dump is not None:
                self.issue("agentdojo.capture_reply_mismatch", [call.id], self.R("agentdojo.capture_reply_appended@1"))
        for (p, at), (_seq, payload) in sorted(self.defence_msgs.items()):
            # D-670: an assistant message a defence appended, with the auxiliary call its recorder bracketed
            named = self.calls.get(str(payload.get("call"))) if payload.get("call") is not None else None
            if p != entry.index or named is None or named.pass_ != entry.index or named.data.get("role") != "auxiliary" \
                    or named.resp.get("status") not in ("kept", "cached") or named.event.get("actor") != payload["actor"]:
                continue
            if 0 <= at < len(dump) and shapes[at] == "assistant" and at not in used and self._reply_agrees(dump[at], named):
                named.output = at
                used.add(at)
            else:
                self.issue("agentdojo.capture_reply_mismatch", [named.id], self.R("defence.message_by_defence@1"))

    def _reply_agrees(self, message: Mapping[str, Any], call: _Call) -> bool:
        """The dump message agrees with the decoded response (text and tool-call names), when the response decodes."""
        if self.messages_api:
            return self._messages_reply_agrees(message, call)
        response = self.blob_json(call.resp.get("response"))
        choices = response.get("choices") if isinstance(response, dict) else None
        choice = _dict(choices[0]).get("message") if isinstance(choices, list) and choices else None
        if not isinstance(choice, dict):
            return True  # nothing to contradict the position rule
        text = choice.get("content")
        texts = _native_texts(message.get("content"))
        if not ((text is None and texts is None) or (isinstance(text, str) and texts == [text])):
            return False
        wire_calls = choice.get("tool_calls") or []
        dropped: list[int] = []
        if isinstance(wire_calls, list) and not self.messages_api and self.fam.quirk(DROPPED_CALL_QUIRK) is not None:
            # D-685 (b): a harness that drops a call it cannot convert (AgentDyn) is compared on the calls it kept; a
            # Chat Completions reading only, never applied to a Messages-API reply (D-656 review)
            dropped = [c for c, wc in enumerate(wire_calls) if self._dropped_by_harness(wc)]
            wire_calls = [wc for c, wc in enumerate(wire_calls) if c not in dropped]
        names = [_dict(_dict(c).get("function")).get("name") for c in wire_calls] if isinstance(wire_calls, list) else None
        agrees = names == [c.get("function") for c in (message.get("tool_calls") or [])]
        call.dropped = dropped if agrees else []
        return agrees

    def _dropped_by_harness(self, wire_call: object) -> bool:
        """``agentdyn.malformed_tool_call_dropped@1``: AgentDyn's ``_openai_to_tool_call`` (``json.loads`` of the
        arguments, then ``FunctionCall`` validation) fails, and ``_openai_to_assistant_message`` drops the call, exactly
        when the call has no function or its arguments do not decode to a JSON object. Decoded with the bounded strict
        loader: a text it refuses but stdlib json accepts is counted as dropped, the names then disagree, and the reply is
        reported unmatched (fail closed)."""
        function = _dict(wire_call).get("function")
        if not isinstance(function, dict):
            return True
        arguments = function.get("arguments")
        if not isinstance(arguments, str):
            return True
        try:  # untrusted wire text: the bounded strict loader (item 48), never stdlib json
            decoded = self._json_text(arguments)
        except (IngestError, UnicodeError):
            return True
        return not isinstance(decoded, dict)

    # ------------------------------------------------------------------------------------------ tools
    def _link_tools(self, entry: _Pass, tools: list[_Tool], dump: list[Any], shapes: list[str | None],
                    content_parts: list[int], call_parts: Mapping[str, tuple[int, int]]) -> None:
        """``tool.dispatch.at`` (O), else the unique call part with the dispatch's ``provider_call_id`` (O, C.5.4)."""
        for tool in tools:
            at = _dict(tool.data.get("at"))
            i, j = _int(at.get("message")), _int(at.get("call"))
            if i is not None and j is not None and 0 <= i < len(dump) and shapes[i] == "assistant" \
                    and 0 <= j < len(dump[i].get("tool_calls") or []):
                tool.part, tool.part_pos = part_id(self._mid(entry, i), content_parts[i] + j), i
                tool.lexical_args = _dict(dump[i]["tool_calls"][j]).get("args")
                continue
            pid = tool.data.get("provider_call_id")
            matches = [(p, pos) for p, (pos, jj) in call_parts.items()
                       if isinstance(pid, str) and pid and dump[pos]["tool_calls"][jj].get("id") == pid]
            if len(matches) == 1:
                tool.part, tool.part_pos = matches[0]
                pos, jj = call_parts[tool.part]
                tool.lexical_args = _dict(dump[pos]["tool_calls"][jj]).get("args")
            elif entry.dump is not None:
                self.issue("call_result_link_conflict", [tool.id or self.dc_ids.get(tool.res_seq or -1, "run")],
                           self.R("agentdojo.capture_execution_result@1"))

    def _link_results(self, entry: _Pass, dump: list[Any], shapes: list[str | None],
                      content_parts: list[int]) -> dict[int, tuple[str | None, str, str]]:
        """``responds_to`` of every tool message: ``(part id or None, tag, rule)`` per dump position (D.6.6.1 rules)."""
        out: dict[int, tuple[str | None, str, str]] = {}
        i = 0
        while i < len(dump):
            if shapes[i] != "assistant":
                if shapes[i] == "tool":
                    out[i] = (None, "I", "agentdojo.positional_match@1")
                i += 1
                continue
            calls = dump[i].get("tool_calls") or []
            j = i + 1
            results: list[int] = []
            while j < len(dump) and shapes[j] == "tool":
                results.append(j)
                j += 1
            ids = [c.get("id") for c in calls]
            tcids = [dump[r].get("tool_call_id") for r in results]
            unique = bool(calls) and all(isinstance(x, str) and x for x in ids) and len(set(ids)) == len(ids)
            if unique and all(t in ids for t in tcids) and len(set(map(str, tcids))) == len(tcids):
                for r, t in zip(results, tcids, strict=True):
                    out[r] = (part_id(self._mid(entry, i), content_parts[i] + ids.index(t)), "D",
                              "agentdojo.call_id_unique_match@1")
            else:
                for p, r in enumerate(results):
                    echo = _dict(dump[r].get("tool_call"))
                    if p < len(calls) and echo.get("function") == calls[p].get("function") \
                            and _lexical(echo.get("args")) == _lexical(calls[p].get("args")):
                        out[r] = (part_id(self._mid(entry, i), content_parts[i] + p), "I", "agentdojo.positional_match@1")
                    else:
                        out[r] = (None, "I", "agentdojo.positional_match@1")
            i = j
        return out

    def _abort_message(self, entry: _Pass, calls: list[_Call], shapes: list[str | None]) -> int | None:
        """``agentdojo.capture_abort_message@1``: the position of the message ``AbortAgentError`` appends to an aborted
        pass (an assistant message with one text block and ``tool_calls: []``, generated by no call), else ``None``."""
        dump = entry.dump or []
        if entry.end is None or _dict(entry.end[1].get("data")).get("aborted") is not True or not dump:
            return None
        last = len(dump) - 1
        message = dump[last]
        if shapes[last] != "assistant" or message.get("tool_calls") != [] or single_text_block(message.get("content")) is None:
            return None
        return None if any(c.output == last for c in calls) else last

    def _unexecuted(self, entry: _Pass, dump: list[Any], shapes: list[str | None], content_parts: list[int],
                    call_parts: Mapping[str, tuple[int, int]], tools: list[_Tool], denied: set[str]) -> None:
        """Call parts with no dispatch: the last assistant message's are unexecuted (max_iters or an abort); others are
        missing results (as D.6.6 for native logs)."""
        handled = {t.part for t in tools if t.part is not None}
        assistants = [i for i, s in enumerate(shapes) if s == "assistant" and i != self._abort_pos]
        last = assistants[-1] if assistants else None
        pending_last = [p for p, (pos, _j) in call_parts.items() if p not in handled and p not in denied and pos == last]
        pending_other = [p for p, (pos, _j) in call_parts.items() if p not in handled and p not in denied and pos != last]
        if pending_last:
            self.issue("unexecuted_tool_call", pending_last, self.R("agentdojo.unexecuted_trailing_calls@1"))
        if pending_other:
            self.issue("missing_tool_result", pending_other, self.R("agentdojo.capture_execution_result@1"), severity="error")

    def _decision_slot(self, event: Mapping[str, Any], entry: _Pass, calls: list[_Call], n: int) -> int:
        subject = _dict(_dict(event.get("data")).get("subject"))
        if "occ" in subject:
            tool = self.tools.get(str(subject["occ"]))
            if tool is not None and tool.pass_ == entry.index:
                if tool.result_pos is not None:
                    return tool.result_pos
                return (tool.part_pos + 1) if tool.part_pos is not None else n
        if "at" in subject:
            at = _dict(subject["at"])
            i = _int(at.get("message"))
            return (i + 1) if i is not None and 0 <= i < n else n
        if isinstance(subject.get("call"), str):
            # D-670: a decision that replaced a call's reply sits in the slot of the message it put in its place, after
            # the call (same slot, earlier seq) and before that message, which names it as its generator
            for (p, position), (_seq, payload) in self.defence_msgs.items():
                if p == entry.index and payload.get("replaces") == subject["call"] and 0 <= position < n:
                    return position
        return n

    # ------------------------------------------------------------------------------------------ records
    def _model_call(self, entry: _Pass | None, call: _Call, scope: str, shapes: Sequence[str | None]) -> None:
        d, resp = call.data, call.resp
        actor = str(call.event["actor"])
        mc = _Rec(k="model_call", id=call.id, actor=actor, role=d["role"], scope=scope, ev="O", by="capture",
                  src=[self.L(call.seq, "/data")])
        rules: list[str] = []
        if call.resp_event is not None:
            mc.add("src", self.L(call.resp_seq or 0, "/data"))
        mc.data.update(self._inputs(entry, call, mc, rules))
        params = _dict(d.get("params"))
        if params:
            mc.data["params"] = {k: mc.enc(params[k], f"/params/{k}") for k in ("configured", "transmitted") if k in params}
            if not mc.data["params"]:
                del mc.data["params"]
        status = resp.get("status")
        replaced = self.replaced_calls.get(str(d.get("call")))
        if replaced is not None and status in ("kept", "cached") and call.resp_event is not None:
            # D-670: a defence's modify decision replaced the reply in the message list, so it never answered
            status = "discarded"
            mc.data["status"] = status
            mc.data["reason"] = "replaced_by_defence"
            mc.tag("/status", "D")
            mc.tag("/reason", "D")
            mc.add("src", self.L(replaced, "/data"))
            rules += [self.R("defence.reply_replaced@1", "/status"), self.R("defence.reply_replaced@1", "/reason")]
        elif call.resp_event is None:
            mc.unk("/status", "not_captured")
            mc.unk("/response", "not_captured")
        elif status in MODEL_CALL_STATUS:
            mc.data["status"] = status
        else:
            mc.unk("/status", "ambiguous")
            rules.append(self.R("agentdojo.capture_status@1", "/status"))
        if _typed(resp.get("reason")) and "reason" not in mc.data:
            mc.data["reason"] = mc.enc(resp["reason"], "/reason")
        retry = self.calls.get(str(d.get("retry_of"))) if d.get("retry_of") is not None else None
        if retry is not None and retry.id in self._emitted:
            mc.data["retry_of"] = retry.id
        elif d.get("retry_of") is not None:
            self._malformed(call.seq, "llm.request retry_of")
        for key in ("finish_reason", "served_model", "response_id"):
            if _typed(resp.get(key)):
                mc.data[key] = mc.enc(resp[key], f"/{key}")
                mc.tag(f"/{key}", "O:provider")
        usage = _dict(resp.get("usage"))
        kept = {k: v for k, v in usage.items() if k in _USAGE_KEYS and _int(v) is not None and v >= 0}
        if kept:
            mc.data["usage"] = dict(kept)
            mc.tag("/usage", "O:provider")
        for key, ref, seq in (("request", d.get("request"), call.seq), ("response", resp.get("response"), call.resp_seq)):
            if _blob_hex(ref) is not None:
                if self._is_redacted(seq, f"/{key}"):
                    mc.unk(f"/{key}", "withheld")
                    self._redacted_record(seq, call.id)
                else:
                    mc.data[key] = dict(ref)  # type: ignore[arg-type]
        if self._is_redacted(call.seq, "/params") and "params" in mc.data:
            del mc.data["params"]
            mc.unk("/params", "withheld")
            self._redacted_record(call.seq, call.id)
        t = _time(call.event, call.resp_event)
        if t:
            mc.data["t"] = t
        if rules:
            mc.data["rule"] = rules
        self._emit(mc)
        if self.messages_api and call.resp_event is not None:
            self._stream_issues(call)
        if status == "discarded" and call.resp_event is not None:
            self._discarded_message(call, scope)

    def _inputs(self, entry: _Pass | None, call: _Call, mc: _Rec, rules: list[str]) -> dict[str, Any]:
        """The ``input`` member (or its unknown), with the sent transforms of each item."""
        detached = self.detached_calls.get(str(call.data.get("call")))
        if detached is not None:
            # D-670: a defence's call built from its own conversation (MELON's masked re-run): no message of the pass
            mc.tag("/input", "D")
            mc.add("src", self.L(detached, "/data/payload"))
            rules.append(self.R("defence.detached_input@1", "/input"))
            return {"input": []}
        cls = call.input_class
        if entry is None or entry.dump is None:
            mc.unk("/input", "not_recorded" if entry is None else "not_captured")
            return {}
        if call.inputs is None:
            mc.unk("/input", "ambiguous")
            if cls == "invalid":
                rules.append(self.R("agentdojo.capture_sent_form@1", "/input"))
                self.issue("agentdojo.capture_sent_form_unexplained", [call.id], self.R("agentdojo.capture_sent_form@1"),
                           detail="input_at does not name positions of the pass dump")
            else:
                rules.append(self.R("cap.context_alignment@1", "/input"))
            return {}
        if cls == "D":
            mc.tag("/input", "D")
            rules.append(self.R("cap.context_alignment@1", "/input"))
            mc.add("src", self.B(entry.dump_hex or "", ""))
        else:
            mc.add("src", self.L(call.seq, "/data/input_at"))
        if self.messages_api:
            return {"input": self._messages_inputs(entry, call, mc, rules)}
        wire = self._wire_messages(call)
        withheld = self._is_redacted(call.seq, "/request")
        items: list[Any] = []
        if wire is not None and len(wire) != len(call.inputs):
            self.issue("agentdojo.capture_sent_form_unexplained", [call.id], self.R("agentdojo.capture_sent_form@1"),
                       detail=f"request holds {len(wire)} messages for {len(call.inputs)} input positions")
            wire = None
        for i, pos in enumerate(call.inputs):
            mid = self._mid(entry, pos)
            if wire is None:
                items.append(mid)
                continue
            faithful, transforms = self._sent(entry.dump[pos], wire[i])
            later = None if faithful else self._decided_after(entry, pos, call.seq)
            if later is not None:
                # D-670: a defence redacted or modified this tool message after the call was sent (MELON decides after
                # the agent's step): the call saw the content before the decision, which the decision kept
                was = {**entry.dump[pos], "content": self.blob_json(later[1])}
                faithful, _ = self._sent(was, wire[i])
                if faithful:
                    before: dict[str, Any] = {"id": mid, "sent": ["other"]}
                    mc.tag(f"/input/{i}/sent", "D")
                    mc.add("src", self.L(later[0], "/data/original"))
                    rules.append(self.R("defence.sent_before_decision@1", f"/input/{i}/sent"))
                    if not withheld:
                        before["sent_sha256"] = _jcs_sha256(wire[i])
                        mc.tag(f"/input/{i}/sent_sha256", "D")
                        rules.append(self.R("defence.sent_before_decision@1", f"/input/{i}/sent_sha256"))
                    items.append(before)
                    continue
            if not faithful:
                self.issue("agentdojo.capture_sent_form_unexplained", [call.id], self.R("agentdojo.capture_sent_form@1"),
                           detail=f"input {i}")
                items.append(mid)
            elif transforms:
                item: dict[str, Any] = {"id": mid, "sent": transforms}
                mc.tag(f"/input/{i}/sent", "D")
                rules.append(self.R("agentdojo.capture_sent_form@1", f"/input/{i}/sent"))
                digest = None if withheld else _jcs_sha256(wire[i])
                if digest is not None:
                    item["sent_sha256"] = digest
                    mc.tag(f"/input/{i}/sent_sha256", "D")
                    rules.append(self.R("agentdojo.capture_sent_form@1", f"/input/{i}/sent_sha256"))
                items.append(item)
            else:
                items.append(mid)
        if wire is not None:
            mc.add("src", self.L(call.seq, "/data/request"))
        return {"input": items}

    def _messages_inputs(self, entry: _Pass, call: _Call, mc: _Rec, rules: list[str]) -> list[Any]:
        """``input`` of a Messages call: each item's sent form under ``anthropic_messages.sent_form@1`` (module
        docstring of ``messages_wire``); an unexplained difference is reported and no transform is claimed."""
        assert entry.dump is not None and call.inputs is not None
        natives = [entry.dump[pos] for pos in call.inputs]
        matches = mw.match_inputs(natives, self.blob_json(call.data.get("request")))
        withheld = self._is_redacted(call.seq, "/request")
        items: list[Any] = []
        if matches is None:
            self.issue("agentdojo.capture_sent_form_unexplained", [call.id], self.R(_MSG_SENT),
                       detail="the request does not carry the input messages in the stock Messages rendering")
            return [self._mid(entry, pos) for pos in call.inputs]
        for i, (pos, (faithful, transforms, unit)) in enumerate(zip(call.inputs, matches, strict=True)):
            mid = self._mid(entry, pos)
            if not faithful:
                self.issue("agentdojo.capture_sent_form_unexplained", [call.id], self.R(_MSG_SENT), detail=f"input {i}")
                items.append(mid)
            elif transforms:
                item: dict[str, Any] = {"id": mid, "sent": transforms}
                mc.tag(f"/input/{i}/sent", "D")
                rules.append(self.R(_MSG_SENT, f"/input/{i}/sent"))
                digest = None if withheld else _jcs_sha256(unit)
                if digest is not None:
                    item["sent_sha256"] = digest
                    mc.tag(f"/input/{i}/sent_sha256", "D")
                    rules.append(self.R(_MSG_SENT, f"/input/{i}/sent_sha256"))
                items.append(item)
            else:
                items.append(mid)
        mc.add("src", self.L(call.seq, "/data/request"))
        return items

    def _stream_issues(self, call: _Call) -> None:
        """``anthropic_messages.stream_read@1``: a streamed reply that departs from the SDK's accumulation is
        ``stream_inconsistent`` (nothing is claimed from it); one without ``message_stop``, or that ends inside an event
        or a line, is ``stream_incomplete`` (what the element took is what the stream held, disclosed)."""
        reply = self.messages_reply(call)
        if reply is None or not reply.streamed or reply.error is not None:
            return
        if reply.inconsistent is not None:
            self.issue("anthropic_messages.stream_inconsistent", [call.id], self.R(_MSG_STREAM), detail=reply.inconsistent)
        elif not reply.complete or reply.torn:
            self.issue("anthropic_messages.stream_incomplete", [call.id], self.R(_MSG_STREAM),
                       detail="no message_stop" if not reply.complete else "torn after message_stop")

    def _messages_reply_agrees(self, message: Mapping[str, Any], call: _Call) -> bool:
        """``capture_reply_appended@1`` on the Messages wire: the dump message is the stock element's reading of the
        reply (``_anthropic_to_assistant_message``): its content blocks are the reply's non-tool blocks, and its tool
        calls are the reply's ``tool_use`` blocks with a valid name when ``stop_reason`` is ``tool_use``, else none."""
        reply = self.messages_reply(call)
        if reply is None or reply.error is not None or reply.inconsistent is not None:
            return True  # nothing to contradict the position rule (an inconsistent stream is reported, not read)
        raw = message.get("content")
        content: list[Any] = raw if isinstance(raw, list) else []
        native: list[tuple[str, Any]] = []
        for block in content:
            kind = block.get("type") if isinstance(block, dict) else None
            if kind == "text":
                native.append(("text", block.get("content")))
            elif kind == "thinking" and block.get("id") is not None:
                native.append(("thinking", (block.get("content"), block.get("id"))))
            elif kind in ("thinking", "redacted_thinking"):  # the stock element's RedactedThinkingContentBlock
                native.append(("redacted_thinking", block.get("content")))
            else:
                native.append((str(kind), block))
        if native != mw.reply_texts(reply):
            return False
        wire_names = [b.get("name") for b, _p in reply.blocks if b.get("type") == "tool_use"
                      and isinstance(b.get("name"), str) and mw.VALID_TOOL_NAME.match(b["name"])] \
            if reply.stop_reason == "tool_use" else []
        return wire_names == [c.get("function") for c in (message.get("tool_calls") or [])]

    def _thinking_omitted(self, call: _Call, rec: _Rec, parts: list[dict[str, Any]], rules: list[str]) -> None:
        """``anthropic_messages.thinking_omitted@1``: a reasoning part whose block the provider returned as a thinking
        block with empty text and a signature (display ``omitted``) does not show the reasoning, it withholds it: its
        text is omitted and declared ``withheld`` (aer/0.2, D-211), ``src`` into the response blob. The dump's empty
        text is listed in ``ext.agentdojo.thinking_omitted`` so the live-versus-native projection compares it."""
        reply = self.messages_reply(call)
        hexdigest = _blob_hex(call.resp.get("response"))
        if reply is None or hexdigest is None or reply.inconsistent is not None:
            return
        wire = [(b, p) for b, p in reply.blocks if b.get("type") != "tool_use"]
        omitted: list[int] = []
        for k, part in enumerate(parts):
            if k >= len(wire) or part.get("t") != "reasoning" or part.get("text") != "":
                continue
            block, pointer = wire[k]
            signature = block.get("signature")
            if block.get("type") == "thinking" and block.get("thinking") == "" and isinstance(signature, str) and signature:
                del part["text"]
                rec.unk(f"/parts/{k}/text", "withheld")
                rules.append(self.R(_MSG_THINKING, f"/parts/{k}/text"))
                rec.add("src", self.BP(hexdigest, pointer))
                omitted.append(k)
        if omitted:
            rec.ext()["thinking_omitted"] = omitted

    def _decided_after(self, entry: _Pass, pos: int, after_seq: int) -> tuple[int, Mapping[str, Any]] | None:
        """``(seq, original blob)`` of a ``redact``/``modify`` decision on the tool message at dump position ``pos``,
        recorded after event ``after_seq`` and keeping the content before it (D-670)."""
        for seq, event in self.decisions:
            data = _dict(event.get("data"))
            tool = self.tools.get(str(_dict(data.get("subject")).get("occ")))
            if seq > after_seq and _int(event.get("pass")) == entry.index and tool is not None \
                    and tool.result_pos == pos and data.get("verdict") in ("redact", "modify") \
                    and _blob_hex(data.get("original")) is not None:
                return seq, data["original"]
        return None

    def _discarded_message(self, call: _Call, scope: str) -> None:
        """C.13.7: a discarded reply is a message ``generated_by`` its call (decoded from the response blob)."""
        if self.messages_api:
            self._messages_discarded(call, scope)
            return
        ref = call.resp.get("response")
        hexdigest = _blob_hex(ref)
        response = self.blob_json(ref)
        choices = response.get("choices") if isinstance(response, dict) else None
        message = _dict(choices[0]).get("message") if isinstance(choices, list) and choices else None
        if hexdigest is None or not isinstance(message, dict):
            self.issue("capture_error", [call.id], self.R("agentdojo.capture_discarded_reply@1"),
                       detail="discarded reply without a decodable response")
            return
        mid = f"m{self.n_dump + self.n_discarded}"
        self.n_discarded += 1
        # No `actor`: the reply's author follows from `generated_by` (the call's actor). A rejected reply is no answer of
        # the agent, and C.12.2 pairs answering calls with the llm_agent-authored assistant messages (D.10.4a).
        rec = _Rec(k="message", id=mid, scope=scope, role="assistant", generated_by=call.id,
                   after=[{"b": "causal", "id": call.id}], ev="O", by="capture",
                   src=[self.B(hexdigest, "/choices/0/message")])
        parts: list[dict[str, Any]] = []
        rules = [self.R("aer.output_after_generator@1", "/after"), self.R("agentdojo.capture_discarded_reply@1")]
        content = message.get("content")
        if content is None or isinstance(content, str):
            parts.append({"t": "text", "text": rec.enc(content, "/parts/0/text")})
        else:  # wire content parts (item 47): text blocks are text, anything else is kept as `other`, never dropped
            for block in content if isinstance(content, list) else [content]:
                k = len(parts)
                if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str):
                    parts.append({"t": "text", "text": rec.enc(block["text"], f"/parts/{k}/text")})
                else:
                    parts.append({"t": "other", "type": "agentdojo.unknown_block", "value": rec.enc(block, f"/parts/{k}/value")})
            if any(part["t"] == "other" for part in parts):
                self.issue("agentdojo.unknown_message_shape", [mid], self.R("agentdojo.capture_discarded_reply@1"))
        for k, made in enumerate(parts):  # as _assistant_message: an empty text is ambiguous (aer.sentinel; review R3-1)
            if made["t"] == "text" and made.get("text") == "":
                rec.unk(f"/parts/{k}/text", "ambiguous")
                rules.append(self.R("agentdojo.empty_assistant_text_ambiguous@1", f"/parts/{k}/text"))
        for wc in message.get("tool_calls") or []:
            k = len(parts)
            function = _dict(_dict(wc).get("function"))
            name = function.get("name")
            arguments = function.get("arguments")
            try:  # untrusted wire text: the bounded strict loader (item 48), never stdlib json
                args = self._json_text(arguments) if isinstance(arguments, str) else None
                ambiguous = not isinstance(arguments, str)
            except (IngestError, UnicodeError):
                args, ambiguous = arguments, True
            part: dict[str, Any] = {"t": "tool_call", "name": rec.enc(name if isinstance(name, str) else "", f"/parts/{k}/name"),
                                    "args": rec.enc(args, f"/parts/{k}/args")}
            if isinstance(arguments, str):
                part["args_raw"] = rec.enc(arguments, f"/parts/{k}/args_raw")
            if isinstance(_dict(wc).get("id"), str):
                part["provider_call_id"] = rec.enc(wc["id"], f"/parts/{k}/provider_call_id")
            if ambiguous:
                rec.unk(f"/parts/{k}/args", "ambiguous")
                rules.append(self.R("agentdojo.capture_discarded_reply@1", f"/parts/{k}/args"))
            parts.append(part)
        rec.data["parts"] = parts
        hits = self._blob_redactions(call.resp_seq, hexdigest)
        if hits:  # D-211: a redacted reply text or argument is withheld (D.10.4a item 23)
            members = self._content_members(parts, content, "/choices/0/message/content")
            calls_k = [k for k, part in enumerate(parts) if part["t"] == "tool_call"]
            members += [(k, "args", f"/choices/0/message/tool_calls/{c}/function/arguments") for c, k in enumerate(calls_k)]
            self._withhold_parts(rec, call.resp_seq, hits, members)
        rec.tag("/after", "D")
        rec.data["rule"] = rules
        self._emit(rec)
        calls = [part_id(mid, k) for k, part in enumerate(parts) if part["t"] == "tool_call"]
        if calls:  # a rejected reply's calls were never dispatched (C.12.2 tool_calls_dispatched: listed, not executed)
            self.issue("unexecuted_tool_call", calls, self.R("agentdojo.capture_discarded_reply@1"))

    def _messages_discarded(self, call: _Call, scope: str) -> None:
        """``anthropic_messages.discarded_reply@1``: a discarded Messages reply is a message ``generated_by`` its call,
        decoded from the response blob (JSON or the rebuilt stream): text -> text, thinking -> reasoning (with its
        signature; empty text with a signature is withheld as in ``thinking_omitted``), redacted thinking -> reasoning
        ``redacted``, tool_use -> tool_call (``args`` = ``input``; a streamed call keeps its ``partial_json`` as
        ``args_raw``, and ``args`` is ambiguous when that text is not JSON), any other block -> other."""
        reply = self.messages_reply(call)
        hexdigest = _blob_hex(call.resp.get("response"))
        if hexdigest is None or reply is None or reply.error is not None or reply.inconsistent is not None:
            self.issue("capture_error", [call.id], self.R(_MSG_DISCARDED),
                       detail="discarded reply without a decodable, consistent response")
            return
        mid = f"m{self.n_dump + self.n_discarded}"
        self.n_discarded += 1
        rec = _Rec(k="message", id=mid, scope=scope, role="assistant", generated_by=call.id,
                   after=[{"b": "causal", "id": call.id}], ev="O", by="capture",
                   src=[self.BP(hexdigest, None if reply.streamed else "")])
        rules = [self.R("aer.output_after_generator@1", "/after"), self.R(_MSG_DISCARDED)]
        parts: list[dict[str, Any]] = []
        unknown = False
        for block, pointer in reply.blocks:
            k = len(parts)
            kind = block.get("type")
            if kind == "text" and isinstance(block.get("text"), str):
                parts.append({"t": "text", "text": rec.enc(block["text"], f"/parts/{k}/text")})
                if block["text"] == "":  # as _assistant_message: an empty text is ambiguous (aer.sentinel)
                    rec.unk(f"/parts/{k}/text", "ambiguous")
                    rules.append(self.R("agentdojo.empty_assistant_text_ambiguous@1", f"/parts/{k}/text"))
            elif kind == "thinking" and isinstance(block.get("thinking"), str):
                part: dict[str, Any] = {"t": "reasoning"}
                signature = block.get("signature")
                if isinstance(signature, str) and signature:
                    part["signature"] = rec.enc(signature, f"/parts/{k}/signature")
                if block["thinking"] == "" and isinstance(signature, str) and signature:
                    rec.unk(f"/parts/{k}/text", "withheld")
                    rules.append(self.R(_MSG_THINKING, f"/parts/{k}/text"))
                else:
                    part["text"] = rec.enc(block["thinking"], f"/parts/{k}/text")
                parts.append(part)
            elif kind == "redacted_thinking":
                parts.append({"t": "reasoning", "text": None, "redacted": True})
            elif kind == "tool_use" and isinstance(block.get("name"), str):
                args = block.get("input")
                tool: dict[str, Any] = {"t": "tool_call", "name": rec.enc(block["name"], f"/parts/{k}/name")}
                if args is mw.BAD:
                    tool["args"] = rec.enc(block.get("input_json"), f"/parts/{k}/args")
                    rec.unk(f"/parts/{k}/args", "ambiguous")
                    rules.append(self.R(_MSG_DISCARDED, f"/parts/{k}/args"))
                else:
                    tool["args"] = rec.enc(args, f"/parts/{k}/args")
                if isinstance(block.get("input_json"), str):
                    tool["args_raw"] = rec.enc(block["input_json"], f"/parts/{k}/args_raw")
                if isinstance(block.get("id"), str):
                    tool["provider_call_id"] = rec.enc(block["id"], f"/parts/{k}/provider_call_id")
                parts.append(tool)
            else:
                unknown = True
                parts.append({"t": "other", "type": "agentdojo.unknown_block", "value": rec.enc(block, f"/parts/{k}/value")})
            if pointer is not None:
                rec.add("src", self.B(hexdigest, pointer))
        if not parts:
            parts.append({"t": "text", "text": None})
        if unknown:
            self.issue("agentdojo.unknown_message_shape", [mid], self.R(_MSG_DISCARDED))
        rec.data["parts"] = parts
        hits = self._blob_redactions(call.resp_seq, hexdigest)
        if hits:  # D-211: a redacted text, argument or value of the reply is withheld (an event stream: the whole blob)
            members: list[tuple[int, str, str]] = []
            for k, (block, pointer) in enumerate(reply.blocks):
                base = pointer if pointer is not None else ""
                member = {"text": "text", "thinking": "text", "tool_use": "args"}.get(str(block.get("type")), "value")
                sub = {"text": "/text", "thinking": "/thinking", "tool_use": "/input"}.get(str(block.get("type")), "")
                members.append((k, member, base + sub if pointer is not None else base))
            self._withhold_parts(rec, call.resp_seq, hits, members)
        if not reply.complete or reply.torn:
            self.issue("anthropic_messages.stream_incomplete", [mid], self.R(_MSG_STREAM),
                       detail="discarded reply from a stream without message_stop" if not reply.complete
                       else "discarded reply from a torn stream")
        rec.tag("/after", "D")
        rec.data["rule"] = rules
        self._emit(rec)
        calls = [part_id(mid, k) for k, part in enumerate(parts) if part["t"] == "tool_call"]
        if calls:  # a rejected reply's calls were never dispatched (C.12.2 tool_calls_dispatched: listed, not executed)
            self.issue("unexecuted_tool_call", calls, self.R(_MSG_DISCARDED))

    def _message(self, entry: _Pass, i: int, scope: str, shapes: Sequence[str | None], content_parts: Sequence[int],
                 responds: Mapping[int, tuple[str | None, str, str]], generators: Mapping[int, tuple[str, str]],
                 prev: str | None) -> str:
        dump = entry.dump or []
        message, shape = dump[i], shapes[i]
        mid = self._mid(entry, i)
        rec = _Rec(k="message", id=mid, scope=scope, ev="O", by="capture", src=[self.B(entry.dump_hex or "", f"/{i}")])
        rules: list[str] = []
        if shape is None:
            role = message.get("role") if isinstance(message, dict) else None
            rec.data["role"] = rec.enc(role, "/role") if isinstance(role, str) and role else "agentdojo.unknown"
            rec.data["parts"] = [{"t": "other", "type": "agentdojo.unknown_message", "value": rec.enc(message, "/parts/0/value")}]
            rec.unk("/actor", "not_recorded")
            self.issue("agentdojo.unknown_message_shape", [mid], self.R("agentdojo.tracelogger_record_shape@1"))
        else:
            rec.data["role"] = shape
            if shape == "assistant":
                self._assistant_message(entry, i, rec, rules)
            elif shape == "tool":
                self._tool_message(i, rec, rules, responds, generators)
            else:
                rec.data["parts"] = self._content(rec, message.get("content"))
                if not self._defence_author(entry, i, rec, rules):
                    self._author(i, shape, rec, rules)
        hits = self._blob_redactions(entry.end[0] if entry.end is not None else None, entry.dump_hex)
        if hits:  # D-211: a redacted text, argument or value of this message is withheld (D.10.4a item 23)
            parts = rec.data.get("parts") or []
            if shape is None:
                members = [(0, "value", f"/{i}")]
            elif shape == "tool":
                # RC-1: a tool_result part keeps text xor value under aer/0.2 too (D-211 and design section 1.2 relax
                # only text, reasoning and refusal text, tool_call args and other value), so a redacted tool output keeps
                # its redacted value; capture_redaction names `exec`, as no record is withheld (D.10.4a item 23, RC-19)
                members = []
            else:
                members = self._content_members(parts, message.get("content"), f"/{i}/content")
                n = len(members) if isinstance(message.get("content"), list) else min(1, len(parts))
                calls = [k for k, part in enumerate(parts) if part.get("t") == "tool_call" and k >= n]
                members += [(k, "args", f"/{i}/tool_calls/{c}/args") for c, k in enumerate(calls)]
            self._withhold_parts(rec, entry.end[0] if entry.end is not None else None, hits, members)
        if "after" not in rec.data and prev is not None:
            rec.data["after"] = [{"b": "pos", "id": prev}]
            rec.tag("/after", "D")
            rules.append(self.R("agentdojo.messages_append_ordered@1", "/after"))
        if rules:
            rec.data["rule"] = rules
        self._emit(rec)
        return mid

    def _defence_author(self, entry: _Pass, i: int, rec: _Rec, rules: list[str]) -> bool:
        """D-670: a message the defence's recorder saw its element append is the defence's (``defence_message`` note;
        the role stays verbatim: role is not authorship, C.3.4). The recorder observed the element append it; the
        actor follows from that note by ``defence.message_by_defence@1`` (D), cited through the note."""
        noted = self.defence_msgs.get((entry.index, i))
        if noted is None or noted[1]["actor"] not in self.actor_kind:
            return False
        seq, payload = noted
        rec.data["actor"] = str(payload["actor"])
        rec.tag("/actor", "D")
        rec.data.setdefault("src", []).append(self.L(seq, "/data/payload"))
        rules.append(self.R("defence.message_by_defence@1", "/actor"))
        if rec.data.get("role") == "user" and not self._first_user_seen:
            self._first_user_seen = True  # cannot happen in the stock defences; keeps the first-user rule's meaning
        return True

    def _author(self, i: int, role: str, rec: _Rec, rules: list[str]) -> None:
        if role == "system":
            if i == 0:
                rec.data["actor"] = self.bench
                rec.tag("/actor", "D")
                rules.append(self.R("agentdojo.system_prompt_from_harness@1", "/actor"))
            else:
                rec.unk("/actor", "not_recorded")
        elif not self._first_user_seen:
            self._first_user_seen = True
            rec.data["actor"] = self.user
            rec.tag("/actor", "D")
            rules.append(self.R("agentdojo.user_is_simulated@1", "/actor"))
        else:
            rec.data["actor"] = self.user
            rec.tag("/actor", "I")
            rules.append(self.R("agentdojo.additional_user_message_unattributed@1", "/actor"))
            self.issue("unattributed_additional_user_message", [str(rec.data["id"])],
                       self.R("agentdojo.additional_user_message_unattributed@1"))

    def _content(self, rec: _Rec, content: object, base: int = 0) -> list[dict[str, Any]]:
        """R-CONTENT (D.6.3), by the TraceLogger mapper's own rule (``content_block_parts``), so the two mappers read
        content blocks identically by construction (regeneration-batch item 47, core review D's CD-13)."""
        parts, null_text_blocks, unknown = content_block_parts(content, base, rec.enc)
        if null_text_blocks:
            rec.ext()["null_text_blocks"] = null_text_blocks
        for _ in range(unknown):
            self.issue("agentdojo.unknown_message_shape", [str(rec.data["id"])], self.R("agentdojo.tracelogger_record_shape@1"))
        return parts

    def _assistant_message(self, entry: _Pass, i: int, rec: _Rec, rules: list[str]) -> None:
        message = (entry.dump or [])[i]
        parts = self._content(rec, message.get("content"))
        for k, part in enumerate(parts):
            if part.get("t") == "text" and part.get("text") == "":
                rec.unk(f"/parts/{k}/text", "ambiguous")
                rules.append(self.R("agentdojo.empty_assistant_text_ambiguous@1", f"/parts/{k}/text"))
        calls_raw = message.get("tool_calls")
        placeholders: dict[str, Any] = {}
        for call in calls_raw or ():
            k = len(parts)
            cpart: dict[str, Any] = {"t": "tool_call", "name": rec.enc(call["function"], f"/parts/{k}/name"),
                                     "args": rec.enc(call["args"], f"/parts/{k}/args")}
            if "id" in call:
                cpart["provider_call_id"] = rec.enc(call["id"], f"/parts/{k}/provider_call_id")
                if call["id"] == "":
                    rec.unk(f"/parts/{k}/provider_call_id", "ambiguous")
            else:
                rec.unk(f"/parts/{k}/provider_call_id", "not_recorded")
            rec.unk(f"/parts/{k}/args_raw", "not_recorded")
            if "placeholder_args" in call:
                placeholders[str(k)] = rec.enc(call["placeholder_args"], json_pointer("ext", "agentdojo", "placeholder_args", str(k)))
            parts.append(cpart)
        if placeholders:
            rec.ext()["placeholder_args"] = placeholders
        if calls_raw is None and "tool_calls" not in message:
            rec.ext()["calls_form"] = "absent"
        elif calls_raw == []:
            rec.ext()["calls_form"] = "empty_list"
        if calls_raw:
            rules.append(self.R("agentdojo.args_are_effective@1"))  # dump args are post-normalisation (0.1.35, D.6.6)
        rec.data["parts"] = parts
        generator = next((c for c in self.call_order if c.pass_ == entry.index and c.output == i), None)
        if i == self._abort_pos:  # AbortAgentError's message: not a model reply, its raiser is not recorded
            rec.unk("/actor", "not_recorded")
            rec.unk("/generated_by", "not_recorded")
            rules.append(self.R("agentdojo.capture_abort_message@1"))
        elif generator is not None:
            rec.data.update(actor=str(generator.event["actor"]), generated_by=generator.id,
                            after=[{"b": "causal", "id": generator.id}])
            rec.tag("/generated_by", "D")
            rec.tag("/after", "D")
            rec.tag("/actor", "D")
            reply_rule = "defence.message_by_defence@1" if generator.data.get("role") == "auxiliary" \
                else "agentdojo.capture_reply_appended@1"
            if generator.data.get("role") == "auxiliary":
                seq, _payload = self.defence_msgs[(entry.index, i)]
                rec.data.setdefault("src", []).append(self.L(seq, "/data/payload"))
            rules += [self.R(reply_rule, "/generated_by"),
                      self.R(reply_rule, "/actor"),
                      self.R("aer.output_after_generator@1", "/after")]
            if self.messages_api:
                self._thinking_omitted(generator, rec, parts, rules)
            else:
                self._wire_reply_fields(generator, rec, parts, rules)
            if generator.dropped:
                self._dropped_calls(generator, rec, rules)
        elif self._replacement(entry, i, rec, rules):
            pass
        else:
            if self.agent is not None:
                rec.data["actor"] = self.agent
                rec.tag("/actor", "D")
                rules.append(self.R("agentdojo.capture_reply_appended@1", "/actor"))
            rec.unk("/generated_by", "not_captured")
            self.issue("missing_generated_by", [str(rec.data["id"])], self.R("agentdojo.capture_reply_appended@1"))

    def _dropped_calls(self, call: _Call, rec: _Rec, rules: list[str]) -> None:
        """D-685 (b), ``agentdyn.malformed_tool_call_dropped@1``: the wire tool calls of the kept reply that the harness
        dropped are listed in ``ext.agentdojo.dropped_calls`` (``index`` into the reply's ``tool_calls``, ``name``,
        ``args_raw`` and ``provider_call_id`` as sent), class D, ``src`` into the response blob. They are no part of the
        message and were never dispatched, so no tool execution and no provenance relation comes from them."""
        ref = call.resp.get("response")
        hexdigest = _blob_hex(ref)
        response = self.blob_json(ref)
        choices = response.get("choices") if isinstance(response, dict) else None
        message = _dict(choices[0]).get("message") if isinstance(choices, list) and choices else None
        wire_calls = _dict(message).get("tool_calls")
        if hexdigest is None or not isinstance(wire_calls, list):
            return
        listed: list[dict[str, Any]] = []
        for n, c in enumerate(call.dropped):
            wc = _dict(wire_calls[c]) if 0 <= c < len(wire_calls) else {}
            function = _dict(wc.get("function"))
            base = json_pointer("ext", "agentdojo", "dropped_calls", str(n))
            entry: dict[str, Any] = {"index": c}
            if isinstance(function.get("name"), str):
                entry["name"] = rec.enc(function["name"], base + "/name")
            if "arguments" in function:
                entry["args_raw"] = rec.enc(function["arguments"], base + "/args_raw")
            if isinstance(wc.get("id"), str):
                entry["provider_call_id"] = rec.enc(wc["id"], base + "/provider_call_id")
            listed.append(entry)
            rec.add("src", self.B(hexdigest, f"/choices/0/message/tool_calls/{c}"))
        rec.ext()["dropped_calls"] = listed
        rec.tag("/ext/agentdojo/dropped_calls", "D")
        rules.append(self.R(DROPPED_CALL_RULE, "/ext/agentdojo/dropped_calls"))

    def _replacement(self, entry: _Pass, i: int, rec: _Rec, rules: list[str]) -> bool:
        """D-670: the assistant message a defence put in place of an agent call's reply (a ``defence_message`` note that
        names the replaced call, and that call's ``modify`` decision) is generated by the decision and the defence's."""
        noted = self.defence_msgs.get((entry.index, i))
        if noted is None or not isinstance(noted[1].get("replaces"), str):
            return False
        seq, payload = noted
        decision = self.replaced_calls.get(str(payload["replaces"]))
        dc = self.dc_ids.get(decision) if decision is not None else None
        if dc is None or payload["actor"] not in self.actor_kind:
            return False
        rec.data.update(actor=str(payload["actor"]), generated_by=dc, after=[{"b": "causal", "id": dc}])
        for pointer in ("/actor", "/generated_by", "/after"):
            rec.tag(pointer, "D")
        rec.data.setdefault("src", []).append(self.L(seq, "/data/payload"))
        rules += [self.R("defence.reply_replaced@1", "/generated_by"), self.R("defence.message_by_defence@1", "/actor"),
                  self.R("aer.output_after_generator@1", "/after")]
        return True

    def _wire_reply_fields(self, call: _Call, rec: _Rec, parts: list[dict[str, Any]], rules: list[str]) -> None:
        """``agentdojo.capture_reply_wire_fields@1``: the refusal and the reasoning text the provider returned with a kept
        reply, which the stock element keeps out of the AgentDojo message (``_openai_to_assistant_message``; RT-1 under
        ``gateway_compat``), appended after the dump's parts (refusal, then reasoning: the baseline's log order) as
        ``refusal``/``reasoning`` parts, ``O:provider``, ``src`` into the response blob. A kind the dump already holds is
        not added (the baseline attached log reasoning only where the message had none). The dump's parts are never
        changed; the live-versus-native projection leaves these parts out (:func:`native_comparable`)."""
        ref = call.resp.get("response")
        hexdigest = _blob_hex(ref)
        response = self.blob_json(ref)
        choices = response.get("choices") if isinstance(response, dict) else None
        message = _dict(choices[0]).get("message") if isinstance(choices, list) and choices else None
        if hexdigest is None or not isinstance(message, dict):
            return
        present = {part.get("t") for part in parts}
        found: list[tuple[str, str, str]] = []
        refusal = message.get("refusal")
        if isinstance(refusal, str) and refusal and "refusal" not in present:
            found.append(("refusal", refusal, "/choices/0/message/refusal"))
        if "reasoning" not in present:
            for key in ("reasoning", "reasoning_content"):  # the baseline's _reasoning_text, field order kept
                value = message.get(key)
                if isinstance(value, str) and value:
                    found.append(("reasoning", value, f"/choices/0/message/{key}"))
                    break
            else:
                details = message.get("reasoning_details")
                if isinstance(details, list):
                    texts = [d.get("text") or d.get("summary") or "" for d in details if isinstance(d, dict)]
                    text = "".join(t for t in texts if isinstance(t, str))
                    if text:
                        found.append(("reasoning", text, "/choices/0/message/reasoning_details"))
        added: list[int] = []
        hits = self._blob_redactions(call.resp_seq, hexdigest)
        for kind, text, pointer in found:
            k = len(parts)
            parts.append({"t": kind, "text": rec.enc(text, f"/parts/{k}/text")})
            rec.tag(f"/parts/{k}", "O:provider")
            rec.add("src", self.B(hexdigest, pointer))
            added.append(k)
            if hits:  # D-211: a redacted refusal or reasoning text is withheld (D.10.4a item 23)
                rec.data["parts"] = parts
                self._withhold_parts(rec, call.resp_seq, hits, [(k, "text", pointer)])
        if added:  # the rule is unscoped (the parts are O); ext.agentdojo.wire_parts names them for native_comparable
            rules.append(self.R(_WIRE_FIELDS_RULE))
            rec.ext()["wire_parts"] = added

    def _tool_message(self, i: int, rec: _Rec, rules: list[str], responds: Mapping[int, tuple[str | None, str, str]],
                      generators: Mapping[int, tuple[str, str]]) -> None:
        dump_message = self._current_dump[i]
        content, error = dump_message.get("content"), dump_message.get("error")
        part: dict[str, Any] = {"t": "tool_result"}
        block = single_text_block(content)
        if block is not None:
            part["text"] = rec.enc(block, "/parts/0/text")
        elif isinstance(content, list):
            part["value"] = rec.enc(content, "/parts/0/value")
            self.issue("agentdojo.multi_block_tool_content", [str(rec.data["id"])], self.R("agentdojo.tracelogger_record_shape@1"),
                       severity="info")
        else:
            part["text"] = rec.enc(content, "/parts/0/text")
        part["error"] = rec.enc(error, "/parts/0/error")
        target, tag, link_rule = responds.get(i, (None, "I", "agentdojo.positional_match@1"))
        if target is not None:
            part["responds_to"] = target
            rec.tag("/parts/0/responds_to", tag)
        else:
            rec.unk("/parts/0/responds_to", "ambiguous")
            self.issue("orphan_tool_result", [str(rec.data["id"])], self.R(link_rule))
        rules.append(self.R(link_rule, "/parts/0/responds_to"))
        rec.data["parts"] = [part]
        gen = generators.get(i)
        if gen is not None and gen[0] in self._replaced_generator and gen[0] not in self._emitted:
            gen = self._replaced_generator[gen[0]]  # the decision was rejected as malformed: no dangling generator
        actor_kinds = [t for t, k in self.actor_kind.items() if k == "tool_runtime"]
        if gen is not None:
            gid, gtag = gen
            cls = "I" if gtag == "I" else "D"
            rec.data.update(generated_by=gid, after=[{"b": "causal", "id": gid}])
            rec.tag("/generated_by", cls)
            rec.tag("/after", cls)
            rules += [self.R("agentdojo.capture_execution_result@1", "/generated_by"),
                      self.R("aer.output_after_generator@1", "/after")]
            author = self._authors.get(gid)
            if author is not None:
                rec.data["actor"] = author
                rec.tag("/actor", cls)
                rules.append(self.R("agentdojo.capture_execution_result@1", "/actor"))
        else:
            rec.unk("/generated_by", "not_captured")
            if actor_kinds:
                rec.data["actor"] = actor_kinds[0]
                rec.tag("/actor", "D")
                rules.append(self.R("agentdojo.functions_runtime@1", "/actor"))
        tcid = dump_message.get("tool_call_id")
        if target is None or not self._linked_id_equals(target, tcid):
            rec.ext()["tool_call_id"] = rec.enc(tcid, "/ext/agentdojo/tool_call_id")

    def _linked_id_equals(self, target: str, tcid: object) -> bool:
        message_id, _, k = target.partition("#")
        rec = self._records.get(message_id)
        if rec is None:
            return False
        parts = rec.data.get("parts") or []
        part = parts[int(k)] if int(k) < len(parts) else {}
        return "provider_call_id" in part and _lexical(part["provider_call_id"]) == _lexical(tcid)

    def _tool_execution(self, tool: _Tool, scope: str) -> None:
        d, r = tool.data, tool.res
        te = _Rec(k="tool_execution", id=tool.id, actor=str(tool.event["actor"]), scope=scope, ev="O", by="capture",
                  src=[self.L(tool.seq, "/data")])
        te.data["name"] = te.enc(d["name"], "/name")
        rules: list[str] = []
        if tool.part is not None:
            te.data["call"] = tool.part
            te.data["after"] = [{"b": "causal", "id": tool.part.partition("#")[0]}]
            te.tag("/after", "D")
            rules.append(self.R("aer.execution_after_call@1", "/after"))
        else:
            te.unk("/call", "ambiguous")
            rules.append(self.R("agentdojo.capture_execution_result@1", "/call"))
        if "args" in d:
            if self._is_redacted(tool.seq, "/args"):
                te.unk("/args", "withheld")
                self._redacted_record(tool.seq, tool.id)
            else:
                te.data["args"] = te.enc(self._lexical_args(tool), "/args")
        if tool.res_event is None:
            te.unk("/status", "not_captured")
        else:
            te.add("src", self.L(tool.res_seq or 0, "/data"))
            status = r.get("status")
            if status in ("ok", "error", "invalid"):
                te.data["status"] = status
            else:
                te.unk("/status", "ambiguous")
                rules.append(self.R("agentdojo.capture_status@1", "/status"))
            for key in ("args_effective", "returned"):
                if key not in r:
                    continue
                if self._is_redacted(tool.res_seq, f"/{key}"):
                    te.unk(f"/{key}", "withheld")
                    self._redacted_record(tool.res_seq, tool.id)
                elif _blob_hex(r[key]) is not None:
                    te.data[key] = dict(r[key])
                else:
                    te.data[key] = te.enc(r[key], f"/{key}")
            if "args_effective" not in r and status == "invalid":
                te.unk("/args_effective", "not_applicable")
            exc = _dict(r.get("exception"))
            if isinstance(exc.get("type"), str) and isinstance(exc.get("message"), str):
                if self._is_redacted(tool.res_seq, "/exception"):
                    te.unk("/exception", "withheld")
                    self._redacted_record(tool.res_seq, tool.id)
                else:
                    te.data["exception"] = {"message": te.enc(exc["message"], "/exception/message"),
                                            "type": te.enc(exc["type"], "/exception/type")}
        t = _time(tool.event, tool.res_event)
        if t:
            te.data["t"] = t
        if rules:
            te.data["rule"] = rules
        self._authors[tool.id] = str(tool.event["actor"])
        self._emit(te)

    @staticmethod
    def _lexical_args(tool: _Tool) -> Any:
        """The dispatch's requested ``args`` in their source lexical form. A capture event is a JCS line, so the
        dispatch's member order and integral floats are gone; the linked call in the pass's message dump (written as
        TraceLogger writes it, insertion order and Python float spelling) holds them. When the two are the same JCS
        value, the dump's form is encoded (the value is unchanged; ``ext.lex`` gets the order and float hints, as the
        importers record them); otherwise (the stock in-place ``literal_eval`` of string lists changed the dump's
        args) the dispatch's value is kept without hints."""
        requested = tool.data["args"]
        source = tool.lexical_args
        if source is not None and jcs_bytes(source) == jcs_bytes(requested):
            return source
        return requested

    def _denial(self, tool: _Tool, scope: str) -> None:
        """C.5.5: a ``denied`` result is a ``decision`` (verdict ``deny``, subject the call part) and no execution."""
        assert tool.res_seq is not None and tool.part is not None
        dc_id = self.dc_ids[tool.res_seq]
        decider = tool.res.get("decided_by")
        actor = decider if isinstance(decider, str) and decider in self.actor_kind else None
        if actor is None:
            self._malformed(tool.res_seq, "denied tool.result decided_by")
            return
        dc = _Rec(k="decision", id=dc_id, actor=actor, scope=scope, subject=tool.part, verdict="deny", ev="O", by="capture",
                  src=[self.L(tool.seq, "/data"), self.L(tool.res_seq, "/data")],
                  after=[{"b": "causal", "id": tool.part.partition("#")[0]}])
        dc.tag("/after", "D")
        rules = [self.R("aer.decision_after_subject@1", "/after")]
        error = tool.res.get("error")
        if _typed(error):  # the defence's own denial text, as the model was sent it
            dc.data["reason"] = dc.enc(error, "/reason")
        else:
            dc.unk("/reason", "not_recorded")
        match = self.denial_matches.get(str(tool.data.get("occ")))
        if match is not None:
            # D-670: the gate ran the call nowhere and its error matched the defence's declared denial text; the
            # harness attributed the non-execution to the defence by that match, a deterministic reading (class D)
            dc.tag("/actor", "D")
            dc.data["src"].append(self.L(match, "/data/payload"))
            rules.append(self.R("defence.denial_declared_text@1", "/actor"))
        dc.data["rule"] = rules
        if str(tool.data.get("occ")) in self.post_hoc:
            dc.unk("/t", "not_captured")  # recorded after the gate returned: the decision's own time was not observed
        else:
            t = _time(tool.event, tool.res_event)
            if t:
                dc.data["t"] = t
        self._authors[dc_id] = actor
        self._emit(dc)

    def _decision_event(self, seq: int, event: Mapping[str, Any], scope: str) -> None:
        data = _dict(event.get("data"))
        actor = data.get("actor") if isinstance(data.get("actor"), str) else event.get("actor")
        subject = _dict(data.get("subject"))
        target: str | None = None
        if "occ" in subject:
            tool = self.tools.get(str(subject["occ"]))
            target = tool.id if tool is not None and tool.id in self._emitted else None
        elif "call" in subject:
            call = self.calls.get(str(subject["call"]))
            target = call.id if call is not None and call.id in self._emitted else None
        elif "at" in subject:
            at = _dict(subject["at"])
            entry = self.passes.get(_int(event.get("pass")) or 0)
            i, j = _int(at.get("message")), _int(at.get("call"))
            # the subject is a tool_call part: a known assistant message that has call j (as _link_tools; item 46)
            if entry is not None and entry.dump is not None and i is not None and j is not None and 0 <= i < len(entry.dump) \
                    and self._shape(entry.dump[i]) == "assistant" and 0 <= j < len(entry.dump[i].get("tool_calls") or []):
                candidate = part_id(self._mid(entry, i), self._content_len(entry.dump[i]) + j)
                target = candidate if candidate.partition("#")[0] in self._emitted else None
        verdict = data.get("verdict")
        if target is None or not isinstance(actor, str) or actor not in self.actor_kind or verdict not in DECISION_VERDICTS \
                or verdict == "other":
            self._malformed(seq, "decision")
            return
        dc = _Rec(k="decision", id=self.dc_ids[seq], actor=actor, scope=scope, subject=target, verdict=verdict, ev="O",
                  by="capture", src=[self.L(seq, "/data")], after=[{"b": "causal", "id": target.partition("#")[0]}])
        dc.tag("/after", "D")
        rules = [self.R("aer.decision_after_subject@1", "/after")]
        if _typed(data.get("reason")):
            dc.data["reason"] = dc.enc(data["reason"], "/reason")
        else:
            dc.unk("/reason", "not_recorded")
        if _blob_hex(data.get("original")) is not None:
            dc.data["original"] = dict(data["original"])
        elif verdict in ("redact", "modify"):
            dc.unk("/original", "not_captured")
        dc.data["rule"] = rules
        self._authors[self.dc_ids[seq]] = actor
        self._emit(dc)

    def _state_event(self, seq: int, event: Mapping[str, Any], scope: str) -> None:
        data = _dict(event.get("data"))
        env = _dict(data.get("env"))
        st = _Rec(k="state_change", id=self.st_ids[seq], scope=scope, target="environment", ev="O", by="capture",
                  src=[self.L(seq, "/data")])
        tool = self.tools.get(str(data.get("occ"))) if "occ" in data else None
        if tool is not None and tool.id in self._emitted:
            st.data["cause"] = tool.id
        if isinstance(env.get("sha256"), str) and _HEX64.fullmatch(env["sha256"]) and _typed(env.get("canon")):
            st.data["canon"] = st.enc(env["canon"], "/canon")
            st.data["after_sha256"] = env["sha256"]
        if _blob_hex(env.get("snapshot")) is not None:
            st.data["snapshot_after"] = dict(env["snapshot"])
        t = _time(event, None)
        if t:
            st.data["t"] = {k.replace("start", "end"): v for k, v in t.items()}
        self._emit(st)

    def _pass_state(self, entry: _Pass, scope: str) -> None:
        """The per-pass state change (``cause`` = the attempt, C.13.7), when a pass boundary recorded a digest."""
        marker = entry.end or entry.start
        if marker is None:
            return
        before = _dict(_dict(entry.start[1].get("data")).get("env")) if entry.start else {}
        after = _dict(_dict(entry.end[1].get("data")).get("env")) if entry.end else {}
        st = _Rec(k="state_change", id=self.st_ids[marker[0]], scope=scope, cause=scope, target="environment", ev="O",
                  by="capture", src=[self.L(b[0], "/data/env") for b in (entry.start, entry.end) if b is not None])
        canon = before.get("canon") if _typed(before.get("canon")) else after.get("canon") if _typed(after.get("canon")) else None
        digest_before = before.get("sha256") if isinstance(before.get("sha256"), str) and _HEX64.fullmatch(before["sha256"]) else None
        digest_after = after.get("sha256") if isinstance(after.get("sha256"), str) and _HEX64.fullmatch(after["sha256"]) else None
        if canon is not None and (digest_before or digest_after):
            st.data["canon"] = st.enc(canon, "/canon")
            if digest_before:
                st.data["before_sha256"] = digest_before
            if digest_after:
                st.data["after_sha256"] = digest_after
        if digest_after is None:
            st.unk("/after_sha256", "not_captured")
        if digest_before is None:
            st.unk("/before_sha256", "not_captured")
        if isinstance(after.get("changed"), bool):
            st.data["changed"] = after["changed"]
        for key, member in (("snapshot_before", before.get("snapshot")), ("snapshot_after", after.get("snapshot"))):
            if _blob_hex(member) is not None:
                st.data[key] = dict(member)  # type: ignore[arg-type]
        t = _time(entry.start[1] if entry.start else None, entry.end[1] if entry.end else None)
        if t:
            st.data["t"] = t
        self._emit(st)

    def _outside_passes(self) -> None:
        """Calls, executions and decisions recorded outside any pass (``pass: null``) belong to the run scope."""
        for call in self.call_order:
            if call.pass_ is None or call.pass_ not in self.passes:
                call.pass_ = None
                self._model_call(None, call, "run", [])
        for tool in self.tool_order:
            if tool.pass_ is None or tool.pass_ not in self.passes:
                if tool.res.get("status") == "denied":
                    self._malformed(tool.seq, "denied tool.result outside a pass")
                    continue
                tool.pass_ = None
                self._tool_execution(tool, "run")
        for seq, event in self.states:
            p = _int(event.get("pass"))
            if p is None or p not in self.passes:
                self._state_event(seq, event, "run")
        for seq, event in self.decisions:  # regen item 44: decisions of no pass were never emitted
            p = _int(event.get("pass"))
            if p is None or p not in self.passes:
                self._decision_event(seq, event, "run")

    # ------------------------------------------------------------------------------------------ outcomes
    def _judgements(self) -> None:
        valid: list[tuple[int, int, dict[str, Any]]] = []
        for seq, data in self.outcomes:
            judgements = data.get("judgements")
            for k, judgement in enumerate(judgements if isinstance(judgements, list) else []):
                if not isinstance(judgement, dict) or not _typed(judgement.get("name")) or "value" not in judgement \
                        or judgement.get("origin") not in JUDGEMENT_ORIGINS:
                    self._malformed(seq, "outcome judgement")
                    continue
                valid.append((seq, k, judgement))
        # D.6.7 parity (D.10.10 item 12) and the fork's run errors (D.11.7 item 7, D.11.9): the stock runner caught a run
        # error -- a pipeline error event, or the backend's run_error_imposed note read from the native log -- and
        # returned the outcomes its except clause imposes. Those values are a harness default, not a checker's verdict.
        error_seqs = [seq for seq, data in self.errors if data.get("where") == "pipeline"]
        imposed = bool(valid) and bool(error_seqs or self.run_error_note) \
            and all(j["origin"] == "harness_default" for _s, _k, j in valid)
        quirk = self.fam.quirk("agentdojo.run_error_imposes_outcome") if imposed else None
        rule_id = "agentdojo.run_error_imposed_outcome@1"
        if imposed and quirk is None:
            self.issue("agentdojo.undeclared_quirk", ["exec"], self.R(rule_id), detail="agentdojo.run_error_imposes_outcome")
        note_values = _dict(self.run_error_note[1].get("judgements")) if self.run_error_note is not None else {}
        ids: list[str] = []
        for n, (seq, k, judgement) in enumerate(valid):
            name, value = judgement["name"], judgement["value"]
            rec = _Rec(k="judgement", id=f"j{n}", actor=self.bench, subject="run", origin=judgement["origin"],
                       ev="O", by="benchmark", src=[self.L(seq, f"/data/judgements/{k}")])
            rec.data["name"] = rec.enc(name, "/name")
            rec.data["value"] = rec.enc(value, "/value")
            expected = quirk.params.get(name) if quirk is not None else None
            if quirk is not None and isinstance(expected, bool) and value is expected:
                # the origin is derived from the run error and the profile's quirk, not observed: D under the rule
                rec.tag("/origin", "D")
                rec.data["rule"] = [self.R(rule_id, "/origin")]
                rec.add("src", *(self.L(s, "/data/where") for s in error_seqs))
                if self.run_error_note is not None:
                    rec.add("src", self.L(self.run_error_note[0], f"/data/payload/judgements/{name}"))
            else:
                rec.tag("/origin", "O:capture")
                if quirk is not None:
                    self.issue("capture_error", [rec.data["id"]], self.R(rule_id),
                               detail=f"imposed {name} differs from the profile's run_error_imposes_outcome value")
            if self.run_error_note is not None and name in note_values and note_values[name] != value:
                self.issue("capture_error", [rec.data["id"]], self.R(rule_id),
                           detail=f"seq {self.run_error_note[0]}: run_error_imposed note disagrees on {name}")
            if judgement["origin"] == "checker":
                rec.unk("/inputs", "not_recorded")
                rec.data["rule"] = [self.R("agentdojo.checker_inputs_unverified@1", "/inputs")]
            self._emit(rec)
            ids.append(str(rec.data["id"]))
        if imposed:
            self.issue("outcome_imposed_by_runner", ids, self.R(rule_id))
            if quirk is not None:
                self._run_error_extra(quirk.params.get("extra_key"), rule_id)

    def _run_error_extra(self, key: object, rule_id: str) -> None:
        """The log key the fork writes beside an imposed outcome (quirk ``extra_key``, AutoDojo ``error_type``) as
        ``ext.agentdojo.extra.<key>`` of the header, as the TraceLogger mapper keeps it (``O`` by capture: the backend's
        note read it from the native log, which is cited too). A note that disagrees with the native log is reported."""
        if not isinstance(key, str) or not key or self.run_error_note is None:
            return
        seq, payload = self.run_error_note
        if key not in payload:
            self.issue("capture_error", ["exec"], self.R(rule_id), detail=f"seq {seq}: run_error_imposed note lacks {key}")
            return
        value = payload[key]
        pointer = json_pointer("ext", "agentdojo", "extra", key)
        self.h.ext().setdefault("extra", {})[key] = self.h.enc(value, pointer)
        self.h.tag(pointer, "O:capture")
        self.h.add("src", self.L(seq, json_pointer("data", "payload", key)))
        native = self._native_document()
        if isinstance(native, dict):
            self.h.add("src", {"a": "a1", "p": json_pointer(key)})
            if native.get(key) != value:
                self.issue("capture_error", ["exec"], self.R(rule_id),
                           detail=f"seq {seq}: the run_error_imposed note's {key} differs from the native log")

    def _native_document(self) -> Any:
        """The native TraceLogger JSON (strict loader), or ``None`` when it is not in the session or not JSON."""
        if not isinstance(self.unit.auxiliary.get("native_log"), ArtefactRef):
            return None
        try:
            return strict_json_loads(self.ctx.open_auxiliary("native_log"), self.limits)
        except (AgentProvError, IngestError):
            return None

    def _backend_identity(self) -> None:
        """``agentdojo.capture_backend_identity@1`` (D.11.9): the session's backend and benchmark code identity must be
        the profile's. A difference is reported; the profile is never swapped for another one."""
        rule = self.R("agentdojo.capture_backend_identity@1")
        declared = self.live.get("backend")
        if self.backend_id is None:
            self.issue("identity_unresolved", ["exec"], rule, detail="session.start names no backend id")
        elif self.backend_id != declared:
            self.issue("identity_conflict", ["exec"], rule, severity="error",
                       detail=f"session backend {self.backend_id[:40]!r} is not the profile's {str(declared)[:40]!r}")
        pins = _dict(self.live.get("pins"))
        if self.identity is None:
            self.issue("identity_unresolved", ["exec"], rule, detail="no identity event in the verified prefix")
            return
        ident = _dict(self.identity[1].get("benchmark"))
        pairs = [("repo", "repo"), ("commit", "commit")] if "commit" in pins else [("distribution", "dist"), ("version", "dist_version")]
        for pin, member in pairs:
            if pin in pins and ident.get(member) != pins[pin]:
                self.issue("identity_conflict", ["exec"], rule, severity="error",
                           detail=f"seq {self.identity[0]}: identity benchmark {member} differs from the profile pin {pin}")
        if "commit" not in pins and (ident.get("commit") is not None or ident.get("repo") is not None):
            # the fork is distributed under the same name and version as the wheel (D.11.1): a git source contradicts
            # a registry-wheel pin even when distribution and version agree
            self.issue("identity_conflict", ["exec"], rule, severity="error",
                       detail=f"seq {self.identity[0]}: identity benchmark names a git source; the profile pins a wheel")

    # ------------------------------------------------------------------------------------------ issues and checks
    def _session_issues(self) -> None:
        rule = self.R("agentdojo.capture_status@1")
        if not self.view.sealed:
            self.issue("capture_unsealed", ["run"], rule, severity="error",
                       detail=f"verified {len(self.events)} of {self.view.n_lines} lines")
        for seq, data in self.errors:
            fatal = data.get("fatal") is True
            self.issue("capture_error", ["run"], rule, severity="error" if fatal else "warning",
                       detail=f"seq {seq}: {'fatal ' if fatal else ''}error event")
        if self.end is not None and self.end[1].get("status") == "aborted":
            self.issue("aborted_attempt", ["run"], rule)
        if not any(p.start is not None for p in self.passes.values()):
            self.issue("no_execution_observed", ["exec"], self.R("agentdojo.capture_no_pass@1"))
        for seq, _event in self.orphan_results:
            self._malformed(seq, "tool.result without its dispatch")
        if self.native_seq is not None and "native_log" not in self.unit.auxiliary:
            self.issue("capture_error", ["exec"], rule, detail=f"seq {self.native_seq}: native log not in the session")

    def _is_redacted(self, seq: int | None, member: str) -> bool:
        """Whether a redaction of event ``seq`` touches ``member`` (a field pointer or the blob it names)."""
        if seq is None:
            return False
        for item in self.redactions.get(seq, ()):
            field_ = item.get("field")
            if isinstance(field_, str) and (field_ == member or field_.startswith(member + "/")):
                return True
            blob = item.get("blob")
            data = _dict(self.events[seq].get("data"))
            ref = data.get(member.lstrip("/"))
            hexdigest = _blob_hex(ref)
            if isinstance(blob, str) and hexdigest is not None and blob.removeprefix("sha256:") == hexdigest:
                return True
        return False

    def _blob_redactions(self, seq: int | None, hexdigest: str | None) -> list[str]:
        """The pointers into blob ``hexdigest`` that event ``seq`` reports redacted (capture/0.1 ``{blob, p, rule}``)."""
        if seq is None or hexdigest is None:
            return []
        return [str(item["p"]) for item in self.redactions.get(seq, ())
                if isinstance(item.get("p"), str) and str(item.get("blob", "")).removeprefix("sha256:") == hexdigest]

    def _withhold_parts(self, rec: _Rec, seq: int | None, hits: Sequence[str],
                        members: Sequence[tuple[int, str, str]]) -> None:
        """D.10.4a item 23 under ``aer/0.2`` (D-211): a required part member that D-211 may withhold (the ``text`` of a
        text, reasoning or refusal part, a tool_call's ``args``, an other part's ``value``; never a tool_result's) built
        from a redacted place of a blob is omitted with ``unk withheld``, instead of keeping the redacted value.
        ``members`` are ``(part index, member, pointer into the blob)``; a redaction at or under the pointer withholds the
        member."""
        if not hits:
            return
        parts = rec.data.get("parts") or []
        for k, member, pointer in members:
            if k < len(parts) and parts[k].get("t") == "tool_result":  # RC-1: outside D-211's relaxation
                continue
            if k < len(parts) and member in parts[k] and any(p == pointer or p.startswith(pointer + "/") for p in hits):
                del parts[k][member]
                rec.unk(f"/parts/{k}/{member}", "withheld")
                self._redacted_record(seq, str(rec.data["id"]))

    @staticmethod
    def _content_members(parts: Sequence[Mapping[str, Any]], content: object, base: str) -> list[tuple[int, str, str]]:
        """The content parts' required members and their blob pointers: one part for a string (or ``null``), one per
        block for a list (R-CONTENT, ``content_block_parts``)."""
        def member(part: Mapping[str, Any]) -> str:
            return "text" if "text" in part else "value"

        if isinstance(content, list):
            return [(b, member(parts[b]), f"{base}/{b}") for b in range(min(len(content), len(parts)))]
        return [(0, member(parts[0]), base)] if parts else []

    def _redacted_record(self, seq: int | None, rid: str) -> None:
        if seq is not None:
            self.redacted_ids.setdefault(seq, [])
            if rid not in self.redacted_ids[seq]:
                self.redacted_ids[seq].append(rid)

    def _redaction_issues(self) -> None:
        for seq in sorted(self.redactions):
            ids = self.redacted_ids.get(seq) or ["exec"]
            for item in self.redactions[seq]:
                rule_id = item.get("rule")
                declared = isinstance(rule_id, str) and _RULE_ID.fullmatch(rule_id) is not None \
                    and rule_id.startswith("cap.secret.") and self._declared(rule_id)
                self.issue("capture_redaction", ids, rule_id if declared else self.R("agentdojo.capture_withheld@1"),  # type: ignore[arg-type]
                           detail=f"seq {seq}")

    def _declared(self, rule_id: str) -> bool:
        try:
            self.R(rule_id)
        except AgentProvError:
            return False
        return True

    def _checks(self) -> None:
        sealed_ok = self.view.sealed and not self.view.findings
        self.ctx.check("aer.acc.capture_chain@1", scope="run", verdict="consistent" if sealed_ok else "inconsistent",
                       observed={"lines": self.view.n_lines, "verified": len(self.events)},
                       reason=None if sealed_ok else ("unsealed" if not self.view.sealed else "chain_findings"))
        starts = [p for p in self.passes.values() if p.start is not None]
        if self.passes:
            ends = [p for p in self.passes.values() if p.end is not None]
            closed = all(p.end is not None for p in starts) and all(p.start is not None for p in ends)
            self.ctx.check("aer.acc.passes_closed@1", scope="run", verdict="consistent" if closed else "inconsistent",
                           observed={"pass_end": len(ends), "pass_start": len(starts)},
                           reason=None if closed else "pass_without_end")
        # dispatch_vs_results, per scope holding a dispatch or a result: run first, then the attempts by index
        def scope_of(p: int | None) -> str:
            return f"att{p}" if p is not None and p in self.passes else "run"

        tallies: dict[str, list[int]] = {}  # scope -> [dispatches, results, unpaired]
        for tool in self.tool_order:
            row = tallies.setdefault(scope_of(tool.pass_), [0, 0, 0])
            row[0] += 1
            row[1] += int(tool.res_event is not None)
            row[2] += int(tool.res_event is None)
        for _seq, event in self.orphan_results:
            row = tallies.setdefault(scope_of(_int(event.get("pass"))), [0, 0, 0])
            row[1] += 1
            row[2] += 1
        for scope in sorted(tallies, key=lambda s: -1 if s == "run" else int(s[3:])):
            dispatches, results, unpaired = tallies[scope]
            self.ctx.check("aer.acc.dispatch_vs_results@1", scope=scope,
                           verdict="consistent" if unpaired == 0 else "inconsistent",
                           observed={"dispatches": dispatches, "results": results},
                           reason=None if unpaired == 0 else "occurrence_without_its_pair")
        for index in sorted(self.passes):
            entry = self.passes[index]
            before = _dict(_dict(entry.start[1].get("data")).get("env")) if entry.start else {}
            after = _dict(_dict(entry.end[1].get("data")).get("env")) if entry.end else {}
            has_before = isinstance(before.get("sha256"), str) and _HEX64.fullmatch(before["sha256"]) is not None
            has_after = isinstance(after.get("sha256"), str) and _HEX64.fullmatch(after["sha256"]) is not None
            ok = has_before and has_after
            self.ctx.check("aer.acc.env_recorded@1", scope=f"att{index}", verdict="consistent" if ok else "inconsistent",
                           observed={"after": int(has_after), "before": int(has_before)},
                           reason=None if ok else "state_digest_missing")

    # ------------------------------------------------------------------------------------------ live versus native
    def _native_check(self, records: list[dict[str, Any]]) -> None:
        """D.10.4: map the native TraceLogger JSON under the same profile and compare the common projections."""
        native_ref = self.unit.auxiliary.get("native_log")
        if not isinstance(native_ref, ArtefactRef):
            return
        rule = self.R("agentdojo.capture_native_check@1")
        try:
            raw = self.ctx.open_auxiliary("native_log")
        except AgentProvError:
            self.issue("live_native_divergence", ["exec"], rule, severity="error", detail="native log unreadable")
            return
        reader = TraceLoggerReader()
        sniff = reader.sniff(raw, label="", limits=self.limits)
        if not sniff.match:
            self.issue("live_native_divergence", ["exec"], rule, severity="error",
                       detail="native log is not a TraceLogger record: " + ",".join(sniff.reasons))
            return
        artefact = ArtefactRef("a0", native_ref.sha256, native_ref.bytes, "application/json", native_ref.origin,
                               "primary", "native")
        mapping = mapping_id(TRACELOGGER_ID, self.ctx.profile.id)
        sub = _SubContext(self.ctx, mapping, import_execution_id(mapping, native_ref.sha256, {"p": ""}))
        try:
            item = next(reader.parse(raw, artefact, limits=self.limits))
            native = [dict(r) for r in TraceLoggerMapper().map(ExecutionUnit(primary=item), sub)]
        except (IngestError, MalformedArtefact, UnsupportedVariant) as exc:
            self.issue("live_native_divergence", ["exec"], rule, severity="error",
                       detail=f"native log not mappable ({exc.code})")
            return
        denied = {r.get("subject") for r in records if r.get("k") == "decision" and r.get("verdict") == "deny"}
        if denied:  # D-670: the native log writes a denied call as an errored tool message (no decision exists there)
            native = [r for r in native if not (r.get("k") == "tool_execution" and r.get("call") in denied)]
        live_projection, native_projection = common_projection(native_comparable(records)), common_projection(native)
        if projection_bytes(live_projection) != projection_bytes(native_projection):
            pointers = projection_differences(live_projection, native_projection, limit=12)
            self.issue("live_native_divergence", ["exec"], rule, severity="error",
                       detail="differs at " + ", ".join(pointers))

    # ------------------------------------------------------------------------------------------ emission
    def _emit(self, rec: _Rec | dict[str, Any]) -> None:
        self.body.append(rec)
        rid = rec.data["id"] if isinstance(rec, _Rec) else rec["id"]
        self._emitted.add(rid)
        if isinstance(rec, _Rec):
            self._records[rid] = rec


# ------------------------------------------------------------------------------------------------ module helpers
_BAD: Final = object()
#: The ``agentdojo`` notes of the defence recorders (D-670; ``agentprov_backend.defences``) the mapper reads.
DEFENCE_NOTES: Final = frozenset({"defence_message", "defence_denial_match", "defence_gate_post_hoc", "defence_identity",
                                  "defence_detached_input"})
_ABORT_RULE: Final = "agentdojo.capture_abort_message@1"


_WIRE_FIELDS_RULE: Final = "agentdojo.capture_reply_wire_fields@1"


def native_comparable(records: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """The live records the native log can express: without the message ``AbortAgentError`` appends to an aborted pass,
    which the TraceLogger never logs (``agentdojo.art.abort_message_not_logged``; D.10.4a), and without the reply parts
    only the wire carries (``agentdojo.capture_reply_wire_fields@1``: capture is the more informative record, K.9.1(3)).
    Those parts are always the last of their message, so the remaining parts keep their indices. A reasoning part
    withheld under ``anthropic_messages.thinking_omitted@1`` is compared with the empty text the wire and the native log
    both hold."""
    out: list[Mapping[str, Any]] = []
    for r in records:
        if r.get("k") != "message":
            out.append(r)
            continue
        if _ABORT_RULE in (r.get("rule") or ()):
            continue
        ext = r.get("ext")
        listed = ext.get("agentdojo", {}).get("wire_parts") if isinstance(ext, Mapping) else None
        wire = {k for k in listed if isinstance(k, int)} if isinstance(listed, list) else set()
        omitted = ext.get("agentdojo", {}).get("thinking_omitted") if isinstance(ext, Mapping) else None
        if isinstance(omitted, list) and isinstance(r.get("parts"), list):
            # D-656: the native log holds the empty text the wire shows; the live record withholds it (comparison only)
            r = {**r, "parts": [{**part, "text": ""} if k in omitted and "text" not in part else part
                                for k, part in enumerate(r["parts"])]}
        if wire and isinstance(r.get("parts"), list):
            r = {**r, "parts": [part for k, part in enumerate(r["parts"]) if k not in wire]}
        out.append(r)
    return out


def _call_ok(call: object) -> bool:
    return (isinstance(call, dict) and set(call) <= {"function", "args", "id", "placeholder_args"}
            and {"function", "args"} <= set(call) and isinstance(call["function"], str) and isinstance(call["args"], dict))


def _native_texts(content: object) -> list[str] | None:
    """The texts the stock rendering sends for recorded content: ``None``; a string; each block's ``content or ""``."""
    if content is None:
        return None
    if isinstance(content, str):
        return [content]
    if isinstance(content, list):
        return [str(b.get("content") or "") if isinstance(b, dict) else "" for b in content]
    return None


def _wire_texts(content: object) -> Any:
    """The texts of sent content: ``None``; a string; the ``text`` of each text part (another part kind is ``_BAD``)."""
    if content is None:
        return None
    if isinstance(content, str):
        return [content]
    if isinstance(content, list):
        out: list[str] = []
        for part in content:
            if not isinstance(part, dict) or part.get("type") != "text" or not isinstance(part.get("text"), str):
                return _BAD
            out.append(part["text"])
        return out
    return _BAD


def _jcs_sha256(value: object) -> str | None:
    try:
        return hashlib.sha256(jcs_bytes(value)).hexdigest()
    except (TypeError, ValueError):
        return None


def _unique_alignment(candidates: Sequence[Any], wire: Sequence[Any], equal: Any) -> list[int] | None:
    """The positions of ``candidates`` that ``wire`` matches one to one in order, when exactly one such alignment exists
    (``cap.context_alignment@1``); ``None`` when none or several do. Counting is capped at two."""
    n, m = len(candidates), len(wire)
    if m == 0 or m > n:
        return [] if m == 0 else None
    match = [[bool(equal(candidates[i], wire[j])) for j in range(m)] for i in range(n)]
    # ways[i][j]: alignments of wire[j:] onto candidates[i:], capped at 2
    ways = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        ways[i][m] = 1
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            total = ways[i + 1][j] + (ways[i + 1][j + 1] if match[i][j] else 0)
            ways[i][j] = min(total, 2)
    if ways[0][0] != 1:
        return None
    out: list[int] = []
    i, j = 0, 0
    while j < m:
        if match[i][j] and ways[i + 1][j + 1] == 1 and ways[i + 1][j] == 0:
            out.append(i)
            j += 1
        i += 1
    return out
