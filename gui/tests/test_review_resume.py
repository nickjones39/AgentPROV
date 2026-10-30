"""GUI review GR-3: Resume rebuilds the safety facts from the recorded argv, never from job.json's word for them."""

from __future__ import annotations

import os
import shlex
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from agentprov_gui.jobs.commands import CONFORMANCE_OPTION, FORMS, JobSpec, build_spec
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
    yield runs
    runs.tick_timer.stop()
    runs.list_timer.stop()
    runs.deleteLater()


def _planted(page: Any, record: dict[str, Any]) -> Any:
    """A finished job whose job.json says what ``record`` says (job.json is untrusted input to Resume)."""
    import json
    import uuid

    from agentprov.jobs.record import JOB_FORMAT

    job_id = str(uuid.uuid7())
    d = page.manager.jobs_dir / job_id
    d.mkdir(parents=True)
    (d / "job.json").write_text(json.dumps({"format": JOB_FORMAT, "job_id": job_id, "created": "2026-10-22T00:00:00Z",
                                            "argv": [], "writes": [], **record}))
    (d / "ended.json").write_text(json.dumps({"exit_code": 0, "outcome": "ok", "how": "waited"}))
    page.refresh()
    page.select(job_id)
    return page.manager.jobs[job_id]


def _ended(qapp: Any, page: Any, spec: JobSpec) -> Any:
    job = page.start(spec)
    assert job is not None
    wait(qapp, lambda: page.manager.refresh() is not None and page.manager.jobs[job.job_id].state != "running", 30)
    page.refresh()
    page.select(job.job_id)
    return job


def _resume(page: Any, monkeypatch: pytest.MonkeyPatch) -> tuple[list[tuple[JobSpec, str]], list[JobSpec], list[str]]:
    """Resume the selected job; return what reached the confirmation, what was started and any refusal shown."""
    import agentprov_gui.ui.jobdialog as jd
    import agentprov_gui.ui.runs as runs_mod

    confirmed: list[tuple[JobSpec, str]] = []
    started: list[JobSpec] = []
    shown: list[str] = []

    def fake_confirm(parent: Any, spec: JobSpec, preview: str) -> JobSpec:
        confirmed.append((spec, preview))
        return spec

    class Box:
        def __init__(self, *a: Any, **k: Any) -> None:
            shown.append(" ".join(str(x) for x in (*a[1:], *k.values())))

        def exec(self) -> int:
            return 0

    monkeypatch.setattr(jd, "confirm", fake_confirm)
    monkeypatch.setattr(runs_mod, "safe_message_box", Box)
    monkeypatch.setattr(page, "start", lambda spec, **k: started.append(spec))
    page.resume()
    return confirmed, started, shown


