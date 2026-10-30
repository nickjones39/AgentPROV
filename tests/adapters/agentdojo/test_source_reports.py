"""The recorded full-snapshot imports behind the ``supported`` statuses of the phase-10 AgentDojo-family parts (D.3.2 rule 1;
HON-10; docs/architecture D.6.12 item 20, D.6.13, D.6.14, D.6.15).

The reports in ``docs/reports/{agentdojo,rope,agentdyn,mandate,survey}`` are written by ``tools/import_report.py`` from local
runs of ``agentprov import`` (the corpora are outside the repository). This test reads only the committed numbers: a part may
be ``supported`` only while its report shows the full pinned snapshot sealed with zero degenerate or failed units, every AER
valid, every derivation passing tier 4 and recomputing byte-identically, the pinned snapshot verified, the profile's census
reproduced, and the reproducibility evidence that exists stated as what it is. ``tests/adapters/test_import_reports.py`` holds
the gate for the phase-6 parts.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentprov.adapters.profiles import load_profile
from agentprov.adapters.registry import get_source

REPORTS = Path(__file__).resolve().parents[3] / "docs" / "reports"
#: Profiles changed by the regeneration batch after their reports were recorded: profile id -> (the profile digest the report
#: records, the batch item). Such a report describes the corpus as it stands until the user-approved regeneration
#: (docs/reports/analysis/regen-batch.md); the test then requires the recorded digest to be exactly the pre-batch one, and
#: the entry is removed when the corpus is regenerated and its report rewritten.
AWAITING_REGENERATION = {
    "agentdojo-upstream": ("a13b76ba7e224ff3ca71588010a23bf777601583e21b7d9a7cf71518359257fe", "item 3 (D-24 twins)"),
    "rope": ("a17aeb470fd3ebea282a4b290284314a81162aca13cd189a3821b7729ee3e16c", "item 3 (D-24 twins)"),
    "agentdyn": ("afa4090ecc3c19f81d58afd4850f99e4ae0fdc207af0d90db0a2dd5bca82bd94", "item 3 (D-24 twins)"),
    "mandate-agentdojo-eval": ("e5bcd8db43cfe74458bc52750d6913a7d362c8df9717b2766a1467cc8b0a9d45", "item 3 (D-24 twins)"),
    "survey-runs": ("db5cd1e79cd44f37fb11bd3074caa4e23b622cb704079786865f3bbcb8d76a76", "item 3 (D-24 twins)"),
}
_HEAD_VARIANTS = {"v0.k11": 24_914, "v1.k14": 11_764, "v1.k14.incomplete": 1}

#: (source, part) -> (report, executions, candidates, profile, variants, cross-checks against the investigation required)
GATES = {
    ("mandate-agentdojo-eval", "head"): ("mandate/import-cli-mandate.json", 396, 396, "mandate-agentdojo-eval", {"v1.k14": 396}, True),
    ("agent-security-tools-survey", "agentdojo-runs"): ("survey/import-cli-agentdojo-runs.json", 3_243, 3_243, "survey-runs", {"v1.k14": 3_243}, True),
    ("rope", "head"): ("rope/import-cli-rope.json", 10_791, 10_791, "rope", {"v1.k14": 10_789, "v1.k14.incomplete": 2}, False),
    ("agentdyn", "a"): ("agentdyn/import-cli-agentdyn.json", 38_281, 47_723, "agentdyn", {"v1.k14": 38_269, "v1.k14.incomplete": 12}, False),
    ("agentdojo", "head"): ("agentdojo/import-cli-head.json", 36_679, 36_679, "agentdojo-upstream", _HEAD_VARIANTS, False),
}


def _supported(source: str, part: str):
    capability = {c.part: c for c in get_source(source).capabilities}[part]
    if capability.import_status != "supported":
        pytest.skip(f"{source} · {part} is {capability.import_status}: no gate is claimed")
    return capability


@pytest.mark.parametrize(("key", "gate"), sorted(GATES.items()), ids=[f"{s}:{p}" for s, p in sorted(GATES)])
def test_a_supported_part_has_a_passing_full_snapshot_report(key, gate):
    source, part = key
    path, executions, candidates, profile_id, variants, cross_checks = gate
    capability = _supported(source, part)
    report = json.loads((REPORTS / path).read_text(encoding="utf-8"))
    counters = report["cli"]["counters"]
    assert report["cli"]["exit_code"] == 0 and report["corpus"]["partial"] is False
    recorded = report["corpus"]["profile"]["sha256"]
    pending = AWAITING_REGENERATION.get(profile_id)
    expected = pending[0] if pending is not None else load_profile(profile_id).sha256
    assert pending is None or pending[0] != load_profile(profile_id).sha256, "a regenerated report: drop its entry"
    assert report["corpus"]["profile"]["id"] == profile_id and recorded == "sha256:" + expected
    assert counters["seen"] == candidates and counters["mapped"] == report["executions"] == executions
    assert counters["degenerate"] == counters["failed"] == 0  # "registered" counts select.* rows of files not mapped (AgentDyn B and C)
    assert counters["annotated"] == counters["derived"] == counters["validated"] == executions
    assert report["aer"]["digest_ok"] == report["aer"]["validator_pass"] == executions and report["aer"]["validator_mode"] == ["release"]
    assert report["prov"]["derived"] == report["prov"]["validation_pass"] == report["prov"]["recompute_identical"] == executions
    assert report["prov"]["failed_or_skipped_checks"] == {}
    assert report["variants"] == variants and report["origin_kinds"] == {"git": executions}
    assert report["pinned_snapshot_check"]["all_match"] is True
    assert report["profile_census"]["differences"] == []
    if cross_checks:
        assert report["cross_checks"]["all_equal"] is True
    determinism = report["determinism"]
    if determinism["second_import"] in ("run", "run_on_pre_integration_code"):  # a second full import, compared whole
        assert determinism["result"]["all_equal"] is True and determinism["result"]["whole_tree"]["identical"] is True
    else:  # stated as not run, with the reason; never claimed
        assert determinism["second_import"] == "not_run" and determinism["reason"]
    assert path in str(capability.caveat) or "docs/reports/" + path in str(capability.caveat)


def test_the_mandate_report_matches_the_investigation_and_the_survey_report_its_own_figures():
    mandate = REPORTS / "mandate" / "import-cli-mandate.json"
    survey = REPORTS / "survey" / "import-cli-agentdojo-runs.json"
    if not mandate.is_file() or not survey.is_file():
        pytest.skip("the reports are not recorded yet")
    m = json.loads(mandate.read_text(encoding="utf-8"))
    census = m["profile_census"]["measured"]["agentdojo.mandate_decline"]
    assert census == {"allowed_inferred": 143, "declines": 240}
    assert m["prov"]["statements_by_rule"]["aprov.n_decision@1"] == 240  # one decision node per decline
    s = json.loads(survey.read_text(encoding="utf-8"))
    assert s["seal_issues_by_code"]["outcome_imposed_by_runner"] == 11 and s["files_by_seal_issue_code"]["unexecuted_tool_call"] == 48
    assert s["profile_census"]["measured"]["agentdojo.injection_task_as_user_task_prepass"] == {"files": 105}


def test_the_rope_q8_slice_reproduces_the_corrected_security_counts():
    """D.6.13 Q.8: 198 / 260 / 220 logs per correction, recorded versus recomputed ``security``, the AutoDojo slice."""
    path = REPORTS / "rope" / "rope-q8.json"
    if not path.is_file():
        pytest.skip("the ROPE Q.8 report is not recorded yet")
    q8 = json.loads(path.read_text(encoding="utf-8"))
    by_rule = q8["q8_corrections"]["by_rule"]
    assert (by_rule["slack_it5.logs"], by_rule["dailylife_it7.logs"], by_rule["github_it1.logs"]) == (198, 260, 220)
    assert (by_rule["slack_it5.recorded_true"], by_rule["slack_it5.recomputed_true"]) == (32, 0)
    assert (by_rule["dailylife_it7.recorded_true"], by_rule["dailylife_it7.recomputed_true"]) == (39, 22)
    assert (by_rule["github_it1.recorded_true"], by_rule["github_it1.recomputed_true"]) == (5, 0)
    assert q8["q8_corrections"]["recomputed_not_beside_a_recorded_security"] == 0
    assert q8["autodojo_slice"]["logs"] == 2_847 and q8["autodojo_slice"]["security_true"] == {"effective_true": 71, "recorded_true": 88}
    assert q8["units"] == {"agent_execution": 10_789, "outcome_only": 2} and q8["aer_files"] == 10_791


def test_the_head_report_records_the_history_fields():
    """D.6.12 item 20 and D.6.16: with the history index cached, every head AER carries the introducing commit's bound and the
    24,914 old-format logs an era; the counts equal D.6.16 item 9."""
    path = REPORTS / "agentdojo" / "import-cli-head.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    history = report["history_fields"]
    assert history["with_committed_no_later_than"] == history["with_introduced_in_commit"] == 36_679
    assert history["distinct_introducing_commits"] == 50 and history["earliest"].startswith("2024-06-02") and history["latest"].startswith("2025-07-25")
    assert sum(history["era"].values()) == 24_914 and history["era"]["pre_versioning|v1->v1.1"] == 14_182
    assert history["variant_by_era_presence"]["v0.k11|era"] == 24_914


def test_the_agentdyn_sem_fail_closed_counts_are_consistent():
    path = REPORTS / "agentdyn" / "sem-unknown-tools.json"
    if not path.is_file():
        pytest.skip("the AgentDyn SEM report is not recorded yet")
    sem = json.loads(path.read_text(encoding="utf-8"))
    assert sem["sem_files"] == 38_281
    assert sum(sem["unknown_tool_annotations_by_type"].values()) == sem["unknown_tool_annotations"]
    assert sem["unknown_tool_annotations"] <= sem["annotations"] and sem["files_with_unknown_tool_annotations"] <= sem["sem_files"]
