"""The PROV graph scene: built-in Qt items over a computed layout (design §7.1 step 6, §7.3; D-397, D-444).

* One item per node (``QGraphicsEllipseItem`` for entities, ``QGraphicsRectItem`` for activities, a polygon "house" for
  agents) and one ``QGraphicsPathItem`` per edge, plus arrowheads; no Python ``paint()`` overrides, so painting stays in
  C++. Labels are ``QGraphicsSimpleTextItem`` (never interprets markup) holding the trusted-grammar label lines only.
* Level of detail by the view scale, switched only at tier changes by toggling the visibility of a few layer items:
  < 0.15 → the overview raster (one pixmap, painted from the layout data in a worker thread, no text);
  0.15–0.5 → shapes only; 0.5–1.2 → one-line labels (the local id); ≥ 1.2 → full labels and edge labels.
* The BSP index is used (depth capped at 10) and ``sceneRect`` is set explicitly.
* Overlay edges (inference relations between placed nodes) belong to their bundle's layer, so the bundle toggles change
  visibility only and never re-lay out. Folded elements show as a badge with a count.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Final

from agentprov.render import style
from PySide6.QtCore import QObject, QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsPixmapItem,
    QGraphicsPolygonItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QStyleOptionGraphicsItem,
    QWidget,
)

from agentprov_gui import text as T
from agentprov_gui.graph.dotjson import Layout
from agentprov_gui.graph.viewgraph import VEdge, ViewGraph
from agentprov_gui.ui.theme import ACCESS, GraphPalette

__all__ = ["LOD_FULL", "LOD_RASTER", "LOD_SHAPES", "GraphScene", "lod_tier"]

LOD_RASTER: Final = 0
LOD_SHAPES: Final = 1
LOD_SHORT: Final = 2
LOD_FULL: Final = 3
EDGE_LABEL_LIMIT: Final = 4000
BSP_DEPTH: Final = 10
_DASH: Final = {"O": Qt.PenStyle.SolidLine, "D": Qt.PenStyle.DashLine, "I": Qt.PenStyle.DotLine, None: Qt.PenStyle.SolidLine}
_NODE_WIDTH: Final = {"O": 2.0, "D": 1.2, "I": 1.6, None: 0.6}
_EDGE_WIDTH: Final = {"O": 1.8, "D": 1.1, "I": 1.5, None: 0.6}
NODE_KEY: Final = 0  # QGraphicsItem.data key holding the node key


def lod_tier(scale: float, n_nodes: int) -> int:
    if scale < 0.15 and n_nodes > 200:
        return LOD_RASTER
    if scale < 0.5:
        return LOD_SHAPES
    if scale < 1.2:
        return LOD_SHORT
    return LOD_FULL


def _layer(scene: QGraphicsScene, z: float) -> QGraphicsRectItem:
    item = QGraphicsRectItem()
    item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemHasNoContents, True)
    item.setZValue(z)
    scene.addItem(item)
    return item


def _house(w: float, h: float) -> QPolygonF:
    return QPolygonF([
        QPointF(-w / 2, -h / 6), QPointF(0, -h / 2), QPointF(w / 2, -h / 6), QPointF(w / 2, h / 2), QPointF(-w / 2, h / 2),
    ])  # fmt: skip


def _path(points: tuple[tuple[float, float], ...]) -> QPainterPath:
    path = QPainterPath()
    if not points:
        return path
    path.moveTo(*points[0])
    rest = points[1:]
    if len(rest) >= 3 and len(rest) % 3 == 0:
        for i in range(0, len(rest), 3):
            path.cubicTo(QPointF(*rest[i]), QPointF(*rest[i + 1]), QPointF(*rest[i + 2]))
    else:
        for p in rest:
            path.lineTo(*p)
    return path


def clip_segment(x0: float, y0: float, x1: float, y1: float, rect: QRectF) -> tuple[float, float] | None:
    """Liang–Barsky: the parameter interval ``(t0, t1)`` of the segment inside ``rect``, or ``None``."""
    dx, dy = x1 - x0, y1 - y0
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x0 - rect.left()), (dx, rect.right() - x0), (-dy, y0 - rect.top()), (dy, rect.bottom() - y0)):
        if p == 0:
            if q < 0:
                return None
            continue
        t = q / p
        if p < 0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
        if t0 > t1:
            return None
    return t0, t1


class ClippedLineItem(QGraphicsLineItem):
    """A straight edge that strokes only its visible part.

    Qt dashes a whole path before clipping it, so the long dashed and dotted edges of a large layered layout cost
    0.8 s per frame (measured: 0.13 s with solid pens). This item clips the line to the exposed rectangle first and
    offsets the dash pattern by the clipped length, so the pattern stays put while panning. It draws exactly what
    ``QGraphicsLineItem`` would draw; only the invisible part is skipped.
    """

    def __init__(self, x0: float, y0: float, x1: float, y1: float, parent: QGraphicsItem | None = None) -> None:
        super().__init__(x0, y0, x1, y1, parent)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemUsesExtendedStyleOption, True)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget | None = None) -> None:
        line = self.line()
        exposed = option.exposedRect.adjusted(-4, -4, 4, 4)
        span = clip_segment(line.x1(), line.y1(), line.x2(), line.y2(), exposed)
        if span is None:
            return
        t0, t1 = span
        pen = QPen(self.pen())
        scene = self.scene()
        if isinstance(scene, GraphScene) and scene.coarse:
            pen.setStyle(Qt.PenStyle.SolidLine)  # LOD 0.15–0.5: no dash patterns (design §7.3)
        elif pen.style() != Qt.PenStyle.SolidLine and t0 > 0:
            scale = painter.worldTransform().m11() if pen.isCosmetic() else 1.0
            width = max(pen.widthF(), 1.0)
            pen.setDashOffset(pen.dashOffset() + t0 * line.length() * scale / width)
        painter.setPen(pen)
        dx, dy = line.x2() - line.x1(), line.y2() - line.y1()
        painter.drawLine(QPointF(line.x1() + dx * t0, line.y1() + dy * t0), QPointF(line.x1() + dx * t1, line.y1() + dy * t1))


def _arrow(tip: QPointF, before: QPointF, size: float = 7.0) -> QPolygonF:
    angle = math.atan2(tip.y() - before.y(), tip.x() - before.x())
    left = QPointF(tip.x() - size * math.cos(angle - 0.4), tip.y() - size * math.sin(angle - 0.4))
    right = QPointF(tip.x() - size * math.cos(angle + 0.4), tip.y() - size * math.sin(angle + 0.4))
    return QPolygonF([tip, left, right])


@dataclass(slots=True)
class NodeItems:
    shape: QGraphicsRectItem | QGraphicsPolygonItem | QGraphicsEllipseItem
    short: QGraphicsSimpleTextItem
    full: QGraphicsSimpleTextItem
    badge: QGraphicsItem | None
    base_pen: QPen
    fill_plain: QColor
    fill_overlay: QColor
    edges: list[int] = field(default_factory=list)


@dataclass(slots=True)
class EdgeItems:
    edge: VEdge
    path: QGraphicsPathItem | ClippedLineItem
    head: QGraphicsPolygonItem
    label: QGraphicsSimpleTextItem | None
    base_pen: QPen


class GraphScene(QGraphicsScene):
    """Scene for one :class:`ViewGraph` and its :class:`Layout`."""

    def __init__(self, view: ViewGraph, layout: Layout, palette: GraphPalette, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.view, self.layout, self.gpal = view, layout, palette
        self.setItemIndexMethod(QGraphicsScene.ItemIndexMethod.BspTreeIndex)
        # Qt's automatic depth (15 for the largest all-bundle layout) puts each long edge's bounding rect into thousands
        # of leaves: +315 MiB measured. Depth 10 costs +26 MiB with the same paint and hit-test times.
        self.setBspTreeDepth(BSP_DEPTH)
        self.setBackgroundBrush(QBrush(QColor(palette.canvas)))
        margin = 40.0
        self.setSceneRect(QRectF(-margin, -margin, layout.width + 2 * margin, layout.height + 2 * margin))
        self.nodes: dict[str, NodeItems] = {}
        self.edges: list[EdgeItems] = []
        self.layers = {
            "edges.core": _layer(self, 1), "edges.inference": _layer(self, 2), "edges.assessment": _layer(self, 2),
            "nodes": _layer(self, 3), "labels.short": _layer(self, 4), "labels.full": _layer(self, 4),
            "labels.edges": _layer(self, 4), "badges": _layer(self, 5), "heads": _layer(self, 2),
        }  # fmt: skip
        self.raster: QGraphicsPixmapItem | None = None
        self.coarse = False
        self.tier = -1
        self.assessment_shown = False
        self._selected: str | None = None
        self._bundles: dict[str, bool] = {}
        self._build()

    # ------------------------------------------------------------------------------------------ build
    def _build(self) -> None:
        pal = self.gpal
        small = QFont("Helvetica", 9)
        label_font = QFont("Helvetica", 10)
        text_brush = QBrush(QColor(pal.text_on_fill))
        border = {"activity": pal.activity_border, "entity": pal.entity_border, "agent": pal.agent_border}
        for vnode in self.view.nodes:
            box = self.layout.nodes.get(vnode.key)
            if box is None:
                continue
            cx, cy, w, h = box
            n = vnode.node
            plain = style.node_attrs(n.section, n.cls, n.kind)
            over = style.node_attrs(n.section, n.cls, n.kind, integrity=n.integrity, role=n.role)
            colour = border.get(n.section, pal.entity_border)
            if n.kind in ("inference", "assessment"):
                colour = pal.inference if n.kind == "inference" else pal.assessment
            elif n.kind is None:
                colour = pal.ghost
            extra = 1.0 if ACCESS["increase_contrast"] else 0.0  # Increase Contrast: 2-px strokes (macos-design §5)
            pen = QPen(QColor(colour), _NODE_WIDTH.get(n.cls, 0.6) + 0.4 + extra, _DASH.get(n.cls, Qt.PenStyle.SolidLine))
            if n.kind is None:
                pen.setStyle(Qt.PenStyle.DashLine)
            pen.setCosmetic(False)
            fill_plain = QColor("#F2F2F2" if n.kind is None else plain["fillcolor"])
            fill_overlay = QColor(over["fillcolor"])
            shape: QGraphicsRectItem | QGraphicsPolygonItem | QGraphicsEllipseItem
            if n.section == "activity":
                shape = QGraphicsRectItem(QRectF(-w / 2, -h / 2, w, h), self.layers["nodes"])
            elif n.section == "agent":
                shape = QGraphicsPolygonItem(_house(w, h), self.layers["nodes"])
            else:
                shape = QGraphicsEllipseItem(QRectF(-w / 2, -h / 2, w, h), self.layers["nodes"])
            shape.setPos(cx, cy)
            shape.setPen(pen)
            shape.setBrush(QBrush(fill_plain))
            shape.setData(NODE_KEY, vnode.key)
            shape.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
            shape.setAcceptHoverEvents(True)
            short = QGraphicsSimpleTextItem(vnode.lines[0], self.layers["labels.short"])
            short.setFont(small)
            short.setBrush(text_brush)
            r = short.boundingRect()
            short.setPos(cx - r.width() / 2, cy - r.height() / 2)
            lines = list(vnode.lines)
            if ACCESS["differentiate"]:  # Differentiate Without Colour: bundle letters (C, I, A) in the label
                lines.append({"core": "[C]", "inference": "[I]", "assessment": "[A]"}.get(n.kind or "", "[outside]"))
            full = QGraphicsSimpleTextItem("\n".join(lines), self.layers["labels.full"])
            full.setFont(label_font)
            full.setBrush(text_brush)
            r = full.boundingRect()
            full.setPos(cx - r.width() / 2, cy - r.height() / 2)
            badge = None
            if vnode.folded:
                badge = self._badge(len(vnode.folded), cx + w / 2, cy - h / 2, vnode.key)
            self.nodes[vnode.key] = NodeItems(shape, short, full, badge, pen, fill_plain, fill_overlay)
        laid = {(s, d): pts for s, d, pts in self.layout.edges}
        for edge in self.view.edges:
            if edge.src not in self.nodes or edge.dst not in self.nodes:
                continue
            pts = laid.get((edge.src, edge.dst)) if not edge.overlay else None
            if pts is None:
                pts = self._straight(edge.src, edge.dst)
            self._edge(edge, pts, small)

    def _straight(self, src: str, dst: str) -> tuple[tuple[float, float], ...]:
        sx, sy, sw, sh = self.layout.nodes[src]
        dx, dy, dw, dh = self.layout.nodes[dst]
        ang = math.atan2(dy - sy, dx - sx)

        def rim(cx: float, cy: float, w: float, h: float, a: float) -> tuple[float, float]:
            return (cx + math.cos(a) * w / 2, cy + math.sin(a) * h / 2)

        return (rim(sx, sy, sw, sh, ang), rim(dx, dy, dw, dh, ang + math.pi))

    def _badge(self, count: int, x: float, y: float, key: str) -> QGraphicsItem:
        rect = QGraphicsRectItem(QRectF(-12, -8, 24, 16), self.layers["badges"])
        rect.setPos(x, y)
        rect.setBrush(QBrush(QColor(self.gpal.assessment)))
        rect.setPen(QPen(Qt.PenStyle.NoPen))
        rect.setData(NODE_KEY, key)
        label = QGraphicsSimpleTextItem(f"+{count}" if count < 1000 else "+999", rect)
        label.setFont(QFont("Helvetica", 8))
        label.setBrush(QBrush(QColor("#FFFFFF")))
        r = label.boundingRect()
        label.setPos(-r.width() / 2, -r.height() / 2)
        return rect

    def _edge(self, edge: VEdge, pts: tuple[tuple[float, float], ...], font: QFont) -> None:
        pal = self.gpal
        layer = self.layers[f"edges.{edge.kind}"] if f"edges.{edge.kind}" in self.layers else self.layers["edges.core"]
        if edge.link:
            colour, dash, width = "#808080", Qt.PenStyle.DashLine, 0.8
        else:
            colour = pal.relation(edge.relation, edge.kind)
            dash, width = _DASH.get(edge.cls, Qt.PenStyle.SolidLine), _EDGE_WIDTH.get(edge.cls, 0.6)
        pen = QPen(QColor(colour), width + 0.3 + (0.8 if ACCESS["increase_contrast"] else 0.0), dash)
        pen.setCosmetic(True)
        path: QGraphicsPathItem | ClippedLineItem
        if len(pts) == 2:
            path = ClippedLineItem(pts[0][0], pts[0][1], pts[1][0], pts[1][1], layer)
        else:
            path = QGraphicsPathItem(_path(pts), layer)
        path.setPen(pen)
        head = QGraphicsPolygonItem(
            _arrow(QPointF(*pts[-1]), QPointF(*pts[-2]) if len(pts) > 1 else QPointF(*pts[-1])), self.layers["heads"]
        )
        head.setBrush(QBrush(QColor(colour)))
        head.setPen(QPen(Qt.PenStyle.NoPen))
        label = None
        if len(self.edges) < EDGE_LABEL_LIMIT:
            mid = _path(pts).pointAtPercent(0.5)
            label = QGraphicsSimpleTextItem(T.line(edge.relation, 40), self.layers["labels.edges"])
            label.setFont(font)
            label.setBrush(QBrush(QColor(colour)))
            label.setPos(mid.x() + 2, mid.y() - 12)
        index = len(self.edges)
        self.edges.append(EdgeItems(edge, path, head, label, pen))
        self.nodes[edge.src].edges.append(index)
        self.nodes[edge.dst].edges.append(index)

    # ------------------------------------------------------------------------------------------ state
    def set_tier(self, tier: int) -> None:
        if tier == self.tier:
            return
        self.tier = tier
        self.coarse = tier <= LOD_SHAPES
        raster = tier == LOD_RASTER and self.raster is not None
        self.layers["heads"].setVisible(not raster and tier >= LOD_SHORT)
        for name, layer in self.layers.items():
            if name.startswith("labels.short"):
                layer.setVisible(tier == LOD_SHORT)
            elif name.startswith("labels.full") or name == "labels.edges":
                layer.setVisible(tier == LOD_FULL)
            elif name.startswith("edges.") or name in ("nodes", "badges"):  # "heads" is set above
                layer.setVisible(not raster and self._bundle_visible(name))
        if self.raster is not None:
            self.raster.setVisible(raster)

    def _bundle_visible(self, layer: str) -> bool:
        if layer == "edges.inference":
            return self._bundles.get("inference", True)
        if layer in ("edges.assessment", "badges"):
            return self._bundles.get("assessment", True)
        return True

    def set_bundles(self, *, inference: bool, assessment: bool) -> None:
        self._bundles = {"inference": inference, "assessment": assessment}
        if self.tier != LOD_RASTER or self.raster is None:
            self.layers["edges.inference"].setVisible(inference)
            self.layers["edges.assessment"].setVisible(assessment)
            self.layers["badges"].setVisible(assessment)
        if assessment != self.assessment_shown:
            self.assessment_shown = assessment
            for items in self.nodes.values():
                items.shape.setBrush(QBrush(items.fill_overlay if assessment else items.fill_plain))

    def set_raster(self, image: QImage) -> None:
        if self.raster is None:
            self.raster = QGraphicsPixmapItem()
            self.raster.setZValue(0)
            self.raster.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
            self.addItem(self.raster)
        self.raster.setPixmap(QPixmap.fromImage(image))
        scale = self.layout.width / max(image.width(), 1)
        self.raster.setScale(scale)
        self.raster.setPos(0, 0)
        self.raster.setVisible(self.tier == LOD_RASTER)
        if self.tier == LOD_RASTER:
            self.tier = -1
            self.set_tier(LOD_RASTER)

    def node_at(self, item: QGraphicsItem | None) -> str | None:
        while item is not None:
            key = item.data(NODE_KEY)
            if isinstance(key, str):
                return key
            item = item.parentItem()
        return None

    def select(self, key: str | None) -> None:
        if self._selected is not None and self._selected in self.nodes:
            items = self.nodes[self._selected]
            items.shape.setPen(items.base_pen)
            for i in items.edges:
                self.edges[i].path.setPen(self.edges[i].base_pen)
        self._selected = key
        if key is not None and key in self.nodes:
            items = self.nodes[key]
            pen = QPen(QColor(self.gpal.selection), items.base_pen.widthF() * 2 + 2.0)
            items.shape.setPen(pen)
            for i in items.edges:
                e = self.edges[i]
                thick = QPen(e.base_pen)
                thick.setWidthF(e.base_pen.widthF() * 2.2 + 0.5)
                e.path.setPen(thick)

    def dim(self, keep: set[str] | None) -> None:
        """Dim every node and edge outside ``keep`` (``None``: undim all)."""
        for key, items in self.nodes.items():
            o = 1.0 if keep is None or key in keep else 0.15
            items.shape.setOpacity(o)
            items.short.setOpacity(o)
            items.full.setOpacity(o)
        for e in self.edges:
            o = 1.0 if keep is None or (e.edge.src in keep and e.edge.dst in keep) else 0.1
            e.path.setOpacity(o)
            e.head.setOpacity(o)
            if e.label is not None:
                e.label.setOpacity(o)

    def neighbourhood(self, key: str, hops: int) -> set[str]:
        adj: dict[str, set[str]] = {}
        for e in self.edges:
            adj.setdefault(e.edge.src, set()).add(e.edge.dst)
            adj.setdefault(e.edge.dst, set()).add(e.edge.src)
        seen = {key}
        frontier = {key}
        for _ in range(hops):
            frontier = {m for k in frontier for m in adj.get(k, ())} - seen
            seen |= frontier
        return seen

    def keys(self) -> Iterable[str]:
        return self.nodes.keys()


def paint_raster(layout: Layout, sections: dict[str, str], fills: dict[str, str], canvas: str, edge_colour: str,
                 max_px: int = 2048) -> QImage:
    """The overview raster, painted from the layout data only (no scene access, no text); safe in a worker thread."""
    scale = min(1.0, max_px / max(layout.width, layout.height, 1.0))
    image = QImage(max(1, int(layout.width * scale)), max(1, int(layout.height * scale)), QImage.Format.Format_RGB32)
    image.fill(QColor(canvas))
    painter = QPainter(image)
    painter.scale(scale, scale)
    painter.setPen(QPen(QColor(edge_colour), 0))
    for _, _, pts in layout.edges:
        if len(pts) >= 2:
            painter.drawLine(QPointF(*pts[0]), QPointF(*pts[-1]))
    painter.setPen(Qt.PenStyle.NoPen)
    for key, (cx, cy, w, h) in layout.nodes.items():
        painter.setBrush(QColor(fills.get(key, "#FFFC87")))
        rect = QRectF(cx - w / 2, cy - h / 2, w, h)
        if sections.get(key) == "entity":
            painter.drawEllipse(rect)
        else:
            painter.drawRect(rect)
    painter.end()
    return image
