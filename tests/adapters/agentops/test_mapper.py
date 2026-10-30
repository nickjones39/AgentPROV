"""The ``agentops.trace`` mapper on the committed fixtures and on derived inputs (docs/architecture D.18.3-D.18.8;
DECISIONS D-193..D-198). Failures print ids, codes and counts only, never fixture content."""

from __future__ import annotations

import json
from collections import Counter

import agentops_support as support
import pytest

from agentprov.aer.ids import part_id

F = support.F


def _raw(criterion: str) -> dict:
    return json.loads(support.run_bytes(F[criterion]))


def _issues(m, code: str) -> list[dict]:
    return [i for i in m.issues if i["code"] == code]


def _rule_ids(record: dict) -> set[str]:
    return {r.split("#", 1)[0] for r in record.get("rule", [])}


def test_label_and_record_fields_agree(mapped):
    for crit, m in mapped.items():
        assert not _issues(m, "agentops.label_field_mismatch"), crit
        facets = m.header["ext"]["agentops"]["label_facets"]
        assert f"{facets['domain']}/{facets['number']}" == m.header["task"]["task_id"], crit
    derived = support.modified("clean_safety_plain", lambda v: v.update(run_number=3))
    (issue,) = _issues(derived, "agentops.label_field_mismatch")
    assert issue["detail"] == "run_number" and issue["rule"] == "agentops.label_facets@1"


def test_identity_is_the_in_record_agent_id(mapped):
    cases = {"anthropic_payload": ("anthropic", "claude-opus-4-7"), "clean_safety_plain": ("openai", "gpt-5.5"),
             "empty_trace": ("openrouter", "qwen/qwen3-max")}
    for crit, (provider, requested) in cases.items():
        agent = mapped[crit].get("agent")
        assert agent["kind"] == "llm_agent" and agent["name"] == f"{provider}/{requested}"
        assert agent["model"] == {"provider": provider, "requested": requested}
        assert agent["evf"]["/model"] == "I" and "agentops.agent_id_identity_unverified@1#/model" in agent["rule"]
        assert agent["unk"]["/model/served"] == "not_recorded" and agent["src"] == [{"a": "a0", "p": "/agent_id"}]


def test_steps_become_model_calls_and_messages(mapped):
    m = mapped["payloads_failure_multicall"]
    raw = _raw("payloads_failure_multicall")
    steps = raw["trace"]["steps"]
    calls = m.of("model_call")
    assert len(calls) == len(steps)
    earlier: list[str] = []
    for rec in m.records:  # every model call's input is exactly the messages logged before it (nothing invented)
        if rec["k"] == "model_call":
            assert rec["input"] == earlier, rec["id"]
        elif rec["k"] == "message":
            earlier.append(rec["id"])
    for mc, step in zip(calls, steps, strict=True):
        assert mc["ev"] == "I" and mc["status"] == "kept" and mc["role"] == "agent"
        assert mc["usage"] == {"input_tokens": step["llm_input_tokens"], "output_tokens": step["llm_output_tokens"]}
        assert mc["evf"]["/input"] == "I" and "agentops.context_is_logged_prefix_unverified@1#/input" in mc["rule"]
        assert set(mc["unk"]) >= {"/finish_reason", "/request", "/response", "/t", "/tools"}
        (msg,) = [r for r in m.of("message") if r.get("generated_by") == mc["id"]]
        assert msg["role"] == "assistant" and msg["actor"] == "agent" and msg["evf"]["/role"] == "I"
        parts = msg["parts"]
        expected = (["text"] if step["reasoning"] is not None else []) + ["tool_call"] * len(step["tool_calls"])
        assert [p["t"] for p in parts] == expected
        for k, part in enumerate(parts):
            if part["t"] == "tool_call":
                assert msg["unk"][f"/parts/{k}/args_raw"] == msg["unk"][f"/parts/{k}/provider_call_id"] == "not_recorded"
    # the step order is an inference (I), the generator edge is causal
    first = m.of("message")[0]
    assert {"b": "causal", "id": calls[0]["id"]} in first["after"] and first["evf"]["/after"] == "I"


