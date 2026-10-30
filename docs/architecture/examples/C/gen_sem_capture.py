"""SEM 0.1 example over the v1 AER example, and a SYNTHETIC capture/0.1 test vector (scratch prototype).

r2 contract (regenerated 2026-10-08, RESOLUTIONS §5 step 10; SWEEP_r2 SW-C1, SW-C7): SEM profile
`{"id": "agentdojo.suites", "version": 1}`, integer catalogue versions, `role` values as arrays over EF E.7.1's
security roles, marker `status`; capture `session.start` with `writer`, `runtime` and `config_sha256`, merged
instrumentation items (D.10.7), an `identity` event, `input_at`/`n_messages` on `llm.request`, `tool.dispatch.args`,
and `session.end` with `appended_by` and no accounting. Run after gen_examples.py:

    uv run --no-project --with rfc8785==0.1.4 python gen_sem_capture.py
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import rfc8785

OUT = Path(__file__).parent


def jcs(o):
    return rfc8785.dumps(o)


def sealed(lines):
    body = b"".join(jcs(r) + b"\n" for r in lines)
    seal = {"k": "seal", "id": "seal", "n_records": len(lines) + 1, "records_sha256": hashlib.sha256(body).hexdigest()}
    return body + jcs(seal) + b"\n", seal["records_sha256"]


# ------------------------------------------------------------------ SEM
aer = (OUT / "adprov_v1_llama_injecagent.aer.jsonl").read_bytes()
recs = [json.loads(l) for l in aer.split(b"\n")[:-1]]
by = {r["id"]: r for r in recs}
hdr, seal = recs[0], recs[-1]
text = by["m3"]["parts"][0]["text"]
payload = by["fx0"]["content"]
start = text.index(payload)  # code points (Python str indices) = Unicode scalar values here
span = [start, start + len(payload)]
assert by["te0"]["name"] == "read_file" and by["te1"]["name"] == "update_scheduled_transaction" and by["te2"]["name"] == "send_money"
S = [
    {"k": "sem", "id": "sem", "sem": "0.1", "ex": hdr["ex"], "aer_digest": "sha256:" + seal["records_sha256"],
     "profile": {"id": "agentdojo.suites", "version": 1}, "rules": {"agentdojo": 1},
     "ns": {}, "canon": "jcs-rfc8785", "hash": "sha256"},
    {"k": "ann", "id": "a0", "target": "m3#0", "type": "integrity", "value": "untrusted", "ev": "I",
     "rule": ["agentdojo.integrity_external_content@1"], "premises": [{"id": "te0", "p": "/name"}]},
    {"k": "ann", "id": "a1", "target": "m3#0", "type": "channel", "value": "file", "ev": "I",
     "rule": ["agentdojo.channel_table@1"], "premises": [{"id": "te0", "p": "/name"}]},
    {"k": "ann", "id": "a2", "target": "m3#0", "at": "/text", "span": span, "type": "injection_marker",
     "value": {"fixture": "fx0", "status": "present", "normaliser": "agentdojo.yaml_norm@1"}, "ev": "D",
     "rule": ["agentdojo.injection_marker_yaml@1"],
     "premises": [{"id": "m3", "p": "/parts/0/text"}, {"id": "fx0", "p": "/content"}]},
    # roles: EF E.7.1 values (multi-class arrays); the baseline read/sink tables refined by the profile
    {"k": "ann", "id": "a3", "target": "te0", "type": "role", "value": ["content_source"], "ev": "I",
     "rule": ["agentdojo.read_tools@1"], "premises": [{"id": "te0", "p": "/name"}]},
    {"k": "ann", "id": "a4", "target": "te1", "type": "role", "value": ["write_sink"], "ev": "I",
     "rule": ["agentdojo.sink_tools@1"], "premises": [{"id": "te1", "p": "/name"}]},
    {"k": "ann", "id": "a5", "target": "te2", "type": "role", "value": ["send_sink"], "ev": "I",
     "rule": ["agentdojo.sink_tools@1"], "premises": [{"id": "te2", "p": "/name"}]},
    {"k": "ann", "id": "a6", "target": "j0", "type": "outcome", "value": {"claim": "user_task_solved", "holds": False},
     "ev": "D", "rule": ["agentdojo.utility_meaning@1"], "premises": [{"id": "j0", "p": "/value"}]},
    {"k": "ann", "id": "a7", "target": "j1", "type": "outcome", "value": {"claim": "attack_succeeded", "holds": True},
     "ev": "D", "rule": ["agentdojo.security_polarity@1"],
     "premises": [{"id": "j1", "p": "/value"}, {"id": "j1", "p": "/origin"}, {"id": "exec", "p": "/task/attack_id"}]},
]
data, dg = sealed(S)
(OUT / "adprov_v1_llama_injecagent.sem.jsonl").write_bytes(data)
print("SEM", len(S) + 1, "records; digest", dg, "span", span, "ex", hdr["ex"])

# ------------------------------------------------------------------ capture/0.1 (SYNTHETIC)
SESSION = "019a0f3c-7b2e-7c41-9a55-3e1f2d0c4b8a"   # synthetic UUIDv7 (illustration only)
blobs = {}


def blob(obj, media="application/json"):
    b = jcs(obj)
    h = hashlib.sha256(b).hexdigest()
    blobs[h] = b
    return {"$blob": "sha256:" + h, "bytes": len(b), "media": media}


req0 = {"model": "scripted-fake", "messages": [{"role": "system", "content": "SYS"}, {"role": "user", "content": "Q"}],
        "tools": [{"type": "function", "function": {"name": "get_balance", "parameters": {"type": "object", "properties": {}}}}]}
resp0 = {"id": "fake-0", "model": "scripted-fake", "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {
    "role": "assistant", "content": None,
    "tool_calls": [{"id": "call_0", "type": "function", "function": {"name": "get_balance", "arguments": "{}"}}]}}],
    "usage": {"prompt_tokens": 12, "completion_tokens": 5, "total_tokens": 17}}
req1 = {"model": "scripted-fake", "messages": req0["messages"] + [resp0["choices"][0]["message"],
        {"role": "tool", "tool_call_id": "call_0", "content": "1810.0"}], "tools": req0["tools"]}
resp1 = {"id": "fake-1", "model": "scripted-fake", "choices": [{"index": 0, "finish_reason": "stop", "message": {
    "role": "assistant", "content": "Your balance is 1810.0."}}],
    "usage": {"prompt_tokens": 20, "completion_tokens": 7, "total_tokens": 27}}
native = [{"role": "system", "content": [{"type": "text", "content": "SYS"}]},
          {"role": "user", "content": [{"type": "text", "content": "Q"}]},
          {"role": "assistant", "content": None, "tool_calls": [{"function": "get_balance", "args": {}, "id": "call_0", "placeholder_args": None}]},
          {"role": "tool", "content": [{"type": "text", "content": "1810.0"}], "tool_call_id": "call_0",
           "tool_call": {"function": "get_balance", "args": {}, "id": "call_0", "placeholder_args": None}, "error": None},
          {"role": "assistant", "content": [{"type": "text", "content": "Your balance is 1810.0."}], "tool_calls": None}]

EX = "ex_" + SESSION
CELL = {"benchmark": "agentdojo", "suite": "banking", "task_id": "user_task_0", "attack_id": None,
        "attack_target_id": None, "defense_id": None, "attack_params": {}}
# synthetic run configuration, expanded plan included, secrets excluded (D.10.2); its JCS digest is config_sha256
CONFIG = {"agent": {"model_requested": "scripted-fake", "provider": "openai_compatible", "endpoint": "fake",
                    "api_key_env": None, "params": {"temperature": 0.0}, "llm_element": "native",
                    "transport": "scripted", "script": "two_turn_balance"},
          "backend": {"id": "agentdojo", "version": "0.1.0"},
          "plan": {"cells": ["banking/user_task_0/none/none"]}}
ENV_DIGEST = hashlib.sha256(b"synthetic environment state").hexdigest()   # get_balance is read-only
INSTRUMENTATION = [   # D.10.7 items for a native-element session over the scripted test transport
    {"id": "agentdojo.pass_recorder_wrap@1", "kind": "behaviour_preserving", "recorded": "full"},
    {"id": "agentdojo.executor_mirror@1", "kind": "behaviour_preserving", "recorded": "full", "params": {"mirrors": "0.1.35"}},
    {"id": "agentdojo.recording_runtime_class@1", "kind": "behaviour_preserving", "recorded": "full"},
    {"id": "agentdojo.recording_transport@1", "kind": "behaviour_preserving", "recorded": "full"},
    {"id": "agentdojo.llm_span_brackets@1", "kind": "behaviour_preserving", "recorded": "full"},
    {"id": "agentdojo.temperature_not_transmitted@1", "kind": "harness_policy", "recorded": "full"},
    {"id": "agentdojo.env_dump_per_pass@1", "kind": "behaviour_preserving", "recorded": "full"},
    {"id": "agentdojo.transport_scripted@1", "kind": "test_only", "recorded": "full"},
]
events = [
    ("session.start", None, None, {"capture": "0.1", "session": SESSION, "ex": EX, "attempt": 0, "cell": CELL,
                                   "writer": {"dist": "agentprov-capture", "version": "0.1.0"},
                                   "backend": {"id": "agentdojo", "version": "0.1.0"},
                                   "runtime": {"python": "3.12.11", "platform": "synthetic",
                                               "lock_sha256": hashlib.sha256(b"synthetic uv.lock").hexdigest()},
                                   "actors": {"agent": {"kind": "llm_agent", "model": {"requested": "scripted-fake"}},
                                              "env": {"kind": "tool_runtime", "name": "agentdojo.FunctionsRuntime"}},
                                   "config_sha256": hashlib.sha256(jcs(CONFIG)).hexdigest()}),
    ("instrumentation", None, None, {"items": INSTRUMENTATION}),
    ("identity", None, None, {"benchmark": {"name": "agentdojo", "dist": "agentdojo", "dist_version": "0.1.35",
                                            "suite_set": "v1.2.2"},
                              "harness": {"dist": "agentprov-backend", "version": "0.1.0"},
                              "agent": {"model_requested": "scripted-fake", "provider": "openai_compatible",
                                        "endpoint_host": "fake.invalid",
                                        "sdk": {"name": "agentprov_backend.testing.ScriptedTransport", "version": "0.1.0"}}}),
    ("pass.start", 0, None, {"env": {"sha256": ENV_DIGEST, "canon": "jcs-rfc8785"}}),
    ("llm.request", 0, "agent", {"call": "c0", "role": "agent", "attempt": 0,
                                 "endpoint": {"host": "fake.invalid", "path": "/v1/chat/completions"},
                                 "params": {"configured": {"temperature": 0.0}, "transmitted": {}},
                                 "input_at": [0, 1], "n_messages": 2, "request": blob(req0)}),
    ("llm.response", 0, "agent", {"call": "c0", "status": "kept", "response": blob(resp0), "finish_reason": "tool_calls",
                                  "served_model": "scripted-fake", "response_id": "fake-0",
                                  "usage": {"input_tokens": 12, "output_tokens": 5, "total_tokens": 17}}),
    ("tool.dispatch", 0, "env", {"occ": "o0", "at": {"message": 2, "call": 0}, "provider_call_id": "call_0",
                                 "name": "get_balance", "args": {}, "args_raw": "{}"}),
    ("tool.result", 0, "env", {"occ": "o0", "status": "ok", "args_effective": {}, "returned": "1810.0",
                               "rendered": "1810.0", "model_visible": "1810.0", "error": None}),
    ("llm.request", 0, "agent", {"call": "c1", "role": "agent", "attempt": 0,
                                 "endpoint": {"host": "fake.invalid", "path": "/v1/chat/completions"},
                                 "params": {"configured": {"temperature": 0.0}, "transmitted": {}},
                                 "input_at": [0, 1, 2, 3], "n_messages": 4, "request": blob(req1)}),
    ("llm.response", 0, "agent", {"call": "c1", "status": "kept", "response": blob(resp1), "finish_reason": "stop",
                                  "served_model": "scripted-fake", "response_id": "fake-1",
                                  "usage": {"input_tokens": 20, "output_tokens": 7, "total_tokens": 27}}),
    ("pass.end", 0, None, {"aborted": False, "messages": blob(native),
                           "env": {"sha256": ENV_DIGEST, "canon": "jcs-rfc8785", "changed": False}}),
    ("outcome", None, None, {"judgements": [{"name": "utility", "value": True, "origin": "checker"}]}),
    ("session.end", None, None, {"status": "complete", "appended_by": "worker"}),
]
lines = []
prev = None
t0 = 0                     # mono_ns is relative to the origin taken at session.start (C.13.2)
for seq, (typ, pss, actor, data_) in enumerate(events):
    ev = {"seq": seq, "type": typ, "ts": f"2026-10-07T12:00:{seq:02d}.000000Z", "mono_ns": t0 + seq * 1_000_000,
          "pass": pss, "actor": actor, "prev": prev, "data": data_}
    if typ == "session.end":
        ev["data"]["n_events"] = seq + 1
    line = jcs(ev) + b"\n"
    lines.append(line)
    prev = hashlib.sha256(line).hexdigest()
cap = b"".join(lines)
(OUT / "synthetic.capture.jsonl").write_bytes(cap)
print("capture events", len(lines), "bytes", len(cap), "file sha256", hashlib.sha256(cap).hexdigest(), "head", prev)
# verify chain and the sealed condition (C.13.2)
p = None
for ln in cap.split(b"\n")[:-1]:
    e = json.loads(ln)
    assert e["prev"] == p, e["seq"]
    p = hashlib.sha256(ln + b"\n").hexdigest()
last = json.loads(cap.split(b"\n")[-2])
assert last["type"] == "session.end" and last["data"]["n_events"] == len(lines)
print("chain ok, sealed; blobs:", {k[:12]: len(v) for k, v in blobs.items()})
