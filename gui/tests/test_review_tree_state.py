"""GR-36: the read-only snapshot sees created directories and sidecars beside a corpus, and opening a corpus with the
default layout cache placement writes only below ``$AGENTPROV_HOME/gui/cache/layout``, never under the corpora root."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from _corpus_support import tree_state
from test_viewer import _open, wait


def test_tree_state_sees_dirs_and_siblings(tmp_path: Path) -> None:
    root = tmp_path / "corpora"
    (root / "c.partial").mkdir(parents=True)
    (root / "c.partial" / "a.json").write_bytes(b"{}")
    before = tree_state(root)
    (root / "c.partial" / "gui-cache" / "layout").mkdir(parents=True)  # an empty directory inside the tree
    assert tree_state(root) != before
    before = tree_state(root)
    (root / "c.gui-sidecar.json").write_bytes(b"{}")  # a sidecar beside the corpus
    assert tree_state(root) != before
    before = tree_state(root)
    (root / "c.partial" / "gui-cache" / "layout").rmdir()
    (root / "c.partial" / "gui-cache").rmdir()
    (root / "c.gui-sidecar.json").unlink()
    assert tree_state(root) != before  # the root's own mtime moved


def test_tree_state_sees_chmod(tmp_path: Path) -> None:
    """GR-62: a permission change (which moves ctime, not mtime) on a file, a subdirectory or the root shows up."""
    root = tmp_path / "corpora"
    sub = root / "c.partial"
    sub.mkdir(parents=True)
    f = sub / "a.json"
    f.write_bytes(b"{}")
    for p, before_mode, after_mode in ((f, 0o600, 0o666), (sub, 0o700, 0o777), (root, 0o700, 0o755)):
        os.chmod(p, before_mode)
        before = tree_state(root)
        os.chmod(p, after_mode)
        assert tree_state(root) != before, p.name


def _main(qapp: Any, mini_corpus: Path, tmp_path: Path, **kw: Any) -> Any:
    from PySide6.QtCore import QSettings

    from agentprov_gui.settings import Settings
    from agentprov_gui.ui.mainwindow import MainWindow

    settings = Settings(QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat))
    settings.corpus_roots = [mini_corpus.parent]
    w = MainWindow(settings, **kw)
    w.show()
    return w


def _close(qapp: Any, w: Any) -> None:
    w.close()
    w.deleteLater()
    qapp.processEvents()


def _open_all(qapp: Any, w: Any, corpus: Path) -> None:
    v = _open(qapp, w, corpus)
    for row in range(v.model.rowCount()):
        v.exec_view.selectRow(row)
        wait(qapp, lambda: v.preview.graph.scene_ is not None)


def test_open_default_cache_is_read_only(qapp: Any, mini_corpus: Path, tmp_path: Path, _home: Path) -> None:
    corpora = mini_corpus.parent
    before = tree_state(corpora)
    w = _main(qapp, mini_corpus, tmp_path)  # no cache_dir, no home: the default placement
    try:
        _open_all(qapp, w, mini_corpus)
    finally:
        _close(qapp, w)
    assert tree_state(corpora) == before  # nothing created, changed or touched under the corpora root
    cache = _home / "gui" / "cache" / "layout"
    assert cache.is_dir() and any(cache.iterdir())


def test_explicit_home_governs_layout_cache(qapp: Any, mini_corpus: Path, tmp_path: Path, _home: Path) -> None:
    home = tmp_path / "explicit-home"
    corpora = mini_corpus.parent
    before = tree_state(corpora)
    w = _main(qapp, mini_corpus, tmp_path, home=home)
    try:
        _open_all(qapp, w, mini_corpus)
    finally:
        _close(qapp, w)
    assert tree_state(corpora) == before
    cache = home / "gui" / "cache" / "layout"
    assert cache.is_dir() and any(cache.iterdir())
    assert not (_home / "gui" / "cache" / "layout").exists()
