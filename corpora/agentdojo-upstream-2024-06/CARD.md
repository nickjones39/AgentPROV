---
mode: import
corpus: agentdojo-upstream-2024-06
---

## Motivation

The `2024-06` run logs that the AgentDojo authors published with the benchmark, imported natively from the pinned upstream commit.

## Composition

The corpus holds {{v:/counts/executions}} execution records from one source, {{v:/counts/by_unit/agent_execution}} of them agent executions. {{claim:no_restrictions}} {{claim:raw_included}} {{claim:validation_strict}}

## Collection process

AgentPROV did not run these executions: it imported the run logs the source published, at the pinned origin listed under Composition. Every imported log is evidence of what the source harness recorded, not of what happened; statements AgentPROV adds carry an evidence class (observed, derived or inferred) and a rule id. AgentDojo's own harness wrote one TraceLogger log per run; the log keeps only the last of up to three passes, so earlier passes are recorded as lost.

## Preprocessing and labelling

Each log was parsed through the bounded, stdlib-only ingest layer, mapped to one AgentPROV Execution Record (`aer/0.1`) by the adapter named under Integrity and verification, annotated by the semantics profile (`sem/0.1`) and derived to W3C PROV bundles (`agentprov-prov/0.1`). Raw bytes are stored unchanged; nothing is scrubbed or corrected. Unknown values are declared unknown with a reason, never filled in.

## Uses

The corpus supports provenance-aware analyses of agent-security runs: which inputs reached the agent, which tool calls it made, and how outcomes were recorded. Rates are computed per corpus and never pooled across corpora without deduplication by execution id. Analyses that need complete records filter on completeness and fail closed.

## Maintenance

Maintained by the AgentPROV project. A correction is a new corpus version with an entry in `CHANGELOG.md`; nothing is removed from a sealed version.
