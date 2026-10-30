"""The New Job form and the confirmation by tier (design §6.2 "New job", §8.3a, §8.4; macos-design §3.3).

The form is generated from :data:`agentprov_gui.jobs.commands.FORMS`. It shows the exact argv it will run and its tier
before anything starts. Confirmations:

* **R0** none (the argv is shown);
* **R1** a dialog that names what is written and where; ``purge`` also asks for the object's first 8 hex digits, then
  ``--yes`` is added;
* **R2** the hosts or cost note and an explicit tick box; the network flags are in the argv only because the user set
  them in the form.

The D-432 conformance box ("Run the W3C PROV conformance check (tier 4)") is on by default for PROV-generating forms.
Unticking it shows a blocking warning every time; the default button keeps the check. It is enabled only when the CLI
offers the option (G2c-5).
"""

from __future__ import annotations

import shlex
from collections.abc import Mapping
from typing import Any, Final

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QLineEdit,
    QScrollArea,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from agentprov_gui import text as T
from agentprov_gui.jobs.commands import GLOBAL_FIELDS, CommandForm, Field, FormError, JobSpec, build_spec
from agentprov_gui.ui.safe import ReadOnlyText, SafeForm, SafeLabel, choose, set_tooltip

__all__ = ["CONFORMANCE_WARNING", "JobDialog", "confirm", "conformance_warning"]

CONFORMANCE_WARNING: Final = (
    "Not advisable. The PROV bundles of this run will not be checked against the W3C PROV constraints. The corpus will "
    "be marked unvalidated, cannot be sealed or released until a full recompute validates it into a new corpus, and its "
    "results should "
    "not be reported."
)
TIER_TEXT: Final = {"R0": "R0 · read-only", "R1": "R1 · writes local data", "R2": "R2 · network or paid calls"}


def conformance_warning(parent: QWidget | None) -> bool:
    """True when the user chose to skip the check (default: keep it)."""
    return choose(parent, "PROV conformance check", "Skip the W3C PROV conformance check?", CONFORMANCE_WARNING,
                  "Keep the Check", "Skip the Check")


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
    ok.button(QDialogButtonBox.StandardButton.Cancel).setDefault(True)
    tick: QCheckBox | None = None
    typed: QLineEdit | None = None
    if spec.tier == "R2":
        tick = QCheckBox("I understand this job uses the network (and may download large files or cost money)", dlg)
        tick.setAccessibleName("Network consent")
        lay.addWidget(tick)
    if spec.destructive:
        digest = next((a for a in spec.argv if a.startswith("sha256:")), "")
        lay.addWidget(SafeLabel("This removal is irreversible. Type the first 8 hex digits of the object to confirm.",
                                name="Purge warning", parent=dlg))
        typed = QLineEdit(dlg)
        typed.setAccessibleName("First 8 hex digits of the object")
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


