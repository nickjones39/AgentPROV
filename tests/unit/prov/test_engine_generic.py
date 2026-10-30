"""The generic kinds and extension constructs derive their named PROV statements (EF F.2.6, C.3.15; AD-15; PQ phase 5
exit "synthetic generic-kind fixtures derive their named statements"; the PROV half of K.6.4 / DoD Q.3).

Every assertion is by rule id and arguments, on a synthetic ``tst`` execution built in ``prov_support``.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import prov_support as ps  # noqa: E402

from agentprov.aer.rules import RuleEntry  # noqa: E402
from agentprov.prov.engine import ProvDerivation, ProvDerivationError, derive  # noqa: E402

Stmt = tuple[str, str, tuple[tuple[str, str], ...]]  # (bundle kind, rule, sorted prov: arguments)


def run(tmp_path: Path, records: list[dict[str, Any]] | None = None, **kw: Any) -> ProvDerivation:
    reg = kw.pop("registry", None) or ps.registry()
    doc = ps.write_aer(records or ps.generic_records(), tmp_path / "g.aer.jsonl")
    assert ps.check_valid(doc, reg) == []
    return derive(doc, registry=reg, **kw)


def statements(result: ProvDerivation) -> list[dict[str, Any]]:
    out = []
    for iri, bundle in result.document["bundle"].items():
        kind = "core" if ".core." in iri else "inf"
        for section, items in bundle.items():
            for ident, body in items.items():
                out.append({"bundle": kind, "section": section, "id": ident, **body})
    return out


def find(result: ProvDerivation, section: str, rule: str | None = None, **args: str) -> list[dict[str, Any]]:
    keys = {k.replace("__", ":"): v for k, v in args.items()}
    return [s for s in statements(result) if s["section"] == section and (rule is None or s.get("apv:rule") == rule)
            and all(s.get(k) == v for k, v in keys.items())]


def one(result: ProvDerivation, section: str, rule: str, **args: str) -> dict[str, Any]:
    found = find(result, section, rule, **args)
    assert len(found) == 1, (section, rule, args, len(found))
    return found[0]


def types_of(body: dict[str, Any]) -> set[str]:
    value = body.get("prov:type", [])
    return {v["$"] for v in (value if isinstance(value, list) else [value])}


@pytest.fixture(scope="module")
def result(tmp_path_factory: pytest.TempPathFactory) -> ProvDerivation:
    return run(tmp_path_factory.mktemp("generic"))


def test_planner_step(result: ProvDerivation) -> None:
    node = one(result, "activity", "aprov.g_act@1", id="x:ac0")
    assert types_of(node) == {"apv:GenericActivity"} and node["apv:activityType"] == "tst:plan"
    assert node["prov:label"] == "plan"
    use = one(result, "used", "aprov.g_use@1", prov__activity="x:ac0", prov__entity="x:m1")
    assert use["prov:role"]["$"] == "apv:ActivityInput" and use["apv:inputIndex"] == 0
    assoc = one(result, "wasAssociatedWith", "aprov.g_assoc@1", prov__activity="x:ac0", prov__agent="x:agent")
    assert assoc["prov:role"]["$"] == "apv:PerformerRole"
    one(result, "wasGeneratedBy", "aprov.g_gen@1", prov__entity="x:af0", prov__activity="x:ac0")
    comm = one(result, "wasInformedBy", "aprov.comm@1", prov__informed="x:ac0", prov__informant="x:mc0")
    assert comm["bundle"] == "core" and comm["apv:viaEntity"]["$"] == "x:m1"
    premises = {p["$"] for p in comm["apv:premise"]}
    assert {"x:" + s["id"].removeprefix("x:") for s in find(result, "used", "aprov.g_use@1", prov__activity="x:ac0")} <= premises


def test_memory_write_and_read_communicate_through_the_item(result: ProvDerivation) -> None:
    one(result, "used", "aprov.g_use@1", prov__activity="x:ac1", prov__entity="x:m1-0")
    one(result, "wasGeneratedBy", "aprov.g_gen@1", prov__entity="x:af1", prov__activity="x:ac1")
    one(result, "used", "aprov.g_use@1", prov__activity="x:ac2", prov__entity="x:af1")
    comm = one(result, "wasInformedBy", "aprov.comm@1", prov__informed="x:ac2", prov__informant="x:ac1")
    assert comm["apv:viaEntity"]["$"] == "x:af1" and len(comm["apv:premise"]) == 2


def test_screenshot_artefact_binds_the_blob_digest(result: ProvDerivation) -> None:
    node = one(result, "entity", "aprov.n_artefact@1", id="x:af2")
    assert types_of(node) == {"apv:GenericArtefact"}
    assert node["apv:contentSha256"] == ps.BLOB_SHA and node["apv:mediaType"] == "image/png"
    one(result, "wasGeneratedBy", "aprov.g_gen@1", prov__entity="x:af2", prov__activity="x:ac3")
    assert find(result, "used", "aprov.g_use@1", prov__activity="x:ac3") == []  # inputs: [] -> no usage


def test_hand_off_starts_the_sub_agent(result: ProvDerivation) -> None:
    start = one(result, "wasStartedBy", "aprov.spawn@1", prov__activity="x:sc0", prov__starter="x:te0")
    assert "prov:trigger" not in start
    one(result, "wasAssociatedWith", "aprov.assoc_scope@1", prov__activity="x:sc0", prov__agent="x:sub")
    assert types_of(one(result, "activity", "aprov.n_scope@1", id="x:sc0")) == {"apv:SubagentInvocation"}


def test_human_approval_allow(result: ProvDerivation) -> None:
    assoc = one(result, "wasAssociatedWith", "aprov.decision@1", prov__activity="x:dc0", prov__agent="x:human")
    assert assoc["prov:role"]["$"] == "apv:DeciderRole"
    one(result, "used", "aprov.decision@1", prov__activity="x:dc0", prov__entity="x:m1-1")
    start = one(result, "wasStartedBy", "aprov.authorise@1", prov__activity="x:te0", prov__starter="x:dc0")
    assert "prov:trigger" not in start
    one(result, "used", "aprov.use_request@1", prov__activity="x:te0", prov__entity="x:m1-1")
    one(result, "wasInformedBy", "aprov.comm@1", prov__informed="x:dc0", prov__informant="x:mc0")
    one(result, "actedOnBehalfOf", "aprov.assoc_tool@1", prov__delegate="x:env", prov__responsible="x:agent",
        prov__activity="x:te0")
    assert find(result, "wasStartedBy", "aprov.start_tool@1") == []  # authorised: no auto-execution start


def test_approval_with_edit_is_a_disclosed_gap_ne18(result: ProvDerivation) -> None:
    assert find(result, "used", "aprov.use_request@1", prov__activity="x:te1") == []
    gap = [s for s in find(result, "entity", "aprov.n_gap@1") if s["apv:about"]["$"] == "x:te1"]
    assert [(g["apv:property"], g["apv:status"]["$"]) for g in gap] == [("/call", "apv:NotRecorded")]
    assert {"code": "ne18_modified_request", "id": "te1"}.items() <= next(
        d for d in result.report.disclosed if d["code"] == "ne18_modified_request").items()
    one(result, "wasStartedBy", "aprov.authorise@1", prov__activity="x:te1", prov__starter="x:dc1")


def test_denied_call_has_no_execution(result: ProvDerivation) -> None:
    part = one(result, "entity", "aprov.n_part@1", id="x:m1-3")
    assert part["apv:dispatchStatus"]["$"] == "apv:Denied"
    assert find(result, "used", None, prov__entity="x:m1-3") == [
        one(result, "used", "aprov.decision@1", prov__activity="x:dc2", prov__entity="x:m1-3")]
    one(result, "wasGeneratedBy", "aprov.gen_result@1", prov__entity="x:m4-0", prov__activity="x:dc2")


def test_text_parsed_action_has_no_request_usage(result: ProvDerivation) -> None:
    assert find(result, "used", None, prov__activity="x:te2") == []
    one(result, "wasAssociatedWith", "aprov.assoc_tool@1", prov__activity="x:te2", prov__agent="x:env")
    deleg = one(result, "actedOnBehalfOf", "aprov.assoc_tool@1", prov__delegate="x:env", prov__responsible="x:agent",
                prov__activity="x:te2")
    assert "te2/requested_by" in deleg["apv:sourcePointer"]


def test_unknown_event_in_ext_yields_no_statement(result: ProvDerivation) -> None:
    for s in statements(result):
        assert "telemetry" not in str(s.get("apv:sourcePointer", ""))
        assert not any("ext" in str(v) for k, v in s.items() if k == "apv:sourcePointer")


def test_an_inferred_input_link_routes_usage_and_communication_out_of_the_core(tmp_path: Path) -> None:
    records = ps.generic_records()
    ac2 = next(r for r in records if r["id"] == "ac2")
    ac2["evf"] = {"/inputs/0": "I"}
    ac2["rule"] = ["tst.d@1", "tst.i@1#/inputs/0"]
    result = run(tmp_path, records)
    use = one(result, "used", "aprov.g_use@1", prov__activity="x:ac2", prov__entity="x:af1")
    assert use["bundle"] == "inf" and use["apv:method"] == "tst.i@1"
    comm = one(result, "wasInformedBy", "aprov.comm@1", prov__informed="x:ac2", prov__informant="x:ac1")
    assert comm["bundle"] == "inf" and comm["apv:evidenceClass"]["$"] == "apv:Inferred"
    assert any(b.iri.startswith("xd:bundle.inf.tst-i-v1.") for b in result.bundles)


def test_auto_execution_assumption_starts_the_tool_and_delegates(tmp_path: Path) -> None:
    records = ps.generic_records()
    for r in records:
        if r["id"] == "te0":
            del r["authorised_by"]
            r["rule"] = ["tst.d@1", "tst.auto@1"]
    result = run(tmp_path, records)
    start = one(result, "wasStartedBy", "aprov.start_tool@1", prov__activity="x:te0", prov__trigger="x:m1-1",
                prov__starter="x:mc0")
    assert start["apv:evidenceClass"]["$"] == "apv:Derived" and start["apv:assumption"]["$"] == "apv:AutoExecution"
    deleg = one(result, "actedOnBehalfOf", "aprov.assoc_tool@1", prov__activity="x:te0")
    assert "tst.auto@1" in deleg["apv:basisRule"]


def test_an_asserted_assumption_makes_the_start_inferred(tmp_path: Path) -> None:
    records = ps.generic_records()
    for r in records:
        if r["id"] == "te0":
            del r["authorised_by"]
            r["rule"] = ["tst.d@1", "tst.auto_i@1"]
    reg = ps.registry()
    doc = ps.write_aer(records, tmp_path / "g.aer.jsonl")
    result = derive(doc, registry=reg, check_aer=False)
    start = one(result, "wasStartedBy", "aprov.start_tool@1", prov__activity="x:te0")
    assert start["bundle"] == "inf" and start["apv:method"] == "tst.auto_i@1"


@pytest.mark.parametrize(("kind", "type_"), [("activity", "tst:model_call"), ("artefact", "tst:message")])
def test_generic_records_shadowing_a_specialised_kind_are_refused_ne21(tmp_path: Path, kind: str, type_: str) -> None:
    records = ps.generic_records()
    for r in records:
        if r["k"] == kind:
            r["type"] = type_
            break
    doc = ps.write_aer(records, tmp_path / "g.aer.jsonl")
    with pytest.raises(ProvDerivationError) as err:
        derive(doc, registry=ps.registry(), check_aer=False)
    assert err.value.code == "prov.generic_kind_misuse"


def test_an_invalid_aer_is_refused(tmp_path: Path) -> None:
    records = ps.generic_records()
    records[1] = copy.deepcopy(records[1]) | {"kind": "robot"}
    doc = ps.write_aer(records, tmp_path / "g.aer.jsonl")
    with pytest.raises(ProvDerivationError) as err:
        derive(doc, registry=ps.registry())
    assert err.value.code == "prov.aer_invalid"


def test_g_act_never_types_a_specialised_activity_class(result: ProvDerivation) -> None:
    specialised = {"apv:ModelInvocation", "apv:CacheRead", "apv:ToolExecution", "apv:Decision", "apv:CheckerRun"}
    for node in find(result, "activity", "aprov.g_act@1"):
        assert not types_of(node) & specialised


def test_rule_with_unknown_class_cannot_raise(tmp_path: Path) -> None:
    extra = {"tst.weak@1": RuleEntry("tst.weak", 1, "I", "active", "weak")}
    records = ps.generic_records()
    fx = next(r for r in records if r["id"] == "m0")
    fx["evf"] = {"/actor": "I"}
    fx["rule"] = ["tst.weak@1#/actor"]
    result = run(tmp_path, records, registry=ps.registry(extra))
    attr = one(result, "wasAttributedTo", "aprov.attr_message@1", prov__entity="x:m0")
    assert attr["bundle"] == "inf" and attr["apv:method"] == "tst.weak@1"


def test_an_inferred_attribute_on_an_activity_becomes_a_premised_assessment(tmp_path: Path) -> None:
    records = ps.generic_records()
    ac0 = next(r for r in records if r["id"] == "ac0")
    ac0["evf"] = {"/label": "I"}
    ac0["rule"] = ["tst.d@1", "tst.i@1#/label"]
    result = run(tmp_path, records)
    node = one(result, "activity", "aprov.g_act@1", id="x:ac0")
    assert "prov:label" not in node and node["bundle"] == "core"
    assessments = [s for s in find(result, "entity") if s.get("apv:claim", {}).get("$") == "apv:Labelled"]
    assert len(assessments) == 1
    a = assessments[0]
    assert a["bundle"] == "inf" and a["prov:label"] == "plan" and a["apv:method"] == "tst.i@1"
    assert a["apv:subject"]["$"] == "x:ac0" and a["apv:premise"]["$"] == "x:ac0"
