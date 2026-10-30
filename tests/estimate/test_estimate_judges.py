"""D-770: the estimate of an Inspect plan: cells of samples × epochs, the scorer's judge calls priced at the judge
model, the shipped priors that count judge calls among the agent's, and the D-740 bound shown per sample.

Synthetic fixtures only."""

from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from agentprov.estimate import plan as P
from agentprov.estimate.cost import (
    BENIGN,
    INSPECT_KIND,
    NO_ATTACK,
    CellStats,
    JudgeStats,
    PlanCell,
    Quantiles,
    estimate,
)
from agentprov.estimate.prices import Price

TODAY = dt.date(2026, 10, 23)
AGENT = Price("openai", "agent-m", Decimal(1), Decimal(10), None, "s", TODAY)
JUDGE = Price("openai", "judge-m", Decimal(2), Decimal(20), None, "s", TODAY)
JUDGES = JudgeStats(Quantiles(1, 2), Quantiles(400, 800), Quantiles(300, 600))
STATS = CellStats(Quantiles(2, 4), Quantiles(1000, 2000), Quantiles(0, 0), Quantiles(100, 200), Quantiles(60, 120),
                  "corpus", judges=JUDGES)
CELL = PlanCell("inspect_evals/agentharm", None, INSPECT_KIND, 0, executions=3, parallel=3)


def _cost(tin: int, tout: int, price: Price) -> Decimal:
    return (Decimal(tin) * price.input + Decimal(tout) * price.output) / 10**6


# ------------------------------------------------------------------------------------------------------ the plan
def _inspect_plan(**over: Any) -> bytes:
    doc: dict[str, Any] = {
        "format": "agentprov-run-dry-plan/0.1", "plan_sha256": "0" * 64, "backend": "inspect-agentharm", "repeats": 1,
        "max_attempts": 3, "units": 2, "settled": 0, "attempts_due": 6, "benchmark_version": "",
        "cells": [{"cell_key": "k1", "suite": None, "kind": None, "attack": None, "user_task_id": None,
                   "injection_task_id": None, "settled": 0, "task": "inspect_evals/agentharm", "samples": 2},
                  {"cell_key": "k2", "suite": None, "kind": None, "attack": None, "user_task_id": None,
                   "injection_task_id": None, "settled": 0, "task": "inspect_evals/agentharm", "samples": 1}],
        "inspect": {"task": "inspect_evals/agentharm", "epochs": 2, "message_limit": 10, "max_connections": 3,
                    "judges": {"refusal_judge": "judge-m", "semantic_judge": "judge-m"}},
    }  # fmt: skip
    doc.update(over)
    return json.dumps(doc).encode()


def test_an_inspect_plan_becomes_cells_of_samples_times_epochs() -> None:
    plan = P.parse_plan(_inspect_plan())
    assert plan.inspect is not None and plan.inspect.judges == (("refusal_judge", "judge-m"),
                                                                ("semantic_judge", "judge-m"))
    assert [(c.suite, c.attack, c.kind, c.executions, c.parallel) for c in plan.cells] == [
        ("inspect_evals/agentharm", None, INSPECT_KIND, 4, 3), ("inspect_evals/agentharm", None, INSPECT_KIND, 2, 2)]
    assert plan.to_json()["inspect"]["samples"] == 3 and plan.to_json()["inspect"]["epochs"] == 2


@pytest.mark.parametrize("over", [
    {"inspect": {"task": "t", "epochs": 1, "max_connections": 1}},  # no judges table
    {"inspect": {"task": "t", "epochs": 1, "max_connections": 1, "judges": {"r": 3}}},  # a judge that is not a model
    {"inspect": ["not", "a", "table"]},
    {"cells": [{"cell_key": "k", "suite": None, "kind": None, "settled": 0, "samples": 2}]},  # no task
    {"cells": [{"cell_key": "k", "suite": None, "kind": None, "settled": 0, "task": "t", "samples": -1}]},
])
def test_a_malformed_inspect_plan_is_refused(over: dict[str, Any]) -> None:
    with pytest.raises(P.PlanError):
        P.parse_plan(_inspect_plan(**over))


