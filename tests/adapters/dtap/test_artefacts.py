"""The ``dtap`` artefact catalogue against the safety net (docs/architecture D.16.12, D.15.3; sample check §9.1 b1).

Every mapped fixture is scanned with its SEM records and the shipped catalogues. The catalogue must account for every
finding, and an entry may claim a finding only through a rule, ``claims`` item or issue code of its own case: a seal
issue is claimed exactly by the entries that list its code, and a case the net cannot see (its detector rule is
``reserved``) claims nothing. Failures print ids and tokens only, never fixture content.
"""

from __future__ import annotations

from collections import defaultdict


from agentprov.aer.rules import load_catalogue as load_rules
from agentprov.artefacts import Finding, discover_catalogues, scan
from agentprov.artefacts.catalogue import load_catalogue

#: Entries whose case no field read by the safety net carries (ext, register or release scan): reserved detectors.
NOT_VISIBLE = {
    "dtap.art.naive_timestamp", "dtap.art.copy_duplicate", "dtap.art.secret_like_strings", "dtap.art.goal_text_appended",
    "dtap.art.claudesdk_unknown_result_name",
}  # fmt: skip
#: generic detector (and variant, or None for every variant) -> the one entry that classifies it for DTap.
ONLY_ENTRY = {
    ("sentinel_time", None): "dtap.art.event_times_not_recorded",
    ("accounting_unverifiable", "aer.acc.agent_calls_vs_assistant@1"): "dtap.art.derived_model_calls",
    ("provider_id_anomaly", "absent"): "dtap.art.no_call_ids",
    ("payload_not_reaching_agent", None): "dtap.art.payload_not_observed",
}


def _findings(mapped) -> dict[str, list[Finding]]:
    catalogues = discover_catalogues()
    return {fid: scan([*m.doc.records, m.doc.seal], catalogues, sem_records=m.sem.records) for fid, m in mapped.items()}


def _short(f: Finding) -> tuple[str, str]:
    return f.detector.removeprefix("artefact.generic."), f.variant


def test_every_finding_on_a_fixture_is_classified(mapped):
    unclaimed = [(fid, *_short(f), f.ids) for fid, fs in _findings(mapped).items() for f in fs if not f.classified]
    assert unclaimed == [], f"findings with no catalogue entry (triage needed): {unclaimed}"


def test_claims_are_specific_to_the_entry(mapped):
    entries = {e.id: e for e in load_catalogue("dtap").entries}
    by_issue: dict[str, set[str]] = defaultdict(set)
    for e in entries.values():
        for code in e.issues:
            by_issue[code].add(e.id)
    seen: set[tuple[str, str]] = set()
    for fid, findings in _findings(mapped).items():
        for f in findings:
            detector, variant = _short(f)
            seen.add((detector, variant))
            claimed = set(f.entries)
            assert not claimed & NOT_VISIBLE, (fid, detector, variant, sorted(claimed & NOT_VISIBLE))
            if detector == "seal_issue":  # exactly the entries recording the code: no claim through a shared rule
                assert claimed == by_issue[variant], (fid, variant, sorted(claimed))
            for (det, var), entry in ONLY_ENTRY.items():
                if detector == det and var in (None, variant):
                    assert claimed == {entry}, (fid, detector, variant, sorted(claimed))
            if detector == "harness_imposed_outcome":
                assert "dtap.art.harness_default_outcome" in claimed and "dtap.art.rerun_single_judge" not in claimed, fid
            if detector == "empty_execution":
                assert len(claimed & {"dtap.art.empty_trajectory", "dtap.art.judge_only_directory"}) == 1, (fid, sorted(claimed))
    # the fixtures exercise the cases the sample check found unclassified or wrongly claimed
    assert {("sentinel_time", "unknown_ambiguous"), ("sentinel_time", "unknown_not_recorded"),
            ("accounting_unverifiable", "aer.acc.agent_calls_vs_assistant@1"), ("provider_id_anomaly", "absent"),
            ("harness_imposed_outcome", "harness_default")} <= seen, sorted(seen)


def test_naive_timestamp_claims_no_run_of_its_own_or_any_other(mapped):
    """The zone is recorded only in ext.dtap.timestamp_zone: the time findings of naive and aware runs are identical, so
    the entry claims none of them (it claimed every run before the fix); its count comes from ext (D.16.12)."""
    zones: dict[str, str] = {}
    for fid, m in mapped.items():
        run = next((r for r in m.records if r.get("k") == "scope" and r.get("id") == "run"), {})
        zone = run.get("ext", {}).get("dtap", {}).get("timestamp_zone")
        if isinstance(zone, str):
            zones[fid] = zone
    assert {"none", "utc"} <= set(zones.values()), zones
    for fid, findings in _findings(mapped).items():
        times = [f for f in findings if f.detector.endswith(".sentinel_time")]
        assert all(f.entries == ("dtap.art.event_times_not_recorded",) for f in times), fid


def test_reserved_detectors_are_never_cited(mapped):
    """The five reserved rules name cases the net cannot see; no AER record, seal issue or SEM annotation cites them, and
    each is the detector of exactly one catalogue entry."""
    rules = load_rules("dtap", 1, package="agentprov.adapters.dtap").rules
    reserved = {rid for rid, rule in rules.items() if rule.status == "reserved"}
    assert reserved == {"dtap.timestamp_zone_none@1", "dtap.byte_identical_copy@1", "dtap.secret_like_string@1",
                        "dtap.goal_prefix_appended@1", "dtap.result_name_unknown@1"}
    assert all(not rules[r].citable for r in reserved)
    for fid, m in mapped.items():
        cited = {ref.split("#", 1)[0] for rec in m.records for ref in rec.get("rule", [])}
        cited |= {i["rule"].split("#", 1)[0] for i in m.issues}
        cited |= {r.split("#", 1)[0] for a in m.sem.annotations for r in a["rule"]}
        assert not cited & reserved, (fid, sorted(cited & reserved))
    detectors = {e.id: e.detector_rule for e in load_catalogue("dtap").entries}
    assert {e for e, r in detectors.items() if r in reserved} == NOT_VISIBLE
    assert sorted(r for r in detectors.values() if r in reserved) == sorted(reserved)
