"""The semantics profile ``agentops.tools`` at the version the profile selects (docs/architecture D.18.8; C.14): labels,
markers, outcomes, validation."""

from __future__ import annotations

import json

import agentops_support as support

from agentprov.adapters.agentops.semantics.tools import CITED_RULES, ProfileDataError, parse_tables
from agentprov.adapters.semantics_profiles import load_semantics_profile


def test_every_sem_rule_is_cited(mapped):
    """Each rule the profile declares is cited by some annotation of the fixtures, except the taint policy's (stated as
    apv:policy by the PROV engine) and the normaliser (named in marker values)."""
    cited = {r.split("#", 1)[0] for m in mapped.values() for a in m.sem.annotations for r in a["rule"]}
    normalisers = {a["value"]["normaliser"] for m in mapped.values() for a in m.annotations("injection_marker")}
    assert normalisers == {"agentops.verbatim_match@1"}
    profile = load_semantics_profile("agentops.tools", support.SEM_VERSION)
    assert profile.taint_policy is not None and profile.taint_policy.rule == "agentops.taint_sink_untrusted@1"
    assert set(CITED_RULES) - cited - normalisers - {profile.taint_policy.rule} == set()


def test_markers_locate_each_payload_in_its_result(mapped):
    for crit in ("openrouter_payload", "anthropic_payload", "payloads_failure_multicall", "unlisted_tool_name"):
        m = mapped[crit]
        fixtures = {f["id"]: f["content"] for f in m.of("fixture") if f["kind"] == "injection_payload"}
        present = [a for a in m.annotations("injection_marker") if a["value"]["status"] == "present"]
        assert {a["value"]["fixture"] for a in present} == set(fixtures), crit
        for a in present:
            mid, k = a["target"].split("#")
            text = m.get(mid)["parts"][int(k)]["text"]
            start, end = a["span"]
            assert a["at"] == "/text" and text[start:end] == fixtures[a["value"]["fixture"]] and a["ev"] == "D"
            integrity = [x for x in m.annotations("integrity") if x["target"] == a["target"]]
            assert [x["value"] for x in integrity] == ["untrusted"]
            assert [x["value"] for x in m.annotations("author") if x["target"] == a["target"]] == [{"actor": "att"}]
        assert not [a for a in m.annotations("injection_marker") if a["value"]["status"] == "gap"]


def test_integrity_and_roles(mapped):
    m = mapped["noisy_safety_failure"]
    (dc,) = m.of("decision")
    (msg,) = [r for r in m.of("message") if r.get("generated_by") == dc["id"]]
    assert [a["value"] for a in m.annotations("integrity") if a["target"] == f"{msg['id']}#0"] == ["unknown"]
    prompt = next(f for f in m.of("fixture") if f["kind"] == "task_prompt")
    assert [a["value"] for a in m.annotations("integrity") if a["target"] == prompt["id"]] == ["unknown"]  # safety suite
    m = mapped["task_with_context"]
    prompt = next(f for f in m.of("fixture") if f["kind"] == "task_prompt")
    assert [a["value"] for a in m.annotations("integrity") if a["target"] == prompt["id"]] == ["trusted"]
    for crit, m in mapped.items():
        for te in m.of("tool_execution"):
            (role,) = [a for a in m.annotations("role") if a["target"] == te["id"]]
            assert role["value"] != [] and role["rule"] in (["agentops.tool_table@1"], ["agentops.unknown_tool@1"]), crit
    unknown = [a for a in mapped["unlisted_tool_name"].annotations("role") if a["value"] == ["unknown"]]
    assert unknown and all(a["rule"] == ["agentops.unknown_tool@1"] for a in unknown)


def test_outcomes(mapped):
    for crit, m in mapped.items():
        outcomes = {m.get(a["target"])["name"]: a["value"] for a in m.annotations("outcome")}
        raw = json.loads(support.run_bytes(support.F[crit]))
        assert outcomes["completion"] == {"claim": "user_task_solved", "score": raw["scores"]["completion"],
                                          "scale": "agentops.completion_0_1"}
        default = [j for j in m.of("judgement") if j["origin"] == "harness_default"]
        assert not {a["target"] for a in m.annotations("outcome")} & {j["id"] for j in default}  # SEM-V08
        if raw["scores"]["safety"]["injections_present"]:
            assert outcomes["safety"]["claim"] == "agentops.injection_resistance"
        else:
            assert "safety" not in outcomes


def test_profile_data_is_closed():
    profile = load_semantics_profile("agentops.tools", support.SEM_VERSION)
    files = {"profile.toml": b"", "tools.toml": b"", "extra.toml": b""}
    try:
        parse_tables(files)
    except ProfileDataError as exc:
        assert "unexpected" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("an extra data file must be refused")
    assert set(profile.tables.tools) == {"calculate", "get_current_time", "get_stock_price", "get_weather", "query_database",
                                         "read_file", "run_python", "send_email", "web_search", "write_file"}
    assert all(integrity != "trusted" for _roles, integrity in profile.tables.tools.values())
