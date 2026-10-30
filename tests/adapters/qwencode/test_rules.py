"""The ``qwencode`` rule catalogue (docs/architecture D.24.8; D.5.2): self-test, citation policy and coverage both ways."""

from __future__ import annotations

import ast
import re
import tomllib
from importlib import resources

import qwencode_support as support

from agentprov.aer.rules import RULE_ID_RE, load_catalogue, parse_catalogue

PACKAGE = "agentprov.adapters.qwencode"
SRC = support.REPO / "src" / "agentprov" / "adapters" / "qwencode"
ISSUE_CODES = {
    "user_message_not_logged", "truncated_capture", "no_result_message", "error_result", "unmapped_message",
    "subagent_event", "sidecar_missing", "join_unverified", "final_text_differs", "score_unrecognised",
    "extra_result_message",
}  # fmt: skip
TYPES = {"qwencode:subagent_event", "qwencode:unmapped_message", "qwencode:message_payload"}


def catalogue():
    return load_catalogue("qwencode", 2, package=PACKAGE)


def test_the_catalogue_passes_the_self_test_and_the_citation_policy():
    cat = catalogue()
    assert (cat.namespace, cat.version, cat.format) == ("qwencode", 2, "agentprov-rule-catalogue/0.1")
    assert cat.issue_codes == ISSUE_CODES and cat.subtypes == {"qwencode.content_block", "qwencode.execution_rules"} and cat.types == TYPES
    data = (resources.files(PACKAGE) / "rules" / "qwencode.rules.toml").read_bytes()
    assert parse_catalogue(data).digest == cat.digest
    for rule in tomllib.loads(data.decode("utf-8"))["rule"]:
        rid = f"{rule['id']}@{rule['version']}"
        assert RULE_ID_RE.fullmatch(rid) and rule["statement"].endswith(".") and rule["code"] == [], rid
        if rule["class"] == "D":  # deterministic functions of observed bytes: no assumption (D-574)
            assert rule["assumptions"] == [] and rule["evidence"], rid
        else:  # the CLI sources were not fetched: every assumption is asserted
            assert rule["assumptions"] and all(v["status"] == "asserted" for v in rule["verification"]), rid
        if rule["id"].endswith("_unverified"):
            assert rule["class"] == "I", rid


def test_every_tests_node_id_of_the_catalogue_exists():
    doc = tomllib.loads((resources.files(PACKAGE) / "rules" / "qwencode.rules.toml").read_text(encoding="utf-8"))
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
        assert {r for r in _cited(m) if r.startswith("qwencode.")} <= set(cat.rules), crit
        for issue in m.issues:
            if issue["code"].startswith("qwencode."):
                assert cat.declares_issue_code(issue["code"]), (crit, issue["code"])


def test_every_declared_rule_is_exercised(mapped):
    """Coverage the other way: every citable rule is cited by an AER, a SEM document or a seal of the fixtures or of the
    derived inputs below; reserved rules are artefact-catalogue detector names (test_artefacts.py)."""
    from agentprov.adapters.qwencode.semantics.tools import CITED_RULES

    cited: set[str] = set()
    for m in mapped.values():
        cited |= _cited(m)
        cited |= {r.split("#", 1)[0] for a in m.sem.annotations for r in a["rule"]}

    cited |= _cited(support.modified("python", lambda ms: [*ms[:-1], {**ms[-1], "is_error": True, "subtype": "x"}]))

    def odd(ms):
        ms.insert(-1, {"type": "status"})
        ms.insert(-1, {"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "nope", "is_error": False, "content": "orphan"}]}})
        ms[-1]["result"] = "changed"

    cited |= _cited(support.modified("python", odd))
    label = support.by_criterion("python")
    f = __import__("agentprov.adapters.qwencode.dialect", fromlist=["parse_label"]).parse_label(label)
    member = f"results/Qwen/{f.model}/{f.target}/{f.language}/conversation_log/index{f.scenario}.json"
    cited |= _cited(support.modified("python", supp={member: b"[]"}))
    cited |= set(CITED_RULES)  # the profile's rules are checked annotation by annotation in test_semantics.py
    citable = {rid for rid, rule in catalogue().rules.items() if rule.citable}
    assert citable - cited == set(), sorted(citable - cited)


def test_the_mapper_source_cites_only_declared_rules():
    source = (SRC / "mapper.py").read_text(encoding="utf-8") + (SRC / "semantics" / "tools.py").read_text(encoding="utf-8")
    source += (SRC / "dialect.py").read_text(encoding="utf-8")
    literals = set(re.findall(r'"(qwencode\.[a-z_.0-9]+@[0-9]+)"', source))
    assert literals <= set(catalogue().rules) and literals
    codes = {c.removeprefix("qwencode.") for c in re.findall(r'"(qwencode\.[a-z_]+)"', source)} & ISSUE_CODES
    assert codes == ISSUE_CODES  # every declared issue code is raised somewhere in the mapper


def test_profile_quirks_and_pairing_name_catalogue_rules():
    from agentprov.adapters.profiles import load_profile

    family = load_profile(support.PROFILE).family_table()
    for quirk in family["quirk"]:
        assert all(r in catalogue().rules for r in quirk["rules"]), quirk["id"]
    assert family["pairing"] in catalogue().rules
