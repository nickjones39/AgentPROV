# Pre-release checks for sealing the 8 round-1 corpora (Option A)

Date: 2026-10-28, Mac Studio. Code: `main` `8c244150` (D-810 landed), clean checkout, Python 3.14.9 (core venv; the
interpreter floor is 3.14.8). Brief: `~/.agentprov/handoff/pre-release-checks.md`. Option A is the user's final choice
(2026-10-28; D-359): the trees are sealed as built, and the `checker_outcome` I-class is disclosed, not re-imported.

**Nothing was sealed, packaged, deposited, fetched or pushed. Nothing was written inside a corpus.** Seal forecasts are
`agentprov package --dry-run` (which writes nothing; N.1.6) at this checkout. Recomputes ran `--dry-run` at each tree's
building commit, in scratch worktrees with their own Python 3.14.8 venvs. Raw objects were copied into a scratch
`TMPDIR` on another volume, so the trees' inodes were not even hard-linked. All heavy jobs went through
`tools/suite_queue.py --class import`. Counts, ordinals and digests only: this report holds no address, account name,
path, token or benchmark text. The scratch scripts and their JSON outputs are listed in section 13.

## Your decisions, in one list (each with my recommendation)

**Applied (2026-10-29, `e47258d2`).** You approved items 1–5 and 8 in this window, and item 7 ("amend statement 4 to
65"). They are applied on this branch: D-910 (C-1), the two spec comments (C-4), the statement amendment and 30 new
statements in `corpora/datasheet-statements.toml`. Item 2 is accepted as the triage plan; its tool (C-3) is for the
deposit. Item 6 was decided on 2026-10-29 (row 6), and the 8 corpora are sealed (next section). At `e47258d2`, all 8 trees pass a seal dry run
with the new statements rendered and linted (table below).

| # | Decision | Option taken | Where |
|---|---|---|---|
| 1 | **C-1, the survey seal blocker:** `ast-survey-agentdojo-rg2` fails `corpus.datasheet.lint` (AR-12) because the profile's attribution quotes a paper title with the word "Reproducible" | Class-0 fix: the datasheet renders `attribution` entries as quoted third-party credit, and the lint exempts exactly those. The alternative, `survey-runs@4` plus a re-import, is out of proportion → **Applied** (D-910, `e47258d2`). | check 8 |
| 2 | **C-3, gitleaks triage:** 2,912 findings in 6 corpora, classified by rule, key name and origin, never by value | Accept the proposed classes: upstream-data and benchmark-input → `synthetic-benchmark` (525); model-generated → `model-generated` (2,371). Build C-3, a triage-file writer from these tables, before the deposit → **Accepted**; C-3 is built before the deposit. | check 4, table 4b |
| 3 | **U-4, home-path statement:** `benchmark-and-model-home-paths` is out of date | Amend it. AgentHarm: 19 names, 9 benchmark, 10 model (#17 is `C:\Users\<name>`). agentdyn-a: all suites, 17 names in derived records, 11 suite personas, 6 by the model → **Applied.** | check 3, check 5 |
| 4 | **2024-06 licence files:** the spec says AgentDojo's LICENSE and CITATION.bib are at the pin `c2748856`, but neither exists there | Supply both from `089ed468` at sealing; correct the spec comment (C-4, class 0; spec bytes only, nothing sealed) → **Applied** (spec comment; pass `089ed468`'s files at sealing). | check 8 |
| 5 | **Building commit:** disclose, or build `--built-at` | Disclose: the two drafted `building-commit-by-digest-*` statements. `--built-at` needs a `corpus-0.2` schema change before the first seal → **Applied** (two statements). | check 7 |
| 6 | **16 unclassifiable agentdyn-a findings** (7 uncited raw files of part-c variants that are not imported, 14 `password` findings; 2 more sit in a file the seal already withholds) and **ordinal #20** (1 uncited raw file). 0 executions are affected | **Decided (2026-10-29, the user through the orchestrator, value-blind):** the 16 `password` values are `model-generated` (4 distinct values, each first seen as the `password` argument of an assistant tool call, next to `username`, in all 98 raw objects that hold one; none in the AgentDyn benchmark package); #20 is `false-positive` (a model-generated path, first seen in assistant content, under `local_dir_path`). No withholding: no C-8, no purge tombstone. | check 4 |
| 7 | **D-810 statement 4:** the seal withholds **65** uncited agentdyn-a files, not the decided wording's 40. 25 more hold one of the withheld freemail addresses (9 distinct) | Amend the decided wording (drafted: 65 files; 37 addresses in no execution's records + 9 shared with statement 3). Decided wording is yours to change → **Applied** (your message: "amend statement 4 to 65"). | check 4 |
| 8 | **Approve the remaining drafts:** D-359, D-771, D-811, PC-01, the D-810 rows, the adprov and ROPE home paths | Approve; they land in `corpora/datasheet-statements.toml` in the seal train → **Applied.** | check 5 |
| 9 | **Order** | Land 1, 4 and 8, then seal all 8 from one clean commit with `--licence-file`, then the real release scan and `verify --level chain` per tree. Optionally a scratch seal rehearsal of agentdyn-a first (a seal of a copy: needs your yes) | check 8 |

Less urgent: U-7 (`LIVE_BLOCK` → `corpus-0.3` with live sealing), U-10 (combined-release layout after the Wave-2 sizes),
U-11 (housekeeping after sealing).

## Sealed (2026-10-29)

On your typed "Seal" in this window, all 8 corpora were sealed one at a time through the queue. They were sealed from a
clean detached checkout of the pushed `main` `8bb6bc92bc458c5f03df86a2d1b81f3492e67ad0` (Python 3.14.8, offline venv
from its `uv.lock`), with `--licence-file` as in check 8 and no release date (`release.created` null). Before sealing,
seal dry runs at `cd44c83c` and at `8bb6bc92` were compared for every tree: same exit code, identical withholding
plans, and identical DATASHEET.md once the commit ids and the content-digest value are masked. Each root digest below
was recomputed independently as the sha256 of `checksums.sha256`, and each equals the release scan's target.

| Corpus | Sealed directory (`~/.agentprov/corpora/`) | Root digest | Withheld objects / executions | `verify --level chain` | Release scan |
|---|---|---|---|---|---|
| `mandate-agentdojo-eval` 0.1.0 | `mandate-agentdojo-eval-rg1` | `sha256:297c195f36427ffc6460a1512168b85e6ab1ed1483b30dfa6d306272c4691c8a` | 0 / 0 | ok, 396 executions, 1,616 files, 0 findings | 0 (0 untriaged) |
| `ast-survey-agentharm` 0.1.0 | `ast-survey-agentharm-rg2` | `sha256:ba9c2206fc207f0ff09653e353c754a5a758e257d8c6cf54db8515c7bcf9f229` | 13 / 1 | ok, 1,055 executions, 4,249 files, 0 findings | 6,540 (2,622 untriaged) |
| `ast-survey-agentdojo` 0.1.0 | `ast-survey-agentdojo-rg2` | `sha256:b1f061bfbd0e6d7f438f13c55f2f27d3e8819f63112d8a4b5e9561c58e8f58a3` | 16 / 11 | ok, 3,232 executions, 12,965 files, 0 findings | 22,965 (0 untriaged) |
| `adprov-v1-release` 0.1.0 | `adprov-v1-release-rg2` | `sha256:f90e6d33634da679ed4be35718f420b3ebae7d32887da970413d447a5cf514a1` | 8 / 8 | ok, 17,656 executions, 88,314 files, 0 findings | 137,527 (21 untriaged) |
| `rope` 0.1.0 | `rope-rg1` | `sha256:36a72042c361042ff47a40733b9fe9684759a02570090e5f4334f90ef04f6f5f` | 17 / 17 | ok, 10,774 executions, 43,166 files, 0 findings | 88,532 (313 untriaged) |
| `agentdojo-upstream-2024-06` 0.1.0 | `agentdojo-upstream-2024-06-rg1` | `sha256:843aa425e32797434a8d31eb84577e49b690f8cfc17d9b3c37ba8d88477b783a` | 10 / 10 | ok, 18,231 executions, 72,956 files, 0 findings | 94,159 (2 untriaged) |
| `agentdojo-upstream-head` 0.1.0 | `agentdojo-upstream-head-rg1` | `sha256:725509b6bd8f80f0659604620e8493e3a81c49b9147be8f8926e11c9b9aed614` | 13 / 13 | ok, 36,666 executions, 146,696 files, 0 findings | 226,256 (2 untriaged) |
| `agentdyn-a` 0.1.0 | `agentdyn-a-rg1` | `sha256:6500f7c83e1ba5293e288f00b030de767100aec384d708f4816fa6927f2542db` | 192 / 127 | ok, 38,154 executions, 162,027 files, 0 findings | 281,914 (5,485 untriaged) |

