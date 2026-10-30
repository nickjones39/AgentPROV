"""D-rule citation by verified code and the ``_unverified`` twins (docs/architecture D.5.4 "Citation of D rules"; D-24,
D-27 c6; regeneration-batch item 3; analysis B6, C6).

The resolver (:mod:`agentprov.adapters.code_verification`), the C.6.5 weakening of a record to its rules' class, the
twins of the shipped catalogues, the profiles' ``verified_code``, and the completeness rule that an inferred loss is not a
proven one (H.3.2(2)). The per-source fixture tests run the automated R07b check (``citation_check``) on real logs.
"""

from __future__ import annotations

import copy
import functools

import sys
import tomllib
from importlib import resources
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "agentdojo"))

from agentdojo_support import base_log, june_entry, map_log, profile_with  # noqa: E402
from citation_check import unverified_d_citations  # noqa: E402

from agentprov.adapters.agentdojo import citation  # noqa: E402
from agentprov.adapters.agentdojo.profile import family_table  # noqa: E402
from agentprov.adapters.code_verification import (  # noqa: E402
    TWIN_SUFFIX,
    Citations,
    VerifiedCode,
    code_commits,
    parse_verified_code,
    reading_of,
    weaken_to_rule_class,
)
from agentprov.adapters.profiles import load_profile  # noqa: E402
from agentprov.adapters.runner.importer import index_completeness, proven_loss_codes  # noqa: E402
from agentprov.aer.rules import load_catalogue  # noqa: E402
from agentprov.errors import ProfileError, RuleNotDeclared  # noqa: E402

C274885 = "c274885610efaaafec38b6d3eb07152ba7ff3f94"
HEAD = "089ed468cf3ed0322acc66b0211f26d9d90dbf60"
WHEEL_0135 = "a75aba7631d3ca5fb7ab938965c97ead2f9ff84b"
ADPROV = "579a908354b93361efe0905ffb7623256aa96a06"
FAMILY_CATALOGUES = ("agentdojo", "agentdyn", "rope", "mandate", "survey", "autodojo", "adprov")
#: The twins regeneration-batch item 3 adds (D-24: harness rules; D-27 c6: the nine document-only rules, and
#: adprov.empty_assistant_text_ambiguous, the tenth code-less D rule a mapper cites).
ITEM3_TWINS = {
    "agentdojo": {"benchmark_from_dialect", "user_is_simulated", "system_prompt_from_harness", "functions_runtime",
                  "log_holds_last_pass", "null_final_implies_three_passes", "empty_assistant_text_ambiguous",
                  "call_id_unique_match", "tool_status_from_error", "tools_executed_sequentially", "args_are_effective",
                  "committed_no_later_than", "checker_outcome", "benign_security_constant", "dos_security_rule",
                  "dos_placeholder_injection_task", "run_error_imposed_outcome", "injection_task_as_user_task"},
    "agentdyn": {"last_assistant_content_none_max3", "json_decode_error_imposed", "drift_user_error_key"},
    "rope": {"benchmark_from_suite", "tree_arm_config", "denial_query_echo_variant"},
    "adprov": {"single_attempt_from_call_count", "lost_calls_from_count", "assistant_turn_one_call", "call_id_unique_match",
               "tool_turn_is_one_execution", "finish_reason_positional", "empty_assistant_text_ambiguous"},
}
#: The SEM-rule twins regeneration-batch item 1 adds (D-86 and its addendum; cited by agentdojo.suites@2).
ITEM1_TWINS = {"agentdojo": {"injection_marker_yaml", "utility_meaning", "security_polarity", "autodojo_payload_unescape",
                             # regeneration-batch item 5 (D-370): the environment load
                             "environment_loaded_with_injections"},
               # regeneration-batch item 2 (D-376): CaMeL's feedback and planner input (the logs predate the cited code)
               "agentdyn": {"camel_interpreter_feedback", "camel_planner_input_not_logged"}}
