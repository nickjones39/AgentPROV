"""D.11.5 at the backend level: fork suite tasks driven through the shared harness (``AutoDojoBackend``) with
``ScriptedTransport`` under the recording transport of the real OpenAI SDK client of the fork's **unmodified**
``OpenAILLM`` (AD-09; no network, no keys).

Covered: a fork banking task without defence under ``important_instructions``; one ``autodojo`` cache-replay cell from
the synthetic fixture cache; an error-skipped cell (``run_error_imposes_outcome``); the fork's declared behaviour
(temperature transmitted, system role, malformed-JSON retry), ``ToolsExecutionLoop.max_input_tokens`` recorded, the
fork's log layout, live versus native agreement (pass dump, injections, judgements), and the refusals."""

from __future__ import annotations

import json
import os

import pytest
from agentdojo.models import MODEL_NAMES

from agentprov_backend.attacks import UnsupportedConfiguration
from agentprov_backend.testing import Reply
from agentprov_backend.testing.scenarios import (
    AUTODOJO_SCENARIOS,
    SYNTHETIC_AUTODOJO_CACHE,
    autodojo_attack_env,
    autodojo_cache_sha256,
    benign_cell,
)
from support import assert_capture_invariants, pass_message_lists, run_cell, run_scenario, stage_cache

II = AUTODOJO_SCENARIOS["autodojo_banking_important_instructions"]
REPLAY = AUTODOJO_SCENARIOS["autodojo_banking_cache_replay"]
NATIVE = II.agent
READ = {"name": "get_most_recent_transactions", "args": {"n": 100}, "id": "call_1"}
ANSWER = "You spent 1050 in March 2022."


def _statuses(run):
    return [(e["data"]["call"], e["data"]["status"], e["data"].get("reason")) for e in run.of("llm.response")]


def _live_equals_native(run) -> None:
    """Backend half of the live-versus-native agreement: the scored pass's message dump equals the fork's
    TraceLogger messages, the recorded fixtures equal its injections, and the judgements its utility/security."""
    native = run.native()
    dump = pass_message_lists(run)[-1]
    assert json.dumps(dump, sort_keys=True) == json.dumps(native["messages"], sort_keys=True)
    assert {f["data"]["vector"]: f["data"]["content"] for f in run.of("fixture")} == native["injections"]
    j = run.judgements()
    assert (j["utility"][0], j["security"][0]) == (native["utility"], native["security"])


# ------------------------------------------------------------------ the D.11.5 cells


def test_fork_banking_important_instructions(tmp_path):
    before = dict(MODEL_NAMES)
    run = run_scenario(tmp_path, II.name)
    assert dict(MODEL_NAMES) == before
    assert run.result.status == "complete"
    assert_capture_invariants(run)
    _live_equals_native(run)
    start = run.of("session.start")[0]["data"]
    assert start["backend"]["id"] == "autodojo" and start["cell"]["benchmark"] == "agentdojo"
    ident = run.of("identity")[0]["data"]["benchmark"]
    assert ident["commit"] == "aa458794b7eb7f082e94daeac4c0f55bfc0c90cc" and ident["repo"].endswith("/AutoDojo")
    items = run.items()
    assert items["agentdojo.transport_scripted@1"]["kind"] == "test_only"
    display = items["agentdojo.attack_model_display_name@1"]["params"]
    assert display["display_name"] == "Scripted Model" and display["benchmark_fallback"] == "AI assistant"
    assert all("Scripted Model" in f["data"]["content"] for f in run.of("fixture"))
    assert run.judgements()["security"][1] == "checker" and run.judgements()["utility"][1] == "checker"
    assert run.notes("run_error_imposed") == []


