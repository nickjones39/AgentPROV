"""Settings panes added in G2: Jobs, Compute (D-432), Continuous integration (D-431, D-432) and Dev runs (D-544).

Every value is an ``agentprov settings`` key (D-703; reverse CLI parity D-700): a pane reads its prefix with
``settings list`` and saves only what changed with ``settings set`` / ``unset`` (:class:`CliSettingsPane`), so
the CLI's schema is the check and a value the GUI shows is one the CLI uses.

Each pane is a page of the form style (D-1060): a title, sections of rows (a plain label, a grey caption, the right
control with its unit; the CLI key and flag in the tooltip), one "Advanced: …" disclosure for the rarely used settings,
and at the bottom the **terminal command** card: the ``agentprov settings set`` / ``unset`` commands of the pending
changes, from :func:`settings_client.plan`, the function OK's write runs (the stored values' ``settings list`` while
nothing changed).

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
* **Updates** (``update.auto_check``, D-1065): the daily check for a new release when the app starts.
"""

from __future__ import annotations

import math
import os
import re
from collections.abc import Callable, Sequence
from dataclasses import fields as dc_fields
from pathlib import Path
from typing import Any, ClassVar, Final

from agentprov.devrun import plan as devrun
from agentprov.ingest.limits import IngestLimits
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QDoubleSpinBox,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from agentprov_gui import platform_limits
from agentprov_gui import text as T
from agentprov_gui.ui import forms
from agentprov_gui.ui.forms import (
    CommandCard,
    Disclosure,
    FactGrid,
    FormPage,
    FormRow,
    FormSection,
    IntField,
    SegmentedControl,
    StatusBadge,
    Switch,
)
from agentprov_gui.ui.platformnotice import PlatformNotice, gate
from agentprov_gui.ui.safe import SafeLabel, set_control_tooltip, set_setting_tooltip

__all__ = ["ADVANCED_NAME", "COPY_NAME", "WORKER_COMMANDS", "AssistantPane", "Choices", "CiPane", "CliSettingsPane",
           "ComputePane", "DevRunPane", "JobsPane", "LocalModelsPane", "SectionForm", "UpdatesPane", "command_card",
           "settings_page", "short_field", "watch"]  # fmt: skip

WORKER_COMMANDS: Final = ("import", "derive", "recompute", "validate", "verify", "render")
#: the accessible name of every pane's "Advanced: …" disclosure and of every pane's Copy (parity.PRESENTATIONAL)
ADVANCED_NAME: Final = "Show advanced settings"
COPY_NAME: Final = "Copy the Settings terminal commands"
#: what the command card says while a pane's stored values are not read
NOT_READ: Final = "Nothing to run until the stored settings are read"


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


# --------------------------------------------------------------------------------------------- the panes' parts
def settings_page(owner: QWidget, title: str, *, name: str = "") -> FormPage:
    """``owner``'s page: a :class:`FormPage` titled ``title`` filling ``owner`` (a Settings pane)."""
    outer = QVBoxLayout(owner)
    outer.setContentsMargins(0, 0, 0, 0)
    page = FormPage(name=name or f"{title} settings", title=title, parent=owner)
    outer.addWidget(page)
    return page


def command_card(parent: QWidget) -> CommandCard:
    """The terminal command card of a Settings pane (its Copy is named :data:`COPY_NAME`)."""
    card = CommandCard(parent=parent)  # it re-wraps when a hidden pane is first shown (forms.CommandCard)
    card.copy_button.setAccessibleName(COPY_NAME)
    set_control_tooltip(card.copy_button, "Copies the commands shown below, one line per command, so they can be run "
                                          "in a terminal. OK runs the same commands.")
    return card


def short_field(parent: QWidget, *, name: str, placeholder: str = "Not set", width: int = 130) -> QLineEdit:
    """A short right-aligned text field for an optional number (empty: unset; a value the schema would refuse is left
    out when saving, GR-30, GR-31), the width of the form's number fields."""
    line = QLineEdit(parent)
    line.setAccessibleName(name)
    line.setPlaceholderText(placeholder)
    line.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    line.setFixedWidth(width)
    line.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)  # the unit follows it (FormRow)
    return line


class Choices(SegmentedControl):
    """A segmented control whose choices carry the stored value (``currentData``) and a tip each; ``setCurrentText``
    takes a choice's label or its value, as the combo box it replaces took its text."""

    def __init__(self, choices: Sequence[tuple[str, str, str]], *, name: str, parent: QWidget | None = None,
                 active: Callable[[], bool] | None = None) -> None:
        super().__init__([(label, value) for label, value, _tip in choices], name=name, parent=parent)
        self.choice_values = [value for _label, value, _tip in choices]
        for i, (_label, _value, tip) in enumerate(choices):
            self.set_tip(i, tip, active=active)

    def setCurrentText(self, text: str) -> None:
        for i, value in enumerate(self.choice_values):
            if text in (self.itemText(i), value):
                self.setCurrentIndex(i)
                return


class SectionForm:
    """``SafeForm.add``'s calls on a :class:`FormSection` (a pane built with the form layout keeps its calls and gets
    the form style): each ``add`` is a row of the section, made on first use by ``make``. A text field shows wrapped
    and a combo box shrinks, so neither widens the column."""

    def __init__(self, make: Callable[[], FormSection]) -> None:
        self.make = make
        self.section: FormSection | None = None

    def add(self, label: str, field: QWidget, tip: str | None = None, *, subject: QWidget | None = None,
            active: Callable[[], bool] | None = None, caption_text: str = "") -> FormRow:
        if self.section is None:
            self.section = self.make()
        if isinstance(field, SafeLabel):
            field.setWordWrap(True)
            field.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        if isinstance(field, QComboBox):
            field.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            field.setMinimumContentsLength(12)
        if isinstance(field, QPlainTextEdit):
            field.setMaximumHeight(110)
        return self.section.add_row(label, field, tip=tip, subject=subject, active=active, caption_text=caption_text)


def watch(root: QWidget, changed: Callable[[], None]) -> None:
    """Call ``changed`` whenever an input under ``root`` changes (so the terminal command follows the form)."""
    for w in root.findChildren(QWidget):
        if isinstance(w.parent(), (QSpinBox, QDoubleSpinBox, QComboBox)) or forms.is_input_part(w):
            continue  # a spin box's or combo box's own line edit, a segment: their owner is watched
        if isinstance(w, SegmentedControl):
            w.currentIndexChanged.connect(lambda _i: changed())
        elif isinstance(w, QSpinBox | QDoubleSpinBox):
            w.valueChanged.connect(lambda _v: changed())
        elif isinstance(w, QComboBox):
            w.currentTextChanged.connect(lambda _t: changed())
        elif isinstance(w, QLineEdit | QPlainTextEdit):
            w.textChanged.connect(changed)
        elif isinstance(w, QAbstractButton) and w.isCheckable():
            w.toggled.connect(lambda _on: changed())
        elif isinstance(w, QTableWidget):
            w.itemChanged.connect(lambda _item: changed())
            w.model().rowsInserted.connect(lambda *_a: changed())
            w.model().rowsRemoved.connect(lambda *_a: changed())


