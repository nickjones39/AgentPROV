# Phase 12a: evidence for DoD Q.15, Q.15a, Q.16, Q.17 and Q.31

Date: 2026-10-11, updated 2026-10-12 by phase 12b (branch `phase-12b`, with `main` @ `3c2503d` merged, so phase 11,
phase 12c and the phase-10 work are included). Host: macOS arm64 (M2 Max), CPython 3.14.8, uv 0.12.23. This records what
was checked, how, and what is still open. The sign-off for the user is `dod-signoff.md`.

**Status words.** MET: checked and true now. MET (local): true, but the CI run that should also show it has not run
(GitHub Actions has refused to start jobs since 2026-10-09, billing; AGENTS.md §0). OPEN: not yet checked or not yet
true; the reason is given.

## Q.15: the enumerated security categories pass

| Category (Q.15) | Evidence | Status |
|---|---|---|
| Archive traversal labels, symlinks and bombs | `tests/security/test_archives.py` (SEC-05/07/08; the exact obs-G8 reproduction), `test_decompression.py` (SEC-06), `test_links_special_files.py` (SEC-10), `test_raw_store_expand.py`, `test_selection_patterns.py` (F-08 bound, D-59), `test_nested_tar.py` (the nested `tar.gz` reader, D-57, with the obs-G1 cases), `test_expand_budget.py` (> 256 MiB selected, streaming, D-58/D-60); fuzz `test_ingest_fuzz.py`, `tests/fuzz/test_ingest_paths_fuzz.py`, `tests/fuzz/test_tar_fuzz.py` | MET |
| Deep or huge JSON and duplicate keys | `test_json_limits.py` (SEC-01/02/04), `test_encoding.py`, `test_jsonl_framing.py` (SEC-03); `tests/fuzz/test_jsonl_fuzz.py` | MET |
| Invalid UTF-8 | `test_encoding.py::test_sec01_invalid_utf8_gives_the_encoding_code_with_an_offset` and siblings | MET |
| Forged digests and manifests | AER seal (`tests/unit/aer/test_seal.py`), origin blob SHA-1 (`tests/adapters/runner/test_import_pipeline.py`), store never rewrites (`test_raw_store.py`), in-band claims (`test_inband_claims.py`, SEC-17), fetch and references (`test_fetch_hardening.py`, SEC-24). Corpus tamper matrix over 25 sealed file kinds (edited, removed, added; checksums regenerated against the root digest; `chain` names the link), `rederive`, member CRC on a sealed corpus, archive-mode deposits and tree-mode path safety: phase 12c, `test_sec15_tamper_matrix.py`, `test_sec15_deposits.py`, `test_sec19_cross_snapshot.py` (sec-coverage.md §5.6). Purged objects never return (D-61) | MET, with two Low findings open for the orchestrator: F-12C-01 and F-12C-02 (self-consistent forgeries that `chain` should reconcile; the published root digest detects both) |
| Reordered records | `test_reordering.py` (SEC-16), `capture/tests/test_verify.py`, `tests/fuzz/test_capture_log_fuzz.py` | MET |
| Prompt-injection strings rendered only through `quote_untrusted` | `test_quote_untrusted.py` (SEC-12), `test_untrusted_content.py`, CLI stream tests, the render tests (`render` extra); phase 12c on a hostile Inspect corpus: `stats` (every format), `inspect` with and without `--show-content`, `verify`, the generated files (`test_sec12_display_surfaces.py`) | MET for `validate`, `render`, `inspect`, `verify` and content; **OPEN** for data-derived *labels* in two generated surfaces: F-12C-03 (Medium, `DATASHEET.md` model id unescaped for Markdown/HTML) and F-12C-04 (Low, `stats` labels keep LF; Markdown passes HTML), routed to the orchestrator |
| Process controls run in CI and are documented | dependency scanning (job `dependencies`, osv-scanner over all four locks; `uv lock --check` in `core`), pinned-fetch hardening (SEC-24 tests in `core`), the interpreter guard (SEC-26 tests; the floor step in `core`); documented in `docs/threat-model.md` §6 | MET (local); no CI run since 2026-10-09 |

