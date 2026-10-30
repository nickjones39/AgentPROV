# Bug pass: the new families (session bugpass-new-families)

Scope: the adapter work that landed after `docs/reports/bugpass/` (BF-n):
- phase 10j's six agentdojo-family profiles and identity tables (D-250..D-258);
- memo-ozdincer's results-container dialect and the shared agentdojo redaction (D-470..D-479, D-476, D-510);
- 10o part C, the `qwencode` family (D-570..D-579);
- 10i's agentops context pins with D-530 and D-560, held on `phase-10i-context` at `bd3f14e3`;
- the AgentDyn `history` part (R-10j-2, regen item 95), held on `regen-held-2` at `98168627`;
- `import --sample` (D-529) and its three stratum hooks.

Reviewed at origin/main `37be83cd` (10j `3a3f8110`, 10q `37be83cd`, 10o part C `fddf6ab1`). The held branches were read
only, in detached scratch worktrees.

Method: as in `docs/reports/bugpass/`. One read-only reviewer per area (A 10j, B 10q, C redaction, D qwencode, E 10i,
F agentdyn history, G D-529). Each area worked through the same checklist:
- invariant 2;
- evidence classes;
- identity against documentation;
- redaction in every form (plain, pointer-escaped, as a key, origin path, lex hint, issue text);
- withholding and selection codes;
- census counts against the profile;
- issue codes;
- determinism;
- README listing.

Every finding then went to its own verifier, which tried to disprove it. A finding was kept only with a reproduction (a
failing test or a command) under `repro/NF-nn_*`. Of 41 candidates, 37 were confirmed and 4 refuted. The verifiers
narrowed several claims to what they reproduced, and the table states the narrowed claim. Fixes are one per commit, each
with a regression test that fails before the fix.

Byte class as in BF-n: **0** = no stored AER/SEM/PROV byte and no stage code digest moves; **1** = the fix is under a
digest (`adapters/<family>/` with profiles and tables, `adapters/runner/`, `aer/`, `sem/`, `prov/`, `vocab/`, `validate/`,
`views/`). Class 1 becomes a regen-batch proposal (`proposals.md`). A class-1 finding in a file another session is
building on is routed (`routing.md`). Held-branch findings are routed to the branch owner.

