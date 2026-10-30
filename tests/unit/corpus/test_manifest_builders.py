"""The manifest builders (``agentprov.corpus.manifest``; H.2.3, H.2.9, H.2.12; D-33, D-40, D-41).

Counts are recomputed from the register (HL-T3 reconciliation): a selection exclusion is never a candidate, any other
``not_imported`` entry is; the snapshot origin is built from the recorded pin and refuses ``local``; the D-40 validation
summary and ``linkage_resolved_pct``; the D-41 duplicates summary; rule catalogue references.
"""

from __future__ import annotations

import pytest

from agentprov.corpus.manifest import (
    AerStats,
    ManifestError,
    corpus_counts,
    is_exclusion,
    linkage_resolved_pct,
    rule_catalogue_refs,
    snapshot_counts,
    snapshot_origin_from_pin,
    validation_summary,
)
from agentprov.corpus.register import RegisterEntry
from agentprov.raw.members import MemberRow

EXCLUDE = [{"code": "select.owned_elsewhere", "glob": "src/agentdojo/defenses/drift/runs/**", "owner": "drift"},
           {"code": "select.not_execution_artefact", "glob": "**/.DS_Store", "owner": None}]  # fmt: skip


def _entry(path: str, code: str, snapshot: str = "a") -> RegisterEntry:
    owner = {"corpus_id": "drift", "source_id": "drift"} if code == "select.owned_elsewhere" else None
    return RegisterEntry(subject={"snapshot_id": snapshot, "path": path}, code=code, severity="info", stage="select",
                         disposition="not_imported", owner=owner)


def test_exclusions_are_not_candidates_but_other_not_imported_entries_are_d33():
    register = [
        _entry("src/agentdojo/defenses/drift/runs/x.json", "select.owned_elsewhere"),  # excluded by a glob
        _entry("runs/b/variant.json", "select.dialect_planned"),  # matched by include, not importable: a candidate
        RegisterEntry(subject={"snapshot_id": "a", "path": "runs/c/bad.json"}, code="ingest.size.file", severity="error",
                      stage="ingest", disposition="not_imported"),
    ]
    counts = snapshot_counts([], register, "a", EXCLUDE, all_snapshots=["a"])
    assert counts == {"candidates": 2, "executions": 0, "not_imported": 2,
                      "selection_excluded": {"select.owned_elsewhere": 1}}  # fmt: skip
    assert counts["candidates"] == counts["executions"] + counts["not_imported"]


def test_an_exclusion_needs_the_matching_glob_and_code():
    assert is_exclusion(_entry("src/agentdojo/defenses/drift/runs/x.json", "select.owned_elsewhere"), "a", EXCLUDE)
    assert not is_exclusion(_entry("src/agentdojo/defenses/drift/runs/x.json", "select.dialect_planned"), "a", EXCLUDE)
    assert not is_exclusion(_entry("src/agentdojo/defenses/drift/runs/x.json", "select.owned_elsewhere", "b"), "a", EXCLUDE)


def test_an_archive_member_exclusion_is_matched_by_its_member_label_as_the_importer_matches_it_d560():
    # the register path of an archive member is `<archive>!/<chain label>`; the importer matched the exclude glob
    # against the member's own label (`_glob_label`, D-380), so the seal must too, or the exclusion counts as a candidate
    exclude = [{"code": "select.not_execution_artefact", "glob": "pilot_v1_seeded/*/*_report.json", "owner": None},
               {"code": "select.out_of_scope", "glob": "pilot_v1_seeded/*/*/clean/**", "owner": None}]  # fmt: skip
    report = _entry("traces.tar.gz!/pilot_v1_seeded/gpt55/gpt55_report.json", "select.not_execution_artefact")
    clean = _entry("traces.tar.gz!/pilot_v1_seeded/gpt55/m/clean/run.json", "select.out_of_scope")
    nested = _entry("outer.zip!/inner.tar.gz!/pilot_v1_seeded/gpt55/gpt55_report.json", "select.not_execution_artefact")
    assert all(is_exclusion(e, "a", exclude) for e in (report, clean, nested))
    assert not is_exclusion(_entry("traces.tar.gz!/pilot_v1_seeded/gpt55/m/clean/run.json", "select.not_execution_artefact"),
                            "a", exclude)
    counts = snapshot_counts([], [report, clean], "a", exclude, all_snapshots=["a"])
    assert counts == {"candidates": 0, "executions": 0, "not_imported": 0,
                      "selection_excluded": {"select.not_execution_artefact": 1, "select.out_of_scope": 1}}  # fmt: skip


