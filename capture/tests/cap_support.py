"""Shared helpers: the C.13.8 synthetic session replayed through ``CaptureLog`` (conventions of
``docs/architecture/examples/C/gen_sem_capture.py``), scripted clocks, and log builders."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import rfc8785

from agentprov_capture.log import CaptureLog

SESSION = "019a0f3c-7b2e-7c41-9a55-3e1f2d0c4b8a"
VECTOR_SHA256 = "0e22300b8729440fea35f5d8271d82ea0916431493cd6ec315e4d0d045990add"
VECTOR_HEAD = "c6c44c6c4b0fe31667b6c58aa8dc31e26f5c2aaf89cb3aa3c354e2d7d5442437"
VECTOR_PATH = Path(__file__).resolve().parents[2] / "docs" / "architecture" / "examples" / "C" / "synthetic.capture.jsonl"


def jcs(obj: Any) -> bytes:
    return rfc8785.dumps(obj)


def scripted_clock() -> Callable[[], datetime]:
    """Call n returns 2026-10-07T12:00:<n>.000000Z (the vector's timestamps)."""
    counter = iter(range(10_000))
    return lambda: datetime(2026, 10, 7, 12, 0, 0, tzinfo=UTC).replace(second=next(counter) % 60)


def scripted_mono() -> Callable[[], int]:
    """Call n returns n * 1_000_000 ns."""
    counter = iter(range(10_000))
    return lambda: next(counter) * 1_000_000


REQ0 = {
    "model": "scripted-fake",
    "messages": [{"role": "system", "content": "SYS"}, {"role": "user", "content": "Q"}],
    "tools": [{"type": "function", "function": {"name": "get_balance", "parameters": {"type": "object", "properties": {}}}}],
}
RESP0 = {
    "id": "fake-0",
    "model": "scripted-fake",
    "choices": [
        {
            "index": 0,
            "finish_reason": "tool_calls",
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": "call_0", "type": "function", "function": {"name": "get_balance", "arguments": "{}"}}],
            },
        }
    ],
    "usage": {"prompt_tokens": 12, "completion_tokens": 5, "total_tokens": 17},
}
REQ1 = {
    "model": "scripted-fake",
    "messages": REQ0["messages"] + [RESP0["choices"][0]["message"], {"role": "tool", "tool_call_id": "call_0", "content": "1810.0"}],
    "tools": REQ0["tools"],
}
RESP1 = {
    "id": "fake-1",
    "model": "scripted-fake",
    "choices": [
        {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "Your balance is 1810.0."}}
    ],
    "usage": {"prompt_tokens": 20, "completion_tokens": 7, "total_tokens": 27},
}
NATIVE = [
    {"role": "system", "content": [{"type": "text", "content": "SYS"}]},
    {"role": "user", "content": [{"type": "text", "content": "Q"}]},
    {"role": "assistant", "content": None, "tool_calls": [{"function": "get_balance", "args": {}, "id": "call_0", "placeholder_args": None}]},
    {
        "role": "tool",
        "content": [{"type": "text", "content": "1810.0"}],
        "tool_call_id": "call_0",
        "tool_call": {"function": "get_balance", "args": {}, "id": "call_0", "placeholder_args": None},
        "error": None,
    },
    {"role": "assistant", "content": [{"type": "text", "content": "Your balance is 1810.0."}], "tool_calls": None},
]

CELL = {
    "benchmark": "agentdojo",
    "suite": "banking",
    "task_id": "user_task_0",
    "attack_id": None,
    "attack_target_id": None,
    "defense_id": None,
    "attack_params": {},
}
CONFIG = {
    "agent": {
        "model_requested": "scripted-fake",
        "provider": "openai_compatible",
        "endpoint": "fake",
        "api_key_env": None,
        "params": {"temperature": 0.0},
        "llm_element": "native",
        "transport": "scripted",
        "script": "two_turn_balance",
    },
    "backend": {"id": "agentdojo", "version": "0.1.0"},
    "plan": {"cells": ["banking/user_task_0/none/none"]},
}
ENV_DIGEST = hashlib.sha256(b"synthetic environment state").hexdigest()
INSTRUMENTATION = [
    {"id": "agentdojo.pass_recorder_wrap@1", "kind": "behaviour_preserving", "recorded": "full"},
    {"id": "agentdojo.executor_mirror@1", "kind": "behaviour_preserving", "recorded": "full", "params": {"mirrors": "0.1.35"}},
    {"id": "agentdojo.recording_runtime_class@1", "kind": "behaviour_preserving", "recorded": "full"},
    {"id": "agentdojo.recording_transport@1", "kind": "behaviour_preserving", "recorded": "full"},
    {"id": "agentdojo.llm_span_brackets@1", "kind": "behaviour_preserving", "recorded": "full"},
    {"id": "agentdojo.temperature_not_transmitted@1", "kind": "harness_policy", "recorded": "full"},
    {"id": "agentdojo.env_dump_per_pass@1", "kind": "behaviour_preserving", "recorded": "full"},
    {"id": "agentdojo.transport_scripted@1", "kind": "test_only", "recorded": "full"},
]
ENDPOINT = {"host": "fake.invalid", "path": "/v1/chat/completions"}


