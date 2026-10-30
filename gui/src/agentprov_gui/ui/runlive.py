"""Run live (design §8, §19.2; D-650–D-655; wireframe 04).

One dialog configures a live capture run, shows the estimate, confirms and hands the job to Runs:

* **Source** (agentdojo or autodojo) with its live status from ``agentprov info --format json``. While the live part
  is ``planned`` (today) only scripted runs can start; a real model's Start is disabled with that reason (§8.1).
* **Model:** the scripted transport (no network, no keys, no cost) or an endpoint of the checkout's ``endpoints.toml``
  with a model id (completed from ``agentprov prices list``; never a default). The key variable it needs and whether the
  keychain holds it are shown; **Store Key…** stores one (D-655).
* **Cells:** suites, attacks (ticks), user tasks, injection tasks, benign include / exclude / only, repeats. The lists
  come from ``run SOURCE --catalogue`` (D-652); a refused attack cannot be ticked and says why.
* **Estimate** (§8.3 as amended, D-650, D-701): after every change (debounced), ``agentprov estimate … --format json``
  plans the cells (a dry run, D-651), prices them and returns p50 and p90 cost and time, the breakdown per suite and per
  attack, the worst case, the sources of its numbers and the price's date (with a warning past 60 days). The open
  corpora are passed as ``--stats-corpus``. The GUI shows the CLI's numbers and lines; it computes none.
* **Start** confirms by tier: R1 for scripted runs, R2 for a real model with the cost, the endpoint host, the model, the
  key variable's name (never its value) and the consent box "I consent to API costs for up to N cell attempts"; only
  then is ``--i-consent-to-api-costs`` added. **Preflight Only…** is a separate R2 job (one paid probe call).

Every string from the CLI or the backend is a label: shown through ``text.line`` only.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Final

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from agentprov_gui import text as T
from agentprov_gui.jobs.commands import CONFORMANCE_OPTION, FORMS, Field, FormError, JobSpec
from agentprov_gui.jobs.manager import JobManager
from agentprov_gui.live import keychain
from agentprov_gui.live import models as models_mod
from agentprov_gui.live.backends import NOT_BUILT, live_backends
from agentprov_gui.live.models import (
    ModelList,
    identity_argv,
    identity_lines,
    list_argv,
    parse_identity,
    parse_list,
    refresh_argv,
    refresh_blocked,
)
from agentprov_gui.live.plan import (
    Catalogue,
    Endpoint,
    EstimateView,
    PlanError,
    PriceRow,
    PriceTable,
    live_status,
    load_endpoints,
    parse_catalogue,
    parse_estimate,
    parse_prices,
)
from agentprov_gui.live.runspec import (
    DECLARED_CONTAINMENT,
    RunSettings,
    catalogue_argv,
    containment_choices,
    containment_line,
    estimate_argv,
    job_spec,
    key_names,
)
from agentprov_gui.ui.jobdialog import TIER_TEXT, confirm, conformance_warning
from agentprov_gui.ui.safe import (
    ReadOnlyText,
    SafeForm,
    SafeLabel,
    ask,
    safe_message_box,
    set_combo_item_tooltip,
    set_list_item_tooltip,
    set_tooltip,
)
from agentprov_gui.ui.worker import submit

__all__ = ["DEV_SCRIPT", "LiveStart", "RunLiveDialog", "consent_text", "run_cli"]

DEV_SCRIPT: Final = Path(__file__).resolve().parent.parent / "data" / "scripted-dev.json"
DEBOUNCE_MS: Final = 800
MAX_STDOUT: Final = 64 * 1024 * 1024
GATED: Final = ("planned", "not_possible")


@dataclass(frozen=True, slots=True)
class LiveStart:
    """What Runs starts: the spec, and for a real model the key names and non-secret values for the helper's line."""

    spec: JobSpec
    key_names: tuple[str, ...] = ()
    values: tuple[tuple[str, str], ...] = ()
    backend: str = ""  # recorded in job.json (the same suite can run on two backends)


