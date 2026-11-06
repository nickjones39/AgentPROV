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
* **Only the agentprov program behind** (D-1070): when the check says the ``agentprov`` this app runs (the configured
  checkout or package install) is older than the newest release but the app is not, replacing the bundle would not
  change that program. The notice says so and offers Update agentprov…, and About's button becomes Update agentprov…;
  no bundle is downloaded or installed.
* **The whole software, one confirmation** (D-1130): Download and Install… (or Update agentprov…) first asks the CLI
  how the program it runs is installed (``update install`` without a flag; nothing changes) when that program is
  behind and is not the bundle's own copy (which the bundle install updates with the app). It then downloads and
  verifies what it can (the app's bundle; for a pip, uv tool or pipx install the release's wheels), and asks once, in
  one dialog, naming each part it will replace (from which version to which, how it was verified, what is kept to go
  back to) and each part it cannot update and why, with the command to run. Only after Install does it run ``update
  install --confirm --bundle`` and then ``update install --package --confirm`` or ``update install --checkout --confirm
  --allow-network``. A part that cannot be updated is never attempted.

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

__all__ = ["UpdateController", "UpdateNotice", "UpdatesSection", "confirm_update"]

#: how long each command may take (a download of up to 2 GiB on a slow line; the macOS disk image's copy)
#: ``None``: no time limit. A confirmed install ("apply": pip, uv pip, git and uv sync, the bundle swap) is never killed
#: part of the way through (D-1130 review): a package install keeps no previous version, so a kill could leave it half
#: replaced. "install" is the plan query (``update install`` without a flag), which changes nothing
TIMEOUTS: Final[dict[str, float | None]] = {"status": 60.0, "check": 180.0, "download": 4 * 3600.0, "install": 1800.0,
                                            "apply": None, "settings": 60.0}
#: the button names (reverse parity, :mod:`agentprov_gui.parity`)
CHECK_NAME: Final = "Check for Updates"
INSTALL_NAME: Final = "Download and Install…"
#: D-1130: only the agentprov program to update (the app is current, or the app is not a bundle)
PROGRAM_NAME: Final = "Update agentprov…"

#: ``run(argv, timeout)``: one ``agentprov`` call (exit code, stdout, stderr tail); ``timeout`` ``None``: no limit
Runner = Callable[[list[str], float | None], tuple[int, bytes, bytes]]


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


def confirm_update(parent: QWidget | None, plan: U.UpdatePlan) -> bool:
    """The one explicit confirmation before anything is replaced (D-1130): each part replaced (the versions, how it was
    verified, what is kept to go back to), each part that cannot be updated and why, and what happens next. Cancel is
    the default."""
    lines: list[str] = []
    for part in plan.parts:
        label = "Source" if "--checkout" in part.argv else "Verified"  # a git pull is not a verification
        lines.append(f"{part.name} ({part.detail}): {part.from_version or 'unknown version'} → "
                     f"{part.to_version or 'the new version'}. {label}: {part.verified}. Kept: {part.keeps}.")
    for what, why, command in plan.cannot:
        lines.append(f"Not updated: {what}, because {why}." + (f" Run it yourself: {command}" if command else ""))
    if plan.followup:
        lines.append(plan.followup)
    if any(not part.signed for part in plan.parts):
        lines.append(U.UNSIGNED_NOTE)
    if any(part.name == "The app" for part in plan.parts):
        lines.append("Windows cannot replace a running app: the new version is applied once you quit AgentPROV; then "
                     "open it again." if _windows() else "Afterwards, quit AgentPROV and open it again to start the "
                     "new version.")
    names = " and ".join(part.name[4:] if part.name.startswith("The ") else part.name for part in plan.parts)
    title = f"Install AgentPROV {plan.to_version}?" if any(p.name == "The app" for p in plan.parts) and \
        plan.to_version else f"Update {names}?"
    return choose(parent, "Install Update", title, "\n\n".join(lines), "Cancel", "Install",
                  tips=("Changes nothing; a verified download stays staged, so Download and Install… can use it later.",
                        "Replaces each part named here, one after the other, with the agentprov update install "
                        "command shown in About; a part that cannot be updated is not touched."))


