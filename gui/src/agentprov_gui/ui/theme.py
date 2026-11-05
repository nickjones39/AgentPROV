"""Colour tokens and appearance (design §12; macos-design §4.2, §5; D-443, D-444).

* Chrome colours come from the ``QPalette`` (Light, Dark, the user's accent). "Follow system" is the default; Light
  and Dark force ``QStyleHints.setColorScheme`` (Qt ≥ 6.8).
* Status tokens pair a colour with a glyph and a word, so status never depends on colour alone.
* **Form style (D-1060):** :class:`Tokens` holds the palette of the one visual and form style for light and dark,
  :data:`TYPE` the type scale and :data:`SPACE` the 8 px grid; :func:`stylesheet` builds the one app-wide style sheet
  from them and :func:`apply_style` sets it on the application once at startup (again whenever the colour scheme
  changes). The form components of :mod:`agentprov_gui.ui.forms` take their colours from the same tokens.
* PROV graph colours: fills keep their W3C hue in both appearances (text on fills stays black, except the sink fill);
  strokes and edges switch to the measured dark variants on a dark canvas; the light "Accessible" palette (default)
  darkens the three relation colours under 3:1, and "W3C exact" restores ``render.style``'s values.
"""

from __future__ import annotations

import gc
from dataclasses import dataclass, fields
from typing import Final

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication, QWidget

__all__ = ["ATTACK_GLYPH", "SPACE", "STATUS", "TYPE", "GraphPalette", "Tokens", "apply_scheme", "apply_style",
           "attack_tint", "graph_palette", "is_dark", "mark_destructive", "set_app_sheet", "stylesheet", "tokens"]

#: Accessibility display flags (macOS: from NSWorkspace through the native layer; elsewhere all off).
ACCESS: dict[str, bool] = {"differentiate": False, "increase_contrast": False, "reduce_motion": False}

#: token -> (light, dark, glyph, word)
STATUS: Final[dict[str, tuple[str, str, str, str]]] = {
    "ok": ("#248A3D", "#30D158", "✓", "ok"),
    "sealed": ("#248A3D", "#30D158", "✓", "sealed"),
    "ok_with_issues": ("#C55300", "#FF9230", "!", "with issues"),
    "failed": ("#D70015", "#FF4245", "×", "failed"),
    "working": ("#0068D6", "#0091FF", "◐", "working"),
    "writing": ("#A16A00", "#FFD600", "✎", "being written"),
    "unreadable": ("#8E8E93", "#8E8E93", "?", "unreadable"),
}


def is_dark() -> bool:
    app = QGuiApplication.instance()
    if app is None:
        return False
    hints = QGuiApplication.styleHints()
    scheme = hints.colorScheme()
    if scheme == Qt.ColorScheme.Dark:
        return True
    if scheme == Qt.ColorScheme.Light:
        return False
    return QGuiApplication.palette().color(QPalette.ColorRole.Window).lightness() < 128


def apply_scheme(choice: str) -> None:
    """``system``, ``light`` or ``dark`` (Qt ≥ 6.8 ``setColorScheme``)."""
    hints = QGuiApplication.styleHints()
    scheme = {"light": Qt.ColorScheme.Light, "dark": Qt.ColorScheme.Dark}.get(choice, Qt.ColorScheme.Unknown)
    hints.setColorScheme(scheme)


#: D-706: the Viewer's mark for a row whose attack succeeded. Never colour alone: the glyph and the word go with the tint.
ATTACK_GLYPH: Final = "⚑"
#: (light, dark, high contrast light, high contrast dark): a soft red behind default text, readable in both schemes
_ATTACK_TINT: Final = ("#FBE3E4", "#4A2326", "#F5C2C5", "#6B2A30")


def attack_tint() -> QColor:
    """The row tint of a succeeded attack, for the current scheme (stronger under Increase Contrast)."""
    strong = ACCESS["increase_contrast"]
    return QColor(_ATTACK_TINT[(2 if strong else 0) + (1 if is_dark() else 0)])


def status_colour(token: str) -> QColor:
    light, dark, _, _ = STATUS.get(token, STATUS["unreadable"])
    return QColor(dark if is_dark() else light)


def status_text(token: str | None) -> str:
    if token is None:
        return ""
    _, _, glyph, word = STATUS.get(token, ("", "", "·", token))
    return f"{glyph} {word}"


