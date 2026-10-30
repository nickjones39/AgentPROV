"""The semantics profile ``autogen.tools@1`` (docs/architecture D.19.8; C.14; DECISIONS D-306)."""

from __future__ import annotations

from collections import Counter

from agentprov.adapters.autogen.semantics.tools import CITED_RULES, NS
from agentprov.adapters.semantics_profiles import load_semantics_profile
from agentprov.aer.rules import load_catalogue


def test_the_profile_loads_with_its_table_and_policy():
    p = load_semantics_profile("autogen.tools", 1)
    assert (p.id, p.version) == ("autogen.tools", 1) and len(p.tables.tools) == 49
    kinds = Counter(k for _roles, _integrity, k in p.tables.tools.values())
    assert kinds == Counter({"harness": 2, "injecagent_user": 17, "injecagent_attacker": 30})
    assert all(i != "trusted" for _r, i, _k in p.tables.tools.values())
    assert p.tool_label("no_such_tool") == (("unknown",), "unknown", ("autogen.unknown_tool@1",))
    assert set(p.ns) == set(NS) == {"autogen.canary_present", "autogen.attacker_tool_called", "autogen.keyword_stop"}


def test_every_sem_rule_is_cited():
    rules = load_catalogue("autogen", 1).rules
    for ref in CITED_RULES:
        assert ref in rules and rules[ref].citable, ref


def test_annotations_on_the_fixture_arm(tool_arm):
    types: Counter[str] = Counter()
    for rid, m in tool_arm.items():
        for a in m.sem.annotations:
            types[a["type"]] += 1
            if a["type"] == "integrity" and a["target"].split("#", 1)[0] in {r["id"] for r in m.of("fixture")}:
                kind = m.get(a["target"])["kind"]
                assert a["value"] == ("trusted" if kind in ("task_prompt", "system_prompt") else "untrusted"), (rid, kind)
            if a["type"] == "injection_marker" and a["value"]["status"] == "present":
                assert a["at"] == "/text" and a["span"][0] < a["span"][1]
        withheld = [r for r in m.of("message") if r.get("generated_by", "").startswith("dc")]
        for msg in withheld:
            (lab,) = [a for a in m.sem.annotations if a["target"] == f"{msg['id']}#0" and a["type"] == "integrity"]
            assert lab["value"] == "unknown", rid
    assert {"integrity", "role", "injection_marker", "autogen.attacker_tool_called"} <= set(types)


def test_canary_claims_on_the_probe_phases(staged):
    import autogen_support as support

    hits = 0
    for unit, aux in support.units(support.ROOT + "results/phase2/runs.jsonl", staged):
        if not unit.primary.value["probe_id"].endswith("_attack"):
            continue
        m = support.map_unit_of(unit, aux, sem=True)
        for a in m.sem.annotations:
            if a["type"] == "autogen.canary_present":
                hits += 1
                assert a["ev"] == "D" and m.get(a["value"]["fixture"])["kind"] == "injection_payload"
        if hits >= 3:
            break
    assert hits >= 1
