"""The semantics profile ``geminicli.tools@1`` (docs/architecture D.23.8; C.14): labels, outcome, taint policy."""

from __future__ import annotations

import pytest

from agentprov.adapters.geminicli.semantics.tools import CITED_RULES, ProfileDataError, parse_tables
from agentprov.adapters.semantics_profiles import load_semantics_profile


def _integrity(m, target):
    return [a["value"] for a in m.annotations("integrity") if a["target"] == target]


def test_tool_roles_and_integrity(mapped):
    profile = load_semantics_profile("geminicli.tools", 1)
    for crit, m in mapped.items():
        for te in m.of("tool_execution"):
            (role,) = [a for a in m.annotations("role") if a["target"] == te["id"]]
            assert role["value"] == list(profile.tool_label(te["name"])[0]) and role["ev"] == "I", crit
        for msg in m.of("message"):
            for k, part in enumerate(msg["parts"]):
                pid = f"{msg['id']}#{k}"
                if part["t"] == "tool_result":
                    te = m.get(msg["generated_by"]) if "generated_by" in msg else None
                    want = profile.tool_label(te["name"] if te else None)[1]
                    assert _integrity(m, pid) == [want], (crit, pid)
                elif msg["actor"] in ("agent", "user"):
                    assert _integrity(m, pid) == ["trusted"], (crit, pid)
        (fx,) = m.of("fixture")
        assert _integrity(m, fx["id"]) == ["unknown"]
    assert profile.tool_label("run_shell_command")[:2] == (("execute_sink",), "untrusted")
    assert profile.tool_label("replace")[:2] == (("write_sink",), "unknown")


def test_unknown_tool_fails_closed():
    profile = load_semantics_profile("geminicli.tools", 1)
    assert profile.tool_label("not_a_tool") == (("unknown",), "unknown", ("geminicli.unknown_tool@1",))
    assert profile.tool_label(None)[0] == ("unknown",)


def test_outcome_reads_elicited(mapped):
    for crit, m in mapped.items():
        (elicited,) = [j for j in m.of("judgement") if j["name"] == "elicited"]
        outcomes = [a for a in m.annotations("outcome")]
        assert [a["target"] for a in outcomes] == [elicited["id"]], crit  # n_misaligned gets no reading
        assert outcomes[0]["value"] == {"claim": "geminicli.misalignment_elicited", "holds": elicited["value"]}
        assert outcomes[0]["ev"] == "I"
    assert {a["value"]["holds"] for m in mapped.values() for a in m.annotations("outcome")} == {True, False}


def test_profile_builds_and_declares_its_taint_policy(mapped):
    profile = load_semantics_profile("geminicli.tools", 1)
    assert profile.taint_policy is not None and profile.taint_policy.rule == "geminicli.taint_sink_untrusted@1"
    cited = {r.split("#", 1)[0] for m in mapped.values() for a in m.sem.annotations for r in a["rule"]}
    assert set(CITED_RULES) - cited - {profile.taint_policy.rule, "geminicli.unknown_tool@1"} == set()
    with pytest.raises(ProfileDataError):
        parse_tables({"profile.toml": b"", "tools.toml": b'[[tool]]\nname = "x"\nroles = ["execute_sink"]\nintegrity = "trusted"\nevidence = ["observed"]\nreason = "r"\n'})
