"""The ``survey-runs`` profile (docs/architecture D.4.4, D.6.4, D.6.7, D.6.15; phase 10): the AgentDojo run logs of the Agent
Security Tools Survey.

Synthetic logs written the way AgentDojo 0.1.35 writes them exercise each rule; the six real fixtures
(``tests/fixtures/survey/``, byte-identical blobs of ``Forever-CodingNoob/agent-security-tools-survey@89c4db2c``, CC-BY-4.0)
are loaded programmatically and never printed (R-42). The survey's AgentHarm part belongs to the profile ``survey-agentharm``.
"""

from __future__ import annotations

import json
import os
from typing import Any

import pytest
from agentdojo_support import map_log
from source_support import (
    DIGESTS,
    FIXTURES,
    REGEN,
    SOURCES,
    call,
    final,
    fixture_bytes,
    fixture_entries,
    log_with,
    map_fixture,
    map_synthetic,
    ok,
    result,
    turn,
    v1_log,
)

from agentprov.adapters.agentdojo import census
from agentprov.adapters.agentdojo.identity import resolve
from agentprov.adapters.agentdojo.layout import parse_layout
from agentprov.adapters.agentdojo.profile import check_against_schema, family_schema, family_table
from agentprov.adapters.agentdojo.quirks import CensusFile
from agentprov.adapters.profiles import load_profile
from agentprov.adapters.registry import get_source
from agentprov.aer.reader import load_aer_bytes
from agentprov.aer.rules import load_catalogue
from agentprov.testing import golden

PROFILE = "survey-runs"
ERROR = "Skipping task user_task_9 because of openai InternalServerError: Error code: 500 - {'error': {'message': 'error parsing tool call'}}"
MODELS = {"runs_qwen3_14b": "qwen3:14b", "runs_qwen3-coder_30b": "qwen3-coder:30b", "runs_gpt-oss_120b": "gpt-oss:120b"}


def survey_path(slug: str, doc: dict[str, Any]) -> str:
    attack = doc.get("attack_type") or "none"
    return (f"agentdojo/results/{slug}/openai-compatible/{doc['suite_name']}/{doc['user_task_id']}/{attack}/"
            f"{doc.get('injection_task_id') or 'none'}.json")


def survey_log(messages: list[dict[str, Any]], slug: str = "runs_qwen3_14b", **overrides: Any) -> tuple[dict[str, Any], str]:
    doc = log_with(messages, **{"pipeline_name": "openai-compatible", "benchmark_version": "v1.2.2", **overrides})
    return doc, survey_path(slug, doc)


def simple() -> list[dict[str, Any]]:
    c = call("send_money", {"recipient": "X", "amount": 10}, "call_ab12cd34")
    return [turn(c), result(c, "{'message': 'sent'}"), final()]


# ------------------------------------------------------------------------------------------------ identity
def test_the_model_comes_from_the_results_directory():
    """survey.model_from_results_dir@1: the slug table, never the logged pipeline_name (the constant openai-compatible)."""
    table = family_table(load_profile(PROFILE))
    assert dict(table.identity["slug_to_model"]) == MODELS and table.identity["pipeline_name_policy"] == "constant_not_model"
    layout = table.layout
    assert layout is not None
    assert layout.match("clone/agentdojo/results/runs_qwen3_14b/openai-compatible/banking/user_task_0/important_instructions/injection_task_0.json") == {
        "results_dir": "runs_qwen3_14b", "pipeline_dir": "openai-compatible", "suite": "banking", "task_dir": "user_task_0",
        "attack_dir": "important_instructions", "file": "injection_task_0"}
    for slug, model in MODELS.items():
        doc, path = survey_log(simple(), slug)
        m = map_synthetic(PROFILE, doc, path)
        ok(m)
        agent = m.get("agent")
        assert agent["model"] == {"requested": model} and agent["evf"] == {"/model": "I"}
        assert "survey.model_from_results_dir@1#/model" in agent["rule"] and agent["src"] == [{"a": "a0", "o": "/path"}]
        assert not m.issues("agentdojo.pipeline_name_mismatch") and not m.issues("identity_unresolved")
        assert m.header["ext"]["agentdojo"]["pipeline_name"] == "openai-compatible"  # verbatim, never the identity
        assert m.header["task"]["defense_id"] is None


