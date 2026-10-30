"""Regeneration-batch item 12 (E2-b3, c3/c4) with U6-a and U6-b (D-374, D-375): the eval runner's spans and the sample's
run are associated with the harness, tool spans with the tool runtime; the sample input is attributed to the benchmark
(D on inspect_ai code at the producer 53c1fa98, its twin elsewhere), a plan-inserted system message too (class I); judge
actors declare their unlogged code and version, the bench actor takes the task's version label; a model call whose
request the transcript's retention policy dropped declares ``/params/transmitted`` lost. Synthetic samples only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import inspect_support as support
import pytest
from agentprov.adapters.inspect.mapper import producer_commit, verified_rule
from agentprov.adapters.profiles import SourceProfile, parse_profile
from agentprov.aer.reader import load_aer
from agentprov.aer.rules import RuleRegistry
from agentprov.aer.validate import AerValidator
from agentprov.prov.engine import derive
from agentprov.validate import validate_prov

REPO = Path(__file__).resolve().parents[3]
PROFILE = REPO / "src" / "agentprov" / "adapters" / "inspect" / "profiles" / "survey-agentharm.profile.toml"
PRODUCER = "0.3.247.dev69+g53c1fa98b"
HARNESS = "inspect.sample_run_by_harness@1"
INPUT = "inspect.sample_input_from_benchmark@1"
RETENTION = "inspect.model_api_call_retention@1"
PLAN_STEPS = [{"solver": "inspect_evals/system_prompt_based_on_model", "params": {}},
              {"solver": "prompt_template", "params": {"template": "\n\n{prompt}"}},
              {"solver": "generate", "params": {"tool_calls": "loop"}}]


def band_profile(producer: str) -> SourceProfile:
    text = PROFILE.read_text(encoding="utf-8")
    old = f'producer_band = {{ inspect_ai = ["{PRODUCER}"] }}'
    assert old in text
    return parse_profile(text.replace(old, f'producer_band = {{ inspect_ai = ["{producer}"] }}').encode("utf-8"),
                         source="test-variant")


def run(tmp_path: Path, sample: dict[str, Any], *, producer: str = PRODUCER, plan: bool = True,
        task_version: Any = 2) -> tuple[support.Unit, dict[str, Any]]:
    """Import one synthetic sample; it validates in release mode, derives and passes tier 4. Returns the PROV too."""
    used = band_profile(producer)
    header = support.synthetic_header(producer)
    header["eval"]["task_version"] = task_version
    if plan:
        header["plan"]["steps"] = PLAN_STEPS
    imported = support.import_log(support.build_eval(header, {"s1_epoch_1.json": sample}), tmp_path / "raw", profile=used)
    assert imported.register == [] and len(imported.units) == 1
    unit = imported.units[0]
    assert not unit.outcome.degenerate, unit.outcome.error_code
    assert not {i["code"] for i in unit.info.issues} & {"adapter_defect", "unparseable_artefact"}
    validator = AerValidator(store=imported.store, catalogues=RuleRegistry.default(), mode="release",
                             profile_digests={(used.id, used.version): used.sha256})
    for line in unit.data.splitlines(keepends=True):
        validator.feed(line)
    report = validator.finish()
    assert report.ok, sorted({(f.code, f.pointer) for f in report.errors})
    path = tmp_path / "x.aer.jsonl"
    path.write_bytes(unit.data)
    doc = load_aer(path)
    prov = derive(doc).prov_json
    result = validate_prov(prov, doc)
    assert result.ok, [(o.id, sorted(o.codes())) for o in result.outcomes if o.status == "fail"]
    return unit, json.loads(prov)


def rule_at(record: dict[str, Any], pointer: str) -> list[str]:
    return [r.split("#", 1)[0] for r in record.get("rule", []) if r.endswith("#" + pointer)]


def scope(unit: support.Unit, span_name: str) -> dict[str, Any]:
    return next(r for r in unit.of_kind("scope") if r.get("ext", {}).get("inspect", {}).get("span", {}).get("name") == span_name)


def associations(prov: dict[str, Any]) -> set[tuple[str, str]]:
    out = set()
    for bundle in prov["bundle"].values():
        for body in bundle.get("wasAssociatedWith", {}).values():
            out.add((body["prov:activity"], body.get("prov:agent")))
    return out


def tool_span_sample() -> dict[str, Any]:
    def tune(s: support.Sample, sample: dict[str, Any]) -> None:
        k = next(i for i, e in enumerate(sample["events"]) if e["event"] == "tool")
        span = {"uuid": s.uid("E"), "span_id": "SpanTool00000000000000", "timestamp": sample["events"][k]["timestamp"],
                "working_start": 1.0, "event": "span_begin", "id": "SpanTool00000000000000", "type": "tool",
                "name": "get_x", "parent_id": "SpanGenerate0000000000"}
        sample["events"][k]["span_id"] = "SpanTool00000000000000"
        end = {"uuid": s.uid("E"), "span_id": "SpanTool00000000000000", "timestamp": sample["events"][k]["completed"],
               "working_start": 1.0, "event": "span_end", "id": "SpanTool00000000000000"}
        sample["events"][k:k + 1] = [span, sample["events"][k], end]
    return support.basic_sample(tune=tune)


def test_producer_commit_and_the_twin_choice():
    assert producer_commit(PRODUCER) == "53c1fa98b" and producer_commit("0.3.130") is None
    assert producer_commit("0.3.134.dev31+geb46eef8") == "eb46eef8"
    assert verified_rule(HARNESS, PRODUCER) == HARNESS
    assert verified_rule(HARNESS, "0.3.130") == "inspect.sample_run_by_harness_unverified@1"
    assert verified_rule(HARNESS, "0.3.159.dev20+g3ddd7997") == "inspect.sample_run_by_harness_unverified@1"
    assert verified_rule("inspect.span_is_scope@1", "0.3.130") == "inspect.span_is_scope@1"  # older rules unchanged


def test_the_run_and_the_runners_spans_are_the_harness_and_tool_spans_the_runtime(tmp_path):
    u, prov = run(tmp_path, tool_span_sample())
    runs = next(r for r in u.of_kind("scope") if r["id"] == "run")
    assert runs["id"] == "run" and runs["actor"] == "harness" and runs["evf"]["/actor"] == "D"
    assert rule_at(runs, "/actor") == [HARNESS]
    for name in ("init", "solvers", "scorers", "combined_scorer"):
        rec = scope(u, name)
        assert rec["actor"] == "harness" and rule_at(rec, "/actor") == [HARNESS], name
    assert scope(u, "generate")["actor"] == "agent"  # an agent-role span keeps the agent (inspect.span_is_scope@1)
    tool = scope(u, "get_x")
    assert tool["actor"] == "env" and rule_at(tool, "/actor") == ["inspect.tool_span_by_runtime@1"]
    assoc = associations(prov)
    assert ("x:run", "x:harness") in assoc and ("x:" + tool["id"], "x:env") in assoc


def test_an_unverified_producer_cites_the_twins(tmp_path):
    u, _prov = run(tmp_path, support.basic_sample(), producer="0.3.130")
    runs = next(r for r in u.of_kind("scope") if r["id"] == "run")
    assert runs["evf"]["/actor"] == "I" and rule_at(runs, "/actor") == ["inspect.sample_run_by_harness_unverified@1"]
    user = next(m for m in u.of_kind("message") if m["role"] == "user" and m["scope"] == "run")
    assert user["actor"] == "bench" and user["evf"]["/actor"] == "I"
    assert rule_at(user, "/actor") == ["inspect.sample_input_from_benchmark_unverified@1"]


def test_the_sample_input_and_the_plan_system_message_are_the_benchmarks(tmp_path):
    u, prov = run(tmp_path, support.basic_sample())
    msgs = {m["role"] + ":" + m["scope"]: m for m in u.of_kind("message") if m["role"] in ("system", "user")}
    user, system = msgs["user:run"], msgs["system:run"]
    assert user["actor"] == "bench" and user["evf"]["/actor"] == "D" and rule_at(user, "/actor") == [INPUT]
    assert system["actor"] == "bench" and system["evf"]["/actor"] == "I"
    assert rule_at(system, "/actor") == ["inspect.system_message_from_task_plan@1"]
    judge_prompt = next(m for m in u.of_kind("message") if m["role"] == "user" and m["scope"] != "run")
    assert "actor" not in judge_prompt and judge_prompt["unk"]["/actor"] == "not_recorded"
    attributed = {(b["prov:entity"], b["prov:agent"]) for bundle in prov["bundle"].values()
                  for b in bundle.get("wasAttributedTo", {}).values()}
    assert ("x:" + user["id"], "x:bench") in attributed and ("x:" + system["id"], "x:bench") in attributed


def test_without_a_logged_plan_the_system_message_stays_unattributed(tmp_path):
    u, _prov = run(tmp_path, support.basic_sample(), plan=False)
    system = next(m for m in u.of_kind("message") if m["role"] == "system")
    assert "actor" not in system and system["unk"]["/actor"] == "not_recorded"


def test_judges_declare_code_and_version_and_bench_takes_the_task_version(tmp_path):
    u, _prov = run(tmp_path, support.basic_sample())
    judge = next(a for a in u.of_kind("actor") if a["kind"] == "judge")
    assert judge["unk"] == {"/code": "not_recorded", "/version": "not_recorded"}
    bench = next(a for a in u.of_kind("actor") if a["id"] == "bench")
    assert bench["version"] == "2" and bench["evf"]["/version"] == "D"
    assert rule_at(bench, "/version") == ["inspect.task_version_label@1"]
    assert "task_version" not in bench.get("ext", {}).get("inspect", {})


@pytest.mark.parametrize("task_version", [0, "0"])
def test_the_default_task_version_is_no_label(tmp_path, task_version):
    u, _prov = run(tmp_path, support.basic_sample(), task_version=task_version)
    bench = next(a for a in u.of_kind("actor") if a["id"] == "bench")
    assert "version" not in bench and bench["unk"]["/version"] == "not_recorded"


def test_a_request_dropped_by_the_retention_policy_is_lost(tmp_path):
    """Six agent calls: the first five keep ``call``, the sixth does not (``log/_transcript.py`` l. 617-637)."""
    def tune(s: support.Sample, sample: dict[str, Any]) -> None:
        events = sample["events"]
        k = max(i for i, e in enumerate(events) if e["event"] == "model" and e["model"].endswith("agent:1b"))
        extra = [dict(events[k], uuid=s.uid("E")) for _ in range(4)]
        events[k + 1:k + 1] = extra
        agent = [e for e in events if e["event"] == "model" and e["model"].endswith("agent:1b")]
        assert len(agent) == 6
        for e in agent[:5]:
            e["call"] = {"request": {"model": "synthetic-agent:1b", "temperature": 0.0}, "response": {}, "time": 0.1}
    u, _prov = run(tmp_path, support.basic_sample(tune=tune))
    calls = [m for m in u.of_kind("model_call") if m["role"] == "agent"]
    assert [("transmitted" in m.get("params", {})) for m in calls] == [True] * 5 + [False]
    assert calls[5]["unk"]["/params/transmitted"] == "lost" and rule_at(calls[5], "/params/transmitted") == [RETENTION]
    judge = next(m for m in u.of_kind("model_call") if m["role"] == "auxiliary")
    assert judge["unk"]["/params/transmitted"] == "not_recorded"  # no earlier kept call of that model: not explained
