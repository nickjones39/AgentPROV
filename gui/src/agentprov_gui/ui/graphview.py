"""The Graph tab (design §7.2; wireframe 02; macos-design §5; D-397, D-444, D-446).

Toolbar: zoom −/+, 100 %, Fit; bundle toggles (core always; inference and assessment as overlays); evidence filter;
layout (overlay: ``dot`` core + overlays, or full: layered, with "collapse mentions"); search with k-hop Focus.
Hover a node for 400 ms: a plain-text popover with its attributes (data values hidden as ``‹text, n chars, sha256›``
until Show content, then fenced as data with their locator). Click selects and pins it to the inspector table; Esc clears. The Elements list (id, section,
bundle, class, degree) is the accessible view of the graph, synchronised with the selection.

Model building and layout run in a worker thread; the scene is built on the UI thread from immutable results.
"""

from __future__ import annotations

from functools import partial
from pathlib import Path
from typing import Any, Final

from agentprov.render import style
from agentprov.render.graph import DrawNode, GraphModel, build_model
from PySide6.QtCore import (
    QAbstractTableModel,
    QEvent,
    QModelIndex,
    QPersistentModelIndex,
    QPoint,
    Qt,
    QThreadPool,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QGuiApplication,
    QHideEvent,
    QImage,
    QKeySequence,
    QMouseEvent,
    QNativeGestureEvent,
    QPainter,
    QShortcut,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFrame,
    QGraphicsView,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from agentprov_gui import text as T
from agentprov_gui.graph.layout import LayoutResult, compute_layout
from agentprov_gui.graph.scene import LOD_RASTER, GraphScene, lod_tier, paint_raster
from agentprov_gui.graph.viewgraph import ViewGraph, attribute_rows, full_view, overlay_view
from agentprov_gui.ui import theme
from agentprov_gui.ui.safe import ReadOnlyText, SafeLabel, is_tooltip_role, safe_tooltip, set_tooltip
from agentprov_gui.ui.worker import submit

__all__ = ["GraphTab", "GraphView"]

MIN_SCALE: Final = 0.05
MAX_SCALE: Final = 8.0
HOVER_MS: Final = 400


# ----------------------------------------------------------------------------------------------- worker
def graph_work(doc: Any, ex: str, *, full: bool, collapse: bool, cache_dir: Path | None,
               model: GraphModel | None) -> tuple[GraphModel, ViewGraph, LayoutResult]:
    """``build_model`` (validates first) → view → layout; runs off the UI thread."""
    model = model or build_model(doc, ex=ex, mode="all")
    view = full_view(model, collapse_mentions=collapse) if full else overlay_view(model)
    return model, view, compute_layout(view, engine="layered" if full else "auto", cache_dir=cache_dir)


# ----------------------------------------------------------------------------------------------- the view
class GraphView(QGraphicsView):
    """Pan (drag the background), zoom (wheel with ⌘/Ctrl or ⌥, pinch, keys), hover and click."""

    hovered = Signal(str, QPoint)  # node key, global position
    hover_ended = Signal()  # the cursor moved off its node or out of the view
    clicked = Signal(str)
    scale_changed = Signal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAccessibleName("PROV graph canvas")
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.MinimalViewportUpdate)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.setInterval(HOVER_MS)
        self._hover_timer.timeout.connect(self._hover_fire)
        self._hover_key: str | None = None
        self._hover_pos = QPoint()
        self.viewport().grabGesture(Qt.GestureType.PinchGesture)

    def graph_scene(self) -> GraphScene | None:
        scene = self.scene()
        return scene if isinstance(scene, GraphScene) else None

    def current_scale(self) -> float:
        return float(self.transform().m11())

    def zoom_by(self, factor: float) -> None:
        current = self.current_scale()
        target = min(MAX_SCALE, max(MIN_SCALE, current * factor))
        if target != current:
            self.scale(target / current, target / current)
            self._scale_moved()

    def set_zoom(self, value: float) -> None:
        self.resetTransform()
        self.scale(value, value)
        self._scale_moved()

    def fit(self) -> None:
        scene = self.scene()
        if scene is not None:
            self.fitInView(scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
            if self.current_scale() > 1.5:
                self.set_zoom(1.5)
            self._scale_moved()

    def refresh_lod(self) -> None:
        self._scale_moved()

    def _scale_moved(self) -> None:
        scene = self.graph_scene()
        s = self.current_scale()
        if scene is not None:
            tier = lod_tier(s, len(scene.nodes))
            if tier == LOD_RASTER and scene.raster is None:
                tier = 1
            scene.set_tier(tier)
            self.setRenderHint(QPainter.RenderHint.Antialiasing, tier >= 2)
        self.scale_changed.emit(s)

    def wheelEvent(self, event: QWheelEvent) -> None:
        mods = event.modifiers()
        if mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.MetaModifier):
            delta = event.angleDelta().y() or event.pixelDelta().y()
            if delta:
                self.zoom_by(1.0015 ** delta)
            event.accept()
            return
        super().wheelEvent(event)

    def viewportEvent(self, event: QEvent) -> bool:
        if isinstance(event, QNativeGestureEvent):
            if event.gestureType() == Qt.NativeGestureType.ZoomNativeGesture:
                self.zoom_by(1.0 + event.value())
                return True
            if event.gestureType() == Qt.NativeGestureType.SmartZoomNativeGesture:
                if abs(self.current_scale() - 1.0) < 0.01:
                    self.fit()
                else:
                    self.set_zoom(1.0)
                return True
        return super().viewportEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        super().mouseMoveEvent(event)
        scene = self.graph_scene()
        key = scene.node_at(self.itemAt(event.position().toPoint())) if scene is not None else None
        if key != self._hover_key:
            self._hover_key = key
            self._hover_timer.stop()
            self.hover_ended.emit()
            if key is not None:
                self._hover_pos = event.globalPosition().toPoint()
                self._hover_timer.start()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        moved = (event.position().toPoint() - self._press).manhattanLength() > 4 if hasattr(self, "_press") else False
        super().mouseReleaseEvent(event)
        if moved or event.button() != Qt.MouseButton.LeftButton:
            return
        scene = self.graph_scene()
        key = scene.node_at(self.itemAt(event.position().toPoint())) if scene is not None else None
        self.clicked.emit(key or "")

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self._press = event.position().toPoint()
        super().mousePressEvent(event)

    def _hover_fire(self) -> None:
        if self._hover_key is not None:
            self.hovered.emit(self._hover_key, self._hover_pos)

    def leaveEvent(self, event: QEvent) -> None:
        self._hover_timer.stop()
        self._hover_key = None
        self.hover_ended.emit()
        super().leaveEvent(event)


