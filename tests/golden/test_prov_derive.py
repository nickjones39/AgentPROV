"""``agentprov-prov/0.1`` on the golden v1 AERs (PQ phase 5 exit; J.3.5 gate D cross-counts; E.9 golden digests).

For every golden pair: map the transcript to an AER (as gates A1/A2 do), derive twice and compare bytes, then check the
J.3.5 invariants that are decidable per execution:

- ``ToolExecution`` activities = tool executions; request entities = tool-call parts; requests without execution carry
  ``apv:NotDispatched`` exactly when the seal lists them under ``unexecuted_tool_call``;
- ``ModelInvocation`` activities that generate a held assistant message = assistant messages with a generator;
- ``wasGeneratedBy(output, ToolExecution)`` = one per tool execution (its result part, or ``te.out`` under a defence);
- context membership (``aprov.use_context@1``) never in the core, only in inference bundles whose method set holds
  ``adprov.context_is_prefix@1`` (AD-05; R-05);
- 0 statements from G-ACT, G-USE, G-GEN or G-ASSOC (migration AERs hold no generic records);
- no relation carries a time, no ``"0"``/``""`` time literal, and every ``prov:startTime``/``endTime`` restates a
  typed AER ``t`` value.

The PROV-JSON digests are compared with ``prov_digests.json`` (committed; E.9 item 4.1). Regenerate it deliberately with
``AGENTPROV_REGEN_PROV_DIGESTS=1`` after a spec or catalogue version bump. Failures print ids and digests only.
"""

from __future__ import annotations

import json
import os
import sys
from functools import cache
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_v1_round_trip as v1  # noqa: E402

from agentprov.adapters.runner import aer_bytes, map_artefact  # noqa: E402
from agentprov.aer.reader import AerDocument, load_aer  # noqa: E402
from agentprov.prov.engine import ProvDerivation, derive  # noqa: E402
from agentprov.prov.serialise.time import prov_time  # noqa: E402

DIGESTS = Path(__file__).resolve().parent / "prov_digests.json"
REGEN = "AGENTPROV_REGEN_PROV_DIGESTS"
GENERIC = {"aprov.g_act@1", "aprov.g_use@1", "aprov.g_gen@1", "aprov.g_assoc@1"}
NODE = ("entity", "activity", "agent")


@cache
def _derived(pair_id: str, tmp: Path) -> tuple[AerDocument, ProvDerivation, bytes]:
    pair = next(p for p in v1.PAIRS if p.id == pair_id)
    outcome, _ = map_artefact(v1._source(pair), v1._origin(pair), profile_id="adprov-v1")
    data, _ = aer_bytes(outcome)
    path = tmp / f"{pair_id}.aer.jsonl"
    path.write_bytes(data)
    doc = load_aer(path)
    first = derive(doc)
    second = derive(doc)
    return doc, first, second.prov_json


@pytest.fixture
def derived(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory) -> tuple[AerDocument, ProvDerivation, bytes]:
    pair = request.param
    if pair is None:
        v1._require()
    return _derived(pair.id, tmp_path_factory.getbasetemp())


def _ids() -> list[Any]:
    return v1._ids()


def statements(result: ProvDerivation) -> list[tuple[str, str, str, dict[str, Any]]]:
    out = []
    for iri, bundle in result.document["bundle"].items():
        for section, items in bundle.items():
            for ident, body in items.items():
                out.append((iri, section, ident, body))
    return out


def types_of(body: dict[str, Any]) -> set[str]:
    value = body.get("prov:type", [])
    return {v["$"] for v in (value if isinstance(value, list) else [value])}


@pytest.mark.parametrize("derived", _ids(), indirect=True)
def test_derivation_is_deterministic(derived: tuple[AerDocument, ProvDerivation, bytes]) -> None:
    _doc, result, again = derived
    assert result.prov_json == again


@pytest.mark.parametrize("derived", _ids(), indirect=True)
def test_gate_d_cross_counts(derived: tuple[AerDocument, ProvDerivation, bytes]) -> None:
    doc, result, _ = derived
    stmts = statements(result)
    nodes = {ident: (iri, body) for iri, section, ident, body in stmts if section in NODE}
    tool_exec = [r for r in doc.records if r.get("k") == "tool_execution"]
    assert sum("apv:ToolExecution" in types_of(b) for _, b in nodes.values()) == len(tool_exec)
    calls = [f"{m['id']}#{k}" for m in doc.of_kind("message") for k, p in enumerate(m.get("parts", []))
             if p.get("t") == "tool_call"]
    requests = {i for i, (_, b) in nodes.items() if "apv:ToolCallRequest" in types_of(b)}
    assert requests == {"x:" + c.replace("#", "-") for c in calls}
    executed = {r["call"] for r in tool_exec if "call" in r}
    listed = {i for issue in doc.seal["issues"] if issue["code"] == "unexecuted_tool_call" for i in issue["ids"]}
    not_dispatched = {i for i, (_, b) in nodes.items() if b.get("apv:dispatchStatus", {}).get("$") == "apv:NotDispatched"}
    assert not_dispatched == {"x:" + c.replace("#", "-") for c in listed}
    assert listed == set(calls) - executed
    assistant = [m for m in doc.of_kind("message") if m["role"] == "assistant" and "generated_by" in m]
    gen_assistant = {b["prov:activity"] for _, s, _, b in stmts if s == "wasGeneratedBy"
                     and b.get("apv:rule") == "aprov.gen_message@1" and b["prov:entity"] in {"x:" + m["id"] for m in assistant}}
    assert len(gen_assistant) == len({m["generated_by"] for m in assistant}) == len(assistant)
    te_ids = {"x:" + r["id"] for r in tool_exec}
    gen_result = [b for _, s, _, b in stmts if s == "wasGeneratedBy" and b.get("apv:rule") == "aprov.gen_result@1"
                  and b["prov:activity"] in te_ids]
    # one output per tool turn (J.3.5): the tool_result part, or the pre-decision ``te.out`` when a defence generated
    # the recorded result (PI detector, C05)
    assert sorted(b["prov:activity"] for b in gen_result) == sorted(te_ids)


