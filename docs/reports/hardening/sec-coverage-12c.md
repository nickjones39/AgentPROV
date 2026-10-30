# SEC coverage added in phase 12c (tests that needed phase-11 code)

Branch `phase-12c` (own worktree), from `main` @ `33c1fcf`. Scope: `sec-coverage.md` §4.4, the rows marked 12b there
(SEC-15, SEC-19 cross-snapshot, SEC-12 display surfaces, SEC-11 pydot ban, SEC-25 `purge`, SEC-26 `package`, SEC-22
`derive`/`recompute` determinism, fuzzing of the `dtap` reader). Tests only: no file under `src/` was changed. Phase 12b's
final step merges this file into `sec-coverage.md` §5 and `dod-evidence.md`.

**Status vocabulary** (as in `sec-coverage.md`). COVERED: a test asserts the clause. WEAKER: a test exists but asserts
less than the row says (the gap is named). MISSING: no test. FINDING: a test exposes a defect; it is marked
`xfail(strict=True)` with the finding id and routed to the owner, never fixed here. DEFERRED: the build does not
provide the behaviour by a recorded decision (the decision is cited).

**Method.** Every corpus is built at test time under `tmp_path` (the sealed three-log test corpus `mini-mit` of
`tests/unit/release/release_support.py`, the sealed Inspect AgentHarm test corpus built by the SEC-15 slow fixture,
working corpora of `derive_support`, synthetic trees of `tests/security/import_harness.py`). Nothing under
`~/.agentprov` is read or written. New helper modules (not collected): `tests/security/corpus_harness.py` (paths,
`cli` and `sealed` fixtures, the `OpenSpy` audit hook) and `tests/security/sec15_support.py` (tamper devices).
`tests/security/conftest.py` is unchanged.

## Summary

| Area | New test file(s) | Rows | Findings |
|---|---|---|---|
| SEC-15 tamper matrix and deposits | `test_sec15_tamper_matrix.py`, `test_sec15_deposits.py` | 22 | F-12C-01 |
| SEC-19 duplicates across and within snapshots | `test_sec19_cross_snapshot.py` | 9 | F-12C-02 |
| SEC-12 display surfaces | `test_sec12_display_surfaces.py` | 13 | F-12C-03, F-12C-04 |
| SEC-11 pydot ban | `test_sec11_pydot_ban.py` | 5 | none |
| SEC-25 `purge` | `test_sec25_purge.py` | 6 | F-12C-05 |
| SEC-26 `package` refusals | `test_sec26_package.py` | 5 | none |
| SEC-22 `derive`/`recompute` determinism | `test_sec22_derive_determinism.py` | 6 | none |
| `dtap` reader fuzzing | `tests/fuzz/test_dtap_reader_fuzz.py` | 9 | none |

**Findings, by owner** (each an `xfail(strict=True)` test, so a fix turns it into an XPASS failure that forces the marker
to be removed):

| Id | Severity | Owner (route) | One line |
|---|---|---|---|
| F-12C-03 | Medium | orchestrator (`corpus/datasheet.py`) | a hostile model id reaches `DATASHEET.md` unescaped: raw controls, live HTML, a forged heading, an HTML comment hiding the rest |
| F-12C-05 | Medium | phase 12b (`raw/`, import pipeline; the D-46 item) | a re-import after a `purge` stores the purged credential again |
| F-12C-01 | Low | orchestrator (`corpus/verify.py`) | a raw object replaced by a forged `REFERENCES.json` entry passes `chain` silently, also in release mode |
| F-12C-02 | Low | orchestrator (`corpus/verify.py`) | `chain` does not reconcile rows' `snapshot_ids` and `n_origins` with the manifest and `raw/origins.jsonl` |
| F-12C-04 | Low | orchestrator (`stats/tables.py`, `stats/output.py`) | a `stats` label keeps a raw LF; Markdown output passes HTML |

F-12C-01 and F-12C-02 are self-consistent forgeries that the published root digest still detects (T-13 residual); they
matter because `chain` claims the reconciliation. No finding is in `adapters/dtap/`. Proposals P-1 to P-3 and
observations O-2, O-3 (and the linked-root note under SEC-15) need a decision, not a fix.

**Local run on the merged branch** (2026-10-12; `phase-12c` with `origin/main` @ `3a9957c` merged; macOS arm64,
CPython 3.14.8): `uv run pytest -q`: **5,934 passed, 107 skipped, 8 xfailed** (42 min); the 8 xfails are this phase's
findings, the skips are environmental (full-corpus gates, the `render` extra, host limits). `ruff check .`, `mypy`,
`tools/check_unicode.py` and `uv lock --check` pass. The SEC-11 dynamic tests were also run with the `render` extra
installed offline (18 passed), and the `dtap` fuzz with `AGENTPROV_FUZZ=thorough` (9 passed).

**Time cost.** The default suite gains about 3 minutes; the `slow` cases (the sealed Inspect corpus for the CRC rows,
other SEC-22 families and the hash-seed runs) add about 4. `slow` is not deselected by default (`pyproject.toml`).

Node ids below are relative to `tests/security/` unless they start with `tests/`.

## SEC-15: tamper matrix and deposits (K.12.5, K.12.15)