* Each withholding seal moved its private files into `<directory>.withheld/` (never released; D-231).
* The release-scan documents are in the session scratchpad, not beside the corpora. The untriaged findings are exactly
  the account-path and gitleaks findings of table 4b; every e-mail finding is cleared by rule. Once C-3 writes the
  per-root-digest triage files, the scans run again with `--triage` and the documents go beside each corpus for the
  deposit builder.
* **Triaged (2026-10-29, C-3, D-920).** `tools/release_triage.py` recomputed the classes on each sealed tree. They equal
  table 4b by rule, origin and layer, and table 4c's ordinal hits. The tool wrote `<directory>.release-triage.toml`
  beside each of the 8 trees (from `pre-release-checks/triage-decisions/<corpus>.toml`; item 6 applied as decided).
  `release_scan.py --triage` then wrote `<directory>.release-scan.json` beside each tree: every document has its sealed
  root digest, the same fingerprints as the seal-time scan, **0 untriaged and 0 `real`**, and records its triage
  file's sha256. Nothing inside a sealed tree was written. Untriaged before → after: agentharm 2,622 → 0, adprov 21 → 0,
  rope 313 → 0, 2024-06 2 → 0, head 2 → 0, agentdyn-a 5,485 → 0; mandate and ast-survey-agentdojo stay at 0, each with
  an empty triage file.
* `ast-survey-agentdojo` and `mandate-agentdojo-eval` already scan clean (exit 0).
* Not sealed, as planned: the never-seal trees `ast-survey-agentdojo-rg1`, `adprov-v1-release-rg1` and
  `ast-survey-agentharm-rg1`, and the 8 `-p10.pre-regen` copies (section 9).

## Verdicts (before sealing)

All 8 trees were checked, and every decision but item 6 is applied. Final seal dry run at `e47258d2`: a clean checkout,
licence files supplied, and the new statements rendered and linted.

| Tree to seal | Executions | Seal dry run at `e47258d2` | Withheld at sealing: objects / executions | Recompute `--dry-run` at the building commit | Verdict |
|---|---:|---|---|---|---|
| `mandate-agentdojo-eval-rg1` | 396 | pass | 0 / 0 | `5b1f6fdf`: 396/396 identical at 8 and 3 workers | **ready** |
| `ast-survey-agentharm-rg2` | 1,056 | pass | 13 / 1 (D-811: 6 + 6; D-810: 1) | `5fc39c16`: 1,056/1,056 at 8 and 3 | **ready** |
| `ast-survey-agentdojo-rg2` | 3,243 | pass (blocked at `8c244150`, AR-12; fixed by D-910) | 16 / 11 (D-771: 5; D-810: 11) | `d93aa261`: 3,243/3,243 at 8 and 3 | **ready** |
| `adprov-v1-release-rg2` | 17,664 | pass | 8 / 8 (D-810) | `5b1f6fdf`: 17,664/17,664 at 8 and 16 | **ready** |
| `rope-rg1` | 10,791 | pass | 17 / 17 (D-810) | `5b1f6fdf`: 10,791/10,791 at 8 and 16 | **ready** |
| `agentdojo-upstream-2024-06-rg1` | 18,241 | pass (licence files from `089ed468`) | 10 / 10 (D-810) | `5b1f6fdf`: 18,241/18,241 at 8 and 16 | **ready** |
| `agentdojo-upstream-head-rg1` | 36,679 | pass | 13 / 13 (D-810) | `5b1f6fdf`: 36,679/36,679 at 8 and 16 | **ready** |
| `agentdyn-a-rg1` | 38,281 | pass | 192 / 127 (D-810: 127 primary objects + 65 uncited) | `5b1f6fdf`: 38,281/38,281 at 8 and 16 | **ready**; item 6 before the deposit |

"Ready" means ready for your sealing yes, once `e47258d2` (or the train that carries it) is on the sealing checkout.
Seal all 8 from one clean commit, with `--licence-file` for every tree except Mandate. The release-scan triage
(table 4b) is a deposit gate, and the deposit is deferred to the combined release (section 10).

## 1. Stray sealed copies and the never-seal list

**Scan of all of `~/.agentprov`** (every `corpus.json`, `DEPOSIT-MANIFEST.json`, `deposit-metadata.json`,
`WITHHELD.json`, `*.release-scan.json` and `*.withheld` sidecar, at any depth; `locks/` skipped):

| What | Found |
|---|---|
| Sealed corpora (`corpus.json` with `sealed: true` or `state` other than `working`) | **0** |
| Deposit bundles (`DEPOSIT-MANIFEST.json`, `deposit-metadata.json`) | **0** |
| `WITHHELD.json` or `DIR.withheld/` sidecars | **0** |
| Release-scan documents | **0** |
| Working corpora | 22 at the time of the scan, all in `~/.agentprov/corpora/`, all `sealed: false`, `state: working`, `mode: import` (the 8 trees, the 11 below, and Wave-2 trees `*-w2.partial` being imported) |
| Other `corpus.json` files | 3, upstream payload lists inside a staging clone (`staging/10c/menelaus29/.../src/payloads/corpus.json`), not AgentPROV corpora |

**Scratch corpora named by the brief are not on this machine.** No `corpus.json` or `derivation.json` exists outside
`~/.agentprov/corpora/`. The interbolt l2-head-j1/-j2 and the 12 controlarena v2 corpora (pre-check scratch), the
credleak v1 copies (`gui-build/pkg`, `phase10k/c2seal`; trashed 2026-10-22 on the MacBook) and the 10o qwen-j2/j2b trials
were not copied to the Studio. `migration-work/precheck/` holds only L1 rows, `_fp/`, `_ops/` and 34 empty `exam/`
folders (section 9).

**`package` refuses every tree that must not be sealed** (dry runs at this checkout with today's specs; licence files
supplied where the refusal would come later):

| Tree | Refusal |
|---|---|
| `ast-survey-agentdojo-rg1` | `package.refused.spec` (survey-runs@2; the spec names @3) |
| `ast-survey-agentharm-rg1` | `package.refused.spec` (survey-agentharm@1; the spec names @2) |
| `adprov-v1-release-rg1` | `package.refused.stages` (no `adprov-v2.3-compat` PROV; after a full withholding plan) |
| the 8 `-p10.pre-regen` safety copies | `package.refused.spec` each (they record the pre-round profiles) |

`package` seals only the one `--corpus` it is given, and the deposit mode accepts sealed corpora only (there are none),
so nothing can be picked up by accident. **Result: pass.**

