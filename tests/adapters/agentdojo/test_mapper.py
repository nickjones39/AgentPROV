"""``agentdojo.tracelogger`` mapping (docs/architecture D.6.5-D.6.7, D.6.10, D.6.11; C.16.1; K.6.2).

Golden-backed tests use the real C.16.1 artefact and the native logs N-C01…N-C09 (skipped when the fixtures are
absent); every other test builds a synthetic TraceLogger log in code. Nothing compares decoded documents with ``==``
where bytes are the contract: byte and JCS comparisons only (K.1(9)); failures print ids, pointers and digests, never
fixture content (R-42).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from agentdojo_support import (
    C161_PATH,
    REPO,
    base_log,
    c161_bytes,
    june_entry,
    map_bytes,
    map_log,
    map_native,
    native_entries,
    new_log,
    profile_with,
)

from agentprov.adapters.agentdojo.mapper import tool_status
from agentprov.adapters.profiles import load_profile
from agentprov.aer.ids import import_execution_id, mapping_id
from agentprov.aer.rules import load_catalogue
from agentprov.testing import golden

#: The C.16.1 vector as the writer seals it today: the ``aer/0.2`` reseal (C.21; the published 0.1 vector is unchanged).
VECTOR = REPO / "docs" / "architecture" / "examples" / "C" / "aer-0.2" / "agentdojo_2024_pi_detector.aer.jsonl"
KAT1 = "ex_7uz2oys57hugtsueixylme4fl5"


def _require_golden() -> None:
    if not golden.golden_available():
        pytest.skip(golden.golden_skip_reason() or "golden fixtures not found")


def _ok(m) -> None:
    report = m.validate()
    assert report.ok, sorted({f.code + " " + f.pointer for f in report.errors})
    assert report.passed and not report.skipped, report.skipped


# ------------------------------------------------------------------------------------------------ the worked example
def test_c16_1_vector_is_reproduced():
    """C.16.1 is normative: the shipped mapper and profile reproduce the vector byte for byte (E22 regenerated it)."""
    _require_golden()
    m = map_bytes(c161_bytes(), C161_PATH)
    golden.assert_bytes_equal(VECTOR.read_bytes(), m.data, what="C.16.1 vector")
    assert m.header["profile"] == load_profile("agentdojo-upstream").header()
    _ok(m)


def test_kat_execution_id():
    """D.6.10 item 2: the C.16.1 artefact maps to the KAT id of C.4.1 / K.5.2 (AD-04)."""
    _require_golden()
    raw = c161_bytes()
    m = map_bytes(raw, C161_PATH)
    assert m.info.ex == KAT1 == m.header["ex"]
    assert import_execution_id(mapping_id("agentdojo.tracelogger", "agentdojo-upstream"), m.header["source_key"]["sha256"],
                               {"p": ""}) == KAT1


# ------------------------------------------------------------------------------------------------ header and identity
def test_header_and_task():
    m = map_log(base_log())
    h = m.header
    assert h["dialect"] == {"id": "agentdojo.tracelogger", "variant": "v0.k11"}
    assert h["adapter"] == {"id": "agentdojo.tracelogger", "version": "0.1.0"}
    assert h["task"] == {"attack_id": "important_instructions", "attack_target_id": "injection_task_2", "benchmark": "agentdojo",
                         "defense_id": None, "suite": "banking", "task_id": "user_task_1"}
    assert h["evf"] == {"/task/benchmark": "D", "/task/defense_id": "I"}
    assert h["artifacts"][0]["prov_primary"] == "native"  # pinned publisher origin (D.6.5 Step 1)
    assert h["unk"] == {"/instrumentation": "not_recorded"} and h["unit"] == "agent_execution"
    assert h["ext"]["agentdojo"] == {"error": None, "pipeline_name": "gpt-4o-2024-05-13"}
    assert h["rules"] == {"aer": 1, "agentdojo": 2}
    run = m.get("run")
    assert run["t"] == {"dur_clock": "wall", "dur_s": 3} and run["ext"]["lex"] == {"flt": ["/t/dur_s"]}
    pre = map_log(base_log(user_task_id="injection_task_3", attack_type=None, injection_task_id=None, injections={}))
    assert pre.header["ext"]["agentdojo"]["task_kind"] == "injection_task_as_user_task"
    assert "agentdojo.injection_task_as_user_task@1#/ext/agentdojo/task_kind" in pre.header["rule"]
    dos = map_log(base_log(attack_type="captcha_dos"))
    assert dos.header["ext"]["agentdojo"]["task_kind"] == "dos"
    _ok(m), _ok(pre), _ok(dos)


def test_identity_from_the_directory_never_from_pipeline_name():
    doc = base_log(pipeline_name="gpt-4o-2024-05-13-tool_filter")
    m = map_log(doc, pipeline_dir="gpt-4o-2024-05-13-tool_filter")
    agent = m.get("agent")
    assert agent["model"] == {"requested": "gpt-4o-2024-05-13"} and agent["evf"] == {"/model": "I"}
    assert m.header["task"]["defense_id"] == "tool_filter" and m.get("def0")["name"] == "tool_filter"
    mismatch = map_log(base_log(pipeline_name="something-else"), pipeline_dir="gpt-4o-2024-05-13")
    assert mismatch.get("agent")["model"]["requested"] == "gpt-4o-2024-05-13"
    assert "agentdojo.pipeline_name_mismatch" in mismatch.codes
    unknown = map_bytes(map_log(base_log()).raw, "logs/elsewhere.json")
    assert "model" not in unknown.get("agent") and unknown.get("agent")["unk"]["/model"] == "not_recorded"
    assert "identity_unresolved" in unknown.codes and unknown.header["unk"]["/task/defense_id"] == "not_recorded"
    _ok(m), _ok(mismatch), _ok(unknown)


def test_path_fields_must_agree():
    doc = base_log()
    m = map_log(doc, path="runs/gpt-4o-2024-05-13/slack/user_task_1/important_instructions/injection_task_2.json")
    assert [i.get("detail") for i in m.issues("agentdojo.path_field_mismatch")] == ["suite_name"]
    assert m.header["task"]["suite"] == "banking"  # reported, never corrected
    _ok(m)


# ------------------------------------------------------------------------------------------------ actors, scopes, fixtures
def test_fixtures_are_attributed_to_the_attacker():
    m = map_log(base_log())
    fixtures = m.of_kind("fixture")
    assert [f["vector"] for f in fixtures] == ["vec_b", "vec_a"]  # source object order (D.6.5 Step 4)
    assert all(f["actor"] == "att" and f["evf"] == {"/actor": "I"} for f in fixtures)
    benign = map_log(base_log(attack_type=None, injection_task_id=None, injections={"v": "x"}))
    assert "actor" not in benign.of_kind("fixture")[0] and not [a for a in benign.of_kind("actor") if a["id"] == "att"]
    _ok(m), _ok(benign)


def test_attempt_scope_and_the_retry_rule():
    m = map_log(base_log())
    att = m.get("att0")
    assert att["unk"] == {"/index": "lost"} and att["rule"] == ["agentdojo.log_holds_last_pass@1"]
    assert m.issues("earlier_attempts_unobservable")[0]["rule"] == "agentdojo.log_holds_last_pass@1"
    doc = base_log()
    doc["messages"][-1]["content"] = None
    retry = map_log(doc)
    att = retry.get("att0")
    assert att["index"] == 2 and "unk" not in att and att["ext"]["agentdojo"] == {"pre_state_not_initial": True}
    assert "agentdojo.null_final_implies_three_passes@1#/index" in att["rule"]
    assert {"retry_passes_inferred", "earlier_attempts_unobservable"} <= set(retry.codes)
    errored = map_log(dict(doc, error="context_length_exceeded"))
    assert "index" not in errored.get("att0")  # a run error is not a re-run trigger
    _ok(retry), _ok(errored)


def test_c07_rerun_is_inferred_structurally():
    """J.2.4 C07 (phase-6 resolution): the native log's final assistant content is null and there is no run error, so
    the retry rule fires on the log's own structure; no replay evidence is used. The provider ids are all ``""``."""
    _require_golden()
    entry = next(e for e in native_entries() if e.id == "N-C07")
    m = map_native(entry)
    att = m.get("att0")
    assert att["index"] == 2 and "agentdojo.null_final_implies_three_passes@1#/index" in att["rule"]
    assert att["ext"]["agentdojo"] == {"pre_state_not_initial": True}
    assert {"retry_passes_inferred", "earlier_attempts_unobservable"} <= set(m.codes)
    calls = [p for r in m.records if r.get("k") == "message" for p in r.get("parts", []) if p.get("t") == "tool_call"]
    assert calls and all(p.get("provider_call_id") == "" for p in calls)
    _ok(m)


