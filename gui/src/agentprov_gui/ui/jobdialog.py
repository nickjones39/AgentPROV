"""The New Job form and the confirmation by tier (design §6.2 "New job", §8.3a, §8.4; macos-design §3.3).

The form is generated from :data:`agentprov_gui.jobs.commands.FORMS`, laid out in the one form style (D-1060) from the
form's presentation table (:data:`~agentprov_gui.jobs.commands.LOOKS`): grouped sections, plain labels with grey
captions (the CLI option is in each tooltip), a segmented control for each exclusive way to fill the form (fetch the pin
or a local folder; all, the first N or a sample of N), switches, number fields whose grey "Default (…)" means the
option is left out, path fields, and one "Advanced: …" disclosure. A field hidden by a choice is left out of the
command; a field the table places inline (such as Download if not cached, or N) sits after another row's control.
The form is the left column; the right one keeps in view what Continue will do (the "What happens" card: the tier
badge and one plain sentence from the form's own values, :func:`what_happens`), the command card with the exact argv
the job will run, from the same :func:`build_spec`, and Cancel and Continue… at its bottom right. Confirmations:

* **R0** none (the argv is shown);
* **R1** a dialog that names what is written and where; ``purge`` also asks for the object's first 8 hex digits, then
  ``--yes`` is added;
* **R2** the hosts or cost note and an explicit tick box; the network flags are in the argv only because the user set
  them in the form.

The D-432 conformance switch ("W3C PROV conformance check", under Advanced) is on by default for PROV-generating forms.
Turning it off shows a blocking warning every time; the default button keeps the check. It is enabled only when the CLI
offers the option (G2c-5).
"""

from __future__ import annotations

import re
import shlex
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import partial
from pathlib import PurePath
from typing import Any, Final

from PySide6.QtCore import QCoreApplication, QEvent, Qt, QTimer
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from agentprov_gui import platform_limits
from agentprov_gui import text as T
from agentprov_gui.jobs.commands import (
    COMMON_LOOKS,
    GLOBAL_FIELDS,
    GLOBAL_LOOKS,
    LOOKS,
    CommandForm,
    Field,
    FormError,
    FormLook,
    JobSpec,
    Look,
    Mode,
    build_spec,
)
from agentprov_gui.ui import forms, theme
from agentprov_gui.ui.forms import (
    CommandCard,
    DecimalField,
    Disclosure,
    FormPage,
    FormRow,
    FormSection,
    IntField,
    PathField,
    SegmentedControl,
    StatusBadge,
    SummaryPanel,
    Switch,
)
from agentprov_gui.ui.platformnotice import PlatformNotice
from agentprov_gui.ui.safe import (
    ReadOnlyText,
    SafeLabel,
    choose,
    set_control_tooltip,
    set_help_tooltip,
    set_setting_tooltip,
    set_unavailable_tooltip,
)

__all__ = ["CHOICE_TIPS", "CONFORMANCE_TIP", "CONFORMANCE_WARNING", "JobDialog", "Placed", "choice_tip", "confirm",
           "conformance_warning", "field_tip", "placement", "tier_badge", "what_happens"]

CONFORMANCE_WARNING: Final = (
    "Not advisable. The PROV bundles of this run will not be checked against the W3C PROV constraints. The corpus will "
    "be marked unvalidated, cannot be sealed or released until a full recompute validates it into a new corpus, and its "
    "results should "
    "not be reported."
)
TIER_TEXT: Final = {"R0": "R0 · read-only", "R1": "R1 · writes local data", "R2": "R2 · network or paid calls"}
CONFORMANCE_TIP: Final = (
    "On (default): the PROV this job generates is checked against the W3C PROV constraints (validation tier 4). "
    "Unticking it, after a warning, adds --skip-prov-conformance: the corpus is marked unvalidated and cannot be "
    "sealed until a full recompute validates it into a new corpus."
)
#: New Job's tier badge: the tier in plain words and a tint (the words carry it, never the colour alone)
TIER_BADGE: Final = {"R0": ("Read-only", "neutral"), "R1": ("Writes local data", "info"),
                     "R2": ("Uses the network", "warn")}
#: the jobs that delete, cancel for good or go back a version: their Continue… and Start are red (a dry run is not)
DESTRUCTIVE_COMMANDS: Final = frozenset({"purge", "devrun_prune", "jobs_prune", "jobs_cancel", "keys_delete",
                                         "prices_unset", "update_rollback"})
#: options that make an R2 job a paid one (a cost consent, a cap, a price, a key)
_PAID: Final = frozenset({"--i-consent-to-api-costs", "--max-calls", "--max-cost-usd", "--price-in", "--price-out",
                          "--keychain", "--env-stdin"})
#: the "Uses the network" badge beside a network option that is on
NETWORK_BADGE_TIP: Final = ("This option makes the job an R2 job: it uses the network (downloads, or calls to a "
                            "provider). Continue then asks you to confirm with a tick box before the job starts.")