#: The issue-rule twin regeneration-batch item 103 adds (D-80 (d) addendum, user decision 2026-10-15): the two issues
#: whose conclusion is a reading of the harness (not dispatched; result lost) cite it under unverified code.
ITEM103_TWINS = {"agentdojo": {"unexecuted_trailing_calls"}}
C6_NINE = {"adprov.assistant_turn_one_call", "adprov.call_id_unique_match", "adprov.tool_turn_is_one_execution",
           "adprov.finish_reason_positional", "adprov.single_attempt_from_call_count", "adprov.lost_calls_from_count",
           "agentdojo.functions_runtime", "agentdojo.committed_no_later_than", "agentdojo.empty_assistant_text_ambiguous"}


def _raw_rules(namespace: str) -> dict[str, dict]:
    home = "adapters/adprov" if namespace == "adprov" else "adapters/agentdojo"
    data = resources.files("agentprov").joinpath(*home.split("/"), "rules", f"{namespace}.rules.toml").read_bytes()
    return {f"{r['id']}@{r['version']}": r for r in tomllib.loads(data.decode("utf-8"))["rule"]}


# ------------------------------------------------------------------------------------------------ the catalogues
def test_every_twin_restates_its_d_rule():
    """A twin ``<id>_unverified@n`` of a D rule ``<id>@n`` is class I and active, reads the same premises, and its
    statement names the D rule; item 3's twins restate the D statement in full."""
    twins = 0
    for namespace in FAMILY_CATALOGUES:
        raw = _raw_rules(namespace)
        for rid, rule in raw.items():
            name, _, version = rid.partition("@")
            if not name.endswith(TWIN_SUFFIX) or f"{name.removesuffix(TWIN_SUFFIX)}@{version}" not in raw:
                continue
            twins += 1
            d = raw[f"{name.removesuffix(TWIN_SUFFIX)}@{version}"]
            assert d["class"] == "D" and rule["class"] == "I" and rule["status"] == "active", rid
            assert rule.get("premises", []) == d.get("premises", []) and not rule.get("code"), rid
            assert d["id"] in rule["statement"], rid
            if d["id"].split(".", 1)[1] in (*ITEM3_TWINS.get(namespace, ()), *ITEM1_TWINS.get(namespace, ()),
                                            *ITEM103_TWINS.get(namespace, ())):
                assert rule["statement"].endswith(d["statement"]) and "D.5.4" in rule["evidence"], rid
    # plus the four phase-6/10 structural twins
    assert twins == sum(map(len, ITEM3_TWINS.values())) + sum(map(len, ITEM1_TWINS.values())) + \
        sum(map(len, ITEM103_TWINS.values())) + 4


def test_item3_twins_exist_and_the_nine_document_only_rules_are_among_them():
    for namespace, names in ITEM3_TWINS.items():
        catalogue = load_catalogue(namespace)
        for name in names:
            assert catalogue.get(f"{namespace}.{name}@1").cls == "D"
            assert catalogue.get(f"{namespace}.{name}{TWIN_SUFFIX}@1").cls == "I"
    for rid in C6_NINE:  # D-27 c6: each cites no code, so no profile can verify it
        namespace = rid.split(".", 1)[0]
        assert not code_commits(namespace)[f"{rid}@1"], rid
        assert f"{rid}{TWIN_SUFFIX}@1" in load_catalogue(namespace).rules


def test_code_commits_are_read_from_the_loaded_catalogue():
    assert code_commits("agentdojo")["agentdojo.log_holds_last_pass@1"] == {C274885, WHEEL_0135}
    assert code_commits("agentdojo")["agentdojo.naive_local_timestamp@1"] == {HEAD}
    assert code_commits("agentdojo")["agentdojo.functions_runtime@1"] == frozenset()


# ------------------------------------------------------------------------------------------------ the resolver
def _cite(verified, facets=None, **kw) -> Citations:
    return Citations(parse_verified_code(verified, "test"), facets or {}, namespaces=citation.NAMESPACES, **kw)


def test_a_d_rule_is_cited_at_d_only_for_code_its_entry_lists():
    june = _cite([{"commit": C274885}])
    assert june.cite("agentdojo.checker_outcome@1") == "agentdojo.checker_outcome@1"
    assert june.cls("agentdojo.checker_outcome@1") == "D"
    head = _cite([{"commit": HEAD}, {"commit": WHEEL_0135}])
    assert head.cite("agentdojo.checker_outcome@1") == "agentdojo.checker_outcome_unverified@1"  # cited at c274885 only
    assert head.cite("agentdojo.naive_local_timestamp@1") == "agentdojo.naive_local_timestamp@1"
    assert head.cite("agentdojo.args_are_effective@1") == "agentdojo.args_are_effective@1"
    assert head.cls("agentdojo.checker_outcome@1") == "I"