def test_an_unknown_results_directory_resolves_nothing():
    doc, path = survey_log(simple(), "runs_other_model")
    m = map_synthetic(PROFILE, doc, path)
    ok(m)
    assert m.issues("identity_unresolved")[0]["ids"] == ["agent"] and "model" not in m.get("agent")
    table = family_table(load_profile(PROFILE))
    assert resolve(table.identity, {"results_dir": "runs_other_model"}, "openai-compatible").model is None


def test_a_pipeline_name_that_names_a_model_is_still_not_compared():
    doc, path = survey_log(simple(), "runs_qwen3_14b", pipeline_name="openai-compatible-qwen3:14b")
    m = map_synthetic(PROFILE, doc, path)
    ok(m)
    assert not m.issues("agentdojo.pipeline_name_mismatch") and m.get("agent")["model"] == {"requested": "qwen3:14b"}


# ------------------------------------------------------------------------------------------------ the run-error patch
def test_a_run_error_imposes_the_patched_outcome():
    """D.6.7 row 1 under survey.internal_server_error_patch@1: harness_default, evidence class I (the patch is a claim)."""
    c = call("send_email", {"to": "x"}, "call_ab12cd34")
    doc, path = survey_log([turn(c), result(c, "")], "runs_gpt-oss_120b", error=ERROR, utility=False, security=True)
    m = map_synthetic(PROFILE, doc, path)
    ok(m)
    utility, security = m.of_kind("judgement")
    for j, value in ((utility, False), (security, True)):
        assert j["origin"] == "harness_default" and j["value"] is value and j["evf"] == {"/origin": "I"}
        assert j["rule"] == ["survey.internal_server_error_patch@1#/origin"]
    issue = m.issues("outcome_imposed_by_runner")[0]
    assert issue["rule"] == "survey.internal_server_error_patch@1" and issue["ids"] == ["j0", "j1"]
    assert m.header["ext"]["agentdojo"]["error"] == ERROR  # the run error verbatim
    assert not m.issues("agentdojo.undeclared_quirk")
    counts = census.census_file(CensusFile(m.records, m.info.issues))
    assert counts["agentdojo.run_error_imposes_outcome"] == {"files": 1}


def test_an_upstream_run_error_keeps_its_class_d_origin():
    """The origin takes the class of its rule: the upstream rule is D, so the generic path is unchanged (D.6.12)."""
    m = map_log(v1_log(error="boom", utility=False, security=True), profile=load_profile("agentdojo-upstream"))
    ok(m)
    for j in m.of_kind("judgement"):
        assert j["evf"] == {"/origin": "D"} and j["rule"] == ["agentdojo.run_error_imposed_outcome@1#/origin"]


# ------------------------------------------------------------------------------------------------ the other quirks
def test_unexecuted_trailing_calls_are_reported():
    c = call("search", {"q": "x"}, "call_ab12cd34")
    doc, path = survey_log([turn(c, text="")], user_task_id="user_task_3", injection_task_id=None, attack_type=None, injections={})
    m = map_synthetic(PROFILE, doc, path)
    ok(m)
    assert m.issues("unexecuted_tool_call")[0]["ids"] == ["m2#1"] and not m.of_kind("tool_execution")
    counts = census.census_file(CensusFile(m.records, m.info.issues))["agentdojo.unexecuted_trailing_calls"]
    assert counts == {"calls": 1, "logs": 1, "traces": 1}


