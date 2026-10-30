# User-facing documentation review before v0.1.0

Date: 2026-10-30, Mac Studio. Branch `claude/docs-review-v010-0a7f3d`, based on `118db8d7`, with `origin/main` merged
up to `9018f11a`. The README's badge row and centred tagline are kept exactly as they are on main. Class 0: docs only.
No code, generated block, corpus or decision file was changed. Nothing was pushed.

**Scope.** These files were reviewed:
- `README.md`;
- every chapter of `docs/user-guide/`;
- `site/index.html`;
- `docs/release-notes/v0.1.0.md`;
- `CITATION.cff` and `THIRD_PARTY_NOTICES.md`;
- the `mkdocs.yml` navigation.

`docs/architecture/` was checked only where these files link into it.

**Method.** Every command and flag in the guide was compared with `agentprov <cmd> --help`, for all 64 commands and
subcommands. Defaults, codes and file names were checked in `src/`, `capture/` and `backends/`. The desktop app
chapter was checked against `gui/src/agentprov_gui/`: its menus, panes, labels and step lists. The registry samples
were re-run with `agentprov info` and `info agentdojo` against a scratch `AGENTPROV_HOME`. The backend environment
markers were read under `~/.agentprov/envs` (read only). External links were read but not fetched. Every screenshot
was compared with the code and with the scene in `gui/tools/screenshots.py`.

**Checks on the head.**
- `tools/check_unicode.py`: clean.
- `ruff check .`: clean.
- `uv sync --frozen --group docs`, then `mkdocs build --strict`: passes.
- `tests/repo`: 170 passed.
- `gui/tests/test_g5_*` (they read the notices): 37 passed.
- `gen_docs.py`, `gen_readme_corpora.py`, `gen_readme_sources.py`, `gen_user_guide_cli.py` and `regen_pins.py --check`:
  all current.
- Claims lint (`lint_text`) over every touched file: no new findings. Four findings from before this review remain
  (question Q1).

**Release facts checked.**
- 52 sealed corpora at 0.1.0: round 1's 8 at `8bb6bc92`, wave 2's 43 at `c0e711f4`, DTap at `3000b220`.
- 417,898 released executions.
- Tags are `corpus/<id>/v0.1.0`.

Chapter 14 and the README agree with these. No in-scope text says the corpora are unsealed. Every "not sealed"
statement refers to live working corpora, which is correct.

## 1. Findings by file

Status: **fixed** on this branch, or **open** (see section 3).

### README.md

| # | Finding | Status |
|---|---|---|
| R-1 | The quick start began with a plain `uv sync`, and its import used `--fetch` with an empty cache, so it stops with `raw.fetch.not_cached`. It now runs `uv sync --frozen --group docs` and adds the one `agentprov fetch --profile agentdojo-upstream --pin 2024-06 --allow-network` step first | fixed |
| R-2 | The quick start's `package` line implied that sealing needs nothing more. Its comment now points to chapter 5's requirements (the spec and the release scan) | fixed |
| R-3 | "The copyleft fixtures in `tests/` … will be removed or replaced before any public release" was stale since D-945 (synthetic fixtures). It now says so, and that restricted-use fixtures stay in the development repository (D-943) | fixed |
| R-4 | It said backend environments are "built offline". They are built offline from the uv cache unless `--allow-network` is given | fixed |
| R-5 | It said the Zenodo uploader "start[s] from the same job runner". It runs in the terminal pane of Package › Create Zenodo drafts (`zenodo_run.PtyRun`), not as a job | fixed |
| R-6 | The BibTeX differed from `CITATION.cff` and the landing page (title "an execution-provenance framework…", key `agentprov_2026`). It now matches them and names `CITATION.cff` | fixed |
| R-7 | The development section showed `pytest -n 10`, which is machine-specific. It now shows `-n <workers>` and says that `ci_local.py` picks the count from the host. Its `uv sync` is now `uv sync --frozen` | fixed |
| R-8 | Links to `AGENTS.md` (lines 25, 301, 347) and `CLAUDE.md` (line 301), and a mention of "AGENTS.md §8" (line 323). These files are not in the public export | open, Q2 |
| R-9 | Pre-release wording that becomes wrong at R: the status quote, "Read it on GitHub for now", "No Linux or Windows bundle is released yet", "There is no DOI yet", "Next: … the v0.1.0 release", "Still waiting: the user guide's website" | open, Q4 |
| R-10 | Three claims-lint findings from before this review: the heading "Reproducibility" (271), "a seed does not make them reproducible" (273), "graphs remain reproducible byte for byte" (355) | open, Q1 |
| R-11 | The badges link `https://w3id.org/agentprov/#corpora`, `#cite` and `/docs/`. These resolve to the website only after the w3id pull request (go-live step 7); until then w3id's root serves the agentprov-ns landing page | open, Q3 |
| R-12 | The G5 clean-machine result is stated three times (Platforms, Desktop app, Status and roadmap) | open (minor) |

