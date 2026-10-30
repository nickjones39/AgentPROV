"""``common_projection``: the comparable view used by the differential tests (docs/architecture K.3.2, K.9.1).

The projection itself lives in the adapters layer (:mod:`agentprov.adapters.projection`), because the capture mapper
runs the same comparison at map time (the live-versus-native check of D.10.4): one definition, two callers. Times are
excluded; compare projections as JCS bytes (:func:`projection_bytes`), never with Python ``==`` (K.1(9)).
"""

from __future__ import annotations

from agentprov.adapters.projection import common_projection, projection_bytes, projection_differences

__all__ = ["common_projection", "projection_bytes", "projection_differences"]