class IdentityDialog(QDialog):
    """A local model's identity record, as ``agentprov models --model-id ID --format json`` gives it (D-692): a short
    summary, then the record as JSON (``ensure_ascii``, plain text). Read-only."""

    def __init__(self, record: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Model Identity")
        self.setAccessibleName("Model identity record")
        self.resize(760, 560)
        lay = QVBoxLayout(self)
        for line in identity_lines(record):
            lay.addWidget(SafeLabel(T.line(line, 300), name="Identity summary", parent=self))
        text = ReadOnlyText(name="Identity record JSON", parent=self)
        text.setPlainText(json.dumps(record, indent=2, sort_keys=True, ensure_ascii=True))
        lay.addWidget(text, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)


def run_cli(manager: JobManager, argv: Sequence[str], *, stdin_fd: int | None = None,
            timeout: float = 600) -> tuple[int, bytes, bytes]:
    """An R0 CLI call (``info``, ``--catalogue``, a dry run): its exit code, stdout (bounded) and the stderr tail."""
    if not manager.cli.available:
        return 127, b"", b"no CLI"
    try:
        done = subprocess.run(  # noqa: S603 - the configured CLI and a fixed argv
            [*manager.cli.program, *argv, "--progress", "off", "--no-colour"], capture_output=True, timeout=timeout,
            check=False, env=manager.child_env(), stdin=subprocess.DEVNULL if stdin_fd is None else stdin_fd)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 124, b"", type(exc).__name__.encode()
    finally:
        if stdin_fd is not None:
            os.close(stdin_fd)
    return done.returncode, done.stdout[:MAX_STDOUT], done.stderr[-4096:]


#: D-729: the preflight probe makes at most this many calls (the CLI's ``PROBE_ATTEMPTS``)
PROBE_CALLS: Final = 3
#: the run options a preflight-only run must not carry: the CLI refuses caps with --preflight-only (D-725, exit 2)
CAP_KEYS: Final = frozenset({"max_calls", "max_cost_usd", "price_in", "price_out"})


def consent_text(attempts: int, *, local: bool = False, preflight: bool = False) -> str:
    if preflight:
        what = f"up to {PROBE_CALLS} preflight probe calls"
        return f"I consent to a local model run of {what}" if local else f"I consent to API costs for {what}"
    if local:  # D-726: a local model server; no API cost
        return f"I consent to a local model run of up to {attempts:,} cell attempts"
    return f"I consent to API costs for up to {attempts:,} cell attempts"


def preflight_settings(s: RunSettings) -> RunSettings:
    """The settings of a preflight-only run: the probe alone, without the campaign's caps (the CLI refuses them)."""
    return replace(s, extra={**{k: v for k, v in s.extra.items() if k not in CAP_KEYS}, "preflight_only": True})


def _checked(widget: QListWidget) -> list[str]:
    return [str(widget.item(i).data(Qt.ItemDataRole.UserRole)) for i in range(widget.count())
            if widget.item(i).checkState() == Qt.CheckState.Checked]


def _spin(parent: QWidget, lo: int, hi: int, value: int | None) -> QSpinBox:
    s = QSpinBox(parent)
    s.setRange(lo - 1, hi)
    s.setSpecialValueText("default")
    s.setValue(value if value is not None else lo - 1)
    return s


def _spin_value(s: QSpinBox) -> int | None:
    return s.value() if s.value() >= s.minimum() + 1 else None


class RunLiveDialog(QDialog):
    def __init__(self, manager: JobManager, *, home: Path, checkout: Path | None, opened: Sequence[Path] = (),
                 conformance_option: str | None = None, preset: RunSettings | None = None,
                 run: Callable[..., tuple[int, bytes, bytes]] = run_cli, dev_run: bool = False,
                 cli_options: frozenset[str] = frozenset(),
                 call_cap: int | None = None, cost_cap: float | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.manager, self.home, self.checkout, self.run = manager, home, checkout, run
        self.conformance_option = conformance_option
        self.cli_options = cli_options  # run --help (feature detection: D-656 --max-tokens)
        #: design §19.2: a live dev run ticks every suite by default, stops at the call cap and must estimate under
        #: the cost cap (p90) to start
        self.dev_run, self.call_cap, self.cost_cap = dev_run, call_cap, cost_cap
        self.setWindowTitle("Live Dev Run" if dev_run else "Run Live")
        self.setAccessibleName("Run live")
        self.resize(900, 820)
        self.prices: PriceTable | None = None  # agentprov prices list (D-701), loaded in the background
        self.endpoints: dict[str, Endpoint] = load_endpoints(checkout)
        self.opened = [str(p) for p in opened if (Path(p) / "aer").is_dir()]  # --stats-corpus (design §8.3)
        self.catalogue: Catalogue | None = None
        self.catalogues: dict[str, Catalogue | str] = {}  # backend: catalogue, or why there is none
        self.estimate_result: EstimateView | None = None
        self.live_status: dict[str, str | None] = {}
        self.keys_present: dict[str, bool] = {}
        self.keychain_ok: bool | None = None
        self.start: LiveStart | None = None
        self.preflight_reason: str | None = None  # why Preflight Only… is disabled (see _gate)
        self._dry_seq = 0
        self.model_lists: dict[str, ModelList] = {}  # endpoint -> agentprov models's list (the picker, D-700)
        self._models_seq = 0
        self.identity_dialog: IdentityDialog | None = None
        self._build(preset or RunSettings(script=str(DEV_SCRIPT)))
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.refresh_estimate)
        self._load_status()
        self._load_catalogue()
        self._keys_refresh()
        self._load_prices()
        self._changed()

    # ------------------------------------------------------------------------------------------ widgets
    def _build(self, s: RunSettings) -> None:
        outer = QVBoxLayout(self)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        body = QWidget(scroll)
        col = QVBoxLayout(body)
        # source
        src = QGroupBox("Source", body)
        sf = SafeForm(src)
        self.backends = live_backends()
        self.source = QComboBox(src)  # the backend picker (user decision 2026-10-22)
        for b in self.backends:
            self.source.addItem(T.line(b.source, 40), b.source)
        index = self.source.findData(s.source)
        self.source.setCurrentIndex(max(0, index))
        self.source.currentIndexChanged.connect(self._backend_changed)
        sf.add("Backend", self.source)
        self.status = SafeLabel("Live status: checking…", name="Live status", parent=src)
        sf.add("Status", self.status)
        self.version = QComboBox(src)
        self.version.setEditable(True)
        self.version.setCurrentText(s.benchmark_version)
        self.version.currentTextChanged.connect(lambda _t: self._changed())
        sf.add("Benchmark version (default: the backend's)", self.version)
        col.addWidget(src)
        # model
        mod = QGroupBox("Model", body)
        mf = SafeForm(mod)
        self.mode = QComboBox(mod)
        self.mode.addItems(["Scripted transport (no network, no keys, no cost)", "Endpoint (real model)"])
        self.mode.setCurrentIndex(0 if s.scripted else 1)
        self.mode.currentIndexChanged.connect(self._mode_and_changed)
        mf.add("Transport", self.mode)
        self.script = QLineEdit(s.script or str(DEV_SCRIPT), mod)
        self.script.textChanged.connect(lambda _t: self._changed())
        mf.add("Script (SCRIPT.json)", self.script)
        self.endpoint = QComboBox(mod)
        self.endpoint.addItems(sorted(self.endpoints))
        if s.model:
            self.endpoint.setCurrentText(s.model)
        self.endpoint.currentTextChanged.connect(self._endpoint_changed)
        mf.add("Endpoint (endpoints.toml)", self.endpoint)
        self.model_id = QComboBox(mod)
        self.model_id.setEditable(True)
        self.model_id.setCurrentText(s.model_id)
        self.model_id.currentTextChanged.connect(lambda _t: self._changed())
        mf.add("Model id (no default)", self.model_id)
        # the model picker is a client of agentprov models (D-691, D-730; D-700): list, refresh, identity
        picker_row = QHBoxLayout()
        self.models_status = SafeLabel("", name="Model list status", parent=mod)
        self.models_status.setWordWrap(True)
        picker_row.addWidget(self.models_status, 1)
        self.refresh_models_btn = QPushButton("Refresh List", mod)
        self.refresh_models_btn.setAccessibleName("Refresh the provider's model list (network)")
        self.refresh_models_btn.clicked.connect(self._refresh_models)
        picker_row.addWidget(self.refresh_models_btn)
        self.identity_btn = QPushButton("Identity…", mod)
        self.identity_btn.setAccessibleName("Show the local model's identity record")
        self.identity_btn.clicked.connect(self._show_identity)
        picker_row.addWidget(self.identity_btn)
        picker_box = QWidget(mod)
        picker_box.setLayout(picker_row)
        mf.add("Models", picker_box)
        key_row = QHBoxLayout()
        self.key_label = SafeLabel("", name="Key status", parent=mod)
        key_row.addWidget(self.key_label, 1)
        self.key_btn = QPushButton("Store Key…", mod)
        self.key_btn.setAccessibleName("Store the endpoint key")
        self.key_btn.clicked.connect(self._store_key)
        key_row.addWidget(self.key_btn)
        key_box = QWidget(mod)
        key_box.setLayout(key_row)
        mf.add("Key", key_box)
        self.price_label = SafeLabel("", name="Price", parent=mod)
        mf.add("Price", self.price_label)
        self.containment = QComboBox(mod)
        self.containment.addItems(["", *containment_choices()])  # sandbox-exec on macOS only (G5 P-4)
        self.containment.setCurrentText(s.containment)
        self.containment.currentTextChanged.connect(lambda _t: self._changed())
        mt_row = QHBoxLayout()
        self.max_tokens_mode = QComboBox(mod)
        self.max_tokens_mode.addItems(["harness default (16,000)", "a number"])
        self.max_tokens_mode.setAccessibleName("Max tokens choice")
        self.max_tokens_mode.currentIndexChanged.connect(lambda _i: self._changed())
        self.max_tokens = QSpinBox(mod)
        self.max_tokens.setRange(1, 1_000_000)
        self.max_tokens.setValue(16_000)
        self.max_tokens.setAccessibleName("Max tokens")
        self.max_tokens.valueChanged.connect(lambda _v: self._changed())
        mt_row.addWidget(self.max_tokens_mode)
        mt_row.addWidget(self.max_tokens)
        self.max_tokens_box = QWidget(mod)
        self.max_tokens_box.setLayout(mt_row)
        self.max_tokens_label = mf.add("Max tokens (Anthropic endpoints; D-656)", self.max_tokens_box)
        # D-725 (live pilot): an API-endpoint run needs both caps; shown once the CLI offers them
        caps_row = QHBoxLayout()
        self.max_calls = QSpinBox(mod)
        self.max_calls.setRange(0, 10_000_000)
        self.max_calls.setSpecialValueText("—")
        self.max_calls.setAccessibleName("Max billed model calls")
        self.max_cost = QDoubleSpinBox(mod)
        self.max_cost.setRange(0, 1_000_000)
        self.max_cost.setDecimals(2)
        self.max_cost.setPrefix("$")
        self.max_cost.setAccessibleName("Max cost in USD")
        self.price_in = QDoubleSpinBox(mod)
        self.price_out = QDoubleSpinBox(mod)
        for price_spin, name in ((self.price_in, "Cap price, input side, USD per million tokens"),
                                 (self.price_out, "Cap price, output, USD per million tokens")):
            price_spin.setRange(0, 10_000)
            price_spin.setDecimals(4)
            price_spin.setAccessibleName(name)
        cap_spins: tuple[QSpinBox | QDoubleSpinBox, ...] = (self.max_calls, self.max_cost, self.price_in, self.price_out)
        for cap in cap_spins:
            cap.valueChanged.connect(lambda _v: self._changed())
            caps_row.addWidget(cap)
        self.caps_box = QWidget(mod)
        self.caps_box.setLayout(caps_row)
        self.caps_label = mf.add("API caps: calls, USD, $/M in, $/M out (D-725)", self.caps_box)
        self._caps_priced_for: tuple[str, str] | None = None
        mf.add("Containment (required for a real model)", self.containment)
        mf.add("", SafeLabel(DECLARED_CONTAINMENT, name="Containment note", parent=mod))
        col.addWidget(mod)
        # cells
        cells = QGroupBox("Cells", body)
        cf = SafeForm(cells)
        self.cat_label = SafeLabel("Catalogue: loading…", name="Catalogue status", parent=cells)
        cf.add("Catalogue", self.cat_label)
        self.suites = QListWidget(cells)
        self.suites.setAccessibleName("Suites")
        self.suites.setMaximumHeight(140)
        self.suites.itemChanged.connect(lambda _i: self._changed())
        cf.add("Suites", self.suites)
        self.attacks = QListWidget(cells)
        self.attacks.setAccessibleName("Attacks")
        self.attacks.setMaximumHeight(180)
        self.attacks.itemChanged.connect(lambda _i: self._changed())
        cf.add("Attacks", self.attacks)
        self._wanted = (set(s.suites), set(s.attacks))
        self.user_tasks = QLineEdit(s.user_tasks, cells)
        self.user_tasks.setPlaceholderText("all (or ids, or index ranges such as 0-2,5)")
        self.user_tasks.textChanged.connect(lambda _t: self._changed())
        cf.add("User tasks", self.user_tasks)
        self.injection_tasks = QLineEdit(s.injection_tasks, cells)
        self.injection_tasks.setPlaceholderText("all (or ids, or index ranges)")
        self.injection_tasks.textChanged.connect(lambda _t: self._changed())
        cf.add("Injection tasks", self.injection_tasks)
        self.benign = QComboBox(cells)
        self.benign.addItems(["include", "exclude", "only"])
        self.benign.setCurrentText(s.benign or "include")
        self.benign.currentTextChanged.connect(lambda _t: self._changed())
        cf.add("Benign cells", self.benign)
        self.repeats = _spin(cells, 1, 1000, s.repeats)
        self.repeats.valueChanged.connect(lambda _v: self._changed())
        cf.add("Repeats", self.repeats)
        col.addWidget(cells)
        # run
        runbox = QGroupBox("Run", body)
        rf = SafeForm(runbox)
        self.corpus = QLineEdit(s.corpus, runbox)
        self.corpus.setPlaceholderText(str(self.home / "corpora" / "<source>-live-<campaign>"))
        self.corpus.textChanged.connect(lambda _t: self._changed())
        rf.add("Working corpus (outside the repository)", self.corpus)
        self.campaign = QLineEdit(s.campaign, runbox)
        self.campaign.textChanged.connect(lambda _t: self._changed())
        rf.add("Campaign (corpus id <source>-live-<campaign>)", self.campaign)
        self.jobs = _spin(runbox, 1, 512, s.jobs)
        self.jobs.valueChanged.connect(lambda _v: self._changed())
        rf.add("Concurrent traces (--jobs)", self.jobs)
        self.max_attempts = _spin(runbox, 1, 100, s.max_attempts)
        self.max_attempts.valueChanged.connect(lambda _v: self._changed())
        rf.add("Max attempts per unit", self.max_attempts)
        self.canary = _spin(runbox, 0, 100_000, s.canary)
        rf.add("Canary cells (0 disables)", self.canary)
        self.cell_timeout = QDoubleSpinBox(runbox)
        self.cell_timeout.setRange(0, 86_400)
        self.cell_timeout.setSpecialValueText("default (1800 s)")
        self.cell_timeout.setValue(s.cell_timeout or 0)
        rf.add("Cell timeout (seconds)", self.cell_timeout)
        self.conformance = QCheckBox("Run the W3C PROV conformance check (tier 4)", runbox)
        self.conformance.setAccessibleName("Run the W3C PROV conformance check")
        self.conformance.setChecked(True)
        if self.conformance_option is None:
            self.conformance.setEnabled(False)
            set_tooltip(self.conformance, "This CLI cannot skip the check yet (G2c-5): the check always runs.")
        self.conformance.clicked.connect(self._conformance_clicked)
        rf.add("Conformance", self.conformance)
        tune_row = QHBoxLayout()
        self.tune_btn = QPushButton("Tune…", runbox)
        self.tune_btn.setAccessibleName("Tune the concurrency with a host preset")
        self.tune_btn.clicked.connect(self.tune)
        tune_row.addWidget(self.tune_btn)
        tune_row.addStretch(1)
        tune_box = QWidget(runbox)
        tune_box.setLayout(tune_row)
        rf.add("Concurrency plan (run --dry-run with a host preset)", tune_box)
        col.addWidget(runbox)
        # more options: every other run field (D-654)
        self.more = QToolButton(body)
        self.more.setText("More Options")
        self.more.setCheckable(True)
        self.more.setAccessibleName("Show more run options")
        col.addWidget(self.more)
        more_box = QWidget(body)
        more_form = SafeForm(more_box)
        more_box.setVisible(False)
        self.more.toggled.connect(more_box.setVisible)
        self.more_inputs: dict[str, QWidget] = {}
        for f in FORMS["run"].fields:
            if f.key in _DIALOG_KEYS:
                continue
            w = _field_widget(f, more_box, s.extra.get(f.key))
            _connect(w, self._changed)
            self.more_inputs[f.key] = w
            more_form.add(f.label, w)
        col.addWidget(more_box)
        # estimate
        est = QGroupBox("Estimate", body)
        el = QVBoxLayout(est)
        self.headline = SafeLabel("Estimate: waiting for the plan…", name="Estimate", parent=est)
        self.headline.setWordWrap(True)
        el.addWidget(self.headline)
        self.details = ReadOnlyText(name="Estimate details", parent=est)
        self.details.setMinimumHeight(220)
        el.addWidget(self.details)
        col.addWidget(est)
        col.addStretch(1)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)
        self.error = SafeLabel("", name="Form error", parent=self)
        self.error.setWordWrap(True)
        outer.addWidget(self.error)
        buttons = QDialogButtonBox(self)
        self.preflight_btn = buttons.addButton("Preflight Only…", QDialogButtonBox.ButtonRole.ActionRole)
        self.preflight_btn.setAccessibleName("Run the preflight probe only")
        self.preflight_btn.clicked.connect(lambda: self._start(preflight=True))
        self.start_btn = buttons.addButton("Start…", QDialogButtonBox.ButtonRole.AcceptRole)
        self.start_btn.setAccessibleName("Start the live run")
        self.start_btn.clicked.connect(lambda: self._start(preflight=False))
        cancel = buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        cancel.clicked.connect(self.reject)
        outer.addWidget(buttons)
        self._mode_changed()
        self._models()

    # ------------------------------------------------------------------------------------------ state
    def backend(self) -> str:
        data = self.source.currentData()
        return str(data) if data else ""

    def _backend_changed(self, _index: int) -> None:
        self._show_catalogue()
        self._changed()

    def _mode_and_changed(self, _index: int) -> None:
        self._mode_changed()
        self._changed()

    def _endpoint_changed(self, _text: str) -> None:
        self._models()
        self._load_model_list()
        self._changed()

    @property
    def scripted(self) -> bool:
        return self.mode.currentIndex() == 0

    def _caps_shown(self) -> bool:
        """D-725: a real run on an API (not local) endpoint, with a CLI that has the cap options."""
        ep = self._endpoint()
        return not self.scripted and ep is not None and not ep.local and "--max-calls" in self.cli_options

    def _local_consent(self) -> bool:
        ep = self._endpoint()
        return (not self.scripted and ep is not None and ep.local
                and "--i-consent-to-local-run" in self.cli_options)

    def _price_caps(self) -> None:
        """Fill the cap prices from the price table once per endpoint and model (the user may change them): the
        input side is the highest of input, cached input and cache write (the CLI's upper-bound rule)."""
        key = (self.endpoint.currentText(), self.model_id.currentText().strip())
        p = self.price() if self._caps_shown() else None
        if p is None or key == self._caps_priced_for:
            return
        self._caps_priced_for = key
        side = max(v for v in (p.input, p.cached_input, p.cache_write) if v is not None)
        for spin, value in ((self.price_in, side), (self.price_out, p.output)):
            spin.blockSignals(True)
            spin.setValue(float(value))
            spin.blockSignals(False)

    def _anthropic(self) -> bool:
        ep = self._endpoint()
        return not self.scripted and ep is not None and ep.api == "anthropic_messages"

    def _extra(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, w in self.more_inputs.items():
            value = _widget_value(w)
            if value not in (None, "", False):
                out[key] = value
        if self._caps_shown():
            if self.max_calls.value():
                out["max_calls"] = self.max_calls.value()
            if self.max_cost.value():
                out.update(max_cost_usd=self.max_cost.value(), price_in=self.price_in.value(),
                           price_out=self.price_out.value())
        if self._anthropic():
            out.pop("reasoning_effort", None)  # D-656: the Anthropic element sends no effort
            if out.get("llm_element") == "gateway_compat":
                out.pop("llm_element")
            if "--max-tokens" in self.cli_options:
                out["max_tokens"] = ("harness-default" if self.max_tokens_mode.currentIndex() == 0
                                     else str(self.max_tokens.value()))
        return out

    def settings(self) -> RunSettings:
        corpus = self.corpus.text().strip()
        if not corpus and self.campaign.text().strip():
            corpus = str(self.home / "corpora" / f"{self.backend()}-live-{self.campaign.text().strip()}")
        return RunSettings(
            source=self.backend(), corpus=corpus, campaign=self.campaign.text().strip(),
            scripted=self.scripted, script=self.script.text().strip(), model=self.endpoint.currentText(),
            model_id=self.model_id.currentText().strip(), suites=tuple(_checked(self.suites)),
            attacks=tuple(_checked(self.attacks)), user_tasks=self.user_tasks.text().strip(),
            injection_tasks=self.injection_tasks.text().strip(),
            benign="" if self.benign.currentText() == "include" else self.benign.currentText(),
            benchmark_version=self.version.currentText().strip(), repeats=_spin_value(self.repeats),
            jobs=_spin_value(self.jobs), max_attempts=_spin_value(self.max_attempts), canary=_spin_value(self.canary),
            cell_timeout=self.cell_timeout.value() or None, containment=self.containment.currentText(),
            extra=self._extra(),
        )  # fmt: skip

    def _endpoint(self) -> Endpoint | None:
        return self.endpoints.get(self.endpoint.currentText())

    def _anthropic_controls(self) -> None:
        anthropic = self._anthropic()
        show = anthropic and "--max-tokens" in self.cli_options
        self.max_tokens_box.setVisible(show)
        self.max_tokens_label.setVisible(show)
        caps = self._caps_shown()
        self.caps_box.setVisible(caps)
        self.caps_label.setVisible(caps)
        self._price_caps()
        self.max_tokens.setEnabled(self.max_tokens_mode.currentIndex() == 1)
        for key in ("reasoning_effort", "llm_element"):  # D-656: refused for an Anthropic endpoint
            w = self.more_inputs.get(key)
            if w is not None:
                w.setEnabled(not anthropic)

    def _mode_changed(self) -> None:
        real = not self.scripted
        for w in (self.endpoint, self.model_id, self.key_btn, self.containment):
            w.setEnabled(real)
        self.script.setEnabled(not real)

    def _models(self) -> None:
        """The picker's ids: ``agentprov models``'s list for the endpoint when it has one (usable models, with their
        facts as tooltips), else the price table's models."""
        current = self.model_id.currentText()
        self.model_id.blockSignals(True)
        self.model_id.clear()
        listed = self.model_lists.get(self.endpoint.currentText())
        choices = [c for c in listed.choices if c.usable] if listed is not None else []
        if choices:
            for c in choices:
                self.model_id.addItem(T.line(c.id, 120), c.id)
                if c.note:
                    set_combo_item_tooltip(self.model_id, self.model_id.count() - 1, c.note)
        else:
            models = self.prices.models.get(self.endpoint.currentText(), {}) if self.prices else {}
            self.model_id.addItems([T.line(m, 120) for m in sorted(models)])
        self.model_id.setCurrentText(current)
        self.model_id.blockSignals(False)

    # ------------------------------------------------------------------ the model picker (agentprov models; D-700)
    def _allow_lan(self) -> bool:
        box = self.more_inputs.get("allow_lan_endpoint")
        return isinstance(box, QCheckBox) and box.isChecked()

    def _key_stored(self, ep: Endpoint) -> bool:
        return bool(ep.api_key_env) and self.keychain_ok is True and self.keys_present.get(str(ep.api_key_env)) is True

    def _picker_controls(self) -> None:
        ep = self._endpoint()
        real = not self.scripted and ep is not None
        blocked = refresh_blocked(ep, key_stored=self._key_stored(ep)) if ep is not None else "no endpoint"
        self.refresh_models_btn.setVisible(ep is not None and models_mod.is_provider(ep))
        self.refresh_models_btn.setEnabled(real and blocked is None)
        set_tooltip(self.refresh_models_btn, blocked or "agentprov models --allow-network: the provider's registry host "
                    "only; no tokens, no cost (R2, confirmed)")
        self.identity_btn.setVisible(ep is not None and ep.local)
        self.identity_btn.setEnabled(real and ep is not None and ep.local and bool(self.model_id.currentText().strip()))

    def _load_model_list(self, argv: list[str] | None = None) -> None:
        ep = self._endpoint()
        if ep is None:
            self.models_status.set_plain("")
            return
        argv = argv or list_argv(ep, key_stored=self._key_stored(ep), allow_lan=self._allow_lan())
        if argv is None:
            self.models_status.set_plain(f"{T.line(ep.name, 40)}: no agentprov models list for this endpoint; the "
                                         "ids come from the price table")
            return
        self.models_status.set_plain(f"{T.line(ep.name, 40)}: reading the model list (agentprov models)…")
        self._models_seq += 1
        seq = self._models_seq

        def work(_s: object) -> tuple[int, bytes, bytes]:
            return self.run(self.manager, argv, timeout=180)

        def done(result: tuple[int, bytes, bytes]) -> None:
            listed = parse_list(ep, *result)
            self.model_lists[ep.name] = listed
            if seq == self._models_seq and self.endpoint.currentText() == ep.name:
                self.models_status.set_plain(T.line(listed.detail, 300))
                self._models()
                self._changed()

        submit(self, work, done, lambda _code: None)

    def _refresh_models(self) -> None:
        ep = self._endpoint()
        argv = refresh_argv(ep, key_stored=self._key_stored(ep)) if ep is not None else None
        if ep is None or argv is None:
            return
        if ask(self, "Refresh model list", f"Fetch {T.line(ep.name, 40)}'s model list now?",
               "R2: one request to the provider's model registry (no tokens, no cost); the list is cached with its "
               "date. agentprov models --allow-network."):
            self._load_model_list(argv)

    def _show_identity(self) -> None:
        ep = self._endpoint()
        model = self.model_id.currentText().strip()
        if ep is None or not ep.local or not model:
            return
        argv = identity_argv(ep, model, allow_lan=self._allow_lan())
        self.models_status.set_plain(f"{T.line(model, 120)}: reading its identity (weight digests are cached after "
                                     "the first time)…")

        def work(_s: object) -> tuple[int, bytes, bytes]:
            return self.run(self.manager, argv, timeout=1800)

        def done(result: tuple[int, bytes, bytes]) -> None:
            code, out, err = result
            record = parse_identity(code, out)
            if record is None:
                reason = err.decode("utf-8", "replace").strip().splitlines()[-1:] or [f"exit {code}"]
                self.models_status.set_plain(f"{T.line(model, 120)}: no identity record ({T.line(reason[0], 200)})")
                return
            listed = self.model_lists.get(ep.name)
            self.models_status.set_plain(T.line(listed.detail, 300) if listed is not None else "")
            self.identity_dialog = IdentityDialog(record, self)
            self.identity_dialog.open()

        submit(self, work, done, lambda _code: None)

    def price(self) -> PriceRow | None:
        """The model's price as ``agentprov prices list`` resolved it (None: unpriced, or the list is loading)."""
        if self.scripted or self.prices is None:
            return None
        return self.prices.lookup(self.endpoint.currentText(), self.model_id.currentText().strip())

    def _changed(self) -> None:
        self._picker_controls()
        ep = self._endpoint()
        names = key_names(ep.api_key_env if ep else None, optional=bool(ep and ep.local))
        if self.scripted:
            self.key_label.set_plain("not needed (scripted)")
        elif not names and ep is not None and ep.local and ep.api_key_env:  # D-827: the server's optional key
            stored = self.keys_present.get(ep.api_key_env) if self.keychain_ok is True else None
            self.key_label.set_plain(f"{ep.api_key_env}: optional (local endpoint); " + (
                "stored in the keychain, sent to the server" if stored else
                "not stored, no key is sent" if stored is False or self.keychain_ok is False else "checking…"))
        elif not names:
            self.key_label.set_plain("not needed (local endpoint)")
        elif self.keychain_ok is False:
            self.key_label.set_plain("no secure keychain: real-model runs are disabled")
        else:
            stored = self.keys_present.get(names[0])
            self.key_label.set_plain(f"{names[0]}: " + ("stored in the keychain" if stored else
                                                         "not stored" if stored is False else "checking…"))
        p = self.price()
        if self.scripted:
            self.price_label.set_plain("no cost (scripted transport)")
        elif self.prices is None:
            self.price_label.set_plain("prices: loading (agentprov prices list)…")
        elif self.endpoint.currentText() in self.prices.local:
            self.price_label.set_plain("local endpoint: no per-token cost (time only)")
        elif p is None:
            self.price_label.set_plain("no price for this model: enter one in Settings › Prices")
        else:
            self.price_label.set_plain(T.line(p.text(), 300))
        self._gate()
        self.timer.start(DEBOUNCE_MS)

    def _gate(self) -> str | None:
        """Why Start is disabled (None: enabled). Preflight Only… has the same gate without the caps, which a
        preflight-only run does not take (``self.preflight_reason``)."""
        self._anthropic_controls()
        reason = None
        caps_missing = False
        status = self.live_status.get(self.backend())
        s = self.settings()
        entry = self.catalogues.get(s.source)
        if isinstance(entry, str):
            reason = f"{s.source}: {entry}. Nothing is launched for it."
        elif not s.suites:
            reason = "Tick at least one suite."
        elif not s.corpus or not s.campaign:
            reason = "Name a campaign (and optionally the working corpus)."
        elif self.checkout is not None and _inside(Path(s.corpus), self.checkout):
            reason = "The working corpus must be outside the repository (guard G3)."
        elif self.scripted and not Path(s.script).is_file():
            reason = "The script file does not exist."
        elif not self.scripted:
            ep = self._endpoint()
            if status in GATED:
                reason = (f"Real-model runs of {s.source} are gated: its live part is {status} (exit 5 until its "
                          "gates pass). Scripted runs work.")
            elif ep is None or not s.model_id:
                reason = "Choose an endpoint and a model id."
            elif self._anthropic() and "--max-tokens" not in self.cli_options:
                reason = ("This CLI has no --max-tokens yet, which an Anthropic endpoint needs (D-656); use the "
                          "openrouter endpoint for Claude until it lands.")
            elif not s.containment:
                reason = "A real model needs a containment (--containment)."
            elif ep.api_key_env and not ep.local and (self.keychain_ok is False
                                                      or not self.keys_present.get(ep.api_key_env)):
                reason = f"{ep.api_key_env} is not in the keychain (Store Key…)."
            elif self.cost_cap is not None:
                e = self.estimate_result
                if e is None or e.cost_p90 is None:
                    reason = "The dev run's cost cap needs an estimate with a price first."
                elif float(e.cost_p90) > self.cost_cap:
                    reason = f"The estimate (p90 ${e.cost_p90:.4f}) is above the dev run's cost cap (${self.cost_cap:g})."
            caps_missing = self._caps_shown() and not (self.max_calls.value() and self.max_cost.value())
        self.preflight_reason = reason
        if reason is None and caps_missing:
            reason = "An API-endpoint run needs both caps: max model calls and max cost (D-725)."
        self.start_btn.setEnabled(reason is None)
        self.preflight_btn.setEnabled(self.preflight_reason is None and not self.scripted)
        self.error.set_plain(reason or "")
        return reason

    # ------------------------------------------------------------------------------------------ background
    def _load_status(self) -> None:
        for source in (b.source for b in self.backends):
            def work(_s: object, source: str = source) -> tuple[str, bytes]:
                return source, self.run(self.manager, ["info", source, "--format", "json"], timeout=120)[1]

            submit(self, work, self._status_loaded, lambda _code: None)

    def _status_loaded(self, result: tuple[str, bytes]) -> None:
        source, data = result
        status, _backend = live_status(data, source)
        self.live_status[source] = status
        if source == self.backend():
            self.status.set_plain(f"Live status: {T.line(status or 'unknown', 40)}"
                                  + (" (scripted runs only)" if status in GATED else ""))
        self._gate()

    def _load_catalogue(self) -> None:
        """Every backend's catalogue at once (D-652): the picker shows which environments are built."""
        self.cat_label.set_plain("Catalogue: loading…")
        for b in self.backends:
            def work(_s: object, source: str = b.source) -> tuple[str, int, bytes, bytes]:
                return (source, *self.run(self.manager, list(catalogue_argv(source)), timeout=300))

            submit(self, work, self._catalogue_loaded, lambda code: self.cat_label.set_plain(f"Catalogue: {code}"))

    def _catalogue_loaded(self, result: tuple[str, int, bytes, bytes]) -> None:
        source, code, out, err = result
        backend = next((b.backend for b in self.backends if b.source == source), source)
        text = err.decode("utf-8", "replace")
        if code != 0:
            if code == 3 and "not built" in text:
                self.catalogues[source] = NOT_BUILT.format(backend=backend)
            else:
                tail = T.line(text.strip().splitlines()[-1] if text.strip() else "", 300)
                self.catalogues[source] = f"catalogue unavailable (exit {code}): {tail}"
        else:
            try:
                self.catalogues[source] = parse_catalogue(out)
            except PlanError as exc:
                self.catalogues[source] = f"catalogue unusable: {exc}"
        i = self.source.findData(source)
        if i >= 0:
            entry = self.catalogues[source]
            self.source.setItemText(i, T.line(source, 40) + ("" if isinstance(entry, Catalogue)
                                                              else f"  ({T.line(entry, 200)})"))
        if source == self.backend():
            self._show_catalogue()

    def _show_catalogue(self) -> None:
        entry = self.catalogues.get(self.backend())
        if not isinstance(entry, Catalogue):
            self.catalogue = None
            self.cat_label.set_plain("Catalogue: " + (T.line(entry, 300) if entry else "loading…"))
            self.suites.clear()
            self.attacks.clear()
            self._changed()
            return
        cat = entry
        self.catalogue = cat
        self.cat_label.set_plain(f"{len(cat.suites)} suites, {len(cat.attacks)} attacks "
                                 f"({T.line(cat.backend, 20)}, {T.line(cat.benchmark_version, 20)})")
        self.version.blockSignals(True)
        current = self.version.currentText()
        self.version.clear()
        self.version.addItems(["", *(T.line(v, 40) for v in cat.benchmark_versions)])
        self.version.setCurrentText(current)
        self.version.blockSignals(False)
        wanted_suites, wanted_attacks = self._wanted
        self.suites.blockSignals(True)
        self.suites.clear()
        for s in cat.suites:
            item = QListWidgetItem(f"{T.line(s.name, 80)}  ({len(s.user_tasks)} user, {len(s.injection_tasks)} "
                                   "injection tasks)")
            item.setData(Qt.ItemDataRole.UserRole, s.name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            ticked = s.name in wanted_suites or (self.dev_run and not wanted_suites)
            item.setCheckState(Qt.CheckState.Checked if ticked else Qt.CheckState.Unchecked)
            self.suites.addItem(item)
        self.suites.blockSignals(False)
        self.attacks.blockSignals(True)
        self.attacks.clear()
        for a in cat.attacks:
            label = T.line(a.name, 80) + (" (DoS: one cell per user task)" if a.dos else "")
            if a.needs:
                label += " (needs " + ", ".join(T.line(n, 40) for n in a.needs) + ": More options)"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, a.name)
            flags = item.flags() | Qt.ItemFlag.ItemIsUserCheckable
            if a.refused:
                flags &= ~Qt.ItemFlag.ItemIsEnabled
                set_list_item_tooltip(item, "Refused by the backend: " + a.refused)
            item.setFlags(flags)
            item.setCheckState(Qt.CheckState.Checked if a.name in wanted_attacks and not a.refused
                               else Qt.CheckState.Unchecked)
            self.attacks.addItem(item)
        self.attacks.blockSignals(False)
        self._changed()

    def _keys_refresh(self) -> None:
        names = sorted({e.api_key_env for e in self.endpoints.values() if e.api_key_env})

        def work(_s: object) -> tuple[bool, dict[str, bool]]:
            st = keychain.status(self.manager.cli)
            return st.allowed, (keychain.present(self.manager.cli, names) if st.allowed and names else {})

        def done(result: tuple[bool, dict[str, bool]]) -> None:
            self.keychain_ok, self.keys_present = result
            self._load_model_list()  # a stored key may now allow a stale provider list to be refreshed (D-733)
            self._changed()

        submit(self, work, done, lambda _code: done((False, {})))

    def _load_prices(self) -> None:
        def work(_s: object) -> tuple[int, bytes, bytes]:
            return self.run(self.manager, ["prices", "list", "--format", "json"], timeout=120)

        def done(result: tuple[int, bytes, bytes]) -> None:
            code, out, _err = result
            try:
                self.prices = parse_prices(out) if code == 0 else PriceTable({}, frozenset(), 0, "", 0, None, {})
            except PlanError:
                self.prices = PriceTable({}, frozenset(), 0, "", 0, None, {})
            self._models()
            self._changed()

        submit(self, work, done, lambda _code: None)

    def refresh_estimate(self) -> None:
        s = self.settings()
        if not s.suites or not self.manager.cli.available:
            self.headline.set_plain("Estimate: tick a suite (and attacks) to see the cost.")
            self.details.setPlainText("")
            return
        ep = self._endpoint()
        status = self.live_status.get(s.source)
        names = key_names(ep.api_key_env if ep else None, optional=bool(ep and ep.local))
        real_ok = (not self.scripted and status not in GATED and status is not None
                   and all(self.keys_present.get(n) for n in names))
        try:
            argv = estimate_argv(s, real_allowed=real_ok, stats_corpora=self.opened)
        except FormError as exc:
            self.headline.set_plain(f"Estimate: {exc}")
            return
        self._dry_seq += 1
        seq = self._dry_seq
        self.headline.set_plain("Estimate: planning and pricing the cells (agentprov estimate)…")

        def work(_s: object) -> tuple[int, int, bytes, bytes]:
            return (seq, *self.run(self.manager, list(argv), timeout=600))  # --keychain: the CLI reads it

        submit(self, work, self._estimate_loaded, lambda code: self.headline.set_plain(f"Estimate: {code}"))

    def _estimate_loaded(self, result: tuple[int, int, bytes, bytes]) -> None:
        seq, code, out, err = result
        if seq != self._dry_seq:
            return  # a newer selection is being estimated
        if code != 0:
            tail = T.line(err.decode("utf-8", "replace").strip().splitlines()[-1] if err.strip() else "", 300)
            self.headline.set_plain(f"Estimate: agentprov estimate ended with exit {code}: {tail}")
            return
        try:
            self.estimate_result = parse_estimate(out)
        except PlanError as exc:
            self.headline.set_plain(f"Estimate: the estimate is unusable ({exc})")
            return
        self.show_estimate()

    def show_estimate(self) -> None:
        e = self.estimate_result
        if e is None:
            return
        self._gate()
        self.headline.set_plain(T.line(e.text[0] if e.text else "", 600))
        self.details.setPlainText("\n".join(T.line(x, 600) for x in e.text[1:]))

    # ------------------------------------------------------------------------------------------ actions
    def tune(self) -> None:
        """§8.1 step 4: ``run --dry-run`` with a host preset (More Options: preset, m5ultra and the model-size fields;
        default ``--m5ultra``) prints the concurrency plan; Apply copies its ``--jobs`` into the form. R0."""
        s = self.settings()
        keys = ("preset", "m5ultra", "model_dir", "model_size_gb", "active_params_b", "context_tokens",
                "kv_gb_per_trace", "server_max_concurrency")
        extra = {k: v for k, v in s.extra.items() if k in keys}
        if not extra.get("preset") and not extra.get("m5ultra"):
            extra["m5ultra"] = True
        ep = self._endpoint()
        if not self.scripted and ep is not None and ep.local and s.model_id:  # D-828: its Settings › Local models facts
            extra.update(model=s.model, model_id=s.model_id)
        try:
            from agentprov_gui.jobs.commands import build_spec as _build

            spec = _build(FORMS["run"], {"source": s.source, "dry_run": True, "jobs": s.jobs, **extra})
        except FormError as exc:
            self.error.set_plain(f"Tune: {exc}")
            return
        argv = [*spec.argv[:-1], "--json", spec.argv[-1]]
        code, out, err = self.run(self.manager, argv, timeout=120)
        jobs = None
        try:
            import json

            doc = json.loads(out)
            value = doc.get("counters", {}).get("jobs") if isinstance(doc, dict) else None
            jobs = value if isinstance(value, int) and not isinstance(value, bool) else None
        except ValueError:
            pass
        text = T.clean(err.decode("utf-8", "replace"), 8000) if err else ""
        box = QDialog(self)
        box.setWindowTitle("Concurrency plan")
        box.setAccessibleName("Concurrency plan")
        lay = QVBoxLayout(box)
        pane = ReadOnlyText(name="Concurrency plan output", parent=box)
        pane.setPlainText(f"exit {code}\n{text}")
        lay.addWidget(pane)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, box)
        apply = None
        if jobs is not None and code == 0:
            apply = buttons.addButton(f"Apply --jobs {jobs}", QDialogButtonBox.ButtonRole.AcceptRole)
            apply.clicked.connect(box.accept)
        buttons.rejected.connect(box.reject)
        lay.addWidget(buttons)
        if box.exec() and jobs is not None:
            self.jobs.setValue(jobs)

    def _store_key(self) -> None:
        ep = self._endpoint()
        if ep is None or not ep.api_key_env:
            return
        from agentprov_gui.ui.livepanes import StoreKeyDialog

        dlg = StoreKeyDialog(ep.api_key_env, self)
        accepted = bool(dlg.exec())
        value = dlg.take()
        if accepted and value:
            from agentprov_gui.app import register_secret

            register_secret(value)
            try:
                keychain.store(self.manager.cli, ep.api_key_env, value)
            except keychain.KeychainError as exc:
                safe_message_box(self, "Key not stored", "The key was not stored.",
                                 informative=T.line(exc.code, 60)).exec()
            del value
        self._keys_refresh()

    def _conformance_clicked(self, checked: bool) -> None:
        if not checked and not conformance_warning(self):
            self.conformance.setChecked(True)
        self._changed()

    def _start(self, *, preflight: bool) -> None:
        reason = self._gate()
        if (self.preflight_reason if preflight else reason) is not None:
            return
        s = self.settings()
        if preflight:
            s = preflight_settings(s)
        consent = False
        if not self.scripted:
            consent = self.confirm_costs(s, preflight=preflight)
            if not consent:
                return
        try:
            spec = job_spec(s, consent=consent, local_consent=self._local_consent(),
                            conformance=self.conformance.isChecked(),
                            conformance_option=self.conformance_option)
        except FormError as exc:
            self.error.set_plain(str(exc))
            return
        if self.scripted:
            confirmed = confirm(self, spec, " ".join(["agentprov", *spec.argv]))
            if confirmed is None:
                return
            spec = confirmed
        ep = self._endpoint()
        names = tuple(key_names(ep.api_key_env if ep else None, optional=bool(ep and ep.local))) if not self.scripted else ()
        backend = next((b.backend for b in self.backends if b.source == s.source), s.source)
        if self.call_cap is not None:  # §19.2: the follower counts model_call steps; Runs drains the job at the cap
            spec = replace(spec, extra={**dict(spec.extra or {}), "progress_level": "steps", "call_cap": self.call_cap,
                                        "devrun": True})
        self.start = LiveStart(spec, names, backend=backend)
        self.accept()

    def confirm_costs(self, s: RunSettings, *, preflight: bool) -> bool:
        """The R2 confirmation (§8.3): endpoint host, model, key variable name, containment, cells, repeats, jobs,
        both estimates, the billing note, and the consent box that alone enables Start."""
        ep = self._endpoint()
        e = self.estimate_result
        attempts = 1 if preflight else (e.attempts_due if e else 0)
        dlg = QDialog(self)
        dlg.setWindowTitle("Confirm: Run Live" + (" (preflight only)" if preflight else ""))
        dlg.setAccessibleName("Confirm the live run")
        lay = QVBoxLayout(dlg)
        host = T.line(ep.base_url if ep else "", 200)
        lines = [TIER_TEXT["R2"], f"Endpoint: {T.line(s.model, 40)} ({host})", f"Model: {T.line(s.model_id, 120)}",
                 f"Key variable: {T.line(ep.api_key_env if ep and ep.api_key_env else 'none', 64)} (from the "
                 "keychain; its value is never shown)", f"Containment: {T.line(containment_line(s.containment), 120)}"]
        if preflight:
            lines.append(f"Preflight only: up to {PROBE_CALLS} probe calls to the endpoint (another only while the "
                         "reply is unconfirmed), then the job ends. A preflight-only run takes no caps.")
        elif e is not None:
            lines += [T.line(x, 600) for x in e.text[:2]]  # the CLI's headline (cost, time) and plan lines
            lines.append(f"{e.units:,} unit(s) due; --jobs {s.jobs or 1}")
            if e.cost_worst is not None:
                lines.append(f"Worst case (every due attempt at p90): ${e.cost_worst:.4f}")
        if not preflight:
            lines.append(f"Before the first cell, the preflight probe makes up to {PROBE_CALLS} calls, charged to the "
                         "caps.")
        if self._caps_shown() and not preflight:
            lines.append(f"Caps (D-725): at most {s.extra.get('max_calls', 0):,} billed model calls and "
                         f"${float(s.extra.get('max_cost_usd', 0)):,.2f}, priced at ${float(s.extra.get('price_in', 0))}"
                         f" / ${float(s.extra.get('price_out', 0))} per million tokens in / out")
        lines.append("A local model server: no provider bills these calls." if ep is not None and ep.local else
                     "Model calls may be billed by the provider.")
        lay.addWidget(SafeLabel("\n".join(lines), name="What this run costs", parent=dlg))
        tick = QCheckBox(consent_text(attempts, local=self._local_consent(), preflight=preflight), dlg)
        tick.setAccessibleName("Consent to API costs")
        lay.addWidget(tick)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, dlg)
        ok = box.button(QDialogButtonBox.StandardButton.Ok)
        ok.setText("Start")
        ok.setEnabled(False)
        box.button(QDialogButtonBox.StandardButton.Cancel).setDefault(True)
        tick.toggled.connect(ok.setEnabled)
        box.accepted.connect(dlg.accept)
        box.rejected.connect(dlg.reject)
        lay.addWidget(box)
        return bool(dlg.exec()) and tick.isChecked()


