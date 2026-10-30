# Pre-round review: re-check of the owner fixes on a19be82e

Date: 2026-10-22. Head: `integration/pre-round-2026-10-21` at a19be82e (fixes cdd26e34..a19be82e). The original review
is [report.md](report.md). The scope was the one the orchestrator set: verify each PR-1..PR-14 fix, and look for new
interactions among the fixes. This is not a full review.

## Verdict

**Ready for the round, with three conditions:**

1. **RC-1** (item 20 / #29): fix it, or keep live capture out of the round. The fix moves the agentdojo
   `adapter_code_sha256`, so it should land before the round's imports.
2. **Record PR-1's working-manifest change** (RC-3) before the round. Without it, the post-check cannot attribute the
   context `verification` bytes it will see.
3. **Add regen-batch rows for the fix commits** that have none (RC-4). The post-check needs them to explain the moved aer
   digests.

Every other open item is low severity and can land with or after the round. Of the original findings, PR-1, PR-2, PR-3,
PR-4, PR-6, PR-7, PR-8, PR-9, PR-10, PR-14 and the code lows are fixed. PR-5 and #29 are partly fixed. PR-13 is mostly
fixed.

## Method

- **Fix checks:** workflow `wf_cfced353-841`, 75 agents. Seven checkers, one per fix group, re-ran the original probes at
  a19be82e and at cdd26e34 (before and after). Any fix judged incomplete, and any new finding, went to two adversarial
  verifiers (reproduction, intent). Result: `~/.agentprov/review/pre-round/recheck-result.json`. Probes:
  `~/.agentprov/review/pre-round/probes-recheck/`.
- **Slim proofs:** through main's queue (`--class import --cpu 2`), no network, `GIT_NO_LAZY_FETCH=1`. Logs:
  `~/.agentprov/review/pre-round/proofs-recheck/`.

## Proofs

- **Re-map of the same 14 samples, FIX against INT.** Only code digests moved, and every move is attributed:
  - `corpus.json` `/adapters/0/code_sha256` and the `derivation.json` aer stage `adapter_code_sha256`,
    `engine_code_sha256` and `fn_digest`;
  - the agentdojo and adprov adapter digests moved by #29 (ac7526c4);
  - the aer engine digest moved by the importer fixes (8b99e8dc, 58213f5d, fb114e42, 22f197aa, ac7526c4).

  No AER, SEM, PROV, index, register, raw, validation or manifest content changed. Item 151 predicts changes for
  crash-path units only, and none occur in the samples.
- **recompute and verify:**
  - `recompute --dry-run` on all FIX scratch corpora: identical, no notices. `verify --level chain` is ok.
  - FIX on INT-built corpora: identical, with the aer code-digest notice only.
  - FIX on BASE-built 0.1 corpora: the PR-3 lines name the aer format, the corpus format and the vocabulary drift.
    AgentHarm gets the PR-10 notice.
- **PR-3 probe (what-surrounds):**
  - The dry run exits 0 and names the three drifts. At INT it exited 1.
  - `recompute --out` refuses with `corpus.derive.version_drift`, exit 4, before `NEW.partial` exists.
  - `members.jsonl` is explained (PR-10).
- **PR-14:** kexin-xu-01-agentharm, fragfuse-agentharm and environmentoptim-agentdojo now seal with the shipped statements
  table (corpus/0.2), and `verify --release` is 0.
- **PR-2:** real DTap with an LFS pinned object seals as corpus/0.2 (git origin, 2 pinned objects, tasks verification
  `{blob, 6682, 0}`), and `verify --release` is 0.
- **PR-1:** cannot run offline on real data. The fetch cache lacks the huggingface pins, and agentops and qwencode are
  `planned`. Instead:
  - 122 targeted tests pass through the queue (the fix's tests, the D-530/D-221 seal tests and the pre-check tests);
  - the checkers' probes seal a cache-route GitPinTree `tasks` tree and the qwencode `supp` archive. The `supp` zip with
    a synthetic token is withheld, the token is in no sealed byte, and `verify --release` is 0. At INT both were refused.

## Status of the original findings

| Finding | Status at a19be82e |
|---|---|
| PR-1 context verification | **fixed**: every CLI route records `{download\|blob}` and seals. Recording gap: RC-3 |
| PR-2 pinned LFS seal origin | **fixed**: the exclusion is by exact (sha256, origin), and a genuinely mixed primary is still refused |
| PR-3 version_drift format/vocab | **fixed**: (a) and (b) refuse, a current corpus is not refused, the notices name the drift |
| PR-4 context archive digest | **fixed** |
| PR-5 absent context/pinned object | **partly fixed**: no crash, dependents unverified; a purged pinned LFS object still exits 1 (RC-2) |
| PR-6 drain in re-maps | **fixed**: opt-in from `cli/import_`; re-maps degrade to a stop |
| PR-7 skip-conformance resume | **fixed**; side effect RC-9 |
| PR-8 sample with pinned object | **fixed** for multi readers; regression on non-multi readers (RC-5) |
| PR-9 pass-1 collapse | **fixed**: a full import still collapses (D-202) |
| PR-10 members fn_digest | **fixed**; low edge RC-7 |
| PR-11 #3, #4, #6, #7 | **fixed** |
| PR-12 #14, #16, #17, #19, #21; P-3; P-4 | **fixed**. P-3 truncates drift reasons (RC-8); P-4's documented guard is not enforced (RC-8) |
| PR-13 docs | **mostly fixed**: #24 not done; #22/#25/#27/#30 partly (RC-10) |
| PR-14 statements lint | **fixed**; the rendered wording is awkward (RC-11) |
| #29 capture_mapper and D-219 | D-219 and D-210 **fixed**; D-211 regresses tool messages (RC-1) |

## New findings (all adversarially verified)

### Medium

**RC-1. Item 20's D-211 withholding deletes a `tool_result` part's text, which the aer/0.2 schema cannot omit**
(CONFIRMED ×2).
- **Interaction:** ac7526c4 (`capture_mapper.py`, the dump-message `shape == "tool"` branch with `_withhold_parts`) ×
  part C's aer/0.2 part schema (`aer/_structure.py`).
- **Cause:** the schema's D-211 relaxation covers only text, reasoning and refusal `text`, tool_call `args` and other
  `value`. `partToolResult` stays oneOf text xor value.
- **Effect:** a live capture whose `pass.end` dump redacts a tool output, the main redaction case, now fails the write
  gate (`aer.schema.oneof` at `/parts/0`). `seal_outcome` then replaces the whole session with a 3-record degenerate AER
  (`adapter_defect`). At INT it sealed as a 20-record AER with `capture_redaction`.
- **Scope:** no committed fixture has this case, so no pin moves, and live capture is not in the round. But the fix
  moves the agentdojo adapter digest.
- **Probes:** `probes-recheck/d219-item20/probe_d211.py`, `probe_tool_fallback.py`.
- **Fix:** exclude `tool_result` parts from `_withhold_parts`, as D-211 and the aer-0.2 design §1.2 intend. Add a test
  with a redaction at a tool message's content.
- **Class:** 1. **Owner:** deferrals.

**RC-2. PR-5 residual: after a pinned LFS object is purged, `recompute` and `verify --level rederive` still exit 1**
(CONFIRMED medium/low).
- **Cause:** `drop_absent` removes the object, but the pointer stays in the primaries. The re-map then disposes the
  pointer's sibling `judge_result.json` under a path subject, which the BF-20 `accounted` filter (absent shas and
  `absent_ex` ids) does not cover. One `register.jsonl` row is added, classed UNEXPLAINED.
- **Test gap:** the new PR-5 test asserts only `code != 70` and `unexplained_change == 0`. It does not check
  `corpus_unexplained` or the exit code.
- **Probe:** `probes-recheck/10i-runner/`.
- **Fix:** drop the pointer and its auxiliaries with the absent object, or account their path subjects. Tighten the test.
- **Class:** 0. **Owner:** 10i.

### Low

- **RC-3. PR-1's class-2 manifest change is recorded only in commit ebdda8e7** (PLAUSIBLE ×2).
  - The change: `snapshot.context[].verification` goes from null to `{kind: download|blob, verified, unverified: 0}` for
    dtap/agentops `tasks` via `--fetch` and the qwencode/openhands `supp` archive.
  - It is not recorded in:
    - regen-batch (the item 98-100 row still predicts only `pin`/`input`);
    - a D-221 addendum;
    - the H.2.3 kind vocabulary. The D-530 write-up did plan `{kind: "download"}`.
  - The requested qwencode/openhands `supp` and cache-route seal tests were not added (the checkers' probes stand in for
    them). The `redcode-exec-qwencode` profile comments and the `test_withhold` docstring still say the seal "waits for
    D-530".
  - Owners: deferrals, with 10i.
- **RC-4. Fix commits without a regen-batch row or DECISIONS record** (CONFIRMED). These move the aer engine digest
  (class 1) or change behaviour:
  - the 10i fixes PR-4, PR-5, PR-8 and #4 (58213f5d): no docs at all. PR-8 also changes the D-529 sample keys for pinned
    objects (`label\x00pinned`, pointers always pass), which D-529's text does not describe;
  - PR-7's resume-identity and reuse-key change, plus PR-9 and #3: in the regen-batch rider only, with no DECISIONS or
    N.1.8(3) line;
  - P-1/PR-3's extension of D-430's drift lines: no D-430 addendum.

  The consequence is that every writing recompute of a corpus/0.1 corpus is now refused, so route (a), re-import, is the
  only upgrade path. Owners: 10i, cli-robustness, deferrals.
- **RC-5. PR-8 applies its "an LFS pointer always passes the sample" rule to non-multi readers too.** A sampled DTap
  import whose pinned object is sampled out writes the pointer's auxiliary row, which a full import does not have, and
  departs from INT. Fix: restrict the rule to the multi branch, or tie the pointer to its object's key. Class 1.
  Owner: 10i.
- **RC-6. D-219's `not_captured` is also reached on the write-gate fallback** (`degenerate_unit` with value None), where
  the task id was read and mapped. Pass the mapped header's task, or record this in D-219 and item 151. Class 1.
  Owner: deferrals.
- **RC-7. PR-10's relabel compares decoded and re-encoded member rows**, so a non-canonical source row with the same
  fields is reported as a refactor. Fix: relabel the raw `fn_digest` token, or require a canonical round trip first.
  Class 0. Owner: bug pass review.
- **RC-8. The recompute summary:**
  - P-3's `refusal` and the error notice truncate the drift lines at 300 characters, so the new format and vocabulary
    lines are cut. The `DRIFT_REFUSAL` text still says "profile or catalogue".
  - P-4's documented guard ("`NEW.partial` of a failed recompute is not sealable", N.2.7) is not enforced: package seals
    it.

  Fix: enforce the guard or reword it as advice. Class 0. Owner: deferrals.
- **RC-9. Since PR-7, a `--skip-prov-conformance` recompute from a fully validated source reuses nothing** (PLAUSIBLE).
  It recomputes SEM and PROV too, because the all-or-nothing reuse key no longer matches. Document or split it.
  Owner: cli-robustness.
- **RC-10. Docs:**
  - item 59's prediction omits the agentdojo SEM digest (`raw/members.py` is in its closure);
  - regen-batch row 20 and the item 20 body still say the capture edits are routed and awaiting approval;
  - #24's combined-tree digest table is not done;
  - #16's datasheet "Per-unit inputs" table and context related identifiers are not in the H.9 or release metadata spec;
  - the item-22 figures cite a "bug pass review classification" whose S1-S18/N1-N14 case table is in no committed file.

  Owners: regen plan, deferrals, bug pass.
- **RC-11. PR-14 moved names, not only numbers, into figures**, so the released sentences read "kexin-xu-01 [source
  note] … 68 [source note]" and "local Qwen3.5 [source note] logs". Reword to avoid the digits, or exempt declared
  identifiers. Owner: regen plan (regen-items' round duties).
- **RC-12. Pre-check tools at a19be82e** (owner pre-check):
  - `l2_check.pin_origins` replays the seal's origin step without PR-2's exclusion, so any corpus with pinned objects
    gets a false seal failure. Fix: move the exclusion into a shared package helper.
  - `l2_check` reads the root digest from stdout, but `package` prints it to stderr, so `--seal` never runs
    `verify --release`.
  - `l2_import`'s DTap `ContextTree("tasks")` has no `pin=`.
  - `l2_import` prune passes unsampled LFS pinned objects.
- **RC-13. Pre-existing, found while checking PR-5/PR-10** (identical at INT; owner bug pass / twins):
  - purging a DTap trajectory makes its supporting file a new execution in the re-map (unexplained);
  - `_compare_corpus_files` compares line sets, so reordered or duplicated rows are not reported;
  - derive's present-layer check ignores `--skip-prov-conformance`;
  - `recompute --out` after a context archive is purged records neither the context role nor `context_skipped`
    (PLAUSIBLE).

## Scratch

**Cleaned up 2026-10-22, on the orchestrator's instruction.**
- **Kept (evidence for this report and report.md), 11 MB:** `~/.agentprov/review/pre-round/{proofs,proofs-redact,proofs-recheck}/`,
  `workflow-result.json` and `recheck-result.json`.
- **Removed with `git worktree remove`** (all three clean): the review worktrees `base/`, `int/` and `fix/`.
- **Moved, not deleted, to `~/.Trash/agentprov-cleanup-2026-10-22/pre-round-review/`, 9.4 GB:**
  - `precheck-pre-round-review/`: every scratch corpus, including the sealed scratch copies under `redact/` and `fix/`;
  - `probes/` and `probes-recheck/`;
  - the session scratchpad.

  The probe and corpus paths cited above now live there.

The table below shows the layout before the cleanup.

| Path | Size | What |
|---|---|---|
| `~/.agentprov/migration-work/precheck/pre-round-review/redact/` | 5.7 GB | redaction proof scratch corpora, sealed copies, seeded caches, the stopped dtap prune run |
| `~/.agentprov/migration-work/precheck/pre-round-review/fix/` | 1.4 GB | re-check scratch corpora and sealed copies |
| `~/.agentprov/migration-work/precheck/pre-round-review/{base,int,int-j1,probe-fmt,cross-out}/` | 0.8 GB | re-map proof corpora |
| `~/.agentprov/review/pre-round/{base,int,fix}/` | 0.65 GB | three detached worktrees (238b34a8, cdd26e34, a19be82e) |
| `~/.agentprov/review/pre-round/probes{,-recheck}/` | 1.6 GB | probe scripts and outputs |
| `~/.agentprov/review/pre-round/proofs{,-redact,-recheck}/`, `*-result.json` | 11 MB | proof scripts, logs and comparisons; the workflow results |

## Condition re-check on 39eeed41 (2026-10-22)

**Head:** 39eeed41, new since a19be82e:
- 27278bd5: cli-robustness RC-4 records;
- 8994c0ee: 10i RC-5, RC-2, RC-4;
- 39eeed41: deferrals RC-1, RC-3, D-430 addendum, RC-6, RC-8, RC-10.

**Method:**
- Workflow `wf_24a1419a-41a`, 33 agents: three checkers re-ran the earlier probes at 39eeed41 and at a19be82e, and every incomplete fix or new finding got two adversarial verifiers. Result: `~/.agentprov/review/pre-round/condition-result.json`; probes in `probes-cond/`.
- One slim proof through the queue: `proofs-cond/`.

### Verdict

**The three conditions are met. Ready for the round.** The remaining items are low and can follow the round. Fix item
155's digest history (below) before the post-check uses it.

### Proof

- **Re-map:** the same 14 samples at 39eeed41, compared with the a19be82e and cdd26e34 corpora.
  - Every AER, SEM, PROV, raw, members, origins, index, register and validation file is byte-identical, and so is the
    id-normalised PROV.
  - Against a19be82e, only two digests move, as predicted:
    - the aer `engine_code_sha256` (`importer.py`, RC-5): agentdojo family `611a4ccb…`→`25e4f6a0…`, adprov
      `d4aeedcf…`→`a5ccb145…`, inspect `1ba23e7a…`→`f3f8048e…`;
    - the agentdojo-family `adapter_code_sha256` (`capture_mapper.py`, RC-1): `6eba419c…`→`ff3ffe3c…`;
    - with the `fn_digest` that follows from them.
- **recompute and verify:** `recompute --dry-run` reports 0 differences on all 14; `verify --level chain` is ok.

### Status of the conditions

| Item | Status at 39eeed41 |
|---|---|
| RC-1 tool_result withholding | **fixed**: a redacted tool output seals a 20-record AER with `capture_redaction`, as at INT; the other D-211 cases still withhold; 12 capture fixtures unchanged; 446 tests pass |
| RC-2 purged pinned LFS object | **fixed**: recompute and rederive exit 0 with 0 unexplained; residuals RC-14, RC-16 |
| RC-3 PR-1 recording | **fixed** (D-221 addendum, items 98-100, H.2.3); residuals RC-15, RC-19 |
| RC-4 fix records | **fixed** for cli-robustness (items 152-154, D-529/D-525 addenda, N.1.8(3)) and 10i (D-530 addendum, item 155); residual RC-17 |
| RC-5 sample pointer rule | **fixed** on all readers; MCPHunt (PR-8) still correct |
| RC-6 D-219 write-gate fallback | **fixed** by record (D-219 addendum, item 151) |
| RC-8 drift lines / P-4 | **fixed**: `summary.refusal` holds one line per drift; P-4 is advice; residual RC-18 |
| D-430 addendum | **fixed**: its lines match `version_drift` |
| RC-10 docs | item 20 and H.9/H.10.5 **fixed**; item 59, #24 and the item-22 case table still open (regen plan, bug pass) |

### New low findings (all CONFIRMED by both verifiers)

- **RC-14 (10i, class 0):** RC-2's exemption is wide. `_labels_of_executions` accounts the label of every raw object an
  absent-dependent execution references, including inputs that verified executions share (a task's `config.yaml`). So
  `_compare_corpus_files` drops every `origins`, `members` and `register` line holding such a label, and a real change
  on a shared input would be hidden in a corpus with a purge or a withheld object. One verifier rated it medium. Fix:
  account only labels referenced exclusively by absent-dependent executions.
- **RC-16 (10i, class 0):** the same mask is built with `json.dumps` (ASCII-escaped), while JCS rows hold raw UTF-8. A
  non-ASCII label is therefore never accounted, and that case still exits 1.
- **RC-17 (10i, docs):** item 155's digest history quotes `code_sha256(['adapters/runner', 'aer'])` (the seeds). Since the
  D-451 addendum, corpora record `code_sha256(aer_scope(family))`, which differs per family. Give the per-family values
  before the post-check compares `derivation.json`.
- **RC-15 (deferrals, docs):** H.2.3, the D-221 addendum and items 98-100 list a context verification kind `listing`
  that the code never writes for a context tree (only download or blob). The corpus-0.2 schema accepts any non-empty
  kind string; optionally constrain it before any corpus/0.2 seal.
- **RC-18 (deferrals, class 0):**
  - `summary.refusal` keeps at most 15 drift lines without saying any were dropped, and the format and vocabulary lines
    come last.
  - The stderr error line now shows `<U+000A>` escapes, and the error notice is still cut at 300 characters.
- **RC-19 (deferrals, docs):**
  - The RC-1 test docstring and code comment say `capture_redaction` names the tool message; it reports `exec`.
  - Spec D.10.4a item 23 does not state the `tool_result` exception.
  - The `redcode-exec-qwencode` profile comment still says the import waits for D-530. Editing it moves the profile
    digest, so either record why it stays or fix it in the round.

### Scratch of the condition re-check

Cleaned up 2026-10-22 on the orchestrator's instruction:
- **Removed:** the `cond/` (39eeed41) and `fix/` (a19be82e) worktrees, both clean, with `git worktree remove`.
- **Moved** to `~/.Trash/agentprov-cleanup-2026-10-22/pre-round-review/`: `precheck-pre-round-review-cond/` and
  `probes-cond/`.
- **Kept:** `~/.agentprov/review/pre-round/proofs-cond/`, `condition-result.json` and all earlier evidence (13 MB in
  total).