def test_the_dry_plan_carries_the_inspect_table_escaped() -> None:
    from agentprov.cli.run import _plan_json_inspect

    hostile = "judge" + chr(0x202E) + "x"
    config = {"task": "inspect_evals/agentharm", "epochs": 2, "max_connections": 4,
              "limits": {"message_limit": 10, "token_limit": 20000},
              "judges": {"refusal_judge": {"model_requested": hostile}, "semantic_judge": {"model_requested": "m"}}}
    got = _plan_json_inspect(config)
    assert got is not None and got["epochs"] == 2 and got["message_limit"] == 10 and got["max_connections"] == 4
    assert chr(0x202E) not in got["judges"]["refusal_judge"] and got["judges"]["semantic_judge"] == "m"
    assert _plan_json_inspect({"repeats": 1}) is None  # an AgentDojo-family backend config


# ------------------------------------------------------------------------------------------------------ pricing
def test_judge_calls_are_priced_at_the_judge_model() -> None:
    e = estimate([CELL], repeats=1, attempts_due=1, jobs=1, price=AGENT, stats_for=lambda *_: STATS, preflight=False,
                 today=TODAY, judged=True, judge_price=JUDGE)
    assert e.cost_p50 == 3 * 2 * _cost(1000, 100, AGENT) + 3 * 1 * _cost(400, 300, JUDGE)
    assert e.cost_p90 == 3 * 4 * _cost(2000, 200, AGENT) + 3 * 2 * _cost(800, 600, JUDGE)
    assert e.calls_p50 == 3 * (2 + 1) and e.calls_p90 == 3 * (4 + 2)  # billed calls: the agent's and the judges'
    assert e.seconds_p50 == 60 and e.seconds_p90 == 120  # three samples, three at a time: one sample's time
    assert [g.label for g in e.by_attack] == [NO_ATTACK] and NO_ATTACK != BENIGN
    assert e.cost_worst is not None and e.cost_worst >= e.cost_p90
    assert not e.warnings


def test_samples_beyond_the_concurrency_take_longer() -> None:
    cell = PlanCell("t", None, INSPECT_KIND, 0, executions=4, parallel=2)
    e = estimate([cell], repeats=1, attempts_due=1, jobs=1, price=AGENT, stats_for=lambda *_: STATS, preflight=False,
                 judged=True, judge_price=AGENT)
    assert e.seconds_p50 == 2 * 60


def test_without_judges_the_judge_statistics_are_ignored() -> None:
    e = estimate([PlanCell("banking", None, "user_task", 0)], repeats=1, attempts_due=1, jobs=1, price=AGENT,
                 stats_for=lambda *_: STATS, preflight=False, today=TODAY)
    assert e.cost_p50 == 2 * _cost(1000, 100, AGENT) and e.calls_p50 == 2 and [g.label for g in e.by_attack] == [BENIGN]


def test_statistics_that_count_judges_with_the_agent_are_priced_at_the_agent_price() -> None:
    mixed = CellStats(Quantiles(3, 7), Quantiles(600, 2000), Quantiles(0, 0), Quantiles(300, 600), Quantiles(30, 100),
                      "priors", judges_in_calls=True)
    same = estimate([CELL], repeats=1, attempts_due=1, jobs=1, price=AGENT, stats_for=lambda *_: mixed,
                    preflight=False, today=TODAY, judged=True, judge_price=AGENT)
    assert same.cost_p50 == 3 * 3 * _cost(600, 300, AGENT) and not same.warnings  # the same price: nothing to say
    other = estimate([CELL], repeats=1, attempts_due=1, jobs=1, price=AGENT, stats_for=lambda *_: mixed,
                     preflight=False, today=TODAY, judged=True, judge_price=JUDGE)
    assert other.cost_p50 == same.cost_p50 and any("priced at the agent's model" in w for w in other.warnings)


