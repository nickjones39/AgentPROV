"""Runs (design §6.2, §6.2a; wireframe 03; macos-design §3.3 "Runs"; D-392, D-544; the house style of D-1060).

* **Jobs:** the job list (running, ended) and the selected job's detail as cards: a header with its title, a state
  badge (Running, Pausing, Paused, Stopping, Stopped, Cancelled, Ended, Failed), the progress bar and the facts the
  job reports (for a live run, ``agentprov run``: cells done of the total, in progress, and the billed model calls and
  the spend's upper bound against their caps from the working corpus's ``live.caps``), the controls, what each control
  does, the terminal commands of the selected job (a :class:`CommandCard`), the command as copyable argv, counts by
  status, failures by code and the stderr tail (escaped). Controls: Pause (drain; only for a job started with
  ``--control-file``), Resume (re-runs the same command as a new job; never a cancelled one), Stop (one graceful stop),
  Cancel Run… (D-1061: ``agentprov jobs cancel ID``, the stop and a mark that makes Resume refuse the job; nothing is
  deleted), Force Kill… (after a Stop that hangs, confirmed), Open in Viewer, Open Log, Copy Command, Live Preview.
* **Batches** (D-704): each batch runs as its own driver job (``agentprov batch run``), so it keeps going when the GUI
  closes; the GUI creates and starts it (``batch create --stdin``, ``batch start --confirm-r2``) and shows its file. A
  driver started again without the confirmation holds at an R2 step until Resume Batch confirms it (GR-48). Stop Batch
  stops the selected batch's driver and every running step job (``batch stop ID --steps``); Resume Batch goes on.
* **Dev runs** (D-544): plan, start, a summary row per part, and Stop Dev Run (the latest running dev run's batch, as
  Stop Batch, and any running live dev-run job).
* **Sessions** (§6.2a): ``tools/queue_status.py --json`` of the configured checkout every 30 s while the tab is
  visible (an R0 subprocess). Read-only; every string escaped.

Closing the GUI never stops a job. Every start, stop, kill, drain and cancel is an ``agentprov jobs`` call, and a
batch's an ``agentprov batch`` call (D-704). Each terminal command card is built with :func:`build_spec` from the
command's own form, the argv the action runs. Timers: 250 ms for the selected job's files, 1 s for the list and
batches; a live run's ``live.caps`` is read in the pool at most every 5 s.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import shlex
import subprocess
import time
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from functools import partial
from pathlib import Path
from typing import Any, Final

from agentprov.devrun import plan as devrun
from agentprov.jobs.follow import ProgressState, Rates, TailReader, eta_text, last_heartbeat_offset
from agentprov.jobs.record import abandoned_mark, read_json
from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPersistentModelIndex, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QShowEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QMenu,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTableView,
    QTableWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from agentprov_gui import platform_limits
from agentprov_gui import text as T
from agentprov_gui.jobs import batch as batch_client
from agentprov_gui.jobs.batch import Batch
from agentprov_gui.jobs.commands import CONFORMANCE_OPTION, FORMS, FormError, JobSpec, build_spec, resume_spec
from agentprov_gui.jobs.manager import Job, JobManager, SpawnRefused, cli_options, tail_bytes
from agentprov_gui.readmodel.corpus import summarise
from agentprov_gui.ui import theme
from agentprov_gui.ui.detail import fill_rows
from agentprov_gui.ui.forms import (
    CommandCard,
    FormPage,
    FormSection,
    StatusBadge,
    caption,
    heading,
    link_button,
)
from agentprov_gui.ui.jobdialog import JobDialog
from agentprov_gui.ui.platformnotice import PlatformNotice, gate, notifier
from agentprov_gui.ui.safe import (
    CRITICAL,
    INFORMATION,
    WARNING,
    ReadOnlyText,
    SafeLabel,
    ask,
    help_tooltip,
    is_tooltip_role,
    safe_message_box,
    safe_tooltip,
    set_control_tooltip,
    set_header_tooltips,
    set_tab_tooltip,
)
from agentprov_gui.ui.worker import run_off_ui, submit

__all__ = ["JobInfo", "JobsModel", "RunsPage", "job_commands", "job_status", "live_facts"]

TICK_MS: Final = 250
LIST_MS: Final = 1000
SESSIONS_MS: Final = 30_000
#: how often the selected running live run's working corpus is read for ``live.caps`` (in the pool)
LIVE_S: Final = 5.0
#: the largest working ``corpus.json`` read for those facts (its ``live.sessions`` grows with the run)
MANIFEST_BYTES: Final = 16 * 1024 * 1024


class Follower:
    """The progress fold of one job, read incrementally."""

    def __init__(self, job: Job) -> None:
        path = job.file("progress.jsonl")
        self.reader = TailReader(path)
        offset = last_heartbeat_offset(path)
        if offset:
            self.reader.seek_to_offset(offset)
        self.state = ProgressState()
        self.rates = Rates()
        self.finished = False

    def tick(self) -> None:
        if self.finished:  # a closed reader would reopen at offset 0 and fold the file twice
            return
        for ev in self.reader.read():
            self.state.apply(ev)
        self.rates.update(time.monotonic(), self.state.done)

    def finish(self) -> None:
        """One step of the final fold of an ended job; at the end of the file, release the handle (GR-27).

        GR-44: each call reads one tick's budget (a 1 MiB read), so a large ended job folds across refreshes and
        never stalls the UI thread; the handle stays open (and ``finished`` false) until the fold is caught up.
        """
        if self.finished:
            return
        offset = self.reader.offset
        self.tick()
        if not self.reader.lagging_bytes or self.reader.offset == offset:
            self.reader.close()
            self.finished = True


# --------------------------------------------------------------------------------------------- job states (D-1061)
@dataclass(slots=True)
class JobInfo:
    """What a job's files say beyond its record: the cancel mark (``abandoned.json``, D-1061) and the last control
    request written for it (``control.json``: ``drain`` or ``stop``, D-394)."""

    abandoned: bool = False
    control: str | None = None

    @classmethod
    def read(cls, job: Job, previous: JobInfo | None = None) -> JobInfo:
        """``previous``: what was read for the job on an earlier refresh after it ended; its control request no longer
        changes, so only the cancel mark is read again."""
        if previous is not None and job.state != "running":
            return cls(abandoned_mark(job.directory) is not None, previous.control)
        control = None
        if job.record.get("control_file"):
            doc = read_json(job.file("control.json"), 4096)
            request = doc.get("request") if doc is not None else None
            control = request if request in ("drain", "stop") else None
        return cls(abandoned_mark(job.directory) is not None, control)


def job_status(job: Job, info: JobInfo, *, outcome: str | None = None) -> tuple[str, str]:
    """The state word of ``job`` and its badge tint. ``outcome``: the progress file's end outcome when the app folded
    it (``drained``: the job finished its in-flight units after a Pause and stopped early, exit 0)."""
    if job.state == "running":
        if info.abandoned or info.control == "stop" or job.record.get("stop_requested_at"):
            return "Stopping", "warn"
        if info.control == "drain":
            return "Pausing", "warn"
        return "Running", "info"
    if job.state == "spawning":
        return "Starting", "info"
    if info.abandoned:
        return "Cancelled", "neutral"
    if job.state == "unobserved":
        return "Ended, unobserved", "warn"
    if job.exit_code == 0 and (outcome == "drained" or (outcome is None and info.control == "drain")):
        return "Paused", "info"
    if job.exit_code == 130 or job.outcome in ("interrupted", "killed"):
        return "Stopped", "warn"
    if job.exit_code == 0:
        return "Ended", "ok"
    return "Failed", "bad"


def state_cell(job: Job, status: tuple[str, str]) -> str:
    """The list's state text: the state word, the exit code once there is one, a stale lock."""
    word = status[0]
    if job.exit_code is not None and job.state != "running":
        word += f" (exit {job.exit_code})"
    return word + (" · stale lock" if job.stale_lock else "")


TIER_WORDS: Final = {"R0": "R0 · read-only", "R1": "R1 · writes", "R2": "R2 · network or paid"}


def local_created(stamp: object) -> str:
    """``job.json``'s ``created`` (UTC) in this computer's time zone, named."""
    from agentprov_gui.live.pricerefresh import local_time_text

    if not isinstance(stamp, str):
        return ""
    try:
        when = dt.datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.UTC)
    except ValueError:
        return T.clean(stamp, 40)
    return local_time_text(when)


def job_commands(job: Job, info: JobInfo) -> list[tuple[str, tuple[str, ...]]]:
    """The terminal commands of ``job`` (D-1061), each built from its ``jobs`` form with the job's real id: pause
    (when it runs with a control file), stop, resume (unless cancelled), cancel (unless an ended job is cancelled
    already), follow."""
    running = job.state == "running"

    def argv(name: str, **values: Any) -> tuple[str, ...]:
        return build_spec(FORMS[f"jobs_{name}"], {"job_id": job.job_id, "format": None, **values}).argv

    out: list[tuple[str, tuple[str, ...]]] = []
    if running and job.record.get("control_file"):
        out.append(("pause: finish what is in progress, start nothing new", argv("drain")))
    if running:
        out.append(("stop now", argv("stop")))
    if not info.abandoned:
        out.append(("resume once it has ended" if running else "resume", argv("resume")))
    if running or not info.abandoned:
        out.append(("cancel: stop, and never resume", argv("cancel")))
    out.append(("follow progress", argv("follow")))
    return out


def _form_argv(name: str, **values: Any) -> tuple[str, ...]:
    return build_spec(FORMS[name], {"format": None, **values}).argv


