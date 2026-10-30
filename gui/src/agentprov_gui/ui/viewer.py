"""The Viewer (design §6.1; wireframe 01; macos-design §3.3 "Viewer", "Execution detail"; D-840..D-845).

A document tab bar: the first tab, **Corpora**, is the corpus browser (corpora list → executions table, virtualised,
model-side sort and filter → a preview of the selected execution); every other tab is one execution opened with a
double-click, Return or Open in New Tab (:class:`~agentprov_gui.ui.execution.ExecutionPane`: Graph + PROV-JSON side
by side, AER, SEM, Register, Validation, Raw, Index Row). At most :data:`MAX_TABS` execution tabs; only the
:data:`LIVE_SCENES` most recently viewed keep a live graph scene.

Opening a corpus is **read-only**: no write, no lock, nothing created inside it. Index and detail loads run in worker
threads and come back as immutable objects; a newer request supersedes an older one (generation counter).
"""

from __future__ import annotations

import shlex
import threading
import time
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Any, Final

from agentprov.corpus.layout import PARTIAL_SUFFIX
from agentprov.corpus.reader import CorpusReader
from PySide6.QtCore import (
    QAbstractTableModel,
    QEvent,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QPoint,
    Qt,
    QThreadPool,
    Signal,
)
from PySide6.QtGui import QGuiApplication, QKeySequence, QMouseEvent, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QMenu,
    QPushButton,
    QSplitter,
    QTabBar,
    QTableView,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from agentprov_gui import text as T
from agentprov_gui.readmodel.corpus import CorpusSummary, discover
from agentprov_gui.readmodel.detail import DetailCache
from agentprov_gui.readmodel.executions import (
    COLUMNS,
    OUTCOME_LABELS,
    ExecutionTable,
    TableFilter,
    cli_selection,
    load_table,
)
from agentprov_gui.ui import theme
from agentprov_gui.ui.execution import CorpusSource, ExecutionPane
from agentprov_gui.ui.safe import (
    SafeLabel,
    is_tooltip_role,
    safe_tooltip,
    set_tab_tooltip,
    set_tooltip,
    tab_text,
)
from agentprov_gui.ui.worker import JobSignals, submit

__all__ = ["LIVE_SCENES", "MAX_TABS", "CorporaModel", "ExecutionsModel", "ViewerPage", "elide_middle"]

#: D-843: open execution tabs at most (fixed; a presentational limit with no Settings key)
MAX_TABS: Final = 12
#: D-843: the current tab and the most recently viewed others keep a live graph scene; older ones keep only the layout
LIVE_SCENES: Final = 4
#: D-840: execution ids in tab titles are elided in the middle to about this many characters
TAB_TITLE_CHARS: Final = 20

ANY: Final = "any"
ATTACK_KEY: Final = "outcome.attack_succeeded"
#: D-706: the rule behind the attack-succeeded column, its glyph and its tint (header and cell tooltips, the legend)
ATTACK_RULE: Final = ("attack succeeded: the SEM claim attack_succeeded holds, i.e. the benchmark's checker judged the "
                      "injection task achieved on an attacked cell. Blank: not judged, or a benign cell (never guessed "
                      "from a raw judgement).")
OUTCOME_RULE: Final = {
    ATTACK_KEY: ATTACK_RULE,
    "outcome.user_task_solved": "utility: the SEM claim user_task_solved holds (yes), does not (no), or was not judged "
                                "(blank).",
}
#: the pickers of the second filter row (the task and outcome columns of a derived corpus)
TASK_PICKERS: Final = ("cell.suite", "cell.attack_id", "cell.attack_target_id", "cell.defense_id", "model.requested",
                       "outcome.user_task_solved", ATTACK_KEY)
_TITLES: Final = {c.key: c.title for c in COLUMNS}


def elide_middle(text: str, limit: int = TAB_TITLE_CHARS) -> str:
    """``text`` shortened in the middle to ``limit`` characters (D-840: the start and the end of an id both matter)."""
    if len(text) <= limit:
        return text
    head = (limit - 1) // 2
    return text[:head] + "…" + text[len(text) - (limit - 1 - head):]


