"""Install Command Line Tool… and Uninstall Command Line Tool (D-1130): the app's own ``agentprov`` in a Terminal.

The desktop bundle is also the ``agentprov`` program (``AgentPROV --cli ARGS``, :func:`~agentprov_gui.jobs.manager.
bundled_program`). These two items put a small launcher named ``agentprov`` on the user's ``PATH`` that runs it, as an
editor's "install the command in PATH" does, and take it away again. Every write is the bundle's own CLI
(``agentprov launcher install|remove``, D-391); the app only asks first and shows the reply:

* **Install** asks ``launcher status`` where a launcher would go (``~/.local/bin``; ``/usr/local/bin`` is offered only
  when this account can write it, and nothing ever asks for administrator rights), then a confirmation that names the
  launcher's path and what it runs (``"EXE" --cli ARGS``), and says when the folder already holds another
  ``agentprov`` (pip, uv tool, pipx, a checkout's ``.venv``), which is never replaced. The reply says how to put the
  folder on ``PATH`` when it is not there.
* **Uninstall** lists the launchers this app made (by their marker line) and removes only those, after a
  confirmation; any other ``agentprov`` is left and named.

The items are shown in the macOS application menu (and in Help on Linux and Windows) only when this app is the bundle:
a checkout's or a package's app has no bundled CLI, and its own ``agentprov`` is already a Terminal command. Which CLI
the app runs (Settings › General, :class:`~agentprov_gui.jobs.manager.CliLocator`) is unchanged: the launcher is never
taken for a separately installed ``agentprov`` (:func:`~agentprov_gui.jobs.manager.is_cli_launcher`).
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Final

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QVBoxLayout, QWidget

from agentprov_gui import text as T
from agentprov_gui.jobs.manager import CliLocator, bundled_program
from agentprov_gui.ui.forms import FullTextCombo
from agentprov_gui.ui.safe import (
    CRITICAL,
    INFORMATION,
    WARNING,
    SafeLabel,
    choose,
    safe_message_box,
    set_combo_item_tooltip,
    set_control_tooltip,
    set_help_tooltip,
)

__all__ = ["INSTALL_NAME", "INSTALL_TIP", "UNINSTALL_NAME", "UNINSTALL_TIP", "ConfirmInstall", "install",
           "uninstall"]

#: the menu items (reverse parity, :mod:`agentprov_gui.parity`)
INSTALL_NAME: Final = "Install Command Line Tool…"
UNINSTALL_NAME: Final = "Uninstall Command Line Tool"
INSTALL_TIP: Final = ("Put an agentprov command on your PATH (in ~/.local/bin) that runs this app's own agentprov, so it "
                      "also works in a Terminal (agentprov launcher install). Asks first; never needs administrator "
                      "rights.")
UNINSTALL_TIP: Final = ("Remove the agentprov command Install Command Line Tool made (agentprov launcher remove). Any "
                        "other agentprov (pip, uv tool, pipx, a checkout) is left alone.")
#: the confirmation's buttons (reverse parity)
CONFIRM_INSTALL: Final = "Install the Terminal command"
CONFIRM_REMOVE: Final = "Remove the Terminal command"
NOT_BUNDLE: Final = ("This copy of AgentPROV is not the desktop app bundle, so it has no agentprov of its own to put on "
                     "your PATH. An agentprov from a checkout (.venv/bin) or from pip, uv tool or pipx is already a "
                     "Terminal command.")

#: ``run(argv)``: one call of the bundle's own agentprov (exit code, stdout, stderr tail)
Runner = Callable[[Sequence[str]], tuple[int, bytes, bytes]]


def _bundled_runner() -> Runner | None:
    own = bundled_program()
    if not own:
        return None
    cli = CliLocator(None, own, (), True)

    def run(argv: Sequence[str]) -> tuple[int, bytes, bytes]:
        from agentprov_gui.live.cli import call

        QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            return call(cli, list(argv), timeout=60)
        finally:
            QGuiApplication.restoreOverrideCursor()

    return run


def available() -> bool:
    """Whether this app is the bundle, with its own agentprov to link (the items are shown only then)."""
    return bool(bundled_program())


def _json(run: Runner, argv: Sequence[str]) -> tuple[dict[str, Any] | None, str]:
    """The command's JSON reply, or ``None`` and the reason (its stderr, as the CLI said it)."""
    from agentprov_gui.live.cli import last_line
    from agentprov_gui.updates import _document

    code, out, err = run([*argv, "--format", "json"])
    if code == 0:  # bounded, strict (the update documents' reader): the reply is the CLI's, read as data (S3)
        doc = _document(code, out, ("agentprov-launcher/0.1",))
        return (doc, "") if doc is not None else (None, "the reply was not readable")
    lines = [x for x in err.decode("utf-8", "replace").splitlines()
             if x.strip() and not x.startswith(("INFO ", "DEBUG "))]
    return None, "\n".join(lines[-8:]) or last_line(err) or f"agentprov exited with code {code}"


