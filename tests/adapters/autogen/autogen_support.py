"""Helpers for the ``autogen`` adapter tests (imported as ``autogen_support``; not collected).

The committed fixtures (``tests/fixtures/autogen/``, byte-identical members of the pinned deposit zip, Zenodo 23025259
v1.0; ``SOURCE.json`` lists container, label, method, CRC-32, size and sha256) are the InjecAgent tool-block arm
(``results/phase6/tool/``: runs, events and guard log), the InjecAgent case file, ``config.json``, the phase-0 capture and
the deposit's licence texts. The phases that need the probe set are tested against the staged deposit zip when it is
present (``STAGED``, user-approved phase-10e download), and skipped otherwise. The files hold injection passages by
design: they are data, and no helper prints their content.

Rows are mapped the way the row-unit capability will map them (D-301): one ``ExecutionUnit`` per run row with a line
locator, the reader's ``auxiliary_for`` inputs under ``member`` origins, :func:`map_unit`, sealing and loading.
"""

from __future__ import annotations

import hashlib
import io
import json
import zlib
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from agentprov.adapters.autogen.dialect import AutoGenRunsReader
from agentprov.adapters.autogen.mapper import AutoGenMapper
from agentprov.adapters.profiles import load_profile
from agentprov.adapters.runner import MapOutcome, aer_bytes, map_unit
from agentprov.adapters.types import ArtefactRef, ExecutionUnit
from agentprov.aer.reader import AerDocument, load_aer_bytes
from agentprov.ingest.archives import iter_zip_members, open_zip
from agentprov.ingest.limits import IngestLimits
from agentprov.raw.origins import Origin

REPO = Path(__file__).resolve().parents[3]
FIXTURES = REPO / "tests" / "fixtures" / "autogen"
STAGED = Path.home() / ".agentprov" / "staging" / "10e" / "zenodo_23025259" / "autogen-guard-placement-data-code-v1.0.zip"
PROFILE = "autogen-guard-placement"
ZIP_SHA256 = "af2f519347c9554ba0857cc4ca989c17e45588bc421b1af990971540bd9f7b63"
ROOT = "autogen-guard-placement/"
TOOL_ARM = ROOT + "results/phase6/tool/runs.jsonl"


class _Listing:
    def __init__(self, labels: set[str]) -> None:
        self.labels = labels

    def siblings(self, label: str) -> tuple[str, ...]:
        head = label.rsplit("/", 1)[0] + "/"
        return tuple(sorted(x for x in self.labels if x.startswith(head) and "/" not in x[len(head):]))

    def exists(self, ref: str) -> bool:
        return ref in self.labels


@cache
def fixture_members() -> dict[str, tuple[bytes, int]]:
    """Label -> (bytes, zip method) of every committed fixture member."""
    rows = json.loads((FIXTURES / "SOURCE.json").read_text(encoding="utf-8"))
    return {r["label"]: ((FIXTURES / r["file"]).read_bytes(), int(r["method"])) for r in rows}


@cache
def staged_members() -> dict[str, tuple[bytes, int]] | None:
    """Label -> (bytes, method) of every member of the staged deposit zip, or ``None`` when it is absent or not pinned."""
    if not STAGED.is_file():
        return None
    raw = STAGED.read_bytes()
    if hashlib.sha256(raw).hexdigest() != ZIP_SHA256:
        return None
    out: dict[str, tuple[bytes, int]] = {}
    with open_zip(io.BytesIO(raw), IngestLimits(), release=False) as z:
        for m in iter_zip_members(z):
            if m.disposition == "selected" and m.label is not None:
                out[m.label] = (z.read_member(m), m.method)
    return out


def _media(label: str) -> str:
    return "application/jsonl" if label.endswith(".jsonl") else "application/json"


def _origin(label: str, data: bytes, method: int) -> Origin:
    return Origin.member(ZIP_SHA256, label, method, zlib.crc32(data), len(data))


def units(label: str, members: dict[str, tuple[bytes, int]]) -> list[tuple[ExecutionUnit, dict[str, bytes]]]:
    reader = AutoGenRunsReader()
    data, method = members[label]
    artefact = ArtefactRef(id="a0", sha256=hashlib.sha256(data).hexdigest(), bytes=len(data), media=_media(label),
                           origin=_origin(label, data, method), role="primary", prov_primary="native")
    plan = reader.auxiliary_for(label, _Listing(set(members)))
    aux: dict[str, ArtefactRef] = {}
    aux_bytes: dict[str, bytes] = {}
    for n, (role, ref) in enumerate(sorted(plan.items())):
        body, meth = members[ref]
        aux[role] = ArtefactRef(id=f"x{n}", sha256=hashlib.sha256(body).hexdigest(), bytes=len(body), media=_media(ref),
                                origin=_origin(ref, body, meth), role="supporting", prov_primary="unknown")
        aux_bytes[role] = body
    return [(ExecutionUnit(primary=item, auxiliary=aux), aux_bytes)
            for item in reader.parse(data, artefact, limits=IngestLimits())]


@dataclass
class Mapped:
    run_id: str
    line: int
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


def map_unit_of(unit: ExecutionUnit, aux: dict[str, bytes], *, sem: bool = False, prov: bool = False) -> Mapped:
    outcome = map_unit(unit, AutoGenMapper(), load_profile(PROFILE), auxiliary=aux)
    sealed, _info = aer_bytes(outcome)
    doc = load_aer_bytes(sealed)
    value = unit.primary.value
    result = Mapped(str(value.get("run_id")), int(unit.primary.locator.line or 0), outcome, sealed, doc)
    if sem or prov:
        from agentprov.adapters.semantics_profiles import load_semantics_profile
        from agentprov.sem.engine import annotate

        profile = load_semantics_profile("autogen.tools", 1)
        result.sem = annotate(doc, profile)
        if prov:
            from agentprov.prov.engine import derive

            result.prov = derive(doc, [result.sem], sem_profiles={(profile.id, profile.version): profile})
    return result


def map_file(label: str, members: dict[str, tuple[bytes, int]], *, sem: bool = False, prov: bool = False,
             run_ids: set[str] | None = None) -> dict[str, Mapped]:
    out: dict[str, Mapped] = {}
    for unit, aux in units(label, members):
        rid = str(unit.primary.value.get("run_id"))
        if run_ids is None or rid in run_ids:
            out[rid] = map_unit_of(unit, aux, sem=sem, prov=prov)
    return out
