"""Documentation screenshots of the GUI (README "Desktop app"; ``docs/images/gui/``).

Usage (macOS, for the native chrome; elsewhere the Qt chrome is captured)::

    QT_QPA_PLATFORM=cocoa uv run --project gui python gui/tools/screenshots.py [--max-width N] [OUT_DIR [SCENE ...]]

Each picture is a **scene** (:data:`SCENES`, one function each); without SCENE arguments every scene is taken. The
user guide's pictures live in ``docs/user-guide/images/gui/`` (taken with ``--max-width 1200``); the README keeps only
:data:`README_SCENES` in ``docs/images/gui/`` (build log entry 45).

* **Without OUT_DIR** the pictures go to a new temporary folder outside the repository, whose path is printed, so a
  bare run never overwrites or recreates a committed picture (build log entry 47).
* **The README folder** takes only :data:`README_SCENES`: an OUT_DIR that is ``docs/images/gui/`` with any other scene
  (or with no scene names, which means every scene) is refused (exit 2).

* The corpus is synthetic: the three AgentDojo golden test logs, built by the core's test helper
  (``tests/unit/corpus/seal_support.py``) in a temporary directory, opened through a **relative** corpus root
  (``corpora``) so no home path appears. ``AGENTPROV_HOME`` is a temporary directory too. The work folder holding
  them is removed when the run ends, also on a guard refusal or an error (:func:`work_folder`).
* The New Job preview shows the program as ``agentprov`` (on the PATH), never a checkout path.
* Light appearance; content stays hidden (no Show content switch is turned on).
* **Leak guard:** before each image is saved, every visible string (labels, buttons, group box titles, line edits,
  text panes, status bar messages, table cells and headers, tree rows at every depth (capped), tab titles, window
  titles, graph labels, and with the native chrome the NSWindow title, subtitle, activity and search field) is scanned
  for account paths, e-mail addresses and key shapes; a hit refuses to save and exits 1.
* **This repository's own GitHub links** (``github.com/nickjones39/AgentPROV/…``) are split into their path and query
  segments before the scan (F-11): their segments could line up as a 40-character AWS-secret run. Each segment is still
  scanned, so a secret that is a whole segment, or any other key shape inside such a link, is caught. **Limitation:** a
  secret that contains '/' and sits inside one of these links is split too and no longer matches the AWS shape. Every
  other URL and all other text get the full scan, a key beside '/' or '+' included.
"""

from __future__ import annotations

import contextlib
import os
import re
import shutil
import sys
import tempfile
import time
from collections import deque
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Final

REPO = Path(__file__).resolve().parents[2]
#: The README's own picture folder and the only scenes it keeps (build log entries 45 and 47)
README_OUT: Final = REPO / "docs" / "images" / "gui"
README_SCENES: Final = ("agentprov-app", "viewer-graph")
LEAKS = re.compile(
    r"/Users/|/home/|C:\\\\Users|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|sk-[A-Za-z0-9_-]{10,}|"
    r"AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{20,}|xox[abp]-|-----BEGIN|AIza[0-9A-Za-z_-]{35}|hf_[A-Za-z0-9]{30,}|"
    r"github_pat_[A-Za-z0-9_]{22,}|(?i:bearer)\s+[A-Za-z0-9._~+/=-]{16,}|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}|"
    # an AWS secret access key: exactly 40 base64 characters with upper, lower and a digit (a hex sha1 or sha256 is
    # not); only a letter or digit bounds it, so a key beside '/' or '+' (a path or URL segment) is still caught, while
    # an unbroken longer run is not
    r"(?<![A-Za-z0-9])(?=[A-Za-z0-9/+]{0,39}[A-Z])(?=[A-Za-z0-9/+]{0,39}[a-z])(?=[A-Za-z0-9/+]{0,39}[0-9])"
    r"[A-Za-z0-9/+]{40}(?![A-Za-z0-9])"
)
#: F-11: the repository's own GitHub links (About, the README, the user guide). Their path segments can line up as a
#: 40-character base64 run (``com/nickjones39/AgentPROV/blob/main/docs``), which the AWS-secret shape flags. Before
#: matching, such a link is split into its segments (at ``/ ? # & =``), so each segment is checked on its own: a
#: 40-character secret that is a whole segment of one of these links is still caught, and everything outside them is
#: checked as before (a key beside '/' or '+' included). Only this repository's links are split, never another URL.
OWN_LINK = re.compile(r"(?:https?://)?(?:www\.)?github\.com/nickjones39/AgentPROV(?![A-Za-z0-9_.-])[^\s\"'<>()\[\]]*",
                      re.IGNORECASE)
_LINK_SEP = re.compile(r"[/?#&=]")


def leak_hits(text: str) -> list[str]:
    """The leak-shaped substrings of ``text`` (:data:`LEAKS`), with the repository's own links split first."""
    checked = OWN_LINK.sub(lambda m: " ".join(_LINK_SEP.split(m.group(0))), text)
    return [m.group(0) for m in LEAKS.finditer(checked)]


