"""The gate-C expected-differences register (J.3.4): the committed file, the loader's validation and the checker
(unlisted fails, over-bound fails, ambiguous fails, the declared set must be hit exactly), plus the C6 masks and the
pointer diff of :mod:`agentprov.migration.c6`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agentprov.migration import c6
from agentprov.migration.xd import (
    DEFAULT_REGISTER_PATH,
    Observation,
    RegisterError,
    check,
    load_register,
    parse_register,
)


def _entry(**changes: Any) -> dict[str, Any]:
    base = {"id": "XD-C6-F02-x", "comparison": "C6", "defect": "F-02", "applies_to": ["scenario:*"],
            "match": ["deviation:F-02/*"], "old": "o", "new": "n", "evidence": "B.9 F-02", "max_per_item": 2}
    base.update(changes)
    return base


def _register(*entries: dict[str, Any]) -> Any:
    return parse_register({"register": {"format": "agentprov-expected-differences/1"}, "difference": list(entries)})


def _obs(key: str, item: str = "scenario:s1") -> Observation:
    return Observation("C6", item, key)


def test_the_committed_register_loads_and_cites_its_defects() -> None:
    register = load_register(DEFAULT_REGISTER_PATH)
    c6_entries = register.for_comparison("C6")
    assert {e.defect for e in c6_entries} == {"F-02", "F-05", "F-13", "D.7.3", "D.10.5", "C.15.3"}
    assert all(e.evidence and e.old and e.new for e in c6_entries)
    # exactly one entry per deviation: no observation key two entries would both absorb
    for key in ("deviation:F-02/mc0", "deviation:F-05/failed-cell", "deviation:F-13/display-name",
                "deviation:D.7.3/capture-block", "deviation:D.10.5/benign-security", "deviation:C.15.3/generator-meta"):
        assert sum(e.applies(_obs(key)) for e in c6_entries) == 1, key
    # the failure-shaped keys of the detectors are registered nowhere
    for key in ("deviation:F-05/failed-cell-not-kept", "deviation:F-13/display-name-differs",
                "deviation:D.7.3/verdict-disagrees", "v1:/meta/model", "projection:/judgements/0/value"):
        assert not any(e.applies(_obs(key)) for e in register.entries), key


@pytest.mark.parametrize(("change", "message"), [
    ({"id": "C6-no-prefix"}, "id must match"),
    ({"comparison": "C9"}, "comparison"),
    ({"id": "XD-C2-F02-x"}, "agree with the id"),
    ({"defect": None}, "must cite"),
    ({"defect": "bug-7"}, "defect must be"),
    ({"max_per_item": 0}, "positive integer"),
    ({"max_per_item": True}, "positive integer"),
    ({"applies_to": []}, "applies_to"),
    ({"evidence": " "}, "evidence"),
    ({"surprise": 1}, "unknown members"),
])
def test_malformed_entries_are_refused(change: dict[str, Any], message: str) -> None:
    entry = {k: v for k, v in _entry(**change).items() if v is not None}
    with pytest.raises(RegisterError, match=message):
        _register(entry)


def test_duplicates_and_a_missing_header_are_refused() -> None:
    with pytest.raises(RegisterError, match="duplicate"):
        _register(_entry(), _entry())
    with pytest.raises(RegisterError, match="format"):
        parse_register({"difference": [_entry()]})


def test_an_unlisted_difference_fails() -> None:
    result = check([_obs("v1:/meta/model")], _register(_entry()))
    assert not result.ok and [o.key for o in result.unlisted] == ["v1:/meta/model"]
    assert result.failures() == [{"item": "scenario:s1", "check": "xd.unlisted", "detail": "v1:/meta/model"}]


def test_a_count_above_the_bound_fails() -> None:
    register = _register(_entry(max_per_item=2))
    assert check([_obs("deviation:F-02/mc0"), _obs("deviation:F-02/mc1")], register).ok
    result = check([_obs(f"deviation:F-02/mc{i}") for i in range(3)], register)
    assert not result.ok and result.over_bound == [("XD-C6-F02-x", "scenario:s1", 3, 2)]
    # the bound is per item
    assert check([_obs("deviation:F-02/mc0", "scenario:a"), _obs("deviation:F-02/mc1", "scenario:a"),
                  _obs("deviation:F-02/mc0", "scenario:b")], register).ok


def test_two_entries_for_one_deviation_are_ambiguous() -> None:
    register = _register(_entry(), _entry(id="XD-C6-F02-y"))
    result = check([_obs("deviation:F-02/mc0")], register)
    assert not result.ok and result.ambiguous[0][1] == ("XD-C6-F02-x", "XD-C6-F02-y")


def test_applies_to_and_comparison_limit_an_entry() -> None:
    register = _register(_entry(applies_to=["scenario:only"]))
    assert not check([_obs("deviation:F-02/mc0", "scenario:other")], register).ok
    assert not check([Observation("C2", "scenario:only", "deviation:F-02/mc0")], register).ok
    assert check([_obs("deviation:F-02/mc0", "scenario:only")], register).ok


def test_the_declared_set_must_be_hit_exactly() -> None:
    register = _register(_entry(), _entry(id="XD-C6-F13-y", defect="F-13", match=["deviation:F-13/*"]))
    ok = check([_obs("deviation:F-02/mc0")], register, expected={"scenario:s1": ["XD-C6-F02-x"]})
    assert ok.ok and ok.counts_by_entry() == {"XD-C6-F02-x": 1}
    missing = check([], register, expected={"scenario:s1": ["XD-C6-F02-x"]})
    assert missing.missing == [("scenario:s1", "XD-C6-F02-x")] and not missing.ok
    extra = check([_obs("deviation:F-13/a")], register, expected={"scenario:s1": []})
    assert extra.unexpected == [("scenario:s1", "XD-C6-F13-y")] and not extra.ok
    with pytest.raises(RegisterError, match="not in the register"):
        check([], register, expected={"scenario:s1": ["XD-C6-nope"]})


# ------------------------------------------------------------------------------------------------ narrow detectors
def _aer(*records: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"k": "execution", "id": "exec"}, *records]


def test_the_benign_security_detector_is_narrow() -> None:
    benign = {"old": {"kind": "benign"}}
    meta = {"attack_type": "benign", "security": None}
    stock = {"k": "judgement", "id": "j1", "name": "security", "value": True, "origin": "harness_default"}
    assert c6.benign_security_constant(meta, _aer(stock), benign)
    assert not c6.benign_security_constant(meta, _aer(stock), {"old": {"kind": "injection"}})
    assert not c6.benign_security_constant({**meta, "security": False}, _aer(stock), benign)
    assert not c6.benign_security_constant(meta, _aer({**stock, "origin": "checker"}), benign)
    assert not c6.benign_security_constant(meta, _aer({**stock, "value": False}), benign)
    assert not c6.benign_security_constant({"attack_type": "benign"}, _aer(stock), benign)  # no security member


def test_the_generator_meta_detector_is_narrow() -> None:
    old = {"model": "deepseek", "model_config": {"temperature": 0.0}}
    view = {"model": None}
    assert c6.generator_meta_absent(old, view, _aer())
    assert not c6.generator_meta_absent(old, {"model": "deepseek"}, _aer())
    assert not c6.generator_meta_absent(old, {"model": None, "model_config": {}}, _aer())
    assert not c6.generator_meta_absent({"model": "deepseek"}, view, _aer())
    assert not c6.generator_meta_absent(old, view, [{"k": "execution", "id": "exec", "ext": {"adprov": {}}}])


# ------------------------------------------------------------------------------------------------ c6 masks and diffs
def _transcript() -> dict[str, Any]:
    tool = {"role": "tool", "tool_call_id": "c1", "function": "f", "args": {}, "content": "x", "content_sha256": "s",
            "error": None, "started_at": "2026-10-08T00:00:00+00:00", "ended_at": "2026-10-08T00:00:01+00:00"}
    return {"adprov_schema": "transcript/v1",
            "meta": {"model": "m", "started_at": "t0", "ended_at": "t1", "wall_clock_s": 0.5, "n_attempts": 2},
            "turns": [{"role": "user", "content": "q"}, dict(tool)],
            "discarded_attempts": [{"turns": [dict(tool)]}]}


def test_the_time_mask_keeps_member_order_and_drops_tool_times() -> None:
    doc = _transcript()
    masked = c6.mask_transcript(doc)
    assert list(masked["meta"]) == list(doc["meta"])
    assert [masked["meta"][k] for k in c6.META_TIME_KEYS] == [c6.MASK] * 3
    for turn in (masked["turns"][1], masked["discarded_attempts"][0]["turns"][0]):
        assert "started_at" not in turn and "ended_at" not in turn
    assert doc["turns"][1]["started_at"]  # the input is not modified
    # a new view without tool times equals the old transcript after the mask
    other = _transcript()
    for turn in (other["turns"][1], other["discarded_attempts"][0]["turns"][0]):
        del turn["started_at"], turn["ended_at"]
    other["meta"]["wall_clock_s"] = 9.0
    assert c6.serialise_v1(c6.mask_transcript(other)) == c6.serialise_v1(masked)


def test_the_graph_mask_removes_time_attributes_at_any_depth() -> None:
    graph = {"activity": {"a": {"prov:startTime": "t", "prov:endTime": "u", "prov:label": "f"}},
             "wasGeneratedBy": {"g": {"prov:time": "t", "prov:entity": "e"}}}
    assert c6.mask_graph(graph) == {"activity": {"a": {"prov:label": "f"}}, "wasGeneratedBy": {"g": {"prov:entity": "e"}}}


def test_the_pointer_diff_reports_presence_order_type_and_value() -> None:
    old = {"a": {"x": 1, "y": 2}, "b": [1, 2], "c": 1.0, "d": "s", "e/f": 1}
    new = {"a": {"y": 2, "x": 1}, "b": [1], "c": 1, "d": "t", "g": 0, "e/f": 1}
    assert list(c6.json_differences(old, new)) == ["/g", "/a#order", "/b/1", "/c", "/d"]
    assert list(c6.json_differences(json.loads('{"k": [1, {"z": null}]}'), json.loads('{"k": [1, {"z": null}]}'))) == []
    assert list(c6.json_differences({"e/f": 1}, {"e/f": 2})) == ["/e~1f"]



# ------------------------------------------------------------------------------------------------ compare_work
def _c6_work(work: Path, listed: list[str] | None, present: list[str], fmt: str = "agentprov-c6-work/1") -> Path:
    """A C6 work dir: the producer's ``manifest.json`` listing ``listed`` (no manifest when ``None``) and a
    ``<name>/scenario.json`` for each of ``present``."""
    work.mkdir()
    if listed is not None:
        (work / "manifest.json").write_text(json.dumps({"format": fmt, "scenarios": listed}), encoding="utf-8")
    for name in present:
        (work / name).mkdir()
        (work / name / "scenario.json").write_text(json.dumps({"name": name, "category": "b"}), encoding="utf-8")
    return work


@pytest.fixture
def clean_scenarios(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every found scenario compares clean, as a passing scenario would: only the scenario set decides."""
    def stub(directory: Path) -> c6.C6Item:
        return c6.C6Item(json.loads((directory / "scenario.json").read_text(encoding="utf-8"))["name"], "b", ())
    monkeypatch.setattr(c6, "compare_scenario", stub)


