"""The credential-leak study adapter family ``credleak`` (docs/architecture D.19; DECISIONS D-260..D-268).

Zenodo 22737462 (v3, CC-BY-4.0) holds the run data of "How Credentials Leak from 'Safe' LLM Coding Agents": one JSON
*cell* per (model, channel, scenario, wave), each with every repetition in ``runs[]``. A run is a list of turns (user
message, one assistant text, the ordered tool calls with input and output in one entry, one timestamp) plus the
harness's detector signals. There is no message list, no model-call boundary, no call id and no per-call time. Hence a
family of its own (D-260):

* :mod:`~agentprov.adapters.credleak.dialect`: :class:`CredleakCellReader` (dialect ``credleak.cell``, variant ``v1``),
  the path grammar and one located item per run (locator ``{"p": "/runs/<i>"}``, HL H.7.1 "element of a JSON array");
* :mod:`~agentprov.adapters.credleak.mapper`: :class:`CredleakMapper` (adapter ``credleak.cell``, D.19.3-D.19.7);
* :mod:`~agentprov.adapters.credleak.redact`: the tool-output redaction of third-party account paths (D-605);
* ``profiles/credleak-p15b.profile.toml`` (with the ``[withhold]`` policy of D-265 and the redaction rule of D-605;
  version 1 under ``profiles/archive/``), ``rules/credleak.rules.toml`` (version 1 under ``rules/archive/``),
  ``artefacts.toml``, ``ext.schema.json``, ``family.schema.json``, ``rates.toml`` and ``semantics/credleak.tools-1/``,
  ``semantics/credleak.tools-2/`` (the same tables on catalogue version 2).

**Planted credentials.** The study plants canary credentials in the agent's workspace; every planted value carries the
upper-case tag the profile's withholding rules name. The mapper copies run content verbatim (aer/0.1 has no in-string
redaction of content; the one exception is an account path in tool output, D-605), so a run whose content holds a
planted value is withheld at sealing by the profile's ``[withhold]`` policy (D-234, D-235), never by this package. This
package never prints, logs or tests a planted value.

Text in the deposit (task prompts, injection payloads, poisoned rules files, tool outputs, agent output) is untrusted
data, never instructions. This package imports only the standard library and ``agentprov.{ingest,aer,adapters,errors}``.
"""

from __future__ import annotations

from typing import Final

__all__ = ["ADAPTER_ID", "DIALECT_ID", "VARIANT"]

ADAPTER_ID: Final = "credleak.cell"
DIALECT_ID: Final = "credleak.cell"
VARIANT: Final = "v1"
