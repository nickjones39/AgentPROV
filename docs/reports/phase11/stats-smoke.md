# `agentprov stats` smoke run on two working p10 corpora (phase 11, U6)

Date 2026-10-11, branch `phase-11-u6` at the U6 commits, M2 Max, single process. Read-only: each run was wrapped in
`agentprov.testing.fs_guard.unchanged(<corpus>.partial)` (every file's bytes, sha256, mode, inode and mtime, directory
mtimes included) and no change was found. Output went to the session scratch directory, outside the repository and every
corpus. Numbers only; no content string was printed. Corpus data is untrusted and was treated as data.

Command per corpus (`base` = the four tables; `full` = plus `--artefacts --per-execution`):

```
agentprov -q --progress off stats --corpus ~/.agentprov/corpora/<name> --format json --out <scratch>/<name>-<base|full>.json [--artefacts --per-execution]
```

## Timings and determinism

| Corpus (working, `not_sealed`) | Rows | base | full | full output |
|---|---|---|---|---|
| `ast-survey-agentharm-p10.partial` | 1,056 | 15.9 s | 18.7 s | 12.7 MB |
| `mandate-agentdojo-eval-p10.partial` | 396 | 3.7 s | 5.1 s | 6.3 MB |

The `full` JSON of both corpora was byte-identical across two runs. AER and PROV reads dominate (the AgentHarm AERs are
larger). Extrapolated linearly, a 36k-execution corpus of AgentDojo size takes minutes, single process; `--per-execution`
output grows to tens of rows per execution.

## Results (numbers only)

**ast-survey-agentharm** (`agent-security-tools-survey`, profile `survey-agentharm@1`; registry part `agentharm`,
`supported`): 1,056 records, `n_executions` 1,056, `n_outcome_only` 0; status ok 1,052 / ok_with_issues 4 / failed 0;
completeness `verified_complete` 1,056; PROV output 1,056; failures 0. Register: `map.dangling_source_ref` 4,
`map.inspect.sample_limit` 54, `map.missing_tool_result` 4.
Statements 329,158 (O 147,825; D 162,581; I 18,752), by bundle core 216,424 / inference 0 / assessment 67,326 /
toplevel 45,408; 37 distinct rules, all in the shipped `aprov` catalogue; structural (unclassified) 16,700; the
per-execution table (59,694 rows) sums to the same 329,158.
Field-group coverage: ctx, tooldefs, model_req, model_served, usage, finish, reasoning (704 cells), sysprompt, t_model,
t_tool (766 cells), callid, link, outcome_logged 1.0; sampling 0.810606 (200 cells undeclared `not_recorded`); checker
0.0 (1,056 undeclared); passes, env, payload: no cell. All groups: 14,618 cells, coverage 0.914079, observed share
0.789438, 1,256 undeclared. Unknowns: 74,914 occurrences, 4,669 undeclared. Artefacts: 10 table rows over 3 model
labels; 3 rows `artefact.unclassified.*` covering 35 executions.

**mandate-agentdojo-eval** (profile `mandate-agentdojo-eval@1`; registry part `head`, `supported`): 396 records,
`n_executions` 396, `n_outcome_only` 0; status ok 396; completeness `unverifiable` 396; PROV output 396; failures 0.
Register: `map.accounting_unverifiable` 396, `map.earlier_attempts_unobservable` 396.
Statements 111,502 (O 39,573; D 29,259; I 42,670), by bundle core 39,090 / inference 28,217 / assessment 16,732 /
toplevel 27,463; 42 distinct rules, all shipped; structural 12,678; per-execution table 28,186 rows, same sum.
Field-group coverage: sysprompt, callid, link, payload (369 cells), outcome_logged 1.0; ctx and model_req 0.0 (I);
tooldefs, model_served, sampling, usage, finish, t_model, t_tool, checker 0.0 (`not_recorded`; sampling's 396 are
undeclared); passes 0.0 (`lost`, 396); reasoning, env: no cell. All groups: 6,294 cells, coverage 0.308707, observed
share 0.246584. Unknowns: 28,178 occurrences, 3,638 undeclared. Artefacts: 5 rows, none unclassified.

## Observations for the owners (not acted on here)

- **Undeclared absences** (C.2.3: absent without `unk`) are now measurable per pointer. AgentHarm: the checker actor's
  `/version` and `/code` (1,056 executions) and `/params/transmitted` on 200 executions; Mandate: `/params/transmitted`
  on all 396 calls. C.7.2(3) says producers SHOULD declare these; whether the Inspect and AgentDojo-family mappers
  should add `unk` entries is an adapter question (owners: the adapter sessions; it would change AER bytes, so
  regen-batch.md).
- **AgentHarm `payload`** has no cell (no injection-payload fixture), so it does not appear as `not_applicable`; O.3.5
  names `payload` for AgentHarm as the example of `not_applicable`, which needs an `unk` declaration by the mapper to
  show up in the table.
