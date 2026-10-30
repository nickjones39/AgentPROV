# Regeneration round: plan and rehearsal (D-350..D-359, proposals)

Status: **the round ran on 2026-10-22 and passed (§7 outcome, `round/README.md`)**; the plan as approved follows.
Written 2026-10-13 by the regeneration-round planning session (branch `regen-plan`, from origin/main `6421c05`). The
rehearsal ran on APFS clones under `~/.agentprov/migration-work/regen-plan/` at `6421c05`; nothing under
`~/.agentprov/corpora/` was written (read-only reads and `cp -c` clones only). Raw run logs, timings and summaries:
`~/.agentprov/migration-work/regen-plan/logs/` (`runs.jsonl` holds one row per measured command). The measurement
wrapper is `tools/regen/measure.py`.

Standing rules that shape the plan: the user approves the fix list and then, separately, the regeneration
([[fixes-before-corpus-regeneration]] in the project memory; `regen-batch.md` preamble); corpora are never rewritten in
place and never deleted (old ones are renamed); the `*.pre-*` corpora are history and are not touched; no data is
excluded for having no successful attack (D-279 addendum, user 2026-10-13); one heavy job at a time on this machine.

## 0. Summary

- **What the round regenerates (default):** the eight working corpora `~/.agentprov/corpora/*-p10.partial`, 126,351
  executions, 38.9 GB on disk, all by a **fresh pinned import** (route (a), user decision 2026-10-13; §3.1), because aer/0.2 and items
  3, 13, 14, 17, 22 move AER bytes in every corpus and a re-map would replay the recorded v1 versions after D-31. No
  network: every input is in the verified fetch cache or the pristine baseline clone. New corpora for `planned` sources are listed (§1.2) but
  are not in the round unless the user asks.
- **Can it start now?** No. Order before the round (user rulings 2026-10-13/14, relayed by the orchestrator; §4):
  (1) the D-31 bumps branch (integer bumps, `rules/archive/`, the semantics versions of D-353, notice-only
  `limits_sha256`); (2) `regen-items-2-12` (items 2, 4-12, U6-a/b/c, D-182, D-372); (3) the remaining code merges
  (RW-1, 10m, 10n, runner D-321/D-323, D-315, ingest-formats-3 with the spool fix P-10, offline `--fetch` P-11);
  (4) aer/0.2 last; (5) the re-rehearsal of §3.5; (6) the round, on the user's separate yes. The performance sessions
  (suite-perf, pipeline-perf, workflow-tools) come first (user priority 2026-10-14) and will change the timings of §5.
- **Rehearsals on clones:** the re-map at `6421c05` on Mandate (396) and ROPE (10,791): deterministic at 8 and 3
  workers, tier 4 and linkage pass, `verify --level chain` clean apart from the working-tree checksum notice. The aer/0.2
  preview on `deferrals-c` (Mandate): clean. Route (a) on Mandate at `c4fd0dc2` through a scratch checkout of the cached
  pin: clean, comparator ids equal. ROPE route (a) paused (8,192 of 10,791 sealed) for the performance sessions.
- **Findings** F-1..F-8 (§6), all routed to the orchestrator and decided or owned; none was fixed here.
- **Estimate for the full round** (8 corpora, one heavy job at a time, machine load as measured): see §5.3.

## 1. Inventory

### 1.1 Corpora to regenerate (the current working corpora)

Read-only scan of `corpus.json`, `derivation.json`, `register.jsonl` and `raw/members.jsonl` of each corpus
(2026-10-13). All eight are working trees (`state: working`, `sealed: false`, `release.status: dev`, `corpus_version`
null), imported in release mode `until = validation`, format `agentprov-corpus/0.1`, `aer/0.1`, `sem/0.1`,
`agentprov-prov/0.1`. Stage digests are the first 12 hex digits of each stage's `fn_digest`.

| Corpus directory | corpus_id · part | Snapshot pin (origin kind) | Executions | Register rows | Members | Source profile · SEM profile | Rules in the `aer` stage | `fn_digest` aer / sem / prov / validation (expand) | Size |
|---|---|---|---:|---:|---:|---|---|---|---:|
| `mandate-agentdojo-eval-p10.partial` | mandate-agentdojo-eval · head | git `fa62a9775849` (local) | 396 | 792 | 0 | mandate-agentdojo-eval@1 · agentdojo.suites@1 | aer, agentdojo, mandate | `0928f3723059` / `e1b6f94665cd` / `8a0c70d71417` / `dd1fcafd5655` | 71 MB |
| `ast-survey-agentharm-p10.partial` | ast-survey-agentharm · agentharm | git `89c4db2c9497` (local; 6 logs) | 1,056 | 62 | 1,691 | survey-agentharm@1 · inspect.agentharm@1 | aer, inspect | `160699a88ec8` / `377c2a051b43` / `8a0c70d71417` / `bf7d0d0b656c` (`1d32304c8db4`) | 309 MB |
| `ast-survey-agentdojo-p10.partial` | ast-survey-agentdojo · agentdojo-runs | git `89c4db2c9497` (local) | 3,243 | 6,555 | 0 | survey-runs@1 · agentdojo.suites@1 | aer, agentdojo, survey | `a7579f0691c2` / `e1b6f94665cd` / `8a0c70d71417` / `dd1fcafd5655` | 752 MB |
| `rope-p10.partial` | rope · head | git `64495e16e640` (local) | 10,791 | 37,594 | 0 | rope@1 · agentdojo.suites@1 | aer, agentdojo, autodojo, rope | `605ce8cee9a1` / `e1b6f94665cd` / `8a0c70d71417` / `dd1fcafd5655` | 4.9 GB |
| `adprov-v1-release-p10.partial` | adprov-v1 · release | git `579a908354b9` (local) | 17,664 | 6,121 | 0 | adprov-v1@1 · agentdojo.suites@1 | adprov, aer, agentdojo | `4566870ecda5` / `e1b6f94665cd` / `8a0c70d71417` / `dd1fcafd5655` | 3.3 GB |
| `agentdojo-upstream-2024-06-p10.partial` | agentdojo-upstream · 2024-06 | git `c274885610ef` (git) | 18,241 | 36,551 | 0 | agentdojo-upstream@1 · agentdojo.suites@1 | aer, agentdojo | `057211531f6e` / `e1b6f94665cd` / `8a0c70d71417` / `dd1fcafd5655` | 3.5 GB |
| `agentdojo-upstream-head-p10.partial` | agentdojo-upstream · head | git `089ed468cf3e` (local) | 36,679 | 75,968 | 0 | agentdojo-upstream@1 · agentdojo.suites@1 | aer, agentdojo | `057211531f6e` / `e1b6f94665cd` / `8a0c70d71417` / `dd1fcafd5655` | 7.5 GB |
| `agentdyn-a-p10.partial` | agentdyn · a | git `5353cf7615b1` (local) | 38,281 | 90,474 | 0 | agentdyn@1 · agentdojo.suites@1 | aer, agentdojo, agentdyn | `768e53c78eda` / `e1b6f94665cd` / `8a0c70d71417` / `dd1fcafd5655` | 14 GB |
| **Total** | | | **126,351** | 254,117 | 1,691 | | | | **38.9 GB** |

Completeness today (`counts.by_completeness`): adprov-v1 14,688 verified / 32 known-incomplete / 2,944 unverifiable;
2024-06 232 / 51 / 17,958; head 232 / 83 / 36,364; AgentDyn 0 / 837 / 37,444; survey AgentDojo 3,243 unverifiable;
AgentHarm 1,056 verified; Mandate 396 unverifiable; ROPE 2 / 322 / 10,467. Per layer (KiB, `du -sk`): PROV is 78-89 % of
every AgentDojo-family corpus (AgentDyn 12.4 GB of 14.9), raw is 2.0 GB in total.

Notes:
- `regen-batch.md` item 28 cites "126,747 stored AERs of the nine current corpora"; the eight working corpora hold
  126,351. The difference is 396, one Mandate copy (likely `mandate-agentdojo-eval-p10-b.pre-integration`). History
  copies are not regenerated.
- Seven corpora record their snapshot with a `local` origin (`<home>/Desktop/PhD/Labs/AgentPROV-upstream/...`) beside a
  verified git pin (`verification.kind = blob`, every blob verified); only 2024-06 has a `git` origin. A re-map keeps
  the recorded origins (D-30), so the regenerated corpora keep these `local` origins (observation O-1, §6).
- These manifests predate D-33: AgentDyn's snapshot counts read `candidates` 47,723, `executions` 38,281, `not_imported`
  10,391 (which includes the 949 `selection_excluded`). Sealing recomputes the counts (D-33(1)); nothing to do in the
  round.

### 1.2 New corpora the round could create (only if the user asks; default: not in the round)

Profiled sources in the registry with status `planned` or `partial` (`agentprov info`, `6421c05`) and branches not yet
merged. Each has had at most a scratch trial import. Importing them is a first import, not a regeneration; listed so the
user can decide whether the round should include any.

| Source · part | Family | Executions (trial or census) | State on main | What it waits for |
|---|---|---:|---|---|
| dtap · head | dtap | full set not imported (sample 500) | planned | DTap step 4: R12b-2/3 (tier-4 64 MiB parse cap, pii-4 PROV size), pinned origins (D-29 Q3) |
| openagentsafety · head | openhands | 1,560 | planned | nothing technical (10g trials clean) |
| redcode-exec-openhands · head | openhands | 5,460 | planned | archive inputs (now on main) + a trial |
| 19 phase-10d AgentDojo-format profiles (interbolt … llm-lock; 4 copyleft corpora) | agentdojo | 34,057 + llm-lock 53,307 logs | planned | the round's agentdojo code (items 1, 3, 13-15, 22) |
| whistlebench · final-runs | inspect | 9,200 | planned (trial only, D-155) | items 16/25/28 landed; D-155 keeps it trial-only |
| seagent-agentdojo · head | agentdojo | 5,342 | planned | archive inputs on main; a trial import |
| kexin-xu-01-agentharm, fragfuse-agentharm | inspect | 2,005 / 1,747 | planned | **D-182 redaction**, D-186 (raw with account paths) |
| agentops-bench · pilot-v1-seeded | agentops | 3,360 in scope | planned | D-192 (top-level tar.gz, ingest-formats-2: now on main), a trial |
| drift · head / history | agentdojo (DRIFT build) | 1,569 / 1,046 | planned | item 22's dispatch; history is licence `reference` |
| agentdyn · c | agentdojo (DRIFT build) | 4,258 + 949 | partial after item 22 | item 22 merge; the user's yes |
| credleak (Zenodo 22737462) | credleak | 19,636 | on main (10k) | R-10k-1 runner merge |
| Bedrock Converse (21944598), MCPHunt | bedrock, mcphunt | 1,334 / 6,786 | branch `phase-10m-readers` | merge; MCPHunt needs RW-1 and R-10k-1 follow-up (i) |
| AutoGen guard placement, ATIA | autogen, inspect | 1,080 / 123 | branch `phase-10n-small` | merge; R-10k-1 (R-10n-3) |
| gemini-cli (10o), control-arena (10p) | new | in progress | sessions running | their own phases |

