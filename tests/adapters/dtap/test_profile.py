"""Profile, registry entry, rate exclusions and artefact catalogue of the ``dtap`` family (docs/architecture D.16.12,
D.16.16, D.3; D-48 item 10)."""

from __future__ import annotations

import json
import tomllib
from importlib import resources

import dtap_support as support

from agentprov.adapters.profiles import load_profile

SRC = support.REPO / "src" / "agentprov" / "adapters" / "dtap"


def test_profile_pins_licence_import_and_family_schema():
    profile = load_profile("dtap-bench")
    assert (profile.family, profile.source_id, profile.parts) == ("dtap", "dtap", ("head",))
    pins = {(p["role"], p.get("file", "")): p for p in profile.data["source"]["pins"]}
    runs = pins[("runs", "")]
    assert runs["kind"] == "git" and runs["commit"] == support.RUNS_COMMIT and runs["primary"] is True
    assert pins[("tasks", "")]["commit"] == support.TASKS_COMMIT
    lfs = [p for (role, _f), p in pins.items() if role == "lfs_object"]
    assert {p["sha256"] for p in lfs} == {"29b8bc6959bc434c2cc61d5ac3689dc949e50d14a9a4b366dc426e56bf51aa83",
                                          "6731a5cc8842c7983624ca8a234574d81fda165fbac46c94219b1f0a01e8d072"}
    assert {p["bytes"] for p in lfs} == {12281319, 10646342} and all(p["kind"] == "hf" for p in lfs)
    assert profile.data["licence"]["spdx"] == "Apache-2.0" and profile.data["licence"]["policy"] == "include"
    imp = profile.data["import"]
    assert imp["dialect"] == imp["mapper"] == "dtap.trajectory" and imp["context_artefacts"] == ("tasks:**/config.yaml",)
    import jsonschema

    schema = json.loads((SRC / "family.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    family = tomllib.loads((SRC / "profiles" / "dtap-bench.profile.toml").read_text(encoding="utf-8"))["family"]["dtap"]
    assert list(jsonschema.Draft202012Validator(schema).iter_errors(family)) == []
    jsonschema.Draft202012Validator.check_schema(json.loads((SRC / "ext.schema.json").read_text(encoding="utf-8")))


def test_registry_entry_is_supported_lazy_and_apache_without_restriction():
    from agentprov.adapters.registry import MAPPERS, READERS, get_source
    from agentprov.adapters.runner import resolve_factory

    reg = get_source("dtap")
    (part,) = reg.capabilities
    assert part.part == "head" and part.import_status == "supported" and part.target_import_status == "supported"
    assert part.profile == "dtap-bench" and part.semantics == ("dtap.tools@3",) and part.corpus_id == "dtap-bench"
    assert reg.licence.spdx == "Apache-2.0" and reg.licence.restrictions == () and reg.licence.policy == "include"
    assert resolve_factory(READERS["dtap.trajectory"]).__name__ == "DtapTrajectoryReader"
    assert resolve_factory(MAPPERS["dtap.trajectory"]).__name__ == "DtapMapper"


def test_rate_exclusions_parse_and_name_declared_codes():
    """Phase-11 interface (D-48 item 10): optional package data adapters/dtap/rates.toml."""
    data = (resources.files("agentprov").joinpath("adapters", "dtap", "rates.toml")).read_bytes()
    doc = tomllib.loads(data.decode("utf-8"))
    assert doc["version"] == 1 and doc["family"] == "dtap"
    from agentprov.aer.rules import load_catalogue
    from agentprov.aer.types import CORE_ISSUE_CODES

    cat = load_catalogue("dtap", 3)
    ids = set()
    for entry in doc["exclusion"]:
        assert set(entry) == {"id", "profiles", "issue_codes", "judgement_origins", "rates", "basis"}
        assert entry["id"].startswith("dtap.rate.") and entry["id"] not in ids and entry["profiles"] == ["dtap-bench"]
        ids.add(entry["id"])
        assert set(entry["rates"]) <= {"field_groups", "unknowns", "outcome"} and entry["basis"]
        assert set(entry["judgement_origins"]) <= {"checker", "harness_default", "harness_rule", "recomputed"}
        for code in entry["issue_codes"]:
            seal = code.removeprefix("map.")
            assert code.startswith("map.") and (seal in CORE_ISSUE_CODES or cat.declares_issue_code(seal)), code
    assert {"dtap.rate.harness_failure", "dtap.rate.unresolved_rerun", "dtap.rate.outcome_only", "dtap.rate.non_informative"} == ids


def test_artefact_catalogue_validates_and_references_exist():
    from agentprov.artefacts.catalogue import check_references, load_catalogue

    cat = load_catalogue("dtap")
    assert check_references(cat) == [] and len(cat.entries) >= 25
    assert all(e.id.startswith("dtap.art.") for e in cat.entries)
    assert all(x.status == "unverified" for e in cat.entries for x in e.expected)  # until the step-4 import (D.15.6)
