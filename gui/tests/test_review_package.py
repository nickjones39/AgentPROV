"""GUI review GR-7: the Package preconditions show corpus.json 'partial' and 'release' as checked flags, never raw."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

_NL = chr(10)  # hostile values are built from fragments at runtime
_RLO = chr(0x202E)
_BEL = chr(7)


def _preconditions(tmp_path: Path, manifest: dict[str, Any]) -> list[str]:
    from agentprov_gui.ui.package import PackagePage

    work = tmp_path / "victim.partial"
    work.mkdir(parents=True, exist_ok=True)
    (work / "corpus.json").write_text(json.dumps({"format": "agentprov-corpus/0.1", "counts": {}, **manifest}))
    page = PackagePage(lambda spec: None, None)
    page.timer.stop()
    page.corpus.setText(str(work))
    page._show(0)
    shown = page.texts[0].toPlainText()
    return shown.split(_NL + _NL + "Dry run:")[0].split(_NL)


def test_hostile_partial_and_release_cannot_forge_lines(qapp: Any, tmp_path: Path) -> None:
    forged = "False (must be false)" + _NL + "writer's lock: none" + _NL + "interpreter advisory: none"
    lines = _preconditions(tmp_path, {"partial": forged, "release": "yes" + _RLO + "on" + _BEL})
    text = _NL.join(lines)
    assert _RLO not in text and _BEL not in text
    assert sum(line.startswith("writer's lock") for line in lines) == 1
    assert sum(line.startswith("interpreter advisory") for line in lines) == 1
    partial = [line for line in lines if line.startswith("partial:")]
    assert len(partial) == 1 and partial[0].startswith("partial: not a boolean (") and "not satisfied" in partial[0]
    release = [line for line in lines if line.startswith("release status:")]
    assert len(release) == 1 and release[0].startswith("release status: not a release record (")


def test_boolean_and_absent_flags(qapp: Any, tmp_path: Path) -> None:
    """F-13: ``release`` is the release record (status, created), never a flag; the release-mode requirement is the
    validation stage's mode in derivation.json."""
    lines = _preconditions(tmp_path / "a", {"partial": False, "release": {"created": None, "status": "dev"}})
    assert "partial: false (must be false)" in lines and "release status: dev (not released)" in lines
    assert not any("not a boolean" in line for line in lines if line.startswith("release"))
    assert any(line.startswith("validation mode: no validation stage recorded") for line in lines)
    lines = _preconditions(tmp_path / "b", {"partial": True})
    assert "partial: true (must be false; not satisfied)" in lines and "release status: absent" in lines
    lines = _preconditions(tmp_path / "s", {"release": {"created": "2026-10-22T00:00:00Z", "status": "sealed"}})
    assert "release status: sealed, created 2026-10-22T00:00:00Z" in lines
    lines = _preconditions(tmp_path / "c", {})
    assert "partial: absent (must be false; not satisfied)" in lines


@pytest.mark.parametrize(("mode", "expected"), [
    ("release", "validation mode: release (strict, as package needs)"),
    ("dev", "validation mode: dev (package needs strict validation; not satisfied)"),
])
def test_the_validation_mode_comes_from_derivation_json(qapp: Any, tmp_path: Path, mode: str, expected: str) -> None:
    work = tmp_path / "w" / "victim.partial"
    work.mkdir(parents=True)
    (work / "derivation.json").write_text(json.dumps({"format": "agentprov-derivation/0.1", "stages": [
        {"stage": "validation", "fn": "validate", "mode": mode}]}))
    lines = _preconditions(tmp_path / "w", {"partial": False, "release": {"created": None, "status": "dev"}})
    assert expected in lines