class CliSettingsPane(QWidget):
    """A pane whose values are ``agentprov settings`` keys under :attr:`PREFIX` (D-700, D-703). The stored values are
    read in the background; until they arrive the pane's fields (:attr:`body`) are disabled and :meth:`save` writes
    nothing. When they cannot be read, :attr:`notice`, above the fields and not greyed, says why and what to set
    (D-1030). Saving writes only the keys that changed (:func:`settings_client.write`); a refused value is listed.
    :attr:`KEYS` maps each input widget's attribute name to its key (the reverse-parity registry, D-700).

    The page (:attr:`page`) has the pane's title (:attr:`HEADING`, else :attr:`TITLE` without " settings"), the
    sections :meth:`build` makes (:meth:`section`, :meth:`advanced`; :attr:`form` keeps the form layout's ``add``) and
    the terminal command card (:attr:`command`) of the pending changes (:func:`settings_client.plan`)."""

    PREFIX: str = ""
    TITLE: str = "Settings"
    HEADING: str = ""
    KEYS: ClassVar[dict[str, str]] = {}

    def __init__(self, checkout: Path | None, parent: QWidget | None = None, *, cli: Any = None) -> None:
        """``cli`` (a :data:`settings_client.Caller`) defaults to the checkout's CLI."""
        super().__init__(parent)
        from agentprov_gui.jobs.manager import CliLocator

        self.checkout = checkout
        self.cli = CliLocator.for_checkout(checkout) if cli is None else cli
        self.loaded: dict[str, Any] | None = None
        self.page = settings_page(self, self.HEADING or self.TITLE.removesuffix(" settings"), name=self.TITLE)
        column = self.page.column
        self.notice = SafeLabel("Reading the stored settings (agentprov settings list)…",
                                name=f"{self.TITLE}: status", parent=column)
        self.notice.setWordWrap(True)
        self.page.add(self.notice)
        self.body = QWidget(column)
        self.body.setAccessibleName(f"{self.TITLE}: fields")
        self.sections = QVBoxLayout(self.body)
        self.sections.setContentsMargins(0, 0, 0, 0)
        self.sections.setSpacing(18)
        self.page.add(self.body)
        self.form = SectionForm(lambda: self.section(""))
        self.build()
        self.command = command_card(column)
        self.page.add(self.command)
        self._timer = QTimer(self)  # the card follows the form after the change (a model switch fills several fields)
        self._timer.setSingleShot(True)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self.show_command)
        watch(self.body, self._timer.start)
        self.show_command()
        self.body.setEnabled(False)
        from agentprov_gui import settings_client
        from agentprov_gui.ui.worker import submit

        submit(self, lambda _s: settings_client.read_or_reason(self.cli, self.PREFIX), self._loaded,
               lambda code: self.load_failed(f"Reading the settings failed ({T.line(code, 60)})."))

    # ------------------------------------------------------------------ the page
    def section(self, title: str, *, note: str = "", into: Disclosure | None = None) -> FormSection:
        """A new section at the end of the fields (or of the disclosure ``into``)."""
        sec = FormSection(title, parent=into.content if into is not None else self.body, note=note)
        if into is not None:
            into.add(sec)
        else:
            self.sections.addWidget(sec)
        return sec

    def advanced(self, holds: str, tip: str) -> Disclosure:
        """The pane's one "Advanced: ``holds``" disclosure (rule 4), collapsed until opened."""
        box = Disclosure(f"Advanced: {holds}", screen="settings", key=self.PREFIX.rstrip(".") or "pane",
                         name=ADVANCED_NAME, parent=self.body)
        set_control_tooltip(box.button, tip)
        self.sections.addWidget(box)
        return box

    def commands(self) -> list[tuple[str, list[str]]]:
        """The terminal commands the card shows: OK's writes for the pending changes (:func:`settings_client.plan`),
        else the stored values' ``settings list``; none until those are read."""
        from agentprov_gui import settings_client

        if self.loaded is None:
            return []
        pending = settings_client.plan(self.loaded, self.values())
        if not pending:
            return [("The stored values; nothing changed, so OK writes nothing",
                     settings_client.list_argv(self.PREFIX))]
        return [("What OK runs" if i == 0 else "", argv) for i, argv in enumerate(pending)]

    def show_command(self) -> None:
        self.command.set_commands(self.commands(), note=NOT_READ)

    def load_failed(self, reason: str = "") -> None:
        """The stored values could not be read: the fields stay disabled and :attr:`notice` says why."""
        self.notice.set_plain(f"{self.TITLE} cannot be changed here: {T.line(reason, 400)}" if reason else
                              f"{self.TITLE} cannot be changed here: the stored settings could not be read.")
        self.notice.show()

    def build(self) -> None:  # pragma: no cover - every pane overrides it
        raise NotImplementedError

    def show_values(self, values: dict[str, Any]) -> None:  # pragma: no cover
        raise NotImplementedError

    def values(self) -> dict[str, Any]:  # pragma: no cover
        """The keys to store; a key at its default is left out, so saving unsets it."""
        raise NotImplementedError

    def _loaded(self, values: dict[str, Any] | str | None) -> None:
        if not isinstance(values, dict):
            self.load_failed(values or "")
            return
        self.loaded = values
        self.show_values(values)
        self.notice.hide()
        self.body.setEnabled(True)
        self.show_command()

    def save(self) -> None:
        if self.loaded is None:
            return
        from agentprov_gui import settings_client
        from agentprov_gui.ui.worker import run_off_ui

        loaded, values = self.loaded, self.values()
        # AU-GUI-3: one CLI process per changed key, in the pool; the Settings window is disabled meanwhile
        refused = run_off_ui(self.window(), lambda: settings_client.write(self.cli, loaded, values))
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


def _status_row(sec: FormSection, label: str, badge: StatusBadge, caption_text: str, tip: str) -> FormRow:
    """A read-only row: a status badge (words with a tint) and a caption; its tip on the label and the badge."""
    row = sec.add_row(label, badge, caption_text=caption_text, stretch=False)
    for widget in (row.label, badge):
        set_setting_tooltip(widget, tip)
    return row


