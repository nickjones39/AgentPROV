"""D-1064: features the CLI refuses on this platform are disabled in the app with the CLI's message, and say so.

The platform is simulated: ``info``'s ``platform`` member is built from the core's own table for Windows x86_64, Windows
ARM64, Linux and macOS, and either fed through the fake CLI (the main window's check) or set directly. Each gated control
is disabled with the table's message as its tooltip (shown although the control is disabled), each notice is shown with
its guide link, everything else stays enabled, and macOS and Linux are unaffected except sandbox-exec off macOS.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from agentprov.platforms import unavailable_here

from agentprov_gui import platform_limits
from agentprov_gui.platform_limits import PlatformLimits

#: the real CLI question (the conftest stubs it for every other test)
FETCH = platform_limits.fetch
WIN_X64 = ("Windows", "x86_64")
WIN_ARM = ("Windows", "arm64")
LINUX = ("Linux", "x86_64")
MACOS = ("Darwin", "arm64")


def member(system: str, machine: str) -> dict[str, Any]:
    """``agentprov info --format json``'s ``platform`` member on that platform (the core's table)."""
    return {"system": system, "machine": machine,
            "unavailable": [hit.to_json() for hit in unavailable_here(system, machine)]}


def limits(where: tuple[str, str]) -> PlatformLimits:
    parsed = platform_limits.parse(0, json.dumps({"agentprov_version": "0", "platform": member(*where)}).encode())
    assert parsed is not None
    return parsed


def simulate(where: tuple[str, str]) -> PlatformLimits:
    from agentprov_gui.ui import platformnotice

    parsed = limits(where)
    platformnotice.apply(parsed)
    return parsed


def message(where: tuple[str, str], feature: str) -> str:
    hit = limits(where).get(feature)
    assert hit is not None
    return hit.message


def tip(text: str) -> str:
    from agentprov_gui.ui.safe import help_tooltip

    return help_tooltip(text)


def wait(app: Any, cond: Any, timeout: float = 30) -> None:
    from PySide6.QtCore import QEventLoop, QThreadPool

    end = time.monotonic() + timeout
    while not cond():
        assert time.monotonic() < end, "timed out"
        QThreadPool.globalInstance().waitForDone(100)
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20)


# ---------------------------------------------------------------------------------------------- the CLI's answer
def test_the_info_member_is_read_per_platform() -> None:
    assert {x.feature for x in limits(WIN_X64).limits} == {"live_runs", "sandbox_exec", "job_queue"}
    assert {x.feature for x in limits(WIN_ARM).limits} == {"live_runs", "backend_build", "sandbox_exec", "job_queue"}
    assert {x.feature for x in limits(LINUX).limits} == {"sandbox_exec"}
    assert limits(MACOS).limits == () and limits(MACOS).known
    hit = limits(WIN_X64).get("live_runs")
    assert hit is not None and hit.guide == "07-live-runs.md#platforms" and hit.headline == "Not available on Windows x86_64"
    assert "available on macOS and Linux" in hit.message and "macOS and Linux" in hit.explanation
    assert limits(WIN_ARM).get("backend_build", "agentdojo") is not None
    assert limits(WIN_ARM).get("backend_build", "inspect-agentharm") is None  # narrowed to the AgentDojo family


def test_an_older_or_failed_cli_means_nothing_is_known() -> None:
    assert platform_limits.parse(1, b"") is None
    assert platform_limits.parse(0, b'{"agentprov_version": "0"}') is None  # a CLI before D-1064
    assert platform_limits.parse(0, b"not json") is None
    assert platform_limits.current() is platform_limits.UNKNOWN and platform_limits.current().get("live_runs") is None


def test_a_guide_the_app_cannot_follow_is_dropped() -> None:
    doc = member(*WIN_X64)
    doc["unavailable"][0]["guide"] = "../../etc/passwd"
    parsed = platform_limits.parse(0, json.dumps({"platform": doc}).encode())
    assert parsed is not None and parsed.limits[0].guide == ""


@pytest.mark.parametrize(("where", "argv", "feature"), [
    (WIN_X64, ["run", "agentdojo", "--corpus", "/c"], "live_runs"),
    (WIN_X64, ["run", "agentdojo", "--preflight-only"], "live_runs"),
    (WIN_X64, ["run", "agentdojo", "--dry-run", "--m5ultra"], None),  # a host preset's dry run still plans
    (WIN_ARM, ["backends", "build", "agentdojo"], "backend_build"),
    (WIN_ARM, ["backends", "build", "autodojo", "--offline-check"], "backend_build"),
    (WIN_ARM, ["backends", "build", "agentdojo", "--dry-run"], None),  # the plan is still printed
    (WIN_ARM, ["backends", "build", "inspect-agentharm"], None),
    (WIN_X64, ["backends", "build", "agentdojo"], None),
    (LINUX, ["run", "agentdojo", "--containment", "sandbox-exec"], "sandbox_exec"),
    (LINUX, ["run", "agentdojo", "--containment", "vm"], None),
    (WIN_X64, ["jobs", "start", "--queue-cpu", "2", "--", "import", "x"], "job_queue"),
    (MACOS, ["run", "agentdojo", "--containment", "sandbox-exec"], None),
    (WIN_X64, ["import", "agentdojo"], None),
])
def test_each_refused_command_is_named(where: tuple[str, str], argv: list[str], feature: str | None) -> None:
    hit = limits(where).for_argv(argv)
    assert (hit.feature if hit is not None else None) == feature


# ---------------------------------------------------------------------------------------------- the main window
@pytest.fixture
def window(qapp: Any, tmp_path: Path, fake_checkout: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    from PySide6.QtCore import QSettings

    from agentprov_gui.settings import Settings
    from agentprov_gui.ui.mainwindow import MainWindow

    monkeypatch.setattr(platform_limits, "fetch", FETCH)  # the fake CLI answers info

    def make(where: tuple[str, str] | None) -> Any:
        if where is not None:  # what the fake CLI's info answers
            (Path(os.environ["AGENTPROV_HOME"]) / "fake-platform.json").write_text(json.dumps(member(*where)))
        settings = Settings(QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
        settings.checkout = fake_checkout
        w = MainWindow(settings, cache_dir=tmp_path / "layout", home=tmp_path / "home")
        made.append(w)
        w.show()
        wait(qapp, lambda: platform_limits.current().known or where is None)
        qapp.processEvents()
        return w

    made: list[Any] = []
    yield make
    for w in made:
        w.close()
        w.deleteLater()
    qapp.processEvents()


@pytest.mark.skipif(os.name != "posix", reason="the fake CLI is a POSIX sh script")
@pytest.mark.parametrize("where", [WIN_X64, WIN_ARM], ids=["windows-x86_64", "windows-arm64"])
def test_windows_disables_run_live_with_the_reason(qapp: Any, window: Any, where: tuple[str, str]) -> None:
    w = window(where)
    w.go("Runs")
    qapp.processEvents()
    runs = w.runs
    text = message(where, "live_runs")
    for button in (runs.live_btn, runs.live_dev_btn):
        assert not button.isEnabled() and button.toolTip() == tip(text)
    action = w.action_map["runLive"]
    assert not action.isEnabled() and action.toolTip() == tip(text)
    assert action.shortcut().toString() == "Ctrl+L" and action in w.menuBar().actions()[0].menu().actions()
    assert runs.platform_notice.isVisible()
    hit = limits(where).get("live_runs")
    assert hit is not None and runs.platform_notice.badge.text() == hit.headline
    assert hit.headline == ("Not available on Windows x86_64" if where == WIN_X64 else "Not available on Windows ARM64")
    assert "macOS and Linux" in runs.platform_notice.text.text() and runs.platform_notice.link.isVisible()
    from test_tooltip_coverage import _report, gaps

    found = gaps(runs, minimum=20)  # the notice, its badge and link have tooltips too
    assert not found, _report(found)
    # everything else stays enabled (New Job's button follows the CLI's version check, not the platform)
    assert w.action_map["newJob"].isEnabled() and w.action_map["devRun"].isEnabled()
    assert all(a.isEnabled() for a in w.menuBar().actions()[0].menu().actions() if a is not action)


@pytest.mark.skipif(os.name != "posix", reason="the fake CLI is a POSIX sh script")
@pytest.mark.parametrize("where", [LINUX, MACOS, None], ids=["linux", "macos", "unknown"])
def test_macos_and_linux_keep_run_live(qapp: Any, window: Any, where: tuple[str, str] | None) -> None:
    w = window(where)
    w.go("Runs")
    qapp.processEvents()
    runs = w.runs
    assert runs.live_btn.isEnabled() and runs.live_dev_btn.isEnabled() and w.action_map["runLive"].isEnabled()
    assert not runs.platform_notice.isVisible()
    assert "Configures a live capture" in runs.live_btn.toolTip()


@pytest.mark.skipif(os.name != "posix", reason="the fake CLI is a POSIX sh script")
def test_how_to_run_it_opens_the_guide_section_in_docs(qapp: Any, window: Any, fake_checkout: Path) -> None:
    repo = Path(__file__).resolve().parents[2]
    guide = fake_checkout / "docs" / "user-guide"
    guide.mkdir(parents=True)
    (guide / "07-live-runs.md").write_bytes((repo / "docs" / "user-guide" / "07-live-runs.md").read_bytes())
    w = window(WIN_X64)
    w.go("Runs")
    w.runs.platform_notice.link.click()
    qapp.processEvents()
    assert w.pages.currentWidget() is w.docs
    assert w.docs.current is not None and w.docs.current.name == "07-live-runs.md"


def test_a_disabled_control_still_shows_why(qapp: Any) -> None:
    """The in-use gate swallows a disabled control's tooltip; a platform-gated one gets through, and its own tooltip
    comes back once the limit is gone."""
    from PySide6.QtCore import QEvent, QPoint
    from PySide6.QtGui import QHelpEvent
    from PySide6.QtWidgets import QPushButton

    from agentprov_gui.ui import safe
    from agentprov_gui.ui.platformnotice import gate

    button = QPushButton("Run")
    safe.set_control_tooltip(button, "Starts a run.")
    gate_filter = button.findChild(safe._SettingTipGate)
    event = QHelpEvent(QEvent.Type.ToolTip, QPoint(1, 1), QPoint(1, 1))
    button.setEnabled(False)
    assert gate_filter.eventFilter(button, event) is True  # an ordinary disabled control: no tooltip
    hit = limits(WIN_X64).get("live_runs")
    gate(button, hit)
    assert not button.isEnabled() and button.toolTip() == tip(message(WIN_X64, "live_runs"))
    assert gate_filter.eventFilter(button, event) is False  # shown
    gate(button, None)
    assert button.isEnabled() and button.toolTip() == safe.help_tooltip("Starts a run.")
    button.deleteLater()


# ---------------------------------------------------------------------------------------------- Run Live
@pytest.mark.parametrize("where", [WIN_X64, WIN_ARM], ids=["windows-x86_64", "windows-arm64"])
@pytest.mark.parametrize("scripted", [True, False], ids=["scripted", "real-model"])
def test_run_live_opened_anyway_refuses_start(qapp: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                               where: tuple[str, str], scripted: bool) -> None:
    from test_runlive_form import QUOTE, _dialog, _settle

    simulate(where)
    dlg = _dialog(tmp_path, monkeypatch, scripted=scripted, quote=QUOTE)
    _settle(qapp, dlg)
    dlg.show()
    qapp.processEvents()
    text = message(where, "live_runs")
    assert dlg.platform_notice.isVisible() and dlg.platform_notice.limit is not None
    for button in (dlg.start_btn, dlg.preflight_btn):
        assert not button.isEnabled() and button.toolTip() == tip(text)
    assert dlg.error.text() == text
    dlg._start(preflight=False)
    dlg._start(preflight=True)
    assert dlg.start is None
    dlg.close()


def test_how_to_run_it_in_a_dialog_opens_a_guide_window(qapp: Any, tmp_path: Path,
                                                        monkeypatch: pytest.MonkeyPatch) -> None:
    """A modal dialog would hide the main window's Docs page: the guide opens in a window of the dialog's own."""
    from agentprov_gui.ui.help import DocsPage
    from test_runlive_form import _dialog

    simulate(WIN_X64)
    dlg = _dialog(tmp_path, monkeypatch, scripted=True)
    dlg.show()
    dlg.platform_notice.link.click()
    qapp.processEvents()
    shown = [p for p in dlg.findChildren(DocsPage) if p.isWindow() and p.isVisible()]
    assert len(shown) == 1
    shown[0].close()
    dlg.close()


def test_run_live_on_macos_is_unchanged(qapp: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from test_runlive_form import QUOTE, _dialog, _settle

    simulate(MACOS)
    dlg = _dialog(tmp_path, monkeypatch, scripted=True, quote=QUOTE)
    _settle(qapp, dlg)
    assert dlg.platform_notice.isHidden() and dlg.start_btn.isEnabled()
    assert "Confirms the run" in dlg.start_btn.toolTip()
    dlg.close()


@pytest.mark.parametrize("where", [LINUX, WIN_X64], ids=["linux", "windows"])
def test_sandbox_exec_is_shown_disabled_off_macos(qapp: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                  where: tuple[str, str]) -> None:
    from PySide6.QtCore import Qt

    from agentprov_gui.live import runspec
    from agentprov_gui.ui import runlive
    from agentprov_gui.ui.safe import safe_tooltip
    from test_runlive_form import QUOTE, _dialog, _settle

    monkeypatch.setattr(runlive, "containment_choices", lambda: runspec.containment_choices("linux"))
    simulate(where)
    dlg = _dialog(tmp_path, monkeypatch, scripted=False, quote=QUOTE)
    _settle(qapp, dlg)
    box = dlg.containment
    assert [box.itemText(i) for i in range(box.count())] == ["", "sandbox-exec", "dedicated-user", "vm"]
    index = box.findText("sandbox-exec")
    assert not box.model().item(index).isEnabled()
    assert box.itemData(index, Qt.ItemDataRole.ToolTipRole) == safe_tooltip(message(where, "sandbox_exec"))
    if where == LINUX:  # live runs work there: a preset's sandbox-exec is refused with the table's reason
        box.setCurrentText("sandbox-exec")
        assert dlg._gate() == message(LINUX, "sandbox_exec") and not dlg.start_btn.isEnabled()
        box.setCurrentText("vm")
        assert dlg._gate() != message(LINUX, "sandbox_exec")
    dlg.close()


def test_run_live_has_tooltips_on_windows(qapp: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from test_runlive_form import QUOTE, _dialog, _settle
    from test_tooltip_coverage import _report, gaps

    simulate(WIN_ARM)
    dlg = _dialog(tmp_path, monkeypatch, scripted=False, quote=QUOTE)
    _settle(qapp, dlg)
    found = gaps(dlg, minimum=40)
    dlg.close()
    assert not found, _report(found)


# ---------------------------------------------------------------------------------------------- New Job forms
@pytest.mark.parametrize(("where", "values", "refused"), [
    (WIN_ARM, {"backend": "agentdojo"}, True),
    (WIN_ARM, {"backend": "agentdyn", "offline_check": True}, True),
    (WIN_ARM, {"backend": "agentdojo", "dry_run": True}, False),
    (WIN_ARM, {"backend": "inspect-agentharm"}, False),
    (WIN_X64, {"backend": "agentdojo"}, False),
    (LINUX, {"backend": "agentdojo"}, False),
])
def test_backend_builds_on_windows_arm64(qapp: Any, where: tuple[str, str], values: dict[str, Any],
                                         refused: bool) -> None:
    from agentprov_gui.jobs.commands import FORMS
    from agentprov_gui.ui.jobdialog import JobDialog

    simulate(where)
    dlg = JobDialog(FORMS["backends_build"], program=("agentprov",), preset=values)
    dlg.show()
    qapp.processEvents()
    assert dlg.ok.isEnabled() is not refused
    assert dlg.platform_notice.isVisible() is refused
    if refused:
        assert dlg.ok.toolTip() == tip(message(WIN_ARM, "backend_build"))
        dlg._accept()
        assert dlg.spec is None
    else:
        assert "tier's confirmation" in dlg.ok.toolTip()
    dlg.close()


def test_the_run_form_on_windows(qapp: Any) -> None:
    from agentprov_gui.jobs.commands import FORMS
    from agentprov_gui.ui.jobdialog import JobDialog

    simulate(WIN_X64)
    dlg = JobDialog(FORMS["run"], program=("agentprov",), preset={"source": "agentdojo", "corpus": "/tmp/c"})
    dlg.show()
    qapp.processEvents()
    if dlg.error.isHidden():  # the form is complete: refused with the reason
        assert not dlg.ok.isEnabled() and dlg.ok.toolTip() == tip(message(WIN_X64, "live_runs"))
        assert dlg.platform_notice.isVisible()
    dlg.close()


def test_other_forms_stay_enabled_on_windows(qapp: Any, tmp_path: Path) -> None:
    from agentprov_gui.jobs.commands import FORMS
    from agentprov_gui.ui.jobdialog import JobDialog

    simulate(WIN_ARM)
    dlg = JobDialog(FORMS["validate"], program=("agentprov",), preset={"corpus": str(tmp_path)})
    dlg.show()
    qapp.processEvents()
    assert dlg.ok.isEnabled() and dlg.platform_notice.isHidden()
    dlg.close()


# ---------------------------------------------------------------------------------------------- the job queue
def _settings_cli(argv: Any) -> tuple[int, bytes, bytes]:
    return (0, json.dumps({"values": {}}).encode(), b"") if list(argv)[:2] == ["settings", "list"] else (0, b"", b"")


@pytest.mark.parametrize("where", [WIN_X64, WIN_ARM], ids=["windows-x86_64", "windows-arm64"])
def test_queue_settings_are_disabled_on_windows(qapp: Any, where: tuple[str, str]) -> None:
    from agentprov_gui.ui.platformnotice import PlatformNotice
    from agentprov_gui.ui.settings_panes import ComputePane, DevRunPane

    simulate(where)
    text = tip(message(where, "job_queue"))
    compute = ComputePane(None, cli=_settings_cli)
    dev = DevRunPane(None, cli=_settings_cli)
    wait(qapp, lambda: compute.loaded is not None and dev.loaded is not None)
    for w in (compute.queue, compute.queue_cpu, compute.cpu_budget, compute.mem_budget):
        assert not w.isEnabled() and w.toolTip() == text
    notices = [n for n in compute.findChildren(PlatformNotice) if n.accessibleName() == "Job queue on this platform"]
    assert len(notices) == 1 and not notices[0].isHidden() and notices[0].limit is not None
    assert not dev.queue_cpu.isEnabled() and dev.queue_cpu.toolTip() == text
    # the rest of the pane stays enabled
    assert all(spin.isEnabled() for spin in compute.jobs.values()) and dev.keep.isEnabled()
    compute.deleteLater()
    dev.deleteLater()


@pytest.mark.parametrize("where", [LINUX, MACOS], ids=["linux", "macos"])
def test_queue_settings_stay_on_macos_and_linux(qapp: Any, where: tuple[str, str]) -> None:
    from agentprov_gui.ui.settings_panes import ComputePane, DevRunPane

    simulate(where)
    compute = ComputePane(None, cli=_settings_cli)
    dev = DevRunPane(None, cli=_settings_cli)
    wait(qapp, lambda: compute.loaded is not None and dev.loaded is not None)
    assert compute.queue.isEnabled() and compute.queue_cpu.isEnabled() and dev.queue_cpu.isEnabled()
    compute.deleteLater()
    dev.deleteLater()


def test_no_queue_option_reaches_the_cli_on_windows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``jobs start --queue-cpu`` and a batch step's ``queue_cpu`` would be refused (platform.unsupported): on Windows
    a job's reservation stays a recorded fact and a batch step has none; on Linux both pass as before."""
    from agentprov_gui.jobs import batch
    from agentprov_gui.jobs.commands import JobSpec
    from agentprov_gui.jobs.manager import CliLocator, JobManager, SpawnRefused

    spec = JobSpec("import", ("import", "agentdojo"), "R1", "x", extra={"queue_cpu": 2})
    seen: list[list[str]] = []
    m = JobManager(tmp_path / "home", CliLocator(tmp_path, ("agentprov",)))
    monkeypatch.setattr(m, "call", lambda argv, **kw: (seen.append(list(argv)), (1, b"", b"x"))[1])
    for where, queued in ((WIN_X64, False), (LINUX, True)):
        simulate(where)
        seen.clear()
        with pytest.raises(SpawnRefused):  # the stand-in CLI refuses; only the argv is checked
            m.spawn(spec)
        head = seen[0][: seen[0].index("--")]
        assert ("--queue-cpu" in head) is queued
        assert ("queue_cpu" in batch._step_json(spec)) is queued


