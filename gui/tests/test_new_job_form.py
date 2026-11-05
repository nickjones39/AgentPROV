"""D-1060: Runs › New Job in the one form style. Every form renders from its presentation table (or the defaults), its
command card shows exactly the argv the job runs (the same build_spec), a choice hides the rows it does not use and
leaves their fields out, and no form scrolls sideways. The compact two-column layout: the form on the left, "What
happens" (the tier and one sentence) and the command card on the right, fields placed inline after another row's
control, and the import form fitting 1000×560 without scrolling."""

from __future__ import annotations

import re
import shlex
from typing import Any

import pytest

from agentprov_gui.jobs.commands import (
    COMMON_LOOKS,
    FORMS,
    GLOBAL_FIELDS,
    GLOBAL_LOOKS,
    LOOKS,
    CommandForm,
    JobSpec,
    Look,
    build_spec,
)

_SHA = "sha256:" + "ab" * 32


def _required(form: CommandForm) -> dict[str, Any]:
    """A value for every required field, so the form builds."""
    out: dict[str, Any] = {}
    for f in form.fields:
        if not f.required:
            continue
        if f.kind in ("path", "dir"):
            out[f.key] = f"/tmp/apv-{f.key}"
        elif f.kind == "choice":
            out[f.key] = next(c for c in f.choices if c)
        elif f.kind == "int":
            out[f.key] = 1
        elif f.key in ("corpus", "part"):
            out[f.key] = f"/tmp/apv-{f.key}"
        elif f.key == "object":
            out[f.key] = _SHA
        elif f.key == "corpus_version":
            out[f.key] = "0.1.0"
        elif f.key == "release_date":
            out[f.key] = "2026-11-05"
        else:
            out[f.key] = "x"
    if form.name in ("purge", "validate"):
        out["corpus"] = "/tmp/apv-corpus"
    return out


def test_the_presentation_table_names_only_real_fields() -> None:
    """A look, a mode or a condition that names no field of its form would silently do nothing."""
    globals_ = {f.key for f in GLOBAL_FIELDS}
    assert set(GLOBAL_LOOKS) == globals_
    every = {f.key for form in FORMS.values() for f in form.fields}
    assert set(COMMON_LOOKS) <= every
    for name, look in LOOKS.items():
        form = FORMS[name]
        keys = {f.key: f for f in form.fields}
        assert set(look.fields) <= set(keys), name
        owned: list[str] = []
        for mode in look.modes:
            assert 2 <= len(mode.segments) <= 4, mode.key
            assert not mode.flag or keys[mode.flag].kind == "bool", mode.key
            assert all(k in keys and not keys[k].required for k in mode.owns()), mode.key
            owned += mode.owns()
        assert len(owned) == len(set(owned)), name  # a field belongs to one mode at most
        for key, item in look.fields.items():
            if item.when:
                other = item.when.partition("=")[0]
                assert other in keys and other != key, (name, key)
            if item.inline:  # after a field's or a mode's control
                assert item.inline in keys or item.inline in {m.key for m in look.modes}, (name, key)
                assert item.inline != key and not look.fields.get(item.inline, Look()).inline, (name, key)
        for condition, clause in look.says:  # a sentence names only the form's fields
            terms = [t.lstrip("!").partition("=")[0] for t in condition.split(",") if t]
            slots = re.findall(r"\{(\w+)(?::(?:name|short))?\}", clause)
            assert set(terms) | set(slots) <= set(keys), (name, condition, clause)
            assert clause.count("{") == len(slots), (name, clause)


@pytest.mark.parametrize("name", sorted(FORMS))
def test_every_form_renders_and_its_card_is_the_command_it_runs(qapp: Any, name: str) -> None:
    from agentprov_gui.ui.jobdialog import DEFAULT_SIZE, JobDialog

    form = FORMS[name]
    preset = _required(form)
    program = ("agentprov",) if form.tool is None else ("python3", "tools/ci_local.py", "-C", "/tmp/checkout")
    dlg = JobDialog(form, program=program, preset=preset, conformance_option="--skip-prov-conformance")
    dlg.advanced.set_open(True)
    dlg.resize(*DEFAULT_SIZE)
    dlg.show()
    qapp.processEvents()
    page = dlg.page
    assert page.widget().minimumSizeHint().width() <= page.viewport().width(), name  # rule 7: never sideways
    assert dlg.minimumWidth() <= DEFAULT_SIZE[0] and dlg.width() == DEFAULT_SIZE[0], name  # the default size suffices
    assert dlg.summary.isAncestorOf(dlg.tier) and dlg.summary.isAncestorOf(dlg.command), name  # the right column
    assert dlg.says.text().endswith("."), name
    spec = dlg.build()
    # the dialog fills the fields exactly as the preset: numbers unset, a choice at its default, or at its first value
    # when it has no blank (as the earlier combo box did)
    shown = {f.key: f.choices[0] for f in form.fields
             if f.kind == "choice" and f.default is None and "" not in f.choices and f.key not in preset}
    assert spec.argv == build_spec(form, {**shown, **preset}, conformance_option="--skip-prov-conformance").argv
    assert dlg.command_line() == shlex.join([*program, *spec.argv])
    assert dlg.tier.text().startswith(spec.tier)
    dlg.advanced.set_open(False)
    dlg.close()