TREE_CAP = 5000  # model cells read per item view
#: ``--max-width N``: after the guard passed and the image was saved, scale it down to at most N pixels wide (smooth)
#: and re-save it with the strongest PNG compression, to keep documentation images small. ``None`` keeps the capture.
MAX_WIDTH: int | None = None


def _model_strings(model: Any) -> list[str]:
    """Display text of every row of ``model`` (tree children included, breadth first), at most ``TREE_CAP`` cells."""
    from PySide6.QtCore import QModelIndex, Qt

    out: list[str] = []
    queue = deque([QModelIndex()])
    while queue and len(out) < TREE_CAP:
        parent = queue.popleft()
        try:
            columns = model.columnCount(parent)
        except TypeError:  # a list model: one column
            columns = 1
        for r in range(model.rowCount(parent)):
            for c in range(max(1, columns)):
                index = model.index(r, c, parent)
                value = model.data(index, Qt.ItemDataRole.DisplayRole)
                if value is not None:
                    out.append(str(value))
                if c == 0 and model.rowCount(index) > 0:  # hasChildren is private on some PySide models
                    queue.append(index)
            if len(out) >= TREE_CAP:
                break
    return out[:TREE_CAP]


def visible_strings(root: Any) -> list[str]:
    from PySide6.QtCore import QModelIndex, Qt
    from PySide6.QtWidgets import (
        QAbstractButton,
        QAbstractItemView,
        QComboBox,
        QGraphicsSimpleTextItem,
        QGraphicsView,
        QGroupBox,
        QHeaderView,
        QLabel,
        QLineEdit,
        QPlainTextEdit,
        QStatusBar,
        QTabBar,
        QTextEdit,
        QWidget,
    )

    out = [root.windowTitle()]
    chrome = getattr(root, "chrome", None)
    if chrome is not None:  # the native title bar is in the capture, but its text is not Qt's
        out += chrome.visible_text()
    for w in [root, *root.findChildren(QWidget)]:
        if not w.isVisible():
            continue
        if isinstance(w, QLabel | QAbstractButton):
            out.append(w.text())
        elif isinstance(w, QGroupBox):
            out.append(w.title())
        elif isinstance(w, QLineEdit):
            out += [w.text(), w.placeholderText()]
        elif isinstance(w, QPlainTextEdit | QTextEdit):
            out += [w.toPlainText(), w.placeholderText()]
        elif isinstance(w, QStatusBar):
            out.append(w.currentMessage())
        elif isinstance(w, QComboBox):
            out += [w.itemText(i) for i in range(w.count())]
        elif isinstance(w, QTabBar):
            out += [w.tabText(i) for i in range(w.count())]
        elif isinstance(w, QHeaderView) and w.model() is not None:
            model, orientation = w.model(), w.orientation()
            horizontal = orientation == Qt.Orientation.Horizontal
            count = model.columnCount(QModelIndex()) if horizontal else model.rowCount(QModelIndex())
            for i in range(min(count, TREE_CAP)):
                value = model.headerData(i, orientation, Qt.ItemDataRole.DisplayRole)
                if value is not None:
                    out.append(str(value))
        elif isinstance(w, QAbstractItemView) and w.model() is not None:
            out += _model_strings(w.model())
        elif isinstance(w, QGraphicsView) and w.scene() is not None:
            out += [i.text() for i in w.scene().items() if isinstance(i, QGraphicsSimpleTextItem)]
    return out


def guard(widget: Any, name: str) -> None:
    hits = sorted({hit[:12] + "…" for s in visible_strings(widget) for hit in leak_hits(s)})
    if hits:
        print(f"{name}: refused, visible text matches the leak guard ({len(hits)} distinct)", file=sys.stderr)
        raise SystemExit(1)


def capture(widget: Any, path: Path) -> None:
    from agentprov_gui.platform import macos

    guard(widget, path.name)
    if not ((getattr(widget, "chrome", None) is not None or macos.available())
            and macos.capture_window_png(widget, str(path))):
        widget.grab().save(str(path))
    if MAX_WIDTH is not None:
        _shrink(path, MAX_WIDTH)


