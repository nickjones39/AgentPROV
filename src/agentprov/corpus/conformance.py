"""The W3C PROV conformance mark of a working corpus (G2c-5, D-432; design.md §8.3a).

``--skip-prov-conformance`` (a dev-mode option of the PROV-generating commands, never with ``--release`` and never in the
regeneration round) skips tier 4 only (the PROV-O round trip and constraint checks); mapping, SEM, PROV generation, the
AER validator and linkage still run, so no output byte changes. The working manifest then records
``validation.prov_conformance: "skipped"`` (only then: an ordinary corpus is byte-identical), and the corpus counts as
**unvalidated** until a full ``recompute --out NEW --stages sem,prov,validation`` writes a new corpus without the mark
(user decision 2026-10-15: ``validate`` stays read-only; a derive never carries a skipped validation layer). ``package`` refuses to seal it
and ``verify`` fails it.

This module is the one reader of the mark. Its producers (the import, derive, recompute and live pipelines) and the
the recompute clearing are wired with their owners (D-525).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

__all__ = ["SKIPPED", "UNVALIDATED_CODE", "conformance_skipped"]

SKIPPED: Final = "skipped"
#: The code a refusal or verify finding carries for an unvalidated corpus.
UNVALIDATED_CODE: Final = "corpus.validation.prov_conformance_skipped"


def conformance_skipped(manifest: Mapping[str, Any] | None) -> bool:
    """Whether ``manifest`` (a working ``corpus.json``) records a skipped tier 4 that no later validation cleared."""
    if not isinstance(manifest, Mapping):
        return False
    validation = manifest.get("validation")
    return isinstance(validation, Mapping) and validation.get("prov_conformance") == SKIPPED