The generated sources table is current, and its counts agree with the registry (51 sources, 69 parts). The 13 AER
record kinds were checked against `RECORD_KINDS`.

### docs/user-guide/ (hand-written parts)

| # | File:line | Finding | Status |
|---|---|---|---|
| G-1 | README.md (guide home) "Website" | The preview command was `uv sync --group docs`; it is now `--frozen --group docs`. The "goes live only when the repository is made public" text is release-day wording | fixed; wording open, Q4 |
| G-2 | 01:34 | The install command was a plain `uv sync`; it is now `uv sync --frozen --group docs` | fixed |
| G-3 | 01:60–62 | The sample `info` output lacked `zenodo: yes` and printed `~` where the CLI prints `<home>` (`cli/common.py`) | fixed |
| G-4 | 01:97 | The docs group command now includes `--frozen` | fixed |
| G-5 | 01:119–127 | The `AGENTPROV_HOME` table lacked `jobs/`, `calibration/`, `tmp/`, `models-cache/`, `cache/git-history/` and `model-digests.jsonl` | fixed |
| G-6 | 01:66–67 | The sample host is the old MacBook (12 cores, 32 GiB, darwin 27.0.0) | open, Q11 |
| G-7 | 01:84–89, 06, 07, 10 | `uv sync --extra X` drops the docs group, which section 01:100 warns about. The extra commands were left minimal | open, Q15 |
| G-8 | 02:20 | Pinned origins also include URL files (`ORIGIN_KINDS`, `dca-agentdojo`) | fixed |
| G-9 | 02:107 | The rule catalogue `aprov` is at version 3 (D-930); older corpora record 2 | fixed |
| G-10 | 02:38–39 | "byte-identical … on any machine" claims more than was tested (01:18–23) | open, Q8 |
| G-11 | 03:21–30 | In the `info` sample, the registry date (2026-10-11 → 2026-10-30), the DTap row (planned → supported [18]) and caveat [2]'s seal text were out of date | fixed |
| G-12 | 03:53–62 | The `info agentdojo` sample lacked the `sealed:` lines | fixed |
| G-13 | 03:37 | The definition of `partial` contradicted the sealed `partial` parts. It now matches the README's definition | fixed |
| G-14 | 03:318 | The refusal example named DTap, which is now supported. It now uses `agentdyn · history` (re-run: exit 5) | fixed |
| G-15 | 04:21, 10:273 | "a dry run (`derive` …)" now reads `derive --dry-run` | fixed |
| G-16 | 04:52 | The drift example now reads "catalogue aprov v2 recorded, v3 current" | fixed |
| G-17 | 04:225–226 | "That built-in default is due to rise after the round-1 seal" is pre-seal wording | open, Q7 |
| G-18 | 04:219, 10:219 | "32 GiB on the Mac Studio", but `compute.validation_cache_gib` is 64 on this machine | open, Q11 |
| G-19 | 04:64, 04:97, 14:218 | "reproduce" is used for re-derivation | open, Q12 |
| G-20 | 05:412–413 | It said the collection trial had not run on the sandbox; it ran on 2026-10-29 (`zenodo-sandbox-trial.md`) | fixed |
| G-21 | 06:76 | The `stats --select` keys lacked `issue`, `cell.<member>` and `outcome.<claim>` | fixed |
| G-22 | 06:165–166 | `render.graph_too_large` now gives exit 1. The render-inside-a-corpus error is `render.output_in_corpus`, not `corpus.sealed` | fixed |
| G-23 | 07:17, 07:921 | `rope · head` has no backend, so `run rope` exits 5 ("no live capability"), even with `--llm-script`. The refusal text is corrected | fixed |
| G-24 | 07:77–90 | The environment table listed the removed `agentdojo-79922295` and build dates of 2026-10-22. The four markers say 2026-10-28 10:23 | fixed; inventory open, Q11 |
| G-25 | 07:404–405 | It said the run's notice still uses the pre-seal text; the registry caveat has been updated | fixed |
| G-26 | 07:768–769 | WhistleBench and ATIA are `supported` and sealed in wave 2, not `planned` | fixed |
| G-27 | 07:248, 370, 388–391 | "measured" is used for the preset calibration | open, Q9 |
| G-28 | 07:897–902 | The reason given for not sealing live corpora differs from `docs/roadmap.md` and D-991 | open, Q10 |
| G-29 | 08 (desktop app) | Fixed against the code:<br>- the shortcuts: ⌘L, ⌘N, ⌘R, ⌘1–⌘6, ⌃⌘S, Text Size; Settings and About in the app menu on macOS;<br>- where the Qt toolbar and the job count sit;<br>- the Corpora columns;<br>- "Close Tab";<br>- the viewer-aer caption (the row shown is attack succeeded: no);<br>- the dev-run plan (60 parts, 180 steps, last part `yockcheng-…`; re-run);<br>- the Live Dev Run folder and caps;<br>- the New Job form "Build a collection index deposit" (D-947);<br>- the API cap fields' visibility;<br>- the Package step 1 preconditions;<br>- steps 2–4 after sealing;<br>- the index umbrella line in the Deposits format;<br>- the Keys caption;<br>- the Estimate caption;<br>- the `.dmg` name | fixed |
| G-30 | 08:43–47 | "No released bundle exists yet" (three rows) is release-day wording | open, Q4 |
| G-31 | 08:49 | "released with that label (D-750) until they have been tested on clean machines" refers to no label any more, and the bundles have been tested | open, Q4 |
| G-32 | 08:420–450 | D-949's "Cross-link drafts?" question, and the rule that a collection is drafted from the terminal, are not described | open, Q5 |
| G-33 | 09:45–46 | The key sources lacked `--env-stdin` (the desktop app) | fixed |
| G-34 | 09:155, 01:20 | "The repository is private" | open, Q4 |
| G-35 | 10:266 | The sample `info` path was `~`; the CLI prints `<home>` | fixed |
| G-36 | 12:73, 12:83, 14:21–24 | The issue code is `map.earlier_attempts_unobservable`, and URL pins were missing from the Pin entry and the chapter 14 bullet | fixed |
| G-37 | 15 (generated) | It covers round 1's 8 corpora under their local tree names (`…-rg1`, `…-rg2`), not all 52, and its header says "regenerate after wave 2" | open, Q6 |
| G-38 | `_findings.md` | Rows F-17 and F-18 have swapped status: F-18 is fixed in code (`package.py`), F-17 is not | open, Q14 |
| G-39 | `_go-live.md`, `_findings.md` | Internal checklists inside `docs/user-guide/`, with a stale status (2026-10-28) | open, Q14 |
| G-40 | 13:78 | "index.html, landing page of https://w3id.org/agentprov/" changes after the w3id pull request | open, Q3 |

