"""Gate C6 scenarios: the scripted ``_FakeClient`` scenarios of the baseline's ``tests/test_attempts.py`` (docs/
architecture J.3.4 row C6; K.9.2), as data both sides of the gate run.

Every scenario drives a real AgentDojo v1.2.2 task (``banking/user_task_1``, as the baseline tests do) through

* the **old side**, the frozen baseline generator (``generate._run_one_benign`` / ``_run_one_injection`` at ``579a908``,
  run by ``tools/migration/baseline_probe.py`` under the baseline interpreter) with the model shorthand and the
  environment variables of ``old``, and
* the **new side**, ``AgentDojoBackend.execute`` with the ``gateway_compat`` element (the ``_CompatLLM`` port, AD-09),
  ``transport = "scripted"`` and the pipeline name the baseline gave the same cell (``<shorthand>/<model id>+prov``,
  ``generate.py:296``), plus the display-name preset ``adprov-v2.3-title-case`` for attacked cells (F-13),

with the **same wire responses**: :func:`wire_responses` renders each step with
:func:`agentprov_backend.testing.transport.render_response`, the bytes ``ScriptedTransport`` serves, and the probe
serves those bytes to the baseline's SDK client.

``category`` is J.3.4's split: ``a`` = no D5 deviation (single pass, no retry, no gate failure), compared as v1-view
and compat-graph bytes after the time mask; ``b`` = deviation scenarios, compared by ``common_projection`` plus the
registered XD entries listed in ``expect_xd`` (``migration/expected_differences.toml``). ``source`` names the baseline
test each scenario comes from. Nothing here imports a benchmark package.
"""

from __future__ import annotations

import base64
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from agentprov_backend.testing.transport import render_response, step_from_dict

__all__ = ["C6_SCENARIOS", "C6Scenario", "PRESET", "bundle", "wire_responses"]

PRESET = "adprov-v2.3-title-case"
XD_D73 = "XD-C6-D73-capture-verdict"
XD_BENIGN_SECURITY = "XD-C6-D105-benign-security"
XD_GENERATOR_META = "XD-C6-C153-generator-meta"
BENCHMARK_VERSION = "v1.2.2"
SUITE = "banking"
USER_TASK = "user_task_1"
#: placeholder credentials for the scripted providers (never a key; the scripted transport sends nowhere)
_PLACEHOLDER_KEY = "c6-scripted-placeholder-key"

_PROVIDERS: Mapping[str, Mapping[str, Any]] = {
    "deepseek": {"model_id": "deepseek-chat", "endpoint": "deepseek",
                 "env": {"DEEPSEEK_API_KEY": _PLACEHOLDER_KEY, "DEEPSEEK_BASE_URL": "https://api.deepseek.com/v1",
                         "DEEPSEEK_MODEL": "deepseek-chat"}},
    "openrouter": {"model_id": "openai/gpt-4o-mini", "endpoint": "openrouter",
                   "env": {"OPENROUTER_API_KEY": _PLACEHOLDER_KEY, "OPENROUTER_BASE_URL": "https://openrouter.ai/api/v1",
                           "OPENROUTER_MODEL": "openai/gpt-4o-mini"}},
}