def test_missing_judge_statistics_or_price_are_warnings_not_guesses() -> None:
    bare = CellStats(Quantiles(2, 4), Quantiles(1000, 2000), Quantiles(0, 0), Quantiles(100, 200), Quantiles(60, 120),
                     "default")
    e = estimate([CELL], repeats=1, attempts_due=1, jobs=1, price=AGENT, stats_for=lambda *_: bare, preflight=False,
                 today=TODAY, judged=True, judge_price=AGENT)
    assert e.calls_p50 == 3 * 2 and any("no judge-call statistics" in w for w in e.warnings)
    unpriced = estimate([CELL], repeats=1, attempts_due=1, jobs=1, price=AGENT, stats_for=lambda *_: STATS,
                        today=TODAY, judged=True, judge_price=None)
    body = unpriced.to_json(TODAY)
    assert unpriced.cost_p50 is None and unpriced.cost_worst is None and body["by_suite"][0]["cost_p50"] is None
    assert any("No price for the judge model" in w for w in unpriced.warnings)


# ------------------------------------------------------------------------------------------------------ counts
def _records(judge_usage: dict[str, int] | None) -> list[dict[str, Any]]:
    judge_call: dict[str, Any] = {"k": "model_call", "id": "j1", "actor": "judge-0", "role": "auxiliary", "input": []}
    if judge_usage is not None:
        judge_call["usage"] = judge_usage
    return [
        {"k": "execution", "aer": "0.2", "ex": "ex_t", "task": {"benchmark": "agentharm",
                                                                "suite": "inspect_evals/agentharm"}},
        {"k": "actor", "id": "agent", "kind": "llm_agent", "model": {"requested": "m-1", "provider": "openai"}},
        {"k": "actor", "id": "judge-0", "kind": "judge", "model": {"requested": "judge-m"}},
        {"k": "model_call", "id": "c1", "actor": "agent", "input": [],
         "usage": {"input_tokens": 1000, "output_tokens": 50}},
        {"k": "model_call", "id": "c2", "actor": "agent", "input": [],
         "usage": {"input_tokens": 1200, "output_tokens": 70}},
        judge_call,
    ]


def test_judge_calls_are_counted_apart_from_the_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    from agentprov.estimate import usage

    monkeypatch.setattr(usage, "iter_records", lambda _path: iter(_records({"input_tokens": 400,
                                                                             "output_tokens": 300})))
    u = usage.execution_usage("unused")
    assert u is not None and u.calls == 2 and u.tokens_in == (1000, 1200)
    assert u.judge_tokens_in == (400,) and u.judge_tokens_out == (300,)
    stats = usage.aggregate([u, u])[("agentharm", "inspect_evals/agentharm", "", "m-1", "")]
    assert (stats.calls_p50, stats.judge_calls_p50, stats.judge_tokens_in_p50, stats.judge_tokens_out_p90) == \
        (2, 1, 400, 300)
    assert set(usage.JUDGE_FIELDS) <= set(stats.to_json())


def test_a_judge_call_without_usage_is_estimated_from_its_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    from agentprov.estimate import usage

    records = _records(None)
    records.insert(3, {"k": "message", "id": "m1", "parts": [{"text": "x" * 40}]})
    records[-1]["input"] = ["m1"]
    monkeypatch.setattr(usage, "iter_records", lambda _path: iter(records))
    u = usage.execution_usage("unused")
    assert u is not None and u.judge_tokens_in == (10,) and u.basis == "mixed"


def test_executions_without_judges_keep_their_columns(monkeypatch: pytest.MonkeyPatch) -> None:
    from agentprov.estimate import usage

    records = [r for r in _records({"input_tokens": 1, "output_tokens": 1}) if r.get("id") not in ("judge-0", "j1")]
    monkeypatch.setattr(usage, "iter_records", lambda _path: iter(records))
    u = usage.execution_usage("unused")
    assert u is not None and u.calls == 2 and u.judge_tokens_in == ()
    stats = next(iter(usage.aggregate([u]).values()))
    assert stats.judge_calls_p50 is None and not set(usage.JUDGE_FIELDS) & set(stats.to_json())


