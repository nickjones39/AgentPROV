"""SEC-18 (K.12.5, EF never-emit; T-15): a claimed time is a recorded value, never ordering or causal evidence.

Times on model calls and tool executions are varied (ordered, reversed, implausible, unparseable); the PROV relations
must be exactly those of the time-less control, time attributes may appear only on activities, and each value must
reach PROV as recorded (canonical ``xsd:dateTime`` or its verbatim lexical form). ``time.implausible`` has no emitter
yet (docs/reports/hardening/sec-coverage.md, SOURCE-GAP), so it is not asserted here.
"""

from __future__ import annotations

from typing import Any

import pytest
from aer_support import edit, example_records
from time_support import derive_records, relations, time_attribute_holders

TIMED = ("mc0", "te0", "mc1")


def _t(start: str) -> dict[str, Any]:
    return {"start": start, "end": start}


CASES: dict[str, list[dict[str, Any]]] = {
    "ordered": [_t("2026-10-08T12:00:00Z"), _t("2026-10-08T12:00:02Z"), _t("2026-10-08T12:00:04Z")],
    "reversed": [_t("2026-10-08T12:00:04Z"), _t("2026-10-08T12:00:02Z"), _t("2026-10-08T12:00:00Z")],
    "implausible": [_t("1970-01-01T00:00:00Z"), _t("2999-12-31T23:59:59Z"), _t("2026-12-31T23:59:60Z")],
    "lexical": [{"start_naive": "2026-10-08T12:00:00", "raw": {"start": "yesterday"}},
                {"start_naive": "2026-10-08T11:00:00", "raw": {"start": "0"}},
                {"raw": {"start": "2026-10-08 12:00:00 +0200"}}],
}


def timed(times: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records = example_records()
    for rid, t in zip(TIMED, times, strict=True):
        records = edit(records, rid, t=t)
    return records


CONTROL = relations(derive_records(example_records()))


@pytest.mark.parametrize("case", sorted(CASES))
def test_sec18_claimed_times_never_change_the_relations(case: str) -> None:
    prov = derive_records(timed(CASES[case]))
    assert relations(prov) == CONTROL
    assert time_attribute_holders(prov) <= {"activity"}


@pytest.mark.parametrize("case", sorted(CASES))
def test_sec18_each_claimed_value_reaches_prov_as_recorded(case: str) -> None:
    from agentprov.prov.serialise.time import prov_time

    prov = derive_records(timed(CASES[case]))
    core = next(body for name, body in prov["bundle"].items() if ".core." in name)
    for rid, t in zip(TIMED, CASES[case], strict=True):
        node = core["activity"][f"x:{rid}"]
        if "start" in t:
            canonical = prov_time(t["start"])
            if canonical is not None:
                assert node["prov:startTime"] == canonical and "apv:startTimeLexical" not in node
            else:  # a leap second: kept verbatim, never "corrected" to a neighbouring instant
                assert node["apv:startTimeLexical"] == t["start"] and "prov:startTime" not in node
        elif "start_naive" in t:
            assert node["apv:startTimeLexical"] == t["start_naive"] and "prov:startTime" not in node
        else:  # only the verbatim source string: no time attribute at all, nothing invented
            assert not {"prov:startTime", "apv:startTimeLexical"} & set(node)
        time_values = {str(v) for k, v in node.items() if "Time" in k}
        assert t.get("raw", {}).get("start") not in time_values  # the verbatim source string stays in AER t.raw only