def test_engine_assumptions_are_cited():
    """EF E.10 item 21: env cites the auto-execution I twin; every checker judgement the checker-input I twin."""
    m = map_log(base_log())
    env = m.get("env")
    assert env["evf"] == {"/on_behalf_of": "I"} and "agentdojo.auto_execution_unverified@1#/on_behalf_of" in env["rule"]
    for j in m.of_kind("judgement"):
        cites = "agentdojo.checker_inputs_unverified@1#/inputs" in j["rule"]
        assert cites == (j["origin"] == "checker") and (j.get("unk") == {"/inputs": "not_recorded"}) == cites


# ------------------------------------------------------------------------------------------------ messages and calls
def test_message_order_and_context():
    m = map_log(base_log())
    mc0, mc1 = m.get("mc0"), m.get("mc1")
    assert mc0["input"] == ["m0", "m1"] and mc1["input"] == ["m0", "m1", "m2", "m3"]
    assert mc0["evf"] == {"/input": "I"} and "agentdojo.context_is_prefix@1#/input" in mc0["rule"]
    assert m.get("m1")["after"] == [{"b": "pos", "id": "m0"}] and m.get("m2")["after"] == [{"b": "causal", "id": "mc0"}]
    assert [r["k"] for r in m.records].index("model_call") < [r.get("id") for r in m.records].index("m2")
    assert m.get("m2")["parts"][0] == {"t": "text", "text": None}