def test_the_solvability_prepass_is_labelled_not_benign():
    doc, path = survey_log(simple(), user_task_id="injection_task_4", injection_task_id=None, attack_type=None, injections={})
    m = map_synthetic(PROFILE, doc, path)
    ok(m)
    assert m.header["ext"]["agentdojo"]["task_kind"] == "injection_task_as_user_task"
    counts = census.census_file(CensusFile(m.records, m.info.issues))
    assert counts["agentdojo.injection_task_as_user_task_prepass"] == {"files": 1}
    assert counts["agentdojo.benign_security_constant"] == {"files": 1, "origin_rule_applied": 1}


def test_security_means_the_injection_succeeded_whatever_the_readme_says():
    """semantic_trap_security_gloss: the code semantics apply, so the SEM reading of security=True is attack_succeeded."""
    from agentprov.adapters.semantics_profiles import load_semantics_profile

    profile = load_semantics_profile("agentdojo.suites", 1)
    doc, path = survey_log(simple(), security=True, utility=False)
    m = map_synthetic(PROFILE, doc, path)
    claims = {a.target: a.value for a in profile.annotate(load_aer_bytes(m.data)) if a.type == "outcome"}
    assert claims["j1"] == {"claim": "attack_succeeded", "holds": True} and claims["j0"] == {"claim": "user_task_solved", "holds": False}
    quirk = family_table(load_profile(PROFILE)).quirk("agentdojo.semantic_trap_security_gloss")
    assert quirk is not None and "resist" in str(quirk.note) and quirk.rules == ("agentdojo.security_polarity@1",)


def test_the_structural_rules_are_the_unverified_twins():
    """D.5.4 'I twins': the survey's patched fork is unpinned, so survey-runs cites the _unverified twins."""
    doc, path = survey_log(simple())
    m = map_synthetic(PROFILE, doc, path)
    assert m.get("run")["rule"] == ["agentdojo.naive_local_timestamp_unverified@1#/t/start"]
    assert "agentdojo.tool_msg_is_one_execution_unverified@1" in m.get("te0")["rule"]
    assert m.get("te0")["ev"] == "I"


# ------------------------------------------------------------------------------------------------ profile and registry
def test_profile_pins_licence_and_selection():
    profile = load_profile(PROFILE)
    data = profile.data
    pins = {p["role"]: p for p in data["source"]["pins"]}
    git = pins["git"]
    assert git["commit"] == "89c4db2c949797fbb38c5bfed85dc82780ddbfe3" and git["primary"] is True and git["part"] == "agentdojo-runs"
    assert git["tree"] == "agentdojo" and git["expected_files"] == 3256 and git["expected_bytes"] == 43_565_675
    assert pins["zenodo_v1_0_0"]["doi"] == "10.5281/zenodo.22135957" and pins["zenodo_v1_0_1"]["doi"] == "10.5281/zenodo.22140262"
    assert pins["zenodo_v1_0_0"]["primary"] is False and pins["zenodo_v1_0_1"]["primary"] is False
    assert data["source"]["concept_doi"] == "10.5281/zenodo.22135956"
    assert data["licence"]["spdx"] == "CC-BY-4.0" and data["licence"]["holders"] == ("Jhih-Jhong Lin",) and data["licence"]["policy"] == "include"
    imp = data["import"]
    assert tuple(imp["include"]) == ("agentdojo/results/runs_*/openai-compatible/**/*.json",)
    excludes = {(e["glob"], e["code"]) for e in imp["exclude"]}
    assert ("asb/results/*.csv", "select.dialect_planned") in excludes
    assert ("agentdojo/agentdojo/**", "select.owned_elsewhere") in excludes
    assert ("agentharm/results/**/*.eval", "select.owned_elsewhere") in excludes
    owned = next(e for e in imp["exclude"] if e["glob"].startswith("agentharm"))
    assert owned["owner"] == "agent-security-tools-survey" and owned["owner_corpus"] == "ast-survey-agentharm"
    assert tuple(imp["context_artefacts"]) == ("agentdojo/results/runs_*/console_*.log", "agentdojo/results/timing_summary.csv",
                                               "agentdojo/run_full_benchmark.sh")
    assert dict(imp["rules"]) == {ns: load_catalogue(ns).version for ns in imp["rules"]} == {"aer": 1, "agentdojo": 2, "survey": 1}
    assert tuple(data["family"]["agentdojo"]["harness"]["verified_code"]) == ()  # the patched fork is unpinned (D-24)
    agentharm = load_profile("survey-agentharm")
    assert agentharm.data["source"]["pins"][0]["commit"] == git["commit"]  # the shared pin