SCREEN: Final = "new-job"
_OPTIONS, _MORE, _RUN, _OTHER = "Options", "More options", "Run", "Other arguments"
_SEGMENTS_MAX_CHARS: Final = 24  # a choice field becomes a segmented control with 2-4 choices this short
_SEGMENTS_MAX_WIDTH: Final = 360  # ... and at most this wide (else a combo box: the form column never scrolls sideways)
#: the dialog's size on opening: the import form fits it without scrolling (the approved compact design)
DEFAULT_SIZE: Final = (1000, 560)
SIDE_WIDTH: Final = 330  # the right column (the approved design's)
_PAGE_MARGINS: Final = (20, 16, 20, 16)  # the form column's, left, top, right, bottom (the approved design's)
_SLOT: Final = re.compile(r"\{(\w+)(?::(\w+))?\}")  # a sentence clause's {KEY} or {KEY:name}


def field_tip(f: Field) -> str:
    """A form field's tooltip: its help, then the option it sets (or that it is positional) and whether it is
    required."""
    if f.option is None:
        sets = "Given as a positional argument" + ("s (separated by spaces)" if f.kind == "list" else "")
    elif f.kind == "bool":
        sets = f"Ticked: adds {f.option}"
    elif f.kind == "multi":
        sets = f"Sets {f.option} once per value (separated by spaces)"
    elif f.kind == "list":
        sets = f"Sets {f.option} (values separated by spaces)"
    else:
        sets = f"Sets {f.option}"
    if f.kind in ("path", "dir"):
        sets += "; an absolute path"
    text = f"{f.help} ({sets[0].lower()}{sets[1:]})." if f.help else f"{sets}."
    if f.kind == "choice" and "" in f.choices:
        text += " Blank: the option is left out."
    return text + (" Required." if f.required else "")


#: What choosing one value of a choice field means, by (option, value); a segment's tooltip adds the option it sets
#: (:func:`choice_tip`). From the CLI's help and the user guide; a value not listed is named by its option alone.
CHOICE_TIPS: Final[Mapping[tuple[str, str], str]] = {
    ("--format", "text"): "Plain text, for reading",
    ("--format", "json"): "JSON, for scripts and other tools",
    ("--format", "markdown"): "Markdown tables",
    ("--format", "csv"): "Comma-separated values, for a spreadsheet",
    ("--log-format", "text"): "The job's stderr log as text lines",
    ("--log-format", "json"): "The job's stderr log as JSON records",
    ("--prov-spec", "agentprov-prov/0.1"): "The provenance spec agentprov-prov/0.1",
    ("--prov-spec", "adprov-v2.3-compat"): "The frozen AgentDojo-PROV v2.3 compatibility spec (the regression oracle)",
    ("--level", "checksums"): "Every file against checksums.sha256, and no file outside it",
    ("--level", "chain"): "The manifest, digests, index, register and counts, the AER seals, the raw objects and the SEM "
                          "and PROV inputs",
    ("--level", "rederive"): "Everything chain checks, plus a byte-identical re-derivation from the stored raw objects "
                             "(the slowest)",
    ("--bundle", "core"): "The core bundle only",
    ("--bundle", "all"): "The core bundle and the inference and assessment bundles",
    ("--direction", "LR"): "The graph's ranks run left to right",
    ("--direction", "TB"): "The graph's ranks run top to bottom",
    ("--views", "transcript-v1"): "Adds the transcript-v1 view",
    ("--sample-mode", "first"): "The first N by key",
    ("--sample-mode", "spread"): "Round-robin over the reader's arms",
    ("--sample-mode", "random"): "A seeded random sample (the seed is recorded in the manifest)",
    ("--reason", "secret"): "The object holds a leaked secret, such as a key or a token",
    ("--reason", "personal_data"): "The object holds personal data",
    ("--scope", "golden"): "The golden set, as CI checks it",
    ("--scope", "full"): "The baseline trees (local)",
    ("--benign", "include"): "Benign cells are estimated with the attacked ones",
    ("--benign", "exclude"): "No benign cells",
    ("--benign", "only"): "Only the benign cells",
    ("--llm-element", "native"): "The benchmark's stock LLM element",
    ("--llm-element", "gateway_compat"): "The AgentDojo-PROV baseline's request path: connection and timeout errors are "
                                         "asked again, up to 8 attempts (the presets' element)",
    ("--temperature-policy", "as-benchmark"): "Accepts the stock benchmark's behaviour for a configured parameter it "
                                              "does not transmit (recorded)",
    ("--temperature-policy", "inject"): "Not available yet: the CLI refuses it",
    ("--containment", "sandbox-exec"): "Enforced by the probed macOS sandbox profile (macOS only)",
    ("--containment", "dedicated-user"): "Your declaration that the run executes as a dedicated user: recorded, not "
                                         "checked",
    ("--containment", "vm"): "Your declaration that the run executes in a virtual machine: recorded, not checked",
    ("--slot", "network"): "Holds the global network slot: one such job at a time",
    ("--slot", "backends"): "Holds the global backends slot: one such job at a time",
    ("--state", "running"): "Only the running jobs",
    ("--state", "ended"): "Only the jobs that ended",
    ("--state", "all"): "Every job",
}


def choice_tip(f: Field, value: str) -> str:
    """A choice segment's tooltip: what choosing ``value`` of ``f`` means (:data:`CHOICE_TIPS`) and what it does to
    the command."""
    if f.option is None:
        does = f"gives {value} as the positional argument"
    elif not value:
        does = f"leaves {f.option} out, so the CLI's default applies"
    else:
        does = f"sets {f.option} {value}"
    meaning = CHOICE_TIPS.get((f.option or "", value), "")
    return f"{meaning} ({does})." if meaning else f"{does[0].upper()}{does[1:]}."


