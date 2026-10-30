"""Execution detail tabs: PROV-JSON, AER, SEM, Register, Validation (design §6.1; wireframe 01; S2, S3).

* **Content is hidden by default** (G.8.2, S2). Each pane that can show content has its own "Show content" switch; it
  is never persisted and resets when a corpus is opened. Hidden values show as ``‹text, n chars, sha256:…›``; shown
  values are fenced by ``quote_untrusted`` with their locator and truncated at the viewer limit.
* **Structure is always visible**: ids, kinds, evidence classes, rule ids, locators, unknown reasons, digests and sizes,
  each escaped as one line (S3).
* Trees are populated lazily (a 4 MB PROV document has tens of thousands of attributes).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from typing import Any, Final

from agentprov.aer.reader import AerDocument
from agentprov.corpus.register import RegisterEntry
from agentprov.render import style
from agentprov.sem.types import SemDocument
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from agentprov_gui import text as T
from agentprov_gui.ui.safe import ReadOnlyText, SafeLabel

__all__ = ["AerTab", "ProvJsonTab", "RegisterTab", "SemTab", "ValidationTab", "fill_rows"]

#: AER record members that are structure (ids, enums, locators, rule ids), shown without Show content.
AER_STRUCTURE: Final = frozenset({
    "id", "k", "ev", "evf", "by", "rule", "rules", "src", "unk", "after", "scope", "actor", "role", "status", "kind",
    "t", "subject", "origin", "aer", "mode", "unit", "dialect", "adapter", "profile", "canon", "hash", "ns", "ex",
    "source_key", "artifacts", "call", "occ", "at", "pass", "seq", "n_records", "records_sha256", "accounting",
    "issues", "code", "version",
})  # fmt: skip
_PLACEHOLDER_KEY: Final = "__placeholder__"


def compact(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def field_display(name: str, value: Any, *, structural: bool, show: bool, locator: str, limit: int) -> str:
    """One field as a pane shows it: structure escaped as a line; content as a placeholder, or fenced when shown."""
    text = compact(value)
    if structural or (isinstance(value, str | int | float | bool) and not T.is_content_value(value)) or value is None:
        return T.line(text, 400)
    if not show:
        return T.content_digest_label(text)
    return T.fenced(text, f"{locator}/{name}", limit)


def fill_rows(table: QTableWidget, rows: Iterable[Iterable[str]]) -> None:
    rows = [list(r) for r in rows]
    table.setRowCount(len(rows))
    for i, row in enumerate(rows):
        for j, s in enumerate(row):
            item = QTableWidgetItem(s)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            table.setItem(i, j, item)


def _table(headers: list[str], name: str, parent: QWidget) -> QTableWidget:
    table = QTableWidget(0, len(headers), parent)
    table.setAccessibleName(name)
    table.setHorizontalHeaderLabels(headers)
    table.verticalHeader().setVisible(False)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.horizontalHeader().setStretchLastSection(True)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    return table


def _content_switch(parent: QWidget, pane: str, slot: Callable[[bool], None]) -> QCheckBox:
    cb = QCheckBox("Show content (this pane only; escaped, fenced, truncated)", parent)
    cb.setAccessibleName(f"Show content in the {pane} pane")
    cb.toggled.connect(slot)
    return cb


# ----------------------------------------------------------------------------------------------- PROV-JSON
class ProvJsonTab(QWidget):
    """A lazily filled tree (document → bundles → sections → statements → attributes) and a raw-text pane that is
    filled only when Show content is on."""

    statement_selected = Signal(str)  # statement key, for syncing the graph

    def __init__(self, parent: QWidget | None = None, *, stacked: bool = False) -> None:
        """``stacked``: the tree above the raw text (beside the graph in an execution tab, D-841), else side by side."""
        super().__init__(parent)
        self.setAccessibleName("PROV-JSON")
        self.doc: dict[str, Any] | None = None
        self.raw = ""
        self.locator = ""
        self.limit = T.CONTENT_CHARS_DEFAULT
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.spec = QComboBox(self)
        self.spec.setAccessibleName("PROV specification")
        top.addWidget(self.spec)
        self.info = SafeLabel("", name="PROV document facts", parent=self)
        if stacked:  # narrow beside the graph: the facts get a wrapping line of their own
            top.addStretch(1)
        else:
            top.addWidget(self.info, 1)
        self.show_cb = _content_switch(self, "PROV-JSON", self._toggle)
        top.addWidget(self.show_cb)
        lay.addLayout(top)
        if stacked:
            self.info.setWordWrap(True)
            lay.addWidget(self.info)
        split = QSplitter(Qt.Orientation.Vertical if stacked else Qt.Orientation.Horizontal, self)
        self.tree = QTreeWidget(split)
        self.tree.setAccessibleName("PROV-JSON tree")
        self.tree.setHeaderLabels(["statement", "value"])
        self.tree.setColumnWidth(0, 360)
        self.tree.itemExpanded.connect(self._expand)
        self.tree.currentItemChanged.connect(self._current)
        self.text = ReadOnlyText(name="PROV-JSON text", parent=split)
        split.addWidget(self.tree)
        split.addWidget(self.text)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        lay.addWidget(split, 1)
        self._docs: dict[str, tuple[dict[str, Any], str, str, int]] = {}
        self.spec.currentTextChanged.connect(self._show_spec)

    def set_documents(self, docs: Mapping[str, tuple[dict[str, Any], str, str, int]], limit: int) -> None:
        """``docs``: spec -> (parsed document, file text, locator, size)."""
        self.limit = limit
        self._docs = dict(docs)
        self.show_cb.setChecked(False)
        self.spec.blockSignals(True)
        self.spec.clear()
        self.spec.addItems(sorted(self._docs))
        self.spec.blockSignals(False)
        self._show_spec(self.spec.currentText())

    def _show_spec(self, spec: str) -> None:
        self.tree.clear()
        self.text.clear()
        if spec not in self._docs:
            self.doc = None
            self.info.set_plain("No PROV output for this execution.")
            return
        self.doc, self.raw, self.locator, size = self._docs[spec]
        bundles = self.doc.get("bundle", {}) if isinstance(self.doc.get("bundle"), dict) else {}
        self.info.set_plain(f"{size:,} bytes · {len(bundles)} bundles · {T.line(self.locator, 120)}")
        root = QTreeWidgetItem(self.tree, ["document", ""])
        top_sections = {k: v for k, v in self.doc.items() if k not in ("bundle", "prefix") and isinstance(v, dict)}
        prefix = self.doc.get("prefix", {})
        p = QTreeWidgetItem(root, [f"prefix ({len(prefix) if isinstance(prefix, dict) else 0})", ""])
        if isinstance(prefix, dict):
            for k in sorted(prefix):
                row = QTreeWidgetItem(p, [T.line(k, 80), self._prefix(k, prefix[k])])
                row.setData(0, Qt.ItemDataRole.UserRole, ("prefix", (k, prefix[k])))  # for _toggle
        top = QTreeWidgetItem(root, [f"top level ({sum(len(v) for v in top_sections.values())} statements)", ""])
        self._sections(top, top_sections)
        for iri in sorted(bundles):
            body = bundles[iri]
            kind = "core" if ".core." in iri else "inference" if ".inf." in iri else "assessment" if ".assess." in iri else ""
            b = QTreeWidgetItem(root, [f"bundle {T.line(iri, 120)}", f"[{kind}]" if kind else ""])
            if isinstance(body, dict):
                self._sections(b, {k: v for k, v in body.items() if isinstance(v, dict) and k != "prefix"})
        root.setExpanded(True)
        self._toggle(self.show_cb.isChecked())

    def _sections(self, parent: QTreeWidgetItem, sections: Mapping[str, dict[str, Any]]) -> None:
        for name in sorted(sections):
            statements = sections[name]
            s = QTreeWidgetItem(parent, [f"{T.line(name, 60)} ({len(statements)})", ""])
            s.setData(0, Qt.ItemDataRole.UserRole, ("section", statements))
            QTreeWidgetItem(s, [_PLACEHOLDER_KEY, ""])  # makes it expandable

    def _expand(self, item: QTreeWidgetItem) -> None:
        payload = item.data(0, Qt.ItemDataRole.UserRole)
        first = item.child(0) if item.childCount() == 1 else None
        if not payload or first is None or first.text(0) != _PLACEHOLDER_KEY:
            return
        item.takeChild(0)
        kind, value = payload
        if kind == "section":
            for key in sorted(value)[:20000]:
                attrs = value[key]
                st = QTreeWidgetItem(item, [T.line(key, 160), self._summary(attrs)])
                st.setData(0, Qt.ItemDataRole.UserRole, ("statement", (key, attrs)))
                QTreeWidgetItem(st, [_PLACEHOLDER_KEY, ""])
        elif kind == "statement":
            key, attrs = value
            for name, v in sorted(attrs.items()) if isinstance(attrs, dict) else ():
                row = QTreeWidgetItem(item, [T.line(name, 80), self._attr(name, v, key)])
                row.setData(0, Qt.ItemDataRole.UserRole, ("attr", name))  # the raw name, for _toggle

    def _summary(self, attrs: Any) -> str:
        """The statement's type QNames and rule id: ``render.style``'s trusted grammars or a fixed placeholder, never
        content (S2), so the Show content switch does not apply to it."""
        if not isinstance(attrs, dict):
            return ""
        types = attrs.get("prov:type")
        rule = attrs.get("apv:rule")
        bits = []
        if types is not None:
            bits.append(T.line(", ".join(style.qnames(types)) or "(type)", 120))
        if isinstance(rule, str):
            bits.append(style.token(rule, style._RULE_RE, "(rule)"))
        return " · ".join(bits)

    def _attr(self, name: str, value: Any, key: str) -> str:
        """Metadata as one line; content as a placeholder, or fenced with its locator when shown (S2), so the
        tree's own Copy keeps the fence (S13)."""
        if not T.is_content_value(value):
            return T.line(T.plain_value(value), self.limit)
        if not self.show_cb.isChecked():
            return T.content_digest_label(T.plain_value(value))
        return T.fenced(T.plain_value(value), f"{self.locator}#{key}/{name}", self.limit)

    def _prefix(self, name: str, value: Any) -> str:
        """A prefix value: an IRI as one line; anything else is content, a placeholder or fenced when shown (GR-55)."""
        if T.is_iri(value):
            return T.line(value, 200)
        if not self.show_cb.isChecked():
            return T.content_digest_label(compact(value))
        return T.fenced(compact(value), f"{self.locator}#prefix/{name}", self.limit)

    def _current(self, item: QTreeWidgetItem | None, _prev: QTreeWidgetItem | None) -> None:
        payload = item.data(0, Qt.ItemDataRole.UserRole) if item is not None else None
        if payload and payload[0] == "statement":
            self.statement_selected.emit(payload[1][0])

    def _toggle(self, on: bool) -> None:
        if on and self.doc is not None:
            self.text.setPlainText(T.fenced_display(self.raw, self.doc, self.locator))
        else:
            self.text.setPlainText("Content is hidden. Turn on “Show content” to read this document's text "
                                   "(escaped and fenced as data).")
        # refresh every built attribute row, collapsed statements included (_expand does not rebuild them), by the
        # raw name kept on the row: the shown name is escaped and truncated (GR-53); and every prefix value (GR-55)
        for item in self._iter_items():
            payload = item.data(0, Qt.ItemDataRole.UserRole)
            if payload and payload[0] == "prefix":
                item.setText(1, self._prefix(*payload[1]))
            elif payload and payload[0] == "statement":
                key, attrs = payload[1]
                for i in range(item.childCount()):
                    child = item.child(i)
                    row = child.data(0, Qt.ItemDataRole.UserRole) if child is not None else None
                    if child is None or not row or row[0] != "attr":
                        continue
                    name = row[1]
                    if isinstance(attrs, dict) and name in attrs:
                        child.setText(1, self._attr(name, attrs[name], key))

    def _iter_items(self) -> Iterable[QTreeWidgetItem]:
        stack = [self.tree.topLevelItem(i) for i in range(self.tree.topLevelItemCount())]
        while stack:
            item = stack.pop()
            if item is None:
                continue
            yield item
            stack.extend(item.child(i) for i in range(item.childCount()))

    def reveal(self, key: str) -> bool:
        """Select the statement ``key`` (expanding its section on demand)."""
        for item in list(self._iter_items()):
            payload = item.data(0, Qt.ItemDataRole.UserRole)
            if payload and payload[0] == "section" and key in payload[1]:
                item.setExpanded(True)
                for i in range(item.childCount()):
                    child = item.child(i)
                    p = child.data(0, Qt.ItemDataRole.UserRole) if child is not None else None
                    if child is not None and p and p[1][0] == key:
                        self.tree.setCurrentItem(child)
                        self.tree.scrollToItem(child)
                        return True
        return False


