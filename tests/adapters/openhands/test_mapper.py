"""The ``openhands.events`` mapper on the committed fixtures (docs/architecture D.17.3-D.17.8; D-171-D-179).

Asserts structure, links, evidence classes and issues only; no fixture text is printed or compared verbatim.
"""

from __future__ import annotations

import json

import openhands_support as support
import pytest

from agentprov.adapters.openhands.citation import citations
from agentprov.errors import MalformedArtefact


def _rules(rec):
    return [r.split("#", 1)[0] for r in rec.get("rule", [])]


def test_every_fixture_seals_with_consistent_accounting(mapped):
    for fid, m in mapped.items():
        assert m.header["unit"] == "agent_execution" and not m.outcome.degenerate, fid
        assert m.doc.seal["accounting"]["status"] == "consistent", fid
        assert "openhands.filtered_events" in m.codes(), fid  # every saved trajectory has id gaps


def test_variants_and_headers(mapped):
    for fid, m in mapped.items():
        variant = m.header["dialect"]["variant"]
        assert variant == ("oas-0.28" if fid.startswith("O") else "oh-1.5"), fid
    r1 = mapped["R1"].header
    assert r1["task"]["benchmark"] == "redcode-exec" and r1["task"]["attack_id"] == "C1" and r1["task"]["suite"] == "python"
    assert r1["evf"]["/task/attack_id"] == "D"
    o1 = mapped["O1"].header
    assert o1["task"]["benchmark"] == "openagentsafety" and "attack_id" not in o1["task"]
    assert o1["unk"]["/task/attack_id"] == "not_recorded"
    assert mapped["O8"].header["task"]["task_id"] == "safety-memo_draft"


def test_cause_links_are_derived_under_the_verified_code(mapped):
    """D-172: both profiles name a verified commit, so the cause link and the execution are class D."""
    for fid, m in mapped.items():
        for te in m.of("tool_execution"):
            assert te["ev"] == "D" and "openhands.observation_is_execution@1" in _rules(te), fid
            assert te["evf"]["/call"] == "D"
        for msg in m.of("message"):
            if msg["role"] == "tool":
                assert msg["evf"]["/parts/0/responds_to"] == "D" and "openhands.cause_link@1" in _rules(msg)
                call = msg["parts"][0]["responds_to"]
                te = m.get(msg["generated_by"])
                assert te["call"] == call and m.get(call.split("#")[0])["role"] == "assistant"


def test_without_verified_code_the_twins_are_cited():
    cite = citations({}, {"variant": "oas-0.28"}, "test")
    assert cite.cite("openhands.cause_link@1") == "openhands.cause_link_unverified@1"
    assert cite.cls("openhands.cause_link@1") == "I"
    assert cite.cite("openhands.redcode_prompt_join@1") == "openhands.redcode_prompt_join@1"  # independent
    verified = citations({"verified_code": [{"commit": "a77b05509ec010d44d1e274b0f8daace0f89ea8f"}]}, {}, "test")
    assert verified.cite("openhands.cause_link@1") == "openhands.cause_link@1"


def test_model_calls_come_from_the_recorded_responses(mapped):
    for fid, m in mapped.items():
        for mc in m.of("model_call"):
            assert mc["role"] == "agent" and mc["status"] == "kept" and mc["evf"]["/input"] == "I", fid
            if mc["ev"] == "O":
                assert "served_model" in mc and "response_id" in mc and "finish_reason" in mc
            else:
                assert "openhands.text_message_is_model_output_unverified@1" in _rules(mc)
        served = {mc["served_model"] for mc in m.of("model_call") if "served_model" in mc}
        agent = m.get("agent")
        assert agent["kind"] == "llm_agent" and agent["model"]["served"] in served
    o1 = mapped["O1"].get("agent")
    assert o1["model"]["requested"].startswith("openai/neulab/")  # the LiteLLM route string, observed
    assert "/model/requested" in mapped["R1"].get("agent")["unk"]


def test_parallel_calls_of_one_response_share_one_assistant_message(mapped):
    m = mapped["O2"]
    def calls(msg):
        return sum(p["t"] == "tool_call" or (p["t"] == "other" and p["type"] == "openhands.finish_call") for p in msg["parts"])

    multi = [msg for msg in m.of("message") if msg["role"] == "assistant" and calls(msg) > 1]
    assert multi
    msg = multi[0]
    calls = {f"{msg['id']}#{k}" for k, p in enumerate(msg["parts"]) if p["t"] == "tool_call"}
    executed = {te["call"] for te in m.of("tool_execution")}
    assert calls <= executed