Chapters 11 and 14 (generated) are current. Every flag in every `agentprov …` example exists on its parser. Every
relative link and anchor resolves (mkdocs strict, plus a link check of the GitHub-form links into the repository). No
guide chapter links an agent file; 09:40 only names them as files that third-party clones may carry. The catalogue
counts in 07:168–172 were not re-checked, because `--catalogue` starts the worker.

### site/index.html

| # | Finding | Status |
|---|---|---|
| S-1 | It said "Four live backends record runs as `capture/0.1`", but the Inspect harness keeps Inspect's own log (`by: source`; 07:36–42). It now says that AgentDojo, AutoDojo and AgentDyn record `capture/0.1`, and that an Inspect harness runs AgentHarm and keeps Inspect's log | fixed |

The rest checks out against the code:
- the app tour: 12 tabs at most, the Runs controls, the R0/R1/R2 tier texts, the nine Package steps, the CLI lines
  (`stats --select`, `render --ex`, `inspect --view sem|records`);
- the downloads, the first-launch text, the coverage phrase (generated) and the BibTeX.

The site's links are relative (`docs/…`) or GitHub release URLs, plus `https://w3id.org/agentprov/ns`.

### docs/release-notes/v0.1.0.md

| # | Finding | Status |
|---|---|---|
| N-1 | Live capture listed only the three `capture/0.1` backends; the AgentHarm Inspect harness was missing. It is added (Inspect's own log); the D-991 sentence is unchanged | fixed |
| N-2 | The website URLs are `nickjones39.github.io/AgentPROV/…`, while the README uses `w3id.org/agentprov/…` | open, Q3 |

The placeholders `<SOFTWARE_DOI>`, `<UMBRELLA_DOI>`, `<R>` and `<LISTING_SHA256>` are left as they are.
`tests/repo/test_release_notes.py` passes.

### CITATION.cff

| # | Finding | Status |
|---|---|---|
| C-1 | The keyword `reproducibility` is flagged by the claims lint (AR-12) | open, Q1 |

The version, licence, author, ORCID (check digit valid) and title agree with the site's BibTeX.

### THIRD_PARTY_NOTICES.md

| # | Finding | Status |
|---|---|---|
| T-1 | "Small test fixtures derived from these sources are kept only in the private repository" contradicted D-943. Permissive fixtures are in the public tree; the restricted-use ones stay private, and their tests skip | fixed |
| T-2 | The live backends listed only `agentdojo` and `autodojo`. Added: AgentDyn at `5353cf76` (MIT); and for the Inspect harness, `inspect-ai` 0.3.263 and `inspect-evals` 0.20.0 (MIT, read from the environment's metadata), plus the AgentHarm dataset at `e23b3fe6` (MIT with its use clause) | fixed |
| T-3 | No pointer to the desktop bundles' notices (Qt/PySide6, LGPL-3.0). Added a link to `gui/THIRD_PARTY_NOTICES.md` | fixed |
| T-4 | The data table lists only the sources known on 2026-10-07; about 25 registered and sealed sources are missing (AgentHarm forks, WhistleBench, ControlArena, ATIA, OpenAgentSafety, RedCode, MCPHunt and others). A pointer to the generated tables was added | partly fixed; open, Q13 |

### mkdocs.yml

The navigation lists all 15 chapters and the home page in order, and matches the files and the guide home's contents
table. The `_*.md` files are excluded. `site_url` is the github.io form (Q3). No finding.

## 2. Screenshots

The scene script (`gui/tools/screenshots.py`) still matches the code. None were re-shot: re-shooting means running the
GUI screenshot pass, which is not a trivial edit.

| Image | State | What differs |
|---|---|---|
| `docs/user-guide/images/gui/licences.png` | **stale** | Parts that are now `supported` show as `planned` (yockcheng, whistlebench, what-surrounds, tacit, shreeyavarma, sentry, seagent, redcode-exec-qwencode and -openhands, openagentsafety) |
| `docs/user-guide/images/gui/package-finish.png` | **stale** | Opens "The deposit is built and verified…"; the code now opens "Nothing has been uploaded. Once step 8 has built and verified the deposit, …" (F-18) |
| `docs/user-guide/images/gui/zenodo-drafts.png` | **stale** | The Deposits placeholder lacks the index-umbrella line (D-947) |
| `docs/user-guide/images/gui/settings-appearance.png` | **stale** | The label says "(macOS; takes effect at the next start)"; the code says "(takes effect at the next start)" |
| `docs/user-guide/images/gui/settings-dev-runs.png` | **stale** | The plan says "10 parts, 50 executions … rope/head"; the defaults now give 60 parts and 300 executions, ending at `yockcheng-prompt-injection-harness/head` |
| `docs/user-guide/images/gui/system.png` | current against the code | Shows the old MacBook (12 cores, 32 GiB), not the Mac Studio |
| `docs/user-guide/images/gui/about.png`, `settings-ci.png` | current against the code | Show "nickjones39/AgentPROV (private)" and "private repository" (code strings; Q4) |
| `docs/user-guide/images/gui/run-live.png`, `run-live-models.png` | current, clipped | The right edge is cut off (part of the containment note; the Identity… button) |
| `docs/user-guide/images/gui/settings-compute.png` | current against the code | Shows "Test gate workers (pytest -n) 10", which nothing reads (F-17; Q5) |

All the other images used by chapter 8 and the README are current: viewer-graph, viewer-tabs, viewer-outcomes,
viewer-aer (its caption is fixed), runs-jobs, runs-batches, new-job, run-live-estimate, model-identity, logs, package,
settings-general, -viewer, -jobs, -keys, -local-models, -prices, -estimate and -zenodo, and
`docs/images/gui/agentprov-app.png`.

## 3. Questions for the user

All fifteen were answered on 2026-10-30; section 4 records the decisions and what was done.

- **Q1. Claims-lint findings from before this review.** They are left as they are, because they are claim wordings.
  The proposals:
  - README "## Reproducibility" → "## Derivation and execution reproducibility";
  - "a seed does not make them reproducible" → "a seed does not make them repeat exactly";
  - "AgentDojo-PROV graphs remain reproducible byte for byte" → "remain derivation-reproducible byte for byte";
  - the `CITATION.cff` keyword `reproducibility` → `derivation reproducibility`.

  Chapter 14:158 is a third-party paper title in the generated block, so it is a false positive.
- **Q2. Agent-file links in the README (P-3a).** The proposal:
  - line 25: "decisions are in [`DECISIONS.md`](docs/architecture/DECISIONS.md)", with no AGENTS.md;
  - line 301: "Read the specification ([`docs/architecture/`](docs/architecture/)) and [`docs/adapter-guide.md`](docs/adapter-guide.md) before changing anything";
  - drop "AGENTS.md §8 describes the multi-session workflow rules";
  - line 347: "the open decisions are in [`DECISIONS.md`](docs/architecture/DECISIONS.md)".

  Shall I apply this, or does P-3a's own scrub do it?
- **Q3. One URL form for the website.** The README uses `w3id.org/agentprov/…`. The release notes, the guide home and
  `mkdocs.yml`'s `site_url` use `nickjones39.github.io/AgentPROV/…`. The w3id root moves to the website only at go-live
  step 7, so until then the README's badges lead to the agentprov-ns landing page, and chapter 13:78 is stale after it.
  Which should be canonical?
- **Q4. Release-day wording.** These go stale at R:
  - README: R-9;
  - guide home: "Website";
  - chapter 8: "No released bundle exists yet" (×3) and the D-750 sentence at 08:49;
  - 01:20 and 09:155: "repository is private" (and 09:155 needs a public contact route for security reports);
  - the GUI strings "nickjones39/AgentPROV (private)" (`about.py`, `package.py` Finish) and Settings › CI's "private
    repository".

  Should these change in the release commit (step 5 of the v0.1.0 plan), with the text drafted now?
- **Q5. GUI behaviour that the chapter documents but the code does not do** (code fixes, not doc fixes):
  - F-17: `compute.gate_n` is read by nothing.
  - `compute.preset` is ignored by Run Live's Tune, which uses `--m5ultra` unless More Options says otherwise.
  - `compute.start_stagger` is read by nothing.
  - Preflight Only… on an API endpoint puts the caps into the argv, which the CLI refuses (exit 2, `run.py:1937`). This
    looks like a bug; it was not run.
  - The GUI's preflight text says "one probe call", but the CLI makes up to three.
  - The More Options labels "live once calibrated; D-823" are stale (m5ultra v2 is calibrated).
  - The `gui/pyproject.toml` comment asks for Qt ≥ 6.12.1, but the lock pins 6.12.0.
  - `render`'s `EXTRA_HINT` is `uv sync --extra render`, which drops the docs group.

  Also: should chapter 8 describe D-949's cross-link question (G-32)?
- **Q6. Chapter 15.** Regenerate it over all 52 sealed corpora, and show corpus ids instead of local tree names?
- **Q7. The tier-4 cache default (04:225).** Is the class-1 raise after the round-1 seal still planned? If not:
  "**Unset:** the cache keeps its built-in 2 GiB; the setting is how a machine gets more."
- **Q8. The scope of 02:38–39** ("on any machine and with any number of workers"), given that only macOS is tested.
- **Q9. D-991 and "measured".** Is "measured" exempt for the preset calibration vocabulary in chapter 7?
- **Q10. Live sealing (07:897–902).** Align its reason with the roadmap and D-991 (planned for v0.2, needs
  `agentprov-corpus/0.3`)?
- **Q11. Machine-specific values in the public guide:**
  - the environment inventory and build times (07:73–90);
  - the cache size (04:219, 10:219);
  - the sample host (01:66).

  Keep these, generalise them, or update them to the Mac Studio?
- **Q12. "Reproduce" for re-derivation** (04:64, 04:97, 14:218). Change it to "re-derive" or "derivation-reproducible"?
- **Q13. THIRD_PARTY_NOTICES's data table.** Expand it to every registered source (from the registry's SPDX ids, with
  the licence basis checked per source), or keep the pointer added here?
- **Q14. The guide's internal `_go-live.md` and `_findings.md`.** Leave them out of the public export (they are
  orchestrator checklists), and fix the swapped F-17/F-18 rows?
