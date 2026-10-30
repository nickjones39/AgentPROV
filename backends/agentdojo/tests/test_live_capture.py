"""K.8.1 at the backend level: real AgentDojo 0.1.35 suite tasks driven through ``build_instrumented_pipeline`` with
``ScriptedTransport`` as the HTTP transport *under* the recording transport of the real OpenAI SDK client of the
stock element (no network, no keys). The (core) rows of K.8.1 are checked in core on the produced sessions (K.8.5).

Every produced session must verify sealed, every ``llm.request`` must carry ``input_at`` and ``n_messages``, and the
recorded request bodies must be the bytes the server received (``support.assert_capture_invariants``)."""

from __future__ import annotations

import json

import pytest
from agentdojo.models import MODEL_NAMES

from agentprov_backend.testing import Fail, Reply
from agentprov_backend.testing.scenarios import SCENARIOS, benign_cell
from support import assert_capture_invariants, pass_message_lists, run_cell, run_scenario

NATIVE = SCENARIOS["benign_banking_single_pass"].agent
GATEWAY = {**NATIVE, "llm_element": "gateway_compat", "endpoint": "deepseek"}
OPENROUTER_GATEWAY = {**NATIVE, "llm_element": "gateway_compat", "endpoint": "openrouter"}
CELL = benign_cell("banking", "user_task_1")
READ = {"name": "get_most_recent_transactions", "args": {"n": 100}, "id": "call_1"}
ANSWER = "You spent 1050 in March 2022."


def _statuses(run):
    return [(e["data"]["call"], e["data"]["status"], e["data"].get("reason")) for e in run.of("llm.response")]


# ------------------------------------------------------------------ one benign cell per v1.2.2 suite

BENIGN = {
    "banking": ("user_task_1", {"name": "get_balance", "args": {}}),
    "workspace": ("user_task_0", {"name": "get_current_day", "args": {}}),
    "travel": ("user_task_0", {"name": "get_user_information", "args": {}}),
    "slack": ("user_task_0", {"name": "get_channels", "args": {}}),
}


@pytest.mark.parametrize("suite", sorted(BENIGN))
def test_one_benign_cell_per_suite(tmp_path, suite):
    task, call = BENIGN[suite]
    run = run_cell(tmp_path, benign_cell(suite, task), NATIVE, [Reply.tool_calls([call]), Reply.text("Done.")])
    assert run.result.status == "complete"
    assert_capture_invariants(run)
    types = [e["type"] for e in run.events]
    assert types[:3] == ["session.start", "instrumentation", "identity"] and types[-1] == "session.end"
    assert types.count("pass.start") == types.count("pass.end") == 1
    assert [e["data"]["n_messages"] for e in run.of("llm.request")] == [2, 4]
    assert run.of("tool.result")[0]["data"]["status"] == "ok"
    native = run.native()
    assert native["suite_name"] == suite and native["user_task_id"] == task
    # the pass dump is the native log's message list (the native log keeps the last pass)
    (dump,) = pass_message_lists(run)
    assert json.dumps(dump, sort_keys=True) == json.dumps(native["messages"], sort_keys=True)
    assert run.judgements()["security"] == (True, "harness_default")
    assert run.judgements()["utility"][1] == "checker"


# ------------------------------------------------------------------ attacks


def test_injection_cell_with_an_explicit_display_name_leaves_model_names_unchanged(tmp_path):
    before = dict(MODEL_NAMES)
    run = run_scenario(tmp_path, "injection_important_instructions")
    assert dict(MODEL_NAMES) == before and list(MODEL_NAMES) == list(before)
    assert run.result.status == "complete"
    assert_capture_invariants(run)
    (item,) = [i for i in run.of("instrumentation")[0]["data"]["items"]
               if i["id"] == "agentdojo.attack_model_display_name@1"]
    assert item["kind"] == "attack_parameter" and item["params"]["display_name"] == "Scripted Model"
    fixtures = run.of("fixture")
    assert fixtures and all(f["data"]["kind"] == "injection_payload" and f["actor"] == "attacker" for f in fixtures)
    assert {f["data"]["vector"]: f["data"]["content"] for f in fixtures} == run.native()["injections"]
    assert all("Scripted Model" in f["data"]["content"] for f in fixtures)
    assert run.judgements() == {"utility": (run.result.outcome["utility"], "checker"),
                                "security": (run.result.outcome["security"], "checker")}
    assert run.of("session.start")[0]["data"]["cell"]["attack_params"] == {"model_display_name": "Scripted Model"}


