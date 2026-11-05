"""THE only place that creates text-bearing widgets that could interpret markup (design §11 S1; D-396).

Qt's ``QLabel`` and ``QMessageBox`` default to ``AutoText``, which renders a string that *looks* like HTML as HTML, and
``QLabel`` lets links be activated (research §M8). Tooltips are always rich text. So every label, message box,
tooltip and form row is made here, in plain-text mode, and ``tests/test_lint_safe.py`` bans the dangerous APIs
(``QLabel``, ``QMessageBox``, ``setToolTip``, ``setHtml``, ``QTextBrowser``, ``QFormLayout``, ``ToolTipRole``,
``QProgressDialog``, ``QErrorMessage``, ``QStaticText``, ``fromHtml``, ``set*WhatsThis``, ``WhatsThisRole``, …)
everywhere else in the package.

Every widget made here needs an accessible name (D-446).
"""

from __future__ import annotations

import math
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import ClassVar, Final

from PySide6.QtCore import (
    QAbstractItemModel,
    QEvent,
    QMargins,
    QMarginsF,
    QModelIndex,
    QObject,
    QPoint,
    QRect,
    QRectF,
    QSettings,
    QSize,
    Qt,
    QUrl,
)
from PySide6.QtGui import (
    QAction,
    QColor,
    QFont,
    QGuiApplication,
    QHelpEvent,
    QImage,
    QPainter,
    QPen,
    QPixmap,
    QTextDocument,
)
from PySide6.QtGui import Qt as QtGuiNs
from PySide6.QtWidgets import (
    QApplication,
    QFormLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QTableWidget,
    QTextBrowser,
    QToolTip,
    QTreeWidget,
    QWidget,
)

from agentprov_gui import text as T
from agentprov_gui.ui import theme

__all__ = [
    "TIP_FONT_PX",
    "TIP_MAX_WIDTH",
    "TIP_OFFSET",
    "TIP_PADDING",
    "TIP_RADIUS",
    "TIP_SHADOW",
    "DocView",
    "ReadOnlyText",
    "SafeForm",
    "SafeImage",
    "SafeLabel",
    "TooltipFilter",
    "help_tooltip",
    "install_tooltip_filter",
    "is_tip_label",
    "is_tooltip_role",
    "pointer_scale",
    "safe_message_box",
    "safe_tooltip",
    "screen_rect",
    "set_combo_item_tooltip",
    "set_control_tooltip",
    "set_header_tooltips",
    "set_help_tooltip",
    "set_item_tooltip",
    "set_list_item_tooltip",
    "set_setting_tooltip",
    "set_tab_tooltip",
    "set_tooltip",
    "set_tooltips_shown",
    "set_unavailable_tooltip",
    "tab_text",
    "tip_position",
    "tip_size",
    "tip_style",
    "tooltips_shown",
]


class SafeLabel(QLabel):
    """A plain-text label: ``PlainText`` format, selectable, links never opened. Text is shown as given (the caller
    escapes data with :mod:`agentprov_gui.text`)."""

    def __init__(self, text: str = "", *, name: str, parent: QWidget | None = None, selectable: bool = True) -> None:
        super().__init__(parent)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setOpenExternalLinks(False)
        flags = Qt.TextInteractionFlag.TextSelectableByMouse if selectable else Qt.TextInteractionFlag.NoTextInteraction
        self.setTextInteractionFlags(flags)
        self.setAccessibleName(name)
        super().setText(text)

    def set_plain(self, text: str) -> None:
        super().setText(text)

    def setTextFormat(self, fmt: Qt.TextFormat) -> None:
        super().setTextFormat(Qt.TextFormat.PlainText)  # never anything else, whatever the caller asks