## 2. What moves bytes, and where

Every change merged on main or queued for the round, mapped to the stages and corpora it moves. "Code digest" means
`engine_code_sha256`/`adapter_code_sha256` and so the stage `fn_digest`, with no output byte change (H.8.4(2): passes
as a refactor only when every output is identical). Counts are the predictions recorded in `regen-batch.md` and the
owning reports; the rehearsal checked some of them (§3.4).

### 2.1 Change list

| Change (status on 2026-10-13) | Stages moved | Corpora and predicted effect |
|---|---|---|
| **aer/0.2 + agentprov-corpus/0.2** (deferrals part C, D-210..D-217; branch `deferrals-c`, merges LAST) | every AER (header `aer` member), so SEM `aer_digest`, PROV, validation; `corpus.json` `format`/`formats`; `aer` stage `format` | **all 8 corpora, every execution.** Content changes beyond the header only for live records with a cut prefix or redaction (none stored). D-216: no stored line is over 1 MiB, so no stored AER is refused |
| Item 3 + E2-c6 (D-80, D-81; on main) | AER (profile digest in every header; twins), PROV, completeness | 2024-06 18,241, head 36,679, Mandate 396, ROPE 10,791 (322 known_incomplete → unverifiable), AgentDyn 38,281 (825 → unverifiable), survey 3,243, adprov-v1 17,664: every AER; AgentHarm none |
| Item 13 (D-84; on main) | AER/SEM/PROV | head: 10,732 `v0.k11` logs cite twins; 36 retries known_incomplete → unverifiable; 2024-06 none |
| Item 14 (D-87; on main) | AER/SEM/PROV | 2024-06 2,799, head 2,135, adprov-v1 16,247 executions (`apv:afterCausal` to the inference bundle) |
| Item 17 (D-207; on main) | AER (system-prompt label), profile digest | 2024-06 18,034 labelled (17,281 default, 753 spotlighting 2024-06), head 24,707 (23,954 / 606 / 147) |
| Item 1 (D-86; on main) | `agentdojo` catalogue digest in every PROV; AER: head `v1.k14` 140 and Mandate 27 cite D again; SEM/PROV under `suites@2` only | all AgentDojo-family PROV + adprov-v1 profile digest (17,664). B1 (ROPE AutoDojo 1,877 executions gain present markers) and D-86 twins **only if the corpus is derived with `suites@2`** (see F-4, D-353) |
| Item 15 (phase-10d R1; on main) | `agentdojo` catalogue digest | PROV of every AgentDojo-family corpus and adprov-v1 (one attribute) |
| Item 16 (D-155 addendum; on main) | `inspect` catalogue and code digests | AgentHarm: AER bodies identical (1,056/1,056), PROV catalogue attribute only |
| Item 18 (D-156 part 2; on main) | `adapters/agentdojo` code digest | manifests only; no stored member-origin AER |
| Item 19 (scoring rules; on main) | `agentdojo` catalogue digest | PROV catalogue attribute of the AgentDojo family and adprov-v1 |
| Item 21 (phase 10l DRIFT build; on main) | `adapters/agentdojo` code digest | manifests only (`recompute` code-digest notice) |
| Item 22 (RT-1/2/4/5; implemented, branch `claude/items-26-27`) | AgentDyn profile digest; `aer` stage `rules` gains `drift` | AgentDyn 38,281 AERs in `profile.sha256` only (checked on 600 stored executions); `adapters/agentdojo` code digest everywhere |
| Item 23 (RT-3; same branch) | SEM `engine_code_sha256` | every corpus with an `agentdojo` semantics profile; no annotation outside DRIFT (0 stored `drift.isolation_pass`) |
| Item 24 (D-28 addendum 2; on main) | `prov`, `validate` code digests | all corpora, code digest only; PROV moves only for class-I `unexecuted_tool_call` (none stored) |
| Item 25 (D-155 addendum 2; on main) | `inspect` code and catalogue digests | AgentHarm: AER bodies identical |
| Item 26 (implemented, user-approved; branch `claude/items-26-27`) | `agentdyn` catalogue digest; `artefacts.toml` (agentdojo code digest) | AgentDyn PROV catalogue attribute (38,281); no AER or SEM byte (nothing cites the rule) |
| Item 27 (implemented, user-approved; same branch) | (a) capture mapper; (b) `agentdojo.suites@3`; AgentDyn parts a/b/c and autodojo-live select `@3` | (a) no stored corpus; (b) AgentDyn SEM and PROV of all 38,281 when re-derived under `@3` (F-4) |
| Item 28 (i) (D-155 addendum 3; branch `claude/item-28-not-inlined`) | `inspect` code and catalogue digests | AgentHarm AER bodies identical (1,056/1,056) |
| Item 20 (capture mapper under aer/0.2) | capture AERs | no stored corpus (no live corpus) |
| Items 2, 4-12; U6-a/b/c (rows "13-15" of the second list) | as each row of the table in `regen-batch.md` says | **not implemented** (F-2; to be built before the round, P-3): CaMeL 386 AgentDyn logs (2); assessment flags (4); `used(run, fixture)` in core PROV of every attacked execution (5); `partial` markers (6); F-01 catalogue digest (7); F-10 (8); index completeness refresh (9: head 232, ROPE 2, 2024-06; the rehearsal saw ROPE's 2 `index.completeness` findings); validator constraints (10: validation digests of every corpus); AgentHarm 4 executions → known_incomplete (11); Inspect harness/benchmark D rules (12: AgentHarm 1,056); U6-a/b AgentHarm 1,056/200, U6-c Mandate 396 |
| D-31 integer version bumps (user ruling 2026-10-11; **not applied**; scheduled first, P-2) | every catalogue and profile that changed bytes (the owner lists them; at least `agentdojo`, `agentdyn`, `rope`, `adprov`, `inspect`, and the semantics profiles); profiles `agentdojo-upstream`, `rope`, `agentdyn`, `survey-runs`, `mandate-agentdojo-eval`, `adprov-v1`, `survey-agentharm`, `agentdojo-live`, `autodojo-live`; old versions under `rules/archive/` | AER header `rules`/`profile.version` of every execution of the 8 corpora (already moving with aer/0.2); without them every regenerated corpus records an integer version whose bytes differ from what the earlier corpora recorded (F-1) |
| D-182 Inspect redaction (R-H1; implemented in `regen-items-2-12`, row above) | Inspect code digest; with a catalogue bump, every Inspect AER header | AgentHarm 1,056 (header only; no redaction table in its profile) |
| ingest-formats bundle (D-240..D-246; on main) | `expand` `fn_digest` and `aer`/`expand` `limits_sha256`; `corpus.json` limits record | all 8 (limits record); AgentHarm's 1,691 member rows keep digests/labels/dispositions, only `fn_digest` moves |
| ingest-formats-2 (D-247..D-249; on main since `d67ce49`) | `EXPAND_MODULES`, origin kinds (`split`), importer | expand `fn_digest`; `aer` stage engine digest; no stored AER/SEM/PROV byte (no stored split or top-level tar.gz) |
| Phase 12b expand bundle (D-56..D-59; on main) | `expand` `fn_digest` | AgentHarm member rows' `fn_digest` only |
| R-10k-1 runner (D-320; not merged) | `aer` stage `engine_code_sha256` | all 8: code digest only, no AER/SEM/PROV byte |
| RW-1 withholding by issue code (D-311..D-314; seal-only) | sealing (`WITHHELD.json` 0.2 only for policies with an issue rule) | none of the 8 (no `[withhold]` table in their profiles) |
| **D-31 option B** (user, 2026-10-13, after H.2.5 refused mixed catalogue versions; D-31 bumps branch, lands first) | the integer bumps and `rules/archive/`; semantics per corpus decided by the user 2026-10-13: `agentdojo.suites@2` for agentdojo-upstream (2024-06, head), ROPE, Mandate, survey and adprov-v1; `@3` for AgentDyn a/b/c and autodojo-live; `inspect.agentharm@2` for AgentHarm; `suites@4` dropped; `@1` only for recomputing the stored corpora | every SEM header and PROV of the 8 corpora; annotation changes as §2.2 |
| `regen-items-2-12` (code-complete at `5c73a317`; lands right after the D-31 branch): items 2, 4-12, U6-a/b/c, R-10p-2 (`model_roles`), **D-182** + R-10p-3 (Inspect account-path redaction), D-372 | AER (items 2, 11, 12, U6), SEM/assessment (4, 6, 8), core PROV (5), validation (10), index (9, D-372) | item 4's C1 screen fires on head 11, 2024-06 9, ROPE 5 executions; item 5 adds `used(run, fixture)` (gate D's never-emit exemption admits `agentdojo:load_environment`, TraceLogger only); an AgentHarm re-map rehearsal by that session: 630 lost requests, every execution passes tier 4; D-372: ROPE 322, AgentDyn 825, head 36 → `unverifiable` |
| Carved blobs (D-218, `353ea7de`; landed) | runner origins (`carved`), `verify`/`recompute` re-carve | none of the 8 (no stored string over 1 MiB; ATIA and OpenHands content only) |
| Remaining code merges before aer/0.2: RW-1, phase 10m, phase 10n, runner D-321/D-323, D-315, ingest-formats-3 | stage code digests (runner, expand, limits) | code digests only for the 8 corpora unless their owners' predictions say otherwise (to be entered in `regen-batch.md` by each) |
| D-410 rule-catalogue cache (pipeline-perf; regen-batch item 32; **on main** `e24bf772`) | `aer` stage `engine_code_sha256`/`fn_digest` | code digest only; no output byte (Mandate checked by its owner) |
| D-413 validate tiers 3-4 in T1 jobs (pipeline-perf; reviewed) | `validate --corpus` scheduling | none (byte-identical reports) |
| Remap fix (`41d7a2f`: the G4 profile check guards only added snapshots) | none (enables re-map) | prerequisite for every re-map; on main |
| D-360 fixture cap (tests only) | none | none |
| Phase 10k credleak family (on main) | `adapters/` registry (new family) | none of the 8 |

