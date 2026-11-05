"""UC-39 (dtap's share): a value outside the AER ranges never reaches a typed field. A ``traj_info`` counter above
2^53 - 1 made the seal's accounting check uncanonicalisable, so the run was ``adapter_defect``; it is now an
inconsistent counter (no step population is that large) that the check does not copy. Synthetic runs only."""

from __future__ import annotations

import json

import dtap_support as support
import pytest

from agentprov.aer.canon import I_JSON_MAX


def _mapped(**traj_info):
    label, data = support.run([support.call("a", {}), support.result("a")])
    value = json.loads(data)
    value["traj_info"].update(traj_info)
    return support.map_label(label, runs={label: json.dumps(value).encode()}, tasks={})


def _check(m):
    return next(c for c in m.doc.seal["accounting"]["checks"] if c["id"] == "dtap.acc.counters@1")


@pytest.mark.parametrize("counter", ["step_count", "actions_count", "tool_count", "user_turn"])
def test_a_counter_beyond_the_i_json_range_is_inconsistent_and_not_copied(counter):
    m = _mapped(**{counter: I_JSON_MAX + 1})
    check = _check(m)
    assert check["verdict"] == "inconsistent" and check["reason"] == "counters_differ_from_steps"
    assert counter not in check["observed"] and check["observed"]["steps"] == 2


def test_a_counter_at_the_limit_is_copied():
    check = _check(_mapped(step_count=I_JSON_MAX))
    assert check["verdict"] == "inconsistent" and check["observed"]["step_count"] == I_JSON_MAX


def test_a_huge_duration_and_an_impossible_timestamp_stay_raw():
    m = _mapped(duration=2**70, timestamp="9999-99-99T99:99:99Z")
    run = m.get("run")
    assert run["t"] == {"raw": {"end": "9999-99-99T99:99:99Z"}} and "/t/dur_s" in run["unk"]
