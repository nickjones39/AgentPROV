"""Independent version axes (docs/architecture: section L.1). Never collapse them into one number."""

from __future__ import annotations

from importlib import metadata
from typing import Final

#: The release literal, used only by a source tree with no installed distribution. A test pins it to pyproject.toml.
_UNINSTALLED_VERSION: Final = "0.1.0"


def _software_version() -> str:
    """``pyproject.toml`` ``[project].version`` via the installed metadata (L.1.1 row 1), the one software version source.

    The ``expand`` stage reads the same metadata (``raw.members._engine_version``), so every stage records one version.
    """
    try:
        return metadata.version("agentprov")
    except metadata.PackageNotFoundError:  # pragma: no cover - an uninstalled source tree
        return _UNINSTALLED_VERSION


__version__: Final = _software_version()  # software (tag v0.1.0)

VERSIONS: Final[dict[str, str]] = {
    "software": __version__,
    "aer": "aer/0.2",  # canonical execution record format (aer/0.1 frozen and still read; D-212)
    "sem": "sem/0.1",  # standoff semantic annotations
    "capture": "capture/0.1",  # live raw-evidence event log
    "prov_spec": "agentprov-prov/0.1",  # provenance specification + rule catalogue
    "compat_spec": "adprov-v2.3-compat",  # frozen regression oracle (not recommended semantics)
    "ontology": "apv 0.2.0",  # https://w3id.org/agentprov/ns#
    "corpus_format": "agentprov-corpus/0.2",  # agentprov-corpus/0.1 still read and verified
}

#: Formats frozen at the phase-6 gate (AD-06, 2026-10-08): three importers (Inspect ``.eval``, AgentDojo TraceLogger
#: ``v0.k11``, the FooBench future-framework adapter) mapped onto them with no format change. A change to a frozen
#: format's schema, record kinds or closed enums is a new version (``aer/0.2``, ``capture/0.2``; D.12.4), never an edit
#: in place; ``tests/unit/test_format_freeze.py`` enforces it.
FROZEN: Final[frozenset[str]] = frozenset({"aer", "capture"})