def conformance_warning(parent: QWidget | None) -> bool:
    """True when the user chose to skip the check (default: keep it)."""
    return choose(parent, "PROV conformance check", "Skip the W3C PROV conformance check?", CONFORMANCE_WARNING,
                  "Keep the Check", "Skip the Check",
                  tips=("Keeps the switch on: the job checks its PROV against the W3C PROV constraints.",
                        "Turns the switch off: --skip-prov-conformance is added and the corpus is marked "
                        "unvalidated."))


def is_destructive(spec: JobSpec) -> bool:
    """True for a job that deletes, cancels for good or goes back a version (:data:`DESTRUCTIVE_COMMANDS`, or a
    destructive spec such as a purge); a dry run never is."""
    return spec.destructive or (spec.command in DESTRUCTIVE_COMMANDS and "--dry-run" not in spec.argv)


def confirm(parent: QWidget | None, spec: JobSpec, argv_preview: str) -> JobSpec | None:
    """The tier confirmation. Returns the spec to run (``purge`` gains ``--yes``), or ``None`` when cancelled."""
    if spec.tier == "R0" and not spec.destructive:
        return spec
    dlg = QDialog(parent)
    # the label names a data-derived path (S3); clean, not line: a resumed label may already carry the CLI escapes
    dlg.setWindowTitle(f"Confirm: {T.window_title(T.clean(spec.label, 120))}")
    dlg.setAccessibleName("Confirm job")
    lay = QVBoxLayout(dlg)
    lines = [TIER_TEXT.get(spec.tier, spec.tier)]
    if spec.writes:
        lines.append("Writes: " + ", ".join(T.line(w, 200) for w in spec.writes))
    lines += list(spec.notes)
    lay.addWidget(SafeLabel("\n".join(lines), name="What this job does", parent=dlg))
    argv = ReadOnlyText(name="Command", parent=dlg, wrap=True)
    argv.setPlainText(argv_preview)
    argv.setMaximumHeight(90)
    lay.addWidget(argv)
    ok = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, dlg)
    start = ok.button(QDialogButtonBox.StandardButton.Ok)
    start.setText("Start")
    set_control_tooltip(start, "Starts the job with the command shown"
                        + (" once the tick box is ticked" if spec.tier == "R2" else "")
                        + (" once the typed digits match" if spec.destructive else "") + ".")
    ok.button(QDialogButtonBox.StandardButton.Cancel).setDefault(True)
    theme.mark_destructive(start, is_destructive(spec))
    tick: QCheckBox | None = None
    typed: QLineEdit | None = None
    if spec.tier == "R2":
        tick = QCheckBox("I understand this job uses the network (and may download large files or cost money)", dlg)
        tick.setAccessibleName("Network consent")
        set_control_tooltip(tick, "An R2 job (network, downloads or paid calls) starts only once this is ticked.")
        lay.addWidget(tick)
    if spec.destructive:
        digest = next((a for a in spec.argv if a.startswith("sha256:")), "")
        lay.addWidget(SafeLabel("This removal is irreversible. Type the first 8 hex digits of the object to confirm.",
                                name="Purge warning", parent=dlg))
        typed = QLineEdit(dlg)
        typed.setAccessibleName("First 8 hex digits of the object")
        set_control_tooltip(typed, "The first 8 hex digits of the object's sha256. Start is enabled only when they "
                                   "match; --yes is then added to the purge.")
        lay.addWidget(typed)
        expected = digest.removeprefix("sha256:")[:8]
    else:
        expected = ""

    def update() -> None:
        allowed = (tick is None or tick.isChecked()) and (typed is None or typed.text().strip() == expected)
        start.setEnabled(bool(allowed))

    if tick is not None:
        tick.toggled.connect(update)
    if typed is not None:
        typed.textChanged.connect(update)
    update()
    ok.accepted.connect(dlg.accept)
    ok.rejected.connect(dlg.reject)
    lay.addWidget(ok)
    if not dlg.exec():
        return None
    if spec.destructive:
        from dataclasses import replace

        new_argv = list(spec.argv)
        new_argv.insert(len(new_argv) - 1, "--yes")
        return replace(spec, argv=tuple(new_argv))
    return spec


# ----------------------------------------------------------------------------------------------- layout (no Qt)
def tier_badge(spec: JobSpec) -> tuple[str, str]:
    """The tier badge's text and tint: the tier and what it means in plain words ("R2 · Uses the network"; "Paid API
    calls" when the argv carries a cost consent, a cap, a price or a key), and "irreversible" for a destructive job."""
    words, kind = TIER_BADGE.get(spec.tier, (spec.tier, "neutral"))
    if spec.tier == "R2" and {a.split("=", 1)[0] for a in spec.argv} & _PAID:
        words = "Paid API calls"
    text = f"{spec.tier} · {words}"
    return (text + " · irreversible", "bad") if spec.destructive else (text, kind)


def _split_label(label: str) -> tuple[str, str]:
    """A field label's plain part and its trailing parenthesis as a caption: ``"Corpus (written as DIR.partial)"``
    gives ``("Corpus", "Written as DIR.partial")``."""
    if not label.endswith(")"):
        return label, ""
    depth = 0
    for i in range(len(label) - 1, -1, -1):
        depth += {")": 1, "(": -1}.get(label[i], 0)
        if depth == 0:
            head, inner = label[:i].rstrip(), label[i + 1:-1].strip()
            return (head, inner[:1].upper() + inner[1:]) if head else (label, "")
    return label, ""


