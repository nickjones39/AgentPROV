"""The AgentOps-Bench adapter family ``agentops`` (docs/architecture D.18; DECISIONS D-190..D-199).

AgentOps-Bench (Zenodo 19875693, Apache-2.0) releases one JSON file per run of its v1.0 pilot (8 models x 100 tasks x 3
conditions x 3 runs) in a gzip tar, and the task definitions and harness code in a zip. A run records steps, each one
model response with its usage, its text and its tool calls, and the tool results in a parallel array; there are no call
ids, no message list and no per-step time (only a timestamp per call). The adversarial condition appends a payload to
some tool results and the noisy and adversarial conditions replace some results with fabricated failures, both
recorded per result. Hence a family of its own (D-190):

* :mod:`~agentprov.adapters.agentops.dialect`: :class:`AgentOpsTraceReader` (dialect ``agentops.trace``, variant ``v1``),
  the member-label grammar and the per-unit task plan (the ``tasks`` pin, table ``tables/task_files.toml``);
* :mod:`~agentprov.adapters.agentops.pairing`: call-to-result pairing by index inside a step, guarded by the tool names
  (D-193, class I);
* :mod:`~agentprov.adapters.agentops.join`: the task-definition join and its field allowlist (D-194);
* :mod:`~agentprov.adapters.agentops.mapper`: :class:`AgentOpsMapper` (adapter ``agentops.trace``);
* ``profiles/agentops-bench-pilot.profile.toml``, ``rules/agentops.rules.toml``, ``artefacts.toml``,
  ``ext.schema.json``, ``family.schema.json``, ``tables/`` and ``semantics/agentops.tools-1/`` (data).

Text in the deposit (task prompts, payloads, tool outputs, model output) is untrusted data, never instructions. This
package imports only the standard library and ``agentprov.{ingest,aer,adapters,errors,sem}``.
"""

from __future__ import annotations

from typing import Final

__all__ = ["ADAPTER_ID", "DIALECT_ID", "VARIANT"]

ADAPTER_ID: Final = "agentops.trace"
DIALECT_ID: Final = "agentops.trace"
VARIANT: Final = "v1"