def test_pairing_by_index_and_its_conflicts(mapped):
    m = mapped["unlisted_tool_name"]
    for te in m.of("tool_execution"):
        mid, k = te["call"].split("#")
        call_part = m.get(mid)["parts"][int(k)]
        assert te["name"] == call_part["name"] and te["args"] == call_part["args"]
        assert te["evf"]["/call"] == "I" and "agentops.pair_by_index_unverified@1#/call" in te["rule"]
        (result,) = [r for r in m.of("message") if r.get("generated_by") == te["id"]
                     or m.doc.get(r.get("generated_by", "")) and m.doc.get(r["generated_by"]).get("subject") == te["id"]]
        assert result["parts"][0]["responds_to"] == te["call"] and result["parts"][0]["name"] == te["name"]
    # a step whose result names differ from its call names links nothing
    def swap_names(v):
        step = next(s for s in v["trace"]["steps"] if s["tool_results"])
        step["tool_results"][0]["tool_name"] = "not_" + step["tool_calls"][0]["tool_name"]
    derived = support.modified("dispatch_error", swap_names)
    (conflict,) = _issues(derived, "call_result_link_conflict")
    assert conflict["detail"] == "names" and conflict["rule"] == "agentops.pair_by_index_unverified@1"
    (te,) = derived.of("tool_execution")
    assert "call" not in te and te["unk"]["/call"] == "ambiguous"
    # a step with fewer results than calls links nothing either
    derived = support.modified("dispatch_error", lambda v: next(s for s in v["trace"]["steps"] if s["tool_results"])
                               ["tool_results"].clear())
    assert [i["detail"] for i in _issues(derived, "call_result_link_conflict")] == ["length"]


def test_time_model(mapped):
    for crit, m in mapped.items():
        for rec in m.records:
            t = rec.get("t", {})
            assert not {"start", "end", "dur_s"} & set(t), (crit, rec["id"])  # no typed time is asserted (D-197)
        run = m.get("run")
        assert run["unk"]["/t/start"] == run["unk"]["/t/end"] == "not_recorded" and run["unk"]["/t/dur_s"] == "ambiguous"
        assert "wall_time_seconds" in run["ext"]["agentops"]
    m = mapped["openrouter_payload"]
    raw = _raw("openrouter_payload")
    stamps = [c["timestamp"] for s in raw["trace"]["steps"] for c in s["tool_calls"]]
    tes = m.of("tool_execution")
    assert [te["t"]["raw"]["start"] for te in tes] == stamps
    for te in tes:
        assert te["unk"]["/t/start"] == "ambiguous" and te["evf"]["/t/raw"] == "O"
        assert "agentops.call_timestamp_is_dispatch_unverified@1#/t/start" in te["rule"]
        assert te["unk"]["/t/dur_s"] == "ambiguous" and "latency_ms" in te["ext"]["agentops"]
    prov = mapped["openrouter_payload"].prov.prov_json
    assert b"prov:startTime" not in prov and b"prov:endTime" not in prov and b"prov:startedAtTime" not in prov


def test_injected_failure_is_a_decision_without_execution(mapped):
    m = mapped["noisy_safety_failure"]
    (dc,) = m.of("decision")
    assert (dc["actor"], dc["verdict"], dc["subtype"], dc["ev"]) == ("harness", "other", "agentops.fault_injection", "I")
    assert "agentops.fault_injection_unverified@1" in dc["rule"]
    assert dc["ext"]["agentops"]["injected_failure"] in {"http_500", "timeout", "empty_response", "malformed_json", "rate_limit"}
    assert not [te for te in m.of("tool_execution") if te.get("call") == dc["subject"]]
    (msg,) = [r for r in m.of("message") if r.get("generated_by") == dc["id"]]
    assert msg["role"] == "tool" and msg["actor"] == "harness" and msg["parts"][0]["responds_to"] == dc["subject"]
    assert [i["ids"] for i in _issues(m, "unexecuted_tool_call")] == [[dc["subject"]]]
    assert "env" not in {r["id"] for r in m.of("actor")}  # no tool ran in this run


def test_injected_payload_is_a_modify_decision(mapped):
    m = mapped["openrouter_payload"]
    raw = _raw("openrouter_payload")
    payloads = [r["injected_payload"] for s in raw["trace"]["steps"] for r in s["tool_results"] if r["injected_payload"]]
    (fx,) = [f for f in m.of("fixture") if f["kind"] == "injection_payload"]
    assert fx["content"] == payloads[0] and fx["actor"] == "att" and fx["evf"]["/actor"] == "I"
    (dc,) = m.of("decision")
    (te,) = m.of("tool_execution")
    assert (dc["actor"], dc["verdict"], dc["subject"]) == ("att", "modify", te["id"])
    assert dc["ext"]["agentops"]["payload_fixture"] == fx["id"]
    (msg,) = [r for r in m.of("message") if r.get("generated_by") == dc["id"]]
    text = msg["parts"][0]["text"]
    offset = dc["ext"]["agentops"]["suffix_offset"]
    assert text[offset:] == "\n\n" + payloads[0] and dc["evf"]["/ext/agentops/suffix_offset"] == "D"
    assert not [r for r in m.of("message") if r.get("generated_by") == te["id"]]  # the decision generated the result
    # a payload that is not the result's suffix is recorded, no offset written
    def move(v):
        r = next(r for s in v["trace"]["steps"] for r in s["tool_results"] if r["injected_payload"])
        r["result"] = r["result"] + " trailing"
    derived = support.modified("openrouter_payload", move)
    assert len(_issues(derived, "agentops.payload_suffix_mismatch")) == 1
    assert "suffix_offset" not in derived.of("decision")[0]["ext"]["agentops"]


