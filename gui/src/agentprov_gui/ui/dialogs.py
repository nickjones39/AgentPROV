"""About and Settings windows (design §6.6, §6.8; macos-design §3.1: About from the App menu, Settings with ⌘,).

Both are in the GUI's form style (D-1060): page titles, sections of rows in rounded cards under small capitalised
headings, plain labels with a grey caption, the CLI key or flag in the tooltip, and macOS button placement.

* **Settings** is a sidebar of panes in four groups (App: General, Appearance, Viewer, Updates; Running: Jobs, Compute, Dev
  Runs, CI; Models and costs: Keys, Local Models, Prices, Estimate, Assistant; Release: Zenodo) beside the chosen pane,
  with Cancel and OK at the bottom right. OK applies every pane (each writes only what changed); Cancel writes nothing.
  The panes that hold ``agentprov settings`` show the terminal commands of their pending changes.
* **About** shows the versions, Check for Updates (D-1065: the last check, the newest release, Download and Install…
  and the terminal commands; :mod:`agentprov_gui.ui.updates`), the formats, the project and the third-party notices.

All text is plain: the repository name is selectable text with no link (S4), and the notices are a read-only plain-text
pane.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Final

import PySide6
from PySide6.QtCore import Qt, qVersion
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from agentprov_gui import text as T
from agentprov_gui.about import AUTHOR, LICENCE, NOTICES, PURPOSE, REPOSITORY, about_facts
from agentprov_gui.settings import Settings
from agentprov_gui.ui import forms, theme
from agentprov_gui.ui.brand import mark_pixmap
from agentprov_gui.ui.forms import Disclosure, FormPage, FormSection, IntField, PathField, Switch
from agentprov_gui.ui.safe import (
    ReadOnlyText,
    SafeImage,
    SafeLabel,
    set_control_tooltip,
    set_list_item_tooltip,
)
from agentprov_gui.ui.settings_panes import ADVANCED_NAME, Choices

__all__ = ["GROUPS", "AboutDialog", "SettingsDialog"]

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

#: the Settings sidebar: groups of panes, in order
GROUPS: Final = (("App", ("General", "Appearance", "Viewer", "Updates")),
                 ("Running", ("Jobs", "Compute", "Dev Runs", "CI")),
                 ("Models and costs", ("Keys", "Local Models", "Prices", "Estimate", "Assistant")),
                 ("Release", ("Zenodo",)))
#: what each pane holds (its sidebar tooltip)
PANE_TIPS: Final = {
    "General": "The AgentPROV checkout or installed agentprov the app runs, and the corpus folders the Viewer scans.",
    "Appearance": "Light or dark, the graph palette, tooltips and the experimental native toolbar.",
    "Viewer": "How much content text the Viewer shows.",
    "Updates": "Whether the app checks for a new release once a day when it starts (update.auto_check).",
    "Jobs": "What agentprov jobs prune keeps, and whether batches go on after a failed step (jobs.*).",
    "Compute": "The machine preset, worker processes per command and the shared job queue (compute.*).",
    "Dev Runs": "What a dev run samples and checks, and the live dev run's caps (devrun.*).",
    "CI": "The default CI target and the CI targets' state (ci.*).",
    "Keys": "The API keys and Zenodo tokens in the OS keychain (agentprov keys).",
    "Local Models": "What run uses for a local model: its folder, size, parameters and memory (local_models.*).",
    "Prices": "The price table's sources and your per-model overrides (agentprov prices).",
    "Estimate": "The default assumptions of an estimate, and the daily price refresh (estimate.default.*).",
    "Assistant": "Who answers in Help › Assistant (assistant.*).",
    "Zenodo": "The defaults of the draft-only Zenodo uploader (zenodo.*).",
}
SIDEBAR_WIDTH: Final = 200


def _sidebar_style(t: theme.Tokens) -> str:
    """The Settings sidebar (Settings.dc.html): grey, its group headings small and grey, the chosen pane in the accent
    colour with rounded corners; from the theme's tokens."""
    return (f"QListWidget {{ background: {t.summary}; border: none; border-right: 1px solid {t.card_border}; "
            "padding: 10px 8px; outline: 0; }"
            f"QListWidget::item {{ color: {t.text}; padding: 4px 8px; border-radius: 6px; }}"
            f"QListWidget::item:selected {{ color: {t.accent_text}; background: {t.accent}; }}"
            f"QListWidget::item:disabled {{ color: {t.caption}; padding: 10px 8px 2px 8px; }}")


