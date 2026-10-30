# Suite performance: baseline (D-400)

Measured 2026-10-14 by the suite-perf session. Raw timings stay in the session's scratchpad; nothing here names a test's
data.

## Run

| | |
|---|---|
| Commit | `c4fd0dc2` (origin/main at the start), a clean detached worktree; nothing of this branch |
| Machine | M2 Max, 12 cores, 32 GB, macOS |
| Command | `pytest --durations=0 -p no:randomly -p no:cacheprovider --hypothesis-show-statistics` (one process) plus a measurement-only plugin (per-test wall, process CPU, child CPU via `RUSAGE_CHILDREN`, spawns by kind, `time.sleep`) |
| Environment | `PYTHONDONTWRITEBYTECODE=1` (set by the Claude desktop app for session processes), so no bytecode cache |
| Load | **Contended.** 1-minute load average 47–56 at the start, peaking at 117, 20 at the end; up to five other full suites ran at the same time |
| Result | 6,911 passed, 128 skipped, 3 xfailed (7,042 collected) |
| Wall | **55 min 10 s** (3,310.7 s) |
| CPU | 1,885 s user + 213 s system for the whole process tree; peak RSS 2.8 GB |

The wall time is contended. The CPU figures do not depend on the load, so they are the numbers to compare against.

## Where the time goes

Over the 7,042 tests, 3,243 s of wall time was spent inside the tests. The rest of the run, about 67 s, was collection
and startup.

| Class | Seconds | Share of in-test wall |
|---|---:|---:|
| CPU in the pytest process | 1,367 | 42 % |
| CPU in child processes (worker pools, CLI subprocesses, git, dot) | 691 | 21 % |
| `time.sleep` (polling in worker and progress tests) | 42 | 1 % |
| Neither: waiting for a CPU under the load, plus I/O | 1,263 | 39 % |

**Process spawns.** The run started 2,544 `git` processes, 484 `agentprov.worker` processes, 73 `python -m agentprov`
CLI subprocesses, 55 other Python processes, 11 multiprocessing spawns, and a handful of `gitleaks`, `uv`, `dot` and
`sandbox-exec`.

**Hypothesis.** 91 tests used `@given`: 65 s of wall time and 47 s of CPU.

**Collection alone.** 43 s wall / 18.7 s CPU without bytecode, against 21 s wall / 10.4 s CPU with it. The cost was
assertion rewriting of all 456 test modules, which `PYTHONDONTWRITEBYTECODE` stops pytest from caching. Under xdist
every worker pays the collection cost.

On top of that, `tests/adapters/inspect/test_item28.py` spends 5–16 s at import time building three 1 MiB strings with
a quadratic loop.

**Import times** (`python -X importtime`, cumulative):

| Module | Import time |
|---|---:|
| `agentprov.cli.main` | 0.62 s |
| `hypothesis` | 0.31 s |
| `rdflib` | 0.16 s |
| `jsonschema` | 0.13 s |
| `agentprov.prov.engine` | 0.13 s |
| `prov` | 0.02 s |

## Totals per directory

From the plugin: wall, process CPU, child CPU and spawns, all in seconds except tests and spawns.

