"""The ``agentharm`` · ``live`` registry part and the ``agentharm-live`` profile (D-666; design note §5).

* The registration is a planned live part served by the ``inspect-agentharm`` backend, mapped by the unchanged
  ``inspect.eval`` reader and mapper (run, then import: D-665), restricted use (D-668); the survey's AgentHarm part no
  longer claims a live status.
* The profile loads, its ``[family.inspect]`` table (``live`` included) conforms to the closed schema, and its pins are
  the environment's: the lock's wheel hashes, the dataset recipe's revision and the worker's instrumentation ids.
* The ``run`` status gate admits a scripted run of the planned part and refuses a real one.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

import pytest

from agentprov.adapters.profiles import load_profile
from agentprov.cli.common import CommandResult
from agentprov.adapters.registry import BACKENDS, MAPPERS, READERS, get_source
from agentprov.aer.rules import load_catalogue
from agentprov.cli.live.envs import backend_project, dataset_recipe, lock_wheel

REPO = Path(__file__).resolve().parents[3]


def _part():
    return {c.part: c for c in get_source("agentharm").capabilities}["live"]


def _live() -> dict:
    return tomllib.loads((REPO / "src/agentprov/adapters/inspect/profiles/agentharm-live.profile.toml").read_text())


def test_registration_is_the_partial_live_part():
    source = get_source("agentharm")
    assert source.family == "inspect" and [c.part for c in source.capabilities] == ["live"]
    part = _part()
    assert part.evidence == "n/a" and part.import_status is None and part.live_status == "partial"
    assert part.backend == "inspect-agentharm" and part.profile == "agentharm-live"
    assert part.requires == ("backend:inspect-agentharm",) and part.semantics == ("inspect.agentharm@2",)
    assert part.reader == READERS["inspect.eval"] and part.mapper == MAPPERS["inspect.eval"]
    assert "D-668" in " ".join(source.licence.restrictions)
    # D-741: the declared subset of the partial part; D-744: the user-approved probe replaces rule 3's phrase (D-722)
    for phrase in ("--max-calls", "--max-cost-usd", "D-740", "OpenAI-chat endpoints only", "--containment",
                   "Real-model probe 2026-10-23, approved by the user", "API endpoint class",
                   "docs/reports/inspect-harness/probe-d667.md", "not sealed", "D-668"):
        assert phrase in part.caveat, phrase
    assert "no real-model run" not in part.caveat
    survey = {c.part: c for c in get_source("agent-security-tools-survey").capabilities}["agentharm"]
    assert survey.live_status is None and survey.import_status == "supported"


def test_backend_descriptor_is_native_log():
    descriptor = BACKENDS["inspect-agentharm"]
    assert descriptor.project == "backends/inspect/envs/agentharm" and descriptor.native_log is True
    assert descriptor.worker_module == "agentprov_backend_inspect.worker" and descriptor.capture_mapper == "inspect.eval"
    assert descriptor.profile == "agentharm-live"
    assert not any(d.native_log for name, d in BACKENDS.items() if name != "inspect-agentharm")


def test_profile_loads_without_status():
    profile = load_profile("agentharm-live")
    assert profile.version == 1 and profile.family == "inspect" and profile.parts == ("live",)
    assert profile.source_id == "agentharm" and "status" not in profile.data
    assert tuple(profile.data["import"]["include"]) == ("raw/inspect/*.eval",)


def test_family_table_conforms_to_the_closed_schema():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((REPO / "src/agentprov/adapters/inspect/family.schema.json").read_bytes())
    table = _live()["family"]["inspect"]
    jsonschema.validate(table, schema)
    bad = json.loads(json.dumps(table))
    bad["live"]["unknown"] = 1
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)
    bad = json.loads(json.dumps(table))
    bad["live"]["backend"] = "agentdojo"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_pins_are_the_environments():
    live = _live()["family"]["inspect"]["live"]
    project = backend_project(live["backend"], REPO)
    assert f"backends/{project.project.relative_to(REPO / 'backends').as_posix()}" == live["project"]
    for pin in (live["pins"], *live["distribution_pins"]):
        wheel = lock_wheel(project, pin["distribution"])
        assert wheel is not None and (wheel["version"], wheel["wheel_sha256"]) == (pin["version"], pin["wheel_sha256"])
    assert _live()["family"]["inspect"]["producer_band"]["inspect_ai"] == [live["pins"]["version"]]
    recipe = dataset_recipe(project)
    assert recipe is not None and {"repo": recipe["repo"], "revision": recipe["revision"]} == live["dataset"]
    (pin,) = _live()["source"]["pins"]
    assert (pin["dataset"], pin["revision"]) == (recipe["repo"], recipe["revision"])


def test_instrumentation_is_the_workers():
    worker = (REPO / "backends/inspect/src/agentprov_backend_inspect/worker.py").read_text()
    ids = re.findall(r'"id": "(inspect\.[a-z_]+@\d+)"', worker)
    assert sorted(ids) == sorted(_live()["family"]["inspect"]["live"]["instrumentation_accepted"])


def test_every_quirk_rule_exists_in_the_shipped_catalogue():
    catalogue = load_catalogue("inspect")
    for quirk in _live()["family"]["inspect"]["quirk"]:
        for rule in quirk.get("rules", ()):
            entry = catalogue.get(rule)
            assert entry is not None and entry.citable, (quirk["id"], rule)


def test_run_gate_admits_scripted_and_real_runs_with_the_caveat():
    """D-741: the partial part admits a real-model run past the status gate, with the caveat as a notice (the endpoint,
    consent, caps and the D-740 bound are checked later in ``run``); a scripted run is admitted the same way."""
    from agentprov.cli.run import _live_capability

    for scripted in (True, False):
        result = CommandResult()
        capability = _live_capability("agentharm", result, scripted=scripted)
        assert capability.part == "live" and capability.backend == "inspect-agentharm"
        assert any(n.startswith("agentharm · live (partial): partial (D-741") for n in result.notices), result.notices
