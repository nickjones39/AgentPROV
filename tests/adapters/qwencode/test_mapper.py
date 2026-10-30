"""The ``qwencode.json`` mapper (docs/architecture D.24.3-D.24.6; D-572..D-577). Facts are computed from the fixture
bytes inside the test (never printed); derived inputs cover cases the snapshot does not hold."""

from __future__ import annotations

import json

import pytest
import qwencode_support as support

from agentprov.adapters.qwencode.dialect import parse_label
from agentprov.adapters.runner import NotOfDialect

C = support.by_criterion


def _check(m: support.Mapped, cid: str) -> dict:
    (check,) = [c for c in m.doc.seal["accounting"]["checks"] if c["id"] == cid]
    return check


def _blocks(msgs: list[dict]) -> list[list[dict]]:
    out, cur = [], []
    for m in msgs:
        if m["type"] == "assistant":
            cur.append(m)
            continue
        if cur:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def _score(label: str) -> dict:
    f = parse_label(label)
    assert f is not None
    member = f"results/Qwen/{f.model}/{f.target}/{f.language}/conversation_log/index{f.scenario}.json"
    return next(e for e in json.loads(support.tree()[1][member]) if e["index"] == f.case_key)


def test_header_task_and_request_type(mapped):
    for crit, m in mapped.items():
        f = parse_label(m.label)
        assert f is not None
        assert m.header["task"] == {"benchmark": "redcode-exec", "suite": f.language, "task_id": f.case_key,
                                    "attack_id": {"S1": "C1", "S2": "C2", "S3": "C3"}[f.target]}, crit
        assert m.header["evf"]["/task/attack_id"] == "D" and m.header["unk"]["/task/defense_id"] == "not_recorded"
        assert m.header["ext"]["qwencode"]["label_facets"]["file"] == f.file
        assert m.header["ext"]["qwencode"]["init"]["qwen_code_version"].startswith("0.21.")


def test_actors_and_model(mapped):
    for crit, m in mapped.items():
        actors = {r["id"]: r for r in m.of("actor")}
        init = support.messages(m.label)[0] if crit != "truncated_capture" else None
        assert {"bench", "harness", "user", "agent", "redcode_qwen_scorer"} <= set(actors), crit
        assert actors["agent"]["model"]["requested"] == m.header["ext"]["qwencode"]["init"]["model"]
        assert actors["agent"]["unk"]["/model/served"] == "not_recorded" and actors["agent"]["on_behalf_of"] == "user"
        assert actors["harness"]["version"] == m.header["ext"]["qwencode"]["init"]["qwen_code_version"]
        if init is not None:
            assert actors["agent"]["model"]["requested"] == init["model"]


def test_blocks_become_model_calls_and_messages(mapped):
    for crit, m in mapped.items():
        if crit == "truncated_capture":
            continue
        msgs = support.messages(m.label)
        blocks = _blocks(msgs)
        calls = m.of("model_call")
        assert len(calls) == len(blocks), crit
        for mc, block in zip(calls, blocks, strict=True):
            (msg,) = [r for r in m.of("message") if r.get("generated_by") == mc["id"]]
            content = [c for b in block for c in b["message"]["content"]]
            assert [p["t"] for p in msg["parts"]] == [{"text": "text", "tool_use": "tool_call"}[c["type"]] for c in content]
            for p, c in zip(msg["parts"], content, strict=True):
                if c["type"] == "tool_use":
                    assert (p["name"], p["args"], p["provider_call_id"]) == (c["name"], c["input"], c["id"]), crit
            assert len(msg["ext"]["qwencode"]["messages"]) == len(block)
            total = {k: sum(b["message"]["usage"][k] for b in block) for k in ("input_tokens", "output_tokens")}
            if any(total.values()):
                assert mc["usage"] == total and mc["evf"]["/usage"] == "D", crit
            else:
                assert mc["unk"]["/usage"] == "ambiguous"
            assert mc["ev"] == "I" and mc["unk"]["/t"] == "not_recorded"
    multi = mapped["multi_block_message"]
    assert any(len(e["ext"]["qwencode"]["messages"][0:1]) and len(r["parts"]) > 1 for r in multi.of("message")
               if r["role"] == "assistant" for e in [r])


