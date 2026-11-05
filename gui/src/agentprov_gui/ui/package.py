"""Package (design §6.7; wireframe 06; macos-design §3.3 "Package"; the form style of D-1060).

A guided flow that calls only ``agentprov package`` and ``agentprov verify`` (as jobs) and never re-implements them:

1. **Corpus:** a working corpus; the preconditions the GUI can see (``partial: false``, no lock, no
   ``interpreter_advisory``, release mode, the checkout's git state), then ``package --dry-run`` and its refusal.
2. **Withholding:** counts by reason and basis from ``WITHHELD.json`` of the sealed corpus. The withheld **values**
   never appear; the ``DIR.withheld/`` sidecar is never opened.
3. **Counts and licences:** from the manifest.
4. **Datasheet:** ``DATASHEET.md`` as plain text (not rendered Markdown, so no autolinks).
5. **Seal:** ``package --corpus DIR --corpus-version X.Y.Z [--spec] [--licence-file] [--release-date]`` (R1).
6. **Verify:** ``verify --corpus DIR --level chain --release --root-digest <from the seal's output>``.
7. **Release scan:** whether ``<corpus>.release-scan.json`` exists (running the scan stays a terminal step).
8. **Deposit:** ``package --deposit OUT --corpus DIR --metadata release.toml`` then ``verify`` of the ``.meta.zip``.
9. **Finish:** "Nothing has been uploaded." Two actions (D-880): **Write release.toml from the Zenodo settings…** (a
   template, never over an existing file) and **Create Zenodo drafts…**, which runs the draft-only uploader
   (``agentprov_zenodo``, not an ``agentprov`` command) under a pseudo-terminal where the user types each confirmation
   phrase (:class:`agentprov_gui.ui.zenodo.ZenodoDraftsDialog`). It makes unpublished drafts only; Publish stays the
   user's, on Zenodo's website.

**Layout (D-1060):** the steps are a stepper on the left (number, name, what the step is for and its state: done ✓,
running ◐, needs attention !, failed ×, not reached; the current one highlighted), each with its tooltip. Each step's
page shows only the fields that step uses (the working corpus and version in step 1; the spec, licence file and release
date in step 5; the deposit folder and release.toml in step 8), its results as a checklist with the raw text behind a
Details disclosure, and a terminal command card built from the same :func:`build_spec` call the step's action runs.
The step's action sits bottom left, Back and Continue bottom right.

Every job is started through the Runs page, so it has a job directory, a dashboard and a log. The 1 s timer refreshes
only the job status of the job-driven steps (1, 5, 6, 8); the corpus steps, the preconditions of step 1 and the
conformance mark of step 5 are read when the step, the corpus or the deposit field, the checkout or a finished job
changes (GR-23, GR-54).
"""

from __future__ import annotations

import os
import re
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from agentprov.corpus.reader import CorpusReader
from agentprov.errors import AgentProvError
from agentprov.ingest.loaders import strict_json_loads
from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QRect, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from agentprov_gui import text as T
from agentprov_gui.about import git_commit
from agentprov_gui.jobs.commands import FORMS, FormError, JobSpec, build_spec
from agentprov_gui.jobs.manager import Job, read_json, tail_bytes
from agentprov_gui.readmodel.corpus import summarise
from agentprov_gui.ui import theme
from agentprov_gui.ui.forms import (
    CommandCard,
    Disclosure,
    FormPage,
    FormSection,
    PathField,
    StatusBadge,
    caption,
    heading,
)
from agentprov_gui.ui.safe import (
    ReadOnlyText,
    SafeLabel,
    set_control_tooltip,
    set_help_tooltip,
    set_list_item_tooltip,
)

__all__ = ["FINISH_TEXT", "Check", "PackagePage", "release_scan_argv", "root_digest_of"]

STEPS: Final = ("1 Corpus", "2 Withholding", "3 Counts and licences", "4 Datasheet", "5 Seal", "6 Verify",
                "7 Release scan", "8 Deposit", "9 Finish")
#: each step's name, and what it is for (the grey line under it in the step list)
STEP_NAMES: Final = tuple(step.split(" ", 1)[1] for step in STEPS)
STEP_NOTES: Final = ("Check it can be packaged", "What sealing withheld", "Review totals and terms",
                     "Preview DATASHEET.md", "Write the sealed corpus", "Check the digest chain",
                     "Look for secrets and paths", "Build the upload folder", "Zenodo drafts and next steps")
FINISH_TEXT: Final = (
    "Nothing has been uploaded. Once step 8 has built and verified the deposit, uploading to Zenodo is a manual step, "
    "done only on "
    "the project owner's explicit instruction: Create Zenodo drafts… makes unpublished drafts (one per licence class, "
    "cross-linked to the first as the umbrella), and publishing stays yours, on Zenodo's website.\n\nFiles to upload "
    "(from DEPOSIT-MANIFEST.json):\n"
)
#: the line under each step's title
STEP_INTROS: Final = (
    "Choose the working corpus and check that it can be packaged. Nothing is written in this step.",
    "What sealing withheld, from the sealed corpus's WITHHELD.json. The withheld values never appear. Runs nothing.",
    "The counts and licences recorded in the corpus's manifest (corpus.json). Runs nothing.",
    "The datasheet the seal generates, shown as plain text. Runs nothing.",
    "Seal the working corpus into a corpus version. Seal… shows the command for you to confirm first.",
    "Check the sealed corpus's digest chain in release mode, with the root digest the seal printed.",
    "The release scan looks for secrets, home paths and account paths. It runs from a terminal; the deposit build "
    "refuses a corpus without one.",
    "Build the deposit draft from the sealed corpus and release.toml, then verify it. Nothing is uploaded.",
    FINISH_TEXT.split("\n\n", 1)[0],
)
MARKED_TEXT: Final = (
    "Sealing is disabled: this corpus skipped the W3C PROV conformance check (validation.prov_conformance = skipped). "
    "Revalidate it with a full recompute into a new corpus (recompute --out NEW --stages sem,prov,validation), then seal "
    "the new corpus; package would refuse this one (package.refused.prov_conformance). validate --corpus does not clear "
    "the mark."
)
_ROOT: Final = re.compile(r"root digest (sha256:[0-9a-f]{64})")
#: the steps whose text follows a job; the timer refreshes only these (GR-23)
_JOB_STEPS: Final = frozenset({0, 4, 5, 7})
#: DATASHEET.md is shown up to this many characters, read as at most four bytes each (GR-23)
_DATASHEET_CHARS: Final = 200_000
#: the release scan is a repository tool run in the checkout from a terminal (G.9.4), not an agentprov command
RELEASE_SCAN_PROGRAM: Final = "uv run python"
RELEASE_SCAN_TOOL: Final = "tools/release_scan.py"
#: what each step shows or runs and what it needs (its item's tooltip in the step list)
STEP_TIPS: Final = (
    "Checks the working corpus before sealing: the preconditions this page can see (partial false, release status, "
    "strict validation mode, no interpreter advisory, no writer's lock, the checkout's commit). Check and Dry Run then "
    "runs package --dry-run as a job, which checks everything the seal would and writes nothing. Needs the working "
    "corpus and the corpus version (this step's fields).",
    "Shows what sealing withheld, from the sealed corpus's WITHHELD.json: the entries, the executions affected or "
    "withheld whole, and counts by reason, basis and [withhold] rule. The withheld values never appear and the "
    "DIR.withheld sidecar is never opened. Runs nothing; needs a sealed corpus (step 5).",
    "Shows the counts and the licences recorded in the corpus's manifest (corpus.json), as JSON. Runs nothing; needs "
    "a working or sealed corpus.",
    "Shows DATASHEET.md, the datasheet the seal generates, as plain text (not rendered Markdown). Runs nothing; needs "
    "a sealed corpus (step 5).",
    "Seals the working corpus into a corpus version with package (Seal…), after you confirm the command. Needs the "
    "corpus version, a clean checkout and a corpus spec; takes this step's spec, licence file and release date when "
    "given. A corpus that skipped the PROV conformance check cannot be sealed: the button then opens a full "
    "recompute into a new corpus.",
    "Runs verify --corpus DIR --level chain --release as a job (Verify (chain, release)), with the root digest that "
    "step 5's seal printed on this page in this session, when there is one. Needs a sealed corpus.",
    "Shows whether the release scan (<corpus>.release-scan.json) and its untriaged file exist beside the corpus. The "
    "scan is a repository tool run from a terminal (tools/release_scan.py on the sealed corpus, then triage every "
    "finding); the deposit build of step 8 refuses a corpus without one. Runs nothing.",
    "Builds a deposit draft in the deposit output directory with package --deposit (Build Deposit…), after you "
    "confirm the command, then verifies its .meta.zip. Needs the sealed corpus, the release scan (step 7), a "
    "release.toml with a title and the release date. Nothing is uploaded.",
    "Lists the archives to upload, from DEPOSIT-MANIFEST.json in the deposit output directory; nothing has been "
    "uploaded. Write release.toml from the Zenodo settings… writes a metadata template; Create Zenodo drafts… makes "
    "unpublished drafts with the draft-only uploader, and you publish on Zenodo's website.",
)
_ACTION_TIPS: Final = {
    0: "Runs package --dry-run on the working corpus as a job, after you confirm the command: it checks everything the "
       "seal would and writes nothing.",
    4: "Seals the working corpus into a corpus version (package --corpus DIR --corpus-version X.Y.Z with the spec, "
       "licence file and release date of step 5), after you confirm the command. For a corpus that skipped the PROV "
       "conformance check it opens a full recompute into a new corpus instead.",
    5: "Runs verify --corpus DIR --level chain --release as a job, with the root digest the seal printed on this page "
       "in this session.",
    7: "Builds a deposit draft in the deposit output directory from the sealed corpus and release.toml (package "
       "--deposit), after you confirm the command, then verifies its .meta.zip. Nothing is uploaded.",
}


