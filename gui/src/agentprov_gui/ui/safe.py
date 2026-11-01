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

from collections.abc import Callable, Sequence
from pathlib import Path

from PySide6.QtCore import QAbstractItemModel, QEvent, QModelIndex, QObject, Qt, QUrl
from PySide6.QtGui import QHelpEvent, QImage, QPixmap, QTextDocument
from PySide6.QtGui import Qt as QtGuiNs
from PySide6.QtWidgets import (
    QApplication,
    QFormLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QTableWidget,
    QTextBrowser,
    QTreeWidget,
    QWidget,
)

from agentprov_gui import text as T

__all__ = [
    "DocView",
    "ReadOnlyText",
    "SafeForm",
    "SafeImage",
    "SafeLabel",
    "help_tooltip",
    "is_tooltip_role",
    "safe_message_box",
    "safe_tooltip",
    "set_combo_item_tooltip",
    "set_control_tooltip",
    "set_header_tooltips",
    "set_item_tooltip",
    "set_list_item_tooltip",
    "set_setting_tooltip",
    "set_tab_tooltip",
    "set_tooltip",
    "tab_text",
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
        if event.type() != QEvent.Type.ToolTip:
            return False
        pointer = QApplication.widgetAt(event.globalPos()) if isinstance(event, QHelpEvent) else None
        if self.in_use(pointer):
            return False
        event.accept()  # the event stops here: no ancestor's tooltip is shown instead
        return True


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


def set_list_item_tooltip(item: object, value: object) -> None:
    """A tooltip on a ``QListWidgetItem`` (one column)."""
    item.setToolTip(safe_tooltip(value))  # type: ignore[attr-defined]


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


def choose(parent: QWidget | None, title: str, text: str, informative: str, keep: str, other: str) -> bool:
    """Two named buttons; ``keep`` is the default and the escape button. True when ``other`` (destructive) is chosen."""
    box = safe_message_box(parent, title, text, informative=informative, icon=QMessageBox.Icon.Warning,
                           buttons=QMessageBox.StandardButton.NoButton)
    keep_button = box.addButton(keep, QMessageBox.ButtonRole.RejectRole)
    other_button = box.addButton(other, QMessageBox.ButtonRole.DestructiveRole)
    box.setDefaultButton(keep_button)
    box.setEscapeButton(keep_button)
    box.exec()
    return box.clickedButton() is other_button
