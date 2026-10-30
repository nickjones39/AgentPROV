"""GR-38 (macos-design §2.6 fallback): a failure after the native toolbar is attached detaches it again, so the Qt
toolbar the caller then builds is never shown beside a native toolbar whose delegate is gone. A real, never-shown
NSWindow stands in for the Qt window; Qt runs offscreen. Skipped off macOS."""

from __future__ import annotations

import sys
from typing import Any

import pytest

from agentprov_gui.platform import macos

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="AppKit is macOS-only")


def _install(qapp: Any, monkeypatch: pytest.MonkeyPatch, window_menu: Any) -> tuple[Any, Any]:
    appkit = pytest.importorskip("AppKit")
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QWidget

    appkit.NSApplication.sharedApplication()
    style = appkit.NSWindowStyleMaskTitled | appkit.NSWindowStyleMaskClosable | appkit.NSWindowStyleMaskResizable
    nswin = appkit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        ((0, 0), (800, 600)), style, appkit.NSBackingStoreBuffered, True
    )
    nswin.setReleasedWhenClosed_(False)
    monkeypatch.setattr(macos, "available", lambda: True)
    monkeypatch.setattr(macos, "_ns_window", lambda w: nswin)
    monkeypatch.setattr(macos, "_window_menu", window_menu)
    widget = QWidget()
    actions = {k: QAction(k, widget) for k in macos.ITEMS}
    return macos.install(widget, actions), nswin


def test_late_failure_detaches_the_native_toolbar(qapp: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: Any, **kwargs: Any) -> bool:
        raise RuntimeError("injected")

    chrome, nswin = _install(qapp, monkeypatch, boom)
    assert chrome is None
    assert nswin.toolbar() is None  # the caller's Qt toolbar is the only one


def test_control_keeps_the_native_toolbar(qapp: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[bool] = []
    monkeypatch.setattr(macos, "_request_authorisation", lambda: asked.append(True), raising=False)
    chrome, nswin = _install(qapp, monkeypatch, lambda *a, **k: True)
    assert asked == [True]  # GR-67: notification authorisation is asked at install, not at the first notification
    assert chrome is not None
    assert nswin.toolbar() == chrome.toolbar
    assert nswin.toolbar().delegate() is not None
