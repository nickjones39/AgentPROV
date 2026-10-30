"""System (design §6.4; wireframe 05; the tab is "System", not "Activity": a PROV term).

A 1 Hz sampler in the GUI process (never inside a job), running **only while this page is visible**: each sample is
a short task in the global thread pool, at most one in flight (a long-lived ``QThread`` owned by the page aborted Qt
when the page was destroyed while it ran). CPU per core (sparklines over 120 s, drawn with ``QPainter``: Qt Charts and Qt Graphs are GPL-only),
memory and swap, free disk under ``AGENTPROV_HOME``, and the process tree of the selected job (the CLI and its
children: RSS, CPU %, threads). The tree is re-walked every 10 s (``children(recursive=True)`` costs ~37 ms on macOS,
research §M4); between walks the known pids are sampled. Temperatures: Linux only (psutil has none elsewhere).
"""

from __future__ import annotations

import shutil
import sys
import time
from collections import deque
from pathlib import Path
from typing import Any, Final

import psutil
from PySide6.QtCore import QPointF, QRectF, QTimer
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QGridLayout, QSizePolicy, QTableWidget, QVBoxLayout, QWidget

from agentprov_gui import text as T
from agentprov_gui.ui.detail import fill_rows
from agentprov_gui.ui.safe import SafeLabel
from agentprov_gui.ui.worker import submit

__all__ = ["Sampler", "Sparkline", "SystemPage"]

HISTORY: Final = 120
TREE_REFRESH_S: Final = 10.0


