"""``gui/tools/screenshots.py`` removes its own work folder (``/tmp/agentprov-shots-*``) when a run ends: after success,
a leak-guard refusal (exit 1) or an error, never following the ``checkout`` symlink to the repository."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from test_review_screenshot_guard import _tool


def _populate(work: Path, outside: Path) -> None:
    (work / "corpora" / "x.partial").mkdir(parents=True)
    (work / "corpora" / "x.partial" / "executions.jsonl").write_text("{}\n", encoding="utf-8")
    (work / "checkout").symlink_to(outside, target_is_directory=True)  # as cli_shim links the repository
    os.chdir(work)


@pytest.mark.parametrize("ending", [None, RuntimeError("boom"), SystemExit(1), KeyboardInterrupt()])
def test_the_work_folder_is_removed_however_the_run_ends(tmp_path: Path, ending: BaseException | None) -> None:
    tool = _tool()
    outside = tmp_path / "repo"
    outside.mkdir()
    (outside / "keep.txt").write_text("kept", encoding="utf-8")
    cwd = os.getcwd()
    seen: list[Path] = []
    if ending is None:
        with tool.work_folder() as work:
            seen.append(work)
            assert work.name.startswith("agentprov-shots-") and (work.stat().st_mode & 0o777) == 0o700
            _populate(work, outside)
    else:
        with pytest.raises(type(ending)), tool.work_folder() as work:
            seen.append(work)
            _populate(work, outside)
            raise ending
    assert not seen[0].exists() and not seen[0].is_symlink()
    assert (outside / "keep.txt").read_text(encoding="utf-8") == "kept"  # the symlink was unlinked, not followed
    assert os.getcwd() == cwd


def test_main_removes_the_work_folder_on_a_guard_refusal(tmp_path: Path, monkeypatch: Any) -> None:
    tool = _tool()
    seen: list[Path] = []

    def refuse(work: Path, out: Path, names: list[str]) -> int:
        seen.append(work)
        _populate(work, tmp_path)
        raise SystemExit(1)  # capture() exits 1 when the leak guard refuses an image

    monkeypatch.setattr(tool, "_run", refuse)
    cwd = os.getcwd()
    with pytest.raises(SystemExit):
        tool.main(["screenshots.py", str(tmp_path / "out"), next(iter(tool.SCENES))])
    assert seen and not seen[0].exists() and os.getcwd() == cwd
