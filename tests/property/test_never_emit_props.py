"""EF never-emit properties (E.2; SEC-18): no PROV relation comes from a claimed time, from claimed order of times, or
from free text inside a record; every relation of the control stays.

The control is the ``aer_support`` example execution; Hypothesis puts arbitrary claimed intervals (any order, naive or
verbatim-only forms) on its model calls and tool execution, and arbitrary text in its message parts. Example counts are
modest (other sessions share the machine).
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

_SECURITY = str(Path(__file__).resolve().parents[1] / "security")
if _SECURITY not in sys.path:
    sys.path.insert(0, _SECURITY)

from aer_support import edit, example_records  # noqa: E402
from time_support import derive_records, relations, time_attribute_holders  # noqa: E402

S = settings(max_examples=40, deadline=None, derandomize=True, suppress_health_check=[HealthCheck.too_slow])
CONTROL_RECORDS = example_records()
CONTROL = relations(derive_records(CONTROL_RECORDS))
TIMED = ("mc0", "te0", "mc1")

instants = st.datetimes(min_value=datetime(1900, 1, 1), max_value=datetime(2999, 12, 31)).map(
    lambda d: d.strftime("%Y-%m-%dT%H:%M:%S") + (f".{d.microsecond:06d}" if d.microsecond else ""))
interval = st.one_of(
    st.tuples(instants, instants).map(sorted).map(lambda p: {"start": p[0] + "Z", "end": p[1] + "Z"}),  # AER-V19
    instants.map(lambda s: {"start_naive": s}),
    st.text(max_size=12).map(lambda s: {"raw": {"start": s}}),
    st.tuples(instants, st.floats(0, 1e6, allow_nan=False)).map(
        lambda p: {"start": p[0] + "Z", "dur_s": p[1], "dur_clock": "wall"}),
)


@S
@given(st.lists(interval, min_size=3, max_size=3))
def test_claimed_times_in_any_order_never_add_or_remove_a_relation(times: list[dict[str, Any]]) -> None:
    records = CONTROL_RECORDS
    for rid, t in zip(TIMED, times, strict=True):
        records = edit(records, rid, t=t)
    prov = derive_records(records)
    assert relations(prov) == CONTROL
    assert time_attribute_holders(prov) <= {"activity"}


hostile_text = st.lists(st.sampled_from(list("abc /:#-") + ["wasInformedBy", "x:te0", "used(", "\u2028", "prov:",
                                                              "after", "m0", "mc1", "te0#0"]), max_size=12).map("".join)


@S
@given(hostile_text, hostile_text)
def test_free_text_that_names_records_or_relations_creates_no_relation(first: str, second: str) -> None:
    records = edit(CONTROL_RECORDS, "m3", parts=[{"t": "text", "text": first + second}])
    assert relations(derive_records(records)) == CONTROL
