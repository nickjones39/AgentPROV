"""The main window (design §6; macos-design §3.1–3.4; D-442).

A sidebar with sections (Corpora: Viewer; Jobs and Release arrive with G2; Help: Docs and Assistant, D-1010) | the
active page. The Assistant opens as a tab of its own beside the page (D-1040), so the chat and the page it is about are
one click apart; the tab bar shows only while the Assistant tab is open. The frame follows the house style (D-1060): the
sidebar is a source list (section headings in small capitals, a drawn glyph per page, a rounded selection from the
theme; :class:`brand.SourceListDelegate`), the Qt toolbar and the status bar take the theme's tokens and are restyled
when the appearance changes, and the job count in the status bar is a status badge. On macOS, About and
Settings… sit in the App menu (Qt's ``AboutRole``/``PreferencesRole`` move them there) and Settings opens with ⌘,;
elsewhere they are in the Help and Edit menus. Every action has a menu item; the Go menu switches pages (⌘1 …).
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Any

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QAction, QColor, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QSizePolicy,
    QStackedWidget,
    QStatusBar,
    QTabBar,
    QTabWidget,
    QWidget,
)

from agentprov_gui import text as T
from agentprov_gui.paths import agentprov_home, layout_cache_dir
from agentprov_gui.platform import ACTIVITY_TIP, SEARCH_TIP, TOOLBAR_TIPS
from agentprov_gui.settings import Settings
from agentprov_gui.ui import theme
from agentprov_gui.ui.brand import GLYPH_ROLE, SourceListDelegate, glyph_icon
from agentprov_gui.ui.dialogs import AboutDialog, SettingsDialog
from agentprov_gui.ui.execution import render_values
from agentprov_gui.ui.forms import StatusBadge
from agentprov_gui.ui.safe import (
    set_action_tooltip,
    set_control_tooltip,
    set_list_item_tooltip,
    set_tab_tooltip,
    set_tooltips_shown,
)
from agentprov_gui.ui.viewer import ViewerPage, verify_values

__all__ = ["MainWindow"]

#: The CLI's closed outcome vocabulary; anything else in ended.json/summary.json shows as "ended" (S15).
_OUTCOMES = frozenset({"ok", "failures", "usage", "environment", "refused", "unsupported", "internal", "interrupted",
                       "signal"})
#: what each sidebar page holds (its tooltip)
PAGE_TIPS = {
    "Viewer": "Browse corpora, their executions and the PROV graph of each execution (read-only).",
    "Runs": "Start and follow jobs: live runs, New Job forms and dev runs.",
    "Logs": "Read a job's log records or stderr, filtered by level, text or execution.",
    "System": "CPU, memory, swap, free disk space and the processes of the job selected in Runs.",
    "Licences": "The licence facts of every registered source, and the systematic search's exclusions (read-only).",
    "Package": "Seal a working corpus, verify it and build a deposit draft, in nine steps. Nothing is uploaded.",
    "Docs": "The user guide of the AgentPROV checkout set in Settings › General.",
    "Assistant": "Ask a model how to do something in AgentPROV (agentprov assist), in a tab beside the page.",
}
#: the sidebar row of the Assistant: it opens the Assistant tab, not a page of the stack (D-1040)
_ASSISTANT_ROW = "assistant-tab"


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings, *, cache_dir: Path | None = None, home: Path | None = None,
                 jobs: bool = True) -> None:
        super().__init__()
        self.settings = settings
        from agentprov_gui.jobs.manager import set_cli_choice, set_installed_program

        set_installed_program(settings.cli_program)  # the CLI without a checkout (D-1030)
        set_cli_choice(settings.cli_choice)  # or always the bundle's own (D-1130)
        self._base_point_size: float | None = None
        self.setWindowTitle("AgentPROV")
        self.setAccessibleName("AgentPROV main window")
        self.setMinimumSize(900, 560)
        self.resize(1400, 900)
        central = QWidget(self)
        lay = QHBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.sidebar = QListWidget(central)
        self.sidebar.setAccessibleName("Navigation")
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setMaximumWidth(232)
        self.sidebar.setMinimumWidth(160)
        self.sidebar.setFrameShape(QFrame.Shape.NoFrame)
        self.sidebar.setItemDelegate(SourceListDelegate(self.sidebar))  # the source list (D-1060)
        self.sidebar.setMouseTracking(True)  # the hover row
        self.sidebar.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.sidebar.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # D-1040: tab 0 holds the page chosen in the sidebar; the Assistant opens as a second, closable tab
        self.tabs = QTabWidget(central)
        self.tabs.setAccessibleName("Window tabs")
        self.tabs.setDocumentMode(True)
        self.tabs.tabBar().setDrawBase(False)  # no platform band behind the tabs (D-1060)
        self.tabs.setTabsClosable(True)
        self.tabs.setTabBarAutoHide(True)  # one tab (no Assistant): the window looks as it did
        self.pages = QStackedWidget(self.tabs)
        self.pages.setAccessibleName("Pages")
        self.tabs.addTab(self.pages, "")
        bar = self.tabs.tabBar()
        for side in (QTabBar.ButtonPosition.LeftSide, QTabBar.ButtonPosition.RightSide):
            bar.setTabButton(0, side, None)  # the page tab cannot be closed
        self.tabs.tabCloseRequested.connect(self._tab_close_requested)
        lay.addWidget(self.sidebar)
        lay.addWidget(self.tabs, 1)
        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar(self))
        self.statusBar().setAccessibleName("Status")
        self.statusBar().setSizeGripEnabled(sys.platform != "darwin")  # macOS windows resize from any edge
        self.viewer = ViewerPage(settings.corpus_roots, cache_dir if cache_dir is not None else layout_cache_dir(home),
                                 settings.content_limit, self, store=settings.store)
        self.viewer.set_exact_palette(settings.graph_palette == "exact")
        self.viewer.status_message.connect(lambda msg: self.statusBar().showMessage(msg))
        self.viewer.corpus_opened.connect(self._corpus_opened)
        self.viewer.open_folder_requested.connect(self._open_dialog)  # the corpora list's Open Folder… (D-1060)
        self._add_section("Corpora")
        self._add_page("Viewer", self.viewer)
        self.runs: Any = None
        if jobs:
            self._jobs_pages(home or agentprov_home())
        self._help_pages()
        self._updates()
        self.sidebar.currentRowChanged.connect(self._nav)
        self.tabs.currentChanged.connect(self._tab_changed)
        self.sidebar.setCurrentRow(1)
        self.action_map: dict[str, QAction] = {}
        self.chrome: Any = None
        self.toolbar: Any = None
        self._running_ids: set[str] = set()
        self._menus()
        self._restore()
        self._install_chrome()
        self._restyle()
        QGuiApplication.styleHints().colorSchemeChanged.connect(lambda _scheme: self._restyle())
        self.viewer.refresh()

    # ------------------------------------------------------------------------------------------ G2 pages
    def _jobs_pages(self, home: Path) -> None:
        from agentprov_gui.jobs.manager import CliLocator, JobManager
        from agentprov_gui.ui.licences import LicencesPage
        from agentprov_gui.ui.logs import LogsPage
        from agentprov_gui.ui.package import PackagePage
        from agentprov_gui.ui.runs import RunsPage
        from agentprov_gui.ui.system import SystemPage

        self.manager = JobManager(home, CliLocator.for_checkout(self.settings.checkout))
        self.runs = RunsPage(self.manager, self.settings, self)
        self.logs = LogsPage(self.manager, self)
        self.system = SystemPage(home, self)
        self.licences = LicencesPage(self.settings.checkout, self)
        self.package = PackagePage(self.runs.start, self.settings.checkout, self, revalidate=self._revalidate)
        self.viewer.revalidate_requested.connect(self._revalidate)
        self.viewer.render_requested.connect(self._render)
        self.viewer.verify_requested.connect(self._verify)
        self._add_section("Jobs")
        self._add_page("Runs", self.runs)
        self._add_page("Logs", self.logs)
        self._add_page("System", self.system)
        self._add_section("Release")
        self._add_page("Licences", self.licences)
        self._add_page("Package", self.package)
        self.viewer.verified_lookup = self._verified
        self.runs.open_corpus.connect(self._open_written)
        self.runs.open_log.connect(self._open_log)
        self.runs.jobs_changed.connect(self._jobs_changed)
        self.runs.view.selectionModel().currentRowChanged.connect(self._job_selected)
        self.activity = StatusBadge("", name="Job activity", parent=self)  # words with a tint (D-1060)
        set_control_tooltip(self.activity, ACTIVITY_TIP)
        self.statusBar().addPermanentWidget(self.activity)
        self._platform_check(self.manager.cli)
        self._version_check()

    def _help_pages(self) -> None:
        """Help › Docs and Assistant (D-1010): the checkout's user guide (else the app's own copy), and a chat through
        ``agentprov assist`` (the checkout's CLI, else the installed one; D-1030)."""
        from agentprov_gui.jobs.manager import CliLocator
        from agentprov_gui.ui.help import AssistantPage, DocsPage

        self.docs = DocsPage(self.settings.checkout, self)
        from agentprov_gui.ui.platformnotice import set_docs

        set_docs(self.docs, partial(self.go, "Docs"))  # D-1064: a notice's "How to run it" opens its guide section
        self.assistant = AssistantPage(CliLocator.for_checkout(self.settings.checkout), self)
        self.assistant.hide()  # a tab once opened (D-1040); until then not a loose child over the page
        self.docs.status_message.connect(lambda msg: self.statusBar().showMessage(msg, 8000))
        self.docs.settings_requested.connect(self.open_settings)
        self.assistant.settings_requested.connect(self.open_settings)
        self._add_section("Help")
        self._add_page("Docs", self.docs)
        item = QListWidgetItem("Assistant")  # not a page of the stack: it opens the Assistant tab (D-1040)
        item.setData(Qt.ItemDataRole.UserRole, _ASSISTANT_ROW)
        item.setData(GLYPH_ROLE, "Assistant")
        set_list_item_tooltip(item, PAGE_TIPS["Assistant"], wrap=True)
        self.sidebar.addItem(item)

    def _verified(self, corpus: Path) -> str | None:
        """The last successful ``verify`` job of the GUI on ``corpus`` (design §6.1 "verified status")."""
        for job in self.manager.refresh():  # newest first
            argv = job.argv
            if job.command != "verify" or job.exit_code != 0 or "--corpus" not in argv:
                continue
            target = Path(argv[argv.index("--corpus") + 1])
            if target.name.removesuffix(".partial") == corpus.name and target.parent == corpus.parent:
                level = argv[argv.index("--level") + 1] if "--level" in argv else "chain"
                return f"{level}, {job.record.get('created', '')}, job {job.job_id[:13]}"
        return None

    def _render(self, corpus: str, ex: str) -> None:
        """Viewer › Export Graph: the render job form for one execution (D-706; ``agentprov render``, D-654)."""
        self.go("Runs")
        self.runs.new_job("render", render_values(corpus, ex))

    def _verify(self, corpus: str) -> None:
        """Viewer › the notice's Verify…: the verify job form for the open corpus (G.8.6; ``agentprov verify``)."""
        self.go("Runs")
        self.runs.new_job("verify", verify_values(Path(corpus)))

    def _revalidate(self, corpus: str) -> None:
        self.go("Runs")
        self.runs.revalidate(corpus)

    def _open_written(self, path: str) -> None:
        self.go("Viewer")
        self.viewer.open_path(Path(path))

    def _open_log(self, job_id: str) -> None:
        self.logs.reload_jobs()
        self.logs.show_job(job_id)
        self.go("Logs")

    def _job_selected(self, *_: object) -> None:
        job = self.runs.selected
        if job is not None and job.state == "running":
            self.system.follow_job(job.pid, job.record.get("pid_create_time"), job.job_id)

    def _jobs_changed(self, running: int, ended: int) -> None:
        self.activity.set_status(f"● {running} running" if running else f"{ended} jobs", "info" if running else "neutral")
        jobs = {j.job_id: j for j in self.manager.jobs.values()}
        now_running = {k for k, j in jobs.items() if j.state == "running"}
        ended_ids, self._running_ids = self._running_ids - now_running, now_running
        for job_id in ended_ids:
            # AU-GUI-5: a job no longer listed (its folder removed, job.json unreadable for one read) gets no notice
            if (job := jobs.get(job_id)) is not None:
                self._job_ended(job)
        if self.chrome is not None:
            self.chrome.set_activity(running, ended)
            sel = self.runs.selected
            follower = self.runs.followers.get(sel.job_id) if sel is not None else None
            fraction = follower.state.fraction if follower is not None and sel is not None and sel.state == "running" \
                else None
            self.chrome.set_progress(fraction)

    def _job_ended(self, job: Any) -> None:
        """A notification for a job longer than 2 minutes, only when the app is not in front (macos-design §6)."""
        import time as _time

        try:
            started = job.file("job.json").stat().st_ctime
        except OSError:
            return
        if _time.time() - started < 120 or self.isActiveWindow():
            return
        corpus = Path(job.writes[0]).name if job.writes else ""
        outcome = job.outcome if job.outcome in _OUTCOMES else "ended"
        body = f"{T.line(job.command, 40)} {T.line(corpus, 80)}: {outcome}".strip()
        if self.chrome is not None:
            self.chrome.notify("Job finished", body)
        else:
            QApplication.alert(self)

    def _version_check(self) -> None:
        """Viewer-only mode when the CLI's formats differ from the library's (design §2.2)."""
        from agentprov import versions

        from agentprov_gui.jobs.manager import allowlisted_env
        from agentprov_gui.ui.worker import submit

        cli = self.manager.cli
        if not cli.available:
            self.statusBar().showMessage("Viewer only: no AgentPROV checkout with a CLI and no installed agentprov "
                                         "(Settings › General).")
            self.runs.new_btn.setEnabled(False)
            return

        def work(_s: object) -> str:
            import subprocess

            done = subprocess.run([*cli.program, "--version"], capture_output=True, timeout=60, check=False,  # noqa: S603
                                  stdin=subprocess.DEVNULL, env=allowlisted_env())
            return done.stdout.decode("utf-8", "replace")

        def finished(out: str) -> None:
            if self.manager.cli is not cli:  # the checkout changed in Settings while this check ran
                return
            line = next((x for x in out.splitlines() if x.startswith("formats:")), "")
            seen = set(line.removeprefix("formats:").split())
            wanted = {versions.VERSIONS[k] for k in ("aer", "sem", "prov_spec")}
            if not wanted <= seen:
                self.runs.new_btn.setEnabled(False)
                self.statusBar().showMessage("Viewer only: the CLI's formats differ from this GUI's library. "
                                             + T.line(line, 200))

        submit(self, work, finished)

    def _platform_check(self, cli: Any) -> None:
        """D-1064: what this CLI refuses on this platform (``agentprov info --format json``'s ``platform`` member); the
        pages disable those features with its message. Unknown (nothing disabled) until it answers or without a CLI."""
        from agentprov_gui import platform_limits
        from agentprov_gui.ui import platformnotice
        from agentprov_gui.ui.worker import submit

        platformnotice.apply(None)
        if not cli.available:
            return

        def work(_s: object) -> platform_limits.PlatformLimits | None:
            return platform_limits.fetch(cli)

        def finished(limits: platform_limits.PlatformLimits | None) -> None:
            if self.manager.cli is cli:  # else the checkout changed in Settings while this ran
                platformnotice.apply(limits)

        submit(self, work, finished)

    def _platform_gate(self) -> None:
        """D-1064: Run Live… stays in the File menu, disabled with the reason, where live runs are refused."""
        from agentprov_gui import platform_limits
        from agentprov_gui.ui.platformnotice import gate_action

        if "runLive" in self.action_map:
            gate_action(self.action_map["runLive"], platform_limits.current().get("live_runs"))

    # ------------------------------------------------------------------------------------------ navigation
    def _add_section(self, title: str) -> None:
        """A section heading of the sidebar: not selectable; the delegate draws it in small grey capitals."""
        item = QListWidgetItem(title.upper())
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        self.sidebar.addItem(item)

    def _add_page(self, title: str, page: QWidget) -> None:
        item = QListWidgetItem(title)
        item.setData(Qt.ItemDataRole.UserRole, self.pages.addWidget(page))
        item.setData(GLYPH_ROLE, title)
        if title in PAGE_TIPS:
            set_list_item_tooltip(item, PAGE_TIPS[title], wrap=True)
        self.sidebar.addItem(item)

    def _nav(self, row: int) -> None:
        item = self.sidebar.item(row)
        index = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if index == _ASSISTANT_ROW:
            self.open_assistant()
        elif isinstance(index, int):
            self.pages.setCurrentIndex(index)
            self.tabs.setTabText(0, item.text())
            self.assistant.set_page(item.text())  # D-1041: the page the Assistant's next message is about
            set_tab_tooltip(self.tabs, 0, f"{item.text()}: the page chosen in the sidebar (not closable)", wrap=True)
            self.tabs.setCurrentIndex(0)

    def go(self, title: str) -> None:
        if title == "Assistant":
            self.open_assistant()
            return
        for i in range(self.sidebar.count()):
            if self.sidebar.item(i).text() == title:
                self.sidebar.setCurrentRow(i)
                self.tabs.setCurrentIndex(0)  # the row may be current already, with the Assistant tab in front
                return

    # ------------------------------------------------------------------------------------------ the Assistant tab
    def open_assistant(self) -> None:
        """Help › Assistant (D-1040): open the Assistant tab beside the page, or bring it to the front. The page tab
        keeps its page; the conversation lives in :attr:`assistant`, so it survives switching and closing the tab."""
        index = self.tabs.indexOf(self.assistant)
        if index < 0:
            index = self.tabs.addTab(self.assistant, "Assistant")
            self.tabs.tabBar().setAccessibleTabName(index, "Assistant chat")
            set_tab_tooltip(self.tabs, index, "The Assistant chat. Closing the tab keeps the conversation; New Chat "
                                              "clears it.", wrap=True)
        self.tabs.setCurrentIndex(index)
        if self.assistant.input.isEnabled():
            self.assistant.input.setFocus()

    def close_assistant(self) -> bool:
        """Close the Assistant tab (its × or ⌘W); the conversation is kept for the next time it opens. ``False`` when
        it is not open."""
        index = self.tabs.indexOf(self.assistant)
        if index < 0:
            return False
        self.tabs.removeTab(index)
        return True

    def _assistant_current(self) -> bool:
        return self.tabs.currentWidget() is self.assistant

    def _tab_close_requested(self, index: int) -> None:
        if self.tabs.widget(index) is self.assistant:
            self.close_assistant()

    def _tab_changed(self, _index: int) -> None:
        """The sidebar marks what is in front: the Assistant's row, or the row of the page in the page tab."""
        if self._assistant_current():
            target: object = _ASSISTANT_ROW
        else:
            target = self.pages.currentIndex()
        for i in range(self.sidebar.count()):
            if self.sidebar.item(i).data(Qt.ItemDataRole.UserRole) == target:
                self.sidebar.blockSignals(True)
                self.sidebar.setCurrentRow(i)
                self.sidebar.blockSignals(False)
                return

    # ------------------------------------------------------------------------------------------ menus
    def _action(self, text: str, slot: Callable[[], object], shortcut: QKeySequence | QKeySequence.StandardKey | str | None = None,
                role: QAction.MenuRole | None = None) -> QAction:
        act = QAction(text, self)
        if isinstance(shortcut, QKeySequence.StandardKey):
            act.setShortcuts(shortcut)  # every platform binding (QKeySequence(key) keeps only the first: ⌘F4, not ⌘W)
        elif shortcut is not None:
            act.setShortcut(QKeySequence(shortcut))
        if role is not None:
            act.setMenuRole(role)
        act.triggered.connect(slot)
        return act

    def _menus(self) -> None:
        bar = self.menuBar()
        file_menu = bar.addMenu("&File")
        self.action_map["openCorpus"] = self._action("Open Corpus…", self._open_dialog, QKeySequence.StandardKey.Open)
        self.action_map["reload"] = self._action("Reload", self.viewer.refresh, QKeySequence.StandardKey.Refresh)
        file_menu.addAction(self.action_map["openCorpus"])
        file_menu.addAction(self.action_map["reload"])
        if self.runs is not None:
            self.action_map["runLive"] = self._action("Run Live…", self._run_live, "Ctrl+L")  # design §6.2
            file_menu.addAction(self.action_map["runLive"])
            file_menu.setToolTipsVisible(True)  # D-1064: a disabled Run Live… says why (other items have no tooltip)
            from agentprov_gui.ui.platformnotice import notifier

            notifier().changed.connect(self._platform_gate)
            self._platform_gate()
            self.action_map["newJob"] = self._action("New Job…", self._new_job_menu, "Ctrl+N")
            self.action_map["devRun"] = self._action("Dev Run…", self.runs.start_dev_run, None)
            file_menu.addAction(self.action_map["newJob"])
            file_menu.addAction(self.action_map["devRun"])
        file_menu.addSeparator()
        # D-845: the Viewer's execution tabs; ⌘W closes the current one, and the window on the Corpora tab
        self.action_map["openInTab"] = self._action("Open in New Tab", self._open_in_tab)
        self.action_map["closeTab"] = self._action("Close Tab", self._close_tab, QKeySequence.StandardKey.Close)
        self.action_map["closeOtherTabs"] = self._action("Close Other Tabs", self._close_other_tabs, "Ctrl+Alt+W")
        self.action_map["closeWindow"] = self._action("Close Window", self.close, "Ctrl+Shift+W")
        for key in ("openInTab", "closeTab", "closeOtherTabs"):
            file_menu.addAction(self.action_map[key])
        file_menu.addSeparator()
        file_menu.addAction(self.action_map["closeWindow"])
        edit_menu = bar.addMenu("&Edit")
        edit_menu.addAction(self._action("Settings…", self._settings, QKeySequence.StandardKey.Preferences
                                         if sys.platform == "darwin" else "Ctrl+,",
                                         QAction.MenuRole.PreferencesRole))
        view_menu = bar.addMenu("&View")
        self.action_map["toggleSidebar"] = self._action("Toggle Sidebar", self._toggle_sidebar, "Ctrl+Meta+S")
        view_menu.addAction(self.action_map["toggleSidebar"])
        # D-1060: the Viewer's side panes (⌥⌘0 is Text Size › Default, so the inspector takes ⌥⌘I)
        for key, sequence in (("toggleCorpora", "Ctrl+Alt+1"), ("toggleInspector", "Ctrl+Alt+I")):
            act = self.viewer.pane_actions[key]
            act.setShortcut(QKeySequence(sequence))
            act.triggered.connect(partial(self.go, "Viewer"))
            self.action_map[key] = act
            view_menu.addAction(act)
        size_menu = view_menu.addMenu("Text Size")
        size_menu.addAction(self._action("Bigger", lambda: self.scale_text(1.1), "Ctrl+Alt+="))
        size_menu.addAction(self._action("Smaller", lambda: self.scale_text(1 / 1.1), "Ctrl+Alt+-"))
        size_menu.addAction(self._action("Default", lambda: self.scale_text(None), "Ctrl+Alt+0"))
        go_menu = bar.addMenu("&Go")
        for i, page in enumerate(("Viewer", "Runs", "Logs", "System", "Licences", "Package", "Docs", "Assistant"), 1):
            go_menu.addAction(self._action(page, partial(self.go, page), f"Ctrl+{i}"))
        go_menu.addSeparator()
        self.action_map["corporaTab"] = self._action("Corpora", self._corpora_tab)
        go_menu.addAction(self.action_map["corporaTab"])
        # D-845: ⌘⇧] / ⌘⇧[ on macOS (Qt's NextChild there is ⌘Tab, the app switcher); Ctrl+PgDown / Ctrl+PgUp
        # elsewhere, where Ctrl+Tab stays with the sub-tabs
        mac = sys.platform == "darwin"
        for name, text, step, keys in (
                ("nextTab", "Next Tab", 1, ("Ctrl+}", "Ctrl+Shift+]") if mac else ("Ctrl+PgDown",)),
                ("previousTab", "Previous Tab", -1, ("Ctrl+{", "Ctrl+Shift+[") if mac else ("Ctrl+PgUp",))):
            act = self._action(text, partial(self._step_tab, step))
            act.setShortcuts([QKeySequence(k) for k in keys])
            self.action_map[name] = act
            go_menu.addAction(act)
        if sys.platform == "darwin":
            bar.addMenu("Window")  # filled by the native layer (NSApp.windowsMenu), else left to the system
        help_menu = bar.addMenu("&Help")
        help_menu.addAction(self._action("About AgentPROV", self._about, None, QAction.MenuRole.AboutRole))
        help_menu.addAction(self._action("Check for Updates…", lambda: self._about(check=True), None,
                                         QAction.MenuRole.ApplicationSpecificRole))
        # D-1130: the bundle's own agentprov in a Terminal (macOS: the application menu, beside Check for Updates…)
        from agentprov_gui.ui import clitool

        for key, (name, slot, tip) in {"installCli": (clitool.INSTALL_NAME, lambda: clitool.install(self),
                                                      clitool.INSTALL_TIP),
                                       "uninstallCli": (clitool.UNINSTALL_NAME, lambda: clitool.uninstall(self),
                                                        clitool.UNINSTALL_TIP)}.items():
            act = self._action(name, slot, None, QAction.MenuRole.ApplicationSpecificRole)
            set_action_tooltip(act, tip)
            act.setVisible(clitool.available())  # a checkout's or a package's app has no bundled agentprov
            self.action_map[key] = act
            help_menu.addAction(act)
        help_menu.setToolTipsVisible(True)
        help_menu.addAction(self._action("AgentPROV Help", partial(self.go, "Docs"), "Ctrl+?"))
        help_menu.addAction(self._action("Ask the Assistant", self.open_assistant))
        help_menu.addAction(self._action("Keyboard Shortcuts", self._shortcuts))

    # ------------------------------------------------------------------------------------------ Viewer tabs (D-845)
    def _viewer_current(self) -> bool:
        return not self._assistant_current() and self.pages.currentWidget() is self.viewer

    def _open_in_tab(self) -> None:
        if self._viewer_current():
            self.viewer.open_current_in_tab()

    def _close_tab(self) -> None:
        """⌘W: the Assistant tab when it is in front (D-1040); else the current execution tab; the window when the
        Viewer shows its Corpora tab or another page is shown."""
        if self._assistant_current():
            self.close_assistant()
        elif not (self._viewer_current() and self.viewer.close_current_tab()):
            self.close()

    def _close_other_tabs(self) -> None:
        if self._viewer_current():
            self.viewer.close_other_tabs()

    def _corpora_tab(self) -> None:
        self.go("Viewer")
        self.viewer.show_corpora()

    def _step_tab(self, step: int) -> None:
        """The Viewer's execution tabs while the Viewer is in front; else the window's tabs, the page and the Assistant
        (D-1040)."""
        if self._viewer_current():
            self.viewer.step_tab(step)
        elif self.tabs.count() > 1:
            self.tabs.setCurrentIndex((self.tabs.currentIndex() + step) % self.tabs.count())

    # ------------------------------------------------------------------------------------------ chrome (D-440)
    def _toggle_sidebar(self) -> None:
        self.sidebar.setVisible(not self.sidebar.isVisible())

    def _new_job_menu(self) -> None:
        if self.runs is not None:
            self.go("Runs")
            self.runs.new_btn.showMenu()

    def _search(self, text: str) -> None:
        """The toolbar search (the user's own input): the Viewer's id filter only (S15)."""
        self.go("Viewer")
        self.viewer.set_search(text.strip()[:200])

    def _install_chrome(self) -> None:
        from agentprov_gui.platform import native_chrome_enabled

        if native_chrome_enabled(self.settings.native_chrome):
            from agentprov_gui.platform import macos

            self.chrome = macos.install(self, self.action_map, on_search=self._search, on_flags=self._flags)
            if self.chrome is not None:
                self._flags(self.chrome.flags)
                self.chrome.set_subtitle("Viewer")
                self.viewer.search_changed.connect(self.chrome.set_search)  # AU-NG-5: the field follows the Viewer
                return
        self._qt_toolbar()

    def _qt_toolbar(self) -> None:
        """The Qt toolbar (Windows, Linux, and the macOS fallback): the same actions, and the search field."""
        from PySide6.QtWidgets import QLineEdit, QToolBar

        bar = QToolBar("Main", self)
        bar.setAccessibleName("Main toolbar")
        bar.setObjectName("main-toolbar")
        bar.setMovable(False)
        bar.setIconSize(QSize(16, 16))
        bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toolbar = bar
        for key in ("toggleSidebar", "openCorpus", "reload", "newJob", "devRun"):
            if key in self.action_map:
                bar.addAction(self.action_map[key])
                button = bar.widgetForAction(self.action_map[key])
                if button is not None:  # the action's own tooltip is only its name
                    set_control_tooltip(button, TOOLBAR_TIPS[key])
                    button.setProperty("apvGlyph", key)  # its drawn glyph (on the button, so menus stay without)
        search = QLineEdit(bar)
        search.setAccessibleName("Search execution ids")
        search.setPlaceholderText("Search ids")
        set_control_tooltip(search, SEARCH_TIP + " (press Return).")
        search.setMaximumWidth(260)
        search.returnPressed.connect(lambda: self._search(search.text()))
        self.viewer.search_changed.connect(lambda text: search.setText(text) if text != search.text() else None)
        spacer = QWidget(bar)
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        bar.addWidget(spacer)  # the search field on the right, as in the native toolbar
        bar.addWidget(search)
        self.addToolBar(bar)

    def _restyle(self) -> None:
        """The frame's colours from the theme's tokens (D-1060): the sidebar as a source list, the Qt toolbar and the
        status bar on the summary colour with a hairline, and the toolbar's drawn glyphs. Called at start and whenever
        the appearance changes (these sheets are the widgets' own, so the app-wide sheet's rebuild does not reach
        them)."""
        t = theme.tokens()
        self.sidebar.setStyleSheet(
            f"QListWidget#sidebar {{ background: {t.summary}; border: none; border-right: 1px solid {t.card_border};"
            f" padding-top: 4px; outline: 0; }}")
        self.statusBar().setStyleSheet(
            f"QStatusBar {{ background: {t.summary}; color: {t.secondary}; border-top: 1px solid {t.hairline}; }}"
            " QStatusBar::item { border: none; }")
        if self.toolbar is not None:
            self.toolbar.setStyleSheet(
                f"QToolBar#main-toolbar {{ background: {t.summary}; border: none; border-bottom: 1px solid {t.hairline};"
                f" padding: 4px 8px; spacing: 4px; }}"
                f" QToolBar#main-toolbar QToolButton {{ color: {t.text}; background: transparent;"
                f" border: 1px solid transparent; border-radius: 6px; padding: 3px 8px; }}"
                f" QToolBar#main-toolbar QToolButton:hover {{ background: {t.hover}; }}"
                f" QToolBar#main-toolbar QToolButton:pressed {{ background: {t.pressed}; }}"
                f" QToolBar#main-toolbar QToolButton:focus {{ border: 1px solid {t.accent}; }}")
            from PySide6.QtWidgets import QToolButton

            for button in self.toolbar.findChildren(QToolButton):
                key = button.property("apvGlyph")
                if isinstance(key, str):
                    button.setIcon(glyph_icon(key, QColor(t.secondary)))
        self.sidebar.viewport().update()

    def _flags(self, flags: Any) -> None:
        theme.ACCESS.update(differentiate=bool(flags.differentiate_without_colour),
                            increase_contrast=bool(flags.increase_contrast), reduce_motion=bool(flags.reduce_motion))

    def _open_dialog(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Open Corpus", str(self.settings.corpus_roots[0]))
        if path:
            self.go("Viewer")
            self.viewer.open_path(Path(path))

    def _settings(self) -> None:
        self.open_settings(None)

    def open_settings(self, pane: str | None) -> None:
        """The Settings dialog, on ``pane`` when given (Help › Assistant opens its own pane)."""
        dlg = SettingsDialog(self.settings, self, pane=pane)
        if dlg.exec():
            theme.apply_scheme(self.settings.theme)
            set_tooltips_shown(self.settings.show_tooltips)
            self.viewer.roots = self.settings.corpus_roots
            self.viewer.set_show_content_limit(self.settings.content_limit)
            self.viewer.set_exact_palette(self.settings.graph_palette == "exact")
            self.viewer.refresh()
            from agentprov_gui.jobs.manager import CliLocator, set_cli_choice, set_installed_program

            set_installed_program(self.settings.cli_program)
            set_cli_choice(self.settings.cli_choice)
            if self.runs is not None:
                self._apply_job_settings()
            self.docs.set_checkout(self.settings.checkout)
            self.assistant.cli = CliLocator.for_checkout(self.settings.checkout)
            self.assistant.reload()

    def _apply_job_settings(self) -> None:
        """New jobs use the checkout and the settings just saved (GR-32); running jobs keep their recorded argv."""
        from agentprov_gui.jobs.manager import CliLocator

        self.manager.cli = CliLocator.for_checkout(self.settings.checkout)
        self.runs._options.clear()  # the cached ``--help`` options were the old CLI's
        self.runs.stored.clear()  # and the cached agentprov settings may have changed
        self.package.checkout = self.settings.checkout
        self.licences.checkout = self.settings.checkout
        self.licences.reload()
        if self.statusBar().currentMessage().startswith("Viewer only"):
            self.statusBar().clearMessage()
        self.runs.new_btn.setEnabled(True)  # the check below disables it again for a checkout without a usable CLI
        self._platform_check(self.manager.cli)
        self._version_check()

    def _updates(self) -> None:
        """Check for Updates (D-1065): one controller for About, the menu item and the start-up notice; its commands are
        the configured CLI's (the jobs' manager, else the checkout's or the installed agentprov)."""
        from agentprov_gui import updates as U
        from agentprov_gui.ui.updates import UpdateController

        def run(argv: list[str], timeout: float | None) -> tuple[int, bytes, bytes]:
            if self.runs is not None:
                return self.manager.call(argv, timeout=timeout)
            from agentprov_gui.jobs.manager import CliLocator
            from agentprov_gui.live.cli import call

            return call(CliLocator.for_checkout(self.settings.checkout), argv, timeout=timeout)

        def current() -> Any:
            from agentprov_gui.jobs.manager import CliLocator

            return self.manager.cli if self.runs is not None else CliLocator.for_checkout(self.settings.checkout)

        def program() -> str:
            return str(current().kind)

        def identity() -> str:  # D-1130 review: the CLI the confirmation described is the one that installs
            cli = current()
            return repr((tuple(cli.program), tuple(cli.python), bool(cli.bundled)))

        self.updates = UpdateController(run, bundle=U.app_bundle(), gui=U.app_version(), program=program,
                                        identity=identity, parent=self)
        self.updates.notice.connect(self._update_notice)
        if self.runs is not None:  # D-1130: once the program has updated, the stale backend environments are rebuilt
            self._rebuild_after_update()

    def _rebuild_after_update(self) -> None:
        """The update's last step (D-1130): its confirmation says the rebuild follows when the program part is planned
        and the CLI runs from a checkout; after the program part has installed, ``agentprov backends rebuild-stale
        --allow-network`` starts as a job (on the Runs page), or the note says why not."""
        from agentprov_gui import updates as U
        from agentprov_gui.jobs import rebuild

        def notify(note: str) -> None:
            self.updates.result = [*self.updates.result, note]
            self.updates.changed.emit()
            self.statusBar().showMessage(note, 15_000)
            self.runs.refresh()

        def followup(plan: U.UpdatePlan) -> str | None:
            planned = any(part.name == rebuild.PROGRAM_PART for part in plan.parts)
            return rebuild.CONFIRM_LINE if planned and self.manager.cli.checkout is not None else None

        self.updates.after_update = rebuild.after_update(self.manager, notify)
        self.updates.followup = followup
        self.updates.prepare = rebuild.prepare

    def start_update_check(self) -> None:
        """The daily update check at start-up (``update check --if-stale`` unless ``update.auto_check`` is false); it
        never blocks the window and stays silent when it fails (offline, no CLI)."""
        self.updates.startup()

    def _update_notice(self, check: Any) -> None:
        """Once per new release: Update Now (About, the download and the confirmed install), Later (asked again at the
        next start) or Skip This Version (``update.last_notified``)."""
        from agentprov_gui.ui.updates import UpdateNotice

        dlg = UpdateNotice(check, self)
        dlg.exec()
        if dlg.choice == "skip" and check.release is not None:
            self.updates.skip(check.release)
        elif dlg.choice == "update":
            self._about(install=True)

    def _about(self, *, check: bool = False, install: bool = False) -> None:
        """About; ``check``: Help › Check for Updates… starts a check; ``install``: the notice's Update Now starts the
        download (the install waits for its confirmation)."""
        dlg = AboutDialog(self.settings.checkout, self, updates=self.updates)
        if check:
            self.updates.check_now()
        elif install:
            self.updates.download_and_install(dlg)
        dlg.exec()

    def _shortcuts(self) -> None:
        from agentprov_gui.ui.safe import safe_message_box

        safe_message_box(self, "Keyboard Shortcuts", "Keyboard shortcuts", informative=SHORTCUTS).exec()

    def scale_text(self, factor: float | None) -> None:
        """In-app text size, 85–200 % (D-446)."""
        app = QApplication.instance()
        if not isinstance(app, QApplication):
            return
        font = app.font()
        if self._base_point_size is None:
            self._base_point_size = font.pointSizeF()
        base = self._base_point_size
        current = font.pointSizeF()
        target = base if factor is None else min(base * 2.0, max(base * 0.85, current * factor))
        font.setPointSizeF(target)
        app.setFont(font)

    def _run_live(self) -> None:
        if self.runs is not None:
            self.go("Runs")
            self.runs.run_live()

    def _corpus_opened(self, name: str, seconds: float) -> None:
        if self.runs is not None and self.viewer.summary is not None:
            self.runs.opened_corpus = Path(self.viewer.summary.path)  # the Run live estimate's first source (§8.3)
        if self.chrome is not None:  # macOS: the title stays the app's, the corpus is the subtitle (HIG)
            self.chrome.set_subtitle(T.line(name, 80))
        else:
            self.setWindowTitle(f"AgentPROV — {T.window_title(T.line(name, 80))}")

    # ------------------------------------------------------------------------------------------ state
    def _restore(self) -> None:
        geometry = self.settings.store.value("window/geometry")
        if isinstance(geometry, QByteArray):
            self.restoreGeometry(geometry)

    def closeEvent(self, event: object) -> None:
        self.settings.store.setValue("window/geometry", self.saveGeometry())
        if self.runs is not None:
            self.system.shutdown()  # jobs keep running: closing the GUI never stops a job (D-392)
        super().closeEvent(event)  # type: ignore[arg-type]


SHORTCUTS = (
    "⌘O / Ctrl+O  Open corpus\n"
    "⌘R / F5      Reload the corpora list\n"
    "⌘1           Viewer (⌘2 to ⌘7: Runs, Logs, System, Licences, Package, Docs)\n"
    "⌘8           the Assistant, in a tab beside the page; ⌘W closes the tab (the chat is kept), ⌘⇧] ⌘⇧[ switch "
    "between it and the page; in the Assistant, ⌘↩ sends\n"
    "⌘?           AgentPROV Help (the Docs page)\n"
    "⌥⌘1 / ⌥⌘I   Viewer: show or hide the corpora list and the inspector (a collapsed pane's strip opens it too)\n"
    "Viewer tabs: Return or double-click opens an execution in a new tab; ⌘W closes it (on Corpora: the window), "
    "⌥⌘W closes the other tabs, ⇧⌘W closes the window, ⌘⇧] ⌘⇧[ next and previous tab (Ctrl+PgDown, Ctrl+PgUp "
    "elsewhere), ⌃Tab ⌃⇧Tab the sub-tabs, middle-click closes a tab\n"
    "⌘, / Ctrl+,  Settings\n"
    "Graph: ⌘+ ⌘− zoom, ⌘0 actual size, ⌘9 or F fit, Esc clear selection, the mouse wheel or pinch "
    "zooms under the pointer, drag or a two-finger trackpad scroll pans (⇧ + wheel scrolls)\n"
    "⌥⌘= ⌥⌘− ⌥⌘0  Text size bigger, smaller, default"
)
