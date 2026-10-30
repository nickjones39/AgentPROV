"""The ``foobench`` rule catalogue: self-test and coverage (docs/architecture D.12.1 row 5, D.5.2; K.6.4).

Coverage runs both ways: every rule and issue code the mapper emits is declared (the writer and the runner reject an
undeclared one at map time, and this test checks the sealed output and the source), and every declared rule and issue code
is exercised by the fixture.
"""

from __future__ import annotations

import ast
import re
from importlib import resources
from pathlib import Path

from agentprov.aer.rules import RULE_ID_RE, load_catalogue, parse_catalogue

PACKAGE = "agentprov.adapters.foobench"
MAPPER = Path(__file__).resolve().parents[3] / "src" / "agentprov" / "adapters" / "foobench" / "mapper.py"
ISSUE_CODES = {"unmapped_event_type", "restore_unmodelled", "observation_unlinked", "handoff_not_expanded"}
TYPES = {
    "foobench:plan_step", "foobench:plan", "foobench:memory_item", "foobench:memory_read", "foobench:memory_snippet",
    "foobench:observe", "foobench:screenshot",
}  # fmt: skip
#: D.12.1 row 5 and the rules the mapping needed (statement names in the catalogue).
EXPECTED_RULES = {
    "foobench.schema_is_foobench@1", "foobench.actor_table@1", "foobench.thread_scopes@1", "foobench.call_id_match@1",
    "foobench.event_implies_success@1", "foobench.verdict_table@1", "foobench.memory_key_match@1", "foobench.plan_media_json@1",
    "foobench.text_action_parse@1", "foobench.handoff_sub_file@1", "foobench.unknown_event_kept@1",
    "foobench.restore_not_linearised@1", "foobench.observation_injected@1",
}  # fmt: skip
#: Rules of the semantics profile foobench.toy@1 (D.12.1 row 7): cited by SEM annotations, never by the AER or the
#: mapper (tests/adapters/foobench/test_semantics.py covers them).
SEM_RULES = {
    "foobench.tool_role_table@1", "foobench.tool_output_label_table@1", "foobench.artefact_label_table@1",
    "foobench.observation_label_table@1", "foobench.taint_sink_untrusted@1",
}  # fmt: skip


def catalogue():
    return load_catalogue("foobench", 1, package=PACKAGE)


def cited(records: list[dict]) -> set[str]:
    """Every rule id the AER cites: records, header, seal issues and accounting checks (the ``aer`` ones)."""
    out: set[str] = set()
    for rec in records:
        out.update(ref.split("#", 1)[0] for ref in rec.get("rule", []))
        out.update(i["rule"].split("#", 1)[0] for i in rec.get("issues", []))
    return out


def test_the_catalogue_is_the_d12_one_and_passes_the_self_test():
    cat = catalogue()
    assert (cat.namespace, cat.version, cat.format) == ("foobench", 1, "agentprov-rule-catalogue/0.1")
    assert set(cat.rules) == EXPECTED_RULES | SEM_RULES and cat.issue_codes == ISSUE_CODES and cat.types == TYPES and cat.subtypes == frozenset()
    data = (resources.files(PACKAGE) / "rules" / "foobench.rules.toml").read_bytes()
    assert parse_catalogue(data).digest == cat.digest  # the D.5.2 self-test items 1-5 run on every parse
    for rid, rule in cat.rules.items():
        assert RULE_ID_RE.fullmatch(rid) and rule.status == "active" and rule.cls in ("D", "I") and rule.statement.endswith(".")
        assert rule.assumptions == () and rule.verification == ()  # a toy format: no assumption is asserted or verified
    assert {rid for rid, r in cat.rules.items() if r.cls == "I"} == {"foobench.text_action_parse@1"} | SEM_RULES


def test_every_tests_node_id_of_the_catalogue_exists():
    import tomllib

    doc = tomllib.loads((resources.files(PACKAGE) / "rules" / "foobench.rules.toml").read_text(encoding="utf-8"))
    for rule in doc["rule"]:
        assert rule["tests"], rule["id"]
        for node in rule["tests"]:
            path, _, name = node.partition("::")
            tree = ast.parse((Path(__file__).resolve().parents[3] / path).read_text(encoding="utf-8"))
            assert name in {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}, node


def test_every_emitted_rule_and_issue_is_declared(foo, mapped):
    cat = catalogue()
    foobench = {r for r in cited(mapped.records) if r.startswith("foobench.")}
    assert foobench <= set(cat.rules)
    for issue in mapped.issues:
        assert RULE_ID_RE.fullmatch(issue["rule"].split("#", 1)[0])
        if issue["code"].startswith("foobench."):
            assert cat.declares_issue_code(issue["code"])
            assert issue["rule"] in cat.rules
    # the same holds on the unhappy paths: a missing sub-agent file, an unknown verdict, an unfinished tool
    events = foo.events(foo.raw(foo.PRIMARY))
    next(e for e in events if e.get("type") == "approval")["decision"] = "defer"
    events.append({"type": "tool_start", "ts": "2026-10-01T12:01:00Z", "call": "c6", "name": "delete_file", "args": {}})
    for variant in (foo.map(foo.raw(foo.PRIMARY), None), foo.map(foo.lines(events))):
        assert {r for r in cited(variant.records) if r.startswith("foobench.")} <= set(cat.rules)
        for issue in variant.issues:
            assert not issue["code"].startswith("foobench.") or cat.declares_issue_code(issue["code"])


def test_every_declared_rule_is_exercised(mapped):
    exercised = {r for r in cited(mapped.records) if r.startswith("foobench.")}
    assert exercised == set(catalogue().rules) - SEM_RULES  # the SEM profile's rules are exercised by test_semantics.py
    # handoff_not_expanded needs a hand-off deeper than 4 or a cycle, which the D.12 fixture has not: test_core_d.py
    assert {i["code"].removeprefix("foobench.") for i in mapped.issues if i["code"].startswith("foobench.")} == \
        ISSUE_CODES - {"handoff_not_expanded"}


def test_the_mapper_source_cites_exactly_the_declared_rules_and_codes():
    source = MAPPER.read_text(encoding="utf-8")
    literals = set(re.findall(r'"(foobench\.[a-z_]+@[0-9]+)"', source))
    assert literals == set(catalogue().rules) - SEM_RULES
    codes = set(re.findall(r'issue="([a-z_]+)"', source)) | {c.removeprefix("foobench.") for c in re.findall(r'"(foobench\.[a-z_]+)"', source)}
    assert {c for c in codes if c in ISSUE_CODES} == ISSUE_CODES


def test_every_activity_and_artefact_type_in_the_aer_is_declared(mapped):
    types = {r["type"] for r in mapped.records if r["k"] in ("activity", "artefact")}
    assert types == TYPES <= catalogue().types
    assert "foobench" in mapped.records[0]["ns"]  # the namespace of every type is declared in execution.ns (C.10)
