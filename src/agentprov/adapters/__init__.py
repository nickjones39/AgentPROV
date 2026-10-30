"""The adapter model (docs/architecture D.1-D.3; MN M.1.2): protocols, core types, profiles, the runner and the registry.

This package re-exports the protocols and core types only; it imports no adapter family (D.2.1). Families live in
sub-packages (``adprov``; ``agentdojo`` and ``inspect`` arrive with their importers) and are reached through the
registry's lazy factory strings.
"""

from __future__ import annotations

from agentprov.adapters.protocols import AerRecord, Mapper, MappingContext, Reader, SourceTree
from agentprov.adapters.types import (
    ArtefactRef,
    CandidateArtefact,
    ExecutionUnit,
    Issue,
    LocatedItem,
    Locator,
    Origin,
    SniffResult,
)

__all__ = [
    "AerRecord",
    "ArtefactRef",
    "CandidateArtefact",
    "ExecutionUnit",
    "Issue",
    "LocatedItem",
    "Locator",
    "Mapper",
    "MappingContext",
    "Origin",
    "Reader",
    "SniffResult",
    "SourceTree",
]
