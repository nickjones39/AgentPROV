"""The semantics profile ``agentdojo.suites@2``: reviewed tool tables (docs/architecture C.14.8; R8; D-110..D-112), the
SEM-rule twins (D-86) and the AutoDojo payload unescape (B1), both regeneration-batch item 1.

* version 2 loads by convention, carries version 1's tables unchanged and annotates every golden AgentDojo AER as
  version 1 does, except where it deliberately diverges: a D rule is cited through its ``_unverified`` twin (with ``ev``
  weakened to I) for a log whose source profile does not verify the rule's code (D-86), and a payload with an
  AutoDojo cache link is also read with AutoDojo's escape undone (B1);
* the reviewed tables are well formed, cite their code per state, and keep a tool only when every code state labels it
  alike (CrAIBench crypto_trading: 13 tools in one state; chain: 4 of 9 across two states);
* selection: a reviewed table applies to an unlabelled run of its (benchmark, suite); a recorded label selects none;
  version 1 knows none of these tools;
* CrAIBench logs (synthetic and the real fixtures) annotate with the reviewed labels, validate as SEM, and derive PROV
  that passes tier 4.

Fixture text is never printed (G.8.1 item 5): failures show ids, labels and tool names only.
"""

from __future__ import annotations

import copy
import dataclasses
import importlib.util
import json
import sys
import tomllib
from functools import cache
from pathlib import Path
from typing import Any

import pytest
from phase10d_support import SOURCES, fixture_entries, map_doc, map_fixture, ok, synthetic_path


from agentprov.adapters.agentdojo.hooks.autodojo import yaml_escape
from agentprov.adapters.agentdojo.semantics import markers
from agentprov.adapters.agentdojo.semantics.suites import (
    CITED_RULES_OF,
    R_REVIEWED_LABEL,
    R_REVIEWED_TABLE,
    R_UNESCAPE,
    TWINNED,
    ProfileDataError,
    SuitesProfile,
    parse_tables,
    sem_citations,
)
from agentprov.aer.evidence import weakest
from agentprov.adapters.semantics_profiles import load_semantics_profile
from agentprov.aer.reader import AerDocument, load_aer_bytes
from agentprov.aer.rules import load_catalogue
from agentprov.sem.engine import annotate
from agentprov.sem.profiles import profile_digest
from agentprov.sem.types import INTEGRITY_VALUES, ROLE_VALUES, SemanticsProfile
from agentprov.sem.validate import validate_sem_document
from agentprov.testing import sem_v23 as ss


def _load_test_semantics() -> Any:
    """agentdojo's ``test_semantics``, loaded by path under its own name: ten other adapter directories have a module of
    that name, and a bare import took whichever came first on ``sys.path`` (bug pass BF-35)."""
    name = "agentprov_tests_agentdojo_test_semantics"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name("test_semantics.py"))
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


ts = _load_test_semantics()

DIR_1 = ts.PROFILE_DIR
DIR_2 = DIR_1.parent / "agentdojo.suites-2"
CRAIBENCH = next(s for s in SOURCES if s.name == "craibench")
CHAIN_KNOWN = {"getBalance", "getTransactions", "read_file", "transfer"}
CRYPTO_TOOLS = {"exchangeFiat", "getRecentPricesFromOracle", "getTransactions", "leveragedTrading", "limitOrderTrade",
                "performArbitrage", "provideLiquidity", "read_file", "siphon", "spotTrade", "tradeFutures",
                "tradeOnDex", "tradeOptions"}


@cache
def v2() -> SuitesProfile:
    prof = load_semantics_profile("agentdojo.suites", 2)
    assert isinstance(prof, SuitesProfile)
    return prof


def _files(directory) -> dict[str, bytes]:  # type: ignore[no-untyped-def]
    return {p.name: p.read_bytes() for p in sorted(directory.iterdir()) if p.is_file()}


def _reviewed_doc() -> dict[str, Any]:
    return tomllib.loads((DIR_2 / "reviewed_tables.toml").read_text(encoding="utf-8"))


