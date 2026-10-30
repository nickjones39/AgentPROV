# Phase 10p: census of the control-arena persistent-state archive (Inspect)

Branch `phase-10p-controlarena`, 2026-10-13. Source: HF dataset
`idacy/control-arena-persistent-state-eval-archive-2026-07-30` @ `84d39e0a485d7ea6ca10f4ceb2a3fbf88dab0e62` (MIT, card).
Phase-10e rank 13 (D-145; card §3.6 of `../systematic-search/candidates/phase10e-candidates.md`). Decisions D-340–D-348
were **approved by the user on 2026-10-13** (section 6; option (a) for D-344); D-349 is reserved. The profile, registry
entry, tests and spec section followed (section 8); the scratch trial waits for R-10p-6 (section 7). Third-party data, read in memory through
`agentprov.ingest`; nothing in it was run, installed, extracted or followed (the archive's READMEs give extraction commands;
they were not used).

**Secrets and account names.** Every sample carries planted credentials (section 4). No credential value, and no
workstation account name or path that contains one, appears in this report, the census files or the commits. Credentials
are described by shape class and JSON pointer, account paths by structure (`/Users/<account>/…`) and an 8-hex digest.

Work directory (outside Git): `~/.agentprov/migration-work/phase10p/` (`scripts/census.py`, `aggregate.py`,
`accounts.py`, `apikey_digests.py`; `census/full/*.census.json`, `census/aggregate.json`, `census/accounts2.json`).
Staging copy: `~/.agentprov/staging/10p/hf_idacy_control-arena/`.

## 1. Acquisition

With the user's large-download consent of 2026-10-13 (full snapshot), all 72 files of the pinned tree were staged:
6,835,660,481 B (70 downloaded, the 2 loose logs copied from the phase-10e staging). Each file was checked against the
tree listing that phase 10e saved at the pin (LFS objects: sha256 = the LFS oid; git files: blob sha1 = oid; sizes
equal). One record in `~/.agentprov/cache/acquisitions.jsonl` (session `phase-10p`). The three logical zips rebuilt
from their parts match the archive's own `logs_tmp_zips/SHA256SUMS`.

## 2. Method

`census.py` opens each container the way an import would: the three split zips with `open_split_zip` (D-243), each
tar.zst with `open_archive` (D-240), each `.eval` with `open_zip`, all with the default `IngestLimits` and in release
mode. Members are gated with a profile-like selection (`.eval` and nested `.zip`), so their dispositions and codes are
those an import would record. **Nested zips** that the default limits reject were then re-read with a census-only
limits object (member bound 4 GiB, depth 3), so that their logs could be counted and compared; that read is census
only. Per log: header facts (producer, models, roles, plan, scorers, status, commits). Per sample: counts, digests
(`msg_digest` over role, text and tool calls, ids excluded; `uuid`), item-16 link checks, strings over 1 MiB (item 28),
secret-like strings by class and pointer, account-like paths by pointer. `aggregate.py` classifies each log once, in
container order (split zips, their nested zips, tars, loose): `byte_duplicate` (sha256 seen), `no_header`, unreadable
(`zero` / `truncated`), or `original`. Equal message text with distinct sample uuids is not a duplicate (D-181).

## 3. What the archive holds

### 3.1 Containers

