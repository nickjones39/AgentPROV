"""The app icon and the mark (brand note ``docs/reports/gui/logo/brand.md``), and the window frame's own drawing.

The PNGs in ``data/icons/`` are rendered from ``docs/images/brand/*.svg`` by ``gui/tools/make_icons.py`` (no QtSvg at
run time). A bundle gets its Finder, Dock, Explorer and desktop icons from the packaging files. The window icon set
here is the one Qt shows (title bars, the taskbar, and the Dock for an unbundled run).

**The frame (D-1060's house style):** the small monochrome glyphs of the sidebar and the Qt toolbar are drawn as Qt
paths here (no image files), in a token colour, so they follow light and dark. :class:`SourceListDelegate` draws a
list as a macOS source list: section headings in small capitals, rows of a comfortable height and a rounded selection
from the theme. :func:`page_layout` gives a read-only page (Logs, System, Licences, Docs, Assistant) its page title and
the style's margins.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Final

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from agentprov_gui.ui import theme
from agentprov_gui.ui.forms import CommandCard, caption
from agentprov_gui.ui.safe import SafeLabel

__all__ = ["GLYPHS", "GLYPH_ROLE", "ICONS", "SourceListDelegate", "app_icon", "command_card", "draw_glyph",
           "glyph_icon", "mark_pixmap", "page_header", "page_layout"]

ICONS: Final = Path(__file__).resolve().parent.parent / "data" / "icons"
#: the window icon's sizes (make_icons.WINDOW_SIZES)
_SIZES: Final = (16, 32, 64, 128, 256, 512)
#: the item data role that names a source-list row's glyph (one of :data:`GLYPHS`)
GLYPH_ROLE: Final = int(Qt.ItemDataRole.UserRole) + 7


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


# ----------------------------------------------------------------------------------------------- the glyphs
def _viewer(p: QPainterPath) -> None:  # a small graph: three nodes and their edges
    for x, y in ((4.0, 4.5), (12.0, 4.5), (8.0, 12.0)):
        p.addEllipse(QPointF(x, y), 2.0, 2.0)
    for (x1, y1), (x2, y2) in (((6.0, 4.5), (10.0, 4.5)), ((5.0, 6.3), (7.0, 10.2)), ((11.0, 6.3), (9.0, 10.2))):
        p.moveTo(x1, y1)
        p.lineTo(x2, y2)


def _runs(p: QPainterPath) -> None:  # a play mark in a circle
    p.addEllipse(QPointF(8, 8), 6.5, 6.5)
    p.moveTo(6.5, 5.2)
    p.lineTo(11.0, 8.0)
    p.lineTo(6.5, 10.8)
    p.closeSubpath()


def _logs(p: QPainterPath) -> None:  # a page of lines
    p.addRoundedRect(QRectF(2.5, 1.8, 11, 12.4), 2, 2)
    for y, end in ((5.5, 11.0), (8.0, 11.0), (10.5, 8.5)):
        p.moveTo(5.0, y)
        p.lineTo(end, y)


def _system(p: QPainterPath) -> None:  # a gauge
    p.arcMoveTo(QRectF(1.5, 3.0, 13, 13), 200)
    p.arcTo(QRectF(1.5, 3.0, 13, 13), 200, -220)
    p.moveTo(8.0, 9.5)
    p.lineTo(11.0, 6.0)
    p.addEllipse(QPointF(8.0, 9.5), 0.9, 0.9)


def _licences(p: QPainterPath) -> None:  # a seal with its ribbon
    p.addEllipse(QPointF(8, 6.5), 4.5, 4.5)
    p.moveTo(5.8, 10.5)
    p.lineTo(4.8, 14.5)
    p.lineTo(8.0, 13.0)
    p.lineTo(11.2, 14.5)
    p.lineTo(10.2, 10.5)


def _package(p: QPainterPath) -> None:  # a box
    p.moveTo(8, 1.8)
    for x, y in ((14, 4.8), (14, 11.2), (8, 14.2), (2, 11.2), (2, 4.8)):
        p.lineTo(x, y)
    p.closeSubpath()
    p.moveTo(2, 4.8)
    p.lineTo(8, 7.8)
    p.lineTo(14, 4.8)
    p.moveTo(8, 7.8)
    p.lineTo(8, 14.2)


def _docs(p: QPainterPath) -> None:  # an open book
    p.moveTo(8, 4)
    p.cubicTo(6, 2.6, 4, 2.6, 1.8, 3.2)
    p.lineTo(1.8, 13)
    p.cubicTo(4, 12.4, 6, 12.4, 8, 13.8)
    p.cubicTo(10, 12.4, 12, 12.4, 14.2, 13)
    p.lineTo(14.2, 3.2)
    p.cubicTo(12, 2.6, 10, 2.6, 8, 4)
    p.lineTo(8, 13.8)


def _assistant(p: QPainterPath) -> None:  # a speech bubble
    p.addRoundedRect(QRectF(1.8, 2.5, 12.4, 8.8), 3, 3)
    p.moveTo(5.0, 11.3)
    p.lineTo(4.4, 14.2)
    p.lineTo(8.2, 11.3)


def _sidebar(p: QPainterPath) -> None:  # a window with its sidebar
    p.addRoundedRect(QRectF(1.8, 2.8, 12.4, 10.4), 2, 2)
    p.moveTo(6, 2.8)
    p.lineTo(6, 13.2)


def _open(p: QPainterPath) -> None:  # a folder
    p.moveTo(1.8, 4)
    p.lineTo(6, 4)
    p.lineTo(7.5, 5.6)
    p.lineTo(14.2, 5.6)
    p.lineTo(14.2, 13)
    p.lineTo(1.8, 13)
    p.closeSubpath()


def _reload(p: QPainterPath) -> None:  # a circular arrow
    rect = QRectF(2.5, 2.5, 11, 11)
    p.arcMoveTo(rect, 60)
    p.arcTo(rect, 60, 300)
    tip = QPointF(8 + 5.5 * math.cos(math.radians(60)), 8 - 5.5 * math.sin(math.radians(60)))
    p.moveTo(tip.x() - 3.2, tip.y() - 1.2)
    p.lineTo(tip)
    p.lineTo(tip.x() - 1.0, tip.y() + 3.2)


def _new(p: QPainterPath) -> None:  # a plus
    p.moveTo(8, 2.5)
    p.lineTo(8, 13.5)
    p.moveTo(2.5, 8)
    p.lineTo(13.5, 8)


def _devrun(p: QPainterPath) -> None:  # a flask
    p.moveTo(5.5, 2)
    p.lineTo(10.5, 2)
    p.moveTo(6.6, 2)
    p.lineTo(6.6, 6.5)
    p.lineTo(2.4, 13.6)
    p.lineTo(13.6, 13.6)
    p.lineTo(9.4, 6.5)
    p.lineTo(9.4, 2)
    p.moveTo(4.4, 10.2)
    p.lineTo(11.6, 10.2)


#: the glyphs by name: the sidebar's pages and the Qt toolbar's actions (a 16-unit box, drawn as strokes)
GLYPHS: Final = {
    "Viewer": _viewer, "Runs": _runs, "Logs": _logs, "System": _system, "Licences": _licences, "Package": _package,
    "Docs": _docs, "Assistant": _assistant, "toggleSidebar": _sidebar, "openCorpus": _open, "reload": _reload,
    "newJob": _new, "devRun": _devrun,
}  # fmt: skip


def draw_glyph(painter: QPainter, name: str, rect: QRectF, colour: QColor, *, width: float = 1.3) -> None:
    """Stroke the glyph ``name`` into ``rect`` (square) in ``colour``; an unknown name draws nothing."""
    build = GLYPHS.get(name)
    if build is None:
        return
    path = QPainterPath()
    build(path)
    scale = min(rect.width(), rect.height()) / 16.0
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.translate(rect.topLeft())
    painter.scale(scale, scale)
    pen = QPen(colour, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(path)
    painter.restore()


def glyph_icon(name: str, colour: QColor, size: int = 16, ratio: float = 2.0) -> QIcon:
    """The glyph ``name`` as an icon of ``size`` points in ``colour`` (drawn at ``ratio`` for Retina screens)."""
    pixmap = QPixmap(int(size * ratio), int(size * ratio))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    draw_glyph(painter, name, QRectF(0, 0, size, size), colour)
    painter.end()
    return QIcon(pixmap)


# ----------------------------------------------------------------------------------------------- the source list
class SourceListDelegate(QStyledItemDelegate):
    """Draws a list as a source list: a row that cannot be selected is a section heading (small capitals, grey); any
    other row is a page, with its glyph (:data:`GLYPH_ROLE`), its text and a rounded selection in the accent colour
    while the list has the focus, else in the neutral pressed colour. Text is drawn as plain text."""

    ROW: Final = 28
    SECTION: Final = 30

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> QSize:
        base = super().sizeHint(option, index)
        if self._section(index):
            return QSize(base.width(), self.SECTION if index.row() else self.SECTION - 8)
        return QSize(base.width(), max(self.ROW, base.height()))

    @staticmethod
    def _section(index: QModelIndex | QPersistentModelIndex) -> bool:
        return not bool(index.flags() & Qt.ItemFlag.ItemIsSelectable)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> None:
        t = theme.tokens()
        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        rect = QRectF(option.rect)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._section(index):
            painter.setFont(theme.scaled_font("heading", option.font))
            painter.setPen(QColor(t.caption))
            painter.drawText(rect.adjusted(16, 0, -8, -5), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom),
                             text)
            painter.restore()
            return
        state = option.state
        view = option.widget
        focused = isinstance(view, QAbstractItemView) and view.hasFocus() and view.isActiveWindow()
        selected = bool(state & QStyle.StateFlag.State_Selected)
        box = rect.adjusted(8, 1, -8, -1)
        if selected:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(t.accent if focused else t.pressed))
            painter.drawRoundedRect(box, 6, 6)
        elif state & QStyle.StateFlag.State_MouseOver:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(t.hover))
            painter.drawRoundedRect(box, 6, 6)
        on_accent = selected and focused
        enabled = bool(state & QStyle.StateFlag.State_Enabled)
        ink = QColor(t.accent_text if on_accent else (t.text if enabled else t.disabled))
        x = box.left() + 10
        glyph = index.data(GLYPH_ROLE)
        if isinstance(glyph, str) and glyph in GLYPHS:
            size = 16.0
            draw_glyph(painter, glyph, QRectF(x, box.center().y() - size / 2, size, size),
                       QColor(t.accent_text if on_accent else t.accent))
            x += size + 9
        painter.setFont(option.font)
        painter.setPen(ink)
        area = QRectF(x, box.top(), box.right() - x - 6, box.height())
        elided = painter.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, int(area.width()))
        painter.drawText(area, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), elided)
        painter.restore()


# ----------------------------------------------------------------------------------------------- read-only pages
def page_header(parent: QWidget, title: str, *, caption_text: str = "",
                caption_name: str | None = None) -> tuple[QWidget, QHBoxLayout, SafeLabel]:
    """A page's header: the page title (20 px, semibold) on a row the caller can add badges and buttons to, and a grey
    caption under it (hidden while empty). Returns ``(header, title row, caption)``."""
    header = QWidget(parent)
    header.setAccessibleName(f"{title} header")
    head = QVBoxLayout(header)
    head.setContentsMargins(0, 0, 0, 0)
    head.setSpacing(2)
    row = QHBoxLayout()
    row.setSpacing(theme.SPACE)
    label = SafeLabel(title, name=f"{title} page title", parent=header, selectable=False)
    label.setFont(theme.scaled_font("title"))
    row.addWidget(label)
    row.addStretch(1)
    head.addLayout(row)
    note = caption(caption_text, name=caption_name or f"{title}: note", parent=header)
    note.setVisible(bool(caption_text))
    head.addWidget(note)
    return header, row, note


def page_layout(page: QWidget, title: str, *, caption_text: str = "",
                caption_name: str | None = None) -> tuple[QVBoxLayout, QHBoxLayout, SafeLabel]:
    """Lay out a read-only page in the house style: the page background, the style's margins and
    :func:`page_header`. Returns ``(page layout, title row, caption)``."""
    page.setProperty("apvRole", "page")
    page.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    lay = QVBoxLayout(page)
    lay.setContentsMargins(3 * theme.SPACE, 20, 3 * theme.SPACE, 2 * theme.SPACE)
    lay.setSpacing(14)
    header, row, note = page_header(page, title, caption_text=caption_text, caption_name=caption_name)
    lay.addWidget(header)
    return lay, row, note


def command_card(parent: QWidget, *, name: str = "Terminal command") -> CommandCard:
    """A :class:`forms.CommandCard` for a page whose width changes (a stretching column, not a fixed panel); the card
    itself wraps its commands again whenever its text's width changes."""
    return CommandCard(name=name, parent=parent)