The full map of SEC-01…SEC-26 to tests, with every gap, is `docs/reports/hardening/sec-coverage.md`. Local run on
2026-10-11: `uv run pytest tests/security tests/fuzz tests/repo tests/property tests/boundary` gave **744 passed, 2
skipped** (the skips are host-dependent: no start-up footprint measured, and `RLIMIT_AS` not enforced on macOS).

## Q.15a: the interpreter policy holds (AD-16 as ruled)

| Clause | Evidence | Status |
|---|---|---|
| `requires-python = ">=3.14"`, `.python-version` `3.14` | `tests/security/test_import_controls.py::test_sec26_requires_python_and_the_interpreter_pin_are_314` | MET |
| CI core job on the latest 3.14 patch | `ci.yml` job `core`: `uv python install 3.14`, then the new step asserting `sys.version_info >= (3, 14, 8)`; guarded by `tests/repo/test_repository_hygiene.py::test_ci_scans_every_lockfile_and_checks_every_lock_and_the_interpreter_floor` | MET (local) |
| Below 3.14.8: release mode refuses archive and compressed-stream ingestion; dev mode warns and records `python_version` and `interpreter_advisory` | `tests/security/test_interpreter_guard.py`, `test_archives.py::test_sec07_interpreter_guard_refuses_before_the_object_is_opened_in_release_mode`, `tests/unit/raw/test_members.py`, `tests/unit/ingest/test_streams.py`; plain JSON unaffected: `test_import_controls.py::test_sec26_below_the_floor_a_plain_json_import_is_unaffected`. `package --deposit` below the floor exits 3 before any archive is opened; `package` refuses an advisory corpus (exit 4); `verify --release --level rederive` exits 3 (phase 12c, `test_sec26_package.py`) | MET. O-2 (`package` seal mode opens no archive and so has nothing to refuse) is resolved by narrowing the spec wording (D-62, user decision 2026-10-12) |
| No override flag | `test_interpreter_guard.py::test_no_override_flag_exists` | MET |

## Q.16: no secrets or corpora in Git