# ----------------------------------------------------------------------------------------------- popover
def attribute_text(value: Any, show_content: bool, limit: int, locator: str) -> str:
    """Metadata as one line; content as a placeholder, or fenced with ``locator`` when shown (S2), so a table's own
    Copy keeps the fence (S13)."""
    plain = T.plain_value(value)
    if not T.is_content_value(value):
        return T.line(plain, limit)
    if not show_content:
        return T.content_digest_label(plain)
    return T.fenced(plain, locator, limit)


def node_facts(node: DrawNode, bundle_titles: dict[int, str], show_content: bool, limit: int,
               locator: str) -> list[tuple[str, str]]:
    """The popover/inspector rows of ``node``; ``locator`` names the PROV document its shown content comes from."""
    rows = [
        ("id", T.line(node.key)),
        ("section", node.section),
        ("bundle", bundle_titles.get(node.bundle, "outside the drawn bundles") if node.bundle is not None
         else "outside the drawn bundles"),
        ("evidence class", node.cls or "—"),
    ]  # fmt: skip
    if node.integrity:
        rows.append(("integrity (assessment)", node.integrity))
    if node.role:
        rows.append(("role (assessment)", node.role))
    rows += [(T.line(k, 80), attribute_text(v, show_content, limit, f"{locator}#{node.key}/{k}"))
             for k, v in attribute_rows(node)]
    return rows


