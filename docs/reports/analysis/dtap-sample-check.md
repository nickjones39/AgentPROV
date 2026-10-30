# DTap-Bench sample corpus: corpus check (protocol v1)

Date: 2026-10-12. Analyst: Claude (worktree session `agent-ab75fb7fd9c5ba49e`, read-only on corpora and staging data).
Code: `main` @ `2c95a5b` (rebased; clean tree). The corpus was built on the same commit. No file under `src/` was
changed by this check. Method: `docs/reports/analysis/CORPUS-CHECK-PROTOCOL.md` (version 1, cited as "protocol §n").
Data directory: `docs/reports/analysis/dtap-sample-check-data/` (counts, normalised pointers, execution ids and
truncated digests only). Per-execution outputs: `~/.agentprov/migration-work/phase10b/check/` (not committed).

Sections 1 and 2 were written and committed **before** any check ran (pre-registration, protocol §2.1 step 1). Results
begin in section 3.

---

## 0. Summary

Written after the checks. Corpus: `dtap-sample-500` (501 executions: 498 `agent_execution`, 3 `outcome_only`; 499
with SEM and PROV; ten harness/model pairs, five splits, 1,000 input files), built from the pinned staging trees with
1,017 + 6,682 files pin-verified, in 897 s with 4 workers.

**Clean.** Every zero-tolerance check gives 0:
- X01 strict parse, X02 second JCS, X05 framing and X06 (`jsonschema`, 23,513 AER records);
- U02 (lone surrogates), U03 (U+2028/2029/0085), U12 (pointer digits);
- P01-P05 (no strict-order or other cycle, no C51/C26/C24 violation, no entity with two generators after expansion);
- P06 (323,386 inference-bundle arguments resolve in their application view);
- R01a-R01c and R01l: no `wasInfluencedBy`, no PROV time attribute, no I statement in core, tool executions `use` only
  their request;
- D01: 499 × 6 configurations = 2,994 re-derivations byte-identical, tiers 3-4 equal in 499 of 499 (95 % bound 0.60 %);
- D02 (new DTap re-map helper): 498 of 498 AERs reproduced from the raw objects;
- worker count: a second import with 1 worker gives 8,994 of 8,994 files byte-identical, except the input-tree path in
  `corpus.json`;
- IM01 recompute: 499 of 499 identical.

**DTap-specific checks (independent re-implementations from D.16): 0 mismatches.**
- R03 analogue: 10,108 raw steps against AER.
- Re-pairing: 3,086 links; every one of 136 multi-call batches carries its `pairing_ambiguous_batch` issue.
- Markers: 3,263 statuses recomputed.
- Exposure: 344 payload fixtures; every observed class is backed by a match in logged content.
  `configured_only` and `partial_match` are I and sit only in the assessment bundle; the observed classes are D.
- Join: 443 tiers recomputed.
- Judges: 499 judge-to-attempt links recomputed. 19 audit-corrected judgements keep both values.
- The R01n applies-check holds for 7 issue codes.
- DT01: no `env_vars` key or value in any derived file, except values that the run's own raw log already holds
  (79 AERs; class a).
- Calibration: C00 found 15 of 15 faults on Mandate (identical to the baseline). The DTap checks found 15 of 15
  injected faults.

**Findings.**
- No defect in AER, SEM or PROV content.
- (b) 4 items, none changing an existing corpus:
  1. the dtap artefact catalogue gives misleading labels (1,229 findings unclassified; broad detector rules claim
     findings that belong to other entries);
  2. auxiliary artefacts are recorded as `application/octet-stream`, which gives P07 media-type variants;
  3. the D.16.6/D.16.8 wording;
  4. the analysis tools.
- (c) 4 questions: shared `raw:` entity variants (P07: 61 keys; the phase-10 baseline had 0 within a corpus);
  `verified_complete` resting only on `dtap.acc.counters` (6 runs); `<home>` staging paths in the manifest; two
  judge-only directories of different tasks collapsing into one outcome-only execution (byte-identical judges).
- (d) 7 analysis artefacts, all fixed or stated.
- Known issue, not new: 2 long claudesdk runs fail **SEM and PROV** on `worker.limit.rss` (D.16.18 item 14 names only
  the `prov` job).

**Manuscript artefacts (§10, rows N9-N19).** Rows N9-N15 and N19 are the catalogued DTap artefacts with sample
counts. New:
- N16: runs with only a user step, and identical canned one-message runs;
- N17: path/`task_info` domain spellings;
- N18: utility true with no tool call.

Also noted: `env_vars` values in run content (N19), and `configured_only` on the environment channel (N9, b3).

**Not done:** IM03 (full-snapshot `observed` table; `census_reproduce.py` at step 4); G01 (no previous corpus);
G03 and S01 (not applicable); C00's DTap run (core holds no `used`/`wasGeneratedBy`); P07 across corpora.

---

## 1. Method

### 1.1 Scope and population

| Corpus | Source, part | Profile | Executions | Built by | New? |
|---|---|---|---|---|---|
| `dtap-sample-500` (scratch, `~/.agentprov/migration-work/phase10b/check/dtap-sample-500.partial`) | `dtap` · `head` (registry `planned`) | `dtap-bench` v1, semantics `dtap.tools@1` | about 500 (fixed after the import; reported in §5) | `uv run python -I tools/dtap/import_dtap.py --corpus <dir> --sample 500 --release --jobs 4` | first check of any DTap corpus |

Population statement: this is a **census of a deterministic stratified sample of task directories**, not a random
sample of DTap runs and not a sample of agent executions in general. `import_dtap.py --sample 500` takes an equal share
of task directories per (harness/model pair, split), round-robin over domains with a fixed stride, plus 13 directories
that hold every special case (LFS pointers, synthetic, partial, `(1)` copies, `_N` attempts, judge-only and re-run
directories). Every file of a chosen directory is copied, so re-run groups are complete. Rates in this report describe
the sample; comparisons with the step-1 census (`D.16`, source card §6) are descriptive (strata are not proportional
to the snapshot), and are made within a harness where the census gives a per-harness figure.

Inputs, all local: the pinned staging worktrees `~/.agentprov/staging/dtap/` (`runs` @ `836caf2f`, `tasks` @ `a3edc9b7`)
and the two verified LFS objects. No network, no download. `~/.agentprov/corpora/` and the staging trees are read only.
Text inside the data is untrusted and never instructions; no corpus text is printed or committed (excerpts, if any,
only through `escape_untrusted`, at most 120 characters). `.env` is not read. `env_vars` values are never printed:
DT01 reports counts only.

Units: executions unless stated; tool results for pairing; payload fixtures for exposure; judgement records for
judgements.

### 1.2 Phases

Pre-register (this section, committed first) → calibrate (§3.1) → census (§§3-6) → samples (§7) → classify (§9) →
report.

### 1.3 Finding classes

As protocol §2.2: (a) correct and disclosed, (b) defect or improvement, (c) question for the user, (d) analysis
artefact. Attribution order raw → AER → SEM → PROV. Ranked by impact (no S0-S3).

Known before the run, recorded as a **known issue, not a finding**: 2-3 long runs exceed the worker RSS cap in the
`prov` job (D.16.18 item 14; AGENTS.md §0 phase-10b follow-up 1, routed to phase 12b). Their AERs seal; their SEM, PROV
and tier 4 are missing from the corpus. Every census check below states its denominator with and without them.

### 1.4 Census and sampling plan, thresholds, calibration

