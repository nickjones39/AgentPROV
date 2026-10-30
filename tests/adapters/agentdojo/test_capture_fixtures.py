"""The scripted capture sessions of the backend stream, mapped by the core (docs/architecture K.8.5, K.9.1; D.10.10).

``tests/fixtures/capture/<scenario>/session/`` holds real ``capture/0.1`` sessions of ``agentdojo==0.1.35`` driven by
``ScriptedTransport`` (no network, no model). Each is mapped from its staging layout, validated in release mode against
its own objects, and checked against the scenario's expected record shape, accounting and issues. The generic checks
of every session (SEM, PROV, tier 4, context classes, live versus native) are ``tests/integration/test_live_mapping.py``
and ``tests/differential/test_live_vs_native.py``; this module pins what each scenario must show. The fixtures are read
programmatically; nothing here prints their content.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

import pytest
from capture_support import FIXTURES, MappedSession, map_staged_session

from agentprov.adapters.semantics_profiles import load_semantics_profile
from agentprov.aer.reader import load_aer_bytes
from agentprov.sem.engine import annotate

SCENARIOS = ("benign_banking_single_pass", "injection_important_instructions", "rerun_three_passes", "tool_errors",
             "aborted_pass", "gateway_compat_malformed_discarded", "run_error_context_length", "failing_cell_uncaught_400")


@cache
def _mapped(scenario: str) -> MappedSession:
    staged = FIXTURES / scenario / "session"
    if not (staged / "raw" / "capture").is_dir():
        pytest.skip(f"capture fixture {scenario} is not present")
    m = map_staged_session(Path(staged))
    report = m.validate()
    assert report.ok, [(f.code, f.pointer) for f in report.errors]
    assert "live_native_divergence" not in m.codes
    return m


def _statuses(m: MappedSession, kind: str) -> list[str | None]:
    return [r.get("status") for r in m.of_kind(kind)]


def test_every_scenario_is_present_and_has_a_native_log():
    present = [s for s in SCENARIOS if (FIXTURES / s / "session" / "raw" / "capture").is_dir()]
    if not present:
        pytest.skip("no capture fixtures")
    for scenario in present:
        m = _mapped(scenario)
        assert [a["role"] for a in m.header["artifacts"]] == ["capture_log", "native_log"], scenario


def test_benign_single_pass():
    m = _mapped("benign_banking_single_pass")
    assert m.codes == [] and m.info.accounting.status == "consistent"
    assert _statuses(m, "model_call") == ["kept", "kept"] and _statuses(m, "tool_execution") == ["ok"]
    assert [(j["name"], j["origin"]) for j in m.of_kind("judgement")] == [("utility", "checker"), ("security", "harness_default")]
    assert all("input" in mc and "/input" not in mc.get("evf", {}) for mc in m.of_kind("model_call"))
    # one benchmark actor: the harness's declared `bench` carries the identity's versions (no second `bench0`)
    benches = [a for a in m.of_kind("actor") if a.get("kind") == "benchmark"]
    assert [a["id"] for a in benches] == ["bench"]
    assert benches[0]["version"] == "v1.2.2" and benches[0]["code"]["dist_version"] == "0.1.35"


def test_injection_payload_is_found_through_the_yaml_reading():
    """``agentdojo.art.injection_yaml_folding``: the environment's YAML folds the payload's whitespace, so the
    model-visible text differs from the fixture; the YAML normaliser still finds it (marker ``present``)."""
    m = _mapped("injection_important_instructions")
    fixtures = m.of_kind("fixture")
    attackers = {r["id"] for r in m.of_kind("actor") if r["kind"] == "attacker"}
    assert fixtures and all(f["kind"] == "injection_payload" and f["actor"] in attackers for f in fixtures)
    sem = annotate(load_aer_bytes(m.data), load_semantics_profile("agentdojo.suites", 1))
    markers = [a for a in sem.annotations if a.get("type") == "injection_marker"]
    assert any(a["value"]["status"] == "present" and a["value"]["normaliser"] == "agentdojo.yaml_norm@1" for a in markers)


def test_rerun_three_passes_scores_the_last():
    m = _mapped("rerun_three_passes")
    attempts = [r for r in m.of_kind("scope") if r["kind"] == "attempt"]
    assert [(a["index"], a["scored"]) for a in attempts] == [(0, False), (1, False), (2, True)]
    assert m.checks("aer.acc.passes_closed@1")[0]["observed"] == {"pass_end": 3, "pass_start": 3}
    assert m.codes == [] and m.info.accounting.status == "consistent"


def test_tool_errors_are_sent_as_their_error_text():
    m = _mapped("tool_errors")
    assert _statuses(m, "tool_execution") == ["invalid", "invalid", "error"]
    last = m.of_kind("model_call")[-1]
    transforms = [item["sent"] for item in last["input"] if isinstance(item, dict)]
    assert transforms == [["error_substitution"]] * 3
    assert all(len(item["sent_sha256"]) == 64 for item in last["input"] if isinstance(item, dict))


def test_aborted_pass_abort_message():
    """``agentdojo.art.abort_message_not_logged``: AbortAgentError's message closes the aborted pass in the capture and
    is absent from the native log; it is no reply of the agent, and the call it cut short is unexecuted."""
    m = _mapped("aborted_pass")
    assert m.get("att0")["status"] == "aborted" and "aborted_attempt" in m.codes
    abort = [r for r in m.of_kind("message") if "agentdojo.capture_abort_message@1" in r.get("rule", [])]
    assert len(abort) == 1 and "actor" not in abort[0] and abort[0]["unk"]["/generated_by"] == "not_recorded"
    assert [i["ids"] for i in m.issues("unexecuted_tool_call")] == [["m2#1"]]
    assert m.info.accounting.status == "consistent"


def test_gateway_compat_discarded_reply_and_observed_counts():
    m = _mapped("gateway_compat_malformed_discarded")
    calls = m.of_kind("model_call")
    assert [c["status"] for c in calls] == ["discarded", "kept", "kept"] and calls[1]["retry_of"] == calls[0]["id"]
    assert all(item["sent"] == ["role_rewrite"] for c in calls for item in c["input"][:1])
    items = {i["id"]: i for i in m.header["instrumentation"]}
    assert items["agentdojo.retry_malformed_tool_json@1"]["params"]["observed"] == {"resampled": 1}
    assert items["agentdojo.retry_upstream_failure@1"]["params"]["observed"] == {"retried": 0}
    discarded = next(r for r in m.of_kind("message") if r.get("generated_by") == calls[0]["id"])
    assert [i["ids"] for i in m.issues("unexecuted_tool_call")] == [[f"{discarded['id']}#1"]]
    assert m.info.accounting.status == "consistent"


def test_run_error_imposes_the_outcomes():
    """``agentdojo.art.http_400_not_retried``: a provider 400 is one ``error`` call, never retried; the stock runner
    catches it and imposes both outcomes."""
    m = _mapped("run_error_context_length")
    calls = m.of_kind("model_call")
    assert [(c["status"], c["reason"]) for c in calls] == [("error", "http_400")] and "retry_of" not in calls[0]
    assert m.get("run")["status"] == "ok" and m.get("att0")["status"] == "aborted"
    assert {j["origin"] for j in m.of_kind("judgement")} == {"harness_default"}
    assert "outcome_imposed_by_runner" in m.codes and "capture_error" in m.codes


def test_uncaught_failure_is_sealed_errored():
    """``agentdojo.art.aborted_pass_cause``: the pass cut by the escaping exception is ``aborted``; the run is ``error``
    (session ``errored``) and keeps no outcome."""
    m = _mapped("failing_cell_uncaught_400")
    assert m.get("run")["status"] == "error" and m.get("att0")["status"] == "aborted"
    assert not m.of_kind("judgement") and m.issues("capture_error")
    assert [(c["status"], c["reason"]) for c in m.of_kind("model_call")] == [("error", "http_400")]
