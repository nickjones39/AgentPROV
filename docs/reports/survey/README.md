# Agent Security Tools Survey, AgentDojo runs: full import (phase 10, 2026-10-11)

`import-cli-agentdojo-runs.json` records the import of the 3,243 AgentDojo logs of `Forever-CodingNoob/agent-security-tools-survey`
(source `agent-security-tools-survey`, part `agentdojo-runs`, profile `survey-runs`, corpus `ast-survey-agentdojo`) through
`agentprov import`, written by `tools/import_report.py`. It holds numbers, codes and digests only; log text (which holds
prompt-injection payloads by design) is never printed. The corpus is outside the repository. The survey's AgentHarm part is a
separate source of another family and corpus (`docs/reports/inspect/`). The data are CC-BY-4.0.

```bash
uv run agentprov import agent-security-tools-survey --snapshot agentdojo-runs --input <clone> --verify-against-pin \
    --release --jobs 10 --corpus ~/.agentprov/corpora/ast-survey-agentdojo-p10 --summary-json <summary>
uv run python tools/import_report.py --corpus ~/.agentprov/corpora/ast-survey-agentdojo-p10.partial --summary <summary> \
    --out docs/reports/survey/import-cli-agentdojo-runs.json --extra <pin check, census, cross-checks, independent re-import>
uv run python tools/agentdojo/profile_census.py --profile survey-runs --part agentdojo-runs
uv run python tools/agentdojo/source_checks.py --source survey --corpus ~/.agentprov/corpora/ast-survey-agentdojo-p10.partial
uv run python tools/sem/sem_import_report.py --corpus ~/.agentprov/corpora/ast-survey-agentdojo-p10.partial \
    --compare ~/.agentprov/corpora/ast-survey-agentdojo-p10.pre-integration.partial --out docs/reports/sem/import-survey-agentdojo-runs.json
```

**Origin.** The input is the local clone at the pinned commit `89c4db2c…` (untrusted third-party data, read through
`agentprov.ingest.paths`), checked with `--verify-against-pin` against the pin's tree listing of `agentdojo/` (3,256 files,
43,565,675 bytes; seeded offline into the fetch cache with `tools/seed_git_cache.py`, logged in `acquisitions.jsonl`). The 3,253
files read (the 3,243 logs and ten context artefacts: eight console logs, `timing_summary.csv` and the run script) all matched
their tree entries and carry the pinned `git` origin (`pinned_snapshot_check`). A survey import must name its part
(`--snapshot agentdojo-runs`); the six AgentHarm `.eval` files of the same clone are registered `select.owned_elsewhere`
(owner corpus `ast-survey-agentharm`) and the four ASB result CSVs `select.dialect_planned` (10 register rows, `not_imported`).

AgentPROV source at the integrated `main` `afe7038`, CPython 3.14.8, M2 Max, 10 T1 workers, **release mode** (AER validator release
mode with locators resolved against the raw store; tier 4 strict). Step `survey` of the phase-10 run script.

| `agentprov import agent-security-tools-survey --snapshot agentdojo-runs` | |
|---|---|
| Exit code / wall time | 0 / 525 s |
| Candidates / mapped / sealed clean / with issues / degenerate / failed / registered | 3,243 / 3,243 / 3,184 / 59 / 0 / 0 / 0 |
| Variant / unit | `v1.k14` 3,243 / `agent_execution` 3,243 |
| Origins | `git` 3,243 |
| AER execution digests equal to the index / AER validator pass (release) | 3,243 / 3,243 |
| SEM annotated / `agentprov-prov/0.1` derived / tier-4 pass (strict) / PROV re-derived byte-identically | 3,243 / 3,243 / 3,243 / 3,243 |
| Accounting / completeness | `unverifiable` 3,243 (TraceLogger records no model call) / `unverifiable` 3,243 |
| Records | 95,836 |

Seal issues (files): `accounting_unverifiable` 3,243 and `earlier_attempts_unobservable` 3,243 (info-level facts of every
TraceLogger log), `outcome_imposed_by_runner` 11 (the `gpt-oss:120b` run errors), `unexecuted_tool_call` 48 (the iteration-capped
traces). No adapter issue code fired: no `identity_unresolved`, `pipeline_name_mismatch`, `path_field_mismatch` or
`undeclared_quirk`. Every log carries the AgentDojo default system prompt and is labelled `agentdojo_default`.

**Census** (`profile_census`, reproduces every `observed` count of the profile, `differences: []`): run-error files **11**,
iteration-capped traces **48** (49 unexecuted calls) and solvability pre-pass files **105** are the investigation's figures;
`benign_security_constant` 396 files, 395 applied (the 396th is a run error); `args_mutated_in_place` 2,901 files;
placeholder arguments 11,286; no log ends in a null content (so no hidden earlier pass is detectable).

**Cross-checks against the investigation** (`source_checks --source survey`, all equal): the per-model aggregates of verify
§2.4 reproduce from the AERs (benign utility 67.0 / 57.7 / 69.1 per cent, utility under attack 54.9 / 36.6 / 52.8, mean security
over the 949 attack pairs 27.0 / 21.9 / 17.6, solvability 68.6 / 60.0 / 62.9, for `gpt-oss:120b`, `qwen3-coder:30b` and `qwen3:14b`
on 97 benign, 949 attacked and 35 solvability logs each), the message totals (3,243 system, 3,243 user, 13,599 assistant, 11,237
tool), 11,286 tool calls, and the 11 run errors (all `gpt-oss:120b`). Security is AgentDojo's code semantics (the injection task
succeeded), so these "security" rates are targeted attack success rates, not the README's "resisted" gloss.

**Reproducibility.** No second import of this snapshot was run (regenerations need the user's approval), so the whole-tree
comparison across `--jobs` that the earlier reports record is missing here (`determinism.second_import = "not_run"`). The only
reproducibility evidence is an independent earlier import on the wave-2 branch code (corpus
`ast-survey-agentdojo-p10.pre-integration.partial`, before the cross-branch fixes): the integrated corpus has **3,243 of 3,243 AER
documents and 3,243 of 3,243 SEM documents byte-identical** to it, and every PROV document differs in exactly one value, the
`apv:sha256` of the `agentdojo` rule-catalogue entity (D.6.16 added rules; catalogue version unchanged).
`docs/reports/sem/import-survey-agentdojo-runs.json` is the SEM-stage report of the same corpus.

What this does not show: the model id is in no record (it is read from the results directory name, class I); the code that wrote
the logs is the pinned `agentdojo` submodule commit plus three local patches that are in no pinned tree, so the structural rules are
cited as class-I twins and the run-error outcomes (`utility` False, `security` True) are values the survey's patch imposed.
