"""The generic denial hook ``agentdojo.defence_denial_message`` (routing R1; D-113; docs/architecture D.6.6).

Its matchers parse from the profile's ``params.denials`` and refuse malformed params (a packaging defect); a text matches
by exact text, prefix or a whole-text regular expression; a matcher names exactly one defence actor of the file or none.
The per-source behaviour (a denial becomes a decision, other errors stay executions) is tested on a synthetic log of each
source in ``test_phase10d_sources.py``.
"""

from __future__ import annotations

from typing import Any

import pytest

from agentprov.adapters.agentdojo.hooks.defence_denial import QUIRK_ID, RULE, matchers
from agentprov.adapters.agentdojo.quirks import hooks
from agentprov.adapters.profiles import load_profile
from agentprov.adapters.registry import REGISTRY
from agentprov.aer.rules import load_catalogue
from agentprov.errors import ProfileError


def test_the_hook_is_registered_and_its_rule_is_a_class_i_rule_of_the_catalogue():
    hook = hooks()[QUIRK_ID]
    assert hook.rules == (RULE,) and hook.tool_message is not None and set(hook.census) == {"denials"}
    entry = load_catalogue("agentdojo").get(RULE)
    assert entry is not None and entry.citable and entry.cls == "I"


def test_matchers_parse_and_match():
    (exact, prefix, regex) = matchers({"denials": [
        {"defences": ["interbolt-*"], "error_equals": ["Blocked by security policy."]},
        {"defences": ["gate-*"], "error_prefix": ["BLOCKED by security policy"], "content_equals_error": True},
        {"defences": ["progent"], "error_regex": r"ValidationError: The tool '\w+' is not allowed\.\..*"},
    ]})
    assert exact.text_matches("Blocked by security policy.") and not exact.text_matches("Blocked by security policy. x")
    assert prefix.text_matches("BLOCKED by security policy: egress") and prefix.content_equals_error
    assert not prefix.text_matches("ValueError: BLOCKED by security policy")
    assert regex.text_matches("ValidationError: The tool 'send_money' is not allowed.. Please\ncontinue")
    assert not regex.text_matches("Error: ValidationError: The tool 'send_money' is not allowed..")  # whole text
    assert not exact.content_equals_error


def test_a_matcher_names_exactly_one_defence_of_the_file():
    (m,) = matchers({"denials": [{"defences": ["gate-*", "munim*"], "error_prefix": ["x"]}]})
    assert m.defence(["gate-all"]) == "gate-all"
    assert m.defence(["none", "spotlighting_with_delimiting"]) is None  # not defended by it
    assert m.defence(["gate-all", "munim"]) is None  # ambiguous: left to the generic rows
    assert m.defence([]) is None


@pytest.mark.parametrize("params", [
    {},
    {"denials": []},
    {"denials": [{"error_prefix": ["x"]}]},
    {"denials": [{"defences": ["a"]}]},
    {"denials": [{"defences": "a", "error_prefix": ["x"]}]},
    {"denials": [{"defences": ["a"], "error_prefix": [""]}]},
    {"denials": [{"defences": ["a"], "error_regex": "("}]},
    {"denials": [{"defences": ["a"], "error_prefix": ["x"], "content_equals_error": "yes"}]},
    {"denials": [{"defences": ["a"], "error_prefix": ["x"], "reason": "x"}]},
])
def test_malformed_params_are_refused(params: dict[str, Any]):
    with pytest.raises(ProfileError):
        matchers(params)


def test_every_shipped_profile_declaring_the_quirk_parses_and_cites_the_rule():
    declared = 0
    for registration in REGISTRY:
        for part in registration.capabilities:
            if part.profile is None or registration.family != "agentdojo":
                continue
            data = load_profile(part.profile).data
            for quirk in data.get("family", {}).get("agentdojo", {}).get("quirk", ()):
                if quirk["id"] == QUIRK_ID:
                    declared += 1
                    assert tuple(quirk["rules"]) == (RULE,) and matchers(quirk["params"])
                    # one census per part of the profile, keyed by the part names it declares (and this registry part)
                    assert set(quirk["observed"]) == set(data["profile"]["parts"]) and part.part in quirk["observed"]
                    assert all(set(v) == {"denials"} for v in quirk["observed"].values())
    assert declared == 10  # seven phase-10d profiles, and kavach-agentdojo's three parts (phase 10j, D-253)
