"""A2 (build log entries 45 and 47): ``gui/tools/screenshots.py`` without OUT_DIR writes to a new temporary folder
outside the repository, and ``docs/images/gui/`` takes only the README's scenes. No scene is taken here (``_run`` is
replaced), so nothing is captured and the leak guard is not involved."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

from test_review_screenshot_guard import _tool


def _record(tool: Any, monkeypatch: pytest.MonkeyPatch) -> list[tuple[Path, list[str]]]:
    calls: list[tuple[Path, list[str]]] = []

    def run(_work: Path, out: Path, names: list[str]) -> int:
        calls.append((out, names))
        return 0

    monkeypatch.setattr(tool, "_run", run)
    return calls


def test_a_bare_run_writes_outside_the_repository(monkeypatch: pytest.MonkeyPatch,
                                                  capsys: pytest.CaptureFixture[str]) -> None:
    tool = _tool()
    calls = _record(tool, monkeypatch)
    assert tool.main(["screenshots.py"]) == 0
    (out, names), = calls
    try:
        assert out.is_dir() and out.name.startswith("agentprov-shots-out-") and not any(out.iterdir())
        assert not out.resolve().is_relative_to(tool.REPO.resolve())
        assert names == list(tool.SCENES)
        assert str(out) in capsys.readouterr().out
    finally:
        shutil.rmtree(out)


@pytest.mark.parametrize("scenes", [[], ["new-job"], ["viewer-graph", "viewer-tabs"]])
def test_the_readme_folder_refuses_other_scenes(monkeypatch: pytest.MonkeyPatch, scenes: list[str],
                                                capsys: pytest.CaptureFixture[str]) -> None:
    tool = _tool()
    calls = _record(tool, monkeypatch)
    assert tool.main(["screenshots.py", str(tool.README_OUT), *scenes]) == 2
    assert not calls and "keeps only agentprov-app, viewer-graph" in capsys.readouterr().err


@pytest.mark.parametrize("scenes", [["viewer-graph"], ["agentprov-app"], ["agentprov-app", "viewer-graph"]])
def test_the_readme_folder_takes_its_own_scenes(monkeypatch: pytest.MonkeyPatch, scenes: list[str]) -> None:
    tool = _tool()
    calls = _record(tool, monkeypatch)
    assert tool.main(["screenshots.py", str(tool.README_OUT), *scenes]) == 0
    assert calls == [(tool.README_OUT.resolve(), scenes)]


def test_another_folder_takes_every_scene(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    tool = _tool()
    calls = _record(tool, monkeypatch)
    assert tool.main(["screenshots.py", "--max-width", "1200", str(tmp_path / "guide")]) == 0
    assert calls == [((tmp_path / "guide").resolve(), list(tool.SCENES))]
