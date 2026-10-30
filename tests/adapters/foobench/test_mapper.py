"""Mapper ``foobench.jsonl``: FooBench traces -> AER (docs/architecture D.12.1 row 3, D.12.2; C.3.13-C.3.15; K.6.4).

The AER of the fixture is compared with the checked-in golden file as **bytes** (never Python ``==`` on parsed values:
member order and number spelling are part of the gate, C.11.4). Regenerate it deliberately with
``AGENTPROV_REGENERATE_GOLDEN=1 uv run pytest tests/adapters/foobench/test_mapper.py -k golden`` after a reviewed
mapper, profile or catalogue change.
"""

from __future__ import annotations

import hashlib
import json
import os
import tomllib
from collections.abc import Mapping
from importlib import resources
from pathlib import Path
from typing import Any

import jsonschema

from agentprov.adapters.foobench.mapper import FooMapper
from agentprov.adapters.runner import aer_bytes, map_unit
from agentprov.aer.rules import RuleRegistry

GOLDEN = Path(__file__).resolve().parent / "golden" / "trace-001.aer.jsonl"
PACKAGE = "agentprov.adapters.foobench"


def schema(name: str) -> dict[str, Any]:
    return json.loads((resources.files(PACKAGE) / name).read_bytes())


def thaw(value: Any) -> Any:
    """A profile's frozen mappings and tuples as plain JSON values."""
    if isinstance(value, Mapping):
        return {k: thaw(v) for k, v in value.items()}
    if isinstance(value, tuple | list):
        return [thaw(v) for v in value]
    return value


# ------------------------------------------------------------------------------------------------ golden and validity
def test_the_fixture_maps_to_the_golden_aer_bytes(mapped):
    if os.environ.get("AGENTPROV_REGENERATE_GOLDEN") == "1":
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_bytes(mapped.data)
    assert mapped.data == GOLDEN.read_bytes()  # bytes, not parsed values


def test_the_mapping_is_deterministic(foo, mapped):
    again = foo.map()
    assert again.data == mapped.data and again.info.execution_digest == mapped.info.execution_digest


def test_the_aer_is_clean_not_degenerate_and_validates_against_the_store(mapped):
    assert not mapped.outcome.degenerate and mapped.outcome.error_code is None
    report = mapped.validate("release")
    assert report.ok, sorted({(f.code, f.pointer) for f in report.errors})
    assert report.passed and report.findings == () and report.skipped == ()  # nothing skipped, nothing flagged
    assert mapped.records[0]["profile"] == {"id": "foobench", "sha256": mapped.records[0]["profile"]["sha256"], "version": 1}


def test_the_header_names_the_adapter_dialect_namespace_and_both_raw_files(foo, mapped):
    header = mapped.records[0]
    assert header["adapter"] == {"id": "foobench.jsonl", "version": "0.1.0"}
    assert header["dialect"] == {"id": "foobench.jsonl", "variant": "v1"}
    assert header["ns"] == {"foobench": "https://w3id.org/agentprov/ns/foobench#"} and header["rules"] == {"aer": 1, "foobench": 1}
    assert header["source_key"]["loc"] == {} and header["unit"] == "agent_execution" and header["mode"] == "import"
    assert header["task"] == {"benchmark": "foobench", "task_id": "task-001"}
    primary, sub = header["artifacts"]
    assert (primary["id"], primary["role"], primary["prov_primary"]) == ("a0", "primary", "native")
    assert (sub["id"], sub["role"]) == ("a1", "supporting")  # the hand-off's second file (D.12.2)
    assert header["evf"] == {"/task/benchmark": "D"}


# ------------------------------------------------------------------------------------------------ kinds and ids
def test_ids_follow_d122_and_specialised_kinds_come_first(mapped):
    by = mapped.by_id()
    kinds = {k: sorted(r["id"] for r in mapped.of_kind(k)) for k in ("activity", "artefact", "tool_execution", "decision", "state_change")}
    assert kinds["activity"] == ["ac0", "ac1", "ac2"] and kinds["artefact"] == ["af0", "af1", "af2", "af3"]
    assert kinds["tool_execution"] == [f"te{n}" for n in range(6)] and kinds["decision"] == ["dc0", "dc1", "dc2", "dc3"]
    assert kinds["state_change"] == ["st0"]
    assert [by[a]["type"] for a in kinds["activity"]] == ["foobench:plan_step", "foobench:memory_read", "foobench:observe"]
    assert [by[a]["type"] for a in kinds["artefact"]] == ["foobench:plan", "foobench:memory_item", "foobench:memory_snippet", "foobench:screenshot"]
    assert sorted(r["id"] for r in mapped.of_kind("model_call")) == [f"mc{n}" for n in range(8)]
    messages = sorted(r["id"] for r in mapped.of_kind("message"))
    assert messages == sorted([*(f"m{n}" for n in range(16)), "p0", "sm0", "sm1"])
    assert [r["id"] for r in mapped.of_kind("scope")] == ["run", "thr0", "att0", "sc0"]