#: the run fields the dialog's own controls set (everything else is under More Options)
_DIALOG_KEYS: Final = frozenset({
    "source", "corpus", "campaign", "suite", "benchmark_version", "user_tasks", "attack", "injection_tasks", "benign",
    "model", "model_id", "llm_script", "repeats", "max_attempts", "canary", "cell_timeout", "jobs", "containment",
    "dry_run", "preflight_only", "max_tokens", "max_calls", "max_cost_usd", "price_in", "price_out"})


def _field_widget(f: Field, parent: QWidget, value: Any) -> QWidget:
    w: QWidget
    if f.kind == "bool":
        cb = QCheckBox(parent)
        cb.setChecked(bool(value))
        w = cb
    elif f.kind == "choice":
        combo = QComboBox(parent)
        combo.addItems([c for c in f.choices])
        if value in f.choices:
            combo.setCurrentText(str(value))
        w = combo
    elif f.kind == "int":
        w = _spin(parent, 0, 10_000_000, value if isinstance(value, int) and not isinstance(value, bool) else None)
    else:
        line = QLineEdit(parent)
        if value is not None:
            line.setText(str(value))
        w = line
    w.setAccessibleName(f.label)
    if f.help:
        set_tooltip(w, f.help)
    return w


def _connect(w: QWidget, slot: Callable[[], None]) -> None:
    if isinstance(w, QCheckBox):
        w.toggled.connect(lambda _c: slot())
    elif isinstance(w, QComboBox):
        w.currentTextChanged.connect(lambda _t: slot())
    elif isinstance(w, QSpinBox):
        w.valueChanged.connect(lambda _v: slot())
    elif isinstance(w, QLineEdit):
        w.textChanged.connect(lambda _t: slot())


def _widget_value(w: QWidget) -> Any:
    if isinstance(w, QCheckBox):
        return w.isChecked()
    if isinstance(w, QComboBox):
        return w.currentText()
    if isinstance(w, QSpinBox):
        return _spin_value(w)
    if isinstance(w, QLineEdit):
        return w.text().strip()
    return None


def _inside(path: Path, root: Path) -> bool:
    try:
        Path(os.path.realpath(path.expanduser())).relative_to(os.path.realpath(root))
    except ValueError:
        return False
    return True


#: re-exported for the Runs page (the option name the conformance box adds when unticked)
CONFORMANCE: Final = CONFORMANCE_OPTION