def test_choosing_how_to_fill_a_form_hides_rows_and_leaves_their_fields_out(qapp: Any) -> None:
    from agentprov_gui.ui.jobdialog import JobDialog

    dlg = JobDialog(FORMS["import"], program=("agentprov",), preset={"source": "agentdojo", "corpus": "/c"})
    origin, how = dlg.modes["origin"], dlg.modes["how_much"]
    assert origin.currentText() == "Local folder" and not dlg.inputs["fetch"].isChecked()  # never the network by default
    assert not dlg.rows["input"].isHidden() and dlg.rows["allow_network"].isHidden()
    dlg.inputs["input"].edit.setText("/data/logs")
    assert "--input" in dlg.build().argv
    origin.setCurrentIndex(0)  # Fetch the pin
    assert dlg.rows["input"].isHidden() and not dlg.rows["allow_network"].isHidden()
    argv = dlg.build().argv
    assert "--fetch" in argv and "--input" not in argv  # the hidden folder is left out, not sent
    assert dlg.tier.text() == "R2 · Uses the network"  # in the What happens card, beside the choice
    assert dlg.rows["large_download"].isHidden()  # only with Download if not cached
    dlg.inputs["allow_network"].setChecked(True)
    assert not dlg.rows["large_download"].isHidden()
    assert how.currentText() == "All" and dlg.rows["limit"].isHidden() and dlg.rows["sample"].isHidden()
    how.setCurrentIndex(1)
    dlg.inputs["limit"].setValue(5)
    assert dlg.build().argv[dlg.build().argv.index("--limit") + 1] == "5"
    how.setCurrentIndex(2)
    assert "--limit" not in dlg.build().argv and not dlg.rows["sample"].isHidden()
    assert dlg.rows["seed"].isHidden()  # the seed goes with random sampling only
    dlg.inputs["sample_mode"].setCurrentIndex(dlg.inputs["sample_mode"].count() - 1)  # random
    assert not dlg.rows["seed"].isHidden()


def test_a_preset_chooses_its_segment(qapp: Any) -> None:
    """The Runs page's full recompute (a new corpus, never in place) and the screenshot's fetch preset open on the
    segment their values fill."""
    from agentprov_gui.ui.jobdialog import JobDialog

    dlg = JobDialog(FORMS["recompute"], program=("agentprov",),
                    preset={"corpus": "/c", "dry_run": False, "out": "/n", "stages": "sem,prov,validation"})
    assert dlg.modes["result"].currentText() == "Write a new corpus"
    argv = dlg.build().argv
    assert "--out" in argv and "--dry-run" not in argv
    plain = JobDialog(FORMS["recompute"], program=("agentprov",), preset={"corpus": "/c"})
    assert plain.modes["result"].currentText() == "Compare only" and "--dry-run" in plain.build().argv
    fetch = JobDialog(FORMS["import"], program=("agentprov",), preset={"source": "s", "corpus": "/c", "fetch": True,
                                                                       "limit": 5})
    assert fetch.modes["origin"].currentText() == "Fetch the pin" and fetch.modes["how_much"].currentText() == "First N"