def _shrink(path: Path, width: int) -> None:
    """Scale a saved capture down to ``width`` pixels (never up) and save it with PNG compression level 0 (smallest)."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage

    image = QImage(str(path))
    if image.isNull():
        raise SystemExit(f"{path.name}: the saved capture cannot be read back")
    if image.width() > width:
        image = image.scaledToWidth(width, Qt.TransformationMode.SmoothTransformation)
    if not image.save(str(path), "PNG", 0):
        raise SystemExit(f"{path.name}: the scaled capture cannot be saved")


def pump(app: Any, seconds: float, until: Any = None) -> None:
    from PySide6.QtCore import QEventLoop

    end = time.time() + seconds
    while time.time() < end and not (until and until()):
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20)
        time.sleep(0.01)


def build_corpus(work: Path) -> Path:
    sys.path.insert(0, str(REPO / "tests" / "unit" / "corpus"))
    import seal_support  # the core's test helper: three golden AgentDojo logs, release mode

    class Factory:
        def mktemp(self, name: str) -> Path:
            return Path(tempfile.mkdtemp(prefix=name, dir=work))

    seal_support.working_corpus(Factory(), work / "corpora" / "agentdojo-dev")
    return work


def derive_corpus(work: Path) -> Path:
    """``agentprov derive`` of the working corpus into ``corpora/agentdojo-derived`` (D-706: full index rows with the
    task cell and the outcome facet, so the Viewer shows its task and outcome columns and the attack-succeeded marker).
    In-process through the core's own CLI entry; no network."""
    from agentprov.cli.main import main as cli

    out = work / "corpora" / "agentdojo-derived"
    code = cli(["derive", "--corpus", str(work / "corpora" / "agentdojo-dev"), "--out", str(out), "--progress", "off",
                "-q"])
    if code != 0:
        raise SystemExit(f"derive of the screenshot corpus ended with exit {code}")
    return out


def cli_shim(work: Path) -> Path:
    """``<work>/bin/agentprov``: runs this checkout's CLI through ``<work>/checkout`` (a symlink to the checkout), so a
    job record's interpreter path is a short temporary path, never a home path. The jobs the scenes start run the real
    CLI on the synthetic corpora under the temporary ``AGENTPROV_HOME``."""
    (work / "checkout").symlink_to(REPO, target_is_directory=True)
    shim = work / "bin" / "agentprov"
    shim.parent.mkdir()
    shim.write_text(f'#!/bin/sh\nexec "{work / "checkout" / ".venv" / "bin" / "python"}" -m agentprov "$@"\n',
                    encoding="utf-8")
    shim.chmod(0o755)
    return shim.parent


class Shots:
    """The shared state of a screenshot run: the application, the main window, the settings and the output folder."""

    def __init__(self, app: Any, window: Any, settings: Any, out: Path, work: Path) -> None:
        self.app, self.window, self.settings, self.out, self.work = app, window, settings, out, work
        self.jobs: list[Any] = []  # the jobs the job scenes started, oldest first
        self.prefs: Any = None  # the Settings dialog while Settings scenes run


def _open(s: Shots, name: str) -> Any:
    viewer = s.window.viewer
    s.window.go("Viewer")
    viewer.open_path(Path("corpora") / name)
    pump(s.app, 30, lambda: viewer.table is not None and viewer.model.rowCount() > 0
         and viewer.summary is not None and viewer.summary.path.name.startswith(name))
    pump(s.app, 0.5)
    return viewer


def _tab(tabs: Any, title: str) -> None:
    for i in range(tabs.count()):
        if tabs.tabText(i) == title:
            tabs.setCurrentIndex(i)
            return
    raise SystemExit(f"no tab named {title!r}")


def scene_viewer_graph(s: Shots) -> None:
    """The Viewer: corpora list, executions table and the PROV graph of the first execution."""
    viewer = _open(s, "agentdojo-dev")
    viewer.exec_view.selectRow(0)
    pump(s.app, 60, lambda: viewer.preview.graph.scene_ is not None)
    pump(s.app, 1.0)
    graph = viewer.preview.graph
    graph.view.set_zoom(1.25)  # full trusted-grammar labels (LOD "full")
    graph.view.centerOn(graph.scene_.sceneRect().center())
    pump(s.app, 0.5)
    capture(s.window, s.out / "viewer-graph.png")


def _row_with(viewer: Any, header: str, value: str) -> int:
    model = viewer.exec_view.model()
    from PySide6.QtCore import Qt

    cols = [c for c in range(model.columnCount()) if header in str(model.headerData(c, Qt.Orientation.Horizontal))]
    for r in range(model.rowCount()):
        if cols and value in str(model.data(model.index(r, cols[0]))):
            return r
    return 0


def scene_viewer_outcomes(s: Shots) -> None:
    """The Viewer on the derived corpus: task and outcome columns, their pickers, the attack-succeeded marker and the
    CLI line (D-706)."""
    from PySide6.QtCore import Qt

    viewer = _open(s, "agentdojo-derived")
    row = _row_with(viewer, "attack succeeded", "yes")
    viewer.exec_view.selectRow(row)
    model = viewer.exec_view.model()
    cols = [c for c in range(model.columnCount())
            if "attack succeeded" in str(model.headerData(c, Qt.Orientation.Horizontal))]
    if cols:  # scroll the table so the outcome columns are in view
        viewer.exec_view.scrollTo(model.index(row, cols[0]))
    _tab(viewer.preview.tabs, "SEM")
    pump(s.app, 1.0)
    capture(s.window, s.out / "viewer-outcomes.png")


