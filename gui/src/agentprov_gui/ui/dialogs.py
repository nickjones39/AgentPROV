"""About and Settings windows (design §6.6, §6.8; macos-design §3.1: About from the App menu, Settings with ⌘,).

All text is plain: the repository name is selectable text with no link (S4), and the notices are a read-only plain-text
pane.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import PySide6
from PySide6.QtCore import qVersion
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLineEdit,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from agentprov_gui import text as T
from agentprov_gui.about import AUTHOR, LICENCE, NOTICES, PURPOSE, REPOSITORY, about_facts
from agentprov_gui.settings import Settings
from agentprov_gui.ui import theme
from agentprov_gui.ui.brand import mark_pixmap
from agentprov_gui.ui.safe import ReadOnlyText, SafeForm, SafeImage, SafeLabel, set_control_tooltip

__all__ = ["AboutDialog", "SettingsDialog"]

#: what each format row of About names (agentprov.versions.VERSIONS, and the job progress events)
FORMAT_TIPS = {
    "aer": "The AgentPROV Execution Record (AER) format the core writes: the canonical record of one execution.",
    "sem": "The format of the semantic (SEM) annotations made on each execution record.",
    "capture": "The raw-evidence event log a live run writes.",
    "prov_spec": "The provenance specification and rule catalogue that derive the W3C PROV bundles.",
    "compat_spec": "The frozen AgentDojo-PROV v2.3 compatibility rules, kept as a regression oracle (not the "
                   "recommended semantics).",
    "ontology": "The AgentPROV ontology (apv) the PROV bundles use.",
    "corpus_format": "The corpus layout the core writes.",
    "progress": "The progress events a job's CLI writes, which the Runs dashboards read.",
}


class AboutDialog(QDialog):
    def __init__(self, checkout: Path | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("About AgentPROV")
        self.setAccessibleName("About AgentPROV")
        facts = about_facts(checkout, qVersion(), PySide6.__version__)
        lay = QVBoxLayout(self)
        head = QHBoxLayout()
        head.addWidget(SafeImage(mark_pixmap(64, dark=theme.is_dark(), ratio=self.devicePixelRatioF()),
                                 name="AgentPROV logo", parent=self))
        titles = QVBoxLayout()
        name = SafeLabel("AgentPROV", name="Application name", parent=self)
        font = name.font()
        font.setPointSizeF(font.pointSizeF() * 1.4)
        font.setBold(True)
        name.setFont(font)
        titles.addWidget(name)
        titles.addWidget(SafeLabel("Execution provenance for LLM-agent security research", name="Application purpose",
                                   parent=self))
        head.addLayout(titles, 1)
        lay.addLayout(head)
        form = SafeForm()
        rows = [
            ("GUI version", facts.gui_version, "The version of this desktop app (agentprov-gui)."),
            ("Core software version", facts.core_version, "The version of the agentprov core library this app "
                                                          "imports."),
            *((f"Format: {k}", v, FORMAT_TIPS.get(k, "")) for k, v in facts.formats),
            ("Git commit", facts.commit, "The commit of the AgentPROV checkout set in Settings › General, marked "
                                         "(modified) when its tree has uncommitted changes."),
            ("Repository", REPOSITORY, ""),
            ("Licence", LICENCE, "The licence of AgentPROV itself; the notices below cover third-party software."),
            ("Author", AUTHOR, ""),
            ("", PURPOSE, ""),
            ("Qt / PySide6", f"{facts.qt_version} / {facts.pyside_version}",
             "The versions of Qt and of PySide6 (Qt for Python) this app runs on."),
        ]
        for label, value, tip in rows:
            form.add(label, SafeLabel(T.line(value, 200), name=label or "Purpose", parent=self), tip or None)
        lay.addLayout(form)
        notices = ReadOnlyText(name="Third-party notices", parent=self, wrap=True)
        notices.setPlainText(NOTICES)
        notices.setMinimumHeight(120)
        set_control_tooltip(notices, "The licences of the third-party software in the app's bundles: Qt and PySide6, "
                                     "and the Python packages.")
        lay.addWidget(notices)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self.facts = facts


class SettingsDialog(QDialog):
    """G1 panes: General (paths), Appearance, Viewer. Jobs, Compute, Live, CI and Experimental come with G2/G3."""

    def __init__(self, settings: Settings, parent: QWidget | None = None, *, pane: str | None = None) -> None:
        """``pane`` names the tab shown first (Help › Assistant opens "Assistant")."""
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setAccessibleName("Settings")
        self.settings = settings
        lay = QVBoxLayout(self)
        tabs = QTabWidget(self)
        tabs.setAccessibleName("Settings panes")
        lay.addWidget(tabs)
        # General
        general = QWidget(tabs)
        gf = SafeForm(general)
        self.checkout = QLineEdit(str(settings.checkout or ""), general)
        self.checkout.setAccessibleName("AgentPROV checkout")
        gf.add("AgentPROV checkout (for writes)", self.checkout,
               "The AgentPROV repository whose agentprov CLI runs every job, import and settings change, and whose "
               "user guide Help › Docs shows. Without one, the agentprov program below is used, and Help › Docs shows "
               "the guide that comes with the app.")
        self.cli_program = QLineEdit(str(settings.cli_program or ""), general)
        self.cli_program.setAccessibleName("agentprov program")
        self.cli_program.setPlaceholderText("found on PATH")
        gf.add("agentprov program (when no checkout is set)", self.cli_program,
               "The agentprov command installed with pip install agentprov (for example ~/.local/bin/agentprov, or "
               "the agentprov of a virtual environment). Empty: the first agentprov on PATH, then in ~/.local/bin, "
               "/opt/homebrew/bin and /usr/local/bin. Used only when no checkout is set.")
        self.cli_in_use = SafeLabel("", name="CLI in use", parent=general)
        self.cli_in_use.setWordWrap(True)
        gf.add("CLI in use", self.cli_in_use,
               "The agentprov that the Assistant, the Settings panes and the jobs run with these two settings.")
        for field in (self.checkout, self.cli_program):
            field.editingFinished.connect(self._show_cli)
        self._show_cli()
        self.roots = QLineEdit("; ".join(str(p) for p in settings.corpus_roots), general)
        self.roots.setAccessibleName("Corpus roots")
        gf.add("Corpus roots (separated by ;)", self.roots,
               "Folders the Viewer scans for corpora, separated by semicolons. Each corpus found under them is "
               "listed in the sidebar; nothing is written there.")
        tabs.addTab(general, "General")
        # Appearance
        appearance = QWidget(tabs)
        af = SafeForm(appearance)
        self.theme = QComboBox(appearance)
        self.theme.addItems(["system", "light", "dark"])
        self.theme.setCurrentText(settings.theme)
        af.add("Appearance (Follow system is recommended)", self.theme,
               "system follows the operating system's light or dark mode; light and dark force one.")
        self.graph_colours = QComboBox(appearance)
        self.graph_colours.addItems(["accessible", "exact"])
        self.graph_colours.setCurrentText(settings.graph_palette)
        af.add("Graph palette (light canvas)", self.graph_colours,
               "accessible darkens the three PROV relation colours that fall under 3:1 contrast on a light canvas; "
               "exact keeps the W3C PROV colours of agentprov render. A dark canvas always uses its own variants.")
        self.native = QCheckBox(appearance)
        self.native.setChecked(settings.native_chrome)
        native_label = af.add("Experimental: native macOS toolbar (takes effect at the next start)", self.native,
                              "On: the main window uses a native macOS toolbar (SF Symbols, unified title bar). Off: "
                              "Qt's own toolbar. The change applies the next time the app starts.")
        if sys.platform != "darwin":  # G5 P-6: the native chrome exists only on macOS; the stored value is kept
            native_label.hide()
            self.native.hide()
        tabs.addTab(appearance, "Appearance")
        # Viewer
        viewer = QWidget(tabs)
        vf = SafeForm(viewer)
        self.limit = QSpinBox(viewer)
        self.limit.setRange(1, T.CONTENT_CHARS_MAX)
        self.limit.setValue(settings.content_limit)
        vf.add("Content display limit (characters, max 2,000)", self.limit,
               "How many characters of each message, tool argument or result the Viewer shows when Show content is "
               "on (default 500). Longer text is cut; corpus text is always shown as plain, quoted text.")
        tabs.addTab(viewer, "Viewer")
        from agentprov_gui.ui.livepanes import EstimatePane, KeysPane, PricesPane
        from agentprov_gui.ui.settings_panes import (
            AssistantPane,
            CiPane,
            ComputePane,
            DevRunPane,
            JobsPane,
            LocalModelsPane,
        )
        from agentprov_gui.ui.zenodo import ZenodoPane

        self.panes: list[Any] = [
            JobsPane(settings.checkout, tabs), ComputePane(settings.checkout, tabs),
            CiPane(settings.checkout, tabs), DevRunPane(settings.checkout, tabs),
            KeysPane(settings.store, settings.checkout, tabs), LocalModelsPane(settings.checkout, tabs),
            PricesPane(settings.checkout, tabs), EstimatePane(settings.checkout, tabs),
            ZenodoPane(settings.checkout, tabs), AssistantPane(settings.checkout, tabs)]
        for p, title in zip(self.panes, ("Jobs", "Compute", "CI", "Dev Runs", "Keys", "Local Models", "Prices",
                                         "Estimate", "Zenodo", "Assistant"),
                            strict=True):
            tabs.addTab(p, title)
        self.tabs = tabs
        for i in range(tabs.count()):
            if pane is not None and tabs.tabText(i) == pane:
                tabs.setCurrentIndex(i)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _show_cli(self) -> None:
        """Settings › General's "CLI in use" for the two fields as typed (file checks only; nothing runs)."""
        from agentprov_gui.jobs.manager import CliLocator, installed_program

        checkout, program = self.checkout.text().strip(), self.cli_program.text().strip()
        if checkout:
            cli = CliLocator.for_checkout(Path(checkout))
        else:
            found = installed_program(Path(program) if program else None)
            cli = CliLocator(None, (str(found),) if found is not None else ())
        self.cli_in_use.set_plain(T.line(cli.describe(), 300))

    def _accept(self) -> None:
        s = self.settings
        s.checkout = Path(self.checkout.text().strip()) if self.checkout.text().strip() else None
        s.cli_program = Path(self.cli_program.text().strip()) if self.cli_program.text().strip() else None
        roots = [Path(p.strip()) for p in self.roots.text().split(";") if p.strip()]
        if roots:
            s.corpus_roots = roots
        s.theme = self.theme.currentText()
        s.graph_palette = self.graph_colours.currentText()
        s.content_limit = self.limit.value()
        s.native_chrome = self.native.isChecked()
        for pane in self.panes:
            pane.save()
        self.accept()