## 2. Masked value-level comparison rg1 → rg2 (`ast-survey-agentdojo`, `ast-survey-agentharm`)

**Method** (`prov_compare.py`, section 13). Every execution of both trees (3,243 and 1,056) was read on both sides:
the `agentprov-prov/0.1` PROV document, the AER and the SEM file. Each document becomes a multiset of records (one per
PROV statement, AER record or SEM line), and the two multisets are compared per execution. The masks, applied the same
way to both sides, are exactly these:

1. **Content-addressed identifiers:** record and blank-node ids (16 or 26 base32 characters), mention ids (`mn-` and 12),
   and the AER and SEM document digests inside ids (`xd:aer.<hex>`, `xd:sem.<profile>.<hex>`).
2. **Digest cascade fields:** `apv:derivationKey`, `apv:sha256` of the `xd:aer.` and `xd:sem.` entities, the AER and SEM
   `seal.records_sha256`, and the SEM `aer_digest`. Each is a digest over inputs that include the AER digest.
3. **The profile reference:** the AER `execution.profile` record, whose changes are reported separately.

Nothing else is masked. Rule ids, evidence classes, catalogue and profile digests, raw-object digests, software
versions and every data value are compared as they are.

| Tree pair | Executions | PROV equal after masking | AER equal | SEM equal | Record counts equal |
|---|---:|---:|---:|---:|---:|
| `ast-survey-agentdojo` rg1 (`5b1f6fdf`) → rg2 (`d93aa261`) | 3,243 | **3,243** | 3,243 | 3,243 | 3,243 |
| `ast-survey-agentharm` rg1 (`5b1f6fdf`) → rg2 (`5fc39c16`) | 1,056 | **1,056** | 1,056 | 1,056 | 1,056 |

**The only root difference is the profile reference, as predicted.** In every execution `execution.profile` changes
in `version` and `sha256` only:

| Tree pair | Profile | Old sha256 = | New sha256 = |
|---|---|---|---|
| survey | `survey-runs` 2 → 3 | `profiles/archive/survey-runs.profile.v2.toml` (`5bcaf980…`) | shipped `survey-runs.profile.toml` (`ad3bb341…`) |
| agentharm | `survey-agentharm` 1 → 2 | `profiles/archive/survey-agentharm.profile.v1.toml` (`b303208a…`) | shipped `survey-agentharm.profile.toml` (`6c9df117…`) |

Both bumps are the `[withhold]` tables of D-771 and D-811. Every other difference is that change's digest cascade
(masks 1 and 2). The code moved between `5b1f6fdf` and `d93aa261` or `5fc39c16` (the `aer` engine digest), but it
changed no PROV, AER or SEM value. The withholding itself acts at sealing, so the raw stores are equal (post-check PC1).
The withheld objects are in check 4.

*Limit:* masking ids compares link targets by their masked form, so a permutation of links between records with
identical masked content would not show. Every id here is content-addressed from the same inputs, so such a
permutation would also change other records. A first run also produced 52 spurious differences: a 64-hex digest whose
first 16 characters are base32-shaped was half-masked. They disappeared once the digest mask was matched first.
**Result: pass; every difference predicted.**

## 3. AgentHarm home-path ordinals: 19 vs 18 (reconciled)

Read in memory from `ast-survey-agentharm-rg2`. No name was printed, and the `_ops` digest→ordinal map was not opened
(`homepath_reconcile.py`, section 13). There are three counts, not two:

| Count | Method | Result |
|---|---|---:|
| Post-check scan ordinals | `post_check.py` `_account_ordinals`: D-457 forms over every stored file, trailing dots stripped | 20 = **19** names in the AER + **#20**, raw objects only |
| Item-22 re-measure | `tools/regen/homepath_remeasure.py`: D-457 over AER records and PROV files, names as matched | 23 = the same 19 + 4 trailing-dot variants (#4, #6, #7, #13; #14 and #17 occur only with a dot) |
| Bug-pass classification | `home-paths-classification.md`: the `/home/<name>` paths | **18** |

* **#20** is the survey author's account in the 6 `.eval` `header.json` members. D-811 withholds those members (check 4:
  `withheld` in the seal plan). It is in no AER or PROV file.
* **The 19th name is #17**, the only Windows-form path (`<drive>:\Users\<name>`; 14 characters). It has 4 hits (2 AER
  files, 2 raw objects, 1 execution), and its first appearance is an assistant message with no earlier token. The other
  18 are POSIX `/home/<name>` paths, the classification's S1–S18. The classification counted `/home/` paths only.
* **Cross-check against the classification's 9/9 split** (first appearance per execution, from the AER):
  - benchmark-first (the execution header or fixture, or a tool result first): #1–#8, 8 names;
  - assistant-first with the bare token earlier in tool output in every execution: #10 (the classification's S10,
    "a common English word", benchmark);
  - assistant-first with no benchmark source: #9, #11–#16, #18, #19, which is 9, the classification's 9 model-generated;
  - #17 (Windows form): assistant-first, not in the AgentHarm data, which makes a 10th model-generated name.

So the 19 released ordinals are 9 synthetic-benchmark and 10 model-generated, and the model-generated ones are triaged
`false-positive` (a model-generated path), as the classification did. **Datasheet consequence:** the statement
`benchmark-and-model-home-paths` says "(/home/<name>/)" with figures 18, 9 and 9. It omits #17. Either amend its text and
figures (19 names, 10 model) or leave it as it is with #17 triaged separately. A draft is in check 5, and the choice is
decision U-4. **Result: reconciled; no new account.**

## 4. Release-scan triage per corpus

**No pre-seal mode exists in `tools/release_scan.py`.** It refuses a working tree, apart from `--list-addresses`. The
forecast (`forecast.py`, section 13) therefore calls the tool's own functions at this checkout with its real rules:

* gitleaks 8.30.1 with the release configuration and the D-310 key-cut check;
* the native path scan with archives decoded (D-491): home path, host name, D-457 account paths, D-600 secret shapes;
* the D-810 e-mail rule, with path-scan version 6 and the spec's persona files read from the repository, each checked
  against the sha256 the spec records, as sealing copies them;
* the acct-label allowlist (`REDACTION_LABEL`) and the account allowlist.

Each finding is labelled *withheld* when its file leaves at sealing, according to the withholding plan captured from
that tree's own `package --dry-run`. Files that sealing adds (`rules/`, `LICENSES/`, `DATASHEET.md`) hold digests and
our own text only; they are not forecast. The real scan runs after sealing, on the sealed root digest (D-42).

### 4a. D-810: the counts reproduce

In every tree, every released `email-address` finding is cleared by a rule, and every untriaged e-mail finding sits in
a file the seal withholds.

| Corpus | upstream-data / benchmark-input addresses (released) | model-generated: addresses / released executions | withhold: addresses / executions (share; by suite; tasks) | design (sec. 13–14) |
|---|---|---|---|---|
| ast-survey-agentharm | 46 / 20 | 16 / 12 | 1 / 1 (0.09 %; `inspect_evals/agentharm` 1; 1) | equal |
| ast-survey-agentdojo | 76 / 4 | 10 / 22 | 3 / 11 (0.34 %; workspace 11; 7) | equal |
| rope | 93 / 0 | 21 / 68 | 6 / 17 (0.16 %; dailylife 10, github 7; 5) | equal; 68 = 69 − 1 withheld execution |
| agentdojo-upstream-2024-06 | 83 / 0 | 21 / 123 | 3 / 10 (0.05 %; slack 1, workspace 9; 4) | equal |
| adprov-v1-release | 81 / 4 | 48 / 247 | 9 / 8 (0.05 %; slack 1, travel 1, workspace 6; 7) | equal; 247 = 248 − 1 withheld |
| agentdojo-upstream-head | 83 / 0 | 28 / 282 | 4 / 13 (0.04 %; slack 3, workspace 10; 5) | equal |
| agentdyn-a | 35 / 8 | 219 / 762 | 57 / 127 (0.33 %; dailylife 70, github 55, shopping 2; 22) | equal except: 8 = 9 − 1 and 219 = 220 − 1 (one address of each class occurs only in withheld files); 762 = 777 − 15 withheld executions |
| **Total** | | | **83 / 187** | **equal** |

