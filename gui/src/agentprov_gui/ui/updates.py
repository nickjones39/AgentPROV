"""Check for Updates (D-1065, the GUI half): About's Updates section, the start-up notice and the install flow.

The app opens no connection (S11): :class:`UpdateController` runs the ``agentprov update`` commands of the configured
CLI (:mod:`agentprov_gui.updates` builds and reads them) in the background, so the window never waits on the network,
and one controller, owned by the main window, holds the state, so a download keeps going when About is closed.

* **Check for Updates** (About, and Help › Check for Updates…) runs ``update check --allow-network`` with this app's
  bundle and version; About shows the cached result first (``update status``, no network).
* **Download and Install…** runs ``update download --allow-network`` (the CLI verifies the bundle against
  ``SHA256SUMS`` and, when the package lists a release key, its signature), then asks the user, naming the folder that
  will be replaced and that the old version is kept for rollback, and only then runs ``update install --confirm
  --bundle PATH``. The app never replaces itself unasked. When the app is not a bundle (a checkout, a package install),
  the button shows the upgrade command the CLI prints (``update install`` without ``--bundle``) and installs nothing.
* **At start-up**, unless the setting ``update.auto_check`` is false, ``update check --if-stale`` runs once (the CLI
  fetches at most once a local day). When a newer release is out and it is not the one the user skipped
  (``update.last_notified``), :class:`UpdateNotice` asks once: Update Now, Later (asked again next launch) or Skip
  This Version (``agentprov settings set update.last_notified X.Y.Z``). Offline or with no CLI, nothing is shown.

Every result is shown as the CLI says it, in plain text (S1), with the "checked against SHA256SUMS only" note for a
release the package cannot check a signature of, and the quit-and-reopen instruction (Windows: applied after quit).
"""

from __future__ import annotations

import datetime as dt
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QDialog, QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from agentprov_gui import text as T
from agentprov_gui import updates as U
from agentprov_gui.ui import forms, theme
from agentprov_gui.ui.forms import CommandCard, FormPage, FormSection, StatusBadge
from agentprov_gui.ui.safe import ReadOnlyText, SafeLabel, choose, set_control_tooltip

__all__ = ["UpdateController", "UpdateNotice", "UpdatesSection", "confirm_install"]

#: how long each command may take (a download of up to 2 GiB on a slow line; the macOS disk image's copy)
TIMEOUTS: Final = {"status": 60.0, "check": 180.0, "download": 4 * 3600.0, "install": 1800.0, "settings": 60.0}
#: the button names (reverse parity, :mod:`agentprov_gui.parity`)
CHECK_NAME: Final = "Check for Updates"
INSTALL_NAME: Final = "Download and Install…"
COMMAND_NAME: Final = "Show the Upgrade Command"

#: ``run(argv, timeout)``: one ``agentprov`` call (exit code, stdout, stderr tail)
Runner = Callable[[list[str], float], tuple[int, bytes, bytes]]


def _when(value: str | None) -> str:
    """The CLI's UTC time as the computer's local time, named (``today 09:14 NZDT``); the raw text if unreadable."""
    from agentprov_gui.live.pricerefresh import local_time_text

    if not value:
        return ""
    try:
        when = dt.datetime.fromisoformat(value.strip())
    except ValueError:
        return f"{value} UTC"
    return local_time_text(when if when.tzinfo else when.replace(tzinfo=dt.UTC))


def _windows() -> bool:
    return sys.platform.startswith("win")


def confirm_install(parent: QWidget | None, download: U.Download, bundle: Path, current: str | None) -> bool:
    """The explicit confirmation before ``update install --confirm``: what is replaced, by what, how it was checked,
    that the old version is kept for rollback, and what happens next. Cancel is the default."""
    new = download.version or "the new version"
    lines = [f"This replaces the app's folder {T.line(str(bundle), 300)} (AgentPROV {current or 'of unknown version'}) "
             f"with AgentPROV {new} ({download.asset or 'the downloaded bundle'}), which agentprov update download "
             f"verified ({download.verification}{', signed by ' + download.signed_by if download.signed_by else ''}).",
             "The current version is kept beside it, in .AgentPROV-previous, so it can be restored with agentprov "
             f"update rollback --yes --bundle {T.line(str(bundle), 300)}."]
    if not download.signed:
        lines.append(U.UNSIGNED_NOTE)
    lines.append("Windows cannot replace a running app: the new version is applied once you quit AgentPROV; then open "
                 "it again." if _windows() else "Afterwards, quit AgentPROV and open it again to start the new version.")
    return choose(parent, "Install Update", f"Install AgentPROV {new}?", "\n\n".join(lines), "Cancel", "Install",
                  tips=("Keeps the app as it is; the verified download stays staged, so you can install it later.",
                        "Runs agentprov update install --confirm --bundle with this app's folder: replaces the app "
                        "and keeps the old version for rollback."))


