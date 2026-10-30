# AgentDyn variant A: full import (phase 10, 2026-10-11)

`import-cli-agentdyn.json` records the import of the variant-A logs of `SaFo-Lab/AgentDyn` `runs/` (source `agentdyn`, part
`a`, profile `agentdyn`, corpus `agentdyn`) through `agentprov import`, written by `tools/import_report.py`.
`sem-unknown-tools.json` counts the fail-closed SEM annotations (`tools/agentdojo/sem_unknown_tools.py`). Both hold numbers,
codes and digests only; log text (which holds prompt-injection payloads by design) is never printed. The corpus is outside the
repository.

```bash
uv run agentprov import agentdyn --snapshot a --input <clone> --verify-against-pin --release --jobs 10 \
    --corpus ~/.agentprov/corpora/agentdyn-a-p10 --summary-json <summary>
uv run python tools/import_report.py --corpus ~/.agentprov/corpora/agentdyn-a-p10.partial --summary <summary> \
    --out docs/reports/agentdyn/import-cli-agentdyn.json --extra <pin check, census, determinism note, SEM fail-closed counts>
uv run python tools/agentdojo/sem_unknown_tools.py --corpus ~/.agentprov/corpora/agentdyn-a-p10.partial --out docs/reports/agentdyn/sem-unknown-tools.json
uv run python tools/agentdojo/profile_census.py --profile agentdyn --part a --workers 2
```

**Origin.** The input is the local clone at the pinned commit `5353cf76…` (untrusted third-party data, read through
`agentprov.ingest.paths`), checked with `--verify-against-pin` against the pin's listing of `runs/` (47,723 files, 598,326,615
bytes; tree `90d6d50d…`; seeded offline into the fetch cache with `tools/seed_git_cache.py`, logged in `acquisitions.jsonl`). All
47,723 files matched their tree entries (`pinned_snapshot_check`). Variants are assigned to parts by the profile's `variant_labels`:
importing part `a` maps the 38,281 `v1.k14` files and registers the other 9,442 (variants B, `v0.k11`, and C, `drift.k18.messages`)
as `select.dialect_planned`; the input root also holds 949 DRIFT runs vendored under `src/` (byte-identical to the `drift` source),
registered `select.owned_elsewhere` with owner `drift`.

AgentPROV source at the integrated `main` `afe7038`, CPython 3.14.8, M2 Max, 10 T1 workers, **release mode** (AER validator release
mode with locators resolved against the raw store; tier 4 strict). Step `agentdyn` of the phase-10 run script.

| `agentprov import agentdyn --snapshot a` | |
|---|---|
| Exit code / wall time | 0 / 9,145 s |
| Candidates / mapped / sealed clean / with issues / degenerate / failed | 47,723 / 38,281 / 35,904 / 2,377 / 0 / 0 |
| Registered (`select.dialect_planned`) / excluded (`select.owned_elsewhere`) | 9,442 / 949 |
| Variant / unit | `v1.k14` 38,269, `v1.k14.incomplete` 12 / `agent_execution` 38,281 |
| Origins | `git` 38,281 |
| AER execution digests equal to the index / AER validator pass (release) | 38,281 / 38,281 |
| SEM annotated / `agentprov-prov/0.1` derived / tier-4 pass (strict) / PROV re-derived byte-identically | 38,281 / 38,281 / 38,281 / 38,281 |
| Accounting / completeness | `unverifiable` 38,270, `consistent` 11 / `unverifiable` 37,444, `known_incomplete` 837 |
| Records | 1,552,020 |

Seal issues (files): `accounting_unverifiable` 38,270 and `earlier_attempts_unobservable` 38,281 (info-level facts of every
TraceLogger log), `unexecuted_tool_call` 1,683, `retry_passes_inferred` 826, `agentdojo.local_parse_drop_possible` 488,
`unattributed_additional_user_message` 266, `orphan_tool_result` 240 (the CaMeL pipelines), `incomplete_run` 12,
`agentdojo.pipeline_name_mismatch` 12 (the variant-A travel strays in the Progent directory, D.6.14 item 3) and
`outcome_imposed_by_runner` 5. No `identity_unresolved`: every pipeline directory is in the 76-row identity table.

**Census** (`profile_census`, reproduces every `observed` count of the profile, `differences: []`; 47,723 files read, 38,281
sealed, 9,442 not this part's): selected counts include 826 null-final logs, 5 run-error files, 12 incomplete runs, 1,647
solvability pre-pass files, 5,184 spotlighting and 5,184 repeat-user-prompt logs, 4,542 tool-filter logs, 29,317 detector
redactions, 2,635 CaMeL tool messages (1,977 orphan executions), 434 integrated-DRIFT user messages, 15,306 null call ids and
210,127 placeholder arguments.

**SEM fails closed.** The semantics profile `agentdojo.suites@1` has tool tables only for AgentDojo's suites, so every tool of
the AgentDyn suites `dailylife`, `github` and `shopping` is annotated `unknown` by design (rule `agentdojo.unknown_tool@1`).
`sem-unknown-tools.json`: 630,549 of the 1,772,460 annotations (210,242 integrity, 420,307 role) cite that rule, covering
210,242 tool executions and 210,065 tool-call parts, in 32,262 of the 38,281 logs. The import report splits the logs by suite
(`sem_fail_closed.by_benchmark_suite`: dailylife 11,684 of 13,350 logs, github 10,502 of 12,444, shopping 10,076 of 12,473; the 14
travel logs have none). SEM tables for these suites are not built (D.6.14 item 9), so no integrity or role claim about their tools
exists in the assessment bundles.

**Reproducibility.** No second full import of this snapshot was run (regenerations need the user's approval), so no whole-tree
comparison across `--jobs` exists for it (`determinism.second_import = "not_run"`). The branch-code copy
`agentdyn-a-p10.pre-integration.partial` is an interrupted run of 648 executions; against it the integrated corpus has **648 of 648
AER documents and 648 of 648 SEM documents byte-identical**, and every PROV document differs in exactly one value, the
`apv:sha256` of the `agentdojo` rule-catalogue entity (D.6.16 added rules; catalogue version unchanged). That is a partial
independent re-import, not a determinism check.

What this does not show: variants B and C (planned), the `history` part, the identity of any model (directory names are
publisher-asserted curation labels, class I), and any semantics for the three new suites.
