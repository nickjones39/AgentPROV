"""One execution's detail (design §6.1 "Execution detail"; D-841, D-842, D-844; the one style of D-1060).

An :class:`ExecutionPane` holds its own Graph, PROV-JSON, AER, SEM, Register, Validation, Raw and Index Row widgets,
its own load generation counter (a newer request supersedes an older one, per pane) and its own Show-content switches
(S2: off in every new pane). Two forms:

- **compact** (the Viewer's right-hand inspector, D-842, D-1060): Graph and PROV-JSON are separate views, laid out for
  a narrow pane (the graph's tools wrap, the PROV-JSON tree sits above its text);
- **full** (a Viewer tab, D-841): the first view shows the graph and the PROV-JSON side by side, linked both ways.

The views are chosen with a segmented control in place of a tab bar (D-1060); :attr:`ExecutionPane.tabs` stays the
container that holds them (its own bar hidden), so every view keeps its content rules (S1 plain text, the Show content
switches, the limits). The compact header is a small EXECUTION heading with Open in New Tab, the id and its status,
completeness and source as badges (words with a tint); the full header is the id as a title with the badges and its
actions (Show in Corpora, Export Graph…). The **terminal command** (D-700) is what the pane shows in a terminal:
``agentprov inspect ID --corpus DIR --view …`` for the open view and the ``agentprov render`` that Export Graph… opens
with the render form's defaults, both built by the job forms' own :func:`build_spec` (a card under a full pane's views;
in the inspector, a "Terminal command" disclosure under Export Graph…).

A full pane keeps the loaded detail and its corpus path, never an open reader (D-844): it is a read-only snapshot, and
Reload Execution re-reads it. Nothing is written inside a corpus.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any, Final

from agentprov.corpus.reader import CorpusReader, CorpusReadError
from PySide6.QtCore import QSettings, Qt, QThreadPool, Signal
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from agentprov_gui import text as T
from agentprov_gui.jobs.commands import FORMS, FormError, build_spec
from agentprov_gui.readmodel.detail import DetailCache, ExecutionDetail, load_detail
from agentprov_gui.readmodel.executions import ExecutionTable, read_row
from agentprov_gui.ui import theme
from agentprov_gui.ui.detail import (
    AerTab,
    ProvJsonTab,
    RegisterTab,
    SemTab,
    ValidationTab,
    field_tip,
    fill_rows,
    tidy_view,
)
from agentprov_gui.ui.forms import (
    CommandCard,
    Disclosure,
    SegmentedControl,
    StatusBadge,
    caption,
    heading,
    link_button,
)
from agentprov_gui.ui.graphview import GraphTab
from agentprov_gui.ui.safe import (
    ReadOnlyText,
    SafeLabel,
    set_control_tooltip,
    set_header_tooltips,
    set_tab_tooltip,
    set_tooltip,
)
from agentprov_gui.ui.worker import JobSignals, submit

__all__ = ["EXECUTION_ID", "CorpusSource", "ExecutionPane", "render_values"]

#: The core's ``agentprov.aer.ids.EXECUTION_ID_RE`` (not on the GUI's import allowlist; a test pins the two together).
#: S13: only an id of this shape reaches the clipboard or a terminal command.
EXECUTION_ID: Final = re.compile(
    r"ex_(?:[a-z2-7]{26}|[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})"
)
GRAPH_PROV: Final = "Graph + PROV-JSON"
#: what each detail tab shows (tab tooltips)
TAB_TIPS: Final = {
    "Graph": "The execution's W3C PROV graph: the core bundle, with the inference and assessment bundles as overlays",
    "PROV-JSON": "The PROV documents as a tree of bundles, sections and statements; Show content adds the raw text",
    GRAPH_PROV: "The PROV graph and its PROV-JSON side by side; selecting a statement in one selects it in the other",
    "AER": "The AgentPROV Execution Record: the canonical records of the execution, grouped by kind, and its seal",
    "SEM": "The semantic annotations on the AER records, per semantics profile",
    "Register": "The register entries (issues) recorded for this execution",
    "Validation": "The validation checks run on this execution and their results",
    "Raw": "The raw source artefacts behind this execution, by digest",
    "Index Row": "This execution's row of the corpus index (executions.jsonl), as JSON",
}
#: D-700: the ``agentprov inspect --view`` that prints what each detail tab shows, and the comment over it (the CLI's
#: nearest view where it has none of its own: the summary holds the index row and the AER's summary)
INSPECT_VIEWS: Final[dict[str, tuple[str, str]]] = {
    "Graph": ("prov", "the Graph tab: the PROV statements"),
    "PROV-JSON": ("prov", "the PROV-JSON tab: every bundle's statements"),
    GRAPH_PROV: ("prov", "the Graph + PROV-JSON tab: every bundle's statements"),
    "AER": ("records", "the AER tab: the records"),
    "SEM": ("sem", "the SEM tab: the annotations"),
    "Register": ("summary", "the Register tab: the CLI's nearest view is the summary (index row with its issues)"),
    "Validation": ("summary", "the Validation tab: the CLI's nearest view is the summary"),
    "Raw": ("raw", "the Raw tab: the raw artefacts"),
    "Index Row": ("summary", "the Index Row tab: the summary holds the index row"),
}
#: a status or completeness as a badge's tint (the words carry it; the tint only repeats it)
STATUS_KIND: Final = {"ok": "ok", "ok_with_issues": "warn", "failed": "bad"}
COMPLETENESS_KIND: Final = {"verified_complete": "ok", "known_incomplete": "warn", "unverifiable": "neutral"}


def render_values(corpus: str, ex: str) -> dict[str, Any]:
    """The render form's values for Export Graph… (D-706, D-654): the one place the main window's render form and the
    pane's terminal command both take them from."""
    return {"corpus": corpus, "ex": ex}


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
    commands_changed = Signal()  # the terminal command changed (another execution, sub-tab or bundle choice)

    def __init__(self, cache_dir: Path | None, cache: DetailCache, *, compact: bool,
                 content_limit: int = T.CONTENT_CHARS_DEFAULT, exact_palette: bool = False,
                 parent: QWidget | None = None, store: QSettings | None = None) -> None:
        super().__init__(parent)
        self.compact = compact
        self.store = store  # the GUI's QSettings: the inspector's Terminal command disclosure is remembered there
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
        margin = 0 if self.compact else 2 * theme.SPACE
        dl.setContentsMargins(margin, theme.SPACE if not self.compact else 0, margin, margin)
        dl.setSpacing(6 if self.compact else 4)
        self.status_badge = StatusBadge(name="Execution status", parent=self)
        set_tooltip(self.status_badge, "The execution's status: ok, ok with issues (a warning in the register) or failed")
        self.completeness_badge = StatusBadge(name="Execution completeness", parent=self)
        set_tooltip(self.completeness_badge, "verified complete (the record reconciles with the source), known "
                                             "incomplete (a rule proves loss) or unverifiable (the source does not "
                                             "record enough to tell)")
        self.source_badge = StatusBadge(name="Execution source", parent=self)
        set_tooltip(self.source_badge, "The registry id of the source the execution came from")
        badges = (self.status_badge, self.completeness_badge, self.source_badge)
        if self.compact:
            # the inspector: a small heading with Open in New Tab, the id, then its states as badges
            top = QHBoxLayout()
            top.addWidget(heading("Execution", name="Execution heading", parent=self))
            top.addStretch(1)
            self.open_btn = link_button("Open in New Tab", name="Open this execution in a new Viewer tab", parent=self)
            set_control_tooltip(self.open_btn, "Open in a tab of its own (double-click or Return in the table)")
            self.open_btn.setEnabled(False)
            self.open_btn.clicked.connect(self.open_requested)
            top.addWidget(self.open_btn)
            dl.addLayout(top)
            self.title = SafeLabel("Select an execution", name="Execution detail title", parent=self)
            self.title.setFont(theme.scaled_font("mono"))
            self.title.setWordWrap(True)
            self.title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            dl.addWidget(self.title)
            badge_row = QHBoxLayout()
            badge_row.setSpacing(6)
            for badge in badges:
                badge_row.addWidget(badge)
            badge_row.addStretch(1)
            dl.addLayout(badge_row)
        else:
            # the header: the id as a title, its states as badges, the actions at the right
            title_row = QHBoxLayout()
            title_row.setSpacing(theme.SPACE)
            self.title = SafeLabel("", name="Execution detail title", parent=self)
            font = theme.scaled_font("title")
            font.setWeight(QFont.Weight.DemiBold)
            self.title.setFont(font)
            self.title.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
            title_row.addWidget(self.title)
            for badge in badges:
                title_row.addWidget(badge)
            title_row.addStretch(1)
            self.reveal_btn = QPushButton("Show in Corpora", self)
            self.reveal_btn.setAccessibleName("Show this execution in the Corpora tab")
            set_control_tooltip(self.reveal_btn, "Select this execution's row in the Corpora tab")
            self.reveal_btn.clicked.connect(self.reveal_requested)
            title_row.addWidget(self.reveal_btn)
            title_row.addWidget(self._render_button())
            dl.addLayout(title_row)
        self.subtitle = caption("", name="Execution detail facts", parent=self)
        self.subtitle.setVisible(False)
        dl.addWidget(self.subtitle)
        # D-1060: a segmented control chooses the view (made before the views, so Tab reaches it first); the tab
        # widget's own bar is hidden (it still holds the views, and the focus goes to the segments, not to it)
        titles = ["Graph", "AER", "SEM", "PROV-JSON"] if self.compact else [GRAPH_PROV, "AER", "SEM"]
        titles += ["Register", "Validation", "Raw", "Index Row"]
        self.views = SegmentedControl(titles, name="Execution view", parent=self, wrap=True)
        for i, title in enumerate(titles):
            self.views.set_tip(i, TAB_TIPS[title])
        dl.addWidget(self.views)
        self.tabs = QTabWidget(self)
        self.tabs.setAccessibleName("Execution detail tabs")
        self.tabs.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.graph = GraphTab(cache_dir, self.tabs, content_limit=self.content_limit, two_rows=not self.compact,
                              narrow=self.compact)
        self.graph.exact_palette = exact_palette
        self.prov = ProvJsonTab(self.tabs, stacked=True)
        self.aer = AerTab(self.tabs)
        self.sem = SemTab(self.tabs)
        self.register = RegisterTab(self.tabs)
        self.validation = ValidationTab(self.tabs)
        self.raw = QTableWidget(0, 4, self.tabs)
        self.raw.setAccessibleName("Raw artefacts")
        self.raw.setHorizontalHeaderLabels(["Role", "SHA-256", "In the corpus", "Note"])
        self.raw.horizontalHeader().setStretchLastSection(True)
        tidy_view(self.raw)
        set_header_tooltips(self.raw, [field_tip(tip, raw) for tip, raw in (
            ("The artefact's role: primary (the source file), capture log, native log or supporting", "role"),
            ("The SHA-256 digest of the artefact's bytes in the raw store", "sha256"),
            ("yes: the bytes are in the corpus; no: the artefact is only referenced", "included"),
            ("A note on the artefact", "note"))])  # fmt: skip
        self.row_json = ReadOnlyText(name="Index row JSON", parent=self.tabs)
        rest: list[tuple[QWidget, str]] = [(self.register, "Register"), (self.validation, "Validation"),
                                           (self.raw, "Raw"), (self.row_json, "Index Row")]
        if self.compact:
            # the inspector's order (D-1060): the graph, the records and their annotations, then the PROV-JSON
            views: list[tuple[QWidget, str]] = [(self.graph, "Graph"), (self.aer, "AER"), (self.sem, "SEM"),
                                                (self.prov, "PROV-JSON"), *rest]
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
            views = [(self.graph_prov, GRAPH_PROV), (self.aer, "AER"), (self.sem, "SEM"), *rest]
        for w, title in views:
            set_tab_tooltip(self.tabs, self.tabs.addTab(w, title), TAB_TIPS[title], wrap=True)
        self.tabs.tabBar().hide()
        self.views.currentIndexChanged.connect(self.tabs.setCurrentIndex)
        self.tabs.currentChanged.connect(self.views.setCurrentIndex)
        self.graph.open_in_prov.connect(self._reveal_in_prov)
        self.prov.statement_selected.connect(lambda key: self.graph.select(key, centre=False))
        if not self.compact:
            # D-845: ⌃Tab / ⌃⇧Tab switch the views (macOS; Qt's Meta is the Control key there). Elsewhere QTabWidget's
            # own Ctrl+Tab does it, and the Viewer tabs use Ctrl+PgDown / Ctrl+PgUp.
            for keys, step in (("Meta+Tab", 1), ("Meta+Shift+Backtab", -1), ("Meta+Shift+Tab", -1)):
                sc = QShortcut(QKeySequence(keys), self, context=Qt.ShortcutContext.WidgetWithChildrenShortcut)
                sc.activated.connect(partial(self._step_subtab, step))
        dl.addWidget(self.tabs, 1)
        # the terminal command (D-700): what this pane shows, under its views
        self.command_card = CommandCard(name="Execution terminal command", title="Terminal command", parent=self)
        self.command_card.copy_button.setAccessibleName("Copy this execution's terminal commands")
        self.terminal: Disclosure | None = None
        if self.compact:
            actions = QHBoxLayout()
            actions.addWidget(self._render_button())
            actions.addStretch(1)
            dl.addLayout(actions)
            self.terminal = Disclosure("Terminal command", screen="viewer", key="inspector-terminal", store=self.store,
                                       name="Show the terminal command for this execution", parent=self)
            set_control_tooltip(self.terminal.button, "Shows the agentprov inspect command that prints the open view, "
                                                      "and the agentprov render that Export Graph… opens")
            self.terminal.add(self.command_card)
            dl.addWidget(self.terminal)
        else:
            dl.addSpacing(4)
            dl.addWidget(self.command_card)
        self.commands_changed.connect(self._show_commands)
        self.tabs.currentChanged.connect(lambda _i: self.commands_changed.emit())
        for cb in (self.graph.cb_inf, self.graph.cb_assess):
            cb.toggled.connect(lambda _on: self.commands_changed.emit())
        self._show_commands()

    def _render_button(self) -> QPushButton:
        """Export Graph… (made where it sits, so Tab reaches it in the order it is shown)."""
        self.render_btn = QPushButton("Export Graph…", self)
        self.render_btn.setAccessibleName("Export this execution's graph with agentprov render")
        set_control_tooltip(self.render_btn, "Export this execution's graph as SVG, PNG, PDF or DOT: agentprov render "
                                            "--corpus … --ex …, run as a job")
        self.render_btn.setEnabled(False)
        self.render_btn.clicked.connect(self._request_render)
        return self.render_btn

    # ------------------------------------------------------------------------------------------ loading
    def clear(self) -> None:
        """Empty every part; a pending load is superseded."""
        self._gen += 1
        self.title.set_plain("Select an execution" if self.compact else "")
        self._badges(None)
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
            self.title.set_plain(f"{T.line(self.detail.ex)} · cannot be reloaded ({T.line(code, 80)}); "
                                 "showing the earlier snapshot")
            self._set_state("ready")
            return
        self._badges(None)
        self.title.set_plain(f"{T.line(ex)} cannot be opened ({T.line(code, 80)})")
        self._set_state("failed")

    def _loaded(self, gen: int, root: str, detail: ExecutionDetail) -> None:
        self.cache.put(root, detail)
        self._show(gen, detail)

    def _badges(self, d: ExecutionDetail | None) -> None:
        """The execution's status, completeness and source as badges (hidden while nothing is shown)."""
        row = d.row if d is not None else None
        status = row.status if row is not None else ""
        completeness = row.completeness if row is not None else ""
        self.status_badge.set_status(theme.status_text(status) if status else "", STATUS_KIND.get(status, "neutral"))
        self.completeness_badge.set_status(T.line(completeness.replace("_", " "), 40) if completeness else "",
                                           COMPLETENESS_KIND.get(completeness, "neutral"))
        self.source_badge.set_status(T.line(row.source_id, 60) if row is not None else "", "neutral")

    def _facts_text(self) -> str:
        """The full pane's line under the title: the corpus, read-only or being written, and the snapshot's time."""
        if self.compact or self.source is None:
            return ""
        state = "being written" if self.source.writing else "read-only"
        text = f"{T.line(self.source.name, 80)} ({state})"
        if self.source.writing and self.loaded_at is not None:  # the computer's local time with its zone's name
            text += f" · snapshot loaded at {time.strftime('%H:%M:%S %Z', time.localtime(self.loaded_at))}"
        return text

    def _show(self, gen: int, d: ExecutionDetail) -> None:
        if gen != self._gen:
            return
        row = d.row
        self.detail = d
        self.loaded_at = time.time()
        self.title.set_plain(T.line(d.ex))
        self._badges(d)
        facts = self._facts_text()
        self.subtitle.set_plain(facts)
        self.subtitle.setVisible(bool(facts))
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
        self.commands_changed.emit()

    # ------------------------------------------------------------------------------------------ terminal command
    def terminal_commands(self) -> list[tuple[str, list[str]]]:
        """D-700: ``(comment, argv)`` of what this pane shows, as a terminal prints it: ``agentprov inspect`` with the
        open sub-tab's view, and the ``agentprov render`` Export Graph… opens (the render form's defaults). Both come
        from the job forms' :func:`build_spec`, the code the jobs run. None for an id of another shape (S13)."""
        if self.state != "ready" or self.ex is None or self.source is None or not self.source.arg \
                or EXECUTION_ID.fullmatch(self.ex) is None:
            return []
        tab = self.tabs.tabText(self.tabs.currentIndex())
        view, comment = INSPECT_VIEWS.get(tab, ("summary", "the execution's summary"))
        bundle: str | None = None
        if view == "prov":  # the graph shows the core bundle and the overlays ticked; the tree shows every bundle
            overlays = self.graph.cb_inf.isChecked() or self.graph.cb_assess.isChecked()
            bundle = "all" if tab != "Graph" or overlays else "core"
            comment += f" ({'every bundle' if bundle == 'all' else 'the core bundle'})"
        out: list[tuple[str, list[str]]] = []
        try:
            spec = build_spec(FORMS["inspect"], {"target": self.ex, "corpus": self.source.arg, "view": view,
                                                 "bundle": bundle, "format": None})
            out.append((comment, list(spec.argv)))
        except FormError:
            pass
        try:
            spec = build_spec(FORMS["render"], render_values(self.source.arg, self.ex))
            out.append(("Export Graph… (the render form's defaults)", list(spec.argv)))
        except FormError:
            pass
        return out

    def _show_commands(self) -> None:
        self.command_card.set_commands(self.terminal_commands(), note="the commands appear once an execution is read")

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
