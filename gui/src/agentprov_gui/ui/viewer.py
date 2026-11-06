"""The Viewer (design §6.1; wireframe 01; macos-design §3.3 "Viewer", "Execution detail"; D-840..D-845; D-1060).

A document tab bar: the first tab, **Corpora**, is the corpus browser; every other tab is one execution opened with a
double-click, Return or Open in New Tab (:class:`~agentprov_gui.ui.execution.ExecutionPane`: Graph + PROV-JSON side
by side, AER, SEM, Register, Validation, Raw, Index Row). At most :data:`MAX_TABS` execution tabs; only the
:data:`LIVE_SCENES` most recently viewed keep a live graph scene.

The corpus browser has **three panes** (D-1060, the user's 2026-11-05 design), divided by 1 px lines:

* **Corpora** (left): a source list of the corpora under the corpus roots, grouped by state (Sealed, Working, Being
  written, Unreadable), each row the corpus's name and its execution count, a filter box and Open Folder…; choosing a
  row opens the corpus. Its manifest facts (id, version, content digest, folder, state) are in Corpus Details.
* **Executions** (middle): a header with the corpus's name, its state and verification as badges, its version and
  execution count and the actions that apply (Verify…, Revalidate…, Corpus Details); the filters as applied chips
  ("Attack: important_instructions ×") with + Add filter (every facet's values with how many executions each would
  show) and Clear all; the executions table (virtualised, model-side sort and filter); and a collapsed "Terminal
  command for this view" with the ``agentprov stats`` that selects the rows shown (D-700, D-706). The id search is the
  window's toolbar search field (:meth:`ViewerPage.set_search`; a chip shows it).
* **Inspector** (right): the selected execution (a compact :class:`ExecutionPane`).

The two side panes collapse to a slim labelled strip that says what they hold ("CORPORA · name", "EXECUTION · ex_…");
the strip, the toolbar buttons at the tab bar's corners and View › Show/Hide Corpora and Inspector open them again.
Their widths and states are remembered in the GUI's QSettings; when the window is narrow, the inspector collapses
first, then the corpora list (both stay one click away), and they come back when it is wide again.

Opening a corpus is **read-only**: no write, no lock, nothing created inside it. Index and detail loads run in worker
threads and come back as immutable objects; a newer request supersedes an older one (generation counter).
"""

from __future__ import annotations

import shlex
import threading
import time
from collections import Counter
from collections.abc import Callable, Sequence
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
    QPointF,
    QRectF,
    QSettings,
    QSize,
    Qt,
    QThreadPool,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QAction,
    QColor,
    QGuiApplication,
    QIcon,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QPixmap,
    QResizeEvent,
    QShortcut,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStyle,
    QStyleOptionViewItem,
    QTabBar,
    QTableView,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from agentprov_gui import text as T
from agentprov_gui.jobs.commands import FORMS, FormError, build_spec
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
from agentprov_gui.ui.brand import SourceListDelegate
from agentprov_gui.ui.detail import field_tip, tidy_view
from agentprov_gui.ui.execution import EXECUTION_ID, CorpusSource, ExecutionPane
from agentprov_gui.ui.forms import (
    CommandCard,
    Disclosure,
    FactGrid,
    FlowLayout,
    StatusBadge,
    caption,
    heading,
    link_button,
)
from agentprov_gui.ui.safe import (
    SafeLabel,
    help_tooltip,
    is_tooltip_role,
    safe_tooltip,
    set_action_tooltip,
    set_control_tooltip,
    set_list_item_tooltip,
    set_tab_tooltip,
    set_tooltip,
    tab_text,
)
from agentprov_gui.ui.worker import JobSignals, submit

__all__ = ["EXECUTION_ID", "FACETS", "LIVE_SCENES", "MAX_TABS", "CollapsedStrip", "ExecutionsModel", "SidePane",
           "ViewerPage", "elide_middle", "verify_values"]

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
#: the filters of the task and outcome columns (a derived corpus); offered only when the column is shown
TASK_PICKERS: Final = ("cell.suite", "cell.attack_id", "cell.attack_target_id", "cell.defense_id", "model.requested",
                       "outcome.user_task_solved", ATTACK_KEY)
#: every column filter, in the order the selection (and so ``agentprov stats --select``) lists them, whatever order
#: the chips were added in; the issue code is its own part of the selection (TableFilter.issue_code)
FACETS: Final = ("status", "completeness", "source_id", "unit", *TASK_PICKERS)
ISSUE: Final = "issue"
#: the order + Add filter lists them in
MENU_ORDER: Final = ("status", "completeness", "source_id", "unit", ISSUE, "cell.suite", "cell.attack_id",
                     "cell.attack_target_id", "cell.defense_id", "model.requested", "outcome.user_task_solved",
                     ATTACK_KEY)
_TITLES: Final = {c.key: c.title for c in COLUMNS}
#: D-1060: each executions column's header in plain words (the index field it shows is in the header's tooltip)
PLAIN: Final = {
    "ex": "Execution", "status": "Status", "completeness": "Completeness", "source_id": "Source",
    "snapshot": "Snapshot", "unit": "Record type", "profile": "Source profile", "cell.suite": "Suite",
    "cell.task_id": "User task", "cell.attack_id": "Attack", "cell.attack_target_id": "Injection task",
    "cell.defense_id": "Defence", ATTACK_KEY: "Attack succeeded", "outcome.user_task_solved": "Utility",
    "model.requested": "Model requested", "model.served": "Model served", "judgements": "Judgements",
    "cell.repeat": "Repeat", "n.messages": "Messages", "n.model_calls": "Model calls", "n.tool_executions": "Tool runs",
    "n_issues": "Issues", "attempt": "Attempt", "issue": "Issue",
}  # fmt: skip
#: Corpus Details: each fact's name in plain words, and the field it shows (the names' tooltips)
CORPUS_HEADERS: Final = ("Corpus", "State", "Corpus id", "Version", "Executions", "Content digest", "Folder")
CORPUS_FIELDS: Final = ("the folder's name", "state", "corpus_id", "corpus_version", "executions", "content_digest",
                        "root")
#: what each fact of Corpus Details holds
CORPUS_TIPS: Final = (
    "The corpus folder's name.",
    "sealed (finished; never written again), working (not sealed yet), writing (a CLI job holds its lock now) or "
    "unreadable (the reason is under the facts).",
    "The corpus id from corpus.json.",
    "The corpus version (SemVer) from corpus.json.",
    "The number of executions the manifest (corpus.json) counts.",
    "The corpus content digest from corpus.json.",
    "The folder that holds the corpus: one of the corpus roots in Settings, or a folder opened with Open Folder….",
)
#: what each column of the executions table holds (header tooltips; the outcome columns use OUTCOME_RULE)
COLUMN_TIPS: Final = {
    "ex": "The execution id. Double-click or Return opens the execution in a tab of its own.",
    "status": "ok, ok with issues (a warning in the register) or failed (a failed stage or an error-severity issue).",
    "completeness": "verified complete (the record reconciles with the source), known incomplete (a rule proves loss) "
                    "or unverifiable (the source does not record enough to tell).",
    "source_id": "The registry id of the source the execution came from.",
    "snapshot": "The source snapshots in which this execution was found.",
    "unit": "What the record describes: an observed agent execution, an outcome only (no trajectory) or a scenario.",
    "profile": "The source profile (id@version) that mapped the execution.",
    "cell.suite": "The benchmark suite.",
    "cell.task_id": "The user task.",
    "cell.attack_id": "The attack (injection method); blank on a benign cell.",
    "cell.attack_target_id": "The injection task the attack tries to achieve; blank on a benign cell.",
    "cell.defense_id": "The defence the run used; blank when none was recorded.",
    "model.requested": "The model the run asked for.",
    "model.served": "The model the provider reports it served.",
    "judgements": "The benchmark's own outcome judgements, as recorded.",
    "cell.repeat": "The repeat index of the cell.",
    "n.messages": "Messages in the execution.",
    "n.model_calls": "Model calls in the execution.",
    "n.tool_executions": "Tool executions in the execution.",
    "n_issues": "Issue codes in the register for this execution; hover a cell for the codes.",
    "attempt": "Live runs: the attempt index of this cell (0-based). Blank for imports.",
    ISSUE: "An issue code in the register for this execution.",
}
#: the corpora list's groups, in order: (key, heading); a state of any other name gets a group of its own after them
GROUPS: Final = (("sealed", "Sealed"), ("working", "Working"), ("writing", "Being written"),
                 ("unreadable", "Unreadable"))

