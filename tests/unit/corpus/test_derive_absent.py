"""BF-20 and CB-6: ``derive``/``recompute`` of a corpus with objects that are absent on purpose.

An object that ``purge`` removed (``raw/tombstones.jsonl``), that the sealed corpus withholds (``WITHHELD.json``) or that it
references only (``raw/REFERENCES.json``) is absent and accounted for. The derivation counts it, carries the executions that
need it as ``unverified`` (H.4.5(6)) and derives the rest. ``raw.object.missing`` stays the finding for an absence nothing
accounts for. ``NEW`` keeps ``raw/tombstones.jsonl`` (and ``raw/REFERENCES.json``) byte for byte, so the purge record survives.
The source is the small AgentDojo working corpus of ``derive_support``. Fixture text is never printed.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import derive_support as ds
import pytest

from agentprov.cli.main import main
from agentprov.testing import fs_guard


@pytest.fixture(autouse=True)
def _home(monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory) -> None:
    monkeypatch.setenv("AGENTPROV_HOME", str(tmp_path_factory.mktemp("home")))
    monkeypatch.delenv("AGENTPROV_PROGRESS", raising=False)


@pytest.fixture(scope="module")
def source(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return ds.agentdojo_corpus(tmp_path_factory.mktemp("absent-src"), count=2)


def _run(capsys: pytest.CaptureFixture[str], *argv: str, guard: Path | None = None) -> tuple[int, dict[str, Any], str]:
    capsys.readouterr()
    if guard is not None:
        with fs_guard.unchanged(guard):
            code = main([*argv, "--json", "--progress", "off"])
    else:
        code = main([*argv, "--json", "--progress", "off"])
    out, err = capsys.readouterr()
    lines = out.splitlines()
    return code, (json.loads(lines[-1]) if lines else {}), err


def _purged(capsys: pytest.CaptureFixture[str], source: Path, dest: Path) -> tuple[Path, str]:
    shutil.copytree(ds.partial(source), ds.partial(dest), symlinks=True)
    rows = ds.rows(ds.partial(dest))
    sha = rows[0]["raw"][0]["sha256"]
    code, _summary, err = _run(capsys, "purge", sha, "--reason", "secret", "--corpus", str(dest), "--yes")
    assert code == 0, err
    assert (ds.partial(dest) / "raw" / "tombstones.jsonl").is_file()
    return dest, rows[0]["ex"]


def test_cb6_recompute_of_a_purged_working_corpus_reports_the_purged_execution_unverified(capsys, source, tmp_path):
    src, _ex = _purged(capsys, source, tmp_path / "src")
    code, summary, err = _run(capsys, "recompute", "--corpus", str(src), "--dry-run", "--in-process",
                              "--stages", "sem,prov,validation", guard=ds.partial(src))
    assert code == 0 and "raw.object.missing" not in err, err
    counters = summary["counters"]
    assert counters["tombstoned_unavailable"] == 1 and counters["unverified"] == 1, counters
    assert counters["identical"] == 1 and counters["failed"] == counters["unexplained_change"] == 0


def test_cb6_a_full_recompute_of_a_purged_corpus_re_maps_the_rest(capsys, source, tmp_path):
    src, _ex = _purged(capsys, source, tmp_path / "src")
    code, summary, err = _run(capsys, "recompute", "--corpus", str(src), "--dry-run", "--in-process",
                              guard=ds.partial(src))
    assert code == 0 and "raw.object.missing" not in err, err
    counters = summary["counters"]
    assert counters["unverified"] == 1 and counters["identical"] == 1, counters


def test_cb6_derive_out_carries_the_tombstones_and_the_purged_row(capsys, source, tmp_path):
    src, ex = _purged(capsys, source, tmp_path / "src")
    out = tmp_path / "new"
    code, _summary, err = _run(capsys, "derive", "--corpus", str(src), "--out", str(out), "--in-process",
                               "--views", "transcript-v1", guard=ds.partial(src))
    assert code == 0, err
    tombstones = "raw/tombstones.jsonl"
    assert (ds.partial(out) / tombstones).read_bytes() == (ds.partial(src) / tombstones).read_bytes()
    assert ex in {row["ex"] for row in ds.rows(ds.partial(out))}
    code, summary, err = _run(capsys, "verify", "--corpus", str(out), "--level", "chain")
    assert code == 0 and summary["issues_by_code"].get("raw.tombstoned") == 1, (err, summary.get("issues_by_code"))


def test_an_absence_nothing_accounts_for_still_refuses(capsys, source, tmp_path):
    shutil.copytree(ds.partial(source), ds.partial(tmp_path / "src"), symlinks=True)
    src = tmp_path / "src"
    sha = ds.rows(ds.partial(src))[0]["raw"][0]["sha256"].removeprefix("sha256:")
    shard = ds.partial(src) / "raw" / "objects" / sha[:2]
    stored = next(p for p in shard.iterdir() if p.name.startswith(sha))
    stored.chmod(0o644)
    stored.unlink()
    code, _summary, err = _run(capsys, "recompute", "--corpus", str(src), "--dry-run", "--in-process")
    assert code == 1 and "raw.object.missing" in err
