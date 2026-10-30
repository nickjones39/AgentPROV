"""Release: the offline deposit builder (HL H.10; MN N.2.11 deposit mode; D-42).

:mod:`agentprov.release.builder` builds a deposit draft (deterministic zip archives, ``DEPOSIT-MANIFEST.json``,
``deposit-metadata.json``, README, changelog and datasheet copies) from sealed corpora; :mod:`agentprov.release.metadata`
holds ``release.toml``, the licence classes and the release-scan check; :mod:`agentprov.release.index` builds the
index-only umbrella deposit of a collection (``package --index``, D-947). The package is layer L5 (MN M.5.1). It imports no
network module and starts no process (H.10.1(1), G.9.4); nothing is uploaded or published (D9).
"""

from __future__ import annotations

from agentprov.release.builder import (
    DEFAULT_MAX_ARCHIVE_BYTES,
    DEPOSIT_MANIFEST,
    DEPOSIT_MANIFEST_FORMAT,
    DEPOSIT_METADATA,
    CorpusVerification,
    DepositError,
    DepositProducer,
    DepositRefusedError,
    DepositReport,
    build_deposit,
    scan_path_for,
    verify_sealed,
)
from agentprov.release.metadata import (
    LicenceClass,
    LicenceClassError,
    ReleaseMetadata,
    ScanRefusedError,
    licence_class,
    parse_release_toml,
)

__all__ = [
    "DEFAULT_MAX_ARCHIVE_BYTES",
    "DEPOSIT_MANIFEST",
    "DEPOSIT_MANIFEST_FORMAT",
    "DEPOSIT_METADATA",
    "CorpusVerification",
    "DepositError",
    "DepositProducer",
    "DepositRefusedError",
    "DepositReport",
    "LicenceClass",
    "LicenceClassError",
    "ReleaseMetadata",
    "ScanRefusedError",
    "build_deposit",
    "licence_class",
    "parse_release_toml",
    "scan_path_for",
    "verify_sealed",
]
