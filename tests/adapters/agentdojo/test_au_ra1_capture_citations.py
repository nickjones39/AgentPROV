"""Finding AU-RA-1 (2026-11-05; 0.2.0 change batch D-1063, regen-batch row 179): the capture mapper cites through the
family's D-rule policy (D.5.4, D-24): a capture rule that reads the harness's code is D only where its code list cites
the live profile's commit, else its ``_unverified`` twin; the rules that read the capture record itself are independent.
All content is synthetic (the C.13.8 vector)."""

from __future__ import annotations

import copy
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import capture_support as cs
import pytest
from agentdojo_support import map_bytes
from test_capture_mapper import balance_cell

from agentprov.adapters.agentdojo import citation
from agentprov.adapters.agentdojo.profile import family_table
from agentprov.adapters.code_verification import TWIN_SUFFIX, code_commits, rule_class
from agentprov.adapters.profiles import load_profile
from agentprov.adapters.types import Origin
from agentprov.aer.rules import load_catalogue

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # tests/adapters: the R07b helper
from citation_check import unverified_d_citations  # noqa: E402

LIVE = ("agentdojo-live", "autodojo-live", "agentdyn-live")


@pytest.mark.parametrize("profile_id", LIVE)
def test_the_capture_mapper_cites_d_only_for_verified_code(profile_id: str):
    """The project's R07b check reports nothing on the synthetic C.13.8 session under every live profile, and every D
    citation of a governed catalogue is independent or rests on a commit the profile verifies."""
    m = cs.map_built(cs.c13_8_session(), profile_id=profile_id)
    assert m.validate().ok
    assert unverified_d_citations(m.records, m.profile) == []
    verified = {v.commit for v in family_table(m.profile).verified_code}
    for record in m.records:
        for ref in record.get("rule", ()):
            rid = str(ref).partition("#")[0]
            namespace = rid.split(".", 1)[0]
            if namespace in citation.NAMESPACES and rule_class(rid) == "D" and rid not in citation.INDEPENDENT:
                assert code_commits(namespace).get(rid, frozenset()) & verified, (record["id"], rid)


def test_the_capture_and_native_mappings_of_one_cell_cite_the_same_class():
    """The live and native mappings of one agentdojo-live cell cite user_is_simulated at the same class: its code entry is
    the June-2024 code, which the live profile does not verify, so both cite the twin."""

    def classes(records: list[dict[str, Any]]) -> set[str]:
        return {rule_class(str(r).partition("#")[0]) for rec in records for r in rec.get("rule", ())
                if str(r).startswith("agentdojo.user_is_simulated")}

    live = cs.map_built(cs.c13_8_session(), profile_id="agentdojo-live")
    raw = json.dumps(cs.native_log(copy.deepcopy(balance_cell().messages)), indent=4).encode()
    native = map_bytes(raw, "native.json", profile=load_profile("agentdojo-live"), origin=Origin.capture(cs.SESSION))
    assert classes(live.records) == classes(native.records) == {"I"}
    cited = Counter(str(r).partition("#")[0] for rec in live.records for r in rec.get("rule", ())
                    if str(r).startswith("agentdojo.user_is_simulated"))
    assert set(cited) == {"agentdojo.user_is_simulated" + TWIN_SUFFIX + "@1"}


@pytest.mark.parametrize("profile_id", LIVE)
def test_every_capture_rule_resolves_under_every_live_profile(profile_id: str):
    """``Citations(<live profile>)`` resolves every capture rule (no RuleNotDeclared): a code-reading capture rule has its
    _unverified twin, a reading of the capture record itself is independent."""
    policy = citation.citations(family_table(load_profile(profile_id)), {"variant": "0.1"})
    catalogue = load_catalogue("agentdojo")
    for rid in catalogue.rules:
        if rid.startswith("agentdojo.capture_") and TWIN_SUFFIX not in rid:
            resolved = policy.cite(rid)
            assert catalogue.get(resolved) is not None and catalogue.get(resolved).citable, (profile_id, rid)
    if profile_id != "agentdojo-live":  # an AgentDyn suite runs only in the fork and AgentDyn, whose suite files it cites
        assert policy.cite("agentdyn.suite_benchmark@1") == "agentdyn.suite_benchmark@1"
