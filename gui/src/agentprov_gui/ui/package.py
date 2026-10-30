"""Package (design §6.7; wireframe 06; macos-design §3.3 "Package").

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

Every job is started through the Runs page, so it has a job directory, a dashboard and a log. The 1 s timer refreshes
only the job status of the job-driven steps (1, 5, 6, 8); the corpus steps, the preconditions of step 1 and the
conformance mark of step 5 are read when the step, the corpus or the deposit field, the checkout or a finished job
changes (GR-23, GR-54).
"""

from __future__ import annotations

import os
import re
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

from agentprov.corpus.reader import CorpusReader
from agentprov.errors import AgentProvError
from agentprov.ingest.loaders import strict_json_loads
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from agentprov_gui import text as T
from agentprov_gui.about import git_commit
from agentprov_gui.jobs.commands import FORMS, FormError, JobSpec, build_spec
from agentprov_gui.jobs.manager import Job, read_json, tail_bytes
from agentprov_gui.readmodel.corpus import summarise
from agentprov_gui.ui.safe import ReadOnlyText, SafeForm, SafeLabel

__all__ = ["FINISH_TEXT", "PackagePage", "root_digest_of"]

STEPS: Final = ("1 Corpus", "2 Withholding", "3 Counts and licences", "4 Datasheet", "5 Seal", "6 Verify",
                "7 Release scan", "8 Deposit", "9 Finish")