class JobsPane(CliSettingsPane):
    """``jobs.*``: what ``agentprov jobs prune`` keeps by default, and whether batches go on after exit 4 or 70."""

    PREFIX, TITLE, HEADING = "jobs.", "Jobs settings", "Jobs"
    KEYS: ClassVar[dict[str, str]] = {
            "retention": "jobs.retention", "retention_days": "jobs.retention_days", "continue_on_failure": "jobs.continue_on_failure"}

    def build(self) -> None:
        sec = self.section("Ended jobs")
        self.retention = IntField(10, 10_000, 200, name="Keep ended jobs", unset=False, unit="jobs", parent=sec.card)
        sec.add_row("Keep ended jobs", self.retention, caption_text="Prune deletes older ones only when you confirm",
                    tip="agentprov jobs prune keeps at most this many ended jobs (jobs.retention, default 200). It "
                        "lists what it would remove and deletes only with --yes.")
        self.retention_days = IntField(1, 3650, 90, name="and none older than", unset=False, unit="days",
                                       parent=sec.card)
        sec.add_row("and none older than", self.retention_days,
                    tip="agentprov jobs prune also removes ended jobs older than this many days (jobs.retention_days, "
                        "default 90).")
        sec = self.section("Batches")
        self.continue_on_failure = Switch(name="Batches continue after a refusal or error", parent=sec.card)
        sec.add_row("Batches continue after a refusal or error", self.continue_on_failure,
                    caption_text="Exit 4 or 70 of one step does not stop the rest",
                    tip="Off (default): a batch stops after a step that ends with exit 4 (refused by a guard) or 70 "
                        "(internal error). On: the remaining steps run anyway (jobs.continue_on_failure).")
        level = SafeLabel("status", name="Progress level", parent=sec.card)
        sec.add_row("Progress level", level, caption_text="The steps level costs real I/O on large runs",
                    tip="The progress events a job writes: status (one line per stage). steps (one per step) costs "
                        "real I/O on large runs, so jobs keep to status.")

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

    PREFIX, TITLE, HEADING = "compute.", "Compute settings", "Compute"
    #: the preset choices: (label, value, tip); "named" uses the preset name below
    PRESETS: Final = (("This machine", "", "Leaves compute.preset unset: agentprov estimate plans for this machine."),
                      ("M5 Ultra", "m5ultra", "--m5ultra: the calibrated Mac Studio M5 Ultra preset."),
                      ("Named preset", "named", "--preset NAME: a preset of presets.toml, named below."))
    KEYS: ClassVar[dict[str, str]] = {
            "preset": "compute.preset", "preset_name": "compute.preset", "stagger": "compute.start_stagger",
            "queue": "compute.queue_heavy", "queue_cpu": "compute.queue_cpu", "cpu_budget": "compute.cpu_budget",
            "mem_budget": "compute.mem_gib_budget", "gate_n": "compute.gate_n",
            **{f"jobs.{cmd}": f"compute.jobs.{cmd}" for cmd in WORKER_COMMANDS}}

    def build(self) -> None:
        sec = self.section("Machine")
        self.preset = Choices(self.PRESETS, name="Machine preset", parent=sec.card)
        sec.add_row("Machine preset", self.preset, caption_text="What Run Live's Tune and the estimate plan for",
                    tip="The machine preset agentprov estimate plans with (compute.preset). This machine leaves it "
                        "unset; M5 Ultra is the calibrated Mac Studio preset (--m5ultra); Named preset uses the name "
                        "below (--preset NAME). Run Live's Tune uses --m5ultra unless its More Options name another "
                        "preset.")
        self.preset_name = QLineEdit("", sec.card)
        self.preset_name.setPlaceholderText("Not set")
        self.preset_name_row = sec.add_row(
            "Preset name", self.preset_name, caption_text="As presets.toml names it",
            tip="The preset's name in presets.toml, used when Machine preset is Named preset (--preset NAME).",
            active=lambda: self.preset.currentData() == "named")
        self.preset.currentIndexChanged.connect(self._preset_changed)
        self._preset_changed()
        sec = self.section("Worker processes",
                           note="Used when a command is started without a worker count. Host default: "
                                "min(CPUs, ⌊0.75 RAM / 4 GiB⌋).")
        self.jobs: dict[str, IntField] = {}
        for cmd in WORKER_COMMANDS:
            spin = IntField(1, 512, None, name=f"Worker processes for {cmd}", placeholder="Host default",
                            unit="workers", parent=sec.card)  # unset (0) is the host default
            self.jobs[cmd] = spin
            sec.add_row(cmd.capitalize(), spin,
                        tip=f"Worker processes for agentprov {cmd} when --jobs is not given (compute.jobs.{cmd}). "
                            "Empty (0) is the host default; a lower value leaves the machine free for other work.")
        sec = self.section("Job queue")
        self.queue_section = sec
        self.queue = Switch(name="Run heavy jobs through the shared job queue", parent=sec.card, checked=True)
        sec.add_row("Run heavy jobs through the job queue", self.queue,
                    caption_text="They wait for room instead of competing with test suites",
                    tip="On (default): heavy GUI jobs wait for room in the shared job queue (tools/suite_queue.py "
                        "--class import), so they never compete with test suites or other sessions for the machine. "
                        "Off: they start at once (compute.queue_heavy).")
        self.queue_cpu = IntField(1, 256, 2, name="Queue reservation per GUI job", unset=False, unit="CPUs",
                                  parent=sec.card)
        self.queue_rows = [sec.add_row(
            "Reserve per job", self.queue_cpu,
            tip="How many CPUs of the queue's budget each queued GUI job reserves (--cpu; compute.queue_cpu, default "
                "2).")]
        self.cpu_budget = short_field(sec.card, name="Queue CPU budget", placeholder="Default (CPUs − 2)")
        self.queue_rows.append(sec.add_row(
            "CPU budget", self.cpu_budget, unit="CPUs", caption_text="Shared out among queued jobs",
            tip="The CPUs the job queue shares out among queued jobs (compute.cpu_budget); agentprov jobs start "
                "passes it as AGENTPROV_JOB_CPU_BUDGET. Empty: the CPU count less 2."))
        self.mem_budget = short_field(sec.card, name="Queue memory budget in GiB", placeholder="Default (75 % of RAM)")
        self.queue_rows.append(sec.add_row(
            "Memory budget", self.mem_budget, unit="GiB", caption_text="Shared out among queued jobs",
            tip="The memory, in GiB, the job queue shares out among queued jobs (compute.mem_gib_budget); agentprov "
                "jobs start passes it as AGENTPROV_JOB_MEM_GIB_BUDGET. Empty: 75 % of RAM."))
        self.queue.toggled.connect(self._queue_changed)
        if (refused := platform_limits.current().get("job_queue")) is not None:
            # D-1064: the CLI refuses the queue here (--queue-cpu): each setting disabled with its reason, and a notice
            for w in (self.queue, self.queue_cpu, self.cpu_budget, self.mem_budget):
                gate(w, refused)
            notice = PlatformNotice("job_queue", name="Job queue on this platform", parent=sec.card, card=False)
            sec.add(notice)
        elif os.name != "posix":  # G5 P-3: tools/suite_queue.py locks with fcntl; Windows has no job queue in v0.1
            for w in (self.queue, self.queue_cpu, self.cpu_budget, self.mem_budget):
                w.setEnabled(False)
            sec.add_row("Job queue", SafeLabel("Not available on Windows: jobs start directly",
                                               name="Job queue on Windows", parent=sec.card),
                        tip="tools/suite_queue.py locks with fcntl, which Windows does not have, so jobs start "
                            "directly.")
        box = self.advanced("start stagger, test gate workers, ingest limits",
                            "Shows or hides the live start stagger and the test gate's workers (both stored but not "
                            "used yet) and the ingest limits every import applies.")
        sec = self.section("Stored, not used yet", into=box)
        self.stagger = short_field(sec.card, name="Live start stagger in seconds")
        sec.add_row("Live start stagger", self.stagger, unit="seconds", caption_text="Planned for v0.2",
                    tip="Seconds between the starts of a live run's parallel workers (compute.start_stagger, 0 to "
                        "3600; --start-stagger). Stored but not used yet (planned for v0.2).")
        self.gate_n = IntField(1, 256, 10, name="Test gate workers", unset=False, unit="workers", parent=sec.card)
        sec.add_row("Test gate workers", self.gate_n, caption_text="ci_local.py picks its own count",
                    tip="Workers for the test gate (pytest -n; compute.gate_n). Stored but not used yet: "
                        "tools/ci_local.py takes $AGENTPROV_SUITE_WORKERS, else a count picked from the host.")
        sec = self.section("Ingest limits (read-only)", into=box,
                           note="Part of a corpus's identity, so not a setting: only a source profile's [import] "
                                "limits may raise them, up to 64 MiB.")
        limits = IngestLimits()
        shown = FactGrid(name="Ingest limits (read-only)", parent=sec.card)
        for f in dc_fields(limits):
            if f.name != "zip_methods":
                shown.set(f.name, f"{getattr(limits, f.name):,}" if isinstance(getattr(limits, f.name), int)
                          else str(getattr(limits, f.name)))
        set_setting_tooltip(shown, "The limits every import applies to untrusted input: sizes, counts, compression "
                                   "ratios and nesting depth. They are part of a corpus's identity, so they are not a "
                                   "setting; only a source profile's [import] limits may raise them.")
        sec.add(shown)

    def _preset_changed(self, *_: object) -> None:
        self.preset_name_row.setVisible(self.preset.currentData() == "named")

    def _queue_changed(self, on: bool) -> None:
        for row in self.queue_rows:
            row.setVisible(on)

    def show_values(self, values: dict[str, Any]) -> None:
        preset = values.get("compute.preset")
        if preset == "m5ultra":
            self.preset.setCurrentText("m5ultra")
        elif isinstance(preset, str) and preset:
            self.preset.setCurrentText("named")
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
        if self.preset.currentData() == "m5ultra":
            out["compute.preset"] = "m5ultra"
        elif self.preset.currentData() == "named" and name:
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

    PREFIX, TITLE, HEADING = "ci.", "CI settings", "CI"
    TARGETS: Final = {"local": "Local", "github": "GitHub-hosted", "mac-studio": "Self-hosted runner"}
    KEYS: ClassVar[dict[str, str]] = {"target": "ci.default_target"}

    def build(self) -> None:
        sec = self.section("Default target")
        tips = {"local": "Runs tools/ci_local.py through the shared suite queue on this machine.",
                "github": "gh workflow run ci.yml: GitHub's hosted runners (R2, network; spends Actions minutes).",
                "mac-studio": "The self-hosted runner (CI_RUNNER); needs a registered runner."}
        self.target = Choices([(label, key, tips[key]) for key, label in self.TARGETS.items()],
                              name="Default CI target", parent=sec.card)
        sec.add_row("Default CI target", self.target,
                    caption_text="Stored, not used yet: each CI run is chosen in Runs › New Job",
                    tip="The CI target to preselect (ci.default_target). Stored but not used yet: each CI run is chosen "
                        "in Runs › New Job. Local runs tools/ci_local.py through the queue; GitHub-hosted spends "
                        "Actions minutes; the self-hosted runner needs a registered runner.")
        sec = self.section("Targets", note="Running CI or changing a repository variable is a job of its own in Runs, "
                                           "confirmed each time. The app stores no token.")
        local = self.checkout is not None and (self.checkout / "tools" / "ci_local.py").is_file()
        _status_row(sec, "Local runner", StatusBadge("Available" if local else "Not in this checkout",
                                                     name="Local CI availability", kind="ok" if local else "neutral",
                                                     parent=sec.card),
                    "Runs › New Job › Run CI locally" if local else "This checkout has no local CI script",
                    "Local CI runs tools/ci_local.py, which queues itself in the shared suite queue "
                    + ("(available: Runs › New Job › Run CI locally)." if local else
                       "(tools/ci_local.py is not in this checkout)."))
        _status_row(sec, "GitHub-hosted", StatusBadge("Network, confirmed", name="GitHub CI note", kind="warn",
                                                      parent=sec.card),
                    "Runs on GitHub's hosted runners and spends Actions minutes",
                    "gh workflow run ci.yml --ref <branch> (R2: network; runs on GitHub's hosted runners).")
        _status_row(sec, "Run CI on every push", StatusBadge("Set in Runs", name="CI on push note", parent=sec.card),
                    "The repository variable is the source of truth",
                    "CI_ON_PUSH: changed only with an explicit R2 confirmation in Runs; the repository variable is the "
                    "source of truth.")
        _status_row(sec, "Self-hosted runner", StatusBadge("Not configured", name="Self-hosted runner",
                                                           parent=sec.card),
                    "No runner with that label is registered",
                    "CI_RUNNER: not configured (no runner with that label is registered).")

    def show_values(self, values: dict[str, Any]) -> None:
        stored = str(values.get("ci.default_target", "local"))
        self.target.setCurrentText(stored if stored in self.TARGETS else "local")

    def values(self) -> dict[str, Any]:
        chosen = str(self.target.currentData() or "local")
        return {} if chosen == "local" else {"ci.default_target": chosen}


