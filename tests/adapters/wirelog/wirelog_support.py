"""Helpers for the ``wirelog`` adapter tests (imported as ``wirelog_support``; not collected).

The committed fixtures (tests/fixtures/wirelog/, chosen by criterion and copied byte-identically from the pinned zip in
memory; SOURCE.json lists each member's label, CRC-32, size, method and sha256, CRITERIA.json the run directory of each
criterion) sit at their member labels below ``zip/``. The files hold prompt-injection payloads by design: they are data,
and no helper prints their content.

* :func:`map_run` maps one run the way the import pipeline's ``map`` job does (the reader's ``auxiliary_for`` plan over
  the fixture listing, ``map_artefact_total`` with the auxiliary rows), each artefact under a ``member`` origin (D-154
  method), returning the sealed AER and its SEM and PROV;
* :func:`modified` maps a run whose request log, response log or auxiliary bytes a test changed (derived inputs for
  cases the snapshot does not hold).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from agentprov.adapters.runner import MapOutcome, aer_bytes, map_artefact_total
from agentprov.adapters.runner.importer import _AuxListing, aux_media
from agentprov.adapters.semantics_profiles import load_semantics_profile
from agentprov.adapters.types import Origin
from agentprov.adapters.wirelog.dialect import WireLogReader
from agentprov.aer.reader import AerDocument, load_aer_bytes
from agentprov.io.canonical import sha256_hex

REPO = Path(__file__).resolve().parents[3]
FIXTURES = REPO / "tests" / "fixtures" / "wirelog"
PROFILE = "what-surrounds"
ZIP_SHA256 = "08e60afd5ba0c0c044afd005c015cbc539428255240f1ea2a555feb800079454"


@cache
def criteria() -> dict[str, str]:
    return dict(json.loads((FIXTURES / "CRITERIA.json").read_text(encoding="utf-8")))


class _Criteria(Mapping[str, str]):
    def __getitem__(self, key: str) -> str:
        return criteria()[key]

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(criteria())

    def __len__(self) -> int:
        return len(criteria())


#: Fixture criterion -> run directory (docs/reports/phase10m/README.md; tools: the phase-10m scratch scripts).
F = _Criteria()


@cache
def source_entries() -> tuple[dict[str, Any], ...]:
    return tuple(json.loads((FIXTURES / "SOURCE.json").read_text(encoding="utf-8")))


def entry(label: str) -> dict[str, Any]:
    return next(e for e in source_entries() if e["label"] == label)


def member_bytes(label: str) -> bytes:
    return (FIXTURES / "zip" / label).read_bytes()


def label_of(criterion: str, name: str = "response_raw.json") -> str:
    return f"runs_named/{F[criterion]}/{name}"


def origin(label: str, data: bytes) -> Origin:
    import zlib

    method = entry(label)["method"] if any(e["label"] == label for e in source_entries()) else 8
    return Origin.member(ZIP_SHA256, label, method, zlib.crc32(data), len(data))


@dataclass
class Mapped:
    label: str
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


def map_label(label: str, *, data: bytes | None = None, aux: Mapping[str, bytes | None] | None = None, sem: bool = False,
              prov: bool = False) -> Mapped:
    """Map one response log as the import pipeline's ``map`` job would (auxiliary rows from the reader's plan).

    ``aux`` replaces (bytes) or removes (``None``) auxiliary members by role."""
    labels = [e["label"] for e in source_entries()]
    plan = WireLogReader().auxiliary_for(label, _AuxListing(labels, {}))
    rows: list[dict[str, Any]] = []
    blobs: dict[str, bytes] = {}
    for role, ref in sorted(plan.items()):
        raw = member_bytes(ref)
        if aux is not None and role in aux:
            replaced = aux[role]
            if replaced is None:
                continue
            raw = replaced
        rows.append({"role": role, "label": ref, "media": aux_media(ref), "sha256": sha256_hex(raw), "size": len(raw),
                     "origin": origin(ref, raw).to_json()})
        blobs[role] = raw
    primary = member_bytes(label) if data is None else data
    outcome, _unit = map_artefact_total(primary, origin(label, primary), profile_id=PROFILE, auxiliary=rows,
                                        auxiliary_bytes=blobs)
    sealed, _info = aer_bytes(outcome)
    doc = load_aer_bytes(sealed)
    result = Mapped(label, outcome, sealed, doc)
    if sem or prov:
        from agentprov.sem.engine import annotate

        profile = load_semantics_profile("wirelog.tools", 1)
        result.sem = annotate(doc, profile)
        if prov:
            from agentprov.prov.engine import derive

            result.prov = derive(doc, [result.sem], sem_profiles={(profile.id, profile.version): profile})
    return result


def map_run(criterion: str, *, sem: bool = False, prov: bool = False) -> Mapped:
    return map_label(label_of(criterion), sem=sem, prov=prov)


def _compact(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":")).encode("ascii")


def modified(criterion: str, *, requests: Callable[[list[Any]], None] | None = None,
             responses: Callable[[list[Any]], None] | None = None, meta: Callable[[dict[str, Any]], None] | None = None,
             aux: Mapping[str, bytes | None] | None = None, sem: bool = False, prov: bool = False) -> Mapped:
    """Map a derived run: the fixture's logs with the changes applied (compact re-serialisation, never written to disk)."""
    label = label_of(criterion)
    data = None
    changed: dict[str, bytes | None] = dict(aux or {})
    if requests is not None:
        value = json.loads(member_bytes(label_of(criterion, "request.json")))
        requests(value)
        changed["request"] = _compact(value)
    if responses is not None:
        value = json.loads(member_bytes(label))
        responses(value)
        data = _compact(value)
    if meta is not None:
        value = json.loads(member_bytes(label_of(criterion, "meta.json")))
        meta(value)
        changed["meta"] = _compact(value)
    return map_label(label, data=data, aux=changed, sem=sem, prov=prov)
