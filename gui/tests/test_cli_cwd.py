"""The GUI's short CLI calls start ``run``, ``backends`` and ``migrate`` in the checkout (M.4): those commands find the
backend projects from their cwd. An app opened from the Finder has cwd ``/``, where Run Live's ``run --catalogue``
exited 3 with ``backend.repository_missing`` and showed no suites or attacks (2026-11-06). Every other command keeps
the GUI's own cwd.

The CLI here is a stand-in script that prints its cwd; nothing of agentprov runs.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


def _locator(tmp_path: Path) -> object:
    from agentprov_gui.jobs.manager import CliLocator

    checkout = tmp_path / "checkout"
    checkout.mkdir()
    script = tmp_path / "fake_agentprov.py"
    script.write_text("import os\nprint(os.getcwd())\n", encoding="utf-8")
    return CliLocator(checkout, (sys.executable, "-I", str(script)))


@pytest.mark.parametrize("argv", [["run", "--catalogue", "agentdojo"], ["backends", "build", "agentdojo"],
                                  ["migrate", "status"]])
def test_repository_commands_start_in_the_checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                   argv: list[str]) -> None:
    from agentprov_gui.jobs.manager import JobManager
    from agentprov_gui.live.cli import call
    from agentprov_gui.ui.runlive import run_cli

    cli = _locator(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)  # the Finder's "/" in the test's own tree
    checkout = str(Path(cli.checkout).resolve())  # type: ignore[attr-defined]
    manager = JobManager(tmp_path / "home", cli)  # type: ignore[arg-type]
    for code, out, _err in (run_cli(manager, argv, timeout=60), manager.call(argv, timeout=60),
                            call(cli, argv, timeout=60)):  # type: ignore[arg-type]
        assert code == 0 and Path(out.decode().strip()).resolve() == Path(checkout)


def test_other_commands_keep_the_gui_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agentprov_gui.jobs.manager import CliLocator, JobManager

    cli = _locator(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    manager = JobManager(tmp_path / "home", cli)  # type: ignore[arg-type]
    for argv in (["info"], ["settings", "list"], ["update", "status"], []):
        assert cli.cwd_for(argv) is None  # type: ignore[attr-defined]
    code, out, _err = manager.call(["info"], timeout=60)
    assert code == 0 and Path(out.decode().strip()).resolve() == elsewhere.resolve()
    assert CliLocator(None, ("agentprov",)).cwd_for(["run", "--catalogue", "agentdojo"]) is None  # no checkout


def test_the_repository_commands_are_the_core_s() -> None:
    from agentprov.jobs.tiers import REPO_COMMANDS as CORE

    from agentprov_gui.jobs.manager import REPO_COMMANDS

    assert REPO_COMMANDS == CORE  # a copy (D-391): the GUI does not import agentprov.jobs.tiers
