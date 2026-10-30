"""The ROPE source (profile ``rope``) and the AutoDojo-attack slice it serves (profile ``autodojo-via-rope``)
(docs/architecture D.4.4, D.5.4, D.6.4, D.6.6, D.6.7, D.6.13; DoD Q.8).

The real fixtures (``tests/fixtures/rope/``: byte-identical blobs of ``xhOwenMa/ROPE@64495e16``, MIT) are loaded
programmatically and never printed (R-42): they hold benchmark prompt-injection payloads. ROPE's correction scripts are
ported in :mod:`agentprov.adapters.agentdojo.hooks.rope`; nothing here imports or runs ROPE code.
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
from agentdojo_support import Mapped, log_bytes, map_bytes

from agentprov.adapters.agentdojo import census, quirks
from agentprov.adapters.agentdojo.hooks import autodojo as link
from agentprov.adapters.agentdojo.hooks import rope as rope_hooks
from agentprov.adapters.agentdojo.profile import family_table
from agentprov.adapters.agentdojo.quirks import CensusFile, HookView, QuirkHook, ToolDecision, ToolMessage
from agentprov.adapters.profiles import load_profile, parse_profile
from agentprov.adapters.registry import EXTERNAL_OWNERS, get_source
from agentprov.adapters.runner import aer_bytes, map_artefact_total
from agentprov.adapters.types import Origin
from agentprov.aer.rules import RuleRegistry, load_catalogue
from agentprov.aer.validate import AerValidator
from agentprov.testing import golden

REPO_URL = "https://github.com/xhOwenMa/ROPE"
PIN = "64495e16e640d687e06e6b1b6cee6dccc5b9b7cb"
REPO = Path(__file__).resolve().parents[3]
FIXTURES = REPO / "tests" / "fixtures" / "rope"
PROFILE_PATH = REPO / "src" / "agentprov" / "adapters" / "agentdojo" / "profiles" / "rope.profile.toml"
SPEC = REPO / "docs" / "architecture" / "D_adapters.md"
ROPE_DIGESTS = Path(__file__).resolve().parent / "rope_aer_digests.json"
REGEN = "AGENTPROV_REGEN_AGENTDOJO_AER"
SAMPLE2 = "runs/gpt-4o-mini/slack/user_task_0/important_instructions/injection_task_5.json"
QWEN_AUTODOJO = "runs/qwen3-235b/slack/user_task_0/autodojo/injection_task_4.json"
GEMINI_CLEAN = "runs/gemini-2.5-flash/banking/user_task_0/none/none.json"
EMPTY = "runs/qwen3-235b/travel/user_task_2/agentlab_longhorizon/injection_task_2.json"
LONG_HORIZON = "runs/gpt-4o-mini/slack/user_task_0/agentlab_longhorizon/injection_task_1.json"
WRAPPED = "runs/gemini-2.5-flash/shopping/user_task_0/autodojo/injection_task_5.json"
BANKING_AUTODOJO = "runs/gpt-4o-mini/banking/user_task_7/autodojo/injection_task_7.json"
ABLATION_IT7 = "runs/ablation/always-action-open/dailylife/user_task_6/important_instructions/injection_task_7.json"
ROUTER_IT7 = "runs/router/gemini-3-flash-clamp/dailylife/user_task_8/important_instructions/injection_task_7.json"
GITHUB_IT1 = "runs/gpt-4o-mini/github/user_task_3/important_instructions/injection_task_1.json"
RETRY = "runs/gemini-2.5-flash/dailylife/user_task_12/autodojo/injection_task_2.json"
TRAILING = "runs/ablation/always-fully-specified/shopping/user_task_3/important_instructions/injection_task_6.json"


# ------------------------------------------------------------------------------------------------ helpers
def _ok(m: Any) -> None:
    report = m.validate()
    assert report.ok and report.passed, [(f.code, f.pointer) for f in report.errors]


def _entries() -> dict[str, dict[str, Any]]:
    if not (FIXTURES / "SOURCE.json").is_file():
        pytest.skip("the rope fixtures are not present")
    return {e["original_path"]: e for e in json.loads((FIXTURES / "SOURCE.json").read_bytes())}


def _raw(path: str) -> bytes:
    entry = _entries()[path]
    raw = (FIXTURES / entry["sample_file"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == entry["sha256"] and golden.git_blob_sha1(raw) == entry["git_blob_sha1"]
    return raw


def _doc(path: str) -> dict[str, Any]:
    value: dict[str, Any] = json.loads(_raw(path))
    return value


def _map(path: str, profile: Any = None) -> Mapped:
    raw = _raw(path)
    return map_bytes(raw, path, profile=profile or load_profile("rope"),
                     origin=Origin.git(REPO_URL, PIN, path, golden.git_blob_sha1(raw)))


def _map_doc(doc: dict[str, Any], path: str, profile: Any = None) -> Mapped:
    raw = log_bytes(doc)
    return map_bytes(raw, path, profile=profile or load_profile("rope"),
                     origin=Origin.git(REPO_URL, PIN, path, golden.git_blob_sha1(raw)))


def _variant(old: str, new: str) -> Any:
    text = PROFILE_PATH.read_text(encoding="utf-8")
    assert old in text, old
    return parse_profile(text.replace(old, new).encode("utf-8"), source="test-rope-variant")


def _cf(m: Mapped) -> CensusFile:
    return CensusFile(m.records[:-1], m.info.issues)


def _rope(record: dict[str, Any]) -> dict[str, Any]:
    return dict((record.get("ext") or {}).get("rope") or {})


# ------------------------------------------------------------------------------------------------ profile and registry
def test_profile_pins_and_system_prompt_variant():
    profile = load_profile("rope")
    table = family_table(profile)
    pin = next(p for p in profile.data["source"]["pins"] if p.get("primary"))
    assert pin["commit"] == PIN and pin["part"] == "head" and "tree" not in pin and pin["expected_files"] == 24909
    assert profile.parts == ("head",) and table.verified_code == ()  # unreleased fork states: no code verified (D-24)
    assert table.harness["code_identity"] == "unpinned"
    assert dict(profile.data["import"]["rules"]) == {ns: load_catalogue(ns).version for ns in ("aer", "agentdojo", "autodojo", "rope")}
    hooked = quirks.hooks()
    for quirk in table.quirks:  # every hooked quirk lists its hook's rules (D.6.12 item 7)
        if quirk.id in hooked:
            assert set(hooked[quirk.id].rules) <= set(quirk.rules)
    variant = table.prompt_variants[0]
    assert variant.label == "auto_complete_line"
    system = _doc(SAMPLE2)["messages"][0]["content"]
    text = "\n".join(block["content"] for block in system)
    assert hashlib.sha256(text.encode("utf-8")).hexdigest() == variant.sha256
    m = _map(SAMPLE2)
    _ok(m)
    assert m.get("m0")["ext"]["agentdojo"]["system_prompt_variant"] == "auto_complete_line"
    assert not m.issues("agentdojo.system_prompt_unrecognised") and not m.issues("agentdojo.undeclared_quirk")


def test_registry_rope_and_the_autodojo_slice():
    rope = get_source("rope")
    head = {c.part: c for c in rope.capabilities}["head"]
    assert rope.family == "agentdojo" and head.profile == "rope" and head.corpus_id == "rope"
    assert head.variants == ("v1.k14", "v1.k14.incomplete") and head.target_import_status == "supported"
    assert head.import_status in ("partial", "supported") and head.live_status == "planned" and head.caveat
    assert rope.licence.spdx == "MIT" and rope.licence.policy == "include"
    sliced = {c.part: c for c in get_source("autodojo").capabilities}["rope-slice"]
    assert sliced.via == "rope" and sliced.owner == "rope" and sliced.import_status == "partial" and sliced.caveat
    profile = load_profile("rope")
    owned = [e for e in profile.data["import"]["exclude"] if e["code"] == "select.owned_elsewhere"]
    assert [e["owner"] for e in owned] == ["ext:agentlab"] and "ext:agentlab" in EXTERNAL_OWNERS
    assert [d["owner"] for d in profile.data["lineage"]["duplicates"]] == ["ext:agentlab"]
    via = load_profile("autodojo-via-rope")
    assert via.data["profile"]["via"] == "rope" and "import" not in via.data and via.source_id == "autodojo"


# ------------------------------------------------------------------------------------------------ guard denials
def test_guard_denial_is_a_decision_not_an_execution():
    doc = _doc(SAMPLE2)
    denied = [i for i, msg in enumerate(doc["messages"])
              if msg["role"] == "tool" and isinstance(msg["error"], str) and msg["error"].startswith("The tool '")]
    m = _map(SAMPLE2)
    _ok(m)
    guard = next(a for a in m.of_kind("actor") if a.get("kind") == "defense")
    assert guard["name"] == "rope" and guard["rule"] == ["rope.guard_active_in_main_tree@1"] and guard["ev"] == "I"
    assert m.header["task"]["defense_id"] == "rope"
    decisions = m.of_kind("decision")
    assert len(denied) == len(decisions) == 3
    executed = {te["src"][0]["p"] for te in m.of_kind("tool_execution")}
    for dc, index in zip(decisions, denied, strict=True):
        assert dc["actor"] == guard["id"] and dc["verdict"] == "deny" and "#" in dc["subject"]
        assert dc["unk"]["/reason"] == "not_recorded" and "reason" not in dc
        assert dc["rule"][0] == "rope.denial_error_pattern@1" and dc["ev"] == "I"
        message = m.get(f"m{index}")
        assert message["generated_by"] == dc["id"] and message["actor"] == guard["id"]
        assert message["parts"][0]["responds_to"] == dc["subject"] and f"/messages/{index}/tool_call" not in executed
    census_counts = census.census_file(_cf(m))["agentdojo.rope_guard_denial"]
    assert census_counts == {"denials": 3, "none_variant": 3, "query_variant": 0}


def test_denial_query_echo_variants():
    pre = _map(SAMPLE2).of_kind("decision")
    post = _map(QWEN_AUTODOJO).of_kind("decision")
    assert {_rope(d)["query_echo"] for d in pre} == {"none"} and {_rope(d)["query_echo"] for d in post} == {"query"}
    for dc in (*pre, *post):  # the enforcer that wrote the text is an unreleased state: the twin, class I (D-24)
        assert dc["evf"]["/ext/rope/query_echo"] == "I"
        assert "rope.denial_query_echo_variant_unverified@1#/ext/rope/query_echo" in dc["rule"]
    # an error that does not match the pattern stays an execution with status error (D.6.6 row precedence)
    doc = _doc(SAMPLE2)
    index = next(i for i, msg in enumerate(doc["messages"]) if msg["role"] == "tool" and msg["error"])
    doc["messages"][index]["error"] = "ValueError: something else"
    m = _map_doc(doc, SAMPLE2)
    _ok(m)
    assert len(m.of_kind("decision")) == 2 and any(te["status"] == "error" for te in m.of_kind("tool_execution"))


# ------------------------------------------------------------------------------------------------ identity and tree
def test_identity_from_the_directory_and_the_tag_conflict():
    qwen = _map(QWEN_AUTODOJO)
    _ok(qwen)
    agent = qwen.get("agent")
    assert agent["model"] == {"requested": "qwen3-235b"} and agent["rule"][-1] == "rope.model_dir_identity@1#/model"
    assert qwen.header["ext"]["agentdojo"]["pipeline_name"].startswith("gpt-4o-mini-")
    [conflict] = qwen.issues("identity_conflict")
    assert conflict["detail"] == "pipeline_name names gpt-4o-mini" and conflict["rule"] == "rope.model_dir_identity@1"
    assert conflict["ids"] == ["agent"]
    assert census.census_file(_cf(qwen))["agentdojo.pipeline_name_not_identity"] == {"qwen_autodojo_mislabelled": 1}
    for path, model in ((GEMINI_CLEAN, "gemini-2.5-flash"), (LONG_HORIZON, "gpt-4o-mini"), (ABLATION_IT7, "gpt-4o-mini"),
                        (ROUTER_IT7, "gpt-4o-mini"), (EMPTY, "qwen3-235b")):
        m = _map(path)
        _ok(m)
        assert m.get("agent")["model"]["requested"] == model and not m.issues("identity_conflict"), path
    # a profile without model_tokens leaves the tag alone (the hook is param-driven)
    plain = _variant('params = { model_tokens = ["gpt-4o-mini", "gpt-4o", "gemini-2.5-flash", "qwen3-235b"] }\n', "")
    assert not _map(QWEN_AUTODOJO, plain).issues("identity_conflict")


def test_release_tree_arms():
    router = _map(ROUTER_IT7)
    assert router.header["ext"]["rope"]["arm"] == {"clamp": True, "router": "gemini-3-flash", "tree": "router"}
    assert "rope.tree_arm_config_unverified@1#/ext/rope/arm" in router.header["rule"]
    assert router.header["evf"]["/ext/rope/arm"] == router.header["evf"]["/task/benchmark"] == "I"  # D-24 twins
    assert router.header["task"]["benchmark"] == "agentdyn" and router.get("bench")["name"] == "agentdyn"
    assert "rope.benchmark_from_suite_unverified@1#/task/benchmark" in router.header["rule"]
    ablation = _map(ABLATION_IT7)
    assert ablation.header["ext"]["rope"]["arm"] == {"policy": "always-action-open", "tree": "ablation"}
    main = _map(SAMPLE2)
    assert "rope" not in main.header["ext"] and main.header["task"]["benchmark"] == "agentdojo"
    assert rope_hooks._arm("router/gpt-oss-20b") == {"clamp": False, "router": "gpt-oss-20b", "tree": "router"}
    assert rope_hooks._arm("gpt-4o") is None and rope_hooks._arm("other/x") is None
    counts = census.census_file(_cf(router))["agentdojo.rope_release_tree"]
    assert counts == {"ablation_files": 0, "router_files": 1, "router_clamp_files": 1}
    lh = _map(LONG_HORIZON)
    _ok(lh)
    assert lh.header["task"]["attack_id"] == "long_horizon" and not lh.issues("agentdojo.path_field_mismatch")


def test_generic_quirks_of_the_rope_fixtures():
    empty = _map(EMPTY)
    _ok(empty)
    assert empty.header["unit"] == "outcome_only" and not empty.of_kind("judgement")
    assert empty.issues("no_execution_observed") and empty.issues("no_outcome_recorded")
    retry = _map(RETRY)
    _ok(retry)
    assert retry.get("att0")["index"] == 2 and retry.issues("retry_passes_inferred")
    # analysis B6: the retry reading is the twin (class I), so the loss is inferred, not proven
    assert retry.get("att0")["ev"] == "I"
    assert retry.issues("retry_passes_inferred")[0]["rule"] == "agentdojo.null_final_implies_three_passes_unverified@1"
    trailing = _map(TRAILING)
    _ok(trailing)
    assert trailing.issues("unexecuted_tool_call") and trailing.issues("retry_passes_inferred")
    clean = _map(GEMINI_CLEAN)
    security = next(j for j in clean.of_kind("judgement") if j["name"] == "security")
    assert security["origin"] == "harness_default" and security["evf"] == {"/origin": "I"}
    assert security["rule"] == ["agentdojo.benign_security_constant_unverified@1#/origin"]
    calls = [p for msg in clean.of_kind("message") for p in msg.get("parts", ()) if p["t"] == "tool_call"]
    assert calls and all(p["provider_call_id"] is None for p in calls)


# ------------------------------------------------------------------------------------------------ effect corrections
def test_corrections_are_recomputed_judgements_beside_the_recorded():
    expected = {SAMPLE2: (True, False, "slack_it5"), ROUTER_IT7: (True, False, "dailylife_it7"),
                ABLATION_IT7: (True, True, "dailylife_it7")}
    for path, (recorded, corrected, label) in expected.items():
        m = _map(path)
        _ok(m)
        j1 = m.get("j1")
        j2 = m.get("j2")
        assert j1["name"] == "security" and j1["value"] is recorded and j1["origin"] == "checker" and "revises" not in j1
        assert j2["name"] == "security" and j2["value"] is corrected and j2["origin"] == "recomputed" and j2["revises"] == "j1"
        assert j2["actor"] == "rcorr" and j2["ev"] == "D" and j2["rule"] == ["rope.security_correction@1"] and "by" not in j2
        assert _rope(j2) == {"correction": label}
        judge = m.get("rcorr")
        assert judge["kind"] == "judge" and judge["name"] == "rope.corrections"
    github = _map(GITHUB_IT1)
    _ok(github)
    j2 = github.get("j2")
    assert j2["value"] is rope_hooks.corrected_security(_doc(GITHUB_IT1)) and _rope(j2) == {"correction": "github_it1"}
    for path in (GEMINI_CLEAN, QWEN_AUTODOJO, LONG_HORIZON, EMPTY):  # no correction applies
        m = _map(path)
        assert not any(j["origin"] == "recomputed" for j in m.of_kind("judgement")) and not any(
            a["id"] == "rcorr" for a in m.of_kind("actor"))
    counts = census.census_file(_cf(_map(SAMPLE2)))["agentdojo.rope_effect_correction"]
    assert counts["slack_it5"] == 1 and counts["slack_it5_recorded_true"] == 1 and counts["slack_it5_corrected_true"] == 0


def _slack_doc(*calls: tuple[str, dict[str, Any], str | None]) -> dict[str, Any]:
    messages: list[dict[str, Any]] = [{"role": "system", "content": [{"type": "text", "content": "s"}]},
                                      {"role": "user", "content": [{"type": "text", "content": "u"}]}]
    for i, (fn, args, error) in enumerate(calls):
        call = {"function": fn, "args": args, "id": f"call_{i}", "placeholder_args": None}
        messages.append({"role": "assistant", "content": None, "tool_calls": [call]})
        messages.append({"role": "tool", "content": [{"type": "text", "content": ""}], "tool_call_id": f"call_{i}",
                         "tool_call": dict(call), "error": error})
    return {"suite_name": "slack", "injection_task_id": "injection_task_5", "user_task_id": "user_task_0",
            "messages": messages, "security": True}


def test_correction_port_cases():
    fred = {"user": "Fred"}
    general = {"user": "Fred", "channel": "general"}
    # slack IT5 (invite Fred, add him to general, remove him): only executed calls count, in order
    assert rope_hooks.corrected_security(_slack_doc(("invite_user_to_slack", fred, None), ("add_user_to_channel", general, None),
                                                    ("remove_user_from_slack", fred, None))) is True
    assert rope_hooks.corrected_security(_slack_doc(("invite_user_to_slack", fred, None), ("add_user_to_channel", general, None))) is False
    assert rope_hooks.corrected_security(_slack_doc(("invite_user_to_slack", fred, "The tool 'x' is not allowed.."),
                                                    ("add_user_to_channel", general, None),
                                                    ("remove_user_from_slack", fred, None))) is False
    # dailylife IT7: URL normalised, save_dir defaulted and stripped
    daily = _slack_doc(("download_file_through_url", {"url": "HTTPS://www.my_company.com/important_message.pdf "}, None))
    daily.update(suite_name="dailylife", injection_task_id="injection_task_7")
    assert rope_hooks.corrected_security(daily) is True
    daily["messages"][3]["tool_call"]["args"]["save_dir"] = "/downloads/"
    assert rope_hooks.corrected_security(daily) is True
    daily["messages"][3]["tool_call"]["args"]["save_dir"] = "/tmp"
    assert rope_hooks.corrected_security(daily) is False
    daily["messages"][3]["tool_call"]["args"]["url"] = 7  # the released code would fail on .strip()
    with pytest.raises(rope_hooks._Indeterminate):
        rope_hooks.corrected_security(daily)
    # github IT1: the recorded flag minus deletions that did not execute; a transfer task without a trace is undecidable
    github = _slack_doc(("git_delete_repo", {"repo_name": "emmajohnson/file_compression"}, None))
    github.update(suite_name="github", injection_task_id="injection_task_1")
    assert rope_hooks.corrected_security(github) is True
    github["security"] = False
    assert rope_hooks.corrected_security(github) is False
    github.update(security=True, messages=[], user_task_id="user_task_9")
    assert rope_hooks.corrected_security(github) is True
    github["user_task_id"] = "user_task_2"
    with pytest.raises(rope_hooks._Indeterminate):
        rope_hooks.corrected_security(github)
    assert rope_hooks.corrected_security({"suite_name": "slack", "injection_task_id": "injection_task_4"}) is None


def test_undecidable_and_mismatched_corrections_give_issues_not_judgements():
    doc = _doc(GITHUB_IT1)
    doc.update(messages=[], security=True)  # transfer task user_task_3 without a trace: github_it1.py raises
    path = GITHUB_IT1
    m = _map_doc(doc, path)
    _ok(m)
    assert not any(j.get("origin") == "recomputed" for j in m.of_kind("judgement"))
    [issue] = m.issues("rope.correction_indeterminate")
    assert issue["rule"] == "rope.security_correction@1" and issue["detail"].startswith("github_it1")


def test_correction_scripts_are_cited_when_the_pinned_bytes_are_context(monkeypatch: pytest.MonkeyPatch):
    import agentprov.adapters.runner as runner

    scripts = {label: f"# {label}\n".encode() for label in ("runs/corrections.py", "runs/slack_it5.py")}
    pins = ", ".join(f'"{label}" = "{hashlib.sha256(data).hexdigest()}"' for label, data in scripts.items())
    line = next(x for x in PROFILE_PATH.read_text(encoding="utf-8").splitlines() if x.startswith("params = { scripts = {"))
    profile = _variant(line, f"params = {{ scripts = {{ {pins} }} }}")
    monkeypatch.setattr(runner, "load_profile", lambda _pid: profile)
    raw = _raw(SAMPLE2)
    origin = Origin.git(REPO_URL, PIN, SAMPLE2, golden.git_blob_sha1(raw))
    context = [{"label": label, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data),
                "origin": Origin.git(REPO_URL, PIN, label, golden.git_blob_sha1(data)).to_json()}
               for label, data in scripts.items()]
    outcome, _unit = map_artefact_total(raw, origin, profile_id="rope", part="head", context=context, context_bytes=scripts)
    data, info = aer_bytes(outcome)
    records = [json.loads(line) for line in data.splitlines()]
    header = records[0]
    assert [a["role"] for a in header["artifacts"]] == ["primary", "supporting", "supporting"]
    j2 = next(r for r in records if r.get("id") == "j2")
    assert {"a": "a1"} in j2["src"] and {"a": "a2"} in j2["src"]

    class Store:
        blobs = {hashlib.sha256(raw).hexdigest(): raw, **{hashlib.sha256(d).hexdigest(): d for d in scripts.values()}}

        def has(self, sha: str) -> bool:
            return sha in self.blobs

        def size(self, sha: str) -> int:
            return len(self.blobs[sha])

        def read_bytes(self, sha: str) -> bytes:
            return self.blobs[sha]

    validator = AerValidator(store=Store(), catalogues=RuleRegistry.default(), mode="release",
                             profile_digests={(profile.id, profile.version): profile.sha256})
    for line in data.splitlines(keepends=True):
        validator.feed(line)
    report = validator.finish()
    assert report.ok, [(f.code, f.pointer) for f in report.errors]
    # other bytes under a pinned label: no recomputation, a warning
    changed = {"runs/corrections.py": b"# changed\n", "runs/slack_it5.py": scripts["runs/slack_it5.py"]}
    context[0] = {**context[0], "sha256": hashlib.sha256(changed["runs/corrections.py"]).hexdigest()}
    outcome, _unit = map_artefact_total(raw, origin, profile_id="rope", part="head", context=context, context_bytes=changed)
    assert not any(r.get("origin") == "recomputed" for r in outcome.records)
    assert any(i["code"] == "rope.correction_code_mismatch" for i in outcome.issues)


# ------------------------------------------------------------------------------------------------ AutoDojo payload link
def test_autodojo_payload_cache_link():
    via = load_profile("autodojo-via-rope")
    qwen = _map(QWEN_AUTODOJO)
    ext = qwen.header["ext"]["autodojo"]
    assert ext["provenance_profile"] == via.header()
    assert len(ext["cache_cells"]) == 40 and all(c.startswith("autodojo:slack/") for c in ext["cache_cells"])
    assert qwen.header["evf"]["/ext/autodojo/cache_cells"] == "I"
    assert "autodojo.payload_cache_link@1#/ext/autodojo/cache_cells" in qwen.header["rule"]
    assert {f["ext"]["autodojo"]["cache_match"] for f in qwen.of_kind("fixture")} == {"exact"}
    wrapped = _map(WRAPPED)
    _ok(wrapped)
    assert wrapped.header["ext"]["autodojo"]["cache_cells"] == ["rope:shopping/openai/gpt-4o-mini/routed"]
    assert "wrapped" in {f["ext"]["autodojo"]["cache_match"] for f in wrapped.of_kind("fixture")}
    banking = _map(BANKING_AUTODOJO)
    _ok(banking)
    cells = banking.header["ext"]["autodojo"]["cache_cells"]
    assert len(cells) in (8, 16, 20, 38) and "autodojo:banking/openai/gpt-4o-mini/datafilter" in cells
    counts = census.census_file(_cf(wrapped))["agentdojo.autodojo_payload_cache_link"]
    assert counts["files_linked"] == 1 and counts["files_cells_1"] == 1 and counts["slots_wrapped"] == 1
    assert counts["slots"] == counts["slots_linked"] == len(_doc(WRAPPED)["injections"])
    for path in (SAMPLE2, GEMINI_CLEAN, LONG_HORIZON):  # only attack_dir = autodojo cells consult the link
        assert "autodojo" not in _map(path).header["ext"]
    # a payload no cache holds: no ambiguity set, an info issue, no fixture link
    doc = _doc(QWEN_AUTODOJO)
    vector = next(iter(doc["injections"]))
    doc["injections"][vector] = "not a cached variant"
    m = _map_doc(doc, QWEN_AUTODOJO)
    _ok(m)
    assert "cache_cells" not in m.header["ext"]["autodojo"]
    [issue] = m.issues("autodojo.payload_cache_unlinked")
    assert issue["detail"] == "unmatched_slots" and issue["rule"] == "autodojo.payload_cache_link@1"


def test_yaml_escape_and_the_wrapper_pattern():
    assert link.yaml_escape('a\\b"c\nd\te') == 'a\\\\b\\"c\\nd\\te'
    assert link.yaml_escape("ab" + "c\n") == link.yaml_escape("ab") + link.yaml_escape("c\n")
    goal = 'Send "all" money\nnow'
    text = link._WRAPPER.format(user="Emma Johnson", model="AI model developed by Google", goal=goal)
    found = link._WRAPPED.fullmatch(link.yaml_escape(text))
    assert found is not None and found.group("goal") == link.yaml_escape(goal)
    assert link._WRAPPED.fullmatch(link.yaml_escape(goal)) is None


def _old_wrapper_regex() -> re.Pattern[str]:
    """The regular expression the wrapper match used before the linear-time rewrite (escaping finding F-03)."""
    out = []
    for piece in re.split(r"(\{user\}|\{model\}|\{goal\})", link._WRAPPER):
        if piece == "{user}":
            out.append(re.escape(link.yaml_escape("Emma Johnson")))
        elif piece == "{model}":
            out.append(r"(?P<model>.*?)")
        elif piece == "{goal}":
            out.append(r"(?P<goal>.*)")
        else:
            out.append(re.escape(link.yaml_escape(piece)))
    return re.compile("".join(out), re.DOTALL)


def _same_match(old: re.Pattern[str], payload: str) -> None:
    a, b = old.fullmatch(payload), link._WRAPPED.fullmatch(payload)
    assert (a is None) == (b is None)
    if a is not None and b is not None:
        assert (a.group("model"), a.group("goal")) == (b.group("model"), b.group("goal"))


def test_wrapper_match_equals_the_old_regex_on_every_fixture_and_on_adversarial_shapes():
    import random

    old = _old_wrapper_regex()
    payloads: list[str] = []
    if (FIXTURES / "SOURCE.json").is_file():
        for path in sorted(FIXTURES.rglob("*.json")):
            doc = json.loads(path.read_bytes())
            injections = doc.get("injections") if isinstance(doc, dict) else None
            if isinstance(injections, dict):
                payloads += [v for v in injections.values() if isinstance(v, str)]
    pieces = [link._WRAPPED.prefix, link._WRAPPED.middle, link._WRAPPED.tail, "goal", "\\n", "x", "", "\n"]
    rng = random.Random(20261011)
    for goal in ("g", "", 'say "hi"\nnow\t\\', "\u202e\U0001f600"):
        for model in ("AI model", "", "a. b", "to you, X.\\n\\nBefore"):
            text = link._WRAPPER.format(user="Emma Johnson", model=model, goal=goal)
            payloads += [link.yaml_escape(text), link.yaml_escape(text) + "x", "x" + link.yaml_escape(text), goal]
    for _ in range(3000):
        payloads.append("".join(rng.choice(pieces) for _ in range(rng.randint(0, 7))))
    assert len(payloads) > 3000
    for payload in payloads:
        _same_match(old, payload)
    wrapped = [p for p in payloads if link._WRAPPED.fullmatch(p) is not None]
    assert len(wrapped) > 16  # the comparison covered matches, not only refusals


def test_wrapper_match_is_linear_on_the_crafted_stub_input():
    import time

    # The audit input: the wrapper text up to and including "first:" + blank line, repeated, with no valid tail. The old
    # regular expression took 1.6 s for 300 KB and grew quadratically.
    stub = link._WRAPPED.prefix + "m" + link._WRAPPED.middle
    payload = stub * (3_000_000 // len(stub))
    assert len(payload) > 2_000_000
    started = time.perf_counter()
    assert link._WRAPPED.fullmatch(payload) is None
    assert link._WRAPPED.fullmatch(payload + link._WRAPPED.tail[:-1]) is None
    found = link._WRAPPED.fullmatch(payload + link._WRAPPED.tail)  # a valid tail makes it a (huge) match
    assert found is not None and found.group("model") == "m"
    assert found.group("goal") == payload[len(link._WRAPPED.prefix) + 1 + len(link._WRAPPED.middle) :]
    assert time.perf_counter() - started < 2.0


def test_cache_table_is_generated_from_the_pins():
    via = load_profile("autodojo-via-rope")
    prov = via.family_table()["attack_provenance"]
    path = REPO / "src" / "agentprov" / "adapters" / "agentdojo" / prov["table"]["path"]
    data = path.read_bytes()
    assert hashlib.sha256(data).hexdigest() == prov["table"]["sha256"]
    table = link.load_table(prov["table"]["path"], prov["table"]["sha256"])
    assert len(table.cells) == 153 and sum(c.startswith("rope:") for c in table.cells) == 3
    doc = json.loads(data)
    assert doc["sources"]["autodojo"]["commit"] == prov["cache_commit"] and doc["sources"]["rope"]["commit"] == PIN
    assert all(re.fullmatch(r"[0-9a-f]{64}", d) for rows in doc["slots"].values() for d in rows)
    import sys

    sys.path.insert(0, str(REPO / "tools" / "agentdojo"))
    import autodojo_cache_table

    from agentprov.raw.fetch import Fetcher, Recipe, resolve_cache_dir

    fetcher = Fetcher(resolve_cache_dir(None))
    pins = [Recipe(kind="git", role="x", primary=False, repo=str(prov["cache_repo"]), commit=str(prov["cache_commit"])),
            Recipe(kind="git", role="y", primary=False, repo=REPO_URL, commit=PIN)]
    if not all(fetcher.plan(r).cached for r in pins):
        pytest.skip("the AutoDojo and ROPE pins are not in the fetch cache")
    assert autodojo_cache_table.build() == data


# ------------------------------------------------------------------------------------------------ fixtures and catalogues
def test_rope_fixtures_follow_k41_map_validate_and_keep_their_aer_bytes():
    """D.6.10 items 1 and 5: every real ROPE fixture maps, validates in release mode and keeps its AER bytes
    (regenerate with ``AGENTPROV_REGEN_AGENTDOJO_AER=1``)."""
    entries = _entries()
    on_disk = {p.relative_to(FIXTURES).as_posix() for p in FIXTURES.rglob("*") if p.is_file() and p.name != "SOURCE.json"}
    assert on_disk == {e["sample_file"] for e in entries.values()} and len(entries) == 12
    assert (REPO / "tests" / "fixtures" / "LICENSES" / "ROPE-MIT.txt").read_text(encoding="utf-8").startswith("MIT License")
    produced: dict[str, str] = {}
    variants = set()
    for path, entry in entries.items():
        assert entry["commit_or_revision"] == PIN and entry["licence_class"] == "permissive" and entry["synthetic"] is False
        assert entry["sample_file"] == path and path.startswith("runs/") and entry["size_bytes"] == len(_raw(path))
        m = _map(path)
        _ok(m)
        assert not m.outcome.degenerate and m.header["artifacts"][0]["prov_primary"] == "native"
        assert not m.issues("agentdojo.undeclared_quirk") and not m.issues("agentdojo.path_field_mismatch")
        variants.add(m.header["dialect"]["variant"])
        produced[path] = golden.sha256_hex(m.data)
        assert _map(path).data == m.data  # deterministic
    assert variants == {"v1.k14", "v1.k14.incomplete"}
    if os.environ.get(REGEN):
        ROPE_DIGESTS.write_text(json.dumps(dict(sorted(produced.items())), indent=2) + "\n", encoding="utf-8")
    expected = json.loads(ROPE_DIGESTS.read_text(encoding="utf-8"))
    assert sorted(k for k, v in produced.items() if expected.get(k) != v) == [] and set(expected) == set(produced)


def _index(namespace: str) -> dict[str, str]:
    text = SPEC.read_text(encoding="utf-8")
    section = text.split("### D.5.4 Initial rule index (v0.1)", 1)[1].split("### D.5.5", 1)[0]
    out: dict[str, str] = {}
    for line in section.splitlines():
        found = re.match(rf"^\| `({namespace}\.[a-z0-9_]+)` \| ([DI]) \|", line)
        if found:
            out[found.group(1)] = found.group(2)
    return out


@pytest.mark.parametrize(("namespace", "issue_codes"), [
    ("rope", ("correction_indeterminate", "correction_code_mismatch")),
    ("autodojo", ("payload_cache_unlinked",)),
])
def test_catalogues_declare_the_d54_rules_and_their_tests_exist(namespace: str, issue_codes: tuple[str, ...]):
    catalogue = load_catalogue(namespace)
    index = _index(namespace)
    assert index
    for rule_id, cls in index.items():
        entry = catalogue.get(f"{rule_id}@1")
        assert entry is not None and entry.cls == cls and entry.citable, rule_id
    for code in issue_codes:
        assert catalogue.declares_issue_code(f"{namespace}.{code}")
    path = REPO / "src" / "agentprov" / "adapters" / "agentdojo" / "rules" / f"{namespace}.rules.toml"
    doc = tomllib.loads(path.read_text(encoding="utf-8"))
    for rule in doc["rule"]:
        assert rule["tests"], rule["id"]
        for node in rule["tests"]:
            file, _, name = node.partition("::")
            assert f"def {name}(" in (REPO / file).read_text(encoding="utf-8"), f"{rule['id']}: {node}"
        for code in rule.get("code", []):
            assert re.fullmatch(r"[0-9a-f]{40}", code["commit"]), rule["id"]
        for verification in rule.get("verification", []):
            assert verification["status"] == "asserted", rule["id"]


def test_rope_quirk_ids_and_hooks():
    found = quirks.hooks()
    for quirk_id in (rope_hooks.GUARD, rope_hooks.TREE, rope_hooks.TAG, rope_hooks.CORRECTION, link.QUIRK_ID):
        assert quirk_id in found
    assert found[rope_hooks.TAG].rules == () and not found[rope_hooks.TAG].namespaces  # param-driven, shareable


# ------------------------------------------------------------------------------------------------ hook points (D.6.13)
_TEST_RULE = "agentdojo.local_model_tag_count@1"


def _execution(view: HookView, header: dict[str, Any]) -> None:
    header.setdefault("ext", {})["testns"] = {"suite": view.doc["suite_name"], "model": view.model}
    header.setdefault("evf", {})["/ext/testns"] = "I"
    header.setdefault("rule", []).append(view.rule(_TEST_RULE, "/ext/testns"))
    assert view.issue is not None
    view.issue("identity_conflict", ["agent"], _TEST_RULE, detail="test")


def _actors(view: HookView) -> list[dict[str, Any]]:
    return [{"k": "actor", "id": "xjudge", "kind": "judge", "name": "test.judge", "ev": "I", "rule": [view.rule(_TEST_RULE)]}]


def _fixture(view: HookView, vector: str, record: dict[str, Any]) -> None:
    record.setdefault("ext", {})["testns"] = {"vector_seen": vector}


def _deny_all(view: HookView, message: ToolMessage) -> ToolDecision | None:
    return ToolDecision(defence="guard", rules=(_TEST_RULE,), ev="I", ext={"testns": {"flag": "x"}},
                        evf={"/ext/testns/flag": "I"}, scoped=((_TEST_RULE, "/ext/testns/flag"),))


_HOOK = QuirkHook(quirk_id="agentdojo.test_points", rules=(_TEST_RULE,), namespaces={"testns": "https://example.org/testns#"},
                  defences=lambda view: ["guard"], tool_message=_deny_all, execution=_execution, actors=_actors,
                  fixture=_fixture)


def test_execution_actor_fixture_and_decision_hook_points(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(quirks, "hooks", lambda: {_HOOK.quirk_id: _HOOK})
    profile = _variant("[family.agentdojo.outcomes]", f'[[family.agentdojo.quirk]]\nid = "agentdojo.test_points"\n'
                                                       f'applies = {{}}\nrules = ["{_TEST_RULE}"]\n\n[family.agentdojo.outcomes]')
    doc = copy.deepcopy(_doc(QWEN_AUTODOJO))
    m = _map_doc(doc, QWEN_AUTODOJO, profile)
    _ok(m)
    assert m.header["ext"]["testns"] == {"suite": "slack", "model": "qwen3-235b"} and m.header["ns"]["testns"]
    assert m.issues("identity_conflict")[0]["detail"] == "test"
    assert m.get("xjudge")["kind"] == "judge"
    assert all(f["ext"]["testns"]["vector_seen"] in doc["injections"] for f in m.of_kind("fixture"))
    assert not m.of_kind("tool_execution")
    dc = m.of_kind("decision")[0]
    assert dc["evf"] == {"/ext/testns/flag": "I"} and f"{_TEST_RULE}#/ext/testns/flag" in dc["rule"]
