# D-358: the old corpora reproduce at their building commit

D-358 (user ruling D-430, 2026-10-14) asks that each stored `-p10` corpus rebuild byte for byte from its raw inputs at
the commit and lockfile that built it. That is H.8's promise, checked at the building commit rather than at main. All
eight `-p10` corpora match **`afe7038`** by code and lockfile digests (`tools/regen/find_building_commit.py`; plan
§3.7). The check repeats each corpus's original import command at `afe7038` on the same pinned input, then compares the
whole output tree with the stored corpus, file by file (`tools/regen/tree_compare.py`, read only).

**Result: all eight reproduce.** In the seven corpora imported from a scratch checkout (`--input`), the only difference
is `corpus.json`'s `/sources/0/snapshots/0/origin/path`, the input directory. The plan allowed that difference in
advance. 2024-06 uses its original `--fetch --allow-network` and is identical in every file, `corpus.json` included.

## Setup

- **Code:** a scratch checkout of `afe7038` outside git (`read-tree` and `checkout-index` into
  `~/.agentprov/migration-work/regen-plan/build-afe7038/`), with its own `uv sync --locked --offline`. The lockfile
  digest is `da3cceee…`, the one every `-p10` manifest records.
- **Inputs:**
  - **Six corpora:** a scratch checkout of each verified cached pin, with `--verify-against-pin`.
  - **adprov-v1:** the pristine baseline clone.
  - **2024-06:** `--fetch` from the local cache.
- **Driver:** `tools/regen/d358_building_commit.sh`. It runs one `--class import` queue job at a time, and checks that
  `acquisitions.jsonl` is unchanged after each import. A fresh start renames an interrupted output tree aside; nothing
  is deleted.
- **Scratch only:** outputs went to `migration-work/regen-plan/out/d358-*`, and the stored corpora were read in place,
  read only. After the round they are named `<id>-p10.pre-regen.partial`.
- **Records:** built with `tools/regen/d358_records.py`. They hold counters, issue codes, file counts and digests only.

## Results

| Corpus | Executions (clean / with issues) | Files identical | `corpus.json` pointers that differ | Run (UTC date) | Workers | Wall min | Peak RSS GiB |
|---|---|---|---|---|---|---|---|
| mandate-agentdojo-eval | 396 (396 / 0) | 1,595 / 1,596 | origin path | 2026-10-13 | 8 | 3.7 | 0.93 |
| ast-survey-agentharm | 1,056 (1,052 / 4) | 4,243 / 4,244 | origin path | 2026-10-14 | 6 | 9.7 | 1.22 |
| ast-survey-agentdojo | 3,243 (3,184 / 59) | 12,989 / 12,990 | origin path | 2026-10-14 | 6 | 13.6 | 1.14 |
| adprov-v1-release | 17,664 (17,584 / 80) | 70,663 / 70,664 | origin path | 2026-10-14 | 6 | 51.2 | 1.47 |
| agentdojo-upstream-2024-06 | 18,241 (17,747 / 494) | **72,972 / 72,972** | none | 2026-10-23 | 4 | 50.9 | 1.04 |
| rope | 10,791 (9,366 / 1,425) | 43,206 / 43,207 | origin path | 2026-10-22 | 4 | 95.3 | 0.97 |
| agentdojo-upstream-head | 36,679 (33,745 / 2,934) | 146,723 / 146,724 | origin path | 2026-10-23 | 4 | 147.5 | 1.32 |
| agentdyn-a | 38,281 (35,904 / 2,377) | 162,573 / 162,574 | origin path | 2026-10-23 | 4 | 240.6 | 2.27 |

- **Imports:** every import exited 0, with 0 failed and 0 degenerate.
- **Comparisons:** every comparison had 0 files only in the stored corpus and 0 only in the rebuild.
- **Execution counts:** they equal the stored corpora's, as do the clean and with-issues splits.
- **Run times:** `timing.json` keeps `measure.py`'s `started`, which is the machine's local time (UTC+13).
- **Load:** the 2026-10-13 and 2026-10-14 runs shared the machine at load 12 to 47, so their wall times are not
  benchmarks.

## Notes

- **2024-06 and the network.** The user approved `--fetch --allow-network` in this session's window
  (2026-10-22T23:25Z; the 2026-10-14 approval was given elsewhere).
  `afe7038` predates D-220's offline `--fetch`, so the original command needs the flag. The local cache is a complete
  clone of the pin (commit `c274885`, `runs/` tree `1227480d`, 18,241 files). Nothing was fetched:
  - `acquisitions.jsonl` is unchanged (56 lines, `928c84d6…`);
  - the import log has no `network host=` line, and the fetcher logs every network action at that level.
- **ROPE and AER-V35 (a correction to plan §3.7).** Plan §3.7 said that 200 stored ROPE AERs pass the `afe7038`
  validator with "0 errors, 0 `aer.blob.digest`". That check did not test AER-V35. In file mode (`validate --release
  --store`) the `afe7038` validator is given no package profile digests, so it skips V35 ("profile digest (V35): no
  package profile digests given"). That skip is one of the six checks behind its exit 1.
  - The full run here has the same limit. Over every re-imported ROPE AER (22 batches, 10,791 files, 505,333 records),
    it found 0 errors, 0 failed and 0 warnings, and V35 was skipped in each batch (`rope/validate-afe7038.json`).
  - V35 does run inside the import. The importer's seal-time validator passes the profile digest
    (`adapters/runner/importer.py:774` at `afe7038`), and all 10,791 executions were validated and sealed with no
    `aer.blob.digest`. The AERs are byte-identical to the stored ones.
  - So the stored `rope-p10` AERs pass V35 against `afe7038`'s `rope@1` bytes. That supports plan §3.7's conclusion:
    main's old failure was F-1's same-version profile drift, not a defect of the stored corpus.
- **Interruptions.** The first AgentDyn run, on 2026-10-23, was killed after 4 h 08 min, when every background shell
  of the session was stopped together under memory pressure. A second run was stopped cleanly 4 minutes in, for a
  planned restart of the machine. The run in the table started fresh after the restart. 2024-06 had been paused by the
  user on 2026-10-14 at 3,584 of 18,241 executions, and restarted fresh. All three interrupted trees are kept, renamed
  `out/d358-*.interrupted-*.partial`, and are on the orchestrator's cleanup list. A resume was not an option. At
  `afe7038` the execution index is written only on a clean exit, and a resumed run is not the original command.

## Files

`<corpus>/import.json`, `<corpus>/tree.json`, `<corpus>/timing.json`; `rope/validate-afe7038.json`.
