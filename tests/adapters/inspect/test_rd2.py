"""RD-2 (core review D, routed to regen-items-2-12): regeneration-batch items 81-84 in the Inspect mapper.

- 81 (CD-24): a score event without ``scorer`` (inspect_ai < 0.3.217) takes its scorer span's name; no duplicate.
- 82 (CD-25): a non-UTC offset is converted to UTC with the original in ``t.raw`` (C.8.3); no time is dropped.
- 83 (CD-26): a dangling ground-truth attachment is reported and its keys are kept.
- 84 (CD-27): a non-string ``tool_call_id`` takes the orphan path instead of crashing the sample.

Synthetic samples only."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import inspect_support as s

from agentprov.aer.reader import load_aer_bytes


def _map(tmp_path, sample: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    (u,) = s.import_log(s.build_eval(s.synthetic_header(), {"s1_epoch_1.json": sample}), tmp_path).units
    assert not u.outcome.degenerate, u.outcome.error_code
    doc = load_aer_bytes(u.data)
    issues = list(doc.seal.get("issues", []))
    assert "adapter_defect" not in {i["code"] for i in issues}
    return list(doc.records), issues


def _judgements(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in records if r["k"] == "judgement"]


# ------------------------------------------------------------------------------------------------ item 81 (CD-24)
def _without_scorer(smp: s.Sample, sample: dict[str, Any]) -> None:
    for e in sample["events"]:
        if e["event"] == "score":
            e.pop("scorer")
            e.pop("scorer_args")


def test_a_score_event_without_scorer_is_named_by_its_scorer_span(tmp_path):
    named, _ = _map(tmp_path / "a", s.basic_sample())
    unnamed, _ = _map(tmp_path / "b", s.basic_sample(tune=_without_scorer))
    got = _judgements(unnamed)
    assert sorted(j["name"] for j in got) == ["combined_scorer.refusal", "combined_scorer.score"]  # no duplicates
    want = {j["name"]: j for j in _judgements(named)}
    for j in got:
        assert (j["actor"], j.get("generated_by"), j["value"]) == (want[j["name"]]["actor"],
                                                                   want[j["name"]].get("generated_by"), want[j["name"]]["value"])
        assert "/name" not in j.get("unk", {})


def test_a_score_event_outside_a_scorer_span_keeps_an_ambiguous_name(tmp_path):
    def tune(smp: s.Sample, sample: dict[str, Any]) -> None:
        _without_scorer(smp, sample)
        for e in sample["events"]:
            if e["event"] == "score":
                e["span_id"] = "SpanScorers00000000000"  # the enclosing `scorers` span is not a scorer span

    got = _judgements(_map(tmp_path, s.basic_sample(tune=tune))[0])
    event_born = [j for j in got if j["name"].startswith("score.")]
    assert sorted(j["name"] for j in event_born) == ["score.refusal", "score.score"]
    assert all(j["unk"]["/name"] == "ambiguous" for j in event_born)


# ------------------------------------------------------------------------------------------------ item 82 (CD-25)
_INSTANT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:]{8}\.[0-9]{6}\+00:00")
_LOCAL = timezone(timedelta(hours=-7))


def _shift(value: Any) -> Any:
    """Every recorded instant at the same moment, written with a -07:00 offset."""
    if isinstance(value, str) and _INSTANT.fullmatch(value):
        return datetime.fromisoformat(value).astimezone(_LOCAL).isoformat(timespec="microseconds")
    if isinstance(value, dict):
        return {k: _shift(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_shift(v) for v in value]
    return value


def _times(records: list[dict[str, Any]]) -> dict[str, tuple[Any, ...]]:
    return {r["id"]: ({k: v for k, v in r.get("t", {}).items() if k != "raw"}, r.get("after"),
                      {p: v for p, v in r.get("unk", {}).items() if p.startswith("/t/")})
            for r in records if "id" in r}


def test_a_non_utc_offset_is_converted_and_kept_in_raw(tmp_path):
    utc, _ = _map(tmp_path / "utc", s.basic_sample())
    local, _ = _map(tmp_path / "local", _shift(s.basic_sample()))
    assert _times(local) == _times(utc)  # same instants, same time edges, nothing declared unknown or dropped
    assert any(r.get("after") for r in local)
    converted = 0
    for r in local:
        t = r.get("t", {})
        for slot in ("start", "end"):
            if slot in t:
                raw = t["raw"][slot]
                assert raw.endswith("-07:00")
                assert datetime.fromisoformat(raw).astimezone(UTC) == datetime.fromisoformat(t[slot])
                converted += 1
    assert converted > 0
    spans = [r for r in local if r["k"] == "scope" and r.get("t", {}).get("raw")]
    assert spans and all("end" in r["t"] and "end" in r["t"]["raw"] for r in spans)
    (state,) = [r for r in local if r["k"] == "state_change" and r["target"] == "other"]
    assert state["t"]["end"] and state["t"]["raw"]["end"].endswith("-07:00")


def test_a_utc_log_is_unchanged_by_the_conversion(tmp_path):
    records, _ = _map(tmp_path, s.basic_sample())
    assert not any(r.get("t", {}).get("raw") for r in records)


# ------------------------------------------------------------------------------------------------ item 83 (CD-26)
def test_a_dangling_ground_truth_reference_is_reported_and_kept(tmp_path):
    def tune(smp: s.Sample, sample: dict[str, Any]) -> None:
        sample["metadata"]["target_functions"] = "attachment://deadbeefdeadbeefdeadbeefdeadbeef"

    records, issues = _map(tmp_path, s.basic_sample(tune=tune))
    assert ("dangling_source_ref", "/metadata") in {(i["code"], i.get("detail")) for i in issues}
    assert not [r for r in records if r["k"] == "fixture" and r["kind"] == "ground_truth"]
    kept = records[0]["ext"]["inspect"]["sample_metadata"]
    assert kept["grading_function"] == "grade_x" and "target_functions" in kept


def test_a_resolved_ground_truth_stays_a_fixture(tmp_path):
    records, _ = _map(tmp_path, s.basic_sample())
    (fx,) = [r for r in records if r["k"] == "fixture" and r["kind"] == "ground_truth"]
    assert fx["content"] == {"target_functions": ["get_x"], "grading_function": "grade_x"}
    assert "grading_function" not in json.dumps(records[0].get("ext", {}))


# ------------------------------------------------------------------------------------------------ item 84 (CD-27)
def test_an_unhashable_tool_call_id_takes_the_orphan_path(tmp_path):
    def tune(smp: s.Sample, sample: dict[str, Any]) -> None:
        for m in [*sample["messages"], *sample["events_data"]["messages"]]:
            if m["role"] == "tool":
                m["tool_call_id"] = ["call_synthetic_1"]

    records, issues = _map(tmp_path, s.basic_sample(tune=tune))
    assert "orphan_tool_result" in {i["code"] for i in issues}
    assert any(r["k"] == "message" for r in records)


def test_a_recorded_start_after_its_end_is_ambiguous_not_a_defect(tmp_path):
    """Seen in whistlebench (10 of 1,850 rehearsal samples): at one local offset, a span and a model call record an end an
    hour before their start. Neither instant is asserted; both stay verbatim, declared ambiguous; no time edge uses them."""
    sample = _shift(s.basic_sample())
    model = next(e for e in sample["events"] if e["event"] == "model")
    began = datetime.fromisoformat(model["timestamp"])
    model["completed"] = (began - timedelta(hours=1)).isoformat(timespec="microseconds")
    records, _ = _map(tmp_path, sample)
    (mc,) = [r for r in records if r["k"] == "model_call" and r["t"].get("raw", {}).get("start") == model["timestamp"]]
    assert "start" not in mc["t"] and "end" not in mc["t"]
    assert mc["t"]["raw"] == {"start": model["timestamp"], "end": model["completed"]}
    assert mc["unk"]["/t/start"] == "ambiguous" and mc["unk"]["/t/end"] == "ambiguous"
    assert not any(a.get("b") == "time" for a in mc.get("after", ()))
    assert not any(a == {"b": "time", "id": mc["id"]} for r in records for a in r.get("after", ()))
