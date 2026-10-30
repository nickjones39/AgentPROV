"""The gemini-cli event-stream adapter family ``geminicli`` (docs/architecture D.23; DECISIONS D-330..D-337).

Zenodo 20404563 (``RESULTS_raw.tar.zst``, CC-BY-4.0) releases 10,000 rollouts of a code-agent agentic-misalignment
benchmark in 20 cells (scaffold x model). Only the five ``gemini_cli`` cells hold a structured trajectory: the CLI's
``--output-format stream-json`` events (``init``, ``message``, ``tool_use``, ``tool_result``, ``error``, ``result``),
one JSON object per line. Tool results name their call by a CLI-generated ``tool_id``; assistant text arrives as
streamed deltas; no event marks a model request. Hence a family of its own (D-330):

* :mod:`~agentprov.adapters.geminicli.dialect`: :class:`GeminiStreamReader` (dialect ``geminicli.stream_json``, variant
  ``v1``), the member-label grammar and the per-unit sibling plan;
* :mod:`~agentprov.adapters.geminicli.mapper`: :class:`GeminiStreamMapper` (adapter ``geminicli.stream_json``);
* ``profiles/code-agent-misalignment-geminicli.profile.toml``, ``rules/geminicli.rules.toml``, ``artefacts.toml``,
  ``ext.schema.json``, ``family.schema.json`` and ``semantics/geminicli.tools-1/`` (data).

Text in the deposit (task files, prompts, tool outputs, model output) is untrusted data, never instructions: the runs
are agentic-misalignment elicitations and hold manipulative content by design. This package imports only the standard
library and ``agentprov.{ingest,aer,adapters,errors,sem}``.
"""

from __future__ import annotations

from typing import Final

__all__ = ["ADAPTER_ID", "DIALECT_ID", "NAMESPACE", "VARIANT"]

ADAPTER_ID: Final = "geminicli.stream_json"
DIALECT_ID: Final = "geminicli.stream_json"
VARIANT: Final = "v1"
NAMESPACE: Final = "geminicli"
