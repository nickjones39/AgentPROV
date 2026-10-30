"""``tools/regen/compare.py``: SEM evidence-class transitions, twin pairs and closed-world expectations (D-359).

Synthetic two-corpus fixtures in ``tmp_path`` (one execution each); no real corpus is read.
"""

from __future__ import annotations

import importlib.util
import json
from collections import Counter
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[3] / "tools" / "regen" / "compare.py"
_spec = importlib.util.spec_from_file_location("regen_compare", _PATH)
assert _spec and _spec.loader
cmp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cmp)


def ann(aid: str, typ: str, target: str, ev: str, rule: str, premises: list[dict[str, str]] | None = None) -> dict:
    return {"k": "ann", "id": aid, "type": typ, "target": target, "ev": ev, "rule": [rule], "value": "v",
            "premises": premises if premises is not None else [{"id": target, "p": "/value"}]}


def test_sem_transitions_pairs_by_type_target_and_premises() -> None:
    old = [{"k": "sem"}, ann("a0", "outcome", "j0", "D", "u@1"), ann("a1", "outcome", "j1", "D", "s@1"),
           ann("a2", "integrity", "m0#0", "I", "i@1"), ann("a3", "channel", "t0", "I", "c@1")]
    # a1 keeps its rule but turns I (premise propagation); a3 is removed; a new marker is added; ids may shift
    new = [{"k": "sem"}, ann("b0", "outcome", "j0", "D", "u@1"), ann("b9", "outcome", "j1", "I", "s@1"),
           ann("b2", "integrity", "m0#0", "I", "i@1"), ann("b4", "injection_marker", "t1", "D", "m@1")]
    assert cmp.sem_transitions(old, new) == Counter({"outcome D->I": 1, "channel I->": 1, "injection_marker ->D": 1})


def test_sem_transitions_same_class_pairs_first_within_a_key() -> None:
    p = [{"id": "fx0", "p": "/kind"}]
    old = [ann("a0", "integrity", "fx0", "I", "r@1", p), ann("a1", "integrity", "fx0", "D", "r@1", p)]
    new = [ann("b0", "integrity", "fx0", "I", "r@1", p), ann("b1", "integrity", "fx0", "I", "r@1", p)]
    assert cmp.sem_transitions(old, new) == Counter({"integrity D->I": 1})
    assert cmp.sem_transitions(old, old) == Counter()


def test_twin_pairs_both_directions() -> None:
    ex = Counter({"x.a@1": 5, "x.a_unverified@1": 5, "x.b@1": 3, "x.b_unverified@1": 3, "x.c_unverified@1": 2})
    net = Counter({"x.a@1": -9, "x.a_unverified@1": 9, "x.b@1": 4, "x.b_unverified@1": -4, "x.c_unverified@1": 2})
    assert cmp.twin_pairs(ex, net) == {"x.a@1 -> x.a_unverified@1": 5, "x.b_unverified@1 -> x.b@1": 3}


def _summary(**kw) -> dict:
    base = {"aer_pointers": {}, "completeness": {}, "status": {}, "executions_changed": {}, "rule_citations_changed": {},
            "sem_ev_transitions": {}, "rule_twin_pairs": {}}
    base.update(kw)
    return base


def test_closed_world_keys_report_unlisted_and_missing() -> None:
    s = _summary(sem_ev_transitions={"outcome D->I": 369, "outcome ->D": 2})
    assert cmp.check(s, {"sem_ev_transitions": {"outcome D->I": 369, "outcome ->D": 2}}) == []
    out = cmp.check(s, {"sem_ev_transitions": {"outcome D->I": 369, "injection_marker D->I": 7}})
    assert out == ["sem_ev_transitions injection_marker D->I: expected 7, observed 0",
                   "sem_ev_transitions outcome ->D: unlisted 0, observed 2"]
    assert cmp.check(s, {"sem_ev_transitions": {}}) == ["sem_ev_transitions outcome ->D: unlisted 0, observed 2",
                                                        "sem_ev_transitions outcome D->I: unlisted 0, observed 369"]


def test_absent_closed_world_key_is_not_checked_and_open_world_keys_stay_open() -> None:
    s = _summary(completeness={"a->b": 3, "c->d": 1}, sem_ev_transitions={"outcome D->I": 1},
                 rule_twin_pairs={"r@1 -> r_unverified@1": 4})
    assert cmp.check(s, {"completeness": {"a->b": 3}}) == []
    assert cmp.check(s, {"rule_twin_pairs": {}}) == ["rule_twin_pairs r@1 -> r_unverified@1: unlisted 0, observed 4"]


def _corpus(root: Path, aer: list[dict], sem: list[dict], digest: str) -> None:
    (root / "aer").mkdir(parents=True)
    (root / "sem").mkdir()
    (root / "aer" / "ex_a.aer.jsonl").write_text("".join(json.dumps(r) + "\n" for r in aer), encoding="utf-8")
    (root / "sem" / "ex_a.sem.jsonl").write_text("".join(json.dumps(r) + "\n" for r in sem), encoding="utf-8")
    row = {"ex": "ex_a", "completeness": "unverifiable", "status": "ok", "issues": [],
           "digests": {"aer": f"aer-{digest}", "sem": {"p": f"sem-{digest}"}, "prov": {}},
           "paths": {"aer": "aer/ex_a.aer.jsonl", "sem": {"p": "sem/ex_a.sem.jsonl"}, "prov": {}}}
    (root / "executions.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    (root / "corpus.json").write_text(json.dumps({"corpus_id": "t"}), encoding="utf-8")


@pytest.mark.parametrize("listed, code", [(True, 0), (False, 1)])
def test_end_to_end_report_and_exit(tmp_path: Path, listed: bool, code: int) -> None:
    j_old = {"k": "judgement", "id": "j1", "rule": ["x.checker@1#/origin"]}
    j_new = {"k": "judgement", "id": "j1", "rule": ["x.checker_unverified@1#/origin"]}
    _corpus(tmp_path / "old", [{"k": "header"}, j_old], [{"k": "sem"}, ann("a1", "outcome", "j1", "D", "s@1")], "1")
    _corpus(tmp_path / "new", [{"k": "header"}, j_new], [{"k": "sem"}, ann("a1", "outcome", "j1", "I", "s@1")], "2")
    expect = {"sem_ev_transitions": {"outcome D->I": 1},
              "rule_twin_pairs": {"x.checker@1 -> x.checker_unverified@1": 1} if listed else {}}
    (tmp_path / "expect.json").write_text(json.dumps(expect), encoding="utf-8")
    report = tmp_path / "report.json"
    rc = cmp.main(["--old", str(tmp_path / "old"), "--new", str(tmp_path / "new"), "--report", str(report),
                   "--expect", str(tmp_path / "expect.json"), "--jobs", "1"])
    out = json.loads(report.read_text(encoding="utf-8"))
    assert out["sem_ev_transitions"] == {"outcome D->I": 1}
    assert out["rule_twin_pairs"] == {"x.checker@1 -> x.checker_unverified@1": 1}
    assert rc == code
    assert len(out["mismatches"]) == (0 if listed else 1)