def session_start_data(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "capture": "0.1",
        "session": SESSION,
        "ex": "ex_" + SESSION,
        "attempt": 0,
        "cell": CELL,
        "writer": {"dist": "agentprov-capture", "version": "0.1.0"},
        "backend": {"id": "agentdojo", "version": "0.1.0"},
        "runtime": {
            "python": "3.12.11",
            "platform": "synthetic",
            "lock_sha256": hashlib.sha256(b"synthetic uv.lock").hexdigest(),
        },
        "actors": {
            "agent": {"kind": "llm_agent", "model": {"requested": "scripted-fake"}},
            "env": {"kind": "tool_runtime", "name": "agentdojo.FunctionsRuntime"},
        },
        "config_sha256": hashlib.sha256(jcs(CONFIG)).hexdigest(),
    }
    data.update(overrides)
    return data


def new_log(tmp: Path, *, name: str = "session", redactor: Any = None, scripted: bool = True) -> CaptureLog:
    return CaptureLog(
        tmp / "raw" / "capture" / f"{name}.capture.jsonl",
        SESSION,
        blobs_dir=tmp / "raw" / "blobs",
        clock=scripted_clock() if scripted else None,
        mono_ns=scripted_mono() if scripted else None,
        redactor=redactor,
    )


def start(log: CaptureLog) -> None:
    """session.start + instrumentation (the first two events of every log)."""
    log.emit("session.start", session_start_data())
    log.emit("instrumentation", {"items": INSTRUMENTATION})


def replay_vector(log: CaptureLog) -> str:
    """Write the C.13.8 session through ``log`` and seal it ``complete``; returns the chain head."""
    log.emit("session.start", session_start_data())
    log.emit("instrumentation", {"items": INSTRUMENTATION})
    log.emit(
        "identity",
        {
            "benchmark": {"name": "agentdojo", "dist": "agentdojo", "dist_version": "0.1.35", "suite_set": "v1.2.2"},
            "harness": {"dist": "agentprov-backend", "version": "0.1.0"},
            "agent": {
                "model_requested": "scripted-fake",
                "provider": "openai_compatible",
                "endpoint_host": "fake.invalid",
                "sdk": {"name": "agentprov_backend.testing.ScriptedTransport", "version": "0.1.0"},
            },
        },
    )
    log.emit("pass.start", {"env": {"sha256": ENV_DIGEST, "canon": "jcs-rfc8785"}}, pass_=0)
    params = {"configured": {"temperature": 0.0}, "transmitted": {}}
    log.emit(
        "llm.request",
        {
            "call": "c0",
            "role": "agent",
            "attempt": 0,
            "endpoint": ENDPOINT,
            "params": params,
            "input_at": [0, 1],
            "n_messages": 2,
            "request": log.put_blob(jcs(REQ0), "application/json"),
        },
        pass_=0,
        actor="agent",
    )
    log.emit(
        "llm.response",
        {
            "call": "c0",
            "status": "kept",
            "response": log.put_blob(jcs(RESP0), "application/json"),
            "finish_reason": "tool_calls",
            "served_model": "scripted-fake",
            "response_id": "fake-0",
            "usage": {"input_tokens": 12, "output_tokens": 5, "total_tokens": 17},
        },
        pass_=0,
        actor="agent",
    )
    log.emit(
        "tool.dispatch",
        {"occ": "o0", "at": {"message": 2, "call": 0}, "provider_call_id": "call_0", "name": "get_balance", "args": {}, "args_raw": "{}"},
        pass_=0,
        actor="env",
    )
    log.emit(
        "tool.result",
        {"occ": "o0", "status": "ok", "args_effective": {}, "returned": "1810.0", "rendered": "1810.0", "model_visible": "1810.0", "error": None},
        pass_=0,
        actor="env",
    )
    log.emit(
        "llm.request",
        {
            "call": "c1",
            "role": "agent",
            "attempt": 0,
            "endpoint": ENDPOINT,
            "params": params,
            "input_at": [0, 1, 2, 3],
            "n_messages": 4,
            "request": log.put_blob(jcs(REQ1), "application/json"),
        },
        pass_=0,
        actor="agent",
    )
    log.emit(
        "llm.response",
        {
            "call": "c1",
            "status": "kept",
            "response": log.put_blob(jcs(RESP1), "application/json"),
            "finish_reason": "stop",
            "served_model": "scripted-fake",
            "response_id": "fake-1",
            "usage": {"input_tokens": 20, "output_tokens": 7, "total_tokens": 27},
        },
        pass_=0,
        actor="agent",
    )
    log.emit(
        "pass.end",
        {
            "aborted": False,
            "messages": log.put_blob(jcs(NATIVE), "application/json"),
            "env": {"sha256": ENV_DIGEST, "canon": "jcs-rfc8785", "changed": False},
        },
        pass_=0,
    )
    log.emit("outcome", {"judgements": [{"name": "utility", "value": True, "origin": "checker"}]})
    return log.close("complete")


def vector_lines() -> list[bytes]:
    return VECTOR_PATH.read_bytes().splitlines(keepends=True)