| NF | area | severity | file:line | defect (as reproduced) | byte class | status |
|---|---|---|---|---|---|---|
| NF-1 | A | correctness | `adapters/agentdojo/profiles/environmentoptim-agentdojo.profile.toml:61,75` | the `runs/dojo_*` exclude and the lineage entry name the owner by corpus id `agentdojo-upstream`, not source id `agentdojo`; `_owner` falls back and the trial register holds 36,679 rows with the unregistered source id `agentdojo-upstream`; profile checks test only the id's shape, not registry membership | 1 | routed to regen-items (R-NF-1; edits this profile for item 105) |
| NF-2 | A | robustness | `docs/reports/phase10q/d510-directory-account-paths.md:60`; D-510 | the D-510 identity recipe (layout facet → `redact_value` → row) does not cover EnvironmentOptim's 13 doubly nested logs: under the layout grammar their account directory falls in the optional `arm` facet and `pipeline_dir` is `workspace`, so they resolve no model. Latent until R-10j-1 lands | 1 | routed to regen-items (R-NF-2; item 105) |
| NF-3 | A | docs | `docs/architecture/DECISIONS.md` D-250; `docs/reports/phase10j/census.md` §2, §9 | D-250 says the authority-caps table is keyed by experiment path and pipeline directory; as built it is keyed by pipeline directory only (`model_from = "pipeline_dir"`, 21 rows), which is defensible because the 3,260 re-packed copies span experiments, but nothing records it | 0 | P-1 approved by the user 2026-10-21: D-250 addendum and census §2/§9 corrected |
| NF-4 | A | docs | `adapters/registry/__init__.py` (kavach caveats) | all three Kavach caveats give the union "six directories identity_unresolved"; per pin it is 1 (3 logs), 6 (150), 5 (66) | 0 | **fixed 094de61e** |
| NF-5 | B | correctness | `adapters/agentdojo/results_mapper.py:829` | `outcome_imposed_by_runner` cites the class-D `rescont.exception_imposes_outcome@1`, while the judgements it reports cite the `_unverified` twin (D.5.4, D-472 with `verified_code = []`); the 10q trial counts 1,297 such issues | 1 | regen item 115: approved 2026-10-21, built on held `bugpass-nf-regen-results` |
| NF-6 | B | correctness | `adapters/agentdojo/results_mapper.py:359` | a container with no `defense` key and no table defence gets `task.defense_id = null` at class I with no premise and no locator: an asserted "no defence" that nothing logged (invariant 2); the attack path does it right (`unk` + `rescont.attack_unrecorded`) | 1 | regen item 116: approved 2026-10-21, built on held `bugpass-nf-regen-results` |
| NF-7 | B | robustness | `adapters/agentdojo/results_mapper.py:873` | a degenerate row in a container without `suite` writes `task.suite` from the row at O with no `/results/<i>/suite` locator. Latent (0 degenerate rows at the pin) | 1 | regen item 117: approved 2026-10-21, built on held `bugpass-nf-regen-results` |
| NF-8 | B | robustness | `adapters/agentdojo/results_mapper.py:806-829` | every `messages == []` row is relabelled `harness_default` without checking that its values are the ones the quirk declares (`utility = false`, `security = true`); other values lose their checker origin silently. Latent (all 1,038 such rows hold false/true) | 1 | regen item 118: approved 2026-10-21, built on held `bugpass-nf-regen-results` |
| NF-9 | B | docs | `DECISIONS.md` D-470, D-474; `docs/reports/phase10q/README.md` §5 | D-470 says the item value is `{container, row}`; as built it is the whole parsed container (aggregate included) and the locator selects the row (D.6.20 item 1 is right). D-474 says `identity_conflict` on 5,369 runs; the table also flags the five LoRA names on that checkpoint (6,306) | 0 | P-2 approved by the user 2026-10-21: D-470 and D-474 addenda, 10q README §5 corrected |
| NF-10 | C | **security** | `adapters/agentdojo/redact.py:189` | the redactor walks plain strings and keys only; an observed model string with a lone surrogate is stored as `{"$utf16": base64}` and keeps the account path in encoded form, with no D tag, no `rescont.redacted` entry and no issue; a plain-bytes leak scan cannot see it. Latent | 1 | routed to regen-items (R-NF-3; owns the redaction wiring, item 105) |
| NF-11 | C | **security** | `adapters/agentdojo/redact.py:100,114-123` | `parse_redact_rules` refuses only patterns that fullmatch `""`; zero-width patterns (lookarounds, `\b`) and the `{leaf}` fallback on a slashless value render a label that still holds the account, yet the pointer is reported redacted. R-10j-1's recommended rule is clean; the module does not fail closed. Latent | 1 | routed to regen-items (R-NF-3) |
| NF-12 | C | robustness | `adapters/agentdojo/mapper.py:237`, `capture_mapper.py`, `results_mapper.py` | builds that do not apply a declared `[[family.agentdojo.redact]]` scope ignore it silently (fail open): TraceLogger/DRIFT on main (item 105 wires these), the capture mapper, and `ResultsBuild` for any scope but `model_id`. Latent (no profile declares such a rule) | 1 | routed to regen-items (R-NF-3) |
| NF-13 | C | robustness | `adapters/agentdojo/results_mapper.py:296` | `ResultsBuild` skips the regen-item-7 / D-378 lone-surrogate pass; one lone surrogate in a message or tool output turns the row into a 3-record `adapter_defect`. Latent | 1 | regen item 119: approved 2026-10-21, built on held `bugpass-nf-regen-results` |
| NF-14 | D | correctness | `adapters/qwencode/dialect.py:152-165` | salvage runs on any strict-loader rejection (invalid UTF-8, duplicate key, NaN, trailing data, over-size), not only a capture cut: the prefix is mapped and the rest dropped silently instead of the D.2.8 case-3 degenerate AER. Latent | 1 | regen item 120: approved 2026-10-21, built on held `bugpass-nf-regen-qwencode` |
| NF-15 | D | robustness | `adapters/qwencode/dialect.py:172-230` | salvage cost is unbounded (up to 4,096 full strict parses plus a quadratic `_spans`); nothing limits the input to the 64 KiB the comment states: 32 KiB took 72 s, 64 KiB 114 s. Latent | 1 | regen item 121: approved 2026-10-21, built on held `bugpass-nf-regen-qwencode` |
| NF-16 | D | correctness | `adapters/qwencode/mapper.py:51` | the logged `result.stats` (per-model, per-source request and token counts, per-tool counts) is in all 3,295 result messages but not in `_RESULT_FIELDS`, so no AER/SEM/PROV holds it (D-572: result fields in ext); the part-C census misses it | 1 | regen item 122: approved 2026-10-21, built on held `bugpass-nf-regen-qwencode` |
| NF-17 | D | correctness | `adapters/qwencode/dialect.py:297-307` | a selected run output in the D.24.1 grammar that is malformed or of an unsupported Qwen Code version is registered `select.not_execution_artefact` (info, generic detail) instead of a degenerate AER (D.2.8 case 3). Latent | 1 | regen item 123: approved 2026-10-21, built on held `bugpass-nf-regen-qwencode` |
| NF-18 | D | robustness | `adapters/qwencode/mapper.py:~630,703,734,~676` | a null/absent/non-string `tool_use.name` or non-string user text reaches the writer (`'None'` sentinel, schema type errors); the run becomes `adapter_defect` instead of a recorded data problem. Latent | 1 | regen item 124: approved 2026-10-21, built on held `bugpass-nf-regen-qwencode` |
| NF-19 | D | correctness | `adapters/qwencode/mapper.py:782-790` | a score entry without `score` becomes an observed judgement value `null` with a locator to a missing key; `true` takes the score-1 path; a string score is stored as O and SEM drops it silently. Latent | 1 | regen item 125: approved 2026-10-21, built on held `bugpass-nf-regen-qwencode` |
| NF-20 | D | robustness | `adapters/qwencode/mapper.py:566` | a second `result` message is skipped with no record or issue, even when it contradicts the first; a non-UTF-8 `execution_rules.md` is registered as a sidecar with no fixture and no issue. Latent | 1 | regen item 126: approved 2026-10-21, built on held `bugpass-nf-regen-qwencode` |
| NF-21 | D | correctness | `adapters/qwencode/semantics/tools.py:192-200` | every integer score other than 0 and 3 is annotated `qwencode.non_informative` citing `qwencode.score_meaning@1`, which covers score 1 only (D-576, D.24.7). Latent (scores 0, 1, 3 only). The openhands sibling has the same catch-all (outside this pass) | 1 | regen item 127: approved 2026-10-21, built on held `bugpass-nf-regen-qwencode` |
| NF-22 | D | docs | `docs/architecture/D_adapters.md` D.24.6; `docs/reports/phase10o/part-c.md` §5 | "the Qwen part's only home path is `/home/user/`"; the runs zip also holds `/home/node/` (11) and one RedCode payload name (58), which is benchmark content (no operator account; D-578 stands) | 0 | **fixed 5c27c279** |
| NF-23 | E | correctness | `src/agentprov/corpus/manifest.py:683` (`is_exclusion`) | the seal matched an archive member's exclude glob against `<archive>!/<chain label>`; the importer matches the member label, so D-560's select rows count as candidates at seal and verify. Latent on main | 0 | **fixed 02da616a** |
| NF-24 | E | robustness | `corpus/package.py`, `corpus/rawtree.py` (held) | `package` seals a corpus imported with context trees or R3 pinned objects without a refusal or notice; the closed corpus-0.1 snapshot drops `context[]`/`pinned_objects`, so every re-map of the sealed corpus runs without the joins (`recompute`: 23/25 unexplained on the fixture) | 0 | user decision 2026-10-21: corpus/0.2 carries both (with deferrals part C); **backstop b055b05c**: `package` refuses such a corpus (`package.refused.context`) until then |
| NF-25 | E | determinism | `adapters/runner/importer.py:2261` (held) | the G4 resume check ignores context roles, pins and `pinned_objects`: a resumed working corpus can mix joined and unjoined units while the manifest records the last run's set | 1 | routed to phase-10i-context (R-NF-5) |
| NF-26 | E | robustness | `corpus/derive.py:1910` (held) | a re-map writes `snapshot.context[i].verification = null`; `recompute` does not notice (corpus.json not compared). Manifest only | 0 | routed to phase-10i-context (R-NF-5) |
| NF-27 | E | robustness | `cli/import_.py:495` (held) | `--context` accepts a duplicate ROLE (last wins) and a PATH with no file matching the role's `context_artefacts` (vacuous pin check; every unit un-joined; exit 0) | 0 | routed to phase-10i-context (R-NF-5) |
| NF-28 | E | robustness | `cli/import_.py:527,556` (held) | a context download pin or `lfs_object` pin without `sha256` is accepted from the fetch cache, checked by md5/size only; every other path refuses it (`raw.fetch.unverifiable`) | 0 | routed to phase-10i-context (R-NF-5) |
| NF-29 | E | docs | `cli/import_.py:503`, D-530, MN N.2.2 (held) | `--no-context` is described as "recorded" but leaves no record in the corpus (CLI notice only) | 0 | routed to phase-10i-context (R-NF-5) |
| NF-30 | F | robustness | `adapters/runner/__init__.py:497` (held) | `own_pin_part` ignores the file's origin commit, so `--snapshot history --pin head` would map all 47,723 head files as part `history`. Latent (needs the wrong pin named) | 1 | routed to regen-held-2 (R-NF-6) |
| NF-31 | F | docs | `adapters/registry/__init__.py:490-494` and profile/table/README and the D.6.14 history item (all on the held branch) | the history part is described as 621 `drift.k18.messages` logs; one is `v1.k14.incomplete`, and `variants` omits it | 1 (profile text) | routed to regen-held-2 (R-NF-6) |
| NF-32 | F | docs | `agentdyn.profile.toml:66`, `tables/agentdyn_history_pipeline_dirs.toml` (held) | the history pin's commit facts are wrong: the directory was replaced at `4d2748c6`, not `6623a721`; the 621st file is not present from `2d4ad05a` | 1 (profile text) | routed to regen-held-2 (R-NF-6) |
| NF-33 | F | test-gap | `tools/agentdojo/profile_census.py`, `tests/full_corpus/test_profile_census.py` | the census found a part's pin only by `part == X and primary`, so agentdyn's part `c` (six DRIFT quirk counts, files of the `head` pin) was always skipped, and the tool raised a bare `StopIteration` | 0 | **fixed 850b2142** (+ 2df67fd2) |
| NF-34 | G | determinism | `adapters/runner/importer.py:2130` | resuming a sampled multi-execution import drops a file sealed whole (degenerate) from the candidates, so a different sample is drawn and the corpus holds the union. Latent | 1 | regen item 128: approved 2026-10-21, built on held `bugpass-nf-regen-runner` |
| NF-35 | G | correctness | `adapters/runner/importer.py:2095` | a refused `--sample-mode spread` (no hook) still rewrites corpus.json and derivation.json, which can erase a recorded `selection.sample`. Latent | 1 | regen item 129: approved 2026-10-21, built on held `bugpass-nf-regen-runner` |
| NF-36 | G | correctness | `adapters/runner/importer.py:2576` | `partial` and `selection` come from the last run only; a sampled snapshot followed by a full one leaves `partial: false`, and `package` accepts the corpus. Latent | 1 | regen item 130: approved 2026-10-21, built on held `bugpass-nf-regen-runner` |
| NF-37 | G | robustness | `adapters/inspect/dialect.py:140-143` | `sample_stratum` splits at the first `!/`, so a `.eval` inside a declared nested archive gets the archive as its stratum and `spread` does not spread (controlarena-persistent v2) | 1 | regen item 131: approved 2026-10-21, built on held `bugpass-nf-regen-runner` |
| NF-38 | A | test-gap | `tests/adapters/agentdojo/test_defence_denial.py` | the orchestrator's check of 1b96a80b: the 7 → 10 count is right (seven head-only 10d profiles plus Kavach's three parts), but the widened pin accepted any `observed` keys | 0 | **fixed 62bb5f92** (keys must equal the profile's parts; mutation-checked) |

## Observations from the build reviews (2026-10-21; not counted as findings above)

- **Other rescont issues cite D rules directly** (item 115's builder): `injection_map_not_recorded`,
  `request_not_recorded`, `melon_calls_not_recorded` and `n_results_mismatch` cite D rules that have `_unverified`
  twins. This is the same kind of problem as NF-5. A real-fixture test that walks every issue's rule fails on them.
  The generic mapper cites issue rules "as given" (D.5.4's default), so this needs a ruling before it becomes an item.
- **The benign-constant path ignores the logged value** (item 118's reviewer): on a benign exception row whose logged
  `security` is not `true`, the benign-constant origin is imposed unchecked. This is the analogue of NF-8. Latent: the
  profile declares no param for the benign quirk. Not reproduced as a separate finding.
- **`--retry-failed` on a capped snapshot** (item 130's reviewer): retried non-degenerate failures can be counted
  into the snapshot's cap twice. Plausible, not reproduced.
- **The openhands siblings of NF-19 and NF-21** (`openhands/mapper.py:1259`, `openhands.tools@1`) are outside this
  pass. The openhands owner decides.

## Orchestrator checks

- **test_defence_denial (1b96a80b):** NF-38.
- **Kavach denials 45 × 3:** correct. `observed` is the uncollapsed census per pin. All 45 `[KAVACH BLOCK` tool errors are in `results_v2/agentdojo_slack_gemma_dell/logs/local-kavach`, which all three pins hold. The branch-only Kavach arms hold no tool messages. The 10j trial corpora (`-j 2` and `-j 4`, after the D-253 collapse) each hold 45 AERs with one denial decision each, so the corpus has 45 decisions, not 135.
- **AgentDyn history, single owner** (by blob id, `GIT_NO_LAZY_FETCH=1`, `ls-tree` only):
  - the 621 blobs at `785b9127:runs/gpt-4o-mini-2024-07-18-drift/` are distinct, and none occurs anywhere in AgentDyn head `5353cf76`, DRIFT or drift-1;
  - EnvironmentOptim `febf82d8` holds exactly 620 of them at the same paths and ids;
  - the 621st (`v1.k14.incomplete`) is nowhere in EnvironmentOptim.
- **AgentDyn history, orphans:** none.
  - Every blob under EnvironmentOptim's eight `owner = "agentdyn"` globs is held by an agentdyn part: 47,681 = 47,061 at head plus 620 in history.
  - All 36,679 `runs/dojo_*` blobs are in the cached upstream pins (the owner's id form is NF-1).
  - No selected or `redaction_pending` EnvironmentOptim blob occurs in any AgentDyn commit.

## Not findings (refuted by the verifiers)

- `docs/reports/phase10q/census.json` records a profile sha256 no committed profile has. It is the digest from before the `observed` lines were written back, the census workflow every report follows.
- The phase-10q leak check derives its search strings from the rules. That is its stated scope, it is complete for the pin, and D-510's generic path lint is routed.
- Items 98-100 omit an AER-set change for LFS objects through the CLI. No such stored corpus exists or can exist: mcphunt is `planned` and refused.
- The history slice brings the D-257 bare key header into agentdyn. It stays inside RT-10/CC-02's counted scope; at most a count note when that decision is written.

## Checked and clean (reviewers' notes, abridged)

- **10j:**
  - every `observed` quirk count of the six profiles equals the stored census reports (`differences: []`);
  - the selection tallies reconcile: EnvironmentOptim 104 + 6,016 + 84,360 = 90,480; drift1 626 + 1,569;
  - `dedup.collapsed` reconciles: authority-caps 3,260; Kavach 634 = 264 + 370;
  - the identity rows match the documents (DCA README, Kavach run summaries, authority-caps suffixes, D-254);
  - no account or home path in any selected raw log of the six sources, nor in the trial AER/SEM/PROV (including `~1` escapes);
  - `-j 4` and `-j 2` trial compares show 0 differing files;
  - both README generators pass `--check`.
- **History part:**
  - invariant 2: no invented times;
  - origins and `introduced_in_commit` match the trees;
  - fixture-scale determinism holds under three hash seeds;
  - real-data determinism (2026-10-21, `regen-held-2` 98168627): the history part imported at `-j1` and `-j2` gives
    byte-identical aer/sem/prov/raw/validation, `executions.jsonl` and `register.jsonl` (2,490 files each, 0 differing);
  - redaction is clean in every corpus file.
- **memo-ozdincer real-data determinism (2026-10-21, this branch at cd09b8f5):** `tools/agentdojo/phase10q_trial.py
  import` at `-j1` and `-j2` gives byte-identical corpora (39,370 files each, 0 differing; the same counters and issue
  codes: 13,070 mapped, 0 failed). `-j1` took 7,699 s and `-j2` 4,944 s (each in an import-queue slot at `--cpu 2`).
- **D-529:** the modes are as specified (`random` keys by sha256, `spread` takes strata round-robin, `first`), and every refusal path is checked.

## Not covered

- PROV statement review beyond grep scans.
- A real-data re-import of the DCA part (blocked by R-10j-3).
- The `full_corpus` census runs of the six 10j profiles: the stored reports were used.
- Qwen Code real-data imports: the part waits on D-530's recipe.
- The openhands sibling of NF-21, which is outside this pass.
