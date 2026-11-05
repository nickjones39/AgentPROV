"""Review UC-39 in the agentdojo family (2026-11-01; 0.2.0 change batch D-1063, regeneration-batch item 174): a count,
duration or time outside the AER's ranges reached a typed field, so the writer refused the whole execution. As item 96
(a negative duration), an out-of-range duration stays verbatim in ``t.raw.dur`` declared ``ambiguous``; a capture
count beyond the I-JSON range is not typed; a capture time outside the AER's field ranges, or an interval whose
recorded start is after its end, is no typed time. Synthetic data only."""

from __future__ import annotations

import json
from typing import Any

import pytest
from agentdojo_support import map_log, new_log
from source_support import ok
from test_r10j45 import _drift, _run
from test_rescont import container, one, row
from test_uc_capture_findings import _ok, _seal, _session

I_JSON_MAX = 2**53 - 1
OUT_OF_RANGE = [2**53, 2**60, 9.1e15]


@pytest.mark.parametrize("duration", OUT_OF_RANGE)
def test_a_tracelogger_duration_beyond_the_i_json_range_is_kept_raw_and_ambiguous(duration: Any):
    m = map_log(new_log(duration=duration))
    ok(m)
    run = m.get("run")
    assert run["t"] == {"raw": {"dur": json.dumps(duration)}} and run["unk"]["/t/dur_s"] == "ambiguous"


def test_a_tracelogger_duration_at_the_i_json_bound_is_unchanged():
    run = map_log(new_log(duration=I_JSON_MAX)).get("run")
    assert run["t"] == {"dur_s": I_JSON_MAX, "dur_clock": "wall"}


def test_a_drift_duration_beyond_the_i_json_range_is_kept_raw_and_ambiguous():
    def edit(doc: dict[str, Any]) -> None:
        doc["duration"] = 2**53

    run = _run(_drift(edit)[0])
    assert run["t"] == {"raw": {"dur": str(2**53)}} and run["unk"]["/t/dur_s"] == "ambiguous"


@pytest.mark.parametrize("duration", [-0.5, *OUT_OF_RANGE])
def test_a_results_row_duration_outside_the_aer_range_is_kept_raw_and_ambiguous(duration: Any):
    m = one(container([row(duration=duration)]))
    assert not m.outcome.degenerate and "adapter_defect" not in m.codes, m.codes
    report = m.validate()
    assert report.ok, [(f.code, f.pointer) for f in report.errors]
    run = m.get("run")
    assert run["t"] == {"raw": {"dur": json.dumps(duration)}} and run["unk"]["/t/dur_s"] == "ambiguous"


def test_a_results_row_duration_in_range_is_unchanged():
    run = one(container([row(duration=2.5)])).get("run")
    assert run["t"] == {"dur_s": 2.5, "dur_clock": "wall"} and "/t/dur_s" not in run["unk"]


# ------------------------------------------------------------------------------------------------ capture
# A verified capture event is JCS (C.13.2, cap.chain.not_jcs), so it cannot hold an integer beyond the I-JSON range; its
# ts is checked against the AER's field ranges by the chain verifier (cap.chain.bad_envelope). The tests below pin both.
@pytest.mark.parametrize("ts", ["2026-10-07T12:00:61.000000Z", "2026-13-07T12:00:01.000000Z",
                                "2026-10-07T24:00:01.000000Z"])
def test_a_capture_time_outside_the_aer_ranges_is_not_typed(ts: str):
    s = _session()
    lines = s.lines()
    s.lines = lambda: _retimed(lines, {"llm.response": ts})  # type: ignore[method-assign]
    m = _seal(s)
    _ok(m)
    assert "end" not in m.get("mc0").get("t", {})


def test_a_capture_interval_whose_wall_clock_went_backwards_is_ambiguous():
    """The wall clock can step back between two events (an NTP step); the monotonic offsets still order them."""
    s = _session()
    lines = s.lines()
    s.lines = lambda: _retimed(lines, {"llm.response": "2026-10-07T11:59:59.000000Z"})  # type: ignore[method-assign]
    m = _seal(s)
    _ok(m)
    t = m.get("mc0")["t"]
    assert "start" not in t and "end" not in t
    assert t["raw"] == {"start": "2026-10-07T12:00:04.000000Z", "end": "2026-10-07T11:59:59.000000Z"}
    assert m.get("mc0")["unk"]["/t/start"] == "ambiguous" and m.get("mc0")["unk"]["/t/end"] == "ambiguous"
    assert t["mono_start_ns"] < t["mono_end_ns"]


def _retimed(lines: list[bytes], new_ts: dict[str, str]) -> list[bytes]:
    """The log with the first event of each named type given another ``ts``, the hash chain recomputed."""
    import hashlib

    import rfc8785

    out: list[bytes] = []
    prev = None
    done: set[str] = set()
    for line in lines:
        event = json.loads(line)
        if event["type"] in new_ts and event["type"] not in done:
            event["ts"] = new_ts[event["type"]]
            done.add(event["type"])
        event["prev"] = prev
        data = rfc8785.dumps(event) + b"\n"
        out.append(data)
        prev = hashlib.sha256(data).hexdigest()
    return out