# ----------------------------------------------------------------------------------------------- models
class CorporaModel(QAbstractTableModel):
    HEADERS: Final = ("corpus", "state", "corpus_id", "version", "executions", "content_digest", "root")

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[CorpusSummary] = []

    def set_rows(self, rows: list[CorpusSummary]) -> None:
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self.HEADERS)

    def _state(self, c: CorpusSummary) -> str:
        token = "writing" if c.writing else c.state
        return theme.status_text(token)

    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        c = self.rows[index.row()]
        col = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            values = (T.line(c.name, 80), self._state(c), T.line(c.corpus_id or "—", 60), T.line(c.corpus_version or "—"),
                      f"{c.executions:,}" if c.executions is not None else "—",
                      T.line(c.content_digest[:19] + "…") if c.content_digest else "—", T.line(str(c.path.parent), 80))
            return values[col]
        if role == Qt.ItemDataRole.ForegroundRole and col == 1:
            return theme.status_colour("writing" if c.writing else c.state)
        if role == Qt.ItemDataRole.AccessibleTextRole and col == 1:
            return f"state: {self._state(c)}"
        if is_tooltip_role(role):
            return safe_tooltip(str(c.path) + (f" ({c.error})" if c.error else ""))
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return None


class ExecutionsModel(QAbstractTableModel):
    """A view over an :class:`ExecutionTable` through a row permutation (sort and filter in Python, research §M5)."""

    def __init__(self) -> None:
        super().__init__()
        self.table: ExecutionTable | None = None
        self.order: list[int] = []
        self.columns = list(COLUMNS)
        self.sort_key = "ex"
        self.descending = False
        self.filter = TableFilter()

    def set_table(self, table: ExecutionTable | None) -> None:
        self.beginResetModel()
        self.table = table
        if table is not None:
            keep = set(table.non_empty_columns()) | {"ex", "status"}
            self.columns = [c for c in COLUMNS if c.key in keep]
        self.filter = TableFilter()
        self.sort_key, self.descending = "ex", False
        self.order = list(range(len(table))) if table is not None else []
        self.endResetModel()

    def apply(self, flt: TableFilter | None = None, sort_key: str | None = None, descending: bool | None = None) -> None:
        if self.table is None:
            return
        self.filter = flt if flt is not None else self.filter
        self.sort_key = sort_key if sort_key is not None else self.sort_key
        self.descending = descending if descending is not None else self.descending
        self.beginResetModel()
        self.order = self.table.select(self.filter, self.sort_key, self.descending)
        self.endResetModel()

    def sort(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder) -> None:
        if 0 <= column < len(self.columns):
            self.apply(sort_key=self.columns[column].key, descending=order == Qt.SortOrder.DescendingOrder)

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self.order)

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self.columns)

    def table_row(self, view_row: int) -> int:
        return self.order[view_row]

    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or self.table is None:
            return None
        col = self.columns[index.column()]
        row = self.order[index.row()]
        value = self.table.value(row, col.key)
        if role == Qt.ItemDataRole.BackgroundRole:
            return theme.attack_tint() if self.attack_succeeded(row) else None
        if role == Qt.ItemDataRole.DisplayRole:
            if value is None:
                return "—"
            if col.key == ATTACK_KEY and value == "yes":
                return f"{theme.ATTACK_GLYPH} yes"
            if col.key == "status":
                return theme.status_text(value) if value in theme.STATUS else T.line(value)
            if col.numeric:
                return f"{value:,}" if isinstance(value, int) else T.line(value)
            return T.line(value)
        if role == Qt.ItemDataRole.ForegroundRole and col.key == "status" and isinstance(value, str):
            return theme.status_colour(value)
        if role == Qt.ItemDataRole.TextAlignmentRole and col.numeric:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.AccessibleTextRole and col.key == ATTACK_KEY and value == "yes":
            return "attack succeeded"
        if is_tooltip_role(role) and col.key == "n_issues":
            issues = self.table.issues[row]
            return safe_tooltip(", ".join(issues)) if issues else None
        if is_tooltip_role(role) and col.key in OUTCOME_RULE:
            return safe_tooltip(OUTCOME_RULE[col.key])
        return None

    def attack_succeeded(self, row: int) -> bool:
        """D-706: the row's ``attack_succeeded`` claim holds (never on an unknown or benign row)."""
        sets = self.table.sets.get(ATTACK_KEY) if self.table is not None else None
        return sets is not None and "true" in sets[row]

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if orientation != Qt.Orientation.Horizontal:
            return None
        key = self.columns[section].key
        if role == Qt.ItemDataRole.DisplayRole:
            return f"{theme.ATTACK_GLYPH} {self.columns[section].title}" if key == ATTACK_KEY else \
                self.columns[section].title
        if is_tooltip_role(role) and key in OUTCOME_RULE:
            return safe_tooltip(OUTCOME_RULE[key])
        return None


