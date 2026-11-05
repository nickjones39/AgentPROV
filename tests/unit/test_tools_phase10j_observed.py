"""``tools/agentdojo/phase10j_profiles.py observed`` keeps the counts it does not re-measure (audit AU-TRS-2).

``write_observed`` rebuilt each quirk's ``observed`` table from the ``--report`` parts only, so re-measuring one part of a
multi-part profile (kavach-agentdojo: main, nav-fixer2, rearch-forcedformat-fix) deleted the other parts' declared
counts, and a quirk the report did not measure became ``part = {  }``. Synthetic profile snippet in tmp_path only.
"""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "agentdojo"))

import phase10j_profiles  # noqa: E402

PROFILE = """[[family.agentdojo.quirk]]
id = "agentdojo.benign_security_constant"
observed = { main = { files = 13, origin_rule_applied = 12 }, nav-fixer2 = { files = 98, origin_rule_applied = 95 } }

[[family.agentdojo.quirk]]
id = "agentdojo.dos_security_not_utility"
observed = { main = { files = 2 }, nav-fixer2 = { files = 5 } }

[[family.agentdojo.quirk]]
id = "agentdojo.incomplete_run"
"""


def _observed(path: Path) -> dict[str, object]:
    return {q["id"]: q.get("observed") for q in tomllib.loads(path.read_text())["family"]["agentdojo"]["quirk"]}


def test_re_measuring_one_part_keeps_the_other_parts_and_unmeasured_quirks(tmp_path) -> None:
    profile = tmp_path / "p.profile.toml"
    profile.write_text(PROFILE)
    report = tmp_path / "main.census.json"
    report.write_text(json.dumps({"measured": {"agentdojo.benign_security_constant": {"files": 14, "origin_rule_applied": 11}}}))
    phase10j_profiles.write_observed(profile, {"main": report})
    assert _observed(profile) == {
        "agentdojo.benign_security_constant": {"main": {"files": 14, "origin_rule_applied": 11},
                                               "nav-fixer2": {"files": 98, "origin_rule_applied": 95}},
        "agentdojo.dos_security_not_utility": {"main": {"files": 2}, "nav-fixer2": {"files": 5}},
        "agentdojo.incomplete_run": None,
    }


def test_a_new_part_is_added_beside_the_declared_ones(tmp_path) -> None:
    profile = tmp_path / "p.profile.toml"
    profile.write_text(PROFILE)
    report = tmp_path / "r.census.json"
    report.write_text(json.dumps({"measured": {"agentdojo.incomplete_run": {"files": 3, "null_outcome_files": 1, "x": 9}}}))
    phase10j_profiles.write_observed(profile, {"rearch-forcedformat-fix": report})
    observed = _observed(profile)
    assert observed["agentdojo.incomplete_run"] == {"rearch-forcedformat-fix": {"files": 3, "null_outcome_files": 1}}
    assert observed["agentdojo.dos_security_not_utility"] == {"main": {"files": 2}, "nav-fixer2": {"files": 5}}
