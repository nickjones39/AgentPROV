"""Generate the four C.16 worked examples from real artefacts (scratch prototype).

r2 contract (regenerated 2026-10-08, RESOLUTIONS §5 step 10; SWEEP_r2 SW-C1): execution ids over the mapping id
`<adapter id>/<profile id>` (C.4.1, AD-04), `unit`, `profile {id, version: int, sha256}`, `rules {<ns>: <int>}`,
dialect variants owned by D, `prov_primary` on every artefact, existence classes with weaker fields in `evf`,
D.5.4 rule names, merged instrumentation items, the merged `aer.acc.reported_counts@1` check and the C.12.3 issue
codes. Outputs are written next to this script and are never edited by hand.

Run: uv run --no-project --with rfc8785==0.1.4 python gen_examples.py
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from aerlib import (Pairs, add_lex, pget, ex_id, ex_preimage, jcs, parse_ordered, plain, seal_and_serialise,
                    sha256_hex, validate)

INV = Path.home() / "Desktop/PhD/Labs/AgentPROV/investigation"
UP = Path.home() / "Desktop/PhD/Labs/AgentPROV-upstream"
OUT = Path(__file__).parent

NS_IRI = "https://w3id.org/agentprov/ns/{}#"

# Stand-in profile texts. The shipped profiles (D.4.3, D.4.4) do not exist yet, so `profile.sha256` in these vectors
# is the SHA-256 of the stand-in bytes below (C.16.0). It changes when the vectors are regenerated against the
# shipped profile files.
PROFILE_STANDINS = {
    pid: (f'# stand-in for spec/examples/C (C.16.0); not the shipped profile\n'
          f'[profile]\nid = "{pid}"\nversion = 1\nformat = "agentprov-source-profile/0.1"\n'
          f'source_id = "{src}"\nfamily = "{fam}"\n').encode("utf-8")
    for pid, src, fam in (("agentdojo-upstream", "agentdojo", "agentdojo"), ("adprov-v1", "adprov-v1", "adprov"),
                          ("stac", "stac", "stac"), ("rope", "rope", "agentdojo"))
}


# Shipped profiles replace their stand-ins (erratum E22, phase 6): C.16.1 carries the digest of the shipped
# `agentdojo-upstream` profile and is produced byte for byte by the shipped mapper
# (tests/adapters/agentdojo/test_mapper.py::test_c16_1_vector_is_reproduced; tools/agentdojo/regen_c161.py).
SHIPPED_PROFILES = {
    "agentdojo-upstream": OUT.resolve().parents[3] / "src/agentprov/adapters/agentdojo/profiles/agentdojo-upstream.profile.toml",
}


def profile(pid: str) -> dict:
    if pid in SHIPPED_PROFILES:
        return {"id": pid, "version": 1, "sha256": sha256_hex(SHIPPED_PROFILES[pid].read_bytes())}
    return {"id": pid, "version": 1, "sha256": sha256_hex(PROFILE_STANDINS[pid])}


def L(a, p=None, **kw):
    d = {"a": a}
    if p is not None:
        d["p"] = p
    d.update(kw)
    return d


def text_parts(content):
    """AgentDojo content (str | None | list of blocks) -> AER parts (text / reasoning)."""
    if content is None:
        return [{"t": "text", "text": None}]
    if isinstance(content, str):
        return [{"t": "text", "text": content}]
    out = []
    for b in content:
        if b["type"] == "text":
            out.append({"t": "text", "text": b["content"]})
        elif b["type"] in ("thinking", "redacted_thinking"):
            out.append({"t": "reasoning", "text": b["content"], **({"redacted": True} if b["type"] == "redacted_thinking" else {})})
        else:
            out.append({"t": "other", "type": b["type"], "value": b})
    return out


def catalogue_of(recs, seal_body):
    cat = {r.split("#")[0] for rec in recs for r in rec.get("rule", [])}
    cat |= {i["rule"] for i in seal_body.get("issues", [])}
    cat |= {c["id"] for c in seal_body["accounting"]["checks"]}
    return cat


def write(name, recs, seal_body, artefacts):
    data, digest = seal_and_serialise(recs, seal_body)
    errs = validate(data, artefacts, catalogue_of(recs, seal_body))
    (OUT / f"{name}.aer.jsonl").write_bytes(data)
    print(f"== {name}: {len(recs)+1} records, {len(data)} bytes, ex {recs[0]['ex']}, execution digest {digest}")
    for e in errs:
        print("   ERROR", e)
    return data


def unverifiable_issue(seal_body):
    """C.12.3 / D.6.9: an unverifiable (inconsistent) verdict raises the mirroring issue, citing the check."""
    for c in seal_body["accounting"]["checks"]:
        if c["verdict"] in ("unverifiable", "inconsistent"):
            seal_body["issues"].append({"code": f"accounting_{c['verdict']}", "ids": [c["scope"]], "rule": c["id"]})


# =====================================================================================
# 1. AgentDojo June-2024 native log (transformers_pi_detector), dialect variant v0.k11
# =====================================================================================
def ex_agentdojo():
    path = INV / "samples/agentdojo/gpt-4o-2024-05-13-transformers_pi_detector__banking__user_task_13__important_instructions__injection_task_7.json"
    raw = path.read_bytes()
    src = parse_ordered(raw)
    d = plain(src)
    msgs = d["messages"]
    sha = sha256_hex(raw)
    prof = profile("agentdojo-upstream")
    adapter = "agentdojo.tracelogger"
    loc = {"p": ""}
    ex = ex_id(adapter + "/" + prof["id"], sha, loc)
    ns = {"agentdojo": NS_IRI.format("agentdojo")}
    R = []
    R.append({
        "k": "execution", "id": "exec", "aer": "0.1", "ex": ex, "mode": "import", "unit": "agent_execution",
        "source_key": {"sha256": sha, "loc": loc},
        "artifacts": [{"id": "a0", "role": "primary", "prov_primary": "native", "sha256": sha, "bytes": len(raw),
                       "media": "application/json",
                       "origin": {"kind": "git", "repo": "https://github.com/ethz-spylab/agentdojo",
                                  "commit": "c274885610efaaafec38b6d3eb07152ba7ff3f94",
                                  "path": "runs/gpt-4o-2024-05-13-transformers_pi_detector/banking/user_task_13/important_instructions/injection_task_7.json",
                                  "blob_sha1": "4cbf084087345a813c6d93e99aa2d37eec2ca507"}}],
        "adapter": {"id": adapter, "version": "0.1.0"},
        "dialect": {"id": "agentdojo.tracelogger", "variant": "v0.k11"},
        "profile": prof,
        "rules": {"aer": 1, "agentdojo": 1},
        "ns": ns, "canon": "jcs-rfc8785", "hash": "sha256",
        "task": {"benchmark": "agentdojo", "suite": "banking", "task_id": "user_task_13",
                 "attack_id": "important_instructions", "attack_target_id": "injection_task_7",
                 "defense_id": "transformers_pi_detector"},
        "ev": "O", "by": "config",
        "evf": {"/task/benchmark": "D", "/task/defense_id": "I"},
        "rule": ["agentdojo.benchmark_from_dialect@1#/task/benchmark",
                 "agentdojo.defence_suffix@1#/task/defense_id"],
        "src": [L("a0", "/suite_name"), L("a0", "/user_task_id"), L("a0", "/attack_type"),
                L("a0", "/injection_task_id"), L("a0", o="/path")],
        "unk": {"/instrumentation": "not_recorded"},
        "ext": {"agentdojo": {"pipeline_name": d["pipeline_name"], "error": d["error"]}},
    })
    # actors in D.6.5 Step 2 order
    R.append({"k": "actor", "id": "bench", "kind": "benchmark", "name": "agentdojo",
              "ev": "D", "rule": ["agentdojo.benchmark_from_dialect@1"],
              "unk": {"/version": "not_recorded", "/code": "not_recorded"}})
    R.append({"k": "actor", "id": "user", "kind": "simulated_user", "ev": "D",
              "rule": ["agentdojo.user_is_simulated@1"]})
    R.append({"k": "actor", "id": "agent", "kind": "llm_agent", "on_behalf_of": "user",
              "model": {"requested": "gpt-4o-2024-05-13"},
              "ev": "D", "evf": {"/model": "I"},
              "rule": ["agentdojo.user_is_simulated@1", "agentdojo.pipeline_dir_is_model_identity@1#/model"],
              "src": [L("a0", o="/path")],
              "unk": {"/model/served": "not_recorded", "/model/provider": "not_recorded", "/params": "not_recorded"}})
    R.append({"k": "actor", "id": "env", "kind": "tool_runtime", "name": "agentdojo.FunctionsRuntime",
              "on_behalf_of": "agent", "ev": "D", "evf": {"/on_behalf_of": "I"},  # EF E.10 item 21
              "rule": ["agentdojo.functions_runtime@1", "agentdojo.auto_execution_unverified@1#/on_behalf_of"]})
    R.append({"k": "actor", "id": "att", "kind": "attacker", "name": "important_instructions",
              "ev": "O", "by": "config", "src": [L("a0", "/attack_type")]})
    R.append({"k": "actor", "id": "def0", "kind": "defense", "name": "transformers_pi_detector",
              "ev": "I", "rule": ["agentdojo.defence_suffix@1"], "src": [L("a0", o="/path")],
              "unk": {"/model": "not_recorded", "/version": "not_recorded"}})
    R.append({"k": "scope", "id": "run", "kind": "run", "actor": "agent",
              "t": {"dur_s": d["duration"], "dur_clock": "wall"},
              "ev": "O", "by": "source", "src": [L("a0", "/duration")],
              "unk": {"/t/start": "not_recorded", "/t/end": "not_recorded", "/status": "not_recorded"}})
    R.append({"k": "scope", "id": "att0", "kind": "attempt", "parent": "run", "actor": "agent", "scored": True,
              "ev": "D", "rule": ["agentdojo.log_holds_last_pass@1"], "unk": {"/index": "lost"}})
    vec, payload = next(iter(d["injections"].items()))
    R.append({"k": "fixture", "id": "fx0", "kind": "injection_payload", "vector": vec, "content": payload,
              "actor": "att", "ev": "O", "by": "benchmark", "evf": {"/actor": "I"},
              "rule": ["agentdojo.payload_attributed_to_attacker@1#/actor"],
              "src": [L("a0", f"/injections/{vec}")]})
    # m0 system, m1 user
    R.append({"k": "message", "id": "m0", "scope": "att0", "role": "system", "actor": "bench",
              "parts": text_parts(msgs[0]["content"]), "ev": "O", "by": "source",
              "evf": {"/actor": "D"}, "rule": ["agentdojo.system_prompt_from_harness@1#/actor"],
              "src": [L("a0", "/messages/0")]})
    R.append({"k": "message", "id": "m1", "scope": "att0", "role": "user", "actor": "user",
              "parts": text_parts(msgs[1]["content"]), "after": [{"id": "m0", "b": "pos"}],
              "ev": "O", "by": "source", "evf": {"/actor": "D", "/after": "D"},
              "rule": ["agentdojo.user_is_simulated@1#/actor", "agentdojo.messages_append_ordered@1#/after"],
              "src": [L("a0", "/messages/1")]})
    unk_mc = {"/request": "not_recorded", "/response": "not_recorded", "/usage": "not_recorded",
              "/finish_reason": "not_recorded", "/tools": "not_recorded", "/t": "not_recorded"}
    R.append({"k": "model_call", "id": "mc0", "actor": "agent", "role": "agent", "scope": "att0",
              "input": ["m0", "m1"], "status": "kept", "after": [{"id": "m1", "b": "pos"}],
              "ev": "D", "evf": {"/input": "I"},
              "rule": ["agentdojo.assistant_msg_has_one_call@1", "agentdojo.messages_append_ordered@1#/after",
                       "agentdojo.context_is_prefix@1#/input"],
              "unk": dict(unk_mc)})
    tc = msgs[2]["tool_calls"][0]
    m2 = {"k": "message", "id": "m2", "scope": "att0", "role": "assistant", "actor": "agent", "generated_by": "mc0",
          "parts": text_parts(msgs[2]["content"]) + [
              {"t": "tool_call", "name": tc["function"], "args": tc["args"], "provider_call_id": tc["id"]}],
          "after": [{"id": "mc0", "b": "causal"}],
          "ev": "O", "by": "source", "evf": {"/generated_by": "D", "/after": "D"},
          "rule": ["agentdojo.assistant_msg_has_one_call@1#/generated_by", "aer.output_after_generator@1#/after"],
          "src": [L("a0", "/messages/2")], "unk": {"/parts/1/args_raw": "not_recorded"}}
    add_lex(m2, [("/parts/1/args", pget(src, "/messages/2/tool_calls/0/args"))])
    R.append(m2)
    tm = msgs[3]
    R.append({"k": "tool_execution", "id": "te0", "actor": "env", "scope": "att0", "call": "m2#1",
              "name": tm["tool_call"]["function"], "args": tm["tool_call"]["args"], "status": "ok",
              "after": [{"id": "m2", "b": "causal"}],
              "ev": "D", "evf": {"/name": "O", "/args": "O"}, "by": "source",
              "rule": ["agentdojo.tool_msg_is_one_execution@1", "agentdojo.call_id_unique_match@1#/call",
                       "agentdojo.tool_status_from_error@1#/status", "aer.execution_after_call@1#/after"],
              "src": [L("a0", "/messages/3/tool_call"), L("a0", "/messages/3/error")],
              "unk": {"/args_effective": "not_recorded", "/returned": "not_recorded", "/t": "not_recorded"}})
    R.append({"k": "decision", "id": "dc0", "actor": "def0", "scope": "att0", "subject": "te0", "verdict": "redact",
              "after": [{"id": "te0", "b": "causal"}],
              "ev": "I", "rule": ["agentdojo.pi_detector_sentinel@1", "aer.decision_after_subject@1#/after"],
              "src": [L("a0", "/messages/3/content")],
              "unk": {"/original": "overwritten", "/reason": "not_recorded", "/t": "not_recorded"}})
    R.append({"k": "message", "id": "m3", "scope": "att0", "role": "tool", "actor": "def0", "generated_by": "dc0",
              "parts": [{"t": "tool_result", "responds_to": "m2#1", "text": tm["content"], "error": tm["error"]}],
              "after": [{"id": "dc0", "b": "causal"}],
              "ev": "O", "by": "source", "evf": {"/actor": "I", "/generated_by": "I", "/parts/0/responds_to": "D", "/after": "I"},
              "rule": ["agentdojo.pi_detector_sentinel@1#/actor", "agentdojo.pi_detector_sentinel@1#/generated_by",
                       "agentdojo.call_id_unique_match@1#/parts/0/responds_to", "aer.output_after_generator@1#/after"],
              "src": [L("a0", "/messages/3")]})
    R.append({"k": "model_call", "id": "mc1", "actor": "agent", "role": "agent", "scope": "att0",
              "input": ["m0", "m1", "m2", "m3"], "status": "kept", "after": [{"id": "m3", "b": "pos"}],
              "ev": "D", "evf": {"/input": "I"},
              "rule": ["agentdojo.assistant_msg_has_one_call@1", "agentdojo.messages_append_ordered@1#/after",
                       "agentdojo.context_is_prefix@1#/input"],
              "unk": dict(unk_mc)})
    R.append({"k": "message", "id": "m4", "scope": "att0", "role": "assistant", "actor": "agent", "generated_by": "mc1",
              "parts": text_parts(msgs[4]["content"]), "after": [{"id": "mc1", "b": "causal"}],
              "ev": "O", "by": "source", "evf": {"/generated_by": "D", "/after": "D"},
              "rule": ["agentdojo.assistant_msg_has_one_call@1#/generated_by", "aer.output_after_generator@1#/after"],
              "src": [L("a0", "/messages/4")]})
    # D.6.7: no run error, attacked, not DoS -> origin checker under agentdojo.checker_outcome@1
    R.append({"k": "judgement", "id": "j0", "actor": "bench", "subject": "run", "name": "utility", "value": d["utility"], "origin": "checker",
              "ev": "O", "by": "benchmark", "evf": {"/origin": "D"},
              "rule": ["agentdojo.checker_outcome@1#/origin", "agentdojo.checker_inputs_unverified@1#/inputs"],
              "unk": {"/inputs": "not_recorded"},  # EF E.10 item 21
              "src": [L("a0", "/utility"), L("a0", "/error")]})
    R.append({"k": "judgement", "id": "j1", "actor": "bench", "subject": "run", "name": "security", "value": d["security"], "origin": "checker",
              "ev": "O", "by": "benchmark", "evf": {"/origin": "D"},
              "rule": ["agentdojo.checker_outcome@1#/origin", "agentdojo.checker_inputs_unverified@1#/inputs"],
              "unk": {"/inputs": "not_recorded"},  # EF E.10 item 21
              "src": [L("a0", "/security"), L("a0", "/attack_type"), L("a0", "/error")]})
    seal_body = {
        "accounting": {
            "status": "unverifiable",
            "checks": [
                {"id": "aer.acc.agent_calls_vs_assistant@1", "scope": "att0", "verdict": "unverifiable",
                 "reason": "model_calls_derived_from_messages", "observed": {"assistant_messages": 2, "model_calls": 2}},
                {"id": "aer.acc.tool_calls_dispatched@1", "scope": "att0", "verdict": "consistent",
                 "observed": {"tool_calls": 1, "tool_executions": 1, "unexecuted": 0}},
                {"id": "aer.acc.tool_results_linked@1", "scope": "att0", "verdict": "consistent",
                 "observed": {"tool_results": 1, "linked": 1}},
                {"id": "aer.acc.executions_have_results@1", "scope": "att0", "verdict": "consistent",
                 "observed": {"tool_executions": 1, "with_result": 1}},
                {"id": "aer.acc.assistant_generated_by@1", "scope": "att0", "verdict": "consistent",
                 "observed": {"assistant_messages": 2, "with_generated_by": 2}},
            ],
        },
        "issues": [{"code": "earlier_attempts_unobservable", "ids": ["att0"], "rule": "agentdojo.log_holds_last_pass@1"}],
    }
    unverifiable_issue(seal_body)
    return write("agentdojo_2024_pi_detector", R, seal_body, {"a0": raw}), R


# =====================================================================================
# 2. AgentDojo-PROV transcript/v1 (released, Llama-3.3-70B, injecagent), dialect variant v1
# =====================================================================================
V1_PATH = INV / "baseline/golden/corpus-prov/meta-llama_llama-3.3-70b-instruct/injecagent/banking_user_task_2_x_injectiontask5_injection.transcript.json"


def iso_z(s):
    assert s.endswith("+00:00"), s
    return s[:-6] + "Z"


def ex_v1():
    raw = V1_PATH.read_bytes()
    src = parse_ordered(raw)
    d = plain(src)
    meta, turns = d["meta"], d["turns"]
    msrc = dict(src)["meta"]
    tsrc = dict(src)["turns"]
    mcsrc = dict(dict(msrc)["model_config"])
    sha = sha256_hex(raw)
    prof = profile("adprov-v1")
    adapter = "adprov.transcript_v1"
    loc = {"p": ""}
    ex = ex_id(adapter + "/" + prof["id"], sha, loc)
    ns = {"adprov": NS_IRI.format("adprov"), "agentdojo": NS_IRI.format("agentdojo")}
    mc = meta["model_config"]
    R = []
    hdr = {
        "k": "execution", "id": "exec", "aer": "0.1", "ex": ex, "mode": "import", "unit": "agent_execution",
        "source_key": {"sha256": sha, "loc": loc},
        "artifacts": [{"id": "a0", "role": "primary", "prov_primary": "native", "sha256": sha, "bytes": len(raw),
                       "media": "application/json",
                       "origin": {"kind": "corpus", "corpus": "AgentDojo-PROV", "version": "2.3",
                                  "producer_commit": "579a908354b93361efe0905ffb7623256aa96a06",
                                  "path": "corpus-prov/meta-llama_llama-3.3-70b-instruct/prov/injecagent/banking_user_task_2_x_injectiontask5_injection.transcript.json"}}],
        "adapter": {"id": adapter, "version": "0.1.0"},
        "dialect": {"id": "adprov.transcript_v1", "variant": "v1"},
        "profile": prof,
        "rules": {"adprov": 1, "aer": 1, "agentdojo": 1},
        "ns": ns, "canon": "jcs-rfc8785", "hash": "sha256",
        "task": {"benchmark": "agentdojo", "suite": meta["suite"], "task_id": meta["user_task_id"],
                 "attack_id": meta["attack_type"], "attack_target_id": meta["injection_task_id"], "defense_id": None},
        # merged instrumentation items (C.3.1, AD-03 R-2); kinds follow the D.10.7 analogues
        "instrumentation": [
            {"id": "adprov.developer_role_rewrite@1", "kind": "request_modifying", "recorded": "none"},
            {"id": "adprov.malformed_tool_call_resample@1", "kind": "harness_policy", "recorded": "summary"},
            {"id": "adprov.upstream_failure_retry@1", "kind": "harness_policy", "recorded": "summary"},
            {"id": "adprov.model_display_name@1", "kind": "attack_parameter", "recorded": "none"},
            {"id": "adprov.temperature_not_transmitted@1", "kind": "harness_policy", "recorded": "none"},
        ],
        "ev": "O", "by": "config",
        "evf": {"/task/benchmark": "D", "/task/defense_id": "D", "/instrumentation": "I"},
        "rule": ["adprov.v1_benchmark_is_agentdojo@1#/task/benchmark", "adprov.release_undefended@1#/task/defense_id",
                 "adprov.v1_capture_code_semantics@1#/instrumentation"],
        "src": [L("a0", "/meta/suite"), L("a0", "/meta/user_task_id"), L("a0", "/meta/attack_type"),
                L("a0", "/meta/injection_task_id")],
        "ext": {"adprov": {"model": meta["model"], "v1": {
            "variant": "released", "meta_keys": [k for k, _ in msrc],
            "model_config_keys": [k for k, _ in mcsrc.items()],
            "usage_keys": [k for k, _ in dict(mcsrc)["usage"]]}}},
    }
    R.append(hdr)
    R.append({"k": "actor", "id": "user", "kind": "simulated_user", "ev": "D", "rule": ["agentdojo.user_is_simulated@1"]})
    ag = {"k": "actor", "id": "agent", "kind": "llm_agent", "on_behalf_of": "user",
          "model": {"requested": meta["model_id"]}, "params": {"temperature": mc["temperature"]},
          "ev": "O", "by": "config", "evf": {"/on_behalf_of": "D"},
          "rule": ["agentdojo.user_is_simulated@1#/on_behalf_of"],
          "src": [L("a0", "/meta/model_id"), L("a0", "/meta/model_config/temperature")],
          "unk": {"/model/served": "not_recorded", "/model/provider": "not_recorded"}}
    add_lex(ag, [("/params/temperature", mcsrc["temperature"])])
    R.append(ag)
    R.append({"k": "actor", "id": "env", "kind": "tool_runtime", "name": "agentdojo.FunctionsRuntime",
              "on_behalf_of": "agent", "ev": "D", "rule": ["agentdojo.functions_runtime@1"]})
    R.append({"k": "actor", "id": "att", "kind": "attacker", "name": meta["attack_type"],
              "ev": "O", "by": "config", "src": [L("a0", "/meta/attack_type")]})
    R.append({"k": "actor", "id": "bench", "kind": "benchmark", "name": "agentdojo", "version": meta["benchmark_version"],
              "code": {"dist": "agentdojo", "dist_version": meta["agentdojo_version"]},
              "ev": "O", "by": "source", "src": [L("a0", "/meta/benchmark_version"), L("a0", "/meta/agentdojo_version")],
              "unk": {"/code/commit": "not_recorded"}})
    R.append({"k": "actor", "id": "harness", "kind": "harness", "name": "agentdojo-prov",
              "ev": "O", "by": "source", "src": [L("a0", "/adprov_schema")],
              "unk": {"/version": "not_recorded", "/code": "not_recorded"}})
    u = mc["usage"]
    usrc = dict(mcsrc["usage"])
    run = {"k": "scope", "id": "run", "kind": "run", "actor": "agent",
           "t": {"start": iso_z(meta["started_at"]), "end": iso_z(meta["ended_at"]), "dur_s": meta["wall_clock_s"],
                 "dur_clock": "monotonic", "raw": {"start": meta["started_at"], "end": meta["ended_at"]}},
           "usage": {"input_tokens": u["prompt_tokens"], "output_tokens": u["completion_tokens"],
                     "total_tokens": u["total_tokens"], "calls": u["n_llm_calls"]},
           "ev": "O", "by": "source", "evf": {"/usage": "O:provider", "/usage/calls": "O"},
           "src": [L("a0", "/meta/started_at"), L("a0", "/meta/ended_at"), L("a0", "/meta/wall_clock_s"),
                   L("a0", "/meta/model_config/usage")],
           "unk": {"/status": "not_recorded"}}
    # ext.lex over every source-copied number of typed fields (C.11.4); sparse, so usually empty here
    add_lex(run, [("/t/dur_s", dict(msrc)["wall_clock_s"]), ("/usage/input_tokens", usrc["prompt_tokens"]),
                  ("/usage/output_tokens", usrc["completion_tokens"]), ("/usage/total_tokens", usrc["total_tokens"]),
                  ("/usage/calls", usrc["n_llm_calls"])])
    R.append(run)
    R.append({"k": "scope", "id": "att0", "kind": "attempt", "parent": "run", "actor": "agent", "index": 0, "scored": True,
              "ev": "D", "rule": ["adprov.single_attempt_from_call_count@1"],
              "src": [L("a0", "/meta/model_config/usage/n_llm_calls")]})
    vec, payload = next(iter(meta["injections"].items()))
    R.append({"k": "fixture", "id": "fx0", "kind": "injection_payload", "vector": vec, "content": payload, "actor": "att",
              "ev": "O", "by": "benchmark", "evf": {"/actor": "I"},
              "rule": ["agentdojo.payload_attributed_to_attacker@1#/actor"],
              "src": [L("a0", f"/meta/injections/{vec}")]})
    R.append({"k": "message", "id": "m0", "scope": "att0", "role": "system", "actor": "bench",
              "parts": [{"t": "text", "text": turns[0]["content"]}], "ev": "O", "by": "source",
              "evf": {"/actor": "D"}, "rule": ["agentdojo.system_prompt_from_harness@1#/actor"], "src": [L("a0", "/turns/0")]})
    R.append({"k": "message", "id": "m1", "scope": "att0", "role": "user", "actor": "user",
              "parts": [{"t": "text", "text": turns[1]["content"]}], "after": [{"id": "m0", "b": "pos"}],
              "ev": "O", "by": "source", "evf": {"/actor": "D", "/after": "D"},
              "rule": ["agentdojo.user_is_simulated@1#/actor", "agentdojo.messages_append_ordered@1#/after"],
              "src": [L("a0", "/turns/1")]})
    # assistant/tool turns
    mid, mcid, teid = 2, 0, 0
    inputs = ["m0", "m1"]
    prev = "m1"
    i = 2
    while i < len(turns):
        t = turns[i]
        assert t["role"] == "assistant"
        mcr = {"k": "model_call", "id": f"mc{mcid}", "actor": "agent", "role": "agent", "scope": "att0",
               "input": list(inputs), "status": "kept", "finish_reason": mc["finish_reasons"][mcid],
               "after": [{"id": prev, "b": "pos"}],
               "ev": "D", "evf": {"/input": "I"},
               "rule": ["adprov.assistant_turn_one_call@1", "agentdojo.messages_append_ordered@1#/after",
                        "adprov.context_is_prefix@1#/input", "adprov.finish_reason_positional@1#/finish_reason"],
               "src": [L("a0", f"/meta/model_config/finish_reasons/{mcid}")],
               "unk": {"/request": "not_recorded", "/response": "not_recorded", "/usage": "not_recorded",
                       "/tools": "not_recorded", "/params": "not_recorded", "/t": "not_recorded"}}
        R.append(mcr)
        parts = [{"t": "text", "text": t["text"]}]
        lexsrc = []
        tsrc_i = dict(tsrc[i])
        for j, c in enumerate(t.get("tool_calls") or []):
            parts.append({"t": "tool_call", "name": c["function"], "args": c["args"], "provider_call_id": c["id"]})
            lexsrc.append((f"/parts/{1+j}/args", dict(tsrc_i["tool_calls"][j])["args"]))
        m = {"k": "message", "id": f"m{mid}", "scope": "att0", "role": "assistant", "actor": "agent",
             "generated_by": f"mc{mcid}", "parts": parts, "after": [{"id": f"mc{mcid}", "b": "causal"}],
             "ev": "O", "by": "source", "evf": {"/generated_by": "D", "/after": "D"},
             "rule": ["adprov.assistant_turn_one_call@1#/generated_by", "aer.output_after_generator@1#/after"],
             "src": [L("a0", f"/turns/{i}")]}
        if t["text"] == "":
            m["unk"] = {"/parts/0/text": "ambiguous"}
            m["rule"].append("adprov.release_null_as_empty@1#/parts/0/text")
        add_lex(m, lexsrc)
        R.append(m)
        asst_id = f"m{mid}"
        inputs.append(asst_id)
        prev = asst_id
        mid += 1
        mcid += 1
        i += 1
        ncalls = len(t.get("tool_calls") or [])
        for j in range(ncalls):
            tt = turns[i]
            assert tt["role"] == "tool"
            te = {"k": "tool_execution", "id": f"te{teid}", "actor": "env", "scope": "att0", "call": f"{asst_id}#{1+j}",
                  "name": tt["function"], "args": tt["args"],
                  "status": "ok" if tt["error"] is None else ("invalid" if tt["error"].startswith("ValidationError") else "error"),
                  "t": {"start": iso_z(tt["started_at"]), "end": iso_z(tt["ended_at"]),
                        "raw": {"start": tt["started_at"], "end": tt["ended_at"]}},
                  "after": [{"id": asst_id, "b": "causal"}],
                  "ev": "O", "by": "source", "evf": {"/call": "D", "/status": "D", "/after": "D"},
                  "rule": ["adprov.call_id_unique_match@1#/call", "agentdojo.tool_status_from_error@1#/status",
                           "aer.execution_after_call@1#/after"],
                  "src": [L("a0", f"/turns/{i}/function"), L("a0", f"/turns/{i}/args"), L("a0", f"/turns/{i}/error"),
                          L("a0", f"/turns/{i}/started_at"), L("a0", f"/turns/{i}/ended_at")],
                  "unk": {"/args_effective": "not_recorded"}}
            add_lex(te, [("/args", dict(tsrc[i])["args"])])
            R.append(te)
            tm = {"k": "message", "id": f"m{mid}", "scope": "att0", "role": "tool", "actor": "env", "generated_by": f"te{teid}",
                  "parts": [{"t": "tool_result", "responds_to": f"{asst_id}#{1+j}", "text": tt["content"], "error": tt["error"]}],
                  "after": [{"id": f"te{teid}", "b": "causal"}],
                  "ev": "O", "by": "source", "evf": {"/generated_by": "D", "/parts/0/responds_to": "D", "/after": "D"},
                  "rule": ["adprov.tool_turn_is_one_execution@1#/generated_by", "adprov.call_id_unique_match@1#/parts/0/responds_to",
                           "aer.output_after_generator@1#/after"],
                  "src": [L("a0", f"/turns/{i}")]}
            R.append(tm)
            inputs.append(f"m{mid}")
            prev = f"m{mid}"
            mid += 1
            teid += 1
            i += 1
    # D.7.3: released utility/security are the stock checkers' values (security of a benign run would be
    # adprov.benign_security_normalised@1, harness_default; this run is attacked)
    R.append({"k": "judgement", "id": "j0", "actor": "bench", "subject": "run", "name": "utility", "value": meta["utility"], "origin": "checker", "ev": "O", "by": "benchmark",
              "evf": {"/origin": "D"},
              "rule": ["adprov.checker_outcome@1#/origin"], "src": [L("a0", "/meta/utility")]})
    R.append({"k": "judgement", "id": "j1", "actor": "bench", "subject": "run", "name": "security", "value": meta["security"], "origin": "checker", "ev": "O", "by": "benchmark",
              "evf": {"/origin": "D"},
              "rule": ["adprov.checker_outcome@1#/origin"],
              "src": [L("a0", "/meta/security"), L("a0", "/meta/attack_type")]})
    n_asst = sum(t["role"] == "assistant" for t in turns)
    n_tool = sum(t["role"] == "tool" for t in turns)
    seal_body = {
        "accounting": {
            "status": "consistent",
            "checks": [
                # C.12.2: the single merged reported-count check (R-13); agent_calls_vs_assistant is omitted because
                # the reported call count is the stronger evidence
                {"id": "aer.acc.reported_counts@1", "scope": "run", "verdict": "consistent",
                 "observed": {"reported_calls": u["n_llm_calls"], "assistant_messages": n_asst, "lost_calls": 0,
                              "finish_reasons": len(mc["finish_reasons"])}},
                {"id": "aer.acc.tool_calls_dispatched@1", "scope": "att0", "verdict": "consistent",
                 "observed": {"tool_calls": n_tool, "tool_executions": n_tool, "unexecuted": 0}},
                {"id": "aer.acc.tool_results_linked@1", "scope": "att0", "verdict": "consistent",
                 "observed": {"tool_results": n_tool, "linked": n_tool}},
                {"id": "aer.acc.executions_have_results@1", "scope": "att0", "verdict": "consistent",
                 "observed": {"tool_executions": n_tool, "with_result": n_tool}},
                {"id": "aer.acc.assistant_generated_by@1", "scope": "att0", "verdict": "consistent",
                 "observed": {"assistant_messages": n_asst, "with_generated_by": n_asst}},
            ],
        },
        "issues": [],
    }
    data = write("adprov_v1_llama_injecagent", R, seal_body, {"a0": raw})
    # ---- regenerate transcript/v1 through the C.15.3 view and compare bytes
    regenerated = serialise(render(data))
    print("   v1 view byte-identical:", regenerated == raw, len(regenerated), len(raw))
    return data, R


def apply_lex(rec, ptr_prefix, value):
    """Re-impose source member order / float-ness recorded in ext.lex onto `value` located at ptr_prefix."""
    lex = (rec.get("ext") or {}).get("lex") or {}
    ords, flts = lex.get("ord", {}), set(lex.get("flt", []))

    def walk(v, at):
        if isinstance(v, dict):
            keys = ords.get(at, sorted(v, key=lambda s: s.encode("utf-16-be")))
            return {k: walk(v[k], at + "/" + k.replace("~", "~0").replace("/", "~1")) for k in keys}
        if isinstance(v, list):
            return [walk(x, f"{at}/{i}") for i, x in enumerate(v)]
        if at in flts and isinstance(v, int) and not isinstance(v, bool):
            return float(v)
        return v
    return walk(value, ptr_prefix)


def render(aer_bytes: bytes) -> dict:
    """transcript/v1 view (C.15.3 `render`), released variant only (prototype); reads nothing from raw."""
    recs = [json.loads(l) for l in aer_bytes.split(b"\n")[:-1]]
    by = {r["id"]: r for r in recs}
    hdr = recs[0]
    v1 = hdr["ext"]["adprov"]["v1"]
    task = hdr["task"]
    agent, bench, run = by["agent"], by["bench"], by["run"]
    fx = [r for r in recs if r["k"] == "fixture" and r["kind"] == "injection_payload"]
    jud = {r["name"]: r["value"] for r in recs if r["k"] == "judgement" and "revises" not in r}
    mcs = [r for r in recs if r["k"] == "model_call" and r["role"] == "agent"]
    params = apply_lex(agent, "/params", agent.get("params", {}))
    usage_map = {"prompt_tokens": "input_tokens", "completion_tokens": "output_tokens", "total_tokens": "total_tokens",
                 "n_llm_calls": "calls", "reasoning_tokens": "reasoning_tokens", "cached_tokens": "cache_read_tokens"}
    src_of = {
        "model": lambda: hdr["ext"]["adprov"]["model"],
        "model_id": lambda: agent["model"]["requested"],
        "suite": lambda: task["suite"],
        "user_task_id": lambda: task["task_id"],
        "injection_task_id": lambda: task["attack_target_id"],
        "attack_type": lambda: task["attack_id"] if task["attack_id"] is not None else "benign",
        "injections": lambda: {f["vector"]: f["content"] for f in fx},
        "utility": lambda: jud.get("utility"),
        "security": lambda: jud.get("security"),
        "started_at": lambda: run["t"]["raw"]["start"],
        "ended_at": lambda: run["t"]["raw"]["end"],
        "wall_clock_s": lambda: apply_lex(run, "/t/dur_s", run["t"]["dur_s"]),
        "agentdojo_version": lambda: bench["code"]["dist_version"],
        "benchmark_version": lambda: bench["version"],
        "model_config": lambda: {
            k: {"temperature": lambda: params["temperature"],
                "usage": lambda: {uk: apply_lex(run, "/usage/" + usage_map[uk], run["usage"][usage_map[uk]])
                                  for uk in v1["usage_keys"]},
                "finish_reasons": lambda: [m["finish_reason"] for m in mcs]}[k]()
            for k in v1["model_config_keys"]},
    }
    meta = {k: src_of[k]() for k in v1["meta_keys"]}
    turns = []
    msgs = [r for r in recs if r["k"] == "message" and r["scope"] == "att0"]
    msgs.sort(key=lambda r: int(r["id"][1:]))
    tes = {r["id"]: r for r in recs if r["k"] == "tool_execution"}
    parts = {f'{m["id"]}#{k}': p for m in msgs for k, p in enumerate(m["parts"])}
    for m in msgs:
        role = m["role"]
        if role in ("system", "user"):
            turns.append({"role": role, "content": m["parts"][0]["text"]})
        elif role == "assistant":
            t = {"role": "assistant", "text": m["parts"][0]["text"]}
            calls = []
            for k, p in enumerate(m["parts"]):
                if p["t"] == "tool_call":
                    calls.append({"id": p["provider_call_id"], "function": p["name"],
                                  "args": apply_lex(m, f"/parts/{k}/args", p["args"])})
            if calls:
                t["tool_calls"] = calls
            turns.append(t)
        elif role == "tool":
            te = tes[m["generated_by"]]
            p = m["parts"][0]
            t = {"role": "tool", "tool_call_id": parts[p["responds_to"]]["provider_call_id"], "function": te["name"],
                 "args": apply_lex(te, "/args", te["args"]), "content": p["text"],
                 "content_sha256": "sha256:" + hashlib.sha256(p["text"].encode()).hexdigest(), "error": p["error"]}
            if "t" in te and "raw" in te["t"]:
                t["started_at"], t["ended_at"] = te["t"]["raw"]["start"], te["t"]["raw"]["end"]
            turns.append(t)
    return {"adprov_schema": "transcript/v1", "meta": meta, "turns": turns}


def serialise(doc: dict) -> bytes:
    """C.15.3 `serialise`: json.dumps(doc, indent=2), Python defaults, no trailing newline."""
    return json.dumps(doc, indent=2).encode("utf-8")


# =====================================================================================
# 3. STAC case 223 (scenario record; STAC import is planned)
# =====================================================================================
def ex_stac():
    art = UP / "multiturn-agent-attack/data/STAC_benchmark_data.json"
    raw = art.read_bytes()
    sha = sha256_hex(raw)
    s, e = 2190260, 2195497
    sl = raw[s:e]
    rec = plain(parse_ordered(sl))
    assert rec["id"] == 223
    full = json.loads(raw)
    assert full[223] == rec
    prof = profile("stac")
    adapter = "stac.json_array"
    loc = {"p": "/223"}                    # canonical key form; the byte span stays in the src locators (C.4.1)
    ex = ex_id(adapter + "/" + prof["id"], sha, loc)
    B = lambda p: {"a": "a0", "bytes": [s, e], "p": p}
    gc = rec["generation_config"]
    ih = rec["interaction_history"]
    ph = rec["planner_history"]
    R = []
    R.append({
        "k": "execution", "id": "exec", "aer": "0.1", "ex": ex, "mode": "import", "unit": "scenario",
        "source_key": {"sha256": sha, "loc": loc},
        "artifacts": [{"id": "a0", "role": "primary", "prov_primary": "native", "sha256": sha, "bytes": len(raw),
                       "media": "application/json",
                       "origin": {"kind": "git", "repo": "https://github.com/amazon-science/MultiTurnAgentAttack",
                                  "commit": "ddeede7a0042d108b819e35281135b0b0fabb4de", "path": "data/STAC_benchmark_data.json",
                                  "blob_sha1": "b2882668a78edba1e4bb426f0864c2dcf6c4b204"}}],
        "adapter": {"id": adapter, "version": "0.1.0"},
        "dialect": {"id": "stac.json_array", "variant": "v1"},
        "profile": prof,
        "rules": {"aer": 1, "stac": 1},
        "ns": {"stac": NS_IRI.format("stac")}, "canon": "jcs-rfc8785", "hash": "sha256",
        "task": {"benchmark": "stac", "environment": gc["environment"], "task_id": str(rec["id"]), "attack_id": "stac"},
        "ev": "O", "by": "source", "evf": {"/task/attack_id": "D", "/task/benchmark": "D"},
        "rule": ["stac.case_is_attack@1#/task/attack_id", "stac.benchmark_from_dialect@1#/task/benchmark"],
        "src": [B("/id"), B("/generation_config/environment")],
        "unk": {"/task/defense_id": "not_recorded", "/instrumentation": "not_recorded"},
        "ext": {"stac": {"dataset": gc["dataset"], "generation_config": gc}},
    })
    # D.8.2: no llm_agent actor is emitted for a scenario; the target agent is not asserted (R-28)
    for aid, role, key in (("gen", "tool_chain_generator", "tool_chain_generator"),
                           ("verifier", "tool_chain_verifier", "tool_chain_verifier"),
                           ("writer", "prompt_writer", "prompt_writer"), ("planner", "attack_planner", "planner")):
        R.append({"k": "actor", "id": aid, "kind": "attacker", "role": role, "model": {"requested": gc[key]},
                  "ev": "O", "by": "source", "src": [B(f"/generation_config/{key}")],
                  "unk": {"/model/served": "not_recorded", "/params": "not_recorded"}})
    R.append({"k": "actor", "id": "script", "kind": "attacker", "role": "context_fabricator", "name": "STAC_gen step 3",
              "ev": "I", "rule": ["stac.assistant_turns_scripted@1"]})
    R.append({"k": "actor", "id": "env", "kind": "tool_runtime", "name": "SHADE_Arena workspace (STAC-vendored)",
              "ev": "D", "rule": ["stac.environment_from_config@1"], "src": [B("/generation_config/environment")]})
    R.append({"k": "scope", "id": "run", "kind": "run", "ev": "D", "rule": ["stac.case_is_one_scenario@1"],
              "unk": {"/t": "not_recorded", "/status": "not_recorded"}})
    R.append({"k": "scope", "id": "thr0", "kind": "thread", "parent": "run", "ev": "D",
              "rule": ["stac.interaction_history_is_thread@1"], "src": [B("/interaction_history")]})
    R.append({"k": "scope", "id": "thr1", "kind": "thread", "parent": "run", "actor": "planner", "ev": "D",
              "rule": ["stac.planner_history_is_thread@1"], "src": [B("/planner_history")]})
    R.append({"k": "fixture", "id": "fx0", "kind": "attack_plan", "content": rec["attack_plan"], "actor": "gen",
              "ev": "O", "by": "source", "evf": {"/actor": "D"}, "rule": ["stac.plan_from_generator@1#/actor"],
              "src": [B("/attack_plan")]})
    # m1: scripted assistant tool call (array index 1)
    c = ih[1]["tool_calls"][0]
    args = json.loads(json.loads(c["function"]["arguments"]))
    R.append({"k": "message", "id": "m1", "scope": "thr0", "role": "assistant", "actor": "script",
              "parts": [{"t": "tool_call", "name": c["function"]["name"], "args": args,
                         "args_raw": c["function"]["arguments"], "provider_call_id": c["id"]}],
              "ev": "O", "by": "source", "evf": {"/actor": "I", "/parts/0/args": "D"},
              "rule": ["stac.assistant_turns_scripted@1#/actor", "stac.double_json_arguments@1#/parts/0/args"],
              "src": [B("/interaction_history/1")],
              "ext": {"stac": {"plan_step": 1}}})
    R.append({"k": "tool_execution", "id": "te0", "actor": "env", "scope": "thr0", "call": "m1#0",
              "name": ih[2]["name"], "status": "ok", "after": [{"id": "m1", "b": "causal"}],
              "ev": "D", "evf": {"/name": "O", "/status": "I"}, "by": "source",
              "rule": ["stac.tool_msg_is_one_execution@1", "stac.call_id_unique_match@1#/call",
                       "stac.tool_status_from_content@1#/status", "aer.execution_after_call@1#/after"],
              "src": [B("/interaction_history/2/name"), B("/interaction_history/2/tool_call_id")],
              "unk": {"/args": "not_recorded", "/args_effective": "not_recorded", "/t": "not_recorded"}})
    R.append({"k": "message", "id": "m2", "scope": "thr0", "role": "tool", "actor": "env", "generated_by": "te0",
              "parts": [{"t": "tool_result", "responds_to": "m1#0", "name": ih[2]["name"], "text": ih[2]["content"]}],
              "after": [{"id": "te0", "b": "causal"}],
              "ev": "O", "by": "source", "evf": {"/generated_by": "D", "/parts/0/responds_to": "D", "/after": "D"},
              "rule": ["stac.tool_msg_is_one_execution@1#/generated_by", "stac.call_id_unique_match@1#/parts/0/responds_to",
                       "aer.output_after_generator@1#/after"],
              "src": [B("/interaction_history/2")]})
    R.append({"k": "message", "id": "m0", "scope": "thr0", "role": "user", "actor": "writer",
              "parts": [{"t": "text", "text": ih[0]["content"]}], "after": [{"id": "te0", "b": "proto"}],
              "ev": "O", "by": "source", "evf": {"/actor": "I", "/after": "I"},
              "rule": ["stac.prefix_user_turns_by_prompt_writer@1#/actor", "stac.prompt_written_after_execution@1#/after"],
              "src": [B("/interaction_history/0")]})
    R.append({"k": "model_call", "id": "mc0", "actor": "planner", "role": "auxiliary", "scope": "thr1", "status": "kept",
              "after": [{"id": "m0", "b": "proto"}, {"id": "m2", "b": "proto"}],
              "ev": "D", "evf": {"/after": "I"},
              "rule": ["stac.planner_entry_has_one_call@1", "stac.planning_after_prefix@1#/after"],
              "src": [B("/planner_history/0")],
              "unk": {"/input": "not_recorded", "/request": "not_recorded", "/response": "not_recorded",
                      "/usage": "not_recorded", "/params": "not_recorded", "/t": "not_recorded"}})
    R.append({"k": "message", "id": "p0", "scope": "thr1", "role": "assistant", "actor": "planner", "generated_by": "mc0",
              "parts": [{"t": "other", "type": "stac.planner_output", "value": ph[0]}],
              "after": [{"id": "mc0", "b": "causal"}],
              "ev": "O", "by": "source", "evf": {"/generated_by": "D", "/after": "D"},
              "rule": ["stac.planner_entry_has_one_call@1#/generated_by", "aer.output_after_generator@1#/after"],
              "src": [B("/planner_history/0")]})
    # R-56: the final user turn quotes the planner's prediction; it is not generated by mc0 (no generated_by);
    # its order after p0 rests on the generator procedure (`proto`, C.8.2) under the equality rule
    R.append({"k": "message", "id": "m3", "scope": "thr0", "role": "user", "actor": "planner",
              "parts": [{"t": "text", "text": ih[3]["content"]}], "after": [{"id": "p0", "b": "proto"}],
              "ev": "O", "by": "source", "evf": {"/actor": "D", "/after": "D"},
              "rule": ["stac.final_prompt_from_planner@1#/actor", "stac.final_prompt_from_planner@1#/after"],
              "src": [B("/interaction_history/3"), B("/planner_history/0/predicted_attack_prompt")]})
    seal_body = {
        "accounting": {
            "status": "consistent",
            "checks": [
                {"id": "aer.acc.tool_calls_dispatched@1", "scope": "thr0", "verdict": "consistent",
                 "observed": {"tool_calls": 1, "tool_executions": 1, "unexecuted": 0}},
                {"id": "aer.acc.tool_results_linked@1", "scope": "thr0", "verdict": "consistent",
                 "observed": {"tool_results": 1, "linked": 1}},
                {"id": "aer.acc.executions_have_results@1", "scope": "thr0", "verdict": "consistent",
                 "observed": {"tool_executions": 1, "with_result": 1}},
            ],
        },
        "issues": [
            {"code": "no_outcome_recorded", "ids": ["run"], "rule": "stac.no_judgements_released@1"},
            {"code": "stac.target_response_not_released", "ids": ["m3"], "rule": "stac.no_judgements_released@1"},
        ],
    }
    return write("stac_case_223", R, seal_body, {"a0": raw}), R


# =====================================================================================
# 4. ROPE denial (qwen3-235b, autodojo), dialect variant v1.k14
# =====================================================================================
def ex_rope():
    path = INV / "samples/rope/runs__qwen3-235b__slack__user_task_0__autodojo__injection_task_4.json"
    raw = path.read_bytes()
    src = parse_ordered(raw)
    d = plain(src)
    msgs = d["messages"]
    sha = sha256_hex(raw)
    prof = profile("rope")
    adapter = "agentdojo.tracelogger"
    loc = {"p": ""}
    ex = ex_id(adapter + "/" + prof["id"], sha, loc)
    R = []
    R.append({
        "k": "execution", "id": "exec", "aer": "0.1", "ex": ex, "mode": "import", "unit": "agent_execution",
        "source_key": {"sha256": sha, "loc": loc},
        "artifacts": [{"id": "a0", "role": "primary", "prov_primary": "native", "sha256": sha, "bytes": len(raw),
                       "media": "application/json",
                       "origin": {"kind": "git", "repo": "https://github.com/xhOwenMa/ROPE",
                                  "commit": "64495e16e640d687e06e6b1b6cee6dccc5b9b7cb",
                                  "path": "runs/qwen3-235b/slack/user_task_0/autodojo/injection_task_4.json",
                                  "blob_sha1": "f5dc686a27eb880baf02642cee4ebac3fd4d3b2a"}}],
        "adapter": {"id": adapter, "version": "0.1.0"},
        "dialect": {"id": "agentdojo.tracelogger", "variant": "v1.k14"},
        "profile": prof,
        "rules": {"aer": 1, "agentdojo": 1, "rope": 1},
        "ns": {"agentdojo": NS_IRI.format("agentdojo"), "rope": NS_IRI.format("rope")},
        "canon": "jcs-rfc8785", "hash": "sha256",
        "task": {"benchmark": "agentdojo", "suite": d["suite_name"], "task_id": d["user_task_id"],
                 "attack_id": d["attack_type"], "attack_target_id": d["injection_task_id"], "defense_id": "rope"},
        "ev": "O", "by": "config", "evf": {"/task/benchmark": "D", "/task/defense_id": "I"},
        "rule": ["rope.benchmark_from_suite@1#/task/benchmark", "rope.guard_active_in_main_tree@1#/task/defense_id"],
        "src": [L("a0", "/suite_name"), L("a0", "/user_task_id"), L("a0", "/attack_type"), L("a0", "/injection_task_id"),
                L("a0", o="/path")],
        "unk": {"/instrumentation": "not_recorded"},
        "ext": {"agentdojo": {"pipeline_name": d["pipeline_name"], "error": d["error"],
                              "benchmark_version": d["benchmark_version"],
                              "agentdojo_package_version": d["agentdojo_package_version"]},
                "rope": {"tree": "main", "model_dir": "qwen3-235b", "attack_dir": "autodojo"}},
    })
    # actors in D.6.5 Step 2 order, plus the profile's harness actor
    R.append({"k": "actor", "id": "bench", "kind": "benchmark", "name": "agentdojo", "version": d["benchmark_version"],
              "ev": "O", "by": "source", "src": [L("a0", "/benchmark_version")], "unk": {"/code": "not_recorded"}})
    R.append({"k": "actor", "id": "user", "kind": "simulated_user", "ev": "D", "rule": ["agentdojo.user_is_simulated@1"]})
    R.append({"k": "actor", "id": "agent", "kind": "llm_agent", "on_behalf_of": "user", "model": {"requested": "qwen3-235b"},
              "ev": "D", "evf": {"/model": "I"},
              "rule": ["agentdojo.user_is_simulated@1", "rope.model_dir_identity@1#/model"],
              "src": [L("a0", o="/path"), L("a0", "/messages/2/tool_calls/0/id")],
              "unk": {"/model/served": "not_recorded", "/model/provider": "not_recorded", "/params": "not_recorded"}})
    R.append({"k": "actor", "id": "env", "kind": "tool_runtime", "name": "agentdojo.FunctionsRuntime", "on_behalf_of": "agent",
              "ev": "D", "evf": {"/on_behalf_of": "I"},  # EF E.10 item 21 (item 3's I twin)
              "rule": ["agentdojo.functions_runtime@1", "agentdojo.auto_execution_unverified@1#/on_behalf_of"]})
    R.append({"k": "actor", "id": "att", "kind": "attacker", "name": d["attack_type"], "ev": "O", "by": "config",
              "src": [L("a0", "/attack_type")]})
    R.append({"k": "actor", "id": "def0", "kind": "defense", "name": "rope", "ev": "I", "rule": ["rope.guard_active_in_main_tree@1"],
              "src": [L("a0", o="/path")], "unk": {"/version": "not_recorded", "/code": "not_recorded"}})
    R.append({"k": "actor", "id": "harness", "kind": "harness", "name": "agentdojo (AutoDojo fork vendored in ROPE)",
              "ev": "I", "rule": ["rope.harness_is_vendored_autodojo@1"], "src": [L("a0", "/agentdojo_package_version")],
              "unk": {"/version": "ambiguous", "/code": "not_recorded"}})
    ts = d["evaluation_timestamp"]
    # C.8.5 / D.6.5 Step 3: unverified producing code -> the I twin agentdojo.naive_local_timestamp_unverified@1
    R.append({"k": "scope", "id": "run", "kind": "run", "actor": "agent",
              "t": {"start_naive": ts.replace(" ", "T"), "dur_s": d["duration"], "dur_clock": "wall", "raw": {"start": ts}},
              "ev": "O", "by": "source", "evf": {"/t/start_naive": "I"},
              "rule": ["agentdojo.naive_local_timestamp_unverified@1#/t/start_naive"],
              "src": [L("a0", "/evaluation_timestamp"), L("a0", "/duration")],
              "unk": {"/t/start": "ambiguous", "/t/end": "not_recorded", "/status": "not_recorded"}})
    R.append({"k": "scope", "id": "att0", "kind": "attempt", "parent": "run", "actor": "agent", "scored": True,
              "ev": "D", "rule": ["agentdojo.log_holds_last_pass@1"], "unk": {"/index": "lost"}})
    vec, payload = next(iter(d["injections"].items()))
    R.append({"k": "fixture", "id": "fx0", "kind": "injection_payload", "vector": vec, "content": payload, "actor": "att",
              "ev": "O", "by": "benchmark", "evf": {"/actor": "I"},
              "rule": ["agentdojo.payload_attributed_to_attacker@1#/actor"],
              "src": [L("a0", f"/injections/{vec}")]})
    R.append({"k": "message", "id": "m0", "scope": "att0", "role": "system", "actor": "bench", "parts": text_parts(msgs[0]["content"]),
              "ev": "O", "by": "source", "evf": {"/actor": "D"}, "rule": ["agentdojo.system_prompt_from_harness@1#/actor"],
              "src": [L("a0", "/messages/0")]})
    R.append({"k": "message", "id": "m1", "scope": "att0", "role": "user", "actor": "user", "parts": text_parts(msgs[1]["content"]),
              "after": [{"id": "m0", "b": "pos"}], "ev": "O", "by": "source", "evf": {"/actor": "D", "/after": "D"},
              "rule": ["agentdojo.user_is_simulated@1#/actor", "agentdojo.messages_append_ordered@1#/after"],
              "src": [L("a0", "/messages/1")]})
    cu = ["agentdojo.assistant_msg_has_one_call@1", "agentdojo.messages_append_ordered@1#/after", "agentdojo.context_is_prefix@1#/input"]
    unk_mc = {"/request": "not_recorded", "/response": "not_recorded", "/usage": "not_recorded", "/finish_reason": "not_recorded",
              "/tools": "not_recorded", "/params": "not_recorded", "/t": "not_recorded"}
    R.append({"k": "model_call", "id": "mc0", "actor": "agent", "role": "agent", "scope": "att0", "input": ["m0", "m1"], "status": "kept",
              "after": [{"id": "m1", "b": "pos"}], "ev": "D", "evf": {"/input": "I"}, "rule": cu, "unk": dict(unk_mc)})
    tc = msgs[2]["tool_calls"][0]
    R.append({"k": "message", "id": "m2", "scope": "att0", "role": "assistant", "actor": "agent", "generated_by": "mc0",
              "parts": text_parts(msgs[2]["content"]) + [{"t": "tool_call", "name": tc["function"], "args": tc["args"],
                                                         "provider_call_id": tc["id"]}],
              "after": [{"id": "mc0", "b": "causal"}], "ev": "O", "by": "source", "evf": {"/generated_by": "D", "/after": "D"},
              "rule": ["agentdojo.assistant_msg_has_one_call@1#/generated_by", "aer.output_after_generator@1#/after"],
              "src": [L("a0", "/messages/2")], "unk": {"/parts/1/args_raw": "not_recorded"}})
    tm = msgs[3]
    # D.6.6: a denial is a decision only (no tool_execution); ext.rope.query_echo in {none, query}
    R.append({"k": "decision", "id": "dc0", "actor": "def0", "scope": "att0", "subject": "m2#1", "verdict": "deny",
              "after": [{"id": "m2", "b": "causal"}],
              "ev": "I", "rule": ["rope.denial_error_pattern@1", "aer.decision_after_subject@1#/after"],
              "src": [L("a0", "/messages/3/error"), L("a0", "/messages/3/tool_call")], "unk": {"/reason": "not_recorded", "/t": "not_recorded"},
              "ext": {"rope": {"query_echo": "query"}}})
    R.append({"k": "message", "id": "m3", "scope": "att0", "role": "tool", "actor": "def0", "generated_by": "dc0",
              "parts": [{"t": "tool_result", "responds_to": "m2#1", "text": tm["content"][0]["content"], "error": tm["error"]}],
              "after": [{"id": "dc0", "b": "causal"}],
              "ev": "O", "by": "source", "evf": {"/actor": "I", "/generated_by": "I", "/parts/0/responds_to": "D", "/after": "I"},
              "rule": ["rope.denial_error_pattern@1#/actor", "rope.denial_error_pattern@1#/generated_by",
                       "agentdojo.call_id_unique_match@1#/parts/0/responds_to", "aer.output_after_generator@1#/after"],
              "src": [L("a0", "/messages/3")]})
    R.append({"k": "model_call", "id": "mc1", "actor": "agent", "role": "agent", "scope": "att0", "input": ["m0", "m1", "m2", "m3"],
              "status": "kept", "after": [{"id": "m3", "b": "pos"}], "ev": "D", "evf": {"/input": "I"}, "rule": cu, "unk": dict(unk_mc)})
    R.append({"k": "message", "id": "m4", "scope": "att0", "role": "assistant", "actor": "agent", "generated_by": "mc1",
              "parts": text_parts(msgs[4]["content"]), "after": [{"id": "mc1", "b": "causal"}],
              "ev": "O", "by": "source", "evf": {"/generated_by": "D", "/after": "D"},
              "rule": ["agentdojo.assistant_msg_has_one_call@1#/generated_by", "aer.output_after_generator@1#/after"],
              "src": [L("a0", "/messages/4")]})
    for jid, name in (("j0", "utility"), ("j1", "security")):
        R.append({"k": "judgement", "id": jid, "actor": "bench", "subject": "run", "name": name, "value": d[name],
                  "origin": "checker", "ev": "O", "by": "benchmark", "evf": {"/origin": "D"},
                  "rule": ["agentdojo.checker_outcome@1#/origin", "agentdojo.checker_inputs_unverified@1#/inputs"],
                  "src": [L("a0", f"/{name}"), L("a0", "/error")], "unk": {"/inputs": "not_recorded"}})
    seal_body = {
        "accounting": {
            "status": "unverifiable",
            "checks": [
                {"id": "aer.acc.agent_calls_vs_assistant@1", "scope": "att0", "verdict": "unverifiable",
                 "reason": "model_calls_derived_from_messages", "observed": {"assistant_messages": 2, "model_calls": 2}},
                {"id": "aer.acc.tool_calls_dispatched@1", "scope": "att0", "verdict": "consistent",
                 "observed": {"tool_calls": 1, "tool_executions": 0, "denied": 1, "unexecuted": 0}},
                {"id": "aer.acc.tool_results_linked@1", "scope": "att0", "verdict": "consistent",
                 "observed": {"tool_results": 1, "linked": 1}},
                {"id": "aer.acc.assistant_generated_by@1", "scope": "att0", "verdict": "consistent",
                 "observed": {"assistant_messages": 2, "with_generated_by": 2}},
            ],
        },
        "issues": [
            {"code": "earlier_attempts_unobservable", "ids": ["att0"], "rule": "agentdojo.log_holds_last_pass@1"},
            {"code": "identity_conflict", "ids": ["agent"], "rule": "rope.model_dir_identity@1"},
        ],
    }
    unverifiable_issue(seal_body)
    return write("rope_denial_qwen_autodojo", R, seal_body, {"a0": raw}), R


# =====================================================================================
# Known-answer vectors of C.4.1 / K.5.2
# =====================================================================================
def kats():
    a1 = INV / "samples/agentdojo/gpt-4o-2024-05-13-transformers_pi_detector__banking__user_task_13__important_instructions__injection_task_7.json"
    a4 = INV / "samples/agent-security-tools-survey/agentharm_inspect__gptoss_benign__sample_42-1_epoch_1.json"
    h1, h4 = sha256_hex(a1.read_bytes()), sha256_hex(a4.read_bytes())
    rows = [("agentdojo.tracelogger/agentdojo-upstream", h1, {"p": ""}),
            ("agentdojo.tracelogger/agentdojo-upstream", h1, {}),
            ("agentdojo.tracelogger/agentdojo-upstream", h1, {"line": 0}),
            ("inspect.eval/survey-agentharm", h4, {"p": ""})]
    for n, (mid, h, loc) in enumerate(rows, 1):
        print(f"KAT {n}: {mid} {jcs(loc).decode()} preimage {sha256_hex(ex_preimage(mid, h, loc))} -> {ex_id(mid, h, loc)}")
    print("superseded mapping id agentdojo.tracelogger ->", ex_id("agentdojo.tracelogger", h1, {"p": ""}))


if __name__ == "__main__":
    kats()
    ex_agentdojo()
    ex_v1()
    ex_stac()
    ex_rope()
