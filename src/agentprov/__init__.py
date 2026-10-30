"""AgentPROV: an execution-provenance framework for LLM-agent security research.

Pipeline (each stage after the raw store is a pure, versioned function)::

    raw evidence (imported logs | live capture/0.1)  ->  AER (aer/0.2; aer/0.1 read)  ->  SEM (sem/0.1)
        ->  W3C PROV (agentprov-prov/0.1: core / inference / assessment bundles)
        ->  validation  ->  corpus (hash-chained manifest)

See ``docs/architecture/`` for the normative specification and ``AGENTS.md`` for project memory.
"""

from agentprov.versions import VERSIONS, __version__

__all__ = ["VERSIONS", "__version__"]
