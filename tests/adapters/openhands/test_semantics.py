"""The semantics profile ``openhands.tools`` at the version the profiles select (docs/architecture D.17.10): data checks,
tool labels, readings."""

from __future__ import annotations

import json

import openhands_support as support

from agentprov.adapters.openhands.semantics.tools import CITED_RULES
from agentprov.adapters.semantics_profiles import load_semantics_profile
from agentprov.sem.types import ROLE_VALUES

#: Every tool function name the phase-10g census found (tcm_function), finish excepted (a control call, D-175).
CENSUS_TOOLS = {"execute_bash", "execute_ipython_cell", "str_replace_editor", "browser", "web_read", "chat", "think",
                "task_tracker", "fetch"}


def _profile():
    return load_semantics_profile("openhands.tools", support.SEM_VERSION)


def test_the_profile_loads_with_its_rules_and_taint_policy():
    profile = _profile()
    assert (profile.id, profile.version, dict(profile.rules)) == ("openhands.tools", 2, {"openhands": 2})
    assert profile.taint_policy is not None and profile.taint_policy.rule == "openhands.taint_sink_untrusted@1"
    assert set(profile.classes) == set(CITED_RULES)
    assert load_semantics_profile("openhands.tools", support.SEM_VERSION).sha256 == profile.sha256


def test_every_census_tool_is_labelled_and_unknown_tools_fail_closed():
    profile = _profile()
    for name in CENSUS_TOOLS:
        roles, integrity, rules = profile.tool_label(name)
        assert roles and set(roles) <= set(ROLE_VALUES) and integrity in ("untrusted", "unknown"), name
        assert rules == ("openhands.tool_table@1",)
    assert profile.tool_label("no_such_tool") == (("unknown",), "unknown", ("openhands.unknown_tool@1",))
    assert profile.tool_label(None)[2] == ("openhands.unknown_tool@1",)


def test_the_census_tool_list_matches_the_report():
    census = json.loads((support.REPO / "docs/reports/phase10g/openagentsafety.census.json").read_text(encoding="utf-8"))
    rc = json.loads((support.REPO / "docs/reports/phase10g/redcode-openhands.census.json").read_text(encoding="utf-8"))
    names = {k.split(":")[2] for c in (census, rc) for k in c["totals"]["tcm_function"] if k.startswith("action:")}
    assert names - {"finish"} == CENSUS_TOOLS


def test_annotations_target_the_records_they_read(mapped):
    for fid, m in mapped.items():
        ids = {r["id"] for r in m.records}
        for a in m.sem.annotations:
            assert a["target"].split("#", 1)[0] in ids | {"exec", "run"}, fid
            assert all(r.split("#", 1)[0] in CITED_RULES for r in a["rule"]), fid


def test_taint_assessments_reach_the_assessment_bundle(mapped):
    m = mapped["R2"]
    bundles = json.loads(m.prov.prov_json)["bundle"]
    assess = [name for name in bundles if ".assess." in name]
    assert assess
    text = json.dumps({k: bundles[k] for k in assess})
    assert "openhands.taint_sink_untrusted@1" in text
