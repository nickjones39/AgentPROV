"""The results-container dialect of memo-ozdincer/agentdojo (phase 10q; D-470..D-479; docs/architecture D.6.20).

Two real containers are committed (``tests/fixtures/memo-ozdincer/``, MIT, no account path and no secret-like string,
D-478); every other case is a synthetic container built here, with a made-up workstation account (the D-185 pattern).
The containers hold prompt-injection payloads: nothing here prints them.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import zlib
from pathlib import Path
from typing import Any

import pytest
from agentdojo_support import Mapped

from agentprov.adapters.agentdojo import citation
from agentprov.adapters.agentdojo.mapper import TraceLoggerMapper
from agentprov.adapters.agentdojo.profile import check_against_schema, family_schema, family_table
from agentprov.adapters.agentdojo.redact import RULE, Redactor, parse_redact_rules, redact_value
from agentprov.adapters.agentdojo.results_mapper import container_table
from agentprov.adapters.agentdojo.results_reader import DIALECT_ID, ResultsContainerReader, row_variant
from agentprov.adapters.code_verification import TWIN_SUFFIX
from agentprov.adapters.profiles import load_profile, parse_profile
from agentprov.adapters.registry import get_source
from agentprov.adapters.runner import aer_bytes, map_unit
from agentprov.adapters.semantics_profiles import load_semantics_profile
from agentprov.adapters.types import ArtefactRef, ExecutionUnit, Origin
from agentprov.aer.reader import load_aer_bytes
from agentprov.aer.rules import RuleRegistry, load_catalogue
from agentprov.errors import ProfileError
from agentprov.ingest.limits import IngestLimits
from agentprov.prov.engine import derive
from agentprov.sem.engine import annotate
from agentprov.testing import golden

REPO = Path(__file__).resolve().parents[3]
FIXTURES = REPO / "tests" / "fixtures" / "memo-ozdincer"
PROFILE = "memo-ozdincer-agentdojo"
REPO_URL = "https://github.com/memo-ozdincer/agentdojo"
PIN = "7c331d978acca38534a3d42951f28a25ba26901b"
#: a made-up account (never a real one); the D-476 patterns match its structure, not the name
ACCOUNT = "zz" + "9acct"
CLUSTER_LLAMA = f"/scratch/{ACCOUNT}/proj/models/llama-70b"
MELON = "Potential prompt injection detected, stopping execution."


# ------------------------------------------------------------------------------------------------ builders
def _call(function: str, **args: Any) -> dict[str, Any]:
    return {"function": function, "args": args}


def row(**over: Any) -> dict[str, Any]:
    messages = [
        {"role": "system", "content": "You are a helpful and harmless bank assistant."},
        {"role": "user", "content": "Pay the bill."},
        {"role": "assistant", "content": "<function-call>[read_file(file_path='bill.txt')]</function-call>",
         "tool_calls": [_call("read_file", file_path="bill.txt")]},
        {"role": "tool", "content": "Bill: 98.70", "tool_call": _call("read_file", file_path="bill.txt"), "error": None},
        {"role": "assistant", "content": "Done."},
    ]
    base: dict[str, Any] = {"user_task_id": "user_task_0", "injection_task_id": "injection_task_1", "utility": True,
                            "security": False, "duration": 12.0, "messages": messages,
                            "classification": {"label": "benign", "tool_calls": ["read_file"], "n_tool_calls": 1,
                                               "is_harmful": False, "is_refusal": False, "has_attack_initiation": False}}
    base.update(over)
    return base


def container(rows: list[dict[str, Any]] | None = None, **over: Any) -> dict[str, Any]:
    rows = [row()] if rows is None else rows
    base: dict[str, Any] = {"label": "test", "suite": "banking", "adapter": None, "defense": None, "attack": "tool_knowledge",
                            "model": "meta-llama/Llama-3.3-70B-Instruct-Turbo", "base_url": "http://localhost:8000/v1",
                            "port": 8000, "n_results": len(rows), "aggregate": {}, "results": rows}
    base.update(over)
    return base


def raw_of(doc: dict[str, Any]) -> bytes:
    return json.dumps(doc, indent=2).encode()


def map_all(raw: bytes, path: str = "results/api_evals/test.json", *, profile: Any = None) -> list[Mapped]:
    profile = profile or load_profile(PROFILE)
    reader, mapper, limits = ResultsContainerReader(), TraceLoggerMapper(), IngestLimits()
    sniff = reader.sniff(raw, label=path, limits=limits)
    assert sniff.match, sniff.reasons
    origin = Origin.git(REPO_URL, PIN, path, golden.git_blob_sha1(raw))
    artefact = ArtefactRef("a0", hashlib.sha256(raw).hexdigest(), len(raw), "application/json", origin, "primary",
                           mapper.prov_primary(sniff.flags))  # type: ignore[arg-type]
    out = []
    for item in reader.parse(raw, artefact, limits=limits):
        outcome = map_unit(ExecutionUnit(item), mapper, profile)
        data, info = aer_bytes(outcome)
        out.append(Mapped(raw, outcome, data, info, profile))
    return out


def one(doc: dict[str, Any], path: str = "results/api_evals/test.json", **kw: Any) -> Mapped:
    mapped = map_all(raw_of(doc), path, **kw)
    assert len(mapped) == 1
    return mapped[0]


def ok(m: Mapped) -> None:
    errors = [(f.code, f.pointer) for f in m.validate().findings if f.severity == "error"]
    assert errors == [], errors


def _severities(m: Mapped, code: str) -> list[str]:
    return [str(s) for i, s in zip(m.outcome.issues, m.outcome.severities, strict=True) if i["code"] == code]


def _fixtures() -> list[dict[str, Any]]:
    source = FIXTURES / "SOURCE.json"
    if not source.is_file():
        pytest.skip("the memo-ozdincer fixtures are absent")
    return list(json.loads(source.read_bytes()))


def _fixture(path: str) -> bytes:
    entry = next(e for e in _fixtures() if e["path"] == path)
    raw = (FIXTURES / path).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == entry["sha256"] and len(raw) == entry["size"]
    assert f"{zlib.crc32(raw) & 0xFFFFFFFF:08x}" == entry["crc32"] and golden.git_blob_sha1(raw) == entry["git_blob"]
    return raw


# ------------------------------------------------------------------------------------------------ profile, registry, catalogue
def test_profile_registry_and_closed_schema():
    profile = load_profile(PROFILE)
    imp = profile.data["import"]
    assert imp["dialect"] == DIALECT_ID and imp["mapper"] == "agentdojo.tracelogger" and tuple(imp["variants"]) == ("rc.k7", "rc.k12")
    import tomllib

    fam = tomllib.loads((REPO / f"src/agentprov/adapters/agentdojo/profiles/{PROFILE}.profile.toml").read_text())["family"]["agentdojo"]
    assert check_against_schema(fam, family_schema()) == []
    jsonschema = pytest.importorskip("jsonschema")
    jsonschema.validate(fam, family_schema())
    assert family_table(profile).verified_code == ()  # D-472: no writer verified
    part = get_source(PROFILE).capabilities[0]
    assert part.import_status == "supported" and part.reader.endswith(":ResultsContainerReader")
    assert part.mapper.endswith(":TraceLoggerMapper") and part.corpus_id == PROFILE


def test_container_table_is_pinned_and_holds_no_raw_model_string():
    table = container_table(family_table(load_profile(PROFILE)))
    assert table
    text = (REPO / "src/agentprov/adapters/agentdojo/tables/memo_ozdincer_containers.toml").read_text()
    assert re.search(r"/(?:scratch|mfs1/u|home|Users)/[^/<\s\"']+/", text.replace("…", "")) is None


def test_every_rescont_twin_restates_its_d_rule():
    cat = load_catalogue("rescont")
    for entry in cat.rules.values() if hasattr(cat.rules, "values") else cat.rules:
        if entry.cls != "D" or not getattr(entry, "code", ()):
            continue
        twin = cat.get(entry.id.split("@")[0] + TWIN_SUFFIX + "@1") if "@" in entry.id else cat.get(entry.id + TWIN_SUFFIX)
        assert twin is not None and twin.cls == "I", entry.id
        assert entry.statement in twin.statement, entry.id
    assert "rescont" in citation.NAMESPACES


# ------------------------------------------------------------------------------------------------ reader
def test_reader_variants_and_rows():
    assert row_variant(row()) == "rc.k7"
    k12 = {k: v for k, v in row().items() if k != "classification"} | {"mode": "benign", "failure_mode": "success",
                                                                        "n_assistant_turns": 2, "n_total_tool_calls": 1,
                                                                        "any_garbled": False, "turns": []}
    assert row_variant(k12) == "rc.k12" and row_variant(k12 | {"suite": "banking"}) == "rc.k12"
    assert row_variant({"x": 1}) == "rc.unknown"
    reader = ResultsContainerReader()
    assert not reader.sniff(b'{"a": 1}', label="x", limits=IngestLimits()).match
    mapped = map_all(raw_of(container([row(), row(user_task_id="user_task_1")])))
    assert [m.header["source_key"]["loc"] for m in mapped] == [{"p": "/results/0"}, {"p": "/results/1"}]
    assert len({m.header["ex"] for m in mapped}) == 2


def test_n_results_mismatch_is_reported():
    m = one(container(n_results=7))
    assert "rescont.n_results_mismatch" in m.codes


def test_an_unknown_row_shape_is_a_degenerate_execution_never_dropped():
    mapped = map_all(raw_of(container([{"user_task_id": "user_task_0", "odd": True}])))
    assert len(mapped) == 1 and mapped[0].outcome.degenerate
    assert mapped[0].header["dialect"] == {"id": DIALECT_ID, "variant": "rc.unknown"}
    assert mapped[0].header["source_key"]["loc"] == {"p": "/results/0"}


def test_a_degenerate_row_cites_the_suite_it_takes_from_the_row_nf7():
    """Regen item 117 (NF-7): a degenerate row of a container without ``suite`` takes ``task.suite`` from the row (smoke
    rows), so its header cites ``/results/<i>/suite``; with a container ``suite`` it cites ``/suite`` as before."""
    r = row(suite="banking")
    r["extra"] = 1
    doc = container([row(), r], mode="smoke")
    del doc["suite"]
    m = map_all(raw_of(doc), "results/comprehensive_eval/smoke_x.json")[1]
    assert m.outcome.degenerate and m.header["task"]["suite"] == "banking"
    assert {"a": "a0", "p": "/results/1/suite"} in m.header["src"] and {"a": "a0", "p": "/suite"} not in m.header["src"]
    ok(m)
    doc["suite"] = "banking"
    control = map_all(raw_of(doc), "results/comprehensive_eval/smoke_x.json")[1]
    assert control.outcome.degenerate and {"a": "a0", "p": "/suite"} in control.header["src"]
    assert {"a": "a0", "p": "/results/1/suite"} not in control.header["src"]


def test_dispatch_is_deterministic():
    raw = raw_of(container())
    assert map_all(raw)[0].data == map_all(raw)[0].data


# ------------------------------------------------------------------------------------------------ header and actors
def test_header_task_and_benchmark():
    m = one(container())
    ok(m)
    task = m.header["task"]
    assert task == {"benchmark": "agentdojo", "suite": "banking", "task_id": "user_task_0", "attack_id": "tool_knowledge",
                    "attack_target_id": "injection_task_1", "defense_id": None}
    assert m.header["adapter"]["id"] == "agentdojo.tracelogger" and m.header["dialect"]["id"] == DIALECT_ID
    assert m.header["rules"]["rescont"] == 2  # D-31: version 2 since items 116 and 118 added issue codes


def test_container_fields_reach_every_row():
    mapped = map_all(raw_of(container([row(), row(user_task_id="user_task_3")], defense="melon", attack="direct")))
    for m in mapped:
        assert m.header["task"]["attack_id"] == "direct" and m.header["task"]["defense_id"] == "melon"
        assert m.header["ext"]["rescont"]["container"]["port"] == 8000


def test_bench_version_is_v1_by_the_script():
    bench = one(container()).get("bench")
    assert bench["version"] == "v1" and bench["evf"]["/version"] == "I"
    assert any("suite_version_v1_unverified" in r for r in bench["rule"])


def test_identity_comes_from_the_container_table():
    m = one(container(model="cb", attack=None, suite="banking"), "results/full_eval/x.json")
    agent = m.get("agent")
    assert agent["model"] == {"requested": "meta-llama/Llama-3.3-70B-Instruct"} and agent["evf"]["/model"] == "I"
    assert "identity_conflict" in m.codes  # D-474 (a): EVAL_LOG and MULTITURN_RESULTS say 3.1
    provider = one(container()).get("agent")
    assert provider["model"] == {"requested": "meta-llama/Llama-3.3-70B-Instruct-Turbo"} and provider["evf"]["/model"] == "O"
    unknown = one(container(model="/workspace/models/llama-70b"), "results/tokenless_battery/x.json")
    assert "model" not in unknown.get("agent") and "identity_unresolved" in unknown.codes  # the table says not_recorded (D-92)
    unresolved = one(container(model="nosuch"), "results/api_evals/x.json")
    assert "identity_unresolved" in unresolved.codes


def test_a_lora_adapter_is_a_defence_actor():
    m = one(container(model="cb"), "results/full_eval/x.json")
    ok(m)
    defence = m.get("def0")
    assert defence["name"] == "cb" and defence["ev"] == "I" and "defence_basis" in defence["ext"]["rescont"]
    assert m.header["task"]["defense_id"] == "cb"


def test_an_attack_comes_from_a_document_only():
    documented = one(container(model="cb", attack=None), "results/full_eval/x.json")
    assert documented.header["task"]["attack_id"] == "training_format" and documented.header["evf"]["/task/attack_id"] == "I"
    assert "attack_basis" in documented.header["ext"]["rescont"]
    undocumented = container(model="mse4")
    del undocumented["attack"]
    m = one(undocumented, "results/comprehensive_eval/x.json")
    assert "attack_id" not in m.header["task"] and m.header["unk"]["/task/attack_id"] == "not_recorded"
    assert "rescont.attack_unrecorded" in m.codes
    benign = one(container([row(injection_task_id=None)]))
    assert benign.header["task"]["attack_id"] is None


def test_a_container_without_a_defense_key_records_no_defence_nf6():
    """Regen item 116 (NF-6): no ``defense`` key and no table defence is an unrecorded defence (``unk not_recorded`` and
    the info issue ``rescont.defence_unrecorded``), never an asserted "no defence"; a logged ``defense: null`` still is."""
    absent = container()
    del absent["defense"]
    m = one(absent)
    ok(m)
    assert "defense_id" not in m.header["task"] and m.header["unk"]["/task/defense_id"] == "not_recorded"
    assert "/task/defense_id" not in m.header["evf"] and not [r for r in m.header["rule"] if r.endswith("#/task/defense_id")]
    (issue,) = m.issues("rescont.defence_unrecorded")
    assert issue["ids"] == ["exec"] and _severities(m, "rescont.defence_unrecorded") == ["info"]
    logged_null = one(container(defense=None))
    assert logged_null.header["task"]["defense_id"] is None and logged_null.header["evf"]["/task/defense_id"] == "I"
    assert {"a": "a0", "p": "/defense"} in logged_null.header["src"] and "rescont.defence_unrecorded" not in logged_null.codes
    table = container(model="cb")
    del table["defense"]
    by_table = one(table, "results/full_eval/x.json")  # a LoRA adapter the table names is still the defence (D-474)
    assert by_table.header["task"]["defense_id"] == "cb" and "rescont.defence_unrecorded" not in by_table.codes


def test_a_version_1_aer_validates_against_the_archived_catalogue_d31(monkeypatch):
    """D-31 (option A): items 116 and 118 added issue codes, so ``rescont`` and the profile are at version 2. An AER the
    phase-10q trial build wrote (``rescont`` and the profile at version 1, main's bytes) still validates: both version-1
    files come from ``archive/``. The trial build is replayed by shipping ``rescont`` at version 1 to the mapper."""
    import agentprov.adapters.runner as runner  # noqa: PLC0415

    real = runner.load_catalogue
    monkeypatch.setattr(runner, "load_catalogue",
                        lambda ns, version=None, **kw: real(ns, 1 if ns == "rescont" and version is None else version, **kw))
    m = one(container(), profile=load_profile(PROFILE, 1))
    assert m.header["rules"]["rescont"] == 1 and m.header["profile"]["version"] == 1
    ok(m)
    assert RuleRegistry.default().get("rescont", 1).digest == load_catalogue("rescont", 1).digest != load_catalogue("rescont").digest


# ------------------------------------------------------------------------------------------------ scopes, messages
def test_run_scope_has_the_duration_and_no_times():
    run = one(container()).get("run")
    assert run["t"] == {"dur_s": 12.0, "dur_clock": "wall"}
    assert run["unk"]["/t/start"] == "not_recorded" and run["unk"]["/t/end"] == "not_recorded"


def test_attempt_index_is_lost():
    att = one(container()).get("att0")
    assert att["unk"] == {"/index": "lost"} and "index" not in att


def test_system_message_is_the_script_prompt():
    m0 = one(container()).get("m0")
    assert m0["actor"] == "bench" and m0["evf"]["/actor"] == "I"


def test_model_calls_infer_their_input():
    m = one(container())
    mc = m.of_kind("model_call")[1]
    assert mc["input"] == ["m0", "m1", "m2", "m3"] and mc["evf"]["/input"] == "I"
    assert "rescont.request_not_recorded" in m.codes


def test_calls_have_no_provider_id_and_link_positionally():
    m = one(container())
    ok(m)
    call = m.get("m2")["parts"][1]
    assert call["t"] == "tool_call" and "provider_call_id" not in call
    assert m.get("m2")["unk"]["/parts/1/provider_call_id"] == "not_recorded"
    te = m.of_kind("tool_execution")[0]
    assert te["call"] == "m2#1" and te["evf"]["/call"] == "I"
    assert m.get("m3")["parts"][0]["responds_to"] == "m2#1"


def test_empty_assistant_text_is_ambiguous():
    r = row()
    r["messages"][-1]["content"] = ""
    m = one(container([r]))
    assert m.get("m4")["unk"]["/parts/0/text"] == "ambiguous"


def test_a_repeated_prompt_is_the_defence_copy():
    r = row()
    r["messages"].insert(4, {"role": "user", "content": "Pay the bill."})
    m = one(container([r], defense="repeat_user_prompt"))
    ok(m)
    copy_msg = m.get("m4")
    assert copy_msg["actor"] == "def0" and copy_msg["ext"]["rescont"]["copy_of"] == "m1"


def test_spotlighted_outputs_are_post_defence():
    m = one(container(defense="spotlighting_with_delimiting"))
    assert m.get("m3")["ext"]["rescont"]["content_state"] == "post_defence"


def test_a_melon_block_is_a_defence_decision():
    r = row()
    r["messages"][-1] = {"role": "assistant", "content": MELON}
    m = one(container([r], defense="melon"))
    ok(m)
    dc = m.of_kind("decision")[0]
    assert dc["actor"] == "def0" and dc["verdict"] == "terminate" and dc["subject"] == "te0"
    block = m.get("m4")
    assert block["actor"] == "def0" and block["generated_by"] == dc["id"]
    assert len(m.of_kind("model_call")) == 1 and "rescont.melon_calls_not_recorded" in m.codes


def test_raw_output_is_the_returned_value_when_structured():
    r = row()
    r["messages"][3]["raw_output"] = {"amount": 98.7}
    te = one(container([r])).of_kind("tool_execution")[0]
    assert te["returned"] == {"amount": 98.7}
    r["messages"][3]["raw_output"] = "Bill: 98.70"
    te = one(container([r])).of_kind("tool_execution")[0]
    assert te["unk"]["/returned"] == "ambiguous" and te["ext"]["rescont"]["raw_output"] == "Bill: 98.70"


def test_lone_surrogates_are_replaced_with_a_disclosure_nf13():
    """Regen item 119 (NF-13): the D-378 surrogate pass runs in the results build too. A lone surrogate in a message's text
    or a tool output (``json.dumps(ensure_ascii=True)`` of an emoji cut in half) is replaced by U+FFFD, tagged D and
    disclosed by ``agentdojo.lone_surrogate_replaced``, instead of sealing the row as an ``adapter_defect``."""
    r = row()
    r["messages"][4]["content"] = "done \ud800"
    r["messages"][3]["content"] = "Bill \ud83d"
    m = one(container([r]))
    assert not m.outcome.degenerate
    ok(m)
    assert m.get("m4")["parts"][0]["text"] == "done �" and m.get("m3")["parts"][0]["text"] == "Bill �"
    assert m.get("m4")["evf"]["/parts/0/text"] == "D"
    assert "agentdojo.lone_surrogate_replaced@1#/parts/0/text" in m.get("m4")["rule"]
    (issue,) = m.issues("agentdojo.lone_surrogate_replaced")
    assert issue["ids"] == ["m3", "m4"] and _severities(m, "agentdojo.lone_surrogate_replaced") == ["info"]
    # a key cannot be $utf16-wrapped: scrubbed before mapping, disclosed on exec
    k = row()
    k["messages"][2]["tool_calls"][0]["args"] = {"file\udc00": "bill.txt"}
    k["messages"][3]["tool_call"]["args"] = {"file\udc00": "bill.txt"}
    keyed = one(container([k]))
    assert not keyed.outcome.degenerate
    ok(keyed)
    assert keyed.of_kind("tool_execution")[0]["args"] == {"file�": "bill.txt"}
    assert keyed.issues("agentdojo.lone_surrogate_replaced")[0]["ids"][0] == "exec"
    assert keyed.of_kind("tool_execution")[0]["call"] == "m2#1"  # the link still matches on the scrubbed args


def test_script_summaries_stay_in_ext():
    m = one(container())
    assert m.header["ext"]["rescont"]["derived"]["classification"]["label"] == "benign"
    assert not [j for j in m.of_kind("judgement") if j["name"] not in ("utility", "security")]


def test_no_fixtures_and_an_info_issue():
    m = one(container())
    assert m.of_kind("fixture") == [] and "rescont.injection_map_not_recorded" in m.codes


# ------------------------------------------------------------------------------------------------ outcomes
def test_an_empty_row_is_outcome_only_with_imposed_outcomes():
    m = one(container([row(messages=[], utility=False, security=True)]))
    ok(m)
    assert m.header["unit"] == "outcome_only" and m.of_kind("message") == []
    assert {j["origin"] for j in m.of_kind("judgement")} == {"harness_default"}
    assert "outcome_imposed_by_runner" in m.codes and "no_execution_observed" in m.codes


def test_the_imposed_outcome_issue_cites_the_judgements_twin_nf5():
    """Regen item 115 (NF-5): ``outcome_imposed_by_runner`` cites what the judgements cite, the ``_unverified`` twin of
    ``rescont.exception_imposes_outcome@1`` (D.5.4, D-472: ``verified_code = []``), never the class-D rule."""
    m = one(container([row(messages=[], utility=False, security=True)]))
    ok(m)
    cited = {r.split("#", 1)[0] for j in m.of_kind("judgement") for r in j["rule"]}
    assert cited == {f"rescont.exception_imposes_outcome{TWIN_SUFFIX}@1"}
    (issue,) = m.issues("outcome_imposed_by_runner")
    assert issue["rule"].split("#", 1)[0] in cited


@pytest.mark.parametrize(("utility", "security", "imposed", "differ"), [
    (False, True, ["j0", "j1"], []),
    (True, True, ["j1"], ["j0"]),
    (False, False, ["j0"], ["j1"]),
    (True, False, [], ["j0", "j1"]),
])
def test_an_exception_row_imposes_only_the_declared_values_nf8(utility: bool, security: bool, imposed: list[str],
                                                                 differ: list[str]):
    """Regen item 118 (NF-8): a row with no messages relabels a judgement ``harness_default`` only when its logged value
    is the one ``agentdojo.rescont_exception_row_defaults`` declares (``utility = false``, ``security = true``), as the
    capture mapper does; another value keeps its checker origin and raises ``rescont.exception_row_values_differ``."""
    m = one(container([row(messages=[], utility=utility, security=security)]))
    ok(m)
    origins = {j["id"]: j["origin"] for j in m.of_kind("judgement")}
    assert origins == {jid: "harness_default" if jid in imposed else "checker" for jid in ("j0", "j1")}
    assert [i["ids"] for i in m.issues("outcome_imposed_by_runner")] == ([imposed] if imposed else [])
    assert [i["ids"] for i in m.issues("rescont.exception_row_values_differ")] == [[jid] for jid in differ]
    assert set(_severities(m, "rescont.exception_row_values_differ")) <= {"warning"}
    assert "no_execution_observed" in m.codes


def test_benign_security_is_a_harness_default():
    origins = {j["name"]: j["origin"] for j in one(container([row(injection_task_id=None)])).of_kind("judgement")}
    assert origins == {"utility": "checker", "security": "harness_default"}


# ------------------------------------------------------------------------------------------------ redaction (D-476)
def _leaks(data: bytes) -> list[str]:
    out = []
    for form in (CLUSTER_LLAMA, f"/scratch/{ACCOUNT}/", f"~1scratch~1{ACCOUNT}~1", ACCOUNT):
        if form.encode() in data:
            out.append(form.replace(ACCOUNT, "<acct>"))
    return out


def test_redaction_covers_values_keys_and_pointers():
    m = one(container(model=CLUSTER_LLAMA), "results/api_evals/x.json")
    ok(m)
    assert _leaks(m.data) == []
    label = m.header["ext"]["rescont"]["container"]["model"]
    assert re.fullmatch(r"cluster:[0-9a-f]{12}/llama-70b", label)
    assert {"p": "/ext/rescont/container/model", "rule": f"{PROFILE}@2#cluster_scratch"} in m.header["ext"]["rescont"]["redacted"]
    assert m.header["evf"]["/ext/rescont/container/model"] == "D" and f"{RULE}#/ext/rescont/container/model" in m.header["rule"]
    assert "rescont.value_redacted" in m.codes
    assert m.header["src"].count({"a": "a0", "p": "/model"}) == 1  # the locator stays on the raw field


def test_redactor_rewrites_keys_and_pointer_escaped_forms_bf21():
    rules = parse_redact_rules([{"id": "r", "scope": "model_id", "pattern": r"^(?P<span>/scratch/[^/]+/.*)/(?P<leaf>[^/]+)$",
                                 "replacement": "cluster:{span12}/{leaf}"}], "t")
    red = Redactor("p", 1, rules, {"model_id": [CLUSTER_LLAMA]})
    escaped = CLUSTER_LLAMA.replace("/", "~1")
    record = {"k": "actor", "id": "agent", "ev": "O", "by": "config",
              "ext": {"x": {CLUSTER_LLAMA: 1}, "lex": {"ord": {f"/ext/x/{escaped}": [CLUSTER_LLAMA]}}},
              "evf": {f"/ext/x/{escaped}": "O"}, "rule": [f"a.b@1#/ext/x/{escaped}"]}
    done = red.apply(record, lambda p: f"{RULE}#{p}")
    assert done and _leaks(json.dumps(record).encode()) == []
    label = red.label(CLUSTER_LLAMA)
    assert record["ext"]["x"] == {label: 1}
    assert record["evf"][f"/ext/x/{label.replace("/", "~1")}"] == "D"  # a redacted pointer is D (D-182)


def test_pipeline_name_scope_with_a_munged_home_path():
    """Phase 10j's shape (D-255): a munged cluster home path in the logged pipeline_name, here with a made-up account."""
    rules = parse_redact_rules([{"id": "home", "scope": "pipeline_name",
                                 "pattern": r"^_ceph_ssd_students_(?P<span>[^_/]+)_(?P<leaf>qwen3_5(?:-[0-9]+B)?)$",
                                 "replacement": "_ceph_ssd_students_{span12}_{leaf}"}], "t")
    for leaf in ("qwen3_5", "qwen3_5-2B", "qwen3_5-4B"):
        name = f"_ceph_ssd_students_{ACCOUNT}_{leaf}"
        label, rid = redact_value(rules, "pipeline_name", name, salt="p")
        assert rid == "home" and ACCOUNT not in label and label.endswith("_" + leaf)
        assert redact_value(rules, "model_id", name, salt="p") == (name, None)  # another scope is not touched
        red = Redactor("p", 1, rules, {"pipeline_name": [name]})
        record = {"k": "execution", "id": "exec", "ev": "O", "ext": {"agentdojo": {"pipeline_name": name}},
                  "artifacts": [{"id": "a0", "origin": {"kind": "git", "path": f"runs/arm/{name}/banking/user_task_0/none/none.json"}}],
                  "src": [{"a": "a0", "o": "/path"}]}
        red.apply(record, lambda p: f"{RULE}#{p}")
        assert record["ext"]["agentdojo"]["pipeline_name"] == label and ACCOUNT not in json.dumps(record)
        # D-510 (A): the directory that repeats the pipeline name is rewritten inside the origin path; the locator stays
        assert record["artifacts"][0]["origin"]["path"] == f"runs/arm/{label}/banking/user_task_0/none/none.json"
        assert record["src"] == [{"a": "a0", "o": "/path"}]
    a = redact_value(rules, "pipeline_name", f"_ceph_ssd_students_{ACCOUNT}_qwen3_5", salt="p")[0]
    b = redact_value(rules, "pipeline_name", "_ceph_ssd_students_other_qwen3_5", salt="p")[0]
    assert a != b  # distinct spans stay distinct


def test_redaction_rules_are_closed():
    good = {"id": "r", "scope": "model_id", "pattern": "^/x/(?P<leaf>[^/]+)$", "replacement": "{span12}/{leaf}"}
    parse_redact_rules([good], "t")
    for bad in ({**good, "scope": "content"}, {**good, "pattern": ".*"}, {**good, "replacement": "{name}"},
                {**good, "extra": 1}, {"id": "r", "scope": "model_id", "pattern": "^/x$", "replacement": "{leaf}"}):
        with pytest.raises(ProfileError):
            parse_redact_rules([bad], "t")
    with pytest.raises(ProfileError):
        parse_redact_rules([good, good], "t")


def test_two_strings_with_one_label_are_a_profile_defect():
    rules = parse_redact_rules([{"id": "r", "scope": "model_id", "pattern": r"^/scratch/[^/]+/(?:.*/)?(?P<leaf>[^/]+)$",
                                 "replacement": "c/{leaf}"}], "t")
    with pytest.raises(ProfileError):
        Redactor("p", 1, rules, {"model_id": ["/scratch/a/x/m", "/scratch/b/y/m"]})


def test_no_account_path_reaches_sem_or_prov():
    m = one(container(model=CLUSTER_LLAMA), "results/api_evals/x.json")
    aer = load_aer_bytes(m.data)
    sem = annotate(aer, load_semantics_profile("agentdojo.suites", 2))
    sem_bytes = json.dumps([sem.header, *sem.records, sem.seal]).encode()
    prov = derive(aer, [sem], registry=RuleRegistry.default(),
                  sem_profiles={("agentdojo.suites", 2): load_semantics_profile("agentdojo.suites", 2)})
    assert _leaks(m.data) == [] and _leaks(sem_bytes) == [] and _leaks(prov.prov_json) == []


# ------------------------------------------------------------------------------------------------ real fixtures
def test_real_fixtures_map_validate_and_cite_only_twins():
    for entry in _fixtures():
        if entry["path"] == "LICENSE":
            continue
        mapped = map_all(_fixture(entry["path"]), entry["path"])
        assert mapped and not any(m.outcome.degenerate for m in mapped)
        for m in mapped:
            ok(m)
            refs = [ref for record in m.records for ref in record.get("rule", ()) or ()]
            # regen item 115 (NF-5): the issue that reports the judgements' imposed origin cites their reading too (the
            # other issues cite their rule as given, as the generic mapper's do)
            refs += [i["rule"] for i in m.info.issues if i["code"] == "outcome_imposed_by_runner"]
            for ref in refs:
                rid = str(ref).split("#", 1)[0]
                ns = rid.split(".", 1)[0]
                if ns in citation.NAMESPACES and rid not in citation.INDEPENDENT and rid != RULE:
                    # a D rule that has an _unverified twin reads the harness code: with verified_code = [] (D-472) only
                    # the twin may be cited (RuleEntry carries no `code` list, so the twin's existence is the test)
                    entry_ = load_catalogue(ns).get(rid)
                    base, _, version = rid.rpartition("@")
                    assert entry_ is None or entry_.cls == "I" \
                        or load_catalogue(ns).get(f"{base}{TWIN_SUFFIX}@{version}") is None, rid


def test_fixtures_stay_within_the_budget():
    total = sum(e["size"] for e in _fixtures())
    assert total <= 512 * 1024


def test_profile_variant_change_is_refused_without_a_bump():
    data = (REPO / f"src/agentprov/adapters/agentdojo/profiles/{PROFILE}.profile.toml").read_bytes()
    bad = data.replace(b'variants = ["rc.k7", "rc.k12"]', b'variants = ["rc.k7"]')
    profile = parse_profile(bad, source="test")
    rows = map_all(raw_of(container([copy.deepcopy(row()) | {"mode": "x"}])), profile=profile)
    assert rows[0].outcome.degenerate


# ------------------------------------------------------------------------------------------------ full snapshot (local)
#: quirk id -> (census key, measured counter) of tools/agentdojo/phase10q_trial.py's report
_CENSUS: dict[str, dict[str, tuple[str, str]]] = {
    "agentdojo.rescont_exception_row_defaults": {"rows": ("rows_with", "exception_row")},
    "agentdojo.rescont_benign_security_constant": {"rows": ("rows_with", "benign_security")},
    "agentdojo.rescont_null_content_as_empty": {"messages": ("features", "empty_assistant_text"),
                                                 "rows": ("rows_with", "empty_assistant_text")},
    "agentdojo.rescont_melon_block": {"messages": ("features", "melon_block"), "rows": ("rows_with", "melon_block")},
    "agentdojo.rescont_repeat_prompt_copy": {"messages": ("features", "repeat_copy"), "rows": ("rows_with", "repeat_copy")},
    "agentdojo.rescont_spotlighting_delimiters": {"messages": ("features", "spotlighted_output"),
                                                   "rows": ("rows_with", "spotlighted_output")},
    "agentdojo.rescont_raw_output": {"messages": ("features", "raw_output"), "rows": ("rows_with", "raw_output")},
    "agentdojo.args_mutated_in_place": {"calls": ("features", "tool_calls"), "rows": ("rows_with", "tool_calls")},
    "agentdojo.provider_call_id_anomalies": {"calls_without_id": ("features", "tool_calls"), "rows": ("rows_with", "tool_calls")},
    "agentdojo.unexecuted_trailing_calls": {"rows": ("rows_with", "unexecuted_trailing_calls")},
}


@pytest.mark.full_corpus
def test_every_observed_count_is_reproduced_on_the_pinned_snapshot(request: pytest.FixtureRequest):
    """D.6.10 item 3 for this dialect: the census of the pinned snapshot reproduces every declared count, maps every row,
    and leaves no account path in any sealed AER (D-476)."""
    if "full_corpus" not in str(request.config.getoption("markexpr")):
        pytest.skip("a full-snapshot census takes about a minute: select it with `pytest -m full_corpus`")
    import os
    import sys

    from agentprov.raw.fetch import Fetcher, Recipe, resolve_cache_dir

    profile = load_profile(PROFILE)
    pin = next(dict(p) for p in profile.data["source"]["pins"] if p.get("primary") is True)
    if not Fetcher(resolve_cache_dir(None)).plan(Recipe.from_pin(pin, canonical_repo=REPO_URL)).cached:
        pytest.skip("the memo-ozdincer pin is not in the fetch cache (U-07)")
    sys.path.insert(0, str(REPO / "tools" / "agentdojo"))
    import phase10q_trial

    report = phase10q_trial.census(workers=int(os.environ.get("AGENTPROV_JOBS", "4")))
    assert report["crashes"] == [] and report["degenerate"] == 0 and report["account_leaks"] == 0
    assert report["rows"] == 13070 and report["containers"] == {"mapped": 137}
    for quirk in family_table(profile).quirks:
        for key, value in quirk.observed.get("head", {}).items():
            section, name = _CENSUS[quirk.id][key]
            assert report[section].get(name, 0) == value, (quirk.id, key)