def test_payload_fidelity_wire_capture_native(tmp_path):
    """SEC-14: the payload text is identical in the capture log's fixture, the native log's injections and the wire
    request the model was sent (inside the YAML tool output); nothing is written outside the staging directory."""
    import yaml

    run = run_scenario(tmp_path, "injection_important_instructions")
    assert [p for p in tmp_path.rglob("*") if not p.is_relative_to(run.dir)] == []
    payloads = {f["data"]["vector"]: f["data"]["content"] for f in run.of("fixture")}
    assert payloads == run.native()["injections"]
    second = run.json_blob(run.of("llm.request")[1]["data"]["request"])
    (tool_msg,) = [m for m in second["messages"] if m["role"] == "tool"]
    text = "".join(p["text"] for p in tool_msg["content"])
    native_tool = [m for m in run.native()["messages"] if m["role"] == "tool"][0]
    assert native_tool["content"][0]["content"] == text
    # AgentDojo formats the payload into its environment YAML, whose line folding turns "\n\n" into "\n": the text
    # the model sees differs from attack.attack()'s return in whitespace only (a benchmark artefact, D.10.10; the
    # SEM marker normalisers collapse whitespace on both sides). Our recorders change nothing: wire == native.
    def collapse(t: str) -> str:
        return " ".join(t.split())

    seen = collapse(json.dumps(yaml.safe_load(text), ensure_ascii=False).replace("\\n", " "))
    for payload in payloads.values():
        assert collapse(payload) in seen


def test_a_stock_named_model_needs_no_display_name(tmp_path):
    agent = {**NATIVE, "model_requested": "gpt-4o-2024-05-13"}
    cell = {**SCENARIOS["injection_important_instructions"].cell, "attack_params": {}}
    run = run_cell(tmp_path, cell, agent, [Reply.tool_calls([READ]), Reply.text(ANSWER)])
    assert run.result.status == "complete"
    assert "agentdojo.attack_model_display_name@1" not in run.instrumentation_ids()
    assert all("GPT-4" in f["data"]["content"] for f in run.of("fixture"))


def test_an_attack_without_a_resolvable_name_is_refused_and_sealed(tmp_path):
    before = dict(MODEL_NAMES)
    cell = {**SCENARIOS["injection_important_instructions"].cell, "attack_params": {}}
    run = run_cell(tmp_path, cell, NATIVE, [])
    assert run.result.status == "errored" and dict(MODEL_NAMES) == before
    (err,) = run.of("error")
    assert err["data"]["exception"]["type"] == "UnsupportedConfiguration" and err["data"]["fatal"] is True
    assert run.of("pass.start") == [] and run.transport.bodies == []
    assert_capture_invariants(run)


def test_dos_attack_security_is_the_stock_rule(tmp_path):
    cell = {"cell_key": "banking/user_task_1/dos/injection_task_0", "suite": "banking", "user_task_id": "user_task_1",
            "injection_task_id": "injection_task_0", "attack": "dos", "defence": None, "kind": "dos",
            "attack_params": {"model_display_name": "Scripted Model"}}
    run = run_cell(tmp_path, cell, NATIVE, [Reply.tool_calls([READ]), Reply.text("asdf")])
    assert run.result.status == "complete"
    assert_capture_invariants(run)
    utility, security = run.result.outcome["utility"], run.result.outcome["security"]
    assert security == (not utility)
    assert run.judgements()["security"] == (security, "harness_rule")


# ------------------------------------------------------------------ passes


