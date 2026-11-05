"""Logs (design §6.3; wireframe 05).

The selected job's ``log.jsonl`` (structured; already escaped and redacted by the CLI) or ``stderr.txt`` (plain lines),
in a ring-buffer model (50,000 records by default) shown by a uniform-row list. Filters: level toggles, a substring
search (case-insensitive), "only this execution". Follow scrolls to the end; Pause stops scrolling while reading
continues, and a banner counts the records that left the buffer. The follower reads at most 1 MiB per 250 ms tick and
shows a "lagging" note when the file grows faster. Copy gives TSV of the selected rows, as shown (escaped). Every cell
passes ``text.clean`` (S3).

House style (D-1060): the page title with the job's state as a status badge, the job and the filters in one card (the
log source a segmented control, the levels chips), the records in a card with plain-language column headers (the
record's field names in the header tooltips), a record's time in this computer's time zone, named (the recorded UTC
time in the cell's tooltip), and the terminal command card: ``agentprov jobs follow --log ID`` and ``agentprov jobs
show ID``, built by the ``jobs_follow`` and ``jobs_show`` forms (:func:`commands_for`).
"""

from __future__ import annotations

import datetime as dt
from functools import lru_cache
from typing import Any, Final

from agentprov.jobs.follow import LogRecord, LogRing, TailReader
from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPersistentModelIndex, Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QTableView,
    QWidget,
)

from agentprov_gui import text as T
from agentprov_gui.jobs.commands import FORMS, build_spec
from agentprov_gui.jobs.manager import Job, JobManager
from agentprov_gui.ui import theme
from agentprov_gui.ui.brand import command_card, page_layout
from agentprov_gui.ui.forms import (
    ChipGroup,
    Choice,
    FormSection,
    SegmentedControl,
    StatusBadge,
    Switch,
    caption,
    combo,
    heading,
)
from agentprov_gui.ui.safe import SafeLabel, help_tooltip, is_tooltip_role, safe_tooltip, set_control_tooltip

__all__ = ["LogModel", "LogsPage", "commands_for", "job_status", "local_time"]

LEVELS: Final = ("DEBUG", "INFO", "WARNING", "ERROR")


@lru_cache(maxsize=4096)
def local_time(stamp: str) -> str:
    """A record's ISO 8601 time in this computer's time zone, named (``2026-11-05 10:23:45 NZDT``); a time without a
    zone is the CLI's UTC. Anything else is shown as recorded."""
    try:
        when = dt.datetime.fromisoformat(stamp.strip())
    except ValueError:
        return stamp
    if when.tzinfo is None:
        when = when.replace(tzinfo=dt.UTC)
    local = when.astimezone()
    return f"{local:%Y-%m-%d %H:%M:%S} {local.tzname() or 'local time'}"


def job_status(job: Job) -> tuple[str, str]:
    """The words and the badge kind of a job's state: running; ended with its outcome (and the exit code when it is
    not 0); ended unobserved (its supervisor is gone and no end was recorded)."""
    if job.state == "running":
        return "Running", "info"
    if job.state == "unobserved":
        return "Ended, unobserved", "warn"
    outcome = T.line(job.outcome or "ended", 30)
    if job.exit_code == 0:
        return f"Ended: {outcome}", "ok"
    return f"Ended: {outcome} (exit {job.exit_code})", "bad"


def commands_for(job_id: str) -> list[tuple[str, tuple[str, ...]]]:
    """The terminal commands of the page's view of ``job_id``, from the ``jobs_follow`` and ``jobs_show`` forms (the
    argv a job of those forms runs)."""
    follow = build_spec(FORMS["jobs_follow"], {"job_id": job_id, "log": True}).argv
    show = build_spec(FORMS["jobs_show"], {"job_id": job_id, "format": "text"}).argv
    return [("the log records, followed as they are written", follow), ("the job: its command, state and outcome", show)]


