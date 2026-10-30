# Wave 2 corpora: final report (2026-10-29)

The wave-2 corpora session (Mac Studio, brief `~/.agentprov/handoff/wave-2-corpora.md`) fetched the identified wave-2
source parts and built them into **44 working corpora with 308,536 executions** under `~/.agentprov/corpora/`, about
238 GB. Every tree passed import, `validate`, `verify --level chain` and `recompute --dry-run` with 0 differences. The
8 round-1 corpora were not touched. Nothing is sealed here: the wave-2 pre-release checks seal the 44 trees and write
their own seal report. The trees are listed in `~/.agentprov/migration-work/wave-2/valid-trees.txt`.

## What was built

- **Parts.** The registry's 53 planned parts and the 2 partial ones (`agentdyn · c`, `autodojo · rope-slice`), less:
  - EnvironmentOptim, excluded by the user after it was withdrawn upstream (D-901);
  - `agentdyn · history`, still `planned` (fingerprint deduplication is deferred to v0.2);
  - `drift · history`, reference-only;
  - `autodojo · rope-slice`, already counted in round-1 `rope`.

  Several corpora hold more than one part or snapshot: ControlArena 5 snapshots, RedCode-OpenHands 6 (one per zip,
  D-932), Kavach 3 (D-253), and dca-agentdojo the `v1` and `drift` parts.
- **Building commits** (D-780; each kept as a local tag `wave2/build-<commit>`; the per-commit archive goes with the
  Zenodo software record, option C):

  | Commit | Trees | Head commit of the build |
  |---|---|---|
  | `0ea673f7` | 25 corpora of batch 1 | D-830 (wave-2 parts planned → partial) |
  | `3bb905d9` | 5: whistlebench, atia, kexin, fragfuse, Kavach (rebuilt as one tree) | D-830 (on the rebased branch) |
  | `7285a516` | 7: ControlArena (rebuilt), AgentOps, AutoGen, code-agent-misalignment, OpenAgentSafety, qwen-code, what-surrounds | D-833 (dtap, mcphunt, dca planned → partial) |
  | `296418cb` | 3: agentdyn-c, credleak-p15b (rebuilt), dca-agentdojo (rebuilt) | D-930 |
  | `f8b5d62b` | 3: agentdyn-b, mcphunt (rebuilt), redcode-exec-openhands | a merge of D-930..D-933 |
  | `1adb6b36` | dtap-bench | D-934, after D-935 |

- **Decisions of this wave:**
  - D-930: assessments cite no `unk` premise field (NE-12; aprov catalogue v3).
  - D-931: per-source map memory cap (MCPHunt).
  - D-932: multi-pin imports and RedCode supplementary context.
  - D-933: AgentDyn B profile v4.
  - D-934: DTap strings over 1 MiB are not inlined.
  - D-935: PROV-document parse limit and per-source prov memory cap. The D-935 addenda give the DTap outcome.
  - D-981: a resumed import counts a skipped unit's auxiliary files as used.
  - D-950 (the artefact-scope session): the artefact-catalogue entries for the wave-2 corpora.
  - Parked, not on main: D-970 (per-source CPU budget, v0.2) and D-971 (spec-named `resource` withholding, not chosen).

## The corpora

Census is the per-part figure of `docs/user-guide/14-corpora.md` unless the note says otherwise. Validate counts
passed executions. "Unclassified artefact ids" counts the `artefact.unclassified.*` ids in the after-census of the
artefact-scope pass (D-950; `migration-work/wave-2/artefacts/after/`). "D-810 addresses" counts the distinct address
digests the count pass found (cleared by persona files or withheld at sealing; nothing is withheld until sealing).
Disk is `du` of the working tree.

