"""The AutoDojo capture fixtures mapped by the core under ``autodojo-live`` (docs/architecture D.11.7, D.11.9; phase 9).

``tests/fixtures/capture/autodojo/<scenario>/session/`` holds real ``capture/0.1`` sessions of the AutoDojo fork
(``xhOwenMa/AutoDojo@aa458794``) driven by ``ScriptedTransport``. Each is mapped with the profile its
``session.start.backend.id`` selects, validated in release mode against its own objects, and checked for what the
scenario must show: the fork's instrumentation accepted, the cache as a ``supporting`` artefact, the fork's imposed
run-error outcome, the parent-appended abort. The generic checks (SEM, PROV, tier 4, live versus native) run over these
sessions in ``tests/integration/test_live_mapping.py`` and ``tests/differential/test_live_vs_native.py``. The fixtures
are read programmatically; nothing here prints their content.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

import pytest
from capture_support import FIXTURES, MappedSession, map_staged_session

from agentprov.adapters.runner.live import capture_profile_id
from agentprov.errors import AgentProvError

ROOT = FIXTURES / "autodojo"
SCENARIOS = ("autodojo_banking_important_instructions", "autodojo_banking_cache_replay",
             "autodojo_error_skipped_json_decode", "autodojo_aborted_kill")
FORK = {"repo": "https://github.com/xhOwenMa/AutoDojo", "commit": "aa458794b7eb7f082e94daeac4c0f55bfc0c90cc"}


def _staged(scenario: str) -> Path:
    staged = ROOT / scenario / "session"
    if not (staged / "raw" / "capture").is_dir():
        pytest.skip(f"AutoDojo capture fixture {scenario} is not present")
    return staged


@cache
def _mapped(scenario: str, profile_id: str | None = None) -> MappedSession:
    m = map_staged_session(_staged(scenario), profile_id=profile_id)
    report = m.validate()
    assert report.ok, [(f.code, f.pointer) for f in report.errors]
    return m


def _log(scenario: str) -> bytes:
    (log,) = (_staged(scenario) / "raw" / "capture").glob("*.capture.jsonl")
    return log.read_bytes()


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_profile_comes_from_the_backend_id_and_every_session_maps(scenario: str) -> None:
    assert capture_profile_id(_log(scenario)) == "autodojo-live"
    m = _mapped(scenario)
    assert m.header["profile"]["id"] == "autodojo-live" and m.header["mode"] == "live"
    assert not ({"live_native_divergence", "identity_conflict", "identity_unresolved",
                 "agentdojo.instrumentation_unrecognised"} & set(m.codes)), m.codes
    bench = next(a for a in m.of_kind("actor") if a["kind"] == "benchmark")
    assert {k: bench["code"].get(k) for k in FORK} == FORK and bench["name"] == "agentdojo"
    # re-mapping is byte-identical (RPR-10)
    assert map_staged_session(_staged(scenario)).data == m.data


def test_the_phase_8_backend_selects_its_own_profile() -> None:
    logs = sorted(FIXTURES.glob("*/session/raw/capture/*.capture.jsonl"))
    if not logs:
        pytest.skip("no phase-8 capture fixtures")
    assert {capture_profile_id(p.read_bytes()) for p in logs} == {"agentdojo-live"}
    with pytest.raises(AgentProvError) as info:
        capture_profile_id(_log(SCENARIOS[0]).replace(b'"id":"autodojo"', b'"id":"unknown"', 1))
    assert info.value.code == "adapter.backend_unknown"


def test_fork_instrumentation_is_declared_and_accepted() -> None:
    m = _mapped("autodojo_banking_important_instructions")
    items = {i["id"]: i for i in m.header["instrumentation"]}
    for item in ("autodojo.fork_temperature_transmitted@1", "autodojo.fork_malformed_json_retry@1",
                 "autodojo.fork_system_role@1", "autodojo.env_nltk_preprovisioned@1", "agentdojo.transport_scripted@1"):
        assert item in items, item
    assert "agentdojo.temperature_not_transmitted@1" not in items
    assert items["autodojo.fork_temperature_transmitted@1"]["params"]["transmitted"] == 0
    assert m.info.accounting.status == "consistent"
    assert [(j["name"], j["origin"]) for j in m.of_kind("judgement")] == [("utility", "checker"), ("security", "checker")]
    # the fork sends the system message as `system`: the stock rendering, no declared transform
    first = m.of_kind("model_call")[0]
    assert all(isinstance(i, str) for i in first["input"])


def test_cache_replay_lists_the_cache_as_a_supporting_artefact() -> None:
    m = _mapped("autodojo_banking_cache_replay")
    cell_params = _cell(_log("autodojo_banking_cache_replay"))["attack_params"]
    (cache_art,) = [a for a in m.header["artifacts"] if a["role"] == "supporting"]
    assert cache_art["id"] == "a2" and cache_art["sha256"] == cell_params["autodojo_cache_sha256"]
    assert cache_art["prov_primary"] == "unknown" and cache_art["media"] == "application/json"
    assert cache_art["sha256"] in m.objects  # the staged copy the worker read
    item = next(i for i in m.header["instrumentation"] if i["id"] == "autodojo.attack_cache_replay@1")
    assert item["kind"] == "attack_parameter" and item["params"]["cache_sha256"] == cache_art["sha256"]
    assert item["params"]["variant"] == cell_params["autodojo_variant"] == 0
    assert m.header["task"]["attack_id"] == "autodojo" and m.info.accounting.status == "consistent"
    assert m.of_kind("fixture")


def _cell(log: bytes) -> dict:
    import json

    return json.loads(log.split(b"\n", 1)[0])["data"]["cell"]


def test_run_error_imposes_the_forks_outcome() -> None:
    """D.11.7 item 7: the fork skips the task on a JSONDecodeError and imposes utility = security = false. The values are
    observed (the stock runner returned them); the origin harness_default is derived from the run error under the
    profile's quirk (D, ``agentdojo.run_error_imposed_outcome@1``), and ``error_type`` is kept as the native log keeps it."""
    m = _mapped("autodojo_error_skipped_json_decode")
    judgements = m.of_kind("judgement")
    assert [(j["name"], j["value"], j["origin"]) for j in judgements] == [("utility", False, "harness_default"),
                                                                         ("security", False, "harness_default")]
    for j in judgements:
        assert j["evf"] == {"/origin": "D"} and j["rule"] == ["agentdojo.run_error_imposed_outcome@1#/origin"]
        assert len(j["src"]) == 3  # the outcome, the pipeline error event and the run_error_imposed note
    assert m.header["ext"]["agentdojo"]["extra"] == {"error_type": "json_decode_error"}
    assert m.header["evf"]["/ext/agentdojo/extra/error_type"] == "O:capture"
    assert {"a": "a1", "p": "/error_type"} in m.header["src"]
    assert [i["ids"] for i in m.issues("outcome_imposed_by_runner")] == [["j0", "j1"]]
    calls = m.of_kind("model_call")
    assert [(c["status"], c["reason"]) for c in calls] == [("discarded", "superseded_by_retry")] * 2 + [
        ("discarded", "element_raised:JSONDecodeError")]
    assert m.get("run")["status"] == "ok" and m.get("att0")["status"] == "aborted"
    assert m.info.accounting.status == "consistent"


