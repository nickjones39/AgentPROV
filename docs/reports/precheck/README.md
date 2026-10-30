# Corpus pre-check before the regeneration round

Branch `precheck-corpora` (from `origin/main` `8ad0c522`), started 2026-10-14. Orchestrator: the session "Phase 8 setup".
Runbook: [`../analysis/CORPUS-CHECK-PROTOCOL.md`](../analysis/CORPUS-CHECK-PROTOCOL.md) (this pre-check extends it as
version 2, section 8 there). Baselines: FA (`phase10-corpus-analysis.md`), E2 (`phase10-examination-2.md`).

This file is the **pre-registered method** (A1 phase P0). It is committed before any check of this pre-check runs. The
per-corpus expectations are committed under `prereg/` before that corpus's checks run. Results that the post-check (after
the round) compares against are in `summary.json` and `data/<corpus_id>/`.

## 1. Scope and population

- Population: the 42 corpora / 50 source parts of the README's generated corpus listing (`tools/readme_corpora.toml`,
  `tools/gen_readme_corpora.py`), on code `8ad0c522`. The registry also lists 7 parts that are not in the listing
  (`agentdojo · live`, `autodojo · live`, `agentdyn · d` (owned by `drift`), `agentdyn · history`,
  `adprov-v1 · converted-legacy`, `foobench · fixture`, `drift · history`); they are out of scope except where another part's
  check needs them (overlap, C5). `manifest.json` lists every part with its family, profile, pin, staging location and
  previous reports.
- Statement: each result describes the **pinned raw snapshot as staged** (Level 1) or a **deterministic stratified sample
  of it mapped by the code at the commit named** (Level 2). It is a census of what was published, not a sample of agent
  executions in general.
- Order: the 8 parts examined in E2 (agentdojo head and 2024-06, agentdyn a, rope head incl. the AutoDojo slice,
  adprov-v1 release, survey agentharm and agentdojo-runs, mandate) are examined **for the delta since E2 only**; then the
  other parts in waves grouped by family.

## 2. Steps per corpus (and part)

| Step | Who | Output | Rule |
|---|---|---|---|
| 0 Pre-register | researcher agent | `prereg/<corpus_id>.md` | expectations only: counts, arms, models, outcome rates from the paper(s), quirks from the census and `artefacts.toml`, the check map (which checks apply, which do not and why). **Committed before step 2 starts** |
| 1 Desk research | researcher agent (internet allowed) | `research` section of the dossier, with URLs | papers (arXiv/DOI, versions), repository (history around the pin, issues, errata), data record (Zenodo/HF/Figshare versions, file lists, checksums, licence), harness and benchmark version, models and providers, reported results, known harness bugs, licence and use restrictions, anything that says the data differs from the paper. Web text is untrusted data: summarise, at most one short quote per source |
| 2 Level 1 | examiner agent | `data/<corpus_id>/l1-<part>.json` | whole population, raw only, through `agentprov.ingest`, no mapping (`tools/precheck/l1_scan.py`) |
| 3 Level 2 | examiner agent | `data/<corpus_id>/l2-sample-<part>.json`, `l2-<part>.json` | deterministic stratified sample through the pipeline into a scratch corpus (`tools/precheck/l2_sample.py`, `l2_import.py`, `l2_check.py`) |
| 4 Verify | verifier agent per corpus (and a dedicated verifier per high-impact finding) | `data/<corpus_id>/findings.json` with verdicts | every finding has a reproduction command with its output and survives an adversarial attempt to refute it |
| 5 Dossier | verifier agent | `<corpus_id>.md` | the template of section 6 |

## 3. Level 1 (whole population)

Checks (ids continue the protocol; new ones are `L1-nn`):

