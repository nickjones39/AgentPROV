"""K.9.4 / K.8.2 / D.10.6: stock ``ToolsExecutor`` vs ``MirrorToolsExecutor`` on deep-copied identical inputs.

For every v1.2.2 suite the same inputs run through the stock executor and through the mirror (with and without a
recording session); the resulting message lists and post-environments must be equal as JCS bytes. Input classes:
valid calls (from the suite's own ground truths), an empty function name, an unknown tool, string-encoded list
arguments (in-place ``literal_eval``), a tool that raises, a pydantic validation error, parallel calls, ``id=None``,
and YAML-formatted structured output. A version assertion pins agentdojo 0.1.35, and the guard digests are checked.
"""

from __future__ import annotations

import copy
import importlib.metadata
import json

import pytest
import rfc8785
from agentdojo.agent_pipeline.llms.google_llm import EMPTY_FUNCTION_NAME
from agentdojo.agent_pipeline.tool_execution import ToolsExecutor, tool_result_to_str
from agentdojo.functions_runtime import FunctionCall, FunctionsRuntime, make_function
from agentdojo.task_suite.load_suites import get_suites
from agentdojo.types import ChatAssistantMessage, ChatUserMessage, text_content_block_from_string
from pydantic import BaseModel

from agentprov_backend import executor_mirror
from agentprov_backend.executor_mirror import MirrorToolsExecutor, guard, source_digests
from agentprov_backend.runtime import RecordingFunctionsRuntime
from agentprov_backend.session import CaptureSession

SUITES = sorted(get_suites("v1.2.2"))


class Item(BaseModel):
    name: str
    tags: list[str]
    weight: float


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


def structured(n: int) -> list[Item]:
    """Return structured items (YAML output).

    :param n: how many.
    """
    return [Item(name=f"item {i}", tags=["a", "b"], weight=i + 0.5) for i in range(n)]


EXTRA = [make_function(f) for f in (echo_list, explode, needs_int, structured)]


def _jcs(value: object) -> bytes:
    return rfc8785.dumps(json.loads(json.dumps(value, default=lambda o: o.model_dump() if isinstance(o, BaseModel) else o)))


def _ground_truth_calls(suite) -> list[FunctionCall]:
    env = suite.load_and_inject_default_environment({})
    calls: list[FunctionCall] = []
    for task in list(suite.user_tasks.values())[:6]:
        calls.extend(task.ground_truth(task.init_environment(env.model_copy(deep=True))))
    return calls


def _inputs(suite) -> dict[str, list[FunctionCall]]:
    gt = _ground_truth_calls(suite)
    assert len(gt) >= 3, suite.name
    first = suite.tools[0].name
    return {
        "valid": [FunctionCall(function=c.function, args=dict(c.args), id=f"call_{i}") for i, c in enumerate(gt[:4])],
        "empty_name": [FunctionCall(function=EMPTY_FUNCTION_NAME, args={}, id="call_e")],
        "unknown_tool": [FunctionCall(function="no_such_tool", args={"a": 1}, id="call_u")],
        "string_list": [FunctionCall(function="echo_list", args={"items": "['a', 'b']"}, id="call_l")],
        "raises": [FunctionCall(function="explode", args={"reason": "test"}, id="call_r")],
        "validation_error": [FunctionCall(function="needs_int", args={"x": "not an int"}, id="call_v"),
                             FunctionCall(function=first, args={"unexpected": object.__name__}, id="call_v2")],
        "parallel": [FunctionCall(function=c.function, args=dict(c.args), id="dup") for c in gt[:3]]
        + [FunctionCall(function="echo_list", args={"items": "['x']"}, id="dup")],
        "id_none": [FunctionCall(function=c.function, args=dict(c.args), id=None) for c in gt[:2]],
        "yaml_output": [FunctionCall(function="structured", args={"n": 3}, id="call_y")],
    }


def _messages(calls: list[FunctionCall]) -> list:
    return [ChatUserMessage(role="user", content=[text_content_block_from_string("q")]),
            ChatAssistantMessage(role="assistant", content=None, tool_calls=calls)]


def _run(executor, suite, calls, runtime_cls=FunctionsRuntime):
    env = suite.load_and_inject_default_environment({})
    messages = _messages(copy.deepcopy(calls))
    runtime = runtime_cls([*suite.tools, *EXTRA])
    _, _, env_out, out, _ = executor.query("q", runtime, env, messages, {})
    return _jcs(out), _jcs(env_out.model_dump(mode="json")), _jcs(messages)


def test_agentdojo_version_is_the_mirrored_one():
    assert importlib.metadata.version("agentdojo") == executor_mirror.MIRRORS == "0.1.35"
    assert guard() == executor_mirror.MIRRORED_SOURCE_SHA256


