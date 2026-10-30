"""The capture/0.1 hash-chain verifier (C.13.2; K.5.7 item 6).

``verify_chain`` is pure: it takes the raw line bytes and the parsed events (the caller parses; core uses the strict
loader of ``agentprov.ingest``, ``verify_file`` uses the stdlib parser below) and never parses JSON itself. It reports
the **verifiable prefix**, not a pass/fail verdict, because an unsealed or damaged log is kept and its prefix is mapped
(C.13.2): ``n_verified`` events are well-formed and chain-consistent, ``head`` is the hash of the last of them, and
``sealed`` says whether the whole file is a complete, intact session.

A log is sealed iff there is no issue at all and its last event is ``session.end`` whose ``n_events`` equals the
number of lines. Each issue code below is stable; the ``cap`` rule catalogue lists them (``chain.<name>``).

========================================  =====================================================================
``cap.chain.empty``                       no line at all
``cap.chain.bad_json``                    a complete line is not a strict-JSON object (the caller passed ``None``
                                          or a non-object for it)
``cap.chain.not_jcs``                     the line is not ``JCS(event) + LF``
``cap.chain.bad_type``                    ``type`` is outside the 17-name vocabulary (``llm.exchange``, ...)
``cap.chain.bad_envelope``                the envelope has a missing, unknown or ill-typed member (``pass_no``,
                                          ``monotonic_ns``, bad ``ts``, ...)
``cap.chain.seq_gap``                     ``seq`` is not the line index (a line removed, duplicated or reordered)
``cap.chain.prev_mismatch``               ``prev`` is not the SHA-256 of the previous line (including LF); ``prev``
                                          of line 0 is not ``null``. The previous line's integrity is unconfirmed,
                                          so ``n_verified`` excludes it
``cap.chain.bad_first_event``             line 0 is not ``session.start``
``cap.chain.bad_second_event``            line 1 is not ``instrumentation``
``cap.chain.misplaced_event``             ``session.start`` or ``instrumentation`` after their place
``cap.chain.bad_session_start``           ``session.start.data`` has no ``capture: "0.1"`` or no valid ``actors``
``cap.chain.undeclared_actor``            an event's ``actor`` tag is not declared in ``session.start.actors``
``cap.chain.bad_session_end``             ``session.end.data`` is malformed (``status``, ``appended_by``,
                                          ``n_events``, an unknown member such as ``completed`` or ``by``), or a
                                          parent-appended event has a status other than ``aborted``/``errored``
``cap.chain.n_events_mismatch``           ``session.end.n_events`` is not the number of lines up to and including it
``cap.chain.after_end``                   something follows ``session.end`` (more lines or torn bytes)
``cap.chain.torn_tail``                   the final line has no LF (a write was cut short)
``cap.chain.unsealed``                    every complete line verifies but no ``session.end`` ends the log
========================================  =====================================================================

Limits of a chain: it detects accidental damage and edits that were not re-hashed. It cannot detect an edit of the
final line that keeps it well-formed, or a truncation at a line boundary, unless the chain head is recorded elsewhere
(the corpus manifest records it, C.13.2). ``n_verified`` is conservative: when a ``prev`` mismatch is found at line
``k``, line ``k-1`` is either the altered line or the line whose successor was altered, so it is not counted.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import rfc8785

from .errors import CaptureLogError
from .events import ACTOR_TAG_RE, data_problem, envelope_problem

__all__ = [
    "DEFAULT_MAX_BYTES",
    "ISSUE_CODES",
    "ChainIssue",
    "VerifyReport",
    "line_hash",
    "split_lines",
    "strict_loads",
    "verify_chain",
    "verify_file",
]

#: The closed set of codes ``verify_chain`` can report (documented above; listed in the ``cap`` catalogue).
ISSUE_CODES: Final[tuple[str, ...]] = (
    "cap.chain.empty",
    "cap.chain.bad_json",
    "cap.chain.not_jcs",
    "cap.chain.bad_type",
    "cap.chain.bad_envelope",
    "cap.chain.seq_gap",
    "cap.chain.prev_mismatch",
    "cap.chain.bad_first_event",
    "cap.chain.bad_second_event",
    "cap.chain.misplaced_event",
    "cap.chain.bad_session_start",
    "cap.chain.undeclared_actor",
    "cap.chain.bad_session_end",
    "cap.chain.n_events_mismatch",
    "cap.chain.after_end",
    "cap.chain.torn_tail",
    "cap.chain.unsealed",
)

#: ``verify_file`` refuses files larger than this (a session log with inline fixtures is megabytes at most).
DEFAULT_MAX_BYTES: Final = 256 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class ChainIssue:
    """One finding. ``seq`` is the index of the offending line (``None`` for a whole-log finding)."""

    code: str
    seq: int | None
    detail: str


@dataclass(frozen=True, slots=True)
class VerifyReport:
    """Result of a chain verification (see the module docstring for the exact meaning of each member)."""

    sealed: bool
    n_verified: int
    head: str | None
    status: str | None
    appended_by: str | None
    issues: tuple[ChainIssue, ...]

    @property
    def codes(self) -> tuple[str, ...]:
        return tuple(issue.code for issue in self.issues)


def line_hash(line: bytes) -> str:
    """SHA-256 (hex) of a line's bytes including its LF: the ``prev`` of the next line and the chain head."""
    return hashlib.sha256(line).hexdigest()


