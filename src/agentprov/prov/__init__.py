"""Provenance engine ``agentprov-prov/0.1`` (docs/architecture E, F).

``derive(aer)`` returns the canonical bundled PROV-JSON of one sealed AER execution: the core bundle (OBSERVED and
DERIVED statements), one inference bundle per method set (INFERRED statements) and the top-level conversion
provenance. The frozen ``adprov-v2.3-compat`` regression oracle lives in :mod:`agentprov.prov.compat` and is imported
only by ``agentprov.prov.specs`` (lazily), ``agentprov.migration`` and tests (MN M.5.2(3)).

The engine modules are imported on first use, so ``import agentprov.prov.compat`` stays light.
"""

from __future__ import annotations

from typing import Any

__all__ = ["AGENTPROV_PROV_0_1", "ProvDerivation", "ProvDerivationError", "ProvOptions", "derive"]


def __getattr__(name: str) -> Any:
    if name == "AGENTPROV_PROV_0_1":
        from agentprov.prov.specs import load_spec

        return load_spec()
    if name in ("ProvDerivation", "ProvDerivationError", "ProvOptions", "derive"):
        from agentprov.prov import engine

        return getattr(engine, name)
    raise AttributeError(name)