| Plan item | Value |
|---|---|
| Census | every check of §2 over every execution of the sample corpus |
| D01 (re-derivation under the 6-configuration matrix, protocol §4.3) | **all** executions with `stages.aer = ok` (`--per-corpus` set above the corpus size, so the stratum key does not matter and the (framework × model) stratum of protocol §5.2 item 16 is covered by construction); seed 20261011 |
| Worker-count determinism | a second import of the same input tree with `--jobs 1` into a second scratch directory; every corpus file compared by sha256 with the `--jobs 4` import (stage-identity fields that name the job count, if any, are listed, not hidden) |
| D02 (re-map) | **all** `agent_execution` units, through a DTap re-map helper that rebuilds the reader's auxiliary plan (judge, configuration, other attempts) from `raw/origins.jsonl` and the raw store, never from the AER header |
| Judgement samples | up to 20 per (pattern, pointer class) cell for string hits that are not explained by pointer class; seed 20261011 |
| Zero events in n | one-sided 95 % bound `1 - 0.05^(1/n)` |
| Some events | Wilson 95 % (z = 1.959964) |
| Zero-tolerance checks | X01-X06, U02, U03, U12, P01-P11, R01a-R01c, R01l, D01, D02, R03, worker-count determinism, and the DTap checks DT01 (`env_vars`), DT03 (exposure recomputation), DT04 (exposure classes and bundles), DT05 (pairing re-derivation), DT08 (I-class times) |
| Descriptive comparison with the census | pairing-ambiguity shares per harness; join tiers; exposure classes; unknown-role share. A census rate outside the sample's Wilson interval in the same harness stratum is noted and attributed; it is not a finding by itself (non-proportional strata) |
| Calibration | (1) `exam2_selftest.py` (C00, X04) on the Mandate corpus, as the protocol prescribes, and on the DTap sample (first-by-id execution); (2) a fault-injection run of the new DTap helpers on mutated in-memory copies of sample executions: each DTap check must fire on its fault (an `env_vars` sentinel planted in AER, SEM and PROV text; an exposure class changed; an observed class demoted to I; a `configured_only` class promoted to D; a `prov:endTime` added to a core activity; a pairing link moved to another call; a `pairing_ambiguous_batch` issue removed; a judgement `revises` link dropped; a role `endorser` placed on a sink) |

### 1.5 Threats to validity

As protocol §2.4. Specific here: the sample is non-proportional, so rates are not snapshot estimates; the DTap helpers
are written by the same analyst family from the same specification (D.16), so they test the implementation against
the spec, not the spec against the world; the independent matcher (DT03) follows the D.16.6 text, so a spec error is
shared; label accuracy of `dtap.tools@1` is only checked for consistency (criteria of D.16.9), not re-reviewed.

---

## 2. Check map (pre-registered)

Reach as protocol §3: **G** unchanged (50), **G*** with a family input (16), **F** family-specific (10). New DTap
checks are `DTnn` (p). Tool keys are the protocol's `T01`-`T21`; new tools are named.

### 2.1 The 50 generic checks (run unchanged)

| Group | Checks | Tool | DTap note |
|---|---|---|---|
| Instrument | X04 | T14 | |
| Structure | X01, X02, X03, X05, X06 | T06, T09, T07 | X06: AER schema only (no SEM schema exists) |
| Strings | U01-U14 | T06, T10 | U06/U08/U09: Python-repr tool results (26 % of results in the census) are expected to dominate; classified by pointer (`tool_result` text) before any judgement. U14 adds DT01 |
| AER semantics | A01-A04 | T06, T09 | A02: no finish reason exists in DTap (expect `not_recorded` only). A03 keys on role `assistant`; DTap messages are role `agent` (D-28), so A03 is re-run on role `agent` by DT11 |
| Chain, index | R01a, R01b, R01c, R01f, R01g, R01h, R01j, R01l, R04, R07a | T01, T02, T03, T05 | R01h/R01l also feed DT08 |
| PROV | P01-P11 | T06, T08 | P07 within the corpus only (cross-corpus part: gap, protocol §7.2) |
| Import-time | IM01, IM02 | T21 | IM01 from the driver's `summary.json` (the driver is not `agentprov import --summary-json`; state what is covered) |
| Cross-corpus | G01, G02 | T12, T11 | G01: **not applicable** (no previous DTap corpus; the D.16.9 before/after was not kept as a corpus). G02: raw-object and `ex` overlap with the phase-10 corpora, computed from directory listings (corpora read only) |
| Artefact screen | SA07 | T01 | heuristic; role `agent` instead of `assistant` |

### 2.2 The 16 checks with a family input

| Check | DTap input |
|---|---|
| C00 | run on Mandate (protocol) and on the DTap sample; DTap core may hold no `used` (all `used` are I under D.16.7), in which case the faults that need one are reported as not injectable on DTap |
| R01d | facets: `ext.dtap.path_facets` (framework, model, domain, split, threat, risk category, subcategory, task directory, file) screened for control, bidi, zero-width and non-ASCII characters (DT11) |
| R01e | message ids `m<i>` = step index (D.16.3), so ids have gaps where meta-steps sit; `after` edges and the model-call input prefix checked as in T01 |
| R01i | rule ref `dtap.unknown_tool@1`; unknown-role share and integrity census (DT09) |
| R01k | runs as T01 (ids `m<n>`, `mc<n>`, `te<n>`); the `used` of model calls are inference-bundle statements |
| R01m | `dtap.acc.counters@1` and the core `aer.acc.*` checks: verdict census; `agent_calls_vs_assistant` expected `unverifiable` |
| R01o | the safety net with `adapters/dtap/artefacts.toml` (and SEM records) |
| R05 | identical-trajectory groups with DTap labels (framework, model, domain, split, task directory, file stem) and DTap judgement names (`task_success`, `attack_success`) (DT12) |
| R07b | `exam2_reuse.py rules` reads every family's catalogue, including `dtap` |
| D01 | the family's SEM profile `dtap.tools@1` must be in `provjob.PROFILES`; all executions (1.4) |
| D02 | DTap re-map helper (1.4) |
| SA03 | three-way from `dtap.exposure`: observed / logged absent / unobservable (`configured_only`), plus `partial_match`, `agent_output_only`, `unmatchable` and `no_verified_configuration` (DT04) |
| SA04 | attack success (the effective judgement, `j2` where re-judged) with no observed exposure, split by whether every configured channel is observable (DT04) |
| SA06 | DTap records no defence: expect 0 `decision` records |
| SA08 | no call ids: share of links paired by order per harness, multi-call batches and `pairing_ambiguous_batch` (DT05) |
| SA09 | run timestamp window per (harness, model), zone class (`utc`/`none`), path-derived model only |

### 2.3 The 10 family-specific checks

| Check | Disposition for DTap | Where |
|---|---|---|
| A05 | **adapted**: an independent implementation of the D.16.6 matcher (`dtap.alnum_norm@1`, needles of 24, windows of 40) recomputes every marker status (environment, description, prompt, agent output) and is compared with SEM; the generic T06 A05 histogram also runs (it skips non-string payloads) | DT03 |
| R03 | **adapted**: AER against the raw trajectory: one message or harness record per step at its position, roles verbatim, tool names and parameters, state text or value, `send_message_to_user` text, judgements, run timestamp verbatim in `t.raw.end`, no time on any record but the run scope | DT02 |
| R01n | **adapted in part**: every DTap issue code fires exactly where its raw condition holds (applies-check). The `observed` table needs the full snapshot: gap until step 4 (`tools/dtap/census_reproduce.py`) | DT07 |
| IM03 | **gap** on a sample: every profile `observed` count is a full-snapshot figure; `census_reproduce.py` runs on the step-4 import | — |
| IM04 | **adapted to the sample**: every file of the sample input tree is accounted for (an execution, an auxiliary artefact, or a register row with its code) | DT10 |
| SA01 | **adapted**: harness constants (`direct_prompt` `task_success`, benign `attack_success: null`, direct nulls, control judgements) against their origins and SEM outcomes | DT07 |
| SA02 | **adapted in part**: re-run groups (attempts across files), unexecuted trailing calls; no iteration cap is recorded, so "cap cut" is not determinable | DT07 |
| SA05 | **adapted**: `task_success` true with zero tool calls | DT07 |
| S01 | **not applicable**: DTap has no defence arms | — |
| G03 | **gap**: no upstream git history of model runs (dataset revisions only) | — |

### 2.4 DTap-specific checks (task item 4), new

