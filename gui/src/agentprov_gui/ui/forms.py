"""The shared form components of the GUI's one visual and form style (D-1060; the style guide's nine rules).

Every input screen is built from these, so Run Live, New Job, Settings, Package and the Zenodo forms change together:

* :class:`FormPage`: a column at most :data:`COLUMN_MAX` px wide that scrolls only vertically (rule 7: help text
  wraps, controls shrink, never a horizontal scroll bar);
* :class:`FormSection`: a small capitalised heading over a rounded card whose rows are separated by hairlines
  (rule 1); a hidden row takes its hairline with it (rule 3);
* :class:`FormRow`: a plain label, an optional grey caption under it (rule 2), the control and an optional unit;
  the tooltip (the CLI flag, the file name) goes through :func:`safe.set_setting_tooltip`;
* :class:`Disclosure`: one collapsed level labelled with what it holds, remembered per screen (rule 4);
* the right control (rule 6): :class:`SegmentedControl` (two to four exclusive choices), :class:`Switch` (on/off),
  :class:`ChipGroup` and :class:`Checklist` (many toggles), :class:`IntField` / :class:`DecimalField` (a short
  right-aligned number with its unit and a grey "Default (…)" placeholder meaning unset, rule 5) and
  :class:`PathField` (a field plus Choose…, the long middle elided);
* :class:`StatusBadge` (words and a tint, never colour alone), :class:`CommandCard` (the terminal command, plain
  text, wrapped, with Copy) and :class:`SummaryPanel` (what the choices add up to, rule 8).

All text is plain (S1): every text-bearing part is a :class:`safe.SafeLabel` or a button's plain text, and colours come
from :mod:`theme`'s tokens through the app-wide style sheet (the ``apvRole`` property selects a part). Every widget
has an accessible name; tab order follows the visual order (widgets are created in that order).
"""

from __future__ import annotations

import shlex
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QSettings, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QGuiApplication,
    QKeyEvent,
    QPainter,
    QPaintEvent,
    QResizeEvent,
    QShowEvent,
    QValidator,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractSpinBox,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLayout,
    QLayoutItem,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStyle,
    QStyleOptionFrame,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from agentprov_gui.ui import theme
from agentprov_gui.ui.safe import SafeLabel, set_control_tooltip, set_help_tooltip, set_setting_tooltip

__all__ = [
    "COLUMN_MAX", "LABEL_WIDTH", "Checklist", "ChipGroup", "Choice", "CommandCard", "DecimalField", "Disclosure",
    "FactGrid", "FormPage", "FormRow", "FormSection", "IntField", "OverflowBar", "PathField", "SegmentedControl",
    "StatusBadge",
    "SummaryPanel", "Switch", "caption", "combo", "command_text", "heading", "is_input_part", "link_button",
    "wrap_command",
]  # fmt: skip

#: rule 7: the form column's maximum width; the label column's width (the style guide's 160-190 px)
COLUMN_MAX: Final = 680
LABEL_WIDTH: Final = 180
SUMMARY_WIDTH: Final = 340
#: the property that marks a widget as part of a composite input (a segment, a chip, a checklist box), so the reverse
#: parity walk (D-700) counts the composite once
INPUT_PART: Final = "apvInputPart"


def _role(widget: QWidget, role: str) -> None:
    widget.setProperty("apvRole", role)


def is_input_part(widget: QObject) -> bool:
    """True for a part of a composite input (its owner is the input)."""
    return bool(widget.property(INPUT_PART))


def caption(text: str, *, name: str, parent: QWidget | None = None, role: str = "caption") -> SafeLabel:
    """A grey caption (11 px): word-wrapped plain text that never widens the column."""
    label = SafeLabel(text, name=name, parent=parent, selectable=False)
    _role(label, role)
    label.setFont(theme.scaled_font("caption"))
    label.setWordWrap(True)
    label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    label.setMinimumWidth(0)
    return label


def heading(text: str, *, name: str | None = None, parent: QWidget | None = None) -> SafeLabel:
    """A section heading: small, semibold, grey, in capitals (rule 1)."""
    label = SafeLabel(text.upper(), name=name or text, parent=parent, selectable=False)
    _role(label, "heading")
    label.setFont(theme.scaled_font("heading"))
    return label


def link_button(text: str, *, name: str, parent: QWidget | None = None) -> QPushButton:
    """A text-only button in the link colour (Copy, Show the plan by suite)."""
    button = QPushButton(text, parent)
    _role(button, "link")
    button.setAccessibleName(name)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setFlat(True)
    return button


def combo(parent: QWidget | None = None, *, name: str, editable: bool = False, minimum_chars: int = 12) -> QComboBox:
    """A combo box that never widens the column for a long item (it shrinks to ``minimum_chars``; the popup shows the
    whole text)."""
    box = QComboBox(parent)
    box.setEditable(editable)
    box.setAccessibleName(name)
    box.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    box.setMinimumContentsLength(minimum_chars)
    box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    return box


