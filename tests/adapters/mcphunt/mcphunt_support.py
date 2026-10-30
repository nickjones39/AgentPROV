"""Helpers for the ``mcphunt`` adapter tests (imported as ``mcphunt_support``; not collected).

The committed fixtures (tests/fixtures/mcphunt/) are documents with the source's envelope and traces copied byte for byte
from their element slices of the pinned documents, chosen by criterion among traces that are canary-free by evidence
(no canary flag, no taint read or fragment match, no credential or password shape; docs/reports/phase10m/ part B).
SOURCE.json lists each element's source file, digest, index, offset, length and sha256; CRITERIA.json the fixture
document and index of each criterion.

* :func:`map_trace` maps one fixture trace as the runner's streaming job does (D-323): the reader's ``parse_stream``
  yields one item per trace, each mapped by ``map_unit`` and sealed (end to end: ``test_streaming_import.py``);
* :func:`modified` maps a derived trace (a changed copy, never written to disk).
"""

from __future__ import annotations

import copy
import hashlib
import io
import json
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from agentprov.adapters.mcphunt.dialect import McpHuntReader
from agentprov.adapters.mcphunt.mapper import McpHuntMapper
from agentprov.adapters.profiles import load_profile
from agentprov.adapters.runner import MapOutcome, aer_bytes, map_unit
from agentprov.adapters.semantics_profiles import load_semantics_profile
from agentprov.adapters.types import ArtefactRef, ExecutionUnit, LocatedItem, Origin
from agentprov.aer.reader import AerDocument, load_aer_bytes
from agentprov.ingest.limits import IngestLimits

REPO = Path(__file__).resolve().parents[3]
FIXTURES = REPO / "tests" / "fixtures" / "mcphunt"
PROFILE = "mcphunt"
REVISION = "c4c69322bf9ed7690f5265577365709dad5dd454"


@cache
def criteria() -> dict[str, dict[str, Any]]:
    return dict(json.loads((FIXTURES / "CRITERIA.json").read_text(encoding="utf-8")))


F = criteria  # criterion -> {fixture_file, index}


@cache
def source() -> dict[str, Any]:
    return dict(json.loads((FIXTURES / "SOURCE.json").read_text(encoding="utf-8")))


def limits() -> IngestLimits:
    """The effective limits of an import under the profile: its ``[import] limits`` raise (D-323, RB-2)."""
    from agentprov.ingest.profile_limits import apply_profile_limits

    return apply_profile_limits(IngestLimits(), load_profile(PROFILE).data["import"]["limits"])


def items(fixture_file: str, data: bytes | None = None) -> list[LocatedItem]:
    raw = (FIXTURES / fixture_file).read_bytes() if data is None else data
    rel = fixture_file.removeprefix("docs/")
    origin = Origin.from_json({"kind": "hf", "repo": "lihaonan0716/mcphunt-agent-traces", "revision": REVISION, "path": rel})
    artefact = ArtefactRef(id="a0", sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw), media="application/json",
                           origin=origin, role="primary", prov_primary="native")
    return list(McpHuntReader().parse_stream(io.BytesIO(raw), artefact, limits=limits()))


@dataclass
class Mapped:
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

    def checks(self) -> dict[str, dict[str, Any]]:
        return {c["id"]: c for c in self.doc.seal["accounting"]["checks"]}

    def get(self, rid: str) -> dict[str, Any]:
        found = self.doc.get(rid)
        assert found is not None, rid
        return found

    def of(self, kind: str) -> list[dict[str, Any]]:
        return self.doc.of_kind(kind)

    def annotations(self, type_: str | None = None) -> list[dict[str, Any]]:
        assert self.sem is not None
        return [a for a in self.sem.annotations if type_ is None or a["type"] == type_]


def map_item(item: LocatedItem, *, sem: bool = False, prov: bool = False) -> Mapped:
    outcome = map_unit(ExecutionUnit(primary=item), McpHuntMapper(), load_profile(PROFILE))
    sealed, _info = aer_bytes(outcome)
    doc = load_aer_bytes(sealed)
    result = Mapped(outcome, sealed, doc)
    if sem or prov:
        from agentprov.sem.engine import annotate

        profile = load_semantics_profile("mcphunt.tools", SEM_VERSION)
        result.sem = annotate(doc, profile)
        if prov:
            from agentprov.prov.engine import derive

            result.prov = derive(doc, [result.sem], sem_profiles={(profile.id, profile.version): profile})
    return result


def map_trace(criterion: str, *, sem: bool = False, prov: bool = False) -> Mapped:
    spec = criteria()[criterion]
    return map_item(items(spec["fixture_file"])[spec["index"]], sem=sem, prov=prov)


def modified(criterion: str, change: Callable[[dict[str, Any]], None], *, sem: bool = False, prov: bool = False) -> Mapped:
    """Map a derived trace: the fixture trace's view with ``change`` applied to a deep copy of the trace."""
    spec = criteria()[criterion]
    item = items(spec["fixture_file"])[spec["index"]]
    value = copy.deepcopy(item.value)
    change(value["trace"])
    derived = LocatedItem(artefact=item.artefact, locator=item.locator, dialect=item.dialect, variant=item.variant,
                          flags=item.flags, value=value)
    return map_item(derived, sem=sem, prov=prov)

#: The semantics profile version the current profile selects (D-31 bump with regen items 38-41; @1 reads catalogue v1).
SEM_VERSION = 2
