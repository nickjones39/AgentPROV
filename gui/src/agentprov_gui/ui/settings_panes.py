"""Settings panes added in G2: Jobs, Compute (D-432), Continuous integration (D-431, D-432) and Dev runs (D-544).

Every value is an ``agentprov settings`` key (D-703; reverse CLI parity D-700): a pane reads its prefix with
``settings list`` and saves only what changed with ``settings set`` / ``unset`` (:class:`CliSettingsPane`), so
the CLI's schema is the check and a value the GUI shows is one the CLI uses.

* **Jobs** (``jobs.*``): what ``agentprov jobs prune`` keeps by default; whether batches go on after exit 4 or 70.
* **Compute** (``compute.*``): the machine preset (``--m5ultra`` or a named ``--preset``, used by Run live), default
  ``--jobs`` per command (0 = host default), whether heavy jobs go through the shared job queue
  (``tools/suite_queue.py --class import``) with their ``--cpu`` reservation, the queue's machine budget (which
  ``agentprov jobs start`` gives queued jobs as ``AGENTPROV_JOB_CPU_BUDGET`` and ``AGENTPROV_JOB_MEM_GIB_BUDGET``),
  the test gate's ``-n``, and the ingest limits shown read-only (a corpus's identity; a profile changes them).
* **Continuous integration** (``ci.default_target``): Local (``tools/ci_local.py`` through the queue; shown
  unavailable until the checkout has it), GitHub-hosted (``gh workflow run ci.yml``: R2, it spends Actions minutes),
  the ``CI_ON_PUSH`` toggle and the self-hosted runner (``CI_RUNNER``; "not configured" until a runner is
  registered). The GUI stores no token.
* **Dev runs** (``devrun.*``): every D-544 setting, with Reset to defaults.
* **Local models** (``local_models.*``, D-828): a local model's folder, weight size, active parameters, context and KV
  cache per trace, which ``run`` uses when the flag is not given.
"""

from __future__ import annotations

import math
import os
import re
from dataclasses import fields as dc_fields
from pathlib import Path
from typing import Any, ClassVar, Final

from agentprov.devrun import plan as devrun
from agentprov.ingest.limits import IngestLimits
from PySide6.QtWidgets import QCheckBox, QComboBox, QLineEdit, QPushButton, QSpinBox, QWidget

from agentprov_gui import text as T
from agentprov_gui.ui.safe import ReadOnlyText, SafeForm, SafeLabel

__all__ = ["WORKER_COMMANDS", "CiPane", "CliSettingsPane", "ComputePane", "DevRunPane", "JobsPane", "LocalModelsPane"]

WORKER_COMMANDS: Final = ("import", "derive", "recompute", "validate", "verify", "render")


def int_setting(cfg: Any, key: str, default: int, lo: int, hi: int) -> int:
    """``cfg[key]`` as an int clamped to ``[lo, hi]`` (the spin box's range). A missing value, the wrong JSON type, a
    bool, a non-finite number or a string ``int()`` rejects gives ``default`` (GR-31: a corrupted setting never
    crashes the dialog or a job start)."""
    value = cfg.get(key, default) if isinstance(cfg, dict) else default
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return default
    try:
        n = int(value)
    except (ValueError, OverflowError):
        return default
    return min(max(n, lo), hi)


