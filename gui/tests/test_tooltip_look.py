"""The tooltip's look (D-1060): the application's tooltip filter gives Qt's tooltip label the current scheme's card
colour with a hairline border, rounded corners and a soft shadow on a translucent window, the text colour, the tooltip
font and padding, and a maximum width at which a long explanation wraps into a block; the text stays the escaped plain
text of :mod:`agentprov_gui.ui.safe` (S1). Placement is test_tooltip_placement's; the Show tooltips switch is
test_tooltip_setting's."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

LONG = ("Shows or hides the rest of this command's options, including the global options (logging, progress, the "
        "summary's failure list, stale locks). ") * 2


@pytest.fixture
def tip_filter(qapp: Any, monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    from PySide6.QtWidgets import QToolTip

    from agentprov_gui.ui import safe

    monkeypatch.setattr(safe, "pointer_scale", lambda: 1.0)
    f = safe.TooltipFilter(qapp)
    qapp.installEventFilter(f)
    yield f
    qapp.removeEventFilter(f)
    safe.set_tooltips_shown(True)
    QToolTip.hideText()
    qapp.processEvents()
    f.deleteLater()


@pytest.fixture
def button(qapp: Any) -> Iterator[Any]:
    from PySide6.QtWidgets import QPushButton

    b = QPushButton("Verify")
    b.resize(200, 40)
    b.show()
    qapp.processEvents()
    yield b
    b.hide()
    b.deleteLater()


def _show(qapp: Any, widget: Any, tip: str, *, literal: str = "") -> Any:
    """Hover ``widget`` whose tooltip is ``tip`` (an explanation) or ``literal`` (a value shown as one line), set
    through safe.py; returns the shown tooltip label."""
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QHelpEvent
    from PySide6.QtWidgets import QApplication, QToolTip

    from agentprov_gui.ui.safe import set_help_tooltip, set_tooltip

    if literal:
        set_tooltip(widget, literal)
    else:
        set_help_tooltip(widget, tip)
    QToolTip.hideText()
    qapp.processEvents()
    centre = widget.rect().center()
    QApplication.sendEvent(widget, QHelpEvent(QEvent.Type.ToolTip, centre, widget.mapToGlobal(centre)))
    qapp.processEvents()
    shown = [w for w in qapp.topLevelWidgets() if w.objectName() == "qtooltip_label" and w.isVisible()]
    assert shown, "no tooltip is showing"
    return shown[0]


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_the_tooltip_is_a_card_of_the_scheme(qapp: Any, tip_filter: Any, button: Any,
                                             monkeypatch: pytest.MonkeyPatch, dark: bool) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QPalette

    from agentprov_gui.ui import safe, theme

    monkeypatch.setattr(theme, "is_dark", lambda: dark)
    t = theme.tokens(dark)
    label = _show(qapp, button, "Runs verify (--level chain).")
    assert label.styleSheet() == safe.tip_style(t)
    assert label.palette().color(QPalette.ColorRole.WindowText) == QColor(t.text)
    assert label.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)  # the corners and shadow show through
    assert label.windowFlags() & Qt.WindowType.NoDropShadowWindowHint  # its own shadow, not the system's
    image = label.grab().toImage()
    ratio = image.devicePixelRatio()
    m = safe.TIP_SHADOW

    def pixel(x: float, y: float) -> QColor:
        return image.pixelColor(round(x * ratio), round(y * ratio))

    inside = pixel(m.left() + 3, label.height() / 2)  # the card's padding, left of the text
    assert inside.name() == QColor(t.card).name()
    assert pixel(0, 0).alpha() == 0  # outside the rounded corner: transparent
    assert 0 < pixel(label.width() / 2, label.height() - 2).alpha() < 80  # under the card: the soft shadow
    border = pixel(label.width() / 2, m.top())  # the hairline border's row
    assert border.name() != inside.name()


def test_the_font_and_padding(qapp: Any, tip_filter: Any, button: Any) -> None:
    from PySide6.QtWidgets import QApplication

    from agentprov_gui.ui import safe

    label = _show(qapp, button, "Short.")
    base = QApplication.font().pointSizeF()
    assert label.font().pointSizeF() == pytest.approx(base * safe.TIP_FONT_PX / 13)
    m, (pv, ph) = safe.TIP_SHADOW, safe.TIP_PADDING
    text = label.contentsRect()
    assert text.left() == m.left() + ph and text.top() == m.top() + pv
    assert label.width() - text.right() - 1 == m.right() + ph
    assert label.height() - text.bottom() - 1 == m.bottom() + pv


def test_a_long_explanation_wraps_at_the_maximum_width(qapp: Any, tip_filter: Any, button: Any) -> None:
    from agentprov_gui.ui import safe

    cap = safe.TIP_MAX_WIDTH + safe.TIP_SHADOW.left() + safe.TIP_SHADOW.right()
    short = _show(qapp, button, "Short.")
    short_size = short.size()
    assert short_size.width() < cap / 2  # a short tip stays a short line
    label = _show(qapp, button, LONG)
    assert cap - 60 < label.width() <= cap  # a block as wide as the maximum allows
    assert label.height() > 3 * short_size.height() - 2 * (safe.TIP_SHADOW.top() + safe.TIP_SHADOW.bottom())
    assert label.heightForWidth(label.width()) <= label.height()  # every wrapped line fits: nothing cut off


def test_text_that_cannot_wrap_keeps_its_width(qapp: Any, tip_filter: Any, button: Any) -> None:
    """A long id shown literally (safe_tooltip: its spaces do not break) is never cut at the maximum width."""
    from agentprov_gui.ui import safe

    label = _show(qapp, button, "", literal="sha256:" + "0123456789abcdef" * 4 + " " + "x" * 40)
    assert label.width() > safe.TIP_MAX_WIDTH
    assert label.width() >= label.minimumSizeHint().width()


def test_the_text_stays_plain(qapp: Any, tip_filter: Any, button: Any, hostile: list[str]) -> None:
    from PySide6.QtWidgets import QToolTip

    for value in hostile:
        label = _show(qapp, button, value)
        assert label.text() == button.toolTip() == QToolTip.text()
        assert label.text().startswith("<p>") and "<b>" not in label.text() and "<a " not in label.text()
        assert "<img" not in label.text()


def test_the_scheme_follows_a_change_of_appearance(qapp: Any, tip_filter: Any, button: Any,
                                                   monkeypatch: pytest.MonkeyPatch) -> None:
    from agentprov_gui.ui import safe, theme

    monkeypatch.setattr(theme, "is_dark", lambda: False)
    assert _show(qapp, button, "One.").styleSheet() == safe.tip_style(theme.LIGHT)
    monkeypatch.setattr(theme, "is_dark", lambda: True)
    assert _show(qapp, button, "Two.").styleSheet() == safe.tip_style(theme.DARK)


def test_no_tooltip_and_no_card_while_tooltips_are_off(qapp: Any, tip_filter: Any, button: Any) -> None:
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QHelpEvent
    from PySide6.QtWidgets import QApplication, QToolTip

    from agentprov_gui.ui import safe

    safe.set_control_tooltip(button, "Runs verify.")
    safe.set_tooltips_shown(False)
    QToolTip.hideText()
    qapp.processEvents()
    centre = button.rect().center()
    QApplication.sendEvent(button, QHelpEvent(QEvent.Type.ToolTip, centre, button.mapToGlobal(centre)))
    qapp.processEvents()
    assert not QToolTip.isVisible()
    safe.set_tooltips_shown(True)
    assert "verify" in _show(qapp, button, "Runs verify.").text()
