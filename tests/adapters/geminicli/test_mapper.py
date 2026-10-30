"""The ``geminicli.stream_json`` mapper (docs/architecture D.23.3-D.23.7; D-332..D-337).

Facts about a fixture are computed from its bytes inside the test (never printed); derived inputs cover cases the
snapshot does not hold. Failures name ids, codes and criteria only."""

from __future__ import annotations

import json
from collections import Counter

import geminicli_support as support
import pytest

from agentprov.adapters.geminicli.dialect import STREAM, VERDICT
from agentprov.adapters.runner import NotOfDialect

D = support.by_criterion


def _verdict(m: support.Mapped) -> dict:
    return json.loads(support.file_bytes(f"{m.directory}/{VERDICT}"))


def _meta(m: support.Mapped) -> dict:
    return json.loads(support.file_bytes(f"{m.directory}/gemini_meta.json"))


def _check(m: support.Mapped, cid: str = "geminicli.acc.counters@1") -> dict:
    (check,) = [c for c in m.doc.seal["accounting"]["checks"] if c["id"] == cid]
    return check


def _blocks(items: list[dict]) -> list[list[dict]]:
    blocks: list[list[dict]] = []
    current: list[dict] = []
    for e in items[1:]:
        if (e["type"] == "message" and e.get("role") == "assistant") or e["type"] == "tool_use":
            current.append(e)
            continue
        if current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    return blocks


def test_header_task_and_facets(mapped):
    for crit, m in mapped.items():
        facets = m.header["ext"]["geminicli"]["label_facets"]
        assert m.header["task"] == {"benchmark": "code-agent-misalignment", "suite": facets["skeleton"],
                                    "task_id": facets["mutation"]}, crit
        assert m.header["unk"]["/task/attack_id"] == "not_recorded" and m.header["unit"] == "agent_execution"
        assert "geminicli.label_field_mismatch" not in m.codes(), crit
        assert m.header["ext"]["geminicli"]["session_id"] == support.events(m.directory)[0]["session_id"]


def test_label_field_mismatch_is_recorded():
    d = D("ok_with_text_and_calls")
    verdict = json.loads(support.file_bytes(f"{d}/{VERDICT}"))
    verdict["mutation_id"] = "SK-OTHER__m99"
    m = support.modified("ok_with_text_and_calls", aux={VERDICT: json.dumps(verdict).encode()})
    assert [i["detail"] for i in m.issues if i["code"] == "geminicli.label_field_mismatch"] == ["mutation_id"]


def test_sidecars_are_named_supporting_artefacts(mapped):
    for crit, m in mapped.items():
        sidecars = m.header["ext"]["geminicli"]["sidecars"]
        _primary, plan = support.plan(m.directory, {**support.files_of(m.directory), "RESULTS_build/manifest.csv": b""})
        assert set(sidecars) == set(plan), crit
        arts = {a["id"]: a for a in m.header["artifacts"]}
        assert len({a["sha256"] for a in arts.values()}) == len(arts), crit  # one entry per distinct raw object
        assert all(aid in arts and arts[aid]["role"] == "supporting" for aid in sidecars.values()), crit
        assert arts["a0"]["role"] == "primary"


def test_manifest_cross_check(mapped):
    for crit, m in mapped.items():
        assert m.header["ext"]["geminicli"]["manifest"] == {"status": "agrees"}, crit
    d = D("ok_with_text_and_calls")
    verdict = json.loads(support.file_bytes(f"{d}/{VERDICT}"))
    differs = support.modified("ok_with_text_and_calls",
                               aux={"RESULTS_build/manifest.csv": support.manifest_for(d, elicited=int(not verdict["elicited"]))})
    assert differs.header["ext"]["geminicli"]["manifest"] == {"status": "differs", "fields": ["elicited"]}
    assert "geminicli.manifest_differs" in differs.codes()
    other = support.manifest_for(d, mutation_id="SK-OTHER__m99")
    assert support.modified("ok_with_text_and_calls", aux={"RESULTS_build/manifest.csv": other}).header["ext"]["geminicli"][
        "manifest"] == {"status": "not_listed"}
    missing = support.modified("ok_with_text_and_calls", aux={"RESULTS_build/manifest.csv": None})
    assert missing.header["ext"]["geminicli"]["manifest"] == {"status": "missing"}