def test_a_modes_flag_has_no_row_of_its_own(qapp: Any) -> None:
    """AU-NG-1: the mode is the flag's only control, even when a common look puts the flag under Advanced (recompute's
    dry run): choosing a segment sets or clears it, and no second switch overrides the segment."""
    from agentprov_gui.ui.jobdialog import JobDialog, _ModeControl

    for name, look in LOOKS.items():
        for mode in look.modes:
            if not mode.flag:
                continue
            dlg = JobDialog(FORMS[name], program=("agentprov",))
            assert isinstance(dlg.inputs[mode.flag], _ModeControl), (name, mode.flag)
            assert mode.flag not in dlg.rows, (name, mode.flag)
            for i in range(len(mode.segments)):
                dlg.modes[mode.key].setCurrentIndex(i)
                assert bool(dlg.values().get(mode.flag)) == (i == mode.flag_segment), (name, i)
    dlg = JobDialog(FORMS["recompute"], program=("agentprov",), preset={"corpus": "/c"})
    dlg.modes["result"].setCurrentIndex(1)  # Write a new corpus
    dlg.inputs["out"].edit.setText("/new")
    argv = dlg.build().argv
    assert "--out" in argv and "--dry-run" not in argv and dlg.ok.isEnabled()
    dlg.modes["result"].setCurrentIndex(0)  # Compare only
    argv = dlg.build().argv
    assert "--dry-run" in argv and "--out" not in argv


def test_numbers_unset_leave_the_option_out(qapp: Any) -> None:
    from agentprov_gui.ui.jobdialog import JobDialog

    dlg = JobDialog(FORMS["priors_build"], program=("agentprov",))
    assert dlg.build().argv == ("priors", "build", "--jobs", "8")  # the field's default, as before
    dlg.inputs["jobs"].setValue(dlg.inputs["jobs"].minimum())  # cleared: the grey placeholder, no option
    assert "--jobs" not in dlg.build().argv
    assert dlg.inputs["jobs"].lineEdit().placeholderText().startswith("Default")


def test_the_advanced_disclosure_is_collapsed_and_holds_the_rare_options(qapp: Any) -> None:
    from agentprov_gui.ui.jobdialog import JobDialog

    dlg = JobDialog(FORMS["derive"], program=("agentprov",), preset={"corpus": "/a", "out": "/b"})
    assert not dlg.advanced.is_open() and dlg.advanced.button.text().startswith("Advanced: ")
    for key in ("jobs", "dry_run", "g_verbose", "no_reuse"):
        assert dlg.advanced.content.isAncestorOf(dlg.inputs[key]), key
    for key in ("corpus", "out", "stages"):
        assert not dlg.advanced.content.isAncestorOf(dlg.inputs[key]), key
    assert dlg.advanced.content.isAncestorOf(dlg.conformance) and dlg.conformance.isChecked()


def test_copy_copies_the_command_the_job_runs(qapp: Any) -> None:
    from PySide6.QtGui import QGuiApplication

    from agentprov_gui.ui.jobdialog import JobDialog

    program = ("/opt/apv venv/bin/python", "-m", "agentprov")
    dlg = JobDialog(FORMS["validate"], program=program, preset={"corpus": "/c d"})
    dlg.command.copy_button.click()
    assert QGuiApplication.clipboard().text() == shlex.join([*program, *dlg.build().argv])
    assert "'/c d'" in QGuiApplication.clipboard().text()


@pytest.mark.parametrize(("argv", "tier", "destructive", "text", "kind"), [
    (("validate",), "R0", False, "R0 · Read-only", "neutral"),
    (("derive", "--out", "/n"), "R1", False, "R1 · Writes local data", "info"),
    (("import", "--fetch"), "R2", False, "R2 · Uses the network", "warn"),
    (("run", "--max-cost-usd", "5"), "R2", False, "R2 · Paid API calls", "warn"),
    (("purge", _SHA), "R1", True, "R1 · Writes local data · irreversible", "bad"),
])
def test_the_tier_badge_says_what_the_tier_means(argv: tuple[str, ...], tier: str, destructive: bool, text: str,
                                                 kind: str) -> None:
    from agentprov_gui.ui.jobdialog import tier_badge

    assert tier_badge(JobSpec(argv[0], argv, tier, "x", destructive=destructive)) == (text, kind)


