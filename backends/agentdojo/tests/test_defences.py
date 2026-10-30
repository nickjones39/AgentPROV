"""Defended pipelines (D-670..D-679; docs/reports/defence-backends/design.md §3.4, §3.9).

For each first-set defence that this environment can build without downloads (``repeat_user_prompt``,
``spotlighting_with_delimiting``, ``tool_filter``) and for the two recorders that need a stand-in here (an
``output_filter`` detector, an ``executor_gate`` executor), the tests check:

* structure: the instrumented pipeline is the stock-built one with the declared substitutions only;
* behaviour: the stock defended pipeline and the instrumented one, driven by the same script, give equal message
  lists, environments and outcomes (JCS);
* capture: the defence actor, its auxiliary calls, decisions, denials and the messages it inserts are recorded, and
  nothing is invented (no decision without an observed verdict, no result for a call that never ran).

The PI detector needs torch, transformers and pinned weights (D-672), which this environment does not have: its entry
is refused here, and its recorder is exercised with a stand-in detector of the same base class.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

import openai
import pytest
import rfc8785
from agentdojo.agent_pipeline import agent_pipeline as stock_pipeline_module
from agentdojo.agent_pipeline.agent_pipeline import AgentPipeline, PipelineConfig
from agentdojo.agent_pipeline.base_pipeline_element import BasePipelineElement
from agentdojo.agent_pipeline.llms.openai_llm import OpenAILLM
from agentdojo.agent_pipeline.pi_detector import PromptInjectionDetector
from agentdojo.functions_runtime import EmptyEnv
from agentdojo.task_suite.load_suites import get_suite

from agentprov_backend import defences
from agentprov_backend.defences import (
    ACTOR,
    DefenceEntry,
    build_defended_pipeline,
    catalogue_entries,
    entry_refusal,
    load_registry,
    resolve,
)
from agentprov_backend.runner import SCRIPTED_BASE_URL, _default_http_client, catalogue, expand_plan
from agentprov_backend.session import serialise_messages
from agentprov_backend.testing import ScriptedTransport, step_from_dict
from agentprov_backend.testing.scenarios import MODEL, _agent, _call, _cell, _text, _tool

from support import Run, assert_capture_invariants, pass_message_lists, run_cell

BANKING_READ = _call("get_most_recent_transactions", {"n": 100})
FINAL = _text("You spent 1050 in March 2022.")
VERSION = "v1.2.2"
INJECTION_MARK = "<INFORMATION>"  # the important_instructions template's opening tag


def _jcs(value: Any) -> bytes:
    return rfc8785.dumps(json.loads(json.dumps(value, default=str)))


def _defended_cell(defence: str, *, attack: str | None = None, injection: str | None = None,
                   user_task: str = "user_task_1") -> dict[str, Any]:
    cell = _cell("banking", user_task, attack=attack, injection=injection,
                 kind="attacked" if attack else "user_task",
                 attack_params={"model_display_name": "Scripted Model"} if attack else None)
    cell["defence"] = defence
    return cell


# ---------------------------------------------------------------------------------------------- the registry


def test_the_registry_validates_and_lists_the_first_set():
    reg = load_registry()
    assert {"repeat_user_prompt", "spotlighting_with_delimiting", "tool_filter", "transformers_pi_detector",
            "mandate_envelope", "mandate_scoped", "mandate_intent"} <= set(reg)
    for entry in reg.values():
        assert entry.licence["spdx"] == "MIT"
        if entry.provider == "builtin":
            assert entry.benchmark_name == entry.id  # ids are the benchmark's own names (D-670)


@pytest.mark.parametrize("did", ["repeat_user_prompt", "spotlighting_with_delimiting", "tool_filter"])
def test_builtins_without_assets_are_buildable_here(did):
    assert entry_refusal(resolve(did, "agentdojo")) is None


def test_the_pi_detector_is_refused_until_its_assets_are_provisioned():
    reason = entry_refusal(resolve("transformers_pi_detector", "agentdojo"), prefix="/nonexistent-prefix")
    assert reason is not None and ("not installed" in reason or "not provisioned" in reason)
    assert "--defence-assets transformers_pi_detector" in reason


def test_a_provisioned_entry_without_its_files_is_refused():
    reason = entry_refusal(resolve("mandate_intent", "agentdojo"), prefix="/nonexistent-prefix")
    assert reason is not None and "missing" in reason


def test_unknown_and_foreign_defences_are_refused():
    from agentprov_backend.attacks import UnsupportedConfiguration

    with pytest.raises(UnsupportedConfiguration, match="unknown defence"):
        resolve("no_such_defence", "agentdojo")
    with pytest.raises(UnsupportedConfiguration, match="not built by the 'autodojo' backend"):
        resolve("tool_filter", "autodojo")


def test_a_changed_guarded_source_refuses_the_entry():
    entry = resolve("repeat_user_prompt", "agentdojo")
    name = next(iter(entry.guarded))
    changed = replace(entry, guarded={**entry.guarded, name: "0" * 64})
    assert "differs" in entry_refusal(changed)


def test_malformed_registries_are_refused(tmp_path):
    from agentprov_backend.attacks import UnsupportedConfiguration

    base = defences.registry_path().read_text(encoding="utf-8")
    cases = {
        "format": base.replace('format = "agentprov-defence-registry/0.1"', 'format = "x"'),
        "unknown member": base.replace('id = "tool_filter"', 'id = "tool_filter"\nsurprise = 1'),
        "duplicate": base + '\n[[defence]]\nid = "tool_filter"\ntitle = "t"\nbackends = ["agentdojo"]\n'
                            'provider = "builtin"\nbenchmark_name = "tool_filter"\n'
                            'licence = { spdx = "MIT", basis = "b" }\nsuites = ["*"]\n',
        "gate without denials": base.replace('denials = [{ error_prefix = "MANDATE_DECLINE: " }]\n', "", 1),
    }
    for label, text in cases.items():
        p = tmp_path / f"{label.replace(' ', '_')}.toml"
        p.write_text(text, encoding="utf-8")
        with pytest.raises(UnsupportedConfiguration):
            load_registry(p)


# ---------------------------------------------------------------------------------------------- plans, catalogue


def _plan(defence: str, suites: Sequence[str] = ("banking",)) -> dict[str, Any]:
    return {"plan": {"format": "agentprov-run-plan/0.1", "suites": list(suites), "user_tasks": "0-1",
                     "defence": defence},
            "agent": _agent()}


def test_a_plan_carries_its_defence_into_every_cell():
    plan = expand_plan(_plan("repeat_user_prompt"))
    assert plan.cells and {c.defence for c in plan.cells} == {"repeat_user_prompt"}


def test_a_plan_outside_a_defence_s_suites_is_refused():
    from agentprov_backend.attacks import UnsupportedConfiguration

    with pytest.raises(UnsupportedConfiguration, match="runs on"):
        expand_plan(_plan("mandate_intent", suites=("banking", "slack")))
    with pytest.raises(UnsupportedConfiguration, match="unknown defence"):
        expand_plan(_plan("melon_rp"))


def test_the_catalogue_lists_defences_with_this_environment_s_refusals():
    doc = catalogue(VERSION)
    by = {d["name"]: d for d in doc["defences"]}
    assert by["tool_filter"]["refused"] is None and by["tool_filter"]["aux_llm"] == "agent_endpoint"
    assert by["transformers_pi_detector"]["refused"]
    assert by["mandate_intent"]["refused"] and by["mandate_intent"]["needs"] == ["--defence-assets mandate_intent"]
    assert catalogue_entries("autodojo") == []  # no first-set entry names the fork yet


# ---------------------------------------------------------------------------------------------- stock vs instrumented


class _Capture(BasePipelineElement):
    """Runs a pipeline and keeps the messages it returned (the stock side of the differential)."""

    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.name = inner.name
        self.messages: list[Any] = []

    def query(self, query, runtime, env=EmptyEnv(), messages=[], extra_args={}):  # noqa: B006, B008
        out = self.inner.query(query, runtime, env, messages, extra_args)
        self.messages = list(out[3])
        return out


def _stock_llm(steps: Sequence[Mapping[str, Any]]) -> tuple[OpenAILLM, ScriptedTransport]:
    transport = ScriptedTransport([step_from_dict(s) for s in steps], model=MODEL)
    client = openai.OpenAI(api_key="scripted-no-key", base_url=SCRIPTED_BASE_URL,
                           http_client=_default_http_client(transport))
    llm = OpenAILLM(client, MODEL, temperature=0.0)
    llm.name = MODEL
    return llm, transport


def _stock_run(defence: str | None, steps: Sequence[Mapping[str, Any]], *, user_task: str = "user_task_1",
               pipeline: Any = None) -> tuple[list[Any], Any, tuple[bool, bool], ScriptedTransport]:
    suite = get_suite(VERSION, "banking")
    llm, transport = _stock_llm(steps)
    if pipeline is None:
        pipeline = AgentPipeline.from_config(PipelineConfig(llm=llm, model_id=None, defense=defence,
                                                            system_message_name=None, system_message=None))
    else:
        pipeline = pipeline(llm)
    cap = _Capture(pipeline)
    task = suite.get_user_task_by_id(user_task)
    env = suite.load_and_inject_default_environment({})
    utility, security = suite.run_task_with_pipeline(cap, task, None, {}, environment=env)
    return cap.messages, env, (utility, security), transport


def _instrumented(tmp_path: Path, defence: str, steps: Sequence[Mapping[str, Any]], **kw: Any) -> Run:
    run = run_cell(tmp_path, _defended_cell(defence, **kw), _agent(), steps)
    assert run.result.status == "complete", run.of("error")
    assert_capture_invariants(run)
    return run


def _same(run: Run, stock_messages: list[Any], stock_env: Any, stock_outcome: tuple[bool, bool],
          stock_transport: ScriptedTransport) -> None:
    (last,) = pass_message_lists(run)[-1:]
    data, _ = serialise_messages(stock_messages)
    assert _jcs(last) == _jcs(json.loads(data))
    assert run.judgements()["utility"][0] == stock_outcome[0]
    assert [json.loads(b) for b in run.transport.bodies] == [json.loads(b) for b in stock_transport.bodies]
    snapshot = run.of("pass.end")[-1]["data"]["env"].get("snapshot")
    assert snapshot is not None  # env_snapshots is on by default: the environments are really compared
    assert _jcs(run.json_blob(snapshot)) == _jcs(stock_env.model_dump(mode="json"))
    assert len(run.transport.bodies) == len(stock_transport.bodies) > 0


@pytest.mark.parametrize("defence, steps", [
    ("repeat_user_prompt", [_tool(BANKING_READ), FINAL]),
    ("spotlighting_with_delimiting", [_tool(BANKING_READ), FINAL]),
    ("tool_filter", [_text("get_most_recent_transactions"), _tool(BANKING_READ), FINAL]),
])
def test_instrumented_defended_pipelines_equal_stock(tmp_path, defence, steps):
    run = _instrumented(tmp_path, defence, steps)
    _same(run, *_stock_run(defence, steps))
    start = run.of("session.start")[0]["data"]
    assert start["cell"]["defense_id"] == defence
    assert start["actors"][ACTOR] == {"kind": "defense", "name": defence, **(
        {"model": {"requested": MODEL, "provider": "openai_compatible", "endpoint": "scripted.invalid"}}
        if defence == "tool_filter" else {})}
    ids = run.instrumentation_ids()
    assert "agentdojo.defence_pipeline_rewrite@1" in ids
    (ident,) = run.notes("defence_identity")
    assert ident["entry"]["id"] == defence and ident["registry_sha256"] == defences.registry_sha256()
    assert run.native()["pipeline_name"] == f"{MODEL}-{defence}"  # stock naming, so native logs land as stock's


def test_repeat_user_prompt_records_the_inserted_user_turn(tmp_path):
    run = _instrumented(tmp_path, "repeat_user_prompt", [_tool(BANKING_READ), FINAL])
    (messages,) = pass_message_lists(run)
    notes = run.notes("defence_message")
    assert [n["at"] for n in notes] == [4]  # system, user, assistant(call), tool, *user (repeated)*, assistant
    assert messages[4]["role"] == "user" and messages[4]["content"] == messages[1]["content"]
    assert all(n["actor"] == ACTOR and n["role"] == "user" for n in notes)


def test_spotlighting_keeps_the_delimiting_formatter_and_the_system_sentence(tmp_path):
    run = _instrumented(tmp_path, "spotlighting_with_delimiting", [_tool(BANKING_READ), FINAL])
    (messages,) = pass_message_lists(run)
    (result,) = run.of("tool.result")
    assert result["data"]["rendered"].startswith("<<") and result["data"]["rendered"].endswith(">>")
    entry = resolve("spotlighting_with_delimiting", "agentdojo")
    assert messages[0]["content"][0]["content"].endswith(entry.system_suffix)
    assert not run.of("decision")  # a formatter is not a decision (as the import side, D.6.6)


def test_tool_filter_calls_are_auxiliary_calls_of_the_defence(tmp_path):
    run = _instrumented(tmp_path, "tool_filter", [_text("get_most_recent_transactions"), _tool(BANKING_READ), FINAL])
    reqs = run.of("llm.request")
    assert [(e["data"]["role"], e["actor"]) for e in reqs] == [("auxiliary", ACTOR), ("agent", "agent"),
                                                              ("agent", "agent")]
    assert reqs[0]["data"]["n_messages"] == 3  # system, user, filter prompt
    (tools,) = run.notes("defence_tools")
    assert tools["after"] == ["get_most_recent_transactions"] and len(tools["before"]) > 1
    assert tools["calls"] == [reqs[0]["data"]["call"]]
    notes = run.notes("defence_message")
    assert [(n["at"], n["role"]) for n in notes] == [(2, "user"), (3, "assistant")]
    assert notes[1]["call"] == reqs[0]["data"]["call"]
    # the agent's next request offers only the kept tool
    body = json.loads(run.blob(reqs[1]["data"]["request"]))
    assert [t["function"]["name"] for t in body["tools"]] == ["get_most_recent_transactions"]


def test_the_structure_is_the_stock_pipeline_with_declared_substitutions(tmp_path):
    from agentprov_backend.runner import CaptureSession

    llm, _ = _stock_llm([])
    config = PipelineConfig(llm=llm, model_id=None, defense=None, system_message_name=None, system_message=None)
    session = CaptureSession(tmp_path / "s")
    for did in ("repeat_user_prompt", "spotlighting_with_delimiting", "tool_filter"):
        made = build_defended_pipeline(resolve(did, "agentdojo"), config, session)
        stock = AgentPipeline.from_config(config.model_copy(update={"defense": did}))
        inner = made.pipeline.inner
        assert len(inner.elements) == len(stock.elements)
        stock_loop, loop = stock.elements[-1], inner.elements[-1]
        assert len(loop.elements) == len(stock_loop.elements)
        assert all(s.split(":", 1)[1].split("(", 1)[0] in ("SpannedLLM", "MirrorToolsExecutor", "prompt_wrapper",
                                                          "tool_list_filter") for s in made.substitutions)
        assert inner.name == f"{MODEL}-{did}"


# ---------------------------------------------------------------------------------------------- output filter


class _MarkDetector(PromptInjectionDetector):
    """A deterministic stand-in for the classifier: flags the important_instructions tag."""

    def detect(self, tool_output: str) -> tuple[bool, float]:
        hit = INJECTION_MARK in tool_output
        return hit, 0.99 if hit else 0.01


def _with_detector(monkeypatch: pytest.MonkeyPatch, *, raise_on_injection: bool = False) -> None:
    def factory(**kwargs: Any) -> _MarkDetector:
        return _MarkDetector(mode=kwargs.get("mode", "message"), raise_on_injection=raise_on_injection)

    monkeypatch.setattr(stock_pipeline_module, "TransformersBasedPIDetector", factory)
    entry = resolve("transformers_pi_detector", "agentdojo")
    stand_in = replace(entry, assets={}, assets_pending=None, weights=(),
                       elements=({"match": f"{__name__}._MarkDetector", "where": "loop", "recorder": "output_filter",
                                  "observe": "detect"},),
                       guarded={k: v for k, v in entry.guarded.items() if "TransformersBasedPIDetector" not in k})
    reg = {**load_registry(), stand_in.id: stand_in}
    monkeypatch.setattr(defences, "load_registry", lambda path=None: reg)


def test_an_output_filter_records_redactions_with_their_original_and_allows_with_scores(tmp_path, monkeypatch):
    _with_detector(monkeypatch)
    steps = [_tool(BANKING_READ), FINAL]
    run = _instrumented(tmp_path, "transformers_pi_detector", steps, attack="important_instructions",
                        injection="injection_task_0")
    (messages,) = pass_message_lists(run)
    (result,) = run.of("tool.result")
    (decision,) = run.of("decision")
    d = decision["data"]
    assert decision["actor"] == ACTOR and d["actor"] == ACTOR
    assert d["subject"] == {"occ": result["data"]["occ"]} and d["verdict"] == "redact"
    assert d["reason"] == "is_injection=True score=0.99"
    original = run.json_blob(d["original"])
    assert INJECTION_MARK in original[0]["content"]  # the text the stock in-place overwrite destroys
    assert messages[3]["content"][0]["content"] == "<Data omitted because a prompt injection was detected>"
    assert INJECTION_MARK in result["data"]["rendered"]  # the executor's output, before the defence


def test_an_output_filter_records_an_allow_only_when_it_observed_the_verdict(tmp_path, monkeypatch):
    _with_detector(monkeypatch)
    run = _instrumented(tmp_path, "transformers_pi_detector", [_tool(BANKING_READ), FINAL])
    (decision,) = run.of("decision")
    assert decision["data"]["verdict"] == "allow" and decision["data"]["reason"] == "is_injection=False score=0.01"
    assert "original" not in decision["data"]


def test_an_output_filter_abort_is_a_terminate_decision_on_an_aborted_pass(tmp_path, monkeypatch):
    _with_detector(monkeypatch, raise_on_injection=True)
    run = run_cell(tmp_path, _defended_cell("transformers_pi_detector", attack="important_instructions",
                                            injection="injection_task_0"), _agent(), [_tool(BANKING_READ)])
    assert_capture_invariants(run)
    (decision,) = run.of("decision")
    assert decision["data"]["verdict"] == "terminate"
    assert [e["data"]["aborted"] for e in run.of("pass.end")] == [True]


def test_the_pi_detector_differential_with_the_stand_in(tmp_path, monkeypatch):
    _with_detector(monkeypatch)
    steps = [_tool(BANKING_READ), FINAL]
    run = _instrumented(tmp_path, "transformers_pi_detector", steps)
    _same(run, *_stock_run("transformers_pi_detector", steps))


# ---------------------------------------------------------------------------------------------- executor gate


GATE_SOURCE = '''
from agentdojo.agent_pipeline.tool_execution import ToolsExecutor, tool_result_to_str
from agentdojo.functions_runtime import EmptyEnv
from agentdojo.types import ChatToolResultMessage, text_content_block_from_string


def make_gate(blocked):
    class TestGate(ToolsExecutor):
        def query(self, query, runtime, env=EmptyEnv(), messages=[], extra_args={}):
            if not messages or messages[-1]["role"] != "assistant" or not messages[-1].get("tool_calls"):
                return query, runtime, env, messages, extra_args
            results = []
            for tc in messages[-1]["tool_calls"]:
                if tc.function in blocked:
                    reason = "GATE_DECLINE: " + tc.function
                    results.append(ChatToolResultMessage(role="tool", content=[text_content_block_from_string(reason)],
                                                         tool_call_id=tc.id, tool_call=tc, error=reason))
                    continue
                if tc.function not in (t.name for t in runtime.functions.values()):
                    results.append(ChatToolResultMessage(role="tool", content=[text_content_block_from_string("")],
                                                         tool_call_id=tc.id, tool_call=tc,
                                                         error=f"Invalid tool {tc.function} provided."))
                    continue
                out, error = runtime.run_function(env, tc.function, tc.args)
                results.append(ChatToolResultMessage(role="tool",
                                                     content=[text_content_block_from_string(self.output_formatter(out))],
                                                     tool_call_id=tc.id, tool_call=tc, error=error))
            return query, runtime, env, [*messages, *results], extra_args
    return TestGate(tool_result_to_str)
'''


def _gate_entry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: str = GATE_SOURCE,
                blocked: Sequence[str] = ("send_money",), denials: Sequence[Mapping[str, str]] | None = None,
                did: str = "test_gate", file_label: str = "gate.py", entry_point: str = "make_gate",
                kwargs: Mapping[str, Any] | None = None) -> DefenceEntry:
    data = source.encode("utf-8")
    root = tmp_path / "prefix" / "agentprov_defences" / did
    root.mkdir(parents=True)
    (root / file_label).write_bytes(data)
    entry = DefenceEntry(
        id=did, title="test gate", backends=("agentdojo",), provider="provisioned",
        licence={"spdx": "MIT", "basis": "test"}, guarded={},
        elements=({"match": "agentdojo.agent_pipeline.tool_execution.ToolsExecutor", "where": "loop",
                   "recorder": "executor_gate"},),
        formatter="stock", aux_llm="none", suites=("banking",), cost={},
        code={"repo": "https://example.invalid/test", "commit": "0" * 40,
              "files": [{"path": file_label, "blob_sha1": "0" * 40, "sha256": hashlib.sha256(data).hexdigest()}],
              "entry": f"{file_label}:{entry_point}", "kwargs": dict(kwargs if kwargs is not None
                                                                      else {"blocked": list(blocked)})},
        denials=tuple(denials or ({"error_prefix": "GATE_DECLINE: "},)),
    )
    reg = {**load_registry(), did: entry}
    monkeypatch.setattr(defences, "load_registry", lambda path=None: reg)
    monkeypatch.setattr(defences, "provisioned_dir", lambda e, prefix=None: tmp_path / "prefix" / "agentprov_defences"
                        / e.id)
    return entry


SEND = _call("send_money", {"recipient": "US133000000121212121212", "amount": 10.0, "subject": "x",
                            "date": "2022-01-01"}, "call_2")


def test_a_gate_denial_is_a_denied_result_by_the_defence_and_never_an_execution(tmp_path, monkeypatch):
    _gate_entry(tmp_path, monkeypatch)
    run = _instrumented(tmp_path, "test_gate", [_tool(BANKING_READ, SEND), FINAL])
    dispatch = {e["data"]["occ"]: e["data"] for e in run.of("tool.dispatch")}
    results = {e["data"]["occ"]: e["data"] for e in run.of("tool.result")}
    assert sorted(d["name"] for d in dispatch.values()) == ["get_most_recent_transactions", "send_money"]
    by_name = {d["name"]: occ for occ, d in dispatch.items()}
    ok, denied = results[by_name["get_most_recent_transactions"]], results[by_name["send_money"]]
    assert ok["status"] == "ok" and "returned" in ok
    assert denied["status"] == "denied" and denied["decided_by"] == ACTOR and "returned" not in denied
    assert denied["error"] == "GATE_DECLINE: send_money"
    assert dispatch[by_name["send_money"]]["at"] == {"message": 2, "call": 1}
    (match,) = run.notes("defence_denial_match")
    assert match == {"occ": by_name["send_money"], "actor": ACTOR, "matcher": 0}
    assert run.notes("defence_gate_post_hoc") == [{"actor": ACTOR, "occs": [by_name["send_money"]]}]
    assert "agentdojo.defence_code_provisioned@1" in run.instrumentation_ids()


def test_a_gate_differential_against_the_unwrapped_gate(tmp_path, monkeypatch):
    entry = _gate_entry(tmp_path, monkeypatch)
    steps = [_tool(BANKING_READ, SEND), FINAL]
    run = _instrumented(tmp_path, "test_gate", steps)
    gate = defences.load_provisioned(entry)(blocked=["send_money"])

    def build(llm: Any) -> Any:
        from agentdojo.agent_pipeline.basic_elements import InitQuery, SystemMessage
        from agentdojo.agent_pipeline.agent_pipeline import load_system_message
        from agentdojo.agent_pipeline.tool_execution import ToolsExecutionLoop

        pipe = AgentPipeline([SystemMessage(load_system_message(None)), InitQuery(), llm,
                              ToolsExecutionLoop([gate, llm])])
        pipe.name = f"{MODEL}-test_gate"
        return pipe

    _same(run, *_stock_run(None, steps, pipeline=build))


def test_an_unexplained_non_execution_gets_no_invented_result(tmp_path, monkeypatch):
    _gate_entry(tmp_path, monkeypatch, denials=({"error_prefix": "SOMETHING_ELSE"},))
    run = _instrumented(tmp_path, "test_gate", [_tool(SEND), FINAL])
    (dispatch,) = run.of("tool.dispatch")
    assert not run.of("tool.result")
    assert run.notes("defence_unclassified_non_execution") == [{"occ": dispatch["data"]["occ"], "actor": ACTOR}]


def test_the_gate_reports_an_unknown_tool_as_invalid(tmp_path, monkeypatch):
    _gate_entry(tmp_path, monkeypatch)
    run = _instrumented(tmp_path, "test_gate", [_tool(_call("no_such_tool", {}, "call_9")), FINAL])
    (result,) = run.of("tool.result")
    assert result["data"]["status"] == "invalid" and "decided_by" not in result["data"]


# ---------------------------------------------------------------------------------------------- Mandate (opt-in)


MANDATE_CACHE = Path.home() / ".agentprov/cache/git/github.com/jwilliamsc/mandate-agentdojo-eval.git"


def _mandate_source() -> bytes | None:
    """The pinned Mandate file from the bare fetch cache (read with GIT_NO_LAZY_FETCH=1; nothing is fetched)."""
    if not MANDATE_CACHE.is_dir() or shutil.which("git") is None:
        return None
    entry = resolve("mandate_intent", "agentdojo")
    assert entry.code is not None
    f = entry.code["files"][0]
    env = {**os.environ, "GIT_NO_LAZY_FETCH": "1"}
    proc = subprocess.run(["git", "-C", str(MANDATE_CACHE), "cat-file", "blob", f["blob_sha1"]],
                          capture_output=True, env=env, check=False)
    if proc.returncode != 0 or hashlib.sha256(proc.stdout).hexdigest() != f["sha256"]:
        return None
    return proc.stdout


@pytest.mark.parametrize("mode", ["envelope", "intent"])
def test_mandate_denies_an_unknown_recipient_from_its_pinned_code(tmp_path, monkeypatch, mode):
    data = _mandate_source()
    if data is None:
        pytest.skip("the pinned Mandate blob is not in the bare fetch cache")
    did = f"mandate_{mode}"
    real = resolve(did, "agentdojo")
    root = tmp_path / "prefix" / "agentprov_defences" / did
    root.mkdir(parents=True)
    (root / "agentdojo_mandate_eval.py").write_bytes(data)
    monkeypatch.setattr(defences, "provisioned_dir", lambda e, prefix=None: tmp_path / "prefix" / "agentprov_defences"
                        / e.id)
    assert entry_refusal(real) is None
    attacker = _call("send_money", {"recipient": "US133000000121212121212", "amount": 100.0, "subject": "x",
                                    "date": "2022-01-01"}, "call_2")
    run = _instrumented(tmp_path, did, [_tool(attacker), FINAL])
    (result,) = run.of("tool.result")
    assert result["data"]["status"] == "denied" and result["data"]["decided_by"] == ACTOR
    assert result["data"]["error"].startswith("MANDATE_DECLINE: ")
    assert run.native()["pipeline_name"] == f"{MODEL}-{did}"  # the authors' own naming (build_pipeline)
