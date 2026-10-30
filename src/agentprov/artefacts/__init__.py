"""The thin shared artefact layer (layer L3 beside ``validate``; docs/architecture D.15, DECISIONS D-12; MN M.1.2).

Every source that becomes a PROV corpus has artefacts: defects of the upstream harness, the benchmark, a baseline
converter or the capture. Knowledge about them belongs to the adapter that reads the source: each family ships its own
versioned catalogue ``adapters/<family>/artefacts.toml`` and handles every case at conversion time. This package holds
only what is common, so counts are comparable across sources and citable:

* :mod:`~agentprov.artefacts.catalogue`: the catalogue schema, loader, discovery (package data only; no adapter module is
  imported) and the cross-check that every ``detector``/``handling`` rule id exists in some rule catalogue;
* :mod:`~agentprov.artefacts.detectors`: the generic, source-neutral detectors computable from an AER alone;
* :mod:`~agentprov.artefacts.scan`: :func:`scan` (the safety net over one sealed AER, unclaimed hits become
  ``artefact.unclassified.<detector>``) and :func:`table` (the per-class summary of D.15.4).

The package changes none of ``aer``, ``prov``, ``validate`` or ``corpus``, writes nothing, and reads no clock, network or
environment. **It is not wired into the CLI yet**: ``import --dry-run --artefacts`` waits for the import pipeline and
``stats --artefacts`` for phase 11. The wiring will call :func:`scan` and :func:`table` and add no semantics.
"""

from __future__ import annotations

from agentprov.artefacts.catalogue import (
    GENERIC_PREFIX,
    UNCLASSIFIED_PREFIX,
    ArtefactCatalogue,
    ArtefactCatalogueError,
    ArtefactEntry,
    Expected,
    Problem,
    check_references,
    discover_catalogues,
    families_with_catalogues,
    known_issue_codes,
    known_rule_ids,
    load_catalogue,
    parse_catalogue,
)
from agentprov.artefacts.detectors import DETECTORS, NOT_YET_IMPLEMENTED, DetectorInfo
from agentprov.artefacts.scan import Finding, ScanError, TableRow, scan, scan_many, table

__all__ = [
    "DETECTORS",
    "GENERIC_PREFIX",
    "NOT_YET_IMPLEMENTED",
    "UNCLASSIFIED_PREFIX",
    "ArtefactCatalogue",
    "ArtefactCatalogueError",
    "ArtefactEntry",
    "DetectorInfo",
    "Expected",
    "Finding",
    "Problem",
    "ScanError",
    "TableRow",
    "check_references",
    "discover_catalogues",
    "families_with_catalogues",
    "known_issue_codes",
    "known_rule_ids",
    "load_catalogue",
    "parse_catalogue",
    "scan",
    "scan_many",
    "table",
]
