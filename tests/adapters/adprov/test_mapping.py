"""``adprov.transcript_v1`` mapping (docs/architecture D.7.3, C.15.3, C.16.2, J.2.4, J.3.2; K.6.2).

Golden-backed tests use the real AgentDojo-PROV pairs (skipped when the fixtures are absent); every other test builds a
synthetic transcript in code. Nothing here compares decoded documents with ``==``: byte and JCS comparisons only
(K.1(9)); failures print ids, pointers and digests, never fixture content (R-42).
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import tomllib
from pathlib import Path

import pytest

from agentprov.adapters.adprov.dialect import TranscriptV1Reader
from agentprov.adapters.adprov.mapper import TranscriptV1Mapper, _tool_status
from agentprov.adapters.profiles import load_profile
from agentprov.adapters.runner import aer_bytes, map_unit
from agentprov.adapters.types import ArtefactRef, ExecutionUnit
from agentprov.aer.rules import load_catalogue
from agentprov.ingest.limits import IngestLimits
from agentprov.io.canonical import jcs_bytes
from agentprov.testing import golden

REPO = Path(__file__).resolve().parents[3]
#: The C.16.2 vector as the writer seals it today: the ``aer/0.2`` reseal (C.21; the published 0.1 vector is unchanged).
C16_2 = REPO / "docs" / "architecture" / "examples" / "C" / "aer-0.2" / "adprov_v1_llama_injecagent.aer.jsonl"
#: The stand-in profile text whose digest the C.16.2 vector carries (docs/architecture/examples/C/gen_examples.py).
STANDIN = (
    b'# stand-in for spec/examples/C (C.16.0); not the shipped profile\n[profile]\nid = "adprov-v1"\nversion = 1\n'
    b'format = "agentprov-source-profile/0.1"\nsource_id = "adprov-v1"\nfamily = "adprov"\n'
)


def _assert_round_trip(m) -> None:
    golden.assert_bytes_equal(m.raw, m.view_bytes(), what="serialise(render(map(v1)))")
    report = m.validate()
    assert report.ok, sorted({f.code + " " + f.pointer for f in report.errors})


# ------------------------------------------------------------------------------------------------ the worked example
def test_c16_2_vector_is_reproduced(golden_pairs, v1):
    """C.16.2 is normative: with its stand-in profile digest, the mapper reproduces the vector byte for byte."""
    pair = golden_pairs.get("R04")
    if pair is None:
        pytest.skip("R04 is not in this golden set")
    raw = pair.transcript.read_bytes()
    golden.assert_matches_sha256(raw, "a8ef75b854a1bddbb9b3b265fdd48094f5ca689aab762da24a05472e56221335", what="R04")
    profile = dataclasses.replace(load_profile("adprov-v1"), sha256=hashlib.sha256(STANDIN).hexdigest())
    reader, mapper = TranscriptV1Reader(), TranscriptV1Mapper()
    sniff = reader.sniff(raw, label="R04", limits=IngestLimits())
    origin = v1.origin("corpus-prov/meta-llama_llama-3.3-70b-instruct/prov/injecagent/"
                       "banking_user_task_2_x_injectiontask5_injection.transcript.json")
    artefact = ArtefactRef("a0", hashlib.sha256(raw).hexdigest(), len(raw), "application/json", origin, "primary",
                           mapper.prov_primary(sniff.flags))  # type: ignore[arg-type]
    item = next(reader.parse(raw, artefact, limits=IngestLimits()))
    data, info = aer_bytes(map_unit(ExecutionUnit(item), mapper, profile))
    golden.assert_bytes_equal(C16_2.read_bytes(), data, what="C.16.2 vector")
    assert info.execution_digest == "8280aee77cd80a9b7748599bba7f7b5ca501a948fc1a977121c6e0d3ac9d61a1"  # aer/0.2 (C.21)


# ------------------------------------------------------------------------------------------------ header
def test_header_task_coordinates(map_golden, v1):
    released = map_golden("R04").header
    assert released["task"]["defense_id"] is None and released["evf"]["/task/defense_id"] == "D"
    assert released["profile"]["id"] == "adprov-v1" and released["artifacts"][0]["prov_primary"] == "native"
    assert released["dialect"] == {"id": "adprov.transcript_v1", "variant": "v1"}
    benign = map_golden("R01").header
    assert benign["task"]["attack_id"] is None
    assert "adprov.v1_benign_label@1#/task/attack_id" in benign["rule"]
    assert not [r for r in map_golden("R01").of_kind("actor") if r["kind"] == "attacker"]
    converted = map_golden("C04").header
    assert converted["artifacts"][0]["prov_primary"] == "secondary"
    assert "defense_id" not in converted["task"] and converted["unk"]["/task/defense_id"] == "ambiguous"
    assert converted["unk"]["/instrumentation"] == "not_recorded" and "instrumentation" not in converted
    assert converted["ext"]["adprov"]["v1"]["variant"] == "converted"


def test_converted_upstream_link(map_golden):
    link = map_golden("C06").header["ext"]["adprov"]["derived_from_upstream"]
    assert link == {
        "commit": "c274885610efaaafec38b6d3eb07152ba7ff3f94",
        "path": "runs/command-r-plus/travel/user_task_18/important_instructions/injection_task_2.json",
        "repo": "https://github.com/ethz-spylab/agentdojo",
    }
    benign = map_golden("C01").header["ext"]["adprov"]["derived_from_upstream"]
    assert benign["path"] == "runs/claude-3-haiku-20240307/banking/user_task_9/none/none.json"
    assert map_golden("C01").header["evf"]["/ext/adprov/derived_from_upstream"] == "D"


def test_converted_identity_is_not_split(map_golden):
    """J.4.4: the v1 import keeps the pipeline name verbatim and asserts no model or defence identity."""
    m = map_golden("C05")
    agent = m.by_id()["agent"]
    assert "model" not in agent and agent["unk"]["/model/requested"] == "ambiguous"
    assert "agentdojo.pipeline_dir_is_model_identity@1#/model/requested" in agent["rule"]
    ext = m.header["ext"]
    assert ext["agentdojo"]["pipeline_name"] == ext["adprov"]["model_id"] == ext["adprov"]["model"]


def test_injection_task_as_user_task_kind(v1):
    doc = v1.converted(user_task_id="injection_task_4", attack_type="benign", injection_task_id=None, injections={})
    m = v1.map(v1.dump(doc))
    assert m.header["ext"]["agentdojo"]["task_kind"] == "injection_task_as_user_task"
    assert "agentdojo.injection_task_as_user_task@1#/ext/agentdojo/task_kind" in m.header["rule"]
    _assert_round_trip(m)


# ------------------------------------------------------------------------------------------------ attempts and calls
def test_attempt_structure_by_call_count(map_golden, v1):
    # counter equals the assistant turns: one attempt, index 0 (C.16.2); the rule cites no code, so its twin (D-27 c6)
    att = map_golden("R04").by_id()["att0"]
    assert att["index"] == 0 and att["scored"] is True and att["ev"] == "I"
    assert att["rule"] == ["adprov.single_attempt_from_call_count_unverified@1"]
    # no counter (DeepSeek): index unknown, earlier passes unobservable
    r01 = map_golden("R01")
    assert r01.by_id()["att0"]["unk"] == {"/index": "lost"}
    assert "earlier_attempts_unobservable" in r01.issue_codes()
    # R05 (C.7.4): 6 reported calls, 2 assistant turns, 7 finish reasons -> mutually inconsistent: no lost call,
    # finish reasons kept verbatim, accounting inconsistent
    r05 = map_golden("R05")
    calls = r05.of_kind("model_call")
    assert len(calls) == 2 and all(c["unk"]["/finish_reason"] == "ambiguous" for c in calls)
    assert len(r05.header["ext"]["adprov"]["v1"]["finish_reasons"]) == 7
    assert r05.info.accounting.status == "inconsistent" and "accounting_inconsistent" in r05.issue_codes()
    # a consistent excess (finish reasons == reported calls): the missing calls are lost model calls (C.7.4)
    doc = v1.released()
    doc["meta"]["model_config"]["usage"]["n_llm_calls"] = 4
    doc["meta"]["model_config"]["finish_reasons"] = ["stop", "length", "tool_calls", "stop"]
    m = v1.map(v1.dump(doc))
    by = m.by_id()
    lost = [c for c in m.of_kind("model_call") if c["scope"] == "att0"]
    assert [c["id"] for c in lost] == ["mc0", "mc1"]
    assert all(c["unk"]["/status"] == "lost" and c["unk"]["/input"] == "lost" and c["ev"] == "I" for c in lost)  # D-27 c6
    assert all(c["rule"][0] == "adprov.lost_calls_from_count_unverified@1" for c in lost)
    assert [c.get("finish_reason") for c in m.of_kind("model_call")] == ["stop", "length", "tool_calls", "stop"]
    assert by["att0"]["scored"] is False and by["att1"]["scored"] is True and "index" not in by["att1"]
    assert m.info.accounting.status == "consistent"
    _assert_round_trip(m)


def test_context_membership_is_inferred(map_golden):
    for pair_id in ("R02", "C03"):
        for call in map_golden(pair_id).of_kind("model_call"):
            assert call["evf"]["/input"] == "I" and "adprov.context_is_prefix@1#/input" in call["rule"]


def test_finish_reasons_alignment(map_golden, v1):
    # aligned: one typed finish reason per call, cited positionally (the rule cites no code: its twin, D-27 c6)
    for call in map_golden("R02").of_kind("model_call"):
        assert isinstance(call["finish_reason"], str)
        assert "adprov.finish_reason_positional_unverified@1#/finish_reason" in call["rule"]
    # a provider null stays unknown (never a sentinel), the rest aligned
    doc = v1.released()
    doc["meta"]["model_config"]["finish_reasons"] = [None, "stop"]
    m = v1.map(v1.dump(doc))
    first, second = m.of_kind("model_call")
    assert "finish_reason" not in first and first["unk"]["/finish_reason"] == "not_recorded"
    assert second["finish_reason"] == "stop"
    _assert_round_trip(m)


def test_tool_linking_by_id_and_position(map_golden):
    # unique ids: linked by id, under a rule that cites no code, so its twin and I (D-27 c6)
    for te in map_golden("R03").of_kind("tool_execution"):
        assert te["evf"]["/call"] == "I" and "adprov.call_id_unique_match_unverified@1#/call" in te["rule"]
    # null ids (Cohere) and "" ids (Gemini): positional pairing verified by function and args (I)
    for pair_id in ("C06", "C07"):
        m = map_golden(pair_id)
        for te in m.of_kind("tool_execution"):
            assert te["evf"]["/call"] == "I" and "agentdojo.positional_match@1#/call" in te["rule"]
        for msg in m.of_kind("message"):
            if msg["role"] == "tool":
                assert msg["evf"]["/parts/0/responds_to"] == "I"


def test_tool_id_mismatch_links_nothing(v1):
    doc = v1.converted()
    doc["turns"][3]["tool_call_id"] = "call_other"
    m = v1.map(v1.dump(doc))
    te = m.of_kind("tool_execution")[0]
    assert "call" not in te and te["unk"]["/call"] == "ambiguous"
    assert "adprov.tool_call_id_mismatch" in m.issue_codes()
    _assert_round_trip(m)


def test_tool_status_from_error():
    assert _tool_status(None) == "ok"
    assert _tool_status("ValidationError: 1 validation error") == "invalid"
    assert _tool_status("Invalid tool x provided.") == "invalid"
    assert _tool_status("Empty function name provided.") == "invalid"
    assert _tool_status("KeyError: 'x'") == "error"


def test_unexecuted_trailing_calls(v1):
    doc = v1.released()
    doc["turns"] = doc["turns"][:3]  # the last assistant turn's call has no tool turn
    doc["meta"]["model_config"]["usage"]["n_llm_calls"] = 1
    doc["meta"]["model_config"]["finish_reasons"] = ["tool_calls"]
    m = v1.map(v1.dump(doc))
    issue = next(i for i in m.info.issues if i["code"] == "unexecuted_tool_call")
    assert issue["ids"] == ["m2#1"] and issue["rule"] == "agentdojo.unexecuted_trailing_calls@1"
    assert not m.of_kind("tool_execution")
    _assert_round_trip(m)


def test_duplicated_call_id_timing_is_overwritten(map_golden):
    """J.2.4 R07: the timing of an earlier same-id call was overwritten by the later one's."""
    m = map_golden("R07")
    issue = next(i for i in m.info.issues if i["code"] == "adprov.tool_timing_overwritten")
    (te_id,) = issue["ids"]
    te = m.by_id()[te_id]
    assert te["unk"]["/t/start"] == "overwritten" and "start" not in te["t"] and "raw" in te["t"]
    # the repeated id is unique within each assistant turn's batch, so the link is by id (D.6.6.1 step 1), not positional
    assert te["evf"]["/call"] == "I" and "adprov.call_id_unique_match_unverified@1#/call" in te["rule"]


