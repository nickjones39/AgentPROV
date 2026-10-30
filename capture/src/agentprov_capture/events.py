"""The capture/0.1 event model: envelope, closed event-type vocabulary and per-type ``data`` member sets (C.13.2, C.13.3).

This module is the writer's and the verifier's shared definition of *shape*. It is deliberately smaller than the
published JSON Schema (``agentprov/schemas/capture-0.1.schema.json``, C.13.9): it checks the envelope exactly, the type
vocabulary exactly, and the *top-level member sets* of ``data`` (required and optional members per type). Nested shapes
are the schema's job (a core test validates everything the writer produces against it, and pins ``DATA_MEMBERS`` to
the schema).

Rejected by construction (K.5.7 item 6): the envelope names ``pass_no`` and ``monotonic_ns``, the event types
``llm.exchange``, ``llm.span``, ``exception`` and ``artefact``, and the ``session.end`` members ``completed`` and ``by``
(``status`` and ``appended_by`` are the only terminal vocabulary).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Final

__all__ = [
    "ACTOR_TAG_RE",
    "APPENDED_BY",
    "BLOB_DIGEST_RE",
    "DATA_MEMBERS",
    "ENVELOPE_FIELDS",
    "EVENT_TYPES",
    "HEX64_RE",
    "SESSION_STATUSES",
    "TS_RE",
    "BlobRef",
    "data_problem",
    "envelope_problem",
    "format_ts",
    "is_blob_ref",
]

#: ``BlobRef`` (C.11.5, C.13.8): a plain dict ``{"$blob": "sha256:<hex64>", "bytes": int, "media": str}``.
BlobRef = dict[str, Any]

#: The closed event-type vocabulary of C.13.3, in the order of the table. New types wait for ``capture/0.2``.
EVENT_TYPES: Final[tuple[str, ...]] = (
    "session.start",
    "instrumentation",
    "identity",
    "fixture",
    "pass.start",
    "llm.request",
    "llm.response",
    "tool.dispatch",
    "tool.result",
    "decision",
    "state",
    "pass.end",
    "outcome",
    "native.log",
    "note",
    "error",
    "session.end",
)

#: The envelope members of C.13.2: exactly these, plus the optional top-level ``lex``.
ENVELOPE_FIELDS: Final[frozenset[str]] = frozenset({"seq", "type", "ts", "mono_ns", "pass", "actor", "prev", "data"})
_ENVELOPE_OPTIONAL: Final[frozenset[str]] = frozenset({"lex"})

SESSION_STATUSES: Final[tuple[str, ...]] = ("complete", "incomplete", "errored", "aborted")
APPENDED_BY: Final[tuple[str, ...]] = ("worker", "parent")


def _members(required: str, optional: str = "") -> tuple[frozenset[str], frozenset[str]]:
    return frozenset(required.split()), frozenset(optional.split()) | {"redactions"}


#: ``type -> (required members, optional members)`` of ``data`` (closed in 0.1; C.13.3, C.13.9). ``redactions`` may
#: appear in every type (C.13.9 resolution 2).
DATA_MEMBERS: Final[Mapping[str, tuple[frozenset[str], frozenset[str]]]] = {
    "session.start": _members("actors attempt backend capture cell config_sha256 ex runtime session writer"),
    "instrumentation": _members("items"),
    "identity": _members("agent benchmark harness"),
    "fixture": _members("content kind", "subtype vector"),
    "pass.start": _members("env"),
    "llm.request": _members("attempt call endpoint params request role", "input_at n_messages retry_of"),
    "llm.response": _members(
        "call status", "exception finish_reason http_status reason response response_id served_model usage"
    ),
    "tool.dispatch": _members("args name occ provider_call_id", "args_raw at"),
    "tool.result": _members(
        "model_visible occ rendered status", "args_effective decided_by error exception returned"
    ),
    "decision": _members("actor subject verdict", "original reason replacement subtype"),
    "state": _members("env", "occ"),
    "pass.end": _members("aborted env messages"),
    "outcome": _members("judgements", "declared_semantics"),
    "native.log": _members("bytes path sha256"),
    "note": _members("kind ns payload"),
    "error": _members("exception fatal where", "traceback"),
    "session.end": _members("appended_by n_events status"),
}

ACTOR_TAG_RE: Final = re.compile(r"[a-z][a-z0-9_]{0,31}")
HEX64_RE: Final = re.compile(r"[0-9a-f]{64}")
BLOB_DIGEST_RE: Final = re.compile(r"sha256:[0-9a-f]{64}")
#: Envelope ``ts``: RFC 3339 UTC with exactly six fraction digits and ``Z`` (C.13.9 resolution 5).
TS_RE: Final = re.compile(
    r"[0-9]{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])T(?:[01][0-9]|2[0-3]):[0-5][0-9]:(?:[0-5][0-9]|60)\.[0-9]{6}Z"
)


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def format_ts(moment: datetime) -> str:
    """``YYYY-MM-DDTHH:MM:SS.ffffffZ`` from an aware datetime (converted to UTC). A naive datetime is refused."""
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("the clock must return an aware datetime")
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def is_blob_ref(value: object) -> bool:
    """A ``$blob`` reference object (any dict with a ``$blob`` member counts; its shape is checked by the writer)."""
    return isinstance(value, dict) and "$blob" in value


def envelope_problem(event: object) -> str | None:
    """The first problem with ``event`` as an envelope (C.13.2) or ``None``.

    Checks the exact member set, the types and ranges of ``seq``, ``type``, ``ts``, ``mono_ns``, ``pass``, ``actor``,
    ``prev`` and that ``data`` is an object, and ``prev`` is ``null`` iff ``seq`` is 0. It does not check chain linkage.
    """
    if not isinstance(event, Mapping):
        return "event is not an object"
    keys = set(event)
    missing = ENVELOPE_FIELDS - keys
    if missing:
        return f"missing envelope member {sorted(missing)[0]!r}"
    extra = keys - ENVELOPE_FIELDS - _ENVELOPE_OPTIONAL
    if extra:
        return f"unknown envelope member {sorted(extra, key=str)[0]!r}"
    seq = event["seq"]
    if not _is_int(seq) or seq < 0:
        return "seq must be a non-negative integer"
    kind = event["type"]
    if not isinstance(kind, str) or kind not in EVENT_TYPES:
        return "type is not in the capture/0.1 vocabulary"
    ts = event["ts"]
    if not isinstance(ts, str) or TS_RE.fullmatch(ts) is None:
        return "ts must be RFC 3339 UTC with six fraction digits and Z"
    mono = event["mono_ns"]
    if not _is_int(mono) or mono < 0:
        return "mono_ns must be a non-negative integer"
    pass_ = event["pass"]
    if pass_ is not None and (not _is_int(pass_) or pass_ < 0):
        return "pass must be a non-negative integer or null"
    actor = event["actor"]
    if actor is not None and (not isinstance(actor, str) or ACTOR_TAG_RE.fullmatch(actor) is None):
        return "actor must be a tag or null"
    prev = event["prev"]
    if seq == 0:
        if prev is not None:
            return "prev of seq 0 must be null"
    elif not isinstance(prev, str) or HEX64_RE.fullmatch(prev) is None:
        return "prev must be 64 lower-case hex digits"
    if not isinstance(event["data"], Mapping):
        return "data must be an object"
    if "lex" in event and not isinstance(event["lex"], Mapping):
        return "lex must be an object"
    return None


def data_problem(kind: str, data: object) -> str | None:
    """The first problem with the top-level members of ``data`` for event type ``kind`` or ``None``.

    Closed member sets (C.13.3): an unknown member (``completed``, ``by``, ``plan_sha256``, ``mode``, ...) or a missing
    required member is a problem. Values are not checked here, except the ``session.end`` enumerations.
    """
    if kind not in DATA_MEMBERS:
        return "type is not in the capture/0.1 vocabulary"
    if not isinstance(data, Mapping):
        return "data must be an object"
    required, optional = DATA_MEMBERS[kind]
    keys = set(data)
    unknown = keys - required - optional
    if unknown:
        return f"unknown data member {sorted(unknown, key=str)[0]!r} for {kind}"
    missing = required - keys
    if missing:
        return f"missing data member {sorted(missing)[0]!r} for {kind}"
    if kind == "session.end":
        if data["status"] not in SESSION_STATUSES:
            return "session.end status must be complete, incomplete, errored or aborted"
        if data["appended_by"] not in APPENDED_BY:
            return "session.end appended_by must be worker or parent"
        if not _is_int(data["n_events"]) or data["n_events"] < 1:
            return "session.end n_events must be a positive integer"
    return None