def test_empty_final_reply_three_passes_are_all_kept(tmp_path):
    run = run_scenario(tmp_path, "rerun_three_passes")
    assert run.result.status == "complete"
    assert_capture_invariants(run)
    starts, ends = run.of("pass.start"), run.of("pass.end")
    assert [e["pass"] for e in starts] == [e["pass"] for e in ends] == [0, 1, 2]
    assert all(e["data"]["aborted"] is False for e in ends)
    # environment chaining: each pass starts from the state the previous one left
    for prev, nxt in zip(ends[:-1], starts[1:], strict=True):
        assert nxt["data"]["env"]["sha256"] == prev["data"]["env"]["sha256"]
    # cross-pass reuse of the provider id: distinct occurrences
    dispatch = run.of("tool.dispatch")
    assert [d["data"]["provider_call_id"] for d in dispatch] == ["call_1", "call_1"]
    assert [d["data"]["occ"] for d in dispatch] == ["o0", "o1"] and [d["pass"] for d in dispatch] == [0, 1]
    # n_messages restarts per pass (fresh messages each pass)
    assert [e["data"]["n_messages"] for e in run.of("llm.request")] == [2, 4, 2, 4, 2]
    # the native log holds only the last pass
    lists = pass_message_lists(run)
    assert len(lists) == 3 and len(run.native()["messages"]) == len(lists[2]) == 3


def test_refusal_in_every_pass(tmp_path):
    steps = [Reply.refusal("I can't help with that"), Reply.refusal("Still no"), Reply.refusal("No")]
    run = run_cell(tmp_path, CELL, NATIVE, steps)
    assert run.result.status == "complete"
    assert_capture_invariants(run)
    assert len(run.of("pass.end")) == 3
    refusals = [run.json_blob(e["data"]["response"])["choices"][0]["message"]["refusal"] for e in run.of("llm.response")]
    assert refusals == ["I can't help with that", "Still no", "No"]


def test_abort_agent_error_pass_is_recorded_aborted(tmp_path):
    run = run_scenario(tmp_path, "aborted_pass")
    assert run.result.status == "complete"
    assert_capture_invariants(run)
    (end,) = run.of("pass.end")
    assert end["data"]["aborted"] is True
    (dump,) = pass_message_lists(run)
    assert dump[-1]["role"] == "assistant" and dump[-1]["content"][0]["content"] == "aborted by a simulated guard"
    assert run.of("tool.dispatch") == [] and run.of("error") == []


def test_max_iters_cut_leaves_tool_calls_pending(tmp_path):
    steps = [Reply.tool_calls([READ], content="checking") for _ in range(16)]
    run = run_cell(tmp_path, CELL, NATIVE, steps)
    assert run.result.status == "complete"
    assert_capture_invariants(run)
    assert len(run.of("llm.request")) == 16 and len(run.of("tool.dispatch")) == 15
    (dump,) = pass_message_lists(run)
    assert dump[-1]["role"] == "assistant" and dump[-1]["tool_calls"]


# ------------------------------------------------------------------ tools


def test_tool_errors_and_invalid_names(tmp_path):
    run = run_scenario(tmp_path, "tool_errors")
    assert run.result.status == "complete"
    assert_capture_invariants(run)
    results = [e["data"] for e in run.of("tool.result")]
    assert [r["status"] for r in results] == ["invalid", "invalid", "error"]
    unknown, invalid_args, raised = results
    assert unknown["model_visible"] == "Invalid tool no_such_tool provided." and unknown["rendered"] == ""
    assert invalid_args["exception"]["type"] == "ValidationError" and "args_effective" not in invalid_args
    assert raised["exception"] == {"type": "ValueError", "message": "Transaction with ID 999 not found."}
    assert raised["args_effective"]["id"] == 999
    for r in results:
        assert r["model_visible"] == r["error"] and r["rendered"] == "" and "returned" not in r
    # what the model was sent is the error text (openai_llm.py:103)
    sent = run.json_blob(run.of("llm.request")[1]["data"]["request"])
    assert [m["content"] for m in sent["messages"] if m["role"] == "tool"] == [r["error"] for r in results]


# ------------------------------------------------------------------ provider failures, native element


