"""The semantics profile ``mcphunt.tools`` at the version the profile selects (docs/architecture D.21.8; C.14) on the
committed fixtures."""

from __future__ import annotations

import mcphunt_support as support

from agentprov.adapters.semantics_profiles import load_semantics_profile


def _by_target(m, type_):
    return {a["target"]: a for a in m.annotations(type_)}


def test_tool_labels(mapped):
    profile = load_semantics_profile("mcphunt.tools", support.SEM_VERSION)
    assert profile.tool_label("filesystem", "write_file")[:2] == (("write_sink",), "unknown")
    assert profile.tool_label("shell", "execute_command")[:2] == (("execute_sink",), "unknown")
    assert profile.tool_label("fetch", "fetch")[:2] == (("egress_read",), "untrusted")
    assert profile.tool_label("unknown", "write") == (("unknown",), "unknown", ("mcphunt.unknown_tool@1",))
    m = mapped["web_servers"]
    roles = _by_target(m, "role")
    names = {a["id"]: a["name"] for a in m.of("actor")}
    for te in m.of("tool_execution"):
        assert roles[te["id"]]["value"] == list(profile.tool_label(names[te["actor"]], te["name"])[0])


def test_integrity_and_channels(mapped):
    m = mapped["web_servers"]
    integrity, channel = _by_target(m, "integrity"), _by_target(m, "channel")
    assert integrity["m0#0"]["value"] == integrity["m1#0"]["value"] == "trusted"
    for rec in m.of("message"):
        for k, part in enumerate(rec["parts"]):
            pid = f"{rec['id']}#{k}"
            if part["t"] == "tool_result":
                assert integrity[pid]["value"] in ("unknown", "untrusted") and pid in channel
            elif rec["actor"] == "agent":
                assert integrity[pid]["value"] == "trusted"
    assert "web" in {a["value"] for a in channel.values()}


def test_outcomes(mapped):
    for crit, m in mapped.items():
        claims = {a["value"]["claim"]: a["value"]["holds"] for a in m.annotations("outcome")}
        by_name = {j["name"]: j["value"] for j in m.of("judgement")}
        assert claims["mcphunt.unsafe"] is by_name["outcome"].startswith("unsafe"), crit
        assert claims["user_task_solved"] is by_name["task_completed"], crit


def test_taint_policy():
    profile = load_semantics_profile("mcphunt.tools", support.SEM_VERSION)
    assert profile.taint_policy is not None and profile.taint_policy.rule == "mcphunt.taint_sink_untrusted@1"