@dataclass(frozen=True)
class C6Scenario:
    name: str
    description: str
    source: str  # the baseline test (tests/test_attempts.py unless stated) the response sequence comes from
    category: str  # "a" | "b"
    provider: str  # "deepseek" | "openrouter": the baseline shorthand and its endpoint entry
    steps: tuple[Mapping[str, Any], ...]
    expect_xd: tuple[str, ...] = ()
    attack: str | None = None
    injection_task: str | None = None
    expect_status: str = "complete"
    expect_old_written: bool = True

    @property
    def all_xd(self) -> tuple[str, ...]:
        """``expect_xd`` plus the D.7.3 entry wherever the baseline writes a transcript: every live transcript of
        ``579a908`` carries ``meta.n_attempts`` and ``meta.capture``, which the AER expresses as attempt scopes and the
        seal's accounting verdict (J.3.4: ``meta.capture.complete`` -> the capture verdict, D.7.3). Also implied:
        the benign security constant (D.10.5) for every benign cell with a transcript, and the generator's
        bookkeeping meta the live view cannot render (C.15.3) for every C6(a) scenario, which compares the views."""
        implied: tuple[str, ...] = ()
        if self.expect_old_written:
            implied += (XD_D73,)
            if self.attack is None:
                implied += (XD_BENIGN_SECURITY,)
            if self.category == "a":
                implied += (XD_GENERATOR_META,)
        return tuple(self.expect_xd) + implied

    @property
    def model_id(self) -> str:
        return str(_PROVIDERS[self.provider]["model_id"])

    @property
    def pipeline_name(self) -> str:
        """``generate._make_pipeline``: ``f"{model}/{model_id}+prov"``."""
        return f"{self.provider}/{self.model_id}+prov"

    def cell(self) -> dict[str, Any]:
        attacked = self.attack is not None
        return {
            "cell_key": f"{SUITE}/{USER_TASK}/{self.attack or 'none'}/{self.injection_task or 'none'}",
            "suite": SUITE, "user_task_id": USER_TASK, "injection_task_id": self.injection_task, "attack": self.attack,
            "defence": None, "kind": "attacked" if attacked else "user_task",
            "attack_params": {"model_display_name_preset": PRESET} if attacked else {},
        }

    def agent(self) -> dict[str, Any]:
        return {"model_requested": self.model_id, "provider": "openai_compatible",
                "endpoint": _PROVIDERS[self.provider]["endpoint"], "api_key_env": None, "params": {},
                "llm_element": "gateway_compat", "transport": "scripted", "script": "script.json", "base_url": None}

    def backend_config(self) -> dict[str, Any]:
        return {"pipeline_name": self.pipeline_name}

    def old(self) -> dict[str, Any]:
        return {"model": self.provider, "env": dict(_PROVIDERS[self.provider]["env"]),
                "kind": "injection" if self.attack is not None else "benign", "suite": SUITE, "user_task": USER_TASK,
                "injection_task": self.injection_task, "attack": self.attack}


def _call(name: str = "get_most_recent_transactions", args: Mapping[str, Any] | None = None,
          call_id: str = "call_1") -> dict[str, Any]:
    return {"name": name, "args": dict({"n": 5} if args is None else args), "id": call_id}


def _tool(*calls: Mapping[str, Any], **extra: Any) -> dict[str, Any]:
    return {"reply": "tool_calls", "calls": [dict(c) for c in (calls or (_call(),))], **extra}


def _text(content: str = "You spent 1050.", **extra: Any) -> dict[str, Any]:
    return {"reply": "text", "content": content, **extra}