| Directory | Tests | Wall | CPU | Child CPU | Spawns |
|---|---:|---:|---:|---:|---:|
| `tests/adapters` | 1552 | 1473.3 | 646.7 | 132.0 | 178 |
| `tests/security` | 1019 | 683.2 | 218.4 | 200.9 | 285 |
| `tests/unit` | 2793 | 366.8 | 149.4 | 85.3 | 992 |
| `tests/integration` | 49 | 235.1 | 13.4 | 141.6 | 182 |
| `tests/corpus` | 61 | 137.2 | 121.5 | 25.7 | 38 |
| `tests/cli` | 549 | 123.3 | 45.5 | 60.5 | 790 |
| `tests/migration` | 174 | 89.5 | 69.3 | 30.8 | 458 |
| `tests/golden` | 372 | 49.8 | 46.9 | 3.3 | 2 |
| `tests/repo` | 49 | 22.4 | 0.8 | 7.1 | 6 |
| `tests/prov` | 212 | 20.2 | 19.6 | 0.0 | 1 |
| `tests/fuzz` | 48 | 14.3 | 14.1 | 0.0 | 0 |
| `tests/property` | 27 | 13.0 | 13.0 | 0.0 | 0 |
| `tests/full_corpus` | 43 | 5.6 | 1.8 | 3.2 | 255 |
| `tests/boundary` | 55 | 4.0 | 2.7 | 0.3 | 1 |
| `tests/differential` | 12 | 3.0 | 2.9 | 0.0 | 0 |
| `tests/render` | 25 | 2.3 | 0.3 | 0.5 | 12 |

## Tests that cannot simply run concurrently

These findings came from a static scan and a review. The handling of each is in `decisions.md` and `results.md`.

- **Load-sensitive.**
  - rlimit, CPU and wall-timeout tests: `tests/security/test_worker_isolation.py`.
  - Host calibration: `tests/unit/test_host.py`.
  - Worker-pool behaviour: `tests/unit/io/test_workers*.py` and `tests/unit/test_progress.py`.
  - CPU and elapsed bounds measured through child rusage: `tests/security/test_expand_budget.py`.
  - Timing thresholds below 5 s in several security tests.
- **Own pools.**
  - Determinism checks at 3 and 4 workers: `test_sec22_derive_determinism.py`, `test_expand_determinism.py` and
    `unit/corpus/test_derive.py`.
  - An 8-process `ProcessPoolExecutor` in `adapters/inspect/test_survey.py`.
  - About 20 files that take the host-default pool size, `--jobs 0` = min(CPUs, 0.75 RAM / 4 GiB) = 6 workers here.
- **Global state.**
  - Per-process caches: `host._CACHE` and the calibration cache in `agentprov.io.workers`. A calibration that fails
    under load is cached as failed.
  - `del sys.modules["tarfile"]` in `tests/security/test_nested_tar.py`.
  - The live-backend session fixtures set `AGENTPROV_HOME` in `os.environ` for the rest of the session.
  - A bare-name `test_semantics` import that resolves differently depending on which conftests a subset loads.
- **Shared paths.**
  - Golden regeneration writes into the checkout, but only when `AGENTPROV_REGEN_*` is set.
  - The `test_new_family_no_core_change.py` tests read the live working tree (`git ls-files --others`).
- **Not found:** fixed ports (all servers bind port 0), `setrlimit` in the test process, or umask changes.

## Top 100 tests by wall time (contended)

