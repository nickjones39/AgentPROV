"""The experimental live PROV preview's data side (design §9; D-398). No Qt, no network, nothing written.

**It is not provenance.** The corpus PROV comes from the engine's versioned rule catalogue after recording
(invariant 1). This is a provisional picture of the capture stream for watching a run: never saved, exported or
compared with corpus PROV.

:class:`CaptureTail` follows one growing ``raw/capture/<session>.capture.jsonl`` (capture/0.1): an offset reader with a
partial-line buffer, each complete line parsed by the strict loader under a size cap, and the ``prev`` chain checked
(sha256 of the previous line, LF included). A broken chain, a malformed line or an over-long one stops that tail with
a reason; nothing is repaired.

:func:`deltas` reads **envelope metadata only**: ``seq``, ``type``, ``pass``, ``actor``, and from ``data`` only the ids
``call``, ``occ``, ``status``, ``at``, ``input_at`` and ``n_messages`` (each checked against a closed pattern). It never
reads message text, tool names, arguments, results, blobs or ``pass.end.messages``: staged files have passed only the
worker's redactor, not T0's secret scan.

The provisional mapping (§9): ``session.start`` → the Run (agents from the actor tags); ``pass.start`` → a Pass;
``llm.request`` + ``llm.response`` → a ModelInvocation (completed on the response); ``tool.dispatch`` + ``tool.result``
→ a ToolExecution (a ``denied`` result is a Decision); ``decision`` → a Decision; ``pass.end`` closes the pass;
``outcome`` → an Outcome. Edges only where the event ids name both ends (``call``, ``occ``, ``at``, ``input_at``).
"""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from agentprov.errors import IngestError
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads

__all__ = ["BANNER", "MAX_NODES", "CaptureTail", "Delta", "PreviewGraph", "capture_log"]

BANNER: Final = ("Preview: provisional graph from the capture stream. Not corpus provenance; the engine derives the real "
                 "PROV after recording.")
MAX_LINE: Final = 4 * 1024 * 1024
MAX_READ: Final = 1024 * 1024  # per poll
MAX_NODES: Final = 20_000
_ID: Final = re.compile(r"[A-Za-z0-9_.:@-]{1,80}")
_TAG: Final = re.compile(r"[a-z][a-z0-9_]{0,31}")
_STATUS: Final = re.compile(r"[a-z_]{1,32}")
_LIMITS: Final = IngestLimits().replace(max_jsonl_line_bytes=MAX_LINE, max_json_depth=64)


def capture_log(home: Path, session: str) -> Path | None:
    """``$AGENTPROV_HOME/staging/<session>/raw/capture/<session>.capture.jsonl`` for a session id from a ``session``
    progress event; ``None`` when the id is not a plain label (it names a path component)."""
    if not re.fullmatch(r"[0-9a-f-]{8,64}", session):
        return None
    return home / "staging" / session / "raw" / "capture" / f"{session}.capture.jsonl"


