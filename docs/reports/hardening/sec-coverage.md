# SEC-01…SEC-26 coverage audit (phase 12a, before new tests)

Date: 2026-10-11. Base: `main` @ `0b47d96`. Method: every row of G.10 (and the matching K.12.x bullets, K.5.6, K.11,
K.14, K.17) was split into clauses; for each clause the test bodies under `tests/`, `capture/tests/` and
`backends/*/tests/` were read to confirm that they assert the clause, not just a similar name. Nothing was run for the
audit. Fixture contents were not read (deny rule); fixture-dependent clauses are marked as such.

This file is the "before" picture. The tests added in phase 12a are listed in §4 and, once written, in §5 with their
names, so a reader can see which gaps were closed and which remain.

**Status vocabulary.** COVERED: a test asserts the clause. WEAKER: a test exists but asserts less than the row says
(the gap is named). MISSING: no test, source code exists. SOURCE-GAP: no test *and* no code emits the behaviour; a
source change (and a decision) comes first. 12b: needs phase-11 or phase-10b code (`verify` levels, `rederive`,
`package`, `purge`, `stats`, deposits, corpus dedupe across snapshots, the `dtap` reader). BACKEND: needs a backend
environment. DEFERRED: the spec itself defers it (AD-10 row cited). CI: a process control, proved by a CI job, not a
pytest.

## 1. Cross-cutting findings

1. **Traceability (K.16).** Only SEC-01…SEC-12 use the `test_sec<NN>_` prefix. No test function is named
   `test_sec13_`…`test_sec26_`, although many clauses of those rows are proved by unprefixed tests.
2. **Spec-named files that do not exist:** `tests/repo/` (whole directory), `tests/fuzz/` (whole directory),
   `tests/security/test_locator_traversal.py`, `test_untrusted_content.py`, `test_agent_channels.py`,
   `test_static_dangerous_calls.py`, `test_tamper.py`, `test_deposits.py`, `test_reordering.py`,
   `test_inband_claims.py`, `test_time_claims.py`, `test_identity_spoofing.py`, `test_metadata_poisoning.py`,
   `test_supply_chain.py`, `test_secrets.py`; `tests/cli/test_cli_output_safety.py`; `tests/unit/corpus/test_dedup.py`
   (the nearest is `test_dedup_index.py`); `tests/property/test_never_emit_props.py`;
   `backends/agentdojo/tests/test_hostile_worker.py`. (`backends/autodojo/pyproject.toml` already points to the missing
   `tests/security/test_supply_chain.py`.)
3. **CLI today:** `info validate import fetch run backends migrate render` (`cli/main.py`). No `inspect`, `stats`,
   `derive`, `recompute`, `verify`, `package`, `purge`; no `src/agentprov/release/` or `stats/`. Every clause that
   needs them is 12b.
4. **Defect found during the audit (fixed in 12a, byte-neutral):** `aer.locators.pointer_get` calls `int()` on an
   array-index token of any length. A token of more than 4,300 digits raises an untyped `ValueError` (CPython's
   integer-string limit), which escapes `LocatorResolver.resolve` and **crashes the tier-2 AER validator** when an
   `unk` or `evf` key of a hostile AER line points into a list (reproduced with the `aer_support` example records and
   `/rule/9…9`). Any AER read from a downloaded deposit is untrusted (G.1.3), so this is a T-19/T-01-class robustness
   bug. Valid AER never contains such a pointer, so the fix changes no byte of any corpus.
5. **Spec drift (the code is right, the G.10/K.12 text is stale):**
   - SEC-09 / K.12.1 say bidi names are *rejected*; G.3.6 and the code accept them as labels and always display them
     escaped (`test_sec09_bidi_and_tag_characters_are_labels_that_are_always_displayed_escaped`).
   - K.12.2 / SEC-04 name a `rejected_unsafe` register disposition; it was retired (D.2.8), the code writes
     `not_imported`.
   - K.12.5 / G.2 T-16 name `capture.chain.order/.gap/.duplicate/.truncated`; the verifier emits the 17 `cap.chain.*`
     codes of C.13.2 item 16 (reordered, removed and duplicated lines all give `cap.chain.seq_gap`; truncation gives
     `torn_tail` or `unsealed`).
   - SEC-18 says claimed times "never create `after` edges". The Inspect mapper deliberately emits `after {b: "time"}`
     edges from recorded intervals under `aer.time_order@1`, and `aprov.after@1` turns them into the `apv:afterTime`
     attribute only. The real invariant is: a claimed time yields no PROV *relation*, and an `after` edge only under the
     declared time-order rule.
   - SEC-03 and SEC-08 name files at other paths than the tests (§2).
   These are recorded here; the spec text is corrected in G.10/K.12 in this phase (small, append-only edits).
6. **Source gaps that need a decision before a test can pass:**
   - **SEC-18 `time.implausible`:** the code is in the register code table (`corpus/register.py:69`) but nothing
     emits it. Its only specified basis, `ext.agentdojo.committed_no_later_than`, needs the full-history AgentDojo
     fetch, which is blocked on the user's consent (U-07). Left as SOURCE-GAP.
   - **SEC-20 requested versus served model:** the capture mapper records `served_model` per call (`O:provider`) but
     never compares it with the requested model, so `identity_conflict` cannot fire for it (it fires only for backend
     and benchmark pin mismatches, `capture_mapper.py` ~l.1868–1883). Adding the comparison is an `agentdojo` adapter
     change; no live corpus exists yet, but it must be checked against the capture-fixture digests first. Proposed,
     not applied (§4.3).
   - **SEC-16 `aer.order.noncanonical`** (C.17, V28) is a corpus-tier re-map check and is not implemented; it belongs
     to the corpus validation tier (phase 11). A reordered sealed file is still caught by `aer.seal.digest`.
7. **Repository hygiene gap:** `.gitignore` has no `*.log` (only `docs/**/*.log`) and no `CLAUDE.local.md`, although
   K.17(1) and G.11 #22 assume both. Fixed in 12a (ignore patterns only; no tracked file is affected).