_SEND = {"recipient": "US133000000121212121212", "amount": 7.5, "subject": "x", "date": "2022-03-01"}
_DETAILS = [{"type": "reasoning.encrypted", "data": "pass-1 signature"}]
_PROVIDER_REPLY = {"raw": {"status": 200, "json": {
    "id": None, "object": "chat.completion", "created": 0, "model": None, "system_fingerprint": "fp_abc",
    "provider": "DeepInfra",
    "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "You spent 1050."}}],
    "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}}}}

C6_SCENARIOS: dict[str, C6Scenario] = {s.name: s for s in [
    # ---------------------------------------------------------------- C6(a): single pass, no retry, no gate failure
    C6Scenario("single_pass", "one tool call, one answer, one pass",
               "test_a_single_pass_run_records_one_attempt_and_no_discarded_key", "a", "deepseek",
               (_tool(), _text())),
    C6Scenario("no_usage", "a provider that reports no usage (DeepSeek-style)",
               "test_a_provider_that_reports_no_usage_is_not_refused_as_an_incomplete_capture", "a", "deepseek",
               (_tool(usage=None), _text(usage=None))),
    C6Scenario("partial_usage", "usage missing on the first call only",
               "test_usage_missing_on_some_calls_does_not_fake_an_incomplete_capture", "a", "deepseek",
               (_tool(usage=None), _text())),
    C6Scenario("provider_fields", "OpenRouter reply naming its upstream provider and a fingerprint",
               "test_the_response_the_provider_reports_is_recorded", "a", "openrouter",
               (_tool(), _PROVIDER_REPLY)),
    C6Scenario("reasoning_single_pass", "OpenRouter reasoning text and reasoning_details passed back within the pass",
               "test_a_rerun_pass_is_kept_and_its_logs_do_not_leak_into_the_next (single-pass variant)", "a",
               "openrouter",
               (_tool(reasoning="think", reasoning_details=_DETAILS), _text(reasoning="answer"))),
    C6Scenario("tool_errors", "an unknown tool, an argument-validation error and a tool that raises in one turn",
               "agentprov_backend.testing.scenarios: tool_errors (no test_attempts.py counterpart)", "a", "deepseek",
               (_tool(_call("no_such_tool", {}, "call_1"), _call("get_most_recent_transactions", {"n": "many"}, "call_2"),
                      _call("update_scheduled_transaction", {"id": 999, "amount": 1.0}, "call_3")),
                _text("I could not complete the request."))),
    # ---------------------------------------------------------------- C6(b): deviation scenarios
    C6Scenario("rerun_two_passes", "an empty final reply makes AgentDojo re-run; the provider reuses call_1",
               "test_a_rerun_pass_is_kept_and_its_logs_do_not_leak_into_the_next", "b", "openrouter",
               (_tool(reasoning="p1 think", reasoning_details=_DETAILS), {"reply": "reasoning", "content": None, "reasoning": "p1 empty"},
                _tool(reasoning="p2 think"), _text(reasoning="p2 answer"))),
    C6Scenario("rerun_env_change", "pass 1 pays and goes silent; pass 2 only reads",
               "test_the_environment_a_pass_changes_is_recorded_not_only_replayable", "b", "openrouter",
               (_tool(_call("send_money", _SEND)), {"reply": "null"}, _tool(_call(call_id="call_2")), _text())),
    C6Scenario("refusal_rerun", "two refusals (content null) re-run the pipeline; the third pass answers",
               "test_a_refusal_is_recorded_on_its_turn_in_every_pass", "b", "deepseek",
               ({"reply": "refusal", "refusal": "I can't help with that"}, {"reply": "refusal", "refusal": "Still no"},
                _text())),
    C6Scenario("malformed_args_resample", "malformed tool-call JSON is re-asked at once by the port",
               "test_malformed_tool_call_arguments_are_retried_and_recorded_not_fatal", "b", "deepseek",
               ({"fail": "malformed_args", "raw": "{\"n\": 5", "id": "call_1"}, _tool(), _text()),
               expect_xd=("XD-C6-F02-discarded-model-calls",)),
    C6Scenario("upstream_failures_retried", "no choices, then finish_reason=error, then the real replies",
               "test_provider_failures_are_retried_not_taken_as_the_reply (whole task)", "b", "openrouter",
               ({"fail": "no_choices"}, {"fail": "finish_error"}, _tool(), _text()),
               expect_xd=("XD-C6-F02-discarded-model-calls",)),
    C6Scenario("server_5xx_retried", "four 5xx outlast agentdojo's three attempts; the port's outer loop retries",
               "test_a_provider_5xx_is_retried_but_a_4xx_is_not (5xx half)", "b", "deepseek",
               ({"fail": "http", "status": 503}, {"fail": "http", "status": 502}, {"fail": "http", "status": 503},
                {"fail": "http", "status": 500}, _tool(), _text()),
               expect_xd=("XD-C6-F02-discarded-model-calls",)),
    C6Scenario("http_400_refused", "a 400 is not retried (one wire attempt) and fails the cell",
               "test_a_provider_5xx_is_retried_but_a_4xx_is_not (4xx half; one attempt, D.10.10 item 18)", "b",
               "deepseek", ({"fail": "http", "status": 400, "code": "invalid_request"},),
               expect_xd=("XD-C6-F02-discarded-model-calls", "XD-C6-F05-failed-cell-kept"), expect_status="errored", expect_old_written=False),
    C6Scenario("injection_important_instructions", "important_instructions x injection_task_0 with the v2.3 display name",
               "generate._run_one_injection (MODEL_NAMES registration, generate.py:299-302)", "b", "deepseek",
               (_tool(), _text()), expect_xd=("XD-C6-F13-display-name-preset",),
               attack="important_instructions", injection_task="injection_task_0"),
]}


def wire_responses(sc: C6Scenario) -> list[dict[str, Any]]:
    """Per step, what the scripted server returns: ``{status, headers, body_b64}`` or ``{connect_error}``."""
    out: list[dict[str, Any]] = []
    for n, raw in enumerate(sc.steps):
        step = step_from_dict(raw)
        if step.raise_connect is not None:
            out.append({"connect_error": step.raise_connect})
            continue
        status, headers, content = render_response(step, n, model=sc.model_id)
        out.append({"status": status, "headers": headers, "body_b64": base64.b64encode(content).decode("ascii")})
    return out


def bundle(sc: C6Scenario) -> dict[str, Any]:
    """The scenario file both sides read (``<work>/<name>/scenario.json``)."""
    return {
        "format": "agentprov-c6-scenario/1",
        "name": sc.name,
        "description": sc.description,
        "source": sc.source,
        "category": sc.category,
        "expect_xd": list(sc.all_xd),
        "expect_status": sc.expect_status,
        "expect_old_written": sc.expect_old_written,
        "benchmark_version": BENCHMARK_VERSION,
        "steps": [dict(s) for s in sc.steps],
        "wire": wire_responses(sc),
        "old": sc.old(),
        "new": {"cell": sc.cell(), "agent": sc.agent(), "backend_config": sc.backend_config()},
    }
