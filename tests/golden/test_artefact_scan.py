"""The artefact safety net over the 19 golden v1 AERs, with the shipped ``adprov`` catalogue (DoD phase 6; D.15.6, D.15.7).

Every golden pair is mapped to an AER (as gates A1/A2 do) and scanned. The shipped catalogue must account for every
finding: a finding that no entry claims fails the test with its detector, variant and locators, so a new anomaly is
triaged by a reviewed catalogue change (D.15.3) and never absorbed silently. The named cases pin the specific entries to
the golden traces that exhibit them. Failures print ids and tokens only, never trace content (G.8.1 item 5).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_v1_round_trip as v1  # noqa: E402

from agentprov.artefacts import Finding, discover_catalogues, scan, table  # noqa: E402


def _findings(pair: Any, tmp: Path) -> list[Finding]:
    _data, doc = v1._aer(pair, tmp)
    return scan([*doc.records, doc.seal], discover_catalogues())


@pytest.mark.parametrize("pair", v1._ids())
def test_every_finding_on_a_golden_trace_is_claimed_by_the_adprov_catalogue(pair: Any, tmp_path: Path):
    v1._require()
    found = _findings(pair, tmp_path)
    unclaimed = [(f.detector.rsplit(".", 1)[1], f.variant, f.ids) for f in found if not f.classified]
    assert unclaimed == [], f"{pair.id}: findings with no catalogue entry (triage needed): {unclaimed}"


@pytest.mark.parametrize("pair", v1._ids())
def test_the_scan_of_a_golden_trace_is_repeatable(pair: Any, tmp_path: Path):
    v1._require()
    first = _findings(pair, tmp_path)
    assert first == _findings(pair, tmp_path)


#: golden id -> artefact ids that the catalogue must report for that trace (a subset: more may be present).
EXPECTED: dict[str, set[str]] = {
    "R05": {"adprov.art.reported_calls_exceed"},  # the Gemini trace whose reported counts disagree (C.7.4)
    "R07": {"adprov.art.provider_call_ids", "adprov.art.timing_overwritten_by_id"},  # repeated tool-call id
    "C01": {"adprov.art.timing_stub", "adprov.art.benign_security_constant", "adprov.art.usage_absent"},
    "C04": {"adprov.art.dos_polarity"},
    "C06": {"adprov.art.run_error_imposed", "adprov.art.provider_call_ids"},  # run error plus absent call ids
    "C07": {"adprov.art.provider_call_ids"},  # Gemini empty-string ids
}


@pytest.mark.parametrize("pair_id", sorted(EXPECTED))
def test_named_golden_traces_exhibit_their_catalogue_entries(pair_id: str, tmp_path: Path):
    v1._require()
    pair = next((p for p in v1.PAIRS if p.id == pair_id), None)
    if pair is None:
        pytest.skip(f"golden pair {pair_id} not available")
    reported = {a for f in _findings(pair, tmp_path) for a in f.artefact_ids}
    assert EXPECTED[pair_id] <= reported, f"{pair_id}: missing {sorted(EXPECTED[pair_id] - reported)}"


def test_the_golden_table_has_no_unclassified_rows(tmp_path: Path):
    v1._require()
    findings = [f for pair in v1.PAIRS for f in _findings(pair, tmp_path)]
    rows = table(findings, n_executions=len(v1.PAIRS))
    assert rows and not [r.artefact_id for r in rows if r.artefact_id.startswith("artefact.unclassified.")]
    assert all(0 < (r.proportion or 0) <= 1 for r in rows)