8. **CI gap:** the `dependencies` job (the spec's `supply-chain`) runs osv-scanner on the root `uv.lock` only; the
   three backend locks are not scanned, although K.14 and SEC-23 say "every lock". Fixed in 12a. No schedule trigger
   exists or is added (D-22). GitHub Actions has refused to start jobs since 2026-10-09 (billing), so no CI run
   evidence newer than that exists.

## 2. Row-by-row coverage

Paths are relative to the repository root; `sec/` abbreviates `tests/security/`.

### SEC-01 — strict JSON values (T-01)

| Clause | Status | Evidence | Gap |
|---|---|---|---|
| duplicate keys at every depth | COVERED | `sec/test_json_limits.py::test_sec01_duplicate_keys_at_every_depth`, `::test_sec01_duplicate_key_that_differs_only_by_escape_is_still_a_duplicate` | — |
| `NaN`/`Infinity` | COVERED | `::test_sec01_nonfinite_literals` | — |
| `1e400`, 10^6-digit integer (typed code before CPython's limit) | COVERED | `::test_sec01_overflowing_float_and_enormous_integer_have_typed_codes`, `::test_sec01_digit_cap_below_cpython_limit_so_the_typed_error_fires_first` | limit±1 probe only in `tests/unit/ingest/test_json_loader.py::test_integer_digit_cap_at_default` |
| BOM; invalid UTF-8; UTF-16/32; NUL | COVERED | `sec/test_encoding.py::test_sec01_utf8_bom_rejected_strict_and_stripped_with_a_finding_when_lenient`, `::test_sec01_invalid_utf8_gives_the_encoding_code_with_an_offset`, `::test_sec01_error_for_invalid_utf8_does_not_echo_bytes`, `::test_sec01_utf16_and_utf32_are_never_auto_detected`, `::test_sec01_nul_bytes` | — |
| escaped lone surrogate → finding plus `$utf16` | COVERED / WEAKER | finding: `::test_sec01_escaped_lone_surrogate_is_a_finding_and_the_code_units_are_recoverable`; `$utf16`: `tests/unit/aer/test_jcs.py::test_encode_escapes` | no loader-to-AER end-to-end case |
| hostile but valid values byte-identical | COVERED | `sec/test_encoding.py::test_sec01_valid_unusual_content_passes_byte_identically`, `sec/test_json_limits.py::test_sec01_hostile_but_valid_values_survive_byte_identically` | — |

### SEC-02 — depth (T-01, T-04)

| Clause | Status | Evidence | Gap |
|---|---|---|---|
| depth 257 and 100,000 → `ingest.json.depth`, never `RecursionError` | COVERED | `sec/test_json_limits.py::test_sec02_depth_over_the_cap_is_a_typed_error_never_recursionerror`, `::test_sec02_depth_257_and_the_200kb_file`, `::test_sec02_depth_cap_holds_with_a_tiny_recursion_limit`, `::test_sec02_unterminated_string_hiding_brackets_cannot_bypass_the_pre_scan`, `::test_sec02_quote_escape_patterns_do_not_make_the_prescan_quadratic` | limit−1 in `tests/unit/ingest/test_json_loader.py::test_depth_cap_at_default` |

### SEC-03 — JSONL framing (T-02)

| Clause | Status | Evidence | Gap |
|---|---|---|---|
| U+2028/U+0085 stay one line | COVERED | `sec/test_jsonl_framing.py::test_sec03_u2028_u0085_and_u2029_inside_a_record_stay_one_line` | — |
| CRLF, blank, NUL, BOM, missing final LF, over-long: distinct codes, locators, other lines mapped | COVERED | `::test_sec03_each_defect_has_its_own_distinct_code_and_locator`, `::test_sec03_bom_on_the_first_line_only`, `::test_sec03_a_line_made_only_of_whitespace_is_blank_not_a_record`, `::test_sec03_overlong_line_is_discarded_in_bounded_chunks_and_framing_resumes`, `::test_sec03_strict_numbers_apply_per_line` | — |
| bare CR | WEAKER | `tests/unit/ingest/test_jsonl_loader.py::test_bare_cr_between_tokens_is_whitespace_within_one_line` | not a SEC test; no bare CR inside a string |
| line cap limit±1 | WEAKER | `tests/unit/ingest/test_jsonl_loader.py::test_line_length_cap_probed_at_the_limit` | not under `tests/security` |
| Hypothesis fuzz `tests/fuzz/test_jsonl_fuzz.py` | WEAKER | `sec/test_ingest_fuzz.py::test_f1_mutated_jsonl` | wrong path; JSON-seed mutations only (no CRLF, BOM, NUL, split/merge, oversize line); no F-3 `fs_guard` |
| K.11.2 regression set `fixtures/synthetic/jsonl/` | not checked | — | fixture tree not read |

### SEC-04 — size caps before full reads (T-01, T-03)

| Clause | Status | Evidence | Gap |
|---|---|---|---|
| file and record caps before decode/parse | COVERED | `sec/test_json_limits.py::test_sec04_document_size_is_decided_before_decoding_or_parsing` (−1/0/+1), `::test_sec04_default_file_cap_rejects_64mib_plus_one_without_parsing`, `::test_sec04_record_cap` | — |
| line cap | WEAKER | see SEC-03 | — |
| member cap on the declared size | COVERED | `sec/test_archives.py::test_sec07_member_size_cap_on_declared_size_before_any_read`; ±1 in `tests/unit/ingest/test_archives.py::test_member_size_cap` | — |
| store cap; no bytes kept | COVERED | `tests/unit/raw/test_store.py::test_size_cap_accepts_up_to_the_limit`, `::test_size_cap_rejects_limit_plus_one_before_publishing_and_leaves_nothing`, `::test_declared_size_over_the_cap_refuses_without_reading`; `sec/test_raw_store.py::test_oversize_streams_are_cut_off_and_leave_nothing` | — |
| member violation → register row (stage `ingest`) | COVERED | `sec/test_raw_store_expand.py::test_rejected_members_leave_no_bytes_only_rows_and_size_digest_limit_details`; `tests/unit/corpus/test_register.py::test_from_event_builds_the_ingest_entry` | — |
| oversize loose input file → register row (`not_imported`), nothing stored | MISSING | — | `importer.py::_Pipeline._store` has the branch; no test drives it |

### SEC-05 — YAML and nested archives (T-04)

| Clause | Status | Evidence | Gap |
|---|---|---|---|
| aliases, self-reference, billion laughs rejected within budget, in-process | COVERED | `sec/test_yaml_bombs.py::test_sec05_alias_documents_are_rejected_in_process_within_budget`, `::test_sec05_the_billion_laughs_document_is_tiny` | — |
| … in a worker | WEAKER | `::test_sec05_alias_documents_are_rejected_in_a_fresh_interpreter` | a fresh `-I` interpreter, not a T1 `WorkerPool` job |
| … give marker status `ambiguous` | MISSING | — | only the exception is asserted |
| size cap, depth, tags, duplicates | COVERED | `::test_sec05_size_cap_probed_at_the_limit`, `::test_sec05_oversize_input_is_refused_before_it_is_parsed`, `::test_sec05_deep_nesting_is_a_bounded_yaml_error_not_a_recursion_crash`, `::test_sec05_duplicate_keys_and_unsafe_tags_are_refused`, `::test_sec05_wide_documents_within_the_cap_stay_fast` | — |
| nesting depth 3 → `ingest.archive.depth`; undeclared nested archive stored, not expanded | COVERED | `sec/test_archives.py::test_sec05_nested_archive_depth_three_is_never_opened`, `::test_sec05_an_undeclared_nested_archive_is_not_expanded`, `::test_sec05_a_nested_archive_bomb_is_bounded_by_the_member_and_ratio_gates`; `tests/unit/raw/test_members.py::test_a_container_beyond_max_archive_depth_is_stored_but_never_opened` | — |

### SEC-06 — decompression (T-05)

| Clause | Status | Evidence | Gap |
|---|---|---|---|
| gzip/bzip2/xz/zstd single stream stored inert, `ingest.stream.codec` | COVERED | `sec/test_decompression.py::test_sec06_a_single_stream_is_recognised_by_magic_and_never_decompressed`, `::test_sec06_a_gzip_bomb_as_a_single_stream_costs_nothing` | — |
| deflate and zstd member bombs, declared-size lies | COVERED | `::test_sec06_deflate_member_bomb_is_stopped_by_the_ratio_gate`, `::test_sec06_zstd_member_bomb_is_stopped_by_the_ratio_gate`, `::test_sec06_declared_size_lie_is_bounded_for_both_codecs`, `::test_sec06_zip_member_decompression_never_allocates_beyond_the_declared_size`, `::test_sec06_zstd_frame_with_an_oversized_window_is_rejected_with_the_memory_code`, `::test_sec06_truncated_compressed_member_is_a_typed_error`, `::test_sec06_corrupt_compressed_bytes_never_raise_untyped_exceptions` | ratio ±1 in `tests/unit/ingest/test_archives.py::test_ratio_boundary_uses_strictly_greater` |
| four-codec stream suite | DEFERRED | — | written when a stream codec is enabled (G.3.4; AD-10 row 16) |

### SEC-07 — ZIP (T-05, T-06)

| Clause | Status | Evidence (`sec/test_archives.py::`) | Gap |
|---|---|---|---|
| CD size check before `ZipFile()`; CD beyond the file; 200,000 entries; lying EOCD; ZIP64 | COVERED | `test_sec07_cd_over_the_default_limit_is_rejected_before_zipfile`, `test_sec07_cd_size_cap_probed_at_the_limit`, `test_sec07_cd_beyond_the_file_is_rejected_before_zipfile`, `test_sec07_200k_entries_with_realistic_names_are_rejected_before_zipfile`, `test_sec07_entries_over_max_members_with_short_names_are_rejected_after_open`, `test_sec07_lying_eocd_count_does_not_hide_extra_entries`, `test_sec07_member_count_cap`, `test_sec07_zip64_end_record_is_read_and_checked`, `test_sec07_inconsistent_zip64_record_is_a_format_error` | — |
| prefix, trailing data | COVERED | `test_sec07_prefix_polyglot_is_rejected`, `test_sec07_trailing_data_is_recorded_not_rejected`, `test_sec07_archive_comment_is_not_trailing_data` | — |
| ratio, member, total, count, container size | COVERED | `test_sec07_deflate_zip_bomb_is_stopped_by_the_ratio_before_any_decompression`, `test_sec07_ratio_is_not_applied_below_the_floor`, `test_sec07_declared_size_lie_cannot_inflate_the_allocation`, `test_sec07_file_size_cap_on_the_container` | ±1 probes mostly in `tests/unit/ingest/test_archives.py` |
| overlap (full, partial), encrypted, method, CRC | COVERED | `test_sec07_full_overlap_two_entries_one_local_header`, `test_sec07_partial_overlap_member_data_runs_into_the_next_entry`, `test_sec07_local_header_extra_field_length_is_counted_in_the_overlap_check`, `test_sec07_bad_local_header_signature_rejects_the_archive`, `test_sec07_encrypted_member_is_rejected_alone`, `test_sec07_methods_outside_the_allowed_set`, `test_sec07_allowed_methods_are_accepted`, `test_sec07_crc_mismatch_rejects_that_member_when_streamed`, `test_sec07_declared_size_smaller_than_the_data_stops_at_the_declared_size_and_fails_the_crc`, `test_sec07_declared_size_larger_than_the_data_is_a_size_mismatch` | — |
| whole-archive versus per-member dispositions | COVERED | `test_sec07_whole_archive_versus_per_member_dispositions` | — |
| `not_selected` rows | WEAKER | `test_sec07_not_selected_members_are_never_decompressed` | the `raw/members.jsonl` row is not asserted |
| more than 256 MiB of selected members ingested (`DATA` not against the `JSON` cap; R-40) | WEAKER | `test_sec07_many_selected_megabytes_beyond_a_small_job_cap_are_accepted_when_within_member_and_total_limits` | archive layer only; no worker test that DATA above `max_json_job_bytes` is accepted |
| `rederive` re-expands identically; `verify --level chain` detects a CRC mismatch | 12b | — | no `rederive` or `verify` command |
| tar refused | COVERED | `test_sec07_tar_is_refused_with_exit_5_and_never_opened` | obs-G1 tar cases kept for a future enablement |

### SEC-08 — traversal and confinement (T-07)

| Clause | Status | Evidence | Gap |
|---|---|---|---|
| traversal names are labels, rejected, never opened; nothing written | COVERED | `sec/test_archives.py::test_sec08_traversal_names_are_labels_that_are_rejected_and_never_opened`, `::test_sec08_nothing_is_written_when_selected_members_are_streamed`, `::test_sec08_member_to_json_never_exposes_the_raw_name`; `sec/test_raw_store_expand.py::test_hostile_names_never_become_paths_and_nothing_is_extracted` | `fs_guard` is local to `test_archives.py` |
| locators confined (`test_locator_traversal.py`) | WEAKER | `tests/unit/aer/test_locators.py::test_unresolvable_locators_fail`, `::test_pointer_helpers`, `::test_byte_range_with_slice_relative_pointer`, `::test_line_form_is_zero_based_and_lf_split` | no `..`, absolute, `~2`, huge or bool `line`/`bytes`, huge array index; code not asserted. **The huge-index case crashes** (§1 item 4) |
| every written path under the corpus root, sharded-id pattern | WEAKER | `tests/unit/corpus/test_layout.py::test_shard_is_the_first_hex_digits_of_sha256_of_the_id`, `::test_paths_follow_h12`; `tests/unit/corpus/test_writer.py::test_end_to_end_files_and_cross_references` | no walk of every written file after a hostile-input import |
| store object paths | COVERED | `sec/test_raw_store.py::test_untrusted_digest_strings_are_absent_and_never_reach_the_filesystem`, `::test_a_symlinked_object_is_never_followed`, `::test_a_symlinked_shard_directory_is_never_followed`; `tests/unit/raw/test_store.py::test_malformed_digests_are_absent_and_never_become_paths` | — |

### SEC-09 — names (T-08)

| Clause | Status | Evidence (`sec/test_names.py::`) | Gap |
|---|---|---|---|
| controls, ANSI, lone surrogates | COVERED | `test_sec09_every_c0_and_c1_control_is_rejected`, `test_sec09_ansi_sequences_are_rejected`, `test_sec09_lone_surrogates_are_rejected` | — |
| bidi | COVERED (as G.3.6 rules) | `test_sec09_bidi_and_tag_characters_are_labels_that_are_always_displayed_escaped` | G.10 wording stale (§1 item 5) |
| length before NFC, bytes not characters, 10 KB strings | COVERED | `test_sec09_length_is_checked_in_bytes_before_nfc`, `test_sec09_length_check_counts_bytes_not_characters`, `test_sec09_ten_kilobyte_and_hostile_strings_are_bounded_errors` | — |
| reserved names, trailing dots | COVERED | `test_sec09_reserved_device_names`, `test_sec09_windows_hostile_names`, `test_sec09_confusable_prefixes_of_reserved_names_are_fine` | — |
| NFC/NFD and case collisions; all colliding members rejected | COVERED | `test_sec09_nfc_nfd_and_case_collisions_share_a_key`; `sec/test_archives.py::test_sec07_duplicate_names_and_collisions_reject_every_colliding_member` | not at the `expand` level |

### SEC-10 — links and special files (T-09)

| Clause | Status | Evidence | Gap |
|---|---|---|---|
| zip symlink attribute | COVERED | `sec/test_archives.py::test_sec07_non_regular_unix_modes_are_rejected` | named `sec07` |
| git mode 120000 stored as data | COVERED | `sec/test_fetch_hardening.py::test_a_symlink_blob_is_data_and_never_resolved`; `tests/unit/raw/test_fetch.py::test_every_blob_is_read_with_its_sha1_recomputed_and_symlinks_are_data` | — |
| `--input` symlink in any component; swap after discovery; FIFO without hanging; hardlink refused unless allowed | COVERED | `sec/test_links_special_files.py::test_sec10_*` (12 tests, each under both the native and the forced verify mechanism) | `O_NOFOLLOW_ANY` itself is exercised only when the suite runs on macOS (maintainer's machine; AD-10 row 18) |
| hardlink acceptance recorded | MISSING | — | the `--allow-hardlinks` notice (`cli/import_.py`) is untested |

### SEC-11 — no execution of untrusted content (T-10)

| Clause | Status | Evidence | Gap |
|---|---|---|---|
| static scan (`eval`, `exec`, pickle, `marshal`, unsafe YAML, `shell=True`, extraction, `entry_points`, `load_dotenv`, `splitlines` in loaders) | WEAKER | `sec/test_ingest_static.py::test_sec11_no_dangerous_imports_calls_or_attributes`, `::test_sec11_yaml_is_imported_only_by_yamlsafe_and_only_load_is_called_with_the_strict_loader`, `::test_sec11_json_loads_is_called_only_by_the_strict_loader_and_never_on_bytes`, `::test_sec11_no_text_mode_open_and_no_extraction_vocabulary_in_ingest`; partial: `sec/test_raw_store.py::test_no_raw_store_module_imports_a_network_or_process_module`, `sec/test_fetch_hardening.py::test_fetch_uses_no_dangerous_calls_or_unsafe_helpers`, `tests/boundary/test_artefacts_boundary.py` | scans `ingest/` (and parts of `raw/`) only; nothing scans the rest of `src/agentprov`, `capture/src`, `backends/shared/src` |
| pydot `create`/`write_*` banned | 12b | `tests/render/test_render.py::test_pydot_is_imported_only_inside_functions_and_never_asked_to_spawn_graphviz` | render behaviour, not a ban |
| store objects 0444 without exec bits | COVERED | `sec/test_raw_store.py::test_published_objects_are_read_only_without_exec_bits`; `tests/unit/raw/test_store.py::test_put_stores_bytes_at_the_content_address_with_mode_0444` | — |
| sniffed pickle stays inert | MISSING | — | no test feeds pickle bytes through `import` |
| `artefact` content with image/HTML `media` stored, never decoded | MISSING | — | — |

### SEC-12 — display of untrusted content (T-11)

| Clause | Status | Evidence | Gap |
|---|---|---|---|
| `quote_untrusted`: Cc/Cf/Cs/Zl/Zp, fence, round trip | COVERED | `sec/test_quote_untrusted.py::test_sec12_*` (15 tests) | — |
| CLI output carries no raw control bytes | WEAKER | `tests/cli/test_cli_streams.py::test_untrusted_file_names_never_reach_the_terminal_raw`, `tests/cli/test_cli_render.py::test_hostile_content_never_reaches_the_terminal_and_is_data_in_the_dot`, `tests/cli/test_exit_codes.py::test_exit_70_internal_one_line_without_a_traceback` | no `import` + `validate` run over payload-bearing input (`test_untrusted_content.py`) |
| exception arguments escaped | COVERED | `tests/cli/test_exit_codes.py::test_exit_70_with_verbose_shows_frames_and_escapes_arguments`, `tests/cli/test_logging.py::test_exception_arguments_are_escaped_and_frames_appear_only_at_debug` | — |
| `inspect` without `--show-content` | 12b | (feedback sink: `tests/cli/test_feedback.py::test_content_is_never_shown_without_show_content`) | no `inspect` command |
| generated Markdown, datasheet section, `stats` | 12b | — | `release/`, `stats/` absent |
| `render` DOT and SVG | COVERED (12b re-check) | `tests/render/test_render.py::test_default_dot_has_no_data_derived_text_and_no_link_attributes`, `::test_show_content_dot_is_escaped_and_parses`, `::test_svg_has_no_script_and_no_data_derived_link`, … | `URL=`/`shapefile` asserted on DOT only; needs `dot` |

### SEC-13 — agent channels in the repository (T-11)

| Clause | Status | Evidence | Gap |
|---|---|---|---|
| no third-party agent-instruction files in fixtures | COVERED | `tests/golden/test_golden_index.py::test_the_fixture_tree_holds_no_agent_instruction_files_and_respects_the_size_caps` | skips when fixtures are absent |
| `.gitattributes` binary rule; `.ignore`/`.rgignore`; `.claude/settings.json` deny rules; `AGENTS.md` + `CLAUDE.md` | MISSING (state true) | — | the files are right; nothing asserts them |
| golden-helper output holds no fixture substring > 40 characters | COVERED | `tests/unit/testing/test_golden_helpers.py::test_describe_diff_never_prints_a_long_fixture_substring`, `::test_assertrepr_compare_ignores_non_strings_and_escapes_strings`, `::test_the_repo_conftest_installs_the_hook_for_a_real_failing_assert` | — |
| `tools/check_unicode.py` rejects each category, accepts exempt fixtures | MISSING | — | runs in CI and pre-commit, never under pytest |
| ruff `PLE2502` enabled | MISSING (state true) | — | — |
| K.17 hygiene (tracked corpora, `.env`, `*.log`, `CLAUDE.local.md`, > 1 MiB files, secret patterns) | MISSING | partial: the 1 MiB check in `test_golden_index.py` | `.gitignore` lacks `*.log` and `CLAUDE.local.md` (§1 item 7) |

### SEC-14 — live payload fidelity and hostile T2 worker (T-07, T-09, T-12, T-24)

| Clause | Status | Evidence | Gap |
|---|---|---|---|
| payload identical in wire, capture, native log | BACKEND | `backends/agentdojo/tests/test_live_capture.py::test_payload_fidelity_wire_capture_native` | no AutoDojo equivalent |
| … and in the AER | WEAKER | `tests/adapters/agentdojo/test_capture_mapper.py::test_attacked_cell_fixtures_and_attacker` | vector and actor asserted, not byte equality of the fixture content |
| worker sees only its T2 home; outside writes not ingested; `../x`/absolute rejected; symlinked/hardlinked staged file rejected; unreported file reported, not ingested; forged `identity`/`hello_ok` exit 3 | COVERED | `tests/integration/test_run_spawn.py::test_the_worker_environment_is_the_allowlist`, `::test_hostile_reports_are_rejected_with_their_ingest_code` (dotdot, absolute, symlink, hardlink), `::test_unreported_files_are_ignored_and_reported`, `::test_a_hello_identity_mismatch_exits_3_before_any_cell`, `::test_a_capture_identity_mismatch_aborts_the_campaign_with_exit_3`, `::test_a_tampered_environment_exits_3_and_runs_nothing` | fake worker; `backends/agentdojo/tests/test_hostile_worker.py` absent (BACKEND) |

### SEC-15 — tamper matrix and deposits (T-07, T-13, T-14, T-20, T-21)

| Clause | Status | Evidence | Gap |
|---|---|---|---|
| forged AER seal → `aer.seal.digest` | COVERED | `tests/unit/aer/test_seal.py::test_seal_count_and_digest_are_checked`, `::test_reader_rejects_tampered_and_malformed_files` | — |
| forged origin blob SHA-1 | COVERED | `tests/adapters/runner/test_import_pipeline.py::test_a_file_the_pin_does_not_vouch_for_is_registered_not_imported`; `tests/cli/test_import_cmd.py::test_a_listing_pin_that_does_not_match_registers_every_file` | — |
| store corruption detected | COVERED (store level) | `tests/unit/raw/test_store.py::test_verify_and_verify_on_read_detect_corruption`; `sec/test_raw_store.py::test_an_existing_digest_is_never_rewritten_even_when_its_content_is_wrong` | — |
| corpus tamper matrix, regenerated checksums vs root digest, `rederive` forgery, chain CRC; deposits (archive mode, symlinked object, `../` relpath, `rules.mismatch`, `rules.unavailable`) | 12b | — | needs `verify`, `rederive`, `package` |

### SEC-16 — reordering (T-16)

| Clause | Status | Evidence | Gap |
|---|---|---|---|
| capture reordered, deleted, duplicated, truncated | COVERED | `capture/tests/test_verify.py::test_reordered_lines`, `::test_removed_line`, `::test_duplicated_line`, `::test_torn_tail_mid_line`, `::test_torn_tail_missing_only_the_lf`, `::test_missing_session_end_is_unsealed_but_fully_verified`, `::test_log_of_one_event_is_unsealed` | codes differ from the spec text (§1 item 5) |
| capture inserted | WEAKER | `capture/tests/test_verify.py::test_session_start_and_instrumentation_only_at_their_place` | only misplaced `session.start`/`instrumentation`; no forged ordinary event |
| AER forward reference after a reorder | COVERED | `tests/unit/aer/test_refs.py::test_forward_reference_is_aer_ref_forward`, `::test_after_edges_reference_earlier_records_only` | — |
| AER lines swapped with references still backward → `aer.seal.digest` | MISSING | — | `aer.order.noncanonical` itself is a SOURCE-GAP (corpus tier, phase 11) |

### SEC-17 — in-band claims (T-13, T-20)

| Clause | Status | Evidence | Gap |
|---|---|---|---|
| embedded PROV yields no core PROV statement | MISSING | — | — |
| claimed `sha256`, producer versions yield no identity | WEAKER | `tests/adapters/adprov/test_mapping.py::test_layout_deviations_raise_issues`, `::test_converted_identity_is_not_split` | mismatch flagged; "never identity" not asserted |
| claims appear only as `O` data `by: source` | WEAKER | indirect through the C.16.2 vector (`tests/adapters/adprov/test_mapping.py::test_c16_2_vector_is_reproduced`) | — |
| `hadPrimarySource` only for `prov_primary ∈ {native, byte_derived}` | WEAKER | `tests/prov/test_tier4_golden.py::test_mutation_fires_its_finding` (validator side) | no engine test over the four `prov_primary` values |

### SEC-18 — claimed times (T-15)

| Clause | Status | Evidence | Gap |
|---|---|---|---|
| claimed times never create PROV dependencies | WEAKER | `tests/prov/test_tier4_golden.py::test_mutation_fires_its_finding[relation_time-…]`, `[time_without_aer-…]`, `[sentinel_time-…]` | validator side only; no engine property test (`test_never_emit_props.py` absent) |
| no `after` edges from claimed times | WEAKER | `tests/adapters/inspect/test_mapping_rows.py` (time edges cite `aer.time_order@1`) | wording drift (§1 item 5) |
| `time.implausible`, value unchanged | SOURCE-GAP | value-kept cases: `tests/adapters/agentdojo/test_v1_import.py` (naive timestamps kept with `unk` ambiguous) | nothing emits the code (§1 item 6) |

### SEC-19 — duplicates and ownership (T-17)

| Clause | Status | Evidence | Gap |
|---|---|---|---|
| same bytes at two origins → one execution, two origins | WEAKER | `tests/adapters/runner/test_import_pipeline.py::test_dispositions_degenerate_not_dialect_duplicate_and_excluded` | `n_origins` on the index row not asserted; cross-snapshot collapse is 12b |
| `select.owned_elsewhere` + `owner`, not imported twice | COVERED | `tests/adapters/runner/test_profile_selection.py::test_excluded_files_are_registered_with_their_code_and_owner`; `tests/adapters/agentdojo/test_profile_machinery.py::test_generic_import_and_lineage_tables_are_closed` | cross-corpus checks DEFERRED (AD-10 row 6) |

### SEC-20 — identity spoofing (T-18)

| Clause | Status | Evidence | Gap |
|---|---|---|---|
| requested versus served model → `identity_conflict`, neither overwritten | SOURCE-GAP | (`served_model` recorded: `tests/adapters/agentdojo/test_capture_mapper.py`) | no comparison in the mapper (§1 item 6) |
| directory versus `pipeline_name` | COVERED | `tests/adapters/agentdojo/test_rope.py::test_identity_from_the_directory_and_the_tag_conflict`, `tests/adapters/agentdojo/test_mapper.py::test_identity_from_the_directory_never_from_pipeline_name`, `tests/adapters/agentdojo/test_identity.py::test_model_and_defence_from_the_directory` | — |
| version claims | COVERED | `tests/adapters/agentdojo/test_v1_import.py::test_v1_k14_package_version_is_a_distribution_version_not_code` | — |
| capture-code commit claims | WEAKER | T0 aborts: `tests/integration/test_run_spawn.py::test_a_capture_identity_mismatch_aborts_the_campaign_with_exit_3`; `tests/adapters/agentdojo/test_autodojo_capture.py::test_profile_pins_must_match_the_observed_identity` | no offline mapper test for a claimed capture-code commit |

### SEC-21 — metadata poisoning (T-19)

| Clause | Status | Evidence | Gap |
|---|---|---|---|
| suite/task/pipeline/version with `/`, `..`, NUL, ANSI, 10 KB never alter paths or identity | MISSING | — | — |
| unknown tools fail closed in SEM | COVERED | `tests/adapters/agentdojo/test_semantics.py::test_unknown_tools_fail_closed`, `tests/prov/test_assessment_golden.py::test_unlabelled_requests_and_members_fail_closed` | — |
| undeclared `activity`/`artefact` `type`, `other` `subtype` rejected | COVERED / WEAKER | `tests/unit/aer/test_generic_kinds.py::test_undeclared_namespace_is_ext_undeclared_and_malformed_type_is_pattern`, `tests/unit/aer/test_records.py::test_enum_escape_needs_a_declared_subtype`, `::test_the_other_escape_on_the_remaining_enums` | every case uses `activity`; no `artefact` case; no NUL/ANSI/10 KB `type` |

### SEC-22 — worker isolation (T-01…T-06, T-26)

| Clause | Status | Evidence (`sec/test_worker_isolation.py::` unless noted) | Gap |
|---|---|---|---|
| CPU loop, memory hog, wall timeout, `EFBIG` with the pipe working, `RLIMIT_AS` | COVERED | `test_cpu_loop_is_killed_by_sigxcpu`, `test_memory_hog_is_killed_before_it_holds_its_allocation`, `test_wall_timeout_kills_the_process_group`, `test_file_writes_fail_with_efbig_while_the_pipe_still_works`, `test_address_space_limit_where_the_kernel_enforces_it` | — |
| audit hook blocks network and subprocess events | COVERED | `test_audit_hook_blocks_network_events_in_the_worker`, `test_audit_hook_blocks_subprocess_events_in_the_worker` | — |
| no secret in the worker environment; no `FORBIDDEN` module after a job | COVERED | `test_environment_is_scrubbed`, `test_no_forbidden_module_is_loaded_in_a_worker` | — |
| outputs identical across worker counts, runs and in-process | COVERED (import) | `tests/adapters/runner/test_import_pipeline.py::test_outputs_do_not_depend_on_workers_batches_or_in_process` | `derive`/`recompute` are 12b |
| a worker failure gives a degenerate AER and keeps raw bytes | MISSING | — | `importer.py::_Pipeline._job_failure` untested |

### SEC-23 — supply chain (T-21, T-22, T-23)

| Clause | Status | Evidence | Gap |
|---|---|---|---|
| each `uv.lock` passes `uv lock --check` | CI | `ci.yml` job `core`, step "Every lockfile is current" (five projects); local run 2026-10-11 passes | — |
| wheel-only except the allowlist; fixed `exclude-newer` | MISSING | (true by inspection: every registry package in the four locks has wheels; all locks carry `exclude-newer = 2026-10-07T00:00:00Z`) | — |
| no `entry_points` use | WEAKER | ingest and fetch scans only | — |
| registry factories `agentprov.`-namespaced | WEAKER | `resolve_factory` refuses other prefixes | refusal and full registry walk untested |
| profile files refused in release mode | MISSING | — | `load_profile_file(mode="release")` untested |
| osv-scanner in CI | CI (partial) | job `dependencies`: root `uv.lock` only | backend locks not scanned (§1 item 8) |
| no backend project depends on `agentprov` | COVERED | `tests/boundary/test_import_boundary.py::test_no_backend_lock_lists_the_core_package`, `::test_nothing_under_capture_or_backends_imports_agentprov` | — |

### SEC-24 — hardened fetch and references (T-20, T-24)

| Clause | Status | Evidence | Gap |
|---|---|---|---|
| no working tree; symlinks as data; gitlink not fetched; branch/tag refused; hook never runs | COVERED | `sec/test_fetch_hardening.py::test_no_working_tree_and_no_upstream_file_exists_outside_the_object_database`, `::test_a_symlink_blob_is_data_and_never_resolved`, `::test_a_gitlink_is_recorded_and_never_fetched`, `::test_a_branch_a_tag_or_an_abbreviated_commit_is_refused_before_any_work`, `::test_a_hook_in_the_source_never_runs` | — |
| blob SHA-1 checked | COVERED | `tests/unit/raw/test_fetch.py::test_a_tampered_blob_is_caught_by_the_sha1_check` | the hardening-file test does not tamper |
| redirects drop the token; no downgrade; host allowlist; token only for its host | COVERED | `sec/test_fetch_hardening.py::test_cross_host_redirects_drop_credentials_downgrades_and_unlisted_hosts_are_refused`, `::test_a_token_goes_only_to_the_declared_host_and_only_unredirected`; `tests/unit/raw/test_fetch.py::test_redirects_must_stay_on_https_and_the_allow_list` | — |
| reference matching no in-package origin → `raw.reference.unpinned_origin`, not fetched | COVERED | `tests/unit/raw/test_references.py::test_a_git_reference_must_match_repo_commit_and_path`, `::test_no_pins_means_unpinned`; `tests/cli/test_fetch_cmd.py::test_an_origin_that_matches_no_in_package_pin_is_never_contacted` | — |

### SEC-25 — secrets (T-25)

| Clause | Status | Evidence | Gap |
|---|---|---|---|
| sentinel absent from written files; header allowlist and denylist; scan failure → `errored`; staging re-scan quarantines | COVERED | `capture/tests/test_redact.py::test_sentinel_appears_in_no_written_file`, `::test_request_header_allowlist_keeps_only_allowlisted_values`, `::test_hard_denylist_names`, `::test_denylist_wins_over_every_allowlist_entry`, `::test_scan_failure_writes_nothing_and_the_session_ends_errored`; `tests/integration/test_run_spawn.py::test_a_secret_in_a_staged_file_quarantines_the_session`; `backends/agentdojo/tests/test_live_capture.py::test_secrets_are_absent_from_every_artefact` (BACKEND) | no single sweep over corpus, register, report and logs |
| `dotenv_values` only, `os.environ` unchanged; `.env` from `--env-file` or the repo root, never cwd | MISSING | — | `cli/run.py::_read_env_file` untested (`python-dotenv` is in the `live` extra) |
| T1/T2 environment allowlists | COVERED | `sec/test_worker_isolation.py::test_environment_is_scrubbed`; `tests/integration/test_run_spawn.py::test_the_worker_environment_is_the_allowlist`; `tests/cli/test_live_units.py::test_the_worker_environment_is_an_allowlist` | — |
| base-URL refusals; `--allow-custom-endpoint` | COVERED / WEAKER | `capture/tests/test_endpoints.py::test_validate_rejects`, `::test_check_base_url_host_must_match_unless_custom`; `tests/cli/test_live_units.py::test_real_agent_resolution_never_records_the_key` | the "recorded" notice with the flag is untested |
| home path and host name absent from non-content surfaces | COVERED | `capture/tests/test_redact.py::test_home_path_and_host_name_on_non_content_surfaces_only`; `tests/cli/test_cli_streams.py::test_home_and_host_are_redacted_on_non_content_surfaces` | — |
| `purge` tombstone | 12b | — | no `purge` |
| gitleaks over full history | CI | job `secrets` (`gitleaks/gitleaks-action@ff98106e…`, v2.3.9, `fetch-depth: 0`); `.gitleaks.toml`; pre-commit gitleaks v8.28.0 | no CI run since 2026-10-09 (billing) |

### SEC-26 — interpreter guard (T-26)

| Clause | Status | Evidence (`sec/test_interpreter_guard.py::` unless noted) | Gap |
|---|---|---|---|
| dev mode below 3.14.8 warns and records | COVERED | `test_dev_mode_below_floor_warns_and_returns_record`, `test_warning_is_not_a_user_warning`; `tests/unit/corpus/test_writer.py::test_dev_mode_advisory_is_kept_for_the_manifest_producer_block`; `tests/unit/raw/test_members.py::test_dev_mode_below_the_floor_warns_and_records_an_event_per_root` | `corpus.json` fields not asserted end to end |
| release mode refuses (exit 3) before any archive is opened | COVERED | `test_release_mode_below_floor_refuses`; `sec/test_archives.py::test_sec07_interpreter_guard_refuses_before_the_object_is_opened_in_release_mode`; `tests/unit/raw/test_members.py::test_release_mode_below_the_floor_refuses_before_any_object_is_opened` | — |
| `package` refuses an advisory manifest (exit 4) | WEAKER | `test_manifest_with_advisory_is_refused_with_exit_4` (function level) | `package` is 12b |
| at or above 3.14.8 silent; no override flag | COVERED | `test_at_or_above_floor_is_silent`, `test_manifest_without_advisory_is_accepted`, `test_no_override_flag_exists` | — |
| plain JSON/JSONL unaffected | MISSING | — | — |
| `requires-python = ">=3.14"`, `.python-version` 3.14 | MISSING (state true) | — | — |

## 3. Fuzz layer (K.11) before phase 12a

| Target (K.11.1) | Existing fuzz | Gap |
|---|---|---|
| tier-1 parsers (JSON, JSONL, zip, names, quote, YAML) | `sec/test_ingest_fuzz.py::test_f1_*` (F-1, F-5) | JSONL mutations are JSON-seed only; no F-3 |
| AgentDojo TraceLogger reader + mapper | `tests/adapters/agentdojo/test_reader.py::test_mutation_fuzzing_raises_only_typed_errors` | — |
| FooBench reader + mapper | `tests/adapters/foobench/test_fuzz.py` | extend, do not duplicate |
| adprov `transcript/v1` reader | none | — |
| Inspect `.eval` reader (and reference resolution) | none | — |
| capture-log reader and verifier | none | — |
| `expand` stage | none (unit tests only) | — |
| locator resolver | none | crashes on a huge array index (§1 item 4) |
| raw store, origins, members, references decoders | none | — |
| AER validator | `tests/property/test_validator_props.py` (schema agreement; arbitrary lines never raise) | no mutation of real sealed AERs; misses the pointer crash |
| `dtap` reader | — | 12b (phase 10b owns the reader) |

## 4. Phase 12a plan (tests that need no phase-11 code)

### 4.1 New and extended tests

- **SEC-03/K.11:** `tests/fuzz/test_jsonl_fuzz.py` (CRLF, BOM, NUL, split/merge, oversize lines, F-3); a bare-CR
  security test.
- **SEC-04:** an oversize loose file through `import_source` gives an `ingest` register row and stores nothing.
- **SEC-05:** an alias bomb inside tool content gives marker status `ambiguous`; YAML in a T1 worker job.
- **SEC-07:** DATA above `max_json_job_bytes` is accepted by the worker protocol (R-40); `not_selected` member rows.
- **SEC-08:** `tests/security/test_locator_traversal.py` (pointer and range forms, the huge-index regression).
- **SEC-09:** collisions at the `expand` level.
- **SEC-10:** the `--allow-hardlinks` notice.
- **SEC-11:** `tests/security/test_static_dangerous_calls.py` over all of `src/agentprov`, `capture/src` and
  `backends/shared/src`; inert pickle through `import`; `artefact` media never selects a parser.
- **SEC-12:** `tests/security/test_untrusted_content.py` (import + validate over payload-bearing FooBench input; no raw
  controls on the terminal; payload byte-identical in raw and AER).
- **SEC-13:** `tests/repo/test_repository_hygiene.py`, `tests/repo/test_unicode_controls.py`,
  `tests/security/test_agent_channels.py`.
- **SEC-16:** `tests/security/test_reordering.py` (swapped AER lines → `aer.seal.digest`; a forged ordinary capture
  event).
- **SEC-17:** `tests/security/test_inband_claims.py` (FooBench/adprov input carrying embedded PROV, a claimed sha256
  and producer strings; `prov_primary` over the four values).
- **SEC-18:** `tests/security/test_time_claims.py` and `tests/property/test_never_emit_props.py` (reversed and
  implausible claimed times create no PROV relation; values kept).
- **SEC-19:** the index row of a collapsed duplicate carries both origins.
- **SEC-21:** `tests/security/test_metadata_poisoning.py` (hostile suite/task/pipeline/version values; hostile generic
  `type`s for both kinds).
- **SEC-22:** a worker failure ends in a degenerate AER with the raw bytes kept.
- **SEC-23:** `tests/security/test_supply_chain.py` (locks: wheels, `exclude-newer`, no `rdf.plugins`; no
  `entry_points` in `src/`; registry factories namespaced and the refusal; profile files refused in release mode).
- **SEC-25:** `tests/security/test_secrets.py` (`.env` resolution and `os.environ` untouched, with a stub `dotenv`;
  `--allow-custom-endpoint` notice).
- **SEC-26:** packaging constants; plain JSON is unaffected below the floor.
- **K.11 fuzz suites** (`tests/fuzz/`): raw decoders, locator resolver, AER validator over mutated sealed AERs, and the
  adprov, Inspect and capture readers; the FooBench fuzz is extended in place.

### 4.2 Fixes in 12a (no corpus byte changes; each proved by the golden/digest gates)

- `aer.locators.pointer_get`: refuse an array-index token longer than any valid index before `int()` (§1 item 4).
- Escaping audit A4 items in scope: F-08 (`raw/members.py` glob selection), F-11 (profile regexes), F-12
  (`prov/serialise/time.py` `\d`, `io/atomic.py` `\d+` before `int()`), F-13 (TriG and the `tools/` path helper).
- `.gitignore`: `*.log`, `CLAUDE.local.md`.
- CI `dependencies`: scan all four locks.

### 4.3 Proposed, not applied (need the user's decision)

- **SEC-20 served-versus-requested model** in `adapters/agentdojo/capture_mapper.py`: a new `identity_conflict` when
  a call's `served_model` differs from the requested model. It would add an issue to live AERs with a mismatch; the
  capture fixtures must be checked first.
- **SEC-18 `time.implausible`:** blocked on U-07 (full-history fetch for `committed_no_later_than`).

### 4.4 Left for phase 12b

SEC-15 (tamper matrix, `verify` levels, `rederive`, deposits), SEC-19 cross-snapshot dedupe, SEC-12 render/`stats`/
datasheet/`inspect` cases, SEC-11 pydot ban, SEC-25 `purge`, SEC-26 `package`, SEC-22 `derive`/`recompute`
determinism, fuzzing of the `dtap` reader, and the final DoD sign-off.

**Status (2026-10-12):** every item is done. The test items were done by phase 12c (§5.6); the ingest, raw and worker
items and the DoD sign-off by phase 12b (§5.5, `dod-evidence.md`, `dod-signoff.md`).

## 5. Phase 12a results (2026-10-11)

New test files carry the `test_sec<NN>_` prefix (K.16). Local run of `tests/security tests/fuzz tests/repo
tests/property tests/boundary`: 744 passed, 2 skipped (host-dependent). Evidence for the DoD rows is in
`dod-evidence.md`.

### 5.1 Gaps closed

| Row | Was | Now proved by |
|---|---|---|
| SEC-03 | bare CR and line-cap probes only in unit tests; fuzz at the wrong path, JSON-seed only | `test_jsonl_framing.py::test_sec03_a_bare_cr_never_splits_a_record`, `::test_sec03_line_cap_probed_at_the_limit`; `tests/fuzz/test_jsonl_fuzz.py` (framing mutations, F-3) |
| SEC-04 | over-cap loose file untested | `test_import_controls.py::test_sec04_an_over_cap_loose_file_is_registered_and_keeps_no_bytes` (limit−1/limit/limit+1) |
| SEC-05 | `ambiguous` marker untested | `test_yaml_bombs.py::test_sec05_an_alias_bomb_in_tool_output_gives_marker_status_ambiguous_within_budget` |
| SEC-07 | R-40 (DATA beyond the JSON cap) untested | `test_worker_isolation.py::test_sec07_member_data_beyond_the_json_job_cap_is_accepted_and_the_total_cap_still_holds`; F-08: `test_selection_patterns.py` |
| SEC-08 | no locator traversal file; a huge index crashed | `test_locator_traversal.py` (pointer, range, line, label forms; the crash regression); `tests/fuzz/test_locator_fuzz.py` |
| SEC-11 | scan of `ingest/` only; pickle and media untested | `test_static_dangerous_calls.py` (all of `src/agentprov`, `capture/src`, `backends/shared/src`, reviewed allowlist, subprocess importers; pickle stored, never loaded; media never selects a parser) |
| SEC-12 | no payload-bearing pipeline test | `test_untrusted_content.py` (raw and AER byte identity; `validate` output free of controls and payload text) |
| SEC-13 | `tests/repo/` absent | `tests/repo/test_repository_hygiene.py`, `tests/repo/test_unicode_controls.py`; plus CI guards (no schedule, every lock scanned) |
| SEC-16 | AER swaps and forged capture events untested | `test_reordering.py` (incl. the stated self-consistent-forgery limit) |
| SEC-17 | no in-band-claims test | `test_inband_claims.py` |
| SEC-18 | validator-side only | `test_time_claims.py`; `tests/property/test_never_emit_props.py` |
| SEC-19 | `n_origins` unasserted | `test_import_controls.py::test_sec19_the_same_bytes_at_two_paths_are_one_execution_with_two_origins` |
| SEC-21 | no poisoning test; no `artefact` type case | `test_metadata_poisoning.py` |
| SEC-22 | worker failure path untested | `test_import_controls.py::test_sec22_a_map_job_stopped_by_a_limit_is_registered_with_its_limit_code_and_keeps_the_raw_bytes` |
| SEC-23 | no supply-chain test | `test_supply_chain.py` |
| SEC-25 | `.env` resolution and the custom-endpoint notice untested | `test_secrets.py` |
| SEC-26 | packaging constants, plain JSON below the floor untested | `test_import_controls.py::test_sec26_*` |
| K.11 | fuzz only for ingest, TraceLogger and FooBench | `tests/fuzz/` (JSONL, raw decoders and store, locators, AER validator, capture log and reader, adprov and Inspect readers, input-tree discovery); FooBench fuzz extended in place |

### 5.2 Defects found and fixed (no AER/SEM/PROV byte of any corpus changes)

| Where | Defect | Found by | Fix |
|---|---|---|---|
| `aer/locators.py` `pointer_get` | a 4,301+ digit array index raised `ValueError` (CPython's int-string limit), crashing `LocatorResolver` and the tier-2 validator | audit (§1 item 4) | length guard before `int()` |
| `aer/locators.py` `pointer_get` | a non-string pointer (`src[].o`) raised `AttributeError` | `tests/fuzz/test_aer_validator_fuzz.py` | non-strings never resolve |
| `aer/validate.py` | a scalar where a list belongs (`rule`, `parts`, `input`, `inputs`, `after`, seal issue `ids`), an unhashable `unk` reason or accounting scope raised `TypeError` | the validator fuzz (ci and thorough budgets) | `_as_list`, `_hashable`; `tests/security/test_validator_robustness.py` (27 of 49 cases fail without the fix) |
| `adapters/runner/importer.py` `_seal` | a map job stopped by a worker limit lost its `worker.limit.*` register row when the degenerate AER could not be sealed | `test_import_controls.py` SEC-22 | the extra rows are registered on that path too (register rows only, only for a stopped job) |
| `io/atomic.py` | `.tmp-<pid>` names with non-ASCII or 4,301+ digits, or a pid beyond the OS range (also in a lock file), raised `ValueError`/`OverflowError` | escaping audit F-12, then probing | ASCII, at most 19 digits, `\Z`; a pid beyond the OS range counts as alive (fail safe) |
| `prov/serialise/time.py` | `\d` accepted every Unicode digit at the regex stage | escaping audit F-12 | `re.ASCII`; output-identical (all 15,750 single-digit substitutions with the 750 non-ASCII Nd digits already gave `None`) |

Proof of byte neutrality: `tests/golden`, `tests/prov`, `tests/unit`, `tests/adapters` and `tests/property` pass
(3,341 tests; `prov_digests.json` and `gate_d_digests.json` unchanged). The stage code digests in `derivation.json`
move with any `src/` change, as for every earlier code change; no file in `EXPAND_MODULES` was touched, so no
`members.jsonl` `fn_digest` changes.

### 5.3 Recorded, not fixed (decision or another phase needed)

- **F-08 compiler hardening** (refuse multi-`*` segments in `raw.members.Selection`): changes the `expand` stage's
  `fn_digest`, so it waits; the shipped patterns are pinned linear by test (regen-batch note).
- **A degenerate header that cannot name its task cannot be sealed** (`task.task_id` is required in `aer/0.1` with no
  `unk` escape): the AgentDojo known follow-up, now also shown for adprov by the reader fuzz. The pipeline registers
  `map.adapter_defect` and keeps the bytes. Fixing it needs `aer/0.2` or a mapper fallback to the label's task id.
- **Lone surrogates** end in `adapter_defect` for adprov too: F-01 / D-23, already in the regeneration batch.
- **SEC-20 served versus requested model**, **SEC-18 `time.implausible`**, **SEC-16 `aer.order.noncanonical`**: §1
  item 6.
- **F-13 TriG**: nothing writes TriG to disk or a terminal in this build (the tier-4 round trip is in memory); the
  escaping of control characters in TriG literals becomes a requirement of phase 11's `derive --trig`. The `tools/`
  path-helper half of F-13 is already fixed on `main` (`d3a6e13`).
- **SEC-05 "in a worker"**: no YAML job kind exists; the fresh-interpreter test stands (WEAKER).
- **SEC-14 AER payload leg, SEC-10 hardlink notice, SEC-20 capture-code commit claim, SEC-09 expand-level
  collisions**: small, still open.
- **SEM validator and reader fuzzing**: SEM documents from a deposit are untrusted too; not in the 12a scope.

### 5.4 Spec drift corrected in this phase

G.10 / K.12 wording for SEC-09 (bidi names are labels), SEC-04 (`not_imported`, not `rejected_unsafe`), SEC-16
(the `cap.chain.*` codes), SEC-18 (`after` edges only under the time-order rule) and the test-file paths of SEC-03 and
SEC-08 (G.10 note added in this phase).

## 5.5 Phase 12b results (2026-10-12; branch `phase-12b`; D-53–D-61)

Source changes in `ingest/`, `raw/`, `io/workers.py` and `tools/seed_git_cache.py`, each with tests. None changes an
AER, SEM or PROV byte (golden and gate-D digests unchanged; the full suite passes). D-56–D-59 change `EXPAND_MODULES`
files, so they form the `expand` bundle of `docs/reports/analysis/regen-batch.md` (user decision: one merge unit; only
the `expand` `fn_digest` moves; no stored member row changes).

| Row / item | Change | Proved by |
|---|---|---|
| SEC-24 / D.16.18 item 13 | Hugging Face dataset git pins (`huggingface.co/datasets/<owner>/<name>`), own cache namespace (D-53) | `tests/unit/raw/test_fetch.py` (local bare repository, no network), `tests/cli/test_fetch_cmd.py::test_every_shipped_profile_pin_loads_for_the_references_mode` |
| SEC-24 (routing R2) | `GIT_NO_LAZY_FETCH=1` on every Fetcher git call; absent blobs (`ls-tree` size `BAD`) refused `raw.fetch.blob_absent` (D-54) | `test_fetch.py` partial-clone tests with controls (the lazy fetch from a local upstream was reproduced without the guard), `tests/unit/raw/test_seed_git_cache.py` |
| SEC-22 / D.16.18 item 14 | Declared, bounded memory cap per job kind: `prov` 4 GiB, every cap in [64 MiB, 16 GiB], worker count from the largest cap (D-55, user decisions) | `tests/unit/io/test_workers.py` cap tests, `tests/security/test_worker_isolation.py::test_sec22_a_job_kind_with_a_declared_cap_runs_past_the_default_cap_and_is_still_bounded`; measurements `prov-rss.md` |
| SEC-09 (D-91) | `:` is a label character inside a member component; drive forms refused in every component; one info finding `ingest.name.colon` (D-56) | `tests/security/test_names.py::test_sec09_*colon*`, `::test_sec09_a_drive_form_*`, `test_raw_store_expand.py::test_sec09_colon_labels_*` |
| SEC-05/06/07/08/09/10 (D-90) | A gzip tar nested in a zip, read by AgentPROV's own header parser (no `tarfile`; obs-G1 closed by construction) (D-57, user-approved) | `tests/security/test_nested_tar.py` (41 cases, among them the 256 MiB long-name header in O(chunk) memory), `test_raw_store_expand.py::test_sec07_a_tar_gz_member_of_a_zip_*`, `tests/fuzz/test_tar_fuzz.py` |
| SEC-07 (D-47 item 2) | Exact obs-G8 reproduction | `test_archives.py::test_sec07_obs_g8_exact_reproduction_*`, `test_raw_store_expand.py::test_sec07_the_obs_g8_archive_*` |
| SEC-07 / HL.R7 (D-47 item 3) | Streaming `expand`: the container is opened by digest, hashed in chunks and read through the handle (D-58) | `test_workers.py::test_open_input_*`, `tests/security/test_expand_budget.py` (peak below the container size); 505 → 134 MiB, `expand-calibration.md` |
| SEC-07 / F-08 | A selection-pattern segment holds at most two `*` (D-59) | `test_selection_patterns.py::test_sec07_a_segment_with_more_than_two_wildcards_is_refused` |
| SEC-07 (D-47 item 1; G.11.3 Q13) | Expand-job budgets calibrated on > 256 MiB of selected members, values kept (D-60) | `test_expand_budget.py` (seeded archive generated at test time), `expand-calibration.md` (also the cached survey `artifact.zip`) |
| SEC-25 / F-12C-05 (D-46 open item) | Tombstoned digests blocked at ingest: the raw store never publishes one; the fetch cache never downloads one (D-61) | `tests/security/test_sec25_purge.py::test_sec25_a_reimport_never_stores_a_tombstoned_object_again` (12c's strict xfail, now a pass), `tests/unit/raw/test_store.py` tombstone tests, `test_fetch.py::test_a_purged_*` |
| Q.16 re-run | Two gitleaks false positives (execution ids containing "api"/"key" in DTap check data) allowed by an anchored entry | `tests/repo/test_repository_hygiene.py::test_the_execution_id_allowlist_entry_matches_only_a_whole_execution_id`; re-run: no leaks |
| (own test) | A load-sensitive worker test (failed on `origin/main` too at load ~57) | `test_worker_isolation.py::test_a_limit_event_replaces_the_worker_and_the_next_job_runs` |

**Routed** (`routing-12b.md`): R12b-1 the per-run `prov`-cap flag and its record (user-approved, CLI and importer
owners); R12b-2 tier 4 parses PROV-JSON under the 64 MiB untrusted-input cap; R12b-3 the 991 MB PROV of DTap `pii-4`;
R12b-5 the importer never asks for level 2 (nested patterns); R12b-6 the importer should register a new tombstoned
candidate. R12b-4 (own) is done.

## 5.6 Phase 12c results, merged (2026-10-12; merged into `main` at `bc6b113`; D-63–D-69)

Tests only, no `src/` change. The full record, with every check and node id, is
`docs/reports/hardening/sec-coverage-12c.md`; this section carries its summary into the coverage report.

| Area (rows of §4.4) | Test file(s) | Checks | Status |
|---|---|---|---|
| SEC-15 tamper matrix and deposits | `test_sec15_tamper_matrix.py`, `test_sec15_deposits.py` | 22 | COVERED, except F-12C-01 |
| SEC-19 duplicates across and within snapshots | `test_sec19_cross_snapshot.py` | 9 | COVERED, except F-12C-02; in-corpus cross-snapshot collapse DEFERRED by D-35 |
| SEC-12 display surfaces (`stats`, `inspect`, datasheet, `verify`) | `test_sec12_display_surfaces.py` | 13 | COVERED, except F-12C-03, F-12C-04 |
| SEC-11 pydot ban | `test_sec11_pydot_ban.py` | 5 | COVERED |
| SEC-25 `purge` | `test_sec25_purge.py` | 6 | COVERED (F-12C-05 fixed by phase 12b, D-61) |
| SEC-26 `package` and the deposit builder under the guard | `test_sec26_package.py` | 5 | COVERED (observation O-2) |
| SEC-22 `derive`/`recompute` determinism | `test_sec22_derive_determinism.py` | 6 | COVERED |
| `dtap` reader fuzzing | `tests/fuzz/test_dtap_reader_fuzz.py` | 9 | COVERED (observation O-3) |

**Findings** (each a strict xfail until fixed): F-12C-01 (Low; `corpus/verify.py`: a raw object behind a forged
`REFERENCES.json` entry passes `chain`), F-12C-02 (Low; `chain` does not reconcile rows' `snapshot_ids`/`n_origins`),
F-12C-03 (**Medium**; `corpus/datasheet.py`: a hostile model id reaches `DATASHEET.md` unescaped), F-12C-04 (Low;
`stats` labels keep a raw LF, Markdown output passes HTML): all routed to the orchestrator and still open. F-12C-05
(Medium): fixed (§5.5). F-12C-01 and F-12C-02 are self-consistent forgeries that the published root digest detects.

**Proposals and observations** (decisions, not fixes): P-1 orphan execution files pass `chain`; P-2 copied package
files (`schemas/**`, an added `WITHHELD.json` or `views/`) are not reconciled by `chain`; P-3 no release path after a
purge (sealing refuses a tombstoned corpus; nothing writes `WITHHELD.json`); O-2 (resolved by D-62: the spec wording is narrowed) `package` seal mode is not refused below
the 3.14.8 floor (it opens no archive; the deposit builder refuses); O-3 the `dtap`
`parse_path` accepts `.`/`..` facets (safe in the pipeline); and a linked `--corpus` root is followed by `verify`.
**Spec drift** recorded by 12c: H.7.2(1)/(3), the H.4.2 `agentdojo-upstream` row and MN N.2.2 `--snapshot` still describe
several snapshots in one corpus (D-35 and N.2.2(7) say one).

**Local run on the merged `phase-12b`** (2026-10-12; `main` @ `3c2503d` merged; macOS arm64, CPython 3.14.8, load
~35): `uv run pytest -q`: **6,063 passed, 107 skipped, 7 xfailed** (47 min); the 7 xfails are F-12C-01 to F-12C-04.
`ruff check .`, `mypy`, `tools/check_unicode.py` and `uv lock --check` (all five projects) pass.

