"""Full import of the pinned ``2024-06`` snapshot and gate R in full (J.2.6, J.4.2-J.4.3; D.6.10 item 3; PQ phase 6).

Local only (marker ``full_corpus``): needs the bare, extraction-free object store of ``ethz-spylab/agentdojo`` at
``c274885`` (``$AGENTPROV_UPSTREAM_CACHE``, default ``~/.agentprov/cache/git/github.com/ethz-spylab/agentdojo.git``) and,
for gate R, ``AGENTPROV_BASELINE_CORPUS`` (the AgentDojo-PROV checkout). A run takes about 25 minutes on an M2 Max with
10 workers; it executes ``tools/agentdojo/import_scan.py``, whose committed reports are ``docs/reports/agentdojo/``.
Nothing is printed except counts, codes and pinned paths.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "agentdojo"))

import import_scan  # noqa: E402

from agentprov.adapters.profiles import load_profile  # noqa: E402

pytestmark = pytest.mark.full_corpus

BLOBS, COMPARABLE, OUTCOME_ONLY = 18_241, 18_027, 207
MIXTRAL = {
    f"runs/mistralai_Mixtral-8x7B-Instruct-v0.1/{p}/none/none.json"
    for p in ("banking/user_task_0", "slack/user_task_0", "slack/user_task_1", "travel/user_task_0", "workspace/user_task_0",
              "workspace/user_task_1", "workspace/user_task_3")
}


@pytest.fixture(scope="module")
def reports(request: pytest.FixtureRequest) -> tuple[dict, dict]:
    if "full_corpus" not in str(request.config.getoption("markexpr")):
        pytest.skip("a full-scope run takes about 25 minutes: select it with `pytest -m full_corpus`")
    cache = Path(os.environ.get("AGENTPROV_UPSTREAM_CACHE", "") or import_scan.DEFAULT_CACHE)
    if cache.name != "agentdojo.git":
        cache = cache / "git" / "github.com" / "ethz-spylab" / "agentdojo.git"
    if not cache.is_dir():
        pytest.skip("the bare fetch cache of ethz-spylab/agentdojo is not present (U-07)")
    baseline = os.environ.get("AGENTPROV_BASELINE_CORPUS")
    result = import_scan.scan(cache, Path(baseline) if baseline else None, workers=int(os.environ.get("AGENTPROV_JOBS", "10")))
    return import_scan.summarise(result)


def test_every_pinned_blob_is_sealed_with_zero_crashes(reports):
    imp, _gate = reports
    assert imp["crashes"] == 0, imp["crash_rows"][:5]
    assert imp["blobs"] == imp["sealed"] == BLOBS and imp["degenerate"] == 0
    assert imp["variants"] == {"v0.k11": BLOBS}
    assert imp["outcome_only"] == OUTCOME_ONLY
    assert imp["mixtral"]["files"] == imp["mixtral"]["sealed"] == 7


def test_every_aer_validates_and_derives(reports):
    imp, _gate = reports
    assert imp["aer_validator"]["ok"] == imp["aer_validator"]["passed_release"] == BLOBS, imp["aer_validator"]["error_codes"]
    assert imp["prov"]["derived"] == imp["prov"]["validate_prov_ok"] == BLOBS, imp["prov"]["failed_checks"]


def test_profile_census_matches_the_observed_counts(reports):
    """D.6.10 item 3: every ``2024-06`` count the profile declares is what the full import observes."""
    imp, _gate = reports
    quirks = {q["id"]: q for q in load_profile("agentdojo-upstream").data["family"]["agentdojo"]["quirk"]}
    for quirk_id, counts in imp["census_2024_06"].items():
        declared = dict(quirks[quirk_id].get("observed", {}).get("2024-06", {}))
        assert declared == counts, quirk_id


def test_gate_r_full(reports):
    """R1/R2 over the 18,027 comparable pairs (the claim gate), R4 over the 207 EXCLUDED rows, R5 unmatched sets."""
    _imp, gate = reports
    if not gate["available"]:
        pytest.skip("AGENTPROV_BASELINE_CORPUS is not set to the AgentDojo-PROV checkout (gate R)")
    assert gate["comparable_pairs"] == gate["converted_transcripts"] == COMPARABLE
    assert gate["R4"] == {"excluded_rows": OUTCOME_ONLY, "outcome_only_aers": OUTCOME_ONLY, "equal": OUTCOME_ONLY,
                          "outcome_only_without_row": 0}
    assert set(gate["R5"]["native_only"]) == MIXTRAL and gate["R5"]["v1_only"] == []
    assert gate["R1"]["pass"] == gate["R2"]["pass"] == COMPARABLE, (gate["R1"]["categories"], gate["R2"]["categories"])
    assert gate["claim_gate"] == "pass"