def split_lines(data: bytes) -> list[bytes]:
    """Split on LF only (never ``splitlines``): lines keep their LF; a final piece without LF (torn) is kept as is."""
    parts = data.split(b"\n")
    lines = [part + b"\n" for part in parts[:-1]]
    if parts[-1]:
        lines.append(parts[-1])
    return lines


def _fail(issues: list[ChainIssue], code: str, seq: int | None, detail: str) -> None:
    issues.append(ChainIssue(code, seq, detail))


def _canonical(event: Any) -> bytes | None:
    try:
        return rfc8785.dumps(event) + b"\n"
    except Exception:  # noqa: BLE001 - any serialisation failure means "not canonical"
        return None


def verify_chain(lines: Sequence[bytes], events: Sequence[Mapping[str, Any] | None]) -> VerifyReport:
    """Verify the hash chain and the structure of a capture log (C.13.2).

    ``lines`` are the raw lines including their LF (a final torn line without LF is passed as is). ``events`` are the
    parsed objects of the **complete** lines, in order; ``None`` marks a complete line the caller could not parse as
    strict JSON. ``ValueError`` when the two sequences do not line up (a caller bug, not a finding).
    """
    n_lines = len(lines)
    torn = n_lines > 0 and not lines[-1].endswith(b"\n")
    n_complete = n_lines - 1 if torn else n_lines
    if len(events) != n_complete or any(not line.endswith(b"\n") for line in lines[:n_complete]):
        raise ValueError("events must be the parsed complete lines (only the last line may lack its LF)")
    issues: list[ChainIssue] = []
    if n_lines == 0:
        _fail(issues, "cap.chain.empty", None, "the log has no line")
        return VerifyReport(False, 0, None, None, None, tuple(issues))

    actors: frozenset[str] = frozenset()
    sealed_at: int | None = None
    n_verified = 0
    failed = False

    for i in range(n_complete):
        line, event = lines[i], events[i]
        if sealed_at is not None:
            extra = n_lines - i
            _fail(issues, "cap.chain.after_end", i, f"{extra} line(s) follow session.end")
            failed = True
            break
        if not isinstance(event, Mapping):
            _fail(issues, "cap.chain.bad_json", i, "line is not a strict-JSON object")
            n_verified, failed = i, True
            break
        if _canonical(event) != line:
            _fail(issues, "cap.chain.not_jcs", i, "line is not JCS(event) followed by LF")
            n_verified, failed = i, True
            break
        problem = envelope_problem(event)
        if problem is not None:
            if problem.startswith("type is not"):
                code = "cap.chain.bad_type"
            elif problem.startswith("prev"):
                code = "cap.chain.prev_mismatch"
            else:
                code = "cap.chain.bad_envelope"
            _fail(issues, code, i, problem)
            n_verified = max(i - 1, 0) if code == "cap.chain.prev_mismatch" else i
            failed = True
            break
        if event["seq"] != i:
            _fail(issues, "cap.chain.seq_gap", i, f"expected seq {i}, found {event['seq']}")
            n_verified, failed = i, True
            break
        if i > 0 and event["prev"] != line_hash(lines[i - 1]):
            _fail(issues, "cap.chain.prev_mismatch", i, f"prev does not match the hash of line {i - 1}")
            n_verified, failed = max(i - 1, 0), True
            break
        kind: str = event["type"]
        data: Mapping[str, Any] = event["data"]
        if i == 0:
            if kind != "session.start":
                _fail(issues, "cap.chain.bad_first_event", i, "the first event must be session.start")
                n_verified, failed = i, True
                break
            declared = data.get("actors")
            if (
                data.get("capture") != "0.1"
                or not isinstance(declared, Mapping)
                or not declared
                or not all(isinstance(tag, str) and ACTOR_TAG_RE.fullmatch(tag) for tag in declared)
            ):
                _fail(issues, "cap.chain.bad_session_start", i, "session.start needs capture 0.1 and declared actors")
                n_verified, failed = i, True
                break
            actors = frozenset(declared)
        elif i == 1:
            if kind != "instrumentation":
                _fail(issues, "cap.chain.bad_second_event", i, "the second event must be instrumentation")
                n_verified, failed = i, True
                break
        elif kind in ("session.start", "instrumentation"):
            _fail(issues, "cap.chain.misplaced_event", i, f"{kind} is only valid at its fixed place")
            n_verified, failed = i, True
            break
        actor = event["actor"]
        if actor is not None and actor not in actors:
            _fail(issues, "cap.chain.undeclared_actor", i, f"actor {actor!r} is not declared in session.start")
            n_verified, failed = i, True
            break
        if kind == "session.end":
            problem = data_problem("session.end", data)
            if problem is None and data["appended_by"] == "parent" and data["status"] not in ("aborted", "errored"):
                problem = "a parent-appended session.end has status aborted or errored"
            if problem is not None:
                _fail(issues, "cap.chain.bad_session_end", i, problem)
                n_verified, failed = i, True
                break
            if data["n_events"] != i + 1:
                _fail(
                    issues,
                    "cap.chain.n_events_mismatch",
                    i,
                    f"session.end declares {data['n_events']} events, the log has {i + 1} up to it",
                )
                n_verified, failed = i, True
                break
            sealed_at = i
        n_verified = i + 1

    if not failed:
        if torn:
            if sealed_at is not None:
                _fail(issues, "cap.chain.after_end", n_complete, "torn bytes follow session.end")
            else:
                _fail(issues, "cap.chain.torn_tail", n_complete, "the final line has no LF")
        if sealed_at is None:
            _fail(issues, "cap.chain.unsealed", None, "the log has no terminal session.end")

    sealed = sealed_at is not None and not issues
    head = line_hash(lines[n_verified - 1]) if n_verified > 0 else None
    status = appended_by = None
    if sealed:
        end_data = events[sealed_at]["data"]  # type: ignore[index]
        status, appended_by = end_data["status"], end_data["appended_by"]
    return VerifyReport(sealed, n_verified, head, status, appended_by, tuple(issues))


