"""Regeneration-batch items 22 and 23 (phase 10l routed edits, user-approved 2026-10-13): the TraceLogger mapper
dispatches the DRIFT variants to the DRIFT build (RT-1), and the SEM tool label of a tool output that DRIFT's isolation
pass forwarded is its execution's tool (RT-3, D-274). Uses the phase-10l DRIFT fixtures through ``test_drift``."""

from __future__ import annotations

import hashlib

import test_drift as drift
from agentprov.adapters.agentdojo.dialect import TraceLoggerReader
from agentprov.adapters.agentdojo.drift_mapper import DRIFT_VARIANTS
from agentprov.adapters.agentdojo.mapper import TraceLoggerMapper
from agentprov.adapters.agentdojo.semantics.suites import R_REDACTED, R_UNKNOWN_TOOL
from agentprov.adapters.profiles import load_profile
from agentprov.adapters.runner import aer_bytes, map_unit
from agentprov.adapters.semantics_profiles import load_semantics_profile
from agentprov.adapters.types import ArtefactRef, ExecutionUnit, Origin
from agentprov.aer.reader import load_aer_bytes
from agentprov.ingest.limits import IngestLimits
from agentprov.testing import golden


def _via_tracelogger(raw: bytes, path: str) -> bytes:
    """``drift.map_drift`` with the dialect's own mapper instead of ``DriftMapper``."""
    reader, mapper, limits = TraceLoggerReader(), TraceLoggerMapper(), IngestLimits()
    sniff = reader.sniff(raw, label=path, limits=limits)
    origin = Origin.git(drift.DRIFT_REPO, drift.HEAD, path, golden.git_blob_sha1(raw))
    artefact = ArtefactRef("a0", hashlib.sha256(raw).hexdigest(), len(raw), "application/json", origin, "primary",
                           mapper.prov_primary(sniff.flags))  # type: ignore[arg-type]
    item = next(reader.parse(raw, artefact, limits=limits))
    data, _info = aer_bytes(map_unit(ExecutionUnit(item), mapper, load_profile("drift")))
    return data


def test_the_tracelogger_mapper_dispatches_drift_to_the_drift_build():
    assert {v for _d, v in TraceLoggerMapper.accepts} >= DRIFT_VARIANTS
    for entry in drift._entries():
        raw = drift._raw(entry)
        assert _via_tracelogger(raw, entry["original_path"]) == drift.map_drift(raw, entry["original_path"]).data


def test_an_isolated_tool_output_keeps_its_tools_label_without_the_redaction_rule():
    semantics = load_semantics_profile("agentdojo.suites", 2)
    labelled = 0
    for entry in drift._entries():
        doc = load_aer_bytes(drift.map_drift(drift._raw(entry), entry["original_path"]).data)
        isolated = {r["id"] for r in doc.records if r.get("k") == "decision" and r.get("subtype") == "drift.isolation_pass"
                    and (doc.get(r.get("subject")) or {}).get("k") == "tool_execution"}
        targets = {f"{r['id']}#0" for r in doc.records if r.get("k") == "message" and r.get("generated_by") in isolated}
        for ann in semantics.annotate(doc):
            if ann.type == "integrity" and ann.target in targets:
                rules = {r.split("#", 1)[0] for r in ann.rule}
                assert R_REDACTED not in rules
                if R_UNKNOWN_TOOL not in rules:
                    labelled += 1
                    assert ann.value != "unknown"
    assert labelled > 0
