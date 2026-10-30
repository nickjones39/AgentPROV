# Home-directory paths in derived records: classification (2026-10-22)

Source of datasheet item 22 (`docs/reports/analysis/datasheet-items.md`) and statement `benchmark-and-model-home-paths`
(`corpora/datasheet-statements.toml`). The bug pass review session (`bugpass-perf-10`) classified the
`/home/<name>/`-shaped paths that the pre-round integration review's redaction proof reported in two stored corpora.
Its scripts read the stored corpora and printed counts and opaque ordinals only. No path value was written anywhere,
and none is recorded here.

**Method.** D-457 shapes over every derived record (AER, PROV), excluding the allowlist and D-604 labels. For each
distinct path name, the first record holding it in each execution, and whether the bare token occurs in any earlier
record of the same execution (system prompt, user prompt, fixtures, tool results). Hits were also checked for
harness-derived fields (tracebacks, log locations, environment).

## ast-survey-agentharm (stored corpus, 1,056 AERs)

18 distinct path names, S1–S18.

| Names | First seen | Classification |
|---|---|---|
| S1, S3, S8 | benchmark-authored (user prompt, sample-metadata prompt or fixture) in every execution; S1 and S8 appear as paths in AgentHarm's public dataset | synthetic-benchmark |
| S5 | benchmark-authored first in 49 executions, tool output first in 19; a path in AgentHarm's public dataset; a standard home-folder name | synthetic-benchmark |
| S2, S4, S6, S7, S10 | tool output of AgentHarm's offline stub tools (S2 also bare in the public prompts; S10 a common English word seen bare in the survey's docs) | synthetic-benchmark |
| S9, S11–S18 | model-generated: nothing earlier in the execution holds the token (S9 bare earlier in model and tool text only); 1–3 executions each; S11 and S15 are standard home-folder names | false-positive (model-generated path) |

Totals: 9 benchmark names (S1–S8, S10), 9 model-generated names (S9, S11–S18). No hit in a harness-derived field.

## agentdyn-a, github suite (stored corpus, 12,444 executions with task.suite == "github")

14 distinct path names, N1–N14. Every name first appears as a path in a model turn; the suite's tool results and errors
echo it back.

| Names | Token supplied earlier by | Classification |
|---|---|---|
| N2, N3, N10 | system prompt and environment fixture records (the suite's fictional user identity) | synthetic-benchmark |
| N1, N5, N7, N8, N11, N12, N14 | task prompt and/or the suite's tool results (environment data) | synthetic-benchmark |
| N4 | the suite's tool results only | synthetic-benchmark |
| N6, N9, N13 | nowhere earlier in any form (N13 is the 11-character segment of execution `ex_56reuumb6kl4s6z4pjq5qzzw2b`) | false-positive (model-generated path) |

Totals: 11 benchmark persona or environment names, 3 model-generated names. No hit in a harness-derived field. The
AgentDyn staging clone is blob-less; its suite files were not read (lazy fetch blocked), so the classification rests on
the stored records. rope's runs of the AgentDyn suites were not scanned.

## Verdict

No segment names a real third-party account, so no D-604 redaction or withholding item is needed. Model and benchmark
text stays verbatim (D-604). Release-scan triage: synthetic-benchmark for the benchmark names, false-positive for the
model-generated ones. User decision 2026-10-22: disclose this as datasheet item 22.

## Re-measure after regeneration (2026-10-24, plan §7b)

The classification's inputs are unchanged in the regenerated corpora (`docs/reports/regeneration/item22/`):
- `ast-survey-agentharm-rg2` holds the same D-457 path names with the same per-execution features as the stored corpus.
- `agentdyn-a-rg1`'s github suite holds the same 14 names over the same 12,444 executions.
- Neither has a hit in a harness-derived field.

The counts and labels above stand.