def test_unverified_code_and_document_only_rules_resolve_to_their_twins():
    none = _cite([])
    assert none.cite("agentdojo.null_final_implies_three_passes@1") == "agentdojo.null_final_implies_three_passes_unverified@1"
    assert none.cite("agentdyn.last_assistant_content_none_max3@1") == "agentdyn.last_assistant_content_none_max3_unverified@1"
    june = _cite([{"commit": C274885}])
    for rid in ("agentdojo.functions_runtime@1", "agentdojo.committed_no_later_than@1",
                "agentdojo.empty_assistant_text_ambiguous@1"):  # D-27 c6: no code, so never verified
        assert june.cite(rid) == rid.replace("@1", "_unverified@1")


def test_i_rules_other_namespaces_and_independent_rules_pass_through():
    none = _cite([], independent=citation.INDEPENDENT)
    for rid in ("agentdojo.context_is_prefix@1", "agentdojo.auto_execution_unverified@1", "aer.output_after_generator@1",
                "agentdojo.system_prompt_variant_digest@1", "rope.security_correction@1",
                "agentdojo.functions_runtime_unverified@1"):
        assert none.cite(rid) == rid


def test_a_d_rule_with_no_twin_fails_closed():
    with pytest.raises(RuleNotDeclared, match="declares no class-I twin"):
        _cite([]).cite("agentdojo.tracelogger_record_shape@1")
    with pytest.raises(RuleNotDeclared):
        _cite([]).cite("mandate.decline_prefix@1")


def test_selectors_choose_the_verified_code_per_record():
    entries = [{"commit": C274885, "applies": {"variant": ["v0.k11"]}},
               {"commit": HEAD, "applies": {"variant": ["v1.k14*"]}}]
    assert _cite(entries, {"variant": "v0.k11"}).verified == {C274885}
    assert _cite(entries, {"variant": "v1.k14.incomplete"}).verified == {HEAD}
    assert _cite(entries, {"variant": None}).verified == frozenset()
    assert VerifiedCode(HEAD).matches({})


def test_malformed_verified_code_is_a_profile_error():
    for bad in ([{"commit": "c274885"}], [{"commit": C274885.upper()}], [{"commit": C274885, "applies": ["v0"]}], ["x"]):
        with pytest.raises(ProfileError):
            parse_verified_code(bad, "test")


def test_reading_of_maps_a_twin_to_its_d_rule():
    assert reading_of("agentdojo.checker_outcome_unverified@1#/origin") == "agentdojo.checker_outcome@1"
    assert reading_of("agentdojo.checker_outcome@1") == "agentdojo.checker_outcome@1"


# ------------------------------------------------------------------------------------------------ C.6.5 weakening
def test_weakening_follows_the_rule_class_and_never_raises():
    record = {"k": "tool_execution", "id": "te0", "ev": "D", "name": "f", "status": "ok", "call": "m1#0",
              "evf": {"/name": "O"},
              "rule": ["agentdojo.tool_msg_is_one_execution@1", "agentdojo.call_id_unique_match@1#/call",
                       "agentdojo.tool_status_from_error_unverified@1#/status"]}
    weaken_to_rule_class(record)
    assert record["ev"] == "D" and record["evf"] == {"/name": "O", "/status": "I"}
    record["rule"][0] = "agentdojo.tool_msg_is_one_execution_unverified@1"
    weaken_to_rule_class(record)
    assert record["ev"] == "I" and record["evf"] == {"/name": "O", "/status": "I"}  # /call inherits I; O stays O
    observed = {"k": "message", "id": "m1", "ev": "O", "by": "source", "role": "assistant",
                "rule": ["agentdojo.args_are_effective_unverified@1"]}
    weaken_to_rule_class(observed)
    assert observed["ev"] == "O" and "evf" not in observed  # an observation is not justified by a rule
    output = {"k": "message", "id": "m2", "ev": "O", "by": "source", "role": "assistant", "generated_by": "mc0",
              "after": [{"b": "causal", "id": "mc0"}], "evf": {"/after": "D", "/generated_by": "D"},
              "rule": ["adprov.assistant_turn_one_call_unverified@1#/generated_by", "aer.output_after_generator@1#/after"]}
    weaken_to_rule_class(output)  # the causal edge rests on the generator link (C.6.5 rule 1), whose rule is the twin
    assert output["evf"] == {"/after": "I", "/generated_by": "I"}
    derived = {"k": "actor", "id": "user", "ev": "D", "kind": "simulated_user", "rule": ["agentdojo.user_is_simulated@1"]}
    weaken_to_rule_class(derived)
    assert derived == {"k": "actor", "id": "user", "ev": "D", "kind": "simulated_user", "rule": ["agentdojo.user_is_simulated@1"]}