class CliSettingsPane(QWidget):
    """A pane whose values are ``agentprov settings`` keys under :attr:`PREFIX` (D-700, D-703). The stored values are
    read in the background; until they arrive the pane is disabled and :meth:`save` writes nothing. Saving writes only
    the keys that changed (:func:`settings_client.write`); a refused value is listed. :attr:`KEYS` maps each input
    widget's attribute name to its key (the reverse-parity registry, D-700)."""

    PREFIX: str = ""
    TITLE: str = "Settings"
    KEYS: ClassVar[dict[str, str]] = {}

    def __init__(self, checkout: Path | None, parent: QWidget | None = None, *, cli: Any = None) -> None:
        """``cli`` (a :data:`settings_client.Caller`) defaults to the checkout's CLI."""
        super().__init__(parent)
        from agentprov_gui.jobs.manager import CliLocator

        self.checkout = checkout
        self.cli = CliLocator.for_checkout(checkout) if cli is None else cli
        self.loaded: dict[str, Any] | None = None
        self.form = SafeForm(self)
        self.build()
        self.setEnabled(False)
        from agentprov_gui import settings_client
        from agentprov_gui.ui.worker import submit

        submit(self, lambda _s: settings_client.read(self.cli, self.PREFIX), self._loaded,
               lambda _code: self.load_failed())

    def load_failed(self) -> None:
        """The stored values could not be read: the pane stays disabled."""

    def build(self) -> None:  # pragma: no cover - every pane overrides it
        raise NotImplementedError

    def show_values(self, values: dict[str, Any]) -> None:  # pragma: no cover
        raise NotImplementedError

    def values(self) -> dict[str, Any]:  # pragma: no cover
        """The keys to store; a key at its default is left out, so saving unsets it."""
        raise NotImplementedError

    def _loaded(self, values: dict[str, Any] | None) -> None:
        if values is None:
            self.load_failed()
            return
        self.loaded = values
        self.show_values(values)
        self.setEnabled(True)

    def save(self) -> None:
        if self.loaded is None:
            return
        from agentprov_gui import settings_client

        refused = settings_client.write(self.cli, self.loaded, self.values())
        if refused:
            from agentprov_gui.ui.safe import safe_message_box

            safe_message_box(self, self.TITLE, "Some settings were refused and not saved.",
                             informative="; ".join(T.line(r, 200) for r in refused)).exec()


def _number(text: str) -> float | None:
    try:
        value = float(text.strip())
    except (ValueError, OverflowError):
        return None
    return value if math.isfinite(value) else None