# ----------------------------------------------------------------------------------------------- AER
class AerTab(QWidget):
    """Records grouped by kind; the selected record's fields at the right."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAccessibleName("AER")
        self.aer: AerDocument | None = None
        self.locator = ""
        self.limit = T.CONTENT_CHARS_DEFAULT
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.info = SafeLabel("", name="AER facts", parent=self)
        top.addWidget(self.info, 1)
        self.show_cb = _content_switch(self, "AER", lambda _on: self._refresh())
        top.addWidget(self.show_cb)
        lay.addLayout(top)
        split = QSplitter(Qt.Orientation.Horizontal, self)
        self.tree = QTreeWidget(split)
        self.tree.setAccessibleName("AER records")
        self.tree.setHeaderLabels(["id", "kind", "ev", "by", "rule", "src", "unk", "after"])
        self.tree.currentItemChanged.connect(lambda *_: self._refresh())
        self.fields = _table(["field", "value"], "AER record fields", split)
        split.addWidget(self.tree)
        split.addWidget(self.fields)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        lay.addWidget(split, 1)

    def set_document(self, aer: AerDocument | None, locator: str, limit: int, error: str | None) -> None:
        self.aer, self.locator, self.limit = aer, locator, limit
        self.show_cb.setChecked(False)
        self.tree.clear()
        self.fields.setRowCount(0)
        if aer is None:
            self.info.set_plain(f"The AER cannot be shown ({T.line(error or 'missing', 80)}).")
            return
        self.info.set_plain(
            f"{len(aer.records)} records · execution digest {aer.execution_digest[:16]}… · file sha256 "
            f"{aer.file_sha256[:16]}… · seal: {T.line(compact(aer.seal.get('n_records')), 20)} records"
        )
        groups: dict[str, list[dict[str, Any]]] = {}
        for rec in aer.records:
            groups.setdefault(str(rec.get("k")), []).append(rec)
        for kind in sorted(groups):
            g = QTreeWidgetItem(self.tree, [f"{T.line(kind, 40)} ({len(groups[kind])})", "", "", "", "", "", "", ""])
            for rec in groups[kind]:
                cols = [rec.get("id"), rec.get("k"), rec.get("ev"), rec.get("by"), rec.get("rule"), rec.get("src"),
                        rec.get("unk"), rec.get("after")]
                item = QTreeWidgetItem(g, [T.line(compact(c), 120) if c is not None else "" for c in cols])
                item.setData(0, Qt.ItemDataRole.UserRole, rec)
            g.setExpanded(len(groups[kind]) <= 50)
        seal = QTreeWidgetItem(self.tree, ["seal", "seal", "", "", "", "", "", ""])
        seal.setData(0, Qt.ItemDataRole.UserRole, aer.seal)
        for i in range(self.tree.columnCount()):
            self.tree.resizeColumnToContents(i)

    def _refresh(self) -> None:
        item = self.tree.currentItem()
        rec = item.data(0, Qt.ItemDataRole.UserRole) if item is not None else None
        if not isinstance(rec, dict):
            self.fields.setRowCount(0)
            return
        rid = compact(rec.get("id", "seal"))
        loc = f"{self.locator}#{rid}"
        shown = self.show_cb.isChecked()
        rows = [
            (T.line(k, 80), field_display(k, rec[k], structural=k in AER_STRUCTURE, show=shown, locator=loc,
                                          limit=self.limit))
            for k in sorted(rec)
        ]
        fill_rows(self.fields, rows)
        self.fields.resizeColumnToContents(0)
        self.fields.resizeRowsToContents()


# ----------------------------------------------------------------------------------------------- SEM
class SemTab(QWidget):
    HEADERS: Final = ["id", "target", "type", "value", "ev", "rule", "premises", "method", "confidence"]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAccessibleName("SEM")
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.profile = QComboBox(self)
        self.profile.setAccessibleName("Semantics profile")
        self.profile.currentTextChanged.connect(self._show)
        top.addWidget(self.profile)
        self.info = SafeLabel("", name="SEM facts", parent=self)
        top.addWidget(self.info, 1)
        lay.addLayout(top)
        self.table = _table(self.HEADERS, "SEM annotations", self)
        lay.addWidget(self.table, 1)
        self.docs: dict[str, SemDocument] = {}
        self.errors: dict[str, str] = {}

    def set_documents(self, docs: Mapping[str, SemDocument], errors: Mapping[str, str]) -> None:
        self.docs, self.errors = dict(docs), dict(errors)
        self.profile.blockSignals(True)
        self.profile.clear()
        self.profile.addItems(sorted(set(self.docs) | set(self.errors)))
        self.profile.blockSignals(False)
        self._show(self.profile.currentText())

    def _show(self, profile: str) -> None:
        doc = self.docs.get(profile)
        if doc is None:
            self.table.setRowCount(0)
            code = self.errors.get(profile)
            self.info.set_plain(f"Not available ({T.line(code, 80)})." if code else "No SEM output for this execution.")
            return
        annotations = [r for r in doc.records if r.get("k") != "header" and r is not doc.header]
        self.info.set_plain(f"{len(annotations)} annotations · SEM digest {doc.digest[:16]}…")
        fill_rows(self.table, ([T.line(compact(a.get(h)), 200) if a.get(h) is not None else "" for h in self.HEADERS]
                               for a in annotations))
        self.table.resizeColumnsToContents()


# ----------------------------------------------------------------------------------------------- register, validation
class RegisterTab(QWidget):
    HEADERS: Final = ["code", "severity", "stage", "disposition", "rule", "detail", "ids", "owner"]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAccessibleName("Register")
        lay = QVBoxLayout(self)
        self.info = SafeLabel("", name="Register facts", parent=self)
        lay.addWidget(self.info)
        self.table = _table(self.HEADERS, "Register entries for this execution", self)
        lay.addWidget(self.table, 1)

    def set_entries(self, entries: list[RegisterEntry], error: str | None) -> None:
        if error:
            self.info.set_plain(f"The register cannot be read ({T.line(error, 80)}).")
        else:
            self.info.set_plain(f"{len(entries)} entries for this execution")
        fill_rows(self.table, (
            [T.line(e.code), e.severity, e.stage, e.disposition, T.line(e.rule or ""), T.line(e.detail, 200),
             T.line(", ".join(e.ids), 200), T.line(compact(dict(e.owner)) if e.owner else "", 120)]
            for e in entries
        ))  # fmt: skip
        self.table.resizeColumnsToContents()


class ValidationTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAccessibleName("Validation")
        lay = QVBoxLayout(self)
        self.info = SafeLabel("", name="Validation facts", parent=self)
        lay.addWidget(self.info)
        self.table = _table(["check", "result", "detail"], "Validation checks", self)
        lay.addWidget(self.table, 1)

    def set_row(self, row: Mapping[str, Any] | None, error: str | None) -> None:
        if row is None:
            self.table.setRowCount(0)
            self.info.set_plain(f"Not available ({T.line(error, 80)})." if error else "No validation row for this execution.")
            return
        self.info.set_plain(
            f"verdict {T.line(compact(row.get('verdict')), 40)} · spec {T.line(compact(row.get('spec')), 60)} · "
            f"versions {T.line(compact(row.get('versions')), 200)}"
        )
        checks = row.get("checks")
        rows: list[list[str]] = []
        if isinstance(checks, dict):
            for name in sorted(checks):
                v = checks[name]
                result = v.get("result", v.get("status", v.get("outcome"))) if isinstance(v, dict) else v
                rest = {k: x for k, x in v.items() if k not in ("result", "status", "outcome")} if isinstance(v, dict) else {}
                rows.append([T.line(name, 80), T.line(compact(result), 40), T.line(compact(rest) if rest else "", 300)])
        elif isinstance(checks, list):
            for v in checks:
                if isinstance(v, dict):
                    name = v.get("id", v.get("check", v.get("name")))
                    result = v.get("result", v.get("status", v.get("outcome", v.get("failed"))))
                    rest = {k: x for k, x in v.items() if k not in ("id", "check", "name", "result", "status", "outcome")}
                    rows.append([T.line(compact(name), 80), T.line(compact(result), 40), T.line(compact(rest), 300)])
        fill_rows(self.table, rows)
        self.table.resizeColumnsToContents()
