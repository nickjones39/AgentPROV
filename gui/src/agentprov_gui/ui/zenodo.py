"""Zenodo in the GUI (D-880): Settings › Zenodo, the release.toml template and Package › Create Zenodo drafts….

* **Settings › Zenodo** (``zenodo.*`` keys of ``agentprov settings``, D-703): the target the drafts dialog preselects
  (never a default of the uploader's ``--target``, D-790), community identifiers, the AgentPROV concept DOI and default
  creators. They only **prefill**: ``release.toml`` stays the record (H.10.2), written by the user. No token is a
  setting; the tokens are rows of Settings › Keys (``agentprov keys``, the OS keychain).
* **Write release.toml from the Zenodo settings…**: a template with the creators and the concept DOI, written only
  where no file exists; its empty title keeps ``package --deposit`` refusing it until the user fills it in.
* **Create Zenodo drafts…**: runs the draft-only uploader (``agentprov_zenodo``, :mod:`agentprov_gui.zenodo_run`) for
  the deposits of a collection, one per licence class with the first as the umbrella, under a pseudo-terminal. The
  user types each confirmation phrase in the dialog's terminal pane. It creates and links **unpublished drafts only**:
  the user reviews each one and presses Publish on Zenodo's website (D-790).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, ClassVar, Final

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from agentprov_gui import text as T
from agentprov_gui import zenodo_run
from agentprov_gui.ui.safe import ReadOnlyText, SafeForm, SafeLabel, ask
from agentprov_gui.ui.settings_panes import CliSettingsPane

__all__ = ["ZenodoDraftsDialog", "ZenodoPane", "creators_of", "release_toml_template"]

TARGET_LABELS: Final = {"sandbox": "Sandbox (sandbox.zenodo.org)", "production": "Production (zenodo.org)"}
_CREATOR: Final = re.compile(r"zenodo\.creators\.([0-9]{1,2})\.(name|orcid|affiliation)")
_OUTPUT_CHARS: Final = 200_000
MAX_CREATORS: Final = 100


def creators_of(values: dict[str, Any]) -> list[dict[str, str]]:
    """The ``zenodo.creators.N.*`` settings as creators in index order (a creator without a name is skipped)."""
    rows: dict[int, dict[str, str]] = {}
    for key, value in values.items():
        m = _CREATOR.fullmatch(key)
        if m and isinstance(value, str) and value:
            rows.setdefault(int(m.group(1)), {})[m.group(2)] = value
    return [rows[i] for i in sorted(rows) if rows[i].get("name")]


def _creator_lines(creators: list[dict[str, str]]) -> str:
    return "\n".join("; ".join([c.get("name", ""), c.get("orcid", ""), c.get("affiliation", "")]).rstrip("; ")
                     for c in creators)


def release_toml_template(values: dict[str, Any]) -> str:
    """A ``release.toml`` (H.10.2) from the Zenodo settings. The title is left empty on purpose, so ``package --deposit``
    refuses the file until the user has written one; strings are JSON-escaped (valid TOML basic strings)."""
    out = ["# release.toml written from Settings > Zenodo (D-880). Fill in the title and the description before",
           "# building the deposit; package --deposit refuses an empty title.", 'title = ""',
           'description_preamble = ""', "keywords = []"]
    concept = values.get("zenodo.concept_doi")
    if isinstance(concept, str) and concept:
        out.append(f"concept_doi = {json.dumps(concept)}")
    for creator in creators_of(values) or [{"name": ""}]:
        out += ["", "[[creators]]", f"name = {json.dumps(creator.get('name', ''))}"]
        out += [f"{k} = {json.dumps(creator[k])}" for k in ("orcid", "affiliation") if creator.get(k)]
    return "\n".join(out) + "\n"


class ZenodoPane(CliSettingsPane):
    """Settings › Zenodo: the ``zenodo.*`` keys (D-880). Creators are one per line, ``Name; ORCID; Affiliation``."""

    PREFIX, TITLE = "zenodo.", "Zenodo settings"
    KEYS: ClassVar[dict[str, str]] = {"target": "zenodo.target_preselect", "communities": "zenodo.communities",
                                      "concept_doi": "zenodo.concept_doi", "creators": "zenodo.creators.*.name"}

    def build(self) -> None:
        form = self.form
        self.target = QComboBox(self)
        self.target.addItems(list(TARGET_LABELS.values()))
        form.add("Target preselected in Create Zenodo drafts (chosen again for every run)", self.target)
        self.communities = QLineEdit(self)
        self.communities.setPlaceholderText("community identifiers, comma-separated")
        form.add("Communities (each one's curators accept or decline a draft)", self.communities)
        self.concept_doi = QLineEdit(self)
        self.concept_doi.setPlaceholderText("10.5281/zenodo.NNNNNNN (empty for a first release)")
        form.add("AgentPROV concept DOI (for a new version)", self.concept_doi)
        self.creators = QPlainTextEdit(self)
        self.creators.setPlaceholderText("Name; ORCID; Affiliation (one creator per line)")
        self.creators.setTabChangesFocus(True)
        form.add("Default creators (prefill release.toml)", self.creators)
        form.add("Token", SafeLabel("Settings › Keys holds ZENODO_SANDBOX_TOKEN and ZENODO_TOKEN in the OS keychain; "
                                    "the GUI never reads them back", name="Zenodo token note", parent=self))

    def show_values(self, values: dict[str, Any]) -> None:
        self.target.setCurrentText(TARGET_LABELS.get(str(values.get("zenodo.target_preselect", "sandbox")),
                                                     TARGET_LABELS["sandbox"]))
        communities = values.get("zenodo.communities")
        self.communities.setText(", ".join(T.line(c, 100) for c in communities) if isinstance(communities, list) else "")
        concept = values.get("zenodo.concept_doi")
        self.concept_doi.setText(T.line(concept, 200) if isinstance(concept, str) else "")
        self.creators.setPlainText(T.multiline(_creator_lines(creators_of(values)), 20_000))

    def values(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        chosen = next((k for k, v in TARGET_LABELS.items() if v == self.target.currentText()), "sandbox")
        if chosen != "sandbox":
            out["zenodo.target_preselect"] = chosen
        slugs = [s for s in self.communities.text().replace(",", " ").split() if s]
        if slugs:
            out["zenodo.communities"] = slugs
        if self.concept_doi.text().strip():
            out["zenodo.concept_doi"] = self.concept_doi.text().strip()
        lines = [ln for ln in self.creators.toPlainText().splitlines() if ln.strip()][:MAX_CREATORS]
        for i, ln in enumerate(lines):
            parts = [p.strip() for p in ln.split(";")]
            for field, value in zip(("name", "orcid", "affiliation"), parts, strict=False):
                if value:
                    out[f"zenodo.creators.{i}.{field}"] = value
        return out


#: D-949: a collection is drafted from the terminal; the dialog is meant for single records
CROSS_LINK_WARNING: Final = (
    "These {n} lines will be drafted and then cross-linked, the first as the umbrella. A whole collection is drafted "
    "from the terminal (the part records first, then the index umbrella from their receipts, then --cross-link; "
    "user guide chapter 5). Use this dialog for single records. Cross-link these {n} drafts anyway?")


class ZenodoDraftsDialog(QDialog):
    """Package › Create Zenodo drafts…: the collection's uploader runs, one after another, in a terminal pane."""

    def __init__(self, cli: Any, checkout: Path | None, parent: QWidget | None = None, *, deposits: str = "",
                 settings: dict[str, Any] | None = None, env: dict[str, str] | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Create Zenodo drafts")
        self.cli, self.checkout = cli, checkout
        self._env = env
        self.run: zenodo_run.PtyRun | None = None
        self.queue: list[zenodo_run.Step] = []
        self.output = ""
        #: asked before a run that cross-links two or more drafts (D-949); tests replace it
        self.confirm_cross_link = self._ask_cross_link
        lay = QVBoxLayout(self)
        lay.addWidget(SafeLabel(
            "Creates and cross-links UNPUBLISHED drafts only. Nothing is published: review each draft on Zenodo's website "
            "and press Publish there yourself. The token comes from Settings › Keys (the OS keychain).",
            name="Zenodo drafts notice", parent=self))
        form = SafeForm()
        self.target = QComboBox(self)
        self.target.addItems(list(TARGET_LABELS.values()))
        form.add("Target", self.target)
        self.communities = QLineEdit(self)
        form.add("Communities (comma-separated)", self.communities)
        self.deposits = QPlainTextEdit(self)
        self.deposits.setTabChangesFocus(True)
        self.deposits.setPlaceholderText("DEPOSIT_DIR sha256:ROOT [sha256:ROOT ...], one per line; the first is the "
                                         "umbrella (one deposit per licence class). An index umbrella (package --index) "
                                         "is named alone, with no root digest")
        self.deposits.setPlainText(deposits)
        form.add("Deposits (first line: the umbrella)", self.deposits)
        lay.addLayout(form)
        settings = settings or {}
        self.target.setCurrentText(TARGET_LABELS.get(str(settings.get("zenodo.target_preselect", "sandbox")),
                                                     TARGET_LABELS["sandbox"]))
        communities = settings.get("zenodo.communities")
        if isinstance(communities, list):
            self.communities.setText(", ".join(T.line(c, 100) for c in communities))
        self.terminal = ReadOnlyText(name="Uploader terminal", parent=self, wrap=True)
        lay.addWidget(self.terminal, 1)
        row = QHBoxLayout()
        self.typed = QLineEdit(self)
        self.typed.setAccessibleName("Typed confirmation phrase")
        self.typed.setPlaceholderText("type the phrase the uploader asks for, then Send")
        self.typed.returnPressed.connect(self.send)
        row.addWidget(self.typed, 1)
        self.send_btn = QPushButton("Send", self)
        self.send_btn.setAccessibleName("Send the typed line to the uploader")
        self.send_btn.clicked.connect(self.send)
        self.start_btn = QPushButton("Start", self)
        self.start_btn.setAccessibleName("Start the Zenodo draft uploader")
        self.start_btn.clicked.connect(self.start)
        self.stop_btn = QPushButton("Stop", self)
        self.stop_btn.setAccessibleName("Stop the Zenodo draft uploader")
        self.stop_btn.clicked.connect(self.stop)
        for b in (self.send_btn, self.start_btn, self.stop_btn):
            row.addWidget(b)
        lay.addLayout(row)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self._pump)
        if not zenodo_run.available():
            self.start_btn.setEnabled(False)
            self._show("A pseudo-terminal is not available on this system (macOS and Linux only): run "
                       "tools/zenodo_draft.py in a terminal instead.\n")
        self._idle()

    # ------------------------------------------------------------------------------------------ state
    def _idle(self) -> None:
        running = self.run is not None
        self.start_btn.setEnabled(not running and zenodo_run.available())
        self.stop_btn.setEnabled(running)
        self.send_btn.setEnabled(running)
        self.typed.setEnabled(running)
        for w in (self.target, self.communities, self.deposits):
            w.setEnabled(not running and not self.queue)

    def _show(self, text: str) -> None:
        self.output = (self.output + T.multiline(text, _OUTPUT_CHARS))[-_OUTPUT_CHARS:]
        self.terminal.set_plain_keep(self.output, follow_end=True)

    def chosen_target(self) -> str:
        return next((k for k, v in TARGET_LABELS.items() if v == self.target.currentText()), "sandbox")

    def argv(self, step: zenodo_run.Step) -> list[str]:
        return [*self.cli.python, "-I", "-m", zenodo_run.MODULE, *step.args]

    # ------------------------------------------------------------------------------------------ actions
    def start(self) -> None:
        if self.run is not None or self.queue:
            return
        try:
            deposits = zenodo_run.parse_deposits(self.deposits.toPlainText())
            communities = zenodo_run.parse_communities(self.communities.text())
            plan = zenodo_run.plan_steps(deposits, self.chosen_target(), communities)
        except ValueError as exc:
            self._show(f"Not started: {exc}\n")
            return
        if not getattr(self.cli, "python", None):
            self._show("Not started: no checkout with a Python environment is configured (Settings › General).\n")
            return
        for note in plan.notes:
            self._show(note + "\n")
        if not plan.steps:
            self._show("Nothing to do.\n")
            return
        host = zenodo_run.TARGETS[self.chosen_target()]
        if len(deposits) >= 2 and not self.confirm_cross_link(CROSS_LINK_WARNING.format(n=len(deposits))):
            self._show("Not started: cross-linking was declined. Draft a collection from the terminal (D-949).\n")
            return
        self._show(f"{len(plan.steps)} uploader run(s) on {host}; each asks for its own typed phrase. Nothing is "
                   "published.\n")
        self.queue = list(plan.steps)
        self._next()

    def _ask_cross_link(self, text: str) -> bool:
        return ask(self, "Cross-link drafts?", text)  # plain text; Cancel is the default

    def _next(self) -> None:
        if not self.queue:
            self._show("\nDone. The drafts are NOT published: review each on Zenodo's website and press Publish there.\n")
            self._idle()
            return
        step = self.queue.pop(0)
        self._show(f"\n=== {step.what}\n")
        from agentprov_gui.jobs.manager import allowlisted_env

        env = allowlisted_env() if self._env is None else dict(self._env)
        try:
            self.run = zenodo_run.PtyRun(self.argv(step), env, cwd=self.checkout)
        except OSError as exc:
            self.queue = []
            self._show(f"The uploader could not start ({type(exc).__name__}).\n")
            self._idle()
            return
        self._idle()
        self.timer.start()
        self.typed.setFocus()

    def _pump(self) -> None:
        run = self.run
        if run is None:
            self.timer.stop()
            return
        chunk = run.read()
        if chunk:
            self._show(chunk)
        code = run.poll()
        if code is None:
            return
        self._show(run.read())
        run.close()
        self.run = None
        self.timer.stop()
        if code != 0:
            self.queue = []
            self._show(f"\nThe uploader ended with exit {code}; the remaining runs were not started.\n")
            self._idle()
            return
        self._next()

    def send(self) -> None:
        if self.run is None:
            return
        self.run.send_line(self.typed.text())
        self.typed.clear()

    def stop(self) -> None:
        self.queue = []
        if self.run is not None:
            self.run.stop()

    def done(self, result: int) -> None:  # closing the dialog stops a run
        self.queue = []
        if self.run is not None:
            self.run.close()
            self.run = None
        self.timer.stop()
        super().done(result)