class SafeImage(QLabel):
    """A label that shows a pixmap and never text (the About window's mark)."""

    def __init__(self, pixmap: QPixmap, *, name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.setAccessibleName(name)
        self.setPixmap(pixmap)


def safe_tooltip(value: object) -> str:
    """A tooltip that shows ``value`` literally: escaped as one line, then converted from plain text (S1)."""
    return str(QtGuiNs.convertFromPlainText(T.line(value, 500)))


def set_tooltip(widget: QWidget, value: object) -> None:
    widget.setToolTip(safe_tooltip(value))


def help_tooltip(value: object) -> str:
    """Explanatory text for a tooltip: escaped like :func:`safe_tooltip` but with ordinary spaces, so a long
    explanation wraps."""
    return str(QtGuiNs.convertFromPlainText(T.line(value, 500), Qt.WhiteSpaceMode.WhiteSpaceNormal))


def set_help_tooltip(widget: QWidget, value: object) -> None:
    """Explanatory text (:func:`help_tooltip`) as ``widget``'s tooltip, shown whatever its state (a status badge whose
    tip changes with the status)."""
    widget.setToolTip(help_tooltip(value))


#: D-1064: a control disabled because this platform cannot run the feature; its tooltip (why) shows while it is off
UNAVAILABLE_TIP: Final = "apvUnavailableTip"
_TIP_BEFORE: Final = "apvTipBefore"


def set_unavailable_tooltip(target: QWidget | QAction, value: object | None) -> None:
    """Why a control (a widget or a menu action) is unavailable on this platform (D-1064), as its tooltip, shown although
    it is disabled (the in-use gate of :func:`set_setting_tooltip` lets it through). ``None`` puts the control's own
    tooltip back. Enabling or disabling the control is the caller's."""
    marked = bool(target.property(UNAVAILABLE_TIP))
    if value is None:
        if marked:
            target.setProperty(UNAVAILABLE_TIP, False)
            before = target.property(_TIP_BEFORE)
            target.setToolTip(before if isinstance(before, str) else "")
        return
    if not marked:
        target.setProperty(_TIP_BEFORE, target.toolTip() if isinstance(target, QWidget) else "")
        target.setProperty(UNAVAILABLE_TIP, True)
    target.setToolTip(help_tooltip(value))


class _SettingTipGate(QObject):
    """Swallows a tooltip event unless the setting is in use (Qt shows tooltips on disabled widgets too)."""

    def __init__(self, owner: QWidget, subject: QWidget, active: Callable[[], bool] | None) -> None:
        super().__init__(owner)
        self.subject, self.active = subject, active

    def in_use(self, pointer: QWidget | None = None) -> bool:
        """The subject is enabled, the widget under the pointer (a disabled part of a row) too, and ``active()``."""
        return (self.subject.isEnabled() and (pointer is None or pointer.isEnabled())
                and (self.active is None or bool(self.active())))

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() != QEvent.Type.ToolTip or watched.property(UNAVAILABLE_TIP):  # D-1064: says why it is off
            return False
        pointer = QApplication.widgetAt(event.globalPos()) if isinstance(event, QHelpEvent) else None
        if self.in_use(pointer):
            return False
        event.accept()  # the event stops here: no ancestor's tooltip is shown instead
        return True


#: Where a tooltip's top-left corner goes from the pointer's hot spot, in points at the standard pointer size: just
#: right of and below the macOS arrow, which reaches 10 × 17 points from its hot spot (the arrow's image is 28 × 40
#: points, hot spot (4.5, 4)). Scaled by :func:`pointer_scale`, so a larger pointer does not cover the tip.
TIP_OFFSET: Final = QPoint(4, 20)

_POINTER_PREFS: list[QSettings] = []


def pointer_scale() -> float:
    """macOS Accessibility › Display › Pointer size (``mouseDriverCursorSize``, 1 to 4), which Qt multiplies into its
    own cursor size; 1 elsewhere, or when it cannot be read. Read only, never written."""
    if sys.platform != "darwin":
        return 1.0
    if not _POINTER_PREFS:
        _POINTER_PREFS.append(QSettings(QSettings.Format.NativeFormat, QSettings.Scope.UserScope, "apple.com",
                                        "universalaccess"))
    try:
        value = float(_POINTER_PREFS[0].value("mouseDriverCursorSize", 1.0))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 1.0
    return min(4.0, max(1.0, value)) if math.isfinite(value) else 1.0


def tip_position(anchor: QPoint, size: QSize, screen: QRect, scale: float = 1.0) -> QPoint:
    """The top-left corner of a tooltip (or the graph's popover) of ``size`` for the pointer's hot spot at ``anchor``:
    :data:`TIP_OFFSET` times ``scale``; left of the hot spot when that would cross the screen's right edge, above it
    when it would cross the bottom, and then kept on ``screen`` (the clamping of Qt's ``QTipLabel::placeTip``)."""
    x = anchor.x() + round(TIP_OFFSET.x() * scale)
    y = anchor.y() + round(TIP_OFFSET.y() * scale)
    if x + size.width() > screen.x() + screen.width():
        x = anchor.x() - 4 - size.width()
    if y + size.height() > screen.y() + screen.height():
        y = anchor.y() - 4 - size.height()
    x = max(screen.x(), min(x, screen.x() + screen.width() - size.width()))
    y = max(screen.y(), min(y, screen.y() + screen.height() - size.height()))
    return QPoint(x, y)


def screen_rect(at: QPoint, widget: QWidget | None = None) -> QRect:
    """The geometry of the screen under ``at`` (else ``widget``'s, else the primary screen's)."""
    screen = QGuiApplication.screenAt(at) or (widget.screen() if widget is not None else None) \
        or QGuiApplication.primaryScreen()
    return screen.geometry() if screen is not None else QRect(at, QSize(1, 1))


#: The tooltip's look (D-1060): a card of the current scheme (its colour, a hairline border, rounded corners and a soft
#: shadow), text at :data:`TIP_FONT_PX` with :data:`TIP_PADDING` around it, wrapped at :data:`TIP_MAX_WIDTH`.
TIP_MAX_WIDTH: Final = 360  # the card's widest (px): a longer explanation wraps into a block
TIP_PADDING: Final = (6, 9)  # between the card's edge and the text (px): top and bottom, left and right
TIP_RADIUS: Final = 8
TIP_SHADOW: Final = QMargins(5, 3, 5, 7)  # the room around the card for its shadow (left, top, right, bottom; px)
TIP_FONT_PX: Final = 12  # at the 13 px body size; it follows View › Bigger and Smaller


def is_tip_label(widget: QObject) -> bool:
    """Qt's tooltip label: a label that is a tooltip window (it has no object name yet when it is first polished)."""
    return isinstance(widget, QLabel) and widget.isWindow() and widget.windowType() == Qt.WindowType.ToolTip


def tip_style(t: theme.Tokens) -> str:
    """The tooltip label's own style sheet (Qt's style sheets name its label ``QToolTip``): the text colour of ``t``, no
    panel of Qt's (the filter paints the card), and the shadow's room and the padding around the text."""
    m, (pv, ph) = TIP_SHADOW, TIP_PADDING
    return (f"QToolTip {{ color: {t.text}; background: transparent; border: none; "
            f"margin: {m.top()}px {m.right()}px {m.bottom()}px {m.left()}px; padding: {pv}px {ph}px; }}")


def tip_font() -> QFont:
    """The tooltip's font: the application's, at :data:`TIP_FONT_PX` of the 13 px body size."""
    font = QFont(QApplication.font())
    size = font.pointSizeF()
    if size > 0:
        font.setPointSizeF(max(7.0, size * TIP_FONT_PX / theme.TYPE["body"]))
    return font


def tip_size(label: QLabel) -> QSize:
    """The size of a tooltip label: the card at most :data:`TIP_MAX_WIDTH` wide, as narrow as the text's lines at that
    width allow (a short tip stays one short line; a long explanation wraps into a block), and as tall as the wrapped
    text. Text that cannot wrap there (a long path or id, whose spaces do not break) keeps the size Qt gives it."""
    hint = label.sizeHint()
    cap = TIP_MAX_WIDTH + TIP_SHADOW.left() + TIP_SHADOW.right()
    if not label.wordWrap() or label.minimumSizeHint().width() > cap:
        return hint
    height = label.heightForWidth(cap)
    lo, hi = min(label.minimumSizeHint().width(), cap), cap  # the narrowest width that keeps the lines at the cap
    while lo < hi:
        mid = (lo + hi) // 2
        if label.heightForWidth(mid) > height:
            lo = mid + 1
        else:
            hi = mid
    return QSize(hi, height)


def _paint_tip_card(label: QLabel) -> None:
    """The card behind the tooltip's text: a soft shadow (rings fading outwards, a little lower than the card), then
    the card's colour with a hairline border and rounded corners. The label paints its text over it."""
    t = theme.tokens()
    card = QRectF(label.rect()).marginsRemoved(QMarginsF(TIP_SHADOW))
    p = QPainter(label)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    rings = min(TIP_SHADOW.left(), TIP_SHADOW.right())
    shade = QColor(0, 0, 0, 22 if theme.is_dark() else 12)
    for i in range(rings, 0, -1):
        p.setBrush(shade)
        p.drawRoundedRect(card.adjusted(-i, -i + 2, i, i + 2), TIP_RADIUS + i, TIP_RADIUS + i)
    p.setBrush(QColor(t.card))
    p.setPen(QPen(QColor(t.card_border), 1))
    p.drawRoundedRect(card.adjusted(0.5, 0.5, -0.5, -0.5), TIP_RADIUS, TIP_RADIUS)
    p.end()


class TooltipFilter(QObject):
    """Every tooltip of the app passes here: installed once on the application (``app.py``,
    :func:`install_tooltip_filter`), it sees each tooltip event before the widget, item view, header, tab bar or combo
    popup that would answer it.

    * Settings › Appearance › Show tooltips off (:func:`set_tooltips_shown`): every tooltip event is swallowed.
    * On: Qt's tooltip label is placed at :func:`tip_position` of the pointer when it is shown or moved to a new tip.
      Qt itself puts it a whole cursor image below the hot spot (``QTipLabel::placeTip``: ``QPlatformCursor::size()``
      down, which on macOS is the arrow image's 40 points times the pointer size) for any tip more than half that
      tall, which is every wrapped explanation, and beside the pointer for a shorter one.
    * The look (D-1060): the label gets a translucent window before it first exists (no system shadow; its own soft
      one), the current scheme's card colour, hairline border and text colour (:func:`tip_style`), the tooltip font
      (:func:`tip_font`) and its size (:func:`tip_size`: a long explanation wraps at :data:`TIP_MAX_WIDTH`) whenever
      it is shown or resized for a new tip, so a change of the appearance reaches the next tip.

    The setting gates (:func:`set_setting_tooltip`) still decide first: a tip they swallow is never shown, so it is
    never placed. The text is the widget's own (plain text, S1)."""

    #: Settings › Appearance › Show tooltips (:func:`set_tooltips_shown`)
    shown: ClassVar[bool] = True

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.anchor: QPoint | None = None  # the hot spot of the latest tooltip event
        self._placing = False

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        kind = event.type()
        if kind == QEvent.Type.ToolTip:
            if not TooltipFilter.shown:
                event.accept()  # the event stops here: no ancestor's tooltip either
                return True
            if isinstance(event, QHelpEvent):
                self.anchor = event.globalPos()
            return False
        if kind == QEvent.Type.Paint:
            if is_tip_label(watched):
                _paint_tip_card(watched)  # type: ignore[arg-type]
            return False
        if kind == QEvent.Type.Polish and is_tip_label(watched):
            self.prepare(watched)  # type: ignore[arg-type]
            return False
        if kind in (QEvent.Type.Show, QEvent.Type.Move, QEvent.Type.Resize) and not self._placing \
                and isinstance(watched, QWidget) and (watched.objectName() == "qtooltip_label" or is_tip_label(watched)):
            if kind != QEvent.Type.Move and is_tip_label(watched):
                self.style(watched)  # type: ignore[arg-type]
            if self.anchor is not None:
                self.place(watched, self.anchor)
        return False

    @staticmethod
    def prepare(label: QLabel) -> None:
        """Before the tooltip's window exists: translucent, so the card's corners and shadow show what is behind them,
        and without the system's shadow (the card has its own)."""
        label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        if label.windowHandle() is None:
            label.overrideWindowFlags(label.windowFlags() | Qt.WindowType.NoDropShadowWindowHint)

    def style(self, label: QLabel) -> None:
        """The current scheme's style, the tooltip font and :func:`tip_size` (each set only when it changed)."""
        if not label.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground):
            self.prepare(label)  # a label made before the filter was installed
        sheet = tip_style(theme.tokens())
        if label.styleSheet() != sheet:
            label.setStyleSheet(sheet)
        font = tip_font()
        if label.font() != font:
            label.setFont(font)
        if label.margin() or label.indent() > 0:
            label.setMargin(0)
            label.setIndent(0)
        size = tip_size(label)
        if label.size() != size:
            self._placing = True
            try:
                label.resize(size)
            finally:
                self._placing = False

    def place(self, label: QWidget, anchor: QPoint) -> None:
        """Move Qt's tooltip ``label`` to :func:`tip_position` of ``anchor``. On a Show event the window is not on screen
        yet, so it appears there directly."""
        target = tip_position(anchor, label.size(), screen_rect(anchor, label), pointer_scale())
        if label.pos() != target:
            self._placing = True
            try:
                label.move(target)
            finally:
                self._placing = False


