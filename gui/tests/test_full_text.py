"""Every dropdown and every shortened cell of the GUI can be read in full.

* :class:`forms.FullTextCombo` (every combo box of the app): its popup is at least as wide as its widest item, up to the
  screen's limit; an item wider than that has its whole text as its tooltip; the closed box, narrower than its text,
  shows the whole text first in its tooltip.
* :func:`safe.shortened_cell_tip` (the app-wide tooltip filter): a table, tree or list cell whose text is wider than the
  cell and that has no tooltip of its own shows its whole text.

All of these tooltips are the plain, escaped text :mod:`agentprov_gui.ui.safe` makes (S1), never escaped twice."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

SRC = Path(__file__).resolve().parents[1] / "src" / "agentprov_gui"
_TAGS = re.compile(r"</?p>|<br\s*/?>")


def _plain(tip: str) -> str:
    from PySide6.QtGui import QTextDocumentFragment

    assert tip.startswith("<p") and "<" not in _TAGS.sub("", tip), tip
    return QTextDocumentFragment.fromHtml(tip).toPlainText()


def test_every_combo_box_of_the_app_is_a_full_text_combo() -> None:
    """No screen builds a bare ``QComboBox``: each one is :class:`forms.FullTextCombo` (directly or through
    :func:`forms.combo`), so the popup fix reaches all of them."""
    offenders = [f"{p.relative_to(SRC)}:{n}" for p in SRC.rglob("*.py")
                 for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
                 if "QComboBox(" in line and "class FullTextCombo(QComboBox)" not in line]
    assert offenders == []


def test_combo_returns_a_full_text_combo(qapp: Any) -> None:
    from agentprov_gui.ui.forms import FullTextCombo, combo

    assert isinstance(combo(None, name="Choice"), FullTextCombo)


def test_the_popup_is_as_wide_as_its_widest_item(qapp: Any) -> None:
    from PySide6.QtWidgets import QWidget

    from agentprov_gui.ui.forms import combo

    host = QWidget()
    box = combo(host, name="Model id", minimum_chars=6)
    long = "a-provider/a-rather-long-model-identifier-that-the-closed-box-cannot-show-2026-10-28"
    box.addItems(["short", long])
    box.resize(90, box.sizeHint().height())
    host.show()
    qapp.processEvents()
    need = max(box.fontMetrics().horizontalAdvance(long), box.view().fontMetrics().horizontalAdvance(long))
    assert need < box.screen_limit()  # it fits on the screen: no tooltip needed
    box.showPopup()
    qapp.processEvents()
    view = box.view()
    assert view.width() >= need and view.minimumWidth() >= need
    assert view.minimumWidth() <= box.screen_limit()
    assert box.itemData(1, 3) is None  # ToolTipRole: the popup shows it whole
    box.hidePopup()
    host.close()


def test_the_viewer_evidence_filter_shows_every_choice_whole(qapp: Any) -> None:
    """The graph's evidence class filter ("All evidence", "Observed only" …): its popup is wider than each choice's
    text, measured in the box's own font (the macOS popup draws in it, with a checkmark column)."""
    from agentprov_gui.ui.forms import FullTextCombo
    from agentprov_gui.ui.graphview import GraphTab

    tab = GraphTab(None, narrow=True)
    tab.resize(320, 500)
    tab.show()
    qapp.processEvents()
    for box in (tab.evidence, tab.layout_choice, tab.hops):
        assert isinstance(box, FullTextCombo)
        widest = max(box.fontMetrics().horizontalAdvance(box.itemText(i)) for i in range(box.count()))
        assert box.popup_width() > widest
    tab.close()