class _Hairline(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        _role(self, "hairline")
        self.setFixedHeight(1)
        self.setFrameShape(QFrame.Shape.NoFrame)


# --------------------------------------------------------------------------------------------- page, section, row
class FormPage(QScrollArea):
    """A vertically scrolling form column at most :data:`COLUMN_MAX` px wide (rule 7). The horizontal scroll bar is
    always off and the column takes the viewport's width below the maximum; its parts wrap or shrink."""

    def __init__(self, *, name: str, parent: QWidget | None = None, title: str = "",
                 max_width: int = COLUMN_MAX) -> None:
        super().__init__(parent)
        self.setAccessibleName(name)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        outer = QWidget(self)
        _role(outer, "page")
        row = QHBoxLayout(outer)
        row.setContentsMargins(3 * theme.SPACE, 20, 3 * theme.SPACE, 3 * theme.SPACE)
        self.column = QWidget(outer)
        _role(self.column, "column")
        self.column.setMaximumWidth(max_width)
        self.column.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.layout_ = QVBoxLayout(self.column)
        self.layout_.setContentsMargins(0, 0, 0, 0)
        self.layout_.setSpacing(18)  # the style guide: 18 px between sections
        if title:
            t = SafeLabel(title, name=title, parent=self.column, selectable=False)
            t.setFont(theme.scaled_font("title"))
            self.layout_.addWidget(t)
        row.addWidget(self.column, 1)
        row.addStretch(0)
        self.layout_.addStretch(1)
        self.setWidget(outer)

    def add(self, widget: QWidget) -> QWidget:
        """Append ``widget`` (a section, a disclosure) to the column."""
        self.layout_.insertWidget(self.layout_.count() - 1, widget)
        return widget


class FormRow(QWidget):
    """One row of a card: the label (with an optional grey caption under it), the control(s) and an optional unit.

    ``tip`` says what the setting does (the CLI flag goes here, rule 2); the label and the field show it only while
    the setting is in use (:func:`safe.set_setting_tooltip`). ``stretch``: the control takes the rest of the row (a
    short control, such as a number, stays at its size). ``top``: the label aligns with the control's top (a
    checklist)."""

    def __init__(self, label: str, field: QWidget | None, *, caption_text: str = "", tip: str | None = None,
                 unit: str = "", trailing: Sequence[QWidget] = (), stretch: bool = True, top: bool = False,
                 subject: QWidget | None = None, active: Callable[[], bool] | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAccessibleName(label or "Row")
        self.hairline = _Hairline(self)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self.hairline)
        body = QHBoxLayout()
        body.setContentsMargins(14, 10, 14, 10)
        body.setSpacing(12)
        outer.addLayout(body)
        left = QVBoxLayout()
        left.setSpacing(2)
        self.label = SafeLabel(label, name=label or "Row label", parent=self, selectable=False)
        self.label.setWordWrap(True)
        left.addWidget(self.label)
        self.caption = caption(caption_text, name=f"{label}: note" if label else "Note", parent=self)
        self.caption.setVisible(bool(caption_text))
        left.addWidget(self.caption)
        holder = QWidget(self)
        holder.setFixedWidth(LABEL_WIDTH)
        holder.setLayout(left)
        left.setContentsMargins(0, 0, 0, 0)
        if top:
            left.addStretch(1)
        body.addWidget(holder, 0, Qt.AlignmentFlag.AlignTop if top else Qt.AlignmentFlag.AlignVCenter)
        self.field = field
        self.unit: SafeLabel | None = None
        fixed = (QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Maximum)
        if field is not None and field.sizePolicy().horizontalPolicy() in fixed:
            stretch = False  # a control that cannot grow keeps to the left, the row's space after it
        if field is not None:
            if label:
                self.label.setBuddy(field)
            if not field.accessibleName():
                field.setAccessibleName(label)
            body.addWidget(field, 1 if stretch else 0, Qt.AlignmentFlag.AlignTop if top else Qt.AlignmentFlag(0))
        unit = unit or (getattr(field, "unit", "") if field is not None else "")
        if unit:
            self.unit = SafeLabel(unit, name=f"{label} unit", parent=self, selectable=False)
            _role(self.unit, "unit")
            body.addWidget(self.unit)
        for w in trailing:
            body.addWidget(w)
        if not stretch:
            body.addStretch(1)
        if tip and field is not None:
            subj = subject or field
            for widget in dict.fromkeys((self.label, field, subj)):
                set_setting_tooltip(widget, tip, subject=subj, active=active)
        elif tip:
            set_setting_tooltip(self.label, tip, active=active)

    def set_caption(self, text: str) -> None:
        self.caption.set_plain(text)
        self.caption.setVisible(bool(text))


class FormSection(QWidget):
    """A heading over a rounded card of rows separated by hairlines (rule 1); ``note``: a grey line under the card.
    A hidden row's hairline goes with it, and the first visible row has none."""

    def __init__(self, title: str, *, parent: QWidget | None = None, note: str = "") -> None:
        super().__init__(parent)
        self.setAccessibleName(title)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.heading = heading(title, parent=self) if title else None
        if self.heading is not None:
            self.heading.setContentsMargins(10, 0, 0, 0)
            lay.addWidget(self.heading)
        self.card = QFrame(self)
        _role(self.card, "card")
        self.card.setAccessibleName(f"{title} card" if title else "Card")
        self.rows = QVBoxLayout(self.card)
        self.rows.setContentsMargins(0, 0, 0, 0)
        self.rows.setSpacing(0)
        lay.addWidget(self.card)
        self.note = caption(note, name=f"{title}: note" if title else "Section note", parent=self)
        self.note.setContentsMargins(10, 0, 0, 0)
        self.note.setVisible(bool(note))
        lay.addWidget(self.note)
        self._members: list[QWidget] = []

    def add(self, row: QWidget) -> QWidget:
        """Append a row (a :class:`FormRow`, or any widget, which then gets a hairline of its own)."""
        if not isinstance(row, FormRow):
            row = _Wrapped(row, self.card)
        self.rows.addWidget(row)
        self._members.append(row)
        row.installEventFilter(self)
        self._hairlines()
        return row

    def add_row(self, label: str, field: QWidget | None, **kw: object) -> FormRow:
        row = FormRow(label, field, parent=self.card, **kw)  # type: ignore[arg-type]
        self.add(row)
        return row

    def set_note(self, text: str) -> None:
        self.note.set_plain(text)
        self.note.setVisible(bool(text))

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() in (QEvent.Type.ShowToParent, QEvent.Type.HideToParent):
            self._hairlines()
        return False

    def _hairlines(self) -> None:
        first = True
        for row in self._members:
            line = getattr(row, "hairline", None)
            if row.isHidden():
                continue
            if isinstance(line, QWidget):
                line.setVisible(not first)
            first = False
        self.card.setVisible(not first)


class _Wrapped(QWidget):
    """A widget placed in a card as a row of its own (a note, a full-width control)."""

    def __init__(self, inner: QWidget, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAccessibleName(inner.accessibleName() or "Row")
        self.inner = inner
        self.hairline = _Hairline(self)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.hairline)
        box = QVBoxLayout()
        box.setContentsMargins(14, 8, 14, 8)
        box.addWidget(inner)
        lay.addLayout(box)
        inner.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # the row follows its widget's visibility
        if watched is self.inner and event.type() in (QEvent.Type.ShowToParent, QEvent.Type.HideToParent):
            self.setVisible(not self.inner.isHidden())
        return False


# --------------------------------------------------------------------------------------------- disclosure (rule 4)
_REMEMBERED: dict[str, bool] = {}  # without a store: remembered for this process only (tests, a dialog without one)


class Disclosure(QWidget):
    """One collapsed level labelled with what it holds ("Advanced: concurrency, attempts, …"); never nested. Its
    state is remembered per screen: in ``store`` (the GUI's QSettings) under ``forms/disclosure/SCREEN/KEY``, else for
    this process."""

    toggled = Signal(bool)

    def __init__(self, title: str, *, screen: str, key: str, store: QSettings | None = None, name: str = "",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAccessibleName(title)
        self.store, self.setting = store, f"forms/disclosure/{screen}/{key}"
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.button = QToolButton(self)
        _role(self.button, "disclosure")
        self.button.setText(title)
        self.button.setCheckable(True)
        self.button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.button.setArrowType(Qt.ArrowType.RightArrow)
        self.button.setIconSize(QSize(9, 9))
        self.button.setAccessibleName(name or title)
        lay.addWidget(self.button, 0, Qt.AlignmentFlag.AlignLeft)
        self.content = QWidget(self)
        self.content.setAccessibleName(f"{title}: contents")
        self.body = QVBoxLayout(self.content)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(18)
        lay.addWidget(self.content)
        self.button.toggled.connect(self._toggled)
        opened = self._stored()
        self.button.setChecked(opened)
        self._show(opened)

    def add(self, widget: QWidget) -> QWidget:
        self.body.addWidget(widget)
        return widget

    def is_open(self) -> bool:
        return self.button.isChecked()

    def set_open(self, value: bool) -> None:
        self.button.setChecked(value)

    def _stored(self) -> bool:
        if self.store is None:
            return _REMEMBERED.get(self.setting, False)
        value = self.store.value(self.setting, "false")
        return value is True or value == "true"

    def _toggled(self, opened: bool) -> None:
        if self.store is None:
            _REMEMBERED[self.setting] = opened
        else:
            self.store.setValue(self.setting, "true" if opened else "false")
        self._show(opened)
        self.toggled.emit(opened)

    def _show(self, opened: bool) -> None:
        self.button.setArrowType(Qt.ArrowType.DownArrow if opened else Qt.ArrowType.RightArrow)
        self.content.setVisible(opened)


# --------------------------------------------------------------------------------------------- the right control
class SegmentedControl(QFrame):
    """Two to four exclusive choices (rule 6), with the combo box's API (``currentIndex``, ``setCurrentIndex``,
    ``currentData``, ``currentIndexChanged``). Left and Right move the choice; each segment can take its own tip."""

    currentIndexChanged = Signal(int)
    #: the most choices a wrapping control takes
    WRAP_MAX: Final = 10

    def __init__(self, choices: Sequence[str | tuple[str, object]], *, name: str, parent: QWidget | None = None,
                 current: int = 0, wrap: bool = False) -> None:
        """``wrap``: the segments wrap onto the next line in a narrow pane, and up to :data:`WRAP_MAX` choices are
        allowed (the Viewer's inspector, whose views replace a tab bar)."""
        super().__init__(parent)
        if not 2 <= len(choices) <= (self.WRAP_MAX if wrap else 4):
            raise ValueError("a segmented control has two to four choices")
        _role(self, "segments")
        self.setAccessibleName(name)
        lay: QLayout
        if wrap:
            self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
            self.setContentsMargins(2, 2, 2, 2)
            lay = FlowLayout(self, spacing=2)
        else:
            self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
            lay = QHBoxLayout(self)
            lay.setContentsMargins(2, 2, 2, 2)
            lay.setSpacing(2)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons: list[QPushButton] = []
        self._data: list[object] = []
        for i, choice in enumerate(choices):
            text, data = (choice, choice) if isinstance(choice, str) else choice
            b = QPushButton(text, self)
            _role(b, "segment")
            b.setProperty(INPUT_PART, True)
            b.setCheckable(True)
            b.setAutoDefault(False)
            b.setAccessibleName(f"{text}")
            b.setAccessibleDescription(f"{name}: choice {i + 1} of {len(choices)}")
            self.group.addButton(b, i)
            lay.addWidget(b)
            self.buttons.append(b)
            self._data.append(data)
        self._current = -1
        self.group.idToggled.connect(self._toggled)
        self.setCurrentIndex(current)
        keys = _SegmentKeys(self)
        for b in self.buttons:
            b.installEventFilter(keys)

    def count(self) -> int:
        return len(self.buttons)

    def currentIndex(self) -> int:
        return self._current

    def currentData(self) -> object:
        return self._data[self._current] if 0 <= self._current < len(self._data) else None

    def currentText(self) -> str:
        return self.buttons[self._current].text() if 0 <= self._current < len(self.buttons) else ""

    def itemText(self, index: int) -> str:
        return self.buttons[index].text()

    def setCurrentIndex(self, index: int) -> None:
        if not 0 <= index < len(self.buttons) or index == self._current:
            return
        self.buttons[index].setChecked(True)  # the group unchecks the others; _toggled emits

    def set_tip(self, index: int, tip: str, *, active: Callable[[], bool] | None = None) -> None:
        set_control_tooltip(self.buttons[index], tip, active=active)

    def _toggled(self, index: int, checked: bool) -> None:
        if checked and index != self._current:
            self._current = index
            self.currentIndexChanged.emit(index)

    def step(self, step: int) -> None:
        """Move the choice by ``step`` (Left and Right on a segment), keeping the focus on the chosen segment."""
        target = max(0, min(len(self.buttons) - 1, self._current + step))
        self.setCurrentIndex(target)
        self.buttons[target].setFocus(Qt.FocusReason.TabFocusReason)


class _SegmentKeys(QObject):
    """Left and Right on a segment move the choice (as a macOS segmented control does)."""

    def __init__(self, control: SegmentedControl) -> None:
        super().__init__(control)
        self.control = control

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.KeyPress and isinstance(event, QKeyEvent):
            step = {Qt.Key.Key_Left: -1, Qt.Key.Key_Right: 1}.get(Qt.Key(event.key()))
            if step is not None:
                self.control.step(step)
                return True
        return False


class Switch(QCheckBox):
    """On/off (rule 6): a check box drawn as a switch (keyboard, accessibility and ``isChecked`` are the check box's).
    Its label is the row's; it has no text of its own."""

    W: Final = 38
    H: Final = 22

    def __init__(self, *, name: str, parent: QWidget | None = None, checked: bool = False) -> None:
        super().__init__(parent)
        self.setAccessibleName(name)
        self.setChecked(checked)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:
        return QSize(self.W + 4, self.H + 4)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def hitButton(self, pos: QPoint) -> bool:
        return self.rect().contains(pos)

    def paintEvent(self, _event: QPaintEvent) -> None:
        t = theme.tokens()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        track = QRect(2, 2, self.W, self.H)
        on = self.isChecked()
        colour = QColor(t.switch_on if on else t.switch_off)
        if not self.isEnabled():
            colour.setAlpha(110)
        p.setPen(QColor(t.accent) if self.hasFocus() else Qt.PenStyle.NoPen)
        p.setBrush(colour)
        p.drawRoundedRect(track, self.H / 2, self.H / 2)
        knob = self.H - 4
        x = track.right() - knob - 1 if on else track.left() + 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(t.knob))
        p.drawEllipse(QRect(x, track.top() + 2, knob, knob))
        p.end()


@dataclass(frozen=True, slots=True)
class Choice:
    """One toggle of a :class:`ChipGroup` or :class:`Checklist`: its key (what the setting holds), its label, an
    optional grey detail (counts), its tip, and whether it can be chosen at all (a refused attack cannot)."""

    key: str
    label: str
    detail: str = ""
    tip: str = ""
    enabled: bool = True


class _ChoiceSet(QWidget):
    """Many toggles with one API: ``set_choices``, ``checked``, ``set_checked``, ``changed``."""

    changed = Signal()

    def __init__(self, *, name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAccessibleName(name)
        self.boxes: dict[str, QAbstractButton] = {}
        self.choices: list[Choice] = []

    def _make(self, choice: Choice) -> QAbstractButton:
        raise NotImplementedError

    def _place(self, widgets: list[QWidget]) -> None:
        raise NotImplementedError

    def set_choices(self, choices: Sequence[Choice], checked: Sequence[str] = ()) -> None:
        """Replace the toggles; ``checked`` are ticked (a disabled one never is). Emits nothing."""
        for w in self.findChildren(QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly):
            w.hide()
            w.deleteLater()
        self.boxes = {}
        self.choices = list(choices)
        widgets: list[QWidget] = []
        wanted = set(checked)
        for c in choices:
            b = self._make(c)
            b.setProperty(INPUT_PART, True)
            b.setEnabled(c.enabled)
            b.setChecked(c.enabled and c.key in wanted)
            if c.tip and c.enabled:
                set_control_tooltip(b, c.tip)
            elif c.tip:  # a disabled toggle's reason (a refused attack) is shown although it is disabled
                set_help_tooltip(b, c.tip)
            b.toggled.connect(lambda _on: self.changed.emit())
            self.boxes[c.key] = b
            holder = b.parentWidget()
            widgets.append(holder if holder is not None and holder is not self else b)
        self._place(widgets)

    def checked(self) -> list[str]:
        return [c.key for c in self.choices if self.boxes[c.key].isChecked()]

    def count(self) -> int:
        return len(self.choices)

    def set_checked(self, keys: Sequence[str]) -> None:
        """Tick exactly ``keys`` (the enabled ones); emits ``changed`` once."""
        wanted = set(keys)
        for c in self.choices:
            b = self.boxes[c.key]
            b.blockSignals(True)
            b.setChecked(c.enabled and c.key in wanted)
            b.blockSignals(False)
        self.changed.emit()

    def selectable(self) -> list[str]:
        return [c.key for c in self.choices if c.enabled]


class ChipGroup(_ChoiceSet):
    """Toggles as chips that wrap onto the next line (attacks)."""

    def __init__(self, *, name: str, parent: QWidget | None = None) -> None:
        super().__init__(name=name, parent=parent)
        self.flow = FlowLayout(self, spacing=6)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)

    def _make(self, choice: Choice) -> QAbstractButton:
        text = choice.label + (f" · {choice.detail}" if choice.detail else "")
        b = QPushButton(text, self)
        _role(b, "chip")
        b.setCheckable(True)
        b.setAutoDefault(False)
        b.setAccessibleName(choice.label)
        if choice.detail:
            b.setAccessibleDescription(choice.detail)
        return b

    def _place(self, widgets: list[QWidget]) -> None:
        for w in widgets:
            self.flow.addWidget(w)
        self.updateGeometry()


class Checklist(_ChoiceSet):
    """Toggles as check boxes in ``columns`` columns, each with its grey detail (suites with their task counts)."""

    def __init__(self, *, name: str, parent: QWidget | None = None, columns: int = 2) -> None:
        super().__init__(name=name, parent=parent)
        self.columns = columns
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(16)
        self.grid.setVerticalSpacing(6)
        for c in range(columns):
            self.grid.setColumnStretch(c, 1)

    def _make(self, choice: Choice) -> QAbstractButton:
        cell = QWidget(self)
        row = QHBoxLayout(cell)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        box = QCheckBox(choice.label, cell)
        box.setAccessibleName(choice.label)
        box.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        indicator = box.style().pixelMetric(QStyle.PixelMetric.PM_IndicatorWidth, None, box)
        box.setMinimumWidth(indicator + 12 + box.fontMetrics().horizontalAdvance(choice.label))  # its whole label
        row.addWidget(box)
        if choice.detail:
            detail = caption(choice.detail, name=f"{choice.label}: {choice.detail}", parent=cell)
            detail.setWordWrap(False)
            detail.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
            box.setAccessibleDescription(choice.detail)
            row.addWidget(detail)
        row.addStretch(1)
        return box

    def _place(self, widgets: list[QWidget]) -> None:
        for i, w in enumerate(widgets):
            self.grid.addWidget(w, i // self.columns, i % self.columns)


class FlowLayout(QLayout):
    """Items left to right, wrapping onto the next line (the chips)."""

    def __init__(self, parent: QWidget | None = None, *, spacing: int = 6) -> None:
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self._spacing = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item: QLayoutItem) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> QLayoutItem | None:
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int) -> QLayoutItem | None:
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self) -> Qt.Orientation:
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._arrange(QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._arrange(rect, apply=True)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        return size

    def _arrange(self, rect: QRect, *, apply: bool) -> int:
        x, y, line = rect.x(), rect.y(), 0
        for item in self._items:
            widget = item.widget()
            if widget is not None and widget.isHidden():
                continue
            hint = item.sizeHint()
            if x + hint.width() > rect.right() + 1 and line > 0:
                x, y, line = rect.x(), y + line + self._spacing, 0
            if apply:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self._spacing
            line = max(line, hint.height())
        return y + line - rect.y()


class OverflowBar(QWidget):
    """A toolbar of one line for a pane that can be narrow (the Viewer inspector's graph tools): the groups that do not
    fit move, from the end, behind **More** (a popup panel that holds the same widgets, one group a line), so each
    keeps its tooltip, shortcut, accessible name and state. More is shown only while something is behind it."""

    def __init__(self, *, name: str, more_name: str, more_tip: str, parent: QWidget | None = None,
                 spacing: int = 10) -> None:
        super().__init__(parent)
        self.setAccessibleName(name)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self._spacing = spacing
        self.groups: list[QWidget] = []
        self._shown = -1  # how many groups are in the line (the rest are behind More)
        self.row = QHBoxLayout(self)
        self.row.setContentsMargins(0, 0, 0, 0)
        self.row.setSpacing(spacing)
        self.row.addStretch(1)
        self.more = QToolButton(self)
        _role(self.more, "disclosure")
        self.more.setText("More")
        self.more.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.more.setArrowType(Qt.ArrowType.DownArrow)
        self.more.setIconSize(QSize(9, 9))
        self.more.setAccessibleName(more_name)
        set_control_tooltip(self.more, more_tip)
        self.more.clicked.connect(self.show_more)
        self.row.addWidget(self.more)
        self.panel = QFrame(self, Qt.WindowType.Popup)
        _role(self.panel, "card")
        self.panel.setAccessibleName(f"{name}: more")
        self.panel_rows = QVBoxLayout(self.panel)
        self.panel_rows.setContentsMargins(12, 10, 12, 10)
        self.panel_rows.setSpacing(8)

    def add(self, group: QWidget) -> QWidget:
        """Append ``group`` (a widget, often a row of controls that belong together) to the line."""
        self.groups.append(group)
        self.panel_rows.addWidget(group, 0, Qt.AlignmentFlag.AlignLeft)  # placed by _reflow
        self._shown = -1
        self._reflow(self.width())
        return group

    def overflowed(self) -> list[QWidget]:
        """The groups behind More."""
        return self.groups[max(self._shown, 0):]

    def sizeHint(self) -> QSize:
        width = sum(g.sizeHint().width() for g in self.groups) + self._spacing * max(0, len(self.groups) - 1)
        return QSize(width, self.minimumSizeHint().height())

    def minimumSizeHint(self) -> QSize:
        heights = [g.sizeHint().height() for g in self.groups[:max(self._shown, 0)]] + [self.more.sizeHint().height()]
        return QSize(self.more.sizeHint().width(), max(heights))

    def _fits(self, width: int) -> int:
        widths = [g.sizeHint().width() for g in self.groups]
        if sum(widths) + self._spacing * max(0, len(widths) - 1) <= width:
            return len(widths)
        room = width - self.more.sizeHint().width() - self._spacing
        used, count = 0, 0
        for w in widths:
            used += w + (self._spacing if count else 0)
            if used > room:
                break
            count += 1
        return count

    def _reflow(self, width: int) -> None:
        shown = self._fits(width)
        if shown == self._shown:
            return
        self._shown = shown
        for group in self.groups:
            self.row.removeWidget(group)
            self.panel_rows.removeWidget(group)
        for i, group in enumerate(self.groups):  # insertWidget and addWidget move a widget to its new parent
            if i < shown:
                self.row.insertWidget(i, group)
            else:
                self.panel_rows.addWidget(group, 0, Qt.AlignmentFlag.AlignLeft)
        self.more.setVisible(shown < len(self.groups))
        if self.panel.isVisible() and shown == len(self.groups):
            self.panel.hide()
        self.updateGeometry()

    def show_more(self) -> None:
        """Open the panel under More, right-aligned with it and kept on the screen; the focus goes to its first
        control (Esc or a click outside closes it)."""
        if not self.overflowed():
            return
        self.panel.adjustSize()
        below = self.more.mapToGlobal(QPoint(self.more.width() - self.panel.width(), self.more.height()))
        screen = self.screen().availableGeometry() if self.screen() is not None else None
        if screen is not None:
            below.setX(max(screen.left(), min(below.x(), screen.right() - self.panel.width())))
        self.panel.move(below)
        self.panel.show()
        self.panel.focusNextChild()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._reflow(event.size().width())

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._reflow(self.width())


# --------------------------------------------------------------------------------------------- numbers (rule 5)
class _Unset:
    """The sentinel convention of the number fields: the minimum means unset and shows the grey placeholder."""

    unit: str
    placeholder: str

    def _setup(self, spin: QAbstractSpinBox, placeholder: str, unit: str, name: str) -> None:
        spin.setAccessibleName(name)
        spin.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        spin.setProperty("apvRole", "number")  # the style sheet hides its arrows (NoButtons breaks its edit field)
        spin.setCorrectionMode(QAbstractSpinBox.CorrectionMode.CorrectToNearestValue)
        spin.setKeyboardTracking(True)
        spin.setFixedWidth(130)
        spin.lineEdit().setPlaceholderText(placeholder)
        self.unit = unit
        self.placeholder = placeholder


class IntField(QSpinBox, _Unset):
    """A short right-aligned whole number with its unit (rule 6). With ``unset`` (the default), the minimum of the
    range is the "not set" value: it shows ``placeholder`` (such as "Default (3)") in grey and :meth:`number` gives
    ``None``, so the option is left out of the command, exactly as the earlier "default" and "—" special values did."""

    def __init__(self, lo: int, hi: int, value: int | None = None, *, name: str, placeholder: str = "Default",
                 unit: str = "", unset: bool = True, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.unset = unset
        self.setRange(lo - 1 if unset else lo, hi)
        self._setup(self, placeholder, unit, name)
        self.setValue(value if value is not None else self.minimum())

    def number(self) -> int | None:
        """The value, ``None`` while unset."""
        return None if self.unset and self.value() == self.minimum() else self.value()

    def textFromValue(self, value: int) -> str:
        return "" if self.unset and value == self.minimum() else str(value)

    def valueFromText(self, text: str) -> int:
        stripped = text.strip().replace(",", "")
        if not stripped and self.unset:
            return self.minimum()
        try:
            return int(stripped)
        except ValueError:
            return self.minimum()

    def validate(self, text: str, pos: int) -> tuple[QValidator.State, str, int]:

        if not text.strip() and self.unset:
            return QValidator.State.Acceptable, text, pos
        return super().validate(text, pos)


class DecimalField(QDoubleSpinBox, _Unset):
    """A short right-aligned decimal with its unit; like :class:`IntField`, the minimum is "not set" when ``unset``.
    ``trim``: trailing zeros are not shown (``90`` rather than ``90.00``; the value keeps its decimals)."""

    def __init__(self, lo: float, hi: float, value: float | None = None, *, name: str, decimals: int = 2,
                 placeholder: str = "Default", unit: str = "", unset: bool = True, trim: bool = False,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.unset, self.trim = unset, trim
        self.setDecimals(decimals)
        self.setRange(lo, hi)
        self._setup(self, placeholder, unit, name)
        self.setValue(value if value is not None else self.minimum())

    def number(self) -> float | None:
        return None if self.unset and self.value() == self.minimum() else self.value()

    def textFromValue(self, value: float) -> str:
        if self.unset and value == self.minimum():
            return ""
        text = f"{value:.{self.decimals()}f}"
        return text.rstrip("0").rstrip(".") if self.trim and "." in text else text

    def valueFromText(self, text: str) -> float:
        stripped = text.strip().replace(",", "")
        if not stripped and self.unset:
            return self.minimum()
        try:
            return float(stripped)
        except ValueError:
            return self.minimum()

    def validate(self, text: str, pos: int) -> tuple[QValidator.State, str, int]:

        if not text.strip() and self.unset:
            return QValidator.State.Acceptable, text, pos
        return super().validate(text, pos)


# --------------------------------------------------------------------------------------------- paths
class _ElidedLineEdit(QLineEdit):
    """A line edit that shows a long path with its middle elided while it does not have the focus (the text itself,
    which the form reads, is never changed)."""

    def paintEvent(self, event: QPaintEvent) -> None:
        text = self.text()
        if self.hasFocus() or not text:
            super().paintEvent(event)
            return
        opt = QStyleOptionFrame()
        self.initStyleOption(opt)
        area = self.style().subElementRect(QStyle.SubElement.SE_LineEditContents, opt, self)
        area = area.adjusted(4, 0, -4, 0)
        metrics = self.fontMetrics()
        if metrics.horizontalAdvance(text) <= area.width():
            super().paintEvent(event)
            return
        p = QPainter(self)
        self.style().drawPrimitive(QStyle.PrimitiveElement.PE_PanelLineEdit, opt, p, self)
        p.setPen(self.palette().color(self.foregroundRole()))
        p.drawText(area, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                   metrics.elidedText(text, Qt.TextElideMode.ElideMiddle, area.width()))
        p.end()


class PathField(QWidget):
    """A path: the field (``edit``, middle-elided while not edited) and **Choose…** (a file or folder picker)."""

    def __init__(self, text: str = "", *, name: str, choose_name: str, folder: bool = False, placeholder: str = "",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAccessibleName(name)
        self.folder = folder
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.edit = _ElidedLineEdit(text, self)
        self.edit.setAccessibleName(name)
        self.edit.setMinimumWidth(60)
        self.edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        if placeholder:
            self.edit.setPlaceholderText(placeholder)
        lay.addWidget(self.edit, 1)
        self.button = QPushButton("Choose…", self)
        self.button.setAccessibleName(choose_name)
        self.button.setAutoDefault(False)
        self.button.clicked.connect(self.choose)
        set_control_tooltip(self.button, "Opens a " + ("folder" if folder else "file") + " picker; the choice fills "
                                         "the field.")
        lay.addWidget(self.button)
        self.setFocusProxy(self.edit)

    def text(self) -> str:
        return self.edit.text()

    def choose(self) -> None:
        start = self.edit.text().strip() or str(Path.home())
        if self.folder:
            chosen = QFileDialog.getExistingDirectory(self, self.accessibleName(), start)
        else:
            chosen = QFileDialog.getOpenFileName(self, self.accessibleName(), start)[0]
        if chosen:
            self.edit.setText(chosen)


# --------------------------------------------------------------------------------------------- status, results
class StatusBadge(SafeLabel):
    """Words with a tint (``ok``, ``warn``, ``bad``, ``info``, ``neutral``): the words carry the status, the colour
    only repeats it (never colour alone)."""

    KINDS: Final = ("ok", "warn", "bad", "info", "neutral")

    def __init__(self, text: str = "", *, name: str, kind: str = "neutral", parent: QWidget | None = None) -> None:
        super().__init__(text, name=name, parent=parent, selectable=False)
        self.setFont(theme.scaled_font("caption"))
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.kind = ""
        self.set_status(text, kind)

    def set_status(self, text: str, kind: str = "neutral") -> None:
        kind = kind if kind in self.KINDS else "neutral"
        self.set_plain(text)
        self.setVisible(bool(text))
        if kind != self.kind:
            self.kind = kind
            _role(self, f"badge-{kind}")
            theme.repolish(self)


class FactGrid(QWidget):
    """Two columns of facts (a grey name, a right-aligned value), as in the summary panel."""

    def __init__(self, *, name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAccessibleName(name)
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(12)
        self.grid.setVerticalSpacing(6)
        self.values: dict[str, SafeLabel] = {}
        self.names: dict[str, SafeLabel] = {}

    def set(self, key: str, value: str, *, label: str | None = None) -> None:
        """Set (or add) the fact ``key``; an empty value hides the row."""
        if key not in self.values:
            row = len(self.values)
            name = SafeLabel(label or key, name=label or key, parent=self, selectable=False)
            _role(name, "caption")
            val = SafeLabel("", name=f"{label or key} value", parent=self)
            val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            val.setWordWrap(True)
            val.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            self.grid.addWidget(name, row, 0)
            self.grid.addWidget(val, row, 1)
            self.grid.setColumnStretch(1, 1)
            self.names[key], self.values[key] = name, val
        if label is not None:
            self.names[key].set_plain(label)
        self.values[key].set_plain(value)
        self.names[key].setVisible(bool(value))
        self.values[key].setVisible(bool(value))

    def value(self, key: str) -> str:
        return self.values[key].text() if key in self.values else ""


def command_text(argv: Sequence[str], program: str = "agentprov") -> str:
    """One shell line: ``program`` and ``argv``, each argument quoted for a POSIX shell where it needs it."""
    return " ".join([program, *(shlex.quote(a) for a in argv)])


#: where a long argument may be broken over lines (after the character): path separators, spaces and the separators of
#: a ``key=value,…`` list; then, only for a path part longer than the line, after a hyphen, underscore or dot
_BREAKS: Final = ("/", "\\", " ", ",", "=")
_LAST_BREAKS: Final = ("-", "_", ".")


def _soft_break(unit: str, width: int) -> list[str]:
    """``unit`` in pieces of at most ``width`` characters, each ending at a path separator or a space where one falls
    inside the line (else after a hyphen, underscore or dot). Only a single word longer than the whole line with none
    of these is cut inside it (nothing else would fit)."""
    pieces: list[str] = []
    while len(unit) > width:
        cut = max(unit.rfind(ch, 1, width) for ch in _BREAKS)
        if cut <= 0:
            cut = max(unit.rfind(ch, 1, width) for ch in _LAST_BREAKS)
        if cut <= 0:
            cut = width - 1
        pieces.append(unit[:cut + 1])
        unit = unit[cut + 1:]
    pieces.append(unit)
    return pieces


def wrap_command(argv: Sequence[str], columns: int, program: str = "agentprov") -> str:
    """The command over several lines of at most ``columns`` characters (where an argument allows): arguments are
    joined with continuation backslashes, an option stays on the line of its value, and an argument longer than a line
    is broken softly after a path separator or at a space (shown on the next lines without a backslash), never inside a
    word unless one word is longer than the line. Display only: Copy takes :func:`command_text`."""
    columns = max(20, columns)
    words = [shlex.quote(a) for a in argv]
    units: list[str] = []
    i = 0
    while i < len(words):  # "--suite banking" stays together
        word = words[i]
        if word.startswith("-") and i + 1 < len(words) and not words[i + 1].startswith("-"):
            units.append(f"{word} {words[i + 1]}")
            i += 2
        else:
            units.append(word)
            i += 1
    indent = "  "
    head = _soft_break(program, columns - len(indent) - 2)  # a long program (New Job's interpreter) breaks the same way
    lines = [piece if k == 0 else indent + piece for k, piece in enumerate(head)]
    current = lines.pop()
    for unit in units:
        if len(current) + 1 + len(unit) + 2 <= columns:
            current += " " + unit
            continue
        lines.append(current + " \\")
        if len(indent + unit) + 2 <= columns:
            current = indent + unit
            continue
        pieces = _soft_break(unit, columns - len(indent) - 2)  # room for the next line's " \\"
        lines += [indent + piece for piece in pieces[:-1]]
        current = indent + pieces[-1]
    lines.append(current)
    return "\n".join(lines)


class CommandCard(QWidget):
    """The terminal command card: a small heading with **Copy**, then the commands in a dark monospace card, plain
    text, wrapped to the card's width (never a horizontal scroll). ``set_commands`` takes ``(comment, argv)`` pairs;
    a comment (such as "the quote") is printed as a ``#`` line above its command. Copy copies the commands as single
    lines (with their comments), exactly what the dialog would run. ``program``: the program the commands start with
    (default ``agentprov``; New Job gives the job's own, already quoted for a POSIX shell; a repository tool or the
    Zenodo uploader names its own).

    The wrap follows the width of the text itself: the card re-wraps whenever its text is resized or shown, so a card
    laid out on a hidden page (a Settings pane, a tab not yet opened) never keeps the width it had before it was
    shown, and the card's own resize (which comes before its text's) is not relied on."""

    def __init__(self, *, name: str = "Terminal command", title: str = "Terminal command",
                 parent: QWidget | None = None, program: str = "agentprov") -> None:
        super().__init__(parent)
        self.setAccessibleName(name)
        self.program = program
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        top = QHBoxLayout()
        top.addWidget(heading(title, parent=self), 1)
        self.copy_button = link_button("Copy", name="Copy the terminal command", parent=self)
        self.copy_button.clicked.connect(self.copy)
        set_control_tooltip(self.copy_button, "Copies the command shown below, one line per command, so it can be run "
                                              "in a terminal.")
        top.addWidget(self.copy_button)
        lay.addLayout(top)
        self.card = QFrame(self)
        _role(self.card, "code")
        inner = QVBoxLayout(self.card)
        inner.setContentsMargins(12, 10, 12, 10)
        self.body = SafeLabel("", name=f"{name} text", parent=self.card)
        _role(self.body, "code")
        self.body.setFont(theme.scaled_font("mono"))
        self.body.setWordWrap(True)
        self.body.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.body.setMinimumWidth(0)
        inner.addWidget(self.body)
        lay.addWidget(self.card)
        self.commands: list[tuple[str, tuple[str, ...]]] = []
        self.note = ""
        self._wrapped_at = -1  # the columns of the current wrap
        self.body.installEventFilter(self)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(lambda: self.copy_button.setText("Copy"))

    def set_commands(self, commands: Sequence[tuple[str, Sequence[str]]], *, note: str = "") -> None:
        """Show ``commands``; ``note`` (a reason there is none yet) is shown when the list is empty."""
        self.commands = [(c, tuple(a)) for c, a in commands]
        self.note = note
        self.copy_button.setEnabled(bool(self.commands))
        self._render()

    def columns(self) -> int:
        width = self.body.width() or (self.width() - 24)
        advance = max(1, self.body.fontMetrics().horizontalAdvance("M"))
        return max(20, width // advance - 1)

    def _render(self) -> None:
        columns = self.columns()
        self._wrapped_at = columns
        if not self.commands:
            self.body.set_plain(f"# {self.note}" if self.note else "")
            return
        parts = [("# " + c + "\n" if c else "") + wrap_command(argv, columns, self.program)
                 for c, argv in self.commands]
        self.body.set_plain("\n".join(parts))

    def plain(self) -> str:
        """What Copy copies: each command on one line, under its comment."""
        return "\n".join(("# " + c + "\n" if c else "") + command_text(argv, self.program)
                         for c, argv in self.commands)

    def copy(self) -> None:
        if not self.commands:
            return
        QGuiApplication.clipboard().setText(self.plain())
        self.copy_button.setText("Copied")
        self._timer.start(1500)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """Re-wrap when the text's width gives other columns (a resize, or the pending resize of a page shown for the
        first time)."""
        if (watched is self.body and event.type() in (QEvent.Type.Resize, QEvent.Type.Show)
                and self.columns() != self._wrapped_at):
            self._render()
        return False


class SummaryPanel(QScrollArea):
    """The right-hand panel (rule 8): what the choices add up to stays visible beside the form. A fixed-width column
    that scrolls vertically only when the window is too short; ``add`` appends a part, ``card`` a rounded card."""

    def __init__(self, *, name: str = "Summary", parent: QWidget | None = None, width: int = SUMMARY_WIDTH) -> None:
        super().__init__(parent)
        self.setAccessibleName(name)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFixedWidth(width)
        inner = QWidget(self)
        _role(inner, "summary")
        self.layout_ = QVBoxLayout(inner)
        self.layout_.setContentsMargins(20, 20, 20, 20)
        self.layout_.setSpacing(14)
        self.layout_.addStretch(1)
        self.setWidget(inner)
        self.inner = inner

    def add(self, widget: QWidget, *, after_stretch: bool = False) -> QWidget:
        """Append ``widget`` above the stretch (or, ``after_stretch``, at the bottom of the panel)."""
        if after_stretch:
            self.layout_.addWidget(widget)
        else:
            self.layout_.insertWidget(self._stretch_index(), widget)
        return widget

    def _stretch_index(self) -> int:
        for i in range(self.layout_.count()):
            item = self.layout_.itemAt(i)
            if item is not None and item.spacerItem() is not None:
                return i
        return self.layout_.count()

    def card(self, *, name: str) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame(self.inner)
        _role(frame, "card")
        frame.setAccessibleName(name)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(8)
        self.add(frame)
        return frame, lay
