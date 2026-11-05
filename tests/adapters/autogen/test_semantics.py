"""The semantics profile ``autogen.tools`` (docs/architecture D.19.8; C.14; DECISIONS D-306): ``@2`` (D-1063) is ``@1``'s
tables on catalogue autogen 2."""

from __future__ import annotations

from collections import Counter

from agentprov.adapters.autogen.semantics.tools import CITED_RULES, NOT_INLINED_RULES, NS
from agentprov.adapters.semantics_profiles import load_semantics_profile
from agentprov.aer.rules import load_catalogue


def test_the_profile_loads_with_its_table_and_policy():
    p = load_semantics_profile("autogen.tools", 2)
    assert (p.id, p.version, dict(p.rules)) == ("autogen.tools", 2, {"autogen": 2}) and len(p.tables.tools) == 49
    one = load_semantics_profile("autogen.tools", 1)
    assert dict(one.rules) == {"autogen": 1} and one.tables == p.tables
    # AU-RC-3 (row 182): @2 also cites autogen.payload_marker_not_inlined@1, which the archived catalogue 1 lacks
    assert dict(one.classes) == {r: c for r, c in p.classes.items() if r not in NOT_INLINED_RULES}
    kinds = Counter(k for _roles, _integrity, k in p.tables.tools.values())
    assert kinds == Counter({"harness": 2, "injecagent_user": 17, "injecagent_attacker": 30})
    assert all(i != "trusted" for _r, i, _k in p.tables.tools.values())
    assert p.tool_label("no_such_tool") == (("unknown",), "unknown", ("autogen.unknown_tool@1",))
    assert set(p.ns) == set(NS) == {"autogen.canary_present", "autogen.attacker_tool_called", "autogen.keyword_stop"}


def test_every_sem_rule_is_cited():
    rules = load_catalogue("autogen", 2).rules
    for ref in (*CITED_RULES, *NOT_INLINED_RULES):
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


def test_a_result_not_inlined_has_gap_markers():
    """AU-RC-3 (D-1063, regen-batch row 182): a tool result over 1 MiB is a digest object in the AER
    (``autogen.content_not_inlined@1``). ``@1`` yielded no marker for it and counted every payload as absent for its
    integrity; from ``@2`` each payload fixture is marked ``gap`` on it under ``autogen.payload_marker_not_inlined@1``,
    the result keeps its tool's label and no author is claimed."""
    import importlib.util
    from pathlib import Path

    import autogen_support as support

    # by path: every wave-2 family has a test_uc39_41 module, so a plain import takes whichever was loaded first
    spec = importlib.util.spec_from_file_location("autogen_test_uc39_41", Path(__file__).with_name("test_uc39_41.py"))
    assert spec is not None and spec.loader is not None
    uc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(uc)

    from agentprov.sem.engine import annotate

    members = dict(support.fixture_members())
    rows = uc._lines(members[support.TOOL_ARM][0])
    for msg in rows[0]["messages"]:
        if msg.get("type") == "ToolCallExecutionEvent":
            for c in msg["raw"]["content"]:
                c["content"] = uc.BIG
    members[support.TOOL_ARM] = (uc._dump(rows), members[support.TOOL_ARM][1])
    unit, aux = support.units(support.TOOL_ARM, members)[0]
    m = support.map_unit_of(unit, aux, sem=True, prov=True)
    (tool,) = [r for r in m.of("message") if any(p.get("t") == "tool_result" and "value" in p for p in r["parts"])]
    payloads = sorted(f["id"] for f in m.of("fixture") if f["kind"] == "injection_payload")
    mine = [a for a in m.sem.annotations if a["target"] == f"{tool['id']}#0"]
    markers = [a for a in mine if a["type"] == "injection_marker"]
    assert payloads and sorted(a["value"]["fixture"] for a in markers) == payloads
    assert all(a["value"]["status"] == "gap" and a["rule"] == ["autogen.payload_marker_not_inlined@1"] for a in markers)
    assert not [a for a in mine if a["type"] == "author"]
    old = annotate(m.doc, load_semantics_profile("autogen.tools", 1))  # @1 keeps its reading (version-gated)
    assert not [a for a in old.annotations if a["target"] == f"{tool['id']}#0" and a["type"] == "injection_marker"]
