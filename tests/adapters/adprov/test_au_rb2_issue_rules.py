"""AU-RB-2 (audit 2026-11-05; 0.2.0 change batch D-1063, regeneration-batch item 180): the adprov mapper cites a seal
issue's rule through the D.5.4 reading, as the agentdojo and DRIFT mappers do. For a released transcript,
``agentdojo.unexecuted_trailing_calls@1`` cites only the June-2024 code (c274885), which adprov-v1 verifies for the
converted tree only, so the ``unexecuted_tool_call`` issue cites its class-I twin, and the PROV engine states the
part's ``apv:dispatchStatus`` in an inference bundle instead of the core bundle (D-24, D.5.4). A link problem cites the
rule that read the link: ``adprov.call_id_unique_match`` (through its twin) on the unique-id path, the positional rule
otherwise. Synthetic transcripts only."""

from __future__ import annotations

import copy
import json
from typing import Any

from agentprov.aer.reader import load_aer_bytes
from agentprov.prov.engine import derive


def _issues(m: Any) -> list[tuple[str, str]]:
    return [(i["code"], i["rule"]) for i in m.info.issues]


def _dispatch_bundles(m: Any) -> list[str]:
    prov = derive(load_aer_bytes(m.data)).prov_json
    doc = json.loads(prov) if isinstance(prov, str | bytes) else prov
    out = []
    for name, bundle in (doc.get("bundle") or {}).items():
        for entity in (bundle.get("entity") or {}).values():
            if "apv:dispatchStatus" in entity:
                out.append(name.split(":")[-1].split(".")[1])
    return out


def _trailing(doc: dict[str, Any], call_id: Any) -> dict[str, Any]:
    doc["turns"][-1] = {"role": "assistant", "text": "One more.",
                        "tool_calls": [{"id": call_id, "function": "get_balance", "args": {}}]}
    return doc


def test_a_released_unanswered_trailing_call_cites_the_twin_and_is_inferred(v1: Any):
    doc = _trailing(v1.released(), "call_2")
    doc["meta"]["model_config"]["usage"]["n_llm_calls"] = 2
    m = v1.map(v1.dump(doc))
    assert not m.outcome.degenerate and m.validate().ok
    assert ("unexecuted_tool_call", "agentdojo.unexecuted_trailing_calls_unverified@1") in _issues(m)
    assert _dispatch_bundles(m) == ["inf"]


def test_a_converted_unanswered_trailing_call_keeps_the_d_rule_and_the_core_bundle(v1: Any):
    m = v1.map(v1.dump(_trailing(v1.converted(), None)))
    assert not m.outcome.degenerate and m.validate().ok
    assert ("unexecuted_tool_call", "agentdojo.unexecuted_trailing_calls@1") in _issues(m)
    assert _dispatch_bundles(m) == ["core"]


def test_a_released_missing_result_before_the_last_turn_cites_the_twin(v1: Any):
    doc = v1.released()
    doc["turns"][2]["tool_calls"].append({"id": "call_9", "function": "get_balance", "args": {}})
    m = v1.map(v1.dump(doc))
    assert not m.outcome.degenerate
    assert ("missing_tool_result", "agentdojo.unexecuted_trailing_calls_unverified@1") in _issues(m)


def test_a_link_conflict_found_by_a_unique_id_cites_the_id_rule(v1: Any):
    doc = v1.released()
    doc["turns"].insert(4, copy.deepcopy(doc["turns"][3]))  # a second tool turn answers the one unique id
    m = v1.map(v1.dump(doc))
    assert not m.outcome.degenerate
    assert ("call_result_link_conflict", "adprov.call_id_unique_match_unverified@1") in _issues(m)


def test_an_id_mismatch_cites_the_rule_that_read_the_link(v1: Any):
    released = v1.released()
    released["turns"][3]["tool_call_id"] = "call_x"  # unique ids: the id path
    m = v1.map(v1.dump(released))
    assert ("adprov.tool_call_id_mismatch", "adprov.call_id_unique_match_unverified@1") in _issues(m)
    converted = v1.converted()
    converted["turns"][3]["tool_call_id"] = "call_x"  # no unique ids: the positional path
    m = v1.map(v1.dump(converted))
    assert ("adprov.tool_call_id_mismatch", "agentdojo.positional_match@1") in _issues(m)
