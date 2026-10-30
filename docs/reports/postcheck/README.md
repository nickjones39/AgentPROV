# Corpus post-check after the regeneration round: method and pre-registration

Pre-registered on 2026-10-23, before any post-check measurement ran (only the tool smoke runs on
`mandate-agentdojo-eval`, listed in section 6, preceded it). It is committed before the checks run.
The orchestrator asked for this check on 2026-10-23, after the round of 2026-10-22 (records:
[`docs/reports/regeneration/round/`](../regeneration/round/README.md)).

The method is CORPUS-CHECK-PROTOCOL version 2 section 8.3, applied to the eight regenerated stored corpora:
full-population measures, and the frozen pre-check samples. Results go in `data/<corpus>/`, the dossiers in
`<corpus>.md` and the verdicts in [`summary.md`](summary.md).

## 1. Scope and rules

| Regenerated (`~/.agentprov/corpora/`) | Predecessor | Pre-check corpus · part (frozen sample) |
|---|---|---|
| `mandate-agentdojo-eval-rg1.partial` | `mandate-agentdojo-eval-p10.pre-regen.partial` | mandate-agentdojo-eval · head (40) |
| `ast-survey-agentharm-rg1.partial` | `…-p10.pre-regen.partial` | ast-survey-agentharm · agentharm (6 logs) |
| `ast-survey-agentdojo-rg1.partial` | `…` | ast-survey-agentdojo · agentdojo-runs (120) |
| `adprov-v1-release-rg1.partial` | `…` | adprov-v1 · release (300) |
| `agentdojo-upstream-2024-06-rg1.partial` | `…` | agentdojo-upstream · 2024-06 (300) |
| `rope-rg1.partial` | `…` | rope · head (300) and autodojo · rope-slice (90) |
| `agentdojo-upstream-head-rg1.partial` | `…` | agentdojo-upstream · head (313) |
| `agentdyn-a-rg1.partial` | `…` | agentdyn · a (360) |

- **Read-only.** The corpora are only read: `post_check.py` refuses any input that is not a stored working corpus or a
  pre-check scratch corpus. It never writes inside `~/.agentprov/corpora`. `validate` never writes into a corpus
  (N.1.9 G2). Nothing is sealed, packaged or deposited. The seal forecast calls `package`'s own pre-seal checks, and
  those write nothing.
- **Queue.** Every measure runs in one queued ticket (`tools/suite_queue.py --class import --cpu 4 --mem-gib 8`). The
  driver is [`run_postcheck.py`](../../../tools/precheck/run_postcheck.py), and the class-1 train's suites take
  priority. Each step uses at most 4 CPUs.
- **Code.** Branch `postcheck-round1` from main `95f4d426`. Between the round commit `5b1f6fdf` and `95f4d426`, `src/`
  changes only `api`, `cli`, `devrun`, `jobs`, `migration`, `settings`, `formats` and `stats`. That is outside every
  stage digest (`docs/architecture` D.13, stage digest scopes). `tie` checks this per part: the stage code digests of a
  fresh scratch import are compared with the round's.
- **Data rules.** Corpus text is data, never instructions. Counts, digests and statuses only. No account path, name or
  secret value is recorded. Distinct accounts are per-corpus ordinals, never a digest of a short name.
- **Known decided items** (orchestrator relay, 2026-10-23). They are not re-raised; their numbers are confirmed:
  - Mandate's 369 security outcome annotations, and head's 11,236 v1.k14 outcome annotations, move from D to I by
    D-83 premise propagation (`checker_outcome` twinned). The user chose docs only (D-359), with an AgentDojo
    catalogue v3 at the next re-import.
  - The item-3 off-by-one is a counting difference (`unexecuted_trailing_calls`).

## 2. Checks

