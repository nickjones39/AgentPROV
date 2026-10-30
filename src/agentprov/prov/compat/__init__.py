"""Frozen compatibility profiles (docs/architecture EF E.8, J.3.3).

Quarantined (MN M.5.2(3)): only ``agentprov.prov.specs`` (lazily, when ``adprov-v2.3-compat`` is explicitly requested),
``agentprov.migration`` and tests may import this package. Nothing here is imported by ``agentprov.prov`` itself.
"""
