"""The safety-net detector ``payload_not_reaching_agent`` over real mapped AERs and their real SEM (D.15.3; analysis B5).

The AER comes from the AgentDojo mapper (synthetic logs, as the other mapper tests build them) and the SEM from the shipped
profile ``agentdojo.suites@1``; the detector reads the SEM markers only and never alters a record.
"""

from __future__ import annotations

import copy
from typing import Any

import agentdojo_support as ads

from agentprov.adapters.semantics_profiles import load_semantics_profile
from agentprov.aer.reader import load_aer_bytes
from agentprov.artefacts import discover_catalogues, scan
from agentprov.sem.engine import annotate

DETECTOR = "artefact.generic.payload_not_reaching_agent"


def _records(doc: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    aer = load_aer_bytes(ads.map_log(doc).data)
    sem = annotate(aer, load_semantics_profile("agentdojo.suites", 1))
    return [*aer.records, aer.seal], list(sem.records)


def _hits(doc: dict[str, Any]) -> list[Any]:
    aer, sem = _records(doc)
    before = copy.deepcopy((aer, sem))
    found = [f for f in scan(aer, discover_catalogues(), sem_records=sem) if f.detector == DETECTOR]
    assert (aer, sem) == before  # reports, never alters
    return found


def _with_tool_text(text: str) -> dict[str, Any]:
    doc = ads.new_log()
    doc["messages"][3]["content"] = text
    return doc


def test_an_attacked_run_whose_tool_results_hold_no_payload_is_reported():
    (hit,) = _hits(ads.new_log())
    assert hit.variant == "absent" and hit.n == 1
    assert hit.ids == ("exec",)
    # the shipped catalogue (B4) claims it for the agentdojo-upstream profile: flag only
    assert hit.entries == ("agentdojo.art.payload_not_reaching_agent",) and hit.handling == ("FO",)


def test_a_run_that_surfaces_one_payload_is_not_reported():
    assert _hits(_with_tool_text("balance 100 payload A end")) == []


def test_a_benign_run_is_not_reported():
    doc = ads.new_log(attack_type=None, injection_task_id=None, injections={})
    assert _hits(doc) == []


def test_an_attacked_run_with_no_recorded_payload_is_no_marker():
    (hit,) = _hits(ads.new_log(injections={}))
    assert hit.variant == "no_marker"
