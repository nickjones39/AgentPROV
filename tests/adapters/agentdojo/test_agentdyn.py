"""The ``agentdyn`` source profile, its identity table, rule catalogue and quirk hooks (docs/architecture D.4.4, D.4.5, D.5.4,
D.6.4, D.6.6, D.6.14; phase 10).

Real inputs: fifteen byte-identical logs of ``SaFo-Lab/AgentDyn@5353cf76`` (MIT; ``tests/fixtures/agentdyn/``, ``SOURCE.json``
per K.4.1), loaded programmatically and never printed (R-42): they hold prompt-injection payloads by design. The hook
mechanics that no real log exercises are tested with synthetic ``v1.k14`` logs written the way AgentDojo 0.1.35 writes them.
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
from agentdojo_support import log_bytes, map_bytes

from agentprov.adapters.agentdojo import census
from agentprov.adapters.agentdojo.dialect import classify
from agentprov.adapters.agentdojo.identity import resolve
from agentprov.adapters.agentdojo.profile import family_table
from agentprov.adapters.agentdojo.quirks import CensusFile, hooks
from agentprov.adapters.profiles import load_profile
from agentprov.adapters.runner import NotSelected, map_artefact_total, variant_part
from agentprov.adapters.types import Origin
from agentprov.aer.rules import load_catalogue
from agentprov.testing import golden

REPO = Path(__file__).resolve().parents[3]
FIXTURES = REPO / "tests" / "fixtures" / "agentdyn"
DIGESTS = Path(__file__).resolve().parent / "agentdyn_aer_digests.json"
REGEN = "AGENTPROV_REGEN_AGENTDYN_AER"
REPO_URL = "https://github.com/SaFo-Lab/AgentDyn"
COMMIT = "5353cf7615b135cace8d07c8f12dac53a16b6db3"
SENTINEL = "<Data omitted because a prompt injection was detected>"
CATALOGUE = REPO / "src" / "agentprov" / "adapters" / "agentdojo" / "rules" / "agentdyn.rules.toml"
TABLE = REPO / "src" / "agentprov" / "adapters" / "agentdojo" / "tables" / "agentdyn_pipeline_dirs.toml"

A_DEFAULT = "21a1c00db164a6d5d9d456be30eea3ed23bc11e6a89af0f56b8098d1f9ee3e36"


def _profile() -> Any:
    return load_profile("agentdyn")


def _entries() -> list[dict[str, Any]]:
    if not (FIXTURES / "SOURCE.json").is_file():
        pytest.skip("the agentdyn fixtures are not present")
    return list(json.loads((FIXTURES / "SOURCE.json").read_bytes()))


def _origin(entry: dict[str, Any]) -> Origin:
    return Origin.git(entry["repository"], entry["commit_or_revision"], entry["original_path"], entry["git_blob_sha1"])


def _fixture(fragment: str) -> dict[str, Any]:
    found = [e for e in _entries() if fragment in e["original_path"]]
    assert len(found) == 1, (fragment, len(found))
    return found[0]


def _doc(entry: dict[str, Any]) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads((FIXTURES / entry["sample_file"]).read_bytes())
    return loaded


def _map_entry(entry: dict[str, Any]) -> Any:
    raw = (FIXTURES / entry["sample_file"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == entry["sha256"] and golden.git_blob_sha1(raw) == entry["git_blob_sha1"]
    return map_bytes(raw, entry["original_path"], profile=_profile(), origin=_origin(entry))


def _fix(fragment: str) -> Any:
    return _map_entry(_fixture(fragment))


def _ok(m: Any) -> None:
    report = m.validate()
    assert report.ok and report.passed, [(f.code, f.pointer) for f in report.errors]


def _severities(m: Any, code: str) -> list[str]:
    return [str(s) for i, s in zip(m.outcome.issues, m.outcome.severities, strict=True) if i["code"] == code]


def _census(m: Any) -> dict[str, dict[str, int]]:
    return census.census_file(CensusFile(m.records, m.info.issues))


# ------------------------------------------------------------------------------------------------ synthetic v1.k14 logs
def _block(text: str | None) -> list[dict[str, str | None]]:
    return [{"type": "text", "content": text}]


def _call(name: str, args: dict[str, Any], cid: str | None) -> dict[str, Any]:
    return {"function": name, "args": args, "id": cid, "placeholder_args": None}


def a_log(pipeline_dir: str = "gpt-4o-2024-08-06", *, messages: list[dict[str, Any]] | None = None, **overrides: Any) -> dict[str, Any]:
    """A variant A log (AgentDojo 0.1.35 key set; content blocks) of the shopping suite: one call answered by id."""
    call = _call("get_shopping_account_user_information", {}, "call_1")
    doc: dict[str, Any] = {
        "suite_name": "shopping",
        "pipeline_name": pipeline_dir,
        "user_task_id": "user_task_1",
        "injection_task_id": "injection_task_2",
        "attack_type": "important_instructions",
        "injections": {"injection_emails_0": "payload"},
        "messages": messages if messages is not None else [
            {"role": "system", "content": _block("You are a helpful assistant.")},
            {"role": "user", "content": _block("Show my account.")},
            {"role": "assistant", "content": None, "tool_calls": [call]},
            {"role": "tool", "content": _block("{'Email': 'x'}"), "tool_call_id": "call_1", "tool_call": call, "error": None},
            {"role": "assistant", "content": _block("Done."), "tool_calls": []},
        ],
        "error": None,
        "benchmark_version": "v1.2.2",
        "evaluation_timestamp": "2026-01-22 07:51:35",
        "agentdojo_package_version": "0.1.35",
        "duration": 3.5,
        "utility": True,
        "security": False,
    }
    doc.update(overrides)
    return doc


def a_path(doc: dict[str, Any], pipeline_dir: str) -> str:
    attack = doc.get("attack_type") or "none"
    return f"runs/{pipeline_dir}/{doc['suite_name']}/{doc['user_task_id']}/{attack}/{doc.get('injection_task_id') or 'none'}.json"


def map_a(doc: dict[str, Any], pipeline_dir: str = "gpt-4o-2024-08-06") -> Any:
    return map_bytes(log_bytes(doc), a_path(doc, pipeline_dir), profile=_profile())


# ------------------------------------------------------------------------------------------------ profile and table
def test_profile_declares_the_d44_facts():
    profile = _profile()
    table = family_table(profile)
    data = profile.data
    assert profile.source_id == "agentdyn" and profile.parts == ("a", "b", "c", "history") and profile.family == "agentdojo"  # history: item 95
    pin = data["source"]["pins"][0]
    assert pin["commit"] == COMMIT and pin["expected_files"] == 47723 and pin["part"] == "a" and pin["primary"] is True
    assert data["licence"]["spdx"] == "MIT" and data["licence"]["basis"] == "MIT as declared; not legally settled"
    assert data["licence"]["policy"] == "include"
    dup = data["lineage"]["duplicates"][0]
    assert (dup["of"], dup["owner"], dup["relation"]) == ("drift", "drift", "byte_identical")
    imp = data["import"]
    assert dict(imp["variant_labels"]) == {"v1.k14": "a", "v0.k11": "b", "drift.k18.messages": "c", "drift.k18.conversations": "d"}
    assert imp["opt_in_parts"][0]["part"] == "history"
    assert any(e["code"] == "select.owned_elsewhere" and e["owner"] == "drift" for e in imp["exclude"])
    assert dict(table.benchmark["suites"]) == {"shopping": "agentdyn", "github": "agentdyn", "dailylife": "agentdyn", "travel": "agentdojo"}
    assert table.benchmark["version_label_semantics"] == "label_not_suite_version"
    assert table.retry_semantics == "agentdyn.last_assistant_content_none_max3"
    assert table.identity["model_from"] == "pipeline_dir" and table.identity["rule"] == "agentdyn.pipeline_dir_registry@1"
    assert {v.label for v in table.prompt_variants} == {"auto_complete_line", "auto_complete_line_spotlighting", "agentdojo_default"}


def test_every_source_specific_quirk_has_a_hook_and_a_census():
    table = family_table(_profile())
    registered = hooks()
    for quirk_id in ("agentdojo.progent_denial", "agentdojo.drift_integrated_user_error_key", "agentdojo.camel_orphan_tool_results"):
        assert quirk_id in registered and table.quirk(quirk_id) is not None
        assert set(registered[quirk_id].rules) <= set(table.quirk(quirk_id).rules)
        declared = {k for counts in table.quirk(quirk_id).observed.values() for k in counts}
        assert declared <= set(registered[quirk_id].census), quirk_id
    # D.4.4 counts of part a, as declared
    assert table.quirk("agentdojo.run_error_imposes_outcome").observed["a"] == {"files": 5}
    assert table.quirk("agentdojo.pi_detector_redaction").observed["a"] == {"redacted_tool_messages": 29317}
    assert table.quirk("agentdojo.drift_integrated_user_error_key").observed["a"] == {"user_messages": 434}
    assert table.quirk("agentdojo.camel_orphan_tool_results").observed["a"]["tool_messages"] == 2635
    assert table.quirk("agentdojo.camel_orphan_tool_results").observed["a"]["assistant_calls"] == 658
    assert table.quirk("agentdojo.provider_call_id_anomalies").observed["a"] == {"null_ids": 15306}
    assert table.quirk("agentdojo.incomplete_run").observed["a"]["files"] == 12


def test_the_identity_table_has_one_row_per_pipeline_directory():
    rows = family_table(_profile()).table_rows
    assert len(rows) == 76
    doc = tomllib.loads(TABLE.read_text(encoding="utf-8"))
    assert [r["name"] for r in doc["dir"]] == sorted(r["name"] for r in doc["dir"])
    bases = {"gpt-4o-2024-08-06", "gpt-4o-mini-2024-07-18", "gpt-5-mini-2025-08-07", "gpt-5.1-2025-11-13", "google_gemini-2.5-flash",
             "google_gemini-2.5-pro", "meta-llama_llama-3.3-70b-instruct", "qwen_qwen3-235b-a22b-2507"}
    defences = ("drift", "piguard_detector", "progent", "prompt_guard_2_detector", "repeat_user_prompt",
                "spotlighting_with_delimiting", "tool_filter", "transformers_pi_detector")
    expected = {b for b in bases} | {f"{b}-{d}" for b in bases for d in defences}
    expected |= {"gpt-4o-mini-2024-07-18-camel", "meta_secalign-70B", "meta_secalign-8B", "qwen_qwen-2.5-72b-instruct-progent"}
    assert set(rows) == expected
    for name, row in rows.items():
        suffix = next((d for d in (*defences, "camel") if name.endswith("-" + d)), "none")
        assert row["defence"] == suffix or name.startswith("meta_secalign"), name
        assert row["variant"] in ("A", "B", "C")
        assert (row["variant"] == "B") == (row["codebase"].startswith("progent")), name
        assert ("provider" in row) == (row["variant"] != "C"), name
        assert row.get("provider_evidence", "I") == "I"
    # the variants of the logs: eight Progent directories (B) and seven DRIFT-original directories (C)
    assert sorted(n for n, r in rows.items() if r["variant"] == "B") == sorted(f"{b}-progent" for b in bases)
    assert sorted(n for n, r in rows.items() if r["variant"] == "C") == sorted(f"{b}-drift" for b in bases if b != "gpt-4o-mini-2024-07-18")
    assert rows["meta_secalign-70B"]["pipeline_name"] == "local" and rows["meta_secalign-70B"]["model"] == "Meta-SecAlign-70B"
    assert rows["google_gemini-2.5-flash-piguard_detector"]["provider"] == "google"
    assert rows["google_gemini-2.5-pro-piguard_detector"]["provider"] == "openrouter"
    assert rows["gpt-4o-mini-2024-07-18-drift"]["variant"] == "A"


def test_identity_comes_from_the_pipeline_dir_table():
    """D.4.5: model, defence and provider are the row's, asserted under ``agentdyn.pipeline_dir_registry@1`` (class I); the
    logged ``pipeline_name`` is kept and compared, never used."""
    m = _fix("google_gemini-2.5-flash-piguard_detector")
    _ok(m)
    agent = m.get("agent")
    assert agent["model"] == {"requested": "gemini-2.5-flash", "provider": "google"} and agent["evf"] == {"/model": "I"}
    assert "agentdyn.pipeline_dir_registry@1#/model" in agent["rule"] and agent["src"] == [{"a": "a0", "o": "/path"}]
    assert "/model/provider" not in agent["unk"]
    defence = m.get("def0")
    assert defence["kind"] == "defense" and defence["name"] == "piguard_detector" and defence["rule"] == ["agentdyn.pipeline_dir_registry@1"]
    assert m.header["task"]["defense_id"] == "piguard_detector" and m.header["ext"]["agentdojo"]["pipeline_name"] == "gemini-2.5-flash-piguard_detector"
    assert not m.issues("agentdojo.pipeline_name_mismatch") and not m.issues("identity_unresolved")
    # the table row's pipeline_name is the expected value; another one is reported, never corrected
    doc = a_log("google_gemini-2.5-flash-piguard_detector", pipeline_name="gemini-2.5-flash")
    other = map_a(doc, "google_gemini-2.5-flash-piguard_detector")
    assert other.issues("agentdojo.pipeline_name_mismatch") and other.get("agent")["model"]["requested"] == "gemini-2.5-flash"
    # an undeclared directory resolves nothing (A-3): no model, no defence, an issue
    unknown = map_a(a_log("gpt-9-turbo"), "gpt-9-turbo")
    assert unknown.issues("identity_unresolved") and unknown.get("agent")["unk"]["/model"] == "not_recorded"
    assert "defense_id" not in unknown.header["task"] and unknown.header["unk"]["/task/defense_id"] == "not_recorded"
    ident = resolve(family_table(_profile()).identity, {"pipeline_dir": "meta_secalign-8B"}, "local", family_table(_profile()).table_rows)
    assert ident.model == "Meta-SecAlign-8B" and ident.provider == "local" and not ident.pipeline_name_mismatch


def test_the_benchmark_of_the_new_suites_is_agentdyn_and_its_version_a_label():
    m = _fix("gpt-4o-2024-08-06/shopping/user_task_1/important_instructions")
    bench = m.get("bench")
    assert m.header["task"]["benchmark"] == "agentdyn" and bench["name"] == "agentdyn" and bench["version"] == "v1.2.2"
    assert bench["ext"]["agentdojo"]["version_label_semantics"] == "label_not_suite_version"
    assert bench["code"] == {"dist": "agentdojo", "dist_version": "0.1.35"} and bench["unk"] == {"/code/commit": "not_recorded"}
    stray = _fix("gpt-5-mini-2025-08-07-progent/travel")
    assert stray.header["task"]["benchmark"] == "agentdojo" and stray.header["task"]["suite"] == "travel"
    camel = _fix("gpt-4o-mini-2024-07-18-camel/github/user_task_14")
    assert camel.get("bench")["unk"]["/version"] == "not_recorded" and "version" not in camel.get("bench")  # benchmark_version null


# ------------------------------------------------------------------------------------------------ fixtures
def test_fixtures_follow_k41_and_cover_the_variants():
    entries = _entries()
    variants = {}
    for entry in entries:
        assert entry["commit_or_revision"] == COMMIT and entry["licence_class"] == "permissive" and entry["synthetic"] is False
        assert entry["sample_file"] == entry["original_path"] and entry["original_path"].startswith("runs/")
        assert entry["repository"] == REPO_URL and "MIT" in entry["licence"]
        raw = (FIXTURES / entry["sample_file"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == entry["sha256"] and len(raw) == entry["size_bytes"]
        assert golden.git_blob_sha1(raw) == entry["git_blob_sha1"]
        variants[entry["original_path"]] = classify(json.loads(raw)).variant
    assert set(variants.values()) == {"v1.k14", "v1.k14.incomplete", "v0.k11", "drift.k18.messages"}
    on_disk = {p.relative_to(FIXTURES).as_posix() for p in FIXTURES.rglob("*") if p.is_file() and p.name != "SOURCE.json"}
    assert on_disk == {e["sample_file"] for e in entries}


def test_fixtures_map_validate_and_keep_their_aer_bytes():
    """D.6.10 items 1 and 5: every real A fixture maps, validates in release mode (locators resolved), carries the pinned
    profile, and its AER bytes are pinned (regenerate with ``AGENTPROV_REGEN_AGENTDYN_AER=1``)."""
    produced: dict[str, str] = {}
    profile = _profile()
    for entry in _entries():
        m = _map_entry(entry)
        _ok(m)
        assert not m.outcome.degenerate and m.header["profile"] == profile.header()
        if entry["schema_variant"] == "C":  # the DRIFT build (D-270; regeneration-batch item 22, RT-1 and RT-2)
            assert m.header["rules"]["drift"] == 1 and not m.issues("drift.quirk_hook_not_applied")
        else:
            assert m.header["artifacts"][0]["prov_primary"] == "native"
            assert m.header["rules"]["agentdyn"] == 2  # D-31
        assert not m.issues("agentdojo.undeclared_quirk"), (entry["original_path"], m.issues("agentdojo.undeclared_quirk"))
        produced[entry["original_path"]] = golden.sha256_hex(m.data)
    if os.environ.get(REGEN):
        DIGESTS.write_text(json.dumps(dict(sorted(produced.items())), indent=2) + "\n", encoding="utf-8")
    expected = json.loads(DIGESTS.read_text(encoding="utf-8"))
    assert sorted(k for k, v in produced.items() if expected.get(k) != v) == []
    assert set(expected) == set(produced)


def test_fixture_mapping_is_deterministic():
    entry = _fixture("gpt-4o-2024-08-06/shopping/user_task_1/important_instructions")
    assert _map_entry(entry).data == _map_entry(entry).data


def test_system_prompt_variants_are_labelled_by_digest():
    """D.6.6 system row: the auto-complete prompt of AgentDyn, its spotlighting form and Progent's 0.1.29 default are told
    apart by the SHA-256 of the text; logs without a system message (CaMeL, integrated DRIFT) have nothing to label."""
    labelled = {"gpt-4o-2024-08-06/shopping/user_task_1/important_instructions": "auto_complete_line",
                "gpt-4o-2024-08-06-spotlighting_with_delimiting/dailylife": "auto_complete_line_spotlighting",
                "meta-llama_llama-3.3-70b-instruct-progent/shopping/user_task_7": "agentdojo_default"}
    for fragment, label in labelled.items():
        m = _fix(fragment)
        assert m.get("m0")["ext"]["agentdojo"]["system_prompt_variant"] == label, fragment
        assert not m.issues("agentdojo.system_prompt_unrecognised")
    for fragment in ("gpt-4o-mini-2024-07-18-drift/shopping", "gpt-4o-mini-2024-07-18-camel/github/user_task_14"):
        m = _fix(fragment)
        assert not any(r.get("role") == "system" for r in m.of_kind("message")) and not m.issues("agentdojo.system_prompt_unrecognised")
    unknown = map_a(a_log())  # a text that is none of the pinned ones: reported, not labelled
    assert unknown.issues("agentdojo.system_prompt_unrecognised")[0]["ids"] == ["m0"]
    assert hashlib.sha256(b"You are a helpful assistant.").hexdigest() != A_DEFAULT


# ------------------------------------------------------------------------------------------------ variants and parts
def test_variant_labels_route_the_other_parts():
    """D.4.4 ``variant_labels`` / the rule ``agentdyn.variant_by_keyset``: each variant belongs to one part; the importer of
    part ``a`` records the others as ``select.dialect_planned`` and never maps them."""
    profile = _profile()
    assert [variant_part(profile, v) for v in ("v1.k14", "v1.k14.incomplete", "v0.k11", "drift.k18.messages", "drift.k18.conversations")] \
        == ["a", "a", "b", "c", "d"]
    for fragment, owner in (("progent/shopping/user_task_7", "b"), ("gpt-5.1-2025-11-13-drift", "c")):
        entry = _fixture(fragment)
        raw = (FIXTURES / entry["sample_file"]).read_bytes()
        with pytest.raises(NotSelected):
            map_artefact_total(raw, _origin(entry), profile_id="agentdyn", part="a")
        outcome, _unit = map_artefact_total(raw, _origin(entry), profile_id="agentdyn", part=owner)
        # B is mapped by the generic mapper where its part is asked for; C by the DRIFT build (item 22, RT-1)
        assert not outcome.degenerate
    a = _fixture("gpt-4o-2024-08-06/shopping/user_task_1/important_instructions")
    outcome, _unit = map_artefact_total((FIXTURES / a["sample_file"]).read_bytes(), _origin(a), profile_id="agentdyn", part="a")
    assert not outcome.degenerate


def test_variant_c_rekey_is_declared_not_cited():
    entry = load_catalogue("agentdyn").get("agentdyn.variant_c_rekey@1")
    assert entry is not None and entry.cls == "I" and entry.citable
    # the C file is recognised by its key set (messages + build_constraints) and nothing in a mapped A file cites the rule
    c = _doc(_fixture("gpt-5.1-2025-11-13-drift"))
    assert classify(c).variant == "drift.k18.messages" and "conversations" not in c
    assert not any("variant_c_rekey" in ref for r in _fix("gpt-4o-2024-08-06/shopping").records for ref in r.get("rule", ()))


# ------------------------------------------------------------------------------------------------ retry, run error, incomplete
def test_retry_is_inferred_from_the_last_assistant_message_anywhere():
    """``agentdyn.last_assistant_content_none_max3@1``: the last assistant message anywhere (not the final message) with null
    content shows a retry that ran out, as for upstream; cited under AgentDyn's own rule, through its I twin because the
    harness code is not verified (D.5.4, D-24; analysis B6): the index is inferred and the loss not proven."""
    doc = a_log()
    doc["messages"] = doc["messages"][:4]  # ends with the tool message; the last assistant message has content null
    m = map_a(doc)
    _ok(m)
    att = m.get("att0")
    assert att["index"] == 2 and att["ext"]["agentdojo"]["pre_state_not_initial"] is True and att["ev"] == "I"
    assert "agentdyn.last_assistant_content_none_max3_unverified@1#/index" in att["rule"]
    assert not any("null_final_implies_three_passes" in ref for ref in att["rule"])
    assert m.issues("retry_passes_inferred")[0]["rule"] == "agentdyn.last_assistant_content_none_max3_unverified@1"
    assert "retry_passes_inferred" in m.codes and _census(m)["agentdojo.silent_rerun_last_pass_only"] == {"null_final_logs": 1}
    plain = map_a(a_log())
    assert "index" not in plain.get("att0") and not plain.issues("retry_passes_inferred")


def test_json_decode_error_imposes_the_outcome():
    """``agentdyn.json_decode_error_imposed@1``: a run error makes both judgements the runner's, not the checker's; the origin
    is I through the rule's twin (the January runs predate the pinned code, D-24)."""
    m = _fix("meta-llama_llama-3.3-70b-instruct/github/injection_task_1")
    _ok(m)
    assert m.header["ext"]["agentdojo"]["error"].startswith("Skipping task")
    judgements = m.of_kind("judgement")
    assert [(j["name"], j["value"], j["origin"]) for j in judgements] == [("utility", False, "harness_default"), ("security", True, "harness_default")]
    assert all(j["rule"] == ["agentdyn.json_decode_error_imposed_unverified@1#/origin"] for j in judgements)
    assert all(j["evf"] == {"/origin": "I"} for j in judgements)
    assert m.issues("outcome_imposed_by_runner")[0]["rule"] == "agentdyn.json_decode_error_imposed_unverified@1"
    assert _census(m)["agentdojo.run_error_imposes_outcome"] == {"files": 1}
    assert "agentdojo.run_error_imposed_outcome" not in json.dumps(m.records)


