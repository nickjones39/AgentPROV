"""Run live (design §8, §19.2; D-650–D-655; wireframe 04; the form style of D-1060).

One dialog configures a live capture run, shows the estimate, confirms and hands the job to Runs. Its layout is the
GUI's one form style (D-1060): a form column of sections (Benchmark, Model, Limits, What to run, Save to) beside a
summary panel that keeps the result in view, and a footer with Preflight Only… on the left and Cancel and Start… on
the right.

* **Benchmark:** the backend (agentdojo or autodojo) with its live status from ``agentprov info --format json`` as a
  badge. While the live part is ``planned`` (today) only scripted runs can start; a real model's Start is disabled with
  that reason (§8.1).
* **Model:** the transport as a segmented control. Scripted (no network, no keys, no cost) shows only its script; a
  real model shows the endpoint of the checkout's ``endpoints.toml``, the model id (completed from ``agentprov models``
  or ``agentprov prices list``; never a default), the price, the key variable it needs and whether the keychain holds
  it (**Store Key…** stores one, D-655) and the containment. Rows that do not apply are hidden, not greyed.
* **Limits** (an API endpoint, D-725): the cost and call caps and the prices they are priced at; "Use the quote's
  upper figure" fills the cost cap from the quote's p90.
* **What to run:** the scope (the full benchmark, or chosen suites and attacks), suites as a two-column checklist with
  their task counts, attacks as chips (a refused one cannot be chosen and says why), the benign cells, and behind one
  disclosure the task selection and repeats. The lists come from ``run SOURCE --catalogue`` (D-652). The full benchmark
  gives the same arguments as ticking every suite and every attack that can be chosen, with the benign cells.
* **Save to:** the campaign and the working corpus; behind "Advanced: …" the concurrency (with **Tune…**), attempts,
  canary, cell timeout, the conformance switch and every other ``run`` option (D-654).
* **Summary / quote** (§8.3 as amended, D-650, D-701): after every change (debounced), ``agentprov estimate …
  --format json`` plans the cells (a dry run, D-651), prices them and returns p50 and p90 cost and time. For a real
  model the panel is the quote for this run (typical and upper cost, cell runs, model calls, tokens, time at the
  chosen concurrency) with how it is worked out, from the CLI's ``quote`` object when it gives one (read defensively,
  the estimate's own figures otherwise) and always marked an estimate only. The open corpora are passed as
  ``--stats-corpus``. The GUI shows the CLI's numbers and lines; it computes none. The before-you-start checks, the
  plan by suite and the **terminal command** (the exact ``agentprov estimate`` and ``agentprov run`` the dialog would
  start, from the same functions that build them) follow.
* **Daily price refresh** (D-1062): with the setting on, the first Run Live of a day starts ``agentprov prices
  refresh --allow-network`` as a job (the GUI opens no connection itself, S11) and re-runs the estimate when it ends;
  the quote says when the prices were refreshed, or that the refresh failed and which prices are used.
* **Start** confirms by tier: R1 for scripted runs, R2 for a real model with the cost, the endpoint host, the model, the
  key variable's name (never its value) and the consent box "I consent to API costs for up to N cell attempts"; only
  then is ``--i-consent-to-api-costs`` added. **Preflight Only…** is a separate R2 job (one paid probe call).

Every string from the CLI or the backend is a label: shown through ``text.line`` only.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import json
import os
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from decimal import ROUND_CEILING, Decimal
from pathlib import Path
from typing import Any, Final
from urllib.parse import urlsplit

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from agentprov_gui import platform_limits
from agentprov_gui import text as T
from agentprov_gui.jobs.commands import CONFORMANCE_OPTION, FORMS, Field, FormError, JobSpec, build_spec
from agentprov_gui.jobs.manager import Job, JobManager
from agentprov_gui.live import keychain, pricerefresh
from agentprov_gui.live import models as models_mod
from agentprov_gui.live.backends import NOT_BUILT, live_backends
from agentprov_gui.live.cli import last_line
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
    Quote,
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
from agentprov_gui.ui import forms, theme
from agentprov_gui.ui.forms import (
    Checklist,
    ChipGroup,
    Choice,
    CommandCard,
    DecimalField,
    Disclosure,
    FactGrid,
    FormPage,
    FormSection,
    IntField,
    PathField,
    SegmentedControl,
    StatusBadge,
    SummaryPanel,
    Switch,
)
from agentprov_gui.ui.jobdialog import CONFORMANCE_TIP, TIER_TEXT, confirm, conformance_warning, field_tip
from agentprov_gui.ui.platformnotice import PlatformNotice, gate_combo_item, notifier
from agentprov_gui.ui.safe import (
    ReadOnlyText,
    SafeLabel,
    ask,
    safe_message_box,
    set_combo_item_tooltip,
    set_control_tooltip,
    set_help_tooltip,
    set_setting_tooltip,
    set_unavailable_tooltip,
)
from agentprov_gui.ui.worker import run_off_ui, submit

__all__ = ["DEV_SCRIPT", "LiveStart", "RunLiveDialog", "consent_text", "run_cli"]

DEV_SCRIPT: Final = Path(__file__).resolve().parent.parent / "data" / "scripted-dev.json"
DEBOUNCE_MS: Final = 800
MAX_STDOUT: Final = 64 * 1024 * 1024
GATED: Final = ("planned", "not_possible")
#: D-1062: "Build cost figures from my corpora" leaves the machine to other work (CLAUDE.md: --jobs 8 to 16 shares it)
PRIORS_JOBS: Final = 8
#: the screen's name for the remembered disclosures (D-1060 rule 4)
SCREEN: Final = "run-live"
#: the scope control's choices (What to run)
FULL, CHOOSE = 0, 1
DASH: Final = "—"
#: the estimate's token basis when no usage was recorded (characters / 4)
CHARS_BASIS: Final = "chars/" + "4"


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
#: The hosts the CLI classes a local entry's run ``local`` on (D-721; ``agentprov.cli.live.policy.LOOPBACK_HOSTS``).
LOOPBACK_HOSTS: Final = frozenset({"127.0.0.1", "::1", "localhost"})


def on_loopback(base_url: str) -> bool:
    """Whether ``base_url``'s host is loopback, as the CLI's endpoint class reads it."""
    try:
        return (urlsplit(base_url).hostname or "").lower() in LOOPBACK_HOSTS
    except ValueError:
        return False


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


def _spin(parent: QWidget, lo: int, hi: int, value: int | None, *, name: str = "", placeholder: str = "Default",
          unit: str = "") -> IntField:
    """A whole number whose unset value (``lo - 1``, the earlier "default" special value) leaves the option out."""
    return IntField(lo, hi, value, name=name, placeholder=placeholder, unit=unit, parent=parent)


def _spin_value(s: QSpinBox) -> int | None:
    return s.value() if s.value() >= s.minimum() + 1 else None


def usd(value: Decimal | None) -> str:
    """A dollar figure as the CLI's money() writes it (``$1,234``, ``$12.34``, ``$0.0123``); a dash when unknown."""
    if value is None:
        return DASH
    if value >= 100:
        return f"${value:,.0f}"
    if value >= 1:
        return f"${value:,.2f}"
    return f"${value:.4f}" if value > 0 else "$0"


def _tokens(value: float | None) -> str:
    if value is None:
        return DASH
    return f"{value / 1e6:,.1f} M" if value >= 100_000 else f"{value / 1e3:,.1f} k"


def _span(lo: float | None, hi: float | None, fmt: Callable[[float], str]) -> str:
    if lo is None:
        return DASH if hi is None else fmt(hi)
    if hi is None or fmt(lo) == fmt(hi):
        return fmt(lo)
    return f"{fmt(lo)} – {fmt(hi)}"


def _duration(lo: float | None, hi: float | None) -> str:
    longest = max(v for v in (lo, hi, 0.0) if v is not None)
    if longest >= 2 * 3600:
        return _span(None if lo is None else lo / 3600, None if hi is None else hi / 3600, lambda v: f"{v:,.1f}") + " h"
    return _span(None if lo is None else lo / 60, None if hi is None else hi / 60, lambda v: f"{v:,.0f}") + " min"