def test_priors_rows_with_and_without_the_judge_split(tmp_path: Path) -> None:
    from agentprov.estimate.priors import PRIORS_FORMAT, StatsSource, load_priors

    base = {"benchmark": "agentharm", "attack": None, "family": None, "backend": None, "basis": "usage",
            "executions": 9, "calls": 27, "calls_p50": 3, "calls_p90": 7, "tokens_in_p50": 600, "tokens_in_p90": 2000,
            "tokens_cached_p50": 0, "tokens_cached_p90": 0, "tokens_out_p50": 300, "tokens_out_p90": 600}
    split = {**base, "suite": "split", "judge_calls_p50": 1, "judge_calls_p90": 2, "judge_tokens_in_p50": 350,
             "judge_tokens_in_p90": 700, "judge_tokens_out_p50": 320, "judge_tokens_out_p90": 640}
    path = tmp_path / "priors.json"
    path.write_text(json.dumps({"format": PRIORS_FORMAT, "built_from": {}, "rows": [{**base, "suite": "old"}, split]}))
    source = StatsSource(benchmark="agentharm", model=None, priors=load_priors(path)[1])
    old, new = source("old", None, INSPECT_KIND), source("split", None, INSPECT_KIND)
    assert old.judges is None and old.judges_in_calls
    assert new.judges == JudgeStats(Quantiles(1, 2), Quantiles(350, 700), Quantiles(320, 640))
    assert not new.judges_in_calls


# ------------------------------------------------------------------------------------------------------ the CLI
def test_the_d740_bound_per_sample() -> None:
    from agentprov.cli.estimate import _sample_call_bound

    info = P.InspectInfo("inspect_evals/agentharm", 1, 10, 4, ())
    assert _sample_call_bound("inspect-agentharm", info) == 42  # (9 x 2 + 3) x 2: D-740's worked figure
    assert _sample_call_bound("inspect-agentharm", P.InspectInfo("other/task", 1, 10, 4, ())) is None
    assert _sample_call_bound("inspect-agentharm", P.InspectInfo("inspect_evals/agentharm", 1, None, 4, ())) is None
    assert _sample_call_bound("no-such-backend", info) is None


def test_judge_prices_at_the_agent_endpoint(tmp_path: Path) -> None:
    from agentprov.cli.estimate import _judge_price

    warnings: list[str] = []
    assert _judge_price(tmp_path, {"r": "agent-m"}, real=True, endpoint="openai", model_id="agent-m", price=AGENT,
                        warnings=warnings) is AGENT and not warnings
    assert _judge_price(tmp_path, {"r": "x"}, real=False, endpoint=None, model_id=None, price=AGENT,
                        warnings=warnings) is AGENT
    two = _judge_price(tmp_path, {"r": "gpt-4o-mini", "s": "gpt-4o"}, real=True, endpoint="openai",
                       model_id="agent-m", price=AGENT, warnings=warnings)
    assert two is not None and two.model.endswith("gpt-4o") and any("dearest" in w for w in warnings)
    warnings.clear()
    assert _judge_price(tmp_path, {"r": "no-such-model-x"}, real=True, endpoint="openai", model_id="agent-m",
                        price=AGENT, warnings=warnings) is None
    assert any("No price for the judge model" in w and "no-such-model-x" in w for w in warnings)


def test_the_text_form_shows_the_inspect_line() -> None:
    from agentprov.cli.estimate import text_lines

    plan = P.parse_plan(_inspect_plan())
    e = estimate(plan.cells, repeats=1, attempts_due=6, jobs=1, price=AGENT, stats_for=lambda *_: STATS,
                 today=TODAY, judged=True, judge_price=JUDGE)
    doc = {"transport": "http", "jobs": 1, "plan": {**plan.to_json()}, **e.to_json(TODAY)}
    doc["plan"]["inspect"]["calls_bound_per_sample"] = 42
    line = next(x for x in text_lines(doc) if x.startswith("Inspect "))
    assert "3 sample(s) × 2 epoch(s)" in line and "refusal_judge judge-m" in line and "42 billed calls" in line
