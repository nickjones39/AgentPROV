"""The ``agentops`` rule catalogue (docs/architecture D.18.9; D.5.2): self-test, citation policy and coverage both ways."""

from __future__ import annotations

import ast
import re
import tomllib
from importlib import resources

import agentops_support as support

from agentprov.aer.rules import RULE_ID_RE, load_catalogue, parse_catalogue

PACKAGE = "agentprov.adapters.agentops"
SRC = support.REPO / "src" / "agentprov" / "adapters" / "agentops"
ISSUE_CODES = {
    "empty_trace", "run_error", "iteration_limit", "task_join_missing", "user_message_not_logged", "unlisted_tool_name",
    "dispatch_error_result", "final_output_differs", "label_field_mismatch", "payload_suffix_mismatch",
    "failure_with_payload", "repeated_tool_names", "payload_outside_adversarial", "value_redacted",
}  # fmt: skip


def catalogue():
    return load_catalogue("agentops", 2, package=PACKAGE)  # D-31 bump with regen items 34-37; v1 is archived


def test_the_catalogue_passes_the_self_test_and_the_citation_policy():
    cat = catalogue()
    assert (cat.namespace, cat.version, cat.format) == ("agentops", 2, "agentprov-rule-catalogue/0.1")
    assert cat.issue_codes == ISSUE_CODES and cat.subtypes == {"agentops.fault_injection"} and cat.types == set()
    data = (resources.files(PACKAGE) / "rules" / "agentops.rules.toml").read_bytes()
    assert parse_catalogue(data).digest == cat.digest
    for rule in tomllib.loads(data.decode("utf-8"))["rule"]:
        rid = f"{rule['id']}@{rule['version']}"
        assert RULE_ID_RE.fullmatch(rid) and rule["statement"].endswith(".") and rule["code"] == [], rid
        if rule["class"] == "D":  # deterministic functions of observed bytes or package data: no assumption
            assert rule["assumptions"] == [] and rule["evidence"], rid
        else:  # the producing code is not verified (D-193): every assumption is asserted, and the name says so
            assert rule["assumptions"] and all(v["status"] == "asserted" for v in rule["verification"]) or \
                not rule["id"].endswith("_unverified"), rid
        if rule["id"].endswith("_unverified"):
            assert rule["class"] == "I", rid


def test_every_tests_node_id_of_the_catalogue_exists():
    doc = tomllib.loads((resources.files(PACKAGE) / "rules" / "agentops.rules.toml").read_text(encoding="utf-8"))
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
        assert {r for r in _cited(m) if r.startswith("agentops.")} <= set(cat.rules), crit
        for issue in m.issues:
            if issue["code"].startswith("agentops."):
                assert cat.declares_issue_code(issue["code"]), (crit, issue["code"])


def test_every_declared_rule_is_exercised(mapped):
    """Coverage the other way: every citable rule is cited by an AER, a SEM document or a seal of the fixtures or of the
    derived inputs below; reserved rules are artefact-catalogue detector names (test_artefacts.py)."""
    from agentprov.adapters.agentops.semantics.tools import CITED_RULES

    cited: set[str] = set()
    for m in mapped.values():
        cited |= _cited(m)
        cited |= {r.split("#", 1)[0] for a in m.sem.annotations for r in a["rule"]}
    cited |= _cited(support.modified("clean_safety_plain", lambda v: v["trace"].update(completed=False)))
    cited |= _cited(support.modified("clean_safety_plain", lambda v: v.update(run_number=3)))
    cited |= set(CITED_RULES)  # the profile's rules are checked annotation by annotation in test_semantics.py
    disclosures = {"agentops.final_output_copy@1", "agentops.payload_suffix@1"}  # raised by test_mapper.py derived inputs
    disclosures.add("agentops.value_redacted@1")  # D-608: no fixture holds an account path; test_redact.py builds runs
    citable = {rid for rid, rule in catalogue().rules.items() if rule.citable}
    assert citable - cited - disclosures == set(), sorted(citable - cited - disclosures)


def test_the_mapper_source_cites_only_declared_rules():
    source = (SRC / "mapper.py").read_text(encoding="utf-8") + (SRC / "semantics" / "tools.py").read_text(encoding="utf-8")
    source += (SRC / "pairing.py").read_text(encoding="utf-8")
    literals = set(re.findall(r'"(agentops\.[a-z_.]+@[0-9]+)"', source))
    assert literals <= set(catalogue().rules) and literals
    codes = {c.removeprefix("agentops.") for c in re.findall(r'"(agentops\.[a-z_]+)"', source)} & ISSUE_CODES
    assert codes == ISSUE_CODES  # every declared issue code is raised somewhere in the mapper


def test_profile_quirks_and_pairing_name_catalogue_rules():
    from agentprov.adapters.profiles import load_profile

    family = load_profile(support.PROFILE).family_table()
    for quirk in family["quirk"]:
        assert all(r in catalogue().rules for r in quirk["rules"]), quirk["id"]
    assert family["pairing"] in catalogue().rules