| # | Wall s | CPU s | Child CPU s | Spawns | Test |
|---:|---:|---:|---:|---:|---|
| 1 | 173.01 | 37.86 | 46.56 | 5 | `tests/security/test_sec15_tamper_matrix.py::test_sec15_chain_checks_member_crc32_and_size_on_a_sealed_corpus_even_after_a_consistent_forgery` |
| 2 | 101.77 | 59.81 | 0.00 | 0 | `tests/adapters/inspect/test_catalogues.py::test_ext_inspect_matches_its_schema` |
| 3 | 77.52 | 45.57 | 0.00 | 0 | `tests/security/test_json_stream.py::test_a_document_above_max_json_bytes_streams_in_bounded_memory` |
| 4 | 63.50 | 16.71 | 0.00 | 0 | `tests/unit/corpus/test_derive.py::test_a_remap_from_the_stored_raw_gives_byte_identical_aer[inspect]` |
| 5 | 51.95 | 51.10 | 0.00 | 0 | `tests/corpus/test_tamper.py::test_member_object_altered` |
| 6 | 51.39 | 50.67 | 0.00 | 0 | `tests/corpus/test_tamper.py::test_member_crc32_disagreeing_with_members_jsonl` |
| 7 | 50.52 | 15.55 | 0.00 | 0 | `tests/adapters/dtap/test_mapper.py::test_every_fixture_seals_validates_and_derives` |
| 8 | 46.43 | 7.52 | 0.00 | 0 | `tests/adapters/agentdojo/test_phase10d_sources.py::test_real_fixtures_map_validate_cite_only_twins_and_keep_their_aer_bytes[glitch]` |
| 9 | 39.69 | 38.15 | 0.00 | 0 | `tests/adapters/credleak/test_mapper.py::test_every_fixture_run_seals_and_derives_valid_provenance` |
| 10 | 39.36 | 5.62 | 0.00 | 0 | `tests/adapters/agentdojo/test_phase10d_sources.py::test_real_fixtures_map_validate_cite_only_twins_and_keep_their_aer_bytes[kongminos]` |
| 11 | 32.71 | 7.58 | 0.00 | 0 | `tests/adapters/agentdojo/test_phase10d_sources.py::test_real_fixtures_map_validate_cite_only_twins_and_keep_their_aer_bytes[melon]` |
| 12 | 30.80 | 8.22 | 0.00 | 0 | `tests/adapters/agentdojo/test_phase10d_sources.py::test_real_fixtures_map_validate_cite_only_twins_and_keep_their_aer_bytes[mohameduk]` |
| 13 | 30.33 | 30.19 | 0.04 | 2 | `tests/migration/test_gate_d.py::test_golden_scope_reproduces_the_gate_d_test_through_the_cli` |
| 14 | 29.99 | 22.26 | 0.00 | 0 | `tests/adapters/test_code_verification.py::test_one_real_fixture_per_affected_profile_passes_sem_prov_and_tier4` |
| 15 | 28.79 | 0.71 | 17.02 | 8 | `tests/integration/test_run_live_autodojo.py::test_a_scripted_agentdyn_session_maps_and_its_end_state_is_not_reproducible` |
| 16 | 28.63 | 0.28 | 7.09 | 4 | `tests/integration/test_run_live_autodojo.py::test_a_forced_kill_leaves_a_parent_sealed_aborted_session` |
| 17 | 27.80 | 14.27 | 0.00 | 0 | `tests/unit/corpus/test_derive.py::test_a_remap_from_the_stored_raw_gives_byte_identical_aer[agentdojo]` |
| 18 | 27.75 | 4.49 | 16.44 | 15 | `tests/adapters/dtap/test_import.py::test_output_is_byte_identical_across_worker_counts` |
| 19 | 26.34 | 9.04 | 0.00 | 0 | `tests/adapters/agentdojo/test_phase10d_sources.py::test_real_fixtures_map_validate_cite_only_twins_and_keep_their_aer_bytes[interbolt]` |
| 20 | 26.09 | 6.51 | 0.97 | 1 | `tests/security/test_expand_budget.py::test_sec07_more_than_256_mib_of_selected_members_expand_within_budget_and_without_holding_the_container` |
| 21 | 25.70 | 0.43 | 11.00 | 4 | `tests/integration/test_run_live_autodojo.py::test_a_scripted_v2_suite_session_maps[banking_v2_0]` |
| 22 | 25.52 | 15.81 | 0.00 | 0 | `tests/unit/corpus/test_derive.py::test_a_differing_member_row_fails_the_remap` |
| 23 | 24.56 | 0.27 | 7.93 | 2 | `tests/integration/test_run_live_agentdojo.py::test_a_poisoned_capture_log_from_the_real_worker_never_reaches_the_corpus` |
| 24 | 24.18 | 17.74 | 0.00 | 0 | `tests/security/test_metadata_poisoning.py::test_sec21_hostile_metadata_values_never_reach_a_written_path` |
| 25 | 23.43 | 15.68 | 0.00 | 0 | `tests/adapters/test_code_verification.py::test_no_real_fixture_cites_a_d_rule_for_unverified_code` |
| 26 | 20.73 | 0.01 | 7.04 | 1 | `tests/repo/test_unicode_controls.py::test_sec13_the_tracked_tree_is_clean` |
| 27 | 19.89 | 0.97 | 22.53 | 34 | `tests/integration/test_run_live_autodojo.py::test_a_scripted_autodojo_cell_replays_a_verified_cache` |
| 28 | 19.85 | 4.40 | 0.00 | 0 | `tests/adapters/agentdojo/test_phase10d_sources.py::test_real_fixtures_map_validate_cite_only_twins_and_keep_their_aer_bytes[linyxus]` |
| 29 | 19.05 | 10.64 | 0.00 | 0 | `tests/unit/aer/test_schema_file.py::test_tricky_values_agree_one_level_down` |
| 30 | 18.86 | 13.78 | 0.00 | 0 | `tests/adapters/test_code_verification.py::test_released_adprov_transcripts_cite_no_rule_off_the_writers_code_path` |
| 31 | 18.85 | 17.64 | 0.00 | 0 | `tests/adapters/dtap/test_import.py::test_every_candidate_has_one_disposition_and_every_execution_validates` |
| 32 | 18.43 | 7.50 | 0.00 | 0 | `tests/adapters/agentdojo/test_reader.py::test_mutation_fuzzing_raises_only_typed_errors` |
| 33 | 18.39 | 3.01 | 17.03 | 16 | `tests/adapters/runner/test_import_pipeline.py::test_outputs_do_not_depend_on_workers_batches_or_in_process` |
| 34 | 17.80 | 6.13 | 8.46 | 7 | `tests/security/test_sec22_derive_determinism.py::test_sec22_derive_is_byte_identical_across_worker_counts_runs_and_in_process[agentdojo-aer]` |
| 35 | 17.71 | 13.86 | 0.00 | 0 | `tests/adapters/test_code_verification.py::test_a_causal_after_is_never_stronger_than_the_call_link_it_follows` |
| 36 | 17.06 | 5.43 | 0.00 | 0 | `tests/security/test_sec15_tamper_matrix.py::test_sec15_chain_detects_an_altered_member_object_on_a_sealed_corpus` |
| 37 | 16.95 | 4.90 | 0.00 | 0 | `tests/adapters/agentdojo/test_items_22_23.py::test_the_tracelogger_mapper_dispatches_drift_to_the_drift_build` |
| 38 | 16.73 | 1.02 | 11.52 | 7 | `tests/integration/test_run_live_agentdojo.py::test_a_scripted_run_seals_and_derives_valid_executions` |
| 39 | 16.54 | 16.32 | 0.00 | 0 | `tests/unit/test_tools_dtap_check.py::test_scan_of_the_imported_fixtures_is_clean` |
| 40 | 16.33 | 0.15 | 58.85 | 9 | `tests/adapters/inspect/test_survey.py::test_committed_log_derives_and_passes_tier4` |
| 41 | 16.33 | 3.80 | 14.81 | 14 | `tests/security/test_sec22_derive_determinism.py::test_sec22_recompute_is_byte_identical_across_worker_counts_runs_and_in_process[agentdojo-from-raw]` |
| 42 | 16.25 | 1.75 | 13.10 | 2 | `tests/security/test_sec22_derive_determinism.py::test_sec22_outputs_do_not_depend_on_the_process_or_its_hash_seed[recompute-agentdojo]` |
| 43 | 15.84 | 7.42 | 0.00 | 0 | `tests/adapters/agentdojo/test_drift.py::test_every_fixture_maps_and_validates_in_release_mode_with_pinned_digests` |
| 44 | 15.68 | 6.83 | 0.00 | 0 | `tests/adapters/agentdojo/test_rope.py::test_rope_fixtures_follow_k41_map_validate_and_keep_their_aer_bytes` |
| 45 | 15.55 | 2.43 | 0.00 | 0 | `tests/adapters/agentdojo/test_phase10d_sources.py::test_real_fixtures_map_validate_cite_only_twins_and_keep_their_aer_bytes[ceferisbarov]` |
| 46 | 15.54 | 0.25 | 15.51 | 6 | `tests/integration/test_backends_build_autodojo.py::test_build_and_offline_check` |
| 47 | 15.27 | 4.52 | 0.00 | 0 | `tests/adapters/agentdojo/test_agentdyn.py::test_fixtures_map_validate_and_keep_their_aer_bytes` |
| 48 | 13.44 | 4.87 | 0.00 | 0 | `tests/adapters/agentdojo/test_phase10d_sources.py::test_real_fixtures_map_validate_cite_only_twins_and_keep_their_aer_bytes[geryon]` |
| 49 | 13.36 | 0.76 | 9.62 | 2 | `tests/security/test_sec22_derive_determinism.py::test_sec22_outputs_do_not_depend_on_the_process_or_its_hash_seed[recompute-inspect]` |
| 50 | 13.28 | 1.50 | 8.43 | 9 | `tests/unit/corpus/test_derive.py::test_the_reuse_cache_gives_the_bytes_of_a_full_recompute[expand,aer]` |
| 51 | 13.15 | 9.36 | 0.00 | 0 | `tests/adapters/inspect/test_survey.py::test_mapping_is_deterministic` |
| 52 | 12.93 | 5.44 | 0.00 | 0 | `tests/adapters/agentdojo/test_phase10d_sources.py::test_real_fixtures_map_validate_cite_only_twins_and_keep_their_aer_bytes[tacit]` |
| 53 | 12.87 | 4.19 | 0.00 | 0 | `tests/adapters/agentdojo/test_phase10f_seagent.py::test_member_origins_seal_and_validate_in_release_mode_d156` |
| 54 | 12.60 | 12.56 | 0.00 | 0 | `tests/golden/test_gate_d.py::test_prov_with_the_assessment_bundle_is_deterministic_and_passes_tier_4[R08]` |
| 55 | 12.46 | 0.87 | 12.47 | 39 | `tests/cli/test_import_cmd.py::test_summary_and_tree_are_byte_identical_across_jobs` |
| 56 | 12.46 | 5.75 | 0.00 | 0 | `tests/adapters/agentdojo/test_phase10f_seagent.py::test_real_fixtures_map_validate_and_cite_only_twins` |
| 57 | 12.38 | 2.80 | 0.00 | 0 | `tests/adapters/agentdojo/test_drift.py::test_a_matching_mapping_hook_is_reported_not_skipped` |
| 58 | 11.55 | 0.38 | 2.59 | 2 | `tests/adapters/dtap/test_import.py::test_release_mode_import_validates` |
| 59 | 11.45 | 1.96 | 8.64 | 2 | `tests/security/test_sec22_derive_determinism.py::test_sec22_outputs_do_not_depend_on_the_process_or_its_hash_seed[derive-agentdojo-aer]` |
| 60 | 11.12 | 2.43 | 0.00 | 0 | `tests/adapters/agentdojo/test_phase10d_sources.py::test_real_fixtures_map_validate_cite_only_twins_and_keep_their_aer_bytes[craibench]` |
| 61 | 11.04 | 5.98 | 8.69 | 14 | `tests/migration/test_gates_ab.py::test_results_do_not_depend_on_the_worker_count_or_the_mode` |
| 62 | 10.66 | 2.15 | 8.98 | 7 | `tests/security/test_sec22_derive_determinism.py::test_sec22_recompute_is_byte_identical_across_worker_counts_runs_and_in_process[agentdojo-from-aer]` |
| 63 | 10.49 | 1.90 | 0.00 | 0 | `tests/adapters/agentdojo/test_phase10d_sources.py::test_real_fixtures_map_validate_cite_only_twins_and_keep_their_aer_bytes[shreeyavarma]` |
| 64 | 10.48 | 0.32 | 8.58 | 4 | `tests/integration/test_run_live_autodojo.py::test_a_scripted_v2_suite_session_maps[travel_v2_0]` |
| 65 | 10.41 | 2.49 | 8.86 | 8 | `tests/security/test_sec22_derive_determinism.py::test_sec22_recompute_dry_run_summaries_are_byte_identical_across_worker_counts[agentdojo]` |
| 66 | 9.92 | 1.51 | 7.76 | 11 | `tests/security/test_sec22_derive_determinism.py::test_sec22_recompute_is_byte_identical_across_worker_counts_runs_and_in_process[inspect-from-raw]` |
| 67 | 9.66 | 0.15 | 12.74 | 6 | `tests/integration/test_run_live_agentdojo.py::test_the_build_records_its_marker_and_passes_the_offline_check` |
| 68 | 9.37 | 3.24 | 2.50 | 3 | `tests/adapters/runner/test_ingest_formats_2.py::test_a_split_import_is_byte_identical_to_itself_and_recompute_and_rederive_replay_it` |
| 69 | 9.15 | 1.84 | 6.20 | 6 | `tests/unit/corpus/test_derive.py::test_outputs_do_not_depend_on_the_worker_count` |
| 70 | 8.82 | 2.95 | 0.00 | 0 | `tests/adapters/agentdojo/test_phase10d_sources.py::test_real_fixtures_annotate_under_suites_v2_citing_only_twins[melon]` |
| 71 | 8.59 | 8.08 | 0.00 | 0 | `tests/prov/test_tier4_golden.py::test_golden_derivation_passes_tier4[R08]` |
| 72 | 8.52 | 6.67 | 0.65 | 31 | `tests/cli/test_import_cmd.py::test_dry_run_writes_nothing_and_reports_the_real_counters` |
| 73 | 8.39 | 0.40 | 1.98 | 9 | `tests/integration/test_run_spawn.py::test_resume_skips_nothing_until_a_conclusive_attempt_and_counts_attempts_across_invocations` |
| 74 | 8.39 | 7.88 | 0.00 | 0 | `tests/adapters/credleak/test_artefacts.py::test_reserved_detectors_are_never_cited` |
| 75 | 8.13 | 5.78 | 0.00 | 0 | `tests/adapters/runner/test_import_pipeline.py::test_an_inspect_log_is_expanded_planned_and_mapped_per_sample` |
| 76 | 8.07 | 3.98 | 0.00 | 0 | `tests/adapters/agentdojo/test_semantics_reviewed.py::test_v2_annotates_every_golden_agentdojo_aer_exactly_as_v1` |
| 77 | 7.90 | 3.69 | 0.00 | 0 | `tests/adapters/agentdojo/test_semantics.py::test_cited_rules_exist_with_matching_classes` |
| 78 | 7.88 | 1.91 | 0.00 | 0 | `tests/adapters/agentdojo/test_phase10d_sources.py::test_real_fixtures_map_validate_cite_only_twins_and_keep_their_aer_bytes[bookkeeper]` |
| 79 | 7.86 | 0.87 | 2.43 | 2 | `tests/security/test_sec15_tamper_matrix.py::test_sec15_withheld_control_the_sealed_withheld_corpus_passes_release_mode` |
| 80 | 7.76 | 5.28 | 4.81 | 6 | `tests/migration/test_gate_e.py::test_gate_e_passes_on_the_golden_set` |
| 81 | 7.74 | 7.65 | 0.04 | 2 | `tests/migration/test_gate_e.py::test_the_report_bytes_are_stable_across_two_runs` |
| 82 | 7.70 | 0.62 | 7.02 | 2 | `tests/security/test_sec22_derive_determinism.py::test_sec22_outputs_do_not_depend_on_the_process_or_its_hash_seed[derive-inspect-aer]` |
| 83 | 7.68 | 1.88 | 5.07 | 7 | `tests/security/test_sec22_derive_determinism.py::test_sec22_recompute_dry_run_summaries_are_byte_identical_across_worker_counts[inspect]` |
| 84 | 7.58 | 0.08 | 3.58 | 1 | `tests/integration/test_run_live_agentdojo.py::test_dry_run_with_the_real_worker_expands_the_plan` |
| 85 | 7.53 | 5.36 | 4.34 | 6 | `tests/cli/test_migrate_cmd.py::test_gate_e_writes_the_semdiff_reports_and_prints_the_oracle_notice` |
| 86 | 7.50 | 4.98 | 0.00 | 0 | `tests/adapters/inspect/test_survey.py::test_every_sample_imports_seals_and_validates` |
| 87 | 7.38 | 2.33 | 0.00 | 0 | `tests/adapters/agentdojo/test_phase10d_sources.py::test_real_fixtures_map_validate_cite_only_twins_and_keep_their_aer_bytes[yockcheng]` |
| 88 | 7.38 | 3.61 | 0.00 | 0 | `tests/security/test_sec19_cross_snapshot.py::test_sec19_the_same_bytes_in_two_snapshot_corpora_are_one_execution_each_with_one_id_and_their_own_snapshot` |
| 89 | 7.06 | 4.52 | 0.00 | 0 | `tests/adapters/runner/test_deferrals_part_a.py::test_the_re_mapped_manifest_names_the_shipped_profile` |
| 90 | 6.95 | 1.83 | 0.00 | 0 | `tests/adapters/agentdojo/test_phase10d_sources.py::test_real_fixtures_map_validate_cite_only_twins_and_keep_their_aer_bytes[menelaus29]` |
| 91 | 6.90 | 5.23 | 0.00 | 0 | `tests/adapters/inspect/test_whistlebench.py::test_every_sample_imports_seals_and_validates_in_release_mode` |
| 92 | 6.89 | 2.75 | 0.00 | 0 | `tests/adapters/agentdojo/test_items_22_23.py::test_an_isolated_tool_output_keeps_its_tools_label_without_the_redaction_rule` |
| 93 | 6.84 | 0.40 | 8.62 | 21 | `tests/unit/raw/test_expand_determinism.py::test_one_and_three_workers_and_repeated_runs_are_identical` |
| 94 | 6.69 | 2.22 | 0.00 | 0 | `tests/adapters/agentdojo/test_drift.py::test_the_census_hooks_reproduce_the_fixture_counts` |
| 95 | 6.65 | 0.78 | 3.04 | 2 | `tests/security/test_sec19_cross_snapshot.py::test_sec19_a_sealed_corpus_records_the_collapse_in_its_index_register_origins_and_duplicates_summary` |
| 96 | 6.59 | 0.78 | 4.99 | 6 | `tests/adapters/credleak/test_runner_multi_execution.py::test_a_sealed_two_snapshot_corpus_of_multi_run_cells_verifies_and_withholds_the_planted_run` |
| 97 | 6.57 | 0.07 | 3.62 | 1 | `tests/integration/test_run_live_agentdojo.py::test_preflight_probe_through_the_real_worker` |
| 98 | 6.49 | 3.73 | 0.61 | 31 | `tests/cli/test_import_cmd.py::test_a_second_run_resumes_and_leaves_the_tree_unchanged` |
| 99 | 6.43 | 0.38 | 5.82 | 9 | `tests/adapters/credleak/test_runner_multi_execution.py::test_resume_after_a_crash_between_two_runs_maps_only_the_second` |
| 100 | 6.41 | 1.78 | 0.00 | 0 | `tests/adapters/agentdojo/test_phase10d_sources.py::test_real_fixtures_annotate_under_suites_v2_citing_only_twins[linyxus]` |
