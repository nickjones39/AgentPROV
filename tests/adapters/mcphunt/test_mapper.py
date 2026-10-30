"""The ``mcphunt.trace`` mapper on the committed MCPHunt fixtures and derived traces (docs/architecture D.21.3-D.21.8;
DECISIONS D-287..D-289). Assertions name ids, kinds, rules and counts; no fixture content is printed."""

from __future__ import annotations

import json

import jsonschema
import mcphunt_support as support

from agentprov.adapters.semantics_profiles import load_semantics_profile
from agentprov.aer.rules import RuleRegistry
from agentprov.aer.validate import validate_records
from agentprov.sem.validate import validate_sem_document
from agentprov.validate import validate_prov


def _rules(rec: dict) -> set[str]:
    return {r.split("#", 1)[0] for r in rec.get("rule", [])}


def _calls(m: support.Mapped) -> list[str]:
    return [f"{r['id']}#{k}" for r in m.of("message") for k, p in enumerate(r["parts"]) if p["t"] == "tool_call"]


def test_release_validation_sem_prov_and_determinism(mapped):
    reg = RuleRegistry.default()
    profile = load_semantics_profile("mcphunt.tools", support.SEM_VERSION)
    for crit, m in mapped.items():
        rep = validate_records([*m.doc.records, m.doc.seal], store=None, catalogues=reg, mode="release")
        assert not rep.findings, (crit, sorted({f.code for f in rep.findings}))
        assert not validate_sem_document(m.sem, m.doc, catalogues=reg, mode="release", profile=profile).findings, crit
        assert validate_prov(m.prov.prov_json, m.doc, sems=[m.sem]).failed() == [], crit
        assert support.map_trace(crit).data == m.data, crit
        assert m.header["unit"] == "agent_execution" and m.header["source_key"]["loc"] == {"p": f"/traces/{support.F()[crit]['index']}"}


