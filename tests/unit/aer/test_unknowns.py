"""K.5.1 items 8-10 (C.7): the closed reason list, ``unk``/value conflicts, the sentinel ban, null vs empty."""

from __future__ import annotations

from typing import Any

import pytest
from aer_support import codes_of, edit, example_records, insert_after, validate_example

from agentprov.aer.types import UNKNOWN_REASONS


def run(records: list[dict[str, Any]], **kw: Any) -> list[str]:
    return codes_of(validate_example(records, **kw))


def test_seven_reasons_in_the_order_of_c71() -> None:
    assert UNKNOWN_REASONS == (
        "not_recorded", "lost", "overwritten", "withheld", "ambiguous", "not_captured", "not_applicable",
    )


@pytest.mark.parametrize("reason", UNKNOWN_REASONS)
def test_each_reason_is_accepted_on_an_absent_field(reason: str) -> None:
    assert run(edit(example_records(), "mc0", unk={"/finish_reason": reason})) == []


@pytest.mark.parametrize("reason", ["unknown", "redacted", "Lost", "", "none", 3, None])
def test_other_reasons_are_aer_unk_reason(reason: Any) -> None:
    assert "aer.unk.reason" in run(edit(example_records(), "mc0", unk={"/finish_reason": reason}))


def test_in_place_redaction_is_overwritten() -> None:
    dc = {"k": "decision", "id": "dc0", "ev": "I", "rule": ["tst.i@1"], "actor": "agent", "subject": "te0",
          "verdict": "redact", "unk": {"/original": "overwritten"}}
    assert run(insert_after(example_records(), "te0", dc)) == []


def test_a_value_beside_an_unk_entry_is_a_conflict_except_for_ambiguous() -> None:
    assert "aer.unk.conflict" in run(edit(example_records(), "mc0", finish_reason="stop", unk={"/finish_reason": "not_recorded"}))
    assert "aer.unk.conflict" in run(edit(example_records(), "mc0", unk={"/status": "lost"}))
    ok = edit(example_records(), "mc0", finish_reason="stop", unk={"/finish_reason": "ambiguous"})
    assert "aer.unk.conflict" not in run(ok)
    # declaring a whole object unknown covers its members and the object must then be absent
    assert "aer.unk.conflict" in run(edit(example_records(), "run", t={"dur_s": 1.0, "dur_clock": "wall"}, unk={"/t": "not_recorded"}))


def test_ambiguous_may_keep_the_verbatim_value() -> None:
    parts = [{"t": "text", "text": ""}, {"t": "tool_call", "name": "lookup", "args": {}, "provider_call_id": ""}]
    recs = edit(example_records(), "m1", parts=parts,
                unk={"/parts/0/text": "ambiguous", "/parts/1/provider_call_id": "ambiguous"},
                rule=["tst.d@1#/parts/0/text", "tst.d@1#/parts/1/provider_call_id"])
    assert run(recs) == []


# ------------------------------------------------------------------------------------------------ sentinels
@pytest.mark.parametrize("stub", ["0", "", "unknown", "NONE", "null", "n/a", "NA", "-"])
def test_placeholders_in_typed_time_fields_are_aer_sentinel(stub: str) -> None:
    found = run(edit(example_records(), "run", t={"start": stub}))
    assert "aer.sentinel" in found and "aer.schema.pattern" not in found


def test_a_malformed_non_sentinel_time_is_a_pattern_error() -> None:
    assert "aer.schema.pattern" in run(edit(example_records(), "run", t={"start": "yesterday"}))
    assert "aer.schema.pattern" in run(edit(example_records(), "run", t={"start": "2026-10-08T12:00:00+00:00"}))  # not Z
    assert run(edit(example_records(), "run", t={"start": "2026-10-08T12:00:00.123456Z"})) == []


@pytest.mark.parametrize("stub", ["", "unknown", "0", "None", "-"])
def test_placeholders_in_typed_string_fields(stub: str) -> None:
    assert "aer.sentinel" in run(edit(example_records(), "agent", version=stub))
    assert "aer.sentinel" in run(edit(example_records(), "agent", model={"requested": stub}))
    assert "aer.sentinel" in run(edit(example_records(), "exec", task={"benchmark": "tst", "task_id": stub}))
    assert "aer.sentinel" in run(edit(example_records(), "te0", name=stub))


