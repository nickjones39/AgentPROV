# Core review B: findings

Branch `review-fix-core-b`, reviewed at origin/main `7f8f8cb3` (2026-10-14). Scope: `corpus/` (B1a, B1b), `release/` (B2), `raw/` (B3), `migration/` (B4), `stats/` and `render/` (B5).

Method: six read-only reviewers, one per area. Each claim then went to an adversarial verifier that tried to disprove it and kept it only if a script it wrote and ran reproduced it. The repro scripts and the full reviewer and verifier records (`review-wave.json`) are in `~/.agentprov/migration-work/review-core-b/repro/`; each finding's verifier script is under `verify-<area>-<n>/`. The scripts are outside the repository on purpose.

Severity is the verifier's corrected value. Class 0 means the fix changes no stored bytes or stage digests; class 1 means it does (regen batch).

## Summary

| id | area | severity | class | where | finding | disposition |
|---|---|---|---|---|---|---|
| CB-1 | B1a-1 | correctness | 0 | `src/agentprov/corpus/purge.py:267` | purge of an outer container misses executions and stored objects that come from a nested archive inside it | ROUTED to the bug pass (purge.py and withhold._Planner.citing must change together) |
| CB-2 | B1a-2 | robustness | 0 | `src/agentprov/corpus/index.py:439` | Index and register decoders raise TypeError on type-confused fields, so `verify` ends with exit 70 instead of reporting index.invalid | FIXED 75cfbca0 |
| CB-3 | B1a-3 | robustness | 0 | `src/agentprov/corpus/writer.py:396` | CorpusWriter.flush commits executions.jsonl before validation/results.jsonl, so a failed flush permanently loses validation rows on resume | FIXED cc96c18a |
| CB-4 | B1a-4 | correctness | 1 | `src/agentprov/corpus/manifest.py:754` | by_stage.expand.ok subtracts failed containers that were never counted, so a failed container lowers the count of successful expansions | CLASS 1: regen-batch item 57 (approved; held branch review-core-b-regen) |
| CB-5 | B1a-5 | correctness | 0 | `src/agentprov/corpus/spec.py:318` | corpus-spec licence.files accepts names that differ only in case; on macOS the generated LICENSES/<src>/NOTICE.md and LICENSE are silently overwritten | FIXED 5dcadd7c (deferrals-c rebases over it) |
| CB-6 | B1b-1 | correctness | 0 | `src/agentprov/corpus/derive.py:652` | derive/recompute refuse every working corpus after `purge` (raw.object.missing), and NEW never carries raw/tombstones.jsonl or raw/REFERENCES.json | ROUTED to the twins (derive.py; sibling of BF-20) |
| CB-7 | B1b-2 | not reproduced | 0 | `src/agentprov/corpus/package.py:685` | seal records the sealing checkout's commit as producer.git_commit without checking that the working corpus was built by that code | NOT REPRODUCED (behaviour as H.8.4(2) specifies) |
| CB-8 | B1b-3 | not reproduced | 0 | `src/agentprov/corpus/verify.py:932` | An edited views/ file in a sealed corpus passes `verify --level chain` once checksums.sha256 is regenerated (views are not digest-chained) | NOT REPRODUCED (D-63/H.5.5 boundary); optional SEC-15 pin test noted |
| CB-9 | B1b-4 | robustness | 0 | `src/agentprov/corpus/package.py:811` | A seal killed after corpus.json says sealed:true and before the swap leaves DIR.partial that can neither be resealed nor written | FIXED edd105fa (forward recovery; deferrals-c rebases over it) |
| CB-10 | B1b-5 | correctness | 0 | `src/agentprov/corpus/package.py:1063` | _check_gating accepts a failed gating check of an unregistered execution if any other failed row is registered | FIXED fef231db (deferrals-c rebases over it) |
| CB-11 | B1b-6 | security | 0 | `src/agentprov/corpus/verify.py:714` | chain never recomputes a row's status (H.3.2(1)) or checks register entries against the row's issues; a whitewashed row passes a consistent forgery | ROUTED to the twins (verify.py) |
| CB-12 | B1b-7 | robustness | 0 | `src/agentprov/corpus/integrity.py:270` | A checksums.sha256 that is a symlink (or otherwise refused by open_evidence) makes verify raise IngestError instead of reporting a finding | FIXED 051ad3dc |
| CB-13 | B2-1 | security | 0 | `src/agentprov/release/verify.py:231` | Release-mode deposit verify never opens an archive that no corpus entry names (orphan archive), and passes a deposit whose corpora list is empty | FIXED a0f1d747 |
| CB-14 | B2-2 | security | 0 | `src/agentprov/release/verify.py:186` | DATASHEET-<id>.md in a deposit is never compared with the sealed DATASHEET.md, so a forged datasheet copy (and any extra listed document) passes verify even with --root-digest | D-490 (approved) BUILT 4225858e |
| CB-15 | B2-3 | correctness | 0 | `src/agentprov/release/metadata.py:97` | D-42 relicensing and non-commercial refusals miss valid SPDX ids: GPL-2.0+, LGPL-2.1+, GPL-2.0-with-classpath-exception, 'GPL-3.0-only WITH ...', PolyForm-Noncommercial-1.0.0 | FIXED 6059fccf (release/metadata.py) + 990e2181 (package.py NC predicate; deferrals-c rebases over it) |
| CB-16 | B2-4 | security | 0 | `tools/release_scan.py:289` | The home-path / host-name scan of tools/release_scan.py never reads inside compressed raw objects, so the user's home path in a deflated .eval/zip member passes the release scan | D-491 (approved); build after D-450 lands |
| CB-17 | B2-5 | security | 0 | `tools/release_scan.py:328` | Release-scan triage is not bound to a root digest: a triage TOML reused for a later corpus version silently triages a new secret at the same path:rule:line | FIXED fb74527f |
| CB-18 | B2-6 | correctness | 0 | `src/agentprov/corpus/package.py:140` | Seal mode accepts an impossible --release-date (2026-02-30, 2026-13-45, 0000-00-00) and writes it as release.created of a sealed corpus; the manifest validator is regex-only | FIXED e5011f19 (CLI) + be46b138 (ReleaseArgs/manifest backstop, ASCII epoch) |
| CB-19 | B2-7 | robustness | 0 | `src/agentprov/release/builder.py:226` | package --deposit with a release date after 2107 passes every check (and --dry-run), then crashes with struct.error while writing the first archive (exit 70) | FIXED 264e8a07 (CLI); builder backstop ROUTED to the bug pass (release/builder.py) |
| CB-20 | B3-1 | security | 1 | `src/agentprov/adapters/runner/importer.py:1026` | Archive input: the stored container is never checked against the verified pin digest (TOCTOU between verify and copy); the pinned zenodo/hf origin is recorded for bytes the pin does not vouch for | CLASS 1: regen-batch item 58 (approved; after D-414 lands) |
| CB-21 | B3-2 | robustness | 0 | `src/agentprov/raw/fetch.py:1430` | U-07 large-download consent is bypassed when a download pin has no pinned size and the server sends no Content-Length | FIXED 97274bee |
| CB-22 | B3-3 | robustness | 1 | `src/agentprov/raw/members.py:1057` | One hostile archive aborts the whole expand call: identical inner-archive bytes reached at two levels with different selections raise MembersConflictError out of expand_containers | CLASS 1: regen-batch item 59 (approved; held branch review-core-b-regen) |
| CB-23 | B3-4 | robustness | 0 | `src/agentprov/raw/history.py:80` | History index: a far-future committer date crashes fetch --history with an untyped ValueError | FIXED e9551d4f |
| CB-24 | B3-5 | correctness | 0 | `src/agentprov/raw/references.py:143` | REFERENCES.json git origins never resolve against a pin whose tree is a directory without a trailing slash | FIXED 9ccba6f6 |
| CB-25 | B3-6 | security | 0 | `src/agentprov/raw/fetch.py:1056` | git fetch follows HTTP redirects to any host and downgrades https to http (no protocol/redirect restriction in _hardening) | FIXED 34a9419e |
| CB-26 | B4-1 | correctness | 0 | `src/agentprov/cli/migrate.py:209` | gate-d writes its report, markdown and executions JSONL into a corpus when the target comes from --reports-dir (the inside-corpus refusal only covers --report) | FIXED 805d6868 |
| CB-27 | B4-2 | correctness | 0 | `src/agentprov/migration/gates.py:222` | Gate report file name ignores scope: a later sample/golden run on the same day and commit overwrites the full-scope report and breaks the AD-07 chain | FIXED e5b878c0 |
| CB-28 | B4-3 | correctness | 0 | `src/agentprov/migration/reconcile.py:139` | R3 projection drops the skip-listed member names at every depth, so differences in tool-call arguments named id/k/rule/hash/ns/src/... are never compared | FIXED 123f82c1 (after regen-items-2-12 landed) |
| CB-29 | B4-4 | not reproduced | 0 | `src/agentprov/migration/gates.py:424` | G0 in dev mode passes when the recorded baseline wheel or requirements file is missing (recorded-but-missing becomes 'skipped') | NOT REPRODUCED (J.1.6 resolution 1: dev-mode skip is specified) |
| CB-30 | B4-5 | robustness | 0 | `src/agentprov/migration/gate_d.py:428` | Full-scope gate D passes (role release) with every J.3.5 tree accepted as a gap, validating zero migration executions, and unlocks gate E; accepted gaps are PASS even under --release | FIXED ba3f03ff |
| CB-31 | B4-6 | test-gap | 0 | `src/agentprov/migration/c6.py:390` | C6 comparer passes on an incomplete or empty scenario set; it never checks the scenarios against the producer's manifest | FIXED 4fc4ca6d |
| CB-32 | B5-1 | security | 0 | `src/agentprov/stats/output.py:82` | stats text/CSV output prints the manifest's corpus_id and content_digest raw: a hostile corpus forges table lines and writes terminal escapes to stdout | FIXED f21a977b |
| CB-33 | B5-2 | correctness | 0 | `src/agentprov/stats/tables.py:196` | Artefacts table groups rows by the truncated, comma-joined display label, so distinct models are pooled into one row | FIXED e681e866 |
| CB-34 | B5-3 | robustness | 0 | `src/agentprov/render/output.py:24` | render with --corpus '.' (or '/') crashes with an internal error; '--corpus C/x/..' is wrongly refused because the default output dir is computed from the unresolved path | FIXED d13184c8 |
| CB-35 | B5-4 | correctness | 0 | `src/agentprov/stats/datasheet.py:46` | datasheet_field_groups drops stats read/evaluation failures silently: published coverage table has n_executions counting executions that contributed no cells | FIXED 5cc022d0 |

## B1a

### CB-1 (B1a-1): purge of an outer container misses executions and stored objects that come from a nested archive inside it

- **Reproduced:** yes
- **Severity:** correctness (claimed security); **class:** 0
- **Where:** src/agentprov/corpus/purge.py:263-272 (_containers_of; used at 300-301) and src/agentprov/corpus/withhold.py:482-487 (_Planner.citing)
- **Disposition:** ROUTED to the bug pass (purge.py and withhold._Planner.citing must change together)
- **Repro:** `~/.agentprov/migration-work/review-core-b/repro/verify-B1a-1/`

**Failing input.** A working corpus where outer.zip (C_o) holds inner.zip (C_i), which holds log.json (L). The index row's primary raw is L. raw/members.jsonl has the rows (container=C_o -> C_i) and (container=C_i -> L). Run `agentprov purge sha256:<C_o> --reason secret --corpus DIR`.

**Expected.** The execution mapped from outer!/inner.zip!/log.json is listed as affected and gets the `release.withheld` register entry. member_objects lists every stored object expanded from C_o, both C_i and L. This matches the docstring: an execution cites the object when its raw array names it 'or names an object that was expanded from it'.

**Actual.** plan_corpus returns affected=() and new_register_entries=0. member_objects lists only C_i. `_containers_of` follows one level of raw/members.jsonl, so L (a byte copy of the leaked file) is neither reported nor withheld. For a one-level container the same execution is affected, so nested and flat archives behave differently.

**Verifier.** The core claim holds at origin/main 7f8f8cb3. purge._containers_of (src/agentprov/corpus/purge.py:263-272) follows raw/members.jsonl one level only, and plan_corpus (lines 300-301) uses that result for `cited` and `member_objects`. The two-level layout is what real imports produce. In expand_containers (src/agentprov/raw/members.py:1214-1227) a nested archive is re-queued as a ContainerSpec with sha256=put.sha256, so its members' rows carry container=<inner digest>, not the outer one. The input is therefore reachable through `agentprov import` with a profile that declares nested archives, followed by `agentprov purge`.

Three parts of the claim need correcting.
(1) The seal-time planner has the same one-level rule. withhold._Planner.citing (src/agentprov/corpus/withhold.py:482-487) gives the identical result, so at seal the nested execution is also released. The two modules agree with each other but not with the flat case. The proposed fix to purge.py alone is wrong: the seal then refuses with corpus.withhold.unexplained (reproduced), because the register lists an execution that no seal-time cause explains. The closure has to go into both purge._containers_of and withhold._Planner.citing, and into the spec text (HL H.4.5 item 3, "a member of it") at the same time.
(2) Severity is overstated. By design, purging a container never removes or withholds its members: the module docstring says they stay stored and are listed, and seal-time container closure only goes upward. So the leaked file L's raw bytes stay stored, and are released at seal, in the flat case too. What nesting really changes is that (a) L is not in the printed member list (only C_i is; purging C_i would then list L), and (b) the execution's derived AER/SEM/PROV is not withheld, while in the flat case it is. That is a correctness/consistency defect with a security-relevant side, not a primary leak path.
(3) Not covered by BF-19 (that is the upward closure in verify) or F-12C-05 (re-storing purged bytes). The existing tests (tests/cli/test_purge_cmd.py::test_a_container_purge_lists_the_members_that_stay) use only a one-level container.

**Evidence.** Script: scratchpad/review/verify-B1a-1/repro.py. It builds two working corpora with CorpusWriter. In "flat", outer holds log.json. In "nested", outer holds inner.zip, which holds log.json. Each has one execution whose primary raw is the log. It runs plan_corpus and apply on the outer digest. Output:
[flat] purge outer: affected=('ex_cccccccccccccccccccccccccc',) new_register_entries=1
[flat]   member_objects=['80d06d7c'] inner=None log=80d06d7c
[flat]   after apply: removed=True withheld_register=[{'ex': 'ex_cccccccccccccccccccccccccc'}] log_still_stored=True
[nested] purge outer: affected=() new_register_entries=0
[nested]   member_objects=['834fa567'] inner=834fa567 log=6ac5d83e
[nested]   after apply: removed=True withheld_register=[] log_still_stored=True
Script: scratchpad/review/verify-B1a-1/repro_seal.py. It runs withhold.plan_withholding on the purged corpora:
[flat] seal plan: withheld executions=['ex_cccccccccccccccccccccccccc']
[nested] seal plan: withheld executions=[]
[nested] purge-only fix: seal refused corpus.withhold.unexplained
The last line shows that the claimed purge-only fix breaks sealing: a register release.withheld for the nested execution is refused by _refuse_unexplained.
The nested rows come from real imports: in src/agentprov/raw/members.py:1214-1227 a nested child is a ContainerSpec with sha256=put.sha256, so its rows carry container=inner.

**Fix.** Define one shared "expanded from" closure: from {digest}, repeatedly add the sha256 of every selected members.jsonl row whose container is already in the set, until nothing is added. Use it in purge.plan_corpus for `cited` and `member_objects`, and in withhold._Planner.citing for the seal-time affected set, so the register written by purge and the seal-time set stay equal. Otherwise _refuse_unexplained refuses the seal. container_objects can stay one level or be closed upward the same way. Update the purge module docstring and HL H.4.5 item 3 / G.9.6 ("or, for a container, an object expanded from it at any depth"). Add regression tests: two-level nesting through purge (affected and member_objects), and the same corpus through plan_withholding/seal, checking that the nested execution is withheld and the seal succeeds.

### CB-2 (B1a-2): Index and register decoders raise TypeError on type-confused fields, so `verify` ends with exit 70 instead of reporting index.invalid

- **Reproduced:** yes
- **Severity:** robustness (claimed robustness); **class:** 0
- **Where:** src/agentprov/corpus/index.py:439 (IndexRow.__post_init__, the ex/source_id/snapshot_ids/adapter/profile/issues checks, lines 439-475); src/agentprov/corpus/register.py:148 and :167 (RegisterEntry.__post_init__, _stage_of_code(code) and _RID_RE.fullmatch(previous['rid'])); the TypeError escapes at src/agentprov/corpus/reader.py:306 (iter_index) and :207 (_detect_depth), then src/agentprov/corpus/verify.py:441
- **Disposition:** FIXED 75cfbca0
- **Repro:** `~/.agentprov/migration-work/review-core-b/repro/verify-B1a-2/`

**Failing input.** An executions.jsonl line that is a valid row except for `"source_id": 5` (or `"ex": 1`, `"adapter": null`, `"snapshot_ids": [["x"]]`, `"issues": [{}]`). Or a register.jsonl entry with `"previous": {"corpus_version":"1","rid":5}` or `"code": ["x"]`.

**Expected.** IndexRow.from_json / RegisterEntry raise IndexError_ / RegisterError, so CorpusReader.iter_index raises CorpusReadError. verify then reports `index.invalid` (or `corpus.read.invalid`) and continues with exit 1, the same as for `"source_id": "BAD"`. A downloaded corpus is untrusted (G.5.7) and should never crash the verifier.

**Actual.** `EXECUTION_ID_RE.fullmatch(1)`, `_ID_RE.fullmatch(5)`, `sorted(set([{}]))`, `_stage_of_code(['x'])` (frozenset membership) and `_RID_RE.fullmatch(5)` raise builtins.TypeError. reader.iter_index (reader.py:306) catches only IngestError/IndexError_, and _Verifier.documents catches only AgentProvError, so the run aborts with `agentprov: internal error: TypeError ... (exit 70)` and no other check runs. The same happens in _detect_depth (reader.py:207), CorpusWriter.open on resume, and render/source.py decode_index.

**Verifier.** I could not disprove it. At 7f8f8cb3, IndexRow.__post_init__ calls regex fullmatch, set() and sorted() on values from untrusted JSON before checking their types. RegisterEntry.__post_init__ does the same: frozenset membership in _stage_of_code, and _RID_RE.fullmatch on previous.rid. A wrong-typed field therefore raises builtins.TypeError. reader.iter_index catches only (IngestError, IndexError_), and _Verifier.documents catches only AgentProvError, so the TypeError reaches the CLI as an internal error with exit 70. This is reachable from the real CLI path (`agentprov verify --corpus <dir>`). None of BF-1..37 or F-12C-* mention TypeError, type confusion or exit 70 on index or register rows, and no guard or test covers it. Spec G.5.7 treats a downloaded corpus as untrusted, so verify should report the problem instead of crashing. The string-typed control case behaves correctly (index.invalid, exit 1), which confirms the expected behaviour.

**Evidence.** Script: ~/.agentprov/migration-work/review-core-b/repro/verify-B1a-2/repro.py (scratch data in ~/.agentprov/migration-work/review-core-b/verify-B1a-2). Key output:
[source_id BAD (control)] decode_index -> IndexError_; iter_index -> CorpusReadError
[source_id 5] decode_index -> TypeError; iter_index -> TypeError
[ex 1] / [adapter null] / [snapshot [[x]]] / [issues [{}]] -> TypeError for both
[register previous.rid 5] decode_register -> TypeError
[register code ['x']] decode_register -> TypeError
[register code 'nope.nope' (control)] decode_register -> RegisterError
CLI [source_id BAD (control)] exit=1 ... failed: index.invalid at executions.jsonl
CLI [source_id 5] exit=70 ... agentprov: internal error: TypeError: expected string or bytes-like object, got 'int' (exit 70); counters={} (no other check ran)

**Fix.** In IndexRow.__post_init__, check isinstance(x, str) before every regex fullmatch (ex, source_id, each snapshot id, source_key, adapter, profile). Check that every element of snapshot_ids and issues is a str before calling set() or sorted(). In RegisterEntry.__post_init__, check that code, stage, severity, disposition, previous.rid and previous.corpus_version are str before the frozenset lookups and regex matches. Raise IndexError_ / RegisterError on a failed check. A simpler fallback: in IndexRow.from_json and RegisterEntry.from_json, catch (TypeError, ValueError) and re-raise as IndexError_ / RegisterError. Add a parametrised test that sends each wrong-typed field through decode_index / decode_register and through `verify`, and expects index.invalid with exit 1. Valid rows decode exactly as before, so no stored bytes change.

### CB-3 (B1a-3): CorpusWriter.flush commits executions.jsonl before validation/results.jsonl, so a failed flush permanently loses validation rows on resume

- **Reproduced:** yes
- **Severity:** robustness (claimed robustness); **class:** 0
- **Where:** src/agentprov/corpus/writer.py:396 (index written before validation at 397-401); same commit-point assumption in src/agentprov/adapters/runner/importer.py:899 and src/agentprov/corpus/derive.py:1147-1150
- **Disposition:** FIXED cc96c18a
- **Repro:** `~/.agentprov/migration-work/review-core-b/repro/verify-B1a-3/`

**Failing input.** An import whose final flush fails after `self.index.write(...)` and before the validation results are written, for example ENOSPC or SIGKILL while writing validation/results.jsonl. Then `agentprov import` is resumed on the same working corpus.

**Expected.** The index is the commit point and is written last, so on resume an execution either has its index row and its validation row, or neither (and is re-processed).

**Actual.** The index row is on disk but its validation row is not. On resume the importer sees the row (`has_execution`) and counts it skipped_resume. The validation row that was only in memory is lost for good, and validation/results.jsonl stays missing or short. Only a later `verify` reports `index.digest.validation`. --retry-failed does not help because the row is not failed.

**Verifier.** I could not disprove the claim. At origin/main 7f8f8cb3, CorpusWriter.flush (src/agentprov/corpus/writer.py:392-401) writes origins, members and register first. It then writes executions.jsonl (`self.index.write`, line 396). Only after that does it write validation/results.jsonl and summary.json (lines 397-401). Both resume paths treat the index row as the commit point:
- The importer's `_known_artefacts` / `_seen_before` (adapters/runner/importer.py:868-899) counts an indexed execution as skipped_resume. `--retry-failed` only discards rows with status 'failed'.
- derive's resume (corpus/derive.py:1147-1150, `_complete`) checks only that the index row's `validation` digest is not None. It never checks that a validation row exists.

Nothing upstream stops a resume in this state. derivation.json and corpus.json are written after flush (`_write_documents`, importer.py:2128-2129), so after a failed flush they are absent and `_check_identity` skips them. No BF-1..BF-37 or F-12C-* item covers this; the BF list only has BF-32 (derive resume under another semantics profile), which is unrelated. One correction to the claim's fix: origins, members and register are already written before the index. Only the two validation files come after it.

