"""Core data types of the adapter model (docs/architecture D.2.2; layer L4).

Frozen dataclasses mirroring C's contract (C.3.12, C.9). Where D.2.2 spells something differently from C, C prevails
(D.2.2 preamble): the origin of a raw artefact is the one C.3.12 :class:`~agentprov.raw.origins.Origin` (all eight kinds,
including ``corpus``), re-exported here, and an artefact serialises to the header's ``artifacts[]`` item through
:meth:`ArtefactRef.to_json`.

``Issue`` is the one adapter issue type of :mod:`agentprov.errors` (D.2.7), re-exported.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from agentprov.aer.types import Json
from agentprov.errors import Issue
from agentprov.raw.origins import Origin

__all__ = [
    "ArtefactRef",
    "CandidateArtefact",
    "EvidenceClass",
    "ExecutionUnit",
    "Issue",
    "Json",
    "LocatedItem",
    "Locator",
    "Origin",
    "Rejected",
    "SniffResult",
    "UnkReason",
]

EvidenceClass = Literal["O", "D", "I"]
UnkReason = Literal["not_recorded", "lost", "overwritten", "withheld", "ambiguous", "not_captured", "not_applicable"]


@dataclass(frozen=True, slots=True)
class ArtefactRef:
    """One entry of the AER header's ``artifacts[]`` (C.3.12 Artefact)."""

    id: str  # "a<n>"
    sha256: str  # lower-case hex of the raw bytes
    bytes: int
    media: str
    origin: Origin
    role: Literal["primary", "capture_log", "native_log", "supporting"] = "primary"
    prov_primary: Literal["native", "byte_derived", "secondary", "unknown"] = "unknown"  # R-22; fail closed

    def to_json(self) -> dict[str, Json]:
        origin: dict[str, Json] = dict(self.origin.to_json())
        return {
            "bytes": self.bytes,
            "id": self.id,
            "media": self.media,
            "origin": origin,
            "prov_primary": self.prov_primary,
            "role": self.role,
            "sha256": self.sha256,
        }


@dataclass(frozen=True, slots=True)
class Locator:
    """C's locator (C.9.1). The canonical key form is computed only by :mod:`agentprov.aer.ids`."""

    a: str | None = None
    p: str | None = None
    line: int | None = None
    bytes: tuple[int, int] | None = None
    o: str | None = None
    blob: str | None = None

    def key(self) -> dict[str, Json]:
        """The locator without ``a`` (the ``source_key.loc`` input; validated by ``aer.ids.canonical_key_loc``)."""
        out: dict[str, Json] = {}
        if self.p is not None:
            out["p"] = self.p
        if self.line is not None:
            out["line"] = self.line
        if self.bytes is not None and self.p is None and self.line is None:
            out["bytes"] = [self.bytes[0], self.bytes[1]]
        return out

    @classmethod
    def from_key(cls, loc: Mapping[str, Any], *, a: str | None = None) -> Locator:
        """The inverse of :meth:`key` (``a`` given separately): ``p``, ``line`` or ``bytes`` of a key locator."""
        span = loc.get("bytes")
        line = loc.get("line")
        return cls(a=a, p=None if loc.get("p") is None else str(loc["p"]), line=None if line is None else int(line),
                   bytes=None if span is None else (int(span[0]), int(span[1])))


@dataclass(frozen=True, slots=True)
class SniffResult:
    match: bool
    dialect: str | None = None
    variant: str | None = None
    flags: frozenset[str] = frozenset()
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CandidateArtefact:
    label: str  # NFC logical name relative to the source root (G.3.6); never a path to open
    size: int
    origin: Origin


@dataclass(frozen=True, slots=True)
class LocatedItem:
    artefact: ArtefactRef
    locator: Locator
    dialect: str
    variant: str
    flags: frozenset[str]
    value: Any  # from agentprov.ingest.loaders.strict_json_loads: untrusted data, source member order kept
    reader_issues: tuple[Issue, ...] = ()


@dataclass(frozen=True, slots=True)
class Rejected:
    """A row of a ``multi_execution`` file that is not an execution (D-321): the reader's ``rejected`` yields one per row
    its ``parse`` does not, so the two partition the file. ``code`` is ``select.not_execution_artefact`` or
    ``select.out_of_scope``; ``detail`` is the reader's generated register detail (never source content)."""

    locator: Locator
    code: str
    detail: str


@dataclass(frozen=True, slots=True)
class ExecutionUnit:
    primary: LocatedItem
    auxiliary: Mapping[str, ArtefactRef] = field(default_factory=dict)
    mode: Literal["import", "live"] = "import"
    ex: str | None = None