def test_outcome_keys_may_be_absent_not_null():
    """verify/agentdyn.md §9 item 2: the 12 incomplete logs lack the keys; the variant is ``v1.k14.incomplete`` and no
    judgement is emitted (never a null placeholder)."""
    for fragment, has_duration in (("gpt-4o-mini-2024-07-18-camel/github/user_task_12", True),
                                   ("gpt-5-mini-2025-08-07-progent/travel/user_task_11", False)):
        m = _fix(fragment)
        _ok(m)
        assert m.header["dialect"]["variant"] == "v1.k14.incomplete" and not m.of_kind("judgement")
        assert m.issues("incomplete_run")[0]["ids"] == ["run"]
        assert ("dur_s" in m.get("run").get("t", {})) == has_duration
        counts = _census(m)["agentdojo.incomplete_run"]
        assert counts["files"] == 1 and counts["null_outcome_files"] == 0
    assert _census(_fix("gpt-4o-2024-08-06/shopping"))["agentdojo.incomplete_run"] == {"files": 0, "null_outcome_files": 0}


# ------------------------------------------------------------------------------------------------ detectors
@pytest.mark.parametrize(("fragment", "detector"), [
    ("google_gemini-2.5-flash-piguard_detector", "piguard_detector"),
    ("google_gemini-2.5-pro-prompt_guard_2_detector", "prompt_guard_2_detector"),
    ("google_gemini-2.5-flash-transformers_pi_detector", "transformers_pi_detector"),
])
def test_all_three_detectors_redact_through_the_sentinel_row(fragment: str, detector: str):
    """D.6.6 PI-detector row, generalised by the quirk's ``params.defences``: the v1.k14 sentinel is a one-block content list;
    the redacting defence is the pipeline's own detector."""
    entry = _fixture(fragment)
    m = _map_entry(entry)
    _ok(m)
    sentinel_messages = [i for i, msg in enumerate(_doc(entry)["messages"])
                         if msg["role"] == "tool" and msg["content"][0]["content"] == SENTINEL]
    assert sentinel_messages
    actor = next(a for a in m.of_kind("actor") if a.get("name") == detector)
    decisions = [d for d in m.of_kind("decision") if d["verdict"] == "redact"]
    assert len(decisions) == len(sentinel_messages) and all(d["actor"] == actor["id"] for d in decisions)
    assert all(d["unk"]["/original"] == "overwritten" and d["rule"][0] == "agentdojo.pi_detector_sentinel@1" for d in decisions)
    for i in sentinel_messages:
        message = m.get(f"m{i}")
        assert message["actor"] == actor["id"] and message["generated_by"].startswith("dc")
        assert message["parts"][0]["text"] == SENTINEL
    assert _census(m)["agentdojo.pi_detector_redaction"]["redacted_tool_messages"] == len(sentinel_messages)
    assert not m.issues("agentdojo.undeclared_quirk")


