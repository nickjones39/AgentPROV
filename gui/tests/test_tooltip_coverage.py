"""Every element on every screen has a tooltip, in plain text (S1).

The walk opens each page of the main window, each dialog (New Job for every form, Run Live for both transports,
Settings with every pane, About, Zenodo drafts, the live preview, the job confirmation, the key and identity dialogs)
and checks every interactive part: buttons (segments, switches, chips, link and tool buttons, the disclosure headers),
inputs (line edits, spin boxes, combo boxes, editable text), Choose… path fields, status badges, the rows of the
navigation lists, the sections of the column headers and the tabs of tab bars. Each gives a non-empty tooltip of the
text Qt would show (``toolTip()``, the header model's and the item's ``ToolTipRole``, ``tabToolTip``), and every
tooltip is the escaped plain text that :mod:`agentprov_gui.ui.safe` makes. :data:`EXEMPT` names the few elements whose
visible words say everything. The Viewer pages (the three-pane corpus Viewer and its execution tabs) are walked by
:func:`test_viewer_pages_have_tooltips`."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

#: a dialog's standard button (in its button box) by its text -> why it has no tooltip: its words say all there is to
#: say. Any other button with these words still needs one.
EXEMPT: dict[str, str] = {
    "OK": "the dialog's standard confirm button",
    "Cancel": "the dialog's standard dismiss button",
    "Close": "the dialog's standard close button",
}

_TAGS = re.compile(r"</?p>|<br\s*/?>")


def plain(tip: str) -> bool:
    """A tooltip as :func:`safe.safe_tooltip` and :func:`safe.help_tooltip` make it: Qt's paragraph around escaped
    text, with no other markup."""
    return tip.startswith("<p") and "<" not in _TAGS.sub("", tip) and not re.search(r"&(?!(amp|lt|gt|quot);)", tip)


def _exempt(widget: Any) -> bool:
    from PySide6.QtWidgets import QAbstractButton, QDialogButtonBox

    return isinstance(widget, QAbstractButton) and isinstance(widget.parent(), QDialogButtonBox) \
        and widget.text().replace("&", "") in EXEMPT


def _label(widget: Any) -> str:
    text = getattr(widget, "text", None)
    shown = text() if callable(text) and isinstance(text(), str) else ""
    return f"{type(widget).__name__} {widget.accessibleName() or shown!r}"


def _parts(top: Any, skip: tuple[Any, ...] = ()) -> Iterator[tuple[str, str | None]]:
    """(description, tooltip) for every interactive part under ``top`` (``top`` too), except under ``skip``; the
    tooltip is ``None`` for an :data:`EXEMPT` part without one."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QAbstractButton,
        QAbstractItemView,
        QAbstractSpinBox,
        QComboBox,
        QLineEdit,
        QListWidget,
        QPlainTextEdit,
        QScrollBar,
        QTabBar,
        QTableView,
        QTreeView,
        QWidget,
    )

    from agentprov_gui.ui.forms import PathField, StatusBadge

    inputs = (QAbstractButton, QLineEdit, QAbstractSpinBox, QComboBox, QPlainTextEdit, StatusBadge)
    internal = (QAbstractItemView, QComboBox, QAbstractSpinBox, QLineEdit, QTabBar, QScrollBar)  # their own parts

    def skipped(w: Any) -> bool:
        return any(s is w or s.isAncestorOf(w) for s in skip)

    widgets = [top, *top.findChildren(QWidget)]
    for w in widgets:
        if skipped(w) or w.objectName().startswith("qt_"):
            continue
        if isinstance(w, inputs) and not isinstance(w.parent(), internal):
            if isinstance(w, QPlainTextEdit) and w.isReadOnly():
                continue  # a read-only pane shows text; it is not an input
            tip = w.toolTip()
            if not tip and isinstance(w, QLineEdit) and isinstance(w.parent(), PathField):
                tip = w.parent().toolTip()  # the path field's own edit: the field's tip is shown for it
            yield _label(w), (None if not tip and _exempt(w) else tip)
        if isinstance(w, QListWidget) and w.objectName() != "data":
            for row in range(w.count()):
                item = w.item(row)
                if item.flags() & Qt.ItemFlag.ItemIsSelectable:
                    yield f"{w.accessibleName()} › {item.text()}", item.toolTip()
        if isinstance(w, QTableView | QTreeView) and w.model() is not None:
            header = w.horizontalHeader() if isinstance(w, QTableView) else w.header()
            if header.isHidden():
                continue
            model = w.model()
            for column in range(model.columnCount()):
                tip = model.headerData(column, Qt.Orientation.Horizontal, Qt.ItemDataRole.ToolTipRole)
                yield f"{w.accessibleName()} › column {model.headerData(column, Qt.Orientation.Horizontal)}", \
                    str(tip or "")
        if isinstance(w, QTabBar) and not w.isHidden():
            for i in range(w.count()):
                yield f"{w.parent().accessibleName()} › tab {w.tabText(i)}", w.tabToolTip(i)