def _section(page: FormPage, title: str, *, note: str = "") -> FormSection:
    sec = FormSection(title, parent=page.column, note=note)
    page.add(sec)
    return sec


def _value(text: str, name: str, parent: QWidget) -> SafeLabel:
    """A read-only value of a row: plain, selectable, wrapped (never widens the column)."""
    label = SafeLabel(T.line(text, 200), name=name, parent=parent)
    label.setWordWrap(True)
    label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    return label


class AboutDialog(QDialog):
    def __init__(self, checkout: Path | None, parent: QWidget | None = None, *, updates: Any = None) -> None:
        """``updates``: the main window's :class:`~agentprov_gui.ui.updates.UpdateController` (default: one for the
        checkout's CLI, this dialog's own)."""
        super().__init__(parent)
        self.setWindowTitle("About AgentPROV")
        self.setAccessibleName("About AgentPROV")
        self.resize(640, 720)
        facts = about_facts(checkout, qVersion(), PySide6.__version__)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        page = FormPage(name="About AgentPROV", parent=self)
        lay.addWidget(page, 1)
        head = QWidget(page.column)
        hl = QHBoxLayout(head)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(16)
        hl.addWidget(SafeImage(mark_pixmap(64, dark=theme.is_dark(), ratio=self.devicePixelRatioF()),
                               name="AgentPROV logo", parent=head))
        titles = QVBoxLayout()
        titles.setSpacing(2)
        name = SafeLabel("AgentPROV", name="Application name", parent=head)
        name.setFont(theme.scaled_font("title"))
        titles.addWidget(name)
        titles.addWidget(forms.caption("Execution provenance for LLM-agent security research",
                                       name="Application purpose", parent=head, role="secondary"))
        titles.addStretch(1)
        hl.addLayout(titles, 1)
        page.add(head)
        sec = _section(page, "Versions")
        for label, value, tip in (
                ("GUI version", facts.gui_version, "The version of this desktop app (agentprov-gui)."),
                ("Core software version", facts.core_version, "The version of the agentprov core library this app "
                                                              "imports."),
                ("Qt / PySide6", f"{facts.qt_version} / {facts.pyside_version}",
                 "The versions of Qt and of PySide6 (Qt for Python) this app runs on.")):
            sec.add_row(label, _value(value, label, sec.card), tip=tip)
        from agentprov_gui.ui.updates import UpdatesSection

        self.updates = updates if updates is not None else _own_updates(checkout, self)
        self.updates_section = UpdatesSection(self.updates, page.column)
        page.add(self.updates_section)
        sec = _section(page, "Formats", note="The format versions this app reads and the core writes.")
        for k, v in facts.formats:
            sec.add_row(f"Format: {k}", _value(v, f"Format: {k}", sec.card), tip=FORMAT_TIPS.get(k) or None)
        sec = _section(page, "Project", note=PURPOSE)
        for label, value, tip in (
                ("Git commit", facts.commit, "The commit of the AgentPROV checkout set in Settings › General, marked "
                                             "(modified) when its tree has uncommitted changes."),
                ("Repository", REPOSITORY, ""),
                ("Licence", LICENCE, "The licence of AgentPROV itself; the notices below cover third-party software."),
                ("Author", AUTHOR, "")):
            sec.add_row(label, _value(value, label, sec.card), tip=tip or None)
        sec = _section(page, "Third-party notices")
        notices = ReadOnlyText(name="Third-party notices", parent=sec.card, wrap=True)
        notices.setPlainText(NOTICES)
        notices.setMinimumHeight(140)
        notices.setFrameShape(QFrame.Shape.NoFrame)
        set_control_tooltip(notices, "The licences of the third-party software in the app's bundles: Qt and PySide6, "
                                     "and the Python packages.")
        sec.add(notices)
        footer = QWidget(self)
        footer.setProperty("apvRole", "footer")
        row = QHBoxLayout(footer)
        row.setContentsMargins(20, 12, 20, 12)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, footer)
        buttons.rejected.connect(self.reject)
        row.addWidget(buttons)
        lay.addWidget(footer)
        self.facts = facts