def test_ext_matches_schema(mapped):
    schema = json.loads((support.REPO / "src/agentprov/adapters/mcphunt/ext.schema.json").read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    for crit, m in mapped.items():
        for rec in m.records:
            ext = rec.get("ext", {}).get("mcphunt")
            if ext is not None:
                assert list(validator.iter_errors(ext)) == [], (crit, rec["id"])


def test_header_and_task(mapped):
    m = mapped["main_benign_success"]
    task = m.header["task"]
    assert task["benchmark"] == "mcphunt" and task["environment"] == "benign" and task["defense_id"] is None
    assert m.header["unk"]["/task/attack_id"] == "not_applicable" and m.header["evf"]["/task/defense_id"] == "D"
    assert m.header["ext"]["mcphunt"]["split"] == "main"
    assert mapped["live_guard_arm"].header["task"]["defense_id"] == "taint_tracking"
    assert mapped["mitigation_detailed"].header["task"]["defense_id"] == "mitigation_prompt:detailed"
    system, user = m.get("m0"), m.get("m1")
    assert (system["role"], system["actor"], user["role"], user["actor"]) == ("system", "harness", "user", "user")
    assert "mcphunt.system_prompt_by_harness_unverified@1" in _rules(system)
    assert user["ext"]["mcphunt"]["task_prompt_copy"] is True and "mcphunt.task_prompt_differs" not in m.codes()
    assert "mcphunt.deposit_harness_unverified@1" in _rules(m.get("harness"))
    changed = support.modified("main_benign_success", lambda t: t.update(task_prompt=t["task_prompt"] + " (changed)"))
    assert "mcphunt.task_prompt_differs" in changed.codes()
    assert "mcphunt.user_is_task_unverified@1" in _rules(m.get("user"))


def test_runtime_actors_per_server(mapped):
    m = mapped["web_servers"]
    runtimes = {a["id"]: a for a in m.of("actor") if a["kind"] == "tool_runtime"}
    assert "srv_fetch" in runtimes and all(a["id"] == "srv_" + a["name"] for a in runtimes.values())
    for a in runtimes.values():
        assert a["code"]["dist"] and a["code"]["dist_version"] and a["evf"]["/code/dist"] == "I"
    for te in m.of("tool_execution"):
        assert te["actor"] in runtimes
    assert "mcphunt.model_identity_unverified@1" in _rules(m.get("agent"))

    def unknown(t: dict) -> None:
        t["events"][0]["server"] = "unknown"

    changed = support.modified("web_servers", unknown)
    assert "mcphunt.unknown_server" in changed.codes()
    assert changed.get("srv_unknown")["unk"]["/code"] == "not_recorded"


def test_turns_align_with_assistant_messages(mapped):
    for crit, m in mapped.items():
        calls = m.of("model_call")
        assistants = [r for r in m.of("message") if r["role"] == "assistant"]
        assert [a["generated_by"] for a in assistants] == [c["id"] for c in calls][: len(assistants)], crit
        assert all(a["evf"]["/generated_by"] == "D" for a in assistants), crit
        assert all(c["evf"]["/input"] == "I" and c["tools"] == "fx1" for c in calls), crit
        assert m.checks()["aer.acc.agent_calls_vs_assistant@1"]["verdict"] == "consistent", crit
    m = mapped["main_benign_success"]
    assert any(a.get("ext", {}).get("mcphunt", {}).get("wire_field") == "final_message" for a in m.of("message"))
    assert any(a.get("ext", {}).get("mcphunt", {}).get("empty_text") for a in m.of("message") if a["role"] == "assistant")

    def misalign(t: dict) -> None:
        t["turn_log"][0]["n_tool_calls"] += 1

    changed = support.modified("main_benign_success", misalign)
    assert "mcphunt.turn_misaligned" in changed.codes()
    assert all(a["evf"]["/generated_by"] == "I" for a in changed.of("message") if a["role"] == "assistant")


def test_calls_events_and_messages_link(mapped):
    for crit, m in mapped.items():
        calls = set(_calls(m))
        tes = {te["id"]: te for te in m.of("tool_execution")}
        results = [r for r in m.of("message") if r["parts"] and r["parts"][0]["t"] == "tool_result"]
        assert len(results) == len(tes) == len(calls), crit
        for msg in results:
            te = tes[msg["generated_by"]]
            assert msg["parts"][0]["responds_to"] == te["call"] and te["call"] in calls
            assert msg["evf"]["/parts/0/responds_to"] == "D" and te["evf"]["/call"] == "I"
            assert "mcphunt.event_pairs_call_unverified@1" in _rules(te) and "returned" in te
        checks = m.checks()
        assert all(checks[c]["verdict"] == "consistent" for c in ("aer.acc.tool_calls_dispatched@1",
                                                                  "aer.acc.tool_results_linked@1",
                                                                  "aer.acc.executions_have_results@1")), crit
    assert "mcphunt.result_truncated_in_message" in mapped["result_truncated"].codes()

    def differs(t: dict) -> None:
        tool = next(x for x in t["messages"] if x["role"] == "tool")
        tool["content"] = tool["content"] + " (changed)"

    assert "mcphunt.result_differs" in support.modified("main_benign_success", differs).codes()

    def rename(t: dict) -> None:
        t["events"][0]["tool"] = "something_else"

    conflict = support.modified("main_benign_success", rename)
    assert "call_result_link_conflict" in conflict.codes()


def test_unparsed_arguments_are_disclosed(mapped):
    m = mapped["args_unparsed"]
    assert "mcphunt.args_unparsed" in m.codes()
    unparsed = [te for te in m.of("tool_execution") if te.get("unk", {}).get("/args") == "ambiguous"]
    assert unparsed and all("args_raw" in te["ext"]["mcphunt"] for te in unparsed)


def test_canary_flags_are_the_withholding_basis(mapped):
    for crit, m in mapped.items():
        assert "mcphunt.canary_flagged" not in m.codes(), crit  # fixtures are canary-free by evidence
        assert all(te["ext"]["mcphunt"]["canary"] == {"in_args": False, "in_result": False, "visible_to_llm": False}
                   for te in m.of("tool_execution")), crit

    def flag(t: dict) -> None:
        t["events"][0]["canary_in_result"] = True
        t["events"][-1]["canary_in_args"] = True

    crit = next(c for c, m in mapped.items() if len(m.of("tool_execution")) >= 2)  # two distinct flagged events
    changed = support.modified(crit, flag)
    issues = [i for i in changed.issues if i["code"] == "mcphunt.canary_flagged"]
    assert len(issues) == 1  # one per trace: the RW-1 trigger
    tes = changed.of("tool_execution")
    assert issues[0]["rule"].startswith("mcphunt.canary_flagged@1") and issues[0]["ids"] == [tes[0]["id"], tes[-1]["id"]]
    assert issues[0]["detail"] == "2 canary-flagged event(s)"
    from agentprov.adapters.profiles import load_profile

    assert load_profile(support.PROFILE).family_table()["withhold_basis"] == "mcphunt.canary_flagged"


def test_guard_rewrite_is_a_modify_decision():
    def guard(t: dict) -> None:
        t["events"][0]["sanitized_args"] = {"redacted": True}
        t["events"][0]["taint_blocked"] = True
        t["events"][0]["taint_report"] = {"n": 1}

    m = support.modified("live_guard_arm", guard, sem=True, prov=True)
    (dc,) = m.of("decision")
    te = next(te for te in m.of("tool_execution") if te.get("authorised_by") == dc["id"])
    assert dc["verdict"] == "modify" and dc["actor"] == "def" and dc["subject"] == te["call"]
    assert te["args_effective"] == {"redacted": True} and "mcphunt.taint_guard_unverified@1" in _rules(dc)
    assert m.get("def")["kind"] == "defense"
    assert validate_prov(m.prov.prov_json, m.doc, sems=[m.sem]).failed() == []


def test_times_are_kept_raw(mapped):
    for crit, m in mapped.items():
        run = m.get("run")
        assert run["t"]["raw"]["end"] and run["unk"]["/t/end"] == "ambiguous" and "end" not in run["t"], crit
        assert "mcphunt.collection_time_unverified@1" in _rules(run)
        for te in m.of("tool_execution"):
            assert "t" not in te and te["unk"]["/t/start"] == "ambiguous" and "timestamp" in te["ext"]["mcphunt"]
    statuses = {crit: mapped[crit].get("run").get("status") for crit in ("main_benign_success", "main_turn_cap",
                                                                         "main_error_finish", "main_length_finish")}
    assert statuses == {"main_benign_success": "ok", "main_turn_cap": "limit", "main_error_finish": "error",
                        "main_length_finish": "limit"}
    assert "mcphunt.run_end_unverified@1" in _rules(mapped["main_turn_cap"].get("run"))
    assert "mcphunt.duration_no_clock@1" in _rules(mapped["main_turn_cap"].get("run"))


def test_counters_check(mapped):
    for crit, m in mapped.items():
        assert m.checks()["mcphunt.acc.counters@1"]["verdict"] == "consistent", crit
    changed = support.modified("main_benign_success", lambda t: t.update(num_events=t["num_events"] + 1))
    assert changed.checks()["mcphunt.acc.counters@1"]["verdict"] == "inconsistent"


def test_an_unreadable_document_is_one_degenerate_execution():
    from agentprov.adapters.runner import aer_bytes, map_artefact_total
    from agentprov.adapters.types import Origin
    from agentprov.aer.reader import load_aer_bytes

    spec = support.F()["main_benign_success"]
    data = (support.FIXTURES / spec["fixture_file"]).read_bytes()[:-2]  # truncated: not valid JSON
    origin = Origin.from_json({"kind": "hf", "repo": "lihaonan0716/mcphunt-agent-traces", "revision": support.REVISION,
                               "path": "main/truncated.json"})
    outcome, _unit = map_artefact_total(data, origin, profile_id=support.PROFILE)
    assert outcome.degenerate
    doc = load_aer_bytes(aer_bytes(outcome)[0])
    assert doc.header["task"]["task_id"] == "document:main/truncated.json"
    issue = next(i for i in doc.seal["issues"] if i["code"] == "unparseable_artefact")
    assert issue["rule"].startswith("mcphunt.unreadable_document@1")


def test_judgements(mapped):
    m = mapped["failing_tool"]
    by_name = {j["name"]: j for j in m.of("judgement")}
    assert {"outcome", "task_completed", "any_risk", "strict_leakage", "data_flow_risk", "signals_fired"} <= set(by_name)
    assert all(j["origin"] == "checker" and j["by"] == "benchmark" for j in by_name.values())
    assert "mcphunt.labels_recorded_unverified@1" in _rules(by_name["outcome"])
    assert any(te["status"] == "error" for te in m.of("tool_execution"))
