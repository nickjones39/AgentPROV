"""Regeneration-batch item 5 (analysis C2, D-370): the suite loads the environment with the run's injections before the
passes (``task_suite.py`` at c274885, 089ed468 and the 0.1.35 wheel), so a TraceLogger execution with payload fixtures
has one ``agentdojo:load_environment`` activity, performed by the benchmark, whose inputs are the fixtures; PROV gives
``used(x:ac0, x:fx<i>)`` and the association with ``bench``. Synthetic logs only."""

from __future__ import annotations

import json
from typing import Any

from pathlib import Path

from test_agentdyn import a_log, map_a

from agentprov.aer.reader import load_aer
from agentprov.prov.engine import derive
from agentprov.validate import validate_prov


def _prov(m: Any, tmp_path: Path) -> dict[str, Any]:
    """Derive the PROV of a mapped log; it passes tier 4."""
    path = tmp_path / "x.aer.jsonl"
    path.write_bytes(m.data)
    doc = load_aer(path)
    prov = derive(doc).prov_json
    result = validate_prov(prov, doc)
    assert result.ok, [(o.id, sorted(o.codes())) for o in result.outcomes if o.status == "fail"]
    return json.loads(prov)


def test_the_environment_load_uses_every_payload(tmp_path):
    doc = a_log(injections={"injection_emails_0": "payload one", "injection_reviews_1": "payload two"})
    m = map_a(doc)
    report = m.validate()
    assert report.ok and report.passed, [(f.code, f.pointer) for f in report.errors]
    (ac,) = m.of_kind("activity")
    fixtures = [f["id"] for f in m.of_kind("fixture")]
    assert ac["type"] == "agentdojo:load_environment" and ac["actor"] == "bench" and ac["scope"] == "run"
    assert ac["inputs"] == fixtures == ["fx0", "fx1"] and ac["unk"] == {"/t": "not_recorded"}
    # AgentDyn's code is not verified (D-24): the twin, class I, on the record and on each input
    assert ac["ev"] == "I" and set(ac["evf"].values()) == {"I"}
    assert "agentdojo.environment_loaded_with_injections_unverified@1#/inputs/1" in ac["rule"]
    prov = _prov(m, tmp_path)
    statements = [(sec, body) for bundle in prov["bundle"].values() for sec, items in bundle.items()
                  if isinstance(items, dict) for body in items.values() if isinstance(body, dict)]
    used = {body.get("prov:entity") for sec, body in statements if sec == "used" and body.get("prov:activity") == "x:ac0"}
    assert used == {"x:fx0", "x:fx1"}
    assert any(sec == "wasAssociatedWith" and body.get("prov:activity") == "x:ac0" and body.get("prov:agent") == "x:bench"
               for sec, body in statements)


def test_no_fixture_no_activity():
    m = map_a(a_log(injections={}, attack_type=None, injection_task_id=None))
    assert m.of_kind("activity") == []