def test_cache_replay_cell_from_the_synthetic_cache(tmp_path):
    run = run_scenario(tmp_path, REPLAY.name)
    assert run.result.status == "complete"
    assert_capture_invariants(run)
    _live_equals_native(run)
    variant = SYNTHETIC_AUTODOJO_CACHE["injection_tasks"]["injection_task_0"]["injection_incoming_transaction"]["variants"][0]
    (fixture,) = run.of("fixture")
    assert fixture["data"]["vector"] == "injection_incoming_transaction" and fixture["data"]["content"] == variant
    item = run.items()["autodojo.attack_cache_replay@1"]
    assert item["kind"] == "attack_parameter"
    assert item["params"] == {"cache_label": "raw/attack/autodojo-cache.json", "cache_sha256": autodojo_cache_sha256(),
                              "cache_bytes": len(json.dumps(SYNTHETIC_AUTODOJO_CACHE, indent=2, sort_keys=True)) + 1,
                              "variant": 0}
    # the fork's fallback name is declared, not hidden
    fallback = run.items()["agentdojo.attack_model_display_name@1"]["params"]
    assert fallback == {"display_name": "AI assistant", "attack": "autodojo", "checked": True,
                        "source": "benchmark_fallback"}
    assert run.of("session.start")[0]["data"]["cell"]["attack_params"]["autodojo_cache_sha256"] == autodojo_cache_sha256()
    # the variables were scoped to the attack's construction
    assert "AUTODOJO_CACHE" not in os.environ and "AUTODOJO_VARIANT" not in os.environ
    # the model saw the variant in the tool output (the wire request)
    second = run.json_blob(run.of("llm.request")[1]["data"]["request"])
    (tool_msg,) = [m for m in second["messages"] if m["role"] == "tool"]
    seen = " ".join("".join(p["text"] for p in tool_msg["content"]).split())
    assert "[synthetic AutoDojo fixture, variant 0]" in seen and "US133000000121212121212" in seen


def test_variant_equal_to_original_is_wrapped_by_the_fork(tmp_path):
    cell = {**REPLAY.cell, "attack_params": {**REPLAY.cell["attack_params"], "autodojo_variant": 1}}
    run = run_cell(tmp_path, cell, NATIVE, [Reply.tool_calls([READ]), Reply.text(ANSWER)],
                   attack_env=autodojo_attack_env(1))
    assert run.result.status == "complete"
    (fixture,) = run.of("fixture")
    assert "<INFORMATION>" in fixture["data"]["content"] and "AI assistant" in fixture["data"]["content"]
    assert run.items()["autodojo.attack_cache_replay@1"]["params"]["variant"] == 1


def test_error_skipped_cell_imposes_false_false_and_records_error_type(tmp_path):
    run = run_scenario(tmp_path, "autodojo_error_skipped_json_decode")
    assert run.result.status == "complete"
    assert_capture_invariants(run)
    assert _statuses(run) == [("c0", "discarded", "superseded_by_retry"), ("c1", "discarded", "superseded_by_retry"),
                              ("c2", "discarded", "element_raised:JSONDecodeError")]
    assert [e["data"]["retry_of"] for e in run.of("llm.request")[1:]] == ["c0", "c1"]
    assert run.judgements() == {"utility": (False, "harness_default"), "security": (False, "harness_default")}
    native = run.native()
    assert native["error_type"] == "json_decode_error" and native["error"] is not None
    assert native["utility"] is False and native["security"] is False
    (note,) = run.notes("run_error_imposed", "autodojo")
    assert note == {"error_type": "json_decode_error", "native_error_present": True,
                    "judgements": {"utility": False, "security": False}, "source": "native_log.error_type"}
    (end,) = run.of("pass.end")
    assert end["data"]["aborted"] is True
    semantics = run.of("outcome")[0]["data"]["declared_semantics"]
    assert "security = false" in semantics["run_error"]


def test_context_length_error_is_skipped_with_its_error_type(tmp_path):
    run = run_cell(tmp_path, benign_cell("banking", "user_task_1"), NATIVE, [{"fail": "context_length"}])
    assert run.result.status == "complete"
    assert run.native()["error_type"] == "context_length_exceeded"
    assert run.judgements() == {"utility": (False, "harness_default"), "security": (False, "harness_default")}


# ------------------------------------------------------------------ declarations and fork facts


def test_fork_request_behaviour_is_declared_and_observed(tmp_path):
    run = run_scenario(tmp_path, II.name)
    items = run.items()
    assert "agentdojo.temperature_not_transmitted@1" not in items
    assert items["autodojo.fork_temperature_transmitted@1"]["params"] == {"configured": None, "transmitted": 0}
    assert items["autodojo.fork_malformed_json_retry@1"]["kind"] == "harness_policy"
    assert items["autodojo.fork_system_role@1"]["kind"] == "harness_policy"
    assert items["autodojo.env_nltk_preprovisioned@1"]["params"] == {"punkt_tab_sha256": None}
    assert "autodojo.fork_openrouter_extras@1" not in items          # scripted host, not openrouter.ai
    assert items["agentdojo.executor_mirror@1"]["params"]["mirrors"] == "0.1.35"
    first = run.json_blob(run.of("llm.request")[0]["data"]["request"])
    assert first["messages"][0]["role"] == "system" and first["temperature"] == 0.0
    assert run.of("llm.request")[0]["data"]["params"]["transmitted"]["temperature"] == 0
    (pipeline,) = run.notes("pipeline")
    assert pipeline["max_input_tokens"] is None