| Tree (`~/.agentprov/corpora/<tree>.partial`) | Census | Executions | Status ok / with issues / failed | Validate passed | Verify chain | Recompute | Built at | Unclassified artefact ids | D-810 addresses | Disk | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `agentdyn-b-w2` | 5,184 | 5,184 | 5,087 / 97 / 0 | 5,184 | 0 failed | 5,184 identical, 0 unexplained | `f8b5d62b` | 0 | 481 | 2.4 GB | profile v4 (D-933) |
| `agentdyn-c-w2` | 4,258 | 4,258 | 2,254 / 2,004 / 0 | 4,258 | 0 failed | 4,258 identical, 0 unexplained | `296418cb` | 0 | 481 | 1.9 GB |  |
| `agentops-bench-w2` | 3,360 | 3,360 | 2,681 / 679 / 0 | 3,360 | 0 failed | 3,360 identical, 0 unexplained | `7285a516` | 0 | 61 | 0.6 GB |  |
| `aiauthz-agentdojo-w2` | 174 | 174 | 104 / 70 / 0 | 174 | 0 failed | 174 identical, 0 unexplained | `0ea673f7` | 0 | 1 | 0.0 GB |  |
| `atia-benchmark-w2` | 123 | 123 | 123 / 0 / 0 | 123 | 0 failed | 123 identical, 0 unexplained | `3bb905d9` | 0 | 10 | 0.4 GB |  |
| `authority-caps-agentdojo-w2` | 18,739 | 18,739 | 18,266 / 473 / 0 | 18,739 | 0 failed | 18,739 identical, 0 unexplained | `0ea673f7` | 0 | 134 | 5.4 GB |  |
| `autogen-guard-placement-w2` | 1,080 | 1,080 | 1,040 / 40 / 0 | 1,080 | 0 failed | 1,080 identical, 0 unexplained | `7285a516` | 0 | 8 | 0.4 GB |  |
| `bookkeeper-agentdojo-w2` | 570 | 570 | 565 / 5 / 0 | 570 | 0 failed | 570 identical, 0 unexplained | `0ea673f7` | 0 | 1 | 0.1 GB |  |
| `ceferisbarov-agentdojo-w2` | 18,442 | 18,442 | 18,287 / 155 / 0 | 18,442 | 0 failed | 18,442 identical, 0 unexplained | `0ea673f7` | 1 | 125 | 5.6 GB |  |
| `code-agent-misalignment-w2` | 2,182 | 2,182 | 968 / 1,214 / 0 | 2,182 | 0 failed | 2,182 identical, 0 unexplained | `7285a516` | 1 | 382 | 3.2 GB |  |
| `controlarena-persistent-w2b` | 5,742 | 5,742 | 2,463 / 3,279 / 0 | 5,742 | 0 failed | 5,742 identical, 0 unexplained | `7285a516` | 2 | 452 | 108.3 GB | rebuilt after the Inspect not-inlined fix (item 28) |
| `craibench-agentdojo-w2` | 1,163 | 1,163 | 475 / 688 / 0 | 1,163 | 0 failed | 1,163 identical, 0 unexplained | `0ea673f7` | 0 | 4 | 0.2 GB |  |
| `credleak-p15b-w2b` | 19,636 | 19,636 | 19,636 / 0 / 0 | 19,636 | 0 failed | 19,636 identical, 0 unexplained | `296418cb` | 1 | 92 | 3.2 GB | rebuilt (w2 trashed) |
| `dca-agentdojo-w2b` | 16,221 | 16,221 | 11,451 / 4,770 / 0 | 16,221 | 0 failed | 16,221 identical, 0 unexplained | `296418cb` | 1 | 135 | 3.7 GB | v1 + drift parts; rebuilt (w2 trashed) |
| `drift-head-w2` | 1,569 | 1,569 | 1,252 / 317 / 0 | 1,569 | 0 failed | 1,569 identical, 0 unexplained | `0ea673f7` | 0 | 130 | 0.4 GB |  |
| `drift1-agentdojo-w2` | 626 | 626 | 546 / 80 / 0 | 626 | 0 failed | 626 identical, 0 unexplained | `0ea673f7` | 0 | 86 | 0.2 GB |  |
| `fragfuse-agentharm-w2` | 1,747 | 1,747 | 1,721 / 26 / 0 | 1,747 | 0 failed | 1,747 identical, 0 unexplained | `3bb905d9` | 0 | 72 | 0.7 GB | restricted use |
| `gate-agentdojo-w2` | 3,872 | 3,870 | 2,822 / 1,048 / 0 | 3,870 | 0 failed | 3,870 identical, 0 unexplained | `0ea673f7` | 0 | 145 | 0.9 GB | 2 byte-identical copies collapse |
| `geryon-agentdojo-w2` | 3,179 | 3,179 | 3,150 / 29 / 0 | 3,179 | 0 failed | 3,179 identical, 0 unexplained | `0ea673f7` | 1 | 15 | 1.0 GB |  |
| `glitch-agentdojo-w2` | 1,844 | 1,844 | 1,843 / 1 / 0 | 1,844 | 0 failed | 1,844 identical, 0 unexplained | `0ea673f7` | 0 | 85 | 0.5 GB |  |
| `hilarytorn-trajectory-poisoning-w2` | 990 | 990 | 990 / 0 / 0 | 990 | 0 failed | 990 identical, 0 unexplained | `0ea673f7` | 0 | 9 | 0.4 GB |  |
| `interbolt-agentdojo-w2` | 2,016 | 2,016 | 2,015 / 1 / 0 | 2,016 | 0 failed | 2,016 identical, 0 unexplained | `0ea673f7` | 0 | 7 | 0.7 GB |  |
| `ipi-defenses-agentdojo-w2` | 3,211 | 3,211 | 3,209 / 2 / 0 | 3,211 | 0 failed | 3,211 identical, 0 unexplained | `0ea673f7` | 0 | 2 | 0.6 GB |  |
| `kavach-agentdojo-w2` | 2,625 | 2,625 | 2,515 / 110 / 0 | 2,625 | 0 failed | 2,625 identical, 0 unexplained | `3bb905d9` | 1 | 115 | 0.4 GB | one tree, 3 snapshots in order (D-253); the corpus table's per-snapshot log counts sum to 3,218, and logs shared across snapshots are one execution each, giving the 2,625 D-253 expects |
| `kexin-xu-01-agentharm-w2` | 2,825 | 2,797 | 2,746 / 51 / 0 | 2,797 | 0 failed | 2,797 identical, 0 unexplained | `3bb905d9` | 0 | 95 | 1.0 GB | 28 samples of 2 unfinished headerless logs are not executions (registry note); restricted use |
| `kongminos-agentdojo-w2` | 950 | 950 | 779 / 171 / 0 | 950 | 0 failed | 950 identical, 0 unexplained | `0ea673f7` | 0 | 76 | 0.3 GB |  |
| `linyxus-agentdojo-w2` | 9,068 | 9,068 | 7,988 / 1,080 / 0 | 9,068 | 0 failed | 9,068 identical, 0 unexplained | `0ea673f7` | 0 | 123 | 2.4 GB |  |
| `llm-lock-agentdojo-w2` | 53,307 | 53,307 | 0 / 53,307 / 0 | 53,307 | 0 failed | 53,307 identical, 0 unexplained | `0ea673f7` | 0 | 913 | 15.8 GB |  |
| `mcphunt-w2b` | 6,786 | 6,786 | 6,241 / 545 / 0 | 6,786 | 0 failed | 6,786 identical, 0 unexplained | `f8b5d62b` | 0 | 265 | 8.4 GB | rebuilt after D-931 (map memory cap) |
| `melon-agentdojo-w2` | 1,911 | 1,911 | 1,905 / 6 / 0 | 1,911 | 0 failed | 1,911 identical, 0 unexplained | `0ea673f7` | 0 | 7 | 0.4 GB |  |
| `memo-ozdincer-agentdojo-w2` | 13,070 | 13,070 | 10,443 / 2,627 / 0 | 13,070 | 0 failed | 13,070 identical, 0 unexplained | `0ea673f7` | 0 | 136 | 4.0 GB |  |
| `menelaus29-ipi-multidomain-w2` | 858 | 858 | 856 / 2 / 0 | 858 | 0 failed | 858 identical, 0 unexplained | `0ea673f7` | 1 | 69 | 0.2 GB |  |
| `mohameduk-agentdojo-w2` | 3,630 | 3,630 | 3,614 / 16 / 0 | 3,630 | 0 failed | 3,630 identical, 0 unexplained | `0ea673f7` | 0 | 109 | 1.1 GB |  |
| `openagentsafety-w2` | 1,560 | 1,560 | 1,375 / 185 / 0 | 1,560 | 0 failed | 1,560 identical, 0 unexplained | `7285a516` | 1 | 124 | 3.3 GB |  |
| `redcode-exec-openhands-w2` | 5,460 | 5,460 | 5,460 / 0 / 0 | 5,460 | 0 failed | 5,460 identical, 0 unexplained | `f8b5d62b` | 0 | 122 | 1.7 GB | 6 zips, one snapshot each (D-932) |
| `redcode-exec-qwencode-w2` | 3,300 | 3,299 | 3,295 / 4 / 0 | 3,299 | 0 failed | 3,299 identical, 0 unexplained | `7285a516` | 1 | 136 | 0.7 GB | 1 empty output file, as the census expects |
| `seagent-agentdojo-w2` | 5,342 | 5,342 | 3,622 / 1,720 / 0 | 5,342 | 0 failed | 5,342 identical, 0 unexplained | `0ea673f7` | 0 | 301 | 1.7 GB |  |
| `sentry-agentdojo-w2` | 674 | 674 | 596 / 78 / 0 | 674 | 0 failed | 674 identical, 0 unexplained | `0ea673f7` | 0 | 74 | 0.2 GB |  |
| `shreeyavarma-llm-safety-w2` | 672 | 672 | 614 / 58 / 0 | 672 | 0 failed | 672 identical, 0 unexplained | `0ea673f7` | 0 | 81 | 0.2 GB |  |
| `tacit-agentdojo-w2` | 2,076 | 2,076 | 1,543 / 533 / 0 | 2,076 | 0 failed | 2,076 identical, 0 unexplained | `0ea673f7` | 0 | 93 | 0.6 GB |  |
| `what-surrounds-w2` | 1,334 | 1,334 | 1,334 / 0 / 0 | 1,334 | 0 failed | 1,334 identical, 0 unexplained | `7285a516` | 0 | 5 | 0.3 GB |  |
| `whistlebench-w2` | 9,200 | 9,200 | 4 / 9,196 / 0 | 9,200 | 0 failed | 9,200 identical, 0 unexplained | `3bb905d9` | 3 | 265 | 9.4 GB |  |
| `yockcheng-prompt-injection-harness-w2` | 280 | 280 | 277 / 3 / 0 | 280 | 0 failed | 280 identical, 0 unexplained | `0ea673f7` | 0 | 74 | 0.1 GB |  |
| `dtap-bench-w2c` | 67,808 | 67,711 | 59,998 / 7,712 / 1 | 67,710 | 0 failed | 67,711 identical, 0 unexplained | `1adb6b36` | 0 | — | 45.0 GB | census counts trajectory files: 92 byte-identical copies collapse, 20 synthetic runs and 2 LFS pointers (their pinned objects are imported) are registered, 8 files are excluded by the profile; recompute version of w2b (D-981); 1 registered failed execution (778 calls, output limit); 210-call run included, load-dependent (D-935, item 24); D-810 count pass not run here |
| **44 trees** | 308,664 | **308,536** | | | | | | | | **238 GB** | |