def test_converted_timing_stub_is_unknown(map_golden):
    for te in map_golden("C01").of_kind("tool_execution"):
        assert te["t"] == {"raw": {"end": "0", "start": "0"}}
        assert te["unk"]["/t/start"] == te["unk"]["/t/end"] == "not_recorded"
        assert "adprov.timing_stub_is_unknown@1#/t/start" in te["rule"]
    run = map_golden("C01").by_id()["run"]
    assert run["t"]["dur_clock"] == "wall" and run["unk"]["/t/start"] == "not_recorded"


def test_pi_detector_redaction(map_golden):
    """C05: the detector's sentinel is a redact decision over the execution; the original output is overwritten."""
    m = map_golden("C05")
    decisions = m.of_kind("decision")
    assert len(decisions) == 4
    by = m.by_id()
    for dc in decisions:
        assert dc["verdict"] == "redact" and dc["ev"] == "I" and dc["unk"]["/original"] == "overwritten"
        assert by[dc["subject"]]["k"] == "tool_execution"
    redacted = [msg for msg in m.of_kind("message") if msg.get("generated_by", "").startswith("dc")]
    assert len(redacted) == 4 and all(msg["actor"] == "def0" and msg["evf"]["/generated_by"] == "I" for msg in redacted)


def test_additional_user_turns_are_unattributed(v1):
    doc = v1.converted()
    doc["turns"].insert(4, {"role": "user", "content": "a later user-role turn (synthetic)"})
    m = v1.map(v1.dump(doc))
    later = m.by_id()["m4"]
    assert later["actor"] == "user" and later["evf"]["/actor"] == "I"
    assert "unattributed_additional_user_message" in m.issue_codes()
    _assert_round_trip(m)