**One difference that needs a decision (item 7).** agentdyn-a's `withhold-object` class holds the decided 37
addresses, but the seal withholds **192** raw objects. They are 127 primary objects of the withheld executions plus
**65** uncited raw run files (part-c variants that are not imported), not 40. 37 of the 65 hold a `withhold-object`
address (3 of them also a `withhold` one). The other 25 hold only one of 9 distinct `withhold`-class addresses: a
model-written freemail address that also occurs in a withheld execution. The `address` rule withholds every object
holding such a digest, as D-810 section 14 designed. Sections 13 and 14 counted only the `withhold-object` files. No
execution is affected. Statement 4 as decided ("40 files … addresses that occur in no execution's records") would be
wrong, so an amended wording is drafted.

### 4b. Gitleaks: every finding with its proposed class (by key name and origin, never by value)

Origin, from the pinned gitleaks report and the tree:
* **upstream-data:** a 16+ character token of the finding's line (or the `private-key` header) occurs in the
  benchmark's own suite data: the AgentDojo package suites, AgentDyn's suites, or the AgentHarm data;
* **benchmark-input:** an AER record that the benchmark supplies (execution header, fixture, scope, actor, or a user,
  tool, system or environment message);
* **model-generated:** an AER record the model writes (assistant message, tool call, the state change after a call);
* a PROV or raw-object copy takes the origin of its execution's AER finding with the same rule and key (in line order
  when an execution has several);
* **unclassified:** none of these. The conservative proposal is then withhold.

The per-finding rows (rule, layer, file as a 12-hex digest, line, key name, origin, proposed class, state) are in
`pre-release-checks/gitleaks-<corpus>.tsv` beside this report.

| Corpus | Rule | Key name | Origin | Findings by layer (aer / prov / raw-object) | Proposed class | State |
|---|---|---|---|---|---|---|
| ast-survey-agentharm | `facebook-secret` | `(none)` | upstream-data | 1 (0 / 0 / 1) | **synthetic-benchmark** | released |
| ast-survey-agentharm | `generic-api-key` | `(none)` | upstream-data | 19 (0 / 0 / 19) | **synthetic-benchmark** | released |
| ast-survey-agentharm | `generic-api-key` | `encryption_key` | model-generated | 26 (26 / 0 / 0) | **model-generated** | released |
| ast-survey-agentharm | `generic-api-key` | `encryption_key` | upstream-data | 18 (6 / 0 / 12) | **synthetic-benchmark** | released |
| ast-survey-agentharm | `generic-api-key` | `is` | benchmark-input | 4 (4 / 0 / 0) | **synthetic-benchmark** | released |
| ast-survey-agentharm | `generic-api-key` | `is` | model-generated | 4 (4 / 0 / 0) | **model-generated** | released |
| ast-survey-agentharm | `generic-api-key` | `key` | benchmark-input | 13 (10 / 3 / 0) | **synthetic-benchmark** | released |
| ast-survey-agentharm | `generic-api-key` | `key` | model-generated | 27 (26 / 1 / 0) | **model-generated** | released |
| ast-survey-agentharm | `generic-api-key` | `key` | upstream-data | 2 (0 / 0 / 2) | **synthetic-benchmark** | released |
| adprov-v1-release | `generic-api-key` | `password` | model-generated | 2 (1 / 0 / 1) | **model-generated** | released |
| adprov-v1-release | `generic-api-key` | `password` | upstream-data | 2 (1 / 0 / 1) | **synthetic-benchmark** | released |
| rope | `generic-api-key` | `Audit_Token` | upstream-data | 2 (0 / 0 / 2) | **synthetic-benchmark** | released |
| rope | `generic-api-key` | `Validation_Token_Header` | upstream-data | 4 (0 / 0 / 4) | **synthetic-benchmark** | released |
| rope | `generic-api-key` | `Verification_Token` | upstream-data | 26 (12 / 0 / 14) | **synthetic-benchmark** | released |
| rope | `generic-api-key` | `password` | model-generated | 100 (50 / 0 / 50) | **model-generated** | released |
| rope | `generic-api-key` | `ssh_key` | upstream-data | 4 (2 / 0 / 2) | **synthetic-benchmark** | released |
| rope | `private-key` | `(none)` | upstream-data | 156 (74 / 4 / 78) | **synthetic-benchmark** | released |
| agentdojo-upstream-2024-06 | `generic-api-key` | `token` | model-generated | 2 (1 / 0 / 1) | **model-generated** | released |
| agentdojo-upstream-head | `generic-api-key` | `token` | model-generated | 2 (1 / 0 / 1) | **model-generated** | released |
| agentdyn-a | `generic-api-key` | `is` | upstream-data | 8 (4 / 0 / 4) | **synthetic-benchmark** | released |
| agentdyn-a | `generic-api-key` | `key` | upstream-data | 12 (4 / 0 / 8) | **synthetic-benchmark** | released |
| agentdyn-a | `generic-api-key` | `password` | model-generated | 2194 (1097 / 0 / 1097) | **model-generated** | released |
| agentdyn-a | `generic-api-key` | `password` | unclassified | 14 (0 / 0 / 14) | **withhold** | released |
| agentdyn-a | `generic-api-key` | `password` | unclassified | 2 (0 / 0 / 2) | **withhold** | withheld |
| agentdyn-a | `generic-api-key` | `password` | upstream-data | 2 (1 / 0 / 1) | **synthetic-benchmark** | released |
| agentdyn-a | `generic-api-key` | `requested` | upstream-data | 8 (4 / 0 / 4) | **synthetic-benchmark** | released |
| agentdyn-a | `generic-api-key` | `token` | model-generated | 8 (4 / 0 / 4) | **model-generated** | released |
| agentdyn-a | `private-key` | `(none)` | model-generated | 6 (3 / 1 / 2) | **model-generated** | released |
| agentdyn-a | `private-key` | `(none)` | upstream-data | 244 (136 / 5 / 103) | **synthetic-benchmark** | released |

Totals: model-generated (released) 2,371; synthetic-benchmark (released) 525; withhold (released) 14; withhold (withheld) 2. ast-survey-agentdojo and mandate have no gitleaks finding.

* agentdyn-a's `private-key`: 244 are the AgentDyn fixture key and 6 are model-written (3 AER records, 1 PROV, 2 raw
  copies). The post-check's line check gave 243 and 7. Here a raw or PROV copy follows its execution's AER finding, and
  that moves 1 finding.
* **The 14 + 2 unclassified** (decided under item 6 on 2026-10-29: `model-generated`; the table rows now say `model-generated (item 6)`) are `password` values in 7 + 1 uncited raw files of agentdyn-a's part-c variants. They map
  to no execution, so no AER record gives their origin. Their pattern matches the 2,194 model-written `password`
  values of the imported variants, but under the rule above that is not enough. Item 6.

### 4c. Account paths (D-457), released files

