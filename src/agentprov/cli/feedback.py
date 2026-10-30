"""Live feedback for long-running commands (docs/architecture MN N.1.14; DECISIONS D-8).

Feedback is a channel of its own, separate from logging (N.1.12): ``--progress`` sets how much the user sees on stderr
while the work runs, ``-v``/``-q`` set the log level. This module is the core side of N.1.14: the levels, the
renderers, the throttling and the ``agentprov-progress/0.2`` JSON-lines writer. Library code reports through the small
sink interface of :mod:`agentprov.progress`; the sink defined here (:class:`FeedbackSink`) is what the CLI installs.

Design (the guarantees of N.1.14(4) hold by construction):

* **F2, no back-pressure.** ``FeedbackSink.emit`` does O(1) work in the caller's thread: it trims the event, updates a
  few counters under a short lock and calls ``Queue.put_nowait`` on a bounded queue of 4,096 items. When the queue is
  full the event is dropped and counted; the caller never waits. A dedicated daemon thread (``agentprov-feedback``)
  drains the queue and does all formatting and writing, so a stalled terminal, pipe or ``--progress-file`` can only
  delay the display. One thread serves the terminal renderer and the optional file writer, so a stalled file also
  delays the terminal; that is "delaying only the display" and is accepted.
* **Authoritative counters are kept on the producer side.** The unit counts, the issue-code histogram, the current
  unit and the drop count live in the sink (updated in ``emit``), not in the queued events. A dropped event therefore
  loses at most a line of display, never a count in the end-of-run table.
* **Throttling.** The ``tty`` renderer redraws its single status line at most 10 times a second and prints step
  lines above it. The ``plain`` renderer prints a status line at most every 10 s or every 500 units. Both read an
  injectable monotonic clock, so the rate limits are tested without sleeping.
* **No ANSI unless interactive.** ``tty`` is chosen only for a terminal whose ``TERM`` is not ``dumb``; an explicit
  ``--progress-format tty`` on anything else degrades to ``plain``. Plain and JSON-lines output contain no escape
  sequence of ours, and every data-derived string is passed through ``escape_untrusted`` first, so control characters
  in untrusted text cannot reach the terminal (N.1.13).
* **Content only on request.** Events carry content in a separate field; it is dropped at the door unless
  ``--show-content`` is set, then shown through ``quote_untrusted`` truncated to ``--content-chars``. The excerpt
  source is capped at 8,192 characters before it is queued, to bound the queue's memory.
* **F1, F4.** Nothing here is read by a pipeline decision, and the sink holds no reference the producer's results
  depend on. The drop count is reported in the end-of-run table and the JSON-lines ``end`` event, never in the
  ``agentprov-cli-summary`` document (which must be byte-stable, N.1.4(3)).
"""

from __future__ import annotations

import os
import queue
import shutil
import threading
import time
import uuid
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import IO, Any, Final, NamedTuple, Protocol

from agentprov.errors import AgentProvError
from agentprov.ingest.quote import quote_untrusted
from agentprov.io.canonical import jcs_bytes
from agentprov.progress import FieldValue, ProgressEvent

__all__ = [
    "CONTENT_CHARS_DEFAULT",
    "CONTENT_CHARS_MAX",
    "FILE_MIN_LEVEL",
    "FORMATS",
    "KIND_LEVEL",
    "LEVELS",
    "PLAIN_MIN_INTERVAL_S",
    "PLAIN_MIN_UNITS",
    "PROGRESS_FORMAT_ID",
    "QUEUE_SIZE",
    "TTY_MIN_INTERVAL_S",
    "FeedbackConfig",
    "FeedbackConfigError",
    "FeedbackSink",
    "JsonlRenderer",
    "PlainRenderer",
    "Snapshot",
    "TtyRenderer",
    "format_status",
    "format_summary",
    "is_interactive",
    "make_sink",
    "open_progress_file",
    "resolve_feedback_config",
]

LEVELS: Final[tuple[str, ...]] = ("off", "summary", "status", "steps", "trace")
FORMATS: Final[tuple[str, ...]] = ("auto", "tty", "plain", "jsonl")
#: The minimum level at which each event kind is queued for display (N.1.14(1)).
KIND_LEVEL: Final[Mapping[str, str]] = {
    "start": "summary",
    "unit_start": "status",
    "unit_done": "status",
    "step": "steps",
    "trace": "trace",
    "stage": "status",
    "worker": "status",
    "session": "status",
    "control": "summary",
}
#: ``--progress-interval`` and ``--progress-max-bytes`` defaults (D-393).
HEARTBEAT_INTERVAL_S: Final = 2.0
PROGRESS_MAX_BYTES: Final = 8 * 1024 * 1024
_MAX_STAGES: Final = 64
_MAX_PIDS: Final = 512
_HEARTBEAT_ISSUES: Final = 10
PROGRESS_FORMAT_ID: Final = "agentprov-progress/0.2"  # D-393: a superset of 0.1 (the 0.1 events keep their shape)
#: The ``--progress-file`` shows at least this level (``--progress`` can raise it, never lower it).
FILE_MIN_LEVEL: Final = "status"
QUEUE_SIZE: Final = 4096
TTY_MIN_INTERVAL_S: Final = 0.1  # at most 10 status redraws a second (N.1.14(2))
PLAIN_MIN_INTERVAL_S: Final = 10.0  # at most one plain status line every 10 s ...
PLAIN_MIN_UNITS: Final = 500  # ... or every 500 units (N.1.12(4))
CONTENT_CHARS_DEFAULT: Final = 200
CONTENT_CHARS_MAX: Final = 2000
_CONTENT_SOURCE_CAP: Final = 8192
_MAX_ISSUE_CODES: Final = 1000  # distinct codes tracked; further ones count as "<other>"
_MAX_STATUSES: Final = 50
_FIELD_STR_CAP: Final = 256
_JOIN_TIMEOUT_S: Final = 2.0
_KNOWN_STATUS_ORDER: Final = ("sealed", "sealed_with_issues", "ok", "failed", "refused")
_CLEAR_LINE: Final = "\r\x1b[2K"
_RESERVED_KEYS: Final = frozenset(
    {"v", "ts", "level", "event", "unit", "status", "stage", "duration_s", "total", "codes", "content", "seq", "run"}
)