def test_a_sentinel_outside_a_detector_pipeline_is_an_ordinary_result():
    doc = a_log()
    doc["messages"][3]["content"] = _block(SENTINEL)
    m = map_a(doc)
    _ok(m)
    assert not [d for d in m.of_kind("decision")] and m.of_kind("tool_execution")
    assert m.issues("agentdojo.undeclared_quirk")[0]["detail"] == "agentdojo.pi_detector_redaction"


def test_null_call_ids_are_kept_null_and_linked_by_position():
    """The Google-client detector pipelines and the local SecAlign client log ``id: null`` (D.6.6.1 item 3)."""
    m = _fix("google_gemini-2.5-flash-piguard_detector")
    calls = [p for r in m.of_kind("message") if r["role"] == "assistant" for p in r["parts"] if p["t"] == "tool_call"]
    assert calls and all(p["provider_call_id"] is None for p in calls)
    te = m.of_kind("tool_execution")[0]
    assert te["call"] and te["evf"]["/call"] == "I" and "agentdojo.positional_match@1#/call" in te["rule"]
    assert _census(m)["agentdojo.provider_call_id_anomalies"]["null_ids"] == len(calls)


def test_local_model_raw_completions_are_counted_for_secalign():
    m = _fix("meta_secalign-8B")
    _ok(m)
    assert m.issues("agentdojo.local_parse_drop_possible")
    assert any(r.get("ext", {}).get("agentdojo", {}).get("local_model_tag_count") for r in m.of_kind("message"))
    counts = _census(m)["agentdojo.local_model_raw_completion"]
    assert counts["turns_more_tags_than_calls"] == len(m.issues("agentdojo.local_parse_drop_possible"))
    assert m.get("agent")["model"] == {"requested": "Meta-SecAlign-8B", "provider": "local"}
    assert not m.issues("agentdojo.pipeline_name_mismatch")  # the row records pipeline_name "local"