def gaps(top: Any, *, skip: tuple[Any, ...] = (), minimum: int = 1) -> list[str]:
    """What is wrong under ``top``: parts without a tooltip, and tooltips that are not plain text. ``minimum``: the walk
    must see at least this many parts (a vacuous pass would see none)."""
    parts = list(_parts(top, skip))
    assert len(parts) >= minimum, f"the walk saw {len(parts)} parts of {top.accessibleName()}"
    missing = sorted({f"no tooltip: {what}" for what, tip in parts if tip == ""})
    rich = sorted({f"not plain text: {what}: {tip[:80]!r}" for what, tip in parts if tip and not plain(tip)})
    return missing + rich


def _report(found: list[str]) -> str:
    return "\n  " + "\n  ".join(found)


# ---------------------------------------------------------------------------------------------- the main window
@pytest.fixture
def window(qapp: Any, tmp_path: Path, fake_checkout: Path, mini_corpus: Path) -> Any:
    from PySide6.QtCore import QSettings

    from agentprov_gui.settings import Settings
    from agentprov_gui.ui.mainwindow import MainWindow

    settings = Settings(QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    settings.checkout = fake_checkout
    settings.corpus_roots = [mini_corpus.parent]
    w = MainWindow(settings, cache_dir=tmp_path / "layout", home=tmp_path / "home")
    w.show()
    yield w
    w.close()
    w.deleteLater()
    qapp.processEvents()


def _viewer_parts(window: Any) -> tuple[Any, ...]:
    return (window.viewer,)


def test_every_page_has_tooltips(qapp: Any, window: Any) -> None:
    """The frame (sidebar, toolbar, status bar, window tabs) and the pages Runs, Logs, System, Licences, Package, Docs
    and the Assistant tab; the Viewer is :func:`test_viewer_pages_have_tooltips`."""
    window.open_assistant()  # the second tab: its tab bar shows
    for title in ("Runs", "Logs", "System", "Licences", "Package", "Docs"):
        window.go(title)
        qapp.processEvents()
    found = gaps(window, skip=_viewer_parts(window), minimum=80)
    assert not found, _report(found)


def test_viewer_pages_have_tooltips(qapp: Any, window: Any, mini_corpus: Path) -> None:
    from test_viewer import _open

    v = _open(qapp, window, mini_corpus)
    v.open_current_in_tab()
    found = gaps(window.viewer, minimum=40)
    assert not found, _report(found)


# ---------------------------------------------------------------------------------------------- the dialogs
def _forms() -> list[str]:
    from agentprov_gui.jobs.commands import FORMS

    return sorted(FORMS)


@pytest.mark.parametrize("name", _forms())
def test_every_new_job_form_has_tooltips(qapp: Any, name: str) -> None:
    from agentprov_gui.jobs.commands import FORMS
    from agentprov_gui.ui.jobdialog import JobDialog

    dlg = JobDialog(FORMS[name], program=("agentprov",), conformance_option="--skip-prov-conformance")
    found = gaps(dlg, minimum=3)
    dlg.deleteLater()
    assert not found, _report(found)


@pytest.mark.parametrize("scripted", [True, False], ids=["scripted", "real-model"])
def test_run_live_has_tooltips(qapp: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scripted: bool) -> None:
    from test_runlive_form import QUOTE, _dialog, _settle

    dlg = _dialog(tmp_path, monkeypatch, scripted=scripted, quote=QUOTE)
    _settle(qapp, dlg)
    found = gaps(dlg, minimum=40)
    dlg.close()
    assert not found, _report(found)


def test_settings_has_tooltips(qapp: Any, tmp_path: Path, fake_checkout: Path) -> None:
    """Every pane of the Settings sidebar (each is built when the dialog opens), and the sidebar's rows."""
    from PySide6.QtCore import QSettings

    from agentprov_gui.settings import Settings
    from agentprov_gui.ui.dialogs import SettingsDialog
    from test_settings_tooltips import _settle

    settings = Settings(QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    settings.checkout = fake_checkout
    dlg = SettingsDialog(settings)
    _settle(qapp)
    for row in range(dlg.sidebar.count()):
        dlg.sidebar.setCurrentRow(row)
        qapp.processEvents()
    _settle(qapp)
    found = gaps(dlg, minimum=100)
    dlg.deleteLater()
    assert not found, _report(found)


def test_about_has_tooltips(qapp: Any) -> None:
    from agentprov_gui.about import default_checkout
    from agentprov_gui.ui.dialogs import AboutDialog

    dlg = AboutDialog(default_checkout())
    found = gaps(dlg)
    dlg.deleteLater()
    assert not found, _report(found)


def test_zenodo_drafts_has_tooltips(qapp: Any, tmp_path: Path) -> None:
    from agentprov_gui.ui.zenodo import ZenodoDraftsDialog
    from test_zenodo import _Cli

    dlg = ZenodoDraftsDialog(_Cli(tmp_path / "x.py"), tmp_path, deposits=f"{tmp_path} sha256:{'0' * 64}")
    found = gaps(dlg, minimum=5)
    dlg.deleteLater()
    assert not found, _report(found)


def test_live_preview_has_tooltips(qapp: Any, tmp_path: Path) -> None:
    from agentprov_gui.ui.preview import PreviewWindow

    window = PreviewWindow(tmp_path, lambda: [], title="t")
    found = gaps(window)
    window.timer.stop() if hasattr(window, "timer") else None
    window.deleteLater()
    assert not found, _report(found)


def test_key_and_identity_dialogs_have_tooltips(qapp: Any) -> None:
    from agentprov_gui.ui.livepanes import StoreKeyDialog
    from agentprov_gui.ui.runlive import IdentityDialog

    found: list[str] = []
    for dlg in (StoreKeyDialog("OPENROUTER_API_KEY"), IdentityDialog({"model_id": "m"})):
        found += gaps(dlg)
        dlg.deleteLater()
    assert not found, _report(found)


@pytest.mark.parametrize("name", ["import", "purge"])
def test_the_job_confirmation_has_tooltips(qapp: Any, monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    """The confirmation New Job shows before a job starts: an R2 job's consent box, a purge's typed digits."""
    from PySide6.QtWidgets import QDialog

    from agentprov_gui.jobs.commands import FORMS, build_spec
    from agentprov_gui.ui import jobdialog

    values = {"import": {"source": "agentdojo", "corpus": "/c", "fetch": True},
              "purge": {"corpus": "/c", "object": "sha256:" + "a" * 64, "reason": "secret"}}[name]
    spec = build_spec(FORMS[name], values)
    seen: list[list[str]] = []

    def look(dlg: QDialog) -> int:
        seen.append(gaps(dlg))
        return 0

    monkeypatch.setattr(QDialog, "exec", look)
    assert jobdialog.confirm(None, spec, "agentprov " + " ".join(spec.argv)) is None
    ((found,),) = [seen]
    assert not found, _report(found)


def test_the_question_boxes_have_tooltips(qapp: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """A question with two named buttons (skipping the conformance check) says what each does; OK and Cancel are
    :data:`EXEMPT`."""
    from PySide6.QtWidgets import QMessageBox

    from agentprov_gui.ui import jobdialog, safe

    seen: list[list[str]] = []

    def look(box: QMessageBox) -> int:
        seen.append(gaps(box))
        return int(QMessageBox.StandardButton.Cancel)

    monkeypatch.setattr(QMessageBox, "exec", look)
    jobdialog.conformance_warning(None)
    safe.ask(None, "Stop job", "Stop this job?")
    assert seen == [[], []], _report([*seen[0], *seen[1]])
