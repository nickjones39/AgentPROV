"""D-1060, the window frame and its read-only pages in the house style: the sidebar as a source list, the toolbar and
status bar on the theme's tokens, and the terminal command cards of Logs, System, Licences and the Assistant, each
built by the function (a job form, or the Assistant's own argv) whose argv the GUI runs. The Assistant's CLI is a fake
caller: no model, no network."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from agentprov_gui.jobs.commands import FORMS, JobSpec, build_spec
from agentprov_gui.jobs.manager import CliLocator, JobManager
from test_help_pages import FakeCli, _reply, wait

FAKE = Path(__file__).parent / "fake" / "fake_cli.py"


@pytest.fixture
def window(qapp: Any, tmp_path: Path) -> Any:
    from PySide6.QtCore import QSettings

    from agentprov_gui.settings import Settings
    from agentprov_gui.ui.mainwindow import MainWindow

    settings = Settings(QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    w = MainWindow(settings, cache_dir=tmp_path / "layout", home=tmp_path / "home")
    yield w
    w.close()


# ---------------------------------------------------------------------------------------------- the frame
def test_the_sidebar_is_a_source_list(window: Any) -> None:
    from PySide6.QtCore import Qt

    from agentprov_gui.ui.brand import GLYPH_ROLE, GLYPHS, SourceListDelegate

    bar = window.sidebar
    assert isinstance(bar.itemDelegate(), SourceListDelegate)
    assert bar.accessibleName() == "Navigation"
    sections = [bar.item(i).text() for i in range(bar.count()) if not bar.item(i).flags() & Qt.ItemFlag.ItemIsSelectable]
    assert sections == ["CORPORA", "JOBS", "RELEASE", "HELP"], "headings in capitals, never selectable"
    pages = [bar.item(i) for i in range(bar.count()) if bar.item(i).flags() & Qt.ItemFlag.ItemIsSelectable]
    assert [p.text() for p in pages] == ["Viewer", "Runs", "Logs", "System", "Licences", "Package", "Docs", "Assistant"]
    assert all(p.data(GLYPH_ROLE) == p.text() and p.text() in GLYPHS for p in pages), "each page row has its glyph"
    from PySide6.QtWidgets import QStyleOptionViewItem

    opt = QStyleOptionViewItem()
    opt.initFrom(bar)
    assert bar.itemDelegate().sizeHint(opt, bar.model().index(1, 0)).height() >= SourceListDelegate.ROW


def test_the_frame_follows_the_appearance(qapp: Any, window: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """The frame's own sheets are rebuilt from the tokens when the colour scheme changes (offscreen Qt has no
    scheme of its own, so the change is signalled by hand)."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication

    from agentprov_gui.ui import theme

    hints = QGuiApplication.styleHints()
    monkeypatch.setattr(theme, "is_dark", lambda: True)
    try:
        hints.colorSchemeChanged.emit(Qt.ColorScheme.Dark)
        assert theme.DARK.summary in window.sidebar.styleSheet()
        assert theme.DARK.summary in window.statusBar().styleSheet()
        assert theme.DARK.summary in window.toolbar.styleSheet()
    finally:
        monkeypatch.undo()
        hints.colorSchemeChanged.emit(Qt.ColorScheme.Light)
    assert theme.LIGHT.summary in window.sidebar.styleSheet()


def test_the_qt_toolbar_draws_a_glyph_on_each_button(window: Any) -> None:
    from PySide6.QtWidgets import QToolButton

    bar = window.toolbar
    assert bar is not None and bar.accessibleName() == "Main toolbar" and not bar.isMovable()
    glyphed = [b for b in bar.findChildren(QToolButton) if b.property("apvGlyph")]
    assert {b.property("apvGlyph") for b in glyphed} == {"toggleSidebar", "openCorpus", "reload", "newJob", "devRun"}
    assert all(not b.icon().isNull() for b in glyphed)
    assert all(window.action_map[k].icon().isNull() for k in ("openCorpus", "reload")), "menus stay without icons"


def test_the_job_count_is_a_status_badge(window: Any) -> None:
    from agentprov_gui.ui.forms import StatusBadge

    assert isinstance(window.activity, StatusBadge)
    window._jobs_changed(2, 5)
    assert window.activity.text() == "● 2 running" and window.activity.kind == "info"
    window._jobs_changed(0, 5)
    assert window.activity.text() == "5 jobs" and window.activity.kind == "neutral"