class FeedbackConfigError(AgentProvError):
    """An invalid feedback option or environment value. Exit 2 (usage)."""

    code = "cli.usage.progress"
    exit_code = 2


def _rank(level: str) -> int:
    return LEVELS.index(level)


def _safe(value: object, max_chars: int = 500) -> str:
    from agentprov.cli.common import safe_text

    return safe_text(value, max_chars=max_chars)


# --------------------------------------------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FeedbackConfig:
    """Resolved feedback settings. ``fmt`` is concrete (``tty``, ``plain`` or ``jsonl``), never ``auto``."""

    level: str
    fmt: str
    progress_file: str | None = None
    show_content: bool = False
    content_chars: int = CONTENT_CHARS_DEFAULT
    progress_interval: float = HEARTBEAT_INTERVAL_S
    progress_max_bytes: int = PROGRESS_MAX_BYTES
    #: Fields of the ``run`` header line (command, mode, dry_run, jobs, corpus_root, summary), already safe text.
    header: Mapping[str, FieldValue] = field(default_factory=dict)


def is_interactive(stream: object, env: Mapping[str, str]) -> bool:
    """A terminal whose ``TERM`` is not ``dumb`` (N.1.14(2); D-7: ``isatty`` plus ``TERM``, no platform branch)."""
    isatty = getattr(stream, "isatty", None)
    if isatty is None:
        return False
    try:
        tty = bool(isatty())
    except (ValueError, OSError):
        return False
    return tty and env.get("TERM") != "dumb"


def resolve_feedback_config(
    *,
    progress: str | None,
    progress_format: str | None,
    progress_file: str | None,
    show_content: bool,
    content_chars: int | None,
    quiet: bool,
    env: Mapping[str, str],
    stream: object,
    progress_interval: float = HEARTBEAT_INTERVAL_S,
    progress_max_bytes: int = PROGRESS_MAX_BYTES,
    header: Mapping[str, FieldValue] | None = None,
) -> FeedbackConfig:
    """Apply N.1.2's defaults. Precedence for the level: ``--progress``, then ``AGENTPROV_PROGRESS`` (which counts as
    giving ``--progress``), then ``-q`` (``off``), then ``status`` on an interactive stderr and ``summary`` otherwise.
    """
    interactive = is_interactive(stream, env)
    chosen = progress
    if chosen is None:
        env_value = env.get("AGENTPROV_PROGRESS")
        if env_value:
            chosen = env_value
    if chosen is None:
        chosen = "off" if quiet else ("status" if interactive else "summary")
    if chosen not in LEVELS:
        raise FeedbackConfigError(f"invalid progress level {_safe(chosen, 40)!r}; choose one of {', '.join(LEVELS)}")
    fmt = progress_format or "auto"
    if fmt not in FORMATS:
        raise FeedbackConfigError(f"invalid progress format {_safe(fmt, 40)!r}; choose one of {', '.join(FORMATS)}")
    if fmt == "auto":
        fmt = "tty" if interactive else "plain"
    elif fmt == "tty" and not interactive:
        fmt = "plain"  # the tty renderer never emits ANSI when the stream is not an interactive terminal
    chars = CONTENT_CHARS_DEFAULT if content_chars is None else content_chars
    if not 1 <= chars <= CONTENT_CHARS_MAX:
        raise FeedbackConfigError(f"--content-chars must be between 1 and {CONTENT_CHARS_MAX}")
    return FeedbackConfig(chosen, fmt, progress_file, show_content, chars, progress_interval, progress_max_bytes,
                          dict(header or {}))


def open_progress_file(path: str) -> IO[str]:
    """Open ``--progress-file`` for appending (D-393: a resumed job extends its own history; each process start writes a
    new ``run`` line): UTF-8, ``\\n`` line ends (no platform translation), line buffered."""
    try:
        return open(path, "a", encoding="utf-8", newline="\n", buffering=1)  # noqa: SIM115 - closed by the sink
    except OSError as exc:
        raise FeedbackConfigError(f"cannot open --progress-file: {_safe(exc.strerror or exc.__class__.__name__, 80)}") from None