def test_tool_use_ids_link_results(mapped):
    for crit, m in mapped.items():
        executions = {te["call"]: te for te in m.of("tool_execution")}
        for msg in (r for r in m.of("message") if r["role"] == "tool" and "generated_by" in r):
            te = m.get(msg["generated_by"])
            assert msg["parts"][0]["responds_to"] == te["call"], crit
            message_id, k = te["call"].split("#")
            part = m.get(message_id)["parts"][int(k)]
            assert part["provider_call_id"] == msg["ext"]["qwencode"]["tool_use_id"]
            assert te["status"] == ("error" if msg["ext"]["qwencode"]["is_error"] else "ok") and te["evf"]["/status"] == "D"
        assert len(executions) == len(m.of("tool_execution"))
    errors = [te for te in mapped["bash_suffix"].of("tool_execution") if te["status"] == "error"]
    assert errors  # the tool-error criterion lives in this run


def test_run_status_and_result(mapped):
    for crit, m in mapped.items():
        run = m.get("run")
        if crit == "truncated_capture":
            assert "status" not in run and run["unk"]["/status"] == "not_recorded"
            continue
        result = support.messages(m.label)[-1]
        assert run["status"] == "ok" and run["evf"]["/status"] == "D", crit
        assert run["ext"]["qwencode"]["duration_ms"] == result["duration_ms"]
        assert m.header["ext"]["qwencode"]["result"]["num_turns"] == result["num_turns"]
    error = support.modified("python", lambda ms: [*ms[:-1], {**ms[-1], "is_error": True, "subtype": "error_max_turns"}])
    assert error.get("run")["status"] == "error" and {"qwencode.error_result", "incomplete_run"} <= set(error.codes())


def test_result_stats_are_kept_verbatim(mapped):
    """NF-16 (regen item 122): the result message's ``stats`` (per-model and per-source request and token counts, per-tool
    counts) is kept verbatim in ``ext.qwencode.result`` (O, under the result message's locator), as the other result
    fields (D-572)."""
    seen = 0
    for crit, m in mapped.items():
        if crit == "truncated_capture":
            assert "result" not in m.header["ext"]["qwencode"]
            continue
        result = support.messages(m.label)[-1]
        assert "stats" in result, crit
        assert m.header["ext"]["qwencode"]["result"]["stats"] == result["stats"], crit
        assert "/ext/qwencode/result" not in m.header.get("evf", {}) and m.header["ev"] == "O"
        assert {"a": "a0", "p": f"/{len(support.messages(m.label)) - 1}"} in m.header["src"]
        seen += 1
    assert seen


def test_no_time_is_recorded(mapped):
    for crit, m in mapped.items():
        assert m.get("run")["unk"]["/t"] == "not_recorded", crit
        assert all("t" not in r for r in m.records if r.get("k") in ("message", "model_call", "tool_execution"))


def test_prompt_and_rules_fixtures(mapped):
    for crit, m in mapped.items():
        fixtures = {f["kind"]: f for f in m.of("fixture")}
        f = parse_label(m.label)
        assert f is not None
        prompt = fixtures["task_prompt"]
        assert prompt["ev"] == "I" and prompt["evf"]["/content"] == "O", crit
        assert prompt["ext"]["qwencode"]["request"]["source"] == ("dataset" if f.target == "S1" else "prompt")
        rules = fixtures["other"]
        assert rules["subtype"] == "qwencode.execution_rules" and rules["ext"]["qwencode"]["placed_as"] == "/app/QWEN.md"
        assert rules["content"] == support.tree()[1]["OH_evaluation/execution_rules.md"].decode()
        assert "qwencode.user_message_not_logged" in m.codes()


def test_score_judgement(mapped):
    seen = set()
    for crit, m in mapped.items():
        (j,) = m.of("judgement")
        score = _score(m.label)
        assert j["name"] == "score" and j["value"] == score["score"] and j["actor"] == "redcode_qwen_scorer", crit
        assert j["ext"]["qwencode"]["judge"]["step_count"] == score["step_count"]
        if score["score"] == 1:
            assert j["unk"]["/origin"] == "ambiguous"
        else:
            assert j["origin"] == "checker" and j["evf"]["/origin"] == "I"
        seen.add(score["score"])
    assert {0, 1, 3} <= seen


