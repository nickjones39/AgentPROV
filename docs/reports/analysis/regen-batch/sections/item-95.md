## Item 95 (R-10j-2, routed from phase 10j; user decisions 2026-10-14; held branch `regen-held-2`): the agentdyn `history` part, first slice

The 621 `drift.k18.messages` logs of `runs/gpt-4o-mini-2024-07-18-drift/` at AgentDyn `785b9127`, which AgentDyn's own head
replaced at `4d2748c6` (corrected from `6623a721`, bug pass NF-32). Phase 10j found 620 of them byte-identical in EnvironmentOptim; the user ruled them AgentDyn's. Spec:
D.6.14 item 11. User decisions:
- the part is AgentDyn's, named `history`;
- the GitHub route: one fetch at the pin, approved directly in this session's window;
- import all 621.

**Change.**
- Profile `agentdyn` version 3, with version 2 archived (`418fbcbd38a9…`, byte-identical to main's version 2): part
  `history` with its own pin (commit, tree, `tree_sha1`, `expected_files` 621) and `[identity] part_tables`.
- A one-row identity table `tables/agentdyn_history_pipeline_dirs.toml`.
- Family code: `FamilyTable.part_rows`/`rows_for`, used by both mappers' `resolve`, and the `part_tables` schema.
- Runner: `own_pin_part`. A part with its own pin that `variant_labels` never names selects every file of its pin.
- Registry `agentdyn · history`: [8]'s text, with the reader, mapper, semantics and corpus of part `c`. Still `planned`.
- README listing note.

**Predicted.**
- Stored corpora: no AER, SEM or PROV byte moves.
  - The stored AgentDyn corpus (`agentdyn-a-p10`) records profile version 1 and maps only head files, which still resolve
    against the unchanged head table: `rows_for` returns it for every commit but `785b9127`.
  - Parts `a`, `b` and `c` share the head pin and are named in `variant_labels`, so their selection is unchanged.
- At the round's re-import, AgentDyn AERs declare profile version 3 (`profile.version`/`sha256`), as any D-31 bump does.
- Moved digests:
  - the `agentdojo` family `adapter_code_sha256` and the SEM `engine_code_sha256`, from `profile.py`, both mappers and
    `family.schema.json`;
  - the runner code, a `map` stage input for every source.
- No catalogue changes, so no rule version moves.
- The new slice, once fetched and imported in the round: 621 AERs.
  - The 620 phase 10l mapped are expected to map cleanly, now with the history row, so without the
    `agentdojo.pipeline_name_mismatch` that 10l's stand-in raised on all 620.
  - The 621st's outcome is to be reported.

**Measured so far.**
- `tests/adapters/agentdojo/test_r10j2.py` (5 tests): the history-identity test fails without `part_tables`.
- `tests/unit/test_d31_bumps.py`: agentdyn is current at version 3, and version 2 is archived.
- `spec_labels --check`: 0 problems. `reserve_id scan`: 0 unreserved labels.

**Done (2026-10-15).**
- **Twins review:** the D-31 owner approved the bump. Requested fix: `corpora/agentdyn-a/corpus-spec.toml` names
  `agentdyn@3` (done).
- **Fetch** (user-approved, import lane, logged in `cache/acquisitions.jsonl`, consent `--allow-network`):
  - commit `785b9127` at depth 1: 621 blobs under the tree, 9,138,599 bytes, each verified by git blob id. The size gate
    did not fire; objects shared with the cached `5353cf76` were not re-sent.
  - blobless history: 3.7 MB, 49,192 blobs indexed, 7 introducing commits.
- **Trial import:**
  - `import_source` in release mode from the fetch cache into a scratch corpus
    (`~/.agentprov/migration-work/regen-items-2-12/r10j2/agentdyn-history`). The CLI refuses a `planned` part, so the
    registry part stays `planned` until the round's recorded import.
  - 621 seen, 621 mapped, 0 degenerate, 0 failed. 621 annotated, derived and validated.
  - 620 `drift.k18.messages` logs resolve against the history row with no `pipeline_name_mismatch`, which 10l's
    stand-in had raised on all 620. Their seal issues are `accounting_unverifiable`, `drift.agent_prompt_not_recorded`,
    `drift.injection_map_not_recorded` (560) and `drift.calls_in_text_not_executed` (242).
- **The 621st file** (`shopping/injection_task_0/none/…`, AgentDyn only): an incomplete TraceLogger log
  (`v1.k14.incomplete`), introduced in `785b9127` itself.
  - It maps cleanly through the TraceLogger build with the history row's identity (model `gpt-4o-mini-2024-07-18`,
    defence `drift`).
  - Issues: `incomplete_run`, `earlier_attempts_unobservable`, and `agentdojo.pipeline_name_mismatch`. Its logged
    pipeline name differs from the DRIFT logs', and the mismatch is reported, not hidden.
