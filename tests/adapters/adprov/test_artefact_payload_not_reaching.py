"""The safety-net detector ``payload_not_reaching_agent`` over mapped transcript/v1 AERs (D.15.3, D.15.8 item 11).

The AER comes from the adprov mapper (synthetic transcripts built in code) and the SEM from the shipped profile
``agentdojo.suites@2``, the profile the sealed adprov corpus was annotated with. The ``adprov`` catalogue must claim both
variants the release shows (``absent``: tool results compared and none held the payload; ``no_marker``: no tool result)
as flag-only, so they are no longer reported as unclassified.
"""

from __future__ import annotations

import hashlib
from typing import Any

from agentprov.adapters.semantics_profiles import load_semantics_profile
from agentprov.aer.reader import load_aer_bytes
from agentprov.artefacts import discover_catalogues, scan
from agentprov.sem.engine import annotate

DETECTOR = "artefact.generic.payload_not_reaching_agent"
ENTRY = "adprov.art.payload_not_reaching_agent"


def _hits(v1: Any, doc: dict[str, Any]) -> list[Any]:
    aer = load_aer_bytes(v1.map(v1.dump(doc)).data)
    sem = annotate(aer, load_semantics_profile("agentdojo.suites", 2))
    return [f for f in scan([*aer.records, aer.seal], discover_catalogues(), sem_records=list(sem.records))
            if f.detector == DETECTOR]


def _no_tool_call(doc: dict[str, Any]) -> dict[str, Any]:
    doc["turns"] = [doc["turns"][0], doc["turns"][1], {"role": "assistant", "text": "Done."}]
    return doc


def test_a_released_attacked_run_whose_tool_results_hold_no_payload_is_claimed(v1):
    (hit,) = _hits(v1, v1.released())
    assert (hit.variant, hit.ids, hit.n) == ("absent", ("exec",), 1)
    assert hit.classified and hit.entries == (ENTRY,) and hit.handling == ("FO",)


def test_a_released_attacked_run_with_no_tool_result_is_claimed_as_no_marker(v1):
    (hit,) = _hits(v1, _no_tool_call(v1.released()))
    assert hit.variant == "no_marker"
    assert hit.entries == (ENTRY,) and hit.handling == ("FO",)


def test_a_run_whose_tool_result_carries_the_payload_is_not_reported(v1):
    doc = v1.released()
    content = "balance 100; PAYLOAD-A (synthetic); end"
    doc["turns"][3]["content"] = content
    doc["turns"][3]["content_sha256"] = "sha256:" + hashlib.sha256(content.encode()).hexdigest()
    assert _hits(v1, doc) == []


def test_a_benign_run_is_not_reported(v1):
    assert _hits(v1, v1.released(attack_type=None, injection_task_id=None, injections={}, security=None)) == []


def test_the_converted_tree_is_claimed_by_the_same_entry(v1):
    (hit,) = _hits(v1, v1.converted())
    assert hit.variant == "absent" and hit.entries == (ENTRY,)
