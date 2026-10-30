"""GUI review GR-28: the Runs dashboard's stderr and argv panes are not reset on every timer tick. A newly selected
job shows the end of its stderr tail; unchanged text keeps the scroll position and selection; new text follows the
end when the user was at the end."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from agentprov_gui.jobs.commands import JobSpec
from agentprov_gui.jobs.manager import CliLocator, JobManager
from test_viewer import wait

FAKE = Path(__file__).parent / "fake" / "fake_cli.py"


@pytest.fixture
def page(qapp: Any, tmp_path: Path) -> Any:
    from PySide6.QtCore import QSettings

    from agentprov_gui.settings import Settings
    from agentprov_gui.ui.runs import RunsPage

    manager = JobManager(tmp_path / "home", CliLocator(None, (sys.executable, str(FAKE))))
    runs = RunsPage(manager, Settings(QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)))
    runs.tick_timer.stop()
    runs.list_timer.stop()
    runs.resize(1000, 800)
    runs.show()
    yield runs
    for j in list(runs.manager.jobs.values()):
        if j.state == "running":
            runs.manager.kill(j)
    runs.deleteLater()


def _lines(start: int, stop: int) -> str:
    return "".join(f"stderr line {i}\n" for i in range(start, stop))


def test_stderr_tail_follows_the_end_and_keeps_the_user_position(qapp: Any, page: Any) -> None:
    from PySide6.QtGui import QTextCursor

    job = page.start(JobSpec("import", ("import", "--units", "2"), "R1", "fake"))
    assert job is not None
    wait(qapp, lambda: page.manager.refresh() is not None and page.manager.jobs[job.job_id].state != "running", 30)
    page.refresh()
    path = job.file("stderr.txt")
    path.write_text(_lines(0, 400), encoding="utf-8")
    page.select(job.job_id)  # as a click or start() does; the list timer passes scroll=False
    qapp.processEvents()
    sb = page.stderr.verticalScrollBar()
    assert sb.maximum() > 0 and sb.value() == sb.maximum()  # (a) a newly selected job shows the newest lines
    # (b) the list timer re-selects the job: the user's position and selection survive unchanged text
    sb.setValue(sb.maximum() // 2)
    middle = sb.value()
    c = page.stderr.textCursor()
    c.movePosition(QTextCursor.MoveOperation.End)
    c.movePosition(QTextCursor.MoveOperation.PreviousBlock, QTextCursor.MoveMode.KeepAnchor, 2)
    page.stderr.setTextCursor(c)
    chosen = page.stderr.textCursor().selectedText()
    assert chosen
    sb.setValue(middle)
    argv_sb = page.argv.verticalScrollBar()
    argv_before = (argv_sb.value(), page.argv.toPlainText())
    page.refresh()
    page.refresh()
    qapp.processEvents()
    assert sb.value() == middle
    assert page.stderr.textCursor().selectedText() == chosen
    assert (argv_sb.value(), page.argv.toPlainText()) == argv_before
    # (b') new text while the user reads the middle keeps the position
    with path.open("a", encoding="utf-8") as fh:
        fh.write(_lines(400, 405))
    page.refresh()
    qapp.processEvents()
    assert sb.value() == middle
    # (c) at the end, new lines are followed
    sb.setValue(sb.maximum())
    with path.open("a", encoding="utf-8") as fh:
        fh.write(_lines(405, 415))
    page.refresh()
    qapp.processEvents()
    assert "stderr line 414" in page.stderr.toPlainText()
    assert sb.value() == sb.maximum()


def _top_line(page: Any) -> str:
    from PySide6.QtCore import QPoint

    return str(page.stderr.cursorForPosition(QPoint(0, 0)).block().text())


def _finished_job(qapp: Any, page: Any) -> Any:
    job = page.start(JobSpec("import", ("import", "--units", "2"), "R1", "fake"))
    assert job is not None
    wait(qapp, lambda: page.manager.refresh() is not None and page.manager.jobs[job.job_id].state != "running", 30)
    page.refresh()
    return job


def test_stderr_position_is_kept_by_content_when_the_tail_window_slides(qapp: Any, page: Any) -> None:
    """GR-57: past 64 KiB the tail drops its oldest lines as the file grows; the line the user reads stays on top."""
    job = _finished_job(qapp, page)
    path = job.file("stderr.txt")
    path.write_text(_lines(0, 10_000), encoding="utf-8")
    assert path.stat().st_size > 64 * 1024
    page.select(job.job_id)
    qapp.processEvents()
    sb = page.stderr.verticalScrollBar()
    sb.setValue(sb.maximum() // 2)
    qapp.processEvents()
    reading = _top_line(page)
    assert reading.startswith("stderr line ")
    for added in ((10_000, 10_400), (10_400, 10_401)):
        with path.open("a", encoding="utf-8") as fh:
            fh.write(_lines(*added))
        page.refresh()
        qapp.processEvents()
        assert _top_line(page) == reading
        assert sb.value() < sb.maximum()
    # the line the user read slid out of the window: the pane shows the oldest lines still held
    with path.open("a", encoding="utf-8") as fh:
        fh.write(_lines(10_401, 20_000))
    page.refresh()
    qapp.processEvents()
    assert sb.value() == 0


def test_stderr_long_escaped_line_is_broken_for_display(qapp: Any, page: Any) -> None:
    """GR-57: 64 KiB of NUL escapes to one 512K-char line; the pane breaks it as GR-22/GR-23 do elsewhere."""
    from agentprov_gui.text import DISPLAY_LINE_CHARS

    job = _finished_job(qapp, page)
    job.file("stderr.txt").write_bytes(bytes([0]) * (64 * 1024))
    page.select(job.job_id)
    qapp.processEvents()
    text = page.stderr.toPlainText()
    assert len(text) >= 8 * 64 * 1024
    assert max(len(part) for part in text.split("\n")) <= DISPLAY_LINE_CHARS