def test_tool_linking_by_id():
    doc = base_log()
    msgs = doc["messages"]
    msgs[2]["tool_calls"].append({"function": "get_balance", "args": {}, "id": "call_2"})
    msgs.insert(4, {"role": "tool", "content": "1", "tool_call_id": "call_2",
                    "tool_call": {"function": "get_balance", "args": {}, "id": "call_2"}, "error": None})
    m = map_log(doc)
    te0, te1 = m.get("te0"), m.get("te1")
    assert te0["call"] == "m2#1" and te1["call"] == "m2#2" and "/call" not in te1["evf"]
    assert te1["after"] == [{"b": "causal", "id": "m2"}, {"b": "pos", "id": "m3"}]
    assert "agentdojo.tools_executed_sequentially@1#/after" in te1["rule"]
    assert m.get("m4")["parts"][0]["responds_to"] == "m2#2" and m.get("m4")["evf"]["/parts/0/responds_to"] == "D"
    assert te0["args"] == {"amount": 10, "recipient": "X"} and te0["ext"]["lex"] == {
        "flt": ["/args/amount"], "ord": {"/args": ["recipient", "amount"]}}
    _ok(m)


def test_tool_linking_by_position():
    doc = base_log()
    for message in doc["messages"]:
        for call in message.get("tool_calls") or ():
            call["id"] = ""
        if message["role"] == "tool":
            message["tool_call_id"] = ""
            message["tool_call"]["id"] = ""
    m = map_log(doc)
    te0, tool = m.get("te0"), m.get("m3")
    assert te0["call"] == "m2#1" and te0["evf"]["/call"] == "I" and "agentdojo.positional_match@1#/call" in te0["rule"]
    assert tool["evf"]["/parts/0/responds_to"] == "I" and "ext" not in tool  # the logged id is the linked call's id
    assert m.get("m2")["unk"]["/parts/1/provider_call_id"] == "ambiguous"
    _ok(m)
    cohere = base_log()
    del cohere["messages"][2]["tool_calls"][0]["id"]
    del cohere["messages"][3]["tool_call"]["id"]
    cohere["messages"][3]["tool_call_id"] = None
    c = map_log(cohere)
    assert "provider_call_id" not in c.get("m2")["parts"][1] and c.get("m2")["unk"]["/parts/1/provider_call_id"] == "not_recorded"
    assert c.get("m3")["ext"]["agentdojo"]["tool_call_id"] is None
    _ok(c)