- **Q15. Extra-install commands.** Write them as `uv sync --frozen --group docs --extra X` throughout, so that they
  agree with 01:100?

## 4. The user's decisions (2026-10-30) and what was done

The user approved the recommendations for Q1–Q15 ("Yes: go with your recommendations for Q1–Q15") and then asked for
Q16 (no planned work in the README) and Q17 (the README's live label), all relayed by the orchestrator. The second
commit series on this branch carries them out.

| Q | Decision | Done |
|---|---|---|
| Q1 | Apply the four rewordings | The README heading is now "Derivation and execution reproducibility", "repeat exactly" and "derivation-reproducible byte for byte"; the `CITATION.cff` keyword is now `derivation reproducibility`. 14:158 stays (a false positive) |
| Q2 | No README links to agent files | Done. The README now points to `DECISIONS.md`, the specification and the adapter guide |
| Q3 | `https://w3id.org/agentprov/` is canonical | The release notes, the guide home and `mkdocs.yml` `site_url` (and its test) use the w3id form, docs at `/docs/`. Chapter 13 now says the agentprov-ns site serves the `/ns` and `/exec` IRIs, while `https://w3id.org/agentprov/` leads to the project website. `_go-live.md` step 6 keeps the github.io address, because it checks the Pages deployment itself |
| Q4 | Draft the wording now, apply it in the release commit | Section 5 below |
| Q5 | Fix the GUI code, with tests | Run Live: Preflight Only… no longer needs the caps and passes none (`preflight_settings`, `CAP_KEYS`). Its confirmation and consent name the probe's bound, up to `PROBE_CALLS` = 3 calls, and a full run's confirmation says the probe's calls are charged to the caps. New test: `gui/tests/test_g3_live.py::test_preflight_only_on_an_api_endpoint_needs_no_caps_and_passes_none`. The More Options labels are now "Host preset (D-822, D-823)" and "m5ultra preset (calibrated, version 2; D-823)". `EXTRA_HINT` and `render --help` now read `uv sync --frozen --group docs --extra render` (the two core tests are updated, and chapter 11 is regenerated). The `gui/pyproject.toml` comment now matches the lock (6.12.0). Chapter 8's Compute caption says that `compute.gate_n` and `compute.start_stagger` are stored but not used yet (planned for v0.2; roadmap line added), and that `compute.preset` is read by `agentprov estimate`. G-32 is not added |
| Q6 | Regenerate chapter 15 over the 52 sealed corpora, by corpus id | `tools/gen_corpus_artefacts.py` now heads and orders each corpus by its corpus id, and refuses two sealed trees with the same id. The page was regenerated from `agentprov stats --artefacts` over all 52 sealed trees (run through the machine queue, class rehearsal, 1 CPU) |
| Q7 | Document the current behaviour | 04: "**Unset:** the cache keeps its built-in 2 GiB; the setting is how a machine gets more." |
| Q8 | Narrow 02:38–39 | It now says "across runs, processes and worker counts. This is tested on macOS on Apple silicon; other platforms are untested" |
| Q9 | "measured" stays | Unchanged: it refers to the machine calibration, not to live results (D-991) |
| Q10 | Align live sealing with the roadmap | 07 now says it is planned for v0.2 and needs `agentprov-corpus/0.3` with a closed live block, with a link to the roadmap |
| Q11 | Generalise the machine-specific values | 01 (sample host), 04 and 10 (cache cap, queue slots, host default, workers, the volume setup) and 07 (environment inventory) now say "for example, on one development machine". The README's calibration sentence no longer names the hardware. The report path `docs/reports/mac-studio-calibration/` and the preset name `m5ultra` are identifiers and stay |
| Q12 | "reproduce" → "re-derive" | 04:64, 04:97 and 14:218 |
| Q13 | Keep the pointer; add a v0.2 roadmap line | `docs/roadmap.md`, "Planned for v0.2" |
| Q14 | Leave both files out of the public export; fix the rows | Added to P-3a in `public-repo-plan.md`. In `_findings.md`, F-17 is open (planned for v0.2) and F-18 is fixed (its screenshot is still stale) |
| Q15 | `uv sync --frozen --group docs --extra X` throughout | 01, 06, 07 and 10. The core's hint for the `live` extra (`cli/run.py`, "run: uv sync --extra live") is not changed, because the decision named only `EXTRA_HINT`; it is left for the user |

| Q16 | The README lists only what this release has, and no planned work (README only) | `tools/gen_readme_sources.py` lists the parts in a sealed corpus and the `partial` live parts (`shown()`, from the registry's own fields); its summary reads "The 50 sources and their 64 parts with a sealed corpus or a tested live backend". Planned, owned-elsewhere, compat-oracle and toy parts, and the `foobench` sentence, are gone from the README (they stay in `agentprov info`, chapter 14 and the roadmap). The prose no longer has "pre-release", "for now", "yet", "will", the "Next:" and "Still waiting:" lines, "in v0.1" or the link to `docs/roadmap.md`. The legend defines only the statuses shown. `tests/repo/test_readme_sources.py` checks the filter. Chapter 14's generator is unchanged |
| Q17 | A `partial` live part reads "live (tested subset)" in the README only | `LIVE_LABEL` in the README generator. The legend and the Live backends paragraph say that the scripted live gate passes and that real-model runs are admitted only for the subset the caveat declares (D-720). The registry, the guide, the spec and the claims vocabulary keep `partial`. New test: `test_a_partial_live_part_reads_live_tested_subset_in_the_readme_only` |

Left for later:
- The CLI's own refusal text "--preflight-only is one model call; the caps belong to a campaign" (`cli/run.py`,
  quoted at 07:522) still says "one model call", while the probe makes up to three. It is core CLI text, outside the
  GUI fix.
- `.github/workflows/pages.yml` and D-760 name `docs/user-guide/_go-live.md`, which the public export now leaves out
  (P-3a's scoping pass).

## 5. Release-day wording (Q4): drafted, apply in the release commit (plan step 5)

Each entry gives the current text and its replacement. `<SOFTWARE_DOI>` and `<UMBRELLA_DOI>` are the release plan's
placeholders, filled at the same step.

**README.md: applied under Q18, not drafted.** The user asked for the README to be in its released state now. The
README is exported to the public repository, which goes public only after the Zenodo records are published (release
plan steps 11–12), so every public reader sees the past tense when it is true. Until then, the private development copy
describes the release as done; that is not a claim about the private repository's present state. The README adds no
`<SOFTWARE_DOI>` or `<UMBRELLA_DOI>` placeholder: it links `https://w3id.org/agentprov/#corpora`, and the badge row's
`<SOFTWARE_DOI>` (two places) is still the only one, as release plan step 5 expects.

The items below stay drafts, to be applied in the release commit (plan step 5).

**docs/user-guide/README.md, "Website"**

- now: "This guide is also built as a website at <https://w3id.org/agentprov/docs/>, under the project's landing page
  at <https://w3id.org/agentprov/>. The site goes live only when the repository is made public, on the project owner's
  instruction. Until then, read the guide here on GitHub, or preview it on your own machine: `uv sync --frozen --group
  docs`, then `uv run --group docs mkdocs serve`, which serves it at <http://127.0.0.1:8000/docs/> only."
- replace with: "This guide is also a website at <https://w3id.org/agentprov/docs/>, under the project's landing page
  at <https://w3id.org/agentprov/>. To preview a change on your own machine: `uv sync --frozen --group docs`, then
  `uv run --group docs mkdocs serve`, which serves it at <http://127.0.0.1:8000/docs/> only."

**docs/user-guide/08-desktop-app.md, the platform table and line 49**

1. Linux aarch64:
   - now: "No released bundle exists yet: the manual-dispatch workflow `bundles.yml` has not been dispatched (Actions
     billing, D-431)"
   - replace with: "Released with v0.1.0 as `AgentPROV-linux-aarch64.tar.gz`"
2. Linux x86_64:
   - now: "No released bundle exists yet (`bundles.yml` not dispatched)"
   - replace with: "Released with v0.1.0 as `AgentPROV-linux-x86_64.tar.gz`"
3. Windows x86_64:
   - now: "No released bundle exists yet (`bundles.yml` not dispatched)."
   - replace with: "Released with v0.1.0 as `AgentPROV-windows-x64.zip`."
4. Windows ARM64 (it carries no such sentence today): add "Released with v0.1.0 as `AgentPROV-windows-arm64.zip`."
   after its report link, so that all four rows agree.
5. Line 49:
   - now: "The non-macOS bundles are released with that label (D-750) until they have been tested on clean machines."
   - replace with: "Each release bundle carries its `bundle-report.json` (its checks, interpreter, glibc floor, signature
     and sha256). The Linux and Windows bundles have passed the clean-machine tests above (D-750, G5); the x86_64 ones
     were tested under emulation."

