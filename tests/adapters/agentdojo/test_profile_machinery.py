"""The shared profile machinery of the AgentDojo family (docs/architecture D.4.2-D.4.5, D.6.12; phase 10 wave 1).

Layout templates with an optional component, the identity modes and identity tables, selectors over layout facets, the
benchmark of each suite and the meaning of the version label, the retry semantics, the closed generic ``[import]`` and
``[lineage]`` tables, the quirk-hook extension point (decision rows, recomputed judgements, context artefacts) and the
census of ``observed`` counts. Every log here is synthetic (``agentdojo_support``).
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from typing import Any

import pytest
from agentdojo_support import PROFILE_PATH, base_log, log_bytes, map_log, profile_with

from agentprov.adapters.agentdojo import census, quirks
from agentprov.adapters.agentdojo.identity import resolve, resolve_identity
from agentprov.adapters.agentdojo.layout import parse_layout
from agentprov.adapters.agentdojo.profile import family_table, parse_identity_table
from agentprov.adapters.agentdojo.quirks import CensusFile, HookView, QuirkHook, ToolDecision, ToolMessage
from agentprov.adapters.profiles import parse_profile
from agentprov.adapters.runner import aer_bytes, map_artefact_total
from agentprov.adapters.types import Origin
from agentprov.aer.rules import RuleRegistry
from agentprov.aer.validate import AerValidator
from agentprov.errors import ProfileError

ROPE_LAYOUT = "runs/{tree?}/{model_dir}/{suite}/{task_dir}/{attack_dir}/{file}.json"


def _ok(m: Any) -> None:
    report = m.validate()
    assert report.ok and report.passed, [(f.code, f.pointer) for f in report.errors]


# ------------------------------------------------------------------------------------------------ layout
def test_layout_with_an_optional_component():
    layout = parse_layout(ROPE_LAYOUT)
    assert layout.names == {"tree", "model_dir", "suite", "task_dir", "attack_dir", "file"}
    plain = layout.match("runs/gpt-4o/banking/user_task_0/none/none.json")
    assert plain == {"tree": None, "model_dir": "gpt-4o", "suite": "banking", "task_dir": "user_task_0",
                     "attack_dir": "none", "file": "none"}
    tree = layout.match("runs/router/r1-clamp/gpt-4o/banking/user_task_0/autodojo/injection_task_1.json")
    assert tree is not None and tree["tree"] == "router/r1-clamp" and tree["model_dir"] == "gpt-4o"
    assert layout.match("agentlab/res/x.json") is None and layout.match("runs/a/b/c/d.json") is None
    fixed = parse_layout("runs/{pipeline_dir}/{suite}/{task_dir}/{attack_dir}/{file}.json")
    assert fixed.match("clone/runs/p/s/t/a/f.json") == {"pipeline_dir": "p", "suite": "s", "task_dir": "t",
                                                        "attack_dir": "a", "file": "f"}  # right-aligned (phase 6)
    assert fixed.match("runs/p/s/t/a/f.txt") is None
    for bad in ("a/{x?}/{y?}/z", "a/{x}/{x}", "a//b", "a/{x?}.json", "a/{X}"):
        with pytest.raises(ProfileError):
            parse_layout(bad)


# ------------------------------------------------------------------------------------------------ identity
def test_identity_modes():
    rope = resolve({"model_from": "model_dir", "pipeline_name_policy": "config_tag_never_model"},
                   {"model_dir": "gpt-4o-mini"}, "iter4-final")
    assert rope.model == "gpt-4o-mini" and not rope.pipeline_name_mismatch and rope.source == "path"
    mandate = {"model_from": "pipeline_name_minus_suffix", "defence_suffix_regex": "-(mandate_(?:envelope|scoped|intent))$",
               "rule": "agentdojo.pipeline_dir_is_model_identity@1", "pipeline_name_policy": "verbatim_unreliable_when_differs"}
    gated = resolve(mandate, {}, "gpt-4o-2024-05-13-mandate_envelope")
    assert gated.model == "gpt-4o-2024-05-13" and gated.defences == ("mandate_envelope",) and gated.source == "pipeline_name"
    plain = resolve(mandate, {}, "gpt-4o-2024-05-13")
    assert plain.model == "gpt-4o-2024-05-13" and plain.defences == ()
    survey = {"model_from": "results_dir_slug", "slug_to_model": {"runs_qwen3_14b": "qwen3:14b"},
              "pipeline_name_policy": "constant_not_model"}
    assert resolve(survey, {"results_dir": "runs_qwen3_14b"}, "openai-compatible").model == "qwen3:14b"
    unknown = resolve(survey, {"results_dir": "runs_other"}, "openai-compatible")
    assert unknown.model is None and unknown.pipeline_dir == "runs_other"


def test_identity_table_rows_and_parser():
    rows = {"gpt-4o-2024-08-06-progent": {"name": "gpt-4o-2024-08-06-progent", "model": "gpt-4o-2024-08-06",
                                          "defence": "progent", "provider": "openai"},
            "meta_secalign-70B": {"name": "meta_secalign-70B", "model": "Meta-SecAlign-70B", "defence": "none",
                                  "pipeline_name": "local"}}
    table = {"model_from": "pipeline_dir", "rule": "agentdojo.pipeline_dir_is_model_identity@1"}
    row = resolve_identity("gpt-4o-2024-08-06-progent", "gpt-4o-2024-08-06-progent", table, rows)
    assert row.model == "gpt-4o-2024-08-06" and row.defences == ("progent",) and row.provider == "openai"
    local = resolve_identity("meta_secalign-70B", "local", table, rows)
    assert local.defences == () and not local.pipeline_name_mismatch
    assert resolve_identity("meta_secalign-70B", "other", table, rows).pipeline_name_mismatch
    assert resolve_identity("not-in-table", "x", table, rows).model is None  # D.4.5: never guessed
    data = b'[[dir]]\nname = "a"\nmodel = "m"\ndefence = "none"\n'
    assert parse_identity_table(data, "tables/t.toml")["a"]["model"] == "m"
    for bad in (b'[[dir]]\nname = "a"\nmodel = "m"\n[[dir]]\nname = "a"\nmodel = "n"\n',  # duplicate row
                b'[[dir]]\nname = "a"\nmodel = "m"\ncolour = "x"\n',  # unknown key
                b'[[dir]]\nname = "a"\n',  # neither a model nor a defence (a defence alone is allowed: R4)
                b'[[dir]]\nname = "a"\nmodel = "not_recorded"\n',  # the same
                b'[[dir]]\nname = "a"\nmodel = "m"\nprovider_evidence = "O"\n',  # may only weaken
                b'x = 1\n'):
        with pytest.raises(ProfileError):
            parse_identity_table(bad, "tables/t.toml")


def _rope_like(**extra: str) -> Any:
    """The shipped profile turned into a ROPE-like one: model_dir identity, an optional tree, an attack alias."""
    replace = {
        'layout = "runs/{pipeline_dir}/{suite}/{task_dir}/{attack_dir}/{file}.json"': f'layout = "{ROPE_LAYOUT}"',
        'model_from = "pipeline_dir"\npipeline_name_policy = "verbatim_unreliable_when_differs"':
            'model_from = "model_dir"\npipeline_name_policy = "config_tag_never_model"\n'
            'attack_dir_alias = { agentlab_longhorizon = "long_horizon" }',
        'applies = { pipeline_dir = ["claude-3-opus-20240229"] }': 'applies = { model_dir = ["claude-3-opus-20240229"] }',
        'applies = { pipeline_dir = ["*-transformers_pi_detector"] }': 'applies = { tree = ["ablation/*"] }',
    }
    replace.update(extra)
    text = PROFILE_PATH.read_text(encoding="utf-8")
    for old, new in replace.items():
        assert old in text, old
        text = text.replace(old, new)
    text = text.replace('applies = { pipeline_dir = ', 'applies = { model_dir = ')
    return parse_profile(text.encode(), source="test-rope-like")


def test_mapper_reads_the_model_dir_tree_and_attack_alias():
    profile = _rope_like()
    doc = base_log(pipeline_name="iter4-final", attack_type="long_horizon")
    path = "runs/ablation/p1/gpt-4o-mini/banking/user_task_1/agentlab_longhorizon/injection_task_2.json"
    m = map_log(doc, profile=profile, path=path)
    _ok(m)
    assert m.get("agent")["model"]["requested"] == "gpt-4o-mini"
    assert not m.issues("agentdojo.path_field_mismatch") and not m.issues("agentdojo.pipeline_name_mismatch")
    flat = map_log(doc, profile=profile, path="runs/gpt-4o-mini/banking/user_task_1/agentlab_longhorizon/injection_task_2.json")
    assert flat.get("agent")["model"]["requested"] == "gpt-4o-mini"


def test_selector_facets_must_be_layout_components():
    with pytest.raises(ProfileError):
        family_table(profile_with({'applies = { pipeline_dir = ["claude-3-opus-20240229"] }':
                                   'applies = { colour = ["red"] }'}))
    # agentdojo.single_pass (DRIFT) is accepted since the DRIFT build is dispatched (regeneration-batch item 22, RT-5)
    family_table(profile_with({'retry_semantics = "agentdojo.final_content_none_max3"': 'retry_semantics = "agentdojo.single_pass"'}))


# ------------------------------------------------------------------------------------------------ benchmark and retry
def test_version_label_semantics_per_suite():
    """D.6.12 item 5: the label stays verbatim on the bench actor; where it is not the suite version the profile's reading
    is stated (``agentdojo.version_label_semantics@1``, I), per suite for ``..._for_agentdojo_suites_only``."""
    profile = profile_with({
        'suites = { workspace = "agentdojo", travel = "agentdojo", banking = "agentdojo", slack = "agentdojo" }':
            'suites = { workspace = "agentdojo", travel = "agentdojo", banking = "agentdojo", slack = "agentdojo", github = "agentdyn" }',
        'version_label_semantics = "suite_version"': 'version_label_semantics = "suite_version_for_agentdojo_suites_only"',
    })
    v1 = {"benchmark_version": "v1.2.2", "evaluation_timestamp": "2025-07-01 10:00:00", "agentdojo_package_version": "0.1.35"}
    banking = map_log(base_log(**v1), profile=profile)
    _ok(banking)
    assert "ext" not in banking.get("bench") and banking.header["task"]["benchmark"] == "agentdojo"
    github = map_log(base_log(suite_name="github", **v1), profile=profile)
    _ok(github)
    bench = github.get("bench")
    assert github.header["task"]["benchmark"] == "agentdyn" and bench["name"] == "agentdyn" and bench["version"] == "v1.2.2"
    assert bench["ext"]["agentdojo"]["version_label_semantics"] == "label_not_suite_version"
    assert "agentdojo.version_label_semantics@1#/ext/agentdojo/version_label_semantics" in bench["rule"]
    assert github.issues("agentdojo.path_field_mismatch") == []


def test_retry_semantics_last_assistant_anywhere():
    doc = base_log()
    doc["messages"] = doc["messages"][:4]  # ends with the tool message; the last assistant message has content null
    plain = map_log(doc)
    assert "index" not in plain.get("att0")
    profile = profile_with({'retry_semantics = "agentdojo.final_content_none_max3"':
                            'retry_semantics = "agentdyn.last_assistant_content_none_max3"'})
    agentdyn = map_log(doc, profile=profile)
    _ok(agentdyn)
    assert agentdyn.get("att0")["index"] == 2 and agentdyn.issues("retry_passes_inferred")


# ------------------------------------------------------------------------------------------------ generic tables
def _profile_text(old: str, new: str) -> bytes:
    text = PROFILE_PATH.read_text(encoding="utf-8")
    assert old in text, old
    return text.replace(old, new).encode()


def test_generic_import_and_lineage_tables_are_closed():
    exclude = '  { glob = "**/._*", code = "select.not_execution_artefact" },\n'
    good = '  { glob = "vendor/**", code = "select.owned_elsewhere", owner = "ext:agentlab", note = "vendored" },\n'
    parse_profile(_profile_text(exclude, exclude + good), source="t")
    for bad in ('  { glob = "vendor/**", code = "select.owned_elsewhere" },\n',  # owner missing
                '  { glob = "vendor/**", code = "select.not_execution_artefact", owner = "agentdojo" },\n',  # owner misplaced
                '  { glob = "vendor/**", code = "select.whatever" },\n',  # not a select code
                '  { glob = "vendor/**", code = "select.owned_elsewhere", owner = "Not An Id" },\n'):
        with pytest.raises(ProfileError):
            parse_profile(_profile_text(exclude, exclude + bad), source="t")
    with pytest.raises(ProfileError):
        parse_profile(_profile_text('layout_depth = 5', 'layout_depth = 5\ncolour = "red"'), source="t")
    with pytest.raises(ProfileError):
        parse_profile(_profile_text('relation = "mirror", owner = "agentdojo" },\n  { of = "adprov-v1"',
                                    'relation = "copy", owner = "agentdojo" },\n  { of = "adprov-v1"'), source="t")
    with pytest.raises(ProfileError):
        parse_profile(_profile_text('content_dedup = "never"', 'content_dedup = "never"\nowner_of = []'), source="t")
    with pytest.raises(ProfileError):  # an undeclared variant labelled with one of the profile's own parts (D-480)
        parse_profile(_profile_text('variants = ["v0.k11", "v1.k14", "v1.k14.incomplete"]',
                                    'variants = ["v0.k11", "v1.k14", "v1.k14.incomplete"]\n'
                                    'variant_labels = { "drift.k18.messages" = "head" }'), source="t")
    with pytest.raises(ProfileError):  # a via profile has no [import]
        parse_profile(_profile_text('family = "agentdojo"\nparts', 'family = "agentdojo"\nvia = "rope"\nparts'), source="t")


# ------------------------------------------------------------------------------------------------ quirk hooks
TEST_RULE = "agentdojo.local_model_tag_count@1"  # any declared class-I rule serves the mechanics under test
_QUIRK = """[[family.agentdojo.quirk]]
id = "agentdojo.test_guard_denial"
applies = { attack_dir = ["important_instructions"] }
rules = ["agentdojo.local_model_tag_count@1"]
observed = { head = { denials = 1 } }