def test_empty_texts_are_ambiguous(map_golden, v1):
    released = map_golden("R04").by_id()["m2"]
    assert released["unk"]["/parts/0/text"] == "ambiguous"
    assert "adprov.release_null_as_empty@1#/parts/0/text" in released["rule"]
    doc = v1.converted()
    doc["turns"][2]["text"] = ""
    m = v1.map(v1.dump(doc))
    msg = m.by_id()["m2"]
    assert msg["unk"]["/parts/0/text"] == "ambiguous"
    assert "adprov.empty_assistant_text_ambiguous_unverified@1#/parts/0/text" in msg["rule"]  # no code cited: the twin
    _assert_round_trip(m)


# ------------------------------------------------------------------------------------------------ outcomes
def test_judgement_origins(map_golden):
    def origins(pair_id: str) -> dict[str, tuple[str, list[str]]]:
        return {j["name"]: (j["origin"], j["rule"]) for j in map_golden(pair_id).of_kind("judgement")}

    checked = ["adprov.checker_outcome@1#/origin", "agentdojo.checker_inputs_unverified@1#/inputs"]  # E.10 item 21
    assert origins("R02") == {"utility": ("checker", checked), "security": ("checker", checked)}
    assert origins("R01")["security"] == ("harness_default", ["adprov.benign_security_normalised@1#/origin"])
    assert origins("C01")["security"] == ("harness_default", ["agentdojo.benign_security_constant@1#/origin"])
    assert origins("C04")["security"] == ("harness_rule", ["agentdojo.dos_security_rule@1#/origin"])
    assert origins("C04")["utility"] == ("checker", ["agentdojo.checker_outcome@1#/origin",
                                                     "agentdojo.checker_inputs_unverified@1#/inputs"])
    c06 = origins("C06")
    assert c06["utility"][0] == c06["security"][0] == "harness_default"
    assert "outcome_imposed_by_runner" in map_golden("C06").issue_codes()