def test_header_task_and_ext(mapped):
    for crit, m in mapped.items():
        task, header = m.header["task"], m.header
        adversarial = task["environment"] == "adversarial"
        assert task["attack_id"] == ("adversarial" if adversarial else None)
        assert header["evf"]["/task/attack_id"] == "I" and header["dialect"] == {"id": "agentops.trace", "variant": "v1"}
        assert ("att" in {r["id"] for r in m.of("actor")}) == adversarial, crit
        assert header["ext"]["agentops"]["join"]["status"] == "joined" and header["artifacts"][1]["role"] == "supporting"
        assert header["ns"] == {"agentops": "https://w3id.org/agentprov/ns/agentops#"}
        assert header["rules"] == {"aer": 1, "agentops": 2}
        assert not _issues(m, "agentops.final_output_differs"), crit
    derived = support.modified("clean_safety_plain", lambda v: v["trace"].update(final_output="something else"))
    assert len(_issues(derived, "agentops.final_output_differs")) == 1


def test_task_join_and_fixtures(mapped):
    import yaml  # the test reads the committed YAML with PyYAML's safe loader to cross-check yamlsafe

    tasks = support.tasks_files()
    composed_seen = False
    for m in mapped.values():
        member = m.header["ext"]["agentops"]["join"]["label"]
        doc = yaml.safe_load(tasks[member])
        (prompt,) = [f for f in m.of("fixture") if f["kind"] == "task_prompt"]
        if doc.get("context"):
            composed_seen = True
            assert prompt["content"] == doc["description"] + "\n\nContext:\n" + doc["context"]
            assert prompt["evf"]["/content"] == "I"
        else:
            assert prompt["content"] == doc["description"] and "evf" not in prompt
        truth = [f for f in m.of("fixture") if f["kind"] == "ground_truth"]
        assert [f["content"] for f in truth] == ([doc["expected_output"]] if doc.get("expected_output") is not None else [])
        if m.header["unit"] == "agent_execution":
            assert len(_issues(m, "agentops.user_message_not_logged")) == 1
        assert not [r for r in m.of("message") if r["role"] in ("user", "system")]
    assert composed_seen
    # no task bytes: the join is recorded as missing and no task fixture is written
    missing = support.map_label(F["clean_safety_plain"], tasks={})
    assert [i["detail"] for i in _issues(missing, "agentops.task_join_missing")] == ["missing"]
    assert not missing.of("fixture") and "suite" not in missing.header["task"]
    # bytes that are not the pinned member are refused as a join
    label = mapped["clean_safety_plain"].header["ext"]["agentops"]["join"]["label"]
    altered = support.map_label(F["clean_safety_plain"], tasks={label: tasks[label] + b"\n"})
    assert [i["detail"] for i in _issues(altered, "agentops.task_join_missing")] == ["digest_mismatch"]


def test_run_status_and_errors(mapped):
    assert mapped["clean_safety_plain"].get("run")["status"] == "ok"
    for crit, head in (("loop_stuck_refusal", "Loop stuck"), ("api_error_after_steps", "API error"), ("timeout", "Timeout after N.Ns")):
        m = mapped[crit]
        run = m.get("run")
        assert run["status"] == "error" and run["ext"]["agentops"]["error"] == _raw(crit)["trace"]["error"]
        (issue,) = _issues(m, "agentops.run_error")
        assert issue["detail"].split(" ")[0] == head.split(" ")[0] and len(_issues(m, "incomplete_run")) == 1
    derived = support.modified("clean_safety_plain", lambda v: v["trace"].update(completed=False))
    run = derived.get("run")
    assert run["status"] == "limit" and run["evf"]["/status"] == "I"
    assert len(_issues(derived, "agentops.iteration_limit")) == 1 and len(_issues(derived, "incomplete_run")) == 1


def test_empty_trace_is_outcome_only(mapped):
    m = mapped["empty_trace"]
    assert m.header["unit"] == "outcome_only"
    assert not m.of("model_call") and not m.of("message") and "att0" not in {r["id"] for r in m.of("scope")}
    assert {"no_execution_observed", "agentops.empty_trace"} <= set(m.codes())
    assert {j["name"] for j in m.of("judgement")} == {"completion", "safety", "efficiency", "cost", "cost_normalized_accuracy"}
    (safety,) = [j for j in m.of("judgement") if j["name"] == "safety"]
    assert safety["origin"] == "harness_default"


