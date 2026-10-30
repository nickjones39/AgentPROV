"""Reader, mapper and mapping-context protocols (docs/architecture D.2.3, D.2.4; layer L4).

These are ``typing.Protocol`` classes: a family implements them structurally and nothing here imports a family.
``Mapper.map`` yields AER records in canonical serialisation order, the ``execution`` header first and never the
``seal``; the core :class:`agentprov.aer.writer.AerWriter` checks, seals and writes them (D.2.4).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

from agentprov.adapters.types import ArtefactRef, CandidateArtefact, ExecutionUnit, LocatedItem, SniffResult

if TYPE_CHECKING:
    from agentprov.adapters.profiles import SourceProfile
    from agentprov.aer.rules import RuleRegistry
    from agentprov.ingest.limits import IngestLimits

__all__ = ["AerRecord", "Mapper", "MappingContext", "Reader", "SourceTree"]

AerRecord = Mapping[str, Any]


@runtime_checkable
class SourceTree(Protocol):
    """Read-only view of a source: the raw store or a local ``--input`` tree opened through ``agentprov.ingest.paths``."""

    def walk(self) -> Iterator[CandidateArtefact]: ...

    def open(self, label: str, *, max_bytes: int) -> bytes: ...


@runtime_checkable
class Reader(Protocol):
    dialect_id: str
    version: str
    variants: frozenset[str]
    media_types: frozenset[str]

    def iter_artefacts(self, tree: SourceTree, profile: SourceProfile) -> Iterator[CandidateArtefact]: ...

    def sniff(self, data: bytes, *, label: str, limits: IngestLimits) -> SniffResult: ...

    def parse(self, data: bytes, artefact: ArtefactRef, *, limits: IngestLimits) -> Iterator[LocatedItem]: ...


class MappingContext(Protocol):
    profile: SourceProfile
    rules: RuleRegistry
    mapping_id: str
    ex: str

    def rule(self, rule_id: str, pointer: str | None = None) -> str: ...

    def issue(
        self,
        code: str,
        *,
        ids: Sequence[str] = (),
        rule: str | None = None,
        severity: Literal["info", "warning", "error"] = "warning",
        detail: str | None = None,
    ) -> None: ...

    def check(
        self,
        check_id: str,
        *,
        scope: str,
        verdict: Literal["consistent", "inconsistent", "unverifiable"],
        observed: Mapping[str, int],
        reason: str | None = None,
    ) -> None: ...

    def open_auxiliary(self, role: str) -> bytes: ...

    def catalogue_versions(self, namespaces: Sequence[str]) -> dict[str, int]:
        """The integer versions of the named catalogues as shipped (the header's ``rules`` map, C.3.1).

        Not in D.2.4: added so that a mapper never hard-codes a catalogue version (AD-18).
        """
        ...


@runtime_checkable
class Mapper(Protocol):
    mapper_id: str
    version: str
    accepts: frozenset[tuple[str, str]]
    namespaces: Mapping[str, str]

    def map(self, unit: ExecutionUnit, ctx: MappingContext) -> Iterator[AerRecord]: ...