def batch_commands(batch: Batch | None, running: bool) -> list[tuple[str, tuple[str, ...]]]:
    """The terminal commands of the selected batch (its show, resume and, while it runs, stop), each built from its
    ``batch`` form; without a selection, the list."""
    out: list[tuple[str, tuple[str, ...]]] = [("every batch", _form_argv("batch_list"))]
    if batch is None:
        return out
    out.append(("this batch's steps", _form_argv("batch_show", batch_id=batch.batch_id)))
    out.append(("confirm its held steps and go on", _form_argv("batch_resume", batch_id=batch.batch_id,
                                                               confirm_r2=True)))
    if running:
        out.append(("stop it and its running steps", batch_client.stop_argv(batch.batch_id, steps=True, fmt=None)))
    return out


def dev_commands(batch: Batch | None, live: Sequence[Job]) -> list[tuple[str, tuple[str, ...]]]:
    """The dev run's terminal commands: plan, start and list, and the stops of the running dev run (its batch, and
    each running live dev-run job)."""
    out: list[tuple[str, tuple[str, ...]]] = [
        ("the plan", _form_argv("devrun_plan")),
        ("start one (the imports read the fetch cache: R2)", _form_argv("devrun_start", confirm_r2=True)),
        ("the dev runs kept", _form_argv("devrun_list")),
    ]
    if batch is not None:
        out.append(("stop the running dev run", batch_client.stop_argv(batch.batch_id, steps=True, fmt=None)))
    out += [("stop the running live dev run", _form_argv("jobs_stop", job_id=j.job_id)) for j in live]
    return out


def _decimal_usd(value: object) -> str | None:
    """A recorded USD amount (a decimal string, H.1.4(3)) as ``$1.23`` (at least two decimals), or ``None``."""
    if isinstance(value, bool) or not isinstance(value, str | int):
        return None
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        return None
    if not amount.is_finite() or amount < 0:
        return None
    return f"${amount:,.2f}" if amount == amount.quantize(Decimal("0.01")) else f"${amount:,}"