def test_link_conflict_is_ambiguous():
    doc = base_log()
    doc["messages"][2]["tool_calls"][0]["id"] = ""
    doc["messages"][3]["tool_call"] = {"function": "other_tool", "args": {}}
    m = map_log(doc)
    assert m.get("te0")["unk"]["/call"] == "ambiguous" and "call" not in m.get("te0")
    assert m.get("m3")["unk"]["/parts/0/responds_to"] == "ambiguous"
    assert m.issues("call_result_link_conflict")[0]["ids"] == ["te0", "m3"]
    _ok(m)


def test_tool_status_from_error():
    assert tool_status(None) == "ok"
    assert tool_status("Invalid tool x provided.") == tool_status("ValidationError: bad") == "invalid"
    assert tool_status("Empty function name provided. Provide a valid function name.") == "invalid"
    assert tool_status("ValueError: no such file") == "error"
    doc = base_log()
    doc["messages"][3]["error"] = "ValueError: boom"
    m = map_log(doc)
    assert m.get("te0")["status"] == "error" and m.get("m3")["parts"][0]["error"] == "ValueError: boom"
    _ok(m)


def test_unexecuted_trailing_calls():
    doc = base_log()
    doc["messages"][-1]["tool_calls"] = [{"function": "f", "args": {}, "id": "call_9"}]
    m = map_log(doc)
    assert m.issues("unexecuted_tool_call")[0]["ids"] == ["m4#1"]
    assert m.get("m4")["parts"][1]["name"] == "f"
    middle = base_log()
    middle["messages"][2]["tool_calls"].append({"function": "g", "args": {}, "id": "call_2"})
    mm = map_log(middle)
    assert mm.issues("missing_tool_result")[0]["ids"] == ["m2#2"]
    _ok(m)


def test_empty_assistant_text_is_ambiguous():
    doc = base_log()
    doc["messages"][-1]["content"] = ""
    doc["messages"][-1]["tool_calls"] = []
    m = map_log(doc)
    m4 = m.get("m4")
    assert m4["parts"] == [{"t": "text", "text": ""}] and m4["unk"] == {"/parts/0/text": "ambiguous"}
    # D-27 c6: the rule cites no code (documentary evidence only), so its I twin is cited for every profile
    assert "agentdojo.empty_assistant_text_ambiguous_unverified@1#/parts/0/text" in m4["rule"]
    assert m4["ext"]["agentdojo"] == {"calls_form": "empty_list"}
    _ok(m)


def test_additional_user_messages_are_unattributed():
    doc = base_log()
    doc["messages"].append({"role": "user", "content": "And now?"})
    m = map_log(doc)
    assert m.get("m5")["evf"]["/actor"] == "I" and m.issues("unattributed_additional_user_message")[0]["ids"] == ["m5"]
    _ok(m)


def test_unknown_shapes_are_kept_verbatim():
    doc = base_log(extra_key=[1, 2.0])
    doc["messages"].append({"role": "critic", "content": "?", "score": 1})
    m = map_log(doc)
    assert m.header["ext"]["agentdojo"]["extra"] == {"extra_key": [1, 2]}
    assert "agentdojo.unknown_top_level_key" in m.codes
    m5 = m.get("m5")
    assert m5["role"] == "critic" and m5["parts"][0]["type"] == "agentdojo.unknown_message"
    assert "agentdojo.unknown_message_shape" in m.codes
    _ok(m)


# ------------------------------------------------------------------------------------------------ defences
def test_tool_filter_messages_belong_to_the_defence():
    doc = base_log(pipeline_name="gpt-4o-2024-05-13-tool_filter")
    msgs = doc["messages"]
    msgs[2:2] = [{"role": "user", "content": "Filter the tools."},
                 {"role": "assistant", "content": "send_money", "tool_calls": None}]
    m = map_log(doc)
    prompt, output, aux = m.get("m2"), m.get("m3"), m.get("mc0")
    assert prompt["actor"] == "def0" and prompt["evf"]["/actor"] == "I"
    assert aux["role"] == "auxiliary" and aux["actor"] == "def0" and aux["ev"] == "I"
    assert output["actor"] == "def0" and output["generated_by"] == "mc0"
    assert m.get("mc1")["role"] == "agent" and m.get("mc1")["input"] == ["m0", "m1", "m2", "m3"]
    _ok(m)