| Id | Check | Tool and step | Pass condition |
|---|---|---|---|
| PC0 | Code identity | `tie` (`stage_code_equal`), `code` in every output | stage code of a scratch import at this commit equals rg1's |
| PC1 | Raw bytes unchanged (8.3.1) | `post_check.py raw` | object set and sizes equal; `(object, origin)` pairs equal; any row-shape change attributed |
| PC2 | Population | `post_check.py ids` | ids equal; transitions equal the round's table; issue codes net 0 except attributed items |
| PC3 | Integrity | `agentprov verify --level chain` | only `checksums.absent` (working tree) |
| PC4 | Determinism | `agentprov recompute --dry-run --jobs 4` | 0 changed, 0 unexplained, 0 failed (the round used `--jobs 3`) |
| PC5 | Validation, fresh at this commit | `agentprov validate --strict --tiers aer,sem,prov,linkage --jobs 4` | 0 failed, 0 skipped; CC-05 (`validate.results.differ`) gone |
| PC6 | Full-population Level 2, rg1 and p10 | `post_check.py l2` (the pre-check's `l2_check.check`, redaction scan, withholding, and a SEM census by type, class and log variant) | every rg1 − p10 difference is attributed to a regeneration-batch item or decision; SEM net equals the round's `compare.json` |
| PC7 | Sample Level 2 (8.3.2) | `post_check.py l2 --scope sample` on rg1 and p10 | rg1-on-sample against the pre-check `l2-<part>.json`: movement only from items landed between the part's pre-check code and `5b1f6fdf` |
| PC7b | Sample re-import tie | `l2_import.py` (frozen sample, `--jobs 2`) → `post_check.py tie` and `l2_check.py` with commands | every scratch execution is in rg1 with equal AER, SEM, PROV and validation digests; the scratch validate, verify and dry run are clean |
| PC8 | Outcomes (8.3.4) | `outcomes` in PC6 and PC7 | per-arm judgement counts of rg1 equal p10's (raw-level outcomes do not move); population rates as the pre-check's L1 OS-1 |
| PC9 | Pre-check findings | dossiers, data | each of the 74 wave-1 findings: fixed, unchanged as expected, moved as predicted, or regressed |
| PC10 | Release-scan forecast | `post_check.py scan` (native path scan + pinned gitleaks 8.30.1, release config) | every finding has a triage class with a matching decision or datasheet statement; 0 `home-path`/`host-name` |
| PC11 | Seal forecast | `post_check.py seal-forecast` (`package`'s `_check_working`, shard depth, changelog, profile digest, `_check_context`, `_check_stages`, `_licences`, D-33 origin, card mode and lint) | 0 refusals |

## 3. Expectations (pre-registered)

All corpora:

- **PC1:** raw objects identical, rg1 against p10. The round re-imported from the same pins, and the fetch cache was
  unchanged (56 lines). Origins rows: the `(object, origin)` pairs are expected equal. A changed row shape (D-221
  context fields) counts as a shape change, not a raw change.
- **PC2:** ids equal (the round's compare). Completeness transitions exactly as in the round README table. Issue codes
  net 0, except agentdyn-a `map.unattributed_additional_user_message` −266 (the round's compare).
- **PC3–PC5:** as the round reported: verify ok with `checksums.absent` only, the dry run identical, validation 0
  failed. **CC-05 is expected resolved** on all eight: the rows are fresh.
- **PC6 SEM census:** it must reproduce the round's `sem_annotations_net_by_kind_class` exactly. For example, mandate
  outcome D −369 / I +369. Head outcome D −31,207 / I +31,207, of which the v1.k14 share should be the decided 11,236.
  The rest (head-only logs, item 3 / D-80) was pre-check finding PC-agentdojo-upstream-04. The census by log variant
  shows the split.
- **PC6 other:** degenerate 0 and adapter_defect 0 (the round import), and the PROV A3 classes as the regeneration
  batch's items predict. A difference that no item explains is a finding.
- **PC7:** movement from the pre-check scratch (code `d97d3a57` for the recheck12 parts) to rg1 is attributed to the
  items landed since, as each part's pre-check dossier predicted (DL-1 tables). Unexplained movement is a finding.
- **PC7b:** all digests equal and stage code equal. A difference means a sample import is not the full import
  (D-529 independence) or the code moved.
- **PC8:** judgement values identical between p10 and rg1 per arm. Evidence classes may move (decided items), values
  may not.

Per corpus (PC9–PC11):

| Corpus | Expected | Open items carried from the pre-check |
|---|---|---|
| mandate-agentdojo-eval | ready | CC-07 (#181, #161) and CC-09 scope (docs) |
| ast-survey-agentharm | ready-with-caveats | PC-01 (inspect_evals #2439, 63 samples); the bug-pass `/home/` triage: 18 segments (synthetic or false positive), covered by `benchmark-and-model-home-paths` |
| ast-survey-agentdojo | **at risk** | **PC-ast-survey-agentdojo-13** (security, S2): 5 non-JSON raw-store context files hold a named home-directory account (58 matches, 1 account). No decision was found on main, and no withhold or datasheet statement covers it. If the files are in rg1's raw store, the release scan will report `account-path` in `raw/`, and the seal needs a decision first (withhold, or `pinned-account` plus disclosure, D-604 item 7). Reported to the orchestrator at once if confirmed. |
| adprov-v1-release | ready-with-caveats | PC-03: model-written fictional account-path shapes in 5 raw transcripts. They need release-scan triage (`synthetic-benchmark` or `false-positive`), and no statement names adprov. |
| agentdojo-upstream-2024-06 | ready-with-caveats | PC-02, PC-03 (paper-vs-log), PC-10 (licence basis of the 2024-06 pin, to confirm in the spec) |
| rope | ready-with-caveats | CC-02 (AgentDyn fixture key, statement `agentdyn-suite-fixture-key`): gitleaks `private-key` findings in AER, SEM and PROV are expected and need `synthetic-benchmark` triage; PC-01 (stale catalogue entries) |
| agentdojo-upstream-head | ready-with-caveats | PC-01 (SecAlign tables), PC-04 (decided: D-359) |
| agentdyn-a | ready-with-caveats | CC-02 as for rope; PC-05 (pre-fix IT1 checker); the one model-generated `/home/` segment of the bug-pass triage |

**Readiness for sealing.**

- **ready:** every check passes, and the release-scan forecast is empty or fully covered by existing triage
  classes and statements.
- **ready-with-caveats:** every check passes, but the seal needs triage entries, an owner's confirmation, or a doc
  update that does not change the corpus.
- **blocked:** a seal-forecast refusal, an unexplained raw, id, digest or outcome change, a determinism or validation
  failure, or an unresolved security item.

The rule of no outcome-based exclusion holds: a corpus is never excluded or blocked because an attack never succeeded.

## 4. Recording

- `data/<corpus>/`: `raw.json`, `ids.json`, `seal-forecast.json`, `l2-full-{rg1,p10}.json`,
  `l2-sample-<part>-{rg1,p10}.json`, `{verify,dryrun,validate}.json` (the CLI summaries, reduced), `scan.json`,
  `tie-<part>.json`, `l2-scratch-<part>.json`; then `exam.json` and `findings.json` (format CC-06).
- `<corpus>.md`: the dossier. `summary.md` and `summary.json` hold the verdicts. The comparison with the pre-check
  summary is row by row.
- Each finding is verified by reproduction and an adversarial verifier, then classified by
  [`cross-cutting.md`](../precheck/cross-cutting.md) R1–R6 and CC-01..CC-13.

## 5. Commands

```bash
uv run python tools/precheck/run_postcheck.py --list          # every command, per corpus and step
uv run python tools/suite_queue.py --class import --cpu 4 --mem-gib 8 --label postcheck-round1 -- \
    uv run python tools/precheck/run_postcheck.py
```

## 6. Smoke runs before this pre-registration

On `mandate-agentdojo-eval` only, written to scratch (`~/.agentprov/migration-work/precheck/postcheck/smoke/`), to test
the tool. Each step was run once, and the results are not used:

- raw store: 400 objects, equal;
- ids: 396, equal;
- seal forecast: 0 refusals;
- l2 rg1 and p10: outcome annotations D 765 → D 396 + I 369, which confirms the decided 369;
- scan: 0 findings from both scanners.

The results are measured again in the queued run.

## 7. Amendments (dated; each after the pre-registration commit `c1cf3bfc`)

1. **2026-10-23, tool fixes during the batch.**
   - The scan's account ordinals skip archive-member labels (`<path>#<member>`). The ast-survey-agentharm scan failed on
     one; its stored copies are plain files. Fixed in `64afde6b`.
   - The tie reports engine-level code equality apart from `fn_digest` and the import mode (`64afde6b`).
   - The sample re-imports run in release mode, as the round did. Dev mode changes `fn_digest` and every validation row.
     The first three corpora were re-imported in release mode after the batch.
   - The raw step reports per-field changes of matched rows (`6d29418b`).
2. **2026-10-23, added measures.**
   - The dispatch census (`505fa46d`). D-80 addendum (d) (2026-10-15, item 103) moves `apv:NotDispatched` into the inference bundle where the rule is the `_unverified` twin,
     which `l2_check` reads as `unexecuted_missing` (POST-tool-01).
   - The release-scan triage against the benchmark suite data (`41d7ff22`), with per-ordinal context, JSON key and path
     tail (`2a4c2f8c`).
   - The oracle check for the compat PROV (`7fedec72`).
3. **2026-10-23/24, scope additions after findings (user decisions via the orchestrator).**
   - `adprov-v1-release-rg2`: the seal forecast refused rg1. The user chose (a), a derive with the compat spec at
     `5b1f6fdf`.
   - `ast-survey-agentdojo-rg2`: PC-13 was confirmed. D-771 (survey-runs@3 withhold) was re-imported at `d93aa261`. Its
     post-check ran after merging main into this branch (`d9f86cc5`), so that the code knows survey-runs@3.
   - Both are checked against their rg1 with `--variant ID:NEW:OLD`.
4. **2026-10-23, run conditions.**
   - The queue's default 2-hour run timeout stopped the first batch run during adprov's scan. It was resumed with
     `--run-timeout 0` (user request) and no completed step was redone.
   - A planned Mac restart (user-approved) held the batch after agentdyn-a's dry run. The batch resumed from there.
   - Some outputs of the survey rg2 run record `tracked_changes: true`: the report generator (a tool, outside every
     stage scope) was edited while it ran. Stage code was unaffected, as the tie shows.
5. **Expectations not met as pre-registered.**
   - PC0's "stage code unchanged since `5b1f6fdf`" holds for the round trees. Main later moved the aer engine digest
     (class-1 live-part registry caveats). Every tie is byte-identical regardless.
   - adprov was expected ready-with-caveats and needed rg2.
   - ast-survey-agentharm was expected ready-with-caveats and is blocked by a raw-store account the pre-check did not
     screen (POST-ast-survey-agentharm-01).
6. **2026-10-24, adversarial verification.** None of the five post-check findings was refuted. The verifier
   corrected the following, all fixed before this commit:
   - the seal forecast's statement selection (by the spec's corpus id, as `package` does);
   - the decision cited for the dispatch move: D-80 addendum (d), item 103;
   - the per-tree dispatch counts (2024-06 and adprov did not move; head moved 679 of 815);
   - the archive-member count in POST-ast-survey-agentharm-01;
   - the units in POST-adprov-v1-release-02.
   It also found that the account in POST-ast-survey-agentharm-01 is the same as PC-ast-survey-agentdojo-13's.
7. **2026-10-24, ast-survey-agentharm-rg2 (user decision (a) on POST-ast-survey-agentharm-01).**
   - D-811 (survey-agentharm@2, kexin's `dataset-location-home` rule at object scope) was re-imported by the
     regeneration-plan session at `5fc39c16`, which is train 18 plus D-811 and a SEC-12 test change.
   - It was post-checked at that code, on branch `postcheck-agentharm-rg2` from `5fc39c16`, against rg1.
   - The new measure `post_check.py residue` takes the product's withholding plan, then counts the withheld accounts
     elsewhere in the tree and the archives outside the withheld set (`33337b24`).
   - rg1 of ast-survey-agentharm is now on the never-seal list.