def test_generic_defences_of_the_fork_are_declared_quirks():
    for fragment, rule, defence in (
        ("spotlighting_with_delimiting/dailylife", "agentdojo.spotlighting_content@1", "spotlighting_with_delimiting"),
        ("google_gemini-2.5-flash-tool_filter", "agentdojo.tool_filter_aux_message@1", "tool_filter"),
        ("gpt-4o-2024-08-06-repeat_user_prompt", "agentdojo.repeat_user_prompt_copy@1", "repeat_user_prompt"),
    ):
        m = _fix(fragment)
        _ok(m)
        assert m.header["task"]["defense_id"] == defence
        assert any(rule in json.dumps(r.get("rule", ())) for r in m.records), fragment
        assert not m.issues("agentdojo.undeclared_quirk")


# ------------------------------------------------------------------------------------------------ progent denial
def test_progent_denial_is_a_decision():
    """``agentdyn.progent_denial_pattern@1`` (I): a denial is a ``deny`` decision of the progent defence and no
    ``tool_execution``; its reason is not logged. Real variant B log, mapped by the generic mapper through the profile."""
    entry = _fixture("meta-llama_llama-3.3-70b-instruct-progent/shopping/user_task_7")
    m = _map_entry(entry)
    _ok(m)
    doc = _doc(entry)
    denied = [i for i, msg in enumerate(doc["messages"]) if msg["role"] == "tool" and str(msg.get("error")).startswith("ValidationError: The tool '")
              and "is not allowed.." in msg["error"]]
    assert len(denied) == 1
    decisions = [d for d in m.of_kind("decision") if d["verdict"] == "deny"]
    assert len(decisions) == 1
    dc = decisions[0]
    progent = next(a for a in m.of_kind("actor") if a.get("name") == "progent")
    assert dc["actor"] == progent["id"] and dc["ev"] == "I" and dc["unk"]["/reason"] == "not_recorded"
    assert dc["rule"][0] == "agentdyn.progent_denial_pattern@1" and re.fullmatch(r"m\d+#\d+", dc["subject"])
    message = m.get(f"m{denied[0]}")
    assert message["generated_by"] == dc["id"] and message["actor"] == progent["id"]
    assert message["parts"][0]["error"] == doc["messages"][denied[0]]["error"]  # the denial text stays the tool result
    assert all(te["name"] != doc["messages"][denied[0]]["tool_call"]["function"] or te["args"] != doc["messages"][denied[0]]["tool_call"]["args"]
               for te in m.of_kind("tool_execution"))
    assert _census(m)["agentdojo.progent_denial"] == {"denials": 1}


