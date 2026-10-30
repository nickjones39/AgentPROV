"""Helpers for the ``credleak`` adapter tests (imported as ``credleak_support``; not collected).

The committed fixtures (tests/fixtures/credleak/cells/, built by tools/credleak/build_fixtures.py) are run cells of
Zenodo 22737462 v3 that carry none of the study's planted credentials. They are unedited except three cells whose ``ls -l``
owner and group columns named a third-party account, replaced by ``user`` padded to the column width (fixture scrub
2026-10-21; SOURCE.json ``modified`` and ``derived_from``). They hold prompt-injection payloads by design
(the poisoned files, pages and rules the study planted): they are data, and no helper prints their content.

* :func:`map_cell` maps every run of one cell the way the mapper is run per unit (``map_unit``), sealing each AER through
  the writer's checks and deriving its SEM and PROV;
* :func:`synthetic_cell` builds a cell at test time (never committed) from a fixture's shape, optionally carrying
  test-made sentinel values for the withholding tests (assembled at run time; never printed).
"""

from __future__ import annotations

import hashlib
import json
import zlib
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from agentprov.adapters.credleak.dialect import CredleakCellReader
from agentprov.adapters.credleak.mapper import CredleakMapper
from agentprov.adapters.profiles import load_profile
from agentprov.adapters.runner import MapOutcome, aer_bytes, map_unit
from agentprov.adapters.semantics_profiles import load_semantics_profile
from agentprov.adapters.types import ArtefactRef, ExecutionUnit, Origin
from agentprov.aer.reader import AerDocument, load_aer_bytes
from agentprov.ingest.limits import IngestLimits

REPO = Path(__file__).resolve().parents[3]
FIXTURES = REPO / "tests" / "fixtures" / "credleak"
PROFILE = "credleak-p15b"
PREFIX = "p15b-run-data/"
#: A stand-in container digest for the member origins of mapped fixtures (the tests map members, not the pinned zip).
CONTAINER = "0" * 64


@cache
def source_entries() -> tuple[dict[str, Any], ...]:
    return tuple(json.loads((FIXTURES / "SOURCE.json").read_text(encoding="utf-8")))


def by_criterion(criterion: str) -> dict[str, Any]:
    return next(e for e in source_entries() if criterion in e["criteria"])


def cell_bytes(entry: dict[str, Any]) -> bytes:
    return (FIXTURES / entry["path"]).read_bytes()


def member_origin(label: str, data: bytes) -> Origin:
    return Origin.member(CONTAINER, label, 8, zlib.crc32(data) & 0xFFFFFFFF, len(data))


@dataclass
class Mapped:
    label: str
    index: int
    outcome: MapOutcome
    data: bytes
    doc: AerDocument
    sem: Any = None
    prov: Any = None

    @property
    def records(self) -> list[dict[str, Any]]:
        return self.doc.records

    @property
    def header(self) -> dict[str, Any]:
        return self.doc.header

    @property
    def issues(self) -> list[dict[str, Any]]:
        return list(self.doc.seal.get("issues", []))

    def codes(self) -> list[str]:
        return [i["code"] for i in self.issues]

    def get(self, rid: str) -> dict[str, Any]:
        found = self.doc.get(rid)
        assert found is not None, rid
        return found

    def of(self, kind: str) -> list[dict[str, Any]]:
        return self.doc.of_kind(kind)


#: The semantics profile version each source-profile version selects (D-605: profile 2 reads credleak.tools@2).
SEMANTICS_OF = {1: 1, 2: 2}


def map_cell(label: str, data: bytes, *, sem: bool = True, prov: bool = True, origin: Origin | None = None,
             profile_version: int | None = None) -> list[Mapped]:
    """Map every run of one cell (one ``map_unit`` per located item), seal each AER and derive SEM and PROV. The current
    profile unless ``profile_version`` names an archived one (D-31)."""
    profile = load_profile(PROFILE, profile_version)
    reader, mapper = CredleakCellReader(), CredleakMapper()
    origin = origin or member_origin(label, data)
    artefact = ArtefactRef(id="a0", sha256=hashlib.sha256(data).hexdigest(), bytes=len(data), media="application/json",
                           origin=origin, role="primary", prov_primary="native")
    out: list[Mapped] = []
    semantics = load_semantics_profile("credleak.tools", SEMANTICS_OF[profile.version])
    for item in reader.parse(data, artefact, limits=IngestLimits()):
        outcome = map_unit(ExecutionUnit(primary=item), mapper, profile)
        sealed, _info = aer_bytes(outcome)
        doc = load_aer_bytes(sealed)
        index = int(str(item.locator.p).rsplit("/", 1)[-1])
        result = Mapped(label, index, outcome, sealed, doc)
        if sem or prov:
            from agentprov.sem.engine import annotate

            result.sem = annotate(doc, semantics)
            if prov:
                from agentprov.prov.engine import derive

                result.prov = derive(doc, [result.sem], sem_profiles={(semantics.id, semantics.version): semantics})
        out.append(result)
    return out


def map_entry(entry: dict[str, Any], **kwargs: Any) -> list[Mapped]:
    return map_cell(entry["label"], cell_bytes(entry), **kwargs)


# ------------------------------------------------------------------------------------------------ synthetic cells
def sentinel(kind: str) -> str:
    """A test-made value of a planted-credential shape, assembled at run time (never a real or deposited value)."""
    digits = "".join(str((7 * i + 3) % 10) for i in range(24))
    if kind == "tag":
        return "test-" + "CAN" + "ARY" + "-sentinel-" + digits[:8]
    if kind == "aws":
        return "AK" + "IA" + "TESTSENTINEL" + digits[:4]
    if kind == "sk":
        return "s" + "k-" + "testsentinel" + digits
    raise ValueError(kind)


def synthetic_cell(*, output: str = "ok", runs: int = 1, model: str = "test-model", scenario: str = "TX.1",
                   technique: str = "TX", turns: list[dict[str, Any]] | None = None, **run_fields: Any) -> bytes:
    """A cell built at test time (never committed) in the deposit's shape, with one tool call whose output is ``output``."""
    turn = {"turnNumber": 0, "userMessage": "do the task", "assistantResponse": "done",
            "toolCalls": [{"tool": "Read", "input": {"file_path": "README.md"}, "output": output,
                           "canaryInInput": False, "canaryInOutput": False}],
            "timestamp": "2026-06-11T08:00:00.000Z", "canaryDetected": False, "canariesFound": []}
    run = {"model": model, "scenarioId": scenario, "scenarioName": "synthetic", "repetition": 1, "durationMs": 1000,
           "turns": turns if turns is not None else [turn], "hijackSucceeded": False, "exfiltrationDetected": False,
           "exfiltrationCount": 0, "exfiltrationPaths": [], "agentDetected": False, "displayedToUser": False, "ges": 100,
           "gesDisplayed": 100, "gesExfil": 100, "firstCanaryTurn": None, "intentVerdicts": [None]}
    run.update(run_fields)
    cell = {"config": {"maxTurns": 10, "systemPrompt": False}, "defence": "C4-baseline", "model": model,
            "runId": "2026-06-11T08-00-00-000Z", "runs": [dict(run, repetition=i + 1) for i in range(runs)],
            "scenario": scenario, "summary": {}, "technique": technique, "timestamp": "2026-06-11T09:00:00.000Z"}
    return json.dumps(cell, indent=2).encode()
