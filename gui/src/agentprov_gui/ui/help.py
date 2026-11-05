"""The Help section of the sidebar (D-1010): Docs and Assistant.

* **Docs** reads the user guide of the configured checkout (``docs/user-guide/*.md``, without the internal ``_*.md``
  checklists), else the copy that comes with the app (:mod:`agentprov_gui.guide`, D-1030), says which one it shows, and
  shows it in :class:`~agentprov_gui.ui.safe.DocView`. A link to another chapter opens it (and its heading); a web
  address is copied to the clipboard, since the app opens no web pages (S11).
* **Assistant** is one chat session with a model the user chose (Settings › Assistant). Every message runs
  ``agentprov assist --format json`` with the conversation on stdin (reverse CLI parity, D-700), with the checkout's
  CLI or, without a checkout, the ``agentprov`` installed with ``pip install agentprov`` (D-1030): the CLI picks the
  passages of the guide, the CLI help and the code docstrings that fit the question, makes the request and reads the
  key from the keychain, so the GUI process opens no connection and never holds a key (S11, D-702). The reply is model
  output: it is shown escaped in a plain-text pane (S2), never followed or run. *New Chat* clears the session.
  The Assistant is a tab beside a page of the window (D-1040); each request names that page, from :data:`ASSIST_PAGES`
  only (D-1041), and the line under the message field says so. Nothing the page shows is sent.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Final

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut, QTextCursor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QWidget,
)

from agentprov_gui import __version__
from agentprov_gui import text as T
from agentprov_gui.guide import BUNDLED, chapter_files, pick_guide
from agentprov_gui.ui.brand import SourceListDelegate, command_card, page_layout
from agentprov_gui.ui.forms import FormSection, StatusBadge, SummaryPanel, caption, heading
from agentprov_gui.ui.safe import DocView, ReadOnlyText, SafeLabel, set_control_tooltip

__all__ = ["AssistantPage", "DocsPage", "chapters", "slug"]

ONLINE_DOCS: Final = "https://w3id.org/agentprov/docs/"
MAX_DOC_BYTES: Final = 2 * 1024 * 1024
#: the local servers of endpoints.toml: the request stays on this machine, so no --allow-network
LOCAL_ENDPOINTS: Final = ("ollama", "omlx", "lmstudio", "mlx_lm", "llamacpp", "vllm")
REQUEST_FORMAT: Final = "agentprov-assist-request/0.1"
REPLY_FORMAT: Final = "agentprov-assist-reply/0.1"
REPLY_CHARS: Final = 60_000
#: The CLI's request limits (``agentprov.cli.assist``: MAX_MESSAGES, MAX_MESSAGE_CHARS, MAX_REQUEST_BYTES). The page
#: keeps the whole conversation but sends only what fits: a long earlier reply is cut and the oldest turns are dropped,
#: so one long answer or a long chat never blocks the next message (review UC-14).
SEND_MESSAGES: Final = 40
SEND_TURN_CHARS: Final = 20_000
SEND_BYTES: Final = 1024 * 1024
#: the CLI waits up to 120 s for the model; this leaves it room to start and to answer
CALL_TIMEOUT_S: Final = 200.0
#: D-1041: the pages a request may name (``agentprov.cli.assist.PAGES``); any other page is not named
ASSIST_PAGES: Final = ("Viewer", "Runs", "Logs", "System", "Licences", "Package", "Docs")
_H1: Final = re.compile(r"^#\s+(.+?)\s*#*\s*$", re.MULTILINE)


def slug(heading: str) -> str:
    """A heading's anchor as MkDocs writes it: lower case, punctuation dropped, spaces as hyphens."""
    text = re.sub(r"[`*_]", "", heading).strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"[\s]+", "-", text)