@pytest.mark.usefixtures("clean_scenarios")
def test_compare_work_passes_only_the_full_listed_scenario_set(tmp_path: Path) -> None:
    register = load_register(DEFAULT_REGISTER_PATH)
    full = c6.compare_work(_c6_work(tmp_path / "full", ["s1", "s2"], ["s2", "s1"]), register)
    assert full.ok and full.scenarios == ["s1", "s2"] and full.missing == [] and full.extra == []
    # the producer listed three scenarios but none, or one, was written (a -k run, a killed run, a pruned dir)
    empty = c6.compare_work(_c6_work(tmp_path / "empty", ["s1", "s2", "s3"], []), register)
    assert not empty.ok and empty.items == [] and empty.missing == ["s1", "s2", "s3"]
    partial = c6.compare_work(_c6_work(tmp_path / "partial", ["s1", "s2", "s3"], ["s1"]), register)
    assert not partial.ok and [i.scenario for i in partial.items] == ["s1"] and partial.missing == ["s2", "s3"]
    extra = c6.compare_work(_c6_work(tmp_path / "extra", ["s1"], ["s1", "s9"]), register)
    assert not extra.ok and extra.missing == [] and extra.extra == ["s9"]


@pytest.mark.usefixtures("clean_scenarios")
def test_compare_work_fails_without_the_producer_manifest(tmp_path: Path) -> None:
    register = load_register(DEFAULT_REGISTER_PATH)
    absent = c6.compare_work(_c6_work(tmp_path / "absent", None, ["s1"]), register)
    assert not absent.ok and absent.scenarios is None
    other = c6.compare_work(_c6_work(tmp_path / "other", ["s1"], ["s1"], fmt="agentprov-c6-work/2"), register)
    assert not other.ok and other.scenarios is None
    (tmp_path / "broken").mkdir()
    (tmp_path / "broken" / "manifest.json").write_text("{", encoding="utf-8")
    assert not c6.compare_work(tmp_path / "broken", register).ok
    (tmp_path / "broken" / "manifest.json").write_text("[]", encoding="utf-8")
    assert not c6.compare_work(tmp_path / "broken", register).ok
