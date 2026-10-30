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
"""

from __future__ import annotations

import contextlib
import datetime as dt
from pathlib import Path
from typing import Any, ClassVar, Final

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QHBoxLayout,
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
from agentprov_gui.ui.safe import SafeForm, SafeLabel, safe_message_box
from agentprov_gui.ui.worker import submit

__all__ = ["EstimatePane", "KeysPane", "PricesPane", "StoreKeyDialog"]

NO_KEYCHAIN: Final = ("No secure keychain: keys cannot be stored; real-model runs from the GUI are disabled. Use the "
                      "agentprov CLI with your own environment instead.")
ESTIMATE_PREFIX: Final = "estimate.default."


class StoreKeyDialog(QDialog):
    """A password field; the value never stays in the widget after OK or Cancel."""

    def __init__(self, name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Store {name}")
        self.setAccessibleName("Store a key")
        lay = QVBoxLayout(self)
        lay.addWidget(SafeLabel(f"{name}: stored in the OS keychain only (service agentprov). The CLI reads it from "
                                "there when a live run starts (D-702), and it is never shown again.",
                                name="Key explanation", parent=self))
        self.field = QLineEdit(self)
        self.field.setEchoMode(QLineEdit.EchoMode.Password)  # Qt disables copy and cut in password mode
        self.field.setAccessibleName(f"{name} value")
        lay.addWidget(self.field)
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
        lay = QVBoxLayout(self)
        self.status = SafeLabel("Keychain: not checked yet", name="Keychain status", parent=self)
        lay.addWidget(self.status)
        self.table = QTableWidget(0, 3, self)
        self.table.setHorizontalHeaderLabels(["endpoint", "key variable", "stored"])
        self.table.setAccessibleName("Endpoint keys")
        self.table.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(self.table)
        row = QHBoxLayout()
        self.check = QPushButton("Check Keychain", self)
        self.check.setAccessibleName("Check the keychain")
        self.check.clicked.connect(self.refresh)
        self.store_btn = QPushButton("Store Key…", self)
        self.store_btn.setAccessibleName("Store the selected key")
        self.store_btn.clicked.connect(self.store_selected)
        self.delete_btn = QPushButton("Delete Key", self)
        self.delete_btn.setAccessibleName("Delete the selected key")
        self.delete_btn.clicked.connect(self.delete_selected)
        for b in (self.check, self.store_btn, self.delete_btn):
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        self.names: list[str] = []
        self._fill({})

    def _fill(self, present: dict[str, bool]) -> None:
        eps = [e for e in load_endpoints(self.checkout).values() if e.api_key_env]
        rows: list[tuple[str, str]] = []
        for e in eps:
            assert e.api_key_env is not None
            rows.append((f"{e.name} (optional, local)" if e.local else e.name, e.api_key_env))  # D-827: oMLX's optional key
        rows += ZENODO_KEYS  # D-880: the draft-only uploader's tokens (agentprov keys accepts them)
        self.table.setRowCount(len(rows))
        self.names = []
        for i, (label, name) in enumerate(rows):
            self.names.append(name)
            stored = present.get(name)
            for j, v in enumerate((label, name, "—" if stored is None else ("yes" if stored else "no"))):
                self.table.setItem(i, j, QTableWidgetItem(T.line(v, 80)))

    def refresh(self) -> None:
        try:
            st = keychain.status(self.cli)
        except keychain.KeychainError as exc:
            self.status.set_plain(f"Keychain: the helper failed ({T.line(exc.code, 60)})")
            return
        if not st.allowed:
            self.status.set_plain(NO_KEYCHAIN + (f" ({T.line(st.reason, 300)})" if st.reason else ""))
            self.store_btn.setEnabled(False)
            return
        self.status.set_plain(f"Keychain: {T.line(st.backend or '', 60)} (allowed)")
        try:
            self._fill(keychain.present(self.cli, sorted(set(self.names))))
        except keychain.KeychainError as exc:
            self.status.set_plain(f"Keychain: {T.line(exc.code, 60)}")

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
        try:
            keychain.store(self.cli, name, value)
        except keychain.KeychainError as exc:
            safe_message_box(self, "Key not stored", "The key was not stored.", informative=T.line(exc.code, 60)).exec()
        del value
        self.refresh()

    def delete_selected(self) -> None:
        name = self._selected()
        if name is None:
            return
        with contextlib.suppress(keychain.KeychainError):
            keychain.delete(self.cli, name)
        self.refresh()

    def save(self) -> None:
        """Keys are stored at once by the helper; nothing is kept in the settings."""


class PricesPane(QWidget):
    """The price sources and the per-model overrides (``agentprov prices``; D-701)."""

    COLUMNS: Final = ("endpoint:model", "input $/M", "cached input $/M", "output $/M", "cache write $/M", "as of")

    def __init__(self, checkout: Path | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.cli = CliLocator.for_checkout(checkout)
        lay = QVBoxLayout(self)
        self.sources = SafeLabel("Prices: loading (agentprov prices list)…", name="Price sources", parent=self)
        lay.addWidget(self.sources)
        self.table = QTableWidget(0, len(self.COLUMNS), self)
        self.table.setHorizontalHeaderLabels(list(self.COLUMNS))
        self.table.setAccessibleName("Price overrides")
        lay.addWidget(self.table)
        row = QHBoxLayout()
        self.add_btn = QPushButton("Add Override", self)
        self.add_btn.setAccessibleName("Add a price override")
        self.add_btn.clicked.connect(lambda: self._add())
        remove = QPushButton("Remove Override", self)
        remove.setAccessibleName("Remove the selected override")
        remove.clicked.connect(lambda: self.table.removeRow(self.table.currentRow()))
        row.addWidget(self.add_btn)
        row.addWidget(remove)
        row.addStretch(1)
        lay.addLayout(row)
        self.loaded: dict[str, tuple[str, ...]] | None = None  # None until the list arrived: save() writes nothing
        self.setEnabled(False)
        submit(self, lambda _s: call(self.cli, ["prices", "list", "--format", "json"]), self._loaded,
               lambda code: self.sources.set_plain(f"Prices: agentprov prices list failed ({T.line(code, 60)})"))

    def _loaded(self, result: tuple[int, bytes, bytes]) -> None:
        code, out, err = result
        try:
            table = parse_prices(out) if code == 0 else None
        except PlanError:
            table = None
        if table is None:
            self.sources.set_plain(f"Prices: agentprov prices list ended with exit {code}: "
                                   f"{T.line(last_line(err), 200)}")
            return
        self.fill(table)

    def fill(self, table: PriceTable) -> None:
        self.sources.set_plain("\n".join([
            f"Shipped table: {table.shipped_rows} prices as of {T.line(table.shipped_as_of or 'unknown', 20)} "
            "(OpenRouter snapshot and provider pages; see the About box for sources).",
            "Refreshed OpenRouter prices: " + (T.line(table.refreshed_as_of, 20) if table.refreshed_as_of else
                                               "none (Runs › New Job › Refresh model prices, a confirmed network job)"),
            "Prices older than 60 days are shown with a warning on every estimate. Overrides win over both.",
        ]))
        self.table.setRowCount(0)
        self.loaded = {}
        for key, p in sorted(table.overrides.items()):
            values = (key, str(p.input), "" if p.cached_input is None else str(p.cached_input), str(p.output),
                      "" if p.cache_write is None else str(p.cache_write), p.as_of)
            self.loaded[key] = values[1:]
            self._add(list(values))
        self.setEnabled(True)

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

    def save(self) -> None:
        """``prices unset`` for removed overrides and ``prices set`` for new or changed ones; refusals are listed."""
        if self.loaded is None:
            return
        values = self.values()
        refused: list[str] = []
        for key in sorted(set(self.loaded) - set(values)):
            endpoint, _, model = key.partition(":")
            code, _out, err = call(self.cli, ["prices", "unset", endpoint, model])
            if code != 0:
                refused.append(f"{key}: {last_line(err)}")
        for key, (pin, cached, pout, write, as_of) in sorted(values.items()):
            if self.loaded.get(key) == (pin, cached, pout, write, as_of):
                continue
            endpoint, _, model = key.partition(":")
            argv = ["prices", "set", endpoint, model, "--input", pin, "--output", pout, "--as-of", as_of]
            argv += ["--cached-input", cached] if cached else []
            argv += ["--cache-write", write] if write else []
            code, _out, err = call(self.cli, argv)
            if code != 0:
                refused.append(f"{key}: {last_line(err)}")
        if refused:
            safe_message_box(self, "Overrides not saved", "Some overrides were refused and were not saved.",
                             informative="; ".join(T.line(r, 200) for r in refused)).exec()


def _cell(item: QTableWidgetItem | None) -> str:
    return item.text().strip() if item is not None else ""


class EstimatePane(QWidget):
    """The default assumptions (labelled as such on every estimate that uses them): ``agentprov settings``
    ``estimate.default.<name>_<p50|p90>`` (D-701, D-703)."""

    FIELDS: Final = (("calls", "Model calls per cell", 6, 12), ("tokens_in", "Input tokens per call", 4000, 9000),
                     ("tokens_out", "Output tokens per call", 200, 600), ("seconds", "Seconds per cell", 45, 150))
    #: reverse CLI parity (D-700): each spin box's ``agentprov settings`` key
    KEYS: ClassVar[dict[str, str]] = {f"spins.{k}_{q}": f"{ESTIMATE_PREFIX}{k}_{q}" for k, *_ in FIELDS
                                      for q in ("p50", "p90")}

    def __init__(self, checkout: Path | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.cli = CliLocator.for_checkout(checkout)
        form = SafeForm(self)
        self.spins: dict[str, QDoubleSpinBox] = {}
        for key, label, p50, p90 in self.FIELDS:
            for q, default in (("p50", p50), ("p90", p90)):
                spin = QDoubleSpinBox(self)
                spin.setRange(0, 10_000_000)
                spin.setDecimals(0)
                spin.setValue(float(default))
                self.spins[f"{key}_{q}"] = spin
                form.add(f"{label} ({q})", spin)
        self.status = SafeLabel("Loading the stored defaults (agentprov settings)…", name="Estimate defaults status",
                                parent=self)
        form.add("Used", SafeLabel("where neither an opened corpus nor the shipped priors cover a suite and attack "
                                   "(agentprov estimate)", name="Where the defaults apply", parent=self))
        form.add("Stored", self.status)
        self.loaded: dict[str, float] | None = None
        self.setEnabled(False)
        submit(self, lambda _s: call(self.cli, ["settings", "list", "--prefix", ESTIMATE_PREFIX, "--format", "json"]),
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
            self.status.set_plain(f"agentprov settings ended with exit {code}: {T.line(last_line(err), 200)}")
            return
        for name, spin in self.spins.items():
            value = stored.get(ESTIMATE_PREFIX + name)
            if isinstance(value, int | float) and not isinstance(value, bool):
                spin.setValue(float(value))
        self.loaded = self.values()
        self.status.set_plain(f"{sum(1 for k in stored if k.startswith(ESTIMATE_PREFIX))} stored; the rest are the "
                              "shipped assumptions")
        self.setEnabled(True)

    def values(self) -> dict[str, float]:
        return {k: s.value() for k, s in self.spins.items()}

    def save(self) -> None:
        if self.loaded is None:
            return
        refused = []
        for name, value in self.values().items():
            if value != self.loaded.get(name):
                code, _out, err = call(self.cli, ["settings", "set", ESTIMATE_PREFIX + name, f"{value:g}"])
                if code != 0:
                    refused.append(f"{name}: {last_line(err)}")
        if refused:
            safe_message_box(self, "Defaults not saved", "Some estimate defaults were refused.",
                             informative="; ".join(T.line(r, 200) for r in refused)).exec()