def test_weakening_reaches_a_nested_scoped_pointer_as_aer_v14_reads_it_f1():
    # pre-round review F-1 (D-224): AER-V14 evaluates a scoped rule's own pointer when a value is there, so the weakening
    # must too; else a twinned retry rule scoped to /ext/agentdojo/pre_state_not_initial left that value D (the AgentDyn
    # retry semantics, refused by the writer)
    retry = "agentdyn.last_assistant_content_none_max3_unverified@1"
    att = {"k": "scope", "id": "att0", "kind": "attempt", "parent": "run", "actor": "agent", "scored": True, "ev": "D",
           "index": 2, "ext": {"agentdojo": {"pre_state_not_initial": True}},
           "rule": ["agentdojo.log_holds_last_pass@1", f"{retry}#/ext/agentdojo/pre_state_not_initial", f"{retry}#/index"]}
    weaken_to_rule_class(att)
    assert att["ev"] == "D" and att["evf"] == {"/ext/agentdojo/pre_state_not_initial": "I", "/index": "I"}
    absent = {"k": "scope", "id": "att0", "kind": "attempt", "parent": "run", "actor": "agent", "scored": True, "ev": "D",
              "rule": ["agentdojo.log_holds_last_pass@1", f"{retry}#/ext/agentdojo/pre_state_not_initial"]}
    weaken_to_rule_class(absent)
    assert "evf" not in absent  # no value at the pointer: nothing to weaken


# ------------------------------------------------------------------------------------------------ profiles
@pytest.mark.parametrize("profile_id", ["rope", "agentdyn", "survey-runs"])
def test_unverified_harness_profiles_verify_no_code(profile_id):
    assert family_table(load_profile(profile_id)).verified_code == ()


def test_upstream_verifies_june_code_for_v0_and_the_030_family_for_v1():
    """June-2024 code verifies a v0.k11 log introduced in the 2024-06 pin's history only (D-84); a later or unknown
    introducing commit verifies nothing."""
    fam = family_table(load_profile("agentdojo-upstream"))
    june = {"variant": "v0.k11", "introduced_under": C274885}
    assert {v.commit for v in fam.verified_code if v.matches(june)} == {C274885}
    for later in ({**june, "introduced_under": HEAD}, {**june, "introduced_under": None}, {"variant": "v0.k11"}):
        assert {v.commit for v in fam.verified_code if v.matches(later)} == set()
    assert {v.commit for v in fam.verified_code if v.matches({"variant": "v1.k14"})} == {WHEEL_0135, HEAD}


def test_adprov_verifies_june_code_for_converted_transcripts_only():
    """June-2024 code for converted transcripts; for released ones the writer's pinned agentdojo 0.1.35 (D-86 addendum:
    579a908's pyproject requires agentdojo==0.1.35, whose task suite and tool_result_to_str the writer ran)."""
    entries = parse_verified_code(load_profile("adprov-v1").family_table()["verified_code"], "adprov-v1")
    assert {v.commit for v in entries if v.matches({"transcript": "released"})} == {ADPROV, WHEEL_0135}
    assert {v.commit for v in entries if v.matches({"transcript": "converted"})} == {ADPROV, C274885}


