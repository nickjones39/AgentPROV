"""D-1130: ``agentprov backends rebuild-stale`` from the GUI: the job form, the one-call API the update flow uses
(``agentprov_gui.jobs.rebuild``) and the Runs page's **Rebuild Stale Environments…** button. The command itself is
tested in the core (``tests/cli/test_backends_rebuild_stale.py``)."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from agentprov_gui.jobs import rebuild
from agentprov_gui.jobs.commands import FORMS, REBUILD_STALE_NOTES, REBUILD_STALE_TITLE, JobSpec
from agentprov_gui.jobs.manager import REPO_COMMANDS, SpawnRefused


def test_the_form_runs_the_command_in_the_backends_slot_from_the_checkout() -> None:
    form = FORMS[rebuild.FORM]
    assert form.words == ("backends", "rebuild-stale") and form.slot == "backends" and form.menu
    assert form.title == REBUILD_STALE_TITLE
    assert form.words[0] in REPO_COMMANDS  # the job starts in the checkout (it needs backends/)


def test_the_default_spec_allows_the_network_and_says_what_it_does() -> None:
    spec = rebuild.rebuild_stale_spec()
    assert spec.argv == ("backends", "rebuild-stale", "--allow-network")
    assert spec.tier == "R2" and spec.slot == "backends" and spec.label == REBUILD_STALE_TITLE
    assert spec.notes == REBUILD_STALE_NOTES
    assert "downloads the pinned wheels" in spec.notes[0] and "about 15 minutes" in spec.notes[1]


def test_offline_backends_and_dry_run_specs() -> None:
    offline = rebuild.rebuild_stale_spec(allow_network=False, backends=("agentdojo", "autodojo"))
    assert offline.argv == ("backends", "rebuild-stale", "--backend", "agentdojo,autodojo")
    assert offline.tier == "R1" and offline.notes == REBUILD_STALE_NOTES[1:]
    dry = rebuild.rebuild_stale_spec(allow_network=False, dry_run=True)
    assert dry.argv[-1] == "--dry-run" and dry.tier == "R0" and dry.notes == ()


class _Manager:
    def __init__(self, checkout: Path | None, refuse: bool = False) -> None:
        self.cli = SimpleNamespace(checkout=checkout, available=True)
        self.spawned: list[JobSpec] = []
        self.refuse = refuse

    def spawn(self, spec: JobSpec) -> Any:
        if self.refuse:
            raise SpawnRefused("the backends slot is held by job 20261106T000000Z-aaaa", "gui.slot.busy")
        self.spawned.append(spec)
        return SimpleNamespace(job_id="20261106T010203Z-abcd")


def test_without_a_checkout_nothing_starts_and_the_note_says_why() -> None:
    manager = _Manager(None)
    started = rebuild.start_rebuild_stale(manager)
    assert started == rebuild.Started(None, rebuild.NO_CHECKOUT, "gui.checkout.missing") and manager.spawned == []
    assert "checkout" in started.note


def test_with_a_checkout_one_call_starts_the_job(tmp_path: Path) -> None:
    manager = _Manager(tmp_path)
    started = rebuild.start_rebuild_stale(manager)
    assert started.job_id == "20261106T010203Z-abcd" and started.code is None and "Runs page" in started.note
    assert [s.argv for s in manager.spawned] == [("backends", "rebuild-stale", "--allow-network")]


def test_a_refused_spawn_is_a_note_not_an_exception(tmp_path: Path) -> None:
    started = rebuild.start_rebuild_stale(_Manager(tmp_path, refuse=True))
    assert started.job_id is None and started.code == "gui.slot.busy" and "backends slot" in started.note


@pytest.fixture
def page(qapp: Any, tmp_path: Path) -> Any:
    from PySide6.QtCore import QSettings

    from agentprov_gui.jobs.manager import CliLocator, JobManager
    from agentprov_gui.settings import Settings
    from agentprov_gui.ui.runs import RunsPage

    fake = Path(__file__).parent / "fake" / "fake_cli.py"
    manager = JobManager(tmp_path / "home", CliLocator(None, (sys.executable, str(fake))))
    runs = RunsPage(manager, Settings(QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)))
    runs.tick_timer.stop()
    runs.list_timer.stop()
    yield runs
    runs.deleteLater()


def test_the_runs_button_without_a_checkout_explains(page: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from agentprov_gui.ui import runs

    shown: list[tuple[Any, ...]] = []
    monkeypatch.setattr(runs, "safe_message_box", lambda *a, **k: shown.append(a) or SimpleNamespace(exec=lambda: 0))
    started: list[JobSpec] = []
    monkeypatch.setattr(page, "start", lambda spec, **k: started.append(spec))
    assert page.rebuild_btn.accessibleName() == "Rebuild stale backend environments"
    page.rebuild_btn.click()
    assert shown and shown[0][2] == rebuild.NO_CHECKOUT and started == []


def test_the_runs_button_confirms_then_starts(page: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from agentprov_gui.ui import jobdialog

    page.manager.cli = SimpleNamespace(checkout=tmp_path, available=True, program=("agentprov",))
    asked: list[tuple[JobSpec, str]] = []
    answer: list[JobSpec | None] = [None]
    monkeypatch.setattr(jobdialog, "confirm", lambda parent, spec, preview: asked.append((spec, preview)) or answer[0])
    started: list[JobSpec] = []
    monkeypatch.setattr(page, "start", lambda spec, **k: started.append(spec))
    page.rebuild_btn.click()  # cancelled
    assert asked[0][1] == "agentprov backends rebuild-stale --allow-network" and asked[0][0].tier == "R2"
    assert started == []
    answer[0] = asked[0][0]
    page.rebuild_btn.click()
    assert [s.argv for s in started] == [("backends", "rebuild-stale", "--allow-network")]


def test_the_update_hook_starts_the_rebuild_only_after_the_program_part(tmp_path: Path) -> None:
    manager = _Manager(tmp_path)
    notes: list[str] = []
    hook = rebuild.after_update(manager, notes.append)
    hook(["The app"])
    assert manager.spawned == [] and notes == []
    hook(["The app", rebuild.PROGRAM_PART])
    assert len(manager.spawned) == 1 and "Runs page" in notes[0]
    without = rebuild.after_update(_Manager(None), notes.append)
    without([rebuild.PROGRAM_PART])
    assert notes[-1] == rebuild.NO_CHECKOUT
    assert "about 15 minutes" in rebuild.CONFIRM_LINE and "rebuild-stale" in rebuild.CONFIRM_LINE


def test_the_main_window_hooks_the_rebuild_into_the_update(qapp: Any, tmp_path: Path) -> None:
    """D-1130: the confirmation names the rebuild only for a program part with a checkout; after the installs the hook
    starts it through the jobs' manager (or says why not), and the note reaches About's result and the status bar."""
    from PySide6.QtCore import QSettings

    from agentprov_gui import updates as U
    from agentprov_gui.settings import Settings
    from agentprov_gui.ui.mainwindow import MainWindow

    settings = Settings(QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    w = MainWindow(settings, cache_dir=tmp_path / "layout", home=tmp_path / "home")
    try:
        assert w.updates.after_update is not None and w.updates.followup is not None

        def part(name: str) -> U.Part:
            return U.Part(name, "", None, "9.9.9", "", "", ("update", "install"))

        program, app = U.UpdatePlan((part(rebuild.PROGRAM_PART),), ()), U.UpdatePlan((part("The app"),), ())
        w.manager = _Manager(None)  # the CLI without a checkout
        w.updates.after_update = None
        w._rebuild_after_update()
        assert w.updates.followup(program) is None
        w.updates.after_update([rebuild.PROGRAM_PART])
        assert w.updates.result[-1] == rebuild.NO_CHECKOUT and w.statusBar().currentMessage() == rebuild.NO_CHECKOUT
        w.manager = _Manager(tmp_path)  # a checkout
        w._rebuild_after_update()
        assert w.updates.followup(program) == rebuild.CONFIRM_LINE and w.updates.followup(app) is None
        w.updates.after_update(["The app"])
        assert w.manager.spawned == []
        w.updates.after_update(["The app", rebuild.PROGRAM_PART])
        assert [s.argv for s in w.manager.spawned] == [("backends", "rebuild-stale", "--allow-network")]
        assert "Runs page" in w.updates.result[-1]
    finally:
        w.close()
