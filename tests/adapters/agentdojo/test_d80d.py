"""D-80 (d) addendum (regeneration-batch item 103; user decision 2026-10-15, from the corpus pre-check): under a harness
whose code is not verified, ``unexecuted_tool_call`` and ``missing_tool_result`` cite the resolved rule, the class-I
twin ``agentdojo.unexecuted_trailing_calls_unverified@1``, as the retry and run-error readings do. A missing result
then proves no loss (H.3.2(2)). Under verified code the D rule stays.
Synthetic logs."""

from __future__ import annotations

from typing import Any

from agentdojo_support import map_log, new_log
from source_support import call, final, log_with, map_synthetic, ok, result, turn

from agentprov.aer.reader import load_aer_bytes
from agentprov.corpus.facets import header_rule_class, proven_loss_codes

PROFILE = "survey-runs"  # verified_code = []
TWIN = "agentdojo.unexecuted_trailing_calls_unverified@1"
RULE = "agentdojo.unexecuted_trailing_calls@1"


def survey_log(messages: list[dict[str, Any]]) -> tuple[dict[str, Any], str]:
    """A survey-runs log at its pinned layout (as test_survey's helper; a bare ``test_survey`` import is ambiguous)."""
    doc = log_with(messages, pipeline_name="openai-compatible", benchmark_version="v1.2.2")
    attack = doc.get("attack_type") or "none"
    path = (f"agentdojo/results/runs_qwen3_14b/openai-compatible/{doc['suite_name']}/{doc['user_task_id']}/{attack}/"
            f"{doc.get('injection_task_id') or 'none'}.json")
    return doc, path


def _calls() -> list[dict[str, Any]]:
    """A batch whose first call is never answered (missing_tool_result), then a final turn whose call is never run
    (unexecuted_tool_call)."""
    a, b, c = (call("get_x", {"n": n}, f"call_{n}") for n in (1, 2, 3))
    return [turn(a, b), result(b, "done"), turn(c)]


def test_an_unverified_harness_cites_the_twin_on_both_issues():
    doc, path = survey_log(_calls())
    m = map_synthetic(PROFILE, doc, path)
    ok(m)
    assert {i["rule"] for i in m.issues("missing_tool_result")} == {TWIN}
    assert {i["rule"] for i in m.issues("unexecuted_tool_call")} == {TWIN}
    aer = load_aer_bytes(m.data)
    # the result's loss is inferred, not proven (H.3.2(2)); completeness here also follows the accounting checks
    assert "missing_tool_result" not in proven_loss_codes(aer.seal["issues"], header_rule_class(aer.records[0]))


def test_verified_code_keeps_the_d_rule():
    """agentdojo-upstream verifies the June-2024 code (c274885): the issue's rule stays D, as before."""
    doc = new_log()
    doc["messages"][2]["tool_calls"].append({"function": "send_money", "args": {"recipient": "Y", "amount": 5.0},
                                              "id": "call_2"})
    doc["messages"].pop()  # the batch's second call is the last agent turn's: unexecuted_tool_call
    m = map_log(doc)
    assert {i["rule"] for i in m.issues("unexecuted_tool_call")} == {RULE}


def test_a_final_text_turn_is_untouched():
    doc, path = survey_log([final("Done.")])
    m = map_synthetic(PROFILE, doc, path)
    assert not m.issues("unexecuted_tool_call") and not m.issues("missing_tool_result")