def test_counters_check(mapped):
    assert _check(mapped["ok_with_text_and_calls"])["verdict"] == "consistent"
    sub = _check(mapped["subagent_counter_differs"])
    assert (sub["verdict"], sub["reason"]) == ("unverifiable", "subagent_calls_not_logged")
    aborted = _check(mapped["aborted_after_result"])
    assert (aborted["verdict"], aborted["reason"]) == ("unverifiable", "no_result_event")

    def more_calls(items):
        for e in items:
            if e["type"] == "result":
                e["stats"]["tool_calls"] += 5

    bad = _check(support.modified("ok_with_text_and_calls", more_calls))
    assert (bad["verdict"], bad["reason"]) == ("inconsistent", "tool_calls_differ_from_stream")


def test_run_status_from_result_or_exit_code(mapped):
    def status(m):
        return m.get("run").get("status")

    assert status(mapped["ok_with_text_and_calls"]) == "ok"
    err = mapped["error_result"]
    assert status(err) == "error" and {"geminicli.cli_error_result", "incomplete_run"} <= set(err.codes())
    for crit in ("aborted_after_result", "aborted_unanswered_call"):
        m = mapped[crit]
        assert status(m) == "aborted" and _meta(m)["exit_code"] == 143, crit
        assert {"geminicli.no_result_event", "incomplete_run"} <= set(m.codes()), crit
        assert m.get("run")["evf"]["/status"] == "I"
    exit0 = support.modified("aborted_after_result", aux={"gemini_meta.json": b'{"exit_code": 0, "elapsed_sec": 1}'})
    assert "status" not in exit0.get("run") and exit0.get("run")["unk"]["/status"] == "not_recorded"


def test_tool_id_links_results_to_calls(mapped):
    for crit, m in mapped.items():
        items = support.events(m.directory)
        results = [e for e in items if e["type"] == "tool_result"]
        executions = m.of("tool_execution")
        assert len(executions) == len(results), crit
        uses = {e["tool_id"]: e for e in items if e["type"] == "tool_use"}
        for te, result in zip(executions, results, strict=True):
            tool_id = te["ext"]["geminicli"]["tool_id"]
            assert tool_id == result["tool_id"] and te["name"] == uses[tool_id]["tool_name"], crit
            message_id, k = te["call"].split("#")
            calls = m.get(message_id)["ext"]["geminicli"]["calls"]
            assert next(c for c in calls if c["part"] == int(k))["tool_id"] == tool_id, crit
            assert te["status"] == {"success": "ok", "error": "error"}[result["status"]] and te["evf"]["/status"] == "D"
            if "error" in result:
                assert te["ext"]["geminicli"]["error"] == result["error"]
        for msg in (r for r in m.of("message") if r["role"] == "tool"):
            te = m.get(msg["generated_by"])
            assert msg["parts"][0]["responds_to"] == te["call"], crit
    no_output = mapped["success_without_output"]
    empty = [msg for msg in no_output.of("message") if msg["role"] == "tool" and msg["parts"][0]["text"] is None]
    assert empty and all(msg["unk"]["/parts/0/text"] == "ambiguous" for msg in empty)


def test_verdict_meta_disagreement(mapped):
    for crit, m in mapped.items():
        differs = _verdict(m)["exit_code"] != _meta(m)["exit_code"]
        assert ("geminicli.verdict_meta_disagree" in m.codes()) == differs, crit
        assert m.header["ext"]["geminicli"]["verdict"] == _verdict(m)  # never corrected


def test_model_identity_is_the_cell_model(mapped):
    seen = set()
    for crit, m in mapped.items():
        agent = m.get("agent")
        verdict = _verdict(m)
        assert agent["model"] == {"requested": verdict["model"]} and agent["evf"]["/model"] == "I", crit
        assert agent["unk"]["/model/served"] == "not_recorded" and agent["name"] == verdict["sut_id"]
        cli = support.events(m.directory)[0]["model"]
        assert m.header["ext"]["geminicli"]["cli_model"] == cli
        assert ("geminicli.cli_model_alias" in m.codes()) == (cli != verdict["model"]), crit
        seen.add(verdict["model"])
    assert len(seen) == 5  # one fixture per cell at least


def test_actors(mapped):
    for crit, m in mapped.items():
        actors = {r["id"]: r for r in m.of("actor")}
        assert {"bench", "harness", "user", "agent", "detector"} <= set(actors), crit
        assert actors["user"]["kind"] == "simulated_user" and actors["agent"]["on_behalf_of"] == "user"
        has_results = any(e["type"] == "tool_result" for e in support.events(m.directory))
        assert ("env" in actors) == has_results, crit
        (user,) = [r for r in m.of("message") if r["role"] == "user"]
        assert user["actor"] == "user" and user["evf"]["/actor"] == "I"