The census total differs from the executions by 128, all accounted for in the notes: gate 2, kexin 28, qwen-code 1
and DTap 97.

## Notes and open items

- **DTap.** The 778-call openclaw run is the corpus's one registered failed execution: its PROV is over the worker's
  output limit at any load. The 210-call openaisdk run was derived by a retry on an otherwise idle machine. Whether its
  prov job completes depends on the 300 s per-job CPU budget and the load (D-935 addenda, datasheet item 24).
  - The retry wrote 2 wrong register rows (D-981, fixed). The passed tree `dtap-bench-w2c` is the `recompute --out`
    version of the retried tree at the same building commit, with identical executions.
  - Its last recompute served tier 4 from the validation cache.
  - DTap's D-810 address count pass was not run by this session; the pre-release persona forecasts cover it before
    sealing.
- **Validation and recompute.** Every recompute ran at a second worker count, at the tree's building commit (F-8).
  DTap's verify used main's code: its building commit predates 4243cecd's PROV-document reader limit.
- **Withholding.** Nothing is withheld in a working tree. The `[withhold]` and redaction rules apply at import (as
  the profiles declare) and at sealing, with the D-810 persona files the pre-release checks draft.
- **Registry status.** The wave-2 parts stay `import partial` (D-830) until their corpora are sealed; changing them
  to `supported` is a class-1 registry change for after the seal.
- **Not built:** `agentdyn · history` (deduplication, v0.2), `drift · history` (reference-only), EnvironmentOptim
  (D-901).
- **Scratch.** Logs, check outputs and census files are in `~/.agentprov/migration-work/wave-2/` (7.4 GB). The bulky
  check outputs go to the Trash after the user's OK.
