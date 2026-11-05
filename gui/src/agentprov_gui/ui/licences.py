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

House style (D-1060): the page title with a badge saying whether the systematic-search records were found, tables in
cards with plain-language column headers, the selected source's policy and flags as status badges above its details,
and the terminal command card: ``agentprov info SOURCE`` (every source without a selection), built by the ``info`` form
(:func:`commands_for`). The excluded records have no CLI equivalent (they are a report of the checkout).
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import Final

from agentprov.adapters.registry import REGISTRY, SourceRegistration
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QSplitter,
    QTableWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from agentprov_gui import text as T
from agentprov_gui.jobs.commands import FORMS, build_spec
from agentprov_gui.ui.brand import command_card, page_layout
from agentprov_gui.ui.detail import fill_rows
from agentprov_gui.ui.forms import FormSection, StatusBadge, caption
from agentprov_gui.ui.safe import (
    ReadOnlyText,
    SafeLabel,
    set_control_tooltip,
    set_header_tooltips,
    set_tab_tooltip,
)

__all__ = ["LicencesPage", "commands_for", "flags_of", "policy_kind", "search_records"]

INCLUDED_HEADERS: Final = ("Source", "SPDX licence", "Policy", "Data licence", "Flags", "Parts", "Search decision")
EXCLUDED_HEADERS: Final = ("Record", "Name", "Licence", "Exclusion code", "Other codes", "Notes")
#: a licence policy's badge kind: stored, referenced, a separate corpus, withheld
_POLICY_KINDS: Final = {"include": "ok", "reference": "info", "nc_partition": "warn", "forbidden": "bad"}

