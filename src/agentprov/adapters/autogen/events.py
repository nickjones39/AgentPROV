"""A run's rows of the harness event log ``events.jsonl`` and its attempt (docs/architecture D.19.4; D-302).

The harness writes every event of a team run to the phase's ``events.jsonl`` with a run-wide counter ``seq`` starting at
1 (``RunLog.add`` in the deposit's ``src/harness.py``; read as data, never run). A run that errored was set aside and run
again under the same ``run_id`` (``set_aside_errors``), so its events hold an aborted first attempt and a second one whose
counter restarts at 1. The run row belongs to the attempt whose model responses match it: the last attempt, checked by
the function-call ids and the response texts (``autogen.event_attempt@1``, D). Rows are selected by ``run_id`` (an id
join), never by order or time.

Kinds: ``guard`` (a verdict per guard on one text, identified by the first 16 hex digits of its SHA-256), ``llm_request``
(the messages handed to the model client), ``llm_response`` (its result, with ``request_seq``) and ``tool_call`` (a tool
body entered). Standard library and ``agentprov.{ingest,errors}`` only.
"""

from __future__ import annotations

import hashlib
import io
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from agentprov.errors import IngestError, MalformedArtefact
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import NO_VALUE, scan_jsonl

__all__ = ["EVENT_KINDS", "Event", "RunEvents", "load_run_events", "sha16"]

EVENT_KINDS: Final = frozenset({"guard", "llm_request", "llm_response", "tool_call"})


def sha16(text: str) -> str:
    """The harness's text digest: the first 16 hex digits of SHA-256 over the UTF-8 text (``sha`` in harness.py)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class Event:
    """One event row: its 0-based line in ``events.jsonl`` and its parsed object."""

    line: int
    value: Mapping[str, Any]

    @property
    def kind(self) -> str:
        return str(self.value.get("kind"))

    @property
    def seq(self) -> int:
        return int(self.value["seq"])


@dataclass
class RunEvents:
    """The events of one run: the attempt mapped and the aborted earlier attempts (counted, never mapped)."""

    attempt: list[Event]
    aborted: list[list[Event]] = field(default_factory=list)

    def of(self, kind: str) -> list[Event]:
        return [e for e in self.attempt if e.kind == kind]

    def requests(self) -> dict[int, Event]:
        return {e.seq: e for e in self.of("llm_request")}

    def response_of(self) -> dict[int, Event]:
        """``request seq`` -> its response (``request_seq`` names the request: ``autogen.request_seq@1``)."""
        out: dict[int, Event] = {}
        for e in self.of("llm_response"):
            rs = e.value.get("request_seq")
            if isinstance(rs, int) and not isinstance(rs, bool) and rs not in out:
                out[rs] = e
        return out


def _check(value: object) -> Mapping[str, Any]:
    if not isinstance(value, dict) or value.get("kind") not in EVENT_KINDS:
        raise MalformedArtefact("an events.jsonl row is not an event of a known kind")
    seq = value.get("seq")
    if not isinstance(seq, int) or isinstance(seq, bool) or seq < 1 or not isinstance(value.get("run_id"), str):
        raise MalformedArtefact("an events.jsonl row has no positive seq or no run_id")
    return value


#: Parsed event logs by content digest (a pure cache: equal bytes parse to equal rows). One phase's log serves every run
#: of that phase, so a worker mapping many rows of one file parses its log once.
_INDEX: dict[str, dict[str, list[Event]]] = {}
_INDEX_MAX: Final = 4


def _index(data: bytes, limits: IngestLimits) -> dict[str, list[Event]]:
    key = hashlib.sha256(data).hexdigest()
    hit = _INDEX.get(key)
    if hit is not None:
        return hit
    by_run: dict[str, list[Event]] = {}
    for line, _offset, value, findings in scan_jsonl(io.BytesIO(data), limits):
        bad = next((f for f in findings if f.severity == "error"), None)
        if bad is not None:
            raise IngestError(bad.code, f"events.jsonl line {line}: rejected")
        if value is NO_VALUE:
            continue
        if isinstance(value, dict) and isinstance(value.get("run_id"), str):
            by_run.setdefault(value["run_id"], []).append(Event(line, value))
    if len(_INDEX) >= _INDEX_MAX:
        _INDEX.pop(next(iter(_INDEX)))
    _INDEX[key] = by_run
    return by_run


def load_run_events(data: bytes, run_id: str, limits: IngestLimits, *,
                    call_ids: Sequence[Sequence[str]], texts: Sequence[tuple[str, str]]) -> RunEvents:
    """The events of ``run_id``, split into attempts where ``seq`` restarts at 1. The attempt mapped is the last one;
    ``call_ids`` (the row's request events' call ids, in order) and ``texts`` ((agent, text) of the row's agent
    messages) must agree with it, else ``MalformedArtefact`` (no attempt can be named)."""
    rows = [Event(e.line, _check(e.value)) for e in _index(data, limits).get(run_id, [])]
    if not rows:
        return RunEvents([])
    attempts: list[list[Event]] = []
    for e in rows:
        if e.seq == 1 or not attempts:
            attempts.append([])
        attempts[-1].append(e)
    last = RunEvents(attempts[-1], attempts[:-1])
    if not _agrees(last, call_ids, texts):
        raise MalformedArtefact("the run's last event attempt does not match the run row")
    return last


def _agrees(run: RunEvents, call_ids: Sequence[Sequence[str]], texts: Sequence[tuple[str, str]]) -> bool:
    """The attempt's function-call ids equal the row's request ids in order, and every agent text of the row is the
    text of a response of the same agent (the census found this in 1,080 of 1,080 runs)."""
    resp_ids = [[str(c.get("id")) for c in e.value["content"] if isinstance(c, dict)]
                for e in run.of("llm_response") if isinstance(e.value.get("content"), list)]
    if [list(x) for x in call_ids] != resp_ids:
        return False
    answered = {(str(e.value.get("agent")), e.value["content"]) for e in run.of("llm_response")
                if isinstance(e.value.get("content"), str)}
    return all(t in answered for t in texts)