class LogModel(QAbstractTableModel):
    HEADERS: Final = ("Time", "Level", "Written by", "Execution", "Message")
    TIPS: Final = ("When the record was written, in this computer's time zone (the record's ts field, in UTC)",
                   "DEBUG, INFO, WARNING or ERROR (the record's level field)",
                   "The part of agentprov that wrote it (the record's logger field)",
                   "The execution it is about, when it names one (the record's ex field)",
                   "The message, escaped and redacted by the CLI (the record's msg field)")
    #: the first columns' widths (px); the message takes the rest
    WIDTHS: Final = (178, 76, 150, 150)

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[LogRecord] = []

    def set_rows(self, rows: list[LogRecord]) -> None:
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def append(self, rows: list[LogRecord]) -> None:
        if not rows:
            return
        self.beginInsertRows(QModelIndex(), len(self.rows), len(self.rows) + len(rows) - 1)
        self.rows.extend(rows)
        self.endInsertRows()

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self.HEADERS)

    def cell(self, row: int, col: int) -> str:
        r = self.rows[row]
        return T.clean((local_time(r.ts) if r.ts else "", r.level, r.logger, r.ex or "", r.msg)[col], 400)

    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return self.cell(index.row(), index.column())
        if index.column() == 0 and is_tooltip_role(role) and self.rows[index.row()].ts:
            return safe_tooltip(f"Recorded as {self.rows[index.row()].ts}")
        if index.column() == 1 and role in (Qt.ItemDataRole.ForegroundRole, Qt.ItemDataRole.BackgroundRole):
            t = theme.tokens()  # the word is in the cell; the tint only repeats it
            tint = {"WARNING": (t.warn_fg, t.warn_bg), "ERROR": (t.bad_fg, t.bad_bg)}.get(self.rows[index.row()].level)
            if tint is not None:
                return QColor(tint[0] if role == Qt.ItemDataRole.ForegroundRole else tint[1])
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if orientation != Qt.Orientation.Horizontal:
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return self.HEADERS[section]
        if is_tooltip_role(role):
            return help_tooltip(self.TIPS[section])
        return None


