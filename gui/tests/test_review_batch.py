"""GUI review GR-4 and GR-48 after D-704. Batches are the core's (``agentprov batch``; the rules that a step is checked
again before it starts and that an R2 step waits for ``--confirm-r2`` are tested in ``tests/jobs/test_batch.py``).
Here: the GUI reads a planted or hostile batch file without starting anything, and Resume Batch asks for the tier
confirmation of each held step before it runs ``batch resume --confirm-r2``."""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from agentprov_gui.jobs import batch as batch_client
from agentprov_gui.jobs.batch import BATCH_FORMAT, Batch
from agentprov_gui.jobs.commands import JobSpec
from agentprov_gui.jobs.manager import CliLocator, JobManager

FAKE = Path(__file__).parent / "fake" / "fake_cli.py"
_DD = "-" * 2  # hostile flags are built from fragments at runtime


def _manager(home: Path) -> JobManager:
    return JobManager(home, CliLocator(None, (sys.executable, str(FAKE))))


@pytest.mark.parametrize("doc", [
    {"format": BATCH_FORMAT, "batch_id": "x", "steps": "not a list"},
    {"format": BATCH_FORMAT, "batch_id": "x", "steps": [{"argv": [1, 2]}, {"argv": ["import"], "state": 3}]},
    {"format": "other", "batch_id": "x", "steps": []},
    {"format": BATCH_FORMAT, "steps": [{"argv": ["import"]}]},
])
def test_a_planted_batch_file_is_read_without_error(tmp_path: Path, doc: dict[str, Any]) -> None:
    directory = tmp_path / "home" / "batches"
    directory.mkdir(parents=True)
    (directory / "planted.json").write_text(json.dumps(doc))
    for batch in Batch.load_all(tmp_path / "home"):
        assert all(isinstance(a, str) for s in batch.steps for a in s.spec.argv)


@pytest.fixture
def page_with_held_r2(qapp: Any, tmp_path: Path) -> Iterator[Any]:
    from PySide6.QtCore import QSettings

    from agentprov_gui.settings import Settings
    from agentprov_gui.ui.runs import RunsPage

    home = tmp_path / "home"
    m = _manager(home)
    r2 = JobSpec("fetch", ("fetch", "--units", "1", _DD + "allow-" + "network"), "R2", "net")
    plain = JobSpec("import", ("import", "--units", "1"), "R1", "imp")
    bid = batch_client.create(m, "held", [r2, plain])
    path = home / "batches" / f"{bid}.json"
    doc = json.loads(path.read_text())
    doc["steps"][0]["state"] = "held"  # as a driver started without the confirmation leaves it (GR-48)
    path.write_text(json.dumps(doc))
    runs = RunsPage(m, Settings(QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)))
    yield runs
    for j in list(runs.manager.refresh()):
        if j.state == "running":
            runs.manager.kill(j)
    runs.deleteLater()


def test_resume_batch_confirms_each_held_step_before_the_cli_runs_it(
        page_with_held_r2: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    import agentprov_gui.ui.jobdialog as jd

    page = page_with_held_r2
    assert page.manager.refresh() == []  # constructing the page (GUI start) started nothing
    (batch,) = page.batches
    assert [s.state for s in batch.steps] == ["held", "pending"]
    seen: list[JobSpec] = []
    monkeypatch.setattr(jd, "confirm", lambda parent, spec, preview: seen.append(spec))  # cancelled
    page.batch_table.selectRow(0)
    page.resume_batch()
    assert [s.tier for s in seen] == ["R2"] and page.manager.refresh() == []  # no driver without the confirmation

    def ok(parent: Any, spec: JobSpec, preview: str) -> JobSpec:
        seen.append(spec)
        return spec

    monkeypatch.setattr(jd, "confirm", ok)
    page.batch_table.selectRow(0)
    page.resume_batch()
    end = time.monotonic() + 60
    while time.monotonic() < end:
        current = next(b for b in Batch.load_all(page.manager.home) if b.batch_id == batch.batch_id)
        if current.finished:
            break
        time.sleep(0.1)
    assert [s.state for s in current.steps] == ["done", "done"]
    driver = next(j for j in page.manager.refresh() if j.job_id == current.driver_job_id)
    assert driver.record["subcommand_argv"][:2] == ["batch", "run"]