def test_native_malformed_tool_json_is_stock_failure(tmp_path):
    run = run_cell(tmp_path, CELL, NATIVE, [Fail.malformed_args('{"n": 5'), Reply.text(ANSWER)])
    assert run.result.status == "errored"
    assert_capture_invariants(run)
    assert _statuses(run) == [("c0", "discarded", "element_raised:JSONDecodeError")]
    (pass_end,) = run.of("pass.end")
    assert pass_end["data"]["aborted"] is True
    assert [e["data"]["where"] for e in run.of("error")] == ["pipeline", "cell"]
    assert run.native()["messages"]          # partial native evidence is kept


@pytest.mark.parametrize("element", ["native", "gateway_compat"])
def test_upstream_5xx_is_retried_and_every_attempt_recorded(tmp_path, element):
    agent = NATIVE if element == "native" else GATEWAY
    steps = [Fail.http(503), Fail.http(502), Fail.http(503), Fail.http(500), Reply.tool_calls([READ]), Reply.text(ANSWER)]
    run = run_cell(tmp_path, CELL, agent, steps)
    assert run.result.status == "complete"
    assert_capture_invariants(run)
    statuses = _statuses(run)
    assert [s for _, s, _ in statuses] == ["error"] * 4 + ["kept", "kept"]
    assert [r for _, _, r in statuses][:4] == ["http_503", "http_502", "http_503", "http_500"]
    reqs = [e["data"] for e in run.of("llm.request")]
    if element == "native":
        # the SDK's own retries: c0, c1 (retry_of c0), c2 (retry_of c1) ...
        assert [r.get("retry_of") for r in reqs[:5]] == [None, "c0", "c1", "c2", "c3"]
        assert [r["attempt"] for r in reqs[:5]] == [0, 1, 2, 3, 4]
    else:
        observed = run.notes("instrumentation_observed")[0]
        assert observed["agentdojo.http_backoff@1"] == {"retried": 1}


@pytest.mark.parametrize("element", ["native", "gateway_compat"])
def test_a_4xx_is_not_retried(tmp_path, element):
    agent = NATIVE if element == "native" else GATEWAY
    run = run_cell(tmp_path, CELL, agent, [Fail.http(400, code="invalid_request")])
    assert run.result.status == "errored"
    assert_capture_invariants(run)
    assert _statuses(run) == [("c0", "error", "http_400")]
    assert run.of("error")[-1]["data"]["exception"]["type"] == "BadRequestError"


def test_deterministic_5xx_native(tmp_path):
    run = run_cell(tmp_path, CELL, NATIVE, [Fail.http(500)] * 9)
    assert run.result.status == "errored"
    assert_capture_invariants(run)
    # the SDK's 3 tries inside each of agentdojo's 3 tenacity attempts
    assert [s for _, s, _ in _statuses(run)] == ["error"] * 9


def test_deterministic_5xx_gateway_compat_is_bounded(tmp_path):
    run = run_cell(tmp_path, CELL, GATEWAY, [Fail.http(500)] * 9)
    assert run.result.status == "errored"
    assert_capture_invariants(run)
    assert len(run.of("llm.request")) <= 9


def test_native_no_choices_is_stock_failure(tmp_path):
    run = run_cell(tmp_path, CELL, NATIVE, [Fail.no_choices()])
    assert run.result.status == "errored"
    assert_capture_invariants(run)
    assert _statuses(run) == [("c0", "discarded", "element_raised:TypeError")]


def test_run_error_imposed_by_the_stock_runner(tmp_path):
    run = run_scenario(tmp_path, "run_error_context_length")
    assert run.result.status == "complete"
    assert_capture_invariants(run)
    assert run.native()["error"] is not None
    assert run.judgements() == {"utility": (False, "harness_default"), "security": (True, "harness_default")}
    assert [e["data"]["where"] for e in run.of("error")] == ["pipeline"]


def test_a_failing_cell_is_sealed_and_kept(tmp_path):
    run = run_scenario(tmp_path, "failing_cell_uncaught_400")
    assert run.result.status == "errored"
    assert_capture_invariants(run)
    assert run.of("outcome") == []
    assert run.result.native_artefacts == (run.session.native_label,)
    assert run.of("error")[-1]["data"]["fatal"] is True


# ------------------------------------------------------------------ gateway_compat