**docs/user-guide/01-install.md, line 20**

- now: "(D-431: manual dispatch only, blocked by Actions billing while the repository is private)"
- replace with: "(D-431: manual dispatch only)"

**docs/user-guide/09-safety.md, line 156**

- now: "The repository is private. Report a security problem to the maintainer directly, not in an issue that quotes
  the payload."
- replace with: "Report a security problem privately, through GitHub's private vulnerability reporting on
  [`nickjones39/AgentPROV`](https://github.com/nickjones39/AgentPROV/security/advisories/new) (the repository's
  Security tab, *Report a vulnerability*), never in a public issue, and never quote a payload in an issue."
- Owner step: enable *Private vulnerability reporting* in the public repository's settings (Settings › Code security).

**The desktop app (code strings; apply with tests, then re-shoot `about.png` and `settings-ci.png`)**

1. `gui/src/agentprov_gui/about.py:25`:
   - now: `REPOSITORY: Final = "nickjones39/AgentPROV (private)"`
   - replace with: `REPOSITORY: Final = "nickjones39/AgentPROV"`
2. `gui/src/agentprov_gui/ui/package.py:557` (Finish):
   - now: `"\n\nRepository: nickjones39/AgentPROV (private). No link, no upload."`
   - replace with: `"\n\nRepository: nickjones39/AgentPROV. No upload."`