# ----------------------------------------------------------------------------------------------- the PROV graph
_RELATION_LIGHT_W3C: Final = {
    "wasGeneratedBy": "#006400", "used": "#8B0000", "wasAttributedTo": "#FED37F", "wasAssociatedWith": "#FED37F",
    "actedOnBehalfOf": "#FED37F", "wasInfluencedBy": "#BEBEBE",
}  # fmt: skip
_RELATION_LIGHT_ACCESSIBLE: Final = {
    **_RELATION_LIGHT_W3C, "wasAttributedTo": "#B8860B", "wasAssociatedWith": "#B8860B", "actedOnBehalfOf": "#B8860B",
    "wasInfluencedBy": "#7F7F7F",
}  # fmt: skip
_RELATION_DARK: Final = {
    "wasGeneratedBy": "#5CC85C", "used": "#FF7A7A", "wasAttributedTo": "#E8C46A", "wasAssociatedWith": "#E8C46A",
    "actedOnBehalfOf": "#E8C46A", "wasInfluencedBy": "#B0B0B0",
}  # fmt: skip


@dataclass(frozen=True, slots=True)
class GraphPalette:
    canvas: str
    text_on_fill: str
    other_relation: str
    relations: dict[str, str]
    inference: str
    assessment: str
    ghost: str
    activity_border: str
    entity_border: str
    agent_border: str
    selection: str
    dim_alpha: int = 40

    def relation(self, name: str, kind: str | None) -> str:
        if kind == "inference":
            return self.inference
        if kind == "assessment":
            return self.assessment
        return self.relations.get(name, self.other_relation)


def graph_palette(*, dark: bool, exact: bool = False, canvas_light_paper: bool = False) -> GraphPalette:
    accent = QGuiApplication.palette().color(QPalette.ColorRole.Highlight).name() if QGuiApplication.instance() else "#0A84FF"
    if dark and not canvas_light_paper:
        return GraphPalette("#1E1E1E", "#000000", "#E6E6E6", dict(_RELATION_DARK), "#B994E6", "#E8925F", "#9A9A9A",
                            "#8FA6FF", "#B0B0B0", "#E8C46A", accent)
    relations = dict(_RELATION_LIGHT_W3C if exact else _RELATION_LIGHT_ACCESSIBLE)
    return GraphPalette("#FFFFFF", "#000000", "#000000", relations, "#6A3D9A", "#B15928",
                        "#999999" if exact else "#7A7A7A", "#0000FF", "#808080", "#B08A3C", accent)


# ----------------------------------------------------------------------------------------- the form style (D-1060)
@dataclass(frozen=True, slots=True)
class Tokens:
    """The palette of the one visual and form style (the style guide's nine rules). Every colour of the style sheet and
    of the form components comes from here; :func:`tokens` picks the light or the dark set from the appearance."""

    window: str  # the page behind the cards
    card: str  # a section's rounded card
    card_border: str
    hairline: str  # between the rows of a card
    text: str
    secondary: str  # summary lines
    caption: str  # grey captions, units and section headings
    field: str  # an input's background
    field_border: str
    disabled: str  # disabled text
    hover: str  # a plain button under the pointer
    pressed: str
    accent: str  # the default button, focus, a chosen chip's border
    accent_pressed: str
    accent_text: str  # text on the accent
    accent_soft: str  # a chosen chip's background
    link: str  # link-style buttons (Copy, Show the plan by suite)
    segment: str  # a segmented control's track
    segment_on: str  # its chosen segment
    summary: str  # the right-hand summary panel and the footer
    code: str  # the terminal command card
    code_text: str
    switch_on: str
    switch_off: str
    knob: str
    ok_bg: str
    ok_fg: str
    warn_bg: str
    warn_fg: str
    bad_bg: str
    bad_fg: str
    info_bg: str
    info_fg: str
    neutral_bg: str
    neutral_fg: str
    danger: str  # a destructive button's text and border (Cancel Run…, Delete Key…); at least 4.5:1 on field and hover
    danger_soft: str  # its background under the pointer
    danger_fill: str  # a destructive default button's background (white text on it, at least 4.5:1)
    danger_pressed: str


