"""One execution's detail (design §6.1 "Execution detail"; D-841, D-842, D-844).

An :class:`ExecutionPane` holds its own Graph, PROV-JSON, AER, SEM, Register, Validation, Raw and Index Row widgets,
its own load generation counter (a newer request supersedes an older one, per pane) and its own Show-content switches
(S2: off in every new pane). Two forms:

- **compact** (the preview below the executions table, D-842): Graph and PROV-JSON are separate sub-tabs;
- **full** (a Viewer tab, D-841): the first sub-tab shows the graph and the PROV-JSON side by side, linked both ways.

A full pane keeps the loaded detail and its corpus path, never an open reader (D-844): it is a read-only snapshot, and
Reload Execution re-reads it. Nothing is written inside a corpus.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Final

from agentprov.corpus.reader import CorpusReader, CorpusReadError
from PySide6.QtCore import Qt, QThreadPool, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from agentprov_gui import text as T
from agentprov_gui.readmodel.detail import DetailCache, ExecutionDetail, load_detail
from agentprov_gui.readmodel.executions import ExecutionTable, read_row
from agentprov_gui.ui import theme
from agentprov_gui.ui.detail import AerTab, ProvJsonTab, RegisterTab, SemTab, ValidationTab, fill_rows
from agentprov_gui.ui.graphview import GraphTab
from agentprov_gui.ui.safe import ReadOnlyText, SafeLabel, set_tooltip
from agentprov_gui.ui.worker import JobSignals, submit

__all__ = ["CorpusSource", "ExecutionPane"]

GRAPH_PROV: Final = "Graph + PROV-JSON"


@dataclass(frozen=True, slots=True)
class CorpusSource:
    """The corpus an execution was read from, as a pane remembers it (no open reader, D-844)."""

    name: str
    root: str  # the tree read (resolved): the DetailCache key and the tab identity (D-843)
    path: Path  # what Reload Execution re-opens
    arg: str  # the corpus as ``--corpus`` names it (Export Graph)
    writing: bool  # a working tree being written by a CLI job: the snapshot time is shown


class ExecutionPane(QWidget):
    render_requested = Signal(str, str)  # (corpus, ex): Export Graph… (D-706, D-654)
    open_requested = Signal()  # compact: Open in New Tab (D-842)
    reveal_requested = Signal()  # full: Show in Corpora (D-841)
    state_changed = Signal()  # loading, ready or failed: the tab title follows

    def __init__(self, cache_dir: Path | None, cache: DetailCache, *, compact: bool,
                 content_limit: int = T.CONTENT_CHARS_DEFAULT, exact_palette: bool = False,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.compact = compact
        self.setAccessibleName("Execution preview" if compact else "Execution")
        self.cache = cache
        self.content_limit = content_limit
        self.pool = QThreadPool.globalInstance()
        self.source: CorpusSource | None = None
        self.ex: str | None = None
        self.detail: ExecutionDetail | None = None
        self.state = "empty"  # empty | loading | ready | failed
        self.loaded_at: float | None = None
        self._gen = 0
        self._build(cache_dir, exact_palette)

    def _build(self, cache_dir: Path | None, exact_palette: bool) -> None:
        dl = QVBoxLayout(self)
        dl.setContentsMargins(0, 0, 0, 0)
        title_row = QHBoxLayout()
        self.title = SafeLabel("Select an execution" if self.compact else "", name="Execution detail title", parent=self)
        title_row.addWidget(self.title, 1)
        if self.compact:
            self.open_btn = QPushButton("Open in New Tab", self)
            self.open_btn.setAccessibleName("Open this execution in a new Viewer tab")
            set_tooltip(self.open_btn, "Open in a tab of its own (double-click or Return in the table)")
            self.open_btn.setEnabled(False)
            self.open_btn.clicked.connect(self.open_requested)
            title_row.addWidget(self.open_btn)
        else:
            self.reveal_btn = QPushButton("Show in Corpora", self)
            self.reveal_btn.setAccessibleName("Show this execution in the Corpora tab")
            set_tooltip(self.reveal_btn, "Select this execution's row in the Corpora tab")
            self.reveal_btn.clicked.connect(self.reveal_requested)
            title_row.addWidget(self.reveal_btn)
        self.render_btn = QPushButton("Export Graph…", self)
        self.render_btn.setAccessibleName("Export this execution's graph with agentprov render")
        set_tooltip(self.render_btn, "agentprov render --corpus … --ex … (SVG, PNG, PDF or DOT), as a job")
        self.render_btn.setEnabled(False)
        self.render_btn.clicked.connect(self._request_render)
        title_row.addWidget(self.render_btn)
        dl.addLayout(title_row)
        self.tabs = QTabWidget(self)
        self.tabs.setAccessibleName("Execution detail tabs")
        self.graph = GraphTab(cache_dir, self.tabs, content_limit=self.content_limit, two_rows=not self.compact)
        self.graph.exact_palette = exact_palette
        self.prov = ProvJsonTab(self.tabs, stacked=not self.compact)
        self.aer = AerTab(self.tabs)
        self.sem = SemTab(self.tabs)
        self.register = RegisterTab(self.tabs)
        self.validation = ValidationTab(self.tabs)
        self.raw = QTableWidget(0, 4, self.tabs)
        self.raw.setAccessibleName("Raw artefacts")
        self.raw.setHorizontalHeaderLabels(["role", "sha256", "included", "note"])
        self.raw.verticalHeader().setVisible(False)
        self.raw.horizontalHeader().setStretchLastSection(True)
        self.row_json = ReadOnlyText(name="Index row JSON", parent=self.tabs)
        if self.compact:
            first: list[tuple[QWidget, str]] = [(self.graph, "Graph"), (self.prov, "PROV-JSON")]
            self.graph_prov: QSplitter | None = None
        else:
            # D-841: the graph and the PROV-JSON side by side (60:40); dragging the splitter to an edge hides a side
            self.graph_prov = QSplitter(Qt.Orientation.Horizontal, self.tabs)
            self.graph_prov.setAccessibleName("Graph and PROV-JSON")
            self.graph_prov.addWidget(self.graph)
            self.graph_prov.addWidget(self.prov)
            self.graph_prov.setStretchFactor(0, 3)
            self.graph_prov.setStretchFactor(1, 2)
            self.graph_prov.setSizes([600, 400])  # scaled to the width the splitter gets
            first = [(self.graph_prov, GRAPH_PROV)]
        for w, title in (*first, (self.aer, "AER"), (self.sem, "SEM"), (self.register, "Register"),
                         (self.validation, "Validation"), (self.raw, "Raw"), (self.row_json, "Index Row")):
            self.tabs.addTab(w, title)
        self.graph.open_in_prov.connect(self._reveal_in_prov)
        self.prov.statement_selected.connect(lambda key: self.graph.select(key, centre=False))
        if not self.compact:
            # D-845: ⌃Tab / ⌃⇧Tab switch the sub-tabs (macOS; Qt's Meta is the Control key there). Elsewhere QTabWidget's
            # own Ctrl+Tab does it, and the Viewer tabs use Ctrl+PgDown / Ctrl+PgUp.
            for keys, step in (("Meta+Tab", 1), ("Meta+Shift+Backtab", -1), ("Meta+Shift+Tab", -1)):
                sc = QShortcut(QKeySequence(keys), self, context=Qt.ShortcutContext.WidgetWithChildrenShortcut)
                sc.activated.connect(partial(self._step_subtab, step))
        dl.addWidget(self.tabs, 1)

    # ------------------------------------------------------------------------------------------ loading
    def clear(self) -> None:
        """Empty every part; a pending load is superseded."""
        self._gen += 1
        self.title.set_plain("Select an execution" if self.compact else "")
        self.graph.clear()
        self.prov.set_documents({}, self.content_limit)
        self.aer.set_document(None, "", self.content_limit, None)
        self.sem.set_documents({}, {})
        self.register.set_entries([], None)
        self.validation.set_row(None, None)
        self.raw.setRowCount(0)
        self.row_json.setPlainText("")
        self.render_btn.setEnabled(False)
        if self.compact:
            self.open_btn.setEnabled(False)
        self.source, self.ex, self.detail, self.loaded_at = None, None, None, None
        self._set_state("empty")

    def load(self, reader: CorpusReader, table: ExecutionTable, row: int, source: CorpusSource) -> None:
        """Show table row ``row`` of the corpus ``reader`` reads: from the cache, else read in a worker thread."""
        ex = table.ex(row)
        self._gen += 1
        gen = self._gen
        self.source, self.ex = source, ex
        cached = self.cache.get(source.root, ex)
        if cached is not None:
            self._show(gen, cached)
            return
        self._loading(ex)

        def work(_signals: JobSignals) -> ExecutionDetail:
            return load_detail(reader, read_row(reader, table, row))

        submit(self, work, partial(self._loaded, gen, source.root), partial(self._failed, gen, ex), pool=self.pool)

    def show_detail(self, detail: ExecutionDetail, source: CorpusSource) -> None:
        """Show an already loaded detail (a new tab opened from the preview, D-843: shared, not copied)."""
        self._gen += 1
        self.source, self.ex = source, detail.ex
        self._show(self._gen, detail)

    def reload(self) -> None:
        """Reload Execution (D-844): re-open the corpus and re-read this execution; the old snapshot stays on failure."""
        if self.source is None or self.ex is None:
            return
        self._gen += 1
        gen = self._gen
        source, ex = self.source, self.ex
        self._loading(ex)

        def work(_signals: JobSignals) -> tuple[str, ExecutionDetail]:
            reader = CorpusReader.open(source.path)
            row = reader.row(ex)
            if row is None:
                raise CorpusReadError("the execution is no longer in the corpus index", code="corpus.read.missing")
            return str(reader.root), load_detail(reader, row)

        def done(res: tuple[str, ExecutionDetail]) -> None:
            self._loaded(gen, res[0], res[1])

        submit(self, work, done, partial(self._failed, gen, ex), pool=self.pool)

    def _loading(self, ex: str) -> None:
        self.title.set_plain(f"{T.line(ex)} · loading…")
        self._set_state("loading")

    def _failed(self, gen: int, ex: str, code: str) -> None:
        if gen != self._gen:
            return
        if self.detail is not None:  # a failed reload keeps the snapshot (D-844)
            self.title.set_plain(f"{self._title_text(self.detail)} · cannot be reloaded ({T.line(code, 80)}); "
                                 "showing the earlier snapshot")
            self._set_state("ready")
            return
        self.title.set_plain(f"{T.line(ex)} cannot be opened ({T.line(code, 80)})")
        self._set_state("failed")

    def _loaded(self, gen: int, root: str, detail: ExecutionDetail) -> None:
        self.cache.put(root, detail)
        self._show(gen, detail)

    def _title_text(self, d: ExecutionDetail) -> str:
        row = d.row
        text = f"{T.line(d.ex)} · {T.line(row.source_id)} · {theme.status_text(row.status)} · {T.line(row.completeness)}"
        if not self.compact and self.source is not None:
            state = "being written" if self.source.writing else "read-only"
            text += f" · {T.line(self.source.name, 80)} ({state})"
            if self.source.writing and self.loaded_at is not None:
                text += f" · snapshot loaded at {time.strftime('%H:%M:%S', time.localtime(self.loaded_at))}"
        return text

    def _show(self, gen: int, d: ExecutionDetail) -> None:
        if gen != self._gen:
            return
        row = d.row
        self.detail = d
        self.loaded_at = time.time()
        self.title.set_plain(self._title_text(d))
        docs = {spec: (d.prov[spec], d.prov_text[spec], (row.prov_paths or {}).get(spec, spec), d.prov_size[spec])
                for spec in d.prov}
        self.prov.set_documents(docs, self.content_limit)
        self.aer.set_document(d.aer, row.aer_path, self.content_limit, d.errors.get("aer"))
        self.sem.set_documents(d.sem, {k.removeprefix("sem:"): v for k, v in d.errors.items() if k.startswith("sem:")})
        self.register.set_entries(d.register, d.errors.get("register"))
        self.validation.set_row(d.validation, d.errors.get("validation"))
        fill_rows(self.raw, ([r.role, r.sha256, "yes" if r.included else "no", "content is not shown in G1"]
                             for r in row.raw))
        self.raw.resizeColumnsToContents()
        # the checked index row itself (D-706); ensure_ascii escapes every control character (S3)
        self.row_json.setPlainText(json.dumps(row.to_json(), indent=2, sort_keys=True, ensure_ascii=True))
        self.render_btn.setEnabled(self.source is not None)
        if self.compact:
            self.open_btn.setEnabled(True)
        spec = "agentprov-prov/0.1" if "agentprov-prov/0.1" in d.prov else (sorted(d.prov)[0] if d.prov else None)
        if spec is not None:
            self.graph.set_document(d.prov[spec], d.ex, docs[spec][2])
        else:
            self.graph.clear()
            self.graph.status.set_plain("No PROV output: nothing to draw." if not any(
                k.startswith("prov:") for k in d.errors) else "The PROV document cannot be read.")
        self._set_state("ready")

    def _set_state(self, state: str) -> None:
        self.state = state
        self.state_changed.emit()

    # ------------------------------------------------------------------------------------------ actions
    def _request_render(self) -> None:
        if self.ex is not None and self.source is not None:
            self.render_requested.emit(self.source.arg, self.ex)

    def _reveal_in_prov(self, key: str) -> None:
        if self.prov.reveal(key) and self.compact:
            self.tabs.setCurrentWidget(self.prov)

    def _step_subtab(self, step: int) -> None:
        self.tabs.setCurrentIndex((self.tabs.currentIndex() + step) % self.tabs.count())

    def set_show_content_limit(self, limit: int) -> None:
        self.content_limit = limit
        self.graph.set_show_content(self.graph.show_content, limit)  # refreshes popover and inspector

    def set_exact_palette(self, exact: bool) -> None:
        self.graph.exact_palette = exact
