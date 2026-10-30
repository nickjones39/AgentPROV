"""The ``mandate-agentdojo-eval`` profile and its quirk hook (docs/architecture D.4.4, D.6.4, D.6.6, D.6.15; phase 10).

Synthetic logs written the way AgentDojo 0.1.35 writes them exercise each rule; the eight real fixtures
(``tests/fixtures/mandate/``, byte-identical blobs of ``jwilliamsc/mandate-agentdojo-eval@fa62a977``, MIT, publisher unverified)
are loaded programmatically and never printed (R-42). The corpus digest of the profile is recomputed from the pinned tree
wherever its bare fetch cache is present.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any

import pytest
from agentdojo_support import path_of
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
)

from agentprov.adapters.agentdojo import census
from agentprov.adapters.agentdojo.identity import resolve
from agentprov.adapters.agentdojo.profile import check_against_schema, family_schema, family_table
from agentprov.adapters.agentdojo.quirks import CensusFile
from agentprov.adapters.profiles import load_profile
from agentprov.adapters.registry import get_source
from agentprov.adapters.runner import aer_bytes, map_artefact_total
from agentprov.adapters.types import Origin
from agentprov.aer.rules import RuleRegistry, load_catalogue
from agentprov.aer.validate import AerValidator
from agentprov.testing import golden

PROFILE = "mandate-agentdojo-eval"
DECLINE = "MANDATE_DECLINE: recipient US133000000121212121212 derives from neither the principal's task nor established counterparties (intent coherence)"
MONEY = {"recipient": "US133000000121212121212", "amount": 10.0}


def mandate_path(mode: str | None, doc: dict[str, Any]) -> str:
    return path_of(doc, "gpt-4o-2024-05-13" + (f"-mandate_{mode}" if mode else ""))


def mandate_log(mode: str | None, messages: list[dict[str, Any]], **overrides: Any) -> tuple[dict[str, Any], str]:
    name = "gpt-4o-2024-05-13" + (f"-mandate_{mode}" if mode else "")
    doc = log_with(messages, pipeline_name=name, **overrides)
    return doc, mandate_path(mode, doc)


def declined() -> list[dict[str, Any]]:
    c = call("send_money", MONEY, "call_1")
    return [turn(c), result(c, DECLINE, DECLINE), final()]


# ------------------------------------------------------------------------------------------------ the decline row
def test_a_decline_is_a_defence_decision_and_no_execution():
    """D.6.6 decline row: no tool_execution; dc0 by the mandate_<mode> defence actor, subject the declined tool_call part."""
    doc, path = mandate_log("intent", declined())
    m = map_synthetic(PROFILE, doc, path)
    ok(m)
    assert not m.of_kind("tool_execution")
    actor = next(a for a in m.of_kind("actor") if a.get("kind") == "defense")
    assert actor["name"] == "mandate_intent" and actor["rule"] == ["mandate.model_from_pipeline_name@1"]
    dc = m.get("dc0")
    assert dc["actor"] == actor["id"] and dc["verdict"] == "deny" and dc["subject"] == "m2#1" and dc["ev"] == "D"
    assert dc["reason"] == DECLINE and dc["evf"] == {"/reason": "O"} and dc["rule"][0] == "mandate.decline_prefix@1"
    message = m.get("m3")
    assert message["generated_by"] == "dc0" and message["actor"] == actor["id"] and message["evf"]["/generated_by"] == "D"
    assert message["parts"][0]["responds_to"] == "m2#1" and message["parts"][0]["error"] == DECLINE
    assert "mandate" in m.header["rules"] and m.header["ns"]["mandate"] == "https://w3id.org/agentprov/ns/mandate#"
    assert not m.issues("agentdojo.undeclared_quirk")


def test_the_decline_needs_the_executors_shape_and_a_mandate_pipeline():
    # content differs from the error: not the executor's message, left to the generic rows (a plain tool error)
    c = call("send_money", MONEY, "call_1")
    doc, path = mandate_log("intent", [turn(c), result(c, "something else", DECLINE), final()])
    m = map_synthetic(PROFILE, doc, path)
    ok(m)
    assert not m.of_kind("decision") and m.get("te0")["status"] == "error"
    # the same message in the undefended pipeline of the same model: the hook does not apply
    doc, path = mandate_log(None, declined())
    plain = map_synthetic(PROFILE, doc, path)
    ok(plain)
    assert not plain.of_kind("decision") and plain.get("te0")["status"] == "error"
    assert not [a for a in plain.of_kind("actor") if a.get("kind") == "defense"] and "mandate" not in plain.header["ns"]
    # an error that merely mentions the prefix is not a decline
    doc, path = mandate_log("intent", [turn(c), result(c, "x MANDATE_DECLINE: y", "x MANDATE_DECLINE: y"), final()])
    assert not map_synthetic(PROFILE, doc, path).of_kind("decision")


def test_the_baseline_converter_hazard_is_gone_no_declined_sink_is_executed():
    """verify §3.7 item 5: a declined send_money must not become an executed sink."""
    doc, path = mandate_log("intent", declined())
    m = map_synthetic(PROFILE, doc, path)
    assert [r["name"] for r in m.of_kind("tool_execution")] == []
    assert any(r["k"] == "decision" and r["verdict"] == "deny" for r in m.records)


# ------------------------------------------------------------------------------------------------ the allow inference
def test_a_gated_call_without_a_decline_is_inferred_allowed():
    c1, c2 = call("send_money", MONEY, "call_1"), call("get_balance", {}, "call_2")
    doc, path = mandate_log("envelope", [turn(c1, c2), result(c1, "sent"), result(c2, "100"), final()])
    m = map_synthetic(PROFILE, doc, path)
    ok(m)
    gated, free = m.get("te0"), m.get("te1")
    assert gated["name"] == "send_money" and gated["ext"]["mandate"] == {"gate": "allow"}
    assert gated["evf"]["/ext/mandate/gate"] == "I" and "mandate.allow_inferred@1#/ext/mandate/gate" in gated["rule"]
    assert "mandate" not in (free.get("ext") or {}) and free["name"] == "get_balance"


def test_the_gated_set_depends_on_the_mode():
    """envelope gates the money tools; scoped and intent add update_password and update_user_info (agentdojo_mandate_eval.py l. 191)."""
    c = call("update_password", {"password": "x"}, "call_1")
    messages = [turn(c), result(c, "Password updated."), final()]
    envelope = map_synthetic(PROFILE, *mandate_log("envelope", messages))
    intent = map_synthetic(PROFILE, *mandate_log("intent", messages))
    scoped = map_synthetic(PROFILE, *mandate_log("scoped", messages))
    baseline = map_synthetic(PROFILE, *mandate_log(None, messages))
    for m in (envelope, intent, scoped, baseline):
        ok(m)
    assert "mandate" not in (envelope.get("te0").get("ext") or {})
    assert intent.get("te0")["ext"]["mandate"] == {"gate": "allow"} and scoped.get("te0")["ext"]["mandate"] == {"gate": "allow"}
    assert "mandate" not in (baseline.get("te0").get("ext") or {})
    assert next(a for a in scoped.of_kind("actor") if a.get("kind") == "defense")["name"] == "mandate_scoped"


def test_an_executed_gated_call_that_errored_still_passed_the_gate():
    c = call("update_scheduled_transaction", {"id": 9, "amount": 1.0}, "call_1")
    doc, path = mandate_log("envelope", [turn(c), result(c, "", "ValueError: Transaction with ID 9 not found."), final()])
    m = map_synthetic(PROFILE, doc, path)
    ok(m)
    te = m.get("te0")
    assert te["status"] == "error" and te["ext"]["mandate"] == {"gate": "allow"}


# ------------------------------------------------------------------------------------------------ identity
def test_identity_is_read_from_the_pipeline_name():
    table = family_table(load_profile(PROFILE))
    for name, model, defences in (
        ("gpt-4o-2024-05-13", "gpt-4o-2024-05-13", ()),
        ("gpt-4o-2024-05-13-mandate_envelope", "gpt-4o-2024-05-13", ("mandate_envelope",)),
        ("gpt-4o-2024-05-13-mandate_scoped", "gpt-4o-2024-05-13", ("mandate_scoped",)),
        ("gpt-4o-2024-05-13-mandate_intent", "gpt-4o-2024-05-13", ("mandate_intent",)),
        ("gpt-4o-2024-05-13-mandate_other", "gpt-4o-2024-05-13-mandate_other", ()),  # not a mode of the harness: kept whole
    ):
        found = resolve(table.identity, {}, name)
        assert (found.model, found.defences, found.source) == (model, defences, "pipeline_name"), name
    assert table.identity["rule"] == "mandate.model_from_pipeline_name@1" and "collision_note" in table.identity
    doc, path = mandate_log("intent", declined())
    m = map_synthetic(PROFILE, doc, path)
    agent = m.get("agent")
    assert agent["model"] == {"requested": "gpt-4o-2024-05-13"} and agent["evf"] == {"/model": "I"}
    assert "mandate.model_from_pipeline_name@1#/model" in agent["rule"] and agent["src"] == [{"a": "a0", "p": "/pipeline_name"}]
    assert m.header["task"]["defense_id"] == "mandate_intent"


# ------------------------------------------------------------------------------------------------ the other quirks
def test_the_solvability_prepass_is_labelled_and_the_benign_constant_is_not_an_observation():
    c = call("update_password", {"password": "x"}, "call_1")
    doc, path = mandate_log("intent", [turn(c), result(c, "ok"), final()], user_task_id="injection_task_7", injection_task_id=None,
                            attack_type=None, injections={})
    m = map_synthetic(PROFILE, doc, path)
    ok(m)
    assert m.header["ext"]["agentdojo"]["task_kind"] == "injection_task_as_user_task"
    # the pre-pass passage was checked unchanged at 089ed468 and in the 0.1.35 wheel (D-86 addendum): D for these logs;
    # the benign constant cites the runner at c274885 only, which is not the 0.1.35 code of these logs: its twin (D-24)
    assert "agentdojo.injection_task_as_user_task@1#/ext/agentdojo/task_kind" in m.header["rule"]
    security = next(j for j in m.of_kind("judgement") if j["name"] == "security")
    assert security["origin"] == "harness_default" and security["evf"] == {"/origin": "I"}
    assert security["rule"] == ["agentdojo.benign_security_constant_unverified@1#/origin"]
    counts = census.census_file(CensusFile(m.records, m.info.issues))
    assert counts["agentdojo.injection_task_as_user_task_prepass"] == {"files": 1}
    assert counts["agentdojo.mandate_decline"] == {"declines": 0, "allowed_inferred": 1}


def test_the_default_system_prompt_is_labelled_by_its_wheel_digest():
    profile = load_profile(PROFILE)
    table = family_table(profile)
    (variant,) = table.prompt_variants
    assert variant.label == "agentdojo_default" and "364bea42" in str(variant.source)
    assert variant.sha256 == "a021a92b114c523250d0e52b18adc0aa7b41db7c7628b579b2b8db1df9361837"


# ------------------------------------------------------------------------------------------------ context artefacts
def test_the_harness_is_cited_as_a_supporting_artefact_when_the_import_supplies_it():
    doc, path = mandate_log("intent", [turn(call("send_money", MONEY, "call_1")), result(call("send_money", MONEY, "call_1"), DECLINE, DECLINE),
                                         turn(call("update_password", {"password": "x"}, "call_2")),
                                         result(call("update_password", {"password": "x"}, "call_2"), "ok"), final()])
    raw = json.dumps(doc, indent=4).encode("utf-8")
    src = SOURCES["mandate"]
    harness = b"# the harness bytes\n"
    origin = Origin.git(src["repo"], src["commit"], path, golden.git_blob_sha1(raw))
    context = [{"label": "agentdojo_mandate_eval.py", "sha256": hashlib.sha256(harness).hexdigest(), "size": len(harness),
                "origin": Origin.git(src["repo"], src["commit"], "agentdojo_mandate_eval.py", golden.git_blob_sha1(harness)).to_json()}]
    plain, _ = map_artefact_total(raw, origin, profile_id=PROFILE)
    assert len(plain.records[0]["artifacts"]) == 1
    outcome, _ = map_artefact_total(raw, origin, profile_id=PROFILE, context=context,
                                    context_bytes={"agentdojo_mandate_eval.py": harness})
    data, _info = aer_bytes(outcome)
    header = outcome.records[0]
    assert [(a["id"], a["role"]) for a in header["artifacts"]] == [("a0", "primary"), ("a1", "supporting")]
    decision = next(r for r in outcome.records if r.get("k") == "decision")
    execution = next(r for r in outcome.records if r.get("k") == "tool_execution")
    assert decision["ext"]["mandate"] == {"harness": "a1"} and execution["ext"]["mandate"] == {"gate": "allow", "harness": "a1"}

    class Store:
        blobs = {hashlib.sha256(raw).hexdigest(): raw, hashlib.sha256(harness).hexdigest(): harness}

        def has(self, sha: str) -> bool:
            return sha in self.blobs

        def size(self, sha: str) -> int:
            return len(self.blobs[sha])

        def read_bytes(self, sha: str) -> bytes:
            return self.blobs[sha]

    profile = load_profile(PROFILE)
    validator = AerValidator(store=Store(), catalogues=RuleRegistry.default(), mode="release",
                             profile_digests={(profile.id, profile.version): profile.sha256})
    for line in data.splitlines(keepends=True):
        validator.feed(line)
    report = validator.finish()
    assert report.ok, [(f.code, f.pointer) for f in report.errors]


# ------------------------------------------------------------------------------------------------ profile and registry
def test_profile_pins_licence_and_selection():
    profile = load_profile(PROFILE)
    data = profile.data
    (pin,) = data["source"]["pins"]
    assert pin["commit"] == "fa62a977584962f7b4b24a40772a83345fd920d4" and pin["primary"] is True and pin["part"] == "head"
    assert pin["expected_files"] == 401 and pin["expected_bytes"] == 3_137_054  # 396 logs + 5 root files
    assert data["source"]["corpus_digest"] == "a8f4a9d726073fb142e7580a18f65d8985095ac23658dd1b7c4cb178eac9bd5e"
    assert data["licence"]["spdx"] == "MIT" and data["licence"]["basis"] == "MIT as declared; publisher unverified"
    assert data["licence"]["holders"] == ("Mandate Labs (asserted; publisher unverified)",) and data["licence"]["policy"] == "include"
    imp = data["import"]
    assert tuple(imp["variants"]) == ("v1.k14",) and tuple(imp["include"]) == ("runs/**/*.json",)
    assert tuple(imp["context_artefacts"]) == ("agentdojo_mandate_eval.py", "README.md", "requirements.txt", "LICENSE")
    assert dict(imp["rules"]) == {ns: load_catalogue(ns).version for ns in imp["rules"]} == {"aer": 1, "agentdojo": 2, "mandate": 1}
    assert dict(data["family"]["agentdojo"]["benchmark"]["suites"]) == {"banking": "agentdojo"}
    verified = {v["commit"] for v in data["family"]["agentdojo"]["harness"]["verified_code"]}
    assert verified == {"a75aba7631d3ca5fb7ab938965c97ead2f9ff84b", "089ed468cf3ed0322acc66b0211f26d9d90dbf60",
                        "fa62a977584962f7b4b24a40772a83345fd920d4"}  # 0.1.35, the head pin, the evaluation script


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
    problems = census.compare(table, "head", {})
    assert [p for p in problems if "no census function" in p] == []
    declared = census.declared(table, "head")
    assert declared["agentdojo.mandate_decline"] == {"declines": 240, "allowed_inferred": 143}
    assert declared["agentdojo.injection_task_as_user_task_prepass"] == {"files": 27}


def test_the_catalogue_cites_the_source_commit_and_declares_three_rules():
    catalogue = load_catalogue("mandate")
    assert sorted(catalogue.rules) == ["mandate.allow_inferred@1", "mandate.decline_prefix@1", "mandate.model_from_pipeline_name@1"]
    assert catalogue.rules["mandate.decline_prefix@1"].cls == "D" and catalogue.rules["mandate.allow_inferred@1"].cls == "I"
    assert catalogue.rules["mandate.model_from_pipeline_name@1"].cls == "I"


def test_registry_entry_is_gated_and_lazy():
    source = get_source("mandate-agentdojo-eval")
    (part,) = source.capabilities
    assert part.part == "head" and part.profile == PROFILE and part.variants == ("v1.k14",) and part.corpus_id == "mandate-agentdojo-eval"
    assert part.import_status in ("partial", "supported") and part.target_import_status == "supported" and part.caveat
    assert source.licence.basis == "MIT as declared; publisher unverified" and source.licence.policy == "include"
    if part.import_status == "supported":  # D.3.2: only with the full pinned snapshot imported and recorded (HON-10)
        assert "docs/reports/mandate/import-cli-mandate.json" in part.caveat
    else:
        assert "full snapshot not yet imported" in part.caveat


# ------------------------------------------------------------------------------------------------ real fixtures
def test_fixtures_are_provenanced_and_licensed():
    entries = fixture_entries("mandate")
    on_disk = {p.relative_to(FIXTURES / "mandate").as_posix() for p in (FIXTURES / "mandate").rglob("*") if p.is_file()} - {"SOURCE.json"}
    assert on_disk == {e["sample_file"] for e in entries}
    for e in entries:
        raw = fixture_bytes("mandate", e)
        assert e["commit_or_revision"] == SOURCES["mandate"]["commit"] and e["licence_class"] == "permissive" and e["synthetic"] is False
        assert e["size_bytes"] == len(raw) and e["sample_file"] == e["original_path"] and e["original_path"].startswith("runs/")
    licence = (FIXTURES / "LICENSES" / "Mandate-MIT.txt").read_text(encoding="utf-8")
    assert licence.startswith("MIT License") and "Copyright (c) 2026 Mandate Labs" in licence


def test_real_fixtures_map_validate_and_keep_their_aer_bytes():
    """D.6.10 items 1 and 5: every real fixture maps, validates in release mode, carries the D.6.15 facts, and its AER bytes
    are pinned (regenerate with ``AGENTPROV_REGEN_AGENTDOJO_AER=1``)."""
    produced: dict[str, str] = {}
    profile = load_profile(PROFILE)
    declines = allowed = 0
    for entry in fixture_entries("mandate"):
        m = map_fixture("mandate", entry)
        ok(m)
        assert not m.outcome.degenerate and m.header["profile"] == profile.header() and m.header["dialect"]["variant"] == "v1.k14"
        assert m.header["artifacts"][0]["prov_primary"] == "native" and not m.issues("identity_unresolved")
        assert m.get("m0")["ext"]["agentdojo"]["system_prompt_variant"] == "agentdojo_default"
        assert m.get("bench")["version"] in ("v1.2.1",) and m.get("bench")["code"]["dist_version"] == "0.1.35"
        assert m.get("agent")["model"] == {"requested": "gpt-4o-2024-05-13"}
        counts = census.census_file(CensusFile(m.records, m.info.issues))["agentdojo.mandate_decline"]
        declines += counts["declines"]
        allowed += counts["allowed_inferred"]
        defended = "mandate_" in entry["original_path"].split("/")[1]
        assert bool(m.header["task"]["defense_id"]) is defended
        if not defended:
            assert counts == {"declines": 0, "allowed_inferred": 0}
        produced[entry["original_path"]] = golden.sha256_hex(m.data)
    assert declines >= 4 and allowed >= 4  # the chosen fixtures hold declines and passed gated calls of both modes
    path = DIGESTS / "mandate_aer_digests.json"
    if os.environ.get(REGEN):
        path.write_text(json.dumps(dict(sorted(produced.items())), indent=2) + "\n", encoding="utf-8")
    expected = json.loads(path.read_text(encoding="utf-8"))
    assert sorted(k for k, v in produced.items() if expected.get(k) != v) == [] and set(expected) == set(produced)


def test_real_decline_and_prepass_fixtures_carry_the_documented_shapes():
    seen = set()
    for entry in fixture_entries("mandate"):
        m = map_fixture("mandate", entry)
        path = entry["original_path"]
        decisions = m.of_kind("decision")
        for dc in decisions:
            tool = next(r for r in m.records if r.get("id") == dc["subject"].split("#")[0])
            assert tool["role"] == "assistant" and dc["subject"].count("#") == 1  # the tool_call part of the requesting turn
            assert dc["reason"].startswith("MANDATE_DECLINE:")
            seen.add("decline")
        if path.split("/banking/")[1].split("/")[0].startswith("injection_task_") and path.endswith("/none/none.json"):
            assert m.header["ext"]["agentdojo"]["task_kind"] == "injection_task_as_user_task"
            seen.add("prepass")
        if path.endswith("user_task_11/important_instructions/injection_task_2.json"):
            assert not m.of_kind("tool_execution") and not decisions  # a tool-free run
            seen.add("tool_free")
    assert seen == {"decline", "prepass", "tool_free"}


# ------------------------------------------------------------------------------------------------ pinned tree
@pytest.mark.full_corpus
def test_the_corpus_digest_is_reproduced_from_the_pinned_tree():
    """verify/mandate-agentdojo-eval.md §1: sha256 of the sorted "<path relative to runs/> <sha256>" lines, newline-terminated."""
    from agentprov.raw.fetch import Fetcher, Recipe, resolve_cache_dir

    profile = load_profile(PROFILE)
    source = profile.data["source"]
    pin = next(dict(p) for p in source["pins"] if p.get("primary") is True)
    recipe = Recipe.from_pin(pin, canonical_repo=source["canonical_repo"])
    fetcher = Fetcher(resolve_cache_dir(None))
    if not fetcher.plan(recipe).cached:
        pytest.skip("the pinned commit is not in the fetch cache (tools/seed_git_cache.py)")
    entries, _ = fetcher.git_tree(recipe)
    runs = [e for e in entries if e.is_blob and e.path.startswith("runs/")]
    lines = sorted(f"{b.entry.path.removeprefix('runs/')} {hashlib.sha256(b.data).hexdigest()}" for b in fetcher.iter_git_blobs(recipe, runs))
    assert len(lines) == 396
    digest = hashlib.sha256(("\n".join(lines) + "\n").encode("utf-8")).hexdigest()
    assert digest == source["corpus_digest"]
    assert hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest().startswith("3d1ea264")  # without the final newline