def _parse_reviewed(doc: dict[str, Any]):  # type: ignore[no-untyped-def]
    """``parse_tables`` of version 2 with ``doc``, written back as TOML, as its reviewed tables."""
    files = _files(DIR_2)
    files["reviewed_tables.toml"] = _toml(doc).encode("utf-8")
    return parse_tables(files, 2)


def _toml(doc: dict[str, Any]) -> str:
    """A minimal TOML writer for the reviewed-table shape (strings, lists of strings, nested tables)."""
    lines: list[str] = []
    for table in doc["table"]:
        lines.append("[[table]]")
        lines += [f"{k} = {json.dumps(v)}" for k, v in table.items() if k != "code_state"]
        for state in table.get("code_state", []):
            lines.append("[[table.code_state]]")
            lines += [f"{k} = {json.dumps(v)}" for k, v in state.items() if k not in ("tools", "files")]
            for tool, entry in state.get("tools", {}).items():
                lines.append(f"[table.code_state.tools.{tool}]")
                lines += [f"{k} = {json.dumps(v)}" for k, v in entry.items()]
    return "\n".join(lines) + "\n"


def _craibench_log(suite: str, calls: list[tuple[str, str]], pipeline: str = "gpt-4o-spotlighting_with_delimiting"
                   ) -> AerDocument:
    """A v0.k11 CrAIBench log of ``suite``: one assistant turn per (tool, reply), then a final reply."""
    doc = ts.ads.new_log(suite_name=suite, pipeline_name=pipeline, user_task_id="user_task_1",
                         injection_task_id="injection_task_0")
    messages = doc["messages"][:2]
    for i, (tool, reply) in enumerate(calls):
        call = {"function": tool, "args": {}, "id": f"call_{i}"}
        messages.append({"role": "assistant", "content": None, "tool_calls": [call]})
        messages.append({"role": "tool", "content": reply, "tool_call_id": call["id"], "tool_call": call,
                         "error": None})
    messages.append({"role": "assistant", "content": "Done.", "tool_calls": None})
    doc["messages"] = messages
    m = map_doc(CRAIBENCH, doc, synthetic_path(CRAIBENCH, doc))
    ok(m)
    return load_aer_bytes(m.data)


def _labels(prof: SemanticsProfile, doc: AerDocument) -> dict[str, tuple[Any, Any, tuple[str, ...]]]:
    """tool name -> (role of its execution, integrity of its result part, rules of the integrity annotation)."""
    anns = list(prof.annotate(doc))
    out: dict[str, tuple[Any, Any, tuple[str, ...]]] = {}
    for te in doc.of_kind("tool_execution"):
        (role,) = ts._on(anns, te["id"], "role")
        part = ss.result_part(doc, te["id"])
        assert part is not None
        (integrity,) = ts._on(anns, part, "integrity")
        out[te["name"]] = (role.value, integrity.value, integrity.rule)
    return out


# ------------------------------------------------------------------------------------------------ loading and v1 parity
def test_v2_loads_and_matches_its_directory():
    prof = v2()
    files = _files(DIR_2)
    assert set(files) == {"labels.toml", "profile.toml", "reviewed_tables.toml", "suite_tools.toml"}
    assert (prof.id, prof.version, prof.sha256) == ("agentdojo.suites", 2, profile_digest(files))
    assert dict(prof.rules) == {"agentdojo": 2}  # D-31 option A: @2 reads catalogue 2
    assert load_semantics_profile("agentdojo.suites", 1).sha256 != prof.sha256