def test_other_validation_errors_are_not_denials():
    call = _call("send_email", {"x": 1}, "call_1")
    doc = a_log("gpt-4o-2024-08-06-progent")
    doc["messages"][3] = {"role": "tool", "content": _block(""), "tool_call_id": "call_1", "tool_call": call,
                          "error": "ValidationError: Additional properties are not allowed ('type' was unexpected)"}
    doc["messages"][2]["tool_calls"] = [call]
    m = map_a(doc, "gpt-4o-2024-08-06-progent")
    _ok(m)
    assert not m.of_kind("decision") and m.of_kind("tool_execution")[0]["status"] == "invalid"
    doc["messages"][3]["error"] = "ValidationError: The tool 'send_email' is not allowed.. Please try other tools or arguments"
    denied = map_a(doc, "gpt-4o-2024-08-06-progent")
    _ok(denied)
    assert not denied.of_kind("tool_execution") and denied.get("dc0")["subject"] == "m2#1"
    # the selector is the profile's: the same text in an undefended pipeline is an ordinary error
    plain = map_a(doc, "gpt-4o-2024-08-06")
    assert plain.of_kind("tool_execution")[0]["status"] == "invalid" and not plain.of_kind("decision")


# ------------------------------------------------------------------------------------------------ integrated DRIFT
def test_drift_user_error_key_is_a_defence_message():
    """``agentdyn.drift_user_error_key@1``: a user message with an ``error`` key is the DRIFT validator's feedback; the
    decision refuses the preceding assistant output (here a message with an empty ``tool_calls``). Cited through its I twin:
    the DRIFTLLM code at the pin is not verified for the January runs (D-24)."""
    entry = _fixture("gpt-4o-mini-2024-07-18-drift/shopping/injection_task_4")
    m = _map_entry(entry)
    _ok(m)
    doc = _doc(entry)
    flagged = [i for i, msg in enumerate(doc["messages"]) if msg["role"] == "user" and "error" in msg]
    assert flagged
    drift = next(a for a in m.of_kind("actor") if a.get("name") == "drift")
    dcs = [d for d in m.of_kind("decision") if d["verdict"] == "deny"]
    assert len(dcs) == len(flagged)
    for i, dc in zip(flagged, dcs, strict=True):
        message = m.get(f"m{i}")
        assert message["role"] == "user" and message["actor"] == drift["id"] and message["generated_by"] == dc["id"]
        assert dc["actor"] == drift["id"] and dc["ev"] == "I" and dc["rule"][0] == "agentdyn.drift_user_error_key_unverified@1"
        assert dc["subject"] == f"m{i - 1}" and m.get(f"m{i - 1}")["role"] == "assistant"  # no call part to refuse
        assert dc["reason"] == doc["messages"][i]["error"] and dc["src"] == [{"a": "a0", "p": f"/messages/{i}/error"}]
        assert message["parts"][0]["text"] == doc["messages"][i]["content"][0]["content"]
    assert not m.issues("unknown_message_shape") and not m.issues("agentdojo.unknown_message_shape")
    assert m.info.accounting.to_json()["status"] in ("consistent", "unverifiable")
    assert _census(m)["agentdojo.drift_integrated_user_error_key"] == {"user_messages": len(flagged)}


