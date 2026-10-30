"""Context membership of live model calls, and live AER through SEM and PROV (docs/architecture C.13.7, D.10.4, EF
``aprov.use_context@1``; K.8.5).

* With ``input_at`` the input is O by capture, and its ``used`` statements are OBSERVED in the core bundle.
* Without it the input is the unique alignment of the decoded wire request with the pass dump under
  ``cap.context_alignment@1`` (D): DERIVED, never O; no unique alignment gives ``unk /input ambiguous``.
* Sent transforms (``role_rewrite`` under the declared ``gateway_compat`` rewrite) are declared per item.
* Live AER passes SEM ``agentdojo.suites@1`` (tier 3) and PROV derivation with tier 4 in release mode; the session also
  maps from a staging directory through :mod:`agentprov.adapters.runner.live`.
"""

from __future__ import annotations

import copy
import hashlib
import json
from functools import cache
from pathlib import Path
from typing import Any

from capture_cells import INSTRUMENTATION_GATEWAY, Cell, balance_cell, wire
from capture_support import MappedSession, c13_8_session, map_built

from agentprov.adapters.runner import aer_bytes
from agentprov.adapters.runner.live import map_session as map_staged
from agentprov.adapters.semantics_profiles import load_semantics_profile
from agentprov.aer.reader import load_aer_bytes
from agentprov.prov.engine import derive
from agentprov.sem.engine import annotate
from agentprov.sem.types import SemanticsProfile
from agentprov.sem.validate import validate_sem_document
from agentprov.validate import validate_prov


@cache
def _profile() -> SemanticsProfile:
    return load_semantics_profile("agentdojo.suites", 1)


def _derive(m: MappedSession) -> tuple[Any, Any, dict[str, Any]]:
    doc = load_aer_bytes(m.data)
    sem = annotate(doc, _profile())
    report = validate_sem_document(sem, doc, mode="release", profile=_profile())
    assert report.ok and not report.errors and not report.skipped, [f.code for f in report.errors]
    result = derive(doc, [sem], sem_profiles={("agentdojo.suites", 1): _profile()})
    again = derive(doc, [annotate(doc, _profile())], sem_profiles={("agentdojo.suites", 1): _profile()})
    assert result.prov_json == again.prov_json
    checks = validate_prov(result.prov_json, doc, sems=[sem])
    failures = [(o.id, [f.code for f in o.findings]) for o in checks.outcomes if o.status not in ("pass", "not_applicable")]
    assert checks.passed and failures == [], failures
    return doc, result, json.loads(result.prov_json)


def _context_usages(prov: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for bundle in prov.get("bundle", {}).values():
        for stmt in bundle.get("used", {}).values():
            if stmt.get("apv:rule") == "aprov.use_context@1":
                out.append(stmt)
    for stmt in prov.get("used", {}).values():
        if stmt.get("apv:rule") == "aprov.use_context@1":
            out.append(stmt)
    return out


def _class(stmt: dict[str, Any]) -> str:
    return str(stmt["apv:evidenceClass"]["$"])


# ------------------------------------------------------------------------------------------------ membership
def test_input_at_membership_is_observed_in_prov():
    m = map_built(c13_8_session())
    _doc, result, prov = _derive(m)
    usages = _context_usages(prov)
    assert len(usages) == 6 and {_class(u) for u in usages} == {"apv:Observed"}
    assert [b for b in result.bundles if b.kind == "assessment"][0].profile == "agentdojo.suites@1"


def test_missing_input_at_aligns_under_cap_rule():
    cell = Cell()
    cell.start_pass()
    cell.reply(calls=[("get_balance", {})], input_at=False)
    cell.reply(content="Your balance is 1810.0.", input_at=False, n_messages=False)
    cell.end_pass()
    cell.outcome()
    m = map_built(cell.close())
    assert m.validate().ok
    for mc in ("mc0", "mc1"):
        record = m.get(mc)
        assert record["evf"]["/input"] == "D" and "cap.context_alignment@1#/input" in record["rule"]
    assert m.get("mc1")["input"] == ["m0", "m1", "m2", "m3"]
    _doc, _result, prov = _derive(m)
    assert {_class(u) for u in _context_usages(prov)} == {"apv:Derived"}


def test_ambiguous_alignment_is_declared():
    cell = Cell()
    cell.start_pass()
    cell.messages.append(copy.deepcopy(cell.messages[1]))  # the prompt twice: the request matches two alignments
    body = [wire(cell.messages[0]), wire(cell.messages[1])]
    cell.reply(content="Hello", input_at=False, n_messages=False, wire_messages=body)
    cell.end_pass()
    m = map_built(cell.close())
    assert m.validate().ok
    mc = m.get("mc0")
    assert "input" not in mc and mc["unk"]["/input"] == "ambiguous" and "cap.context_alignment@1#/input" in mc["rule"]


def test_role_rewrite_under_gateway_compat():
    cell = Cell(instrumentation=INSTRUMENTATION_GATEWAY)
    cell.start_pass()
    body = [dict(wire(cell.messages[0]), role="system"), wire(cell.messages[1])]
    cell.reply(content="Hello", wire_messages=body)
    cell.end_pass()
    m = map_built(cell.close())
    assert m.validate().ok
    item = m.get("mc0")["input"][0]
    assert item["id"] == "m0" and item["sent"] == ["role_rewrite"] and len(item["sent_sha256"]) == 64
    # without the declared rewrite the stock system role is the recorded form: no transform
    plain = Cell()
    plain.start_pass()
    plain.reply(content="Hello", wire_messages=body)
    plain.end_pass()
    assert map_built(plain.close()).get("mc0")["input"] == ["m0", "m1"]


# ------------------------------------------------------------------------------------------------ SEM and PROV
def test_live_cells_pass_sem_prov_and_tier_4():
    multi = Cell()
    multi.start_pass()
    multi.reply(calls=[("get_balance", {})])
    multi.end_pass(aborted=True)
    multi.start_pass()
    multi.reply(calls=[("send_money", {"recipient": "X", "amount": 10.0})])
    multi.reply(content="Done.")
    multi.end_pass(env=hashlib.sha256(b"after").hexdigest(), changed=True)
    multi.outcome()
    for session in (balance_cell().close(), multi.close()):
        _derive(map_built(session))


def test_a_staged_session_maps_through_the_runner(tmp_path: Path):
    """The staging layout of C.13.1 (``raw/capture``, ``raw/blobs/sha256``), read through ingest.paths."""
    s = c13_8_session()
    root = tmp_path / s.session
    (root / "raw" / "capture").mkdir(parents=True)
    (root / "raw" / "capture" / f"{s.session}.capture.jsonl").write_bytes(s.log_bytes())
    for digest, data in s.blobs.items():
        target = root / "raw" / "blobs" / "sha256" / digest[:2] / digest
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    outcome, unit, register = map_staged(root)
    assert outcome is not None and unit is not None and register == []
    data, _info = aer_bytes(outcome)
    assert data == map_built(s).data