def chapters(guide: Path) -> list[tuple[str, Path]]:
    """``(title, path)`` of the guide's chapters: the README first, then the numbered chapters in order."""
    out: list[tuple[str, Path]] = []
    for path in chapter_files(guide):
        try:
            head = path.read_text(encoding="utf-8")[:4096]
        except (OSError, UnicodeDecodeError):
            continue
        match = _H1.search(head)
        title = match.group(1).strip() if match else path.stem
        out.append(("Overview" if path.name == "README.md" else title, path))
    return out


def request_bytes(messages: list[dict[str, str]], page: str | None = None) -> bytes:
    """The ``agentprov assist`` request for ``messages``, within the CLI's limits: each earlier reply cut at
    :data:`SEND_TURN_CHARS`, then the oldest turns dropped (so the first one sent is the user's) until at most
    :data:`SEND_MESSAGES` are left and the document fits in :data:`SEND_BYTES`. The newest question is always sent.
    ``page`` (D-1041) is named only when it is one of :data:`ASSIST_PAGES`; a CLI older than D-1041 ignores it."""
    head: dict[str, Any] = {"format": REQUEST_FORMAT}
    if page in ASSIST_PAGES:
        head["page"] = page
    turns = [{"role": m["role"], "content": m["content"] if m["role"] == "user" or len(m["content"]) <= SEND_TURN_CHARS
              else m["content"][:SEND_TURN_CHARS]} for m in messages]
    while True:
        while len(turns) > 1 and turns[0]["role"] != "user":
            turns.pop(0)
        data = json.dumps({**head, "messages": turns}).encode("utf-8")
        if len(turns) <= 1 or (len(turns) <= SEND_MESSAGES and len(data) <= SEND_BYTES):
            return data
        turns.pop(0)

