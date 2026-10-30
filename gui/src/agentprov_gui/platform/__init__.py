"""Platform chrome (D-440, D-449). Only ``platform/macos.py`` exists so far; Windows and Linux use the Qt chrome.

:func:`native_chrome_enabled` honours Settings › Experimental › "Native macOS toolbar" (on by default on macOS) and the
environment variable ``AGENTPROV_GUI_NATIVE_CHROME=0``.
"""

from __future__ import annotations

import os
import sys

__all__ = ["native_chrome_enabled"]


def native_chrome_enabled(setting: bool) -> bool:
    """Only on macOS with Qt's ``cocoa`` platform plugin: under ``offscreen`` or ``minimal`` a window id is not an
    ``NSView`` pointer, and treating it as one would crash."""
    if sys.platform != "darwin" or os.environ.get("AGENTPROV_GUI_NATIVE_CHROME") == "0":
        return False
    from PySide6.QtGui import QGuiApplication

    return setting and QGuiApplication.platformName() == "cocoa"
