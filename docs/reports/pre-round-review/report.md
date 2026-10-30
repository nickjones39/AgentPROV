# Pre-round integration review: integration/pre-round-2026-10-21 @ cdd26e34

Date: 2026-10-22. Base: main 238b34a8 (main fc84e7d5 since, docs only). Reviewer: session pre-round-review
(orchestrator "Phase 8 setup"). The checklist drafted while parked is in [checklist.md](checklist.md).

## Verdict

**Not ready for the regeneration round as integrated.** The proofs are clean: every byte the combined tree changes is
predicted by an item. But the review found interaction defects, and some must land before the round because their fixes
move runner (`aer` stage) digests or working-manifest bytes:

- **Two seal blockers** from part C (D-221) × D-530 (PR-1, PR-2). Every context tree resolved the default CLI way, and
  every corpus with an R3 pinned LFS object, cannot be packaged.
- **A version-guard gap** (PR-3). `recompute` neither refuses nor reports the aer/0.1→0.2 and apv 0.1.0→0.2.0 moves. A
  re-map silently upgrades a 0.1 corpus, which D-430 rules out. A re-derive without a re-map seals apv 0.2.0 PROV under
  `ontology.version` 0.1.0, which D-500 rules out.
- **Five medium runner/derive interactions** (PR-4..PR-9) and a recompute false alarm (PR-10).