LIGHT: Final = Tokens(
    window="#ECECEC", card="#FFFFFF", card_border="#DCDCDE", hairline="#ECECEE", text="#1D1D1F", secondary="#3A3A3C",
    caption="#6E6E73", field="#FFFFFF", field_border="#C8C8CC", disabled="#8E8E93", hover="#F2F2F4", pressed="#E4E4E7",
    accent="#0071E3", accent_pressed="#0058B0", accent_text="#FFFFFF", accent_soft="#E8F1FD", link="#0063D1",
    segment="#E3E3E6", segment_on="#FFFFFF", summary="#F6F6F7", code="#1D1D1F", code_text="#F5F5F7",
    switch_on="#34C759", switch_off="#D1D1D6", knob="#FFFFFF", ok_bg="#DCF5E1", ok_fg="#1D6B2F", warn_bg="#FFF1D6",
    warn_fg="#8A5300", bad_bg="#FDE2DF", bad_fg="#A1261B", info_bg="#E8F1FD", info_fg="#0058B0", neutral_bg="#ECECEE",
    neutral_fg="#3A3A3C", danger="#C41E16", danger_soft="#FDE2DF", danger_fill="#C41E16", danger_pressed="#A0150F",
)  # fmt: skip
DARK: Final = Tokens(
    window="#1E1E1E", card="#2A2A2C", card_border="#3A3A3C", hairline="#38383A", text="#F5F5F7", secondary="#D1D1D6",
    caption="#98989D", field="#1C1C1E", field_border="#4A4A4E", disabled="#6E6E73", hover="#363638", pressed="#424245",
    accent="#0A84FF", accent_pressed="#0060DF", accent_text="#FFFFFF", accent_soft="#12355E", link="#4DA3FF",
    segment="#3A3A3C", segment_on="#636366", summary="#232325", code="#0D0D0F", code_text="#F5F5F7",
    switch_on="#30D158", switch_off="#48484A", knob="#FFFFFF", ok_bg="#17361F", ok_fg="#6FDC8C", warn_bg="#46350F",
    warn_fg="#FFCC66", bad_bg="#4A1C19", bad_fg="#FF8A80", info_bg="#12355E", info_fg="#8CC4FF", neutral_bg="#3A3A3C",
    neutral_fg="#D1D1D6", danger="#FF6B63", danger_soft="#4A1C19", danger_fill="#B92C26", danger_pressed="#9A221D",
)  # fmt: skip

#: the type scale in pixels at the default text size: body text and labels, captions, section headings, page titles,
#: the terminal command card (the system font throughout; the command card's is the fixed-pitch system font)
TYPE: Final = {"body": 13, "caption": 11, "heading": 11, "title": 20, "mono": 11}
#: the spacing grid (px); rows, cards and sections use multiples of it
SPACE: Final = 8


def tokens(dark: bool | None = None) -> Tokens:
    """The light or dark tokens; ``None``: the current appearance (:func:`is_dark`)."""
    return DARK if (is_dark() if dark is None else dark) else LIGHT


def scaled_font(role: str, base: QFont | None = None) -> QFont:
    """The application font scaled to ``role`` of :data:`TYPE` (relative to the 13 px body, so View › Bigger and
    Smaller still scale it); headings and titles are semibold, ``mono`` is the fixed-pitch system font."""
    from PySide6.QtGui import QFontDatabase

    reference = QFont(base) if base is not None else QApplication.font()
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont) if role == "mono" else QFont(reference)
    size = reference.pointSizeF()
    if size > 0:
        font.setPointSizeF(max(7.0, size * TYPE.get(role, TYPE["body"]) / TYPE["body"]))
    if role in ("heading", "title"):
        font.setWeight(QFont.Weight.DemiBold)
    return font


