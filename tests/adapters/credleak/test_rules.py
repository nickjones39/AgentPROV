"""The ``credleak`` rule catalogue (docs/architecture D.19.8; D.5.2): self-test, citation policy and coverage both ways."""

from __future__ import annotations

import ast
import json
import re
import tomllib
from importlib import resources

import credleak_support as support

from agentprov.aer.rules import RULE_ID_RE, load_catalogue, parse_catalogue

PACKAGE = "agentprov.adapters.credleak"
SRC = support.REPO / "src" / "agentprov" / "adapters" / "credleak"
ISSUE_CODES = {"path_outside_grammar", "turn_number_mismatch", "cell_run_disagree", "invocation_error", "value_redacted"}
SYNTH_LABEL = "p15b-run-data/01-injection-map/T1-file-document/test-model/run__T1__test-model__T1.9__2026.json"


def catalogue():
    return load_catalogue("credleak", 2, package=PACKAGE)


def test_the_catalogue_passes_the_self_test_and_the_citation_policy():
    cat = catalogue()
    assert (cat.namespace, cat.version, cat.format) == ("credleak", 2, "agentprov-rule-catalogue/0.1")
    assert cat.issue_codes == ISSUE_CODES and cat.types == set() and cat.subtypes == set()
    data = (resources.files(PACKAGE) / "rules" / "credleak.rules.toml").read_bytes()
    assert parse_catalogue(data).digest == cat.digest
    doc = tomllib.loads(data.decode("utf-8"))
    for rule in doc["rule"]:
        rid = f"{rule['id']}@{rule['version']}"
        assert RULE_ID_RE.fullmatch(rid) and rule["statement"].endswith(".") and rule["code"] == [], rid
        if rule["class"] == "D":  # deterministic functions of observed fields: no assumption, census evidence
            assert rule["assumptions"] == [] and rule["evidence"], rid
        for v in rule.get("verification", []):
            assert v["status"] == "asserted", rid  # no harness code of the study is verified


def test_every_tests_node_id_of_the_catalogue_exists():
    doc = tomllib.loads((resources.files(PACKAGE) / "rules" / "credleak.rules.toml").read_text(encoding="utf-8"))
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
    out.update(i["rule"].split("#", 1)[0] for i in m.issues if i.get("rule"))
    out.update(c["id"] for c in m.doc.seal["accounting"]["checks"])
    return out


def test_every_emitted_rule_and_issue_is_declared(mapped):
    cat = catalogue()
    for path, runs in mapped.items():
        for m in runs:
            assert {r for r in _cited(m) if r.startswith("credleak.")} <= set(cat.rules), path
            for issue in m.issues:
                if issue["code"].startswith("credleak."):
                    assert cat.declares_issue_code(issue["code"]), (path, issue["code"])


def test_every_declared_rule_is_exercised(mapped):
    """Every citable rule is cited by an AER, a SEM document or a seal of the fixtures plus the synthetic cells of
    test_mapper.py; reserved rules are artefact-catalogue detector names (test_artefacts.py keeps them uncited)."""
    cited: set[str] = set()
    for runs in mapped.values():
        for m in runs:
            cited |= _cited(m)
            cited |= {r.split("#", 1)[0] for a in m.sem.annotations for r in a["rule"]}
    value = json.loads(support.synthetic_cell(turns=[{"turnNumber": 3, "userMessage": "a", "assistantResponse": "b",
                                                      "timestamp": "2026-06-11T08:00:00.000Z", "toolCalls": []}]))
    value["runs"][0]["model"] = "other"
    for m in support.map_cell(SYNTH_LABEL, json.dumps(value).encode(), sem=False, prov=False):
        cited |= _cited(m)
    for m in support.map_cell("outside/grammar.json", support.synthetic_cell(), sem=False, prov=False):
        cited |= _cited(m)
    account = "/home/" + "tst" + "acct/x"  # D-605: a made-up account path in tool output
    for m in support.map_cell(SYNTH_LABEL, support.synthetic_cell(output=account), sem=False, prov=False):
        cited |= _cited(m)
    from agentprov.adapters.semantics_profiles import load_semantics_profile

    cited.add(str(load_semantics_profile("credleak.tools", 2).taint_policy.rule))
    citable = {rid for rid, rule in catalogue().rules.items() if rule.citable}
    assert citable - cited == set(), sorted(citable - cited)


def test_the_mapper_source_cites_only_declared_rules():
    source = "".join((SRC / name).read_text(encoding="utf-8") for name in ("mapper.py", "redact.py", "semantics/__init__.py"))
    literals = set(re.findall(r'"(credleak\.[a-z_.]+@[0-9]+)"', source))
    assert literals <= set(catalogue().rules) and literals
    codes = {c.removeprefix("credleak.") for c in re.findall(r'"(credleak\.[a-z_]+)"', source)} & ISSUE_CODES
    assert codes == ISSUE_CODES  # every declared issue code is raised somewhere in the mapper