_FILTER: list[TooltipFilter] = []


def install_tooltip_filter(app: QApplication, *, shown: bool = True) -> TooltipFilter:
    """The application's :class:`TooltipFilter`, installed on the first call; ``shown`` is Settings › Appearance › Show
    tooltips."""
    set_tooltips_shown(shown)
    if not _FILTER:
        _FILTER.append(TooltipFilter(app))
        app.installEventFilter(_FILTER[0])
    return _FILTER[0]


def set_tooltips_shown(shown: bool) -> None:
    """Settings › Appearance › Show tooltips: off swallows every tooltip (and the graph's popover); a tip already
    showing is hidden."""
    TooltipFilter.shown = bool(shown)
    if not shown:
        QToolTip.hideText()


def tooltips_shown() -> bool:
    return TooltipFilter.shown


def set_setting_tooltip(widget: QWidget, value: object, *, subject: QWidget | None = None,
                        active: Callable[[], bool] | None = None) -> None:
    """What a setting does, as ``widget``'s tooltip, shown only while the setting is in use: ``subject`` (default
    ``widget``) is enabled, so is the widget under the pointer, and ``active()`` (when given) is true. A greyed-out
    setting, or one that does not apply to the current choice, shows none. The text is :func:`help_tooltip`'s."""
    widget.setToolTip(help_tooltip(value))
    widget.installEventFilter(_SettingTipGate(widget, subject or widget, active))


