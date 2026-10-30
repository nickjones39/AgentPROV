"""The concurrency sweep's pure parts (N.2.1a(4); D-820, D-821): the ``--tune-jobs`` values, the per-call facts read
from a capture log (latency, client timeouts, usage), an arm's metrics, the stop rule and the recommendation.

Capture logs are written by the real :class:`agentprov_capture.log.CaptureLog` with an injected monotonic clock.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agentprov.cli.live import tune

ENDPOINT = {"base_url_host": "127.0.0.1", "api": "openai_chat"}


def _log(tmp_path: Path, calls: list[dict[str, Any]]) -> bytes:
    """A capture log with one request/response pair per entry of ``calls`` (``ms``: latency; ``exc``; ``usage``)."""
    from agentprov_capture.log import CaptureLog

    ticks = [0]

    def mono() -> int:
        return ticks[0]

    path = tmp_path / "s.capture.jsonl"
    blobs = tmp_path / "blobs"
    blobs.mkdir(exist_ok=True)
    log = CaptureLog(path, "0" * 32, blobs_dir=blobs, mono_ns=mono)
    log.emit("session.start", {"capture": "0.1", "session": "0" * 32, "ex": "ex_" + "0" * 32, "attempt": 0,
                               "cell": {"benchmark": "agentdojo", "suite": "banking", "task_id": "user_task_0",
                                        "attack_id": None, "attack_target_id": None, "defense_id": None,
                                        "attack_params": {}},
                               "writer": {"dist": "agentprov-capture", "version": "0.1.0"},
                               "backend": {"id": "agentdojo", "version": "0.1.0"},
                               "runtime": {"python": "3.12", "platform": "x", "lock_sha256": "0" * 64},
                               "actors": {"agent": {"kind": "llm_agent"}}, "config_sha256": "0" * 64})
    log.emit("instrumentation", {"items": []})
    log.emit("pass.start", {"env": {"sha256": "0" * 64, "canon": "jcs-rfc8785"}}, pass_=0)
    request = log.put_blob(b'{"messages": []}', "application/json")
    for i, c in enumerate(calls):
        log.emit("llm.request", {"call": f"c{i}", "role": "agent", "attempt": 0, "endpoint": ENDPOINT,
                                 "params": {"configured": {}, "transmitted": {}}, "request": request},
                 pass_=0, actor="agent")
        ticks[0] += int(c["ms"] * 1e6)
        data: dict[str, Any] = {"call": f"c{i}"}
        if "exc" in c:
            data.update(status="error", exception={"type": c["exc"], "message": "x"})
        else:
            data.update(status="kept", finish_reason="stop", response=log.put_blob(b'{"id":"r"}', "application/json"),
                        usage=c.get("usage", {}))
        log.emit("llm.response", data, pass_=0, actor="agent")
        ticks[0] += 1_000_000
    log.close("complete")
    return path.read_bytes()


@pytest.mark.parametrize("text, values", [("1,2,4,6,8,12", [1, 2, 4, 6, 8, 12]), ("4", [4]), (" 8, 2 ", [8, 2])])
def test_parse_jobs(text: str, values: list[int]) -> None:
    assert tune.parse_jobs(text) == values


@pytest.mark.parametrize("text", ["", "0", "1,1", "1,x", "-1", "1.5", ",".join(map(str, range(1, 14)))])
def test_parse_jobs_refuses(text: str) -> None:
    with pytest.raises(tune.TuneUsageError):
        tune.parse_jobs(text)
    with pytest.raises(tune.TuneUsageError):
        tune.parse_jobs("16", host_max=12)


def test_call_facts_latency_timeouts_and_usage(tmp_path: Path) -> None:
    log = _log(tmp_path, [{"ms": 120, "usage": {"prompt_tokens": 4000, "completion_tokens": 50}},
                          {"ms": 900, "exc": "APITimeoutError"}, {"ms": 30, "exc": "APIConnectionError"},
                          {"ms": 200, "usage": {"input_tokens": 10, "output_tokens": 5}}])
    facts = tune.call_facts(log)
    assert [round(x) for x in facts.latencies_ms] == [120, 900, 30, 200]
    assert (facts.timeouts, facts.errors) == (1, 1)
    assert (facts.tokens_in, facts.tokens_out) == (4010, 55)
    assert tune.call_facts(b"not json\n{}\n").unparsed == 2


def test_arm_metrics(tmp_path: Path) -> None:
    log = _log(tmp_path, [{"ms": 100, "usage": {"prompt_tokens": 100, "completion_tokens": 10}}, {"ms": 300}])
    entries = [{"session": "a", "capture_sha256": "x"}, {"session": "b", "parent_note": "timeout"}]
    arm = tune.arm_metrics(4, wall_s=1800.0, counters={"cells_planned": 2, "conclusive": 2, "failed": 0},
                           entries=entries, read_log=lambda e: log if e.get("capture_sha256") else None)
    assert arm["traces_per_hour"] == 4.0 and arm["seconds_per_cell"] == 3600.0
    assert (arm["calls"], arm["client_timeouts"], arm["cell_timeouts"], arm["request_timeouts"]) == (2, 0, 1, 1)
    assert arm["latency_ms"] == {"p50": 100.0, "p90": 300.0, "max": 300.0}
    assert arm["tokens"]["prompt"] == 100 and json.dumps(arm)  # JSON-ready


def _arm(jobs: int, rate: float | None, *, timeouts: int = 0, failed: int = 0, conclusive: int = 24) -> dict[str, Any]:
    return {"jobs": jobs, "status": "ran", "traces_per_hour": rate, "request_timeouts": timeouts,
            "cells": {"cells_planned": 24, "conclusive": conclusive, "failed": failed}}


def test_recommend_smallest_within_ninety_percent_of_peak() -> None:
    arms = [_arm(1, 10), _arm(2, 19), _arm(4, 36), _arm(6, 39), _arm(8, 40), _arm(12, 38)]
    assert tune.recommend(arms)["jobs"] == 4  # 36 >= 0.9 x 40
    assert tune.recommend(arms)["peak_traces_per_hour"] == 40


def test_timeouts_and_failures_are_never_picked_but_count_for_the_peak() -> None:
    arms = [_arm(2, 30), _arm(4, 34, timeouts=1), _arm(8, 50, failed=1)]
    rec = tune.recommend(arms)
    assert rec["peak_traces_per_hour"] == 50 and rec["jobs"] is None
    assert tune.recommend([_arm(2, 46), _arm(8, 50, failed=1)])["jobs"] == 2
    assert tune.recommend([_arm(1, 10, conclusive=23)])["jobs"] is None  # an unfinished cell
    assert tune.recommend([tune.skipped(8, "memory")])["jobs"] is None


def test_stop_rule() -> None:
    assert tune.stops_sweep(_arm(4, 30, timeouts=2)) and tune.stops_sweep(_arm(4, 30, failed=1))
    assert not tune.stops_sweep(_arm(4, 30)) and not tune.stops_sweep(tune.skipped(4, "memory"))


def test_report_markdown_escapes_the_model_id(tmp_path: Path) -> None:
    doc = tune.report_document(header={"model": {"id": "evil|`id`\u202e"}, "preset": {"name": "m5ultra", "version": 1},
                                       "sample": {"cells": ["a"]}, "order": [1], "test_only": True},
                               arms=[_arm(1, 10), tune.skipped(2, "memory")])
    text = tune.report_markdown(doc)
    assert "evil\\|'id'" in text and "\u202e" not in text and "skipped (memory)" in text
    js, md = tune.write_report(tmp_path, doc)
    assert json.loads(js.read_text())["format"] == tune.TUNE_FORMAT and md.read_text() == text


def test_arm_files_resume_only_for_the_same_configuration(tmp_path: Path) -> None:
    path = tmp_path / "jobs-4.json"
    tune.write_arm(path, "sha256:" + "a" * 64, _arm(4, 30))
    assert tune.read_arm(path, "sha256:" + "a" * 64) == _arm(4, 30)
    assert tune.read_arm(path, "sha256:" + "b" * 64) is None
    path.write_text("not json")
    assert tune.read_arm(path, "sha256:" + "a" * 64) is None
