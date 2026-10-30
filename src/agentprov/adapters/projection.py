"""The common projection of an AER: the view two mappings of one execution must agree on (docs/architecture D.10.4,
K.3.2, K.9.1; layer L4).

The live capture of an AgentDojo cell and the native TraceLogger log the stock harness wrote for the same cell are two
records of one execution. Their AERs differ by design (the capture holds every pass, wire requests, times and the
provider's facts; the native log holds the last pass only), so they are compared through a projection that keeps only
what both express:

* ``messages``: the message sequence of the **scored attempt** (the attempt scope with ``scored: true``, else the last
  attempt scope in file order), without the messages of discarded replies (views exclude them, C.13.7): per message its
  ``role`` and its parts (text, reasoning, tool-call ``name`` and ``args``, tool-result ``text``/``value`` and ``error``,
  other parts' ``type``/``value``), the tool-call parts after the others (a stable partition: content order is kept,
  and a message's calls are a member separate from its content, so where a mapper places them carries no fact; the
  importers put them last, the capture mapper puts the reply facts only the wire carries after them, D.10.4a);
* ``tool_executions``: the ``name`` and ``status`` of the executions of that attempt, in file order;
* ``fixtures``: ``kind``, ``vector`` and ``content`` of every fixture, ordered by vector then content;
* ``judgements``: ``name`` and ``value``, ordered by name.

Values are compared **as JCS values with their lexical hints** (D.10.4): every copied value is decoded with the record's
``ext.lex`` hints (:func:`agentprov.aer.canon.decode_value`) and rendered in its source lexical form (member order and
int/float kept; ASCII-escaped). Times, ids, evidence tags, locators and ``ext`` are excluded (K.9.1 item 4). The result
is plain JSON: compare it as JCS bytes (:func:`projection_bytes`), never with Python ``==``.

``agentprov.testing.projections.common_projection`` is this function (the test-support name of K.3.2); the capture
mapper uses it for the live-versus-native check, so it lives in the adapters layer.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Final

from agentprov.aer.canon import CanonError, LexHints, decode_value
from agentprov.io.canonical import jcs_bytes

__all__ = ["PROJECTION_KEYS", "common_projection", "projection_bytes", "projection_differences"]

PROJECTION_KEYS: Final = ("fixtures", "judgements", "messages", "tool_executions")


def _lexical(value: object, pointer: str, lex: LexHints | None) -> str:
    """The value in its source lexical form: decoded with the hints at ``pointer``, rendered with source member order
    and float typing, ASCII-escaped (a lone surrogate never reaches the JCS encoder)."""
    try:
        decoded = decode_value(value, at=pointer, lex=lex)  # type: ignore[arg-type]
    except CanonError:  # a malformed reserved object: compare the stored form
        decoded = value
    return json.dumps(decoded, ensure_ascii=True, allow_nan=True, separators=(",", ":"))


def _lex_of(record: Mapping[str, Any]) -> LexHints | None:
    ext = record.get("ext")
    lex = ext.get("lex") if isinstance(ext, Mapping) else None
    return LexHints.from_dict(lex) if isinstance(lex, Mapping) else None


def _part(part: Mapping[str, Any], k: int, lex: LexHints | None) -> dict[str, Any]:
    t = part.get("t")
    base = f"/parts/{k}"
    out: dict[str, Any] = {"t": t}
    keys: Sequence[str]
    if t in ("text", "reasoning", "refusal"):
        keys = ("text",)
    elif t == "tool_call":
        keys = ("name", "args")
    elif t == "tool_result":
        keys = ("text", "value", "error")
    elif t == "other":
        keys = ("type", "value")
    else:
        keys = tuple(sorted(k for k in part if k != "t"))
    for key in keys:
        if key in part:
            out[key] = _lexical(part[key], f"{base}/{key}", lex)
    return out


def _calls_last(parts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The projected parts with every ``tool_call`` part after the others, each group in its own order."""
    return [p for p in parts if p.get("t") != "tool_call"] + [p for p in parts if p.get("t") == "tool_call"]


