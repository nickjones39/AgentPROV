"""Helpers for the ``agentdojo.capture`` tests (docs/architecture C.13, D.10.4, K.8.5; phase 8).

* :class:`Session` writes synthetic ``capture/0.1`` logs the way ``agentprov_capture.log.CaptureLog`` does (JCS lines,
  ``prev`` chain, ``session.end`` with ``n_events``), with content-addressed blobs. :func:`c13_8_session` rebuilds the
  C.13.8 vector exactly (the events and blobs of ``docs/architecture/examples/C/gen_sem_capture.py``).
* :func:`map_session` plans a staged session with the reader, maps it with the registered mapper through the runner's
  ``map_unit`` and seals it; :class:`MappedSession` validates it in release mode against a store holding the session's
  objects.

All content here is synthetic (no third-party text).
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import rfc8785

from agentprov.adapters.agentdojo.capture_mapper import AgentDojoCaptureMapper
from agentprov.adapters.agentdojo.capture_reader import CaptureLogReader, SessionObject
from agentprov.adapters.profiles import SourceProfile, load_profile
from agentprov.adapters.runner import MapOutcome, aer_bytes, map_unit
from agentprov.adapters.types import Origin
from agentprov.aer.rules import RuleRegistry
from agentprov.aer.validate import AerValidator, ValidationReport
from agentprov.aer.writer import SealInfo

REPO = Path(__file__).resolve().parents[3]
VECTOR = REPO / "docs" / "architecture" / "examples" / "C" / "synthetic.capture.jsonl"
VECTOR_SHA256 = "0e22300b8729440fea35f5d8271d82ea0916431493cd6ec315e4d0d045990add"
VECTOR_HEAD = "c6c44c6c4b0fe31667b6c58aa8dc31e26f5c2aaf89cb3aa3c354e2d7d5442437"
SESSION = "019a0f3c-7b2e-7c41-9a55-3e1f2d0c4b8a"
SESSION_B = "019a0f3c-7b2e-7c41-9a55-3e1f2d0c4b8b"


def jcs(obj: object) -> bytes:
    return rfc8785.dumps(obj)


# ------------------------------------------------------------------------------------------------ session writer
class Session:
    """A synthetic capture session: events, blobs and the hash chain (C.13.2), as ``CaptureLog`` writes them."""

    def __init__(self, session: str = SESSION) -> None:
        self.session = session
        self.events: list[dict[str, Any]] = []
        self.blobs: dict[str, bytes] = {}
        self.native: bytes | None = None

    def blob(self, obj: object, media: str = "application/json") -> dict[str, Any]:
        data = obj if isinstance(obj, bytes) else jcs(obj)
        digest = hashlib.sha256(data).hexdigest()
        self.blobs[digest] = data
        return {"$blob": "sha256:" + digest, "bytes": len(data), "media": media}

    def emit(self, type_: str, data: dict[str, Any], *, pass_: int | None = None, actor: str | None = None) -> int:
        self.events.append({"type": type_, "pass": pass_, "actor": actor, "data": data})
        return len(self.events) - 1

    def close(self, status: str = "complete", appended_by: str = "worker") -> None:
        self.emit("session.end", {"status": status, "appended_by": appended_by})

    def lines(self) -> list[bytes]:
        out: list[bytes] = []
        prev = None
        for seq, spec in enumerate(self.events):
            data = copy.deepcopy(spec["data"])
            if spec["type"] == "session.end":
                data["n_events"] = seq + 1
            minute, second = divmod(seq, 60)
            event = {"seq": seq, "type": spec["type"], "ts": f"2026-10-07T12:{minute:02d}:{second:02d}.000000Z",
                     "mono_ns": seq * 1_000_000, "pass": spec["pass"], "actor": spec["actor"], "prev": prev, "data": data}
            line = jcs(event) + b"\n"
            out.append(line)
            prev = hashlib.sha256(line).hexdigest()
        return out

    def log_bytes(self) -> bytes:
        return b"".join(self.lines())

    def set_native(self, doc: Mapping[str, Any]) -> None:
        """The native TraceLogger JSON (written as ``TraceLogger.save`` writes it) and its ``native.log`` event."""
        self.native = json.dumps(doc, indent=4).encode("utf-8")
        self.emit("native.log", {"path": f"raw/capture/{self.session}.native.json",
                                 "sha256": hashlib.sha256(self.native).hexdigest(), "bytes": len(self.native)})


# ------------------------------------------------------------------------------------------------ the C.13.8 vector
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
CONFIG = {"agent": {"model_requested": "scripted-fake", "provider": "openai_compatible", "endpoint": "fake",
                    "api_key_env": None, "params": {"temperature": 0.0}, "llm_element": "native",
                    "transport": "scripted", "script": "two_turn_balance"},
          "backend": {"id": "agentdojo", "version": "0.1.0"},
          "plan": {"cells": ["banking/user_task_0/none/none"]}}
ENV_DIGEST = hashlib.sha256(b"synthetic environment state").hexdigest()
TOOLS = [{"type": "function", "function": {"name": "get_balance", "parameters": {"type": "object", "properties": {}}}}]


def start_data(session: str = SESSION, *, cell: Mapping[str, Any] | None = None, attempt: int = 0) -> dict[str, Any]:
    return {"capture": "0.1", "session": session, "ex": "ex_" + session, "attempt": attempt,
            "cell": dict(cell or {"benchmark": "agentdojo", "suite": "banking", "task_id": "user_task_0", "attack_id": None,
                                  "attack_target_id": None, "defense_id": None, "attack_params": {}}),
            "writer": {"dist": "agentprov-capture", "version": "0.1.0"}, "backend": {"id": "agentdojo", "version": "0.1.0"},
            "runtime": {"python": "3.12.11", "platform": "synthetic",
                        "lock_sha256": hashlib.sha256(b"synthetic uv.lock").hexdigest()},
            "actors": {"agent": {"kind": "llm_agent", "model": {"requested": "scripted-fake"}},
                       "env": {"kind": "tool_runtime", "name": "agentdojo.FunctionsRuntime"}},
            "config_sha256": hashlib.sha256(jcs(CONFIG)).hexdigest()}


IDENTITY = {"benchmark": {"name": "agentdojo", "dist": "agentdojo", "dist_version": "0.1.35", "suite_set": "v1.2.2"},
            "harness": {"dist": "agentprov-backend", "version": "0.1.0"},
            "agent": {"model_requested": "scripted-fake", "provider": "openai_compatible", "endpoint_host": "fake.invalid",
                      "sdk": {"name": "agentprov_backend.testing.ScriptedTransport", "version": "0.1.0"}}}
ENDPOINT = {"host": "fake.invalid", "path": "/v1/chat/completions"}
PARAMS = {"configured": {"temperature": 0.0}, "transmitted": {}}


def text(s: str) -> list[dict[str, Any]]:
    return [{"type": "text", "content": s}]


def call(function: str, args: dict[str, Any], cid: str) -> dict[str, Any]:
    return {"function": function, "args": args, "id": cid, "placeholder_args": None}


def response(rid: str, *, content: str | None = None, calls: Sequence[Mapping[str, Any]] = (),
             finish: str = "stop", usage: tuple[int, int] = (10, 5)) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if calls:
        message["tool_calls"] = [{"id": c["id"], "type": "function",
                                  "function": {"name": c["function"], "arguments": json.dumps(c["args"])}} for c in calls]
    return {"id": rid, "model": "scripted-fake", "choices": [{"index": 0, "finish_reason": finish, "message": message}],
            "usage": {"prompt_tokens": usage[0], "completion_tokens": usage[1], "total_tokens": sum(usage)}}


def c13_8_session() -> Session:
    """The C.13.8 synthetic vector, event for event and blob for blob (gen_sem_capture.py)."""
    s = Session(SESSION)
    req0 = {"model": "scripted-fake", "messages": [{"role": "system", "content": "SYS"}, {"role": "user", "content": "Q"}],
            "tools": TOOLS}
    resp0 = {"id": "fake-0", "model": "scripted-fake", "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {
        "role": "assistant", "content": None,
        "tool_calls": [{"id": "call_0", "type": "function", "function": {"name": "get_balance", "arguments": "{}"}}]}}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 5, "total_tokens": 17}}
    req1 = {"model": "scripted-fake", "messages": req0["messages"] + [resp0["choices"][0]["message"],
            {"role": "tool", "tool_call_id": "call_0", "content": "1810.0"}], "tools": TOOLS}
    resp1 = {"id": "fake-1", "model": "scripted-fake", "choices": [{"index": 0, "finish_reason": "stop", "message": {
        "role": "assistant", "content": "Your balance is 1810.0."}}],
        "usage": {"prompt_tokens": 20, "completion_tokens": 7, "total_tokens": 27}}
    native = [{"role": "system", "content": text("SYS")},
              {"role": "user", "content": text("Q")},
              {"role": "assistant", "content": None, "tool_calls": [call("get_balance", {}, "call_0")]},
              {"role": "tool", "content": text("1810.0"), "tool_call_id": "call_0",
               "tool_call": call("get_balance", {}, "call_0"), "error": None},
              {"role": "assistant", "content": text("Your balance is 1810.0."), "tool_calls": None}]
    s.emit("session.start", start_data())
    s.emit("instrumentation", {"items": copy.deepcopy(INSTRUMENTATION)})
    s.emit("identity", copy.deepcopy(IDENTITY))
    s.emit("pass.start", {"env": {"sha256": ENV_DIGEST, "canon": "jcs-rfc8785"}}, pass_=0)
    s.emit("llm.request", {"call": "c0", "role": "agent", "attempt": 0, "endpoint": ENDPOINT, "params": PARAMS,
                           "input_at": [0, 1], "n_messages": 2, "request": s.blob(req0)}, pass_=0, actor="agent")
    s.emit("llm.response", {"call": "c0", "status": "kept", "response": s.blob(resp0), "finish_reason": "tool_calls",
                            "served_model": "scripted-fake", "response_id": "fake-0",
                            "usage": {"input_tokens": 12, "output_tokens": 5, "total_tokens": 17}}, pass_=0, actor="agent")
    s.emit("tool.dispatch", {"occ": "o0", "at": {"message": 2, "call": 0}, "provider_call_id": "call_0",
                             "name": "get_balance", "args": {}, "args_raw": "{}"}, pass_=0, actor="env")
    s.emit("tool.result", {"occ": "o0", "status": "ok", "args_effective": {}, "returned": "1810.0", "rendered": "1810.0",
                           "model_visible": "1810.0", "error": None}, pass_=0, actor="env")
    s.emit("llm.request", {"call": "c1", "role": "agent", "attempt": 0, "endpoint": ENDPOINT, "params": PARAMS,
                           "input_at": [0, 1, 2, 3], "n_messages": 4, "request": s.blob(req1)}, pass_=0, actor="agent")
    s.emit("llm.response", {"call": "c1", "status": "kept", "response": s.blob(resp1), "finish_reason": "stop",
                            "served_model": "scripted-fake", "response_id": "fake-1",
                            "usage": {"input_tokens": 20, "output_tokens": 7, "total_tokens": 27}}, pass_=0, actor="agent")
    s.emit("pass.end", {"aborted": False, "messages": s.blob(native),
                        "env": {"sha256": ENV_DIGEST, "canon": "jcs-rfc8785", "changed": False}}, pass_=0)
    s.emit("outcome", {"judgements": [{"name": "utility", "value": True, "origin": "checker"}]})
    s.close("complete")
    return s


def native_log(messages: Sequence[Any], *, suite: str = "banking", task: str = "user_task_0", attack: str | None = None,
               target: str | None = None, injections: Mapping[str, Any] | None = None, utility: bool = True,
               security: bool = True, error: str | None = None) -> dict[str, Any]:
    """A ``v1.k14`` TraceLogger record of the same cell (the stock 0.1.35 key set and order)."""
    return {"suite_name": suite, "pipeline_name": "scripted-fake", "user_task_id": task, "injection_task_id": target,
            "attack_type": attack, "injections": dict(injections or {}), "messages": list(messages), "error": error,
            "utility": utility, "security": security, "duration": 1.25, "agentdojo_package_version": "0.1.35",
            "benchmark_version": "v1.2.2", "evaluation_timestamp": "2026-10-07 14:00:12"}


# ------------------------------------------------------------------------------------------------ mapping
class DictStore:
    """A raw store over a dict of objects by digest (the AER validator's store protocol)."""

    def __init__(self, objects: Mapping[str, bytes]) -> None:
        self.objects = dict(objects)

    def has(self, sha256: str) -> bool:
        return sha256 in self.objects

    def size(self, sha256: str) -> int:
        return len(self.objects[sha256])

    def read_bytes(self, sha256: str) -> bytes:
        return self.objects[sha256]


@dataclass
class MappedSession:
    log: bytes
    objects: dict[str, bytes]
    outcome: MapOutcome
    data: bytes
    info: SealInfo
    profile: SourceProfile
    register: list[dict[str, str]] = field(default_factory=list)

    @property
    def records(self) -> list[dict[str, Any]]:
        return [json.loads(line) for line in self.data.splitlines()]

    @property
    def header(self) -> dict[str, Any]:
        return self.records[0]

    def get(self, rid: str) -> dict[str, Any]:
        return next(r for r in self.records if r.get("id") == rid)

    def of_kind(self, kind: str) -> list[dict[str, Any]]:
        return [r for r in self.records if r.get("k") == kind]

    @property
    def codes(self) -> list[str]:
        return [i["code"] for i in self.info.issues]

    def issues(self, code: str) -> list[dict[str, Any]]:
        return [i for i in self.info.issues if i["code"] == code]

    def checks(self, check_id: str) -> list[dict[str, Any]]:
        return [dict(c) for c in self.info.accounting.checks if c["id"] == check_id]

    def validate(self) -> ValidationReport:
        validator = AerValidator(store=DictStore(self.objects), catalogues=RuleRegistry.default(), mode="release",
                                 profile_digests={(self.profile.id, self.profile.version): self.profile.sha256})
        for line in self.data.splitlines(keepends=True):
            validator.feed(line)
        return validator.finish()


def session_objects(log: bytes, blobs: Mapping[str, bytes], native: bytes | None, session: str) -> list[SessionObject]:
    origin = Origin.capture(session)
    objects = [SessionObject(f"raw/capture/{session}.capture.jsonl", hashlib.sha256(log).hexdigest(), len(log), origin)]
    for digest, data in sorted(blobs.items()):
        objects.append(SessionObject(f"raw/blobs/sha256/{digest[:2]}/{digest}", digest, len(data), origin))
    if native is not None:
        objects.append(SessionObject(f"raw/capture/{session}.native.json", hashlib.sha256(native).hexdigest(), len(native),
                                     origin))
    return objects


def map_session(log: bytes, blobs: Mapping[str, bytes] | None = None, native: bytes | None = None, *,
                session: str = SESSION, profile_id: str = "agentdojo-live") -> MappedSession:
    """Plan, map and seal one staged session (the runner's container path: ``reader.plan`` then ``map_unit``)."""
    profile = load_profile(profile_id)
    blobs = dict(blobs or {})
    objects = {hashlib.sha256(log).hexdigest(): log, **blobs}
    if native is not None:
        objects[hashlib.sha256(native).hexdigest()] = native
    plan = CaptureLogReader().plan(session_objects(log, blobs, native, session), objects.__getitem__, profile)
    assert len(plan.units) == 1, plan.register
    outcome = map_unit(plan.units[0], AgentDojoCaptureMapper(), profile, auxiliary=plan.auxiliary)
    data, info = aer_bytes(outcome)
    return MappedSession(log, objects, outcome, data, info, profile, plan.register)


def map_built(s: Session, **kwargs: Any) -> MappedSession:
    return map_session(s.log_bytes(), s.blobs, s.native, session=s.session, **kwargs)


# ------------------------------------------------------------------------------------------------ staged sessions
FIXTURES = REPO / "tests" / "fixtures" / "capture"
LIVE_ENV = "AGENTPROV_LIVE_ARTEFACTS"
#: Fixture directories of a further backend (``tests/fixtures/capture/<backend>/<scenario>/session``); their sessions
#: are mapped with the profile their ``session.start.backend.id`` selects (D.11.9). ``anthropic``: the provider-anthropic
#: sessions of the AgentDojo backend (D-656), in the same generic live gates.
BACKEND_FIXTURE_DIRS = ("anthropic", "autodojo")


def _staging_dir(path: Path) -> Path | None:
    for candidate in (path, path / "session"):
        if (candidate / "raw" / "capture").is_dir():
            return candidate
    return None


def live_sessions() -> list[tuple[str, Path, bool]]:
    """``(id, staging directory, produced by a backend job)``: the frozen sessions ``tests/fixtures/capture/<scenario>/
    session/`` and, with ``AGENTPROV_LIVE_ARTEFACTS``, the staging directories below it (K.8.5)."""
    import os

    out: list[tuple[str, Path, bool]] = []
    if FIXTURES.is_dir():
        for scenario in sorted(p for p in FIXTURES.iterdir() if p.is_dir()):
            staged = _staging_dir(scenario)
            if staged is not None:
                out.append((scenario.name, staged, False))
            elif scenario.name in BACKEND_FIXTURE_DIRS:  # a backend's own fixtures, one level down (phase 9)
                for nested in sorted(p for p in scenario.iterdir() if p.is_dir()):
                    staged = _staging_dir(nested)
                    if staged is not None:
                        out.append((f"{scenario.name}-{nested.name}", staged, False))
    env = os.environ.get(LIVE_ENV)
    if env and Path(env).is_dir():
        for path in sorted(p for p in Path(env).iterdir() if p.is_dir()):
            staged = _staging_dir(path)
            if staged is not None:
                out.append((f"live-{path.name}", staged, True))
    return out


def map_staged_session(directory: Path, *, profile_id: str | None = None,
                       origins: Mapping[str, Origin] | None = None) -> MappedSession:
    """Map a staging directory through :mod:`agentprov.adapters.runner.live` and seal it (the validation store holds the
    staged objects). Without ``profile_id`` the profile is the one the log's backend id selects."""
    from agentprov.adapters.runner.live import capture_profile_id, stage_objects
    from agentprov.adapters.runner.live import map_session as map_staged

    members, read, _rejected = stage_objects(directory)
    objects = {m.sha256: read(m.sha256) for m in members}
    log = next(objects[m.sha256] for m in members if m.label.endswith(".capture.jsonl"))
    profile_id = profile_id or capture_profile_id(log)
    outcome, _unit, register = map_staged(directory, profile_id=profile_id, origins=origins)
    assert outcome is not None, register
    data, info = aer_bytes(outcome)
    return MappedSession(log, objects, outcome, data, info, load_profile(profile_id), register)
