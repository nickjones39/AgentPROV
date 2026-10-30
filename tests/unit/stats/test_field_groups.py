"""Field groups of the information-loss table (O.3.5; C.3.16; R-57; K.5.11 items 3-4): the packaged list and its evaluation."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
import stats_support as ss

from agentprov.aer.reader import load_aer
from agentprov.aer.types import UNKNOWN_REASONS
from agentprov.stats.fieldgroups import (
    O35_GROUPS,
    STATUSES,
    FieldGroupError,
    evaluate,
    field_groups,
    field_groups_bytes,
    message_roles,
    parse_field_groups,
    weakness,
)

VECTORS = Path(__file__).resolve().parents[3] / "docs" / "architecture" / "examples" / "C"


def _edit(records, rid, **changes):
    out = copy.deepcopy(records)
    for rec in out:
        if rec.get("id") == rid:
            for key, value in changes.items():
                if value is None:
                    rec.pop(key, None)
                else:
                    rec[key] = value
    return out


def _cells(records):
    return evaluate(records).cells


# ------------------------------------------------------------------------------------------------ the packaged list
def test_the_packaged_groups_are_the_o35_list_in_order():
    groups = field_groups()
    assert tuple(g.id for g in groups) == O35_GROUPS and len(O35_GROUPS) == 18
    assert "outcome_replayed" not in O35_GROUPS  # deferred with replay (AD-10 row 2)
    assert all(g.label and "C.3.16" in g.spec and g.pointers for g in groups)


def test_the_c316_pointers_are_carried():
    by_id = {g.id: g for g in field_groups()}
    expected = {
        "ctx": ("/input",), "tooldefs": ("/tools", "/content"), "model_req": ("/model/requested",),
        "model_served": ("/served_model", "/model/served"), "sampling": ("/params/transmitted",),
        "usage": ("/usage",), "finish": ("/finish_reason",), "reasoning": ("/parts/<k>",),
        "sysprompt": ("/parts", "/content"), "t_model": ("/t",), "t_tool": ("/t",), "passes": ("/index",),
        "env": ("/before_sha256", "/after_sha256"), "callid": ("/parts/<k>/provider_call_id",),
        "link": ("/parts/<k>/responds_to", "/call", "/requested_by"), "payload": ("/content",),
        "outcome_logged": ("/value",), "checker": ("/version", "/code"),
    }  # fmt: skip
    assert {k: by_id[k].pointers for k in expected} == expected
    assert [len(by_id[k].alternatives) for k in ("model_served", "usage", "sysprompt")] == [2, 2, 2]  # the "or" rows


def test_status_order_follows_c316():
    assert STATUSES[:3] == ("O", "D", "I")
    assert max(STATUSES, key=weakness) == "unk:not_recorded"  # the first C.7.1 reason is the weakest
    assert sorted(s.removeprefix("unk:") for s in STATUSES[3:]) == sorted(UNKNOWN_REASONS)


def test_agent_is_grouped_with_assistant_as_data():
    assert message_roles() == {"assistant": ("assistant", "agent")}
    records = ss.agent_records(ss.ex_id(0))
    as_agent = _edit(records, "m1", role="agent")
    assert _cells(as_agent)["reasoning"] == ("O", False)  # D.16.17 item 3: role `agent` kept verbatim, grouped here
    assert "reasoning" not in _cells(_edit(records, "m1", role="planner"))  # a role the table does not group


@pytest.mark.parametrize("mutation, message", [
    (lambda t: t.replace('version = 1', 'version = 2', 1), "version"),
    (lambda t: t.replace('record = "model_call"', 'record = "call"', 1), "record kind"),
    (lambda t: t.replace('pointer = "/input"', 'pointer = "input"', 1), "pointer"),
    (lambda t: t.replace('array = true', 'array = true\nbogus = 1', 1), "unknown key"),
    (lambda t: t.replace('id = "ctx.model_call.input"', 'id = "tooldefs.model_call.tools"', 1), "duplicate"),
])  # fmt: skip
def test_malformed_field_group_files_are_refused(mutation, message):
    text = field_groups_bytes().decode("utf-8")
    assert parse_field_groups(text.encode())  # the packaged file parses
    with pytest.raises(FieldGroupError):
        parse_field_groups(mutation(text).encode())


# ------------------------------------------------------------------------------------------------ evaluation
def test_the_standard_execution_has_the_expected_cells():
    status = evaluate(ss.agent_records(ss.ex_id(0)))
    assert status.cells == ss.EXPECTED_CELLS
    assert "env" not in status.cells  # no state change: no cell (C.3.16)
    assert status.occurrences["checker.actor.version"] == {("O", False): 1}
    assert status.occurrences["checker.actor.code"] == {("unk:not_recorded", False): 1}


def test_effective_tag_is_longest_prefix_and_party_collapses():
    records = ss.agent_records(ss.ex_id(0))
    assert _cells(_edit(records, "mc0", evf={"/input": "I", "/input/0": "O:capture"}))["ctx"] == ("O", False)
    assert _cells(_edit(records, "mc0", evf={"/input/0": "D"}))["ctx"] == ("D", False)
    assert _cells(_edit(records, "mc0", evf=None))["finish"] == ("D", False)  # back to the record's existence class


def test_unknowns_at_enclosing_and_lower_pointers_count():
    records = ss.agent_records(ss.ex_id(0))
    enclosing = _edit(records, "mc0", unk={"/params": "withheld", "/t": "not_recorded"})
    assert _cells(enclosing)["sampling"] == ("unk:withheld", False)
    below = _edit(records, "bench", unk={"/version/x": "ambiguous", "/code": "not_recorded"})
    assert evaluate(below).occurrences["checker.actor.version"] == {("unk:ambiguous", False): 1}
    many = _edit(records, "mc0", unk={"/t": "lost", "/t/start": "not_captured"})
    assert _cells(many)["t_model"] == ("unk:lost", False)  # the first reason in C.7.1's order


def test_array_items_are_occurrences():
    records = ss.agent_records(ss.ex_id(0))
    two = _edit(records, "mc0", input=["m0", "m1"], evf={"/input/1": "I", "/finish_reason": "O:provider"})
    assert evaluate(two).occurrences["ctx.model_call.input"] == {("D", False): 1, ("I", False): 1}
    assert _cells(two)["ctx"] == ("I", False)  # the weakest item
    empty = _edit(records, "mc0", input=[])
    assert evaluate(empty).occurrences["ctx.model_call.input"] == {("I", False): 1}  # a known-empty array: one occurrence
    item_unknown = _edit(records, "mc0", input=["m0", "m1"], unk={"/input/1/sent": "not_captured", "/t": "not_recorded"})
    assert evaluate(item_unknown).occurrences["ctx.model_call.input"] == {("I", False): 1, ("unk:not_captured", False): 1}


def test_an_absent_pointer_without_unk_is_undeclared():
    records = ss.agent_records(ss.ex_id(0))
    assert _cells(records)["tooldefs"] == ("unk:not_recorded", True)
    declared = _edit(records, "mc0", unk={"/tools": "not_recorded", "/t": "not_recorded"})
    assert _cells(declared)["tooldefs"] == ("unk:not_recorded", False)


def test_named_by_follows_the_reference():
    records = ss.agent_records(ss.ex_id(0))
    with_tools = _edit(records, "mc0", tools="fxt")
    with_tools.insert(1, {"k": "fixture", "id": "fxt", "ev": "D", "kind": "tool_definitions", "content": []})
    assert _cells(with_tools)["tooldefs"] == ("D", False)  # /tools at D (record class), the fixture's /content at D
    unnamed = copy.deepcopy(records)
    unnamed.insert(1, {"k": "fixture", "id": "fxt", "ev": "O", "kind": "tool_definitions", "content": []})
    assert evaluate(unnamed).occurrences["tooldefs.fixture.content"] == {}  # not named by an agent call: not selected


def test_alternatives_take_the_strongest():
    records = ss.agent_records(ss.ex_id(0))
    served = _edit(records, "mc0", served_model="m", evf={"/input": "I", "/served_model": "O:provider"})
    assert _cells(served)["model_served"] == ("O", False)
    usage = _edit(records, "run", usage={"input": 1}, evf={"/usage": "O:provider"})
    assert _cells(usage)["usage"] == ("O", False)


def test_fallback_to_requested_by():
    records = ss.agent_records(ss.ex_id(0))
    no_call = _edit(records, "te0", call=None, requested_by="agent", evf={"/t": "O:source", "/requested_by": "I"})
    assert evaluate(no_call).occurrences["link.tool_execution.call"] == {("I", False): 1}
    neither = _edit(records, "te0", call=None)
    assert evaluate(neither).occurrences["link.tool_execution.call"] == {("unk:not_recorded", True): 1}
    ambiguous = _edit(records, "te0", call=None, unk={"/call": "ambiguous"})
    assert evaluate(ambiguous).occurrences["link.tool_execution.call"] == {("unk:ambiguous", False): 1}


def test_revised_judgements_are_not_logged_outcomes():
    records = ss.agent_records(ss.ex_id(0))
    records.append({"k": "judgement", "id": "j1", "ev": "I", "actor": "bench", "subject": "run", "name": "utility",
                    "value": False, "origin": "recomputed", "revises": "j0"})  # fmt: skip
    assert evaluate(records).occurrences["outcome_logged.judgement.value"] == {("O", False): 1}


def test_c16_vectors():
    """Spec vectors (C.16): the cells follow from their evf/unk declarations."""
    v1 = evaluate(load_aer(VECTORS / "adprov_v1_llama_injecagent.aer.jsonl").records).cells
    assert v1["ctx"] == ("I", False)  # evf {"/input": "I"}
    assert v1["usage"] == ("O", False)  # run scope evf {"/usage": "O:provider"} beats the calls' declared unknown
    # passes: the attempt scope is class I since the D-24 twins (regeneration-batch item 3 updated the C.16 vector)
    assert v1["passes"] == ("I", False) and v1["sysprompt"] == ("O", False) and v1["t_tool"] == ("O", False)
    assert v1["t_model"] == ("unk:not_recorded", False) and v1["checker"] == ("unk:not_recorded", False)
    pi = evaluate(load_aer(VECTORS / "agentdojo_2024_pi_detector.aer.jsonl").records).cells
    assert pi["passes"] == ("unk:lost", False)  # last-pass-only logging (C.3.3)
    assert pi["model_req"] == ("I", False)  # evf {"/model": "I"} on the agent actor (C.6.6)