def set_control_tooltip(widget: QWidget, value: object, *, active: Callable[[], bool] | None = None) -> None:
    """What a control (a button, a filter, a switch, a status line) does, shown like a setting's: only while it is
    enabled and ``active()`` (when given) is true (:func:`set_setting_tooltip`)."""
    set_setting_tooltip(widget, value, active=active)


def set_header_tooltips(view: QTableWidget | QTreeWidget, tips: Sequence[str]) -> None:
    """What each column of a ``QTableWidget`` or ``QTreeWidget`` holds, as its header's tooltip (in column order)."""
    if isinstance(view, QTreeWidget):
        header = view.headerItem()
        for column, tip in enumerate(tips):
            header.setToolTip(column, help_tooltip(tip))
        return
    for column, tip in enumerate(tips):
        item = view.horizontalHeaderItem(column)
        if item is not None:
            item.setToolTip(help_tooltip(tip))


def set_list_item_tooltip(item: object, value: object, *, wrap: bool = False) -> None:
    """A tooltip on a ``QListWidgetItem`` (one column); ``wrap``: explanatory text (:func:`help_tooltip`)."""
    item.setToolTip(help_tooltip(value) if wrap else safe_tooltip(value))  # type: ignore[attr-defined]


def set_combo_item_tooltip(box: object, index: int, value: object) -> None:
    """A tooltip on one item of a ``QComboBox``."""
    box.setItemData(index, safe_tooltip(value), Qt.ItemDataRole.ToolTipRole)  # type: ignore[attr-defined]


