"""D-1060: the theme of the one visual and form style: light and dark tokens, the type scale and the app-wide style
sheet built from them."""

from __future__ import annotations

from typing import Any

import pytest


def test_light_and_dark_tokens_define_every_colour_and_differ(qapp: Any) -> None:
    from agentprov_gui.ui import theme

    for t in (theme.LIGHT, theme.DARK):
        for name in theme.token_names():
            value = getattr(t, name)
            assert isinstance(value, str) and value.startswith("#") and len(value) == 7, name
    assert theme.LIGHT.window != theme.DARK.window and theme.LIGHT.text != theme.DARK.text
    assert theme.tokens(dark=True) is theme.DARK and theme.tokens(dark=False) is theme.LIGHT
    assert theme.TYPE == {"body": 13, "caption": 11, "heading": 11, "title": 20, "mono": 11} and theme.SPACE == 8


def test_the_style_sheet_is_built_from_the_tokens_and_applied_once(qapp: Any) -> None:
    from agentprov_gui.ui import theme

    light, dark = theme.stylesheet(theme.LIGHT), theme.stylesheet(theme.DARK)
    for t, sheet in ((theme.LIGHT, light), (theme.DARK, dark)):
        assert t.accent in sheet and t.card in sheet and t.code in sheet  # the default button, cards, the command card
        for selector in ("QPushButton:default", "QLineEdit", "QComboBox", "QCheckBox", "QHeaderView::section",
                         "QTabBar::tab", "QScrollArea", "QGroupBox", 'apvRole="card"'):
            assert selector in sheet, selector
    old = qapp.styleSheet()
    try:
        theme.apply_style(qapp, dark=True)
        assert qapp.styleSheet() == dark
        theme.apply_style(qapp, dark=False)
        assert qapp.styleSheet() == light
    finally:
        qapp.setStyleSheet(old)


def test_the_type_scale_follows_the_application_font(qapp: Any) -> None:
    from PySide6.QtGui import QFont

    from agentprov_gui.ui import theme

    base = QFont(qapp.font())
    base.setPointSizeF(13)
    assert theme.scaled_font("caption", base).pointSizeF() == pytest.approx(11)
    assert theme.scaled_font("title", base).pointSizeF() == pytest.approx(20)
    assert theme.scaled_font("heading", base).weight() == QFont.Weight.DemiBold
    bigger = QFont(base)
    bigger.setPointSizeF(26)  # View › Bigger scales captions too
    assert theme.scaled_font("caption", bigger).pointSizeF() == pytest.approx(22)


def test_the_app_sheet_is_set_with_the_collector_paused(qapp: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Qt re-styles every widget from its own list; a garbage collection started meanwhile from a Python event filter
    could delete a widget only Python held while Qt walks that list (a crash), so the collector waits."""
    import gc

    from agentprov_gui.ui import theme

    seen: list[bool] = []
    monkeypatch.setattr(gc, "isenabled", lambda: True)
    monkeypatch.setattr(gc, "disable", lambda: seen.append(False))
    monkeypatch.setattr(gc, "enable", lambda: seen.append(True))
    old = qapp.styleSheet()
    theme.set_app_sheet(qapp, old)
    assert seen == [False, True] and qapp.styleSheet() == old


def _contrast(a: str, b: str) -> float:
    def lum(h: str) -> float:
        def f(c: float) -> float:
            return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

        r, g, b_ = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
        return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b_)

    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_the_destructive_style_is_red_and_readable_in_both_schemes(qapp: Any) -> None:
    """A destructive button (Cancel Run…, Delete Key…, a prune) is red text and border, filled red as the default
    button; every pairing meets WCAG AA for text (4.5:1) in light and dark."""
    from PySide6.QtWidgets import QPushButton

    from agentprov_gui.ui import theme

    for t in (theme.LIGHT, theme.DARK):
        for background in (t.field, t.card, t.window, t.summary, t.danger_soft):  # its hover is danger_soft
            assert _contrast(t.danger, background) >= 4.5, (t.danger, background)
        for fill in (t.danger_fill, t.danger_pressed):
            assert _contrast("#FFFFFF", fill) >= 4.5, fill
        sheet = theme.stylesheet(t)
        assert 'QPushButton[apvRole="destructive"]' in sheet and t.danger_fill in sheet
    button = QPushButton("Delete Key…")
    theme.mark_destructive(button)
    assert button.property("apvRole") == "destructive"
    theme.mark_destructive(button, False)
    assert button.property("apvRole") == ""