def test_gateway_compat_discards_a_malformed_reply_and_resamples(tmp_path):
    run = run_scenario(tmp_path, "gateway_compat_malformed_discarded")
    assert run.result.status == "complete"
    assert_capture_invariants(run)
    statuses = _statuses(run)
    assert statuses[0][1] == "discarded" and statuses[0][2].startswith("malformed tool call:")
    assert [s for _, s, _ in statuses[1:]] == ["kept", "kept"]
    assert run.of("llm.request")[1]["data"]["retry_of"] == "c0"
    observed = run.notes("instrumentation_observed")[0]
    assert observed["agentdojo.retry_malformed_tool_json@1"] == {"resampled": 1}
    assert observed["agentdojo.retry_upstream_failure@1"] == {"retried": 0}
    # discarded content recorded
    assert run.json_blob(run.of("llm.response")[0]["data"]["response"])["choices"][0]["message"]["tool_calls"]


def test_gateway_compat_retries_provider_failures(tmp_path):
    run = run_cell(tmp_path, CELL, OPENROUTER_GATEWAY, [Fail.no_choices(), Fail.finish_error(), Reply.text(ANSWER)])
    assert run.result.status == "complete"
    assert_capture_invariants(run)
    statuses = _statuses(run)
    assert [s for _, s, _ in statuses] == ["discarded", "discarded", "kept"]
    assert statuses[0][2].startswith("no choices returned") and statuses[1][2] == "finish_reason=error"
    assert run.notes("instrumentation_observed")[0]["agentdojo.retry_upstream_failure@1"] == {"retried": 2}


def test_gateway_compat_reasoning_passback_reset_per_pass(tmp_path):
    details = [{"type": "reasoning.encrypted", "data": "pass-1 signature"}]
    agent = {**OPENROUTER_GATEWAY, "params": {"reasoning_effort": "low"}}
    steps = [Reply.tool_calls([READ], reasoning="p1 think", reasoning_details=details), Reply.null(),
             Reply.tool_calls([READ], reasoning="p2 think"), Reply.text(ANSWER)]
    run = run_cell(tmp_path, CELL, agent, steps)
    assert run.result.status == "complete"
    assert_capture_invariants(run)
    bodies = [run.json_blob(e["data"]["request"]) for e in run.of("llm.request")]
    assert "pass-1 signature" in json.dumps(bodies[1]["messages"])
    assert "pass-1 signature" not in json.dumps(bodies[3]["messages"])
    assert all(b["extra_body"] if "extra_body" in b else b.get("reasoning") == {"effort": "low"} for b in bodies)
    assert "agentdojo.reasoning_passback@1" in run.instrumentation_ids()
    # RT-1: reasoning never enters the scored messages
    assert "p2 think" not in json.dumps(run.native()["messages"])


# ------------------------------------------------------------------ providers and reasoning


def test_reasoning_content_is_in_the_response_blob_not_the_messages(tmp_path):
    steps = [Reply.tool_calls([READ]), Reply.reasoning(ANSWER, "ds thoughts", field="reasoning_content")]
    run = run_cell(tmp_path, CELL, NATIVE, steps)
    assert run.result.status == "complete"
    assert_capture_invariants(run)
    last = run.json_blob(run.of("llm.response")[-1]["data"]["response"])
    assert last["choices"][0]["message"]["reasoning_content"] == "ds thoughts"
    assert "ds thoughts" not in json.dumps(run.native()["messages"])


def test_a_provider_without_usage(tmp_path):
    run = run_cell(tmp_path, CELL, NATIVE, [Reply.tool_calls([READ], usage=None), Reply.text(ANSWER, usage=None)])
    assert run.result.status == "complete"
    assert_capture_invariants(run)
    assert all("usage" not in e["data"] for e in run.of("llm.response"))
    assert all(e["data"]["status"] == "kept" for e in run.of("llm.response"))


def test_usage_served_model_and_ids_are_recorded_from_the_provider(tmp_path):
    run = run_scenario(tmp_path, "benign_banking_single_pass")
    first = run.of("llm.response")[0]["data"]
    assert first["usage"] == {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120}
    assert first["served_model"] == "scripted-fake" and first["response_id"] == "scripted-0"
    assert first["finish_reason"] == "tool_calls"


