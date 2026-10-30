"""Regeneration-batch item 133 (pre-check PC-04, user decision 2026-10-21: split per scope;
``inspect.cached_output_own_message@1``): Inspect's model cache returns the stored ModelOutput unchanged, message and
ToolCall ids included. A scorer that replays another scorer's monitor conversation from the cache gets that scope's own
message, and its re-run tools answer that copy's calls, not the first scorer's. Synthetic samples only."""

from __future__ import annotations

import copy
from typing import Any

import inspect_support as support
from test_item16 import TOOLS, _frame, cites, codes, run

CACHED = "inspect.cached_output_own_message@1"
JUDGE = "openai/synthetic-judge"


def _monitor(s: support.Sample, span: str, sys_: dict[str, Any], user: dict[str, Any], produced: dict[str, Any],
             call: dict[str, Any], verdict: dict[str, Any], *, cached: bool) -> dict[str, Any]:
    """One monitor turn in ``span``: a model call that emits ``produced`` (a tool call), the tool's run, and a final
    verdict; served from the cache when ``cached``. Returns the tool's result message (a fresh one per run)."""
    extra = {"cache": "read"} if cached else {}
    result = s.msg("tool", "synthetic tool output", tool_call_id=call["id"], function="get_x")
    s.model(span, JUDGE, [sys_, user], produced, tools=TOOLS, **extra)
    s.tool(span, call, result)
    s.model(span, JUDGE, [sys_, user, produced, result], verdict, tools=TOOLS, **extra)
    return result


def replay_sample(*, second_scope: bool = True) -> dict[str, Any]:
    s = support.Sample()
    gen, system, user = _frame(s)
    final = s.msg("assistant", "Synthetic final answer.", source="generate", model="synthetic")
    s.model(gen, "ollama/synthetic-agent:1b", [system, user], final, tools=TOOLS)
    s.end(gen)
    s.messages.extend([system, user, final])
    call = {"id": "call_monitor_1", "function": "get_x", "arguments": {"q": "a"}, "type": "function"}
    produced = s.msg("assistant", "Checking.", source="generate", model="synthetic-judge", tool_calls=[call])
    verdict = s.msg("assistant", "Score: 0.", source="generate", model="synthetic-judge")
    first = s.span("SpanScorerA00000000000", "scorer", "max_of_2")
    sys_a, user_a = s.msg("system", "You are a monitor."), s.msg("user", "Rate the transcript.")
    _monitor(s, first, sys_a, user_a, produced, call, verdict, cached=False)
    if second_scope:
        s.end(first)
        second = s.span("SpanScorerB00000000000", "scorer", "mean_of_2")
    else:
        second = first
    sys_b, user_b = s.msg("system", "You are a monitor."), s.msg("user", "Rate the transcript.")
    _monitor(s, second, sys_b, user_b, copy.deepcopy(produced), call, copy.deepcopy(verdict), cached=True)
    s.end(second)
    return s.build()


def test_a_cached_scorer_call_owns_its_copy_and_its_results(tmp_path):
    u = run(tmp_path, replay_sample())
    holders = [m for m in u.of_kind("message") if any(p.get("t") == "tool_call" for p in m["parts"])]
    assert len(holders) == 2 and len({m["scope"] for m in holders}) == 2
    own = next(m for m in holders if cites(m, CACHED))
    calls = {c["id"]: c for c in u.of_kind("model_call")}
    assert calls[own["generated_by"]].get("status") == "cached" and calls[own["generated_by"]]["scope"] == own["scope"]
    te_by_scope = {te["scope"]: te for te in u.of_kind("tool_execution")}
    results = [m for m in u.of_kind("message") if m["role"] == "tool"]
    assert len(results) == 2
    for result in results:  # each run's result answers its own scope's call, executed once
        call_part = result["parts"][0]["responds_to"]
        assert call_part.split("#", 1)[0] in {h["id"] for h in holders if h["scope"] == result["scope"]}
        assert te_by_scope[result["scope"]]["call"] == call_part
    assert cites(te_by_scope[own["scope"]], CACHED)
    assert not codes(u) & {"call_result_link_conflict", "orphan_tool_result", "unexecuted_tool_call"}
    assert u.info.accounting.status == "consistent"


def test_a_cache_hit_in_the_producing_scope_keeps_one_message(tmp_path):
    """Fail closed to the existing reading: a cached replay inside the scope that produced the message is no new copy."""
    u = run(tmp_path, replay_sample(second_scope=False))
    holders = [m for m in u.of_kind("message") if any(p.get("t") == "tool_call" for p in m["parts"])]
    assert len(holders) == 1 and not cites(holders[0], CACHED)