class Sparkline(QWidget):
    def __init__(self, name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAccessibleName(name)
        self.values: deque[float] = deque(maxlen=HISTORY)
        self.setMinimumSize(120, 36)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def push(self, value: float) -> None:
        self.values.append(max(0.0, min(100.0, value)))
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(QPen(self.palette().color(self.foregroundRole()), 0.5))
        p.drawRect(r)
        if len(self.values) > 1:
            step = r.width() / (HISTORY - 1)
            pts = [QPointF(r.right() - (len(self.values) - 1 - i) * step, r.bottom() - v / 100 * r.height())
                   for i, v in enumerate(self.values)]
            p.setPen(QPen(QColor("#0A84FF"), 1.4))
            p.drawPolyline(pts)
        p.end()


class Sampler:
    """One sample per call (run in a pool thread, one at a time). Keeps the job's process set between calls."""

    def __init__(self, home: Path) -> None:
        self.home = home
        self.root_pid: int | None = None
        self.root_create: float | None = None
        self._procs: dict[int, psutil.Process] = {}
        self._walked = 0.0
        self.active = False

    def sample(self) -> dict[str, Any]:
        out: dict[str, Any] = {"cpu": psutil.cpu_percent(percpu=True), "mem": psutil.virtual_memory()._asdict(),
                               "swap": psutil.swap_memory()._asdict()}
        try:
            out["disk"] = shutil.disk_usage(self.home if self.home.exists() else Path.home())._asdict()
        except OSError:
            out["disk"] = None
        if sys.platform.startswith("linux") and hasattr(psutil, "sensors_temperatures"):
            out["temps"] = {k: [t.current for t in v] for k, v in psutil.sensors_temperatures().items()}
        out["procs"] = self._proc_rows()
        return out

    def _proc_rows(self) -> list[tuple[int, str, float, float, int]]:
        if self.root_pid is None:
            return []
        now = time.monotonic()
        if now - self._walked > TREE_REFRESH_S:
            self._walked = now
            try:
                root = psutil.Process(self.root_pid)
                if self.root_create is not None and abs(root.create_time() - self.root_create) > 0.01:
                    return []
                self._procs = {p.pid: p for p in [root, *root.children(recursive=True)]}
            except psutil.Error:
                self._procs = {}
        rows = []
        for pid, proc in list(self._procs.items()):
            try:
                with proc.oneshot():
                    rows.append((pid, proc.name(), proc.cpu_percent(), proc.memory_info().rss / 2**20, proc.num_threads()))
            except psutil.Error:
                self._procs.pop(pid, None)
        return rows


class SystemPage(QWidget):
    def __init__(self, home: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAccessibleName("System")
        lay = QVBoxLayout(self)
        self.summary = SafeLabel("", name="System summary", parent=self)
        lay.addWidget(self.summary)
        from agentprov_gui.platform.windows import long_path_warning

        warning = long_path_warning()  # G5 P-5: Windows only; None elsewhere
        if warning is not None:
            self.long_paths = SafeLabel(warning, name="Windows long paths", parent=self)
            self.long_paths.setWordWrap(True)
            lay.addWidget(self.long_paths)
        grid = QGridLayout()
        self.cores: list[Sparkline] = []
        for i in range(psutil.cpu_count() or 1):
            spark = Sparkline(f"CPU core {i + 1}", self)
            self.cores.append(spark)
            grid.addWidget(SafeLabel(f"core {i + 1}", name=f"core {i + 1} label", parent=self, selectable=False),
                           i // 4, (i % 4) * 2)
            grid.addWidget(spark, i // 4, (i % 4) * 2 + 1)
        lay.addLayout(grid)
        self.memory = Sparkline("Memory used", self)
        lay.addWidget(SafeLabel("memory used", name="memory label", parent=self, selectable=False))
        lay.addWidget(self.memory)
        self.procs = QTableWidget(0, 5, self)
        self.procs.setAccessibleName("Job processes")
        self.procs.setHorizontalHeaderLabels(["pid", "name", "CPU %", "RSS MiB", "threads"])
        self.procs.verticalHeader().setVisible(False)
        self.procs.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(SafeLabel("processes of the selected job (Runs)", name="processes label", parent=self))
        lay.addWidget(self.procs, 1)
        self.sampler = Sampler(home)
        self._in_flight = False
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._request)

    def _request(self) -> None:
        if self._in_flight or not self.sampler.active:
            return
        self._in_flight = True
        submit(self, lambda _s: self.sampler.sample(), self._done, lambda _code: self._done(None))

    def _done(self, sample: dict[str, Any] | None) -> None:
        self._in_flight = False
        if sample is not None and self.sampler.active:
            self._show(sample)

    def follow_job(self, pid: int | None, create_time: float | None) -> None:
        self.sampler.root_pid, self.sampler.root_create = pid, create_time
        self.sampler._walked = 0.0

    def showEvent(self, event: Any) -> None:
        self.sampler.active = True
        self.timer.start()
        super().showEvent(event)

    def hideEvent(self, event: Any) -> None:
        self.sampler.active = False
        self.timer.stop()
        super().hideEvent(event)

    def shutdown(self) -> None:
        self.timer.stop()
        self.sampler.active = False

    def _show(self, s: dict[str, Any]) -> None:
        for spark, value in zip(self.cores, s["cpu"], strict=False):
            spark.push(float(value))
        mem = s["mem"]
        self.memory.push(float(mem.get("percent", 0)))
        parts = [f"CPU {sum(s['cpu']) / max(len(s['cpu']), 1):.0f} %",
                 f"memory {mem['used'] / 2**30:.1f} of {mem['total'] / 2**30:.1f} GiB",
                 f"swap {s['swap']['used'] / 2**30:.1f} GiB"]
        if s.get("disk"):
            parts.append(f"free under AGENTPROV_HOME {s['disk']['free'] / 2**30:.0f} GiB")
        parts.append("temperatures: " + (", ".join(f"{T.line(k, 30)} {max(v):.0f} °C" for k, v in s["temps"].items() if v)
                                         if s.get("temps") else "not available on this OS"))
        self.summary.set_plain(" · ".join(parts))
        fill_rows(self.procs, ([str(pid), T.line(name, 60), f"{cpu:.0f}", f"{rss:.0f}", str(threads)]
                               for pid, name, cpu, rss, threads in s.get("procs", [])))
