"""The ``autogen.runs`` mapper (docs/architecture D.19.3-D.19.7; DECISIONS D-300..D-305).

The committed InjecAgent tool-block arm covers model calls, calls and results, blocks at the tool boundary, a call
rejected before its body and the attacker tools; the staged deposit (skipped when absent) covers the probe phases:
retried runs, the four entry points, bus blocks, the keyword guard and the selector. Nothing here prints source text.
"""

from __future__ import annotations

import json
from collections import Counter

import autogen_support as support
import pytest

from agentprov.aer.rules import RuleRegistry
from agentprov.aer.validate import validate_records

WITHHELD = "[content withheld by guard]"


def _staged(members, label_tail: str, pick, limit: int = 1) -> list[support.Mapped]:
    label = support.ROOT + "results/" + label_tail
    out = []
    for unit, aux in support.units(label, members):
        if pick(unit.primary.value):
            out.append(support.map_unit_of(unit, aux, sem=True, prov=True))
            if len(out) >= limit:
                break
    assert out, label_tail
    return out


# ------------------------------------------------------------------------------------------------ committed fixtures
def test_every_fixture_run_seals_and_validates_in_release_mode(tool_arm):
    assert len(tool_arm) == 20
    for rid, m in tool_arm.items():
        assert not m.outcome.degenerate, rid
        for mode in ("dev", "release"):
            report = validate_records([*m.doc.records, m.doc.seal], store=None, catalogues=RuleRegistry.default(), mode=mode)
            assert report.ok, (rid, mode, [f.code for f in report.findings][:5])
        assert m.doc.seal["accounting"]["status"] == "consistent", rid
        assert m.header["source_key"]["loc"] == {"line": m.line} and m.header["dialect"]["variant"] == "injecagent"


def test_model_calls_pair_by_request_seq(tool_arm):
    for rid, m in tool_arm.items():
        for mc in m.of("model_call"):
            assert mc["status"] == "kept" and mc["role"] == "agent" and mc["actor"] in ("researcher", "writer"), rid
            assert set(mc["usage"]) == {"input_tokens", "output_tokens"} and mc["unk"]["/served_model"] == "not_recorded"
            assert all(s["a"] == "a1" or s["a"] != "a0" for s in mc["src"])  # cited in the event log, not the run row
            assert "autogen.request_log_is_model_input_unverified@1#/input" in mc["rule"]
            assert all(m.get(i)["k"] == "message" for i in mc["input"])


def test_agent_messages_link_to_their_model_call(tool_arm):
    for rid, m in tool_arm.items():
        for msg in m.of("message"):
            if msg["actor"] in ("researcher", "writer"):
                assert msg["role"] == "assistant" and m.get(msg["generated_by"])["k"] == "model_call", (rid, msg["id"])
                assert msg["evf"]["/generated_by"] == "D", (rid, msg["id"])
    folded = [msg for m in tool_arm.values() for msg in m.of("message") if msg["parts"][0]["t"] == "reasoning"]
    assert folded and all(len(msg["parts"]) > 1 and "thought_message" in msg["ext"]["autogen"] for msg in folded)
    assert all(any(r.startswith("autogen.thought_equal@1#/parts/0") for r in msg["rule"]) for msg in folded)


def test_results_answer_their_calls(tool_arm):
    statuses: Counter[str] = Counter()
    for rid, m in tool_arm.items():
        parts = {f"{r['id']}#{k}": p for r in m.of("message") for k, p in enumerate(r["parts"])}
        for te in m.of("tool_execution"):
            statuses[te.get("status", "unk")] += 1
            call = parts[te["call"]]
            assert call["t"] == "tool_call" and call["name"] == te["name"] and te["args"] == call["args"], (rid, te["id"])
            assert te["evf"]["/call"] == "D" and json.loads(call["args_raw"]) == call["args"]
        for msg in m.of("message"):
            if msg["role"] == "tool":
                assert parts[msg["parts"][0]["responds_to"]]["t"] == "tool_call", (rid, msg["id"])
    assert statuses == Counter({"ok": 30, "invalid": 1})
    rejected = tool_arm["p6tool_ia07_1"]
    (te,) = [t for t in rejected.of("tool_execution") if t.get("status") == "invalid"]
    assert te["evf"]["/status"] == "I" and "autogen.tool_error_result" in rejected.codes()


