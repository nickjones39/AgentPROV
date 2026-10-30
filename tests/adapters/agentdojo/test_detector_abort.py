"""The ``log_end`` hook point and the quirk ``agentdojo.detector_abort`` (routing R10; D-116; docs/architecture D.6.6).

On llm-lock's synthetic logs: a log that ends at one executed tool output, in an arm whose defence is a declared aborting
detector, gains a ``terminate`` decision by that detector about that output's ``tool_execution``; with several outputs
in the last turn the subject is the request message and the info issue says the flagged output is not recorded; a log
that ends with the agent's answer, or in an arm without the quirk, gets nothing. The SEM and PROV of an aborted log
validate. Byte-neutrality for every other profile is the pinned AER and PROV digests (phase10d, golden, gate D).
"""

from __future__ import annotations

from typing import Any

import pytest
from phase10d_support import BY_NAME, map_doc, ok
from source_support import call, final, log_with, result, turn

from agentprov.adapters.agentdojo.hooks.detector_abort import ISSUE, QUIRK_ID, RULE, defences
from agentprov.adapters.agentdojo.quirks import hooks
from agentprov.aer.rules import load_catalogue
from agentprov.errors import ProfileError

SRC = BY_NAME["llm-lock"]


def _map(arm: str, messages: list[dict[str, Any]], error: str | None = None):  # type: ignore[no-untyped-def]
    doc = log_with(messages, pipeline_name="local", benchmark_version="v1.2.2")
    doc["error"] = error
    path = (f"data/agentdojo/{arm}/logs/local/{doc['suite_name']}/{doc['user_task_id']}/"
            f"{doc.get('attack_type') or 'none'}/{doc.get('injection_task_id') or 'none'}.json")
    m = map_doc(SRC, doc, path)
    ok(m)
    return m


def _terminates(m) -> list[dict[str, Any]]:  # type: ignore[no-untyped-def]
    return [r for r in m.of_kind("decision") if r.get("verdict") == "terminate"]


C1 = call("get_balance", {}, "call_1")
C2 = call("get_iban", {}, "call_2")


def test_the_hook_and_rule_are_registered_class_i():
    hook = hooks()[QUIRK_ID]
    assert hook.rules == (RULE,) and hook.log_end is not None and set(hook.census) == {"aborts", "aborts_output_unrecorded"}
    entry = load_catalogue("agentdojo").get(RULE)
    assert entry is not None and entry.citable and entry.cls == "I"


def test_an_aborted_log_ends_with_a_terminate_decision():
    m = _map("llm", [turn(C1), result(C1, "1000")])
    (dc,) = _terminates(m)
    (te,) = m.of_kind("tool_execution")
    actor = m.get(dc["actor"])
    assert actor["kind"] == "defense" and actor["name"] == "llm"
    assert dc["subject"] == te["id"] and dc["ev"] == "I" and dc["unk"]["/reason"] == "not_recorded"
    assert any(str(r).split("#")[0] == RULE for r in dc["rule"])
    assert m.records.index(dc) > max(m.records.index(r) for r in m.of_kind("message"))  # after the messages
    assert not m.issues(ISSUE)


def test_several_trailing_outputs_name_the_request_and_raise_the_issue():
    m = _map("multiclass", [turn(C1, C2), result(C1, "1000"), result(C2, "XX")])
    (dc,) = _terminates(m)
    request = m.get(dc["subject"])
    assert request["k"] == "message" and request["role"] == "assistant"
    assert [p["name"] for p in request["parts"] if p.get("t") == "tool_call"] == ["get_balance", "get_iban"]
    (issue,) = m.issues(ISSUE)
    assert issue["ids"] == [request["id"]] and issue["rule"] == RULE


@pytest.mark.parametrize(("arm", "messages"), [
    ("llm", [turn(C1), result(C1, "1000"), final()]),  # the agent answered: not an abort
    ("none", [turn(C1), result(C1, "1000")]),  # undefended arm: the quirk does not apply
    ("transformer/protectai-deberta-v3-base-prompt-injection-v2", [turn(C1), result(C1, "1000")]),  # a redacting arm
])
def test_no_decision_where_the_detector_did_not_abort(arm: str, messages: list[dict[str, Any]]):
    assert _terminates(_map(arm, messages)) == []


def test_a_recorded_run_error_is_not_credited_to_the_detector():
    """Regen item 43 (CD-15): ``AbortAgentError`` leaves ``error`` null; a log that ends at a tool output with a recorded
    run error ended for that error (``outcome_imposed_by_runner``), so the detector gets no terminate decision."""
    m = _map("llm", [turn(C1), result(C1, "1000")],
             error="Skipping task user_task_0 due to context_length_exceeded: Error code: 400")
    assert _terminates(m) == []
    assert m.issues("outcome_imposed_by_runner")


def test_an_aborted_log_derives_and_validates():
    from agentprov.adapters.semantics_profiles import load_semantics_profile
    from agentprov.aer.reader import load_aer_bytes
    from agentprov.prov.engine import derive
    from agentprov.sem.engine import annotate
    from agentprov.validate import validate_prov

    doc = load_aer_bytes(_map("embedding", [turn(C1), result(C1, "1000")]).data)
    prof = load_semantics_profile("agentdojo.suites", 2)
    sem = annotate(doc, prof)
    res = derive(doc, [sem], sem_profiles={(prof.id, prof.version): prof})
    report = validate_prov(res.prov_json, doc, sems=[sem])
    assert report.ok, sorted(report.codes())
    assert b"apv:VerdictTerminate" in (res.prov_json if isinstance(res.prov_json, bytes) else res.prov_json.encode())


@pytest.mark.parametrize("params", [{}, {"defences": []}, {"defences": "llm"}, {"defences": [""]}])
def test_malformed_params_are_refused(params: dict[str, Any]):
    with pytest.raises(ProfileError):
        defences(params)
