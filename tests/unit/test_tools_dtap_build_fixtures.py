"""``tools/dtap/build_fixtures.py``: a secret-pattern hit refuses the build before any file is written (audit AU-TRS-1).

The builder used to write every file into ``--out`` (by default the tracked ``tests/fixtures/dtap``) while scanning, so a
refused build left the secret-bearing file there next to a stale SOURCE.json. Synthetic trees only; no value is printed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
TOOLS = REPO / "tools" / "dtap"


@pytest.fixture(scope="module")
def bf():
    sys.path.insert(0, str(TOOLS))
    try:
        import build_fixtures

        yield build_fixtures
    finally:
        sys.path.remove(str(TOOLS))


def _tree(tmp_path: Path, bf, monkeypatch, judge: bytes) -> list[str]:
    census = tmp_path / "census.json"
    census.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(bf, "CENSUS", census)
    runs, tasks, out = tmp_path / "runs", tmp_path / "tasks", tmp_path / "fixtures" / "dtap"
    for directory, _purpose in bf.EXTRA.values():
        (runs / directory).mkdir(parents=True)
    first = sorted(d for d, _ in bf.EXTRA.values())[0]
    (runs / first / "judge_result.json").write_bytes(judge)
    tasks.mkdir()
    return ["--runs", str(runs), "--tasks", str(tasks), "--out", str(out)]


def test_a_secret_hit_refuses_the_build_and_writes_nothing(bf, tmp_path, monkeypatch, capsys) -> None:
    secret = b'{"note": "sk-' + b"A" * 24 + b'"}'
    argv = _tree(tmp_path, bf, monkeypatch, secret)
    assert bf.main(argv) == 1
    assert json.loads(capsys.readouterr().err) == {"refused_secret_pattern_hits": {"openai_sk": 1}}
    assert not (tmp_path / "fixtures").exists()


def test_a_clean_build_writes_the_files(bf, tmp_path, monkeypatch, capsys) -> None:
    argv = _tree(tmp_path, bf, monkeypatch, b'{"success": true}')
    assert bf.main(argv) == 0
    out = tmp_path / "fixtures" / "dtap"
    written = sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file())
    assert len(written) == 2 and written[0] == "SOURCE.json" and written[1].endswith("/judge_result.json")
    assert (tmp_path / "fixtures" / "LICENSES" / "DTap-Bench-ATTRIBUTION.txt").is_file()
