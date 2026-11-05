"""Findings AU-RA-2 and AU-RA-3 (2026-11-05; 0.2.0 change batch D-1063, regen-batch row 179): an active class-D rule
of a governed catalogue that no mapper can cite at D (no code entry, no ``_unverified`` twin) is reserved:
``agentdojo.first_user_msg_is_task_prompt@1`` (catalogue ``agentdojo`` 3) and ``agentdyn.variant_by_keyset@1``
(catalogue ``agentdyn`` 3). The archived version 2, which the sealed corpora record, keeps both active."""

from __future__ import annotations

import pytest

from agentprov.adapters.agentdojo import citation
from agentprov.adapters.code_verification import TWIN_SUFFIX, code_commits
from agentprov.aer.rules import load_catalogue

#: Class-D rules the family cites as given, never through the policy: AgentPROV's own transformations (the D-378
#: surrogate pass, the D-476 redaction), an issue rule of a log that observed no execution (no record cites it), and a
#: quirk's declared rule cited only by the undeclared-quirk issue.
AS_GIVEN = frozenset({"agentdojo.lone_surrogate_replaced@1", "rescont.value_redacted@1", "agentdojo.no_execution_observed@1",
                      "agentdojo.placeholder_args_ground_truth_only@1"})


@pytest.mark.parametrize("namespace", ["agentdojo", "agentdyn", "rescont"])
def test_every_active_d_rule_can_be_cited_under_the_policy(namespace: str):
    """An active class-D rule that is not independent has a code entry or a declared _unverified twin, the condition
    Citations needs (D.5.4); a rule no mapper can cite so is reserved."""
    catalogue = load_catalogue(namespace)
    for rid, entry in catalogue.rules.items():
        if (entry.status != "active" or entry.cls != "D" or rid in citation.INDEPENDENT or rid in AS_GIVEN
                or TWIN_SUFFIX in rid):
            continue
        name, _, version = rid.partition("@")
        twin = catalogue.get(f"{name}{TWIN_SUFFIX}@{version}")
        assert code_commits(namespace).get(rid) or (twin is not None and twin.cls == "I" and twin.citable), rid


def test_the_rules_no_mapper_cites_are_reserved():
    assert load_catalogue("agentdojo").get("agentdojo.first_user_msg_is_task_prompt@1").status == "reserved"
    assert load_catalogue("agentdyn").get("agentdyn.variant_by_keyset@1").status == "reserved"
    # the archived version 2, which the sealed corpora record, keeps them active and unchanged
    assert load_catalogue("agentdojo", 2).get("agentdojo.first_user_msg_is_task_prompt@1").status == "active"
    assert load_catalogue("agentdyn", 2).get("agentdyn.variant_by_keyset@1").status == "active"
