"""Logs (design §6.3; wireframe 05).

The selected job's ``log.jsonl`` (structured; already escaped and redacted by the CLI) or ``stderr.txt`` (plain lines),
in a ring-buffer model (50,000 records by default) shown by a uniform-row list. Filters: level toggles, a substring
search (case-insensitive), "only this execution". Follow scrolls to the end; Pause stops scrolling while reading
continues, and a banner counts the records that left the buffer. The follower reads at most 1 MiB per 250 ms tick and
shows a "lagging" note when the file grows faster. Copy gives TSV of the selected rows, as shown (escaped). Every cell
passes ``text.clean`` (S3).
"""

from __future__ import annotations

from typing import Any, Final

from agentprov.jobs.follow import LogRecord, LogRing, TailReader
from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPersistentModelIndex, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from agentprov_gui import text as T
from agentprov_gui.jobs.manager import JobManager
from agentprov_gui.ui.safe import SafeLabel

__all__ = ["LogModel", "LogsPage"]

LEVELS: Final = ("DEBUG", "INFO", "WARNING", "ERROR")


class LogModel(QAbstractTableModel):
    HEADERS: Final = ("ts", "level", "logger", "ex", "message")

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
        return T.clean((r.ts, r.level, r.logger, r.ex or "", r.msg)[col], 400)

    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if index.isValid() and role == Qt.ItemDataRole.DisplayRole:
            return self.cell(index.row(), index.column())
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
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
        lay = QVBoxLayout(self)
        bar = QHBoxLayout()
        self.job = QComboBox(self)
        self.job.setAccessibleName("Job")
        self.job.currentIndexChanged.connect(self._job_changed)
        bar.addWidget(self.job, 2)
        self.source = QComboBox(self)
        self.source.setAccessibleName("Log source")
        self.source.addItems(["log.jsonl", "stderr.txt"])
        self.source.currentIndexChanged.connect(self._job_changed)
        bar.addWidget(self.source)
        self.level_boxes: dict[str, QCheckBox] = {}
        for level in LEVELS:
            cb = QCheckBox(level.lower(), self)
            cb.setAccessibleName(f"Show {level.lower()} records")
            cb.setChecked(level != "DEBUG")
            cb.toggled.connect(self._refilter)
            self.level_boxes[level] = cb
            bar.addWidget(cb)
        self.search = QLineEdit(self)
        self.search.setAccessibleName("Search the log")
        self.search.setPlaceholderText("search")
        self.search.textChanged.connect(self._refilter)
        bar.addWidget(self.search, 2)
        self.ex = QLineEdit(self)
        self.ex.setAccessibleName("Only this execution")
        self.ex.setPlaceholderText("only ex_…")
        self.ex.textChanged.connect(self._refilter)
        bar.addWidget(self.ex, 1)
        self.follow = QCheckBox("follow", self)
        self.follow.setAccessibleName("Follow the end of the log")
        self.follow.setChecked(True)
        bar.addWidget(self.follow)
        copy = QPushButton("Copy", self)
        copy.setAccessibleName("Copy the selected rows")
        copy.clicked.connect(self.copy)
        bar.addWidget(copy)
        lay.addLayout(bar)
        self.banner = SafeLabel("", name="Log buffer facts", parent=self)
        lay.addWidget(self.banner)
        self.model = LogModel()
        self.view = QTableView(self)
        self.view.setAccessibleName("Log records")
        self.view.setModel(self.model)
        self.view.verticalHeader().setVisible(False)
        self.view.verticalHeader().setDefaultSectionSize(20)
        self.view.horizontalHeader().setStretchLastSection(True)
        self.view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.view.setWordWrap(False)
        lay.addWidget(self.view, 1)
        QShortcut(QKeySequence.StandardKey.Copy, self.view).activated.connect(self.copy)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(250)
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

    def _job_changed(self) -> None:
        job_id = self.job.currentData()
        if not isinstance(job_id, str) or job_id not in self.manager.jobs:
            return
        self.job_id = job_id
        job = self.manager.jobs[job_id]
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