Everything else is low severity or documentation. Before the round: PR-1, PR-4, PR-6, PR-8, PR-9 and the runner items of
PR-11 (class 1, importer), and PR-3 (class 0, but it guards the round's own recompute checks). PR-2, PR-5, PR-7, PR-10,
PR-14 and the rest can land before or with the round. PR-2 and PR-14 (two datasheet statements that fail the H.9(3)
lint, so three corpora cannot be packaged) must land before any seal or deposit.

## Method

- **Review:** a workflow (`wf_efc8da0d-c87`, 75 agents) with eight finder dimensions:
  - importer selection;
  - importer stop/drain;
  - the derive chain;
  - versions and digests;
  - part C;
  - redaction and withholding;
  - adapter files that several merges edited;
  - docs and digest predictions.

  Every finding went to two adversarial verifiers. One tried to refute it by reproduction; the other by intent, scope and
  pre-existence at base. A completeness critic then looked for uncovered merges and files, and its finding was verified
  the same way. Of 33 findings, 28 were confirmed by both verifiers, 4 are plausible (one of the two refuted) and 1 was
  refuted. Probes are under `~/.agentprov/review/pre-round/probes/<dimension>/`.
- **Proofs:**
  - Scratch only, through main's `suite_queue --class import --cpu 2`, `--jobs 2`, `GIT_NO_LAZY_FETCH=1`, no network.
  - Data under `~/.agentprov/review/pre-round/proofs*/`; scratch corpora under
    `~/.agentprov/migration-work/precheck/pre-round-review/`.
  - No stored corpus was written; the snapshots before and after are identical.

## Proofs

### Re-map of a sample per stored corpus, base 238b34a8 against int cdd26e34

- **Scope:** the eight p10 corpora.
  - 24 labels each from the pre-check's pre-registered L2 samples; AgentHarm is 2 `.eval` = 352 executions.
  - Plus targeted item-103 samples (executions with `map.unexecuted_tool_call`).
- **Every difference is attributed, and none is unpredicted:**
  - item 20: `aer` 0.1→0.2, the seal `records_sha256`, `corpus.json` formats;
  - item 85: the vocabulary 0.2.0, the `*Status` null form, and the aprov catalogue digest;
  - item 86: `apv:adapterAssumption`;
  - item 95: agentdyn@3;
  - item 103: the `_unverified` twin rule, and the `NotDispatched` inference bundle combined with item 24;
  - D-451 and BF-39: every stage's engine digest, and the AgentHarm `members.jsonl` `fn_digest`;
  - the family code and catalogue digests (in-place v2 catalogue edits).
- **What did not move:**
  - `raw/objects` and `raw/origins.jsonl` are byte-identical in every pair.
  - Import reports are identical except agentdyn's profile version.
  - Index `completeness`/`status`/`issues` are unchanged.
- **The "no stored byte" items hold in the sample:** 77/78, 87-93, 96-101, 105, 108, 115-131, 145, 150.
- **On the INT scratch corpora:** `recompute --dry-run` reports 0 differences on all 14; `verify --level chain` is ok on
  all 14; INT `--jobs 1` = `--jobs 2`.
- **Stored mandate-p10 at INT:** `recompute --dry-run` gives 396 `changed_explained`, 0 unexplained; the stored tree is
  unchanged.
- **D-430 holds for catalogue drift:** a BASE corpus with catalogue drift is refused on `--out` (exit 4, `version_drift`).
  A corpus with only format and vocabulary drift is not refused (PR-3).

### Redaction and withholding, one scratch import per family

No leak in any shipping or local channel. One new seal blocker (PR-14). Details are in the section "Redaction and
withholding proof" below.

## Findings

Severity is after verification. "Class": 0 = no corpus or derivation byte; 1 = stage or code digests only; 2 = corpus
content or manifest bytes. Owners as routed by the orchestrator: archived sessions are re-opened by it.

### High (blocks sealing)

**PR-1. D-221 refuses every context tree resolved the default CLI way** (findings #12, #18, #23; CONFIRMED ×3).
- **Interaction:** 10i D-530 (e92a4091) × part C D-221 (4b6d8c8e); also D-602/D-578, qwencode, dtap-sec, agentops-sec.
- **Cause:**
  - The CLI returns `pin_check None` for the default context trees:
    - every download (archive) context pin (`cli/import_.py:597`, `:603`);
    - a git context resolved from the fetch cache (`GitPinTree`, `:611`).
  - The importer then writes `snapshot.context[].verification: null` (`importer.py:2981`).
  - `package._check_context` (`package.py:405`) refuses any entry whose verification is not `{unverified: 0}`
    (`package.refused.unverified`).
  - Only `--context ROLE=PATH` for a git role gets a PinCheck, and the D-221 tests cover only that route.
- **Effect:** these corpora are unsealable:
  - redcode-exec-qwencode with its `supp` zip, by any route (so D-602's withholding of the token-bearing zip never reaches
    a seal);
  - redcode-exec-openhands with its supp context;
  - dtap-bench and agentops-bench `tasks` imported with `--fetch`.
- **Probes:**
  - `probes/partc-int/p4_archive_context_package.py`;
  - `probes/docs-digest/ctx_withhold_probe.py` with its control;
  - `probes/redact-withhold/p2_ctx_seal.py`. Patching in `{kind: archive, verified: stored, unverified: 0}` makes the
    seal succeed, withhold correctly and pass `verify --level chain --release`.
- **Fix:**
  - Record a verification for pinned trees at import: archive by sha256 and size, fetch-cache git by blob ids. The D-530
    write-up planned `{kind: "download"}`.
  - Or let `_check_context` accept these tree kinds.
  - Add the deferred seal e2e tests (qwencode/openhands supp, a cache-route `tasks`).
- **Class:** 2 for working manifests if the verification is recorded, so it lands before the round.
- **Owner:** deferrals (part C) with 10i.

**PR-2. A corpus with an R3 pinned LFS object cannot be sealed** (critic finding #32; CONFIRMED, verifiers say medium;
listed here because it blocks every dtap-bench@2 and mcphunt@2 seal).
- **Interaction:** 10i D-530 item 6 × part C D-221/NF-24.
- **Cause:**
  - `_with_overlay` (`importer.py:1347-1357`) maps the pinned object as a primary candidate with an `hf` origin.
  - `seal` builds the snapshot origin from every primary's root origin (`package.py:795-802`), with no pinned-object
    exclusion.
  - `snapshot_origin_from_pin` refuses git+hf as mixed kinds (`manifest.py:1003`), giving `package.refused.pin`.
- **Probe:** `probes/critic/p1_lfs_seal_origin.py` (DTap fixture with one LFS object).
- **Fix:** drop the recorded pinned objects' exact (sha256, origin) pairs before `snapshot_object_origins`, mirroring
  `rawtree`'s `pinned_keys`. Add a positive seal and `verify --level chain` test for DTap and MCPHunt.
- **Class:** 0 (package).
- **Owner:** deferrals (part C).

### Medium-high

**PR-14. Two datasheet statements fail the H.9(3) statement lint, so `package` refuses three corpora** (redaction
proof; re-checked independently: `probes/main-lint/lint.py`).
- **Failing statements:**
  - `agentharm-raw-withheld-account-paths` (literal `kexin-xu-01`) blocks kexin-xu-01-agentharm and fragfuse-agentharm;
  - `environmentoptim-raw-paths-account-segment` (literal `Qwen3.5`) blocks environmentoptim-agentdojo.
- **Effect:** `agentprov package` exits 1 with `corpus.datasheet.statements`.
- **Scope:** at base 238b34a8, 0 of 42 statements fail H.9(3); at int, these 2 of 52 do.
- **Origin:** items 106/108 (b339e499) and the item-107 follow-up (72d808bf). The claims lint did not change.
- **Why no test caught it:** nothing in the suite lints the whole table or seals these corpora.
- **Fix:** move the literal numbers into declared `figures` placeholders, or reword. Add a test that runs
  `CHECKER.lint_card` over every statement in `corpora/datasheet-statements.toml`.
- **Class:** 0, but a seal blocker. **Owner:** regen-items (items 106-108).

**PR-3. `version_drift` ignores the AER format and the vocabulary version** (proof P-1 + findings #10, #13; CONFIRMED ×3).
- **Interaction:** D-430 (main) × part C aer/0.2 and corpus/0.2 × items 85/86 (apv 0.2.0).
- **Cause:** `Derivation.version_drift` (`corpus/derive.py:773`) lists only profile and catalogue version or byte drift.
- **(a) Re-map:** a re-map recompute `--out` of a BASE-built 0.1 corpus with no catalogue drift writes a uniform
  agentprov-corpus/0.2 / aer/0.2 / apv 0.2.0 corpus.
  - Case: what-surrounds (wirelog family, untouched).
  - No refusal and no notice: the stage `format` change marks the stage changed, so every AER difference is
    "explained".
  - D-430 says a writing recompute refuses when this build records a declared version differently, and that there is no
    upgrade mode.
  - Files: `proofs/logs/recompute-probe-{dry,out}-base.json`, `cmp/probe-outint-vs-outbase.json`.
- **(b) Re-derive without a re-map** (`--stages sem,prov,validation`) of a 0.1 corpus:
  - It keeps format 0.1 (C.21 item 5, `derive._base_manifest`), but the PROV states `apv:vocabularyVersion 0.2.0` with
    0.2.0-only terms.
  - `package` would seal `ontology.version 0.1.0` (`package.py:767,945`, `manifest.py:202`). D-500 and regen-batch
    lines 1487-1490 say this state must not exist.
  - Applies to adprov-v1, ast-survey-agentharm, rope and credleak-p15b, which have no catalogue drift.
  - Probes: `probes/versions-digests/probe_ontology.py`, `probes/part-c/p5*`.
- **Fix:**
  - `version_drift` adds the format lines: `aer: format aer/0.1 recorded, aer/0.2 current` and the corpus format.
  - It adds the vocabulary line: `prov: vocabulary apv 0.2.0, corpus/0.1 pins 0.1.0`.
  - A writing recompute or derive then refuses before `NEW.partial` exists. Optionally, `package` also refuses a
    corpus/0.1 seal whose PROV vocabulary is not 0.1.0.
- **Class:** 0 (corpus/derive and package are in no stage digest).
- **Owner:** deferrals (part C), with the regen plan (D-430).

### Medium

**PR-4. D-530's `_archive_context` stores the context archive before checking its digest** (#0; CONFIRMED, interaction).
- **Interaction:** core-B item 58 (CB-20) × D-530 item 99.
- **Cause:** `importer.py:1376-1386` calls `add_object` without `expected_sha256`/`expected_size` and compares only
  afterwards.
- **Effect:** a swapped `supp.zip` stays in `raw/objects` with the pinned zenodo origin after `raw.digest.mismatch`. That
  is the false pinned origin CB-20 removed elsewhere.
- **Probe:** `probes/runner-sel/p2_context_swap.py`.
- **Fix:** pass `expected_sha256=archive.sha256, expected_size=archive.size`, as `archive_members` does, and add a
  regression test.
- **Class:** 1. **Owner:** 10i.

**PR-5. A re-map of a corpus whose context-tree or pinned object is absent on purpose crashes** (#9; CONFIRMED).
- **Interaction:** D-530 re-map (`StoredRawTree` context and pinned objects) × BF-20/CB-6 `exclude_absent`, which covers
  primaries only × D-602 / part C making context withholding reachable.
- **Effect:** after a purge of the archive context, a `tasks` file or a pinned LFS object, `recompute --dry-run` and
  `verify --level rederive` end in exit 70 (`KeyError`, from `StoredArchive.__init__` `store.size`) or
  `corpus.rawtree.invalid`. The control, a purged primary, behaves as BF-20 says.
- **Probes:** `probes/derive-chain/test_probe_absent_{archive_ctx,context}.py`.
- **Fix:** `exclude_absent` and `StoredRawTree` drop absent objects from `recorded_context`/`recorded_pinned_objects`, and
  mark the dependent executions unverified.
- **Class:** 0 (corpus/). **Owner:** 10i, with derive-bugpass (twins).

**PR-6. A drain sent to `recompute`, `derive` or `verify --level rederive` is honoured inside their re-map** (#5;
CONFIRMED).
- **Interaction:** D-525 premerge-2 (the importer drain) × the re-map callers × D-610.
- **Cause:** `_Pipeline.run()` calls `drain.drain_supported()` unconditionally (`importer.py:2228-2231`). `--control-file`
  is global, and the re-map callers ignore the returned report.
- **Effect:** a GUI "Pause" yields a truncated NEW, marked incomplete `{drained}`, reported as `failed`/`corpus_unexplained`
  (exit 1) with no mention of a drain. MN N.1.10(5) and D-525 say an unwired command degrades to a stop.
- **Probe:** `probes/d610-runstate/probe_recompute_drain.py`.
- **Fix:** make the drain opt-in (`import_source(..., drain=True)` from `cli/import_.py` only).
- **Class:** 1. **Owner:** cli-robustness.

**PR-7. A recompute resumed with the opposite `--skip-prov-conformance` setting is accepted** (#8; CONFIRMED, not an
interaction: one lineage).
- **Effect:** a recompute interrupted under the skip and resumed without it gives a NEW that claims full tier 4. One row
  has no PV-NE checks, and verify and validate pass.
- **Cause:** `_current_definitions` (`derive.py:553`) omits `prov_conformance`, so `derived_from()` and
  `_reuse_corpus_key` do not distinguish the setting.
- **Fix:** thread the setting into `_current_definitions`.
- **Class:** 0. **Owner:** cli-robustness.

**PR-8. `--sample` on a multi-execution import with an R3 pinned object loses the LFS pointer and over-selects** (#1;
CONFIRMED).
- **Interaction:** D-529 × D-530 item 6 × NF-34 `label#` keys.
- **Effect (MCPHunt):** `--sample 1` seals both object traces (selected=1) and drops the pointer's
  `select.not_execution_artefact` row.
- **Probes:** `probes/runner-sel/p3_overlay_sample.py`, `p3b_keys.py`.
- **Fix:** key pass-1 storage and sample keys by candidate identity, not by label alone.
- **Class:** 1. **Owner:** 10i / NF bug pass.

**PR-9. A sampled-out multi-execution file that another snapshot sealed whole is collapsed into the sampled snapshot in
pass 1** (#2; CONFIRMED).
- **Cause:** `_store` calls `_seen_before` (the D-202 collapse) in pass 1, before the sample is drawn.
- **Effect:** `executions.jsonl` lists the file under the sampled snapshot, with a `dedup.collapsed` row, though it was
  not selected. At base it was neither a candidate nor counted.
- **Probe:** `probes/runner-sel/p1_collapse.py`.
- **Fix:** defer the `_seen_before` side effects to pass 2, when the `label#` key is sampled.
- **Class:** 1. **Owner:** NF bug pass (D-529 owner: cli-robustness).

**PR-10. At INT, recompute of any archive-input corpus built before BF-39 exits 1** with
`raw/members.jsonl differs ... UNEXPLAINED` (proof P-2; CONFIRMED).
- **Cause:**
  - Each member row records the expand `fn_digest`, and BF-39 moves it, so a code-only expand change never gives
    identical bytes.
  - The other stages get the H.8.4(2) notice instead.
  - Seen on what-surrounds (10,744 rows) and AgentHarm (476).
  - The behaviour pre-exists for any `EXPAND_MODULES` edit; BF-39 makes it hit every stored archive corpus. BF-39's
    prediction names only `derivation.json`.
- **Fix:** `_compare_corpus_files` counts an expand code-digest change as explaining `members.jsonl` when only
  `/fn_digest` differs. Or record the expected exit 1 in the round notes and the prediction.
- **Class:** 0. **Owner:** bug pass review (D-451).

### Low

**PR-11. Runner, class 1 (land with PR-4..PR-9):**
- **#3:** pass 1 of a sampled multi import ignores D-321's `_rows_refused`, so a file later sealed whole changes the resume
  key set (`random`/`spread` resumes can draw differently). Owner: NF bug pass.
- **#4:** a `url` context pin fetched with `--fetch` ignores the fetch cache's retrieval time. `_context_tree` omits
  `retrieved_at=outcome.retrieved_at`, so the import is refused when the pin lacks one (D-455 × D-530). Owner: 10i.
- **#6:** the D-610 clean-tail rule looks only at sealed units, so an item rejected by the AER write gate after a counted
  item of the last candidate leaves a drained `--limit` run unmarked. Owner: cli-robustness / NF bug pass.
- **#7:** item 108's `_hold_account_paths` runs before RD-3's `pin_candidates` snapshot (`importer.py:1311-1313`). A
  listing pin is then checked over the listing minus the held file, so every other file becomes `raw.origin.blob_mismatch`.
  This is latent: only adprov-v1 has a listing pin, and it has no account-shaped label. Fix: take the snapshot first.
  Owner: regen-items (item 108).

**PR-12. Other code, class 0:**
- **#19:** the item-108 account-path lint is vacuous under dtap-bench@2. `covered()` treats any pattern match as cover and
  ignores the rule's `labels` allowlist, while D-607's `host_account_token` matches any segment. Owner: regen-items, with
  the bug pass.
- **#21:** controlarena-persistent v3 redacts to `/Users/account-<12 hex>`, which `release_scan`'s `REDACTION_LABEL`
  (`acct-<12 hex>`) does not exempt. It is masked today because D-344 withholds every execution. Owner: 10p.
- **#14:** `gui/tests/test_viewer.py:244` still expects `aer/0.1`. The integration gate does not run the GUI suite.
  Owner: GUI.
- **#17:** `tools/analysis2/exam2_schema.py:73` hard-codes `aer-0.1.schema.json`. Owner: pre-check.
- **#16:** the datasheet and deposit metadata ignore the D-221 sealed members (context origins, pinned objects,
  `context_skipped`). Fix before any corpus/0.2 deposit. Owner: deferrals.
- **P-3:** a refused recompute's summary has `refusal: null` with `outcome: refused`. Owner: regen plan / cli-robustness.
- **P-4:** `recompute --out` that ends in `failures` leaves `NEW.partial` on disk. Check that this is intended.

**PR-13. Documentation and predictions:**
- **#11, #15, #25 (stale apv claims):** item 20's prediction, C.21 item 4 and the aer-0.2 `design.md` still say "apv
  0.1.0 unchanged". On the combined tree PROV is apv 0.2.0 (items 85/86), corpus/0.2 records `ontology.version` 0.2.0, and
  views/compat moved by items 72/77. Owner: deferrals.
- **#20, #26 (datasheet rows):** `corpora/datasheet-statements.toml:53,67` still cite rows 17/18 after the pc01 renumber.
  Row 17 is now claimed by two statements, including the D-609 withholding disclosure. Should be 18/19. Owner: artefact.
- **#22, #30 (stale status lines):**
  - D-210..D-212 still say "awaiting approval";
  - regen-batch still has "D-525 NOT BUILT YET";
  - qwencode/openhands profile comments, the registry caveat and the D_adapters bullet still say "waits for D-530 /
    corpus/0.2". Update them when PR-1's seal test exists.
  - Owners: deferrals, cli-robustness, 10i.
- **#27:** regen-batch has no row for items 57-59 (core-B) or 114 and 149 (10m), although item 57 moves `corpus.json`
  counts and item 114 moves register rows. Owners: regen-items, with core-B and 10m.
- **#24 (PLAUSIBLE):** under the D-451 closures, `versions.py`, `raw/members.py` and the registry are hashed into stages
  that several predictions exclude. Suggest one combined-tree digest table per stage. Owner: regen plan.
- **#29 (PLAUSIBLE):** part C's routed adapter halves are not landed and item 20's capture section is still "planned":
  - the item 20 `capture_mapper.py` edits;
  - D-219's `degenerate_header` edits, which no regen item tracks.

  Owner: regen-items.
- **#31:** union-merge artefacts. Row 137 plus a blank line splits rows 33-41 out of the regen-batch table, and 18
  id-ledger lines are duplicated. Owner: workflow tools.
- **Proofs:**
  - BF-39's prediction omits `members.jsonl` `fn_digest` (PR-10).
  - Item 103's wording ("24 profiles with `verified_code = []`") also fires for per-execution unverified resolutions in
    the head corpus (1/24, 5/8). Consistent with "cite the resolved rule"; the wording only.

**Refuted (#28):** "D-601 widened the Inspect harness pointers, so D-349's proof is stale". Only the sentence "No other
profile declares redaction rules" is outdated; it is folded into PR-13's stale wording.

## Checked and found consistent

Each dimension's 'checked' list is in the workflow result (`~/.agentprov/review/pre-round/workflow-result.json`).
Highlights:

- **Merges:** every first-parent merge touching `adapters/runner/` was read with `git show --cc`. Only bd50124b (rd3),
  2080050a (d455) and 79103462 have real resolution hunks, and none lost or duplicated a hunk.
- **D-529 × RD-3, D-218, D-414, D-455, D-560:** consistent. CD-6 is registered once; sample counts add up; carved blobs
  are held only in pass 2; D-560 exclusions come before sampling; D-455 retrieval times are used on fetch, input and
  re-map.
- **D-610, D-525 drain and NF-36 in the import path:** the mark is written, carried and cleared as decided. Package,
  derive and recompute refuse it. The nested-label prefix rule holds. 50 targeted tests pass.
- **10i `locate()` move:**
  - `raw/store.py` is byte-identical base→int, and nothing imports the old location.
  - The expand digest moves only by D-451/BF-39 and CB-22, both documented.
- **D-451 scopes:** both writers build the stage digests from `stage_scopes`, and `test_stage_scopes` passes.
- **D-550 cache:** it keys on the whole package digest, and G2c-5 skips bypass it.
- **D-530 re-map:** derive, recompute and `verify --level rederive` take one context-tree path.
- **Redaction:** the item-108 holds × recompute re-map keep `select.redaction_pending`.

## Redaction and withholding proof

- **Scope:** one small scratch import per family at INT, through the queue.
  - **Real data, by import strategy:**
    - prune / release: kexin-xu-01, fragfuse, whistlebench, interbolt, environmentoptim, agentdyn·a, adprov-v1,
      openagentsafety;
    - any-glob / dev: controlarena zip-3-003, dtap, credleak-p15b, autogen, geminicli.
  - **Synthetic fixtures:** memo-ozdincer, redcode-exec-openhands, agentops, mcphunt, qwencode.
- **Data:** `~/.agentprov/review/pre-round/proofs-redact/` (`scan-*.json`, `plan-*.json`, job logs). The subagent could not
  write a summary file; the summary is reproduced here.
- **Shipping channels are clean.** Checked: AER, SEM, PROV, index, register, `corpus.json`, `derivation.json`, validation
  rows, `WITHHELD.json`, the sealed `DATASHEET.md`, `rules/` and `schemas/`.
  - No targeted workstation account appears, and no withheld-rule match appears in a released file.
  - Account-shaped strings left in derived records are model-authored or benchmark content (prompts, tool args, model
    `cmd`), which D-182 and D-604(2) keep.
- **Raw residue is by decision.** Account paths in released raw objects and `raw/origins.jsonl` ship under D-604(7) and
  D-510, with matching datasheet statements: whistlebench, openagentsafety, EnvironmentOptim, and dtap and credleak (raw
  only).
- **Withholding at seal:**
  - kexin: 2 objects;
  - fragfuse: 7;
  - whistlebench: 4;
  - interbolt PC-05: the 24 `run_manifest.json` objects, as decided.
  - For the archive parts the product's `plan_withholding` was checked, with a residual rescan of every file it would
    release, all clean:
    - controlarena: all 15 executions;
    - credleak: 96/180 executions;
    - autogen: the deposit zip;
    - geminicli: 275 objects and 1 execution.
  - Sealed `verify --level chain` is 0 everywhere sealing was possible.
- **Local channels are clean:** `--summary-json`, `--progress trace` JSONL (also with `--show-content`), `--log-file`,
  the control acknowledgement, the tier-4 cache entries of every scratch PROV document, spool and temp leftovers. The only
  personal path is the operator's own, in uv's `VIRTUAL_ENV` warning on stderr.
- **D-529 × holds:** units held as `select.redaction_pending` get no sample slot (`first`, `random` with two seeds).
- **Not exercised on real data:**
  - planned parts via the CLI (the status gate was left closed);
  - kexin local-path-model logs (the `l2_import` guard is stale);
  - sealing archive parts in scratch;
  - `withheld.unscanned` (no sampled archive triggered it; the `test_sec25_*` suites pass).
- **Tool findings** (pre-check tools, class 0, owner pre-check):
  - `l2_check.py --seal` cannot seal: its `CARD.md` has no front matter (H.9(5)), and its spec origin is wrong for a
    seeded git pin with covering pathspecs;
  - `l2_import.py --strategy prune` does not restrict the dtap recipe (66,026 of 133,851 candidates kept for a 5-label
    sample);
  - the kexin guard in `l2_import` still says the D-182 table is pending.
- **Observation:** agentdyn·a has no redaction table. Three named accounts sit in tool args, tool `error` and text, in
  raw and AER alike. The AgentDyn owner should confirm they are fictional suite content.
- **Scratch:** about 5.7 GB is left under `~/.agentprov/migration-work/precheck/pre-round-review/`, nothing deleted,
  including a stopped dtap prune run of 895 MB. Re-map proof corpora are alongside.