| Corpus | Ordinals | Classes | Basis |
|---|---|---|---|
| mandate, 2024-06, head | 0 | — | — |
| ast-survey-agentdojo | 1 (#1, 58 matches) | **withheld** | raw only: the 5 console logs of D-771 |
| ast-survey-agentharm | 19 released + #20 withheld | 9 `synthetic-benchmark`, 10 `false-positive` (model-generated path) | check 3 |
| adprov-v1-release | 1 | `synthetic-benchmark` | the name is in the AgentDojo suite data; the model writes it into paths (assistant, tool call) |
| rope | 2 | `synthetic-benchmark` | AgentDyn suite persona names |
| agentdyn-a | 20 | 11 `synthetic-benchmark` (#2, #4–#6, #9–#11, #13, #15–#17: names in the AgentDyn suite data); 6 `false-positive` (#1, #3, #7, #8, #12, #14: not in the suite data; they occur in assistant messages and tool calls, and in tool results that echo them; model-generated paths, as the bug-pass classification found for its github names N6, N9 and N13); #18, #19 `false-positive` (tool-call argument keys `file_path`, `source_path`, post-check); **#20 unclassified** | #18–#20 each in 1 uncited raw file (part-c). #20 sits under mixed keys (`content`, `local_dir_path`, `path`) → item 6: decided `false-positive` (a model-generated path) |

No D-600 shape (`ghp_`, `gho_`, `ghu_`/`ghs_`, `ghr_`, `github_pat_`, `hf_`, `sk-lf-`/`pk-lf-`) and no `home-path` or
`host-name` finding occurs in any of the 8 trees, archive members included.

## 5. Datasheet statements

**How drafts were checked.** Each draft was appended to the committed `corpora/datasheet-statements.toml` and loaded with
the strict loader (`load_statements`: closed keys, every figure declared and used, unique ids). Each text then passed
the card lint as sealing applies it (`mode: import` front matter). Each text with its figures filled also passed the
datasheet claims lint (AR-12, scope words, NC rules; the whole-document G.8.5 rule set aside, since it does not apply to
a fragment). All 31 drafts pass all three. The drafts are in `pre-release-checks.drafts.toml` beside this report. They
are **not** in `corpora/datasheet-statements.toml`: they go there only after the user approves them in this window.

| Required statement | State | Draft id(s) / existing id |
|---|---|---|
| adprov / ROPE home-path sentence (POST-adprov-v1-release-02) | **missing → drafted** | `model-home-paths-adprov-v1-release` (1 name, from the AgentDojo suite data, written by the model); `benchmark-home-paths-rope` (2 AgentDyn persona names) |
| D-359 I-class (Mandate 369, head 11,236 security outcomes D→I) | **missing → drafted**; figures **re-counted exactly** from the SEM layer, p10 → rg1 | `checker-outcome-inferred` |
| D-771 withholding | **missing → drafted**; 5 objects, 0 executions (seal plan) | `survey-console-logs-withheld` |
| D-811 withholding | **missing → drafted**; 6 header members + 6 `.eval` = 12 objects, 0 executions (seal plan) | `survey-agentharm-eval-headers-withheld` |
| D-810's four statements (decided wording, sec. 13) | **drafted as decided, one row per corpus**, for all 7 corpora with addresses; figures from each tree's seal plan and forecast (check 4a). Statement 4 (agentdyn-a) needs the amended wording of item 7 (65 files, not 40). Mandate holds no address, so it has no row | `fictional-benchmark-personas-<corpus>`, `model-generated-addresses-kept-<corpus>`, `model-freemail-addresses-withheld-<corpus>`, `uncited-raw-objects-withheld-agentdyn-a` (amended) |
| PC-01 (AgentHarm bundled-file tools fail; inspect_evals #2439) | **missing → drafted**; **re-counted exactly**: 63 of 1,056 samples (benign 40, harmful 23 of 528 each; read_file 84 calls, convert_pdf_to_text 62) | `agentharm-bundled-file-tools-fail` |
| acct-label guessability (D-604/D-182) | **exists** | `redaction-labels-guessable` (`corpora = ["*"]`; its text is conditional, and none of the 8 carries an acct label) |
| EnvironmentOptim path (D-604 exception) | **exists**; applies to `environmentoptim-agentdojo`, none of these 8 | `environmentoptim-raw-paths-account-segment` |
| gemini-2.5-pro utility under attack | **exists** (agentdyn-a). It is **row 18** of `datasheet-items.md` (the brief says 17) | `agentdyn-gemini-2-5-pro-undefended` |
| AgentDyn fixture key | **exists** (agentdyn-a, rope; 111 files). It is **row 19** (the brief says 18). ROPE's 156 `private-key` findings confirm it applies to rope | `agentdyn-suite-fixture-key` |
| benchmark and model `/home/` paths (optional) | **exists** (ast-survey-agentharm, agentdyn-a) but is **out of date**: for AgentHarm it says 18 names, 9 by the model, and `/home/<name>/`, while the tree holds 19 with 10 by the model (#17 is `C:\Users\<name>`); for agentdyn-a it covers the github suite only (14 names) while the derived records hold 17 over all suites, plus 3 raw-only | replacement drafted: `benchmark-and-model-home-paths-amended` (item 3, U-4) |
| Building commit (check 7, if disclosed) | **new, drafted** | `building-commit-by-digest-5b1f6fdf` (six trees), `building-commit-by-digest-d93aa261` (survey) |

**D-359 context for the statement (not part of it):** in `agentdojo-upstream-head` a further 9,292 security outcomes and
10,679 utility outcomes are class I because their own rule is the `_unverified` twin (item 3 / D-80). That is design,
not D-359. Over the corpus, 20,528 of 33,027 security outcomes and 10,679 of 36,573 utility outcomes are class I. In
Mandate, all 396 utility outcomes stay D.

## 6. The live-block closure (`corpus/manifest.py` `LIVE_BLOCK`)

**Not needed before sealing these 8.** From the seal path:

* `package` refuses a live corpus before anything else, with exit 5 (`package.unsupported.live`). It checks twice:
  `corpus.json` `mode: live` (D-666), and any index row whose `mode` is not `import`.
* The seal writes `"live": None` into every sealed manifest, unconditionally (`corpus/package.py`, the manifest block).
  The working live block is never copied.
* All 8 trees are `mode: import`, with no `live` key in their working manifests, and every dry run passes the row-mode
  check.

**But it has a timing consequence that the user should know before the seal.** The published
`schemas/corpus-0.2.schema.json` contains `LIVE_BLOCK`'s closed shape (eight keys). Sealing copies that schema into
each corpus, and `verify --level chain` compares it byte for byte with the package (D-163, P-2). Once the first of
these 8 is sealed under `agentprov-corpus/0.2`, the schema's bytes are frozen. Closing the live block (adding
`egress` (D-664), `quality` and `attack_caches`) then needs a new schema version (`corpus-0.3`), not an in-place
amendment as D-780 did. Closing it is also more than three keys. The working live block written by `run` carries
about 25 keys (transport, endpoint, plan and config digests, local models, accepted served models, caps, egress,
quality, attack caches...). Deciding which of them a sealed live corpus publishes is design work for when live sealing
is built. **Recommendation:** seal now, and give the live-seal support its own design with `corpus-0.3` (C-6, class 0).
Decision U-7.

## 7. The building commit

**What the seal records today** (`corpus/package.py`, the producer block; `corpus/datasheet.py` `_building`):

* `producer.git_commit` and `git_tree_clean`: the **sealing** checkout (release mode refuses an unknown commit or a
  dirty tree: `package.refused.git`), plus `distributions_sha256` and the zlib version of the sealing environment;
* from the working manifest: `agentprov_version`, `python` (3.14.8 for all 8), `platform`, `key_distributions`,
  `lockfile_sha256` and `isolation`;
* `build_steps` only when the working manifest has them. **Correction to the brief:** 7 of the 8 predate D-780 and record
  no building commit, but `ast-survey-agentharm-rg2` does: `build_steps = [import at 5fc39c16…, clean, stages aer, expand,
  prov, sem, validation]`. Its datasheet will say "import at commit `5fc39c16…`, which wrote aer, expand, prov, sem,
  validation". The other 7 will say "building commit not recorded";
* `derivation.json` (sealed with the corpus) keeps each stage's code digests. That is how the building commits were
  found (`tools/regen/find_building_commit.py`, D-358), and how this check reproduced each tree (section 8: 0 differences
  at `5b1f6fdf` and `d93aa261`).

**What `--built-at <commit>` would add** (design §7, not built): a build step `{command: import, git_commit, basis:
stage_digests_match}`, written after the sealer recomputes every stage digest from that commit's tree (git plumbing,
no checkout) and requires equality with `derivation.json`. The datasheet line would then name the commit. It proves "a
commit with equal stage digests", not "the commit that ran", and the record says so.

**Its cost, beyond the code:**

1. `build_steps` items are a closed shape in the published `corpus-0.2` schema (`additionalProperties: false`;
   no `basis` key). Adding `basis` means amending `corpus-0.2` **before the first seal** (the D-780 precedent; class 0,
   with a before/after stage-digest proof), or `corpus-0.3`. A sealed corpus is never rewritten, so an attestation added
   later needs a new corpus version of every tree.
2. `find_building_commit.py` must take D-451's directory closures first (design §7).
3. Tests (the dirty, absent and mismatching commit cases), the H.2.7 spec, and the user guide. Estimate: about a day for
   one session, then a train before the seal.

**Recommendation: disclose, do not build** (decision U-6). The attestation proves no more than D-358 and this check
already prove (equal stage digests and a byte-identical dry run at the commit). Building it now puts a schema change
into the window just before the seal. Two drafted statements (check 5, `building-commit-by-digest-*`) name the commits
and cite the evidence. They cost one table row each and touch no code or schema.

## 8. Seal rehearsal

**Dry seal** (`agentprov package --corpus <tree> --corpus-version 0.1.0 --spec corpora/<id>/corpus-spec.toml
[--licence-file NAME=PATH]... --dry-run`, at `main` `8c244150` (2024-06, head and agentdyn-a at `f6dab4da`, which is `8c244150` plus this report), clean checkout; in-process, with the withholding plan
captured; through the queue). It writes nothing (N.1.6). Exact refusals:

| Tree | Without `--licence-file` | With the licence files | Content digest of the forecast |
|---|---|---|---|
| mandate | exit 0 (its LICENSE is a raw object at the pin) | — | `sha256:bedeeea7…` |
| ast-survey-agentharm-rg2 | exit 4 `package.refused.licence_file` (LICENSE, AgentHarm-LICENSE) | exit 0 | `sha256:10e86c5a…` |
| ast-survey-agentdojo-rg2 | exit 4 `package.refused.licence_file` (LICENSE) | **exit 1 `corpus.datasheet.lint`**: "DATASHEET.md:200: AR-12 use 'derivation-reproducible'" | — |
| adprov-v1-release-rg2 | (spec: LICENSE, AgentDojo-LICENSE) | exit 0 | `sha256:b40c7258…` |
| rope-rg1 | (spec: LICENSE) | exit 0 | `sha256:da0f01de…` |
| agentdojo-upstream-2024-06-rg1 | (spec: LICENSE, CITATION.bib) | exit 0 (files from `089ed468`) | `sha256:930c2b08…` |
| agentdojo-upstream-head-rg1 | (spec: LICENSE, CITATION.bib) | exit 0 | `sha256:19a2ef3d…` |
| agentdyn-a-rg1 | (spec: LICENSE) | exit 0 | `sha256:15063ff4…` |

The content digests change at the real seal with the licence files supplied there, the release date and the
statements added, so they are for comparison only.

* **The survey refusal (blocking at `8c244150`; fixed by D-910, applied in `e47258d2`, where the dry run passes).** Line 200 is in "Distribution and licensing". It renders the `attribution` of
  `survey-runs@3`'s `[licence]` table, which quotes the title of the survey's Zenodo artefact, and that title contains the
  word "Reproducible". AR-12 forbids an unqualified "reproducible" anywhere in a datasheet (L.2.1), and nothing exempts a
  quoted third-party title. The post-check's seal forecast ran the card lint but did not render the datasheet, so it
  missed this. The regeneration round's `package --dry-run` covered AgentHarm only. Fixing the profile text would be a
  D-31 bump and a re-import (class 1), so the recommended fix is C-1 (class 0).
* **Licence files (U-8).** Seven of the eight specs name upstream licence files that the corpus does not store, so
  sealing needs `--licence-file` for each, and `NOTICE.md` records them as "supplied at sealing (not verified against a
  pin)". This check used pinned copies read offline (`GIT_NO_LAZY_FETCH=1`, local clones and the fetch cache; nothing
  fetched):
  - AgentDojo at `089ed468`: LICENSE, CITATION.bib;
  - AgentDyn at `5353cf76`: LICENSE;
  - ROPE at `64495e16`: LICENSE;
  - the survey repository at `89c4db2c`: LICENSE (the CC BY 4.0 legal code), also used as adprov's LICENSE;
  - the AgentHarm HF dataset at `e23b3fe6`: LICENSE;
  - for adprov's AgentDojo-LICENSE, the AgentDojo-PROV v2.3 release's `AGENTDOJO-LICENSE.txt` (byte-equal to AgentDojo's
    MIT LICENSE).

  Two mismatches with the specs:
  - **`agentdojo-upstream-2024-06`:** the spec says LICENSE and CITATION.bib are "AgentDojo's at the pinned commit", but
    `c2748856` has neither. LICENSE was added in `bd533515` (2024-06-10) and CITATION.bib in `ef848f3d` (2024-06-21), both
    ancestors of `089ed468`. The forecast used `089ed468`'s files.
  - **`adprov-v1-release`:** the spec's LICENSE is the CC-BY-4.0 legal code. The AgentDojo-PROV release folder's own
    `LICENSE` is the MIT code licence, not that text, so it must not be supplied by mistake.
