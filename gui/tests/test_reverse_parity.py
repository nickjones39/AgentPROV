"""D-700: reverse CLI parity. Every GUI setting and action has a CLI equivalent (:mod:`agentprov_gui.parity`).

The built main window, Settings dialog and Run Live dialog are walked. Each Settings input must be a pane's ``KEYS``
entry naming a key of the core's settings schema, or excluded with a reason; each Run Live input a ``run`` form field
or a ``run`` option (a read-only widget only shows); each button and menu action a ``FORMS`` title, a command of the CLI, or presentational with a
reason. Every command and option the registry names, including those quoted in its reasons, must be the CLI's
(:func:`test_cli_parity.cli_tree`, the parser walked in a subprocess). A new widget fails until it is mapped.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from agentprov import settings as core_settings

from agentprov_gui import parity
from agentprov_gui.jobs.commands import FORMS, MANAGED_OPTIONS
from agentprov_gui.jobs.manager import CliLocator, JobManager
from test_cli_parity import cli_tree


@pytest.fixture(scope="module")
def tree() -> dict[str, Any]:
    return cli_tree()


def _settle(qapp: Any) -> None:
    from PySide6.QtCore import QThreadPool

    QThreadPool.globalInstance().waitForDone(60_000)
    qapp.processEvents()


def _inputs(root: Any) -> Iterator[Any]:
    """The widgets a user sets something with (read-only ones only show a value)."""
    from PySide6.QtWidgets import (
        QCheckBox,
        QComboBox,
        QDoubleSpinBox,
        QLineEdit,
        QListWidget,
        QPlainTextEdit,
        QRadioButton,
        QSpinBox,
        QWidget,
    )

    kinds = (QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QCheckBox, QPlainTextEdit, QRadioButton, QListWidget)
    for w in root.findChildren(QWidget):
        if not isinstance(w, kinds) or isinstance(w.parent(), (QSpinBox, QDoubleSpinBox, QComboBox)):
            continue  # (a spin box's or combo box's own line edit)
        if isinstance(w, (QLineEdit, QPlainTextEdit)) and w.isReadOnly():
            continue
        yield w


def _attr(owner: Any, widget: Any) -> str | None:
    """``name`` when ``owner.name is widget``, ``name.key`` when ``owner.name[key] is widget``."""
    for name, value in vars(owner).items():
        if value is widget:
            return str(name)
        if isinstance(value, dict):
            for key, item in value.items():
                if item is widget:
                    return f"{name}.{key}"
    return None


def _label(w: Any) -> str:
    text = w.accessibleName() if hasattr(w, "accessibleName") and w.accessibleName() else w.text()
    return str(text).replace("&", "").strip()


def _command(tree: dict[str, Any], words: tuple[str, ...]) -> bool:
    return " ".join(words) in tree


def _in_schema(key: str) -> bool:
    samples = (key.replace("*", "x"), key.replace("*", "0"))  # a name family, or an indexed one (zenodo.creators.N)
    return any(k.matches(sample) for sample in samples for k in core_settings.SCHEMA)


def test_every_settings_input_is_a_cli_setting_or_excluded(qapp: Any, tmp_path: Path) -> None:
    from PySide6.QtCore import QSettings

    from agentprov_gui.settings import Settings
    from agentprov_gui.ui.dialogs import SettingsDialog

    dlg = SettingsDialog(Settings(QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)))
    _settle(qapp)
    panes = list(dlg.panes)
    bad: list[str] = []
    seen: dict[int, set[str]] = {id(p): set() for p in panes}
    checked = list(_inputs(dlg))
    assert len(checked) >= 45  # the walk sees the panes (a vacuous pass would see none)
    for w in checked:
        owner = w.parent()
        while owner is not None and owner is not dlg and not any(owner is p for p in panes):
            owner = owner.parent()
        if owner is dlg:
            attr = _attr(dlg, w)
            if attr not in parity.SETTINGS_EXCLUDED:
                bad.append(f"Settings dialog: {attr or _label(w)!r} is not excluded")
            continue
        attr = _attr(owner, w)
        keys = getattr(type(owner), "KEYS", {})
        if attr is None or attr not in keys:
            bad.append(f"{type(owner).__name__}: input {attr or _label(w)!r} has no settings key")
            continue
        seen[id(owner)].add(attr)
        if not _in_schema(keys[attr]):
            bad.append(f"{type(owner).__name__}.{attr}: {keys[attr]!r} is not an agentprov settings key")
    for pane in panes:
        stale = set(getattr(type(pane), "KEYS", {})) - seen[id(pane)]
        if stale:
            bad.append(f"{type(pane).__name__}: KEYS names no input: {sorted(stale)}")
    for name, reason in parity.SETTINGS_EXCLUDED.items():
        assert hasattr(dlg, name) and len(reason) > 10, name
    dlg.deleteLater()
    assert not bad, "\n".join(bad)


def test_every_run_live_input_is_a_run_option(qapp: Any, tmp_path: Path, tree: dict[str, Any]) -> None:
    from agentprov_gui.ui.runlive import RunLiveDialog

    manager = JobManager(tmp_path / "home", CliLocator(None, ()))
    dlg = RunLiveDialog(manager, home=tmp_path / "home", checkout=None, run=lambda *a, **k: (127, b"", b""))
    _settle(qapp)
    fields = {f.key for f in FORMS["run"].fields}
    options = set(tree["run"]["options"]) | set(MANAGED_OPTIONS["run"])
    bad: list[str] = []
    checked = list(_inputs(dlg))
    assert len(checked) >= 50
    for w in checked:
        attr = _attr(dlg, w)
        key = attr.removeprefix("more_inputs.") if attr else None
        if key in fields:
            continue
        if key in parity.RUN_LIVE_INPUTS:
            option, _why = parity.RUN_LIVE_INPUTS[key]
            if option not in options:
                bad.append(f"Run Live {key}: {option} is not a run option")
            continue
        bad.append(f"Run Live input {attr or _label(w)!r} is neither a run field nor a run option")
    dlg.deleteLater()
    assert not bad, "\n".join(bad)


def _actions(root: Any) -> Iterator[tuple[str, Any]]:
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QAbstractButton, QLineEdit

    for a in root.findChildren(QAction):
        if a.isSeparator() or a.menu() is not None or isinstance(a.parent(), QLineEdit) or not _label(a):
            continue
        yield _label(a), a
    for b in root.findChildren(QAbstractButton):
        if b.objectName().startswith("qt_") or isinstance(b.parent(), QLineEdit):
            continue
        label = _label(b)
        if label in ("Scroll Left", "Scroll Right") or not label:
            continue
        yield label, b


def test_every_action_is_a_cli_command_or_presentational(qapp: Any, tmp_path: Path, tree: dict[str, Any]) -> None:
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QCheckBox

    from agentprov_gui.settings import Settings
    from agentprov_gui.ui import mainwindow
    from agentprov_gui.ui.dialogs import SettingsDialog
    from agentprov_gui.ui.runlive import RunLiveDialog

    settings = Settings(QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    win = mainwindow.MainWindow(settings, cache_dir=tmp_path / "c", home=tmp_path / "home")
    dlg = SettingsDialog(settings)
    live = RunLiveDialog(JobManager(tmp_path / "home", CliLocator(None, ())), home=tmp_path / "home", checkout=None,
                         run=lambda *a, **k: (127, b"", b""))
    _settle(qapp)
    titles = {f.title: f for f in FORMS.values()}
    bad: list[str] = []
    labels: set[str] = set()
    for root in (win, dlg, live):
        for label, widget in _actions(root):
            labels.add(label)
            if root is not win and isinstance(widget, QCheckBox):
                continue  # a dialog's ticks are inputs (the tests above)
            if label in titles or label in parity.PRESENTATIONAL or label in parity.OUTSIDE_CLI:
                continue
            words = parity.ACTIONS.get(label)
            if words is None:
                bad.append(f"{type(root).__name__}: {label!r} is neither a CLI command nor presentational")
    assert len(labels) >= 80 and "Seal a working corpus" in labels and "Stop the job" in labels
    for label, words in parity.ACTIONS.items():
        if not _command(tree, words):
            bad.append(f"ACTIONS {label!r}: agentprov {' '.join(words)} is not a command")
    win.close()
    dlg.deleteLater()
    live.deleteLater()
    assert not bad, "\n".join(bad)


_QUOTED = re.compile(r"agentprov ((?:[a-z][a-z-]*(?: |$))+)((?:--?[a-z][a-z-]*(?: [a-z0-9][a-z0-9-]*)?(?: |$))*)")


def test_the_registry_names_real_commands_and_options(tree: dict[str, Any]) -> None:
    """Every ``agentprov CMD --option`` a reason quotes is the CLI's, and every reason says something."""
    reasons = [*parity.SETTINGS_EXCLUDED.values(), *parity.PRESENTATIONAL.values(),
               *(why for _o, why in parity.RUN_LIVE_INPUTS.values())]
    bad: list[str] = []
    for reason in reasons:
        assert len(reason) > 10, reason
        for m in _QUOTED.finditer(re.sub(r"[(),;:]", " ", reason)):
            tokens = m.group(0).split()[1:]
            words: list[str] = []
            for t in tokens:
                if t.startswith("-") or not _command(tree, (*words, t)):
                    break
                words.append(t)
            if not words:
                bad.append(f"{reason!r}: names no agentprov command")
                continue
            known = set(tree[" ".join(words)]["options"]) | set(tree[""]["options"])
            bad.extend(f"{reason!r}: agentprov {' '.join(words)} has no {t}" for t in tokens
                       if t.startswith("--") and t not in known)
    assert not bad, "\n".join(bad)


def test_the_outside_cli_actions_name_real_uploader_options() -> None:
    """D-880: every option an :data:`parity.OUTSIDE_CLI` action names is one the uploader's parser defines (read from
    its source, ``zenodo/src/agentprov_zenodo/draft.py``: the GUI never imports the uploader)."""
    import ast

    source = Path(__file__).resolve().parents[2] / "zenodo" / "src" / "agentprov_zenodo" / "draft.py"
    options = {a.value for n in ast.walk(ast.parse(source.read_text("utf-8")))
               if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "add_argument"
               for a in n.args if isinstance(a, ast.Constant) and str(a.value).startswith("--")}
    assert {"--create-draft", "--cross-link", "--keychain"} <= options
    for label, (used, reason) in parity.OUTSIDE_CLI.items():
        assert len(reason) > 10, label
        assert set(used) <= options, f"{label!r}: {sorted(set(used) - options)} are not uploader options"