def test_unanswered_last_call(mapped):
    m = mapped["aborted_unanswered_call"]
    items = support.events(m.directory)
    assert items[-1]["type"] == "tool_use"
    (issue,) = [i for i in m.issues if i["code"] == "missing_tool_result"]
    (part,) = issue["ids"]
    assert part not in {te["call"] for te in m.of("tool_execution")}
    message_id, k = part.split("#")
    calls = m.get(message_id)["ext"]["geminicli"]["calls"]
    assert next(c for c in calls if c["part"] == int(k))["tool_id"] == items[-1]["tool_id"]


def test_orphan_result_and_unmapped_event():
    def odd(items):
        tail = items.pop()  # the result event
        items.append({"type": "tool_result", "timestamp": tail["timestamp"], "tool_id": "x-0-orphan", "status": "success",
                      "output": "o"})
        items.append({"type": "checkpoint", "timestamp": tail["timestamp"]})
        items.append({"type": "message", "timestamp": tail["timestamp"], "role": "user", "content": "again"})
        items.append(tail)
        items.append({"type": "message", "timestamp": tail["timestamp"], "role": "assistant", "content": "late",
                      "delta": True})

    m = support.modified("ok_with_text_and_calls", odd)
    codes = set(m.codes())
    assert {"orphan_tool_result", "geminicli.unmapped_event", "unattributed_additional_user_message",
            "geminicli.events_after_result"} <= codes
    (activity,) = [r for r in m.of("activity") if r["type"] == "geminicli:unmapped_event"]
    (payload,) = [r for r in m.of("artefact") if r["generated_by"] == activity["id"]]
    assert payload["content"]["type"] == "checkpoint"
    orphan = [r for r in m.of("message") if r["role"] == "tool" and "generated_by" not in r]
    assert len(orphan) == 1 and orphan[0]["unk"]["/parts/0/responds_to"] == "ambiguous"
    unparseable = support.modified("ok_with_text_and_calls", aux={VERDICT: b"{"})
    assert {"geminicli.sidecar_unparseable", "geminicli.sidecar_missing", "no_outcome_recorded"} <= set(unparseable.codes())

    def repeated(items):
        use = next(e for e in items if e["type"] == "tool_use")
        items.insert(items.index(use) + 1, dict(use))

    conflict = support.modified("ok_with_text_and_calls", repeated)
    assert "call_result_link_conflict" in conflict.codes()


def test_blocks_become_model_calls_and_messages(mapped):
    for crit, m in mapped.items():
        blocks = _blocks(support.events(m.directory))
        calls = m.of("model_call")
        assert len(calls) == len(blocks), crit
        for mc, block in zip(calls, blocks, strict=True):
            (msg,) = [r for r in m.of("message") if r.get("generated_by") == mc["id"]]
            assert msg["role"] == "assistant" and mc["ev"] == "I" and mc["status"] == "kept", crit
            text = "".join(e["content"] for e in block if e["type"] == "message")
            texts = "".join(p["text"] for p in msg["parts"] if p["t"] == "text")
            assert texts == text, crit
            names = [p["name"] for p in msg["parts"] if p["t"] == "tool_call"]
            assert names == [e["tool_name"] for e in block if e["type"] == "tool_use"], crit
            assert len(msg["ext"]["geminicli"].get("chunks", [])) == sum(e["type"] == "message" for e in block)
            assert all(k in mc["unk"] for k in ("/usage", "/served_model", "/t"))
        inputs = [mc["input"] for mc in calls]
        assert all(set(a) <= set(b) for a, b in zip(inputs, inputs[1:], strict=False)), crit  # logged prefix grows


def test_times_stay_raw(mapped):
    for crit, m in mapped.items():
        items = support.events(m.directory)
        run = m.get("run")
        assert run["t"]["raw"] == {"start": items[0]["timestamp"], "end": items[-1]["timestamp"]}, crit
        assert run["unk"]["/t/start"] == run["unk"]["/t/end"] == "ambiguous"
        stamps = {e["tool_id"]: e["timestamp"] for e in items if e["type"] == "tool_use"}
        ends = {e["tool_id"]: e["timestamp"] for e in items if e["type"] == "tool_result"}
        for te in m.of("tool_execution"):
            tid = te["ext"]["geminicli"]["tool_id"]
            assert te["t"]["raw"] == {"start": stamps[tid], "end": ends[tid]} and "start" not in te["t"], crit
            assert te["unk"]["/t/start"] == "ambiguous"
        assert all("t" not in r for r in m.of("message"))