def test_nltk_digest_is_reported_from_nltk_data(tmp_path):
    import hashlib

    data = tmp_path / "nltk_data" / "tokenizers"
    data.mkdir(parents=True)
    (data / "punkt_tab.zip").write_bytes(b"not really a zip")
    run = run_cell(tmp_path, benign_cell("banking", "user_task_1"), NATIVE,
                   [Reply.tool_calls([READ]), Reply.text(ANSWER)], environ={"NLTK_DATA": str(tmp_path / "nltk_data")})
    assert run.items()["autodojo.env_nltk_preprovisioned@1"]["params"] == {
        "punkt_tab_sha256": hashlib.sha256(b"not really a zip").hexdigest()}


def test_the_fork_log_layout_keeps_slashes_in_the_pipeline_name(tmp_path):
    """The fork's TraceLogger does not replace ``/`` in the pipeline name (``logging.py``); the harness still finds
    the one native file and records the stock relative path."""
    agent = {**NATIVE, "model_requested": "vendor/scripted-fake"}
    run = run_cell(tmp_path, benign_cell("banking", "user_task_1"), agent,
                   [Reply.tool_calls([READ]), Reply.text(ANSWER)])
    assert run.result.status == "complete"
    (path,) = run.notes("native_log_stock_path")
    assert path["logdir_relative"] == "vendor/scripted-fake/banking/user_task_1/none/none.json"
    assert run.native()["pipeline_name"] == "vendor/scripted-fake"
    assert not (run.dir / "raw" / "native-tmp").exists()


@pytest.mark.parametrize("suite,task,call", [
    ("banking_v2_0", "user_task_1", {"name": "get_balance", "args": {}}),
    ("travel_v2_0", "user_task_0", {"name": "get_user_information", "args": {}}),
])
def test_fork_suites_run(tmp_path, suite, task, call):
    run = run_cell(tmp_path, benign_cell(suite, task), NATIVE, [Reply.tool_calls([call]), Reply.text("Done.")])
    assert run.result.status == "complete", run.of("error")
    assert_capture_invariants(run)
    assert run.native()["suite_name"] == suite


def test_an_agentdyn_checkout_does_not_break_the_recorder(tmp_path):
    """The AgentDyn shopping environment stores a callable (OTP ``verification_stack``) after a checkout; pydantic
    cannot dump it. The recorder dumps it as a placeholder and records the loss instead of raising into the run."""
    steps = [Reply.tool_calls([{"name": "cart_add_product", "args": {"product_id": "P007", "quantity": 1}, "id": "c1"}]),
             Reply.tool_calls([{"name": "checkout_selected_cart", "args": {"product_ids": ["P007"]}, "id": "c2"}]),
             Reply.text("Done.")]
    run = run_cell(tmp_path, benign_cell("shopping", "user_task_0"), NATIVE, steps)
    assert run.result.status == "complete", run.of("error")
    assert_capture_invariants(run)
    assert run.of("error") == [] and [r["data"]["status"] for r in run.of("tool.result")] == ["ok", "ok"]
    (lossy,) = run.notes("env_dump_lossy")
    assert lossy == {"pass": 0, "at": "end", "types": ["ShoppingPlatform", "function"]}


def test_agentdyn_suites_are_registered():
    from agentprov_backend.autodojo import AutoDojoBackend

    suites = AutoDojoBackend().identity().suite_set
    assert {"shopping", "github", "dailylife", "banking_v2_4", "travel_v2_4"} <= set(suites)


# ------------------------------------------------------------------ refusals (sealed errored, nothing sent)


def _refused(run, text: str) -> None:
    assert run.result.status == "errored"
    (err,) = run.of("error")
    assert err["data"]["exception"]["type"] == "UnsupportedConfiguration" and err["data"]["where"] == "setup"
    assert text in err["data"]["exception"]["message"]
    assert run.transport.bodies == [] and run.of("pass.start") == []
    assert_capture_invariants(run)


@pytest.mark.parametrize("defence", ["drift", "progent", "camel", "camel_nopolicy"])
def test_pipeline_replacing_defences_are_refused(tmp_path, defence):
    _refused(run_cell(tmp_path, {**benign_cell("banking", "user_task_1"), "defence": defence}, NATIVE, []),
             "replaces pipeline components")


