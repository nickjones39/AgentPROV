"""Runs (design §6.2, §6.2a; wireframe 03; macos-design §3.3 "Runs"; D-392, D-544).

* **Jobs:** the job list (running, ended) and the dashboard of the selected job: the command as copyable argv, the
  progress bar, counts by status, failures by code, throughput and the ETA range, dropped events, the stderr tail
  (escaped). Actions: Stop (one SIGTERM), Force kill (after Stop, confirmed), Pause (drain; only when the CLI accepts
  ``--control-file``), Resume (re-runs the same command as a new job), Open in Viewer, Open log, Copy command.
* **Batches** (D-704): each batch runs as its own driver job (``agentprov batch run``), so it keeps going when the GUI
  closes; the GUI creates and starts it (``batch create --stdin``, ``batch start --confirm-r2``) and shows its file. A
  driver started again without the confirmation holds at an R2 step until Resume Batch confirms it (GR-48).
* **Dev runs** (D-544): plan, start, and a summary row per part.
* **Sessions** (§6.2a): ``tools/queue_status.py --json`` of the configured checkout every 30 s while the tab is
  visible (an R0 subprocess). Read-only; every string escaped.

Closing the GUI never stops a job. Every start, stop, kill and drain is an ``agentprov jobs`` call (D-704). Timers:
250 ms for the selected job's files, 1 s for the list and batches.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import time
from functools import partial
from pathlib import Path
from typing import Any, Final

from agentprov.devrun import plan as devrun
from agentprov.jobs.follow import ProgressState, Rates, TailReader, eta_text, last_heartbeat_offset
from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPersistentModelIndex, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QMenu,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableView,
    QTableWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from agentprov_gui import text as T
from agentprov_gui.jobs import batch as batch_client
from agentprov_gui.jobs.batch import Batch
from agentprov_gui.jobs.commands import CONFORMANCE_OPTION, FORMS, FormError, JobSpec, resume_spec
from agentprov_gui.jobs.manager import Job, JobManager, SpawnRefused, cli_options, tail_bytes
from agentprov_gui.readmodel.corpus import summarise
from agentprov_gui.ui.detail import fill_rows
from agentprov_gui.ui.jobdialog import JobDialog
from agentprov_gui.ui.safe import (
    CRITICAL,
    INFORMATION,
    WARNING,
    ReadOnlyText,
    SafeLabel,
    ask,
    is_tooltip_role,
    safe_message_box,
    safe_tooltip,
)
from agentprov_gui.ui.worker import submit

__all__ = ["JobsModel", "RunsPage"]

TICK_MS: Final = 250
LIST_MS: Final = 1000
SESSIONS_MS: Final = 30_000


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


def job_state_text(job: Job) -> str:
    if job.state == "running":
        return "◐ running"
    if job.state == "unobserved":
        return "? ended (unobserved)" + (" · stale lock" if job.stale_lock else "")
    mark = "✓" if job.exit_code == 0 else "×"
    return f"{mark} {job.outcome or 'ended'} ({job.exit_code})"


class JobsModel(QAbstractTableModel):
    HEADERS: Final = ("job", "command", "state", "tier", "progress", "created")

    def __init__(self) -> None:
        super().__init__()
        self.jobs: list[Job] = []
        self.progress: dict[str, str] = {}

    def set_jobs(self, jobs: list[Job]) -> None:
        self.beginResetModel()
        self.jobs = jobs
        self.endResetModel()

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self.jobs)

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self.HEADERS)

    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        job = self.jobs[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            values = (T.clean(job.record.get("label", ""), 80), job.command, job_state_text(job),
                      str(job.record.get("tier", "")), self.progress.get(job.job_id, ""),
                      T.clean(job.record.get("created", ""), 40))
            return values[index.column()]
        if is_tooltip_role(role):
            return safe_tooltip(job.job_id)
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return None


def _table(headers: list[str], name: str, parent: QWidget) -> QTableWidget:
    t = QTableWidget(0, len(headers), parent)
    t.setAccessibleName(name)
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().setVisible(False)
    t.horizontalHeader().setStretchLastSection(True)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    return t


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
    def _button(self, text: str, name: str, slot: Any) -> QPushButton:
        b = QPushButton(text, self)
        b.setAccessibleName(name)
        b.clicked.connect(slot)
        return b

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        bar = QHBoxLayout()
        self.new_btn = QPushButton("New Job ▾", self)
        self.new_btn.setAccessibleName("New job")
        menu = QMenu(self.new_btn)
        for key, form in FORMS.items():
            if form.menu:
                menu.addAction(form.title, partial(self.new_job, key))
        self.new_btn.setMenu(menu)
        bar.addWidget(self.new_btn)
        bar.addWidget(self._button("Dev Run…", "Start a dev run", self.start_dev_run))
        bar.addWidget(self._button("Live Dev Run…", "Start a live dev run", self.start_live_dev_run))
        self.live_btn = self._button("▶ Run Live…", "Run live", self.run_live)
        bar.insertWidget(0, self.live_btn)
        bar.addStretch(1)
        bar.addWidget(SafeLabel("Each batch runs as its own job: it keeps going when this window closes.", name="Batch note", parent=self))
        lay.addLayout(bar)
        self.tabs = QTabWidget(self)
        self.tabs.setAccessibleName("Runs views")
        lay.addWidget(self.tabs, 1)
        # jobs tab
        jobs_tab = QWidget(self.tabs)
        jl = QVBoxLayout(jobs_tab)
        split = QSplitter(Qt.Orientation.Vertical, jobs_tab)
        self.model = JobsModel()
        self.view = QTableView(split)
        self.view.setAccessibleName("Jobs")
        self.view.setModel(self.model)
        self.view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.view.verticalHeader().setVisible(False)
        self.view.horizontalHeader().setStretchLastSection(True)
        self.view.selectionModel().currentRowChanged.connect(self._row_changed)
        split.addWidget(self.view)
        dash = QWidget(split)
        dl = QVBoxLayout(dash)
        self.title = SafeLabel("Select a job", name="Job title", parent=dash)
        dl.addWidget(self.title)
        self.argv = ReadOnlyText(name="Job command", parent=dash, wrap=True)
        self.argv.setMaximumHeight(70)
        dl.addWidget(self.argv)
        self.bar = QProgressBar(dash)
        self.bar.setAccessibleName("Job progress")
        dl.addWidget(self.bar)
        self.facts = SafeLabel("", name="Job facts", parent=dash)
        dl.addWidget(self.facts)
        tables = QHBoxLayout()
        self.counts = _table(["status", "count"], "Counts by status", dash)
        self.codes = _table(["code", "count"], "Failures and issues by code", dash)
        self.codes.cellDoubleClicked.connect(self._code_clicked)
        tables.addWidget(self.counts)
        tables.addWidget(self.codes)
        dl.addLayout(tables)
        self.stderr = ReadOnlyText(name="Job stderr (last 64 KiB, escaped)", parent=dash)
        self.stderr.setMaximumHeight(120)
        dl.addWidget(self.stderr)
        actions = QHBoxLayout()
        self.stop_btn = self._button("Stop…", "Stop the job", self.stop)
        self.kill_btn = self._button("Force Kill…", "Force kill the job", self.kill)
        self.drain_btn = self._button("Pause (Drain)", "Pause the job", self.drain)
        self.resume_btn = self._button("Resume", "Resume the job as a new job", self.resume)
        self.viewer_btn = self._button("Open in Viewer", "Open the written corpus in the viewer", self._open_viewer)
        self.log_btn = self._button("Open Log", "Open the job log", self._open_log)
        self.copy_btn = self._button("Copy Command", "Copy the job command", self.copy_command)
        self.preview_btn = self._button("Live Preview (experimental)…", "Open the live preview (off by default)",
                                        self.open_preview)
        self.preview_btn.setEnabled(False)
        for b in (self.stop_btn, self.kill_btn, self.drain_btn, self.resume_btn, self.viewer_btn, self.log_btn,
                  self.copy_btn, self.preview_btn):
            actions.addWidget(b)
        dl.addLayout(actions)
        split.addWidget(dash)
        jl.addWidget(split)
        self.tabs.addTab(jobs_tab, "Jobs")
        # batches tab
        batch_tab = QWidget(self.tabs)
        bl = QVBoxLayout(batch_tab)
        self.batch_table = _table(["batch", "step", "command", "state", "exit", "note"], "Batch steps", batch_tab)
        bl.addWidget(self.batch_table)
        batch_actions = QHBoxLayout()
        batch_actions.addWidget(self._button("Resume Batch…", "Confirm the held steps of the selected batch",
                                             self.resume_batch))
        batch_actions.addStretch(1)
        bl.addLayout(batch_actions)
        self.tabs.addTab(batch_tab, "Batches")
        # dev runs tab
        dev_tab = QWidget(self.tabs)
        dvl = QVBoxLayout(dev_tab)
        self.dev_info = SafeLabel("", name="Dev run facts", parent=dev_tab)
        dvl.addWidget(self.dev_info)
        self.dev_table = _table(["part", "import", "mapped", "with issues", "degenerate", "failed", "top issues",
                                 "validate", "recompute", "seconds"], "Dev run summary", dev_tab)
        dvl.addWidget(self.dev_table)
        self.tabs.addTab(dev_tab, "Dev Runs")
        # sessions tab
        sess_tab = QWidget(self.tabs)
        sl = QVBoxLayout(sess_tab)
        self.sess_info = SafeLabel("Read-only: tools/queue_status.py --json every 30 s while this tab is visible.",
                                   name="Sessions facts", parent=sess_tab)
        sl.addWidget(self.sess_info)
        self.sessions = _table(["name", "state", "waits on", "branch", "dirty", "suite on head", "idle", "flags"],
                               "Development sessions", sess_tab)
        sl.addWidget(self.sessions)
        self.tabs.addTab(sess_tab, "Sessions")
        self.tabs.currentChanged.connect(self._tab_changed)

    # ------------------------------------------------------------------------------------------ jobs
    def options_for(self, words: tuple[str, ...]) -> frozenset[str]:
        if words not in self._options:
            self._options[words] = cli_options(self.manager.cli, words)
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
        dlg = RunLiveDialog(self.manager, home=self.manager.home, checkout=self.manager.cli.checkout,
                            opened=self.opened_corpora(),
                            conformance_option=CONFORMANCE_OPTION if CONFORMANCE_OPTION in opts else None,
                            preset=preset, dev_run=dev_run, call_cap=call_cap, cost_cap=cost_cap, cli_options=opts,
                            parent=self)
        if not dlg.exec() or dlg.start is None:
            return None
        start = dlg.start
        try:
            job = self.manager.spawn(start.spec, control_file="--control-file" in opts,
                                     extra_record={"backend": start.backend})
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
        if follower.state.steps.get("model_call", 0) >= cap:
            self._capped.add(job.job_id)
            if not self.manager.request(job, "drain"):
                self.manager.stop(job)

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

            values = settings_client.read(self.manager.call, prefix)
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
                and os.name == "posix"):  # the job queue locks with fcntl: none on Windows (G5 P-3)
            from dataclasses import replace

            from agentprov_gui.ui.settings_panes import int_setting

            spec = replace(spec, extra={**extra, "queue_cpu": int_setting(cfg, "compute.queue_cpu", 2, 1, 256)})
        try:
            job = self.manager.spawn(spec, control_file=control)
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

    def _dashboard(self, *, fresh: bool = False) -> None:
        """``fresh``: the job was just selected (not a timer refresh), so the text panes start over."""
        job = self.selected
        if job is None:
            return
        f = self.followers.get(job.job_id)
        if f is not None and job.state != "running":
            f.tick() if job.state == "spawning" else f.finish()
        self.title.set_plain(f"{T.clean(job.record.get('label', ''), 120)} · {job_state_text(job)}")
        self.argv.set_plain_keep(T.multiline(shlex.join(job.argv), 4000), fresh=fresh)
        st = f.state if f else ProgressState()
        if st.total:
            self.bar.setRange(0, st.total)
            self.bar.setValue(min(st.done, st.total))
        else:
            self.bar.setRange(0, 0 if job.state == "running" else 1)
            self.bar.setValue(0 if job.state == "running" else 1)
        now = time.monotonic()
        parts = [f"done {st.done:,}" + (f" of {st.total:,}" if st.total else ""), f"in flight {st.in_flight}"]
        if f is not None and job.state == "running":
            rate = f.rates.short() or f.rates.mean(now, st.done)
            if rate:
                parts.append(f"{rate:.2f} units/s")
            parts.append(eta_text(f.rates.eta(now, st.done, st.total)))
        if st.dropped:
            parts.append(f"{st.dropped} progress events dropped")
        if f is not None and (f.reader.skipped_bad or f.reader.skipped_long):
            parts.append(f"{f.reader.skipped_bad + f.reader.skipped_long} progress lines skipped")
        if not f or not st.events:
            parts.append("no progress events (this command does not write them today)")
        if job.record.get("conformance_skipped") or (job.state != "running" and job.writes and summarise(
                Path(job.writes[0])).prov_conformance == "skipped"):
            parts.insert(0, "⚠ UNVALIDATED: the PROV conformance check was skipped (§8.3a); seal and release are "
                            "refused until a full recompute validates it into a new corpus")
        if job.stale_lock:
            parts.append("stale lock: start a --break-stale-lock job")
        self.facts.set_plain(" · ".join(parts))
        fill_rows(self.counts, ([T.clean(k, 60), f"{v:,}"] for k, v in st.statuses.most_common()))
        fill_rows(self.codes, ([T.clean(k, 120), f"{v:,}"] for k, v in st.codes.most_common(200)))
        tail = T.multiline(tail_bytes(job.file("stderr.txt")).decode("utf-8", "replace"), 65536)
        # GR-28: the newest lines, the user's reading position kept (by content, GR-57); long lines broken (GR-57)
        self.stderr.set_plain_keep(T.display_lines(tail), follow_end=True, fresh=fresh)
        running = job.state == "running"
        self.stop_btn.setEnabled(running)
        self.kill_btn.setEnabled(running)
        self.drain_btn.setEnabled(running and bool(job.record.get("control_file")))
        self.preview_btn.setEnabled(running and job.command == "run")
        self.resume_btn.setEnabled(not running)
        self.viewer_btn.setEnabled(bool(job.writes))

    # ------------------------------------------------------------------------------------------ actions
    def stop(self) -> None:
        job = self.selected
        if job is None:
            return
        if ask(self, "Stop job", "Stop this job?", (
                "In-flight units are aborted and recorded as aborted. Paid calls already made are not refunded. The "
                "CLI flushes, releases its lock and exits with code 130.")):
            sent = self.manager.request(job, "stop") or self.manager.stop(job)
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
            self.manager.kill(job)

    def drain(self) -> None:
        if self.selected is not None:
            self.manager.request(self.selected, "drain")

    def resume(self) -> None:
        job = self.selected
        if job is None:
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
        """GR-25: a resumed dev-run job stays part of its run (its folder busy, its row in the summary, its queue)."""
        out: dict[str, str | int] = {k: v for k in ("devrun", "part") if isinstance(v := job.record.get(k), str) and v}
        if isinstance(cpu := job.record.get("queue_cpu"), int) and not isinstance(cpu, bool):
            out["queue_cpu"] = cpu
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
        try:
            batch_id = batch_client.create(self.manager, label, specs, continue_on_failure=continue_on_failure)
            batch_client.start(self.manager, batch_id, confirm_r2=True)
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
            batch_client.resume(self.manager, batch.batch_id, confirm_r2=True)
        except SpawnRefused as exc:
            safe_message_box(self, "Batch", "The batch was not resumed.", informative=T.line(exc.reason, 400)).exec()
        self.refresh()

    def _batches_view(self) -> None:
        rows = []
        self._batch_rows = []
        for b in self.batches[-20:]:
            for i, s in enumerate(b.steps):
                self._batch_rows.append(b)
                rows.append([T.clean(b.label, 60), str(i + 1), T.clean(s.spec.label, 80), s.state,
                             "" if s.exit_code is None else str(s.exit_code), T.clean(s.note, 80)])
        fill_rows(self.batch_table, rows)

    # ------------------------------------------------------------------------------------------ dev runs
    def dev_settings(self) -> devrun.DevSettings:
        """The ``agentprov settings`` ``devrun.*`` values (D-703, D-705); the defaults when they cannot be read."""
        code, out, _err = self.manager.call(["settings", "list", "--prefix", "devrun.", "--format", "json"])
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
        code, out, err = self.manager.call(["devrun", "plan", "--format", "json"])
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
        code, out, err = self.manager.call(["devrun", "start", "--confirm-r2", "--format", "json"])
        if code != 0:
            safe_message_box(self, "Dev run", "The dev run was not started.",
                             informative=T.line(JobManager._refusal(code, err).reason, 400), icon=WARNING).exec()
            return
        self.refresh()
        self.tabs.setCurrentIndex(2)

    def _dev_view(self) -> None:
        jobs = [j for j in self.model.jobs if j.record.get("devrun")]
        if not jobs:
            self.dev_info.set_plain("No dev run yet. Dev Run… samples every chosen corpus part (Settings › Dev Runs).")
            return
        latest = max(str(j.record.get("devrun")) for j in jobs)
        mine = [j for j in jobs if j.record.get("devrun") == latest]
        running = sum(1 for j in mine if j.state == "running")
        self.dev_info.set_plain(f"Dev run {latest}: {len(mine)} jobs, {running} running")
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
    def _tab_changed(self, index: int) -> None:
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