| Check | Status | Test node id | Notes |
|---|---|---|---|
| Every sealed file kind (25 kinds: manifest, index, register, derivation, origins, members, raw object, AER, SEM, PROV, validation results and summary, datasheet, changelog, three licence files, seven `rules/` files, schema) **edited**, **removed**, **added** (where a second file of the kind is grammar-admitted) and **reordered** (JSONL lines, JSON keys): the `checksums` level names the change | COVERED | `test_sec15_tamper_matrix.py::test_sec15_every_sealed_file_kind_edited_removed_added_or_reordered_is_detected[<kind>-<op>]` (68 cases) | exactly one of `checksums.mismatch`, `.missing`, `.unlisted` |
| Checksums regenerated by the attacker over each of those changes: `checksums` passes; the published root digest detects it, also with `--release` | COVERED | same test, step 2 | `root_digest.mismatch` in every case (D-39) |
| `chain` over the regenerated checksums names the broken H.5.1 link | COVERED | same test, step 3 | e.g. `aer.seal.digest`, `sem.seal.digest`, `index.digest.prov`, `index.digest.validation`, `raw.digest.mismatch`, `raw.object.missing`, `manifest.files`, `manifest.digests`, `rules.mismatch`, `index.invalid`, `corpus.read.*` |
| Files no digest chain covers (DATASHEET, CHANGELOG, `LICENSES/**`, `schemas/**`, the manifest's key order, orphan AER/SEM/PROV files, an added `WITHHELD.json` or `views/` file): detected by the root digest only | COVERED (boundary pinned) | same test (`chain_code` `None`); `test_sec15_tamper_matrix.py::test_sec15_an_added_optional_file_is_detected_by_the_checksums_and_root_digest_only[withheld,view]` | as H.5.5 specifies; see proposals P-1, P-2 |
| `checksums.sha256` itself edited, removed, reordered | COVERED | `::test_sec15_an_edited_or_removed_checksums_file`, `::test_sec15_a_reordered_checksums_file_is_malformed_and_every_line_is_named_by_number` | `checksums.absent`, `root_digest.unverifiable`; refused lines are named `#<n>`, never echoed |
| `corpus.json` removed | COVERED | `::test_sec15_a_removed_manifest_leaves_no_sealed_corpus_to_verify[checksums,chain,rederive]` | exit 2 (not a sealed corpus, N.1.5) at every level, never 0 |
| `rederive` detects a derived-only forgery (checksums, index digest and manifest regenerated) | COVERED (phase 11) | `tests/corpus/test_tamper.py::test_forged_derived_file` | not duplicated |
| Forged origin blob SHA-1 | COVERED (phase 11) | `tests/corpus/test_tamper.py::test_forged_raw_origin` | not duplicated |
| Forged AER seal; AER lines reordered | COVERED (phase 11) | `tests/corpus/test_tamper.py::test_forged_aer_seal`, `::test_reordered_aer_lines` | the matrix adds AER, SEM and PROV reorders |
| `verify --level chain` detects a member CRC-32 (and size) mismatch on a **sealed** corpus, also after a consistent forgery of `raw/members.jsonl` and the manifest | COVERED (`slow`) | `test_sec15_tamper_matrix.py::test_sec15_chain_checks_member_crc32_and_size_on_a_sealed_corpus_even_after_a_consistent_forgery` | the phase-11 test ran on a working tree only; the fixture seals the Inspect AgentHarm test corpus (176 executions, 177 selected members), about 110 s |
| An altered member object of a sealed corpus | COVERED (`slow`) | `::test_sec15_chain_detects_an_altered_member_object_on_a_sealed_corpus` | `raw.digest.mismatch` + `raw.member.crc32` |
| A raw object hidden behind a forged tombstone (consistent forgery) | COVERED | `::test_sec15_a_raw_object_hidden_behind_a_forged_tombstone_is_reported_and_fails_release_mode` | reported `tombstoned` (never silently missing); dev exit 0 with the finding, release exit 1; root digest detects |
| A raw object hidden behind a forged `REFERENCES.json` entry (consistent forgery) | **FINDING F-12C-01** | `::test_sec15_a_raw_object_hidden_behind_a_forged_reference_is_never_passed_silently` (xfail strict); control: `::test_sec15_a_raw_object_hidden_behind_a_forged_reference_with_only_the_checksums_regenerated_fails` | see Findings |
| Archive mode reads a deposit without extraction | COVERED | `test_sec15_deposits.py::test_sec15_archive_mode_reaches_no_extraction_api_and_writes_nothing_anywhere`; phase 11: `tests/corpus/test_deposit_verify.py::test_a_clean_deposit_passes_chain_in_archive_mode_without_extraction` | new: extraction APIs and `tempfile.mkdtemp` patched to fail; deposit, source corpus, cwd and `$AGENTPROV_HOME` guarded unchanged; lone meta archive too |
| Tree mode: a symlinked raw object is refused, never followed | COVERED | `test_sec15_deposits.py::test_sec15_a_symlinked_raw_object_is_refused_and_never_followed` | `checksums.unreadable` + `corpus.tree.link`; the sentinel target (identical bytes) is never opened (audit hook); the attacker cannot re-seal (`corpus.integrity.not_closed`) |
| Tree mode: a symlinked shard directory or execution file | COVERED | `::test_sec15_a_symlinked_shard_directory_is_refused_and_never_followed`, `::test_sec15_a_symlinked_execution_file_is_refused_and_never_followed` | — |
| Tree mode: a `../`, inner `../` or absolute relpath in `checksums.sha256`, an index row, the manifest's `files`, a rule catalogue, a semantics profile or a source profile entry is refused before it is opened | COVERED | `::test_sec15_a_hostile_relpath_in_checksums_is_refused_before_it_is_opened[*]`, `::test_sec15_a_hostile_relpath_in_an_index_row_is_refused_before_it_is_opened[*]`, `::test_sec15_a_hostile_relpath_in_the_manifest_is_refused_before_it_is_opened[*]` (18 cases) | `checksums.path_invalid`, `index.invalid`, `manifest.invalid` / `manifest.files` / `rules.mismatch`; sentinel never opened |
| Deposit: a member named `<prefix>/../x`, with an inner `../`, absolute, or with backslashes | COVERED | `::test_sec15_a_hostile_member_name_in_a_deposit_archive_is_a_label_never_a_path[*]` | label, never a path; never echoed on stdout/stderr |
| Deposit: a `../`, absolute or nested archive name in `DEPOSIT-MANIFEST.json` | COVERED | `::test_sec15_a_hostile_archive_name_in_the_deposit_manifest_is_refused[*]` | `deposit.manifest.invalid` |
| Deposit: a symlinked archive; a symlinked deposit manifest | COVERED | `::test_sec15_a_symlinked_archive_in_a_deposit_is_never_followed`, `::test_sec15_a_symlinked_deposit_manifest_is_not_a_deposit` | `deposit.unlisted` + `deposit.missing`; a linked manifest is no deposit (exit 2) |
| A swapped `rules/` copy gives `rules.mismatch` and is not loaded | COVERED | tree mode (phase 11): `tests/corpus/test_tamper.py::test_swapped_rules_copy` (rederive still identical); archive mode (new): `test_sec15_deposits.py::test_sec15_a_deposit_with_a_swapped_rules_copy_fails_with_rules_mismatch_in_archive_mode`; builder: `::test_sec15_the_deposit_builder_with_the_cli_verifier_refuses_a_forged_rules_authority[swapped]` | the deposit is internally consistent at `checksums`; only the authority check sees it |
| A catalogue version the package does not ship gives `rules.unavailable` | COVERED | tree mode (phase 11): `tests/corpus/test_tamper.py::test_unshipped_catalogue_version`; archive mode (new): `::test_sec15_a_deposit_whose_catalogue_version_the_package_does_not_ship_is_unverified_never_passed`; builder: `::…forged_rules_authority[unshipped]` | unverified: dev exit 0 with the finding, release exit 1; the builder refuses (`release.failed.verify`) |
| Positive control for the audit-hook spy | COVERED | `::test_sec15_the_open_spy_records_an_open_of_a_sentinel_and_nothing_else` | guards every `spy.events == []` against passing vacuously |

**Observation (not a finding).** A `--corpus` path that is itself a symbolic link to a sealed corpus is followed and
verified (exit 0). The root is the user's own choice of path; G.3.6's no-follow rule applies to the relpaths inside it.
Recorded so the reviewer can decide whether `verify` should refuse a linked root as `import --input` does.

## SEC-19: duplicates across snapshots and within a snapshot (K.12.5; HL H.7)

| Check | Status | Test node id | Notes |
|---|---|---|---|
| The same bytes at two origins of one snapshot give one execution with two origins; `n_origins` on the index row | COVERED (12a) | `test_import_controls.py::test_sec19_the_same_bytes_at_two_paths_are_one_execution_with_two_origins` | working corpus |
| … and in a **sealed** corpus: `n_origins`, `snapshot_ids`, both origins in `raw/origins.jsonl`, one `dedup.collapsed` register entry, the manifest's `duplicates` tallies (D-41), `chain` passes | COVERED | `test_sec19_cross_snapshot.py::test_sec19_a_sealed_corpus_records_the_collapse_in_its_index_register_origins_and_duplicates_summary` | `{collapsed: 1, multi_origin_executions: 1, multi_snapshot_executions: 0, …}` |
| A forged duplicate tally, row `n_origins` or row `snapshot_ids` (consistent forgery) | COVERED | `::test_sec19_a_forged_duplicate_record_is_detected_by_chain[tally,n_origins,snapshot_ids]` | `manifest.duplicates` (the tallies recompute from index and register) |
| A dropped second origin with only the checksums regenerated | COVERED | `::test_sec19_a_dropped_second_origin_with_only_the_checksums_regenerated_is_detected` | `manifest.files` |
| A dropped second origin, manifest regenerated too | **FINDING F-12C-02 (b)** | `::test_sec19_a_collapsed_execution_whose_second_origin_was_dropped_is_never_passed` (xfail strict) | see Findings |
| Index rows attributed to a snapshot the manifest does not declare, tallies updated to match | **FINDING F-12C-02 (a)** | `::test_sec19_an_index_row_attributed_to_an_undeclared_snapshot_is_never_passed` (xfail strict) | see Findings |
| Cross-snapshot collapse **inside one corpus** (H.7.2(1)/(3): one row listing both snapshots) | DEFERRED (by decision) | `::test_sec19_a_second_snapshot_into_one_working_corpus_is_refused_with_exit_4_and_writes_nothing` | the build refuses a second snapshot (G4, `corpus.identity_mismatch`, exit 4; MN N.2.2(7)); D-35 (user-confirmed) splits AgentDojo June-2024 and HEAD into two corpora. No byte or file of the working corpus changes (the writer's lock file comes and goes) |
| The same bytes in **two snapshot corpora** (D-35 layout) | COVERED | `::test_sec19_the_same_bytes_in_two_snapshot_corpora_are_one_execution_each_with_one_id_and_their_own_snapshot` | one execution in each, same content-addressed id, `source_key` and `raw`; each row, origin and manifest names only its own snapshot and commit; the two AERs differ only in the header's artefact origin commit (and so the seal) |
| `select.owned_elsewhere` + `owner`, not imported twice | COVERED (before 12c) | `tests/adapters/runner/test_profile_selection.py::test_excluded_files_are_registered_with_their_code_and_owner` | cross-corpus checks DEFERRED (AD-10 row 6) |

**Spec drift (for the spec owner; no test fails on it).** H.7.2(1) and (3), the `agentdojo-upstream` row of the H.4.2
source table ("Both snapshots in one corpus") and the `--snapshot` row of MN N.2.2 ("Several snapshots may share one
corpus, one per invocation") still describe several snapshots in one corpus. MN N.2.2(7) ("A second snapshot in one
working corpus is therefore refused in this build") and D-35 say otherwise, and the code follows them; D-108 still calls
the second snapshot "phase 11", which did not build it. With one snapshot per corpus, two corpora of one source can
hold the same execution id with different AER bytes (the recorded origin commit). D-35 records the shared ids
(`datasheet-items.md` row 3); that the AER, SEM and PROV bytes of a shared id differ is not stated there and is worth
adding.

## SEC-12: display of untrusted content on the phase-11 surfaces (K.12.6(c)(e)(f); G.8.2, G.8.6)

Input: one sealed corpus built at test time from a synthetic Inspect `.eval` (`inspect_support.build_eval`, no fixture
text) whose model id (a label that reaches the AER, the index, `corpus.json` `models` and the datasheet) and whose tool
output and final answer (content) carry terminal escapes, bidi, U+2028/U+2029, CR and LF, Markdown headings, a backtick,
HTML (`<img onerror>`, `<!--`), a `javascript:` link, ChatML and `<think>` forgeries, shell and template payloads and an
agent-addressed sentence assembled at run time. Imported in release mode, sealed with `corpora/ast-survey-agentharm`.
An AgentDojo probe was also run: AgentDojo log fields (pipeline name, versions, injections, messages) reach the raw
store and the AER only, never `corpus.json` `models` or `framework_identities`, so the datasheet path needs a source whose
model id is taken from the log (Inspect; capture's served model).

| Check | Status | Test node id | Notes |
|---|---|---|---|
| Hostile text kept byte-identical as data in raw and AER (K.12.6(d)) | COVERED | `test_sec12_display_surfaces.py::test_sec12_hostile_text_is_kept_byte_identical_as_data_in_raw_and_aer` | 12a proved it for AgentDojo (`test_untrusted_content.py`) |
| `stats` (text, Markdown, CSV, JSON; `--artefacts --per-execution`) prints no content and no raw control; starts no process; corpus and cwd unchanged (K.12.6(a)(b)(c)) | COVERED | `::test_sec12_stats_prints_no_content_and_no_raw_control_in_any_format[*]` | `subprocess.Popen` patched to fail; `fs_guard` over the corpus and an empty cwd |
| `stats` escapes data-derived labels (G.8.6): no raw control | COVERED | `::test_sec12_a_data_derived_stats_label_carries_no_raw_control` | `model_label` over the hostile AER |
| … a label is one line and cannot add Markdown lines or HTML | **FINDING F-12C-04** | `::test_sec12_a_data_derived_stats_label_is_one_line`, `::test_sec12_a_data_derived_stats_label_cannot_add_markdown_lines_or_html` (xfail strict) | function level: the shipped Inspect artefact catalogue gives no artefacts-table row (the only table keyed by a data-derived label) for a synthetic log, so the row is added to the real report document of the hostile corpus and rendered with `stats.output.render` |
| CSV formula guard: a data-derived cell starting with `=`, `+`, `-` or `@` is prefixed with `'` | COVERED | `::test_sec12_a_data_derived_csv_cell_never_starts_a_spreadsheet_formula[*]` | no earlier test asserted it |
| `inspect` without `--show-content` prints no content on any view (`summary`, `records`, `timeline`, `evidence`, `sem`, `prov`, `raw`; text and JSON); the model label only escaped; no process; nothing written (K.12.6(f)) | COVERED | `::test_sec12_inspect_without_show_content_prints_no_content_and_labels_only_escaped[*]` (14 cases) | the label is a G.8.6 label: shown on one line with `<U+001B>` escapes |
| `inspect` of a corpus root, an AER, a SEM and a PROV file prints no content | COVERED | `::test_sec12_inspect_of_a_corpus_root_or_a_file_prints_no_content[*]` | — |
| `inspect --show-content`: every content value is inside a `quote_untrusted` fence, no raw control | COVERED | `::test_sec12_inspect_with_show_content_fences_every_content_value[*]`; positive control `::test_sec12_inspect_records_with_show_content_shows_the_payload_fenced` | fence check pairs each `<<UNTRUSTED <token>` header with its `<<END UNTRUSTED <token>>>` |
| `DATASHEET.md` holds no content and has its untrusted-content section | COVERED | `::test_sec12_the_datasheet_holds_no_content_and_has_its_untrusted_content_section`; phase 11: `tests/unit/corpus/test_datasheet.py::test_the_datasheet_has_the_untrusted_content_section_g85` | — |
| Generated Markdown escapes data-derived values (K.12.6(e)) | **FINDING F-12C-03** | `::test_sec12_the_datasheet_has_no_raw_control_character`, `::test_sec12_a_hostile_model_id_cannot_add_markdown_structure_or_html_to_the_datasheet` (xfail strict) | end to end through `seal` |
| `CHANGELOG.md`, `NOTICE.md`, `DERIVED.txt` hold no data-derived text | COVERED | `::test_sec12_the_other_generated_files_hold_no_data_derived_text[*]` | from the spec and the in-package profile only |
| `verify` prints neither content nor the label | COVERED | `::test_sec12_verify_prints_no_content_or_label[checksums,chain]` | — |
| `render` DOT and SVG | COVERED (before 12c) | `tests/render/test_render.py` (render extra) | unchanged; the pydot ban is item 4 |

## SEC-11: pydot never spawns Graphviz (K.12.6 static test; K.5.12; G.8.6)

| Check | Status | Test node id | Notes |
|---|---|---|---|
| pydot imported only by `render/dot.py`, only inside functions; no other Graphviz binding (`graphviz`, `pygraphviz`, `networkx` drawing, `prov.dot`) anywhere in `src/agentprov`, `capture/src`, `backends/shared/src` | COVERED | `test_sec11_pydot_ban.py::test_sec11_no_module_imports_pydot_or_another_graphviz_binding_where_it_may_not` | 255 files |
| No pydot `create`/`write`, no generated `create_<fmt>`/`write_<fmt>` (73 names in pydot 4.0.1), no `call_graphviz`, no `getattr` with such a name or a computed name on a pydot object, also through aliases (`h = g`, `import pydot as p`, `pydot = require_pydot()`) | COVERED | `::test_sec11_no_module_reaches_a_pydot_method_that_spawns_graphviz`, `::test_sec11_the_pydot_home_builds_text_only` | replaces the phase-11 render-module check, which looked only at variables named `graph`, `pydot` or `g` (`tests/render/test_render.py::test_pydot_is_imported_only_inside_functions_and_never_asked_to_spawn_graphviz`) |
| The scanner reports every forbidden pattern and ignores ordinary `stream.write`/`proc.stdin.write` | COVERED | `::test_sec11_the_scanner_reports_each_forbidden_pattern[*]` (11 snippets), `::test_sec11_the_scanner_leaves_ordinary_write_and_create_calls_alone` | positive and negative controls |
| `agentprov render --format dot` (with and without `--show-content`) starts no process and never reaches pydot's spawning entry points | COVERED (`render` extra) | `::test_sec11_render_to_dot_starts_no_process_and_never_reaches_pydot_spawning[*]` | `Dot.create`, `Dot.write`, `pydot.core.call_graphviz` patched to fail; `subprocess.Popen` recorded; skipped without pydot |
| `--format svg` starts only the absolute `dot` with `-Tsvg` (and `-V`), no shell | COVERED (`render` extra + Graphviz) | `::test_sec11_render_to_svg_starts_only_the_absolute_dot_with_a_fixed_argv` | argv and environment of `run_dot` itself: `tests/render/test_render.py::test_dot_is_the_only_process_with_a_fixed_argv_and_a_minimal_environment` |

The `render` extra (pydot 4.0.1) is in `uv.lock`; it was installed offline from the local uv cache into this worktree's
`.venv` for the run (`uv run --extra render --offline`) and removed again (`uv sync --offline`). Without it the three
dynamic tests skip with the reason, as `tests/render` does.

## SEC-25: `purge` of a leaked credential (K.12.11; G.9.5, G.9.6; D-46)

Input: a working corpus imported in release mode from two synthetic AgentDojo logs, one tool output carrying a
credential-shaped sentinel assembled at run time; `agentprov -vv --log-file … purge sha256:<object> --reason secret
--corpus … --yes --json`.

| Check | Status | Test node id | Notes |
|---|---|---|---|
| The sentinel is stored before the purge (control) | COVERED | `test_sec25_purge.py::test_sec25_the_leak_is_stored_before_the_purge` | — |
| `purge` removes the object and writes a tombstone `{date, reason, sha256}` without the value; neither the tombstone file, the register, stdout, stderr nor the DEBUG log file holds any 8-character fragment of it; the citing execution gets `release.withheld` | COVERED | `::test_sec25_purge_removes_the_object_and_leaves_a_tombstone_without_the_value` | phase 11 checked the tombstone fields and stdout/stderr on a hand-built store (`tests/cli/test_purge_cmd.py::test_purge_removes_tombstones_and_withholds`) |
| `verify --level chain` reports the object `tombstoned`, never missing; prints no fragment | COVERED | `::test_sec25_verify_reports_the_purged_object_as_tombstoned_never_as_missing` | tombstoned fails release mode (H.5.5) |
| A purged working corpus cannot be sealed, so the value never reaches a sealed corpus or deposit | COVERED (fail closed) | `::test_sec25_a_purged_working_corpus_cannot_be_sealed_so_the_value_never_reaches_a_release` | sealing verifies in release mode and refuses (`corpus.manifest.verify`, `raw.tombstoned`); see proposal P-3. The private working tree keeps the execution's AER (G.9.5: "kept in the private store") |
| A sealed corpus is never purged | COVERED | `::test_sec25_a_sealed_corpus_is_never_purged` | exit 4, tree unchanged |
| A re-import after the purge never stores the tombstoned object again | **FINDING F-12C-05** | `::test_sec25_a_reimport_never_stores_a_tombstoned_object_again` (xfail strict) | the D-46 open item, now with a reproduction |

## SEC-26: `package` and the deposit builder under the interpreter guard (K.12.12(2)(3); G.3.8; AD-16)

| Check | Status | Test node id | Notes |
|---|---|---|---|
| `package` (seal mode) refuses a working corpus whose manifest records an `interpreter_advisory` with exit 4, on a patched interpreter, and writes nothing | COVERED | `test_sec26_package.py::test_sec26_package_refuses_an_advisory_working_corpus_with_exit_4_on_a_patched_interpreter` | the advisory comes from a real dev-mode import of a synthetic `.eval` below 3.14.8 (warning raised and the record asserted); before 12c only the function level was tested |
| `package --deposit` refuses a sealed corpus that records an advisory with exit 4; no deposit written | COVERED | `::test_sec26_package_deposit_refuses_a_sealed_corpus_that_records_an_advisory_with_exit_4`; control `::test_sec26_the_deposit_control_builds_on_a_patched_interpreter` | the advisory is set with `release_support.restamp` (a sealed advisory corpus cannot be produced: dev-mode corpora fail sealing) |
| `package --deposit` below 3.14.8 exits 3 before any archive is opened; nothing written | COVERED | `::test_sec26_package_deposit_below_the_floor_exits_3_before_any_archive_is_opened` | builder level was tested in phase 11 |
| `verify --release --level rederive` (tree mode) below 3.14.8 exits 3 before reading | COVERED | `::test_sec26_verify_release_rederive_below_the_floor_exits_3_before_reading` | archive mode: `tests/corpus/test_deposit_verify.py::test_release_mode_below_the_interpreter_floor_is_refused_before_reading` |
| `package` (seal mode) below 3.14.8 opens no archive | COVERED (observation O-2) | `::test_sec26_package_below_the_floor_opens_no_archive_while_sealing`; spy control `::test_sec26_the_archive_spy_sees_an_in_process_archive_open` | no zip opened in process and no T1 worker started; sealing is **not** refused (exit 0) |

**Observation O-2 (for the spec owner).** K.12.12(2) and the SEC-26 row list `package` among the release-mode entry points
that refuse below 3.14.8 with exit 3. In this build the seal mode of `package` does not call the guard: it opens no
archive (proved above), so no CVE-affected parser runs, and the deposit builder, the actual release step, refuses below the
floor. The sealed manifest's `producer.python` then records the old interpreter while `interpreter_advisory` stays `null`.
Either the spec wording is narrowed to "reads no archive" or seal mode calls the guard; no security property depends on
the choice.

## SEC-22: `derive` and `recompute` determinism (K.12.10; K.13 RPR-8; invariant 4)

Sources built at test time: AgentDojo (three golden logs) and a synthetic Inspect `.eval` with two samples (the archive
container family: its re-map re-runs `expand` in T1), each as an AER-only corpus (for `derive`) and a full one (for
`recompute`). Every command runs under `fs_guard` over its source; trees are compared byte for byte, with only
`corpus.json` `producer.isolation` (D-43) removed for the in-process run.

| Check | Status | Test node id | Notes |
|---|---|---|---|
| `recompute` from raw, `--jobs 1` / `4` / `--in-process`, AgentDojo | COVERED (phase 11) | `tests/unit/corpus/test_derive.py::test_outputs_do_not_depend_on_the_worker_count` | — |
| `derive` (adds SEM, PROV, validation) byte-identical for `--jobs 1`, `--jobs 3`, a second `--jobs 3` run and `--in-process`; same counters | COVERED | `test_sec22_derive_determinism.py::test_sec22_derive_is_byte_identical_across_worker_counts_runs_and_in_process[agentdojo-aer]`; `[inspect-aer]` (`slow`) | asserts the layers were really derived |
| `recompute` (both stage sets: from the stored AER, and the default re-map from raw) byte-identical across those four runs | COVERED | `::test_sec22_recompute_is_byte_identical_across_worker_counts_runs_and_in_process[inspect-from-raw]`; `[inspect-from-aer]`, `[agentdojo-from-raw]`, `[agentdojo-from-aer]` (`slow`) | the container re-map reproduces `raw/members.jsonl` byte for byte; every execution `identical` |
| `recompute --dry-run` summaries (counters, failures) byte-identical across `--jobs 1`, `--jobs 3`, `--in-process` | COVERED | `::test_sec22_recompute_dry_run_summaries_are_byte_identical_across_worker_counts[inspect]`; `[agentdojo]` (`slow`) | — |
| Fresh interpreters with `PYTHONHASHSEED` 0 and 4242 (`python -m agentprov`, `--jobs 2`) give the in-process tree | COVERED (`slow`) | `::test_sec22_outputs_do_not_depend_on_the_process_or_its_hash_seed[*]` (derive and recompute, both families) | — |
| A worker failure ends in a degenerate AER and keeps the raw bytes | COVERED (12a) | `test_import_controls.py::test_sec22_a_map_job_stopped_by_a_limit_is_registered_with_its_limit_code_and_keeps_the_raw_bytes` | — |

## Fuzzing of the `dtap` reader (K.11.1; D.16.1, D.16.2)

New file `tests/fuzz/test_dtap_reader_fuzz.py`, under the `fuzz_support` budgets and the F-3 working-directory guard of
`tests/fuzz/conftest.py`. Reader only; the mapper and short arbitrary bytes are fuzzed by phase 10b's
`tests/adapters/dtap/test_fuzz.py`. Default run: 9 passed in about 19 s; `AGENTPROV_FUZZ=thorough` (×20): 9 passed in
173 s (2026-10-12). No defect found.

| Check (K.11.1) | Status | Test node id | Notes |
|---|---|---|---|
| Every committed seed is classified; executions parse, the LFS pointer and the synthetic run do not | COVERED | `tests/fuzz/test_dtap_reader_fuzz.py::test_every_seed_is_classified_and_the_executions_parse` | seeds read by the test, never printed |
| F-1/F-5: `sniff` total, `parse` one item iff `sniff` matched, else `MalformedArtefact` or a G.3.9 `IngestError`; deterministic with a fresh reader | COVERED | `::test_sniff_and_parse_are_total_and_deterministic_on_mutated_seeds` | byte mutations of the 25 fixture files |
| The sniff-then-parse cache never returns another input's value | COVERED | `::test_the_sniff_cache_never_lets_parse_return_another_inputs_value` | interleaved inputs, equal-but-distinct byte objects |
| The D.16.2 sniff table as a differential oracle (trajectory, judge, red-teaming, synthetic flag in `task_info` or `traj_info.metadata`, `debug` flag) and `register_detail` | COVERED | `::test_the_sniff_follows_the_d16_2_table` | the oracle is written from the spec table |
| An LFS pointer is never parsed | COVERED | `::test_an_lfs_pointer_is_never_parsed` | — |
| `parse_path`/`config_path` total on hostile labels (dot segments, backslashes, empty, long, reserved names); facets keep the grammar; a label the names guard admits yields no `.`/`..` segment and a normalised configuration path | COVERED | `::test_parse_path_and_config_path_are_total_and_keep_the_grammar` | see observation O-3 |
| `file_class` total; only ASCII digits make `timestamp`/`copy`/`rerun` | COVERED | `::test_file_class_is_total_and_only_ascii_digits_make_a_time_named_class` | all Unicode `Nd` digits tried |
| `state_form` total on arbitrary JSON, lone surrogates, 3,000-deep brackets, Python-literal and code-like strings; nothing evaluated | COVERED | `::test_state_form_is_total_and_evaluates_nothing` | see observation O-3 |
| `iter_artefacts` and `auxiliary_for` total and order-independent on hostile listings; strays skipped; a judge file primary only where no trajectory-bearing file is chosen in its directory; auxiliary refs stay in the directory or are `tasks:` refs that exist | COVERED | `::test_discovery_is_total_deterministic_and_keeps_the_judge_rule` | discovery never opens a file |

**Observation O-3 (for the `dtap` owner; no test fails on it).** `parse_path` accepts `.` and `..` as facet values (a
label `openaisdk/../code/benign/1/x.json` parses, and `config_path` then contains `..`). This is safe in the pipeline,
because the walk hands the reader only labels the names guard admits and configuration refs are looked up as labels,
never opened as paths; the fuzz test pins that combination. The `state_form` docstring lists eight classes but the code
also returns `json_text` and `other`.

## Findings

| Id | Severity | Where (owner) | Reproduction | Expected | Actual |
|---|---|---|---|---|---|
| F-12C-01 | Low | `src/agentprov/corpus/verify.py` (`_Verifier._missing_object`, `references`); orchestrator | `test_sec15_tamper_matrix.py::test_sec15_a_raw_object_hidden_behind_a_forged_reference_is_never_passed_silently`: on a sealed corpus whose snapshot has `raw_policy = "include"`, delete one included raw object, write `raw/REFERENCES.json` with one entry for it that carries its real pinned git origin (so `raw.reference.unpinned_origin` does not fire), regenerate the manifest's `files`, `digests` and content digest and `checksums.sha256` (`verify_support.reforge`), run `verify --level chain --release --root-digest <the forger's root digest>` | A referenced object in an include-policy snapshot is a failure, or at least `unverified` (its bytes and the AER `artifacts` link were not checked; H.5.5: "a skipped check is reported as such and produces exit status 1 in release mode"), so release mode fails | No finding at all; exit 0 in dev and release mode. Only the root digest published outside the corpus detects it (as for every self-consistent forgery, T-13 residual). The equivalent tombstone forgery is reported `tombstoned` and fails release mode |
| F-12C-02 | Low | `src/agentprov/corpus/verify.py` (`_Verifier.executions`, `manifest_members`); orchestrator | (a) `test_sec19_cross_snapshot.py::test_sec19_an_index_row_attributed_to_an_undeclared_snapshot_is_never_passed`: on a sealed one-snapshot corpus (`2024-06`), set every index row's `snapshot_ids` to `["2024-06", "head"]`, set `duplicates.multi_snapshot_executions` to the row count, regenerate the manifest digests, content digest and checksums. (b) `::test_sec19_a_collapsed_execution_whose_second_origin_was_dropped_is_never_passed`: remove one of the two `raw/origins.jsonl` lines of a collapsed execution (its row keeps `n_origins: 2`), regenerate the same | `chain` fails: every snapshot a row names is declared in `sources[].snapshots`, and a row's `n_origins` equals its origins in `raw/origins.jsonl` (H.7.2(1); H.5.5 "register ↔ index ↔ counts reconciliation") | Exit 0 in dev and release mode; only the published root digest detects either forgery |
| F-12C-03 | **Medium** | `src/agentprov/corpus/datasheet.py` (`_md`, `_t_models`, `_t_frameworks`; the `{{v:...}}` placeholder fill); orchestrator | `test_sec12_display_surfaces.py` fixture `hostile`: a synthetic Inspect `.eval` whose header `eval.model` is a hostile string, imported (release mode) and sealed; read `DATASHEET.md` | Data-derived manifest values are escaped for display (G.8.2/G.8.6) and for Markdown (K.12.6(e): "no unescaped payload text that could inject Markdown or HTML"): one line per cell, no raw control, no backtick, `<`, `[`/`]` or `!` that a renderer would interpret | `_md` escapes only `\`, `|` and LF. The model id's ESC, RLO, CR and U+2028 are written raw; its backtick closes the cell's code span, so `<img src=x onerror=…>` and a `javascript:` link become live Markdown/HTML; its CR starts a new `# …` heading line; its `<!--` opens an HTML comment that hides the rest of the datasheet, including the "Untrusted content" warning section, in a renderer. The datasheet is published in every deposit. The `framework_identities` columns (`fw`, `distribution`, `reported_version`, `suite_set`) and `served`/`provider` use the same `_md`; only `requested` was exercised end to end |
| F-12C-04 | Low | `src/agentprov/stats/tables.py` (`_label`, `model_label`) and `stats/output.py` (`_md`); orchestrator | `test_sec12_display_surfaces.py::test_sec12_a_data_derived_stats_label_is_one_line`, `::…cannot_add_markdown_lines_or_html`: `model_label` over the hostile corpus's AER, then `stats.output.render` of the corpus's report with one artefacts row keyed by that label | A label is one escaped line (LF and TAB escaped too), and the Markdown format escapes HTML and Markdown link/heading syntax | `escape_untrusted` keeps LF and TAB (correct for fenced content, not for a table cell), so a model id splits its row into forged lines and headings in `text` and `markdown`; `<img`, `<!--` and `](javascript:` pass into the Markdown output. Raw control characters are escaped. Reaching it needs an artefacts-table row for a hostile model id (no shipped catalogue entry fired on the synthetic log) |
| F-12C-05 | Medium | the import pipeline's raw-store writes (`src/agentprov/adapters/runner/importer.py` through `raw/store.py`); phase 12b (the D-46 item "blocking tombstoned digests at ingest" moved to phase 12) | `test_sec25_purge.py::test_sec25_a_reimport_never_stores_a_tombstoned_object_again`: import a log carrying a credential, `purge` its object (`--reason secret`), run the same import again into the same working corpus | The tombstoned digest is never stored again; the candidate is registered (G.9.6; D-46) | Both executions are `skipped_resume`, yet the purged object, with the credential, is written back into `raw/objects/`, beside its tombstone. A later `verify` reports the object `tombstoned` while it is present |

**Status (2026-10-12, branch `fix-12c-findings`, not yet merged).** F-12C-03 **fixed** (`c3f5eda`: every manifest
value in `DATASHEET.md` passes `escape_untrusted_line` and `escape_markdown`, H.9(8)); F-12C-01 **fixed** (`6e86d7d`:
`raw.reference.not_permitted`, D-160 user-approved); F-12C-02 **fixed** (`c973bb2`: `index.snapshot.undeclared`,
`index.n_origins`); F-12C-04 **fixed** (`aa11274`: one-line labels, Markdown escaping; D-161 user-approved). Their six strict
xfails pass and lost their markers. F-12C-05 is still open (phase 12b).

## Proposals (for the orchestrator; no test fails on them)

- **P-1. Orphan execution files.** An AER, SEM or PROV file that no index row names, added with `checksums.sha256`
  regenerated, passes `chain` (H.5.5 has no reverse check from files present to index rows). A one-line reconciliation
  (every `aer/`, `sem/`, `prov/` label present is named by a row) would move it from root-digest-only to `chain`.
- **P-2. Copied package files.** `schemas/**` are copies of package resources (H.1.2) but, unlike `rules/**`, are not
  compared with the package by `chain`; an added `WITHHELD.json` or `views/` file in a corpus whose spec has none is
  not reconciled with the manifest either. Both are detected only by the root digest today.

**Status (branch `fix-12c-findings`):** P-1 **implemented** (`9b33d8d`: `index.orphan`, sealed corpora; D-162
user-approved) and P-2 **implemented** (`d2a0cf9`: `schemas.mismatch`, `schemas.unavailable`, `withheld.undeclared`,
`views.undeclared`; D-163 user-approved); the tamper-matrix rows that pinned them as root-digest-only now expect these codes.
P-3 stays open.

- **P-3. No release path after a purge.** G.9.5 says a new corpus version is built with the object withheld and
  `WITHHELD.json` listing it. In this build sealing refuses any working corpus with a tombstone (sealing runs `chain` in
  release mode, where `raw.tombstoned` fails), and the seal code hard-codes `"withheld": 0`; nothing writes
  `WITHHELD.json`. This fails closed (the secret cannot reach a release), but a corpus with one leaked credential cannot
  be released at all until the withhold path exists.
  **Status (branch `withholding`, merged 2026-10-13): implemented** (D-230..D-237, user-approved 2026-10-13).
  Sealing withholds the tombstoned object and its executions, writes `WITHHELD.json` and renames the withheld files into
  the private sidecar `DIR.withheld/`. Release-mode `chain` accepts a tombstone exactly when `WITHHELD.json` lists it. The
  row above is replaced by `test_sec25_purge.py::test_sec25_a_purged_working_corpus_seals_with_the_value_withheld_so_it_never_reaches_a_release`
  and the end-to-end suite `test_sec25_withholding.py` (purge -> re-version -> seal -> `verify --release`, deposit).

## Decisions (phase 12c; D-63–D-69)

- **D-63.** Phase 12c's security tests reuse the phase-11 test helpers (`release_support`, `seal_support`,
  `derive_support`, `verify_support`) through a new helper module `tests/security/corpus_harness.py`, which puts them on
  the path and defines the `cli` and `sealed` fixtures; test modules bind those fixtures by assignment
  (`cli = harness.cli`). Rejected: editing `tests/security/conftest.py` (owned by another session) and importing the
  fixtures by name (ruff F811 on every test argument). The tamper matrix pins the D-39 boundary (root-digest-only files)
  as passing `chain`, so any later extension of `chain` is a visible, deliberate test change.
- **D-64.** SEC-19's cross-snapshot clause is tested as the build defines it (one snapshot per corpus: MN N.2.2(7),
  D-35): the G4 refusal of a second snapshot, and the D-35 two-corpora layout sharing execution ids. H.7.2's in-corpus
  collapse across snapshots is recorded as deferred with the spec drift above, not as a finding. Rejected: an xfail
  test demanding H.7.2(1) (it would contradict a user-confirmed decision).
- **D-65.** SEC-12's phase-11 surfaces are tested end to end on a hostile **Inspect** corpus, because AgentDojo log fields
  never reach the manifest's `models` or `framework_identities` (probe recorded above), while Inspect takes the model id
  from the log. The stats label case is tested at function level (`model_label` + `render` over the real report
  document) because no shipped artefact catalogue entry fires on a synthetic log. Rejected: forging an AER inside a
  sealed corpus to reach the surfaces (it would test a forged corpus, not hostile source data).
- **D-66.** SEC-11's pydot ban is a whole-codebase AST scan with alias and `getattr` tracking and a positive control,
  plus a dynamic check with pydot's spawning entry points patched to fail. The generated method names are listed from
  pydot 4.0.1's `Dot.formats` in the test; a pydot upgrade that adds a format needs that list extended (the dynamic test
  would still catch a call through `call_graphviz`). Rejected: banning every `.create`/`.write` attribute (ordinary
  stream writes are everywhere) and relying on the render-module check alone.
- **D-67.** SEC-25 and SEC-26 run end to end on real imports (AgentDojo with a sentinel credential; a synthetic Inspect
  `.eval` below the floor for the advisory) instead of the hand-built stores of the phase-11 unit tests. The interpreter
  is patched through `agentprov.envinfo._running_version`, as `test_interpreter_guard.py` does; archive opens are spied
  on `zipfile.ZipFile` in process, with a process spy for T1 workers (which a monkeypatch cannot reach) and a positive
  control. The seal-mode-below-the-floor behaviour is pinned as observed (exit 0, no archive opened) and recorded as O-2
  rather than as a finding.
- **D-68.** SEC-22's determinism tests compare whole working trees byte for byte and remove only `producer.isolation`
  (the one value D-43 records differently for `--in-process`); `--no-reuse` is passed so the reuse cache cannot mask a
  difference. One case per command runs by default (about 33 s); the other families, stage sets and the fresh-interpreter
  hash-seed runs are `slow`. The synthetic Inspect builder moved into `corpus_harness.inspect_working`, shared with
  SEC-26.
- **D-69.** The `dtap` reader fuzz lives in `tests/fuzz/` with the shared budgets and seeds from the committed fixtures,
  and puts `tests/adapters/dtap` on the path in the test module itself (the fuzz `conftest.py` is not this phase's). It
  adds a spec-table oracle for the sniff instead of re-checking the reader against itself, and leaves the mapper fuzz to
  phase 10b's file. Rejected: copying phase 10b's arbitrary-bytes test, and editing `adapters/dtap/` for O-3.