# ----------------------------------------------------------------------------------------------- the page
class ViewerPage(QWidget):
    revalidate_requested = Signal(str)  # a marked corpus (§8.3a): the main window opens the full-recompute form
    render_requested = Signal(str, str)  # (corpus, ex): the main window opens the render form (D-706, D-654)
    status_message = Signal(str)
    corpus_opened = Signal(str, float)  # name, seconds (for the window title and measurements)

    def __init__(self, roots: list[Path], cache_dir: Path | None, content_limit: int = T.CONTENT_CHARS_DEFAULT,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAccessibleName("Viewer")
        self.roots = roots
        self.content_limit = content_limit
        self.pool = QThreadPool.globalInstance()
        self.reader: CorpusReader | None = None
        self.summary: CorpusSummary | None = None
        self.table: ExecutionTable | None = None
        self.cache = DetailCache()
        self.cache_dir = cache_dir
        self.exact_palette = False  # Settings › Appearance "W3C exact" (set through set_exact_palette)
        self._gen = 0
        #: D-843: the open execution tabs by (corpus root, ex), and the panes in viewing order (most recent last)
        self.exec_tabs: dict[tuple[str, str], ExecutionPane] = {}
        self._viewed: list[ExecutionPane] = []
        self._pending_reveal: str | None = None  # Show in Corpora of another corpus: select this ex once it is open
        self._fixing_order = False
        self._cancel = threading.Event()
        self._opened_at = 0.0
        self.last_open_seconds: float | None = None
        #: (corpus path) -> "level, date, job" of the last successful GUI verify job, or None (set by the main window)
        self.verified_lookup: Callable[[Path], str | None] = lambda _p: None
        self._build(cache_dir)

    def _build(self, cache_dir: Path | None) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        # D-840: the document tab bar; tab 0 is the corpus browser
        self.doc_tabs = QTabWidget(self)
        self.doc_tabs.setAccessibleName("Viewer tabs")
        self.doc_tabs.setDocumentMode(True)
        self.doc_tabs.setTabsClosable(True)
        self.doc_tabs.setMovable(True)
        self.doc_tabs.setUsesScrollButtons(True)
        self.doc_tabs.setElideMode(Qt.TextElideMode.ElideNone)  # titles are elided in the middle by elide_middle
        corner = QWidget(self.doc_tabs)
        cl = QHBoxLayout(corner)
        cl.setContentsMargins(0, 0, 0, 0)
        self.tab_count = SafeLabel("", name="Open execution tabs", parent=corner, selectable=False)
        cl.addWidget(self.tab_count)
        self.reload_btn = QPushButton("Reload", corner)
        self.reload_btn.setAccessibleName("Reload corpora list")
        set_tooltip(self.reload_btn, "Reload the corpora list (⌘R)")
        self.reload_btn.clicked.connect(self.refresh)
        cl.addWidget(self.reload_btn)
        self.doc_tabs.setCornerWidget(corner, Qt.Corner.TopRightCorner)
        self.browser = QWidget(self.doc_tabs)
        self.browser.setAccessibleName("Corpora browser")
        brl = QVBoxLayout(self.browser)
        brl.setContentsMargins(0, 4, 0, 0)
        split = QSplitter(Qt.Orientation.Vertical, self.browser)
        # corpora
        top = QWidget(split)
        tl = QVBoxLayout(top)
        tl.setContentsMargins(0, 0, 0, 0)
        self.corpora = CorporaModel()
        self.corpora_view = QTableView(top)
        self.corpora_view.setAccessibleName("Corpora list")
        self.corpora_view.setModel(self.corpora)
        self.corpora_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.corpora_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.corpora_view.verticalHeader().setVisible(False)
        self.corpora_view.horizontalHeader().setStretchLastSection(True)
        self.corpora_view.activated.connect(self._corpus_activated)
        self.corpora_view.doubleClicked.connect(self._corpus_activated)
        tl.addWidget(self.corpora_view)
        split.addWidget(top)
        # executions
        mid = QWidget(split)
        ml = QVBoxLayout(mid)
        ml.setContentsMargins(0, 0, 0, 0)
        self.banner = QFrame(mid)
        self.banner.setFrameShape(QFrame.Shape.StyledPanel)
        bl = QHBoxLayout(self.banner)
        self.banner_text = SafeLabel("", name="Corpus verification banner", parent=self.banner)
        bl.addWidget(self.banner_text, 1)
        self.revalidate_btn = QPushButton("Revalidate (full recompute)…", self.banner)
        self.revalidate_btn.setAccessibleName("Revalidate this corpus with a full recompute into a new corpus")
        self.revalidate_btn.clicked.connect(self._request_revalidate)
        self.revalidate_btn.hide()
        bl.addWidget(self.revalidate_btn)
        self.banner.hide()
        ml.addWidget(self.banner)
        filters = QHBoxLayout()
        task_filters = QHBoxLayout()
        self.pickers: dict[str, QComboBox] = {}
        for key in ("status", "completeness", "source_id", "unit", *TASK_PICKERS):
            box = QComboBox(mid)
            box.setAccessibleName(f"Filter by {_TITLES[key]}")
            box.addItem(f"{_TITLES[key]}: {ANY}")
            box.currentIndexChanged.connect(self._filter_changed)
            if key in OUTCOME_RULE:
                set_tooltip(box, OUTCOME_RULE[key])
            self.pickers[key] = box
            (task_filters if key in TASK_PICKERS else filters).addWidget(box)
        task_filters.addStretch(1)
        self.issue_picker = QComboBox(mid)
        self.issue_picker.setAccessibleName("Filter by issue code")
        self.issue_picker.addItem(f"issue: {ANY}")
        self.issue_picker.currentIndexChanged.connect(self._filter_changed)
        filters.addWidget(self.issue_picker)
        self.ex_filter = QLineEdit(mid)
        self.ex_filter.setAccessibleName("Filter executions by id")
        self.ex_filter.setPlaceholderText("id contains")
        self.ex_filter.setClearButtonEnabled(True)
        self.ex_filter.textChanged.connect(self._filter_changed)
        filters.addWidget(self.ex_filter, 1)
        self.count_label = SafeLabel("", name="Executions count", parent=mid)
        filters.addWidget(self.count_label)
        ml.addLayout(filters)
        ml.addLayout(task_filters)
        self.derive_hint = SafeLabel("This corpus has working rows only: derive it (agentprov derive) for the suite, "
                                     "task, attack, defence and outcome columns.", name="Derive hint", parent=mid)
        self.derive_hint.hide()
        ml.addWidget(self.derive_hint)
        self.legend = SafeLabel(f"{theme.ATTACK_GLYPH} {ATTACK_RULE}", name="Attack succeeded legend", parent=mid)
        self.legend.setWordWrap(True)
        self.legend.hide()
        ml.addWidget(self.legend)
        cli_row = QHBoxLayout()
        self.cli_line = SafeLabel("", name="CLI selection", parent=mid)
        self.cli_line.setWordWrap(True)
        cli_row.addWidget(self.cli_line, 1)
        self.copy_cli_btn = QPushButton("Copy CLI", mid)
        self.copy_cli_btn.setAccessibleName("Copy the CLI selection")
        set_tooltip(self.copy_cli_btn, "The agentprov stats command that selects the rows shown (D-700)")
        self.copy_cli_btn.clicked.connect(self._copy_cli)
        cli_row.addWidget(self.copy_cli_btn)
        ml.addLayout(cli_row)
        self.model = ExecutionsModel()
        self.exec_view = QTableView(mid)
        self.exec_view.setAccessibleName("Executions table")
        self.exec_view.setModel(self.model)
        self.exec_view.setSortingEnabled(True)
        self.exec_view.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.exec_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.exec_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.exec_view.verticalHeader().setVisible(False)
        self.exec_view.verticalHeader().setDefaultSectionSize(22)
        self.exec_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.exec_view.horizontalHeader().setStretchLastSection(True)
        self.exec_view.setWordWrap(False)
        self.exec_view.selectionModel().currentRowChanged.connect(self._row_changed)
        self.exec_view.doubleClicked.connect(self._open_index)
        for return_key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):  # D-845: Return opens the execution in a new tab
            sc = QShortcut(QKeySequence(return_key), self.exec_view, context=Qt.ShortcutContext.WidgetShortcut)
            sc.activated.connect(self.open_current_in_tab)
        self.exec_view.setAccessibleDescription("Return or a double-click opens the execution in a new tab")
        self.exec_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.exec_view.customContextMenuRequested.connect(self._exec_menu)
        ml.addWidget(self.exec_view, 1)
        split.addWidget(mid)
        # the preview of the selected execution (D-842)
        self.preview = ExecutionPane(cache_dir, self.cache, compact=True, content_limit=self.content_limit, parent=split)
        self.preview.render_requested.connect(self.render_requested)
        self.preview.open_requested.connect(self.open_current_in_tab)
        split.addWidget(self.preview)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 3)
        split.setStretchFactor(2, 5)
        split.setSizes([150, 260, 600])
        brl.addWidget(split)
        self.doc_tabs.addTab(self.browser, "Corpora")
        bar = self.doc_tabs.tabBar()
        for side in (QTabBar.ButtonPosition.LeftSide, QTabBar.ButtonPosition.RightSide):
            bar.setTabButton(0, side, None)  # D-840: the corpus browser cannot be closed
        bar.setAccessibleTabName(0, "Corpora browser")
        set_tab_tooltip(self.doc_tabs, 0, "The corpora list and the executions table (not closable)")
        bar.tabMoved.connect(self._tab_moved)
        bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        bar.customContextMenuRequested.connect(self._tab_menu)
        bar.installEventFilter(self)
        self.doc_tabs.tabCloseRequested.connect(self.close_tab)
        self.doc_tabs.currentChanged.connect(self._tab_changed)
        lay.addWidget(self.doc_tabs)
        self._refresh_tabs()

    # ------------------------------------------------------------------------------------------ corpora
    def refresh(self) -> None:
        self.corpora.set_rows(discover(self.roots))
        self.corpora_view.resizeColumnsToContents()
        self.status_message.emit(f"{len(self.corpora.rows)} corpora found")

    def _corpus_activated(self, index: QModelIndex) -> None:
        if index.isValid():
            self.open_corpus(self.corpora.rows[index.row()])

    def open_path(self, path: Path) -> None:
        from agentprov_gui.readmodel.corpus import summarise

        self.open_corpus(summarise(path))

    def open_corpus(self, summary: CorpusSummary) -> None:
        """Open ``summary`` read-only and load its executions table in the background."""
        self._cancel.set()
        self._cancel = threading.Event()
        cancel = self._cancel
        self._gen += 1
        gen = self._gen
        self.summary = summary
        self.reader, self.table = None, None
        self.cache.clear()
        self.model.set_table(None)
        self.preview.clear()
        self._show_banner(summary)
        if summary.root is None:
            self.status_message.emit(f"{T.line(summary.name, 80)} cannot be opened ({T.line(summary.error, 60)})")
            return
        self._opened_at = time.perf_counter()
        self.count_label.set_plain("reading the index…")

        def work(signals: JobSignals) -> tuple[CorpusReader, ExecutionTable]:
            reader = CorpusReader.open(summary.path)
            table = load_table(reader, on_chunk=signals.progress.emit, cancel=cancel)
            return reader, table

        submit(self, work, partial(self._table_loaded, gen), partial(self._table_failed, gen),
               partial(self._progress, gen), self.pool)

    def _progress(self, gen: int, rows: int) -> None:
        if gen == self._gen:
            self.count_label.set_plain(f"reading… {rows:,}")

    def _request_revalidate(self) -> None:
        if self.summary is not None:
            self.revalidate_requested.emit(str(self.summary.path))

    def _show_banner(self, s: CorpusSummary) -> None:
        if s.writing:
            text = f"{T.line(s.name, 80)} is a working tree being written by a CLI job. It is read without a lock; " \
                   "documents may change while you look."
        elif s.state != "sealed":
            text = f"{T.line(s.name, 80)} is not sealed and not verified. Run Verify first (G.8.6)."
        else:
            verified = self.verified_lookup(s.path)
            if verified is not None:
                text = f"{T.line(s.name, 80)} is sealed and verified ({T.line(verified, 160)})."
            else:
                text = f"{T.line(s.name, 80)} is sealed but has not been verified by this GUI. Run Verify first (G.8.6)."
        self.revalidate_btn.setVisible(s.prov_conformance == "skipped")
        if s.prov_conformance == "skipped":
            text += " The PROV conformance check (tier 4) was skipped: this corpus is unvalidated until a full " \
                    "recompute validates it into a new corpus (Revalidate); do not report its results (§8.3a)."
        self.banner_text.set_plain(text)
        self.banner.show()

    def _table_failed(self, gen: int, code: str) -> None:
        if gen != self._gen or code == "LoadCancelled":
            return
        self.count_label.set_plain("")
        self.status_message.emit(f"The executions index cannot be read ({T.line(code, 80)}).")

    def _table_loaded(self, gen: int, res: tuple[CorpusReader, ExecutionTable]) -> None:
        if gen != self._gen:
            return
        self.reader, self.table = res
        self.model.set_table(self.table)
        shown = {c.key for c in self.model.columns}
        for key, box in self.pickers.items():
            box.blockSignals(True)
            box.clear()
            box.addItem(f"{_TITLES[key]}: {ANY}")
            values = self.table.vocabulary(key)
            for v in values:
                box.addItem(OUTCOME_LABELS[v] if key in OUTCOME_RULE else T.line(v, 80), v)
            box.setVisible(key not in TASK_PICKERS or (key in shown and bool(values)))
            box.blockSignals(False)
        self.derive_hint.setVisible(len(self.table) > 0 and self.table.full_rows == 0)
        self.legend.setVisible(ATTACK_KEY in shown)
        self.issue_picker.blockSignals(True)
        self.issue_picker.clear()
        self.issue_picker.addItem(f"issue: {ANY}")
        for code in self.table.issue_codes():
            self.issue_picker.addItem(T.line(code, 80), code)
        self.issue_picker.blockSignals(False)
        self.ex_filter.clear()
        self._update_count()
        self._update_cli()
        header = self.exec_view.horizontalHeader()
        for i in range(self.model.columnCount()):
            header.resizeSection(i, 240 if self.model.columns[i].key == "ex" else 110)
        self.last_open_seconds = time.perf_counter() - self._opened_at
        name = self.summary.name if self.summary else ""
        self.corpus_opened.emit(name, self.last_open_seconds)
        self.status_message.emit(
            f"{T.line(name, 80)}: {len(self.table):,} executions in {self.last_open_seconds:.2f} s (read-only)")
        if self._pending_reveal is not None:
            ex, self._pending_reveal = self._pending_reveal, None
            self.select_ex(ex)

    def _filter_changed(self) -> None:
        if self.table is None:
            return
        pickers = []
        for key, box in self.pickers.items():
            value = box.currentData()
            if isinstance(value, str):
                pickers.append((key, frozenset({value})))
        issue = self.issue_picker.currentData()
        flt = TableFilter(tuple(pickers), self.ex_filter.text().strip(), issue if isinstance(issue, str) else None)
        self.model.apply(flt)
        self._update_count()
        self._update_cli()

    def corpus_arg(self) -> str | None:
        """The open corpus as ``--corpus`` names it: the absolute final ``DIR``, also when the tree read is
        ``DIR.partial`` (the core resolves ``DIR`` to it, N.1.5); ``None`` when none is open."""
        if self.reader is None:
            return None
        root = self.reader.root
        if self.reader.used_partial and root.name.endswith(PARTIAL_SUFFIX):
            root = root.with_name(root.name[: -len(PARTIAL_SUFFIX)])
        return str(root)

    def cli_command(self) -> tuple[str, list[str]]:
        """The ``agentprov stats`` command that selects the rows shown (D-700, D-706), and what it cannot express."""
        args, notes = cli_selection(self.model.filter)
        corpus = self.corpus_arg() or "CORPUS"
        return shlex.join(["agentprov", "stats", "--corpus", corpus, *args]), notes

    def _update_cli(self) -> None:
        command, notes = self.cli_command()
        self.cli_line.set_plain(T.line("CLI: " + command + ("" if not notes else "  (" + "; ".join(notes) + ")"), 600))

    def _copy_cli(self) -> None:
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self.cli_command()[0])

    def _update_count(self) -> None:
        total = len(self.table) if self.table is not None else 0
        shown = self.model.rowCount()
        self.count_label.set_plain(f"{shown:,} of {total:,}" if shown != total else f"{total:,} executions")

    def _clear_filters(self) -> None:
        for box in (*self.pickers.values(), self.issue_picker):
            box.blockSignals(True)
            box.setCurrentIndex(0)
            box.blockSignals(False)
        self.ex_filter.blockSignals(True)
        self.ex_filter.clear()
        self.ex_filter.blockSignals(False)
        self._filter_changed()

    def select_ex(self, ex: str) -> bool:
        """Select ``ex``'s row in the executions table (clearing the filters when they hide it) and show the Corpora
        tab. ``False`` when the open corpus has no such execution."""
        if self.table is None:
            return False
        rows = [i for i in range(len(self.table)) if self.table.ex(i) == ex]
        if not rows:
            return False
        if rows[0] not in self.model.order:
            self._clear_filters()
        view_row = self.model.order.index(rows[0])
        self.doc_tabs.setCurrentIndex(0)
        self.exec_view.selectRow(view_row)
        self.exec_view.scrollTo(self.model.index(view_row, 0))
        return True

    # ------------------------------------------------------------------------------------------ preview (D-842)
    def _source(self) -> CorpusSource | None:
        if self.reader is None or self.summary is None:
            return None
        return CorpusSource(self.summary.name, str(self.reader.root), self.summary.path, self.corpus_arg() or "",
                            self.summary.writing)

    def _row_changed(self, current: QModelIndex, _prev: QModelIndex) -> None:
        source = self._source()
        if not current.isValid() or self.table is None or self.reader is None or source is None:
            return
        self.preview.load(self.reader, self.table, self.model.table_row(current.row()), source)

    # ------------------------------------------------------------------------------------------ execution tabs
    def _open_index(self, index: QModelIndex) -> None:
        if index.isValid():
            self.open_row(index.row())

    def open_current_in_tab(self) -> None:
        """Open in New Tab (D-842, D-845): the execution selected in the table."""
        index = self.exec_view.currentIndex()
        if index.isValid():
            self.open_row(index.row())

    def open_row(self, view_row: int) -> ExecutionPane | None:
        """Open the execution at ``view_row`` of the table in a tab of its own, or focus its tab when it is open."""
        source = self._source()
        if self.table is None or self.reader is None or source is None or not 0 <= view_row < self.model.rowCount():
            return None
        row = self.model.table_row(view_row)
        ex = self.table.ex(row)
        key = (source.root, ex)
        pane = self.exec_tabs.get(key)
        if pane is not None:
            self.doc_tabs.setCurrentWidget(pane)
            return pane
        if len(self.exec_tabs) >= MAX_TABS:
            self._evict()
        pane = ExecutionPane(self.cache_dir, self.cache, compact=False, content_limit=self.content_limit,
                             exact_palette=self.exact_palette, parent=self.doc_tabs)
        pane.render_requested.connect(self.render_requested)
        pane.reveal_requested.connect(partial(self.reveal_in_corpora, pane))
        pane.state_changed.connect(self._refresh_tabs)
        self.exec_tabs[key] = pane
        preview = self.preview
        if preview.state == "ready" and preview.detail is not None and preview.detail.ex == ex and \
                preview.source is not None and preview.source.root == source.root:
            pane.show_detail(preview.detail, source)  # shared with the preview, not read again (D-843)
        else:
            pane.load(self.reader, self.table, row, source)
        self.doc_tabs.addTab(pane, "")
        self.doc_tabs.setCurrentWidget(pane)
        self._refresh_tabs()
        return pane

    def _evict(self) -> None:
        """D-843: close the least recently viewed execution tab (never the current one) and say which."""
        current = self.doc_tabs.currentWidget()
        for pane in self._viewed + [p for p in self.exec_tabs.values() if p not in self._viewed]:
            if pane is not current:
                ex = pane.ex or ""
                self.close_tab(self.doc_tabs.indexOf(pane))
                self.status_message.emit(f"Closed the tab of {T.line(ex)}: at most {MAX_TABS} execution tabs are "
                                         "open (the least recently viewed closes first)")
                return

    def pane_at(self, index: int) -> ExecutionPane | None:
        w = self.doc_tabs.widget(index)
        return w if isinstance(w, ExecutionPane) and w is not self.preview else None

    def close_tab(self, index: int) -> bool:
        """Close the execution tab at ``index``; ``False`` for the Corpora tab (never closed) or no tab."""
        pane = self.pane_at(index)
        if pane is None:
            return False
        for key, p in list(self.exec_tabs.items()):
            if p is pane:
                del self.exec_tabs[key]
        if pane in self._viewed:
            self._viewed.remove(pane)
        pane.clear()  # supersedes its pending loads; releases the scene and hides the popover
        self.doc_tabs.removeTab(index)
        pane.deleteLater()
        self._refresh_tabs()
        return True

    def close_current_tab(self) -> bool:
        """⌘W (D-845): close the current execution tab; ``False`` on the Corpora tab (the window closes instead)."""
        return self.close_tab(self.doc_tabs.currentIndex())

    def close_other_tabs(self, keep: ExecutionPane | None = None) -> None:
        """⌥⌘W (D-845): close every execution tab except ``keep`` (default: the current one)."""
        if keep is None:
            current = self.doc_tabs.currentWidget()
            keep = current if isinstance(current, ExecutionPane) else None
        for pane in list(self.exec_tabs.values()):
            if pane is not keep:
                self.close_tab(self.doc_tabs.indexOf(pane))

    def step_tab(self, step: int) -> None:
        """⌘⇧] / ⌘⇧[ (D-845): the next or previous tab, wrapping."""
        n = self.doc_tabs.count()
        if n > 1:
            self.doc_tabs.setCurrentIndex((self.doc_tabs.currentIndex() + step) % n)

    def show_corpora(self) -> None:
        self.doc_tabs.setCurrentIndex(0)

    def reveal_in_corpora(self, pane: ExecutionPane) -> None:
        """Show in Corpora (D-841): select the execution's row; opens its corpus first when another one is open."""
        if pane.ex is None or pane.source is None:
            return
        if self.reader is not None and str(self.reader.root) == pane.source.root:
            if not self.select_ex(pane.ex):
                self.status_message.emit(f"{T.line(pane.ex)} is not in the open corpus's index any more")
            return
        self._pending_reveal = pane.ex
        self.doc_tabs.setCurrentIndex(0)
        self.open_path(pane.source.path)

    def _tab_changed(self, index: int) -> None:
        pane = self.pane_at(index)
        if pane is not None:
            if pane in self._viewed:
                self._viewed.remove(pane)
            self._viewed.append(pane)
            pane.graph.restore_scene()
        # D-843: only the LIVE_SCENES most recently viewed tabs keep a live graph scene
        for old in self._viewed[:-LIVE_SCENES]:
            old.graph.release_scene()

    def _tab_moved(self, _from: int, _to: int) -> None:
        if self._fixing_order:
            return
        at = self.doc_tabs.indexOf(self.browser)
        if at != 0:  # D-840: the corpus browser stays first
            self._fixing_order = True
            self.doc_tabs.tabBar().moveTab(at, 0)
            self._fixing_order = False

    def _refresh_tabs(self) -> None:
        """Titles, tooltips, accessible names and the counter of the execution tabs (D-840, D-845)."""
        roots = {p.source.root for p in self.exec_tabs.values() if p.source is not None}
        bar = self.doc_tabs.tabBar()
        for i in range(self.doc_tabs.count()):
            pane = self.pane_at(i)
            if pane is None or pane.source is None:
                continue
            ex = T.line(pane.ex or "")
            corpus = T.line(pane.source.name, 80)
            title = elide_middle(ex)
            if len(roots) > 1:
                title += f" · {elide_middle(corpus, 24)}"
            state = {"loading": "loading", "failed": "cannot be opened"}.get(pane.state, "ready")
            if state != "ready":
                title += f" · {state}…" if state == "loading" else f" · {state}"
            self.doc_tabs.setTabText(i, tab_text(title))
            set_tab_tooltip(self.doc_tabs, i, f"{ex}\n{corpus}\n{T.line(str(pane.source.path), 300)}")
            bar.setAccessibleTabName(i, f"Execution {ex} in corpus {corpus}, {state}")
            for side in (QTabBar.ButtonPosition.LeftSide, QTabBar.ButtonPosition.RightSide):
                button = bar.tabButton(i, side)
                if button is not None:
                    button.setAccessibleName(f"Close {ex}")
        n = len(self.exec_tabs)
        self.tab_count.set_plain(f"{n} of {MAX_TABS} open" if n else "")

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        # D-845: a middle-click closes an execution tab
        if watched is self.doc_tabs.tabBar() and event.type() == QEvent.Type.MouseButtonRelease and \
                isinstance(event, QMouseEvent) and event.button() == Qt.MouseButton.MiddleButton:
            index = self.doc_tabs.tabBar().tabAt(event.position().toPoint())
            if self.close_tab(index):
                return True
        return super().eventFilter(watched, event)

    def _tab_menu(self, pos: QPoint) -> None:
        bar = self.doc_tabs.tabBar()
        pane = self.pane_at(bar.tabAt(pos))
        if pane is None:
            return
        menu = QMenu(self)
        menu.addAction("Close Tab", lambda: self.close_tab(self.doc_tabs.indexOf(pane)))
        menu.addAction("Close Other Tabs", lambda: self.close_other_tabs(pane))
        menu.addSeparator()
        menu.addAction("Show in Corpora", lambda: self.reveal_in_corpora(pane))
        menu.addAction("Reload Execution", pane.reload)
        menu.addAction("Copy Execution Id", lambda: self._copy_text(pane.ex))
        menu.exec(bar.mapToGlobal(pos))

    def _exec_menu(self, pos: QPoint) -> None:
        index = self.exec_view.indexAt(pos)
        if not index.isValid() or self.table is None:
            return
        ex = self.table.ex(self.model.table_row(index.row()))
        menu = QMenu(self)
        menu.addAction("Open in New Tab", lambda: self.open_row(index.row()))
        menu.addAction("Copy Execution Id", lambda: self._copy_text(ex))
        menu.exec(self.exec_view.viewport().mapToGlobal(pos))

    @staticmethod
    def _copy_text(text: str | None) -> None:
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None and text:
            clipboard.setText(text)

    def panes(self) -> list[ExecutionPane]:
        """The preview and every execution tab (Settings changes apply to all of them)."""
        return [self.preview, *self.exec_tabs.values()]

    def set_show_content_limit(self, limit: int) -> None:
        self.content_limit = max(1, min(limit, T.CONTENT_CHARS_MAX))
        for pane in self.panes():
            pane.set_show_content_limit(self.content_limit)

    def set_exact_palette(self, exact: bool) -> None:
        self.exact_palette = exact
        for pane in self.panes():
            pane.set_exact_palette(exact)
