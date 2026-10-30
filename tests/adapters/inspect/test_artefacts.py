"""The ``inspect`` artefact catalogue after the corpus pre-check, wave 1 (D-581, D-582; regeneration-batch item 109).

Three entries of the survey AgentHarm dossier (``docs/reports/precheck/ast-survey-agentharm.md`` PC-01 and PC-02). The
version stays 1 (D-31 owner ruling 2026-10-21: in place, no corpus records the artefact catalogue). The safety-net cases
map a synthetic ``.eval`` and scan it; failures print ids and tokens only."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import inspect_support as support
import pytest

from agentprov.aer.reader import load_aer_bytes
from agentprov.artefacts import discover_catalogues, scan
from agentprov.artefacts.catalogue import ArtefactEntry, check_references, load_catalogue

SNAPSHOT = "git:89c4db2c949797fbb38c5bfed85dc82780ddbfe3"


@pytest.fixture(scope="module")
def entries() -> dict[str, ArtefactEntry]:
    return {e.id: e for e in load_catalogue("inspect").entries}


def _rows(entry: ArtefactEntry) -> set[tuple[str, int, str, str]]:
    return {(x.snapshot, x.count, x.unit, x.status) for x in entry.expected}


def test_catalogue_validates_in_place_at_version_1():
    cat = load_catalogue("inspect")
    assert cat.version == 1 and len(cat.entries) == 21  # +9 wave-2 artefact scope (D-950)
    assert [str(p) for p in check_references(cat)] == []


def test_bundled_file_not_found(entries):
    e = entries["inspect.art.bundled_file_not_found"]
    assert (e.cause, e.detector_rule, e.detector_class, e.handling_class) == (
        "upstream_harness", "inspect.tool_error_status@1", "D", "FO")
    assert e.profiles == ("survey-agentharm",) and e.manuscript and not e.claims
    assert _rows(e) == {(SNAPSHOT, 63, "samples", "verified"), (SNAPSHOT, 84, "calls", "verified"),
                        (SNAPSHOT, 62, "calls", "verified")}


def test_the_two_generic_entries(entries):
    finish = entries["inspect.art.abnormal_finish_max_tokens"]
    assert (finish.detector_rule, finish.claims) == ("artefact.generic.abnormal_finish",
                                                      ("artefact.generic.abnormal_finish#max_tokens",))
    assert _rows(finish) == {(SNAPSHOT, 23, "executions", "verified")}
    text = entries["inspect.art.text_tool_call"]
    assert (text.detector_rule, text.claims) == ("artefact.generic.text_encoded_call",
                                                  ("artefact.generic.text_encoded_call#marker",))
    assert _rows(text) == {(SNAPSHOT, 12, "executions", "verified")}
    assert all(e.handling_class == "FO" and e.manuscript for e in (finish, text))


def _scan(tmp_path: Path, sample: dict[str, Any]) -> list[Any]:
    data = support.build_eval(support.synthetic_header(), {"s1_epoch_1.json": sample})
    (unit,) = support.import_log(data, tmp_path).units
    aer = load_aer_bytes(unit.data)
    return scan([*aer.records, aer.seal], discover_catalogues())


def _stop_at_max_tokens(_s: Any, sample: dict[str, Any]) -> None:
    last = [e for e in sample["events"] if e.get("event") == "model" and e["model"].endswith("agent:1b")][-1]
    last["output"]["choices"][0]["stop_reason"] = "max_tokens"


def test_a_max_tokens_turn_is_claimed_by_its_entry(tmp_path):
    findings = _scan(tmp_path, support.basic_sample(tune=_stop_at_max_tokens))
    hits = [f for f in findings if f.detector == "artefact.generic.abnormal_finish"]
    assert [(f.variant, f.entries, f.handling) for f in hits] == [
        ("max_tokens", ("inspect.art.abnormal_finish_max_tokens",), ("FO",))]


def test_the_file_tool_entry_claims_no_safety_net_finding(tmp_path):
    """Its detector is a mapper rule with no generic counterpart, so it claims no finding: the counts come from the
    pre-check scan, not from the net."""
    error = {"type": "file_not_found", "message": "Synthetic: file not found."}
    findings = _scan(tmp_path, support.basic_sample(tool_error=error, tune=_stop_at_max_tokens))
    assert findings  # the max_tokens turn gives the net one finding to claim
    assert all("inspect.art.bundled_file_not_found" not in f.entries for f in findings)