# --------------------------------------------------------------------------------------------------------------
# State, items, formatting
# --------------------------------------------------------------------------------------------------------------


class _Item(NamedTuple):
    kind: str
    wall: float
    mono: float
    event: ProgressEvent
    seq: int | None = None


@dataclass(frozen=True, slots=True)
class Snapshot:
    """A consistent copy of the sink's counters (taken under its lock)."""

    command: str
    total: int | None
    done: int
    counts: tuple[tuple[str, int], ...]
    issues: tuple[tuple[str, int], ...]
    current: str | None
    started: float
    dropped: int


def _fmt_duration(seconds: float | None) -> str:
    if seconds is None or seconds != seconds or seconds < 0:
        return "-"
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, rest = divmod(int(seconds), 60)
    if minutes < 60:
        return f"{minutes}m{rest:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m"


def _fmt_value(value: FieldValue) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.3g}"
    if isinstance(value, int):
        return str(value)
    return _safe(value, 80)


def _fmt_fields(fields: Mapping[str, FieldValue], *, skip: tuple[str, ...] = ()) -> str:
    return " ".join(f"{_safe(k, 40)}={_fmt_value(v)}" for k, v in sorted(fields.items()) if k not in skip)


def _order_counts(counts: Mapping[str, int]) -> tuple[tuple[str, int], ...]:
    known = [(s, counts[s]) for s in _KNOWN_STATUS_ORDER if s in counts]
    rest = sorted((s, n) for s, n in counts.items() if s not in _KNOWN_STATUS_ORDER)
    return tuple(known + rest)


def _counts_text(counts: tuple[tuple[str, int], ...]) -> str:
    return ", ".join(f"{_safe(s, 40)} {n}" for s, n in counts) if counts else "none"


def format_status(snap: Snapshot, now: float) -> str:
    """The one-line status: done/total, percentage, rate, ETA, elapsed, counters and the current unit (N.1.14(1))."""
    elapsed = max(0.0, now - snap.started)
    parts = [_safe(snap.command or "agentprov", 40)]
    if snap.total:
        pct = 100.0 * snap.done / snap.total
        parts.append(f"{snap.done}/{snap.total} {pct:.0f}%")
    else:
        parts.append(f"{snap.done} done")
    if snap.done and elapsed > 0:
        rate = snap.done / elapsed
        parts.append(f"{rate:.1f}/s")
        if snap.total and snap.total > snap.done:
            parts.append(f"ETA {_fmt_duration((snap.total - snap.done) / rate)}")
    parts.append(f"elapsed {_fmt_duration(elapsed)}")
    if snap.counts:
        parts.append(_counts_text(snap.counts))
    if snap.current:
        parts.append(f"cur {_safe(snap.current, 60)}")
    return " | ".join(parts)


def format_summary(snap: Snapshot, now: float, exit_code: int | None, *, show_drops: bool) -> list[str]:
    """The end-of-run summary table (counts by status, issue codes, wall time; N.1.14(1))."""
    suffix = "" if exit_code is None else f" (exit {exit_code})"
    lines = [f"{_safe(snap.command or 'agentprov', 40)}: finished in {_fmt_duration(now - snap.started)}{suffix}"]
    if snap.counts or snap.total:
        total = snap.total if snap.total is not None else snap.done
        lines.append(f"  units    {snap.done} of {total}: {_counts_text(snap.counts)}")
    if snap.issues:
        lines.append("  issues   " + ", ".join(f"{_safe(c, 80)} x{n}" for c, n in snap.issues[:12]))
        if len(snap.issues) > 12:
            lines.append(f"           ... and {len(snap.issues) - 12} more codes")
    if show_drops or snap.dropped:
        lines.append(f"  dropped  {snap.dropped} feedback events (display only; results are unaffected)")
    return lines


def _format_item(item: _Item, cfg: FeedbackConfig) -> list[str]:
    """The text lines for an event at the configured level (empty when the event is only a state update)."""
    ev = item.event
    level = _rank(cfg.level)
    lines: list[str] = []
    if ev.kind == "start":
        parts = [f"agentprov {_safe(ev.fields.get('command') or 'run', 40)}"]
        label = ev.fields.get("source") or ev.fields.get("backend")
        if label:
            parts.append(_safe(label, 60))
        banner = " ".join(parts)
        detail = _fmt_fields(ev.fields, skip=("command", "source", "backend"))
        if ev.total is not None:
            detail = f"units={ev.total} {detail}"
        detail = detail.strip()
        lines.append(f"{banner}: {detail}" if detail else banner)
    elif ev.kind == "unit_done" and level >= _rank("steps"):
        text = f"  unit {_safe(ev.status or '-', 40)} {_safe(ev.unit or '-', 80)} {_fmt_duration(ev.duration_s)}"
        if ev.codes:
            text += " codes: " + ", ".join(_safe(c, 80) for c in ev.codes[:8])
        extra = _fmt_fields(ev.fields) if level >= _rank("trace") else ""
        lines.append(f"{text} {extra}".rstrip())
    elif ev.kind == "step" and level >= _rank("steps"):
        text = f"  step {_safe(ev.stage or '-', 40)} {_safe(ev.unit or '-', 80)} {_fmt_duration(ev.duration_s)}"
        extra = _fmt_fields(ev.fields)
        lines.append(f"{text} {extra}".rstrip())
        lines.extend(_content_lines(ev, cfg))
    elif ev.kind == "trace" and level >= _rank("trace"):
        head = f"  trace {_safe(ev.stage or '-', 40)}"
        if ev.unit:
            head += f" {_safe(ev.unit, 80)}"
        lines.append(f"{head} {_fmt_fields(ev.fields)}".rstrip())
        lines.extend(_content_lines(ev, cfg))
    return lines


