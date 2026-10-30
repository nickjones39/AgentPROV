"""The recorded full-snapshot imports behind the registry's ``supported`` statuses (D.3.2 rule 1; HON-10).

The reports in ``docs/reports/`` are written by ``tools/import_report.py`` from local runs of ``agentprov import`` (the
corpora are outside the repository). This test reads only the committed numbers: a part may be ``supported`` only while
its report shows the full pinned snapshot sealed with zero degenerate or failed units, every AER valid, every derivation
passing tier 4 and recomputing byte-identically, and a byte-identical second import.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentprov.adapters.registry import get_source

REPORTS = Path(__file__).resolve().parents[2] / "docs" / "reports"

#: (source, part) -> (report, executions, candidates)
GATES = {
    ("agentdojo", "2024-06"): ("agentdojo/import-cli-2024-06.json", 18_241, 18_241),
    ("adprov-v1", "release"): ("adprov/import-cli-release.json", 17_664, 17_664),
    ("agent-security-tools-survey", "agentharm"): ("inspect/import-cli-agentharm.json", 1_056, 6),
}


@pytest.mark.parametrize(("key", "gate"), sorted(GATES.items()), ids=[f"{s}:{p}" for s, p in sorted(GATES)])
def test_a_supported_part_has_a_passing_full_snapshot_report(key, gate):
    source, part = key
    path, executions, candidates = gate
    capability = {c.part: c for c in get_source(source).capabilities}[part]
    if capability.import_status != "supported":
        pytest.skip(f"{source} · {part} is {capability.import_status}: no gate is claimed")
    report = json.loads((REPORTS / path).read_text(encoding="utf-8"))
    counters = report["cli"]["counters"]
    assert report["cli"]["exit_code"] == 0 and report["corpus"]["partial"] is False
    assert counters["seen"] == candidates and counters["mapped"] == report["executions"] == executions
    assert counters["degenerate"] == counters["failed"] == counters["registered"] == 0
    assert report["aer"]["digest_ok"] == report["aer"]["validator_pass"] == executions
    assert report["prov"]["derived"] == report["prov"]["validation_pass"] == report["prov"]["recompute_identical"] == executions
    assert report["prov"]["failed_or_skipped_checks"] == {}
    assert all(item["equal"] for item in report.get("comparison", {}).get("keys", {}).values())
    assert report["determinism"]["result"]["all_equal"] is True
    assert report["determinism"]["result"]["whole_tree"]["identical"] is True
    assert path in str(capability.caveat)


def test_the_survey_report_matches_the_d95_record_and_the_pinned_logs():
    report = json.loads((REPORTS / "inspect" / "import-cli-agentharm.json").read_text(encoding="utf-8"))
    assert report["pinned_snapshot_check"]["all_match"] is True
    expected = report["expected_d95"]
    assert report["seal_issues_by_code"] == expected["issues"] and report["accounting"] == expected["accounting"]
    assert report["executions"] == expected["samples"]