def stylesheet(t: Tokens) -> str:
    """The one app-wide style sheet (D-1060) from the tokens: buttons (the default one blue; a destructive one, marked
    by :func:`mark_destructive`, red: red text and border, filled red when it is the default), inputs, combo boxes,
    check boxes, tables and their headers, tabs, scroll areas and group boxes as cards; the form components' parts are
    selected by their ``apvRole`` property. Sizes follow the 8 px grid; fonts stay the application's (the components
    scale theirs from it), so View › Bigger and Smaller keep working."""
    badge = "border-radius: 8px; padding: 1px 8px;"
    return f"""
QPushButton {{ color: {t.text}; background: {t.field}; border: 1px solid {t.field_border}; border-radius: 6px;
    padding: 4px 14px; min-height: 16px; }}
QPushButton:hover {{ background: {t.hover}; }}
QPushButton:pressed {{ background: {t.pressed}; }}
QPushButton:focus {{ border: 1px solid {t.accent}; }}
QPushButton:disabled {{ color: {t.disabled}; }}
QPushButton:default, QPushButton[apvRole="primary"] {{ color: {t.accent_text}; background: {t.accent};
    border: 1px solid {t.accent}; }}
QPushButton:default:pressed, QPushButton[apvRole="primary"]:pressed {{ background: {t.accent_pressed}; }}
QPushButton:default:disabled, QPushButton[apvRole="primary"]:disabled {{ color: {t.accent_text};
    background: {t.field_border}; border-color: {t.field_border}; }}
QPushButton[apvRole="destructive"] {{ color: {t.danger}; border: 1px solid {t.danger}; }}
QPushButton[apvRole="destructive"]:hover {{ background: {t.danger_soft}; }}
QPushButton[apvRole="destructive"]:pressed {{ background: {t.danger_soft}; }}
QPushButton[apvRole="destructive"]:disabled {{ color: {t.disabled}; border: 1px solid {t.field_border}; }}
QPushButton[apvRole="destructive"]:default {{ color: #FFFFFF; background: {t.danger_fill};
    border: 1px solid {t.danger_fill}; }}
QPushButton[apvRole="destructive"]:default:pressed {{ background: {t.danger_pressed}; }}
QPushButton[apvRole="destructive"]:default:disabled {{ color: #FFFFFF; background: {t.field_border};
    border-color: {t.field_border}; }}
QPushButton[apvRole="destructive"]:focus {{ border: 1px solid {t.accent}; }}
QPushButton[apvRole="link"] {{ color: {t.link}; background: transparent; border: none; padding: 0px 2px; }}
QPushButton[apvRole="link"]:disabled {{ color: {t.disabled}; }}
QPushButton[apvRole="link"]:focus {{ text-decoration: underline; }}
QPushButton[apvRole="segment"] {{ color: {t.text}; background: transparent; border: 1px solid transparent;
    border-radius: 5px; padding: 3px 14px; }}
QPushButton[apvRole="segment"]:checked {{ background: {t.segment_on}; border: 1px solid {t.card_border}; }}
QPushButton[apvRole="segment"]:focus {{ border: 1px solid {t.accent}; }}
QPushButton[apvRole="chip"] {{ color: {t.text}; background: {t.field}; border: 1px solid {t.field_border};
    border-radius: 11px; padding: 2px 10px; }}
QPushButton[apvRole="chip"]:checked {{ color: {t.info_fg}; background: {t.accent_soft}; border: 1px solid {t.accent}; }}
QPushButton[apvRole="chip"]:focus {{ border: 1px solid {t.accent}; }}
QPushButton[apvRole="chip"]:disabled {{ color: {t.disabled}; background: transparent; }}
QToolButton[apvRole="disclosure"] {{ color: {t.secondary}; background: transparent; border: none; padding: 2px 4px; }}
QToolButton[apvRole="disclosure"]:focus {{ color: {t.accent}; }}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{ color: {t.text}; background: {t.field};
    border: 1px solid {t.field_border}; border-radius: 6px; padding: 3px 6px; min-height: 16px;
    selection-background-color: {t.accent}; selection-color: {t.accent_text}; }}
QSpinBox[apvRole="number"]::up-button, QSpinBox[apvRole="number"]::down-button,
QDoubleSpinBox[apvRole="number"]::up-button, QDoubleSpinBox[apvRole="number"]::down-button {{ width: 0px;
    border: none; }}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border: 1px solid {t.accent}; }}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {{ color: {t.disabled}; }}
QComboBox QAbstractItemView {{ color: {t.text}; background: {t.card}; selection-background-color: {t.accent};
    selection-color: {t.accent_text}; }}
QCheckBox, QRadioButton {{ color: {t.text}; spacing: 6px; }}
QCheckBox:disabled, QRadioButton:disabled {{ color: {t.disabled}; }}
QGroupBox {{ color: {t.text}; background: {t.card}; border: 1px solid {t.card_border}; border-radius: 10px;
    margin-top: 20px; padding: 10px 8px 8px 8px; }}
QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left; left: 10px; padding: 0px 2px;
    color: {t.caption}; }}
QHeaderView::section {{ color: {t.caption}; background: {t.summary}; border: none;
    border-bottom: 1px solid {t.hairline}; border-right: 1px solid {t.hairline}; padding: 4px 8px; }}
QTableView, QTreeView, QListView {{ color: {t.text}; background: {t.card}; border: 1px solid {t.card_border};
    gridline-color: {t.hairline}; alternate-background-color: {t.summary}; }}
QListView[apvRole="stepper"] {{ background: transparent; border: none; }}
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ color: {t.secondary}; background: transparent; border: none; border-bottom: 2px solid transparent;
    padding: 5px 14px; }}
QTabBar::tab:selected {{ color: {t.text}; border-bottom: 2px solid {t.accent}; }}
QTabBar::tab:hover {{ color: {t.text}; }}
QScrollArea {{ background: transparent; border: none; }}
QWidget[apvRole="page"] {{ background: {t.window}; }}
QWidget[apvRole="column"] {{ background: transparent; }}
QFrame[apvRole="card"] {{ background: {t.card}; border: 1px solid {t.card_border}; border-radius: 10px; }}
QFrame[apvRole="hairline"] {{ background: {t.hairline}; border: none; }}
QWidget[apvRole="summary"] {{ background: {t.summary}; }}
QWidget[apvRole="footer"] {{ background: {t.summary}; }}
QFrame[apvRole="segments"] {{ background: {t.segment}; border: none; border-radius: 7px; }}
QFrame[apvRole="code"] {{ background: {t.code}; border: none; border-radius: 8px; }}
QLabel[apvRole="caption"], QLabel[apvRole="heading"], QLabel[apvRole="unit"] {{ color: {t.caption}; }}
QLabel[apvRole="secondary"] {{ color: {t.secondary}; }}
QLabel[apvRole="code"] {{ color: {t.code_text}; background: transparent; }}
QLabel[apvRole="badge-ok"] {{ color: {t.ok_fg}; background: {t.ok_bg}; {badge} }}
QLabel[apvRole="badge-warn"] {{ color: {t.warn_fg}; background: {t.warn_bg}; {badge} }}
QLabel[apvRole="badge-bad"] {{ color: {t.bad_fg}; background: {t.bad_bg}; {badge} }}
QLabel[apvRole="badge-info"] {{ color: {t.info_fg}; background: {t.info_bg}; {badge} }}
QLabel[apvRole="badge-neutral"] {{ color: {t.neutral_fg}; background: {t.neutral_bg}; {badge} }}
"""


