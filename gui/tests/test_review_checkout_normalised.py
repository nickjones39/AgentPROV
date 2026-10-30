"""GUI review GR-51: a checkout typed as a relative or ``~`` path is made absolute (``expanduser``, then ``abspath``)
when Settings saves it and when the CLI locator reads it. Before, ``ck`` gave a relative program that the spawn (cwd =
the job directory) could not find (``gui.spawn.failed``), and ``~/ck`` reported the CLI missing."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from agentprov_gui.jobs.commands import JobSpec
from agentprov_gui.jobs.manager import CliLocator, JobManager
from test_jobs import wait_end

posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX executable script")


FAKE = Path(__file__).parent / "fake" / "fake_cli.py"


def _checkout(root: Path) -> Path:
    """A checkout whose ``agentprov`` is the fake CLI (D-704: a spawn is ``agentprov jobs start``, which it hands to
    the core)."""
    import sys

    bindir = root / ".venv" / "bin"
    bindir.mkdir(parents=True)
    (bindir / "agentprov").write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE}" "$@"\n', encoding="utf-8")
    (bindir / "python").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    for name in ("agentprov", "python"):
        (bindir / name).chmod(0o755)
    return root


@posix_only
@pytest.mark.parametrize("typed", ["ck", "./ck", "~/ck-home"])
def test_locator_resolves_a_relative_or_home_checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                      typed: str) -> None:
    work, fake_home = tmp_path / "work", tmp_path / "fake-home"
    _checkout(work / "ck")
    _checkout(fake_home / "ck-home")
    monkeypatch.chdir(work)
    monkeypatch.setenv("HOME", str(fake_home))
    cli = CliLocator.for_checkout(Path(typed))
    assert cli.available, typed
    assert cli.checkout is not None and cli.checkout.is_absolute()
    assert all(os.path.isabs(p) for p in (cli.program[0], cli.python[0])), (cli.program, cli.python)
    m = JobManager(tmp_path / "home", cli)
    job = m.spawn(JobSpec("validate", ("validate", "--corpus", str(tmp_path / "c")), "R0", "v"))
    wait_end(m, job.job_id)
    assert m.jobs[job.job_id].exit_code == 0


def test_settings_store_an_absolute_checkout(qapp: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from PySide6.QtCore import QSettings

    from agentprov_gui.settings import Settings
    from agentprov_gui.ui.dialogs import SettingsDialog

    work, fake_home = tmp_path / "work", tmp_path / "fake-home"
    work.mkdir()
    monkeypatch.chdir(work)
    monkeypatch.setenv("HOME", str(fake_home))
    settings = Settings(QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    dlg = SettingsDialog(settings)
    for typed, want in (("ck", work / "ck"), ("./ck", work / "ck"), ("~/" + "ck-home", fake_home / "ck-home")):
        dlg.checkout.setText(typed)
        dlg._accept()
        assert settings.store.value("paths/checkout") == str(want), typed
        assert settings.checkout == want
    settings.store.setValue("paths/checkout", "~/" + "older")  # a value stored before the fix is read absolute too
    assert settings.checkout == fake_home / "older"
    dlg.deleteLater()