def test_empty_string_standing_in_for_a_null_text_is_a_sentinel() -> None:
    parts = [{"t": "text", "text": ""}, {"t": "tool_call", "name": "lookup", "args": {}}]
    assert "aer.sentinel" in run(edit(example_records(), "m1", parts=parts))
    # declared ambiguous (release null-as-empty) it is valid; null stays valid
    declared = edit(example_records(), "m1", parts=parts, unk={"/parts/0/text": "ambiguous"}, rule=["tst.d@1#/parts/0/text"])
    assert run(declared) == []
    # an empty tool output is a recorded value, not a sentinel
    empty_tool = edit(example_records(), "m2", parts=[{"t": "tool_result", "responds_to": "m1#1", "text": ""}])
    assert "aer.sentinel" not in run(empty_tool)


def test_zero_standing_in_for_unknown_usage_is_a_sentinel() -> None:
    zero = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    assert "aer.sentinel" in run(edit(example_records(), "mc0", usage=zero))
    assert "aer.sentinel" not in run(edit(example_records(), "mc0", usage={"input_tokens": 0, "output_tokens": 5}))
    assert "aer.sentinel" not in run(edit(example_records(), "mc0", usage={"calls": 0}))


def test_the_baseline_timing_stub_is_valid_only_as_verbatim_raw_with_unk() -> None:
    stub = {"raw": {"start": "0", "end": "0"}}
    recs = edit(example_records(), "te0", t=stub["raw"] and {"raw": {"start": "0", "end": "0"}},
                unk={"/t/start": "not_recorded", "/t/end": "not_recorded"})
    assert run(recs) == []  # the deny-list applies to typed fields only; t.raw is verbatim (C.7.3, R-30)


def test_sentinels_are_warnings_in_dev_mode() -> None:
    recs = edit(example_records(), "agent", version="unknown")
    report = validate_example(recs, mode="dev")
    assert report.ok and [f.code for f in report.warnings] == ["aer.sentinel"]
    assert not validate_example(recs, mode="release").ok


def test_source_side_sentinels_in_ext_are_preserved() -> None:
    recs = edit(example_records(), "exec", ext={"tst": {"agentdojo_package_version": "unknown", "x": ""}})
    assert run(recs) == []


def test_null_is_kept_null_and_distinct_from_empty() -> None:
    null_part = [{"t": "text", "text": None}, {"t": "tool_call", "name": "lookup", "args": {}}]
    assert run(edit(example_records(), "m1", parts=null_part)) == []
    task = {"benchmark": "tst", "task_id": "t1", "attack_id": None, "defense_id": None}
    assert run(edit(example_records(), "exec", task=task)) == []


def test_time_order_and_dur_clock() -> None:
    assert "aer.order.time" in run(edit(example_records(), "run", t={"start": "2026-10-08T12:00:02Z", "end": "2026-10-08T12:00:01Z"}))
    assert run(edit(example_records(), "run", t={"start": "2026-10-08T12:00:01Z", "end": "2026-10-08T12:00:01Z"})) == []
    # fractions compare numerically, not lexically
    assert run(edit(example_records(), "run", t={"start": "2026-10-08T12:00:01.5Z", "end": "2026-10-08T12:00:01.25Z"})) == ["aer.order.time"]
    assert "aer.schema.required" in run(edit(example_records(), "run", t={"dur_s": 1.5}))
    assert "aer.schema.required" in run(edit(example_records(), "run", t={"dur_clock": "wall"}))
    assert run(edit(example_records(), "run", t={"dur_s": 1.5, "dur_clock": "monotonic"})) == []
    assert "aer.schema.additional" in run(edit(example_records(), "run", t={"mono_start_ns": 5}))  # live only
    assert "aer.order.time" in run(edit(example_records(), "run", t={"start_naive": "2026-10-08T12:00:02", "end_naive": "2026-10-08T12:00:01"}))
