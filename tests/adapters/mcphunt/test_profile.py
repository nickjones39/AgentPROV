"""Profile, registry entry, family schema and withholding policy of the ``mcphunt`` family (D.21.10; D-286, D-288,
D-289)."""

from __future__ import annotations

import json
import tomllib

import mcphunt_support as support

from agentprov.adapters.profiles import load_profile

SRC = support.REPO / "src" / "agentprov" / "adapters" / "mcphunt"


def test_profile_pins_licence_import_and_family_schema():
    import jsonschema

    profile = load_profile(support.PROFILE)
    assert (profile.family, profile.source_id, profile.parts) == ("mcphunt", "mcphunt", ("head",))
    pins = profile.data["source"]["pins"]
    runs = [p for p in pins if p["role"] == "runs"]
    assert len(runs) == 1 and runs[0]["commit"] == support.REVISION and runs[0]["primary"] is True
    lfs = [p for p in pins if p["role"] == "lfs_object"]
    assert len(lfs) == 15 and all(p["revision"] == support.REVISION and len(p["sha256"]) == 64 for p in lfs)
    assert profile.data["licence"]["spdx"] == "CC-BY-4.0" and profile.data["licence"]["policy"] == "include"
    imp = profile.data["import"]
    assert imp["dialect"] == "mcphunt.traces" and imp["mapper"] == "mcphunt.trace" and imp["variants"] == ("v2.0.0",)
    schema = json.loads((SRC / "family.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    family = tomllib.loads((SRC / "profiles" / "mcphunt.profile.toml").read_text(encoding="utf-8"))["family"]["mcphunt"]
    assert list(jsonschema.Draft202012Validator(schema).iter_errors(family)) == []
    jsonschema.Draft202012Validator.check_schema(json.loads((SRC / "ext.schema.json").read_text(encoding="utf-8")))
    assert family["streamed_arrays"] == ["/traces"] and "max_json_element_bytes" not in family
    from agentprov.ingest.profile_limits import PROFILE_RAISABLE  # D-323: the raise sits at the calibrated ceiling

    assert dict(imp["limits"]) == {"max_json_element_bytes": 64 * 2**20} == dict(PROFILE_RAISABLE)


def test_withhold_policy_is_a_shape_backstop_at_object_scope():
    from agentprov.corpus.withhold import policy_of_profile

    profile = load_profile(support.PROFILE)
    data = (SRC / "profiles" / "mcphunt.profile.toml").read_bytes()
    policy = policy_of_profile(data, profile_id=profile.id, profile_version=profile.version)
    assert policy is not None and {r.reason for r in policy.rules} == {"secret"}
    (flag,) = policy.issue_rules  # D-289 option (c): the seal-issue trigger (RW-1, D-311)
    assert (flag.id, flag.code, flag.register_code) == ("canary-flagged", "mcphunt.canary_flagged", "map.mcphunt.canary_flagged")
    backstop = [r for r in policy.rules if r.kind != "issue"]
    assert {r.scope for r in backstop} == {"object"} and len(backstop) == 6
    from agentprov.corpus.withhold import check_issue_codes, declared_issue_codes

    check_issue_codes(policy, declared_issue_codes({"mcphunt": 1}))  # the catalogue declares the code
    text = (SRC / "profiles" / "mcphunt.profile.toml").read_text(encoding="utf-8")
    import re

    # the policy names shapes only, never a value: no full credential-shaped literal is in the profile
    assert not re.search(r"\b(?:sk_live_|AKIA)[A-Za-z0-9]{16}\b|\bxox[abpors]-[A-Za-z0-9-]{10,}\b", text)


def test_registry_entry_is_supported_and_cc_by():
    from agentprov.adapters.registry import MAPPERS, READERS, get_source
    from agentprov.adapters.runner import resolve_factory

    reg = get_source("mcphunt")
    (part,) = reg.capabilities
    assert part.part == "head" and part.import_status == "supported" and part.target_import_status == "supported"
    assert part.profile == "mcphunt" and part.semantics == ("mcphunt.tools@2",) and part.corpus_id == "mcphunt"
    assert reg.licence.spdx == "CC-BY-4.0" and reg.licence.policy == "include"
    assert resolve_factory(READERS["mcphunt.traces"]).__name__ == "McpHuntReader"
    assert resolve_factory(MAPPERS["mcphunt.trace"]).__name__ == "McpHuntMapper"