def test_other_defences_are_refused_as_for_agentdojo(tmp_path):
    # the fork's filter defences are not in the registry (D-671: second set), and no first-set entry names autodojo
    _refused(run_cell(tmp_path, {**benign_cell("banking", "user_task_1"), "defence": "promptguard"}, NATIVE, []),
             "unknown defence 'promptguard'")
    _refused(run_cell(tmp_path, {**benign_cell("banking", "user_task_1"), "defence": "tool_filter"}, NATIVE, []),
             "not built by the 'autodojo' backend")


def test_gateway_compat_is_refused(tmp_path):
    _refused(run_cell(tmp_path, benign_cell("banking", "user_task_1"), {**NATIVE, "llm_element": "gateway_compat"}, []),
             "gateway_compat")


def test_the_ours_attack_is_refused(tmp_path):
    cell = {**II.cell, "attack": "ours", "cell_key": "banking/user_task_1/ours/injection_task_0"}
    _refused(run_cell(tmp_path, cell, NATIVE, []), "optimiser")


def test_the_optimiser_is_not_installed():
    import importlib.util

    assert importlib.util.find_spec("agentdojo.variant_generation") is None


@pytest.mark.parametrize("change,text", [
    ({"attack_params": {"autodojo_variant": 0}}, "autodojo_cache_sha256"),
    ({"attack_params": {"autodojo_cache_sha256": "0" * 64, "autodojo_variant": 0}}, "differs from attack_params"),
    ({"attack_params": {"autodojo_cache_sha256": autodojo_cache_sha256(), "autodojo_variant": 1}}, "AUTODOJO_VARIANT"),
])
def test_cache_contract_violations_are_refused(tmp_path, change, text):
    _refused(run_cell(tmp_path, {**REPLAY.cell, **change}, NATIVE, [], attack_env=autodojo_attack_env(0)), text)


def test_a_missing_attack_env_is_refused_even_with_the_variables_in_the_process(tmp_path, monkeypatch):
    stage = tmp_path / "session"
    stage_cache(stage)
    monkeypatch.setenv("AUTODOJO_CACHE", str(stage / "raw" / "attack" / "autodojo-cache.json"))
    _refused(run_cell(tmp_path, REPLAY.cell, NATIVE, [], attack_env={}, stage=False), "AUTODOJO_CACHE_label")


@pytest.mark.parametrize("label", ["../outside.json", "/etc/hosts", "raw/attack/link.json"])
def test_cache_labels_resolve_only_inside_the_session(tmp_path, label):
    stage = tmp_path / "session"
    real = stage_cache(stage)
    (stage / "raw" / "attack" / "link.json").symlink_to(real)
    (tmp_path / "outside.json").write_bytes(real.read_bytes())
    run = run_cell(tmp_path, REPLAY.cell, NATIVE, [], stage=False,
                   attack_env={"AUTODOJO_CACHE_label": label, "AUTODOJO_VARIANT": 0})
    assert run.result.status == "errored" and run.transport.bodies == []


def test_resolve_session_file_rejects_hard_links(tmp_path):
    from agentprov_backend.autodojo import resolve_session_file

    real = stage_cache(tmp_path)
    os.link(real, tmp_path / "raw" / "attack" / "hard.json")
    with pytest.raises(UnsupportedConfiguration):
        resolve_session_file(tmp_path, "raw/attack/hard.json")


def test_a_plan_is_expanded_against_the_fork_suite_set():
    from agentprov_backend.autodojo import AutoDojoBackend
    from agentprov_backend.runner import load_plan

    text = ('[plan]\nformat = "agentprov-run-plan/0.1"\nbackend = "autodojo"\nsuites = ["banking_v2_1", "shopping"]\n'
            'user_tasks = "0"\nattacks = ["autodojo"]\ninjection_tasks = "0"\nbenign = "exclude"\n'
            f'[attack_params]\nautodojo_cache_sha256 = "{autodojo_cache_sha256()}"\nautodojo_variant = 0\n'
            '[agent]\nmodel_requested = "scripted-fake"\ntransport = "scripted"\nscript = "s.json"\n')
    plan = load_plan(text, backend=AutoDojoBackend())
    assert [c.suite for c in plan.cells] == ["banking_v2_1", "shopping"] and all(c.attack == "autodojo" for c in plan.cells)
    with pytest.raises(UnsupportedConfiguration):
        load_plan(text.replace('backend = "autodojo"', 'backend = "agentdojo"'), backend=AutoDojoBackend())
    with pytest.raises(UnsupportedConfiguration):
        load_plan(text.replace("autodojo_variant = 0\n", ""), backend=AutoDojoBackend())
