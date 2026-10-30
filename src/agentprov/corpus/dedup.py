"""``source_key``: the identity of the evidence an execution was mapped from (HL H.7.1; MN M.1.2).

Only the key function exists in phase 3. Ownership, ``select.owned_elsewhere`` and collapse (H.7.2, H.7.3) arrive with the
corpus layer's later phases and are injected by the caller from the registry (MN M.5.2(1)).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from agentprov.aer.ids import canonical_key_loc
from agentprov.io.canonical import is_sha256_hex, jcs_bytes

__all__ = ["SOURCE_KEY_PREFIX", "source_key"]

SOURCE_KEY_PREFIX: Final = "sha256:"


def source_key(artefact_sha256: str, loc: Mapping[str, object]) -> str:
    """``"sha256:" + artefact_sha256_hex + "#" + JCS(loc)``, always with the ``#`` (H.7.1; R-03, AD-04).

    ``loc`` is the canonical key form of the AER in-artefact locator (``{}``, ``{"p": ...}``, ``{"line": n}``); for an
    archive member the digest is the **member object's** (AD-12). ``ValueError`` for a malformed digest or locator.
    """
    if not is_sha256_hex(artefact_sha256):
        raise ValueError("artefact digest must be 64 lower-case hex digits")
    return f"{SOURCE_KEY_PREFIX}{artefact_sha256}#{jcs_bytes(canonical_key_loc(loc)).decode('utf-8')}"