def test_released_adprov_transcripts_cite_no_rule_off_the_writers_code_path():
    """Verifying a75aba7 for released transcripts makes every rule citing it D there; the mapper may therefore cite none
    of the 0.1.35 rules whose passage is not on the writer's path (benchmark.py's DoS rule and pre-pass loop, the run-error
    imposition): those are cited for converted transcripts only, and a released run is never a pre-pass."""
    off_path = ("agentdojo.dos_security_rule", "agentdojo.injection_task_as_user_task", "agentdojo.run_error_imposed_outcome")
    released = 0
    for label, mapped, _profile in _real_mappings():
        if not label.startswith("adprov/") or mapped.header["ext"]["adprov"]["v1"]["variant"] != "released":
            continue
        released += 1
        cited = {r.split("#", 1)[0].split("@", 1)[0] for rec in mapped.records for r in rec.get("rule", ())}
        assert not cited & set(off_path), label
    assert released


# ------------------------------------------------------------------------------------------------ mapping (B6)
def _null_final(**kw):
    doc = base_log(**kw)
    doc["messages"][-1]["content"] = None
    return doc


def test_june_retry_is_derived_and_proves_loss():
    m = map_log(_null_final())
    att = m.get("att0")
    assert att["ev"] == "D" and att["index"] == 2 and "evf" not in att
    retry = m.issues("retry_passes_inferred")[0]
    assert retry["rule"] == "agentdojo.null_final_implies_three_passes@1"
    assert proven_loss_codes(m.info.issues) == {"retry_passes_inferred"}
    assert unverified_d_citations(m.records, m.profile) == []


def test_unverified_retry_is_inferred_and_leaves_completeness_unverifiable():
    """Analysis B6: the retry inference for an unverified harness cites the twin, the index is I (inference bundle) and
    the loss is inferred, not proven, so the execution is ``unverifiable`` instead of ``known_incomplete``."""
    unverified = profile_with({june_entry(): ""})
    m = map_log(_null_final(), profile=unverified)
    assert m.validate().ok
    att = m.get("att0")
    assert att["ev"] == "I" and att["index"] == 2
    assert "agentdojo.null_final_implies_three_passes_unverified@1#/index" in att["rule"]
    assert "agentdojo.log_holds_last_pass_unverified@1" in att["rule"]
    assert m.issues("retry_passes_inferred")[0]["rule"] == "agentdojo.null_final_implies_three_passes_unverified@1"
    assert m.issues("earlier_attempts_unobservable")[0]["rule"] == "agentdojo.null_final_implies_three_passes_unverified@1"
    assert proven_loss_codes(m.info.issues) == frozenset()
    accounting = m.info.accounting.to_json()
    codes = {i["code"] for i in m.info.issues}
    proven = codes - ((codes & {"retry_passes_inferred"}) - proven_loss_codes(m.info.issues))
    assert index_completeness(degenerate=False, accounting=accounting["status"], checks_evaluated=len(accounting["checks"]),
                              unit_kind="agent_execution", seal_codes=proven) == "unverifiable"
    assert index_completeness(degenerate=False, accounting=accounting["status"], checks_evaluated=len(accounting["checks"]),
                              unit_kind="agent_execution", seal_codes=codes) == "known_incomplete"  # the old reading
    assert unverified_d_citations(m.records, unverified) == []
    for record in m.records[1:]:  # every governed D rule went to its twin, and its record or field to I
        for ref in record.get("rule", ()):
            rid = ref.partition("#")[0]
            if rid.split(".", 1)[0] == "agentdojo" and rid not in citation.INDEPENDENT:
                assert load_catalogue("agentdojo").get(rid).cls == "I" or not code_commits("agentdojo").get(rid), ref


def test_loss_codes_without_a_d_rule_prove_nothing():
    issues = [{"code": "retry_passes_inferred", "rule": "agentdyn.last_assistant_content_none_max3_unverified@1"},
              {"code": "incomplete_run", "rule": "agentdojo.incomplete_run@1"},
              {"code": "aborted_attempt"},
              {"code": "unexecuted_tool_call", "rule": "agentdojo.unexecuted_trailing_calls@1"}]
    assert proven_loss_codes(issues) == {"incomplete_run"}