class DevRunPane(CliSettingsPane):
    """Settings › Dev Runs: the ``agentprov settings`` ``devrun.*`` keys (D-703, D-705); the plan preview is the core's
    pure planner (:mod:`agentprov.devrun.plan`)."""

    PREFIX, TITLE, HEADING = "devrun.", "Dev run settings", "Dev Runs"
    KEYS: ClassVar[dict[str, str]] = {
            "samples": "devrun.samples", "overrides": "devrun.override.*", "include": "devrun.include", "exclude": "devrun.exclude", "mode": "devrun.sample_mode", "seed": "devrun.seed", "keep": "devrun.keep",
            "queue_cpu": "devrun.queue_cpu", "conformance": "devrun.prov_conformance",
            "transport": "devrun.live.transport", "tasks": "devrun.live.tasks_per_suite",
            "attacks": "devrun.live.attacks_per_task", "suites": "devrun.live.suites",
            "call_cap": "devrun.live.call_cap", "cost_cap": "devrun.live.cost_cap"}

    def build(self) -> None:
        sec = self.section("Samples")
        self.samples = IntField(0, 100_000, 5, name="Samples per part", unset=False, unit="executions",
                                parent=sec.card)
        sec.add_row("Samples per part", self.samples, caption_text="Read from the fetch cache",
                    tip="How many executions a dev run imports from each importable part, read from the fetch cache "
                        "(devrun.samples, default 5). Overrides replace it for single parts.")
        self.mode = Choices((("First", "first", "The first N executions by key."),
                             ("Spread", "spread", "Round-robin over the reader's arms."),
                             ("Random", "random", "N drawn at random with the seed below.")),
                            name="Sampling mode", parent=sec.card)
        sec.add_row("Sampling mode", self.mode, caption_text="Spread and random need a CLI option (D-544)",
                    tip="How the sample is chosen before mapping (import --sample-mode): first takes the first N by "
                        "key, spread goes round-robin over the reader's arms, random draws N with the seed below.")
        self.seed = IntField(0, 2**31 - 1, 0, name="Seed", unset=False, parent=sec.card)
        self.seed_row = sec.add_row(
            "Seed", self.seed, caption_text="Recorded in the manifest",
            tip="The seed for random sampling (import --seed; recorded in the manifest), so the same sample can be "
                "drawn again. Used only when Sampling mode is random.",
            active=lambda: self.mode.currentData() == "random")
        self.mode.currentIndexChanged.connect(lambda _i: self.seed_row.setVisible(self.mode.currentData() == "random"))
        sec = self.section("Checks and housekeeping")
        self.conformance = Switch(name="Dev runs: run the W3C PROV conformance check", parent=sec.card, checked=True)
        self.conformance.clicked.connect(self._conformance_clicked)
        sec.add_row("W3C PROV conformance check", self.conformance, caption_text="Off skips validation tier 4",
                    tip="On (default): each dev-run import runs the W3C PROV conformance check, validation tier 4. "
                        "Off: faster, but the import skips tier 4 and validate checks only the aer, sem and linkage "
                        "tiers; the app asks before turning it off.")
        self.keep = IntField(1, 100, 5, name="Keep the last dev runs", unset=False, unit="dev runs", parent=sec.card)
        sec.add_row("Keep the last", self.keep, caption_text="Older dev-run folders are removed",
                    tip="How many dev-run folders under $AGENTPROV_HOME/dev-runs are kept; older ones are removed "
                        "(agentprov devrun prune; devrun.keep, default 5).")
        self.queue_cpu = IntField(1, 64, 2, name="Queue reservation per step", unset=False, unit="CPUs",
                                  parent=sec.card)
        sec.add_row("Reserve per step", self.queue_cpu,
                    tip="How many CPUs of the job queue's budget each dev-run step reserves (--cpu; devrun.queue_cpu, "
                        "default 2).")
        if (refused := platform_limits.current().get("job_queue")) is not None:  # D-1064: no queue where refused
            gate(self.queue_cpu, refused)
            sec.add(PlatformNotice("job_queue", name="Dev-run job queue on this platform", parent=sec.card,
                                   card=False))
        sec = self.section("Live dev run")
        self.transport = Choices((("Scripted", "scripted", "Replays a fixed script: no network, no cost."),
                                  ("Real model", "real", "Calls the configured model: needs your consent and a "
                                                         "stored key.")),
                                 name="Live transport", parent=sec.card)
        sec.add_row("Transport", self.transport, caption_text="Real needs consent and a stored key",
                    tip="How Live Dev Run talks to a model (G3): scripted replays a fixed script (no network, no "
                        "cost); real calls the configured model, which needs your consent and a stored key.")
        self.tasks = IntField(1, 1000, 3, name="Live tasks per suite", unset=False, unit="tasks", parent=sec.card)
        sec.add_row("Tasks per suite", self.tasks,
                    tip="How many user tasks of each suite Live Dev Run captures: tasks 0 to N−1 "
                        "(devrun.live.tasks_per_suite, default 3).")
        self.attacks = IntField(0, 100, 1, name="Live attacks per task", unset=False, unit="attacks", parent=sec.card)
        sec.add_row("Attacks per task", self.attacks, caption_text="0 runs each task without an attack",
                    tip="0 runs each task without an attack. 1 or more adds the direct attack with injection task 0, "
                        "the only attack a live dev run uses (devrun.live.attacks_per_task, default 1).")
        self.suites = QLineEdit(sec.card)
        self.suites.setPlaceholderText("Every configured suite")
        sec.add_row("Suites", self.suites, caption_text="Comma separated",
                    tip="The AgentDojo suites Live Dev Run uses, comma separated. Empty: every configured suite.")
        self.call_cap = IntField(0, 100_000, 5, name="Live model-call cap", unset=False, unit="calls", parent=sec.card)
        sec.add_row("Model-call cap", self.call_cap, caption_text="In all; 0: no cap",
                    tip="The most model calls a live dev run may make in all (devrun.live.call_cap, default 5). 0: no "
                        "call cap.")
        self.cost_cap = short_field(sec.card, name="Live cost cap")
        sec.add_row("Cost cap", self.cost_cap, unit="USD", caption_text="Priced from Settings › Prices",
                    tip="The most a live dev run may spend, priced from Settings › Prices (devrun.live.cost_cap). "
                        "Empty: no cost cap.")
        box = self.advanced("per-part overrides, include and exclude lists",
                            "Shows or hides the sample counts for single parts and the include and exclude lists.")
        sec = self.section("Parts", into=box)
        self.overrides = QLineEdit(sec.card)
        self.overrides.setPlaceholderText("source/part=N, source=N, … (0 skips)")
        sec.add_row("Overrides", self.overrides, caption_text="A part's entry wins over its source's",
                    tip="Sample counts for single sources or parts, as source/part=N or source=N, comma separated. A "
                        "source/part entry wins over a source entry; 0 leaves the part out.")
        self.include = QLineEdit(sec.card)
        self.include.setPlaceholderText("Every importable part")
        sec.add_row("Include", self.include, caption_text="Sources or parts, comma separated",
                    tip="Only these sources or parts go into the dev run, comma separated (source or source/part). "
                        "Empty: every importable part.")
        self.exclude = QLineEdit(sec.card)
        self.exclude.setPlaceholderText("None")
        sec.add_row("Exclude", self.exclude, caption_text="Wins over Include",
                    tip="Sources or parts left out of the dev run, comma separated; an excluded part stays out even "
                        "when Include names it.")
        sec = self.section("Plan")
        self.preview = SafeLabel("", name="Dev run plan preview", parent=sec.card)
        self.preview.setWordWrap(True)
        self.preview.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        sec.add_row("Plan", self.preview, tip="What a dev run with these settings would import: the core's planner "
                                              "(agentprov devrun start plans the same).")
        reset = QPushButton("Reset to Defaults", sec.card)
        reset.setAccessibleName("Reset dev run settings to defaults")
        reset.setAutoDefault(False)
        reset.clicked.connect(lambda: self.show_settings(devrun.DEFAULTS))
        set_control_tooltip(reset, "Puts every dev-run field back to the shipped defaults; nothing is stored until OK.")
        sec.add_row("", reset, stretch=False)
        self.show_settings(devrun.DEFAULTS)

    def load_failed(self, reason: str = "") -> None:
        super().load_failed(reason)
        self.preview.set_plain("The stored dev-run settings could not be read (agentprov settings).")

    def show_values(self, values: dict[str, Any]) -> None:
        self.show_settings(devrun.DevSettings.from_settings(values))

    def values(self) -> dict[str, Any]:
        return self.settings().to_settings()

    def show_command(self) -> None:
        super().show_command()
        if self.loaded is not None:  # the plan follows the form too
            parts = devrun.plan(self.settings())
            self.preview.set_plain(f"{len(parts)} parts, {sum(p.samples for p in parts)} executions: "
                                   + T.line(", ".join(p.key for p in parts), 400))

    def show_settings(self, s: devrun.DevSettings) -> None:
        self.samples.setValue(s.samples)
        self.overrides.setText(", ".join(f"{k}={v}" for k, v in sorted(s.overrides.items())))
        self.include.setText(", ".join(s.include))
        self.exclude.setText(", ".join(s.exclude))
        self.mode.setCurrentText(s.mode)
        self.seed.setValue(s.seed)
        self.seed_row.setVisible(s.mode == "random")
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

        mode = str(self.mode.currentData()) if self.mode.currentData() in ("first", "spread", "random") else "first"
        return devrun.DevSettings(
            samples=self.samples.value(), overrides={k: min(v, 100_000) for k, v in overrides.items() if k},
            include=tuple(items(self.include)), exclude=tuple(items(self.exclude)), mode=mode,
            seed=self.seed.value(), keep=self.keep.value(), queue_cpu=self.queue_cpu.value(),
            prov_conformance=self.conformance.isChecked(),
            live_transport="real" if self.transport.currentData() == "real" else "scripted",
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

    PREFIX, TITLE, HEADING = "local_models.", "Local models", "Local Models"
    FIELDS: Final = (("folder", "model_dir"), ("size_gb", "model_size_gb"), ("active", "active_params_b"),
                     ("context", "context_tokens"), ("kv", "kv_gb_per_trace"))
    #: the endpoint and model pickers select the key's two middle segments; each field is one key
    KEYS: ClassVar[dict[str, str]] = {"endpoint": "local_models.*.*.model_dir", "model": "local_models.*.*.model_dir",
                                      **{attr: f"local_models.*.*.{field}" for attr, field in FIELDS}}

    def build(self) -> None:
        from agentprov_gui.live.plan import load_endpoints

        self.edits: dict[str, Any] = {}
        self.current: tuple[str, str] | None = None
        self.endpoints = {n: e for n, e in load_endpoints(self.checkout).items() if e.local}
        sec = self.section("Model")
        self.endpoint = forms.combo(sec.card, name="Local endpoint")
        self.endpoint.addItems(sorted(self.endpoints))
        sec.add_row("Local server", self.endpoint, caption_text="A local entry of the endpoint list",
                    tip="The local server (a local entry of endpoints.toml) whose models you describe here.")
        self.model = forms.combo(sec.card, name="Model id", editable=True)
        self.list_btn = QPushButton("List Models", sec.card)
        self.list_btn.setAccessibleName("List the local server's models")
        self.list_btn.setAutoDefault(False)
        self.list_btn.clicked.connect(self.list_models)
        set_setting_tooltip(self.list_btn, "Asks the local server which models it serves (agentprov models) and adds "
                            "them to the list.")
        sec.add_row("Model id", self.model, trailing=[self.list_btn], caption_text="As the server names it",
                    tip="The model id exactly as the server serves it. Type one, or press List Models to ask the "
                        "server. Each model's values are kept while you switch.")
        sec = self.section("What run uses",
                           note="An empty field is unset: the model's folder, then the preset, decide.")
        self.folder = QLineEdit("", sec.card)
        self.folder.setAccessibleName("Folder")
        self.folder.setPlaceholderText("Not set")
        self.browse_btn = QPushButton("Choose…", sec.card)
        self.browse_btn.setAccessibleName("Browse for the model's folder")
        self.browse_btn.setAutoDefault(False)
        self.browse_btn.clicked.connect(self.browse)
        self.find_btn = QPushButton("Find", sec.card)
        self.find_btn.setAccessibleName("Find the model's folder")
        self.find_btn.setAutoDefault(False)
        self.find_btn.clicked.connect(self.find_folder)
        set_setting_tooltip(self.browse_btn, "Picks the model's folder in a folder dialog.")
        set_setting_tooltip(self.find_btn, "Looks for the model's folder in oMLX's, the Hugging Face cache's and LM "
                            "Studio's folders (agentprov models --find-folders). No server is asked and no file is "
                            "opened.")
        sec.add_row("Folder", self.folder, trailing=[self.browse_btn, self.find_btn],
                    caption_text="Default: the server's own listing, or none",
                    tip="The model's folder on disk, an absolute path (--model-dir). run reads its config.json and "
                        "weight files and records the folder in the run's identity record. Empty: the server's own "
                        "listing, or none.")
        self.size_gb = short_field(sec.card, name="Weight size in GB")  # not `size`: that would hide QWidget.size()
        sec.add_row("Weight size", self.size_gb, unit="GB", caption_text="Default: summed from the folder's weights",
                    tip="The model's weight size in decimal GB, for run's memory plan (--model-size-gb). Empty: summed "
                        "from the folder's weight files.")
        self.active = short_field(sec.card, name="Active parameters in billions")
        sec.add_row("Active parameters", self.active, unit="billion",
                    caption_text="Default: from the folder's config.json",
                    tip="The parameters active per token, in billions (for a mixture-of-experts model, the active ones "
                        "only; --active-params-b). It picks the preset's row. Empty: derived from the folder's "
                        "config.json where it can be.")
        self.context = short_field(sec.card, name="Context per trace in tokens")
        sec.add_row("Context per trace", self.context, unit="tokens", caption_text="Default: the preset's",
                    tip="The context, in tokens, one trace may fill (--context-tokens); the KV-cache plan sizes each "
                        "trace for it. Empty: the preset's default.")
        self.kv = short_field(sec.card, name="KV cache per trace in GB")
        sec.add_row("KV cache per trace", self.kv, unit="GB",
                    caption_text="Default: from config.json, else the preset's",
                    tip="The KV-cache memory one trace needs, in GB, for run's memory plan (--kv-gb-per-trace). Empty: "
                        "from the folder's config.json, else the preset's fallback.")
        self.clear_btn = QPushButton("Clear", sec.card)
        self.clear_btn.setAccessibleName("Clear the model's settings")
        self.clear_btn.setAutoDefault(False)
        self.clear_btn.clicked.connect(self.clear_model)
        set_setting_tooltip(self.clear_btn, "Empties this model's fields; OK then unsets its stored values.")
        self.status = SafeLabel("", name="Local models status", parent=sec.card)
        self.status.setWordWrap(True)
        self.status.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.status.setProperty("apvRole", "caption")
        sec.add_row("", self.status, trailing=[self.clear_btn])
        self.endpoint.currentTextChanged.connect(lambda _t: self._endpoint_changed())
        self.model.currentTextChanged.connect(lambda _t: self._switch())

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
            self.status.set_plain("Not a model id the settings can name (letters, digits and _.:/@+- only)")

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
        self.status.set_plain(f"Asking {T.line(ep.name, 40)} for its models…")
        submit(self, lambda _s: self._call(argv), lambda r: self._listed(ep, r),
               lambda code: self.status.set_plain(f"The model list failed ({T.line(code, 60)})"))

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
        self.status.set_plain("Looking for the model's folder…")
        submit(self, lambda _s: self._call(argv), lambda r: self._found((endpoint, model), r),
               lambda code: self.status.set_plain(f"The folder search failed ({T.line(code, 60)})"))

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
            self.status.set_plain("No folder found in oMLX's, the Hugging Face cache's or LM Studio's folders; use "
                                  "Choose…")
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
        self.status.set_plain("Cleared: OK unsets this model's settings")


class AssistantPane(CliSettingsPane):
    """``assistant.*`` (D-1010): who answers in Help › Assistant (``agentprov assist``). *Server* is a local server kind
    (its default address fills *Base URL*; *Refresh* lists the models it serves, the loaded one first, with
    ``agentprov assist --list-models``) or an API provider, chosen under *Provider*. The key is the endpoint's own,
    stored in Settings › Keys; a local server needs none."""

    PREFIX, TITLE = "assistant.", "Assistant settings"
    KEYS: ClassVar[dict[str, str]] = {"server": "assistant.server", "base_url": "assistant.base_url",
                                      "endpoint": "assistant.endpoint", "model": "assistant.model"}
    #: local server kinds: (label, default base URL); Strata and Other have no fixed address
    SERVERS: Final = (("omlx", "oMLX", "http://127.0.0.1:8000/v1"), ("mlx_lm", "MLX (mlx_lm.server)", "http://127.0.0.1:8080/v1"),
                      ("lmstudio", "LM Studio", "http://127.0.0.1:1234/v1"), ("ollama", "Ollama", "http://127.0.0.1:11434/v1"),
                      ("splash", "Splash", "http://127.0.0.1:8003/v1"), ("strata", "Strata", ""),
                      ("llamacpp", "llama.cpp", "http://127.0.0.1:8080/v1"), ("vllm", "vLLM", "http://127.0.0.1:8000/v1"),
                      ("other", "Other (OpenAI-compatible)", ""))
    PROVIDERS: Final = ("openai", "anthropic", "openrouter", "deepseek", "gemini", "llama", "qwen", "glm")
    #: a local server kind that is also a local entry of endpoints.toml (its optional key, D-827)
    REGISTRY_LOCAL: Final = ("omlx", "mlx_lm", "lmstudio", "ollama", "llamacpp", "vllm")

    def build(self) -> None:
        sec = self.section("Who answers")
        self.server = forms.combo(sec.card, name="Server")
        self.server.addItem("Not set", "")
        for key, name, _url in self.SERVERS:
            self.server.addItem(f"{name} (local)", key)
        self.server.addItem("API provider (OpenAI, Anthropic, …)", "api")
        sec.add_row("Server", self.server, caption_text="A local server, or an API provider",
                    tip="Who answers in Help › Assistant: a local server kind (its default address fills Base URL) or "
                        "an API provider, chosen under Provider (assistant.server, assistant.endpoint).")
        self.base_url = QLineEdit(sec.card)
        self.base_url.setPlaceholderText("http://127.0.0.1:PORT/v1")
        self.base_url_label = sec.add_row(
            "Base URL", self.base_url, caption_text="On this computer (loopback) only",
            tip="The local server's OpenAI-compatible address, on loopback only, such as http://127.0.0.1:8000/v1 "
                "(--base-url; assistant.base_url).")
        self.endpoint = forms.combo(sec.card, name="Provider")
        for name in self.PROVIDERS:
            self.endpoint.addItem(name, name)
        self.endpoint_label = sec.add_row(
            "Provider", self.endpoint, caption_text="Bills the tokens; its key is in Settings › Keys",
            tip="The API provider that answers (--endpoint; assistant.endpoint). Its key comes from Settings › Keys, "
                "and the provider bills the tokens.")
        self.model = forms.combo(sec.card, name="Model id", editable=True)
        self.model.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.refresh = QPushButton("Refresh", sec.card)
        self.refresh.setAccessibleName("Refresh the server's model list")
        self.refresh.setAutoDefault(False)
        self.refresh.clicked.connect(self.refresh_models)
        set_setting_tooltip(self.refresh, "Asks the local server which models it serves, the loaded one first "
                            "(agentprov assist --list-models). No model is called.")
        model_row = sec.add_row("Model", self.model, trailing=[self.refresh],
                                tip="The model that answers, by its id (--model-id; assistant.model). Type one, or "
                                    "press Refresh to list a local server's models.")
        self.models_status = model_row.caption
        self.models_status.setAccessibleName("Model list status")
        sec = self.section("Key and privacy")
        for text, name in (
                ("An API provider's key is stored in Settings › Keys (OpenAI: OPENAI_API_KEY; Anthropic: "
                 "ANTHROPIC_API_KEY; OpenRouter: OPENROUTER_API_KEY). A local server needs none (oMLX's optional "
                 "OMLX_API_KEY is used when stored).", "Assistant key"),
                ("Each message, the conversation so far and the passages of the user guide, the CLI help and the code "
                 "docstrings chosen for it go to this server. No corpus content is sent. An API provider bills the "
                 "tokens.", "What the Assistant sends")):
            sec.add(forms.caption(text, name=name, parent=sec.card, role="secondary"))
        self.server.currentIndexChanged.connect(self._server_changed)
        self._server_changed()

    @property
    def kind(self) -> str:
        return str(self.server.currentData() or "")

    def _server_changed(self, *_: object) -> None:
        kind = self.kind
        local = kind not in ("", "api")
        local_widgets: tuple[QWidget, ...] = (self.base_url_label, self.base_url, self.refresh)
        for widget in local_widgets:
            widget.setVisible(local)
        api_widgets: tuple[QWidget, ...] = (self.endpoint_label, self.endpoint)
        for widget in api_widgets:
            widget.setVisible(kind == "api")
        default = next((url for key, _l, url in self.SERVERS if key == kind), "")
        known = {url for _k, _l, url in self.SERVERS}
        if local and (not self.base_url.text().strip() or self.base_url.text().strip() in known):
            self.base_url.setText(default)
        self.models_status.set_plain("")
        self.models_status.setVisible(False)

    def _set_models_status(self, text: str) -> None:
        self.models_status.set_plain(text)
        self.models_status.setVisible(bool(text))

    def refresh_models(self) -> None:
        """``agentprov assist --list-models`` for the server and address shown (loopback; no model is called)."""
        from agentprov_gui.ui.worker import submit

        argv = ["assist", "--list-models", "--server", self.kind, "--keychain", "--format", "json"]
        if self.base_url.text().strip():
            argv += ["--base-url", self.base_url.text().strip()]
        self.refresh.setEnabled(False)
        self._set_models_status("Asking the server…")
        caller = self.cli

        def work(_s: object) -> tuple[int, bytes, bytes]:
            from agentprov_gui import settings_client

            return settings_client._run(caller, argv)  # the panes' way to run a CLI command (a locator or a callable)

        submit(self, work, self._models, lambda code: self._models((124, b"", code.encode())))

    def _models(self, result: tuple[int, bytes, bytes]) -> None:
        import json

        from agentprov_gui.live.cli import last_line

        self.refresh.setEnabled(True)
        code, out, err = result
        try:
            doc = json.loads(out) if code == 0 else None
        except ValueError:
            doc = None
        rows = doc.get("models") if isinstance(doc, dict) else None
        if not isinstance(rows, list):
            self._set_models_status(f"No model list: {T.line(last_line(err) or f'exit {code}', 300)}")
            return
        typed = self.model.currentText().strip()
        self.model.clear()
        loaded = ""
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("id"), str):
                continue
            ident = T.line(row["id"], 200)
            self.model.addItem(f"{ident}  (loaded)" if row.get("loaded") else ident, row["id"])
            if row.get("loaded") and not loaded:
                loaded = row["id"]
        pick = typed if typed and self.model.findData(typed) >= 0 else loaded
        index = self.model.findData(pick) if pick else 0
        self.model.setCurrentIndex(max(index, 0))
        self._set_models_status(f"{self.model.count()} models" + (f"; loaded: {T.line(loaded, 200)}" if loaded
                                                                  else ""))

    def _model_id(self) -> str:
        data = self.model.currentData()
        text = self.model.currentText().strip()
        if isinstance(data, str) and self.model.itemText(self.model.currentIndex()) == text:
            return data  # a listed model ("id  (loaded)" shows its id's data)
        return text

    #: the keys that together say who answers; the model is chosen on its own
    CONNECTION: Final = ("assistant.server", "assistant.base_url", "assistant.endpoint")
    _shown: dict[str, Any] | None = None  # the keys as the fields first showed the stored values

    def show_values(self, values: dict[str, Any]) -> None:
        server, endpoint = values.get("assistant.server"), values.get("assistant.endpoint")
        url = values.get("assistant.base_url")
        # AU-GUI-1: the CLI also takes a local endpoints.toml entry, or a base URL, without a server kind; they are shown
        # as that server, or as Other, rather than as the first API provider or as not set
        kind = (server if isinstance(server, str) else
                endpoint if isinstance(endpoint, str) and endpoint in self.REGISTRY_LOCAL else
                "api" if isinstance(endpoint, str) else "other" if isinstance(url, str) and url else "")
        self.server.setCurrentIndex(max(self.server.findData(kind), 0))
        if isinstance(url, str):
            self.base_url.setText(url)
        if kind == "api" and isinstance(endpoint, str):
            if self.endpoint.findData(endpoint) < 0:  # another endpoints.toml entry: shown, not replaced by openai
                self.endpoint.addItem(T.line(endpoint, 60), endpoint)
            self.endpoint.setCurrentIndex(self.endpoint.findData(endpoint))
        model = values.get("assistant.model")
        self.model.setEditText(model if isinstance(model, str) else "")
        self._shown = self._chosen()

    def values(self) -> dict[str, Any]:
        """AU-GUI-1: what the fields say only where the user changed them. The connection (server, base URL, provider)
        and the model are each written as the fields show them once changed; otherwise the stored keys are kept as
        they are, so an OK for another pane never rewrites what the CLI set and the pane cannot show exactly."""
        now = self._chosen()
        shown, stored = self._shown, self.loaded
        if shown is None or stored is None:
            return now
        out: dict[str, Any] = {}
        for group in (self.CONNECTION, ("assistant.model",)):
            changed = any(now.get(key) != shown.get(key) for key in group)
            source = now if changed else stored
            out.update({key: source[key] for key in group if key in source})
        return out

    def _chosen(self) -> dict[str, Any]:
        """The keys as the fields show them."""
        out: dict[str, Any] = {}
        kind, model = self.kind, self._model_id()
        if kind == "api":
            out["assistant.endpoint"] = str(self.endpoint.currentData())
        elif kind:
            out["assistant.server"] = kind
            if self.base_url.text().strip():
                out["assistant.base_url"] = self.base_url.text().strip()
            if kind in self.REGISTRY_LOCAL:
                out["assistant.endpoint"] = kind  # its optional key (oMLX)
        if model:
            out["assistant.model"] = model
        return out