def test_an_unattributable_entry_in_a_multi_snapshot_corpus_is_refused():
    entry = RegisterEntry(subject={"source_key": "sha256:" + "0" * 64 + "#{}"}, code="select.dialect_planned", severity="info",
                          stage="select", disposition="not_imported")
    assert snapshot_counts([], [entry], "a", [], all_snapshots=["a"])["not_imported"] == 1
    with pytest.raises(ManifestError):
        snapshot_counts([], [entry], "a", [], all_snapshots=["a", "b"])


# ------------------------------------------------------------------------------------------------ origin from the pin (D-33)
GIT = {"kind": "git", "repo": "https://github.com/o/r", "commit": "c" * 40, "path": "runs/x.json", "blob_sha1": "1" * 40}


def test_git_origin_from_pin_and_objects():
    pin = {"commit": "c" * 40, "kind": "git", "role": "head", "tree": "runs/", "tree_sha1": "2" * 40}
    assert snapshot_origin_from_pin(pin, [GIT]) == {"commit": "c" * 40, "kind": "git", "repo": "https://github.com/o/r",
                                                    "subtree": "runs", "subtree_sha1": "2" * 40}
    whole = snapshot_origin_from_pin({"commit": "c" * 40, "kind": "git", "repo": "https://github.com/o/r"}, [GIT])
    assert whole["subtree"] == "" and "subtree_sha1" not in whole


def test_corpus_origin_for_the_adprov_release():
    obj = {"kind": "corpus", "corpus": "AgentDojo-PROV", "version": "2.3", "producer_commit": "c" * 40, "path": "a"}
    pin = {"commit": "c" * 40, "kind": "git", "repo": "https://github.com/n/agentdojo-prov", "tree": "corpus/corpus-prov"}
    assert snapshot_origin_from_pin(pin, [obj]) == {"corpus": "AgentDojo-PROV", "kind": "corpus",
                                                    "producer_commit": "c" * 40, "version": "2.3"}


@pytest.mark.parametrize(
    ("pin", "objects"),
    [
        (None, [GIT]),
        ({"commit": "main", "kind": "git"}, [GIT]),
        ({"commit": "c" * 40, "kind": "git"}, [{"kind": "local", "path": "/x"}]),
        ({"commit": "d" * 40, "kind": "git"}, [GIT]),
        ({"commit": "c" * 40, "kind": "git", "repo": "https://github.com/other/r"}, [GIT]),
    ],
)
def test_origins_without_a_vouching_pin_are_refused(pin, objects):
    with pytest.raises(ManifestError):
        snapshot_origin_from_pin(pin, objects)


# ------------------------------------------------------------------------------------------------ validation (D-40)
def test_linkage_resolved_pct_is_floored_and_exact_at_one_hundred():
    assert linkage_resolved_pct(10, 10) == {"$dec": "100.00"}
    assert linkage_resolved_pct(9999, 10000) == {"$dec": "99.99"}
    assert linkage_resolved_pct(99999, 100000) == {"$dec": "99.99"}  # never rounded up to 100
    assert linkage_resolved_pct(0, 3) == {"$dec": "0.00"}
    assert linkage_resolved_pct(0, 0) is None
    with pytest.raises(ValueError):
        linkage_resolved_pct(4, 3)


