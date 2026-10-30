"""Family fixes from the corpus pre-check, wave 2 (D-586..D-588; regeneration-batch items 111-113).

Each profile goes to version 2 because the pre-check scratch corpora
(``~/.agentprov/migration-work/precheck/<corpus>/l2-head-j{1,2}.partial``) recorded version 1. Version 1 ships byte
for byte under ``profiles/archive/`` (D-31 owner ruling 2026-10-21). Failures print ids and tokens only, never log
content."""

from __future__ import annotations

from typing import Any

import phase10d_support as p10d
import pytest

from agentprov.adapters.agentdojo.profile import family_table
from agentprov.adapters.profiles import load_profile

#: The profile digests the pre-check scratch corpora record in derivation.json (both j1 and j2), for version 1.
RECORDED_V1 = {
    "geryon-agentdojo": "76324274295b1d87139fd13f2586fb96cdd6edc13decf5a33325587f39eeaeaf",
    "kongminos-agentdojo": "bd58983eca2e4dcba687fa48c999b1bb1e81b38cbedf261b0ebdbc6bb4df251b",
    "melon-agentdojo": "9757a714918c90aa1f515e25d836e47cbfc97e7b4b85b84f88a60a6da5846ee0",
    "seagent-agentdojo": "30b76ce0183f44eb9ccbfbdf1745c862ec48aab1c721e1f315b155c08e32aef4",
    "tacit-agentdojo": "ee686ef7d1daea594dba1ee0290fdb6576fb9496b23d3e5145d5515f0e47f15e",
}
SOURCES = {s.name: s for s in p10d.SOURCES}


@pytest.mark.parametrize("profile_id", sorted(RECORDED_V1))
def test_version_2_with_the_recorded_version_1_archived(profile_id):
    assert load_profile(profile_id).version == 2
    archived = load_profile(profile_id, 1)
    assert archived.version == 1 and archived.sha256 == RECORDED_V1[profile_id]


def _mapped(name: str) -> list[tuple[str, Any]]:
    src = SOURCES[name]
    return [(entry["original_path"], p10d.map_fixture(src, entry)) for entry in p10d.fixture_entries(src)]


# ------------------------------------------------------------------------------------------------ tacit (D-587)
def test_tacit_declares_the_local_model_quirk_for_the_llama_pipeline_only():
    (quirk,) = [q for q in family_table(load_profile("tacit-agentdojo")).quirks
                if q.id == "agentdojo.local_model_raw_completion"]
    assert quirk.matches({"pipeline_dir": "local"}) and not quirk.matches({"pipeline_dir": "vllm_parsed"})
    assert quirk.rules == ("agentdojo.local_model_tag_count@1",)


@pytest.mark.parametrize("name", ["tacit", "kongminos"])  # D-587, D-590
def test_local_model_turns_with_more_tags_than_calls_are_flagged_and_never_reparsed(name):
    flagged = 0
    for path, m in _mapped(name):
        issues = m.issues("agentdojo.local_parse_drop_possible")
        tagged = [r for r in m.of_kind("message") if "local_model_tag_count" in r.get("ext", {}).get("agentdojo", {})]
        if "/vllm_parsed/" in path:
            assert not issues and not tagged, path  # the vLLM client parses calls server-side
            continue
        flagged += len(issues)
        for issue in issues:
            assert issue["rule"] == "agentdojo.local_model_tag_count@1"
            (msg,) = [r for r in m.of_kind("message") if r["id"] in issue["ids"]]
            n_calls = sum(1 for part in msg["parts"] if part["t"] == "tool_call")
            assert msg["ext"]["agentdojo"]["local_model_tag_count"] > n_calls, path
    if name == "tacit":
        assert flagged > 0
    else:  # the kongminos fixtures hold no such turn; the quirk still covers their pipeline directory
        (quirk,) = [q for q in family_table(load_profile("kongminos-agentdojo")).quirks
                    if q.id == "agentdojo.local_model_raw_completion"]
        assert quirk.matches({"pipeline_dir": "local"})


# ------------------------------------------------------------------------------------------------ geryon (D-588)
QWEN, GPT = "qwen.qwen3-235b-a22b-2507", "openai.gpt-oss-120b"


def test_geryon_table_gives_every_recorded_condition_b_log_set_its_policy_model():
    rows = family_table(load_profile("geryon-agentdojo")).table_rows
    for name, row in rows.items():
        run_set, log_set = name.split("/")
        if "-B-" not in log_set or run_set == "runs-claude-policy":  # condition A, or no run record
            assert "defence_model" not in row, name
        else:
            assert row["defence"] == "progent", name
            assert row["defence_model"] == (QWEN if run_set.startswith("runs-strong-policy") else GPT), name


def test_geryon_defence_actor_carries_the_policy_model_from_the_identity():
    seen = set()
    for path, m in _mapped("geryon"):
        defences = [r for r in m.of_kind("actor") if r["kind"] == "defense"]
        if "-A-" in path:
            assert defences == [], path
            continue
        (actor,) = defences
        assert actor["name"] == "progent" and actor["ev"] == "I"
        if "/runs-claude-policy/" in path:  # no run record: nothing is guessed
            assert "model" not in actor and actor["unk"]["/model"] == "not_recorded"
            seen.add("not_recorded")
        else:
            assert actor["model"] == {"requested": GPT if "/runs-strong-policy" not in path else QWEN}
            assert "agentdojo.pipeline_dir_is_model_identity@1#/model" in actor["rule"]
            assert actor["unk"] == {"/model/provider": "not_recorded", "/model/served": "not_recorded",
                                    "/version": "not_recorded"}
            seen.add("model")
    assert seen == {"model", "not_recorded"}