def scene_viewer_aer(s: Shots) -> None:
    """The AER tab of one execution: records by kind with evidence class, attesting party and rules (content hidden)."""
    viewer = _open(s, "agentdojo-derived")
    viewer.exec_view.selectRow(0)
    _tab(viewer.preview.tabs, "AER")
    pump(s.app, 1.0)
    capture(s.window, s.out / "viewer-aer.png")


def _viewer_tabs(s: Shots, path: Path, *, busiest: bool = False) -> None:
    """Two executions of the derived corpus and one of the working corpus open in tabs of their own; the current tab
    shows its graph and PROV-JSON side by side, a statement selected in both. ``busiest`` selects the shown statement
    with the most edges (so the graph around it is drawn), else the first one the PROV-JSON tree shows."""
    viewer = _open(s, "agentdojo-dev")
    other = viewer.open_row(0)
    viewer = _open(s, "agentdojo-derived")
    panes = [viewer.open_row(1), viewer.open_row(0)]
    pump(s.app, 60, lambda: all(p is not None and p.state == "ready" and p.graph.scene_ is not None for p in panes))
    pane = panes[1]
    pump(s.app, 1.0)
    graph = pane.graph
    nodes = graph.scene_.nodes
    order = sorted(nodes, key=lambda k: -len(nodes[k].edges)) if busiest else list(nodes)
    key = next((k for k in order if pane.prov.reveal(k)), None)  # a statement the PROV-JSON tree shows
    if key is not None:
        graph.select(key, centre=True)
        graph.prov_btn.click()
    graph.view.set_zoom(1.0)
    if key is not None:
        graph.view.centerOn(nodes[key].shape)
    pump(s.app, 0.5)
    capture(s.window, path)
    viewer.close_other_tabs(keep=None)
    viewer.close_current_tab()
    viewer.show_corpora()
    del other


def scene_viewer_tabs(s: Shots) -> None:
    """Viewer tabs (D-840..D-845): executions open in tabs of their own, the graph and PROV-JSON side by side."""
    _viewer_tabs(s, s.out / "viewer-tabs.png")


def scene_agentprov_app(s: Shots) -> None:
    """The README's top picture: the Viewer with execution tabs (as ``viewer-tabs``), centred on the statement with the
    most edges."""
    _viewer_tabs(s, s.out / "agentprov-app.png", busiest=True)


def scene_new_job(s: Shots) -> None:
    """New Job: the import form with its command preview and tier, scrolled to the conformance box."""
    from PySide6.QtWidgets import QScrollArea

    from agentprov_gui.jobs.commands import FORMS
    from agentprov_gui.ui.jobdialog import JobDialog

    s.window.go("Runs")
    # GR-20: job paths are absolute; the work folder is a short temporary path (never a home path). The CLI of this
    # build offers --skip-prov-conformance, so the box is enabled as the app enables it after reading --help (G2c-5).
    dialog = JobDialog(FORMS["import"], program=("agentprov",), parent=s.window,
                       conformance_option="--skip-prov-conformance",
                       preset={"source": "agentdojo", "corpus": str(s.work / "corpora" / "agentdojo-dev"),
                               "snapshot": "2024-06", "fetch": True, "limit": 5})
    dialog.resize(760, 720)
    dialog.show()
    pump(s.app, 0.5)
    scroll = dialog.findChild(QScrollArea)
    scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())  # show the conformance box
    pump(s.app, 0.5)
    capture(dialog, s.out / "new-job.png")
    dialog.close()


def _start_jobs(s: Shots) -> None:
    """Two real, light jobs on the derived corpus (validate, then verify), started as the Runs page starts them
    (``agentprov jobs start``), and waited for."""
    if s.jobs:
        return
    from agentprov_gui.jobs.commands import FORMS, build_spec

    corpus = str(s.work / "corpora" / "agentdojo-derived")
    for name, values in (("validate", {"corpus": corpus, "strict": True}), ("verify", {"corpus": corpus})):
        job = s.window.manager.spawn(build_spec(FORMS[name], values))
        s.jobs.append(job)
        pump(s.app, 120, lambda j=job: (s.window.manager.refresh() or True) and s.window.manager.jobs[j.job_id].state
             != "running")
    s.window.runs.refresh()
    pump(s.app, 2.0)


def scene_runs_jobs(s: Shots) -> None:
    """Runs › Jobs: the job list and the dashboard of a finished validate job."""
    _start_jobs(s)
    s.window.go("Runs")
    _tab(s.window.runs.tabs, "Jobs")
    s.window.runs.select(s.jobs[0].job_id)
    pump(s.app, 1.5)
    capture(s.window, s.out / "runs-jobs.png")