def _count(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def live_block(corpus: Path) -> dict[str, Any] | None:
    """The ``live`` block of a run's working ``corpus.json`` (``DIR.partial``; H.2.2), read strictly; ``None`` when
    it is absent, too large or unreadable. Called in the pool."""
    from agentprov.corpus.layout import MANIFEST, PARTIAL_SUFFIX

    final = corpus.with_name(corpus.name.removesuffix(PARTIAL_SUFFIX))
    doc = read_json(final.with_name(final.name + PARTIAL_SUFFIX) / MANIFEST, MANIFEST_BYTES)
    live = doc.get("live") if doc is not None else None
    return live if isinstance(live, dict) else None


def live_facts(live: dict[str, Any] | None) -> dict[str, str]:
    """The facts a live run's ``live`` block records, as text (only those it has): ``calls`` (billed model calls,
    with the cap), ``cost`` (the spend's upper bound, with the cap), ``model``, ``endpoint``, ``traces``."""
    out: dict[str, str] = {}
    if not live:
        return out
    recorded = live.get("caps")
    caps: dict[str, Any] = recorded if isinstance(recorded, dict) else {}
    billed, cap = _count(caps.get("billed_calls")), _count(caps.get("max_calls"))
    if billed is not None:
        out["calls"] = f"{billed:,}" + (f" of {cap:,} cap" if cap is not None else "")
    spend, max_cost = _decimal_usd(caps.get("spend_upper_bound_usd")), _decimal_usd(caps.get("max_cost_usd"))
    if spend is not None:
        out["cost"] = spend + (f" of {max_cost} cap" if max_cost is not None else "")
    model = live.get("model_requested")
    if isinstance(model, str) and model:
        out["model"] = T.clean(model, 80)
    endpoint = live.get("endpoint")
    if isinstance(endpoint, str) and endpoint and endpoint != "scripted":
        out["endpoint"] = T.clean(endpoint, 60)
    if live.get("transport") == "scripted":
        out["model"] = "a scripted model"
    traces = _count(live.get("jobs"))
    if traces:
        out["traces"] = f"{traces} trace{'s' if traces != 1 else ''} at once"
    return out


def control_texts(run: bool) -> list[tuple[str, str]]:
    """What each control does, for a live run (cells, caps) or any other job (units)."""
    unit = "cells" if run else "units"
    return [
        ("Pause", f"Finishes the {unit} in progress and starts no new ones; Resume goes on from there. Only for a job "
                  "started with a control file (Run Live's jobs are)."),
        ("Resume", "Starts the same command again as a new job, after the tier confirmation. "
                   + ("Recorded cells are skipped, and the caps carry over: they count the whole working corpus."
                      if run else "The command's own resume rules decide what is redone.")),
        ("Stop", f"Stops now: the {unit} in progress are aborted and recorded as aborted"
                 + ("; they count against the caps and run again on Resume." if run else ".")
                 + " Force Kill… is for a stop that hangs."),
        ("Cancel", "Stops as Stop does and marks the " + ("run" if run else "job") + " cancelled, so it is never "
                   "resumed. Nothing is deleted: its working corpus stays where it is."),
    ]


class JobsModel(QAbstractTableModel):
    HEADERS: Final = ("Job", "Command", "State", "Risk", "Progress", "Started")
    HEADER_TIPS: Final = (
        "The job's label (job.json label); rest the pointer on a row for its job id",
        "The command the job runs (import, validate, run …)",
        "Running, Pausing (a Pause was asked for), Stopping, Paused (it finished what was in progress and stopped "
        "early, exit 0), Stopped (exit 130), Cancelled (agentprov jobs cancel: never resumed), Ended (exit 0), "
        "Failed (another exit code), or Ended, unobserved: its supervisor is gone and no end was recorded (killed from "
        "outside, or the machine restarted). The exit code is in brackets",
        "The job's risk tier: R0 read-only, R1 writes local data, R2 network, downloads or paid calls",
        "Units done (of the total, with the share) from the job's progress events; empty until the app follows the job",
        "When the job was created (job.json created, recorded in UTC), in this computer's time zone",
    )

    def __init__(self) -> None:
        super().__init__()
        self.jobs: list[Job] = []
        self.progress: dict[str, str] = {}
        #: each job's state word and tint (:func:`job_status`), set by the page on each refresh
        self.states: dict[str, tuple[str, str]] = {}

    def set_jobs(self, jobs: list[Job]) -> None:
        self.beginResetModel()
        self.jobs = jobs
        self.endResetModel()

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self.jobs)

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self.HEADERS)

    def status(self, job: Job) -> tuple[str, str]:
        return self.states.get(job.job_id) or job_status(job, JobInfo())

    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        job = self.jobs[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            tier = str(job.record.get("tier", ""))
            values = (T.clean(job.record.get("label", ""), 80), job.command, state_cell(job, self.status(job)),
                      TIER_WORDS.get(tier, T.clean(tier, 10)), self.progress.get(job.job_id, ""),
                      local_created(job.record.get("created")))
            return values[index.column()]
        if role == Qt.ItemDataRole.ForegroundRole and index.column() == 2:  # the tint repeats the words
            t = theme.tokens()
            return QColor({"ok": t.ok_fg, "warn": t.warn_fg, "bad": t.bad_fg, "info": t.info_fg}.get(
                self.status(job)[1], t.neutral_fg))
        if is_tooltip_role(role):
            return safe_tooltip(job.job_id)
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if orientation != Qt.Orientation.Horizontal:
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return self.HEADERS[section]
        if is_tooltip_role(role):
            return help_tooltip(self.HEADER_TIPS[section])
        return None


def _table(headers: list[str], name: str, parent: QWidget) -> QTableWidget:
    t = QTableWidget(0, len(headers), parent)
    t.setAccessibleName(name)
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().setVisible(False)
    t.horizontalHeader().setStretchLastSection(True)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    return t


def _card(parent: QWidget, name: str, *, margins: int = 16, spacing: int = 10) -> tuple[QFrame, QVBoxLayout]:
    """A rounded card (the form style's card) with a vertical layout."""
    frame = QFrame(parent)
    frame.setProperty("apvRole", "card")
    frame.setAccessibleName(name)
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(margins, margins - 2, margins, margins - 2)
    lay.setSpacing(spacing)
    return frame, lay


def _titled(title: str, widget: QWidget, parent: QWidget, note: str = "") -> QWidget:
    """A small capitalised heading over ``widget`` (a table or a text pane), with an optional grey note under it."""
    box = QWidget(parent)
    box.setAccessibleName(title)
    lay = QVBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(6)
    head = heading(title, parent=box)
    head.setContentsMargins(10, 0, 0, 0)
    lay.addWidget(head)
    lay.addWidget(widget, 1)
    if note:
        n = caption(note, name=f"{title}: note", parent=box)
        n.setContentsMargins(10, 0, 0, 0)
        lay.addWidget(n)
    return box


class RunsPage(QWidget):
    open_corpus = Signal(str)
    open_log = Signal(str)  # job id
    jobs_changed = Signal(int, int)  # running, ended

    def __init__(self, manager: JobManager, settings: Any, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAccessibleName("Runs")
        self.manager, self.settings = manager, settings
        self.followers: dict[str, Follower] = {}
        self.batches: list[Batch] = Batch.load_all(manager.home)
        self._batch_rows: list[Batch] = []  # the batch of each row of the batch table
        self.selected: Job | None = None
        self._options: dict[tuple[str, ...], frozenset[str]] = {}
        #: ``agentprov settings`` values by prefix, read when first needed and cleared on Settings › OK (D-700)
        self.stored: dict[str, dict[str, Any]] = {}
        self.opened_corpus: Path | None = None
        self._capped: set[str] = set()
        #: each job's cancel mark and control request (D-1061), read on each refresh
        self.infos: dict[str, JobInfo] = {}
        #: a live run's ``live`` block (its working corpus), when it was last read, and the reads in the pool
        self._live: dict[str, dict[str, Any] | None] = {}
        self._live_at: dict[str, float] = {}
        self._live_busy: set[str] = set()
        self._live_final: set[str] = set()
        self._build()
        self.manager.load_all()
        self.refresh()
        self.tick_timer = QTimer(self)
        self.tick_timer.timeout.connect(self._tick)
        self.tick_timer.start(TICK_MS)
        self.list_timer = QTimer(self)
        self.list_timer.timeout.connect(self.refresh)
        self.list_timer.start(LIST_MS)
        self.sessions_timer = QTimer(self)
        self.sessions_timer.timeout.connect(self._sessions_refresh)

    # ------------------------------------------------------------------------------------------ widgets
    def _button(self, text: str, name: str, slot: Any, tip: str, *, link: bool = False,
                parent: QWidget | None = None) -> QPushButton:
        b = link_button(text, name=name, parent=parent or self) if link else QPushButton(text, parent or self)
        b.setAccessibleName(name)
        b.setAutoDefault(False)
        b.clicked.connect(slot)
        set_control_tooltip(b, tip)
        return b

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(3 * theme.SPACE, 20, 3 * theme.SPACE, 2 * theme.SPACE)
        lay.setSpacing(12)
        bar = QHBoxLayout()
        bar.setSpacing(8)
        title = SafeLabel("Runs", name="Runs title", parent=self, selectable=False)
        title.setFont(theme.scaled_font("title"))
        bar.addWidget(title)
        bar.addSpacing(12)
        self.live_btn = self._button(
            "▶ Run Live…", "Run live", self.run_live,
            "Configures a live capture (agentprov run), shows its estimate, and starts it as a job after the "
            "confirmation.")
        bar.addWidget(self.live_btn)
        self.new_btn = QPushButton("New Job ▾", self)
        self.new_btn.setAccessibleName("New job")
        menu = QMenu(self.new_btn)
        for key, form in FORMS.items():
            if form.menu:
                menu.addAction(form.title, partial(self.new_job, key))
        self.new_btn.setMenu(menu)
        set_control_tooltip(self.new_btn, "A form for each command (import, validate, derive, recompute, CI …). Each "
                                          "shows the exact command and its tier, and starts it as a job after the "
                                          "tier's confirmation.")
        bar.addWidget(self.new_btn)
        bar.addWidget(self._button(
            "Dev Run…", "Start a dev run", self.start_dev_run,
            "A quick end-to-end check: a few executions of every importable part from the fetch cache, each imported "
            "into a scratch corpus under $AGENTPROV_HOME/dev-runs, then validated and recomputed as one batch. Shows "
            "the plan first "
            "(agentprov devrun plan, devrun start --confirm-r2); the choices are in Settings › Dev Runs."))
        self.live_dev_btn = self._button(
            "Live Dev Run…", "Start a live dev run", self.start_live_dev_run,
            "Opens Run Live preset for a small capture (scripted by default) into a new dev-run folder, with the "
            "tasks, attacks and the call and cost caps from Settings › Dev Runs.")
        bar.addWidget(self.live_dev_btn)
        bar.addStretch(1)
        note = caption("Each job and batch runs on its own: it keeps going when this window closes.",
                       name="Batch note", parent=self)
        note.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        bar.addWidget(note)
        lay.addLayout(bar)
        # D-1064: where live runs are refused, Run Live… and Live Dev Run… stay, disabled with the reason, and say so
        self.platform_notice = PlatformNotice("live_runs", name="Live runs on this platform", parent=self)
        lay.addWidget(self.platform_notice)
        notifier().changed.connect(self._platform_gate)
        self._platform_gate()
        self.tabs = QTabWidget(self)
        self.tabs.setAccessibleName("Runs views")
        lay.addWidget(self.tabs, 1)
        self._build_jobs_tab()
        self._build_batches_tab()
        self._build_dev_tab()
        self._build_sessions_tab()
        self.tabs.currentChanged.connect(self._tab_changed)

    def _platform_gate(self) -> None:
        limit = self.platform_notice.refresh()
        for button in (self.live_btn, self.live_dev_btn):
            gate(button, limit)

    def _build_jobs_tab(self) -> None:
        jobs_tab = QWidget(self.tabs)
        jl = QVBoxLayout(jobs_tab)
        jl.setContentsMargins(0, 12, 0, 0)
        split = QSplitter(Qt.Orientation.Vertical, jobs_tab)
        split.setChildrenCollapsible(False)
        self.model = JobsModel()
        self.view = QTableView(split)
        self.view.setAccessibleName("Jobs")
        self.view.setModel(self.model)
        self.view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.view.verticalHeader().setVisible(False)
        header = self.view.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # the label takes the room; the rest is sized
        for column, width in enumerate((0, 110, 170, 150, 120, 200)):
            if width:
                self.view.setColumnWidth(column, width)
        self.view.setWordWrap(False)
        self.view.setShowGrid(False)
        self.view.setAlternatingRowColors(True)
        self.view.setMinimumHeight(120)
        self.view.selectionModel().currentRowChanged.connect(self._row_changed)
        set_control_tooltip(self.view, "Every job, running and ended; select one for its details. Jobs keep running "
                                       "when this window closes.")
        split.addWidget(self.view)
        self.detail = FormPage(name="Job details", parent=split, max_width=16_777_215)
        self.detail.layout_.setSpacing(16)
        inner = self.detail.widget()
        outer = inner.layout() if inner is not None else None
        if outer is not None:
            outer.setContentsMargins(0, 16, 0, 8)
        col = self.detail.column
        self._build_header(col)
        # what each control does, beside the same in a terminal
        pair = QWidget(col)
        pair.setAccessibleName("Controls and terminal commands")
        pl = QHBoxLayout(pair)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(24)
        self.controls_help = FormSection("What each control does", parent=pair)
        self.control_help: list[SafeLabel] = []
        for name, text in control_texts(False):
            label = SafeLabel(text, name=f"What {name} does", parent=self.controls_help.card, selectable=False)
            label.setProperty("apvRole", "secondary")
            label.setWordWrap(True)
            label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            self.controls_help.add_row(name, label)
            self.control_help.append(label)
        pl.addWidget(self.controls_help, 1, Qt.AlignmentFlag.AlignTop)
        right = QWidget(pair)
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(6)
        self.command_card = CommandCard(name="Job terminal commands", title="The same in a terminal", parent=right)
        rl.addWidget(self.command_card)
        self.command_note = caption("Commands use the job's real id.", name="Job terminal commands: note",
                                    parent=right)
        self.command_note.setContentsMargins(10, 0, 0, 0)
        rl.addWidget(self.command_note)
        rl.addStretch(1)
        pl.addWidget(right, 1)
        self.detail.add(pair)
        # the command, counts, codes and stderr
        self.argv = ReadOnlyText(name="Job command", parent=col, wrap=True)
        self.argv.setMaximumHeight(70)
        self.detail.add(_titled("Command", self.argv, col))
        tables = QWidget(col)
        tables.setAccessibleName("Counts and codes")
        tl = QHBoxLayout(tables)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(24)
        self.counts = _table(["Status", "Units"], "Counts by status", tables)
        self.codes = _table(["Code", "Units"], "Failures and issues by code", tables)
        self.codes.cellDoubleClicked.connect(self._code_clicked)
        set_header_tooltips(self.counts, ["The status a finished unit reported in the job's progress events",
                                          "How many units ended with that status"])
        set_header_tooltips(self.codes, ["A failure or issue code finished units reported; double-click a row to "
                                         "open the job's log on the Logs page",
                                         "How many units reported that code"])
        for t in (self.counts, self.codes):
            t.setMinimumHeight(110)
            t.setMaximumHeight(180)
        tl.addWidget(_titled("Counts by status", self.counts, tables))
        tl.addWidget(_titled("Failures and issues by code", self.codes, tables))
        self.detail.add(tables)
        self.stderr = ReadOnlyText(name="Job stderr (last 64 KiB, escaped)", parent=col)
        self.stderr.setMinimumHeight(100)
        self.stderr.setMaximumHeight(160)
        self.detail.add(_titled("Error output", self.stderr, col, "The last 64 KiB of the job's stderr, escaped."))
        split.addWidget(self.detail)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 3)
        jl.addWidget(split)
        self.tabs.addTab(jobs_tab, "Jobs")
        set_tab_tooltip(self.tabs, 0, "Every job and the details of the selected one. A job is a detached agentprov "
                                      "process: it keeps running when this window closes.", wrap=True)

    def _build_header(self, col: QWidget) -> None:
        """The selected job's header card: title, state badge, progress, facts and the controls."""
        card, cl = _card(col, "Selected job")
        top = QHBoxLayout()
        top.setSpacing(12)
        names = QVBoxLayout()
        names.setSpacing(2)
        self.title = SafeLabel("Select a job", name="Job title", parent=card)
        font = theme.scaled_font("title")
        font.setPointSizeF(max(7.0, font.pointSizeF() * 0.9))
        self.title.setFont(font)
        self.title.setWordWrap(True)
        self.title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        names.addWidget(self.title)
        self.subtitle = caption("", name="Job started", parent=card)
        set_control_tooltip(self.subtitle, "When the job started (this computer's time zone), what it runs and, once "
                                           "it ended, its exit code.")
        names.addWidget(self.subtitle)
        top.addLayout(names, 1)
        self.state_badge = StatusBadge("", name="Job state", parent=card)
        set_control_tooltip(self.state_badge, JobsModel.HEADER_TIPS[2])
        top.addWidget(self.state_badge, 0, Qt.AlignmentFlag.AlignTop)
        cl.addLayout(top)
        self.bar = QProgressBar(card)
        self.bar.setAccessibleName("Job progress")
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        set_control_tooltip(self.bar, "Units done of the total from the selected job's progress events. The bar "
                                      "moves without a total while a running job has not reported one, and is full "
                                      "once a job without one has ended.")
        cl.addWidget(self.bar)
        self.facts = SafeLabel("", name="Job facts", parent=card)
        self.facts.setWordWrap(True)
        self.facts.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        set_control_tooltip(self.facts, "Units done and in progress; while the job runs, its rate and ETA range. For a "
                                        "live run, cells, and from its working corpus (corpus.json live.caps) the "
                                        "billed model calls and the spend's upper bound so far, each against its cap; "
                                        "a run without caps has none.")
        cl.addWidget(self.facts)
        self.warning = StatusBadge("", name="Job warning", kind="warn", parent=card)
        set_control_tooltip(self.warning, "Shown when the job needs attention: its PROV conformance check was skipped "
                                          "(the corpus is unvalidated: seal and release are refused until a full "
                                          "recompute validates it into a new corpus), or it left a stale lock (start "
                                          "the job again with --break-stale-lock).")
        self.warning.setWordWrap(True)
        self.warning.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        cl.addWidget(self.warning)
        self.notes = caption("", name="Job notes", parent=card)
        set_control_tooltip(self.notes, "Dropped or skipped progress events, and a command that writes none.")
        cl.addWidget(self.notes)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.drain_btn = self._button(
            "Pause", "Pause the job", self.drain,
            "Finishes the units in progress and starts no new ones (a drain: agentprov jobs drain ID); Resume goes on "
            "from there. Only for a running job started with a control file (Run Live's jobs are).", parent=card)
        self.resume_btn = self._button(
            "Resume", "Resume the job as a new job", self.resume,
            "Starts the same command again as a new job, after the tier confirmation; the command's own resume rules "
            "decide what is redone: a live run skips its recorded cells and its caps carry over (agentprov jobs "
            "resume ID). Never for a cancelled job.", parent=card)
        self.stop_btn = self._button(
            "Stop…", "Stop the job", self.stop,
            "Asks, then stops the job gracefully: units in flight are aborted and recorded as aborted, and the CLI "
            "flushes, releases its lock and exits with code 130 (agentprov jobs stop ID).", parent=card)
        self.cancel_btn = self._button(
            "Cancel Run…", "Cancel the job", self.cancel,
            "Asks, then stops the job as Stop does and marks it cancelled, so it is never resumed (agentprov jobs "
            "cancel ID; D-1061). Nothing is deleted: its working corpus stays. For a job that has ended, only the "
            "mark is written.", parent=card)
        self.kill_btn = self._button(
            "Force Kill…", "Force kill the job", self.kill,
            "Asks, then kills the job's whole process tree without clean-up; its corpus lock stays (stale). Use it "
            "only after Stop has had time to work (agentprov jobs kill ID --yes).", parent=card)
        for b in (self.cancel_btn, self.kill_btn):  # they end the job for good: the destructive style
            theme.mark_destructive(b)
        for b in (self.drain_btn, self.resume_btn, self.stop_btn, self.cancel_btn, self.kill_btn):
            actions.addWidget(b)
        actions.addStretch(1)
        self.log_btn = self._button("Open Log", "Open the job log", self._open_log,
                                    "Shows the job's log on the Logs page (agentprov jobs follow ID --log).",
                                    link=True, parent=card)
        self.viewer_btn = self._button("Open in Viewer", "Open the written corpus in the viewer", self._open_viewer,
                                       "Opens the corpus the job writes in the Viewer.", link=True, parent=card)
        self.copy_btn = self._button("Copy Command", "Copy the job command", self.copy_command,
                                     "Copies the job's full command line to the clipboard.", link=True, parent=card)
        self.preview_btn = self._button(
            "Live Preview (experimental)…", "Open the live preview (off by default)", self.open_preview,
            "Opens a provisional graph of the selected running live capture (agentprov run); experimental, and off "
            "until you open it.", link=True, parent=card)
        self.preview_btn.setEnabled(False)
        for b in (self.log_btn, self.viewer_btn, self.copy_btn, self.preview_btn):
            actions.addWidget(b)
        cl.addLayout(actions)
        for b in (self.drain_btn, self.resume_btn, self.stop_btn, self.cancel_btn, self.kill_btn, self.log_btn,
                  self.viewer_btn, self.copy_btn):
            b.setEnabled(False)
        self.detail.add(card)

    def _build_batches_tab(self) -> None:
        batch_tab = QWidget(self.tabs)
        bl = QVBoxLayout(batch_tab)
        bl.setContentsMargins(0, 12, 0, 0)
        bl.setSpacing(12)
        self.batch_table = _table(["Batch", "Step", "Job", "State", "Exit code", "Note"], "Batch steps", batch_tab)
        set_header_tooltips(self.batch_table, [
            "The batch's label (the last 20 batches are listed)",
            "The step's place in the batch",
            "The step's job label",
            "pending, held (an R2 step waits for Resume Batch…), running, done, failed, blocked or skipped",
            "The step's exit code once it ended",
            "Why a step is held, blocked, skipped or a fallback"])
        self.batch_table.setShowGrid(False)
        for column, width in enumerate((220, 50, 260, 90, 80)):
            self.batch_table.setColumnWidth(column, width)
        bl.addWidget(_titled("Batch steps", self.batch_table, batch_tab,
                             "Each batch is an ordered list of jobs that runs as one job of its own (agentprov batch "
                             "run), so it keeps going when this window closes."), 1)
        self.batch_card = CommandCard(name="Batch terminal commands", title="The same in a terminal", parent=batch_tab)
        bl.addWidget(self.batch_card)
        batch_actions = QHBoxLayout()
        self.resume_batch_btn = self._button(
            "Resume Batch…", "Confirm the held steps of the selected batch", self.resume_batch,
            "Confirms each held step (network or paid calls) of the selected row's batch, then starts a new driver "
            "job for it (agentprov batch resume ID --confirm-r2). A cancelled confirmation leaves the batch held.",
            parent=batch_tab)
        batch_actions.addWidget(self.resume_batch_btn)
        self.stop_batch_btn = self._button(
            "Stop Batch…", "Stop the selected batch", self.stop_batch,
            "Asks, then stops the selected row's batch: its driver job and every running or queued step job, each "
            "gracefully as Stop on the Jobs tab does, and no further step starts. Its pending steps stay pending; "
            "Resume Batch… goes on from them (agentprov batch stop ID --steps). Only while the batch has a running "
            "job.", parent=batch_tab)
        self.stop_batch_btn.setEnabled(False)
        batch_actions.addWidget(self.stop_batch_btn)
        self.batch_table.currentCellChanged.connect(lambda *_a: self._batch_buttons())
        batch_actions.addStretch(1)
        bl.addLayout(batch_actions)
        self.tabs.addTab(batch_tab, "Batches")
        set_tab_tooltip(self.tabs, 1, "The steps of each batch: an ordered list of jobs that runs as one job of its "
                                      "own (agentprov batch run), so it keeps going when this window closes.",
                        wrap=True)

    def _build_dev_tab(self) -> None:
        dev_tab = QWidget(self.tabs)
        dvl = QVBoxLayout(dev_tab)
        dvl.setContentsMargins(0, 12, 0, 0)
        dvl.setSpacing(12)
        info_card, il = _card(dev_tab, "Dev run", margins=14, spacing=6)
        head = QHBoxLayout()
        self.dev_info = SafeLabel("", name="Dev run facts", parent=info_card)
        self.dev_info.setWordWrap(True)
        self.dev_info.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        head.addWidget(self.dev_info, 1)
        self.dev_badge = StatusBadge("", name="Dev run state", parent=info_card)
        set_control_tooltip(self.dev_badge, "Running while the dev run's batch or one of its live jobs is still going "
                                            "(Stop Dev Run… stops them); not shown otherwise.")
        head.addWidget(self.dev_badge, 0, Qt.AlignmentFlag.AlignTop)
        il.addLayout(head)
        dvl.addWidget(info_card)
        self.dev_table = _table(["Part", "Import", "Mapped", "With issues", "Degenerate", "Failed",
                                 "Most frequent issues", "Validate", "Recompute", "Seconds"], "Dev run summary",
                                dev_tab)
        set_header_tooltips(self.dev_table, [
            "The source part (source/part) the row covers",
            "How the part's import ended (… while it has not)",
            "Executions the import mapped",
            "Executions sealed with issues",
            "Degenerate AERs: the header, run scope and seal only, for an execution that could not be mapped",
            "Executions whose import failed",
            "The import's five most frequent issue codes, with their counts",
            "How agentprov validate of the part's scratch corpus ended",
            "How agentprov recompute --dry-run ended, with its number of differences",
            "Wall-clock seconds of each of the part's jobs, by command"])
        self.dev_table.setShowGrid(False)
        self.dev_table.setColumnWidth(0, 240)
        self.dev_table.setColumnWidth(6, 220)
        dvl.addWidget(_titled("Parts", self.dev_table, dev_tab), 1)
        self.dev_card = CommandCard(name="Dev run terminal commands", title="The same in a terminal", parent=dev_tab)
        dvl.addWidget(self.dev_card)
        dev_actions = QHBoxLayout()
        self.stop_dev_btn = self._button(
            "Stop Dev Run…", "Stop the dev run", self.stop_dev_run,
            "Asks, then stops the latest running dev run: its batch's driver job and every running or queued step "
            "job, each gracefully, and no further part starts (agentprov batch stop ID --steps); a running live dev "
            "run's job is stopped as Stop on the Jobs tab does (agentprov jobs stop ID). Parts not started stay "
            "pending; Resume Batch… on the Batches tab goes on from them.", parent=dev_tab)
        self.stop_dev_btn.setEnabled(False)
        dev_actions.addWidget(self.stop_dev_btn)
        dev_actions.addStretch(1)
        dvl.addLayout(dev_actions)
        self.tabs.addTab(dev_tab, "Dev Runs")
        set_tab_tooltip(self.tabs, 2, "The latest dev run: one row per part with its import, validate and recompute "
                                      "results. Start one with Dev Run…; Settings › Dev Runs holds the choices.",
                        wrap=True)

    def _build_sessions_tab(self) -> None:
        sess_tab = QWidget(self.tabs)
        sl = QVBoxLayout(sess_tab)
        sl.setContentsMargins(0, 12, 0, 0)
        sl.setSpacing(12)
        self.sess_info = caption("Read-only: tools/queue_status.py --json every 30 s while this tab is visible.",
                                 name="Sessions facts", parent=sess_tab)
        self.sess_info.setContentsMargins(10, 0, 0, 0)
        self.sessions = _table(["Session", "State", "Waits on", "Branch", "Uncommitted changes", "Suite green on head",
                                "Idle", "Flags"], "Development sessions", sess_tab)
        set_header_tooltips(self.sessions, [
            "The session's name in its status file (tools/session_status.py)",
            "The state the session reported (building, suite-running, green, waiting-for-user, parked, done …)",
            "What the session waits on, as recorded",
            "The session's branch",
            "Whether its worktree had uncommitted changes when it reported (dirty)",
            "True when its last suite ran green on its current head (suite on head)",
            "Time since the session's last heartbeat",
            "STALE, DEAD, WAITING-ON-USER, SUITE-OLD, GONE, INVALID or HEAD-MOVED; sessions waiting on you are "
            "listed first"])
        self.sessions.setShowGrid(False)
        sl.addWidget(_titled("Development sessions", self.sessions, sess_tab), 1)
        sl.addWidget(self.sess_info)
        self.tabs.addTab(sess_tab, "Sessions")
        set_tab_tooltip(self.tabs, 3, "A read-only view of the development sessions that share this machine "
                                      "(tools/queue_status.py --json, every 30 s while this tab is visible).",
                        wrap=True)

    # ------------------------------------------------------------------------------------------ jobs
    def options_for(self, words: tuple[str, ...]) -> frozenset[str]:
        if words not in self._options:
            self._options[words] = run_off_ui(self, lambda: cli_options(self.manager.cli, words))
        return self._options[words]

    def tool_program(self, tool: str) -> tuple[str, ...] | None:
        checkout, python = self.manager.cli.checkout, self.manager.cli.python
        if checkout is None or not python or not (checkout / tool).is_file():
            return None
        return (*python, str(checkout / tool), "-C", str(checkout))

    def new_job(self, key: str, preset: dict[str, Any] | None = None) -> None:
        form = FORMS[key]
        if form.tool is not None:
            program = self.tool_program(form.tool)
            if program is None:
                safe_message_box(self, form.title, f"{form.tool} is not in the configured checkout.").exec()
                return
            dlg = JobDialog(form, program=program, preset=preset, parent=self)
            if dlg.exec() and dlg.spec is not None:
                from dataclasses import replace

                # D-704: `agentprov jobs start --tool` runs it (resolved inside the checkout's tools/ by the CLI)
                self.start(replace(dlg.spec, extra={**dict(dlg.spec.extra or {}), "tool": form.tool}))
            return
        from agentprov_gui.ui.settings_panes import int_setting

        # GR-64: the Compute pane's range, so a corrupted store never overflows the dialog's spin box.
        default_jobs = int_setting(self.stored_settings("compute."), f"compute.jobs.{form.words[0]}", 0, 0, 512)
        if default_jobs > 0 and any(f.key == "jobs" for f in form.fields):
            preset = {"jobs": default_jobs, **(preset or {})}
        opts = self.options_for(form.words) if self.manager.cli.available else frozenset()
        conformance = CONFORMANCE_OPTION if CONFORMANCE_OPTION in opts else None
        dlg = JobDialog(form, program=self.manager.cli.program, preset=preset, conformance_option=conformance,
                        parent=self)
        if dlg.exec() and dlg.spec is not None:
            self.start(dlg.spec, control="--control-file" in opts)

    HEAVY: Final = ("import", "derive", "recompute", "validate", "verify", "render", "package_seal",
                    "package_deposit")

    def run_live(self, preset: Any = None, *, dev_run: bool = False, call_cap: int | None = None,
                 cost_cap: float | None = None) -> Job | None:
        """Run Live (design §8): the dialog, then the job. A real model's key is read by the CLI itself
        (``run --keychain``, D-702); the estimate is ``agentprov estimate`` (D-701)."""
        from agentprov_gui.ui.runlive import RunLiveDialog

        opts = self.options_for(("run",)) if self.manager.cli.available else frozenset()

        def refresh_record(value: str | None) -> str:  # D-1062: the date the daily price refresh was last started
            if value is not None:
                self.settings.prices_refresh_attempted = value
            return str(self.settings.prices_refresh_attempted)

        dlg = RunLiveDialog(self.manager, home=self.manager.home, checkout=self.manager.cli.checkout,
                            opened=self.opened_corpora(),
                            conformance_option=CONFORMANCE_OPTION if CONFORMANCE_OPTION in opts else None,
                            preset=preset, dev_run=dev_run, call_cap=call_cap, cost_cap=cost_cap, cli_options=opts,
                            parent=self, store=self.settings.store,
                            daily_refresh=True, refresh_record=refresh_record)  # prices.auto_refresh decides
        accepted, start = dlg.exec(), dlg.start
        dlg.deleteLater()  # AU-NG-2: a closed dialog is deleted (a pending result of its own is then dropped)
        if not accepted or start is None:
            return None
        try:
            job = run_off_ui(self, lambda: self.manager.spawn(start.spec, control_file="--control-file" in opts,
                                                              extra_record={"backend": start.backend}))
        except SpawnRefused as exc:
            safe_message_box(self, "Job not started", "The job was not started.",
                             informative=T.line(exc.reason, 400), icon=WARNING).exec()
            return None
        self.refresh()
        self.select(job.job_id)
        return job

    def _enforce_call_cap(self, job: Job, follower: Follower) -> None:
        """Design §19.2: a live dev run stops at its model-call cap (``model_call`` steps): drain when the CLI has the
        control file (D-394), else one SIGTERM. Once per job."""
        cap = job.record.get("call_cap")
        if not isinstance(cap, int) or isinstance(cap, bool) or job.job_id in self._capped:
            return
        if follower.state.step_count("model_call") >= cap:  # absolute: the heartbeat's count after a re-attach
            self._capped.add(job.job_id)
            # AU-GUI-3: in the pool, so the list timer that calls this never waits on a CLI process
            submit(self, lambda _s: self.manager.request(job, "drain") or self.manager.stop(job), lambda _r: None)

    def start_live_dev_run(self) -> Job | None:
        """Design §19.2: a scripted (by default) live run of a few tasks per suite into a dev-run folder, capped."""
        import time as _time

        from agentprov_gui.live.runspec import RunSettings
        from agentprov_gui.ui.runlive import DEV_SCRIPT

        s = self.dev_settings()
        stamp = _time.strftime("%Y%m%dT%H%M%SZ", _time.gmtime())
        n = max(1, s.live_tasks_per_suite)
        preset = RunSettings(
            source="agentdojo", corpus=str(self.manager.home / "dev-runs" / stamp / "live-agentdojo"),
            campaign="devrun", scripted=s.live_transport != "real", script=str(DEV_SCRIPT),
            suites=tuple(s.live_suites), attacks=("direct",)[: s.live_attacks_per_task],
            user_tasks="0" if n == 1 else f"0-{n - 1}", injection_tasks="0" if s.live_attacks_per_task else "")
        return self.run_live(preset, dev_run=True, call_cap=s.live_call_cap or None, cost_cap=s.live_cost_cap)

    def open_preview(self) -> None:
        """D-398 (G4): the provisional live graph of the selected running run job; off until the user opens it."""
        from agentprov_gui.ui.preview import PreviewWindow

        job = self.selected
        if job is None or job.command != "run":
            return
        follower = self.followers.get(job.job_id)
        window = PreviewWindow(self.manager.home, lambda: list(follower.state.sessions) if follower else [],
                               title=str(job.record.get("label", "")), parent=self)
        window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        window.show()

    def opened_corpora(self) -> list[Path]:
        """The corpus open in the Viewer (the estimate's first source, design §8.3); set by the main window."""
        return [self.opened_corpus] if self.opened_corpus is not None else []

    def stored_settings(self, prefix: str) -> dict[str, Any]:
        """The stored ``agentprov settings`` under ``prefix`` (``settings list``; empty when unreadable, which means
        the defaults). Cached until Settings › OK."""
        if prefix not in self.stored:
            from agentprov_gui import settings_client

            values = run_off_ui(self, lambda: settings_client.read(self.manager.call, prefix))
            if values is None:
                return {}
            self.stored[prefix] = values
        return self.stored[prefix]

    def revalidate(self, corpus: str) -> None:
        """Clear the conformance-skip mark the only way there is (user decision 2026-10-15): a full recompute into a new
        corpus, ``recompute --corpus OLD --out NEW --stages sem,prov,validation``, as a detached job. Never in place."""
        final = Path(corpus)
        final = final.with_name(final.name.removesuffix(".partial"))
        out = final.with_name(final.name + "-revalidated")
        n = 2
        while out.exists() or out.with_name(out.name + ".partial").exists():
            out = final.with_name(f"{final.name}-revalidated-{n}")
            n += 1
        self.new_job("recompute", {"corpus": str(final), "dry_run": False, "out": str(out),
                                   "stages": "sem,prov,validation"})

    def start(self, spec: JobSpec, *, control: bool = False) -> Job | None:
        cfg = self.stored_settings("compute.")
        extra = dict(spec.extra or {})
        if (cfg.get("compute.queue_heavy", True) is not False and spec.command in self.HEAVY and not extra.get("tool")
                and "queue_cpu" not in extra and self.manager.cli.checkout is not None
                and os.name == "posix"  # the job queue locks with fcntl: none on Windows (G5 P-3)
                and platform_limits.current().get("job_queue") is None):  # nor where the CLI refuses it (D-1064)
            from dataclasses import replace

            from agentprov_gui.ui.settings_panes import int_setting

            spec = replace(spec, extra={**extra, "queue_cpu": int_setting(cfg, "compute.queue_cpu", 2, 1, 256)})
        try:
            job = run_off_ui(self, lambda: self.manager.spawn(spec, control_file=control))
        except SpawnRefused as exc:
            safe_message_box(self, "Job not started", "The job was not started.",
                             informative=T.line(exc.reason, 400), icon=WARNING).exec()
            return None
        self.refresh()
        self.select(job.job_id)
        return job

    def refresh(self) -> None:
        self.batches = Batch.load_all(self.manager.home)  # each batch's driver job advances it (D-704)
        jobs = self.manager.refresh()
        current = self.selected.job_id if self.selected else None
        ended_before = {j.job_id for j in self.model.jobs if j.state != "running"}
        self.infos = {job.job_id: JobInfo.read(job, self.infos.get(job.job_id) if job.job_id in ended_before else None)
                      for job in jobs}
        self.model.states = {job.job_id: self._status(job) for job in jobs}
        self.model.set_jobs(jobs)
        for job in jobs:
            f = self.followers.get(job.job_id)
            if f is None and job.state == "running":
                f = self.followers[job.job_id] = Follower(job)
            if f is not None:
                if job.state == "running":
                    f.tick()
                    self._enforce_call_cap(job, f)
                elif job.state != "spawning":
                    f.finish()
                frac = f.state.fraction
                self.model.progress[job.job_id] = (f"{f.state.done:,}/{f.state.total:,}" if f.state.total
                                                   else f"{f.state.done:,}") + (f" · {frac:.0%}" if frac else "")
        if current is not None:
            self.select(current, scroll=False)
        self._batches_view()
        self._dev_view()
        running = sum(1 for j in jobs if j.state == "running")
        self.jobs_changed.emit(running, len(jobs) - running)

    def info(self, job: Job) -> JobInfo:
        return self.infos.get(job.job_id) or JobInfo()

    def _status(self, job: Job) -> tuple[str, str]:
        """The state of ``job`` (:func:`job_status`), with the end outcome of its progress file when it is followed."""
        f = self.followers.get(job.job_id)
        outcome = f.state.outcome if f is not None and f.state.ended else None
        return job_status(job, self.info(job), outcome=outcome)

    def select(self, job_id: str, *, scroll: bool = True) -> None:
        for i, job in enumerate(self.model.jobs):
            if job.job_id == job_id:
                self.view.blockSignals(True)
                self.view.selectRow(i)
                self.view.blockSignals(False)
                self.selected = job
                self._dashboard(fresh=scroll)
                return

    def _row_changed(self, current: QModelIndex, _prev: QModelIndex) -> None:
        if current.isValid():
            before = self.selected.job_id if self.selected else None
            self.selected = self.model.jobs[current.row()]
            if self.selected.job_id not in self.followers:
                self.followers[self.selected.job_id] = Follower(self.selected)
            # the list timer's model reset re-sets the current row of the same job: that is no new selection
            self._dashboard(fresh=self.selected.job_id != before)

    def _tick(self) -> None:
        job = self.selected
        f = self.followers.get(job.job_id) if job is not None else None
        if job is None or f is None:
            return
        if job.state == "running":
            f.tick()
            self._dashboard()
        elif job.state != "spawning" and not f.finished:  # GR-44: _dashboard folds the next step of an ended job
            self._dashboard()

    def _live_refresh(self, job: Job) -> None:
        """Read the live run's ``live`` block from its working corpus in the pool: at most every :data:`LIVE_S` while
        it runs, and once more after it ended. The details are redrawn when it arrives."""
        if job.command != "run" or not job.writes or job.job_id in self._live_busy:
            return
        ended = job.state != "running"
        last = self._live_at.get(job.job_id)
        if job.job_id in self._live_final or (not ended and last is not None and time.monotonic() - last < LIVE_S):
            return
        job_id, corpus = job.job_id, Path(job.writes[0])
        self._live_busy.add(job_id)
        self._live_at[job_id] = time.monotonic()

        def done(block: dict[str, Any] | None) -> None:
            self._live_busy.discard(job_id)
            self._live[job_id] = block
            if ended:
                self._live_final.add(job_id)
            if self.selected is not None and self.selected.job_id == job_id:
                self._dashboard()

        submit(self, lambda _s: live_block(corpus), done, lambda _code: self._live_busy.discard(job_id))

    def _dashboard(self, *, fresh: bool = False) -> None:
        """``fresh``: the job was just selected (not a timer refresh), so the text panes start over."""
        job = self.selected
        if job is None:
            return
        f = self.followers.get(job.job_id)
        if f is not None and job.state != "running":
            f.tick() if job.state == "spawning" else f.finish()
        info = self.infos[job.job_id] = JobInfo.read(job)
        status = self.model.states[job.job_id] = self._status(job)
        run = job.command == "run"
        label = T.clean(job.record.get("label", ""), 120) or T.clean(job.command, 60)
        self.title.set_plain(f"Live run · {label}" if run else label)
        self.state_badge.set_status(*status)
        st = f.state if f else ProgressState()
        live = live_facts(self._live.get(job.job_id)) if run else {}
        if run:
            self._live_refresh(job)
        started = local_created(job.record.get("created"))
        what = (live["model"] + (f" through {live['endpoint']}" if "endpoint" in live else "") if "model" in live
                else T.clean(job.command, 60))
        sub = [f"Started {started}" if started else "", what, live.get("traces", "")]
        if job.state != "running" and job.exit_code is not None:
            sub.append(f"ended with exit {job.exit_code}" + (f" ({T.clean(job.outcome, 30)})" if job.outcome else ""))
        self.subtitle.set_plain(" · ".join(x for x in sub if x))
        self.argv.set_plain_keep(T.multiline(shlex.join(job.argv), 4000), fresh=fresh)
        if st.total:
            self.bar.setRange(0, st.total)
            self.bar.setValue(min(st.done, st.total))
        else:
            self.bar.setRange(0, 0 if job.state == "running" else 1)
            self.bar.setValue(0 if job.state == "running" else 1)
        now = time.monotonic()
        unit = "cells" if run else "done"
        parts = [f"{st.done:,} of {st.total:,} {unit}" if st.total else f"{st.done:,} {unit}",
                 f"{st.in_flight} in progress"]
        if "calls" in live:
            parts.append(f"Model calls {live['calls']}")
        elif run and st.step_count("model_call"):  # no caps recorded: the model_call steps (a capped dev run's count)
            cap = job.record.get("call_cap")
            parts.append(f"Model calls {st.step_count('model_call'):,}"
                         + (f" of {cap:,} cap" if isinstance(cap, int) and not isinstance(cap, bool) else ""))
        if "cost" in live:
            parts.append(f"Cost (upper bound) {live['cost']}")
        if f is not None and job.state == "running":
            rate = f.rates.short() or f.rates.mean(now, st.done)
            if rate:
                parts.append(f"{rate:.2f} per second")
            parts.append(eta_text(f.rates.eta(now, st.done, st.total)))
        self.facts.set_plain(" · ".join(parts))
        warnings = []
        if job.record.get("conformance_skipped") or (job.state != "running" and job.writes and summarise(
                Path(job.writes[0])).prov_conformance == "skipped"):
            warnings.append("⚠ UNVALIDATED: the PROV conformance check was skipped (§8.3a); seal and release are "
                            "refused until a full recompute validates it into a new corpus")
        if job.stale_lock:
            warnings.append("stale lock: start a --break-stale-lock job")
        self.warning.set_status(" · ".join(warnings), "warn")
        notes = []
        if st.dropped:
            notes.append(f"{st.dropped} progress events dropped")
        if f is not None and (f.reader.skipped_bad or f.reader.skipped_long):
            notes.append(f"{f.reader.skipped_bad + f.reader.skipped_long} progress lines skipped")
        if not f or not st.events:
            notes.append("no progress events (this command does not write them today)")
        self.notes.set_plain(" · ".join(notes))
        self.notes.setVisible(bool(notes))
        fill_rows(self.counts, ([T.clean(k, 60), f"{v:,}"] for k, v in st.statuses.most_common()))
        fill_rows(self.codes, ([T.clean(k, 120), f"{v:,}"] for k, v in st.codes.most_common(200)))
        tail = T.multiline(tail_bytes(job.file("stderr.txt")).decode("utf-8", "replace"), 65536)
        # GR-28: the newest lines, the user's reading position kept (by content, GR-57); long lines broken (GR-57)
        self.stderr.set_plain_keep(T.display_lines(tail), follow_end=True, fresh=fresh)
        self._controls(job, info, status)

    def _controls(self, job: Job, info: JobInfo, status: tuple[str, str]) -> None:
        """Each control enabled only when it applies (D-1061), what each does, and the job's terminal commands."""
        running = job.state == "running"
        run = job.command == "run"
        self.drain_btn.setEnabled(running and bool(job.record.get("control_file")) and status[0] == "Running")
        self.resume_btn.setEnabled(not running and not info.abandoned)
        self.stop_btn.setEnabled(running)
        self.cancel_btn.setEnabled(running or not info.abandoned)
        self.cancel_btn.setText("Cancel Run…" if run else "Cancel Job…")
        self.kill_btn.setEnabled(running)
        self.preview_btn.setEnabled(running and run)
        self.viewer_btn.setEnabled(bool(job.writes))
        self.log_btn.setEnabled(True)
        self.copy_btn.setEnabled(True)
        for label, (_name, text) in zip(self.control_help, control_texts(run), strict=True):
            label.set_plain(text)
        commands = job_commands(job, info)
        if commands != self.command_card.commands:
            self.command_card.set_commands(commands)
        notes = ["Commands use the job's real id."]
        if running and not job.record.get("control_file"):
            notes.append("It was started without a control file, so it cannot be paused.")
        if info.abandoned:
            notes.append("It was cancelled, so it is never resumed.")
        self.command_note.set_plain(" ".join(notes))

    # ------------------------------------------------------------------------------------------ actions
    def stop(self) -> None:
        job = self.selected
        if job is None:
            return
        if ask(self, "Stop job", "Stop this job?", (
                "In-flight units are aborted and recorded as aborted. Paid calls already made are not refunded. The "
                "CLI flushes, releases its lock and exits with code 130.")):
            sent = run_off_ui(self, lambda: self.manager.request(job, "stop") or self.manager.stop(job))
            if not sent:
                safe_message_box(self, "Stop job", "The job could not be signalled (it ended, or its process is no "
                                 "longer the one that was started).").exec()
            job.record["stop_requested_at"] = time.time()

    def kill(self) -> None:
        job = self.selected
        if job is None:
            return
        if ask(self, "Force kill", "Force kill this job?", (
                "Use this only after Stop has had time to work. The job gets no chance to clean up: its corpus lock "
                "stays (stale), an import's index may not be flushed, and live staging may be orphaned."),
                icon=CRITICAL):
            run_off_ui(self, lambda: self.manager.kill(job))

    def drain(self) -> None:
        job = self.selected
        if job is not None:
            run_off_ui(self, lambda: self.manager.request(job, "drain"))

    def cancel(self) -> None:
        """D-1061: ``agentprov jobs cancel ID`` after the confirmation, off the UI thread: the graceful stop of a running
        job and the mark that makes Resume refuse it. Nothing is deleted."""
        job = self.selected
        if job is None:
            return
        info = JobInfo.read(job)
        running = job.state == "running"
        if not running and info.abandoned:
            return
        what = "run" if job.command == "run" else "job"
        stops = (f"The {what} stops as Stop does: in-flight units are aborted and recorded as aborted. Paid calls "
                 "already made are not refunded. " if running else "")
        if not ask(self, f"Cancel {what}", f"Cancel this {what}?", (
                f"{stops}It is marked cancelled, so it can never be resumed (Resume and agentprov jobs resume refuse "
                f"it). Nothing is deleted: its working corpus stays where it is.")):
            return
        argv = build_spec(FORMS["jobs_cancel"], {"job_id": job.job_id}).argv
        code, _out, err = run_off_ui(self, lambda: self.manager.call(list(argv), timeout=30))
        if running:
            job.record["stop_requested_at"] = time.time()
        if code != 0:
            safe_message_box(self, f"Cancel {what}", f"The {what} could not be cancelled completely.",
                             informative=T.line(JobManager._refusal(code, err).reason, 400), icon=WARNING).exec()
        self.refresh()

    def resume(self) -> None:
        job = self.selected
        if job is None:
            return
        if JobInfo.read(job).abandoned:  # D-1061: the button is disabled; a cancelled job is never resumed
            safe_message_box(self, "Resume", "This job was cancelled, so it is not resumed.").exec()
            return
        argv = self.manager.resume_spec_argv(job)
        if not argv:
            return
        tool_path = job.record.get("tool") if isinstance(job.record.get("tool"), str) else None
        form = next((f for f in FORMS.values() if f.tool == tool_path), None) if tool_path else FORMS.get(job.command)
        tool = self.tool_program(form.tool) if form is not None and form.tool is not None else None
        try:  # GR-3: the tier, --yes, purge's digits, release and the conformance skip come from the argv, not job.json
            spec = resume_spec(form.name if tool_path and form is not None else job.command,
                               [*(tool or ()), *argv] if tool_path else argv, str(job.record.get("tier", "R1")),
                               f"{T.clean(job.record.get('label', ''), 80)} (resumed)", tool=tool or (),
                               writes=job.writes, slot=job.record.get("slot"), extra={**self._resume_extra(job),
                                                                                       "resumes": job.job_id})
        except FormError as exc:
            safe_message_box(self, "Resume", "This job cannot be resumed.", informative=T.line(str(exc), 400)).exec()
            return
        from agentprov_gui.ui.jobdialog import confirm

        if tool_path:
            from dataclasses import replace

            extra = {k: v for k, v in {**dict(spec.extra or {}), "tool": tool_path}.items() if k != "raw"}
            spec = replace(spec, argv=spec.argv[len(tool or ()):], extra=extra)
        program = (*(tool or ()),) if tool_path else self.manager.cli.program
        confirmed = confirm(self, spec, shlex.join([*program, *spec.argv]))
        if confirmed is not None:
            self.start(confirmed, control=bool(job.record.get("control_file")))

    @staticmethod
    def _resume_extra(job: Job) -> dict[str, str | int]:
        """GR-25: a resumed dev-run job stays part of its run (its folder busy, its row in the summary, its queue), and
        a capped live dev run keeps its model-call cap (§19.2)."""
        out: dict[str, str | int] = {k: v for k in ("devrun", "part") if isinstance(v := job.record.get(k), str) and v}
        if isinstance(cpu := job.record.get("queue_cpu"), int) and not isinstance(cpu, bool):
            out["queue_cpu"] = cpu
        if isinstance(cap := job.record.get("call_cap"), int) and not isinstance(cap, bool):  # §19.2: the cap stays,
            out.update(call_cap=cap, progress_level="steps")  # with the model_call steps it counts
        return out

    def _open_log(self) -> None:
        if self.selected is not None:
            self.open_log.emit(self.selected.job_id)

    def copy_command(self) -> None:
        if self.selected is not None:
            QGuiApplication.clipboard().setText(T.line(shlex.join(self.selected.argv), 8000))

    def _open_viewer(self) -> None:
        if self.selected is not None and self.selected.writes:
            self.open_corpus.emit(self.selected.writes[0])

    def _code_clicked(self, row: int, _col: int) -> None:
        if self.selected is not None:
            self.open_log.emit(self.selected.job_id)

    # ------------------------------------------------------------------------------------------ batches
    def start_batch(self, label: str, specs: list[JobSpec], *, continue_on_failure: bool | None = None
                    ) -> Batch | None:
        """Create and start a batch (D-704: ``batch create --stdin`` then ``batch start --confirm-r2``; the user started
        it now, which confirms its R2 steps). Without an explicit ``continue_on_failure`` the CLI follows the setting
        ``jobs.continue_on_failure`` (Settings › Jobs; GR-33). ``None`` when the CLI refused."""
        def create_and_start() -> str:  # AU-GUI-3: both CLI calls in the pool
            batch_id = batch_client.create(self.manager, label, specs, continue_on_failure=continue_on_failure)
            batch_client.start(self.manager, batch_id, confirm_r2=True)
            return batch_id

        try:
            batch_id = run_off_ui(self, create_and_start)
        except SpawnRefused as exc:
            safe_message_box(self, "Batch not started", "The batch was not started.",
                             informative=T.line(exc.reason, 400), icon=WARNING).exec()
            return None
        self.refresh()
        return next((b for b in self.batches if b.batch_id == batch_id), None)

    def resume_batch(self) -> None:
        """GR-48: confirm each held step of the selected batch (the tier confirmation of a new job), then start a new
        driver with ``batch resume --confirm-r2``. A cancelled confirmation leaves the batch held."""
        row = self.batch_table.currentRow()
        if not 0 <= row < len(self._batch_rows):
            return
        batch = self._batch_rows[row]
        from agentprov_gui.ui.jobdialog import confirm

        for step in batch.steps:
            if step.state == "held" and confirm(
                    self, step.spec, shlex.join([*self.manager.cli.program, *step.spec.argv])) is None:
                return
        try:
            run_off_ui(self, lambda: batch_client.resume(self.manager, batch.batch_id, confirm_r2=True))
        except SpawnRefused as exc:
            safe_message_box(self, "Batch", "The batch was not resumed.", informative=T.line(exc.reason, 400)).exec()
        self.refresh()

    STOP_TEXT: Final = ("In-flight units are aborted and recorded as aborted. Paid calls already made are not refunded. "
                        "Each CLI flushes, releases its lock and exits with code 130.")

    def batch_running(self, batch: Batch) -> bool:
        """The batch's driver job or one of its step jobs runs (a step job records its batch's id)."""
        running = {j.job_id for j in self.model.jobs if j.state == "running"}
        return (batch.driver_job_id in running or any(s.job_id in running for s in batch.steps)
                or any(j.state == "running" and j.record.get("batch_id") == batch.batch_id for j in self.model.jobs))

    def selected_batch(self) -> Batch | None:
        row = self.batch_table.currentRow()
        return self._batch_rows[row] if 0 <= row < len(self._batch_rows) else None

    def _batch_buttons(self) -> None:
        batch = self.selected_batch()
        running = batch is not None and self.batch_running(batch)
        self.stop_batch_btn.setEnabled(running)
        commands = batch_commands(batch, running)
        if commands != self.batch_card.commands:
            self.batch_card.set_commands(commands)

    def stop_batch(self) -> None:
        """``agentprov batch stop ID --steps`` for the selected row's batch: its driver and every running step job."""
        batch = self.selected_batch()
        if batch is None or not self.batch_running(batch):
            return
        if ask(self, "Stop batch", "Stop this batch?", (
                f"{T.clean(batch.label, 80)}: its driver and every running or queued step job are stopped, and no "
                f"further step starts. {self.STOP_TEXT} Pending steps stay pending; Resume Batch… goes on from "
                "them.")):
            self._stop_batches([batch], [], "Stop batch")

    def dev_run_targets(self) -> tuple[Batch | None, list[Job]]:
        """What Stop Dev Run stops: the newest dev-run batch with a running job (its steps name their run), and the
        running live dev-run jobs (a single ``run`` job each, outside any batch; design §19.2)."""
        batch = next((b for b in reversed(self.batches)
                      if any(isinstance(s.spec.extra.get("devrun"), str) for s in b.steps) and self.batch_running(b)),
                     None)
        live = [j for j in self.model.jobs if j.state == "running" and j.record.get("devrun")
                and not j.record.get("batch_id")]
        return batch, live

    def stop_dev_run(self) -> None:
        batch, live = self.dev_run_targets()
        if batch is None and not live:
            return
        what = [f"{T.clean(batch.label, 80)}: its batch's driver and every running or queued step job are stopped, "
                "and no further part starts; the parts not started stay pending (Resume Batch… on the Batches tab "
                "goes on from them)."] if batch is not None else []
        if live:
            what.append(f"{len(live)} running live dev run job(s) are stopped.")
        if ask(self, "Stop dev run", "Stop this dev run?", " ".join([*what, self.STOP_TEXT])):
            self._stop_batches([batch] if batch is not None else [], live, "Stop dev run")

    def _stop_batches(self, batches: list[Batch], jobs: list[Job], title: str) -> None:
        """Off the UI thread: ``batch stop ID --steps`` for each batch, the graceful job stop for each job; then the
        views are refreshed and anything that could not be stopped is named."""
        def work() -> list[str]:
            problems: list[str] = []
            for batch in batches:
                try:
                    report = batch_client.stop(self.manager, batch.batch_id, steps=True)
                except SpawnRefused as exc:
                    problems.append(f"{T.clean(batch.label, 60)}: {T.line(exc.reason, 300)}")
                    continue
                unsignalled = report.get("steps_unsignalled")
                if isinstance(unsignalled, list) and unsignalled:
                    problems.append(f"{T.clean(batch.label, 60)}: {len(unsignalled)} step job(s) could not be "
                                    "signalled; stop them on the Jobs tab")
            for job in jobs:
                if not (self.manager.request(job, "stop") or self.manager.stop(job)):
                    problems.append(f"{T.clean(job.record.get('label', ''), 60)}: the job could not be signalled (it "
                                    "ended, or its process is no longer the one that was started)")
            return problems

        problems = run_off_ui(self, work)
        for job in jobs:
            job.record["stop_requested_at"] = time.time()
        self.refresh()
        if problems:
            safe_message_box(self, title, "Not everything could be stopped.",
                             informative=T.multiline("\n".join(problems), 2000), icon=WARNING).exec()

    def _batches_view(self) -> None:
        rows = []
        self._batch_rows = []
        for b in self.batches[-20:]:
            for i, s in enumerate(b.steps):
                self._batch_rows.append(b)
                rows.append([T.clean(b.label, 60), str(i + 1), T.clean(s.spec.label, 80), s.state,
                             "" if s.exit_code is None else str(s.exit_code), T.clean(s.note, 80)])
        fill_rows(self.batch_table, rows)
        self._batch_buttons()

    # ------------------------------------------------------------------------------------------ dev runs
    def dev_settings(self) -> devrun.DevSettings:
        """The ``agentprov settings`` ``devrun.*`` values (D-703, D-705); the defaults when they cannot be read."""
        code, out, _err = run_off_ui(self, lambda: self.manager.call(["settings", "list", "--prefix", "devrun.",
                                                                      "--format", "json"]))
        try:
            values = json.loads(out).get("values") if code == 0 else None
        except ValueError:
            values = None
        return devrun.DevSettings.from_settings(values) if isinstance(values, dict) else devrun.DEFAULTS

    def start_dev_run(self) -> None:
        """D-705: ``agentprov devrun plan`` for the confirmation, then ``agentprov devrun start --confirm-r2`` (the run
        folder, its manifest, its batch and driver job, and the pruning of old runs are the CLI's)."""
        if self.manager.cli.checkout is None or not self.manager.cli.available:
            safe_message_box(self, "Dev run", "A dev run needs a configured AgentPROV checkout.").exec()
            return
        code, out, err = run_off_ui(self, lambda: self.manager.call(["devrun", "plan", "--format", "json"]))
        try:
            doc = json.loads(out) if code == 0 else None
        except ValueError:
            doc = None
        if not isinstance(doc, dict):
            reason = JobManager._refusal(code, err).reason if code != 0 else "no plan"
            safe_message_box(self, "Dev run", "The dev run cannot start.", informative=T.line(reason, 400)).exec()
            return
        settings, parts, steps = doc.get("settings") or {}, doc.get("parts") or [], doc.get("steps") or []
        if settings.get("prov_conformance") is False:
            from agentprov_gui.ui.jobdialog import conformance_warning

            if not conformance_warning(self):
                return
        queued = (f"through the job queue (--class import --cpu {settings.get('queue_cpu')})" if doc.get("queue")
                  else "without the job queue (this checkout has none)")
        text = (f"{len(parts)} parts × {'/'.join(str(p.get('samples')) for p in parts[:1])} samples (mode "
                f"{settings.get('mode')}), {len(steps)} jobs {queued}, as one batch that runs as its own job.\n"
                f"Output: {self.manager.home / 'dev-runs'}/<UTC stamp>\nNever --release, never a stored corpus. "
                f"The last {settings.get('keep')} dev runs are kept.")
        if not ask(self, "Start dev run", "Start a dev run?", T.multiline(text, 2000), icon=INFORMATION,
                   default_ok=True):
            return
        code, out, err = run_off_ui(self, lambda: self.manager.call(["devrun", "start", "--confirm-r2", "--format",
                                                                     "json"]))
        if code != 0:
            safe_message_box(self, "Dev run", "The dev run was not started.",
                             informative=T.line(JobManager._refusal(code, err).reason, 400), icon=WARNING).exec()
            return
        self.refresh()
        self.tabs.setCurrentIndex(2)

    def _dev_view(self) -> None:
        batch, live = self.dev_run_targets()
        self.stop_dev_btn.setEnabled(batch is not None or bool(live))
        self.dev_badge.set_status("Running" if batch is not None or live else "", "info")
        commands = dev_commands(batch, live)
        if commands != self.dev_card.commands:
            self.dev_card.set_commands(commands)
        live_note = (f" · {len(live)} live dev run job(s) running: Stop Dev Run… stops them, as does Stop… on the Jobs "
                     "tab") if live else ""
        # the run folders (UTC stamps sort by time); a capped live dev run records ``devrun: true``, not a folder, and
        # is one job on the Jobs tab
        stamps = [v for j in self.model.jobs if isinstance(v := j.record.get("devrun"), str) and v]
        if not stamps:
            self.dev_info.set_plain("No dev run yet. Dev Run… samples every chosen corpus part (Settings › Dev Runs)."
                                    + live_note)
            return
        latest = max(stamps)
        mine = [j for j in self.model.jobs if j.record.get("devrun") == latest]
        running = sum(1 for j in mine if j.state == "running")
        self.dev_info.set_plain(f"Dev run {latest}: {len(mine)} jobs, {running} running" + live_note)
        rows = []
        for r in devrun.summarise(mine):
            c = r.counters
            note = " (this part's reader cannot sample in this mode)" if r.import_outcome == "unsupported" else ""
            rows.append([T.clean(r.part, 80), (r.import_outcome or "…") + note, str(c.get("executions_mapped", c.get("mapped", ""))),
                         str(c.get("sealed_with_issues", "")), str(c.get("degenerate", "")), str(c.get("failed", "")),
                         T.clean(", ".join(f"{k} {n}" for k, n in r.issues_top), 200), r.validate_outcome or "…",
                         (r.recompute_outcome or "…") + (f" · {r.recompute_counters.get('differences', '')} diffs"
                                                         if "differences" in r.recompute_counters else ""),
                         " / ".join(f"{k} {v:.0f}" for k, v in r.seconds.items())])
        fill_rows(self.dev_table, rows)

    # ------------------------------------------------------------------------------------------ sessions
    def _rewrap_cards(self) -> None:
        """A command card filled while its tab (or this page) was hidden wrapped its commands to the hidden width: wrap
        them again once it is shown."""
        for card in (self.command_card, self.batch_card, self.dev_card):
            QTimer.singleShot(0, lambda c=card: c.set_commands(c.commands, note=c.note))

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._rewrap_cards()

    def _tab_changed(self, index: int) -> None:
        self._rewrap_cards()
        if self.tabs.tabText(index) == "Sessions":
            self._sessions_refresh()
            self.sessions_timer.start(SESSIONS_MS)
        else:
            self.sessions_timer.stop()

    def _sessions_refresh(self) -> None:
        checkout, python = self.manager.cli.checkout, self.manager.cli.python
        if checkout is None or not python:
            self.sess_info.set_plain("No checkout with an interpreter is configured.")
            return

        def work(_s: object) -> bytes:
            done = subprocess.run(  # noqa: S603 - fixed argv, R0
                [*python, str(checkout / "tools" / "queue_status.py"), "--json"], capture_output=True,
                timeout=60, check=False, stdin=subprocess.DEVNULL, cwd=checkout, env=self.manager.child_env(),
            )  # fmt: skip
            return done.stdout

        submit(self, work, self._sessions_loaded, lambda code: self.sess_info.set_plain(
            f"queue_status.py failed ({T.line(code, 60)})"))

    def _sessions_loaded(self, data: bytes) -> None:
        from agentprov.errors import IngestError
        from agentprov.ingest.loaders import strict_json_loads

        try:
            doc = strict_json_loads(data)
        except IngestError as exc:
            self.sess_info.set_plain(f"queue_status.py output is not JSON ({exc.code})")
            return
        sessions = doc.get("sessions") if isinstance(doc, dict) else None
        rows = []
        for s in sessions if isinstance(sessions, list) else []:
            if not isinstance(s, dict):
                continue
            raw_status = s.get("status")
            status: dict[str, Any] = raw_status if isinstance(raw_status, dict) else {}
            flags = [str(f) for f in s.get("flags", [])] if isinstance(s.get("flags"), list) else []
            idle = s.get("idle_s")
            rows.append((0 if "WAITING-ON-USER" in flags else 1, -(idle or 0) if isinstance(idle, int | float) else 0, [
                T.line(s.get("name"), 60), T.line(s.get("state"), 30), T.line(json.dumps(status.get("waits_on")), 80),
                T.line(status.get("branch"), 60), T.line(status.get("dirty"), 10), T.line(s.get("suite_on_head"), 10),
                f"{idle / 60:.0f} min" if isinstance(idle, int | float) else "", T.line(", ".join(flags), 120),
            ]))
        rows.sort(key=lambda r: (r[0], r[1]))
        fill_rows(self.sessions, (r[2] for r in rows))
        self.sess_info.set_plain(f"{len(rows)} sessions · read-only · refreshed {time.strftime('%H:%M:%S')}")


def corpus_of(job: Job) -> Path | None:
    return Path(job.writes[0]) if job.writes else None