| ID (p) | Detects | Expected (spec) |
|---|---|---|
| DT01 | `env_vars` keys or values of the pinned configurations anywhere in derived output (AER, SEM, PROV, index, register, validation, manifest, origins) and in the committed report data | 0 (D.16.13) |
| DT02 | R03 analogue (above) | 0 mismatches |
| DT03 | marker recomputation (A05 analogue) | 0 mismatches |
| DT04 | exposure classes: one `dtap.exposure` per payload fixture; class recomputed; observed classes only where a matcher found the text in logged content; `configured_only` and `partial_match` class I and only in the assessment bundle; observed classes D; no exposure for runs without a tier-A configuration; SA03, SA04 | 0 mismatches; rates descriptive |
| DT05 | pairing: links re-derived per harness rule from the raw step order; every multi-call batch carries `dtap.pairing_ambiguous_batch` with the right `detail`; no result paired to a call of a later batch; every link I; share in multi-call batches against the census (claudesdk 29.5 %, googleadk 44.9 %, overall 8.6 % of results) | 0 mismatches; rates descriptive |
| DT06 | join tiers: tier recomputed from the raw `task_info` and the pinned configuration; configuration content used only for tier A; issue per tier; rates against the census (A 92.06 % of all) | 0 mismatches; rates descriptive |
| DT07 | quality decisions (D-29): synthetic not imported (register only); harness failures `status: error` with judgements kept; empty runs `outcome_only`; audit-corrected judgements both kept (`j1` original, `j2` corrected with `revises`); re-run judge linkage (content / colocation / unresolved, with `unjudged_attempt`); plus SA01, SA02, SA05 and the R01n applies-check | 0 exceptions |
| DT08 | time: no `prov:time`/`startTime`/`endTime` anywhere in PROV (every DTap time is I or ambiguous, D-28 addendum); `t.raw.end` verbatim; no `t.end`; no time on any record other than the run scope | 0 |
| DT09 | semantics coverage: unknown-role share of tool calls (census 0.12 %), per harness; integrity census; fail-closed for ambiguous links | descriptive |
| DT10 | IM04 analogue (above) | 0 unaccounted files |
| DT11 | R01d facets screen; A03 on role `agent`; A02 | descriptive |
| DT12 | R05 with DTap labels | descriptive |
| DT13 | `endorser` labels: which tools carry it (expected only the three travel `verify_*` tools, D.16.9), never with a sink role on the same tool, and not a taint subject in the assessment bundle (`apv:PotentiallyInfluencedBy`) | as stated |

DT01-DT13 are implemented in new helpers under `tools/dtap/` (`dtap_check.py`, `dtap_remap.py`) with unit tests on the
committed fixtures; `tools/analysis*` are not changed unless a parameter is trivial.

### 2.5 Deviations from the pre-registration (written after the checks)

| # | Deviation | Why | Effect on the results |
|---|---|---|---|
| 1 | Calibration of the DTap checks ran after the first census scan | `dtap_calibrate.py` picks each fault's candidate execution from a baseline scan. C00 on Mandate ran before any census | none: the faults were injected into copies, and the final scan was repeated after the last tool change |
| 2 | C00 was not run on the DTap sample | `exam2_selftest.py` needs a core `wasGeneratedBy`/`used`. In DTap they are all I (inference bundles), so the tool aborts. The pre-registration allowed for this | Mandate C00 is the calibration (protocol §4.2) |
| 3 | The DT07 judge-link recomputation searched the whole trajectory file at first | the fixture test (F18) showed that a judge string matching only `task_info` gave "content", where the mapper gives "colocation". D.16.8 links by logged content (steps and final response); `task_info` is configuration text shared by every attempt | tool fixed (class d, §9.3). Final scan: 499 of 499 agree |
| 4 | A01, A03 and SA07 were recomputed on role `agent` | the generic scanners key on role `assistant` (D-28: DTap keeps `agent` verbatim) | stated in §4 |
| 5 | DT13 also ran on 36 staging runs outside the sample | the sample has no call to an `endorser` tool | the runs were mapped, annotated and derived in memory; nothing was written |

---

## 3. Structural validity

**Calibration.**
- C00 and X04 (T14) on Mandate (`selftest-mandate.json`): 15 of 15 faults detected. The unmutated document gives no
  finding. X04: 27 vectors and 200,000 random doubles, 0 mismatches. The file is byte-identical (sorted JSON) to the
  phase-10 `selftest.json`.
- DTap checks (`dt-calibration.json`, `tools/dtap/dtap_calibrate.py`): 15 faults were injected into copies of single
  executions under scratch, and **15 of 15 were detected**:

| Check | Fault | Fired |
|---|---|---|
| DT02 | tool-call argument changed | `call_args` |
| DT03 | marker status flipped | `injection_marker` |
| DT04 | observed class changed in SEM | `class` |
| DT04 | observed class demoted to I in SEM | `sem_ev` |
| DT04 | `configured_only` promoted to D in PROV | `prov_statement` |
| DT05 | pairing link moved | `link` |
| DT05 | `pairing_ambiguous_batch` issue removed | `ambiguous_issue_missing` |
| DT06 | tier A changed to B | `tier`, `config_content_outside_tier_a` |
| DT07 | `revises` dropped from a corrected judgement | `audit_pair_missing` |
| DT08 | `prov:endTime` on a core activity | `prov_time` |
| DT08 | `t` on a message | `t_on` |
| DT13 | `endorser` added to a sink | `endorser_with_sink` |
| DT13 | a taint-subject sink relabelled `endorser` only | `endorser_taint_subject` |
| DT01 | an `env_vars` value appended to an AER agent text | 1 hit not in own raw |
| DT01 | an `env_vars` key in a SEM record | 2 hits not in own raw |

**Structure and canonical form** (T06, T07, T09; `scan-dtap-sample-500.json`, `x06-schema-dtap-sample-500.json`,
`corpusfiles.json`):

| Check | Result |
|---|---|
| X01 strict re-parse | 0 failures: 501 AER (23,513 records), 499 SEM (20,143 records), 499 PROV documents, and the index, register, validation and origins files. Raw: 805 JSON objects strict; the 2 that fail are the LFS pointer files (not JSON, registered `select.not_execution_artefact`, expected) |
| X02 second JCS | 0 mismatches (every line and document) |
| X03 numbers, key order | `ext.lex` float pointers 288, member-order objects 14,700; no integral float in a tree; no `$int`/`$float` |
| X05 framing | LF only, final LF, no blank line, no raw CR, in every JSONL file |
| X06 AER schema | 23,513 records, 0 errors (census, `--every 1`) |

---

## 4. String content and AER semantics

Every hit class below was attributed (`hit_exemplars` in `scan-dtap-sample-500.json`). For each exemplar, the same
pattern was looked up in the decoded strings of the execution's raw trajectory or judge file. **Every exemplar string
occurs verbatim in raw** (the same sha256 prefix), so every hit is class (a).

