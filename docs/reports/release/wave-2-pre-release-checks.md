# Pre-release checks for sealing the wave-2 corpora

Date: 2026-10-29, Mac Studio. Brief: `~/.agentprov/handoff/wave-2-pre-release-checks.md`; method as round 1
(`docs/reports/release/pre-release-checks.md`). Code: `main` `9a44a2b7` for the seal forecasts (D-960 and the 40
approved drafts), `601c0dad` and `82d88a41` for the later spec heads; Python 3.14.8 (core venv).

**During the checks nothing was sealed, packaged, deposited or pushed, and nothing was written inside a corpus.** The
43 trees were then sealed on 2026-10-29 from `c0e711f4`, under the user's sealing pre-approval relayed by the
orchestrator; the seal and the checks after it are in check 6a and check 7. Nothing was tagged, packaged for a deposit
or pushed. Seal forecasts are
`agentprov package --dry-run` (N.1.6, writes nothing) run in process from clean detached checkouts under
`~/.agentprov/merge-train/`, with the withholding plan captured; the release-scan forecast calls `tools/release_scan.py`'s
own functions with its real rules (gitleaks 8.30.1 and its configuration, the native path scan with archives decoded, the
D-810 e-mail rule with each spec's persona files, the acct-label and account allowlists). One network read was made,
with the user's yes: ATIA's `LICENSE` at its pin (one file, checked against the git blob id and sha256 the profile
records). All heavy jobs went through `tools/suite_queue.py --class import`. This report holds counts, ordinals, digests
and rule ids only: no address, account name, path, token or benchmark text.

**Scope.** 43 valid trees of `~/.agentprov/migration-work/wave-2/valid-trees.txt` (240,825 executions): the 40 marked
passed at the start and `agentdyn-b-w2`, `mcphunt-w2b` and `redcode-exec-openhands-w2`, which passed during the check.
`dtap-bench-w2b` was still building; it joins as an addendum (its result provisional until wave 2 confirms its recompute).

## Your decisions, in one list

Every item below was put to you in this session's window (2026-10-29) and answered there, except where it says
otherwise. From the DTap conflict on, decisions are confirmed in the orchestrator's window (its instruction, 2026-10-29).

| # | Decision | Option taken | Where |
|---|---|---|---|
| 1 | **Corpus specs, CARDs, CHANGES and observed persona files** for the 40 trees ready at the start, then for `agentdyn-b`, `mcphunt` and `redcode-exec-openhands` | Approved ("i approve"; "Approve") → on `main` (`3c332756` → `9a44a2b7`; `5ec3cac5` → `82d88a41`) | check 2 |
| 2 | **D-960 (class 0): seal with the archived `aprov` catalogue and source profile the tree recorded.** 37 of 40 trees recorded `aprov` v2 (D-930 kept them there) and `package` accepted only v3; `agentdyn-c` records `agentdyn@3`, archived by D-933 | Approved ("Yes fix as proposed", relayed by the orchestrator) → on `main` (`5e10792b` → `9a44a2b7`) | check 3 |
| 3 | **ATIA's LICENSE** is not on this machine | One-file fetch at the pin, checked against the profile's blob id and sha256 → done | check 6 |
| 4 | **Licence files for the 14 sources without one at the pin** | The CC BY 4.0 legal code (round 1's adprov bytes) for the 10 CC-BY-4.0 corpora; `agentops-bench`, `controlarena-persistent`, `dca-agentdojo`, `drift1-agentdojo` ship none → on `main` (`d48e863f` → `601c0dad`) | check 6 |
| 5 | **what-surrounds' one account name** (#1, 1,849 findings) | Benchmark text (the MCPTox quote, PC-what-surrounds-04): synthetic-benchmark, plus a statement | check 4c, 5 |
| 6 | **CredLeak withholds 5,429 of 19,636 executions** | Disclose as decided (D-265, D-605: exactly 5,422 + 7) | check 5 |
| 7 | **D-961 (class 0): a `withhold-object` address withholds its object alone.** SEAgent's plan withheld all 5,342 executions through its deposit zip | Approved ("chose the recommendation for me -- i approve") → on `main` (`b27972e0` → `d7aca240`) | check 3 |
| 8 | **D-962 (class 0, tools): `scan_origins` classifies what the release scan finds.** 130 addresses in 13 corpora had no class | Approved (class-0 tool fix) → on `main` (`50909749` → `5246e1d4`) | check 2, 3 |
| 9 | **ControlArena seals metadata-only** (D-344: all 5,742 executions withheld) | Seal it in v0.1, with a disclosure | check 5 |
| 10 | **llm-lock withholds 920 of 53,307 executions** under D-810 | Disclose as decided | check 4a |
| 11 | **Gitleaks and account-path triage** | By-origin classes; C-3 recomputes them on the sealed trees (a deposit gate). The one-time look at the 2,985 findings with no derivable origin was **done before the seals**, by the orchestrator under your delegation ("can you do the secret scan review for me, and i approve your judgement on it"), from the value-blind pack in `~/.agentprov/migration-work/wave-2/secret-review/`: model-generated 2,212, synthetic-benchmark 457, false-positive 302, **withhold 14** (plus 3 files holding 4 keys of group G03) → D-964 | check 4b |
| 12 | **The 12 persona files D-962 changes** (`1e088c39`) | Approved; in the orchestrator's next train | check 2 |
| 13 | **D-963 (class 0): an address withholds executions only through their own records.** memo-ozdincer's shared results files took 425 executions for 6 | Approved ("Own records only"); head `233ad28e`, in the orchestrator's next train | check 3 |
| 14 | **DTap's `ex_suw7`** (210 calls, at the 300 s CPU budget) | Retry and include; D-971 (withhold it) is parked. Final answer confirmed in the orchestrator's window | addendum |
| 15 | **The datasheet statements of check 5** (D-810 rows, withholding disclosures) | Approved ("Yes I approve #15", in the orchestrator's window) → in `corpora/datasheet-statements.toml` (`54719b06`) | check 5 |
| 16 | **D-964 (C-8, class 0): the corpus spec lists what a review withholds, by object digest and execution id.** Needed for decision 11's withholds: no profile rule could take them, and purge is a corpus write | Decided by the orchestrator (C-8, not purge) → heads `c5b5690e` (code) and `99e6e3cd` (the `[withhold]` tables of `atia-benchmark`, `openagentsafety`, `tacit-agentdojo`, `agentdyn-b`); push needs your yes | check 3, 4b |
| 17 | **The D-964 disclosure rows** for those four corpora (new wording) | Approved, in the orchestrator's window → in `corpora/datasheet-statements.toml` (`efe1e69b`) | check 5 |
| 18 | **DTap's spec, CARD, CHANGES and observed persona file** (tree `dtap-bench-w2c`) | Approved ("yes approve"), with the Apache-2.0 text as its LICENSE file (as decision 4) | addendum |

**Order for the sealing yes** (in the orchestrator's window): `1e088c39`, D-963 and the approved statements are on
`main`; land D-964 (`c5b5690e`, `99e6e3cd`) and its disclosure rows (item 17); run the final seal dry run of the 43
trees from one clean commit (check 6); then seal the 43 from that commit with `--licence-file` as in check 6; then the
real release scan and `verify --level chain` per tree; C-3 triage before the deposit, applying decision 11's verdicts
(`decisions.toml` of the review pack) as its decisions file. DTap is a later batch on its own.

## The 43 trees

| Tree | Corpus | Executions | Building tag | Profile as built | Licence (SPDX; restriction) | Recompute `--dry-run` at the building commit |
|---|---|---:|---|---|---|---|
| `agentdyn-b-w2` | `agentdyn-b` | 5,184 | `wave2/build-f8b5d62b` | `agentdyn@4` | MIT | 5,184/5,184 identical at 4 workers (import at 5) |
| `agentdyn-c-w2` | `agentdyn-c` | 4,258 | `wave2/build-296418cb` | `agentdyn@3` | MIT | 4,258/4,258 identical at 4 workers (import at 5) |
| `agentops-bench-w2` | `agentops-bench` | 3,360 | `wave2/build-7285a516` | `agentops-bench-pilot@2` | Apache-2.0 | 3,360/3,360 identical at 4 workers (import at 5) |
| `aiauthz-agentdojo-w2` | `aiauthz-agentdojo` | 174 | `wave2/build-0ea673f7` | `aiauthz-agentdojo@1` | AGPL-3.0-only; copyleft (D-94) | 174/174 identical at 4 workers (import at 8) |
| `atia-benchmark-w2` | `atia-benchmark` | 123 | `wave2/build-3bb905d9` | `atia-benchmark@1` | MIT | 123/123 identical at 4 workers (import at 5) |
| `authority-caps-agentdojo-w2` | `authority-caps-agentdojo` | 18,739 | `wave2/build-0ea673f7` | `authority-caps-agentdojo@1` | CC-BY-4.0 | 18,739/18,739 identical at 4 workers (import at 5) |
| `autogen-guard-placement-w2` | `autogen-guard-placement` | 1,080 | `wave2/build-7285a516` | `autogen-guard-placement@2` | CC-BY-4.0 | 1,080/1,080 identical at 4 workers (import at 5) |
| `bookkeeper-agentdojo-w2` | `bookkeeper-agentdojo` | 570 | `wave2/build-0ea673f7` | `bookkeeper-agentdojo@1` | GPL-3.0-or-later; copyleft (D-94) | 570/570 identical at 4 workers (import at 8) |
| `ceferisbarov-agentdojo-w2` | `ceferisbarov-agentdojo` | 18,442 | `wave2/build-0ea673f7` | `ceferisbarov-agentdojo@1` | MIT | 18,442/18,442 identical at 4 workers (import at 8) |
| `code-agent-misalignment-w2` | `code-agent-misalignment` | 2,182 | `wave2/build-7285a516` | `code-agent-misalignment-geminicli@2` | CC-BY-4.0 | 2,182/2,182 identical at 4 workers (import at 5) |
| `controlarena-persistent-w2b` | `controlarena-persistent` | 5,742 | `wave2/build-7285a516` | `controlarena-persistent@4` | MIT | 5,742/5,742 identical at 4 workers (import at 5) |
| `craibench-agentdojo-w2` | `craibench-agentdojo` | 1,163 | `wave2/build-0ea673f7` | `craibench-agentdojo@1` | MIT | 1,163/1,163 identical at 4 workers (import at 8) |
| `credleak-p15b-w2b` | `credleak-p15b` | 19,636 | `wave2/build-296418cb` | `credleak-p15b@2` | CC-BY-4.0 | 19,636/19,636 identical at 4 workers (import at 5) |
| `dca-agentdojo-w2b` | `dca-agentdojo` | 16,221 | `wave2/build-296418cb` | `dca-agentdojo@1` | MIT | 16,221/16,221 identical at 4 workers (import at 5) |
| `drift-head-w2` | `drift-head` | 1,569 | `wave2/build-0ea673f7` | `drift@1` | MIT | 1,569/1,569 identical at 4 workers (import at 8) |
| `drift1-agentdojo-w2` | `drift1-agentdojo` | 626 | `wave2/build-0ea673f7` | `drift1-agentdojo@1` | MIT | 626/626 identical at 4 workers (import at 8) |
| `fragfuse-agentharm-w2` | `fragfuse-agentharm` | 1,747 | `wave2/build-3bb905d9` | `fragfuse-agentharm@2` | MIT; AgentHarm use restriction | 1,747/1,747 identical at 4 workers (import at 5) |
| `gate-agentdojo-w2` | `gate-agentdojo` | 3,870 | `wave2/build-0ea673f7` | `gate-agentdojo@1` | AGPL-3.0-only; copyleft (D-94) | 3,870/3,870 identical at 4 workers (import at 8) |
| `geryon-agentdojo-w2` | `geryon-agentdojo` | 3,179 | `wave2/build-0ea673f7` | `geryon-agentdojo@2` | Apache-2.0 | 3,179/3,179 identical at 4 workers (import at 8) |
| `glitch-agentdojo-w2` | `glitch-agentdojo` | 1,844 | `wave2/build-0ea673f7` | `glitch-agentdojo@1` | MIT | 1,844/1,844 identical at 4 workers (import at 8) |
| `hilarytorn-trajectory-poisoning-w2` | `hilarytorn-trajectory-poisoning` | 990 | `wave2/build-0ea673f7` | `hilarytorn-trajectory-poisoning@1` | MIT | 990/990 identical at 4 workers (import at 8) |
| `interbolt-agentdojo-w2` | `interbolt-agentdojo` | 2,016 | `wave2/build-0ea673f7` | `interbolt-agentdojo@2` | Apache-2.0 | 2,016/2,016 identical at 4 workers (import at 8) |
| `ipi-defenses-agentdojo-w2` | `ipi-defenses-agentdojo` | 3,211 | `wave2/build-0ea673f7` | `ipi-defenses-agentdojo@1` | CC-BY-4.0 | 3,211/3,211 identical at 4 workers (import at 8) |
| `kavach-agentdojo-w2` | `kavach-agentdojo` | 2,625 | `wave2/build-3bb905d9` | `kavach-agentdojo@1` | MIT | 2,625/2,625 identical at 4 workers (import at 5) |
| `kexin-xu-01-agentharm-w2` | `kexin-xu-01-agentharm` | 2,797 | `wave2/build-3bb905d9` | `kexin-xu-01-agentharm@2` | MIT; AgentHarm use restriction | 2,797/2,797 identical at 4 workers (import at 5) |
| `kongminos-agentdojo-w2` | `kongminos-agentdojo` | 950 | `wave2/build-0ea673f7` | `kongminos-agentdojo@2` | MIT | 950/950 identical at 4 workers (import at 8) |
| `linyxus-agentdojo-w2` | `linyxus-agentdojo` | 9,068 | `wave2/build-0ea673f7` | `linyxus-agentdojo@1` | MIT | 9,068/9,068 identical at 4 workers (import at 8) |
| `llm-lock-agentdojo-w2` | `llm-lock-agentdojo` | 53,307 | `wave2/build-0ea673f7` | `llm-lock-agentdojo@1` | GPL-3.0 | 53,307/53,307 identical at 4 workers (import at 8) |
| `mcphunt-w2b` | `mcphunt` | 6,786 | `wave2/build-f8b5d62b` | `mcphunt@3` | CC-BY-4.0 | 6,786/6,786 identical at 4 workers (import at 5) |
| `melon-agentdojo-w2` | `melon-agentdojo` | 1,911 | `wave2/build-0ea673f7` | `melon-agentdojo@2` | MIT | 1,911/1,911 identical at 4 workers (import at 8) |
| `memo-ozdincer-agentdojo-w2` | `memo-ozdincer-agentdojo` | 13,070 | `wave2/build-0ea673f7` | `memo-ozdincer-agentdojo@2` | MIT | 13,070/13,070 identical at 4 workers (import at 8) |
| `menelaus29-ipi-multidomain-w2` | `menelaus29-ipi-multidomain` | 858 | `wave2/build-0ea673f7` | `menelaus29-ipi-multidomain@1` | MIT | 858/858 identical at 4 workers (import at 8) |
| `mohameduk-agentdojo-w2` | `mohameduk-agentdojo` | 3,630 | `wave2/build-0ea673f7` | `mohameduk-agentdojo@1` | MIT | 3,630/3,630 identical at 4 workers (import at 8) |
| `openagentsafety-w2` | `openagentsafety` | 1,560 | `wave2/build-7285a516` | `openagentsafety@2` | MIT | 1,560/1,560 identical at 4 workers (import at 5) |
| `redcode-exec-openhands-w2` | `redcode-exec-openhands` | 5,460 | `wave2/build-f8b5d62b` | `redcode-exec-openhands@1` | CC-BY-4.0 | 5,460/5,460 identical at 4 workers (import at 5) |
| `redcode-exec-qwencode-w2` | `redcode-exec-qwencode` | 3,299 | `wave2/build-7285a516` | `redcode-exec-qwencode@2` | CC-BY-4.0 | 3,299/3,299 identical at 4 workers (import at 5) |
| `seagent-agentdojo-w2` | `seagent-agentdojo` | 5,342 | `wave2/build-0ea673f7` | `seagent-agentdojo@2` | CC-BY-4.0 | 5,342/5,342 identical at 4 workers (import at 8) |
| `sentry-agentdojo-w2` | `sentry-agentdojo` | 674 | `wave2/build-0ea673f7` | `sentry-agentdojo@1` | AGPL-3.0-only; copyleft (D-94) | 674/674 identical at 4 workers (import at 8) |
| `shreeyavarma-llm-safety-w2` | `shreeyavarma-llm-safety` | 672 | `wave2/build-0ea673f7` | `shreeyavarma-llm-safety@1` | MIT | 672/672 identical at 4 workers (import at 8) |
| `tacit-agentdojo-w2` | `tacit-agentdojo` | 2,076 | `wave2/build-0ea673f7` | `tacit-agentdojo@2` | Apache-2.0 | 2,076/2,076 identical at 4 workers (import at 8) |
| `what-surrounds-w2` | `what-surrounds` | 1,334 | `wave2/build-7285a516` | `what-surrounds@1` | CC-BY-4.0 | 1,334/1,334 identical at 4 workers (import at 5) |
| `whistlebench-w2` | `whistlebench` | 9,200 | `wave2/build-3bb905d9` | `whistlebench@2` | MIT | 9,200/9,200 identical at 4 workers (import at 5) |
| `yockcheng-prompt-injection-harness-w2` | `yockcheng-prompt-injection-harness` | 280 | `wave2/build-0ea673f7` | `yockcheng-prompt-injection-harness@1` | Apache-2.0 | 280/280 identical at 4 workers (import at 8) |
| **Total** | 43 | **240,825** | | | | 0 changed, 0 failed, 0 unverified |

## Verdicts

All 43 trees pass a seal dry run at `main` with the fixes and drafts of the list above (the code column names the
commit each forecast ran at; a later commit of the list changes nothing for a tree unless check 3 says so). "Ready"
means ready for your sealing yes once items 12, 13 and 15 are on the sealing commit and the final dry run (check 6)
passes there.

| Corpus | Executions | Seal dry run (code) | Withheld objects / executions at sealing | Of which D-810 executions | Released executions | Verdict |
|---|---:|---|---|---:|---:|---|
| `agentdyn-b` | 5,184 | pass (`54719b06`, D-964) | 485 / 17 | 17 | 5,167 | **ready** |
| `agentdyn-c` | 4,258 | pass (`9a44a2b7`) | 568 / 14 | 14 | 4,244 | **ready** |
| `agentops-bench` | 3,360 | pass (`1e088c39`) | 14 / 0 | 0 | 3,360 | **ready** |
| `aiauthz-agentdojo` | 174 | pass (`9a44a2b7`) | 3 / 0 | 0 | 174 | **ready** |
| `atia-benchmark` | 123 | pass (`54719b06`, D-964; LICENSE fetched) | 18 / 13 | 10 | 110 | **ready** |
| `authority-caps-agentdojo` | 18,739 | pass (`b27972e0`) | 10 / 5 | 5 | 18,734 | **ready** |
| `autogen-guard-placement` | 1,080 | pass (`1e088c39`) | 3 / 0 | 0 | 1,080 | **ready** |
| `bookkeeper-agentdojo` | 570 | pass (`9a44a2b7`) | 0 / 0 | 0 | 570 | **ready** |
| `ceferisbarov-agentdojo` | 18,442 | pass (`9a44a2b7`) | 5 / 4 | 4 | 18,438 | **ready** |
| `code-agent-misalignment` | 2,182 | pass (`1e088c39`) | 313 / 7 | 6 | 2,175 | **ready** |
| `controlarena-persistent` | 5,742 | pass (`b27972e0`) | 7,348 / 5,742 | 0 | 0 | **ready** (metadata-only, D-344) |
| `craibench-agentdojo` | 1,163 | pass (`9a44a2b7`) | 1 / 0 | 0 | 1,163 | **ready** |
| `credleak-p15b` | 19,636 | pass (`9a44a2b7`) | 348 / 5,429 | 0 | 14,207 | **ready** |
| `dca-agentdojo` | 16,221 | pass (`9a44a2b7`) | 12 / 10 | 10 | 16,211 | **ready** |
| `drift-head` | 1,569 | pass (`9a44a2b7`) | 5 / 5 | 5 | 1,564 | **ready** |
| `drift1-agentdojo` | 626 | pass (`9a44a2b7`) | 1 / 0 | 0 | 626 | **ready** |
| `fragfuse-agentharm` | 1,747 | pass (`9a44a2b7`) | 350 / 0 | 0 | 1,747 | **ready** |
| `gate-agentdojo` | 3,870 | pass (`9a44a2b7`) | 4 / 0 | 0 | 3,870 | **ready** |
| `geryon-agentdojo` | 3,179 | pass (`9a44a2b7`) | 1 / 0 | 0 | 3,179 | **ready** |
| `glitch-agentdojo` | 1,844 | pass (`9a44a2b7`) | 2 / 2 | 2 | 1,842 | **ready** |
| `hilarytorn-trajectory-poisoning` | 990 | pass (`9a44a2b7`) | 0 / 0 | 0 | 990 | **ready** |
| `interbolt-agentdojo` | 2,016 | pass (`9a44a2b7`) | 24 / 0 | 0 | 2,016 | **ready** |
| `ipi-defenses-agentdojo` | 3,211 | pass (`9a44a2b7`) | 2 / 0 | 0 | 3,211 | **ready** |
| `kavach-agentdojo` | 2,625 | pass (`9a44a2b7`) | 7 / 6 | 6 | 2,619 | **ready** |
| `kexin-xu-01-agentharm` | 2,797 | pass (`1e088c39`) | 842 / 1 | 1 | 2,796 | **ready** |
| `kongminos-agentdojo` | 950 | pass (`9a44a2b7`) | 0 / 0 | 0 | 950 | **ready** |
| `linyxus-agentdojo` | 9,068 | pass (`9a44a2b7`) | 1 / 0 | 0 | 9,068 | **ready** |
| `llm-lock-agentdojo` | 53,307 | pass (`9a44a2b7`) | 920 / 920 | 920 | 52,387 | **ready** |
| `mcphunt` | 6,786 | pass (`5ec3cac5`) | 28 / 4,596 | 0 | 2,190 | **ready** |
| `melon-agentdojo` | 1,911 | pass (`9a44a2b7`) | 1 / 0 | 0 | 1,911 | **ready** |
| `memo-ozdincer-agentdojo` | 13,070 | pass (`9a44a2b7`) (D-963; 425 before) | 6 / 6 | 6 | 13,064 | **ready** |
| `menelaus29-ipi-multidomain` | 858 | pass (`9a44a2b7`) | 0 / 0 | 0 | 858 | **ready** |
| `mohameduk-agentdojo` | 3,630 | pass (`9a44a2b7`) | 4 / 2 | 2 | 3,628 | **ready** |
| `openagentsafety` | 1,560 | pass (`54719b06`, D-964) | 7 / 2 | 0 | 1,558 | **ready** |
| `redcode-exec-openhands` | 5,460 | pass (`c8ce1d85`) (D-963; 30 before) | 4 / 1 | 1 | 5,459 | **ready** |
| `redcode-exec-qwencode` | 3,299 | pass (`1e088c39`) | 1 / 0 | 0 | 3,299 | **ready** |
| `seagent-agentdojo` | 5,342 | pass (`b27972e0`) | 14 / 11 | 11 | 5,331 | **ready** |
| `sentry-agentdojo` | 674 | pass (`9a44a2b7`) | 0 / 0 | 0 | 674 | **ready** |
| `shreeyavarma-llm-safety` | 672 | pass (`9a44a2b7`) | 1 / 0 | 0 | 672 | **ready** |
| `tacit-agentdojo` | 2,076 | pass (`54719b06`, D-964) | 10 / 6 | 6 | 2,070 | **ready** |
| `what-surrounds` | 1,334 | pass (`9a44a2b7`) | 0 / 0 | 0 | 1,334 | **ready** |
| `whistlebench` | 9,200 | pass (`c8ce1d85`) | 58 / 0 | 0 | 9,200 | **ready** |
| `yockcheng-prompt-injection-harness` | 280 | pass (`9a44a2b7`) | 1 / 0 | 0 | 280 | **ready** |
| **Total (43)** | **240,825** | 43 pass | 11,422 / 16,799 | 1,026 | 224,026 | |

## 1. Stray sealed copies and the never-seal list

A scan of all of `~/.agentprov` (every `corpus.json`, `DEPOSIT-MANIFEST.json`, `deposit-metadata.json`, `WITHHELD.json`,
`*.release-scan.json`, `*.release-triage.toml` and `*.withheld` sidecar, at any depth; `locks/` skipped) finds:

* **Sealed corpora: the 8 round-1 trees only**, each with its expected sidecars (7 `.withheld` directories; Mandate
  withholds nothing), release-scan document and triage file beside it, plus 8 earlier copies of the scan documents in
  `migration-work/pre-release/seal/`. **Deposit bundles: 0.**
* **Working corpora:** the 45 wave-2 trees (`mode: import`, `sealed: false`), the three round-1 never-seal trees, and
  16 live scratch corpora (13 under `calibration/`, 3 under `vms/results/`), which `package` refuses as live (exit 5,
  `package.unsupported.live`). Three `corpus.json` files in a staging clone are upstream payload lists, not corpora.
* **Never seal:** `dtap-bench-w2` (superseded by `dtap-bench-w2b`; it records `dtap-bench@2`, the spec will name `@3`,
  so `package` refuses it at the spec check); `mcphunt-w2` is gone from disk (wave 2 removed it). The round-1 trees
  `ast-survey-agentdojo-rg1`, `adprov-v1-release-rg1` and `ast-survey-agentharm-rg1` stay refused as round 1 showed.
  `package` seals only the one `--corpus` it is given, so nothing is picked up by accident. **Result: pass.**

## 2. The D-810 pass and the persona files

**Method.** `tools/scan_origins.py` on every tree (through `origins_w2.py`, which feeds it the committed upstream-data
lists as the set-aside and writes the observed file with the source's pin: git, Hugging Face revision, or DOI for
Zenodo and Figshare). Upstream-data lists: `agentdojo` for every AgentDojo-format corpus, plus `agentdyn` for
`agentdyn-b`, `agentdyn-c` and `drift-head` (DRIFT ran on AgentDyn's suites: 21 of its addresses are in that list), and
`agentharm` for the two AgentHarm-derived corpora; the other benchmarks have none, so their benchmark-supplied
addresses are classed by first appearance (`benchmark-input`).

**The count pass reproduces.** For all 25 corpora that the wave-2 count pass (`checks1/count_pass.py`) and this pass
share, the not-found count is equal (the three other entries of the count pass are the old Kavach snapshot trees, which
the rebuilt Kavach replaced). Every address it found without an upstream match in those 25 corpora now has an observed class.

**D-962 (decision 8).** The first pass left 130 addresses in 13 corpora without a class. In AER files the release
scan's byte reading and `scan_origins`' decoded reading disagreed on the address boundary after a JSON backslash (in
every case the match starts right after one); the rest sat only in raw files an execution cites but no record is read
from (78 of them in `code-agent-misalignment`'s supporting files). After D-962 the 12 changed observed files add 11
benchmark-input, 13 model-generated and 99 withhold-object addresses and move 3 between classes (first appearances
moved once bytes are read); no `withhold` address is added, so no corpus withholds another execution. 7 addresses stay
without a class, all in files ControlArena's plan withholds (D-344).

| Tree | Executions | Not found | benchmark-input | model-generated | withhold | withhold-object | withhold: executions | withhold-object: raw objects | no class (not-in-AER) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `agentdyn-b-w2` | 5,184 | 325 | 7 | 41 | 9 | 268 | 17 | 380 | 0 |
| `agentdyn-c-w2` | 4,258 | 325 | 0 | 39 | 7 | 279 | 14 | 500 | 0 |
| `agentops-bench-w2` | 3,360 | 26 | 3 | 16 | 0 | 7 | 0 | 1 | 0 |
| `aiauthz-agentdojo-w2` | 174 | 1 | 0 | 0 | 0 | 1 | 0 | 3 | 0 |
| `atia-benchmark-w2` | 123 | 9 | 2 | 4 | 3 | 0 | 10 | 0 | 0 |
| `authority-caps-agentdojo-w2` | 18,739 | 29 | 2 | 21 | 4 | 2 | 5 | 2 | 0 |
| `autogen-guard-placement-w2` | 1,080 | 7 | 5 | 0 | 0 | 2 | 0 | 3 | 0 |
| `bookkeeper-agentdojo-w2` | 570 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `ceferisbarov-agentdojo-w2` | 18,442 | 39 | 1 | 25 | 9 | 4 | 4 | 1 | 0 |
| `code-agent-misalignment-w2` | 2,182 | 349 | 7 | 59 | 4 | 279 | 6 | 45 | 0 |
| `controlarena-persistent-w2b` | 5,742 | 385 | 141 | 2 | 0 | 235 | 0 | 20 | 7 |
| `craibench-agentdojo-w2` | 1,163 | 4 | 0 | 0 | 0 | 4 | 0 | 1 | 0 |
| `credleak-p15b-w2b` | 19,636 | 79 | 49 | 30 | 0 | 0 | 0 | 0 | 0 |
| `dca-agentdojo-w2b` | 16,221 | 37 | 1 | 27 | 8 | 1 | 10 | 1 | 0 |
| `drift-head-w2` | 1,569 | 17 | 5 | 7 | 5 | 0 | 5 | 0 | 0 |
| `drift1-agentdojo-w2` | 626 | 3 | 1 | 1 | 0 | 1 | 0 | 1 | 0 |
| `fragfuse-agentharm-w2` | 1,747 | 10 | 5 | 5 | 0 | 0 | 0 | 0 | 0 |
| `gate-agentdojo-w2` | 3,870 | 61 | 12 | 45 | 0 | 4 | 0 | 4 | 0 |
| `geryon-agentdojo-w2` | 3,179 | 1 | 0 | 0 | 0 | 1 | 0 | 1 | 0 |
| `glitch-agentdojo-w2` | 1,844 | 12 | 4 | 6 | 2 | 0 | 2 | 0 | 0 |
| `hilarytorn-trajectory-poisoning-w2` | 990 | 6 | 0 | 6 | 0 | 0 | 0 | 0 | 0 |
| `interbolt-agentdojo-w2` | 2,016 | 1 | 0 | 1 | 0 | 0 | 0 | 0 | 0 |
| `ipi-defenses-agentdojo-w2` | 3,211 | 1 | 0 | 0 | 0 | 1 | 0 | 2 | 0 |
| `kavach-agentdojo-w2` | 2,625 | 33 | 4 | 18 | 9 | 2 | 6 | 1 | 0 |
| `kexin-xu-01-agentharm-w2` | 2,797 | 54 | 33 | 19 | 1 | 1 | 1 | 828 | 0 |
| `kongminos-agentdojo-w2` | 950 | 1 | 0 | 1 | 0 | 0 | 0 | 0 | 0 |
| `linyxus-agentdojo-w2` | 9,068 | 53 | 40 | 9 | 0 | 4 | 0 | 1 | 0 |
| `llm-lock-agentdojo-w2` | 53,307 | 594 | 49 | 380 | 165 | 0 | 920 | 0 | 0 |
| `mcphunt-w2b` | 6,786 | 238 | 136 | 90 | 0 | 12 | 0 | 5 | 0 |
| `melon-agentdojo-w2` | 1,911 | 4 | 0 | 0 | 0 | 4 | 0 | 1 | 0 |
| `memo-ozdincer-agentdojo-w2` | 13,070 | 29 | 6 | 13 | 6 | 4 | 6 | 1 | 0 |
| `menelaus29-ipi-multidomain-w2` | 858 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| `mohameduk-agentdojo-w2` | 3,630 | 28 | 0 | 19 | 4 | 5 | 2 | 2 | 0 |
| `openagentsafety-w2` | 1,560 | 111 | 95 | 13 | 0 | 3 | 0 | 2 | 0 |
| `redcode-exec-openhands-w2` | 5,460 | 68 | 7 | 2 | 1 | 58 | 1 | 1 | 0 |
| `redcode-exec-qwencode-w2` | 3,299 | 82 | 17 | 0 | 0 | 65 | 0 | 1 | 0 |
| `seagent-agentdojo-w2` | 5,342 | 197 | 0 | 2 | 1 | 194 | 11 | 1 | 0 |
| `sentry-agentdojo-w2` | 674 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `shreeyavarma-llm-safety-w2` | 672 | 8 | 0 | 4 | 0 | 4 | 0 | 1 | 0 |
| `tacit-agentdojo-w2` | 2,076 | 12 | 1 | 7 | 4 | 0 | 6 | 0 | 0 |
| `what-surrounds-w2` | 1,334 | 2 | 1 | 1 | 0 | 0 | 0 | 0 | 0 |
| `whistlebench-w2` | 9,200 | 263 | 196 | 63 | 0 | 4 | 0 | 57 | 0 |
| `yockcheng-prompt-injection-harness-w2` | 280 | 3 | 0 | 1 | 0 | 2 | 0 | 1 | 0 |
| **Total (43)** | 240,825 | 3,508 | 831 | 977 | 242 | 1,451 | 1,026 | 1,868 | 7 |

Columns: `withhold` is a model-written address at a public mail provider (its executions are withheld);
`withhold-object` is an address in no execution's records (its raw objects are withheld, each alone: D-961, D-963).

## 3. Seal-path fixes made during the check (all class 0, all approved, see the list)

| Decision | What `package` did before | Now | Proof of class 0 |
|---|---|---|---|
| D-960 | refused every tree whose `prov` stage recorded `aprov` v2 (37 of 40) and every spec that names an archived source profile (`agentdyn-c`) | seals the recorded catalogue and profile version from the byte-exact archive | 41 stage digests identical; the 8 round-1 seals' `rules/prov` and `rule_catalogues` reproduce byte for byte |
| D-961 | a `withhold-object` address in a stored deposit zip withheld every execution read from it (SEAgent: 5,342) | the object is withheld alone (SEAgent: 11) | round 1's 187 address-rule entries with executions each hold a `withhold` digest |
| D-962 | `scan_origins` left addresses the release scan finds without a class (130) | byte-level matches take their record's origin; raw-only addresses are `withhold-object` | tools only |
| D-963 | an address in a shared results file withheld every execution of the file (memo-ozdincer: 425) | executions are withheld only through their own records (memo-ozdincer: 6) | round 1's 187 withheld executions each hold a `withhold` digest in their own AER |

SEAgent's cause, measured: its deposit zip has 26,033 members, 5,379 selected. The `withhold-object` digests hit its
stored bytes 15 times (15 addresses), all inside deflate-compressed member data (12 unselected members, 3 selected), none
in a member name.

The orchestrator's trains carried two more class-1 changes (D-950 artefact catalogues, `e7a0aa2f` DTap catalogue) and
D-935's PROV-document limit for `verify`; none is read on the seal path or changes a result for these 43 trees (checked
at `d7aca240` and `5246e1d4`).

## 4. Release-scan forecast

`tools/release_scan.py` has no pre-seal mode (it refuses a working tree), so the forecast (`forecast.py`) calls its
functions on each working tree with its real rules (gitleaks 8.30.1 and the release configuration with the D-310 key-cut
check; the native path scan with archives decoded: home path, host name, D-457 account paths, D-600 secret shapes; the
D-810 e-mail rule with the spec's persona files, digest-checked; the account and acct-label allowlists). Each finding is
labelled *withheld* when its file leaves at sealing, by the plan of that tree's own `package --dry-run`. Files sealing
adds hold digests and our own text only and are not forecast. The real scan runs after sealing, on the root digest.

**No released file holds a home path, a host name or a D-600 secret shape.** The scanner's other findings
(`github-pat` 10, `huggingface-access-token` 4, `langfuse-*` 2, `home-path-unscanned` 4: AgentOps' deposit tarball,
which holds a link member the decoded scan refuses) are all in files the seal withholds.

### 4a. D-810: addresses by class (released files)

| Corpus | upstream-data (released) | benchmark-input (released) | model-generated: addresses / executions | withhold (model freemail): addresses / executions | withhold-object: addresses / raw objects |
|---|---:|---:|---|---|---|
| `agentdyn-b` | 35 | 7 | 41 / 105 | 9 / 17 | 268 / 380 |
| `agentdyn-c` | 34 | 0 | 38 / 61 | 7 / 14 | 279 / 500 |
| `agentops-bench` | 0 | 3 | 16 / 9 | 0 / 0 | 7 / 1 |
| `aiauthz-agentdojo` | 0 | 0 | 0 / 0 | 0 / 0 | 1 / 3 |
| `atia-benchmark` | 0 | 2 | 4 / 12 | 3 / 10 | 0 / 0 |
| `authority-caps-agentdojo` | 79 | 2 | 21 / 58 | 4 / 5 | 2 / 2 |
| `autogen-guard-placement` | 0 | 5 | 0 / 0 | 0 / 0 | 2 / 3 |
| `ceferisbarov-agentdojo` | 76 | 1 | 25 / 150 | 9 / 4 | 4 / 1 |
| `code-agent-misalignment` | 0 | 7 | 56 / 116 | 4 / 6 | 279 / 45 |
| `controlarena-persistent` | 0 | 6 | 0 / 0 | 0 / 0 | 235 / 20 |
| `craibench-agentdojo` | 0 | 0 | 0 / 0 | 0 / 0 | 4 / 1 |
| `credleak-p15b` | 0 | 0 | 4 / 5 | 0 / 0 | 0 / 0 |
| `dca-agentdojo` | 81 | 1 | 26 / 132 | 8 / 10 | 1 / 1 |
| `drift-head` | 102 | 2 | 7 / 20 | 5 / 5 | 0 / 0 |
| `drift1-agentdojo` | 80 | 1 | 1 / 1 | 0 / 0 | 1 / 1 |
| `fragfuse-agentharm` | 46 | 5 | 5 / 15 | 0 / 0 | 0 / 0 |
| `gate-agentdojo` | 76 | 12 | 45 / 11 | 0 / 0 | 4 / 4 |
| `geryon-agentdojo` | 11 | 0 | 0 / 0 | 0 / 0 | 1 / 1 |
| `glitch-agentdojo` | 72 | 4 | 6 / 9 | 2 / 2 | 0 / 0 |
| `hilarytorn-trajectory-poisoning` | 2 | 0 | 6 / 9 | 0 / 0 | 0 / 0 |
| `interbolt-agentdojo` | 6 | 0 | 1 / 1 | 0 / 0 | 0 / 0 |
| `ipi-defenses-agentdojo` | 0 | 0 | 0 / 0 | 0 / 0 | 1 / 2 |
| `kavach-agentdojo` | 79 | 2 | 12 / 9 | 9 / 6 | 2 / 1 |
| `kexin-xu-01-agentharm` | 18 | 33 | 19 / 21 | 1 / 1 | 1 / 828 |
| `kongminos-agentdojo` | 75 | 0 | 1 / 4 | 0 / 0 | 0 / 0 |
| `linyxus-agentdojo` | 64 | 40 | 9 / 12 | 0 / 0 | 4 / 1 |
| `llm-lock-agentdojo` | 81 | 47 | 324 / 549 | 165 / 920 | 0 / 0 |
| `mcphunt` | 0 | 28 | 10 / 22 | 0 / 0 | 12 / 5 |
| `melon-agentdojo` | 3 | 0 | 0 / 0 | 0 / 0 | 4 / 1 |
| `memo-ozdincer-agentdojo` | 77 | 6 | 13 / 26 | 6 / 6 | 4 / 1 |
| `menelaus29-ipi-multidomain` | 68 | 1 | 0 / 0 | 0 / 0 | 0 / 0 |
| `mohameduk-agentdojo` | 75 | 0 | 18 / 36 | 4 / 2 | 5 / 2 |
| `openagentsafety` | 0 | 95 | 13 / 24 | 0 / 0 | 3 / 2 |
| `redcode-exec-openhands` | 0 | 7 | 2 / 2 | 1 / 1 | 58 / 1 |
| `redcode-exec-qwencode` | 0 | 17 | 0 / 0 | 0 / 0 | 65 / 1 |
| `seagent-agentdojo` | 81 | 0 | 2 / 8 | 1 / 11 | 194 / 1 |
| `sentry-agentdojo` | 74 | 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| `shreeyavarma-llm-safety` | 71 | 0 | 4 / 6 | 0 / 0 | 4 / 1 |
| `tacit-agentdojo` | 76 | 1 | 7 / 26 | 4 / 6 | 0 / 0 |
| `what-surrounds` | 0 | 1 | 1 / 1 | 0 / 0 | 0 / 0 |
| `whistlebench` | 0 | 196 | 63 / 62 | 0 / 0 | 4 / 57 |
| `yockcheng-prompt-injection-harness` | 71 | 0 | 1 / 1 | 0 / 0 | 2 / 1 |
| **Total** | 1,613 | 532 | 801 / 1,523 | 242 / 1,026 | 1,451 / 1,868 |

Every released `email-address` finding is cleared by a rule in every corpus, except in files the seal withholds. The
figures feed the D-810 statements of check 5.

### 4b. Gitleaks: proposed classes by origin (never by value)

Origin as in round 1 (check 4b of `pre-release-checks.md`): `upstream-data` when a 16+ character token of the line (or a
private-key header) occurs in the benchmark's suite data; `benchmark-input` or `model-generated` by the AER record that
holds it; a PROV or raw copy takes its execution's AER origin. Per-finding rows (rule, layer, file as a 12-hex digest,
line, key name, origin, proposed class, state) of the released findings are in
`wave-2-pre-release-checks/gitleaks-<corpus>.tsv` (findings in withheld files need no triage and are left out).

| Corpus | synthetic-benchmark | model-generated | no derivable origin | in withheld files |
|---|---:|---:|---:|---:|
| `agentdyn-b` | 34 | 24 | 1,200 | 8 |
| `agentdyn-c` | 123 | 12 | 1,109 | 6 |
| `atia-benchmark` | 0 | 0 | 3 | 0 |
| `code-agent-misalignment` | 451 | 0 | 293 | 2 |
| `controlarena-persistent` | 4 | 1 | 6 | 168,549 |
| `credleak-p15b` | 2 | 7 | 1 | 8,273 |
| `fragfuse-agentharm` | 23 | 160 | 172 | 0 |
| `kexin-xu-01-agentharm` | 409 | 749 | 54 | 0 |
| `llm-lock-agentdojo` | 4 | 0 | 0 | 0 |
| `mcphunt` | 1 | 12 | 0 | 63,529 |
| `openagentsafety` | 664 | 487 | 126 | 0 |
| `redcode-exec-openhands` | 6 | 54 | 12 | 0 |
| `redcode-exec-qwencode` | 0 | 44 | 0 | 0 |
| `tacit-agentdojo` | 0 | 0 | 4 | 0 |
| `whistlebench` | 1 | 4 | 5 | 28 |
| **Total** | 1,722 | 1,554 | 2,985 | 240,395 |

Findings with no derivable origin (released), by rule, key name and layer:

* `agentdyn-b`: generic-api-key `password` (raw-object) 1,096; private-key `(none)` (raw-object) 88; generic-api-key `is` (raw-object) 4; generic-api-key `key` (raw-object) 4; generic-api-key `requested` (raw-object) 4; generic-api-key `token` (raw-object) 4
* `agentdyn-c`: generic-api-key `password` (raw-object) 1,102; generic-api-key `token` (raw-object) 4; private-key `(none)` (raw-object) 3
* `atia-benchmark`: github-app-token `(none)` (raw-object) 3
* `code-agent-misalignment`: generic-api-key `auth.py` (raw-object) 81; generic-api-key `api.py` (raw-object) 52; generic-api-key `tokens.py` (raw-object) 38; generic-api-key `secrets.py` (raw-object) 33; generic-api-key `auth_pw.py` (raw-object) 24; generic-api-key `token.py` (raw-object) 18; generic-api-key `test_auth.py` (raw-object) 12; generic-api-key `_api.py` (raw-object) 9; generic-api-key `_tokenizer.py` (raw-object) 9; generic-api-key `python_api.py` (raw-object) 9; generic-api-key `test_auth_utils.py` (raw-object) 2; generic-api-key `AUTH_TESTING.md` (raw-object) 1; generic-api-key `api_jwk.py` (raw-object) 1; generic-api-key `api_jws.py` (raw-object) 1; generic-api-key `api_jwt.py` (raw-object) 1; generic-api-key `keys.pyi` (raw-object) 1; generic-api-key `keywrap.py` (raw-object) 1
* `controlarena-persistent`: generic-api-key `API_KEY` (raw-object) 6
* `credleak-p15b`: curl-auth-user `(none)` (prov) 1
* `fragfuse-agentharm`: generic-api-key `key` (raw-object) 99; generic-api-key `used` (raw-object) 32; generic-api-key `provided` (raw-object) 23; generic-api-key `nOPENAI_API_KEY` (raw-object) 7; generic-api-key `encryption_key` (raw-object) 6; generic-api-key `key` (prov) 4; generic-api-key `provided` (prov) 1
* `kexin-xu-01-agentharm`: generic-api-key `key` (prov) 47; generic-api-key `provided` (prov) 4; generic-api-key `them` (prov) 2; generic-api-key `is` (prov) 1
* `openagentsafety`: curl-auth-user `command` (raw-object) 31; curl-auth-user `(none)` (prov) 28; curl-auth-user `message` (raw-object) 20; jwt `(none)` (raw-object) 8; curl-auth-user `(none)` (raw-object) 7; jwt `(none)` (prov) 4; private-key `(none)` (raw-object) 4; generic-api-key `feed_token` (raw-object) 3; generic-api-key `requesttoken` (raw-object) 3; curl-auth-user `http` (prov) 2; curl-auth-user `http` (raw-object) 2; curl-auth-user `keys` (raw-object) 2; private-key `(none)` (prov) 2; slack-webhook-url `(none)` (raw-object) 2; curl-auth-user `MILESTONE_ID` (prov) 1; curl-auth-user `agent` (raw-object) 1; curl-auth-user `cleanup` (prov) 1; curl-auth-user `cleanup` (raw-object) 1; curl-auth-user `keys` (prov) 1; curl-auth-user `remaining` (raw-object) 1; slack-webhook-url `(none)` (prov) 1; square-access-token `(none)` (raw-object) 1
* `redcode-exec-openhands`: generic-api-key `key` (raw-object) 6; generic-api-key `Key` (raw-object) 2; generic-api-key `Password` (raw-object) 2; generic-api-key `password` (raw-object) 2
* `tacit-agentdojo`: generic-api-key `(none)` (raw-object) 4
* `whistlebench`: generic-api-key `(none)` (raw-object) 4; generic-api-key `(none)` (prov) 1

The groups with no derivable origin are almost all in raw objects no AER record maps, and the largest repeat round-1
patterns: `agentdyn-b`/`-c` `password` (round 1 item 6: model-written passwords in uncited AgentDyn part files) and
`private-key` (the AgentDyn fixture key, row 19 of `datasheet-items.md`); `code-agent-misalignment`'s are under keys
that are source-file names of libraries inside the deposit. As decided (item 11), C-3 recomputes the classes on the
sealed trees (its pairing of copies is finer than this forecast's), and you look once at what stays without an origin
(`tools/release_triage.py --list-secrets --show`, in your own terminal) before the deposit. Sealing does not wait on it.

**Done before the seals (decision 11).** The review pack (`~/.agentprov/migration-work/wave-2/secret-review/`, outside the
repository) groups the 2,985 findings into 76 groups by corpus, rule, layer, key and value shape, with value-blind
evidence per group: check 4b's origin rule applied to each value (the first AER record of a citing execution that holds
it), its first occurrence in the file, a match against the benchmark's own definitions, the JSON location and the value's
shape, and up to five redacted examples. It holds no value and no digest of one; three fail-closed checks (per value,
over all values, and gitleaks over the pack itself) dropped or masked whatever could reveal one. The orchestrator
decided every group under your delegation: the AgentDyn passwords are model-generated (round 1's item 6 again); the
OpenAgentSafety logins, FragFuse and kexin-xu values, ControlArena test keys and RedCode run-time keys are
synthetic-benchmark; code-agent-misalignment's 293 are a file-to-SHA-256 manifest (false-positive); 14 findings in
`atia-benchmark`, `openagentsafety` and `tacit-agentdojo`, and 3 `agentdyn-b` files holding 4 unexplained private keys,
are withheld through D-964 (the verdicts table gives the new figures).

### 4c. Account paths (D-457), by ordinal and the records that hold them

| Corpus | benchmark-input | model-generated | raw only (released) | only in withheld files |
|---|---|---|---|---|
| `agentdyn-b` | 2 (#3, #6) | 4 (#1, #2, #4, #5) | 14 (#7, #8, #9, #10, #11, #12, …) | 0 |
| `agentdyn-c` | 5 (#1, #2, #3, #4, #5) | 1 (#6) | 14 (#7, #8, #9, #10, #11, #12, …) | 0 |
| `agentops-bench` | 0 | 0 | 0 | 1 (#1) |
| `code-agent-misalignment` | 0 | 0 | 0 | 4 (#1, #2, #3, #4) |
| `controlarena-persistent` | 0 | 0 | 0 | 10 (#1, #2, #3, #4, #5, #6, …) |
| `credleak-p15b` | 0 | 0 | 0 | 8 (#1, #2, #3, #4, #5, #6, …) |
| `fragfuse-agentharm` | 13 (#1, #2, #3, #4, #5, #6, …) | 5 (#11, #12, #13, #15, #16) | 0 | 2 (#19, #20) |
| `interbolt-agentdojo` | 0 | 0 | 0 | 1 (#1) |
| `kexin-xu-01-agentharm` | 12 (#1, #2, #3, #4, #5, #6, …) | 0 | 0 | 1 (#13) |
| `llm-lock-agentdojo` | 0 | 2 (#1, #2) | 0 | 0 |
| `mcphunt` | 1 (#1) | 0 | 0 | 4 (#2, #3, #4, #5) |
| `openagentsafety` | 3 (#1, #3, #4) | 1 (#2) | 9 (#5, #6, #7, #8, #9, #10, …) | 0 |
| `redcode-exec-openhands` | 3 (#1, #2, #3) | 0 | 0 | 0 |
| `redcode-exec-qwencode` | 1 (#1) | 0 | 0 | 0 |
| `tacit-agentdojo` | 0 | 1 (#1) | 0 | 0 |
| `what-surrounds` | 1 (#1) | 0 | 0 | 0 |
| `whistlebench` | 10 (#1, #2, #3, #4, #5, #6, …) | 1 (#10) | 1 (#12) | 0 |

Classes by the AER record kinds that hold a name (an aggregate per name, not round 1's first appearance per execution;
C-3 recomputes per ordinal on the sealed tree). Covered by earlier decisions: what-surrounds #1 (the MCPTox quote,
item 5); whistlebench #1 (the scenario user of all 8,800 high-agency samples) and #12 (the workstation account in
`error_retries` tracebacks, raw only: D-601, ships as pinned); OpenAgentSafety's 9 raw-only names (D-606, ship as
pinned); CredLeak's, ControlArena's, AgentOps', code-agent-misalignment's, interbolt's and the AgentHarm parts' names
in withheld files (D-605, D-344/D-345, D-608, D-609, D-456, D-604). `agentdyn-b` and `agentdyn-c` each have 14 raw-only
names, mostly the same names in both (same lengths and hit counts): run files of other AgentDyn parts at the same pin,
the pattern of round 1's agentdyn-a #18–#20 (item 6, `false-positive`); C-3 classes them per ordinal.

## 5. Datasheet statements (decision 15: for your approval)

Each draft passes the strict loader together with the committed table (closed keys, every figure declared and used,
unique ids) and the card lint as sealing applies it; the full rendered datasheet is linted again by each seal dry run.
Drafts are in `wave-2-pre-release-checks/statements.drafts.toml` beside this report; they go into
`corpora/datasheet-statements.toml` only after your approval. **Landed (decision 15, `54719b06`)** with final figures:
the re-forecasts of the 12 persona trees at `c8ce1d85` (llm-lock at `40ad6dde`, which changes nothing on the seal path)
moved only statement 1 and 2 counts, in two corpora: `llm-lock-agentdojo` model-generated addresses 324 → 325 and
their released executions 549 → 554; `mcphunt` benchmark-input addresses 28 → 26, model-generated 10 → 12, released
executions holding one 22 → 396 (the D-962 persona file moved 2 addresses from input to model-generated, and they occur
in many traces). No withheld-execution count moved. The six existing wave-2 rows keep their figures: the all-causes
per-rule probe confirms 272 patch files and 1 README (`cam-harness`), 13 runs (`agentops`), 164 and 24 logs
(`agentharm`), 9 executions (`openagentsafety`), and the CredLeak plan (326 secret + 21 personal-data objects, 5,422 +
7 executions); the census figures of `whistlebench-retry` and `credleak-workstation` describe the pinned raw logs and
stand. The memo-ozdincer row is confirmed by its plan (5 results files cited by 425 executions, 6 withheld, 419
released). **Item 17** (open): one disclosure row per corpus for D-964's withholds, in
`statements.d964.drafts.toml` (lint clean).

| Statement | Corpora | State |
|---|---|---|
| D-810 statement 1, `fictional-benchmark-personas-<corpus>` (decided wording) | every corpus with benchmark addresses | drafted, figures from check 4a |
| D-810 statement 2, `model-generated-addresses-kept-<corpus>` (decided wording) | every corpus with model-written addresses | drafted |
| D-810 statement 3, `model-freemail-addresses-withheld-<corpus>` (decided wording) | every corpus with a `withhold` address (llm-lock: 920 executions, decision 10) | drafted |
| D-810 statement 4, `raw-objects-withheld-for-addresses-<corpus>` (**new wording** for D-961/D-962: objects withheld alone, cited or not) | every corpus with a `withhold-object` address | drafted |
| `what-surrounds-benchmark-home-path` | what-surrounds | drafted (decision 5) |
| `credleak-canary-runs-withheld` | credleak-p15b | drafted (decision 6) |
| `controlarena-metadata-only-release` | controlarena-persistent | drafted (decision 9) |
| `mcphunt-canary-flagged-traces-withheld` | mcphunt | drafted: 4,595 flagged traces (D-289 census, equal to the index and register) + 1 byte-rule hit (`aws-access-key-id`, a derived-file hit) = 4,596 withheld; 2,190 released |
| `memo-ozdincer-shared-results-files-withheld` | memo-ozdincer-agentdojo | drafted (decision 13) |
| Existing wave-2 rows: `cam-harness-account-path-withheld`, `whistlebench-retry-traceback-account`, `credleak-workstation-account-in-raw-tool-output`, `openagentsafety-raw-account-paths`, `agentops-account-path-withheld`, `agentharm-raw-withheld-account-paths` | as named | **figure recount by rule id pending** (the per-rule plan probes, paused for DTap's quiet window) |
| `redaction-labels-guessable`, `implied-prov-inferences`, `art-n7-activity-times` (`corpora = ["*"]`) | all | exist; apply unchanged |
| Licences, copyleft (D-94) and the AgentHarm restriction | per profile | rendered by sealing from each profile's `[licence]` (restrictions verbatim); no statement needed |
| Building commit | all 43 | recorded: every tree's `build_steps` names its building commit (D-780), so the datasheet states it; round 1's `building-commit-by-digest-*` statements are not needed |
| D-901 (EnvironmentOptim excluded, withdrawn upstream) | none of the 43 | a collection-level note for the deposit README (release prep), not a per-corpus statement |

## 6. Seal dry runs

`agentprov package --corpus <tree> --corpus-version 0.1.0 --spec corpora/<id>/corpus-spec.toml [--licence-file
LICENSE=…] --dry-run`, in process with the withholding plan captured, from clean detached checkouts, through the queue.
Exact refusals before the fixes: `package.refused.catalogue` for 37 trees (D-960), a usage error for `agentdyn-c`
(D-960), `package.refused.licence_file` for ATIA (fetched, decision 3). After them all 43 exit 0. ATIA's forecast ran
with a labelled placeholder licence file (the file only changes `LICENSES/` and `NOTICE.md`); its final dry run uses the
fetched file.

**Licence files at sealing (`--licence-file LICENSE=…`):** 28 corpora, the source's `LICENSE` at the pin (read offline
from the local git cache with `GIT_NO_LAZY_FETCH=1`); ATIA, the file fetched at the pin; 10 CC-BY-4.0 corpora
(`authority-caps-agentdojo`, `autogen-guard-placement`, `code-agent-misalignment`, `credleak-p15b`,
`ipi-defenses-agentdojo`, `mcphunt`, `redcode-exec-openhands`, `redcode-exec-qwencode`, `seagent-agentdojo`,
`what-surrounds`), the CC BY 4.0 legal code with round 1's bytes; `agentops-bench`, `controlarena-persistent`,
`dca-agentdojo` and `drift1-agentdojo`, none (their `NOTICE.md` gives the licence basis). The scratch copies and their
sha256 are listed in section 10.

* **Interpreter.** Every tree records Python 3.14.8 or 3.14.9 and no interpreter advisory; the floor is 3.14.8.
* **Release mode** needs a clean checkout and one commit (`package.refused.git`). Seal all 43 from one clean commit
  that carries items 12, 13 and 15, after a final dry run of all 43 there (the forecasts here ran at the commits named
  in the verdicts table; the final run repeats the plan and the datasheet render and lint at the sealing commit).
* **`verify --release`** and the real `tools/release_scan.py` are post-seal steps, as in round 1.

### 6a. The seal (2026-10-29)

The final dry run of all 43 at `c0e711f4` (the merge of D-964, its spec tables, the decision-15 and item-17
statements; `src/` and `tools/` equal to `b936451b`'s) repeated every forecast. The 43 were then sealed from a clean
detached checkout of `c0e711f4` (`~/.agentprov/merge-train/w2prc-seal`), one at a time through the queue, with
`--corpus-version 0.1.0` and the licence files of check 6. Per tree, in this order: `package`, a comparison of the
sealed counts with the forecast (withheld objects, withheld executions, released executions; the loop stops on the
first mismatch), the real `tools/release_scan.py` (gitleaks 8.30.1), and `verify --level chain`.

* **Seal:** 43 of 43 exit 0, and every tree's three counts equal its forecast (the verdicts table). One alarm, on
  `bookkeeper-agentdojo`, was the checker's: it read the absent withheld counters of a corpus with nothing withheld as
  `None` rather than 0. The seal had exited 0 and its counts matched; the checker was fixed and that tree's next steps
  were run by hand.
* **`verify --level chain`:** 43 of 43 exit 0 (for the four D-964 corpora this includes `withheld.listed_released`).
* **Release scan:** 28 exit 0 and 15 exit 1, with 712,538 findings still `untriaged`. The 15 are `what-surrounds`,
  `openagentsafety`, `fragfuse-agentharm`, `tacit-agentdojo`, `code-agent-misalignment`, `kexin-xu-01-agentharm`,
  `redcode-exec-qwencode`, `agentdyn-c`, `agentdyn-b`, `redcode-exec-openhands`, `controlarena-persistent`, `mcphunt`,
  `whistlebench` (680,365 of the untriaged), `credleak-p15b` and `llm-lock-agentdojo`. Across all 43 the scan classed
  1,526,303 findings `synthetic-benchmark`, 17,745 `model-generated` and 52,880 `false-positive`. The untriaged ones
  are C-3's work (`tools/release_triage.py` with decision 11's verdicts), a deposit gate, as planned; no triage was
  done here.
* **Not done:** no tag (the seal tags need their own yes), no `--release` package and no push.

## 7. Recompute at the building commit

**Before the seal.** The wave-2 session ran `recompute --dry-run` for every tree at its building commit, from its build
worktree, at 4 workers against the import's 5 or 8 (`batch1`..`batch5/<tree>.recompute.json`): all 43 report every
selected execution identical, 0 changed, 0 failed, 0 unverified (inventory table). Each tree's `build_steps` records
its building commit, equal to its `wave2/build-*` tag in every case.

**After the seal (D-358).** Each sealed tree was recomputed with `recompute --dry-run --jobs 4` at its building commit,
from a clean detached checkout of its `wave2/build-*` tag (`~/.agentprov/merge-train/w2prc-b-<commit>`), through the
queue. This is not round 1's method: round 1's D-358 re-imported each source and compared the bytes with the
`pre-regen.partial` tree, and never recomputed a sealed tree. A tree passes when every selected execution is
`identical`, or `unverified` because a raw object it needs is withheld (the notice "raw objects withheld by the
source are absent: the executions that need them are unverified, not re-derived (H.4.5(6))"), with 0 changed,
0 explained changes, 0 failed and no unexplained corpus file. One corpus file has a wider rule, the orchestrator's of
2026-10-30: `raw/origins.jsonl` may lose rows, and gain none, when every lost row is mapped to a withheld object or to an
unverified or withheld execution.

**The D-964 corpora** (`atia-benchmark`, `openagentsafety`, `tacit-agentdojo`, `agentdyn-b`) carry
`agentprov-withheld/0.5`, which their building commits cannot read. They ran at their tag with two files from
`c0e711f4` and nothing else: `src/agentprov/corpus/withheld.py` (sha256 `7a8ee19d…`) and
`src/agentprov/schemas/withheld-0.5.schema.json` (`4eb40aed…`), each byte-equal to `c0e711f4`'s
(`~/.agentprov/merge-train/w2prc-r-<commit>`; `git status` shows exactly these two). Neither file is in a stage scope:
all 41 stage digests of each patched checkout equal those of its clean tag (`tools/r1/stage_digests.py`, for
`0ea673f7`, `3bb905d9`, `7285a516` and `f8b5d62b`). The orchestrator accepted this reader for the D-964 corpora.

| Tree | Building commit | Selected | Identical | Unverified | Withheld objects missing | D-358 |
|---|---|---:|---:|---:|---:|---|
| `atia-benchmark-w2` | `3bb905d9` + D-964 reader | 110 | 0 | 110 | 18 | OK |
| `aiauthz-agentdojo-w2` | `0ea673f7` | 174 | 174 | 0 | 3 | OK |
| `yockcheng-prompt-injection-harness-w2` | `0ea673f7` | 280 | 280 | 0 | 1 | OK |
| `bookkeeper-agentdojo-w2` | `0ea673f7` | 570 | 570 | 0 | 0 | OK |
| `drift1-agentdojo-w2` | `0ea673f7` | 626 | 626 | 0 | 1 | OK |
| `shreeyavarma-llm-safety-w2` | `0ea673f7` | 672 | 672 | 0 | 1 | OK |
| `sentry-agentdojo-w2` | `0ea673f7` | 674 | 674 | 0 | 0 | OK |
| `menelaus29-ipi-multidomain-w2` | `0ea673f7` | 858 | 858 | 0 | 0 | OK |
| `kongminos-agentdojo-w2` | `0ea673f7` | 950 | 950 | 0 | 0 | OK |
| `hilarytorn-trajectory-poisoning-w2` | `0ea673f7` | 990 | 990 | 0 | 0 | OK |
| `autogen-guard-placement-w2` | `7285a516` | – | – | – | – | pre-seal (exit 70, withheld input archive) |
| `craibench-agentdojo-w2` | `0ea673f7` | 1,163 | 1,163 | 0 | 1 | OK |
| `what-surrounds-w2` | `7285a516` | 1,334 | 1,334 | 0 | 0 | OK |
| `openagentsafety-w2` | `7285a516` + D-964 reader | 1,558 | 1,551 | 7 | 7 | OK (origins rows mapped) |
| `drift-head-w2` | `0ea673f7` | 1,564 | 1,564 | 0 | 5 | OK |
| `fragfuse-agentharm-w2` | `3bb905d9` | 1,747 | 0 | 1,747 | 350 | OK |
| `glitch-agentdojo-w2` | `0ea673f7` | 1,842 | 1,842 | 0 | 2 | OK |
| `melon-agentdojo-w2` | `0ea673f7` | 1,911 | 1,911 | 0 | 1 | OK |
| `interbolt-agentdojo-w2` | `0ea673f7` | 2,016 | 2,016 | 0 | 24 | OK |
| `tacit-agentdojo-w2` | `0ea673f7` + D-964 reader | 2,070 | 2,070 | 0 | 10 | OK |
| `code-agent-misalignment-w2` | `7285a516` | – | – | – | – | pre-seal (exit 70, withheld input archive) |
| `kavach-agentdojo-w2` | `3bb905d9` | 2,619 | 2,619 | 0 | 7 | OK |
| `kexin-xu-01-agentharm-w2` | `3bb905d9` | 2,796 | 1,697 | 1,099 | 842 | OK |
| `geryon-agentdojo-w2` | `0ea673f7` | 3,179 | 3,179 | 0 | 1 | OK |
| `ipi-defenses-agentdojo-w2` | `0ea673f7` | – | – | – | – | pre-seal (exit 70, withheld input archive) |
| `redcode-exec-qwencode-w2` | `7285a516` | 3,299 | 0 | 3,299 | 1 | OK |
| `agentops-bench-w2` | `7285a516` | – | – | – | – | pre-seal (exit 70, withheld input archive) |
| `mohameduk-agentdojo-w2` | `0ea673f7` | 3,628 | 3,628 | 0 | 4 | OK |
| `gate-agentdojo-w2` | `0ea673f7` | 3,870 | 3,870 | 0 | 4 | OK |
| `agentdyn-c-w2` | `296418cb` | 4,244 | 4,244 | 0 | 568 | OK |
| `agentdyn-b-w2` | `f8b5d62b` + D-964 reader | 5,167 | 5,167 | 0 | 485 | OK |
| `seagent-agentdojo-w2` | `0ea673f7` | – | – | – | – | pre-seal (exit 70, withheld input archive) |
| `redcode-exec-openhands-w2` | `f8b5d62b` | – | – | – | – | pre-seal (exit 70, withheld input archive) |
| `controlarena-persistent-w2b` | `7285a516` | – | – | – | – | pre-seal (exit 70, `KeyError`) |
| `mcphunt-w2b` | `f8b5d62b` + D-1001 | 2,190 | 0 | 2,190 | 28 | OK (D-1001 proof) |
| `linyxus-agentdojo-w2` | `0ea673f7` | 9,068 | 9,068 | 0 | 1 | OK |
| `whistlebench-w2` | `3bb905d9` | 9,200 | 7,750 | 1,450 | 58 | OK |
| `memo-ozdincer-agentdojo-w2` | `0ea673f7` | 13,064 | 12,645 | 419 | 6 | OK |
| `dca-agentdojo-w2b` | `296418cb` | – | – | – | – | pre-seal (exit 70, withheld input archive) |
| `ceferisbarov-agentdojo-w2` | `0ea673f7` | 18,438 | 18,438 | 0 | 5 | OK |
| `authority-caps-agentdojo-w2` | `0ea673f7` | – | – | – | – | pre-seal (exit 70, withheld input archive) |
| `credleak-p15b-w2b` | `296418cb` | – | – | – | – | pre-seal (exit 70, withheld input archive) |
| `llm-lock-agentdojo-w2` | `0ea673f7` | 52,387 | 52,387 | 0 | 920 | OK |
| `dtap-bench-w2c` (addendum) | `1adb6b36` + D-964 reader | 67,708 | 66,878 | 830 | 83 | OK under the D-358 re-map rule, mapping recorded (D-1002) |

**Result: 44 trees (the 43 and DTap, sealed later; see its addendum), every one accounted for: 34 OK after the seal
and 10 under option (a).**

* **34 OK** after the seal: 32 plain (`openagentsafety` among them, with its origins rows mapped), plus `mcphunt` under
  D-1001 and DTap under D-1002. Together they select 221,966 executions: 210,815 identical and 11,151 unverified, all for
  withheld raw objects; 0 changed and 0 failed. DTap's row is OK under the D-358 re-map rule (D-1002): its 8 re-mapped
  judge units and their register and origins rows are mapped in its addendum. In four trees the recompute could check no
  execution after the seal, because every execution needs a withheld object: `atia-benchmark` (all five of its Inspect archives are withheld, three for
  the decision-11 token and two under the profile's address rule), `fragfuse-agentharm`, `redcode-exec-qwencode` and
  `mcphunt` (below).
  The other large shares are `whistlebench` (1,450), `kexin-xu-01-agentharm` (1,099 of 2,796) and `memo-ozdincer`
  (419). For every unverified execution the evidence is the pre-seal recompute and `verify --level chain` on the
  sealed tree. `openagentsafety`: `raw/origins.jsonl` lost 39 rows and gained none. All
  39 are mapped (`recompute --out` into scratch at the patched `7285a516`, a multiset diff): 7 are withheld objects,
  22 are run files of the 9 unverified or withheld units, and 10 are task-workspace files of those units' 5 tasks;
  0 are unexplained.
* **9 exit 70** before any execution is checked, `adapter.archive_input`, "an archive input is exactly one stored
  container". Each of these trees has a stored input archive that the seal withheld, so the sealed tree has nothing to
  re-read: `autogen-guard-placement`, `code-agent-misalignment`, `ipi-defenses-agentdojo`, `agentops-bench`,
  `seagent-agentdojo`, `redcode-exec-openhands`, `dca-agentdojo`, `authority-caps-agentdojo` and `credleak-p15b`.
* **1 exit 70 with a `KeyError`** on an object digest: `controlarena-persistent`, sealed metadata-only (decision 9, all
  5,742 executions withheld, 0 released).
* For these ten, D-358 is the pre-seal recompute at the building commit (all identical) together with `verify --level
  chain` on the sealed tree (exit 0). This is option (a), the user's choice, relayed by the orchestrator. Nothing was
  patched to make them run.
* **`mcphunt`: OK with D-1001** (the user's "Yes to both", relayed by the orchestrator). Recompute at its building
  commit `f8b5d62b` and at `c0e711f4` refused it with `corpus.derive.limits_mismatch`: its sealed `corpus.json` has no
  `limits` record, so recompute replayed the default limits, while `mcphunt@3` raises `max_json_element_bytes`. D-1001
  (`abab97a3`, class 0) rebuilds the limits from the recorded profile and accepts them only when they hash to the AER's
  recorded `limits_sha256`. The proof ran at `f8b5d62b` with the D-1001 patch (all 41 stage digests equal to the clean
  tag's), `recompute --dry-run --jobs 8`, exit 0 (2026-10-29 19:15Z): the D-1001 notice, no refusal, 2,190 selected and
  2,190 unverified, 0 changed and 0 failed, 28 withheld objects absent. Every released execution reads one of the 28
  withheld objects, so after the seal the recompute checks no execution here either; the evidence for them is the
  pre-seal recompute (6,786/6,786 identical) and `verify --level chain` on the sealed tree. The sealed bytes are
  unchanged (not re-sealed). The approved known-issues text (statement `mcphunt-recompute-needs-d1001`, `e6843868`; it
  reaches `DATASHEET.md` at a future seal), word for word:

  > Recomputing this corpus needs agentprov with D-1001 or later: the sealed `corpus.json` does not record
  > `mcphunt@3`'s raised ingest limit (`max_json_element_bytes` = 64 MiB), so earlier versions, including its building
  > commit `f8b5d62b`, refuse with `corpus.derive.limits_mismatch`; D-1001 rebuilds the limit from the profile and
  > accepts it only when it matches the recorded `limits_sha256`.

  The same text is in the v0.1.0 release notes (known limits). For the Zenodo deposit, the builder's supported field is
  the record's `release.toml` `description_preamble` (it opens the deposit description, outside the sealed tree). The
  field is per record, so the text goes into the CC BY record that holds `mcphunt` (round 1's `R7.toml`; the wave-2
  records are not written yet), prefixed "MCPHunt (`mcphunt`): ". Not written there; that file is outside the
  repository.

Recompute on a sealed tree crashing (instead of reporting unverified executions) is a v0.2 roadmap item
(`docs/roadmap.md`).

## 8. Licence classes for the deposit

| Class (SPDX; restriction) | Corpora | Executions |
|---|---|---:|
| MIT | 21: agentdyn-b, agentdyn-c, atia-benchmark, ceferisbarov, controlarena-persistent, craibench, dca, drift-head, drift1, glitch, hilarytorn, kavach, kongminos, linyxus, melon, memo-ozdincer, menelaus29, mohameduk, openagentsafety, shreeyavarma, whistlebench | 99,706 |
| MIT; AgentHarm use restriction | fragfuse-agentharm, kexin-xu-01-agentharm | 4,544 |
| Apache-2.0 | agentops-bench, geryon, interbolt, tacit, yockcheng | 10,911 |
| CC-BY-4.0 | authority-caps, autogen-guard-placement, code-agent-misalignment, credleak-p15b, ipi-defenses, mcphunt, redcode-exec-openhands, redcode-exec-qwencode, seagent, what-surrounds | 67,069 |
| AGPL-3.0-only (each its own corpus and record, D-94) | aiauthz, gate, sentry | 4,718 |
| GPL-3.0-or-later (D-94) | bookkeeper | 570 |
| GPL-3.0 (D-94) | llm-lock | 53,307 |

**For release prep:** `llm-lock-agentdojo`'s profile says `GPL-3.0` (the upstream LICENSE states neither "only" nor "or
later"), a deprecated SPDX id; unlike the four other copyleft profiles it gives no copyleft restriction text, so its
datasheet says `no_restrictions`. Each copyleft corpus is its own record (D-94) and the AgentHarm class differs from
round 1's (MIT, not CC-BY-4.0), so it is its own record too. A change to the profile is class 1 and is not proposed for
v0.1; the Zenodo licence for that record is release prep's choice.

## Addendum: DTap (`dtap-bench-w2c`), a later batch

DTap is not in the first seal batch (your decision, relayed 2026-10-29: "Seal the other 43 trees without waiting for
DTap"). Its tree has 67,711 executions (profile `dtap-bench@3`, `aprov` v3, building commit `1adb6b36`; Apache-2.0 by
both dataset cards, no licence file in either dataset, so `files = []`). Decision 14 (final, confirmed in the
orchestrator's window): `ex_suw7` (210 calls, whose PROV tier sits at the 300 s per-job CPU budget) is **retried and
included**, not withheld (D-971 is parked). Its disclosure says it is included and derivable and that its success
depends on the per-job CPU budget and machine load; `failed_rows = 1` (`ex_dwfig`, 778 calls, `worker.limit.output`, a
registered failed row: datasheet item 24, the size limits of the D-935 addendum, AER kept, no PROV).

Wave 2 marked the tree passed as **`dtap-bench-w2c`**: the `recompute --out` of `dtap-bench-w2b` at its building commit
(identical executions; it drops 2 register rows the `--retry-failed` run wrote wrongly, D-981), `verify --level chain`
0 failed, `recompute --dry-run` 67,711 identical. Done here since: the D-810 origins pass over `w2c` (4,294 addresses:
4,001 benchmark-input, 220 model-generated, 11 `withhold` in 2 executions of 2 suites and 2 tasks, 62 `withhold-object`
in 80 raw objects; no upstream persona file exists for DTap) and the drafts of its spec, CARD, CHANGES and observed
persona file (`6187af41`, item 18: profile `dtap-bench@3`, one snapshot at HF `836caf2f`, no `[withhold]`). **Item 18
approved** ("yes approve", in the orchestrator's window), with a LICENSE added as in decision 4: the canonical Apache
License 2.0 text (11,358 bytes, sha256 `cfc7749b…3d30`, the well-known digest; three independent local copies agree),
supplied at sealing with `--licence-file`, since neither dataset publishes one and Apache-2.0 section 4(a) asks for a
copy. The existing DTap statements (`dtap-*`, rows 6 to 11) apply to `dtap-bench` and are recounted with its D-810
rows.

**Sealed 2026-10-29** from `3000b220` (`3000b220aa8fbdf9c3716647f896bc3e2ef4a31e`, recorded as `producer.git_commit`),
run alone through the queue (the user's advance approval, relayed by the orchestrator). Dry run and seal: 67,708
released executions, 3 withheld executions, 83 withheld objects and `failed_rows` 1 (`ex_dwfig`), equal to the forecast.
Sealed content digest `sha256:b12d51a9…c2c0` (311,120 files, 47.7 GB). Release scan exit 1 (findings for C-3).
`verify --level chain` exit 0. Nothing tagged.

**D-358** (`recompute --dry-run --jobs 12` at `1adb6b36` with the D-964 reader): exit 1. 67,708 selected: 66,878
identical, 830 unverified (each needs a withheld object: 824 a task configuration, 6 a run file), 0 changed, 0 failed
(`ex_dwfig` fails as before). Beyond these, the re-map produced 8 executions the sealed tree does not have, and
`register.jsonl` (6 rows removed, 111 added) and `raw/origins.jsonl` (4 removed) differ. A diagnosis run (the same dry
run, reporting patched only) mapped all of it (`wave-2-pre-release-checks/dtap-d358-mapping/`):

* The 8 are outcome-only units (`map.no_execution_observed`), each a `judge_result.json` that the re-map left beside a
  file it drops on purpose. `exclude_absent` drops the withheld objects and the inputs only unverified executions use
  (RC-13), by sha256; a shared object is kept (RC-14), and so are a withheld execution's own files. In the sealed tree
  exactly 8 kept objects sit beside a dropped file, and they are these 8: 3 are the own judge files of the 3 withheld
  executions, 4 are judge files whose content other runs share (beside a dropped trajectory of an unverified execution)
  and 1 sits beside a withheld synthetic non-execution file.
* All 121 lines concern the paths of these 8 objects or the 8 units: the units' 8 `map.no_execution_observed` rows,
  102 `dedup.collapsed` rows of other path instances of the same objects, and the changed rows of five "(1)" copies
  (4 of them with their origins rows) and of one judge beside a synthetic file.
* The sealed bytes are not affected: every execution present in both trees is identical, the pre-seal recompute at
  `1adb6b36` was 67,711/67,711 identical with 0 unexplained, and the chain verifies. The code fix (`exclude_absent` also
  drops a dropped file's unit-directory neighbours and a withheld execution's files) is a v0.2 roadmap item.

Release safety: the 6 released supporting files of the 3 withheld executions hold neither of the 2 gatewayToken values
nor any `withhold` or `withhold-object` address (only 42 benchmark-input addresses, triaged synthetic-benchmark by the
release scan); a fixed-string search of the whole released tree finds the token in no file. Checked by digest and
count; no value was printed or kept.

**Verdict: OK under the D-358 re-map rule, mapping recorded.** The rule is D-1002 (i)–(iv), approved by the user ("Approve
the rule", in the orchestrator's window, 2026-10-30).

## 9. Code changes and follow-ups

Made and approved (class 0): D-960, D-961, D-962, D-963 (check 3). None class 1. Proposed, not made:

| Id | Change | Class | Needed before |
|---|---|---|---|
| C-W1 | `tools/release_scan.py --forecast` (round 1's C-2, still unbuilt): this check's `forecast.py` as a tool, with the plan's withheld labels and the per-finding gitleaks origins | 0 | the next pre-release check |
| C-W2 | A `--pin-doi` (or Hugging Face revision) option for `scan_origins --out`: the observed files of the Zenodo, Figshare and HF sources were written with a wrapper here | 0 | the next D-810 pass |
| C-W3 | `find_addresses`: one reading of a backslash run for decoded and stored text (the `b`/`f` asymmetry D-962 works around) | 0, but every observed file and scan fingerprint would be re-derived | v0.2 |

## 10. Housekeeping (for you; nothing touched)

| Item | Contents |
|---|---|
| `~/.agentprov/merge-train/w2prc-specs`, `w2prc-main`, `w2prc-d960` | detached scratch worktrees of this check, each with its `.venv` (about 0.3 GB each); `git worktree remove` once this report is accepted. Local branches `claude/vibrant-darwin-c3315f-d960`, `-d961`, `-d963` and `scratch/w2prc-specs` (never pushed) can go with them |
| `~/.agentprov/merge-train/w2prc-seal` (`c0e711f4`), `w2prc-b-<commit>` (5 building tags), `w2prc-r-<commit>` (4 tags with the D-964 reader) | detached worktrees of the seal and of D-358 (about 0.22–0.34 GB each, 2.4 GB in all); the `w2prc-r-*` ones carry the two uncommitted reader files of check 7. Also `w2prc-dtap` (`3000b220`, DTap's seal), `w2prc-r-1adb6b36` (DTap's D-358, with the reader) and `w2prc-p-f8b5d62b` (the D-1001 proof). Keep them until DTap's D-358 is settled, then remove them with `git worktree remove --force` |
| Session scratchpad | the forecast, origins, probe and draft files (section 11), and the seal and D-358 logs (`seal/progress.log`, `d358/progress.log`, `d358/progress-r.log`); outside the repository and `~/.agentprov` |
| `~/.agentprov/corpora/dtap-bench-w2.partial` | superseded; never seal |

## 11. Reproduction and scratch

Scratch tools (session scratchpad, run with the core venv's `python -I`, through `tools/suite_queue.py --class import`):

| Script | What it does |
|---|---|
| `inventory.py`, `w2logs.py` | the 43 trees' manifest facts and the wave-2 import, validate, verify and recompute summaries |
| `origins_w2.py`, `origins.sh`, `origins2.sh` | the D-810 pass (`scan_origins.analyse` with the committed upstream lists; observed files with git, HF or DOI pins) |
| `gen_specs.py` | the spec, CARD and CHANGES drafts (origins from the recorded pins with `package`'s own functions) |
| `forecast.py`, `forecast-main.sh` | `package --dry-run` with the plan captured, plus the release-scan forecast and the per-finding gitleaks origins (round 1's scripts, adapted) |
| `plan_probe.py`, `rule_probe.py`, `ziphits.py` | the plan by rule id and entry; SEAgent's zip regions, value-blind |
| `notinaer.py`, `notinaer_features.py`, `acct_classes.py` | the not-in-AER locations and backslash features; account ordinals by record kind |
| `make_rows_w2.py`, `lint_drafts.py`, `report_tables.py` | the statement drafts and their lint; this report's tables |
