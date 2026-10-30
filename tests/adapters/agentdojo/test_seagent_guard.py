"""SEAgent guard blocks (quirk ``agentdojo.seagent_guard_block``, hook ``hooks/seagent.py``; pre-check
PC-seagent-agentdojo-02, D-591; regeneration-batch item 135). One real fixture holds a block; failures print ids and
tokens only."""

from __future__ import annotations

import copy
import json

from test_phase10f_seagent import _entries, _map, _raw

from agentprov.adapters.agentdojo import census
from agentprov.adapters.agentdojo.quirks import CensusFile
from agentprov.adapters.types import Origin

RULE = "agentdojo.seagent_guard_block@1"
SUFFIX = "BLOCKED_BY_SEAGENT"


def _blocked_entry() -> dict:
    return next(e for e in _entries() if SUFFIX.encode() in _raw(e))


def test_a_renamed_call_is_a_deny_decision_by_the_guard():
    entry = _blocked_entry()
    out = _map(_raw(entry), entry["label"], Origin.local(entry["label"]))
    records = {r["id"]: r for r in out.records}
    (dc,) = [r for r in out.records if r.get("k") == "decision" and RULE in r.get("rule", ())]
    assert dc["verdict"] == "deny" and dc["ev"] == "I" and dc["unk"]["/reason"] == "not_recorded"
    assert records[dc["actor"]]["name"] in ("seagent-initial", "seagent-refined")
    call_msg, _, k = dc["subject"].partition("#")
    part = records[call_msg]["parts"][int(k)]
    assert part["t"] == "tool_call" and part["name"].endswith(SUFFIX)  # the logged name is kept verbatim
    (answer,) = [r for r in out.records if r.get("generated_by") == dc["id"]]
    assert answer["role"] == "tool" and answer["actor"] == dc["actor"]
    executed = [r for r in out.records if r.get("k") == "tool_execution"]
    assert not any(str(r.get("name", "")).endswith(SUFFIX) for r in executed)  # no tool ran


def test_the_suffix_outside_a_seagent_arm_is_left_alone():
    """The same renamed call in a file of another arm (here the pvagent run directory) is not read as a guard block."""
    entry = _blocked_entry()
    other = next(e for e in _entries() if "/pvagent/" in e["label"])
    run_dir = entry["label"].split("/deepseek")[0]
    label = entry["label"].replace(run_dir, other["label"].split("/deepseek")[0])
    out = _map(_raw(entry), label, Origin.local(label))
    assert not [r for r in out.records if r.get("k") == "decision" and RULE in r.get("rule", ())]


def test_a_tool_name_equal_to_the_suffix_is_not_a_block():
    entry = _blocked_entry()
    doc = json.loads(_raw(entry))
    doc = copy.deepcopy(doc)
    for message in doc["messages"]:
        for call in message.get("tool_calls") or ():
            if call["function"].endswith(SUFFIX):
                call["function"] = SUFFIX
        if isinstance(message.get("tool_call"), dict) and message["tool_call"]["function"].endswith(SUFFIX):
            message["tool_call"]["function"] = SUFFIX
    out = _map(json.dumps(doc, indent=4).encode(), entry["label"], Origin.local(entry["label"]))
    assert not [r for r in out.records if r.get("k") == "decision" and RULE in r.get("rule", ())]


def _with_dropped_calls(position: int) -> bytes:
    """The real blocked batch with one more call, which the guard dropped (no tool message), at ``position`` in it."""
    entry = _blocked_entry()
    doc = json.loads(_raw(entry))
    message = next(m for m in doc["messages"] if any(c["function"].endswith(SUFFIX) for c in m.get("tool_calls") or ()))
    dropped = {"function": "get_balance", "args": {}, "id": "call_dropped_synthetic"}
    message["tool_calls"].insert(position, dropped)
    return json.dumps(doc, indent=4).encode()


def test_the_dropped_calls_of_a_blocked_batch_are_unexecuted_not_lost():
    """D-592: before and after the blocked call alike, a dropped call is unexecuted_tool_call (warning) under the guard
    rule; no missing_tool_result, so no failed execution."""
    entry = _blocked_entry()
    for position in (0, 1):
        out = _map(_with_dropped_calls(position), entry["label"], Origin.local(entry["label"]))
        codes = [(i["code"], i.get("severity", "warning"), i["rule"]) for i in out.issues]
        assert ("unexecuted_tool_call", "warning", RULE) in codes, (position, codes)
        assert not [c for c in codes if c[0] == "missing_tool_result"], (position, codes)
        (dropped,) = [i for i in out.issues if i["code"] == "unexecuted_tool_call" and i["rule"] == RULE]
        records = {r["id"]: r for r in out.records}
        msg_id, _, k = dropped["ids"][0].partition("#")
        assert records[msg_id]["parts"][int(k)]["name"] == "get_balance"
        counts = census.census_file(CensusFile(out.records, out.issues))
        # the dropped call is the guard's, not a trailing call of the generic quirk
        assert counts["agentdojo.seagent_guard_block"]["dropped_calls"] == 1, (position, counts)
        assert counts["agentdojo.unexecuted_trailing_calls"]["calls"] == 0, (position, counts)


def test_dropped_calls_outside_a_seagent_arm_keep_the_generic_rows():
    entry = _blocked_entry()
    other = next(e for e in _entries() if "/pvagent/" in e["label"])
    label = entry["label"].replace(entry["label"].split("/deepseek")[0], other["label"].split("/deepseek")[0])
    out = _map(_with_dropped_calls(1), label, Origin.local(label))
    assert not [i for i in out.issues if i["rule"] == RULE]
    assert [i for i in out.issues if i["code"] in ("missing_tool_result", "unexecuted_tool_call")]