def test_transcript_without_turns_is_outcome_only(v1):
    doc = v1.released()
    doc["turns"] = []
    del doc["meta"]["model_config"]
    m = v1.map(v1.dump(doc))
    assert m.header["unit"] == "outcome_only"
    assert not m.of_kind("message") and not [s for s in m.of_kind("scope") if s["kind"] == "attempt"]
    assert "no_execution_observed" in m.issue_codes() and len(m.of_kind("judgement")) == 2
    _assert_round_trip(m)


# ------------------------------------------------------------------------------------------------ layout (J.3.2)
def test_layout_deviations_raise_issues(v1):
    doc = v1.released()
    meta = doc["meta"]
    doc["meta"] = {"model_id": meta.pop("model_id"), **meta, "unexpected_member": [1, 2.0]}  # reordered + unknown member
    turn = doc["turns"][3]
    doc["turns"][3] = {"function": turn.pop("function"), **turn}  # a tool turn in an order the writer never produced
    doc["turns"][3]["content_sha256"] = "sha256:" + "0" * 64  # a digest that does not match the content
    m = v1.map(v1.dump(doc))
    codes = m.issue_codes()
    assert "adprov.v1_layout_unexpected_order" in codes and "adprov.v1_layout_unknown_member" in codes
    assert "adprov.content_hash_mismatch" in codes
    _assert_round_trip(m)  # the issues are recorded, and the view still regenerates the bytes