def test_checks(mapped):
    for crit, m in mapped.items():
        turns = _check(m, "qwencode.acc.turns@1")
        if crit == "truncated_capture":
            assert turns["verdict"] == "unverifiable" and turns["reason"] == "no_result_message"
            continue
        assert turns["verdict"] == "consistent", crit
        assert m.header["ext"]["qwencode"]["final_text"] == "equals_last_text"
    usage = _check(mapped["refused_score_0"], "qwencode.acc.usage@1")  # the usage-above-logged criterion's run
    assert (usage["verdict"], usage["reason"]) == ("unverifiable", "calls_not_logged")

    def below(ms):
        ms[-1]["usage"]["output_tokens"] = 0
        ms[-1]["result"] = "something else"

    derived = support.modified("python", below)
    assert _check(derived, "qwencode.acc.usage@1")["verdict"] in ("inconsistent", "consistent")
    assert derived.header["ext"]["qwencode"]["final_text"] == "differs" and "qwencode.final_text_differs" in derived.codes()

    def more_turns(ms):
        ms[-1]["num_turns"] += 1

    assert _check(support.modified("python", more_turns), "qwencode.acc.turns@1")["verdict"] == "inconsistent"


def test_truncated_output_is_salvaged(mapped):
    m = mapped["truncated_capture"]
    salvage = m.header["ext"]["qwencode"]["salvage"]
    assert salvage["size"] == 65536 and salvage["kept_bytes"] + salvage["dropped_bytes"] == 65536
    assert {"qwencode.truncated_capture", "qwencode.no_result_message", "incomplete_run"} <= set(m.codes())
    assert m.header["evf"]["/ext/qwencode/salvage"] == "D"


def test_sidecars(mapped):
    for crit, m in mapped.items():
        sidecars = m.header["ext"]["qwencode"]["sidecars"]
        plan = support.plan(m.label, *support.tree())
        assert set(sidecars) == set(plan), crit
        arts = {a["id"]: a for a in m.header["artifacts"]}
        assert len({a["sha256"] for a in arts.values()}) == len(arts)
        assert all(arts[aid]["role"] == "supporting" for aid in sidecars.values())
    assert any("api_sample" in m.header["ext"]["qwencode"]["sidecars"] for m in mapped.values())


def test_subagent_and_unmapped(mapped):
    m = mapped["subagent"]
    assert {"qwencode.subagent_event", "unattributed_additional_user_message"} <= set(m.codes())
    assert [r["type"] for r in m.of("activity")] and all(r["type"] == "qwencode:subagent_event" for r in m.of("activity"))

    def odd(ms):
        ms.insert(-1, {"type": "status", "x": 1})
        call = next(c for x in ms if x["type"] == "assistant" for c in x["message"]["content"] if c["type"] == "tool_use")
        ms.insert(-1, {"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": call["id"], "is_error": False, "content": "again"},
            {"type": "tool_result", "tool_use_id": "nope", "is_error": False, "content": "orphan"},
            {"type": "image", "data": "x"}]}})
        ms.insert(-1, {"type": "assistant", "message": {"id": "z", "role": "assistant", "model": "m", "stop_reason": None,
                                                       "usage": {"input_tokens": 0, "output_tokens": 0},
                                                       "content": [{"type": "thinking", "thinking": "t"}]}})

    derived = support.modified("python", odd)
    assert {"qwencode.unmapped_message", "orphan_tool_result", "call_result_link_conflict"} <= set(derived.codes())