def test_model_calls_and_messages(mapped):
    by = mapped.by_id()
    mc0, p0 = by["mc0"], by["p0"]  # the planner step's LLM part: an auxiliary call in the planner thread
    assert (mc0["actor"], mc0["role"], mc0["scope"], mc0["status"]) == ("planner", "auxiliary", "thr0", "kept")
    assert "input" not in mc0 and mc0["unk"] == {"/input": "not_recorded"}  # the request carried no context list
    assert (p0["generated_by"], p0["actor"], p0["scope"], p0["role"]) == ("mc0", "planner", "thr0", "assistant")
    assert by["mc1"]["input"] == ["m0"] and by["mc3"]["input"] == [f"m{n}" for n in range(7)]
    assert (by["mc1"]["actor"], by["mc1"]["role"], by["mc1"]["scope"]) == ("agent", "agent", "att0")
    assert by["m1"]["generated_by"] == "mc1" and [p["t"] for p in by["m1"]["parts"]] == ["text", "tool_call", "tool_call", "tool_call"]
    assert by["planner"]["role"] == "planner" and by["planner"]["kind"] == "llm_agent" and by["agent"]["model"] == {"requested": "foo-agent-1"}


def test_planner_step_memory_and_screenshot_encodings(mapped):
    by = mapped.by_id()
    assert (by["ac0"]["actor"], by["ac0"]["scope"], by["ac0"]["inputs"], by["ac0"]["status"]) == ("harness", "thr0", ["p0"], "ok")
    assert by["af0"]["generated_by"] == "ac0" and by["af0"]["media"] == "application/json" and by["af0"]["content"] == {"steps": ["lookup", "save", "delegate", "act"]}
    assert by["af1"]["generated_by"] == "te1" and by["af1"]["content"] == {"key": "note", "value": "remember the plan"}
    assert by["st0"] == by["st0"] | {"cause": "te1", "target": "agent_store", "scope": "att0"}
    assert by["st0"]["patch"] == [{"op": "add", "path": "/note", "value": "remember the plan"}]
    assert (by["ac1"]["actor"], by["ac1"]["scope"], by["ac1"]["inputs"]) == ("harness", "att0", ["af1"])
    assert by["ac1"]["evf"]["/inputs/0"] == "D"  # the read -> write link is a key match, class D
    assert by["af2"]["generated_by"] == "ac1" and by["af2"]["content"] == "remember the plan"
    assert (by["ac2"]["actor"], by["ac2"]["inputs"]) == ("env", [])
    blob = by["af3"]["content_ref"]
    assert by["af3"]["generated_by"] == "ac2" and by["af3"]["sha256"] == blob["$blob"].removeprefix("sha256:") and by["af3"]["media"] == "image/png"
    assert blob["bytes"] == len(mapped.png) and mapped.records[-1]["blobs"] == [blob["$blob"]]


def test_hand_off_approvals_and_text_action_encodings(mapped):
    by = mapped.by_id()
    assert (by["te2"]["call"], by["te2"]["name"]) == ("m1#3", "transfer_to_researcher")
    assert by["sc0"] == by["sc0"] | {"kind": "subagent", "parent": "run", "actor": "researcher", "spawned_by": "te2"}
    assert by["researcher"]["role"] == "subagent" and by["researcher"]["model"] == {"requested": "foo-sub-1"}
    assert by["mc2"]["scope"] == "sc0" and by["mc2"]["actor"] == "researcher" and by["sm1"]["scope"] == "sc0"
    assert by["mc2"]["src"][0]["a"] == "a1"  # the second file's records cite the supporting artefact
    assert by["m4"]["generated_by"] == "te2" and by["m4"]["parts"][0]["responds_to"] == "m1#3"  # the sub-agent's answer
    assert (by["dc1"]["actor"], by["dc1"]["subject"], by["dc1"]["verdict"]) == ("user", "m7#1", "allow")
    assert (by["te3"]["call"], by["te3"]["authorised_by"]) == ("m7#1", "dc1")
    assert (by["dc2"]["actor"], by["dc2"]["subject"], by["dc2"]["verdict"], by["dc2"]["original"]) == ("user", "m9#1", "modify", "m9#1")
    assert (by["te4"]["call"], by["te4"]["authorised_by"], by["te4"]["args"]) == ("m9#1", "dc2", {"body": "edited draft", "to": "alice"})
    te5 = by["te5"]
    assert te5["requested_by"] == "agent" and "call" not in te5 and (te5["name"], te5["args"]) == ("scroll", {"direction": "down"})
    assert te5["evf"] == te5["evf"] | {"/name": "I", "/args": "I"} and "foobench.text_action_parse@1#/args" in te5["rule"]
    assert by["m12"]["generated_by"] == "te5" and by["m12"]["unk"] == {"/parts/0/responds_to": "not_applicable"}