* **Interpreter floor.** 3.14.8 (`envinfo.INTERPRETER_FLOOR`). Every tree records `python 3.14.8` and
  `interpreter_advisory: null`, so `refuse_advisory_manifest` passes. The core venv here runs 3.14.9. The seal's
  withholding scan opens archives in release mode, which refuses any interpreter below the floor.
* **Release mode needs a clean tree and one commit.** `package.refused.git` is raised when `git status --porcelain`
  (untracked files included) is not empty or the commit is unknown. This check hit it once, when a draft of this report
  sat untracked in the worktree. The main checkout was clean (0 lines) at the time of the check. Seal all 8 from **one**
  commit of a clean checkout, so that `producer.git_commit` is the same for the set. Seal after C-1 and the statements
  land, and before any class-1 change.
* **`verify --release`** needs a sealed tree and a root digest published outside it (D-39, D-641), so it is a post-seal
  step, as is the real `tools/release_scan.py`. On a working tree, `verify` reports `checksums.absent` (unverified), as
  expected.
* **Recompute `--dry-run` at the building commit, two worker counts** (scratch worktrees `~/.agentprov/merge-train/prc-*`
  with Python 3.14.8 venvs synced offline from each commit's `uv.lock`; `TMPDIR` in the session scratchpad):

| Tree | Building commit | Workers | Selected | Identical | Changed (explained / unexplained) | Failed | Unverified |
|---|---|---|---:|---:|---|---:|---:|
| mandate | `5b1f6fdf` | 8, 3 | 396 | 396, 396 | 0 / 0 | 0 | 0 |
| ast-survey-agentharm-rg2 | `5fc39c16` | 8, 3 | 1,056 | 1,056, 1,056 | 0 / 0 | 0 | 0 |
| ast-survey-agentdojo-rg2 | `d93aa261` | 8, 3 | 3,243 | 3,243, 3,243 | 0 / 0 | 0 | 0 |
| adprov-v1-release-rg2 | `5b1f6fdf` | 8, 16 | 17,664 | 17,664, 17,664 | 0 / 0 | 0 | 0 |
| rope-rg1 | `5b1f6fdf` | 8, 16 | 10,791 | 10,791, 10,791 | 0 / 0 | 0 | 0 |
| agentdojo-upstream-2024-06-rg1 | `5b1f6fdf` | 8, 16 | 18,241 | 18,241, 18,241 | 0 / 0 | 0 | 0 |
| agentdojo-upstream-head-rg1 | `5b1f6fdf` | 8, 16 | 36,679 | 36,679, 36,679 | 0 / 0 | 0 | 0 |
| agentdyn-a-rg1 | `5b1f6fdf` | 8, 16 | 38,281 | 38,281, 38,281 | 0 / 0 | 0 | 0 |

The large trees use 16 rather than 3 as their second worker count. That is a different count, as determinism requires,
and it fits a shared machine. The only notice was adprov's standing regression-oracle note. At these commits there was
no code-drift notice.

## 9. Housekeeping list (for the user; nothing touched)

With Option A kept, these can go to the Trash **after** the 8 trees are sealed and verified. Each needs the user's ok
first, and nothing is permanently deleted.

| Item | Size | Contents |
|---|---:|---|
| `migration-work/precheck/*/l1-units-*.jsonl` (L1 rows) | 358 MB | 79 files over 48 pre-check corpora |
| `migration-work/precheck/_fp/` | 181 MB | 58 per-part row files (private) |
| `migration-work/precheck/*/exam/` | 0 B | 34 empty folders |
| `migration-work/precheck/postcheck/` | 0 B | empty |
| `corpora/*-p10.pre-regen.partial` (8 safety copies) | **34.6 GB** | mandate 0.07, survey-agentharm 0.30, survey-agentdojo 0.73, adprov 3.28, 2024-06 3.53, rope 4.87, head 7.54, agentdyn-a 14.24 GB |
| `corpora/ast-survey-agentdojo-rg1.partial` | 0.91 GB | never seal (survey-runs@2) |
| `corpora/adprov-v1-release-rg1.partial` | 4.24 GB | never seal (no compat PROV) |
| `corpora/ast-survey-agentharm-rg1.partial` | 0.31 GB | never seal (survey-agentharm@1) |
| **Total (corpora)** | **40.0 GB** | |
| `migration-work/precheck/_ops/` | 320 KB | mode 700/600; `scrub-mapping.json` is the only digest→ordinal map. **Secure delete after release**, not the Trash |
| Scratch worktrees of this check: `~/.agentprov/merge-train/prc-5b1f6fdf`, `prc-d93aa261`, `prc-5fc39c16` | 0.32–0.33 GB each | detached worktrees with `.venv` and `.venv-3148`; remove with `git worktree remove` once the report is accepted |

The scratch outputs of this check stay in the session scratchpad (section 13), outside the repository and
`~/.agentprov`.

## 10. Combined release (several Zenodo records as one collection)

User decision, relayed by the orchestrator (2026-10-28): no deposit for round 1 alone. One combined release with the
Wave-2 corpora, in several records organised as one collection. Sealing the 8 trees (local) stays the target. This
section is a proposal; nothing is decided or deposited.

**Constraints from the code and docs.**

* **One licence class per deposit and per record.** `package --deposit` refuses mixed classes unless
  `--allow-mixed-licence-classes` is given (`release.refused.mixed_licence_classes`, D-42). It never mixes a
  non-commercial `-nc` class, flag or not (`release.refused.nc_partition`, D-25). `tools/zenodo_draft.py` refuses a deposit
  with more than one licence class ("Zenodo holds one licence per record", H.10.6) and maps only the SPDX ids in
  `LICENCE_IDS` (MIT, Apache-2.0, CC-BY-4.0, CC-BY-SA-4.0, CC-BY-NC(-SA)-4.0, CC0-1.0, GPL-3.0-only/-or-later,
  AGPL-3.0-only).
* **Copyleft sources stay one corpus per source** (D-94), each with its source licence (no relicensing, D-25).
* **Record limits** (`zenodo_draft.py`, from the REST documentation, not yet confirmed in the sandbox):
  `MAX_FILES = 100` and `MAX_TOTAL_BYTES = MAX_FILE_BYTES = 50 * 10**9`.
* **Many corpora per deposit work.** `--corpus` repeats. `DEPOSIT-MANIFEST.json` records each corpus's content and root
  digest, licence class, verification level, release-scan summary and archive names. A release-mode `verify` of the
  deposit needs one published `--root-digest` per corpus (D-641). Each corpus needs its triaged
  `<corpus>.release-scan.json` beside it.
* **Archives.** DEFLATE level 6, no ZIP64, so each archive is below 2^31 − 1 bytes and 65,535 members, split on shard
  boundaries, one series per stage (raw, aer, sem, prov, meta) per corpus. The deposit adds README, CHANGELOG, a datasheet
  copy per corpus, `DEPOSIT-MANIFEST.json` and `deposit-metadata.json`.

**Round-1 classes and sizes** (licence classes from each spec and profile, as `package` computes them; archive counts
estimated from the trees with the builder's own size bound, so they are an upper bound on bytes and a lower bound on
archives):

| Class | Corpora | Archives (est.) | Bytes before compression (bound) | Files per record (est.) |
|---|---|---:|---:|---:|
| MIT | mandate, 2024-06, head, rope, agentdyn-a | 37 | 36.7 GB | about 47 |
| CC-BY-4.0 | ast-survey-agentdojo, adprov-v1-release | 12 | 5.5 GB | about 19 |
| CC-BY-4.0 + AgentHarm use restriction | ast-survey-agentharm | 5 | 0.3 GB | about 11 |
| **Round 1** | 8 | **54** | **42.6 GB** | |

DEFLATE shrinks JSON several-fold, so the stored bytes are well below the bound. Each round-1 class fits one record.
**Wave 2: placeholder for the Wave-2 session** (per class: corpora, archive count, bytes). The Wave-2 inventory names
Apache-2.0 sources, copyleft sources (one record each, D-94) and AgentHarm-derived restricted-use parts.

**Proposal.**

1. **One record per licence class:**
   - MIT;
   - Apache-2.0 (if any Wave-2 corpus has it);
   - CC-BY-4.0;
   - CC-BY-4.0 plus the AgentHarm restriction (ast-survey-agentharm, and the AgentHarm-derived Wave-2 parts *if their
     class is identical*: same SPDX and the same restriction text);
   - one record per copyleft corpus (D-94);
   - any `-nc` corpus alone.
2. **Splits within a class** only where a class exceeds 100 files or 50 GB. Split by benchmark family (for example
   AgentDojo-format corpora, Inspect/AgentHarm, OpenHands, others), so that each record is a meaningful unit. Ask Zenodo
   for a quota increase only if one record per class is clearly the better unit for users; round 1 does not need one.
3. **The collection layer:**
   - a Zenodo community for the whole collection;
   - a small umbrella record (CC-BY-4.0) holding the collection README and an index of every record: DOI, licence class,
     corpora, versions, and each corpus's content and root digests. The index lets anyone verify a corpus against a
     published digest (D-39, D-641). It also holds the datasheets and a pointer to the AgentPROV software release.
   - Related identifiers: the umbrella `hasPart` each record, each record `isPartOf` the umbrella, and each record
     `isSupplementTo` (or `isDerivedFrom`) its sources' DOIs.
4. **Order:** create every part record as a draft, collect the reserved DOIs, then build the umbrella's index and draft,
   then add the cross-links. The user publishes; a session never does.

**What exists today:**
- `package --deposit` builds one deposit of many corpora of one class, offline, with digests;
- `zenodo_draft.py` creates or resumes one draft per deposit directory (draft only, never publish; receipt beside it)
  and passes `related_identifiers` from `release.toml` `[[related]]` (DataCite vocabulary, `isPartOf`/`hasPart`
  included);
- the sandbox trial showed that a draft carries a **reserved** DOI (`prereserve_doi`).

**Tooling gaps (class 0, before deposit time):**
- G-1: the draft receipt does not record the reserved DOI, which the cross-links and the umbrella index need;
- G-2: no `communities` field in the draft metadata (it could be added in the web UI instead);
- G-3: no generator for the umbrella index (records × corpora × root digests);
- G-4: `MAX_FILES`, `MAX_TOTAL_BYTES`, the GB unit and the `isPartOf`/`hasPart` relations still need a sandbox
  confirmation.

A session `zenodo-helper-gaps` exists among the linked sessions; G-1 to G-4 may already be its scope.

## 11. Decisions for the user (detail)

The top list carries the decisions to answer now. This table maps them to the ids used in the checks and adds the
later ones.

| Id | Top item | Decision | Recommendation |
|---|---|---|---|
| U-1 | 8 | Approve the drafted statements (D-359, D-771, D-811, PC-01, D-810 rows) | approve |
| U-2 | 1 | Survey AR-12 blocker: C-1 (class 0) or `survey-runs@4` plus a re-import | C-1 |
| U-3 | 8 | POST-adprov-v1-release-02: `model-home-paths-adprov-v1-release`, `benchmark-home-paths-rope` | approve |
| U-4 | 3 | Amend `benchmark-and-model-home-paths` (AgentHarm 19/9/10; agentdyn-a all suites 17/11/6 plus 3 raw-only) | amend |
| U-5 | 2 | Gitleaks triage by origin (table 4b) | accept; build C-3 |
| U-6 | 5 | Building commit | disclose (two drafted statements) |
| U-7 | — | `LIVE_BLOCK` closure | later, as `corpus-0.3` with live sealing (C-6) |
| U-8 | 4 | Licence files at sealing; the 2024-06 spec | `089ed468`'s LICENSE and CITATION.bib; C-4; for adprov the CC BY 4.0 legal code, not the release folder's MIT `LICENSE` |
| U-9 | 9 | Scratch seal rehearsal of agentdyn-a, then the real `release_scan.py` on the copy | yes (a seal of a copy: your typed yes) |
| U-10 | — | Combined-release layout (sec. 10) | per-class records plus a community and an umbrella index; decide after the Wave-2 sizes |
| U-11 | — | Housekeeping (sec. 9) | after the 8 are sealed and verified |
| U-12 | 7 | D-810 statement 4: 65 files, not 40 | amended wording (drafted) |
| U-13 | 6 | 16 unclassifiable `password` values and account ordinal #20, in 8 uncited agentdyn-a raw files (0 executions) | look once in your own terminal, then triage. If any looks real: a purge tombstone (a corpus write) or C-8 |

## 12. Code changes proposed (none made here)

| Id | Change | Class | Needed before |
|---|---|---|---|
| C-1 | The datasheet's "Distribution and licensing" renders each `attribution` entry as a quoted third-party credit, and `lint_datasheet` exempts exactly those quoted entries from AR-12 (`corpus/datasheet.py`, `adapters/registry/claims.py`; neither is in a stage scope, only `adapters/registry/__init__.py` is in `AER_CLOSURE`). Test: the survey-runs attribution renders and passes, while an unquoted "reproducible" elsewhere still fails | **0** (prove with a before/after of every stage digest) | sealing `ast-survey-agentdojo` |
| C-2 | `tools/release_scan.py --forecast --spec SPEC [--licence-file ...]`: this check's `forecast.py` as a tool (a working tree scanned with the sealed rules and persona files, each finding labelled released or withheld by the seal's own plan). The post-check's `seal-forecast` should also render the datasheet (it missed C-1's case) and check the licence files | **0** | the next round's pre-release check |
| C-3 | Triage tooling: a triage-file writer that turns table 4b's classes into the per-root-digest `[[triage]]` file after sealing, and `--list-secrets` (salted digest per distinct redacted match, rule, key, origin, count; a value only with `--show`, in the user's terminal) for item 6 | **0** | the deposit |
| C-4 | Spec comment fixes: 2024-06's licence-file comment (the files are not at `c2748856`), and adprov's note on which LICENSE text to supply | **0** (spec bytes; nothing sealed yet) | sealing those two |
| C-5 | `tools/zenodo_draft.py`: record the reserved DOI in the receipt (G-1); optional `communities` (G-2); an umbrella-index generator (G-3) | **0** | the combined deposit |
| C-6 | Live sealing: the sealed live block's design and `corpus-0.3` (U-7) | **0** for `corpus/` and the schema | the first live deposit |
| C-7 | Only if U-6 is "build": `package --built-at` (design sec. 7), `build_steps[].basis` in `corpus-0.2` before the first seal, `find_building_commit.py` on D-451's closures | **0** + schema | sealing (if chosen) |
| C-8 | Only if item 6 finds a real value: a spec-level object withhold for non-e-mail findings (a `withhold-object` basis keyed by object sha256, like D-810's), so a raw object can be withheld without a profile bump or a corpus write | **0** (spec, `corpus/withhold.py`) | sealing agentdyn-a, if needed |

Nothing class 1 is proposed. All of these stay off `main` until the orchestrator trains them; C-1 and C-4 go before
the seal.

## 13. Reproduction and scratch

The scripts below are scratch tools (session scratchpad, outside the repository), run with the core venv's `python -I`
or through `tools/suite_queue.py --class import` (main's copy). Each reads the trees and writes counts only:

| Script | What it does |
|---|---|
| `forecast.py` | `package --dry-run` in process with `_plan` captured, plus the release-scan forecast of check 4 (gitleaks pin, native scan, D-810 persona files from the spec, withheld/released labels, AER record kinds, account ordinals with suite-data features, D-810 address and execution counts) |
| `recompute.sh`, `forecast.sh` | the queue drivers (building-commit worktrees, worker counts, licence files) |
| `prov_compare.py` | the masked rg1 → rg2 comparison of check 2 |
| `homepath_reconcile.py` | the three AgentHarm name counts and per-ordinal features of check 3 |
| `iclass.py` | SEM outcome evidence-class moves p10 → rg1 (D-359) |
| `deposit_size.py` | per-stage archive estimate with the builder's size bound (section 10) |
| `gitleaks_triage.py`, `gltriage.sh` | the per-finding gitleaks table of check 4b (pinned gitleaks, origin from the AER record or the suite data, the seal plan for withheld files) |
| `dyn_explain.py` | agentdyn-a's 192 withheld objects and the model-generated execution split (check 4a) |
| `lint_drafts.py`, `make_d810_rows.py`, `datasheet_probe.py` | statement drafts and lint; the D-810 rows from the forecasts; the location of the datasheet lint failure |

Inputs that were read but not changed: the 8 trees, the 11 refused trees (dry runs only), local upstream clones and the
fetch cache (`GIT_NO_LAZY_FETCH=1`), and the suite data of the AgentDojo backend venv, the AgentDyn baseline and the
AgentHarm data. Scratch worktrees to remove after acceptance: `~/.agentprov/merge-train/prc-5b1f6fdf`, `prc-d93aa261`,
`prc-5fc39c16` (`git worktree remove`).