def _content_lines(ev: ProgressEvent, cfg: FeedbackConfig) -> list[str]:
    if not cfg.show_content or ev.content is None:
        return []
    return quote_untrusted(ev.content, ev.locator or "-", max_chars=cfg.content_chars).split("\n")


# --------------------------------------------------------------------------------------------------------------
# Renderers
# --------------------------------------------------------------------------------------------------------------


class _Output(Protocol):
    def write(self, s: str, /) -> Any: ...
    def flush(self) -> Any: ...


class _Renderer(Protocol):
    def event(self, item: _Item, snapshot: Callable[[], Snapshot]) -> None: ...
    def tick(self, now: float, snapshot: Callable[[], Snapshot]) -> None: ...
    def finish(self, snap: Snapshot, now: float, exit_code: int | None) -> None: ...


class PlainRenderer:
    """Append-only lines. A status line at most every 10 s or every 500 units; step lines as they arrive."""

    def __init__(
        self,
        out: _Output,
        cfg: FeedbackConfig,
        *,
        min_interval_s: float = PLAIN_MIN_INTERVAL_S,
        min_units: int = PLAIN_MIN_UNITS,
        start: float = 0.0,
    ) -> None:
        self._out = out
        self._cfg = cfg
        self._min_interval = min_interval_s
        self._min_units = min_units
        self._last_status = start
        self._last_done = 0

    def _line(self, text: str) -> None:
        self._out.write(text + "\n")
        self._out.flush()

    def event(self, item: _Item, snapshot: Callable[[], Snapshot]) -> None:
        for text in _format_item(item, self._cfg):
            self._line(text)
        self._maybe_status(item.mono, snapshot)

    def tick(self, now: float, snapshot: Callable[[], Snapshot]) -> None:
        self._maybe_status(now, snapshot)

    def _maybe_status(self, now: float, snapshot: Callable[[], Snapshot]) -> None:
        if _rank(self._cfg.level) < _rank("status"):
            return
        snap = snapshot()
        due = now - self._last_status >= self._min_interval or snap.done - self._last_done >= self._min_units
        if not due or not (snap.command or snap.done or snap.current):
            return
        self._line(format_status(snap, now))
        self._last_status, self._last_done = now, snap.done

    def finish(self, snap: Snapshot, now: float, exit_code: int | None) -> None:
        for text in format_summary(snap, now, exit_code, show_drops=_rank(self._cfg.level) >= _rank("trace")):
            self._line(text)


class TtyRenderer:
    """One status line redrawn in place at most 10 times a second; step lines are printed above it (N.1.14(2))."""

    def __init__(
        self,
        out: _Output,
        cfg: FeedbackConfig,
        *,
        columns: Callable[[], int] | None = None,
        min_interval_s: float = TTY_MIN_INTERVAL_S,
    ) -> None:
        self._out = out
        self._cfg = cfg
        self._columns = columns or (lambda: shutil.get_terminal_size((80, 24)).columns)
        self._min_interval = min_interval_s
        self._last_draw = float("-inf")
        self._dirty = False
        self._visible = False

    def _write(self, text: str) -> None:
        self._out.write(text)
        self._out.flush()

    def _erase(self) -> str:
        if self._visible:
            self._visible = False
            return _CLEAR_LINE
        return ""

    def event(self, item: _Item, snapshot: Callable[[], Snapshot]) -> None:
        lines = _format_item(item, self._cfg)
        if lines:
            self._write(self._erase() + "\n".join(lines) + "\n")
        if _rank(self._cfg.level) >= _rank("status"):
            self._dirty = True
        self.tick(item.mono, snapshot)

    def tick(self, now: float, snapshot: Callable[[], Snapshot]) -> None:
        if not self._dirty or _rank(self._cfg.level) < _rank("status"):
            return
        if now - self._last_draw < self._min_interval:
            return
        text = format_status(snapshot(), now)
        width = max(10, self._columns() - 1)
        if len(text) > width:
            text = text[: width - 1] + "~"
        self._write(_CLEAR_LINE + text)
        self._visible, self._dirty, self._last_draw = True, False, now

    def finish(self, snap: Snapshot, now: float, exit_code: int | None) -> None:
        lines = format_summary(snap, now, exit_code, show_drops=_rank(self._cfg.level) >= _rank("trace"))
        self._write(self._erase() + "\n".join(lines) + "\n")


