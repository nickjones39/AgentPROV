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
from agentprov_gui.ui.safe import ReadOnlyText, SafeForm, SafeImage, SafeLabel

__all__ = ["AboutDialog", "SettingsDialog"]


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
            ("GUI version", facts.gui_version),
            ("Core software version", facts.core_version),
            *((f"Format: {k}", v) for k, v in facts.formats),
            ("Git commit", facts.commit),
            ("Repository", REPOSITORY),
            ("Licence", LICENCE),
            ("Author", AUTHOR),
            ("", PURPOSE),
            ("Qt / PySide6", f"{facts.qt_version} / {facts.pyside_version}"),
        ]
        for label, value in rows:
            form.add(label, SafeLabel(T.line(value, 200), name=label or "Purpose", parent=self))
        lay.addLayout(form)
        notices = ReadOnlyText(name="Third-party notices", parent=self, wrap=True)
        notices.setPlainText(NOTICES)
        notices.setMinimumHeight(120)
        lay.addWidget(notices)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self.facts = facts


class SettingsDialog(QDialog):
    """G1 panes: General (paths), Appearance, Viewer. Jobs, Compute, Live, CI and Experimental come with G2/G3."""

    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
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
        gf.add("AgentPROV checkout (for writes)", self.checkout)
        self.roots = QLineEdit("; ".join(str(p) for p in settings.corpus_roots), general)
        self.roots.setAccessibleName("Corpus roots")
        gf.add("Corpus roots (separated by ;)", self.roots)
        tabs.addTab(general, "General")
        # Appearance
        appearance = QWidget(tabs)
        af = SafeForm(appearance)
        self.theme = QComboBox(appearance)
        self.theme.addItems(["system", "light", "dark"])
        self.theme.setCurrentText(settings.theme)
        af.add("Appearance (Follow system is recommended)", self.theme)
        self.graph_colours = QComboBox(appearance)
        self.graph_colours.addItems(["accessible", "exact"])
        self.graph_colours.setCurrentText(settings.graph_palette)
        af.add("Graph palette (light canvas)", self.graph_colours)
        self.native = QCheckBox(appearance)
        self.native.setChecked(settings.native_chrome)
        native_label = af.add("Experimental: native macOS toolbar (takes effect at the next start)", self.native)
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
        vf.add("Content display limit (characters, max 2,000)", self.limit)
        tabs.addTab(viewer, "Viewer")
        from agentprov_gui.ui.livepanes import EstimatePane, KeysPane, PricesPane
        from agentprov_gui.ui.settings_panes import CiPane, ComputePane, DevRunPane, JobsPane, LocalModelsPane
        from agentprov_gui.ui.zenodo import ZenodoPane

        self.panes: list[Any] = [
            JobsPane(settings.checkout, tabs), ComputePane(settings.checkout, tabs),
            CiPane(settings.checkout, tabs), DevRunPane(settings.checkout, tabs),
            KeysPane(settings.store, settings.checkout, tabs), LocalModelsPane(settings.checkout, tabs),
            PricesPane(settings.checkout, tabs), EstimatePane(settings.checkout, tabs),
            ZenodoPane(settings.checkout, tabs)]
        for pane, title in zip(self.panes, ("Jobs", "Compute", "CI", "Dev Runs", "Keys", "Local Models", "Prices",
                                            "Estimate", "Zenodo"),
                               strict=True):
            tabs.addTab(pane, title)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _accept(self) -> None:
        s = self.settings
        s.checkout = Path(self.checkout.text().strip()) if self.checkout.text().strip() else None
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
