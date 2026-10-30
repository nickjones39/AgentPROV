"""The ``openhands`` rule catalogue (docs/architecture D.17.9; D.5.2): self-test, citation policy, coverage both ways."""

from __future__ import annotations

import ast
import json
import re
import tomllib
from importlib import resources

import openhands_support as support

from agentprov.adapters.openhands.citation import INDEPENDENT
from agentprov.adapters.openhands.semantics.tools import CITED_RULES
from agentprov.aer.rules import RULE_ID_RE, load_catalogue, parse_catalogue

PACKAGE = "agentprov.adapters.openhands"
COMMITS = {"5a13eacf8177c8dab2600f9011d88f18a7db0ad8", "a77b05509ec010d44d1e274b0f8daace0f89ea8f"}
ISSUE_CODES = {
    "filtered_events", "content_not_inlined", "not_executed_notice", "harness_error", "call_not_in_response",
    "unmapped_event", "task_text_not_seen", "join_after_rewrite", "join_unverified", "summary_entry_missing",
    "state_missing", "eval_missing", "served_model_varies", "unexpected_cause_target", "lone_observation",
    "value_redacted",
}  # fmt: skip
#: Detectors of the artefact catalogue that sealing or the release scan apply, never the mapper (D-602, D-606).
RESERVED = {"openhands.deposit_secret_withheld@1", "openhands.fixture_secret_shape@1"}


def _doc():
    return tomllib.loads((resources.files(PACKAGE) / "rules" / "openhands.rules.toml").read_text(encoding="utf-8"))


def _raw():
    return {f"{r['id']}@{r['version']}": r for r in _doc()["rule"]}


def test_the_catalogue_passes_the_self_test_and_the_citation_policy():
    cat = load_catalogue("openhands", 2, package=PACKAGE)  # D-31 bump with D-606; v1 is archived
    assert (cat.namespace, cat.version, cat.format) == ("openhands", 2, "agentprov-rule-catalogue/0.1")
    assert cat.issue_codes == ISSUE_CODES
    data = (resources.files(PACKAGE) / "rules" / "openhands.rules.toml").read_bytes()
    assert parse_catalogue(data).digest == cat.digest
    for rid, rule in _raw().items():
        assert RULE_ID_RE.fullmatch(rid) and rule["statement"].endswith("."), rid
        codes = rule.get("code", [])
        if rule["class"] == "D":
            assert rule["assumptions"] == [] and rule["evidence"], rid
            # a D rule either cites the OpenHands code it was read from (both verified commits) or is independent
            if codes:
                assert {c["commit"] for c in codes} == COMMITS and rid not in INDEPENDENT, rid
            elif rule["status"] == "reserved":
                assert rid in RESERVED, rid
            else:
                assert rid in INDEPENDENT, rid
        else:
            assert codes == [], rid
            for v in rule.get("verification", []):
                assert v["status"] == "asserted", rid


def test_every_twin_restates_its_d_rule():
    raw = _raw()
    with_code = [rid for rid, r in raw.items() if r["class"] == "D" and r.get("code")]
    assert with_code
    for rid in with_code:
        name, _, version = rid.partition("@")
        twin = raw[f"{name}_unverified@{version}"]
        assert twin["class"] == "I" and twin["status"] == "active" and not twin.get("code"), rid
        assert twin["premises"] == raw[rid]["premises"] and twin["statement"].endswith(raw[rid]["statement"]), rid
        assert "D.5.4" in twin["evidence"]


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
    if m.sem is not None:
        for a in m.sem.annotations:
            out.update(r.split("#", 1)[0] for r in a["rule"])
    return out


def _variants() -> list[support.Mapped]:
    """Runtime-derived inputs for rules no committed fixture exercises: a state repr whose agent_state is error, and a
    tool output over 1 MiB."""
    source, label = support.F["O1"]
    files = dict(support.tree(source))
    state_label = label.replace("/traj_", "/state_")
    state = json.loads(files[state_label])
    files[state_label] = json.dumps(re.sub(r"agent_state=<AgentState\.[A-Z_]+: '[a-z_]+'>",
                                           "agent_state=<AgentState.ERROR: 'error'>", state)).encode()
    out = [support.map_label(label, files, source=source)]
    rsource, rlabel = support.F["R1"]
    rfiles = support.tree(rsource)
    events = json.loads(rfiles[rlabel])
    target = next(i for i, e in enumerate(events) if e.get("observation") == "run")
    events[target]["content"] = "x" * (1 << 20 | 1)
    out.append(support.map_label(rlabel, rfiles, source=rsource, data=json.dumps(events).encode()))
    return out


def test_every_emitted_rule_and_issue_is_declared(mapped):
    cat = load_catalogue("openhands", 2, package=PACKAGE)
    for fid, m in mapped.items():
        assert {r for r in _cited(m) if r.startswith("openhands.")} <= set(cat.rules), fid
        for issue in m.issues:
            if issue["code"].startswith("openhands."):
                assert cat.declares_issue_code(issue["code"]), (fid, issue["code"])


def test_every_declared_rule_is_exercised(mapped):
    """Coverage the other way: every rule is cited by an AER, a SEM document or a seal of the fixtures and the
    runtime-derived variants, or is covered by the named test: the twins by test_mapper.py::test_without_verified_code_
    the_twins_are_cited, the taint policy and the fail-closed tool label by test_semantics.py."""
    cited: set[str] = set()
    for m in [*mapped.values(), *_variants()]:
        cited |= _cited(m)
    covered_elsewhere = {r for r in _raw() if "_unverified@" in r and r.replace("_unverified@", "@") in _raw()}
    covered_elsewhere |= {"openhands.taint_sink_untrusted@1", "openhands.unknown_tool@1"} | RESERVED
    covered_elsewhere |= {"openhands.value_redacted@1"}  # test_redact.py (no committed fixture holds an account path)
    declared = set(_raw())
    assert sorted(declared - cited - covered_elsewhere) == []
    assert set(CITED_RULES) <= declared


def test_reserved_detectors_are_never_cited(mapped):
    """D-602: the reserved detector names what sealing's decoded scan withholds; no AER, SEM or seal cites it."""
    assert {r for r, rule in _raw().items() if rule["status"] == "reserved"} == RESERVED
    for m in [*mapped.values(), *_variants()]:
        assert not _cited(m) & RESERVED
