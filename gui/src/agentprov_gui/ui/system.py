"""System (design §6.4; wireframe 05; the tab is "System", not "Activity": a PROV term).

A 1 Hz sampler in the GUI process (never inside a job), running **only while this page is visible**: each sample is
a short task in the global thread pool, at most one in flight (a long-lived ``QThread`` owned by the page aborted Qt
when the page was destroyed while it ran). CPU per core (sparklines over 120 s, drawn with ``QPainter``: Qt Charts and Qt Graphs are GPL-only),
memory and swap, free disk under ``AGENTPROV_HOME``, and the process tree of the selected job (the CLI and its
children: RSS, CPU %, threads). The tree is re-walked every 10 s (``children(recursive=True)`` costs ~37 ms on macOS,
research §M4); between walks the known pids are sampled. Temperatures: Linux only (psutil has none elsewhere).

House style (D-1060): the page title with the followed job as a status badge, the computer's facts in a card, the
cores' sparklines in a card, the processes in a card with plain-language column headers, and the terminal command
card: ``agentprov info`` (its Host section: CPUs, memory, isolation grade) and ``agentprov jobs show ID`` for the
followed job, built by the ``info`` and ``jobs_show`` forms (:func:`commands_for`).
"""

from __future__ import annotations

import shutil
import sys
import time
from collections import deque
from pathlib import Path
from typing import Any, Final

import psutil
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPaintEvent, QPen
from PySide6.QtWidgets import QFrame, QGridLayout, QSizePolicy, QTableWidget, QVBoxLayout, QWidget

from agentprov_gui import text as T
from agentprov_gui.jobs.commands import FORMS, build_spec
from agentprov_gui.ui import theme
from agentprov_gui.ui.brand import command_card, page_header
from agentprov_gui.ui.detail import fill_rows
from agentprov_gui.ui.forms import FactGrid, FormPage, FormSection, StatusBadge, caption
from agentprov_gui.ui.safe import SafeLabel, set_control_tooltip, set_header_tooltips
from agentprov_gui.ui.worker import submit

__all__ = ["Sampler", "Sparkline", "SystemPage", "commands_for"]

HISTORY: Final = 120
TREE_REFRESH_S: Final = 10.0
#: the page column's maximum width (wider than a form's: the cores' grid)
PAGE_MAX: Final = 1100
PROCESS_HEADERS: Final = ("Process id", "Name", "CPU", "Memory (MiB)", "Threads")
PROCESS_TIPS: Final = (
    "The process id (pid).",
    "The process name.",
    "CPU use since the previous sample, in %; above 100 % when it uses more than one core.",
    "Resident memory (RSS) in MiB.",
    "The number of threads.",
)
#: the facts of the computer, in order: (key, label)
FACTS: Final = (("cpu", "CPU, mean of all cores"), ("memory", "Memory in use"), ("swap", "Swap in use"),
                ("disk", "Free under AGENTPROV_HOME"), ("temps", "Temperatures"))


def commands_for(job_id: str | None) -> list[tuple[str, tuple[str, ...]]]:
    """The terminal commands of what the page shows, from the ``info`` and ``jobs_show`` forms: the host's facts, and
    the followed job when there is one."""
    out = [("this computer: CPUs, memory and the isolation grade (its Host section)",
            build_spec(FORMS["info"], {"format": "text"}).argv)]
    if job_id is not None:
        out.append(("the followed job", build_spec(FORMS["jobs_show"], {"job_id": job_id, "format": "text"}).argv))
    return out


