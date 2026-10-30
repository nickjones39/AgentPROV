# Phase 12 (hardening): Definition-of-Done sign-off, for the user's acceptance

Date: 2026-10-12. Prepared by phase 12b. Branch `phase-12b`, with `main` @ `3c2503d` merged; it is not merged into
`main` and not pushed.

**Status: accepted by the user on 2026-10-12**, with O-2 resolved by narrowing the spec wording (D-62). The
conditions in §1 stand as recorded: F-12C-03 is to be fixed before any release or deposit; the CI dispatch is still
pending. The osv-scanner re-run was done on 2026-10-12 with the user's yes: no issues found (the accepted `nltk` advisory
filtered with its reason). The merge of `phase-12b` is a separate decision
(§3).

Phase 12's exit criteria (PQ table row 12) are DoD Q.15, Q.15a, Q.16, Q.17 and Q.31, plus the deliverables: fuzz and
security suites with the G.10 additions, the import-boundary and optional-extras tests, `docs/adapter-guide.md`,
`docs/threat-model.md` and `docs/roadmap.md`. The evidence is in `dod-evidence.md`, and the row-by-row coverage is in
`sec-coverage.md` (§5 for 12a, §5.5 for 12b, §5.6 for 12c merged; details in `sec-coverage-12c.md`).

## 1. Proposed verdict per criterion

| Criterion | Proposed | Why | Condition or open item |
|---|---|---|---|
| **Q.15** security categories | **MET, with conditions** | Every category has passing tests (archives incl. the nested `tar.gz` reader, obs-G1/obs-G8; JSON and UTF-8; tamper matrix and deposits; reordering; display through `quote_untrusted`) | Four findings in **phase-11 code**, routed to the orchestrator and pinned as strict xfails: F-12C-03 (**Medium**, datasheet labels unescaped for Markdown/HTML), F-12C-04 (Low, `stats` labels), F-12C-01 and F-12C-02 (Low, `chain` reconciliation of self-consistent forgeries the root digest detects). Recommend: Q.15 accepted, **F-12C-03 fixed before any release or deposit** (it is in every published datasheet) |
| Q.15 process controls in CI | **MET (local only)** | dependency scanning, pinned-fetch hardening and the interpreter guard are CI steps and documented (threat model §6) | GitHub Actions has refused to start jobs since 2026-10-09 (billing). A manual dispatch is needed once it runs again |
| **Q.15a** interpreter policy | **MET** (O-2 resolved: D-62) | `requires-python`, `.python-version`, CI floor step, no override flag; release-mode refusals for import, `package --deposit` and `verify --release` proved | **O-2:** `package` *seal* mode does not call the guard. It opens no archive (proved), and the deposit builder refuses, but K.12.12(2) names `package`. Decide: narrow the spec wording, or add the guard to seal mode (phase-11 code, orchestrator). No security property depends on the choice |
| **Q.16** no secrets or corpora in Git | **MET (local)** | gitleaks re-run 2026-10-12 over all 389 commits: two false positives (execution ids containing "api"/"key"), allowed by an anchored entry; then no leaks. `.env` ignored and never committed; no corpus or raw store tracked | CI job `secrets` not run since 2026-10-09 |
| **Q.17** locks and osv-scanner | **MET (local), re-run pending** | `uv lock --check` passes in all five projects (2026-10-12); osv-scanner scans all four locks in CI | osv-scanner was last run on 2026-10-11 (one accepted advisory, `nltk`, until 2027-01-11). It queries the OSV service, so a re-run needs **your yes for network use**. No lockfile changed since 2026-10-08 |
| **Q.31** agent hygiene | **MET** | attributes, search ignores and deny rules tested; `inspect` shows content only with `--show-content`, fenced (phase 12c) | — |
| Deliverables (fuzz and security suites, boundary and extras tests, the three docs) | **MET** | `tests/security`, `tests/fuzz` (incl. the `dtap` reader and the tar parser), `tests/property`, `tests/boundary`, `tests/repo`; adapter guide (12a), threat model and roadmap (updated by 12b for D-54–D-61) | — |

Full local run on the merged branch: **6,063 passed, 107 skipped, 7 xfailed** (the 7 are F-12C-01 to F-12C-04);
`ruff`, `mypy`, the Unicode check and `uv lock --check` pass. The golden and gate-D digest tests pass, so no AER, SEM or
PROV byte moved.

## 2. What phase 12b changed (for the record)

D-53 Hugging Face dataset git pins; D-54 no lazy fetch, absent blobs refused; D-55 a declared, bounded memory cap per job
kind (`prov` 4 GiB, ceiling 16 GiB); D-56 `:` in member labels (D-91); D-57 the nested `tar.gz` reader (D-90); D-58
streaming `expand`; D-59 selection-pattern bound (F-08); D-60 expand budgets calibrated; D-61 tombstoned digests blocked
at ingest (F-12C-05). D-62 is unused. Reports: `prov-rss.md`, `expand-calibration.md`, `d90-recommendation.md`,
`routing-12b.md`.

## 3. Before `phase-12b` is merged into `main` (your call)

1. **No import may be paused.** Every `src/` change moves the stage identities, and the expand bundle (D-56–D-59) moves
   the `expand` `fn_digest` (`regen-batch.md`, "Phase 12b `expand` bundle"). No stored member row changes; only the
   four `ast-survey-agentharm*` corpora hold members.
2. The pre-merge checks are run again on the then-current `origin/main`.
3. Merge and push only on your instruction.

## 4. Open items that are not phase 12b's code

| Item | Owner | Note |
|---|---|---|
| F-12C-01..04 | orchestrator (`corpus/verify.py`, `corpus/datasheet.py`, `stats/`) | F-12C-03 is the one to fix before a release |
| P-1, P-2 (`chain` reconciliation of orphan and copied files), P-3 (no release path after a purge) | orchestrator | P-3 fails closed: a purged corpus cannot be sealed |
| R12b-1 per-run `--prov-memory-cap` flag and its record (user-approved) | orchestrator (`cli/`, importer, `derive`) | the pool side exists (`WorkerLimits.kind_rss_bytes`, `caps_record()`) |
| R12b-2 tier 4 parses PROV-JSON under the 64 MiB untrusted-input cap | validator owner | blocks validation of DTap runs with > 64 MiB of PROV |
| R12b-3 DTap `pii-4` derives 991 MB of PROV | validator / prov owner | needs a leaner validator or a disclosed exclusion |
| R12b-5 the importer never requests level 2 (nested patterns) | phase 10d / importer owner | needed before the Zenodo AgentDojo deposits can be imported |
| R12b-6 register a new tombstoned candidate instead of mapping it | importer owner | resumes are already correct |
| Spec drift recorded by 12c (several snapshots per corpus in H.7.2, H.4.2, MN N.2.2) | spec owner | the code follows D-35 |
| Structure scan of Zenodo 23138310's three `tar.gz` containers | phase 10d, with your yes for the download | unsupported headers are refused with a typed code either way |
