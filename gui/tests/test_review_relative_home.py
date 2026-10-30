"""GR-21: a relative or ``~`` ``AGENTPROV_HOME`` is made absolute, so the CLI child (whose cwd is its job directory)
writes its progress, log and summary files where the GUI reads them."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

from agentprov_gui.jobs.commands import FORMS, build_spec
from agentprov_gui.jobs.manager import CliLocator, JobManager
from agentprov_gui.paths import agentprov_home

FAKE = Path(__file__).parent / "fake" / "fake_cli.py"
_REL = "rel" + "home"


def test_agentprov_home_is_absolute_and_expanded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    home = agentprov_home({"AGENTPROV_HOME": _REL})
    assert home.is_absolute() and home == tmp_path / _REL
    monkeypatch.setenv("HOME", str(tmp_path / "h"))
    assert agentprov_home({"AGENTPROV_HOME": "~" + "/x"}) == tmp_path / "h" / "x"


def test_a_relative_home_still_gives_absolute_job_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    m = JobManager(Path(_REL), CliLocator(None, (sys.executable, str(FAKE))))
    assert m.home.is_absolute() and Path(m.child_env()["AGENTPROV_HOME"]).is_absolute()
    job = m.spawn(build_spec(FORMS["validate"], {"corpus": str(tmp_path / "c")}))
    argv = job.record["argv"]
    for option in ("--progress-file", "--log-file", "--summary-json"):
        assert Path(argv[argv.index(option) + 1]).is_absolute(), option
    end = time.monotonic() + 20
    while time.monotonic() < end and not (m.jobs[job.job_id].state != "running" and m.refresh()):
        m.refresh()
        time.sleep(0.05)
    assert (tmp_path / _REL / "jobs" / job.job_id / "summary.json").is_file()  # D-704: $AGENTPROV_HOME/jobs
    assert m.jobs[job.job_id].outcome == "ok"
