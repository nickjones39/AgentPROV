"""D-212 (aer/0.2) with D-430 (pre-round review P-1): recomputing an ``agentprov-corpus/0.1`` corpus with this build is a
drift report, never an upgrade (C.21 item 5). A re-map would write ``aer/0.2`` records into a corpus/0.2 corpus and
recomputed PROV states apv 0.2.0, so ``--out`` refuses before ``NEW.partial`` exists. A re-derivation of any stage
recomputes the whole sem/prov/validation group, so it is refused too."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_deferrals_part_a import two_snapshots  # noqa: E402, F401  (the fixture)

from agentprov.cli.main import main  # noqa: E402


def _as_v01(partial: Path) -> None:
    """Label the working tree as an agentprov-corpus/0.1 corpus (what every corpus imported before aer/0.2 says)."""
    manifest = json.loads((partial / "corpus.json").read_text("utf-8"))
    manifest["format"] = "agentprov-corpus/0.1"
    manifest["formats"] = {**manifest["formats"], "corpus": "agentprov-corpus/0.1", "aer": "aer/0.1"}
    (partial / "corpus.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _recompute(partial: Path, out: Path, stages: str, monkeypatch: pytest.MonkeyPatch, tmp: Path,
               capsys: pytest.CaptureFixture[str]) -> tuple[int, dict]:
    monkeypatch.setenv("AGENTPROV_HOME", str(tmp / "home"))
    capsys.readouterr()
    code = main(["recompute", "--corpus", str(partial), "--out", str(out), "--stages", stages, "--no-reuse",
                 "--in-process", "--json", "--progress", "off"])
    return code, json.loads(capsys.readouterr().out.splitlines()[-1])


def test_a_re_map_of_a_0_1_corpus_is_refused_not_upgraded(two_snapshots, tmp_path, monkeypatch, capsys):  # noqa: F811
    partial, _labels = two_snapshots
    _as_v01(partial)
    code, summary = _recompute(partial, tmp_path / "new", "aer,sem,prov,validation", monkeypatch, tmp_path, capsys)
    assert code == 4 and summary["refusal"]["status"] == "corpus.derive.version_drift"
    assert "corpus: format agentprov-corpus/0.1 recorded, agentprov-corpus/0.2 current" in summary["refusal"]["lines"]
    assert not (tmp_path / "new.partial").exists()


def test_a_sem_prov_re_derivation_of_a_0_1_corpus_is_refused(two_snapshots, tmp_path, monkeypatch, capsys):  # noqa: F811
    partial, _labels = two_snapshots
    _as_v01(partial)
    code, summary = _recompute(partial, tmp_path / "new", "sem,prov,validation", monkeypatch, tmp_path, capsys)
    assert code == 4 and any("prov: vocabulary apv 0.1.0 recorded" in line for line in summary["refusal"]["lines"])
    assert not (tmp_path / "new.partial").exists()


def test_a_validation_only_recompute_of_a_0_1_corpus_is_refused_too(two_snapshots, tmp_path, monkeypatch, capsys):  # noqa: F811
    """Any re-derivation recomputes the sem/prov/validation group (DerivePlan), so PROV is rebuilt under apv 0.2.0 as well:
    at this build every writing recompute of a corpus/0.1 corpus is a drift refusal (D-430)."""
    partial, _labels = two_snapshots
    _as_v01(partial)
    code, summary = _recompute(partial, tmp_path / "new", "validation", monkeypatch, tmp_path, capsys)
    assert code == 4 and summary["refusal"]["status"] == "corpus.derive.version_drift"
    assert not (tmp_path / "new.partial").exists()
