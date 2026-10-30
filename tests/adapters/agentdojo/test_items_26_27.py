"""Regeneration-batch items 26 and 27 (routed from phase 9b, user-approved 2026-10-13): the D.15 entry for AgentDyn's
nondeterministic tools (R-9b-1) and the benchmark of a live AgentDyn cell read from the profile's suites map (R-9b-2 (a))."""

from __future__ import annotations

from typing import Any

import capture_support as cs
import pytest
from agentprov.aer.rules import load_catalogue

SUITE_BENCHMARK = "agentdyn.suite_benchmark@1"


def test_the_nondeterministic_tools_entry_and_its_rule():
    from agentprov.artefacts.catalogue import check_references, parse_catalogue

    rule = load_catalogue("agentdyn").get("agentdyn.nondeterministic_tool_state@1")
    assert rule is not None and rule.cls == "D"
    catalogue = parse_catalogue((cs.REPO / "src/agentprov/adapters/agentdojo/artefacts.toml").read_bytes(), family="agentdojo")
    entry = next(e for e in catalogue.entries if e.id == "agentdyn.art.nondeterministic_tools")
    assert (entry.cause, entry.handling_class, entry.detector_rule) == ("benchmark", "FO", "agentdyn.nondeterministic_tool_state@1")
    assert entry.manuscript and [str(p) for p in check_references(catalogue)] == []


def _cell(suite: str) -> dict[str, Any]:
    return {"benchmark": "agentdojo", "suite": suite, "task_id": "user_task_0", "attack_id": None,
            "attack_target_id": None, "defense_id": None, "attack_params": {}}


def _mapped(monkeypatch: pytest.MonkeyPatch, suite: str) -> Any:
    original = cs.start_data
    monkeypatch.setattr(cs, "start_data", lambda *a, **k: original(*a, **{**k, "cell": _cell(suite)}))
    m = cs.map_built(cs.c13_8_session(), profile_id="autodojo-live")
    report = m.validate()
    assert report.ok, [(f.code, f.pointer) for f in report.errors]
    return m


def test_a_live_agentdyn_cell_reads_its_benchmark_from_the_suites_map(monkeypatch):
    m = _mapped(monkeypatch, "shopping")
    head = m.header
    assert head["task"]["benchmark"] == "agentdyn" and head["ext"]["agentdojo"]["cell_benchmark"] == "agentdojo"
    assert head["evf"]["/task/benchmark"] == "D" and any(r.startswith(SUITE_BENCHMARK) for r in head["rule"])
    assert head["rules"]["agentdyn"] == 2


def test_a_live_agentdojo_cell_is_unchanged(monkeypatch):
    m = _mapped(monkeypatch, "banking")
    head = m.header
    assert head["task"]["benchmark"] == "agentdojo" and "ext" not in head and "agentdyn" not in head["rules"]
    assert "/task/benchmark" not in head.get("evf", {})


# ------------------------------------------------------------------------------------------------ item 27 (b)
def test_suites_3_adds_the_reviewed_agentdyn_tables_and_keeps_version_2():
    from agentprov.adapters.semantics_profiles import load_semantics_profile

    v2, v3 = load_semantics_profile("agentdojo.suites", 2), load_semantics_profile("agentdojo.suites", 3)
    assert {k: len(v) for k, v in v3.tables.reviewed.items() if k[0] == "agentdyn"} == \
        {("agentdyn", "shopping"): 39, ("agentdyn", "github"): 34, ("agentdyn", "dailylife"): 27}
    assert not [k for k in v2.tables.reviewed if k[0] == "agentdyn"]
    assert {k: v for k, v in v3.tables.reviewed.items() if k[0] != "agentdyn"} == dict(v2.tables.reviewed)


def test_a_live_agentdyn_tool_is_labelled_by_the_reviewed_table(monkeypatch):
    from agentprov.adapters.semantics_profiles import load_semantics_profile
    from agentprov.aer.reader import load_aer_bytes

    doc = load_aer_bytes(_mapped(monkeypatch, "shopping").data)
    bench = next(r for r in doc.of_kind("actor") if r.get("kind") == "benchmark")
    assert bench["ext"]["agentdojo"]["version_label_semantics"] == "label_not_suite_version"
    labels = {v: [a for a in load_semantics_profile("agentdojo.suites", v).annotate(doc) if a.type == "integrity"
                  and any("tool" in r for r in a.rule)] for v in (2, 3)}
    assert labels[2] and all(any(r.startswith("agentdojo.unknown_tool@1") for r in a.rule) for a in labels[2])
    assert labels[3] and all(any(r.startswith("agentdojo.reviewed_tool_label@1") for r in a.rule) for a in labels[3])
