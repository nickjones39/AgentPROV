"""The main window (design §6; macos-design §3.1–3.4; D-442).

A sidebar with sections (Corpora: Viewer; Jobs and Release arrive with G2) | the active page. On macOS, About and
Settings… sit in the App menu (Qt's ``AboutRole``/``PreferencesRole`` move them there) and Settings opens with ⌘,;
elsewhere they are in the Help and Edit menus. Every action has a menu item; the Go menu switches pages (⌘1 …).
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Any

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QAction, QFont, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QStackedWidget,
    QStatusBar,
    QWidget,
)

from agentprov_gui import text as T
from agentprov_gui.paths import agentprov_home, layout_cache_dir
from agentprov_gui.settings import Settings
from agentprov_gui.ui import theme
from agentprov_gui.ui.dialogs import AboutDialog, SettingsDialog
from agentprov_gui.ui.safe import SafeLabel
from agentprov_gui.ui.viewer import ViewerPage

__all__ = ["MainWindow"]

#: The CLI's closed outcome vocabulary; anything else in ended.json/summary.json shows as "ended" (S15).
_OUTCOMES = frozenset({"ok", "failures", "usage", "environment", "refused", "unsupported", "internal", "interrupted",
                       "signal"})


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings, *, cache_dir: Path | None = None, home: Path | None = None,
                 jobs: bool = True) -> None:
        super().__init__()
        self.settings = settings
        self._base_point_size: float | None = None
        self.setWindowTitle("AgentPROV")
        self.setAccessibleName("AgentPROV main window")
        self.setMinimumSize(900, 560)
        self.resize(1400, 900)
        central = QWidget(self)
        lay = QHBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        self.sidebar = QListWidget(central)
        self.sidebar.setAccessibleName("Navigation")
        self.sidebar.setMaximumWidth(232)
        self.sidebar.setMinimumWidth(160)
        self.pages = QStackedWidget(central)
        self.pages.setAccessibleName("Pages")
        lay.addWidget(self.sidebar)
        lay.addWidget(self.pages, 1)
        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar(self))
        self.statusBar().setAccessibleName("Status")
        self.viewer = ViewerPage(settings.corpus_roots, cache_dir if cache_dir is not None else layout_cache_dir(home),
                                 settings.content_limit, self)
        self.viewer.set_exact_palette(settings.graph_palette == "exact")
        self.viewer.status_message.connect(lambda msg: self.statusBar().showMessage(msg))
        self.viewer.corpus_opened.connect(self._corpus_opened)
        self._add_section("Corpora")
        self._add_page("Viewer", self.viewer)
        self.runs: Any = None
        if jobs:
            self._jobs_pages(home or agentprov_home())
        self.sidebar.currentRowChanged.connect(self._nav)
        self.sidebar.setCurrentRow(1)
        self.action_map: dict[str, QAction] = {}
        self.chrome: Any = None
        self._running_ids: set[str] = set()
        self._menus()
        self._restore()
        self._install_chrome()
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
        self.activity = SafeLabel("", name="Job activity", parent=self)
        self.statusBar().addPermanentWidget(self.activity)
        self._version_check()

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
        self.runs.new_job("render", {"corpus": corpus, "ex": ex})

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
            self.system.follow_job(job.pid, job.record.get("pid_create_time"))

    def _jobs_changed(self, running: int, ended: int) -> None:
        self.activity.set_plain(f"● {running} running" if running else f"{ended} jobs")
        jobs = {j.job_id: j for j in self.manager.jobs.values()}
        now_running = {k for k, j in jobs.items() if j.state == "running"}
        for job_id in self._running_ids - now_running:
            self._job_ended(jobs[job_id])
        self._running_ids = now_running
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
            self.statusBar().showMessage("Viewer only: no AgentPROV checkout with a CLI is configured.")
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

    # ------------------------------------------------------------------------------------------ navigation
    def _add_section(self, title: str) -> None:
        item = QListWidgetItem(title.upper())
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        font = QFont(item.font())
        font.setBold(True)
        font.setPointSizeF(max(font.pointSizeF() * 0.85, 9.0))
        item.setFont(font)
        self.sidebar.addItem(item)

    def _add_page(self, title: str, page: QWidget) -> None:
        item = QListWidgetItem(title)
        item.setData(Qt.ItemDataRole.UserRole, self.pages.addWidget(page))
        self.sidebar.addItem(item)

    def _nav(self, row: int) -> None:
        item = self.sidebar.item(row)
        index = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if isinstance(index, int):
            self.pages.setCurrentIndex(index)

    def go(self, title: str) -> None:
        for i in range(self.sidebar.count()):
            if self.sidebar.item(i).text() == title:
                self.sidebar.setCurrentRow(i)
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
        size_menu = view_menu.addMenu("Text Size")
        size_menu.addAction(self._action("Bigger", lambda: self.scale_text(1.1), "Ctrl+Alt+="))
        size_menu.addAction(self._action("Smaller", lambda: self.scale_text(1 / 1.1), "Ctrl+Alt+-"))
        size_menu.addAction(self._action("Default", lambda: self.scale_text(None), "Ctrl+Alt+0"))
        go_menu = bar.addMenu("&Go")
        for i, page in enumerate(("Viewer", "Runs", "Logs", "System", "Licences", "Package"), 1):
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
        help_menu.addAction(self._action("Keyboard Shortcuts", self._shortcuts))

    # ------------------------------------------------------------------------------------------ Viewer tabs (D-845)
    def _viewer_current(self) -> bool:
        return self.pages.currentWidget() is self.viewer

    def _open_in_tab(self) -> None:
        if self._viewer_current():
            self.viewer.open_current_in_tab()

    def _close_tab(self) -> None:
        """⌘W: the current execution tab; the window when the Viewer shows its Corpora tab or another page is shown."""
        if not (self._viewer_current() and self.viewer.close_current_tab()):
            self.close()

    def _close_other_tabs(self) -> None:
        if self._viewer_current():
            self.viewer.close_other_tabs()

    def _corpora_tab(self) -> None:
        self.go("Viewer")
        self.viewer.show_corpora()

    def _step_tab(self, step: int) -> None:
        if self._viewer_current():
            self.viewer.step_tab(step)

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
        self.viewer.ex_filter.setText(text.strip()[:200])

    def _install_chrome(self) -> None:
        from agentprov_gui.platform import native_chrome_enabled

        if native_chrome_enabled(self.settings.native_chrome):
            from agentprov_gui.platform import macos

            self.chrome = macos.install(self, self.action_map, on_search=self._search, on_flags=self._flags)
            if self.chrome is not None:
                self._flags(self.chrome.flags)
                self.chrome.set_subtitle("Viewer")
                return
        self._qt_toolbar()

    def _qt_toolbar(self) -> None:
        """The Qt toolbar (Windows, Linux, and the macOS fallback): the same actions, and the search field."""
        from PySide6.QtWidgets import QLineEdit, QToolBar

        bar = QToolBar("Main", self)
        bar.setAccessibleName("Main toolbar")
        bar.setObjectName("main-toolbar")
        for key in ("toggleSidebar", "openCorpus", "reload", "newJob", "devRun"):
            if key in self.action_map:
                bar.addAction(self.action_map[key])
        search = QLineEdit(bar)
        search.setAccessibleName("Search execution ids")
        search.setPlaceholderText("Search ids")
        search.setMaximumWidth(260)
        search.returnPressed.connect(lambda: self._search(search.text()))
        bar.addWidget(search)
        self.addToolBar(bar)

    def _flags(self, flags: Any) -> None:
        theme.ACCESS.update(differentiate=bool(flags.differentiate_without_colour),
                            increase_contrast=bool(flags.increase_contrast), reduce_motion=bool(flags.reduce_motion))

    def _open_dialog(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Open Corpus", str(self.settings.corpus_roots[0]))
        if path:
            self.go("Viewer")
            self.viewer.open_path(Path(path))

    def _settings(self) -> None:
        dlg = SettingsDialog(self.settings, self)
        if dlg.exec():
            theme.apply_scheme(self.settings.theme)
            self.viewer.roots = self.settings.corpus_roots
            self.viewer.set_show_content_limit(self.settings.content_limit)
            self.viewer.set_exact_palette(self.settings.graph_palette == "exact")
            self.viewer.refresh()
            if self.runs is not None:
                self._apply_job_settings()

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
        self._version_check()

    def _about(self) -> None:
        AboutDialog(self.settings.checkout, self).exec()

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
    "⌘1           Viewer\n"
    "Viewer tabs: Return or double-click opens an execution in a new tab; ⌘W closes it (on Corpora: the window), "
    "⌥⌘W closes the other tabs, ⇧⌘W closes the window, ⌘⇧] ⌘⇧[ next and previous tab (Ctrl+PgDown, Ctrl+PgUp "
    "elsewhere), ⌃Tab ⌃⇧Tab the sub-tabs, middle-click closes a tab\n"
    "⌘, / Ctrl+,  Settings\n"
    "Graph: ⌘+ ⌘− zoom, ⌘0 actual size, ⌘9 or F fit, Esc clear selection, ⌥/⌘ + wheel or pinch to zoom\n"
    "⌥⌘= ⌥⌘− ⌥⌘0  Text size bigger, smaller, default"
)