def test_repeat_user_prompt_copies():
    doc = base_log(pipeline_name="gpt-4o-2024-05-13-repeat_user_prompt")
    doc["messages"].insert(4, {"role": "user", "content": "Pay the bill."})
    m = map_log(doc)
    copy = m.get("m4")
    assert copy["actor"] == "def0" and copy["ext"]["agentdojo"] == {"copy_of": "m1"} and copy["evf"]["/actor"] == "I"
    assert not m.issues("unattributed_additional_user_message")
    _ok(m)


def test_spotlighting_content_state():
    m = map_log(base_log(pipeline_name="gpt-4o-2024-05-13-spotlighting_with_delimiting"))
    tool = m.get("m3")
    assert tool["ext"]["agentdojo"] == {"content_state": "post_defence"}
    assert tool["evf"]["/ext/agentdojo/content_state"] == "I"
    _ok(m)


def test_pi_detector_redaction_only_where_declared():
    sentinel = "<Data omitted because a prompt injection was detected>"
    doc = base_log(pipeline_name="gpt-4o-2024-05-13-transformers_pi_detector")
    doc["messages"][3]["content"] = sentinel
    m = map_log(doc)
    assert m.get("dc0")["verdict"] == "redact" and m.get("m3")["generated_by"] == "dc0" and m.get("m3")["actor"] == "def0"
    plain = base_log()
    plain["messages"][3]["content"] = sentinel
    p = map_log(plain)  # no detector in this pipeline: the pattern is not applied, the quirk is reported
    assert not p.of_kind("decision") and p.get("m3")["generated_by"] == "te0"
    assert [i["detail"] for i in p.issues("agentdojo.undeclared_quirk")] == ["agentdojo.pi_detector_redaction"]
    _ok(m), _ok(p)


def test_undeclared_quirks_are_reported_not_applied():
    profile = profile_with({'[[family.agentdojo.quirk]]\nid = "agentdojo.silent_rerun_last_pass_only"\napplies = {}':
                            '[[family.agentdojo.quirk]]\nid = "agentdojo.silent_rerun_last_pass_only"\napplies = { pipeline_dir = ["nothing"] }'})
    doc = base_log()
    doc["messages"][-1]["content"] = None
    m = map_log(doc, profile=profile)
    assert "index" not in m.get("att0")
    assert [i["detail"] for i in m.issues("agentdojo.undeclared_quirk")] == ["agentdojo.silent_rerun_last_pass_only"]


def test_rule_twins_follow_the_profile():
    """D.5.4, D-24: without the June-2024 code among the profile's verified_code, every D rule cited at c274885 only is
    cited through its twin and the statements it justifies are I (C.6.5 rule 1)."""
    profile = profile_with({june_entry(): ""})
    m = map_log(base_log(), profile=profile)
    _ok(m)
    assert m.get("mc0")["ev"] == "I" and "agentdojo.assistant_msg_has_one_call_unverified@1" in m.get("mc0")["rule"]
    assert m.get("te0")["ev"] == "I" and "agentdojo.tool_msg_is_one_execution_unverified@1" in m.get("te0")["rule"]
    assert "agentdojo.messages_append_ordered_unverified@1#/after" in m.get("m1")["rule"]
    assert m.get("m1")["evf"] == {"/actor": "I", "/after": "I"}  # user_is_simulated and the order, both twins
    assert m.get("user")["ev"] == m.get("agent")["ev"] == m.get("bench")["ev"] == "I"
    assert m.get("att0")["ev"] == "I" and m.get("att0")["rule"] == ["agentdojo.log_holds_last_pass_unverified@1"]
    assert [j["evf"]["/origin"] for j in m.of_kind("judgement")] == ["I", "I"]
    assert m.header["evf"]["/task/benchmark"] == "I"
    assert m.get("te0")["rule"][1:3] == ["agentdojo.call_id_unique_match_unverified@1#/call",
                                         "agentdojo.tool_status_from_error_unverified@1#/status"]
    shipped = map_log(base_log())  # v0.k11 under the shipped profile: the June-2024 code is verified
    assert shipped.get("mc0")["ev"] == shipped.get("te0")["ev"] == shipped.get("user")["ev"] == "D"
    assert shipped.get("env")["ev"] == "I"  # agentdojo.functions_runtime cites no code (D-27 c6)