# ------------------------------------------------------------------ declarations


def test_native_default_declares_temperature_not_transmitted_and_no_rewrite(tmp_path):
    run = run_scenario(tmp_path, "benign_banking_single_pass")
    items = {i["id"]: i for i in run.of("instrumentation")[0]["data"]["items"]}
    assert items["agentdojo.temperature_not_transmitted@1"]["kind"] == "harness_policy"
    assert items["agentdojo.transport_scripted@1"]["kind"] == "test_only"
    for absent in ("agentdojo.role_rewrite_developer_to_system@1", "agentdojo.retry_malformed_tool_json@1",
                   "agentdojo.retry_upstream_failure@1", "agentdojo.reasoning_passback@1"):
        assert absent not in items
    assert all(i["kind"] == "behaviour_preserving" for k, i in items.items()
               if k in ("agentdojo.pass_recorder_wrap@1", "agentdojo.executor_mirror@1",
                        "agentdojo.recording_runtime_class@1", "agentdojo.recording_transport@1",
                        "agentdojo.llm_span_brackets@1", "agentdojo.env_dump_per_pass@1"))
    first = run.json_blob(run.of("llm.request")[0]["data"]["request"])
    assert first["messages"][0]["role"] == "developer"          # stock element: no rewrite
    assert "temperature" not in first
    assert run.of("llm.request")[0]["data"]["params"]["transmitted"] == {"tool_choice": "auto"}


def test_configured_temperature_is_recorded_apart_from_transmitted(tmp_path):
    run = run_cell(tmp_path, CELL, {**NATIVE, "params": {"temperature": 0.0}},
                   [Reply.tool_calls([READ]), Reply.text(ANSWER)])
    params = run.of("llm.request")[0]["data"]["params"]
    assert params["configured"] == {"temperature": 0} and "temperature" not in params["transmitted"]
    run2 = run_cell(tmp_path / "b", CELL, {**NATIVE, "params": {"temperature": 0.7}},
                    [Reply.tool_calls([READ]), Reply.text(ANSWER)])
    assert run2.of("llm.request")[0]["data"]["params"]["transmitted"]["temperature"] == 0.7
    assert "agentdojo.temperature_not_transmitted@1" not in run2.instrumentation_ids()


def test_gateway_compat_declares_rewrite_and_resampling(tmp_path):
    run = run_cell(tmp_path, CELL, GATEWAY, [Reply.tool_calls([READ]), Reply.text(ANSWER)])
    items = {i["id"]: i for i in run.of("instrumentation")[0]["data"]["items"]}
    assert items["agentdojo.role_rewrite_developer_to_system@1"]["kind"] == "request_modifying"
    assert items["agentdojo.retry_malformed_tool_json@1"]["params"]["max"] == 8
    assert items["agentdojo.retry_upstream_failure@1"]["kind"] == "harness_policy"
    first = run.json_blob(run.of("llm.request")[0]["data"]["request"])
    assert first["messages"][0]["role"] == "system"
    assert "agentdojo.reasoning_passback@1" not in items          # not OpenRouter


def test_the_undefended_builder_refuses_a_defence_and_non_yaml_and_unknown_defences_are_refused(tmp_path):
    # a registered defence is built by defences.build_defended_pipeline (tests/test_defences.py), never here
    from agentdojo.agent_pipeline import PipelineConfig

    from agentprov_backend.runner import CaptureSession, UnsupportedConfiguration, build_instrumented_pipeline

    llm = object.__new__(__import__("agentdojo").agent_pipeline.llms.openai_llm.OpenAILLM)
    llm.name = "m"
    for kwargs in ({"defense": "tool_filter"}, {"defense": None, "tool_output_format": "json"}):
        config = PipelineConfig.model_construct(llm=llm, model_id=None, defense=kwargs.get("defense"),
                                                system_message="s", system_message_name=None,
                                                tool_output_format=kwargs.get("tool_output_format"))
        with pytest.raises(UnsupportedConfiguration):
            build_instrumented_pipeline(config, CaptureSession(tmp_path / "x"))
    cell = {**CELL, "defence": "no_such_defence"}
    run = run_cell(tmp_path, cell, NATIVE, [])
    assert run.result.status == "errored"
    assert run.of("error")[0]["data"]["exception"]["type"] == "UnsupportedConfiguration"
    run2 = run_cell(tmp_path / "j", CELL, NATIVE, [], backend_config={"tool_output_format": "json"})
    assert run2.result.status == "errored"
    assert_capture_invariants(run2)


