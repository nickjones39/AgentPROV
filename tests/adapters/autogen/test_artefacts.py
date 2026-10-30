"""The ``autogen`` artefact catalogue against the safety net (docs/architecture D.19.11, D.15.3).

Every mapped fixture run is scanned with its SEM records and the shipped catalogues. The catalogue must account for every
finding, and an entry claims a finding only through a rule, ``claims`` item or issue code of its own case. Failures print
ids and tokens only."""

from __future__ import annotations

from collections import defaultdict

from agentprov.aer.rules import load_catalogue as load_rules
from agentprov.artefacts import discover_catalogues, scan
from agentprov.artefacts.catalogue import check_references, load_catalogue

NOT_VISIBLE = {"autogen.art.non_run_rows", "autogen.art.errored_runs_set_aside"}


def _findings(mapped):
    catalogues = discover_catalogues()
    return {rid: scan([*m.doc.records, m.doc.seal], catalogues, sem_records=m.sem.records) for rid, m in mapped.items()}


def test_artefact_catalogue_validates_and_references_exist():
    cat = load_catalogue("autogen")
    assert check_references(cat) == [] and all(e.id.startswith("autogen.art.") for e in cat.entries)


def test_every_finding_on_a_fixture_is_classified(tool_arm):
    unclaimed = [(rid, f.detector, f.variant) for rid, fs in _findings(tool_arm).items() for f in fs if not f.classified]
    assert unclaimed == [], unclaimed


def test_claims_are_specific_to_the_entry(tool_arm):
    entries = {e.id: e for e in load_catalogue("autogen").entries}
    by_issue: dict[str, set[str]] = defaultdict(set)
    for e in entries.values():
        for code in e.issues:
            by_issue[code].add(e.id)
    for rid, findings in _findings(tool_arm).items():
        for f in findings:
            claimed = set(f.entries)
            assert not claimed & NOT_VISIBLE, (rid, f.detector)
            if f.detector.removeprefix("artefact.generic.") == "seal_issue":
                assert claimed == by_issue[f.variant], (rid, f.variant, sorted(claimed))


def test_reserved_detectors_name_the_invisible_entries():
    rules = load_rules("autogen", 1, package="agentprov.adapters.autogen").rules
    reserved = {rid for rid, rule in rules.items() if rule.status == "reserved"}
    detectors = {e.id: e.detector_rule for e in load_catalogue("autogen").entries}
    assert {e for e, r in detectors.items() if r in reserved} == NOT_VISIBLE