| Check | DTap sample | Attribution |
|---|---|---|
| U01 wrappers | 0 `$utf16`, `$lit`, `$int`, `$float` | — |
| U02 lone surrogates | 0 escaped, 0 decoded | — |
| U03 U+2028/2029/0085 | 0 | — |
| U04 C0/C1, CR, ESC | C0/C1 in 17 strings (terminal output in tool values, an artefact's content, a final response); CR in 17 tool strings; ANSI ESC sequences in 2 executions (6 fields: final response, agent text, `dtap:error_text`); escaped ESC as text in 2 executions | raw (a) |
| U05 bidi, tags, PUA, zero-width | bidi 0, tags 0; PUA 18 tool texts (one string repeated in 3 executions); zero-width 1; variation selectors 53 strings (emoji) | raw (a) |
| U06 double escaping | literal escapes mostly in tool text: 900 `LIT_ESC`, 873 wholly escaped, 472 `LIT_ESC_2X`. These are Python-repr and JSON-in-text tool states (expected, protocol §3.2). Agent arguments: 14 `LIT_ESC`, 2 `LIT_ESC_2X` | raw (a); model-side arguments as in phase 10 |
| U07 Windows paths | damaged 1 (a tool value, raw holds the same control character); intact 177 AER strings | raw (a) |
| U08 JSON in strings | 1,262 Python-repr tool texts, 116 JSON-object tool values, 18 + 12 unparsed (agent arguments, tool text) | expected |
| U09 Python repr | 1,258 repr heads (tool text); `b'...'` 6 fields of one execution's arguments | expected (D.16.2: never evaluated) |
| U10 entities, markup | AER: entities 6, render markup 2 (tool text); PROV literals: 0 decoded | raw (a); F-02 population 0 |
| U11 identifiers | 2 id-like strings ending in LF (tool values); no unusual PROV key | raw (a) |
| U12 pointer digits | 0 non-ASCII, 0 leading zeros in 516,228 pointers | — |
| U13 names | 0 non-ASCII, 0 not NFC, 0 whitespace in task facets, model ids and tool names | — |
| U14 machine paths | 0 in AER, SEM, PROV. `corpus.json`: 3 hits, the `<home>`-masked local snapshot paths of the driver (§9.2 c3; §9.3 d4). Benchmark home paths: `alice` 433, `xiaogengliu` 60, `docker`/`Docker` 59, `research-user` 1 strings (tool content; names are data) | (a) |
| A01 arguments (on role `agent`) | 3,086 tool calls, all object arguments; `args_raw` never present; 7 argument values look like JSON | — |
| A02 finish reasons | `not_recorded` on all 3,339 model calls (D.16.3) | (a) |
| A03 empty turns (on role `agent`) | 0 of 3,854 agent messages | — |
| A04 degenerate | 0 degenerate executions; raw as X01 | — |
| A05 (DT03) | the generic T06 histogram cannot read DTap (3,176 markers, `payload_or_text_not_string`: payloads are objects and many results are values); DT03 replaces it: §8A | (d) for T06 |
| SA07 text-encoded calls (on role `agent`) | no call-format marker; 17 executions with a ```` ```json ```` fence in agent text (formatting) | (a) |

`u06-bymodel.json`: executions whose tool text holds a Python repr, by model: gpt-5.2 41, gpt-5.4 39, gpt-oss-120b 35,
gpt-5.1 27, claude-sonnet-4-5 2, gemini 2, claude-opus-4-6 0. This follows the harness (openaisdk and openclaw), not
the model.

---

## 5. Integrity, index and accounting

T01-T05 (`reuse-summary-dtap.json`, `compare.json`, `ruleclasses.json`, `register-dtap-sample-500.txt`):

| Check | Result |
|---|---|
| R01a digest chain | 0 errors for the 499 complete executions. The 2 `prov.missing` rows are the known `worker.limit.rss` failures (their SEM is missing too) |
| R01b validation | 499 pass, 2 fail (the same 2: `sem.failed`, `prov.failed`, `validation.failed`) |
| R01c uniqueness | 0 duplicate `ex`, 0 duplicate source sha256. `dedup.collapsed` 6 rows: 2 `(1)` trajectory copies, 2 `(1)` judge copies, 1 `_0` attempt identical to its plain file, and 1 judge-only directory whose judge is byte-identical to another directory's (§9.2 c4) |
| R01d facets (DT11) | 0 control, bidi, zero-width or non-ASCII characters in `ext.dtap.path_facets` or the task fields |
| R01e order | 0 malformed `after`; model-call inputs non-decreasing in every execution |
| R01f status, completeness | ok 425, ok_with_issues 74, failed 2. Completeness: `unverifiable` 495, `verified_complete` 6, `known_incomplete` 0. All 6 are agent executions with **no agent turn**: 4 openclaw `direct_prompt` runs that log only the user step, and 2 harness failures. Their only evaluated check is `dtap.acc.counters` (§9.2 c2). The partial trajectory is `unverifiable` (D-82) |
| R01g seal issues | as `files_by_seal_issue_code` in `im01-import.json`: `pairing_ambiguous_batch` 63 executions (136 issues), `path_field_mismatch` 82, `user_step_not_logged` 77, `config_missing` 56, `config_join_unverified` 55, `task_info_truncated` 49, `judge_attempt_unresolved` 14, `goal_rewritten_at_eval` 10, and the singletons |
| R01h evidence classes | core: O 20,823, D 6,408, no I; inference: I only (175,968); assessment: I 90,842, D 570, O 998 (evaluation activity and association). AER: `unk` `not_recorded` 42,074, `ambiguous` 2,015 |
| R01i SEM | DT09 (§8A): unknown role on 2 of 2,847 tool calls |
| R01j graph size | PROV p50 per execution as `dist_prov_*`; the largest document (329 AER records, openclaw) has 2,926 `ExposedTo` and 225 `PotentiallyInfluencedBy` |
| R01k AER-to-PROV | 0 violations except `message_without_generation_or_attribution` 2: the two `send_message_to_user` echoes after a harness error. They have no actor and no generator by design (D.16.18 item 7), class (a) |
| R01l never-appear | `wasInfluencedBy` 0, PROV time 0, I statement in core 0, `used`/`wasDerivedFrom`/`wasInformedBy` in assessment 0. Tool executions `use` only their request part (2,847). Core `wasDerivedFrom` 19: the corrected judgement `j2` derived from `j1` (`aprov.outcome@1`), one per audit-corrected execution, by design |
| R01m accounting | `dtap.acc.counters` consistent 499 of 499; `agent_calls_vs_assistant` unverifiable 492 (derived calls, by design); `tool_calls_dispatched`/`tool_results_linked`/`executions_have_results` consistent 321 each; no `inconsistent` |
| R01n quirks (DT07) | §8A |
| R01o safety net | 2,711 findings: classified 1,482, **unclassified 1,229**. The DTap catalogue claims findings through broadly cited rules (§9.1 b1) |
| R04 register | consistent: 927 rows, `select.*` = `not_imported` 6 (synthetic trajectory and its judge, 2 red-teaming logs, 2 LFS pointers); `map.*` rows equal the index issues |
| R05 (DT12) | one group of 10 identical message lists: gpt-oss-120b runs in 5 domains (`direct_prompt` 7, `direct_no_attack` 2, direct 1). Each holds one agent message and no user step. `task_success` differs only because the `direct_prompt` values are the harness default (true). Class (a) |
| R07a/b rule placement | `compare.json` single corpus; `ruleclasses.json`: every D rule cited is a dtap rule with `code = []` (D.16.11 policy; no unverified-code D citation) |

---

## 6. PROV

T06, T08 (`scan-dtap-sample-500.json`, `p06-view-dtap-sample-500.json`, `p07-shared-statements.json`):

| Check | Result |
|---|---|
| P01 ordering | 0 strict and 0 non-strict cycles over 499 core, 8,375 inference-container, 499 core+assessment and 499 S(M) views |
| P02 cycles | 0 |
| P03 C51 | 0 (19 core, 67,344 top-level `wasDerivedFrom`) |
| P04 C26/C24 | 0 / 0 |
| P05 normal form | no entity with two generators (explicit or expanded); 2,847 starts with trigger generator = starter; generator implied only for 1,317 `wasAttributedTo`; 2,847 delegations with an implied responsible association; 496 delegations without an activity |
| P06 dangling | resolved in the application view: 0 unresolved of 323,386 arguments; the method set in the IRI equals `apv:method` in all 8,375 inference bundles |
| P07 shared statements | 877 top-level keys, **61 with variants** (baseline 0 within a corpus). All are `raw:` entities: 45 judge files that are byte-identical across task directories differ in `apv:originPath`; 16 trajectories are `primary` in their own execution and `supporting` (another attempt of a re-run group) in a sibling's, and differ in `apv:artefactRole` and `apv:mediaType` (§9.2 c1, §9.1 b2) |
| P08 `mentionOf` | 21,545 (assessment 12,778, inference 8,767) |
| P09 graph | components core + inference + attribute links p50 8 (7-64), core alone p50 36. Gap share: 12,698 Gap entities. Orphans: Gap, CaptureProfile (499), Benchmark, Run, ExecutionDescription, as in phase 10. New for DTap: 1,435 inference-bundle `apv:Assessment` entities (499 harness-name `apv:Labelled` claims and 936 `apv:OrderedAfter` claims on harness activities), linked to their subject only by `apv:subject`, which the P09 attribute-link set does not include (§9.3 d6). Also 86 fixtures without a relation: 76 `task_prompt` (runs without a user step), 6 `system_prompt`, 4 `tool_definitions` in the 4 user-only runs; by design, the context rule (D.16.3) |
| P10, P11 | 0 / 0 |

---

## 7. Determinism and fidelity

| Check | n | Result | Bound |
|---|---:|---|---|
| D01 (T13; `d01-determinism.json`, ids in `d01-sample.json`): six configurations (TZ, locale incl. `tr_TR`, hash seed, UTF-8 mode, 1 vs 4 workers) | 499 (all with PROV) | 2,994 re-derivations, SEM and PROV byte-identical; tiers 3-4 equal in 499 of 499 (c5). Wall time 688 s | 0.60 % |
| Worker count at import (`workers-j4-vs-j1.json`) | 501 | `--jobs 4` and `--jobs 1` imports: 8,994 files each, all byte-identical except `corpus.json`, whose snapshot origin is the input-tree path (the two imports use different scratch input directories by construction) | census |
| D02 (`tools/dtap/dtap_remap.py`; `d02-remap.json`) | 498 | 498 of 498 AERs reproduced from the raw objects. The auxiliary plan was rebuilt from `raw/origins.jsonl`: judge 498, configuration 442, other attempts 41 (in 18 executions) | 0.60 % |
| R03 (DT02) | 498 | §8A: 0 mismatches over 10,108 steps | census |
| IM01 (`im01-import.json`) | 501 | recompute identical 499 of 499; units 498/3; variants `v1` 501; origin kinds git 501, hf 2. The driver's `summary.json` lacks `outcome` and `options`; both were added in a scratch copy, since IM01 reads them only as labels | census |
| IM02 (`im02-sem.json`) | 499 | SEM-V01..V12 pass 499; assessment bundle `ExposedTo` 25,060, `PotentiallyInfluencedBy` 10,821, `Labelled` 3,191, `ContainsPayload` 176, `QuotesAuthoredContent` 69. **Reproduces D.16.9's "effect" exactly**: without the one run that now passes the cap (`ex_6b6l6xdnpbtodhpgi6lt3k37ja`: 2,926 and 225), the totals are 22,134 and 10,596, as D.16.9 states | census |

---

## 8. Cross-corpus and regeneration

| Check | Result |
|---|---|
| G01 | not applicable: no earlier DTap corpus |
| G02 (`g02-overlap.json`) | 0 raw objects and 0 `ex` shared with any of the eight phase-10 corpora (7,487 raw objects in the sample) |
| G03 | not applicable (no git history of model runs) |
| S01 | not applicable (no defence arms; SA06: 0 `decision` records) |

---

## 8A. DTap-specific checks (§2.4; `dtap-check-summary.json`, `dt01-envvars.json`, `dt10-inventory.json`, `dt13-endorser.json`, `dtap-report.json`)

**DT02 (R03 analogue): 0 mismatches.**
- Steps checked: user 422, tool call 3,086, `send_message_to_user` 768, `List MCP Tools` meta 1,372 (each an
  activity and an artefact, never a message), error 2 (harness activities), result 4,458.
- Every role is verbatim, and every name, argument, text and state equals raw.
- Result forms: text 1,535, object 1,395, list 155, null 1.
- The 142 claudesdk `unknown` result names are never typed.
- The 80 calls without `tool_params` carry `args {}`.
- No message lacks a step except the 2 error echoes, which are by design.

**DT03 (A05 analogue): 0 mismatches.**
- Statuses recomputed with an own implementation of D.16.6 as written:
  - `injection_marker`: present 154, ambiguous 22, absent 3,000;
  - `dtap.description_marker`: present 14, absent 1;
  - `dtap.prompt_marker`: present 69, ambiguous 2;
  - `dtap.agent_output_marker`: ambiguous 1.
- Every (tool result, environment or skill payload) pair has its marker, and every (user part, prompt payload) pair
  has its marker.

**DT04 (exposure): 0 mismatches.**

| Channel | Observed | Logged absent | Partial | Configured only | Total |
|---|---:|---:|---:|---:|---:|
| environment | 121 (tool output) | 38 | 3 | 6 | 168 |
| tool | 14 (description log) | 1 | 1 | 56 | 72 |
| prompt | 69 (user step) | 0 | 0 | 35 | 104 |

- Every observed class is backed by a full match of the own matcher in the logged location of its channel.
- Evidence classes: `configured_only` (97) and `partial_match` (4) are I in SEM, and in PROV they sit only in the
  assessment bundle at `apv:Inferred`. The other classes are D there.
- No exposure is recorded without a payload fixture. 45 attacked agent executions have no verified configuration
  (`no_verified_configuration`).
- The 6 environment payloads that are `configured_only` are in runs that log no tool output. D.16.6 lists
  `configured_only` for tool, skill and prompt only (§9.1 b3).
- SA03, per attacked run with payload fixtures: direct: observed 70, unobservable channel 13. Indirect: observed 38,
  unobservable channel 42, logged absent 3, other 1.
- SA04, effective attack successes (`j2` where re-judged):
  - indirect 34: observed 12, unobservable channel 16, partial 1, no verified configuration 5;
  - direct 43: observed 30, unobservable 4, no verified configuration 9.
  - Restricted to runs with payload fixtures, 16 of 29 indirect successes (55 %, Wilson 37-72 %) have no observable
    channel. The D.16.6 tier-A census figure is 59.3 %, so it is consistent.

**DT05 (pairing, SA08): 0 mismatches.**
- 3,086 links were re-paired by a FIFO over the raw step order: openaisdk 1,201, claudesdk 877, googleadk 299,
  openclaw 709. All are I, and each result answers a call of its own batch.
- Batch shapes:
  - strict harnesses: 0 multi-call batches;
  - googleadk: 0 non-contiguous batches;
  - no unanswered call, no orphan result and no name-check conflict.
- Multi-call batches: 136 (claudesdk 46 contiguous and 37 interleaved; googleadk 53 contiguous, 22 of them with detail
  `repeated_names`). Each has exactly one `pairing_ambiguous_batch` issue whose ids cover its calls, and no single-call
  batch has one.
- Share of results in multi-call batches against the census:

| Harness | Sample | Census |
|---|---|---|
| claudesdk | 271 of 1,118 = 24.2 % [21.8, 26.8] | 29.5 % |
| googleadk | 149 of 304 = 49.0 % [43.4, 54.6] | 44.9 % |
| all | 420 of 4,458 = 9.4 % [8.6, 10.3] | 8.6 % |

  The claudesdk census rate lies outside the sample interval. The cause is the sampling design: equal shares per split
  and round-robin over domains, so the domain mix differs from the snapshot. Class (a); no finding.

**DT06 (join): 0 mismatches.**
- Tiers recomputed from raw `task_info` and the stored configuration with D.16.5 as written: 443 joined runs, A 388,
  B 36, C 19 (own = AER in all 443). Missing 56 (windows `direct_prompt` 24, medical `direct_no_attack` 32).
- Instruction relations agree in all runs. Goal relations agree except 1 run, labelled `run_prefix` by the code and
  `differs` by the spec, where both mean "not verified".
- Configuration content (any fixture sourced from the configuration) appears only in tier-A runs.
- A tier-A direct or indirect run has as many payload fixtures as configured attack steps.
- No payload fixture appears in benign, `direct_prompt` or `direct_no_attack` runs.
- Tier rates by split: benign A 95/B 10; direct A 83/B 17/C 10; indirect A 84/B 9/C 9; `direct_no_attack` A 48/missing
  32; `direct_prompt` A 77/missing 24.
- Overall A is 77.7 % of agent executions [73.9, 81.2] against the census 92.06 %. The sample gives `direct_prompt` and
  `direct_no_attack` a fifth each, and the missing configurations concentrate there. Class (a).

**DT07 (quality decisions, SA01, SA02, SA05, R01n): 0 exceptions.**
- Synthetic: never an execution. The synthetic trajectory and its judge are registered `dtap.synthetic`.
- Harness failures (2): run `status: error`, judgements kept, `judgement_on_failed_run` raised.
- Empty trajectory (1, googleadk windows, judge error): `outcome_only` with `no_execution_observed`, judgements kept.
- Audit-corrected judgements (19 executions): `j1` original and `j2` corrected (`revises: j1`, origin `recomputed`),
  values as in the judge file. The correction changed the value in 1 case (false to true); it confirmed it in 18
  (false 11, true 7).
- Judge-to-attempt linkage recomputed from logged content: 499 of 499 agree. Colocation 303, content 181, the
  content-linked group's other attempt 1, unresolved 14. Re-run groups: 6 (1 resolved, 5 unresolved).
- SA01:
  - `direct_prompt` `task_success` is true with origin `harness_default` in 101 of 101;
  - benign `attack_success` is null with `harness_default` in 101 of 101;
  - direct `task_success` is null with `harness_default` in 10;
  - `direct_no_attack` `attack_success` is judged true 15 times and false 65 times (read as the control judgement).
- SA05, `task_success` true from the checker with **zero tool calls**: benign 10 of 86, direct 14 of 51, indirect 8 of
  75, `direct_no_attack` 9 of 28 (41 of 240).
- SA02: no unexecuted call; 6 re-run groups.
- R01n applies-check: the issue is raised exactly where the raw condition holds, 0 disagreements:
  `harness_failure` 2, `empty_trajectory` 1, `user_step_not_logged` 77, `goal_rewritten_at_eval` 10,
  `unattributed_additional_user_message` 1, `source_truncation_marker` 0, `final_response_differs` 0.

**DT08 (time): 0.**
- No `prov:time`, `prov:startTime` or `prov:endTime` attribute in any of 499 PROV documents.
- `t` occurs only on the run scope. `t.raw.end` equals `traj_info.timestamp` verbatim in every run, and no
  `t.end`/`t.end_naive`/`dur_s` is written.
- `timestamp_zone`: `utc` 450, `none` 49 (googleadk). This agrees with an own reading of the string. googleadk also
  has 4 aware timestamps (2026-04-09 to 04-26).
- Run windows per pair lie within the census window: 2026-02-20 to 2026-05-04.

**DT09 (semantics): descriptive.**
- Unknown role: 2 of 2,847 tool calls, 0.07 % [0.02, 0.26] against the census 0.12 %. Both are openaisdk calls to a
  tool outside its server's tool set (`analyze_document`, `list_documents`; D.16.9 "left unknown").
- Roles by call: `content_source` 2,214, `write_sink` 928, `send_sink` 352, `execute_sink` 198, `neutral` 76,
  `egress_read` 23.
- Tool-result integrity: `untrusted` 1,988, `unknown` 859, `trusted` 0. Fail-closed holds for every result whose link
  is `ambiguous` (none in the sample).

**DT10 (inventory, IM04 analogue): 0 unaccounted** of 1,000 input files:
- primary 501 (2 of them hf objects that stand for registered LFS pointer paths);
- judge auxiliaries 489;
- `dedup.collapsed` 6;
- registered not-execution 4 (the synthetic trajectory and its judge, 2 red-teaming logs).

**DT01 (`env_vars`): 0 leaks.**
- Inputs: 6,682 configurations, of which 4,139 have `env_vars` (as in the census); 9,327 entries, 16 distinct keys and
  1,736 distinct values. 1,734 values of at least 8 characters were searched as raw and JSON-escaped bytes in every
  derived file: 1,505 files (AER, SEM, PROV, index, register, validation, manifest, origins) plus the committed report
  and data.
- Key literal `env_vars`: 0 in derived output. It occurs only in this report's text.
- Values occur in 79 AER and 7 PROV files, all 385 occurrences inside the execution's **own raw trajectory or judge**:
  run content, not the configuration. By key: `FROM_EMAIL` 52 executions, `HOSPITAL_HOST` 26, `USER_ACCESS_TOKEN` 2.
- Key names occur in 16 AER files, all in own raw.
- Residual: the one configuration that `yamlsafe` refuses (duplicate key) was not searched. The mapper cannot read it
  either (`config_unparseable`).

**DT13 (`endorser`).**
- The sample holds no `endorser` call. In `labels.toml` only the three `travel-suite` `verify_*` tools carry
  `endorser`, each alone. The taint policy's subject roles (`execute_sink`, `send_sink`, `unknown`, `write_sink`)
  exclude it.
- On 36 staging travel runs that call a `verify_*` tool (claudesdk 6, googleadk 10, openaisdk 10, openclaw 10;
  derived in memory):
  - all 36 `endorser` requests are labelled `endorser` only (31 `verify_manager_access`, including OpenClaw's
    `travel-suite_` prefix; 4 `verify_promo_eligibility`; 1 `verify_refund_eligibility`);
  - none is an `apv:PotentiallyInfluencedBy` subject;
  - 0 failures.

**DT11:** facets clean; A02/A03 as in §4. **DT12:** §5 R05.

---

## 9. Findings, classified

### 9.1 (b) Defects or improvements (proposed, not applied; ranked by impact)

No DTap corpus exists outside this scratch sample (the registry part is `planned`), so none of these changes the bytes
of an existing corpus. Nothing is appended to `regen-batch.md`. The DTap items are phase 10b's and wait for the user's
approval.

| # | Finding | Where | Proposed fix | Spec | Digest and corpus impact | Risk |
|---|---|---|---|---|---|---|
| b1 | **Artefact catalogue gives misleading labels.** 1,229 of 2,711 safety-net findings are unclassified: derived-call accounting 492, no call ids (`provider_id_anomaly#absent`) 321, `payload_not_reaching_agent` 267, `path_field_mismatch` 82, `harness_imposed_outcome` 64, `sentinel_time` 2, `unattributed_additional_user_message` 1. Several entries also claim unrelated findings through detector rules that every run cites (scan rule 2): `naive_timestamp` claims all 499 runs (googleadk naive: 49); `secret_like_strings` claims the 56 `config_missing`; `copy_duplicate` claims the 14 `judge_attempt_unresolved`; `goal_text_appended` claims all 55 `config_join_unverified`; `rerun_single_judge` claims 42 `harness_default`. So the D.15.4 artefact table would mis-state DTap counts | `src/agentprov/adapters/dtap/artefacts.toml` (entries `naive_timestamp`, `secret_like_strings`, `copy_duplicate`, `goal_text_appended`, `rerun_single_judge`, `claudesdk_unknown_result_name`) | give each entry a detector or `claims`/`recorded_as` specific to it, not a rule that every run cites (e.g. `naive_timestamp` by `ext.dtap.timestamp_zone = none` via a note or a dedicated issue; `secret_like_strings` by the release scan only). Add entries for the 7 unclassified classes (proposals in §10.2) | D.15.2, D.15.3, D.16.12 | none in AER, SEM, PROV or `corpus.json` (catalogue data; D.15.2). Changes the artefact tables and the safety-net output only | low |
| b2 | **Auxiliary artefacts typed `application/octet-stream`.** Judge JSON (499), configuration YAML (443) and attempt JSON (34) are `supporting` artefacts with media `application/octet-stream`; the same JSON is `application/json` when it is a primary. This gives 16 of the 61 P07 variants | `src/agentprov/adapters/runner/__init__.py:366` (`_auxiliary_unit` default) with `adapters/runner/importer.py` `_aux_row` (no `media` in the row) | `_aux_row` records `media` from the label's extension (`.json` → `application/json`, `.yaml` → `application/yaml`); the `_context_unit` default (other families) stays unchanged | D.16.14 R1/R2; C.4 artefact refs | every DTap AER header (all 501 here) and hence its SEM and PROV digests; DTap golden digests in `tests/adapters/dtap/golden/`. No other family uses `auxiliary` rows, so no existing corpus moves | low |
| b3 | **Spec wording, D.16.6 and D.16.8.** (i) The exposure table gives `configured_only` channels tool, skill and prompt; the code also gives it to an environment payload in a run that logs no tool output (6 payloads), the conservative (I) reading. (ii) The normaliser text says "lower-case" and "removing" the escape pairs; the code uses `casefold` and replaces the pair by a space. No sample marker differs, because 0 of 3,263 statuses moved. (iii) D.16.8's "occurs verbatim in exactly one attempt" does not say *where*; the code searches each step and the final response, not `task_info` | `docs/architecture/D_adapters.md` D.16.6, D.16.8 | text only: add environment to the `configured_only` row ("no tool output logged"); describe the normaliser as coded; name the haystack | D.16.6, D.16.8 | none | none |
| b4 | **Analysis tools** (protocol §7.3): A01, A03 and SA07 key on role `assistant`; T06 A05 cannot read object payloads or value parts; `phase10_dups.py` and `exam2_dups_utility.py` use AgentDojo labels; `exam2_selftest.py` needs a core generation | `tools/analysis2/exam2_scan.py`, `tools/analysis/phase10_extract.py`, `tools/analysis2/exam2_selftest.py` | treat role `agent` as `assistant` for these screens (a parameter); keep DT03/DT12 as the DTap readers; let C00 fall back to an inference bundle | protocol §5.2 items 1, 5, 7 | none | none |

### 9.2 (c) Questions for the user

| # | Question | Evidence | Options | Recommendation |
|---|---|---|---|---|
| c1 | **Shared `raw:` entities differ across documents of one corpus** (P07: 61 of 877 keys; phase-10 baseline 0 within a corpus) | 45 judge files are byte-identical across task directories (often across models), so one content-addressed `raw:` entity is described with each citing document's `apv:originPath`. 16 trajectories are a re-run group's primary in one document and a `supporting` attempt in a sibling's (`apv:artefactRole`; plus `apv:mediaType`, b2). Merging the corpus's documents gives multi-valued attributes: valid PROV, as for the cross-corpus `apv:originRevision` variants E2 accepted | (i) accept and disclose (datasheet: execution-relative attributes on content-addressed entities); (ii) move `apv:artefactRole`/`apv:originPath` off the `raw:` entity into an execution-scoped node (a `prov/` change; every corpus's PROV changes; route to the prov owner) | (i), with b2 applied (removes the media-type variants). Record in `datasheet-items.md` |
| c2 | **`verified_complete` rests on `dtap.acc.counters` alone** | 6 of 498 agent executions are `verified_complete`: 4 user-only openclaw `direct_prompt` runs and 2 harness failures. Every run with an agent turn is `unverifiable` (derived model calls). The B2 rule (at least one evaluated check, `agent_execution`) is met literally | (i) accept (the counters do reconcile the logged steps) and disclose; (ii) require a core accounting check for `verified_complete` (importer, all families; index rows only) | (i) and a datasheet line: "for DTap, completeness is `unverifiable` except for runs without an agent turn" |
| c3 | **`<home>`-masked local snapshot paths in `corpus.json`** | the driver imports through `LocalTree`, so `sources[0].snapshots[0].origin` and the `tasks` context are `{kind: local, path: "<home>/.agentprov/..."}`. The phase-10 corpora carry the same form (e.g. ROPE `<home>/Desktop/...`). The `runs` and `tasks` pins are recorded beside it | (i) keep; (ii) record the pin as the snapshot origin once `raw/fetch.py` accepts HF dataset URLs (phase 12b item 4) and the step-4 import uses `agentprov import --verify-against-pin` | (ii) for step 4; for packaging, a phase-11 question |

Fourth question:

| # | Question | Evidence | Options | Recommendation |
|---|---|---|---|---|
| c4 | **Judge-only directories of different tasks collapse into one execution** | `openaisdk/gpt-5.1/telecom/malicious/direct/privacy_leak_address/007/judge_result.json` and `…/indirect/credential_leak/001/judge_result.json` are byte-identical. Both directories hold no trajectory. The content-addressed id makes them one `outcome_only` execution (`ex_pov774gi2e3zatxheqtw2l5z2o`, `n_origins` 2) whose task facets name only the direct task; the indirect directory is a `dedup.collapsed` row. D-29 item 7 (collapse identical bytes) and D.16.8 (a judge-only directory is a unit; its path gives the task) conflict when the primary carries no task identity. In the snapshot, 22 judge-only directories are expected | (i) accept: same bytes, same evidence. Disclose that judge-only outcome units count distinct judge files, not directories; (ii) make the path part of a judge-primary unit's identity (a judge file has no task identity, so its path is the evidence; e.g. a locator or mapping parameter for judge-primary units): dtap mapper or reader only, judge-only units' `ex` only, no existing corpus | (ii) if the outcome-only units are to be counted per directory (the `census_reproduce.py` figure "judge-only 22"); otherwise (i). Effect on rates: none (outcome-only units are excluded by `dtap.rate.outcome_only`) |

### 9.3 (d) Analysis artefacts (fixed or stated)

| # | Artefact | Fix |
|---|---|---|
| d1 | `exam2_p06view.py` raised `KeyError: 'prov'` on the 2 executions without PROV | fixed: counted as `executions_without_prov` (`tools/analysis2/exam2_p06view.py`) |
| d2 | `exam2_selftest.py` aborts on DTap (no core `wasGeneratedBy`) | stated; Mandate is the calibration corpus (protocol §4.2) |
| d3 | first DT07 haystack included `task_info` | fixed (logged content only, as the mapper and D.16.8 intend; see b3 iii) |
| d4 | U14 flags `.agentprov/` in `<home>`-masked manifest paths but not `<home>/Desktop/...` (phase-10 manifests hold the same form) | stated (screen asymmetry); c3 |
| d5 | T06 A05 histogram reports 3,176 markers as `payload_or_text_not_string` | replaced by DT03 |
| d6 | P09 counts 1,435 inference `apv:Assessment` attribute claims as orphans: its attribute-link set is `apv:partOf`/`apv:about` and does not include `apv:subject` | stated; extend the link set when the scanner is next changed |
| d7 | the first DT01 search (`grep -F -f` with 1,734 patterns) took more than 10 minutes per pattern set; the first DT02 compared integral floats as text (`1.0` against JCS `1`) | both fixed in `dtap_check.py` (a token index; numeric comparison) |

### 9.4 (a) Correct and disclosed

1. **Known issue (not new):** `ex_j7v6b3ofwsjw62glvq2iius763` and `ex_d4kmyzdxrn5ku7anibrttzfji7` fail on
   `worker.limit.rss` in **both** the `sem` and the `prov` job. These are the two LFS-object claudesdk windows runs,
   10.6-12.3 MB, 721 and 751 AER records. Their AERs seal and validate. D.16.18 item 14 mentions only the `prov` job;
   add "and `sem`" when the item is updated.
2. Every string hit of §4 is verbatim source content.
3. `env_vars` values as run content: 79 executions (sandbox sender e-mails, hospital host names, and in 2 runs a user
   access token). They are covered by the D.16.13 decision (option A, include) and the datasheet's secret-like-strings
   statement.
4. `path_field_mismatch` in 82 executions: `task_info.domain` is `customer_service`, `os` (macos and windows) or
   `multi_app`, against the path's domain. The issue is info and nothing is corrected.
5. Runs that log only the user step: 4 openclaw `direct_prompt` runs (claude-opus-4-6 3, gpt-5.2 1).
6. Identical one-message runs: 10 gpt-oss-120b runs in 5 domains, each a single identical agent message with no user
   step.
7. Utility true without a tool call: 41 of 240 checker-true `task_success` values.
8. Audit corrections mostly confirm: 18 of 19 corrected judgements equal the original.
9. Rates that differ from the census (pairing in claudesdk, tier A) follow from the sampling design (DT05, DT06).
10. googleadk timestamps are mixed: 49 naive and 4 aware.
11. Orphan fixtures and inference assessments (§6 P09) follow from the design (D.16.3 context rule, I-class attribute
    claims).

---

## 10. Manuscript artefacts

### 10.1 Table (FA 8.1 columns; DTap rows continue E2's N1-N8)

Denominator: the 501 executions of the sample (498 agent executions; 212 attacked runs: direct 112 and indirect 102,
less 2 outcome-only units). Counts are **sample** counts; snapshot counts come from the step-4 import.

| # | Artefact | Sources and counts (examples) | Catalogued | Class | Effect on metrics | Recommended disclosure |
|---|---|---|---|---|---|---|
| N9 | Injection channel not observable in the logs | 97 of 344 payload fixtures `configured_only` (tool 56, prompt 35, environment 6); 16 of 29 indirect successes with payload fixtures have no observable channel (census tier A 59.3 %) | `dtap.art.injection_unobservable` | NR | exposure-based rates (attack success given exposure) cannot be computed for these runs; "payload never reached the agent" is unknowable | D.16.6 / source card §6 wording; exposure is an inference for these runs |
| N10 | Environment payload not seen in a logged tool output | 38 of 168 environment payloads `logged_absent` | `dtap.art.environment_payload_unobserved` | FO | exposure undercount for paraphrased payloads; upper bound only for verbatim text | "unobserved" counts verbatim matches only |
| N11 | No call ids; results paired by order | 3,086 of 3,086 links I; 420 of 4,458 results (9.4 %) in 136 multi-call batches (claudesdk 24 %, googleadk 49 %) | `dtap.art.pairing_ambiguous_batch` | FO | per-call taint and exposure in multi-call batches rest on FIFO | as D.16.7 |
| N12 | Task configuration not verified for the run | tier B 36, C 19, missing 56 of 498 (windows `direct_prompt`, medical control) | `dtap.art.config_join_drift`, `config_missing_or_unparseable` | FO / NR | these runs carry no payload fixture and no exposure claim; attack analyses exclude them | `no_verified_configuration` count beside every exposure rate |
| N13 | Harness-default judgements | `direct_prompt` `task_success` true 101/101; benign `attack_success` null 101/101; direct `task_success` null 10 | `dtap.art.direct_prompt_constant_task_success` (b1 for the rest) | CR | utility rates biased upward if not excluded | as D.16.10 rate defaults |
| N14 | Re-judged results kept twice | 19 executions, 1 value changed | `dtap.art.rejudged_results` | RJ | attack rates depend on which value is used (corrected by default) | "both values reported; corrected value effective" |
| N15 | Re-run directories with one judge | 6 groups, 14 attempts unresolved, 1 unjudged | `dtap.art.rerun_single_judge` | FO / NR | unresolved attempts have no per-run outcome | count of excluded attempts |
| N16 | **new:** agent turn not logged / canned single message | 4 openclaw `direct_prompt` runs with only the user step (`ex_cmcq4rexu47horrn2xheesphxs`); 10 gpt-oss-120b runs with one identical message and no user step (`ex_7pmhkkkswftv65nqbeqro7yu2g`) | new | FO | refusal rates and "no attack success" for these runs may be logging gaps, not behaviour; identical trajectories across tasks | "N runs log no agent turn; M runs consist of one identical message" |
| N17 | **new:** domain spelled differently in path and `task_info` | 82 executions (`customer_service`, `os`, `multi_app`) | new (`seal_issue#dtap.path_field_mismatch` unclassified) | CR | none if the path is the domain (as AgentPROV does) | one sentence in the source card |
| N18 | **new:** task success with no tool call | 41 of 240 checker-true `task_success` (benign 10/86, direct 14/51, indirect 8/75, control 9/28) | new (FA row 9 analogue) | FO | utility may be vacuous for tool-requiring tasks | report beside utility rates |
| N19 | `env_vars` values inside run content | 79 executions (`FROM_EMAIL` 52, `HOSPITAL_HOST` 26, `USER_ACCESS_TOKEN` 2) | `dtap.art.secret_like_strings` (extend) | per D.16.13 (A) | none | covered by datasheet item 12 |

Extended rows: N13 extends FA row 1 (benign constant); N18 extends FA row 9.

### 10.2 Proposed `artefacts.toml` entries (text only; phase 10b; no corpus bytes)

- `dtap.art.agent_turn_not_logged`: scope `dtap-bench`; cause upstream harness; detector `dtap.user_step_not_logged@1`
  is not suitable. Use a generic detector "no message of role `agent` in an `agent_execution`" (new generic, or
  `claims` on `artefact.generic.harness_imposed_outcome` where applicable). Handling FO; expected: sample 4, snapshot
  from step 4.
- `dtap.art.path_domain_spelling`: `recorded_as.issues = ["dtap.path_field_mismatch"]`; detector
  `dtap.path_field_check@1`; handling CR.
- `dtap.art.derived_model_calls`: `claims = ["artefact.generic.accounting_unverifiable"]` with variant
  `aer.acc.agent_calls_vs_assistant@1`; detector `dtap.agent_segment_one_turn_unverified@1`; handling NR.
- `dtap.art.no_call_ids`: `claims = ["artefact.generic.provider_id_anomaly"]` variant `absent`; detector
  `dtap.pair_strict_alternation@1`; handling NR.
- `dtap.art.payload_not_observed`: `claims = ["artefact.generic.payload_not_reaching_agent"]`, pointing to the
  exposure classes (N9/N10); handling FO.
- `dtap.art.harness_default_outcome`: `claims = ["artefact.generic.harness_imposed_outcome"]`; detector
  `dtap.benign_attack_not_judged@1`; handling CR.
- `dtap.art.utility_without_tool_calls`: new generic detector or report-only; handling FO.
- Tighten as in b1: `naive_timestamp`, `secret_like_strings`, `copy_duplicate`, `goal_text_appended`,
  `rerun_single_judge`, `claudesdk_unknown_result_name`.

---

## 11. Delta against the phase-10 baselines

| Check | Baseline (phase 10, 8 corpora) | DTap sample | Explained by |
|---|---|---|---|
| C00 / X04 | 15/15; 0 | 15/15 (identical file); 0 | — |
| X01, X02, X05, X06 | 0 | 0 | — |
| U02, U03, U12 | 0 | 0 | — |
| U04 | 6 argument values (dropped high byte), CR 10 | C0/C1 17 strings, CR 17, ESC 2 (all raw terminal output) | corpus difference (desktop and terminal domains) |
| U05 PUA | 0 | 18 tool texts | corpus difference (raw) |
| U07 damaged paths | 0 | 1 (raw) | corpus difference |
| U09 repr | 127 object reprs | 1,258 repr heads in tool text | expected (D.16.2) |
| A03 empty turns | AgentDyn 4,632 … | 0 of 3,854 agent messages | — |
| R01f `verified_complete` | vacuous rows before B2 | 6, by `dtap.acc.counters` only | c2 |
| R01o unclassified | 156 after B4 | 1,229 | b1 |
| P01-P06, P08, P10, P11 | 0 | 0 | — |
| P07 within corpus | 0 variants | 61 of 877 keys | c1, b2 |
| P09 orphans | Gap, CaptureProfile, MessagePart, … | plus inference `apv:Assessment` 1,435 and fixtures 86 | d6; by design |
| D01 | 1,305 × 6, 0 differences (bound 0.23 %) | 499 × 6, 0 (bound 0.60 %): weaker n, whole sample | — |
| D02 | 350 of 350 (0.85 %) | 498 of 498 (0.60 %) | new DTap re-map |
| R03 | 0 mismatches | 0 (DT02, 10,108 steps) | — |
| G02 | 14,182 shared (2024-06/head) | 0 | — |

---

## 12. Threats to validity and reproducibility

**Environment.**
- Software: CPython 3.14.8 (macOS, Darwin 27.0.0, M2 Max shared with other sessions), `uv.lock` sha256
  `da3cceee…71c0d6`, `rfc8785` 0.1.4, `jsonschema` 4.26.0, `pyyaml` 6.0.3, agentprov 0.1.0. The formats are `aer/0.1`,
  `sem/0.1` and `agentprov-prov/0.1`.
- Corpus digests: `corpus.json` sha256 `a82fe827…bbf8fa1876`, `executions.jsonl` `ec0a6a5f…8db37cb`. The PROV stage
  identity is in `im01-import.json`.

**Seeds.** 20261011, unused in effect: D01 and D02 cover every execution. The `--sample 500` selection is deterministic
(stride 7919 over the sorted task directories).

**Commands, in order.** `$CD` = `~/.agentprov/migration-work/phase10b/check/dtap-sample-500.partial`, `$A` = its
`analysis/` sibling, `$D` = the data directory.
- import: `uv run python -I tools/dtap/import_dtap.py --corpus …/dtap-sample-500 --sample 500 --release --jobs 4`
  (897 s), and again with `--jobs 1` into `dtap-sample-500-j1`;
- T14: `tools/analysis2/exam2_selftest.py --corpus <mandate-p10>`;
- T01 and T02-T05: `phase10_extract.py --jobs 4`; `exam2_reuse.py aggregate|compare|rules`; `phase10_register.py`;
- T06: `exam2_scan.py --jobs 4`, then `exam2_merge.py`;
- T07, T08, T09, T10: `exam2_schema.py`, `exam2_p06view.py`, `exam2_corpusfiles.py`, `exam2_pathgrep.py`;
- T17 and T20: `phase10_dups.py`, `exam2_dups_utility.py`, `exam2_bymodel.py`;
- T13: `exam2_determinism.py sample --per-corpus 2000 --remap-per-corpus 0` (the 2 rows without PROV are dropped), then
  `run`, then `exam2_detsum.py` (688 s);
- T21: `import_report.py` with the adapted summary; `sem_import_report.py`;
- DTap tools:
  - `tools/dtap/dtap_check.py scan --jobs 3`, `summary`, `inventory --input <input tree>`;
  - `tools/dtap/dtap_check.py envvars --tasks <tasks worktree> --extra $D docs/reports/analysis/dtap-sample-check.md`;
  - `tools/dtap/dtap_check.py endorser --runs <runs worktree> --tasks <tasks worktree> --limit 10`;
  - `tools/dtap/dtap_remap.py --jobs 2`;
  - `tools/dtap/dtap_calibrate.py`;
  - `tools/dtap/dtap_report.py`;
- G02: a listing comparison of `raw/objects` names and `ex` ids (inline; result in `g02-overlap.json`).

**Committed.** Every file in `dtap-sample-check-data/`: counts, ids and truncated digests only. DT01 confirmed that none
of them holds an `env_vars` key or value. The per-execution rows (`dtap-rows.jsonl`, the T01 features and T06 scan
rows, the D01 outputs and the D02 rows) stay under `~/.agentprov/migration-work/phase10b/check/analysis/`.

**Not re-run (Q-071).** No second clean-environment run of the analysis tools. The DTap checks share the specification
with the adapter (same analyst family). DT03 and DT06 implement D.16.6 and D.16.5 as written; they agree with the code
here, and b3 records where the wording and the code differ without effect on this sample.