**Evidence.** The repro is at scratchpad/review/verify-B1a-3/repro.py and was run with `uv run python`. Run 1 adds ex1 (validation row plus index entry) and patches atomic_write_bytes to raise ENOSPC on results.jsonl. Run 2 resumes on the same working corpus and adds ex2. Output:
```
run1 flush failed: [Errno 28] No space left on device
resume: ex1 index row present -> True | index validation digest -> StageOutput(state='ok', digest='d488283a...')
resume: ex1 validation row in writer -> False
after resume: ex1 row present -> False | ex2 row present -> True
after resume: summary executions -> 1 | index rows -> 2
```
So after the resume, executions.jsonl holds 2 rows, both with validation digests, while validation/results.jsonl and summary.json cover only ex2. The ex1 row is lost for good: the importer counts ex1 as skipped_resume and derive counts it as 'resumed'. Only a later `verify` reports it, as `index.digest.validation` absent (verify.py:795).

**Fix.** In CorpusWriter.flush, move the validation/results.jsonl and validation/summary.json writes (lines 397-401) above `self.index.write(self.layout.executions)`, so executions.jsonl is the last file written and stays the commit point. A validation row left without an index row after a crash does no harm: the execution is re-processed on resume and add_validation replaces that row, since rows are keyed by ex. Optionally, add a check in open() or in derive's `_complete` that a row with a validation digest has a loaded validation row, and re-process it if not. Add a regression test that injects ENOSPC on results.jsonl, resumes, and asserts every indexed validation digest has a row.

### CB-4 (B1a-4): by_stage.expand.ok subtracts failed containers that were never counted, so a failed container lowers the count of successful expansions

- **Reproduced:** yes
- **Severity:** correctness (claimed correctness); **class:** 1
- **Where:** src/agentprov/corpus/manifest.py:754-756 (corpus_counts by_stage.expand)
- **Disposition:** CLASS 1: regen-batch item 57 (approved; held branch review-core-b-regen)
- **Repro:** `~/.agentprov/migration-work/review-core-b/repro/verify-B1a-4/`

**Failing input.** corpus_counts with members rows for two containers C1 and C2 (both expanded) and one register entry {stage:'expand', code:'expand.failed', subject:{snapshot_id:'s1', path:'c3.zip'}} for a third container C3.

**Expected.** counts.by_stage.expand == {ok: 2, failed: 1}

**Actual.** {ok: 1, failed: 1}. `containers` comes from raw/members.jsonl rows, and a failed expansion (_consume / _failure_event return before any row) adds no rows, so subtracting len(expand_failed) removes it twice. `ok` is clamped to 0 when failures outnumber successes. The failed set is also keyed by path without snapshot_id, so one path failing in two snapshots counts once. The sealed corpus.json and the DATASHEET report wrong expand tallies. No test covers by_stage.expand.

**Verifier.** I could not disprove it. On origin/main 7f8f8cb3 the code behaves as claimed, and real callers reach it. expand_containers (src/agentprov/raw/members.py) gives a failed container no member rows: the expand.container_missing branch around l.1068, _consume returning after _failure_event at l.1175, and the MembersError/OSError branch at l.1246 all return before outcome.rows.extend at l.1251. CorpusWriter.expand (corpus/writer.py:193-201) therefore writes members.jsonl only for containers that succeeded, and registers the failure as a stage='expand' entry. Every stage='expand' event is a container-level failure: findings, member rejections and the advisory all use stage 'ingest'. So in manifest.py:753-756 `containers` holds only the successes, and subtracting len(expand_failed) removes each failure a second time. Both callers seal the wrong value: package.py:700 writes corpus.json, and verify.py:1117 recomputes with the same function, so verify agrees with the wrong number and does not catch it. Neither BF-1..37 nor F-12C-* mentions by_stage, corpus_counts or the expand tally, and no test under tests/ references by_stage. Two details in the claim need correcting. First, I found no consumer of by_stage in the datasheet code (grep finds only manifest.py and the schema), so the error is in corpus.json counts.by_stage.expand, and I could not confirm the claim that the DATASHEET is also wrong. Second, a related edge the claim missed: an archive that expands successfully with zero members also writes no members.jsonl rows, so it is left out of 'ok' as well.

**Evidence.** Script: ~/.agentprov/migration-work/review-core-b/repro/verify-B1a-4/repro.py. It calls the real expand_containers on two stored zips (c1, c2) plus a third spec, c3, whose object is not stored. It turns the events into entries with RegisterEntry.from_event, exactly as CorpusWriter.expand does, then calls corpus_counts. Output:
expanded containers: 2 member rows: 2 rows for c3: 0
register: [('expand', 'expand.container_missing', 'c3.zip')]
no failure entry  -> {'ok': 2, 'failed': 0}
one failed (c3)   -> {'ok': 1, 'failed': 1}  expected {'ok': 2, 'failed': 1}
worker.limit c3   -> {'ok': 1, 'failed': 1}      (failure built with _failure_event(WorkerLimitError('cpu')), the pool path)
1 ok + 2 failed   -> {'ok': 0, 'failed': 2}  expected {'ok': 1, 'failed': 2}   (clamped to 0)
c3 fails in s1,s2 -> {'ok': 1, 'failed': 1}  expected failed 2   (failed set keyed by path only, no snapshot_id)
This can happen in a real import: importer.map_containers (adapters/runner/importer.py ~l.1648-1664) expands several container specs in one corpus.expand call, so one bad container among good ones produces this tally.

**Fix.** Change the two lines so that 'ok' is not reduced by failures and failures are keyed by snapshot and path:
expand_failed = {(e.subject.get("snapshot_id", ""), e.subject.get("source_key", e.subject.get("path", ""))) for e in register if e.stage == "expand" and e.severity == "error"}
by_stage["expand"] = {"ok": len(containers), "failed": len(expand_failed)}
A container that fails never writes members.jsonl rows, so `containers` already counts only successes.

Optional: count a successful zero-member container in 'ok' by recording it in members.jsonl or in the expand stage record.

Add a unit test in tests/unit/corpus that runs two good containers and one failed container and asserts {ok: 2, failed: 1}. Add a second case with one success and two failures that asserts ok is not clamped to 0.

This changes counts.by_stage.expand in corpus.json, and so the manifest digest, for any corpus with an expand failure. Route it to the regen batch.

### CB-5 (B1a-5): corpus-spec licence.files accepts names that differ only in case; on macOS the generated LICENSES/<src>/NOTICE.md and LICENSE are silently overwritten

- **Reproduced:** yes
- **Severity:** correctness (claimed correctness); **class:** 0
- **Where:** src/agentprov/corpus/spec.py:318-320 (missing check). The overwrite happens at src/agentprov/corpus/package.py:669-672 together with the seal write loop `for label in sorted(files): writer.write(label, files[label])`.
- **Disposition:** FIXED 5dcadd7c (deferrals-c rebases over it)
- **Repro:** `~/.agentprov/migration-work/review-core-b/repro/verify-B1a-5/`

**Failing input.** corpus-spec.toml with `[licence] files = ["LICENSE", "license", "notice.md"]`, sealed on the default case-insensitive APFS volume.

**Expected.** parse_spec refuses names that collide case-insensitively with each other or with the generated NOTICE.md (the check `"NOTICE.md" in files` is case-sensitive), or sealing refuses colliding labels. The sealed tree holds each listed file and the generated NOTICE.md.

**Actual.** parse_spec accepts all three. package.seal writes `for label in sorted(files)`: the upstream notice.md replaces the generated NOTICE.md content (the file keeps the name NOTICE.md), and `license` replaces LICENSE. The manifest/datasheet `licence_files` lists LICENSES/s/license and LICENSES/s/notice.md, which do not exist as entries. checksums are built from the tree scan, so sealing succeeds and the H.4.4 attribution notice is lost without any error.

**Verifier.** I could not disprove it. At 7f8f8cb3, parse_spec checks licence.files for duplicates only by exact equality (`_strings`: `len(set(value))`) and checks NOTICE.md with a case-sensitive `"NOTICE.md" in files` (spec.py:319). It refuses "NOTICE.md" but accepts "notice.md" on its own and accepts ["LICENSE", "license", "Notice.md"]. The input is reachable: cli/package.py `_licence_files` supplies each named file either from a raw git object whose path equals the name or from `--licence-file NAME=PATH`, and package.seal puts them in `files` at 669-672 and writes `for label in sorted(files): writer.write(...)`. Nothing downstream catches the collision. write_checksums and verify_checksums and root_digest work from a tree scan. No validator checks that `licences.raw[].licence_files` paths exist (I grepped manifest.py, datasheet.py, release/). The repo already has a case/NFC collision key (ingest/names.collision_key, G.3.6), but corpus/spec.py and package.py do not use it. BF-1..37 and F-12C-* do not cover this. One correction: a single `files = ["notice.md"]` is enough to destroy the generated NOTICE.md. The LICENSE/license pair is only needed for the second overwrite. The impact is limited to spec-author input on a case-insensitive volume (the default APFS on the capture Macs). No corpus data is attacker-controlled here, so it stays at correctness, not security.

