"""Profile, registry entry and family schema of the ``wirelog`` family (docs/architecture D.20.10, D.3; D-280, D-285)."""

from __future__ import annotations

import hashlib
import json
import tomllib

import wirelog_support as support

from agentprov.adapters.profiles import load_profile

SRC = support.REPO / "src" / "agentprov" / "adapters" / "wirelog"


def test_profile_pins_licence_import_and_family_schema():
    import jsonschema

    profile = load_profile(support.PROFILE)
    assert (profile.family, profile.source_id, profile.parts) == ("wirelog", "what-surrounds", ("runs-named",))
    (pin,) = profile.data["source"]["pins"]
    assert pin["sha256"] == support.ZIP_SHA256 and pin["primary"] is True and pin["doi"] == "10.5281/zenodo.21944598"
    assert profile.data["licence"]["spdx"] == "CC-BY-4.0" and profile.data["licence"]["policy"] == "include"
    imp = profile.data["import"]
    assert imp["dialect"] == "wirelog.request_response" and imp["mapper"] == "wirelog.run_dir"
    assert set(imp["variants"]) == {"bedrock-converse", "anthropic-messages"}
    schema = json.loads((SRC / "family.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    family = tomllib.loads((SRC / "profiles" / f"{support.PROFILE}.profile.toml").read_text(encoding="utf-8"))["family"]["wirelog"]
    assert list(jsonschema.Draft202012Validator(schema).iter_errors(family)) == []
    jsonschema.Draft202012Validator.check_schema(json.loads((SRC / "ext.schema.json").read_text(encoding="utf-8")))
    assert family["semantics_profile"] == {"id": "wirelog.tools", "version": 1}
    assert family["synthetic_tools"] is True  # D-284
    assert not set(family["no_attack_arms"]) & set(family["payloads"])
    assert not set(family["code_only_payload_arms"]) & set(family["payloads"])


def test_task_table_digests_name_the_fixture_prompts():
    """Every task id the fixtures name comes from a table row (the digests are of the prompts as logged)."""
    family = load_profile(support.PROFILE).family_table()
    rows = {r["sha256"]: r["id"] for r in family["tasks"]}
    for crit in ("param_description", "user_prefix", "tool_description_hijack"):
        first = json.loads(support.member_bytes(support.label_of(crit, "request.json")))[0]["messages"][0]["content"][0]["text"]
        assert hashlib.sha256(first.encode("utf-8")).hexdigest() in rows, crit


def test_registry_entry_is_supported_and_cc_by():
    from agentprov.adapters.registry import MAPPERS, READERS, get_source
    from agentprov.adapters.runner import resolve_factory

    reg = get_source("what-surrounds")
    (part,) = reg.capabilities
    assert part.part == "runs-named" and part.import_status == "supported" and part.target_import_status == "supported"
    assert part.profile == support.PROFILE and part.semantics == ("wirelog.tools@1",) and part.corpus_id == "what-surrounds"
    assert set(part.variants) == {"bedrock-converse", "anthropic-messages"}
    assert reg.licence.spdx == "CC-BY-4.0" and reg.licence.restrictions == () and reg.licence.policy == "include"
    assert resolve_factory(READERS["wirelog.request_response"]).__name__ == "WireLogReader"
    assert resolve_factory(MAPPERS["wirelog.run_dir"]).__name__ == "WireLogMapper"