3. `gui/src/agentprov_gui/ui/settings_panes.py`, Settings › CI:
   - line 283, now: `"gh workflow run ci.yml --ref <branch> (R2: network, spends Actions minutes of a private repository)"`
   - replace with: `"gh workflow run ci.yml --ref <branch> (R2: network; runs on GitHub's hosted runners)"`
4. Line 287, the label:
   - now: `"Mac Studio runner (CI_RUNNER)"`
   - replace with: `"Self-hosted runner (CI_RUNNER)"`
   - also the accessible name on line 288 (`"Mac Studio runner"` → `"Self-hosted runner"`) and `TARGETS["mac-studio"]`
     (line 270, `"Mac Studio (self-hosted)"` → `"Self-hosted runner"`). The key `mac-studio` stays (it is a stored
     setting value).
5. The module docstring (line 15), "the Mac Studio runner (``CI_RUNNER``…" → "the self-hosted runner (``CI_RUNNER``…".

## 6. Q18: the README in its released state

The user asked for the past tense, because the release is imminent, and then for a sweep of the whole README ("check
the rest of readme for changes like this that are needed"), relayed by the orchestrator. The reasoning is the one in
section 5's note: the public README is seen only after publication.

These sentences were already changed under Q16, before Q18 (no planned or future work):
- "**Status: v0.1, pre-release, under active development.**" → "**Status: v0.1.0.**", which Q18 then changes again
  (item 1);
- "Read it on GitHub for now: its website (`mkdocs.yml`) builds and passes its tests, but goes live only when the
  repository is public." → "…; `mkdocs.yml` builds it as a website." (item 2);
- the "Next: the Zenodo deposit … and the v0.1.0 release." paragraph was removed;
- "Still waiting: the user guide's website, which goes live when the repository becomes public." was removed, together
  with the links to `AGENTS.md` and `docs/roadmap.md`;
- "There is no DOI yet. Until the AgentPROV paper and corpus DOIs exist, please cite the software as below…" →
  "Please cite the software as below (the same record as `CITATION.cff`):" (item 8);
- "(D-431: manual dispatch only, blocked by Actions billing while the repository is private)" → "(D-431: manual
  dispatch only)";
