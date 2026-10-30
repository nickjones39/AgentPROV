# Bug pass bugpass-perf-10: proposals for the user

These findings were reproduced (see `findings.md` and `repro/`) and are not plain bug fixes: each one either moves a
stored code digest (byte class 1) or is new behaviour. **User decision 2026-10-14 (confirmed directly in this
session): all approved.** D-450 is built on `bugpass-perf-10` (0abb32e7, with D-452 and the review fixes in 6fe45aad). D-453 (partial scan of zips
without a central directory) and D-454 option (i) (auto-withhold what stays unreadable, `agentprov-withheld/0.3`) are
approved follow-ups on a fresh branch after bf19-bf15 lands; D-454 (ii) (identity rules) was rejected. D-451 and regen items 33..41 are built on the
held branch `bugpass-regen` for the regeneration round and are not pushed before it. Numbers come from `tools/reserve_id.py`:
regen-batch items 33-41 and decisions D-450..D-459 (D-452..D-459 unused).

## Regen-batch item proposals (byte class 1)

Each item changes a file under an adapter or `aer/` code digest. That moves the `adapter_code_sha256` (or the aer
stage's `engine_code_sha256`) recorded by every stored corpus of that family. The SEM `engine_code_sha256` moves too,
because it hashes the family directories. Stored AER bytes change only where noted.

| item | BF | file | change | AER bytes |
|---|---|---|---|---|
| 33 | BF-5 | `src/agentprov/aer/rules.py:270` | `RuleCatalogue.rules = MappingProxyType(dict(sorted(...)))`, so the D-410 cache cannot be poisoned by a caller. Add a test that `.rules.pop`/item assignment raise `TypeError` and that a reload has the full count | none (same rules, same order) |
| 34 | BF-23 | `adapters/{openhands,credleak,agentops}/mapper.py` (and an audit of `dtap`) | one exported read-only `SENTINELS` constant from `agentprov.aer` (the validator's C.7.3 list), united with each family's extras (`undefined`, `nan`). Every typed tool name and model field the families write is checked against it. A hit gets `unk: ambiguous` and the verbatim value goes to `ext` | only for runs that today degenerate to `adapter_defect` (none in the pinned data) |
| 35 | BF-24 | `adapters/credleak/mapper.py:367-378` | give the agent actor a run locator on every path (`agent.loc({"a": "a0", "p": self.P})`); keep the `/model` locators in the model branch | only for runs whose model is missing, sentinel or non-string |
| 36 | BF-25 | `adapters/agentops/mapper.py:629-631` | pass the step's assistant message id to `_result`; an unpaired fault decision's subject is that message, not `self.messages[-1]` | none in the pinned snapshot (names pair 14,328/14,328) |
| 37 | BF-26 | `adapters/agentops/mapper.py:463` | emit actor `att` whenever a result carries an `injected_payload` with no failure, not only in adversarial runs; cite the payload rule and raise an info issue `agentops.payload_outside_adversarial` (a new catalogue code, so the `agentops` catalogue version is bumped) | none in the pinned snapshot |
| 38 | BF-27 (**security**) | `adapters/mcphunt/mapper.py:639,~704` | compute the canary flag from the raw events after the turn loop, not only from paired events. Raise `mcphunt.canary_flagged` whenever any event has `canary_in_args`/`canary_in_result` true; the ids are the paired te ids, plus a fallback when some flagged event is unpaired | none in the pinned data (every flagged event pairs); it closes the D-289 withhold trigger for traces that do not pair |
| 39 | BF-29 | `adapters/mcphunt/mapper.py:448,641` | a class-D link by call id only when the id is unique among the trace's calls and its tool messages. Otherwise raise `call_result_link_conflict` (`call_id_not_unique`) and emit each source message exactly once | none (ids unique in the data, 129,175/129,175) |
| 40 | BF-30 | `adapters/mcphunt/mapper.py:457-491` | track consumed message indexes. Emit every unconsumed message in source order with an issue: `orphan_tool_result` for role tool, and a new catalogued code (e.g. `mcphunt.unplaced_message`; catalogue bump, D.21.3 table) for other roles | only for traces with such messages (not known in the data) |
| 41 | BF-31 | `adapters/mcphunt/mapper.py:766` | sum only integer counters (the `_model_call` guard). A present non-integer counter makes `mcphunt.acc.counters@1` `unverifiable` (`counters_not_integers`) instead of crashing | only for traces with non-integer counters |

Findings routed to owners that are also class 1 (BF-21, BF-22, BF-28 on `regen-items-2-12`) are not given items here.
The owner decides whether they ride with its regen items.

## Decision proposals

- **D-450 (proposal, security; BF-18). Not-selected archive members are scanned in decoded form at sealing.**
  Today the `[withhold]` byte rules scan each stored object's bytes as stored. The AD-12 closure follows only `selected`
  member rows. So a canary inside a deflated, not-selected member is never seen: not by the planner, not by the
  `chain`/deposit-builder rescan, and not by `tools/release_scan.py` (gitleaks runs with `--max-archive-depth 0`). The
  container is released.
  Proposal: when a policy has byte rules, `corpus/withhold.py` streams every not-selected (and not-expanded nested)
  member of each stored container through `scan_chunks`. This runs in a bounded T1 job with the existing extraction-free
  member gates and stores nothing. A hit withholds the container (basis `container`) and its D-315 group. A container
  that cannot be decoded (deferred codec, depth beyond `max_archive_depth`) refuses the seal
  (`corpus.withhold.unscanned`) unless it is withheld. `chain` and the builder's rescan mirror the decoded scan.
  `release_scan.py` either drops the depth-0 default or documents why it stays.
  Byte class 0 (no stage digest covers `corpus/`). It changes what a seal withholds, so it is a decision, not a bug fix.
  Rejected alternative: rely on the release-time gitleaks scan. It does not open archives today, and D-289 says many
  canaries have no recognisable shape.
  Shipped profiles that make this reachable: geminicli D.23.7 (not-selected claude_code files hold a key-shaped value)
  and credleak D-265 (not-selected collector logs in a zip).
- **D-451 (proposal; BF-33). Stage code digests cover the import closure of each stage.** The sem/prov/validation
  `engine_code_sha256` scopes are fixed directory lists (`corpus/derive.py:228-270`, `adapters/runner/importer.py:1937-1958`,
  pinned equal). The code those stages run imports modules outside them: `adapters/agentdojo/citation.py`,
  `history_table.py`, `adapters/code_verification.py`, `adapters/dtap/matcher.py`, `aer/evidence.py`, `aer/reader.py`
  and `aer/rules.py`. So `recompute --out` (reuse on by default) carries stale SEM/PROV after a behaviour edit there,
  and reports them identical.
  Proposal: pin each stage's file list as its transitive import closure, a constant shared by both files, with a test
  that recomputes the closure (ast) and fails when it grows. This is class 1: every recorded stage digest moves, so it
  lands with the regeneration round.
  Stop-gap with no digest change (class 0, in `corpus/derive.py`, so it is routed to that file's owner):
  `_reuse_corpus_key` also requires that the aer stage's `adapter_code_sha256` and `engine_code_sha256`, recomputed for
  this build, equal the source's recorded values.
