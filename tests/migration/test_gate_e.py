"""Gate E (J.3.6; K.5.6 item 8; K.7.4 item 5): the v2.3 -> ``agentprov-prov/0.1`` semantic diff on the golden set, the edge
classifier on synthetic transcripts, and failure modes.

The golden pairs are third-party data with prompt-injection payloads: nothing here prints a fixture substring. Assertions
are on counts, codes and digests. The full scope (35,691 graphs, phase 13) runs locally only.
"""

from __future__ import annotations

import copy
import json
from collections import Counter

import pytest

from agentprov.ingest.loaders import strict_json_loads
from agentprov.migration import gates, semdiff
from agentprov.prov.compat.adprov_v2_3.build_prov import PI_DETECTOR_PLACEHOLDER, build_prov
from agentprov.testing import golden

needs_golden = pytest.mark.skipif(not golden.golden_available(), reason="golden fixtures not found")


@pytest.fixture(scope="module")
def gate_e(tmp_path_factory):
    work = tmp_path_factory.mktemp("work")
    cfg = gates.MigrationConfig(workers=2, work=work, reports_dir=work / "reports")
    return gates.gate_e_semdiff(cfg, scope="golden")


def _graphs(tree: str) -> list[dict]:
    return [strict_json_loads(e.graph_bytes()) for e in golden.v1_pairs() if (e.tree or "release") == tree]