# ------------------------------------------------------------------------------------------------ outcomes
def test_judgement_origins():
    def origins(**kw: Any) -> list[tuple[str, str, str]]:
        m = map_log(base_log(**kw))
        _ok(m)
        return [(j["name"], j["origin"], j["rule"][0]) for j in m.of_kind("judgement")]

    assert origins() == [("utility", "checker", "agentdojo.checker_outcome@1#/origin"),
                         ("security", "checker", "agentdojo.checker_outcome@1#/origin")]
    assert origins(attack_type=None, injection_task_id=None, injections={})[1] == (
        "security", "harness_default", "agentdojo.benign_security_constant@1#/origin")
    assert origins(attack_type="dos")[1] == ("security", "harness_rule", "agentdojo.dos_security_rule@1#/origin")
    errored = map_log(base_log(error="context_length_exceeded", utility=False, security=True))
    assert {j["origin"] for j in errored.of_kind("judgement")} == {"harness_default"}
    assert errored.issues("outcome_imposed_by_runner")[0]["ids"] == ["j0", "j1"]


def test_incomplete_run():
    doc = base_log()
    for key in ("utility", "security", "duration"):
        del doc[key]
    m = map_log(doc)
    assert not m.of_kind("judgement") and m.issues("incomplete_run")[0]["ids"] == ["run"]
    assert "t" not in m.get("run") and m.get("run")["unk"]["/t"] == "not_recorded"
    _ok(m)


def test_empty_messages_are_outcome_only():
    doc = base_log(messages=[], pipeline_name="claude-3-opus-20240229")
    m = map_log(doc)
    assert m.header["unit"] == "outcome_only" and not m.of_kind("message") and "att0" not in [r.get("id") for r in m.records]
    assert len(m.of_kind("judgement")) == 2 and "no_execution_observed" in m.codes
    assert "agentdojo.undeclared_quirk" not in m.codes
    _ok(m)


# ------------------------------------------------------------------------------------------------ unsupported and malformed
@pytest.mark.parametrize("extra", [
    {"benchmark_version": "v1.2", "evaluation_timestamp": "2025-07-01 10:00:00", "agentdojo_package_version": "0.1.35"},
])
def test_unsupported_variants_seal_degenerate(extra):
    """A recognised variant the profile does not declare seals degenerate (D.2.8 case 3; D.6.12 item 1)."""
    undeclared = profile_with({'variants = ["v0.k11", "v1.k14", "v1.k14.incomplete"]': 'variants = ["v0.k11"]'})
    m = map_log(base_log(**extra), profile=undeclared)
    assert m.outcome.degenerate and m.header["dialect"]["variant"] == "v1.k14"
    assert m.codes[0] == "unsupported_variant" and m.info.issues[0]["rule"] == "agentdojo.tracelogger_record_shape@1"
    assert m.header["task"]["suite"] == "banking"
    _ok(m)
    malformed = map_log(base_log(injections=[1]))
    assert malformed.outcome.degenerate and malformed.codes[0] == "unparseable_artefact"
    missing = dict(base_log())
    del missing["error"]
    gone = map_log(missing)
    assert gone.outcome.degenerate and gone.codes[0] == "unparseable_artefact"


# ------------------------------------------------------------------------------------------------ cross-cutting
def _all_mapped() -> list[Any]:
    out = [map_log(base_log())]
    if golden.golden_available():
        out.append(map_bytes(c161_bytes(), C161_PATH))
        out.extend(map_native(e) for e in native_entries())
    return out


def test_golden_native_logs_map_and_validate():
    _require_golden()
    for entry in native_entries():
        m = map_native(entry)
        assert not m.outcome.degenerate, entry.id
        _ok(m)


def test_mapping_is_deterministic():
    """D.6.10 item 5: map twice, the AER bytes are equal."""
    for m in _all_mapped():
        again = map_bytes(m.raw, m.header["artifacts"][0]["origin"]["path"])
        assert again.data == m.data


