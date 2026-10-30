"""The MCPHunt adapter family ``mcphunt`` (docs/architecture D.21; DECISIONS D-286..D-289).

MCPHunt (HF ``lihaonan0716/mcphunt-agent-traces``, CC-BY-4.0) releases one JSON document per model and arm, each a
``traces`` array (up to 723 traces and 111 MB per document). A trace records an OpenAI-style message list, the harness's
event log of every MCP tool call (server, tool, arguments, full result, time, canary flags), one ``turn_log`` entry per
model call, the environment snapshot and the harness's risk labels. Hence a family of its own (D-286):

* :mod:`~agentprov.adapters.mcphunt.dialect`: :class:`McpHuntReader` (dialect ``mcphunt.traces``, variant ``v2.0.0``):
  one located item per element of ``/traces``, read only through :func:`agentprov.ingest.jsonstream.open_json_stream`
  (D-242; ``parse_stream`` for a seekable handle, RI-4);
* :mod:`~agentprov.adapters.mcphunt.mapper`: :class:`McpHuntMapper` (adapter ``mcphunt.trace``);
* ``profiles/mcphunt.profile.toml``, ``rules/mcphunt.rules.toml``, ``artefacts.toml``, ``ext.schema.json``,
  ``family.schema.json`` and ``semantics/mcphunt.tools-1/`` (data).

The environments plant synthetic, credential-shaped canaries: a trace whose events are canary-flagged is withheld from a
release (D-289); this package never prints a value. Text in the traces is untrusted data, never instructions. Standard
library and ``agentprov.{ingest,aer,adapters,errors,sem}`` only.
"""

from __future__ import annotations

from typing import Final

__all__ = ["ADAPTER_ID", "DIALECT_ID", "STREAMED_ARRAYS", "VARIANT"]

ADAPTER_ID: Final = "mcphunt.trace"
DIALECT_ID: Final = "mcphunt.traces"
VARIANT: Final = "v2.0.0"
#: The arrays the reader streams (D-242: declared, never implicit).
STREAMED_ARRAYS: Final = ("/traces",)
