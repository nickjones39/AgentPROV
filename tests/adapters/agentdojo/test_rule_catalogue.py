"""The ``agentdojo`` rule catalogue (docs/architecture D.5.1-D.5.5, D.6.10 item 6).

* Every ``agentdojo.*`` rule of the D.5.4 index is declared, at the class the index gives.
* Every ``tests`` node of every rule exists (D.5.2 validation item 6); every ``code`` entry names a full commit.
* No rule declares a ``verified`` assumption (the June-2024 AER records no framework identity, AER-V34; D.6.11).
* Reserved rules cannot be cited.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

from agentprov.aer.rules import load_catalogue
from agentprov.errors import RuleNotDeclared

REPO = Path(__file__).resolve().parents[3]
CATALOGUE = REPO / "src" / "agentprov" / "adapters" / "agentdojo" / "rules" / "agentdojo.rules.toml"
SPEC = REPO / "docs" / "architecture" / "D_adapters.md"


def _index() -> dict[str, str]:
    """``agentdojo.*`` rule ids and classes of the D.5.4 table."""
    text = SPEC.read_text(encoding="utf-8")
    section = text.split("### D.5.4 Initial rule index (v0.1)", 1)[1].split("### D.5.5", 1)[0]
    out: dict[str, str] = {}
    for line in section.splitlines():
        match = re.match(r"^\| `(agentdojo\.[a-z0-9_]+)`(?: \([a-z]+\))? \| ([DI]) \|", line)
        if match:
            out[match.group(1)] = match.group(2)
    return out


def test_every_d54_agentdojo_rule_is_declared_at_its_class():
    catalogue = load_catalogue("agentdojo")
    index = _index()
    assert len(index) >= 40
    for rule_id, cls in index.items():
        entry = catalogue.get(f"{rule_id}@1")
        assert entry is not None, rule_id
        assert entry.cls == cls, rule_id


def test_planned_variant_rules_are_declared():
    """Rules for v1.k14 and the head part (phase 10) and SEM readings are declared now, so the catalogue is complete."""
    catalogue = load_catalogue("agentdojo")
    for name in ("args_are_effective", "naive_local_timestamp", "naive_local_timestamp_unverified", "committed_no_later_than",
                 "benchmark_era_from_commit", "local_model_tag_count", "placeholder_args_ground_truth_only",
                 "security_polarity"):
        entry = catalogue.get(f"agentdojo.{name}@1")
        assert entry is not None and entry.citable


def test_reserved_rules_cannot_be_cited():
    from agentprov.adapters.profiles import load_profile
    from agentprov.adapters.runner import MapContext
    from agentprov.aer.rules import RuleRegistry

    entry = load_catalogue("agentdojo").get("agentdojo.record_complete_with_replay@1")
    assert entry is not None and entry.status == "reserved" and not entry.citable
    ctx = MapContext(load_profile("agentdojo-upstream"), RuleRegistry.default(), "m", "ex_x")
    with pytest.raises(RuleNotDeclared):
        ctx.rule("agentdojo.record_complete_with_replay@1")


def test_catalogue_test_references_exist_and_commits_are_full():
    doc = tomllib.loads(CATALOGUE.read_text(encoding="utf-8"))
    for rule in doc["rule"]:
        for node in rule.get("tests", []):
            file, _, name = node.partition("::")
            assert f"def {name}(" in (REPO / file).read_text(encoding="utf-8"), f"{rule['id']}: {node}"
        for code in rule.get("code", []):
            assert re.fullmatch(r"[0-9a-f]{40}", code["commit"]), rule["id"]
        for verification in rule.get("verification", []):
            assert verification["status"] == "asserted", rule["id"]


def test_issue_codes_are_the_spec_codes():
    catalogue = load_catalogue("agentdojo")
    for code in ("pipeline_name_mismatch", "local_parse_drop_possible", "multi_block_tool_content", "unknown_top_level_key",
                 "undeclared_quirk", "unknown_message_shape", "path_field_mismatch", "mixed_content_forms",
                 "system_prompt_unrecognised"):
        assert catalogue.declares_issue_code(f"agentdojo.{code}")


def test_the_generic_defence_denial_rule_is_declared_class_i():
    """Phase-10d R1: one profile-parametric rule for defence refusals logged as tool errors (seven sources). Class I, so
    no `_unverified` twin is needed (D.5.4); the hook that cites it ships with the phase-10d profiles."""
    entry = load_catalogue("agentdojo").get("agentdojo.defence_denial_message@1")
    assert entry is not None and entry.cls == "I" and entry.citable and entry.premises == ("/messages",)
    assert load_catalogue("agentdojo").get("agentdojo.defence_denial_message_unverified@1") is None