# ---------------------------------------------------------------------------------------------------------------
# verify_file and the stdlib strict parser


_SURROGATE_ESCAPE: Final = re.compile(r"\\[uU][dD][89a-fA-F]")
#: Maximum container nesting (``[[]]`` has depth 2), as core's ``ingest.limits.Limits.max_json_depth``.
MAX_JSON_DEPTH: Final = 256
# Strings are skipped, brackets are structural; an unterminated string stops the scan (``json.loads`` rejects it).
_TOKEN: Final = re.compile(rb'"[^"\\]*(?:\\.[^"\\]*)*"|([\[\]{}])|(")', re.DOTALL)


def _too_deep(line: bytes, max_depth: int = MAX_JSON_DEPTH) -> bool:
    """Byte-level nesting pre-scan, never recursing (the twin of core's ``ingest.loaders._prescan_depth``). The
    parser's own ``RecursionError`` cannot be the bound: how deep CPython's C scanner goes depends on the platform's
    stack (100,000 levels parse on Linux with Python 3.14)."""
    depth = 0
    for m in _TOKEN.finditer(line):
        bracket = m.group(1)
        if bracket is None:
            if m.group(2) is not None:
                return False
            continue
        if bracket in (b"[", b"{"):
            depth += 1
            if depth > max_depth:
                return True
        else:
            depth -= 1
    return False


def _object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate object key")
        out[key] = value
    return out


def _reject_constant(name: str) -> Any:
    raise ValueError(f"non-finite number literal {name}")


def _finite_float(text: str) -> float:
    value = float(text)
    if value in (float("inf"), float("-inf")):
        raise ValueError("float overflow")
    return value


def _has_lone_surrogate(value: Any) -> bool:
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, str):
            try:
                item.encode("utf-8")
            except UnicodeEncodeError:
                return True
        elif isinstance(item, dict):
            stack.extend(item.keys())
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    return False


def strict_loads(line: bytes) -> dict[str, Any] | None:
    """Strict JSON-object parse of one line (without its LF) or ``None``.

    Rejects invalid UTF-8, a BOM, duplicate keys, ``NaN``/``Infinity``/overflowing floats, lone surrogates, excessive
    nesting and any top-level value that is not an object. (Core uses ``agentprov.ingest`` instead; this stdlib twin
    exists so backends and tests can verify a file without the core.)
    """
    if _too_deep(line):
        return None
    try:
        text = line.decode("utf-8")
        value = json.loads(
            text, object_pairs_hook=_object_pairs, parse_constant=_reject_constant, parse_float=_finite_float
        )
        if not isinstance(value, dict):
            return None
        if _SURROGATE_ESCAPE.search(text) and _has_lone_surrogate(value):
            return None
        return value
    except (ValueError, RecursionError):  # UnicodeDecodeError and JSONDecodeError are ValueErrors
        return None


def verify_file(path: Path, *, max_bytes: int = DEFAULT_MAX_BYTES) -> VerifyReport:
    """Read ``path`` (bounded by ``max_bytes``), parse it strictly and run :func:`verify_chain`.

    ``CaptureLogError`` (``cap.verify.too_large``) when the file exceeds ``max_bytes``.
    """
    with open(path, "rb") as handle:
        data = handle.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise CaptureLogError(f"capture log exceeds {max_bytes} bytes", code="cap.verify.too_large")
    lines = split_lines(data)
    n_complete = len(lines) - (1 if lines and not lines[-1].endswith(b"\n") else 0)
    events = [strict_loads(line[:-1]) for line in lines[:n_complete]]
    return verify_chain(lines, events)