FINISH_TEXT: Final = (
    "Nothing has been uploaded. Once step 8 has built and verified the deposit, uploading to Zenodo is a manual step, "
    "done only on "
    "the project owner's explicit instruction: Create Zenodo drafts… makes unpublished drafts (one per licence class, "
    "cross-linked to the first as the umbrella), and publishing stays yours, on Zenodo's website.\n\nFiles to upload "
    "(from DEPOSIT-MANIFEST.json):\n"
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
        self._pre: str | None = None
        self._marked: bool | None = None
        self._finished: frozenset[str] = frozenset()
        lay = QHBoxLayout(self)
        self.steps = QListWidget(self)
        self.steps.setAccessibleName("Package steps")
        self.steps.addItems(list(STEPS))
        self.steps.setMaximumWidth(220)
        lay.addWidget(self.steps)
        right = QVBoxLayout()
        lay.addLayout(right, 1)
        form = SafeForm()
        self.corpus = QLineEdit(self)
        form.add("Working corpus (DIR or DIR.partial)", self.corpus)
        self.version = QLineEdit("0.1.0", self)
        form.add("Corpus version", self.version)
        self.spec = QLineEdit(self)
        form.add("Corpus spec (corpus-spec.toml)", self.spec)
        self.licence = QLineEdit(self)
        form.add("Licence file (NAME=PATH)", self.licence)
        self.release_date = QLineEdit(self)
        form.add("Release date (YYYY-MM-DD)", self.release_date)
        self.deposit = QLineEdit(self)
        form.add("Deposit output directory", self.deposit)
        self.metadata = QLineEdit(self)
        form.add("release.toml", self.metadata)
        right.addLayout(form)
        self.pages = QStackedWidget(self)
        self.pages.setAccessibleName("Package step")
        self.texts: list[ReadOnlyText] = []
        self.buttons: list[QPushButton | None] = []
        actions: dict[int, tuple[str, Callable[[], None]]] = {
            0: ("Check and Dry Run", self.dry_run), 4: ("Seal…", self.seal), 5: ("Verify (chain, release)", self.verify),
            7: ("Build Deposit…", self.build_deposit),
        }
        for i, title in enumerate(STEPS):
            page = QWidget(self.pages)
            pl = QVBoxLayout(page)
            pl.addWidget(SafeLabel(title, name=f"Step {title}", parent=page))
            text = ReadOnlyText(name=f"{title} details", parent=page, wrap=True)
            pl.addWidget(text, 1)
            button = None
            if i in actions:
                label, slot = actions[i]
                button = QPushButton(label, page)
                button.setAccessibleName(label)
                button.clicked.connect(slot)
                pl.addWidget(button)
            self.texts.append(text)
            self.buttons.append(button)
            self.pages.addWidget(page)
        last = self.pages.widget(len(STEPS) - 1)
        finish = last.layout() if last is not None else None
        assert finish is not None  # every step page has its QVBoxLayout
        self.release_toml_btn = QPushButton("Write release.toml from the Zenodo settings…", self)
        self.release_toml_btn.setAccessibleName("Write release.toml from the Zenodo settings…")
        self.release_toml_btn.clicked.connect(self.write_release_toml)
        self.zenodo_btn = QPushButton("Create Zenodo drafts…", self)
        self.zenodo_btn.setAccessibleName("Create Zenodo drafts…")
        self.zenodo_btn.clicked.connect(self.create_zenodo_drafts)
        finish.addWidget(self.release_toml_btn)
        finish.addWidget(self.zenodo_btn)
        right.addWidget(self.pages, 1)
        nav = QHBoxLayout()
        back = QPushButton("Back", self)
        back.setAccessibleName("Previous step")
        back.clicked.connect(lambda: self.steps.setCurrentRow(max(0, self.steps.currentRow() - 1)))
        cont = QPushButton("Continue", self)
        cont.setAccessibleName("Next step")
        cont.clicked.connect(lambda: self.steps.setCurrentRow(min(len(STEPS) - 1, self.steps.currentRow() + 1)))
        nav.addStretch(1)
        nav.addWidget(back)
        nav.addWidget(cont)
        right.addLayout(nav)
        self.steps.currentRowChanged.connect(self._show)
        self.corpus.editingFinished.connect(lambda: self._show(self.steps.currentRow()))
        self.deposit.editingFinished.connect(lambda: self._show(self.steps.currentRow()))
        self.steps.setCurrentRow(0)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000)

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

    def _job_text(self, key: str) -> str:
        job = self.jobs.get(key)
        if job is None:
            return "not started"
        summary = read_json(job.file("summary.json")) or {}
        refusal = summary.get("refusal")
        lines = [f"job {job.job_id}: {job.state}" + (f", exit {job.exit_code} ({job.outcome})" if job.exit_code is not None
                                                     else "")]
        if isinstance(refusal, dict):
            lines.append(f"refused: {T.clean(refusal.get('code'))}: {T.clean(refusal.get('message', ''), 2000)}")
        counters = summary.get("counters")
        if isinstance(counters, dict):
            lines += [f"  {T.clean(k, 60)}: {T.clean(v, 60)}" for k, v in sorted(counters.items())]
        for n in summary.get("notices", []) if isinstance(summary.get("notices"), list) else []:
            lines.append("notice: " + T.clean(n, 500))
        return "\n".join(lines)

    def _start(self, key: str, form: str, values: dict[str, Any]) -> None:
        try:
            spec = build_spec(FORMS[form], values, label=f"package flow · {key}")
        except FormError as exc:
            self.texts[self.steps.currentRow()].setPlainText(str(exc))
            return
        import shlex

        from agentprov_gui.ui.jobdialog import confirm

        confirmed = confirm(self, spec, shlex.join(spec.argv))
        if confirmed is None:
            return
        job = self.start_job(confirmed)
        if job is not None:
            self.jobs[key] = job

    # ------------------------------------------------------------------------------------------ steps
    def _seal_values(self, dry: bool) -> dict[str, Any]:
        return {"corpus": str(self._final() or ""), "corpus_version": self.version.text().strip(),
                "spec": self.spec.text().strip(), "licence_file": self.licence.text().strip(),
                "release_date": self.release_date.text().strip(), "dry_run": dry}

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
        seal = self.jobs.get("seal")
        digest = root_digest_of(seal) if seal is not None else None
        values = {"corpus": str(self._final() or ""), "level": "chain", "release": True, "root_digest": digest or ""}
        self._start("verify", "verify", values)

    def build_deposit(self) -> None:
        values = {"deposit": self.deposit.text().strip(), "corpus": [str(self._final() or "")],
                  "metadata": self.metadata.text().strip(), "release_date": self.release_date.text().strip()}
        self._start("deposit", "package_deposit", values)

    def _zenodo_settings(self) -> tuple[Any, dict[str, Any]]:
        from agentprov_gui import settings_client
        from agentprov_gui.jobs.manager import CliLocator

        cli = CliLocator.for_checkout(self._checkout)
        return cli, settings_client.read(cli, "zenodo.") or {}

    def write_release_toml(self) -> None:
        """A release.toml template from Settings › Zenodo (D-880), only where no file exists; the user fills it in."""
        from agentprov_gui.ui.zenodo import release_toml_template

        text = self.texts[len(STEPS) - 1]
        target = self.metadata.text().strip()
        if not target:
            text.setPlainText("Give the release.toml path above first.")
            return
        _cli, values = self._zenodo_settings()
        path = Path(target).expanduser()
        try:
            with open(path, "x", encoding="utf-8") as out:
                out.write(release_toml_template(values))
        except FileExistsError:
            text.setPlainText(f"{T.line(path.name, 200)} exists; it is never overwritten.")
            return
        except OSError as exc:
            text.setPlainText(f"{T.line(path.name, 200)} could not be written ({type(exc).__name__}).")
            return
        text.setPlainText(f"Wrote {T.line(path.name, 200)} from Settings › Zenodo. Fill in the title, description and "
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
        out = Path(self.deposit.text().strip())
        metas = sorted(out.glob("*.meta.zip")) if out.is_dir() else []
        if metas:
            self._start("verify-deposit", "verify", {"corpus": str(metas[0]), "level": "chain"})

    def _tick(self) -> None:
        """The timer: only the job status of a job-driven step is refreshed; a corpus step, the preconditions and the
        conformance mark keep what they read until a job finishes, since a seal or dry run can change corpus.json
        (GR-23, GR-54)."""
        finished = frozenset(k for k, job in self.jobs.items() if job.exit_code is not None)
        if finished != self._finished:
            self._finished = finished
            self._pre = self._marked = None
        index = self.steps.currentRow()
        if index in _JOB_STEPS:
            self._render(index)

    def _show(self, index: int) -> None:
        """A step, corpus field or deposit field change: the static parts are read again (GR-54)."""
        self._pre = self._marked = None
        self._render(index)

    def _render(self, index: int) -> None:
        if index < 0:
            return
        self.pages.setCurrentIndex(index)
        text = self.texts[index]
        if index == 0:
            if self._pre is None:
                self._pre = self._preconditions()
            _set_text(text, self._pre + "\n\nDry run:\n" + self._job_text("dry-run"))
        elif index == 1:
            _set_text(text, self._withholding())
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
                return
            seal = self.jobs.get("seal")
            digest = root_digest_of(seal) if seal is not None else None
            _set_text(text, self._job_text("seal") + (f"\nroot digest {digest}" if digest else ""))
        elif index == 5:
            _set_text(text, self._job_text("verify"))
        elif index == 6:
            _set_text(text, self._release_scan())
        elif index == 7:
            _set_text(text, self._job_text("deposit") + "\n\nVerify of the deposit:\n" + self._job_text("verify-deposit"))
            deposit = self.jobs.get("deposit")
            if deposit is not None and deposit.exit_code == 0 and "verify-deposit" not in self.jobs:
                self.verify_deposit()
        elif index == 8:
            _set_text(text, self._finish())

    def _preconditions(self) -> str:
        final = self._final()
        if final is None:
            return "Choose a working corpus."
        s = summarise(final)
        lines = [f"corpus: {T.line(str(final), 300)}", f"state: {s.state}" + (f" ({s.error})" if s.error else "")]
        reader = self._reader()
        manifest = reader.manifest() if reader is not None else None
        if isinstance(manifest, dict):
            partial = manifest.get("partial")
            lines.append(f"partial: {_flag(partial)} (must be false" + ("" if partial is False else "; not satisfied") + ")")
            lines.append(f"release status: {_release_status(manifest.get('release'))}")
            if reader is not None:
                lines.append(f"validation mode: {_validation_mode(reader)}")
            producer = manifest.get("producer")
            advisory = producer.get("interpreter_advisory") if isinstance(producer, dict) else None
            lines.append(f"interpreter advisory: {T.clean(advisory or 'none', 80)} (must be none)")
        lines.append(f"writer's lock: {'present' if s.writing else 'none'}")
        if self.checkout is not None:
            lines.append(f"checkout commit: {git_commit(self.checkout)} (a clean commit is required)")
        return "\n".join(lines)

    def _withholding(self) -> str:
        reader = self._reader()
        if reader is None or not reader.sealed:
            return "WITHHELD.json is read after sealing (the values never appear; the sidecar is never opened)."
        limit = reader.limits.max_json_bytes
        try:
            if not reader.exists("WITHHELD.json"):
                return "No WITHHELD.json: nothing was withheld."
            with reader.open_file("WITHHELD.json") as stream:  # the size is checked before a byte is read (GR-23)
                size = os.fstat(stream.fileno()).st_size
                if size > limit:
                    return f"WITHHELD.json cannot be read ({size} bytes, over the {limit}-byte JSON limit)"
                data = stream.read(limit + 1)
        except AgentProvError as exc:
            return f"WITHHELD.json cannot be read ({exc.code})"
        except OSError as exc:
            return f"WITHHELD.json cannot be read ({type(exc).__name__})"
        try:
            doc = strict_json_loads(data, reader.limits)
        except AgentProvError:
            doc = None
        if not isinstance(doc, dict):
            return "WITHHELD.json cannot be read (corpus.read.json)"
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
        lines = [f"{len(entries)} withheld entries; {len(affected)} executions affected; "
                 f"{len(withheld) if isinstance(withheld, list) else 0} executions withheld whole; "
                 f"{len(policies) if isinstance(policies, list) else 0} profile [withhold] policies"]
        lines += [f"reason {T.clean(k, 60)}: {n}" for k, n in reasons.most_common()]
        lines += [f"basis {T.clean(k, 60)}: {n}" for k, n in bases.most_common()]
        lines += [f"rule {T.clean(k, 120)}: {n}" for k, n in rules.most_common()]
        return "\n".join(lines)

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

    def _release_scan(self) -> str:
        final = self._final()
        if final is None:
            return ""
        scan = final.with_name(final.name + ".release-scan.json")
        if not scan.is_file():
            return (f"{scan.name} does not exist. Run tools/release_scan.py from a terminal (a repo tool, not a CLI "
                    "command), then triage every finding.")
        doc = read_json(scan) or {}
        untriaged = final.with_name(final.name + ".release-scan.untriaged.json")
        return f"{scan.name} present (format {T.clean(doc.get('format'), 60)}); untriaged file present: {untriaged.is_file()}"

    def _finish(self) -> str:
        out = Path(self.deposit.text().strip()) if self.deposit.text().strip() else None
        manifest = read_json(out / "DEPOSIT-MANIFEST.json") if out is not None else None
        names: list[str] = []
        if isinstance(manifest, dict):
            for a in manifest.get("archives", []) if isinstance(manifest.get("archives"), list) else []:
                if isinstance(a, dict):
                    names.append(f"{T.clean(a.get('name'), 200)}  {T.clean(a.get('bytes'), 20)} bytes  "
                                 f"sha256 {T.clean(a.get('sha256'), 80)}")
        return FINISH_TEXT + ("\n".join(names) if names else "(no deposit built yet)") + \
            "\n\nRepository: nickjones39/AgentPROV. No upload."
