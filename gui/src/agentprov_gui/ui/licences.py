"""Licences (design §6.5; wireframe 06; macos-design §3.3 "Licences"). Read-only.

* **Included:** one row per registry source (``adapters.registry``): SPDX, policy, data licence, restrictions, part
  statuses, and computed flags, each with the rule behind it (shown in the detail pane):
  - **copyleft**: the SPDX id matches ``^(A?GPL|LGPL)-[0-9.]+(-only|-or-later)?$`` (the rule of
    ``release/metadata.py``, which the GUI may not import: D-391);
  - **NC**: ``(^|-)NC(-|$)`` (same source);
  - **restricted**: the registry lists restrictions.
  Systematic-search records join by name or URL; unmatched rows say "unmatched" and are never guessed.
* **Excluded:** the systematic search's excluded records with their criterion codes, from
  ``docs/reports/systematic-search/records-merged.csv`` of the configured checkout (parsed with the stdlib ``csv``
  module under a size limit; every cell escaped).

Changing a licence is a registry or profile change made in code review, never here.
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import Final

from agentprov.adapters.registry import REGISTRY, SourceRegistration
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QSplitter, QTableWidget, QTabWidget, QVBoxLayout, QWidget

from agentprov_gui import text as T
from agentprov_gui.ui.detail import fill_rows
from agentprov_gui.ui.safe import (
    ReadOnlyText,
    SafeLabel,
    set_control_tooltip,
    set_header_tooltips,
    set_tab_tooltip,
)

__all__ = ["LicencesPage", "flags_of", "search_records"]

COPYLEFT: Final = re.compile(r"^(A?GPL|LGPL)-[0-9.]+(-only|-or-later)?$", re.IGNORECASE)
NC: Final = re.compile(r"(^|-)NC(-|$)", re.IGNORECASE)
RECORDS: Final = Path("docs/reports/systematic-search/records-merged.csv")
MAX_CSV_BYTES: Final = 16 * 1024 * 1024
INCLUDED_TIPS: Final = (
    "The source's id in the AgentPROV source registry.",
    "The SPDX licence id of the source; — when the registry records none.",
    "The registry licence policy: include (raw bytes stored in the corpus), reference (listed by digest and pinned "
    "origin, not stored), nc_partition (only in a separately licensed non-commercial corpus) or forbidden (withheld).",
    "An explicit licence for the source's data, if any: none when there is no separate data licence; — when the "
    "registry records nothing.",
    "copyleft (a GPL-family SPDX id), NC (a non-commercial term) and restricted (the registry lists restrictions). The "
    "details below give the rule behind each flag.",
    "Each part of the source with its import status (else its live status): supported, partial, planned or "
    "not_possible.",
    "The decision of the matching systematic-search record, joined by name or URL; unmatched when none matches (never "
    "guessed).",
)
EXCLUDED_TIPS: Final = (
    "The record's id in the systematic search.",
    "The name of the excluded source.",
    "The licence the systematic search recorded for it.",
    "The exclusion criterion code that excluded it (for example EX-NOLOG or EX-LIC-1).",
    "Other exclusion codes that also apply.",
    "The systematic search's notes on the record.",
)


def flags_of(source: SourceRegistration) -> list[tuple[str, str]]:
    """(flag, the rule that set it)."""
    spdx = source.licence.spdx or ""
    out = []
    if COPYLEFT.match(spdx):
        out.append(("copyleft", f"SPDX {spdx} matches the copyleft rule of release/metadata.py"))
    if NC.search(spdx):
        out.append(("NC", f"SPDX {spdx} carries a non-commercial term"))
    if source.licence.restrictions:
        out.append(("restricted", f"{len(source.licence.restrictions)} restriction(s) in the registry"))
    return out


def search_records(checkout: Path | None) -> list[dict[str, str]]:
    if checkout is None:
        return []
    path = checkout / RECORDS
    try:
        if path.stat().st_size > MAX_CSV_BYTES:
            return []
        data = path.read_bytes().decode("utf-8", "replace")
    except OSError:
        return []
    return [dict(r) for r in csv.DictReader(io.StringIO(data))]


def _table(headers: list[str], name: str, parent: QWidget) -> QTableWidget:
    t = QTableWidget(0, len(headers), parent)
    t.setAccessibleName(name)
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().setVisible(False)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.horizontalHeader().setStretchLastSection(True)
    t.setSortingEnabled(True)
    return t


class LicencesPage(QWidget):
    def __init__(self, checkout: Path | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAccessibleName("Licences")
        self.checkout = checkout
        lay = QVBoxLayout(self)
        lay.addWidget(SafeLabel("Read-only. A licence changes only through the registry or a profile, in code review.",
                                name="Licences note", parent=self))
        tabs = QTabWidget(self)
        tabs.setAccessibleName("Licence views")
        lay.addWidget(tabs, 1)
        inc = QSplitter(Qt.Orientation.Vertical, tabs)
        self.included = _table(["source", "SPDX", "policy", "data licence", "flags", "parts", "search record"],
                               "Included sources", inc)
        set_header_tooltips(self.included, INCLUDED_TIPS)
        set_control_tooltip(self.included, "Every source in the registry; select one to show its licence details "
                                           "below. Click a column header to sort.")
        self.included.currentCellChanged.connect(self._detail)
        self.detail = ReadOnlyText(name="Licence details", parent=inc, wrap=True)
        set_control_tooltip(self.detail, "The selected source's licence: SPDX id, policy, basis, holders, "
                                         "restrictions, attribution, what is unassessed, and the rule behind each "
                                         "flag.")
        inc.addWidget(self.included)
        inc.addWidget(self.detail)
        tabs.addTab(inc, "Included")
        set_tab_tooltip(tabs, 0, "Every registered source with its SPDX id, licence policy, data licence, flags and "
                                 "parts (agentprov info SOURCE).", wrap=True)
        exc = QWidget(tabs)
        el = QVBoxLayout(exc)
        self.excluded_info = SafeLabel("", name="Excluded facts", parent=exc)
        el.addWidget(self.excluded_info)
        self.excluded = _table(["record", "name", "licence", "exclusion code", "other codes", "notes"],
                               "Excluded records", exc)
        set_header_tooltips(self.excluded, EXCLUDED_TIPS)
        set_control_tooltip(self.excluded, "The systematic search's excluded records, from records-merged.csv in the "
                                           "checkout. Click a column header to sort.")
        el.addWidget(self.excluded)
        tabs.addTab(exc, "Excluded")
        set_tab_tooltip(tabs, 1, "The records the systematic search excluded, with their exclusion codes (from the "
                                 "checkout's docs/reports/systematic-search/records-merged.csv).", wrap=True)
        self.reload()

    def reload(self) -> None:
        records = search_records(self.checkout)
        by_name = {r.get("name", "").lower(): r for r in records}
        by_url = {r.get("url", "").lower().rstrip("/"): r for r in records}
        rows = []
        self._sources = list(REGISTRY)
        for s in self._sources:
            parts = ", ".join(f"{c.part}:{c.import_status or c.live_status or '-'}" for c in s.capabilities)
            match = by_name.get(s.name.lower())
            if match is None:
                match = next((r for u, r in by_url.items() if u and u in " ".join(s.evidence_refs).lower()), None)
            rows.append([T.line(s.source_id), T.line(s.licence.spdx or "—"), T.line(s.licence.policy),
                         T.line(s.licence.data_licence or "—"), ", ".join(f for f, _ in flags_of(s)) or "—",
                         T.line(parts, 300), T.line(match.get("decision", "") if match else "unmatched")])
        self.included.setSortingEnabled(False)
        fill_rows(self.included, rows)
        self.included.setSortingEnabled(True)
        self.included.resizeColumnsToContents()
        excluded = [r for r in records if r.get("decision") == "excluded"]
        self.excluded_info.set_plain(f"{len(excluded)} excluded records from the systematic search"
                                     if records else "The systematic-search records are not available (no checkout).")
        fill_rows(self.excluded, ([T.line(r.get("id"), 80), T.line(r.get("name"), 80), T.line(r.get("licence"), 60),
                                   T.line(r.get("exclusion_code"), 40), T.line(r.get("other_applicable_codes"), 80),
                                   T.line(r.get("notes"), 200)] for r in excluded))

    def _detail(self, row: int, *_: int) -> None:
        item = self.included.item(row, 0)
        if item is None:
            return
        source = next((s for s in self._sources if T.line(s.source_id) == item.text()), None)
        if source is None:
            return
        lic = source.licence
        lines = [f"{source.source_id}: {source.name}", f"SPDX: {lic.spdx}", f"policy: {lic.policy}",
                 f"basis: {lic.basis}", "holders: " + "; ".join(lic.holders),
                 "restrictions: " + ("; ".join(lic.restrictions) or "none"),
                 "attribution: " + "; ".join(lic.attribution), "unassessed: " + "; ".join(lic.unassessed)]
        lines += [f"flag {f}: {why}" for f, why in flags_of(source)]
        self.detail.setPlainText(T.multiline("\n".join(lines), 20000))