def test_family_part_conforms_to_the_closed_schema_both_checkers():
    jsonschema = pytest.importorskip("jsonschema")
    table = family_table(load_profile(PROFILE))
    jsonschema.validate(table.data, family_schema())
    assert check_against_schema(table.data, family_schema()) == []


def test_every_quirk_rule_exists_and_every_observed_key_has_a_census_function():
    table = family_table(load_profile(PROFILE))
    for quirk in table.quirks:
        for rule in quirk.rules:
            entry = load_catalogue(rule.split(".", 1)[0]).get(rule)
            assert entry is not None and entry.citable, (quirk.id, rule)
    assert [p for p in census.compare(table, "agentdojo-runs", {}) if "no census function" in p] == []
    declared = census.declared(table, "agentdojo-runs")
    assert declared["agentdojo.run_error_imposes_outcome"] == {"files": 11}
    assert declared["agentdojo.unexecuted_trailing_calls"]["traces"] == 48
    assert declared["agentdojo.injection_task_as_user_task_prepass"] == {"files": 105}
    layout = parse_layout(str(load_profile(PROFILE).data["import"]["layout"]))
    assert layout.names == {"results_dir", "pipeline_dir", "suite", "task_dir", "attack_dir", "file"}


def test_the_catalogue_declares_the_two_rules_at_class_i():
    catalogue = load_catalogue("survey")
    assert sorted(catalogue.rules) == ["survey.internal_server_error_patch@1", "survey.model_from_results_dir@1"]
    assert {r.cls for r in catalogue.rules.values()} == {"I"}


def test_registry_entry_is_gated_and_lazy():
    source = get_source("agent-security-tools-survey")
    parts = {c.part: c for c in source.capabilities}
    assert set(parts) == {"agentharm", "agentdojo-runs"}
    part = parts["agentdojo-runs"]
    assert part.profile == PROFILE and part.variants == ("v1.k14",) and part.corpus_id == "ast-survey-agentdojo"
    assert part.import_status in ("partial", "supported") and part.target_import_status == "supported" and part.caveat
    assert part.reader == "agentprov.adapters.agentdojo.dialect:TraceLoggerReader"
    assert parts["agentharm"].corpus_id == "ast-survey-agentharm" and parts["agentharm"].profile == "survey-agentharm"
    if part.import_status == "supported":  # D.3.2: only with the full pinned snapshot imported and recorded (HON-10)
        assert "docs/reports/survey/import-cli-agentdojo-runs.json" in part.caveat
    else:
        assert "full snapshot not yet imported" in part.caveat


# ------------------------------------------------------------------------------------------------ real fixtures
def test_fixtures_are_provenanced_and_licensed():
    entries = fixture_entries("survey")
    on_disk = {p.relative_to(FIXTURES / "survey").as_posix() for p in (FIXTURES / "survey").rglob("*") if p.is_file()} - {"SOURCE.json"}
    assert on_disk == {e["sample_file"] for e in entries}
    for e in entries:
        raw = fixture_bytes("survey", e)
        assert e["commit_or_revision"] == SOURCES["survey"]["commit"] and e["licence_class"] == "permissive" and e["synthetic"] is False
        assert e["size_bytes"] == len(raw) and e["sample_file"] == e["original_path"] and "/openai-compatible/" in e["original_path"]
    licence = (FIXTURES / "LICENSES" / "Survey-CC-BY-4.0.txt").read_text(encoding="utf-8")
    assert "Attribution 4.0 International" in licence