class DocsPage(QWidget):
    """Help › Docs: the chapters of the checkout's user guide, else of the guide that comes with the app (D-1030)."""

    status_message = Signal(str)
    settings_requested = Signal(str)

    def __init__(self, checkout: Path | None, parent: QWidget | None = None, *,
                 bundled: Path | None = BUNDLED) -> None:
        """``bundled`` is the app's copy of the guide (tests give their own)."""
        super().__init__(parent)
        self.setAccessibleName("Docs")
        self.bundled = bundled
        self.guide: Path | None = None
        self.source = "none"  # checkout | bundled | none
        self.current: Path | None = None
        self.history: list[Path] = []
        lay, head, self.note = page_layout(self, "Docs", caption_name="Docs status")
        self.source_badge = StatusBadge("", name="Guide source", parent=self)
        set_control_tooltip(self.source_badge, "Which user guide this page reads: the checkout's own, or the copy that "
                                               "came with the app.")
        head.addWidget(self.source_badge)
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.back_btn = QPushButton("‹ Back", self)
        self.back_btn.setAccessibleName("Back to the previous chapter")
        self.back_btn.clicked.connect(self.back)
        set_control_tooltip(self.back_btn, "Goes back to the chapter shown before this one.")
        self.find_field = QLineEdit(self)
        self.find_field.setAccessibleName("Find in the chapter")
        self.find_field.setPlaceholderText("Find in this chapter")
        self.find_field.returnPressed.connect(self.find_next)
        set_control_tooltip(self.find_field, "Type text and press Return to find its next match in this chapter; the "
                                             "search wraps around once at the end.")
        self.settings_btn = QPushButton("Open Settings…", self)
        self.settings_btn.setAccessibleName("Open Settings to set the AgentPROV checkout")
        self.settings_btn.clicked.connect(lambda: self.settings_requested.emit("General"))
        set_control_tooltip(self.settings_btn,
                            "Opens Settings › General, where the AgentPROV checkout whose user guide this page reads "
                            "is set.")
        self.note.setVisible(True)  # the guide it reads (set_checkout fills it)
        bar.addWidget(self.back_btn)
        bar.addWidget(self.find_field, 1)
        bar.addWidget(self.settings_btn)
        lay.addLayout(bar)
        split = QSplitter(Qt.Orientation.Horizontal, self)
        split.setChildrenCollapsible(False)
        split.setHandleWidth(18)
        chapters_card = FormSection("", parent=split)
        chapters_card.setMaximumWidth(320)
        self.toc = QListWidget(chapters_card.card)
        self.toc.setAccessibleName("Chapters")
        self.toc.setFrameShape(QFrame.Shape.NoFrame)
        self.toc.setItemDelegate(SourceListDelegate(self.toc))  # the sidebar's source-list rows (D-1060)
        self.toc.setMouseTracking(True)
        self.toc.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.toc.setStyleSheet("QListWidget { background: transparent; border: none; outline: 0; }")
        set_control_tooltip(self.toc, "The chapters of the user guide (the checkout's docs/user-guide folder, else the "
                                      "copy that comes with the app); choose one to read it.")
        chapters_card.add(self.toc)
        chapters_card.card.setSizePolicy(chapters_card.card.sizePolicy().horizontalPolicy(),
                                         chapters_card.card.sizePolicy().Policy.Expanding)
        reader = FormSection("", parent=split)
        self.view = DocView(name="Chapter", parent=reader.card)
        self.view.setFrameShape(QFrame.Shape.NoFrame)
        self.view.setStyleSheet("QTextBrowser { background: transparent; border: none; }")
        reader.add(self.view)
        reader.card.setSizePolicy(reader.card.sizePolicy().horizontalPolicy(), reader.card.sizePolicy().Policy.Expanding)
        split.addWidget(chapters_card)
        split.addWidget(reader)
        split.setStretchFactor(1, 1)
        lay.addWidget(split, 1)
        self.toc.currentItemChanged.connect(self._picked)
        self.view.anchorClicked.connect(self.follow)
        self.set_checkout(checkout)

    def set_checkout(self, checkout: Path | None) -> None:
        self.checkout = checkout
        self.guide, self.source = pick_guide(checkout, self.bundled)
        self.history.clear()
        self.current = None
        self.toc.blockSignals(True)
        self.toc.clear()
        found = chapters(self.guide) if self.guide is not None else []
        for title, path in found:
            item = QListWidgetItem(T.line(title, 120))
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            self.toc.addItem(item)
        self.toc.blockSignals(False)
        self.settings_btn.setVisible(self.source != "checkout")
        self.back_btn.setEnabled(False)
        self.source_badge.set_status(*(("No guide", "warn") if not found else ("The checkout's guide", "ok")
                                       if self.source == "checkout" else ("The app's copy of the guide", "info")))
        if not found:
            self.view.clear()
            self.note.set_plain("No user guide here: no AgentPROV checkout with a docs/user-guide folder is set in "
                                "Settings › General, and this app has no copy of the guide. The guide is also online "
                                "at " + ONLINE_DOCS)
            return
        if self.source == "checkout":
            self.note.set_plain(f"The user guide of the checkout: {T.line(str(self.guide), 300)}")
        else:
            self.note.set_plain(f"The user guide that came with this app (AgentPROV {T.line(__version__, 40)})"
                                + (f"; the checkout {T.line(str(checkout), 300)} has no docs/user-guide folder"
                                   if checkout is not None else "")
                                + ". Set a checkout in Settings › General to read its own guide.")
        self.toc.setCurrentRow(0)

    def _picked(self, item: QListWidgetItem | None, _old: object = None) -> None:
        if item is not None:
            self.open(Path(str(item.data(Qt.ItemDataRole.UserRole))), remember=self.current is not None)

    def open(self, path: Path, anchor: str = "", *, remember: bool = True) -> None:
        guide = self.guide
        if guide is None:
            return
        try:
            data = path.read_bytes()[:MAX_DOC_BYTES]
        except OSError:
            self.status_message.emit(f"Cannot read {T.line(path.name, 80)}")
            return
        if path != self.current:
            if remember and self.current is not None:
                self.history.append(self.current)
            self.current = path
            self.view.show_markdown(data.decode("utf-8", "replace"), guide)
            self._select_toc(path)
        self.back_btn.setEnabled(bool(self.history))
        if anchor:
            self.scroll_to(anchor)
        else:
            self.view.verticalScrollBar().setValue(0)

    def _select_toc(self, path: Path) -> None:
        for i in range(self.toc.count()):
            if self.toc.item(i).data(Qt.ItemDataRole.UserRole) == str(path):
                self.toc.blockSignals(True)
                self.toc.setCurrentRow(i)
                self.toc.blockSignals(False)
                return

    def back(self) -> None:
        if self.history:
            path = self.history.pop()
            self.open(path, remember=False)

    def scroll_to(self, anchor: str) -> None:
        """Scroll to the heading whose MkDocs anchor is ``anchor`` (Qt's Markdown import names no anchors)."""
        block = self.view.document().begin()
        while block.isValid():
            if block.blockFormat().headingLevel() and slug(block.text()) == anchor:
                cursor = QTextCursor(block)
                self.view.setTextCursor(cursor)
                bar = self.view.verticalScrollBar()
                bar.setValue(bar.maximum())  # bring the heading to the top, not just into view
                self.view.ensureCursorVisible()
                return
            block = block.next()

    def follow(self, url: QUrl) -> None:
        """A clicked link: a guide chapter (and heading) opens here; a web address is copied, never opened."""
        if url.scheme() in ("http", "https", "mailto"):
            QGuiApplication.clipboard().setText(url.toString())
            self.status_message.emit(f"Link copied: {T.line(url.toString(), 200)} (the app opens no web pages)")
            return
        guide = self.guide
        if guide is None or url.scheme() not in ("", "file"):
            return
        target = url.toLocalFile() if url.isLocalFile() else url.path()
        anchor = url.fragment()
        if not target:
            self.scroll_to(anchor)
            return
        path = (guide / target).resolve() if not Path(target).is_absolute() else Path(target).resolve()
        if path.is_relative_to(guide.resolve()) and path.suffix == ".md" and path.is_file():
            self.open(path, anchor)
        else:
            self.status_message.emit(f"Not a chapter of the guide: {T.line(target, 120)}")

    def find_next(self) -> None:
        if self.find_field.text() and not self.view.find(self.find_field.text()):
            self.view.moveCursor(QTextCursor.MoveOperation.Start)  # wrap around once
            if not self.view.find(self.find_field.text()):
                self.status_message.emit("Not found in this chapter")


