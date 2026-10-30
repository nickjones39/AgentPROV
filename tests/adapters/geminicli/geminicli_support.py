"""Helpers for the ``geminicli`` adapter tests (imported as ``geminicli_support``; not collected).

The committed fixtures (tests/fixtures/geminicli/, rollout directories without their .log files, chosen by criterion and copied
byte-identically from the pinned archive in memory by ``tools/geminicli/build_fixtures.py``) sit at their member labels.
``SOURCE.json`` lists each file's container, label, CRC-32, size, sha256 and the criteria of its rollout. The files hold
manipulative text by design: they are data, and no helper prints their content.

* :func:`map_dir` maps one rollout the way the import pipeline's ``map`` job does (the reader's primary choice and
  ``auxiliary_for`` plan, ``map_artefact_total`` with the auxiliary rows), each artefact under a ``member`` origin
  (D-154 method), returning the sealed AER and its SEM and PROV;
* :func:`modified` maps a rollout whose stream events or sidecar bytes a test changed (derived inputs for cases the
  snapshot does not hold; never written to disk).
"""

from __future__ import annotations

import json
import zlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from agentprov.adapters.geminicli.dialect import STREAM, VERDICT, GeminiStreamReader
from agentprov.adapters.runner import MapOutcome, aer_bytes, map_artefact_total
from agentprov.adapters.runner.importer import _AuxListing, aux_media
from agentprov.adapters.semantics_profiles import load_semantics_profile
from agentprov.adapters.types import Origin
from agentprov.aer.reader import AerDocument, load_aer_bytes
from agentprov.io.canonical import sha256_hex

REPO = Path(__file__).resolve().parents[3]
FIXTURES = REPO / "tests" / "fixtures" / "geminicli"
PROFILE = "code-agent-misalignment-geminicli"
TAR_SHA256 = "f7186010db235cbff10f40c3c2d98208328c6836792973621382b981d0acc3cf"
MANIFEST_HEADER = "agent,model,mutation_id,elicited,timed_out,n_misaligned,elapsed_sec,exit_code,diff_bytes,run_id,source_slug"


@cache
def source_entries() -> tuple[dict[str, Any], ...]:
    return tuple(json.loads((FIXTURES / "SOURCE.json").read_text(encoding="utf-8")))


def criteria(entry: Mapping[str, Any]) -> list[str]:
    return str(entry["note"]).split("criteria ", 1)[1].split(", ")


@cache
def directories() -> dict[str, tuple[str, ...]]:
    """Rollout directory label -> its criteria (from SOURCE.json notes)."""
    out: dict[str, tuple[str, ...]] = {}
    for e in source_entries():
        out[str(e["label"]).rpartition("/")[0]] = tuple(criteria(e))
    return out


def by_criterion(name: str) -> str:
    return next(d for d, crits in sorted(directories().items()) if name in crits)


def streams() -> dict[str, str]:
    """First criterion -> rollout directory, for every rollout whose stream is non-empty."""
    out: dict[str, str] = {}
    for d, crits in sorted(directories().items()):
        if has(f"{d}/{STREAM}") and file_bytes(f"{d}/{STREAM}"):
            out[crits[0]] = d
    return out


def has(label: str) -> bool:
    return any(e["label"] == label for e in source_entries())


def file_bytes(label: str) -> bytes:
    return (FIXTURES / label).read_bytes()


def files_of(directory: str) -> dict[str, bytes]:
    return {str(e["label"]): file_bytes(str(e["label"])) for e in source_entries()
            if str(e["label"]).rpartition("/")[0] == directory}


def member_origin(label: str, data: bytes) -> Origin:
    return Origin.member(TAR_SHA256, label, 0, zlib.crc32(data), len(data))


def manifest_for(directory: str, **override: object) -> bytes:
    """A manifest.csv excerpt for one rollout, built from its verdict (the deposit's 1 MB table is not a fixture)."""
    verdict = json.loads(file_bytes(f"{directory}/{VERDICT}"))
    row = {"agent": verdict["agent"], "model": verdict["model"], "mutation_id": verdict["mutation_id"],
           "elicited": int(verdict["elicited"]), "timed_out": int(verdict["timed_out"]),
           "n_misaligned": verdict["n_misaligned"], "elapsed_sec": verdict["elapsed_sec"], "exit_code": verdict["exit_code"],
           "diff_bytes": 0, "run_id": "", "source_slug": "x"}
    row.update(override)
    return (MANIFEST_HEADER + "\r\n" + ",".join(str(row[k]) for k in MANIFEST_HEADER.split(",")) + "\r\n").encode()


