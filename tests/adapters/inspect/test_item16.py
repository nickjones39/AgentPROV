"""Regeneration-batch item 16 (phase 10f F3): Inspect message copies, first-of-batch tool-event message ids and the
react agent's removed submit message, each read from the producer code at 0.3.130, 0.3.134.dev31, 0.3.154.dev37 and
0.3.159.dev20 (docs/reports/analysis/regen-batch.md item 16). Synthetic samples only.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import inspect_support as support
from agentprov.adapters.profiles import SourceProfile, load_profile, parse_profile
from agentprov.aer.reader import load_aer
from agentprov.aer.rules import RuleRegistry
from agentprov.aer.validate import AerValidator
from agentprov.prov.engine import derive
from agentprov.validate import validate_prov

REPO = Path(__file__).resolve().parents[3]
PROFILE = REPO / "src" / "agentprov" / "adapters" / "inspect" / "profiles" / "survey-agentharm.profile.toml"
SHARE = "inspect.message_copies_share_calls@1"
FIRST = "inspect.tool_event_message_id_first_of_batch@1"
SUBMIT = "inspect.react_submit_message_removed@1"
TOOLS = [{"name": "get_x", "description": "Synthetic tool.", "parameters": {"type": "object", "properties": {}}}]


def submit_profile() -> SourceProfile:
    """The AgentHarm profile with a react submit tool declared (a dev-only variant for tests)."""
    text = PROFILE.read_text(encoding="utf-8")
    old = 'span_roles = { solver = "agent", scorer = "judge" }\n'
    assert old in text
    return parse_profile(text.replace(old, old + 'submit_tools = ["submit"]\n').encode("utf-8"), source="test-variant")


def run(tmp_path: Path, sample: dict[str, Any], profile: SourceProfile | None = None) -> support.Unit:
    """Import one synthetic sample; it validates, derives and passes tier 4."""
    data = support.build_eval(support.synthetic_header(), {"s1_epoch_1.json": sample})
    imported = support.import_log(data, tmp_path / "raw", profile=profile)
    assert imported.register == [] and len(imported.units) == 1
    unit = imported.units[0]
    assert not unit.outcome.degenerate, unit.outcome.error_code
    used = profile or load_profile("survey-agentharm")
    validator = AerValidator(store=imported.store, catalogues=RuleRegistry.default(), mode="release",
                             profile_digests={(used.id, used.version): used.sha256})
    for line in unit.data.splitlines(keepends=True):
        validator.feed(line)
    report = validator.finish()
    assert report.ok, sorted({(f.code, f.pointer) for f in report.errors})
    path = tmp_path / "x.aer.jsonl"
    path.write_bytes(unit.data)
    doc = load_aer(path)
    result = validate_prov(derive(doc).prov_json, doc)
    assert result.ok, [(o.id, sorted(o.codes())) for o in result.outcomes if o.status == "fail"]
    return unit


def cites(record: dict[str, Any], rule: str) -> bool:
    return any(r.split("#", 1)[0] == rule for r in record.get("rule", []))


def codes(unit: support.Unit) -> set[str]:
    return {str(i["code"]) for i in unit.info.issues}


def issues(unit: support.Unit, code: str) -> list[str]:
    """The rule each ``code`` issue cites (the declaration's reason)."""
    return [str(i["rule"]).split("#", 1)[0] for i in unit.info.issues if i["code"] == code]


def _frame(s: support.Sample) -> tuple[str, dict[str, Any], dict[str, Any]]:
    init = s.span("SpanInit00000000000000", "init", "init")
    s.event("sample_init", init, sample={"input": "Synthetic task prompt.", "target": "", "id": s.sid, "metadata": {}},
            state={"messages": []})
    s.end(init)
    gen = s.span("SpanGenerate0000000000", "solver", "generate")
    return gen, s.msg("system", "You are a synthetic agent."), s.msg("user", "Synthetic task prompt.", source="input")


def copies_sample(*, same_calls: bool = True) -> dict[str, Any]:
    """One assistant message stored three ways (same Inspect id): the output choice with reasoning, the ``messages``
    copy without it, and the replayed input copy with the reasoning emulated as text."""
    s = support.Sample()
    gen, system, user = _frame(s)
    call = {"id": "call_copy_1", "function": "get_x", "arguments": {"q": "a"}, "type": "function"}
    produced = s.msg("assistant", [{"type": "reasoning", "reasoning": "Synthetic reasoning.", "redacted": False},
                                   {"type": "text", "text": "Calling."}], source="generate", model="synthetic",
                     tool_calls=[call])
    kept = copy.deepcopy(produced)
    kept["content"] = [{"type": "text", "text": "Calling."}]
    if not same_calls:
        kept["tool_calls"] = [{**call, "arguments": {"q": "b"}}]
    replayed = copy.deepcopy(produced)
    replayed["content"] = [{"type": "text", "text": "<think>\nSynthetic reasoning.\n</think>"},
                           {"type": "text", "text": "Calling."}]
    result = s.msg("tool", "synthetic tool output", tool_call_id=call["id"], function="get_x")
    final = s.msg("assistant", "Synthetic final answer.", source="generate", model="synthetic")
    s.model(gen, "ollama/synthetic-agent:1b", [system, user], produced, tools=TOOLS)
    s.tool(gen, call, result)
    s.model(gen, "ollama/synthetic-agent:1b", [system, user, replayed, result], final, tools=TOOLS)
    s.end(gen)
    s.messages.extend([system, user, kept, result, final])
    return s.build()


def test_copies_of_one_message_share_their_calls(tmp_path):
    u = run(tmp_path, copies_sample())
    holders = [m for m in u.of_kind("message") if any(p.get("t") == "tool_call" for p in m["parts"])]
    assert len(holders) == 3  # the copies stay separate records: the model really was re-sent different content
    te = u.of_kind("tool_execution")[0]
    assert te["call"].startswith("o") and cites(te, SHARE)  # the output choice: the copy the model produced
    result = next(m for m in u.of_kind("message") if m["role"] == "tool")
    assert result["parts"][0]["responds_to"] == te["call"] and cites(result, SHARE)
    assert result["generated_by"] == te["id"]
    assert not codes(u) & {"call_result_link_conflict", "orphan_tool_result"}
    # the copies' parts are declared under the copy rule, never as a lost call; accounting stays consistent
    assert issues(u, "unexecuted_tool_call") == [SHARE]
    assert u.info.accounting.status == "consistent"


def test_copies_with_different_calls_stay_ambiguous(tmp_path):
    u = run(tmp_path, copies_sample(same_calls=False))
    te = u.of_kind("tool_execution")[0]
    assert "call" not in te and te["unk"]["/call"] == "ambiguous" and not cites(te, SHARE)
    assert "call_result_link_conflict" in codes(u)


def batch_sample() -> dict[str, Any]:
    """Two parallel calls in one assistant message; both tool events name the first call's result message, as
    ``execute_tools`` writes them (``message_id=result_messages[0].id``)."""
    s = support.Sample()
    gen, system, user = _frame(s)
    c1 = {"id": "call_batch_1", "function": "get_x", "arguments": {"q": "a"}, "type": "function"}
    c2 = {"id": "call_batch_2", "function": "get_x", "arguments": {"q": "b"}, "type": "function"}
    a1 = s.msg("assistant", "Calling both.", source="generate", model="synthetic", tool_calls=[c1, c2])
    r1 = s.msg("tool", "first output", tool_call_id=c1["id"], function="get_x")
    r2 = s.msg("tool", "second output", tool_call_id=c2["id"], function="get_x")
    final = s.msg("assistant", "Synthetic final answer.", source="generate", model="synthetic")
    s.model(gen, "ollama/synthetic-agent:1b", [system, user], a1, tools=TOOLS)
    s.tool(gen, c1, r1)
    s.tool(gen, c2, r1)  # the first result message's id, not r2's
    s.model(gen, "ollama/synthetic-agent:1b", [system, user, a1, r1, r2], final, tools=TOOLS)
    s.end(gen)
    s.messages.extend([system, user, a1, r1, r2, final])
    return s.build()


def test_later_calls_of_a_batch_link_by_call_id(tmp_path):
    u = run(tmp_path, batch_sample())
    te1, te2 = u.of_kind("tool_execution")
    results = {m["parts"][0]["responds_to"]: m for m in u.of_kind("message") if m["role"] == "tool"}
    first, second = results[te1["call"]], results[te2["call"]]
    assert first["generated_by"] == te1["id"] and not cites(first, FIRST)  # message_id agrees: unchanged citation
    assert second["generated_by"] == te2["id"] and cites(second, FIRST)  # found by call id, not by message_id
    assert not codes(u) & {"missing_tool_result", "dangling_source_ref", "orphan_tool_result"}
    assert u.info.accounting.status == "consistent"


def submit_sample() -> dict[str, Any]:
    """The react agent's final submit: its result message was removed from ``messages`` (``_remove_submit_tool``),
    the tool event keeps the value in ``result``, and the ``messages`` copy of the assistant message lost the call."""
    s = support.Sample()
    gen, system, user = _frame(s)
    call = {"id": "call_submit_1", "function": "submit", "arguments": {"answer": "done"}, "type": "function"}
    produced = s.msg("assistant", "Submitting.", source="generate", model="synthetic", tool_calls=[call])
    kept = copy.deepcopy(produced)
    kept["tool_calls"] = []
    removed = s.msg("tool", "done", tool_call_id=call["id"], function="submit")
    s.model(gen, "ollama/synthetic-agent:1b", [system, user], produced, tools=TOOLS)
    s.tool(gen, call, removed)
    s.end(gen)
    s.messages.extend([system, user, kept])  # the submit result message is not in messages
    return s.build()


def test_a_removed_submit_message_keeps_its_result_as_an_artefact(tmp_path):
    u = run(tmp_path, submit_sample(), submit_profile())
    te = u.of_kind("tool_execution")[0]
    assert te["name"] == "submit" and te["call"].startswith("o")
    af = next(a for a in u.of_kind("artefact") if a.get("type") == "inspect:tool_result")
    assert af["generated_by"] == te["id"] and af["content"] == "done" and cites(af, SUBMIT)
    assert not [m for m in u.of_kind("message") if m["role"] == "tool"]  # no result message is invented
    assert issues(u, "missing_tool_result") == [SUBMIT] and "dangling_source_ref" not in codes(u)
    assert u.info.accounting.status == "consistent"


def test_without_the_profile_key_the_removed_submit_result_stays_missing(tmp_path):
    u = run(tmp_path, submit_sample())
    assert not [a for a in u.of_kind("artefact") if a.get("type") == "inspect:tool_result"]
    assert issues(u, "missing_tool_result") == ["inspect.tool_event_is_execution@1"]