def test_v2_carries_the_v1_tables_unchanged():
    """suite_tools.toml is a byte copy; labels.toml parses equal; profile.toml differs only in its version, the
    agentdojo catalogue version it declares (D-31: 1 for @1, 2 for @2), the reviewed-table selection keys and the
    payload unescape of item 1 (B1)."""
    one, two = _files(DIR_1), _files(DIR_2)
    assert one["suite_tools.toml"] == two["suite_tools.toml"]
    assert tomllib.loads(one["labels.toml"].decode()) == tomllib.loads(two["labels.toml"].decode())
    p1, p2 = (tomllib.loads(f["profile.toml"].decode()) for f in (one, two))
    assert (p1["profile"]["version"], p2["profile"]["version"]) == (1, 2)
    assert (p1["profile"].pop("rules"), p2["profile"].pop("rules")) == ({"agentdojo": 1}, {"agentdojo": 2})
    assert {k: p2["selection"].pop(k) for k in ("reviewed_tables", "reviewed_code_states")} == {
        "reviewed_tables": "reviewed_tables.toml", "reviewed_code_states": "same_label_in_every_state"}
    assert {k: p2["marker"].pop(k) for k in ("payload_unescape", "payload_unescape_link")} == {
        "payload_unescape": R_UNESCAPE, "payload_unescape_link": ["exact", "wrapped"]}
    # regeneration-batch item 8 (D-379): version 2 reads with agentdojo.yaml_norm@2
    assert tuple(p1["marker"].pop("normalisers")) == markers.NORMALISERS_OF[1]
    assert tuple(p2["marker"].pop("normalisers")) == markers.NORMALISERS_OF[2]
    p1["profile"]["version"] = p2["profile"]["version"] = 0
    assert p1 == p2
    assert v2().tables.reviewed and not ts.profile().tables.reviewed


def _as_v2(record: dict[str, Any], cite: Any) -> dict[str, Any]:
    """A version-1 annotation record as version 2 writes it for a log with citation policy ``cite`` (D-86): each rule
    resolved to the rule or its twin; a twin (class I) weakens ``ev``; a marker decided by the YAML reading names
    ``agentdojo.yaml_norm@2`` (item 8, D-379). The annotation id is dropped: version 2 adds annotations (items 4 and 6)."""
    rules = [cite(r) for r in record["rule"]]
    out = {k: v for k, v in record.items() if k != "id"}
    out.update(rule=rules, ev=weakest(record["ev"], "I") if rules != record["rule"] else record["ev"])
    if record["type"] == "injection_marker" and record["value"].get("normaliser") == markers.YAML_NORM:
        out["value"] = {**record["value"], "normaliser": markers.YAML_NORM_STRICT}
    return out


#: Namespaced annotations only version 2 writes (items 6 and 4; D-371, D-377).
V2_ONLY: frozenset[str] = frozenset({"agentdojo.partial_payload", "agentdojo.success_without_visible_payload"})