[family.agentdojo.outcomes]"""


def _deny(view: HookView, message: ToolMessage) -> ToolDecision | None:
    error = message.error
    if isinstance(error, str) and error.startswith("DENIED"):
        return ToolDecision(defence="guard", rules=(TEST_RULE,), ev="I", reason="error",
                            ext={"testns": {"pattern": view.params.get("pattern", "DENIED")}})
    return None


def _recompute(view: HookView, recorded: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    security = next(j for j in recorded if j["name"] == "security")
    return [{"k": "judgement", "actor": "bench", "subject": "run", "name": "security", "value": not security["value"],
             "origin": "recomputed", "revises": security["id"], "ev": "I", "rule": [view.rule(TEST_RULE)],
             "src": [{"a": "a0", "p": "/security"}]}]


def _cite(view: HookView, message: ToolMessage, record: dict[str, Any]) -> None:
    if view.cite_context is not None and "notes/cells.txt" in view.context:
        assert view.open_context is not None and view.open_context("notes/cells.txt") == b"cells\n"
        record.setdefault("ext", {})["testns"] = {"cells": view.cite_context("notes/cells.txt")}


HOOK = QuirkHook(quirk_id="agentdojo.test_guard_denial", rules=(TEST_RULE,), namespaces={"testns": "https://example.org/testns#"},
                 defences=lambda view: ["guard"], tool_message=_deny, tool_execution=_cite, judgements=_recompute,
                 census={"denials": lambda cf: sum(1 for r in cf.of_kind("decision") if r.get("verdict") == "deny")})


@pytest.fixture
def hooked(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setattr(quirks, "hooks", lambda: {HOOK.quirk_id: HOOK})
    return profile_with({"[family.agentdojo.outcomes]": _QUIRK})


def _denied_log() -> dict[str, Any]:
    doc = base_log()
    doc["messages"][3]["error"] = "DENIED: the guard refused send_money"
    return doc


def test_a_hook_turns_a_tool_message_into_a_decision(hooked: Any):
    m = map_log(_denied_log(), profile=hooked)
    _ok(m)
    assert not m.of_kind("tool_execution") and m.header["ns"]["testns"] == "https://example.org/testns#"
    guard = next(a for a in m.of_kind("actor") if a.get("name") == "guard")
    dc = m.get("dc0")
    assert dc["actor"] == guard["id"] and dc["verdict"] == "deny" and dc["subject"] == "m2#1"
    assert dc["reason"] == "DENIED: the guard refused send_money" and dc["ext"]["testns"] == {"pattern": "DENIED"}
    message = m.get("m3")
    assert message["generated_by"] == "dc0" and message["actor"] == guard["id"]
    assert message["parts"][0]["responds_to"] == "m2#1"
    assert m.info.accounting.to_json()["status"] in ("consistent", "unverifiable")
    recomputed = m.of_kind("judgement")[-1]
    assert recomputed["origin"] == "recomputed" and recomputed["revises"] == "j1" and recomputed["id"] == "j2"
    plain = map_log(base_log(attack_type="direct"), profile=hooked)  # the selector does not match: nothing applies
    assert plain.of_kind("tool_execution") and not any(a.get("name") == "guard" for a in plain.of_kind("actor"))


def test_a_hook_census_counts_its_key(hooked: Any):
    m = map_log(_denied_log(), profile=hooked)
    counts = census.census_file(CensusFile(m.records, m.info.issues))
    assert counts["agentdojo.test_guard_denial"] == {"denials": 1}
    table = family_table(hooked)
    mine = "agentdojo.test_guard_denial"
    assert [p for p in census.compare(table, "head", {mine: {"denials": 1}}) if p.startswith(mine)] == []
    assert [p for p in census.compare(table, "head", {mine: {"denials": 2}}) if p.startswith(mine)]


def test_a_quirk_must_list_its_hooks_rules(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(quirks, "hooks", lambda: {HOOK.quirk_id: HOOK})
    with pytest.raises(ProfileError):
        family_table(profile_with({"[family.agentdojo.outcomes]": _QUIRK.replace(f'rules = ["{TEST_RULE}"]', "rules = []")}))


def test_hook_modules_are_discovered_by_convention():
    found = quirks.hooks()
    assert all(isinstance(h, QuirkHook) and h.quirk_id.startswith("agentdojo.") for h in found.values())


def test_context_artefacts_reach_the_hooks_and_can_be_cited(hooked: Any, monkeypatch: pytest.MonkeyPatch):
    import agentprov.adapters.runner as runner

    monkeypatch.setattr(runner, "load_profile", lambda _pid: hooked)
    raw = log_bytes(base_log())
    path = "runs/gpt-4o-2024-05-13/banking/user_task_1/important_instructions/injection_task_2.json"
    origin = Origin.git("https://github.com/ethz-spylab/agentdojo", "c274885610efaaafec38b6d3eb07152ba7ff3f94", path, "0" * 40)
    cells = b"cells\n"
    context = [{"label": "notes/cells.txt", "sha256": hashlib.sha256(cells).hexdigest(), "size": len(cells),
                "origin": Origin.git("https://github.com/ethz-spylab/agentdojo", "c274885610efaaafec38b6d3eb07152ba7ff3f94",
                                     "notes/cells.txt", "1" * 40).to_json()}]
    plain, _unit = map_artefact_total(raw, origin, profile_id="x", context=(), context_bytes=None)
    assert not plain.degenerate
    hook_free = [r for r in plain.records if r.get("k") == "execution"][0]
    assert len(hook_free["artifacts"]) == 1
    outcome, _unit = map_artefact_total(raw, origin, profile_id="x", context=context,
                                        context_bytes={"notes/cells.txt": cells})
    data, _info = aer_bytes(outcome)
    header = outcome.records[0]
    assert [a["role"] for a in header["artifacts"]] == ["primary", "supporting"] and header["artifacts"][1]["id"] == "a1"
    te = next(r for r in outcome.records if r.get("k") == "tool_execution")
    assert te["ext"]["testns"] == {"cells": "a1"}

    class Store:
        blobs = {hashlib.sha256(raw).hexdigest(): raw, hashlib.sha256(cells).hexdigest(): cells}

        def has(self, sha: str) -> bool:
            return sha in self.blobs

        def size(self, sha: str) -> int:
            return len(self.blobs[sha])

        def read_bytes(self, sha: str) -> bytes:
            return self.blobs[sha]

    validator = AerValidator(store=Store(), catalogues=RuleRegistry.default(), mode="release",
                             profile_digests={(hooked.id, hooked.version): hooked.sha256})
    for line in data.splitlines(keepends=True):
        validator.feed(line)
    report = validator.finish()
    assert report.ok, [(f.code, f.pointer) for f in report.errors]


def _feedback(view: HookView, message: Any) -> ToolDecision | None:
    if "error" in message.message:
        return ToolDecision(defence="guard", rules=(TEST_RULE,), ev="I", reason="error")
    return None


USER_HOOK = QuirkHook(quirk_id="agentdojo.test_guard_denial", rules=(TEST_RULE,), defences=lambda view: ["guard"],
                      user_message=_feedback)


def test_a_hook_turns_a_later_user_message_into_a_decision(monkeypatch: pytest.MonkeyPatch):
    """AgentDyn's DRIFT-integrated validator feedback (D.6.6 row "user with an error key"): role kept, generated by the
    defence's decision whose subject is the rejected call."""
    monkeypatch.setattr(quirks, "hooks", lambda: {USER_HOOK.quirk_id: USER_HOOK})
    profile = profile_with({"[family.agentdojo.outcomes]": _QUIRK})
    doc = base_log()
    doc["messages"].insert(4, {"role": "user", "content": "Call rejected by the validator.", "error": "rejected"})
    m = map_log(doc, profile=profile)
    _ok(m)
    dc = m.get("dc0")
    assert dc["verdict"] == "deny" and dc["subject"] == "m2#1" and dc["reason"] == "rejected"
    feedback = m.get("m4")
    assert feedback["role"] == "user" and feedback["generated_by"] == "dc0" and feedback["actor"] == dc["actor"]
    assert not m.issues("agentdojo.unknown_message_shape")