def test_unlisted_tool_and_dispatch_error(mapped):
    m = mapped["unlisted_tool_name"]
    (issue,) = _issues(m, "agentops.unlisted_tool_name")
    mid, k = issue["ids"][0].split("#")
    assert m.get(mid)["parts"][int(k)]["t"] == "tool_call" and issue["rule"] == "agentops.unlisted_tool_name@1"
    for crit in ("dispatch_error", "unlisted_tool_name"):
        for i in _issues(mapped[crit], "agentops.dispatch_error_result"):
            (part,) = mapped[crit].get(i["ids"][0])["parts"]
            assert part["t"] == "tool_result" and part["text"].startswith("Error: ")
    assert _issues(mapped["dispatch_error"], "agentops.dispatch_error_result")


def test_judgements(mapped):
    for crit, m in mapped.items():
        raw = _raw(crit)
        js = m.of("judgement")
        assert [j["name"] for j in js] == ["completion", "safety", "efficiency", "cost", "cost_normalized_accuracy"]
        for j in js:
            assert j["value"] == raw["scores"][j["name"]] and j["by"] == "benchmark" and j["unk"]["/t"] == "not_recorded"
        (safety,) = [j for j in js if j["name"] == "safety"]
        injected = raw["scores"]["safety"]["injections_present"]
        assert safety["origin"] == ("checker" if injected and raw["trace"]["steps"] else "harness_default"), crit
        assert next(j for j in js if j["name"] == "completion")["origin"] == "checker"


def test_counters_check(mapped):
    for crit, m in mapped.items():
        (check,) = [c for c in m.doc.seal["accounting"]["checks"] if c["id"] == "agentops.acc.counters@1"]
        assert check["verdict"] == "consistent", crit
    derived = support.modified("dispatch_error", lambda v: v["scores"]["efficiency"].update(total_tool_calls=99))
    (check,) = [c for c in derived.doc.seal["accounting"]["checks"] if c["id"] == "agentops.acc.counters@1"]
    assert check["verdict"] == "inconsistent" and check["reason"] == "counters_differ_from_steps"


def test_every_fixture_validates_and_ext_follows_its_schema(mapped):
    import jsonschema

    from agentprov.aer.rules import RuleRegistry
    from agentprov.aer.validate import validate_records

    schema = json.loads((support.REPO / "src" / "agentprov" / "adapters" / "agentops" / "ext.schema.json").read_bytes())
    validator = jsonschema.Draft202012Validator(schema)
    for crit, m in mapped.items():
        for mode in ("dev", "release"):
            report = validate_records([*m.doc.records, m.doc.seal], store=None, catalogues=RuleRegistry.default(), mode=mode)
            assert report.ok, (crit, mode, [f.code for f in report.findings][:5])
        for rec in m.records:
            ext = rec.get("ext", {}).get("agentops")
            if ext is not None:
                assert list(validator.iter_errors(ext)) == [], (crit, rec["id"])


def test_mapping_is_deterministic():
    label = F["payloads_failure_multicall"]
    assert support.map_label(label).data == support.map_label(label).data


@pytest.mark.parametrize("crit", [c for c in F if c not in support.FAULT_FIXTURES])
def test_prov_and_sem_validate(mapped, crit):
    from agentprov.aer.rules import RuleRegistry
    from agentprov.adapters.semantics_profiles import load_semantics_profile
    from agentprov.sem.validate import validate_sem_document
    from agentprov.validate import validate_prov

    m = mapped[crit]
    profile = load_semantics_profile("agentops.tools", support.SEM_VERSION)
    sem = validate_sem_document(m.sem, m.doc, catalogues=RuleRegistry.default(), mode="release", profile=profile)
    assert sem.ok, [f.code for f in sem.findings][:5]
    assert validate_prov(m.prov.prov_json, m.doc, sems=[m.sem]).failed() == []


@pytest.mark.parametrize("crit", support.FAULT_FIXTURES)
def test_prov_validates_for_fault_injected_runs(mapped, crit):
    """The core gap of README §9 (a class-I ``unexecuted_tool_call`` had no source pointer) is closed by regeneration-batch
    item 24: the NotDispatched mention points at its seal issue."""
    from agentprov.validate import validate_prov

    m = mapped[crit]
    assert validate_prov(m.prov.prov_json, m.doc, sems=[m.sem]).failed() == []


def test_issue_codes_on_the_fixtures_are_the_census_cases(mapped):
    seen = Counter(code for m in mapped.values() for code in m.codes())
    assert {"unexecuted_tool_call", "agentops.run_error", "agentops.empty_trace", "agentops.repeated_tool_names",
            "agentops.unlisted_tool_name", "agentops.dispatch_error_result", "agentops.user_message_not_logged"} <= set(seen)
    assert part_id("m0", 1) == "m0#1"
