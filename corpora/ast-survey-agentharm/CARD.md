---
mode: import
corpus: ast-survey-agentharm
---

## Motivation

The Agent Security Tools Survey's AgentHarm runs, recorded as Inspect evaluation logs: the first non-AgentDojo-lineage source of AgentPROV, kept as its own restricted-use corpus because of the AgentHarm use clause.

## Composition

The corpus holds {{v:/counts/executions}} execution records from one source, {{v:/counts/by_unit/agent_execution}} of them agent executions. {{claim:restricted_use}} {{claim:has_archive_members}} {{claim:raw_included}} {{claim:validation_strict}}

## Collection process

AgentPROV did not run these executions: it imported the run logs the source published, at the pinned origin listed under Composition. Every imported log is evidence of what the source harness recorded, not of what happened; statements AgentPROV adds carry an evidence class (observed, derived or inferred) and a rule id. The survey ran the AgentHarm tasks of `inspect_evals` under `inspect_ai`; each sample of an evaluation log is an archive member and one execution. The AgentHarm dataset revision is inferred from code, not recorded.

## Preprocessing and labelling

Each log was parsed through the bounded, stdlib-only ingest layer, mapped to one AgentPROV Execution Record (`aer/0.1`) by the adapter named under Integrity and verification, annotated by the semantics profile (`sem/0.1`) and derived to W3C PROV bundles (`agentprov-prov/0.1`). Raw bytes are stored unchanged; nothing is scrubbed or corrected. Unknown values are declared unknown with a reason, never filled in.

## Uses

The corpus supports provenance-aware analyses of agent-security runs: which inputs reached the agent, which tool calls it made, and how outcomes were recorded. Rates are computed per corpus and never pooled across corpora without deduplication by execution id. Analyses that need complete records filter on completeness and fail closed.

## Maintenance

Maintained by the AgentPROV project. A correction is a new corpus version with an entry in `CHANGELOG.md`; nothing is removed from a sealed version.
