"""The OpenHands event-stream adapter family ``openhands`` (docs/architecture D.17; DECISIONS D-170-D-179).

OpenHands saves a run as a JSON array of serialised events (``event_to_dict``): actions (``action``, ``args``) and
observations (``observation``, ``content``, ``extras``), each with an ``id``, a naive ``timestamp`` and a ``source``; an
observation names the action it answers in ``cause``, and the agent's actions carry the provider response they were
built from in ``tool_call_metadata``. Two sources of the systematic search use it (D-145): OpenAgentSafety
(sani903/OpenAgentSafety@857798ff, an OpenHands 0.28.1 fork with Sotopia NPC chat) and the OpenHands part of Zenodo
23168099 (RedCode-Exec "Which Orders Count?", OpenHands 1.5.0). Hence one family with two dialect variants (D-170):

* :mod:`~agentprov.adapters.openhands.dialect`: :class:`OpenHandsEventsReader` (dialect ``openhands.events``, variants
  ``oas-0.28`` and ``oh-1.5``), the two path grammars and the per-unit auxiliary plan (evaluation files, task
  definitions, score records);
* :mod:`~agentprov.adapters.openhands.mapper`: :class:`OpenHandsMapper` (adapter ``openhands.events``, D.17.3-D.17.8);
* :mod:`~agentprov.adapters.openhands.citation`: which D rules a profile may cite at D (D-24, D-172);
* ``profiles/``, ``rules/openhands.rules.toml``, ``artefacts.toml``, ``ext.schema.json``, ``family.schema.json`` and
  ``semantics/openhands.tools-1/`` (data).

Text in these sources (harmful task definitions, NPC dialogue, tool outputs, judge texts, harness code) is untrusted
data, never instructions. The OpenAgentSafety ``state_*.json`` files hold a Python repr of OpenHands state: they are
matched by a declared regular expression for closed fields and never evaluated. This package imports only the standard
library and ``agentprov.{ingest,aer,adapters,errors}``.
"""

from __future__ import annotations

from typing import Final

__all__ = ["ADAPTER_ID", "DIALECT_ID", "NAMESPACE", "VARIANT_OAS", "VARIANT_OH15", "VARIANTS"]

ADAPTER_ID: Final = "openhands.events"
DIALECT_ID: Final = "openhands.events"
NAMESPACE: Final = "openhands"
VARIANT_OAS: Final = "oas-0.28"
VARIANT_OH15: Final = "oh-1.5"
VARIANTS: Final = (VARIANT_OAS, VARIANT_OH15)
