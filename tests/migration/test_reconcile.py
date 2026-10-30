"""Gate R3 (J.4.3, J.4.4): the field-level diff of the native and the converted v1 AER, on the golden pairs and on
synthetic records.

The golden pairs N-C01..N-C09 / C01..C09 are third-party data with prompt-injection payloads: nothing here prints a
fixture substring; assertions are on categories, field patterns, counts and verdicts. The full scope (18,027 pairs) runs
locally with ``tools/migration/r3_reconcile.py``.
"""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

import pytest

from agentprov.adapters.runner import aer_bytes, map_artefact
from agentprov.adapters.types import Origin
from agentprov.migration import reconcile
from agentprov.testing import golden

needs_golden = pytest.mark.skipif(not golden.golden_available(), reason="golden fixtures not found")
UPSTREAM = "https://github.com/ethz-spylab/agentdojo"
C274885 = "c274885610efaaafec38b6d3eb07152ba7ff3f94"
BASELINE = "579a908354b93361efe0905ffb7623256aa96a06"


def _records(data: bytes) -> list[dict[str, Any]]:
    return [json.loads(line) for line in data.splitlines()]


@pytest.fixture(scope="module")
def golden_report() -> reconcile.ReconciliationReport:
    native = {e.id: e for e in golden.native_logs()}
    v1 = {e.id: e for e in golden.v1_pairs()}
    report = reconcile.ReconciliationReport()
    for n in range(1, 10):
        nat, conv = native[f"N-C0{n}"], v1[f"C0{n}"]
        origin_n = Origin.git(UPSTREAM, C274885, nat.origin["path"], nat.origin["git_blob_sha1"])
        origin_c = Origin.corpus("AgentDojo-PROV", "2.3", f"corpus-og-agentdojo-runs-prov/{conv.origin['corpus_relpath']}"
                                 ".transcript.json", producer_commit=BASELINE)
        data_n, info_n = aer_bytes(map_artefact(nat.native_bytes(), origin_n, profile_id="agentdojo-upstream")[0])
        data_c, info_c = aer_bytes(map_artefact(conv.transcript_bytes(), origin_c, profile_id="adprov-v1")[0])
        a, b = _records(data_n), _records(data_c)
        record = reconcile.lineage(a[0], b[0], native_sha256=info_n.file_sha256, v1_sha256=info_c.file_sha256,
                                   v1_issue_codes=[str(i.get("code")) for i in info_c.issues])
        report.add(conv.id, reconcile.project(a), reconcile.project(b), record)
    return report


@needs_golden
def test_the_golden_pairs_pass_r3_with_every_difference_explained(golden_report):
    doc = golden_report.to_json()
    assert doc["pairs"] == 9 and doc["passed"] and doc["unexplained"] == []
    assert doc["lineage_verdicts"] == {"agree": 9}
    assert doc["by_category"]["equal"] > 1000 and "differs_unexpected" not in doc["by_category"]
    rows = {(f["category"], f["pattern"]): f["rule"] for f in doc["fields"]}
    assert rows[("differs_expected", "scope[*]/t/dur_s")] == "rounding"  # J.4.4: round(duration, 3)
    assert rows[("v1_only", "tool_execution[*]/t/raw/start")] == "tool timing (t.raw stub)"
    assert rows[("native_only", "execution[*]/task/defense_id")] == "pipeline/model/defence split"


@needs_golden
def test_messages_parts_tool_calls_results_fixtures_and_judgements_are_equal(golden_report):
    by_kind: Counter[str] = Counter()
    for (category, pattern, _rule), n in golden_report.categories.items():
        kind = pattern.split("[", 1)[0]
        if kind in ("message", "fixture", "judgement") and "/ext/" not in pattern and category != "equal":
            by_kind[f"{kind}:{pattern}"] += n
    assert by_kind == Counter({"message:message[*]/parts/*/provider_call_id": 4})  # the call-id status row of J.4.4


def test_an_unexplained_difference_fails_and_names_its_pattern():
    native = {"message[0]/parts/0/text": "a", "scope[0]/t/dur_s": 1.0}
    v1 = {"message[0]/parts/0/text": "b", "scope[0]/t/dur_s": 1.0004}
    report = reconcile.ReconciliationReport()
    report.add("item-1", native, v1, {"verdict": "agree"})
    doc = report.to_json()
    assert not doc["passed"]
    assert doc["unexplained"] == [{"key": "differs_unexpected:message[*]/parts/*/text", "pairs": 1, "first_items": ["item-1"]}]
    assert ("differs_expected", "scope[*]/t/dur_s", "rounding") in report.categories