def scene_runs_batches(s: Shots) -> None:
    """Runs › Batches: a two-step batch (stats, then verify) created and started through ``agentprov batch``."""
    from agentprov_gui.jobs.commands import FORMS, build_spec

    corpus = str(s.work / "corpora" / "agentdojo-derived")
    specs = [build_spec(FORMS["stats"], {"corpus": corpus, "tables": "counts"}),
             build_spec(FORMS["verify"], {"corpus": corpus, "level": "checksums"})]
    s.window.go("Runs")
    batch = s.window.runs.start_batch("guide demo batch", specs, continue_on_failure=False)
    if batch is None:
        raise SystemExit("the demo batch was refused")
    pump(s.app, 120, lambda: (s.window.runs.refresh() or True) and all(
        st.state in ("done", "failed", "blocked", "skipped") for b in s.window.runs.batches if b.batch_id ==
        batch.batch_id for st in b.steps))
    _tab(s.window.runs.tabs, "Batches")
    s.window.runs.refresh()
    pump(s.app, 1.5)
    capture(s.window, s.out / "runs-batches.png")


def scene_logs(s: Shots) -> None:
    """Logs: the log records of the validate job."""
    _start_jobs(s)
    s.window._open_log(s.jobs[0].job_id)  # what the Runs page's Open Log does
    pump(s.app, 2.5)
    capture(s.window, s.out / "logs.png")


def scene_system(s: Shots) -> None:
    """System: CPU, memory and the processes of the selected job, sampled while the page is visible."""
    s.window.go("System")
    pump(s.app, 4.0)
    capture(s.window, s.out / "system.png")


def scene_licences(s: Shots) -> None:
    """Licences: the included sources with their licence facts (read-only)."""
    s.window.go("Licences")
    pump(s.app, 1.5)
    capture(s.window, s.out / "licences.png")


def scene_package(s: Shots) -> None:
    """Package: the nine steps, on the working corpus (nothing is run or uploaded)."""
    s.window.go("Package")
    page = s.window.package
    page.corpus.setText(str(s.work / "corpora" / "agentdojo-dev"))
    page.corpus.editingFinished.emit()  # as when the field loses focus
    pump(s.app, 2.5)
    capture(s.window, s.out / "package.png")


def scene_package_finish(s: Shots) -> None:
    """Package › 9 Finish with its two Zenodo actions (D-880), on the working corpus. Neither is pressed: no file is
    written, no uploader runs and nothing is uploaded."""
    from agentprov_gui.ui.package import STEPS

    s.window.go("Package")
    page = s.window.package
    page.corpus.setText(str(s.work / "corpora" / "agentdojo-dev"))
    page.corpus.editingFinished.emit()
    page.deposit.setText("deposits/agentdojo-dev")
    page.metadata.setText("release.toml")
    page.steps.setCurrentRow(len(STEPS) - 1)
    pump(s.app, 2.5)
    capture(s.window, s.out / "package-finish.png")


def scene_zenodo_drafts(s: Shots) -> None:
    """Create Zenodo drafts… as it opens, with a placeholder community and no deposit listed: the field shows its
    format. Start is never pressed, so no uploader runs, no keychain is read and nothing reaches the network."""
    from agentprov_gui.ui.zenodo import ZenodoDraftsDialog

    dialog = ZenodoDraftsDialog(s.window.manager.cli, None, s.window,
                                settings={"zenodo.target_preselect": "sandbox", "zenodo.communities": ["example-community"]})
    dialog.resize(900, 640)
    dialog.show()
    pump(s.app, 1.0)
    capture(dialog, s.out / "zenodo-drafts.png")
    dialog.close()


def _settings_dialog(s: Shots) -> Any:
    from agentprov_gui.ui.dialogs import SettingsDialog

    prefs = SettingsDialog(s.settings, s.window)
    prefs.resize(900, 760)
    prefs.show()
    pump(s.app, 4.0)  # the panes load their values with `agentprov settings list` / `prices list` (local CLI calls)
    return prefs


SETTINGS_TABS: Final = ("General", "Appearance", "Viewer", "Jobs", "Compute", "CI", "Dev Runs", "Keys",
                        "Local Models", "Prices", "Estimate", "Zenodo")


def _local_models(s: Shots, prefs: Any) -> None:
    """Settings › Local Models filled in for a placeholder model (example-model on omlx; D-828). The form is only typed
    into: nothing is saved (the dialog is never accepted), no server is asked and no folder is searched."""
    from agentprov_gui.ui.settings_panes import LocalModelsPane

    pane = prefs.findChild(LocalModelsPane)
    pane.endpoint.setCurrentText("omlx")
    pane.model.setEditText("example-model")
    pane._switch()  # as when the model id is picked
    pane.size_gb.setText("3.0")
    pane.active.setText("4")
    pane.context.setText("32768")


def _keys(s: Shots, prefs: Any) -> None:
    """Settings › Keys with its endpoint and key-variable columns wide enough for the names (status only: the keychain
    is never checked here)."""
    from agentprov_gui.ui.livepanes import KeysPane

    table = prefs.findChild(KeysPane).table
    for column in (0, 1):
        table.resizeColumnToContents(column)


