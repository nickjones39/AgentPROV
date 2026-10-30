"""The ``dtap`` rule catalogue (docs/architecture D.16.11; D.5.2): self-test, citation policy and coverage both ways."""

from __future__ import annotations

import ast
import re
import tomllib
from importlib import resources
from pathlib import Path

import dtap_support as support

from agentprov.aer.rules import RULE_ID_RE, load_catalogue, parse_catalogue

PACKAGE = "agentprov.adapters.dtap"
SRC = support.REPO / "src" / "agentprov" / "adapters" / "dtap"
ISSUE_CODES = {
    "partial_trajectory", "empty_trajectory", "harness_failure", "judgement_on_failed_run", "pairing_ambiguous_batch",
    "config_join_unverified", "config_missing", "config_unparseable", "task_info_truncated", "goal_rewritten_at_eval",
    "user_step_not_logged", "final_response_differs", "source_truncation_marker", "judge_error", "judge_attempt_unresolved",
    "unjudged_attempt", "path_field_mismatch", "value_redacted",  # value_redacted: catalogue version 2 (D-607)
    "content_not_inlined",  # catalogue version 3 (D-934)
}  # fmt: skip
#: Rules the mapper and SEM cannot exercise on the fixtures: they are register-only (the reader's sniff) or are raised
#: only on inputs no fixture holds; each is covered by the named test.
REGISTER_ONLY = {"dtap.synthetic_marker@1", "dtap.lfs_pointer@1"}


def catalogue():
    return load_catalogue("dtap", 3, package=PACKAGE)  # current since D-934


def test_the_catalogue_passes_the_self_test_and_the_citation_policy():
    cat = catalogue()
    assert (cat.namespace, cat.version, cat.format) == ("dtap", 3, "agentprov-rule-catalogue/0.1")
    assert cat.issue_codes == ISSUE_CODES
    assert cat.types == {"dtap:list_mcp_tools", "dtap:harness_error", "dtap:tool_name_list", "dtap:error_text"}
    assert cat.subtypes == {"dtap.attack_goal", "dtap.attack_goal_at_eval"}
    data = (resources.files(PACKAGE) / "rules" / "dtap.rules.toml").read_bytes()
    assert parse_catalogue(data).digest == cat.digest
    doc = tomllib.loads(data.decode("utf-8"))
    for rule in doc["rule"]:
        rid = f"{rule['id']}@{rule['version']}"
        assert RULE_ID_RE.fullmatch(rid) and rule["statement"].endswith(".") and rule["code"] == [], rid
        if rule["class"] == "D":  # D rules: deterministic functions of observed fields, no assumption, census evidence
            assert rule["assumptions"] == [] and rule["evidence"], rid
        for v in rule.get("verification", []):
            assert v["status"] == "asserted", rid  # no DTap harness code is verified (D-24)


def test_every_tests_node_id_of_the_catalogue_exists():
    doc = tomllib.loads((resources.files(PACKAGE) / "rules" / "dtap.rules.toml").read_text(encoding="utf-8"))
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
    for fid, m in mapped.items():
        assert {r for r in _cited(m) if r.startswith("dtap.")} <= set(cat.rules), fid
        for issue in m.issues:
            if issue["code"].startswith("dtap."):
                assert cat.declares_issue_code(issue["code"]), (fid, issue["code"])


