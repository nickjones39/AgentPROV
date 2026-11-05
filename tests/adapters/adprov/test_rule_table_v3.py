"""Catalogue ``adprov`` v3 (D-1063, regeneration-batch item 180): audit AU-RB-6 and review UC-41.

AU-RB-6: ``adprov.temperature_not_transmitted@1`` and ``adprov.run_interval_scope@1`` were class D with no code and no
``_unverified`` twin, against D-27 c6 (documentary evidence alone is not enough for D). Version 3 supersedes both: the
temperature reading is minted ``@2`` at class I (the cited request path is the writer's shorthand backends'; which LLM
class ran is not recorded), the run interval ``@2`` keeps class D with the code read offline at the profile's verified
commits (579a908 generate.py brackets ``run_task_with_pipeline``; a75aba7 task_suite.py loads the environment and
scores). Version 2, which the sealed corpus adprov-v1-release-rg2 records, ships byte-exact under ``rules/archive/``;
the source profile names no catalogue version, so it is not bumped."""

from __future__ import annotations

import hashlib
import tomllib
from importlib import resources
from typing import Any

from agentprov.adapters.code_verification import TWIN_SUFFIX, code_commits, parse_verified_code
from agentprov.adapters.profiles import load_profile
from agentprov.aer.rules import load_catalogue

#: derivation.json of adprov-v1-release-rg2 (aer stage rules_sha256.adprov and profile_sha256, read 2026-11-05)
SEALED_V2 = "92a4071ef26be5cde543a458a5dd6ba149a782e4b921f254cabedb1bc5ffe5a0"
SEALED_PROFILE = "e8f39d3263a7dc898645dd308bafafc5c872a7928816b57da13a49f6f9ab1e8c"
#: D rules whose reading does not depend on the producing code: text transformations by AgentPROV, cited as given
CODE_INDEPENDENT = {"adprov.lone_surrogate_replaced@1", "adprov.content_not_inlined@1"}


def _raw() -> dict[str, dict[str, Any]]:
    data = resources.files("agentprov").joinpath("adapters", "adprov", "rules", "adprov.rules.toml").read_bytes()
    return {f"{r['id']}@{r['version']}": r for r in tomllib.loads(data.decode("utf-8"))["rule"]}


def test_version_2_ships_byte_exact_as_the_sealed_corpus_records_it():
    assert load_catalogue("adprov").version == 3
    archived = load_catalogue("adprov", 2)
    assert archived.version == 2 and archived.digest.removeprefix("sha256:") == SEALED_V2
    data = resources.files("agentprov").joinpath("adapters", "adprov", "rules", "archive", "adprov.rules.v2.toml").read_bytes()
    assert hashlib.sha256(data).hexdigest() == SEALED_V2


def test_the_profile_is_not_bumped():
    profile = load_profile("adprov-v1")
    assert profile.version == 2 and profile.sha256.removeprefix("sha256:") == SEALED_PROFILE


def test_the_document_only_d_rules_are_superseded():
    raw, catalogue = _raw(), load_catalogue("adprov")
    for name in ("adprov.temperature_not_transmitted", "adprov.run_interval_scope"):
        assert raw[f"{name}@1"]["status"] == "superseded" and raw[f"{name}@1"]["class"] == "D"
        assert catalogue.get(f"{name}@1").citable  # old corpora stay recomputable (D.5.1)
        assert raw[f"{name}@2"]["status"] == "active"
    assert catalogue.get("adprov.temperature_not_transmitted@2").cls == "I"
    assert catalogue.get("adprov.run_interval_scope@2").cls == "D"
    # the run interval's code is among the commits the profile verifies for a released transcript
    verified = {v.commit for v in parse_verified_code(load_profile("adprov-v1").family_table()["verified_code"], "x")
                if v.matches({"transcript": "released"})}
    assert code_commits("adprov")["adprov.run_interval_scope@2"] <= verified


def test_every_active_d_rule_cites_code_or_has_a_twin():
    """D-27 c6: an active D rule of adprov cites code, or has an ``_unverified`` twin, or is code-independent."""
    raw = _raw()
    for rid, rule in raw.items():
        if rule["class"] != "D" or rule["status"] != "active" or rule.get("code") or rid in CODE_INDEPENDENT:
            continue
        name, _, version = rid.partition("@")
        assert f"{name}{TWIN_SUFFIX}@{version}" in raw, rid


def test_a_mapped_header_cites_catalogue_version_3(v1: Any):
    m = v1.map(v1.dump(v1.released()))
    assert m.header["rules"]["adprov"] == 3 and m.validate().ok
