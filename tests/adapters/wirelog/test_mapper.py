"""The ``wirelog.run_dir`` mapper on the committed Zenodo 21944598 fixtures and derived inputs (docs/architecture D.20.3-
D.20.8; DECISIONS D-281..D-284). Assertions name ids, kinds, rules and counts; no fixture content is printed."""

from __future__ import annotations

import json

import jsonschema
import pytest
import wirelog_support as support

from agentprov.aer.rules import RuleRegistry
from agentprov.aer.validate import validate_records
from agentprov.sem.validate import validate_sem_document
from agentprov.validate import validate_prov


def _rules(rec: dict) -> set[str]:
    return {r.split("#", 1)[0] for r in rec.get("rule", [])}


def _issue(m: support.Mapped, code: str) -> dict:
    return next(i for i in m.issues if i["code"] == code)


# ------------------------------------------------------------------------------------------------ whole-record checks
def test_release_validation_sem_prov_and_determinism(mapped):
    reg = RuleRegistry.default()
    for crit, m in mapped.items():
        rep = validate_records([*m.doc.records, m.doc.seal], store=None, catalogues=reg, mode="release")
        assert not rep.findings, (crit, sorted({f.code for f in rep.findings}))
        from agentprov.adapters.semantics_profiles import load_semantics_profile

        profile = load_semantics_profile("wirelog.tools", 1)
        srep = validate_sem_document(m.sem, m.doc, catalogues=reg, mode="release", profile=profile)
        assert not srep.findings, (crit, sorted({f.code for f in srep.findings}))
        assert validate_prov(m.prov.prov_json, m.doc, sems=[m.sem]).failed() == [], crit
        assert support.map_run(crit).data == m.data, crit  # byte-identical re-map
        assert m.header["unit"] == "agent_execution"