# ------------------------------------------------------------------ secrets


def test_secrets_are_absent_from_every_artefact(tmp_path):
    sentinel = "sk-agentprov-sentinel-4f1c9e"
    agent = {**NATIVE, "api_key_env": "FAKE_PROVIDER_API_KEY"}
    environ = {"FAKE_PROVIDER_API_KEY": sentinel, "OTHER_TOKEN": sentinel + "-2"}
    run = run_cell(tmp_path, CELL, agent, [Reply.tool_calls([READ]), Reply.text(ANSWER)], environ=environ)
    assert run.result.status == "complete"
    # the key reached the provider (Authorization header) ...
    assert run.transport.requests[0].headers["authorization"] == f"Bearer {sentinel}"
    # ... and appears in no staged file
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert sentinel.encode() not in path.read_bytes(), path.name


# ---- D-693: the local model's identity (T0's observation) -------------------------------------------------------

def test_agent_local_model_is_optional_and_leaves_remote_agents_unchanged():
    from agentprov_backend.runner import AgentConfig

    plain = AgentConfig.from_json(NATIVE)
    assert "local_model" not in plain.to_json()  # a remote endpoint's plan and config digests are unchanged
    record = {"format": "agentprov-local-model/0.1", "identity_sha256": "sha256:" + "1" * 64}
    local = AgentConfig.from_json({**NATIVE, "local_model": record})
    assert local.to_json()["local_model"] == record
    assert AgentConfig.from_json(local.to_json()) == local


@pytest.mark.parametrize("bad", ["x", ["x"], {"blob": "y" * 70_000}])
def test_agent_local_model_must_be_a_bounded_object(bad):
    from agentprov_backend.runner import AgentConfig, UnsupportedConfiguration

    with pytest.raises((UnsupportedConfiguration, ValueError)):
        AgentConfig.from_json({**NATIVE, "local_model": bad})


def test_local_model_note_is_written_as_given_and_only_when_given(tmp_path):
    sc = SCENARIOS["benign_banking_single_pass"]
    observed = {"observed": {"format": "agentprov-local-model/0.1", "model_id": "m"}, "matches_plan": True,
                "plan_identity_sha256": "sha256:" + "2" * 64}
    with_note = run_scenario(tmp_path / "a", sc, local_model=observed)
    without = run_scenario(tmp_path / "b", sc)
    assert with_note.notes("local_model") == [observed]
    assert without.notes("local_model") == []
    assert_capture_invariants(with_note)


# ---- D-698: a LAN endpoint (opted in) -----------------------------------------------------------------------------

def test_allow_lan_is_optional_keyless_and_accepts_a_private_http_url():
    from agentprov_backend.runner import AgentConfig, UnsupportedConfiguration, resolve_base_url

    assert "allow_lan" not in AgentConfig.from_json(NATIVE).to_json()
    lan = {**NATIVE, "endpoint": "lmstudio", "api_key_env": None, "base_url": "http://192.168.1.20:1234/v1"}
    with pytest.raises(UnsupportedConfiguration):
        resolve_base_url(AgentConfig.from_json(lan))  # http off loopback without the opt-in
    agent = AgentConfig.from_json({**lan, "allow_lan": True})
    assert resolve_base_url(agent) == "http://192.168.1.20:1234/v1" and agent.to_json()["allow_lan"] is True
    with pytest.raises(UnsupportedConfiguration):
        AgentConfig.from_json({**lan, "allow_lan": True, "api_key_env": "OPENAI_API_KEY"})
    with pytest.raises(UnsupportedConfiguration):
        resolve_base_url(AgentConfig.from_json({**lan, "allow_lan": True, "base_url": "http://8.8.8.8/v1"}))
