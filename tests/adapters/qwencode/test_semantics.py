"""The semantics profile ``qwencode.tools@2`` (docs/architecture D.24.7; C.14): labels, outcome, taint policy."""

from __future__ import annotations

import pytest

from agentprov.adapters.qwencode.semantics.tools import CITED_RULES, ProfileDataError, parse_tables
from agentprov.adapters.semantics_profiles import load_semantics_profile


def _integrity(m, target):
    return [a["value"] for a in m.annotations("integrity") if a["target"] == target]


def test_tool_roles_and_integrity(mapped):
    profile = load_semantics_profile("qwencode.tools", 2)
    for crit, m in mapped.items():
        for te in m.of("tool_execution"):
            (role,) = [a for a in m.annotations("role") if a["target"] == te["id"]]
            assert role["value"] == list(profile.tool_label(te["name"])[0]) and role["ev"] == "I", crit
        for msg in m.of("message"):
            for k, part in enumerate(msg["parts"]):
                pid = f"{msg['id']}#{k}"
                if part["t"] == "tool_result":
                    te = m.get(msg["generated_by"]) if "generated_by" in msg else None
                    assert _integrity(m, pid) == [profile.tool_label(te["name"] if te else None)[1]], (crit, pid)
                elif msg["actor"] == "agent":
                    assert _integrity(m, pid) == ["trusted"], (crit, pid)
        kinds = {f["kind"]: f["id"] for f in m.of("fixture")}
        assert _integrity(m, kinds["task_prompt"]) == ["untrusted"] and _integrity(m, kinds["other"]) == ["trusted"]
    assert profile.tool_label("run_shell_command")[:2] == (("execute_sink",), "untrusted")
    assert profile.tool_label("edit")[:2] == (("write_sink",), "unknown")


def test_unknown_tool_fails_closed():
    profile = load_semantics_profile("qwencode.tools", 2)
    assert profile.tool_label("not_a_tool") == (("unknown",), "unknown", ("qwencode.unknown_tool@1",))


def test_outcome_reads_the_score(mapped):
    seen = set()
    for crit, m in mapped.items():
        (j,) = m.of("judgement")
        (a,) = m.annotations("outcome")
        assert a["target"] == j["id"] and a["ev"] == "I", crit
        if j["value"] in (0, 3):
            assert a["value"] == {"claim": "attack_succeeded", "holds": j["value"] == 3}
        else:
            assert a["value"] == {"claim": "qwencode.non_informative", "holds": True}
        seen.add(j["value"])
    assert {0, 1, 3} <= seen


def test_profile_builds_and_declares_its_taint_policy(mapped):
    profile = load_semantics_profile("qwencode.tools", 2)
    assert profile.taint_policy is not None and profile.taint_policy.rule == "qwencode.taint_sink_untrusted@1"
    cited = {r.split("#", 1)[0] for m in mapped.values() for a in m.sem.annotations for r in a["rule"]}
    assert set(CITED_RULES) - cited - {profile.taint_policy.rule, "qwencode.unknown_tool@1"} == set()
    with pytest.raises(ProfileDataError):
        parse_tables({"profile.toml": b"", "tools.toml": b'[[tool]]\nname = "x"\nroles = ["execute_sink"]\nintegrity = "trusted"\nevidence = ["observed"]\nreason = "r"\n'})


def test_only_listed_scores_are_read():
    """NF-21 (regen item 127): ``qwencode.score_meaning@1`` covers 3, 0 and 1 only. The profile lists
    ``non_informative = [1]`` (``parse_tables`` requires it); any other integer score gets no outcome annotation."""
    import json

    import qwencode_support as support

    from agentprov.adapters.qwencode.dialect import parse_label

    f = parse_label(support.by_criterion("python"))
    assert f is not None
    member = f"results/Qwen/{f.model}/{f.target}/{f.language}/conversation_log/index{f.scenario}.json"
    entries = json.loads(support.tree()[1][member])
    for value, expected in ((2, None), (5, None), (-1, None), (1, {"claim": "qwencode.non_informative", "holds": True}),
                            (3, {"claim": "attack_succeeded", "holds": True}), (0, {"claim": "attack_succeeded", "holds": False})):
        new = [dict(e, score=value) if e["index"] == f.case_key else e for e in entries]
        m = support.modified("python", supp={member: json.dumps(new).encode()}, sem=True)
        assert [a["value"] for a in m.annotations("outcome")] == ([] if expected is None else [expected]), value
    files = {"profile.toml": (support.REPO / "src/agentprov/adapters/qwencode/semantics/qwencode.tools-2/profile.toml").read_bytes(),
             "tools.toml": (support.REPO / "src/agentprov/adapters/qwencode/semantics/qwencode.tools-2/tools.toml").read_bytes()}
    assert parse_tables(files).outcomes["non_informative"] == [1]
    without = files["profile.toml"].replace(b"non_informative = [1]\n", b"")
    assert without != files["profile.toml"]
    with pytest.raises(ProfileDataError):
        parse_tables({**files, "profile.toml": without})
