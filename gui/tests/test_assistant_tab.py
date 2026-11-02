"""D-1040: Help › Assistant opens as a tab of the main window beside the page it is about.

The page tab keeps the page chosen in the sidebar; the Assistant tab opens once, comes to the front when asked for again,
closes with its × or ⌘W, and keeps its conversation through switching, closing and reopening. The Assistant's CLI is a
fake caller (no model, no network)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from test_help_pages import FakeCli, _reply, wait


@pytest.fixture
def win(qapp: Any, tmp_path: Path) -> Any:
    from PySide6.QtCore import QSettings

    from agentprov_gui.settings import Settings
    from agentprov_gui.ui.mainwindow import MainWindow

    settings = Settings(QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    w = MainWindow(settings, cache_dir=tmp_path / "layout", home=tmp_path / "home")
    w.assistant.cli = FakeCli({"assistant.endpoint": "openai", "assistant.model": "m"}, _reply("Run agentprov verify."))
    w.assistant.reload()
    wait(qapp, lambda: w.assistant.ready)
    yield w
    w.close()


def _row(w: Any) -> str:
    return str(w.sidebar.currentItem().text())


def _menu_action(w: Any, text: str) -> Any:
    from PySide6.QtGui import QAction

    return next(a for a in w.findChildren(QAction) if a.text() == text)


def _chat(qapp: Any, w: Any, question: str) -> None:
    w.assistant.input.setPlainText(question)
    w.assistant.send()
    wait(qapp, lambda: not w.assistant.busy)


def test_the_window_has_one_tab_and_no_tab_bar_until_the_assistant_opens(win: Any) -> None:
    assert win.tabs.count() == 1 and win.tabs.widget(0) is win.pages
    assert win.tabs.tabBarAutoHide() and win.tabs.tabText(0) == "Viewer"
    assert win.tabs.indexOf(win.assistant) < 0
    assert win.pages.indexOf(win.assistant) < 0, "the Assistant is a tab, not a page of the stack"
    assert win.tabs.tabBar().tabButton(0, win.tabs.tabBar().ButtonPosition.RightSide) is None
    assert win.tabs.tabBar().tabButton(0, win.tabs.tabBar().ButtonPosition.LeftSide) is None


@pytest.mark.parametrize("how", ["go", "menu", "sidebar", "shortcut"])
def test_opening_the_assistant_adds_its_tab_beside_the_page(win: Any, how: str) -> None:
    win.go("Runs")
    if how == "go":
        win.go("Assistant")
    elif how == "menu":
        _menu_action(win, "Ask the Assistant").trigger()
    elif how == "sidebar":
        row = next(i for i in range(win.sidebar.count()) if win.sidebar.item(i).text() == "Assistant")
        win.sidebar.setCurrentRow(row)
    else:
        go = _menu_action(win, "Assistant")  # Go › Assistant
        assert go.shortcut().toString() == "Ctrl+8"
        go.trigger()
    assert win.tabs.count() == 2 and win.tabs.currentWidget() is win.assistant
    assert win.tabs.tabText(0) == "Runs" and win.tabs.tabText(1) == "Assistant"
    assert win.pages.currentWidget() is win.runs, "the page tab keeps the page the user came from"
    assert _row(win) == "Assistant"


def test_opening_it_again_brings_the_same_tab_to_the_front(win: Any) -> None:
    win.go("Assistant")
    win.go("Package")
    assert win.tabs.currentWidget() is win.pages and win.tabs.count() == 2
    for _ in range(3):
        _menu_action(win, "Ask the Assistant").trigger()
        win.go("Assistant")
    assert win.tabs.count() == 2 and win.tabs.currentWidget() is win.assistant
    assert [win.tabs.widget(i) for i in range(win.tabs.count())] == [win.pages, win.assistant]


def test_switching_between_the_chat_and_the_page_keeps_both(qapp: Any, win: Any) -> None:
    win.go("Logs")
    win.go("Assistant")
    _chat(qapp, win, "How do I verify a corpus?")
    shown = win.assistant.transcript.toPlainText()
    assert "Run agentprov verify." in shown and len(win.assistant.messages) == 2
    win.assistant.input.setPlainText("an unsent draft")
    win.tabs.setCurrentIndex(0)  # a click on the page tab
    assert win.pages.currentWidget() is win.logs and _row(win) == "Logs"
    win.go("Runs")  # another page: still in the page tab
    assert win.tabs.currentIndex() == 0 and win.tabs.tabText(0) == "Runs" and win.tabs.count() == 2
    win.tabs.setCurrentIndex(1)  # a click on the Assistant tab
    assert win.tabs.currentWidget() is win.assistant and _row(win) == "Assistant"
    assert win.assistant.transcript.toPlainText() == shown and len(win.assistant.messages) == 2
    assert win.assistant.input.toPlainText() == "an unsent draft"
    _chat(qapp, win, "And then?")
    assert len(win.assistant.messages) == 4, "the follow-up carries the earlier turns"
    assert "How do I verify a corpus?" in win.assistant.transcript.toPlainText()


def test_next_and_previous_tab_switch_between_the_page_and_the_assistant(win: Any) -> None:
    win.go("Runs")
    win.go("Assistant")
    win.action_map["previousTab"].trigger()
    assert win.tabs.currentIndex() == 0 and win.pages.currentWidget() is win.runs
    win.action_map["nextTab"].trigger()
    assert win.tabs.currentWidget() is win.assistant
    win.action_map["nextTab"].trigger()  # wraps
    assert win.tabs.currentIndex() == 0


def test_next_tab_in_the_viewer_still_steps_its_execution_tabs(win: Any) -> None:
    win.go("Assistant")
    win.go("Viewer")
    stepped: list[int] = []
    win.viewer.step_tab = stepped.append
    win.action_map["nextTab"].trigger()
    assert stepped == [1] and win.tabs.currentIndex() == 0


@pytest.mark.parametrize("how", ["close-tab", "tab-x"])
def test_closing_the_tab_keeps_the_window_and_reopening_keeps_the_chat(qapp: Any, win: Any, how: str,
                                                                        monkeypatch: pytest.MonkeyPatch) -> None:
    closed: list[bool] = []
    monkeypatch.setattr(win, "close", lambda: closed.append(True))
    win.go("System")
    win.go("Assistant")
    _chat(qapp, win, "Where are the logs?")
    if how == "close-tab":
        win.action_map["closeTab"].trigger()  # ⌘W with the Assistant in front
    else:
        win.tabs.tabCloseRequested.emit(1)
    assert not closed, "⌘W on the Assistant closes its tab, not the window"
    assert win.tabs.count() == 1 and win.tabs.currentWidget() is win.pages
    assert win.pages.currentWidget() is win.system and _row(win) == "System"
    win.go("Assistant")
    assert win.tabs.count() == 2 and win.tabs.currentWidget() is win.assistant
    assert len(win.assistant.messages) == 2 and "Where are the logs?" in win.assistant.transcript.toPlainText()
    win.assistant.new_chat()  # New Chat is what clears it
    assert win.assistant.messages == [] and win.tabs.count() == 2


def test_the_chat_is_never_drawn_over_the_page(qapp: Any, win: Any) -> None:
    win.show()
    qapp.processEvents()
    assert not win.assistant.isVisible(), "before it is opened"
    win.go("Assistant")
    qapp.processEvents()
    assert win.assistant.isVisible() and not win.pages.isVisible()
    win.go("Runs")
    qapp.processEvents()
    assert not win.assistant.isVisible() and win.pages.isVisible()
    win.go("Assistant")
    win.close_assistant()
    qapp.processEvents()
    assert not win.assistant.isVisible() and win.pages.isVisible(), "after it is closed"


def test_close_tab_without_the_assistant_in_front_behaves_as_before(win: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    closed: list[bool] = []
    monkeypatch.setattr(win, "close", lambda: closed.append(True))
    win.go("Assistant")
    win.go("Runs")
    win.action_map["closeTab"].trigger()  # Runs in front: the window, as before D-1040
    assert closed == [True] and win.tabs.count() == 2


def test_a_reply_that_arrives_while_the_tab_is_closed_is_kept(qapp: Any, win: Any) -> None:
    win.go("Assistant")
    win.assistant.input.setPlainText("Slow question")
    win.assistant.send()
    win.close_assistant()  # before the answer
    wait(qapp, lambda: not win.assistant.busy)
    win.go("Assistant")
    assert [m["role"] for m in win.assistant.messages] == ["user", "assistant"]
    assert "Run agentprov verify." in win.assistant.transcript.toPlainText()


# ---------------------------------------------------------------------------------------------- the page (D-1041)
def _sent_page(win: Any) -> Any:
    import json

    stdin = next(s for argv, s in reversed(win.assistant.cli.calls) if argv[0] == "assist")
    return json.loads(stdin).get("page", "(none)")


def test_each_message_names_the_page_beside_the_tab(qapp: Any, win: Any) -> None:
    win.go("Runs")
    win.go("Assistant")
    assert "(Runs)" in win.assistant.privacy.text(), "the line under the message field says what goes"
    _chat(qapp, win, "What does tier R0 mean?")
    assert _sent_page(win) == "Runs"
    win.go("Package")  # the page tab follows the sidebar; the chat goes with it
    win.go("Assistant")
    assert "(Package)" in win.assistant.privacy.text()
    _chat(qapp, win, "And on this page?")
    assert _sent_page(win) == "Package" and len(win.assistant.messages) == 4


def test_only_the_page_name_goes_and_only_a_known_one(qapp: Any, win: Any) -> None:
    import json

    from agentprov_gui.ui.help import ASSIST_PAGES, request_bytes

    doc = json.loads(request_bytes([{"role": "user", "content": "q"}], "Runs"))
    assert doc == {"format": "agentprov-assist-request/0.1", "page": "Runs",
                   "messages": [{"role": "user", "content": "q"}]}
    assert "page" not in json.loads(request_bytes([{"role": "user", "content": "q"}], "Nowhere"))
    assert "page" not in json.loads(request_bytes([{"role": "user", "content": "q"}]))
    win.assistant.set_page("Assistant")
    assert win.assistant.page is None and "beside this tab" not in win.assistant.privacy.text()
    pages = [win.sidebar.item(i).text() for i in range(win.sidebar.count())
             if isinstance(win.sidebar.item(i).data(0x0100), int)]  # Qt.UserRole: the stack's pages
    assert tuple(pages) == ASSIST_PAGES, "every page of the stack can be named, and nothing else"


def test_the_app_and_the_cli_know_the_same_pages() -> None:
    from agentprov.cli.assist import PAGES

    from agentprov_gui.ui.help import ASSIST_PAGES

    assert tuple(PAGES) == ASSIST_PAGES
