"""The ``agentdojo-upstream`` profile, the family schema, the registry entry and the artefact catalogue (D.3, D.4, D.15).

* The profile is package data with a digest; its ``[family.agentdojo]`` part conforms to ``family.schema.json``, checked
  by the family's stdlib checker and, differentially, by ``jsonschema`` (D.4.1).
* The pins match J.4.1 (commit, ``runs`` tree, 18,241 blobs) and the catalogue pin matches the shipped catalogues.
* The registry lists ``agentdojo`` · ``2024-06`` at its gated status, with lazy factory strings (D.3.1-D.3.2).
* ``artefacts.toml`` follows the D.15.2 field table; every non-planned detector and handling rule exists (D.15.7).
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

from agentprov.adapters.agentdojo.profile import check_against_schema, family_schema, family_table
from agentprov.adapters.profiles import load_profile, parse_profile
from agentprov.adapters.registry import MAPPERS, READERS, get_source
from agentprov.adapters.runner import resolve_factory
from agentprov.aer.rules import load_catalogue
from agentprov.errors import ProfileError

REPO = Path(__file__).resolve().parents[3]
FAMILY = REPO / "src" / "agentprov" / "adapters" / "agentdojo"


def test_profile_is_package_data_with_a_digest_and_no_status():
    profile = load_profile("agentdojo-upstream")
    assert profile.version == 2 and len(profile.sha256) == 64 and profile.family == "agentdojo"  # D-31
    assert profile.parts == ("head", "2024-06") and "status" not in profile.data
    imp = profile.data["import"]
    assert imp["dialect"] == imp["mapper"] == "agentdojo.tracelogger"


def test_pins_match_j41():
    pins = {p["role"]: p for p in load_profile("agentdojo-upstream").data["source"]["pins"]}
    june = pins["2024-06"]
    assert june["commit"] == "c274885610efaaafec38b6d3eb07152ba7ff3f94" and june["primary"] is True
    assert june["tree_sha1"] == "1227480d637f06ac435c809ab39803afa72f78fc" and june["expected_files"] == 18241
    assert pins["head"]["commit"] == "089ed468cf3ed0322acc66b0211f26d9d90dbf60"


def test_catalogue_pin_matches_the_shipped_catalogues():
    pinned = dict(load_profile("agentdojo-upstream").data["import"]["rules"])
    assert pinned == {ns: load_catalogue(ns).version for ns in pinned} == {"aer": 1, "agentdojo": 2}


def test_family_part_conforms_to_the_closed_schema_both_checkers():
    jsonschema = pytest.importorskip("jsonschema")
    profile = load_profile("agentdojo-upstream")
    table = family_table(profile)
    jsonschema.validate(table.data, family_schema())
    assert check_against_schema(table.data, family_schema()) == []
    bad = json.loads(json.dumps(table.data))
    bad["harness"]["unknown_key"] = 1
    assert check_against_schema(bad, family_schema()) and _jsonschema_fails(jsonschema, bad)
    bad = json.loads(json.dumps(table.data))
    bad["quirk"][0]["observed"]["2024-06"]["files"] = -1
    assert check_against_schema(bad, family_schema()) and _jsonschema_fails(jsonschema, bad)


def _jsonschema_fails(jsonschema, value) -> bool:
    try:
        jsonschema.validate(value, family_schema())
    except jsonschema.ValidationError:
        return True
    return False


def test_a_profile_violating_the_family_schema_is_refused():
    text = (FAMILY / "profiles" / "agentdojo-upstream.profile.toml").read_text(encoding="utf-8")
    profile = parse_profile(text.replace('code_identity = "unpinned"', 'code_identity = "whatever"').encode(), source="t")
    with pytest.raises(ProfileError):
        family_table(profile)


def test_every_quirk_declares_its_rules_and_2024_06_counts():
    catalogue = load_catalogue("agentdojo")
    table = family_table(load_profile("agentdojo-upstream"))
    for quirk in table.quirks:
        for rule in quirk.rules:
            assert catalogue.get(rule) is not None, (quirk.id, rule)
    observed = {q["id"]: q.get("observed", {}) for q in table.data["quirk"]}
    assert observed["agentdojo.empty_messages_with_outcome"]["2024-06"] == {"files": 207}
    assert observed["agentdojo.pi_detector_redaction"]["2024-06"] == {"logs": 624, "redactions": 2154}


def test_registry_entry_is_gated_and_lazy():
    source = get_source("agentdojo")
    part = {c.part: c for c in source.capabilities}["2024-06"]
    assert part.import_status in ("partial", "supported") and part.target_import_status == "supported" and part.caveat
    if part.import_status == "supported":  # D.3.2: only with the full pinned snapshot imported and recorded (HON-10)
        assert (REPO / "docs" / "reports" / "agentdojo" / "import-cli-2024-06.json").is_file()
    else:
        assert "full snapshot not yet imported" in part.caveat
    assert part.profile == "agentdojo-upstream" and part.variants == ("v0.k11",)
    assert READERS["agentdojo.tracelogger"] == part.reader and MAPPERS["agentdojo.tracelogger"] == part.mapper
    assert callable(resolve_factory(part.reader)) and callable(resolve_factory(part.mapper))
    head = {c.part: c for c in source.capabilities}["head"]  # phase 10 (D.6.12)
    assert head.profile == "agentdojo-upstream" and head.variants == ("v0.k11", "v1.k14", "v1.k14.incomplete")
    if head.import_status == "supported":
        assert (REPO / "docs" / "reports" / "agentdojo" / "import-cli-head.json").is_file()
    else:
        assert head.import_status == "partial" and "full snapshot not yet imported" in str(head.caveat)


# ------------------------------------------------------------------------------------------------ artefact catalogue
_REQUIRED = {"id", "title", "description", "scope", "cause", "detector", "handling", "manuscript", "refs"}
_OPTIONAL = {"claims", "recorded_as", "expected"}
_CAUSES = {"upstream_harness", "benchmark", "provider", "baseline_converter", "capture", "unknown"}
_CLASSES = {"CR", "DR", "RJ", "FO", "NR"}


def test_artefact_catalogue_follows_d152():
    doc = tomllib.loads((FAMILY / "artefacts.toml").read_text(encoding="utf-8"))
    assert doc["version"] == 1 and doc["family"] == "agentdojo"
    entries = doc["artefact"]
    # 20 + 2 (head) import, 5 live, 17 phase-10 (B4: 2026-10-11), 1 phase 9b (regeneration-batch item 26),
    # 5 pre-check wave 1 (D-582, regeneration-batch item 109), 3 pre-check wave 2 (D-589), 1 seagent (D-591),
    # 25 wave-2 artefact scope (D-950: 9 agentdojo, 6 drift, 10 rescont)
    assert len(entries) == 82 and len({e["id"] for e in entries}) == len(entries)
    namespaces = ("agentdojo", "rope", "agentdyn", "mandate", "survey", "geryon", "drift", "rescont")
    assert doc["namespaces"] == list(namespaces)
    catalogues = {n: load_catalogue(n) for n in ("agentdojo", "adprov", "aer", "rope", "agentdyn", "mandate", "survey", "autodojo",
                                                     "drift", "rescont")}
    for entry in entries:
        assert _REQUIRED <= set(entry) <= _REQUIRED | _OPTIONAL, entry["id"]
        assert entry["id"].split(".art.")[0] in namespaces and ".art." in entry["id"] and entry["cause"] in _CAUSES
        assert set(entry["detector"]) == {"rule", "class"} and entry["detector"]["class"] in ("O", "D", "I")
        assert entry["handling"]["class"] in _CLASSES
        for rule in (entry["detector"].get("rule"), entry["handling"].get("rule")):
            if rule is None or rule.startswith("artefact.generic."):
                continue
            assert catalogues[rule.split(".", 1)[0]].get(rule) is not None, (entry["id"], rule)
        assert set(entry.get("recorded_as", {})) <= {"issues", "notes", "sem"}
        for expected in entry.get("expected", ()):
            assert {"snapshot", "count", "basis"} <= set(expected) <= {"snapshot", "count", "basis", "unit", "status"}
            assert expected["count"] >= 0 and expected.get("status", "unverified") in ("verified", "unverified")


def test_artefact_catalogue_parses_with_the_shared_layer():
    """The shared loader (``agentprov.artefacts``, D.15.3) accepts the catalogue and finds every reference (D.15.7)."""
    shared = pytest.importorskip("agentprov.artefacts.catalogue")
    catalogue = shared.parse_catalogue((FAMILY / "artefacts.toml").read_bytes(), family="agentdojo")
    assert len(catalogue.entries) == 82
    assert [str(p) for p in shared.check_references(catalogue)] == []