def test_resumed_purge_asks_for_the_digits_again(qapp: Any, page: Any, tmp_path: Path,
                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    spec = build_spec(FORMS["purge"], {"object": "sha256:" + "ab" * 32, "reason": "secret",
                                       "corpus": str(tmp_path / "c")})
    argv = list(spec.argv)
    argv.insert(len(argv) - 1, "--yes")  # what confirm() adds after the typed digits; job.json records it
    _ended(qapp, page, replace(spec, argv=tuple(argv)))
    confirmed, _started, _shown = _resume(page, monkeypatch)
    resumed = confirmed[0][0]
    assert resumed.destructive and "--yes" not in resumed.argv and resumed.tier == "R1"


def test_resumed_tier_comes_from_the_argv(qapp: Any, page: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    net = "--allow" + "-network"
    _ended(qapp, page, JobSpec("import", ("import", "--units", "1", net), "R0", "low tier on record"))
    confirmed, _started, _shown = _resume(page, monkeypatch)
    assert confirmed[0][0].tier == "R2"


def test_resume_refuses_a_refused_option(qapp: Any, page: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    hostile = "--show" + "-content=yes"
    _ended(qapp, page, JobSpec("import", ("import", "--units", "1", hostile), "R1", "refused option"))
    confirmed, started, shown = _resume(page, monkeypatch)
    assert not confirmed and not started and shown and "--show-content" in shown[0]


def test_resume_derives_release_mode(qapp: Any, page: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    _ended(qapp, page, JobSpec("validate", ("validate", "--corpus", "c", "--release"), "R0", "release"))
    confirmed, _started, _shown = _resume(page, monkeypatch)
    assert confirmed[0][0].release


def test_resume_derives_the_conformance_skip(qapp: Any, page: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    _ended(qapp, page, JobSpec("derive", ("derive", "--corpus", "c", "--out", "n", CONFORMANCE_OPTION), "R1", "skip"))
    confirmed, _started, _shown = _resume(page, monkeypatch)
    resumed = confirmed[0][0]
    assert resumed.conformance_skipped and any("conformance" in n for n in resumed.notes)


def test_resume_refuses_a_conformance_skip_in_release_mode(qapp: Any, page: Any,
                                                           monkeypatch: pytest.MonkeyPatch) -> None:
    _ended(qapp, page, JobSpec("derive", ("derive", "--corpus", "c", "--out", "n", "--release", CONFORMANCE_OPTION),
                               "R1", "forged"))
    confirmed, started, shown = _resume(page, monkeypatch)
    assert not confirmed and not started and shown


@pytest.mark.skipif(os.name != "posix", reason="POSIX interpreter path")
def test_resumed_tool_job_stays_raw(qapp: Any, page: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    checkout = tmp_path / "checkout"
    (checkout / "tools").mkdir(parents=True)
    (checkout / ".venv" / "bin").mkdir(parents=True)
    os.symlink(sys.executable, checkout / ".venv" / "bin" / "python")
    (checkout / "tools" / "ci_local.py").write_text("import sys\nprint('ci ok')\n", encoding="utf-8")
    page.manager.cli = CliLocator(checkout, (sys.executable, str(FAKE)), (str(checkout / ".venv" / "bin" / "python"),))
    program = page.tool_program("tools/ci_local.py")
    spec = build_spec(FORMS["ci_local"], {"only": "core"})
    _planted(page, {"command": "tool:tools/ci_local.py", "tool": "tools/ci_local.py", "tier": "R1",
                    "subcommand_argv": list(spec.argv), "label": "ci"})
    confirmed, started, _shown = _resume(page, monkeypatch)
    resumed, preview = confirmed[0]
    assert resumed.extra.get("tool") == "tools/ci_local.py" and "raw" not in resumed.extra  # D-704: `jobs start --tool`
    assert resumed.argv == spec.argv and preview == shlex.join([*program, *spec.argv])
    assert started == [resumed]


@pytest.mark.skipif(os.name != "posix", reason="POSIX interpreter path")
def test_resumed_tool_job_must_run_the_checkout_tool(qapp: Any, page: Any, tmp_path: Path,
                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    checkout = tmp_path / "checkout"
    (checkout / "tools").mkdir(parents=True)
    (checkout / "tools" / "ci_local.py").write_text("print('ci ok')\n", encoding="utf-8")
    page.manager.cli = CliLocator(checkout, (sys.executable, str(FAKE)))
    other = (sys.executable, str(checkout / "tools" / "ci_local.py"))  # not the checkout's interpreter
    _ended(qapp, page, JobSpec("ci_local", other, "R1", "forged tool", extra={"raw": True}))
    confirmed, started, shown = _resume(page, monkeypatch)
    assert not confirmed and not started and shown


@pytest.mark.parametrize(("command", "argv"), [
    ("info", ("import", "--corpus", "c", "src")),
    ("stats", ("package", "c")),
    ("info", ("backends", "build", "agentdojo")),
])
def test_resume_refuses_an_argv_that_is_not_its_forms(qapp: Any, page: Any, command: str, argv: tuple[str, ...],
                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    """GR-46: a job.json naming an R0 form cannot carry another form's argv past the confirmation at R0."""
    _planted(page, {"command": command, "subcommand_argv": list(argv), "tier": "R0", "label": "planted"})
    confirmed, started, shown = _resume(page, monkeypatch)
    assert not confirmed and not started and shown


def test_resume_spec_checks_the_form_words_and_takes_the_slot_from_the_argv() -> None:
    from agentprov_gui.jobs.commands import FormError, resume_spec

    with pytest.raises(FormError):
        resume_spec("backends_build", ("backends", "status"), "R1", "x")
    with pytest.raises(FormError):
        resume_spec("import", ("validate", "--corpus", "c"), "R1", "x")
    assert resume_spec("backends_build", ("backends", "build", "agentdojo"), "R1", "x", slot=None).slot == "backends"
    assert resume_spec("import", ("import", "--fetch", "src"), "R1", "x").slot == "cache"