**Evidence.** The repro is ~/.agentprov/migration-work/review-core-b/repro/verify-B1a-5/repro.py. It runs the real parse_spec and the real package._Writer (the seal's writer), in seal's sorted-label order, against a tree under ~/.agentprov/migration-work/review-core-b/verify-B1a-5/tree. Output:
REFUSED  ["NOTICE.md"] -> licence.files: NOTICE.md is generated at sealing (H.4.4)
ACCEPTED ["notice.md"] -> ('notice.md',)
ACCEPTED ["LICENSE", "license", "Notice.md"] -> ('LICENSE', 'license', 'Notice.md')
labels written / listed in manifest licence_files: ['LICENSES/s/LICENSE', 'LICENSES/s/NOTICE.md', 'LICENSES/s/Notice.md', 'LICENSES/s/license']
on disk: [('LICENSE', b'upstream license'), ('NOTICE.md', b'upstream Notice.md')]
generated notice survives: False
So the generated H.4.4 attribution notice is replaced by the upstream file's bytes and keeps the name NOTICE.md. LICENSE holds the bytes of `license`. Two of the four labels that the manifest's licence_files and DATASHEET list do not exist as tree entries. The checksums are rebuilt from the scanned tree, so the seal does not fail.

**Fix.** In parse_spec, after `files = _strings(...)`, build `keys = [collision_key(n) for n in files]` using agentprov.ingest.names.collision_key (NFC(casefold)). Raise CorpusSpecError when `len(set(keys)) != len(keys)` ("licence.files: names collide case-/normalisation-insensitively") or when `collision_key("NOTICE.md") in keys` (replacing the case-sensitive check). As defence in depth, package.seal could refuse when the collision keys of the `files` labels repeat. Add a spec test for ["notice.md"] and ["LICENSE", "license"].

**Reviewer notes (B1a).** Area B1a reviewed at 7f8f8cb3: layout, manifest (counts, digests, validator), index, register, writer, reader, spec, shapes, stages, dedup, archive, rawtree, purge and withheld. Every finding was reproduced with a script in ~/.agentprov/migration-work/review-core-b/repro/B1a/ (r1..r5); scratch data is in ~/.agentprov/migration-work/review-core-b/B1a/. No repository file was changed.

Checked and not reported:
- Sorting is locale-independent: str sort and utf-8/ascii key sorts agree, and all labels are ASCII.
- decode_index, decode_register and decode_tombstones refuse non-canonical bytes by round trip, so tampering shows.
- classify_relpath refuses dotfiles, '..', non-ASCII and wrong shards.
- The raw store refuses ambiguous extensions and symlinked shards.
- Reader opens are no-follow and grammar-checked.
- Archive-mode duplicate labels are findings.
- rawtree label conflicts are refused.
- Orphan execution files are already caught by verify (index.orphan).

Lower-value observations, not reported as findings:
- classify_relpath admits both shard depths in one tree; orphans() catches the extra copy.
- decode_withheld does not require canonical bytes; the checksums cover it.
- withheld.one_line_note keeps bidi/zero-width characters; the datasheet escaping from F-12C-03 applies downstream.
- CorpusWriter.open follows a symlinked DIR.partial, which purge refuses; this is a local-only concern.
- raw_dispositions can list one digest twice if it is both withheld and referenced.

Finding 5 sits partly in package.py, outside my area; its root cause, the case-sensitive uniqueness check, is in spec.py.

## B1b

### CB-6 (B1b-1): derive/recompute refuse every working corpus after `purge` (raw.object.missing), and NEW never carries raw/tombstones.jsonl or raw/REFERENCES.json

- **Reproduced:** yes
- **Severity:** correctness (claimed correctness); **class:** 0
- **Where:** src/agentprov/corpus/derive.py:634-656 (listed_objects/check_inputs), with derive.py:822-841 (prepare: no copy of raw/tombstones.jsonl) and src/agentprov/corpus/writer.py:316 (rejects the purged execution's row)
- **Disposition:** ROUTED to the twins (derive.py; sibling of BF-20)
- **Repro:** `~/.agentprov/migration-work/review-core-b/repro/verify-B1b-1/`

**Failing input.** A working corpus in which one object was removed with `agentprov purge sha256:<hex> --reason secret --corpus DIR --yes`. The purge docstring (corpus/purge.py:15) says the rows' issues are refreshed 'when the corpus is next derived or sealed'.

**Expected.** `recompute --dry-run` and `derive --out` handle the tombstoned object as `verify --level chain` already does: they report it as tombstoned and skip the checks that need its bytes, then derive the rest. NEW keeps raw/tombstones.jsonl (and raw/REFERENCES.json), so the tombstone, the F-12C-05 re-import guard and verify's `raw.tombstoned` classification still work on NEW.

**Actual.** `listed_objects()` (634-642) marks every raw/origins.jsonl object as included=True, so `check_inputs()` raises RawDigestError raw.object.missing, exit 1, for both `recompute --dry-run --stages sem,prov,validation` and `derive --out`. `verify --level chain` on the same tree exits 0 with `raw.tombstoned` x1. So a purged corpus can no longer get the CLAUDE.md '0 differences' recompute check. Separately, `prepare()` (822-841) copies objects, origins, members and register but never raw/tombstones.jsonl or raw/REFERENCES.json. Once the refusal is fixed, NEW would silently lose the purge record. This is the same root cause as BF-20 (sealed corpora with WITHHELD.json) but a different trigger that BF-20's fix must also cover.

**Verifier.** I could not disprove the claim at 7f8f8cb3. Both commands are reachable from the real CLI. `purge` is a shipped command. MN N.2.15 and the purge.py docstring say that after a purge, counts and index issues are refreshed by `derive` or seal, so derive is expected to work on a purged working corpus. BF-20 does not cover this case: it is about sealed corpora whose objects are listed in WITHHELD.json, and a working corpus after `purge` has no WITHHELD.json, only raw/tombstones.jsonl. A BF-20 fix keyed on WITHHELD.json would therefore not fix this one. I found no existing test or guard for derive or recompute after purge. One correction to the claim: the refusal goes deeper than check_inputs. When I patched listed_objects to skip tombstoned digests, derive still failed later in CorpusWriter (writer.py:316, corpus.writer.raw, "an included raw artefact is not in the store"), because the purged execution's index row still lists the object as included. The fix also has to carry that execution's row as withheld or skip it, not only change check_inputs. The second half of the claim (NEW drops tombstones.jsonl) is confirmed from the code and partly at runtime. derive.py never mentions tombstones, prepare() at 822-841 copies only objects, origins, members and register, and the NEW.partial tree left by the patched run has no raw/tombstones.jsonl. I could not show the full end-to-end loss because derive cannot finish. If that loss happened, packaging NEW would hit withhold.py:686 ("release.withheld in the register but no tombstone"), or the purge record would silently disappear.

**Evidence.** Script: ~/.agentprov/migration-work/review-core-b/repro/verify-B1b-1/repro.py (data under ~/.agentprov/migration-work/review-core-b/verify-B1b-1/). Output:
rows 2 purging primary of row 0
purge exit 0
tombstones present: True
verify chain on purged working corpus exit 0 {'checksums.absent': 1, 'raw.tombstoned': 1}
recompute --dry-run exit 1 ['agentprov: error [raw.object.missing]: a raw object the source lists is missing from its store']
derive --out exit 1 ['agentprov: error [raw.object.missing]: a raw object the source lists is missing from its store']
derive.py mentions tombstones: False
patched derive exit 1 ['agentprov: error [corpus.writer.raw]: an included raw artefact is not in the store']   (listed_objects patched to skip tombstoned digests)
 NEW tree new2.partial tombstones.jsonl present: False
 SRC register release.withheld lines: 1
Spec: MN_repo_cli.md:2914 says "Counts and index issues are refreshed by `derive`/seal, not by `purge` (D-46)".

**Fix.** Read raw/tombstones.jsonl through purge.decode_tombstones in Derivation. In listed_objects/check_inputs, count a not-stored object as tombstoned (a counter plus a notice), not as raw.object.missing. Carry the executions that cite a tombstoned object, either directly or through a raw/members.jsonl container, as withheld: keep their register release.withheld entries, and either do not re-derive or re-write them, or write their rows with the issue refreshed, so that CorpusWriter's included-object check (writer.py:316) does not fire. In prepare(), copy raw/tombstones.jsonl (and raw/REFERENCES.json when present) into NEW byte for byte. Fix this together with BF-20 (twins, claude/rules-drift), and give both triggers one shared 'accounted-for absence' set (tombstones, WITHHELD.json, REFERENCES.json). Add a test: purge, then recompute --dry-run, then derive --out, then package/verify.

### CB-7 (B1b-2): seal records the sealing checkout's commit as producer.git_commit without checking that the working corpus was built by that code

- **Reproduced:** no
- **Severity:** none (not a defect; at most a documentation note that producer.git_commit is the sealing commit, valid for reproduction under H.8.4(2)) (claimed correctness); **class:** 0
- **Where:** src/agentprov/corpus/package.py:685
- **Disposition:** NOT REPRODUCED (behaviour as H.8.4(2) specifies)
- **Repro:** `~/.agentprov/migration-work/review-core-b/repro/verify-B1b-2/`

**Failing input.** A working corpus imported at commit X whose derivation.json stage code digests (engine_code_sha256, adapter_code_sha256, and so fn_digest) are not those of the checkout that runs `package` at commit Y. Simulated by setting every recorded code digest to sha256:eee... (and the cross-checked corpus.json adapters[].code_sha256 to match).

**Expected.** D-430 and D-358 reproduce a corpus 'at the commit and core lockfile that built it' and name `producer.git_commit` as that commit. Seal should therefore refuse (or record the building commit) when a recorded stage's code digest differs from what this checkout computes (code_sha256 over the same scopes, as the importer does).

**Actual.** seal() succeeds and writes producer.git_commit = the sealing commit, while agentprov_version, lockfile_sha256, python and platform are copied from the import. The only code-digest check is adapter code digest consistency between corpus.json and derivation.json (lines ~667-671); nothing compares either with the running code. `verify --level chain` passes too. The manifest can therefore name a commit at which `recompute --dry-run` cannot give 0 differences.

**Verifier.** The mechanics are as described. seal() checks only that the adapter code digest in corpus.json matches the one in derivation.json (package.py:676-680), and it writes producer.git_commit from the sealing checkout (package.py:685). The wrong behaviour the claim depends on does not follow, and the spec does not ask for the proposed fix.

(1) The spec allows code drift. H.8.4(2) leaves code digests out of a stage's declared versions: "If the code digest changes and every output is identical, the change is a refactor and passes." derive.py:142 (_CODE_KEYS) puts this into code.

(2) Seal already refuses a version mismatch. It refuses when the source profile version differs from the one this package ships (cli/package.py), when the rule catalogue bytes differ from aer/sem rules_sha256, when the PROV spec catalogue differs from prov rules_sha256, and when the semantics profile digests differ from sem profiles. So the sealing commit always ships the corpus's declared versions. Under H.8.4(2), recompute at that commit must give 0 differences. If it does not, the cause is unbumped code drift at that commit, and recompute catches that as an unexplained_change. It is not a false statement written by seal.

(3) I reproduced the reviewer's exact scenario: every engine/adapter code digest faked, fn_digest recomputed, corpus.json adapters made to match. Seal succeeds. `recompute --dry-run` on the sealed corpus, run with the same code that sealed it, then gives "3 identical, 0 changed (explained), 0 unexplained, 0 failed", exit 0. It also prints a per-stage notice that the code digest changed and a refactor passes. So the claimed consequence, a recorded commit at which recompute "cannot give 0 differences", does not occur.

(4) The proposed fix would refuse valid corpora. Refusing on any code-digest mismatch goes against H.8.4(2). It would also reject any corpus whose aer stage was imported at one commit and whose sem/prov stages were derived later. derive records the new code digests for the stages it re-runs and keeps the import's aer digests, which is a normal state.

One narrower point, not the claim as stated: producer.lockfile_sha256, key_distributions, python and platform are copied from the import, while git_commit and distributions_sha256 come from the sealing environment. If uv.lock changed between import and seal, the manifest pairs commit Y with commit X's lockfile digest. This is not reproduced here and would need its own report.

**Evidence.** Script: scratchpad/review/verify-B1b-2/repro.py, run with uv run python from the worktree. Key output:
faked code digests: [('aer','engine_code_sha256'), ('aer','adapter_code_sha256'), ('sem','engine_code_sha256'), ('prov','engine_code_sha256'), ('validation','engine_code_sha256')]
SEAL OK; producer.git_commit = 0123456789ab (supplied sealing commit)
recompute --dry-run exit: 0
agentprov recompute: would derive 3 execution(s); recomputed stages: aer,sem,prov,validation; 3 identical, 0 changed (explained), 0 unexplained, 0 failed, 0 unverified
notice: aer: the code digest changed and every declared version is the same (a refactor passes only if every output is identical; H.8.4(2))
(the same notice for sem, prov and validation)
Spec: HL_corpus_versioning.md:1381-1384 (H.8.4(2)); derive.py:142 _CODE_KEYS; package.py:619-650 (catalogue/profile digest refusals at seal).

**Fix.** No code fix needed for the claim as stated. Optionally, D-430/H.2.7 could say that producer.git_commit is the sealing commit, and that seal guarantees the declared versions match at that commit. The separate lockfile_sha256 vs git_commit pairing could be checked: refuse, or emit a notice, when the core uv.lock digest at seal differs from the recorded lockfile_sha256. That needs its own reproduction.

### CB-8 (B1b-3): An edited views/ file in a sealed corpus passes `verify --level chain` once checksums.sha256 is regenerated (views are not digest-chained)

- **Reproduced:** no
- **Severity:** test-gap (not security; behaviour is the specified D-39/D-63 boundary, and rederive plus the root digest detect the edit) (claimed security); **class:** 0
- **Where:** tests/security/test_sec15_tamper_matrix.py:206 (no case pins the edited-view boundary); the behaviour itself, at src/agentprov/corpus/verify.py:932, is as specified
- **Disposition:** NOT REPRODUCED (D-63/H.5.5 boundary); optional SEC-15 pin test noted
- **Repro:** `~/.agentprov/migration-work/review-core-b/repro/verify-B1b-3/`

**Failing input.** A sealed corpus built by `derive --views transcript-v1` and then `package`. One views/transcript-v1/... file is changed to valid JSON with one string altered, and only checksums.sha256 is regenerated.

**Expected.** `chain` fails, because a view is a deterministic function of its AER (transcript_v1.render / render_converted + serialise, as `rederive` compares it). H.5.5 and the SEC-15 matrix list only DATASHEET.md, CHANGELOG.md and LICENSES/** as root-digest-only, and P-2/D-163 covered only an *added* view.

**Actual.** `verify --level chain` exits 0 with no finding. copies_and_optional_files() checks only that a view has a views stage and an index row, and no index digest or manifest FileRef covers view bytes. Only the externally published root digest detects the edit. Also, seal accepted the view files although the spec has `[derive] views = []`; seal never compares the tree's views with the spec.

**Verifier.** I reproduced the behaviour, but it is what the spec specifies, not a defect. (1) H.5.1, the digest chain, covers raw → AER → SEM → PROV → validation → index → corpus.json → checksums. views/ is not a link in it. H.1.2 and H.8 describe a view as an optional further function of the AER, its own DAG node. (2) The H.5.5 `chain` row gives the full check for views: "every `views/` file backed by a `views` stage and an index row (`views.undeclared`)". Content re-rendering is reserved for `rederive`, which caught this edit in my run (`rederive.unexplained_change`). (3) D-63 (DECISIONS.md:1957-1959) and sec-coverage-12c.md row 66 pin this boundary explicitly: "files no digest chain covers (... an added WITHHELD.json or view) pass `chain` and are detected by the root digest only". D-163/P-2 then added only the declaration reconciliation, by approved design. The claim cites the SEC-15 docstring's short list (DATASHEET, CHANGELOG, LICENSES) as the whole root-digest-only set, but that list covers only the KINDS of the mini-mit test corpus, which has no views. It does not narrow D-63. (4) The seal sub-claim does not hold either. The run used the documented CLI override `derive --views transcript-v1`, and derivation.json records the stage (stages = aer, sem, prov, validation, views). H.8.2 makes derivation.json the record of the stages run, and `views.undeclared` checks against it. The copied rules/corpus-spec.toml still says `views = []`, but that is the spec as written, with the CLI override recorded in derivation.json. Nothing is accepted that should not be. What is left is a design proposal: extend `chain` to re-render views, which would need a new D-number and a deliberate change to the SEC-15 pin. At most there is a small test gap: no SEC-15 case pins that an *edited* (not added) view passes `chain` but fails `rederive` and the root digest.

**Evidence.** Script: ~/.agentprov/migration-work/review-core-b/repro/verify-B1b-3/repro.py. It is the B1b script with the work dir moved and a rederive step added. Output at 7f8f8cb3:
  derive --views exit 0
  sealed; view files: 3
  clean chain exit 0 {}
  tampered view, checksums regenerated: chain exit 0 {}
  tampered view: rederive exit 1 {'rederive.unexplained_change': 1}
derivation.json in the sealed corpus: stages ['aer','sem','prov','validation','views']. rules/corpus-spec.toml:20 has `views = []` (the CLI `--views` overrides it and derivation.json records it).
Spec text: HL_corpus_versioning.md H.5.1 (the chain diagram has no views link); H.5.5 `chain` row, which checks views only for stage + index row (`views.undeclared`), while `rederive` re-runs every stage; DECISIONS.md D-63 ("an added WITHHELD.json or view ... detected by the root digest only") and D-163 (P-2 = declaration check only); docs/reports/hardening/sec-coverage-12c.md:66 (boundary pinned "as H.5.5 specifies").

**Fix.** No code fix is needed under the current spec. Optionally, add a SEC-15 case on a sealed corpus derived with `--views transcript-v1`: edit one view, regenerate checksums, then assert `chain` passes (the boundary is pinned), `rederive` reports `rederive.unexplained_change`, and `--root-digest` reports `root_digest.mismatch`. Moving view content into `chain` (re-rendering through VIEW_RENDERERS) would be a spec change. It would need a new decision amending D-63/H.5.5, and the test pin would change deliberately.

### CB-9 (B1b-4): A seal killed after corpus.json says sealed:true and before the swap leaves DIR.partial that can neither be resealed nor written

- **Reproduced:** yes
- **Severity:** robustness (claimed robustness); **class:** 0
- **Where:** src/agentprov/corpus/package.py:811-833 (sealed manifest written at 811, swap at 827; rollback only in the except BaseException block at 828-833); rerun refused at package.py:512 (assert_writable)
- **Disposition:** FIXED edd105fa (forward recovery; deferrals-c rebases over it)
- **Repro:** `~/.agentprov/migration-work/review-core-b/repro/verify-B1b-4/`

**Failing input.** `package` killed with no Python exception (SIGKILL, OOM killer, power loss) between writer.write(MANIFEST, manifest_bytes) (811) and atomic_swap_dir (827). On a large corpus this window covers write_checksums, verify_checksums and the full `_verify_chain`, which can take minutes.

**Expected.** The interrupted seal can be resumed or rolled back: rerunning `package` re-seals, or the working tree is still recognisably working. Rollback today runs only on a Python BaseException.

**Actual.** DIR does not exist, DIR.partial/corpus.json has "sealed": true and checksums.sha256 exists. Rerunning seal raises SealedCorpusError corpus.sealed (exit 4): assert_writable sees the sealed flag, and _check_working would also refuse a non-working manifest. Every writer (import, purge, derive --out inside) is refused too, and the working corpus.json, executions.jsonl and register bytes that rollback would restore are gone. No documented recovery exists; the user must hand-edit the corpus.

**Verifier.** I could not disprove the claim; it holds at origin/main 7f8f8cb3. The rollback in seal() (package.py:828-833) is an `except BaseException` handler, so it runs only when Python raises. SIGKILL, the OOM killer or power loss skip it. The window opens at writer.write(MANIFEST, manifest_bytes) (line 811), which writes "sealed": true. It stays open through write_checksums, verify_checksums, the read-back check, _verify_chain, root_digest and two iter_tree passes, and closes at atomic_swap_dir (line 827). Any kill inside that window leaves DIR.partial with a sealed manifest.

Real callers hit this path: `agentprov package` calls seal(). On a rerun, seal() calls assert_writable(partial) at line 512, which refuses with corpus.sealed, so the tree cannot be resumed. The working bytes are lost: executions.jsonl and corpus.json are rewritten in place, and the copies kept in _Writer.restore exist only in memory.

The spec says this must not happen. MN_repo_cli.md:1512 reads "A crash leaves a resumable working tree, never a half-sealed corpus (H.1.5(1))", and H.1.5(1) says "A failure leaves no half-written corpus". BF-1..BF-37 and F-12C-* do not cover it; the nearest entry, BF-32, is about resuming derive. No test covers a seal killed without a Python exception.

One nuance in the claim: before the kill, the tree has already passed its own checksum and manifest read-back checks. The data is therefore complete and only the final chain verify and the swap are missing. That makes forward recovery (finish the seal) a simpler fix than rollback.

**Evidence.** Reproduction: ~/.agentprov/migration-work/review-core-b/repro/verify-B1b-4/repro.py. It builds a working corpus with tests/unit/corpus/seal_support._build.

Control run: _verify_chain raises RuntimeError and rollback restores the tree. Output: "control (exception) -> corpus.json restored: True | checksums left: False".

Kill run: a forked child replaces _verify_chain with os._exit(137) and calls package.seal. Output:
- child exit: 137
- DIR exists: False | DIR.partial exists: True | sealed: True | checksums.sha256: True
- working corpus.json bytes kept: False | executions.jsonl kept: False
- re-seal: SealedCorpusError corpus.sealed exit 4
- write guard: SealedCorpusError corpus.sealed

The working sealed flag before the seal was False. Spec references: MN_repo_cli.md:1512 and HL_corpus_versioning.md:249-251 (H.1.5(1)).

**Fix.** Simplest fix is forward recovery. At the start of seal(), check whether DIR is absent and DIR.partial/corpus.json says sealed:true. If so, resume instead of calling assert_writable: run verify_checksums(partial), check that the manifest validates and that its corpus_version and content digest match the request, run _verify_chain(partial), then atomic_swap_dir(partial, final). If any check fails, refuse with a dedicated code such as corpus.seal.interrupted that names the state. Also document the recovery in N.2.11.

The alternative is rollback. Before the first write, persist a seal-journal file in DIR.partial that holds the original bytes of each file seal rewrites and the list of files it creates, write it atomically and fsync it. A rerun replays the journal first. assert_writable would have to accept a sealed manifest when the journal is present.

Either way, add a test that kills a forked seal with os._exit inside the window and checks that the next seal finishes or rolls back. The fix changes no stored bytes; the sealed tree produced is the same.

### CB-10 (B1b-5): _check_gating accepts a failed gating check of an unregistered execution if any other failed row is registered

- **Reproduced:** yes
- **Severity:** correctness (claimed correctness); **class:** 0
- **Where:** src/agentprov/corpus/package.py:1063 (_check_gating, lines 1053-1065; called at line 741). Producer of the B case: src/agentprov/corpus/derive.py:1239-1243 and src/agentprov/adapters/runner/importer.py:1781-1786.
- **Disposition:** FIXED fef231db (deferrals-c rebases over it)
- **Repro:** `~/.agentprov/migration-work/review-core-b/repro/verify-B1b-5/`

**Failing input.** A manifest validation summary with a gating check fail=2, for two failed rows A and B. The register has validate.failed for A only; B carries prov.failed. This happens when derive/import's _finish_unit sees a failing tier-3 check and a failed PROV job, because it registers validate.failed only when PROV is ok.

**Expected.** H.2.12: fail MUST be 0 for gating checks 'unless the execution is failed and its row in the register says so'. That is a per-execution condition, so B must refuse the seal exactly as it does when B is alone.

**Actual.** `if not (failed_rows & flagged)` only checks that the two sets intersect. B alone gives ManifestError corpus.manifest.validation. A+B gives no error and the seal proceeds, so whether a corpus seals depends on an unrelated execution.

**Verifier.** I could not disprove it. At origin/main 7f8f8cb3, `_check_gating` (src/agentprov/corpus/package.py:1053-1065) only tests whether the set of failed rows and the set of executions with a `validate.failed` entry overlap at all (`if not (failed_rows & flagged)`). It never ties the failing check counts to particular executions. H.2.12 (docs/architecture/HL_corpus_versioning.md:571-572) states the exemption per execution: "unless the execution is `failed` and its row in the register says so". So whether the seal is refused for one execution depends on an unrelated execution being registered.

The path is reachable from the real derive and import code:
- derive.py:1239-1243 and importer.py:1781-1786 register `validate.failed` only when `prov[SPEC_ID].state == "ok"`.
- When the worker result is ok but carries a `prov_error` frame, `_prov_result` (derive.py:1301-1304) registers only `prov.failed`.
- In that same case `_sem_result` still copies the `sem_validation` tier-3 checks (derive.py:1284-1287) into the validation row. That row is written by `add_validation` and counted in summary.json, so the gating `fail` count goes up with no `validate.failed` entry for that execution.

Neither the BF-1..37 list nor sec-coverage-12c mentions gating or H.2.12, and no test refers to `_check_gating`.

The rule is also looser than the claim says. One `validate.failed` row hides any number of gating failures, including more failures than there are failed rows (third case below). The spec does not say which behaviour is right when the only failed execution is registered as `prov.failed`: refusing it alone could be read as too strict. Either way the result must not depend on another execution, so the defect stands as a correctness issue.

**Evidence.** The repro script ~/.agentprov/migration-work/review-core-b/repro/verify-B1b-5/repro.py calls `agentprov.corpus.package._check_gating` directly. Each case passes a manifest with one check (id `sem.x`, skipped 0) and a different set of rows and register entries. Output from `uv run python` at origin/main:

B alone (gating fail, prov.failed only) -> REFUSED corpus.manifest.validation
A+B (A validate.failed, B prov.failed, fail=2) -> ACCEPTED
A + ok row C, fail=5 -> ACCEPTED

The cause is package.py:1061-1063:
    flagged = {e.subject.get("ex") for e in register if e.code == "validate.failed"}
    failed_rows = {r.ex for r in rows if r.status == "failed"}
    if not (failed_rows & flagged): raise ...

The real producer of the B case is derive.py:1239-1243 (and importer.py:1781-1786), which registers `validate.failed` only when `prov[SPEC_ID].state == "ok"`. A `prov_error` frame registers `prov.failed` (derive.py:1303-1304, 1310-1313), while the tier-3 `sem_validation` checks are still recorded (derive.py:1284-1287) and the validation row is still written (derive.py:1244).

**Fix.** Pass the parsed results rows (`_jsonl(results_bytes)`, already available at line 738) into `_check_gating` and check each execution separately:
- Build `status = {r.ex: r.status for r in rows}`.
- Build `registered = {ex: set of codes}` from the register.
- For every results row whose `checks` contain any gating `fail`, require `status[ex] == "failed"` and a register entry for that ex with an accepted code. The accepted codes are `validate.failed`, or also the stage-failure codes (`prov.failed` / `sem.failed`) that derive and import write instead when PROV fails. Pick one and say so in H.2.12.
- Also require the summed gating `fail` to be at most the number of rows that pass this test.

Alternatively, have derive/import also register `validate.failed` when tier-3 checks fail and PROV has failed. That changes register bytes, so it would be class 1.

### CB-11 (B1b-6): chain never recomputes a row's status (H.3.2(1)) or checks register entries against the row's issues; a whitewashed row passes a consistent forgery

- **Reproduced:** yes
- **Severity:** security (Low; consistent forgery detected only by the published root digest, same T-13 residual class as F-12C-02). Arguably correctness, since `chain` claims H.3.2 recomputation. (claimed security); **class:** 0
- **Where:** src/agentprov/corpus/verify.py:777 (_execution, beside the completeness recompute); also verify.py:1234-1246 (rederive drops index_refreshed)
- **Disposition:** ROUTED to the twins (verify.py)
- **Repro:** `~/.agentprov/migration-work/review-core-b/repro/verify-B1b-6/`

**Failing input.** A sealed corpus where one index row is changed to status 'failed' with issues [] while all its stages are 'ok' and register.jsonl keeps its entries for that ex. counts.by_status is adjusted, and files, digests, content digest and checksums are regenerated (verify_support.reforge, the device used for F-12C-02). The reverse whitewash (status ok and issues dropped on a failed row) uses the same path.

**Expected.** `chain` fails. A row's status should equal compute_status(row.stages, severities of the register entries for that ex) ('index.status'), and the register codes for an ex should equal the row's issues, not just be a superset of them.

**Actual.** Exit 0 with no finding. _execution checks unit, completeness, facets and digests but not status. executions() checks only row.issues ⊆ register codes (R5's one direction). The published root digest is the only anchor; this is the same Low class as F-12C-02 but a different field.

**Verifier.** The main claim holds; one part of it does not. At origin/main 7f8f8cb3, `chain` never recomputes an index row's `status` (H.3.2(1)). _Verifier._execution rechecks unit, completeness, raw, digests and facets but not status, and executions() checks only that row.issues is a subset of the register codes for that ex. I could not disprove the status part: a consistently forged status passes `chain` with exit 0 and no finding.

The claim also undersells it. The strongest level, `--level rederive`, passes the forgery too. The rederive counts the forged row as `rederive_index_refreshed: 1`, a counter only, and verify.py:1234-1246 turns only report.changes and report.corpus_changes into findings. derive.py:40 / _refreshed record index_refreshed (status, issues, completeness...) separately and never as a change.

The other part does not hold as a spec defect. Requiring set(row.issues) == the register codes for that ex, in both directions, goes beyond H.6.1 R5. HL_corpus_versioning.md:1064-1066 states only one direction: "Every code in a row's `issues` has a register entry with that `ex`". The writer (writer.py:319-328, 369) also computes status from the severities of the row's own issue codes only. So a register entry for an ex outside row.issues is not a spec violation. My forgery B (a row's info-only issues dropped, status unchanged) passing `chain` is consistent with the current R5 text. Making that check bidirectional would be a spec change, not a bug fix.

Severity: this is the same T-13 residual as F-12C-02 (Low). The published root digest (`--release` with the root) still detects it. It is not a new class of attack, but a new field (status) that `chain` claims to reconcile and does not. F-12C-02 covers only snapshot_ids and n_origins, and no BF-* item covers status.

**Evidence.** Reproduction: ~/.agentprov/migration-work/review-core-b/repro/verify-B1b-6/repro.py. It builds a fresh sealed 3-execution corpus with seal_support._build and package.seal, real code digests and no fakes, under ~/.agentprov/migration-work/review-core-b/verify-B1b-6. It copies the corpus and applies verify_support.reforge(index=row.status 'ok'->'failed', change=counts.by_status ok-1/failed+1). Output:
  clean chain: (0, {})
  row ex_37evkqmflf2 status ok issues ['map.accounting_unverifiable', 'map.earlier_attempts_unobservable'] stages {aer: ok, prov: {...: ok}, raw: ok, sem: {...: ok}, validation: ok} recomputed ok   (same for the other 2 rows)
  A forged ok->failed chain: (0, {})
  B forged ok->ok, issues [...]->[] chain: (0, {})   (consistent with R5's one-directional text; not a defect)
The rederive check is in repro_rederive.py in the same directory:
  clean rederive: 0 {} {... 'rederive_index_refreshed': 0 ...}
  forgeA rederive: 0 {} {... 'rederive_index_refreshed': 1, 'rederive_identical': 3 ...}
The rederive does see the forged row (index_refreshed 1) but reports no finding and exits 0.

Code: verify.py:700-730 (executions: only the one-directional R5 reconcile), verify.py:739-800 (_execution: completeness at :777, no status check), verify.py:1234-1246 (rederive: index_refreshed is not reported), index.py:195 compute_status, writer.py:319-369 (status = compute_status(stages incl. sem/prov/validation states, severities of the row's issue codes)).

**Fix.** 1. In _Verifier._execution, next to the completeness check at verify.py:777, recompute status the way the writer does: stages = row.stages plus {sem: {p: s.state}, prov: {spec: s.state}, validation: row.validation.state} where present, and severities = [e.severity for e in self.register if e.subject.get('ex') == row.ex and e.code in set(row.issues)]. Add 'index.status' (failed) when compute_status(stages, severities) != row.status. Better still, factor the writer's row-status computation into a shared helper in corpus/index.py so the writer and verify cannot drift.
2. In verify's rederive (verify.py:1234-1246), report a nonzero report.counters['index_refreshed'] on a sealed corpus as a finding: failed when no declared version changed, unverified otherwise. Today a forged status, issues or completeness field is only counted there.
3. Do NOT make the register<->issues reconcile bidirectional without a spec change. H.6.1 R5 requires only issues ⊆ register codes, and the writer's status ignores register entries outside row.issues. If a bidirectional check is wanted, it is a spec decision (R5 text + D-entry) first.
Add an xfail-then-fixed SEC test in the style of test_sec19 (reforge status ok->failed and failed->ok, with counts.by_status adjusted, chain must fail with index.status) and update the H.5.5 chain row to list status recompute.

### CB-12 (B1b-7): A checksums.sha256 that is a symlink (or otherwise refused by open_evidence) makes verify raise IngestError instead of reporting a finding

- **Reproduced:** yes
- **Severity:** robustness (claimed robustness); **class:** 0
- **Where:** src/agentprov/corpus/integrity.py:270-275 (TreeSource.read_checksums), consumed at integrity.py:300 (verify_checksum_source) and src/agentprov/corpus/verify.py:370,379 (_Verifier.checksums)
- **Disposition:** FIXED 051ad3dc
- **Repro:** `~/.agentprov/migration-work/review-core-b/repro/verify-B1b-7/`

**Failing input.** A corpus tree whose checksums.sha256 is a symlink to a file elsewhere (or a FIFO, or larger than STORED_OBJECT_LIMITS).

**Expected.** A structured finding such as `checksums.unreadable` on checksums.sha256 (as for every listed file) in the VerifyReport, with the other levels still reported. root_digest() already maps IngestError to corpus.integrity.unreadable.

**Actual.** TreeSource.read_checksums catches only FileNotFoundError, so verify_checksums and verify_corpus raise IngestError ingest.path.symlink (exit 1) with no report or JSON findings. It fails closed, but the report and the other levels' results are lost.

**Verifier.** I could not disprove it. The input gets through upstream: CorpusReader.open only reads corpus.json to decide whether the tree is sealed, so a sealed tree whose checksums.sha256 is a symlink (pointing to a file with identical bytes) reaches TreeSource. TreeSource.read_checksums (integrity.py:270-275) catches only FileNotFoundError. The IngestError ingest.path.symlink raised by open_evidence is therefore never caught: not in verify_checksum_source (integrity.py:300), and not in _Verifier.checksums (verify.py:370 and 379). No BF-* or F-12C-* item covers it. The SEC-15 rows cover a symlinked raw object, shard directory or execution file, plus an edited, removed or reordered checksums.sha256, but not a symlinked checksums.sha256. It does fail closed (exit 1), so this is not a security bypass. However, the report is lost: corpus is null, issues_by_code is {}, and failures is []. This is inconsistent with root_digest(), which maps the same error to corpus.integrity.unreadable, and with every listed file, which yields checksums.unreadable. The severity "robustness" stands.

**Evidence.** Repro: ~/.agentprov/migration-work/review-core-b/repro/verify-B1b-7/test_repro.py. It uses the corpus_harness `sealed` (mini-mit) and `cli` fixtures. It replaces checksums.sha256 with a symlink to an outside file holding identical bytes. Run with `uv run pytest <repro> -p no:randomly -p no:cacheprovider -q -s --rootdir <dir>`. Output:
API verify_checksums: RAISED IngestError code=ingest.path.symlink
API verify_corpus: RAISED IngestError code=ingest.path.symlink   (level="checksums")
API root_digest: RAISED IntegrityError code=corpus.integrity.unreadable   (the structured path, for contrast)
CLI level=chain: exit=1 ... "corpus":null, "counters":{}, "failures":[], "issues_by_code":{}, notices ["error ingest.path.symlink: ingest.path.symlink: symbolic link in input tree"]
By contrast, a symlinked raw object gives exit 1 with {"checksums.unreadable":1,"corpus.tree.link":1} (test_sec15_deposits.py:111).

**Fix.** Make the checksums read distinguish "absent" from "refused". One option is for read_checksums to return bytes, None, or a refusal code: catch IngestError (exc.code) and OSError (type name) in TreeSource.read_checksums, and do the same in the archive source. In verify_checksum_source, when the read is refused, return ChecksumReport(..., (ChecksumFinding("checksums.unreadable", CHECKSUMS, code),)) and keep the closed-world tree findings. In _Verifier.checksums, reuse the report's bytes instead of calling read_checksums a second time; on a refusal, leave root_digest as None so that a given --root-digest yields root_digest.unverifiable. The identity and chain levels then still run. Add a SEC-15 test for a symlinked or FIFO checksums.sha256 that expects exit 1 with checksums.unreadable.

**Reviewer notes (B1b).** I reviewed corpus/integrity.py, verify.py, derive.py, authority.py, validation.py, validation_job.py, datasheet.py (the escaping is fixed and I found no new variant), package.py (seal) and cli/derive.py. I reproduced all 7 findings with the scripts in ~/.agentprov/migration-work/review-core-b/repro/B1b/ (repro_purge_derive.py, repro_seal_commit.py, repro_views_chain.py, repro_seal_crash.py, repro_gating.py, repro_status_forgery.py, repro_cks_link.py). Scratch corpora are under ~/.agentprov/migration-work/review-core-b/B1b/. I edited nothing in the repository, and no fixture text was printed: the corpora were built through the test helpers seal_support._build and derive_support.agentdojo_corpus.

Routing: finding 1 is in derive.py, which twins/claude-rules-drift owns. It is a different trigger from BF-20 (a working corpus with tombstones, plus tombstones.jsonl and REFERENCES.json never being carried into NEW), so BF-20's fix should cover it. Findings 3, 6 and 7 touch verify.py and integrity.py. Findings 2, 4 and 5 are in package.py (seal).

Checked and not reported:
- The D-430 drift refusal applies only on the CLI path, but verify rederive is a scratch dry run, so that is correct. I found no writing path that bypasses it.
- `version_drift` checks only the catalogue namespaces the source recorded. A namespace that only the current mapper declares would escape the check, but I could not build a concrete case.
- The reuse record miscounts resumed executions as reused. D-30 documents this, so it is not reported.
- `RawRef.included` is always rewritten to True by derive `_entry`. This is latent, because no producer writes False today.
- Case-insensitive APFS path aliases in checksums.sha256 are detected as unlisted.
- The validate pool's `_drop` is safe.
- Compare classes, the explained/upstream logic and the corpus-file deltas look correct.

Not covered: archive mode (archive.py, release/verify), rawtree.py and the remap resume path in depth, and facets.py beyond the completeness rule.

## B2

### CB-13 (B2-1): Release-mode deposit verify never opens an archive that no corpus entry names (orphan archive), and passes a deposit whose corpora list is empty

- **Reproduced:** yes
- **Severity:** security (orphan archive: passes release mode even with --root-digest). The empty-corpora variant alone is robustness: it passes only without --root-digest. (claimed security); **class:** 0
- **Where:** src/agentprov/release/verify.py:286-288 (_Deposit.run: per-corpus loop, no check for unclaimed archives or empty corpora); related: verify.py:229-235 (corpus(): archive/name-prefix cross-check)
- **Disposition:** FIXED a0f1d747
- **Repro:** `~/.agentprov/migration-work/review-core-b/repro/verify-B2-1/`

**Failing input.** A builder-made deposit (one sealed corpus mini-mit 0.1.0). Add mini-mit-v0.1.0.raw.002.zip to the deposit directory, holding members mini-mit-v0.1.0/corpus.json (forged) and mini-mit-v0.1.0/PLANTED.txt. Append it to DEPOSIT-MANIFEST.json archives[] with correct bytes/sha256/md5, corpus_id mini-mit and stage raw, but leave corpora[0].archives unchanged. Separately: set corpora to [].

**Expected.** verify --release (with or without --root-digest) fails. Every archive the deposit lists must belong to exactly one corpus and be opened and checked against that corpus's closed-world checksums.sha256 (H.10.3, D-38). A deposit that verifies no corpus is not 'passed'.

**Actual.** verify_deposit(out, level='chain', release=True, root_digests=[root]) passes, codes {}. Counters show archives 5: the planted archive is hashed against the unanchored deposit manifest but never opened. A user who extracts every zip of the 'verified' deposit gets the forged corpus.json over the sealed one. With corpora: [] and no --root-digest, release mode also passes ({'files_hashed': 9}) although no member of any archive was read.

**Verifier.** I could not disprove the claim. At 7f8f8cb3, _Deposit.files() hashes every file listed in archives[] and documents[] against the deposit manifest, but that manifest is not anchored. Archives are opened (ArchiveSet, members, n_members, members_sha256, stage, closed-world checksums) only in corpus(), and corpus() only reaches the names listed in a corpora[].archives entry. Nothing checks that every archives[] entry is named by exactly one corpus. Nothing checks that corpora[] is non-empty either.

The path is reachable from the CLI (cli/verify.py:195 calls verify_deposit with --release/--root-digest). No existing test covers it: tests/corpus/test_deposit_verify.py and tests/security/test_sec15_deposits.py contain no orphan or empty-corpora case. BF-1..37 and F-12C-* do not cover it. F-12C-01 and the SEC-15 rows cover hostile names, links and unlisted files, not a listed-but-unclaimed archive.

H.10.3(1) and D-38 make each corpus's archive union the closed world of its checksums.sha256 and say "a label in two archives trusts neither". The orphan archive carries a second copy of the corpus.json label, and it still passes with a published --root-digest. That bypasses the only anchor D-39 relies on.

One part of the claim is weaker. The empty-corpora variant passes only without --root-digest. With one, it fails (root_digest.mismatch). Without a root digest the manifest is forgeable anyway, so that variant is a robustness or fail-open gap rather than an anchor bypass.

**Evidence.** The repro is test_repro.py in the scratch directory given under repro_script_path. It builds a deposit from the release_support sealed corpus mini-mit. In the first test it adds mini-mit-v0.1.0.raw.002.zip, holding a forged corpus.json and PLANTED.txt, to the deposit directory and to archives[] with the correct bytes/sha256/md5, plus a bogus n_members of 99 and an all-zero members_sha256. corpora[0].archives is left unchanged. The second test sets corpora to [].

Run with: uv run pytest <repro> -c pyproject.toml --rootdir=. -p no:randomly -p no:cacheprovider -q -s

Output:
BASELINE passed True {} {'files_hashed': 9, 'archives': 5, 'members': 40, 'root_digests_compared': 1}
corpus archives: ['mini-mit-v0.1.0.meta.zip', 'mini-mit-v0.1.0.raw.001.zip', 'mini-mit-v0.1.0.aer.001.zip', 'mini-mit-v0.1.0.prov-agentprov-prov-0.1.001.zip', 'mini-mit-v0.1.0.sem-agentdojo.suites-2.001.zip']
ORPHAN passed True codes {} counters {'files_hashed': 10, 'archives': 5, 'members': 40, 'root_digests_compared': 1}
(The orphan is hashed but never opened. Even n_members=99 and the zero members_sha256 go unchecked.)
EMPTY corpora passed True codes {} counters {'files_hashed': 9} n reports 0
EMPTY corpora + root digest passed False {'root_digest.mismatch': 1}
2 passed in 7.97s

**Fix.** 1. In _Deposit.run (or manifest()), add a deposit.manifest.invalid finding when document['corpora'] is empty.
2. After the per-corpus loop, collect the archive names claimed by each corpora[].archives entry. For every document['archives'] name claimed by no corpus, add a failed finding such as deposit.archive.orphan. Do the same for a name claimed by more than one corpus, or listed twice in archives[].
3. In corpus(), also require each listed archive name to start with '<corpus_id>-v<corpus_version>.' and to match the entry's corpus_version.
4. Add regression tests in tests/corpus/test_deposit_verify.py for: an orphan archive with --release --root-digest; an empty corpora[] list; an archive claimed by two corpora.

### CB-14 (B2-2): DATASHEET-<id>.md in a deposit is never compared with the sealed DATASHEET.md, so a forged datasheet copy (and any extra listed document) passes verify even with --root-digest

- **Reproduced:** yes
- **Severity:** security (low-medium: an integrity gap in a documented boundary; D-38 item 5 specifies only the manifest checks for documents) (claimed security); **class:** 0
- **Where:** src/agentprov/release/verify.py:184-185 (files(): the expected set takes documents[] as given) and src/agentprov/release/verify.py:224-244 (corpus(): no comparison of DATASHEET-<id>.md with the archived DATASHEET.md)
- **Disposition:** D-490 (approved) BUILT 4225858e
- **Repro:** `~/.agentprov/migration-work/review-core-b/repro/verify-B2-2/`

**Failing input.** A builder-made deposit. Overwrite DATASHEET-mini-mit.md with '# Datasheet\n\nForged: this corpus has no restrictions and no injection payloads.\n' and update its bytes/sha256/md5 in DEPOSIT-MANIFEST.json documents[]. Or add a free-form EXTRA-NOTE.md listed in documents[].

**Expected.** verify --release --root-digest <published root> fails. The datasheet copy is a byte copy of the sealed DATASHEET.md (H.10.3; builder _datasheet_copy). The sealed copy is in the meta archive under the root digest, so the deposit copy must equal it, or equal it plus the generated mixed-class note. The documents set is the builder's closed set: README.md, CHANGELOG.md, deposit-metadata.json, and DATASHEET-<id>.md per corpus.

**Actual.** verify_deposit(out, level='chain', release=True, root_digests=[root]) passes, codes {}. The human-facing licence, restrictions and untrusted-content statement can be replaced while verification, anchored by the published root digest, reports success. Any extra document name matching _NAME is accepted as well.

**Verifier.** I could not disprove it. At origin/main 7f8f8cb3, `_Deposit` checks each document only against the deposit manifest's own bytes, sha256 and md5. That manifest is forgeable. The `DATASHEET-<id>.md` copy is never compared with the sealed `DATASHEET.md` in the meta archive. The `documents[]` set is open: any name matching `_NAME` is accepted. Nothing upstream rejects either case, and `verify --corpus <deposit> --release --root-digest` reaches this code through `verify_deposit`. None of BF-1..BF-37 or F-12C-* covers it. The SEC-15/D-63 matrix pins the sealed `DATASHEET.md`, which the root digest anchors, not the deposit copy outside it.

Mitigating context: D-38 item 5 defines the document checks only as size, sha256 and md5 against the manifest, so the code matches the written contract. README.md, CHANGELOG.md and deposit-metadata.json also have no anchor and cannot be checked byte for byte the same way. This is a gap in the specified boundary rather than a deviation from the spec. It is still real and worth fixing, because H.10.3 calls the file a copy, the builder makes a byte copy, and this is the human-facing licence and untrusted-content statement (REP-3) that a reader sees after `--root-digest` reports success.

**Evidence.** Reproduction: `~/.agentprov/migration-work/review-core-b/repro/verify-B2-2/test_repro.py`, run with `uv run pytest ... -p no:randomly -p no:cacheprovider -q -s`.

It builds a deposit with `release_support.build` from a sealed mini-mit corpus. It then overwrites `DATASHEET-mini-mit.md` with a forged text, adds an `EXTRA-NOTE.md`, patches `documents[]` (bytes, md5, sha256) and calls `verify_deposit(level='chain', release=True, root_digests=[root_digest(sealed)])`.

Output:
- `baseline -> passed: True {}`
- `documents: ['CHANGELOG.md', 'DATASHEET-mini-mit.md', 'README.md', 'deposit-metadata.json']`
- `sealed DATASHEET.md == copy: True`
- `forged datasheet copy + extra doc -> passed: True {}`
- control: `wrong root digest -> passed: False {'root_digest.mismatch': 1}`

The builder at `builder.py:656-663` and `:744` makes `DATASHEET-<id>.md` either a byte copy of the sealed `DATASHEET.md`, or (when classes are mixed) `datasheet.rstrip(LF) + LF + note`.

**Fix.** 1. In `_Deposit.manifest()` or `files()`, require `documents[]` names to be exactly {README.md, CHANGELOG.md, deposit-metadata.json} plus DATASHEET-<corpus_id>.md for each `corpora[]` entry. Report any other name as `deposit.manifest.invalid` or `deposit.unlisted`.
2. In `corpus()`, inside the `ArchiveSet` context, read DATASHEET.md through `ArchiveCorpusReader(archives).read_bytes('DATASHEET.md')`. That file is already covered by the archived checksums and the root digest. Compare it with the deposit file `DATASHEET-<corpus_id>.md`:
   - When the manifest's `mixed_licence_classes` is false, require byte equality.
   - When it is true, require that the copy starts with `sealed.rstrip(b'\n') + b'\n'` followed by the builder's note header.
   - On a mismatch, add `deposit.document.datasheet`.
3. Add a SEC-15-style tamper test.
4. Record in D-38/D-39 that README.md, CHANGELOG.md and deposit-metadata.json remain covered only by the deposit manifest.

### CB-15 (B2-3): D-42 relicensing and non-commercial refusals miss valid SPDX ids: GPL-2.0+, LGPL-2.1+, GPL-2.0-with-classpath-exception, 'GPL-3.0-only WITH ...', PolyForm-Noncommercial-1.0.0

- **Reproduced:** yes
- **Severity:** correctness (latent: no shipped profile uses an affected id today) (claimed correctness); **class:** 0
- **Where:** src/agentprov/release/metadata.py:96-97 (_NC, _COPYLEFT), used at :230 (LicenceClass.non_commercial) and :268. Related: src/agentprov/corpus/package.py:346 (redistribution uses the '-NC' substring test).
- **Disposition:** FIXED 6059fccf (release/metadata.py) + 990e2181 (package.py NC predicate; deferrals-c rebases over it)
- **Repro:** `~/.agentprov/migration-work/review-core-b/repro/verify-B2-3/`

**Failing input.** A sealed manifest whose licences.raw[0].spdx is 'GPL-2.0+' (or 'LGPL-2.1+', 'GPL-2.0-with-classpath-exception', 'GPL-3.0-only WITH GCC-exception-3.1'), with derived spdx 'MIT' (user decision) and class {spdx: MIT}. Or a derived/source 'PolyForm-Noncommercial-1.0.0' in a corpus whose id does not end in -nc.

**Expected.** licence_class raises LicenceClassError. D-42 refuses relicensing any GPL/AGPL/LGPL source and admits a non-commercial class only in an -nc corpus with nc_partition. The profile spdx field has no grammar, and spec.py's _SPDX_RE admits '+'.

**Actual.** licence_class(...) returns LicenceClass('MIT', ()) for all four GPL-family ids: 'MIT ACCEPTED'. _COPYLEFT is anchored as ^(A?GPL|LGPL)-[0-9.]+(-only|-or-later)?$, so a '+', '-with-...' or ' WITH ...' suffix escapes it. PolyForm-Noncommercial is not caught by _NC ((^|-)NC(-|$)), so it is treated as commercial and could be mixed. Latent: no shipped profile uses these ids today.

**Verifier.** I could not disprove it. The claim holds at 7f8f8cb3. licence_class is the only D-25/D-42 relicensing guard: corpus/package.py and corpus/spec.py have no copyleft check. spec.py:73 _SPDX_RE admits '+', and the profile [licence].spdx has no grammar, so these ids get through upstream. Neither BF-1..37 nor F-12C-* covers it. Two caveats. (1) It is latent: shipped profiles use only MIT, Apache-2.0, CC-BY-4.0, GPL-3.0, GPL-3.0-or-later and AGPL-3.0-only, and the current regex handles all of them. (2) The proposed fail-closed on ' OR ' is too broad. A dual-licence expression such as 'GPL-2.0-or-later OR MIT' lawfully allows MIT, so refusing it would refuse a valid deposit. Only WITH-exceptions and AND-expressions that contain a copyleft or NC term should force derived == source.

**Evidence.** Script: ~/.agentprov/migration-work/review-core-b/repro/verify-B2-3/repro.py. It builds a minimal manifest (raw spdx = src, derived/class spdx = MIT, policy include, redistribution permitted) and calls agentprov.release.metadata.licence_class. Output:
'GPL-3.0-only' -> refused (release.refused.licence_class)
'GPL-3.0' / 'AGPL-3.0-only' -> refused
'GPL-2.0+' -> derived MIT ACCEPTED LicenceClass(spdx='MIT', restrictions=())
'LGPL-2.1+' -> derived MIT ACCEPTED
'GPL-2.0-with-classpath-exception' -> derived MIT ACCEPTED
'GPL-3.0-only WITH GCC-exception-3.1' -> derived MIT ACCEPTED
'PolyForm-Noncommercial-1.0.0' -> derived MIT ACCEPTED
'CC-BY-NC-4.0' -> refused
derived PolyForm-Noncommercial-1.0.0 spec grammar ok: True -> ACCEPTED in non-nc corpus, non_commercial= False
derived CC-BY-NC-4.0 -> refused release.refused.nc_partition
GPL-2.0+ spec grammar ok: True (corpus/spec.py _SPDX_RE)
Spec: DECISIONS.md:1180 (D-42) refuses relicensing any GPL/AGPL/LGPL source. D_adapters.md:900 says NC artefacts must not be relicensed. The grep found no other relicensing guard in src/agentprov.

**Fix.** Replace the anchored whole-id match with a family test applied to each simple term of the SPDX expression. Split on ' WITH ', ' AND ', ' OR ' and parentheses. A term is copyleft if it matches ^(A?GPL|LGPL)-[0-9], case-insensitive; this covers '+', '-only', '-or-later' and '-with-*-exception'. A term is non-commercial if it matches (^|-)NC(-|$) or 'noncommercial' / 'non-commercial'. Force derived == source when any WITH- or AND-conjunct contains a copyleft or NC term. For a pure OR expression, require derived == source or derived equal to one of the OR alternatives. Do not refuse every OR. Use the same NC predicate in package.py:346 and LicenceClass.non_commercial. Add unit tests for GPL-2.0+, LGPL-2.1+, GPL-2.0-with-classpath-exception, 'GPL-3.0-only WITH GCC-exception-3.1' and PolyForm-Noncommercial-1.0.0.

### CB-16 (B2-4): The home-path / host-name scan of tools/release_scan.py never reads inside compressed raw objects, so the user's home path in a deflated .eval/zip member passes the release scan

- **Reproduced:** yes
- **Severity:** security (claimed security); **class:** 0
- **Where:** tools/release_scan.py:289 (path_scan; _hits at :309; called from scan at :380)
- **Disposition:** D-491 (approved); build after D-450 lands
- **Repro:** `~/.agentprov/migration-work/review-core-b/repro/verify-B2-4/`

**Failing input.** A sealed tree whose raw/objects/<h0h1>/<sha> is an Inspect .eval (zip, DEFLATE) whose header.json holds the user's home path, e.g. '"log_dir": "/Users/<user>/inspect/logs"'. Raw bytes are never edited, so the stored object keeps the path even when the D-182 redaction cleans the AER.

**Expected.** R-51 / G.9.4: 'the script also searches the tree for the user's home path and host name and lists every hit as a finding'. A hit inside a released raw object is a finding that needs triage.

**Actual.** path_scan searches only the stored bytes, and gitleaks runs with --max-archive-depth 0. The deflated member yields no finding, while a plain JSON object with the same path yields one: only 'raw/objects/ab/plain.json home-path line 1' is reported. This is the R-51 detector. D-450 (BF-18, still unmerged) changes only the [withhold]-rule rescan and keeps release_scan at depth 0, so this variant stays open.

**Verifier.** The core claim holds, with one correction. At origin/main 7f8f8cb3, path_scan (tools/release_scan.py:289) and _hits (:309) search only the stored bytes of each file. scan() (:380) runs gitleaks at --max-archive-depth 0 (D-450 keeps it there on purpose), and gitleaks has no home-path rule anyway. So the R-51 home-path / host-name detector never sees a hit inside a zip or a gzip/zstd tar stored under raw/objects/. That path is reachable: HL H.2 stores archive containers as raw/objects/<h2>/<sha>.<ext> inside the sealed corpus, and the release scan walks that tree.

This is not covered elsewhere. BF-18/D-450 (unmerged, on bugpass-perf-10) adds decoded scanning only for [withhold] byte rules: it needs a profile policy and its needles are canaries, not $HOME or the host name. D-454 is about unreadable archives. Neither touches path_scan. F-12C-* does not cover it, and no test exercises an archive in path_scan (tests/unit/release/test_release_scan_tool.py:104 uses plain files only).

Correction to the claim's example: every Inspect profile selects header.json (members = ["header.json", "samples/*_epoch_*.json"]). A selected member is stored decoded as its own raw object, so a home path in header.json IS reported, through that member object. The real gap is members that were not selected and therefore never decompressed (R-40), for example Inspect _journal/start.json, summaries.json and reductions.json, or the unselected files in the geminicli zstd tar and the credleak zip. It also covers any archive stored without a member selection. G.9.4 / G.9.6 say that content-surface home-path hits must be listed and triaged. Instead these pass with no finding, and the deposit builder accepts the scan.

**Evidence.** The repro writes three files under a temp root, all holding the same payload with HOME=/Users/synthetic-reviewer and HOST=synthetic-host.example:
- raw/objects/ab/deflated.eval: a ZIP_DEFLATED archive with member _journal/start.json.
- raw/objects/ab/bundle.tar.gz: a gzip tar with member chats/session.json.
- raw/objects/ab/plain.json: the payload as plain JSON.

The script first asserts that the home-path bytes are absent from both compressed files as stored. It then runs rs.path_scan(root, rs.personal_needles(home=HOME, host=HOST)). Output:
FINDING raw/objects/ab/plain.json home-path 1
FINDING raw/objects/ab/plain.json host-name 1
plain.json reported: True
deflated.eval reported: False
bundle.tar.gz reported: False

**Fix.** Recognise archive objects by their first bytes, not by label: a zip at offset 0, a gzip or zstd tar, and split archives. Only the not_selected members need decoding, because selected members are already scanned as their own objects. Read each archive through the bounded T1 expand path with every member selected and nested archives within max_archive_depth, never extracting to disk. Once D-450 merges, reuse agentprov.corpus.withhold_scan for this. Run the same needle search (rule plus member line) over every decoded member, and report each hit against the archive's label, for example '<label>#<member index>', so the fingerprint stays stable and value-free. An archive that cannot be decoded within the limits becomes an untriaged 'home-path-unscanned' finding, so the scan fails closed. Bump PATH_SCAN_VERSION and add a unit test that puts a deflated member with the home path into the scanned tree.

### CB-17 (B2-5): Release-scan triage is not bound to a root digest: a triage TOML reused for a later corpus version silently triages a new secret at the same path:rule:line

- **Reproduced:** yes
- **Severity:** security (claimed security); **class:** 0
- **Where:** tools/release_scan.py:328 (load_triage, 328-345); binding check belongs in scan(), tools/release_scan.py:375-388
- **Disposition:** FIXED fb74527f
- **Repro:** `~/.agentprov/migration-work/review-core-b/repro/verify-B2-5/`

**Failing input.** Corpus v1: gitleaks reports aer/ab/ex_x.aer.jsonl:generic-api-key:12 (a benchmark fake key), triaged false-positive in triage.toml. Corpus v2 is re-derived after an adapter or redaction change (e.g. a D-31 bump; ex ids are stable). Line 12 of the same AER file now carries a different, real key. Run release_scan.py v2 --triage triage.toml.

**Expected.** D-42: 'triage comes from a reviewed TOML file per fingerprint and per sealed root digest'. A triage decided for v1's bytes does not apply to v2's. The v2 finding is untriaged and the builder refuses (release.refused.scan_untriaged).

**Actual.** load_triage admits only [[triage]] {fingerprint, triage, reason}, with no root digest or content binding. scan_document maps the v2 finding by fingerprint '<path>:<rule>:<line>' to the stale 'false-positive'. check_release_scan accepts it and the deposit is built with the new secret inside. The same applies to any non-content-addressed file (register.jsonl, executions.jsonl, AER/SEM/PROV, DATASHEET.md).

**Verifier.** I could not disprove the claim. load_triage (tools/release_scan.py:328-345) accepts only top-level [[triage]] tables. It rejects a root_digest key ("the triage file holds [[triage]] tables only"), so the format has no way to bind a triage file to a sealed root digest. scan_document (348-359) maps findings by '<path>:<rule>:<line>' alone. check_release_scan (src/agentprov/release/metadata.py:329-371) binds the scan document to the root digest, but not the triage decisions inside it. D-42 (DECISIONS.md, around line 1189) says that "triage comes from a reviewed TOML file per fingerprint and per sealed root digest". The code implements only the per-fingerprint part.

The release-scan.json root binding is real, but it only shows the scan ran on the new bytes. It does not show the triage was reviewed for those bytes. Neither BF-1..37 nor F-12C-* covers this; BF-18 is about archive members, not triage binding.

Two things limit the impact. First, triage is a human-authored input, so an operator can always mis-triage, and a binding only forces a deliberate re-review. Second, the failing case needs a new secret at exactly the same path, rule and line. That is plausible, though: AER, SEM and PROV paths are stable across a D-31 re-derive, and so are register.jsonl, executions.jsonl and DATASHEET.md. I am keeping the severity at security (low-medium: a process-control bypass, not a remote one).

**Evidence.** The script is ~/.agentprov/migration-work/review-core-b/repro/verify-B2-5/repro.py, run with `uv run python` from the worktree. It imports tools/release_scan.py, loads a triage TOML written for v1, then builds scan documents for two different root digests (v1 is sha256:0..0, v2 is sha256:1..1), each with the same finding aer/ab/ex_x.aer.jsonl:generic-api-key:12. Output:
  root_digest key rejected: the triage file holds [[triage]] tables only
  v1 finding triage: false-positive | summary: {'by_triage': {'false-positive': 1}, 'findings': 1}
  v1 builder check accepted: {'false-positive': 1}
  v2 finding triage: false-positive | summary: {'by_triage': {'false-positive': 1}, 'findings': 1}
  v2 builder check accepted: {'false-positive': 1}
So the v1 triage silently applies to v2's different bytes, and agentprov.release.metadata.check_release_scan accepts it (no release.refused.scan_untriaged). The format also gives no way to declare a root digest in the triage file.

**Fix.** Require a top-level `root_digest = "sha256:<64 hex>"` in the triage TOML, and have load_triage return it. In scan() (or main()), compare it with corpus_target(root)['root_digest'] and exit 2 with a clear message when they differ, so each sealed version needs its own reviewed triage file. Optionally record the triage file's sha256 and root digest in the release-scan.json `tools`/`triage` metadata so the builder can check it as well. An optional convenience is to carry entries forward automatically only for content-addressed paths (raw/objects/**). Add a test: a triage file for digest A run against a corpus with digest B exits 2 and leaves no triaged rows. Updating the docstring and G.9.4 to describe the binding changes no stored corpus bytes.

### CB-18 (B2-6): Seal mode accepts an impossible --release-date (2026-02-30, 2026-13-45, 0000-00-00) and writes it as release.created of a sealed corpus; the manifest validator is regex-only

- **Reproduced:** yes
- **Severity:** correctness (claimed correctness); **class:** 0
- **Where:** src/agentprov/corpus/package.py:138-145 (ReleaseArgs.to_json); also src/agentprov/cli/package.py:247-248 and src/agentprov/corpus/manifest.py:328
- **Disposition:** FIXED e5011f19 (CLI) + be46b138 (ReleaseArgs/manifest backstop, ASCII epoch)
- **Repro:** `~/.agentprov/migration-work/review-core-b/repro/verify-B2-6/`

**Failing input.** agentprov package --corpus DIR --corpus-version 0.1.0 --release-date 2026-02-30

**Expected.** Exit 2, '--release-date is YYYY-MM-DD', as the deposit mode does (cli/deposit.py _release_date uses date.fromisoformat). A sealed corpus never records an invented or invalid timestamp (invariant 2; H.2.13).

**Actual.** ReleaseArgs.to_json checks only [0-9]{4}-[0-9]{2}-[0-9]{2}, so created becomes '2026-02-30T00:00:00Z'. validate_manifest checks release.created only against the RFC3339_UTC regex and accepts it, and the same string reaches the withholding plan via _release_date. The corpus seals with an impossible date, and package --deposit then refuses the same date for that corpus. Also, a large SOURCE_DATE_EPOCH (e.g. 10**12) raises an uncaught ValueError (year 33658), an internal error rather than exit 2.

**Verifier.** I could not disprove the claim. Nothing upstream rejects the input. cli/package.py:88 declares --release-date as a plain string. cli/package.py:247-248 passes it straight to ReleaseArgs. The only check is the regex in ReleaseArgs.to_json at corpus/package.py:138-140. manifest.py:328 validates release.created only as Nullable(Str(RFC3339_UTC)), and the only semantic check on it (manifest.py:594) is the dev/null rule. Neither the BF-1..BF-37 bug pass nor sec-coverage-12c mentions release dates. The expected behaviour is what the spec asks for: HL_corpus_versioning.md:579 requires created to be an RFC 3339 UTC string, and RFC 3339 does not allow day 30 in February, month 13 or month 00. A related variant on the same lines: a value that fails the regex (for example --release-date 2026/10/12) also raises a bare ValueError. exit_code_for maps a non-AgentProvError to 70, so the CLI prints 'internal error' instead of exiting 2. The large SOURCE_DATE_EPOCH case can be reached because cli/package.py:248 only checks epoch.isdigit().

**Evidence.** The repro is a pytest file that builds the seal_support working corpus and calls seal(..., release=ReleaseArgs(release_date=bad)). Output:
SEALED 2026-02-30 root_digest True created= 2026-02-30T00:00:00Z validate_manifest issues= []
DEPOSIT refuses 2026-02-30
SEALED 2026-13-45 root_digest True created= 2026-13-45T00:00:00Z validate_manifest issues= []
DEPOSIT refuses 2026-13-45
SEALED 0000-00-00 root_digest True created= 0000-00-00T00:00:00Z validate_manifest issues= []
DEPOSIT refuses 0000-00-00
EPOCH ValueError: year must be in 1..9999, not 33658
4 passed in 10.60s
So each corpus is really sealed (root_digest written) with an impossible created value, validate_manifest returns no issues, and cli/deposit._release_date raises CliUsageError for the same string. ReleaseArgs(source_date_epoch=10**12).to_json() raises a bare ValueError, which main._result_from_exception reports as internal error exit 70.

**Fix.** 1. In cli/package.py, validate args.release_date before building ReleaseArgs, using the same helper as deposit mode (regex plus date.fromisoformat). Raise CliUsageError('agentprov package: --release-date is YYYY-MM-DD') so the exit code is 2. This covers bad formats as well as impossible dates.
2. In cli/package.py, bound SOURCE_DATE_EPOCH to the range datetime accepts (up to 253402300799) and raise CliUsageError when it is out of range.
3. As a backstop, ReleaseArgs.to_json should also call date.fromisoformat(release_date) after the regex.
4. In manifest.py validate_manifest, add a semantic issue for /release/created when datetime.fromisoformat(created.replace('Z', '+00:00')) fails.
5. Add unit tests for 2026-02-30 and for SOURCE_DATE_EPOCH=10**12.

### CB-19 (B2-7): package --deposit with a release date after 2107 passes every check (and --dry-run), then crashes with struct.error while writing the first archive (exit 70)

- **Reproduced:** yes
- **Severity:** robustness (claimed robustness); **class:** 0
- **Where:** src/agentprov/release/builder.py:226 (archive_date_time has no upper bound); the check belongs in build_deposit at builder.py:704-711, before _check_out. Mirror it in src/agentprov/cli/deposit.py:32-40 (_release_date).
- **Disposition:** FIXED 264e8a07 (CLI); builder backstop ROUTED to the bug pass (release/builder.py)
- **Repro:** `~/.agentprov/migration-work/review-core-b/repro/verify-B2-7/`

**Failing input.** agentprov package --deposit OUT --corpus SEALED --metadata release.toml --release-date 2108-01-01

**Expected.** A usage refusal (exit 2) before any corpus is verified. ZIP dates cover 1980..2107. archive_date_time clamps the low end, so the high end is either refused or documented.

**Actual.** _release_date and archive_date_time accept 2108. The chain verification and planning run, and --dry-run reports success. The real build then fails inside zipfile's FileHeader: "error: 'H' format requires 0 <= number <= 65535". This is an internal error (exit 70) after the full verification cost, with the partial draft removed.

**Verifier.** I could not disprove it. The input gets through every layer: cli/deposit.py:32-40 _release_date only checks that the text matches YYYY-MM-DD and that date.fromisoformat accepts it. build_deposit (builder.py:704-735) checks only the corpora list and max_archive_bytes, then verifies and plans. archive_date_time (builder.py:226-230) clamps the low end only. The defect is not in BF-1..BF-37 or F-12C-*. The spec (HL_corpus_versioning.md:1617, DECISIONS.md:1194) states only the 1980 clamp and says nothing about the upper ZIP limit. No existing test covers it; test_builder.py:139 tests only the low clamp. Impact is small because a release date after 2107 is unlikely in practice. It is still an unclassified internal error (exit 70), raised after the full verify and scan cost, where a usage refusal is expected.

**Evidence.** The repro is scratchpad/review/verify-B2-7/test_repro.py. It uses tests/unit/release/release_support.py to make a sealed mini-mit corpus and calls build_deposit through rs.build. Output at origin/main 7f8f8cb3:
cli _release_date('2108-01-01') -> 2108-01-01
archive_date_time -> (2108, 1, 1, 0, 0, 0)
dry_run ok: True ['mini-mit-v0.1.0.meta.zip', ...5 archives]
2107-12-31 real build ok: [...]   (so the boundary is exactly 2107)
real build raised: struct error 'H' format requires 0 <= number <= 65535
exit_code_for: 70
out exists: False partial exists: False
1 passed in 14.15s
So --dry-run reports success for 2108-01-01, while the real build fails inside zipfile with struct.error. cli.common.exit_code_for maps that to 70 (internal error). The partial directory is removed.

**Fix.** At the top of build_deposit, next to the other usage checks, add: if release_date.year > 2107: raise DepositRefusedError("--release-date is at most 2107-12-31 (ZIP timestamps)", code="release.usage", exit_code=2). Do this before _check_out or any verify, so --dry-run refuses too. Add the same bound to cli/deposit.py _release_date (CliUsageError). Document the 1980..2107 range, with the low end clamped and the high end refused, in HL H.10.4 / DECISIONS. Add a test next to test_the_release_date_sets_member_timestamps_clamped_to_1980 asserting a 2108-01-01 build and dry run both exit 2 and write nothing.

**Reviewer notes (B2).** Area B2 (release), reviewed at 7f8f8cb3. No repository file was modified. Scratch repros are in ~/.agentprov/migration-work/review-core-b/repro/B2/: test_b2_orphan.py, test_b2_docs.py, r2_date.py, r3_lic.py, r4_pathscan.py. Scratch pytest basetemps are under ~/.agentprov/migration-work/review-core-b/ (bt1, bt2). The two pytest repros were run with `uv run pytest <file> -c pyproject.toml --rootdir=. -p no:randomly -p no:cacheprovider -s` from the worktree. They build the sealed test corpus through tests/unit/release/release_support (fixture bytes are loaded programmatically and never printed).

Checked and found sound:
- Network: src/agentprov/release/ imports no network or process module, and nothing calls upload or publish. cli/deposit.py only calls git_facts (a subprocess in the CLI layer, as specified).
- Refusals: unsealed or partial trees, advisory, test_only, non-strict validation, withhold snapshot without WITHHELD.json, raw_policy withhold or forbidden, mixed classes, -nc mixing, views/ (exit 5), missing/stale/untriaged/real scan, the D-236 backstop, and interpreter floor 3.14.8 all refuse before anything is written.
- The "real finding admitted when WITHHELD names its fingerprint" exemption cannot collide: rule ids have no ':', so the exemption is effectively dead (fail closed).
- Error and CLI output goes through safe_text. The deposit manifest and metadata record no local path and no matched value.
- Archive bytes are deterministic: sorted members, fixed date_time, attributes and level, no data descriptor on a seekable file, no ZIP64. Member names are '<id>-v<ver>/<grammar label>'.
- The overlap check and the never-rewrite rule hold for OUT.

Known items not re-reported: BF-18 (decoded withhold rescan) and BF-19 (chain container closure). Finding 4 is the home-path detector variant, which D-450 does not touch. Finding 5 was reasoned from code and D-42's wording and was not run end to end. All findings are byte class 0: release/, tools/ and corpus/package.py/verify.py are in no stage digest, and the fixes only refuse inputs that are invalid today. Not covered: gitleaks' own file-skipping behaviour (no binary or network to test offline), and the stats field_groups table escaping (F-12C-04 scope).

## B3

### CB-20 (B3-1): Archive input: the stored container is never checked against the verified pin digest (TOCTOU between verify and copy); the pinned zenodo/hf origin is recorded for bytes the pin does not vouch for

- **Reproduced:** yes
- **Severity:** security (integrity; low exploitability: needs write access to the input/cache file during the verify-to-copy window) (claimed security); **class:** 1
- **Where:** src/agentprov/adapters/runner/importer.py:1026 and 1031 (single-file archive input); 1041-1043 (split parts, which check only after storing); the root cause is src/agentprov/corpus/writer.py:163-168 (add_object exposes no expected digest)
- **Disposition:** CLASS 1: regen-batch item 58 (approved; after D-414 lands)
- **Repro:** `~/.agentprov/migration-work/review-core-b/repro/verify-B3-1/`

**Failing input.** import --input deposit.zip --verify-against-pin (or --fetch from the cache): verify_download / Fetcher._fetch_http hash the file, then the file is replaced by other bytes of the same size before ArchiveTree.archive_members copies it into the raw store

**Expected.** The copy is refused (raw.object.mismatch / raw.digest.mismatch) because the streamed bytes do not hash to ArchiveTree.sha256 (the verified pin digest); nothing is stored or given the pinned origin

**Actual.** No refusal: import_source returns with no failures; raw/objects holds the container under the NEW digest (921729fa... in the repro, pin is 3abd5db5...) and raw/origins.jsonl has a zenodo origin row (the pinned DOI/file) for it. ArchiveTree.sha256/size are carried but never compared; corpus.add_object -> store.put_stream is called without expected_sha256/expected_size. origin_matches_pin compares DOI/file only, so later checks do not notice either. The split-parts path (line 1043) compares only after add_object has already stored the object and recorded the pinned origin.

**Verifier.** I could not disprove this claim. At 7f8f8cb3, ArchiveTree carries the verified sha256 and size, but nothing compares them with the bytes that are actually stored. _Pipeline.archive_members (importer.py:1024-1031) calls CorpusWriter.add_object(handle, container.origin). add_object (corpus/writer.py:167) calls store.put_stream with no expected_sha256 or expected_size, then records the pinned origin under whatever digest came out. put_stream already supports expected_sha256 and expected_size (raw/store.py:422-432); they are just not passed.

The path is reachable from real callers. cli/import_.py:_archive_input (lines 515-519) runs verify_download on one open handle, closes it, and builds an ArchiveTree from the path. ArchiveTree.stream then reopens the file by name. The --fetch path (line 418) works the same way on the cache file.

No later check catches the mismatch:
- origin_matches_pin compares only DOI and file.
- rawtree.StoredTree only checks that snapshot.input.sha256 is a stored object.
- Nothing compares snapshot.origin.sha256 (the pin) with snapshot.input.sha256 (what was stored).

BF-15 and BF-19 concern split-part limits and the closure of withheld members, not this.

Caveats:
1. Exploiting it needs write access to the input or cache file during the window between verification and copy. That makes it a local race, though a concurrent re-fetch or edit could also trigger it by accident.
2. The split-parts path (line 1043) does detect a mismatch, but only after add_object has stored the part and recorded its pinned origin. The run aborts, so that variant is lower impact.

**Evidence.** The repro is ~/.agentprov/migration-work/review-core-b/repro/verify-B3-1/repro.py. Its scratch data is in ~/.agentprov/migration-work/review-core-b/verify-B3-1/run.

What it does:
1. Builds two STORED zips of the same size: good and bad (147 bytes each).
2. Pins sha256(good).
3. Builds ArchiveTree(sha256=pin, size=pin).
4. Overwrites the file with bad.
5. Runs import_source('foobench', ..., in_process=True).

Output:
- verified sha (pin): 484b214f4f346739
- exit_code: 0, failures: []
- zenodo origin rows: [('sha256:bf59d0b1e37834ff', '10.5281/zenodo.7')]
- stored sha == bad: True
- stored sha == pin: False

The c.partial/corpus.json snapshot ends up inconsistent with itself, and nothing flagged it:
- origin.sha256 = sha256:484b214f... (the pin)
- input.sha256 = sha256:bf59d0b1... (what was stored)
- pin.sha256 = 484b214f...

Class 1 is confirmed: importer.py:1969 puts adapters/runner in the aer stage's engine_code_sha256 scope. Honest inputs would store identical object bytes.

**Fix.** 1. Add expected_sha256 and expected_size keyword arguments to CorpusWriter.add_object and forward them to store.put_stream / store.put, which raise before publishing and before origins.add.
2. In archive_members, pass expected_sha256=self.tree.sha256 and expected_size=self.tree.size on both the stream branch and the bytes branch.
3. In _split_members, pass expected_sha256=part.sha256 and expected_size=part.size so the mismatch is refused before the part is stored and its pinned origin is recorded, then drop the post-hoc compare.
4. Optionally, have seal/validate assert snapshot.input.sha256 == snapshot.origin.sha256 for non-split archive inputs.

Add a regression test that swaps the file after the ArchiveTree is built and expects raw.digest.mismatch with no zenodo origin row.

### CB-21 (B3-2): U-07 large-download consent is bypassed when a download pin has no pinned size and the server sends no Content-Length

- **Reproduced:** yes
- **Severity:** robustness (claimed security); **class:** 0
- **Where:** src/agentprov/raw/fetch.py:1392 (pre-check on pinned size only), 1419-1427 (Content-Length check), 1430-1433 (read loop checks only cap); plan() at 1099-1102
- **Disposition:** FIXED 97274bee
- **Repro:** `~/.agentprov/migration-work/review-core-b/repro/verify-B3-2/`

**Failing input.** A zenodo/hf/url pin with sha256 (or md5) but no `bytes`, served chunked (no Content-Length); fetch with --allow-network and without --i-consent-to-large-download

**Expected.** Refused with LargeDownloadRefusedError (raw.fetch.consent_required, exit 4) before or once the stream reaches LARGE_DOWNLOAD_BYTES, as require_split_consent already does for an unsized part ('A part without a pinned size counts as large')

**Actual.** The consent check runs only on the pinned size and on a declared Content-Length; the streaming loop checks only cap = max_artefact_bytes (2 GiB), so up to 2 GiB is downloaded without consent. plan().large is also False for such a pin. Latent for the shipped profiles (every current single download pin has a size; a url pin needs only sha256).

**Verifier.** I could not disprove the defect. At origin/main 7f8f8cb3, _fetch_http checks U-07 consent in only two places: the pinned size (recipe.size, line 1392) and a numeric Content-Length (lines 1419-1427). The read loop (lines 1430-1436) checks only cap. That cap is max_artefact_bytes when the pin has no size. Recipe.from_pin accepts a download pin with only sha256 or md5 (MN_repo_cli N, item 4). So a pin without a size, served without Content-Length (chunked), downloads past LARGE_DOWNLOAD_BYTES without consent. plan() also reports large=False for that pin.

The path is reachable from real callers. cli/fetch.py:184 and cli/import_.py:358 pass the flag straight to Fetcher, and no caller checks first for a single pin; require_split_consent runs only for split archives. Neither BF-1..37 nor F-12C-* covers this. The existing tests cover only a pinned size and a declared Content-Length (tests/unit/raw/test_fetch.py:727-749).

The spec text (MN item 3: "by the pinned size or the announced Content-Length") describes how size is measured. The module docstring ("A download of LARGE_DOWNLOAD_BYTES or more needs the explicit large download consent") and D-249's rule for split parts ("A part without a pinned size counts as large") show the intent: a download that ends up at 100 MiB or more is still covered.

Two corrections to the claim. First, the defect is latent: every shipped single download pin has `bytes`. Second, the download stays bounded by max_artefact_bytes, and the digests are still checked. So this is a gap in the user-consent policy, not an attacker-reachable exploit; I downgrade the severity from security to robustness.

**Evidence.** Script: ~/.agentprov/migration-work/review-core-b/repro/verify-B3-2/repro.py. It sets LARGE_DOWNLOAD_BYTES=1000 and uses a stub transport: status 200, headers {}, 4096-byte body. The pin is zenodo with sha256 only. The cache is under ~/.agentprov/migration-work/review-core-b/verify-B3-2 and is removed afterwards.
Output:
recipe.size = None
plan.large = False
sized pin: refused raw.fetch.consent_required        (control: same body with bytes pinned is refused)
unsized, no Content-Length, no consent: bytes = 4096 network_used = True > threshold: True
split of unsized parts: refused raw.fetch.consent_required   (require_split_consent treats an unsized part as large; single-pin path does not)

**Fix.** Make the rule match require_split_consent (D-249). In _fetch_http, without large_download_consent, refuse with LargeDownloadRefusedError in either case: (a) recipe.size is None and no numeric Content-Length was announced, before reading; or (b), the minimum fix, in the read loop once count >= LARGE_DOWNLOAD_BYTES, removing the .part file through the existing except path. Make plan().large true when size is None for an HTTP pin. Add a test with FakeTransport (headers {}), zenodo_recipe(bytes=None) and LARGE_DOWNLOAD_BYTES monkeypatched to 5 that expects LargeDownloadRefusedError and an empty cache. Update MN_repo_cli item 3 to say that a download with no pinned size and no announced length also needs consent.

### CB-22 (B3-3): One hostile archive aborts the whole expand call: identical inner-archive bytes reached at two levels with different selections raise MembersConflictError out of expand_containers

- **Reproduced:** yes
- **Severity:** robustness (claimed robustness); **class:** 1
- **Where:** src/agentprov/raw/members.py:1055-1057 (expand_containers; reached from adapters/runner/importer.py:1034/1054 -> 1059 via corpus/writer.py:191)
- **Disposition:** CLASS 1: regen-batch item 59 (approved; held branch review-core-b-regen)
- **Repro:** `~/.agentprov/migration-work/review-core-b/repro/verify-B3-3/`

**Failing input.** outer.zip = {x.zip (inner), y.zip = {x.zip (same bytes)}, ok.json}; ContainerSpec(outer, selections=(Selection(include=('*.json',), nested=('*.zip',)), same at level 2)); another innocent container in the same call. Same shape with D-382 declared nested archives whose patterns both match x.zip at two levels.

**Expected.** The second reach of the container is recorded as a register event (e.g. expand.failed / raw.members.conflict for that subject) and skipped; other containers and members keep their outcome (the docstring: a structural defect rejects that container)

**Actual.** MembersConflictError ('one container is reached with two different selections') propagates out of expand_containers before the depth check, so the outcome of every container in the call (including the innocent one) is lost and the import aborts; member objects already put stay in the store without origin rows.

**Verifier.** The defect is real, but the claim overstates its reach. In real callers the "innocent container in the same call" loss cannot happen. The archive-input path (importer.archive_members / _split_members) passes exactly one ContainerSpec. map_containers batches several specs, but each has the single selection Selection(include=member_patterns), which has no `nested` and no `children`, so it never reaches a container twice with two fns. The per-level `selections=(s1, s1)` shape from the claim exists only at the API level. The reachable trigger is D-382 `[import] nested` with an `under` chain (two declared nesting levels), built by importer.archive_selection() -> nested_selection(). There a hostile or merely duplicated inner archive appears both at a level-A position and at a level-B position. That aborts the whole archive import with raw.members.conflict instead of registering that one reach. Even without the bug, a rejected archive input fails the run, so the real loss is this: the register entry is missing, and every other member of the archive is not imported. No shipped profile declares `[import] nested` yet. The controlarena-persistent profile only mentions it in comments, and those comments note that real deposits do contain byte-duplicate nested zips, so this is a latent defect in an implemented and tested feature. The existing test tests/unit/raw/test_members.py::test_two_different_selections_for_one_container_conflict pins the raise only for a caller-supplied root spec that overlaps a nested reach, which is API misuse. Neither BF-1..37 nor F-12C-* covers the content-driven case.

**Evidence.** Repro: ~/.agentprov/migration-work/review-core-b/repro/verify-B3-3/repro.py (run with uv run python at origin/main 7f8f8cb3, in-process WorkerPool, scratch store under ~/.agentprov/migration-work/review-core-b/verify-B3-3, cleaned up after the run).
Case 1 (real caller shape): sel = nested_selection(("*.json",), [{id:A, pattern:"*.zip"}, {id:B, pattern:"inner/*.zip", under:A, max_depth:3}]). outer.zip = {x.zip, y.zip={inner/x.zip (same bytes as x.zip)}, ok.json}, and the call is ContainerSpec(outer,"s","outer.zip",(sel,),prefixed=True), the same call importer.archive_members makes.
Output: "D-382 single archive input: RAISED MembersConflictError raw.members.conflict one container is reached with two different selections | objects in store: 5". That is 4 member objects put with no origin rows returned.
Control (same profile, no duplicate bytes): "OK containers= 4 events= []".
Case 2 (claim's exact per-level shape plus an innocent container): "claim exact shape+innocent: RAISED MembersConflictError raw.members.conflict ...". A variant where y.zip holds inner/x.zip (so '*.zip' does not cross '/') expands normally.
Mechanism: members.py:1055-1057. x.zip opens at depth 2 with fn(SA) and is recorded in `done`. At depth 3 it is reached again with fn(SB), or with Selection() in the per-level case. Then `raise MembersConflictError` runs, which propagates through CorpusWriter.expand (writer.py:191) and importer._expand_archive (importer.py:1059), out of discover() and the run, so no register entry is written. raw/members.py is in EXPAND_MODULES (members.py:121-130), so any fix changes the expand engine_code_sha256: class 1.

**Fix.** In expand_containers, keep the raise only when two caller-supplied root specs conflict (API misuse; this keeps test_two_different_selections_for_one_container_conflict meaningful, or that test should be adjusted on purpose). When a nested reach (depth > its spec's root depth, i.e. a ContainerSpec created by _consume from archive content) finds spec.sha256 already in `done` with a different fn, append ExpandEvent(spec.snapshot_id, path, "raw.members.conflict", "expand", "error", "not_imported", violation_detail(container=spec.sha256, reason="nested archive already expanded with another selection")) and `continue`. Members.jsonl keeps one expansion per container, and the rest of the archive imports. Add a test using nested_selection with an `under` chain and duplicated inner bytes. Class 1: raw/members.py is in EXPAND_MODULES, so the expand engine_code_sha256 / stage identity changes.

### CB-23 (B3-4): History index: a far-future committer date crashes fetch --history with an untyped ValueError

- **Reproduced:** yes
- **Severity:** robustness (claimed robustness); **class:** 0
- **Where:** src/agentprov/raw/history.py:65 (_MAX_EPOCH = 1 << 40) and :78-80 (rfc3339_utc); surfaced via src/agentprov/cli/fetch.py:265
- **Disposition:** FIXED e9551d4f
- **Repro:** `~/.agentprov/migration-work/review-core-b/repro/verify-B3-4/`

**Failing input.** An upstream commit (accepted by transfer.fsckObjects) whose committer timestamp is between 253402300800 (year 10000) and 2**40, introducing a blob of the pinned tree; then `agentprov fetch --profile P --history --allow-network`

**Expected.** HistoryError raw.history.date (the range check's own code), reported per recipe by _fetch_history

**Actual.** rfc3339_utc's guard is `0 <= epoch < 1<<40`, but datetime.fromtimestamp raises ValueError ('year must be in 1..9999, not 10000') above 253402300799; cli/fetch.py:265 catches only AgentProvError, so the whole fetch command dies with a traceback and later recipes are not processed

**Verifier.** I could not disprove the claim. At origin/main 7f8f8cb3, `rfc3339_utc` checks `0 <= epoch < 1<<40`. `datetime.fromtimestamp` has a lower ceiling: it raises a bare ValueError for any epoch of 253402300800 or more (year 10000 and later). The input gets through every upstream check:
- `parse_history_log` only requires the epoch to be all digits.
- Git accepts the commit: `GIT_COMMITTER_DATE=@253402300800` works and `git fsck --strict` exits 0.
- The real `Fetcher.fetch_history` path (file protocol, real git) raises the ValueError.

The CLI wording in the claim needs one correction. `cli/fetch.py` `_fetch_history` catches only AgentProvError, so the ValueError escapes. The top-level handler in `cli/main.py` (`_result_from_exception`) then catches it. The user sees `agentprov: internal error: ValueError: ... (exit 70)` rather than a raw traceback. The substance holds: there is no typed `raw.history.date` error, the recipe's failure is not reported per recipe, and the remaining recipes are not processed. The `finally` block in `fetch_history` still writes the acquisitions row.

Neither the BF-1..BF-37 list nor the F-12C findings cover this. The existing test, `tests/unit/raw/test_history.py::test_dates_are_utc_seconds_and_range_checked`, only probes -1 and 1<<41. Both fall outside the guard, so the gap between the datetime limit and 2**40 is untested.

**Evidence.** The script is `~/.agentprov/migration-work/review-core-b/repro/verify-B3-4/repro.py`. Its scratch git repo is in `~/.agentprov/migration-work/review-core-b/verify-B3-4`. Run with `uv run python`, it printed:

```
rfc3339_utc 253402300799 -> 9999-12-31T23:59:59Z
rfc3339_utc 253402300800 -> UNTYPED ValueError year must be in 1..9999, not 10000
rfc3339_utc 1099511627775 -> UNTYPED ValueError year must be in 1..9999, not 36812
git log %ct: 253402300800
git fsck: 0
fetch_history -> UNTYPED (escapes cli/fetch.py _fetch_history) ValueError year must be in 1..9999, not 10000
```

The code path: `Fetcher._compute_history_index` (`raw/fetch.py` ~1374-1380) calls `build_index`. `build_index` calls `rfc3339_utc` (`history.py:300`; `build_full_index` at `history.py:366` is also affected), which raises ValueError at `history.py:80`. `cli/fetch.py:265` has `except AgentProvError`, which does not match, and the exception reaches `cli/main.py:235`, which turns it into an exit-70 internal error.

**Fix.** In `history.py`, set `_MAX_EPOCH` to 253402300800, i.e. `int(datetime(9999,12,31,23,59,59,tzinfo=UTC).timestamp()) + 1`. An alternative is to wrap `datetime.fromtimestamp` in `try/except (ValueError, OverflowError, OSError)` and raise `HistoryError('a commit timestamp is out of range', code='raw.history.date')`. Then add 253402300800 to the bad values in `test_dates_are_utc_seconds_and_range_checked`. With this change the CLI reports the failure per recipe and carries on with the remaining recipes.

### CB-24 (B3-5): REFERENCES.json git origins never resolve against a pin whose tree is a directory without a trailing slash

- **Reproduced:** yes
- **Severity:** correctness (claimed correctness); **class:** 0
- **Where:** src/agentprov/raw/references.py:143 (_git_match)
- **Disposition:** FIXED 9ccba6f6
- **Repro:** `~/.agentprov/migration-work/review-core-b/repro/verify-B3-5/`

**Failing input.** Pin {kind: git, repo: R, commit: C, tree: 'logs'} (as shipped by atia-benchmark, kexin-xu-01-agentharm, survey-runs, survey-agentharm, whistlebench, adprov-v1); a REFERENCES.json object with origin {kind: git, repo: R, commit: C, path: 'logs/run1.eval', blob_sha1: ...}

**Expected.** resolved: git ls-tree treats the pin's 'logs' as a directory pathspec and Fetcher.git_tree lists logs/run1.eval under that pin

**Actual.** unpinned: _git_match requires path == 'logs' unless the prefix ends with '/', so verify reports raw.reference.unpinned_origin and `agentprov fetch --corpus` refuses the reference; the same reference resolves when the pin says 'logs/'

**Verifier.** I tried to disprove the claim and could not. The code path exists at origin/main and real callers reach it: `corpus/verify.py` (`references()`, line ~655, builds recipes from the corpus's source tables through `recipes_from_source`) and `cli/fetch.py` `_fetch_references` (line ~325, using `_all_recipes()`). `Recipe.from_pin` (`raw/fetch.py:490-491`) copies the pin's `tree` into `paths` exactly as written, so 'logs' keeps no trailing slash. Nothing upstream normalises it. The spec (MN_repo_cli.md:2241, 'a path inside the pin's prefix') and the git_tree semantics (`raw/fetch.py:1165-1167` passes paths as a git pathspec) both treat 'logs' as a directory prefix, so the expected 'resolved' is correct. The existing tests only use 'runs/' or exact file paths (`tests/unit/raw/test_references.py:124-134`), so a slashless directory pin is never covered. BF-1..37 and F-12C-* do not cover it either. F-12C-01 is about forged references passing, which is the opposite problem.

**Evidence.** I ran `uv run python .../verify-B3-5/repro.py` against the real atia-benchmark profile's `[source]` table, parsed with tomllib and passed through `recipes_from_source`. Output:
real atia pin recipe paths: ('logs',) repo: https://github.com/mattngyn/atia_benchmark commit: cc71caf5
real atia pin, path logs/run1.eval -> unpinned
tree='logs'   -> unpinned
tree='logs/'  -> resolved
path='logsX/run1.eval'    tree='logs' -> unpinned
path='other/run1.eval'    tree='logs' -> unpinned
path='logs'               tree='logs' -> resolved
I checked git's pathspec behaviour on a scratch repo with `logs/run1.eval` and a sibling file `logsX`. `git ls-tree -r --full-tree HEAD -- logs` lists only `logs/run1.eval`, so the pin covers that blob and verify_reference's narrowed git_tree would find it. Shipped profiles with a slashless directory tree: atia-benchmark ('logs'), kexin-xu-01-agentharm ('logs'), whistlebench ('final_runs'), survey-runs ('agentdojo'), survey-agentharm ('agentharm/results') and adprov-v1 ('corpus/corpus-prov', 'corpus/corpus-og-agentdojo-runs-prov'). For any of these, a valid REFERENCES.json git origin is reported raw.reference.unpinned_origin by `verify` and refused by `fetch --corpus`.

**Fix.** In _git_match, match each pin path p as a git pathspec prefix: `path == p.rstrip('/') or path.startswith(p.rstrip('/') + '/')`. This keeps the rejection of sibling lookalikes such as 'logsX/...'. Add a test with paths=('runs',) and origin path 'runs/x.json' (resolved), plus 'runsX/x.json' (unpinned).

### CB-25 (B3-6): git fetch follows HTTP redirects to any host and downgrades https to http (no protocol/redirect restriction in _hardening)

- **Reproduced:** yes
- **Severity:** security (hardening gap; low impact: content integrity still rests on the pinned SHA-1 commit, fsck and the blob SHA-1 checks, so the risk is unconsented contact with a host outside the recipe and a cleartext transfer, not content forgery) (claimed security); **class:** 0
- **Where:** src/agentprov/raw/fetch.py:1056-1063 (Fetcher._hardening); test gap in tests/security/test_fetch_hardening.py (SEC-24 covers only the urllib redirect handler)
- **Disposition:** FIXED 34a9419e
- **Repro:** `~/.agentprov/migration-work/review-core-b/repro/verify-B3-6/`

**Failing input.** An https git remote whose initial /info/refs request answers 301 to http://other.example/... (or any non-allow-listed host)

**Expected.** Refused like the HTTPS downloader's SafeRedirectHandler (https only, allow-listed hosts; SEC-24/R-43)

**Actual.** _hardening sets only protocol.file.allow and protocol.ext.allow; git's defaults are http.followRedirects=initial and protocol.http.allow=always (known-safe), so curl's REDIR_PROTOCOLS allows http and the pack is fetched in cleartext from the redirected host. Integrity still rests on the pinned SHA-1 commit + fsck, so this is a hardening gap (network contact outside the recipe's host, cleartext transfer), not a content forgery.

**Verifier.** I could not disprove it. At origin/main 7f8f8cb3, Fetcher._hardening() (src/agentprov/raw/fetch.py:1056-1063) sets only core.hooksPath, protocol.file.allow, protocol.ext.allow, transfer.fsckObjects and core.symlinks. The environment (_GIT_ENV plus _ENV_ALLOW) sets no GIT_ALLOW_PROTOCOL and no http.followRedirects, and GIT_CONFIG_GLOBAL/NOSYSTEM rule out any user config that might restrict them. Git's defaults therefore apply: http.followRedirects=initial, and protocol.http.allow=always (http is a known-safe protocol). An https remote that answers its first /info/refs request with a 301 is followed to another host over plain http, and the pack is downloaded from there in cleartext. I found no existing guard or test for this. SEC-24/R-43 and test_cross_host_redirects_drop_credentials... cover only the urllib SafeRedirectHandler of the HTTPS downloader. BF-* and F-12C-* contain no git-redirect item. The path is reachable from the CLI: `import --fetch --allow-network` runs _fetch_git with the recipe's https URL. The repro uses the remote_urls test seam only so it can point at localhost, and the real remote is the same kind of https URL. Two caveats lower the impact without refuting the claim. First, integrity holds: the commit is pinned by SHA-1, fsck runs and per-file blob SHA-1 is checked. So the defect is unconsented network contact with a host outside the recipe, plus a cleartext transfer that leaks which repo and commit are fetched; the fetched content cannot be forged. Second, the spec's 'redirects are https-only, host-allowlisted' wording (G_security T-20, MN_repo_cli 2247) is written about the HTTP downloader. It is not explicitly stated for git, though G.7.5's intent clearly covers acquisition. One correction to the proposed fix: protocol.http.allow=never alone stops the downgrade but still lets an https redirect to another host through. Only http.followRedirects=false blocks the redirect to another host.

**Evidence.** Repro: ~/.agentprov/migration-work/review-core-b/repro/verify-B3-6/repro.py (data under ~/.agentprov/migration-work/review-core-b/b3-6). Setup: a local TLS front at https://localhost:<p1> with a self-signed cert, trusted only through http.sslCAInfo in the pre-initialised cache bare repo, which stands in for a public CA. It 301-redirects every GET to http://127.0.0.1:<p2>, where a minimal smart-HTTP upload-pack server runs. The call is Fetcher(cache, allow_network=True, env={PATH}, remote_urls={REPO: 'https://localhost:<p1>/o/r'}).fetch(Recipe(kind='git', repo=REPO, commit=COMMIT)), run with system git 2.54.0 (Apple Git-157). Output:
hardening: ['-c','core.hooksPath=/dev/null','-c','protocol.file.allow=never','-c','protocol.ext.allow=never','-c','transfer.fsckObjects=true','-c','core.symlinks=false']
FETCH OK; commit present: True
hit ('https-front', 'GET', '/o/r/info/refs?service=git-upload-pack')
hit ('http-plain', 'GET', '/o/r/info/refs?service=git-upload-pack')
hit ('http-plain', 'POST', '/o/r/git-upload-pack')  (x2)
Fix check (repro_fix.py appends extra -c options to _hardening): with '-c protocol.http.allow=never', and separately with '-c http.followRedirects=false', the result is 'FETCH FAILED: FetchError git -C failed (exit 128)' and only the https-front is contacted.

**Fix.** In _hardening, add '-c', 'protocol.allow=never', then '-c', 'protocol.https.allow=always', and keep protocol.file.allow=always only under the file_protocol test seam. That blocks any downgrade to http, git:// or ssh. Also add '-c', 'http.followRedirects=false' to refuse redirects to another host. Since recipes pin a canonical https://<host>/<owner>/<repo>, a renamed repository should fail loudly and get its recipe updated rather than be followed silently. Extend test_the_git_argv_is_hardened_and_the_environment_is_scrubbed to assert these options, and if feasible add a local TLS-plus-301 test like the repro. Note that protocol.http.allow=never alone still allows an https redirect to another host.

**Reviewer notes (B3).** B3 review of src/agentprov/raw/ at 7f8f8cb3, read-only. I reproduced five findings with scratch scripts in ~/.agentprov/migration-work/review-core-b/repro/B3/ (r1_u07.py, r2_refs.py, r3_hist.py, r4_toctou.py, r5_conflict.py, plus pins.py for the profile census). Scratch data is under ~/.agentprov/migration-work/review-core-b/. Nothing touched the network: transports were stubbed and the worker pool ran in-process.

Finding 1 is in adapters/runner/importer.py, not raw/. I included it because it is the "file changed between hash and copy" case on the B3 checklist, and the raw store already offers the missing check (expected_sha256). Finding 6 (git redirects) was not reproduced: proving it needs an HTTPS server. It rests on git's documented defaults (http.followRedirects=initial; http/https are known-safe protocols).

Byte class:
- Class 0: the fixes in raw/fetch.py, raw/history.py and raw/references.py. raw/ is in no stage code digest apart from raw/members.py.
- Class 1: the members.py fix, because raw/members.py is listed in EXPAND_MODULES and feeds the expand fn_digest. The importer.py fix is also class 1, because adapters/runner is inside the aer engine_code_sha256.

Checked and found sound:
- Store: O_EXCL temporary file, os.link publish with no overwrite, re-hash of an existing digest, no-follow reads through open_evidence, shard lstat, tombstone fail-closed.
- Redirect handler: https only, allow-list, userinfo refused, credential headers dropped on host change. The token is sent unredirected, and only to token_host.
- Git: environment allow-list (no GIT_DIR, HOME or GIT_CONFIG_PARAMETERS), hooks off, file and ext transports refused, fsck on, no submodules, GIT_NO_LAZY_FETCH, blob SHA-1 recomputed.
- Origins and members strict decoding; carve pointer handling.

Smaller items not reported:
- RawObjectStore.digests() yields a stem misfiled in the wrong shard.
- A store opened with create=False still accepts put when tmp/ exists.
- iter_git_blobs stalls 30 s when a blob is over the size limit.
- redact_personal replaces a home path prefix without a path boundary (/Users/nick also matches inside /Users/nicky).
- HistoryIndex.from_bytes can raise ValueError or TypeError on a cache file that was edited but keeps a consistent rows digest.

## B4

### CB-26 (B4-1): gate-d writes its report, markdown and executions JSONL into a corpus when the target comes from --reports-dir (the inside-corpus refusal only covers --report)

- **Reproduced:** yes
- **Severity:** correctness (claimed correctness); **class:** 0
- **Where:** src/agentprov/cli/migrate.py:209 (guard gap at src/agentprov/migration/gate_d.py:392-393)
- **Disposition:** FIXED 805d6868
- **Repro:** `~/.agentprov/migration-work/review-core-b/repro/verify-B4-1/`

**Failing input.** agentprov migrate gate-d --scope full --corpus C --limit 1 --reports-dir C.partial/reports   (or reports_dir from config pointing inside a corpus)

**Expected.** Refused with exit 4 (migration.gate_d.inside_corpus), as for --report C.partial/r.json. Module docstring: 'a report path inside a corpus is refused'; N.1.5: a consumer never writes into a corpus

**Actual.** Exit 0. The run writes C.partial/reports/D/<date>-<commit>.json, .md and .executions.jsonl inside the corpus tree. gate_d_validate calls _refuse_inside only when report_path is not None (gate_d.py:392-393). The CLI then builds the default target from cfg.reports_dir at migrate.py:209, after the guard, and passes it to write_outputs without checking it

**Verifier.** I could not disprove it. At 7f8f8cb3, gate_d_validate calls _refuse_inside only when report_path is not None (gate_d.py:392-393). _run_gate_d then builds the default target from cfg.reports_dir at migrate.py:209 and passes it to write_outputs without any check. cfg.reports_dir can come from the real CLI flag --reports-dir (migrate.py:113-114) or from the config file, so the path is reachable. With --limit (scope sample), require_predecessors is skipped, so nothing stops the run before it writes. The finding is not in BF-1..BF-37 or F-12C-*. No test covers either refusal path: grep finds 'inside_corpus' only in src/agentprov/migration/gate_d.py and cli/checks.py. One mitigation: without --limit, full scope needs predecessor reports under reports_dir, so pointing reports_dir into a corpus there is less likely to happen by accident, but nothing prevents it. Impact is limited to user misconfiguration writing three files into a corpus or .partial tree. That breaks the N.1.5 'consumer never writes into a corpus' rule and the module docstring's promise ('reads them read-only and writes its report ... nowhere else'). Severity correctness stands.

**Evidence.** Script: ~/.agentprov/migration-work/review-core-b/repro/verify-B4-1/repro.py. It creates ~/.agentprov/migration-work/review-core-b/verify_b4_1/c.partial and an empty config, and monkeypatches gate_d.corpus_items and gate_d.execute to return one fake passing 'release' item. It then calls agentprov.cli.main.main(['migrate','gate-d','--scope','full','--corpus',<base>/c,'--limit','1','--config',empty.toml,'--in-process'] + X). Output:
"agentprov: error [migration.gate_d.inside_corpus]: the report path is inside a corpus; gate D never writes into a corpus"
"--report inside corpus: exit 4 ; files: []"
"report: <home>/.agentprov/migration-work/review-core-b/verify_b4_1/c.partial/reports/D/2026-10-14-7f8f8cb.json" (plus the .md and .executions.jsonl)
"--reports-dir inside corpus: exit 0 ; files: ['c.partial/reports/D/2026-10-14-7f8f8cb.executions.jsonl', 'c.partial/reports/D/2026-10-14-7f8f8cb.json', 'c.partial/reports/D/2026-10-14-7f8f8cb.md']"

**Fix.** In _run_gate_d, compute the target before calling gate_d_validate when scope is full. The report_id depends on date and commit, but the directory cfg.reports_dir / 'D' is enough for the check. Call gate_d._refuse_inside(cfg.reports_dir / 'D' / 'x.json', corpora), or compute the final target and refuse it, before any work runs. Alternatively, move the guard into write_outputs by passing corpora to it. Add a test that --reports-dir inside a corpus or .partial tree exits 4 with migration.gate_d.inside_corpus, and also test the existing --report refusal, which has no test today.

### CB-27 (B4-2): Gate report file name ignores scope: a later sample/golden run on the same day and commit overwrites the full-scope report and breaks the AD-07 chain

- **Reproduced:** yes
- **Severity:** correctness (claimed correctness); **class:** 0
- **Where:** src/agentprov/migration/gates.py:218-221 (report_id); consumers at gates.py:265 and cli/migrate.py:164, 209
- **Disposition:** FIXED e5b878c0
- **Repro:** `~/.agentprov/migration-work/review-core-b/repro/verify-B4-2/`

**Failing input.** Run 'migrate gate-d --scope full --corpus ...' (passes, hours of work). The same day at the same commit, run 'migrate gate-d --scope full --corpus ... --limit 100' (scope 'sample'), or gate-a --scope golden after gate-a --scope full

**Expected.** Reports of different scopes are kept side by side. The passing full-scope report stays findable by require_predecessors and is still there to commit (J.3.0: release refused unless a passing full-scope report of every release gate exists)

**Actual.** report_id is '<UTC date>-<short commit>' with no scope. write_report (and gate_d.write_outputs through migrate.py:209) writes both runs to <reports>/<gate>/<date>-<commit>.json, so the second run silently replaces the first. For D the .executions.jsonl and .md are replaced too. _passing_report_exists(..., gate='D', scope='full') then returns False, and gate E refuses (or the evidence for the release is gone)

**Verifier.** I could not disprove it. The default report path is `<reports_dir>/<gate>/<report_id>.json`, and `report_id` is only `started_at[:10]-commit[:7]` (gates.py:218-221). Both CLI paths use it whenever `--report` is not given: migrate.py:164 for gates G0, A, B and E via `write_report(report, cfg.reports_dir, path=None)`, and migrate.py:209 for gate D via `gate_d.write_outputs`. Nothing stops a later run from reaching the same path:
- `--limit` turns the run into scope `sample` (gate_d.py:402).
- `--scope golden` is the CLI default for A, B, D and E (migrate.py:132).
- A dev run after a strict run gets the same name too.

The file is written with `atomic_write_text` and there is no check for an existing file. The `.md` and `.executions.jsonl` files beside a gate D report are replaced as well.

`_passing_report_exists` (gates.py:530) reads only the current files in the reports directory. So after the second run, `require_predecessors` (gates.py:556) refuses the next full-scope gate, and the J.3.0 release precondition (J_migration.md:498-500) loses its evidence. This is not covered by BF-1..BF-37 or F-12C-*. The only related test, `test_write_report_uses_the_gate_directory_and_the_report_id`, pins the current naming and does not test a collision.

Two caveats lower the impact a little:
- If the full-scope report was already committed, git can restore it, but the gate lookup reads the working tree.
- Running again at the same scope and replacing the earlier report is arguably intended. The defect is only the collision across scopes and modes.

**Evidence.** Script: ~/.agentprov/migration-work/review-core-b/repro/verify-B4-2/repro.py. It reproduces the two CLI write paths exactly: `gate_d.write_outputs(GateDResult(...), reports_dir/D/report_id.json)` and `gates.write_report(report, reports_dir)`. It writes to a temporary directory under ~/.agentprov/migration-work/review-core-b/ and deletes it afterwards. Key output:
D full written: ['2026-10-14-7f8f8cb.json', '2026-10-14-7f8f8cb.md', '2026-10-14-7f8f8cb.executions.jsonl'] | passing full D exists: True
D sample written: [same three names] | same path as full: True
stored scope: sample | jsonl rows: 1
passing full D exists after sample run: False
A full -> A/2026-10-14-7f8f8cb.json | passing full A exists: True
A golden -> A/2026-10-14-7f8f8cb.json | same path: True | passing full A exists: False

**Fix.** Put the scope, and for strict runs the mode, in the default file stem, for example `f"{date}-{commit7}-{scope}{'-strict' if strict else ''}"`. Keep `report_id` itself as the G0 identifier if later reports already record it, or update those references to match. The gate lookup scans every `*.json` file, so it keeps working with the new names. As a minimum stop-gap, `write_report` should refuse to replace an existing default-path report whose `scope` or `params.strict` differs. Add a regression test: write a full-scope report and then a golden or sample report on the same date and commit, and check that `_passing_report_exists(scope='full')` is still True.

### CB-28 (B4-3): R3 projection drops the skip-listed member names at every depth, so differences in tool-call arguments named id/k/rule/hash/ns/src/... are never compared

- **Reproduced:** yes
- **Severity:** correctness (claimed correctness); **class:** 0
- **Where:** src/agentprov/migration/reconcile.py:139 (_flat; _SKIP defined at :54-57)
- **Disposition:** FIXED 123f82c1 (after regen-items-2-12 landed)
- **Repro:** `~/.agentprov/migration-work/review-core-b/repro/verify-B4-3/`

**Failing input.** Native and v1 AERs of one banking run whose assistant tool_call part for update_scheduled_transaction has args {"id": 7, ...} on one side and {"id": "999", ...} on the other (or any args/ext object with member 'k', 'rule', 'hash', 'ns', 'src', 'profile', 'aer', 'ex', ...)

**Expected.** message[*]/parts/*/args/id is compared and reported as differs_unexpected, so R3 does not pass. _SKIP is meant for record-level members that differ by design (J.4.4 row 1)

**Actual.** _flat checks 'name not in _SKIP' at every nesting level, so message[0]/parts/0/args/id (and args/k, args/rule, args/hash) are never projected. classify returns no non-equal category and ReconciliationReport.passed is True

**Verifier.** I could not refute this claim. At origin/main 7f8f8cb3, `_flat` (src/agentprov/migration/reconcile.py:139) checks `name not in _SKIP` at every nesting level. Any payload key named id, k, rule, hash, src, ns, ev, by, ex, aer, profile and so on is therefore never projected, including keys inside tool_call `args`, tool_execution `args`/`args_effective`/`returned` and `ext`. J.4.4 (docs/architecture/J_migration.md:1105ff) requires "tool-call function and args (incl. order and float form)" and "tool result content" to be `equal`, so these fields must be compared. Row 1 ("differs by design") covers only record-level ids, origins, mapping, profile and evidence metadata. The input is reachable with real data: AgentDojo banking's update_scheduled_transaction takes an `id` argument. No existing test catches it: tests/migration/test_reconcile.py never uses an args key from _SKIP. BF-1..37 and F-12C-* do not cover R3 projection.

**Evidence.** Script: ~/.agentprov/migration-work/review-core-b/repro/verify-B4-3/repro.py. Native args {id:7, recipient:'X', k:'a', rule:'r1', hash:'h1', src:'s', ns:1} vs v1 args {id:'999', recipient:'X', k:'b', rule:'r2', hash:'h2', src:'t', ns:2}, on both the tool_call part and the tool_execution. The tool_execution `returned` is {id, hash}. Output:
native paths: [..., 'message[0]/parts/0/args/recipient', ..., 'tool_execution[0]/args/recipient', ...] (no args/id, args/k, args/rule, args/hash, args/src, args/ns, and no tool_execution[0]/returned/* at all)
categories: ['equal']
passed: True
Control (only recipient differs, X vs Y): passed (expect False): False. The comparison works for non-skip keys, so the defect is the skip filter applied at depth.

**Fix.** Apply _SKIP only at the record's top level, where `ev`/`by`/`id`/`k`/`rule`/`src`/`unk`/`hash`/`ex`/`aer` etc. are record metadata. Add explicit path-level skips for the nested reference/evidence members that differ by design (for example message parts' `id`, `after/*/id` and per-field `ev`/`unk` slots, per the projection the J.4.4 table already relies on). Below that, never filter by member name inside payload containers: parts/*/args, tool_execution args/args_effective/returned, value, and ext/<ns>/*. Pass a `top: bool` or path context into _flat. Add a regression test with tool_call args containing an `id` key that differs, and assert that R3 does not pass. Check the full R3 run for newly surfaced v1_only/native_only patterns (for example nested ids in parts) and add J.4.4 rows only where the spec explains them.

### CB-29 (B4-4): G0 in dev mode passes when the recorded baseline wheel or requirements file is missing (recorded-but-missing becomes 'skipped')

- **Reproduced:** no
- **Severity:** none (spec-sanctioned dev-mode behaviour; release mode fails as required) (claimed correctness); **class:** 0
- **Where:** src/agentprov/migration/gates.py:424 (behaves as specified by docs/architecture/J_migration.md:270-271)
- **Disposition:** NOT REPRODUCED (J.1.6 resolution 1: dev-mode skip is specified)
- **Repro:** `~/.agentprov/migration-work/review-core-b/repro/verify-B4-4/`

**Failing input.** agentprov migrate verify-baseline (no --release) on a machine with no baseline wheel at AGENTPROV_BASELINE_WHEEL, <venv>/wheel/ or .baseline/wheel, while migration/baseline.lock.json records baseline_wheel_sha256 (it does: 3dcf0ed0...) and requirements_lock_sha256

**Expected.** environment.baseline_wheel fails (J.3.1: pass iff ... the baseline wheel match their recorded hashes). Only an unrecorded hash is meant to be a skip ('Unrecorded, each is a skipped check')

**Actual.** _check_recorded_hash returns SKIPPED with 'the file is missing' whenever strict is False. verdict counts only FAIL, so the G0 report is verdict 'pass', and require_predecessors accepts it for every non-strict A/B/D/E run. tests/migration/test_gate_g0.py:83 covers the recorded-but-missing case only with strict=True

**Verifier.** The mechanics are as the claim describes, but they are the specified behaviour, not a defect. docs/architecture/J_migration.md:268-271 (J.1.6, phase-8 implementation resolution 1) says: "Outside release mode, a recorded hash whose file is absent is `skipped`, as an unrecorded hash already was; in release mode it fails." gates.py:420-424 does exactly that.

A dev-mode G0 that passes with skipped checks is also deliberate and tested. tests/migration/test_gate_g0.py:51-59 asserts verdict "pass" with counts {checked 10, passed 10, skipped 2}. The committed dev-mode report docs/reports/migration/G0.json has verdict "pass", skipped 2, strict false. Spec item 5 cites the "10 passed and 2 skipped in dev mode" run. Skipped checks are never silent: they are listed in report.notes (gates.py:474-476).

The release path cannot be fooled:
- With strict=True a missing file is FAIL (repro output below).
- `_passing_report_exists` (gates.py:550) accepts a predecessor report for a strict run only if its params.strict is True.
- So a dev-mode G0 never satisfies the chain for a release (--release) A/B/D/E run.

The claim's "expected" quotes the J.3.1 pass condition but ignores the J.1.6 resolution, which refines it for dev mode. The strict=True test at test_gate_g0.py:83 covers the only case where a missing file must fail.

**Evidence.** Repro script ~/.agentprov/migration-work/review-core-b/repro/verify-B4-4/repro.py output:
recorded wheel: 3dcf0ed0
strict False skipped the file is missing   (wheel)
strict False skipped the file is missing   (requirements, path None)
strict True fail the file is missing
strict True fail the file is missing

So the behaviour reproduces, but it is the one the spec requires. J_migration.md:270-271: "Outside release mode, a recorded hash whose file is absent is `skipped` ... in release mode it fails." The design is pinned by test_gate_g0.py:51-59 (dev-mode pass with 2 skipped) and by the committed docs/reports/migration/G0.json (verdict pass, skipped 2, strict false). The release chain is guarded at gates.py:550 (a strict run accepts only predecessor reports with params.strict True).

**Fix.** No code fix needed. At most, a test-only addition: assert that with strict=False a recorded-but-missing wheel is 'skipped' and appears in report.notes, which pins the J.1.6 resolution.

### CB-30 (B4-5): Full-scope gate D passes (role release) with every J.3.5 tree accepted as a gap, validating zero migration executions, and unlocks gate E; accepted gaps are PASS even under --release

- **Reproduced:** yes
- **Severity:** robustness (claimed correctness); **class:** 0
- **Where:** src/agentprov/migration/gate_d.py:421-431 (accepted-gap loop; the PASS at :428 itself is by design per D-49)
- **Disposition:** FIXED ba3f03ff
- **Repro:** `~/.agentprov/migration-work/review-core-b/repro/verify-B4-5/`

**Failing input.** agentprov migrate gate-d --scope full [--release] --corpus <any corpus that classifies as 'other'> --accept-gap release --accept-gap converted --accept-gap native

**Expected.** A full-scope D report needs at least one J.3.5 tree actually validated. An accepted gap is at most 'skipped', which fails under strict mode (MP-3: a skipped check is a failure). The report should not satisfy require_predecessors for gate E

**Actual.** by_tree holds only 'other'. inputs.{release,converted,native}.present are each Check(PASS, 'accepted gap'). verdict is 'pass', scope 'full', role 'release'. gates._passing_report_exists(gate='D', scope='full', ...) is True, so a full-scope gate E starts with no migration AER validated

**Verifier.** Only partly right. The second half of the claim, that an accepted gap is PASS even under --release and should be SKIPPED or FAIL, is the documented design. D-49 (docs/reports/phase11/decisions/D-49.md, Rejected alternatives) explicitly rejects "Treat the missing converted tree as `skipped`. A skipped check is a failure (MP-3)". It also says "--accept-gap makes the decision the reviewer's and visible in the report". J_migration.md and DECISIONS.md D-49 say the same, and the real release-chain report docs/reports/migration/release-chain-2026-10-13/D.json depends on it (it uses --accept-gap converted). So the proposed fix of recording gaps as SKIPPED would break the intended workflow and must not be applied.

What survives is the degenerate case. Nothing stops an operator from accepting all three J.3.5 trees as gaps while passing only a corpus that classifies as 'other'. The result is a full-scope report with role release and verdict pass, even though no migration AER was validated. That report satisfies require_predecessors for a full-scope gate E. It is reachable from the CLI (`migrate gate-d --scope full --release --corpus <other> --accept-gap release --accept-gap converted --accept-gap native`), but only after passing full-scope G0/A/B reports exist and only through three explicit operator overrides. The report records all three in details.gaps, notes and params.accept_gaps. Neither BF-* nor F-12C-* covers it, and no existing test covers it. tests/migration/test_gate_d.py only exercises accepting two gaps while the release tree is present. This is a missing guard against operator misuse, not silent wrong output, so it is downgraded to robustness.

**Evidence.** Reproduction: ~/.agentprov/migration-work/review-core-b/repro/verify-B4-5/repro.py. It monkeypatches gate_d.corpus_items to return one 'other' WorkItem and _Source, and gate_d.execute to return one clean result. It then calls gate_d_validate with MigrationConfig(strict=True), scope='full' and accept_gaps=[release, converted, native], writes the report under ~/.agentprov/migration-work/review-core-b/verify-B4-5/reports/D/ and queries gates._passing_report_exists.

Output:
- "scope full role release verdict pass strict True"
- "trees validated ['other'] gaps ['release', 'converted', 'native']"
- "inputs.release.present pass | accepted gap: ..."
- "inputs.converted.present pass | accepted gap: ..."
- "inputs.native.present pass | accepted gap: ..."
- "passing full-scope D report exists for gate E (strict): True"
- Control run without accept_gaps: "verdict fail".

Code: gate_d.py:421-431. The accepted-gap branch appends Check(..., PASS, ...) at line 428. Nothing checks that at least one of TREES appears in by_tree when report_scope == 'full'. gates.py:530-553 (_passing_report_exists) looks only at gate, scope, verdict, commit, lock and strict, not at details.gaps.

**Fix.** Keep accepted gaps as PASS, as D-49 decides. When report_scope == 'full', add one check, e.g. Check('inputs.migration_trees.present', PASS if any(t in by_tree for t in TREES) else FAIL, ...). Alternatively, refuse accept_gaps that cover every tree in TREES with a usage error (exit 2) in gate_d_validate or the CLI. Either way a full-scope D report cannot pass, and so cannot unlock gate E, unless at least one J.3.5 tree was actually validated. Add a test next to test_full_scope_reports_incomplete_and_absent_trees_and_accepts_gaps_explicitly that accepts all three gaps with an 'other' corpus and asserts that the run fails or is refused.

### CB-31 (B4-6): C6 comparer passes on an incomplete or empty scenario set; it never checks the scenarios against the producer's manifest

- **Reproduced:** yes
- **Severity:** test-gap (claimed test-gap); **class:** 0
- **Where:** src/agentprov/migration/c6.py:390 (compare_work); also tests/migration/test_c6_old_vs_new.py (asserts result.ok only)
- **Disposition:** FIXED 4fc4ca6d
- **Repro:** `~/.agentprov/migration-work/review-core-b/repro/verify-B4-6/`

**Failing input.** A C6 work dir where the producer wrote manifest.json listing 14 scenarios but only some <scenario>/scenario.json dirs exist (producer run with -k, or interrupted), or none at all

**Expected.** compare_work / C6Result.ok fails when a scenario in manifest.json (or C6_SCENARIOS) has no compared item. AGENTS.md records 'Gate C6 passes, 14/14 scenarios'

**Actual.** compare_work globs */scenario.json and builds `expected` only from the items it found. With 0 items, register.ok is True and all([]) is True, so ok is True. With a subset, only that subset decides. tests/migration/test_c6_old_vs_new.py skips on empty but asserts result.ok on a partial set

**Verifier.** Partly narrowed, not refuted. compare_work (src/agentprov/migration/c6.py:390-395) only globs */scenario.json. It never reads <work>/manifest.json, which the producer's test_c6_manifest writes with "scenarios": sorted(C6_SCENARIOS), and it never checks C6_SCENARIOS. So C6Result.ok holds for a partial work dir. Three things limit the impact.
(1) The empty case cannot happen through the real caller. tests/migration/test_c6_old_vs_new.py::_work skips when no */scenario.json exists, so the gate shows "skipped", not "passed". compare_work does return ok=True on an empty dir if it is called directly.
(2) In CI (.github/workflows/ci.yml:135-142) the producer step runs before the comparer step with no continue-on-error. A failed or interrupted producer fails the job before the comparer runs.
(3) What remains reachable is a local or manual gate run. Examples: a producer run with -k, a killed run, or a work dir reused or pruned by hand. Any of these lets the comparer pass "C6" on a subset. That subset could back a "14/14" claim like the one in AGENTS.md:1013. Nothing guards against it: no existing test asserts the item count, and BF-*/F-12C-* do not cover it.
This is a gate-completeness test gap, not a correctness bug in stored data.

**Evidence.** Repro: ~/.agentprov/migration-work/review-core-b/repro/verify-B4-6/repro.py (scratch data under ~/.agentprov/migration-work/review-core-b/verify-B4-6, removed afterwards). It uses the real load_register().
Case 1: the work dir holds only manifest.json listing s1, s2, s3.
Case 2: manifest.json lists s1, s2, s3, but only s1/scenario.json exists. compare_scenario is stubbed to return a clean item for s1, as a real passing scenario would.
Output:
  empty: items 0 ok True
  partial: items ['s1'] listed 3 ok True
Code: c6.py:391 `directories = sorted(p.parent for p in Path(work).glob("*/scenario.json"))`. c6.py:394 builds `expected` from the found items only. C6Result.ok at c6.py:168-169 is `self.register.ok and all(...)` over the found items, so 0 or k<14 items pass. The comparer test (tests/migration/test_c6_old_vs_new.py) asserts only result.ok.

**Fix.** In compare_work, read <work>/manifest.json and check that "format" is "agentprov-c6-work/1".
Set listed = set(manifest["scenarios"]) and found = {i.scenario for i in items}.
Record missing = sorted(listed - found) and extra = sorted(found - listed) in a new C6Result field.
Make C6Result.ok also require that missing and extra are empty and that the manifest was present. As an alternative, emit an Observation("C6", f"scenario:{name}", "scenario:missing") for each missing name, so the register fails it as unlisted.
In the comparer test, also assert len(result.items) == len(manifest["scenarios"]) and print the missing names.

**Reviewer notes (B4).** Area B4 (migration) was reviewed read-only at 7f8f8cb3. I read src/agentprov/migration/{gates,gate_d,gate_d_worker,gate_c3,c6,xd,semdiff,pipeline,reconcile,lock}.py, src/agentprov/cli/migrate.py and tools/migration/{gate_c2,gate_c3,gate_c5,r3_reconcile}.py. I also skimmed baseline_probe.py and checked J.3.0/J.3.1/J.3.5 of docs/architecture/J_migration.md. None of the BF-* or F-12C-* findings fall in this area.

All six findings were reproduced with scratch scripts in ~/.agentprov/migration-work/review-core-b/repro/B4/: d_reportsdir.py, report_clobber.py, r3_skip.py, g0_missing.py, d_allgaps.py and c6_empty.py. Scratch data is under ~/.agentprov/migration-work/review-core-b/. No repository file was modified and nothing under tests/fixtures was read. Every fix is class 0: none touches AER, SEM, PROV, manifest or index bytes, only gate reports and report paths.

Considered and not reported (low value or by design):
- `_passing_report_exists` ignores `agentprov.dirty`. A dirty-tree check cannot be added naively, because writing the G0 report into migration/reports makes the tree dirty and committing it changes the commit.
- J.3.1 says the G0 report id is recorded in later reports. No gate records it; this is a spec gap.
- In pipeline.run_pipeline, two concurrent full-scope gates sharing the default work dir would collide on aer-tmp/<sha(item)[:24]>.aer.jsonl. This only matters for concurrent runs, and heavy jobs are queued.
- `c6.json_differences` treats -0.0 and 0.0 as equal while the byte comparison differs, and C6Result.verdict ignores item.checks. The AER encodes -0.0 as $float, so this is not reachable in practice.
- In semdiff.classify_graph, a non-dict relation section is skipped silently. B1 byte identity makes that unreachable.
- xd.parse_register defaults `match` to ['*']. This is a latent fail-open for C2 "compat" observations, which are documented as never absorbable; the current register has no such entry.
- reconcile.lineage counts None == None as 'agree'. Native origins always carry repo, commit and path.
- gate_c3._rerun hard-codes /parts/0/text in its unk check. The v1 and native mappers put the null text at index 0.

## B5

### CB-32 (B5-1): stats text/CSV output prints the manifest's corpus_id and content_digest raw: a hostile corpus forges table lines and writes terminal escapes to stdout

- **Reproduced:** yes
- **Severity:** security (low: needs a hostile third-party corpus, e.g. a downloaded deposit; the effects are terminal escapes and forged lines in text stdout, and raw control characters in CSV) (claimed security); **class:** 0
- **Where:** src/agentprov/stats/source.py:117-121 (root cause); src/agentprov/stats/output.py:82,86 (text label), :136/:141 (CSV corpus_id cell)
- **Disposition:** FIXED f21a977b
- **Repro:** `~/.agentprov/migration-work/review-core-b/repro/verify-B5-1/`

**Failing input.** A sealed corpus whose corpus.json has corpus_id = "evil\n== counts (9 rows)\nsource_id  forged\x1b[2J" and checksums written to match. It is self-consistent, so it passes the default verify="checksums". The working-tree path does no verification at all.

**Expected.** Every data-derived label in every stats format is one line with no raw control characters (G.8.6; the stats module docstring says labels are 'closed-vocabulary values or escaped'). corpus_id/content_digest are either checked against the manifest grammar (CORPUS_ID, sha256:<64 hex>) or passed through escape_untrusted_line.

**Actual.** `agentprov stats --corpus C --tables counts --format text` exits 0 with stdout containing a raw LF, which forges a '== counts (9 rows)' heading and a fake row line, plus a raw ESC[2J. The CSV output carries the raw ESC too, and its formula guard sees only the raw string, so a leading TAB/CR is not neutralised. Markdown is fine because it goes through escape_markdown. Cause: stats/source.py:118 accepts any non-empty string as corpus_id and :121 any string as the recorded content_digest. CorpusReader.manifest() checks only `format`. output.py:82/86 then interpolate both unescaped into the text label, and :141 into the CSV. This is not F-12C-04, which covered the model label in the table cells; the CLI notices already safe_text the same id (cli/stats.py:161).

**Verifier.** I could not disprove the claim at 7f8f8cb3 for sealed corpora. Three details need correcting. (1) In CSV the raw LF does not forge anything: csv.writer quotes the field, so the LF stays inside one valid cell. The defects that remain in CSV are the raw ESC and other control characters, plus a formula guard that ignores a leading TAB or CR. (2) The claimed working-tree path cannot be reached from a bare directory. open_corpus refuses a directory that is unsealed and has no .partial sibling (corpus.not_sealed). A real .partial working tree probably behaves the same way, but I only reproduced the sealed case. (3) The hostile manifest is not caught at the default verify level: `agentprov verify --level checksums` passes it. Only the manifest spec validator (corpus/spec.py:265, CORPUS_ID_RE, max 64) would reject this corpus_id, and stats does not run that validator at its default "checksums" level. This is not F-12C-04, which fixed table-cell labels (model_label) and Markdown escaping. No BF-* finding covers corpus_id or the content_digest label, and no test in tests/ calls _corpus_label with a hostile id.

**Evidence.** The repro builds a sealed corpus with build_corpus(corpus_id='evil\n== counts (9 rows)\nsource_id  forged\x1b[2J'), whose checksums match. Key output lines:
- `sealed True verification checksums corpus_id repr 'evil\n== counts (9 rows)\nsource_id  forged\x1b[2J'`
- `fmt text LF-forged: True ESC: True` / `fmt csv LF-forged: True ESC: True` (the CSV LF is inside a quoted cell) / `fmt markdown LF-forged: False ESC: False`
- `CLI exit 0 ESC in stdout: True forged heading line: True`
- `CLI stdout head: b'...prov spec agentprov-prov/0.1)\n\ncorpus evil\n== counts (9 rows)\nsource_id  forged\x1b[2J; state sealed; verification checksums; ...'`
- `csv tab-led: b'\t=cmd,counts,src-a,...'`: a corpus_id starting with TAB gets past the `=+-@` formula guard.
- `agentprov verify --level checksums` on the same corpus prints `passed; 0 failed`, exit 0.

Cause: stats/source.py:117-121 (_manifest_identity) accepts any non-empty string as corpus_id and any string as the recorded content_digest. CorpusReader.manifest() (corpus/reader.py:268-275) checks only `format`. output.py:82 and :86 then interpolate both raw into the text label, and output.py:136/:141 put corpus_id raw into each CSV row. cli/stats.py:161 already runs the same id through safe_text for notices, so the stdout payload is the one surface left unescaped.

**Fix.** In stats/source.py _manifest_identity:
- Keep corpus_id only if CORPUS_ID_RE.fullmatch(corpus_id) and len(corpus_id) <= 64, reusing corpus/spec.py's regex.
- Keep the recorded content_digest only if it fullmatches r'sha256:[0-9a-f]{64}'.
- Otherwise use None and add a notice.

As defence in depth, pass c['corpus_id'], c['content_digest'] and c['root_digest'] through escape_untrusted_line in output._corpus_label. Also extend _FORMULA_START with '\t' and '\r'.

Add a SEC-12 test: a sealed hostile-corpus_id corpus rendered in the text and csv formats has no raw LF in its label line and no ESC.

### CB-33 (B5-2): Artefacts table groups rows by the truncated, comma-joined display label, so distinct models are pooled into one row

- **Reproduced:** yes
- **Severity:** correctness (claimed correctness); **class:** 0
- **Where:** src/agentprov/stats/tables.py:353 (grouping key), with the label built at tables.py:197 (model_label) and consumed at tables.py:519-529 (_artefact_rows)
- **Disposition:** FIXED e681e866
- **Repro:** `~/.agentprov/migration-work/review-core-b/repro/verify-B5-2/`

**Failing input.** Two executions of one (source_id, profile) whose llm_agent requested models are 'org/'+'m'*210+'-run-A' and 'org/'+'m'*210+'-run-B'. These are distinct ids of the same length that differ after character 200, for example the long account-path model ids seen in AgentHarm-style logs. A variant: one model id 'a,b' versus an execution with two agents 'a' and 'b'.

**Expected.** The artefacts table is per (source_id, profile, model) and never pooled (N.2.12, D.15.4). Two different requested models give two rows, each with n_executions 1.

**Actual.** model_label() returns escape_untrusted_line(','.join(sorted(models)), max_chars=200). The truncation marker carries only the remaining length, so both ids map to the same label, and that label is the grouping key at tables.py:353 (akey). Output: one row 'mmm…[truncated: 20 more chars] artefact.unclassified.sentinel_time n_executions=2 executions=2'. The short models give separate rows with n_executions 1. The ',' join collides in the same way.

**Verifier.** Could not disprove. At 7f8f8cb3, model_label() (src/agentprov/stats/tables.py:188-197) returns _label(','.join(sorted(models))), which is escape_untrusted_line(..., max_chars=200) (_LABEL_CHARS at line 89). compute_corpus uses that display string as the artefacts grouping key at line 353 (akey = (source_id, profile, model_label(document))), and _artefact_rows (line 519) counts n_executions and executions per akey. The path is reachable from `agentprov stats --tables artefacts` through compute_corpus, and nothing upstream rejects long model ids or model ids that contain commas. BF-1..BF-37 do not cover it. F-12C-04 is only about LF/HTML escaping in the label, so it does not cover this either. The spec says what the table should be: D.15.4 says `stats --artefacts` gives the table "per source, part and model", and N.2.12 says results are never pooled. Pooling two distinct requested models into one row breaks that. The defect only appears in edge cases: model ids longer than 200 characters that differ only after character 200, or one model id containing a comma compared with a multi-agent run. Severity correctness (moderate), class 0, because stats output is not stored corpus bytes or stage digests.

**Evidence.** Script: ~/.agentprov/migration-work/review-core-b/repro/verify-B5-2/repro.py. It builds three hand-made corpora with tests/unit/stats/stats_support.build_corpus and runs compute_corpus(open_corpus(root, verify='none'), tables=('artefacts',)). Output:
== long: failures={}
   model=...'mmmmmmmmmmmmmmmmmmm[truncated: 20 more chars]' (n_executions, executions)=[(2, 2)]
== short_control: failures={}
   model=...'short-a' (n_executions, executions)=[(1, 1)]
   model=...'short-b' (n_executions, executions)=[(1, 1)]
== comma: failures={}
   model=...'a,b' (n_executions, executions)=[(2, 2)]
Two distinct requested models, 'org/'+'m'*210+'-run-A' and '...-run-B', end up in one row with n_executions=2. The same happens to one llm_agent with model 'a,b' and an execution with two llm_agents 'a' and 'b'. The short-id control gives separate rows with n_executions=1 each.

**Fix.** Separate identity from display. Add a helper that returns the raw identity, tuple(sorted(models)) or None. Use it as the third element of akey at line 353. In _artefact_rows, sort keys by (source_id, profile, model_tuple or ()), and set the row's "model" to _label(','.join(model_tuple)) only when the row is emitted. Keep model_label() for its other display uses. If two distinct tuples can still render to the same label (truncation, or a comma inside an id), make the rows distinguishable: add a model_key column holding a short sha256 of the JCS of the tuple, or join with an escaped separator. Add a unit test with two models of more than 200 characters that differ only after character 200, plus the 'a,b' versus ('a','b') case.

### CB-34 (B5-3): render with --corpus '.' (or '/') crashes with an internal error; '--corpus C/x/..' is wrongly refused because the default output dir is computed from the unresolved path

- **Reproduced:** yes
- **Severity:** robustness (claimed robustness); **class:** 0
- **Where:** src/agentprov/render/output.py:22-24 (called unresolved from src/agentprov/cli/render.py:229)
- **Disposition:** FIXED d13184c8
- **Repro:** `~/.agentprov/migration-work/review-core-b/repro/verify-B5-3/`

**Failing input.** `cd <corpus>.partial && agentprov render --corpus . --limit 1 --format dot` or `agentprov render --corpus C/aer/.. --limit 1 --format dot --dry-run`

**Expected.** The default output is '<corpus name>-rendered' beside the resolved corpus directory, and the render proceeds (or gives a typed usage error).

**Actual.** '.': exit 70 'internal error: ValueError: PosixPath('.') has an empty name'. default_output_dir calls Path('.').with_name(...), and cli/render.py:229 passes it the unresolved root from locate_corpus. 'C/aer/..': the default becomes 'C/aer/..-rendered', a directory inside the corpus, so the guard refuses with render.output_in_corpus (exit 4) although no --out was given. '..' gives '..-rendered' relative to cwd.

**Verifier.** I could not disprove it. The CLI does not normalise --corpus anywhere before this point. locate_corpus returns Path(path) unresolved when it is a directory (render/source.py:61-63). cli/render.py:229 passes that unresolved root to default_output_dir. default_output_dir uses root.name and root.with_name, which raise ValueError on '.' and '/', and give a '..-rendered' child for paths ending in '..'. The guard (assert_output_allowed) resolves paths only afterwards, so the default it checks already sits inside the corpus. This is not in BF-1..37 (BF-12 is an unrelated tools/ 'render' function) or in F-12C-*. The existing test (tests/render/test_render.py:319-320) only covers normal names. When I ran a control with '--corpus c3', the guard passed and the run reached the later environment stage (exit 3, pydot missing), so the guard does not reject every input.

**Evidence.** The script was run with `uv run python repro.py <venv>/bin/agentprov`. Scratch corpus: ~/.agentprov/migration-work/review-core-b/b53/c3 (empty executions.jsonl plus an aer/ subdir; the guard runs before the index is read).
- default_output_dir '.' raised ValueError PosixPath('.') has an empty name
- default_output_dir '/' raised ValueError PosixPath('/') has an empty name
- default_output_dir '..' -> ..-rendered
- default_output_dir 'C/aer/..' -> C/aer/..-rendered
- `agentprov render --corpus . --limit 1 --format dot --dry-run` (cwd c3) exit 70: "agentprov: internal error: ValueError: PosixPath('.') has an empty name (exit 70)"
- `agentprov render --corpus c3/aer/.. --limit 1 --format dot --dry-run` exit 4: "error [render.output_in_corpus]: refusing to write renders inside a corpus; use --out DIR outside every corpus (guard G8)", although no --out was given
- Control `--corpus c3` exit 3 (render.extra_missing): the guard passes for the same corpus under its plain name.

**Fix.** In default_output_dir, resolve the path first: root = Path(os.path.realpath(corpus_root)), then strip the .partial suffix from root.name and return root.with_name(name + '-rendered'). If root.name is empty after resolving (the filesystem root), raise a typed usage error (exit 2, e.g. render.output_required) that asks for --out. Add test cases for '.', 'C/sub/..' and '/' next to tests/render/test_render.py:319.

### CB-35 (B5-4): datasheet_field_groups drops stats read/evaluation failures silently: published coverage table has n_executions counting executions that contributed no cells

- **Reproduced:** yes
- **Severity:** correctness (low: reachable through the public hook / renderer API; through `agentprov package` the read-failure path is pre-empted by _complete_rows, and only the evaluate() stats.aer.tag path, which needs an AER with an invalid evidence tag, gets through). Also a test-gap: test_datasheet_table.py has no failure case. (claimed correctness); **class:** 0
- **Where:** src/agentprov/stats/datasheet.py:45-48
- **Disposition:** FIXED 5cc022d0
- **Repro:** `~/.agentprov/migration-work/review-core-b/repro/verify-B5-4/`

**Failing input.** A working tree with 2 agent executions in which one AER fails CorpusReader.read_aer (here a byte edit so the digest no longer matches the index). The same happens when evaluate() raises FieldGroupError stats.aer.tag.

**Expected.** The datasheet's field-group table (the stored DATASHEET.md, 'one computation' shared with `stats`) either refuses or visibly marks the failure. `stats` itself reports such failures and exits 1.

**Actual.** compute_corpus returns failures={'corpus.read.aer': 1}, but datasheet_field_groups reads only tables.tables['field_groups'] and ignores tables.failures. The rendered row is '| src-a | pa@1 | all | 2 | 17 | 0 | 8 | 2 | 1 | 0.5882 | 0.4706 |': n_executions=2, but the cells (17 instead of 34) come from one execution, and nothing indicates the loss. In `package` this is mostly latent, because _complete_rows reads every AER first. The evaluate() FieldGroupError path is not pre-checked there, and the function is a public hook.

**Verifier.** I could only partly disprove it. The defect is real at origin/main 7f8f8cb3: datasheet_field_groups (and the renderer hook that package injects) reads tables.tables['field_groups'] and never looks at tables.failures. With an unreadable AER or one that evaluate() rejects, the table still renders and nothing marks the loss. n_executions keeps counting the lost execution while its cells are missing. `agentprov stats` does count these failures (cli/stats.py:168-179).

Reachability through the real CLI is narrower than the claim says, though:
(1) The read_aer failure path (corpus.read.aer) cannot reach a sealed DATASHEET through `agentprov package`. _complete_rows (corpus/package.py:596, 425-445) calls reader.read_aer on every row before the datasheet is rendered, so package refuses first.
(2) The evaluate() path (stats.aer.tag, an invalid evidence tag at a group pointer) is not caught by package's pre-pass. read_aer accepts the record, and facet_members ignores invalid tags (classes_of filters with is_valid_tag). But such an AER only exists if a mapper or validator gap lets an invalid evf tag through, or if someone edits a working tree by hand with a matching digest. In normal pipelines it is latent.

It is not covered by BF-1..37 or F-12C-* (F-12C-03/04 are about escaping). tests/unit/stats/test_datasheet_table.py has no failure case. So this is a real but low-impact correctness gap plus a test gap, mainly on the public hook. The claim's file:line is right.

**Evidence.** The scripts are repro.py and repro_b2.py in the scratchpad (verify-B5-4). Scratch corpora are under ~/.agentprov/migration-work/review-core-b/verify-B5-4/. Both scripts build corpora with tests/unit/stats/stats_support.build_corpus.

repro.py output, 'ctx' row (columns: source_id, profile, group, n_executions, cells, not_applicable, O, D, I, coverage, observed_share):
A clean :  | src-a | pa@1 | ctx | 2 | 2 | 0 | 0 | 0 | 2 | 0.0000 | 0.0000 |
A broken:  | src-a | pa@1 | ctx | 2 | 1 | 0 | 0 | 0 | 1 | 0.0000 | 0.0000 |   (AER bytes edited, model-a -> model-b)
A failures: {'corpus.read.aer': 1}
B failures: {'stats.aer.tag': 1}   (digest-consistent AER, mc0 evf '/input' = 'Z')
B renderer hook: | src-a | pa@1 | ctx | 2 | 1 | 0 | 0 | 0 | 1 | ... |   (package's hook renders it silently)

repro_b2.py: same bad-tag AER, but with headers that carry ev so facet computation can run:
failures: {'stats.aer.tag': 1}
hook row: | src-a | pa@1 | ctx | 2 | 1 | ... |
ex_5ds3d5p facet_members ok   <- package's _complete_rows pre-pass (read_aer + facet_members) does not catch it
ex_ipoupwq facet_members ok

In every case the table says n_executions=2, the cells come from one execution, and nothing in the Markdown shows the loss.

**Fix.** In datasheet_field_groups, after compute_corpus: if tables.failures is non-empty, raise an AgentProvError (e.g. code 'stats.datasheet.failures', listing the codes and counts as sorted identifiers only). The renderer runs inside package's seal, so the seal refuses and the _Writer rolls back. Do not silently render. Add a unit test that builds two executions, one with an invalid evf tag, and asserts the raise.

**Reviewer notes (B5).** I reviewed src/agentprov/stats/ and src/agentprov/render/ read-only at 7f8f8cb3. I checked them against the BF-1..37 list and F-12C-04 and found none of the four findings among them. Scratch scripts are in <tmp>/.../scratchpad/review/B5/ (r1.py, r2.py, r3.py); scratch corpora are in ~/.agentprov/migration-work/review-core-b/B5/. Side effect: the first `uv run` created the gitignored .venv in the worktree. The render probes used `uv run --offline --with pydot>=4.0.1`, an ephemeral environment, and the repo was not modified.

Checked and found sound:
- Model, rule and artefact labels go through escape_untrusted_line, so there is no raw LF, CR, TAB, U+2028/2029 or ESC. The Markdown cells and the corpus heading go through escape_markdown, which handles `|`, backslash, HTML, links and code spans. The CSV formula guard covers the data-derived string cells; the list cells hold only registry ids and execution ids.
- Zero denominators: share() and proportion return None, shown as '-' or an empty cell, so there is no NaN or inf.
- Ordering is deterministic: rows are sorted, failures are sorted in to_json, and failure_list is sorted.
- DOT output: dot_quote escapes &, backslash, quote, CR and LF. No HTML-like or record labels are built, and node ids are hash-derived. The trusted-grammar tokens and the escaping of show_content are covered by tests/render. run_dot uses a fixed argv and a minimal environment.
- The render and stats output guards refuse writes inside a corpus.

Not reported (judgement calls):
- render/source.py does not check the PROV file's sha256 against the index digest, and it shows no 'unverified' notice for a sealed corpus. This looks like a design choice ('shows what the files say').
- Invalid rule ids that collide after the 200-character truncation pool their counts in the statements table. They are already flagged as stats.prov.rule_unknown.

## Fixes for other sessions' findings

These were handed to this branch by core review C and fixed here:

| id | commit | finding |
|---|---|---|
| CC-19 | e5011f19, be46b138 | duplicate of CB-18; adds the non-ASCII `str.isdigit` case for `SOURCE_DATE_EPOCH` |
| CC-20 | d97b7139 | `package` and `package --deposit` skipped the git work-tree guard under `--dry-run` (N.1.6(5)) |
| CC-21 | 7549b6d7 | the `package` summary's `corpus.root` held an unredacted home path |
| CC-7r | 9028b516 | `render --corpus C --out C` created the final dir of a working corpus `C.partial`, which then could not be sealed |
| RC-1 | edd3735a | `CorpusWriter.open` created `X.partial/` before the git work-tree refusal |

## Remainders and follow-ups

- **CB-3.** Optional hardening, not done: derive's `_complete` (`corpus/derive.py`, twins) or the importer's
  `_seen_before` (`adapters/runner/importer.py`) could re-process an index row whose validation digest has no
  validation row. That would repair working corpora that went through a failed flush before the fix.
- **CB-19.** The builder backstop goes to the bug pass: `build_deposit` refuses `release_date.year > 2107` with
  `release.usage` (exit 2), before `_check_out`.
- **CB-28.** The golden pairs show no new R3 differences. The next full-scope R3 run (18,027 pairs) may surface payload
  members named `id`, `hash` or `k` that really differ between native and v1. Triage them against J.4.4.
- **CB-17.** Triage TOML files now need a top-level `root_digest`. Untracked rehearsal triage files (phase 10k and 11)
  without one are refused with exit 2 until they are reviewed for the sealed digest. The scan document gains a `triage`
  key, so the format stays `agentprov-release-scan/0.1` and the change is additive.
- **CB-32.** The stats `fn_digest` (stats package source) changes. It appears only in stats report output.
- **deferrals-c rebase.** The following commits touch files deferrals-c owns:
  - CB-5 (`corpus/spec.py`, `corpus/package.py`)
  - CB-9 (`corpus/package.py`)
  - CB-10 (`corpus/package.py`)
  - CB-15b (`corpus/package.py`, `release/metadata.py`)
  - CB-18b (`corpus/package.py`, `corpus/manifest.py`)
  - CB-3 and RC-1 (`corpus/writer.py`; `claude/derive-bugpass` also edits this file)