### 2.2 Predicted digests per corpus (after the whole queue, aer/0.2 last)

Every AER changes in every corpus (aer/0.2), so every `aer_digest` in SEM and every PROV and validation row changes.
What differs between corpora is what else changes in content:

SEM (user decision 2026-10-13): AgentDojo-family corpora and adprov-v1 under `agentdojo.suites@2` (item 1's B1 and
D-86 twins, plus items 4, 6, 8), AgentDyn under `@3` (item 27(b)'s tables on top of `@2`), AgentHarm under
`inspect.agentharm@2`. Every SEM header and PROV moves. Annotation movements predicted by the owners: item 4 (C1 flag)
head 11, 2024-06 9, ROPE 5; item 6 (`partial` markers, per 4,000-execution sample) AgentDyn 38, ROPE 308, head 50,
survey 52, 2024-06 52; item 8: 0 markers; item 1 B1: ROPE AutoDojo arm 3,344 markers in 1,877 executions (1,118 → 2,528
with a `present` marker); D-86: outcome and marker annotations of ROPE, AgentDyn, survey cite twins (I).

| Corpus | AER content beyond the header | SEM | PROV statements | Completeness / index | `derivation.json` |
|---|---|---|---|---|---|
| Mandate | item 3 twins (13 rules); item 1: 27 executions cite D again; U6-c: `sampling` declared `unk` in 396 | `suites@2`: outcomes and markers stay D (verified code, item 1) | twinned statements to inference; catalogue digests | 396 unverifiable (unchanged) | all stages |
| AgentHarm | items 11, 12, U6-a (1,056), U6-b (200); D-182 redaction where a profile has a table (none in `survey-agentharm`: header only); items 16/25/28 byte-identical; re-map rehearsal by the items-2-12 session: 630 lost requests, all tier 4 pass | `inspect.agentharm@2` (header) | `inspect` catalogue digest; item 12 adds harness/benchmark links | item 11: 4 verified_complete → known_incomplete | all stages incl. `expand` (fn and limits) |
| survey AgentDojo | item 3: 13 rules twinned | `suites@2`: D-86 twins on outcomes and markers; item 6 (52 per 4,000 sample) | as Mandate | unchanged | all stages |
| ROPE | item 3: 15 rules twinned; item 4 (5) | `suites@2`: B1 (1,877 executions), D-86 twins, items 4 (5), 6 (308 per 4,000 sample) | twinned statements | 322 known_incomplete → unverifiable (with D-372; F-5); item 9 refresh of 2 rows (rehearsed) | all stages |
| adprov-v1 | item 3: c6 + five agentdojo rules; item 14: 16,247 | `suites@2`: outcomes stay D (`a75aba7` verified, D-86 addendum) | `apv:afterCausal` of 16,247 to inference | unchanged | all stages |
| 2024-06 | items 3, 14 (2,799), 17 (18,034 labels) | `suites@2`: stays D; items 4 (9), 6 (52 per 4,000 sample) | item 14 | unchanged (item 9 refresh) | all stages |
| head | items 3, 13 (10,732), 14 (2,135), 17 (24,707), 1 (140) | `suites@2`: stays D; items 4 (11), 6 (50 per 4,000 sample) | items 13/14 | 36 retries → unverifiable (D-372); item 9 | all stages |
| AgentDyn | item 3 (16 rules), item 22 (`profile.sha256`), item 2 (386 CaMeL) | `suites@3`: AgentDyn tools labelled instead of `unknown` (27(b)); D-86 twins; item 6 (38 per 4,000 sample) | twinned statements; `agentdyn` catalogue (item 26) | 825 known_incomplete → unverifiable | all stages; `aer` `rules` gains `drift` |

## 3. Order and method

### 3.1 Method per corpus (D-350; route (a), chosen by the user 2026-10-13)

Every corpus is **imported fresh from its pinned inputs into a new corpus directory** (P-4 route (a)). Why not a
re-map: after the D-31 bumps, `recompute` replays the versions the source recorded (H.8), loading the archived profile
v1 and `suites@1` (the D-31 owner, 2026-10-13), so it cannot produce the round's versions (§2, D-353); a re-derive keeps
the stored `aer/0.1` records. A fresh import takes the registry's current profiles and semantics versions with no code
change. The re-map rehearsal of §3.4 still stands as evidence for the pipeline stages an import shares (map, SEM, PROV,
tier 4, determinism) and for `recompute --dry-run` as the determinism check on the new corpus.

Inputs (checked offline 2026-10-13, `GIT_NO_LAZY_FETCH=1`, 0 missing objects in each pinned tree):

| Corpus | Command (the round adds `--release --jobs 8 --summary-json <log>/<id>-import.json`) | Input |
|---|---|---|
| Mandate | `agentprov import mandate-agentdojo-eval --snapshot head --fetch --corpus ~/.agentprov/corpora/mandate-agentdojo-eval-rg1` | cache `jwilliamsc/mandate-agentdojo-eval@fa62a977` (401 entries) |
| AgentHarm | `agentprov import agent-security-tools-survey --snapshot agentharm --fetch --corpus …/ast-survey-agentharm-rg1` | cache `Forever-CodingNoob/agent-security-tools-survey@89c4db2c` (3,308) |
| survey AgentDojo | `… agent-security-tools-survey --snapshot agentdojo-runs --fetch --corpus …/ast-survey-agentdojo-rg1` | same pin |
| adprov-v1 | `agentprov import adprov-v1 --snapshot release --input ~/.agentprov/migration-work/deferrals/baseline-pristine/corpus/corpus-prov --verify-against-pin --corpus …/adprov-v1-release-rg1` | the pristine APFS clone (17,664 transcripts; listing pin `46273b01…`). **Never the working checkout** `../AgentDojo-PROV-framework`, which holds the user's uncommitted edits |
| 2024-06 | `agentprov import agentdojo --snapshot 2024-06 --fetch --corpus …/agentdojo-upstream-2024-06-rg1` | cache `ethz-spylab/agentdojo@c274885` (18,334) |
| ROPE | `agentprov import rope --snapshot head --fetch --corpus …/rope-rg1` | cache `xhOwenMa/ROPE@64495e16` (24,909); the AutoDojo link repo is cached |
| head | `agentprov import agentdojo --snapshot head --fetch --corpus …/agentdojo-upstream-head-rg1` | cache `ethz-spylab/agentdojo@089ed468` (36,860) |
| AgentDyn | `agentprov import agentdyn --snapshot a --fetch --corpus …/agentdyn-a-rg1` | cache `SaFo-Lab/AgentDyn@5353cf76` (49,219) |

- The phase-10 corpora were imported with `--input <upstream clone>` (`local` origins). `--fetch` reads the same pinned
  trees from the verified fetch cache and records `git` origins, which resolves O-1 for six corpora; adprov-v1 stays
  `local` (a gitignored tree, pinned by listing). `--fetch` must stay offline when the pin is cached; the Mandate
  rehearsal (§3.6) found it refused without `--allow-network` (F-7); P-11 makes it offline, and the Mandate rehearsal is
  repeated with `--fetch` once P-11 lands. Any network access needs the user's yes. `--verify-against-pin` goes with
  `--input` only (`--fetch` verifies the pin itself), so the `--fetch` rows of the table drop it.
- `corpus_id`, parts, snapshot ids and pins are unchanged; execution ids are expected unchanged (the ROPE re-map kept
  all 10,791; same H.7.7 mapping identity), and the comparator asserts it. The manifest is `mode: import` with no
  `derived_from`; the lineage to the `-p10` working corpus is recorded in `CHANGELOG.md` at the first seal (no corpus
  version exists yet).
- Worker count 8 (12 cores, shared machine; derive-timings found 8-12 within noise under load); 3 for the cross-check.
- New directories `<id>-rg1.partial`; after every check of §3.3 passes, the old `<id>-p10.partial` is renamed
  `<id>-p10.pre-regen.partial` (rename, never delete); the `*.pre-*` history copies are not touched.
- Before the round, after the D-31 branch lands: `agentprov recompute --corpus <old> --dry-run` on each old corpus must
  report every execution `identical` (the archived loading works and the stored corpora stay recomputable).

Rejected: the re-map (`recompute --out`) as the round's method: it replays the recorded v1 versions after D-31 (above).
Route (b), a recompute upgrade mode (about a day of core work in `corpus/derive.py` and the CLI, its own decision): on the
roadmap after the round (§8). Re-deriving only: keeps aer/0.1. `--input` from the upstream clones: keeps `local` origins
and depends on the clones' working trees; the fetch cache is the verified copy.

### 3.2 Order (D-355, proposal)

One corpus at a time, smallest first, so a failure shows on a cheap corpus; the gate-D inputs before the large ones:

1. Mandate (396) – the canary for every check.
2. AgentHarm (1,056) – the only Inspect corpus and the only one with `expand`.
3. survey AgentDojo (3,243).
4. adprov-v1 release (17,664) and 5. AgentDojo 2024-06 (18,241) – then **gate D and gate E at full scope** on these
   two (`agentprov migrate gate D --scope full --release` with both trees, then gate E; deferrals part D README "The
   release chain": D and E run only on corpora imported with the code they check, at one commit and lock).
6. ROPE (10,791).
7. AgentDojo head (36,679).
8. AgentDyn a (38,281) – last: it needs items 22/26/27 and the `@3` re-derive (the orchestrator relayed that this
   needs the user's yes, which this plan asks for in the same approval).

### 3.3 Checks after each corpus (D-354, proposal)

In this order; a failure stops the round for that corpus and goes to the orchestrator.

1. The import's own summary: `failed 0`, every candidate sealed (`seen = mapped`), `degenerate` and register rows as in
   the phase-10 import reports (`docs/reports/<source>/import-cli-*.json`) unless §2.2 predicts a change; the pinned
   snapshot check passes (`--verify-against-pin`); no `rules.mismatch` or `rules.unavailable`.
2. `tools/suite_queue.py --class rehearsal --cpu 3 -- agentprov recompute --corpus NEW --dry-run --jobs 3`: `identical` for every execution, exit 0. With the import at 8
   workers this is two builds at two worker counts (H.8.4(1), H.11.2(3)); a second dry-run at 8 is added for the three
   small corpora only (§5.3, minimal set).
3. Validation, **full** (user decision 2026-10-14): the import's own validation stage runs tiers 2-4 in release mode
   on every execution; then `tools/suite_queue.py --class rehearsal --cpu 8 -- agentprov validate --corpus NEW --strict
   --tiers aer,sem,prov,linkage --jobs 8` (plus `regression` for adprov-v1) re-checks every stored output in T1 workers
   (D-413, on main `da127648`; byte-identical to the in-process path): about 30 min for ROPE, about 3 h for all eight
   (pipeline-perf's estimate; replaced by the quiet-window calibration, D-415). `--release` stays unused while the SHACL
   tier is unimplemented (F-3).
4. `agentprov verify --corpus NEW --level chain`: exit 1 only for `checksums.absent` (a working tree has no
   `checksums.sha256` until sealing); any other finding fails.
5. After 2024-06 and adprov-v1: gate D then gate E, full scope, release mode (deferrals part D's note).
6. `docs/reports/analysis/CORPUS-CHECK-PROTOCOL.md` (76 checks) against the phase-10 baselines; every movement must be one
   §2.2 predicts.
7. `tools/regen/compare.py --old <id>-p10.partial --new <id>-rg1.partial --expect <id>.expect.json --jobs 4`: equal
   execution-id sets; per execution the masked AER diff (record pointers, records added or removed, rule-citation
   changes), completeness, status and issue transitions, the SEM annotation multiset and the PROV statement and attribute
   multisets per bundle kind; the counts are checked against an expectation file written from §2.2 before the import
   (`docs/reports/regeneration/round/<id>.expect.json`). This replaces recompute's explained-change classification
   (route (a)) and is stronger: "explained" only meant that a declared version differed upstream, and it stayed silent
   when ROPE's 322 completeness moves did not happen (F-5).

Sealing (`package --corpus-version`) is **not** part of the round: corpus versions, CARD texts and release decisions
(F-12C-03 fixed, the copyleft fixtures, D-186) are a separate step after the user has seen the regenerated corpora.

### 3.4 What the re-map rehearsal checked (at `6421c05`)

| Step | Mandate (396) | ROPE (10,791) |
|---|---|---|
| `verify --level chain` on the source clone | exit 1: `rules.mismatch` ×2 (agentdojo@1, mandate profile@1), `checksums.absent` | exit 1: `rules.mismatch` ×3, `index.completeness` ×2, `checksums.absent` |
| `recompute --dry-run` on the source | 396 changed_explained, exit 0 (F-1) | (not run; the `--out` run reports the same classification) |
| `recompute --out NEW --jobs 8` (re-map) | 396 changed_explained, 0 failed, exit 0 | 10,791 changed_explained, 0 failed, 0 unexplained, `index_refreshed` 2, exit 0; `register.jsonl` 11,111 lines replaced (explained); completeness: **322 known_incomplete kept** (F-5), the 2 verified_complete → unverifiable (item 9) |
| stage identities, old → new | aer: adapter/engine code, `limits_sha256`, `profile_sha256`, `rules_sha256` (agentdojo, mandate), fn; sem/prov/validation: code digests and fn | the same fields as Mandate; `rules_sha256` differs for `agentdojo` and `rope` |
| `recompute --dry-run` on NEW, `--jobs 8` | 396 identical | 10,791 identical, exit 0 (5,520 s, peak 2,340 MiB) |
| `recompute --dry-run` on NEW, `--jobs 3` | 396 identical | 10,791 identical, exit 0 (6,051 s; load fell from 23 to 3 during the run; peak 1,402 MiB) |
| `validate --corpus NEW --release` | 396 passed, linkage 396/396 (100 %); exit 1 only for `validate.check.skipped` (SHACL) | `--strict --tiers aer,sem,prov,linkage --sample 2000`: 2,000 passed, linkage 2,000/2,000, 0 skipped, exit 0 (1,934 s, 1.0 ex/s, peak 690 MiB) |
| `verify --corpus NEW --level chain` | exit 0, only `checksums.absent` (unverified) | exit 0, only `checksums.absent` (268 s on a quiet machine; 10,826 raw objects re-hashed) |

### 3.5 What must be rehearsed again (after aer/0.2 merges, the last of the queue)

At the aer/0.2 merge commit, with P-2 (D-31 bumps), P-3 (items, D-372), P-10 (spool fix) on main, all on clones or
scratch corpora under `~/.agentprov/migration-work/regen-plan/`:
- **Route (a) on Mandate and ROPE:** the §3.1 import into a scratch corpus, then every check of §3.3 (dry-run at 3,
  sampled strict validate, verify chain, the comparator against the clone of the old corpus with an expectation file).
  ROPE's 322 retry rows must read `unverifiable` (D-372) and B1 must show (1,877 executions with markers changed, §2.2).
- **AgentHarm and survey AgentDojo imports**, with the parent's RSS measured: the AgentHarm `.eval` zips are the
  many-small-members shape that peaked the T0 importer at ~2.1 GiB before ingest-formats-3's spool fix (P-10).
- **The old corpora's `recompute --dry-run`** on the Mandate and ROPE clones: identical (archived loading, P-2).
- **aer/0.2 specifics:** the new corpora are `agentprov-corpus/0.2` with `aer/0.2` records; `verify --level chain`
  compares the new `corpus-0.2.schema.json` byte for byte (D-163); D-216's 1 MiB check finds nothing (0 stored lines over
  1 MiB).
- **Gate D on the golden set** at that commit (`agentprov migrate gate-d --scope golden`), the cheap precursor of §3.3(5).
The `deferrals-c` preview (§5.4) already showed the 0.2 writer, chain level and determinism on a Mandate re-map.

### 3.7 D-358: the old corpora at their building commit (D-430)

- **Building commit.** The `-p10` manifests predate `producer.git_commit`; they record `producer.lockfile_sha256` and,
  in `derivation.json`, each stage's code digests. `tools/regen/find_building_commit.py` recomputes those digests from
  git trees for every commit (read-only plumbing) and lists the commits whose lockfile and `aer` (adapter and engine),
  `prov` and `validation` digests all match. All eight corpora match **`afe7038`** (2026-10-11, the phase-10 integration
  commit whose tree `run_all.sh` imported), inside the ranges `e9126e9`..`f8b47c4` (six AgentDojo-family corpora, 23
  commits) and `56b5766`..`f8b47c4` (adprov-v1 and AgentHarm, 37 commits, whose adapters did not change in that window).
- **No `recompute` at the building commit.** `recompute`/`derive` arrived with phase 11 (2026-10-12), after `afe7038`.
  So D-358 is realised as the corpus's **original import command, repeated at `afe7038`** on the same pinned input
  (scratch checkout of the cached pin, or the pristine baseline clone for adprov-v1), and a byte comparison of every
  output with the stored corpus.
- **Setup:** `GIT_INDEX_FILE=<scratch>.index git --work-tree=<scratch> read-tree afe7038` + `checkout-index -a -f` into
  `~/.agentprov/migration-work/regen-plan/build-afe7038/` (no git worktree, nothing written to the repository), `uv sync
  --locked --offline` (lockfile digest `da3cceee…` matches the recorded one).
- **Mandate (2026-10-14): reproduced.** `agentprov import mandate-agentdojo-eval --snapshot head --input <scratch pin>
  --verify-against-pin --release --jobs 8` at `afe7038`: 396 sealed clean. `executions.jsonl`, `register.jsonl`,
  `derivation.json`, every file under `aer/`, `sem/`, `prov/`, `validation/` and `raw/objects/` byte-identical to the
  stored corpus; `corpus.json` differs only in `sources[0].snapshots[0].origin.path` (the input directory).
- **D-430 at main (`e73efee3`), checked 2026-10-14 on the Mandate clone** (scratch checkout of `origin/main`, offline
  env): `recompute --out` exits 4 `corpus.derive.version_drift` and writes nothing; `recompute --dry-run --jobs 3` gives
  396 `changed_explained`, 0 unexplained, exit 0, with the notices `version drift: aer: source profile
  mandate-agentdojo-eval v1 recorded, v2 current`, `version drift: aer: catalogue agentdojo v1 recorded, v2 current` and
  `version drift: sem: agentdojo.suites@1 reads catalogue agentdojo v1, the AER would declare v2`.
- **Results of the other seven** (one `--class import` job at a time; AgentHarm, survey and adprov-v1 on 2026-10-14,
  the remaining four after the round, 2026-10-22..23; records in [`d358/`](d358/README.md)):

  | Corpus | Import at `afe7038` | Files identical | Differences |
  |---|---|---|---|
  | AgentHarm (1,056) | 579 s, 6 workers | 4,243 / 4,244 | `corpus.json` `/sources/0/snapshots/0/origin/path` only |
  | survey AgentDojo (3,243) | 816 s, 6 workers | 12,989 / 12,990 | the same pointer only |
  | adprov-v1 (17,664) | 3,073 s, 6 workers | 70,663 / 70,664 | the same pointer only |
  | 2024-06 (18,241; `--fetch --allow-network`) | 3,056 s, 4 workers | **72,972 / 72,972** | none (no fetch: `acquisitions.jsonl` unchanged) |
  | ROPE (10,791) | 5,719 s, 4 workers | 43,206 / 43,207 | the same pointer only |
  | head (36,679) | 8,848 s, 4 workers | 146,723 / 146,724 | the same pointer only |
  | AgentDyn (38,281) | 14,435 s, 4 workers | 162,573 / 162,574 | the same pointer only |

  **D-358 holds for all eight corpora.**

- **The other seven** (heavy; one at a time): the same procedure with the original commands of
  `docs/reports/<source>/import-cli-*.json`. Their original wall times at 10 workers on that code (before D-89's tier-4
  speed-up): survey 525 s, AgentHarm 119 s, adprov-v1 1,476 s, 2024-06 1,615 s, ROPE 3,015 s, head 5,186 s, AgentDyn
  9,145 s: about **5.9 h** in total. Pass: every output file identical, `corpus.json` differing only in the input path.
- **2024-06** repeats its original command, `--fetch --allow-network` (user, 2026-10-14; `afe7038` predates D-220's
  offline `--fetch`); `corpus.json` must then be identical too, and the run stops if `acquisitions.jsonl` changes (40
  lines, sha256 `dcf06598…` before). The other six use `--input <scratch checkout> --verify-against-pin` as originally.
- **ROPE and `aer.blob.digest` (pipeline-perf, D-413 proofs).** The stored `rope-p10` fails strict `aer.validator` with
  `aer.blob.digest` under pre-D-31 code and passes under current main. That code is AER-V35, the AER `/profile/sha256`
  against the package's profile. At `afe7038` the stored AERs pass it: 200 evenly spaced stored ROPE AERs, `validate
  --release --store`, 0 errors, 0 `aer.blob.digest` (exit 1 only for 6 checks the file mode of that build skips). So the
  failure is the same-version profile drift of F-1 (`rope@1` bytes changed in place after `afe7038`), not a defect of
  the stored corpus; D-31's archived `rope@1` is why main passes. **Correction (2026-10-23):** that file-mode check did
  not test V35. The `afe7038` validator is given no package profile digests in file mode and skips V35 ("profile digest
  (V35): no package profile digests given", one of the six skips). So "0 `aer.blob.digest`" there says nothing about
  V35. The full run over all 10,791 re-imported ROPE AERs has the same skip (0 errors, 0 failed, 0 warnings). V35 itself
  runs in the importer's seal-time validator (`adapters/runner/importer.py:774` at `afe7038`). It passed all 10,791,
  and those AERs are byte-identical to the stored ones, so the conclusion stands on that evidence instead
  ([`d358/`](d358/README.md)).
- Tooling: `tools/regen/d358_building_commit.sh` (one `suite_queue.py --class import` job per corpus) and
  `tools/regen/tree_compare.py` (whole-tree byte comparison, read-only). Runs after the merge queue drains (user
  decision 2026-10-14).

### 3.8 P-8: route (a) re-rehearsed at `f24ee223` (2026-10-22; user GO, relayed)

Scratch only (`~/.agentprov/migration-work/regen-plan/out/p8/`); old corpora are the APFS clones under `src/` (and
the stored AgentHarm read in place); one `tools/suite_queue.py` job at a time, `--cpu 2`; driver
`tools/regen/p8_rehearsal.sh`; logs `logs/p8/`. Code: `regen-plan` with `origin/main` `f24ee223` merged, `src/`,
`uv.lock` identical to `f24ee223`. `acquisitions.jsonl` unchanged throughout (56 lines, `928c84d6…`).

| Step | Mandate (396) | ROPE (10,791) | AgentHarm (1,056) |
|---|---|---|---|
| `import --fetch --release --jobs 2` | 396 sealed clean, 0 failed; 97 s | 10,791 mapped (9,366 clean, 1,425 with issues, as stored), 0 degenerate, 0 failed; 6,220 s; peak tree 719 MiB | 1,056 (1,052 clean, 4 with issues), 0 failed; 200 s; parent peak 277 MiB (the spool fix, P-10) |
| corpus | `agentprov-corpus/0.2`, `aer/0.2`, `git` snapshot origin, `agentdojo.suites@2` | same | same, `inspect.agentharm@2` |
| `recompute --dry-run --jobs 3` | 396 identical (22 s) | 10,791 identical (903 s) | — |
| `validate --corpus --strict --tiers aer,sem,prov,linkage --jobs 2` (D-413) | 396 passed, linkage 396/396, 0 skipped (20 s) | 10,791 passed, linkage 10,791/10,791, 0 skipped (708 s) | — |
| `verify --level chain` | ok (only `checksums.absent`) | ok (only `checksums.absent`; 251 s) | — |
| `compare.py` vs the old corpus | ids equal; AER/SEM/PROV changed 396; completeness `unverifiable→unverifiable` 396; 0 mismatches, 0 errors | ids equal; changed 10,791; **`known_incomplete→unverifiable` 322** (D-372), `verified_complete→unverifiable` 2 (item 9); **B1: 3,344 markers to `present`** (2,739 from `absent`, 605 from `ambiguous`) under `agentdojo.autodojo_payload_unescape_unverified@1`, as item 1 predicted; 0 mismatches | ids equal; changed 1,056; **`verified_complete→known_incomplete` 4** (item 11); 0 mismatches |

`agentprov migrate gate-d --scope golden`: 28/28 passed (14 s). **P-8 passes.** The digest-identity method
(`find_building_commit.py`'s construction, run from git trees with each commit's own `stage_scopes.py`) reproduces every
stage digest these imports recorded (agentdojo and inspect adapter, aer, sem; prov; validation; expand).

**Code drift after `f24ee223`.** Stage code digests at `f24ee223` and at `31ee942d` (main after train 4, 2026-10-22) are
identical for every family's adapter, aer and sem stage and for prov, validation and expand: the 28 `src/` files that
train 4 changed lie in no stage scope. The check is repeated, with `tools/regen_pins.py --check`, at the main head the
round runs on.

### 3.6 Route (a) rehearsed at `6421c05`

At current main (`c4fd0dc2`, merged into this branch as `40ad7f2a`: items 22/23/26/27/28, ingest-formats-2, 10k, the
fixture cap and carved blobs on main; the D-31 bumps and `regen-items-2-12` not yet), so the versions are not yet the
round's; this rehearses the method.

- **`--fetch` is refused offline (F-7).** `import … --fetch` without `--allow-network` exits 4
  (`cli.refused.network`, N.1.11) although the pin is fully cached and `raw/fetch.py` would serve it without a socket;
  `--verify-against-pin` is refused with `--fetch` (the fetch verifies the pin itself). Not tried with
  `--allow-network` (needs the user's yes).
- **Offline workaround used here:** the cached pin is materialised into a scratch input with
  `GIT_INDEX_FILE=<scratch>.index git --git-dir=<cache> --work-tree=<scratch> read-tree <commit>` and `checkout-index -a
  -f` (no file written into the cache, no `acquisitions.jsonl` row), then `import --input <scratch>
  --verify-against-pin --release`. Its drawback: the snapshot origin records the scratch path (`local`).

| Step | Mandate (396) | ROPE (10,791) |
|---|---|---|
| import `--input` scratch, `--verify-against-pin --release --jobs 8` | 396 sealed clean, 0 degenerate, 0 failed, pin verified (400 blobs), exit 0; 57 s at load 5 | **paused 2026-10-14** for the performance sessions (user priority, relayed): interrupted cleanly by SIGINT after 3,780 s with 8,192 of 10,791 AERs sealed (load 24-37), exit 130 "in-flight work was sealed or rolled back"; the scratch corpus `out/rope-imp.partial` is kept; it is restarted (not resumed) after pipeline-perf's fixes, since the code will have changed |
| `compare.py` old p10 → imported | ids equal (396/396); AER, SEM, PROV changed in 396; completeness `unverifiable→unverifiable` 396; 24 rule ids change citation counts (13 rules twinned, item 3); 19 AER pointers, all header/evidence/rule members and the seal's `records_sha256`; no record added or removed; SEM: 369 executions' outcome annotations D→I by propagation from their now-I premises (D-83); 0 errors | pending (paused) |
| `recompute --dry-run --jobs 3` on the imported corpus | 396 identical, exit 0 | pending (paused) |
| `verify --level chain` | exit 0, only `checksums.absent` | pending (paused) |

## 4. Blocking prerequisites (D-352, proposal: the round starts only when all are closed)

Order (orchestrator, 2026-10-13, from the user's rulings): (1) the D-31 bumps branch (option B: integer bumps,
archived loading, the semantics versions of D-353, notice-only `limits_sha256`) (P-2); (2)
`regen-items-2-12` (items 2/4-12, U6-a/b/c, D-182, D-372, R-10p-2/3) (P-3, P-5); (3) the remaining code merges: RW-1,
phase 10m, phase 10n, runner D-321/D-323, D-315, ingest-formats-3 with the spool fix (P-1, P-10), and the offline
`--fetch` (P-11); (4) **aer/0.2
(part C) last**; (5) the §3.5 re-rehearsal on clones (P-8); (6) the round, on the user's separate yes (P-9).

| # | Prerequisite | Owner | State (2026-10-13) |
|---|---|---|---|
| P-1 | Merge queue, in order: ingest-formats-2 (on main `d67ce49`), phase 10k (on main), R-10k-1 runner (`f852d27`, `bb938a6`), regen-batch items 22/23/26/27/28 (`claude/items-26-27`), RW-1 (seal-only), D-360 (tests); then P-2, then P-3; **aer/0.2 last** (`deferrals-c`, D-210..D-217) | orchestrator; each owner session | ingest-formats-2 and 10k on main; the rest queued |
| P-2 | **D-31 integer version bumps** for every catalogue and profile whose bytes the batch changed, old versions under `rules/archive/` with archived loading (profiles and semantics tables too, or a write-up first where an archived version cannot load), so `recompute`/`rederive` of an old corpus still loads what it recorded; and **`limits_sha256` notice-only**: it no longer explains an AER output difference (F-1; byte-neutral, `corpus/` is in no stage identity) | regen-batch session ("AgentDojo unverified class twins"), on a fresh branch after its items 22/23/26/27/28 push | **on main** (`430a2dc4`, option B; C.16 digests `220da035` / `fd69ce14` / `d4654a93`); `limits_sha256` notice-only confirmed by the D-358 run; but see F-8 |
| P-3 | Items 2 and 4-12 (approved for implementation 2026-10-11) and U6-a/b/c (approved 2026-10-13, to be renumbered in `regen-batch.md`) implemented, each with its digest prediction | a new session, D-370..D-379 (branch `regen-items-2-12`) | user ruling 2026-10-13: build everything before the round (F-2). Includes **D-372** (user-approved): `corpus/facets.completeness_of` applies the D-24 loss proof, which fixes F-5 (commit `b7b7d5b`, not pushed) |
| P-4 | Producing the decided semantics versions (D-353) for stored corpora. Tested at `6421c05`: `derive` refuses (`corpus.derive.version_mismatch`), `recompute` keeps the recorded `@1`, and after D-31 replays the archived v1 (F-4) | the user | **resolved 2026-10-13: route (a)**, fresh pinned imports (§3.1); route (b) on the roadmap (§8) |
| P-10 | ingest-formats-3's spool fix (`io/workers.py` `SPOOL_MEMORY_PER_JOB`, 64 MiB per job; T0 importer peak ~2.1 GiB → 170 MiB on archives of many small members): needed before the AgentHarm import (its `.eval` zips are that shape); byte-neutral, derivation code digests only | ingest-formats-3, after the runner's D-321/D-323 | queued (P-1) |
| P-13 | ~~F-8 fix~~ replaced by D-430 (user, 2026-10-14): recompute at main reports drift and refuses `--out` on an older-version corpus; D-358 is checked at each corpus's building commit (§3.7). Previously: F-8 fix: the re-map path of `recompute` loads the source profile and catalogues at the versions `derivation.json` records (archived v1), so D-358's "0 differences" holds | the D-31 owner | user ruling 2026-10-14; **on hold** (D-31 owner, 2026-10-14): replaying v1 at main cannot reproduce Mandate byte for byte (AER bodies changed by items 1-28; the current mapper cites 28 `agentdojo` rules the archived v1 catalogue does not declare), and H.8's byte identity is defined at a corpus's building commit + lockfile, not at main. The user is choosing the semantics; D-358's expectation follows that choice |
| P-12 | D-413: `validate --corpus` runs tiers sem/prov/linkage in T1 `validate` workers (`--jobs N`, 0 = host default, 6 on this machine; `--in-process` keeps the old path), byte-identical reports | pipeline-perf | **on main** (`da127648`). Measured at 3 workers under load 30-60: Mandate strict 663 → 185 s, ROPE strict 300-sample 674 → 368 s; 8-worker numbers with the quiet-window calibration (D-415) |
| P-11 | `import --fetch` offline when the cache satisfies the pin; a miss fails `raw.fetch.not_cached`; `--allow-network` only for real fetches (F-7, option (1)) | deferrals session (import CLI) | **on main** (D-220, `e54de9a0`): offline from the cache, a miss is `raw.fetch.not_cached` (exit 4). To do: the Mandate rehearsal with `--fetch` (git origin, `acquisitions.jsonl` unchanged) when heavy work resumes |
| P-5 | D-182 Inspect redaction: moves the Inspect code and every Inspect AER header, so it must land before AgentHarm is regenerated | `regen-items-2-12` | **implemented** (with R-10p-3) at `5c73a317`; lands with P-3 |
| P-6 | R-10k-1 follow-ups (i) `parse_stream`, (ii) per-item register rows, (iii) source keys on the container path | R-10k-1 session after the deferrals session's go | not blocking the 8 corpora (none uses them); blocking credleak, MCPHunt, AutoGen imports if the user adds them (§1.2) |
| P-7 | No import paused anywhere (phase-12a resume rule): every merge above moves stage identities | every session | check at the start of the round |
| P-8 | The rehearsal of §3.5 at the aer/0.2 merge commit (on top of P-2, P-3 with D-372, P-4), clean; ROPE's 322 rows must then read `unverifiable` | this session | **passed 2026-10-22 at `f24ee223`** (§3.8) |
| P-9 | The user's two yeses: the final fix list, then the regeneration itself (and AgentDyn's `@3` re-derive) | the user | this document asks for both |

Not blocking the round but blocking a release: F-12C-03 (datasheet escaping; fixed on main per AGENTS.md §0, re-check at
sealing), the copyleft fixtures, D-186, a manual CI dispatch.

## 5. Resources (measured on the rehearsal)

### 5.1 Measurements

Machine: M2 Max, 12 cores, 32 GiB, shared with other sessions (1-minute load average 15-37 during the runs, recorded per
row in `runs.jsonl`). Peak memory is the summed RSS of the command's whole process tree (CLI + T1 workers), sampled every
second.

| Step | Corpus | Workers | Wall | Rate | Peak tree RSS | Peak single process |
|---|---|---:|---:|---:|---:|---:|
| verify chain (source) | Mandate | 1 | 9.4 s | 42 ex/s | 64 MiB | 64 MiB |
| recompute dry-run (source) | Mandate | 8 | 112 s | 3.5 ex/s | 1,104 MiB | 180 MiB |
| recompute `--out` (re-map) | Mandate | 8 | 113 s | 3.5 ex/s | 1,127 MiB | 193 MiB |
| recompute dry-run (NEW) | Mandate | 8 | 95 s | 4.2 ex/s | 1,098 MiB | — |
| recompute dry-run (NEW) | Mandate | 3 | 155 s | 2.6 ex/s | 594 MiB | — |
| validate `--corpus` | Mandate | 1 | 291 s | 1.4 ex/s | 204 MiB | 204 MiB |
| verify chain (NEW) | Mandate | 1 | 11.5 s | 34 ex/s | 66 MiB | 66 MiB |
| verify chain (source) | ROPE | 1 | 638 s | 17 ex/s | 310 MiB | 310 MiB |
| recompute `--out` (re-map) | ROPE | 8 | 7,173 s (2.0 h) | 1.5 ex/s | 2,109 MiB | 829 MiB |
| recompute dry-run (NEW) | ROPE | 8 | 5,520 s (1.5 h) | 2.0 ex/s | 2,340 MiB | 910 MiB |
| recompute dry-run (NEW) | ROPE | 3 | 6,051 s (1.7 h) | 1.8 ex/s | 1,402 MiB | 926 MiB |
| validate `--strict --sample 2000` | ROPE | 1 | 1,934 s | 1.0 ex/s | 690 MiB | 690 MiB |
| verify chain (NEW) | ROPE | 1 | 268 s | 40 ex/s | 413 MiB | 413 MiB |
| import `--input` (route (a)) | Mandate | 8 | 57 s (load 5) | 6.9 ex/s | 1,317 MiB | 196 MiB |
| recompute dry-run (imported) | Mandate | 3 | 126 s (load 18) | 3.2 ex/s | 584 MiB | 194 MiB |
| verify chain (imported) | Mandate | 1 | 8.3 s | 48 ex/s | 64 MiB | 64 MiB |
| import `--input` (route (a)), partial | ROPE | 8 | 3,780 s for 8,192 sealed AERs, then paused | 2.2 ex/s (map phase, load 24-37) | see `runs.jsonl` | |

### 5.2 Disk

A re-map writes a full new tree beside the old one (raw copied, D-32). The new corpora are about the size of the old
ones (aer/0.2 adds one header byte change per record; item 3/13/14 move statements between bundles, not their number):
about **39 GB** for the eight, plus the dry-run temporary trees (one corpus at a time, written to the system temporary
directory and removed: at most the largest corpus, ~15 GB for AgentDyn). Free on the data volume on 2026-10-13: 325 GiB.
The rehearsal's own clones cost almost nothing (APFS copy-on-write); its new trees: Mandate 74 MB, ROPE 5.5 GB (the source is 4.9 GB: +13 %, mostly PROV, where item 3 splits statements into more inference bundles). Applying +13 % to every corpus gives about **44 GB** for the eight.

### 5.3 Time for the full round

The re-map's cost follows the PROV it writes more closely than the execution count (ROPE's executions are large):
Mandate wrote 495 KiB of PROV per second, ROPE 598 KiB/s, both at 8 workers under a load average of about 28-30. Projected
from the source corpora's PROV size (`du -sk`) at 495-598 KiB/s:

| Corpus | PROV (KiB) | Re-map at 8 workers | Dry-run at 8 | Dry-run at 3 (×1.6, Mandate's ratio) |
|---|---:|---:|---:|---:|
| Mandate | 55,892 | 113 s (measured) | 95 s (measured) | 155 s (measured) |
| AgentHarm | 150,320 | 4-5 min (+ expand) | 4-5 min | 7-8 min |
| survey AgentDojo | 595,660 | 17-20 min | 17-20 min | 27-32 min |
| adprov-v1 | 2,522,852 | 70-85 min | 70-85 min | 1.9-2.3 h |
| 2024-06 | 2,792,016 | 78-94 min | 78-94 min | 2.1-2.5 h |
| ROPE | 4,286,072 | 2.0 h (measured) | 1.5 h (measured) | 1.7 h (measured; load fell during the run) |
| head | 5,967,752 | 2.8-3.4 h | 2.8-3.4 h | 4.4-5.4 h |
| AgentDyn | 12,411,796 | 5.8-7.0 h | 5.8-7.0 h | 9.2-11.1 h |
| **Total** | 28,782,360 | **13.4-16.2 h** | 13.4-16.2 h | 21-26 h |

Other checks, single process: `verify --level chain` re-hashes about 8 MB/s (ROPE 5.1 GB in 638 s, Mandate 34-42
executions/s), so about 1.4 h for all eight; `validate --corpus` runs about 1.4 executions/s on Mandate (ROPE: see §5.1),
so the full runs on the three small corpora take about 55 min together and the five 2,000-execution samples 25-40 min
each. Gates D and E at full scope (35,905 executions in two trees) cost about one dry-run of adprov-v1 plus 2024-06,
2.5-3 h (estimate; not rehearsed: they need regenerated inputs).

**Totals, sequential, at the measured load:**
- *Full check set* (§3.3: re-map, dry-run at 8, dry-run at 3, validation, chain, gates): about **55-65 h** of machine time.
- *Minimal sufficient set*: the re-map itself is the first build, so one dry-run at 3 workers proves both "twice" and
  "across worker counts"; the second dry-run at 8 is kept only for the three small corpora. About **40-48 h**.
- The rates are for a machine shared with several other sessions (load 15-48). derive-timings.md measured 7-9
  executions/s re-derive on a lighter load and ~9.3/s at 12 workers; on a quiet machine the totals should fall by
  roughly half. The round could also wait for the M5 Ultra (user-machines memory), where `--tune-jobs` is still to run.

Peak memory at 8 workers: Mandate 1.1 GiB, ROPE 2.1 GiB (largest single worker 829 MiB). The `prov` job cap is 4 GiB
per job (D-55), so AgentDyn's longest runs stay inside it; the projected tree peak is under 8 GiB, well inside 32 GiB
with the other sessions' use. Proposed (D-354): **the minimal set, run when no other heavy job is on the machine**,
corpus by corpus in §3.2's order, so the round can stop between corpora.

**Revised projection from pipeline-perf (2026-10-14, relayed; write-up `docs/reports/pipeline-perf/profile.md`).** The
rates above were measured under load 15-48 from other sessions; pipeline-perf profiled the cost itself:
- Tier 4 is 89 % of post-AER CPU and the PROV round trip alone 81 % (ROPE, 2,000-execution stratified sample); cost
  about 2.7 us of post-AER CPU per byte of PROV-JSON; per execution mean 1.09 s, p90 2.08 s, max 7.27 s.
- D-410 (rule-catalogue cache; awaiting the user's yes; regen-batch item 32) removes 15-19 % of import CPU (ROPE map
  ~240 → ~10 ms per execution) and moves only the `aer` stage's `engine_code_sha256`/`fn_digest`.
- The flat 8- versus 3-worker times of §5.1 are load, not a serial parent or batch barrier: a schedule model reaches
  93-95 % of the no-barrier ideal at 6-8 workers, the parent about 3 % of CPU. ROPE on an idle machine: 68 min at 3
  workers, 35 at 6, 27 at 8.
- All eight corpora: 27.2 GiB of stored PROV, about **22 CPU-h**, nearly all post-AER: about **3-4 h of import wall time
  at 8 workers** on an idle M2 Max (allow ×1.5: 3-6 h), with D-410 in and one heavy job at a time.
- With the same model, each dry-run at 3 workers costs about 2.5× an 8-worker import, so the minimal check set (import
  at 8 + dry-run at 3) is about 11-15 h idle, and the full set about 15-20 h, against §5.3's 40-65 h under load.
- A measured pool calibration (throughput and RSS against workers) follows in the orchestrator's quiet window; the plan's
  numbers are replaced by it.

**Validation.** `validate --corpus` today is tier-4-bound in one process: 0.69 s per execution on Mandate, ~0.97 s on
ROPE, ~20 CPU-h (~34 h single core) for every corpus. **D-413** (branch `pipeline-perf-d413`; reviewed by the runner and
deferrals owners) runs tiers 3-4 in T1 jobs with byte-identical reports: ~3 h at 8 workers for all eight. Once D-413
lands, **full** stored-output validation becomes affordable; switching §3.3(3) from samples to full is for the user
(proposal below, D-354 alternative).

### 5.4 Preview on `deferrals-c` (aer/0.2, unmerged)

`deferrals-c` (`8c0e316`, the part-C branch rebased on `41d7a2f`, before ingest-formats-2 and 10k) was checked out in
this worktree for the preview only, then the branch was switched back. Mandate's source clone (aer/0.1) re-mapped:

- `recompute --out`: 396 `changed_explained`, exit 0, 113 s-class timing; the new tree is `agentprov-corpus/0.2` with
  `formats.aer = aer/0.2`; the `aer` stage now differs in `format` (`aer/0.1` → `aer/0.2`), a declared version, as the
  design §3(4) says. `rules.mismatch` ×2 as before (P-2 not applied on that branch either).
- dry-run at 8 workers (147 s) and at 3 (245 s): 396 identical, exit 0.
- `verify --level chain`: exit 0 except `checksums.absent` (the chain level reads the 0.2 corpus with its new schema).
- `validate --strict --tiers aer,sem,prov,linkage --sample 100 --seed 0`: 100 passed, linkage 100 %, exit 0 (106 s).

So the reader of a stored aer/0.1 corpus and the writer of aer/0.2 work together through `recompute`; the full rehearsal
of §3.5 is still required at the real merge commit, which will also carry P-2, P-3 and D-372.

## 6. Findings (routed to the orchestrator; nothing fixed here)

- **F-1 (blocking; D-31 not applied and its check masked).** On `6421c05`, `verify --level chain` of every source clone
  reports `rules.mismatch` (Mandate: catalogue `agentdojo@1`, profile `mandate-agentdojo-eval@1`; ROPE: three), because
  the batch changed their bytes at the same integer version. `recompute` nevertheless classifies every changed execution
  `changed_explained` and exits 0: the only declared-identity change of the `aer` stage is `limits_sha256` (the
  ingest-formats `IngestLimits` fields), which `declared_identity` (`corpus/derive.py`) counts as a declared version.
  So D-31's `unexplained_change` cannot fire while the limits record also changes. **User ruling (2026-10-13,
  relayed):** the regen-batch session applies the D-31 bumps with archived loading, and makes `limits_sha256`
  notice-only, on one branch (P-2).
- **F-2 (blocking; approved items not implemented).** Items 2 and 4-12 have no implementation on main (spot checks:
  `_LOSS_CODES` in `adapters/runner/importer.py` lacks `missing_tool_result`, item 11; `validate/constraints.py` still
  calls the event-ordering constraints not instantiable, item 10). U6-a/b/c were still proposals. **User ruling
  (2026-10-13, relayed):** implement items 2 and 4-12 and U6-a/b/c before the round, in a new session (D-370..D-379)
  (P-3).
- **F-3 (tooling).** `validate --corpus --release` exits 1 on every corpus because tier `shacl` is not implemented and a
  skipped check fails in release mode; the plan uses `--strict --tiers ...`. `validate --corpus` ignores `--jobs` (one
  process; Mandate 291 s for 396): a full run over the eight corpora would take on the order of a day, so the plan
  samples the large corpora and relies on the re-map's own validation stage. **User ruling (2026-10-13, relayed):**
  approved as planned; no validate workers and no `--release` while SHACL is unimplemented.
- **F-4 (blocking for items 1 and 27(b)).** `recompute` re-runs SEM with the semantics profiles recorded in the source
  manifest (`_semantics_of`), so a re-map keeps `agentdojo.suites@1` even when the source profile now selects `@2`/`@3`;
  `derive` refuses to replace a present layer. Item 1's B1 and D-86 twins and item 27(b)'s AgentDyn labels therefore do
  not reach the stored corpora by the planned method. **Tested (Mandate):** `derive --corpus NEW --stages sem,prov,validation --semantics-profile agentdojo.suites@2 --dry-run`
is refused with `corpus.derive.version_mismatch` (exit 4: "use recompute --out to re-derive it"), and `recompute
--stages aer --out` still re-runs SEM, PROV and validation under the recorded `@1` (4 stages, 396 changed). There is no
flag on `recompute` to name a semantics version. Needed (P-4): `recompute --semantics-profile ID@N` (or reading the
version the source profile now declares) with the change classified as explained by the `sem` stage's declared
`profiles`, owner corpus/ via the orchestrator.
- **F-5 (blocking; resolved by D-372, user-approved).** A re-map does not apply item 3's B6 rule: ROPE's 322 retry rows,
  each citing only `retry_passes_inferred` under the class-I twin `agentdojo.null_final_implies_three_passes_unverified@1`,
  stay `known_incomplete` where item 3 predicts `unverifiable`. The importer drops unproven loss codes
  (`adapters/runner/importer.py` `_index`, `proven_loss_codes`); `corpus/facets.completeness_of`, used by `recompute`
  (`corpus/derive.py`) and `verify --level chain` (`corpus/verify.py`), did not. Same gap found independently by the
  items-2-12 session and fixed as D-372 (commit `b7b7d5b` on `regen-items-2-12`, not yet pushed; counts ROPE 322,
  AgentDyn 825, head 36 agree). Precondition P-3; the ROPE rehearsal is repeated on top of it.
- **F-6 (observation).** ROPE's source clone has 2 `index.completeness` findings under the current B2 rule (item 9's
  refresh); the re-map performs it (`index_refreshed` 2).
- **Q-1 (open; with the D-31 owner, who adds or sizes the mechanism).** Which change makes `recompute` derive a stored corpus under the newly
  selected semantics version (F-4), and is that change explained by the `sem` stage's declared `profiles`?
- **Q-2 (answered by the user 2026-10-13).** See D-353.
- **F-7 (blocks route (a) with `git` origins; owner: the import CLI, deferrals session).** `agentprov import --fetch`
  requires `--allow-network` even when the fetch cache satisfies the pin, while `raw/fetch.py`'s `Fetcher` with
  `allow_network=False` already serves cached recipes and refuses before any socket on a miss. Options: (1) a small CLI
  change, `--fetch` offline unless `--allow-network` (a miss fails `raw.fetch.not_cached`); recommended; (2) the user
  allows `--allow-network` for the round's imports (expected network use 0; checked by an unchanged `acquisitions.jsonl`
  and no network log lines); (3) `--input` from a scratch checkout of the cached pin (offline, rehearsed; `local` origins
  remain, O-1). Routed to the orchestrator 2026-10-14. **User ruling (2026-10-14, relayed): option (1)**, built by the
  deferrals session as a small byte-neutral CLI branch (P-11).
- **F-8 (defect, blocking; owner: the D-31 owner, "AgentDojo unverified class twins"; routed 2026-10-14).** **User
  ruling (2026-10-14, relayed):** `recompute` replays the RECORDED versions at every stage, so an old corpus recomputes
  to 0 differences; upgrading stays with fresh re-imports (route (a)). The importer's re-map path is being fixed to load
  the profile and catalogues at their recorded versions from the archives (P-13); D-358 is re-run on Mandate after
  that, on the big corpora after the drain. The finding as observed: At main with `430a2dc4`
  (D-31) and `e54de9a0` (D-220), `recompute --dry-run --jobs 8` on the old Mandate clone gives 396 `changed_explained`,
  0 unexplained, 396 `index_refreshed`, exit 0; no `rules.mismatch` any more and `limits_sha256` is a notice. An `--out`
  copy shows why: the `aer` stage is re-mapped with the **current** profile `mandate-agentdojo-eval@2` and catalogue
  `agentdojo@2` (AER `/profile/version` 2, `/rules/agentdojo` 2, 24 rule ids re-cited), while SEM stays at the recorded
  `agentdojo.suites@1`. So the stored corpus is neither reproduced byte for byte (D-358) nor upgraded consistently
  (`suites@2`, D-353): a re-map gives a mixed AER@current / SEM@recorded corpus. The D-31 owner had described the re-map
  as loading the archived v1. Route (a) is unaffected (an import takes the current versions throughout); the history
  claim "every stored corpus stays recomputable" is what is at stake. Evidence: `logs/d358-mandate.json`,
  `d358-mandate-out.json`, `compare-d358.json`, scratch tree `out/mandate-d358.partial`.
- **O-1 (observation).** Seven corpora record `local` snapshot origins (`<home>/Desktop/PhD/Labs/AgentPROV-upstream/…`)
  next to their verified git pins; a re-map keeps them. A release may prefer pinned origins only (D-29 addendum Q3 states
  that rule for DTap); that needs a re-import, not a re-map. For the user's decision before sealing, not before the
  round.

## 7. Decisions (D-350..D-359)

**Status 2026-10-22 (user decisions relayed by the orchestrator on the go/no-go, `go-no-go.md`):** D-350 (route (a)),
D-351 (scope A: the eight stored corpora), D-352, D-353, D-354 (full validation), D-355 (order; `--cpu 6-8` while no
other heavy job runs), D-356, D-357 and D-358 (the remaining four after the round or between corpora) are decided and
recorded in `docs/architecture/decisions/D-350.md`..`D-358.md`. Item 28(ii), item 26 and the U6 `payload` are not in
this round. adprov-v1's listing-pin origin stays open until sealing. P-8 (the re-rehearsal at `f24ee223`) is GO; the
round needs the user's separate yes after P-8. The text below is the original proposal.

**Outcome 2026-10-22 (the round ran after the user's yes):** all eight corpora passed every D-354 check at 5b1f6fdf
(126,351 executions; old corpora renamed `<id>-p10.pre-regen.partial`). The gate chain G0 → A → B → D → E passed at
f0410684, the gate-D fix commit, whose stage digests equal 5b1f6fdf's. The D-354 addendum records the three changes to
the checks made during the round. Records: `round/README.md` (D-357). D-358's remaining four, the post-check and the
item-22 re-measure follow the round.


- **D-350 (method; route (a) chosen by the user 2026-10-13).** Import every corpus fresh from its pinned input (fetch
  cache; adprov-v1 from the pristine clone) into `<id>-rg1`, 8 workers, `--verify-against-pin --release`; check with
  §3.3 including `tools/regen/compare.py` against the old corpus; rename the old corpus `<id>-p10.pre-regen.partial`
  after the checks pass; record the lineage in `CHANGELOG.md` at the first seal. Rejected: the re-map (replays the
  recorded v1 after D-31); route (b) now (a core change just before the round; roadmap); re-derive only (keeps aer/0.1);
  `--input` from upstream clones (`local` origins); `--link-raw`.
- **D-351 (scope).** The round regenerates the eight working corpora only; new corpora for `planned` sources (§1.2) are
  separate imports, each on the user's request. Rejected: importing the 19 phase-10d sources in the same round (doubles
  the round and mixes first imports with regeneration).
- **D-352 (entry gate).** The round starts only when P-1..P-8 of §4 are closed and the user has said yes twice (P-9).
- **D-353 (semantics version; decided by the user 2026-10-13, recorded here).** `agentdojo.suites@2` for
  agentdojo-upstream, ROPE, Mandate, survey and adprov-v1; `@3` for AgentDyn; `inspect.agentharm@2` for AgentHarm;
  `suites@4` dropped. Requires P-4's mechanism (a recorded `@1` re-derived under `@2`/`@3` by `recompute`).
- **D-354 (checks).** §3.3, with `validate --strict --tiers` (not `--release`) and **full** validation of every
  execution of every corpus (user decision 2026-10-14; needs D-413, P-12).
- **D-355 (order).** §3.2.
- **D-356 (failure handling).** A failed check stops that corpus; the new tree stays as evidence (`<id>-rg1.partial`, not
  deleted), the old corpus is not renamed, and the finding goes to the orchestrator. A fix is a code change, so the
  rehearsal of §3.5 is repeated before the round resumes.
- **D-357 (records).** Each corpus's summaries, timings and check outputs go to `docs/reports/regeneration/round/<id>/`
  (small JSON only; no corpus bytes); `regen-batch.md` gets the measured outcome per item ("records the outcome here").
- **D-358 (old corpora reproduce at their building commit; user ruling D-430, 2026-10-14).** Each old `-p10` corpus is
  rebuilt byte for byte from its raw inputs at the commit and lockfile that built it (H.8's promise), in a scratch
  checkout outside git, before the round. At main, `recompute` of an older-version corpus reports the version drift and
  refuses `--out` (D-430, the D-31 owner). See §3.7.
- D-359: unused.

## 7b. Round obligations handed over by the regen-items session (orchestrator, 2026-10-22)

The pre-round integration branch (local `integration/pre-round-2026-10-21`, head `802d8c6d`) holds every held regen
branch, part C (aer/0.2 + corpus/0.2, D-221/D-223) and D-610; green apart from a re-check. After it lands no
`agentprov-corpus/0.1` corpus can be recomputed into new output (D-430, enforced by PR-3), so the round re-imports
(route (a)), as planned. Obligations:

1. **Item 107 census before sealing `fragfuse-agentharm` and `kexin-xu-01-agentharm`** (only if those sources are
   imported in the round, §1.2): run `$AGENTPROV_HOME/migration-work/regen-items-2-12/r107/wscan.py <corpus.partial>
   <pattern>` (scratch, counts only, never values) with each of the two `[[withhold.rules]]` patterns of the profiles over
   the round's import of each part, and `scan.py` (same folder) for 0 derived account occurrences. Expected at the pins:
   fragfuse 161 headers, 164 journals, 25 samples, 164 of 164 `.eval`; kexin 24 headers, 24 journals, 24 of 68 `.eval`;
   0 derived files for both. Any difference: revisit the rule before sealing. Kexin's `{7,32}` floor is snapshot-bound.
   The `r107/` folder is kept for this session.
2. **EnvironmentOptim v2 `[import] rules`:** `rescont = 2` if the NF rescont v2 bump lands.
3. **Item 106:** its 14 never-seal scratch corpora are listed in the PRIVACY note of `regen-batch.md`; they enter the
   pre-release never-seal check.
4. **Profile and registry byte edits for the round:** the qwencode/openhands profile comments still say "waits for
   D-530", and the `agentops` registry part stays `planned` until D-530's CLI part.
5. **Datasheet item 22 counts.** The statement `benchmark-and-model-home-paths` cites
   `docs/reports/bugpass/home-paths-classification.md` (orchestrator, `0dfe2cd0` on the integration branch: 18 names
   S1-S18 in ast-survey-agentharm, 9 benchmark / 9 model-generated; 14 names N1-N14 in agentdyn-a's github suite, 11 / 3;
   counts and case labels only), measured on the **stored** corpora. After the regenerated `ast-survey-agentharm` and
   `agentdyn-a` pass §3.3, re-run that method (D-457 shapes over every derived record, first record per name, earlier
   occurrence of the bare token, harness-derived fields) on them, counts and labels only. Equal counts: record the
   check in the classification report. Different counts, or a name that is neither benchmark nor model text: update
   the report and the statement's figures, or bring it to the user before sealing (D-604, D-186). My interim
   counts-free wording (`44534465` on `integration-fix-ultra-docs`) is superseded and not merged.

D-358 status at handover: AgentHarm, survey and adprov-v1 reproduced at `afe7038`; 2024-06 paused by the user
(2026-10-14) at 3,584 of 18,241 sealed (`out/d358-d2024.partial` kept); ROPE, head and AgentDyn not run. They resume on
the orchestrator's go; 2024-06 restarts fresh (the paused tree is renamed aside, never deleted). **Done 2026-10-23:**
all four reproduced after the round (§3.7, [`d358/`](d358/README.md)).

## 8. Follow-ups after the round (roadmap, not in the round)

- Route (b): a `recompute` upgrade mode that re-maps and re-derives under the current registry versions, classified as
  `changed_explained` by the declared profile and semantics versions (about a day in `corpus/derive.py` and the CLI;
  the D-31 owner's sizing). Every later version bump needs it, and it re-derives from the corpus's own raw store, so it
  does not depend on the fetch cache or the upstream clones.
- Closed-world expectation keys (D-359; implemented in `tools/regen/compare.py`): `sem_ev_transitions`
  (`"<type> <old>-><new>"`, annotations paired by type, target and premises) and `rule_twin_pairs`. An expectation
  file that names either key fails on any unlisted transition or pair. The round's open-world keys let Mandate's 369
  propagated outcomes pass unremarked; the re-imports use the new keys.
- `validate --corpus` workers (F-3), so a full stored-output validation of the large corpora is affordable.
- The SHACL tier, so `validate --release` can pass.
- adprov-v1's `local` origin: the release tree is gitignored at `579a908`, so its origin stays a local listing pin;
  decide before sealing whether a deposit of the baseline release (Zenodo) should become the pinned origin.