- "Windows has no live runs in v0.1 (D-867)" → "Windows has no live runs (D-867)";
- "Live corpora cannot be sealed yet." → "Live corpora cannot be sealed.";
- "No Linux or Windows bundle is released yet (the `bundles.yml` workflow has not been dispatched)." → "The Linux and
  Windows bundles are built by the manual-dispatch workflow `bundles.yml`." (item 3);
- "corpora will be released separately on Zenodo" → "corpus releases go to Zenodo" (item 4).

Q18's changes, before → after (the text as it stood after Q16):

1. **Status box.**
   - before: "> **Status: v0.1.0.** The design is specified in"
   - after: "> **Status: the v0.1.0 release.** The design is specified in"
2. **Documentation.**
   - before: "examples, the desktop app, safety and troubleshooting; `mkdocs.yml` builds it as a website."
   - after: "examples, the desktop app, safety and troubleshooting. Read it on the website, <https://w3id.org/agentprov/docs/>, or here on GitHub."
3. **Desktop app.**
   - before: "A macOS bundle (signed ad hoc) is built and tested on the development Mac. The Linux and Windows bundles are built by the manual-dispatch workflow `bundles.yml`. The bundles built for the clean-machine tests from `main` pass them:"
   - after: "The v0.1.0 release carries bundles for macOS (Apple silicon, signed ad hoc), Windows (ARM64 and x64) and Linux (aarch64 and x86_64), each with its `bundle-report.json`; see the [release notes](docs/release-notes/v0.1.0.md). The macOS bundle was tested on the development Mac, and the bundles built for the clean-machine tests from `main` passed them:"