def test_inline_fields_sit_in_their_hosts_row_and_follow_its_choice(qapp: Any) -> None:
    """Import: Download if not cached is a tick box in the Get the data row, shown only with Fetch the pin; N follows
    All / First N / Sample N in the same row; the fetch cache is under Advanced and goes with Fetch the pin."""
    from PySide6.QtWidgets import QCheckBox

    from agentprov_gui.ui.jobdialog import JobDialog

    dlg = JobDialog(FORMS["import"], program=("agentprov",), preset={"source": "agentdojo", "corpus": "/c"})
    origin, how = dlg.modes["origin"], dlg.modes["how_much"]
    download = dlg.inputs["allow_network"]
    assert isinstance(download, QCheckBox) and download.text() == "Download if not cached"
    assert dlg.rows["allow_network"].parentWidget() is origin.parentWidget()  # the same row
    for key in ("limit", "sample"):
        assert dlg.rows[key].parentWidget() is how.parentWidget(), key
    assert dlg.advanced.content.isAncestorOf(dlg.inputs["cache_dir"])
    assert dlg.rows["allow_network"].isHidden() and dlg.rows["cache_dir"].isHidden()  # Local folder
    origin.setCurrentIndex(0)  # Fetch the pin
    assert not dlg.rows["allow_network"].isHidden() and not dlg.rows["cache_dir"].isHidden()
    download.setChecked(True)
    dlg.inputs["cache_dir"].edit.setText("/cache")
    argv = dlg.build().argv
    assert "--allow-network" in argv and argv[argv.index("--cache-dir") + 1] == "/cache"
    origin.setCurrentIndex(1)  # Local folder: the hidden tick and the cache are left out, not sent
    argv = dlg.build().argv
    assert "--allow-network" not in argv and "--cache-dir" not in argv and "--fetch" not in argv
    how.setCurrentIndex(1)
    assert not dlg.rows["limit"].isHidden() and dlg.rows["sample"].isHidden()
    how.setCurrentIndex(2)
    assert dlg.rows["limit"].isHidden() and not dlg.rows["sample"].isHidden()
    assert "adds --allow-network" in download.toolTip() and "uncached pin is refused" in download.toolTip()


@pytest.mark.parametrize(("name", "preset", "says"), [
    ("import", {"source": "agentdojo", "corpus": "/w/corpora/agentdojo-dev", "fetch": True, "snapshot": "2024-06",
                "limit": 5},
     "Imports the first 5 new units of agentdojo snapshot 2024-06 into the new working corpus agentdojo-dev. The pin "
     "must already be in the fetch cache."),
    ("import", {"source": "agentdojo", "corpus": "/w/c", "input": "/data/logs", "sample": 20},
     "Imports a sample of 20 executions of agentdojo from logs, read in place into the new working corpus c."),
    ("derive", {"corpus": "/w/corpora/a", "out": "/w/corpora/b", "stages": "sem,prov"},
     "Derives a new corpus version from a into b (stages sem,prov)."),
    ("derive", {"corpus": "/w/a", "out": "/w/b", "dry_run": True},
     "Derives a new corpus version from a into b. A dry run: nothing is written."),
    ("verify", {"corpus": "/w/corpora/a"}, "Verifies a at the chain level."),
    ("verify", {"corpus": "/w/a", "level": "rederive", "against_pins": True, "allow_network": True},
     "Verifies a at the rederive level and compares it with the pins, downloading what is not cached."),
    ("purge", {"object": _SHA, "reason": "secret", "corpus": "/w/a"},
     "Removes the object sha256:abababab… (secret) from the working corpus a. Irreversible: Continue asks for the "
     "object's first 8 hex digits."),
    ("settings_list", {}, "Settings: list."),  # no sentence of its own: the title
])
def test_what_happens_says_what_continue_will_do(qapp: Any, name: str, preset: dict[str, Any], says: str) -> None:
    from agentprov_gui.ui.jobdialog import JobDialog

    dlg = JobDialog(FORMS[name], program=("agentprov",), preset=preset)
    assert dlg.says.text() == says
    assert dlg.summary.isAncestorOf(dlg.says) and dlg.summary.isAncestorOf(dlg.tier)


def test_a_hidden_field_never_reaches_the_sentence(qapp: Any) -> None:
    from agentprov_gui.ui.jobdialog import JobDialog, what_happens

    dlg = JobDialog(FORMS["import"], program=("agentprov",),
                    preset={"source": "s", "corpus": "/c", "input": "/in", "limit": 5})
    dlg.modes["how_much"].setCurrentIndex(0)  # All: the limit is hidden and unset
    dlg.modes["origin"].setCurrentIndex(0)  # Fetch the pin: the folder is hidden and unset
    assert dlg.says.text() == "Imports every unit of s into the new working corpus c. The pin must already be in the " \
                              "fetch cache."
    assert what_happens(FORMS["import"], dlg.values()) == dlg.says.text()