def _scored_attempt(records: Sequence[Mapping[str, Any]]) -> str | None:
    attempts = [r for r in records if r.get("k") == "scope" and r.get("kind") == "attempt" and isinstance(r.get("id"), str)]
    scored = [r for r in attempts if r.get("scored") is True]
    chosen = scored[-1] if scored else (attempts[-1] if attempts else None)
    return str(chosen["id"]) if chosen is not None else None


def common_projection(aer_records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """The comparable view of an AER's records (header and seal ignored); see the module docstring."""
    records = [r for r in aer_records if isinstance(r, Mapping)]
    attempt = _scored_attempt(records)
    discarded = {r.get("id") for r in records if r.get("k") == "model_call" and r.get("status") == "discarded"}
    messages: list[dict[str, Any]] = []
    executions: list[dict[str, Any]] = []
    fixtures: list[dict[str, Any]] = []
    judgements: list[dict[str, Any]] = []
    for record in records:
        kind = record.get("k")
        lex = _lex_of(record)
        if kind == "message" and attempt is not None and record.get("scope") == attempt:
            if record.get("generated_by") in discarded:
                continue
            parts = record.get("parts")
            messages.append({
                "role": _lexical(record.get("role"), "/role", lex),
                "parts": _calls_last([_part(p, k, lex) for k, p in enumerate(parts) if isinstance(p, Mapping)])
                if isinstance(parts, list) else [],
            })
        elif kind == "tool_execution" and attempt is not None and record.get("scope") == attempt:
            entry: dict[str, Any] = {"name": _lexical(record.get("name"), "/name", lex)}
            if "status" in record:
                entry["status"] = record["status"]
            executions.append(entry)
        elif kind == "fixture":
            fixture: dict[str, Any] = {"kind": record.get("kind")}
            for key in ("vector", "content"):
                if key in record:
                    fixture[key] = _lexical(record[key], f"/{key}", lex)
            fixtures.append(fixture)
        elif kind == "judgement":
            judgements.append({"name": _lexical(record.get("name"), "/name", lex),
                               "value": _lexical(record.get("value"), "/value", lex)})
    fixtures.sort(key=lambda f: (str(f.get("vector", "")), str(f.get("content", ""))))
    judgements.sort(key=lambda j: (str(j["name"]), str(j["value"])))
    return {"fixtures": fixtures, "judgements": judgements, "messages": messages, "tool_executions": executions}


def projection_bytes(projection: Mapping[str, Any]) -> bytes:
    """The JCS bytes of a projection (the comparison form, K.1(9))."""
    return jcs_bytes(dict(projection))


def projection_differences(left: Mapping[str, Any], right: Mapping[str, Any], *, limit: int = 20) -> list[str]:
    """JSON Pointers (into the projection) at which ``left`` and ``right`` differ, in document order, at most ``limit``.

    The pointers are built from the projection's fixed member names and list indices only, so they carry no source text.
    """
    out: list[str] = []
    stack: list[tuple[object, object, str]] = [(left, right, "")]
    while stack and len(out) < limit:
        a, b, at = stack.pop(0)
        if isinstance(a, Mapping) and isinstance(b, Mapping):
            for key in sorted(set(a) | set(b)):
                if key not in a or key not in b:
                    out.append(f"{at}/{key}")
                else:
                    stack.append((a[key], b[key], f"{at}/{key}"))
        elif isinstance(a, list) and isinstance(b, list):
            for i in range(max(len(a), len(b))):
                if i >= len(a) or i >= len(b):
                    out.append(f"{at}/{i}")
                else:
                    stack.append((a[i], b[i], f"{at}/{i}"))
        elif jcs_bytes(a) != jcs_bytes(b):
            out.append(at or "/")
    return out[:limit]
