"""``tools/regen/tree_compare.py`` (D-358 byte comparison) on synthetic trees in ``tmp_path``: a comparison that sees
nothing, cannot read an entry or meets a symlink must not pass vacuously (AU-TRG-2)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[3] / "tools" / "regen" / "tree_compare.py"


def _compare(old: Path, new: Path, tmp_path: Path) -> tuple[int, dict | None]:
    report = tmp_path / "report.json"
    report.unlink(missing_ok=True)
    proc = subprocess.run([sys.executable, "-I", str(TOOL), str(old), str(new), "--report", str(report)],
                          capture_output=True, text=True, timeout=60)
    return proc.returncode, json.loads(report.read_text(encoding="utf-8")) if report.exists() else None


def _tree(root: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    return root


def test_identical_trees_pass_and_a_changed_file_fails(tmp_path: Path) -> None:
    a = _tree(tmp_path / "a", {"corpus.json": "{}", "aer/x.aer.jsonl": "1\n"})
    b = _tree(tmp_path / "b", {"corpus.json": "{}", "aer/x.aer.jsonl": "1\n"})
    rc, report = _compare(a, b, tmp_path)
    assert rc == 0 and report and report["identical"] == 2
    (b / "aer/x.aer.jsonl").write_text("2\n", encoding="utf-8")
    assert _compare(a, b, tmp_path)[0] == 1


def test_missing_roots_are_refused(tmp_path: Path) -> None:
    rc, report = _compare(tmp_path / "missing1", tmp_path / "missing2", tmp_path)
    assert rc == 2 and report is None
    a = _tree(tmp_path / "a", {"corpus.json": "{}"})
    assert _compare(a, tmp_path / "missing2", tmp_path)[0] == 2


def test_two_empty_trees_do_not_pass(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    assert _compare(tmp_path / "a", tmp_path / "b", tmp_path)[0] == 1


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privileges on Windows")
def test_symlinks_are_compared_by_target_and_never_followed(tmp_path: Path) -> None:
    a = _tree(tmp_path / "a", {"corpus.json": "{}", "t1": "same", "t2": "same"})
    b = _tree(tmp_path / "b", {"corpus.json": "{}", "t1": "same", "t2": "same"})
    (tmp_path / "d1").mkdir()
    (tmp_path / "d2").mkdir()
    os.symlink("t1", a / "lf")
    os.symlink("t2", b / "lf")
    rc, report = _compare(a, b, tmp_path)
    assert rc == 1 and report and report["first_differ"] == ["lf"]
    # a symlink to a directory is listed (os.walk puts it among the directories), not skipped
    (b / "lf").unlink()
    os.symlink("t1", b / "lf")
    os.symlink(tmp_path / "d1", a / "ld")
    os.symlink(tmp_path / "d2", b / "ld")
    rc, report = _compare(a, b, tmp_path)
    assert rc == 1 and report and report["first_differ"] == ["ld"]
    (b / "ld").unlink()
    rc, report = _compare(a, b, tmp_path)
    assert rc == 1 and report and report["first_only_old"] == ["ld"]
    os.symlink(tmp_path / "d1", b / "ld")
    assert _compare(a, b, tmp_path)[0] == 0


@pytest.mark.skipif(sys.platform == "win32" or (hasattr(os, "geteuid") and os.geteuid() == 0),
                    reason="POSIX permissions; root reads everything")
def test_an_unreadable_directory_is_an_error(tmp_path: Path) -> None:
    a = _tree(tmp_path / "a", {"corpus.json": "{}", "x/f": "1"})
    b = _tree(tmp_path / "b", {"corpus.json": "{}", "x/f": "2"})
    (a / "x").chmod(0)
    (b / "x").chmod(0)
    try:
        rc, report = _compare(a, b, tmp_path)
    finally:
        (a / "x").chmod(0o755)
        (b / "x").chmod(0o755)
    assert rc == 2 and report is None