- **The scratch corpus is `agentdyn-history.partial` by design.** `import_source` writes a working corpus as `DIR.partial`.
  A trial runs to `until = "validation"` and never runs `package`, which seals and renames. This matches phase 10f's
  trial corpora (`whistlebench-*.partial`). It is not an interrupted import: exit 0, 621 of 621 validated.
- **Count: 620 vs 621.**
  - R-10j-2 and D-254 count EnvironmentOptim's 620 copies.
  - AgentDyn's tree at `785b9127` holds 621 files in that directory: the 620 DRIFT runs, plus the incomplete
    TraceLogger log above, which only AgentDyn has (tree comparison by blob id, both trees offline).
  - So the part imports 621, and the 620 of R-10j-2 are exactly its DRIFT logs.
- **Ownership: each of the 621 files belongs to exactly one corpus, `agentdyn` part `history`.**
  - EnvironmentOptim's profile (main, phase 10j) excludes `runs/gpt-4o-mini-2024-07-18*/**` as `select.owned_elsewhere`,
    owner `agentdyn`, so its 620 copies are not imported there. The 621st is not in its tree.
  - None of the 621 blob ids occurs anywhere in AgentDyn's head tree `5353cf76` (47,723 `runs/` blobs, `src/` DRIFT
    copies included: 0 shared), so parts a, b, c and d do not hold them.
- **Bug pass new-families (NF-30, NF-31, NF-32; routed R-NF-6), on this branch:**
  - **NF-30 (robustness, fail closed).** `own_pin_part` let a part with its own pin select every file it was given, so
    `--snapshot history --pin head` would have mapped the head's 47,723 files as part `history`. The runner now selects an
    own-pin part's file only when its git origin commit is that part's pin (`own_pin_commits`; `select.dialect_planned`
    otherwise). Profiles without `variant_labels` are unchanged. Test: `test_an_own_pin_part_never_selects_another_commits_files`.
  - **NF-31 (docs).** The 621 logs are 620 `drift.k18.messages` and one `v1.k14.incomplete`. The registry row's
    `variants` now lists both; the profile, table header, registry caveat, README and D.6.14 item 11 say so.
  - **NF-32 (docs).** Rechecked offline in the blob-less 10j clone, using tree and blob ids only:
    - `6623a721` does not touch the directory. `4d2748c6` (2026-04-19) replaced it: 620 modified, 4 added, 1 deleted, 0
      blobs shared with `785b9127`.
    - The 620 DRIFT blobs are present at every commit from `2d4ad05a` to `785b9127`.
    - The 621st file was added at `68aba5bf` under another blob; its pinned blob first appears at `785b9127`.
  - **Bytes.** The profile text moves agentdyn v3's digest (unlanded, so this stays in its one bump) and the history
    table's pin (`a0726790…`). `tests/adapters/agentdojo/agentdyn_aer_digests.json` was regenerated (15 pins) and the
    README regenerated. No stored corpus records agentdyn v3. The scratch trial corpus
    `agentdyn-history.partial` records the earlier v3 bytes; it is a rehearsal and the round re-imports.

