"""Settings › Keys, Prices and Estimate (design §8.2, §8.3 as amended by D-650; D-655).

* **Keys:** whether a secure keychain is available (the helper's allowlisted back-end), and, per endpoint of the
  checkout's ``endpoints.toml``, whether its key variable is stored. **Store…** opens a password field; on OK the value
  is registered with the log redaction first, then handed to the helper, and the field is cleared. The GUI never reads
  a key back for display. Without an allowed back-end: "No secure keychain: keys cannot be stored; real-model runs
  from the GUI are disabled", and the CLI is the way.
* **Prices:** the shipped table's date, the newest refreshed snapshot, and per-model overrides (USD per million
  tokens, with the date entered), all through ``agentprov prices list|set|unset`` (D-701). Refreshing is a confirmed R2
  job (Runs › New Job › Refresh model prices: ``agentprov prices refresh --allow-network``).
* **Estimate:** the default assumptions used where neither an opened corpus nor the priors cover a suite and attack,
  stored as ``agentprov settings`` ``estimate.default.*`` (D-701, D-703).

Each pane is a page of the form style (D-1060) with its terminal command card at the bottom, built from the functions
the pane runs: the ``keys`` commands for the selected key (:mod:`live.keychain`'s argv; a key's value is read from
standard input, so it is never in a command), and the ``prices set|unset`` and ``settings set`` commands of the
pending changes, which OK runs.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any, ClassVar, Final

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from agentprov_gui import text as T
from agentprov_gui.jobs.manager import CliLocator
from agentprov_gui.live import keychain
from agentprov_gui.live.cli import call, last_line
from agentprov_gui.live.plan import PlanError, PriceTable, load_endpoints, parse_prices
from agentprov_gui.ui import forms, theme
from agentprov_gui.ui.forms import DecimalField, FormSection, StatusBadge, Switch
from agentprov_gui.ui.safe import (
    SafeLabel,
    ask,
    safe_message_box,
    set_control_tooltip,
    set_header_tooltips,
    set_setting_tooltip,
)
from agentprov_gui.ui.settings_panes import NOT_READ, command_card, settings_page
from agentprov_gui.ui.worker import run_off_ui, submit

__all__ = ["EstimatePane", "KeysPane", "PricesPane", "StoreKeyDialog"]

NO_KEYCHAIN: Final = ("No secure keychain: keys cannot be stored; real-model runs from the GUI are disabled. Use the "
                      "agentprov CLI with your own environment instead.")
ESTIMATE_PREFIX: Final = "estimate.default."
#: D-1062: the standing consent to the daily price refresh when Run Live opens (unset: on)
AUTO_REFRESH: Final = "prices.auto_refresh"
#: what the Prices and Estimate panes read (and show as their command while nothing changed)
PRICES_LIST: Final = ("prices", "list", "--format", "json")
SETTINGS_LIST: Final = ("settings", "list", "--format", "json")


def _follow(owner: QWidget, show: Any) -> QTimer:
    """A zero-delay single-shot timer that runs ``show`` after the current change (the card follows the form)."""
    timer = QTimer(owner)
    timer.setSingleShot(True)
    timer.setInterval(0)
    timer.timeout.connect(show)
    return timer


class StoreKeyDialog(QDialog):
    """A password field; the value never stays in the widget after OK or Cancel."""

    def __init__(self, name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Store {name}")
        self.setAccessibleName("Store a key")
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 16)
        lay.setSpacing(12)
        title = SafeLabel(f"Store {name}", name="Store key title", parent=self, selectable=False)
        title.setFont(theme.scaled_font("title"))
        lay.addWidget(title)
        lay.addWidget(forms.caption(f"{name}: stored in the OS keychain only (service agentprov). The CLI reads it "
                                    "from there when a live run starts (D-702), and it is never shown again.",
                                    name="Key explanation", parent=self, role="secondary"))
        sec = FormSection("", parent=self)
        self.field = QLineEdit(sec.card)
        self.field.setEchoMode(QLineEdit.EchoMode.Password)  # Qt disables copy and cut in password mode
        self.field.setAccessibleName(f"{name} value")
        sec.add_row("Key value", self.field, caption_text="Pasted or typed; hidden",
                    tip="The key's value. It goes to the OS keychain through agentprov keys set NAME --stdin (on "
                        "standard input, never as an argument) and is cleared from this field.")
        lay.addWidget(sec)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def take(self) -> str:
        value = self.field.text().strip()
        self.field.clear()
        return value


#: D-880: the Zenodo tokens of the draft-only uploader, as rows of Settings › Keys (the core's RELEASE_KEY_NAMES)
ZENODO_KEYS: Final = (("Zenodo sandbox (drafts only)", "ZENODO_SANDBOX_TOKEN"),
                      ("Zenodo production (drafts only)", "ZENODO_TOKEN"))


class KeysPane(QWidget):
    def __init__(self, store: Any, checkout: Path | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store, self.checkout = store, checkout
        from agentprov_gui.jobs.manager import CliLocator

        self.cli = CliLocator.for_checkout(checkout)  # D-702: agentprov keys of the configured checkout
        self.page = settings_page(self, "Keys", name="Keys settings")
        column = self.page.column
        sec = FormSection("Keychain", parent=column)
        self.badge = StatusBadge("Not checked", name="Keychain state", parent=sec.card)
        set_control_tooltip(self.badge, "Whether this computer has a secure OS keychain for the keys (agentprov keys "
                                        "status; Check Keychain asks again). Available: keys can be stored. No secure "
                                        "keychain or Check failed: no key can be stored here. Not checked: not asked "
                                        "yet.")
        self.check = QPushButton("Check Keychain", sec.card)
        self.check.setAccessibleName("Check the keychain")
        self.check.setAutoDefault(False)
        self.check.clicked.connect(self.refresh)
        sec.add_row("OS keychain", self.badge, trailing=[self.check], stretch=False,
                    caption_text="Only key names are read, never a value")
        self.status = forms.caption("Keychain: not checked yet", name="Keychain status", parent=sec.card,
                                    role="secondary")
        sec.add(self.status)
        self.page.add(sec)
        sec = FormSection("Keys", parent=column, note="Endpoint keys come from endpoints.toml; the Zenodo tokens are "
                                                      "for the draft-only uploader.")
        self.table = QTableWidget(0, 3, sec.card)
        self.table.setHorizontalHeaderLabels(["Endpoint", "Key variable", "Stored"])
        self.table.setAccessibleName("Endpoint keys")
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.setMinimumHeight(220)
        set_setting_tooltip(self.table, "Each endpoint's key variable and whether it is stored in the OS keychain "
                            "(not checked until Check Keychain). Select a row to store or delete its key.")
        set_header_tooltips(self.table, ["The endpoint (endpoints.toml) or uploader that uses the key.",
                                         "The key's variable name (api_key_env); the name, never the value.",
                                         "Whether the OS keychain holds it (agentprov keys list)."])
        sec.add(self.table)
        buttons = QWidget(sec.card)
        row = QHBoxLayout(buttons)
        row.setContentsMargins(0, 0, 0, 0)
        self.store_btn = QPushButton("Store Key…", buttons)
        self.store_btn.setAccessibleName("Store the selected key")
        self.delete_btn = QPushButton("Delete Key…", buttons)
        self.delete_btn.setAccessibleName("Delete the selected key")
        theme.mark_destructive(self.delete_btn)
        for b, slot, tip in ((self.store_btn, self.store_selected, "Stores a value for the selected key variable in "
                              "the OS keychain (service agentprov). The app never shows it again."),
                             (self.delete_btn, self.delete_selected, "Deletes the selected key from the OS keychain, "
                              "after asking.")):
            b.setAutoDefault(False)
            b.clicked.connect(slot)
            set_setting_tooltip(b, tip)
            row.addWidget(b)
        row.addStretch(1)
        sec.add(buttons)
        self.page.add(sec)
        set_setting_tooltip(self.check, "Asks the OS keychain which keys are stored (agentprov keys status, then keys "
                                        "list). Only key names are read, never a value.")
        self.command = command_card(column)
        self.page.add(self.command)
        self.names: list[str] = []
        self._fill({})
        self.table.currentCellChanged.connect(lambda *_a: self.show_command())
        self.show_command()
        if not self.cli.available:  # nothing to ask: say what to set
            from agentprov_gui.settings_client import NO_CLI

            self.status.set_plain(f"Keychain: not checked. {NO_CLI}")
            self.store_btn.setEnabled(False)

    def _state(self, text: str, kind: str) -> None:
        self.badge.set_status(text, kind)

    def commands(self) -> list[tuple[str, list[str]]]:
        """``agentprov keys`` as the pane runs it (:mod:`live.keychain`'s argv): the status, and for the selected
        key its store (the value on standard input, never an argument) and its delete (the app asks first)."""
        out = [("Is a secure keychain available (names only, never a value)", ["keys", *keychain.status_argv()])]
        name = self._selected()
        if name is not None:
            out += [(f"Store {name}: the value is read from standard input", ["keys", *keychain.store_argv(name)]),
                    (f"Delete {name} (the app asks first)", ["keys", *keychain.delete_argv(name)])]
        return out

    def show_command(self) -> None:
        self.command.set_commands(self.commands())

    def _fill(self, present: dict[str, bool]) -> None:
        eps = [e for e in load_endpoints(self.checkout).values() if e.api_key_env]
        rows: list[tuple[str, str]] = []
        for e in eps:
            assert e.api_key_env is not None
            rows.append((f"{e.name} (optional, local)" if e.local else e.name, e.api_key_env))  # D-827: oMLX's optional key
        rows += ZENODO_KEYS  # D-880: the draft-only uploader's tokens (agentprov keys accepts them)
        current = self.table.currentRow()
        self.table.setRowCount(len(rows))
        self.names = []
        for i, (label, name) in enumerate(rows):
            self.names.append(name)
            stored = present.get(name)
            for j, v in enumerate((label, name, "Not checked" if stored is None else ("Stored" if stored else
                                                                                     "Not stored"))):
                self.table.setItem(i, j, QTableWidgetItem(T.line(v, 80)))
        self.table.resizeColumnToContents(0)
        if 0 <= current < len(rows):
            self.table.setCurrentCell(current, 0)

    def refresh(self) -> None:
        try:  # AU-GUI-3: agentprov keys status and list run in the pool (the pane is disabled meanwhile)
            st = run_off_ui(self, lambda: keychain.status(self.cli))
        except keychain.KeychainError as exc:
            from agentprov_gui.settings_client import NO_CLI

            self.status.set_plain(f"Keychain: not checked. {NO_CLI}" if not self.cli.available else
                                  f"Keychain: the helper failed ({T.line(exc.code, 60)})")
            self._state("Not checked" if not self.cli.available else "Check failed",
                        "neutral" if not self.cli.available else "bad")
            return
        if not st.allowed:
            self.status.set_plain(NO_KEYCHAIN + (f" ({T.line(st.reason, 300)})" if st.reason else ""))
            self._state("No secure keychain", "warn")
            self.store_btn.setEnabled(False)
            return
        self.status.set_plain(f"Keychain: {T.line(st.backend or '', 60)} (allowed)")
        self._state("Available", "ok")
        try:
            names = sorted(set(self.names))
            self._fill(run_off_ui(self, lambda: keychain.present(self.cli, names)))
        except keychain.KeychainError as exc:
            self.status.set_plain(f"Keychain: {T.line(exc.code, 60)}")
            self._state("Check failed", "bad")

    def _selected(self) -> str | None:
        row = self.table.currentRow()
        return self.names[row] if 0 <= row < len(self.names) else None

    def store_selected(self) -> None:
        name = self._selected()
        if name is None:
            return
        dlg = StoreKeyDialog(name, self)
        accepted = bool(dlg.exec())
        value = dlg.take()
        if not accepted or not value:
            return
        from agentprov_gui.app import register_secret

        register_secret(value)  # GR-16/43: before anything could log it
        held = [value]  # AU-GUI-3: stored from the pool; the holder is emptied after
        try:
            run_off_ui(self, lambda: keychain.store(self.cli, name, held[0]))
        except keychain.KeychainError as exc:
            safe_message_box(self, "Key not stored", "The key was not stored.", informative=T.line(exc.code, 60)).exec()
        held.clear()
        del value
        self.refresh()

    def delete_selected(self) -> None:
        """``keys delete --yes`` only after the GUI's own confirmation (D-654); a failure is reported, never hidden."""
        name = self._selected()
        if name is None:
            return
        if not ask(self, "Delete Key", f"Delete {T.line(name, 64)} from the OS keychain?",
                   "Runs that need this key cannot start until it is stored again. Its value is not shown or kept."):
            return
        try:
            run_off_ui(self, lambda: keychain.delete(self.cli, name))
        except keychain.KeychainError as exc:
            safe_message_box(self, "Key not deleted", "The key was not deleted.", informative=T.line(exc.code, 60)).exec()
        self.refresh()

    def save(self) -> None:
        """Keys are stored at once by the helper; nothing is kept in the settings."""


class PricesPane(QWidget):
    """The price sources and the per-model overrides (``agentprov prices``; D-701)."""

    COLUMNS: Final = ("Model", "Input", "Cached input", "Output", "Cache write", "As of")
    COLUMN_TIPS: Final = ("The model as endpoint:model (the price table's key).",
                          "input $/M: USD per million input tokens.",
                          "cached input $/M: USD per million cached input tokens (empty: not priced).",
                          "output $/M: USD per million output tokens.",
                          "cache write $/M: USD per million tokens written to the cache (empty: not priced).",
                          "as of: the date the prices are from (YYYY-MM-DD).")

    def __init__(self, checkout: Path | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.cli = CliLocator.for_checkout(checkout)
        self.page = settings_page(self, "Prices", name="Prices settings")
        column = self.page.column
        sec = FormSection("Price sources", parent=column,
                          note="Prices older than 60 days are shown with a warning on every estimate. Overrides win "
                               "over both.")
        self.sources = forms.caption("Prices: loading (agentprov prices list)…", name="Price sources",
                                     parent=sec.card, role="secondary")
        set_setting_tooltip(self.sources, "The shipped table (an OpenRouter snapshot and the providers' pages; the "
                                          "About box names the sources) and the newest refreshed snapshot (Runs › New "
                                          "Job › Refresh model prices, agentprov prices refresh --allow-network, a "
                                          "confirmed network job).")
        sec.add(self.sources)
        self.page.add(sec)
        sec = FormSection("Your overrides", parent=column, note="USD per million tokens, each with the date it is "
                                                                "from. OK stores the changes.")
        self.table = QTableWidget(0, len(self.COLUMNS), sec.card)
        self.table.setHorizontalHeaderLabels(list(self.COLUMNS))
        self.table.setAccessibleName("Price overrides")
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 190)
        header = self.table.horizontalHeader()
        for c in range(1, len(self.COLUMNS) - 1):  # wide enough for its header ("Cached input" was cut at 82 px)
            self.table.setColumnWidth(c, max(82, header.sectionSizeFromContents(c).width() + 8))
        self.table.setMinimumHeight(200)
        set_setting_tooltip(self.table, "Your per-model prices in USD per million tokens, each with the date it is "
                            "from. An override wins over the shipped and refreshed prices.")
        set_header_tooltips(self.table, list(self.COLUMN_TIPS))
        sec.add(self.table)
        buttons = QWidget(sec.card)
        row = QHBoxLayout(buttons)
        row.setContentsMargins(0, 0, 0, 0)
        self.add_btn = QPushButton("Add Override", buttons)
        self.add_btn.setAccessibleName("Add a price override")
        self.add_btn.setAutoDefault(False)
        self.add_btn.clicked.connect(lambda: self._add())
        remove = QPushButton("Remove Override", buttons)
        remove.setAccessibleName("Remove the selected override")
        remove.setAutoDefault(False)
        theme.mark_destructive(remove)
        remove.clicked.connect(lambda: self.table.removeRow(self.table.currentRow()))
        set_setting_tooltip(self.add_btn, "Adds an override row: endpoint:model, the prices and the date. OK stores it "
                            "(agentprov prices set).")
        set_setting_tooltip(remove, "Removes the selected override; OK unsets it (agentprov prices unset).")
        row.addWidget(self.add_btn)
        row.addWidget(remove)
        row.addStretch(1)
        sec.add(buttons)
        self.page.add(sec)
        self.command = command_card(column)
        self.page.add(self.command)
        self.loaded: dict[str, tuple[str, ...]] | None = None  # None until the list arrived: save() writes nothing
        self._timer = _follow(self, self.show_command)
        self.table.itemChanged.connect(lambda _item: self._timer.start())
        self.table.model().rowsInserted.connect(lambda *_a: self._timer.start())
        self.table.model().rowsRemoved.connect(lambda *_a: self._timer.start())
        self.show_command()
        self.setEnabled(False)
        submit(self, lambda _s: call(self.cli, list(PRICES_LIST)), self._loaded,
               lambda code: self.sources.set_plain(f"Prices: agentprov prices list failed ({T.line(code, 60)})"))

    def _loaded(self, result: tuple[int, bytes, bytes]) -> None:
        code, out, err = result
        try:
            table = parse_prices(out) if code == 0 else None
        except PlanError:
            table = None
        if table is None:
            from agentprov_gui.settings_client import unavailable

            self.sources.set_plain(f"Prices: {T.line(unavailable('prices list', code, err), 400)}")
            return
        self.fill(table)

    def fill(self, table: PriceTable) -> None:
        self.sources.set_plain("\n".join([
            f"Shipped table: {table.shipped_rows} prices as of {T.line(table.shipped_as_of or 'unknown', 20)} "
            "(OpenRouter snapshot and provider pages; see the About box for sources).",
            "Refreshed OpenRouter prices: " + (T.line(table.refreshed_as_of, 20) if table.refreshed_as_of else
                                               "none (Runs › New Job › Refresh model prices, a confirmed network job)"),
        ]))
        self.table.setRowCount(0)
        self.loaded = {}
        for key, p in sorted(table.overrides.items()):
            values = (key, str(p.input), "" if p.cached_input is None else str(p.cached_input), str(p.output),
                      "" if p.cache_write is None else str(p.cache_write), p.as_of)
            self.loaded[key] = values[1:]
            self._add(list(values))
        self.setEnabled(True)
        self.show_command()

    def _add(self, values: list[str] | None = None) -> None:
        r = self.table.rowCount()
        self.table.insertRow(r)
        values = values or ["openrouter:vendor/model", "", "", "", "", dt.date.today().isoformat()]
        for c, v in enumerate(values):
            self.table.setItem(r, c, QTableWidgetItem(T.line(v, 120)))

    def values(self) -> dict[str, tuple[str, ...]]:
        out: dict[str, tuple[str, ...]] = {}
        for r in range(self.table.rowCount()):
            cells = [_cell(self.table.item(r, c)) for c in range(len(self.COLUMNS))]
            out[cells[0]] = (cells[1], cells[2], cells[3], cells[4], cells[5] or dt.date.today().isoformat())
        return out

    def pending(self) -> list[list[str]]:
        """What OK runs: ``prices unset`` for removed overrides and ``prices set`` for new or changed ones."""
        if self.loaded is None:
            return []
        loaded, values = self.loaded, self.values()
        out: list[list[str]] = []
        for key in sorted(set(loaded) - set(values)):
            endpoint, _, model = key.partition(":")
            out.append(["prices", "unset", endpoint, model])
        for key, (pin, cached, pout, cache_write, as_of) in sorted(values.items()):
            if loaded.get(key) == (pin, cached, pout, cache_write, as_of):
                continue
            endpoint, _, model = key.partition(":")
            argv = ["prices", "set", endpoint, model, "--input", pin, "--output", pout, "--as-of", as_of]
            argv += ["--cached-input", cached] if cached else []
            argv += ["--cache-write", cache_write] if cache_write else []
            out.append(argv)
        return out

    def commands(self) -> list[tuple[str, list[str]]]:
        if self.loaded is None:
            return []
        pending = self.pending()
        if not pending:
            return [("The price table; nothing changed, so OK writes nothing", list(PRICES_LIST))]
        return [("What OK runs" if i == 0 else "", argv) for i, argv in enumerate(pending)]

    def show_command(self) -> None:
        self.command.set_commands(self.commands(), note="Nothing to run until the price table is read")

    def save(self) -> None:
        """Run :meth:`pending`'s commands; refusals are listed."""
        if self.loaded is None:
            return
        pending = self.pending()
        refused: list[str] = []

        def write() -> None:  # AU-GUI-3: in the pool; the Settings window is disabled meanwhile
            for argv in pending:
                code, _out, err = call(self.cli, argv)
                if code != 0:
                    refused.append(f"{argv[2]}:{argv[3]}: {last_line(err)}")

        run_off_ui(self.window(), write)
        if refused:
            safe_message_box(self, "Overrides not saved", "Some overrides were refused and were not saved.",
                             informative="; ".join(T.line(r, 200) for r in refused)).exec()


def _cell(item: QTableWidgetItem | None) -> str:
    return item.text().strip() if item is not None else ""


class EstimatePane(QWidget):
    """The default assumptions (labelled as such on every estimate that uses them): ``agentprov settings``
    ``estimate.default.<name>_<p50|p90>`` (D-701, D-703); and the daily price refresh when Run Live opens, the setting
    ``prices.auto_refresh`` (D-1062; unset: on)."""

    FIELDS: Final = (("calls", "Model calls per cell", 6, 12), ("tokens_in", "Input tokens per call", 4000, 9000),
                     ("tokens_out", "Output tokens per call", 200, 600), ("seconds", "Seconds per cell", 45, 150))
    UNITS: Final = {"calls": "calls", "tokens_in": "tokens", "tokens_out": "tokens", "seconds": "seconds"}
    #: reverse CLI parity (D-700): each spin box's ``agentprov settings`` key
    KEYS: ClassVar[dict[str, str]] = {**{f"spins.{k}_{q}": f"{ESTIMATE_PREFIX}{k}_{q}" for k, *_ in FIELDS
                                         for q in ("p50", "p90")}, "auto_refresh": AUTO_REFRESH}

    def __init__(self, checkout: Path | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.cli = CliLocator.for_checkout(checkout)
        self.page = settings_page(self, "Estimate", name="Estimate settings")
        column = self.page.column
        self.status = forms.caption("Loading the stored defaults (agentprov settings)…",
                                    name="Estimate defaults status", parent=column, role="secondary")
        set_control_tooltip(self.status, "How many of these values are stored (agentprov settings list); the rest are "
                                         "the shipped assumptions.")
        self.page.add(self.status)
        self.spins: dict[str, DecimalField] = {}
        sections = {"p50": FormSection("Typical cell (median)", parent=column,
                                       note="Used where neither an opened corpus nor the shipped priors cover a suite "
                                            "and attack; every estimate that uses them says so."),
                    "p90": FormSection("Upper figure (90th percentile)", parent=column)}
        for q, sec in sections.items():
            for key, label, p50, p90 in self.FIELDS:
                spin = DecimalField(0, 10_000_000, float(p50 if q == "p50" else p90), name=f"{label} ({q})",
                                    decimals=0, unset=False, unit=self.UNITS[key], parent=sec.card)
                self.spins[f"{key}_{q}"] = spin
                sec.add_row(label, spin,
                            tip=f"The {'median' if q == 'p50' else '90th-percentile'} {label[0].lower()}{label[1:]} "
                                "that agentprov estimate assumes where neither an opened corpus nor the shipped priors "
                                f"cover a suite and attack ({ESTIMATE_PREFIX}{key}_{q}).")
            self.page.add(sec)
        sec = FormSection("Prices", parent=column)
        self.auto_refresh = Switch(name="Refresh prices once a day when Run Live opens", parent=sec.card, checked=True)
        sec.add_row("Refresh prices once a day", self.auto_refresh,
                    caption_text="When Run Live first opens on a day; fetches OpenRouter's public price list",
                    tip="On (the default): the first Run Live of a day starts agentprov prices refresh --allow-network "
                        "--if-stale as a job, which fetches OpenRouter's public price list once when no snapshot was "
                        "written today; off, the stored prices are used until you refresh them (setting "
                        "prices.auto_refresh).")
        self.page.add(sec)
        self.command = command_card(column)
        self.page.add(self.command)
        self.loaded: dict[str, float] | None = None
        self.loaded_auto = True
        self._timer = _follow(self, self.show_command)
        for spin in self.spins.values():
            spin.valueChanged.connect(lambda _v: self._timer.start())
        self.auto_refresh.toggled.connect(lambda _on: self._timer.start())
        self.show_command()
        self.setEnabled(False)
        submit(self, lambda _s: call(self.cli, list(SETTINGS_LIST)),
               self._loaded, lambda code: self.status.set_plain(f"agentprov settings failed ({T.line(code, 60)})"))

    def _loaded(self, result: tuple[int, bytes, bytes]) -> None:
        import json

        code, out, err = result
        try:
            doc = json.loads(out) if code == 0 else None
        except ValueError:
            doc = None
        stored = doc.get("values") if isinstance(doc, dict) else None
        if not isinstance(stored, dict):
            from agentprov_gui.settings_client import unavailable

            self.status.set_plain(T.line(unavailable("settings list", code, err), 400))
            return
        for name, spin in self.spins.items():
            value = stored.get(ESTIMATE_PREFIX + name)
            if isinstance(value, int | float) and not isinstance(value, bool):
                spin.setValue(float(value))
        self.auto_refresh.setChecked(stored.get(AUTO_REFRESH) is not False)
        self.loaded = self.values()
        self.loaded_auto = self.auto_refresh.isChecked()
        self.status.set_plain(f"{sum(1 for k in stored if k.startswith(ESTIMATE_PREFIX))} stored; the rest are the "
                              "shipped assumptions")
        self.setEnabled(True)
        self.show_command()

    def values(self) -> dict[str, float]:
        return {k: s.value() for k, s in self.spins.items()}

    def pending(self) -> list[list[str]]:
        """What OK runs: ``settings set`` for each changed value."""
        if self.loaded is None:
            return []
        loaded = self.loaded
        out = [["settings", "set", ESTIMATE_PREFIX + name, f"{value:g}"] for name, value in self.values().items()
               if value != loaded.get(name)]
        auto = self.auto_refresh.isChecked()
        if auto != self.loaded_auto:
            out.append(["settings", "set", AUTO_REFRESH, "true" if auto else "false"])
        return out

    def commands(self) -> list[tuple[str, list[str]]]:
        if self.loaded is None:
            return []
        pending = self.pending()
        if not pending:
            return [("The stored values; nothing changed, so OK writes nothing", list(SETTINGS_LIST))]
        return [("What OK runs" if i == 0 else "", argv) for i, argv in enumerate(pending)]

    def show_command(self) -> None:
        self.command.set_commands(self.commands(), note=NOT_READ)

    def save(self) -> None:
        if self.loaded is None:
            return
        pending = self.pending()
        refused: list[str] = []

        def write() -> None:  # AU-GUI-3: in the pool; the Settings window is disabled meanwhile
            for argv in pending:
                code, _out, err = call(self.cli, argv)
                if code != 0:
                    refused.append(f"{argv[2]}: {last_line(err)}")

        run_off_ui(self.window(), write)
        if refused:
            safe_message_box(self, "Defaults not saved", "Some estimate defaults were refused.",
                             informative="; ".join(T.line(r, 200) for r in refused)).exec()
