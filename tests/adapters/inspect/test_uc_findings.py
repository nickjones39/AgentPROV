"""Review-uncovered findings in the Inspect mapper (2026-11-01; 0.2.0 change batch D-1063, regeneration-batch item
174): UC-39 (counts, durations and times outside the AER's ranges reached typed fields, so the writer refused the
sample) and UC-42 (type confusion, non-conforming state patches and deny-listed header strings). Synthetic data only."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import inspect_support as support
import pytest

I_JSON_MAX = 2**53 - 1


def _one(tmp_path: Path, sample: dict[str, Any], header: dict[str, Any] | None = None) -> tuple[support.Imported,
                                                                                                  support.Unit]:
    data = support.build_eval(header or support.synthetic_header(), {"s1_epoch_1.json": sample})
    imp = support.import_log(data, tmp_path)
    assert imp.register == [], imp.register
    (unit,) = imp.units
    return imp, unit


def _ok(imp: support.Imported, unit: support.Unit) -> None:
    assert not unit.outcome.degenerate and "adapter_defect" not in unit.issue_codes(), unit.issue_codes()
    report = imp.validate(unit)
    assert report.ok, [(f.code, f.pointer) for f in report.errors]


def _tuned(tune: Any) -> dict[str, Any]:
    return support.basic_sample("s1", tune=tune)


def test_the_control_sample_seals(tmp_path):
    _ok(*_one(tmp_path, support.basic_sample("s1")))


# ------------------------------------------------------------------------------------------------ UC-39
@pytest.mark.parametrize("value", ["2026-16-21T00:00:01.000000+00:00", "2026-08-21T24:00:01Z",
                                   "2026-08-32T00:00:01.5Z"])
def test_a_time_outside_the_aer_ranges_is_not_a_typed_time(tmp_path, value: str):
    def tune(s: support.Sample, sample: dict[str, Any]) -> None:
        sample["started_at"] = value

    imp, unit = _one(tmp_path, _tuned(tune))
    _ok(imp, unit)
    run = unit.by_id()["run"]
    assert "start" not in run.get("t", {})


@pytest.mark.parametrize("value", [2**53, 2**60, 9.1e15])
def test_a_total_time_beyond_the_i_json_range_is_kept_verbatim_not_typed(tmp_path, value: float):
    def tune(s: support.Sample, sample: dict[str, Any]) -> None:
        sample["total_time"] = value

    imp, unit = _one(tmp_path, _tuned(tune))
    _ok(imp, unit)
    run = unit.by_id()["run"]
    assert "dur_s" not in run.get("t", {})
    assert "total_time" in run["ext"]["inspect"]


def test_a_usage_count_beyond_the_i_json_range_stays_in_ext(tmp_path):
    def tune(s: support.Sample, sample: dict[str, Any]) -> None:
        for e in sample["events"]:
            if e["event"] == "model":
                e["output"]["usage"]["input_tokens"] = 2**53
                break

    imp, unit = _one(tmp_path, _tuned(tune))
    _ok(imp, unit)
    mc = unit.of_kind("model_call")[0]
    assert "input_tokens" not in mc["usage"] and mc["usage"]["output_tokens"] == 5
    assert mc["ext"]["inspect"]["usage_extra"]["input_tokens"] == {"$int": str(2**53)}


# ------------------------------------------------------------------------------------------------ UC-42
def test_a_span_type_that_is_not_a_string_does_not_crash_the_mapper(tmp_path):
    def tune(s: support.Sample, sample: dict[str, Any]) -> None:
        for e in sample["events"]:
            if e["event"] == "span_begin" and e["type"] == "scorers":
                e["type"] = ["scorers"]

    imp, unit = _one(tmp_path, _tuned(tune))
    _ok(imp, unit)


def test_a_message_id_that_is_not_a_string_does_not_crash_the_call_sharing(tmp_path):
    def tune(s: support.Sample, sample: dict[str, Any]) -> None:
        for m in [*sample["messages"], *sample["events_data"]["messages"]]:
            if m["role"] == "assistant" and m.get("tool_calls"):
                m["id"] = ["not", "a", "string"]

    imp, unit = _one(tmp_path, _tuned(tune))
    assert "adapter_defect" not in unit.issue_codes(), unit.issue_codes()


@pytest.mark.parametrize("changes", [[{"op": "frobnicate", "path": "/messages/2"}],
                                     [{"op": "add", "path": "messages/2", "value": 1}],
                                     [{"op": ["add"], "path": "/x"}],
                                     [{"path": "/x", "value": 1}],
                                     ["add /x"]])
def test_a_non_conforming_state_patch_is_kept_verbatim_and_declared_ambiguous(tmp_path, changes: list[Any]):
    def tune(s: support.Sample, sample: dict[str, Any]) -> None:
        for e in sample["events"]:
            if e["event"] == "state":
                e["changes"] = changes

    imp, unit = _one(tmp_path, _tuned(tune))
    _ok(imp, unit)
    [st] = unit.of_kind("state_change")
    assert "patch" not in st and st["unk"]["/patch"] == "ambiguous"
    assert st["ext"]["inspect"]["changes"] == changes


def test_a_conforming_state_patch_is_still_the_patch(tmp_path):
    imp, unit = _one(tmp_path, support.basic_sample("s1"))
    [st] = unit.of_kind("state_change")
    assert st["patch"] == [{"op": "add", "path": "/messages/2", "value": {"role": "assistant"}}]


@pytest.mark.parametrize("member,value", [("model", "none"), ("model", "-"), ("task_version", "none"),
                                          ("task_version", "unknown"), ("task", "n/a")])
def test_a_deny_listed_header_string_is_not_a_typed_value(tmp_path, member: str, value: str):
    header = support.synthetic_header()
    header["eval"][member] = value
    imp, unit = _one(tmp_path, support.basic_sample("s1"), header)
    _ok(imp, unit)