def test_profile_pins_must_match_the_observed_identity() -> None:
    """``agentdojo.capture_backend_identity@1``: mapped with the AgentDojo profile (forced), the fork's session is
    reported, not silently accepted, and the AgentDojo quirk's values do not license the imposed origin."""
    m = _mapped("autodojo_error_skipped_json_decode", "agentdojo-live")
    details = sorted(str(i.get("detail")) for i in m.issues("identity_conflict"))
    # the fork reports the wheel's distribution name and version (D.11.1), so only the backend id and the git source
    # tell it apart; the version string is never taken as identity
    assert len(details) == 2 and details[0].startswith("seq 2: identity benchmark names a git source")
    assert details[1].startswith("session backend 'autodojo'")
    security = next(j for j in m.of_kind("judgement") if j["name"] == "security")
    assert security["evf"] == {"/origin": "O:capture"} and "rule" not in security
    assert any("differs from the profile's run_error_imposes_outcome" in str(i.get("detail")) for i in m.issues("capture_error"))
    utility = next(j for j in m.of_kind("judgement") if j["name"] == "utility")
    assert utility["evf"] == {"/origin": "D"}  # utility = false is imposed by both runners


def test_parent_killed_session_is_sealed_aborted() -> None:
    m = _mapped("autodojo_aborted_kill")
    assert m.get("run")["status"] == "aborted" and "aborted_attempt" in m.codes
    assert [a["role"] for a in m.header["artifacts"]] == ["capture_log"]  # the fork's partial native file is not announced
    assert m.checks("aer.acc.capture_chain@1")[0]["verdict"] == "consistent"
    assert m.checks("aer.acc.passes_closed@1")[0]["reason"] == "pass_without_end"
    assert m.get("att0")["unk"]["/status"] == "not_captured" and not m.of_kind("judgement")
    last = _log("autodojo_aborted_kill").rstrip(b"\n").rsplit(b"\n", 1)[-1]
    assert b'"appended_by":"parent"' in last and b'"status":"aborted"' in last
