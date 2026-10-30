# Core review C: proposals and open routing

These are proposals for the user to decide; nothing here is implemented. The D-ids were reserved with
`tools/reserve_id.py` (D-540 to D-543 and RC-1/RC-2). No class-1 (regen-batch) item was needed: no fix in this review
changes the bytes of an existing corpus.

## D-540: `api.check_claim` forwards the claims library's keyword arguments (CC-17, medium)

**Problem.** `agentprov.api.check_claim(source_ids, tags, *, derivation=None)` matches the normative signature in
MN M.6 (`MN_repo_cli.md:1334`) and I.5.6 (`I_matrix.md:1492`). The library
`adapters.registry.claims.check_claim` also takes `location`, `agent_executions_only` and `phrase`, and the facade
cannot pass them. Through the facade:
- `check_claim(["rope"], ["agent_execution"])` always returns `NC-ALL-13`, although the library returns `[]` with
  `agent_executions_only=True`.
- `check_claim([], ["coverage_claim"])` always returns `NC-ALL-08`, although the library returns `[]` with
  `phrase=coverage_phrase()`.

I.5.6 rule 2 requires `coverage_claim` to equal the exact `coverage_phrase()`, and nothing in the spec signature can
carry the phrase. The spec contradicts itself, and the facade inherits the gap. Every paper value tagged
`agent_execution` or `coverage_claim` would fail DoD Q.11b even when it is correct. This is latent until the paper
package is wired (the `paper.toml` pin is reported as skipped).

**Proposal.** Make the facade
`check_claim(source_ids, tags, *, derivation=None, location="", agent_executions_only=False, phrase=None)`,
forwarding all four keywords. Update the M.6 and I.5.6 signature blocks to match. Add a contract test that the facade
accepts every keyword-only parameter of the library (`inspect.signature`) and that the two calls above return `[]`.

**Effects.** An additive API change within 0.1.x (M.6 says the facade is stable within 0.1.x, so an addition is
allowed). No corpus bytes change. The M.6/I.5.6 edit overlaps the cli-robustness branch, which also edits
`MN_repo_cli.md`, so coordinate.

**Rejected alternative.** Accepting `**kwargs` and forwarding them unchecked: the facade would no longer document its
contract.

## D-541: `api.rows(corpus, "lineage")` (CC-16 follow-up)

**Problem.** M.6 lists the `lineage` row set: `from_node`, `to_node`, `relation`, `n` and `basis`, computed from
`corpus.json`, `raw/origins.jsonl` and the profiles' `[lineage]`. D-48 item 15 deferred it "until U3's manifest
`sources[].lineage`". U3 sealing has landed (`corpus/package.py:730` writes the member, and `SOURCE_ENTRY` requires
it), but `rows()` still raises `ApiUnavailable` unconditionally. CC-16 corrected the text; the row set is still
missing.

**Proposal.** Build the rows from a sealed manifest's `sources[].lineage` plus `raw/origins.jsonl` duplicates. Raise
`ApiUnavailable` only for a corpus that has no `sources[].lineage` (a working corpus). The existing test
`test_unavailable_parts_say_so` keeps holding on its working corpus. Close the D-48 item 15 deviation.

**Effects.** New API behaviour, no corpus bytes. It needs a sealed fixture corpus with lineage for the test.

## D-542: `live.quality` covers every ledgered session, not only the current invocation's (CC-18, low)

**Problem.** N.2.1b item 12 and D.10.9 say the capture-quality report `live.quality` is derived from the stored
evidence and reproducible from the corpus. `Campaign.report()` builds it from `self.qualities`, which holds only the
sessions ingested by this invocation, while `attempts_per_cell` counts the whole ledger. The verifier reproduced
this with three scripted runs into one corpus:
- After a resume, the per-model counts covered 1 of 2 ledgered sessions.
- A no-op resume wrote `models: {}` and `statuses: {}`, wiping the report.

**Proposal.** Rebuild `SessionQuality` for every ledger entry before the report is written. For earlier entries, read
each stored capture log through the raw store (`capture_sha256`) with `session_quality`, as is done for new sessions.
That keeps the report a pure function of the corpus.

**Rejected alternative.** Merging the counters with the previous `before["quality"]`: that is not reproducible from
the corpus and repeats an earlier error.

**Effects.** This changes `live.quality` bytes of a resumed live working manifest. Only `test_only` live corpora
exist, and none is regenerated, so no regen item is needed. A test needs two runs with `--repeats 1`, then
`--repeats 2`. Owner: `cli/live/campaign.py` (free after this branch) and `cli/run.py` `live_block` (cli-robustness).

## D-543: the instrumentation items named before consent (CC-28 remainder)

**Problem.** N.1.11(3) requires the consent text, before the first model call, to list every declared
instrumentation item. cli-robustness 288db297 added the done count and the `--max-attempts` bound. The items
themselves are computed in the worker per session, so the parent cannot list them before a cell runs, and the
consent text now says so.

**Proposal.** Choose one:
- (a) Add a protocol op, or extend `hello_ok`/`plan`, that returns the declared instrumentation items, and list them
  in the consent text.
- (b) Amend N.1.11(3) to "names the instrumentation the session will declare (listed per session in the capture
  log)" and record the deviation.

Option (a) needs a capture/backend protocol change in `backends/shared`, so its owner decides. Option (b) is a spec
edit only.

## Open routing

| Id | Owner | Item |
|---|---|---|
| RC-1 | `corpus/` owner | `CorpusWriter.open` creates `X.partial/` before `assert_outside_git_work_tree`, so a refused import leaves an empty directory in the git work tree. Check the nearest existing ancestor first. |
| RC-2 | whoever next edits `cli/checks.py` after claude/rules-drift merges | (1) adopt `common.bounded_int` (CC-15) for `checks._non_negative`; (2) CC-23: `validate --report - --json` writes the report and the summary to stdout. Refuse the combination with exit 2, or send the report to stderr as `info`/`inspect`/`stats` do. This session can take both once rules-drift lands. |
| — | core review B | CC-19 (=CB-18), CC-20, CC-21, and the render sibling of CC-7 (`render/output.assert_output_allowed` accepts the final dir of a `.partial` corpus). Accepted. |
| — | cli-robustness | CC-15, CC-22, CC-24..CC-31 landed at 288db297 (not pushed). CC-28 is partial, see D-543. |

## Optional (no D-id)

- The `import --fetch --dry-run` plan line could add "(the real run needs --allow-network)" when the network is not
  allowed. The behaviour itself is as specified (MN N.2.2 import item 2); this is only a wording improvement.