def test_finish_is_a_control_call_without_execution_or_issue(mapped):
    m = mapped["R1"]
    finish = [(msg, k) for msg in m.of("message") for k, p in enumerate(msg.get("parts", []))
              if p["t"] == "other" and p["type"] == "openhands.finish_call"]
    assert finish and "unexecuted_tool_call" not in m.codes()
    msg, k = finish[0]
    assert msg["evf"][f"/parts/{k}/type"] == "D" and "openhands.finish_control_call@1" in _rules(msg)


def test_the_not_executed_notice_is_a_harness_artefact_and_the_call_is_unexecuted(mapped):
    m = mapped["O3"]
    notices = [a for a in m.of("activity") if a["type"] == "openhands:controller_notice"]
    assert len(notices) == 1 and notices[0]["ev"] == "D"
    (text,) = [af for af in m.of("artefact") if af["type"] == "openhands:notice_text"]
    assert text["generated_by"] == notices[0]["id"]
    (issue,) = [i for i in m.issues if i["code"] == "unexecuted_tool_call"]
    call = issue["ids"][0]
    assert call not in {te["call"] for te in m.of("tool_execution")}


def test_uncaused_errors_are_harness_activities(mapped):
    for fid in ("O4", "R3"):
        m = mapped[fid]
        acts = [a for a in m.of("activity") if a["type"] == "openhands:harness_error"]
        assert acts and all(a["status"] == "error" and a["evf"]["/actor"] == "I" for a in acts), fid
        assert "openhands.harness_error" in m.codes()


def test_error_observations_leave_the_execution_status_ambiguous(mapped):
    m = mapped["R2"]
    tes = m.of("tool_execution")
    errors = [te for te in tes if te.get("unk", {}).get("/status") == "ambiguous"]
    assert errors and all("status" not in te for te in errors)
    assert any(te.get("status") == "ok" for te in tes)


def test_simulated_users(mapped):
    m = mapped["O5"]
    fake = m.get("fake_user")
    assert fake["kind"] == "simulated_user" and fake["model"]["requested"] == "gpt-4o-2024-05-13" and fake["ev"] == "I"
    users = [msg for msg in m.of("message") if msg["role"] == "user"]
    assert users[0]["actor"] == "user" and all(msg["actor"] == "fake_user" for msg in users[1:])
    forms = {msg["ext"]["openhands"]["reply_form"] for msg in users[1:]}
    assert forms <= {"fixed_text", "generated"} and forms
    rc_users = [msg for msg in mapped["R1"].of("message") if msg["role"] == "user"]
    assert all(msg["actor"] == "user" for msg in rc_users)
    assert {msg["ext"]["openhands"]["reply_form"] for msg in rc_users[1:]} <= {"fixed_text"}


def test_npc_chat(mapped):
    m = mapped["O1"]
    npcs = [a for a in m.of("actor") if a.get("role") == "npc"]
    assert npcs and all(a["kind"] == "simulated_user" and a["ev"] == "I" for a in npcs)
    chats = [te for te in m.of("tool_execution") if te["name"] == "chat"]
    assert chats and all(te["ext"]["openhands"]["npc"] in {a["id"] for a in npcs} for te in chats if "npc" in te["ext"]["openhands"])
    authors = m.annotations("author")
    assert authors and all(a["ev"] == "I" for a in authors)


def test_recall_steps_are_harness_activities(mapped):
    m = mapped["R1"]
    recalls = [a for a in m.of("activity") if a["type"] == "openhands:recall"]
    contexts = [af for af in m.of("artefact") if af["type"] == "openhands:workspace_context"]
    assert recalls and contexts and contexts[0]["generated_by"] == recalls[0]["id"]
    assert contexts[0]["evf"]["/generated_by"] == "D"


def test_fixtures_and_joins(mapped):
    r1 = mapped["R1"]
    kinds = {fx["kind"]: fx for fx in r1.of("fixture")}
    assert {"system_prompt", "tool_definitions", "task_prompt"} <= set(kinds)
    assert kinds["task_prompt"]["ev"] == "D" and r1.header["ext"]["openhands"]["request_join"]["tier"] in ("exact", "contained")
    assert all(mc.get("tools") == kinds["tool_definitions"]["id"] for mc in r1.of("model_call"))
    r4 = mapped["R4"]
    assert r4.header["ext"]["openhands"]["request_join"]["tier"] == "contained_after_declared_rewrite"
    assert "openhands.join_after_rewrite" in r4.codes()
    o1 = mapped["O1"]
    (task,) = o1.of("fixture")
    assert task["kind"] == "task_prompt" and task["ev"] == "I" and task["evf"]["/content"] == "O"
    assert set(o1.header["ext"]["openhands"]["task_join"]["files"]) == {"task_md", "checkpoints", "scenarios", "evaluator"}