def _own_updates(checkout: Path | None, owner: QWidget) -> Any:
    """An update controller for the checkout's CLI (About opened without the main window's)."""
    from agentprov_gui import updates as U
    from agentprov_gui.jobs.manager import CliLocator
    from agentprov_gui.live.cli import call
    from agentprov_gui.ui.updates import UpdateController

    cli = CliLocator.for_checkout(checkout)
    return UpdateController(lambda argv, timeout: call(cli, argv, timeout=timeout), bundle=U.app_bundle(),
                            gui=U.app_version(), parent=owner)


class SettingsDialog(QDialog):
    """The Settings window: a sidebar of grouped panes (:data:`GROUPS`) beside the chosen pane, Cancel and OK below.
    General, Appearance and Viewer are the GUI's own (Qt-stored) settings; every other pane is an ``agentprov`` client
    (:attr:`panes`, saved on OK)."""

    def __init__(self, settings: Settings, parent: QWidget | None = None, *, pane: str | None = None) -> None:
        """``pane`` names the pane shown first (Help › Assistant opens "Assistant")."""
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setAccessibleName("Settings")
        self.resize(980, 720)
        self.settings = settings
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        outer.addLayout(body, 1)
        self.sidebar = QListWidget(self)
        self.sidebar.setAccessibleName("Settings panes")
        self.sidebar.setFixedWidth(SIDEBAR_WIDTH)
        self.sidebar.setStyleSheet(_sidebar_style(theme.tokens()))
        body.addWidget(self.sidebar)
        self.stack = QStackedWidget(self)
        self.stack.setAccessibleName("Settings pane")
        body.addWidget(self.stack, 1)
        pages: dict[str, QWidget] = {"General": self._general(), "Appearance": self._appearance(),
                                     "Viewer": self._viewer()}
        from agentprov_gui.ui.livepanes import EstimatePane, KeysPane, PricesPane
        from agentprov_gui.ui.settings_panes import (
            AssistantPane,
            CiPane,
            ComputePane,
            DevRunPane,
            JobsPane,
            LocalModelsPane,
            UpdatesPane,
        )
        from agentprov_gui.ui.zenodo import ZenodoPane

        stack = self.stack
        self.panes: list[Any] = [
            JobsPane(settings.checkout, stack), ComputePane(settings.checkout, stack),
            CiPane(settings.checkout, stack), DevRunPane(settings.checkout, stack),
            KeysPane(settings.store, settings.checkout, stack), LocalModelsPane(settings.checkout, stack),
            PricesPane(settings.checkout, stack), EstimatePane(settings.checkout, stack),
            ZenodoPane(settings.checkout, stack), AssistantPane(settings.checkout, stack),
            UpdatesPane(settings.checkout, stack)]
        pages.update(zip(("Jobs", "Compute", "CI", "Dev Runs", "Keys", "Local Models", "Prices", "Estimate", "Zenodo",
                          "Assistant", "Updates"), self.panes, strict=True))
        self.titles: list[str] = []
        for group, titles in GROUPS:
            header = QListWidgetItem(group.upper())
            header.setFlags(Qt.ItemFlag.NoItemFlags)
            header.setFont(theme.scaled_font("heading"))
            self.sidebar.addItem(header)
            for title in titles:
                item = QListWidgetItem(title)
                item.setData(Qt.ItemDataRole.UserRole, self.stack.addWidget(pages[title]))
                set_list_item_tooltip(item, PANE_TIPS[title], wrap=True)
                self.sidebar.addItem(item)
                self.titles.append(title)
        self.sidebar.currentRowChanged.connect(self._nav)
        self.show_pane(pane if pane in self.titles else "General")
        self._footer(outer)

    # ------------------------------------------------------------------------------------------ navigation
    def _nav(self, row: int) -> None:
        item = self.sidebar.item(row)
        index = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if isinstance(index, int):
            self.stack.setCurrentIndex(index)

    def show_pane(self, title: str) -> None:
        """Show the pane named ``title`` (its sidebar row becomes current)."""
        for i in range(self.sidebar.count()):
            item = self.sidebar.item(i)
            if item.text() == title and item.flags() & Qt.ItemFlag.ItemIsSelectable:
                self.sidebar.setCurrentRow(i)
                return

    def current_pane(self) -> str:
        item = self.sidebar.currentItem()
        return item.text() if item is not None else ""

    def _footer(self, outer: QVBoxLayout) -> None:
        footer = QWidget(self)
        footer.setProperty("apvRole", "footer")
        row = QHBoxLayout(footer)
        row.setContentsMargins(20, 12, 20, 12)
        row.setSpacing(10)
        row.addStretch(1)
        cancel = QPushButton("Cancel", footer)
        cancel.setAccessibleName("Cancel")
        cancel.setAutoDefault(False)
        cancel.clicked.connect(self.reject)
        set_control_tooltip(cancel, "Closes Settings; nothing is saved.")
        row.addWidget(cancel)
        self.ok_btn = QPushButton("OK", footer)
        self.ok_btn.setAccessibleName("OK")
        self.ok_btn.setDefault(True)
        self.ok_btn.clicked.connect(self._accept)
        set_control_tooltip(self.ok_btn, "Saves every pane: the app's own settings, and for the others only what "
                                         "changed (the terminal commands each pane shows).")
        row.addWidget(self.ok_btn)
        outer.addWidget(footer)

    # ------------------------------------------------------------------------------------------ the app's own panes
    def _general(self) -> FormPage:
        s = self.settings
        page = FormPage(name="General settings", title="General", parent=self)
        sec = _section(page, "AgentPROV")
        self.checkout_field = PathField(str(s.checkout or ""), name="AgentPROV checkout", folder=True,
                                        choose_name="Choose the AgentPROV checkout folder", placeholder="Not set",
                                        parent=sec.card)
        self.checkout: QLineEdit = self.checkout_field.edit
        sec.add_row("Checkout", self.checkout_field, caption_text="Your AgentPROV clone, for writes",
                    subject=self.checkout,
                    tip="The AgentPROV repository whose agentprov CLI runs every job, import and settings change, and "
                        "whose user guide Help › Docs shows. Without one, the agentprov program below is used, and "
                        "Help › Docs shows the guide that comes with the app.")
        self.cli_program_field = PathField(str(s.cli_program or ""), name="agentprov program",
                                           choose_name="Choose the agentprov program", placeholder="Found on PATH",
                                           parent=sec.card)
        self.cli_program: QLineEdit = self.cli_program_field.edit
        sec.add_row("agentprov program", self.cli_program_field, caption_text="Used when no checkout is set",
                    subject=self.cli_program,
                    tip="The agentprov command installed with pip install agentprov (for example ~/.local/bin/agentprov, "
                        "or the agentprov of a virtual environment). Empty: the first agentprov on PATH, then in "
                        "~/.local/bin, /opt/homebrew/bin and /usr/local/bin. Used only when no checkout is set.")
        self.cli_in_use = _value("", "CLI in use", sec.card)
        sec.add_row("CLI in use", self.cli_in_use, caption_text="Found from the two fields above",
                    tip="The agentprov that the Assistant, the Settings panes and the jobs run with these two "
                        "settings.")
        for field in (self.checkout, self.cli_program):
            field.editingFinished.connect(self._show_cli)
            field.textChanged.connect(lambda _t: self._show_cli())  # Choose… fills the field without editing
        self._show_cli()
        sec = _section(page, "Corpora")
        self.roots = QLineEdit("; ".join(str(p) for p in s.corpus_roots), sec.card)
        self.roots.setAccessibleName("Corpus roots")
        sec.add_row("Corpus roots", self.roots, caption_text="Folders the Viewer scans, separated by ;",
                    tip="Folders the Viewer scans for corpora, separated by semicolons. Each corpus found under them is "
                        "listed in the sidebar; nothing is written there.")
        return page

    def _appearance(self) -> FormPage:
        s = self.settings
        page = FormPage(name="Appearance settings", title="Appearance", parent=self)
        sec = _section(page, "Appearance")
        self.theme = Choices((("System", "system", "Follows the operating system's light or dark mode "
                                                   "(recommended)."),
                              ("Light", "light", "Always light."), ("Dark", "dark", "Always dark.")),
                             name="Appearance", parent=sec.card)
        self.theme.setCurrentText(s.theme)
        sec.add_row("Appearance", self.theme, caption_text="Follow the system is recommended",
                    tip="system follows the operating system's light or dark mode; light and dark force one.")
        self.graph_colours = Choices((("Accessible", "accessible", "Darkens the three PROV relation colours that fall "
                                                                   "under 3:1 contrast on a light canvas."),
                                      ("Exact", "exact", "Keeps the W3C PROV colours of agentprov render.")),
                                     name="Graph palette", parent=sec.card)
        self.graph_colours.setCurrentText(s.graph_palette)
        sec.add_row("Graph palette", self.graph_colours, caption_text="On a light canvas; a dark one has its own",
                    tip="accessible darkens the three PROV relation colours that fall under 3:1 contrast on a light "
                        "canvas; exact keeps the W3C PROV colours of agentprov render. A dark canvas always uses its "
                        "own variants.")
        sec = _section(page, "Help")
        self.show_tips = Switch(name="Show tooltips", parent=sec.card, checked=s.show_tooltips)
        sec.add_row("Show tooltips", self.show_tips,
                    caption_text="Explanations when the pointer rests on a control",
                    tip="On (default): resting the pointer on a control, a column header or a list item shows what it "
                        "does or holds, and on a graph node shows its attributes. Off: no tooltips anywhere in the "
                        "app. Applies when you press OK.")
        self.native_box = Disclosure("Advanced: experimental native macOS toolbar", screen="settings",
                                     key="appearance", name=ADVANCED_NAME, parent=page.column)
        set_control_tooltip(self.native_box.button, "Shows or hides the experimental native macOS toolbar setting.")
        sec = FormSection("Experimental", parent=self.native_box.content)
        self.native = Switch(name="Experimental: native macOS toolbar", parent=sec.card, checked=s.native_chrome)
        sec.add_row("Native macOS toolbar", self.native, caption_text="Takes effect at the next start",
                    tip="On: the main window uses a native macOS toolbar (SF Symbols, unified title bar). Off: Qt's "
                        "own toolbar. The change applies the next time the app starts.")
        self.native_box.add(sec)
        page.add(self.native_box)
        if sys.platform != "darwin":  # G5 P-6: the native chrome exists only on macOS; the stored value is kept
            self.native.hide()
            self.native_box.hide()
        return page

    def _viewer(self) -> FormPage:
        page = FormPage(name="Viewer settings", title="Viewer", parent=self)
        sec = _section(page, "Content")
        self.limit = IntField(1, T.CONTENT_CHARS_MAX, self.settings.content_limit, name="Content display limit",
                              unset=False, unit="characters", parent=sec.card)
        sec.add_row("Content display limit", self.limit, caption_text=f"Up to {T.CONTENT_CHARS_MAX:,}; default 500",
                    tip="How many characters of each message, tool argument or result the Viewer shows when Show "
                        "content is on (default 500). Longer text is cut; corpus text is always shown as plain, quoted "
                        "text.")
        return page

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
        s.theme = str(self.theme.currentData())
        s.graph_palette = str(self.graph_colours.currentData())
        s.content_limit = self.limit.value()
        s.native_chrome = self.native.isChecked()
        s.show_tooltips = self.show_tips.isChecked()
        for pane in self.panes:
            pane.save()
        self.accept()

