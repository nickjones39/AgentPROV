"""G1 exit criteria on a real corpus (read-only): set ``AGENTPROV_GUI_REAL_CORPUS`` to a corpus directory and,
optionally, ``AGENTPROV_GUI_REAL_EX`` to its largest execution. Skipped otherwise (never in the default run).

Read-only is checked on the top level of the corpus tree (every entry's size and mtime) and on the absence of a lock;
hashing a multi-gigabyte corpus is not done here."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import pytest

from test_viewer import wait

REAL = os.environ.get("AGENTPROV_GUI_REAL_CORPUS")
pytestmark = [pytest.mark.real_corpus, pytest.mark.skipif(not REAL, reason="AGENTPROV_GUI_REAL_CORPUS is not set")]


def _top(root: Path) -> dict[str, tuple[int, int]]:
    return {p.name: (p.lstat().st_size, p.lstat().st_mtime_ns) for p in sorted(root.iterdir())}


def test_open_within_budget_and_read_only(qapp: Any, tmp_path: Path) -> None:
    from PySide6.QtCore import QSettings

    from agentprov_gui.readmodel.corpus import summarise
    from agentprov_gui.settings import Settings
    from agentprov_gui.ui.mainwindow import MainWindow

    assert REAL is not None
    summary = summarise(Path(REAL))
    assert summary.root is not None
    before = _top(summary.root)
    settings = Settings(QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    settings.corpus_roots = [summary.path.parent]
    w = MainWindow(settings, cache_dir=tmp_path / "layout")
    w.show()
    v = w.viewer
    started = time.perf_counter()
    v.open_path(Path(REAL))
    wait(qapp, lambda: v.table is not None and v.model.rowCount() > 0, 30)
    elapsed = time.perf_counter() - started
    print(f"open: {len(v.table):,} rows in {elapsed:.2f} s")
    assert elapsed <= 3.0
    ex = os.environ.get("AGENTPROV_GUI_REAL_EX")
    row = v.model.order.index(v.table.columns["ex"].index(ex)) if ex else 0
    started = time.perf_counter()
    v.exec_view.selectRow(row)
    wait(qapp, lambda: v.preview.graph.scene_ is not None, 120)
    print(f"graph: {time.perf_counter() - started:.2f} s; {v.preview.graph.status.text()}")
    g = v.preview.graph
    frames = []
    for zoom in (0.3, 0.6, 1.3):
        g.view.set_zoom(zoom)
        qapp.processEvents()
        t = time.perf_counter()
        g.view.viewport().grab()
        frames.append(time.perf_counter() - t)
    print("frames", [round(f, 3) for f in frames])
    assert max(frames) < 0.25  # interactive in the default view
    w.close()
    assert _top(summary.root) == before