def test_a_user_error_key_needs_a_decision_subject_and_a_string():
    log = a_log("gpt-4o-mini-2024-07-18-drift")
    log["messages"][1]["error"] = "refused"  # the first user message: no assistant output to refuse yet
    first = map_a(log, "gpt-4o-mini-2024-07-18-drift")
    _ok(first)
    assert first.issues("agentdojo.unknown_message_shape") and not first.of_kind("decision")
    log2 = a_log("gpt-4o-mini-2024-07-18-drift")
    log2["messages"].insert(4, {"role": "user", "content": _block("again"), "error": ["not", "a", "string"]})
    odd = map_a(log2, "gpt-4o-mini-2024-07-18-drift")
    assert odd.issues("agentdojo.unknown_message_shape") and not odd.of_kind("decision")
    log3 = a_log("gpt-4o-2024-08-06")
    log3["messages"].insert(4, {"role": "user", "content": _block("again"), "error": "refused"})
    undefended = map_a(log3, "gpt-4o-2024-08-06")  # not a drift pipeline: the key is just an unknown shape
    assert undefended.issues("agentdojo.unknown_message_shape") and not undefended.of_kind("decision")


def test_a_user_error_after_a_single_call_refuses_that_call_part():
    log = a_log("gpt-4o-mini-2024-07-18-drift")
    log["messages"][3] = {"role": "user", "content": _block("[CALL ERROR] refused"), "error": "[CALL ERROR] refused"}
    m = map_a(log, "gpt-4o-mini-2024-07-18-drift")
    _ok(m)
    assert m.get("dc0")["subject"] == "m2#1" and m.get("m3")["generated_by"] == "dc0"
    assert m.issues("missing_tool_result") or m.issues("unexecuted_tool_call")  # the refused call had no execution


