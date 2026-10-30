"""The DRIFT build of the TraceLogger mapper, the ``drift`` catalogue and profile (docs/architecture D.6.19; D-270..D-279).

Real inputs: nine byte-identical logs of ``SaFo-Lab/DRIFT@6fd3df47`` (MIT; ``tests/fixtures/drift/``, ``SOURCE.json`` per
K.4.1), loaded programmatically and never printed (R-42): they hold prompt-injection payloads by design. Behaviours no
fixture shows (the ``messages`` variant, an undeclared quirk, the history pin's plan reading) are tested by changing a real
log or the profile in memory.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import tomllib
from pathlib import Path
from typing import Any

import pytest
from agentdojo_support import Mapped

from agentprov.adapters.agentdojo import census
from agentprov.adapters.agentdojo.dialect import TraceLoggerReader
from agentprov.adapters.agentdojo.drift_mapper import DRIFT_VARIANTS, DriftMapper, call_error_check, is_call_error, text_form
from agentprov.adapters.agentdojo.profile import family_table
from agentprov.adapters.agentdojo.quirks import CensusFile, check_profile_hooks
from agentprov.adapters.profiles import SourceProfile, load_profile, parse_profile
from agentprov.adapters.registry import get_source
from agentprov.adapters.runner import aer_bytes, map_unit
from agentprov.adapters.types import ArtefactRef, ExecutionUnit, Origin
from agentprov.aer.rules import load_catalogue
from agentprov.ingest.limits import IngestLimits
from agentprov.testing import golden

REPO = Path(__file__).resolve().parents[3]
FIXTURES = REPO / "tests" / "fixtures" / "drift"
DIGESTS = Path(__file__).resolve().parent / "drift_aer_digests.json"
REGEN = "AGENTPROV_REGEN_DRIFT_AER"
PROFILE_PATH = REPO / "src" / "agentprov" / "adapters" / "agentdojo" / "profiles" / "drift.profile.toml"
CATALOGUE = REPO / "src" / "agentprov" / "adapters" / "agentdojo" / "rules" / "drift.rules.toml"
DRIFT_REPO = "https://github.com/SaFo-Lab/DRIFT"
HEAD = "6fd3df4763fad77398c3c273c2a4fe14dd50f7ea"
HISTORY = "53dbc6c58d5d1f044f3a68636be30b060bb86d34"


# ---------------------------------------------------------------------------------------------------- helpers
def _entries() -> list[dict[str, Any]]:
    if not (FIXTURES / "SOURCE.json").is_file():
        pytest.skip("the drift fixtures are not present")
    return list(json.loads((FIXTURES / "SOURCE.json").read_bytes()))


def _entry(fragment: str) -> dict[str, Any]:
    found = [e for e in _entries() if fragment in e["original_path"]]
    assert len(found) == 1, (fragment, len(found))
    return found[0]


def _raw(entry: dict[str, Any]) -> bytes:
    return (FIXTURES / entry["sample_file"]).read_bytes()


def map_drift(raw: bytes, path: str, *, profile: SourceProfile | None = None, commit: str = HEAD) -> Mapped:
    """Sniff, parse, map (DRIFT build) and seal ``raw`` as the DRIFT log at ``path`` of ``commit``."""
    profile = profile or load_profile("drift")
    reader, mapper, limits = TraceLoggerReader(), DriftMapper(), IngestLimits()
    sniff = reader.sniff(raw, label=path, limits=limits)
    assert sniff.match and sniff.variant in DRIFT_VARIANTS, sniff
    origin = Origin.git(DRIFT_REPO, commit, path, golden.git_blob_sha1(raw))
    artefact = ArtefactRef("a0", hashlib.sha256(raw).hexdigest(), len(raw), "application/json", origin, "primary",
                           mapper.prov_primary(sniff.flags))  # type: ignore[arg-type]
    item = next(reader.parse(raw, artefact, limits=limits))
    outcome = map_unit(ExecutionUnit(item), mapper, profile)
    data, info = aer_bytes(outcome)
    return Mapped(raw, outcome, data, info, profile)


def _fix(fragment: str, **kwargs: Any) -> Mapped:
    entry = _entry(fragment)
    return map_drift(_raw(entry), entry["original_path"], **kwargs)


def _profile_variant(edit: Any) -> SourceProfile:
    text = PROFILE_PATH.read_text(encoding="utf-8")
    return parse_profile(edit(text).encode("utf-8"), source="drift (test variant)")


def _census(m: Mapped) -> dict[str, dict[str, int]]:
    records = [r for r in m.records if r.get("k") != "seal"]
    return census.census_file(CensusFile(records, m.info.issues))


def _cites(record: dict[str, Any], rule: str) -> bool:
    return any(str(ref).split("#", 1)[0] in (rule, rule.replace("@", "_unverified@")) for ref in record.get("rule", ()))


# ---------------------------------------------------------------------------------------------------- fixtures, catalogue
def test_fixtures_are_byte_identical_to_the_pinned_blobs():
    for entry in _entries():
        raw = _raw(entry)
        assert hashlib.sha256(raw).hexdigest() == entry["sha256"], entry["sample_file"]
        assert golden.git_blob_sha1(raw) == entry["git_blob_sha1"], entry["sample_file"]
        assert entry["commit_or_revision"] == HEAD and entry["licence"].startswith("MIT")


def test_the_licence_notice_is_the_pinned_license_blob():
    notices = json.loads((REPO / "tests" / "fixtures" / "LICENSES" / "SOURCE.json").read_bytes())
    entry = next(e for e in notices if e["sample_file"] == "DRIFT-MIT.txt")
    raw = (REPO / "tests" / "fixtures" / "LICENSES" / "DRIFT-MIT.txt").read_bytes()
    assert (entry["repository"], entry["commit_or_revision"], entry["original_path"]) == (DRIFT_REPO, HEAD, "LICENSE")
    assert golden.git_blob_sha1(raw) == entry["git_blob_sha1"] and raw.startswith(b"MIT License")


def test_every_fixture_maps_and_validates_in_release_mode_with_pinned_digests():
    digests = {e["sample_file"]: hashlib.sha256(_fix(e["original_path"]).data).hexdigest() for e in _entries()}
    if os.environ.get(REGEN):
        DIGESTS.write_text(json.dumps(digests, indent=2, sort_keys=True) + "\n")
    assert digests == json.loads(DIGESTS.read_bytes())
    for entry in _entries():
        m = _fix(entry["original_path"])
        report = m.validate()
        assert report.ok, [(f.code, f.pointer) for f in report.errors][:5]
        assert map_drift(_raw(entry), entry["original_path"]).data == m.data  # deterministic


def test_every_drift_twin_restates_its_d_rule():
    doc = tomllib.loads(CATALOGUE.read_text(encoding="utf-8"))
    rules = {r["id"]: r for r in doc["rule"]}
    d_rules = [r for r in doc["rule"] if r["class"] == "D"]
    assert d_rules
    for d in d_rules:
        twin = rules[d["id"] + "_unverified"]
        assert twin["class"] == "I" and twin["status"] == "active" and not twin.get("code")
        assert twin["premises"] == d["premises"] and twin["statement"].endswith(d["statement"])
        assert d["id"] in twin["statement"] and "D.5.4" in twin["evidence"]
        assert d.get("code") and all(re.fullmatch(r"[0-9a-f]{40}", c["commit"]) for c in d["code"])
    for rule in doc["rule"]:
        for node in rule.get("tests", []):
            file, _, name = node.partition("::")
            assert f"def {name}(" in (REPO / file).read_text(encoding="utf-8"), f"{rule['id']}: {node}"
    catalogue = load_catalogue("drift")
    assert catalogue.get("drift.proposed_calls_reparsed@1").status == "reserved"
    assert "drift.isolation_pass" in catalogue.subtypes


def test_profile_loads_its_quirks_name_their_hook_rules_and_the_registry_lists_it():
    profile = load_profile("drift")
    table = family_table(profile)
    check_profile_hooks(profile.id, table)
    assert table.verified_code == () and table.version_label_semantics("banking") == "suite_version"
    assert table.version_label_semantics("github") == "label_not_suite_version"
    registration = get_source("drift")
    assert [c.part for c in registration.capabilities] == ["head", "history"]
    assert [c.import_status for c in registration.capabilities] == ["partial", "planned"]  # D-830: history is reference-only
    assert all(c.profile == "drift" for c in registration.capabilities)


# ---------------------------------------------------------------------------------------------------- header, actors, scopes
def test_the_drift_defence_comes_from_the_key_set():
    m = _fix("banking/user_task_12/important_instructions/injection_task_7")
    header = m.header
    assert header["dialect"] == {"id": "agentdojo.tracelogger", "variant": "drift.k18.conversations"}
    assert header["adapter"]["id"] == "agentdojo.tracelogger"
    assert header["task"]["defense_id"] == "drift" and header["evf"]["/task/defense_id"] == "I"
    assert "drift.defence_from_keyset_unverified@1#/task/defense_id" in header["rule"]
    defence = [a for a in m.of_kind("actor") if a.get("kind") == "defense"]
    assert [d["name"] for d in defence] == ["drift"] and defence[0]["id"] == "def0" and defence[0]["ev"] == "I"
    agent = m.get("agent")
    assert agent["model"]["requested"] == "gpt-4o-mini-2024-07-18" and agent["evf"]["/model"] == "I"


def test_header_keeps_drift_fields_verbatim_with_their_readings():
    m = _fix("banking/user_task_12/important_instructions/injection_task_7")
    header, doc = m.header, json.loads(m.raw)
    drift = header["ext"]["drift"]
    assert drift["config"] == {k: doc[k] for k in ("build_constraints", "injection_isolation", "dynamic_validation", "adaptive_attack")}
    assert drift["tool_permission"] == doc["tool_permission"] and drift["total_tokens"] == doc["total_tokens"]
    assert drift["plan"] == {"trajectory": doc["initial_trajectory"], "checklist": doc["initial_checklist"]}
    assert header["ext"]["agentdojo"] == {"pipeline_name": doc["pipeline_name"]}  # DRIFT logs no run error
    for rule in ("drift.total_tokens_scope", "drift.tool_permission_per_process", "drift.no_system_message", "drift.no_injection_map"):
        assert f"{rule}_unverified@1" in header["rule"], rule
    assert header["ns"]["drift"] == "https://w3id.org/agentprov/ns/drift#"
    bench = m.get("bench")
    assert bench["version"] == "v1.2" and "version_label_semantics" not in bench.get("ext", {}).get("agentdojo", {})
    run = m.get("run")
    assert run["t"]["dur_s"] == doc["duration"] and "drift.duration_scope_unverified@1" in run["rule"]
    assert not any(r.get("k") == "message" and r.get("role") == "system" for r in m.records)


def test_one_attempt_index_zero_and_no_retry_issue():
    m = _fix("workspace/user_task_2/important_instructions/injection_task_2")
    att = m.get("att0")
    assert att["index"] == 0 and att["ev"] == "I" and "drift.single_pass_unverified@1#/index" in att["rule"]
    assert not {"earlier_attempts_unobservable", "retry_passes_inferred"} & set(m.codes)


def test_no_fixtures_and_the_info_issue():
    m = _fix("workspace/user_task_2/important_instructions/injection_task_2")
    assert not m.of_kind("fixture")
    assert [i["ids"] for i in m.issues("drift.injection_map_not_recorded")] == [["exec"]]
    benign = _fix("shopping/user_task_13/none/none")
    assert not benign.issues("drift.injection_map_not_recorded")


def test_plan_semantics_follow_the_profile_and_are_checked():
    head = _fix("banking/user_task_12/important_instructions/injection_task_7")
    assert head.header["ext"]["drift"]["plan_semantics"] == "initial_plan"
    assert "drift.plan_fields_semantics_unverified@1#/ext/drift/plan_semantics" in head.header["rule"]
    # the same raw planner text under the history pin's end-of-run reading is a contradiction: reported, not written
    as_history = _fix("banking/user_task_12/important_instructions/injection_task_7", commit=HISTORY)
    assert "plan_semantics" not in as_history.header["ext"]["drift"]
    assert as_history.issues("drift.plan_semantics_contradicted")
    # a log whose checklist is end-of-run JSON reads as final_plan_state under the history pin
    entry = _entry("banking/user_task_12/important_instructions/injection_task_7")
    doc = json.loads(_raw(entry))
    doc["initial_checklist"] = json.dumps([{"name": "read_file"}])
    m = map_drift(json.dumps(doc, indent=4).encode(), entry["original_path"], commit=HISTORY)
    assert m.header["ext"]["drift"]["plan_semantics"] == "final_plan_state" and not m.issues("drift.plan_semantics_contradicted")


# ---------------------------------------------------------------------------------------------------- messages
def test_call_error_is_a_validator_denial():
    m = _fix("banking/user_task_8/important_instructions/injection_task_3")
    doc = json.loads(m.raw)
    denials = [d for d in m.of_kind("decision") if d["verdict"] == "deny"]
    assert sorted(d["ext"]["drift"]["check"] for d in denials) == ["checklist", "trajectory"]
    for dc in denials:
        assert dc["actor"] == "def0" and dc["ev"] == "I" and _cites(dc, "drift.call_error_user_is_validator@1")
        subject = m.get(dc["subject"])
        assert subject["role"] == "assistant" and not [p for p in subject["parts"] if p["t"] == "tool_call"]
        assert dc["evf"]["/reason"] == "O" and is_call_error(dc["reason"])
        message = next(r for r in m.of_kind("message") if r.get("generated_by") == dc["id"])
        assert message["role"] == "user" and message["actor"] == "def0" and message["evf"]["/actor"] == "I"
        index = int(message["id"][1:])
        assert doc["conversations"][index]["content"] == message["parts"][0]["text"]
    # the user actor keeps the task prompt only
    assert [r["id"] for r in m.of_kind("message") if r.get("actor") == "user"] == ["m0"]
    assert "unattributed_additional_user_message" not in m.codes
    counts = _census(m)["agentdojo.drift_call_error_as_user"]
    assert counts == {"messages": 2, "files": 1, "trajectory": 1, "checklist": 1}
    assert call_error_check("... does not align with original planned trajectory ...") == "trajectory"


def test_assistant_text_form_and_unrecorded_prompt():
    m = _fix("banking/user_task_12/important_instructions/injection_task_7")
    doc = json.loads(m.raw)
    for rec in (r for r in m.of_kind("message") if r["role"] == "assistant"):
        content = doc["conversations"][int(rec["id"][1:])]["content"]
        assert rec["ext"]["drift"]["text_form"] == text_form(content)
        assert rec["evf"]["/ext/drift/text_form"] == "I"
    for mc in m.of_kind("model_call"):
        assert "input" not in mc and mc["unk"]["/input"] == "not_recorded"
    assert [i["ids"] for i in m.issues("drift.agent_prompt_not_recorded")] == [["mc0"]]
    assert text_form("<function_thought>t</function_thought>\n\n<function_call>[f()]</function_call>\n\n"
                     "<final_answer>a</final_answer>") == "reserialised"
    assert text_form("free text") == "raw"


def test_final_text_calls_not_executed_raise_the_issue():
    reserialised = _fix("banking/user_task_1/important_instructions/injection_task_5")
    raw = _fix("dailylife/user_task_10/important_instructions/injection_task_2")
    two = _fix("banking/user_task_14/important_instructions/injection_task_1")
    for m, detail in ((reserialised, "reserialised"), (raw, "raw")):
        issue = m.issues("drift.calls_in_text_not_executed")
        assert [i["detail"] for i in issue] == [detail]
        last = [r for r in m.of_kind("message")][-1]
        assert issue[0]["ids"] == [last["id"]] and last["ext"]["agentdojo"]["calls_form"] == "empty_list"
    assert not two.issues("drift.calls_in_text_not_executed")  # no <function_call> tag: nothing was proposed


def test_isolation_decision_on_the_last_result_of_each_batch():
    m = _fix("workspace/user_task_5/important_instructions/injection_task_9")
    tools = [r for r in m.of_kind("message") if r["role"] == "tool"]
    assert len(tools) == 2  # one batch of two calls
    first, last = tools
    assert m.get(first["generated_by"])["k"] == "tool_execution" and first["actor"] == "env"
    dc = m.get(last["generated_by"])
    assert dc["k"] == "decision" and dc["verdict"] == "other" and dc["subtype"] == "drift.isolation_pass"
    assert m.get(dc["subject"])["k"] == "tool_execution" and dc["ev"] == "I"
    assert dc["unk"]["/original"] == "ambiguous" and last["actor"] == "def0"
    for msg in tools:
        call = msg["parts"][0]["responds_to"]
        # linked by id (D.6.6.1 rule 1), cited through the rule's twin (D-272): class I
        assert msg["evf"]["/parts/0/responds_to"] == "I" and m.get(call.split("#")[0])["role"] == "assistant"
        assert "agentdojo.call_id_unique_match_unverified@1#/parts/0/responds_to" in msg["rule"]
    every = _census(_fix("banking/user_task_12/important_instructions/injection_task_7"))
    assert every["agentdojo.drift_tool_output_post_isolation"] == {"isolation_decisions": 2, "tool_messages": 2}


def test_judgements_and_the_benign_constant():
    attacked = _fix("workspace/user_task_2/important_instructions/injection_task_2")
    benign = _fix("shopping/user_task_13/none/none")
    security = next(j for j in attacked.of_kind("judgement") if j["name"] == "security")
    assert security["value"] is True and security["origin"] == "checker" and security["unk"] == {"/inputs": "not_recorded"}
    constant = next(j for j in benign.of_kind("judgement") if j["name"] == "security")
    assert constant["value"] is True and constant["origin"] == "harness_default"
    assert "drift.benign_security_constant_unverified@1#/origin" in constant["rule"]
    assert benign.get("bench")["ext"]["agentdojo"]["version_label_semantics"] == "label_not_suite_version"
    agentdyn = _fix("dailylife/user_task_6/important_instructions/injection_task_7")
    assert agentdyn.header["task"]["benchmark"] == "agentdyn"


# ---------------------------------------------------------------------------------------------------- variants, quirks
def test_the_messages_variant_maps_like_conversations_under_its_own_key():
    """AgentDyn variant C is DRIFT output re-keyed to ``messages`` (agentdyn.variant_c_rekey@1)."""
    entry = _entry("banking/user_task_8/important_instructions/injection_task_3")
    doc = json.loads(_raw(entry))
    rekeyed = {("messages" if k == "conversations" else k): v for k, v in doc.items()}
    profile = _profile_variant(lambda t: t.replace('variants = ["drift.k18.conversations"]',
                                                    'variants = ["drift.k18.conversations", "drift.k18.messages"]'))
    a = map_drift(_raw(entry), entry["original_path"], profile=profile)
    b = map_drift(json.dumps(rekeyed, indent=4).encode(), entry["original_path"], profile=profile)
    assert b.header["dialect"]["variant"] == "drift.k18.messages" and b.validate().ok
    strip = lambda m: [{k: v for k, v in r.items() if k not in ("src", "ex", "source_key", "artifacts")}  # noqa: E731
                       for r in m.records[1:-1]]
    assert strip(a) == strip(b)
    assert all(s["p"].startswith("/messages/") for r in b.of_kind("message") for s in r["src"])


def test_an_undeclared_quirk_is_reported_and_not_applied():
    def drop_call_error(text: str) -> str:
        block = re.search(r'\[\[family\.agentdojo\.quirk\]\]\nid = "agentdojo\.drift_call_error_as_user"\n(?:.+\n)+', text)
        assert block is not None
        return text.replace(block.group(0), "")

    m = _fix("banking/user_task_8/important_instructions/injection_task_3", profile=_profile_variant(drop_call_error))
    assert not [d for d in m.of_kind("decision") if d["verdict"] == "deny"]
    assert len(m.issues("unattributed_additional_user_message")) == 2
    assert [i["detail"] for i in m.issues("agentdojo.undeclared_quirk")] == ["agentdojo.drift_call_error_as_user"]


def test_the_census_hooks_reproduce_the_fixture_counts():
    totals: dict[str, dict[str, int]] = {}
    for entry in _entries():
        census.add(totals, _census(_fix(entry["original_path"])))
    assert totals["agentdojo.drift_no_system_no_injections"] == {"system_messages": 0, "fixtures": 0}
    assert totals["agentdojo.drift_plan_fields_by_commit"] == {"initial_plan": 9, "final_plan_state": 0, "contradicted": 0}
    assert totals["agentdojo.drift_calls_in_text_not_executed"]["final_turns"] >= 3
    assert totals["agentdojo.benign_security_constant"]["files"] == 1


def test_drift_mapper_refuses_other_variants_and_malformed_drift_logs():
    from agentprov.errors import MalformedArtefact, UnsupportedVariant

    entry = _entry("banking/user_task_14/important_instructions/injection_task_1")
    doc = json.loads(_raw(entry))
    bad = copy.deepcopy(doc)
    bad["tool_permission"] = []
    with pytest.raises(MalformedArtefact):
        list(DriftMapper().map(*_unit(json.dumps(bad, indent=4).encode(), entry["original_path"])))
    profile = _profile_variant(lambda t: t.replace('variants = ["drift.k18.conversations"]', 'variants = ["v1.k14"]'))
    with pytest.raises(UnsupportedVariant):
        list(DriftMapper().map(*_unit(_raw(entry), entry["original_path"], profile)))


def _unit(raw: bytes, path: str, profile: SourceProfile | None = None) -> tuple[ExecutionUnit, Any]:
    from agentprov.adapters.runner import MapContext
    from agentprov.aer.rules import RuleRegistry

    profile = profile or load_profile("drift")
    reader, limits = TraceLoggerReader(), IngestLimits()
    origin = Origin.git(DRIFT_REPO, HEAD, path, golden.git_blob_sha1(raw))
    artefact = ArtefactRef("a0", hashlib.sha256(raw).hexdigest(), len(raw), "application/json", origin, "primary", "unknown")
    item = next(reader.parse(raw, artefact, limits=limits))
    return ExecutionUnit(item), MapContext(profile, RuleRegistry.default(), "m", "ex_x")


def test_a_matching_mapping_hook_is_reported_not_skipped():
    """RT-1: the DRIFT build runs no quirk hook point; a declared quirk whose hook implements one and whose selector
    matches the file is flagged (``drift.quirk_hook_not_applied``), never ignored. Census-only hooks are inert."""
    from agentprov.adapters.agentdojo.drift_mapper import mapping_hook_points
    from agentprov.adapters.agentdojo.quirks import hooks

    registered = hooks()
    drift_hooks = [h for q, h in registered.items() if q.startswith("agentdojo.drift_") and q != "agentdojo.drift_integrated_user_error_key"]
    assert drift_hooks and all(mapping_hook_points(h) == () for h in drift_hooks)
    assert mapping_hook_points(registered["agentdojo.progent_denial"]) == ("tool_message",)

    def with_progent(applies: str) -> Any:
        return lambda text: text + (f'\n[[family.agentdojo.quirk]]\nid = "agentdojo.progent_denial"\napplies = {applies}\n'
                                    'rules = ["agentdyn.progent_denial_pattern@1"]\n')

    fragment = "banking/user_task_12/important_instructions/injection_task_7"
    flagged = _fix(fragment, profile=_profile_variant(with_progent("{}")))
    assert [i["detail"] for i in flagged.issues("drift.quirk_hook_not_applied")] == ["agentdojo.progent_denial"]
    assert flagged.issues("drift.quirk_hook_not_applied")[0]["rule"] == "agentdyn.progent_denial_pattern@1"
    assert flagged.validate().ok
    other_suite = _fix(fragment, profile=_profile_variant(with_progent('{ suite = ["slack"] }')))
    assert not other_suite.issues("drift.quirk_hook_not_applied")
    for entry in _entries():
        assert not _fix(entry["original_path"]).issues("drift.quirk_hook_not_applied")


def test_the_guard_covers_the_log_end_hook_point():
    """D-116 added the ``log_end`` hook point (phase 10d R10, ``detector_abort``). The DRIFT build does not run it, so a
    declared quirk whose hook sets only ``log_end`` and whose selector matches a DRIFT file is flagged (RT-1)."""
    import dataclasses

    from agentprov.adapters.agentdojo.drift_mapper import mapping_hook_points
    from agentprov.adapters.agentdojo.hooks import detector_abort
    from agentprov.adapters.agentdojo.quirks import QuirkHook, hooks

    only_log_end = QuirkHook(quirk_id="agentdojo.test_log_end", rules=(), log_end=lambda view, end: None)
    assert mapping_hook_points(only_log_end) == ("log_end",)
    # every mapping hook point of QuirkHook is seen, one at a time
    for f in dataclasses.fields(QuirkHook):
        if f.name not in ("quirk_id", "rules", "namespaces", "census"):
            hook = dataclasses.replace(QuirkHook(quirk_id="agentdojo.x", rules=()), **{f.name: lambda *a: None})
            assert mapping_hook_points(hook) == (f.name,), f.name
    registered = hooks()[detector_abort.QUIRK_ID]
    assert mapping_hook_points(registered) == ("log_end",)
    rule = registered.rules[0]
    profile = _profile_variant(lambda text: text + (f'\n[[family.agentdojo.quirk]]\nid = "{detector_abort.QUIRK_ID}"\n'
                                                    f'applies = {{}}\nrules = ["{rule}"]\n'))
    m = _fix("banking/user_task_12/important_instructions/injection_task_7", profile=profile)
    issues = m.issues("drift.quirk_hook_not_applied")
    assert [(i["detail"], i["rule"]) for i in issues] == [(detector_abort.QUIRK_ID, rule)]
    assert not [d for d in m.of_kind("decision") if d.get("verdict") == "terminate"] and m.validate().ok
