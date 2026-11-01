"""Platform chrome (D-440, D-449). Only ``platform/macos.py`` exists so far; Windows and Linux use the Qt chrome.

:func:`native_chrome_enabled` honours Settings › Experimental › "Native macOS toolbar" (on by default on macOS) and the
environment variable ``AGENTPROV_GUI_NATIVE_CHROME=0``.
"""

from __future__ import annotations

import os
import sys
from typing import Final

__all__ = ["ACTIVITY_TIP", "SEARCH_TIP", "TOOLBAR_TIPS", "native_chrome_enabled"]

#: what each toolbar action does (the tooltip of its button, in the Qt and the native toolbar)
TOOLBAR_TIPS: Final = {
    "toggleSidebar": "Shows or hides the sidebar.",
    "openCorpus": "Opens a corpus folder in the Viewer.",
    "reload": "Reloads the Viewer's list of corpora from the corpus roots.",
    "newJob": "Opens the Runs page and its New Job menu, with a form for each command.",
    "devRun": "Starts a dev run, after you confirm its plan: a quick offline import, validate and recompute "
              "--dry-run of a few executions of every importable part, in scratch corpora.",
}
#: the job count's tooltip (the native toolbar's activity item, the Qt status bar)
ACTIVITY_TIP: Final = "The jobs running now; when none is running, the number of ended jobs on record. Runs lists "\
                      "them."
#: the toolbar search field's tooltip
SEARCH_TIP: Final = "Filters the Viewer's executions by id: type part of an execution id"


def native_chrome_enabled(setting: bool) -> bool:
    """Only on macOS with Qt's ``cocoa`` platform plugin: under ``offscreen`` or ``minimal`` a window id is not an
    ``NSView`` pointer, and treating it as one would crash."""
    if sys.platform != "darwin" or os.environ.get("AGENTPROV_GUI_NATIVE_CHROME") == "0":
        return False
    from PySide6.QtGui import QGuiApplication

    return setting and QGuiApplication.platformName() == "cocoa"