def test_judgements(mapped):
    o1 = mapped["O1"]
    names = [j["name"] for j in o1.of("judgement")]
    assert "final_score" in names and "llm_label" in names and "rule_based_score" in names
    assert all(j["origin"] == "checker" and j["evf"]["/origin"] == "I" for j in o1.of("judgement"))
    o4 = mapped["O4"]
    assert "openhands.eval_missing" in o4.codes() and "final_score" not in [j["name"] for j in o4.of("judgement")]
    (r1,) = mapped["R1"].of("judgement")
    assert (r1["name"], r1["value"], r1["origin"]) == ("score", 3, "checker")
    (r2,) = mapped["R2"].of("judgement")
    assert r2["value"] == 1 and "origin" not in r2 and r2["unk"]["/origin"] == "ambiguous"


def test_semantic_outcomes(mapped):
    assert [a["value"] for a in mapped["R1"].annotations("outcome")] == [{"claim": "attack_succeeded", "holds": True}]
    assert [a["value"] for a in mapped["R4"].annotations("outcome")] == [{"claim": "attack_succeeded", "holds": False}]
    assert [a["value"] for a in mapped["R2"].annotations("openhands.non_informative")] == [{"reason": "score_one_ambiguous"}]
    for fid in ("O2", "O5", "O8"):
        (outcome,) = mapped[fid].annotations("outcome")
        assert outcome["value"]["claim"] == "openhands.unsafe_behaviour_detected"


def test_set_of_marks_screenshots_are_not_inlined(mapped):
    m = mapped["O7"]
    assert "data:image/" not in m.data.decode("utf-8")
    marked = [msg for msg in m.of("message") if "set_of_marks" in msg.get("ext", {}).get("openhands", {}).get("extras", {})]
    assert marked and "openhands.content_not_inlined" in m.codes()
    (issue,) = [i for i in m.issues if i["code"] == "openhands.content_not_inlined"]
    assert {msg["id"] for msg in marked if isinstance(msg["ext"]["openhands"]["extras"]["set_of_marks"], dict)} <= set(issue["ids"])
    for msg in marked:
        value = msg["ext"]["openhands"]["extras"]["set_of_marks"]
        if isinstance(value, dict):
            assert set(value["not_inlined"]) >= {"sha256", "bytes"}
            assert msg["evf"]["/ext/openhands/extras/set_of_marks"] == "D"


def test_a_string_over_1_mib_is_not_inlined():
    source, label = support.F["R1"]
    files = support.tree(source)
    events = json.loads(files[label])
    target = next(i for i, e in enumerate(events) if e.get("observation") == "run")
    events[target]["content"] = "x" * (1 << 20 | 1)
    data = json.dumps(events).encode()
    m = support.map_label(label, files, source=source, data=data)
    (msg,) = [msg for msg in m.of("message") if msg["id"] == f"m{target}"]
    assert msg["parts"][0]["text"] is None and msg["unk"]["/parts/0/text"] == "ambiguous"
    assert msg["ext"]["openhands"]["text_not_inlined"]["not_inlined"]["bytes"] == (1 << 20 | 1)
    assert "openhands.content_not_inlined" in m.codes() and len(m.data) < (1 << 20)


def test_mapping_is_deterministic():
    a, b = support.map_fixture("O2", sem=True), support.map_fixture("O2", sem=True)
    assert a.data == b.data
    from agentprov.sem.engine import dumps_sem

    assert dumps_sem(a.sem) == dumps_sem(b.sem)


def test_an_empty_or_malformed_list_is_not_mapped():
    from agentprov.adapters.runner import NotOfDialect, map_artefact_total
    from agentprov.adapters.types import Origin

    label = support.F["R1"][1]
    origin = Origin.member("0" * 64, label, 8, "00000000", 2)
    with pytest.raises(NotOfDialect):
        map_artefact_total(b"[]", origin, profile_id="redcode-exec-openhands")
    with pytest.raises(MalformedArtefact):
        map_artefact_total(b'{"a": 1}', origin, profile_id="redcode-exec-openhands")