def _v2_common(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Version 2's annotations without its own namespaced types, ids dropped (the comparison with version 1)."""
    return [{k: v for k, v in r.items() if k != "id"} for r in records if r["type"] not in V2_ONLY]


def test_v2_annotates_every_golden_agentdojo_aer_exactly_as_v1():
    """Version 2 = version 1 up to the twins (D-86) on every golden AgentDojo AER; none carries an AutoDojo link, so the
    unescape (B1) never applies here (``test_v2_unescapes_autodojo_linked_payloads_only`` covers it)."""
    twinned = 0
    for label, doc in ts._all_docs():
        assert not any(_obj_get(f, "ext", "autodojo") for f in doc.of_kind("fixture")), label
        cite = sem_citations(doc).cite
        first = [_as_v2(r, cite) for r in ss.annotation_records(ts.profile().annotate(doc))]
        second = _v2_common(ss.annotation_records(v2().annotate(doc)))
        assert second == first, label
        twinned += sum(r["rule"] != o["rule"] for r, o in zip(second, ss.annotation_records(ts.profile().annotate(doc)),
                                                                strict=True))
    assert twinned  # the v1.k14 head logs of the native set cite no twin; the adprov pairs and examples do some


def _obj_get(record: dict[str, Any], *keys: str) -> Any:
    node: Any = record
    for k in keys:
        node = node.get(k) if isinstance(node, dict) else None
    return node


def test_v2_cites_the_d_rules_through_twins_by_the_source_profile():
    """D-86 and its addendum: the SEM rules are D where the source profile verifies their code for the log, else their
    class-I twins; the normalisers are harness-independent; a header whose profile digest is not the packaged one
    verifies nothing (fail-closed)."""
    catalogue = load_catalogue("agentdojo")
    for ref in TWINNED:
        name, _, n = ref.partition("@")
        twin = catalogue.get(f"{name}_unverified@{n}")
        assert catalogue.get(ref).cls == "D" and twin is not None and twin.cls == "I" and twin.citable, ref
        assert f"{name}_unverified@{n}" in CITED_RULES_OF[2] and f"{name}_unverified@{n}" not in CITED_RULES_OF[1]
    import test_rope as tr

    rope = load_aer_bytes(tr._map(tr.QWEN_AUTODOJO).data)
    assert {sem_citations(rope).cite(r) for r in TWINNED} == {f"{r.split('@')[0]}_unverified@1" for r in TWINNED}
    for norm in markers.NORMALISERS:  # independent of the harness (D-86 addendum)
        assert sem_citations(rope).cite(norm) == norm
    for label, doc in ts._all_docs():
        variant = _obj_get(doc.header, "dialect", "variant")
        cite = sem_citations(doc).cite
        if doc.header["profile"]["id"] == "agentdojo-upstream" and variant in ("v0.k11", "v1.k14"):
            # c274885 verifies v0.k11; 089ed468 and a75aba7 verify v1.k14 (the passages checked unchanged, D-86 addendum)
            assert [cite(r) for r in TWINNED[:5]] == list(TWINNED[:5]), label
            assert cite(R_UNESCAPE).endswith("_unverified@1"), label  # AutoDojo's escape: aa458794 only
    head = next(doc for _label, doc in ts._all_docs() if doc.header["profile"]["id"] == "agentdojo-upstream")
    stale = _edited(head, lambda r: r["profile"].__setitem__("sha256", "0" * 64) if r.get("id") == "exec" else None)
    assert [sem_citations(stale).cite(r) for r in TWINNED[:5]] == [f"{r.split('@')[0]}_unverified@1" for r in TWINNED[:5]]


def _edited(doc: AerDocument, edit: Any) -> AerDocument:
    """``doc`` with ``edit`` applied to a copy of every record (annotation reads records only; no digest is checked)."""
    records = copy.deepcopy(doc.records)
    for record in records:
        edit(record)
    return dataclasses.replace(doc, header=records[0], records=records,
                               _index={r["id"]: r for r in records if isinstance(r.get("id"), str)})


def test_v2_unescapes_autodojo_linked_payloads_only():
    """B1 on ROPE's AutoDojo fixtures: a marker version 1 misses becomes ``present`` in version 2 exactly when the fixture
    carries a cache link and the payload with AutoDojo's escape undone occurs in a reading of the output; it then cites
    agentdojo.autodojo_payload_unescape (its twin for ROPE, whose harness code is unverified) and the link as a premise.
    Without the link (the same log, its fixtures' ext.autodojo removed) version 2 marks as version 1 up to the twins."""
    import test_rope as tr

    gained = 0
    for path in (tr.QWEN_AUTODOJO, tr.WRAPPED, tr.BANKING_AUTODOJO, tr.RETRY):  # RETRY: an escaped payload gains
        doc = load_aer_bytes(tr._map(path).data)
        cite = sem_citations(doc).cite
        linked = {f["id"]: f for f in doc.of_kind("fixture") if _obj_get(f, "ext", "autodojo", "cache_match")}
        assert linked, path
        first = [_as_v2(r, cite) for r in ss.annotation_records(ts.profile().annotate(doc))]
        second = _v2_common(ss.annotation_records(v2().annotate(doc)))
        assert len(first) == len(second)
        for a, b in zip(first, second, strict=True):
            if a == b:
                continue
            assert b["type"] == "injection_marker" and b["value"]["fixture"] in linked, path
            assert a["value"]["status"] != "present" and b["value"]["status"] == "present", path
            assert b["rule"] == [cite("agentdojo.injection_marker_yaml@1"), cite(R_UNESCAPE)]
            assert cite(R_UNESCAPE) == "agentdojo.autodojo_payload_unescape_unverified@1" and b["ev"] == "I"
            fixture = linked[b["value"]["fixture"]]
            assert {"id": fixture["id"], "p": "/ext/autodojo/cache_match"} in b["premises"]
            assert markers.autodojo_unescape(fixture["content"]) != fixture["content"]  # only an escaped payload gains
            gained += 1
        stripped = _edited(doc, _strip_autodojo)
        cite = sem_citations(stripped).cite
        assert _v2_common(ss.annotation_records(v2().annotate(stripped))) == [
            _as_v2(r, cite) for r in ss.annotation_records(ts.profile().annotate(stripped))], path
    assert gained, "no AutoDojo fixture gained a marker"
    assert markers.autodojo_unescape(yaml_escape('say "hi"\n\tnow \\ done')) == 'say "hi"\n\tnow \\ done'


def _strip_autodojo(record: dict[str, Any]) -> None:
    if record.get("k") == "fixture" and isinstance(record.get("ext"), dict):
        record["ext"].pop("autodojo", None)
        if not record["ext"]:
            record.pop("ext")



def test_the_reviewed_rules_are_active_class_i_rules_of_the_catalogue():
    catalogue = load_catalogue("agentdojo")
    for ref in (R_REVIEWED_TABLE, R_REVIEWED_LABEL):
        entry = catalogue.get(ref)
        assert entry is not None and entry.citable and entry.status == "active" and entry.cls == "I", ref
    assert R_REVIEWED_TABLE in v2().classes and R_REVIEWED_TABLE not in ts.profile().classes


# ------------------------------------------------------------------------------------------------ the tables
def test_reviewed_tables_are_well_formed():
    doc = _reviewed_doc()
    keys = [(t["benchmark"], t["suite"]) for t in doc["table"]]
    assert keys == [("craibench", "crypto_trading"), ("craibench", "chain")]
    for table in doc["table"]:
        assert table["repo"] == CRAIBENCH.repo
        for state in table["code_state"]:
            assert len(state["commit"]) == 40 and state["commit"].startswith(state["id"])
            assert state["runs"] and state["basis"]
            assert all(len(f["blob"]) == 40 and f["path"].startswith("src/agentdojo/") for f in state["files"])
            (suite_file,) = [f for f in state["files"] if f["path"].endswith("/task_suite.py")]
            assert suite_file["note"].endswith(f": {len(state['tools'])} tools"), state["id"]  # the whole TOOLS list
            for tool, entry in state["tools"].items():
                assert set(entry["roles"]) <= set(ROLE_VALUES) and entry["integrity"] in INTEGRITY_VALUES, tool
                assert entry["integrity"] != "trusted", tool  # nothing here verifies a tool's output
                assert ("channel" in entry) == ("content_source" in entry["roles"]), tool
                assert entry["code"].split(" l. ")[0] in {f["path"].rsplit("/", 1)[1] for f in state["files"]}, tool
                assert entry["reason"], tool
    reviewed = v2().tables.reviewed
    assert set(reviewed[("craibench", "crypto_trading")]) == CRYPTO_TOOLS
    assert "secure_funds" not in CRYPTO_TOOLS  # the pin's name; the runs called siphon (renamed after them)
    siphon = reviewed[("craibench", "crypto_trading")]["siphon"]
    assert (siphon.roles, siphon.integrity, siphon.channel) == (("send_sink",), "unknown", None)
    assert reviewed[("craibench", "crypto_trading")]["getRecentPricesFromOracle"].channel == "price_feed"


def test_chain_keeps_only_the_tools_labelled_alike_in_both_states():
    doc = _reviewed_doc()
    (chain,) = [t for t in doc["table"] if t["suite"] == "chain"]
    a, b = chain["code_state"]
    assert (a["id"], b["id"]) == ("a512e34a", "f87dbc74")
    assert set(b["tools"]) - set(a["tools"]) == {"siphon"}
    def label(state: dict[str, Any], tool: str) -> tuple[Any, ...]:
        entry = state["tools"][tool]
        return entry["roles"], entry["integrity"], entry.get("channel")

    differ = {tool for tool in a["tools"] if label(a, tool) != label(b, tool)}
    assert differ == {"bridge", "stake", "airdrop", "deploy_token_contract"}  # code state a only returns a message
    assert set(v2().tables.reviewed[("craibench", "chain")]) == CHAIN_KNOWN == set(a["tools"]) - differ
    # the rule, on edited data: one state alone keeps all its tools; a label that differs drops the tool
    chain["code_state"] = [b]
    assert set(_parse_reviewed(doc).reviewed[("craibench", "chain")]) == set(b["tools"])
    chain["code_state"] = [a, b]
    a["tools"]["transfer"] = dict(a["tools"]["transfer"], roles=["write_sink"])
    assert set(_parse_reviewed(doc).reviewed[("craibench", "chain")]) == CHAIN_KNOWN - {"transfer"}


def _siphon(doc: dict[str, Any]) -> dict[str, Any]:
    entry: dict[str, Any] = doc["table"][0]["code_state"][0]["tools"]["siphon"]
    return entry


@pytest.mark.parametrize(("edit", "message"), [
    (lambda d: d["table"][0].update(benchmark="agentdojo"), "other than 'agentdojo'"),
    (lambda d: d["table"].append(dict(d["table"][0])), "a second table"),
    (lambda d: _siphon(d).update(integrity="untrusted"), "content_source"),
    (lambda d: _siphon(d).update(roles=["neutral", "send_sink"]), "neutral alone"),
    (lambda d: _siphon(d).update(roles=["unknown"]), "never unknown"),
    (lambda d: _siphon(d).update(reason=""), "evidence"),
    (lambda d: _siphon(d).update(note="x"), "unknown keys"),
    (lambda d: d["table"][1]["code_state"][1].update(id="a512e34a"), "distinct ids"),
    (lambda d: d["table"][0].update(code_state=[]), "no [[table.code_state]]"),
])
def test_malformed_reviewed_tables_are_refused(edit, message):  # type: ignore[no-untyped-def]
    doc = _reviewed_doc()
    edit(doc)
    with pytest.raises(ProfileDataError, match=message.replace("[", r"\[").replace("]", r"\]")):
        _parse_reviewed(doc)


def test_version_1_refuses_reviewed_tables_and_version_2_requires_them():
    files = _files(DIR_1)
    with pytest.raises(ProfileDataError):
        parse_tables({**files, "reviewed_tables.toml": _files(DIR_2)["reviewed_tables.toml"]}, 1)
    with pytest.raises(ProfileDataError):
        parse_tables({k: v for k, v in _files(DIR_2).items() if k != "reviewed_tables.toml"}, 2)
    with pytest.raises(ProfileDataError):  # version 2's data under version 1's header
        parse_tables(_files(DIR_2), 1)
    with pytest.raises(ProfileDataError):
        parse_tables(files, 3)


# ------------------------------------------------------------------------------------------------ selection
def test_reviewed_selection():
    doc = _craibench_log("chain", [("getBalance", "1000.0")])
    assert doc.header["task"]["benchmark"] == "craibench" and doc.header["task"]["suite"] == "chain"
    known, premises = v2().known_tools(doc)
    assert known == CHAIN_KNOWN
    assert [(p.id, p.p) for p in premises] == [("exec", "/task/benchmark"), ("exec", "/task/suite")]
    assert ts.profile().known_tools(doc)[0] == frozenset()  # version 1: fail-closed, as before
    bench = doc.get("bench")
    assert bench is not None
    bench["version"] = "v1.2.2"  # a recorded suite-version label: the review covers unlabelled runs only
    known, premises = v2().known_tools(doc)
    assert known == frozenset() and ("bench", "/version") in [(p.id, p.p) for p in premises]
    del bench["version"]
    doc.header["task"]["suite"] = "banking"  # CrAIBench's banking logs are benchmark agentdojo; no craibench table
    assert v2().known_tools(doc)[0] == frozenset()
    doc.header["task"]["benchmark"] = "agentdojo"
    assert v2().known_tools(doc) == ts.profile().known_tools(doc)


# ------------------------------------------------------------------------------------------------ annotation
def test_reviewed_labels_annotate_craibench_runs():
    doc = _craibench_log("crypto_trading", [("getTransactions", "[]"), ("siphon", "{}"), ("exchangeFiat", "{}"),
                                            ("secure_funds", "{}")])
    labels = _labels(v2(), doc)
    reviewed = (R_REVIEWED_LABEL, R_REVIEWED_TABLE)
    assert labels["getTransactions"] == (["content_source"], "untrusted", reviewed)
    assert labels["siphon"] == (["send_sink"], "unknown", reviewed)
    assert labels["exchangeFiat"] == (["send_sink"], "unknown", reviewed)
    assert labels["secure_funds"] == (["unknown"], "unknown", ("agentdojo.unknown_tool@1", R_REVIEWED_TABLE))
    anns = list(v2().annotate(doc))
    channels = [a for a in anns if a.type == "channel"]
    assert [(a.value, a.rule) for a in channels] == [("transaction", reviewed)]
    # version 1 knows none of them (fail-closed): every role unknown, never trusted
    assert {json.dumps(v[0]) for v in _labels(ts.profile(), doc).values()} == {'["unknown"]'}
    # chain: bridge differs between the two code states, so it stays unknown; transfer is known
    labels = _labels(v2(), _craibench_log("chain", [("transfer", "{}"), ("bridge", "{}"), ("siphon", "{}")]))
    assert labels["transfer"] == (["send_sink"], "unknown", reviewed)
    assert labels["bridge"][0] == labels["siphon"][0] == ["unknown"]


def _sem_prov_tier4(doc: AerDocument) -> tuple[Any, Any]:
    from agentprov.prov.engine import derive
    from agentprov.validate import validate_prov

    prof = v2()
    sem = annotate(doc, prof)
    report = validate_sem_document(sem, doc, profile=prof)
    assert report.ok, sorted(report.codes())
    result = derive(doc, [sem], sem_profiles={(prof.id, prof.version): prof})
    prov = validate_prov(result.prov_json, doc, sems=[sem])
    assert prov.ok, sorted(prov.codes())
    return sem, result


def _taints(result: Any) -> list[dict[str, Any]]:
    """The assessment bodies stated under the profile's taint policy (apv:PotentiallyInfluencedBy, EF E.7.3)."""
    doc = json.loads(result.prov_json)
    sections = [s for bundle in doc.get("bundle", {}).values() for s in bundle.values() if isinstance(s, dict)]
    return [body for section in sections for body in section.values()
            if isinstance(body, dict) and body.get("apv:policy") == "agentdojo.taint_sink_untrusted@1"]


def test_a_synthetic_craibench_run_derives_taint_through_the_reviewed_labels():
    """siphon (send_sink) issued after getTransactions (untrusted) is a taint subject exposed to it (EF E.7.3); with no
    sink and no unknown tool there is no taint."""
    doc = _craibench_log("crypto_trading", [("getTransactions", "[]"), ("siphon", "{}")])
    _sem, result = _sem_prov_tier4(doc)
    assessment = [b for b in result.bundles if b.kind == "assessment"]
    assert len(assessment) == 1 and assessment[0].profile == "agentdojo.suites@2"
    taints = _taints(result)
    assert taints and all("aprov.a_taint@1" in body["apv:method"] for body in taints)
    _sem, control = _sem_prov_tier4(_craibench_log("crypto_trading", [("getRecentPricesFromOracle", "[]"),
                                                                       ("getTransactions", "[]")]))
    assert _taints(control) == []


def test_the_real_craibench_fixtures_annotate_validate_and_derive():
    reviewed = v2().tables.reviewed
    seen: set[str] = set()
    for entry in fixture_entries(CRAIBENCH):
        m = map_fixture(CRAIBENCH, entry)
        doc = load_aer_bytes(m.data)
        suite = doc.header["task"]["suite"]
        sem, _result = _sem_prov_tier4(doc)
        table = reviewed.get(("craibench", suite)) if doc.header["task"]["benchmark"] == "craibench" else None
        for name, (role, integrity, rules) in _labels(v2(), doc).items():
            seen.add(f"{suite}/{name}")
            if table is not None and name in table:
                assert role == list(table[name].roles) and integrity == table[name].integrity, name
                assert rules == (R_REVIEWED_LABEL, R_REVIEWED_TABLE), name
            elif table is not None:
                assert role == ["unknown"] and integrity == "unknown", name
    assert seen, "no tool executions in the CrAIBench fixtures"
