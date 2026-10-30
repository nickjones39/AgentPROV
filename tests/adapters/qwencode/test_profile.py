"""Profile, registry entry and family schema of the ``qwencode`` family (docs/architecture D.24.9, D.3; D-571)."""

from __future__ import annotations

import json
import tomllib

import qwencode_support as support

from agentprov.adapters.profiles import load_profile

SRC = support.REPO / "src" / "agentprov" / "adapters" / "qwencode"


def test_profile_pins_licence_import_and_family_schema():
    import jsonschema

    profile = load_profile(support.PROFILE)
    assert (profile.family, profile.source_id, profile.parts) == ("qwencode", support.PROFILE, ("qwen3coder",))
    pins = {p["role"]: p for p in profile.data["source"]["pins"]}
    assert pins["runs"]["sha256"] == support.RUNS_SHA256 and pins["runs"]["primary"] is True
    assert pins["supp"]["sha256"] == support.SUPP_SHA256 and pins["supp"]["primary"] is False
    assert {p["doi"] for p in pins.values()} == {"10.5281/zenodo.23168099"}
    assert profile.data["licence"]["spdx"] == "CC-BY-4.0" and profile.data["licence"]["policy"] == "include"
    imp = profile.data["import"]
    assert imp["dialect"] == imp["mapper"] == "qwencode.json" and imp["variants"] == ("v0.21",)
    assert all(str(g).startswith("supp:") for g in imp["context_artefacts"])
    # D-578 as amended 2026-10-21 (D-602): one object-scope rule for the supplementary zip (test_withhold.py)
    assert [r["id"] for r in profile.data["withhold"]["rules"]] == ["hf-token-shape"]
    schema = json.loads((SRC / "family.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    family = tomllib.loads((SRC / "profiles" / f"{support.PROFILE}.profile.toml").read_text(encoding="utf-8"))["family"]["qwencode"]
    assert list(jsonschema.Draft202012Validator(schema).iter_errors(family)) == []
    jsonschema.Draft202012Validator.check_schema(json.loads((SRC / "ext.schema.json").read_text(encoding="utf-8")))
    assert family["semantics_profile"] == {"id": "qwencode.tools", "version": 2}


def test_supp_pin_is_the_openhands_parts_own():
    """The supplementary zip is pinned identically by both profiles of the deposit."""
    mine = {p["role"]: p for p in load_profile(support.PROFILE).data["source"]["pins"]}["supp"]
    theirs = {p["role"]: p for p in load_profile("redcode-exec-openhands").data["source"]["pins"]}["supp"]
    assert {k: mine[k] for k in ("doi", "file", "sha256", "md5", "size")} == {k: theirs[k] for k in ("doi", "file", "sha256", "md5", "size")}


def test_registry_entry_is_supported_and_cc_by():
    from agentprov.adapters.registry import MAPPERS, READERS, get_source
    from agentprov.adapters.runner import resolve_factory

    reg = get_source(support.PROFILE)
    (part,) = reg.capabilities
    assert part.part == "qwen3coder" and part.import_status == "supported" and part.target_import_status == "supported"
    assert part.profile == support.PROFILE and part.semantics == ("qwencode.tools@2",)
    assert reg.licence.spdx == "CC-BY-4.0" and reg.licence.restrictions == ()
    assert resolve_factory(READERS["qwencode.json"]).__name__ == "QwenJsonReader"
    assert resolve_factory(MAPPERS["qwencode.json"]).__name__ == "QwenJsonMapper"
