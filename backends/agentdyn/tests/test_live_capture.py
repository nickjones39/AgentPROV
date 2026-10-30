"""Scripted cells through the AgentDyn backend (D-688, sessions S1..S4 of the design note), in process: sealed and
verified capture logs, AgentDyn's identity and instrumentation in the header, AgentDyn's default system message on the
wire, and AgentDyn's harness behaviour where it differs from stock (design F-5)."""

from __future__ import annotations

import hashlib
import json

import pytest

from support import PIN, REPO, SYSTEM_PROMPT_SHA256, run_scenario

pytestmark = pytest.mark.backend_agentdyn

AGENTDYN_ITEMS = {"agentdyn.temperature_transmitted@1", "agentdyn.malformed_tool_calls_dropped@1",
                  "agentdyn.json_decode_error_imposes_outcome@1", "agentdyn.model_output_last_assistant@1"}


def _verify(run) -> None:
    from agentprov_capture.verify import verify_file

    report = verify_file(run.session.capture_path)
    assert report.sealed and not report.issues, report
    assert report.status == run.result.status and report.head == run.result.capture_head
    assert [run.blob(e["data"]["request"]) for e in run.of("llm.request")] == run.transport.bodies


def _first_request(run) -> dict:
    return json.loads(run.transport.bodies[0])


@pytest.mark.parametrize("name", ["s1_shopping_benign", "s2_github_important_instructions", "s3_workspace_benign",
                                  "s4_dailylife_malformed_call_dropped"])
def test_scripted_cell_is_sealed_with_agentdyn_identity(tmp_path, name):
    run = run_scenario(tmp_path, name)
    assert run.result.status == "complete", run.of("error")
    _verify(run)
    (start,) = run.of("session.start")
    assert start["data"]["backend"]["id"] == "agentdyn"
    (ident,) = run.of("identity")
    bench = ident["data"]["benchmark"]
    assert bench["repo"] == REPO and bench["commit"] == PIN and bench["dist_version"] == "0.1.35"
    assert bench["system_prompt_sha256"] == SYSTEM_PROMPT_SHA256
    items = run.items()
    assert AGENTDYN_ITEMS <= set(items) and "agentdojo.temperature_not_transmitted@1" not in items
    assert items["agentdojo.executor_mirror@1"]["params"]["mirrors"] == "0.1.35"


def test_agentdyn_sends_its_system_message_as_developer_with_temperature_zero(tmp_path):
    run = run_scenario(tmp_path, "s3_workspace_benign")
    body = _first_request(run)
    system = body["messages"][0]
    assert system["role"] == "developer"
    text = system["content"] if isinstance(system["content"], str) else "".join(p["text"] for p in system["content"])
    assert hashlib.sha256(text.encode("utf-8")).hexdigest() == SYSTEM_PROMPT_SHA256
    assert body["temperature"] == 0.0                     # stock 0.1.35 would omit it
    assert run.items()["agentdyn.temperature_transmitted@1"]["params"]["transmitted"] == 0.0


def test_the_attacked_github_cell_is_judged_by_the_checkers(tmp_path):
    run = run_scenario(tmp_path, "s2_github_important_instructions")
    assert run.judgements() == {"utility": (False, "checker"), "security": (False, "checker")}


def test_a_tool_call_with_non_json_arguments_is_dropped_and_never_dispatched(tmp_path):
    """Design F-5 / D-685: the wire reply lists the call, AgentDyn's assistant message does not, no tool runs."""
    run = run_scenario(tmp_path, "s4_dailylife_malformed_call_dropped")
    (resp,) = run.of("llm.response")
    wire = run.json_blob(resp["data"]["response"])
    assert [c["function"]["name"] for c in wire["choices"][0]["message"]["tool_calls"]] == ["send_email"]
    assert run.of("tool.call") == [] and run.of("tool.result") == []
    (end,) = run.of("pass.end")
    messages = run.json_blob(end["data"]["messages"])
    assert messages[-1]["role"] == "assistant" and not messages[-1].get("tool_calls")
    assert run.judgements()["utility"][1] == "checker"


def test_shopping_tools_read_the_clock_so_reruns_end_in_different_states(tmp_path):
    """R-9b-1: the same tool modules as AutoDojo's copy, so the same nondeterminism (send_email stamps
    datetime.now())."""
    ends = []
    for n in range(2):
        run = run_scenario(tmp_path / str(n), "s1_shopping_benign")
        (start,) = run.of("pass.start")
        (end,) = run.of("pass.end")
        ends.append((start["data"]["env"]["sha256"], end["data"]["env"]["sha256"]))
    assert ends[0][0] == ends[1][0] and ends[0][1] != ends[1][1]
