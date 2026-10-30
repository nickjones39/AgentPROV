"""Semantics profiles of the AgentDojo adapter family (docs/architecture C.14.1; D.1 "Semantics profile").

The profile ``agentdojo.suites`` at version 1 is the data directory ``agentdojo.suites-1/`` beside this package and the
code in :mod:`.suites` (tables, selection, labels, outcomes) and :mod:`.markers` (the injection-marker normalisers).
:func:`agentprov.adapters.semantics_profiles.load_semantics_profile` finds the directory by convention, reads its files and calls
:func:`build_profile`; nothing here reads a corpus copy (AD-14).
"""

from __future__ import annotations

from collections.abc import Mapping

from agentprov.sem.types import SemanticsProfile

__all__ = ["build_profile"]


def build_profile(profile_id: str, version: int, files: Mapping[str, bytes], sha256: str) -> SemanticsProfile:
    """Build the semantics profile ``profile_id`` at ``version`` from its data ``files`` and their digest ``sha256``."""
    from agentprov.adapters.agentdojo.semantics.suites import build

    return build(profile_id, version, files, sha256)
