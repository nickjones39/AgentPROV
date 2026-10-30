"""D.10.6 against the fork: its ``ToolsExecutor.query`` is AST-identical to agentdojo 0.1.35 (verify/autodojo.md #18;
here it is even source-identical), so ``MirrorToolsExecutor``'s guard passes, and the mirror equals the fork's stock
executor on deep-copied identical inputs for every suite the fork registers under v1.2.2 (AgentDyn and the ``_v2_*``
variants included), with and without a recording session (compared as JCS bytes)."""

from __future__ import annotations

import copy
import json
import random
import re

import pytest
import rfc8785
from agentdojo.agent_pipeline.llms.google_llm import EMPTY_FUNCTION_NAME
from agentdojo.agent_pipeline.tool_execution import ToolsExecutor, tool_result_to_str
from agentdojo.functions_runtime import FunctionCall, FunctionsRuntime, make_function
from agentdojo.task_suite.load_suites import get_suites
from agentdojo.types import ChatAssistantMessage, ChatUserMessage, text_content_block_from_string

from agentprov_backend import executor_mirror
from agentprov_backend.executor_mirror import MirrorToolsExecutor, guard, source_digests
from agentprov_backend.pass_recorder import dump_env
from agentprov_backend.runtime import RecordingFunctionsRuntime
from agentprov_backend.session import CaptureSession

SUITES = sorted(get_suites("v1.2.2"))


def echo_list(items: list[str]) -> list[str]:
    """Echo a list.

    :param items: the items.
    """
    return items


def explode(reason: str) -> str:
    """Always raise.

    :param reason: why.
    """
    raise ValueError(f"exploded: {reason}")


def needs_int(x: int) -> int:
    """Double an integer.

    :param x: the integer.
    """
    return 2 * x


EXTRA = [make_function(f) for f in (echo_list, explode, needs_int)]


def _jcs(value: object) -> bytes:
    from pydantic import BaseModel

    return rfc8785.dumps(json.loads(json.dumps(value, default=lambda o: o.model_dump() if isinstance(o, BaseModel) else o)))


def _ground_truth_calls(suite) -> list[FunctionCall]:
    env = suite.load_and_inject_default_environment({})
    calls: list[FunctionCall] = []
    for task in list(suite.user_tasks.values())[:6]:
        calls.extend(task.ground_truth(task.init_environment(env.model_copy(deep=True))))
    return calls


def _inputs(suite) -> dict[str, list[FunctionCall]]:
    gt = _ground_truth_calls(suite)
    assert gt, suite.name
    return {
        "valid": [FunctionCall(function=c.function, args=dict(c.args), id=f"call_{i}") for i, c in enumerate(gt[:4])],
        "empty_name": [FunctionCall(function=EMPTY_FUNCTION_NAME, args={}, id="call_e")],
        "unknown_tool": [FunctionCall(function="no_such_tool", args={"a": 1}, id="call_u")],
        "string_list": [FunctionCall(function="echo_list", args={"items": "['a', 'b']"}, id="call_l")],
        "raises": [FunctionCall(function="explode", args={"reason": "test"}, id="call_r")],
        "validation_error": [FunctionCall(function="needs_int", args={"x": "not an int"}, id="call_v")],
        "parallel": [FunctionCall(function=c.function, args=dict(c.args), id="dup") for c in gt[:3]],
        "id_none": [FunctionCall(function=c.function, args=dict(c.args), id=None) for c in gt[:2]],
    }


def _run(executor, suite, calls, runtime_cls=FunctionsRuntime):
    random.seed(0)  # the AgentDyn tools draw OTPs from `random` (shopping_client.py, github_client.py, ...)
    env = suite.load_and_inject_default_environment({})
    messages = [ChatUserMessage(role="user", content=[text_content_block_from_string("q")]),
                ChatAssistantMessage(role="assistant", content=None, tool_calls=copy.deepcopy(calls))]
    runtime = runtime_cls([*suite.tools, *EXTRA])
    _, _, env_out, out, _ = executor.query("q", runtime, env, messages, {})
    # dump_env: the AgentDyn shopping environment holds a callable after a checkout (see pass_recorder.dump_env)
    return _now_free(_jcs(out)), _now_free(_jcs(dump_env(env_out)))


#: AgentDyn tools stamp the emails they send with ``datetime.now()`` (and draw OTPs from ``random``, seeded above):
#: two stock runs differ there, so wall-clock times with microseconds are masked before comparing.
_NOW = re.compile(rb"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}\.\d{6}")


def _now_free(data: bytes) -> bytes:
    return _NOW.sub(b"<now>", data)


def _start(session: CaptureSession) -> None:
    session.start({
        "cell": {"benchmark": "agentdojo", "task_id": "t"}, "backend": {"id": "autodojo", "version": "0.1.0"},
        "runtime": {"python": "3.12", "platform": "test", "lock_sha256": "0" * 64},
        "actors": {"agent": {"kind": "llm_agent"}, "env": {"kind": "tool_runtime"}},
        "config_sha256": "0" * 64, "instrumentation": [], "identity": {
            "benchmark": {"name": "agentdojo", "dist": "agentdojo", "dist_version": "0.1.35"},
            "harness": {"dist": "agentprov-backend", "version": "0.1.0"},
            "agent": {"model_requested": "m", "provider": "p", "endpoint_host": "h", "sdk": {"name": "s", "version": "1"}}},
    })


def test_the_forks_executor_is_ast_identical_to_0_1_35():
    src_sha, ast_sha = source_digests(ToolsExecutor.query)
    assert ast_sha == executor_mirror.MIRRORED_AST_SHA256
    assert guard() == src_sha == executor_mirror.MIRRORED_SOURCE_SHA256


@pytest.mark.parametrize("suite_name", SUITES)
def test_mirror_equals_the_forks_stock_executor(suite_name, tmp_path):
    suite = get_suites("v1.2.2")[suite_name]
    for label, calls in _inputs(suite).items():
        stock = _run(ToolsExecutor(tool_result_to_str), suite, calls)
        assert _run(MirrorToolsExecutor(tool_result_to_str), suite, calls) == stock, (suite_name, label)
        session = CaptureSession(tmp_path / f"{suite_name}-{label}")
        _start(session)
        recorded = _run(MirrorToolsExecutor(tool_result_to_str, hooks=session), suite, calls,
                        RecordingFunctionsRuntime.bind(session))
        assert recorded == stock, (suite_name, label, "recording")
        session.close("complete")