class RunLiveDialog(QDialog):
    def __init__(self, manager: JobManager, *, home: Path, checkout: Path | None, opened: Sequence[Path] = (),
                 conformance_option: str | None = None, preset: RunSettings | None = None,
                 run: Callable[..., tuple[int, bytes, bytes]] = run_cli, dev_run: bool = False,
                 cli_options: frozenset[str] = frozenset(),
                 call_cap: int | None = None, cost_cap: float | None = None, parent: QWidget | None = None,
                 store: QSettings | None = None, daily_refresh: bool = False,
                 refresh_record: Callable[[str | None], str] | None = None) -> None:
        super().__init__(parent)
        self.manager, self.home, self.checkout, self.run = manager, home, checkout, run
        self.conformance_option = conformance_option
        self.cli_options = cli_options  # run --help (feature detection: D-656 --max-tokens)
        #: design §19.2: a live dev run ticks every suite by default, stops at the call cap and must estimate under
        #: the cost cap (p90) to start
        self.dev_run, self.call_cap, self.cost_cap = dev_run, call_cap, cost_cap
        self.store = store  # the GUI's QSettings: the disclosures' remembered state (None: this process only)
        self.setWindowTitle("Live Dev Run" if dev_run else "Run Live")
        self.setAccessibleName("Run live")
        self.resize(1120, 860)
        self.prices: PriceTable | None = None  # agentprov prices list (D-701), loaded in the background
        self.endpoints: dict[str, Endpoint] = load_endpoints(checkout)
        self.opened = [str(p) for p in opened if (Path(p) / "aer").is_dir()]  # --stats-corpus (design §8.3)
        self.catalogue: Catalogue | None = None
        self.catalogues: dict[str, Catalogue | str] = {}  # backend: catalogue, or why there is none
        self.estimate_result: EstimateView | None = None
        self._estimate_for: tuple[str, ...] | None = None  # the estimate argv estimate_result was computed for
        self.live_status: dict[str, str | None] = {}
        self.keys_present: dict[str, bool] = {}
        self.keychain_ok: bool | None = None
        self.start: LiveStart | None = None
        self.preflight_reason: str | None = None  # why Preflight Only… is disabled (see _gate)
        self._dry_seq = 0
        self.model_lists: dict[str, ModelList] = {}  # endpoint -> agentprov models's list (the picker, D-700)
        self._models_seq = 0
        self.identity_dialog: IdentityDialog | None = None
        self.plan_dialog: QDialog | None = None
        #: D-1062: the price refresh's state line ("" until known), and the job it started
        self.prices_line = ""
        self.refresh_job: str | None = None
        self._polling = False
        self._refresh_active = False
        self._refresh_record = refresh_record
        self._closed = False  # AU-NG-2: set when the dialog closes; a late result starts nothing more
        self._build(preset or RunSettings(script=str(DEV_SCRIPT)))
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.refresh_estimate)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(1000)
        self.refresh_timer.timeout.connect(self._poll_refresh)
        self._load_status()
        self._load_catalogue()
        self._keys_refresh()
        self._load_prices()
        if daily_refresh:
            self._daily_refresh()
        self._changed()

    # ------------------------------------------------------------------------------------------ widgets
    def _build(self, s: RunSettings) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self.page = FormPage(name="Run live settings", parent=self)
        body.addWidget(self.page, 1)
        self.summary = SummaryPanel(name="Summary", parent=self)
        body.addWidget(self.summary)
        outer.addLayout(body, 1)
        # D-1064: opened where live runs are refused (a preset, a shortcut), the dialog says why and Start stays off
        self.platform_notice = PlatformNotice("live_runs", name="Live runs on this platform", parent=self.page.column)
        self.page.add(self.platform_notice)
        notifier().changed.connect(self._platform_changed)
        self._build_benchmark(s)
        self._build_model(s)
        self._build_limits()
        self._build_cells(s)
        self._build_save(s)
        self._build_summary()
        self._build_footer(outer)
        for button in self.findChildren(QPushButton):  # Enter starts only through Start… (D-1060 rule 9)
            button.setAutoDefault(button is self.start_btn)
        self.start_btn.setDefault(True)
        self._mode_changed()
        self._scope_changed()
        self._models()

    def _build_benchmark(self, s: RunSettings) -> None:
        sec = FormSection("Benchmark", parent=self.page.column)
        self.backends = live_backends()
        self.source = forms.combo(sec.card, name="Backend")  # the backend picker (user decision 2026-10-22)
        for b in self.backends:
            self.source.addItem(T.line(b.source, 40), b.source)
        index = self.source.findData(s.source)
        self.source.setCurrentIndex(max(0, index))
        self.source.currentIndexChanged.connect(self._backend_changed)
        self.status = StatusBadge("Checking…", name="Live status", kind="neutral", parent=sec.card)
        set_control_tooltip(self.status, "The backend's live status (agentprov info SOURCE --format json). While it is "
                                         "planned or not_possible, only scripted runs can start.")
        sec.add_row("Backend", self.source, trailing=[self.status],
                    tip="The live backend that runs the cells (agentprov run SOURCE). A backend whose environment is "
                        "not built says so, with the command that builds it.")
        self.version = forms.combo(sec.card, name="Benchmark version", editable=True)
        self.version.setCurrentText(s.benchmark_version)
        line = self.version.lineEdit()
        if line is not None:
            line.setPlaceholderText("The backend's default")
        self.version.currentTextChanged.connect(lambda _t: self._changed())
        row = sec.add_row("Benchmark version", self.version, caption_text="Catalogue: loading…",
                          tip="The benchmark version to run (--benchmark-version); the list holds the versions the "
                              "backend's catalogue offers. Blank: the backend's default.")
        self.cat_label = row.caption
        self.cat_label.setAccessibleName("Catalogue status")
        set_setting_tooltip(self.cat_label, "What the backend offers (agentprov run SOURCE --catalogue): its suites, "
                                            "tasks, attacks and benchmark version. No model call, nothing written.")
        self.page.add(sec)

    def _build_model(self, s: RunSettings) -> None:
        sec = FormSection("Model", parent=self.page.column,
                          note="Endpoint, model, key, price and containment appear when Real model is chosen.")
        self.model_section = sec
        card = sec.card
        self.mode = SegmentedControl([("Scripted", "scripted"), ("Real model", "real")], name="Transport",
                                     parent=card, current=0 if s.scripted else 1)
        self.mode.currentIndexChanged.connect(self._mode_and_changed)
        self.mode.set_tip(0, "Replays the script file below (--llm-script): no network, no keys, no cost; the corpus is "
                             "marked test_only.")
        self.mode.set_tip(1, "Calls a model at an endpoint: an R2 run that needs your consent, a containment and, for "
                             "an API endpoint, its key and the call and cost caps.")
        self.mode_note = forms.caption("", name="Transport note", parent=card)
        sec.add_row("Transport", self.mode, trailing=[self.mode_note],
                    tip="Scripted transport replays the script below (--llm-script): no network, no keys, no cost, and "
                        "the corpus is marked test_only. Real model calls an endpoint: an R2 run that needs consent "
                        "and a containment, and the key of an API endpoint.")
        self.script_field = PathField(s.script or str(DEV_SCRIPT), name="Script", parent=card,
                                      choose_name="Choose the script file")
        self.script = self.script_field.edit
        self.script.textChanged.connect(lambda _t: self._changed())
        self.script_row = sec.add_row(
            "Script", self.script_field, caption_text="The scripted replies (SCRIPT.json)", subject=self.script,
            tip="The scripted transport's replies, a JSON file (--llm-script); the shipped dev script by default.")
        self.endpoint = forms.combo(card, name="Endpoint")
        self.endpoint.addItems(sorted(self.endpoints))
        if s.model:
            self.endpoint.setCurrentText(s.model)
        self.endpoint.currentTextChanged.connect(self._endpoint_changed)
        real_rows: list[QWidget] = [sec.add_row(
            "Endpoint", self.endpoint, caption_text="From endpoints.toml",
            tip="The endpoint to call, by its shorthand in the checkout's endpoints.toml (--model).")]
        self.model_id = forms.combo(card, name="Model id", editable=True)
        self.model_id.setCurrentText(s.model_id)
        self.model_id.currentTextChanged.connect(lambda _t: self._changed())
        # the model picker is a client of agentprov models (D-691, D-730; D-700): list, refresh, identity
        self.refresh_models_btn = QPushButton("Refresh List", card)
        self.refresh_models_btn.setAccessibleName("Refresh the provider's model list (network)")
        self.refresh_models_btn.clicked.connect(self._refresh_models)
        self.identity_btn = QPushButton("Identity…", card)
        self.identity_btn.setAccessibleName("Show the local model's identity record")
        self.identity_btn.clicked.connect(self._show_identity)
        set_control_tooltip(self.identity_btn, "Shows the local model's identity record (agentprov models --endpoint "
                                               "NAME --model-id ID); its weight digests are cached after the first "
                                               "time.")
        model_row = sec.add_row(
            "Model", self.model_id, trailing=[self.refresh_models_btn, self.identity_btn],
            tip="The model the endpoint is asked for (--model-id); there is no default. The list comes from agentprov "
                "models for this endpoint, else from the price table.")
        self.models_status = model_row.caption
        self.models_status.setAccessibleName("Model list status")
        set_setting_tooltip(self.models_status,
                            "The state of the endpoint's model list from agentprov models, which fills Model: an API "
                            "provider's cached list (Refresh List fetches it anew) or a local server's own. Other "
                            "endpoints take their ids from the price table.", active=lambda: not self.scripted)
        real_rows.append(model_row)
        self.price_label = SafeLabel("", name="Price", parent=card)
        self.price_label.setWordWrap(True)
        real_rows.append(sec.add_row(
            "Price", self.price_label, caption_text="Per million tokens",
            tip="The model's price as agentprov prices list resolves it, used by the estimate; a missing price is "
                "entered in Settings › Prices.", active=lambda: not self.scripted))
        # shown only for an Anthropic endpoint (and the caps only for an API endpoint): hidden rows show no tooltip
        mt = QWidget(card)
        mt_row = QHBoxLayout(mt)
        mt_row.setContentsMargins(0, 0, 0, 0)
        self.max_tokens_mode = forms.combo(mt, name="Max tokens choice")
        self.max_tokens_mode.addItems(["Harness default (16,000)", "A number"])
        self.max_tokens_mode.currentIndexChanged.connect(lambda _i: self._changed())
        self.max_tokens = IntField(1, 1_000_000, 16_000, name="Max tokens", unset=False, unit="tokens", parent=mt)
        self.max_tokens.valueChanged.connect(lambda _v: self._changed())
        set_control_tooltip(self.max_tokens_mode, "Harness default sends --max-tokens harness-default (16,000, "
                                                  "recorded as a harness policy); a number states the cap yourself.")
        set_control_tooltip(self.max_tokens, "The reply's token cap you state (--max-tokens N).")
        mt_row.addWidget(self.max_tokens_mode, 1)
        mt_row.addWidget(self.max_tokens)
        self.max_tokens_box = sec.add_row(
            "Max tokens", mt, caption_text="Anthropic endpoints (D-656)", subject=self.max_tokens_mode,
            tip="The reply's token cap an Anthropic endpoint requires (--max-tokens): the harness default 16,000 "
                "(recorded as a harness policy) or a number you state. AgentDojo's own 1024 is never used silently.")
        self.key_label = SafeLabel("", name="Key status", parent=card)
        self.key_label.setWordWrap(True)
        self.key_btn = QPushButton("Store Key…", card)
        self.key_btn.setAccessibleName("Store the endpoint key")
        self.key_btn.clicked.connect(self._store_key)
        set_control_tooltip(self.key_btn, "Stores the endpoint's key variable in the OS keychain (agentprov keys set "
                                          "NAME --stdin); the app never shows it again.")
        real_rows.append(sec.add_row(
            "API key", self.key_label, trailing=[self.key_btn], caption_text="Its value is never shown",
            tip="Whether the endpoint's key variable is in the OS keychain. A real run reads it there itself (run "
                "--keychain), never from .env, and its value is never shown.", active=lambda: not self.scripted))
        self.containment = forms.combo(card, name="Containment")
        self.containment.addItems(["", *containment_choices()])  # sandbox-exec on macOS only (G5 P-4)
        # D-1064: where the CLI reports it unavailable (off macOS), shown disabled with the reason
        gate_combo_item(self.containment, "sandbox-exec", platform_limits.current().get("sandbox_exec"))
        self.containment.setCurrentText(s.containment)
        self.containment.currentTextChanged.connect(lambda _t: self._changed())
        real_rows.append(sec.add_row(
            "Containment", self.containment, caption_text="Required for a real model",
            tip="How the worker running the backend is contained (--containment). sandbox-exec (macOS) is enforced by "
                "the probed profile; dedicated-user and vm are your declaration, recorded but not checked."))
        note = forms.caption(DECLARED_CONTAINMENT, name="Containment note", parent=card)
        real_rows.append(sec.add(note))
        self.real_rows = real_rows
        self.page.add(sec)

    def _build_limits(self) -> None:
        # D-725 (live pilot): an API-endpoint run needs both caps; shown once the CLI offers them
        sec = FormSection("Limits", parent=self.page.column,
                          note="A run on an API endpoint, or on a LAN model server (D-1067), needs both caps: billed "
                               "model calls and spend in USD, priced per million tokens. A cell starts only if its "
                               "worst case fits.")
        card = sec.card
        self.max_cost = DecimalField(0, 1_000_000, None, name="Max cost in USD", placeholder="Not set", unit="USD",
                                     parent=card)
        self.use_upper_btn = forms.link_button("Use the quote's upper figure", parent=card,
                                               name="Fill the cost cap from the quote's upper figure")
        self.use_upper_btn.clicked.connect(self.use_quote_upper)
        set_control_tooltip(self.use_upper_btn, "Fills the cost cap with the quote's upper figure (agentprov "
                                                "estimate's p90 cost), rounded up to the cent.")
        sec.add_row("Stop at a cost of", self.max_cost, trailing=[self.use_upper_btn], stretch=False,
                    caption_text="The run stops starting cells here",
                    tip="Spend of the corpus at most, in USD (--max-cost-usd), an upper bound priced from the recorded "
                        "usage at the two prices below.")
        self.max_calls = IntField(1, 10_000_000, None, name="Max billed model calls", placeholder="Not set",
                                  unit="calls", parent=card)
        sec.add_row("Stop after model calls", self.max_calls, stretch=False,
                    caption_text="Preflight probes included",
                    tip="Billed model calls of the corpus at most, preflight probes included (--max-calls).")
        prices = QWidget(card)
        pl = QHBoxLayout(prices)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(8)
        self.price_in = DecimalField(0, 10_000, None, name="Cap price, input side, USD per million tokens", decimals=4,
                                     unset=False, parent=prices)
        self.price_out = DecimalField(0, 10_000, None, name="Cap price, output, USD per million tokens", decimals=4,
                                      unset=False, parent=prices)
        for spin, unit, tip in (
                (self.price_in, "$/M in", "USD per million input-side tokens for the cost cap (--price-in): the highest "
                                          "of input, cache write and cached; filled from the price table."),
                (self.price_out, "$/M out", "USD per million output tokens for the cost cap (--price-out); filled from "
                                            "the price table.")):
            spin.setFixedWidth(100)
            pl.addWidget(spin)
            u = SafeLabel(unit, name=f"{spin.accessibleName()} unit", parent=prices, selectable=False)
            u.setProperty("apvRole", "unit")
            pl.addWidget(u)
            set_control_tooltip(spin, tip)
        pl.addStretch(1)
        sec.add_row("Priced at", prices, caption_text="Filled from the price table")
        for cap in (self.max_calls, self.max_cost, self.price_in, self.price_out):
            cap.valueChanged.connect(lambda _v: self._changed())
        self.caps_box = sec
        self._caps_priced_for: tuple[str, str] | None = None
        self.page.add(sec)

    def _build_cells(self, s: RunSettings) -> None:
        sec = FormSection("What to run", parent=self.page.column)
        card = sec.card
        self.scope = SegmentedControl([("Full benchmark", "full"), ("Choose suites and attacks", "choose")],
                                      name="Scope", parent=card, current=CHOOSE)
        self.scope.currentIndexChanged.connect(self._scope_and_changed)
        self.scope.set_tip(0, "Runs every suite and every attack the backend can run, with the benign cells (the same "
                              "--suite and --attack as ticking them all).")
        self.scope.set_tip(1, "Runs only the suites and attacks ticked below (--suite, --attack).")
        sec.add_row("Scope", self.scope,
                    tip="Full benchmark runs every suite and every attack the backend can run, with the benign cells: "
                        "the same --suite and --attack as ticking them all. Choose suites and attacks picks them below.")
        self.includes = SafeLabel("", name="What the full benchmark includes", parent=card)
        self.includes.setWordWrap(True)
        self.includes_row = sec.add_row("Includes", self.includes)
        self.suites = Checklist(name="Suites", parent=card)
        self.suites.changed.connect(self._changed)
        self.suites_row = sec.add_row(
            "Suites", self.suites, top=True, caption_text="Beside each: user tasks · injection tasks",
            tip="The suites to run (--suite), each with its number of user and injection tasks. Tick at least one.")
        self.attacks = ChipGroup(name="Attacks", parent=card)
        self.attacks.changed.connect(self._changed)
        self.attacks_row = sec.add_row(
            "Attacks", self.attacks, top=True,
            tip="The attacks to run (--attack); none chosen means benign cells only. A DoS attack runs one cell per "
                "user task, and an attack the backend refuses cannot be chosen.")
        self._wanted = (set(s.suites), set(s.attacks))
        self.benign = forms.combo(card, name="Benign cells")
        self.benign.addItems(["include", "exclude", "only"])
        self.benign.setCurrentText(s.benign or "include")
        self.benign.currentTextChanged.connect(lambda _t: self._changed())
        self.benign_row = sec.add_row(
            "Benign cells", self.benign, stretch=False,
            tip="Whether the benign (unattacked) cells are included (the default), excluded or run alone (--benign).")
        self.page.add(sec)
        self.tasks = Disclosure("Task selection and repeats", screen=SCREEN, key="tasks", store=self.store,
                                name="Show task selection and repeats", parent=self.page.column)
        set_control_tooltip(self.tasks.button, "Shows or hides the user and injection tasks to run (--user-tasks, "
                                               "--injection-tasks) and how often each cell is repeated (--repeats).")
        tasks = FormSection("", parent=self.tasks.content)
        self.user_tasks = QLineEdit(s.user_tasks, tasks.card)
        self.user_tasks.setPlaceholderText("All (or ids, or index ranges such as 0-2,5)")
        self.user_tasks.textChanged.connect(lambda _t: self._changed())
        self.user_tasks_row = tasks.add_row(
            "User tasks", self.user_tasks,
            tip="The user tasks of each suite (--user-tasks): all, ids, or index ranges over the tasks sorted by "
                "number, such as 0-2,5. Blank: all.")
        self.injection_tasks = QLineEdit(s.injection_tasks, tasks.card)
        self.injection_tasks.setPlaceholderText("All (or ids, or index ranges)")
        self.injection_tasks.textChanged.connect(lambda _t: self._changed())
        self.injection_tasks_row = tasks.add_row(
            "Injection tasks", self.injection_tasks,
            tip="The injection tasks paired with each attack (--injection-tasks): all, ids, or index ranges such as "
                "0-2,5. Blank: all.")
        self.repeats = _spin(tasks.card, 1, 1000, s.repeats, name="Repeats", placeholder="Default (1)", unit="times")
        self.repeats.valueChanged.connect(lambda _v: self._changed())
        tasks.add_row("Repeats", self.repeats, stretch=False,
                      tip="Independent repeats of each cell (--repeats); default 1.")
        self.tasks.add(tasks)
        self.page.add(self.tasks)

    def _build_save(self, s: RunSettings) -> None:
        sec = FormSection("Save to", parent=self.page.column)
        card = sec.card
        self.campaign = QLineEdit(s.campaign, card)
        self.campaign.setPlaceholderText("Required")
        self.campaign.textChanged.connect(lambda _t: self._changed())
        self.campaign_row = sec.add_row(
            "Campaign name", self.campaign, caption_text="Corpus id: <source>-live-<campaign>",
            tip="The campaign's name (--campaign), required: the corpus id is <source>-live-<campaign>.")
        self.corpus_field = PathField(s.corpus, name="Working corpus", choose_name="Choose the working corpus folder",
                                      folder=True, parent=card,
                                      placeholder=str(self.home / "corpora" / "<source>-live-<campaign>"))
        self.corpus = self.corpus_field.edit
        self.corpus.textChanged.connect(lambda _t: self._changed())
        sec.add_row("Working corpus", self.corpus_field, caption_text="Outside the repository", subject=self.corpus,
                    tip="The working corpus directory (--corpus), outside the repository; DIR.partial while it is a "
                        "working corpus. Blank: corpora/<source>-live-<campaign> under $AGENTPROV_HOME.")
        self.page.add(sec)
        # every other run option (D-654), behind the one Advanced level (D-1060 rule 4)
        self.advanced = Disclosure("Advanced: concurrency, attempts, timeouts, conformance, every other run option",
                                   screen=SCREEN, key="advanced", store=self.store, name="Show more run options",
                                   parent=self.page.column)
        set_control_tooltip(self.advanced.button, "Shows or hides the concurrency, attempts, canary, cell timeout, the "
                                                  "conformance check and every other option of agentprov run, such as "
                                                  "--defence, --defence-endpoint and the Inspect options.")
        runsec = FormSection("Run", parent=self.advanced.content)
        rc = runsec.card
        self.jobs = _spin(rc, 1, 512, s.jobs, name="Concurrent traces", placeholder="Default (1)", unit="traces")
        self.jobs.valueChanged.connect(lambda _v: self._changed())
        self.tune_btn = QPushButton("Tune…", rc)
        self.tune_btn.setAccessibleName("Tune the concurrency with a host preset")
        self.tune_btn.clicked.connect(self.tune)
        set_control_tooltip(self.tune_btn, "Tune… runs agentprov run SOURCE --dry-run with a host preset (--m5ultra "
                                           "unless the options below name another) and shows the concurrency plan; "
                                           "Apply copies its --jobs into Concurrent traces. No cell runs.")
        runsec.add_row("Concurrent traces", self.jobs, trailing=[self.tune_btn], stretch=False,
                       tip="How many traces run at once (--jobs; default 1). Tune… computes one with a host preset; a "
                           "value above the host's maximum is refused, never clamped.")
        self.start_stagger = DecimalField(0, 3600, _seconds(s.extra.get("start_stagger")), name="Start stagger",
                                          trim=True, placeholder="Default (0)", unit="seconds", parent=rc)
        self.start_stagger.valueChanged.connect(lambda _v: self._changed())
        runsec.add_row("Start stagger", self.start_stagger, stretch=False,
                       caption_text="Spreads the workers' first cells over this many seconds",
                       tip="Worker i starts its first cell at i × SECONDS ÷ the concurrent traces, on a fixed schedule "
                           "(--start-stagger; default 0, or the host preset's own stagger). It changes no request and "
                           "is recorded with the run. AgentDojo-PROV's launcher slept a random 0–20 s instead.")
        self.max_attempts = _spin(rc, 1, 100, s.max_attempts, name="Max attempts per unit", placeholder="Default (3)",
                                  unit="attempts")
        self.max_attempts.valueChanged.connect(lambda _v: self._changed())
        runsec.add_row("Attempts per unit", self.max_attempts, stretch=False,
                       tip="The most attempts a unit (one repeat of a cell) gets, counted across invocations: a unit "
                           "that has not settled is attempted again up to this number in all (--max-attempts; default "
                           "3).")
        self.retry_inconsistent = Switch(name="Retry inconsistent units", parent=rc,
                                         checked=bool(s.extra.get("retry_inconsistent")))
        self.retry_inconsistent.toggled.connect(lambda _c: self._changed())
        runsec.add_row("Retry inconsistent units", self.retry_inconsistent, stretch=False,
                       caption_text="Also re-attempts units whose token accounting did not add up",
                       tip="A unit whose every attempt carries the seal issue accounting_inconsistent counts as "
                           "settled; this also re-attempts it, within Attempts per unit (--retry-inconsistent). Each "
                           "model call inside an attempt keeps the harness's own retries (up to 8 tries, rate-limit "
                           "back-off), which are not a setting.")
        self.canary = _spin(rc, 0, 100_000, s.canary, name="Canary cells", placeholder="Default (10)", unit="cells")
        runsec.add_row("Canary cells", self.canary, stretch=False, caption_text="0 turns the canary off",
                       tip="How many of the first cells the canary checks for a misconfiguration (--canary; default "
                           "10). If it finds one while cells remain, the campaign stops.")
        self.cell_timeout = DecimalField(0, 86_400, s.cell_timeout, name="Cell timeout", trim=True,
                                         placeholder="Default (1,800)", unit="seconds", parent=rc)
        self.cell_timeout.valueChanged.connect(lambda _v: self._changed())
        runsec.add_row("Cell timeout", self.cell_timeout, stretch=False,
                       tip="Wall clock per cell before its worker is killed and the session sealed aborted "
                           "(--cell-timeout; default 1800 s).")
        self.conformance = Switch(name="Run the W3C PROV conformance check", parent=rc, checked=True)
        if self.conformance_option is None:
            self.conformance.setEnabled(False)
            set_help_tooltip(self.conformance, "This CLI cannot skip the check yet (G2c-5): the check always runs.")
        self.conformance.clicked.connect(self._conformance_clicked)
        # a disabled switch keeps its explanation above (a gated tip would hide it)
        runsec.add_row("W3C PROV conformance check", self.conformance, stretch=False,
                       caption_text="Validation tier 4",
                       tip=CONFORMANCE_TIP if self.conformance_option is not None else None)
        self.advanced.add(runsec)
        other = FormSection("Other run options", parent=self.advanced.content)
        self.more_inputs: dict[str, QWidget] = {}
        for f in FORMS["run"].fields:
            if f.key in _DIALOG_KEYS:
                continue
            w = _field_widget(f, other.card, s.extra.get(f.key))
            _connect(w, self._changed)
            self.more_inputs[f.key] = w
            other.add_row(f.label, w, tip=field_tip(f), stretch=f.kind not in ("bool", "int"))
        self.advanced.add(other)
        self.page.add(self.advanced)

    def _build_summary(self) -> None:
        p = self.summary
        self.summary_heading = forms.heading("Summary", name="Summary heading", parent=p.inner)
        p.add(self.summary_heading)
        card, lay = p.card(name="Summary figures")
        top = QHBoxLayout()
        top.setSpacing(6)
        self.big = SafeLabel(DASH, name="Summary figure", parent=card)
        self.big.setFont(theme.scaled_font("title"))
        top.addWidget(self.big, 0, Qt.AlignmentFlag.AlignBottom)
        self.big_unit = SafeLabel("cell runs", name="Summary figure unit", parent=card, selectable=False)
        self.big_unit.setProperty("apvRole", "caption")
        top.addWidget(self.big_unit, 1, Qt.AlignmentFlag.AlignBottom)
        lay.addLayout(top)
        self.sub = forms.caption("", name="Summary line", parent=card, role="secondary")
        lay.addWidget(self.sub)
        self.facts = FactGrid(name="Summary facts", parent=card)
        for key in ("cells", "cost", "calls", "tokens_in", "tokens_out", "time", "concurrency"):  # the order shown
            self.facts.set(key, "")
        lay.addWidget(self.facts)
        self.estimate_only = forms.caption("Estimate only: the actual cost can differ.", name="Estimate only",
                                           parent=card)
        lay.addWidget(self.estimate_only)
        self.prices_status = forms.caption("", name="Prices status", parent=card)
        lay.addWidget(self.prices_status)
        self.headline = forms.caption("Estimate: waiting for the plan…", name="Estimate", parent=card)
        self.headline.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        set_control_tooltip(self.headline, "agentprov estimate's headline for these settings (asked again after every "
                                           "change): cost and time at p50 and p90. The app computes no number itself.")
        lay.addWidget(self.headline)
        self.basis_card, blay = p.card(name="How this is worked out")
        title = SafeLabel("How this is worked out", name="How this is worked out", parent=self.basis_card,
                          selectable=False)
        title.setFont(theme.scaled_font("heading"))
        blay.addWidget(title)
        self.basis = forms.caption("", name="Basis of the quote", parent=self.basis_card, role="secondary")
        blay.addWidget(self.basis)
        self.build_priors_btn = forms.link_button("Build cost figures from my corpora…", parent=self.basis_card,
                                                  name="Build cost figures from my corpora")
        self.build_priors_btn.clicked.connect(self.build_priors)
        set_control_tooltip(self.build_priors_btn, "Starts agentprov priors build as a job (R1, confirmed): it counts "
                                                   "calls, tokens and time in every sealed corpus under "
                                                   "$AGENTPROV_HOME/corpora with 8 worker processes, so the quote can "
                                                   "use your own runs, this model family's first. Nothing is written "
                                                   "into a corpus.")
        blay.addWidget(self.build_priors_btn, 0, Qt.AlignmentFlag.AlignLeft)
        self.priors_status = forms.caption("", name="Cost figures status", parent=self.basis_card)
        self.priors_status.setVisible(False)
        blay.addWidget(self.priors_status)
        checks, clay = p.card(name="Before you start")
        title = SafeLabel("Before you start", name="Before you start", parent=checks, selectable=False)
        title.setFont(theme.scaled_font("heading"))
        clay.addWidget(title)
        self.check_lines = [forms.caption("", name=f"Check {i + 1}", parent=checks, role="secondary")
                            for i in range(3)]
        for line in self.check_lines:
            clay.addWidget(line)
        self.ready = StatusBadge("", name="Readiness", parent=checks)
        set_control_tooltip(self.ready, "Whether Start can be pressed. Ready to start: every check passed. Waiting for "
                                        "the estimate: Start waits until agentprov estimate has planned this "
                                        "selection. Blocked: the line under it says what to change first.")
        clay.addWidget(self.ready)
        self.error = forms.caption("", name="Form error", parent=checks, role="secondary")
        clay.addWidget(self.error)
        self.plan_btn = forms.link_button("Show the plan by suite", name="Show the plan by suite", parent=p.inner)
        self.plan_btn.clicked.connect(self.show_plan)
        set_control_tooltip(self.plan_btn, "agentprov estimate's breakdown of the cells, cost and time by suite and by "
                                           "attack, with the source of each group's statistics.")
        p.add(self.plan_btn)
        self.details = ReadOnlyText(name="Estimate details", parent=p.inner, wrap=True)
        self.details.setVisible(False)  # shown in the plan window
        self.command_card = CommandCard(parent=p.inner)
        p.add(self.command_card)
        foot = forms.caption("Start asks for confirmation. A real model also asks for your consent to the cost.",
                             name="Start note", parent=p.inner)
        p.add(foot, after_stretch=True)

    def _build_footer(self, outer: QVBoxLayout) -> None:
        footer = QWidget(self)
        footer.setProperty("apvRole", "footer")
        row = QHBoxLayout(footer)
        row.setContentsMargins(20, 12, 20, 12)
        row.setSpacing(10)
        self.preflight_btn = QPushButton("Preflight Only…", footer)
        self.preflight_btn.setAccessibleName("Run the preflight probe only")
        set_control_tooltip(self.preflight_btn, "Starts a separate R2 job that runs only the endpoint's preflight "
                                                f"probe (up to {PROBE_CALLS} calls; --preflight-only), without the "
                                                "caps.")
        self.preflight_btn.clicked.connect(lambda: self._start(preflight=True))
        row.addWidget(self.preflight_btn)
        row.addStretch(1)
        cancel = QPushButton("Cancel", footer)
        cancel.setAccessibleName("Cancel")
        cancel.clicked.connect(self.reject)
        set_control_tooltip(cancel, "Closes the dialog; nothing starts.")
        row.addWidget(cancel)
        self.start_btn = QPushButton("Start…", footer)
        self.start_btn.setAccessibleName("Start the live run")
        set_control_tooltip(self.start_btn, "Confirms the run (for a real model: the cost, endpoint, model, key "
                                            "variable and containment, with a consent box), then starts agentprov run "
                                            "as a job on the Runs page.")
        self.start_btn.clicked.connect(lambda: self._start(preflight=False))
        row.addWidget(self.start_btn)
        outer.addWidget(footer)

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

    def _scope_and_changed(self, _index: int) -> None:
        self._scope_changed()
        self._changed()

    def _endpoint_changed(self, _text: str) -> None:
        self._models()
        self._load_model_list()
        self._changed()

    @property
    def scripted(self) -> bool:
        return self.mode.currentIndex() == 0

    def full_scope(self) -> bool:
        return self.scope.currentIndex() == FULL

    def _base_url(self) -> str:
        """The run's base URL as far as the app knows it: the form's own, else the entry's default (a value stored in
        the settings, D-699, or in ``.env`` is not visible here)."""
        w = getattr(self, "more_inputs", {}).get("base_url")  # built after the model section
        value = _widget_value(w) if w is not None else None
        if isinstance(value, str) and value.strip():
            return value.strip()
        ep = self._endpoint()
        return ep.base_url if ep is not None else ""

    def _lan(self) -> bool:
        """A local entry's run that the CLI classes ``api`` (D-1067, amending D-721): the LAN opt-in is ticked, or the
        base URL is off loopback. The opt-in alone counts, since the app cannot see a stored LAN base URL."""
        ep = self._endpoint()
        return (not self.scripted and ep is not None and ep.local
                and (self._allow_lan() or not on_loopback(self._base_url())))

    def _api_run(self) -> bool:
        """D-721 as amended by D-1067: a real run is an API-endpoint run unless its entry is local and on loopback."""
        ep = self._endpoint()
        return not self.scripted and ep is not None and (not ep.local or self._lan())

    def _caps_shown(self) -> bool:
        """D-725: a real API-endpoint run (a LAN model server included, D-1067), with a CLI that has the cap options."""
        return self._api_run() and "--max-calls" in self.cli_options

    def _local_consent(self) -> bool:
        """D-726: the local-run consent flag, for a local entry on loopback only (a LAN server takes API consent)."""
        ep = self._endpoint()
        return (not self.scripted and ep is not None and ep.local and not self._lan()
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
            if value is not None and value is not False and value != "":  # 0 == False: a typed 0 is a value
                out[key] = value
        stagger = self.start_stagger.number()
        if stagger:  # 0 is the CLI's default
            out["start_stagger"] = repr(float(stagger))
        if self.retry_inconsistent.isChecked():
            out["retry_inconsistent"] = True
        if self._caps_shown():
            if self.max_calls.value():
                out["max_calls"] = self.max_calls.value()
            if self.max_cost.value():
                # the prices as text: a price of 0 (a LAN server, a free model) is a value the CLI needs, and the
                # builder leaves out a number equal to False
                out.update(max_cost_usd=self.max_cost.value(), price_in=repr(float(self.price_in.value())),
                           price_out=repr(float(self.price_out.value())))
        if self._anthropic():
            out.pop("reasoning_effort", None)  # D-656: the Anthropic element sends no effort
            if out.get("llm_element") == "gateway_compat":
                out.pop("llm_element")
            if "--max-tokens" in self.cli_options:
                out["max_tokens"] = ("harness-default" if self.max_tokens_mode.currentIndex() == 0
                                     else str(self.max_tokens.value()))
        return out

    def _selection(self) -> tuple[tuple[str, ...], tuple[str, ...], str]:
        """The suites, attacks and benign choice: the full benchmark is every suite and every attack that can be
        chosen, with the benign cells (the same arguments as ticking them all)."""
        if self.full_scope():
            return tuple(self.suites.selectable()), tuple(self.attacks.selectable()), ""
        benign = "" if self.benign.currentText() == "include" else self.benign.currentText()
        return tuple(self.suites.checked()), tuple(self.attacks.checked()), benign

    def settings(self) -> RunSettings:
        corpus = self.corpus.text().strip()
        if not corpus and self.campaign.text().strip():
            corpus = str(self.home / "corpora" / f"{self.backend()}-live-{self.campaign.text().strip()}")
        suites, attacks, benign = self._selection()
        full = self.full_scope()
        real = not self.scripted  # rule 3: a hidden row never reaches the argv (AU-NG-6)
        return RunSettings(
            source=self.backend(), corpus=corpus, campaign=self.campaign.text().strip(),
            scripted=self.scripted, script=self.script.text().strip(), model=self.endpoint.currentText(),
            model_id=self.model_id.currentText().strip() if real else "", suites=suites, attacks=attacks,
            user_tasks="" if full else self.user_tasks.text().strip(),
            injection_tasks="" if full else self.injection_tasks.text().strip(), benign=benign,
            benchmark_version=self.version.currentText().strip(), repeats=_spin_value(self.repeats),
            jobs=_spin_value(self.jobs), max_attempts=_spin_value(self.max_attempts), canary=_spin_value(self.canary),
            cell_timeout=self.cell_timeout.value() or None, containment=self.containment.currentText() if real else "",
            extra=self._extra(),
        )  # fmt: skip

    def _endpoint(self) -> Endpoint | None:
        return self.endpoints.get(self.endpoint.currentText())

    def _anthropic_controls(self) -> None:
        anthropic = self._anthropic()
        show = anthropic and "--max-tokens" in self.cli_options
        self.max_tokens_box.setVisible(show)
        caps = self._caps_shown()
        self.caps_box.setVisible(caps)
        self._price_caps()
        self.max_tokens.setEnabled(self.max_tokens_mode.currentIndex() == 1)
        for key in ("reasoning_effort", "llm_element"):  # D-656: refused for an Anthropic endpoint
            w = self.more_inputs.get(key)
            if w is not None:
                w.setEnabled(not anthropic)

    def _mode_changed(self) -> None:
        """Rule 3: the rows of the transport not chosen are hidden (and disabled, as before)."""
        real = not self.scripted
        for w in (self.endpoint, self.model_id, self.key_btn, self.containment):
            w.setEnabled(real)
        self.script.setEnabled(not real)
        self.script_field.button.setEnabled(not real)
        self.script_row.setVisible(not real)
        for row in self.real_rows:
            row.setVisible(real)
        self.model_section.set_note("" if real else "Endpoint, model, key, price and containment appear when Real "
                                                    "model is chosen.")

    def _scope_changed(self) -> None:
        full = self.full_scope()
        for row in (self.suites_row, self.attacks_row, self.benign_row, self.user_tasks_row,
                    self.injection_tasks_row):
            row.setVisible(not full)
        self.includes_row.setVisible(full)

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
        box = getattr(self, "more_inputs", {}).get("allow_lan_endpoint")
        return isinstance(box, QCheckBox) and box.isChecked()

    def _key_stored(self, ep: Endpoint) -> bool:
        return bool(ep.api_key_env) and self.keychain_ok is True and self.keys_present.get(str(ep.api_key_env)) is True

    def _picker_controls(self) -> None:
        ep = self._endpoint()
        real = not self.scripted and ep is not None
        blocked = refresh_blocked(ep, key_stored=self._key_stored(ep)) if ep is not None else "no endpoint"
        self.refresh_models_btn.setVisible(ep is not None and models_mod.is_provider(ep))
        self.refresh_models_btn.setEnabled(real and blocked is None)
        set_help_tooltip(self.refresh_models_btn, blocked or "agentprov models --allow-network: the provider's "
                         "registry host only; no tokens, no cost (R2, confirmed)")
        self.identity_btn.setVisible(ep is not None and ep.local)
        self.identity_btn.setEnabled(real and ep is not None and ep.local and bool(self.model_id.currentText().strip()))

    def _load_model_list(self, argv: list[str] | None = None) -> None:
        if self._closed:
            return
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
            if seq != self._models_seq:  # a newer read replaced this one: its list is never shown or kept
                return
            listed = parse_list(ep, *result)
            self.model_lists[ep.name] = listed
            if self.endpoint.currentText() == ep.name:
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
        if self._closed:
            return
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

    def _platform_changed(self) -> None:
        self.platform_notice.refresh()
        gate_combo_item(self.containment, "sandbox-exec", platform_limits.current().get("sandbox_exec"))
        self._gate()

    def _gate(self) -> str | None:
        """Why Start is disabled (None: enabled). Preflight Only… has the same gate without the caps, which a
        preflight-only run does not take (``self.preflight_reason``)."""
        self._anthropic_controls()
        reason = None
        caps_missing = estimate_missing = False
        status = self.live_status.get(self.backend())
        s = self.settings()
        entry = self.catalogues.get(s.source)
        refused = platform_limits.current().get("live_runs")  # D-1064: the CLI refuses every run here
        sandbox = platform_limits.current().get("sandbox_exec") if s.containment == "sandbox-exec" else None
        if refused is not None:
            reason = refused.message
        elif isinstance(entry, str):
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
            elif sandbox is not None:
                reason = sandbox.message
            elif ep.api_key_env and not ep.local and (self.keychain_ok is False
                                                      or not self.keys_present.get(ep.api_key_env)):
                reason = f"{ep.api_key_env} is not in the keychain (Store Key…)."
            elif self.cost_cap is not None:
                e = self.current_estimate()
                if e is None or e.cost_p90 is None:
                    reason = "The dev run's cost cap needs an estimate with a price first."
                elif float(e.cost_p90) > self.cost_cap:
                    reason = f"The estimate (p90 ${e.cost_p90:.4f}) is above the dev run's cost cap (${self.cost_cap:g})."
            caps_missing = self._caps_shown() and not (self.max_calls.value() and self.max_cost.value())
            estimate_missing = self.current_estimate() is None
        self.preflight_reason = reason
        if reason is None and caps_missing:
            reason = "An API-endpoint run needs both caps: max model calls and max cost (D-725)."
        if reason is None and estimate_missing:  # Preflight Only… needs none: it runs no cell
            reason = ("Waiting for the estimate of this selection: the consent's attempt count (and a dev run's cost "
                      "cap) comes from it.")
        self.start_btn.setEnabled(reason is None)
        self.preflight_btn.setEnabled(self.preflight_reason is None and not self.scripted)
        for button in (self.start_btn, self.preflight_btn):
            set_unavailable_tooltip(button, refused.message if refused is not None else None)
        self.error.set_plain(reason or "")
        self._summary(s, reason)
        return reason

    # ------------------------------------------------------------------------------------------ the summary panel
    def _summary(self, s: RunSettings, reason: str | None) -> None:
        """Rule 8: what the choices add up to. Every figure is the CLI's (the estimate, its quote); the panel only
        lays them out, and says "—" where a figure is unknown."""
        e = self.current_estimate()
        real = not self.scripted
        ep = self._endpoint()
        local = real and ep is not None and ep.local
        self.summary_heading.set_plain("QUOTE FOR THIS RUN" if real and not local else "SUMMARY")
        q: Quote | None = e.quote if e is not None else None
        jobs = q.jobs if q is not None and q.jobs else (s.jobs or 1)  # the concurrency the CLI gave the time at
        traces = f"{jobs} trace" + ("" if jobs == 1 else "s")
        cells = (q.cells if q is not None and q.cells is not None else e.units) if e is not None else None
        if not real:
            self.big.set_plain(f"{cells:,}" if cells is not None else DASH)
            self.big_unit.set_plain("cell runs")
            self.sub.set_plain(self._selection_line(s))
            self.facts.set("cost", "None (scripted)", label="Cost")
            self.facts.set("calls", "None", label="Model calls")
            self.facts.set("concurrency", traces, label="Concurrency")
            for key in ("cells", "tokens_in", "tokens_out", "time"):
                self.facts.set(key, "")
            self.estimate_only.setVisible(False)
            self.basis_card.setVisible(False)
        else:
            p50 = q.usd_p50 if q is not None and q.usd_p50 is not None else (e.cost_p50 if e is not None else None)
            p90 = q.usd_p90 if q is not None and q.usd_p90 is not None else (e.cost_p90 if e is not None else None)
            self.big.set_plain(usd(p50) if not local else "$0")
            self.big_unit.set_plain("USD, typical" if not local else "USD (a local model server bills nothing)")
            upper = (q.p90_aggregation if q is not None and q.p90_aggregation else
                     "upper (sum of per-cell 90th percentiles)")
            upper = upper.removeprefix("upper ").strip("() ") or "sum of per-cell 90th percentiles"
            self.sub.set_plain(f"Upper estimate: {usd(p90)} ({T.line(upper, 120)})" if p90 is not None and not local
                               else self._selection_line(s))
            calls50 = q.calls_p50 if q is not None and q.calls_p50 is not None else (e.calls_p50 if e else None)
            calls90 = q.calls_p90 if q is not None and q.calls_p90 is not None else (e.calls_p90 if e else None)
            secs50 = q.seconds_p50 if q is not None and q.seconds_p50 is not None else (e.seconds_p50 if e else None)
            secs90 = q.seconds_p90 if q is not None and q.seconds_p90 is not None else (e.seconds_p90 if e else None)
            self.facts.set("cells", f"{cells:,}" if cells is not None else DASH, label="Cell runs")
            self.facts.set("calls", _span(calls50, calls90, lambda v: f"{v:,.0f}"), label="Model calls")
            self.facts.set("tokens_in", _span(q.tokens_in_p50 if q else None, q.tokens_in_p90 if q else None,
                                              lambda v: _tokens(v)), label="Input tokens")
            self.facts.set("tokens_out", _span(q.tokens_out_p50 if q else None, q.tokens_out_p90 if q else None,
                                               lambda v: _tokens(v)), label="Output tokens")
            self.facts.set("time", _duration(secs50, secs90) if e is not None else DASH, label=f"Time at {traces}")
            self.facts.set("cost", "")
            self.facts.set("concurrency", "")
            self.estimate_only.setVisible(True)
            self.basis_card.setVisible(True)
            self.basis.set_plain("\n".join(self._basis_lines(e)))
        self.prices_status.set_plain(self.prices_line if real else "")
        self.prices_status.setVisible(bool(self.prices_line) and real)
        self._checks(s, reason)
        self._command(s)

    def _selection_line(self, s: RunSettings) -> str:
        if not s.suites:
            return "No suite chosen yet"
        names = [T.line(x, 40).capitalize() for x in s.suites]
        suites = " · ".join(names) if len(names) <= 2 else f"{len(names)} suites"
        attacks = f"{len(s.attacks)} attack" + ("" if len(s.attacks) == 1 else "s")
        benign = {"": "benign included", "exclude": "benign excluded", "only": "benign only"}.get(s.benign, s.benign)
        return f"{suites} · {attacks} · {benign}"

    def _basis_lines(self, e: EstimateView | None) -> list[str]:
        """How the quote is worked out, as the CLI states it (``quote.basis``, D-1062). A fallback to the figures for
        all models is never called model-specific, and what the CLI does not say is said to be unknown."""
        if e is None:
            return ["The quote appears once the estimate of this selection is in."]
        b = e.quote.basis if e.quote is not None else None
        model = T.line(self.model_id.currentText().strip() or "this model", 120)
        lines: list[str] = []
        if b is None or b.executions is None:
            lines.append("This CLI does not say how many recorded executions the figures rest on; the plan by suite "
                         "names the source of each group's statistics.")
        elif b.executions == 0:
            lines.append("No recorded execution backs these figures: they are your default assumptions (Settings › "
                         "Estimate).")
        else:
            where = {"local": "your sealed corpora", "shipped": "the shipped priors (built from sealed corpora)",
                     "mixed": "your sealed corpora and the shipped priors"}.get(b.priors or "", "the corpora open in "
                                                                                                "the Viewer")
            if b.corpora and b.priors in ("local", "mixed"):
                where += f" ({b.corpora:,} of yours)"
            if b.family_specific is True:
                family = T.line(b.family, 120) if b.family else model
                lines.append(f"From {b.executions:,} recorded executions of {family} in {where}.")
            elif b.family_specific is False and b.family:
                lines.append(f"Partly {T.line(b.family, 120)}'s own: where no run of it is recorded, the figures for "
                             f"all models are used ({b.executions:,} recorded executions in {where}).")
            elif b.family_specific is False:
                lines.append(f"No recorded run of {model} yet, so the figures for all models are used "
                             f"({b.executions:,} recorded executions in {where}). They become model-specific once a "
                             "run of it is sealed and the cost figures are built from your corpora.")
            else:
                lines.append(f"From {b.executions:,} recorded executions in {where}; whether they are this model's "
                             "own is not stated.")
        token_basis = b.token_basis if b is not None else None
        lines.append({CHARS_BASIS: "Tokens are counted as characters / 4 (no recorded usage).",
                      "usage": "Tokens are the usage recorded in past runs.",
                      "mixed": "Tokens are partly recorded usage, partly characters / 4."}.get(
                          token_basis or "", f"Tokens: {T.line(token_basis, 40)}." if token_basis else
                          "Tokens: your default assumptions." if b is not None and b.executions == 0 else
                          "Tokens: the basis is not stated."))
        price = e.price
        source = {"direct": "the provider's list price", "openrouter": "OpenRouter's list price",
                  "override": "your price override", "local": "a local model server (no per-token cost)"}.get(
                      b.price_source if b is not None and b.price_source else "", price.source if price else "")
        as_of = b.price_as_of if b is not None and b.price_as_of else price.as_of if price else ""
        if source or as_of:
            lines.append(f"Prices: {T.line(source or 'the price table', 200)}"
                         + (f", as of {T.line(as_of, 25)}" if as_of else "") + ".")
        else:
            lines.append("Prices: no price for this model yet.")
        if b is not None and b.discounts_assumed is True:
            lines.append("Cached input is priced at the cache rate where past runs recorded cache reads; batch "
                         "discounts are not assumed.")
        elif b is not None and b.discounts_assumed is False:
            lines.append("Batch and cache discounts are not assumed.")
        else:
            lines.append("Whether batch or cache discounts are assumed is not stated.")
        return lines

    def _checks(self, s: RunSettings, reason: str | None) -> None:
        entry = self.catalogues.get(s.source)
        env = ("✓ Backend environment ready" if isinstance(entry, Catalogue) else
               f"× {T.line(entry, 200)}" if isinstance(entry, str) else "… Checking the backend environment")
        if self.scripted:
            key = "✓ No key needed"
        else:
            text = self.key_label.text()
            stored = "stored in the keychain" in text or "not needed" in text
            key = ("✓ " if stored else "! ") + "Key: " + text
        if not s.corpus:
            corpus = "… No working corpus yet (name a campaign)"
        elif self.checkout is not None and _inside(Path(s.corpus), self.checkout):
            corpus = "× The working corpus is inside the repository"
        else:
            corpus = "✓ Corpus location is outside the repository"
        for label, line in zip(self.check_lines, (env, key, corpus), strict=True):
            label.set_plain(line)
        if reason is None:
            self.ready.set_status("Ready to start", "ok")
        elif reason.startswith("Waiting"):
            self.ready.set_status("Waiting for the estimate", "info")
        else:
            self.ready.set_status("Blocked", "bad")

    def run_spec(self, s: RunSettings | None = None, *, preflight: bool = False, consent: bool = True) -> JobSpec:
        """The job Start (or Preflight Only…) starts for these settings: the one builder of its argv, shared by
        :meth:`_start` and the terminal command card. ``consent``: a real model's consent box is ticked (its flag is
        added only then). Keys never reach the argv: a real run reads its key from the keychain (``--keychain``)."""
        s = s or self.settings()
        if preflight:
            s = preflight_settings(s)
        return job_spec(s, consent=consent and not self.scripted, local_consent=self._local_consent(),
                        conformance=self.conformance.isChecked(), conformance_option=self.conformance_option)

    def _command(self, s: RunSettings) -> None:
        """The terminal command card: the exact ``agentprov estimate`` of the quote (a real model) and ``agentprov
        run`` the dialog would start, from the same builders."""
        commands: list[tuple[str, Sequence[str]]] = []
        note = ""
        if not self.scripted:
            with contextlib.suppress(FormError):
                commands.append(("the quote", self._estimate_argv()))
        try:
            commands.append(("the run" if commands else "", self.run_spec(s).argv))
        except FormError as exc:
            note = f"The run's command appears once the form is complete: {exc}"
        self.command_card.set_commands(commands, note=note)

    def use_quote_upper(self) -> None:
        """Fill the cost cap with the quote's upper figure (p90), rounded up to the cent."""
        e = self.current_estimate()
        upper = None
        if e is not None:
            upper = e.quote.usd_p90 if e.quote is not None and e.quote.usd_p90 is not None else e.cost_p90
        if upper is None:
            return
        self.max_cost.setValue(float((upper * 100).to_integral_value(rounding=ROUND_CEILING) / 100))

    def show_plan(self) -> None:
        """The estimate's breakdown by suite and attack (the CLI's lines), in a window of its own."""
        if self.plan_dialog is None:
            dlg = QDialog(self)
            dlg.setWindowTitle("Plan by Suite")
            dlg.setAccessibleName("Plan by suite")
            dlg.resize(760, 520)
            lay = QVBoxLayout(dlg)
            self.details.setParent(dlg)
            self.details.setVisible(True)
            lay.addWidget(self.details, 1)
            box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, dlg)
            box.rejected.connect(dlg.reject)
            lay.addWidget(box)
            self.plan_dialog = dlg
        self.plan_dialog.open()

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
            self._show_status()
        self._gate()

    def _show_status(self) -> None:
        status = self.live_status.get(self.backend())
        if self.backend() not in self.live_status:
            self.status.set_status("Checking…", "neutral")
            return
        kind = {"supported": "ok", "partial": "warn", "planned": "warn", "not_possible": "bad"}.get(status or "",
                                                                                                    "neutral")
        self.status.set_status(f"Live status: {T.line(status or 'unknown', 40)}"
                               + (" (scripted runs only)" if status in GATED else ""), kind)

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
        self._show_status()
        entry = self.catalogues.get(self.backend())
        if not isinstance(entry, Catalogue):
            self.catalogue = None
            self.cat_label.set_plain("Catalogue: " + (T.line(entry, 300) if entry else "loading…"))
            self.suites.set_choices([])
            self.attacks.set_choices([])
            self.includes.set_plain("")
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
        suites = [Choice(s.name, T.line(s.name, 80), f"{len(s.user_tasks)} · {len(s.injection_tasks)}",
                         tip=f"{len(s.user_tasks)} user tasks · {len(s.injection_tasks)} injection tasks (--suite "
                             f"{T.line(s.name, 80)})")
                  for s in cat.suites]
        ticked = [s.name for s in cat.suites if s.name in wanted_suites or (self.dev_run and not wanted_suites)]
        self.suites.set_choices(suites, ticked)
        attacks = []
        for a in cat.attacks:
            detail = "DoS" if a.dos else ""
            tip = "DoS: one cell per user task. " if a.dos else ""
            if a.needs:
                needs = ", ".join(T.line(n, 40) for n in a.needs)
                detail = (detail + " · " if detail else "") + f"needs {needs}"
                tip += f"Needs {needs}: set it under Advanced."
            if a.refused:
                tip = "Refused by the backend: " + a.refused
            attacks.append(Choice(a.name, T.line(a.name, 80), detail, tip=tip.strip() or f"--attack {a.name}",
                                  enabled=not a.refused))
        self.attacks.set_choices(attacks, [a.name for a in cat.attacks if a.name in wanted_attacks])
        n_attacks = len(self.attacks.selectable())
        self.includes.set_plain(f"{len(cat.suites)} suite" + ("" if len(cat.suites) == 1 else "s")
                                + f" · {n_attacks} attack" + ("" if n_attacks == 1 else "s") + " · benign cells")
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
        if self._closed:
            return

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

    # ------------------------------------------------------------------ the daily price refresh (D-1062)
    def _daily_refresh(self) -> None:
        """Ask ``agentprov prices status`` when the prices were last refreshed; start the refresh job when today's is
        still due. Nothing here blocks the dialog."""
        if not self.manager.cli.available or self._closed:
            return

        def work(_s: object) -> tuple[int, bytes, bytes]:
            return self.run(self.manager, list(pricerefresh.STATUS_ARGV), timeout=60)

        submit(self, work, self._status_for_refresh, lambda _code: None)

    def _status_for_refresh(self, result: tuple[int, bytes, bytes]) -> None:
        if self._refresh_active or self._closed:
            return  # a refresh this dialog started is under way; its end sets the line
        status = pricerefresh.parse_status(result[0], result[1])
        today = dt.date.today()
        attempted = self._refresh_record(None) if self._refresh_record is not None else ""
        if status is not None and status.refreshed_at is not None:
            self.prices_line = f"Prices refreshed {pricerefresh.local_time_text(status.refreshed_at, today=today)}"
        if status is not None and status.auto_refresh is False:
            self.prices_line = ((self.prices_line + "; t") if self.prices_line else "T") + \
                "he daily refresh is off (setting prices.auto_refresh)"
        if not pricerefresh.due(status, attempted=attempted, today=today):
            self._gate()
            return
        if self._refresh_record is not None:
            self._refresh_record(today.isoformat())
        self._refresh_active = True
        self.prices_line = "Refreshing prices (agentprov prices refresh)…"
        # --if-stale: the CLI itself fetches only when no snapshot was written today and the setting is on
        spec = build_spec(FORMS["prices_refresh"], {"if_stale": True}, label="Daily price refresh")

        def spawn(_s: object) -> str:
            return self.manager.spawn(spec).job_id

        def started(job_id: str) -> None:
            self.refresh_job = job_id
            self.refresh_timer.start()

        def refused(code: str) -> None:
            self._refresh_failed(code)

        submit(self, spawn, started, refused)
        self._gate()

    def _poll_refresh(self) -> None:
        """Once a second while the refresh job runs: its state (one read at a time). The job list is refreshed on the
        UI thread, as the Runs page refreshes it (AU-NG-2: a refresh in the pool could replace the list under the page
        and drop its notes, such as a requested stop); only the stderr tail is read in the pool."""
        job_id = self.refresh_job
        if job_id is None or self._closed:
            self.refresh_timer.stop()
            return
        if self._polling:
            return
        self._polling = True
        self.manager.refresh()
        job = self.manager.jobs.get(job_id)

        def work(_s: object) -> tuple[str, int | None, str]:
            if job is None:
                return "ended", None, "the job is no longer listed"
            reason = ""
            if job.state != "running" and job.exit_code != 0:
                try:
                    reason = last_line(job.file("stderr.txt").read_bytes()[-8192:])
                except OSError:
                    reason = ""
            return job.state, job.exit_code, reason

        def done(result: tuple[str, int | None, str]) -> None:
            self._polling = False
            state, code, reason = result
            if state == "running" or self.refresh_job is None or self._closed:
                return
            self.refresh_timer.stop()
            self.refresh_job = None
            self._refresh_active = False
            if code == 0:
                self.prices_line = "Prices refreshed " + pricerefresh.local_time_text(dt.datetime.now(dt.UTC))
                self._load_prices()  # the estimate is asked again with the new prices (_changed)
                self._daily_refresh()  # the snapshot's own time (written_at) replaces the job's end time
            else:
                self._refresh_failed(reason or f"exit {code}")

        def failed(code: str) -> None:
            self._polling = False
            self._refresh_failed(code)

        submit(self, work, done, failed)

    # ------------------------------------------------------------------ local cost figures (agentprov priors build)
    def build_priors(self) -> None:
        """Start ``agentprov priors build --jobs 8`` as a job after its R1 confirmation (D-1062); the estimate is asked
        again when it ends, so the quote can rest on the user's own sealed corpora."""
        try:
            spec = build_spec(FORMS["priors_build"], {"jobs": PRIORS_JOBS}, label="Build cost figures from my corpora")
        except FormError as exc:
            self._priors_line(f"Not started: {exc}")
            return
        confirmed = confirm(self, spec, " ".join(["agentprov", *spec.argv]))
        if confirmed is None:
            return
        self.build_priors_btn.setEnabled(False)
        self._priors_line("Building cost figures from your sealed corpora (agentprov priors build)…")

        def started(job_id: str) -> None:
            self._watch_job(job_id, self._priors_built)

        def refused(code: str) -> None:
            self.build_priors_btn.setEnabled(True)
            self._priors_line(f"Not started: {T.line(code, 200)}")

        submit(self, lambda _s: self.manager.spawn(confirmed).job_id, started, refused)

    def _priors_built(self, code: int | None, reason: str) -> None:
        self.build_priors_btn.setEnabled(True)
        if code == 0:
            self._priors_line("Cost figures built from your sealed corpora; the quote is asked again.")
            self._changed()
        else:
            self._priors_line(f"Building cost figures failed: {T.line(reason or f'exit {code}', 200)}")

    def _priors_line(self, text: str) -> None:
        self.priors_status.set_plain(text)
        self.priors_status.setVisible(bool(text))

    def _watch_job(self, job_id: str, ended: Callable[[int | None, str], None]) -> None:
        """Once a second until the job ends: then ``ended(exit code, the stderr's last line)``. The job list is refreshed
        on the UI thread and only the stderr tail read in the pool (AU-NG-2, as :meth:`_poll_refresh`); a closed dialog
        stops following."""
        timer = QTimer(self)
        timer.setInterval(1000)
        busy = [False]
        holder: list[Job | None] = [None]

        def work(_s: object) -> tuple[str, int | None, str]:
            job = holder[0]
            if job is None:
                return "ended", None, "the job is no longer listed"
            reason = ""
            if job.state != "running" and job.exit_code != 0:
                try:
                    reason = last_line(job.file("stderr.txt").read_bytes()[-8192:])
                except OSError:
                    reason = ""
            return job.state, job.exit_code, reason

        def done(result: tuple[str, int | None, str]) -> None:
            busy[0] = False
            state, code, reason = result
            if state != "running" and timer.isActive():
                timer.stop()
                timer.deleteLater()
                ended(code, reason)

        def failed(code: str) -> None:
            busy[0] = False
            timer.stop()
            timer.deleteLater()
            ended(None, code)

        def tick() -> None:
            if self._closed:
                timer.stop()
                timer.deleteLater()
            elif not busy[0]:
                busy[0] = True
                self.manager.refresh()
                holder[0] = self.manager.jobs.get(job_id)
                submit(self, work, done, failed)

        timer.timeout.connect(tick)
        timer.start()

    def _refresh_failed(self, reason: str) -> None:
        self.refresh_timer.stop()
        self.refresh_job = None
        self._refresh_active = False
        as_of = ""
        if self.prices is not None:
            as_of = self.prices.refreshed_as_of or self.prices.shipped_as_of
        self.prices_line = (f"Using prices of {T.line(as_of, 10)}" if as_of else "Using the stored prices") + \
            f" (refresh failed: {T.line(reason, 200)})"
        self._gate()

    def _estimate_argv(self) -> tuple[str, ...]:
        """``agentprov estimate`` for the current selection (FormError: the form cannot be built)."""
        s = self.settings()
        ep = self._endpoint()
        status = self.live_status.get(s.source)
        names = key_names(ep.api_key_env if ep else None, optional=bool(ep and ep.local))
        real_ok = (not self.scripted and status not in GATED and status is not None
                   and all(self.keys_present.get(n) for n in names))
        return estimate_argv(s, real_allowed=real_ok, stats_corpora=self.opened)

    def current_estimate(self) -> EstimateView | None:
        """The estimate, only while the selection is the one it was computed for: a changed selection's estimate is
        pending (or failed), and the old one must not gate Start or fill the consent text."""
        if self.estimate_result is None:
            return None
        try:
            argv = self._estimate_argv()
        except FormError:
            return None
        return self.estimate_result if argv == self._estimate_for else None

    def _no_estimate(self, headline: str) -> None:
        self._dry_seq += 1  # AU-GUI-6: an estimate (or its failure) still in flight is dropped when it lands
        self.estimate_result = self._estimate_for = None
        self.headline.set_plain(headline)
        self._gate()

    def refresh_estimate(self) -> None:
        if self._closed:
            return
        s = self.settings()
        if not s.suites or not self.manager.cli.available:
            self.details.setPlainText("")
            self._no_estimate("Estimate: tick a suite (and attacks) to see the cost.")
            return
        try:
            argv = self._estimate_argv()
        except FormError as exc:
            self._no_estimate(f"Estimate: {exc}")
            return
        self._dry_seq += 1
        seq = self._dry_seq
        self.headline.set_plain("Estimate: planning and pricing the cells (agentprov estimate)…")

        def work(_s: object) -> tuple[int, tuple[str, ...], int, bytes, bytes]:
            return (seq, argv, *self.run(self.manager, list(argv), timeout=600))  # --keychain: the CLI reads it

        def failed(code: str) -> None:
            if seq == self._dry_seq:  # a newer selection is being estimated, or has none
                self._no_estimate(f"Estimate: {code}")

        submit(self, work, self._estimate_loaded, failed)

    def _estimate_loaded(self, result: tuple[int, tuple[str, ...], int, bytes, bytes]) -> None:
        seq, argv, code, out, err = result
        if seq != self._dry_seq:
            return  # a newer selection is being estimated
        if code != 0:
            tail = T.line(err.decode("utf-8", "replace").strip().splitlines()[-1] if err.strip() else "", 300)
            self._no_estimate(f"Estimate: agentprov estimate ended with exit {code}: {tail}")
            return
        try:
            self.estimate_result = parse_estimate(out)
        except PlanError as exc:
            self._no_estimate(f"Estimate: the estimate is unusable ({exc})")
            return
        self._estimate_for = argv
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
        """§8.1 step 4: ``run --dry-run`` with a host preset (the advanced options: preset, m5ultra and the model-size
        fields; default ``--m5ultra``) prints the concurrency plan; Apply copies its ``--jobs`` into the form. R0."""
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
            # no --jobs: the plan's computed jobs is what Tune offers, never the form's own number (AU-RN-6)
            spec = build_spec(FORMS["run"], {"source": s.source, "dry_run": True, **extra})
        except FormError as exc:
            self.error.set_plain(f"Tune: {exc}")
            return
        argv = [*spec.argv[:-1], "--json", spec.argv[-1]]
        code, out, err = run_off_ui(self, lambda: self.run(self.manager, argv, timeout=120))
        jobs = None
        try:
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
            env, held = ep.api_key_env, [value]  # AU-GUI-3: stored from the pool; the holder is emptied after
            try:
                run_off_ui(self, lambda: keychain.store(self.manager.cli, env, held[0]))
            except keychain.KeychainError as exc:
                safe_message_box(self, "Key not stored", "The key was not stored.",
                                 informative=T.line(exc.code, 60)).exec()
            held.clear()
            del value
        self._keys_refresh()

    def _conformance_clicked(self, checked: bool) -> None:
        if not checked and not conformance_warning(self):
            self.conformance.setChecked(True)
        self._changed()

    def done(self, r: int) -> None:
        """Closing (Start, Cancel, Esc) ends the dialog's own work (AU-NG-2): its timers stop, and a result still in
        flight starts nothing more (no prices list or status, no estimate with ``--keychain``, no further polls) for a
        window nobody sees. A refresh or priors job it started runs on as a job of the Runs page."""
        self._closed = True
        self.timer.stop()
        self.refresh_timer.stop()
        super().done(r)

    def _start(self, *, preflight: bool) -> None:
        reason = self._gate()
        if (self.preflight_reason if preflight else reason) is not None:
            return
        s = self.settings()
        consent = False
        if not self.scripted:
            consent = self.confirm_costs(preflight_settings(s) if preflight else s, preflight=preflight)
            if not consent:
                return
        try:
            spec = self.run_spec(s, preflight=preflight, consent=consent)
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
        e = self.current_estimate()
        attempts = 1 if preflight else (e.attempts_due if e else 0)
        dlg = QDialog(self)
        dlg.setWindowTitle("Confirm: Run Live" + (" (preflight only)" if preflight else ""))
        dlg.setAccessibleName("Confirm the live run")
        lay = QVBoxLayout(dlg)
        host = T.line(self._base_url(), 200)
        lines = [TIER_TEXT["R2"], f"Endpoint: {T.line(s.model, 40)} ({host})", f"Model: {T.line(s.model_id, 120)}",
                 f"Key variable: {T.line(ep.api_key_env if ep and ep.api_key_env else 'none', 64)} (from the "
                 "keychain; its value is never shown)", f"Containment: {T.line(containment_line(s.containment), 120)}"]
        if preflight:
            lines.append(f"Preflight only: up to {PROBE_CALLS} probe calls to the endpoint (another only while the "
                         "reply is unconfirmed), then the job ends. A preflight-only run takes no caps.")
        elif e is not None:
            lines += [T.line(x, 600) for x in e.text[:2]]  # the CLI's headline (cost, time) and plan lines
            stagger = s.extra.get("start_stagger")
            lines.append(f"{e.units:,} unit(s) due; --jobs {s.jobs or 1}"
                         + (f", first starts spread over {float(stagger):g} s" if stagger else ""))
            if e.cost_worst is not None:
                lines.append(f"Worst case (every due attempt at p90): ${e.cost_worst:.4f}")
        if not preflight:
            lines.append(f"Before the first cell, the preflight probe makes up to {PROBE_CALLS} calls, charged to the "
                         "caps.")
        if self._caps_shown() and not preflight:
            lines.append(f"Caps (D-725): at most {s.extra.get('max_calls', 0):,} billed model calls and "
                         f"${float(s.extra.get('max_cost_usd', 0)):,.2f}, priced at ${float(s.extra.get('price_in', 0))}"
                         f" / ${float(s.extra.get('price_out', 0))} per million tokens in / out")
        if self._lan():  # D-1067: an API-endpoint run, because its data leaves this machine
            lines.append("A LAN model server: prompts and replies leave this machine over plain http, so the caps and "
                         "API consent apply, as for an API endpoint (D-1067).")
        else:
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


