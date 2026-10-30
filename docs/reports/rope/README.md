# ROPE: full import and the Q.8 slice (phase 10, 2026-10-10)

`import-cli-rope.json` records the import of the 10,791 TraceLogger logs of `xhOwenMa/ROPE` `runs/` (source `rope`, part `head`,
profile `rope`, corpus `rope`) through `agentprov import`, written by `tools/import_report.py`. `rope-q8.json` is the ROPE slice
of DoD Q.8, written by `tools/agentdojo/rope_report.py` from the sealed AERs. `sem-unknown-tools.json` counts the fail-closed SEM
annotations (`tools/agentdojo/sem_unknown_tools.py`). All hold numbers, codes and digests only; log text (which holds
prompt-injection payloads by design) is never printed. The corpus is outside the repository. The AutoDojo-attack slice
(`autodojo` · `rope-slice`, `via = "rope"`) is imported, owned and counted here.

```bash
uv run agentprov import rope --snapshot head --input <clone> --verify-against-pin --release --jobs 10 \
    --corpus ~/.agentprov/corpora/rope-p10 --summary-json <summary>
uv run python tools/import_report.py --corpus ~/.agentprov/corpora/rope-p10.partial --summary <summary> \
    --out docs/reports/rope/import-cli-rope.json --extra <pin check, census, determinism note, SEM fail-closed counts>
uv run python tools/agentdojo/rope_report.py --corpus ~/.agentprov/corpora/rope-p10.partial --out docs/reports/rope/rope-q8.json
uv run python tools/agentdojo/sem_unknown_tools.py --corpus ~/.agentprov/corpora/rope-p10.partial --out docs/reports/rope/sem-unknown-tools.json
uv run python tools/agentdojo/profile_census.py --profile rope --part head --workers 1
```

**Origin.** The input is the local clone at the pinned commit `64495e16…` (untrusted third-party data, read through
`agentprov.ingest.paths`). The pin is the whole commit (24,909 files, 265,463,047 bytes), not `runs/` alone, so that the context
artefacts outside `runs/` (the correction scripts, the router scopes, the three routed caches) are vouched for by the same listing.
`--verify-against-pin` read 10,826 files (the 10,791 logs and 35 context artefacts); all matched their tree entries and carry the
pinned `git` origin (`pinned_snapshot_check`). The pin's tree listing came from the fetch cache, seeded offline from the clone
(`tools/seed_git_cache.py`, logged in `acquisitions.jsonl`).

AgentPROV source at the integrated `main` `afe7038`, CPython 3.14.8, M2 Max, 10 T1 workers, **release mode** (AER validator release
mode with locators resolved against the raw store; tier 4 strict, a skipped check counts as a failure). Step `rope` of the phase-10
run script. The run finished on its own while the script was stopped for a pause, so the wall time is the script's.

| `agentprov import rope` | |
|---|---|
| Exit code / wall time | 0 / 3,015 s |
| Candidates / mapped / sealed clean / with issues / degenerate / failed / registered | 10,791 / 10,791 / 9,366 / 1,425 / 0 / 0 / 0 |
| Variant | `v1.k14` 10,789, `v1.k14.incomplete` 2 |
| `agent_execution` / `outcome_only` | 10,789 / 2 |
| Origins | `git` 10,791 |
| AER execution digests equal to the index / AER validator pass (release) | 10,791 / 10,791 |
| SEM annotated / `agentprov-prov/0.1` derived / tier-4 pass (strict) / PROV re-derived byte-identically | 10,791 / 10,791 / 10,791 / 10,791 |
| Accounting / completeness | `unverifiable` 10,789, `consistent` 2 / `unverifiable` 10,467, `known_incomplete` 322, `verified_complete` 2 |
| Records | 505,333 |
| Register | 23,528 `sealed`, 14,066 `not_imported` |