COPYLEFT: Final = re.compile(r"^(A?GPL|LGPL)-[0-9.]+(-only|-or-later)?$", re.IGNORECASE)
NC: Final = re.compile(r"(^|-)NC(-|$)", re.IGNORECASE)
RECORDS: Final = Path("docs/reports/systematic-search/records-merged.csv")
MAX_CSV_BYTES: Final = 16 * 1024 * 1024
INCLUDED_TIPS: Final = (
    "The source's id in the AgentPROV source registry (source_id).",
    "The SPDX licence id of the source (licence.spdx); — when the registry records none.",
    "The registry licence policy (licence.policy): include (raw bytes stored in the corpus), reference (listed by "
    "digest and pinned origin, not stored), nc_partition (only in a separately licensed non-commercial corpus) or "
    "forbidden (withheld).",
    "An explicit licence for the source's data (licence.data_licence), if any: none when there is no separate data "
    "licence; — when the registry records nothing.",
    "copyleft (a GPL-family SPDX id), NC (a non-commercial term) and restricted (the registry lists restrictions). The "
    "details below give the rule behind each flag.",
    "Each part of the source with its import status (else its live status): supported, partial, planned or "
    "not_possible.",
    "The decision of the matching systematic-search record, joined by name or URL; unmatched when none matches (never "
    "guessed).",
)
#: a licence flag's badge: what it means and what to check (the rules are those of :func:`flags_of`)
FLAG_TIPS: Final = {
    "copyleft": "Copyleft: the source's SPDX id is a GPL-family licence (the copyleft rule of release/metadata.py). "
                "Read the licence details below before a release.",
    "NC": "Non-commercial: the source's SPDX id carries a non-commercial term. Read the licence details and the policy "
          "below before a release.",
    "restricted": "Restricted: the registry lists restrictions on this source. The licence details below name them; "
                  "read them before a release.",
}
EXCLUDED_TIPS: Final = (
    "The record's id in the systematic search (the id column of records-merged.csv).",
    "The name of the excluded source.",
    "The licence the systematic search recorded for it.",
    "The exclusion criterion code that excluded it, for example EX-NOLOG or EX-LIC-1 (exclusion_code).",
    "Other exclusion codes that also apply (other_applicable_codes).",
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


def policy_kind(policy: str) -> str:
    """The badge kind of a licence policy (an unknown one is neutral)."""
    return _POLICY_KINDS.get(policy, "neutral")


def commands_for(source_id: str | None) -> list[tuple[str, tuple[str, ...]]]:
    """The terminal command of what the Included tab shows, from the ``info`` form: one source's parts, profiles, pins
    and licence, or (``None``) the whole registry."""
    if source_id is None:
        return [("every registered source", build_spec(FORMS["info"], {"format": "text"}).argv)]
    return [("this source's parts, profiles, pins and licence",
             build_spec(FORMS["info"], {"source": source_id, "format": "text"}).argv)]


def _table(headers: list[str] | tuple[str, ...], name: str, parent: QWidget) -> QTableWidget:
    t = QTableWidget(0, len(headers), parent)
    t.setAccessibleName(name)
    t.setHorizontalHeaderLabels(list(headers))
    t.verticalHeader().setVisible(False)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.horizontalHeader().setStretchLastSection(True)
    t.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    t.setFrameShape(QFrame.Shape.NoFrame)
    t.setShowGrid(False)
    t.setSortingEnabled(True)
    return t


def _tab_page(parent: QWidget) -> tuple[QWidget, QVBoxLayout]:
    """A tab's page on the page background, with the style's spacing."""
    page = QWidget(parent)
    page.setProperty("apvRole", "page")
    page.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    lay = QVBoxLayout(page)
    lay.setContentsMargins(0, 12, 0, 0)
    lay.setSpacing(12)
    return page, lay


class LicencesPage(QWidget):
    def __init__(self, checkout: Path | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAccessibleName("Licences")
        self.checkout = checkout
        lay, head, _note = page_layout(self, "Licences", caption_name="Licences note", caption_text=(
            "Read-only. A licence changes only through the registry or a profile, in code review."))
        self.records_badge = StatusBadge("", name="Systematic-search records", parent=self)
        set_control_tooltip(self.records_badge, "Whether the checkout's systematic-search records were found: they "
                                                "fill the Search decision column and the Excluded tab.")
        head.addWidget(self.records_badge)
        tabs = QTabWidget(self)
        tabs.setAccessibleName("Licence views")
        tabs.setDocumentMode(True)
        tabs.tabBar().setDrawBase(False)
        lay.addWidget(tabs, 1)
        # Included: the registry's sources; the selected one's licence below, with its terminal command
        inc_page, inc_lay = _tab_page(tabs)
        inc = QSplitter(Qt.Orientation.Vertical, inc_page)
        inc.setChildrenCollapsible(False)
        sources = FormSection("Registered sources", parent=inc)
        self.included = _table(INCLUDED_HEADERS, "Included sources", sources.card)
        set_header_tooltips(self.included, INCLUDED_TIPS)
        set_control_tooltip(self.included, "Every source in the registry; select one to show its licence details "
                                           "below. Click a column header to sort.")
        self.included.currentCellChanged.connect(self._detail)
        sources.add(self.included)
        inc.addWidget(sources)
        below = QWidget(inc)
        below_lay = QHBoxLayout(below)
        below_lay.setContentsMargins(0, 12, 0, 0)
        below_lay.setSpacing(18)
        chosen = FormSection("Selected source", parent=below)
        badges = QWidget(chosen.card)
        badge_row = QHBoxLayout(badges)
        badge_row.setContentsMargins(0, 0, 0, 0)
        badge_row.setSpacing(6)
        self.source_title = SafeLabel("", name="Selected source name", parent=badges)
        badge_row.addWidget(self.source_title, 1)
        self.policy_badge = StatusBadge("", name="Licence policy", parent=badges)
        set_control_tooltip(self.policy_badge, INCLUDED_TIPS[2])
        badge_row.addWidget(self.policy_badge)
        self.flag_badges = {flag: StatusBadge("", name=f"Flag {flag}", kind="warn", parent=badges)
                            for flag in ("copyleft", "NC", "restricted")}
        for flag, badge in self.flag_badges.items():
            set_control_tooltip(badge, FLAG_TIPS[flag])
            badge_row.addWidget(badge)
        self.no_flags = StatusBadge("", name="No flags", kind="ok", parent=badges)
        set_control_tooltip(self.no_flags, "No licence flag applies to this source: its SPDX id is neither "
                                           "copyleft nor non-commercial, and the registry lists no restrictions.")
        badge_row.addWidget(self.no_flags)
        chosen.add(badges)
        self.detail = ReadOnlyText(name="Licence details", parent=chosen.card, wrap=True)
        self.detail.setFrameShape(QFrame.Shape.NoFrame)
        self.detail.setPlaceholderText("Select a source above to see its licence.")
        set_control_tooltip(self.detail, "The selected source's licence: SPDX id, policy, basis, holders, "
                                         "restrictions, attribution, what is unassessed, and the rule behind each "
                                         "flag.")
        chosen.add(self.detail)
        below_lay.addWidget(chosen, 3)
        self.command_card = command_card(below)
        below_lay.addWidget(self.command_card, 2, Qt.AlignmentFlag.AlignTop)
        inc.addWidget(below)
        inc.setStretchFactor(0, 3)
        inc.setStretchFactor(1, 2)
        inc_lay.addWidget(inc, 1)
        tabs.addTab(inc_page, "Included")
        set_tab_tooltip(tabs, 0, "Every registered source with its SPDX id, licence policy, data licence, flags and "
                                 "parts (agentprov info SOURCE).", wrap=True)
        # Excluded: the systematic search's excluded records
        exc, el = _tab_page(tabs)
        self.excluded_info = caption("", name="Excluded facts", parent=exc)
        el.addWidget(self.excluded_info)
        excluded = FormSection("Excluded records", parent=exc)
        self.excluded = _table(EXCLUDED_HEADERS, "Excluded records", excluded.card)
        set_header_tooltips(self.excluded, EXCLUDED_TIPS)
        set_control_tooltip(self.excluded, "The systematic search's excluded records, from records-merged.csv in the "
                                           "checkout. Click a column header to sort.")
        excluded.add(self.excluded)
        el.addWidget(excluded, 1)
        tabs.addTab(exc, "Excluded")
        set_tab_tooltip(tabs, 1, "The records the systematic search excluded, with their exclusion codes (from the "
                                 "checkout's docs/reports/systematic-search/records-merged.csv).", wrap=True)
        self._show_source(None)
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
        self.records_badge.set_status("Search records found" if records else "No search records",
                                      "ok" if records else "warn")
        fill_rows(self.excluded, ([T.line(r.get("id"), 80), T.line(r.get("name"), 80), T.line(r.get("licence"), 60),
                                   T.line(r.get("exclusion_code"), 40), T.line(r.get("other_applicable_codes"), 80),
                                   T.line(r.get("notes"), 200)] for r in excluded))

    def _show_source(self, source: SourceRegistration | None) -> None:
        """The selected source's title, its policy and flags as badges (words with a tint), and its terminal
        command."""
        self.command_card.set_commands(commands_for(source.source_id if source is not None else None))
        if source is None:
            self.source_title.set_plain("No source selected")
            self.policy_badge.set_status("")
            for badge in self.flag_badges.values():
                badge.set_status("")
            self.no_flags.set_status("")
            return
        self.source_title.set_plain(f"{T.line(source.source_id, 80)}: {T.line(source.name, 120)}")
        policy = T.line(source.licence.policy, 40)
        self.policy_badge.set_status(f"Policy: {policy}", policy_kind(source.licence.policy))
        flags = {f for f, _ in flags_of(source)}
        for flag, badge in self.flag_badges.items():
            badge.set_status(flag if flag in flags else "", "warn")
        self.no_flags.set_status("" if flags else "No flags", "ok")

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
        self._show_source(source)