# ------------------------------------------------------------------------------------------------ CaMeL
def test_camel_orphan_results_are_requested_by_the_defence():
    """``agentdyn.camel_orphan_tool_result@1`` (I): an interpreter execution no assistant call answers is requested by
    the camel defence actor; the issue is informational for CaMeL directories."""
    entry = _fixture("gpt-4o-mini-2024-07-18-camel/github/user_task_14")
    m = _map_entry(entry)
    _ok(m)
    doc = _doc(entry)
    camel = next(a for a in m.of_kind("actor") if a.get("name") == "camel")
    orphans = [te for te in m.of_kind("tool_execution") if "requested_by" in te]
    assert orphans and all(te["requested_by"] == camel["id"] and "call" not in te for te in orphans)
    assert all(te["evf"]["/requested_by"] == "I" and "agentdyn.camel_orphan_tool_result@1#/requested_by" in te["rule"] for te in orphans)
    assert all("/call" not in te["unk"] and not any(ref.endswith("#/call") for ref in te["rule"]) for te in orphans)
    result = next(r for r in m.of_kind("message") if r.get("generated_by") == orphans[0]["id"])
    assert result["parts"][0].get("responds_to") is None and result["unk"]["/parts/0/responds_to"] == "not_recorded"
    assert set(_severities(m, "orphan_tool_result")) == {"info"}
    assert len(m.issues("orphan_tool_result")) == len(orphans)
    tools = sum(1 for msg in doc["messages"] if msg["role"] == "tool")
    calls = sum(len(msg.get("tool_calls") or []) for msg in doc["messages"] if msg["role"] == "assistant")
    assert _census(m)["agentdojo.camel_orphan_tool_results"] == {
        "tool_messages": tools, "assistant_calls": calls, "orphan_executions": len(orphans)}
    assert m.get("bench")["unk"]["/version"] == "not_recorded"


def test_an_orphan_result_outside_a_camel_pipeline_stays_ambiguous():
    call = _call("get_shopping_account_user_information", {}, "call_1")
    doc = a_log()
    doc["messages"].insert(3, {"role": "tool", "content": _block("extra"), "tool_call_id": "call_9", "tool_call": call, "error": None})
    m = map_a(doc)
    orphan = next(te for te in m.of_kind("tool_execution") if "call" not in te)
    assert "requested_by" not in orphan and orphan["unk"]["/call"] == "ambiguous"
    assert set(_severities(m, "orphan_tool_result")) == {"warning"}


# ------------------------------------------------------------------------------------------------ catalogue
def test_the_catalogue_is_complete_and_classed_as_d54_says():
    expected = {"variant_by_keyset": "D", "pipeline_dir_registry": "I", "last_assistant_content_none_max3": "D",
                "json_decode_error_imposed": "D", "drift_user_error_key": "D", "camel_orphan_tool_result": "I",
                "progent_denial_pattern": "I", "variant_c_rekey": "I",
                # the I twins the profile cites (D.5.4, D-24): the harness code is not verified for the logs
                "last_assistant_content_none_max3_unverified": "I", "json_decode_error_imposed_unverified": "I",
                "drift_user_error_key_unverified": "I",
                # regeneration-batch items 26 and 27 (a): the artefact detector and the live suite benchmark
                "nondeterministic_tool_state": "D", "suite_benchmark": "D",
                # regeneration-batch item 2 (B3, D-376): CaMeL's feedback and planner input, with their twins
                "camel_interpreter_feedback": "D", "camel_planner_input_not_logged": "D",
                "camel_interpreter_feedback_unverified": "I", "camel_planner_input_not_logged_unverified": "I",
                # D-685 (b): the live capture's dropped tool calls (cited by the capture mapper directly, never through
                # the family's Citations, so it needs no _unverified twin)
                "malformed_tool_call_dropped": "D"}
    catalogue = load_catalogue("agentdyn")
    assert catalogue.version == 2 and {r.id for r in catalogue.rules.values()} == {f"agentdyn.{n}" for n in expected}
    for name, cls in expected.items():
        entry = catalogue.get(f"agentdyn.{name}@1")
        assert entry is not None and entry.cls == cls and entry.citable and not entry.verification, name
    doc = tomllib.loads(CATALOGUE.read_text(encoding="utf-8"))
    for rule in doc["rule"]:
        for node in rule.get("tests", []):
            file, _, test = node.partition("::")
            assert f"def {test}(" in (REPO / file).read_text(encoding="utf-8"), f"{rule['id']}: {node}"
        for code in rule.get("code", []):
            assert re.fullmatch(r"[0-9a-f]{40}", code["commit"]) and code["commit"] == COMMIT, rule["id"]


def test_the_catalogue_is_cited_where_the_profile_says():
    profile = _profile()
    cited = {ref.split("#", 1)[0] for q in profile.family_table()["quirk"] for ref in q["rules"]}
    assert {"agentdyn.json_decode_error_imposed@1", "agentdyn.progent_denial_pattern@1", "agentdyn.drift_user_error_key@1",
            "agentdyn.camel_orphan_tool_result@1", "agentdyn.last_assistant_content_none_max3@1"} <= cited
    catalogue = load_catalogue("agentdyn")
    assert all(catalogue.get(ref) is not None for ref in cited if ref.startswith("agentdyn."))
    assert profile.data["family"]["agentdojo"]["identity"]["rule"] in {f"{r.id}@{r.version}" for r in catalogue.rules.values()}


# ------------------------------------------------------------------------------------------------ determinism of copies
def test_synthetic_logs_do_not_alias_their_inputs():
    doc = a_log()
    before = copy.deepcopy(doc)
    map_a(doc)
    assert doc == before