# ------------------------------------------------------------------------------------------------ R07b on real fixtures
_SOURCES = {  # fixture directory -> (profile, repository, pinned commit)
    "agentdojo/head": ("agentdojo-upstream", "https://github.com/ethz-spylab/agentdojo", HEAD),
    "rope": ("rope", "https://github.com/xhOwenMa/ROPE", "64495e16e640d687e06e6b1b6cee6dccc5b9b7cb"),
    "agentdyn": ("agentdyn", "https://github.com/SaFo-Lab/AgentDyn", "5353cf7615b135cace8d07c8f12dac53a16b6db3"),
    "mandate": ("mandate-agentdojo-eval", "https://github.com/jwilliamsc/mandate-agentdojo-eval",
                "fa62a977584962f7b4b24a40772a83345fd920d4"),
    "survey": ("survey-runs", "https://github.com/Forever-CodingNoob/agent-security-tools-survey",
               "89c4db2c949797fbb38c5bfed85dc82780ddbfe3"),
}


def _real_mappings() -> list:
    """Every real fixture, mapped once per process (four tests read them); each call returns fresh copies, the
    profiles (the loader's shared objects) aside, so no test can change what another one reads."""
    out = []
    for label, mapped, profile in _mapped_once():
        memo = {id(p): p for p in (profile, getattr(mapped, "profile", None)) if p is not None}
        out.append((label, copy.deepcopy(mapped, memo), profile))
    return out


@functools.cache
def _mapped_once() -> tuple:
    return tuple(_map_real_fixtures())


def _map_real_fixtures():
    import hashlib
    import importlib.util
    import json

    from agentdojo_support import C161_PATH, c161_bytes, map_bytes, map_native, native_entries

    from agentprov.adapters.types import Origin
    from agentprov.testing import golden

    out = [(f"2024-06/{e.id}", map_native(e), None) for e in native_entries()]
    if golden.golden_available():
        out.append(("2024-06/C.16.1", map_bytes(c161_bytes(), C161_PATH), None))
    fixtures = golden.fixtures_root()
    for directory, (profile_id, repo, commit) in _SOURCES.items():
        source = fixtures / directory / "SOURCE.json"
        if not source.is_file():
            continue
        profile = load_profile(profile_id)
        for entry in json.loads(source.read_bytes()):
            raw = (fixtures / directory / entry["sample_file"]).read_bytes()
            assert hashlib.sha256(raw).hexdigest() == entry["sha256"]
            origin = Origin.git(repo, commit, entry["original_path"], entry["git_blob_sha1"])
            out.append((f"{directory}/{entry['original_path']}",
                        map_bytes(raw, entry["original_path"], profile=profile, origin=origin), None))
    spec = importlib.util.spec_from_file_location("adprov_conftest_r07b", Path(__file__).parent / "adprov" / "conftest.py")
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules["adprov_conftest_r07b"] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    adprov = load_profile("adprov-v1")
    for pair in module.load_pairs():
        out.append((f"adprov/{pair.id}", module.map_v1(pair.transcript.read_bytes(), pair.corpus_relpath), adprov))
    return out


def test_no_real_fixture_cites_a_d_rule_for_unverified_code():
    """CORPUS-CHECK-PROTOCOL R07b on every real fixture of the AgentDojo and adprov families (expected after item 3: 0),
    and every fixture's AER still passes release-mode validation."""
    mapped = _real_mappings()
    if len(mapped) < 10:
        pytest.skip("the real fixtures are not present")
    found = {key: hits for key, m, profile in mapped if (hits := unverified_d_citations(m.records, profile or m.profile))}
    assert found == {}
    for key, m, profile in mapped:
        if profile is None:  # the AgentDojo-family helper validates in release mode; adprov's suite validates its own
            report = m.validate()
            assert report.ok and report.passed, (key, [(f.code, f.pointer) for f in report.errors])