class CaptureTail:
    """Complete, chain-checked events of one capture log, as they are appended."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.offset = 0
        self.buffer = b""
        self.prev: str | None = None
        self.stopped: str | None = None  # why the tail stopped (never data)
        self.lines = 0

    def poll(self) -> list[dict[str, Any]]:
        if self.stopped is not None:
            return []
        try:
            with open(self.path, "rb") as fh:
                size = os.fstat(fh.fileno()).st_size
                if size < self.offset:
                    self.stopped = "the log shrank (replaced): the preview stops"
                    return []
                fh.seek(self.offset)
                chunk = fh.read(MAX_READ)
        except FileNotFoundError:
            return []  # not created yet, or removed after the session was stored
        except OSError:
            self.stopped = "the log cannot be read"
            return []
        self.offset += len(chunk)
        data = self.buffer + chunk
        *complete, self.buffer = data.split(b"\n")
        if len(self.buffer) > MAX_LINE:
            self.stopped = "a line is longer than 4 MiB"
            return []
        out = []
        for raw in complete:
            line = raw + b"\n"
            try:
                event = strict_json_loads(raw, _LIMITS, record=True)
            except IngestError as exc:
                self.stopped = f"a line is not strict JSON ({exc.code})"
                break
            if not isinstance(event, dict):
                self.stopped = "a line is not an event object"
                break
            if event.get("prev") != self.prev:
                self.stopped = "the hash chain is broken"
                break
            self.prev = hashlib.sha256(line).hexdigest()
            self.lines += 1
            out.append(event)
        return out


@dataclass(frozen=True, slots=True)
class Delta:
    op: str  # node | edge | close | stopped
    id: str = ""
    kind: str = ""  # run | agent | pass | model | tool | decision | outcome (nodes); edge kinds below
    label: str = ""  # a fixed-vocabulary label built here (never data)
    src: str = ""
    dst: str = ""

    def to_json(self) -> dict[str, str]:
        return {k: v for k, v in (("op", self.op), ("id", self.id), ("kind", self.kind), ("label", self.label),
                                  ("src", self.src), ("dst", self.dst)) if v}


def _id(value: Any) -> str | None:
    return value if isinstance(value, str) and _ID.fullmatch(value) else None


def _ids(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    return [v for v in (value if isinstance(value, list) else [])[:256] if _id(v)]


@dataclass
class PreviewGraph:
    """The provisional graph of one session, grown from envelope metadata (deltas are what is new)."""

    session: str
    nodes: dict[str, str] = field(default_factory=dict)  # id -> kind
    run: str = ""
    current_pass: str = ""
    truncated: bool = False

    def _node(self, nid: str, kind: str, label: str) -> Iterator[Delta]:
        if nid in self.nodes:
            return
        if len(self.nodes) >= MAX_NODES:
            self.truncated = True
            return
        self.nodes[nid] = kind
        yield Delta("node", nid, kind, label)

    def _edge(self, src: str, dst: str, kind: str) -> Iterator[Delta]:
        if src in self.nodes and dst in self.nodes:
            yield Delta("edge", kind=kind, src=src, dst=dst)

    def apply(self, event: dict[str, Any]) -> Iterator[Delta]:
        kind = event.get("type")
        raw = event.get("data")
        data: dict[str, Any] = raw if isinstance(raw, dict) else {}
        p = event.get("pass")
        pass_no = p if isinstance(p, int) and not isinstance(p, bool) and 0 <= p < 10**6 else None
        s = self.session[:8]
        if kind == "session.start":
            self.run = f"{s}:run"
            yield from self._node(self.run, "run", "Run")
            actors = data.get("actors")
            for tag in sorted(actors)[:16] if isinstance(actors, dict) else []:
                if isinstance(tag, str) and _TAG.fullmatch(tag):
                    aid = f"{s}:actor:{tag}"
                    yield from self._node(aid, "agent", f"Agent {tag}")
                    yield from self._edge(self.run, aid, "associated")
        elif kind == "pass.start" and pass_no is not None:
            self.current_pass = f"{s}:pass:{pass_no}"
            yield from self._node(self.current_pass, "pass", f"Pass {pass_no}")
            yield from self._edge(self.current_pass, self.run, "part_of")
        elif kind in ("llm.request", "llm.response"):
            call = _id(data.get("call"))
            if call is None:
                return
            nid = f"{s}:call:{call}"
            if kind == "llm.request":
                n = data.get("n_messages")
                count = f", {n} message(s)" if isinstance(n, int) and not isinstance(n, bool) and 0 <= n < 10**6 else ""
                yield from self._node(nid, "model", f"Model call{count}")
                if self.current_pass:
                    yield from self._edge(nid, self.current_pass, "part_of")
                for occ in _ids(data.get("input_at")):
                    yield from self._edge(nid, f"{s}:occ:{occ}", "used")
            else:
                status = data.get("status")
                label = f"Model call ({status})" if isinstance(status, str) and _STATUS.fullmatch(status) else ""
                yield Delta("close", nid, "model", label)
        elif kind in ("tool.dispatch", "tool.result"):
            occ_id = _id(data.get("occ"))
            if occ_id is None:
                return
            nid = f"{s}:occ:{occ_id}"
            if kind == "tool.dispatch":
                yield from self._node(nid, "tool", "Tool execution")
                if self.current_pass:
                    yield from self._edge(nid, self.current_pass, "part_of")
                at = _id(data.get("at"))
                if at is not None:
                    yield from self._edge(nid, f"{s}:call:{at}", "informed_by")
            else:
                status = data.get("status")
                if status == "denied":
                    yield Delta("close", nid, "decision", "Decision (denied)")
                elif isinstance(status, str) and _STATUS.fullmatch(status):
                    yield Delta("close", nid, "tool", f"Tool execution ({status})")
        elif kind == "decision":
            seq = event.get("seq")
            if isinstance(seq, int) and not isinstance(seq, bool):
                nid = f"{s}:decision:{seq}"
                yield from self._node(nid, "decision", "Decision")
                if self.current_pass:
                    yield from self._edge(nid, self.current_pass, "part_of")
        elif kind == "pass.end" and self.current_pass:
            yield Delta("close", self.current_pass, "pass", "")
            self.current_pass = ""
        elif kind == "outcome":
            nid = f"{s}:outcome"
            yield from self._node(nid, "outcome", "Outcome")
            yield from self._edge(nid, self.run, "generated_by")
        elif kind == "session.end" and self.run:
            status = data.get("status")
            label = f"Run ({status})" if isinstance(status, str) and _STATUS.fullmatch(status) else "Run (ended)"
            yield Delta("close", self.run, "run", label)
