"""S15 (D-448): the native layer is confined. PyObjC (``objc``, ``AppKit``, ``Foundation``, ``UserNotifications``,
``Cocoa``, ``PyObjCTools``, ``CoreFoundation``, ``Quartz``) is imported only in ``platform/macos.py``; the raw FFI and
pointer modules (``ctypes``, ``_ctypes``, ``cffi``, ``_cffi_backend``, ``shiboken6``) only in ``platform/windows.py``
(GR-14). String-literal ``import_module``/``__import__`` names count as imports. ``platform/macos.py`` never builds an
``NSAttributedString`` or an ``NSTextView`` (no content reaches native code)."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import pytest

from _ast_support import SRC, imported_names, modules, rel

PYOBJC = ("objc", "AppKit", "Foundation", "UserNotifications", "Cocoa", "PyObjCTools", "CoreFoundation", "Quartz")
FFI = ("ctypes", "_ctypes", "cffi", "_cffi_backend", "shiboken6")
NATIVE = "platform/macos.py"
HOME = {**dict.fromkeys(PYOBJC, NATIVE), **dict.fromkeys(FFI, "platform/windows.py")}


def test_pyobjc_only_in_the_native_module() -> None:
    bad = [f"{rel(p)}:{line}: {name}" for p, tree in modules() for line, name in imported_names(tree)
           if HOME.get(name.split(".")[0], rel(p)) != rel(p)]
    assert not bad, "\n".join(bad)


def test_native_module_builds_no_rich_text() -> None:
    import ast

    tree = ast.parse((SRC / NATIVE).read_text(encoding="utf-8"))
    banned = {"NSAttributedString", "NSTextView", "NSMutableAttributedString", "setAttributedStringValue_"}
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {
        n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert not (used & banned)


def test_native_chrome_is_off_offscreen_and_by_environment(qapp: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from agentprov_gui.platform import macos, native_chrome_enabled

    assert not native_chrome_enabled(True)  # offscreen platform plugin: never native
    assert not macos.available()
    monkeypatch.setenv("AGENTPROV_GUI_NATIVE_CHROME", "0")
    assert not native_chrome_enabled(True)


def test_qt_toolbar_fallback_has_every_action(qapp: Any, tmp_path: Path) -> None:
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QToolBar

    from agentprov_gui.platform.macos import ITEMS
    from agentprov_gui.settings import Settings
    from agentprov_gui.ui.mainwindow import MainWindow

    w = MainWindow(Settings(QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)), cache_dir=tmp_path / "c",
                   home=tmp_path / "home")
    assert w.chrome is None
    bars = w.findChildren(QToolBar)
    assert bars and set(ITEMS) <= set(w.action_map)
    assert {a.text() for a in bars[0].actions() if a.text()} >= {w.action_map[k].text() for k in ITEMS}
    w.close()


def test_accessibility_flags_change_the_graph(qapp: Any, mini_corpus: Path, tmp_path: Path) -> None:
    from agentprov.render.graph import build_model
    from PySide6.QtWidgets import QGraphicsSimpleTextItem

    from _corpus_support import first_prov
    from agentprov_gui.graph.layout import compute_layout
    from agentprov_gui.graph.scene import GraphScene
    from agentprov_gui.graph.viewgraph import full_view
    from agentprov_gui.ui import theme

    ex, doc = first_prov(mini_corpus)
    view = full_view(build_model(doc, ex=ex, mode="all"))
    layout = compute_layout(view, engine="layered", cache_dir=tmp_path).layout
    try:
        theme.ACCESS.update(differentiate=True, increase_contrast=True)
        scene = GraphScene(view, layout, theme.graph_palette(dark=False))
        texts = [i.text() for i in scene.layers["labels.full"].childItems() if isinstance(i, QGraphicsSimpleTextItem)]
        assert any("[C]" in t for t in texts)
        node = next(iter(scene.nodes.values()))
        assert node.base_pen.widthF() >= 1.6
    finally:
        theme.ACCESS.update(differentiate=False, increase_contrast=False)


@pytest.mark.skipif(sys.platform != "darwin" or os.environ.get("AGENTPROV_GUI_COCOA_TESTS") != "1",
                    reason="native smoke test: macOS with QT_QPA_PLATFORM=cocoa and AGENTPROV_GUI_COCOA_TESTS=1")
def test_cocoa_smoke_native_toolbar(tmp_path: Path) -> None:
    """Run in a fresh process on the cocoa platform: the toolbar attaches, every item maps to a QAction, the chrome
    above the content grows (macos-design §2.6 Tests)."""
    import subprocess

    code = f"""
import sys
from pathlib import Path
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
app = QApplication([])
from agentprov_gui.settings import Settings
from agentprov_gui.ui.mainwindow import MainWindow
from agentprov_gui.platform.macos import ITEMS
s = Settings(QSettings({str(tmp_path / 's.ini')!r}, QSettings.Format.IniFormat))
w = MainWindow(s, cache_dir=Path({str(tmp_path / 'c')!r}), home=Path({str(tmp_path / 'home')!r}))
w.show(); app.processEvents()
c = w.chrome
assert c is not None, 'native chrome not installed'
assert c.window.toolbar() == c.toolbar
ids = [str(i.itemIdentifier()) for i in c.toolbar.items()]
assert all(k in ids for k in ITEMS), ids
assert all(k in w.action_map for k in ITEMS)
c.set_activity(2, 5); c.set_progress(0.4); c.set_progress(None); c.set_activity(0, 5)
print('OK', ids)
w.close()
"""
    env = {**os.environ, "QT_QPA_PLATFORM": "cocoa", "AGENTPROV_HOME": str(tmp_path / "home")}
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=120)
    assert done.returncode == 0 and "OK" in done.stdout, done.stdout + done.stderr
