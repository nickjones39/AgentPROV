"""The semantics profile ``credleak.tools`` (docs/architecture D.19.9; C.14): tables, fail-closed names, taint; version 2
(D-605) is version 1's tables on the credleak catalogue version 2."""

from __future__ import annotations

import tomllib
from importlib import resources

from agentprov.adapters.semantics_profiles import load_semantics_profile


def _tables():
    node = resources.files("agentprov").joinpath("adapters", "credleak", "semantics", "credleak.tools-1", "tables.toml")
    return tomllib.loads(node.read_text(encoding="utf-8"))


def test_roles_and_labels_follow_the_tables(mapped):
    tools = {t["name"]: t for t in _tables()["tool"]}
    seen_unknown = 0
    for runs in mapped.values():
        for m in runs:
            by_target = {}
            for a in m.sem.annotations:
                by_target.setdefault((a["target"], a["type"]), a)
            for te in m.of("tool_execution"):
                role = by_target[(te["id"], "role")]
                expected = tools[te["name"]]["roles"] if te["name"] in tools else ["unknown"]
                assert role["value"] == expected and role["ev"] == "I"
                seen_unknown += te["name"] not in tools
                result = next(r for r in m.of("message") if r.get("generated_by") == te["id"])
                integrity = by_target[(f"{result['id']}#0", "integrity")]
                assert integrity["value"] == (tools[te["name"]]["integrity"] if te["name"] in tools else "unknown")
            for user in [r for r in m.of("message") if r["role"] == "user"]:
                if user["parts"]:
                    assert by_target[(f"{user['id']}#0", "integrity")]["value"] == "trusted"
    assert seen_unknown > 0  # the variant names some models emitted are never read as a known tool


def test_the_taint_policy():
    for version in (1, 2):
        profile = load_semantics_profile("credleak.tools", version)
        policy = profile.taint_policy
        assert policy is not None and policy.rule == "credleak.taint_sink_untrusted@1"
        assert policy.subject_roles == frozenset({"write_sink", "send_sink", "execute_sink", "egress_read", "unknown"})
        assert policy.object_integrity == frozenset({"untrusted", "unknown"})
        assert profile.rules == {"credleak": version}  # D-605: one catalogue version per corpus (H.2.5)


def test_version_2_has_the_tables_of_version_1():
    """D-605 changes only the catalogue version that credleak.tools declares; version 1's bytes are unchanged (the
    digest the corpora recorded)."""
    node = resources.files("agentprov").joinpath("adapters", "credleak", "semantics")
    one, two = (node.joinpath(f"credleak.tools-{v}", "tables.toml").read_text(encoding="utf-8") for v in (1, 2))
    assert tomllib.loads(one) == tomllib.loads(two)
    assert load_semantics_profile("credleak.tools", 1).sha256.removeprefix("sha256:").startswith("721620e801f2")