def set_item_tooltip(item: object, column: int, value: object) -> None:
    """A tooltip on a ``QTreeWidgetItem``/``QTableWidgetItem`` column."""
    item.setToolTip(column, safe_tooltip(value))  # type: ignore[attr-defined]


def set_tab_tooltip(tabs: object, index: int, value: object, *, wrap: bool = False) -> None:
    """A tooltip on one tab of a ``QTabWidget`` (D-840); ``wrap``: explanatory text (:func:`help_tooltip`)."""
    tabs.setTabToolTip(index, help_tooltip(value) if wrap else safe_tooltip(value))  # type: ignore[attr-defined]


def tab_text(text: str) -> str:
    """A tab title from display text (already escaped with :mod:`agentprov_gui.text`): ``&`` doubled, because
    ``QTabBar`` reads it as a mnemonic marker (D-840)."""
    return text.replace("&", "&&")


def is_tooltip_role(role: int) -> bool:
    """For item models: return :func:`safe_tooltip` text for this role, never raw data."""
    return role == Qt.ItemDataRole.ToolTipRole


def tooltip_for(model: QAbstractItemModel, index: QModelIndex, value: object) -> str:
    del model, index
    return safe_tooltip(value)


class ReadOnlyText(QPlainTextEdit):
    """A read-only plain-text pane (``QPlainTextEdit`` never interprets markup)."""

    #: How much text from the first visible line on identifies the reading position (several lines, so a repeated
    #: line alone does not move the view to another copy of it).
    _ANCHOR_CHARS = 1024

    def __init__(self, *, name: str, parent: QWidget | None = None, wrap: bool = False) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setUndoRedoEnabled(False)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth if wrap else QPlainTextEdit.LineWrapMode.NoWrap)
        self.setAccessibleName(name)
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )

    def canInsertFromMimeData(self, source: object) -> bool:
        return False

    def set_plain_keep(self, text: str, *, follow_end: bool = False, fresh: bool = False) -> None:
        """Replace the text only when it changed, so a timer refresh keeps the scroll position and selection.
        With ``follow_end`` the pane stays at the end when it was there (or is ``fresh``: newly filled for another
        item); otherwise the previous reading position is kept, or a ``fresh`` pane starts at the top. The position is
        kept by content (GR-57): a tail window that slides drops its oldest lines, so the same scroll value would show
        later text. The lines on top are found again in the new text (the nearest match at or before their old
        place); when they were dropped the pane shows the top, the oldest lines still held."""
        old = self.toPlainText()
        if not fresh and text == old:
            return
        bar = self.verticalScrollBar()
        at_end, value = bar.value() >= bar.maximum(), bar.value()
        first = self.firstVisibleBlock()
        start = first.position() if first.isValid() else 0
        anchor = old[start:start + self._ANCHOR_CHARS]
        self.setPlainText(text)
        if follow_end and (fresh or at_end):
            bar.setValue(bar.maximum())
        elif not fresh:
            found = text.rfind("\n" + anchor, 0, start + len(anchor)) + 1 if anchor else 0
            if not found and not text.startswith(anchor):
                bar.setValue(0)
                return
            block = self.document().findBlock(found)
            bar.setValue(max(0, value + block.blockNumber() - first.blockNumber()))


