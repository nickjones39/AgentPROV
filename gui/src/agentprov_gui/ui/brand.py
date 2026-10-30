"""The app icon and the mark (brand note ``docs/reports/gui/logo/brand.md``).

The PNGs in ``data/icons/`` are rendered from ``docs/images/brand/*.svg`` by ``gui/tools/make_icons.py`` (no QtSvg at
run time). A bundle gets its Finder, Dock, Explorer and desktop icons from the packaging files. The window icon set
here is the one Qt shows (title bars, the taskbar, and the Dock for an unbundled run).
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon, QPixmap

__all__ = ["ICONS", "app_icon", "mark_pixmap"]

ICONS: Final = Path(__file__).resolve().parent.parent / "data" / "icons"
#: the window icon's sizes (make_icons.WINDOW_SIZES)
_SIZES: Final = (16, 32, 64, 128, 256, 512)


def app_icon() -> QIcon:
    icon = QIcon()
    for n in _SIZES:
        icon.addFile(str(ICONS / f"agentprov-{n}.png"), QSize(n, n))
    return icon


def mark_pixmap(points: int, *, dark: bool, ratio: float = 1.0) -> QPixmap:
    """The flat mark for a light (or ``dark``) background, ``points`` square; the 2x file serves Retina screens."""
    name = "agentprov-mark-on-dark" if dark else "agentprov-mark"
    icon = QIcon(str(ICONS / f"{name}.png"))  # QIcon picks up the @2x file beside it
    return icon.pixmap(QSize(points, points), ratio)
