"""Following a job's files (GUI design §5.3, §5.4, §6.3; in the core since D-704, read-only: the GUI imports it).

* :class:`TailReader`: one open handle and a byte offset; each :meth:`TailReader.read` reads at most 1 MiB, keeps the
  trailing partial line, skips (and counts) lines over 64 KiB, and reopens on rotation (a new file identity, or a size
  smaller than the offset). Lines are parsed with the core's strict loader.
* :class:`ProgressState`: the fold of ``agentprov-progress/0.1`` events (``start``, ``unit_start``, ``unit_done``,
  ``step``, ``trace``, ``end``), and of the 0.2 ``heartbeat`` snapshot when a CLI writes one (absolute counters replace
  the fold). Unknown events and fields are ignored (pytest-reportlog rule).
* :class:`Rates`: throughput as a bias-corrected EWMA (α 0.3 per 5 s window) next to the overall mean, and an ETA range
  shown only after 30 units and 60 s (§5.4).
* :class:`LogRing`: the last N log records (50,000 by default) with the count of records that left the buffer.

Every string in these files is metadata the CLI already escaped; the views apply ``text.clean`` (S3).
"""

from __future__ import annotations

import os
from collections import Counter, deque
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from agentprov.errors import IngestError
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads

__all__ = ["LINE_CAP", "READ_CAP", "LogRecord", "LogRing", "ProgressState", "Rates", "TailReader"]

READ_CAP: Final = 1024 * 1024
LINE_CAP: Final = 64 * 1024
_LIMITS: Final = IngestLimits()


class TailReader:
    def __init__(self, path: Path, *, read_cap: int = READ_CAP, line_cap: int = LINE_CAP) -> None:
        self.path = path
        self.read_cap, self.line_cap = read_cap, line_cap
        self._fh: Any = None
        self._ident: tuple[int, int] | None = None
        self.offset = 0
        self._partial = b""
        self.skipped_long = 0
        self.skipped_bad = 0
        self.lagging_bytes = 0
        self.rotations = 0

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None

    def _open(self) -> bool:
        try:
            fh = open(self.path, "rb")  # noqa: SIM115 - kept open between reads
        except OSError:
            return False
        st = os.fstat(fh.fileno())
        self._fh, self._ident, self.offset, self._partial = fh, (st.st_dev, st.st_ino), 0, b""
        return True

    def seek_to_offset(self, offset: int) -> None:
        if self._fh is None and not self._open():
            return
        self.offset = offset
        self._partial = b""

    def read_lines(self) -> list[bytes]:
        """Complete new lines (without LF), at most ``read_cap`` bytes this call."""
        if self._fh is None and not self._open():
            return []
        try:
            st = os.stat(self.path)
        except OSError:
            st = None
        if st is not None and ((st.st_dev, st.st_ino) != self._ident or st.st_size < self.offset):
            self.close()
            self.rotations += 1
            if not self._open():
                return []
            st = os.fstat(self._fh.fileno())
        self._fh.seek(self.offset)
        data = self._fh.read(self.read_cap)
        self.offset += len(data)
        size = st.st_size if st is not None else self.offset
        self.lagging_bytes = max(0, size - self.offset)
        buf = self._partial + data
        parts = buf.split(b"\n")
        self._partial = parts.pop()
        if len(self._partial) > self.line_cap:  # an over-long line in progress: drop it and count it once
            self._partial = b""
            self.skipped_long += 1
        out: list[bytes] = []
        for line in parts:
            if len(line) > self.line_cap:
                self.skipped_long += 1
                continue
            if line:
                out.append(line)
        return out

    def read(self) -> list[dict[str, Any]]:
        """New complete lines parsed strictly as JSON objects; a malformed line is counted and skipped."""
        records: list[dict[str, Any]] = []
        for line in self.read_lines():
            try:
                value = strict_json_loads(line.rstrip(b"\r"), _LIMITS, record=True)
            except IngestError:
                self.skipped_bad += 1
                continue
            if isinstance(value, dict):
                records.append(value)
            else:
                self.skipped_bad += 1
        return records