Seal issues (files): `accounting_unverifiable` 10,789 and `earlier_attempts_unobservable` 10,789 (info-level facts of every
TraceLogger log), `unexecuted_tool_call` 675, `identity_conflict` 949 (the `qwen3-235b/*/autodojo` logs whose `pipeline_name` tag
names another model than their directory), `retry_passes_inferred` 322, `no_execution_observed` 2 and `no_outcome_recorded` 2 (the
two empty logs). Not imported: `select.owned_elsewhere` 13,765 (`agentlab/**`, owner `ext:agentlab`) and
`select.not_execution_artefact` 301 (`runs/lh_cells.json` and the vendored AutoDojo fork).

**Census** (`profile_census`, reproduces every `observed` count of the profile, `differences: []`; 10,791 logs sealed, 0 crashes):
guard denials 12,657 (`none` variant 9,424, `query` variant 3,233), null-final logs 322, mislabelled qwen logs 949, empty logs 2,
unexecuted trailing calls 753 in 675 logs, ablation 1,240 / router 1,680 logs (clamp 440), `args_mutated_in_place` 10,520.

**Q.8** (`rope-q8.json`). The recorded `security` values stay as logged; the recomputed ones sit beside them (a `recomputed`
judgement that `revises` the recorded one; 0 recomputed values without a recorded one beside them). The corrected-security counts
reproduce D.6.13 and verify/rope.md §6:

| Correction | Logs | Recorded `security` true | After correction | Flipped |
|---|---|---|---|---|
| slack IT5 | 198 | 32 | 0 | 32 |
| dailylife IT7 | 260 | 39 | 22 | 17 |
| github IT1 | 220 | 5 | 0 | 5 |

By attack: slack IT5 covers `important_instructions` 84 (23 → 0), `autodojo` 63 (9 → 0) and `long_horizon` 51 (0 → 0); dailylife IT7
`important_instructions` 200 (32 → 22) and `autodojo` 60 (7 → 0); github IT1 `important_instructions` 160 (4 → 0) and `autodojo` 60
(1 → 0).

**AutoDojo slice** (`rope-q8.json`, `autodojo_slice`). 2,847 logs (3 models × 949 cells: `gemini-2.5-flash`, `gpt-4o-mini`,
`qwen3-235b`; per model 144 banking, 200 dailylife, 180 github, 180 shopping, 105 slack, 140 travel). 5,775 payload slots linked to
the optimiser caches by content (5,772 exact, 3 wrapped); per-file ambiguity sets of 1 cell (1,824 files), 8 (228), 16 (28), 20 (30),
38 (2), 40 (315) and 50 (420); intersected over each (model, suite) arm they give 1, 8, 40 or 50 cells (banking 8 for `gpt-4o-mini` and
`qwen3-235b` and 1 for `gemini-2.5-flash`; slack 40; travel 50; dailylife, github and shopping 1). `security` is true in 88 logs as
recorded (the AutoDojo paper's raw values) and 71 after the recomputation where present.

**SEM fails closed.** `agentdojo.suites@1` has tool tables only for AgentDojo's suites. `sem-unknown-tools.json`: 173,833 of the
655,557 annotations cite `agentdojo.unknown_tool@1` (63,239 integrity, 110,594 role), in 9,331 of the 10,791 logs. 170,013 of them
(2,795 / 2,121 / 2,096 logs) are in the AgentDyn-benchmark suites `dailylife`, `github` and `shopping`; the other 3,820 are in the
three AgentDojo suites (banking 1,773, slack 1,188, travel 859); the cause of those was not investigated (the profile's label
semantics for them is a suite version, so a tool outside the selected version's table is the likely reason, unverified). The split
by suite is `sem_fail_closed.by_benchmark_suite` in the import report.

**Reproducibility.** No second import of this snapshot was run (regenerations need the user's approval), so no whole-tree
comparison across `--jobs` exists for it (`determinism.second_import = "not_run"`). The older branch-code copy
`rope-p10.pre-integration.partial` is an interrupted run and is not comparable.

What this does not show: the denial reason and the guard's allow decisions are not logged; the model of the ablation and router
trees is inferred from the tree names and tags (class I); the harness revision that wrote the AutoDojo runs is unreleased.
