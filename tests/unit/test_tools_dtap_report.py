"""``tools/dtap/dtap_report.py`` re-run groups: one per task directory, not per judge digest (audit AU-TRS-3).

Byte-identical judge files occur in different DTap task directories (sample check c4). Keyed by the judge digest only, two
such re-run directories counted as one group and a resolved one hid an unresolved one. Synthetic corpus only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
TOOLS = REPO / "tools" / "dtap"


@pytest.fixture(scope="module")
def dr():
    sys.path.insert(0, str(TOOLS))
    try:
        import dtap_report

        yield dtap_report
    finally:
        sys.path.remove(str(TOOLS))


def test_byte_identical_judges_in_two_directories_are_two_groups(dr, tmp_path) -> None:
    (tmp_path / "aer").mkdir()
    judge = "a" * 64
    runs = [("ex_1", "finance", "1", True), ("ex_2", "finance", "1", True), ("ex_3", "legal", "7", False),
            ("ex_4", "legal", "7", False)]
    rows = []
    for ex, domain, task_dir, resolved in runs:
        facets = {"framework": "openaisdk", "model": "gpt-5.1", "domain": domain, "split": "malicious", "threat": "direct",
                  "risk_category": "x", "subcategory": None, "task_dir": task_dir, "file": f"{ex}.json"}
        head = {"k": "execution", "unit": "agent_execution", "ext": {"dtap": {
            "path_facets": facets, "join": {"status": "joined", "tier": "A"},
            "judge_link": {"method": "content" if resolved else "unresolved", "resolved": resolved, "group_size": 2,
                           "judge_sha256": judge}}}}
        (tmp_path / "aer" / f"{ex}.aer.jsonl").write_text(json.dumps(head) + "\n" + json.dumps({"k": "seal", "issues": []}) + "\n")
        rows.append({"ex": ex, "status": "ok", "paths": {"aer": f"aer/{ex}.aer.jsonl"}})
    (tmp_path / "executions.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    groups = dr.report(tmp_path)["rerun_groups"]
    assert groups == {"groups": 2, "resolved": 1, "unresolved": 1, "group_level_outcomes": {"judge_not_stored": 1}}