def _relation_counts(graphs: list[dict]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for graph in graphs:
        for relation in semdiff.RELATION_ENDPOINTS:
            counts[relation] += len(graph.get(relation, {}))
    return counts


# ------------------------------------------------------------------------------------------------ the golden gate


@needs_golden
def test_gate_e_passes_on_the_golden_set(gate_e):
    report, reports = gate_e
    doc = report.to_json()
    assert doc["gate"] == "E" and doc["scope"] == "golden" and doc["role"] == "release" and doc["verdict"] == "pass"
    assert doc["counts"] == {"expected": 19, "checked": 19, "passed": 19, "failed": 0, "skipped": 0}
    assert doc["failures"] == [] and all(c["status"] == "pass" for c in doc["checks"])
    assert set(reports) == {"release", "converted"}
    assert {o["name"] for o in doc["outputs"]} == {"semdiff_report", "aer_digest_listing"}
    assert any("regression oracle" in note for note in doc["notes"])


@needs_golden
@pytest.mark.parametrize("tree", ["release", "converted"])
def test_nothing_is_unmapped_and_the_classified_union_is_the_edge_set(gate_e, tree):
    doc = gate_e[1][tree].document
    assert doc["unmapped"] == 0 and doc["unmapped_elements"] == {}
    edges = doc["edges"]
    assert edges["unclassified"] == 0 and edges["missing"] == 0 and edges["classified"] == edges["total"]
    # independently of the classifier: the edge totals per relation type equal what the stored graphs hold
    stored = _relation_counts(_graphs(tree))
    classified = {rel: sum(labels.values()) for rel, labels in edges["by_relation"].items()}
    assert classified == {rel: n for rel, n in stored.items() if n}
    assert edges["total"] == sum(stored.values())


@needs_golden
@pytest.mark.parametrize("tree", ["release", "converted"])
def test_an_r4_and_r6_edge_is_classified_once_with_both_reasons(gate_e, tree):
    doc = gate_e[1][tree].document
    used = doc["edges"]["by_relation"]["used"]
    overlaps = doc["overlaps"]["R4+R6"]
    assert overlaps == used.get("R4+R6", 0) > 0
    rows = {r["id"]: r for r in doc["rows"]}
    # J.1.3: used = R3 + R4 + R6-only, with the overlaps counted once under R4
    assert rows["R3"]["count"] + rows["R4"]["count"] + rows["R6"]["count"] == sum(used.values()) == doc["values"]["used_total"]
    assert rows["R4"]["rules"] == ["R4", "R4+R6"] and rows["R6"]["rules"] == ["R6"]
    assert rows["R6"]["extra"]["taint_pairs"]["count"] == rows["R6"]["count"] + overlaps
    assert rows["R6"]["extra"]["overlaps"]["count"] == overlaps
    # R5 asserts exactly the R4 pairs (audit/provenance.md §4.1)
    assert rows["R5"]["count"] == rows["R4"]["count"]


@needs_golden
@pytest.mark.parametrize("tree", ["release", "converted"])
def test_the_entailed_but_unasserted_communications_are_the_taint_only_edges(gate_e, tree):
    doc = gate_e[1][tree].document
    assert doc["inference6"]["entailed_not_asserted"] == doc["values"]["used_r6_only"]
    assert doc["inference6"]["asserted_not_entailed"] == 0


@needs_golden
def test_the_golden_numbers(gate_e):
    """Pinned golden-scope numbers (they change only with the golden set, the map or the engine)."""
    release, converted = gate_e[1]["release"].document, gate_e[1]["converted"].document
    assert release["edges"]["by_relation"] == {
        "used": {"R3": 14, "R4": 512, "R4+R6": 319, "R6": 322},
        "wasAssociatedWith": {"R2": 199},
        "wasGeneratedBy": {"R1": 199},
        "wasInformedBy": {"R5": 831},
    }
    assert converted["edges"]["by_relation"] == {
        "used": {"R3": 11, "R4": 4, "R4+R6": 4, "R6": 1},
        "wasAssociatedWith": {"R2": 19},
        "wasGeneratedBy": {"R1": 19},
        "wasInformedBy": {"R5": 8},
    }
    assert release["values"]["used_policy_pct"] == 27.59 and converted["values"]["used_policy_pct"] == 5.0


@needs_golden
def test_defence_omitted_is_an_overwritten_pre_decision_entity(gate_e):
    omitted = gate_e[1]["converted"].document["defence_omitted"]
    assert omitted["compat_entities"] == omitted["aer_redact_decisions_overwritten"] == omitted["derived_overwritten_entities"] > 0
    assert omitted["content_status"] == "apv:Overwritten"
    row = next(r for r in gate_e[1]["converted"].document["rows"] if r["id"] == "adprov_defence_omitted")
    assert row["count"] == omitted["compat_entities"] and row["content_status"] == "apv:Overwritten"
    assert row["derived"]["aprov.decision@1"] == {"inference:I": row["derived"]["aprov.decision@1"]["inference:I"]}


@needs_golden
def test_rows_carry_the_report_fields_of_j36(gate_e):
    doc = gate_e[1]["release"].document
    assert doc["semdiff"] == "adprov-v2.3-compat→agentprov-prov/0.1" and doc["report"] == "agentprov-semdiff/0.1"
    assert doc["map"]["sha256"] == semdiff.load_map().sha256 and doc["map"]["path"] == semdiff.MAP_RELPATH
    assert {"aer", "sem", "agentprov-prov", "adprov-v2.3-compat", "catalogue"} <= set(doc["spec_versions"])
    assert len(doc["inputs"]["transcript_listing_sha256"]) == 64 and len(doc["inputs"]["graph_listing_sha256"]) == 64
    assert [r["id"] for r in doc["rows"]] == [r.id for r in semdiff.load_map().rows]
    for row in doc["rows"]:
        assert {"v23_element", "count", "disposition", "targets", "bundle", "evidence_class", "rules"} <= set(row)
        assert row["disposition"] in semdiff.DISPOSITIONS
    # the report holds no time, commit or machine path, so its bytes are a function of the inputs
    text = gate_e[1]["release"].json_text()
    assert "started_at" not in text and "commit" not in text and str(golden.REPO_ROOT) not in text


@needs_golden
def test_the_report_bytes_are_stable_across_two_runs(gate_e, tmp_path):
    report, reports = gate_e
    assert {c.check: c.status for c in report.checks}["determinism.semdiff.release"] == "pass"
    again = gates.gate_e_semdiff(gates.MigrationConfig(workers=1, in_process=True, work=tmp_path), scope="golden")[1]
    assert {t: r.json_bytes() for t, r in again.items()} == {t: r.json_bytes() for t, r in reports.items()}


@needs_golden
def test_the_counterpart_derivation_lands_where_the_map_says(gate_e):
    doc = gate_e[1]["release"].document
    assert doc["derivation"]["rules_not_targeted"] == []
    rows = {r["id"]: r for r in doc["rows"]}
    assert set(rows["R3"]["derived"]["aprov.use_context@1"]) == {"inference:I"}  # AD-05: never in the core
    # regeneration-batch item 3 (D-27 c6): a tool result's generation rests on adprov.tool_turn_is_one_execution, which
    # cites no code, so on the released tree it is INFERRED
    assert set(rows["R1"]["derived"]["aprov.gen_result@1"]) == {"inference:I"}


@needs_golden
def test_write_semdiff_names_the_golden_scope_apart(gate_e, tmp_path):
    written = gates.write_semdiff(gate_e[1], tmp_path, scope="golden")
    assert sorted(p.name for p in written) == [
        "semdiff-converted.golden.json", "semdiff-converted.golden.md", "semdiff-release.golden.json", "semdiff-release.golden.md",
    ]
    data = (tmp_path / "semdiff-release.golden.json").read_bytes()
    assert data == gate_e[1]["release"].json_bytes() and json.loads(data)["unmapped"] == 0
    assert "| R4 used(a_k, e_j)" in (tmp_path / "semdiff-release.golden.md").read_text()


def test_full_scope_gate_e_needs_its_predecessors(tmp_path):
    cfg = gates.MigrationConfig(reports_dir=tmp_path / "r")
    with pytest.raises(gates.GateOrderError, match="gate G0"):
        gates.require_predecessors(cfg, "E", "full")
    assert gates.GATE_ORDER == ("G0", "A", "B", "D", "E")


# ------------------------------------------------------------------------------------------------ the classifier


def _tool(call_id: str, fn: str, content: str = "x") -> dict:
    return {"role": "tool", "tool_call_id": call_id, "function": fn, "args": {}, "content": content, "error": None,
            "started_at": None, "ended_at": None}


def _transcript() -> dict:
    """Three tool-bearing turns: an untrusted read, a sink after it (R4 and R6 on one edge), and a sink after that (R6
    only for the read, R4 and R6 for the previous sink, whose output is untrusted too)."""
    return {
        "meta": {"injections": {}},
        "turns": [
            {"role": "system", "content": "s"},
            {"role": "user", "content": "q"},
            {"role": "assistant", "content": None},
            _tool("c1", "get_received_emails"),
            {"role": "assistant", "content": None},
            _tool("c2", "send_email"),
            {"role": "assistant", "content": None},
            _tool("c3", "send_money"),
            {"role": "assistant", "content": "done"},
        ],
    }


def _classify(view: dict, graph: dict) -> semdiff.ExecutionDiff:
    diff = semdiff.ExecutionDiff("t", "release")
    semdiff.classify_graph(diff, view, graph, semdiff.load_map())
    return diff


def test_the_predicates_reproduce_the_port_on_a_synthetic_transcript():
    view = _transcript()
    diff = _classify(view, build_prov(view))
    assert diff.unclassified == diff.missing_edges == diff.missing_nodes == 0 and not diff.unmapped
    assert diff.reasons == Counter({
        "wasGeneratedBy:R1": 3, "wasAssociatedWith:R2": 3, "used:R3": 1, "wasInformedBy:R5": 2,
        "used:R4+R6": 2, "used:R6": 1,
    })
    assert diff.overlaps == 2 and diff.taint_pairs == 3 and diff.rules["R6"] == 1 and diff.rules["R4"] == 2
    assert diff.inference6["entailed_not_asserted"] == 1 and diff.inference6["asserted_not_entailed"] == 0


def test_a_new_pass_restarts_the_batch_walk():
    view = _transcript()
    view["discarded_attempts"] = [{"turns": copy.deepcopy(view["turns"])}]
    diff = _classify(view, build_prov(view))
    assert diff.unclassified == diff.missing_edges == 0 and diff.reasons["used:R3"] == 2
    assert diff.attributes[("adprov:attempt", "a_k")] == 6


def test_an_extra_edge_is_unclassified_and_a_dropped_one_is_missing():
    view = _transcript()
    graph = build_prov(view)
    extra = copy.deepcopy(graph)
    extra["used"]["adprov:u_99999"] = {"prov:activity": "adprov:a_c1", "prov:entity": "adprov:e_c3"}
    diff = _classify(view, extra)
    assert diff.unclassified == 1 and diff.unmapped["edge:unclassified"] == 1
    fewer = copy.deepcopy(graph)
    fewer["wasInformedBy"].pop(next(iter(fewer["wasInformedBy"])))
    assert _classify(view, fewer).missing_edges == 1


def test_an_acted_on_behalf_of_edge_has_no_builder_predicate():
    view = _transcript()
    graph = build_prov(view)
    graph["actedOnBehalfOf"] = {"adprov:aob_1": {"prov:delegate": "adprov:ag_llm", "prov:responsible": "adprov:ag_llm"}}
    assert _classify(view, graph).unclassified == 1


def test_an_unknown_attribute_node_or_section_is_unmapped():
    view = _transcript()
    graph = build_prov(view)
    graph["entity"]["adprov:e_c1"]["adprov:mystery"] = 1
    graph["agent"]["adprov:ag_other"] = {"prov:label": "x"}
    graph["bundle"] = {}
    diff = _classify(view, graph)
    assert diff.unmapped == Counter({"attribute:adprov:mystery@e_k": 1, "node:agent": 1, "section:bundle": 1})


def test_the_gated_relations_are_classified_by_their_predicates():
    view = _transcript()
    graph = build_prov(view, emit_source_agents=True, emit_derived_edges=True)
    diff = _classify(view, graph)
    assert diff.unclassified == diff.missing_edges == 0 and not diff.unmapped
    # R7 on every taint pair; R8 on the two untrusted outputs (email, and send_email's channel "external")
    assert diff.rules["R7"] == 3 and diff.rules["R8"] == 2 and diff.nodes["ag_src"] == 2


def test_defence_omitted_is_counted_on_the_tool_output():
    view = _transcript()
    view["turns"][3]["content"] = PI_DETECTOR_PLACEHOLDER
    diff = _classify(view, build_prov(view))
    assert diff.attributes[("adprov:defence_omitted", "e_k")] == 1 and not diff.unmapped


@needs_golden
def test_the_taint_assessments_reproduce_the_v23_sink_taint_pairs(gate_e):
    """EF E.7.3 item 2: under unchanged labels the taint assessments are the v2.3 R6 pairs. The golden traces hold no
    unknown tool and no never-executed sink request, so the counts are equal (the full scope may add fail-closed pairs)."""
    for tree, report in gate_e[1].items():
        values = report.document["values"]
        assert values["taint_assessments"] == values["taint_pairs"] > 0, tree