def test_emitted_rules_and_issue_codes_are_declared():
    catalogues = {"agentdojo": load_catalogue("agentdojo"), "aer": load_catalogue("aer")}
    for m in _all_mapped():
        refs = [r for rec in m.records for r in rec.get("rule", [])] + [i["rule"] for i in m.info.issues]
        for ref in refs:
            rule_id = ref.split("#", 1)[0]
            entry = catalogues[rule_id.split(".", 1)[0]].get(rule_id)
            assert entry is not None and entry.citable, rule_id
        for issue in m.info.issues:
            if "." in issue["code"]:
                assert catalogues[issue["code"].split(".", 1)[0]].declares_issue_code(issue["code"]), issue["code"]


def test_ext_agentdojo_follows_the_closed_schema():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((REPO / "src" / "agentprov" / "adapters" / "agentdojo" / "ext.schema.json").read_bytes())
    docs = [base_log(pipeline_name="gpt-4o-2024-05-13-repeat_user_prompt", extra_key=1),
            base_log(attack_type=None, injection_task_id=None, injections={}, user_task_id="injection_task_1")]
    docs[0]["messages"].insert(4, {"role": "user", "content": "Pay the bill."})
    cls = jsonschema.validators.validator_for(schema)
    cls.check_schema(schema)  # once, not per record (what jsonschema.validate repeats on every call)
    validator = cls(schema)
    for m in [*_all_mapped(), *(map_log(d) for d in docs)]:
        for record in m.records:
            ext = (record.get("ext") or {}).get("agentdojo")
            if ext is not None:
                kind = "execution" if record["k"] == "execution" else record["k"]
                error = jsonschema.exceptions.best_match(validator.iter_errors({kind: ext}))
                if error is not None:
                    raise error


def test_lexical_hints_carry_order_and_integral_floats():
    """D.6.10 item 7: non-sorted argument members and integral floats survive through ``ext.lex``."""
    doc = base_log()
    args = {"z": {"b": 1.0, "a": [2.0, {"y": 0, "x": 1}]}, "a": 3}
    doc["messages"][2]["tool_calls"][0]["args"] = args
    doc["messages"][3]["tool_call"]["args"] = args
    m = map_log(doc)
    lex = m.get("m2")["ext"]["lex"]
    assert lex["ord"] == {"/parts/1/args": ["z", "a"], "/parts/1/args/z": ["b", "a"], "/parts/1/args/z/a/1": ["y", "x"]}
    assert lex["flt"] == ["/parts/1/args/z/a/0", "/parts/1/args/z/b"]
    from agentprov.views.transcript_v1 import render_converted, serialise

    turn = render_converted(m.records)["turns"][2]
    assert json.dumps(turn["tool_calls"][0]["args"]) == json.dumps(args)
    assert serialise({"x": turn["tool_calls"][0]["args"]}) == serialise({"x": args})


def test_reader_writes_no_file(tmp_path: Path):
    """The mapper is pure (A-2): mapping in a read-only working directory leaves it untouched."""
    before = sorted(tmp_path.iterdir())
    map_log(new_log())
    assert sorted(tmp_path.iterdir()) == before


# ------------------------------------------------------------------------------------------------ golden AER bytes
AER_DIGESTS = Path(__file__).resolve().parent / "aer_digests.json"
REGEN_AER = "AGENTPROV_REGEN_AGENTDOJO_AER"


def test_golden_aer_bytes():
    """D.6.10 item 1: the AER of every real v0.k11 sample is pinned byte for byte, by the SHA-256 of the file (the AER
    holds third-party text, so the bytes themselves stay with the fixtures). Regenerate deliberately with
    ``AGENTPROV_REGEN_AGENTDOJO_AER=1`` after a profile, catalogue or mapper change, and say why in the commit."""
    _require_golden()
    import os

    produced = {e.id: golden.sha256_hex(map_native(e).data) for e in native_entries()}
    produced["C.16.1"] = golden.sha256_hex(map_bytes(c161_bytes(), C161_PATH).data)
    if os.environ.get(REGEN_AER):
        AER_DIGESTS.write_text(json.dumps(dict(sorted(produced.items())), indent=2) + "\n", encoding="utf-8")
    expected = json.loads(AER_DIGESTS.read_text(encoding="utf-8"))
    changed = sorted(k for k, v in produced.items() if expected.get(k) != v)
    assert changed == [], f"AER bytes changed: {changed}"
    assert expected["C.16.1"] == golden.sha256_hex(VECTOR.read_bytes())
