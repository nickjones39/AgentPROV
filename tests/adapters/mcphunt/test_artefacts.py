"""The ``mcphunt`` artefact catalogue against the safety net (docs/architecture D.21.11, D.15.3).

Every mapped fixture is scanned with its SEM records and the shipped catalogues. The catalogue must account for every
finding, and an entry claims a finding only through a rule, ``claims`` item or issue code of its own case. Failures print
ids and tokens only, never fixture content."""

from __future__ import annotations

from collections import defaultdict

from agentprov.aer.rules import load_catalogue as load_rules
from agentprov.artefacts import Finding, discover_catalogues, scan
from agentprov.artefacts.catalogue import check_references, load_catalogue

NOT_VISIBLE = {"mcphunt.art.non_trace_members", "mcphunt.art.oversized_traces"}


def _findings(mapped) -> dict[str, list[Finding]]:
    catalogues = discover_catalogues()
    return {crit: scan([*m.doc.records, m.doc.seal], catalogues, sem_records=m.sem.records) for crit, m in mapped.items()}


def test_artefact_catalogue_validates_and_references_exist():
    cat = load_catalogue("mcphunt")
    assert check_references(cat) == [] and all(e.id.startswith("mcphunt.art.") for e in cat.entries)


def test_every_finding_on_a_fixture_is_classified(mapped):
    unclaimed = [(crit, f.detector, f.variant, f.ids) for crit, fs in _findings(mapped).items() for f in fs if not f.classified]
    assert unclaimed == [], unclaimed


def test_claims_are_specific_to_the_entry(mapped):
    entries = {e.id: e for e in load_catalogue("mcphunt").entries}
    by_issue: dict[str, set[str]] = defaultdict(set)
    for e in entries.values():
        for code in e.issues:
            by_issue[code].add(e.id)
    seen: set[tuple[str, str]] = set()
    for crit, findings in _findings(mapped).items():
        for f in findings:
            detector = f.detector.removeprefix("artefact.generic.")
            seen.add((detector, f.variant))
            claimed = set(f.entries)
            assert not claimed & NOT_VISIBLE, (crit, detector, sorted(claimed & NOT_VISIBLE))
            if detector == "seal_issue":
                assert claimed == by_issue[f.variant], (crit, f.variant, sorted(claimed))
    assert {("sentinel_time", "unknown_ambiguous"), ("seal_issue", "incomplete_run")} <= seen, sorted(seen)


def test_reserved_detectors_are_never_cited(mapped):
    rules = load_rules("mcphunt", 1, package="agentprov.adapters.mcphunt").rules
    reserved = {rid for rid, rule in rules.items() if rule.status == "reserved"}
    assert reserved == {"mcphunt.non_trace_member@1", "mcphunt.oversized_trace@1"}
    assert all(not rules[r].citable for r in reserved)
    for crit, m in mapped.items():
        cited = {ref.split("#", 1)[0] for rec in m.records for ref in rec.get("rule", [])}
        cited |= {i["rule"].split("#", 1)[0] for i in m.issues}
        cited |= {r.split("#", 1)[0] for a in m.sem.annotations for r in a["rule"]}
        assert not cited & reserved, (crit, sorted(cited & reserved))
    detectors = {e.id: e.detector_rule for e in load_catalogue("mcphunt").entries}
    assert {e for e, r in detectors.items() if r in reserved} == NOT_VISIBLE
