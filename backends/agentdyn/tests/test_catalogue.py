"""D-652 catalogue of the AgentDyn backend (D-688 T2): 7 suites at v1.2.2 (the four AgentDojo suites plus shopping,
github and dailylife), 157 user and 63 injection tasks, the stock 17 attacks (5 DoS), nothing refused or needing a run
option; and the per-suite tool definitions, whose digests the design note compares with AutoDojo's copy (T5)."""

import hashlib

import pytest
import rfc8785

from support import backend

pytestmark = pytest.mark.backend_agentdyn

COUNTS = {"workspace": (40, 14), "travel": (20, 7), "banking": (16, 9), "slack": (21, 5),
          "shopping": (20, 9), "github": (20, 9), "dailylife": (20, 10)}


def test_catalogue_suites_tasks_and_attacks():
    cat = backend().catalogue()
    assert cat["backend"] == "agentdyn" and cat["benchmark_version"] == "v1.2.2"
    assert cat["benchmark_versions"] == ["v1", "v1.1", "v1.1.1", "v1.1.2", "v1.2", "v1.2.1", "v1.2.2"]
    got = {s["name"]: (len(s["user_tasks"]), len(s["injection_tasks"])) for s in cat["suites"]}
    assert got == COUNTS
    assert sum(u for u, _ in got.values()) == 157 and sum(i for _, i in got.values()) == 63
    attacks = cat["attacks"]
    assert len(attacks) == 17 and sum(a["dos"] for a in attacks) == 5
    assert all(a["refused"] is None and a["needs"] == [] for a in attacks)


def test_agentdyn_suites_are_registered_under_every_version_key():
    from agentdojo.task_suite.load_suites import get_suites

    for version in ("v1", "v1.1", "v1.1.1", "v1.1.2", "v1.2", "v1.2.1", "v1.2.2"):
        suites = get_suites(version)
        assert {"shopping", "github", "dailylife"} <= set(suites)
        assert suites["shopping"] is get_suites("v1.2.2")["shopping"]


def tool_definition_digests() -> dict[str, str]:
    """JCS sha256 of ``[{name, description, parameters}]`` per AgentDyn suite, as ``identity.tool_definitions``."""
    from agentprov_backend._jsonval import encode_value
    from agentprov_backend.identity import tool_definitions

    defs = tool_definitions("v1.2.2")
    return {s: hashlib.sha256(rfc8785.dumps(encode_value(defs[s]))).hexdigest()
            for s in ("shopping", "github", "dailylife")}


#: Measured 2026-10-22 with this function in agentdyn-5353cf76 and in autodojo-aa458794: equal (design T5, F-3).
AUTODOJO_TOOL_DIGESTS = {
    "shopping": "8e03e0b07e49f242c0cdac0968e69fcd8eb42ba95f05478b40a80cb1ffc6f6b2",
    "github": "acf1c2527e15070d1dd542ea6e886c1024a1dcb5cb26ee027ceca472734f8f99",
    "dailylife": "64a41c735db0fa6f121294f91bb28b1ffec47c9753ae358fe51620204d412c59",
}


def test_agentdyn_tool_definitions_equal_autodojos_copy():
    assert tool_definition_digests() == AUTODOJO_TOOL_DIGESTS


def test_shopping_ground_truths_are_agentdyns_stubs():
    """Design F-2: at the pin every shopping injection task's ground truth is the ``send_money(recipient="")`` stub
    (AutoDojo replaced them with the attacker actions), so ``tool_knowledge`` payloads differ between the backends."""
    from agentdojo.task_suite.load_suites import get_suite

    suite = get_suite("v1.2.2", "shopping")
    env = suite.load_and_inject_default_environment({})
    functions = {k: [c.function for c in t.ground_truth(env)] for k, t in suite.injection_tasks.items()}
    assert len(functions) == 9 and all(f == ["send_money"] for f in functions.values())