def test_guard_verdicts_map_through_the_profiles_closed_table(mapped):
    by = mapped.by_id()
    assert (by["dc0"]["actor"], by["dc0"]["verdict"], by["dc0"]["subject"]) == ("def0", "allow", "m1#1")
    assert (by["dc3"]["verdict"], by["dc3"]["subject"], by["dc3"]["reason"]) == ("deny", "m13#1", "policy")
    assert by["def0"]["kind"] == "defense" and by["def0"]["name"] == "guard-1"
    assert by["m14"]["generated_by"] == "dc3"  # the denial text is generated by the decision (C.5.5)
    executions = {r["call"] for r in mapped.of_kind("tool_execution") if "call" in r}
    assert "m13#1" not in executions  # a deny has no tool_execution


# ------------------------------------------------------------------------------------------------ disclosed gaps in AER
def test_unknown_and_restore_events_are_kept_verbatim_in_ext_of_the_nearest_preceding_host(mapped):
    by = mapped.by_id()
    (telemetry,) = by["af0"]["ext"]["foobench"]["events"]  # the host is the plan artefact the preceding event produced
    assert set(telemetry) == {"type", "value", "src", "after"} and telemetry["type"] == "telemetry"
    assert telemetry["src"] == {"line": 4} and telemetry["after"] == [{"id": "af0", "b": "pos"}]
    assert telemetry["value"]["counters"] == {"latency_ms": 120, "tokens": 42}
    (restore,) = by["m8"]["ext"]["foobench"]["events"]  # ... and for the restore, the tool result before it
    assert restore["type"] == "checkpoint_restore" and restore["src"] == {"line": 21} and restore["value"]["checkpoint"] == "cp-1"
    assert restore["after"] == [{"id": "m8", "b": "pos"}]
    hosts = [r["id"] for r in mapped.records if "events" in r.get("ext", {}).get("foobench", {})]
    assert hosts == ["af0", "m8"]  # there is no host-less unmapped[] list anywhere
    assert not any("unmapped" in r for r in mapped.records)


def test_observation_messages_carry_no_generator_and_are_declared(mapped):
    by = mapped.by_id()
    for mid, actor in (("m5", "harness"), ("m6", "env")):
        assert by[mid]["unk"] == {"/generated_by": "not_recorded"} and "generated_by" not in by[mid] and by[mid]["actor"] == actor
    assert by["m6"]["parts"][0]["t"] == "blob" and by["m6"]["parts"][0]["data"] == by["af3"]["content_ref"]  # the same digest
    issues = [(i["code"], i["ids"]) for i in mapped.issues]
    assert issues == [
        ("foobench.unmapped_event_type", ["af0"]),
        ("foobench.observation_unlinked", ["m5"]),
        ("foobench.observation_unlinked", ["m6"]),
        ("foobench.restore_unmodelled", ["m8"]),
        ("orphan_tool_result", ["m12#0"]),
        ("accounting_unverifiable", ["thr0"]),
    ]
    assert {i["code"]: i["rule"] for i in mapped.issues}["foobench.restore_unmodelled"] == "foobench.restore_not_linearised@1"


def test_accounting_names_the_planner_thread_as_unverifiable_and_the_rest_consistent(mapped):
    checks = mapped.records[-1]["accounting"]["checks"]
    verdicts = {(c["id"], c["scope"]): c["verdict"] for c in checks}
    assert verdicts[("aer.acc.agent_calls_vs_assistant@1", "thr0")] == "unverifiable"  # an auxiliary call made the only reply
    assert {v for k, v in verdicts.items() if k[1] != "thr0"} == {"consistent"}
    assert mapped.records[-1]["accounting"]["status"] == "unverifiable"
    dispatched = next(c for c in checks if c["id"] == "aer.acc.tool_calls_dispatched@1" and c["scope"] == "att0")
    assert dispatched["observed"] == {"denied": 1, "tool_calls": 6, "tool_executions": 5, "unexecuted": 0}