@pytest.mark.parametrize("preset", [
    {},
    {"source": "agentdojo", "corpus": "/w/corpora/agentdojo-dev", "snapshot": "2024-06", "fetch": True, "limit": 5},
])
def test_import_fits_its_default_size_without_scrolling(qapp: Any, preset: dict[str, Any]) -> None:
    """The approved compact design: the import form fits 1000×560, Advanced closed, with no scroll either way (in
    the app's style, as the app shows it)."""
    from agentprov_gui.ui import theme
    from agentprov_gui.ui.jobdialog import DEFAULT_SIZE, JobDialog

    assert DEFAULT_SIZE == (1000, 560)
    old = qapp.styleSheet()
    try:
        theme.apply_style(qapp, dark=False)
        dlg = JobDialog(FORMS["import"], program=("agentprov",), preset=preset)
        dlg.advanced.set_open(False)
        dlg.show()
        page = dlg.page
        for _ in range(20):  # the first show polishes the style sheet; the layouts and scroll ranges then settle
            qapp.processEvents()
            if page.horizontalScrollBar().maximum() == 0:
                break
        assert (dlg.width(), dlg.height()) == DEFAULT_SIZE
        assert page.verticalScrollBar().maximum() == 0 and page.horizontalScrollBar().maximum() == 0
        assert page.widget().minimumSizeHint().width() <= page.viewport().width()
        assert dlg.summary.verticalScrollBar().maximum() == 0
        assert dlg.ok.isVisibleTo(dlg) and dlg.ok.mapTo(dlg, dlg.ok.rect().bottomRight()).y() <= DEFAULT_SIZE[1]
        dlg.close()
    finally:
        qapp.setStyleSheet(old)


def test_a_zero_the_user_typed_reaches_the_argv() -> None:
    """0 == False in Python: a typed 0 or 0.0 must reach the command line, never be read as "unset"."""
    from agentprov_gui.jobs.commands import FORMS, build_spec

    seen = set()
    for form in FORMS.values():
        if any(g.required for g in form.fields):
            continue
        for f in form.fields:
            if f.kind not in ("int", "float") or f.kind in seen or f.required or f.option is None:
                continue
            argv = build_spec(form, {f.key: 0 if f.kind == "int" else 0.0}).argv
            assert str(f.option) in argv, (form.words, f.key)
            assert argv[argv.index(str(f.option)) + 1] in ("0", "0.0")
            seen.add(f.kind)
    assert "int" in seen  # every float field sits in a form with a required field
    # an unticked switch is still left out
    form = next(fm for fm in FORMS.values()
                if not any(g.required for g in fm.fields) and any(f.kind == "bool" for f in fm.fields))
    flag = next(f for f in form.fields if f.kind == "bool")
    assert str(flag.option) not in build_spec(form, {flag.key: False}).argv


def test_continue_is_red_only_for_a_job_that_deletes_or_undoes(qapp: Any) -> None:
    """Continue… (and the confirmation's Start) take the destructive style for prune, purge, cancel, key deletion, an
    override's removal and rollback; never for a read-only or an ordinary writing job."""
    from agentprov_gui.ui.jobdialog import DESTRUCTIVE_COMMANDS, JobDialog

    assert {"purge", "jobs_prune", "devrun_prune", "update_rollback", "keys_delete"} <= DESTRUCTIVE_COMMANDS
    prune = JobDialog(FORMS["jobs_prune"], program=("agentprov",))
    assert prune.ok.property("apvRole") == "destructive"
    plain = JobDialog(FORMS["validate"], program=("agentprov",), preset={"corpus": "/c"})
    assert (plain.ok.property("apvRole") or "") == ""
    for dlg in (prune, plain):
        dlg.deleteLater()


def test_the_form_column_fits_the_page_from_the_first_show(qapp: Any) -> None:
    """The rows hidden while the form is built (rule 3) no longer leave the column laid out wider than the page for the
    first rounds of the event loop: from the first round it fits, with no horizontal scroll range."""
    from agentprov_gui.ui.jobdialog import JobDialog

    dlg = JobDialog(FORMS["import"], program=("agentprov",), conformance_option="--skip-prov-conformance",
                    preset={"source": "agentdojo", "corpus": "/c/agentdojo-dev", "snapshot": "2024-06", "fetch": True,
                            "limit": 5})
    dlg.advanced.set_open(False)
    dlg.show()
    for _ in range(4):
        qapp.processEvents()
        assert dlg.page.widget().width() <= dlg.page.viewport().width()
        assert dlg.page.horizontalScrollBar().maximum() == 0
    dlg.close()