| Clause | Evidence | Status |
|---|---|---|
| gitleaks reports no findings on the repository history | **Re-run 2026-10-12 (phase 12b)**, gitleaks 8.30.1, `gitleaks git --config .gitleaks.toml --redact --log-opts="--all" .`: 389 commits on all local branches, ~42 MB. It first reported **2 findings**, both `generic-api-key` in `docs/reports/analysis/dtap-sample-check-data/d01-sample.json` (commit `346bf34`, 2026-10-11): lists of AgentPROV execution ids, two of which contain "api" or "key". False positives; `.gitleaks.toml` gained one allowlist entry anchored to the whole secret (`^ex_[a-z2-7]{26}$`, guarded by `test_the_execution_id_allowlist_entry_matches_only_a_whole_execution_id`). Re-run: **no leaks found**. The 2026-10-11 run (235 commits) was clean. CI job `secrets` still has no run since 2026-10-09 | MET (local); CI run still pending |
| `.env` is ignored and absent from history | `git check-ignore .env` → ignored (`.gitignore:8`); `git log --all -- .env '*/.env'` → 0 commits; `test_no_secret_files_logs_or_local_agent_notes_are_tracked` | MET |
| No corpus or raw store is tracked | `test_no_corpus_raw_store_or_upstream_clone_is_tracked` (records only under fixtures, goldens and the spec's examples; no corpus files, `raw/objects`, nested `.git` or gitlinks); `.gitignore` now also has `*.log` and `CLAUDE.local.md` | MET |

## Q.17: `uv lock --check` passes, and osv-scanner runs in CI

| Clause | Evidence | Status |
|---|---|---|
| `uv lock --check` | run 2026-10-11 and again 2026-10-12 (phase 12b, merged branch) in all five projects (`.`, `capture`, `backends/shared`, `backends/agentdojo`, `backends/autodojo`): exit 0 each; also a `core` CI step | MET |
| osv-scanner runs in CI | job `dependencies` now scans all four lockfiles (before phase 12a it scanned only the root `uv.lock`); guarded by the CI test above. **Local run 2026-10-11** (user-approved install, Homebrew osv-scanner 2.6.0) over the same four lockfiles (35 + 27 + 79 + 117 packages): **one advisory**, in `backends/autodojo/uv.lock` only: `nltk 3.10.3`, GHSA-8mgp-746c-j5xp (CVE-2026-81726, PYSEC-2026-3740, published 2026-09-02, CVSS 8.3): "Model-artifact APIs bypass pathsec and touch files outside allowed roots". **No fixed version exists** (affected up to and including 3.10.3, the latest). The core lock, `backends/shared` and `backends/agentdojo` are clean. Exposure: `nltk` is a dependency of the pinned AutoDojo fork only (T2, a separate uv project); the fork imports it lazily inside its filter defences, which AgentPROV refuses to run today (they need a GPU, weights and a Hugging Face token; AGENTS.md phase-9 follow-ups), and `punkt_tab` is provisioned unextracted from a pinned, digest-checked fetch. When the CI job runs, osv-scanner will fail on this advisory unless it is accepted with a recorded reason **Accepted by the user (2026-10-11)** in `backends/autodojo/osv-scanner.toml` with its reason and `ignoreUntil = 2027-01-11`; a re-run then reports "Filtered 1 vulnerability … No issues found" (exit 0). `tests/repo/test_repository_hygiene.py::test_every_accepted_dependency_advisory_has_a_reason_and_an_expiry` keeps every accepted advisory reasoned and time-limited | MET (local); CI run still pending |

## Q.31: agent hygiene

| Clause | Evidence | Status |
|---|---|---|
| `.gitattributes` marks `tests/fixtures/** binary`; `.ignore` and `.rgignore` list `tests/fixtures/` | `test_gitattributes_marks_the_fixture_tree_binary`, `test_search_ignore_files_list_the_fixture_tree` | MET |
| `.claude/settings.json` denies `Read(./tests/fixtures/**)` and `Read(./.env)` | `test_claude_settings_deny_reading_fixtures_and_env` (the deny rules are a partial control: they block the `Read` tool and a direct `cat`, not indirect shell reads; G.8.4, measured in phase 2) | MET |
| `inspect` shows content only with `--show-content`, always through `quote_untrusted` | phase 12c: `test_sec12_display_surfaces.py::test_sec12_inspect_without_show_content_*` (every view, text and JSON), `::test_sec12_inspect_with_show_content_fences_every_content_value` with a positive control; `validate` never prints content (`test_untrusted_content.py`) | MET |

## Status after phase 12b (2026-10-12)

1. Done: SEC-15, SEC-19, SEC-12 surfaces, the `package`/`release` refusal and the `inspect` gate (phase 12c); the
   Q.16 gitleaks re-run and the `uv lock --check` re-run (phase 12b); F-12C-05 fixed (D-61).
2. Open, not phase 12b's code: F-12C-01..04 (orchestrator); a manual CI dispatch once GitHub Actions starts jobs again
   (Q.15 process controls, Q.16, Q.17). O-2 is resolved (D-62). **The sign-off (`dod-signoff.md`) was accepted by the
   user on 2026-10-12.**
3. osv-scanner re-run on 2026-10-12 with the user's yes for network use (osv-scanner 2.6.0, the CI arguments: the four
   lockfiles, 35 + 27 + 79 + 117 packages): **No issues found**; the one accepted advisory (`nltk`, GHSA-8mgp-746c-j5xp,
   `backends/autodojo` only, accepted until 2027-01-11) is filtered with its recorded reason, as on 2026-10-11.
