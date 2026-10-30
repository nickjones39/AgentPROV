"""GR-40 (design §11 S3): Qt treats ``[*]`` in a window title as the window-modified placeholder and hides it, so a
data-derived title (a corpus name, a job label) must show it literally. Qt's escape for a literal ``[*]`` is doubling
(``[*][*]``); ``[[*]]`` would show as ``[]``. The placeholder is assembled at run time (K.4.2)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from agentprov_gui import text as T

PH = "[" + "*" + "]"


@pytest.mark.parametrize("raw", [PH, PH + PH, "[" + PH + "]", PH + "]", "a" + PH + "b", "plain", ""])
def test_window_title_doubles_the_placeholder(raw: str) -> None:
    assert T.window_title(raw) == raw.replace(PH, PH + PH)


@pytest.fixture
def window(qapp: Any, tmp_path: Path) -> Any:
    from PySide6.QtCore import QSettings, QThreadPool

    from agentprov_gui.settings import Settings
    from agentprov_gui.ui.mainwindow import MainWindow

    settings = Settings(QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat))
    settings.corpus_roots = [tmp_path]
    w = MainWindow(settings, cache_dir=tmp_path / "layout")
    w.show()
    yield w
    QThreadPool.globalInstance().waitForDone(30_000)  # the window's corpus scan, before its signals go away
    w.close()
    w.deleteLater()
    qapp.processEvents()


def test_corpus_title_shows_the_placeholder_literally(qapp: Any, window: Any) -> None:
    assert window.chrome is None  # offscreen: the corpus name goes to the window title
    name = "prod" + PH + "-v2"
    window._corpus_opened(name, 0.0)
    qapp.processEvents()
    for modified in (False, True):
        window.setWindowModified(modified)
        qapp.processEvents()
        assert window.windowHandle().title() == "AgentPROV — " + name


def test_confirm_dialog_title_shows_the_placeholder_literally(qapp: Any, window: Any) -> None:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QDialog

    from agentprov_gui.ui import jobdialog

    label = "import · out" + PH + "x"
    spec = SimpleNamespace(tier="R1", destructive=False, label=label, writes=(), notes=())
    seen: list[str] = []

    def grab() -> None:
        for tl in qapp.topLevelWidgets():
            if isinstance(tl, QDialog) and tl.isVisible():
                seen.append(tl.windowHandle().title())
                tl.reject()

    QTimer.singleShot(0, grab)
    assert jobdialog.confirm(window, spec, "agentprov ...") is None  # type: ignore[arg-type]
    assert seen == ["Confirm: " + label]


def test_confirm_dialog_title_escapes_a_data_derived_label(qapp: Any, window: Any, tmp_path: Path) -> None:
    """GR-56 (S3): the confirm title takes the label built from a discovered corpus name, so bidi controls, isolates and
    NBSP in it are escaped like every other window title; a literal ``[*]`` still shows once."""
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QDialog

    from agentprov_gui.jobs.commands import FORMS, build_spec
    from agentprov_gui.ui import jobdialog

    hostile = (0x202E, 0x2066, 0x00A0)
    name = "corp" + chr(hostile[0]) + "txt.exe" + chr(hostile[1]) + chr(hostile[2]) + "x" + PH
    corpus = tmp_path / name
    out = corpus.with_name(corpus.name + "-revalidated")  # as RunsPage.revalidate builds it
    spec = build_spec(FORMS["recompute"], {"corpus": str(corpus), "dry_run": False, "out": str(out),
                                           "stages": "sem,prov,validation"})
    assert spec.tier == "R1"
    seen: list[str] = []

    def grab() -> None:
        for tl in qapp.topLevelWidgets():
            if isinstance(tl, QDialog) and tl.isVisible():
                seen.append(tl.windowHandle().title())
                tl.reject()

    QTimer.singleShot(0, grab)
    assert jobdialog.confirm(window, spec, "agentprov ...") is None
    assert len(seen) == 1
    title = seen[0]
    assert not [hex(ord(c)) for c in title if ord(c) in hostile]
    assert title == "Confirm: " + T.clean(spec.label, 120)
    assert title.count(PH) == 1