class LogsPage(QWidget):
    def __init__(self, manager: JobManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAccessibleName("Logs")
        self.manager = manager
        self.ring = LogRing()
        self.reader: TailReader | None = None
        self.stderr_mode = False
        self.job_id: str | None = None
        lay, head, _note = page_layout(self, "Logs", caption_text="A job's log as the CLI wrote it: escaped and "
                                                                  "redacted, newest at the end.")
        self.state = StatusBadge("", name="Job state", parent=self)
        set_control_tooltip(self.state, "The selected job's state: running, or ended with its outcome and exit code.")
        head.addWidget(self.state)
        # the job and the filters, grouped compactly in one card (D-1060)
        choose = FormSection("", parent=self)
        top = QWidget(choose.card)
        row = QHBoxLayout(top)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        row.addWidget(SafeLabel("Job", name="Job label", parent=top, selectable=False))
        self.job = combo(top, name="Job", minimum_chars=20)
        self.job.currentIndexChanged.connect(self._job_changed)
        set_control_tooltip(self.job, "The job whose log is shown: its label and the start of its id")
        row.addWidget(self.job, 1)
        self.source = SegmentedControl([("Log records", "log.jsonl"), ("Standard error", "stderr.txt")],
                                       name="Log source", parent=top)
        self.source.currentIndexChanged.connect(self._job_changed)
        set_control_tooltip(self.source, "log.jsonl: the job's structured log (escaped and redacted by the CLI). "
                                         "stderr.txt: its standard error, as plain lines.")
        self.source.set_tip(0, "The job's structured log, log.jsonl (escaped and redacted by the CLI).")
        self.source.set_tip(1, "The job's standard error, stderr.txt, as plain lines.")
        row.addWidget(self.source)
        choose.add(top)
        filters = QWidget(choose.card)
        frow = QHBoxLayout(filters)
        frow.setContentsMargins(0, 0, 0, 0)
        frow.setSpacing(10)
        frow.addWidget(SafeLabel("Show", name="Filters label", parent=filters, selectable=False))
        self.levels = ChipGroup(name="Log levels", parent=filters)
        self.levels.set_choices([Choice(level, level.lower(), tip=f"Show the {level} records") for level in LEVELS],
                                checked=[level for level in LEVELS if level != "DEBUG"])
        self.level_boxes: dict[str, QAbstractButton] = {}
        for level in LEVELS:
            box = self.levels.boxes[level]
            box.setAccessibleName(f"Show {level.lower()} records")
            self.level_boxes[level] = box
        self.levels.changed.connect(self._refilter)
        # the four chips on one line: the group is as wide as they are (a flow layout alone would wrap them)
        self.levels.setMinimumWidth(sum(b.sizeHint().width() for b in self.level_boxes.values()) + 6 * len(LEVELS))
        self.levels.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        frow.addWidget(self.levels)
        self.search = QLineEdit(filters)
        self.search.setAccessibleName("Search the log")
        self.search.setPlaceholderText("Text in the message")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._refilter)
        set_control_tooltip(self.search, "Show only the records whose message or logger contains this text (any case)")
        frow.addWidget(self.search, 2)
        self.ex = QLineEdit(filters)
        self.ex.setAccessibleName("Only this execution")
        self.ex.setPlaceholderText("Execution id (ex_…)")
        self.ex.setClearButtonEnabled(True)
        self.ex.textChanged.connect(self._refilter)
        set_control_tooltip(self.ex, "Show only the records of this execution (its exact id)")
        frow.addWidget(self.ex, 1)
        choose.add(filters)
        lay.addWidget(choose)
        # the records: a heading row with what the buffer holds, Follow and Copy, then the table in its card
        bar = QHBoxLayout()
        bar.setSpacing(10)
        bar.addWidget(heading("Records", name="Records heading", parent=self))
        self.banner = caption("", name="Log buffer facts", parent=self)
        set_control_tooltip(self.banner, "The records held in memory. The oldest leave the buffer when it is full; the "
                                         "whole log stays in the job's folder on disk.")
        bar.addWidget(self.banner, 1)
        self.follow = Switch(name="Follow the end of the log", parent=self, checked=True)
        set_control_tooltip(self.follow, "Keep the newest record in view as the log grows. Off: the view stays put while "
                                         "the log is still read.")
        follow_label = caption("Follow the end", name="Follow label", parent=self)
        follow_label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        bar.addWidget(follow_label)
        bar.addWidget(self.follow)
        copy = QPushButton("Copy", self)
        copy.setAccessibleName("Copy the selected rows")
        copy.clicked.connect(self.copy)
        set_control_tooltip(copy, "Copy the selected rows as tab-separated text, as shown (escaped) (⌘C)")
        bar.addWidget(copy)
        lay.addLayout(bar)
        records = FormSection("", parent=self)
        self.model = LogModel()
        self.view = QTableView(records.card)
        self.view.setAccessibleName("Log records")
        self.view.setModel(self.model)
        self.view.setFrameShape(QFrame.Shape.NoFrame)
        self.view.verticalHeader().setVisible(False)
        self.view.verticalHeader().setDefaultSectionSize(22)
        self.view.horizontalHeader().setStretchLastSection(True)
        self.view.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        for column, width in enumerate(LogModel.WIDTHS):
            self.view.setColumnWidth(column, width)
        self.view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.view.setWordWrap(False)
        self.view.setShowGrid(False)
        self.view.setAlternatingRowColors(False)
        records.add(self.view)
        records.card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        lay.addWidget(records, 1)
        # the terminal equivalent of what this page shows (the jobs_follow and jobs_show forms build the argv)
        self.command_card = command_card(self)
        lay.addWidget(self.command_card)
        QShortcut(QKeySequence.StandardKey.Copy, self.view).activated.connect(self.copy)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(250)
        self._show_command()
        self.reload_jobs()

    def reload_jobs(self) -> None:
        current = self.job_id
        self.job.blockSignals(True)
        self.job.clear()
        for j in self.manager.refresh():
            self.job.addItem(f"{T.clean(j.record.get('label', ''), 60)} · {j.job_id[:13]}", j.job_id)
        self.job.blockSignals(False)
        if current is not None:
            self.show_job(current)
        elif self.job.count():
            self._job_changed()

    def show_job(self, job_id: str) -> None:
        for i in range(self.job.count()):
            if self.job.itemData(i) == job_id:
                self.job.setCurrentIndex(i)
                self._job_changed()
                return

    def _show_command(self) -> None:
        if self.job_id is None:
            self.command_card.set_commands([], note="Choose a job to see its terminal commands.")
        else:
            self.command_card.set_commands(commands_for(self.job_id))

    def _show_state(self) -> None:
        job = self.manager.jobs.get(self.job_id) if self.job_id is not None else None
        words, kind = job_status(job) if job is not None else ("", "neutral")
        if (words, kind) != (self.state.text(), self.state.kind):
            self.state.set_status(words, kind)

    def _job_changed(self) -> None:
        job_id = self.job.currentData()
        if not isinstance(job_id, str) or job_id not in self.manager.jobs:
            return
        self.job_id = job_id
        job = self.manager.jobs[job_id]
        self._show_command()
        self._show_state()
        self.stderr_mode = self.source.currentIndex() == 1
        if self.reader is not None:
            self.reader.close()
        self.reader = TailReader(job.file("stderr.txt" if self.stderr_mode else "log.jsonl"))
        self.ring = LogRing()
        self.model.set_rows([])
        self._tick()

    def _matches(self, r: LogRecord) -> bool:
        if r.level and r.level in self.level_boxes and not self.level_boxes[r.level].isChecked():
            return False
        needle = self.search.text().strip().lower()
        if needle and needle not in r.msg.lower() and needle not in r.logger.lower():
            return False
        ex = self.ex.text().strip()
        return not (ex and r.ex != ex)

    def _tick(self) -> None:
        if not self.isVisible() or self.reader is None:
            return
        self._show_state()
        if self.stderr_mode:
            fresh = [LogRecord.plain(line.decode("utf-8", "replace")) for line in self.reader.read_lines()]
        else:
            fresh = [LogRecord.from_json(obj) for obj in self.reader.read()]
        if fresh:
            self.ring.extend(fresh)
            shown = [r for r in fresh if self._matches(r)]
            if len(self.model.rows) + len(shown) > self.ring.capacity:
                self._refilter()
            else:
                self.model.append(shown)
            if self.follow.isChecked():
                self.view.scrollToBottom()
        facts = [f"{len(self.ring):,} records in the buffer"]
        if self.ring.evicted:
            facts.append(f"{self.ring.evicted:,} older records left the buffer; the full log is on disk")
        if self.reader.lagging_bytes:
            facts.append(f"lagging by {self.reader.lagging_bytes / 1048576:.1f} MB")
        if self.reader.skipped_bad or self.reader.skipped_long:
            facts.append(f"{self.reader.skipped_bad + self.reader.skipped_long} lines skipped")
        self.banner.set_plain(" · ".join(facts))

    def _refilter(self) -> None:
        self.model.set_rows([r for r in self.ring if self._matches(r)])

    def copy(self) -> None:
        rows = sorted({i.row() for i in self.view.selectionModel().selectedIndexes()})
        lines = ["\t".join(self.model.cell(r, c) for c in range(len(LogModel.HEADERS))) for r in rows]
        if lines:
            QGuiApplication.clipboard().setText("\n".join(lines))