# ------------------------------------------------------------------------------------------------ closed schemas
def test_ext_foobench_validates_against_its_closed_schema(mapped):
    validator = jsonschema.Draft202012Validator(schema("ext.schema.json"))
    exts = [r["ext"]["foobench"] for r in mapped.records if "foobench" in r.get("ext", {})]
    assert len(exts) == 2
    for ext in exts:
        validator.validate(ext)
    for bad in ({"events": []}, {"events": [{"type": "x"}]}, {"other": 1}, {"events": [{"type": "x", "value": {}, "src": {"line": -1}, "after": [{"id": "m0", "b": "pos"}]}]}):
        assert not validator.is_valid(bad)


def test_the_profile_family_table_validates_against_its_closed_schema(foo):
    table = foo.profile().data["family"]["foobench"]
    plain = thaw(table)
    validator = jsonschema.Draft202012Validator(schema("family.schema.json"))
    validator.validate(plain)
    assert foo.profile().family_table() == table and foo.profile().family == "foobench"
    assert "status" not in foo.profile().data  # the registry is the only status store
    for broken in (
        {**plain, "extra": 1},
        {k: v for k, v in plain.items() if k != "actors"},
        {**plain, "guard_verdicts": {"pass": "maybe"}},
        {**plain, "actors": {"x": {"kind": "wizard"}}},
        {**plain, "actors": {"Bad Id": {"kind": "user"}}},
    ):
        assert not validator.is_valid(broken)


def test_the_profile_is_package_data_that_the_core_loader_accepts(foo):
    profile = foo.profile()
    assert (profile.id, profile.version, profile.source_id, profile.parts) == ("foobench", 1, "foobench", ("fixture",))
    assert profile.sha256 and profile.data["import"]["dialect"] == profile.data["import"]["mapper"] == "foobench.jsonl"
    assert profile.sha256 == hashlib.sha256(foo.profile_bytes()).hexdigest()


def test_artefact_catalogue_has_the_d152_fields_and_its_expected_counts_hold(mapped):
    """D.15.2 shape (the field set the shared loader accepts), rules and issue codes that exist, counts the fixture confirms."""
    doc = tomllib.loads((resources.files(PACKAGE) / "artefacts.toml").read_text(encoding="utf-8"))
    assert set(doc) == {"version", "family", "namespaces", "artefact"} and doc["version"] == 1 and isinstance(doc["version"], int)
    assert (doc["family"], doc["namespaces"]) == ("foobench", ["foobench"])
    catalogue = RuleRegistry.default().get("foobench", 1)
    fields = {"id", "title", "description", "scope", "cause", "detector", "recorded_as", "handling", "expected", "manuscript", "refs"}
    ids = [e["id"] for e in doc["artefact"]]
    assert len(ids) == len(set(ids)) >= 2 and all(i.startswith("foobench.art.") for i in ids)
    seen = {}
    for code in mapped.issue_codes():
        seen[code] = seen.get(code, 0) + 1
    for entry in doc["artefact"]:
        assert set(entry) == fields and set(entry["scope"]) <= {"profiles", "parts", "sources"}
        assert entry["cause"] in {"upstream_harness", "benchmark", "provider", "baseline_converter", "capture", "unknown"}
        assert entry["handling"]["class"] in {"CR", "DR", "RJ", "FO", "NR"}
        assert entry["detector"]["class"] in {"D", "I"} and isinstance(entry["manuscript"], bool)
        for rule in (entry["detector"]["rule"], entry["handling"]["rule"]):
            assert catalogue.get(rule) is not None
        (code,) = entry["recorded_as"]["issues"]
        assert catalogue.declares_issue_code(code)
        (expected,) = entry["expected"]
        assert expected["count"] == seen[code] and expected["status"] == "verified"  # the fixture confirms the count


# ------------------------------------------------------------------------------------------------ robustness
def test_a_malformed_file_still_ends_in_a_sealed_degenerate_aer(foo):
    events = foo.raw(foo.PRIMARY).splitlines()
    broken = b"\n".join([events[0], events[8]]) + b"\n"  # a tool_start for a call no reply made
    m = foo.map(broken, None)
    assert m.outcome.degenerate and m.outcome.error_code == "adapter.malformed_artefact"
    assert [r["k"] for r in m.records] == ["execution", "scope", "seal"]
    assert m.issue_codes() == ["unparseable_artefact"] and m.issues[0]["code"] == "unparseable_artefact"
    assert m.validate().ok and m.records[0]["task"] == {"benchmark": "foobench", "task_id": "task-001"}