def test_an_item_wider_than_the_screen_gets_its_whole_text_as_tooltip(qapp: Any, monkeypatch: Any) -> None:
    from PySide6.QtCore import Qt

    from agentprov_gui.ui.forms import FullTextCombo
    from agentprov_gui.ui.safe import set_combo_item_tooltip

    box = FullTextCombo()
    huge = "x" * 150 + " <b>not markup</b> & " + "y" * 150
    box.addItems(["short", huge, huge + " too"])
    set_combo_item_tooltip(box, 2, "The caller's note")
    monkeypatch.setattr(box, "screen_limit", lambda: 300)
    box.fit_popup()
    assert box.view().minimumWidth() == 300
    tip = Qt.ItemDataRole.ToolTipRole
    assert box.itemData(0, tip) is None
    assert _plain(box.itemData(1, tip)) == huge  # the whole text, escaped once (the markup shows as text)
    assert "&lt;b&gt;" in box.itemData(1, tip)
    third = _plain(box.itemData(2, tip))
    assert third.startswith(huge + " too") and third.endswith("The caller's note")  # the caller's tip kept after it
    # wide enough again: its own tooltips go and the caller's comes back
    monkeypatch.setattr(box, "screen_limit", lambda: 10_000)
    box.fit_popup()
    assert box.itemData(1, tip) is None
    assert _plain(box.itemData(2, tip)) == "The caller's note"
    # fitting twice does not stack the text
    monkeypatch.setattr(box, "screen_limit", lambda: 300)
    box.fit_popup()
    box.fit_popup()
    assert _plain(box.itemData(2, tip)).count(huge) == 1


def test_a_shortened_closed_box_shows_its_whole_text_first_in_its_tooltip(qapp: Any) -> None:
    from PySide6.QtWidgets import QWidget

    from agentprov_gui.ui.forms import combo
    from agentprov_gui.ui.safe import set_control_tooltip

    host = QWidget()
    box = combo(host, name="Benchmark version", minimum_chars=4)
    long = "a benchmark version label far longer than the closed box"
    box.addItems(["v1", long])
    set_control_tooltip(box, "Which benchmark version to run")
    box.setFixedWidth(80)
    host.show()
    qapp.processEvents()
    assert not box.text_shortened() and box.closed_tip() == box.toolTip()
    box.setCurrentIndex(1)
    assert box.text_shortened()
    assert _plain(box.closed_tip()) == f"{long} — Which benchmark version to run"
    assert box.toolTip() != box.closed_tip()  # the widget's own tooltip is unchanged
    host.close()


def _table(qapp: Any, text: str, width: int = 80) -> Any:
    from PySide6.QtWidgets import QTableWidget, QTableWidgetItem

    table = QTableWidget(1, 1)
    table.setItem(0, 0, QTableWidgetItem(text))
    table.horizontalHeader().setStretchLastSection(False)
    table.setColumnWidth(0, width)
    table.resize(300, 200)
    table.show()
    qapp.processEvents()
    return table


def test_a_shortened_cell_shows_its_whole_text(qapp: Any) -> None:
    from agentprov_gui import text as T
    from agentprov_gui.ui.safe import shortened_cell_tip

    shown = T.line("an execution id that is far too long for the column \x1b <i>x</i>", 200)
    table = _table(qapp, shown)
    pos = table.visualRect(table.model().index(0, 0)).center()
    tip = shortened_cell_tip(table.viewport(), pos)
    assert tip is not None and _plain(tip) == shown  # escaped once: the cell's own text, not re-escaped
    assert "<U+003C>" not in _plain(tip)
    assert shortened_cell_tip(table, pos) is None  # only the viewport answers
    table.item(0, 0).setToolTip("own")
    assert shortened_cell_tip(table.viewport(), pos) is None  # a cell with its own tooltip keeps it
    table.close()
    short = _table(qapp, "ok", 200)
    assert shortened_cell_tip(short.viewport(), short.visualRect(short.model().index(0, 0)).center()) is None
    short.close()


def test_the_tooltip_filter_shows_a_shortened_cell(qapp: Any) -> None:
    from PySide6.QtCore import QEvent, QPoint
    from PySide6.QtGui import QHelpEvent

    from agentprov_gui.ui.safe import TooltipFilter

    table = _table(qapp, "a value much wider than the eighty pixel column it sits in")
    pos = table.visualRect(table.model().index(0, 0)).center()
    event = QHelpEvent(QEvent.Type.ToolTip, pos, table.viewport().mapToGlobal(pos))
    tips = TooltipFilter()
    assert tips.eventFilter(table.viewport(), event) is True
    narrow_ok = QHelpEvent(QEvent.Type.ToolTip, QPoint(290, 190), table.viewport().mapToGlobal(QPoint(290, 190)))
    assert tips.eventFilter(table.viewport(), narrow_ok) is False  # no cell there: Qt answers as usual
    table.close()


def test_a_long_filter_value_is_whole_in_its_tooltip() -> None:
    from agentprov_gui.ui.viewer import value_full, value_label

    value = "suite/" + "z" * 120
    assert len(value_label("suite", value)) < len(value) and value_full("suite", value) == value