def _filled(value: Any) -> bool:
    return value not in (None, "", False) and not (isinstance(value, list | tuple) and not value)


def _holds(condition: str, values: Mapping[str, Any]) -> bool:
    """A sentence clause's condition (:class:`FormLook`): every term holds."""
    for term in (t.strip() for t in condition.split(",")):
        if not term:
            continue
        if term.startswith("!"):
            if _filled(values.get(term[1:])):
                return False
            continue
        key, eq, wanted = term.partition("=")
        value = values.get(key)
        if not (str(value) == wanted if eq else _filled(value)):
            return False
    return True


def _shown(value: Any, how: str) -> str:
    """A value as a sentence names it: a path's last part (``name``), a digest's first 8 hex digits (``short``)."""
    items = [str(v) for v in value] if isinstance(value, list | tuple) else [str(value)]
    if how == "name":
        items = [PurePath(v).name or v for v in items]
    elif how == "short":
        items = [v[:len("sha256:") + 8] + "…" if v.startswith("sha256:") and len(v) > 15 else v for v in items]
    return T.line(", ".join(items), 160)


def what_happens(form: CommandForm, values: Mapping[str, Any]) -> str:
    """What Continue will do, in plain words, from the form's values (a field hidden by a choice is unset): the
    clauses of the form's ``says`` (:class:`FormLook`), or its title; a dry run the sentence does not mention adds
    that nothing is written. Facts only from the form; data-derived values are display lines (S3)."""
    says = LOOKS.get(form.name, FormLook()).says
    if not says:
        text = form.title.rstrip(".") + "."
    else:
        parts: list[str] = []
        for condition, clause in says:
            if not _holds(condition, values):
                continue
            if any(not _filled(values.get(key)) for key, _ in _SLOT.findall(clause)):
                continue
            parts.append(_SLOT.sub(lambda m: _shown(values[m[1]], m[2] or ""), clause))
        text = "".join(parts)
    if values.get("dry_run") is True and not any("dry_run" in c for c, _ in says):
        text += " A dry run: nothing is written."
    return text


@dataclass(frozen=True, slots=True)
class Placed:
    """One field's place in New Job, every fallback of its :class:`Look` resolved."""

    field: Field
    look: Look
    section: str
    label: str
    caption: str
    advanced: bool


def placement(form: CommandForm) -> list[Placed]:
    """Each field of ``form`` (and, for a CLI form, the global options) in field order, with its section, plain label,
    caption and whether it sits under Advanced. A field a mode owns sits in the mode's section, unless its look puts it
    under Advanced (it is still shown and set only while its segment is chosen)."""
    own = LOOKS.get(form.name, FormLook())
    owner = {k: m for m in own.modes for k in m.owns()}
    fields = [(f, False) for f in form.fields] + [(f, True) for f in (GLOBAL_FIELDS if form.tool is None else ())]
    out: list[Placed] = []
    for f, is_global in fields:
        look = (GLOBAL_LOOKS.get(f.key) if is_global else own.fields.get(f.key) or COMMON_LOOKS.get(f.key)) or Look()
        plain, paren = _split_label(f.label)
        label = look.label or plain
        caption = look.caption or f.help or ("" if look.label else paren)
        mode = owner.get(f.key)
        if mode is not None:  # the mode's flag has no row of its own: the mode's control is its input, never Advanced
            advanced = look.advanced is True and f.key != mode.flag
        else:
            advanced = is_global or (f.advanced if look.advanced is None else look.advanced)
        section = (mode.section if mode is not None and mode.section and not advanced else look.section) or (
            "Save to" if f.writes else "Output" if f.key == "format" else _OPTIONS)
        if advanced and section == _OPTIONS:
            section = _MORE
        out.append(Placed(f, look, section, label, caption, advanced))
    return out


def _initial(mode: Mode, value: Any) -> int:
    """A mode's first segment: the flag's when it is set, else the first whose fields the preset fills, else the
    default (never the flag's segment while the flag is off)."""
    if mode.flag and value(mode.flag):
        return mode.flag_segment
    candidates = [i for i in range(len(mode.segments)) if not mode.flag or i != mode.flag_segment]
    for i in candidates:
        if any(_filled(value(k)) for k in mode.segments[i].shows):
            return i
    return mode.default if mode.default in candidates else candidates[0]


class _ModeControl(SegmentedControl):
    """A :class:`Mode` as a segmented control. When the mode sets a bool field, the control is that field's input:
    ``isChecked`` and ``setChecked`` read and choose the flag's segment."""

    def __init__(self, mode: Mode, *, parent: QWidget, current: int) -> None:
        super().__init__([s.text for s in mode.segments], name=mode.label, parent=parent, current=current)
        self.mode = mode
        for i, s in enumerate(mode.segments):
            if s.tip:
                self.set_tip(i, s.tip)

    def shows(self) -> tuple[str, ...]:
        return self.mode.segments[self.currentIndex()].shows

    def isChecked(self) -> bool:  # the check box API, for the flag field
        return bool(self.mode.flag) and self.currentIndex() == self.mode.flag_segment

    def setChecked(self, on: bool) -> None:
        if on:
            self.setCurrentIndex(self.mode.flag_segment)
        elif self.isChecked():
            others = [i for i in range(self.count()) if i != self.mode.flag_segment]
            self.setCurrentIndex(self.mode.default if self.mode.default in others else others[0])