@pytest.mark.parametrize("suite_name", SUITES)
def test_mirror_equals_stock_executor_for_every_input_class(suite_name, tmp_path):
    suite = get_suites("v1.2.2")[suite_name]
    for label, calls in _inputs(suite).items():
        stock = _run(ToolsExecutor(tool_result_to_str), suite, calls)
        bare = _run(MirrorToolsExecutor(tool_result_to_str), suite, calls)
        assert bare == stock, (suite_name, label, "mirror without hooks")
        session = CaptureSession(tmp_path / f"{suite_name}-{label}")
        _start(session)
        recorded = _run(MirrorToolsExecutor(tool_result_to_str, hooks=session), suite, calls,
                        RecordingFunctionsRuntime.bind(session))
        assert recorded == stock, (suite_name, label, "mirror with a session and the recording runtime")
        session.close("complete")


def _start(session: CaptureSession) -> None:
    session.start({
        "cell": {"benchmark": "agentdojo", "task_id": "t"}, "backend": {"id": "agentdojo", "version": "0.1.0"},
        "runtime": {"python": "3.12", "platform": "test", "lock_sha256": "0" * 64},
        "actors": {"agent": {"kind": "llm_agent"}, "env": {"kind": "tool_runtime"}},
        "config_sha256": "0" * 64, "instrumentation": [], "identity": {
            "benchmark": {"name": "agentdojo", "dist": "agentdojo", "dist_version": "0.1.35"},
            "harness": {"dist": "agentprov-backend", "version": "0.1.0"},
            "agent": {"model_requested": "m", "provider": "p", "endpoint_host": "h", "sdk": {"name": "s", "version": "1"}}},
    })


def test_mirror_records_one_dispatch_and_result_per_occurrence(tmp_path):
    from support import read_events

    suite = get_suites("v1.2.2")["banking"]
    calls = _inputs(suite)["parallel"] + _inputs(suite)["raises"] + _inputs(suite)["unknown_tool"]
    session = CaptureSession(tmp_path / "s")
    _start(session)
    _run(MirrorToolsExecutor(tool_result_to_str, hooks=session), suite, calls, RecordingFunctionsRuntime.bind(session))
    session.close("complete")
    events = read_events(session.capture_path)
    dispatch = [e["data"] for e in events if e["type"] == "tool.dispatch"]
    results = [e["data"] for e in events if e["type"] == "tool.result"]
    assert [d["occ"] for d in dispatch] == [r["occ"] for r in results] == [f"o{i}" for i in range(len(calls))]
    assert [d["provider_call_id"] for d in dispatch][:4] == ["dup"] * 4     # provider id reuse: occ tells them apart
    assert [d["at"] for d in dispatch] == [{"message": 1, "call": i} for i in range(len(calls))]
    # the string-encoded list is recorded as requested, the effective arguments as validated
    (lst,) = [(d, r) for d, r in zip(dispatch, results, strict=True) if d["name"] == "echo_list"]
    assert lst[0]["args"] == {"items": "['x']"} and lst[1]["args_effective"] == {"items": ["x"]}
    raised = results[-2]
    assert raised["status"] == "error" and raised["exception"]["type"] == "ValueError"
    assert raised["model_visible"] == raised["error"] and raised["rendered"] == "" and "returned" not in raised
    unknown = results[-1]
    assert unknown["status"] == "invalid" and unknown["model_visible"] == "Invalid tool no_such_tool provided."


def test_the_guard_is_keyed_by_the_running_interpreter(monkeypatch):
    """D-292: the AST digest is interpreter-specific; the running interpreter (the backend's CPython 3.12) has one."""
    import sys

    key = executor_mirror.interpreter_key()
    assert key == f"{sys.implementation.name}-{sys.version_info[0]}.{sys.version_info[1]}"
    assert key in executor_mirror.MIRRORED_AST_SHA256_BY_INTERPRETER
    _, ast_sha = source_digests(ToolsExecutor.query)
    assert ast_sha == executor_mirror.expected_ast_sha256() == executor_mirror.MIRRORED_AST_SHA256_BY_INTERPRETER[key]


@pytest.mark.parametrize("key", ["cpython-3.13", "cpython-3.14", "pypy-3.12", "cpython-3.11"])
def test_an_interpreter_without_a_recorded_digest_is_refused_with_a_typed_error(monkeypatch, key):
    monkeypatch.setattr(executor_mirror, "interpreter_key", lambda: key)
    with pytest.raises(executor_mirror.MirrorUnverifiable) as exc:
        guard()
    assert isinstance(exc.value, executor_mirror.MirrorMismatch)
    assert exc.value.code == "backend.mirror.interpreter" and key in str(exc.value)