class Sparkline(QWidget):
    def __init__(self, name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAccessibleName(name)
        self.values: deque[float] = deque(maxlen=HISTORY)
        self.setMinimumSize(72, 30)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def push(self, value: float) -> None:
        self.values.append(max(0.0, min(100.0, value)))
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        t = theme.tokens()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor(t.field_border), 1))
        p.setBrush(QColor(t.field))
        p.drawRoundedRect(r, 4, 4)
        if len(self.values) > 1:
            inner = r.adjusted(2, 3, -2, -2)
            step = inner.width() / (HISTORY - 1)
            pts = [QPointF(inner.right() - (len(self.values) - 1 - i) * step, inner.bottom() - v / 100 * inner.height())
                   for i, v in enumerate(self.values)]
            area = QPainterPath(QPointF(pts[0].x(), inner.bottom()))
            for pt in pts:
                area.lineTo(pt)
            area.lineTo(pts[-1].x(), inner.bottom())
            fill = QColor(t.accent)
            fill.setAlpha(40)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(fill)
            p.drawPath(area)
            p.setPen(QPen(QColor(t.accent), 1.4))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPolyline(pts)
        p.end()


def _labelled(text: str, widget: QWidget, parent: QWidget, *, above: bool = False) -> QWidget:
    """``widget`` with a grey caption beside it (or ``above`` it)."""
    holder = QWidget(parent)
    holder.setAccessibleName(text)
    lay: QVBoxLayout | QGridLayout = QVBoxLayout(holder) if above else QGridLayout(holder)
    lay.setContentsMargins(0, 0, 0, 0)
    label = caption(text, name=f"{text} label", parent=holder)
    if isinstance(lay, QVBoxLayout):
        lay.setSpacing(2)
        lay.addWidget(label)
        widget.setParent(holder)
        lay.addWidget(widget)
    else:
        lay.setHorizontalSpacing(12)
        label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        label.setWordWrap(False)
        lay.addWidget(label, 0, 0)
        widget.setParent(holder)
        lay.addWidget(widget, 0, 1)
        lay.setColumnStretch(1, 1)
    return holder


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
        self.job_id: str | None = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.page = FormPage(name="System facts", parent=self, max_width=PAGE_MAX)
        outer.addWidget(self.page)
        header, head, _note = page_header(self.page.column, "System", caption_text=(
            "This computer, sampled once a second while this page is shown (never inside a job)."))
        self.following = StatusBadge("", name="Followed job", parent=header)
        set_control_tooltip(self.following, "The running job selected in Runs whose processes are listed below.")
        head.addWidget(self.following)
        self.page.add(header)
        from agentprov_gui.platform.windows import long_path_warning

        warning = long_path_warning()  # G5 P-5: Windows only; None elsewhere
        if warning is not None:
            paths = FormSection("Windows long paths", parent=self.page.column)
            self.long_paths = SafeLabel(warning, name="Windows long paths", parent=paths.card)
            self.long_paths.setWordWrap(True)
            paths.add(self.long_paths)
            self.page.add(paths)
        host = FormSection("This computer", parent=self.page.column)
        self.facts = FactGrid(name="System summary", parent=host.card)
        set_control_tooltip(self.facts, "Mean CPU use over all cores, memory and swap in use, the free space "
                                        "under AGENTPROV_HOME and the temperatures (Linux only), sampled once a "
                                        "second while this page is shown.")
        for key, label in FACTS:
            self.facts.set(key, "…", label=label)
        host.add(self.facts)
        self.memory = Sparkline("Memory used", host.card)
        set_control_tooltip(self.memory, f"Memory in use, as a share of the total, over the last {HISTORY} seconds.")
        host.add(_labelled("Memory, last 2 minutes", self.memory, host.card))
        self.page.add(host)
        count = psutil.cpu_count() or 1
        cores = FormSection("CPU cores", parent=self.page.column,
                            note=f"Each core's use from 0 to 100 % over the last {HISTORY} seconds.")
        holder = QWidget(cores.card)
        holder.setAccessibleName("CPU cores")
        grid = QGridLayout(holder)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        columns = 6 if count >= 12 else 4
        self.cores: list[Sparkline] = []
        for i in range(count):
            spark = Sparkline(f"CPU core {i + 1}", holder)
            set_control_tooltip(spark, f"CPU use of core {i + 1} over the last {HISTORY} seconds, from 0 to 100 %.")
            self.cores.append(spark)
            grid.addWidget(_labelled(f"Core {i + 1}", spark, holder, above=True), i // columns, i % columns)
        for c in range(columns):
            grid.setColumnStretch(c, 1)
        cores.add(holder)
        self.page.add(cores)
        procs = FormSection("Processes of the selected job", parent=self.page.column,
                            note="Select a running job in Runs to list its agentprov process and its child processes.")
        self.procs = QTableWidget(0, len(PROCESS_HEADERS), procs.card)
        self.procs.setAccessibleName("Job processes")
        self.procs.setHorizontalHeaderLabels(list(PROCESS_HEADERS))
        self.procs.verticalHeader().setVisible(False)
        self.procs.horizontalHeader().setStretchLastSection(True)
        self.procs.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.procs.setFrameShape(QFrame.Shape.NoFrame)
        self.procs.setShowGrid(False)
        self.procs.setMinimumHeight(160)
        set_header_tooltips(self.procs, PROCESS_TIPS)
        set_control_tooltip(self.procs, "The processes of the running job selected in Runs: its agentprov process "
                                        "and its child processes. The process tree is read again every 10 seconds.")
        procs.add(self.procs)
        self.page.add(procs)
        self.command_card = command_card(self.page.column)
        self.page.add(self.command_card)
        self.sampler = Sampler(home)
        self._in_flight = False
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._request)
        self.command_card.set_commands(commands_for(None))
        self._show_job(None)

    def _request(self) -> None:
        if self._in_flight or not self.sampler.active:
            return
        self._in_flight = True
        submit(self, lambda _s: self.sampler.sample(), self._done, lambda _code: self._done(None))

    def _done(self, sample: dict[str, Any] | None) -> None:
        self._in_flight = False
        if sample is not None and self.sampler.active:
            self._show(sample)

    def follow_job(self, pid: int | None, create_time: float | None, job_id: str | None = None) -> None:
        """Follow the processes of the job whose CLI runs as ``pid`` (``job_id``: the job, for the badge and the
        terminal command)."""
        self.sampler.root_pid, self.sampler.root_create = pid, create_time
        self.sampler._walked = 0.0
        self.job_id = job_id if pid is not None else None
        self.command_card.set_commands(commands_for(self.job_id))

    def _show_job(self, processes: int | None) -> None:
        if self.sampler.root_pid is None:
            words, kind = "No job followed", "neutral"
        else:
            name = f"Job {self.job_id[:13]}" if self.job_id else "The job"
            count = f"{processes} process" + ("" if processes == 1 else "es")
            words, kind = (f"{name}: {count}", "info") if processes else (f"{name}: no processes", "neutral")
        if (words, kind) != (self.following.text(), self.following.kind):
            self.following.set_status(words, kind)

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
        self.facts.set("cpu", f"{sum(s['cpu']) / max(len(s['cpu']), 1):.0f} % of {len(s['cpu'])} cores")
        self.facts.set("memory", f"{mem['used'] / 2**30:.1f} of {mem['total'] / 2**30:.1f} GiB")
        self.facts.set("swap", f"{s['swap']['used'] / 2**30:.1f} GiB")
        self.facts.set("disk", f"{s['disk']['free'] / 2**30:,.0f} GiB" if s.get("disk") else "Not readable")
        self.facts.set("temps", ", ".join(f"{T.line(k, 30)} {max(v):.0f} °C" for k, v in s["temps"].items() if v)
                       if s.get("temps") else "Not available on this OS")
        rows = s.get("procs", [])
        fill_rows(self.procs, ([str(pid), T.line(name, 60), f"{cpu:.0f} %", f"{rss:.0f}", str(threads)]
                               for pid, name, cpu, rss, threads in rows))
        self._show_job(len(rows))