@dataclass
class Mapped:
    directory: str
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

    def annotations(self, type_: str | None = None) -> list[dict[str, Any]]:
        assert self.sem is not None
        return [a for a in self.sem.annotations if type_ is None or a["type"] == type_]


def plan(directory: str, files: Mapping[str, bytes]) -> tuple[str, dict[str, str]]:
    """The reader's primary of the rollout and its auxiliary plan (as discovery does)."""
    reader = GeminiStreamReader()
    listing = _AuxListing(sorted(files), {})
    primary = f"{directory}/{STREAM}" if f"{directory}/{STREAM}" in files else f"{directory}/{VERDICT}"
    return primary, reader.auxiliary_for(primary, listing)


def map_files(directory: str, files: Mapping[str, bytes], *, sem: bool = False, prov: bool = False) -> Mapped:
    primary, aux = plan(directory, files)
    rows: list[dict[str, Any]] = []
    blobs: dict[str, bytes] = {}
    for role, ref in sorted(aux.items()):
        raw = files[ref]
        rows.append({"role": role, "label": ref, "media": aux_media(ref), "sha256": sha256_hex(raw), "size": len(raw),
                     "origin": member_origin(ref, raw).to_json()})
        blobs[role] = raw
    data = files[primary]
    outcome, _unit = map_artefact_total(data, member_origin(primary, data), profile_id=PROFILE, auxiliary=rows,
                                        auxiliary_bytes=blobs, media="application/x-ndjson")
    sealed, _info = aer_bytes(outcome)
    doc = load_aer_bytes(sealed)
    result = Mapped(directory, outcome, sealed, doc)
    if sem or prov:
        from agentprov.sem.engine import annotate

        profile = load_semantics_profile("geminicli.tools", 1)
        result.sem = annotate(doc, profile)
        if prov:
            from agentprov.prov.engine import derive

            result.prov = derive(doc, [result.sem], sem_profiles={(profile.id, profile.version): profile})
    return result


def map_dir(directory: str, *, sem: bool = False, prov: bool = False, manifest: bool = True) -> Mapped:
    """Map one committed rollout; ``manifest`` adds the rollout's manifest excerpt beside ``cells/``."""
    files = files_of(directory)
    if manifest:
        root = directory.split("/cells/", 1)[0]
        files[f"{root}/manifest.csv"] = manifest_for(directory)
    return map_files(directory, files, sem=sem, prov=prov)


def events(directory: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in file_bytes(f"{directory}/{STREAM}").split(b"\n") if line]


def jsonl(items: list[dict[str, Any]]) -> bytes:
    return b"".join(json.dumps(e, ensure_ascii=True, separators=(",", ":")).encode("ascii") + b"\n" for e in items)


def modified(criterion: str, change: Callable[[list[dict[str, Any]]], list[dict[str, Any]] | None] | None = None, *,
             aux: Mapping[str, bytes | None] | None = None, sem: bool = False, prov: bool = False) -> Mapped:
    """Map a derived rollout: the fixture's events with ``change`` applied (in place or returned), and sidecars replaced
    (``aux``: file name -> bytes, or ``None`` to drop the file). Nothing is written to disk."""
    directory = by_criterion(criterion)
    files = files_of(directory)
    root = directory.split("/cells/", 1)[0]
    files[f"{root}/manifest.csv"] = manifest_for(directory)
    if change is not None:
        items = events(directory)
        changed = change(items)
        files[f"{directory}/{STREAM}"] = jsonl(items if changed is None else changed)
    for name, data in (aux or {}).items():
        label = f"{directory}/{name}" if "/" not in name else name
        if data is None:
            files.pop(label, None)
        else:
            files[label] = data
    return map_files(directory, files, sem=sem, prov=prov)