def _zenodo(s: Shots, prefs: Any) -> None:
    """Settings › Zenodo typed into with placeholders (a community, one creator; D-880). Nothing is saved: the dialog is
    never accepted. No token is a setting."""
    from agentprov_gui.ui.zenodo import ZenodoPane

    pane = prefs.findChild(ZenodoPane)
    pane.communities.setText("example-community")
    pane.creators.setPlainText("Example Author; ; Example University")


#: Settings scenes that fill a pane before the capture (the others show the pane as it loads)
SETTINGS_PREPARE: Final = {"Keys": _keys, "Local Models": _local_models, "Zenodo": _zenodo}


def _settings_scene(tab: str) -> Any:
    def scene(s: Shots) -> None:
        from PySide6.QtWidgets import QTabWidget

        if s.prefs is None:  # one dialog for every Settings scene: the panes load once
            s.prefs = _settings_dialog(s)
        prefs = s.prefs
        tabs = next(w for w in prefs.findChildren(QTabWidget) if w.parent() is prefs)
        _tab(tabs, tab)
        if tab in SETTINGS_PREPARE:
            SETTINGS_PREPARE[tab](s, prefs)
        prefs.raise_()
        prefs.activateWindow()
        pump(s.app, 1.0)  # the Keys pane is never checked here: no keychain access
        capture(prefs, s.out / f"settings-{tab.lower().replace(' ', '-')}.png")

    scene.__doc__ = f"Settings › {tab}."
    return scene


#: Stub answers for the Run Live scenes (no backend, no keychain, no server, no network): a catalogue holding a subset
#: of AgentDojo's suites and attacks, placeholder model ids (example-model), a scripted estimate.
STUB_CATALOGUE: Final = {
    "format": "agentprov-backend-catalogue/0.1", "backend": "agentdojo", "benchmark_version": "v1.2.2",
    "benchmark_versions": ["v1.2.2"],
    "suites": [{"name": name, "user_tasks": [f"user_task_{i}" for i in range(u)],
                "injection_tasks": [f"injection_task_{i}" for i in range(n)], "tool_definition_chars": 4000}
               for name, u, n in (("workspace", 40, 14), ("travel", 20, 7), ("banking", 16, 9), ("slack", 21, 5))],
    "attacks": [{"name": a, "dos": dos, "refused": None, "needs": []}
                for a, dos in (("important_instructions", False), ("direct", False), ("ignore_previous", False),
                               ("tool_knowledge", False), ("dos", True))]}
STUB_PRICES: Final = {
    "format": "agentprov-prices-list/0.1", "stale_days": 60, "shipped": {"rows": 1, "as_of": "2026-10-21"},
    "refreshed": {"rows": 0, "as_of": None}, "overrides": [],
    "endpoints": [{"name": "openrouter", "local": False, "models": [
        {"id": "vendor/example-model", "model": "vendor/example-model", "provider": "openrouter", "input": "1",
         "output": "2", "cached_input": None, "source": "stub", "as_of": "2026-10-21", "stale": False, "note": ""}]},
        {"name": "lmstudio", "local": True, "models": []}]}


def _stub_models(endpoint: str, identity: bool) -> dict[str, Any]:
    from agentprov_gui.live import models as M

    base = "http://127.0.0.1:1234/v1"
    if identity:
        return {"format": M.IDENTITY_FORMAT, "model_id": "example-model", "endpoint": endpoint, "base_url": base,
                "server": {"kind": "lmstudio", "version": "0.0.0-stub"}, "identity_sha256": "sha256:" + "0" * 64,
                "files": {"method": "stub", "label": "example-model", "weights_hashed": False,
                          "files": [{"name": "example-model.gguf", "size": 1_000_000_000, "sha256": None,
                                     "sha256_source": "not_hashed"}]}}
    return {"format": M.LOCAL_FORMAT, "endpoints": [{
        "endpoint": endpoint, "base_url": base, "status": "up",
        "server": {"kind_observed": "lmstudio", "version": "0.0.0-stub"},
        "models": [{"id": "example-model", "params": "8B", "quantization": "Q4_K_M", "size_bytes": 1_000_000_000,
                    "loaded": True, "tool_use": True, "remote": False, "servable": True}]}]}


def _stub_run(_manager: Any, argv: list[str], *, stdin_fd: int | None = None, timeout: float = 0
              ) -> tuple[int, bytes, bytes]:
    import json

    if stdin_fd is not None:
        os.close(stdin_fd)
    if argv[0] == "info":
        return 0, json.dumps({"source_id": argv[1], "parts": [{"live": "partial"}]}).encode(), b""
    if "--catalogue" in argv:
        if argv[-1] != "agentdojo":
            return 3, b"", f"agentprov: the backend environment of {argv[-1]} is not built".encode()
        return 0, json.dumps(STUB_CATALOGUE).encode(), b""
    if argv[:2] == ["prices", "list"]:
        return 0, json.dumps(STUB_PRICES).encode(), b""
    if argv[0] == "models":
        return 0, json.dumps(_stub_models(argv[2], "--model-id" in argv)).encode(), b""
    if argv[0] == "estimate":
        attacks = argv[argv.index("--attack") + 1].split(",") if "--attack" in argv else []
        units = 16 + 16 * 9 * len(attacks)
        doc = {"format": "agentprov-estimate/0.1", "units": units, "attempts_due": 3 * units, "cost_p50": "0",
               "cost_p90": "0", "cost_worst": "0", "seconds_p50": 20.0 * units, "seconds_p90": 45.0 * units,
               "price": None, "planned_with": "model", "plan": {"plan_sha256": "0" * 64}, "warnings": [],
               "text": [f"{units:,} cell run(s); scripted transport: no cost (stub estimate for the user guide).",
                        f"Plan 0000…: {units} cells", "By suite: banking"]}
        return 0, json.dumps(doc).encode(), b""
    return 2, b"", b"not offered by the screenshot stub"


