"""GUI review GR-31: a hostile or corrupted setting (a string, NaN or Infinity, a number past a spin box's range, the
wrong JSON type) never crashes the Settings dialog, a dev run or a heavy job's start; the value falls back to its
default or is clamped to the widget's range. A value typed into the dialog that ``str.isdigit()`` accepts but ``int()``
and ``float()`` reject (a superscript digit) is dropped, so OK saves every pane.

D-700: the values are ``agentprov settings`` keys, which the CLI's schema checks before the GUI sees them; the panes
and Runs still clamp what they are given (defence in depth), and old Qt-stored values are ignored."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest
from agentprov import settings as core_settings

from agentprov_gui.jobs.commands import JobSpec
from agentprov_gui.jobs.manager import CliLocator, JobManager

FAKE = Path(__file__).parent / "fake" / "fake_cli.py"
SUP2 = chr(0xB2)  # superscript two: isdigit() is True, int() and float() raise
BIG = 2**40
INF = float("in" + "f")
NAN = float("na" + "n")

CASES = [
    {"jobs.retention": "abc", "jobs.retention_days": NAN},
    {"jobs.retention": NAN, "jobs.continue_on_failure": "yes"},
    {"compute.jobs.import": [1], "compute.queue_heavy": "no"},
    {"compute.jobs.import": BIG, "compute.jobs.derive": "x", "compute.jobs.verify": -5},
    {"compute.queue_cpu": BIG, "compute.gate_n": "two", "compute.start_stagger": [1]},
    {"compute.queue_cpu": INF, "compute.cpu_budget": {"n": 1}, "compute.mem_gib_budget": True, "compute.preset": 3},
]


def _store(path: Path) -> Any:
    from PySide6.QtCore import QSettings

    return QSettings(str(path), QSettings.Format.IniFormat)


def _settle(qapp: Any) -> None:
    from PySide6.QtCore import QThreadPool

    QThreadPool.globalInstance().waitForDone(60_000)
    qapp.processEvents()


@pytest.mark.parametrize("values", CASES)
def test_hostile_values_are_clamped(qapp: Any, values: dict[str, Any]) -> None:
    from agentprov_gui.ui.settings_panes import ComputePane, JobsPane

    jobs, compute = JobsPane(None), ComputePane(None)
    try:
        jobs.show_values(values)
        compute.show_values(values)
        assert 10 <= jobs.retention.value() <= 10_000 and 1 <= jobs.retention_days.value() <= 3650
        assert all(0 <= s.value() <= 512 for s in compute.jobs.values())
        assert 1 <= compute.queue_cpu.value() <= 256 and 1 <= compute.gate_n.value() <= 256
        for key, value in [*jobs.values().items(), *compute.values().items()]:
            core_settings.coerce(key, value)  # whatever a pane would save, the schema accepts
    finally:
        jobs.deleteLater()
        compute.deleteLater()


def test_fallbacks_and_clamps(qapp: Any) -> None:
    from agentprov_gui.ui.settings_panes import ComputePane, JobsPane

    jobs, compute = JobsPane(None), ComputePane(None)
    jobs.show_values({"jobs.retention": "abc"})
    compute.show_values({"compute.jobs.import": BIG, "compute.jobs.derive": "x", "compute.queue_cpu": BIG})
    assert jobs.retention.value() == 200
    assert compute.jobs["import"].value() == 512 and compute.jobs["derive"].value() == 0
    assert compute.queue_cpu.value() == 256
    assert jobs.loaded is None and not jobs.isEnabled()  # no CLI: nothing read, so nothing would be saved
    jobs.deleteLater()
    compute.deleteLater()


def test_typed_superscript_digit_is_dropped_and_every_pane_saves(qapp: Any, tmp_path: Path, fake_checkout: Path,
                                                                 _home: Path) -> None:
    from agentprov_gui.settings import Settings
    from agentprov_gui.ui.dialogs import SettingsDialog

    settings = Settings(_store(tmp_path / "s.ini"))
    settings.checkout = fake_checkout
    dlg = SettingsDialog(settings)
    _settle(qapp)
    jobs, compute, ci, dev = dlg.panes[:4]
    assert all(p.loaded == {} and p.isEnabled() for p in (jobs, compute, ci, dev))  # read through the CLI
    jobs.retention.setValue(777)
    compute.cpu_budget.setText(SUP2)
    compute.stagger.setText("1.5")
    ci.target.setCurrentText(ci.TARGETS["github"])
    dev.cost_cap.setText(SUP2)
    dev.overrides.setText("x=" + SUP2 + ", y=3")
    parsed = dev.settings()
    assert parsed.live_cost_cap is None and dict(parsed.overrides) == {"y": 3}
    dlg._accept()
    assert core_settings.items(home=_home) == {"jobs.retention": 777, "compute.start_stagger": 1.5,
                                               "ci.default_target": "github", "devrun.override.y": 3}
    dlg.deleteLater()
    again = SettingsDialog(settings)  # read back, then saved unchanged: nothing is set or unset
    _settle(qapp)
    assert again.panes[0].retention.value() == 777 and again.panes[1].stagger.text() == "1.5"
    again.panes[0].retention.setValue(200)  # back to the default: unset
    again._accept()
    assert "jobs.retention" not in core_settings.items(home=_home)
    again.deleteLater()


class _Stop(Exception):
    pass


def _page(tmp_path: Path, checkout: Path | None) -> Any:
    from agentprov_gui.settings import Settings
    from agentprov_gui.ui.runs import RunsPage

    manager = JobManager(tmp_path / "home", CliLocator(checkout, (sys.executable, str(FAKE))))
    page = RunsPage(manager, Settings(_store(tmp_path / "s.ini")))
    page.tick_timer.stop()
    page.list_timer.stop()
    return page


def test_heavy_job_start_survives_a_bad_queue_cpu(qapp: Any, tmp_path: Path) -> None:
    page = _page(tmp_path, tmp_path / "checkout")
    page.stored["compute."] = {"compute.queue_cpu": "two"}
    seen: list[JobSpec] = []

    def spawn(spec: JobSpec, control_file: bool = False) -> Any:
        seen.append(spec)
        raise _Stop

    page.manager.spawn = spawn
    with pytest.raises(_Stop):
        page.start(JobSpec("import", ("import",), "R1", "queued import"))
    assert seen[0].extra is not None and seen[0].extra["queue_cpu"] == 2
    page.deleteLater()


def test_runs_reads_compute_settings_through_the_cli(qapp: Any, tmp_path: Path) -> None:
    """D-700: Runs reads ``compute.*`` with ``agentprov settings list`` (cached until Settings › OK)."""
    page = _page(tmp_path, tmp_path / "checkout")
    core_settings.set("compute.queue_cpu", 5, home=page.manager.home)
    core_settings.set("compute.jobs.import", 3, home=page.manager.home)
    assert page.stored_settings("compute.") == {"compute.queue_cpu": 5, "compute.jobs.import": 3}
    core_settings.set("compute.queue_cpu", 6, home=page.manager.home)
    assert page.stored_settings("compute.")["compute.queue_cpu"] == 5  # cached
    page.stored.clear()
    assert page.stored_settings("compute.")["compute.queue_cpu"] == 6
    page.deleteLater()


@pytest.mark.parametrize("value", [2**31, BIG, -BIG])
def test_new_job_survives_a_huge_stored_default_jobs(qapp: Any, tmp_path: Path, monkeypatch: Any,
                                                     value: int) -> None:
    """GR-64: a Compute default ``--jobs`` past a C int reaches Runs > New Job clamped, never as an OverflowError
    from ``QSpinBox.setValue``; a huge preset handed straight to the dialog is clamped too."""
    from agentprov_gui.jobs.commands import FORMS
    from agentprov_gui.ui.jobdialog import JobDialog

    built: list[JobDialog] = []

    def exec_(self: JobDialog) -> int:
        built.append(self)
        return 0

    monkeypatch.setattr(JobDialog, "exec", exec_)
    page = _page(tmp_path, None)
    page.stored["compute."] = {"compute.jobs.import": value, "compute.jobs.validate": value}
    page.new_job("import")
    page.new_job("validate")
    assert len(built) == 2
    dlg = JobDialog(FORMS["import"], program=(sys.executable,), preset={"jobs": value})
    built.append(dlg)
    page.deleteLater()


def _nested(depth: int) -> str:
    return "[" * depth + "]" * depth


@pytest.mark.parametrize("depth", [40, 40_000])
def test_deeply_nested_settings_are_refused(qapp: Any, tmp_path: Path, _home: Path, depth: int) -> None:
    """GR-65: a settings file nested deeper than settings ever are (40,000 levels would make ``str()`` raise
    RecursionError) is refused by the core's strict reader, and a stale Qt-stored value of the old panes is
    ignored, so MainWindow still builds."""
    from agentprov_gui.settings import Settings
    from agentprov_gui.ui import mainwindow

    (_home / "settings.json").write_text('{"format": "agentprov-settings/0.1", "values": {"jobs.retention": '
                                         + _nested(depth) + "}}", encoding="utf-8")
    with pytest.raises(core_settings.SettingsError):
        core_settings.items(home=_home)
    store = _store(tmp_path / "s.ini")
    store.setValue("compute/settings", '{"cpu_budget": ' + _nested(depth) + "}")
    store.setValue("devrun/settings", json.dumps({"include": ["a"]}))
    win = mainwindow.MainWindow(Settings(store), cache_dir=tmp_path / "c", home=tmp_path / "home")
    win.deleteLater()
