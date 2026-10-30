"""The ``inspect.atia@1`` semantics profile (DECISIONS D-307 addendum: orchestrator request 2026-10-21; fail-closed like
D-601's ``inspect.whistlebench@1``; docs/architecture D.9.15, C.14.1-C.14.4; H.2.5).

The profile reads only the AER: every tool is fail-closed (``inspect.untabulated_tool@1``, class I) and no judgement gets
an outcome (the run-time scorer code is not at a pinned identity, and its polarity differs between the logs, pre-check
PC-atia-benchmark-01). No ATIA log is committed (D-309), so the checks run over synthetic ``inspect_ai 0.3.112``-shaped
AERs (a tool-call sample with media inputs, and a sample without a tool call), and over the smallest pinned log when the
fetch cache holds it (``slow``): the SEM validates in release mode (tier 3), cites only the inspect catalogue at the
version the AER declares (one catalogue version per corpus), and PROV derived with it passes tier 4. Nothing here prints
log content (R-42).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import inspect_support as support
import pytest

from agentprov.adapters.inspect.semantics import build_profile
from agentprov.adapters.profiles import load_profile
from agentprov.adapters.registry import get_source
from agentprov.adapters.semantics_profiles import load_semantics_profile
from agentprov.aer.reader import AerDocument, load_aer_bytes
from agentprov.aer.rules import RuleRegistry, load_catalogue
from agentprov.sem.engine import annotate, dumps_sem
from agentprov.sem.profiles import SemanticsProfileError, profile_digest
from agentprov.sem.types import SemanticsProfile
from agentprov.sem.validate import validate_sem_document

SEMANTICS = support.REPO / "src" / "agentprov" / "adapters" / "inspect" / "semantics" / "inspect.atia-1"
RULE = "inspect.untabulated_tool@1"
IMAGE = "data:image/png;base64,c3ludGhldGljLWltYWdl"


def profile() -> SemanticsProfile:
    return load_semantics_profile("inspect.atia", 1)


def _atia_shape(s: support.Sample, sample: dict[str, Any]) -> None:
    """0.3.112: no ``message_id`` on the tool event; an image input as an attachment; one ``harmful_tool_invoked`` score."""
    for event in sample["events"]:
        if event["event"] == "tool":
            del event["message_id"]
        if event["event"] == "score":
            event["scorer"] = "harmful_tool_invoked"
            event["score"] = {"value": "C", "answer": "get_x", "explanation": "Synthetic.", "metadata": {}, "history": []}
    s.attachments.update({"img0": IMAGE})
    user = next(m for m in sample["messages"] if m["role"] == "user")
    user["content"] = [{"type": "text", "text": "Synthetic task prompt."},
                       {"type": "image", "image": "attachment://img0", "detail": "auto"}]
    sample["scores"] = {"harmful_tool_invoked": {"value": "C", "answer": "get_x", "explanation": "Synthetic.",
                                                 "metadata": {}, "history": []}}
    sample["metadata"] = {"attack_type": "synthetic", "benign_tools": ["get_y"], "harmful_tools": ["get_x"],
                          "insight": "Synthetic."}


def _no_call_sample(sid: str) -> dict[str, Any]:
    """An ATIA sample without a tool call (42 of the 123): one model call, a final answer, one ``I`` score."""
    s = support.Sample(sid)
    init = s.span("SpanInit00000000000000", "init", "init")
    s.event("sample_init", init, sample={"input": "Synthetic task prompt.", "target": "", "id": sid, "metadata": {}},
            state={"messages": []})
    s.end(init)
    solvers = s.span("SpanSolvers00000000000", "solvers", "solvers")
    gen = s.span("SpanGenerate0000000000", "solver", "generate", solvers)
    system, user = s.msg("system", "You are a synthetic agent."), s.msg("user", "Synthetic task prompt.", source="input")
    answer = s.msg("assistant", "Synthetic final answer.", source="generate", model="synthetic")
    tools = [{"name": "get_x", "description": "Synthetic tool.", "parameters": {"type": "object", "properties": {}}}]
    s.model(gen, "google/synthetic-agent", [system, user], answer, tools=tools)
    s.end(gen)
    s.end(solvers)
    s.messages.extend([system, user, answer])
    scorers = s.span("SpanScorers00000000000", "scorers", "scorers")
    scorer = s.span("SpanScorer000000000000", "scorer", "harmful_tool_invoked", scorers)
    score = {"value": "I", "answer": "[]", "explanation": "Synthetic.", "metadata": {}, "history": []}
    s.event("score", scorer, score=score, target="", intermediate=False, scorer="harmful_tool_invoked", scorer_args={},
            model_usage={})
    s.end(scorer)
    s.end(scorers)
    return s.build(scores={"harmful_tool_invoked": score})


def _synthetic(tmp_path: Path, sid: str = "s1", *, call: bool = True) -> AerDocument:
    header = support.synthetic_header("0.3.112")
    header["eval"]["task"] = "account_takeover_suite"
    sample = support.basic_sample(sid, tune=_atia_shape) if call else _no_call_sample(sid)
    imported = support.import_log(support.build_eval(header, {f"{sid}_epoch_1.json": sample}),
                                  tmp_path, path="logs/x.eval", profile=load_profile("atia-benchmark"))
    (unit,) = imported.units
    assert not unit.outcome.degenerate
    return load_aer_bytes(unit.data)


def _cached_docs(tmp_path: Path) -> list[AerDocument]:
    import test_atia as atia

    path = min(atia.LOGS, key=lambda p: atia.LOGS[p][1])
    try:
        data = atia._cached_blob(path)
    except Exception as exc:  # an absent cache or blob: this test needs the user-approved fetch
        pytest.skip(f"the pinned ATIA log is not in the fetch cache ({type(exc).__name__})")
    if data is None:
        pytest.skip("the pinned ATIA log is not in the fetch cache")
    imported = support.import_log(data, tmp_path, path=path, profile=load_profile("atia-benchmark"))
    return [load_aer_bytes(u.data) for u in imported.units]


def _check_fail_closed(doc: AerDocument) -> int:
    anns = list(profile().annotate(doc))
    roles = {a.target: a.value for a in anns if a.type == "role"}
    integrity = {a.target: a.value for a in anns if a.type == "integrity"}
    assert {a.type for a in anns} <= {"role", "integrity"}  # no outcome, channel, marker or author
    for te in doc.of_kind("tool_execution"):
        assert roles.pop(te["id"]) == ["unknown"]
    for msg in doc.of_kind("message"):
        for i, part in enumerate(msg["parts"]):
            target = f"{msg['id']}#{i}"
            if part["t"] == "tool_call":
                assert roles.pop(target) == ["unknown"]
            elif part["t"] == "tool_result":
                assert integrity.pop(target) == "unknown"
    assert roles == {} and integrity == {}
    assert {r for a in anns for r in a.rule} == ({RULE} if anns else set())
    assert all(a.ev == "I" for a in anns)
    return len(anns)


def _check_tiers(doc: AerDocument) -> None:
    from agentprov.prov.engine import derive
    from agentprov.validate import validate_prov

    prof = profile()
    sem = annotate(doc, prof)
    assert json.loads(dumps_sem(sem).split(b"\n", 1)[0])["rules"] == {"inspect": 2}
    report = validate_sem_document(sem, doc, catalogues=RuleRegistry.default(), mode="release", profile=prof)
    assert report.ok, [(f.code, f.pointer) for f in report.errors]
    result = derive(doc, [sem], sem_profiles={(prof.id, prof.version): prof})
    prov = validate_prov(result.prov_json, doc, sems=[sem])
    assert prov.ok, [(o.id, sorted(o.codes())) for o in prov.outcomes if o.status == "fail"]


def test_the_profile_is_found_by_convention_and_cites_the_inspect_catalogue_version_2():
    prof = profile()
    assert isinstance(prof, SemanticsProfile)
    assert (prof.id, prof.version, dict(prof.rules), dict(prof.ns), prof.taint_policy) == \
        ("inspect.atia", 1, {"inspect": 2}, {}, None)
    files = {p.name: p.read_bytes() for p in SEMANTICS.iterdir() if p.is_file()}
    assert set(files) == {"tables.toml"} and prof.sha256 == profile_digest(files)
    assert files["tables.toml"].count(b"EMPTY ON PURPOSE") == 2  # no tool and no scorer is tabulated
    assert load_catalogue("inspect").version == 2


def test_the_registry_part_selects_it_and_the_aer_declares_the_same_catalogue_version(tmp_path):
    (part,) = get_source("atia-benchmark").capabilities
    assert part.semantics == ("inspect.atia@1",)
    doc = _synthetic(tmp_path)
    assert doc.header["rules"]["inspect"] == profile().rules["inspect"]  # H.2.5: one catalogue version per corpus


def test_every_tool_is_fail_closed_and_no_outcome_is_claimed(tmp_path):
    doc = _synthetic(tmp_path)
    assert doc.of_kind("tool_execution") and doc.of_kind("judgement")  # a scored call; no claim is read from it
    assert _check_fail_closed(doc) == 3  # the call part, the execution and the result part
    bare = _synthetic(tmp_path / "bare", call=False)
    assert not bare.of_kind("tool_execution") and bare.of_kind("judgement")
    assert _check_fail_closed(bare) == 0  # no tool, so no annotation (and still no outcome)


def test_the_cited_rule_is_class_i_active_and_in_the_declared_catalogue_version():
    entry = load_catalogue("inspect", 2).get(RULE)
    assert entry is not None and entry.citable and entry.status == "active" and entry.cls == "I"
    source = (support.REPO / "src/agentprov/adapters/inspect/semantics/atia.py").read_text(encoding="utf-8")
    assert set(re.findall(r'"(inspect\.[a-z_]+@[0-9]+)"', source)) == {RULE}


def test_the_sem_validates_in_release_mode_and_prov_passes_tier_4(tmp_path):
    _check_tiers(_synthetic(tmp_path))
    _check_tiers(_synthetic(tmp_path / "bare", call=False))


def test_annotate_is_deterministic(tmp_path):
    doc = _synthetic(tmp_path)
    again = _synthetic(tmp_path / "again")  # an independent mapping of the same log
    assert dumps_sem(annotate(doc, profile())) == dumps_sem(annotate(again, profile()))
    assert list(profile().annotate(doc)) == list(profile().annotate(doc))


@pytest.mark.parametrize("tables", [
    b'[tool_policy]\nknown_tools = ["get_x"]\nrole = ["unknown"]\nintegrity = "unknown"\n',
    b'[tool_policy]\nknown_tools = []\nrole = ["send_sink"]\nintegrity = "unknown"\n',
    b'[tool_policy]\nknown_tools = []\nrole = ["unknown"]\nintegrity = "trusted"\n',
    b'[tool_policy]\nknown_tools = []\nrole = ["unknown"]\nintegrity = "unknown"\n'
    b'[[scorer]]\njudgement = "harmful_tool_invoked"\n',
    b'[tool_policy]\nknown_tools = []\nrole = ["unknown"]\nintegrity = "unknown"\n[taint_policy]\nrequest = ["unknown"]\n',
])
def test_a_table_that_claims_more_than_fail_closed_is_refused(tables: bytes):
    with pytest.raises(SemanticsProfileError):
        build_profile("inspect.atia", 1, {"tables.toml": tables}, "0" * 64)


def test_an_unknown_version_or_an_extra_file_is_refused():
    data: dict[str, Any] = {"tables.toml": (SEMANTICS / "tables.toml").read_bytes()}
    with pytest.raises(SemanticsProfileError):
        build_profile("inspect.atia", 2, data, "0" * 64)
    with pytest.raises(SemanticsProfileError):
        build_profile("inspect.atia", 1, {**data, "scorers.toml": b""}, "0" * 64)


def test_the_whistlebench_and_agentharm_profiles_are_unchanged_by_the_dispatch():
    for ref, cls in (("inspect.whistlebench@1", "InspectWhistleBenchProfile"),
                     ("inspect.agentharm@2", "InspectAgentHarmProfile")):
        pid, version = ref.split("@")
        assert type(load_semantics_profile(pid, int(version))).__name__ == cls


@pytest.mark.slow
def test_the_smallest_pinned_log_is_fail_closed_and_passes_tiers_3_and_4(tmp_path):
    docs = _cached_docs(tmp_path)
    assert len(docs) == 19
    assert sum(_check_fail_closed(doc) for doc in docs) > 0
    assert all(doc.header["rules"]["inspect"] == 2 for doc in docs)
    for doc in docs:
        _check_tiers(doc)
