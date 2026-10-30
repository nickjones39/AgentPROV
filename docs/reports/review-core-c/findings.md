# Core review C: findings (CLI and host layer)

Branch `claude/review-fix-core-c-0b3d1c`, from `origin/main` 7f8f8cb3, on 2026-10-14. Orchestrator: "Phase 8 setup".

## Method

Five read-only reviewers ran in parallel, one per area:

| Area | Scope |
|---|---|
| C1a | `cli/main.py`, `common.py`, `checks.py`, `info.py`, `inspect.py`, `stats.py`, `verify.py`, `purge.py`, `deposit.py`, `package.py` |
| C1b | `cli/import_.py`, `fetch.py`, `derive.py`, `migrate.py`, `render.py`, `feedback.py` |
| C1c | `cli/run.py`, `cli/live/*` |
| C2 | `api.py`, `host.py`, `envinfo.py`, `presets.py`, `presets/`, `progress.py` |
| C3 | the `.env` code paths of the live CLI entry, the header allowlist, and the worker environment (code only; no `.env` was read) |

`cli/backends.py` was left out because the ultrareview covers it. The six items already assigned to cli-robustness
were excluded.

Each reviewer handed its findings to an independent verifier. The verifier tried to disprove each finding and rebuilt
its reproduction with its own scratch script. **A finding counts only if the verifier reproduced it.** Of 31 findings,
30 reproduced and 1 was refuted. All reproductions ran offline, with fake keys and stubbed fetchers or the test suite's
fake backend environment. There were no paid calls and no live capture.

Classes:
- class 0: fixed here, one commit per fix, each with a test that fails before the fix.
- class 1: a regen-batch proposal. None were needed.
- new behaviour: a D-id proposal, see [proposals.md](proposals.md).
- routed: the file belongs to an in-flight branch, so the fix belongs to that branch's owner.

## Summary