def safe_message_box(
    parent: QWidget | None,
    title: str,
    text: str,
    *,
    informative: str = "",
    detailed: str = "",
    icon: QMessageBox.Icon = QMessageBox.Icon.Information,
    buttons: QMessageBox.StandardButton = QMessageBox.StandardButton.Ok,
    default: QMessageBox.StandardButton | None = None,
) -> QMessageBox:
    """A message box in plain-text mode (S1). The caller ``exec()``s or ``open()``s it."""
    box = QMessageBox(parent)
    box.setTextFormat(Qt.TextFormat.PlainText)
    box.setIcon(icon)
    box.setWindowTitle(title)
    box.setText(text)
    if informative:
        box.setInformativeText(informative)
        # the informative label follows the box's format; make sure of it
        for label in box.findChildren(QLabel):
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setOpenExternalLinks(False)
    if detailed:
        box.setDetailedText(detailed)  # shown in a QTextEdit as plain text by Qt
    box.setStandardButtons(buttons)
    if default is not None:
        box.setDefaultButton(default)
    box.setAccessibleName(title)
    for label in box.findChildren(QLabel):
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setOpenExternalLinks(False)
    return box


class SafeForm(QFormLayout):
    """A form layout whose row labels are :class:`SafeLabel` (``QFormLayout.addRow(str, …)`` makes an AutoText label).
    Fields grow with the window (the macOS style otherwise keeps them at their size hint, which truncates paths)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

    def add(self, label: str, field: QWidget, tip: str | None = None, *, subject: QWidget | None = None,
            active: Callable[[], bool] | None = None) -> SafeLabel:
        """A row. ``tip`` says what the setting does; the row's label and its field show it only while the setting
        is in use (:func:`set_setting_tooltip`; ``subject`` is the input inside a composite ``field``)."""
        lab = SafeLabel(label, name=label, selectable=False)
        lab.setBuddy(field)
        if not field.accessibleName():
            field.setAccessibleName(label)
        super().addRow(lab, field)
        if tip:
            for widget in dict.fromkeys((lab, field, subject or field)):
                set_setting_tooltip(widget, tip, subject=subject or field, active=active)
        return lab


class DocView(QTextBrowser):
    """The Help › Docs reader (D-1010): the checkout's own user guide, which is first-party Markdown and never data.

    Corpus text, CLI output and model replies never reach this widget; they stay in plain-text panes. Links are never
    followed by the widget: ``anchorClicked`` hands each one to the page, which opens guide chapters itself and copies
    a web address instead of opening it. Images load only from files under the guide's folder, scaled to the view."""

    MAX_IMAGE_WIDTH = 900

    def __init__(self, *, name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.setReadOnly(True)
        self.setAccessibleName(name)
        self.root: Path | None = None

    def show_markdown(self, text: str, root: Path) -> None:
        """Show ``text`` (a guide chapter); relative image paths resolve under ``root``."""
        self.root = root.resolve()
        self.document().setBaseUrl(QUrl.fromLocalFile(str(self.root) + "/"))
        self.setMarkdown(text)

    def loadResource(self, kind: int, url: QUrl | str) -> object:
        """Local image files under the guide only; anything else (a web address, a file elsewhere) loads nothing."""
        if kind != QTextDocument.ResourceType.ImageResource.value or self.root is None:
            return None
        qurl = url if isinstance(url, QUrl) else QUrl(url)
        if qurl.scheme() not in ("", "file"):
            return None
        path = Path(qurl.toLocalFile() if qurl.isLocalFile() else str(self.root / qurl.path())).resolve()
        if not path.is_relative_to(self.root) or not path.is_file():
            return None
        image = QImage(str(path))
        if image.isNull():
            return None
        width = min(self.MAX_IMAGE_WIDTH, max(200, self.viewport().width() - 40))
        return image.scaledToWidth(width, Qt.TransformationMode.SmoothTransformation) if image.width() > width \
            else image


WARNING = QMessageBox.Icon.Warning
CRITICAL = QMessageBox.Icon.Critical
INFORMATION = QMessageBox.Icon.Information


def ask(parent: QWidget | None, title: str, text: str, informative: str = "", *,
        icon: QMessageBox.Icon = QMessageBox.Icon.Warning, default_ok: bool = False) -> bool:
    """An OK/Cancel question in plain text; Cancel is the default unless ``default_ok``."""
    ok, cancel = QMessageBox.StandardButton.Ok, QMessageBox.StandardButton.Cancel
    box = safe_message_box(parent, title, text, informative=informative, icon=icon, buttons=ok | cancel,
                           default=ok if default_ok else cancel)
    return box.exec() == ok


def choose(parent: QWidget | None, title: str, text: str, informative: str, keep: str, other: str, *,
           tips: tuple[str, str] = ("", "")) -> bool:
    """Two named buttons; ``keep`` is the default and the escape button. True when ``other`` (destructive) is chosen.
    ``tips``: what each button does (``keep``'s, then ``other``'s)."""
    box = safe_message_box(parent, title, text, informative=informative, icon=QMessageBox.Icon.Warning,
                           buttons=QMessageBox.StandardButton.NoButton)
    keep_button = box.addButton(keep, QMessageBox.ButtonRole.RejectRole)
    other_button = box.addButton(other, QMessageBox.ButtonRole.DestructiveRole)
    theme.mark_destructive(other_button)
    for button, tip in zip((keep_button, other_button), tips, strict=True):
        if tip:
            button.setToolTip(help_tooltip(tip))
    box.setDefaultButton(keep_button)
    box.setEscapeButton(keep_button)
    box.exec()
    return box.clickedButton() is other_button