# ---------------------------------------------------------------------------------------------- Logs
@pytest.fixture
def ended_job(qapp: Any, tmp_path: Path) -> tuple[JobManager, Any]:
    manager = JobManager(tmp_path / "home", CliLocator(None, (sys.executable, str(FAKE))))
    job = manager.spawn(JobSpec("import", ("import", "--units", "3"), "R1", "logged"))
    wait(qapp, lambda: manager.refresh() and manager.jobs[job.job_id].state != "running")
    return manager, manager.jobs[job.job_id]


def test_the_logs_command_card_is_the_job_forms_argv(qapp: Any, ended_job: Any) -> None:
    from agentprov_gui.ui.forms import command_text
    from agentprov_gui.ui.logs import LogsPage

    manager, job = ended_job
    page = LogsPage(manager)
    page.show()
    page.show_job(job.job_id)
    follow = build_spec(FORMS["jobs_follow"], {"job_id": job.job_id, "log": True}).argv
    show = build_spec(FORMS["jobs_show"], {"job_id": job.job_id, "format": "text"}).argv
    assert [argv for _c, argv in page.command_card.commands] == [follow, show]
    assert follow == ("jobs", "follow", "--log", job.job_id)
    assert command_text(follow) in page.command_card.plain()
    assert page.state.text() == "Ended: ok" and page.state.kind == "ok"
    page.timer.stop()


def test_the_logs_table_speaks_plainly_and_shows_local_time(qapp: Any, ended_job: Any) -> None:
    from PySide6.QtCore import Qt

    from agentprov_gui.ui.logs import LogsPage, local_time

    manager, job = ended_job
    page = LogsPage(manager)
    page.show()
    page.show_job(job.job_id)
    page._tick()
    model = page.model
    headers = [model.headerData(c, Qt.Orientation.Horizontal) for c in range(model.columnCount())]
    assert headers == ["Time", "Level", "Written by", "Execution", "Message"]
    tips = [model.headerData(c, Qt.Orientation.Horizontal, Qt.ItemDataRole.ToolTipRole) for c in range(5)]
    assert all(field in tip for field, tip in zip(("ts", "level", "logger", "ex", "msg"), tips, strict=True))
    assert model.rowCount() >= 3 and model.cell(0, 0) == local_time(model.rows[0].ts)
    # a recorded UTC time is shown in this computer's zone, named; the recorded value is in the cell's tooltip
    from agentprov.jobs.follow import LogRecord

    from agentprov_gui.ui.logs import LogModel

    alone = LogModel()
    alone.set_rows([LogRecord.from_json({"ts": "2026-11-05T01:02:03Z", "level": "ERROR", "logger": "x", "msg": "m"})])
    assert alone.cell(0, 0) == local_time("2026-11-05T01:02:03Z") != "2026-11-05T01:02:03Z"
    assert "2026-11-05T01:02:03Z" in alone.data(alone.index(0, 0), Qt.ItemDataRole.ToolTipRole)
    assert alone.data(alone.index(0, 1), Qt.ItemDataRole.BackgroundRole) is not None, "an error's level is tinted"
    assert alone.cell(0, 1) == "ERROR", "the word carries the level; the tint only repeats it"
    # the level filter: chips, one per level, under their old accessible names; debug starts off
    assert [b.accessibleName() for b in page.level_boxes.values()] == [
        "Show debug records", "Show info records", "Show warning records", "Show error records"]
    assert not page.level_boxes["DEBUG"].isChecked() and page.level_boxes["INFO"].isChecked()
    shown = model.rowCount()
    page.level_boxes["INFO"].setChecked(False)
    assert model.rowCount() < shown
    page.timer.stop()


def test_local_time_names_the_zone() -> None:
    import datetime as dt

    from agentprov_gui.ui.logs import local_time

    text = local_time("2026-11-05T01:02:03Z")
    zone = dt.datetime(2026, 11, 5, 1, 2, 3, tzinfo=dt.UTC).astimezone().tzname()
    assert text.endswith(f" {zone}") and text[:4] == "2026"
    assert local_time("not a time") == "not a time"