def test_blocks_become_decisions(tool_arm):
    decisions = [(rid, d) for rid, m in tool_arm.items() for d in m.of("decision")]
    assert len(decisions) == 17
    for rid, dc in decisions:
        m = tool_arm[rid]
        assert dc["verdict"] == "modify" and dc["actor"] == "guard_llm" and m.get(dc["subject"])["k"] == "tool_execution"
        (out,) = [r for r in m.of("message") if r.get("generated_by") == dc["id"]]
        assert out["role"] == "tool" and out["parts"][0]["text"] == WITHHELD and out["actor"] == "guard_llm"
        assert dc["ev"] == "I" and dc["unk"]["/original"] == "overwritten"


def test_guard_judgements_join_by_digest(tool_arm):
    joined = unjoined = 0
    for m in tool_arm.values():
        for j in m.of("judgement"):
            g = j["ext"]["autogen"]["guard"]
            assert j["name"] == "injection_flag" and isinstance(j["value"], bool) and j["actor"] in ("guard_deberta", "guard_llm")
            if j["subject"] == "run":
                unjoined += 1
                assert j["unk"]["/subject"] == "ambiguous" and "candidates" in g
            else:
                joined += 1
                assert j["evf"]["/subject"] == "D"
            assert "verdict" in g and {"label"} <= set(g["verdict"])  # the guard log row of the same digest
    assert joined > 0 and unjoined < joined


def test_side_list_check(tool_arm):
    for rid, m in tool_arm.items():
        (check,) = [c for c in m.doc.seal["accounting"]["checks"] if c["id"] == "autogen.acc.side_list@1"]
        assert check["verdict"] == "consistent", rid


def test_identity_comes_from_the_config(tool_arm):
    m = tool_arm["p6tool_ia00_0"]
    for agent in ("researcher", "writer"):
        rec = m.get(agent)
        assert rec["kind"] == "llm_agent" and rec["model"] == {"requested": "qwen/qwen3.5-9b"} and rec["evf"]["/model"] == "I"
        assert rec["unk"]["/model/served"] == "not_recorded"
    harness = m.get("harness")
    assert harness["code"] == {"dist": "autogen-agentchat", "dist_version": "0.7.5"} and harness["evf"]["/code"] == "I"
    assert m.get("guard_deberta")["kind"] == "defense" and m.get("guard_llm")["model"] == {"requested": "qwen/qwen3.5-9b"}


def test_task_header(tool_arm):
    m = tool_arm["p6tool_ia00_0"]
    task = m.header["task"]
    row = support.units(support.TOOL_ARM, support.fixture_members())[m.line][0].primary.value
    assert task == {"benchmark": "autogen-guard-placement", "task_id": row["case_id"], "suite": "tool",
                    "environment": "phase6/tool", "attack_id": "injecagent", "defense_id": "block:tool:llm"}
    assert m.header["evf"]["/task/attack_id"] == "D" and m.header["evf"]["/task/defense_id"] == "I"
    assert m.get("run")["status"] in ("limit", "ok") and m.get("run")["evf"]["/status"] == "I"


def test_probe_join_and_fixtures(tool_arm):
    m = tool_arm["p6tool_ia01_1"]
    kinds = Counter((f["kind"], f.get("subtype")) for f in m.of("fixture"))
    assert kinds == Counter({("other", "autogen.probe_document"): 1, ("injection_payload", None): 1,
                             ("task_prompt", None): 1, ("system_prompt", None): 2})
    (payload,) = [f for f in m.of("fixture") if f["kind"] == "injection_payload"]
    assert payload["actor"] == "att" and payload["ext"]["autogen"]["in_document"] is True
    (task,) = [f for f in m.of("fixture") if f["kind"] == "task_prompt"]
    assert task["ext"]["autogen"]["checked_against"] == "task_message" and task["evf"]["/ext/autogen/checked_against"] == "D"


