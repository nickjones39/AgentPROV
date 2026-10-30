"""Defended live sessions mapped by ``agentdojo.capture`` (D-670, D-673, D-677; docs/architecture D.10.11).

``tests/fixtures/capture/defence/<scenario>/session/`` holds real ``capture/0.1`` sessions of ``agentdojo==0.1.35``
driven by ``backends/agentdojo/tools/make_capture_fixtures.py`` through the defended pipelines of
``agentprov_backend.defences`` (scripted transport; the PI detector and the gate run as declared stand-ins). Each one
must map consistent and valid, agree with its native log, and show the defence as the defence's own actions: its actor,
its decisions (redact with the original kept, deny with no execution), its auxiliary calls and the messages it inserts.
Nothing is invented: no time for a decision the harness did not observe when it happened.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.adapters.agentdojo.capture_support import MappedSession, map_staged_session

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "capture" / "defence"
SCENARIOS = ("defence_repeat_user_prompt", "defence_spotlighting", "defence_tool_filter", "defence_pi_detector_redact",
             "defence_melon_block", "defence_melon_pass",
             "defence_gate_denial")
_CACHE: dict[str, MappedSession] = {}


def _mapped(scenario: str) -> MappedSession:
    if scenario not in _CACHE:
        directory = FIXTURES / scenario / "session"
        if not (directory / "raw" / "capture").is_dir():
            pytest.skip(f"no defended capture fixture {scenario}")
        _CACHE[scenario] = map_staged_session(directory)
    return _CACHE[scenario]


def _msg(m: MappedSession, mid: str) -> dict:
    return m.get(mid)


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_every_defended_session_maps_consistent_valid_and_agrees_with_its_native_log(scenario):
    m = _mapped(scenario)
    # no live_native_divergence, no unattributed message, no accounting issue; MELON's replaced reply proposed a transfer
    # that never ran, which the seal reports as it should
    expected = ["unexecuted_tool_call"] if scenario == "defence_melon_block" else []
    assert m.codes == expected, m.codes
    assert m.info.accounting.status == "consistent"
    report = m.validate()
    assert report.ok and report.mode == "release", report.findings
    header = m.header
    assert header["profile"]["id"] == "agentdojo-live" and header["profile"]["version"] == 3
    assert header["rules"]["defence"] == 1
    defence = header["ext"]["agentdojo"]["defence"]
    assert defence["entry"]["id"] == header["task"]["defense_id"]
    actors = {a["id"]: a for a in m.of_kind("actor")}
    assert actors["def0"]["kind"] == "defense" and actors["def0"]["name"] == header["task"]["defense_id"]


def test_repeat_user_prompt_s_turn_is_the_defence_s():
    m = _mapped("defence_repeat_user_prompt")
    users = [r for r in m.of_kind("message") if r["role"] == "user"]
    assert [u["actor"] for u in users] == ["user", "def0"]
    assert "defence.message_by_defence@1#/actor" in users[1]["rule"]


def test_tool_filter_messages_are_the_defence_s():
    m = _mapped("defence_tool_filter")
    calls = {r["id"]: r for r in m.of_kind("model_call")}
    by_actor = sorted((c["actor"], c["id"]) for c in calls.values())
    assert [a for a, _ in by_actor] == ["agent", "agent", "def0"]
    aux = next(c for c in calls.values() if c["actor"] == "def0")
    messages = m.of_kind("message")
    prompt, reply = messages[2], messages[3]
    assert (prompt["role"], prompt["actor"]) == ("user", "def0")
    assert (reply["role"], reply["actor"], reply["generated_by"]) == ("assistant", "def0", aux["id"])
    assert "defence.message_by_defence@1#/generated_by" in reply["rule"]
    agent_replies = [r for r in messages if r["role"] == "assistant" and r["actor"] == "agent"]
    assert len(agent_replies) == 2  # the accounting pairs only these with the agent's calls


def test_a_redaction_keeps_the_original_and_generates_the_tool_message():
    m = _mapped("defence_pi_detector_redact")
    (decision,) = m.of_kind("decision")
    (execution,) = m.of_kind("tool_execution")
    assert (decision["actor"], decision["verdict"], decision["subject"]) == ("def0", "redact", execution["id"])
    assert decision["reason"] == "is_injection=True score=0.99"
    assert "$blob" in json.dumps(decision["original"])  # the overwritten content is kept, not `unk overwritten`
    tool_messages = [r for r in m.of_kind("message") if r["role"] == "tool"]
    assert [t["generated_by"] for t in tool_messages] == [decision["id"]]


def test_a_gate_denial_is_a_decision_with_no_execution():
    m = _mapped("defence_gate_denial")
    (decision,) = m.of_kind("decision")
    executions = m.of_kind("tool_execution")
    assert [e["name"] for e in executions] == ["get_most_recent_transactions"]
    assert (decision["actor"], decision["verdict"]) == ("def0", "deny")
    assert decision["reason"] == "GATE_DECLINE: send_money"
    assert "defence.denial_declared_text@1#/actor" in decision["rule"]
    assert decision.get("evf", {}).get("/actor") == "D"
    assert "t" not in decision and decision["unk"]["/t"] == "not_captured"  # recorded after the gate returned
    denied_message = next(r for r in m.of_kind("message") if r.get("generated_by") == decision["id"])
    assert denied_message["role"] == "tool" and denied_message["actor"] == "def0"


def test_profiles_v1_and_v2_are_archived_and_allow_no_defence():
    from agentprov.adapters.profiles import load_profile

    for version in (1, 2):
        assert "defences" not in load_profile("agentdojo-live", version).data["family"]["agentdojo"]["live"]
    v3 = load_profile("agentdojo-live")
    assert v3.version == 3 and "mandate_intent" in v3.data["family"]["agentdojo"]["live"]["defences"]


#: D-31 (owner's criterion): the archived bytes are the ones scratch corpora recorded. v1: agentdojo-live@1 in
#: ~/.agentprov/migration-work/agentdojo-env, autodojo-live@1 in the GUI G3 end-to-end corpus (D-31 addendum, D-656).
#: v2 (D-656): agentdojo-live@2 and autodojo-live@2 in the live-pilot scratch corpora (checked 2026-10-23, item 167).
ARCHIVE_SHA256 = {
    ("agentdojo-live", 1): "388950f31180751dac530ec253e880ec9d00bf02fd32885f2cf43bf82e97f44a",
    ("autodojo-live", 1): "5d75391f4571b69cf1d457b806704e8b8a97832db8aab0ef98c51fe727a37426",
    ("agentdojo-live", 2): "b99530f26779db2af6cb6791fef1ab025c44bd372940073a608b6ffb5b3e2ddc",
    ("autodojo-live", 2): "d8f9486d9a26cd2b205c209b0b2231898e3d556beef07fb1d28d96dee66641cf",
}


@pytest.mark.parametrize(("pid", "version"), sorted(ARCHIVE_SHA256))
def test_the_archives_are_pinned(pid, version):
    import hashlib

    from agentprov.adapters.profiles import load_profile

    path = (Path(__file__).resolve().parents[3] / "src/agentprov/adapters/agentdojo/profiles/archive"
            / f"{pid}.profile.v{version}.toml")
    assert hashlib.sha256(path.read_bytes()).hexdigest() == ARCHIVE_SHA256[(pid, version)]
    assert load_profile(pid, version).sha256 == ARCHIVE_SHA256[(pid, version)]
    assert load_profile(pid).version == 3


def test_melon_block_maps_the_masked_run_and_the_replaced_reply():
    m = _mapped("defence_melon_block")
    calls = m.of_kind("model_call")
    by_actor = {(c["actor"], c["role"]) for c in calls}
    assert by_actor == {("agent", "agent"), ("def0", "auxiliary")}
    masked_and_embeddings = [c for c in calls if c["actor"] == "def0"]
    assert len(masked_and_embeddings) == 3 and all(c["input"] == [] for c in masked_and_embeddings)
    assert any("defence.detached_input@1#/input" in c.get("rule", []) for c in masked_and_embeddings)
    replaced = next(c for c in calls if c.get("reason") == "replaced_by_defence")
    assert replaced["actor"] == "agent" and replaced["status"] == "discarded"
    decisions = {d["verdict"]: d for d in m.of_kind("decision")}
    assert decisions["modify"]["subject"] == replaced["id"] and "$blob" in json.dumps(decisions["modify"]["original"])
    stop = next(r for r in m.of_kind("message") if r.get("generated_by") == decisions["modify"]["id"])
    assert (stop["role"], stop["actor"]) == ("assistant", "def0")
    discarded = next(r for r in m.of_kind("message") if r.get("generated_by") == replaced["id"])
    assert "actor" not in discarded  # the agent's replaced reply: kept, excluded from views, no answer of the agent
    sent = next(c for c in calls if c["actor"] == "agent" and any(isinstance(i, dict) for i in c.get("input", [])))
    assert "defence.sent_before_decision@1#/input/3/sent" in sent["rule"]


def test_melon_pass_records_an_allow_with_melon_s_score():
    m = _mapped("defence_melon_pass")
    (decision,) = m.of_kind("decision")
    assert decision["verdict"] == "allow" and decision["reason"].startswith("route=PASS")