class UpdateController(QObject):
    """The state of Check for Updates and the commands that change it, run off the UI thread (one at a time).

    ``run`` calls the configured CLI; ``bundle`` is the app's bundle folder (``None``: not a bundle, the upgrade
    command is shown instead of an install); ``gui`` this app's version. ``confirm`` asks before an install (a seam for
    the tests). :attr:`changed` fires whenever anything shown changes; :attr:`notice` carries the check the start-up
    notice is about."""

    changed = Signal()
    notice = Signal(object)

    def __init__(self, run: Runner, *, bundle: Path | None = None, gui: str | None = None,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.run = run
        self.bundle = bundle
        self.gui = gui
        self.check: U.Check | None = None
        self.download: U.Download | None = None
        self.install: U.Install | None = None
        self.busy = ""  # "status", "check", "download", "install", "settings" or ""
        self.status_line = ""  # what is happening, or why the last command gave nothing
        self.result: list[str] = []  # the last download's or install's outcome, as the CLI said it
        self.confirm: Callable[[QWidget | None, U.Download, Path, str | None], bool] = confirm_install
        self.read_status = False

    @property
    def installed(self) -> bool:
        """An install was made in this session (or waits for the app to quit): the running app is the old one."""
        return self.install is not None and self.install.action in ("installed", "waiting-for-quit")

    # ------------------------------------------------------------------ the commands
    def commands(self) -> list[tuple[str, list[str]]]:
        """The terminal commands of each action, as the app runs them (About's command card)."""
        out: list[tuple[str, list[str]]] = [
            ("The last check, from the cache (no network)", U.status_argv(self.bundle, self.gui)),
            ("Check for Updates", U.check_argv(self.bundle, self.gui))]
        if self.bundle is not None:
            out += [("Download and Install…: download and verify", U.download_argv()),
                    ("then, after you confirm, install (the old version is kept for rollback)",
                     U.install_argv(self.bundle, self.gui))]
        else:
            out.append(("Show the Upgrade Command (this app is not a bundle: nothing is installed)",
                        U.install_argv(None, self.gui)))
        return out

    def _start(self, what: str, argv: list[str], done: Callable[[tuple[int, bytes, bytes]], None],
               line: str) -> bool:
        from agentprov_gui.ui.worker import submit

        if self.busy:
            return False
        self.busy, self.status_line = what, line
        self.changed.emit()
        timeout = TIMEOUTS[what]

        def finished(result: tuple[int, bytes, bytes]) -> None:
            self.busy = ""
            done(result)
            self.changed.emit()

        def failed(code: str) -> None:
            self.busy = ""
            self.status_line = f"agentprov update could not be run ({T.line(code, 60)})."
            self.changed.emit()

        submit(self, lambda _s: self.run(argv, timeout), finished, failed)
        return True

    def load_status(self) -> None:
        """The cached check (no network), once per controller."""
        if self.read_status or self.check is not None:
            return
        self.read_status = True

        def done(result: tuple[int, bytes, bytes]) -> None:
            check = U.parse_check(result[0], result[1])
            if check is not None and self.check is None:
                self.check = check
                self.status_line = ""
            elif check is None:
                code, _out, err = result
                self.status_line = U.reason(code, err) if code else (
                    "agentprov update status gave no answer this app reads (is the CLI older than this app?).")

        self._start("status", U.status_argv(self.bundle, self.gui), done, "Reading the last check…")

    def check_now(self) -> bool:
        """Check for Updates: ask GitHub now (through the CLI)."""
        def done(result: tuple[int, bytes, bytes]) -> None:
            check = U.parse_check(result[0], result[1])
            if check is None:
                self.status_line = "The check failed: " + U.reason(result[0], result[2])
                return
            self.check, self.status_line = check, ""

        return self._start("check", U.check_argv(self.bundle, self.gui), done,
                           "Checking for updates (agentprov update check)…")

    def startup(self) -> None:
        """The daily check at start-up: nothing unless ``update.auto_check`` is not false; :attr:`notice` once a newer
        release is found that the user has not skipped. Failures (offline, no CLI) stay silent."""
        from agentprov_gui import settings_client
        from agentprov_gui.ui.worker import submit

        if self.busy:
            return

        def work(_s: object) -> tuple[Any, tuple[int, bytes, bytes] | None]:
            stored = settings_client.read(lambda argv: self.run(list(argv), TIMEOUTS["settings"]), "update.")
            if stored is None or stored.get(U.AUTO_CHECK) is False:
                return stored, None
            return stored, self.run(U.check_argv(self.bundle, self.gui, if_stale=True), TIMEOUTS["check"])

        def done(result: tuple[Any, tuple[int, bytes, bytes] | None]) -> None:
            self.busy = ""
            stored, ran = result
            check = U.parse_check(ran[0], ran[1]) if ran is not None else None
            if check is not None:
                self.check, self.status_line = check, ""
            self.changed.emit()
            if U.notify(check, stored.get(U.LAST_NOTIFIED) if isinstance(stored, dict) else None):
                self.notice.emit(check)

        def failed(_code: str) -> None:
            self.busy = ""
            self.changed.emit()

        self.busy = "check"
        self.changed.emit()
        submit(self, work, done, failed)

    def skip(self, version: str) -> None:
        """Skip This Version: ``settings set update.last_notified X.Y.Z``."""
        def done(result: tuple[int, bytes, bytes]) -> None:
            self.status_line = "" if result[0] == 0 else "Skipping the version was not saved: " + U.reason(
                result[0], result[2])

        self._start("settings", U.skip_argv(version), done, f"Skipping AgentPROV {version}…")

    def download_and_install(self, parent: QWidget | None = None) -> bool:
        """Download and Install…: download and verify, ask, install. Without a bundle: the upgrade command only. Once
        an install was made (or waits for the app to quit), nothing more until the app is started again: a second
        install from the old running app would replace the version kept for rollback."""
        if self.busy or self.installed:
            return False
        self.result = []
        if self.bundle is None:
            return self._start("install", U.install_argv(None, self.gui), self._installed,
                               "Asking agentprov how this install is upgraded…")

        def downloaded(result: tuple[int, bytes, bytes]) -> None:
            got = U.parse_download(result[0], result[1])
            if got is None:
                self.status_line = "The download was refused or failed; nothing is installed: " + U.reason(
                    result[0], result[2])
                return
            self.download = got
            note = [U.UNSIGNED_NOTE] if not got.signed else []
            self.result = [f"Downloaded and verified {got.asset or 'the bundle'} of {got.tag or got.version} "
                           f"({got.verification}{', signed by ' + got.signed_by if got.signed_by else ''}).", *note]
            self.busy, self.status_line = "confirm", "Waiting for your confirmation…"
            self.changed.emit()
            assert self.bundle is not None
            current = self.check.gui if self.check is not None and self.check.gui else self.gui
            try:
                confirmed = self.confirm(QApplication.activeWindow() or parent, got, self.bundle, current)
            finally:
                self.busy = ""
            if not confirmed:
                self.status_line = ("Not installed. The verified download stays staged; Download and Install… "
                                    "asks again.")
                return
            self._start("install", U.install_argv(self.bundle, self.gui), self._installed,
                        f"Installing AgentPROV {got.version or ''} (agentprov update install)…")

        return self._start("download", U.download_argv(), downloaded,
                           "Downloading and verifying the update (agentprov update download)…")

    def _installed(self, result: tuple[int, bytes, bytes]) -> None:
        got = U.parse_install(result[0], result[1])
        if got is None:
            self.status_line = "The install was refused or failed; the app is unchanged: " + U.reason(result[0],
                                                                                                    result[2])
            return
        self.install = got
        self.status_line = ""
        if got.action in ("installed", "waiting-for-quit"):
            self.status_line = ("Installed. Quit AgentPROV and open it again to start the new version." if got.action
                                == "installed" else "Ready. Quit AgentPROV: the update is applied once it has closed.")
        lines = list(got.lines) or ([got.text] if got.text else [])
        if got.action == "command" and got.command:
            lines.append("Run this command in a terminal; the app installs nothing itself.")
        self.result = [*self.result, *lines]


class UpdatesSection(QWidget):
    """About's Updates section: the last check, the newest release and its notes, Check for Updates, Download and
    Install… (or Show the Upgrade Command), the outcome, and the terminal commands of each action."""

    def __init__(self, controller: UpdateController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAccessibleName("Updates")
        self.controller = controller
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        self.section = FormSection("Updates", parent=self)
        lay.addWidget(self.section)
        sec = self.section
        self.last = SafeLabel("", name="Last check", parent=sec.card)
        self.last.setWordWrap(True)
        sec.add_row("Last check", self.last, tip="When agentprov update check last asked GitHub for the newest "
                                                 "release, in this computer's time zone, and what it found (agentprov "
                                                 "update status reads it without the network).")
        self.badge = StatusBadge("", name="Update status", parent=sec.card)
        set_control_tooltip(self.badge, "Whether a newer final release than this app or its agentprov is published "
                                        "(drafts and pre-releases are ignored).")
        self.latest = SafeLabel("", name="Newest release", parent=sec.card)
        self.latest.setWordWrap(True)
        self.latest_row = sec.add_row("Newest release", self.latest, trailing=(self.badge,),
                                      tip="The newest final release of nickjones39/AgentPROV, when it was published "
                                          "and the bundle for this platform.")
        self.notes = ReadOnlyText(name="Release notes", parent=sec.card, wrap=True)
        self.notes.setMinimumHeight(120)
        self.notes_row = sec.add_row("Release notes", self.notes, top=True,
                                     tip="The release's notes as plain text (no links or formatting are followed).")
        buttons = QWidget(sec.card)
        row = QHBoxLayout(buttons)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        self.check_btn = QPushButton(CHECK_NAME, buttons)
        self.check_btn.setAccessibleName(CHECK_NAME)
        self.check_btn.setAutoDefault(False)
        self.check_btn.clicked.connect(controller.check_now)
        set_control_tooltip(self.check_btn, "Runs agentprov update check --allow-network: one request to GitHub's "
                                            "releases API for nickjones39/AgentPROV, made by the agentprov program "
                                            "(the app itself opens no connection).")
        row.addWidget(self.check_btn)
        bundled = controller.bundle is not None
        self.install_btn = QPushButton(INSTALL_NAME if bundled else COMMAND_NAME, buttons)
        self.install_btn.setAccessibleName(INSTALL_NAME if bundled else COMMAND_NAME)
        self.install_btn.setAutoDefault(False)
        self.install_btn.clicked.connect(lambda: controller.download_and_install(self.window()))
        set_control_tooltip(self.install_btn, (
            "Runs agentprov update download --allow-network (the bundle is verified against the release's SHA256SUMS "
            "and, when the package lists a release key, its signature), then asks you before agentprov update install "
            "--confirm replaces the app; the old version is kept for rollback." if bundled else
            "This app runs from a checkout or a package install, not a bundle: runs agentprov update install without "
            "--bundle, which prints the command that upgrades it. Nothing is installed."))
        row.addWidget(self.install_btn)
        row.addStretch(1)
        self.actions_row = sec.add_row("", buttons)
        self.status = forms.caption("", name="Update progress", parent=sec.card, role="secondary")
        set_control_tooltip(self.status, "What the update commands are doing, or why the last one gave nothing.")
        sec.add(self.status)
        self.result = SafeLabel("", name="Update result", parent=sec.card)
        self.result.setWordWrap(True)
        set_control_tooltip(self.result, "What agentprov update download and install said, as they said it.")
        sec.add(self.result)
        self.command = CommandCard(name="Update commands", title="Terminal commands", parent=self)
        self.command.copy_button.setAccessibleName("Copy the update commands")
        set_control_tooltip(self.command.copy_button, "Copies the agentprov update commands shown below, one per line, "
                                                      "so they can be run in a terminal.")
        lay.addWidget(self.command)
        controller.changed.connect(self.refresh)
        self.refresh()
        controller.load_status()

    def refresh(self) -> None:
        c = self.controller
        check = c.check
        if check is None or check.checked_at is None:
            self.last.set_plain("Never checked" if check is not None else "Not read yet")
        else:
            outcome = ("an update is available" if check.update_available else "up to date"
                       if check.update_available is False else "the versions cannot be compared")
            self.last.set_plain(f"{_when(check.checked_at)}: {outcome}")
        available = check is not None and check.update_available is True
        if check is not None and check.latest is not None:
            when = f", published {_when(check.published_at)}" if check.published_at else ""
            asset = (f"; bundle for {check.platform}: {check.asset}" if check.asset else
                     f"; no bundle for {check.platform or 'this platform'}" if c.bundle is not None else "")
            self.latest.set_plain(f"AgentPROV {check.latest}{when}{asset}")
            self.badge.set_status("Update available" if available else "Up to date" if
                                  check.update_available is False else "Not comparable",
                                  "info" if available else "ok" if check.update_available is False else "neutral")
        self.latest_row.setVisible(check is not None and check.latest is not None)
        self.notes.setPlainText(check.notes if available and check is not None else "")
        if available and check is not None and check.notes_truncated:
            self.notes.appendPlainText("\n[The notes are cut at 8000 characters; the release page has the rest.]")
        self.notes_row.setVisible(available and bool(check and check.notes))
        self.check_btn.setEnabled(not c.busy)
        can_install = available and (c.bundle is None or (check is not None and check.asset is not None))
        self.install_btn.setEnabled(not c.busy and can_install and not c.installed)
        self.status.set_plain(c.status_line)
        self.status.setVisible(bool(c.status_line))
        self.result.set_plain("\n".join(c.result))
        self.result.setVisible(bool(c.result))
        commands = c.commands()
        if c.install is not None and c.install.command:
            commands.append(("The upgrade command agentprov printed (run it yourself)", list(c.install.command)))
        self.command.set_commands(commands)


class UpdateNotice(QDialog):
    """The start-up notice, once per new release: "AgentPROV X.Y.Z is available", the notes (plain text), and Update
    Now, Later or Skip This Version (:attr:`choice` is ``update``, ``later`` or ``skip``)."""

    def __init__(self, check: U.Check, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        version = check.latest or "a new version"
        self.setWindowTitle("Software Update")
        self.setAccessibleName("Software Update")
        self.resize(560, 480)
        self.choice = "later"
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        page = FormPage(name="Software Update", parent=self)
        lay.addWidget(page, 1)
        title = SafeLabel(f"AgentPROV {version} is available", name="Update title", parent=page.column)
        title.setFont(theme.scaled_font("title"))
        title.setWordWrap(True)
        page.add(title)
        have = ", ".join(x for x in (f"the app {check.gui}" if check.gui else "",
                                     f"agentprov {check.core}" if check.core else "") if x)
        when = f" It was published {_when(check.published_at)}." if check.published_at else ""
        page.add(forms.caption(f"You have {have or 'an older version'}.{when} Nothing is downloaded or installed "
                               "until you choose Update Now and confirm.", name="Update summary", parent=page.column,
                               role="secondary"))
        sec = FormSection("Release notes", parent=page.column)
        self.notes = ReadOnlyText(name="Release notes", parent=sec.card, wrap=True)
        self.notes.setPlainText(check.notes or "This release has no notes.")
        self.notes.setMinimumHeight(180)
        sec.add(self.notes)
        page.add(sec)
        footer = QWidget(self)
        footer.setProperty("apvRole", "footer")
        row = QHBoxLayout(footer)
        row.setContentsMargins(20, 12, 20, 12)
        row.setSpacing(10)
        self.skip_btn = self._button("Skip This Version", "skip", footer,
                                     f"Does not tell you about AgentPROV {version} again (agentprov settings set "
                                     f"update.last_notified {version}); a later release is announced as usual.")
        self.skip_btn.setEnabled(check.release is not None)
        row.addWidget(self.skip_btn)
        row.addStretch(1)
        row.addWidget(self._button("Later", "later", footer, "Closes this notice; it asks again the next time the app "
                                                             "starts."))
        self.update_btn = self._button("Update Now", "update", footer,
                                       "Opens About and downloads and verifies the update (agentprov update download "
                                       "--allow-network); it asks you again before anything is replaced.")
        self.update_btn.setDefault(True)
        row.addWidget(self.update_btn)
        lay.addWidget(footer)

    def _button(self, text: str, choice: str, parent: QWidget, tip: str) -> QPushButton:
        button = QPushButton(text, parent)
        button.setAccessibleName(text)
        button.setAutoDefault(False)
        set_control_tooltip(button, tip)

        def chosen() -> None:
            self.choice = choice
            self.accept() if choice != "later" else self.reject()

        button.clicked.connect(chosen)
        return button