def test_a_missing_or_broken_sub_agent_file_is_declared_not_fatal(foo):
    missing = foo.map(foo.raw(foo.PRIMARY), None)
    assert not missing.outcome.degenerate and "dangling_source_ref" in missing.issue_codes()
    assert [r["id"] for r in missing.of_kind("scope")] == ["run", "thr0", "att0", "sc0"]  # the hand-off is still recorded
    assert "sm0" not in missing.by_id() and missing.by_id()["sc0"]["spawned_by"] == "te2" and len(missing.records[0]["artifacts"]) == 1
    assert missing.by_id()["researcher"]["ev"] == "D" and missing.by_id()["researcher"]["unk"] == {"/model": "not_recorded"}
    assert missing.validate().ok
    broken = foo.map(foo.raw(foo.PRIMARY), b"not a foobench file\n")
    assert "unparseable_artefact" in broken.issue_codes() and "sm0" not in broken.by_id() and broken.validate().ok


def test_an_outside_the_table_verdict_is_kept_verbatim_and_declared_unknown(foo):
    events = foo.events(foo.raw(foo.PRIMARY))
    next(e for e in events if e.get("type") == "approval" and e["decision"] == "approve")["decision"] = "defer"
    m = foo.map(foo.lines(events))
    dc1 = m.by_id()["dc1"]
    assert "verdict" not in dc1 and dc1["unk"] == {"/verdict": "ambiguous"} and dc1["ext"]["foobench"] == {"verdict_raw": "defer"}
    assert "authorised_by" not in m.by_id()["te3"]  # an unknown verdict authorises nothing
    assert m.validate().ok
    jsonschema.Draft202012Validator(schema("ext.schema.json")).validate(dc1["ext"]["foobench"])


def test_unanswered_requests_and_unfinished_tools_are_declared(foo):
    events = foo.events(foo.raw(foo.PRIMARY))
    events.append({"type": "llm_request", "ts": "2026-10-01T12:01:00Z", "id": "r9", "thread": "main", "actor": "agent", "context": ["u0"]})
    events.append({"type": "text_action", "ts": "2026-10-01T12:01:01Z", "reply": "a15", "raw": "this is not an action"})
    m = foo.map(foo.lines(events))
    last_call = m.of_kind("model_call")[-1]
    assert last_call["unk"] == {"/status": "not_recorded"} and "status" not in last_call and last_call["input"] == ["m0"]
    unknown = [i for i in m.issues if i["code"] == "foobench.unmapped_event_type"]
    assert len(unknown) == 2 and m.validate().ok  # the unparseable text action is kept verbatim, never guessed
    events = foo.events(foo.raw(foo.PRIMARY))
    events.append({"type": "tool_start", "ts": "2026-10-01T12:01:00Z", "call": "c6", "name": "delete_file", "args": {"path": "scratch.txt"}})
    m = foo.map(foo.lines(events))  # the call the guard denied was dispatched after all, and never finished
    assert next(i for i in m.issues if i["code"] == "missing_tool_result")["ids"] == ["te6"]
    assert m.by_id()["te6"]["unk"] == {"/status": "not_recorded"} and m.validate().ok


def test_the_mapper_declares_its_contract(foo):
    mapper = FooMapper()
    assert mapper.mapper_id == "foobench.jsonl" and mapper.accepts == {("foobench.jsonl", "v1")}
    assert mapper.prov_primary(frozenset()) == "native" and set(mapper.namespaces) == {"foobench"}


def test_mapping_through_map_unit_matches_the_helper(foo, mapped):
    unit = foo.unit(foo.raw(foo.PRIMARY), foo.raw(foo.SUB))
    outcome = map_unit(unit, FooMapper(), foo.profile(), registry=foo.registry(), auxiliary={foo.SUB: foo.raw(foo.SUB)})
    data, _ = aer_bytes(outcome, registry=foo.registry())
    assert data == mapped.data
    # without the second file's bytes the file is declared unparseable, not fatal
    bare = map_unit(unit, FooMapper(), foo.profile(), registry=foo.registry())
    assert not bare.degenerate and [i["code"] for i in bare.issues if i["code"] == "unparseable_artefact"] == ["unparseable_artefact"]