| Id | Sev | Sec | Location | Finding | Outcome |
|---|---|---|---|---|---|
| CC-1 | medium | yes | `cli/verify.py:219` | archive-mode `verify` prints the archived `corpus_id`/`corpus_version` raw (ESC/OSC, forged lines) | fixed 0e7cfa00 |
| CC-2 | medium | yes | `cli/live/campaign.py:315-318` | the T0 R-51 secret scan reads a second copy, not the stored bytes (`._*`/`.DS_Store` labels skipped; rewrite between reads) | fixed 2628d991 |
| CC-3 | low | yes | `cli/live/staging.py:124-127` | the worker-reported role decides the capture log: a mislabelled poisoned log bypasses the D-290 quarantine and the D.11.3 identity check | fixed a5da2052 |
| CC-4 | low | yes | `cli/derive.py:361-367` | `--show-diff` keeps LF and TAB from corpus data (forged output lines) | fixed ea31dfea |
| CC-5 | medium | | `cli/live/campaign.py:267` | after the first SIGINT, slots still in `--start-stagger` spawn workers and run full cells | fixed 8f3f25ef |
| CC-6 | low | | `cli/live/campaign.py:435-460` | a campaign-aborting error waits for every other in-flight cell to finish, then drops the results | fixed 1b2f3b1a |
| CC-7 | medium | | `cli/derive.py:157-163` | `--trig` accepts the final dir of the source or new corpus, and dirs inside other sealed corpora | fixed e3cd0fc3 |
| CC-8 | low | | `cli/fetch.py:178`, `cli/import_.py:352` | the fetch cache may be placed inside a sealed corpus, or inside the corpus `fetch --corpus` reads | fixed a75a5ec6 |
| CC-9 | low | | `cli/import_.py:626-630` | `import --dry-run` skips the output-tree guards: exit 0 where the real run exits 4 | fixed 3b692991 |
| CC-10 | low | | `cli/import_.py:373-414, 473-477` | `import --fetch` fetches twice: problems duplicated, network notice never emitted | fixed 59d527ca |
| CC-11 | low | | `cli/purge.py:144-151` | `purge --corpus` on a non-corpus directory exits 1, not 2 | fixed 5553860e |
| CC-12 | low | | `cli/live/envs.py:114-117` | a relative `$AGENTPROV_HOME` breaks every live run (exit 3) | fixed 7f74b4a0 |
| CC-13 | low | | `presets.py:439` | an unreadable `config.json` gives exit 70 (PermissionError) | fixed 50353ce5 |
| CC-14 | low | | `presets.py:371-373, 560` | oversized ints in `config.json` overflow the parameter count (exit 70) | fixed 8c71572d |
| CC-15 | low | | `cli/main.py:231` + int arg types | integer options of 2^53 and above give exit 70 (IntegerDomainError in the start log) | routed: cli-robustness 288db297; `checks.py` line open (RC-2) |
| CC-16 | low | | `api.py:14-17, 173` | stale docstring and refusal text (lineage precondition met; claims library present) | fixed a5356b8a; feature gaps D-540, D-541 |
| CC-17 | medium | | `api.py:284` | `api.check_claim` cannot pass `location`/`agent_executions_only`/`phrase`, so `agent_execution` and `coverage_claim` always fail | proposal D-540 (spec signature change) |
| CC-18 | low | | `cli/live/campaign.py:486-491`, `run.py:1211` | `live.quality` covers only the current invocation's sessions after a resume | proposal D-542 |
| CC-19 | medium | | `cli/package.py:247` | seal-mode `--release-date` not validated (impossible date sealed; malformed exits 70; `SOURCE_DATE_EPOCH` overflow) | routed: core review B (CB-18) |
| CC-20 | low | | `cli/package.py:228`, `cli/deposit.py:83` | the dry run skips the git-work-tree guard (G3): exit 0 versus 4 | routed: core review B |
| CC-21 | low | | `cli/package.py:265` | the summary's `corpus.root` holds the unredacted home path | routed: core review B |
| CC-22 | low | | `cli/main.py:161-168` | `--summary-json`/`--log-file` can write into a sealed corpus (G1) | routed: cli-robustness 288db297 (with `--progress-file`) |
| CC-23 | low | | `cli/checks.py:440` | `validate --report - --json` writes two JSON documents to stdout | held for RC-2 (after claude/rules-drift merges) |
| CC-24 | low | | `cli/run.py:884-885` | `run autodojo --dry-run --allow-network` fetches the pin | routed: cli-robustness 288db297 |
| CC-25 | low | | `cli/run.py:1014-1018` | `run --preflight-only --dry-run` spawns the probe and writes `$AGENTPROV_HOME` | routed: cli-robustness 288db297 |
| CC-26 | low | | `cli/run.py:1083-1092` | dry-run `cells_done_before` and exit code differ from the real run's | routed: cli-robustness 288db297 |
| CC-27 | low | | `cli/common.py:557-562` | the second signal `os._exit`s and leaves T2 workers running (orphans finish their cell) | routed: cli-robustness 288db297 |
| CC-28 | low | | `cli/run.py:679-688` | the consent text omits the done count and the `--max-attempts` bound, and lists no instrumentation items | routed: cli-robustness 288db297 (partial); items part: D-543 |
| CC-29 | low | yes | `cli/run.py:1036` | the hello/plan worker (including real-model `--dry-run`) gets the API key and no network block | routed: cli-robustness 288db297 |
| CC-30 | low | yes | `cli/run.py:656-659, 1102` | worker-supplied probe and plan values are echoed unescaped | routed: cli-robustness 288db297 |
| CC-31 | low | yes | `cli/common.py:142-154` | `safe_text` truncates before redacting, so a registered key across the cut leaks a prefix | routed: cli-robustness 288db297 |
| (refuted) | — | | `cli/import_.py:369` | `import --fetch --dry-run` without `--allow-network` exits 0 | specified by MN N.2.2 import item 2; not a defect |

Security findings in owned code (CC-1 to CC-4) were reported to the orchestrator when the verification wave
finished. Routed security findings: CC-29, CC-30 and CC-31.

## Details of the fixes made here

**CC-1** (N.1.13). The untrusted manifest of a lone `meta.zip` or deposit reached the root-digest line raw. A corpus id
like `"bad\x1b[2Jid\nFORGED LINE"` cleared the screen and printed a forged line. Both values now go through
`safe_text`. Test: `tests/cli/test_cli_streams.py::test_verify_archive_mode_escapes_the_archived_corpus_id_and_version`.

**CC-2** (G.6.4, R-51, N.1.11(2), T-25). `_ingest` stored the bytes `collect_session` read, then scanned a second,
independent read through `discover()`, which skips AppleDouble and `.DS_Store` names. A reported `._leak.json`
holding the key was stored, and quarantined stayed 0. A file rewritten between the two reads was scanned clean but
stored with the key. The collected bytes are now scanned too. Tests: fake-worker mode `junksecret`,
`tests/integration/test_run_spawn.py::test_a_secret_in_a_reported_file_the_directory_walk_skips_still_quarantines`.

**CC-3** (D-290, D.11.3, staging docstring). `SessionFiles.capture_log` selects by role, and the role was the
worker's report. A poisoned log reported as `supporting`, or two logs reported as `capture_log`, skipped the
quarantine and the identity check, while the log was still stored and mapped by label. The role now follows the label
(`_role_for`), as the worker assigns it. Test: fake mode `poisoned_mislabelled`,
`test_a_poisoned_capture_log_reported_with_another_role_is_still_quarantined`.

