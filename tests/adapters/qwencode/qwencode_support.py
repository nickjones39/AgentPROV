"""Helpers for the ``qwencode`` adapter tests (imported as ``qwencode_support``; not collected).

The committed fixtures (tests/fixtures/qwencode/, chosen by criterion and copied byte-identically from the two pinned zips
in memory by ``tools/qwencode/build_fixtures.py``) sit under ``runs/<label>`` (the Qwen zip) and ``supp/<label>`` (the
supplementary zip); ``SOURCE.json`` lists each file's container, label, method, CRC-32, size, sha256 and criteria. The
files hold RedCode payloads by design: they are data, and no helper prints their content.

* :func:`map_run` maps one run the way the import pipeline's ``map`` job will once D-530 wires the supplementary zip as
  the ``supp`` context tree (the reader's plan over a listing with ``supp:<label>`` references, ``map_artefact_total``
  with the auxiliary rows), each file under a ``member`` origin;
* :func:`modified` maps a run whose messages or auxiliary bytes a test changed (derived inputs; never written to disk).
"""

from __future__ import annotations

import json
import zlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from agentprov.adapters.qwencode.dialect import SUPP_ROLE, QwenJsonReader
from agentprov.adapters.runner import MapOutcome, aer_bytes, map_artefact_total
from agentprov.adapters.runner.importer import _AuxListing, aux_media
from agentprov.adapters.semantics_profiles import load_semantics_profile
from agentprov.adapters.types import Origin
from agentprov.aer.reader import AerDocument, load_aer_bytes
from agentprov.io.canonical import sha256_hex

REPO = Path(__file__).resolve().parents[3]
FIXTURES = REPO / "tests" / "fixtures" / "qwencode"
PROFILE = "redcode-exec-qwencode"
RUNS_SHA256 = "2fd0cada13db9064d31b12224602478f75df7193d359b23344612b35c9b347dc"
SUPP_SHA256 = "96e328facb240c14da16c394290372ddbb7221d97498cea16a64bd720192ae69"


@cache
def source_entries() -> tuple[dict[str, Any], ...]:
    return tuple(json.loads((FIXTURES / "SOURCE.json").read_text(encoding="utf-8")))


def criteria(entry: Mapping[str, Any]) -> list[str]:
    note = str(entry["note"]).split("criteria ", 1)
    return [c for c in note[1].split(", ") if c] if len(note) > 1 else []


def run_entries() -> list[dict[str, Any]]:
    return [e for e in source_entries() if e["pin_role"] == "runs" and "/trajectory/qwen_" in e["label"]]


def by_criterion(name: str) -> str:
    return next(e["label"] for e in sorted(run_entries(), key=lambda e: e["label"]) if name in criteria(e))


def runs() -> dict[str, str]:
    """First criterion -> label, for every non-empty run fixture."""
    out: dict[str, str] = {}
    for e in sorted(run_entries(), key=lambda e: e["label"]):
        if e["size_bytes"] and criteria(e):
            out.setdefault(criteria(e)[0], e["label"])
    return out


def file_bytes(entry: Mapping[str, Any]) -> bytes:
    return (FIXTURES / entry["sample_file"]).read_bytes()


@cache
def tree() -> tuple[dict[str, bytes], dict[str, bytes]]:
    """(runs zip members, supplementary zip members) of the fixtures, label -> bytes."""
    runs_files, supp_files = {}, {}
    for e in source_entries():
        (runs_files if e["pin_role"] == "runs" else supp_files)[e["label"]] = file_bytes(e)
    return runs_files, supp_files


def method_of(label: str) -> int:
    return int(next(e["record_locator"]["method"] for e in source_entries() if e["label"] == label))


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

    def get(self, rid: str) -> dict[str, Any]:
        found = self.doc.get(rid)
        assert found is not None, rid
        return found

    def of(self, kind: str) -> list[dict[str, Any]]:
        return self.doc.of_kind(kind)

    def annotations(self, type_: str | None = None) -> list[dict[str, Any]]:
        assert self.sem is not None
        return [a for a in self.sem.annotations if type_ is None or a["type"] == type_]


def plan(label: str, runs_files: Mapping[str, bytes], supp_files: Mapping[str, bytes]) -> dict[str, str]:
    return QwenJsonReader().auxiliary_for(label, _AuxListing(sorted(runs_files), {SUPP_ROLE: sorted(supp_files)}))


def map_files(label: str, runs_files: Mapping[str, bytes], supp_files: Mapping[str, bytes], *, sem: bool = False,
              prov: bool = False) -> Mapped:
    rows: list[dict[str, Any]] = []
    blobs: dict[str, bytes] = {}
    for role, ref in sorted(plan(label, runs_files, supp_files).items()):
        if ref.startswith(SUPP_ROLE + ":"):
            member = ref.split(":", 1)[1]
            raw, container = supp_files[member], SUPP_SHA256
        else:
            member, raw, container = ref, runs_files[ref], RUNS_SHA256
        origin = Origin.member(container, member, method_of(member) if member in tree()[0] or member in tree()[1] else 8,
                               zlib.crc32(raw), len(raw))
        rows.append({"role": role, "label": ref, "media": aux_media(ref), "sha256": sha256_hex(raw), "size": len(raw),
                     "origin": origin.to_json()})
        blobs[role] = raw
    data = runs_files[label]
    outcome, _unit = map_artefact_total(data, Origin.member(RUNS_SHA256, label, method_of(label), zlib.crc32(data), len(data)),
                                        profile_id=PROFILE, auxiliary=rows, auxiliary_bytes=blobs)
    sealed, _info = aer_bytes(outcome)
    doc = load_aer_bytes(sealed)
    result = Mapped(label, outcome, sealed, doc)
    if sem or prov:
        from agentprov.sem.engine import annotate

        profile = load_semantics_profile("qwencode.tools", 2)
        result.sem = annotate(doc, profile)
        if prov:
            from agentprov.prov.engine import derive

            result.prov = derive(doc, [result.sem], sem_profiles={(profile.id, profile.version): profile})
    return result


def map_run(label: str, *, sem: bool = False, prov: bool = False) -> Mapped:
    runs_files, supp_files = tree()
    return map_files(label, runs_files, supp_files, sem=sem, prov=prov)


def messages(label: str) -> list[dict[str, Any]]:
    return json.loads(tree()[0][label])


def modified(criterion: str, change: Callable[[list[dict[str, Any]]], list[dict[str, Any]] | None] | None = None, *,
             supp: Mapping[str, bytes | None] | None = None, sem: bool = False, prov: bool = False) -> Mapped:
    """Map a derived run: the fixture's messages with ``change`` applied, and supplementary files replaced (label ->
    bytes) or dropped (``None``). Nothing is written to disk."""
    label = by_criterion(criterion)
    runs_files, supp_files = dict(tree()[0]), dict(tree()[1])
    if change is not None:
        items = messages(label)
        changed = change(items)
        runs_files[label] = json.dumps(items if changed is None else changed, ensure_ascii=True).encode("ascii")
    for member, data in (supp or {}).items():
        if data is None:
            supp_files.pop(member, None)
        else:
            supp_files[member] = data
    return map_files(label, runs_files, supp_files, sem=sem, prov=prov)
