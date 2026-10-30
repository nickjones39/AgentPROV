"""Semantics profiles of the DTap adapter family (docs/architecture D.16.9; C.14.1).

The profile ``dtap.tools`` at version 1 or 2 is the data directory ``dtap.tools-1/`` or ``dtap.tools-2/`` beside this
package (version 2: the same tables on the ``dtap`` catalogue version 2, D-607) and the code in :mod:`.tools`. :func:`agentprov.adapters.semantics_profiles.load_semantics_profile` finds the directory by convention,
reads its files and calls :func:`build_profile`; nothing here reads a corpus copy (AD-14).
"""

from __future__ import annotations

from collections.abc import Mapping

from agentprov.sem.types import SemanticsProfile

__all__ = ["build_profile"]


def build_profile(profile_id: str, version: int, files: Mapping[str, bytes], sha256: str) -> SemanticsProfile:
    """Build the semantics profile ``profile_id`` at ``version`` from its data ``files`` and their digest ``sha256``."""
    from agentprov.adapters.dtap.semantics.tools import build

    return build(profile_id, version, files, sha256)