def test_judgements_from_the_verdict(mapped):
    for crit, m in mapped.items():
        verdict = _verdict(m)
        judgements = {j["name"]: j for j in m.of("judgement")}
        assert set(judgements) == {"elicited", "n_misaligned"}, crit
        for name, j in judgements.items():
            assert j["value"] == verdict[name] and j["actor"] == "detector" and j["origin"] == "checker", crit
            assert j["evf"]["/origin"] == "I"
    assert any(_verdict(m)["elicited"] for m in mapped.values())
    dropped = support.modified("ok_with_text_and_calls", aux={VERDICT: None})
    assert {"no_outcome_recorded", "geminicli.sidecar_missing"} <= set(dropped.codes()) and not dropped.of("judgement")
    assert dropped.get("agent")["unk"]["/model/requested"] == "ambiguous"


def test_cli_notice_is_an_activity(mapped):
    m = mapped["ok_with_text_and_calls"]  # also the cli_notice criterion
    notices = [e for e in support.events(m.directory) if e["type"] == "error"]
    activities = [r for r in m.of("activity") if r["type"] == "geminicli:cli_notice"]
    assert notices and len(activities) == len(notices)
    for ac, e in zip(activities, notices, strict=True):
        (text,) = [r for r in m.of("artefact") if r["generated_by"] == ac["id"]]
        assert text["type"] == "geminicli:notice_text" and text["content"] == e["message"]
        assert ac["ext"]["geminicli"]["severity"] == e["severity"] and ac["actor"] == "harness"
    assert Counter(m.codes())["geminicli.cli_notice"] == len(notices)


def test_subagent_tool_is_disclosed(mapped):
    m = mapped["subagent_counter_differs"]
    subagents = [te["id"] for te in m.of("tool_execution") if te["name"] == "codebase_investigator"]
    flagged = [i["ids"][0] for i in m.issues if i["code"] == "geminicli.subagent_internals_unobserved"]
    assert subagents and flagged == subagents
    assert not [s for s in m.of("scope") if s["kind"] == "subagent"]  # no sub-agent scope is invented


def test_environment_seed_fixture(mapped):
    for crit, m in mapped.items():
        (fx,) = m.of("fixture")
        assert fx["kind"] == "environment_seed" and fx["ev"] == "I" and fx["evf"]["/content"] == "O", crit
        assert fx["content"] == json.loads(support.file_bytes(f"{m.directory}/fs_before.json"))


def test_non_streams_are_not_of_the_dialect():
    for crit, detail in (("empty_stream", "geminicli.empty_stream"), ("no_stream_with_harness_events", "geminicli.no_stream")):
        d = D(crit)
        with pytest.raises(NotOfDialect) as info:
            support.map_files(d, support.files_of(d))
        assert info.value.detail == detail, crit
    assert not support.has(f"{D('no_stream_with_harness_events')}/{STREAM}")


def test_every_fixture_validates_and_ext_follows_its_schema(mapped):
    import jsonschema

    from agentprov.aer.rules import RuleRegistry
    from agentprov.aer.validate import validate_records

    schema = json.loads((support.REPO / "src" / "agentprov" / "adapters" / "geminicli" / "ext.schema.json").read_bytes())
    validator = jsonschema.Draft202012Validator(schema)
    for crit, m in mapped.items():
        for mode in ("dev", "release"):
            report = validate_records([*m.doc.records, m.doc.seal], store=None, catalogues=RuleRegistry.default(), mode=mode)
            assert report.ok, (crit, mode, [f.code for f in report.findings][:5])
        for rec in m.records:
            ext = rec.get("ext", {}).get("geminicli")
            if ext is not None:
                assert list(validator.iter_errors(ext)) == [], (crit, rec["id"])


def test_mapping_is_deterministic():
    d = D("subagent_counter_differs")
    assert support.map_dir(d).data == support.map_dir(d).data


def test_prov_and_sem_validate(mapped):
    from agentprov.adapters.semantics_profiles import load_semantics_profile
    from agentprov.aer.rules import RuleRegistry
    from agentprov.sem.validate import validate_sem_document
    from agentprov.validate import validate_prov

    profile = load_semantics_profile("geminicli.tools", 1)
    for crit, m in mapped.items():
        sem = validate_sem_document(m.sem, m.doc, catalogues=RuleRegistry.default(), mode="release", profile=profile)
        assert sem.ok, (crit, [f.code for f in sem.findings][:5])
        assert validate_prov(m.prov.prov_json, m.doc, sems=[m.sem]).failed() == [], crit