def test_a_rounding_beyond_half_a_millisecond_is_unexpected():
    out = reconcile.classify({"scope[0]/t/dur_s": 1.0}, {"scope[0]/t/dur_s": 1.001})
    assert out == Counter({("differs_unexpected", "scope[*]/t/dur_s", ""): 1})


def test_one_sided_fields_outside_j44_are_reported_as_unexplained_presence():
    out = reconcile.classify({"message[0]/ext/agentdojo/new_thing": 1}, {})
    assert out == Counter({("native_only", "message[*]/ext/agentdojo/new_thing", "unexplained"): 1})


def test_a_lineage_that_names_another_path_or_an_unresolved_link_disagrees():
    native = {"artifacts": [{"origin": {"repo": UPSTREAM, "commit": C274885, "path": "runs/a.json", "blob_sha1": "b" * 40}}]}
    v1 = {"ext": {"adprov": {"derived_from_upstream": {"repo": UPSTREAM, "commit": C274885, "path": "runs/a.json"}}}}
    agree = reconcile.lineage(native, v1, native_sha256="n", v1_sha256="v", v1_issue_codes=[])
    assert agree["verdict"] == "agree" and agree["rule"] == reconcile.LINEAGE_RULE
    moved = {"ext": {"adprov": {"derived_from_upstream": {"repo": UPSTREAM, "commit": C274885, "path": "runs/b.json"}}}}
    assert reconcile.lineage(native, moved, native_sha256="n", v1_sha256="v", v1_issue_codes=[])["verdict"] == "disagree"
    unresolved = reconcile.lineage(native, v1, native_sha256="n", v1_sha256="v",
                                   v1_issue_codes=["adprov.upstream_link_unresolved"])
    assert unresolved["verdict"] == "disagree"


def test_actor_records_compare_by_id_and_a_defence_attribution_is_expected():
    native = reconcile.project([{"k": "actor", "id": "def0", "kind": "defense", "name": "tool_filter"},
                                {"k": "message", "id": "m1", "role": "user", "actor": "def0"}])
    v1 = reconcile.project([{"k": "actor", "id": "user", "kind": "simulated_user"},
                            {"k": "message", "id": "m1", "role": "user", "actor": "user"}])
    out = reconcile.classify(native, v1)
    assert out[("differs_expected", "message[*]/actor", "defence attribution")] == 1
    assert out[("native_only", "actors/def*/kind", "pipeline/model/defence split (the defence actor)")] == 1


def _banking_pair(args: dict[str, Any], returned: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"k": "execution", "id": "exec", "ex": "ex_a", "ev": "O", "by": "source"},
        {"k": "message", "id": "m1", "ev": "O", "role": "assistant", "after": [{"b": "causal", "id": "mc0"}],
         "parts": [{"t": "tool_call", "name": "update_scheduled_transaction", "args": args}]},
        {"k": "tool_execution", "id": "te0", "call": "m1#0", "name": "update_scheduled_transaction", "args": args,
         "returned": returned, "ext": {"agentdojo": {"id": args["id"]}}},
    ]


def test_payload_members_named_like_record_metadata_are_compared():
    """CB-28: the J.4.4 row-1 skip list (``id``, ``k``, ``rule``, ``hash``, ...) applies to record metadata, never to
    payload: a differing tool-call argument ``id`` is a ``differs_unexpected`` field and R3 does not pass."""
    native = reconcile.project(_banking_pair({"id": 7, "recipient": "X", "k": "a", "rule": "r1", "hash": "h1"},
                                             {"id": 7, "hash": "h1"}))
    v1 = reconcile.project([dict(r, id=f"v{r['id']}", ex="ex_b") if r["k"] == "execution" else r for r in
                            _banking_pair({"id": "999", "recipient": "X", "k": "b", "rule": "r2", "hash": "h2"},
                                          {"id": "999", "hash": "h2"})])
    for path in ("message[0]/parts/0/args/id", "message[0]/parts/0/args/k", "message[0]/parts/0/args/rule",
                 "tool_execution[0]/args/id", "tool_execution[0]/returned/hash", "tool_execution[0]/ext/agentdojo/id"):
        assert path in native and path in v1
    assert not any(p.endswith(("/ev", "/by")) or p in ("execution[0]/ex", "message[0]/after/0/id") for p in native)
    report = reconcile.ReconciliationReport()
    report.add("item-1", native, v1, {"verdict": "agree"})
    assert not report.passed
    assert report.categories[("differs_unexpected", "message[*]/parts/*/args/id", "")] == 1
    assert report.categories[("differs_unexpected", "tool_execution[*]/args/id", "")] == 1