class JobDialog(QDialog):
    """One command's form, its argv preview and tier, then the confirmation."""

    def __init__(self, form: CommandForm, *, program: tuple[str, ...], preset: Mapping[str, Any] | None = None,
                 conformance_option: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.form, self.program, self.conformance_option = form, program, conformance_option
        self.setWindowTitle(form.title)
        self.setAccessibleName(form.title)
        self.resize(720, 640)
        self.spec: JobSpec | None = None
        self.inputs: dict[str, QWidget] = {}
        outer = QVBoxLayout(self)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        body = QWidget(scroll)
        column = QVBoxLayout(body)
        main = QWidget(body)
        fl = SafeForm(main)
        column.addWidget(main)
        self.more = QToolButton(body)
        self.more.setText("More Options")
        self.more.setCheckable(True)
        self.more.setAccessibleName("Show more options")
        column.addWidget(self.more)
        extra_box = QWidget(body)
        more_form = SafeForm(extra_box)
        extra_box.setVisible(False)
        self.more.toggled.connect(extra_box.setVisible)
        column.addWidget(extra_box)
        column.addStretch(1)
        preset = dict(preset or {})
        fields: tuple[Field, ...] = (*form.fields, *(GLOBAL_FIELDS if form.tool is None else ()))
        self.fields = fields
        for f in fields:
            w: QWidget
            value = preset.get(f.key, f.default)
            if f.kind == "bool":
                cb = QCheckBox(body)
                cb.setChecked(bool(value))
                cb.toggled.connect(self._refresh)
                w = cb
            elif f.kind == "choice":
                combo = QComboBox(body)
                combo.addItems(list(f.choices))
                if value in f.choices:
                    combo.setCurrentText(str(value))
                combo.currentTextChanged.connect(self._refresh)
                w = combo
            elif f.kind == "int":
                spin = QSpinBox(body)
                spin.setRange(-1, 10_000_000)
                spin.setSpecialValueText("—")
                # GR-64: clamp a preset from any caller to the range; a C int would overflow on 2**31.
                ok = isinstance(value, int) and not isinstance(value, bool)
                spin.setValue(min(max(value, -1), 10_000_000) if ok else -1)
                spin.valueChanged.connect(self._refresh)
                w = spin
            else:
                line = QLineEdit(body)
                if value is not None:
                    line.setText(" ".join(value) if isinstance(value, list | tuple) else str(value))
                line.textChanged.connect(self._refresh)
                w = line
            w.setAccessibleName(f.label)
            if f.help:
                set_tooltip(w, f.help)
            self.inputs[f.key] = w
            (more_form if f.advanced else fl).add(f.label + (" *" if f.required else ""), w)
        self.extra = QLineEdit(body)
        self.extra.setPlaceholderText("additional options (argv; no shell)")
        self.extra.textChanged.connect(self._refresh)
        fl.add("Additional options", self.extra)
        self.conformance = QCheckBox("Run the W3C PROV conformance check (tier 4)", body)
        self.conformance.setAccessibleName("Run the W3C PROV conformance check")
        self.conformance.setChecked(True)
        self.conformance.setVisible(form.prov_generating)
        if form.prov_generating and conformance_option is None:
            self.conformance.setEnabled(False)
            set_tooltip(self.conformance, "This CLI cannot skip the check yet (G2c-5): the check always runs.")
        self.conformance.clicked.connect(self._conformance_clicked)
        fl.add("Conformance", self.conformance)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)
        self.tier = SafeLabel("", name="Risk tier", parent=self)
        outer.addWidget(self.tier)
        self.preview = ReadOnlyText(name="Command preview", parent=self, wrap=True)
        self.preview.setMaximumHeight(110)
        outer.addWidget(self.preview)
        self.error = SafeLabel("", name="Form error", parent=self)
        outer.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        self.ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.ok.setText("Continue…")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)
        self._refresh()

    def _conformance_clicked(self, checked: bool) -> None:
        if not checked and not conformance_warning(self):
            self.conformance.setChecked(True)
        self._refresh()

    def values(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for f in self.fields:
            w = self.inputs[f.key]
            if isinstance(w, QCheckBox):
                out[f.key] = w.isChecked()
            elif isinstance(w, QComboBox):
                out[f.key] = w.currentText()
            elif isinstance(w, QSpinBox):
                out[f.key] = w.value() if w.value() >= 0 else None
            elif isinstance(w, QLineEdit):
                out[f.key] = w.text()
        return out

    def build(self) -> JobSpec:
        return build_spec(self.form, self.values(), extra=self.extra.text(), conformance=self.conformance.isChecked(),
                          conformance_option=self.conformance_option)

    def _refresh(self) -> None:
        try:
            spec = self.build()
        except FormError as exc:
            self.error.set_plain(str(exc))
            self.ok.setEnabled(False)
            self.preview.setPlainText("")
            self.tier.set_plain("")
            return
        self.error.set_plain("")
        self.ok.setEnabled(True)
        self.tier.set_plain(TIER_TEXT.get(spec.tier, spec.tier) + (" · destructive" if spec.destructive else ""))
        self.preview.setPlainText(shlex.join([*self.program, *spec.argv]))

    def _accept(self) -> None:
        try:
            spec = self.build()
        except FormError as exc:
            self.error.set_plain(str(exc))
            return
        confirmed = confirm(self, spec, shlex.join([*self.program, *spec.argv]))
        if confirmed is not None:
            self.spec = confirmed
            self.accept()