# ------------------------------------------------------------------------------------------------ SEM fail-closed counts
def test_sem_unknown_tool_scan_counts_the_fail_closed_annotations(tmp_path: Path):
    import importlib.util

    spec = importlib.util.spec_from_file_location("sem_unknown_tools", REPO / "tools" / "agentdojo" / "sem_unknown_tools.py")
    assert spec is not None and spec.loader is not None
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    rule = ["agentdojo.unknown_tool@1", "agentdojo.suite_tool_table@1"]
    lines = [
        {"k": "sem", "id": "sem"},
        {"k": "ann", "id": "a0", "type": "role", "target": "te0", "rule": rule, "value": ["unknown"]},
        {"k": "ann", "id": "a1", "type": "role", "target": "m2#1", "rule": rule, "value": ["unknown"]},
        {"k": "ann", "id": "a2", "type": "integrity", "target": "m3#0", "rule": rule, "value": "unknown"},
        {"k": "ann", "id": "a3", "type": "integrity", "target": "m0#0", "rule": ["agentdojo.integrity_principal_content@1"],
         "value": "trusted"},
    ]
    shard = tmp_path / "sem" / "agentdojo.suites-1" / "00"
    shard.mkdir(parents=True)
    (shard / "ex_a.sem.jsonl").write_bytes(b"\n".join(json.dumps(line).encode() for line in lines) + b"\n")
    (shard / "ex_b.sem.jsonl").write_bytes(json.dumps(lines[4]).encode() + b"\n")
    report = tool.scan(tmp_path)
    assert report["sem_files"] == 2 and report["annotations"] == 5 and report["unknown_tool_annotations"] == 3
    assert report["files_with_unknown_tool_annotations"] == 1
    assert report["unknown_tool_executions"] == 1 and report["unknown_tool_call_parts"] == 1


# ------------------------------------------------------------------------------------------------ phase-10d R4
def test_an_identity_row_may_name_a_defence_and_no_model(monkeypatch):
    """Phase-10d R4 (llm-lock): a table row without a model (absent or "not_recorded") still gives its defence; the model
    is unresolved (unk /model not_recorded, identity_unresolved), never guessed (D-92)."""
    import dataclasses

    from agentprov.adapters.agentdojo import profile as profile_module
    from agentprov.adapters.agentdojo.identity import resolve_identity
    from agentprov.adapters.agentdojo.profile import parse_identity_table

    rows = parse_identity_table(b'[[dir]]\nname = "arm-a"\ndefence = "embedding"\n'
                                b'[[dir]]\nname = "arm-b"\nmodel = "not_recorded"\ndefence = "embedding"\n', "t")
    for name in ("arm-a", "arm-b"):
        ident = resolve_identity(name, name, {}, rows)
        assert ident.model is None and ident.defences == ("embedding",)

    profile = _profile()
    fam = family_table(profile)
    name, row = next((n, r) for n, r in sorted(fam.table_rows.items()) if r.get("defence", "none") != "none")
    stripped = {k: v for k, v in row.items() if k != "model"}
    patched = dataclasses.replace(fam, table_rows={**fam.table_rows, name: stripped})
    monkeypatch.setitem(profile_module._CHECKED, profile.sha256, patched)
    m = map_a(a_log(name), name)
    _ok(m)
    agent = m.get("agent")
    assert "model" not in agent and agent["unk"]["/model"] == "not_recorded"
    assert m.issues("identity_unresolved")
    assert m.header["task"]["defense_id"] == row["defence"]
    assert any(a.get("kind") == "defense" and a.get("name") == row["defence"] for a in m.of_kind("actor"))


# ------------------------------------------------------------------------------------------------ D-685 (b)
def test_a_dropped_call_is_recognised_only_under_the_quirk():
    """D-685 (b): the capture mapper treats a wire tool call as dropped by the harness exactly when AgentDyn's
    _openai_to_tool_call would fail (no function, or arguments that do not decode to a JSON object), and only under a
    profile that declares the quirk agentdojo.malformed_tool_call_dropped. No other shipped profile declares it, so the
    recognition is inert for every stock and AutoDojo session (their capture fixtures and golden PROV are pinned by
    test_capture_fixtures and the golden tests)."""
    from types import SimpleNamespace

    from agentprov.adapters.agentdojo.capture_mapper import DROPPED_CALL_QUIRK, DROPPED_CALL_RULE, _Live
    from agentprov.adapters.agentdojo.profile import family_table
    from agentprov.adapters.profiles import load_profile
    from agentprov.ingest.limits import IngestLimits
    from agentprov.ingest.loaders import strict_json_loads

    stub = SimpleNamespace(_json_text=lambda text: strict_json_loads(text.encode("utf-8"), IngestLimits()))

    def dropped(wire_call: object) -> bool:
        return _Live._dropped_by_harness(stub, wire_call)  # type: ignore[arg-type]

    assert not dropped({"function": {"name": "f", "arguments": "{}"}})
    assert not dropped({"function": {"name": "f", "arguments": "{\"a\": [1, {\"b\": null}]}"}})
    assert dropped({"function": {"name": "f", "arguments": "{\"a\": ["}})          # not JSON
    assert dropped({"function": {"name": "f", "arguments": "[1, 2]"}})            # JSON, not an object
    assert dropped({"function": {"name": "f", "arguments": "3"}})
    assert dropped({"function": {"name": "f", "arguments": {"a": 1}}})            # not a string
    assert dropped({"function": {"name": "f"}}) and dropped({"type": "custom"}) and dropped("x")
    profiles = sorted(p.removesuffix(".profile.toml") for p in (
        p.name for p in (REPO / "src" / "agentprov" / "adapters" / "agentdojo" / "profiles").glob("*.profile.toml")))
    declaring = {p for p in profiles if family_table(load_profile(p)).quirk(DROPPED_CALL_QUIRK) is not None}
    assert declaring <= {"agentdyn-live"}
    entry = load_catalogue("agentdyn").get(DROPPED_CALL_RULE)
    assert entry is not None and entry.cls == "D" and entry.citable
