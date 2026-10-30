"""Helpers for the ``openhands`` adapter tests (imported as ``openhands_support``; not collected).

The committed fixtures (tests/fixtures/openhands/, built by tools/openhands/build_fixtures.py) sit at their source paths
below ``oas/`` (sani903/OpenAgentSafety at the pin, byte-identical) and ``redcode/`` (members of the Zenodo 23168099 zips,
byte-identical, under their member labels). The files hold harmful task text and agent output by design: they are data,
and no helper prints their content.

:func:`map_label` maps one primary file the way the import pipeline's ``map`` job does (the reader's ``auxiliary_for``
plan, ``map_artefact_total`` with the auxiliary rows), returning the sealed AER and its SEM and PROV. OpenAgentSafety files
get their git origin at the pin; RedCode members their ``member`` origin (the runner does not import deposit archives
yet, D-156, but a member origin is a release-valid origin, so the AER seals).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from agentprov.adapters.openhands.dialect import OpenHandsEventsReader, parse_path
from agentprov.adapters.runner import MapOutcome, aer_bytes, map_artefact_total
from agentprov.adapters.runner.importer import _AuxListing, aux_media, git_blob_sha1
from agentprov.adapters.semantics_profiles import load_semantics_profile
from agentprov.adapters.types import Origin
from agentprov.aer.reader import AerDocument, load_aer_bytes

REPO = Path(__file__).resolve().parents[3]
FIXTURES = REPO / "tests" / "fixtures" / "openhands"
OAS_REPO = "https://github.com/sani903/OpenAgentSafety"
OAS_COMMIT = "857798ff26c4ce6e1d7911ee4d8b3f84a71184e0"
#: The semantics profile version the current profiles select (D-31 bump with D-606; @1 reads catalogue v1).
SEM_VERSION = 2


@cache
def source_entries() -> tuple[dict[str, Any], ...]:
    return tuple(json.loads((FIXTURES / "SOURCE.json").read_text(encoding="utf-8")))


def tree(source: str) -> dict[str, bytes]:
    """Source path -> bytes of every committed fixture file of ``source`` (``oas`` or ``redcode``)."""
    root = FIXTURES / source
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


@cache
def members() -> dict[str, dict[str, Any]]:
    """RedCode member label -> its ``record_locator`` (container, container_sha256, method, crc32, size)."""
    return {str(e["original_path"]): dict(e["record_locator"]) for e in source_entries() if "record_locator" in e}


def origin_for(source: str, label: str, data: bytes) -> Origin:
    if source == "oas":
        return Origin.git(OAS_REPO, OAS_COMMIT, label, git_blob_sha1(data))
    loc = members()[label]
    return Origin.member(str(loc["container_sha256"]), label, int(loc["method"]), str(loc["crc32"]), int(loc["size"]))


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


def profile_of(label: str) -> str:
    facets = parse_path(label)
    assert facets is not None, label
    return "openagentsafety" if facets.source == "oas" else "redcode-exec-openhands"


def map_label(label: str, files: Mapping[str, bytes], *, source: str, sem: bool = False, prov: bool = False,
              data: bytes | None = None) -> Mapped:
    """Map one primary file as the import pipeline's ``map`` job would (auxiliary rows from the reader's plan)."""
    reader = OpenHandsEventsReader()
    listing = _AuxListing(files, {})
    plan = reader.auxiliary_for(label, listing)
    rows: list[dict[str, Any]] = []
    blobs: dict[str, bytes] = {}
    for role, ref in sorted(plan.items()):
        raw = files[ref]
        rows.append({"role": role, "label": ref, "media": aux_media(ref), "sha256": hashlib.sha256(raw).hexdigest(),
                     "size": len(raw), "origin": origin_for(source, ref, raw).to_json()})
        blobs[role] = raw
    primary = files[label] if data is None else data
    outcome, _unit = map_artefact_total(primary, origin_for(source, label, primary), profile_id=profile_of(label),
                                        auxiliary=rows, auxiliary_bytes=blobs)
    sealed, _info = aer_bytes(outcome)
    doc = load_aer_bytes(sealed)
    result = Mapped(label, outcome, sealed, doc)
    if sem or prov:
        from agentprov.sem.engine import annotate

        profile = load_semantics_profile("openhands.tools", SEM_VERSION)
        result.sem = annotate(doc, profile)
        if prov:
            from agentprov.prov.engine import derive

            result.prov = derive(doc, [result.sem], sem_profiles={(profile.id, profile.version): profile})
    return result


#: Fixture ids -> (source, primary label); chosen by tools/openhands/build_fixtures.py.
F = {
    "O1": ("oas", "evaluation/claude-sonnet/traj_safety-gpg-block.json"),
    "O2": ("oas", "evaluation/gpt-4o/traj_safety-old-token.json"),
    "O3": ("oas", "evaluation/o3-mini/traj_safety-impersonation-leak.json"),
    "O4": ("oas", "evaluation/deepseek_r1/traj_safety-leak-wages.json"),
    "O5": ("oas", "evaluation/o3-mini/traj_safety-audit-notes.json"),
    "O7": ("oas", "evaluation/deepseek_v3/traj_safety-post-bad-message.json"),
    "O8": ("oas", "evaluation/deepseek_r1/traj_safety-memo_draft.json"),
    "R1": ("redcode", "results/OH/claude-sonnet-4-6/S1/python/trajectory/oh_8_28_py_S1-714384d9fddb2446e5.json"),
    "R2": ("redcode", "results/OH/qwen3-coder-30b-a3b/S1/bash/trajectory/oh_18_10_sh_S1-3b57f598182d19d57.json"),
    "R3": ("redcode", "results/OH/qwen3-coder-30b-a3b/S2/bash/trajectory/oh_20_14_S2-555af5a337dff8a1466d.json"),
    "R4": ("redcode", "results/OH/claude-sonnet-4-6/S2/python/trajectory/oh_4_23_S2-207ffe4102723c9c422f8.json"),
}


def map_fixture(fid: str, **kw: Any) -> Mapped:
    source, label = F[fid]
    return map_label(label, tree(source), source=source, **kw)
