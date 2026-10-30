"""D-663: T0's check of an Inspect worker's catalogue (agentprov-inspect-catalogue/0.1). The fixture is the catalogue
the inspect-agentharm worker builds (names and counts only; backends/inspect catalogue.py)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from agentprov.cli.live.inspect_catalogue import CatalogueError, checked_inspect_catalogue

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "inspect_harness" / "catalogue-agentharm.json"


@pytest.fixture
def doc() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_the_worker_catalogue_passes_unchanged(doc):
    assert checked_inspect_catalogue(doc, "inspect-agentharm") == doc
    tasks = {t["name"]: t for t in doc["tasks"]}
    assert {s["name"]: s["samples"] for s in tasks["inspect_evals/agentharm"]["splits"]} == {"test_public": 176, "val": 32}


def test_unknown_members_are_dropped(doc):
    doc["extra"] = "x"
    doc["tasks"][0]["prompt"] = "anything"
    doc["tasks"][0]["fixed"]["temperature_nan"] = float("nan")
    out = checked_inspect_catalogue(doc, "inspect-agentharm")
    assert "extra" not in out and "prompt" not in out["tasks"][0] and "temperature_nan" not in out["tasks"][0]["fixed"]


@pytest.mark.parametrize("mutate", [
    lambda d: d.update(format="agentprov-backend-catalogue/0.1"),
    lambda d: d.update(backend="inspect-other"),
    lambda d: d["tasks"][0].update(name="../etc/passwd"),
    lambda d: d["tasks"][0].update(name="a task with spaces"),
    lambda d: d["tasks"][0]["splits"][0].update(samples=-1),
    lambda d: d["tasks"][0]["splits"][0].update(samples=True),
    lambda d: d["tasks"][0]["params"][0].update(type="code"),
    lambda d: d["tasks"][0]["scorers"][0]["judge_roles"][0].update(calls_per_sample="many"),
    lambda d: d.update(tasks=[{}] * 201),
    lambda d: d["dataset"].update(revision="main"),
])
def test_malformed_catalogues_are_refused(doc, mutate):
    bad = copy.deepcopy(doc)
    mutate(bad)
    with pytest.raises(CatalogueError):
        checked_inspect_catalogue(bad, "inspect-agentharm")


def test_run_dispatches_on_the_catalogue_format(doc):
    """`run --catalogue` (D-652) checks an Inspect worker's document with the Inspect checker, by `format`."""
    from agentprov.cli.run import checked_any_catalogue

    assert checked_any_catalogue(doc, "inspect-agentharm") == doc
    with pytest.raises(Exception, match="malformed"):
        checked_any_catalogue({**doc, "format": "agentprov-backend-catalogue/0.1"}, "inspect-agentharm")