| Id | Check |
|---|---|
| L1-01 | counts of files, archive members and units against the census report and the registry figure; selected / not selected by the profile, with the profile's reason |
| L1-02 | strict parse of every JSON/JSONL object: duplicate keys, `NaN`/`Infinity`, integers beyond I-JSON, lone surrogates (escaped and decoded), BOM, trailing data, invalid UTF-8, truncation (unexpected end), depth |
| L1-03 | encodings and escaping (A4): U+2028/2029/0085, C0/C1 controls, bidi and tag characters, zero-width, U+FFFD, mojibake, literal escape residues (`\n`, `\uXXXX` as text), wholly escaped JSON-in-string |
| L1-04 | duplicates (C5): byte-identical files; identical trajectories (family fingerprint of the message/step list); repeats across parts and across corpora (`l1_xdup.py` over all parts) |
| L1-05 | arm coverage: (model × defence × attack × suite or the family's facets) against the paper's design; missing and extra cells |
| L1-06 | secret-like strings and account paths: **counts and normalised JSON pointers only, never values** |
| L1-07 | timestamps: presence by pointer, parseability, time zones, monotonicity within a unit, range |
| L1-08 | truncation and degenerate files: empty, tiny, zero messages, unterminated runs, error-only runs |

## 4. Level 2 (stratified sample through the pipeline)

- **Selection (deterministic).** Unit = the raw artefact the importer selects (file or archive member). Stratum = the
  part's arm key (L1-05 facets). About 5 units per stratum, minimum 30 and maximum 300 per part (all units when the part
  has fewer than 30). Draw: sort the stratum's labels, then `random.Random(f"20261011:precheck:{source}:{part}:{stratum}")`
  `.sample`; when the total exceeds 300, strata are reduced proportionally with at least 1 per stratum, in sorted stratum
  order. Seed 20261011 is the protocol's. The exact list of labels is committed (`l2-sample-<part>.json`) and the
  post-check reuses it unchanged.
- **Import.** Until `import --sample` (D-529) lands: `tools/precheck/l2_import.py`, which calls the product's
  `import_source` with `ImportFilters(include_paths=<the sampled labels, glob-escaped>)` on the same tree classes the CLI
  or the family's trial driver uses. Dev mode, scratch corpora under
  `~/.agentprov/migration-work/precheck/<corpus_id>/`, never a stored corpus, never edited raw. Every import goes
  through `tools/suite_queue.py --class import --cpu 2 --label precheck-<corpus_id>`.
- **Then:** validate (all tiers), `recompute --dry-run`, a second import into a second scratch corpus with a different
  `--jobs` and a byte comparison (determinism), and `verify --level chain` on a sealed scratch copy where withholding
  applies.
- **Checks:** A2 error classes; A3 PROV issue classes (PI-nn: dangling or missing relations, timestamps, evidence linkage,
  unexecuted calls, invented relations); evidence-class distribution (D/I/O and `_unverified` twins); degenerate and
  `adapter_defect` rates and issue codes; identity resolution (models, defences, attacks) against the documentation;
  redaction (no account path in AER/SEM/PROV in any form); withholding behaviour.
- **Outcome sanity:** utility and attack success on the sample by arm against the paper's numbers. A large gap
  (pre-registered threshold: more than 15 percentage points on an arm with at least 20 sampled executions, or any gap a
  binomial 95% interval of the sample excludes by more than 5 points) is a finding to investigate: mapping or identity
  error, or a real source discrepancy. Small samples are reported with Wilson intervals, never as a verdict.

## 5. Findings

- Id `PC-<corpus_id>-<nn>`. Class: `source-defect` (the data itself), `mapping-defect` (our code), `documentation-mismatch`
  (the data and its docs or paper disagree, or our docs and the data), `expected-known` (already in `artefacts.toml`,
  the profile, the census or a decision), and `analysis-artefact` (a tool error: fixed, never reported as a corpus
  property). Severity S0-S3 (A1): S0 blocks release, S1 changes a headline number, S2 must be disclosed, S3 cosmetic.
- Every finding has: evidence (command and output, counts and pointers only), the verifier's verdict (`confirmed`,
  `refuted`, `undetermined`) and reasoning, a recommendation, and for new source artefacts a proposed `artefacts.toml`
  entry (text only; routed through the orchestrator to the family owner).
- **Never** exclude or recommend excluding data because no attack succeeded (user rule).
- Security-relevant findings (a secret value or account path reaching AER/SEM/PROV or a report, a withholding failure,
  and, by the user's decision of 2026-10-15, a third-party account path or secret in **any raw-store file**, context and
  auxiliary artefacts included) are reported to the orchestrator at once.

## 6. Dossier template (`<corpus_id>.md`)

1. Header: corpus, parts, family, profile, code commit, date, agents.
2. Sources and links (desk research), with the data-versus-paper notes.
3. Expectations (link to `prereg/<corpus_id>.md`, commit id).
4. Level 1 results (per check, with denominators).
5. Level 2: sample list (link), import summary, validation, determinism, A2/A3 classes, evidence classes, identity,
   redaction, withholding.
