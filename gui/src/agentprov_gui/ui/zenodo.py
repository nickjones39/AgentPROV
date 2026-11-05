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
import shlex
from pathlib import Path
from typing import Any, ClassVar, Final

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from agentprov_gui import text as T
from agentprov_gui import zenodo_run
from agentprov_gui.ui.forms import CommandCard, FormSection, SegmentedControl, heading
from agentprov_gui.ui.safe import ReadOnlyText, SafeLabel, ask, set_control_tooltip
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
        form.add("Target preselected in Create Zenodo drafts (chosen again for every run)", self.target,
                 "Which Zenodo Create Zenodo drafts… preselects: the sandbox (sandbox.zenodo.org, for trials) or "
                 "production (zenodo.org). You still choose it for every run, and only drafts are made.")
        self.communities = QLineEdit(self)
        self.communities.setPlaceholderText("community identifiers, comma-separated")
        form.add("Communities (each one's curators accept or decline a draft)", self.communities,
                 "Zenodo community identifiers a draft is offered to, comma separated (zenodo.communities). Each "
                 "community's curators accept or decline it.")
        self.concept_doi = QLineEdit(self)
        self.concept_doi.setPlaceholderText("10.5281/zenodo.NNNNNNN (empty for a first release)")
        form.add("AgentPROV concept DOI (for a new version)", self.concept_doi,
                 "The concept DOI shared by every AgentPROV release, so a new deposit becomes a new version of the "
                 "same record (zenodo.concept_doi). Leave it empty for a first release.")
        self.creators = QPlainTextEdit(self)
        self.creators.setPlaceholderText("Name; ORCID; Affiliation (one creator per line)")
        self.creators.setTabChangesFocus(True)
        form.add("Default creators (prefill release.toml)", self.creators,
                 "The creators written into a new release.toml, one per line as Name; ORCID; Affiliation (ORCID "
                 "and affiliation may be left out).")
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
    """Package › Create Zenodo drafts…: the collection's uploader runs, one after another, in a terminal pane. The
    form style (D-1060): the target, communities and deposits as one section, a command card with the uploader runs
    Start would make (built by :meth:`plan_commands` from the same parse and plan as :meth:`start`, after
    :meth:`program`), the terminal pane and the typed phrase, then Stop bottom left, Close and Start bottom right.
    No button is a default one, so Return in a field never starts the uploader."""

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
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        body = QWidget(self)
        body.setProperty("apvRole", "page")
        lay = QVBoxLayout(body)
        lay.setContentsMargins(24, 20, 24, 16)
        lay.setSpacing(14)
        outer.addWidget(body, 1)
        notice = SafeLabel(
            "Creates and cross-links UNPUBLISHED drafts only. Nothing is published: review each draft on Zenodo's website "
            "and press Publish there yourself. The token comes from Settings › Keys (the OS keychain).",
            name="Zenodo drafts notice", parent=body)
        notice.setWordWrap(True)
        notice.setProperty("apvRole", "secondary")
        lay.addWidget(notice)
        sec = FormSection("Drafts", parent=body)
        settings = settings or {}
        preselect = str(settings.get("zenodo.target_preselect", "sandbox"))
        targets = list(TARGET_LABELS)
        self.target = SegmentedControl([(TARGET_LABELS[key].split(" (", 1)[0], key) for key in targets],
                                       name="Target", parent=sec.card,
                                       current=targets.index(preselect) if preselect in targets else 0)
        for i, key in enumerate(targets):
            self.target.set_tip(i, f"Makes the drafts on {zenodo_run.TARGETS[key]}"
                                   + (", for trials." if key == "sandbox" else "."))
        self.target_row = sec.add_row(
            "Target", self.target,
            tip="Where the drafts are made: the Zenodo sandbox (sandbox.zenodo.org, for trials) or production "
                "(zenodo.org). Settings › Zenodo preselects it; every run passes it as --target.")
        self.target.currentIndexChanged.connect(lambda _i: self._target_changed())
        self.communities = QLineEdit(sec.card)
        self.communities.setPlaceholderText("Not set")
        sec.add_row("Communities", self.communities, caption_text="Community identifiers, comma-separated",
                    tip="Zenodo community identifiers each draft is offered to (--community); each community's curators "
                        "accept or decline it. Prefilled from Settings › Zenodo.")
        self.deposits = QPlainTextEdit(sec.card)
        self.deposits.setAccessibleName("Deposits")
        self.deposits.setTabChangesFocus(True)
        self.deposits.setMinimumHeight(64)
        self.deposits.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.deposits.setPlaceholderText("DEPOSIT_DIR sha256:ROOT [sha256:ROOT ...], one per line; the first is the "
                                         "umbrella (one deposit per licence class). An index umbrella (package --index) "
                                         "is named alone, with no root digest")
        self.deposits.setPlainText(deposits)
        sec.add_row("Deposits", self.deposits, top=True,
                    caption_text="One per line: the folder and its root digests. The first line is the umbrella.",
                    tip="One deposit per line: its directory and the root digest of each corpus in it. The first line "
                        "is the umbrella the others are cross-linked to; an index umbrella (package --index) is named "
                        "alone.")
        lay.addWidget(sec)
        communities = settings.get("zenodo.communities")
        if isinstance(communities, list):
            self.communities.setText(", ".join(T.line(c, 100) for c in communities))
        self._target_changed()
        self.command_card = CommandCard(parent=body, name="Uploader commands", title="Terminal commands",
                                        program=shlex.join(self.program()))
        lay.addWidget(self.command_card)
        lay.addWidget(heading("Uploader terminal", parent=body))
        self.terminal = ReadOnlyText(name="Uploader terminal", parent=body, wrap=True)
        set_control_tooltip(self.terminal, "The uploader's output: its notes and the consent screen of each run, which "
                                           "names the phrase to type below.")
        self.terminal.setMinimumHeight(100)
        lay.addWidget(self.terminal, 1)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.typed = QLineEdit(body)
        self.typed.setAccessibleName("Typed confirmation phrase")
        self.typed.setPlaceholderText("type the phrase the uploader asks for, then Send")
        self.typed.returnPressed.connect(self.send)
        set_control_tooltip(self.typed, "Type the confirmation phrase the running uploader asks for, then press "
                                        "Send or Return.")
        row.addWidget(self.typed, 1)
        self.send_btn = QPushButton("Send", body)
        self.send_btn.setAccessibleName("Send the typed line to the uploader")
        self.send_btn.clicked.connect(self.send)
        set_control_tooltip(self.send_btn, "Sends the typed line to the running uploader, as if typed in a terminal.")
        row.addWidget(self.send_btn)
        lay.addLayout(row)
        footer = QWidget(self)
        footer.setProperty("apvRole", "footer")
        foot = QHBoxLayout(footer)
        foot.setContentsMargins(20, 12, 20, 12)
        foot.setSpacing(10)
        self.stop_btn = QPushButton("Stop", footer)
        self.stop_btn.setAccessibleName("Stop the Zenodo draft uploader")
        self.stop_btn.clicked.connect(self.stop)
        set_control_tooltip(self.stop_btn, "Stops the current uploader run; the remaining runs are not started.")
        foot.addWidget(self.stop_btn)
        foot.addStretch(1)
        close = QPushButton("Close", footer)
        close.setAccessibleName("Close")
        close.clicked.connect(self.reject)
        set_control_tooltip(close, "Closes the dialog; a running uploader is stopped. Nothing is published.")
        foot.addWidget(close)
        self.start_btn = QPushButton("Start", footer)
        self.start_btn.setAccessibleName("Start the Zenodo draft uploader")
        self.start_btn.setProperty("apvRole", "primary")
        self.start_btn.clicked.connect(self.start)
        set_control_tooltip(self.start_btn, "Runs the draft-only uploader: it creates or resumes a draft for each "
                                            "deposit without a complete receipt, then cross-links them when there are "
                                            "two or more. Each run asks for its own typed phrase; nothing is "
                                            "published.")
        foot.addWidget(self.start_btn)
        outer.addWidget(footer)
        for button in self.findChildren(QPushButton):  # Return never starts the uploader: only a click on Start does
            button.setAutoDefault(False)
            button.setDefault(False)
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self._pump)
        self._plan_timer = QTimer(self)  # the command card follows the fields a moment after the last keystroke
        self._plan_timer.setSingleShot(True)
        self._plan_timer.setInterval(250)
        self._plan_timer.timeout.connect(self._update_commands)
        self.deposits.textChanged.connect(self._plan_timer.start)
        self.communities.textChanged.connect(lambda _t: self._plan_timer.start())
        self.target.currentIndexChanged.connect(lambda _i: self._plan_timer.start())
        if not zenodo_run.available():
            self.start_btn.setEnabled(False)
            self._show("A pseudo-terminal is not available on this system (macOS and Linux only): run "
                       "tools/zenodo_draft.py in a terminal instead.\n")
        self._idle()
        self._update_commands()

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
        data = self.target.currentData()
        return data if isinstance(data, str) and data in zenodo_run.TARGETS else "sandbox"

    def program(self) -> list[str]:
        """The uploader as the checkout's interpreter runs it: ``python -I -m agentprov_zenodo``."""
        return [*(getattr(self.cli, "python", None) or ("python",)), "-I", "-m", zenodo_run.MODULE]

    def argv(self, step: zenodo_run.Step) -> list[str]:
        return [*self.program(), *step.args]

    def _target_changed(self) -> None:
        target = self.chosen_target()
        host = zenodo_run.TARGETS[target]
        self.target_row.set_caption(f"{host}, for trials" if target == "sandbox" else
                                    f"{host}: a draft becomes a public record once you publish it there")

    def plan_commands(self) -> tuple[list[tuple[str, tuple[str, ...]]], str]:
        """The uploader runs Start would make for the fields as they are (the same parse and plan as :meth:`start`),
        as the command card's ``(comment, arguments)`` pairs after :meth:`program`, or a note saying why there are
        none. No token is ever among them: every run passes ``--keychain``."""
        try:
            deposits = zenodo_run.parse_deposits(self.deposits.toPlainText())
            communities = zenodo_run.parse_communities(self.communities.text())
            plan = zenodo_run.plan_steps(deposits, self.chosen_target(), communities)
        except ValueError as exc:
            return [], f"The uploader's commands appear once the fields are valid: {exc}"
        if not getattr(self.cli, "python", None):
            return [], "No checkout with a Python environment is configured (Settings › General)."
        if not deposits:
            return [], "List a deposit to see the uploader's commands."
        if not plan.steps:
            return [], "Nothing to do: " + "; ".join(plan.notes)
        return [(step.what, step.args) for step in plan.steps], ""

    def _update_commands(self) -> None:
        commands, note = self.plan_commands()
        self.command_card.set_commands(commands, note=note)

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