def test_every_declared_rule_is_exercised(mapped):
    """Coverage the other way: every rule is cited by an AER, a SEM document or a seal of the fixtures (plus the
    runtime-derived inputs of test_mapper.py and test_semantics.py), or is register-only (the reader's sniff)."""

    from agentprov.adapters.dtap.semantics.tools import CITED_RULES

    cited: set[str] = set()
    for m in mapped.values():
        cited |= _cited(m)
        cited |= {r.split("#", 1)[0] for a in m.sem.annotations for r in a["rule"]}
    partial = support.runs_files()
    label = support.F["F01"].rsplit("/", 1)[0] + "/partial_trajectory.json"
    partial[label] = partial.pop(support.F["F01"])
    cited |= _cited(support.map_label(label, runs=partial))
    cited |= _cited(support.map_steps([{"role": "user", "state": "u", "metadata": {}}, support.result("x"), support.call("a", {}), support.result("a"), support.call("b", {})],
                         framework="claudesdk"))
    cited |= _cited(support.map_steps([support.call("list_workspaces"), support.result("list_workspaces")]))
    agent_only = support.modified("F04", lambda v: v["trajectory"][-1]["metadata"].update(
        message=v["trajectory"][-1]["metadata"].get("message", "") + " " + support.payload("F04", "environment")))
    cited |= {r.split("#", 1)[0] for a in agent_only.sem.annotations for r in a["rule"]}
    cited |= set(CITED_RULES)  # the profile's rule set is checked annotation by annotation in test_semantics.py
    # the disclosure rules are exercised by test_mapper.py::test_disclosure_issues_on_derived_inputs
    disclosures = {"dtap.instruction_cut_500@1", "dtap.instruction_length_500_unverified@1", "dtap.final_response_copy@1",
                   "dtap.source_truncation_marker@1", "dtap.task_id_reformatted@1"}
    # the redaction rule (D-607) is exercised by test_redact.py: no committed fixture holds a listed account
    disclosures.add("dtap.value_redacted@1")
    # the not-inlined rule (D-934) is exercised by test_not_inlined_d934.py: no committed fixture holds a 1 MiB string
    disclosures.add("dtap.content_not_inlined@1")
    # reserved rules are artefact-catalogue detector names, never citable (test_artefacts.py checks they stay uncited)
    citable = {rid for rid, rule in catalogue().rules.items() if rule.citable}
    missing = citable - cited - REGISTER_ONLY - disclosures
    assert missing == set(), sorted(missing)


def test_the_mapper_source_cites_only_declared_rules():
    source = "".join((SRC / name).read_text(encoding="utf-8") for name in ("mapper.py", "redact.py", "semantics/tools.py"))
    literals = set(re.findall(r'"(dtap\.[a-z_.]+@[0-9]+)"', source))
    assert literals <= set(catalogue().rules) and literals
    codes = {c.removeprefix("dtap.") for c in re.findall(r'"(dtap\.[a-z_]+)"', source)} & ISSUE_CODES
    assert codes == ISSUE_CODES  # every declared issue code is raised somewhere in the mapper


def test_every_activity_artefact_type_and_subtype_is_declared(mapped):
    cat = catalogue()
    for m in mapped.values():
        assert {r["type"] for r in m.records if r["k"] in ("activity", "artefact")} <= cat.types
        assert {r["subtype"] for r in m.records if "subtype" in r} <= cat.subtypes
        assert m.header["ns"] == {"dtap": "https://w3id.org/agentprov/ns/dtap#"}


def test_profile_quirks_name_catalogue_rules():
    from agentprov.adapters.profiles import load_profile

    family = load_profile("dtap-bench").family_table()
    for quirk in family["quirk"]:
        assert all(r in catalogue().rules for r in quirk["rules"]), quirk["id"]
    assert set(family["pairing"].values()) <= set(catalogue().rules)
    assert family["matcher"]["normaliser"] in catalogue().rules
    assert Path(SRC / "rules" / "dtap.rules.toml").is_file()


def test_catalogue_version_1_is_archived_unchanged_and_version_2_only_adds_the_redaction_rule():
    """D-31 (D-607): the scratch corpora record dtap 1 at b4df2cb43941; version 2 keeps every version-1 rule as it was."""
    import hashlib

    archived = (SRC / "rules" / "archive" / "dtap.rules.v1.toml").read_bytes()
    assert hashlib.sha256(archived).hexdigest().startswith("b4df2cb43941")
    v1, v2 = load_catalogue("dtap", 1, package=PACKAGE), load_catalogue("dtap", 2, package=PACKAGE)
    assert v1.version == 1 and set(v2.rules) - set(v1.rules) == {"dtap.value_redacted@1"}
    assert all(v2.rules[rid] == rule for rid, rule in v1.rules.items())
    assert v2.issue_codes - v1.issue_codes == {"value_redacted"}
    # D-934: version 3 (current) keeps every version-2 rule and adds the not-inlined rule; v2 is archived as recorded
    archived2 = (SRC / "rules" / "archive" / "dtap.rules.v2.toml").read_bytes()
    assert hashlib.sha256(archived2).hexdigest() == load_catalogue("dtap", 2, package=PACKAGE).digest.removeprefix("sha256:")
    v3 = catalogue()
    assert v3.version == 3 and set(v3.rules) - set(v2.rules) == {"dtap.content_not_inlined@1"}
    assert all(v3.rules[rid] == rule for rid, rule in v2.rules.items())
    assert v3.issue_codes - v2.issue_codes == {"content_not_inlined"}