def test_ext_matches_schema(mapped):
    schema = json.loads((support.REPO / "src/agentprov/adapters/wirelog/ext.schema.json").read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    for crit, m in mapped.items():
        for rec in m.records:
            ext = rec.get("ext", {}).get("wirelog")
            if ext is not None:
                assert list(validator.iter_errors(ext)) == [], (crit, rec["id"])


# ------------------------------------------------------------------------------------------------ identity and layout
def test_label_and_meta_fields_agree(mapped):
    for crit, m in mapped.items():
        assert "wirelog.label_field_mismatch" not in m.codes(), crit
        assert m.header["ext"]["wirelog"]["label_facets"]["run_dir"] == support.F[crit]
    changed = support.modified("param_description", meta=lambda v: v.update(model="amazon.nova-pro-v1:0"))
    assert {i["detail"] for i in changed.issues if i["code"] == "wirelog.label_field_mismatch"} == {"meta_model"}
    assert _issue(changed, "wirelog.label_field_mismatch")["rule"].startswith("wirelog.run_dir_layout@1")


def test_actors_and_identity(mapped):
    m = mapped["system_prompt_explicit"]
    kinds = {a["id"]: a["kind"] for a in m.of("actor")}
    assert kinds == {"bench": "benchmark", "harness": "harness", "user": "simulated_user", "agent": "llm_agent",
                     "env": "tool_runtime", "att": "attacker", "judge": "judge"}
    agent = m.get("agent")
    assert agent["model"]["requested"] == agent["name"] and agent["model"]["provider"] == "aws-bedrock"
    assert agent["evf"]["/model/provider"] == "I" and "wirelog.request_model_identity_unverified@1" in _rules(agent)
    assert agent["unk"]["/model/served"] == "not_recorded"
    env = m.get("env")
    assert env["ext"]["wirelog"]["synthetic"] is True and "wirelog.synthetic_tool_runtime_unverified@1" in _rules(env)
    assert "wirelog.deposit_harness_unverified@1" in _rules(m.get("bench"))
    system = m.get("m0")
    assert (system["role"], system["actor"]) == ("system", "harness")
    assert "wirelog.system_prompt_by_harness_unverified@1" in _rules(system)
    user = m.get("m1")
    assert (user["role"], user["actor"]) == ("user", "user") and "wirelog.user_is_harness_task_unverified@1" in _rules(user)
    assert "wirelog.arm_attacker_unverified@1" in _rules(m.get("att"))
    assert "env" not in {a["id"] for a in mapped["zero_calls"].of("actor")}


def test_clean_arm_has_no_attack(mapped):
    m = mapped["first_batch_clean"]
    assert m.header["task"]["attack_id"] is None and m.header["evf"]["/task/attack_id"] == "I"
    assert "att" not in {a["id"] for a in m.of("actor")}
    assert not [f for f in m.of("fixture") if f["kind"] == "injection_payload"]
    assert any(r.startswith("wirelog.clean_arm_unverified@1") for r in m.header["rule"])


def test_task_id_from_prompt_table(mapped):
    expected = {"param_description": "read_and_email_ticket", "user_prefix": "read_ticket_with_context_prefix",
                "tool_description_hijack": "read_ticket", "anthropic_messages": "read_ticket"}
    for crit, task_id in expected.items():
        assert mapped[crit].header["task"]["task_id"] == task_id, crit
        assert mapped[crit].header["evf"]["/task/task_id"] == "D"

    def rename(requests: list) -> None:
        for request in requests:
            request["messages"][0]["content"][0]["text"] += " now"

    changed = support.modified("zero_calls", requests=rename)
    assert changed.header["task"]["task_id"].startswith("sha256:") and "wirelog.task_prompt_unlisted" in changed.codes()


# ------------------------------------------------------------------------------------------------ context and calls
def test_request_items_resolve_to_earlier_records(mapped):
    m = mapped["four_requests"]
    calls = m.of("model_call")
    assert len(calls) == 4
    for earlier, later in zip(calls, calls[1:], strict=False):
        assert later["input"][: len(earlier["input"])] == earlier["input"]
        assert later["evf"]["/input"] == "D" and "wirelog.request_prefix@1" in _rules(later)
    assert "/input" not in calls[0].get("evf", {})
    assert "wirelog.context_diverges" not in m.codes()


def test_context_divergence_is_disclosed():
    def rewrite(requests: list) -> None:
        requests[1]["messages"][0]["content"][0]["text"] = "something else"

    m = support.modified("tool_description_hijack", requests=rewrite)
    details = {i["detail"] for i in m.issues if i["code"] == "wirelog.context_diverges"}
    assert "messages@1/0" in details
    assert "unattributed_additional_user_message" in m.codes()


def test_responses_link_by_echo(mapped):
    m = mapped["four_requests"]
    assistants = [r for r in m.of("message") if r["role"] == "assistant"]
    assert [a["generated_by"] for a in assistants] == [c["id"] for c in m.of("model_call")]
    assert [a["evf"]["/generated_by"] for a in assistants] == ["D", "D", "D", "I"]
    assert "wirelog.last_response_by_position_unverified@1" in _rules(assistants[-1])
    assert [c["evf"]["/status"] for c in m.of("model_call")] == ["D", "D", "D", "I"]
    assert all(c["status"] == "kept" for c in m.of("model_call"))


def test_calls_and_results_pair_by_id(mapped):
    m = mapped["three_result_message"]
    executions = {te["id"]: te for te in m.of("tool_execution")}
    results = [r for r in m.of("message") if r["parts"] and r["parts"][0]["t"] == "tool_result"]
    assert len(results) == len(executions) == 4
    for msg in results:
        te = executions[msg["generated_by"]]
        assert msg["parts"][0]["responds_to"] == te["call"]
        assert msg["evf"]["/generated_by"] == msg["evf"]["/parts/0/responds_to"] == te["evf"]["/call"] == "D"
        call_msg, k = te["call"].split("#")
        call_part = m.get(call_msg)["parts"][int(k)]
        assert call_part["t"] == "tool_call" and call_part["name"] == te["name"] and call_part["provider_call_id"]
    split = [r for r in results if r["ext"]["wirelog"]["wire_message"]["blocks"] == 3]
    assert [r["ext"]["wirelog"]["wire_message"]["block"] for r in split] == [0, 1, 2]
    assert all("wirelog.result_block_message@1" in _rules(r) for r in results)
    checks = m.checks()
    assert all(checks[c]["verdict"] == "consistent" for c in ("aer.acc.tool_calls_dispatched@1",
                                                                 "aer.acc.tool_results_linked@1",
                                                                 "aer.acc.executions_have_results@1"))


def test_unanswered_call_is_listed():
    def add_call(responses: list) -> None:
        responses[-1]["output"]["message"]["content"].append(
            {"toolUse": {"toolUseId": "tooluse_synthetic_unanswered", "name": "read_file", "input": {"path": "x"}}})

    m = support.modified("zero_calls", responses=add_call)
    issue = _issue(m, "unexecuted_tool_call")
    assert issue["rule"].startswith("wirelog.call_without_result@1") and len(issue["ids"]) == 1
    assert m.of("tool_execution") == []


def test_unknown_block_is_kept_verbatim():
    def add_block(responses: list) -> None:
        responses[0]["output"]["message"]["content"].insert(0, {"reasoningContent": {"reasoningText": {"text": "x"}}})

    m = support.modified("zero_calls", responses=add_block)
    assistant = next(r for r in m.of("message") if r["role"] == "assistant")
    assert assistant["parts"][0]["t"] == "other" and assistant["parts"][0]["type"] == "reasoningContent"
    assert "wirelog.unknown_block" in m.codes()


def test_executions_are_logged_dispatches(mapped):
    m = mapped["tool_description_hijack"]
    aids = {a["id"]: a["origin"]["label"].rsplit("/", 1)[-1] for a in m.header["artifacts"]}
    for te in m.of("tool_execution"):
        assert te["ev"] == "O" and "wirelog.dispatch_logged@1" in _rules(te)
        assert any(aids.get(s["a"]) == "tools_called.txt" for s in te["src"])
        assert te["unk"]["/status"] == "not_recorded" and te["unk"]["/t"] == "not_recorded"


def test_tool_config_is_one_fixture(mapped):
    m = mapped["four_requests"]
    (fx,) = [f for f in m.of("fixture") if f["kind"] == "tool_definitions"]
    assert {c["tools"] for c in m.of("model_call")} == {fx["id"]}
    assert all(c["evf"].get("/tools") == "D" for c in m.of("model_call")[1:])


def test_model_call_after_its_context(mapped):
    for crit, m in mapped.items():
        for call in m.of("model_call"):
            assert call["after"] == [{"b": "causal", "id": call["input"][-1]}], crit
            assert "wirelog.call_after_context@1" in _rules(call)


def test_latency_is_kept_without_clock(mapped):
    m = mapped["tool_description_hijack"]
    for call in m.of("model_call"):
        assert isinstance(call["ext"]["wirelog"]["latency_ms"], int)
        assert call["unk"]["/t/dur_s"] == "ambiguous" and "t" not in call
    anthropic = mapped["anthropic_messages"].of("model_call")[0]
    assert anthropic["unk"]["/t"] == "not_recorded" and anthropic["served_model"] and anthropic["response_id"]


def test_anthropic_messages_variant(mapped):
    m = mapped["anthropic_messages"]
    assert m.header["dialect"] == {"id": "wirelog.request_response", "variant": "anthropic-messages"}
    assert m.get("m0")["ext"]["wirelog"]["string_content"] is True
    assert len(m.of("tool_execution")) == 1 and m.checks()["wirelog.acc.dispatcher_log@1"]["verdict"] == "consistent"


# ------------------------------------------------------------------------------------------------ run, time, joins
def test_run_status_and_save_time(mapped):
    for crit, m in mapped.items():
        run = m.get("run")
        assert run["status"] == "ok" and run["evf"]["/status"] == "I", crit
        assert run["t"]["raw"]["end"] and run["unk"]["/t/end"] == "ambiguous" and "end" not in run["t"]
        assert "wirelog.save_timestamp_unverified@1" in _rules(run)


def test_results_row_join_and_judgements(mapped):
    m = mapped["first_batch_attacked_early"]
    by_name = {j["name"]: j for j in m.of("judgement")}
    assert set(by_name) == {"hijack", "exfiltration", "silent", "call_order", "outcome", "outcome_v2"}
    assert by_name["hijack"]["origin"] == "checker" and by_name["hijack"]["by"] == "benchmark"
    assert by_name["outcome"]["origin"] == "harness_rule"
    assert by_name["outcome_v2"]["origin"] == "recomputed" and by_name["outcome_v2"]["revises"] == by_name["outcome"]["id"]
    assert "wirelog.reclassified_unverified@1" in _rules(by_name["outcome_v2"])
    assert m.header["ext"]["wirelog"]["results_row"]["run_id"] == support.F["first_batch_attacked_early"]
    missing = support.modified("zero_calls", aux={"results": b"run_id,model,arm\n"})
    assert "wirelog.results_row_missing" in missing.codes()
    assert {j["name"] for j in missing.of("judgement")} == {"outcome"}


def test_payload_fixture_and_location(mapped):
    for crit, channel in (("tool_description_hijack", "tool_definitions"), ("param_description", "tool_definitions"),
                          ("tool_result_multi_result", "tool_result")):
        (fx,) = [f for f in mapped[crit].of("fixture") if f["kind"] == "injection_payload"]
        found = fx["ext"]["wirelog"]["found_in"]
        assert found["channel"] == channel and fx["evf"]["/ext/wirelog/found_in"] == "D", crit
        assert fx["actor"] == "att" and fx["evf"]["/content"] == "O:benchmark"
    m = mapped["payload_not_delivered"]
    (fx,) = [f for f in m.of("fixture") if f["kind"] == "injection_payload"]
    assert "found_in" not in fx.get("ext", {}).get("wirelog", {})
    assert _issue(m, "wirelog.payload_not_delivered")["ids"] == [fx["id"]]
    no_entry = support.modified("param_description", aux={"attacks": b"{}"})
    assert "wirelog.payload_entry_missing" in no_entry.codes()
    assert not [f for f in mapped["first_batch_attacked_early"].of("fixture") if f["kind"] == "injection_payload"]


def test_first_batch_disclosures(mapped):
    early, later = mapped["first_batch_attacked_early"], mapped["first_batch_clean"]
    assert {"wirelog.meta_rewritten", "wirelog.final_texts_not_logged"} <= set(early.codes())
    assert "wirelog.meta_rewritten" in later.codes() and "wirelog.final_texts_not_logged" not in later.codes()
    assert "wirelog.meta_rewritten" not in mapped["tool_description_hijack"].codes()


def test_unreadable_auxiliary_is_disclosed():
    m = support.modified("zero_calls", aux={"outcome": b"\xff\xfe"})
    assert {i["detail"] for i in m.issues if i["code"] == "wirelog.unreadable_auxiliary"} == {"outcome"}
    assert "outcome" not in {j["name"] for j in m.of("judgement")}


def test_accounting_checks(mapped):
    for crit, m in mapped.items():
        checks = m.checks()
        for cid in ("wirelog.acc.dispatcher_log@1", "wirelog.acc.recorded_hijack@1", "wirelog.acc.final_text@1"):
            assert checks[cid]["verdict"] == "consistent", (crit, cid)
        assert checks["aer.acc.agent_calls_vs_assistant@1"]["verdict"] == "consistent"
    assert mapped["first_batch_attacked_early"].checks()["wirelog.acc.usage_totals@1"]["verdict"] == "unverifiable"
    assert mapped["tool_description_hijack"].checks()["wirelog.acc.usage_totals@1"]["verdict"] == "consistent"
    wrong = support.modified("tool_description_hijack", meta=lambda v: v.update(fired_attacker=not v["fired_attacker"]))
    assert wrong.checks()["wirelog.acc.recorded_hijack@1"]["verdict"] == "inconsistent"


@pytest.mark.parametrize("crit", ["tool_result_multi_result", "system_prompt_explicit"])
def test_no_time_is_invented(mapped, crit):
    for rec in mapped[crit].records[1:]:
        t = rec.get("t", {})
        assert not ({"start", "end"} & set(t)), rec["id"]


def test_an_unreadable_response_log_is_one_degenerate_execution():
    label = "runs_named/nova-micro__operator_spoof__0004/response_raw.json"
    m = support.map_label(label, data=support.member_bytes(label)[:-2])  # truncated: not valid JSON
    assert m.outcome.degenerate
    assert m.doc.header["task"]["task_id"] == f"run:{label}"
    assert m.doc.header["dialect"]["variant"] == "bedrock-converse"
    issue = next(i for i in m.issues if i["code"] == "unparseable_artefact")
    assert issue["rule"].startswith("wirelog.unreadable_run@1")