def test_malformed_input_seals_degenerate(v1):
    doc = v1.released()
    doc["meta"]["injections"] = ["not", "an", "object"]
    m = v1.map(v1.dump(doc))
    assert m.outcome.degenerate and m.issue_codes() == ["unparseable_artefact"]
    assert [r["k"] for r in m.records] == ["execution", "scope", "seal"]  # header, the run scope (AER-V07), seal
    assert m.validate().ok


# ------------------------------------------------------------------------------------------------ hints, rules, determinism
def test_lexical_hints_are_load_bearing(map_golden):
    """Without ``ext.lex`` the view loses the integral float and the argument order of C.16.2 (C.11.4)."""
    from agentprov.views.transcript_v1 import render, serialise

    m = map_golden("R04")
    stripped = copy.deepcopy(m.records[:-1])
    for record in stripped:
        record.get("ext", {}).pop("lex", None)
    assert serialise(render(stripped)) != m.raw
    assert jcs_bytes(render(stripped)) == jcs_bytes(render(m.records[:-1]))  # values survive; only lexical form is lost


def test_emitted_rules_and_issue_codes_are_declared(golden_pairs, map_golden):
    adprov, agentdojo = load_catalogue("adprov"), load_catalogue("agentdojo")
    catalogues = {"adprov": adprov, "agentdojo": agentdojo, "aer": load_catalogue("aer")}
    for pair_id in sorted(golden_pairs):
        m = map_golden(pair_id)
        refs = [r for rec in m.records for r in rec.get("rule", [])] + [i["rule"] for i in m.info.issues]
        refs += [item["id"] for item in m.header.get("instrumentation", [])]
        for ref in refs:
            rule_id = ref.split("#", 1)[0]
            ns = rule_id.split(".", 1)[0]
            assert catalogues[ns].get(rule_id) is not None, f"{pair_id}: {rule_id} is not declared"
        for issue in m.info.issues:
            if "." in issue["code"]:
                ns = issue["code"].split(".", 1)[0]
                assert catalogues[ns].declares_issue_code(issue["code"]), issue["code"]


def test_catalogue_test_references_exist():
    """D.5.2 validation item 6: every ``tests`` node id of the adprov and agentdojo catalogues exists."""
    for ns, home in (("adprov", "adprov"), ("agentdojo", "agentdojo")):
        path = REPO / "src" / "agentprov" / "adapters" / home / "rules" / f"{ns}.rules.toml"
        doc = tomllib.loads(path.read_text(encoding="utf-8"))
        for rule in doc["rule"]:
            for node in rule.get("tests", []):
                file, _, name = node.partition("::")
                text = (REPO / file).read_text(encoding="utf-8")
                assert f"def {name}(" in text, f"{rule['id']}: {node} does not exist"


def test_mapping_is_deterministic(map_golden, v1, golden_pairs):
    for pair_id in sorted(golden_pairs):
        first = map_golden(pair_id)
        again = v1.map(first.raw, golden_pairs[pair_id].corpus_relpath)
        assert again.data == first.data, f"{pair_id}: AER bytes differ between two runs"


# ------------------------------------------------------------------------------------------------ engine assumptions
def test_engine_assumptions_are_cited(map_golden):
    """EF E.10 item 21: the tool runtime's acting for the agent and the checker inputs rest on asserted assumptions,
    cited as I twins so the engine's start_tool@1, delegation and checker usages fire into inference bundles."""
    catalogue = load_catalogue("agentdojo")
    auto, checker = catalogue.get("agentdojo.auto_execution_unverified@1"), catalogue.get("agentdojo.checker_inputs_unverified@1")
    assert auto is not None and auto.cls == "I" and auto.assumptions == ("apv:AutoExecution",)
    assert checker is not None and checker.cls == "I" and set(checker.assumptions) == {
        "apv:CheckerUsesOutput", "apv:CheckerUsesPreState", "apv:CheckerUsesPostState", "apv:CheckerUsesCallTrace"}
    assert all(v.status == "asserted" for v in (*auto.verification, *checker.verification))
    for pair_id in ("R04", "C06"):
        records = map_golden(pair_id).records
        env = next(r for r in records if r.get("id") == "env")
        assert env["evf"] == {"/on_behalf_of": "I"}
        assert "agentdojo.auto_execution_unverified@1#/on_behalf_of" in env["rule"]
        for j in (r for r in records if r.get("k") == "judgement"):
            cites = "agentdojo.checker_inputs_unverified@1#/inputs" in j["rule"]
            assert cites == (j["origin"] == "checker")
            assert (j.get("unk") == {"/inputs": "not_recorded"}) == cites