#: the panes (D-1060): the strip a collapsed side pane leaves, and the widths a pane keeps while open
STRIP: Final = 34
CORPORA_WIDTH: Final = (180, 220, 420)  # minimum, default, maximum
INSPECTOR_WIDTH: Final = (300, 380, 900)
MIDDLE_MIN: Final = 300
#: a pane the window's width collapsed opens again only once this much more width is there (no flicker at the edge)
REOPEN_MARGIN: Final = 40
CORPORA: Final = "corpora"
INSPECTOR: Final = "inspector"


def elide_middle(text: str, limit: int = TAB_TITLE_CHARS) -> str:
    """``text`` shortened in the middle to ``limit`` characters (D-840: the start and the end of an id both matter)."""
    if len(text) <= limit:
        return text
    head = (limit - 1) // 2
    return text[:head] + "…" + text[len(text) - (limit - 1 - head):]


def verify_values(corpus: Path) -> dict[str, Any]:
    """The verify form's values for the notice's Verify… (the form's own default level, chain): the one place the main
    window's verify form and the Viewer's terminal command both take them from."""
    return {"corpus": str(corpus if corpus.is_absolute() else corpus.absolute())}


def display_argv(argv: Sequence[str]) -> tuple[list[str], bool]:
    """``argv`` as the terminal-command card may show and copy it (S3): each argument escaped as one display line
    where it needs it (a corpus value with a control or bidi character), and whether any was."""
    shown = [T.clean(a, 600) for a in argv]
    return shown, shown != list(argv)


def menu_text(text: str) -> str:
    """A menu item's text: ``&`` doubled, so a value never turns a letter into a mnemonic."""
    return text.replace("&", "&&")


def value_label(key: str, value: str) -> str:
    """A filter value as the menus and chips show it: an outcome state in words, any other value escaped (S3)."""
    return OUTCOME_LABELS.get(value, value) if key in OUTCOME_RULE else T.line(value, 80)


def value_full(key: str, value: str) -> str:
    """A filter value whole, for a tooltip (:func:`safe.safe_tooltip` escapes it): :func:`value_label` cuts a long
    value at 80 characters and a chip elides it further."""
    return OUTCOME_LABELS.get(value, value) if key in OUTCOME_RULE else value


def group_of(summary: CorpusSummary) -> str:
    """The corpora list's group of ``summary``: being written before its state."""
    return "writing" if summary.writing else summary.state


# ----------------------------------------------------------------------------------------------- models
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
        column = self.columns[section]
        key = column.key
        title = PLAIN.get(key, column.title)
        if role == Qt.ItemDataRole.DisplayRole:
            return f"{theme.ATTACK_GLYPH} {title}" if key == ATTACK_KEY else title
        if is_tooltip_role(role):
            tip = OUTCOME_RULE.get(key) or COLUMN_TIPS.get(key)
            if not tip:
                return None
            raw = key + (f"; agentprov stats --select {column.selector}=…" if column.selector else "")
            return help_tooltip(field_tip(tip, raw, "index field"))
        return None


# ----------------------------------------------------------------------------------------------- pane parts
def pane_icon(side: str, colour: QColor, *, shown: bool, size: int = 16, ratio: float = 2.0) -> QIcon:
    """The toolbar glyph of a side pane, drawn as a path: a window outline with a divider near ``side`` (``left`` or
    ``right``); the pane's part is filled while it is shown."""
    pixmap = QPixmap(int(size * ratio), int(size * ratio))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    outline = QRectF(1.5, 2.5, 13.0, 11.0)
    x = 6.0 if side == "left" else 10.0
    if shown:
        fill = QPainterPath()
        part = QRectF(outline.left(), outline.top(), x - outline.left(), outline.height()) if side == "left" else \
            QRectF(x, outline.top(), outline.right() - x, outline.height())
        fill.addRoundedRect(part, 1.5, 1.5)
        tint = QColor(colour)
        tint.setAlphaF(0.35)
        painter.fillPath(fill, tint)
    pen = QPen(colour, 1.3)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    path = QPainterPath()
    path.addRoundedRect(outline, 2.0, 2.0)
    path.moveTo(QPointF(x, outline.top()))
    path.lineTo(QPointF(x, outline.bottom()))
    painter.drawPath(path)
    painter.end()
    return QIcon(pixmap)


class CollapsedStrip(QAbstractButton):
    """A collapsed side pane: a slim strip (:data:`STRIP` px) with a chevron and, written downwards, what the pane
    holds ("CORPORA · name"). A click, Space or Return opens the pane again. Its text is drawn as plain text."""

    def __init__(self, side: str, *, name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.side = side
        self.label = ""
        self.setAccessibleName(name)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setFixedWidth(STRIP)
        self.setMouseTracking(True)

    def set_label(self, text: str) -> None:
        self.label = text
        self.setAccessibleDescription(text)
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(STRIP, 120)

    def minimumSizeHint(self) -> QSize:
        return QSize(STRIP, 40)

    def paintEvent(self, _event: QPaintEvent) -> None:
        t = theme.tokens()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.underMouse() or self.isDown():
            painter.fillRect(self.rect(), QColor(t.pressed if self.isDown() else t.hover))
        # the chevron in a small rounded square at the top: › opens the left pane, ‹ the right one
        box = QRectF((STRIP - 22) / 2, 10, 22, 22)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(t.pressed))
        painter.drawRoundedRect(box, 5, 5)
        pen = QPen(QColor(t.secondary), 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        cx, cy = box.center().x(), box.center().y()
        d = 2.5 if self.side == "left" else -2.5
        chevron = QPainterPath(QPointF(cx - d, cy - 4.5))
        chevron.lineTo(QPointF(cx + d, cy))
        chevron.lineTo(QPointF(cx - d, cy + 4.5))
        painter.drawPath(chevron)
        if self.hasFocus():
            focus = QPen(QColor(t.accent), 1.5)
            painter.setPen(focus)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5), 5, 5)
        # the label, written downwards (rotated a quarter turn clockwise), elided to the strip's height
        painter.setPen(QColor(t.secondary))
        painter.setFont(theme.scaled_font("caption"))
        length = max(0, self.height() - 52)
        text = painter.fontMetrics().elidedText(self.label, Qt.TextElideMode.ElideRight, length)
        painter.translate(STRIP / 2 + painter.fontMetrics().ascent() / 2 - 1, 44)
        painter.rotate(90)
        painter.drawText(QPointF(0, 0), text)
        painter.end()


class SidePane(QFrame):
    """A side pane of the Viewer that collapses to a :class:`CollapsedStrip` (D-1060). It keeps its widths: while open,
    between ``minimum`` and ``maximum``; collapsed, exactly the strip's width. :attr:`auto` marks a pane the window's
    width collapsed (it opens again by itself), as against one the user closed."""

    toggled = Signal(bool)  # open

    def __init__(self, content: QWidget, *, side: str, name: str, strip_name: str, widths: tuple[int, int, int],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName(f"viewer-{side}")
        self.setAccessibleName(name)
        self.side = side
        self.minimum, self.default, self.maximum = widths
        self.auto = False
        self._open = True
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.content = content
        self.strip = CollapsedStrip(side, name=strip_name, parent=self)
        lay.addWidget(self.content)
        lay.addWidget(self.strip)
        self.strip.hide()
        self._limits()

    def is_open(self) -> bool:
        return self._open

    def set_open(self, opened: bool, *, auto: bool = False) -> None:
        """Open or collapse; ``auto``: the window's width did it (else the user did, and the pane is not reopened by
        itself)."""
        self.auto = auto and not opened
        if opened == self._open:
            return
        self._open = opened
        self.content.setVisible(opened)
        self.strip.setVisible(not opened)
        self._limits()
        self.toggled.emit(opened)

    def _limits(self) -> None:
        if self._open:
            self.setMinimumWidth(self.minimum)
            self.setMaximumWidth(self.maximum)
        else:
            self.setFixedWidth(STRIP)

    def width_wanted(self, remembered: int | None) -> int:
        """The width to give the pane: the strip's while collapsed, else the remembered width within its limits."""
        if not self._open:
            return STRIP
        return max(self.minimum, min(self.maximum, remembered or self.default))


class CorporaDelegate(SourceListDelegate):
    """The corpora list as a source list (:class:`brand.SourceListDelegate`): group headings in small capitals, each
    row the corpus's name with its execution count at the right (grey). Text is drawn as plain text."""

    COUNT_ROLE: Final = int(Qt.ItemDataRole.UserRole) + 11

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> None:
        if self._section(index):
            super().paint(painter, option, index)
            return
        t = theme.tokens()
        rect = QRectF(option.rect)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        view = option.widget
        focused = isinstance(view, QAbstractItemView) and view.hasFocus() and view.isActiveWindow()
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        box = rect.adjusted(6, 1, -6, -1)
        if selected:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(t.accent if focused else t.pressed))
            painter.drawRoundedRect(box, 6, 6)
        elif option.state & QStyle.StateFlag.State_MouseOver:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(t.hover))
            painter.drawRoundedRect(box, 6, 6)
        on_accent = selected and focused
        count = str(index.data(self.COUNT_ROLE) or "")
        painter.setFont(theme.scaled_font("caption", option.font))
        count_width = painter.fontMetrics().horizontalAdvance(count) if count else 0
        painter.setPen(QColor(t.accent_text if on_accent else t.caption))
        count_area = QRectF(box.right() - 8 - count_width, box.top(), count_width, box.height())
        painter.drawText(count_area, int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), count)
        unreadable = index.data(Qt.ItemDataRole.UserRole + 1) == "unreadable"
        painter.setFont(option.font)
        painter.setPen(QColor(t.accent_text if on_accent else (t.disabled if unreadable else t.text)))
        area = QRectF(box.left() + 8, box.top(), count_area.left() - box.left() - 16, box.height())
        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        elided = painter.fontMetrics().elidedText(text, Qt.TextElideMode.ElideMiddle, int(max(0.0, area.width())))
        painter.drawText(area, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), elided)
        painter.restore()


