"""``tools/estimate/gen_estimate_priors.py``: which corpora it reads (a regenerated copy before a ``-p<N>`` one, never
two copies of one corpus, never a missing name) and the building commit it records for each (orchestrator
2026-10-23)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

TOOL = Path(__file__).resolve().parents[2] / "tools" / "estimate" / "gen_estimate_priors.py"
SHA = "5b1f6fdf" + "0" * 32


def _tool() -> ModuleType:
    spec = importlib.util.spec_from_file_location("gen_estimate_priors", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _corpora(root: Path, *names: str) -> Path:
    for name in names:
        (root / name / "aer").mkdir(parents=True)
        (root / name / "corpus.json").write_text(json.dumps({"corpus_id": name.split("-")[0]}), encoding="utf-8")
    return root


def test_the_default_prefers_the_newest_regenerated_copy(tmp_path: Path) -> None:
    g = _tool()
    root = _corpora(tmp_path, "x-p10.partial", "x-rg1.partial", "x-rg2.partial", "x.partial", "y-p9.partial",
                    "y.partial", "z.partial", "w-p10.pre-regen.partial")
    assert [p.name for p in g.choose(root, [])] == ["x-rg2.partial", "y-p9.partial", "z.partial"]


def test_named_corpora_are_used_exactly(tmp_path: Path) -> None:
    g = _tool()
    root = _corpora(tmp_path, "x-p10.partial", "x-rg1.partial", "y-rg1.partial")
    assert [p.name for p in g.choose(root, ["x-p10.partial", "y-rg1.partial"])] == ["x-p10.partial", "y-rg1.partial"]
    with pytest.raises(g.Refused, match="twice"):
        g.choose(root, ["x-p10.partial", "x-rg1.partial"])
    with pytest.raises(g.Refused, match="not a corpus"):
        g.choose(root, ["x-rg9.partial"])


def test_every_chosen_corpus_needs_its_building_commit(tmp_path: Path) -> None:
    g = _tool()
    chosen = g.choose(_corpora(tmp_path, "x-rg1.partial", "y-rg1.partial"), [])
    assert g.building_commits([f"x-rg1.partial={SHA}", "y-rg1.partial=abc1234"], chosen) == {
        "x-rg1.partial": SHA, "y-rg1.partial": "abc1234"}
    for pairs, why in (([f"x-rg1.partial={SHA}"], "no --corpus-commit"),
                       ([f"x-rg1.partial={SHA}", "y-rg1.partial=abc1234", f"q.partial={SHA}"], "not chosen"),
                       ([f"x-rg1.partial={SHA}", "y-rg1.partial=main"], "hex commit"),
                       ([f"x-rg1.partial{SHA}", "y-rg1.partial=abc1234"], "NAME=COMMIT")):
        with pytest.raises(g.Refused, match=why):
            g.building_commits(pairs, chosen)


def test_the_table_records_each_corpus_building_commit(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    g = _tool()
    root = _corpora(tmp_path / "corpora", "x-rg1.partial")
    out = tmp_path / "priors.json"
    base = ["--corpora-root", str(root), "--workers", "1", "--out", str(out)]
    assert g.main(base) == 2 and not out.exists() and "no --corpus-commit" in capsys.readouterr().err
    assert g.main([*base, "--corpus-commit", f"x-rg1.partial={SHA}"]) == 0
    (corpus,) = json.loads(out.read_text(encoding="utf-8"))["built_from"]["corpora"]
    assert corpus["name"] == "x-rg1.partial" and corpus["building_commit"] == SHA and corpus["corpus_id"] == "x"
