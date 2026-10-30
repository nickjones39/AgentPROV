# Core review B: proposals for the user

These findings were reproduced (see `findings.md`; repro scripts in `~/.agentprov/migration-work/review-core-b/repro/`).
They are not plain class-0 bug fixes. Each one either changes stored bytes or a stage code digest (class 1), or adds new
behaviour. Numbers come from `tools/reserve_id.py`: decisions D-490..D-491 and regen-batch items 57..59.

**Status (2026-10-14). User decision, confirmed directly in this session: all approved.** D-490 is built on
`review-fix-core-b` (4225858e) and recorded in DECISIONS.md with D-491 (ef66266f). D-491 is built after D-450 lands on
main. Items 57 and 59 are built on the held branch `review-core-b-regen` for the regeneration round, which is not pushed
before the round. Item 58 is built after pipeline-perf's D-414 lands, because both change `importer.py`.

## Regen-batch item proposals (byte class 1)

| item | CB | file | change | what moves |
|---|---|---|---|---|
| 57 | CB-4 | `src/agentprov/corpus/manifest.py:753-756` | `counts.by_stage.expand`: `ok = len(containers)` with nothing subtracted (a failed container writes no `members.jsonl` row, so it is not counted twice). `failed` = the number of distinct `(snapshot_id, source_key or path)` pairs among the `stage == "expand"` error entries, so one path failing in two snapshots counts twice. Optional: record a successful zero-member container in the expand stage record, so it counts as ok | `corpus.json` bytes (and so the content digest and root digest) only for corpora with at least one `expand` register error. AER/SEM/PROV are unchanged, and no stage code digest moves (`corpus/` is in no scope). `verify` recomputes the counts with the same function (`verify.py:1117`), so an old sealed corpus with an expand failure reports a counts mismatch at main until it is regenerated. The round's census should list the corpora with `stage == "expand"` errors in `register.jsonl` |
| 58 | CB-20 | `src/agentprov/adapters/runner/importer.py:1026,1031,1041-1043`; `src/agentprov/corpus/writer.py:163-168` | `CorpusWriter.add_object(..., expected_sha256=, expected_size=)` passed through to `store.put_stream`/`put`. `archive_members` passes `tree.sha256`/`tree.size`, and `_split_members` passes `part.sha256`/`part.size` before storing, so a file swapped between verify and copy is refused (`raw.digest.mismatch`) before the object or its pinned origin is recorded. The post-hoc split compare is dropped. Optional: seal/validate asserts `snapshot.input.sha256 == snapshot.origin.sha256` for a non-split archive input | the aer stage `engine_code_sha256` (scope `adapters/runner` + `aer`) and so `fn_digest` for every corpus. Stored AER, SEM and PROV bytes are unchanged for honest inputs. **Order:** after `regen-items-2-12` and pipeline-perf's D-414 land (orchestrator) |
| 59 | CB-22 | `src/agentprov/raw/members.py:1055-1057` | in `expand_containers`, a nested reach (a `ContainerSpec` made by `_consume` from archive content) that finds the container already expanded with another selection appends `ExpandEvent(..., "raw.members.conflict", "expand", "error", "not_imported", ...)` and continues. A conflict between two caller-supplied root specs still raises (API misuse; `test_two_different_selections_for_one_container_conflict` keeps its meaning). New test: D-382 `nested_selection` with an `under` chain and duplicate inner bytes | the expand stage `engine_code_sha256` (`EXPAND_MODULES`) for every container corpus. `members.jsonl` and register bytes change only for an archive where the conflict occurs. No shipped profile declares `[import] nested` yet, so no stored rows move |

## Decision proposals

- **D-490 (proposal, security; CB-14). Deposit verify checks each datasheet copy against the sealed datasheet.** Today
  `release/verify.py` checks every `documents[]` file only against the deposit manifest, which is not anchored. So a
  forged `DATASHEET-<id>.md` passes `verify --release --root-digest`, and so does any extra document whose name matches
  the grammar. That datasheet is the human-facing licence, restrictions and untrusted-content statement (REP-3).
  Proposal:
  1. `documents[]` must be exactly `README.md`, `CHANGELOG.md`, `deposit-metadata.json` and one
     `DATASHEET-<corpus_id>.md` per `corpora[]` entry. Any other name fails (`deposit.manifest.invalid`).
  2. Inside each corpus's archive set, read `DATASHEET.md` through `ArchiveCorpusReader`. That copy is covered by the
     archived checksums and the root digest.
  3. Compare it with the deposit copy. Without mixed licence classes the copy must be byte-equal. With them it must
     start with `sealed.rstrip(LF) + LF` followed by the builder's note header. On a mismatch, report
     `deposit.document.datasheet`.
  4. D-38 item 5 and H.10.3 record that `README.md`, `CHANGELOG.md` and `deposit-metadata.json` stay covered only by
     the deposit manifest.

  Byte class 0. It changes what verify accepts, so it is a decision.
  Rejected alternative: leave documents manifest-only (D-38 item 5 as written). A reader who sees `--root-digest`
  succeed would then trust a datasheet the root digest never covered.
- **D-491 (proposal, security; CB-16). `tools/release_scan.py` scans unselected archive members for the home path and
  host name.** The R-51 detector (`path_scan`) reads stored bytes only, and gitleaks runs at `--max-archive-depth 0`. So
  a home path inside an unselected, compressed member of a stored container passes: Inspect `_journal/start.json`,
  `summaries.json`, the geminicli zstd tar, the credleak zip. Selected members are already scanned as their own objects.
  Proposal:
  1. Recognise archive objects by their magic bytes (zip, gzip or zstd tar, split archives).
  2. Stream their not-selected members through the same needle search. Reuse D-450's `corpus/withhold_scan`
     decoded-member scan in a bounded job, with no extraction to disk.
  3. Report each hit as `<label>#<member index>`, so the fingerprint stays stable and value-free.
  4. An archive that cannot be decoded within the limits becomes an untriaged `home-path-unscanned` finding (fail
     closed).
  5. Bump `PATH_SCAN_VERSION`.

  **Order:** build after D-450 lands on main (the bug pass). Byte class 0.
  Rejected alternative: raise gitleaks' archive depth. It has no home-path rule, and its archive support does not cover
  zstd tars.

## Notes for other owners

- **deferrals-c rebase.** The orchestrator assigned these class-0 fixes in files deferrals-c owns to this branch
  (deferrals-c is parked): CB-5 (`corpus/spec.py`), CB-9 and CB-10 (`corpus/package.py`), the CB-15 NC predicate at
  `corpus/package.py:346`, and the CB-18 `ReleaseArgs`/`manifest.py` date backstop. deferrals-c resolves the conflicts
  when it rebases. The commits are listed in `findings.md` once they land.
- **Twins (`claude/rules-drift`).** CB-6: derive/recompute refuse a purged working corpus, and NEW drops
  `raw/tombstones.jsonl`; this is a sibling of BF-20. CB-11: `chain`/`rederive` never recompute row status.
- **Bug pass.** CB-1: purge and seal-time citing follow `members.jsonl` one level only, and both modules must change
  together. CB-19 backstop: `build_deposit` refuses `release_date.year > 2107` with `release.usage`.