class ConfirmInstall(QDialog):
    """The confirmation: the launcher's path, what it runs, and (when ``/usr/local/bin`` is writable) the folder."""

    def __init__(self, status: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Install Command Line Tool")
        self.setAccessibleName("Install Command Line Tool")
        self.status = status
        self.entries = [e for e in status.get("entries", []) if isinstance(e, dict)]
        self.app = T.line(status.get("app") or "", 400)
        lay = QVBoxLayout(self)
        lay.addWidget(SafeLabel("Install the agentprov command for the Terminal?", name="Question"))
        self.folder = FullTextCombo()
        self.folder.setAccessibleName("Launcher folder")
        default = os.path.normcase(os.path.normpath(str(status.get("default_dir") or "")))
        choices = [e for e in self.entries if default and os.path.normcase(os.path.dirname(str(e.get("path", ""))))
                   == default] or self.entries[:1]  # the default folder itself, never ~/.local/bin2
        if status.get("system_dir_writable"):
            choices += [e for e in self.entries if e not in choices]
        for i, entry in enumerate(choices):
            self.folder.addItem(T.line(entry.get("path", ""), 400), entry)
            set_combo_item_tooltip(self.folder, i, "In your own folder; no administrator rights." if i == 0 else
                                   "A shared folder this account can write; every user of this Mac sees the command.")
        set_control_tooltip(self.folder, "Where the agentprov launcher goes. The default needs no administrator "
                            "rights; a shared folder is offered only when this account can already write it.")
        self.folder.setVisible(len(choices) > 1)
        lay.addWidget(self.folder)
        self.details = SafeLabel("", name="What the launcher does")
        self.details.setWordWrap(True)
        lay.addWidget(self.details)
        self.buttons = QDialogButtonBox()
        self.ok = self.buttons.addButton(CONFIRM_INSTALL, QDialogButtonBox.ButtonRole.AcceptRole)
        self.ok.setAccessibleName(CONFIRM_INSTALL)
        set_help_tooltip(self.ok, "Write the launcher (agentprov launcher install --dir FOLDER). An earlier launcher of "
                         "this app there is replaced; nothing else is.")
        self.buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        lay.addWidget(self.buttons)
        self.folder.currentIndexChanged.connect(self._show)
        self._show()

    def chosen(self) -> dict[str, Any]:
        entry = self.folder.currentData()
        return entry if isinstance(entry, dict) else {}

    def chosen_dir(self) -> str:
        """The folder of the chosen launcher path (the CLI's own path, of this platform)."""
        return os.path.dirname(str(self.chosen().get("path", "")))

    def _show(self) -> None:
        entry = self.chosen()
        path = str(entry.get("path", ""))
        lines = [f"Launcher: {T.line(path, 400)}", f"It runs: \"{self.app}\" --cli ARGS",
                 "That is this app's own agentprov, so an app update updates the Terminal command too. If the app is "
                 "moved or deleted, the command says so; install it again from the new place."]
        blocked = bool(entry.get("exists")) and not entry.get("launcher")
        if blocked:
            lines.append(f"There is already an agentprov there: {T.line(entry.get('is') or 'another program', 300)}. "
                         "It is not "
                         "replaced; remove it with the tool that installed it, or choose another folder.")
        elif entry.get("launcher"):
            lines.append("An earlier launcher of this app is there; it is replaced.")
        if not entry.get("on_path"):  # the app's PATH (from the Finder or a desktop menu) may be shorter than a shell's
            lines.append("If this folder is not on your Terminal's PATH, the next step says how to add it.")
        self.details.setText("\n\n".join(lines))
        self.ok.setEnabled(not blocked and bool(path))


def _box(parent: QWidget | None, title: str, text: str, informative: str = "", icon: Any = INFORMATION) -> None:
    safe_message_box(parent, title, text, informative=informative, icon=icon).exec()


def install(parent: QWidget | None, *, run: Runner | None = None,
            confirm: Callable[[ConfirmInstall], bool] | None = None) -> dict[str, Any] | None:
    """The whole Install Command Line Tool… flow; the CLI's reply when it installed. ``run`` and ``confirm`` are
    seams for the tests (default: the bundle's own agentprov, and the dialog's ``exec``)."""
    title = "Install Command Line Tool"
    run = run if run is not None else _bundled_runner()
    if run is None:
        _box(parent, title, "The Terminal command comes with the desktop app.", NOT_BUNDLE)
        return None
    status, why = _json(run, ["launcher", "status"])
    if status is None or not status.get("app"):
        _box(parent, title, "Could not check where the command would go.", why or "agentprov did not name the app.",
             CRITICAL)
        return None
    dlg = ConfirmInstall(status, parent)
    ok = (confirm or (lambda d: d.exec() == QDialog.DialogCode.Accepted))(dlg)
    folder = dlg.chosen_dir()
    dlg.deleteLater()
    if not ok:
        return None
    doc, why = _json(run, ["launcher", "install", "--dir", folder])
    if doc is None:
        _box(parent, title, "The Terminal command was not installed.", why, WARNING)
        return None
    verb = {"installed": "installed", "updated": "updated", "unchanged": "already installed"}.get(
        str(doc.get("changed")), "installed")
    lines = [f"{T.line(doc.get('launcher'), 400)} runs \"{T.line(doc.get('app'), 400)}\" --cli ARGS."]
    if doc.get("shadowed_by"):
        lines.append(f"Another agentprov comes first on PATH: {T.line(doc['shadowed_by'], 400)}. A Terminal runs that "
                     "one until you remove it or put this folder first.")
    hint = [T.line(x, 600) for x in doc.get("path_hint") or []]
    if hint and sys.platform != "win32":  # the app's PATH is not the shell's: say it conditionally
        folder = T.line(str(Path(str(doc.get("launcher"))).parent), 400)
        hint[0] = f"If a new Terminal window says agentprov is not found, add {folder} to your PATH (zsh and bash):"
    lines.append("\n".join(hint) if hint else "Open a new Terminal window and type: agentprov --help")
    _box(parent, title, f"The agentprov command is {verb}.", "\n\n".join(lines))
    return doc


def uninstall(parent: QWidget | None, *, run: Runner | None = None,
              confirm: Callable[[str], bool] | None = None) -> dict[str, Any] | None:
    """The Uninstall Command Line Tool flow; the CLI's reply when it removed something."""
    title = "Uninstall Command Line Tool"
    run = run if run is not None else _bundled_runner()
    if run is None:
        _box(parent, title, "The Terminal command comes with the desktop app.", NOT_BUNDLE)
        return None
    status, why = _json(run, ["launcher", "status"])
    if status is None:
        _box(parent, title, "Could not look for the command.", why, CRITICAL)
        return None
    entries = [e for e in status.get("entries", []) if isinstance(e, dict)]
    ours = [e for e in entries if e.get("launcher")]
    others = [f"{T.line(e.get('path'), 400)}: {T.line(e.get('is'), 300)}" for e in entries
              if e.get("exists") and not e.get("launcher")]
    left = ("\n\nLeft as it is (not made by this app):\n" + "\n".join(others)) if others else ""
    if not ours:
        _box(parent, title, "No agentprov command of this app is installed.", left.strip())
        return None
    text = "\n".join(f"{T.line(e.get('path'), 400)} (runs {T.line(e.get('app'), 400)})" for e in ours)
    question = ("Remove the agentprov command?\n\n" + text + "\n\nOnly launchers this app made are removed." + left)
    if not (confirm or _ask_remove(parent, title))(question):
        return None
    doc, why = _json(run, ["launcher", "remove"])
    if doc is None:
        _box(parent, title, "The Terminal command was not removed.", why, WARNING)
        return None
    removed = [T.line(x, 400) for x in doc.get("removed") or []]
    _box(parent, title, "The agentprov command is removed." if removed else "Nothing was removed.",
         "\n".join(removed) + left)
    return doc


def _ask_remove(parent: QWidget | None, title: str) -> Callable[[str], bool]:
    def ask(question: str) -> bool:
        return choose(parent, title, question, "", "Cancel", CONFIRM_REMOVE, tips=(
            "Keep the Terminal command.",
            "Delete the launchers listed (agentprov launcher remove); any other agentprov is left alone."))

    return ask