**CC-4** (N.1.13, N.2.4(5)). `escape_untrusted` keeps LF and TAB; `escape_untrusted_line` does not. Test:
`tests/unit/corpus/test_derive.py::test_show_diff_lines_from_corpus_data_cannot_start_a_new_output_line`.

**CC-5** (N.1.10(2)). `Campaign` now has a stop event. The stagger waits on it. An attempt that finds it set
creates nothing, and an attempt that was spawning when it was set resets its slot. Test:
`tests/cli/test_live_units.py::test_an_interrupt_stops_slots_still_in_their_start_stagger`.

**CC-6** (N.1.10(4)). On any exception other than KeyboardInterrupt, `run()` sets the stop event and kills every slot
before the executor shuts down. The killed sessions stay in staging and are not ledgered, so a resume re-attempts
them. After an identity mismatch, nothing from the untrusted environment is ingested. Test:
`test_a_campaign_aborting_error_kills_the_other_in_flight_workers`.

**CC-7** (G1, G2, G8). `_guard_trig` now covers each tree's final and `.partial` names and calls `assert_writable`.
With `--out`, it runs before any unit is processed. Test:
`test_trig_into_a_corpus_final_directory_or_a_sealed_corpus_is_refused`.

**CC-8** (G1, G2, N.2.2). A new `cli.fetch.guard_cache` is used by `fetch` and by `import`'s `_fetcher`. It refuses
a cache inside a sealed corpus, and for `fetch --corpus` a cache that overlaps that corpus (code
`raw.fetch.cache_in_corpus`, exit 4). It is read-only, so it applies to dry runs too. Tests stub the Fetcher, so a
missing guard cannot reach the network.

**CC-9** (N.1.6(5)). The dry run applies `CorpusWriter.open`'s read-only guards: an existing final directory,
`assert_writable`, and `assert_outside_git_work_tree` (fail closed, as the writer does). Test:
`test_a_dry_run_applies_the_output_tree_guards_of_the_real_run[sealed|inside_sealed|git_work_tree]`.

**CC-10** (N.1.11(1)). `_cached_tree` returns the result of the fetch it made, and the callers note its problems and
its network use once (`_note_fetch`). This changes summary notices only.

**CC-11** (N.1.3). The pre-flight maps `purge.corpus.not_working` to exit 2. The engine in `corpus/` is unchanged.

**CC-12** (M.4). `envs.agentprov_home` expands `~` and makes the path absolute.

**CC-13**. An `OSError` while reading `config.json` is now `PresetUsageError run.model.config` (exit 2).

**CC-14**. Architecture integers above `MAX_ARCHITECTURE_INT` (2^24) are left unknown, with a note, and
`shared_expert_intermediate_size`/`n_shared_experts` go through the same bound. An extreme config at the bound (every
field 2^24) runs a dry run with exit 0.

**CC-16**. The facade text now names the real gaps, which are proposals D-540 and D-541.

## Downstream effects

- **AER, SEM and PROV bytes, golden and compat gates, corpus manifests:** none. No fix touches mapping, provenance,
  the corpus format or recompute.
- **Live working manifests:**
  - CC-2 and CC-3 can turn a previously stored session into a quarantine. That is only possible for a hostile or
    buggy worker; the honest fake and real workers are unaffected.
  - CC-5 and CC-6 change which sessions are attempted after an interrupt or abort.
  - Only `test_only` live corpora exist, and nothing is regenerated.
- **Summaries:** CC-10 changes notices (one problem line instead of two, plus the network notice). CC-8, CC-9 and CC-11
  change exit codes on refused inputs.
- **Manuscript numbers:** none.

## Out-of-scope observations (routed)

- **RC-1, `corpus/writer.py` (corpus/ owner).** `CorpusWriter.open` runs `partial.mkdir` before
  `assert_outside_git_work_tree`, so a refused import leaves an empty `X.partial/` inside the git work tree.
  Reproduced by C1b and its verifier. Fix: run the git-work-tree check on the nearest existing ancestor before the
  `mkdir`.
- **RC-2, `cli/checks.py` (after claude/rules-drift merges).** The `bounded_int` adoption from CC-15 and CC-23.
- **Not reported as defects:**
  - Worker stderr files are scanned against every later session of a slot, so one leak quarantines all later
    sessions. This fails closed.
  - A failed probe leaves its staging directory without a register row.
  - A real-model `--dry-run` under `--containment sandbox-exec` puts the plan worker's cwd and HOME outside the
    profile's write allowance. This is untested here (no sandbox).