def test_validation_summary_tiers_and_linkage():
    summary = {"checks": [
        {"id": "aer.validator", "pass": 2, "fail": 0, "skipped": 0, "not_applicable": 0},
        {"id": "agentdojo.suites@1:SEM-V01", "pass": 2, "fail": 0, "skipped": 0, "not_applicable": 0},
        {"id": "pv.linkage.rule", "pass": 1, "fail": 1, "skipped": 0, "not_applicable": 0},
        {"id": "pv.linkage.premise", "pass": 0, "fail": 0, "skipped": 0, "not_applicable": 2},
    ]}  # fmt: skip
    stage = {"checks": ["aer.validator", "tier3:agentdojo.suites@1", "tier4:agentprov-prov/0.1"], "mode": "release",
             "libraries": {"rdflib": "7.6.0", "prov": "3.2.2"}}
    results = [
        {"ex": "a", "checks": {"aer.validator": "pass", "agentdojo.suites@1:SEM-V01": "pass", "pv.linkage.rule": "pass",
                               "pv.linkage.premise": "not_applicable"}},
        {"ex": "b", "checks": {"aer.validator": "pass", "agentdojo.suites@1:SEM-V01": "pass", "pv.linkage.rule": "fail",
                               "pv.linkage.premise": "not_applicable"}},
    ]  # fmt: skip
    v = validation_summary(summary, stage, results)
    assert v["mode"] == "strict" and list(v["libraries"]) == ["prov", "rdflib"]
    assert {c["id"]: (c["tier"], c["version"]) for c in v["checks"]} == {
        "aer.validator": (2, "aer/0.2"), "agentdojo.suites@1:SEM-V01": (3, "agentdojo.suites@1"),
        "pv.linkage.premise": (4, "agentprov-prov/0.1"), "pv.linkage.rule": (4, "agentprov-prov/0.1")}
    tiers = {t["tier"]: t for t in v["tiers"]}
    assert tiers[2]["executions_passed"] == 2 and tiers[4]["executions_passed"] == 1 and tiers[4]["checks"] == 2
    assert v["linkage"] == {"applicable": 2, "resolved": 1, "spec": "agentprov-prov/0.1"}
    assert v["linkage_resolved_pct"] == {"$dec": "50.00"}
    assert validation_summary(summary, {**stage, "mode": "dev"}, results)["mode"] == "dev"


def test_rule_catalogue_refs_assign_used_rules_and_refuse_unrecorded_namespaces():
    refs = rule_catalogue_refs({"aer": (1, "a" * 64, 14, "rules/aer.rules.toml")}, ["aer.x@1", "aer.y@2", "not a rule"])
    assert refs[0]["rules_used"] == ["aer.x@1", "aer.y@2"] and refs[0]["sha256"] == "sha256:" + "a" * 64
    with pytest.raises(ManifestError):
        rule_catalogue_refs({"aer": (1, "a" * 64, 14, "rules/aer.rules.toml")}, ["rope.z@1"])


def _member(container: str) -> MemberRow:
    return MemberRow(container, "f" * 64, "a.json", 8, "00000000", 1, "a" * 64, "selected")


def _expand_failure(path: str, snapshot: str = "s1") -> RegisterEntry:
    return RegisterEntry(subject={"snapshot_id": snapshot, "path": path}, code="expand.failed", severity="error",
                         stage="expand", disposition="failed", detail="job error")


@pytest.mark.parametrize(("ok", "failures", "expected"), [
    (2, [("c3.zip", "s1")], {"ok": 2, "failed": 1}),  # a failed container writes no members.jsonl row: not subtracted
    (1, [("c2.zip", "s1"), ("c3.zip", "s1")], {"ok": 1, "failed": 2}),  # ok is not clamped to 0
    (1, [("c3.zip", "s1"), ("c3.zip", "s2")], {"ok": 1, "failed": 2}),  # one path failing in two snapshots
    (2, [], {"ok": 2, "failed": 0}),
])  # fmt: skip
def test_by_stage_expand_counts_successful_containers_and_distinct_failures(ok, failures, expected):
    members = [_member(c * 64) for c in "12"[:ok]]
    register = [_expand_failure(path, snapshot) for path, snapshot in failures]
    assert corpus_counts([], register, members, [], AerStats())["by_stage"]["expand"] == expected
