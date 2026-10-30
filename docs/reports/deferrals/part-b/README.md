# Deferrals part B: the full-history AgentDojo fetch and what it decides (2026-10-12)

## The fetch (U-07; the user's yes in the deferrals session, 2026-10-12)

| | |
|---|---|
| Remote | `https://github.com/ethz-spylab/agentdojo` |
| Clone | bare, the full history of the head pin `089ed468`, all blobs, no checkout; hooks off, file protocol off, `fsck` on transfer, isolated git configuration; the pin held by `refs/pins/089ed468…` |
| Store | `$AGENTPROV_HOME/upstream/github.com/ethz-spylab/agentdojo.git` (outside the repository) |
| Size | 722 commits, 73,587 objects (50,221 blobs), 37.8 MB packed, 39.5 MB on disk; fetched in 4.3 s |
| Checks | `git fsck --full` clean; 0 objects missing from the pin's history; no promisor or filter configuration |
| Log | two rows in `~/.agentprov/cache/acquisitions.jsonl`: the retrieval (`mode = "bare-full-history-with-blobs"`), and a correction row for its `files` count (the first row recorded 0 through a counting error in the logging step; 50,221 is correct) |

## 1. The existing history index is complete (D-84 decided by evidence)

`tools/agentdojo/full_history_index.py` (`full-history-check.json`) recomputes each pin's introducing-commit index from the
full store, exactly as `Fetcher._compute_history_index` does, and compares it with the index cached beside the blobless
store (which the shipped history table, `introduced_under` and D-84 rest on):

| Pin | Entries | Recomputed = cached (bytes) | Full index agrees row for row |
|---|---|---|---|
| `2024-06` `c2748856` | 18,334 | yes (`278ae5f4…`) | yes |
| `head` `089ed468` | 36,860 | yes (`1cd7ed93…`) | yes |

So every pinned blob has an introducing commit, and the blobless store lost nothing. D-84's case "no introducing
commit" arises only when an import runs without the history index; the fail-closed rule (cite the twins) stays right for
that case and no stored record is affected. **No byte changes.**

## 2. The full-history index (the `history` part's input)

`agentprov.raw.history.FullHistoryIndex` (format `agentprov-history-index-full/1`; the selection rule of the pinned
indexes, applied to every version ever added under `runs/`), built by the same tool and kept beside the store
(`agentdojo.index/full-089ed468….jsonl`, rows `sha256:22cf59dd…`; derived data, not committed):

| | Count |
|---|---|
| `runs/` log versions in the head pin's history | 48,605 |
| held by both pins | 14,182 |
| held by one pin | 26,556 |
| **superseded** (held by neither pin: the planned `history` part) | **7,867** |
| introducing commits | 55 (2024-05-13 to 2025-07-25) |

The `agentdojo-upstream` profile's note on the `history` part says 11,173 superseded blob versions. This index counts
7,867 `(path, blob)` versions reachable from the head pin. The two definitions differ (the profile's count is from the
investigation and may include versions on refs other than the pin's history, or count distinct blobs differently);
the profile owner should reconcile the note before the `history` part is built.

## 3. The `v0.k11` system-prompt code states (D.6.12 item 6, D.6.11 item 9)

`tools/agentdojo/system_prompt_states.py` (`system-prompt-states.json`) reads the harness's default system message
(`src/<package>/data/system_messages.yaml`, `default` key, strict safe loader) at every commit of the head pin's history,
and the message-0 text of every pinned log (the mapper's digest rule):

- **One code state.** All 547 commits that carry the YAML file (first on 2024-05-29) have the same `default` digest,
  `a021a92b…1837`: the head pin's `agentdojo_default`. 175 earlier commits have no YAML file.
- **The logs.** Of the 28,973 pinned `v0.k11` logs, **27,866** carry exactly that text, equal to the code state in force
  at their own introducing commit (2024-06: 17,281; head only: 10,585). **900** carry another text, all in
  `runs/gpt-4o-2024-05-13-spotlighting_with_delimiting/` (the defence rewrites the system prompt by design). 207 are
  outcome-only logs with no system text.

**Proposal (user-approved 2026-10-12; implemented by the regen-batch session as its item 17):** extend the `agentdojo_default`
variant of `agentdojo-upstream` to the `v0.k11` variant. The label states a fact about the text (its digest equals the
default of the only code state the history ever had), not about the producing code, so it does not depend on D-84's
code coverage. Effect: `ext.agentdojo.system_prompt_variant` (D, `agentdojo.system_prompt_variant_digest@1`) on 17,281 of the
18,241 `agentdojo-upstream-2024-06` executions and 23,954 of the 24,914 `v0.k11` executions of `agentdojo-upstream-head`
(27,866 distinct logs), and either the info issue `agentdojo.system_prompt_unrecognised` on the spotlighting logs (753
in each corpus, 900 distinct) or an `applies` selector that
leaves that defence out (the owner's choice). It reverses the phase-6/phase-10 choice to keep `v0.k11` unlabelled, which
was made because no pinned code covered these logs: the full history now shows the text never changed.

## 4. Code ranges (the input to part C's AER-V34 widening)

`tools/agentdojo/code_ranges.py` (`code-ranges.json`) asks, for each of the 35 code citations at `c274885` of the 26
active class-D `agentdojo` rules: is the cited passage present (its exact lines; and, as a looser measure, with the
package name unified and whitespace collapsed) at **every** commit of `git rev-list c274885..<introducing commit>`, for
each of the 14 introducing commits of the 10,732 head-only `v0.k11` logs?

- Only `agentdojo.duration_scope@1` and `agentdojo.incomplete_run@1` hold for all 10,732 logs, and
  `agentdojo.call_id_unique_match@1` for 5,558. Every other rule fails for every introducing commit, under both
  measures.
- The reason is timing. The pin `c274885` is dated 2024-06-05. The cited passages changed within days after it: the
  first commits without them are dated 2024-06-06 (17 citations), 2024-06-11 to 2024-06-20 (13) and 2024-07-26 (1);
  4 never change. The head-only `v0.k11` logs were introduced from 2024-06-20 onwards (14 commits, the last
  2025-02-25), so every range `c274885..<introducing commit>` already contains the changed code. The introducing
  commit bounds the producing code only from above (D.6.16): a log may have been produced before the change and
  committed later, but nothing recorded shows it.

This is the evidence part C's design needs: a `verified` assumption over a code range can be stated honestly only
for passages that hold over the whole commit set the range denotes, which today is two rules (and one in part). See
`docs/reports/aer-0.2/` when written.

## Files

| File | What |
|---|---|
| `src/agentprov/raw/history.py` | `introducing_commits(..., tree=None, prefix=...)`; `FullHistoryIndex`, `build_full_index` (format `agentprov-history-index-full/1`) |
| `tests/unit/raw/test_full_history_index.py` | the full index's rule, superseded rows, agreement with the pinned indexes, refusal when incomplete |
| `tools/agentdojo/full_history_index.py` | builds the full index; byte-compares the pinned indexes |
| `tools/agentdojo/system_prompt_states.py` | the `v0.k11` code states |
| `tools/agentdojo/code_ranges.py` | the code ranges for part C |
| `full-history-check.json`, `system-prompt-states.json`, `code-ranges.json` | the reports (counts, digests, commit ids, paths; no log or prompt text) |