def last_heartbeat_offset(path: Path, window: int = 4 * 1024 * 1024) -> int:
    """On attach (§5.3): the byte offset of the last ``heartbeat`` line within the last ``window`` bytes, else 0 (fold
    the whole file)."""
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            start = max(0, size - window)
            fh.seek(start)
            data = fh.read()
    except OSError:
        return 0
    at = data.rfind(b'"event":"heartbeat"')
    if at < 0:
        return 0
    line_start = data.rfind(b"\n", 0, at) + 1
    return start + line_start if (start == 0 or line_start > 0) else 0


# ----------------------------------------------------------------------------------------------- progress
@dataclass(slots=True)
class ProgressState:
    """The fold of a progress file. Absolute numbers only; rates are :class:`Rates`."""

    version: str | None = None
    command: str | None = None
    total: int | None = None
    done: int = 0
    current_unit: str | None = None
    in_flight: int = 0
    statuses: Counter[str] = field(default_factory=Counter)
    codes: Counter[str] = field(default_factory=Counter)
    steps: Counter[str] = field(default_factory=Counter)
    stages: dict[str, dict[str, Any]] = field(default_factory=dict)  # 0.2 heartbeat
    workers: dict[str, Any] = field(default_factory=dict)  # 0.2 heartbeat
    ended: bool = False
    exit_code: int | None = None
    elapsed_s: float | None = None
    dropped: int = 0
    events: int = 0
    first_ts: str | None = None
    last_ts: str | None = None
    controls: list[dict[str, Any]] = field(default_factory=list)
    #: D-393 ``session`` events of a live run (session id -> phase), for the live preview (D-398); ids only
    sessions: dict[str, str] = field(default_factory=dict)

    def apply(self, ev: dict[str, Any]) -> None:
        kind = ev.get("event")
        v = ev.get("v")
        if isinstance(v, str):
            self.version = v
        ts = ev.get("ts")
        if isinstance(ts, str):
            self.first_ts = self.first_ts or ts
            self.last_ts = ts
        self.events += 1
        if kind == "start":
            total = ev.get("total")
            self.total = total if isinstance(total, int) and not isinstance(total, bool) else self.total
            command = ev.get("command")
            self.command = command if isinstance(command, str) else self.command
        elif kind == "run":  # 0.2: a new process segment
            total = ev.get("total")
            if isinstance(total, int) and not isinstance(total, bool):
                self.total = total
            self.ended = False
        elif kind == "unit_start":
            self.in_flight += 1
            unit = ev.get("unit")
            self.current_unit = unit if isinstance(unit, str) else self.current_unit
        elif kind == "unit_done":
            self.done += 1
            self.in_flight = max(0, self.in_flight - 1)
            status = ev.get("status")
            if isinstance(status, str):
                self.statuses[status] += 1
            codes = ev.get("codes")
            if isinstance(codes, list):
                for c in codes:
                    if isinstance(c, str):
                        self.codes[c] += 1
        elif kind == "step":
            stage = ev.get("stage")
            if isinstance(stage, str):
                self.steps[stage] += 1
        elif kind == "session":
            session, phase = ev.get("session"), ev.get("phase")
            if isinstance(session, str) and len(session) <= 64 and len(self.sessions) < 100_000:
                self.sessions[session] = phase if phase in ("start", "end") else "start"
        elif kind == "heartbeat":
            self._heartbeat(ev)
        elif kind == "control":
            self.controls.append({k: ev.get(k) for k in ("request", "nonce", "accepted")})
        elif kind == "end":
            self.ended = True
            code = ev.get("exit_code")
            self.exit_code = code if isinstance(code, int) and not isinstance(code, bool) else None
            elapsed = ev.get("elapsed_s")
            self.elapsed_s = float(elapsed) if isinstance(elapsed, int | float) and not isinstance(elapsed, bool) else None
            units = ev.get("units_done")
            if isinstance(units, int) and not isinstance(units, bool):
                self.done = units
            for key, target in (("counts", self.statuses), ("issues", self.codes)):
                value = ev.get(key)
                if isinstance(value, dict):
                    target.clear()
                    target.update({str(k): int(n) for k, n in value.items() if isinstance(n, int)})
            dropped = ev.get("dropped")
            self.dropped = dropped if isinstance(dropped, int) else self.dropped

    def _heartbeat(self, ev: dict[str, Any]) -> None:
        stages = ev.get("stages")
        if isinstance(stages, dict):
            self.stages = {str(k): v for k, v in stages.items() if isinstance(v, dict)}
        counts = ev.get("counts")
        if isinstance(counts, dict):
            self.statuses = Counter({str(k): int(n) for k, n in counts.items() if isinstance(n, int)})
            self.done = sum(self.statuses.values())
        issues = ev.get("issues_top")
        if isinstance(issues, dict):
            self.codes = Counter({str(k): int(n) for k, n in issues.items() if isinstance(n, int)})
        workers = ev.get("workers")
        if isinstance(workers, dict):
            self.workers = workers
        dropped = ev.get("dropped")
        if isinstance(dropped, int):
            self.dropped = dropped

    @property
    def fraction(self) -> float | None:
        if self.total and self.total > 0:
            return min(1.0, self.done / self.total)
        return None