def test_type_guards_on_tool_names_and_user_text():
    """NF-18 (regen item 124): a ``tool_use`` whose ``name`` is absent or not a string, and a user ``text`` block whose
    ``text`` is not a string, are recorded data problems, never ``str(None)`` or a write-gate failure: the block is kept
    verbatim as an ``other`` part (``qwencode.content_block``) with ``qwencode.unmapped_message``, so no call is invented
    and a result naming its id is an orphan whose link is ``ambiguous``."""
    from agentprov.aer.rules import RuleRegistry
    from agentprov.aer.validate import validate_records

    def first_call(ms):
        return next(c for m in ms if m["type"] == "assistant" for c in m["message"]["content"] if c["type"] == "tool_use")

    for name, change in (("5", lambda c: c.__setitem__("name", 5)), ("list", lambda c: c.__setitem__("name", ["x"])),
                         ("null", lambda c: c.__setitem__("name", None)), ("absent", lambda c: c.pop("name"))):
        kept: dict = {}

        def edit(ms, change=change, kept=kept):
            call = first_call(ms)
            change(call)
            kept.update(call)

        m = support.modified("python", edit)
        assert not m.outcome.degenerate and "adapter_defect" not in m.codes(), name
        parts = [p for r in m.of("message") for p in r["parts"]]
        assert {"t": "other", "type": "qwencode.content_block", "value": kept} in parts, name
        assert all(p.get("name") not in ("None", "5", "['x']") for p in parts), name
        assert kept["id"] not in {te["call"] for te in m.of("tool_execution")}
        assert {"qwencode.unmapped_message", "orphan_tool_result"} <= set(m.codes()), name
        report = validate_records([*m.doc.records, m.doc.seal], store=None, catalogues=RuleRegistry.default(), mode="release")
        assert report.ok, (name, [f.code for f in report.findings][:5])

    def user_text(ms):
        ms.insert(-1, {"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": 7}]},
                       "parent_tool_use_id": None})

    m = support.modified("python", user_text)
    assert not m.outcome.degenerate and "qwencode.unmapped_message" in m.codes()
    (user,) = [r for r in m.of("message") if r["role"] == "user"]
    assert user["parts"] == [{"t": "other", "type": "qwencode.content_block", "value": {"type": "text", "text": 7}}]


def test_joins_missing_or_ambiguous():
    f = parse_label(C("python"))
    assert f is not None
    score_member = f"results/Qwen/{f.model}/{f.target}/{f.language}/conversation_log/index{f.scenario}.json"
    entries = json.loads(support.tree()[1][score_member])
    doubled = json.dumps(entries + [e for e in entries if e["index"] == f.case_key]).encode()
    m = support.modified("python", supp={score_member: doubled})
    assert "qwencode.join_unverified" in m.codes() and not m.of("judgement") and "no_outcome_recorded" in m.codes()
    gone = support.modified("python", supp={score_member: None, "OH_evaluation/execution_rules.md": None})
    assert "qwencode.sidecar_missing" in gone.codes() and "other" not in {x["kind"] for x in gone.of("fixture")}
    bad = support.modified("python", supp={score_member: b"{"})
    assert "qwencode.sidecar_missing" in bad.codes()


def test_empty_output_is_not_an_execution():
    label = support.by_criterion("empty_output")
    runs_files, supp_files = support.tree()
    assert runs_files[label] == b""
    with pytest.raises(NotOfDialect) as info:
        support.map_files(label, runs_files, supp_files)
    assert info.value.detail == "qwencode.empty_output"


def test_every_fixture_validates_and_ext_follows_its_schema(mapped):
    import jsonschema

    from agentprov.aer.rules import RuleRegistry
    from agentprov.aer.validate import validate_records

    schema = json.loads((support.REPO / "src" / "agentprov" / "adapters" / "qwencode" / "ext.schema.json").read_bytes())
    validator = jsonschema.Draft202012Validator(schema)
    for crit, m in mapped.items():
        for mode in ("dev", "release"):
            report = validate_records([*m.doc.records, m.doc.seal], store=None, catalogues=RuleRegistry.default(), mode=mode)
            assert report.ok, (crit, mode, [f.code for f in report.findings][:5])
        for rec in m.records:
            ext = rec.get("ext", {}).get("qwencode")
            if ext is not None:
                assert list(validator.iter_errors(ext)) == [], (crit, rec["id"])


def test_mapping_is_deterministic():
    label = C("subagent")
    assert support.map_run(label).data == support.map_run(label).data