class JsonlRenderer:
    """One ``agentprov-progress/0.2`` JSON object per event (``{"v", "ts", "seq", "run", "level", "event", ...}``).

    Every data-derived string is passed through ``escape_untrusted``; ``content`` appears only with ``--show-content``
    and then fenced by ``quote_untrusted``. The JSON text is RFC 8785 canonical, one object per line. 0.2 (D-393) adds
    ``seq`` (assigned when the event is queued, so a gap means a dropped event) and the run id to every line, the
    ``run`` header line, ``heartbeat`` snapshots and ``end.outcome``; the 0.1 events keep their shape.

    With ``path`` and ``max_bytes`` (the ``--progress-file``) the file is rotated past ``max_bytes``: it becomes
    ``<path>.1`` (replacing an older one) and the new file starts with a ``run`` line (next ``segment``) and a
    ``heartbeat``, so a reader that opens the current file never needs ``.1``.
    """

    def __init__(self, out: _Output, cfg: FeedbackConfig, *, wall: Callable[[], float] = time.time, run_id: str = "",
                 next_seq: Callable[[], int] | None = None, path: str | None = None, max_bytes: int | None = None,
                 on_rotate: Callable[[JsonlRenderer], None] | None = None) -> None:
        self._out = out
        self._cfg = cfg
        self._wall = wall
        self._run_id = run_id
        self._next_seq = next_seq
        self._path = path
        self._max_bytes = max_bytes
        self._on_rotate = on_rotate
        self._written = 0
        self.segment = 0
        if path is not None:
            try:
                self._written = os.path.getsize(path)
            except OSError:
                self._written = 0

    def _put(self, obj: dict[str, Any]) -> None:
        line = jcs_bytes(obj).decode("utf-8") + "\n"
        self._out.write(line)
        self._out.flush()
        self._written += len(line.encode("utf-8"))
        if self._max_bytes is not None and self._path is not None and self._written > self._max_bytes:
            self._rotate()

    def _rotate(self) -> None:
        assert self._path is not None
        close = getattr(self._out, "close", None)
        if callable(close):
            close()
        os.replace(self._path, self._path + ".1")
        self._out = open_progress_file(self._path)
        self._written = 0
        self.segment += 1
        if self._on_rotate is not None:
            self._on_rotate(self)  # the new segment's run line and an immediate heartbeat

    def close(self) -> None:
        close = getattr(self._out, "close", None)
        if callable(close):
            close()

    @staticmethod
    def _ts(wall: float) -> str:
        return datetime.fromtimestamp(wall, UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def _head(self, wall: float, level: str, event: str, seq: int | None) -> dict[str, Any]:
        obj: dict[str, Any] = {"v": PROGRESS_FORMAT_ID, "ts": self._ts(wall), "level": level, "event": event}
        if seq is not None:
            obj["seq"] = seq
        if self._run_id:
            obj["run"] = self._run_id
        return obj

    def _own_seq(self) -> int | None:
        return self._next_seq() if self._next_seq is not None else None

    def begin(self, header: Mapping[str, FieldValue], seq: int | None = None) -> None:
        """The ``run`` header line, first in every file segment (``seq`` 0 for the first one)."""
        obj = self._head(self._wall(), "summary", "run", seq if seq is not None else self._own_seq())
        obj["segment"] = self.segment
        for key, value in header.items():
            name = _safe(key, 60)
            if name not in obj:
                obj[name] = _safe(value, 500) if isinstance(value, str) else value
        self._put(obj)

    def heartbeat(self, snapshot: Mapping[str, Any]) -> None:
        """An absolute snapshot (counters, stages, workers, queue, drops): a reader that joins late recovers from it."""
        obj = self._head(self._wall(), "status", "heartbeat", self._own_seq())
        obj.update(snapshot)
        self._put(obj)

    def event(self, item: _Item, snapshot: Callable[[], Snapshot]) -> None:
        ev = item.event
        obj = self._head(item.wall, KIND_LEVEL[ev.kind], ev.kind, item.seq)
        for key, value in (("unit", ev.unit), ("status", ev.status), ("stage", ev.stage)):
            if value is not None:
                obj[key] = _safe(value, 500)
        if ev.duration_s is not None and ev.duration_s == ev.duration_s and abs(ev.duration_s) != float("inf"):
            obj["duration_s"] = round(ev.duration_s, 6)
        if ev.total is not None:
            obj["total"] = ev.total
        if ev.codes:
            obj["codes"] = [_safe(c, 200) for c in ev.codes[:50]]
        for key, raw in ev.fields.items():
            name = _safe(key, 60)
            name = f"field_{name}" if name in _RESERVED_KEYS else name
            if isinstance(raw, float) and (raw != raw or abs(raw) == float("inf")):
                obj[name] = None
            else:
                obj[name] = _safe(raw, 500) if isinstance(raw, str) else raw
        if self._cfg.show_content and ev.content is not None:
            obj["content"] = quote_untrusted(ev.content, ev.locator or "-", max_chars=self._cfg.content_chars)
        self._put(obj)

    def tick(self, now: float, snapshot: Callable[[], Snapshot]) -> None:
        return None

    def finish(self, snap: Snapshot, now: float, exit_code: int | None, outcome: str | None = None) -> None:
        obj = self._head(self._wall(), "summary", "end", self._own_seq())
        obj.update({
            "elapsed_s": round(max(0.0, now - snap.started), 3),
            "units_done": snap.done,
            "counts": {_safe(s, 40): n for s, n in snap.counts},
            "issues": {_safe(c, 80): n for c, n in snap.issues},
            "dropped": snap.dropped,
        })
        if snap.total is not None:
            obj["total"] = snap.total
        if exit_code is not None:
            obj["exit_code"] = exit_code
        if outcome is not None:
            obj["outcome"] = outcome
        summary = self._cfg.header.get("summary")
        if isinstance(summary, str):
            obj["summary"] = _safe(summary, 500)
        self._put(obj)


# --------------------------------------------------------------------------------------------------------------
# The sink
# --------------------------------------------------------------------------------------------------------------


class FeedbackSink:
    """The :class:`agentprov.progress.Progress` implementation the CLI installs. See the module docstring.

    ``out`` is the stderr stream. ``file`` (optional, from :func:`open_progress_file`) additionally receives every
    event as JSON lines; the sink closes it. ``clock`` (monotonic) and ``wall`` (epoch seconds) are injectable.
    ``start_thread=False`` leaves the queue undrained until :meth:`pump` is called (deterministic tests).

    ``agentprov-progress/0.2`` (D-393): a run id (UUIDv7) and a ``seq`` on every JSON line, a ``run`` header first in
    every file segment, a ``heartbeat`` snapshot every ``cfg.progress_interval`` seconds and at each ``stage`` end,
    rotation of the file past ``cfg.progress_max_bytes``, and ``end.outcome``. The snapshot's counters live on the
    producer side, like the end-of-run table's, so a dropped event never loses a count.
    """

    def __init__(
        self,
        cfg: FeedbackConfig,
        out: _Output,
        *,
        file: IO[str] | None = None,
        clock: Callable[[], float] = time.monotonic,
        wall: Callable[[], float] = time.time,
        queue_size: int = QUEUE_SIZE,
        columns: Callable[[], int] | None = None,
        start_thread: bool = True,
        tick_s: float = 0.05,
        stderr: bool = True,
        run_id: str | None = None,
    ) -> None:
        self._cfg = cfg
        self._clock = clock
        self._wall = wall
        self._tick_s = tick_s
        self._level_rank = _rank(cfg.level)
        self._queue: queue.Queue[_Item] = queue.Queue(maxsize=queue_size)
        self._lock = threading.Lock()
        self._dropped = 0
        self._command = ""
        self._total: int | None = None
        self._done = 0
        self._counts: Counter[str] = Counter()
        self._issues: Counter[str] = Counter()
        self._current: str | None = None
        self._started = clock()
        self._stop = threading.Event()
        self._closed = False
        self._exit_code: int | None = None
        self._outcome: str | None = None
        self._file = file
        self.run_id = run_id if run_id is not None else str(uuid.uuid7())
        self._seq = 0
        self._stages: dict[str, dict[str, Any]] = {}
        self._pids: set[int] = set()
        self._workers_configured: int | None = None
        self._heartbeat_due = False
        self._last_heartbeat = self._started
        self._begun = False
        #: Each output with the highest level it shows. The ``--progress-file`` records at least ``status`` (unit events),
        #: whatever stderr shows: a job manager reads the file while stderr is a log at ``summary`` or ``off``.
        self._renderers: list[tuple[_Renderer, int]] = []
        self._jsonl: list[JsonlRenderer] = []
        stderr_rank = self._level_rank if stderr else 0
        if stderr_rank > 0:
            if cfg.fmt == "jsonl":
                renderer = JsonlRenderer(out, cfg, wall=wall, run_id=self.run_id, next_seq=self._take_seq)
                self._jsonl.append(renderer)
                self._renderers.append((renderer, stderr_rank))
            elif cfg.fmt == "tty":
                self._renderers.append((TtyRenderer(out, cfg, columns=columns), stderr_rank))
            else:
                self._renderers.append((PlainRenderer(out, cfg, start=self._started), stderr_rank))
        file_rank = 0
        if file is not None:
            file_rank = max(self._level_rank, _rank(FILE_MIN_LEVEL))
            renderer = JsonlRenderer(file, cfg, wall=wall, run_id=self.run_id, next_seq=self._take_seq,
                                     path=cfg.progress_file, max_bytes=cfg.progress_max_bytes, on_rotate=self._rotated)
            self._jsonl.append(renderer)
            self._renderers.append((renderer, file_rank))
        #: Events up to this rank get a ``seq`` when queued (the file's level, else stderr's): a gap is a drop.
        self._seq_rank = file_rank or (stderr_rank if self._jsonl else 0)
        self._header_seq = self._take_seq() if self._jsonl else None  # the run line is seq 0, whenever it is written
        self._level_rank = max((rank for _, rank in self._renderers), default=0)
        self._broken: set[int] = set()
        self._thread: threading.Thread | None = None
        if start_thread and self._level_rank > 0:
            self._thread = threading.Thread(target=self._run, name="agentprov-feedback", daemon=True)
            self._thread.start()

    # -- producer side: O(1), never blocks --------------------------------------------------------------------

    @property
    def dropped(self) -> int:
        return self._dropped

    def _take_seq(self) -> int:
        with self._lock:
            seq = self._seq
            self._seq += 1
            return seq

    def emit(self, event: ProgressEvent) -> None:
        """Record ``event``. Constant work: trim, count, ``put_nowait``. Never blocks, never raises."""
        if self._level_rank == 0 or self._closed:
            return
        try:
            kind = event.kind
            if event.content is not None:
                event = self._trim_content(event)
            rank = _rank(KIND_LEVEL[kind])
            seq: int | None = None
            with self._lock:
                self._count(event)
                if rank > self._level_rank:
                    return
                if rank <= self._seq_rank:
                    seq = self._seq
                    self._seq += 1
            item = _Item(kind, self._wall(), self._clock(), event, seq)
            try:
                self._queue.put_nowait(item)
            except queue.Full:
                with self._lock:
                    self._dropped += 1
        except Exception:  # noqa: BLE001 - feedback must never break the producer
            return

    def _count(self, event: ProgressEvent) -> None:
        """The authoritative counters (under the lock): every event is counted, whatever is displayed."""
        kind = event.kind
        fields = event.fields
        if kind == "start":
            self._command = str(fields.get("command") or self._command)[:_FIELD_STR_CAP]
            if event.total is not None:
                self._total = event.total
            workers = fields.get("workers")
            if isinstance(workers, int) and not isinstance(workers, bool):
                self._workers_configured = workers
        elif kind == "unit_start":
            self._current = (event.unit or "")[:_FIELD_STR_CAP] or None
        elif kind == "unit_done":
            self._done += 1
            status = (event.status or "done")[:_FIELD_STR_CAP]
            if status not in self._counts and len(self._counts) >= _MAX_STATUSES:
                status = "<other>"
            self._counts[status] += 1
            for code in event.codes[:20]:
                key = code[:_FIELD_STR_CAP]
                if key not in self._issues and len(self._issues) >= _MAX_ISSUE_CODES:
                    key = "<other>"
                self._issues[key] += 1
        elif kind in ("stage", "step") and event.stage:
            entry = self._stage_entry(event.stage[:_FIELD_STR_CAP])
            if entry is None:
                return
            if kind == "step":
                entry["failed" if event.status == "failed" else "done"] += 1
                return
            phase = fields.get("phase")
            entry["state"] = "done" if phase == "end" else "running"
            for key in ("done", "total", "failed"):
                value = fields.get(key)
                if isinstance(value, int) and not isinstance(value, bool):
                    entry[key] = value
            if phase == "end":
                self._heartbeat_due = True
        elif kind == "worker":
            pid = fields.get("pid")
            if isinstance(pid, int) and not isinstance(pid, bool):
                if fields.get("phase") == "exit":
                    self._pids.discard(pid)
                elif len(self._pids) < _MAX_PIDS:
                    self._pids.add(pid)

    def _stage_entry(self, name: str) -> dict[str, Any] | None:
        entry = self._stages.get(name)
        if entry is None:
            if len(self._stages) >= _MAX_STAGES:
                return None
            entry = self._stages[name] = {"state": "running", "done": 0, "total": None, "failed": 0}
        return entry

    def _trim_content(self, event: ProgressEvent) -> ProgressEvent:
        if not self._cfg.show_content or _rank(self._cfg.level) < _rank("steps"):
            return replace(event, content=None, locator=None)
        text = event.content or ""
        if len(text) > _CONTENT_SOURCE_CAP:
            text = text[:_CONTENT_SOURCE_CAP]
        locator = (event.locator or "")[:_FIELD_STR_CAP] or None
        return replace(event, content=text, locator=locator)

    # -- consumer side ----------------------------------------------------------------------------------------

    def _snapshot(self) -> Snapshot:
        with self._lock:
            issues = tuple(sorted(self._issues.items(), key=lambda kv: (-kv[1], kv[0])))
            return Snapshot(
                self._command,
                self._total,
                self._done,
                _order_counts(self._counts),
                issues,
                self._current,
                self._started,
                self._dropped,
            )

    def heartbeat_snapshot(self, now: float | None = None) -> dict[str, Any]:
        """The 0.2 ``heartbeat`` body: absolute counters, so a reader that joins late or misses lines recovers."""
        now = self._clock() if now is None else now
        with self._lock:
            ranked = sorted(self._issues.items(), key=lambda kv: (-kv[1], kv[0]))
            top = ranked[:_HEARTBEAT_ISSUES]
            pids = sorted(self._pids)
            return {
                "elapsed_s": round(max(0.0, now - self._started), 3),
                "total": self._total,
                "units_done": self._done,
                "stages": {_safe(k, 60): dict(v) for k, v in sorted(self._stages.items())},
                "counts": {_safe(s, 40): n for s, n in _order_counts(self._counts)},
                "issues_top": {_safe(c, 80): n for c, n in top},
                "issues_other": sum(n for _, n in ranked[_HEARTBEAT_ISSUES:]),
                "workers": {"configured": self._workers_configured, "alive": len(pids), "pids": pids[:64]},
                "queue": {"pending": None if self._total is None else max(0, self._total - self._done)},
                "dropped": self._dropped,
            }

    def _each(self, call: Callable[[_Renderer], None], *, rank: int = 0) -> None:
        for renderer, shown in self._renderers:
            if id(renderer) in self._broken or rank > shown:
                continue
            try:
                call(renderer)
            except Exception:  # noqa: BLE001 - a broken pipe or closed file disables that output only
                self._broken.add(id(renderer))

    def _each_jsonl(self, call: Callable[[JsonlRenderer], None]) -> None:
        for renderer in self._jsonl:
            if id(renderer) in self._broken:
                continue
            try:
                call(renderer)
            except Exception:  # noqa: BLE001
                self._broken.add(id(renderer))

    def _header(self) -> dict[str, FieldValue]:
        return {"pid": os.getpid(), "agentprov_version": _version(), **dict(self._cfg.header)}

    def _begin(self) -> None:
        if not self._begun:
            self._begun = True
            header = self._header()
            self._each_jsonl(lambda r: r.begin(header, self._header_seq))

    def _rotated(self, renderer: JsonlRenderer) -> None:
        renderer.begin(self._header())
        renderer.heartbeat(self.heartbeat_snapshot())

    def _dispatch(self, item: _Item) -> None:
        self._each(lambda r: r.event(item, self._snapshot), rank=_rank(KIND_LEVEL[item.kind]))

    def _tick(self) -> None:
        now = self._clock()
        self._each(lambda r: r.tick(now, self._snapshot))
        with self._lock:
            due = self._heartbeat_due or now - self._last_heartbeat >= self._cfg.progress_interval
            if due:
                self._heartbeat_due = False
                self._last_heartbeat = now
        if due and self._jsonl:
            body = self.heartbeat_snapshot(now)
            self._each_jsonl(lambda r: r.heartbeat(body))

    def pump(self) -> None:
        """Drain the queue and tick once, in the calling thread (for ``start_thread=False``; tests)."""
        self._begin()
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break
            self._dispatch(item)
        self._tick()

    def _run(self) -> None:
        self._begin()
        while True:
            try:
                item = self._queue.get(timeout=self._tick_s)
            except queue.Empty:
                if self._stop.is_set():
                    break
                self._tick()
                continue
            self._dispatch(item)
            self._tick()
        self._finish()

    def _finish(self) -> None:
        self._begin()
        snap = self._snapshot()
        now = self._clock()
        outcome = self._outcome
        if outcome is None and self._exit_code is not None:
            from agentprov.cli.common import outcome_for

            outcome = outcome_for(self._exit_code)
        if self._jsonl:
            body = self.heartbeat_snapshot(now)
            self._each_jsonl(lambda r: r.heartbeat(body))  # the final counters, as a reader's last snapshot
        for renderer, _shown in self._renderers:
            if id(renderer) in self._broken:
                continue
            try:
                if isinstance(renderer, JsonlRenderer):
                    renderer.finish(snap, now, self._exit_code, outcome)
                else:
                    renderer.finish(snap, now, self._exit_code)
            except Exception:  # noqa: BLE001
                self._broken.add(id(renderer))
        for renderer in self._jsonl:
            if renderer._path is not None:  # the file renderer (it may have rotated to a new handle)
                try:
                    renderer.close()
                except Exception:  # noqa: BLE001, S110
                    pass
        if self._file is not None:
            try:
                self._file.close()
            except Exception:  # noqa: BLE001
                pass

    def close(self, exit_code: int | None = None, *, timeout: float = _JOIN_TIMEOUT_S, outcome: str | None = None) -> int:
        """Stop, drain, print the end-of-run summary and return the drop count. ``outcome`` overrides the one the exit
        code implies (``drained``, D-394).

        If the display is stalled the join times out and the daemon thread is abandoned: the command finishes and
        exits anyway (F2). Calling it again does nothing.
        """
        if self._closed:
            return self._dropped
        self._closed = True
        self._exit_code = exit_code
        self._outcome = outcome
        if self._level_rank == 0:
            return self._dropped
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
        else:
            self.pump()
            self._finish()
        return self._dropped

    def __enter__(self) -> FeedbackSink:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _version() -> str:
    from agentprov.versions import __version__

    return __version__


def make_sink(cfg: FeedbackConfig, stream: _Output, *, stderr: bool = True) -> FeedbackSink | None:
    """The sink for ``cfg``, or ``None`` when nothing would be shown (``off``, or no stderr feedback, and no
    ``--progress-file``): then nothing is created and nothing is opened. ``stderr=False`` (a command without live
    feedback) still writes the ``--progress-file``."""
    if (cfg.level == "off" or not stderr) and not cfg.progress_file:
        return None
    file = open_progress_file(cfg.progress_file) if cfg.progress_file else None
    return FeedbackSink(cfg, stream, file=file, stderr=stderr)
