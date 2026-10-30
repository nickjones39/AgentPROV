"""The ``wirelog`` rule catalogue (docs/architecture D.20.9; D.5.2): self-test, citation policy and coverage both ways."""

from __future__ import annotations

import ast
import re
import tomllib
from importlib import resources

import wirelog_support as support

from agentprov.aer.rules import RULE_ID_RE, load_catalogue, parse_catalogue

PACKAGE = "agentprov.adapters.wirelog"
SRC = support.REPO / "src" / "agentprov" / "adapters" / "wirelog"
ISSUE_CODES = {
    "label_field_mismatch", "context_diverges", "unknown_block", "payload_not_delivered", "payload_entry_missing",
    "final_texts_not_logged", "meta_rewritten", "task_prompt_unlisted", "results_row_missing", "unreadable_auxiliary",
    "turn_limit",
}  # fmt: skip


def catalogue():
    return load_catalogue("wirelog", 1, package=PACKAGE)


def test_the_catalogue_passes_the_self_test_and_the_citation_policy():
    cat = catalogue()
    assert (cat.namespace, cat.version, cat.format) == ("wirelog", 1, "agentprov-rule-catalogue/0.1")
    assert cat.issue_codes == ISSUE_CODES and cat.subtypes == set() and cat.types == set()
    data = (resources.files(PACKAGE) / "rules" / "wirelog.rules.toml").read_bytes()
    assert parse_catalogue(data).digest == cat.digest
    for rule in tomllib.loads(data.decode("utf-8"))["rule"]:
        rid = f"{rule['id']}@{rule['version']}"
        assert RULE_ID_RE.fullmatch(rid) and rule["statement"].endswith(".") and rule["code"] == [], rid
        if rule["class"] == "D":  # deterministic functions of logged bytes or package data: no assumption
            assert rule["assumptions"] == [] and rule["evidence"], rid
        if rule["id"].endswith("_unverified"):  # harness behaviour (D-282): class I with asserted assumptions
            assert rule["class"] == "I" and rule["assumptions"], rid
            assert all(v["status"] == "asserted" for v in rule["verification"]), rid


def test_every_tests_node_id_of_the_catalogue_exists():
    doc = tomllib.loads((resources.files(PACKAGE) / "rules" / "wirelog.rules.toml").read_text(encoding="utf-8"))
    for rule in doc["rule"]:
        assert rule["tests"], rule["id"]
        for node in rule["tests"]:
            path, _, name = node.partition("::")
            tree = ast.parse((support.REPO / path).read_text(encoding="utf-8"))
            assert name in {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}, node


def _cited(m) -> set[str]:
    out: set[str] = set()
    for rec in m.records:
        out.update(ref.split("#", 1)[0] for ref in rec.get("rule", []))
    out.update(i["rule"].split("#", 1)[0] for i in m.issues)
    out.update(c["id"] for c in m.doc.seal["accounting"]["checks"])
    return out


def test_every_emitted_rule_and_issue_is_declared(mapped):
    cat = catalogue()
    for crit, m in mapped.items():
        assert {r for r in _cited(m) if r.startswith("wirelog.")} <= set(cat.rules), crit
        for issue in m.issues:
            if issue["code"].startswith("wirelog."):
                assert cat.declares_issue_code(issue["code"]), (crit, issue["code"])


def test_every_declared_rule_is_exercised(mapped):
    """Coverage the other way: every citable rule is cited by an AER, a SEM document or a seal of the fixtures; rules raised
    only by derived inputs are exercised in test_mapper.py; reserved rules are artefact detector names."""
    from agentprov.adapters.wirelog.semantics.tools import CITED_RULES

    cited: set[str] = set()
    for m in mapped.values():
        cited |= _cited(m)
        cited |= {r.split("#", 1)[0] for a in m.sem.annotations for r in a["rule"]}
    cited |= set(CITED_RULES)
    derived = {"wirelog.call_without_result@1", "wirelog.unknown_block@1", "wirelog.text_file_utf8@1",
               "wirelog.unreadable_run@1"}
    citable = {rid for rid, rule in catalogue().rules.items() if rule.citable}
    assert citable - cited - derived == set(), sorted(citable - cited - derived)


def test_the_mapper_source_cites_only_declared_rules():
    source = (SRC / "mapper.py").read_text(encoding="utf-8") + (SRC / "semantics" / "tools.py").read_text(encoding="utf-8")
    literals = set(re.findall(r'"(wirelog\.[a-z_.]+@[0-9]+)"', source))
    assert literals <= set(catalogue().rules) and literals
    codes = {c.removeprefix("wirelog.") for c in re.findall(r'"(wirelog\.[a-z_]+)"', source)} & ISSUE_CODES
    assert codes == ISSUE_CODES  # every declared issue code is raised somewhere in the mapper


def test_profile_quirks_name_catalogue_rules():
    from agentprov.adapters.profiles import load_profile

    family = load_profile(support.PROFILE).family_table()
    for quirk in family["quirk"]:
        assert all(r in catalogue().rules for r in quirk["rules"]), quirk["id"]