#: the run fields the dialog's own controls set (everything else is under the advanced options)
_DIALOG_KEYS: Final = frozenset({
    "source", "corpus", "campaign", "suite", "benchmark_version", "user_tasks", "attack", "injection_tasks", "benign",
    "model", "model_id", "llm_script", "repeats", "max_attempts", "canary", "cell_timeout", "jobs", "start_stagger",
    "retry_inconsistent", "containment",
    "dry_run", "preflight_only", "max_tokens", "max_calls", "max_cost_usd", "price_in", "price_out"})


def _seconds(value: Any) -> float | None:
    """A stored seconds value (a number or its text) as a float, else None."""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and number >= 0 else None


def _field_widget(f: Field, parent: QWidget, value: Any) -> QWidget:
    """The control of a run field under the advanced options (D-1060 rule 6: a switch for on/off, a short number
    field whose grey placeholder means unset)."""
    w: QWidget
    if f.kind == "bool":
        w = Switch(name=f.label, parent=parent, checked=bool(value))
    elif f.kind == "choice":
        box = forms.combo(parent, name=f.label)
        box.addItems([c for c in f.choices])
        if value in f.choices:
            box.setCurrentText(str(value))
        w = box
    elif f.kind == "int":
        w = _spin(parent, 0, 10_000_000, value if isinstance(value, int) and not isinstance(value, bool) else None,
                  name=f.label)
    else:
        line = QLineEdit(parent)
        if value is not None:
            line.setText(str(value))
        w = line
    w.setAccessibleName(f.label)
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
