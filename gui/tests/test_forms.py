"""D-1060: the shared form components of the one visual and form style (:mod:`agentprov_gui.ui.forms`)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agentprov_gui.jobs.commands import FORMS, build_spec


def test_segmented_control_is_exclusive(qapp: Any) -> None:
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent

    from agentprov_gui.ui.forms import SegmentedControl

    seg = SegmentedControl([("Scripted", "s"), ("Real model", "r"), ("Other", "o")], name="Transport")
    seen: list[int] = []
    seg.currentIndexChanged.connect(seen.append)
    assert seg.currentIndex() == 0 and seg.currentData() == "s" and seg.buttons[0].isChecked()
    seg.buttons[1].click()
    assert seg.currentIndex() == 1 and [b.isChecked() for b in seg.buttons] == [False, True, False]
    seg.buttons[1].click()  # clicking the chosen segment keeps it chosen
    assert seg.currentIndex() == 1 and seg.buttons[1].isChecked()
    seg.setCurrentIndex(2)
    assert [b.isChecked() for b in seg.buttons] == [False, False, True] and seen == [1, 2]
    qapp.sendEvent(seg.buttons[2], QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Left, Qt.KeyboardModifier.NoModifier))
    assert seg.currentIndex() == 1 and seen == [1, 2, 1]
    assert seg.accessibleName() == "Transport" and all(b.accessibleName() for b in seg.buttons)
    with pytest.raises(ValueError):
        SegmentedControl(["one"], name="x")


def test_switch_state(qapp: Any) -> None:
    from agentprov_gui.ui.forms import Switch

    sw = Switch(name="Conformance check", checked=True)
    seen: list[bool] = []
    sw.toggled.connect(seen.append)
    assert sw.isChecked() and sw.accessibleName() == "Conformance check" and sw.text() == ""
    sw.click()
    assert not sw.isChecked() and seen == [False]
    sw.setEnabled(False)
    sw.grab()  # paints in both states without error
    sw.setChecked(True)
    sw.grab()
    assert sw.sizeHint().width() >= Switch.W


def test_disclosure_is_collapsed_by_default_and_remembers_per_screen(qapp: Any, tmp_path: Path) -> None:
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QWidget

    from agentprov_gui.ui.forms import Disclosure

    store = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    a = Disclosure("Advanced: concurrency", screen="run-live", key="advanced", store=store)
    a.add(QWidget())
    assert not a.is_open() and a.content.isHidden()
    a.button.click()
    assert a.is_open() and not a.content.isHidden()
    assert Disclosure("Advanced: concurrency", screen="run-live", key="advanced", store=store).is_open()
    assert not Disclosure("Advanced: x", screen="new-job", key="advanced", store=store).is_open()  # per screen
    a.button.click()
    assert not Disclosure("Advanced: concurrency", screen="run-live", key="advanced", store=store).is_open()
    memory = Disclosure("Tasks", screen="test-memory", key="tasks")  # without a store: this process only
    memory.set_open(True)
    assert Disclosure("Tasks", screen="test-memory", key="tasks").is_open()


def test_number_field_maps_unset_and_values_onto_the_same_argv(qapp: Any) -> None:
    """The earlier spin boxes' "default" and "—" special values left an option out; the field's grey placeholder
    means the same, so the CLI arguments do not change."""
    from agentprov_gui.ui.forms import DecimalField, IntField

    jobs = IntField(1, 512, None, name="Concurrent traces", placeholder="Default (1)", unit="traces")
    assert jobs.number() is None and jobs.text() == "" and jobs.lineEdit().placeholderText() == "Default (1)"
    assert jobs.unit == "traces" and jobs.alignment() & jobs.alignment().AlignRight
    run = FORMS["run"]
    base = {"source": "agentdojo", "corpus": "/tmp/c", "campaign": "t", "suite": "banking", "llm_script": "/tmp/s"}
    assert "--jobs" not in build_spec(run, {**base, "jobs": jobs.number()}).argv
    jobs.setValue(6)
    argv = build_spec(run, {**base, "jobs": jobs.number()}).argv
    assert argv[argv.index("--jobs") + 1] == "6" and jobs.text() == "6"
    jobs.lineEdit().setText("")  # clearing the field unsets it again
    jobs.interpretText()
    assert jobs.number() is None
    calls = IntField(1, 10_000_000, None, name="Max calls", placeholder="Not set")  # the old "—" at 0
    assert calls.minimum() == 0 and calls.value() == 0 and calls.number() is None
    timeout = DecimalField(0, 86_400, None, name="Cell timeout", placeholder="Default (1,800 s)", unit="seconds")
    assert timeout.number() is None and timeout.value() == 0 and timeout.text() == ""
    assert "--cell-timeout" not in build_spec(run, {**base, "cell_timeout": timeout.number()}).argv
    timeout.setValue(90)
    argv = build_spec(run, {**base, "cell_timeout": timeout.number()}).argv
    assert argv[argv.index("--cell-timeout") + 1] == "90.0"
    fixed = DecimalField(0, 100, 2.5, name="Price", unset=False)
    assert fixed.number() == 2.5


def test_chips_and_checklist(qapp: Any) -> None:
    from agentprov_gui.ui.forms import Checklist, ChipGroup, Choice

    for cls in (ChipGroup, Checklist):
        group = cls(name="Attacks")
        seen: list[int] = []
        group.changed.connect(lambda seen=seen: seen.append(1))
        group.set_choices([Choice("direct", "direct"), Choice("ours", "ours", tip="Refused: why", enabled=False),
                           Choice("tool", "tool", detail="DoS")], checked=["direct", "ours"])
        assert group.checked() == ["direct"] and group.selectable() == ["direct", "tool"] and not seen
        group.boxes["tool"].click()
        assert group.checked() == ["direct", "tool"] and seen
        group.set_checked(["ours", "tool"])  # a disabled toggle is never ticked
        assert group.checked() == ["tool"]
        assert all(b.accessibleName() for b in group.boxes.values())


def test_command_card_wraps_and_copies_the_exact_command(qapp: Any) -> None:
    from PySide6.QtGui import QGuiApplication

    from agentprov_gui.ui.forms import CommandCard, command_text, wrap_command

    argv = ("run", "--suite", "banking", "--llm-script", "/tmp/dir with space/" + "x" * 80 + ".json", "--campaign",
            "guide", "agentdojo")
    wrapped = wrap_command(argv, 40)
    lines = wrapped.splitlines()
    assert lines[0].startswith("agentprov run") and all(len(line) <= 40 for line in lines)
    assert "--suite banking" in wrapped  # an option stays with its value
    card = CommandCard()
    card.resize(300, 200)
    card.set_commands([("the run", argv)])
    assert card.body.text().startswith("# the run\nagentprov run")
    card.copy()
    assert QGuiApplication.clipboard().text() == "# the run\n" + command_text(argv)
    assert command_text(argv).count("'") == 2  # the path with a space is quoted once
    card.set_commands([], note="Name a campaign first.")
    assert card.body.text() == "# Name a campaign first." and not card.copy_button.isEnabled()


def test_command_wrap_breaks_at_separators_never_inside_a_word() -> None:
    from agentprov_gui.ui.forms import command_text, wrap_command

    path = "/Users/someone/Library/Application Support/agentprov/corpora/survey-agentdojo-2026/executions.jsonl"
    argv = ("validate", "--corpus", path, "--select", "suite=banking,attack=important_instructions", "--level", "chain")
    for columns in (24, 32, 40, 56, 80):
        wrapped = wrap_command(argv, columns)
        lines = wrapped.splitlines()
        assert all(len(line) <= columns for line in lines), (columns, wrapped)
        # every line ends at a separator, a space, the end of an argument or a continuation backslash: no word is cut
        for line in lines[:-1]:
            assert line.endswith((" \\", "/", " ", ",", "=", "-", "_", ".")), (columns, line)
            assert columns < 32 or line.endswith((" \\", "/", " ", ",", "=")), (columns, line)  # every part fits
        # the shown text is the copied command with the line breaks (and continuation backslashes) added
        joined = "".join(line.removesuffix(" \\").removeprefix("  ") if line.endswith(" \\")
                         else line.removeprefix("  ") for line in lines)
        assert joined.replace(" ", "") == command_text(argv).replace(" ", "")
    # a long program (New Job's interpreter) wraps the same way
    long_program = "/Applications/AgentPROV.app/Contents/Resources/python/bin/python3 -m agentprov"
    assert all(len(line) <= 30 for line in wrap_command(("info",), 30, long_program).splitlines())
    # only a word longer than the whole line, with nowhere to break, is cut inside it
    digest = "a" * 64
    assert all(len(line) <= 30 for line in wrap_command(("verify", digest), 30).splitlines())


def test_command_card_rewraps_when_a_hidden_page_is_first_shown(qapp: Any) -> None:
    """A card built and filled on a page hidden in a stack (a Settings pane) wraps to its real width once shown, not
    to the width its text had while hidden."""
    from PySide6.QtWidgets import QStackedWidget, QWidget

    from agentprov_gui.ui.forms import CommandCard, FormPage, wrap_command

    stack = QStackedWidget()
    stack.addWidget(QWidget())
    page = FormPage(name="Hidden pane")
    card = CommandCard(parent=page.column)
    page.add(card)
    stack.addWidget(page)
    argv = ("run", "--campaign", "a-long-campaign-name", "--llm-script", "/tmp/scripts/" + "folder/" * 8 + "s.json",
            "--suite", "banking", "--attack", "important_instructions", "agentdojo")
    card.set_commands([("", argv)])
    stack.resize(820, 600)
    stack.show()
    qapp.processEvents()
    stack.setCurrentWidget(page)
    for _ in range(3):
        qapp.processEvents()
    columns = card.columns()
    assert columns > 40  # the shown width, not a hidden label's
    assert card.body.text() == wrap_command(argv, columns)
    stack.resize(500, 600)
    for _ in range(3):
        qapp.processEvents()
    assert card.columns() < columns and card.body.text() == wrap_command(argv, card.columns())
    stack.close()


def test_form_page_never_scrolls_horizontally(qapp: Any) -> None:
    from PySide6.QtCore import Qt

    from agentprov_gui.ui.forms import COLUMN_MAX, FormPage, FormSection, PathField, StatusBadge, combo

    page = FormPage(name="Test form")
    section = FormSection("Long things", note="A note " * 40)
    box = combo(name="Backend")
    box.addItem("autodojo  (the backend environment autodojo-0123456789abcdef is not built; run agentprov backends "
                "build autodojo first)")
    section.add_row("Backend", box, caption_text="A caption that is long enough to wrap " * 6,
                    trailing=[StatusBadge("Partial support", name="Live status", kind="warn")])
    section.add_row("Script", PathField("/tmp/" + "very-long-folder-name/" * 12 + "script.json", name="Script",
                                        choose_name="Choose the script file"))
    page.add(section)
    page.resize(900, 500)
    page.show()
    qapp.processEvents()
    assert page.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert page.widget().minimumSizeHint().width() <= page.viewport().width()
    assert page.column.width() <= COLUMN_MAX
    page.resize(560, 500)  # narrower than the column: it shrinks with the window
    qapp.processEvents()
    assert page.widget().minimumSizeHint().width() <= page.viewport().width()
    page.close()


def test_rows_hide_with_their_hairline_and_badges_carry_words(qapp: Any) -> None:
    from PySide6.QtWidgets import QLineEdit

    from agentprov_gui.ui.forms import FormSection, StatusBadge

    section = FormSection("Model")
    a = section.add_row("Endpoint", QLineEdit(), tip="Sets --model")
    b = section.add_row("Model", QLineEdit())
    section.show()
    assert a.hairline.isHidden() and not b.hairline.isHidden()
    a.hide()
    assert b.hairline.isHidden()  # the first visible row has none
    b.hide()
    assert section.card.isHidden()  # no empty card
    assert a.label.buddy() is a.field and a.field.accessibleName() == "Endpoint"
    badge = StatusBadge("Ready", name="Readiness", kind="ok")
    assert badge.text() == "Ready" and badge.property("apvRole") == "badge-ok"
    badge.set_status("Blocked", "bad")
    assert badge.text() == "Blocked" and badge.property("apvRole") == "badge-bad"
    section.close()


def test_overflow_bar_moves_what_does_not_fit_behind_more(qapp: Any) -> None:
    """The groups that do not fit go, from the end, behind More (the same widgets, so their tooltips stay); a wide bar
    has nothing behind More and hides it."""
    from PySide6.QtWidgets import QPushButton, QWidget

    from agentprov_gui.ui.forms import OverflowBar
    from agentprov_gui.ui.safe import set_control_tooltip

    host = QWidget()
    bar = OverflowBar(name="Tools", more_name="More tools", more_tip="The tools there is no room for.", parent=host)
    buttons = []
    for i in range(8):
        b = QPushButton(f"Tool number {i}")
        set_control_tooltip(b, f"Does thing {i}.")
        buttons.append(bar.add(b))
    host.resize(1400, 60)
    bar.resize(1400, 40)
    host.show()
    qapp.processEvents()
    assert bar.overflowed() == [] and bar.more.isHidden()
    bar.resize(300, 40)
    qapp.processEvents()
    behind = bar.overflowed()
    assert behind and behind == buttons[len(buttons) - len(behind):] and not bar.more.isHidden()
    assert all(b.parentWidget() is bar.panel for b in behind)
    assert all(b.parentWidget() is bar for b in buttons[:len(buttons) - len(behind)])
    assert all(b.toolTip() for b in buttons) and bar.more.toolTip() and bar.more.accessibleName() == "More tools"
    bar.show_more()
    qapp.processEvents()
    assert bar.panel.isVisible()
    bar.resize(1400, 40)  # wide again: everything comes back into the line and the panel closes
    qapp.processEvents()
    assert bar.overflowed() == [] and bar.more.isHidden() and not bar.panel.isVisible()
    assert all(b.parentWidget() is bar for b in buttons)
    host.close()


def test_the_inspector_graph_tools_keep_search_in_view_and_overflow_the_rest(qapp: Any) -> None:
    """The Viewer inspector's graph tools: the search with Focus on one line, the others on a line whose groups that do
    not fit go behind More; every control keeps its tooltip wherever it is."""
    from agentprov_gui.ui.forms import OverflowBar
    from agentprov_gui.ui.graphview import GraphTab

    tab = GraphTab(None, narrow=True)
    tab.resize(320, 500)
    tab.show()
    qapp.processEvents()
    bar = tab.findChild(OverflowBar)
    assert bar is not None and bar.overflowed() and not bar.more.isHidden()
    assert tab.search.isVisible() and tab.focus_btn.isVisible() and tab.hops.isVisible()
    for control in (tab.cb_inf, tab.cb_assess, tab.evidence, tab.layout_choice, tab.cb_collapse, tab.content_cb,
                    tab.search, tab.focus_btn, tab.hops):
        assert control.toolTip(), control.accessibleName()
    tab.resize(1600, 500)
    qapp.processEvents()
    assert bar.overflowed() == [] and bar.more.isHidden()
    tab.close()
