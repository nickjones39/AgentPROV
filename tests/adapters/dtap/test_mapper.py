"""The ``dtap.trajectory`` mapper (docs/architecture D.16.3-D.16.10): golden AER bytes per fixture, pairing per harness,
time, judgements, quality flags and the evidence classes the design fixes. Synthetic step logs (built here at run time,
never committed) cover the cases the real fixtures do not hold."""

from __future__ import annotations

import copy
import hashlib
import json
import os
from collections import Counter
from pathlib import Path

import dtap_support as support

from agentprov.adapters.dtap.pairing import pair
from agentprov.io.jsonschema_subset import check_against_schema

GOLDEN = Path(__file__).resolve().parent / "golden" / "aer_digests.json"
SRC = support.REPO / "src" / "agentprov" / "adapters" / "dtap"


def test_golden_aer_bytes_per_fixture(mapped):
    """D.16.14 test 1: the AER bytes of every fixture are pinned (dev-mode goldens; AGENTPROV_REGEN_DTAP_GOLDEN=1)."""
    digests = {fid: hashlib.sha256(m.data).hexdigest() for fid, m in sorted(mapped.items())}
    if os.environ.get("AGENTPROV_REGEN_DTAP_GOLDEN") == "1":
        GOLDEN.parent.mkdir(exist_ok=True)
        GOLDEN.write_text(json.dumps(digests, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    assert json.loads(GOLDEN.read_text(encoding="utf-8")) == digests


def test_every_fixture_seals_validates_and_derives(mapped):
    from agentprov.aer.rules import RuleRegistry
    from agentprov.validate import validate_prov

    registry = RuleRegistry.default()  # what validate_prov builds per call when none is given; built once here
    for fid, m in mapped.items():
        assert not m.outcome.degenerate, fid
        report = validate_prov(m.prov.prov_json, m.doc, sems=[m.sem], registry=registry)
        assert [o.id for o in report.failed()] == [], fid


def test_header_identity_task_and_ext_schema(mapped):
    schema = json.loads((SRC / "ext.schema.json").read_text(encoding="utf-8"))
    for fid, m in mapped.items():
        h = m.header
        assert h["dialect"] == {"id": "dtap.trajectory", "variant": "v1"} and h["profile"]["id"] == "dtap-bench"
        assert h["source_key"]["loc"] == {"p": ""} and h["rules"] == {"aer": 1, "dtap": 3}
        assert h["task"]["benchmark"] == "dtap" and {"a": "a0", "o": "/path"} in h["src"]
        assert h["unk"]["/task/defense_id"] == "not_recorded"
        for record in m.records:
            ext = record.get("ext", {}).get("dtap")
            if ext is not None:
                assert check_against_schema(ext, schema) == [], (fid, record["id"])
    assert mapped["F09"].header["task"]["attack_id"] == "direct_prompt"
    assert mapped["F10"].header["task"]["attack_id"] is None and mapped["F10"].header["evf"]["/task/attack_id"] == "I"
    assert mapped["F01"].header["task"]["task_id"] == "benign/math/57"


def test_actors_and_model_identity_from_the_path(mapped):
    m = mapped["F07"]
    agent, harness = m.get("agent"), m.get("harness")
    assert agent["model"] == {"requested": "claude-opus-4-6"} and agent["ev"] == "I"
    assert "dtap.path_model_identity@1" in agent["rule"]
    assert harness["name"] == "openclaw" and harness["evf"] == {"/name": "I"}
    assert {"a": "a0", "p": "/traj_info/metadata/framework"} in harness["src"]
    assert m.get("att")["name"] == "indirect" and m.get("judge")["kind"] == "judge"
    assert mapped["F01"].doc.get("att") is None  # benign: no attacker


def test_pairing_strict_alternation(mapped):
    m = mapped["F01"]
    te = m.of("tool_execution")
    assert [t["call"] for t in te] == ["m3#0"] and te[0]["evf"]["/call"] == "I"
    assert "dtap.pair_strict_alternation@1#/call" in te[0]["rule"]
    result = m.get("m4")
    assert result["parts"][0]["responds_to"] == "m3#0" and result["evf"]["/parts/0/responds_to"] == "I"
    # List MCP Tools meta-steps are harness activities with their tool-name lists, never messages or executions
    acts = [r for r in m.of("activity") if r["type"] == "dtap:list_mcp_tools"]
    assert len(acts) == 2 and all(a["actor"] == "harness" and a["evf"]["/actor"] == "I" for a in acts)
    assert [r["generated_by"] for r in m.of("artefact")] == [a["id"] for a in acts]
    assert m.doc.get("m0") is None and m.doc.get("m1") is None


def test_pairing_claudesdk_batches(mapped):
    f04, f05 = mapped["F04"], mapped["F05"]
    batch = [i for i in f04.issues if i["code"] == "dtap.pairing_ambiguous_batch"]
    assert len(batch) == 1 and batch[0]["detail"] == "contiguous" and batch[0]["rule"] == "dtap.pair_interleaved_fifo@1"
    unknown = [r for r in f04.of("message") if r["role"] == "tool" and "name" not in r["parts"][0]]
    assert unknown and unknown[0]["unk"]["/parts/0/name"] == "ambiguous"
    assert unknown[0]["ext"]["dtap"]["result_tool_name"] == "unknown"
    assert any(r["parts"][0].get("name") == "ToolSearch" for r in f04.of("message") if r["role"] == "agent" and r["parts"][0]["t"] == "tool_call")
    assert [i["detail"] for i in f05.issues if i["code"] == "dtap.pairing_ambiguous_batch"] == ["interleaved"]


def test_pairing_googleadk_contiguous_batch(mapped):
    m = mapped["F06"]
    batch = [i for i in m.issues if i["code"] == "dtap.pairing_ambiguous_batch"]
    assert [i["detail"] for i in batch] == ["repeated_names"] and batch[0]["rule"] == "dtap.pair_contiguous_batch_fifo@1"
    assert all("dtap.pair_contiguous_batch_fifo@1#/call" in t["rule"] for t in m.of("tool_execution") if "call" in t)


def test_unanswered_call_and_orphan_result():
    m = support.map_steps([{"role": "user", "state": "go", "metadata": {}}, support.result("x"), support.call("a", {"q": 1}), support.result("a"), support.call("b", {})],
             framework="claudesdk")
    codes = {i["code"]: i for i in m.issues}
    assert codes["unexecuted_tool_call"]["ids"] == ["m4#0"] and codes["unexecuted_tool_call"]["rule"] == "dtap.call_without_result@1"
    assert codes["orphan_tool_result"]["ids"] == ["m1"]
    orphan_te = next(t for t in m.of("tool_execution") if "call" not in t)
    assert orphan_te["unk"]["/call"] == "ambiguous" and m.get("m1")["unk"]["/parts/0/responds_to"] == "not_recorded"



def test_unanswered_call_is_not_dispatched_with_its_seal_issue_as_premise():
    """Regeneration-batch item 24: the class-I ``unexecuted_tool_call`` (``dtap.call_without_result@1``) gives the request
    part ``apv:dispatchStatus apv:NotDispatched`` in an inference bundle that points at the seal issue, and tier 4 passes."""
    from agentprov.validate import validate_prov

    label, data = support.run([{"role": "user", "state": "go", "metadata": {}}, support.call("a", {"q": 1}), support.result("a"),
                               support.call("b", {})], framework="claudesdk")
    m = support.map_label(label, runs={label: data}, tasks={}, prov=True)
    index = next(i for i, issue in enumerate(m.issues) if issue["code"] == "unexecuted_tool_call")
    prov = json.loads(m.prov.prov_json)
    mentions = [body for bundle in prov.get("bundle", {}).values() for body in bundle.get("entity", {}).values()
                if body.get("apv:dispatchStatus", {}).get("$") == "apv:NotDispatched"]
    assert len(mentions) == 1
    assert mentions[0]["apv:sourcePointer"] == f"seal/issues/{index}"
    assert mentions[0]["apv:basisRule"] == "dtap.call_without_result@1"
    assert validate_prov(m.prov.prov_json, m.doc, sems=[m.sem]).failed() == []

def test_strict_harness_shape_or_name_conflict_links_nothing():
    m = support.map_steps([support.call("a", {}), support.call("b", {}), support.result("a"), support.result("b")])
    conflict = [i for i in m.issues if i["code"] == "call_result_link_conflict"]
    assert len(conflict) == 1 and conflict[0]["detail"] == "shape"
    assert all("call" not in t and t["unk"]["/call"] == "ambiguous" for t in m.of("tool_execution"))
    m2 = support.map_steps([support.call("a", {}), support.result("other")])
    assert [i["detail"] for i in m2.issues if i["code"] == "call_result_link_conflict"] == ["name"]


def test_call_without_params_has_empty_args_only_for_an_empty_argument_list():
    steps = [support.call("list_workspaces"), support.result("list_workspaces"), {"role": "agent", "action": "odd", "metadata": {"tool_name": "y", "server": "s"}},
             support.result("y")]
    m = support.map_steps(steps)
    assert m.get("m0")["parts"][0]["args"] == {} and m.get("m0")["evf"]["/parts/0/args"] == "D"
    assert m.get("m2")["parts"][0]["args"] is None and m.get("m2")["unk"]["/parts/0/args"] == "ambiguous"


def test_pairing_unit_rules():
    steps = [support.call("a", {}), support.call("b", {}), {"role": "agent", "action": "send_message_to_user", "metadata": {"message": "m"}},
             support.result("a"), support.call("c", {}), support.result("unknown"), support.result("c")]
    p = pair(steps, "claudesdk")
    assert p.links == {3: 0, 5: 1, 6: 4} and len(p.batches) == 1 and p.batches[0].detail == "interleaved"
    g = pair([support.call("a", {}), support.call("a", {}), support.result("a"), support.result("a")], "googleadk")
    assert g.links == {2: 0, 3: 1} and g.batches[0].detail == "repeated_names"


def test_model_calls_one_per_segment_with_the_logged_prefix(mapped):
    m = mapped["F01"]
    calls = m.of("model_call")
    assert [c["input"] for c in calls] == [["m2"], ["m2", "m3", "m4"]]
    for c in calls:
        assert c["ev"] == "I" and c["evf"]["/input"] == "I" and c["status"] == "kept" and c["role"] == "agent"
        assert set(c["unk"]) == {"/finish_reason", "/params", "/request", "/response", "/t", "/usage"}
    agent = [r for r in m.of("message") if r["role"] == "agent"]
    assert all(r["evf"]["/generated_by"] == "I" and r["evf"]["/actor"] == "I" for r in agent)
    # a logged tool list is the calls' tools fixture (I)
    f07 = mapped["F07"]
    tools = next(r for r in f07.of("fixture") if r["kind"] == "tool_definitions")
    assert all(c["tools"] == tools["id"] and c["evf"]["/tools"] == "I" for c in f07.of("model_call"))


def test_time_aware_and_naive(mapped):
    aware, naive = mapped["F01"].get("run"), mapped["F06"].get("run")
    assert aware["t"] == {"raw": {"end": "2026-02-20T21:35:03.584830+00:00"}} and aware["unk"]["/t/end"] == "ambiguous"
    assert aware["ext"]["dtap"]["timestamp_zone"] == "utc" and naive["ext"]["dtap"]["timestamp_zone"] == "none"
    assert "dtap.timestamp_is_run_end_unverified@1#/t/end" in aware["rule"]
    assert aware["unk"]["/t/dur_s"] == "ambiguous" and "duration" in aware["ext"]["dtap"]
    assert "dtap.duration_no_clock@1#/t/dur_s" in aware["rule"]
    for fid, m in mapped.items():  # no time is invented anywhere: no start, no per-step time
        for record in m.records[1:]:
            t = record.get("t", {})
            assert set(t) <= {"raw"}, (fid, record["id"])
        core = [b for b in m.prov.bundles if "core" in str(b)] if hasattr(m.prov, "bundles") else []
        assert b"prov:endTime" not in m.prov.prov_json and b"prov:startTime" not in m.prov.prov_json, fid
        del core


def test_harness_failure_f08(mapped):
    m = mapped["F08"]
    assert m.get("run")["status"] == "error"
    error = next(r for r in m.of("activity") if r["type"] == "dtap:harness_error")
    assert error["status"] == "error" and error["evf"] == {"/actor": "I", "/after": "I"} or error["evf"]["/actor"] == "I"
    text = next(r for r in m.of("artefact") if r["type"] == "dtap:error_text")
    assert text["generated_by"] == error["id"]
    echo = [r for r in m.of("message") if r["role"] == "agent" and r.get("unk", {}).get("/actor") == "ambiguous"]
    assert len(echo) == 1 and "generated_by" not in echo[0] and "dtap.harness_error_echo@1#/actor" in echo[0]["rule"]
    assert Counter(m.codes())["dtap.harness_failure"] == 1 and Counter(m.codes())["dtap.judgement_on_failed_run"] == 1


def test_direct_prompt_f09(mapped):
    m = mapped["F09"]
    j0 = next(j for j in m.of("judgement") if j["name"] == "task_success")
    assert j0["origin"] == "harness_default" and "dtap.direct_task_eval_not_applicable@1#/origin" in j0["rule"]
    assert not [f for f in m.of("fixture") if f["kind"] == "injection_payload"]  # the direct configuration's steps are not applied
    assert "dtap.direct_prompt_no_injection@1" in m.header["rule"]


def test_control_split_f10(mapped):
    m = mapped["F10"]
    assert m.doc.get("att") is None and not [f for f in m.of("fixture") if f["kind"] in ("injection_payload", "other")]
    assert "dtap.control_split_no_attack@1#/task/attack_id" in m.header["rule"]


def test_judge_error_and_empty_trajectory_f11(mapped):
    m = mapped["F11"]
    assert m.header["unit"] == "outcome_only" and m.doc.get("att0") is None and not m.of("message")
    codes = Counter(m.codes())
    assert codes["no_execution_observed"] == 1 and codes["dtap.empty_trajectory"] == 1 and codes["dtap.judge_error"] == 1
    assert m.get("run")["status"] == "error" and {"a": "a0", "p": "/traj_info/metadata/error"} in m.get("run")["src"]
    assert len(m.of("judgement")) == 2


def test_goal_rewritten_at_eval_f18(mapped):
    m = mapped["F18"]
    goals = [f for f in m.of("fixture") if f.get("subtype", "").startswith("dtap.attack_goal")]
    assert [f["subtype"] for f in goals] == ["dtap.attack_goal", "dtap.attack_goal_at_eval"]
    assert all(f["actor"] == "att" and f["evf"]["/actor"] == "I" for f in goals)
    assert "goal_text_updated" in goals[1]["ext"]["dtap"] and Counter(m.codes())["dtap.goal_rewritten_at_eval"] == 1


def test_payload_fixtures_existence_i_content_d(mapped):
    m = mapped["F03"]
    payloads = [f for f in m.of("fixture") if f["kind"] == "injection_payload"]
    assert payloads and all(f["ev"] == "I" and f["evf"] == {"/actor": "I", "/content": "D", "/vector": "D"} for f in payloads)
    assert all(f["src"] == [{"a": m.header["artifacts"][2]["id"]}] for f in payloads)
    assert {f["vector"].split(":", 1)[0] for f in payloads} == {"environment", "tool"}
    assert "dtap.config_content_tier_a@1" in payloads[0]["rule"]
    # tier B/C, missing configuration: no run content from the configuration
    for fid in ("F12", "F14", "F15"):
        assert not [f for f in mapped[fid].of("fixture") if f["kind"] == "injection_payload"], fid


def test_rerun_pair_f20(mapped):
    a, b = mapped["F20a"], mapped["F20b"]
    for m in (a, b):
        assert m.header["ext"]["dtap"]["rerun"] == {"group_size": 2, "stems": ["20260402_213642", "20260403_154959"]}
        assert m.header["ext"]["dtap"]["judge_link"]["resolved"] is False and not m.of("judgement")
        assert Counter(m.codes())["dtap.judge_attempt_unresolved"] == 1
        assert {art["role"] for art in m.header["artifacts"][1:]} == {"supporting"} and len(m.header["artifacts"]) == 4
    # a judge whose recorded text is found in exactly one attempt is linked to it (D), the other attempt is unjudged
    runs = support.runs_files()
    d = support.F["F20a"].rsplit("/", 1)[0]
    from agentprov.adapters.dtap.matcher import normalise, serialise, strings

    judge = json.loads(runs[f"{d}/judge_result.json"])
    other = normalise(serialise(json.loads(runs[support.F["F20a"]])))
    unique = next(text for text in strings(json.loads(runs[support.F["F20b"]])["trajectory"])
                  if len(normalise(text)) >= 40 and normalise(text) not in other)
    judge["attack_message"] = unique  # a judge string is a needle as a whole
    runs[f"{d}/judge_result.json"] = json.dumps(judge).encode()
    won, lost = support.map_label(support.F["F20b"], runs=runs), support.map_label(support.F["F20a"], runs=runs)
    assert won.header["ext"]["dtap"]["judge_link"]["method"] == "content" and len(won.of("judgement")) == 2
    j = won.of("judgement")[0]
    assert j["evf"]["/subject"] == "D" and "dtap.judge_attempt_by_content@1#/subject" in j["rule"]
    assert not lost.of("judgement") and Counter(lost.codes())["dtap.unjudged_attempt"] == 1
    assert lost.header["ext"]["dtap"]["judge_link"]["resolved_to"] == won.header["ex"]


def test_single_attempt_judge_is_colocated_or_matched(mapped):
    m = mapped["F01"]
    j = m.of("judgement")[0]
    assert m.header["ext"]["dtap"]["judge_link"]["method"] in ("colocation", "content")
    if m.header["ext"]["dtap"]["judge_link"]["method"] == "colocation":
        assert j["evf"]["/subject"] == "I" and "dtap.judge_dir_colocation@1#/subject" in j["rule"]
    assert j["origin"] == "checker" and j["evf"]["/origin"] == "I" and j["by"] == "benchmark"


def test_judge_only_directory(mapped):
    m = mapped["X02"]
    assert m.header["unit"] == "outcome_only" and m.header["artifacts"][0]["role"] == "primary"
    js = m.of("judgement")
    assert js and all(j["evf"]["/subject"] == "D" and "dtap.judge_without_trajectory@1#/subject" in j["rule"] for j in js)
    assert Counter(m.codes())["no_execution_observed"] == 1 and m.doc.get("user") is None


def test_rejudged_result(mapped):
    m = mapped["X01"]
    j1, j2 = (j for j in m.of("judgement") if j["name"] == "attack_success")
    assert j1["origin"] == "checker" and {"a": "a1", "p": "/audit_correction/original_attack_success"} in j1["src"]
    assert j2["origin"] == "recomputed" and j2["revises"] == j1["id"] and j2["evf"]["/origin"] == "D"
    assert {"dtap.audit_correction_effective@1#/origin", "dtap.audit_correction_effective@1#/revises"} <= set(j2["rule"])
    assert j2["ext"]["dtap"]["audit"]["patch_id"] == "h5_rejudge_20260426"
    assert j1["unk"]["/t"] == j2["unk"]["/t"] == "not_recorded"


def test_partial_trajectory():
    """The partial file is too large to commit (687 KB); the file name is the only evidence, so F01's bytes under that
    name exercise the rule."""
    runs = support.runs_files()
    label = support.F["F01"].rsplit("/", 1)[0] + "/partial_trajectory.json"
    runs[label] = runs.pop(support.F["F01"])
    m = support.map_label(label, runs=runs)
    codes = Counter(m.codes())
    assert codes["dtap.partial_trajectory"] == 1 and codes["incomplete_run"] == 1


def test_counters_check(mapped):
    for fid, m in mapped.items():
        checks = [c for c in m.doc.seal["accounting"]["checks"] if c["id"] == "dtap.acc.counters@1"]
        if fid == "X02":
            assert checks == []
            continue
        assert len(checks) == 1 and checks[0]["verdict"] == "consistent", fid
    label, data = support.run([support.call("a", {}), support.result("a")])
    bad = json.loads(data)
    bad["traj_info"]["tool_count"] = 7
    m = support.map_label(label, runs={label: json.dumps(bad).encode()}, tasks={})
    check = next(c for c in m.doc.seal["accounting"]["checks"] if c["id"] == "dtap.acc.counters@1")
    assert check["verdict"] == "inconsistent" and check["reason"] == "counters_differ_from_steps"


def test_quality_flags_each_raise_their_issue_once(mapped):
    """D.16.10: every flag a fixture carries is raised exactly once per execution."""
    expected = {
        "F08": ["dtap.harness_failure", "dtap.judgement_on_failed_run"], "F11": ["dtap.empty_trajectory", "no_execution_observed", "dtap.judge_error"],
        "F12": ["dtap.config_join_unverified"], "F15": ["dtap.config_missing"], "F20a": ["dtap.judge_attempt_unresolved"],
        "X02": ["no_execution_observed"], "F18": ["dtap.goal_rewritten_at_eval"],
    }
    for fid, codes in expected.items():
        counts = Counter(mapped[fid].codes())
        assert all(counts[c] == 1 for c in codes), (fid, counts)
    users = [m for m in mapped.values() if any(f["kind"] == "task_prompt" for f in m.of("fixture"))]
    for m in users:
        if m.header["unit"] == "agent_execution":
            assert Counter(m.codes())["dtap.user_step_not_logged"] == 1


def test_no_unknown_sentinel_reaches_a_typed_tool_name(mapped):
    for fid, m in mapped.items():
        for r in m.of("message"):
            for p in r["parts"]:
                assert str(p.get("name", "")).lower() != "unknown", fid
        assert all(str(t["name"]).lower() != "unknown" or t.get("unk", {}).get("/name") == "ambiguous" for t in m.of("tool_execution"))


def test_disclosure_issues_on_derived_inputs():
    """Inputs derived at test time (never committed): a verified 500-character cut, a differing final response, a
    dataset-side truncation marker and a reformatted telecom task id (D.16.3, D.16.5)."""
    base = json.loads(support.runs_files()[support.F["F01"]])
    long_text = "Compute the integral. " * 40
    base["task_info"].update(original_instruction=long_text[:500], task_id="credential_takeover", domain="telecom")
    base["trajectory"][2]["state"] = long_text[:500]
    base["trajectory"][4]["state"] = "output [truncated 300 chars]"
    base["traj_info"]["agent_final_response"] = "something else"
    label = "openaisdk/gpt-5.2/telecom/benign/1/20260101_000000.json"
    config = json.dumps({"Task": {"task_id": "credential_takeover_001", "task_instruction": long_text}}).encode()
    m = support.map_label(label, runs={label: json.dumps(base).encode()}, tasks={"telecom/benign/1/config.yaml": config})
    by_code = {i["code"]: i for i in m.issues}
    assert by_code["dtap.task_info_truncated"]["rule"] == "dtap.instruction_cut_500@1"
    assert by_code["dtap.final_response_differs"]["rule"] == "dtap.final_response_copy@1"
    assert by_code["dtap.source_truncation_marker"]["rule"] == "dtap.source_truncation_marker@1"
    join = m.header["ext"]["dtap"]["join"]
    assert join["instruction"] == "prefix_500" and join["tier"] == "A" and join["task_id"] == "reformatted"
    assert m.header["evf"]["/ext/dtap/join/task_id"] == "I"
    assert "dtap.task_id_reformatted@1#/ext/dtap/join/task_id" in m.header["rule"]
    unverified = support.map_label(label, runs={label: json.dumps(base).encode()}, tasks={})
    assert {i["code"]: i for i in unverified.issues}["dtap.task_info_truncated"]["rule"] == "dtap.instruction_length_500_unverified@1"


def test_mapping_is_deterministic():
    a = support.map_label(support.F["F05"])
    b = support.map_label(support.F["F05"])
    assert a.data == b.data
    c = support.map_label(support.F["F05"], runs=copy.deepcopy(support.runs_files()))
    assert c.data == a.data