@pytest.mark.parametrize("derived", _ids(), indirect=True)
def test_context_membership_is_inferred_and_generic_rules_are_silent(
    derived: tuple[AerDocument, ProvDerivation, bytes],
) -> None:
    _doc, result, _ = derived
    for iri, _section, _ident, body in statements(result):
        rule = body.get("apv:rule")
        assert rule not in GENERIC
        if rule == "aprov.use_context@1":
            assert ".core." not in iri and "adprov-context_is_prefix-v1" in iri
            assert body["apv:evidenceClass"]["$"] == "apv:Inferred"
    assert result.report.rules_fired.keys().isdisjoint(GENERIC)


@pytest.mark.parametrize("derived", _ids(), indirect=True)
def test_times_restate_typed_aer_values_only(derived: tuple[AerDocument, ProvDerivation, bytes]) -> None:
    doc, result, _ = derived
    typed = {prov_time(r["t"][end]) for r in doc.records if isinstance(r.get("t"), dict)
             for end in ("start", "end") if end in r["t"]} - {None}
    for _iri, section, _ident, body in statements(result):
        for key in ("prov:startTime", "prov:endTime", "prov:time"):
            if key in body:
                assert section == "activity", "no relation carries a time"
                assert body[key] in typed and body[key] not in ("0", "")


@pytest.mark.parametrize("derived", _ids(), indirect=True)
def test_core_holds_no_inferred_statement(derived: tuple[AerDocument, ProvDerivation, bytes]) -> None:
    _doc, result, _ = derived
    for iri, _section, ident, body in statements(result):
        if ".core." in iri and "apv:evidenceClass" in body:
            assert body["apv:evidenceClass"]["$"] != "apv:Inferred", ident


def test_golden_digests_are_committed(tmp_path_factory: pytest.TempPathFactory) -> None:
    v1._require()
    produced = {p.id: _derived(p.id, tmp_path_factory.getbasetemp())[1].digests["prov_json"] for p in v1.PAIRS}
    if os.environ.get(REGEN):
        DIGESTS.write_text(json.dumps(dict(sorted(produced.items())), indent=2) + "\n", encoding="utf-8")
    expected = json.loads(DIGESTS.read_text(encoding="utf-8"))
    changed = {k: (expected.get(k), v) for k, v in produced.items() if expected.get(k) != v}
    assert changed == {}, f"PROV-JSON digests changed without a version bump: {sorted(changed)}"


@pytest.mark.parametrize("derived", _ids(), indirect=True)
def test_assumption_rules_fire_as_inferred(derived: tuple[AerDocument, ProvDerivation, bytes]) -> None:
    """EF E.10 item 21: start_tool@1, the runtime delegation and the assumed checker inputs fire on v1 AERs, INFERRED,
    in the bundles of the asserted assumption rules; the synthetic checker run itself stays in the core (DERIVED)."""
    doc, result, _ = derived
    stmts = statements(result)
    # the bundle names every method of the statement: the auto-execution assumption, with the twins of the structural
    # adprov rules that cite no code (D-27 c6) where the execution's call link or its request's generator rests on them
    auto = "agentdojo-auto_execution_unverified-v1"
    called = [r for r in doc.records if r.get("k") == "tool_execution" and "call" in r]
    starts = [(iri, b) for iri, s, _, b in stmts if s == "wasStartedBy" and b.get("apv:rule") == "aprov.start_tool@1"]
    assert len(starts) == len(called) and all(auto in iri for iri, _ in starts)
    delegations = [iri for iri, s, _, b in stmts if s == "actedOnBehalfOf" and b.get("apv:rule") == "aprov.assoc_tool@1"]
    assert len(delegations) == len(called) and all(auto in iri for iri in delegations)
    checkers = [r for r in doc.records if r.get("k") == "judgement" and r.get("origin") == "checker"]
    runs = {i for iri, s, i, b in stmts if s == "activity" and "apv:CheckerRun" in types_of(b)}
    assert runs == {f"x:{j['id']}.check" for j in checkers}
    for iri, s, _ident, b in stmts:
        if s == "used" and b.get("apv:rule") == "aprov.outcome@1":
            assert "agentdojo-checker_inputs_unverified-v1" in iri and b["prov:activity"] in runs
