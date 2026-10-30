"""The AutoGen guard-placement adapter family ``autogen`` (docs/architecture D.19; DECISIONS D-300..D-306).

Zenodo 23025259 v1.0 ("AutoGen guard placement", CC-BY-4.0 data, MIT code) releases a measurement study of one prompt-
injection guard moved between the three interception points of an AutoGen 0.7.5 team (model client, runtime message bus,
tool boundary). Each phase directory holds ``runs.jsonl`` (one run per line: AutoGen ``TaskResult.messages`` dumped by
the harness, plus run settings), ``events.jsonl`` (the harness's run-wide event log: guard verdicts by text digest, model
requests and responses, tool calls) and ``guard_raw.jsonl`` (each distinct scanned text once per guard, with the
verdict detail). Hence a family of its own (D-302):

* :mod:`~agentprov.adapters.autogen.dialect`: :class:`AutoGenRunsReader` (dialect ``autogen.runs``), the label grammar,
  the row selection (D-300) and the per-unit inputs;
* :mod:`~agentprov.adapters.autogen.events`: the run's event rows, the attempt choice and the request/response pairs
  (D-302);
* :mod:`~agentprov.adapters.autogen.mapper`: :class:`AutoGenMapper` (adapter ``autogen.runs``);
* ``profiles/``, ``rules/autogen.rules.toml``, ``artefacts.toml``, ``family.schema.json``, ``ext.schema.json`` and
  ``semantics/autogen.tools-1/`` (data).

**One execution per line.** The runner maps one located item per artefact today, so these units are mapped in memory
until the row-unit capability lands (D-301, routed R-10n-3). Text in the deposit (probe documents with injection
passages and canaries, tool outputs, model output) is untrusted data, never instructions. This package imports only the
standard library and ``agentprov.{ingest,aer,adapters,errors,sem}``.
"""

from __future__ import annotations

from typing import Final

__all__ = ["ADAPTER_ID", "DIALECT_ID", "VARIANTS"]

ADAPTER_ID: Final = "autogen.runs"
DIALECT_ID: Final = "autogen.runs"
#: Variants by the run row's key set (D-302): the team runs of phases 2-5, the InjecAgent runs of phase 6, the
#: condition runs of phases 10 and 13, and the prompt-defence runs of phase 12.
VARIANTS: Final = frozenset({"team", "injecagent", "condition", "defense"})