def root_digest_of(job: Job) -> str | None:
    """The root digest the seal printed (on stderr with the job's options; stdout is checked too). The summary document
    does not carry it."""
    for name in ("stderr.txt", "stdout.txt"):
        m = _ROOT.search(tail_bytes(job.file(name)).decode("utf-8", "replace"))
        if m:
            return m.group(1)
    return None


def _flag(value: object) -> str:
    """A corpus.json flag as checked text: a boolean, ``absent``, or the escaped value marked as not a boolean (S3)."""
    if isinstance(value, bool):
        return str(value).lower()
    return "absent" if value is None else f"not a boolean ({T.line(value, 60)})"


_RELEASE_STATUS = {"dev": "dev (not released)", "release-candidate": "release candidate", "sealed": "sealed"}


def _release_status(release: object) -> str:
    """corpus.json's ``release`` object (``status``, ``created``; HL H.2), as checked text (F-13: it is not a flag)."""
    if release is None:
        return "absent"
    status = release.get("status") if isinstance(release, dict) else None
    if not isinstance(status, str) or status not in _RELEASE_STATUS:
        return f"not a release record ({T.line(release, 60)})"
    created = release.get("created") if isinstance(release, dict) else None
    return _RELEASE_STATUS[status] + (f", created {T.line(created, 40)}" if isinstance(created, str) else "")


def _validation_mode(reader: CorpusReader) -> str:
    """The validation stage's mode in derivation.json: ``package`` needs ``release`` (strict validation)."""
    try:
        derivation = reader.derivation()
    except AgentProvError as exc:
        return f"derivation.json cannot be read ({T.line(exc.code, 60)}; not satisfied)"
    stages = derivation.get("stages") if isinstance(derivation, dict) else None
    stage = next((st for st in stages if isinstance(st, dict) and st.get("stage") == "validation"), None) \
        if isinstance(stages, list) else None
    mode = stage.get("mode") if stage is not None else None
    if stage is None:
        return "no validation stage recorded (package needs strict validation; not satisfied)"
    if mode == "release":
        return "release (strict, as package needs)"
    if mode == "dev":
        return "dev (package needs strict validation; not satisfied)"
    return f"not dev or release ({T.line(mode, 60)}; not satisfied)"


def _set_text(pane: ReadOnlyText, value: str) -> None:
    """Replace the pane's text only when it changed, so a refresh keeps the scroll position and the selection (GR-23)."""
    if value != pane.toPlainText():
        pane.setPlainText(value)



def release_scan_argv(corpus: Path) -> tuple[str, ...]:
    """The release scan's arguments (after ``uv run python``, in the checkout) for a sealed corpus: the tool writes
    ``<corpus>.release-scan.json`` beside it, which step 7 looks for."""
    return (RELEASE_SCAN_TOOL, str(corpus))


# --------------------------------------------------------------------------------------------- the checklist
@dataclass(frozen=True, slots=True)
class Check:
    """One row of a step's checklist: its kind (a key of :data:`CHECK_KINDS`; empty for a plain row), what it says and
    an optional grey detail."""

    kind: str
    text: str
    detail: str = ""


#: a check's kind -> (its badge's tint, its glyph, the word read out): the glyph and the words carry the state, the
#: tint only repeats it
CHECK_KINDS: Final = {
    "ok": ("ok", "✓", "passed"), "warn": ("warn", "!", "needs attention"), "bad": ("bad", "×", "failed"),
    "running": ("info", "◐", "running"), "note": ("neutral", "i", "note"), "todo": ("neutral", "–", "not yet"),
}  # fmt: skip
#: a check badge's tooltip: what the state means and what to do
CHECK_TIPS: Final = {
    "ok": "Passed: nothing to do.",
    "warn": "Needs attention: the text beside it says what to look at before going on.",
    "bad": "Failed: the text beside it says what failed; fix it, then check again.",
    "running": "Running: the job behind this check has not ended yet (Runs follows it).",
    "note": "A note: information only, nothing to do.",
    "todo": "Not yet: this has not been checked or done yet.",
}
#: a step's state in the step list -> (its glyph, or "" for its number, the word read out)
STEP_STATES: Final = {"todo": ("", "not reached"), "running": ("◐", "running"), "done": ("✓", "done"),
                      "warn": ("!", "needs attention"), "failed": ("×", "failed")}