def test_real_fixtures_map_validate_and_keep_their_aer_bytes():
    """D.6.10 items 1 and 5: every real fixture maps, validates in release mode, carries the D.6.15 facts, and its AER bytes
    are pinned (regenerate with ``AGENTPROV_REGEN_AGENTDOJO_AER=1``)."""
    produced: dict[str, str] = {}
    profile = load_profile(PROFILE)
    totals: dict[str, dict[str, int]] = {}
    for entry in fixture_entries("survey"):
        m = map_fixture("survey", entry)
        ok(m)
        slug = entry["original_path"].split("/")[2]
        assert not m.outcome.degenerate and m.header["profile"] == profile.header() and m.header["dialect"]["variant"] == "v1.k14"
        assert m.header["artifacts"][0]["prov_primary"] == "native" and not m.issues("identity_unresolved")
        assert m.get("m0")["ext"]["agentdojo"]["system_prompt_variant"] == "agentdojo_default"
        assert m.get("agent")["model"] == {"requested": MODELS[slug]}
        assert m.get("bench")["version"] == "v1.2.2" and m.get("bench")["code"] == {"dist": "agentdojo", "dist_version": "0.1.35"}
        assert m.header["ext"]["agentdojo"]["pipeline_name"] == "openai-compatible"
        census.add(totals, census.census_file(CensusFile(m.records, m.info.issues)))
        produced[entry["original_path"]] = golden.sha256_hex(m.data)
    assert totals["agentdojo.run_error_imposes_outcome"] == {"files": 2}  # both gpt-oss fixtures
    assert totals["agentdojo.unexecuted_trailing_calls"]["traces"] == 1
    assert totals["agentdojo.injection_task_as_user_task_prepass"] == {"files": 2}
    path = DIGESTS / "survey_aer_digests.json"
    if os.environ.get(REGEN):
        path.write_text(json.dumps(dict(sorted(produced.items())), indent=2) + "\n", encoding="utf-8")
    expected = json.loads(path.read_text(encoding="utf-8"))
    assert sorted(k for k, v in produced.items() if expected.get(k) != v) == [] and set(expected) == set(produced)


def test_the_use_restriction_is_a_property_of_the_part_and_the_info_table_keeps_a_gap():
    """The survey registers an AgentHarm part (restricted use, U-05) and an AgentDojo part (CC-BY-4.0 only); ``info`` shows
    each part's own restriction, and its longest label keeps a space before the role column."""
    from agentprov.adapters.registry.render import registry_rows
    from agentprov.cli.info import _registry_lines

    rows = registry_rows()
    parts = {(r["source_id"], r["part"]): r for r in rows["parts"]}
    assert parts[("agent-security-tools-survey", "agentharm")]["restricted"] is True
    assert parts[("agent-security-tools-survey", "agentdojo-runs")]["restricted"] is False
    assert parts[("mandate-agentdojo-eval", "head")]["restricted"] is False
    lines = _registry_lines({**rows, "note": ""})
    line = next(row for row in lines if "agentdojo-runs" in row)
    assert "agentdojo-runs  " in line and "(restricted)" not in line
    label, role = max(((f"{r['source_id']} · {r['part']}", r["role"]) for r in rows["parts"]), key=lambda x: len(x[0]))
    assert any(row.startswith(f"  {label}  {role}") for row in lines)  # the longest label keeps a two-space gap


def test_the_real_run_errors_impose_false_true_and_end_on_a_tool_message():
    for entry in fixture_entries("survey"):
        raw = json.loads(fixture_bytes("survey", entry))
        m = map_fixture("survey", entry)
        if raw["error"] is None:
            assert not m.issues("outcome_imposed_by_runner")
            continue
        assert "InternalServerError" in raw["error"] and (raw["utility"], raw["security"]) == (False, True)
        assert raw["messages"][-1]["role"] == "tool"
        assert {j["origin"] for j in m.of_kind("judgement")} == {"harness_default"}
        assert m.issues("outcome_imposed_by_runner")
