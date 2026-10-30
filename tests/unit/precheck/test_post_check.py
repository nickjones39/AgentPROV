"""The post-check's read-only measures (``tools/precheck/post_check.py``) on synthetic trees: the input and output
guards (stored working corpora and pre-check scratch only; never an output inside ``corpora/``), the index comparison
(``ids``) and the scratch-to-stored tie (``tie``)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

TOOLS = Path(__file__).resolve().parents[3] / "tools" / "precheck"


@pytest.fixture(scope="module")
def pc():
    sys.path.insert(0, str(TOOLS))
    try:
        import post_check

        yield post_check
    finally:
        sys.path.remove(str(TOOLS))


def _row(ex: str, *, completeness: str = "verified_complete", aer: str = "a", issues: tuple[str, ...] = ()) -> dict[str, Any]:
    return {"ex": ex, "status": "ok", "completeness": completeness, "unit": "agent_execution", "execution_observed": True,
            "issues": list(issues), "raw": [{"role": "primary", "sha256": "0" * 64, "included": True}],
            "digests": {"aer": aer, "sem": {"p@1": "s"}, "prov": {"agentprov-prov/0.1": {"core": "p"}}, "validation": "v"}}


def _corpus(root: Path, rows: list[dict[str, Any]], stages: list[dict[str, Any]] | None = None) -> Path:
    root.mkdir(parents=True)
    (root / "corpus.json").write_text("{}", encoding="utf-8")
    (root / "executions.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    (root / "derivation.json").write_text(json.dumps({"stages": stages or [{"stage": "aer", "engine_code_sha256": "e"}]}),
                                          encoding="utf-8")
    return root


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("AGENTPROV_HOME", str(tmp_path))
    monkeypatch.setenv("AGENTPROV_PRECHECK_ROOT", str(tmp_path / "migration-work" / "precheck"))
    return tmp_path


def test_guards(pc, home: Path) -> None:
    stored = _corpus(home / "corpora" / "c-rg1.partial", [])
    assert pc.guard_input(stored) == stored
    with pytest.raises(SystemExit):
        pc.guard_input(_corpus(home / "corpora" / "sealed", []))  # a sealed corpus (no .partial) is not an input
    with pytest.raises(SystemExit):
        pc.guard_input(_corpus(home / "elsewhere" / "c.partial", []))
    with pytest.raises(SystemExit):
        pc.guard_out(stored / "x.json")
    scratch = _corpus(home / "migration-work" / "precheck" / "c" / "l2-head.partial", [])
    assert pc.guard_input(scratch) == scratch


def test_ids_counts_transitions_and_net_issues(pc, home: Path) -> None:
    old = _corpus(home / "corpora" / "c-p10.pre-regen.partial",
                  [_row("ex_a"), _row("ex_b", issues=("x",)), _row("ex_c")])  # fmt: skip
    new = _corpus(home / "corpora" / "c-rg1.partial",
                  [_row("ex_a"), _row("ex_b", completeness="unverifiable", aer="b", issues=("y", "y")), _row("ex_d")])
    out = pc.ids(old, new)
    assert out["executions"] == {"old": 3, "new": 3, "common": 2, "only_old": 1, "only_new": 1}
    assert out["transitions"]["completeness"] == {"verified_complete->unverifiable": 1,
                                                  "verified_complete->verified_complete": 1}
    assert out["stage_digests_changed"] == {"aer": 1, "prov": 0, "sem": 0, "validation": 0}
    assert out["issues"]["net"] == {"x": -1, "y": 2} and out["raw_refs_changed"] == 0


def test_tie_compares_every_stage_digest(pc, home: Path) -> None:
    stored = _corpus(home / "corpora" / "c-rg1.partial", [_row("ex_a"), _row("ex_b"), _row("ex_c")])
    scratch = _corpus(home / "migration-work" / "precheck" / "c" / "post-head.partial",
                      [_row("ex_a"), _row("ex_b", aer="other"), _row("ex_z")],
                      stages=[{"stage": "aer", "engine_code_sha256": "e"}, {"stage": "sem", "engine_code_sha256": "f"}])
    out = pc.tie(scratch, stored)
    assert out["executions"] == {"scratch": 3, "in_stored": 2, "missing_in_stored": 1, "all_digests_equal": 1,
                                 "differ_by_stage": {"aer": 1}}
    assert out["stage_code_equal"] == {"aer": True, "sem": False}
    assert out["fn_digest_equal"] == {"aer": True, "sem": True} and out["lockfile_equal"] is True


def test_area(pc) -> None:
    assert pc._area("raw/objects/ab/abcdef") == "raw-object"
    assert pc._area("aer/00/ex_x.aer.json") == "aer" and pc._area("executions.jsonl") == "top-level"


def test_triage_context_helpers(pc) -> None:
    data = b'{"error": "Traceback: /home/x/miniconda3/lib/python3.12/site-packages/a.py", "args": {"path": "/home/x/Documents/f"}}'
    assert pc._json_key(data, data.index(b"/home/")) == "error"
    assert pc._json_key(data, data.rindex(b"/home/")) == "path"
    assert pc._tail_class(b"/miniconda3/lib/python3.12/site-packages/a.py") == "toolchain"
    assert pc._tail_class(b"/Documents/report.txt") == "user_dirs" and pc._tail_class(b"/notes.txt") == "other"