class AssistantPage(QWidget):
    """Help › Assistant: one chat session with the model set in Settings › Assistant (``agentprov assist``)."""

    settings_requested = Signal(str)

    def __init__(self, cli: Any, parent: QWidget | None = None) -> None:
        """``cli`` is a :class:`~agentprov_gui.jobs.manager.CliLocator`, or a callable ``(argv, stdin) -> (code,
        stdout, stderr)`` in tests."""
        super().__init__(parent)
        self.setAccessibleName("Assistant")
        self.cli = cli
        self.messages: list[dict[str, str]] = []
        self.endpoint: str | None = None
        self.server: str | None = None
        self.base_url: str | None = None
        self.model: str | None = None
        self.loaded = False
        self.busy = False
        self.generation = 0  # a reply that arrives after New Chat belongs to the old session and is dropped
        self._settings_seq = 0  # AU-GUI-2: a settings read that lands after a newer one is dropped
        self.page: str | None = None  # the page beside the Assistant tab (D-1041; set by the main window)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        chat = QWidget(self)
        lay, head, _note = page_layout(chat, "Assistant", caption_text=(
            "Ask how to do something in AgentPROV. A reply is model output, shown as plain text: nothing in it is "
            "followed or run."))
        self.new_btn = QPushButton("New Chat", chat)
        self.new_btn.setAccessibleName("Clear the chat and start a new one")
        self.new_btn.clicked.connect(self.new_chat)
        set_control_tooltip(self.new_btn, "Clears the conversation and starts a new one; a reply still on its way is "
                                          "dropped.")
        head.addWidget(self.new_btn)
        conversation = FormSection("", parent=chat)
        self.transcript = ReadOnlyText(name="Conversation", parent=conversation.card, wrap=True)
        self.transcript.setFrameShape(QFrame.Shape.NoFrame)
        self.transcript.setStyleSheet("QPlainTextEdit { background: transparent; border: none; }")
        self.transcript.setPlaceholderText("The conversation shows here.")
        conversation.add(self.transcript)
        conversation.card.setSizePolicy(conversation.card.sizePolicy().horizontalPolicy(),
                                        conversation.card.sizePolicy().Policy.Expanding)
        lay.addWidget(conversation, 1)
        composer = FormSection("", parent=chat)
        self.input = QPlainTextEdit(composer.card)
        self.input.setAccessibleName("Your message")
        self.input.setPlaceholderText("Ask how to do something in AgentPROV (⌘↩ or Ctrl+Enter sends)")
        self.input.setMaximumHeight(110)
        self.input.setFrameShape(QFrame.Shape.NoFrame)
        self.input.setStyleSheet("QPlainTextEdit { background: transparent; border: none; }")
        set_control_tooltip(self.input, "Your question about AgentPROV. ⌘↩ or Ctrl+Enter sends it, with the earlier "
                                        "turns of this conversation.")
        composer.add(self.input)
        bottom_row = QWidget(composer.card)
        bottom = QHBoxLayout(bottom_row)
        bottom.setContentsMargins(0, 0, 0, 0)
        self.privacy = caption("", name="What is sent", parent=bottom_row)
        self.send_btn = QPushButton("Send", bottom_row)
        self.send_btn.setAccessibleName("Send the message to the Assistant")
        self.send_btn.setProperty("apvRole", "primary")  # the blue default action (D-1060)
        self.send_btn.clicked.connect(self.send)
        set_control_tooltip(self.send_btn, "Sends the message through agentprov assist, with the passages of the "
                                           "guide, the CLI help and the code docs that best match it.")
        bottom.addWidget(self.privacy, 1)
        bottom.addWidget(self.send_btn, 0, Qt.AlignmentFlag.AlignBottom)
        composer.add(bottom_row)
        lay.addWidget(composer)
        outer.addWidget(chat, 1)
        # the summary panel: the model in use and its state, and the terminal command each message runs
        panel = SummaryPanel(name="Assistant summary", parent=self, width=300)
        panel.add(heading("Model", name="Model heading", parent=panel.inner))
        card, card_lay = panel.card(name="Assistant model")
        self.state = StatusBadge("", name="Assistant state", parent=card)
        set_control_tooltip(self.state, "Whether the Assistant can answer: its model and server or provider are set "
                                        "in Settings › Assistant.")
        card_lay.addWidget(self.state)
        self.status = SafeLabel("Reading the Assistant settings…", name="Assistant status", parent=card)
        self.status.setWordWrap(True)
        set_control_tooltip(self.status, "The model and the server or provider the Assistant uses, from Settings › "
                                         "Assistant.", active=lambda: self.ready)
        card_lay.addWidget(self.status)
        self.settings_btn = QPushButton("Open Settings…", card)
        self.settings_btn.setAccessibleName("Open Settings to set up the Assistant")
        self.settings_btn.clicked.connect(lambda: self.settings_requested.emit("Assistant" if self.loaded else
                                                                               "General"))
        set_control_tooltip(self.settings_btn,
                            "Opens Settings › Assistant to choose the server or API provider and the model, or "
                            "Settings › General when there is no agentprov to run.")
        card_lay.addWidget(self.settings_btn, 0, Qt.AlignmentFlag.AlignLeft)
        self.command_card = command_card(panel.inner)
        panel.add(self.command_card)
        outer.addWidget(panel)
        for keys in ("Ctrl+Return", "Ctrl+Enter"):
            shortcut = QShortcut(QKeySequence(keys), self.input)
            shortcut.activated.connect(self.send)
        self._refresh_controls()
        self.reload()

    # ------------------------------------------------------------------------------------------ the CLI
    def _call(self, argv: list[str], stdin: bytes | None = None) -> tuple[int, bytes, bytes]:
        from agentprov_gui.jobs.manager import CliLocator
        from agentprov_gui.live.cli import call

        if isinstance(self.cli, CliLocator):
            return call(self.cli, argv, timeout=CALL_TIMEOUT_S, stdin=stdin)
        result: tuple[int, bytes, bytes] = self.cli(argv, stdin)
        return result

    def reload(self) -> None:
        """Read ``assistant.endpoint`` and ``assistant.model`` (``agentprov settings list``) in the background."""
        from agentprov_gui.ui.worker import submit

        def work(_s: object) -> dict[str, Any] | None:
            code, out, _err = self._call(["settings", "list", "--prefix", "assistant.", "--format", "json"])
            if code != 0:
                return None
            try:
                values = json.loads(out).get("values")
            except (ValueError, AttributeError):
                return None
            return values if isinstance(values, dict) else None

        self._settings_seq += 1
        seq = self._settings_seq

        def done(values: dict[str, Any] | None) -> None:
            if seq == self._settings_seq:  # else a newer read (Settings › OK) is running or has answered
                self._configured(values)

        submit(self, work, done, lambda _code: done(None))

    def _configured(self, values: dict[str, Any] | None) -> None:
        self.loaded = values is not None
        values = values or {}

        def text(key: str) -> str | None:
            value = values.get(key) if values else None
            return value if isinstance(value, str) and value else None

        self.endpoint, self.server = text("assistant.endpoint"), text("assistant.server")
        self.base_url, self.model = text("assistant.base_url"), text("assistant.model")
        self._refresh_controls()

    @property
    def ready(self) -> bool:
        return self.model is not None and (self.endpoint is not None or self.local)

    @property
    def local(self) -> bool:
        """A local server: a server kind or base URL, or a local entry of endpoints.toml."""
        return self.server is not None or self.base_url is not None or self.endpoint in LOCAL_ENDPOINTS

    @property
    def where(self) -> str:
        if self.server is not None or self.base_url is not None:
            return f"{T.line(self.server or 'local server', 40)}" + (f" ({T.line(self.base_url, 120)})"
                                                                     if self.base_url else "")
        return T.line(self.endpoint, 40)

    def _refresh_controls(self) -> None:
        if not self.loaded:
            self.status.set_plain("The Assistant runs agentprov assist, and its settings could not be read: set the "
                                  "AgentPROV checkout, or the agentprov installed with pip install agentprov, in "
                                  "Settings › General.")
        elif not self.ready:
            self.status.set_plain("The Assistant is not set up. Choose an endpoint and a model in Settings › "
                                  "Assistant, and store the endpoint's key in Settings › Keys (a local server such as "
                                  "Ollama or LM Studio needs no key).")
        else:
            self.status.set_plain(f"Model: {T.line(self.model, 120)} on {self.where}")
        self.settings_btn.setVisible(not self.ready)
        local = self.local
        page = (f" With each one goes the name of the page beside this tab ({self.page}), nothing it shows."
                if self.page in ASSIST_PAGES else "")
        self.privacy.set_plain(
            "" if not self.ready else
            "Your messages and the documentation passages chosen for them go to the local server on this machine."
            + page if local else
            f"Your messages and the documentation passages chosen for them are sent to {T.line(self.endpoint, 40)}; "
            "the provider bills the tokens." + page)
        self.send_btn.setEnabled(self.ready and not self.busy)
        self.input.setEnabled(self.ready)
        self.new_btn.setEnabled(bool(self.messages) or self.busy)
        if not self.loaded:
            self.state.set_status("No agentprov to run", "bad")
        elif not self.ready:
            self.state.set_status("Not set up", "warn")
        else:
            self.state.set_status("Waiting for the reply" if self.busy else "Ready", "info" if self.busy else "ok")
        if self.ready:
            stdin = "the conversation" + (f" and the page name ({self.page})" if self.page in ASSIST_PAGES else "")
            self.command_card.set_commands([(f"{stdin} go on stdin as {REQUEST_FORMAT} JSON; for one question, add "
                                             "--question TEXT", self.assist_argv())])
        else:
            self.command_card.set_commands([], note="Set up the Assistant in Settings › Assistant to see its command.")

    def assist_argv(self) -> list[str]:
        """The ``agentprov assist`` arguments each message runs (and the terminal command card shows): the model, the
        endpoint or local server, the key from the keychain only (never a key in the arguments, D-702) and
        ``--allow-network`` for an API provider."""
        argv = ["assist", "--model-id", str(self.model), "--keychain", "--format", "json"]
        for option, value in (("--endpoint", self.endpoint), ("--server", self.server), ("--base-url", self.base_url)):
            if value is not None:
                argv += [option, value]
        if not self.local:
            argv.append("--allow-network")
        return argv

    def set_page(self, page: str | None) -> None:
        """The page beside the Assistant tab (D-1041): its name goes with the next message."""
        self.page = page if page in ASSIST_PAGES else None
        self._refresh_controls()

    # ------------------------------------------------------------------------------------------ the chat
    def _render(self, pending: bool = False) -> None:
        parts: list[str] = []
        for m in self.messages:
            who = "You" if m["role"] == "user" else "Assistant"
            body = T.multiline(m["content"], REPLY_CHARS)
            parts.append(f"{who}:\n{body}")
            if m.get("sources"):
                parts.append(f"Sources: {m['sources']}")
        if pending:
            parts.append("Assistant: …")
        self.transcript.set_plain_keep("\n\n".join(parts), follow_end=True, fresh=True)

    def send(self) -> None:
        text = self.input.toPlainText().strip()
        if not text or self.busy or not self.ready:
            return
        from agentprov_gui.ui.worker import submit

        self.input.clear()
        self.messages.append({"role": "user", "content": text})
        self.busy = True
        self._render(pending=True)
        self._refresh_controls()
        request = request_bytes(self.messages, self.page)
        argv = self.assist_argv()
        generation = self.generation
        submit(self, lambda _s: self._call(argv, request), lambda r: self._answered(generation, r),
               lambda code: self._answered(generation, (124, b"", code.encode())))

    def _answered(self, generation: int, result: tuple[int, bytes, bytes]) -> None:
        if generation != self.generation:
            return
        self.busy = False
        code, out, err = result
        doc: Any = None
        if code == 0:
            try:
                doc = json.loads(out)
            except ValueError:
                doc = None
        if isinstance(doc, dict) and doc.get("format") == REPLY_FORMAT and isinstance(doc.get("reply"), str):
            listed = doc.get("sources")
            sources: list[Any] = listed if isinstance(listed, list) else []
            self.messages.append({"role": "assistant", "content": doc["reply"] or "(an empty answer)",
                                  "sources": ", ".join(T.line(s, 120) for s in sources[:12] if isinstance(s, str))})
        else:
            from agentprov_gui.live.cli import last_line

            reason = T.line(last_line(err) or f"exit {code}", 400)
            question = self.messages.pop()["content"]  # not answered: give it back for another try
            self._render()
            if not self.input.toPlainText().strip():
                self.input.setPlainText(question)
            self.transcript.appendPlainText(f"\nThe Assistant could not answer: {reason}")
            self._refresh_controls()
            return
        self._render()
        self._refresh_controls()

    def new_chat(self) -> None:
        """Clear the session: the conversation, the transcript and any reply still on its way."""
        self.generation += 1
        self.messages.clear()
        self.busy = False
        self.transcript.set_plain_keep("", fresh=True)
        self._refresh_controls()
        self.input.setFocus()