class Rates:
    """Throughput and ETA (design §5.4)."""

    WINDOW_S: Final = 5.0
    ALPHA: Final = 0.3

    def __init__(self) -> None:
        self.start: float | None = None
        self._window_start: float | None = None
        self._window_done = 0
        self._last_done = 0
        self._ewma = 0.0
        self._weight = 0.0

    def update(self, now: float, done: int) -> None:
        if self.start is None:
            self.start, self._window_start, self._last_done = now, now, done
            return
        assert self._window_start is not None
        self._window_done += max(0, done - self._last_done)
        self._last_done = done
        span = now - self._window_start
        if span >= self.WINDOW_S:
            rate = self._window_done / span
            self._ewma = self.ALPHA * rate + (1 - self.ALPHA) * self._ewma
            self._weight = self.ALPHA + (1 - self.ALPHA) * self._weight
            self._window_start, self._window_done = now, 0

    def short(self) -> float | None:
        return self._ewma / self._weight if self._weight > 0 else None  # bias-corrected (tqdm's form)

    def mean(self, now: float, done: int) -> float | None:
        if self.start is None or now <= self.start:
            return None
        return done / (now - self.start)

    def eta(self, now: float, done: int, total: int | None) -> tuple[float, float] | None:
        """``(low, high)`` seconds, or ``None`` before 30 units and 60 s or without a total."""
        if total is None or self.start is None or done < 30 or now - self.start < 60 or done >= total:
            return None
        remaining = total - done
        rates = [r for r in (self.mean(now, done), self.short()) if r]
        if not rates:
            return None
        times = sorted(remaining / r for r in rates)
        return times[0], times[-1]


def human_duration(seconds: float) -> str:
    s = round(seconds)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h} h {m:02d} m" if h else (f"{m} m {s:02d} s" if m else f"{s} s")


def eta_text(eta: tuple[float, float] | None) -> str:
    if eta is None:
        return "ETA after 30 units and 60 s"
    low, high = eta
    mid = (low + high) / 2
    return f"≈ {human_duration(mid)} ({human_duration(low)} – {human_duration(high)})"


# ----------------------------------------------------------------------------------------------- logs
@dataclass(frozen=True, slots=True)
class LogRecord:
    ts: str
    level: str
    logger: str
    msg: str
    ex: str | None = None
    code: str | None = None
    stage: str | None = None

    @classmethod
    def from_json(cls, obj: dict[str, Any]) -> LogRecord:
        def s(key: str) -> str:
            v = obj.get(key)
            return v if isinstance(v, str) else ""

        def o(key: str) -> str | None:
            v = obj.get(key)
            return v if isinstance(v, str) else None

        return cls(s("ts"), s("level"), s("logger"), s("msg"), o("ex"), o("code"), o("stage"))

    @classmethod
    def plain(cls, line: str, source: str = "stderr") -> LogRecord:
        return cls("", "", source, line)


class LogRing:
    def __init__(self, capacity: int = 50_000) -> None:
        self.capacity = max(10_000, min(capacity, 500_000))
        self.records: deque[LogRecord] = deque(maxlen=self.capacity)
        self.evicted = 0

    def extend(self, records: list[LogRecord]) -> int:
        overflow = max(0, len(self.records) + len(records) - self.capacity)
        self.evicted += overflow
        self.records.extend(records)
        return overflow

    def __len__(self) -> int:
        return len(self.records)

    def __iter__(self) -> Iterator[LogRecord]:
        return iter(self.records)
