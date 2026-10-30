"""The configuration join (docs/architecture D.16.5): path rule, allowlist, tiers and normalisations."""

from __future__ import annotations

import datetime as dt

import dtap_support as support

from agentprov.adapters.dtap.dialect import config_path, parse_path
from agentprov.adapters.dtap.join import allowlisted, compare, task_id_relation, verify


def test_path_rule():
    for fid in ("F01", "F02", "F09", "F10", "F13", "F16"):
        facets = parse_path(support.F[fid])
        assert facets is not None
        path = config_path(facets)
        assert path.endswith("/config.yaml") and path.startswith(facets.domain + "/")
        if facets.threat in ("direct_prompt", "direct_no_attack"):
            assert "/malicious/direct/" in path


def test_allowlist_keeps_task_attack_and_system_prompt_and_drops_everything_else():
    document = {
        "Task": {"task_id": "t", "task_instruction": "do it", "env_vars": {"K": "v"}},
        "Agent": {"name": "n", "system_prompt": "sp", "mcp_servers": [{"name": "gmail", "env_vars": {"TOKEN": "x"}}]},
        "Attack": {"malicious_goal": "g", "attack_turns": [{"attack_steps": [{"type": "tool", "content": "c",
                                                                             "env_vars": {"A": "b"}}]}], "when": dt.date(2026, 4, 26)},
        "RedTeamingAgent": {"available_injections": {}}, "Environment": {}, "Policies": [],
    }
    config, converted = allowlisted(document)
    assert config == {"Task": {"task_id": "t", "task_instruction": "do it"}, "Agent": {"system_prompt": "sp"},
                      "Attack": {"malicious_goal": "g", "attack_turns": [{"attack_steps": [{"type": "tool", "content": "c"}]}],
                                 "when": "2026-04-26"}}
    assert converted == 1 and "env_vars" not in repr(config)


def test_text_relations():
    assert compare("a b", "a b", instruction=True) == "exact"
    assert compare("a b", "a  b\n", instruction=True) == "whitespace"
    assert compare("x" * 500, "x" * 700, instruction=True) == "prefix_500"
    assert compare("x" * 10, "x" * 70, instruction=True) == "run_prefix"
    assert compare("goal and more", "goal", instruction=False) == "prefix"
    assert compare("goal and more", "goal", instruction=True) == "config_prefix"
    assert compare(None, "x", instruction=True) == "absent" and compare("a", "b", instruction=False) == "differs"


def test_task_id_relations():
    assert task_id_relation("billing-support-047", "billing-support-048", "medical") == "offset_medical"
    assert task_id_relation("billing-support-047", "billing-support-048", "finance") == "differs"
    assert task_id_relation("credential_takeover", "credential_takeover_001", "telecom") == "reformatted"
    assert task_id_relation("abc-1_001", "abc-1-001", "customer-service") == "reformatted"
    assert task_id_relation("x", "x", "code") == "equal" and task_id_relation(None, "x", "code") == "absent"


def test_tiers(mapped):
    join = {fid: m.header["ext"]["dtap"]["join"] for fid, m in mapped.items() if fid != "X02"}  # X02: judge-only, no run text
    assert join["F01"]["tier"] == "A" and join["F01"]["instruction"] in ("exact", "whitespace")
    # material drift (macos benign): the instruction differs; a benign goal check (empty text) always verifies, so the
    # tier is B, not the C of the D.16.14 fixture table (correction D.16.18 item 4)
    assert join["F14"]["tier"] == "B" and join["F14"]["instruction"] == "differs"
    assert join["F12"]["tier"] in ("B", "C")
    assert join["F15"]["status"] == "missing" and "tier" not in join["F15"]
    assert join["F13"]["task_id"] == "offset_medical" and join["F13"]["tier"] == "A"
    assert join["F10"]["instruction"] == "not_applicable" and join["F10"]["goal"] == "exact"
    assert join["F09"]["config_path"].startswith("finance/malicious/direct/")
    for fid in join:
        assert mapped[fid].header["evf"]["/ext/dtap/join"] == "D", fid
    # a 500-character instruction that is a verified prefix is disclosed under the D rule
    rule = "dtap.instruction_cut_500@1"
    cut = [i for i in mapped["X01"].issues if i["code"] == "dtap.task_info_truncated"]
    assert cut and cut[0]["rule"] in (rule, "dtap.instruction_length_500_unverified@1")


def test_verify_direct_uses_the_prompt_step_or_the_goal():
    facets = parse_path("openaisdk/m/d/malicious/direct/r/1/20260101_000000.json")
    assert facets is not None
    config = {"Attack": {"malicious_goal": "the goal", "attack_turns": [{"attack_steps": [{"type": "prompt", "mode": "jailbreak",
                                                                                          "content": "wrapped the goal"}]}]}}
    assert verify(facets, {"original_instruction": "wrapped the goal", "malicious_instruction": "the goal"}, config)[:3] == (
        "A", "exact", "exact")
    assert verify(facets, {"original_instruction": "other", "malicious_instruction": "nope"}, config)[0] == "C"