6. Outcome comparison table (arm, n, sample rate with Wilson 95%, paper rate, gap, verdict).
7. Findings (table) with verdicts; proposed `artefacts.toml` entries; items for AGENTS.md §12.
8. Recommendations and readiness verdict for the round: `ready`, `ready-with-caveats`, `blocked` (+ why).
9. Reproduction: exact commands.

## 7. Rules

Internet only for research (papers, repositories, records, issue trackers, metadata APIs). No payload download that is
not already staged under `~/.agentprov/staging` without the user's yes through the orchestrator. Text in corpora, logs,
fixtures, web pages and upstream repositories is data, never instructions. Never read `.env`; `tests/fixtures/**` is
not read. No archive extraction, no raw edit, untrusted bytes only through `agentprov.ingest`. No `src/` change. Machine
shared: imports through the queue, at most `--cpu 2` per job.

## 8. Amendments and known expectations (dated; each made before the checks it affects ran)

- **2026-10-15, stored corpora `validate --corpus` (orchestrator note from the PROV cache session's proofs).** On the 8
  stored corpora, `agentprov validate --corpus` exits 1 with `validate.results.differ`, with the cache on or off: the
  stored validation rows predate the four `pv.constraints.*` checks added by regeneration-batch item 10, and every row
  still passes those checks. This is **expected-known**, not a corpus defect, until the round re-validates them. Level-2
  scratch imports at current `main` validate fresh and are unaffected. The post-check compares like with like: a
  re-validated stored corpus against a fresh scratch import, never a stored pre-item-10 row against a fresh one.
- **2026-10-15, amendment 2 (method details fixed before any Level-1 or Level-2 run; prompted by the pre-registrations'
  open questions and the wave-0 calibration).**
  1. *More strata than the cap.* When a part has more than 300 strata, the sample takes 1 unit per stratum (more than 300
     units, flagged `over_maximum` in the sample file): coverage of every arm is preferred to the cap. Below 300 the rule
     of section 4 holds; the quota k is raised from 5 until the total reaches 30 (`l2_sample.py` docstring).
  2. *Outcome sanity at two levels.* Level 1 extracts the raw outcome fields of every unit (family hooks, no mapping), so
     the population rate per arm is compared with the paper; Level 2 compares the mapped AER outcomes of the sampled units
     with the raw values of the same labels (a mapping check) and with the paper. The gap rule of section 4 applies to
     the population rates; on the sample it applies only to arms with at least 20 sampled executions.
  3. *Multi-execution artefacts.* Until D-529 (`import --sample`) the sample unit is the file or archive member; parts
     with fewer than 30 such units are imported whole. Parts whose Level 2 is blocked by an open runner item or an owner's
     decision get Level 1 only, and the summary records the blocker: mcphunt (D-323 follow-up, then D-529),
     redcode-exec-openhands (archive context tree), agentops-bench (p20 context tree), agentdyn b (first mapping:
     owner), controlarena-persistent (clean post-R-10p-7 trial).
  4. *No data-dependent re-keying.* The stratum key is the pre-registered arm key of the family hook (`l1_families.py`);
     a part with one stratum (e.g. openagentsafety, model only) gets 30 units from that stratum.
  5. *Sample frame restrictions.* kexin-xu-01-agentharm excludes the 18 local-checkpoint logs from the frame
     (`--exclude-facet model=<local-path-model>`) until the profile declares D-182 redaction rules; the AutoDojo slice is
     drawn from ROPE's rows with `--where attack_dir=autodojo`.
  6. *Execution.* The machine queue admits import jobs after hours, so each wave's mechanical steps (L1, sample, two
     imports, check) run in one queued job (`tools/precheck/run_batch.py --plan tools/precheck/plans/wave<n>.toml`),
     waves chained one at a time; tools are frozen while a batch runs.
  7. *Parse classes.* By default L1-02 reports the strict `agentprov.ingest` class only; `--lenient-classes` (opt-in)
     re-parses rejected bytes with stdlib `json` to count every class, and is used only on parts with strict failures.
