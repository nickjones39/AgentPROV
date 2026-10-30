"""The ``autogen`` rule catalogue (docs/architecture D.19.9; D.5.2; DECISIONS D-303): self-test, citation policy and
coverage both ways."""

from __future__ import annotations

import ast
import re
import tomllib
from importlib import resources

import autogen_support as support

from agentprov.adapters.autogen.citation import INDEPENDENT
from agentprov.aer.rules import RULE_ID_RE, load_catalogue, parse_catalogue

PACKAGE = "agentprov.adapters.autogen"
SRC = support.REPO / "src" / "agentprov" / "adapters" / "autogen"
AUTOGEN_COMMIT = "83afbf5857aac683340d4c692194e548b1e8edda"
ISSUE_CODES = {
    "aborted_attempt_events", "arguments_not_json", "block_effect_in_request_log", "block_subject_not_recorded",
    "guard_text_unjoined", "passage_not_in_document", "probe_join_missing", "response_unmatched",
    "task_template_mismatch", "tool_error_result",
}  # fmt: skip
CODE_RULES = {"autogen.call_id_link@1", "autogen.execution_result_status@1", "autogen.arguments_decoded@1"}


def catalogue():
    return load_catalogue("autogen", 1, package=PACKAGE)


def _doc() -> dict:
    return tomllib.loads((resources.files(PACKAGE) / "rules" / "autogen.rules.toml").read_text(encoding="utf-8"))


def test_the_catalogue_passes_the_self_test_and_the_citation_policy():
    cat = catalogue()
    assert (cat.namespace, cat.version, cat.format) == ("autogen", 1, "agentprov-rule-catalogue/0.1")
    assert cat.issue_codes == ISSUE_CODES and cat.subtypes == {"autogen.probe_document"}
    assert cat.types == {"autogen:memory_query", "autogen:memory_content"}
    data = (resources.files(PACKAGE) / "rules" / "autogen.rules.toml").read_bytes()
    assert parse_catalogue(data).digest == cat.digest
    for rule in _doc()["rule"]:
        rid = f"{rule['id']}@{rule['version']}"
        assert RULE_ID_RE.fullmatch(rid) and rule["statement"].endswith("."), rid
        if rid in CODE_RULES:  # D rules read from AutoGen 0.7.5 (D-303)
            assert rule["class"] == "D" and {c["commit"] for c in rule["code"]} == {AUTOGEN_COMMIT}, rid
        else:
            assert rule["code"] == [], rid
        if rule["class"] == "D" and rule["status"] == "active":
            assert rule["assumptions"] == [] and rule["evidence"], rid
            assert rid in CODE_RULES or rid in INDEPENDENT or rule["tests"][0].endswith("test_every_sem_rule_is_cited"), rid
        if rule["id"].endswith("_unverified"):
            assert rule["class"] == "I", rid


def test_every_twin_restates_its_d_rule():
    rules = {f"{r['id']}@{r['version']}": r for r in _doc()["rule"]}
    for rid in CODE_RULES:
        name, _, version = rid.partition("@")
        twin = rules[f"{name}_unverified@{version}"]
        assert twin["class"] == "I" and twin["statement"].endswith(rules[rid]["statement"]), rid
        assert twin["premises"] == rules[rid]["premises"] and twin["code"] == []
    assert {r for r in rules if r.endswith("_unverified@1") and r.replace("_unverified", "") in rules} == \
        {r.replace("@1", "_unverified@1") for r in CODE_RULES}


def test_every_tests_node_id_of_the_catalogue_exists():
    for rule in _doc()["rule"]:
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
    if m.sem is not None:
        out.update(r.split("#", 1)[0] for a in m.sem.annotations for r in a["rule"])
    return out


def test_every_emitted_rule_and_issue_is_declared(tool_arm):
    cat = catalogue()
    for rid, m in tool_arm.items():
        assert {r for r in _cited(m) if r.startswith("autogen.")} <= set(cat.rules), rid
        for issue in m.issues:
            if issue["code"].startswith("autogen."):
                assert cat.declares_issue_code(issue["code"]), (rid, issue["code"])


def test_every_declared_rule_is_exercised(tool_arm, staged):
    """Every citable rule is cited by the fixture arm or by one staged run of each kind; the twins are cited only when
    the AutoGen code is not verified, which the shipped profile never is (D-303)."""
    from agentprov.adapters.autogen.semantics.tools import CITED_RULES

    cited: set[str] = set()
    for m in tool_arm.values():
        cited |= _cited(m)
    picks = [("phase2/runs.jsonl", lambda v: v["run_id"] == "p2_c03_matched_agent"),
             ("phase2/runs.jsonl", lambda v: v["entry"] == "memory"),
             ("phase10/runs.jsonl", lambda v: v["entry"] == "user" and v["condition"] == "observe"),
             ("phase4/runs.jsonl", lambda v: v["run_id"].endswith("_user")),
             ("phase3/runs.jsonl", lambda v: v["probe_id"].endswith("_attack")),
             ("phase13/runs.jsonl", lambda v: True)]
    for tail, pick in picks:
        for unit, aux in support.units(support.ROOT + "results/" + tail, staged):
            if pick(unit.primary.value):
                cited |= _cited(support.map_unit_of(unit, aux, sem=True))
                break
    cited |= set(CITED_RULES)
    twins = {r.replace("@1", "_unverified@1") for r in CODE_RULES}
    citable = {rid for rid, rule in catalogue().rules.items() if rule.citable}
    assert citable - cited - twins == set(), sorted(citable - cited - twins)


def test_reserved_rules_are_never_cited(tool_arm):
    rules = catalogue().rules
    reserved = {rid for rid, rule in rules.items() if rule.status == "reserved"}
    assert reserved == {"autogen.non_run_rows@1", "autogen.errored_runs_set_aside@1"}
    for rid, m in tool_arm.items():
        assert not _cited(m) & reserved, rid


def test_the_mapper_source_cites_only_declared_rules():
    source = "".join((SRC / f).read_text(encoding="utf-8") for f in ("mapper.py", "events.py", "semantics/tools.py"))
    literals = set(re.findall(r'"(autogen\.[a-z_.]+@[0-9]+)"', source))
    assert literals and literals <= set(catalogue().rules)
    codes = {c.removeprefix("autogen.") for c in re.findall(r'"(autogen\.[a-z_]+)"', source)} & ISSUE_CODES
    assert codes == ISSUE_CODES  # every declared issue code is raised somewhere in the mapper


def test_profile_quirks_name_catalogue_rules():
    from agentprov.adapters.profiles import load_profile

    family = load_profile(support.PROFILE).family_table()
    for quirk in family["quirk"]:
        assert all(r in catalogue().rules for r in quirk["rules"]), quirk["id"]