def test_the_r07b_check_finds_a_d_rule_cited_for_unverified_code():
    header = {"k": "execution", "id": "exec", "dialect": {"id": "agentdojo.tracelogger", "variant": "v1.k14"}}
    records = [header, {"k": "actor", "id": "user", "ev": "D", "rule": ["agentdojo.user_is_simulated@1"]},
               {"k": "actor", "id": "env", "ev": "I", "rule": ["agentdojo.functions_runtime_unverified@1"]},
               {"k": "message", "id": "m0", "rule": ["agentdojo.system_prompt_variant_digest@1#/ext/agentdojo/system_prompt_variant"]}]
    assert unverified_d_citations(records, load_profile("rope")) == ["user agentdojo.user_is_simulated@1"]
    assert unverified_d_citations(records, load_profile("agentdojo-upstream")) == ["user agentdojo.user_is_simulated@1"]
    records[0]["dialect"]["variant"] = "v0.k11"  # D-84: a v0.k11 log with no origin has no known introducing commit
    assert unverified_d_citations(records, load_profile("agentdojo-upstream")) == ["user agentdojo.user_is_simulated@1"]
    table = family_table(load_profile("agentdojo-upstream")).history
    assert table is not None
    june = next(c for c, row in table.commits.items() if row.under == C274885)
    later = next(c for c, row in table.commits.items() if row.under == HEAD)
    repo = "https://github.com/ethz-spylab/agentdojo"
    for origin, flagged in (({"kind": "git", "repo": repo, "commit": C274885}, False),
                            ({"kind": "git", "repo": repo, "commit": HEAD, "introduced_in_commit": june}, False),
                            ({"kind": "git", "repo": repo, "commit": HEAD, "introduced_in_commit": later}, True),
                            ({"kind": "git", "repo": repo, "commit": HEAD}, True)):
        records[0]["artifacts"] = [{"origin": origin}]
        assert bool(unverified_d_citations(records, load_profile("agentdojo-upstream"))) is flagged, origin


# ------------------------------------------------------------------------------------------------ SEM and PROV over twins
def _sem_prov_tier4(doc, profile):
    from agentprov.adapters.runner.provjob import PROFILES
    from agentprov.prov.engine import derive
    from agentprov.sem.engine import annotate
    from agentprov.validate import validate_prov

    fam = profile.family_table()  # the importer's --semantics; the stored corpora of both families use agentdojo.suites@1
    ref = (fam.get("benchmark") or {}).get("semantics_profile") or {"id": "agentdojo.suites", "version": 1}
    sem_profile = PROFILES[f"{ref['id']}@{ref['version']}"]
    sem = annotate(doc, sem_profile)
    result = derive(doc, [sem], sem_profiles={(sem_profile.id, sem_profile.version): sem_profile})
    report = validate_prov(result.prov_json, doc, sems=[sem])
    assert report.ok, sorted(report.codes())
    return sem, result


def test_an_outcome_over_a_twinned_origin_is_inferred_with_the_twin_as_its_method():
    """C.6.5 rule 3: an outcome annotation over a judgement whose origin rests on a twin is INFERRED by propagation and
    names no I rule of its own; PROV takes its method from the premise (D-83). A v1.k14 log under agentdojo-upstream."""
    import json

    from agentprov.aer.reader import load_aer_bytes
    from source_support import v1_log

    m = map_log(v1_log())
    doc = load_aer_bytes(m.data)
    sem, result = _sem_prov_tier4(doc, m.profile)
    # the security outcome has the judgement's /origin among its premises (the twin's), so it is INFERRED; the utility
    # outcome reads /value only and keeps D
    outcomes = [r for r in sem.records if r.get("type") == "outcome" and r["ev"] == "I"]
    assert [r["rule"] for r in outcomes] == [["agentdojo.security_polarity@1"]]
    assert {rule for r in outcomes for rule in r["rule"]} <= {"agentdojo.security_polarity@1", "agentdojo.utility_meaning@1"}
    bodies = [b for bundle in json.loads(result.prov_json)["bundle"].values() for section in bundle.values()
              if isinstance(section, dict) for b in section.values()
              if isinstance(b, dict) and b.get("apv:annotationId") in {r["id"] for r in outcomes} and "apv:method" in b]
    assert bodies
    for body in bodies:
        methods = body["apv:method"] if isinstance(body["apv:method"], list) else [body["apv:method"]]
        assert "agentdojo.checker_outcome_unverified@1" in methods


def test_one_real_fixture_per_affected_profile_passes_sem_prov_and_tier4():
    mapped = _real_mappings()
    if len(mapped) < 10:
        pytest.skip("the real fixtures are not present")
    from agentprov.aer.reader import load_aer_bytes

    seen: set[tuple[str, str | None]] = set()
    for _key, m, profile in mapped:
        profile = profile or m.profile
        facet = m.records[0].get("dialect", {}).get("variant"), \
            ((m.records[0].get("ext") or {}).get("adprov") or {}).get("v1", {}).get("variant")
        if (profile.id, str(facet)) in seen:
            continue
        seen.add((profile.id, str(facet)))
        _sem_prov_tier4(load_aer_bytes(m.data), profile)
    assert {p for p, _ in seen} >= {"agentdojo-upstream", "rope", "agentdyn", "survey-runs", "mandate-agentdojo-eval",
                                    "adprov-v1"}