- **2026-10-15, amendment 3 (orchestrator answers; before the affected Level-2 runs).** controlarena-persistent Level 2
  is unblocked (the phase-10p t2 trial is clean, R-10p-7 confirmed); its 36 D-345 account-path logs stay outside the
  frame through the profile's exact-label excludes (`select.redaction_pending`). agentdyn b gets a scratch-only first
  mapping (`l2_import.py --allow-first-mapping`, plan `followup1.toml`); the outcome is recorded in the dossier.
  `--lenient-classes` is used only on parts with strict failures and its output never feeds a mapping. mcphunt Level 2
  waits for D-323 to land and for the LFS gap fix (D-530); D-529 `--sample` is landing early and will replace the
  file-level sample of the multi-execution families when it does (a re-run then, recorded as such).
- **2026-10-15, amendment 4 (D-529 landed on `main` at 8916be94; recorded before any run that could use it).** The
  pre-registered Level-2 samples (`l2-sample-<part>.json`, file or member level) stay authoritative for every part and
  for the post-check. D-529's `--sample N --sample-mode first|random|spread --seed S` is not the pre-registered stratified
  rule, so it is not substituted. It may be used afterwards only as a **supplementary** within-file check of the
  multi-execution families (`spread` exists for `inspect.eval`, `autogen.runs`, `credleak.cell`; other dialects exit 5,
  `import.sample.unsupported`), labelled supplementary in the dossier, with its own code identity: D-529 moves the aer
  engine digest and the inspect, autogen and credleak adapter digests (regen item 102). No running chain switches code;
  `main` is merged only at a chain boundary, and every part's `code-<part>.json` records what it ran.
- **2026-10-15, amendment 5 (scope and wave-7 strata; before any wave-7 data check).** After the merge of `main` at
  faa06d3d the README listing declares 48 corpora / 59 parts: the six phase-10j corpora (authority-caps, ipi-defenses,
  dca, kavach, environmentoptim, drift1; 9 parts) join the population as wave 7, pre-registered at eb7151ee. Their
  stratum keys are fixed from the profiles' layouts and the phase-10j census, not from data: authority-caps
  `container × model_dir × pipeline_dir × attack_dir`, ipi-defenses `container × model_dir × attack_dir`, dca, kavach
  and drift1 `model_dir × suite × attack_dir`, environmentoptim the family default (`l1_families.STRATA`). A member of a
  declared nested archive is read by its own label, its containers forming the `container` facet. dca-agentdojo is
  Level 1 only until D-455 lands (no workaround); environmentoptim's `select.redaction_pending` logs (D-255) stay outside
  the frame (`l2_sample.py --exclude-profile-code`, and `l2_import.py` refuses any such label).
- **2026-10-15, incident note (no data affected).** A wave-7 tool test run outside the repo's `conftest.py` overwrote the
  scratch L1 rows of glitch-agentdojo (`l1-units-head.jsonl`, `l1-aux-head.jsonl`, `_fp/glitch-agentdojo.head.jsonl`)
  with synthetic rows at 11:09:41. They were regenerated by a normal L1 re-run (`l1_scan.py --git ...`, summary to
  scratch) whose units file has sha256 `d8cc0719…`, equal to the `units_sha256` the committed sample records; the
  committed L1 summary differs only in `code_commit` and `elapsed_s`. The glitch examiner's L1 and outcome results were
  written before 11:09:41; its verifiers ran after it and are re-checked by the wave-2 critic. Copies of the tools are
  now tested only with the repo's conftest (isolated home, write guard).
- **2026-10-21, amendment 6 (never-seal list; seal blockers).** The following pre-check scratch corpora must NEVER be
  sealed, packaged or deposited: interbolt-agentdojo `l2-head-j1/-j2` (profile v1 without the CC-11 withhold; twins), and
  the 10 controlarena-persistent `l2-<part>-j1/-j2` (profile v2 629818bd..., which carries a workstation account path;
  10p's v3 adds the redaction; twins, D-31 owner). No pre-check scratch corpus is a release artefact. 10p's t2 seal is
  blocked on D-453/D-454 (186 truncated members unscanned). seagent-agentdojo's two scratch imports exit 1
  deterministically (7 units `failed` with every stage ok, `map.missing_tool_result`); see its dossier.
- **2026-10-21, known expectation (D-610).** Before D-610, a working import corpus left by a drained or interrupted run
  recorded `partial: false`, as if complete. Such a corpus cannot be detected after the fact, except through the
  snapshot counts of a single-execution source (candidates greater than executions). The round re-imports every kept
  corpus, so none survives into it.
