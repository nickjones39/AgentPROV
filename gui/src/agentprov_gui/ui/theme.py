"""Colour tokens and appearance (design §12; macos-design §4.2, §5; D-443, D-444).

* Chrome colours come from the ``QPalette`` (Light, Dark, the user's accent). "Follow system" is the default; Light
  and Dark force ``QStyleHints.setColorScheme`` (Qt ≥ 6.8).
* Status tokens pair a colour with a glyph and a word, so status never depends on colour alone.
* PROV graph colours: fills keep their W3C hue in both appearances (text on fills stays black, except the sink fill);
  strokes and edges switch to the measured dark variants on a dark canvas; the light "Accessible" palette (default)
  darkens the three relation colours under 3:1, and "W3C exact" restores ``render.style``'s values.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette

__all__ = ["ATTACK_GLYPH", "STATUS", "GraphPalette", "apply_scheme", "attack_tint", "graph_palette", "is_dark"]

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