def test_prov_and_sem_validate(mapped):
    from agentprov.adapters.semantics_profiles import load_semantics_profile
    from agentprov.aer.rules import RuleRegistry
    from agentprov.sem.validate import validate_sem_document
    from agentprov.validate import validate_prov

    profile = load_semantics_profile("qwencode.tools", 2)
    for crit, m in mapped.items():
        sem = validate_sem_document(m.sem, m.doc, catalogues=RuleRegistry.default(), mode="release", profile=profile)
        assert sem.ok, (crit, [f.code for f in sem.findings][:5])
        assert validate_prov(m.prov.prov_json, m.doc, sems=[m.sem]).failed() == [], crit


class _Store:
    """A raw store over the fixture bytes, by sha256 (what the corpus's raw store offers the locator resolver)."""

    def __init__(self) -> None:
        import hashlib

        runs_files, supp_files = support.tree()
        self.blobs = {hashlib.sha256(b).hexdigest(): b for b in (*runs_files.values(), *supp_files.values())}

    def has(self, sha256: str) -> bool:
        return sha256 in self.blobs

    def size(self, sha256: str) -> int:
        return len(self.blobs[sha256])

    def read_bytes(self, sha256: str) -> bytes:
        return self.blobs[sha256]


def test_every_locator_resolves_against_the_stored_bytes(mapped):
    """Evidence linkage (C.9.2): every source locator resolves against the stored member bytes. A salvaged output is not
    valid JSON as a whole, so its messages are cited as byte ranges (D-577); an array pointer would dangle."""
    from agentprov.aer.rules import RuleRegistry
    from agentprov.aer.validate import validate_records

    store = _Store()
    for crit, m in mapped.items():
        for mode in ("dev", "release"):
            report = validate_records([*m.doc.records, m.doc.seal], store=store, catalogues=RuleRegistry.default(), mode=mode)
            assert report.ok, (crit, mode, [f.code for f in report.findings][:5])
    cut = mapped["truncated_capture"]
    sources = [s for r in cut.records for s in r.get("src", []) if s.get("a") == "a0" and "o" not in s]
    assert sources and all("bytes" in s and not str(s.get("p", "")).startswith("/0") for s in sources)


def test_score_absent_or_off_scale():
    """NF-19 (regen item 125): a score record without ``score`` writes no judgement (a judgement's value is required, so
    the outcome is ``no_outcome_recorded``) and no locator to the missing key; a score that is not an integer of the
    scale 0, 1, 3 (a boolean included) is kept as logged and raises ``qwencode.score_unrecognised``; ``true`` never takes
    the score-1 path."""
    import hashlib

    from agentprov.aer.rules import RuleRegistry
    from agentprov.aer.validate import validate_records

    f = parse_label(C("python"))
    assert f is not None
    member = f"results/Qwen/{f.model}/{f.target}/{f.language}/conversation_log/index{f.scenario}.json"
    entries = json.loads(support.tree()[1][member])
    idx = next(i for i, e in enumerate(entries) if e["index"] == f.case_key)

    def mapped_with(change):
        es = json.loads(support.tree()[1][member])
        change(es[idx])
        raw = json.dumps(es).encode()
        m = support.modified("python", supp={member: raw})
        store = _Store()
        store.blobs[hashlib.sha256(raw).hexdigest()] = raw
        report = validate_records([*m.doc.records, m.doc.seal], store=store, catalogues=RuleRegistry.default(), mode="release")
        assert report.ok, [x.code for x in report.findings][:5]
        return m

    gone = mapped_with(lambda e: e.pop("score"))
    assert gone.of("judgement") == [] and "no_outcome_recorded" in gone.codes()
    assert not [s for r in gone.records for s in r.get("src", []) if str(s.get("p", "")).endswith("/score")]
    for value in (True, "3", 2, -1, 1.0):
        m = mapped_with(lambda e, value=value: e.__setitem__("score", value))
        (j,) = m.of("judgement")
        assert j["value"] == value and j["origin"] == "checker", value
        if isinstance(value, float):  # the logged float survives JCS as a lex hint (C.11.3)
            assert "/value" in j["ext"]["lex"]["flt"]
        else:
            assert type(j["value"]) is type(value), value
        assert "qwencode.score_unrecognised" in m.codes(), value
    for value in (0, 1, 3):
        m = mapped_with(lambda e, value=value: e.__setitem__("score", value))
        assert "qwencode.score_unrecognised" not in m.codes(), value