def _run_live(s: Shots, *, endpoint: bool) -> Any:
    from agentprov_gui.live import keychain
    from agentprov_gui.live.plan import ENDPOINTS_REL
    from agentprov_gui.live.runspec import RunSettings
    from agentprov_gui.ui.runlive import DEV_SCRIPT, RunLiveDialog

    keychain.status = lambda cli: keychain.KeychainStatus(True, "stub")  # no keychain access in a screenshot
    keychain.present = lambda cli, names: dict.fromkeys(names, False)
    checkout = None
    if endpoint:  # a two-endpoint endpoints.toml: one local server, one API provider (placeholder entries)
        checkout = s.work / "stub-repo"
        path = checkout / ENDPOINTS_REL
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('[endpoints.lmstudio]\nbase_url = "http://127.0.0.1:1234/v1"\nlocal = true\n\n'
                        '[endpoints.openrouter]\nbase_url = "https://openrouter.ai/api/v1"\n'
                        'api_key_env = "OPENROUTER_API_KEY"\nlocal = false\n', encoding="utf-8")
    script = s.work / "scripted-dev.json"  # the shipped dev script, copied so its path is a temporary one
    if not script.exists():
        script.write_bytes(DEV_SCRIPT.read_bytes())
    preset = RunSettings(campaign="guide", script=str(script), suites=("banking",),
                         attacks=("important_instructions",), scripted=not endpoint,
                         model="lmstudio" if endpoint else "", model_id="example-model" if endpoint else "",
                         containment="vm" if endpoint else "", corpus=str(s.work / "corpora" / "agentdojo-live-guide"))
    dialog = RunLiveDialog(s.window.manager, home=s.work / "apv-home", checkout=checkout, preset=preset, run=_stub_run, conformance_option="--skip-prov-conformance",
                           parent=s.window)
    dialog.resize(1150, 900)
    dialog.show()
    pump(s.app, 10, lambda: dialog.estimate_result is not None)
    pump(s.app, 1.5)
    return dialog


def scene_run_live(s: Shots) -> None:
    """Run Live with the scripted transport: backend picker, cells from the backend's catalogue, attack selection and
    the estimate (stub answers; nothing runs)."""
    dialog = _run_live(s, endpoint=False)
    capture(dialog, s.out / "run-live.png")
    dialog.close()


def scene_run_live_estimate(s: Shots) -> None:
    """Run Live scrolled to its end: the attacks, the run settings and the estimate (stub answers; nothing runs)."""
    from PySide6.QtWidgets import QScrollArea

    dialog = _run_live(s, endpoint=False)
    scroll = dialog.findChild(QScrollArea)
    if scroll is not None:
        scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
    pump(s.app, 1.0)
    capture(dialog, s.out / "run-live-estimate.png")
    dialog.close()


def scene_run_live_models(s: Shots) -> None:
    """Run Live with a local endpoint: the model picker filled from ``agentprov models`` (a stub listing of a
    placeholder model), the per-OS containment choices and the declared-containment note."""
    from PySide6.QtWidgets import QScrollArea

    dialog = _run_live(s, endpoint=True)
    pump(s.app, 5, lambda: "lmstudio" in getattr(dialog, "model_lists", {}))
    scroll = dialog.findChild(QScrollArea)
    if scroll is not None:
        scroll.verticalScrollBar().setValue(0)
    pump(s.app, 1.0)
    capture(dialog, s.out / "run-live-models.png")
    dialog.close()


def scene_model_identity(s: Shots) -> None:
    """The Model Identity dialog for a placeholder local model (a stub identity record)."""
    import json

    from agentprov_gui.live import models as M
    from agentprov_gui.ui.runlive import IdentityDialog

    record = M.parse_identity(0, json.dumps(_stub_models("lmstudio", True)).encode())
    if record is None:
        raise SystemExit("the stub identity record does not parse")
    dialog = IdentityDialog(record, s.window)
    dialog.resize(720, 520)
    dialog.show()
    pump(s.app, 1.0)
    capture(dialog, s.out / "model-identity.png")
    dialog.close()