4. **Corpus policy and licences.**
   - before: "corpus releases go to Zenodo, and nothing is published automatically."
   - after: "corpora were released separately on Zenodo, one collection with one record per licence class (<https://w3id.org/agentprov/#corpora>), and nothing is published automatically."
5. **Status (the list of what is in v0.1.0).**
   - before: "Done: the specification; the core"
   - after: "v0.1.0 includes the specification; the core"
6. **Status (the sealed corpora).**
   - before: "presets are calibrated on one development machine ([report](docs/reports/mac-studio-calibration/README.md))."
   - after: "presets are calibrated on one development machine ([report](docs/reports/mac-studio-calibration/README.md)). The sealed corpora were deposited on Zenodo as one collection with one record per licence class, released with v0.1.0 (<https://w3id.org/agentprov/#corpora>)."
7. **Status (the desktop bundles).**
   - before: "The clean-machine tests of the desktop bundles are done: every platform passes every applicable step from `main`,"
   - after: "The desktop bundles passed the clean-machine tests: every platform passed every applicable step from `main`,"
8. **Citation.**
   - before: "Please cite the software as below (the same record as [`CITATION.cff`](CITATION.cff)):"
   - after: "Please cite the software as below. [`CITATION.cff`](CITATION.cff) holds the same record with the software's DOI (GitHub: *Cite this repository*), and the badge above links the DOI."

Kept as they are, because they describe the present:
- "pre-release checks", which is the name of the seal-time checks and their reports;
- "the private development repository", which is where restricted fixtures stay;
- "CI has not run since (D-431: manual dispatch only)";
- "Live corpora cannot be sealed.";
- live capture worded as a tested capability (D-991);
- import `partial` (the user's call);
- the live label "live (tested subset)" (Q17).

The claims lint over README.md reports 0 violations. Lines 1–14 (the badge row and the centred tagline) are
byte-identical to main.