# ----------------------------------------------------------------------------------------------- the dialog
class JobDialog(QDialog):
    """One command's form, its command card and tier badge, then the confirmation."""

    def __init__(self, form: CommandForm, *, program: tuple[str, ...], preset: Mapping[str, Any] | None = None,
                 conformance_option: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.form, self.program, self.conformance_option = form, program, conformance_option
        self.setWindowTitle(form.title)
        self.setAccessibleName(form.title)
        self.resize(*DEFAULT_SIZE)
        self.spec: JobSpec | None = None
        self.inputs: dict[str, QWidget] = {}
        self.rows: dict[str, QWidget] = {}  # a field's row (a FormRow), or its inline part in another row
        self.badges: dict[str, StatusBadge] = {}
        self.modes: dict[str, _ModeControl] = {}
        self.sections: list[tuple[FormSection, list[QWidget]]] = []
        preset = dict(preset or {})
        placed = placement(form)
        self.fields: tuple[Field, ...] = tuple(p.field for p in placed)
        self.placed = {p.field.key: p for p in placed}
        own = LOOKS.get(form.name, FormLook())
        self.owner: dict[str, Mode] = {k: m for m in own.modes for k in m.owns()}
        self.flags = {m.flag: m.key for m in own.modes if m.flag}
        self.inline: dict[str, list[Placed]] = {}  # a field's or mode's key: the fields shown after its control
        for p in placed:
            if p.look.inline:
                self.inline.setdefault(p.look.inline, []).append(p)

        outer = QHBoxLayout(self)  # the form on the left, what Continue will do on the right (rule 8)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.page = FormPage(name=f"{form.title}: settings", parent=self)
        inner = self.page.widget()
        if inner is not None and (inner_layout := inner.layout()) is not None:
            inner_layout.setContentsMargins(*_PAGE_MARGINS)  # the compact design's margins and spacing
        self.page.layout_.setSpacing(14)
        outer.addWidget(self.page, 1)

        # the main sections, in the order their first row appears; a mode's row stands where its first field would
        main: dict[str, list[Any]] = {}
        advanced: dict[str, list[Any]] = {}
        emitted: set[str] = set()
        for p in placed:
            mode = self.owner.get(p.field.key)
            if mode is not None and not p.advanced:
                if mode.key not in emitted:
                    emitted.add(mode.key)
                    rows = main.setdefault(mode.section or p.section, [])
                    rows.append(mode)
                    rows += [q for q in placed if q.field.key in mode.owns() and q.field.key != mode.flag
                             and not q.advanced and not q.look.inline]
                continue
            if p.look.inline:  # in its host's row
                continue
            (advanced if p.advanced else main).setdefault(p.section, []).append(p)
        if form.prov_generating:
            advanced = {_RUN: [], **advanced}
        advanced.setdefault(_OTHER, [])

        def value(key: str) -> Any:
            f = self.placed[key].field
            return preset.get(key, f.default)

        for title, rows in main.items():
            self.page.add(self._section(title, rows, value, self.page.column))
        names = ", ".join(t.lower() for t in advanced)
        self.advanced = Disclosure(f"Advanced: {own.advanced or names}", screen=SCREEN, key=form.name,
                                   name="Show more options", parent=self.page.column)
        set_control_tooltip(self.advanced.button, "Shows or hides the rest of this command's options" + (
            ", including the global options (logging, progress, the summary's failure list, stale locks)."
            if form.tool is None else "."))
        for title, rows in advanced.items():
            sec = self._section(title, rows, value, self.advanced.content)
            if title == _RUN and form.prov_generating:
                self.conformance = self._conformance_switch(sec.card)
                # a disabled switch keeps its explanation above (a gated tip would hide it)
                self._add(sec, sec.add_row("W3C PROV conformance check", self.conformance,
                                           caption_text="Validation tier 4",
                                           tip=CONFORMANCE_TIP if conformance_option is not None else None))
            if title == _OTHER:
                self.extra = QLineEdit(sec.card)
                self.extra.setPlaceholderText("additional options (argv; no shell)")
                self.extra.textChanged.connect(self._refresh)
                self._add(sec, sec.add_row(
                    "Additional options", self.extra, caption_text="Added to the command as typed; no shell runs",
                    tip="Any other options, added to the command as typed: split like a shell line, but no shell "
                        "runs. Paths must be absolute, and an option that has a field here is set in its field."))
            self.advanced.add(sec)
        self.page.add(self.advanced)
        if not form.prov_generating:  # the check does not apply: the switch exists, hidden, and stays on
            self.conformance = self._conformance_switch(self)
            self.conformance.setVisible(False)
            set_help_tooltip(self.conformance, "This command generates no PROV: the W3C PROV conformance check "
                                               "does not apply.")

        outer.addWidget(self._side(program))
        for button in self.findChildren(QPushButton):  # Enter continues only through Continue… (rule 9)
            button.setAutoDefault(button is self.ok)
        self.ok.setDefault(True)
        self._refresh()

    # ------------------------------------------------------------------------------------------ the right column
    def _side(self, program: tuple[str, ...]) -> QWidget:
        """The right column (rule 8): "What happens" (the tier badge and the sentence), the command card, and Cancel
        and Continue… at its bottom right (rule 9). It scrolls on its own when the window is short; the buttons stay."""
        side = QWidget(self)
        side.setProperty("apvRole", "summary")
        side.setFixedWidth(SIDE_WIDTH)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.summary = SummaryPanel(name="What happens and the command", parent=side, width=SIDE_WIDTH)
        lay.addWidget(self.summary, 1)
        group = QWidget(self.summary.inner)
        group.setAccessibleName("What happens")
        glay = QVBoxLayout(group)
        glay.setContentsMargins(0, 0, 0, 0)
        glay.setSpacing(6)
        glay.addWidget(forms.heading("What happens", parent=group))
        card = QFrame(group)
        card.setProperty("apvRole", "card")
        card.setAccessibleName("What happens card")
        clay = QVBoxLayout(card)
        clay.setContentsMargins(14, 12, 14, 12)
        clay.setSpacing(8)
        self.tier = StatusBadge("", name="Risk tier", parent=card)
        set_control_tooltip(self.tier, "The job's risk tier, which sets the confirmation: R0 read-only (none), R1 "
                                       "writes local data (lists what is written), R2 network, downloads or paid "
                                       "calls (a tick box).")
        clay.addWidget(self.tier, 0, Qt.AlignmentFlag.AlignLeft)
        self.says = forms.caption("", name="What Continue will do", parent=card, role="secondary")
        set_control_tooltip(self.says, "What Continue will do, in plain words from the form's values. The command "
                                       "below is what runs.")
        clay.addWidget(self.says)
        self.error = forms.caption("", name="Form error", parent=card, role="secondary")
        clay.addWidget(self.error)
        glay.addWidget(card)
        # D-1064: a command the CLI refuses on this platform (a live run; a backend build on Windows ARM64) says why
        self.platform_notice = PlatformNotice("", name="This command on this platform", parent=group)
        glay.addWidget(self.platform_notice)
        self.summary.add(group)
        self.command = CommandCard(name="Command preview", title="Command", parent=self.summary.inner)
        self.command.program = shlex.join(program) if program else "agentprov"
        set_control_tooltip(self.command.copy_button, "Copies the command shown below, exactly as the job runs it, so "
                                                      "it can be run in a terminal.")
        self.summary.add(self.command)
        bar = QHBoxLayout()
        bar.setContentsMargins(20, 10, 20, 16)
        bar.setSpacing(10)
        bar.addStretch(1)
        cancel = QPushButton("Cancel", side)
        cancel.setAccessibleName("Cancel")
        cancel.clicked.connect(self.reject)
        set_control_tooltip(cancel, "Closes the form; nothing starts.")
        bar.addWidget(cancel)
        self.ok = QPushButton("Continue…", side)
        self.ok.setAccessibleName("Continue")
        set_control_tooltip(self.ok, "Shows the tier's confirmation (none for a read-only job), then starts the "
                                     "command shown as a job.")
        self.ok.clicked.connect(self._accept)
        bar.addWidget(self.ok)
        lay.addLayout(bar)
        return side

    # ------------------------------------------------------------------------------------------ building
    def _conformance_switch(self, parent: QWidget) -> Switch:
        switch = Switch(name="Run the W3C PROV conformance check", parent=parent, checked=True)
        if self.form.prov_generating and self.conformance_option is None:
            switch.setEnabled(False)
            set_help_tooltip(switch, "This CLI cannot skip the check yet (G2c-5): the check always runs.")
        switch.clicked.connect(self._conformance_clicked)
        return switch

    def _add(self, sec: FormSection, row: QWidget) -> QWidget:
        """Record ``row`` as one of ``sec``'s (a section with no row shown is hidden whole)."""
        next(rows for s, rows in self.sections if s is sec).append(row)
        return row

    def _section(self, title: str, rows: list[Any], value: Callable[[str], Any], parent: QWidget) -> FormSection:
        sec = FormSection(title, parent=parent)
        self.sections.append((sec, []))
        for item in rows:
            if isinstance(item, Mode):
                self._mode_row(sec, item, value)
            else:
                self._field_row(sec, item, value)
        return sec

    def _mode_row(self, sec: FormSection, mode: Mode, value: Callable[[str], Any]) -> None:
        control = _ModeControl(mode, parent=sec.card, current=_initial(mode, value))
        control.currentIndexChanged.connect(self._refresh)
        self.modes[mode.key] = control
        trailing: list[QWidget] = self._inline_parts(mode.key, sec.card, value)
        tip = mode.tip
        if mode.flag:
            flag = self.placed[mode.flag].field
            self.inputs[mode.flag] = control
            tip = tip or field_tip(flag)
            if flag.tier == "R2" and not trailing:  # a row with inline parts: the tier badge beside it says it
                self.badges[mode.flag] = StatusBadge("Uses the network", name=f"{mode.label}: network", kind="warn",
                                                     parent=sec.card)
                set_control_tooltip(self.badges[mode.flag], NETWORK_BADGE_TIP)
                trailing.append(self.badges[mode.flag])
        self._add(sec, sec.add_row(mode.label, control, caption_text=mode.caption, tip=tip or None,
                                   trailing=trailing))

    def _field_row(self, sec: FormSection, p: Placed, value: Callable[[str], Any]) -> None:
        f, look = p.field, p.look
        w = self._control(f, look, p.label, value(f.key), sec.card)
        self.inputs[f.key] = w
        trailing: list[QWidget] = self._inline_parts(f.key, sec.card, value)
        if f.kind == "bool" and f.tier == "R2":
            self.badges[f.key] = StatusBadge("Uses the network", name=f"{p.label}: network", kind="warn",
                                             parent=sec.card)
            set_control_tooltip(self.badges[f.key], NETWORK_BADGE_TIP)
            trailing.append(self.badges[f.key])
        subject = w.edit if isinstance(w, PathField) else None
        short = isinstance(w, IntField | DecimalField | Switch | SegmentedControl)  # keeps its size, to the left
        self.rows[f.key] = sec.add_row(p.label, w, caption_text=p.caption, tip=field_tip(f), subject=subject,
                                       trailing=trailing, stretch=not short,
                                       active=lambda key=f.key: self._active(key))
        self._add(sec, self.rows[f.key])

    def _inline_parts(self, host: str, parent: QWidget, value: Callable[[str], Any]) -> list[QWidget]:
        """The fields the table places after ``host``'s control: a bool as a tick box with its label, any other as
        its short label, control and unit. Each part is that field's entry in :attr:`rows` (shown only while the
        field applies); its caption is added to its tooltip."""
        parts: list[QWidget] = []
        for p in self.inline.get(host, ()):
            f = p.field
            part = QWidget(parent)
            part.setAccessibleName(p.label)
            lay = QHBoxLayout(part)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(6)
            w: QWidget
            labels: list[QWidget] = []
            if f.kind == "bool":
                box = QCheckBox(p.label, part)
                box.setChecked(bool(value(f.key)))
                box.toggled.connect(self._refresh)
                box.setAccessibleName(f.label)
                w = box
            else:
                w = self._control(f, p.look, p.label, value(f.key), part)
                label = SafeLabel(p.label, name=f"{p.label} label", parent=part, selectable=False)
                label.setBuddy(w)
                lay.addWidget(label)
                labels.append(label)
                if isinstance(w, IntField | DecimalField):
                    w.setFixedWidth(90)
            lay.addWidget(w)
            unit = getattr(w, "unit", "")
            if unit:
                unit_label = SafeLabel(unit, name=f"{p.label} unit", parent=part, selectable=False)
                unit_label.setProperty("apvRole", "unit")
                lay.addWidget(unit_label)
            tip = field_tip(f) + (f" {p.look.caption}." if p.look.caption else "")
            subject = w.edit if isinstance(w, PathField) else w
            for widget in (*labels, w):
                set_setting_tooltip(widget, tip, subject=subject, active=partial(self._active, f.key))
            self.inputs[f.key] = w
            self.rows[f.key] = part
            parts.append(part)
        return parts

    def _control(self, f: Field, look: Look, label: str, value: Any, parent: QWidget) -> QWidget:
        """The right control for a field (rule 6), set from ``value``; it reports changes to :meth:`_refresh`."""
        w: QWidget
        placeholder = look.placeholder or ("Required" if f.required else "")
        if f.kind == "bool":
            switch = Switch(name=f.label, parent=parent, checked=bool(value))
            switch.toggled.connect(self._refresh)
            w = switch
        elif f.kind == "choice":
            items = [(c or look.placeholder or "Default", c) for c in f.choices]
            current = max(0, list(f.choices).index(value)) if value in f.choices else 0
            seg = (SegmentedControl(items, name=f.label, parent=parent, current=current)
                   if 2 <= len(items) <= 4 and all(len(t) <= _SEGMENTS_MAX_CHARS for t, _ in items) else None)
            if seg is not None and seg.sizeHint().width() <= _SEGMENTS_MAX_WIDTH:
                seg.currentIndexChanged.connect(self._refresh)
                for i, (_text, data) in enumerate(items):
                    seg.set_tip(i, choice_tip(f, data))
                w = seg
            else:
                if seg is not None:
                    seg.setParent(None)
                    seg.deleteLater()
                box = forms.combo(parent, name=f.label)
                for text, data in items:
                    box.addItem(text, data)
                box.setCurrentIndex(current)
                box.currentIndexChanged.connect(self._refresh)
                w = box
        elif f.kind == "int":
            # GR-64: clamp a preset from any caller to the range; a C int would overflow on 2**31
            ok = isinstance(value, int) and not isinstance(value, bool) and value >= 0
            number = IntField(0, 10_000_000, min(value, 10_000_000) if ok else None, name=f.label, parent=parent,
                              placeholder=look.placeholder or "Default", unit=look.unit)
            number.valueChanged.connect(self._refresh)
            w = number
        elif f.kind == "float":
            ok = isinstance(value, int | float) and not isinstance(value, bool) and 0 <= value <= 1e9
            real = DecimalField(-1, 1e9, float(value) if ok else None, name=f.label, decimals=3, trim=True,
                                parent=parent, placeholder=look.placeholder or "Default", unit=look.unit)
            real.valueChanged.connect(self._refresh)
            w = real
        elif f.kind in ("path", "dir"):
            folder = look.folder if look.folder is not None else f.kind == "dir"
            path = PathField(str(value) if value is not None else "", name=f.label, folder=folder, parent=parent,
                             choose_name=f"Choose: {label}", placeholder=placeholder)
            path.edit.textChanged.connect(self._refresh)
            w = path
        else:
            line = QLineEdit(parent)
            if value is not None:
                line.setText(" ".join(value) if isinstance(value, list | tuple) else str(value))
            if placeholder:
                line.setPlaceholderText(placeholder)
            line.textChanged.connect(self._refresh)
            w = line
        w.setAccessibleName(f.label)
        return w

    # ------------------------------------------------------------------------------------------ state
    def _raw(self, key: str) -> Any:
        w = self.inputs[key]
        if isinstance(w, _ModeControl | QCheckBox):
            return w.isChecked()
        if isinstance(w, SegmentedControl | QComboBox):
            return w.currentData()
        if isinstance(w, IntField | DecimalField):
            return w.number()
        if isinstance(w, PathField | QLineEdit):
            return w.text()
        return None

    def _active(self, key: str, depth: int = 0) -> bool:
        """Whether a field is shown and set: its mode's chosen segment shows it, and its condition (``when``) holds."""
        mode = self.owner.get(key)
        if mode is not None and key != mode.flag and key not in self.modes[mode.key].shows():
            return False
        when = self.placed[key].look.when
        if not when:
            return True
        other, eq, wanted = when.partition("=")
        if other not in self.inputs or depth > 4 or not self._active(other, depth + 1):
            return False
        raw = self._raw(other)
        return raw == wanted if eq else _filled(raw)

    def _conformance_clicked(self, checked: bool) -> None:
        if not checked and not conformance_warning(self):
            self.conformance.setChecked(True)
        self._refresh()

    def values(self) -> dict[str, Any]:
        """The form's values; a field hidden by a choice is left out (unset)."""
        out: dict[str, Any] = {}
        for f in self.fields:
            if f.key in self.flags or self._active(f.key):
                out[f.key] = self._raw(f.key)
            else:
                out[f.key] = False if f.kind == "bool" else None
        return out

    def build(self) -> JobSpec:
        return build_spec(self.form, self.values(), extra=self.extra.text(), conformance=self.conformance.isChecked(),
                          conformance_option=self.conformance_option)

    def _layout(self) -> None:
        """Rule 3: only the rows that apply are shown; a section with none is hidden whole."""
        for key, row in self.rows.items():
            shown = self._active(key)
            if row.isHidden() == shown:
                row.setVisible(shown)
                if not isinstance(row, FormRow) and (host := row.parentWidget()) is not None:
                    host.updateGeometry()  # an inline part changes its row's width: no stale size up the column
        for key, badge in self.badges.items():
            badge.setVisible(self._active(key) and bool(self._raw(key)))
        for sec, rows in self.sections:
            sec.setVisible(any(not r.isHidden() for r in rows))

    def _refresh(self, *_args: Any) -> None:
        self._layout()
        try:
            spec = self.build()
        except FormError as exc:
            self.error.set_plain(str(exc))
            self.error.setVisible(True)
            self.ok.setEnabled(False)
            theme.mark_destructive(self.ok, self.form.name in DESTRUCTIVE_COMMANDS)
            self.platform_notice.show_limit(None)
            set_unavailable_tooltip(self.ok, None)
            self.says.set_plain(what_happens(self.form, self.values()))
            self.command.set_commands([], note="The command appears once the form is complete.")
            self.tier.set_status("")
            return
        self.error.set_plain("")
        self.error.setVisible(False)
        refused = platform_limits.current().for_argv(spec.argv) if self.form.tool is None else None
        self.platform_notice.show_limit(refused)
        set_unavailable_tooltip(self.ok, refused.message if refused is not None else None)
        self.ok.setEnabled(refused is None)
        theme.mark_destructive(self.ok, is_destructive(spec))
        self.says.set_plain(what_happens(self.form, self.values()))
        self.tier.set_status(*tier_badge(spec))
        self.command.set_commands([("", spec.argv)])

    def minimum_width(self) -> int:
        """The narrowest the dialog may be: the form's widest part shown (a section or the Advanced line), the page's
        margins, a scroll bar and the right column, so the form never scrolls sideways (rule 7). Measured from the
        parts themselves (the column's own cached size can still count a row hidden before the dialog showed)."""
        parts = self.page.column.findChildren(QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly)
        widest = max((w.minimumSizeHint().width() for w in parts if not w.isHidden()), default=0)
        return (widest + _PAGE_MARGINS[0] + _PAGE_MARGINS[2] + self.page.verticalScrollBar().sizeHint().width()
                + SIDE_WIDTH)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        # the rows hidden while the form was built (rule 3) leave stale sizes in the layouts' pending requests: settle
        # them now and let the scroll area size the column from them, so the column is never laid out wider than the
        # page for the first rounds of the event loop
        QCoreApplication.sendPostedEvents(None, QEvent.Type.LayoutRequest)
        self.page.setWidgetResizable(True)
        QTimer.singleShot(0, self, self._shown)  # the layouts settle once the dialog shows

    def _shown(self) -> None:
        self.setMinimumWidth(self.minimum_width())
        self._refresh()  # the card wraps the command to its width, known once the dialog shows

    def command_line(self) -> str:
        """The command the job runs, on one line (what Copy copies)."""
        return self.command.plain()

    def _accept(self) -> None:
        try:
            spec = self.build()
        except FormError as exc:
            self.error.set_plain(str(exc))
            self.error.setVisible(True)
            return
        if self.form.tool is None and platform_limits.current().for_argv(spec.argv) is not None:
            return  # D-1064: refused here (the notice says why)
        confirmed = confirm(self, spec, shlex.join([*self.program, *spec.argv]))
        if confirmed is not None:
            self.spec = confirmed
            self.accept()
