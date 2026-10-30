"""One test per row of the D.9.2 mapping table, on synthetic band-shaped logs built in code (D.9.4; K.6.4).

Each synthetic log is a real ``.eval`` zip (members Zstandard, method 93) that goes through the whole pipeline: raw
store, the versioned ``expand`` stage, the reader's plan, the mapper and the writer; every AER is then validated in
release mode against the store and derived to PROV (``agentprov-prov/0.1``) and checked by tier 4. Every test asserts the
rule id of its row. The constructs the band lacks (cached and error calls, approvals, compaction, branch, truncation,
sub-agent spans, sandbox and store events, score edits, dangling references) exist only here: they are never claimed
as observed (D.9.0).
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

import inspect_support as support
from agentprov.adapters.inspect.mapper import tool_status
from agentprov.aer.reader import load_aer
from agentprov.prov.engine import derive
from agentprov.validate import validate_prov

GEN = "SpanGenerate0000000000"
SCORER = "SpanScorer000000000000"


def run(tmp_path: Path, sample: dict[str, Any], *, prov: bool = True) -> support.Unit:
    """Import one synthetic sample; assert it validates and (by default) derives and passes tier 4."""
    data = support.build_eval(support.synthetic_header(), {"s1_epoch_1.json": sample})
    imported = support.import_log(data, tmp_path / "raw")
    assert imported.register == [] and len(imported.units) == 1
    unit = imported.units[0]
    assert not unit.outcome.degenerate, unit.outcome.error_code
    report = imported.validate(unit)
    assert report.ok, sorted({(f.code, f.pointer) for f in report.errors})
    if prov:
        path = tmp_path / "x.aer.jsonl"
        path.write_bytes(unit.data)
        doc = load_aer(path)
        result = validate_prov(derive(doc).prov_json, doc)
        assert result.ok, [(o.id, sorted(o.codes())) for o in result.outcomes if o.status == "fail"]
    return unit


def cites(record: dict[str, Any], rule: str) -> bool:
    return any(r.split("#", 1)[0] == rule for r in record.get("rule", []))


def issue_rules(unit: support.Unit) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for i in unit.info.issues:
        out.setdefault(str(i["code"]), []).append(str(i["rule"]))
    return out


def gen_events(sample: dict[str, Any]) -> list[dict[str, Any]]:
    return [e for e in sample["events"] if e.get("span_id") == GEN]


def first(sample: dict[str, Any], kind: str, span: str | None = None) -> dict[str, Any]:
    return next(e for e in sample["events"] if e["event"] == kind and (span is None or e.get("span_id") == span))


# ------------------------------------------------------------------------------------------------ header and fixtures
def test_row_header(tmp_path):
    u = run(tmp_path, support.basic_sample())
    h = u.header
    assert h["dialect"] == {"id": "inspect.eval", "variant": "v2"} and h["unit"] == "agent_execution"
    assert h["task"] == {"benchmark": "agentharm", "suite": "inspect_evals/agentharm_benign", "task_id": "s1", "attack_id": None}
    assert cites(h, "inspect.header_applies_to_samples@1") and h["evf"]["/task/benchmark"] == "D"
    assert [a["role"] for a in h["artifacts"]] == ["primary", "supporting"]
    assert {a["origin"]["label"] for a in h["artifacts"]} == {"samples/s1_epoch_1.json", "header.json"}
    assert {"run_id", "eval_id", "task_args", "epoch", "uuid"} <= set(h["ext"]["inspect"])
    actors = {r["id"]: r for r in u.of_kind("actor")}
    assert actors["harness"]["code"] == {"dist": "inspect_ai", "dist_version": "0.3.247.dev69+g53c1fa98b"}
    assert actors["agent"]["model"] == {"requested": "ollama/synthetic-agent:1b"}
    assert actors["agent"]["params"] == {"max_connections": 1}
    bench = actors["bench"]
    assert bench["code"]["repo"].endswith("inspect_evals.git") and bench["unk"]["/code/commit"] == "ambiguous"
    assert cites(bench, "inspect.header_applies_to_samples@1")


def test_row_fixtures(tmp_path):
    u = run(tmp_path, support.basic_sample())
    fixtures = {r["kind"]: r for r in u.of_kind("fixture")}
    assert set(fixtures) == {"task_prompt", "tool_definitions", "ground_truth"}
    assert fixtures["task_prompt"]["content"] == "Synthetic task prompt."
    assert fixtures["ground_truth"]["content"] == {"target_functions": ["get_x"], "grading_function": "grade_x"}
    assert all(cites(f, "inspect.sample_init_fixtures@1") for f in fixtures.values())
    agent_calls = [r for r in u.of_kind("model_call") if r["role"] == "agent"]
    assert {c.get("tools") for c in agent_calls} == {fixtures["tool_definitions"]["id"]}
    assert "category" in u.header["ext"]["inspect"]["sample_metadata"]


# ------------------------------------------------------------------------------------------------ spans
def test_row_spans(tmp_path):
    u = run(tmp_path, support.basic_sample())
    scopes = {r["ext"]["inspect"]["span"]["name"]: r for r in u.of_kind("scope") if r["id"] != "run"}
    assert scopes["generate"]["kind"] == "agent_invocation" and scopes["generate"]["actor"] == "agent"
    assert scopes["combined_scorer"]["kind"] == "other" and scopes["combined_scorer"]["subtype"] == "inspect.scorer"
    assert scopes["init"]["subtype"] == "inspect.span" and scopes["init"]["parent"] == "run"
    assert scopes["generate"]["parent"] == scopes["solvers"]["id"]
    assert all(cites(s, "inspect.span_is_scope@1") for s in scopes.values())
    assert all("start" in s["t"] and "end" in s["t"] for s in scopes.values())


def test_row_subagent(tmp_path):
    def tune(s: support.Sample, sample: dict[str, Any]) -> None:
        tool = first(sample, "tool")
        tool["agent"] = "researcher"
        tool["agent_span_id"] = "SpanSubAgent0000000000"
        sample["events"].append({"uuid": "E-sub-begin", "span_id": "SpanSubAgent0000000000", "timestamp": support.ts(4.9),
                                 "working_start": 4.9, "event": "span_begin", "id": "SpanSubAgent0000000000",
                                 "parent_id": GEN, "type": "agent", "name": "researcher"})
        sample["events"].append({"uuid": "E-sub-end", "span_id": "SpanSubAgent0000000000", "timestamp": support.ts(4.95),
                                 "working_start": 4.95, "event": "span_end", "id": "SpanSubAgent0000000000"})

    u = run(tmp_path, support.basic_sample(tune=tune))
    sub = next(r for r in u.of_kind("scope") if r.get("kind") == "subagent")
    te = u.of_kind("tool_execution")[0]
    assert sub["spawned_by"] == te["id"] and cites(sub, "inspect.agent_span_is_subagent@1")
    ids = [r["id"] for r in u.records]
    assert ids.index(te["id"]) < ids.index(sub["id"])  # backward-only reference (C.5.2)


# ------------------------------------------------------------------------------------------------ messages
def test_row_message_parts(tmp_path):
    def tune(s: support.Sample, sample: dict[str, Any]) -> None:
        a2 = sample["messages"][4]
        a2["content"] = [
            {"type": "reasoning", "reasoning": "Synthetic thought.", "signature": "sig-1", "redacted": True},
            {"type": "text", "text": "Answer."},
            {"type": "image", "image": "https://example.invalid/synthetic.png", "detail": "auto"},
            {"type": "data", "data": {"k": 1}},
            {"type": "tool_use", "tool_type": "web_search", "id": "tu1", "name": "search", "arguments": "{}"},
            {"type": "audio", "audio": "https://example.invalid/a.mp3", "format": "mp3"},
            {"type": "synthetic_unknown", "payload": "kept verbatim"},
        ]
        for pooled in [m for e in sample["events"] if e["event"] == "model"
                       for m in [c["message"] for c in e["output"]["choices"]] if m["id"] == a2["id"]]:
            pooled["content"] = copy.deepcopy(a2["content"])

    u = run(tmp_path, support.basic_sample(tune=tune))
    msg = next(m for m in u.of_kind("message") if m["role"] == "assistant" and len(m["parts"]) == 7)
    # audio is a uri part like image since regeneration-batch item 25 (b); an unknown type stays an other part
    assert [p["t"] for p in msg["parts"]] == ["reasoning", "text", "uri", "other", "other", "uri", "other"]
    assert msg["parts"][0] == {"t": "reasoning", "text": "Synthetic thought.", "signature": "sig-1", "redacted": True}
    assert [p.get("type") for p in msg["parts"][3:]] == ["inspect.content_data", "inspect.tool_use", None, "synthetic_unknown"]
    assert msg["parts"][5]["uri"] == "https://example.invalid/a.mp3"
    assert issue_rules(u)["inspect.unknown_content_type"] == ["inspect.message_content_parts@1"]
    empty = next(m for m in u.of_kind("message") if m["role"] == "assistant" and any(p.get("t") == "tool_call" for p in m["parts"]))
    assert empty["unk"]["/parts/1/text"] == "ambiguous" and cites(empty, "inspect.message_content_parts@1")


# ------------------------------------------------------------------------------------------------ model events
def test_row_model_call_agent(tmp_path):
    u = run(tmp_path, support.basic_sample())
    by_id = u.by_id()
    calls = [r for r in u.of_kind("model_call") if r["role"] == "agent"]
    assert len(calls) == 2 and all(cites(c, "inspect.model_event_is_call@1") for c in calls)
    first_call, second = calls
    assert first_call["input"] == ["m0", "m1"] and second["input"] == ["m0", "m1", "m2", "m3"]
    assert first_call["status"] == "kept" and first_call["finish_reason"] == "tool_calls"
    assert first_call["usage"] == {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
    assert first_call["params"]["configured"] == {"temperature": 0, "max_tokens": 64}
    assert first_call["t"]["start"].endswith("Z") and first_call["t"]["end"].endswith("Z")
    assert by_id["m2"]["generated_by"] == first_call["id"] and by_id["m4"]["generated_by"] == second["id"]
    agent_checks = [c for c in u.info.accounting.checks if c["id"] == "aer.acc.agent_calls_vs_assistant@1"]
    assert agent_checks and all(c["verdict"] == "consistent" for c in agent_checks)


def test_row_model_call_judge(tmp_path):
    u = run(tmp_path, support.basic_sample())
    scorer = next(r for r in u.of_kind("scope") if r.get("subtype") == "inspect.scorer")
    judge = next(r for r in u.of_kind("model_call") if r["role"] == "auxiliary")
    assert judge["actor"] == "judge0" and judge["scope"] == scorer["id"]
    assert cites(judge, "inspect.span_is_scope@1") and u.by_id()["judge0"]["kind"] == "judge"
    assert judge["input"] == ["p0"] and u.by_id()["p0"]["scope"] == scorer["id"]
    out = next(m for m in u.of_kind("message") if m.get("generated_by") == judge["id"])
    assert out["actor"] == "judge0" and out["scope"] == scorer["id"]
    assert not any(c["scope"] == scorer["id"] for c in u.info.accounting.checks)  # auxiliary: recorded, not reconciled


def test_row_cache_read(tmp_path):
    def tune(s: support.Sample, sample: dict[str, Any]) -> None:
        first(sample, "model", GEN)["cache"] = "read"

    u = run(tmp_path, support.basic_sample(tune=tune))
    cached = next(r for r in u.of_kind("model_call") if r["status"] == "cached")
    assert cites(cached, "inspect.cache_read@1") and cached["evf"]["/status"] == "D"


def test_row_model_error(tmp_path):
    def tune(s: support.Sample, sample: dict[str, Any]) -> None:
        judge = first(sample, "model", SCORER)
        judge["output"]["choices"] = []
        judge["error"] = "Synthetic provider failure."
        judge["retries"] = 2
        sample["events"] = [e for e in sample["events"] if e["event"] != "score"]
        sample["scores"] = {}

    u = run(tmp_path, support.basic_sample(tune=tune))
    failed = next(r for r in u.of_kind("model_call") if r["status"] == "error")
    assert cites(failed, "inspect.model_error@1") and failed["unk"]["/reason"] == "not_recorded"
    assert failed["ext"]["inspect"]["retries"] == 2
    assert not [m for m in u.of_kind("message") if m.get("generated_by") == failed["id"]]


# ------------------------------------------------------------------------------------------------ tool events
def test_row_tool_execution(tmp_path):
    u = run(tmp_path, support.basic_sample())
    te = u.of_kind("tool_execution")[0]
    assert te["call"] == "m2#2" and te["name"] == "get_x" and te["args"] == {"q": "a", "n": 2} and te["status"] == "ok"
    assert cites(te, "inspect.tool_event_is_execution@1") and cites(te, "inspect.tool_call_id_match@1")
    assert {"b": "causal", "id": "m2"} in te["after"]
    result = u.by_id()["m3"]
    assert result["generated_by"] == te["id"] and result["parts"][0]["responds_to"] == "m2#2"
    assert cites(result, "inspect.tool_call_id_match@1")


@pytest.mark.parametrize(("kind", "status"), [("parsing", "invalid"), ("file_not_found", "error"), ("timeout", "error"),
                                               ("sandbox_unavailable", "error"), ("not_in_any_table", "error")])
def test_row_tool_error_status(tmp_path, kind, status):
    u = run(tmp_path, support.basic_sample(tool_error={"type": kind, "message": "Synthetic error."}), prov=kind == "parsing")
    te = u.of_kind("tool_execution")[0]
    assert te["status"] == status and cites(te, "inspect.tool_error_status@1")
    assert u.by_id()["m3"]["parts"][0]["error"] == "Synthetic error."
    assert tool_status(None) == "ok" and tool_status({"type": "approval", "message": ""}) is None


def _approval(sample: dict[str, Any], decision: str, approver: str = "human", **extra: Any) -> dict[str, Any]:
    tool = first(sample, "tool")
    call = sample["messages"][2]["tool_calls"][0]
    event = {"uuid": "E-approval", "span_id": GEN, "timestamp": support.ts(4.6), "working_start": 4.6, "event": "approval",
             "message": "Synthetic approval request.", "call": copy.deepcopy(call), "approver": approver, "decision": decision,
             "explanation": "Synthetic reason.", **extra}
    sample["events"].insert(sample["events"].index(tool), event)
    return tool


def test_row_approval_approve(tmp_path):
    u = run(tmp_path, support.basic_sample(tune=lambda s, x: _approval(x, "approve")))
    dc = u.of_kind("decision")[0]
    te = u.of_kind("tool_execution")[0]
    assert dc["verdict"] == "allow" and dc["actor"] == "user" and dc["subject"] == "m2#2" and dc["reason"] == "Synthetic reason."
    assert te["authorised_by"] == dc["id"] and cites(dc, "inspect.approval_decision@1")
    assert u.by_id()["user"]["kind"] == "user"


def test_row_approval_modify(tmp_path):
    def tune(s: support.Sample, sample: dict[str, Any]) -> None:
        _approval(sample, "modify", approver="policy", modified={"id": "call_synthetic_1", "function": "get_x",
                                                                 "arguments": {"q": "b", "n": 2}, "type": "function"})

    u = run(tmp_path, support.basic_sample(tune=tune))
    dc = u.of_kind("decision")[0]
    assert dc["verdict"] == "modify" and dc["actor"] == "harness" and dc["ext"]["inspect"]["modified"]["arguments"]["q"] == "b"
    assert u.of_kind("tool_execution")[0]["authorised_by"] == dc["id"]


def test_row_approval_reject(tmp_path):
    def tune(s: support.Sample, sample: dict[str, Any]) -> None:
        tool = _approval(sample, "reject")
        error = {"type": "approval", "message": "Synthetic rejection."}
        tool["error"] = error
        sample["messages"][3]["error"] = error
        for m in sample["events_data"]["messages"]:
            if m["id"] == sample["messages"][3]["id"]:
                m["error"] = error

    u = run(tmp_path, support.basic_sample(tune=tune))
    assert u.of_kind("tool_execution") == []
    dc = u.of_kind("decision")[0]
    assert dc["verdict"] == "deny" and dc["subject"] == "m2#2"
    msg = u.by_id()["m3"]
    assert msg["generated_by"] == dc["id"] and cites(msg, "inspect.tool_error_status@1")
    dispatched = next(c for c in u.info.accounting.checks if c["id"] == "aer.acc.tool_calls_dispatched@1")
    assert dispatched["observed"]["denied"] == 1 and dispatched["verdict"] == "consistent"


def test_row_truncated(tmp_path):
    u = run(tmp_path, support.basic_sample(tune=lambda s, x: first(x, "tool").__setitem__("truncated", [4096, 1024])))
    te = u.of_kind("tool_execution")[0]
    dc = u.of_kind("decision")[0]
    assert dc["subject"] == te["id"] and dc["verdict"] == "modify" and dc["actor"] == "harness"
    assert dc["unk"]["/original"] == "overwritten" and cites(dc, "inspect.tool_output_truncated@1")
    assert u.by_id()["m3"]["generated_by"] == dc["id"]
    have = next(c for c in u.info.accounting.checks if c["id"] == "aer.acc.executions_have_results@1")
    assert have["verdict"] == "consistent"


# ------------------------------------------------------------------------------------------------ compaction and branch
def _compaction_span(sample: dict[str, Any], *, with_call: bool) -> None:
    span = "SpanCompact00000000000"
    events = [
        {"uuid": "E-c0", "span_id": span, "timestamp": support.ts(6.5), "working_start": 6.5, "event": "span_begin",
         "id": span, "parent_id": GEN, "type": "compaction", "name": "compaction"},
        {"uuid": "E-c1", "span_id": span, "timestamp": support.ts(6.9), "working_start": 6.9, "event": "compaction",
         "type": "summary", "tokens_before": 100, "tokens_after": 10, "source": "auto"},
        {"uuid": "E-c2", "span_id": span, "timestamp": support.ts(7.0), "working_start": 7.0, "event": "span_end", "id": span},
    ]
    if with_call:
        call = copy.deepcopy(first(sample, "model", GEN))
        call["span_id"] = span
        call["uuid"] = "E-cm"
        call["timestamp"], call["completed"] = support.ts(6.6), support.ts(6.8)
        summary = {"id": "MSummary00000000000000", "role": "assistant", "content": "Synthetic summary.", "source": "generate"}
        call["output"]["choices"] = [{"message": summary, "stop_reason": "stop"}]
        events.insert(1, call)
    sample["events"].extend(events)


def test_row_compaction_with_call(tmp_path):
    u = run(tmp_path, support.basic_sample(tune=lambda s, x: _compaction_span(x, with_call=True)))
    summariser = next(r for r in u.of_kind("model_call") if cites(r, "inspect.compaction@1"))
    summary = next(m for m in u.of_kind("message") if m.get("generated_by") == summariser["id"])
    assert summary["parts"] == [{"t": "text", "text": "Synthetic summary."}]
    assert "compaction" in summariser["ext"]["inspect"] and "inspect.compaction_unmodelled" not in issue_rules(u)


def test_row_compaction_without_call(tmp_path):
    u = run(tmp_path, support.basic_sample(tune=lambda s, x: _compaction_span(x, with_call=False)))
    assert issue_rules(u)["inspect.compaction_unmodelled"] == ["inspect.compaction@1"]
    host = next(r for r in u.of_kind("scope") if "compaction" in r.get("ext", {}).get("inspect", {}))
    assert host["ext"]["inspect"]["span"]["type"] == "compaction"


def test_row_branch(tmp_path):
    def tune(s: support.Sample, sample: dict[str, Any]) -> None:
        sample["events"].append({"uuid": "E-b", "span_id": GEN, "timestamp": support.ts(6.0), "working_start": 6.0,
                                 "event": "branch", "from_anchor": "anchor-1"})

    u = run(tmp_path, support.basic_sample(tune=tune))
    assert issue_rules(u)["inspect.branch_unsupported"] == ["inspect.event_kept_in_ext@1"]
    gen = next(r for r in u.of_kind("scope") if r.get("kind") == "agent_invocation")
    assert gen["ext"]["inspect"]["events"][0]["event"]["event"] == "branch"


# ------------------------------------------------------------------------------------------------ state and sandbox
def test_row_state(tmp_path):
    def tune(s: support.Sample, sample: dict[str, Any]) -> None:
        sample["events"].insert(0, {"uuid": "E-s0", "span_id": None, "timestamp": support.ts(1.2), "working_start": 1.2,
                                    "event": "state", "changes": [{"op": "add", "path": "/tools/0", "value": {"name": "get_x"}}]})

    u = run(tmp_path, support.basic_sample(tune=tune))
    states = u.of_kind("state_change")
    assert [s["subtype"] for s in states] == ["inspect.task_state"] * 2 and all(cites(s, "inspect.state_event@1") for s in states)
    assert states[1]["after"] == [{"b": "proto", "id": states[0]["id"]}]
    assert states[1]["cause"] == states[1]["scope"] and states[1]["patch"][0]["op"] == "add"
    assert "cause" not in states[0]  # outside any span: no solver to cause it


def test_row_store(tmp_path):
    def tune(s: support.Sample, sample: dict[str, Any]) -> None:
        sample["events"].append({"uuid": "E-st", "span_id": GEN, "timestamp": support.ts(5.5), "working_start": 5.5,
                                 "event": "store", "changes": [{"op": "add", "path": "/memo", "value": "x"}]})

    u = run(tmp_path, support.basic_sample(tune=tune))
    store = next(s for s in u.of_kind("state_change") if s["target"] == "agent_store")
    assert "subtype" not in store and store["patch"] == [{"op": "add", "path": "/memo", "value": "x"}]
    assert cites(store, "inspect.state_event@1")


def test_row_sandbox(tmp_path):
    def tune(s: support.Sample, sample: dict[str, Any]) -> None:
        sample["events"].append({"uuid": "E-sb", "span_id": GEN, "timestamp": support.ts(5.6), "working_start": 5.6,
                                 "event": "sandbox", "action": "exec", "cmd": "echo synthetic", "result": 0,
                                 "output": "synthetic\n", "completed": support.ts(5.7)})

    u = run(tmp_path, support.basic_sample(tune=tune))
    activity = u.of_kind("activity")[0]
    artefact = u.of_kind("artefact")[0]
    assert activity["type"] == "inspect:sandbox_exec" and activity["status"] == "ok" and activity["unk"]["/inputs"] == "not_recorded"
    assert artefact["type"] == "inspect:sandbox_output" and artefact["generated_by"] == activity["id"]
    assert artefact["content"] == "synthetic\n" and cites(activity, "inspect.sandbox_activity@1")


# ------------------------------------------------------------------------------------------------ scores
def test_row_score(tmp_path):
    u = run(tmp_path, support.basic_sample())
    judgements = u.of_kind("judgement")
    assert [j["name"] for j in judgements] == ["combined_scorer.score", "combined_scorer.refusal"]
    judge_call = next(r for r in u.of_kind("model_call") if r["role"] == "auxiliary")
    for j in judgements:
        assert j["origin"] == "checker" and j["actor"] == "judge0" and j["generated_by"] == judge_call["id"]
        assert j["unk"]["/inputs"] == "not_recorded" and cites(j, "inspect.score_event@1")
        assert {"a": "a0", "p": f"/scores/combined_scorer/value/{j['name'].split('.')[1]}"} in j["src"]


def test_row_score_edit(tmp_path):
    def tune(s: support.Sample, sample: dict[str, Any]) -> None:
        sample["events"].append({"uuid": "E-se", "span_id": None, "timestamp": support.ts(30.0), "working_start": 30.0,
                                 "event": "score_edit", "score_name": "combined_scorer",
                                 "edit": {"value": {"score": 0.5}, "explanation": "Synthetic correction.",
                                          "provenance": {"author": "synthetic"}}})

    u = run(tmp_path, support.basic_sample(tune=tune))
    edited = next(j for j in u.of_kind("judgement") if j["origin"] == "recomputed")
    original = next(j for j in u.of_kind("judgement") if j["name"] == "combined_scorer.score" and j["origin"] == "checker")
    assert edited["revises"] == original["id"] and edited["value"] == 0.5 and cites(edited, "inspect.score_event@1")


# ------------------------------------------------------------------------------------------------ limits, unmapped, order
def test_row_sample_limit(tmp_path):
    def tune(s: support.Sample, sample: dict[str, Any]) -> None:
        sample["events"].append({"uuid": "E-l", "span_id": GEN, "timestamp": support.ts(6.0), "working_start": 6.0,
                                 "event": "sample_limit", "type": "message", "message": "Synthetic limit.", "limit": 20.0})
        sample["limit"] = {"type": "message", "limit": 20}

    u = run(tmp_path, support.basic_sample(tune=tune))
    run_scope = u.by_id()["run"]
    assert run_scope["status"] == "limit" and cites(run_scope, "inspect.sample_limit@1")
    assert issue_rules(u)["inspect.sample_limit"] == ["inspect.sample_limit@1"]
    assert next(i for i in u.info.issues if i["code"] == "inspect.sample_limit")["ids"] == ["run"]


def test_row_unmapped_events(tmp_path):
    def tune(s: support.Sample, sample: dict[str, Any]) -> None:
        for kind, fields in (("info", {"data": "Synthetic note."}),
                             ("logger", {"message": {"level": "info", "message": "Synthetic log.", "created": 1.0}}),
                             ("error", {"error": {"message": "Synthetic error.", "traceback": "", "traceback_ansi": ""}})):
            sample["events"].append({"uuid": f"E-{kind}", "span_id": SCORER, "timestamp": support.ts(8.0),
                                     "working_start": 8.0, "event": kind, **fields})

    u = run(tmp_path, support.basic_sample(tune=tune))
    scorer = next(r for r in u.of_kind("scope") if r.get("subtype") == "inspect.scorer")
    assert [e["event"]["event"] for e in scorer["ext"]["inspect"]["events"]] == ["info", "logger", "error"]
    unmapped = [i for i in u.info.issues if i["code"] == "inspect.unmapped_event"]
    assert [i["detail"] for i in unmapped] == ["logger", "error"]  # info is observed in the band: no issue
    assert all(i["rule"] == "inspect.event_kept_in_ext@1" for i in unmapped)
    assert u.by_id()["run"]["status"] == "error"


def test_row_event_order(tmp_path):
    def tune(s: support.Sample, sample: dict[str, Any]) -> None:
        # the band's quirk: a tool event precedes the begin of its own tool span in the list, and list order is shuffled
        tool = first(sample, "tool")
        events = sample["events"]
        span = "SpanTool00000000000000"
        events.insert(events.index(tool) + 1, {"uuid": "E-tb", "span_id": span, "timestamp": support.ts(4.8),
                                               "working_start": 4.8, "event": "span_begin", "id": span, "parent_id": GEN,
                                               "type": "tool", "name": "get_x"})
        events.insert(events.index(tool) + 2, {"uuid": "E-te", "span_id": span, "timestamp": support.ts(4.85),
                                               "working_start": 4.85, "event": "span_end", "id": span})
        events.reverse()

    u = run(tmp_path, support.basic_sample(tune=tune))
    edges = [e for r in u.records for e in r.get("after", [])]
    assert edges and {e["b"] for e in edges} <= {"causal", "time", "proto"}  # never "pos"
    by_id = u.by_id()
    for r in u.records:
        for e in r.get("after", []):
            if e["b"] == "time":
                assert by_id[e["id"]]["t"]["end"] < r["t"]["start"] and cites(r, "aer.time_order@1")
    tool_span = next(r for r in u.of_kind("scope") if r["ext"]["inspect"].get("span", {}).get("type") == "tool")
    assert tool_span["subtype"] == "inspect.span"
    catalogue_rule = "inspect.no_order_from_event_list@1"
    assert catalogue_rule in {q for q in _quirk_rules()}


def _quirk_rules() -> set[str]:
    from agentprov.adapters.profiles import load_profile

    quirks = load_profile("survey-agentharm").family_table()["quirk"]
    return {r for q in quirks for r in q.get("rules", ())}


# ------------------------------------------------------------------------------------------------ references
def test_dangling_attachment_gives_dangling_source_ref_and_no_fabricated_input(tmp_path):
    def tune(s: support.Sample, sample: dict[str, Any]) -> None:
        pool = sample["events_data"]["messages"]
        judge_prompt = next(m for m in pool if m["content"] == "Synthetic judge prompt.")
        judge_prompt["content"] = "attachment://00000000000000000000000000000000"

    u = run(tmp_path, support.basic_sample(tune=tune))
    judge = next(r for r in u.of_kind("model_call") if r["role"] == "auxiliary")
    assert "input" not in judge and judge["unk"]["/input"] == "lost"
    assert not [m for m in u.of_kind("message") if m["role"] == "user" and m["scope"] != "run"]
    dangling = [i for i in u.info.issues if i["code"] == "dangling_source_ref"]
    assert dangling and dangling[0]["rule"] == "inspect.model_event_is_call@1" and dangling[0]["ids"] == [judge["id"]]


def test_dangling_input_refs_range_gives_dangling_source_ref(tmp_path):
    def tune(s: support.Sample, sample: dict[str, Any]) -> None:
        first(sample, "model", GEN)["input_refs"] = [[0, 99]]

    u = run(tmp_path, support.basic_sample(tune=tune))
    call = next(r for r in u.of_kind("model_call") if r["role"] == "agent")
    assert call["unk"]["/input"] == "lost" and "input" not in call
    assert "dangling_source_ref" in issue_rules(u)


def test_attachment_references_resolve_to_the_recorded_content(tmp_path):
    def tune(s: support.Sample, sample: dict[str, Any]) -> None:
        sample["attachments"]["0123456789abcdef0123456789abcdef"] = "Synthetic judge prompt."
        for m in sample["events_data"]["messages"]:
            if m["content"] == "Synthetic judge prompt.":
                m["content"] = "attachment://0123456789abcdef0123456789abcdef"

    u = run(tmp_path, support.basic_sample(tune=tune))
    prompt = u.by_id()["p0"]
    assert prompt["parts"] == [{"t": "text", "text": "Synthetic judge prompt."}]
    assert {"a": "a0", "p": "/attachments/0123456789abcdef0123456789abcdef"} in prompt["src"]


def test_dangling_tool_message_gives_missing_tool_result(tmp_path):
    def tune(s: support.Sample, sample: dict[str, Any]) -> None:
        first(sample, "tool")["message_id"] = "NotInTheSample00000000"

    u = run(tmp_path, support.basic_sample(tune=tune))
    te = u.of_kind("tool_execution")[0]
    codes = issue_rules(u)
    assert codes["missing_tool_result"] == ["inspect.tool_event_is_execution@1"] and "dangling_source_ref" in codes
    assert next(i for i in u.info.issues if i["code"] == "missing_tool_result")["ids"] == [te["id"]]