class UpdatesPane(CliSettingsPane):
    """``update.auto_check`` (D-1065; unset: on): whether the app checks for a new release once a day when it starts.
    The check is ``agentprov update check --allow-network --if-stale``, which the CLI makes at most once a local day
    and not at all while the setting is false. ``update.last_notified`` (the release the user chose to skip) is kept as
    stored; Skip This Version in the start-up notice sets it."""

    PREFIX, TITLE, HEADING = "update.", "Updates settings", "Updates"
    KEYS: ClassVar[dict[str, str]] = {"auto_check": "update.auto_check"}

    def build(self) -> None:
        sec = self.section("Check for updates",
                           note="Help › Check for Updates… and About check at any time. Nothing is downloaded or "
                                "installed without your confirmation.")
        self.auto_check = Switch(name="Check for updates once a day", parent=sec.card, checked=True)
        sec.add_row("Check once a day", self.auto_check,
                    caption_text="When the app starts; asks GitHub for the newest release",
                    tip="On (the default): when the app starts, it runs agentprov update check --allow-network "
                        "--if-stale, which asks GitHub's releases API for nickjones39/AgentPROV at most once a day, and "
                        "tells you once about a new version. Off: no check until you choose Check for Updates "
                        "(setting update.auto_check).")

    def show_values(self, values: dict[str, Any]) -> None:
        self.auto_check.setChecked(values.get("update.auto_check") is not False)

    def values(self) -> dict[str, Any]:
        """The other ``update.*`` keys as stored (Skip This Version's release), and the switch: off is ``false``, on
        is left unset (the default) unless it was stored as ``true``."""
        stored = self.loaded or {}
        out = {k: v for k, v in stored.items() if k != "update.auto_check"}
        if not self.auto_check.isChecked():
            out["update.auto_check"] = False
        elif stored.get("update.auto_check") is True:
            out["update.auto_check"] = True
        return out