class Popover(QFrame):
    """A frameless plain-text attribute table shown near the cursor (not a QToolTip, which is rich text)."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setAccessibleName("Element popover")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        self.table = QTableWidget(0, 2, self)
        self.table.setAccessibleName("Element attributes")
        self.table.horizontalHeader().setVisible(False)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)
        self.resize(520, 260)

    def show_rows(self, rows: list[tuple[str, str]], at: QPoint) -> None:
        fill_table(self.table, rows)
        self.table.resizeRowsToContents()
        self.move(at + QPoint(14, 14))
        self.show()
        self.raise_()


def fill_table(table: QTableWidget, rows: list[tuple[str, str]]) -> None:
    table.setRowCount(len(rows))
    for i, (k, v) in enumerate(rows):
        for j, s in enumerate((k, v)):
            item = QTableWidgetItem(s)  # DisplayRole text is drawn as plain text
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            table.setItem(i, j, item)


# ----------------------------------------------------------------------------------------------- elements list
class ElementsModel(QAbstractTableModel):
    HEADERS: Final = ("id", "section", "bundle", "class", "degree", "folded")

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[tuple[str, str, str, str, int, int]] = []

    def set_view(self, view: ViewGraph, scene: GraphScene) -> None:
        self.beginResetModel()
        self.rows = []
        for v in view.nodes:
            if v.key not in scene.nodes:
                continue
            self.rows.append((v.key, v.section, v.kind or "outside", v.cls or "—", len(scene.nodes[v.key].edges),
                              len(v.folded)))
        for key in view.unplaced:
            n = view.by_key[key]
            self.rows.append((key, n.section, (n.kind or "outside") + " (not placed)", n.cls or "—", 0, 0))
        self.endResetModel()

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self.HEADERS)

    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        value = self.rows[index.row()][index.column()]
        if role == Qt.ItemDataRole.DisplayRole:
            return T.line(value) if isinstance(value, str) else value
        if is_tooltip_role(role):
            return safe_tooltip(value)
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return None

    def row_of(self, key: str) -> int:
        for i, r in enumerate(self.rows):
            if r[0] == key:
                return i
        return -1


# ----------------------------------------------------------------------------------------------- the tab
class GraphTab(QWidget):
    """Toolbar + canvas + side panel (search results, Elements list, inspector, legend)."""

    open_in_prov = Signal(str)  # node key

    def __init__(self, cache_dir: Path | None, parent: QWidget | None = None, *,
                 content_limit: int = T.CONTENT_CHARS_DEFAULT, two_rows: bool = False) -> None:
        """``two_rows``: the toolbar takes two rows (beside the PROV-JSON pane in a Viewer tab, D-841)."""
        super().__init__(parent)
        self.setAccessibleName("Graph")
        self.two_rows = two_rows
        self.cache_dir = cache_dir
        self.pool = QThreadPool.globalInstance()
        self.doc: Any = None
        self.ex = ""
        self.locator = ""  # the PROV document's corpus path, for fencing shown content
        self.model: GraphModel | None = None
        self.view_graph: ViewGraph | None = None
        self.scene_: GraphScene | None = None
        self.result: LayoutResult | None = None
        self.show_content = False
        self.content_limit = content_limit  # the viewer's Settings limit (design §6.6)
        self.exact_palette = False  # Settings › Appearance: "W3C exact" instead of "Accessible"
        self._generation = 0
        self._selected: str | None = None
        self._build()

    # ------------------------------------------------------------------------------------------ widgets
    def _button(self, text: str, name: str, slot: Any, tip: str) -> QPushButton:
        b = QPushButton(text, self)
        b.setAccessibleName(name)
        set_tooltip(b, tip)
        b.clicked.connect(slot)
        return b

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        bar = QHBoxLayout()
        self.view = GraphView(self)
        bar.addWidget(self._button("−", "Zoom out", lambda: self.view.zoom_by(1 / 1.25), "Zoom out (⌘−)"))
        bar.addWidget(self._button("+", "Zoom in", lambda: self.view.zoom_by(1.25), "Zoom in (⌘+)"))
        bar.addWidget(self._button("100 %", "Actual size", lambda: self.view.set_zoom(1.0), "Actual size (⌘0)"))
        bar.addWidget(self._button("Fit", "Fit to window", self.view.fit, "Fit (⌘9)"))
        bar.addSpacing(12)
        self.cb_core = QCheckBox("core", self)
        self.cb_core.setChecked(True)
        self.cb_core.setEnabled(False)
        self.cb_inf = QCheckBox("inference", self)
        self.cb_inf.setChecked(True)
        self.cb_assess = QCheckBox("assessment", self)
        self.cb_assess.setChecked(False)
        for cb in (self.cb_core, self.cb_inf, self.cb_assess):
            cb.setAccessibleName(f"Show {cb.text()} bundle")
            bar.addWidget(cb)
        self.cb_inf.toggled.connect(self._bundles_changed)
        self.cb_assess.toggled.connect(self._bundles_changed)
        bar.addSpacing(12)
        self.evidence = QComboBox(self)
        self.evidence.setAccessibleName("Evidence class filter")
        self.evidence.addItems(["evidence: all", "only Observed", "only Derived", "only Inferred"])
        self.evidence.currentIndexChanged.connect(self._evidence_changed)
        bar.addWidget(self.evidence)
        self.layout_choice = QComboBox(self)
        self.layout_choice.setAccessibleName("Layout")
        self.layout_choice.addItems(["layout: core + overlays", "layout: full (layered)"])
        self.layout_choice.currentIndexChanged.connect(self._relayout)
        bar.addWidget(self.layout_choice)
        self.cb_collapse = QCheckBox("collapse mentions", self)
        self.cb_collapse.setAccessibleName("Collapse assessment mentions")
        self.cb_collapse.setChecked(True)
        self.cb_collapse.toggled.connect(self._relayout)
        bar.addWidget(self.cb_collapse)
        bar.addStretch(1)
        if self.two_rows:
            outer.addLayout(bar)
            bar = QHBoxLayout()
        self.search = QLineEdit(self)
        self.search.setAccessibleName("Search graph elements")
        self.search.setPlaceholderText("Search id, type, rule")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._search)
        self.search.returnPressed.connect(self._search_enter)
        bar.addWidget(self.search, 1 if self.two_rows else 0)
        self.hops = QComboBox(self)
        self.hops.setAccessibleName("Focus neighbourhood size")
        self.hops.addItems(["k = 1", "k = 2", "k = 3"])
        bar.addWidget(self.hops)
        self.focus_btn = self._button("Focus", "Focus on selection", self._focus, "Dim everything outside the k-hop "
                                      "neighbourhood of the selection")
        self.focus_btn.setCheckable(True)
        bar.addWidget(self.focus_btn)
        self.content_cb = QCheckBox("Show content", self)
        self.content_cb.setAccessibleName("Show content in the graph popover and inspector")
        self.content_cb.toggled.connect(lambda on: self.set_show_content(on, self.content_limit))
        bar.addWidget(self.content_cb)
        outer.addLayout(bar)

        split = QSplitter(Qt.Orientation.Horizontal, self)
        split.addWidget(self.view)
        side = QWidget(split)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(4, 0, 0, 0)
        self.results = QListWidget(side)
        self.results.setAccessibleName("Search results")
        self.results.setMaximumHeight(120)
        self.results.itemActivated.connect(lambda item: self.select(item.data(Qt.ItemDataRole.UserRole), centre=True))
        sl.addWidget(SafeLabel("Search results", name="Search results heading", parent=side, selectable=False))
        sl.addWidget(self.results)
        sl.addWidget(SafeLabel("Elements", name="Elements heading", parent=side, selectable=False))
        self.elements = ElementsModel()
        self.elements_view = QTableView(side)
        self.elements_view.setAccessibleName("Graph elements list")
        self.elements_view.setModel(self.elements)
        self.elements_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.elements_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.elements_view.verticalHeader().setVisible(False)
        self.elements_view.horizontalHeader().setStretchLastSection(True)
        self.elements_view.selectionModel().currentRowChanged.connect(self._element_row)
        sl.addWidget(self.elements_view, 2)
        sl.addWidget(SafeLabel("Inspector", name="Inspector heading", parent=side, selectable=False))
        self.inspector = QTableWidget(0, 2, side)
        self.inspector.setAccessibleName("Selected element attributes")
        self.inspector.setHorizontalHeaderLabels(["attribute", "value"])
        self.inspector.verticalHeader().setVisible(False)
        self.inspector.horizontalHeader().setStretchLastSection(True)
        self.inspector.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        sl.addWidget(self.inspector, 2)
        self.prov_btn = self._button("Show in PROV-JSON", "Show selection in PROV-JSON", self._show_in_prov,
                                     "Select this element in the PROV-JSON tree")
        sl.addWidget(self.prov_btn)
        legend = ReadOnlyText(name="Legend", parent=side, wrap=True)
        legend.setPlainText(
            "⬭ entity   ▭ activity   ⌂ agent\n"
            "line style: solid = Observed, dashed = Derived, dotted = Inferred\n"
            "purple = inference bundle, brown = assessment bundle, grey dashed = declared outside the drawn bundles\n"
            "+n badge = elements folded onto this node (assessment mentions and claims)"
        )
        legend.setMaximumHeight(90)
        sl.addWidget(legend)
        split.addWidget(side)
        split.setStretchFactor(0, 4)
        split.setStretchFactor(1, 1)
        outer.addWidget(split, 1)
        self.status = SafeLabel("", name="Graph status", parent=self)
        outer.addWidget(self.status)
        self.popover = Popover(self)
        self.view.hovered.connect(self._hover)
        self.view.hover_ended.connect(self.popover.hide)
        app = QGuiApplication.instance()
        if isinstance(app, QGuiApplication):
            app.applicationStateChanged.connect(self._app_state)
        self.view.clicked.connect(lambda key: self.select(key or None))
        self.view.scale_changed.connect(lambda _s: self._update_status())
        for keys, fn in ((QKeySequence.StandardKey.ZoomIn, lambda: self.view.zoom_by(1.25)),
                         (QKeySequence.StandardKey.ZoomOut, lambda: self.view.zoom_by(0.8)),
                         ("Ctrl+0", lambda: self.view.set_zoom(1.0)), ("Ctrl+9", self.view.fit),
                         ("Escape", self._escape), ("F", self.view.fit)):  # fmt: skip
            sc = QShortcut(QKeySequence(keys), self.view)
            sc.activated.connect(fn)

    # ------------------------------------------------------------------------------------------ data
    def clear(self) -> None:
        self._generation += 1
        self.doc, self.model, self.view_graph, self.result = None, None, None, None
        self.view.setScene(None)
        if self.scene_ is not None:
            self.scene_.deleteLater()
        self.scene_ = None
        self.elements.beginResetModel()
        self.elements.rows = []
        self.elements.endResetModel()
        self.results.clear()
        self.inspector.setRowCount(0)
        self.popover.hide()
        self.status.set_plain("")

    def set_document(self, doc: Any, ex: str, locator: str = "") -> None:
        self.clear()
        self.content_cb.setChecked(False)  # S2: per pane, never carried over
        self.doc, self.ex, self.locator = doc, ex, locator or ex
        self._start()

    def set_show_content(self, on: bool, limit: int) -> None:
        self.show_content, self.content_limit = on, limit
        self.popover.hide()  # S2: its rows were drawn under the old switch
        if self._selected:
            self._fill_inspector(self._selected)

    def _start(self) -> None:
        if self.doc is None:
            return
        self._generation += 1
        gen = self._generation
        full = self.layout_choice.currentIndex() == 1
        doc, ex, collapse, cache_dir, model = self.doc, self.ex, self.cb_collapse.isChecked(), self.cache_dir, self.model
        self.status.set_plain("Laying out…")
        def work(_signals: object) -> tuple[GraphModel, ViewGraph, LayoutResult]:
            return graph_work(doc, ex, full=full, collapse=collapse, cache_dir=cache_dir, model=model)

        submit(self, work, partial(self._done, gen), partial(self._failed, gen), pool=self.pool)

    def _relayout(self) -> None:
        self.cb_collapse.setEnabled(self.layout_choice.currentIndex() == 1)
        if self.doc is not None:
            keep_model = self.model
            self.clear_scene_only()
            self.model = keep_model
            self._start()

    def clear_scene_only(self) -> None:
        self.view.setScene(None)
        if self.scene_ is not None:
            self.scene_.deleteLater()
        self.scene_ = None

    @property
    def released(self) -> bool:
        """The scene was dropped to save memory and the layout result kept (D-843)."""
        return self.scene_ is None and self.result is not None and self.view_graph is not None

    def release_scene(self) -> None:
        """Drop the scene and its overview raster, keep the model and the layout result (D-843: a Viewer tab that has
        not been viewed recently). A pending layout or raster for the old scene is superseded."""
        if self.scene_ is None:
            return
        self._generation += 1
        self.popover.hide()
        self.clear_scene_only()

    def restore_scene(self) -> None:
        """Rebuild a released scene from the kept layout result, without laying out again (D-843)."""
        if not self.released:
            return
        assert self.model is not None and self.view_graph is not None and self.result is not None
        selected = self._selected
        self._generation += 1
        self._done(self._generation, (self.model, self.view_graph, self.result))
        if selected is not None:
            self.select(selected)

    def _failed(self, gen: int, code: str) -> None:
        if gen != self._generation:
            return
        self.status.set_plain(f"The graph cannot be drawn ({T.line(code, 80)}).")

    def _done(self, gen: int, res: tuple[GraphModel, ViewGraph, LayoutResult]) -> None:
        if gen != self._generation:
            return
        self.model, self.view_graph, self.result = res
        pal = theme.graph_palette(dark=theme.is_dark(), exact=self.exact_palette)
        scene = GraphScene(self.view_graph, self.result.layout, pal, self)
        self.scene_ = scene
        scene.set_bundles(inference=self.cb_inf.isChecked(), assessment=self.cb_assess.isChecked())
        self.view.setScene(scene)
        self.view.fit()
        self.elements.set_view(self.view_graph, scene)
        self.elements_view.resizeColumnsToContents()
        if len(scene.nodes) > 200:
            sections = {k: n.section for k, n in self.view_graph.by_key.items()}
            fills = {k: items.fill_plain.name() for k, items in scene.nodes.items()}
            layout = self.result.layout
            def raster(_signals: object) -> QImage:
                return paint_raster(layout, sections, fills, pal.canvas, pal.other_relation)

            submit(self, raster, partial(self._raster_done, gen), pool=self.pool)
        self._evidence_changed()
        self._update_status()

    def _raster_done(self, gen: int, image: QImage) -> None:
        if gen == self._generation and self.scene_ is not None:
            self.scene_.set_raster(image)
            self.view.refresh_lod()

    def _show_in_prov(self) -> None:
        if self._selected:
            self.open_in_prov.emit(self._selected)

    def _update_status(self) -> None:
        if self.view_graph is None or self.result is None:
            return
        v = self.view_graph
        folded = sum(len(k) for k in v.folded.values())
        parts = [
            f"{len(v.nodes):,} nodes · {len(v.laid_out_edges):,} edges laid out",
            f"{len(v.edges) - len(v.laid_out_edges):,} overlay edges" if len(v.edges) != len(v.laid_out_edges) else "",
            f"{folded:,} folded" if folded else "",
            f"{len(v.unplaced):,} not placed" if v.unplaced else "",
            f"{self.result.layout.engine} {self.result.seconds:.2f} s" + (" (cached)" if self.result.cached else ""),
            f"zoom {self.view.current_scale() * 100:.0f} %",
            self.result.note or "",
        ]
        self.status.set_plain(" · ".join(p for p in parts if p))

    # ------------------------------------------------------------------------------------------ interaction
    def _bundles_changed(self) -> None:
        if self.scene_ is not None:
            self.scene_.set_bundles(inference=self.cb_inf.isChecked(), assessment=self.cb_assess.isChecked())

    def _evidence_changed(self) -> None:
        if self.scene_ is None:
            return
        wanted = {0: None, 1: "O", 2: "D", 3: "I"}[self.evidence.currentIndex()]
        if wanted is None:
            self.scene_.dim(None)
        else:
            self.scene_.dim({k for k, n in self.scene_.nodes.items()
                             if self.view_graph is not None and self.view_graph.by_key[k].cls == wanted})

    def _bundle_titles(self) -> dict[int, str]:
        return {b.index: b.title for b in self.model.bundles} if self.model is not None else {}

    def _rows_for(self, key: str) -> list[tuple[str, str]]:
        if self.view_graph is None or key not in self.view_graph.by_key:
            return []
        rows = node_facts(self.view_graph.by_key[key], self._bundle_titles(), self.show_content, self.content_limit,
                          self.locator)
        folded = self.view_graph.folded.get(key, [])
        if folded:
            rows.append(("folded elements", f"{len(folded):,}"))
            rows += [("  folded", T.line(k)) for k in folded[:200]]
        return rows

    def _hover(self, key: str, at: QPoint) -> None:
        if self.isVisible():
            self.popover.show_rows(self._rows_for(key), at)

    def hideEvent(self, event: QHideEvent) -> None:
        # The popover is a top-level tool window: hiding this tab or its page does not hide it.
        self.popover.hide()
        super().hideEvent(event)

    def _app_state(self, state: Qt.ApplicationState) -> None:
        if state != Qt.ApplicationState.ApplicationActive:
            self.popover.hide()

    def _escape(self) -> None:
        self.popover.hide()
        self.select(None)
        if self.focus_btn.isChecked():
            self.focus_btn.setChecked(False)
            self._focus()

    def _fill_inspector(self, key: str) -> None:
        fill_table(self.inspector, self._rows_for(key))
        self.inspector.resizeColumnToContents(0)
        self.inspector.resizeRowsToContents()

    def select(self, key: str | None, *, centre: bool = False) -> None:
        self.popover.hide()
        if self.scene_ is None:
            return
        self._selected = key
        self.scene_.select(key)
        if key is None:
            self.inspector.setRowCount(0)
            return
        self._fill_inspector(key)
        row = self.elements.row_of(key)
        if row >= 0 and self.elements_view.currentIndex().row() != row:
            self.elements_view.selectRow(row)
        if centre and key in self.scene_.nodes:
            self.view.centerOn(self.scene_.nodes[key].shape)
        if self.focus_btn.isChecked():
            self._focus()

    def _element_row(self, current: QModelIndex, _prev: QModelIndex) -> None:
        if current.isValid() and 0 <= current.row() < len(self.elements.rows):
            key = self.elements.rows[current.row()][0]
            if key != self._selected:
                self.select(key, centre=True)

    def _focus(self) -> None:
        if self.scene_ is None:
            return
        if self.focus_btn.isChecked() and self._selected in self.scene_.nodes:
            self.scene_.dim(self.scene_.neighbourhood(self._selected, self.hops.currentIndex() + 1))
        else:
            self._evidence_changed()

    def _search(self, query: str) -> None:
        self.results.clear()
        q = query.strip().lower()
        if not q or self.view_graph is None:
            return
        hits = 0
        for key, node in self.view_graph.by_key.items():
            types = " ".join(style.qnames(node.attrs.get("prov:type")))
            rule = node.attrs.get("apv:rule")
            hay = " ".join((key, types, rule if isinstance(rule, str) else "")).lower()
            if self.show_content:
                hay += " " + " ".join(T.plain_value(v) for v in node.attrs.values()).lower()
            if q in hay:
                item = QListWidgetItem(f"{T.line(key, 80)}   {node.section}")
                item.setData(Qt.ItemDataRole.UserRole, key)
                self.results.addItem(item)
                hits += 1
                if hits >= 500:
                    break

    def _search_enter(self) -> None:
        if self.results.count():
            self.results.setCurrentRow(0)
            key = self.results.item(0).data(Qt.ItemDataRole.UserRole)
            self.select(key, centre=True)