def scene_about(s: Shots) -> None:
    """About AgentPROV."""
    from agentprov_gui.ui.dialogs import AboutDialog

    dialog = AboutDialog(s.settings.checkout, s.window)
    dialog.show()
    pump(s.app, 1.0)
    capture(dialog, s.out / "about.png")
    dialog.close()


#: Scenes by name, in the order a full run takes them. ``screenshots.py OUT_DIR [SCENE ...]`` runs the named ones only.
SCENES: dict[str, Any] = {
    "viewer-graph": scene_viewer_graph,
    "viewer-outcomes": scene_viewer_outcomes,
    "viewer-aer": scene_viewer_aer,
    "viewer-tabs": scene_viewer_tabs,
    "agentprov-app": scene_agentprov_app,
    "new-job": scene_new_job,
    "runs-jobs": scene_runs_jobs,
    "runs-batches": scene_runs_batches,
    "logs": scene_logs,
    "system": scene_system,
    "licences": scene_licences,
    "package": scene_package,
    "package-finish": scene_package_finish,
    "zenodo-drafts": scene_zenodo_drafts,
    **{f"settings-{tab.lower().replace(' ', '-')}": _settings_scene(tab) for tab in SETTINGS_TABS},
    "run-live": scene_run_live,
    "run-live-estimate": scene_run_live_estimate,
    "run-live-models": scene_run_live_models,
    "model-identity": scene_model_identity,
    "about": scene_about,
}


@contextlib.contextmanager
def work_folder() -> Iterator[Path]:
    """A fresh private (0700) work folder, removed on exit whether the run succeeded or not (a leak-guard refusal, an
    error or Ctrl-C included). The process leaves it first; the removal never follows a symlink, so the
    ``checkout`` link to this repository (:func:`cli_shim`) is unlinked and its target left alone. A short absolute
    path on POSIX (``/tmp``) for the job forms; elsewhere the default temporary folder."""
    short = Path("/tmp")  # noqa: S108
    work = Path(tempfile.mkdtemp(prefix="agentprov-shots-", dir=short if short.is_dir() else None))
    cwd = os.getcwd()
    try:
        yield work
    finally:
        os.chdir(cwd)
        shutil.rmtree(work, ignore_errors=True)


def main(argv: list[str]) -> int:
    global MAX_WIDTH
    args = list(argv[1:])
    if "--max-width" in args:
        at = args.index("--max-width")
        MAX_WIDTH = int(args[at + 1])
        del args[at:at + 2]
    names = args[1:] or list(SCENES)
    unknown = [n for n in names if n not in SCENES]
    if unknown:
        print(f"unknown scene(s): {', '.join(unknown)}; known: {', '.join(SCENES)}", file=sys.stderr)
        return 2
    if args:
        out = Path(args[0]).resolve()
        extra = [n for n in names if n not in README_SCENES]
        if out == README_OUT.resolve() and extra:
            print(f"{README_OUT.relative_to(REPO)} keeps only {', '.join(README_SCENES)} (build log entry 45); refused: "
                  f"{', '.join(extra)}. The user guide's pictures go to docs/user-guide/images/gui.", file=sys.stderr)
            return 2
    else:  # A2: a bare run never writes into the repository
        out = Path(tempfile.mkdtemp(prefix="agentprov-shots-out-"))
        print(f"no OUT_DIR given: writing to {out}")
    out.mkdir(parents=True, exist_ok=True)
    with work_folder() as work:
        return _run(work, out, names)


def _run(work: Path, out: Path, names: list[str]) -> int:
    """Take the ``names`` scenes into ``out``, with every temporary file under ``work``."""
    os.environ["AGENTPROV_HOME"] = str(work / "apv-home")
    build_corpus(work)
    derive_corpus(work)
    bindir = cli_shim(work)
    os.environ["PATH"] = f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}"
    os.chdir(work)
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    app = QApplication([])
    from agentprov_gui.jobs.manager import CliLocator
    from agentprov_gui.settings import Settings
    from agentprov_gui.ui import theme
    from agentprov_gui.ui.mainwindow import MainWindow

    theme.apply_scheme("light")
    settings = Settings(QSettings(str(work / "settings.ini"), QSettings.Format.IniFormat))
    settings.corpus_roots = [Path("corpora")]
    settings.checkout = work / "checkout"  # the symlink: panes and dialogs show a temporary path, never a home path
    window = MainWindow(settings, cache_dir=work / "layout", home=work / "apv-home")
    window.manager.cli = CliLocator(None, ("agentprov",))  # the shim on PATH; no checkout, so no shared job queue
    window.resize(1560, 980)
    window.show()
    pump(app, 1.5)
    window.viewer.refresh()
    shots = Shots(app, window, settings, out, work)
    for name in names:
        if shots.prefs is not None and not name.startswith("settings-"):
            shots.prefs.close()
            shots.prefs = None
        SCENES[name](shots)
    if shots.prefs is not None:
        shots.prefs.close()
    window.close()
    print("saved", ", ".join(f"{n}.png" for n in names))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