# ---------------------------------------------------------------------------------------------- System
def test_the_system_command_card_and_badge_follow_the_job(qapp: Any, tmp_path: Path) -> None:
    import os

    from agentprov_gui.ui.system import SystemPage

    page = SystemPage(tmp_path)
    info = build_spec(FORMS["info"], {"format": "text"}).argv
    assert [argv for _c, argv in page.command_card.commands] == [info]
    assert page.following.text() == "No job followed"
    page.follow_job(os.getpid(), None, "01abcdef-0000-7000-8000-000000000000")
    show = build_spec(FORMS["jobs_show"], {"job_id": "01abcdef-0000-7000-8000-000000000000", "format": "text"}).argv
    assert [argv for _c, argv in page.command_card.commands] == [info, show]
    page.sampler.active = True
    page._show(page.sampler.sample())
    assert page.following.text().startswith("Job 01abcdef-0000: 1 process") and page.following.kind == "info"
    headers = [page.procs.horizontalHeaderItem(c).text() for c in range(page.procs.columnCount())]
    assert headers == ["Process id", "Name", "CPU", "Memory (MiB)", "Threads"]
    page.shutdown()


def test_the_pages_never_scroll_sideways_at_900_px(qapp: Any, window: Any) -> None:
    from PySide6.QtCore import Qt

    window.resize(900, 640)
    window.show()
    window.go("System")
    qapp.processEvents()
    page = window.system.page
    assert page.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert page.widget().minimumSizeHint().width() <= page.viewport().width()
    for name in ("Logs", "Licences", "Docs"):  # the other pages fit the window's narrowest width
        window.go(name)
        qapp.processEvents()
        assert window.pages.currentWidget().minimumSizeHint().width() <= window.pages.width(), name
    window.open_assistant()
    qapp.processEvents()
    assert window.assistant.minimumSizeHint().width() <= window.tabs.width()
    window.system.shutdown()


# ---------------------------------------------------------------------------------------------- Licences
def test_the_licences_card_is_info_of_the_selected_source(qapp: Any) -> None:
    from agentprov.adapters.registry import REGISTRY

    from agentprov_gui.about import default_checkout
    from agentprov_gui.ui.licences import LicencesPage, flags_of

    page = LicencesPage(default_checkout())
    assert [argv for _c, argv in page.command_card.commands] == [build_spec(FORMS["info"], {"format": "text"}).argv]
    flagged = next(s for s in REGISTRY if flags_of(s))
    row = next(r for r in range(page.included.rowCount()) if page.included.item(r, 0).text() == flagged.source_id)
    page.included.setCurrentCell(row, 0)
    assert [argv for _c, argv in page.command_card.commands] == [
        build_spec(FORMS["info"], {"source": flagged.source_id, "format": "text"}).argv]
    assert page.policy_badge.text() == f"Policy: {flagged.licence.policy}"
    for flag, _why in flags_of(flagged):
        assert page.flag_badges[flag].text() == flag and page.flag_badges[flag].kind == "warn"
    assert page.no_flags.isHidden()
    assert page.included.horizontalHeaderItem(1).text() == "SPDX licence"


# ---------------------------------------------------------------------------------------------- the Assistant
def test_the_assistant_card_shows_the_argv_each_message_runs(qapp: Any) -> None:
    from agentprov_gui.ui.help import AssistantPage

    cli = FakeCli({"assistant.endpoint": "openai", "assistant.model": "m"}, _reply("ok"))
    page = AssistantPage(cli)
    wait(qapp, lambda: page.ready)
    page.set_page("Logs")
    shown = page.command_card.commands
    assert len(shown) == 1 and "page name (Logs)" in shown[0][0]
    page.input.setPlainText("How do I follow a job?")
    page.send()
    wait(qapp, lambda: not page.busy)
    ran = next(argv for argv, _stdin in reversed(cli.calls) if argv[0] == "assist")
    assert list(shown[0][1]) == ran, "the card is the argv the message ran"
    assert "--keychain" in ran and "--allow-network" in ran and not any("key" in a.lower() and "=" in a for a in ran)
    assert page.state.text() == "Ready" and page.state.kind == "ok"


def test_the_assistant_card_waits_for_a_setup(qapp: Any) -> None:
    from agentprov_gui.ui.help import AssistantPage

    page = AssistantPage(FakeCli({}))
    wait(qapp, lambda: page.loaded)
    assert page.command_card.commands == [] and "Settings › Assistant" in page.command_card.note
    assert page.state.text() == "Not set up" and page.state.kind == "warn"
