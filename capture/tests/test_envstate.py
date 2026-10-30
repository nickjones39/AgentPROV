"""Environment digests, snapshots and diffs: the baseline's E-1...E-5 (B CAP-18), with the specification's changes
(JCS canonical form, mapping digest, F-12 `truncated`)."""

from __future__ import annotations

import hashlib
from typing import Any

import pytest

from agentprov_capture import envstate


def test_digest_is_a_mapping_of_sha256_of_the_jcs_snapshot() -> None:
    d = envstate.digest({"b": [1, 2], "a": 1})
    assert d == {"sha256": hashlib.sha256(b'{"a":1,"b":[1,2]}').hexdigest(), "canon": "jcs-rfc8785"}
    assert envstate.snapshot({"b": [1, 2], "a": 1}) == b'{"a":1,"b":[1,2]}'
    assert set(d) == {"sha256", "canon"} and not d["sha256"].startswith("sha256:")  # E-2: bare hex


def test_equal_states_have_equal_digests_whatever_the_key_order() -> None:
    assert envstate.digest({"a": 1, "b": [1, 2]}) == envstate.digest({"b": [1, 2], "a": 1})
    assert envstate.digest({"a": 1}) != envstate.digest({"a": 2})
    assert envstate.digest({"a": [1, 2]}) != envstate.digest({"a": [2, 1]})


def test_dump_state_duck_types_model_dump_and_round_trips_json() -> None:
    class Model:  # a pydantic stand-in
        def model_dump(self, mode: str) -> dict[str, Any]:
            assert mode == "json"
            return {"x": [1, {"y": "z"}]}

    assert envstate.dump_state(Model()) == {"x": [1, {"y": "z"}]}
    assert envstate.dump_state({"t": (1, 2), 3: "k"}) == {"t": [1, 2], "3": "k"}
    assert envstate.dump_state({"when": object}).keys() == {"when"}  # default=str for the unserialisable


def test_values_jcs_cannot_carry_are_encoded_as_in_c11() -> None:
    n = envstate.normalise
    assert n(2**53) == {"$int": str(2**53)} and n(-(2**53)) == {"$int": str(-(2**53))} and n(2**53 - 1) == 2**53 - 1
    assert n(float("nan")) == {"$float": "NaN"} and n(float("-inf")) == {"$float": "-Infinity"}
    assert n(-0.0) == {"$float": "-0"} and n(0.0) == 0.0
    assert n("\ud800") == {"$utf16": "2AA="}
    assert n({"$int": "5"}) == {"$lit": {"$int": "5"}}
    assert n(True) is True and n(None) is None
    with pytest.raises(TypeError):
        n(object())
    with pytest.raises(TypeError):
        n({1: "x"})
    assert envstate.digest({"big": 2**70})["sha256"] != envstate.digest({"big": "1180591620717411303424"})["sha256"]


def test_an_unchanged_state_records_no_diff() -> None:
    rec = envstate.end_env({"a": 1}, {"a": 1})
    assert rec == {**envstate.digest({"a": 1}), "changed": False}
    assert "diff" not in rec


def test_a_changed_state_records_digest_changed_diff_and_snapshot() -> None:
    ref = {"$blob": "sha256:" + "0" * 64, "bytes": 5, "media": "application/json"}
    rec = envstate.end_env({"a": 1}, {"a": 2}, snapshot_ref=ref)
    assert rec["sha256"] == envstate.digest({"a": 2})["sha256"] and rec["changed"] is True and rec["snapshot"] == ref
    assert rec["diff"] == envstate.diff({"a": 1}, {"a": 2})
    assert "diff" not in envstate.end_env({"a": 1}, {"a": 2}, with_diff=False)


def test_pass_chaining_before_of_the_next_pass_is_after_of_the_previous() -> None:
    s0, s1, s2 = {"v": 0}, {"v": 1}, {"v": 2}
    first = envstate.end_env(s0, s1)
    second = envstate.end_env(s1, s2)
    assert first["sha256"] == envstate.digest(s1)["sha256"]
    assert envstate.digest(s1)["sha256"] != second["sha256"] and second["changed"]


def test_leaves_and_list_elements_are_diffed_with_json_pointers() -> None:
    before = {"inbox": [{"id": 1}, {"id": 2}], "balance": 10, "gone": "x", "a/b": {"c": 1}}
    after = {"inbox": [{"id": 2}, {"id": 3}], "balance": 12, "new": "y", "a/b": {"c": 2}}
    d = envstate.diff(before, after)
    assert d["format"] == "agentprov.envdiff@1" and d["truncated"] is False
    got = {(e["op"], e["path"], e.get("element", False)) for e in d["value"]["entries"]}
    assert got == {
        ("changed", "/balance", False),
        ("removed", "/gone", False),
        ("added", "/new", False),
        ("removed", "/inbox", True),
        ("added", "/inbox", True),
        ("changed", "/a~1b/c", False),
    }
    assert d["value"]["n_changes"] == 6


def test_deleting_the_first_list_element_is_one_change_not_many() -> None:
    before = {"xs": [{"v": i} for i in range(50)]}
    after = {"xs": [{"v": i} for i in range(1, 50)]}
    assert envstate.diff(before, after)["value"]["n_changes"] == 1


def test_long_values_are_cut_and_the_cut_is_reported() -> None:  # F-12: the baseline ignored value cuts
    d = envstate.diff({"t": "a" * 5000}, {"t": "b" * 5000})
    entry = d["value"]["entries"][0]
    assert len(entry["before"]) == envstate.VALUE_CAP + 1 and entry["before"].endswith("…")
    assert d["truncated"] is True


def test_too_many_entries_are_cut_and_the_cut_is_reported() -> None:
    big = envstate.diff({}, {f"k{i}": i for i in range(envstate.ENTRY_CAP + 30)})
    assert big["truncated"] is True and len(big["value"]["entries"]) == envstate.ENTRY_CAP
    assert big["value"]["n_changes"] == envstate.ENTRY_CAP + 30
    exact = envstate.diff({}, {f"k{i}": i for i in range(envstate.ENTRY_CAP)})
    assert exact["truncated"] is False


def test_a_reordered_list_is_reported_because_its_digest_moves() -> None:
    rec = envstate.end_env({"xs": [1, 2, 3]}, {"xs": [3, 2, 1]})
    assert rec["changed"] is True
    assert rec["diff"]["value"]["entries"] == [{"op": "reordered", "path": "/xs"}]
    assert envstate.end_env({"xs": [1, 1]}, {"xs": [1, 1]})["changed"] is False


def test_diff_of_normalised_special_values_is_stable() -> None:
    d = envstate.diff({"n": 2**60}, {"n": 2**61})
    assert d["value"]["n_changes"] == 1 and d["value"]["entries"][0]["op"] == "changed"


def test_diff_is_deterministic_and_walks_sorted_keys() -> None:
    a = {"z": 1, "a": [3, 1, 2], "m": {"k": "v"}}
    b = {"z": 2, "a": [1, 2, 3, 4], "m": {"k": "w", "j": 0}}
    assert envstate.diff(a, b) == envstate.diff(a, b)
    assert [(e["op"], e["path"]) for e in envstate.diff(a, b)["value"]["entries"]] == [
        ("added", "/a"),
        ("added", "/m/j"),
        ("changed", "/m/k"),
        ("changed", "/z"),
    ]