# ------------------------------------------------------------------------------------------------ items 13 and 14
def test_a_v0_log_is_june_code_only_when_introduced_in_the_2024_06_history():
    """D-84 (regeneration-batch item 13): the June-2024 citations verify a v0.k11 log only when the commit that
    introduced its blob is in the 2024-06 pin's history (facet ``introduced_under``, from the history table); a log
    introduced later, or with no known introducing commit, cites the twins. A log whose origin is the 2024-06 pin is in
    that history by construction."""
    from agentdojo_support import C274885 as PIN_2024_06
    from agentdojo_support import REPO_URL, git_blob, log_bytes, map_bytes, path_of

    from agentprov.adapters.types import Origin

    table = family_table(load_profile("agentdojo-upstream")).history
    assert table is not None
    june = next(c for c, row in table.commits.items() if row.under == PIN_2024_06)
    later = next(c for c, row in table.commits.items() if row.under == HEAD)
    doc = base_log()
    raw, path = log_bytes(doc), path_of(doc)
    cases = {
        "2024-06 origin": (Origin.git(REPO_URL, PIN_2024_06, path, git_blob(raw)), False),
        "head, introduced in June": (Origin.git(REPO_URL, HEAD, path, git_blob(raw), introduced_in_commit=june), False),
        "head, introduced later": (Origin.git(REPO_URL, HEAD, path, git_blob(raw), introduced_in_commit=later), True),
        "head, no introducing commit": (Origin.git(REPO_URL, HEAD, path, git_blob(raw)), True),
    }
    for label, (origin, twinned) in cases.items():
        m = map_bytes(raw, path, origin=origin)
        assert m.validate().ok, label
        cited = {r.split("#", 1)[0] for rec in m.records for r in rec.get("rule", ())}
        assert ("agentdojo.user_is_simulated_unverified@1" in cited) is twinned, label
        assert ("agentdojo.user_is_simulated@1" in cited) is not twinned, label
        assert unverified_d_citations(m.records, load_profile("agentdojo-upstream")) == [], label


def test_a_causal_after_is_never_stronger_than_the_call_link_it_follows():
    """D-87 (regeneration-batch item 14): an execution's causal ``after`` rests on its ``call`` link, so a positional or
    twinned (I) link makes it I, in both mappers (``weaken_to_rule_class``). Checked on every real fixture mapping, and
    directly on a record."""
    from agentprov.adapters.code_verification import weaken_to_rule_class
    from agentprov.aer.evidence import effective_tag, tag_class

    rank = {"I": 0, "D": 1, "O": 2}
    weakened = 0
    for label, mapped, _profile in _real_mappings():
        for rec in mapped.records:
            after = rec.get("after")
            if rec.get("k") != "tool_execution" or "call" not in rec or not isinstance(after, list):
                continue
            if not any(isinstance(a, dict) and a.get("b") == "causal" for a in after):
                continue
            a_cls, c_cls = (tag_class(effective_tag(rec, p)) for p in ("/after", "/call"))
            assert rank[a_cls] <= rank[c_cls], (label, rec["id"])
            weakened += c_cls == "I"
    assert weakened  # the fixtures hold positional or twinned links
    te = {"k": "tool_execution", "id": "te0", "ev": "D", "call": "m1#0", "evf": {"/call": "I"},
          "after": [{"b": "causal", "id": "m1"}], "rule": ["agentdojo.positional_match@1#/call", "aer.execution_after_call@1#/after"]}
    weaken_to_rule_class(te)
    assert te["evf"]["/after"] == "I"
    te = {"k": "tool_execution", "id": "te0", "ev": "D", "call": "m1#0", "after": [{"b": "causal", "id": "m1"}],
          "rule": ["aer.execution_after_call@1#/after"]}
    weaken_to_rule_class(te)
    assert "evf" not in te  # a D link leaves the edge D