class JobsPane(CliSettingsPane):
    """``jobs.*``: what ``agentprov jobs prune`` keeps by default, and whether batches go on after exit 4 or 70."""

    PREFIX, TITLE = "jobs.", "Jobs settings"
    KEYS: ClassVar[dict[str, str]] = {
            "retention": "jobs.retention", "retention_days": "jobs.retention_days", "continue_on_failure": "jobs.continue_on_failure"}

    def build(self) -> None:
        self.retention = QSpinBox(self)
        self.retention.setRange(10, 10_000)
        self.retention.setValue(200)
        self.form.add("Keep the last N ended jobs (agentprov jobs prune; deletes only with --yes)", self.retention)
        self.retention_days = QSpinBox(self)
        self.retention_days.setRange(1, 3650)
        self.retention_days.setValue(90)
        self.form.add("…and none older than D days", self.retention_days)
        self.continue_on_failure = QCheckBox(self)
        self.form.add("Batches continue after exit 4 or 70", self.continue_on_failure)
        self.form.add("Progress level", SafeLabel("status (steps costs real I/O on large runs)", name="Progress level",
                                                  parent=self))

    def show_values(self, values: dict[str, Any]) -> None:
        self.retention.setValue(int_setting(values, "jobs.retention", 200, 10, 10_000))
        self.retention_days.setValue(int_setting(values, "jobs.retention_days", 90, 1, 3650))
        self.continue_on_failure.setChecked(values.get("jobs.continue_on_failure") is True)

    def values(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.retention.value() != 200:
            out["jobs.retention"] = self.retention.value()
        if self.retention_days.value() != 90:
            out["jobs.retention_days"] = self.retention_days.value()
        if self.continue_on_failure.isChecked():
            out["jobs.continue_on_failure"] = True
        return out


class ComputePane(CliSettingsPane):
    """``compute.*``: the machine preset, default ``--jobs`` per command, the live start stagger, the job queue (on or
    off, its per-job reservation and its machine budget, which ``agentprov jobs start`` gives queued jobs), the test
    gate's ``-n``; the ingest limits are shown read-only (they are part of a corpus's identity)."""

    PREFIX, TITLE = "compute.", "Compute settings"
    PRESETS: Final = ("This machine (auto)", "--m5ultra", "named preset")
    KEYS: ClassVar[dict[str, str]] = {
            "preset": "compute.preset", "preset_name": "compute.preset", "stagger": "compute.start_stagger",
            "queue": "compute.queue_heavy", "queue_cpu": "compute.queue_cpu", "cpu_budget": "compute.cpu_budget",
            "mem_budget": "compute.mem_gib_budget", "gate_n": "compute.gate_n",
            **{f"jobs.{cmd}": f"compute.jobs.{cmd}" for cmd in WORKER_COMMANDS}}

    def build(self) -> None:
        form = self.form
        self.preset = QComboBox(self)
        self.preset.addItems(list(self.PRESETS))
        form.add("Machine preset (Run live's Tune)", self.preset)
        self.preset_name = QLineEdit("", self)
        form.add("Preset name (--preset NAME)", self.preset_name)
        self.jobs: dict[str, QSpinBox] = {}
        for cmd in WORKER_COMMANDS:
            spin = QSpinBox(self)
            spin.setRange(0, 512)
            self.jobs[cmd] = spin
            form.add(f"Default --jobs for {cmd} (0 = host default: min(CPUs, ⌊0.75 RAM / 4 GiB⌋))", spin)
        self.stagger = QLineEdit("", self)
        form.add("Live --start-stagger (seconds)", self.stagger)
        self.queue = QCheckBox(self)
        self.queue.setChecked(True)
        form.add("Run heavy jobs through the shared job queue (--class import)", self.queue)
        self.queue_cpu = QSpinBox(self)
        self.queue_cpu.setRange(1, 256)
        self.queue_cpu.setValue(2)
        form.add("Queue reservation per GUI job (--cpu)", self.queue_cpu)
        self.cpu_budget = QLineEdit("", self)
        self.cpu_budget.setPlaceholderText("default: CPUs − 2")
        form.add("Queue CPU budget (AGENTPROV_JOB_CPU_BUDGET)", self.cpu_budget)
        self.mem_budget = QLineEdit("", self)
        self.mem_budget.setPlaceholderText("default: 75 % of RAM")
        form.add("Queue memory budget, GiB (AGENTPROV_JOB_MEM_GIB_BUDGET)", self.mem_budget)
        self.gate_n = QSpinBox(self)
        self.gate_n.setRange(1, 256)
        self.gate_n.setValue(10)
        form.add("Test gate workers (pytest -n)", self.gate_n)
        if os.name != "posix":  # G5 P-3: tools/suite_queue.py locks with fcntl; Windows has no job queue in v0.1
            for w in (self.queue, self.queue_cpu, self.cpu_budget, self.mem_budget):
                w.setEnabled(False)
            form.add("Job queue", SafeLabel("not available on Windows (tools/suite_queue.py needs fcntl): jobs start "
                                            "directly", name="Job queue on Windows", parent=self))
        limits = IngestLimits()
        shown = ReadOnlyText(name="Ingest limits (read-only)", parent=self, wrap=True)
        shown.setPlainText("\n".join(f"{f.name} = {getattr(limits, f.name)}" for f in dc_fields(limits)
                                     if f.name != "zip_methods"))
        shown.setMaximumHeight(140)
        form.add("Ingest limits (read-only; a profile's [import] limits may raise them, up to 64 MiB)", shown)

    def show_values(self, values: dict[str, Any]) -> None:
        preset = values.get("compute.preset")
        if preset == "m5ultra":
            self.preset.setCurrentText("--m5ultra")
        elif isinstance(preset, str) and preset:
            self.preset.setCurrentText("named preset")
            self.preset_name.setText(preset)
        for cmd, spin in self.jobs.items():
            spin.setValue(int_setting(values, f"compute.jobs.{cmd}", 0, 0, 512))
        for line, key in ((self.stagger, "compute.start_stagger"), (self.cpu_budget, "compute.cpu_budget"),
                          (self.mem_budget, "compute.mem_gib_budget")):
            value = values.get(key)
            line.setText(f"{value:g}" if isinstance(value, int | float) and not isinstance(value, bool) else "")
        self.queue.setChecked(values.get("compute.queue_heavy", True) is not False)
        self.queue_cpu.setValue(int_setting(values, "compute.queue_cpu", 2, 1, 256))
        self.gate_n.setValue(int_setting(values, "compute.gate_n", 10, 1, 256))

    def values(self) -> dict[str, Any]:
        """A text field the schema would refuse is left out (so it reads as unset: GR-30, GR-31)."""
        out: dict[str, Any] = {}
        name = self.preset_name.text().strip()
        if self.preset.currentText() == "--m5ultra":
            out["compute.preset"] = "m5ultra"
        elif self.preset.currentText() == "named preset" and name:
            out["compute.preset"] = name
        out.update({f"compute.jobs.{cmd}": spin.value() for cmd, spin in self.jobs.items() if spin.value()})
        stagger = _number(self.stagger.text())
        if stagger is not None and 0 <= stagger <= 3600:
            out["compute.start_stagger"] = stagger
        if not self.queue.isChecked():
            out["compute.queue_heavy"] = False
        if self.queue_cpu.value() != 2:
            out["compute.queue_cpu"] = self.queue_cpu.value()
        cpu = self.cpu_budget.text().strip()
        if re.fullmatch(r"[0-9]{1,4}", cpu, re.ASCII) and 1 <= int(cpu) <= 4096:
            out["compute.cpu_budget"] = int(cpu)
        mem = _number(self.mem_budget.text())
        if mem is not None and 0.001 <= mem <= 1_000_000:
            out["compute.mem_gib_budget"] = mem
        if self.gate_n.value() != 10:
            out["compute.gate_n"] = self.gate_n.value()
        return out


class CiPane(CliSettingsPane):
    """CI targets (D-431). Every action that runs CI or changes a repository variable is an R2 job with its own
    confirmation, started from Runs; ``ci.default_target`` is stored but not used yet (GR-33)."""

    PREFIX, TITLE = "ci.", "CI settings"
    TARGETS: Final = {"local": "Local (tools/ci_local.py)", "github": "GitHub-hosted",
                      "mac-studio": "Self-hosted runner"}
    KEYS: ClassVar[dict[str, str]] = {"target": "ci.default_target"}

    def build(self) -> None:
        form = self.form
        self.target = QComboBox(self)
        self.target.addItems(list(self.TARGETS.values()))
        form.add("Default CI target (not used yet; each CI run is chosen in Runs › New Job)", self.target)
        local = self.checkout is not None and (self.checkout / "tools" / "ci_local.py").is_file()
        form.add("Local runner", SafeLabel("available: Runs › New Job › Run CI locally (it queues itself in the shared "
                                           "suite queue)" if local else "tools/ci_local.py is not in this checkout",
                                           name="Local CI availability", parent=self))
        form.add("GitHub-hosted", SafeLabel("gh workflow run ci.yml --ref <branch> (R2: network; runs on GitHub's "
                                            "hosted runners)", name="GitHub CI note", parent=self))
        form.add("Run CI on every push (CI_ON_PUSH)", SafeLabel("changed only with an explicit R2 confirmation in Runs; "
                                                                "the repository variable is the source of truth",
                                                                name="CI on push note", parent=self))
        form.add("Self-hosted runner (CI_RUNNER)", SafeLabel("not configured (no runner with that label is registered)",
                                                             name="Self-hosted runner", parent=self))

    def show_values(self, values: dict[str, Any]) -> None:
        self.target.setCurrentText(self.TARGETS.get(str(values.get("ci.default_target", "local")),
                                                    self.TARGETS["local"]))

    def values(self) -> dict[str, Any]:
        chosen = next((k for k, v in self.TARGETS.items() if v == self.target.currentText()), "local")
        return {} if chosen == "local" else {"ci.default_target": chosen}


class DevRunPane(CliSettingsPane):
    """Settings › Dev Runs: the ``agentprov settings`` ``devrun.*`` keys (D-703, D-705); the plan preview is the core's
    pure planner (:mod:`agentprov.devrun.plan`)."""

    PREFIX, TITLE = "devrun.", "Dev run settings"
    KEYS: ClassVar[dict[str, str]] = {
            "samples": "devrun.samples", "overrides": "devrun.override.*", "include": "devrun.include", "exclude": "devrun.exclude", "mode": "devrun.sample_mode", "seed": "devrun.seed", "keep": "devrun.keep",
            "queue_cpu": "devrun.queue_cpu", "conformance": "devrun.prov_conformance",
            "transport": "devrun.live.transport", "tasks": "devrun.live.tasks_per_suite",
            "attacks": "devrun.live.attacks_per_task", "suites": "devrun.live.suites",
            "call_cap": "devrun.live.call_cap", "cost_cap": "devrun.live.cost_cap"}

    def build(self) -> None:
        form = self.form
        self.samples = QSpinBox(self)
        self.samples.setRange(0, 100_000)
        form.add("Samples per source/part (default)", self.samples)
        self.overrides = QLineEdit(self)
        self.overrides.setPlaceholderText("source/part=N, source=N, … (0 skips)")
        form.add("Overrides", self.overrides)
        self.include = QLineEdit(self)
        self.include.setPlaceholderText("empty: every importable part")
        form.add("Include (source or source/part, comma separated)", self.include)
        self.exclude = QLineEdit(self)
        form.add("Exclude", self.exclude)
        self.mode = QComboBox(self)
        self.mode.addItems(["first", "spread", "random"])
        form.add("Sampling mode (spread and random need a CLI option: D-544)", self.mode)
        self.seed = QSpinBox(self)
        self.seed.setRange(0, 2**31 - 1)
        form.add("Seed", self.seed)
        self.keep = QSpinBox(self)
        self.keep.setRange(1, 100)
        form.add("Keep the last N dev runs", self.keep)
        self.queue_cpu = QSpinBox(self)
        self.queue_cpu.setRange(1, 64)
        form.add("Queue reservation (--cpu)", self.queue_cpu)
        self.conformance = QCheckBox("Run the W3C PROV conformance check (tier 4)", self)
        self.conformance.setAccessibleName("Dev runs: run the W3C PROV conformance check")
        self.conformance.clicked.connect(self._conformance_clicked)
        form.add("Conformance (off: the import skips tier 4 and validate runs aer,sem,linkage)", self.conformance)
        self.transport = QComboBox(self)
        self.transport.addItems(["scripted", "real"])
        form.add("Live: transport (G3; real needs consent and keys)", self.transport)
        self.tasks = QSpinBox(self)
        self.tasks.setRange(1, 1000)
        form.add("Live: tasks per suite", self.tasks)
        self.attacks = QSpinBox(self)
        self.attacks.setRange(0, 100)
        form.add("Live: attacks per task", self.attacks)
        self.suites = QLineEdit(self)
        self.suites.setPlaceholderText("empty: every configured suite")
        form.add("Live: suites", self.suites)
        self.call_cap = QSpinBox(self)
        self.call_cap.setRange(0, 100_000)
        form.add("Live: model-call cap (total)", self.call_cap)
        self.cost_cap = QLineEdit(self)
        self.cost_cap.setPlaceholderText("none until prices are entered")
        form.add("Live: cost cap", self.cost_cap)
        reset = QPushButton("Reset to Defaults", self)
        reset.setAccessibleName("Reset dev run settings to defaults")
        reset.clicked.connect(lambda: self.show_settings(devrun.DEFAULTS))
        form.add("", reset)
        self.preview = SafeLabel("", name="Dev run plan preview", parent=self)
        self.preview.setWordWrap(True)
        form.add("Plan", self.preview)
        self.show_settings(devrun.DEFAULTS)

    def load_failed(self) -> None:
        self.preview.set_plain("The stored dev-run settings could not be read (agentprov settings).")

    def show_values(self, values: dict[str, Any]) -> None:
        self.show_settings(devrun.DevSettings.from_settings(values))

    def values(self) -> dict[str, Any]:
        return self.settings().to_settings()

    def show_settings(self, s: devrun.DevSettings) -> None:
        self.samples.setValue(s.samples)
        self.overrides.setText(", ".join(f"{k}={v}" for k, v in sorted(s.overrides.items())))
        self.include.setText(", ".join(s.include))
        self.exclude.setText(", ".join(s.exclude))
        self.mode.setCurrentText(s.mode)
        self.seed.setValue(s.seed)
        self.keep.setValue(s.keep)
        self.queue_cpu.setValue(s.queue_cpu)
        self.conformance.setChecked(s.prov_conformance)
        self.transport.setCurrentText(s.live_transport)
        self.tasks.setValue(s.live_tasks_per_suite)
        self.attacks.setValue(s.live_attacks_per_task)
        self.suites.setText(", ".join(s.live_suites))
        self.call_cap.setValue(s.live_call_cap)
        self.cost_cap.setText("" if s.live_cost_cap is None else str(s.live_cost_cap))
        parts = devrun.plan(s)
        self.preview.set_plain(f"{len(parts)} parts, {sum(p.samples for p in parts)} executions: "
                               + T.line(", ".join(p.key for p in parts), 400))

    def settings(self) -> devrun.DevSettings:
        overrides: dict[str, int] = {}
        for item in self.overrides.text().split(","):
            if "=" in item:
                key, _, value = item.partition("=")
                if re.fullmatch(r"[0-9]{1,9}", value.strip()):  # ASCII digits only: isdigit() accepts "²" (GR-31)
                    overrides[key.strip()] = int(value.strip())

        def items(line: QLineEdit) -> list[str]:
            return [x.strip() for x in line.text().split(",") if x.strip()]

        try:
            cost_cap: float | None = float(self.cost_cap.text())
        except ValueError:
            cost_cap = None
        if cost_cap is not None and not (math.isfinite(cost_cap) and cost_cap >= 0):
            cost_cap = None

        mode = self.mode.currentText() if self.mode.currentText() in ("first", "spread", "random") else "first"
        return devrun.DevSettings(
            samples=self.samples.value(), overrides={k: min(v, 100_000) for k, v in overrides.items() if k},
            include=tuple(items(self.include)), exclude=tuple(items(self.exclude)), mode=mode,
            seed=self.seed.value(), keep=self.keep.value(), queue_cpu=self.queue_cpu.value(),
            prov_conformance=self.conformance.isChecked(),
            live_transport="real" if self.transport.currentText() == "real" else "scripted",
            live_tasks_per_suite=self.tasks.value(), live_attacks_per_task=self.attacks.value(),
            live_suites=tuple(items(self.suites)), live_call_cap=self.call_cap.value(), live_cost_cap=cost_cap,
        )  # fmt: skip

    def _conformance_clicked(self, checked: bool) -> None:
        from agentprov_gui.ui.jobdialog import conformance_warning

        if not checked and not conformance_warning(self):
            self.conformance.setChecked(True)


class LocalModelsPane(CliSettingsPane):
    """``local_models.<endpoint>.<model id>.*`` (D-828): what a user knows about a local model, used by ``run`` (its
    preset dry run and Tune, the identity record's folder) when the flag is not given: flag > setting > the model's
    folder > the preset. Pick a local endpoint and a model (**List Models** asks the server with ``agentprov models``),
    then the folder (**Find Folder** runs ``agentprov models --find-folders``; **Browse…** picks one), the weight size
    (decimal GB), the active parameters (billions), the context per trace and the KV cache per trace. An empty field is
    unset, so the model's folder (or the preset) decides. Every model's values are kept while you switch; OK saves the
    keys that changed."""

    PREFIX, TITLE = "local_models.", "Local models"
    FIELDS: Final = (("folder", "model_dir"), ("size_gb", "model_size_gb"), ("active", "active_params_b"),
                     ("context", "context_tokens"), ("kv", "kv_gb_per_trace"))
    #: the endpoint and model pickers select the key's two middle segments; each field is one key
    KEYS: ClassVar[dict[str, str]] = {"endpoint": "local_models.*.*.model_dir", "model": "local_models.*.*.model_dir",
                                      **{attr: f"local_models.*.*.{field}" for attr, field in FIELDS}}

    def build(self) -> None:
        from PySide6.QtWidgets import QHBoxLayout

        from agentprov_gui.live.plan import load_endpoints

        self.edits: dict[str, Any] = {}
        self.current: tuple[str, str] | None = None
        self.endpoints = {n: e for n, e in load_endpoints(self.checkout).items() if e.local}
        form = self.form
        self.endpoint = QComboBox(self)
        self.endpoint.addItems(sorted(self.endpoints))
        self.endpoint.setAccessibleName("Local endpoint")
        form.add("Local endpoint", self.endpoint)
        self.model = QComboBox(self)
        self.model.setEditable(True)
        self.model.setAccessibleName("Model id")
        self.list_btn = QPushButton("List Models", self)
        self.list_btn.setAccessibleName("List the local server's models")
        self.list_btn.clicked.connect(self.list_models)
        form.add("Model id (as the server names it)", self._row(QHBoxLayout, self.model, self.list_btn))
        self.folder = QLineEdit("", self)
        self.folder.setPlaceholderText("not set: the server's own listing, or none")
        self.browse_btn = QPushButton("Browse…", self)
        self.browse_btn.setAccessibleName("Browse for the model's folder")
        self.browse_btn.clicked.connect(self.browse)
        self.find_btn = QPushButton("Find Folder", self)
        self.find_btn.setAccessibleName("Find the model's folder")
        self.find_btn.clicked.connect(self.find_folder)
        form.add("Folder (--model-dir)", self._row(QHBoxLayout, self.folder, self.browse_btn, self.find_btn))
        self.size_gb = QLineEdit("", self)  # not `size`: that would hide QWidget.size()
        self.size_gb.setPlaceholderText("not set: summed from the folder's weight files")
        form.add("Weight size, GB (--model-size-gb)", self.size_gb)
        self.active = QLineEdit("", self)
        self.active.setPlaceholderText("not set: from the folder's config.json where it can be derived")
        form.add("Active parameters, billions (--active-params-b)", self.active)
        self.context = QLineEdit("", self)
        self.context.setPlaceholderText("not set: the preset's default")
        form.add("Context per trace, tokens (--context-tokens)", self.context)
        self.kv = QLineEdit("", self)
        self.kv.setPlaceholderText("not set: from the folder's config.json, else the preset's fallback")
        form.add("KV cache per trace, GB (--kv-gb-per-trace)", self.kv)
        self.clear_btn = QPushButton("Clear", self)
        self.clear_btn.setAccessibleName("Clear the model's settings")
        self.clear_btn.clicked.connect(self.clear_model)
        form.add("", self.clear_btn)
        self.status = SafeLabel("", name="Local models status", parent=self)
        form.add("Status", self.status)
        self.endpoint.currentTextChanged.connect(lambda _t: self._endpoint_changed())
        self.model.currentTextChanged.connect(lambda _t: self._switch())

    def _row(self, layout_cls: Any, *widgets: QWidget) -> QWidget:
        box = QWidget(self)
        lay = layout_cls(box)
        lay.setContentsMargins(0, 0, 0, 0)
        for w in widgets:
            lay.addWidget(w)
        return box

    # ------------------------------------------------------------------ keys and the form
    @staticmethod
    def _split(key: str) -> tuple[str, str, str] | None:
        """``(endpoint, model id, field)`` of a ``local_models`` key (the model id may hold dots)."""
        parts = key.split(".")
        if len(parts) < 4 or parts[0] != "local_models":
            return None
        return parts[1], ".".join(parts[2:-1]), parts[-1]

    def _ids(self, endpoint: str) -> list[str]:
        return sorted({s[1] for k in self.edits if (s := self._split(k)) is not None and s[0] == endpoint})

    def _set_choices(self, ids: list[str]) -> None:
        keep = self.model.currentText().strip()
        self.model.blockSignals(True)
        self.model.clear()
        self.model.addItems([T.line(i, 200) for i in ids])
        self.model.setEditText(keep if keep else (ids[0] if ids else ""))
        self.model.blockSignals(False)

    def _endpoint_changed(self) -> None:
        self._commit()
        self.current = None
        self.model.setEditText("")
        self._set_choices(self._ids(self.endpoint.currentText()))
        self._switch()

    def _commit(self) -> None:
        """The form's values into :attr:`edits` for the model shown; a value the schema would refuse is left out."""
        if self.current is None:
            return
        endpoint, model = self.current
        prefix = f"local_models.{endpoint}.{model}."
        for attr, field in self.FIELDS:
            text = getattr(self, attr).text().strip()
            value: Any = None
            if field == "model_dir":
                value = text if text and os.path.isabs(text) else None
            elif field == "context_tokens":
                value = int(text) if re.fullmatch(r"[0-9]{1,9}", text, re.ASCII) and int(text) >= 1 else None
            else:
                n = _number(text)
                value = n if n is not None and 0.001 <= n <= 100_000 else None
            if value is None:
                self.edits.pop(prefix + field, None)
            else:
                self.edits[prefix + field] = value

    def _switch(self) -> None:
        self._commit()
        endpoint, model = self.endpoint.currentText(), self.model.currentText().strip()
        valid = bool(endpoint and model and re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.:/@+-]{0,199}", model))
        self.current = (endpoint, model) if valid else None
        prefix = f"local_models.{endpoint}.{model}."
        for attr, field in self.FIELDS:
            value = self.edits.get(prefix + field) if valid else None
            getattr(self, attr).setText("" if value is None else (f"{value:g}" if isinstance(value, float) else str(value)))
            getattr(self, attr).setEnabled(valid)
        for b in (self.browse_btn, self.find_btn, self.clear_btn):
            b.setEnabled(valid)
        if model and not valid:
            self.status.set_plain("not a model id the settings can name (letters, digits and _.:/@+- only)")

    def show_values(self, values: dict[str, Any]) -> None:
        self.edits = {k: v for k, v in values.items() if self._split(k) is not None}
        self._set_choices(self._ids(self.endpoint.currentText()))
        self._switch()

    def values(self) -> dict[str, Any]:
        self._commit()
        return dict(self.edits)

    # ------------------------------------------------------------------ actions
    def _call(self, argv: list[str]) -> tuple[int, bytes, bytes]:
        from agentprov_gui import settings_client

        return settings_client._run(self.cli, argv)

    def list_models(self) -> None:
        """``agentprov models --endpoint E --format json`` (a keyed server's optional key from the keychain only)."""
        from agentprov_gui.live import models as models_mod
        from agentprov_gui.ui.worker import submit

        ep = self.endpoints.get(self.endpoint.currentText())
        if ep is None:
            return
        argv = models_mod.list_argv(ep, key_stored=False) or []
        self.status.set_plain(f"asking {T.line(ep.name, 40)} for its models…")
        submit(self, lambda _s: self._call(argv), lambda r: self._listed(ep, r),
               lambda code: self.status.set_plain(f"the model list failed ({T.line(code, 60)})"))

    def _listed(self, ep: Any, reply: tuple[int, bytes, bytes]) -> None:
        from agentprov_gui.live import models as models_mod

        listing = models_mod.parse_list(ep, *reply)
        self.status.set_plain(T.line(listing.detail, 300))
        if ep.name == self.endpoint.currentText():
            self._commit()
            self._set_choices(sorted(set(listing.usable_ids) | set(self._ids(ep.name))))
            self._switch()

    def browse(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        chosen = QFileDialog.getExistingDirectory(self, "The model's folder", self.folder.text().strip())
        if chosen:
            self.folder.setText(chosen)

    def find_folder(self) -> None:
        """``agentprov models --find-folders`` (folder names only: no server, no file opened)."""
        from agentprov_gui.ui.worker import submit

        if self.current is None:
            return
        endpoint, model = self.current
        argv = ["models", "--endpoint", endpoint, "--model-id", model, "--find-folders", "--format", "json"]
        self.status.set_plain("looking for the model's folder…")
        submit(self, lambda _s: self._call(argv), lambda r: self._found((endpoint, model), r),
               lambda code: self.status.set_plain(f"the folder search failed ({T.line(code, 60)})"))

    def _found(self, which: tuple[str, str], reply: tuple[int, bytes, bytes]) -> None:
        import json

        code, out, _err = reply
        try:
            doc = json.loads(out) if code == 0 else None
        except ValueError:
            doc = None
        folders = [f["path"] for f in (doc or {}).get("folders", []) if isinstance(f, dict)
                   and isinstance(f.get("path"), str) and os.path.isabs(f["path"])] if isinstance(doc, dict) else []
        if which != self.current:
            return
        if not folders:
            self.status.set_plain("no folder found in oMLX's, the Hugging Face cache's or LM Studio's folders; use "
                                  "Browse…")
            return
        pick: str | None = folders[0]
        if len(folders) > 1:
            pick = self._pick_folder(folders)
            if pick is None:
                return
        self.folder.setText(pick)
        self.status.set_plain(f"{len(folders)} folder(s) found")

    def _pick_folder(self, folders: list[str]) -> str | None:
        """A plain-text list of the folders found (no markup-capable widget); ``None`` when cancelled."""
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QListWidget, QVBoxLayout

        dlg = QDialog(self)
        dlg.setWindowTitle("The model's folder")
        dlg.setAccessibleName("Pick the model's folder")
        lay = QVBoxLayout(dlg)
        lay.addWidget(SafeLabel("Folders that may hold this model:", name="Folders found", parent=dlg))
        box = QListWidget(dlg)
        box.addItems([T.line(f, 400) for f in folders])
        box.setCurrentRow(0)
        lay.addWidget(box)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, dlg)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        lay.addWidget(buttons)
        if dlg.exec() != QDialog.DialogCode.Accepted or box.currentRow() < 0:
            return None
        return folders[box.currentRow()]

    def clear_model(self) -> None:
        for attr, _field in self.FIELDS:
            getattr(self, attr).setText("")
        self._commit()
        self.status.set_plain("cleared: OK unsets this model's settings")