| Container (pin path) | Bytes | Inspect logs (members) | Other members |
|---|---:|---|---|
| `logs_tmp_zips/logs-20260610T154758Z-3-001.zip` (8 parts) | 2,147,474,457 | 285 direct `.eval`; 4 nested zips | `stdout.txt` 417, `stderr.txt` 492, `run_eval.py` 429 |
| `logs_tmp_zips/logs-20260610T154758Z-3-002.zip` (8 parts) | 2,147,478,676 | 70 direct; 1 nested zip | run files 548, batch `config.json`/`results.json`/analysis CSV 35 |
| `logs_tmp_zips/logs-20260610T154758Z-3-003.zip` (3 parts) | 781,063,343 | 334 direct | run files 286 |
| `logs_batch_runs-20260730.tar.zst` | 885,551,965 | 110 | 220 run directories (`stdout.txt`, `stderr.txt`, `run_eval.py`), 4 batch `config.json` + `results.json` |
| `agentic_auditor_logs-20260730.tar.zst` | 22,039,676 | 1 (the auditor's input log) | agentic-auditor records (3.4) |
| `apr2026_backup_public_only_data-20260423.tar.zst` | 732,479,131 | 227 inside 4 nested zips | 3,917 working-directory files (results, plots, CSV, code) |
| `link_tracker_rescore_finals-20260730.tar.zst` | 46,160,204 | 0 | 136 rescore `results_*.json` |
| `xx_working_dir_delta_data-20260730.tar.zst` | 10,144,540 | 0 | 82 working-directory files (one 3 KB nested zip, no log) |
| 2 loose `.eval` under `logs_20260315_unique/` | 15,015,700 | 2 | — |
| loose analysis files (`logs_march_rescored/`, `logs_Josh3_analysis_csvs/`, `paper_figures/`, CSV, JSON, README) | ~49 MB | 0 | rescore result JSON 15, analysis CSV 8, figures 12, one benchmark-cache JSON |

### 3.2 Logs and samples by class

| Class | Readable with today's ingest | Only inside nested zips | Notes |
|---|---:|---:|---|
| **original** (logs / samples) | **436 / 2,267** | **928 / 3,475** | 1,364 logs, **5,742 samples** in all |
| byte duplicate | 5 / 25 | 199 / 969 | 179 of the nested ones are the whole apr2026 backup; collapse under D-202/H.7.2 |
| no `header.json` (unfinished; journal only) | 3 / 9 | 7 / 11 | the 2 loose logs are of this kind; `select.dialect_planned` by the reader |
| zero-byte `.eval` | 172 | 48 | not a zip; 105 of the 220 have a complete copy (same file name) in a nested zip |
| truncated `.eval` (local header, no central directory; size a multiple of 256 KiB) | 186 | 0 | 174 of 186 have a complete copy in a nested zip |

Readable now, by container: split zip 3-001 132 logs / 660 samples, 3-002 31 / 153, 3-003 162 / 810, `logs_batch_runs`
110 / 638, the auditor's input log 1 / 6. Nested-only originals by nested zip (all inside the split zips):
`logs/positional_f3m1.zip` 515 / 1,499; `logs/honest_all.zip` 166 / 796 (+3 logs, 13 samples, see below);
`logs/2026-01-15_last-two-days.zip` 123 / 562; `logs/gradual_f3m1.zip` 120 / 600; `logs/run_2.zip` 1 / 5. The apr2026
backup adds no original log.

**Why the nested zips are blocked.** Four are over `max_member_bytes` (256 MiB; 312 MB to 2.09 GB,
`ingest.archive.size`); `run_2.zip` (2.9 MB) is within it, but its logs would sit at archive depth 3 > `max_archive_depth`
(2). Every log inside them is a zip itself. So 3,475 of the 5,742 samples (61%) need a bounded deeper and larger
nested-zip read in `ingest/` (routed, section 7).

**No rescorings among the logs.** No log repeats another log's samples with other scores (by uuid or `msg_digest`); the
three logs that share samples with another log share only 1-message samples that errored before the agent acted
(same text, distinct uuids, D-181). Rescoring exists only as result JSON outside Inspect logs (`results_*.json`).

### 3.3 The original samples (5,742)

- **Producer band:** `inspect_ai` 0.3.159, log version 2, in every log with a header (1,364); only `inspect_ai` in
  `eval.packages`; `control_arena` plan `inject_previous_state → control_solver → extract_state_and_pr_diff`; 13
  distinct `eval.revision` commits; logs created 2026-01-10 to 2026-06-05; status `success` 1,338, `error` 26.
- **Models:** the untrusted (agent) role is `anthropic/claude-sonnet-4-5-20250929` (1,354 logs) or
  `mistral/mistral-large-latest` (10); the trusted role, used only by the scorers (post-hoc monitors), is `openai/gpt-4o`
  (1,185) or `openai/gpt-4.1-mini-2025-04-14` (179). **`eval.model` is `none/none` in 153 distinct logs** (152 original) that set
  `model_roles`; they are real runs (17,762 untrusted model calls in their 704 samples), not mock runs, so D-142's mock rule
  does not apply. Model events: solver spans call only the untrusted model, scorer spans only the trusted one.
- **Setting and modes:** `vibe_coding_persistent` (5,633 samples) and `vibe_coding` (96); `eval_mode` attack 4,351,
  honest 1,378; 12 side tasks (triggered-exfil 1,895, config-telemetry 1,058, malicious-package 500, secret-exfil 500,
  api-token-exfil 280, gradual-api-token-exfil 88, six others with 5 each); 54 main tasks. A log holds one PR sequence
  (1 to 6 samples, one per PR) with persistent state carried between samples.
- **Trajectories:** 5,679 of 5,729 classified samples have tool calls (220,784 calls; `bash`, `text_editor`, `python`,
  `submit`, `private_think`); the other 50 errored before the agent acted. 123 samples have an `error` event, 445
  `sample_limit` events. Events: `model`, `tool`, `sandbox`, `state`, `store`, `score`, `span_*`, `sample_init`,
  `logger`, `error`, `sample_limit`.
- **Item 16 (parallel calls):** 13 parallel batches in 6 samples; 20 of 220,590 tool events name the first result of
  their batch (the `execute_tools` defect, inside item 16 (b)'s range); all other `message_id`s agree. No duplicate
  tool-call ids.
- **Item 28 (strings over 1 MiB):** 28 strings in 22 samples (`/attachments/<key>` 24, `/metadata/pr_diff` 2,
  `/store/submission_diff` 2).
- **Quirks seen:** one tool call whose function name is a prose sentence (model output, kept verbatim); `submit` is a
  tool of the control solver (3,696 calls).

### 3.4 The agentic auditor

`agentic_auditor_logs-20260730.tar.zst` holds one Inspect log (the auditor's input, 6 samples, counted above) and the
auditor's own records: cohort manifests, configs, `auditor_scores.jsonl` and per-cohort score files. The auditor is a
tool-using LLM: 3,053 score rows carry 13,757 commands, each with `argv`, `cwd`, `output`, `exit_code`, `blocked`, and
the final `raw_response`, but not the model's input at each step. That is a partial trajectory (D-141: EX-FMT) in a
format outside the Inspect family.

## 4. Planted credentials

The archive's README calls them benchmark-internal synthetic values (a capture domain and generated `api_key`
variables). Counted by shape class, never printed (`census.py`):

- **Every sample** has an OpenAI-like key in `/metadata/API_KEY` (5,729 of 5,729), with copies in the `sample_init`
  and `state` events. The Inspect mapper copies sample metadata into `ext.inspect.sample_metadata`, so the value reaches
  every AER.
- Agent-handled values (read, written or exfiltrated in the side tasks) in some samples: OpenAI-like 79,520 strings,
  AWS access-key shape 12,990, GitHub token 10,861, Google API key 5,580, private-key header 3,431, Slack token 699, in
  `/events/*` (input, output, cmd, result), `/messages/*`, `/attachments/<key>`, `/metadata/pr_diff` and
  `/store/submission_diff`.
- Distinct `API_KEY` values (digests only, readable containers, `census/apikey.json`): 442 over 2,293 samples, each
  67 characters with the `sk-` prefix and shared by at most 6 samples: one generated key per run, reused across its PR
  sequence. No literal marker covers them; a bounded pattern does (D-344).

## 5. Workstation account paths

A macOS account path (`/Users/<account>/…`, one account, digest prefix `ce5bef8c`) occurs in 36 logs: in 9 headers at
`/eval/metadata/micro_protocol/prompt_file`, and in 107 samples of 29 logs in error tracebacks (`/error/traceback`,
`/error/traceback_ansi` and the same under `/events/*/error/`). `/home/<name>` paths occur only in model-visible content
(tool inputs and outputs, messages, PR diffs, attachments), with placeholder names (`user`, `admin`, `john`, `alice`,
`testuser`, …) and a few unidentified ones: sandbox and generated code, not host fields.

## 6. Decisions (D-340–D-348; user-approved 2026-10-13, as proposed here; DECISIONS.md has the final text)

- **D-340 (execution unit and counting).** One Inspect sample (epoch) of a log with a `header.json` in the band is one
  execution. Counted: attack and honest samples alike, errored samples and samples without tool calls (never an outcome
  rule); the 152 original `none/none` logs with `model_roles` are real runs and are counted. The source counts **5,742 samples
  in 1,364 logs** (replacing the phase-10e lower bound ">=802 logs"); **2,267 samples in 436 logs** are importable with
  today's ingest.
- **D-341 (one corpus, several snapshots).** Corpus and source id `controlarena-persistent`, own permissive corpus
  (MIT), registry status `planned`, one profile with one part per pinned container (D-202 snapshots; D-108 one pin per
  part): `zip-3-001`, `zip-3-002`, `zip-3-003` (split-zip pins, D-249: logical file, and each part's name, size and
  sha256; the parts' total, 5,076,016,476 B, needs the large-download consent), `batch-runs` (tar.zst), `auditor`
  (tar.zst; only its one log is selected), `loose-1` and `loose-2` (the two unfinished logs, pinned so that the
  register records them). Byte-identical logs collapse across snapshots (H.7.2).
- **D-342 (excluded by rule, never silently).** In the pinned containers: non-log members (`stdout.txt`, `stderr.txt`,
  `run_eval.py`, batch `config.json`/`results.json`, analysis CSV) are `not_selected` (batch config and results may be
  declared context artefacts; inert, as for every Inspect profile); unfinished logs `select.dialect_planned` (reader);
  zero-byte and truncated `.eval` members keep the code the import records for them (expected `ingest.archive.format`;
  confirmed in the trial import); the nested zips stay blocked with their ingest code until ingest supports them (no
  profile glob reaches into them before that). Not pinned, with the reason recorded in the profile and the screening
  record: the apr2026 backup (its logs are byte duplicates of the split zips' logs, or empty), the rescore result JSONs
  and analysis files (outcome-only records, EX-NOLOG by D-141), the working-directory delta (no log), and the auditor's
  own records (partial trajectory in another format, EX-FMT by D-141).
- **D-343 (producer band and family values).** `producer_band = {inspect_ai = ["0.3.159"]}`, `log_versions = [2]`,
  `span_roles = {solver = "agent", scorer = "judge"}`, `submit_tools = ["submit"]` if the trial shows control_arena
  removes the submit result (else none). No attack is declared, so `task.attack_id` stays unrecorded (as fragfuse,
  D-184); `eval_mode`, `side_task_name` and `main_task_name` stay in `ext.inspect.sample_metadata`. No semantics profile
  (SEM skipped, as whistlebench).
- **D-344 (withholding).** A `[withhold]` table with D-234 pattern rules for the key shapes seen (OpenAI-like `sk-`,
  AWS access key, GitHub token, Google API key, private-key header, Slack token; `reason = "secret"`). Because
  `/metadata/API_KEY` reaches every AER, the derived-hit escalation withholds **every execution** at a release seal
  (D-235): a public release would hold metadata only. Alternatives for the user: (a) this, recommended (the README's
  "synthetic" is the depositor's statement, D-146 asks for a policy); (b) object scope (still every execution, through
  the derived hit); (c) a mapper change that does not copy `API_KEY` into the AER (routed; the agent-handled values in
  events would still withhold the samples that hold them); (d) withhold nothing on the README's word (rejected by me:
  gitleaks at G.9.4 would flag the release).
- **D-345 (account paths).** As phase 10h (D-182, D-186): raw bytes keep the paths (invariant 3). The header field
  (`micro_protocol.prompt_file`, 9 logs) and the error tracebacks (107 samples) are copied into the AER today. Until the
  regen-batch redaction (D-182) covers these two pointer classes, the 36 logs stay out of every import, including the
  scratch trial (the profile lists them by exact path with a recorded reason, or the trial filters them; user's choice).
- **D-346 (fixtures).** Synthetic only (as D-185): every real sample carries the planted key, and the smallest complete
  real log is over the 512 KiB per-source cap (D-360). Built at test time from the census schema (control_arena header
  with `none/none` plus `model_roles`, solver/scorer spans, a test-made sentinel in `API_KEY`), so the committed bytes
  under `tests/fixtures/inspect` grow by 0 B or by one small generator input.
- **D-347 (what the trial import is).** Scratch corpora under `~/.agentprov/migration-work/phase10p/`, release mode,
  readable containers only, minus D-345's logs; checks: accounting, link issues (item 16's 20 events), `recompute
  --check` 0 differences, and the release seal's withheld count against D-344's prediction.
- **D-348 (counting record).** The screening record of the source is updated to "5,742 samples (2,267 importable
  now)" with this report as `runs_basis`; inclusion is unchanged (D-144).
- **D-349:** reserved.

## 7. Needs routed (through the orchestrator; not this session's files)

- **R-10p-1 (ingest-formats):** a bounded nested-zip read for 3,475 samples: zips inside a split zip that are larger than
  `max_member_bytes` (312 MB to 2.09 GB) and `.eval` logs at depth 3 (a zip in a zip in the split zip; also a zip in a
  tar.zst). Bounded by a declared nested-archive pattern in the profile, not by raising the global limits.
- **R-10p-2 (regen-batch, Inspect mapper):** `eval.model_roles` is not mapped. The agent actor's `model.requested` is
  `eval.model`, i.e. `none/none` for 152 original logs whose agent is the `untrusted` role (served models are right per
  call). Also: item 28's evidence gains 28 strings over 1 MiB in 22 control-arena samples.
- **R-10p-3 (regen-batch, redaction D-182):** two more pointer classes for account paths:
  `/eval/metadata/micro_protocol/prompt_file` and `error.traceback(_ansi)` in samples and events.
- **R-10p-4:** not routed (the user chose D-344 (a)).
- **R-10p-5 (core: register):** the select code `select.redaction_pending` for executions a profile holds back until a
  pending redaction covers them (D-345; `corpus/register.py`, `adapters/profiles.py`, HL H.6.3). Routed to the R-10k-1
  runner session. **Landed 2026-10-13 as D-324**; profile version 2 (2026-10-14) holds the 36 logs by exact label.
- **R-10p-6 (runner, with R-10p-1):** the runner refuses an archive input whose members belong to a container dialect
  (D-200: "an archive of a container dialect ... is refused (exit 5)"), so no `.eval` member of the split zips or the
  tar.zst inputs can be imported yet: 0 of the 2,267 samples. Routed to the ingest-formats-3 session (one nested-archive
  design for depth 2 and depth 3).

## 8. Profile, tests and trial status (2026-10-13)

- **Profile** `src/agentprov/adapters/inspect/profiles/controlarena-persistent.profile.toml` (version 1): five parts and
  pins (D-341; the two loose logs are not pinned, see DECISIONS D-341 "found while building it"), selection
  `**/*.eval`, band 0.3.159, quirks with the census counts of the readable containers, and the `[withhold]` table of
  D-344 (validated by `corpus.withhold.policy_of_profile`). Registry: five `planned` parts of corpus
  `controlarena-persistent`, no semantics.
- **Tests** `tests/adapters/inspect/test_phase10p_controlarena.py` (synthetic only, D-346; 0 B of fixtures): pins and
  part totals, the closed family schema, quirk rules, registry parts, the selection, each withholding rule against a
  run-time sentinel and a clean sample, the key reaching the AER (D-344's prediction), a control-arena-shaped log mapping
  to valid AER (agent `requested` = `none/none`, R-10p-2), out-of-band and header-less logs `select.dialect_planned`,
  empty and truncated logs not mapped, the trial tool's hold entries, the staged auditor input against its pin (skipped
  without the staging copy), and the strict xfail for R-10p-6.
- **Profile version 2 (2026-10-14):** D-345's 36 logs are exact-label excludes with `select.redaction_pending` (D-324);
  28 of the labels are member labels inside zip-3-001's nested zip `logs/2026-01-15_last-two-days.zip`. The trial tool
  no longer needs `--hold`.
- **Trial (D-347): not run.** The first attempt (part `auditor`) stopped at the runner's refusal of a container dialect
  inside an archive input (R-10p-6). When R-10p-6 lands: `uv run python tools/inspect/phase10p_trial.py import --corpus
  ~/.agentprov/migration-work/phase10p/corpora/t1 --input ~/.agentprov/staging/10p/hf_idacy_control-arena`.
- **Predicted, before any seal:** the trial maps 2,232 samples in 429 logs (2,267 / 436 minus D-345's 7 original logs
  and 35 samples; the 5 byte-duplicate logs collapse, H.7.2); the pinned containers' one unfinished log is among the 8 held logs; 358 `.eval` members carry an `ingest.*` code; **a release seal withholds all 2,232 executions**
  (D-344: the `sk-key-shape` rule hits every AER through `ext.inspect.sample_metadata`).
- **Screening record (D-348):** `merge_screen.py` now counts the source on 5,742 samples. The generated tables move:
  distinct runs kept 301,321 → 306,261 and current plus included candidates 422,932 → 427,872 (`sensitivity.md`); the
  source no longer falls below a uniform 1,000-run threshold. The phase-10e candidates report keeps its historical
  ">=802" and 78,001 figures.

## 9. Scratch trial t1 (2026-10-14; D-347)

`tools/inspect/phase10p_trial.py import`, release mode, profile version 2 (`sha256 629818bd…`), the five parts as
snapshots of `~/.agentprov/migration-work/phase10p/corpora/t1` through the job queue (class `import`, 8 workers), on
origin/main 891ffcd1 (ingest-formats-3). 52 minutes wall clock (zip-3-001 885 s, zip-3-002 748 s, zip-3-003 227 s,
batch-runs 520 s, auditor 17 s).

- **Selection reconciles with the census exactly:** 5,522 executions = 5,742 original samples − 220 samples of the 36
  held logs (36 `select.redaction_pending` rows). `select.dialect_planned` 8 (the unfinished logs), `ingest.archive.format`
  189 and `dedup.collapsed` 265 (byte-identical logs, and identical empty `.eval` members collapsing on one digest), stage
  rows `aer`, `prov` and `validation` ok for all, 56 validation checks with 0 failures. The nested zips were read (D-382):
  zip-3-001 2,441 and zip-3-002 1,698 executions.
- **Every execution is degenerate (`map.adapter_defect`, detail `aer.write.invalid`).** Cause (diagnosed in memory on
  the auditor's input log, finding codes only): the Inspect mapper's `_sandbox` emits an `inspect:sandbox_output`
  artefact with `ev = "O", by = "source"` even when the sandbox event has no string `output` (e.g. `write_file`), so
  every asserted field of that artefact is `D` and the writer refuses the record set (AER-V12 `by_without_bare_O`);
  the runner then seals the whole sample degenerate. Every control-arena sample holds such an event. Routed R-10p-7 to
  the Inspect mapper owner (regeneration batch); `test_a_sandbox_write_without_output_maps_to_valid_aer` is a strict
  xfail that reproduces it on a synthetic sample. Other Inspect corpora are affected only if their logs hold sandbox
  events without output (the survey and AgentHarm logs have none; to be checked by the mapper owner).
- **Not done yet:** the release seal's withheld count (D-344 predicts every execution) and `recompute --check`; both
  wait for R-10p-7, since degenerate AERs do not hold the samples' metadata.

## 10. Trial t2, recompute and the seal; profile version 3 (2026-10-15 to 2026-10-21)

- **Trial t2** (profile version 2, after R-10p-7 landed at 714e8187; `corpora/t2`): all five parts exit 0. 5,522
  executions mapped, derived and validated; 0 degenerate, 0 failures. 2,300 sealed clean, 3,222 with issues:
  `unexecuted_tool_call` 3,303 issues (3,222 under `inspect.tool_event_is_execution@1`, 81 under
  `inspect.message_copies_share_calls@1`), `inspect.unmapped_event` 2,284, `inspect.sample_limit` 403,
  `accounting_inconsistent` 728 issues in 364 samples (`aer.acc.tool_results_linked@1`), `inspect.content_not_inlined`
  20. The unexecuted calls are almost all `bash`. In 2,855 later-PR samples they fit control_arena's
  `inject_previous_state` (the earlier PRs' history is replayed into each sample, so those calls ran in an earlier
  sample). The 367 `PR0` samples with them, and all 364 inconsistent ones, are not explained by replay; the mapper owner
  is asked to confirm the semantics. Calls without execution evidence are declared unexecuted, which is conservative.
- **`recompute --dry-run --strict`** on t2: 5,522 identical, 0 unexplained, 0 unverified, no rule drift.
- **Release seal** of t2: refused before writing (`PackageRefusedError`: 186 stored archives not readable in decoded
  form, D-450). They are the 186 truncated `.eval` members; D-453 (partial decoded scan) and D-454 (auto-withhold) are
  not on main yet. The withheld count waits for them.
- **Release seal t2b** (2026-10-21, with D-453/D-454 on main): the withholding stage passed, then the seal was refused
  before writing (`PackageRefusedError`, code `pin`: "a Hugging Face snapshot holds its pinned file and that file's
  members only"). Seal finds a snapshot's origin by going up one container level from each primary object. Here every
  primary is a member of an `.eval` zip, which is itself a member of the tar.zst, the split zip or a nested `logs/*.zip`
  (D-380/D-381). So all five snapshots see only `member` origins (auditor 1 container, batch-runs 110, zip-3-001 515,
  zip-3-002 556, zip-3-003 167). This is a seal defect affecting every archive input with container members. It is routed
  to the corpus/package owner through the orchestrator: walk the chain to its root and match each root against the
  snapshot's pin. With the user's OK, t2 was then moved to the Trash to free disk space (2026-10-21). The withheld
  counts and the `verify --level chain` result will come from the t3 seal (the same data, profile version 3) once
  the fix lands.
- **Trial t3** (profile version 3, 2026-10-21): 5,742 executions, the census's 5,742 original samples, so nothing is
  held. 0 degenerate, 0 failed. 106 values were redacted (`map.inspect.value_redacted`, D-349). The account-segment scan
  of t3 (the same method as for t2, 11,492 files) found 0 hits. Unlike t2, t3 holds the 36 account-path logs, so this
  shows the redaction keeps the segment out of every derived file.
- **`recompute --dry-run --strict` on t3: stopped by user decision (2026-10-22), no result.** The mapping stage was
  complete (5,742 of 5,742 re-imported). The PROV stage was at about 36% (2,048 of 5,742 admitted) after 7.7 hours,
  held back by the memory admission budget, so it needed another 9 to 10 hours. It tested pre-integration code, and the
  pre-round review's re-map, recompute and determinism proofs cover reproducibility. The t2 recompute (5,522 identical)
  stands for version 2.
- **Release seal of t3** (2026-10-22, with the snapshot-chain fix 265d1ce8): sealed. The first attempt was refused by the
  card lint on the trial script's own scratch card (a literal number), before anything was written; the corrected card
  sealed.
  - All 5,742 executions are withheld (D-344 (a): every sample holds a planted key), so 0 are released.
  - 7,339 objects are withheld: 5,940 by profile rule (`sk-key-shape` 5,828, `aws-key-shape` 99, `private-key-header`
    7, `github-token-shape` 6) and 1,399 as containers of withheld members (D-315). 186 archives were scanned partially
    (D-453), and none is unscanned.
  - Released: 1,391 files, 55.9 MB, of which 1,367 raw objects: 1,364 `header.json` members and 3 tiny `.eval` members
    (two truncated zips and one empty file, 3,389 bytes).
  - `verify --level chain`: passed, with 0 failed and 0 unverified. 1,391 of 1,391 files matched, and 1,367 raw objects
    were re-hashed.
- **Finding: 9 released `header.json` objects hold the workstation account segment.** They are the only released objects
  with any `/Users/` segment, and all 9 hold the same account. The derived files hold none (the t3 scan above). Profile
  version 3 withholds only secret shapes (at execution scope), so under D-186 (c) these raw objects ship as they are.
  D-604 has since changed this: raw objects holding a third-party account path are withheld at object scope, and only
  residue that no exact rule can target ships as pinned. These 9 can be targeted exactly. The fix is a profile rule
  (version 4, D-31 bump, since t3 recorded version 3), which needs the user's decision.
- **Profile version 4** (user decision 2026-10-22): one object-scope rule, `users-account-path`
  (`/Users/[A-Za-z0-9._]{1,64}[^A-Za-z0-9._\-]`, reason `personal_data`). Version 3 is archived (D-31). The pattern
  cannot match the redacted form `/Users/account-<span12>`: the fragfuse form would match it and escalate every redacted
  AER (D-235). Proof on the sealed t3 and its sidecar, using the shipped parser (`policy_of_profile`'s rule regex): it
  hits 9 of 1,367 released raw objects and 107 of 7,339 withheld ones, which are exactly the files that hold the account
  (the digest scan), and 0 of the 11,484 AER and PROV files. Execution counts do not change, because every execution is
  withheld under D-344. No re-seal was needed. Held with item 110.
  - Review follow-up (same day): the label becomes the D-604 form `/Users/acct-{span12}`, because the release scan's
    `account-path` rule reports `account-<12 hex>` and exempts only `acct-<12 hex>`. The rule's recorded limits are a
    name holding `-` and a name at the end of an object (the bounded grammar has no lookahead or anchor). The pinned
    bytes hold neither, and the release scan reports both at a deposit (tested). The proof figures above stand: the
    pattern is unchanged, and the new label holds a `-` like the old one.
- **Profile version 3** (D-349): the 36 holds become one redaction rule; version 2 is archived. The scratch import
  with version 3 (t3), its seal and the account-segment scan follow.
- **Scratch corpora under version 2 (privacy note, D-31 review of D-349).** Twelve scratch corpora record version 2:
  phase10p `t1` and `t2` and the precheck `l2-*` corpora. Version 2 held the 36 account-path logs out, so their derived
  files do not hold the account path: the account-segment scan of `t2` (every AER, PROV, register, index and
  validation file, 11,052 files; plain, JSON-escaped, pointer-escaped and percent-decoded forms, matched by digest)
  found 0 hits. Their raw stores hold it, as every version's does (raw ships as it is, D-186 (c)). They are superseded
  (220 samples held, `t1` all degenerate) and are never sealed or deposited; the round imports at version 3.
