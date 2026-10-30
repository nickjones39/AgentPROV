"""The ``credleak`` artefact catalogue (docs/architecture D.19.11, D.15.2): references and reserved detectors."""

from __future__ import annotations

from agentprov.aer.rules import load_catalogue as load_rules
from agentprov.artefacts.catalogue import check_references, load_catalogue


def test_artefact_catalogue_validates_and_references_exist():
    cat = load_catalogue("credleak")
    assert check_references(cat) == [] and len(cat.entries) == 10  # +5 wave-2 artefact scope (D-950)
    assert all(e.id.startswith("credleak.art.") for e in cat.entries)


def test_reserved_detectors_are_never_cited(mapped):
    """The reserved rules name cases no AER field carries (planted values handled at sealing, malformed tool names
    handled by SEM); no AER record, seal issue or SEM annotation cites them, and each detects exactly one entry."""
    rules = load_rules("credleak", 1, package="agentprov.adapters.credleak").rules
    reserved = {rid for rid, rule in rules.items() if rule.status == "reserved"}
    assert reserved == {"credleak.planted_credential@1", "credleak.malformed_tool_name@1"}
    assert all(not rules[r].citable for r in reserved)
    for runs in mapped.values():
        for m in runs:
            cited = {ref.split("#", 1)[0] for rec in m.records for ref in rec.get("rule", [])}
            cited |= {i["rule"].split("#", 1)[0] for i in m.issues if i.get("rule")}
            cited |= {r.split("#", 1)[0] for a in m.sem.annotations for r in a["rule"]}
            assert not cited & reserved
    detectors = sorted(e.detector_rule for e in load_catalogue("credleak").entries if e.detector_rule in reserved)
    assert detectors == sorted(reserved)