def test_attacker_tool_calls_are_claimed_in_sem(tool_arm):
    called = [a for m in tool_arm.values() for a in m.sem.annotations if a["type"] == "autogen.attacker_tool_called"]
    assert len(called) == 5 and all(a["ev"] == "D" for a in called)


def test_sem_and_prov_derive_for_every_fixture_run(tool_arm):
    for rid, m in tool_arm.items():
        assert m.sem is not None and m.prov is not None, rid


def test_mapping_is_deterministic(tool_arm):
    again = support.map_file(support.TOOL_ARM, support.fixture_members())
    assert {rid: m.data for rid, m in again.items()} == {rid: m.data for rid, m in tool_arm.items()}


def test_no_ext_key_shadows_a_core_slot(tool_arm):
    for m in tool_arm.values():
        for rec in m.records:
            assert not set(rec.get("ext", {}).get("autogen", {})) & {"t", "status", "input", "usage", "model"}, rec["id"]


# ------------------------------------------------------------------------------------------------ staged deposit
def test_the_last_attempt_is_mapped(staged):
    (m,) = _staged(staged, "phase2/runs.jsonl", lambda v: v["run_id"] == "p2_c03_matched_agent")
    assert m.header["ext"]["autogen"]["attempt"]["aborted_attempts"] == 1 and "autogen.aborted_attempt_events" in m.codes()
    assert m.doc.seal["accounting"]["status"] == "consistent"


def test_a_run_stopped_before_any_agent_is_outcome_only(staged):
    (m,) = _staged(staged, "phase10/runs.jsonl", lambda v: v["entry"] == "user" and v["condition"] == "observe")
    assert m.header["unit"] == "outcome_only" and m.of("model_call") == [] and "no_execution_observed" in m.codes()
    (kw,) = [a for a in m.sem.annotations if a["type"] == "autogen.keyword_stop"]
    assert kw["value"] == {"holds": True}


def test_ingest_turn(staged):
    (m,) = _staged(staged, "phase2/runs.jsonl", lambda v: v["entry"] == "agent")
    (msg,) = [r for r in m.of("message") if r["actor"] == "ingest"]
    assert msg["role"] == "assistant" and "generated_by" not in msg and msg["evf"]["/actor"] == "I"


def test_memory_entry(staged):
    (m,) = _staged(staged, "phase2/runs.jsonl", lambda v: v["entry"] == "memory")
    (ac,) = m.of("activity")
    (af,) = m.of("artefact")
    assert ac["type"] == "autogen:memory_query" and af["generated_by"] == ac["id"] and af["type"] == "autogen:memory_content"


def test_bus_block_of_the_task_names_the_guard(staged):
    runs = _staged(staged, "phase4/runs.jsonl", lambda v: v["entry"] == "user", limit=30)
    withheld = [m for m in runs for r in m.of("message") if r["role"] == "user" and r["parts"][0]["text"] == WITHHELD]
    assert withheld
    for m in withheld:
        (task,) = [r for r in m.of("message") if r["role"] == "user"]
        assert task["actor"] == "guard_llm" and task["unk"]["/generated_by"] == "not_recorded"
        assert "autogen.block_subject_not_recorded" in m.codes()


def test_the_keyword_guard_strips_rather_than_withholds(staged):
    runs = _staged(staged, "phase10/runs.jsonl", lambda v: v["condition"] == "block_tool", limit=10)
    decisions = [(m, d) for m in runs for d in m.of("decision")]
    assert decisions
    for m, dc in decisions:
        assert dc["actor"] == "guard_keyword" and m.get(dc["subject"])["k"] == "tool_execution"
        (out,) = [r for r in m.of("message") if r.get("generated_by") == dc["id"]]
        assert out["parts"][0]["text"] != WITHHELD  # the keyword is removed, the document stays