class ElidedLabel(SafeLabel):
    """A one-line plain-text label that shortens its text to the width it gets (the corpus's name in the header), so
    a long value never widens the pane. :meth:`full_text` is the whole text (also its tooltip)."""

    def __init__(self, text: str = "", *, name: str, parent: QWidget | None = None,
                 mode: Qt.TextElideMode = Qt.TextElideMode.ElideMiddle) -> None:
        super().__init__("", name=name, parent=parent, selectable=False)
        self._full = ""
        self._mode = mode
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.set_plain(text)

    def set_plain(self, text: str) -> None:
        self._full = text
        set_tooltip(self, text)
        self.updateGeometry()
        self._fit()

    def full_text(self) -> str:
        return self._full

    def sizeHint(self) -> QSize:
        return QSize(self.fontMetrics().horizontalAdvance(self._full) + 4, super().sizeHint().height())

    def minimumSizeHint(self) -> QSize:
        return QSize(min(48, self.sizeHint().width()), super().minimumSizeHint().height())

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._fit()

    def _fit(self) -> None:
        super().set_plain(self.fontMetrics().elidedText(self._full, self._mode, max(0, self.width() - 2)))


class CorpusDetails(QFrame):
    """Corpus Details (D-1060): the open corpus's manifest facts the corpora table used to show (corpus, state, id,
    version, executions, content digest, folder), in a popover under the button. Read-only, plain text."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent, Qt.WindowType.Popup)
        self.setAccessibleName("Corpus details")
        self.setProperty("apvRole", "card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 14)
        lay.setSpacing(8)
        lay.addWidget(heading("Corpus details", name="Corpus details heading", parent=self))
        self.facts = FactGrid(name="Corpus facts", parent=self)
        lay.addWidget(self.facts)
        self.error = caption("", name="Why the corpus cannot be opened", parent=self)
        self.error.hide()
        lay.addWidget(self.error)

    def show_summary(self, s: CorpusSummary) -> None:
        token = group_of(s)
        values = (T.line(s.name, 120), theme.status_text(token), T.line(s.corpus_id or "—", 120),
                  T.line(s.corpus_version or "—"), f"{s.executions:,}" if s.executions is not None else "—",
                  T.line(s.content_digest or "—", 120), T.line(str(s.path.parent), 300))
        for header, field, tip, value in zip(CORPUS_HEADERS, CORPUS_FIELDS, CORPUS_TIPS, values, strict=True):
            self.facts.set(header, value)
            set_control_tooltip(self.facts.names[header], field_tip(tip, field))
        self.error.set_plain(f"It cannot be opened: {T.line(s.error, 80)}." if s.error else "")
        self.error.setVisible(bool(s.error))
        widest = max(self.fontMetrics().horizontalAdvance(v) for v in values)
        self.setFixedWidth(max(380, min(760, widest + 180)))
        self.adjustSize()


# ----------------------------------------------------------------------------------------------- the page
class ViewerPage(QWidget):
    revalidate_requested = Signal(str)  # a marked corpus (§8.3a): the main window opens the full-recompute form
    verify_requested = Signal(str)  # the notice's Verify… (G.8.6): the main window opens the verify form (verify_values)
    render_requested = Signal(str, str)  # (corpus, ex): the main window opens the render form (D-706, D-654)
    status_message = Signal(str)
    corpus_opened = Signal(str, float)  # name, seconds (for the window title and measurements)
    open_folder_requested = Signal()  # the corpora list's Open Folder…: the main window's Open Corpus… dialog
    search_changed = Signal(str)  # the id search changed here (a chip removed): the toolbar's search field follows
    panes_changed = Signal()  # a side pane opened or collapsed: the View menu's commands follow

    def __init__(self, roots: list[Path], cache_dir: Path | None, content_limit: int = T.CONTENT_CHARS_DEFAULT,
                 parent: QWidget | None = None, *, store: QSettings | None = None) -> None:
        super().__init__(parent)
        self.setAccessibleName("Viewer")
        self.roots = roots
        self.store = store  # the GUI's QSettings: the panes' widths and states (None: this process only)
        self.content_limit = content_limit
        self.pool = QThreadPool.globalInstance()
        self.reader: CorpusReader | None = None
        self.summary: CorpusSummary | None = None
        self.table: ExecutionTable | None = None
        self.corpus_rows: list[CorpusSummary] = []
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
        #: the filters applied: a column key of FACETS (or ISSUE) -> its one chosen value, and the id search
        self.filters: dict[str, str] = {}
        self.search_text = ""
        self.chips: dict[str, QPushButton] = {}
        self._available: dict[str, bool] = {}
        self._last_opened: str | None = None  # the side pane the user chose over the other: the width collapses it last
        self.details: CorpusDetails | None = None  # the open Corpus Details popover
        self._fitting = False
        #: (corpus path) -> "level, date, job" of the last successful GUI verify job, or None (set by the main window)
        self.verified_lookup: Callable[[Path], str | None] = lambda _p: None
        self._build(cache_dir)
        QGuiApplication.styleHints().colorSchemeChanged.connect(lambda _scheme: self._restyle())
        self._restyle()

    # ------------------------------------------------------------------------------------------ building
    def _build(self, cache_dir: Path | None) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        # D-840: the document tab bar; tab 0 is the corpus browser
        self.doc_tabs = QTabWidget(self)
        self.doc_tabs.setAccessibleName("Viewer tabs")
        self.doc_tabs.setDocumentMode(True)
        self.doc_tabs.tabBar().setDrawBase(False)  # no platform band behind the tabs, as the window's tabs (D-1060)
        self.doc_tabs.setTabsClosable(True)
        self.doc_tabs.setMovable(True)
        self.doc_tabs.setUsesScrollButtons(True)
        self.doc_tabs.setElideMode(Qt.TextElideMode.ElideNone)  # titles are elided in the middle by elide_middle
        self._build_actions()
        left = QWidget(self.doc_tabs)
        ll = QHBoxLayout(left)
        ll.setContentsMargins(0, 0, 6, 0)
        self.corpora_toggle = self._pane_button(CORPORA, left)
        ll.addWidget(self.corpora_toggle)
        self.doc_tabs.setCornerWidget(left, Qt.Corner.TopLeftCorner)
        corner = QWidget(self.doc_tabs)
        cl = QHBoxLayout(corner)
        cl.setContentsMargins(0, 0, 0, 0)
        self.tab_count = SafeLabel("", name="Open execution tabs", parent=corner, selectable=False)
        set_control_tooltip(self.tab_count, f"Execution tabs open. At most {MAX_TABS}: opening another closes the least "
                                            "recently viewed one.")
        cl.addWidget(self.tab_count)
        self.reload_btn = QPushButton("Reload", corner)
        self.reload_btn.setAccessibleName("Reload corpora list")
        set_control_tooltip(self.reload_btn, "Look for corpora again under the corpus roots in Settings (⌘R)")
        self.reload_btn.clicked.connect(self.refresh)
        cl.addWidget(self.reload_btn)
        self.inspector_toggle = self._pane_button(INSPECTOR, corner)
        cl.addWidget(self.inspector_toggle)
        self.doc_tabs.setCornerWidget(corner, Qt.Corner.TopRightCorner)
        self.browser = QWidget(self.doc_tabs)
        self.browser.setAccessibleName("Corpora browser")
        brl = QVBoxLayout(self.browser)
        brl.setContentsMargins(0, 4, 0, 0)
        # D-1060: three panes divided by 1 px lines (a wider grab area); a side pane never collapses by dragging
        self.pane_split = QSplitter(Qt.Orientation.Horizontal, self.browser)
        self.pane_split.setObjectName("viewer-panes")
        self.pane_split.setAccessibleName("Viewer panes")
        self.pane_split.setHandleWidth(1)
        self.pane_split.setChildrenCollapsible(False)
        self.corpora_pane = SidePane(self._build_corpora(), side="left", name="Corpora pane",
                                     strip_name="Show the corpora list", widths=CORPORA_WIDTH, parent=self.pane_split)
        self.middle = self._build_middle(self.pane_split)  # created in the panes' order: Tab moves left to right
        self.preview = ExecutionPane(cache_dir, self.cache, compact=True, content_limit=self.content_limit,
                                     store=self.store)
        self.preview.render_requested.connect(self.render_requested)
        self.preview.open_requested.connect(self.open_current_in_tab)
        self.preview.state_changed.connect(self._update_strips)
        holder = QWidget()
        hl = QVBoxLayout(holder)
        hl.setContentsMargins(12, 12, 12, 12)
        hl.addWidget(self.preview)
        self.inspector_pane = SidePane(holder, side="right", name="Inspector pane", strip_name="Show the inspector",
                                       widths=INSPECTOR_WIDTH, parent=self.pane_split)
        for pane in (self.corpora_pane, self.middle, self.inspector_pane):
            self.pane_split.addWidget(pane)
        self.pane_split.setStretchFactor(0, 0)
        self.pane_split.setStretchFactor(1, 1)
        self.pane_split.setStretchFactor(2, 0)
        # the window may be narrower than three open panes: the panes collapse to fit (_fit_panes) instead
        self.pane_split.setMinimumWidth(2 * STRIP + MIDDLE_MIN + 2)
        self.pane_split.installEventFilter(self)
        self.pane_split.splitterMoved.connect(self._remember_widths)
        for which, pane in ((CORPORA, self.corpora_pane), (INSPECTOR, self.inspector_pane)):
            set_control_tooltip(pane.strip, "Show the corpora list again (⌥⌘1)" if which == CORPORA
                                else "Show the inspector again (⌥⌘I)")
            pane.strip.clicked.connect(partial(self.set_pane_open, which, True))
            pane.toggled.connect(lambda _on: self._panes_toggled())
        brl.addWidget(self.pane_split)
        self.doc_tabs.addTab(self.browser, "Corpora")
        bar = self.doc_tabs.tabBar()
        for side in (QTabBar.ButtonPosition.LeftSide, QTabBar.ButtonPosition.RightSide):
            bar.setTabButton(0, side, None)  # D-840: the corpus browser cannot be closed
        bar.setAccessibleTabName(0, "Corpora browser")
        set_tab_tooltip(self.doc_tabs, 0, "The corpora list, the executions table and the inspector (not closable)")
        bar.tabMoved.connect(self._tab_moved)
        bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        bar.customContextMenuRequested.connect(self._tab_menu)
        bar.installEventFilter(self)
        self.doc_tabs.tabCloseRequested.connect(self.close_tab)
        self.doc_tabs.currentChanged.connect(self._tab_changed)
        lay.addWidget(self.doc_tabs)
        self._restore_panes()
        self._refresh_tabs()
        self._update_strips()

    def _build_actions(self) -> None:
        """View › Show/Hide Corpora and Inspector: the main window adds them to its View menu with their shortcuts."""
        self.pane_actions: dict[str, QAction] = {}
        for key, which in (("toggleCorpora", CORPORA), ("toggleInspector", INSPECTOR)):
            act = QAction("", self)
            act.triggered.connect(partial(self.toggle_pane, which))
            self.pane_actions[key] = act

    def _pane_button(self, which: str, parent: QWidget) -> QToolButton:
        button = QToolButton(parent)
        button.setCheckable(True)
        button.setChecked(True)
        button.setAutoRaise(True)
        button.setIconSize(QSize(16, 16))
        button.setAccessibleName("Show or hide the corpora list" if which == CORPORA else "Show or hide the inspector")
        set_control_tooltip(button, "Shows or hides the corpora list at the left (⌥⌘1)" if which == CORPORA
                            else "Shows or hides the inspector of the selected execution at the right (⌥⌘I)")
        button.clicked.connect(lambda checked: self.set_pane_open(which, checked))
        return button

    def _build_corpora(self) -> QWidget:
        """The left pane: CORPORA with Open Folder…, the source list grouped by state, the filter box."""
        box = QWidget()
        box.setAccessibleName("Corpora")
        bl = QVBoxLayout(box)
        bl.setContentsMargins(8, 10, 8, 8)
        bl.setSpacing(6)
        top = QHBoxLayout()
        top.setContentsMargins(6, 0, 2, 0)
        top.addWidget(heading("Corpora", name="Corpora heading", parent=box))
        top.addStretch(1)
        self.open_folder_btn = link_button("Open Folder…", name="Open a corpus folder", parent=box)
        set_control_tooltip(self.open_folder_btn, "Opens a corpus folder that is not under the corpus roots (as File › "
                                                  "Open Corpus…, ⌘O). The roots the list shows are set in Settings › "
                                                  "General.")
        self.open_folder_btn.clicked.connect(self.open_folder_requested)
        top.addWidget(self.open_folder_btn)
        bl.addLayout(top)
        self.corpora_list = QListWidget(box)
        self.corpora_list.setAccessibleName("Corpora list")
        self.corpora_list.setObjectName("viewer-corpora")
        self.corpora_list.setFrameShape(QFrame.Shape.NoFrame)
        self.corpora_list.setItemDelegate(CorporaDelegate(self.corpora_list))
        self.corpora_list.setMouseTracking(True)
        self.corpora_list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.corpora_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.corpora_list.setAccessibleDescription("Choosing a corpus opens it, read-only. Arrow keys move through "
                                                   "the list.")
        self._open_timer = QTimer(self)  # arrowing through the list opens the corpus it rests on, not each one passed
        self._open_timer.setSingleShot(True)
        self._open_timer.setInterval(180)
        self._open_timer.timeout.connect(self._open_current_corpus)
        self.corpora_list.currentItemChanged.connect(lambda *_: self._open_timer.start())
        self.corpora_list.itemActivated.connect(lambda _item: self._open_current_corpus())
        bl.addWidget(self.corpora_list, 1)
        self.corpora_empty = caption("No corpora under the corpus roots (Settings › General). Open Folder… opens one "
                                     "from elsewhere.", name="No corpora found", parent=box)
        self.corpora_empty.hide()
        bl.addWidget(self.corpora_empty)
        self.corpora_filter = QLineEdit(box)
        self.corpora_filter.setAccessibleName("Filter corpora")
        self.corpora_filter.setPlaceholderText("Filter corpora")
        self.corpora_filter.setClearButtonEnabled(True)
        set_control_tooltip(self.corpora_filter, "Show only the corpora whose name contains this text")
        self.corpora_filter.textChanged.connect(lambda _t: self._fill_corpora())
        bl.addWidget(self.corpora_filter)
        return box

    def _build_middle(self, parent: QWidget) -> QFrame:
        """The middle pane: the corpus header, the filter chips, the executions table and the terminal command."""
        mid = QFrame(parent)
        mid.setObjectName("viewer-middle")
        mid.setAccessibleName("Executions pane")
        mid.setMinimumWidth(MIDDLE_MIN)
        ml = QVBoxLayout(mid)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(0)
        head = QWidget(mid)
        head.setAccessibleName("Corpus header")
        hl = QVBoxLayout(head)
        hl.setContentsMargins(16, 12, 16, 8)
        hl.setSpacing(6)
        # the name with its state and verification; under it the version and executions with Corpus Details (two rows,
        # so the header fits the narrowest middle pane)
        row = QHBoxLayout()
        row.setSpacing(theme.SPACE)
        self.corpus_title = ElidedLabel("No corpus open", name="Corpus name", parent=head)
        font = theme.scaled_font("title")
        font.setPointSizeF(font.pointSizeF() * 0.9)
        self.corpus_title.setFont(font)
        row.addWidget(self.corpus_title)
        self.state_badge = StatusBadge(name="Corpus state", parent=head)
        set_tooltip(self.state_badge, "Sealed (finished; never written again), Working (not sealed yet), Being written "
                                      "(a CLI job holds its lock now) or Unreadable")
        self.banner_badge = StatusBadge(name="Corpus verification", parent=head)
        set_tooltip(self.banner_badge, "Verified: a verify job of this GUI passed on this corpus (G.8.6). Not verified: "
                                       "none has. Unvalidated: the PROV conformance check was skipped (§8.3a).")
        for badge in (self.state_badge, self.banner_badge):
            row.addWidget(badge, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addStretch(1)
        hl.addLayout(row)
        row = QHBoxLayout()
        row.setSpacing(theme.SPACE)
        self.corpus_facts = ElidedLabel("Choose a corpus in the list at the left.", name="Corpus version",
                                        parent=head, mode=Qt.TextElideMode.ElideRight)
        # the executions the filters show, of all in the corpus ("2 of 3,232 executions")
        self.count_label = ElidedLabel("", name="Executions count", parent=head, mode=Qt.TextElideMode.ElideRight)
        for label in (self.corpus_facts, self.count_label):
            label.setProperty("apvRole", "caption")
            label.setFont(theme.scaled_font("caption"))
            row.addWidget(label, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addStretch(1)
        self.details_btn = QPushButton("Corpus Details", head)
        self.details_btn.setAccessibleName("Show the corpus details")
        set_control_tooltip(self.details_btn, "The open corpus's corpus id, version, executions, content digest, folder "
                                              "and state (from its corpus.json)")
        self.details_btn.setEnabled(False)
        self.details_btn.clicked.connect(self.show_details)
        row.addWidget(self.details_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        hl.addLayout(row)
        self._build_banner(head, hl)
        self._build_filter_bar(head, hl)
        self.derive_hint = caption("This corpus has working rows only: derive it (agentprov derive) for the suite, "
                                   "task, attack, defence and outcome columns.", name="Derive hint", parent=head)
        self.derive_hint.hide()
        hl.addWidget(self.derive_hint)
        # D-706: the rule behind the attack-succeeded mark, as a grey help line (also the column header's and each
        # marked cell's tooltip)
        self.legend = caption(f"{theme.ATTACK_GLYPH} {ATTACK_RULE}", name="Attack succeeded legend", parent=head)
        self.legend.hide()
        hl.addWidget(self.legend)
        ml.addWidget(head)
        self.model = ExecutionsModel()
        self.exec_view = QTableView(mid)
        self.exec_view.setAccessibleName("Executions table")
        self.exec_view.setModel(self.model)
        self.exec_view.setSortingEnabled(True)
        self.exec_view.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.exec_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.exec_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        tidy_view(self.exec_view)
        self.exec_view.setFrameShape(QFrame.Shape.NoFrame)
        self.exec_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.exec_view.horizontalHeader().setStretchLastSection(True)
        self.exec_view.setWordWrap(False)
        self.exec_view.setTabKeyNavigation(False)  # Tab moves on to the next control (the arrows move in the table)
        self.exec_view.selectionModel().currentRowChanged.connect(self._row_changed)
        self.exec_view.doubleClicked.connect(self._open_index)
        for return_key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):  # D-845: Return opens the execution in a new tab
            sc = QShortcut(QKeySequence(return_key), self.exec_view, context=Qt.ShortcutContext.WidgetShortcut)
            sc.activated.connect(self.open_current_in_tab)
        self.exec_view.setAccessibleDescription("Return or a double-click opens the execution in a new tab")
        self.exec_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.exec_view.customContextMenuRequested.connect(self._exec_menu)
        ml.addWidget(self.exec_view, 1)
        self._build_terminal(mid, ml)
        return mid

    def _build_banner(self, parent: QWidget, lay: QVBoxLayout) -> None:
        """The notice under the corpus's name: what to do before relying on it (not verified, being written, PROV
        conformance skipped) and the action that does it."""
        self.banner = QWidget(parent)
        self.banner.setAccessibleName("Corpus notice")
        bl = QHBoxLayout(self.banner)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(theme.SPACE)
        self.banner_text = caption("", name="Corpus verification banner", parent=self.banner)
        bl.addWidget(self.banner_text, 1)
        self.verify_btn = QPushButton("Verify…", self.banner)
        self.verify_btn.setAccessibleName("Verify this corpus")
        set_control_tooltip(self.verify_btn, "Opens the verify form for this corpus (agentprov verify --corpus … --level "
                                             "chain), run as a job. Verify only reads the corpus.")
        self.verify_btn.clicked.connect(self._request_verify)
        self.verify_btn.hide()
        bl.addWidget(self.verify_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        self.revalidate_btn = QPushButton("Revalidate…", self.banner)
        self.revalidate_btn.setAccessibleName("Revalidate this corpus with a full recompute into a new corpus")
        set_control_tooltip(self.revalidate_btn, "Opens the recompute form: a full recompute (sem, prov, validation) into a "
                                                 "new corpus runs the PROV conformance check this corpus skipped. This "
                                                 "corpus is not changed.")
        self.revalidate_btn.clicked.connect(self._request_revalidate)
        self.revalidate_btn.hide()
        bl.addWidget(self.revalidate_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        self.banner.hide()
        lay.addWidget(self.banner)

    def _build_filter_bar(self, parent: QWidget, lay: QVBoxLayout) -> None:
        """The filters as chips ("Attack: important_instructions ×"), + Add filter and Clear all."""
        row = QHBoxLayout()
        row.setSpacing(theme.SPACE)
        self.filter_bar = QWidget(parent)
        self.filter_bar.setAccessibleName("Filters")
        self.filter_flow = FlowLayout(self.filter_bar, spacing=6)
        self.add_filter_btn = QPushButton("+ Add filter", self.filter_bar)
        self.add_filter_btn.setProperty("apvRole", "chip")
        self.add_filter_btn.setAccessibleName("Add filter")
        set_control_tooltip(self.add_filter_btn, "Show only the executions with a chosen value of a column: status, "
                                                 "completeness, source, record type, issue code, and on a derived "
                                                 "corpus suite, attack, injection task, defence, model, utility and "
                                                 "attack succeeded. Each value says how many executions it would show.")
        self.filter_menu = QMenu(self.add_filter_btn)
        self.filter_menu.setAccessibleName("Add filter menu")
        self.filter_menu.aboutToShow.connect(self._fill_filter_menu)
        self.add_filter_btn.setMenu(self.filter_menu)
        self.add_filter_btn.setStyleSheet("QPushButton::menu-indicator { image: none; width: 0px; }")  # a chip
        self.add_filter_btn.setEnabled(False)
        self.filter_flow.addWidget(self.add_filter_btn)
        self.clear_filters_btn = link_button("Clear all", name="Clear all filters", parent=self.filter_bar)
        set_control_tooltip(self.clear_filters_btn, "Remove every filter and the id search: show all the executions")
        self.clear_filters_btn.clicked.connect(self._clear_filters)
        self.clear_filters_btn.hide()
        self.filter_flow.addWidget(self.clear_filters_btn)
        row.addWidget(self.filter_bar, 1)
        lay.addLayout(row)

    def _build_terminal(self, parent: QWidget, lay: QVBoxLayout) -> None:
        """The terminal command (D-700) for the rows shown, in a collapsed disclosure at the bottom; while it is
        collapsed, the command's start is shown beside it."""
        foot = QFrame(parent)
        foot.setObjectName("viewer-foot")
        foot.setAccessibleName("Terminal command for this view")
        fl = QHBoxLayout(foot)
        fl.setContentsMargins(16, 6, 16, 8)
        fl.setSpacing(theme.SPACE)
        self.terminal = Disclosure("Terminal command for this view", screen="viewer", key="terminal", store=self.store,
                                   name="Show the terminal command for this view", parent=foot)
        set_control_tooltip(self.terminal.button, "Shows the agentprov stats command that selects the executions shown "
                                                  "(and agentprov verify while the corpus is not verified), to run in a "
                                                  "terminal")
        # the statistics of the rows shown (and verify while the corpus is not verified), where the CLI line was
        self.commands = CommandCard(name="Viewer terminal command", title="Terminal command", parent=self.terminal)
        self.commands.copy_button.setAccessibleName("Copy the CLI selection")
        set_control_tooltip(self.commands.copy_button, "Copies the commands shown below, one line per command, so they "
                                                       "can be run in a terminal: the agentprov stats command that "
                                                       "selects the rows shown (D-700)")
        self.terminal.add(self.commands)
        self.cli_notes = caption("", name="What the terminal command cannot express", parent=self.terminal)
        self.cli_notes.hide()
        self.terminal.add(self.cli_notes)
        self.terminal.body.setSpacing(6)
        fl.addWidget(self.terminal, 0, Qt.AlignmentFlag.AlignTop)
        self.terminal_preview = ElidedLabel("", name="Terminal command preview", parent=foot,
                                            mode=Qt.TextElideMode.ElideRight)
        self.terminal_preview.setProperty("apvRole", "caption")
        self.terminal_preview.setFont(theme.scaled_font("mono"))
        self.terminal_preview.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        fl.addWidget(self.terminal_preview, 1, Qt.AlignmentFlag.AlignTop)
        self.terminal.toggled.connect(lambda _on: self._terminal_toggled())
        self._terminal_toggled()
        lay.addWidget(foot)

    def _terminal_toggled(self) -> None:
        opened = self.terminal.is_open()
        self.terminal_preview.setVisible(not opened)
        foot = self.terminal.parentWidget()
        foot_layout = foot.layout() if foot is not None else None
        if isinstance(foot_layout, QHBoxLayout):
            foot_layout.setStretchFactor(self.terminal, 1 if opened else 0)

    def _restyle(self) -> None:
        """The panes' colours from the theme's tokens: the side panes on the summary colour, the middle on the card
        colour, 1 px dividers in the hairline colour (HIG), and the pane toggles' glyphs. Called at start and whenever
        the appearance changes."""
        t = theme.tokens()
        self.pane_split.setStyleSheet(
            f"QSplitter#viewer-panes::handle {{ background: {t.card_border}; }}"
            f" QFrame#viewer-left, QFrame#viewer-right {{ background: {t.summary}; border: none; }}"
            f" QFrame#viewer-middle {{ background: {t.card}; border: none; }}"
            f" QFrame#viewer-foot {{ background: {t.summary}; border: none; border-top: 1px solid {t.hairline}; }}"
            f" QListWidget#viewer-corpora {{ background: transparent; border: none; outline: 0; }}")
        self._update_toggles()

    # ------------------------------------------------------------------------------------------ the panes
    def pane(self, which: str) -> SidePane:
        return self.corpora_pane if which == CORPORA else self.inspector_pane

    def _setting(self, which: str, what: str) -> str:
        return f"viewer/panes/{which}/{what}"

    def _stored_width(self, which: str) -> int | None:
        if self.store is None:
            return None
        value = self.store.value(self._setting(which, "width"))
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def _restore_panes(self) -> None:
        """The side panes as the user left them: open or collapsed, and their widths (QSettings)."""
        for which in (CORPORA, INSPECTOR):
            opened = True
            if self.store is not None:
                value = self.store.value(self._setting(which, "open"), "true")
                opened = not (value is False or value == "false")
            self.pane(which).set_open(opened)
        self._apply_sizes()

    def _apply_sizes(self) -> None:
        sizes = self.pane_split.sizes()
        total = sum(sizes) if sum(sizes) > 0 else 1400
        left = self.corpora_pane.width_wanted(self._stored_width(CORPORA))
        right = self.inspector_pane.width_wanted(self._stored_width(INSPECTOR))
        self.pane_split.setSizes([left, max(MIDDLE_MIN, total - left - right), right])

    def _remember_widths(self, *_args: object) -> None:
        if self.store is None:
            return
        sizes = self.pane_split.sizes()
        for which, size in ((CORPORA, sizes[0]), (INSPECTOR, sizes[2])):
            if self.pane(which).is_open() and size > STRIP:
                self.store.setValue(self._setting(which, "width"), size)

    def pane_open(self, which: str) -> bool:
        return self.pane(which).is_open()

    def toggle_pane(self, which: str) -> None:
        """View › Show/Hide Corpora or Inspector, and the toolbar buttons: on the Corpora tab."""
        self.set_pane_open(which, not self.pane(which).is_open())

    def set_pane_open(self, which: str, opened: bool) -> None:
        """Open or collapse a side pane as the user asks (remembered). Opening one the window cannot hold beside the
        other collapses the other (it opens again when there is room), so the one asked for is always reachable."""
        self.doc_tabs.setCurrentIndex(0)
        pane = self.pane(which)
        if opened == pane.is_open() and not pane.auto:
            self._update_toggles()
            return
        pane.set_open(opened)
        if self.store is not None:
            self.store.setValue(self._setting(which, "open"), "true" if opened else "false")
        if opened:
            other = self.pane(INSPECTOR if which == CORPORA else CORPORA)
            if other.is_open() and self.pane_split.width() > 0 and self._required(True, True) > self.pane_split.width():
                other.set_open(False, auto=True)
                self._last_opened = which  # chosen over the other at this width: the width collapses it last
        self._apply_sizes()
        self._panes_toggled()
        if opened:
            pane.content.setFocus(Qt.FocusReason.OtherFocusReason)

    def _required(self, corpora: bool, inspector: bool) -> int:
        """The width three panes need with these side panes open (each at its minimum), dividers included."""
        return (CORPORA_WIDTH[0] if corpora else STRIP) + MIDDLE_MIN + (INSPECTOR_WIDTH[0] if inspector else STRIP) + 2

    def _fit_panes(self) -> None:
        """Mail-style: a narrow window collapses the inspector first, then the corpora list (the pane the user opened
        last goes last); each comes back by itself once the window is wide enough again."""
        if self._fitting:
            return
        width = self.pane_split.width()
        if width <= 0:
            return
        self._fitting = True
        try:
            order = [self.inspector_pane, self.corpora_pane]
            if self._last_opened == INSPECTOR:
                order.reverse()
            changed = False
            for pane in order:
                if pane.is_open() and self._required(self.corpora_pane.is_open(), self.inspector_pane.is_open()) > width:
                    pane.set_open(False, auto=True)
                    changed = True
            for pane in reversed(order):
                if pane.auto and not pane.is_open():
                    corpora = self.corpora_pane.is_open() or pane is self.corpora_pane
                    inspector = self.inspector_pane.is_open() or pane is self.inspector_pane
                    if self._required(corpora, inspector) + REOPEN_MARGIN <= width:
                        pane.set_open(True)
                        changed = True
            if self._required(True, True) + REOPEN_MARGIN <= width:
                self._last_opened = None  # room for both again: the inspector collapses first next time
            if changed:
                self._apply_sizes()
                self._panes_toggled()
        finally:
            self._fitting = False

    def _panes_toggled(self) -> None:
        for i, pane in ((0, self.corpora_pane), (2, self.inspector_pane)):
            handle = self.pane_split.handle(i if i else 1)
            if handle is not None:
                handle.setEnabled(pane.is_open())  # a strip is not dragged wider; its strip opens it
        self._update_toggles()
        self._update_strips()
        self.panes_changed.emit()

    def _update_toggles(self) -> None:
        colour = QColor(theme.tokens().secondary)
        for which, button in ((CORPORA, self.corpora_toggle), (INSPECTOR, self.inspector_toggle)):
            shown = self.pane(which).is_open()
            button.setChecked(shown)
            button.setIcon(pane_icon("left" if which == CORPORA else "right", colour, shown=shown))
        corpora, inspector = self.pane_actions["toggleCorpora"], self.pane_actions["toggleInspector"]
        corpora.setText("Hide Corpora" if self.corpora_pane.is_open() else "Show Corpora")
        inspector.setText("Hide Inspector" if self.inspector_pane.is_open() else "Show Inspector")

    def _update_strips(self) -> None:
        """What a collapsed pane's strip says it holds: the open corpus, the selected execution (S13: its id only when
        it is well formed; display only)."""
        name = T.line(self.summary.name, 80) if self.summary is not None else ""
        self.corpora_pane.strip.set_label("CORPORA" + (f" · {name}" if name else ""))
        ex = self.preview.ex
        short = f"{ex[:9]}…" if ex is not None and EXECUTION_ID.fullmatch(ex) is not None else ""
        self.inspector_pane.strip.set_label("EXECUTION" + (f" · {short}" if short else ""))

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self.pane_split and event.type() == QEvent.Type.Resize:
            self._fit_panes()
        # D-845: a middle-click closes an execution tab
        if watched is self.doc_tabs.tabBar() and event.type() == QEvent.Type.MouseButtonRelease and \
                isinstance(event, QMouseEvent) and event.button() == Qt.MouseButton.MiddleButton:
            index = self.doc_tabs.tabBar().tabAt(event.position().toPoint())
            if self.close_tab(index):
                return True
        return super().eventFilter(watched, event)

    # ------------------------------------------------------------------------------------------ corpora
    def refresh(self) -> None:
        self.corpus_rows = discover(self.roots)
        self._fill_corpora()
        self.status_message.emit(f"{len(self.corpus_rows)} corpora found")

    def _fill_corpora(self) -> None:
        """The source list: a heading per state with its count, then each corpus's name and execution count (by name);
        only the corpora whose name contains the filter text. The open corpus stays selected (not opened again)."""
        needle = self.corpora_filter.text().strip().lower()
        shown = [s for s in self.corpus_rows if needle in s.name.lower()]
        keys = [k for k, _h in GROUPS]
        extra = sorted({group_of(s) for s in shown} - set(keys))
        headings = dict(GROUPS) | {k: T.line(k, 40).replace("_", " ").capitalize() for k in extra}
        lst = self.corpora_list
        lst.blockSignals(True)
        lst.clear()
        current: QListWidgetItem | None = None
        for key in (*keys, *extra):
            members = sorted((s for s in shown if group_of(s) == key), key=lambda s: (s.name.lower(), str(s.path)))
            if not members:
                continue
            head = QListWidgetItem(f"{headings[key].upper()} · {len(members)}")
            head.setFlags(Qt.ItemFlag.NoItemFlags)
            lst.addItem(head)
            for s in members:
                item = QListWidgetItem(T.line(s.name, 120))
                item.setData(Qt.ItemDataRole.UserRole, self.corpus_rows.index(s))
                item.setData(Qt.ItemDataRole.UserRole + 1, s.state)
                count = f"{s.executions:,}" if s.executions is not None else "—"
                item.setData(CorporaDelegate.COUNT_ROLE, count)
                item.setData(Qt.ItemDataRole.AccessibleTextRole,
                             f"{T.line(s.name, 120)}, {theme.status_text(group_of(s))}, {count} executions")
                # the name first: the list elides a long one in the middle
                set_list_item_tooltip(item, f"{s.name} — {s.path}" + (f" ({s.error})" if s.error else ""), wrap=True)
                lst.addItem(item)
                if self.summary is not None and s.path == self.summary.path:
                    current = item
        if current is not None:
            lst.setCurrentItem(current)
        else:
            lst.setCurrentRow(-1)
        lst.blockSignals(False)
        self.corpora_empty.setVisible(not self.corpus_rows)

    def _open_current_corpus(self) -> None:
        self._open_timer.stop()
        item = self.corpora_list.currentItem()
        index = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if not isinstance(index, int) or not 0 <= index < len(self.corpus_rows):
            return
        summary = self.corpus_rows[index]
        if self.summary is not None and self.summary.path == summary.path and self.reader is not None:
            return  # already open
        self.open_corpus(summary)

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
        self.filters.clear()
        self._set_search("")
        self._rebuild_chips()
        self.add_filter_btn.setEnabled(False)
        self._show_banner(summary)
        self._select_open_corpus()
        self._update_strips()
        self._update_cli()
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

    def _select_open_corpus(self) -> None:
        lst = self.corpora_list
        lst.blockSignals(True)
        lst.setCurrentRow(-1)
        for i in range(lst.count()):
            index = lst.item(i).data(Qt.ItemDataRole.UserRole)
            if isinstance(index, int) and self.summary is not None and self.corpus_rows[index].path == self.summary.path:
                lst.setCurrentRow(i)
                break
        lst.blockSignals(False)

    def _progress(self, gen: int, rows: int) -> None:
        if gen == self._gen:
            self.count_label.set_plain(f"reading… {rows:,}")

    def _request_revalidate(self) -> None:
        if self.summary is not None:
            self.revalidate_requested.emit(str(self.summary.path))

    def _request_verify(self) -> None:
        if self.summary is not None:
            self.verify_requested.emit(verify_values(self.summary.path)["corpus"])

    def show_details(self) -> CorpusDetails | None:
        """Corpus Details: the open corpus's manifest facts in a popover under the button."""
        if self.summary is None:
            return None
        popup = self.details
        if popup is None:  # AU-NG-4: one popover, refilled on each open (a new one per click was never deleted)
            popup = CorpusDetails(self)
        popup.show_summary(self.summary)
        at = self.details_btn.mapToGlobal(QPoint(self.details_btn.width() - popup.width(), self.details_btn.height() + 4))
        popup.move(at)
        popup.show()
        self.details = popup
        return popup

    def needs_verify(self) -> bool:
        """The open corpus can be read and no verify job of this GUI has passed on it (and no CLI job is writing it)."""
        s = self.summary
        return s is not None and s.root is not None and not s.writing and \
            (s.state != "sealed" or self.verified_lookup(s.path) is None)

    def _show_banner(self, s: CorpusSummary) -> None:
        """The header for ``s``: its name, state and verification as badges, its version and executions, and what to do:
        being written, not verified (with Verify…) or PROV conformance skipped (with Revalidate…)."""
        self.corpus_title.set_plain(T.line(s.name, 120))
        self.corpus_facts.set_plain(f"Version {T.line(s.corpus_version, 40)} ·" if s.corpus_version else "")
        self.corpus_facts.setVisible(bool(s.corpus_version))
        self.count_label.set_plain(f"{s.executions:,} executions" if s.executions is not None else "")
        self.details_btn.setEnabled(True)
        if s.writing:
            self.state_badge.set_status("Being written", "warn")
        else:
            self.state_badge.set_status({"sealed": "Sealed", "working": "Working"}.get(s.state, "Unreadable"),
                                        {"sealed": "ok", "working": "info"}.get(s.state, "bad"))
        kind, word = "warn", "Not verified"
        if s.writing:
            text = f"{T.line(s.name, 80)} is a working tree being written by a CLI job. It is read without a lock; " \
                   "documents may change while you look."
            word = "Read without a lock"
        elif s.state != "sealed":
            text = f"{T.line(s.name, 80)} is not sealed and not verified. Run Verify first (G.8.6)."
        else:
            verified = self.verified_lookup(s.path)
            if verified is not None:
                text = f"{T.line(s.name, 80)} is sealed and verified ({T.line(verified, 160)})."
                kind, word = "ok", "Verified"
            else:
                text = f"{T.line(s.name, 80)} is sealed but has not been verified by this GUI. Run Verify first (G.8.6)."
        self.verify_btn.setVisible(self.needs_verify())
        self.revalidate_btn.setVisible(s.prov_conformance == "skipped")
        if s.prov_conformance == "skipped":
            text += " The PROV conformance check (tier 4) was skipped: this corpus is unvalidated until a full " \
                    "recompute validates it into a new corpus (Revalidate); do not report its results (§8.3a)."
            kind, word = "bad", "Unvalidated"
        if s.root is None:
            text = f"{T.line(s.name, 80)} cannot be opened ({T.line(s.error, 60)})."
            kind, word = "bad", "Cannot be opened"
            self.verify_btn.hide()
        self.banner_badge.set_status(word, kind)
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
        # which filters apply (the old pickers' rule): the task and outcome ones only for a column shown with values
        self._available = {key: bool(self.table.vocabulary(key)) and (key not in TASK_PICKERS or key in shown)
                           for key in FACETS}
        self._available[ISSUE] = bool(self.table.issue_codes())
        self.add_filter_btn.setEnabled(True)
        self.derive_hint.setVisible(len(self.table) > 0 and self.table.full_rows == 0)
        self.legend.setVisible(ATTACK_KEY in shown)
        self.filters.clear()
        self._set_search("")
        self._rebuild_chips()
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

    # ------------------------------------------------------------------------------------------ filters
    def filter_offered(self, key: str) -> bool | None:
        """Whether + Add filter offers ``key``: True (it has values), False (shown, no values: a base column of a
        corpus without them), None (not shown: a task or outcome column the corpus does not have)."""
        if self.table is None:
            return None
        if self._available.get(key):
            return True
        return None if key in TASK_PICKERS else False

    def filter_values(self, key: str) -> list[tuple[str, str, int]]:
        """``(value, label, count)`` of each value + Add filter offers for ``key``, the old picker's values in its
        order; ``count`` is how many executions choosing it would show, with the other filters kept."""
        if self.table is None:
            return []
        values = self.table.issue_codes() if key == ISSUE else self.table.vocabulary(key)
        rows = self.table.select(self._selection(without=key))
        tally: Counter[str] = Counter()
        if key == ISSUE:
            for r in rows:
                tally.update(set(self.table.issues[r]))
        elif key in self.table.sets:
            sets = self.table.sets[key]
            for r in rows:
                tally.update(set(sets[r]))
        else:
            column = self.table.columns[key]
            tally.update(column[r] for r in rows)
        return [(v, value_label(key, v), tally.get(v, 0)) for v in values]

    def _fill_filter_menu(self) -> None:
        """+ Add filter: a submenu per facet listing its values with their counts (filled when it opens)."""
        menu = self.filter_menu
        menu.clear()
        for key in MENU_ORDER:
            offered = self.filter_offered(key)
            if offered is None:
                continue
            title = PLAIN[key]
            if not offered:
                act = menu.addAction(menu_text(f"{title} (no values)"))
                act.setEnabled(False)
                continue
            sub = menu.addMenu(menu_text(title))
            sub.setAccessibleName(f"Filter by {title.lower()}")
            sub.menuAction().setData(key)
            sub.aboutToShow.connect(partial(self._fill_values_menu, sub, key))
        if menu.isEmpty():
            menu.addAction("Open a corpus first").setEnabled(False)

    def _fill_values_menu(self, sub: QMenu, key: str) -> None:
        sub.clear()
        current = self.filters.get(key)
        if current is not None:
            sub.addAction(f"Remove the {PLAIN[key].lower()} filter", partial(self.set_filter, key, None))
            sub.addSeparator()
        sub.setToolTipsVisible(True)  # a value cut at 80 characters shows whole in its tooltip
        for value, label, count in self.filter_values(key):
            act = sub.addAction(menu_text(f"{label}  ({count:,})"))
            if value_full(key, value) != label:
                set_action_tooltip(act, value_full(key, value))
            act.setData(value)
            act.setCheckable(True)
            act.setChecked(value == current)
            act.triggered.connect(partial(self.set_filter, key, value))

    def set_filter(self, key: str, value: str | None, *_args: object) -> None:
        """Apply one value of a facet (replacing its earlier one), or remove the facet's filter (``None``): the same
        selection the old pickers made."""
        if key not in FACETS and key != ISSUE:
            return
        if value is None:
            self.filters.pop(key, None)
        else:
            self.filters[key] = value
        self._rebuild_chips()
        self._filter_changed()

    def set_search(self, text: str) -> None:
        """The id search (the window's toolbar search field): the executions whose id contains ``text``."""
        self._set_search(text)
        self._rebuild_chips()
        self._filter_changed()

    def _set_search(self, text: str) -> None:
        text = text[:200]
        if text != self.search_text:
            self.search_text = text
            self.search_changed.emit(text)

    def _rebuild_chips(self) -> None:
        """One chip per filter applied ("Attack: x ×", in the facets' order) and one for the id search."""
        for chip in self.chips.values():
            self.filter_flow.removeWidget(chip)
            chip.hide()  # at once: the deletion waits for the event loop
            chip.deleteLater()
        self.chips = {}
        applied: list[tuple[str, str, str, str]] = []  # key, title, label, the whole value (the tooltip's)
        for key in MENU_ORDER:
            if key in self.filters:
                value = self.filters[key]
                applied.append((key, PLAIN[key], value_label(key, value), value_full(key, value)))
        if self.search_text.strip():
            search = self.search_text.strip()
            applied.append(("search", "Id contains", T.line(search, 80), search))
        for key, title, label, full in applied:
            chip = QPushButton(self.filter_bar)
            shown = chip.fontMetrics().elidedText(f"{title}: {label}", Qt.TextElideMode.ElideMiddle, 200)
            chip.setText(menu_text(f"{shown}  ×"))
            chip.setProperty("apvRole", "chip")
            chip.setCheckable(True)
            chip.setChecked(True)
            chip.setAutoDefault(False)
            chip.setAccessibleName(f"Remove the {title.lower()} filter")
            chip.setAccessibleDescription(f"{title}: {label}")
            set_control_tooltip(chip, f"{title}: {full}. Click to remove this filter.")
            chip.clicked.connect(partial(self._remove_chip, key))
            self.chips[key] = chip
        # the chips first, then + Add filter and Clear all
        for widget in (self.add_filter_btn, self.clear_filters_btn):
            self.filter_flow.removeWidget(widget)
        for chip in self.chips.values():
            self.filter_flow.addWidget(chip)
        self.filter_flow.addWidget(self.add_filter_btn)
        self.filter_flow.addWidget(self.clear_filters_btn)
        self.clear_filters_btn.setVisible(bool(self.chips))
        self.filter_bar.updateGeometry()

    def _remove_chip(self, key: str) -> None:
        if key == "search":
            self.set_search("")
        else:
            self.set_filter(key, None)

    def _selection(self, without: str | None = None) -> TableFilter:
        """The filters applied as the table's selection: the facets in :data:`FACETS` order (as the old pickers listed
        them), the id search and the issue code; ``without`` leaves one facet out (the counts of its values)."""
        pickers = tuple((key, frozenset({self.filters[key]})) for key in FACETS
                        if key in self.filters and key != without)
        issue = self.filters.get(ISSUE) if without != ISSUE else None
        return TableFilter(pickers, self.search_text.strip(), issue)

    def _filter_changed(self) -> None:
        if self.table is None:
            return
        self.model.apply(self._selection())
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

    def cli_argv(self) -> tuple[list[str], list[str]]:
        """The ``agentprov stats`` argv (without the program) that selects the rows shown (D-700, D-706), and what it
        cannot express."""
        args, notes = cli_selection(self.model.filter)
        corpus = self.corpus_arg() or "CORPUS"
        return ["stats", "--corpus", corpus, *args], notes

    def cli_command(self) -> tuple[str, list[str]]:
        """The ``agentprov stats`` command that selects the rows shown (D-700, D-706), and what it cannot express."""
        argv, notes = self.cli_argv()
        return shlex.join(["agentprov", *argv]), notes

    def terminal_commands(self) -> tuple[list[tuple[str, list[str]]], list[str]]:
        """D-700: ``(comment, argv)`` of the Corpora tab's selection, as a terminal would run it, and notes on what they
        cannot express: verify (while the corpus is not verified; the verify form's values) and the statistics of the
        rows shown (``cli_argv``). The inspector shows its own inspect and render. Each argument is escaped for display
        where it needs it (S3)."""
        if self.reader is None or self.summary is None:
            return [], []
        commands: list[tuple[str, list[str]]] = []
        if self.needs_verify():
            try:
                spec = build_spec(FORMS["verify"], verify_values(self.summary.path))
                commands.append(("verify the corpus first (Verify…)", list(spec.argv)))
            except FormError:
                pass
        argv, notes = self.cli_argv()
        commands.append(("statistics of the executions shown", argv))
        shown: list[tuple[str, list[str]]] = []
        escaped = False
        for comment, args in commands:
            display, changed = display_argv(args)
            shown.append((comment, display))
            escaped = escaped or changed
        notes = ["Not in the statistics command: " + "; ".join(T.line(n, 200) for n in notes) + "."] if notes else []
        if escaped:
            notes.append("A value holds characters the Viewer shows escaped; the command shows them escaped too.")
        return shown, notes

    def _update_cli(self) -> None:
        commands, notes = self.terminal_commands()
        self.commands.set_commands(commands, note="open a corpus to see its commands")
        self.cli_notes.set_plain(" ".join(notes))
        self.cli_notes.setVisible(bool(notes))
        stats = next((argv for _c, argv in commands if argv[:1] == ["stats"]), None)
        self.terminal_preview.set_plain(" ".join(["agentprov", *stats]) if stats is not None else "")

    def _copy_cli(self) -> None:
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self.cli_command()[0])

    def _update_count(self) -> None:
        total = len(self.table) if self.table is not None else 0
        shown = self.model.rowCount()
        self.count_label.set_plain(f"{shown:,} of {total:,} executions" if shown != total else f"{total:,} executions")

    def _clear_filters(self) -> None:
        self.filters.clear()
        self._set_search("")
        self._rebuild_chips()
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

    # ------------------------------------------------------------------------------------------ inspector (D-842)
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
        menu.addAction("Copy Execution Id", lambda: self._copy_id(pane.ex))
        menu.exec(bar.mapToGlobal(pos))

    def _exec_menu(self, pos: QPoint) -> None:
        index = self.exec_view.indexAt(pos)
        if not index.isValid() or self.table is None:
            return
        ex = self.table.ex(self.model.table_row(index.row()))
        menu = QMenu(self)
        menu.addAction("Open in New Tab", lambda: self.open_row(index.row()))
        menu.addAction("Copy Execution Id", lambda: self._copy_id(ex))
        menu.exec(self.exec_view.viewport().mapToGlobal(pos))

    @classmethod
    def _copy_id(cls, ex: str | None) -> None:
        """S13: only a well-formed execution id reaches the clipboard. The index row's ``ex`` is checked as ASCII only,
        so a hostile corpus could otherwise put LF, ESC or other control characters there."""
        if ex is not None and EXECUTION_ID.fullmatch(ex) is not None:
            cls._copy_text(ex)

    @staticmethod
    def _copy_text(text: str | None) -> None:
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None and text:
            clipboard.setText(text)

    def panes(self) -> list[ExecutionPane]:
        """The inspector and every execution tab (Settings changes apply to all of them)."""
        return [self.preview, *self.exec_tabs.values()]

    def set_show_content_limit(self, limit: int) -> None:
        self.content_limit = max(1, min(limit, T.CONTENT_CHARS_MAX))
        for pane in self.panes():
            pane.set_show_content_limit(self.content_limit)

    def set_exact_palette(self, exact: bool) -> None:
        self.exact_palette = exact
        for pane in self.panes():
            pane.set_exact_palette(exact)
