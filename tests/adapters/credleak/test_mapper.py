"""The ``credleak.cell`` mapper (docs/architecture D.19.3-D.19.7; DECISIONS D-260..D-264).

The fixtures are unedited cells (no planted value); the synthetic cells are built at test time and never committed.
No test prints source content.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import credleak_support as support

from agentprov.adapters.credleak.mapper import JUDGED
from agentprov.aer.ids import part_id

GOLDEN = Path(__file__).resolve().parent / "golden" / "aer_digests.json"
SYNTH_LABEL = "p15b-run-data/01-injection-map/T1-file-document/test-model/run__T1__test-model__T1.9__2026.json"


def _synthetic(**kwargs):
    return support.map_cell(SYNTH_LABEL, support.synthetic_cell(**kwargs), sem=False, prov=False)


def _source_run(m):
    cell = json.loads(support.cell_bytes(next(e for e in support.source_entries() if e["label"] == m.label)))
    return cell, cell["runs"][m.index]


def test_golden_aer_digests(mapped):
    """The sealed AER bytes of every fixture run (regenerate with AGENTPROV_REGEN_CREDLEAK_GOLDEN=1)."""
    digests = {f"{path}#{m.index}": hashlib.sha256(m.data).hexdigest() for path, runs in sorted(mapped.items())
               for m in runs}
    if os.environ.get("AGENTPROV_REGEN_CREDLEAK_GOLDEN") == "1":
        GOLDEN.parent.mkdir(exist_ok=True)
        GOLDEN.write_text(json.dumps(digests, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    assert digests == json.loads(GOLDEN.read_text(encoding="utf-8"))


def test_every_fixture_run_seals_and_derives_valid_provenance(mapped):
    from agentprov.aer.rules import RuleRegistry
    from agentprov.validate import validate_prov

    registry = RuleRegistry.default()  # what validate_prov builds per call when none is given; built once here
    for runs in mapped.values():
        for m in runs:
            assert not m.outcome.degenerate, (m.label, m.index)
            assert validate_prov(m.prov.prov_json, m.doc, sems=[m.sem], registry=registry).failed() == [], \
                (m.label, m.index)


def test_the_header_names_the_run_by_its_cell_digest_and_locator(mapped):
    for runs in mapped.values():
        for m in runs:
            cell, run = _source_run(m)
            header = m.header
            assert header["source_key"]["loc"] == {"p": f"/runs/{m.index}"}
            assert header["task"]["task_id"] == cell["scenario"] == header["task"]["attack_id"]
            assert header["task"]["suite"] == cell["technique"] and header["task"]["defense_id"] == cell["defence"]
            assert header["ext"]["credleak"]["run_index"] == m.index
            assert header["ext"]["credleak"]["path_facets"]["section"] in ("01-injection-map", "03-egress-axis", "04-hygiene")
            agent = m.get("agent")
            assert agent["model"] == {"requested": run["model"]}
            assert "/model/served" in agent["unk"] and "/model/provider" in agent["unk"]
    ids = [m.header["ex"] for runs in mapped.values() for m in runs]
    assert len(set(ids)) == len(ids)


def test_each_result_is_linked_to_the_call_of_its_own_entry(mapped):
    seen = 0
    for runs in mapped.values():
        for m in runs:
            _cell, run = _source_run(m)
            entries = [e for t in run["turns"] for e in t["toolCalls"]]
            tes = m.of("tool_execution")
            assert len(tes) == len(entries)
            for te, entry in zip(tes, entries, strict=True):
                assert te["evf"]["/call"] == "D" and "credleak.pair_same_entry@1#/call" in te["rule"]
                result = next(r for r in m.of("message") if r.get("generated_by") == te["id"])
                part = result["parts"][0]
                assert part["responds_to"] == te["call"] == part_id(te["call"].split("#")[0], 0)
                assert result["evf"]["/parts/0/responds_to"] == "D"
                assert te["name"] == entry["tool"] and te["args"] == entry["input"]
                if "redacted" in result.get("ext", {}).get("credleak", {}):  # D-605: the ls -l columns of account #1
                    assert part.get("text") != entry["output"] and "acct-" in part["text"]
                else:
                    assert part.get("text") == entry["output"]
                seen += 1
    assert seen > 100


def test_no_time_is_typed_and_the_turn_timestamp_is_kept_verbatim(mapped):
    for runs in mapped.values():
        for m in runs:
            _cell, run = _source_run(m)
            assert not any("t" in r for r in m.records)
            scopes = [s for s in m.of("scope") if s["kind"] == "agent_invocation"]
            assert len(scopes) == len(run["turns"])
            for scope, turn in zip(scopes, run["turns"], strict=True):
                assert scope["unk"]["/t"] == "ambiguous" and "credleak.turn_timestamp_role@1#/t" in scope["rule"]
                assert scope["ext"]["credleak"]["timestamp"] == turn["timestamp"]
            run_scope = m.get("run")
            assert run_scope["unk"]["/t/dur_s"] == "ambiguous" and run_scope["ext"]["credleak"]["duration_ms"] == run["durationMs"]


def test_agent_messages_declare_no_generator(mapped):
    for runs in mapped.values():
        for m in runs:
            assert m.of("model_call") == []
            agent = [r for r in m.of("message") if r["role"] == "assistant"]
            assert agent and all(r["unk"]["/generated_by"] == "not_recorded" and "generated_by" not in r for r in agent)
            (issue,) = [i for i in m.issues if i["code"] == "missing_generated_by"]
            assert sorted(issue["ids"]) == sorted(r["id"] for r in agent)


def test_the_response_is_ordered_after_the_user_message_only(mapped):
    for runs in mapped.values():
        for m in runs:
            messages = m.of("message")
            for scope in [s for s in m.of("scope") if s["kind"] == "agent_invocation"]:
                turn = [r for r in messages if r["scope"] == scope["id"]]
                user, response = turn[0], turn[-1]
                assert user["role"] == "user" and response["role"] == "assistant" and "generated_by" not in response
                assert response["after"] == [{"b": "pos", "id": user["id"]}]


def test_a_later_turn_follows_the_end_of_the_previous_one():
    turn = {"turnNumber": 0, "userMessage": "a", "assistantResponse": "b", "timestamp": "2026-06-11T08:00:00.000Z",
            "toolCalls": [{"tool": "Bash", "input": {"command": "ls"}, "output": "x"}]}
    (m,) = _synthetic(turns=[turn, dict(turn, turnNumber=1, toolCalls=[])])
    messages = m.of("message")
    second_user = next(r for r in messages if r["scope"] == "inv1" and r["role"] == "user")
    first = [r for r in messages if r["scope"] == "inv0"]
    assert {a["id"] for a in second_user["after"]} == {first[-2]["id"], first[-1]["id"]}  # last result and response
    assert second_user["evf"]["/after"] == "I"


def test_detector_signals_are_judgements(mapped):
    for runs in mapped.values():
        for m in runs:
            _cell, run = _source_run(m)
            judgements = m.of("judgement")
            assert [j["name"] for j in judgements] == [k for k in JUDGED if k in run]
            for j in judgements:
                assert j["value"] == run[j["name"]] and j["origin"] == "checker" and j["evf"]["/origin"] == "I"
                assert j["actor"] == "det" and j["subject"] == "run"
            fields = m.header["ext"]["credleak"].get("run_fields", {})
            assert not set(fields) & set(JUDGED) and "turns" not in fields


def test_an_invocation_error_ends_the_run_with_status_error():
    entry = support.by_criterion("invocation_error")
    (m,) = support.map_entry(entry, sem=False, prov=False)
    run = m.get("run")
    assert run["status"] == "error" and run["evf"]["/status"] == "I"
    assert "credleak.invocation_error" in m.codes()
    (clean,) = _synthetic()
    assert "status" not in clean.get("run") and clean.get("run")["unk"]["/status"] == "not_recorded"


def test_tool_call_count_check():
    def verdict(m):
        (check,) = [c for c in m.doc.seal["accounting"]["checks"] if c["id"] == "credleak.acc.tool_call_count@1"]
        return check["verdict"]

    assert verdict(_synthetic(toolCallCount=1)[0]) == "consistent"
    assert verdict(_synthetic(toolCallCount=3)[0]) == "inconsistent"
    assert verdict(_synthetic()[0]) == "unverifiable"


def test_cell_run_disagreement_is_an_issue():
    value = json.loads(support.synthetic_cell())
    value["runs"][0]["model"] = "other-model"
    (m,) = support.map_cell(SYNTH_LABEL, json.dumps(value).encode(), sem=False, prov=False)
    assert "credleak.cell_run_disagree" in m.codes()
    assert "credleak.cell_run_disagree" not in _synthetic()[0].codes()


def test_placeholder_names_and_empty_texts_are_never_typed_values():
    turn = {"turnNumber": 0, "userMessage": "a", "assistantResponse": "", "timestamp": "2026-06-11T08:00:00.000Z",
            "toolCalls": [{"tool": "", "input": {}, "output": "x"}]}
    (m,) = _synthetic(turns=[turn])
    response = next(r for r in m.of("message") if r["scope"] == "inv0" and r["role"] == "assistant" and r["parts"] == [])
    assert response["parts"] == []
    call = next(r for r in m.of("message") if r["parts"] and r["parts"][0]["t"] == "tool_call")
    assert call["unk"]["/parts/0/name"] == "ambiguous"
    (te,) = m.of("tool_execution")
    assert te["unk"]["/name"] == "ambiguous"


def test_a_turn_number_out_of_place_leaves_the_index_ambiguous():
    turn = {"turnNumber": 5, "userMessage": "a", "assistantResponse": "b", "timestamp": "2026-06-11T08:00:00.000Z",
            "toolCalls": []}
    (m,) = _synthetic(turns=[turn])
    scope = m.get("inv0")
    assert "index" not in scope and scope["unk"]["/index"] == "ambiguous"
    assert "credleak.turn_number_mismatch" in m.codes()


def test_detector_labels_are_counted_never_copied():
    labels = ["label-alpha-one", "label-beta-two"]
    turn = {"turnNumber": 0, "userMessage": "a", "assistantResponse": "b", "timestamp": "2026-06-11T08:00:00.000Z",
            "toolCalls": [], "canaryDetected": True, "canariesFound": labels}
    (m,) = _synthetic(turns=[turn])
    assert m.get("inv0")["ext"]["credleak"]["canaries_found_count"] == 2
    assert not any(label.encode() in m.data for label in labels)


def test_mapping_is_deterministic():
    entry = support.by_criterion("multiturn")
    first = [m.data for m in support.map_entry(entry, sem=False, prov=False)]
    second = [m.data for m in support.map_entry(entry, sem=False, prov=False)]
    assert first == second