def test_judge_fields_of_a_record_without_a_score_are_kept():
    """Item 125 follow-up: a score record without ``score`` writes no judgement, but its other logged fields (index,
    step_count, exceeded_soft_iteration_cap, used_write_tool, timed_out, last_response_full) stay in the AER as logged
    data: the header's ``ext.qwencode.judge`` (values as logged; D by ``qwencode.score_join@1``, the join that names the
    record the run's), with a header source locator to the record. With a score they stay on the judgement only."""
    import hashlib

    from agentprov.aer.rules import RuleRegistry
    from agentprov.aer.validate import validate_records
    from agentprov.adapters.qwencode.mapper import _SCORE_EXT

    f = parse_label(C("python"))
    assert f is not None
    member = f"results/Qwen/{f.model}/{f.target}/{f.language}/conversation_log/index{f.scenario}.json"
    entries = json.loads(support.tree()[1][member])
    idx = next(i for i, e in enumerate(entries) if e["index"] == f.case_key)
    entries[idx].pop("score")
    raw = json.dumps(entries).encode()
    m = support.modified("python", supp={member: raw})
    assert m.of("judgement") == []
    kept = {k: entries[idx][k] for k in _SCORE_EXT if k in entries[idx]}
    assert len(kept) == len(_SCORE_EXT)  # the fixture's record logs every field
    ext = m.header["ext"]["qwencode"]
    assert ext["judge"] == kept
    assert {"a": ext["sidecars"]["score"], "p": f"/{idx}"} in m.header["src"]
    assert m.header["evf"]["/ext/qwencode/judge"] == "D"
    assert any(r.startswith("qwencode.score_join@1#") for r in m.header["rule"])
    store = _Store()
    store.blobs[hashlib.sha256(raw).hexdigest()] = raw
    report = validate_records([*m.doc.records, m.doc.seal], store=store, catalogues=RuleRegistry.default(), mode="release")
    assert report.ok, [x.code for x in report.findings][:5]
    scored = support.map_run(C("python"))
    (j,) = scored.of("judgement")
    assert "judge" in j["ext"]["qwencode"] and "judge" not in scored.header["ext"]["qwencode"]


def test_extra_result_and_undecodable_rules():
    """NF-20 (regen item 126): a second ``result`` message is kept verbatim as a harness activity with
    ``qwencode.extra_result_message`` (the run's status stays the first result's), and an ``execution_rules.md`` that is
    not UTF-8 raises ``qwencode.sidecar_missing`` (``rules: not UTF-8``) instead of passing silently."""
    from agentprov.aer.rules import RuleRegistry
    from agentprov.aer.validate import validate_records

    items = support.messages(C("python"))
    second = {**items[-1], "subtype": "error_max_turns", "is_error": True, "num_turns": 999}
    m = support.modified("python", lambda ms: [*ms, second])
    assert "qwencode.extra_result_message" in m.codes()
    assert m.get("run")["status"] == "ok" and m.header["ext"]["qwencode"]["result"]["num_turns"] == items[-1]["num_turns"]
    (af,) = [r for r in m.of("artefact") if r.get("content") == second]
    assert m.get(af["generated_by"])["type"] == "qwencode:unmapped_message"
    (issue,) = [i for i in m.issues if i["code"] == "qwencode.extra_result_message"]
    assert issue["rule"].startswith("qwencode.result_status@1") and issue["ids"] == [af["generated_by"]]
    report = validate_records([*m.doc.records, m.doc.seal], store=None, catalogues=RuleRegistry.default(), mode="release")
    assert report.ok, [f.code for f in report.findings][:5]

    bad = support.modified("python", supp={"OH_evaluation/execution_rules.md": b"rules \xff"})
    assert [i.get("detail") for i in bad.issues if i["code"] == "qwencode.sidecar_missing"] == ["rules: not UTF-8"]
    assert "other" not in {f["kind"] for f in bad.of("fixture")}