def test_selector_calls_are_auxiliary(staged):
    (m,) = _staged(staged, "phase13/runs.jsonl", lambda v: True)
    selector = [mc for mc in m.of("model_call") if mc["actor"] == "selector"]
    assert selector and all(mc["role"] == "auxiliary" and "selected" in mc["ext"]["autogen"] for mc in selector)
    assert m.doc.seal["accounting"]["status"] == "consistent"


@pytest.mark.slow
def test_every_staged_run_maps_and_validates(staged):
    units = kinds = 0
    issues: Counter[str] = Counter()
    for label in sorted(staged):
        if not label.endswith("/runs.jsonl") or any(f"phase{x}/" in label for x in (7, 8, 9)):
            continue
        for unit, aux in support.units(label, staged):
            m = support.map_unit_of(unit, aux)
            units += 1
            assert not m.outcome.degenerate
            report = validate_records([*m.doc.records, m.doc.seal], store=None, catalogues=RuleRegistry.default(),
                                      mode="release")
            assert report.ok, (m.run_id, [f.code for f in report.findings][:3])
            kinds += m.header["unit"] == "outcome_only"
            issues.update(m.codes())
    assert (units, kinds) == (1080, 40)
    assert "accounting_inconsistent" not in issues and issues["autogen.tool_error_result"] == 4


# ------------------------------------------------------------------------------------------------ the product path (D-301)
def test_the_product_path_maps_one_execution_per_run_row():
    """R-10n-3, closed by R-10k-1 (D-320): the reader declares ``multi_execution``, so the product path maps each run row
    as its own unit, with the per-unit inputs the reader names."""
    from agentprov.adapters.runner import map_artefact_units

    members = support.fixture_members()
    data, method = members[support.TOOL_ARM]
    rows, blobs = [], {}
    _unit, aux = support.units(support.TOOL_ARM, members)[0]
    for role, ref in sorted(_unit.auxiliary.items()):
        rows.append({"role": role, "label": ref.origin.data["label"], "sha256": ref.sha256, "size": ref.bytes,
                     "media": ref.media, "origin": ref.origin.to_json()})
        blobs[role] = aux[role]
    results = map_artefact_units(data, support._origin(support.TOOL_ARM, data, method), profile_id=support.PROFILE,
                                 media="application/jsonl", auxiliary=rows, auxiliary_bytes=blobs)
    assert len(results) == 20 and not any(outcome.degenerate for outcome, _unit in results)
    assert [u.primary.locator.line for _o, u in results] == list(range(20))
    assert len({outcome.ex for outcome, _unit in results}) == 20


def test_an_unmappable_row_seals_as_a_degenerate_aer():
    from agentprov.adapters.autogen.mapper import AutoGenMapper
    from agentprov.adapters.profiles import load_profile
    from agentprov.adapters.runner import MapContext, _degenerate, aer_bytes

    from agentprov.aer.ids import import_execution_id, mapping_id

    unit, _aux = support.units(support.TOOL_ARM, support.fixture_members())[3]
    profile = load_profile(support.PROFILE)
    mapping = mapping_id(AutoGenMapper.mapper_id, profile.id)
    ex = import_execution_id(mapping, unit.primary.artefact.sha256, unit.primary.locator.key())
    ctx = MapContext(profile, RuleRegistry.default(), mapping, ex, None)
    outcome = _degenerate(unit, AutoGenMapper(), ctx, "unparseable_artefact", "test")
    sealed, _info = aer_bytes(outcome)
    header = outcome.records[0]
    assert outcome.degenerate and header["task"]["task_id"] == unit.primary.value["case_id"]
    assert header["source_key"]["loc"] == {"line": 3} and sealed
