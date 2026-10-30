"""Profiles, registry entries, schemas and artefact catalogue of the ``openhands`` family (docs/architecture D.17.11,
D.3, D.15)."""

from __future__ import annotations

import json
import tomllib

import jsonschema
import openhands_support as support

from agentprov.adapters.code_verification import code_commits
from agentprov.adapters.profiles import load_profile

SRC = support.REPO / "src" / "agentprov" / "adapters" / "openhands"
PROFILES = {"openagentsafety": ("oas-0.28", "MIT"), "redcode-exec-openhands": ("oh-1.5", "CC-BY-4.0")}


def _family(pid: str) -> dict:
    return tomllib.loads((SRC / "profiles" / f"{pid}.profile.toml").read_text(encoding="utf-8"))["family"]["openhands"]


def test_profiles_load_and_their_family_tables_follow_the_closed_schema():
    schema = json.loads((SRC / "family.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator.check_schema(json.loads((SRC / "ext.schema.json").read_text(encoding="utf-8")))
    cited = set().union(*code_commits("openhands").values())
    for pid, (variant, spdx) in PROFILES.items():
        profile = load_profile(pid)
        assert (profile.family, profile.parts) == ("openhands", ("head",))
        assert profile.data["import"]["variants"] == (variant,) and profile.data["licence"]["spdx"] == spdx
        family = _family(pid)
        assert list(jsonschema.Draft202012Validator(schema).iter_errors(family)) == []
        assert {v["commit"] for v in family["verified_code"]} <= cited  # each verified commit is cited by the D rules


def test_redcode_pins_cover_every_fixture_container():
    pins = {p["sha256"] for p in load_profile("redcode-exec-openhands").data["source"]["pins"]}
    containers = {e["record_locator"]["container_sha256"] for e in support.source_entries() if "record_locator" in e}
    assert containers and containers <= pins


def test_every_ext_member_written_is_declared_in_the_ext_schema(mapped):
    schema = json.loads((SRC / "ext.schema.json").read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    for fid, m in mapped.items():
        for rec in m.records:
            ext = rec.get("ext", {}).get("openhands")
            if ext is not None:
                assert list(validator.iter_errors(ext)) == [], (fid, rec["id"])


def test_registry_entries_are_gated_and_lazy():
    from agentprov.adapters.registry import MAPPERS, READERS, get_source
    from agentprov.adapters.runner import resolve_factory

    for pid, (variant, spdx) in PROFILES.items():
        reg = get_source(pid)
        (part,) = reg.capabilities
        # both supported since the wave-2 seal (D-830)
        assert part.import_status == "supported" and part.profile == pid and part.variants == (variant,)
        assert part.semantics == ("openhands.tools@2",) and reg.licence.spdx == spdx and reg.licence.policy == "include"
    assert resolve_factory(READERS["openhands.events"]).__name__ == "OpenHandsEventsReader"
    assert resolve_factory(MAPPERS["openhands.events"]).__name__ == "OpenHandsMapper"


def test_the_artefact_catalogue_is_well_formed():
    from agentprov.artefacts.catalogue import check_references, load_catalogue

    cat = load_catalogue("openhands")
    assert cat.version == 1 and check_references(cat) == []
    assert {e.id for e in cat.entries} >= {"openhands.art.filtered_events", "openhands.art.score_one_ambiguous"}
    for entry in cat.entries:
        assert set(entry.profiles) <= set(PROFILES)
