"""D-1010: the Help section: Docs (the checkout's user guide) and Assistant (a chat through ``agentprov assist``).

The Assistant's CLI is a fake caller ``(argv, stdin) -> (code, stdout, stderr)``: no model, no network."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]


def wait(app: Any, cond: Any, timeout: float = 30) -> None:
    from PySide6.QtCore import QEventLoop

    end = time.monotonic() + timeout
    while not cond():
        assert time.monotonic() < end, "timed out"
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20)
        time.sleep(0.005)


class FakeCli:
    def __init__(self, values: dict[str, Any], reply: Any = None, code: int = 0, err: bytes = b"") -> None:
        self.values, self.reply, self.code, self.err = values, reply, code, err
        self.calls: list[tuple[list[str], bytes | None]] = []

    def __call__(self, argv: list[str], stdin: bytes | None) -> tuple[int, bytes, bytes]:
        self.calls.append((argv, stdin))
        if argv[0] == "settings":
            return 0, json.dumps({"format": "agentprov-settings/0.1", "values": self.values}).encode(), b""
        if self.code:
            return self.code, b"", self.err
        return 0, json.dumps(self.reply).encode(), b""


def _reply(text: str) -> dict[str, Any]:
    return {"format": "agentprov-assist-reply/0.1", "endpoint": "openai", "model": "m", "reply": text,
            "truncated": False, "sources": ["docs/user-guide/08-desktop-app.md"], "usage": {}}


# ---------------------------------------------------------------------------------------------- Docs
def test_the_docs_page_lists_the_guide_and_follows_its_links(qapp: Any) -> None:
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QGuiApplication

    from agentprov_gui.ui.help import DocsPage, chapters

    found = chapters(REPO / "docs" / "user-guide")
    assert found[0][0] == "Overview" and not [p for _t, p in found if p.name.startswith("_")]
    page = DocsPage(REPO)
    assert page.toc.count() == len(found) and page.current == found[0][1]
    assert not page.settings_btn.isVisibleTo(page)
    page.follow(QUrl("07-live-runs.md#containment"))
    assert page.current is not None and page.current.name == "07-live-runs.md"
    assert page.view.textCursor().block().text().strip().lower().startswith("containment")
    page.back()
    assert page.current == found[0][1]
    messages: list[str] = []
    page.status_message.connect(messages.append)
    page.follow(QUrl("https://example.org/x"))
    assert QGuiApplication.clipboard().text() == "https://example.org/x" and "Link copied" in messages[-1]
    page.follow(QUrl("../../CLAUDE.md"))  # outside the guide: not opened
    assert page.current == found[0][1] and "Not a chapter" in messages[-1]


def test_the_docs_page_without_a_checkout_points_to_settings(qapp: Any, tmp_path: Path) -> None:
    from agentprov_gui.ui.help import DocsPage

    page = DocsPage(tmp_path)
    asked: list[str] = []
    page.settings_requested.connect(asked.append)
    assert page.toc.count() == 0 and page.settings_btn.isVisibleTo(page)
    assert "Settings › General" in page.note.text()
    page.settings_btn.click()
    assert asked == ["General"]


def test_doc_images_load_only_from_the_guide(qapp: Any) -> None:
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QTextDocument

    from agentprov_gui.ui.safe import DocView

    view = DocView(name="t")
    guide = REPO / "docs" / "user-guide"
    view.show_markdown("x", guide)
    image = QTextDocument.ResourceType.ImageResource.value
    assert view.loadResource(image, QUrl("images/gui/run-live-models.png")) is not None
    assert view.loadResource(image, QUrl("https://example.org/a.png")) is None
    assert view.loadResource(image, QUrl("../../site/assets/img/brand/favicon.png")) is None


# ---------------------------------------------------------------------------------------------- Assistant
def test_not_set_up_shows_the_settings_link(qapp: Any) -> None:
    from agentprov_gui.ui.help import AssistantPage

    page = AssistantPage(FakeCli({}))
    wait(qapp, lambda: page.loaded)
    asked: list[str] = []
    page.settings_requested.connect(asked.append)
    assert "not set up" in page.status.text() and page.settings_btn.isVisibleTo(page)
    assert not page.send_btn.isEnabled() and not page.input.isEnabled()
    page.settings_btn.click()
    assert asked == ["Assistant"]


def test_a_chat_sends_the_conversation_and_new_chat_clears_it(qapp: Any) -> None:
    from agentprov_gui.ui.help import AssistantPage

    cli = FakeCli({"assistant.endpoint": "openai", "assistant.model": "gpt-x"}, _reply("Open Settings › Keys."))
    page = AssistantPage(cli)
    wait(qapp, lambda: page.ready)
    assert "gpt-x" in page.status.text() and not page.settings_btn.isVisibleTo(page)
    assert "the provider bills the tokens" in page.privacy.text()
    page.input.setPlainText("How do I store a key?")
    page.send()
    wait(qapp, lambda: not page.busy)
    argv, stdin = cli.calls[-1]
    assert argv[:3] == ["assist", "--model-id", "gpt-x"] and argv[argv.index("--endpoint") + 1] == "openai"
    assert "--keychain" in argv and "--allow-network" in argv
    assert json.loads(stdin or b"")["messages"] == [{"role": "user", "content": "How do I store a key?"}]
    shown = page.transcript.toPlainText()
    assert "You:\nHow do I store a key?" in shown and "Assistant:\nOpen Settings › Keys." in shown
    assert "Sources: docs/user-guide/08-desktop-app.md" in shown
    page.input.setPlainText("And for a local model?")
    page.send()
    wait(qapp, lambda: not page.busy)
    assert [m["role"] for m in json.loads(cli.calls[-1][1] or b"")["messages"]] == ["user", "assistant", "user"]
    page.new_btn.click()
    assert page.messages == [] and page.transcript.toPlainText() == ""


def test_a_local_server_needs_no_network_flag_and_a_failure_gives_the_question_back(qapp: Any) -> None:
    from agentprov_gui.ui.help import AssistantPage

    cli = FakeCli({"assistant.endpoint": "ollama", "assistant.model": "qwen3:8b"}, code=3,
                  err=b"agentprov assist: the ollama endpoint did not answer\n")
    page = AssistantPage(cli)
    wait(qapp, lambda: page.ready)
    assert "local server on this machine" in page.privacy.text()
    page.input.setPlainText("hello")
    page.send()
    wait(qapp, lambda: not page.busy)
    assert "--allow-network" not in cli.calls[-1][0]
    assert page.messages == [] and page.input.toPlainText() == "hello"
    assert "could not answer: agentprov assist: the ollama endpoint did not answer" in page.transcript.toPlainText()


def test_a_reply_is_shown_as_escaped_plain_text(qapp: Any, hostile: list[str]) -> None:
    from agentprov_gui.ui.help import AssistantPage

    cli = FakeCli({"assistant.endpoint": "openai", "assistant.model": "m"}, _reply("<b>x</b>\x1b[31m" + hostile[0]))
    page = AssistantPage(cli)
    wait(qapp, lambda: page.ready)
    page.input.setPlainText("q")
    page.send()
    wait(qapp, lambda: not page.busy)
    shown = page.transcript.toPlainText()
    assert "<b>x</b>" in shown and "\x1b" not in shown


def test_a_reply_after_new_chat_is_dropped(qapp: Any) -> None:
    from agentprov_gui.ui.help import AssistantPage

    page = AssistantPage(FakeCli({"assistant.endpoint": "openai", "assistant.model": "m"}, _reply("late")))
    wait(qapp, lambda: page.ready)
    page.messages.append({"role": "user", "content": "q"})
    generation = page.generation
    page.new_chat()
    page._answered(generation, (0, json.dumps(_reply("late")).encode(), b""))
    assert page.messages == []


def test_the_main_window_has_a_help_section(qapp: Any, tmp_path: Path) -> None:
    from PySide6.QtCore import QSettings

    from agentprov_gui.settings import Settings
    from agentprov_gui.ui.mainwindow import MainWindow

    settings = Settings(QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    settings.checkout = REPO
    w = MainWindow(settings, cache_dir=tmp_path / "layout", home=tmp_path / "home")
    rows = [w.sidebar.item(i).text() for i in range(w.sidebar.count())]
    assert rows[-3:] == ["HELP", "Docs", "Assistant"]
    w.go("Docs")
    assert w.pages.currentWidget() is w.docs
    w.go("Assistant")  # D-1040: a tab beside the page, not a page of the stack
    assert w.tabs.currentWidget() is w.assistant and w.pages.currentWidget() is w.docs
    w.close()


@pytest.mark.parametrize(("values", "expected"), [
    ({}, {}),
    ({"assistant.endpoint": "anthropic", "assistant.model": "claude-haiku-5-5"},
     {"assistant.endpoint": "anthropic", "assistant.model": "claude-haiku-5-5"}),
    ({"assistant.server": "splash", "assistant.base_url": "http://127.0.0.1:8003/v1", "assistant.model": "q"},
     {"assistant.server": "splash", "assistant.base_url": "http://127.0.0.1:8003/v1", "assistant.model": "q"}),
    ({"assistant.server": "omlx", "assistant.base_url": "http://127.0.0.1:8000/v1", "assistant.endpoint": "omlx"},
     {"assistant.server": "omlx", "assistant.base_url": "http://127.0.0.1:8000/v1", "assistant.endpoint": "omlx"}),
])
def test_the_settings_pane_round_trips(qapp: Any, values: dict[str, Any], expected: dict[str, Any]) -> None:
    from agentprov_gui.ui.settings_panes import AssistantPane

    pane = AssistantPane(None, cli=lambda argv: (0, json.dumps({"values": values}).encode(), b""))
    wait(qapp, lambda: pane.loaded is not None)
    assert pane.values() == expected


def test_choosing_a_server_fills_its_address_and_refresh_lists_the_loaded_model_first(qapp: Any) -> None:
    from agentprov_gui.ui.settings_panes import AssistantPane

    calls: list[list[str]] = []
    listing = {"format": "agentprov-assist-models/0.1", "base_url": "http://127.0.0.1:8003/v1", "server": "splash",
               "models": [{"id": "qwen-flash-next-q6-256k", "loaded": True}, {"id": "qwen-flash-next-q4-1m",
                                                                             "loaded": False}]}

    def cli(argv: list[str]) -> tuple[int, bytes, bytes]:
        calls.append(argv)
        doc = {"values": {}} if argv[0] == "settings" else listing
        return 0, json.dumps(doc).encode(), b""

    pane = AssistantPane(None, cli=cli)
    wait(qapp, lambda: pane.loaded is not None)
    pane.server.setCurrentIndex(pane.server.findData("splash"))
    assert pane.base_url.text() == "http://127.0.0.1:8003/v1" and pane.refresh.isVisibleTo(pane)
    assert not pane.endpoint.isVisibleTo(pane)
    pane.refresh.click()
    wait(qapp, lambda: pane.model.count() == 2)
    assert calls[-1][:4] == ["assist", "--list-models", "--server", "splash"]
    assert "--base-url" in calls[-1] and pane.model.currentText() == "qwen-flash-next-q6-256k  (loaded)"
    assert pane.values() == {"assistant.server": "splash", "assistant.base_url": "http://127.0.0.1:8003/v1",
                             "assistant.model": "qwen-flash-next-q6-256k"}
    pane.server.setCurrentIndex(pane.server.findData("strata"))
    assert pane.base_url.text() == ""  # no fixed address: typed by the user
    pane.server.setCurrentIndex(pane.server.findData("api"))
    assert pane.endpoint.isVisibleTo(pane) and not pane.refresh.isVisibleTo(pane)
    assert pane.values()["assistant.endpoint"] == "openai"


def test_a_local_server_chat_passes_its_address_and_no_network_flag(qapp: Any) -> None:
    from agentprov_gui.ui.help import AssistantPage

    cli = FakeCli({"assistant.server": "splash", "assistant.base_url": "http://127.0.0.1:8003/v1",
                   "assistant.model": "qwen-flash-next-q6-256k"}, _reply("ok"))
    page = AssistantPage(cli)
    wait(qapp, lambda: page.ready)
    assert "splash (http://127.0.0.1:8003/v1)" in page.status.text()
    page.input.setPlainText("hi")
    page.send()
    wait(qapp, lambda: not page.busy)
    argv = cli.calls[-1][0]
    assert argv[argv.index("--server") + 1] == "splash" and argv[argv.index("--base-url") + 1].endswith(":8003/v1")
    assert "--allow-network" not in argv and "--endpoint" not in argv