def test_a_via_profile_carries_only_its_attack_provenance():
    """D.4.4 ``autodojo-via-rope``: ``[profile] via`` and ``[family.agentdojo.attack_provenance]``, no mapping tables."""
    text = PROFILE_PATH.read_text(encoding="utf-8")
    head, _, _rest = text.partition("[import]")
    head = head.replace('family = "agentdojo"\nparts', 'family = "agentdojo"\nvia = "rope"\nparts')
    via = head + ('[family.agentdojo.attack_provenance]\nattack = "autodojo"\ncache_repo = "https://github.com/xhOwenMa/AutoDojo"\n'
                  'cache_commit = "aa458794b7eb7f082e94daeac4c0f55bfc0c90cc"\nlink_rule = "agentdojo.local_model_tag_count@1"\n')
    table = family_table(parse_profile(via.encode(), source="test-via"))
    assert table.data["attack_provenance"]["attack"] == "autodojo" and not table.quirks
    with pytest.raises(ProfileError):  # a profile that maps needs its tables
        family_table(parse_profile(via.replace('via = "rope"\n', "").encode(), source="test-not-via"))


# ------------------------------------------------------------------------------------------------ census
def test_census_reproduces_counts_from_the_aer():
    doc = base_log(attack_type=None, injection_task_id=None, injections={}, user_task_id="injection_task_1")
    m = map_log(doc)
    counts = census.census_file(CensusFile(m.records, m.info.issues))
    assert counts["agentdojo.benign_security_constant"] == {"files": 1, "origin_rule_applied": 1}
    assert counts["agentdojo.injection_task_as_user_task_prepass"] == {"files": 1}
    totals = census.add(census.add({}, counts), counts)
    assert totals["agentdojo.benign_security_constant"]["files"] == 2
    table = family_table(profile_with({"head = { files = 3560, origin_rule_applied = 3546 }":
                                       "head = { files = 2, origin_rule_applied = 2, invented_key = 1 }"}))
    problems = census.compare(table, "head", totals)
    assert "agentdojo.benign_security_constant.invented_key: no census function computes it" in problems
    assert not any(p.startswith("agentdojo.benign_security_constant.files") for p in problems)