class UpdateController(QObject):
    """The state of Check for Updates and the commands that change it, run off the UI thread (one at a time).

    ``run`` calls the configured CLI; ``bundle`` is the app's bundle folder (``None``: not a bundle, the upgrade
    command is shown instead of an install); ``gui`` this app's version. ``confirm`` asks before an install (a seam for
    the tests). :attr:`changed` fires whenever anything shown changes; :attr:`notice` carries the check the start-up
    notice is about."""

    changed = Signal()
    notice = Signal(object)

    def __init__(self, run: Runner, *, bundle: Path | None = None, gui: str | None = None,
                 program: Callable[[], str] | None = None, identity: Callable[[], str] | None = None,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.run = run
        #: which agentprov ``run`` calls, as text (D-1130 review): taken when Download and Install… starts and compared
        #: before anything is installed, so a CLI changed in Settings › General meanwhile never installs what the
        #: confirmation described for another one
        self.identity = identity if identity is not None else (lambda: "")
        self._identity_at_start = ""
        self._failed: list[str] = []  # the parts of this install chain that were not updated
        self._app_line = ""  # the app part's instruction to quit (and reopen), kept for the status at the chain's end
        self.bundle = bundle
        self.gui = gui
        #: which agentprov ``run`` calls (:attr:`agentprov_gui.jobs.manager.CliLocator.kind`): ``bundled`` is the
        #: bundle's own copy, updated with the app; anything else may need its own update (D-1130)
        self.program = program if program is not None else (lambda: "unknown")
        self.check: U.Check | None = None
        self.download: U.Download | None = None
        self.install: U.Install | None = None
        self.plan_doc: U.Install | None = None  # how the program is installed (update install, no flag)
        self.package: U.Download | None = None  # the program's verified wheels (a package install)
        self.program_install: U.Install | None = None  # the program's update, once made
        self.plan: U.UpdatePlan | None = None
        self.busy = ""  # "status", "check", "download", "install", "settings" or ""
        self.status_line = ""  # what is happening, or why the last command gave nothing
        self.result: list[str] = []  # the last download's or install's outcome, as the CLI said it
        self.confirm: Callable[[QWidget | None, U.UpdatePlan], bool] = confirm_update
        #: the update flow's last step (D-1130): called once, on the UI thread, after the last part's install has
        #: finished, with the parts that were installed (empty when none was). The main window hooks the backend
        #: environments' rebuild here (``agentprov backends rebuild-stale``, its own session); ``None``: nothing
        self.after_update: Callable[[list[str]], None] | None = None
        #: the sentence the one confirmation says about that step, from the plan (``None``: none); set together
        #: with :attr:`after_update` so the user is told before confirming what runs afterwards
        self.followup: Callable[[U.UpdatePlan], str | None] | None = None
        #: called once before the first part installs (D-1130 review): loads what runs after a bundle swap (the
        #: ``after_update`` step), since a module first imported afterwards would come from the new bundle's files
        self.prepare: Callable[[], None] | None = None
        self.read_status = False

    @property
    def installed(self) -> bool:
        """An install was made in this session (or waits for the app to quit): the running app is the old one, or the
        program changed under it; nothing more until the app starts again (and checks again)."""
        app = self.install is not None and self.install.action in ("installed", "waiting-for-quit")
        program = self.program_install is not None and self.program_install.action == "installed"
        return app or program

    @property
    def bundle_update(self) -> bool:
        """Download and Install… replaces the app's bundle: the app is a bundle and the last check did not find only
        the agentprov program it runs behind (D-1070: then only that program is updated)."""
        return self.bundle is not None and not (self.check is not None and self.check.cli_only)

    @property
    def program_update(self) -> bool:
        """The agentprov program the app runs needs its own update (D-1130): the check says it is behind, it is not
        the bundle's own copy (which the bundle install updates), or the app is no bundle at all (then the program is
        the only part there is)."""
        if self.program() == "bundled" and self.bundle_update:
            return False
        if not self.bundle_update:
            return True
        return self.check is not None and self.check.behind_core is True

    # ------------------------------------------------------------------ the commands
    def commands(self) -> list[tuple[str, list[str]]]:
        """The terminal commands of each action, as the app runs them (About's command card)."""
        out: list[tuple[str, list[str]]] = [
            ("The last check, from the cache (no network)", U.status_argv(self.bundle, self.gui)),
            ("Check for Updates", U.check_argv(self.bundle, self.gui))]
        if self.bundle_update:
            out += [("Download and Install…: download and verify the app", U.download_argv()),
                    ("then, after you confirm, install it (the old version is kept for rollback)",
                     U.install_argv(self.bundle, self.gui))]
        if self.program_update:
            out.append(("How the agentprov program the app runs is installed, and whether agentprov can update it "
                        "(changes nothing)", U.plan_argv()))
            auto = self.plan_doc.automatic if self.plan_doc is not None else None
            if auto is not None and auto.available and auto.how == "package":
                out += [("its release wheels, downloaded and verified (never PyPI)", U.package_download_argv()),
                        ("then, after you confirm, installed with its own installer (no dependency resolution, no "
                         "index)", U.package_install_argv())]
            elif auto is not None and auto.available and auto.how == "checkout":
                out.append(("after you confirm: git pull --ff-only origin main and uv sync --frozen --group docs in "
                            "the checkout", U.checkout_install_argv()))
        return out

    def _start(self, what: str, argv: list[str], done: Callable[[tuple[int, bytes, bytes]], None],
               line: str, *, continue_on_error: bool = False) -> bool:
        """Run one command off the UI thread. ``continue_on_error``: when the command could not be run at all, ``done``
        still gets a failed result (exit 70), so an install chain goes on to its next part (D-1130 review)."""
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
            if continue_on_error:
                done((70, b"", f"agentprov update could not be run ({code})".encode("utf-8", "replace")))
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
        """Download and Install… (D-1130): ask how the program is installed (when it needs its own update), download
        and verify the app's bundle and the program's wheels, ask once, then install each part. Without a part agentprov
        can update, the upgrade command is shown and nothing is installed. Once an install was made (or waits for the
        app to quit), nothing more until the app is started again: a second install from the old running app would
        replace the version kept for rollback."""
        if self.busy or self.installed:
            return False
        self.result, self.download, self.package, self.plan_doc, self.plan = [], None, None, None, None
        self._identity_at_start = self.identity()
        self._parent = parent
        if self.program_update:
            return self._start("install", U.plan_argv(), self._planned,
                               "Asking agentprov how the program this app runs is installed…")
        return self._download_app()

    # The steps, each started when the one before has finished (one command at a time).
    def _planned(self, result: tuple[int, bytes, bytes]) -> None:
        got = U.parse_install(result[0], result[1])
        if got is None:
            self.status_line = "agentprov did not say how it is installed; nothing is changed: " + U.reason(
                result[0], result[2])
            return
        self.plan_doc = got
        self._download_app()

    def _download_app(self) -> bool:
        if not self.bundle_update:
            return self._download_program()

        def downloaded(result: tuple[int, bytes, bytes]) -> None:
            got = U.parse_download(result[0], result[1])
            if got is None:
                self.status_line = "The download was refused or failed; nothing is installed: " + U.reason(
                    result[0], result[2])
                return
            self.download = got
            note = [U.UNSIGNED_NOTE] if not got.signed else []
            self.result = [*self.result, f"Downloaded and verified {got.asset or 'the bundle'} of "
                                         f"{got.tag or got.version} ({got.verification}"
                                         f"{', signed by ' + got.signed_by if got.signed_by else ''}).", *note]
            self._download_program()

        return self._start("download", U.download_argv(), downloaded,
                           "Downloading and verifying the update (agentprov update download)…")

    def _download_program(self) -> bool:
        auto = self.plan_doc.automatic if self.plan_doc is not None else None
        if auto is None or not auto.available or auto.how != "package":
            return self._ask(None)

        def downloaded(result: tuple[int, bytes, bytes]) -> None:
            got = U.parse_download(result[0], result[1])
            if got is None or got.kind != "package":
                self._ask(U.reason(result[0], result[2]))
                return
            self.package = got
            self.result = [*self.result, f"Downloaded and verified {', '.join(got.wheels)} ({got.verification}"
                                         f"{', signed by ' + got.signed_by if got.signed_by else ''})."]
            self._ask(None)

        return self._start("download", U.package_download_argv(), downloaded,
                           "Downloading and verifying the agentprov program's wheels (agentprov update download "
                           "--package)…")

    def _ask(self, refused: str | None) -> bool:
        """The one confirmation, then the installs (or, with nothing agentprov can update, the command)."""
        plan = U.plan(bundle=self.bundle if self.bundle_update else None, gui=self.gui, app=self.download,
                      program=self.plan_doc,
                      package=self.package, package_refused=refused,
                      core=self.check.core if self.check is not None else None)
        if self.followup is not None and plan.parts:
            from dataclasses import replace

            plan = replace(plan, followup=self.followup(plan))
        self.plan = plan
        for what, why, command in plan.cannot:
            self.result = [*self.result, f"{what} is not updated here: {why}.", *(
                [f"Run this command in a terminal: {command}"] if command else [])]
        if not plan.parts:
            if self.plan_doc is not None:
                self._show_command(self.plan_doc)
            return True
        self.busy, self.status_line = "confirm", "Waiting for your confirmation…"
        self.changed.emit()
        try:
            confirmed = self.confirm(QApplication.activeWindow() or getattr(self, "_parent", None), plan)
        finally:
            self.busy = ""
        if not confirmed:
            self.status_line = ("Not installed. A verified download stays staged; Download and Install… asks again.")
            self.changed.emit()
            return True
        if self.identity() != self._identity_at_start:
            self.status_line = ("Not installed: the agentprov program this app runs changed while the update was being "
                                "prepared (Settings › General), so the confirmation described another one. A verified "
                                "download stays staged; Download and Install… asks again.")
            self.changed.emit()
            return True
        self._failed, self._app_line = [], ""
        import agentprov_gui.ui.worker  # noqa: F401  (loaded before any swap, with what runs after it)

        if self.prepare is not None:
            self.prepare()
        self._install_parts(list(plan.parts))
        return True

    def _install_parts(self, parts: list[U.Part], installed: list[str] | None = None) -> None:
        installed = [] if installed is None else installed
        if not parts:
            if self._failed and not installed:
                self.status_line = "Nothing was updated: " + "; ".join(self._failed)
            if self.after_update is not None:  # the one call site of the step after the installs (D-1130)
                self.after_update(installed)
            return
        part, rest = parts[0], parts[1:]
        app = part.name == "The app"

        def done(result: tuple[int, bytes, bytes]) -> None:
            got = (self._installed if app else self._program_installed)(result)
            ok = got is not None and got.action in ("installed", "waiting-for-quit")  # this call's, never an earlier
            # a failed part does not stop the next one; each says how it went
            self._install_parts(rest, [*installed, part.name] if ok else installed)

        line = (f"Installing AgentPROV {part.to_version or ''} (agentprov update install)…" if app else
                "Updating the agentprov program (agentprov update install)…")
        self._start("apply", list(part.argv), done, line, continue_on_error=True)

    def _show_command(self, got: U.Install) -> None:
        self.install = got
        lines = list(got.lines) or ([got.text] if got.text else [])
        if got.command:
            lines.append("Run this command in a terminal; the app installs nothing itself here.")
        self.result = [*self.result, *lines]

    def _installed(self, result: tuple[int, bytes, bytes]) -> U.Install | None:
        got = U.parse_install(result[0], result[1])
        if got is None:
            line = "The app was not updated (the install was refused or failed; it is unchanged): " + U.reason(
                result[0], result[2])
            self.status_line = line
            self.result = [*self.result, line]  # kept when a later part reports itself (D-1130 review)
            self._failed.append("the app")
            return None
        self.install = got
        self.status_line = ""
        if got.action in ("installed", "waiting-for-quit"):
            self.status_line = self._app_line = (
                "Installed. Quit AgentPROV and open it again to start the new version." if got.action == "installed"
                else "Ready. Quit AgentPROV: the update is applied once it has closed.")
        lines = list(got.lines) or ([got.text] if got.text else [])
        if got.action == "command" and got.command:
            lines.append("Run this command in a terminal; the app installs nothing itself.")
        self.result = [*self.result, *lines]
        return got

    def _program_installed(self, result: tuple[int, bytes, bytes]) -> U.Install | None:
        got = U.parse_install(result[0], result[1])
        if got is None:
            line = ("The agentprov program was not updated (it is unchanged, or see its output): "
                    + U.reason(result[0], result[2]))
            self.result = [*self.result, line]
            self._failed.append("the agentprov program")
            # the program part's start replaced the status with its progress line: the app's quit line comes first
            self.status_line = f"{self._app_line} {line}" if self._app_line else line
            return None
        self.program_install = got
        unsynced = got.kind == "checkout" and got.action == "installed" and got.synced is False
        if unsynced:
            what = "The checkout was pulled, but its environment was NOT synced (see below): run the uv sync shown."
        elif got.action == "installed":
            what = "The agentprov program is updated; Check for Updates again to confirm."
        else:
            what = "The agentprov program was already current."
        if self._failed:  # an earlier part failed: say both (D-1130 review)
            self.status_line = f"{what} Not updated: {', '.join(self._failed)} (see below)."
        else:  # the app part's instruction to quit, when it installed, stays first
            self.status_line = f"{self._app_line} {what}" if self._app_line else what
        self.result = [*self.result, *got.lines]
        return got


class UpdatesSection(QWidget):
    """About's Updates section: the last check, the newest release and its notes, Check for Updates, Download and
    Install… (or Update agentprov…), the outcome, and the terminal commands of each action."""

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
        self.install_btn = QPushButton(buttons)
        self.install_btn.setAutoDefault(False)
        self.install_btn.clicked.connect(lambda: controller.download_and_install(self.window()))
        self._install_kind: tuple[bool, bool] | None = None
        self._set_install_button()
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

    def _set_install_button(self) -> None:
        """Download and Install… for a bundle update (with the program, when it is behind too), else Update agentprov…
        (not a bundle, or only the agentprov program this app runs is behind, D-1070), with the tooltip of what it
        runs (D-1130)."""
        c = self.controller
        kind = (c.bundle_update, c.bundle is not None)
        if kind == self._install_kind:
            return
        self._install_kind = kind
        name = INSTALL_NAME if c.bundle_update else PROGRAM_NAME
        self.install_btn.setText(name)
        self.install_btn.setAccessibleName(name)
        program = ("the agentprov program this app runs (Settings › General): a pip, uv tool or pipx install from "
                   "the release's verified wheels with its own installer (never PyPI), a clean checkout on main with "
                   "git pull --ff-only and uv sync --frozen")
        set_control_tooltip(self.install_btn, (
            "Runs agentprov update download --allow-network (the bundle is verified against the release's SHA256SUMS "
            "and, when the package lists a release key, its signature) and, when it is out of date too, prepares "
            f"{program}. Then it asks you once, naming each part, before agentprov update install replaces it; the "
            "app's old version is kept for rollback." if c.bundle_update else
            f"Only the agentprov program is out of date, not the app: replacing the app would not change it. Updates "
            f"{program}, after you confirm; any other install gets the command to run, and nothing is installed."
            if c.bundle is not None else
            f"This app runs from a checkout or a package install, not a bundle. Updates {program}, after you confirm; "
            "any other install gets the command to run, and nothing is installed."))

    def refresh(self) -> None:
        c = self.controller
        check = c.check
        self._set_install_button()
        if check is None or check.checked_at is None:
            self.last.set_plain("Never checked" if check is not None else "Not read yet")
        else:
            outcome = ("the agentprov this app runs is out of date" if check.update_available and check.cli_only else
                       "an update is available" if check.update_available else "up to date"
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
        can_install = available and (not c.bundle_update or (check is not None and check.asset is not None))
        self.install_btn.setEnabled(not c.busy and can_install and not c.installed)
        self.status.set_plain(c.status_line)
        self.status.setVisible(bool(c.status_line))
        self.result.set_plain("\n".join(c.result))
        self.result.setVisible(bool(c.result))
        commands = c.commands()
        for got in (c.install, c.plan_doc):
            if got is not None and got.command and got.action == "command":
                commands.append(("The upgrade command agentprov printed (run it yourself)", list(got.command)))
                break
        self.command.set_commands(commands)


class UpdateNotice(QDialog):
    """The start-up notice, once per new release: "AgentPROV X.Y.Z is available", the notes (plain text), and Update
    Now, Later or Skip This Version (:attr:`choice` is ``update``, ``later`` or ``skip``). When only the agentprov
    program the app runs is behind (D-1070) it says so instead, and its primary button is Update agentprov… (still
    ``update``: About then updates that program after the confirmation when agentprov can, D-1130, or shows its upgrade
    command; never a bundle download)."""

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
        cli_only = check.cli_only
        heading = "The agentprov this app runs is out of date" if cli_only else f"AgentPROV {version} is available"
        title = SafeLabel(heading, name="Update title", parent=page.column)
        title.setFont(theme.scaled_font("title"))
        title.setWordWrap(True)
        page.add(title)
        when = f" It was published {_when(check.published_at)}." if check.published_at else ""
        if cli_only:
            app = f"This app is AgentPROV {check.gui}, which is current" if check.gui else "This app is current"
            summary = (f"{app}, but the agentprov program it runs is {check.core or 'older'} and the newest release is "
                       f"{version}.{when} Updating the app would not change that program: Settings › General names "
                       "which one it is (a checkout or a package install). Update agentprov… updates it after you "
                       "confirm when agentprov can (a pip, uv tool or pipx install from the release's verified wheels, "
                       "never PyPI; a clean checkout on main by fast-forward) and otherwise shows the command for you "
                       "to run. The app itself is not downloaded or replaced.")
        else:
            have = ", ".join(x for x in (f"the app {check.gui}" if check.gui else "",
                                         f"agentprov {check.core}" if check.core else "") if x)
            summary = (f"You have {have or 'an older version'}.{when} Nothing is downloaded or installed until you "
                       "choose Update Now and confirm.")
        page.add(forms.caption(summary, name="Update summary", parent=page.column, role="secondary"))
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
        self.update_btn = self._button(
            PROGRAM_NAME, "update", footer,
            "Opens About, which asks agentprov how the program this app runs is installed (agentprov update install "
            "without --bundle) and, when it can update it, downloads and verifies what it needs and asks you before "
            "anything is replaced; otherwise it shows the command to run.") if cli_only else self._button(
            "Update Now", "update", footer, "Opens About and downloads and verifies the update (agentprov update "
            "download --allow-network, and the agentprov program's own update when it is out of date too); it asks you "
            "again, naming each part, before anything is replaced.")
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
