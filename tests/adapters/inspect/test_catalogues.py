"""The inspect family's data: rule catalogue, profile, schemas, artefact catalogue and registry entry (D.3-D.5, D.9,
D.15.2; K.4.2)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tarfile
import tomllib
from pathlib import Path

from agentprov.artefacts.catalogue import check_references
from agentprov.artefacts.catalogue import load_catalogue as load_artefact_catalogue

import jsonschema
import pytest

import inspect_support as support
from agentprov.adapters.profiles import load_profile
from agentprov.adapters.registry import MAPPERS, READERS, get_source
from agentprov.adapters.runner import resolve_factory
from agentprov.aer.rules import load_catalogue

HOME = support.REPO / "src" / "agentprov" / "adapters" / "inspect"
#: Every rule of the D.9.2 table and the D.5.4 index.
D92_RULES = (
    "inspect.header_applies_to_samples", "inspect.sample_init_fixtures", "inspect.span_is_scope",
    "inspect.agent_span_is_subagent", "inspect.model_event_is_call", "inspect.cache_read", "inspect.model_error",
    "inspect.tool_event_is_execution", "inspect.tool_call_id_match", "inspect.tool_error_status",
    "inspect.tool_output_truncated", "inspect.approval_decision", "inspect.compaction", "inspect.state_event",
    "inspect.sandbox_activity", "inspect.score_event", "inspect.no_order_from_event_list",
)
D93_ISSUES = ("sample_limit", "branch_unsupported", "compaction_unmodelled", "unmapped_event", "unknown_content_type")


def test_catalogue_declares_every_d92_rule_and_d93_issue_code():
    catalogue = load_catalogue("inspect")
    for rule in D92_RULES:
        entry = catalogue.get(f"{rule}@1")
        assert entry is not None and entry.cls == "D" and entry.status == "active", rule
    for code in D93_ISSUES:
        assert catalogue.declares_issue_code(f"inspect.{code}"), code
    reserved = catalogue.get("inspect.sample_identity_efp@1")
    assert reserved is not None and reserved.status == "reserved"


def test_catalogue_test_references_exist():
    """D.5.2 validation item 6: every ``tests`` node id of the inspect catalogue exists."""
    doc = tomllib.loads((HOME / "rules" / "inspect.rules.toml").read_text(encoding="utf-8"))
    for rule in doc["rule"]:
        for node in rule.get("tests", []):
            file, _, name = node.partition("::")
            assert f"def {name}(" in (support.REPO / file).read_text(encoding="utf-8"), f"{rule['id']}: {node}"


def test_profile_family_table_matches_its_closed_schema():
    profile = load_profile("survey-agentharm")
    schema = json.loads((HOME / "family.schema.json").read_text(encoding="utf-8"))
    table = tomllib.loads((HOME / "profiles" / "survey-agentharm.profile.toml").read_text(encoding="utf-8"))["family"]["inspect"]
    jsonschema.validate(table, schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({**table, "unknown_key": 1}, schema)
    assert profile.family == "inspect" and profile.source_id == "agent-security-tools-survey"
    assert profile.data["import"]["dialect"] == profile.data["import"]["mapper"] == "inspect.eval"
    assert "status" not in profile.data
    restrictions = profile.data["licence"]["restrictions"]
    assert restrictions and "AgentHarm" in restrictions[0]  # the use clause propagates (R-14)
    quirk_rules = {r for q in table["quirk"] for r in q.get("rules", [])}
    catalogue = load_catalogue("inspect")
    assert all(catalogue.get(r) is not None for r in quirk_rules)


def _compiled(schema: dict) -> jsonschema.protocols.Validator:
    """The schema checked once and compiled, for many instances (``jsonschema.validate`` re-checks it on every call)."""
    cls = jsonschema.validators.validator_for(schema)
    cls.check_schema(schema)
    return cls(schema)


def _validate(validator: jsonschema.protocols.Validator, instance: object) -> None:
    """Exactly ``jsonschema.validate``'s failure: the best-matching error, raised."""
    error = jsonschema.exceptions.best_match(validator.iter_errors(instance))
    if error is not None:
        raise error