def test_runs_does_not_queue_heavy_jobs_on_windows(qapp: Any, tmp_path: Path, fake_checkout: Path,
                                                   monkeypatch: pytest.MonkeyPatch) -> None:
    from PySide6.QtCore import QSettings

    from agentprov_gui.jobs.commands import JobSpec
    from agentprov_gui.jobs.manager import CliLocator, JobManager, SpawnRefused
    from agentprov_gui.settings import Settings
    from agentprov_gui.ui.runs import RunsPage

    settings = Settings(QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    m = JobManager(tmp_path / "home", CliLocator.for_checkout(fake_checkout))
    runs = RunsPage(m, settings)
    spawned: list[JobSpec] = []

    def spawn(spec: JobSpec, **_kw: Any) -> Any:
        spawned.append(spec)
        raise SpawnRefused("no", "x")

    monkeypatch.setattr(m, "spawn", spawn)
    monkeypatch.setattr(runs, "stored_settings", lambda prefix: {})
    from agentprov_gui.ui import runs as runs_mod

    monkeypatch.setattr(runs_mod, "safe_message_box", lambda *a, **k: type("B", (), {"exec": lambda self: 0})())
    spec = JobSpec("import", ("import", "agentdojo"), "R1", "x")
    for where in (WIN_X64, LINUX):
        simulate(where)
        runs.start(spec)
    assert "queue_cpu" not in (spawned[0].extra or {})
    assert ("queue_cpu" in (spawned[1].extra or {})) is (os.name == "posix")
    runs.deleteLater()


def test_the_limits_module_has_no_qt() -> None:
    import subprocess

    code = ("import sys, agentprov_gui.platform_limits; "
            "sys.exit(any(m.startswith('PySide6') for m in sys.modules))")
    assert subprocess.run([sys.executable, "-c", code], check=False).returncode == 0