def apply_style(app: QApplication, *, dark: bool | None = None) -> None:
    """Set the app-wide style sheet (D-1060) once at startup; it is rebuilt whenever the colour scheme changes (the
    Appearance setting, or the system's while the setting follows it). ``dark`` forces one set (tests)."""
    set_app_sheet(app, stylesheet(tokens(dark)))
    if dark is None and not app.property("apvStyleHooked"):
        app.setProperty("apvStyleHooked", True)
        QGuiApplication.styleHints().colorSchemeChanged.connect(lambda _s: set_app_sheet(app, stylesheet(tokens())))


def set_app_sheet(app: QApplication, sheet: str) -> None:
    """``app.setStyleSheet(sheet)`` with Python's cyclic garbage collector paused: Qt re-styles every widget from its
    own list of them, and the event filters written in Python that this calls could otherwise start a collection that
    deletes a widget only Python held (a closed dialog in a reference cycle) while Qt is still walking that list."""
    paused = gc.isenabled()
    gc.disable()
    try:
        app.setStyleSheet(sheet)
    finally:
        if paused:
            gc.enable()


def mark_destructive(button: QWidget, on: bool = True) -> None:
    """Show ``button`` in the destructive style (red) or, ``on`` false, in the plain one. For actions that delete,
    cancel for good or undo (Cancel Run…, Force Kill…, Delete Key…, Remove Override, prune, purge, rollback); the
    button's words still say what it does, the colour only repeats it."""
    role = "destructive" if on else ""
    if (button.property("apvRole") or "") != role:
        button.setProperty("apvRole", role)
        repolish(button)


def repolish(widget: QWidget) -> None:
    """Re-apply the style sheet to ``widget`` after its ``apvRole`` property changed."""
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


def token_names() -> tuple[str, ...]:
    """Every token's name (the light and dark sets define all of them)."""
    return tuple(f.name for f in fields(Tokens))
