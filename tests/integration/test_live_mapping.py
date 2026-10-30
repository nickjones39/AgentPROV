"""Core side of live runs (docs/architecture K.8.5): every captured session maps, validates, annotates and derives.

Inputs: the frozen sessions under ``tests/fixtures/capture/<scenario>/session/`` (the backend stream's scripted
scenarios) and, with ``AGENTPROV_LIVE_ARTEFACTS``, the staging directories a ``backend-agentdojo`` job produced (those
items carry the ``live_artefacts`` marker). With no session at all the test skips with the reason. For each session:

* the staging directory maps through ``agentprov.adapters.runner.live`` (no-follow reads) to a sealed live AER, valid in
  release mode against the staged objects;
* SEM ``agentdojo.suites@1`` passes tier 3, PROV derives deterministically and passes tier 4;
* context membership is OBSERVED for every call whose ``llm.request`` recorded ``input_at``, DERIVED otherwise;
* a sealed session's capture chain is consistent.

The sessions are third-party-free but are read programmatically only; nothing here prints their content.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "adapters" / "agentdojo"))

from capture_support import live_sessions, map_staged_session  # noqa: E402

from agentprov.adapters.semantics_profiles import load_semantics_profile  # noqa: E402
from agentprov.aer.reader import load_aer_bytes  # noqa: E402
from agentprov.prov.engine import derive  # noqa: E402
from agentprov.sem.engine import annotate  # noqa: E402
from agentprov.sem.validate import validate_sem_document  # noqa: E402
from agentprov.validate import validate_prov  # noqa: E402


def _params() -> list[Any]:
    found = [pytest.param(path, id=sid, marks=[pytest.mark.live_artefacts] if live else [])
             for sid, path, live in live_sessions()]
    return found or [pytest.param(None, id="no-capture-sessions")]


@pytest.mark.parametrize("staged", _params())
def test_session_maps_validates_and_derives(staged: Path | None) -> None:
    if staged is None:
        pytest.skip("no capture/0.1 session under tests/fixtures/capture/ and AGENTPROV_LIVE_ARTEFACTS unset")
    m = map_staged_session(staged)
    assert not m.outcome.degenerate, m.codes
    report = m.validate()
    assert report.ok, [(f.code, f.pointer) for f in report.errors]
    doc = load_aer_bytes(m.data)
    profile = load_semantics_profile("agentdojo.suites", 1)
    sem = annotate(doc, profile)
    sem_report = validate_sem_document(sem, doc, mode="release", profile=profile)
    assert sem_report.ok and not sem_report.skipped, [f.code for f in sem_report.errors]
    result = derive(doc, [sem], sem_profiles={("agentdojo.suites", 1): profile})
    assert result.prov_json == derive(doc, [annotate(doc, profile)], sem_profiles={("agentdojo.suites", 1): profile}).prov_json
    checks = validate_prov(result.prov_json, doc, sems=[sem])
    assert checks.passed, [(o.id, [f.code for f in o.findings]) for o in checks.outcomes
                           if o.status not in ("pass", "not_applicable")]
    # context membership: OBSERVED with recorded input_at, DERIVED under the alignment rule otherwise
    with_positions = {r["id"] for r in m.records if r.get("k") == "model_call" and "input" in r
                      and r.get("evf", {}).get("/input") is None}
    prov = json.loads(result.prov_json)
    statements = list(prov.get("used", {}).values())
    for bundle in prov.get("bundle", {}).values():
        statements += list(bundle.get("used", {}).values())
    for stmt in statements:
        if stmt.get("apv:rule") == "aprov.use_context@1":
            activity = str(stmt["prov:activity"]).removeprefix("x:")
            expected = "apv:Observed" if activity in with_positions else "apv:Derived"
            assert stmt["apv:evidenceClass"]["$"] == expected, activity
    if "capture_unsealed" not in m.codes:
        assert m.checks("aer.acc.capture_chain@1")[0]["verdict"] == "consistent"