class _CheckRow(QWidget):
    """A checklist row: the status glyph as a badge, the text and the grey detail under it."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAccessibleName("Check")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 1, 0, 1)
        lay.setSpacing(10)
        self.badge = StatusBadge("", name="Check status", parent=self)
        self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.badge.setFixedWidth(26)
        lay.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(2)
        self.text = SafeLabel("", name="Check text", parent=self)
        self.text.setWordWrap(True)
        self.text.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.text.setMinimumWidth(0)
        col.addWidget(self.text)
        self.detail = caption("", name="Check detail", parent=self)
        self.detail.setVisible(False)
        col.addWidget(self.detail)
        lay.addLayout(col, 1)

    def set_check(self, check: Check) -> None:
        tint, glyph, word = CHECK_KINDS.get(check.kind, ("neutral", "", ""))
        self.badge.set_status(glyph, tint)
        self.badge.setAccessibleName(word or "Check status")
        set_help_tooltip(self.badge, CHECK_TIPS.get(check.kind, "A note of this step."))
        self.text.set_plain(check.text)
        self.detail.set_plain(check.detail)
        self.detail.setVisible(bool(check.detail))
        self.setAccessibleName(f"{word}: {check.text}" if word else check.text)


class _Checks(FormSection):
    """A section whose rows are a step's checks. :meth:`set_checks` shows exactly the given ones (the rows are reused,
    and nothing changes when the checks did not)."""

    def __init__(self, title: str, *, parent: QWidget, note: str = "") -> None:
        super().__init__(title, parent=parent, note=note)
        self.check_rows: list[_CheckRow] = []
        self.shown: tuple[Check, ...] | None = None

    def set_checks(self, checks: Sequence[Check]) -> None:
        wanted = tuple(checks)
        if wanted == self.shown:
            return
        self.shown = wanted
        while len(self.check_rows) < len(wanted):
            row = _CheckRow(self.card)
            self.add(row)
            self.check_rows.append(row)
        for i, row in enumerate(self.check_rows):
            if i < len(wanted):
                row.set_check(wanted[i])
            row.setVisible(i < len(wanted))

    def texts(self) -> list[str]:
        """The shown checks as ``kind: text`` lines (tests, screenshots)."""
        return [f"{c.kind}: {c.text}" for c in self.shown or ()]


# --------------------------------------------------------------------------------------------- the step list
class _StepDelegate(QStyledItemDelegate):
    """Draws a step of the list as the style guide's stepper: a circle with the step's number (✓ done, × failed,
    ! needs attention, ◐ running; the current step's filled with the accent), the step's name and what it is for, in
    plain text. The item keeps its tooltip and its accessible text (the name and the state in words)."""

    HEIGHT: Final = 46

    def __init__(self, page: PackagePage) -> None:
        super().__init__(page.steps)
        self.page = page

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> QSize:
        return QSize(max(0, option.rect.width()), self.HEIGHT)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem,
              index: QModelIndex | QPersistentModelIndex) -> None:
        t = theme.tokens()
        row = index.row()
        state = self.page.states[row] if 0 <= row < len(self.page.states) else "todo"
        current = bool(option.state & QStyle.StateFlag.State_Selected)
        rect: QRect = option.rect
        font: QFont = option.font
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        box = rect.adjusted(4, 2, -4, -2)
        if current:
            focused = bool(option.state & QStyle.StateFlag.State_HasFocus)
            painter.setPen(QColor(t.accent) if focused else Qt.PenStyle.NoPen)
            painter.setBrush(QColor(t.accent_soft))
            painter.drawRoundedRect(box, 8, 8)
        size = 22
        circle = QRect(box.left() + 8, box.center().y() - size // 2, size, size)
        fill = {"done": theme.status_colour("ok"), "failed": theme.status_colour("failed"),
                "warn": theme.status_colour("ok_with_issues")}.get(state)
        if fill is None and current:
            fill = QColor(t.accent)
        if fill is not None:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(fill)
            glyph_colour = QColor(t.accent_text)
        else:
            outline = t.accent if state == "running" else t.field_border
            painter.setPen(QColor(outline))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            glyph_colour = QColor(t.accent if state == "running" else t.caption)
        painter.drawEllipse(circle.adjusted(0, 0, -1, -1))
        number = theme.scaled_font("caption", font)
        number.setWeight(QFont.Weight.DemiBold)
        painter.setFont(number)
        painter.setPen(glyph_colour)
        painter.drawText(circle, int(Qt.AlignmentFlag.AlignCenter), STEP_STATES[state][0] or str(row + 1))
        left = circle.right() + 10
        width = max(0, box.right() - 8 - left)
        title = QFont(font)
        if current:
            title.setWeight(QFont.Weight.DemiBold)
        note = theme.scaled_font("caption", font)
        tm, nm = QFontMetrics(title), QFontMetrics(note)
        top = box.center().y() - (tm.height() + nm.height() + 1) // 2
        align = int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        painter.setFont(title)
        painter.setPen(QColor(t.text))
        name = STEP_NAMES[row] if 0 <= row < len(STEP_NAMES) else ""
        painter.drawText(QRect(left, top, width, tm.height()), align,
                         tm.elidedText(name, Qt.TextElideMode.ElideRight, width))
        painter.setFont(note)
        painter.setPen(QColor(t.secondary if current else t.caption))
        what = STEP_NOTES[row] if 0 <= row < len(STEP_NOTES) else ""
        painter.drawText(QRect(left, top + tm.height() + 1, width, nm.height()), align,
                         nm.elidedText(what, Qt.TextElideMode.ElideRight, width))
        painter.restore()


# --------------------------------------------------------------------------------------------- the page
class PackagePage(QWidget):
    def __init__(self, start_job: Callable[[JobSpec], Job | None], checkout: Path | None,
                 parent: QWidget | None = None, revalidate: Callable[[str], None] | None = None) -> None:
        super().__init__(parent)
        self.revalidate = revalidate
        self.setAccessibleName("Package")
        self.start_job = start_job
        self._checkout = checkout
        self.jobs: dict[str, Job] = {}
        #: the static parts of steps 1 and 5, read once per change, not per tick (GR-54)
        self._pre: tuple[str, list[Check]] | None = None
        self._marked: bool | None = None
        #: what the step list's states need from the corpus and the deposit folder, read with the parts above
        self._static: dict[str, bool] | None = None
        self._finished: frozenset[str] = frozenset()
        #: each step's state in the step list (STEP_STATES)
        self.states: list[str] = ["todo"] * len(STEPS)
        self.texts: list[ReadOnlyText] = []
        self.notes: list[SafeLabel] = []
        self.checks: dict[int, _Checks] = {}
        self.cards: dict[int, CommandCard] = {}
        self.buttons: list[QPushButton | None] = [None] * len(STEPS)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._build_steps())
        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        lay.addLayout(right, 1)
        self.pages = QStackedWidget(self)
        self.pages.setAccessibleName("Package step")
        for i in range(len(STEPS)):
            self.pages.addWidget(self._build_step(i))
        right.addWidget(self.pages, 1)
        right.addWidget(self._build_footer())
        for edit in (self.version, self.spec, self.licence, self.release_date, self.deposit, self.metadata, self.corpus):
            edit.textChanged.connect(lambda _t: self._fields_changed())
        self.steps.currentRowChanged.connect(self._step_changed)
        self.corpus.editingFinished.connect(lambda: self._show(self.steps.currentRow()))
        self.deposit.editingFinished.connect(lambda: self._show(self.steps.currentRow()))
        for field in (self.corpus_field, self.deposit_field):  # after Choose… has filled the field
            field.button.clicked.connect(lambda: self._show(self.steps.currentRow()))
        self.steps.setCurrentRow(0)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000)

    # ------------------------------------------------------------------------------------------ widgets
    def _build_steps(self) -> QWidget:
        side = QWidget(self)
        side.setProperty("apvRole", "summary")
        side.setFixedWidth(240)
        col = QVBoxLayout(side)
        col.setContentsMargins(12, 20, 12, 14)
        col.setSpacing(6)
        title = heading("Package a corpus", parent=side)
        title.setContentsMargins(8, 0, 0, 2)
        col.addWidget(title)
        self.steps = QListWidget(side)
        self.steps.setAccessibleName("Package steps")
        self.steps.setProperty("apvRole", "stepper")
        self.steps.setFrameShape(QFrame.Shape.NoFrame)
        self.steps.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.steps.setUniformItemSizes(True)
        self.steps.setItemDelegate(_StepDelegate(self))
        self.steps.addItems(list(STEPS))
        for row, tip in enumerate(STEP_TIPS):
            item = self.steps.item(row)
            set_list_item_tooltip(item, tip, wrap=True)
            item.setData(Qt.ItemDataRole.AccessibleTextRole, f"{STEPS[row]}: {STEP_STATES['todo'][1]}")
            item.setData(Qt.ItemDataRole.AccessibleDescriptionRole, STEP_NOTES[row])
        set_control_tooltip(self.steps, "The nine steps from a working corpus to a deposit draft; choose one to show "
                                        "it.")
        col.addWidget(self.steps, 1)
        col.addWidget(caption("Each step shows a tooltip with what it runs and what it needs.", name="Step list note",
                              parent=side))
        return side

    def _build_step(self, i: int) -> QWidget:
        page = FormPage(name=f"Step {STEPS[i]}", parent=self.pages)
        column = page.column
        head = QWidget(column)
        hl = QVBoxLayout(head)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(4)
        title = SafeLabel(f"{i + 1} · {STEP_NAMES[i]}", name=f"Step {STEPS[i]}", parent=head, selectable=False)
        title.setFont(theme.scaled_font("title"))
        hl.addWidget(title)
        intro = caption(STEP_INTROS[i], name=f"{STEPS[i]}: what it does", parent=head, role="secondary")
        intro.setFont(theme.scaled_font("body"))
        hl.addWidget(intro)
        page.add(head)
        note = caption("", name=f"{STEPS[i]}: message", parent=column, role="secondary")
        note.setVisible(False)
        page.add(note)
        self.notes.append(note)
        text = ReadOnlyText(name=f"{STEPS[i]} details", parent=column, wrap=True)
        self.texts.append(text)
        if i == 0:
            self._build_corpus(page)
        elif i == 4:
            self._build_seal(page)
        elif i == 7:
            self._build_deposit(page)
        if i in (2, 3):  # the step's content is the text itself: shown in its own card, scrolling inside it
            sec = FormSection("Counts and licences (corpus.json)" if i == 2 else "DATASHEET.md", parent=column)
            text.setFrameShape(QFrame.Shape.NoFrame)
            text.setMinimumHeight(280)
            sec.add(text)
            page.add(sec)
            page.layout_.setStretchFactor(sec, 1)
            page.layout_.setStretch(page.layout_.count() - 1, 0)
            return page
        titles = {1: "What was withheld", 6: "Release scan", 8: "Files to upload"}
        notes = {8: "From DEPOSIT-MANIFEST.json in step 8's deposit folder."}
        checks = _Checks(titles.get(i, "Checks"), parent=column, note=notes.get(i, ""))
        page.add(checks)
        self.checks[i] = checks
        if i == 8:
            self._build_finish(page)
        if i in (0, 4, 5, 6, 7):
            program = RELEASE_SCAN_PROGRAM if i == 6 else "agentprov"
            card = CommandCard(parent=column, program=program)
            page.add(card)
            self.cards[i] = card
        details = Disclosure("Details: the step's output as text", screen="package", key=f"details-{i}",
                             name="Show the step's output as text", parent=column)
        set_control_tooltip(details.button, "Shows or hides the step's checks and job status as plain text: the job, "
                                            "its exit code, a refusal and the counters of its summary.")
        text.setMinimumHeight(160)
        details.add(text)
        page.add(details)
        return page

    def _build_corpus(self, page: FormPage) -> None:
        sec = FormSection("Corpus", parent=page.column,
                          note="The corpus spec, licence file and release date appear in step 5, the deposit folder "
                               "and release.toml in step 8. The dry run takes step 5's fields too.")
        self.corpus_field = PathField(name="Working corpus", choose_name="Choose the working corpus folder",
                                      folder=True, parent=sec.card, placeholder="Not set")
        self.corpus = self.corpus_field.edit
        sec.add_row("Working corpus", self.corpus_field, caption_text="A folder, or one ending .partial",
                    subject=self.corpus,
                    tip="The corpus folder every step reads and acts on, with or without its .partial suffix "
                        "(--corpus).")
        self.version = QLineEdit("0.1.0", sec.card)
        self.version.setAccessibleName("Corpus version")
        self.version.setFixedWidth(130)
        sec.add_row("Version", self.version, stretch=False, caption_text="The corpus spec's version, X.Y.Z",
                    tip="The version the seal gives the corpus, as X.Y.Z: the version of the corpus spec "
                        "(--corpus-version).")
        page.add(sec)

    def _build_seal(self, page: FormPage) -> None:
        sec = FormSection("Seal with", parent=page.column,
                          note="The working corpus and its version are step 1's. Step 1's dry run takes these fields "
                               "too; Build Deposit… in step 8 takes the release date.")
        self.spec_field = PathField(name="Corpus spec", choose_name="Choose the corpus spec file", parent=sec.card,
                                    placeholder="Default (the checkout's corpora/<name>/corpus-spec.toml)")
        self.spec = self.spec_field.edit
        sec.add_row("Corpus spec", self.spec_field, caption_text="With CARD.md and CHANGES.toml beside it",
                    subject=self.spec,
                    tip="The corpus-spec.toml to seal with, with CARD.md and CHANGES.toml beside it (--spec). Leave it "
                        "empty for the checkout's corpora/<name>/corpus-spec.toml, <name> being the corpus folder's "
                        "name.")
        self.licence = QLineEdit(sec.card)
        self.licence.setAccessibleName("Licence file")
        self.licence.setPlaceholderText("Not set")
        sec.add_row("Upstream licence", self.licence, caption_text="Its name, =, then the file: NAME=PATH",
                    tip="An upstream licence file the spec names that the corpus does not store, as NAME=PATH "
                        "(--licence-file).")
        self.release_date = QLineEdit(sec.card)
        self.release_date.setAccessibleName("Release date")
        self.release_date.setPlaceholderText("Not set")
        self.release_date.setFixedWidth(130)
        sec.add_row("Release date", self.release_date, stretch=False, caption_text="YYYY-MM-DD",
                    tip="The seal records it as the release date (if empty: SOURCE_DATE_EPOCH, else none); Build "
                        "Deposit… needs it for the archive timestamps (--release-date).")
        page.add(sec)

    def _build_deposit(self, page: FormPage) -> None:
        self.deposit_section = FormSection("Deposit", parent=page.column)
        sec = self.deposit_section
        self.deposit_field = PathField(name="Deposit output directory", choose_name="Choose the deposit folder",
                                       folder=True, parent=sec.card, placeholder="Not set")
        self.deposit = self.deposit_field.edit
        sec.add_row("Deposit folder", self.deposit_field, caption_text="Where the deposit draft is written",
                    subject=self.deposit,
                    tip="Where Build Deposit… writes the deposit draft (package --deposit OUT); Finish lists its "
                        "archives.")
        self.metadata_field = PathField(name="release.toml", choose_name="Choose the release.toml file",
                                        parent=sec.card, placeholder="Not set")
        self.metadata = self.metadata_field.edit
        sec.add_row("Release metadata", self.metadata_field, caption_text="release.toml: title, creators, DOIs",
                    subject=self.metadata,
                    tip="The deposit's metadata file: title, creators, keywords, description preamble and DOIs "
                        "(--metadata). Write release.toml from the Zenodo settings… (step 9) writes a template here.")
        page.add(sec)

    def _build_finish(self, page: FormPage) -> None:
        sec = FormSection("Zenodo", parent=page.column,
                          note="Uses the deposit folder and release.toml of step 8. Nothing is uploaded from this page.")
        self.release_toml_btn = QPushButton("Write release.toml from the Zenodo settings…", sec.card)
        self.release_toml_btn.setAccessibleName("Write release.toml from the Zenodo settings…")
        self.release_toml_btn.clicked.connect(self.write_release_toml)
        set_control_tooltip(self.release_toml_btn,
                            "Writes a release.toml template to step 8's release.toml path from Settings › Zenodo (the "
                            "creators and the concept DOI). It never overwrites a file; fill in the title, description "
                            "and keywords.")
        sec.add_row("Release metadata", self.release_toml_btn, stretch=False,
                    caption_text="A template from Settings › Zenodo, never over a file")
        self.zenodo_btn = QPushButton("Create Zenodo drafts…", sec.card)
        self.zenodo_btn.setAccessibleName("Create Zenodo drafts…")
        self.zenodo_btn.clicked.connect(self.create_zenodo_drafts)
        set_control_tooltip(self.zenodo_btn,
                            "Opens the dialog that runs the draft-only Zenodo uploader for the deposits you list. It "
                            "makes unpublished drafts only; you publish each one on Zenodo's website.")
        sec.add_row("Zenodo drafts", self.zenodo_btn, stretch=False,
                    caption_text="Unpublished drafts only; you publish on Zenodo's website")
        page.add(sec)

    def _build_footer(self) -> QWidget:
        footer = QWidget(self)
        footer.setProperty("apvRole", "footer")
        row = QHBoxLayout(footer)
        row.setContentsMargins(20, 12, 20, 12)
        row.setSpacing(10)
        actions: dict[int, tuple[str, Callable[[], None]]] = {
            0: ("Check and Dry Run", self.dry_run), 4: ("Seal…", self.seal), 5: ("Verify (chain, release)", self.verify),
            7: ("Build Deposit…", self.build_deposit),
        }
        for i, (label, slot) in actions.items():
            button = QPushButton(label, footer)
            button.setAccessibleName(label)
            button.clicked.connect(slot)
            set_control_tooltip(button, _ACTION_TIPS[i])
            row.addWidget(button)
            self.buttons[i] = button
        row.addStretch(1)
        self.back = QPushButton("Back", footer)
        self.back.setAccessibleName("Previous step")
        self.back.clicked.connect(lambda: self.steps.setCurrentRow(max(0, self.steps.currentRow() - 1)))
        set_control_tooltip(self.back, "Shows the previous step.")
        row.addWidget(self.back)
        self.cont = QPushButton("Continue", footer)
        self.cont.setAccessibleName("Next step")
        self.cont.setProperty("apvRole", "primary")
        self.cont.clicked.connect(lambda: self.steps.setCurrentRow(min(len(STEPS) - 1, self.steps.currentRow() + 1)))
        set_control_tooltip(self.cont, "Shows the next step; it starts nothing.")
        row.addWidget(self.cont)
        return footer

    @property
    def checkout(self) -> Path | None:
        return self._checkout

    @checkout.setter
    def checkout(self, value: Path | None) -> None:
        """Settings saved a checkout: step 1 reads its git state again on the next refresh (GR-54)."""
        self._checkout = value
        self._pre = None

    # ------------------------------------------------------------------------------------------ helpers
    def _final(self) -> Path | None:
        text = self.corpus.text().strip()
        if not text:
            return None
        p = Path(text).expanduser()
        return p.with_name(p.name[: -len(".partial")]) if p.name.endswith(".partial") else p

    def _reader(self) -> CorpusReader | None:
        final = self._final()
        if final is None:
            return None
        try:
            return CorpusReader.open(final)
        except AgentProvError:
            return None

    def _deposit_dir(self) -> Path | None:
        text = self.deposit.text().strip()
        return Path(text) if text else None

    def _job_view(self, key: str, what: str) -> tuple[str, list[Check]]:
        """The job of ``key`` as text (the Details pane) and as checks (``what`` names it), from one read of its
        summary."""
        job = self.jobs.get(key)
        if job is None:
            return "not started", [Check("todo", f"{what}: not started")]
        summary = read_json(job.file("summary.json")) or {}
        refusal = summary.get("refusal")
        lines = [f"job {job.job_id}: {job.state}" + (f", exit {job.exit_code} ({job.outcome})" if job.exit_code is not None
                                                     else "")]
        if job.exit_code is None:
            checks = [Check("running", f"{what}: {T.line(job.state, 40)}", f"job {job.job_id}")]
        elif job.exit_code == 0:
            checks = [Check("ok", f"{what}: finished", f"job {job.job_id}, exit 0 ({job.outcome})")]
        else:
            checks = [Check("bad", f"{what}: failed", f"job {job.job_id}, exit {job.exit_code} ({job.outcome})")]
        if isinstance(refusal, dict):
            code, message = T.clean(refusal.get("code")), T.clean(refusal.get("message", ""), 2000)
            lines.append(f"refused: {code}: {message}")
            checks.append(Check("bad", f"Refused: {code}", message))
        counters = summary.get("counters")
        if isinstance(counters, dict):
            lines += [f"  {T.clean(k, 60)}: {T.clean(v, 60)}" for k, v in sorted(counters.items())]
        for n in summary.get("notices", []) if isinstance(summary.get("notices"), list) else []:
            lines.append("notice: " + T.clean(n, 500))
            checks.append(Check("warn", "Notice", T.clean(n, 500)))
        return "\n".join(lines), checks

    def _say(self, index: int, message: str) -> None:
        """A message for step ``index`` (a form error, what Write release.toml… did): in its text and on the page."""
        self.texts[index].setPlainText(message)
        note = self.notes[index]
        note.set_plain(message)
        note.setVisible(bool(message))

    def _spec(self, key: str, form: str, values: dict[str, Any]) -> JobSpec:
        """The job a step's action starts: the one builder of its argv, shared by the action and the step's command
        card."""
        return build_spec(FORMS[form], values, label=f"package flow · {key}")

    def _start(self, key: str, form: str, values: dict[str, Any]) -> None:
        index = self.steps.currentRow()
        try:
            spec = self._spec(key, form, values)
        except FormError as exc:
            self._say(index, str(exc))
            return
        import shlex

        from agentprov_gui.ui.jobdialog import confirm

        confirmed = confirm(self, spec, shlex.join(spec.argv))
        if confirmed is None:
            return
        job = self.start_job(confirmed)
        if job is not None:
            self.jobs[key] = job
            self.notes[index].setVisible(False)

    # ------------------------------------------------------------------------------------------ steps
    def _seal_values(self, dry: bool) -> dict[str, Any]:
        return {"corpus": str(self._final() or ""), "corpus_version": self.version.text().strip(),
                "spec": self.spec.text().strip(), "licence_file": self.licence.text().strip(),
                "release_date": self.release_date.text().strip(), "dry_run": dry}

    def _verify_values(self) -> dict[str, Any]:
        seal = self.jobs.get("seal")
        digest = root_digest_of(seal) if seal is not None else None
        return {"corpus": str(self._final() or ""), "level": "chain", "release": True, "root_digest": digest or ""}

    def _deposit_values(self) -> dict[str, Any]:
        return {"deposit": self.deposit.text().strip(), "corpus": [str(self._final() or "")],
                "metadata": self.metadata.text().strip(), "release_date": self.release_date.text().strip()}

    def _verify_deposit_values(self) -> dict[str, Any] | None:
        out = Path(self.deposit.text().strip())
        metas = sorted(out.glob("*.meta.zip")) if out.is_dir() else []
        return {"corpus": str(metas[0]), "level": "chain"} if metas else None

    def dry_run(self) -> None:
        self._start("dry-run", "package_seal", self._seal_values(True))

    def marked(self) -> bool:
        """The corpus carries validation.prov_conformance "skipped" (§8.3a): sealing is refused until a full
        full recompute has validated it into a new corpus."""
        final = self._final()
        return final is not None and summarise(final).prov_conformance == "skipped"

    def seal(self) -> None:
        if self.marked():
            self.texts[4].setPlainText(MARKED_TEXT)
            final = self._final()
            if self.revalidate is not None and final is not None:
                self.revalidate(str(final))
            return
        self._start("seal", "package_seal", self._seal_values(False))

    def verify(self) -> None:
        self._start("verify", "verify", self._verify_values())

    def build_deposit(self) -> None:
        self._start("deposit", "package_deposit", self._deposit_values())

    def _zenodo_settings(self) -> tuple[Any, dict[str, Any]]:
        from agentprov_gui import settings_client
        from agentprov_gui.jobs.manager import CliLocator
        from agentprov_gui.ui.worker import run_off_ui

        cli = CliLocator.for_checkout(self._checkout)
        return cli, run_off_ui(self, lambda: settings_client.read(cli, "zenodo.")) or {}

    def write_release_toml(self) -> None:
        """A release.toml template from Settings › Zenodo (D-880), only where no file exists; the user fills it in."""
        from agentprov_gui.ui.zenodo import release_toml_template

        last = len(STEPS) - 1
        target = self.metadata.text().strip()
        if not target:
            self._say(last, "Give the release.toml path in step 8 first.")
            return
        _cli, values = self._zenodo_settings()
        path = Path(target).expanduser()
        try:
            with open(path, "x", encoding="utf-8") as out:
                out.write(release_toml_template(values))
        except FileExistsError:
            self._say(last, f"{T.line(path.name, 200)} exists; it is never overwritten.")
            return
        except OSError as exc:
            self._say(last, f"{T.line(path.name, 200)} could not be written ({type(exc).__name__}).")
            return
        self._say(last, f"Wrote {T.line(path.name, 200)} from Settings › Zenodo. Fill in the title, description and "
                        "keywords before Build Deposit (package --deposit refuses an empty title).")

    def create_zenodo_drafts(self) -> None:
        """The collection's uploader runs in a terminal pane (D-880). Prefilled with this deposit and its root digest."""
        from agentprov_gui.ui.zenodo import ZenodoDraftsDialog

        cli, values = self._zenodo_settings()
        seal = self.jobs.get("seal")
        digest = root_digest_of(seal) if seal is not None else None
        deposit = self.deposit.text().strip()
        line = f"{deposit} {digest}" if deposit and digest else deposit
        ZenodoDraftsDialog(cli, self._checkout, self, deposits=line, settings=values).exec()

    def verify_deposit(self) -> None:
        values = self._verify_deposit_values()
        if values is not None:
            self._start("verify-deposit", "verify", values)

    def _tick(self) -> None:
        """The timer: only the job status of a job-driven step is refreshed; a corpus step, the preconditions and the
        conformance mark keep what they read until a job finishes, since a seal or dry run can change corpus.json
        (GR-23, GR-54)."""
        finished = frozenset(k for k, job in self.jobs.items() if job.exit_code is not None)
        if finished != self._finished:
            self._finished = finished
            self._pre = self._marked = self._static = None
        index = self.steps.currentRow()
        if index in _JOB_STEPS:
            self._render(index)
        else:
            self._refresh_states()

    def _step_changed(self, index: int) -> None:
        for note in self.notes:  # a message belongs to the step it was given on
            note.setVisible(False)
        self._show(index)

    def _show(self, index: int) -> None:
        """A step, corpus field or deposit field change: the static parts are read again (GR-54)."""
        self._pre = self._marked = self._static = None
        self._render(index)

    def _fields_changed(self) -> None:
        """A field was edited: the current step's command card and the notes that quote a field follow it (no read)."""
        index = self.steps.currentRow()
        if index >= 0:
            self._commands(index)
        self._deposit_note()

    def _deposit_note(self) -> None:
        date = self.release_date.text().strip()
        self.deposit_section.set_note(f"Uses the release date of step 5: {T.line(date, 40)}." if date else
                                      "Uses the release date of step 5, which is not set: Build Deposit… needs it.")

    def _render(self, index: int) -> None:
        if index < 0:
            return
        self.pages.setCurrentIndex(index)
        for i, button in enumerate(self.buttons):
            if button is not None:
                button.setVisible(i == index)
        self.back.setEnabled(index > 0)
        self.cont.setEnabled(index < len(STEPS) - 1)
        text = self.texts[index]
        checks: list[Check] = []
        if index == 0:
            if self._pre is None:
                self._pre = self._preconditions()
            job, job_checks = self._job_view("dry-run", "Dry run")
            _set_text(text, self._pre[0] + "\n\nDry run:\n" + job)
            checks = [*self._pre[1], *job_checks]
        elif index == 1:
            shown, checks = self._withholding()
            _set_text(text, shown)
        elif index == 2:
            _set_text(text, self._counts())
        elif index == 3:
            _set_text(text, self._datasheet())
        elif index == 4:
            if self._marked is None:
                self._marked = self.marked()
            marked = self._marked
            button = self.buttons[4]
            if button is not None:  # a marked corpus: the button offers the full recompute instead of the seal
                button.setText("Revalidate (full recompute)…" if marked else "Seal…")
                button.setEnabled(not marked or self.revalidate is not None)
            if marked:
                _set_text(text, MARKED_TEXT)
                checks = [Check("bad", "This corpus cannot be sealed: it skipped the W3C PROV conformance check",
                                MARKED_TEXT)]
            else:
                seal = self.jobs.get("seal")
                digest = root_digest_of(seal) if seal is not None else None
                job, checks = self._job_view("seal", "Seal")
                _set_text(text, job + (f"\nroot digest {digest}" if digest else ""))
                if digest:
                    checks.append(Check("ok", "Root digest", digest))
        elif index == 5:
            seal = self.jobs.get("seal")
            digest = root_digest_of(seal) if seal is not None else None
            job, job_checks = self._job_view("verify", "Verify")
            _set_text(text, job)
            checks = [Check("note", "Root digest from this session's seal", digest) if digest else
                      Check("note", "No root digest", "No seal ran on this page in this session, so verify checks the "
                                                      "chain without an expected root digest."), *job_checks]
        elif index == 6:
            shown, checks = self._release_scan()
            _set_text(text, shown)
        elif index == 7:
            job, checks = self._job_view("deposit", "Deposit build")
            verified, verify_checks = self._job_view("verify-deposit", "Verify of the deposit")
            _set_text(text, job + "\n\nVerify of the deposit:\n" + verified)
            checks += verify_checks
            self._deposit_note()
            deposit = self.jobs.get("deposit")
            if deposit is not None and deposit.exit_code == 0 and "verify-deposit" not in self.jobs:
                self.verify_deposit()
        elif index == 8:
            shown, checks = self._finish()
            _set_text(text, shown)
        if index in self.checks:
            self.checks[index].set_checks(checks)
        self._commands(index)
        self._refresh_states()

    def _step_commands(self, index: int) -> tuple[list[tuple[str, Sequence[str]]], str]:
        """The command card of step ``index``: the argv its action would start, from the same values and builder."""
        try:
            if index == 0:
                return [("", self._spec("dry-run", "package_seal", self._seal_values(True)).argv)], ""
            if index == 4:
                if self._marked:
                    return [], ("This corpus cannot be sealed. Revalidate (full recompute)… opens the recompute job "
                                "that makes a new corpus to seal.")
                return [("", self._spec("seal", "package_seal", self._seal_values(False)).argv)], ""
            if index == 5:
                return [("", self._spec("verify", "verify", self._verify_values()).argv)], ""
            if index == 6:
                final = self._final()
                if final is None:
                    return [], "Choose a working corpus in step 1."
                return [("a repository tool: run it in the checkout, then triage every finding",
                         release_scan_argv(final))], ""
            if index == 7:
                commands: list[tuple[str, Sequence[str]]] = [
                    ("", self._spec("deposit", "package_deposit", self._deposit_values()).argv)]
                deposit = self.jobs.get("deposit")
                values = self._verify_deposit_values() if deposit is not None and deposit.exit_code == 0 else None
                if values is not None:
                    commands.append(("then the deposit's .meta.zip is verified",
                                     self._spec("verify-deposit", "verify", values).argv))
                return commands, ""
        except FormError as exc:
            return [], f"The command appears once the step's fields are complete: {exc}"
        return [], ""

    def _commands(self, index: int) -> None:
        card = self.cards.get(index)
        if card is None:
            return
        commands, note = self._step_commands(index)
        if [(c, tuple(a)) for c, a in commands] != card.commands or note != card.note:
            card.set_commands(commands, note=note)

    def _facts(self) -> dict[str, bool]:
        """What the step list's states need from the corpus, its release scan and the deposit folder; read with the
        static parts (on a step, field, checkout or finished-job change), never per tick."""
        if self._static is None:
            final = self._final()
            reader = self._reader()
            out = self._deposit_dir()
            scan = untriaged = False
            if final is not None:
                scan = final.with_name(final.name + ".release-scan.json").is_file()
                untriaged = final.with_name(final.name + ".release-scan.untriaged.json").is_file()
            self._static = {"sealed": bool(reader is not None and reader.sealed),
                            "scan": scan, "untriaged": untriaged,
                            "deposit": out is not None and (out / "DEPOSIT-MANIFEST.json").is_file()}
        return self._static

    def _job_state(self, key: str) -> str | None:
        job = self.jobs.get(key)
        if job is None:
            return None
        if job.exit_code is None:
            return "running"
        return "done" if job.exit_code == 0 else "failed"

    def _refresh_states(self) -> None:
        """Each step's state in the step list: a job step follows its job; steps 2 to 4 are done once the corpus is
        sealed (what they show is then final), 7 when its scan exists, 9 when the deposit has its manifest."""
        facts = self._facts()
        sealed = "done" if facts["sealed"] else "todo"
        built, checked = self._job_state("deposit"), self._job_state("verify-deposit")
        if "failed" in (built, checked):
            deposit = "failed"
        elif "running" in (built, checked):
            deposit = "running"
        else:
            deposit = "done" if built == "done" or facts["deposit"] else "todo"
        scan = "warn" if facts["untriaged"] else "done" if facts["scan"] else "todo"
        states = [self._job_state("dry-run") or "todo", sealed, sealed, sealed,
                  self._job_state("seal") or sealed, self._job_state("verify") or "todo", scan, deposit,
                  "done" if facts["deposit"] else "todo"]
        if states == self.states:
            return
        self.states = states
        for row, state in enumerate(states):
            self.steps.item(row).setData(Qt.ItemDataRole.AccessibleTextRole, f"{STEPS[row]}: {STEP_STATES[state][1]}")
        self.steps.viewport().update()

    def _preconditions(self) -> tuple[str, list[Check]]:
        final = self._final()
        if final is None:
            return "Choose a working corpus.", [Check("todo", "Choose a working corpus")]
        s = summarise(final)
        lines = [f"corpus: {T.line(str(final), 300)}", f"state: {s.state}" + (f" ({s.error})" if s.error else "")]
        checks = [Check("ok", "A working corpus", f"state: {s.state}") if s.state == "working" else
                  Check("note", "Already sealed", f"state: {s.state}") if s.state == "sealed" else
                  Check("bad", "The corpus cannot be read", lines[1])]
        reader = self._reader()
        manifest = reader.manifest() if reader is not None else None
        if isinstance(manifest, dict):
            partial = manifest.get("partial")
            lines.append(f"partial: {_flag(partial)} (must be false" + ("" if partial is False else "; not satisfied") + ")")
            checks.append(Check("ok", "Complete (not partial)", "partial: false") if partial is False else
                          Check("bad", "Not complete: partial must be false", f"partial: {_flag(partial)}"))
            release = _release_status(manifest.get("release"))
            lines.append(f"release status: {release}")
            checks.append(Check("note", "Release status", release))
            if reader is not None:
                mode = _validation_mode(reader)
                lines.append(f"validation mode: {mode}")
                checks.append(Check("ok", "Validated in release mode", "strict") if mode.startswith("release (") else
                              Check("bad", "Not validated in release mode", mode))
            producer = manifest.get("producer")
            advisory = producer.get("interpreter_advisory") if isinstance(producer, dict) else None
            lines.append(f"interpreter advisory: {T.clean(advisory or 'none', 80)} (must be none)")
            checks.append(Check("bad", "Interpreter advisory", T.clean(advisory, 80)) if advisory else
                          Check("ok", "No interpreter advisory"))
        lines.append(f"writer's lock: {'present' if s.writing else 'none'}")
        checks.append(Check("bad", "A writer holds the lock") if s.writing else Check("ok", "No writer holds the lock"))
        if self.checkout is not None:
            commit = git_commit(self.checkout)
            lines.append(f"checkout commit: {commit} (a clean commit is required)")
            if commit == "not available":
                checks.append(Check("warn", "The checkout's commit is not available", "sealing needs a clean commit"))
            elif commit.endswith(" (modified)"):
                checks.append(Check("warn", "The checkout has uncommitted changes; sealing needs a clean commit",
                                    commit))
            else:
                checks.append(Check("ok", "The checkout is at a clean commit", commit))
        return "\n".join(lines), checks

    def _withholding(self) -> tuple[str, list[Check]]:
        reader = self._reader()
        if reader is None or not reader.sealed:
            return ("WITHHELD.json is read after sealing (the values never appear; the sidecar is never opened).",
                    [Check("todo", "Shown once the corpus is sealed (step 5)",
                           "The withheld values never appear; the sidecar is never opened.")])
        limit = reader.limits.max_json_bytes
        try:
            if not reader.exists("WITHHELD.json"):
                return "No WITHHELD.json: nothing was withheld.", [Check("ok", "Nothing was withheld",
                                                                         "The corpus has no WITHHELD.json.")]
            with reader.open_file("WITHHELD.json") as stream:  # the size is checked before a byte is read (GR-23)
                size = os.fstat(stream.fileno()).st_size
                if size > limit:
                    return _unreadable(f"WITHHELD.json cannot be read ({size} bytes, over the {limit}-byte JSON limit)")
                data = stream.read(limit + 1)
        except AgentProvError as exc:
            return _unreadable(f"WITHHELD.json cannot be read ({exc.code})")
        except OSError as exc:
            return _unreadable(f"WITHHELD.json cannot be read ({type(exc).__name__})")
        try:
            doc = strict_json_loads(data, reader.limits)
        except AgentProvError:
            doc = None
        if not isinstance(doc, dict):
            return _unreadable("WITHHELD.json cannot be read (corpus.read.json)")
        raw_entries = doc.get("entries")
        entries: list[Any] = raw_entries if isinstance(raw_entries, list) else []
        reasons: Counter[str] = Counter()
        bases: Counter[str] = Counter()
        rules: Counter[str] = Counter()
        affected: set[str] = set()
        for e in entries:
            if not isinstance(e, dict):
                continue
            reasons[str(e.get("reason"))] += 1
            bases[str(e.get("basis"))] += 1
            listed = e.get("affected_executions")
            for ex in listed if isinstance(listed, list) else []:
                affected.add(str(ex))
        withheld = doc.get("executions")
        policies = doc.get("policies")
        for policy in policies if isinstance(policies, list) else []:
            listed_rules = policy.get("rules") if isinstance(policy, dict) else None
            for rule in listed_rules if isinstance(listed_rules, list) else []:
                rid = rule.get("id") if isinstance(rule, dict) else rule
                if isinstance(rid, str):
                    rules[rid] += 1
        whole = len(withheld) if isinstance(withheld, list) else 0
        profiles = len(policies) if isinstance(policies, list) else 0
        lines = [f"{len(entries)} withheld entries; {len(affected)} executions affected; "
                 f"{whole} executions withheld whole; {profiles} profile [withhold] policies"]
        lines += [f"reason {T.clean(k, 60)}: {n}" for k, n in reasons.most_common()]
        lines += [f"basis {T.clean(k, 60)}: {n}" for k, n in bases.most_common()]
        lines += [f"rule {T.clean(k, 120)}: {n}" for k, n in rules.most_common()]
        checks = [Check("note", f"{len(entries)} withheld entries",
                        f"{len(affected)} executions affected; {whole} withheld whole; {profiles} profile policies")]
        checks += [Check("", f"Reason: {T.clean(k, 60)}", f"{n} entries") for k, n in reasons.most_common()]
        checks += [Check("", f"Basis: {T.clean(k, 60)}", f"{n} entries") for k, n in bases.most_common()]
        checks += [Check("", f"Rule: {T.clean(k, 120)}", f"{n} policies") for k, n in rules.most_common()]
        return "\n".join(lines), checks

    def _counts(self) -> str:
        reader = self._reader()
        manifest = reader.manifest() if reader is not None else None
        if not isinstance(manifest, dict):
            return "No manifest."
        import json

        counts = manifest.get("counts", {})
        licences = manifest.get("licences", {})
        return T.multiline("counts:\n" + json.dumps(counts, indent=2, sort_keys=True) + "\n\nlicences:\n"
                           + json.dumps(licences, indent=2, sort_keys=True), 20000)

    def _datasheet(self) -> str:
        reader = self._reader()
        if reader is None or not reader.sealed:
            return "DATASHEET.md exists after sealing."
        budget = 4 * _DATASHEET_CHARS  # a display budget, not the 2 GiB artefact cap (GR-23)
        try:
            with reader.open_file("DATASHEET.md") as stream:
                data = stream.read(budget + 1)
        except AgentProvError as exc:
            return f"DATASHEET.md cannot be read ({exc.code})"
        except OSError as exc:
            return f"DATASHEET.md cannot be read ({type(exc).__name__})"
        # plain text, never rendered Markdown; long lines broken so the pane lays them out quickly
        shown = T.display_lines(T.multiline(data[:budget].decode("utf-8", "replace"), _DATASHEET_CHARS))
        if len(data) > budget:
            shown += f"\n\n[DATASHEET.md is longer than {budget} bytes; the rest is not shown]"
        return shown

    def _release_scan(self) -> tuple[str, list[Check]]:
        final = self._final()
        if final is None:
            return "", [Check("todo", "Choose a working corpus in step 1")]
        scan = final.with_name(final.name + ".release-scan.json")
        if not scan.is_file():
            return (f"{scan.name} does not exist. Run tools/release_scan.py from a terminal (a repo tool, not a CLI "
                    "command), then triage every finding.",
                    [Check("warn", "No release scan yet", f"{T.line(scan.name, 200)} does not exist beside the corpus. "
                                                          "Run the command below in a terminal, then triage every "
                                                          "finding.")])
        doc = read_json(scan) or {}
        untriaged = final.with_name(final.name + ".release-scan.untriaged.json")
        present = untriaged.is_file()
        checks = [Check("ok", "Release scan present", f"{T.line(scan.name, 200)}, format {T.clean(doc.get('format'), 60)}"),
                  Check("warn", "An untriaged findings file is present: triage every finding", T.line(untriaged.name, 200))
                  if present else Check("ok", "No untriaged findings file")]
        return (f"{scan.name} present (format {T.clean(doc.get('format'), 60)}); untriaged file present: {present}",
                checks)

    def _finish(self) -> tuple[str, list[Check]]:
        out = self._deposit_dir()
        manifest = read_json(out / "DEPOSIT-MANIFEST.json") if out is not None else None
        names: list[str] = []
        checks: list[Check] = []
        if isinstance(manifest, dict):
            for a in manifest.get("archives", []) if isinstance(manifest.get("archives"), list) else []:
                if isinstance(a, dict):
                    name, size, sha = T.clean(a.get("name"), 200), T.clean(a.get("bytes"), 20), T.clean(a.get("sha256"), 80)
                    names.append(f"{name}  {size} bytes  sha256 {sha}")
                    checks.append(Check("", name, f"{size} bytes · sha256 {sha}"))
        if not checks:
            checks = [Check("todo", "No deposit built yet", "Step 8 builds it in the deposit folder.")]
        return FINISH_TEXT + ("\n".join(names) if names else "(no deposit built yet)") + \
            "\n\nRepository: nickjones39/AgentPROV. No upload.", checks


def _unreadable(text: str) -> tuple[str, list[Check]]:
    return text, [Check("bad", "WITHHELD.json cannot be read", text)]