def test_ext_inspect_matches_its_schema(committed):
    schema = json.loads((HOME / "ext.schema.json").read_text(encoding="utf-8"))
    validator = _compiled(schema)
    seen: set[str] = set()
    for u in committed.units:
        for record in u.records:
            ext = record.get("ext", {}).get("inspect")
            if ext is not None:
                _validate(validator, ext)
                seen.update(ext)
    assert {"run_id", "span", "events", "uuid", "id"} <= seen


def test_artefact_catalogue_is_well_formed_and_cites_declared_rules():
    doc = tomllib.loads((HOME / "artefacts.toml").read_text(encoding="utf-8"))
    assert doc["version"] == 1 and set(doc) == {"version", "family", "namespaces", "artefact"}
    assert doc["family"] == "inspect" and doc["namespaces"] == ["inspect"]
    assert check_references(load_artefact_catalogue("inspect")) == []  # the shared layer's schema and rule-id check
    catalogue = load_catalogue("inspect")
    fields = {"id", "title", "description", "scope", "cause", "detector", "recorded_as", "handling", "expected",
              "manuscript", "refs"}
    ids = [a["id"] for a in doc["artefact"]]
    assert len(ids) == len(set(ids))
    for entry in doc["artefact"]:
        # `claims` is optional (D.15.8 item 3): only the pre-check wave-1 entries on generic detectors carry it (D-582)
        assert fields <= set(entry) <= fields | {"claims"} and entry["id"].startswith("inspect.art."), entry["id"]
        assert entry["cause"] in {"upstream_harness", "benchmark", "provider", "baseline_converter", "capture", "unknown"}
        assert entry["handling"]["class"] in {"CR", "DR", "RJ", "FO", "NR"}
        # a handling rule is required for CR and DR only; a generic detector is no catalogue rule (D.15.8 items 3, 4)
        rules = [entry["detector"]["rule"], entry["handling"].get("rule")]
        for rule in (r for r in rules if r is not None and not r.startswith("artefact.generic.")):
            assert catalogue.get(rule) is not None, rule


def test_registry_entry_is_the_gated_value_with_lazy_factories():
    source = get_source("agent-security-tools-survey")
    part = {c.part: c for c in source.capabilities}["agentharm"]
    assert part.dialects == ("inspect.eval",) and part.variants == ("v2",) and part.profile == "survey-agentharm"
    assert part.corpus_id == "ast-survey-agentharm" and part.target_import_status == "supported"
    assert part.import_status in ("partial", "supported")  # D.3.2 rule 1: never above its gate
    if part.import_status == "supported":  # only with the full pinned snapshot imported and recorded (HON-10)
        assert (Path(__file__).resolve().parents[3] / "docs" / "reports" / "inspect" / "import-cli-agentharm.json").is_file()
    else:
        assert "full snapshot not yet imported" in str(part.caveat)
    assert source.licence.restrictions and source.licence.policy == "include"
    assert READERS["inspect.eval"] == part.reader and MAPPERS["inspect.eval"] == part.mapper
    assert callable(resolve_factory(part.reader)) and callable(resolve_factory(part.mapper))
    code = "import sys, agentprov.adapters.registry; print(any(m.startswith('agentprov.adapters.inspect') for m in sys.modules))"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.strip()
    assert out == "False"


@pytest.mark.slow
def test_restricted_use_fixtures_never_enter_the_sdist(tmp_path):
    """K.4.2: restricted_use fixtures are committable to the private repository only, never in the sdist or wheel."""
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is not on PATH")
    subprocess.run([uv, "build", "--offline", "--sdist", "--out-dir", str(tmp_path)], cwd=support.REPO, check=True,
                   capture_output=True)
    (sdist,) = tmp_path.glob("*.tar.gz")
    with tarfile.open(sdist) as tar:
        names = tar.getnames()
    assert names and not [n for n in names if "/tests/" in n or n.endswith(".eval")]
