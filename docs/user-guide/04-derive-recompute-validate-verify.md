# 4. Derive, recompute, validate and verify

Four commands check and rebuild corpora. None of them changes a corpus in place.

| Command | Question it answers | Writes |
|---|---|---|
| `derive` | can I add a layer (a view, TriG, a new PROV spec) to this corpus? | a new working corpus (`--out NEW`) |
| `recompute` | does re-deriving this corpus give the same bytes? | nothing (`--dry-run`) or a new working corpus (`--out NEW`) |
| `validate` | do the stored outputs pass the validation tiers? | nothing (optionally a report outside the corpus) |
| `verify` | is the corpus intact, from checksums to the raw → AER → SEM → PROV chain? | nothing |

The examples use the demo corpus after it was sealed in [chapter 5](05-package-and-deposit.md) (`corpora/demo`); every
command also accepts a working tree (`corpora/demo.partial`).

## recompute

`recompute` re-runs the derivation stages of a corpus, from its stored raw objects or AERs, and compares the result
with what is stored, byte for byte. It never needs a model. It needs either `--dry-run` (compare in a private
temporary tree, write nothing) or `--out NEW` (write the result as a new working corpus `NEW.partial`).

The private tree of a dry run (`derive --dry-run` or `recompute --dry-run`) and of `verify --level rederive` is made on
the corpus's own filesystem when it can be (D-891): under `$AGENTPROV_HOME/tmp`, or in the system temporary directory,
whichever is on the corpus's volume. There the raw objects are hard-linked into the tree, not copied. A corpus on any
other volume uses the system temporary directory, and its raw objects are copied, with the notice "hard links are not
possible here". The tree is never inside a corpus and is removed afterwards, and where it lies changes no result.

```text
$ agentprov recompute --corpus corpora/demo --dry-run
agentprov import agentdojo: units=3 candidate_kind=file candidates=3 plan=2024-06 -> aer unit_kind=execution workers=6
agentprov recompute: units=3 plan=aer,sem,prov,validation workers=0
recompute: finished in 2.9s (exit 0)
  units    6 of 3: sealed 3, derived 3
  issues   map.accounting_unverifiable x6, map.earlier_attempts_unobservable x6
tier-4 round-trip cache: hits 3
agentprov recompute: would derive 3 execution(s); recomputed stages: aer,sem,prov,validation; 3 identical, 0 changed (explained), 0 unexplained, 0 failed, 0 unverified; 0 index row(s) refreshed
```

The first line is the re-map: `recompute` re-imports the stored raw objects through the same adapter (offline) to
rebuild the AER, then re-derives SEM, PROV and validation. (The `units` line counts both passes, hence "6 of 3".)

**What "0 differences" means.** Each execution is classified:

| Result | Meaning |
|---|---|
| identical | every recomputed output is byte-identical to the stored one |
| changed (explained) | the bytes differ and a declared version also differs (for example a newer rule catalogue) |
| unexplained | the bytes differ while every declared version is the same. This is a defect; the command exits 1 |
| failed | the stage failed for this execution |
| unverified | the execution could not be checked (`--strict` makes this exit 1) |

On the commit and lockfile that built a corpus, `recompute --dry-run` must report 0 changed and 0 unexplained. At a
newer commit, each version drift is reported (for example `version drift: prov: catalogue aprov v2 recorded, v3
current`), and a writing `recompute` refuses to produce a corpus that mixes versions (`corpus.derive.version_drift`).
Upgrading a corpus to newer versions means a fresh import.

**Where is the building commit?** Every corpus an import, a live run, a `derive` or a `recompute --out` writes records
the commit of the AgentPROV checkout that ran it in its manifest, `producer.git_commit` with `git_tree_clean`, and an
ordered `producer.build_steps` list with one entry per process that built it: the command, the version, the commit, and
the stages that process wrote (`aer`, `sem`, `prov`, `validation`, ...). A `recompute --out` that rebuilds only the later
stages shows that the AER is the import's commit. A drift report and a refusal print them (`source import at commit
<hash> wrote aer, ...`). Code that does not run from a git checkout (an installed wheel) records
`git_commit_absent_reason` with the version and the installed-distributions digest instead, never a made-up commit. A
corpus built before this was recorded says `building commit not recorded`; its commit has to be found from the code
digests in `derivation.json`. To re-derive a corpus, check out the recorded commit (with the lockfile it recorded), then
run `recompute --dry-run`.

Writing the result:

```text
$ agentprov recompute --corpus corpora/demo --out corpora/demo-recomputed
…
agentprov recompute: derived 3 execution(s); recomputed stages: aer,sem,prov,validation; 3 identical, 0 changed (explained), 0 unexplained, 0 failed, 0 unverified; 0 index row(s) refreshed
agentprov recompute: new working corpus …/corpora/demo-recomputed.partial
```

| Option | Use |
|---|---|
| `--stages S[,S...]` | stages to re-run: `expand`, `aer`, `sem`, `prov`, `validation`, `views` (default: every stage the source has) |
| `--show-diff N` | show the first differences of N changed executions |
| `--strict` | exit 1 when an execution is unverified |
| `--no-reuse` | with `--out`, recompute everything instead of reusing unchanged outputs |
| `--link-raw` | hard-link raw objects into `NEW` instead of copying them |
| `--jobs N` | worker processes; results are identical for every N |
| `--no-validation-cache` | always run the tier-4 round trip; neither read nor write the cache |

**Live corpora** can be re-derived from their stored AERs but not re-mapped (exit 5).

**Revalidating after a skipped conformance check.** A corpus built with `--skip-prov-conformance` is marked
unvalidated. Only a full recompute into a new corpus clears the mark:

```bash
agentprov recompute --corpus OLD --out NEW --stages sem,prov,validation
```

### Corpora built at an older commit

A corpus is re-derived at the commit that built it, not at the newest checkout. When the code of a stage has changed
since the corpus was built, `recompute --dry-run` at the newer commit reports the drift for that stage, and a writing
`recompute` refuses to mix versions (`corpus.derive.version_drift`). Neither means the corpus is wrong: the check has
to run on the code that built it. Check that commit out in a separate worktree, with its own environment, and recompute
there:

```bash
git worktree add ../agentprov-at-5b1f6fdf 5b1f6fdf
cd ../agentprov-at-5b1f6fdf
uv sync --frozen
uv run agentprov recompute --corpus ~/.agentprov/corpora/CORPUS --dry-run
```

`--dry-run` writes nothing into the corpus, so it can run on the stored tree. Take the commit from the manifest's
`producer.build_steps` (above). The corpora of the 2026 regeneration round were mostly built before commits were
recorded, so [chapter 14](14-corpora.md#the-sealed-corpora-checks-and-reproduction) lists their building commits.

This is how the project checked its own older corpora (decision D-358): all eight corpora that preceded the
regeneration round were rebuilt from their pinned raw inputs at the commit and lockfile that built them, and every
file came out byte-identical (apart from the input directory's path in `corpus.json` where the input was a local
checkout) ([`docs/reports/regeneration/d358/`](https://github.com/nickjones39/AgentPROV/tree/main/docs/reports/regeneration/d358)).

## derive

`derive` adds derived layers that a corpus does not have yet, into a new working corpus. The source is only read.

```text
$ agentprov derive --corpus corpora/demo --out corpora/demo-views --stages views --views transcript-v1
agentprov derive: units=3 plan=views workers=0
derive: finished in 145ms (exit 0)
  units    3 of 3: derived 3
  …
agentprov derive: derived 3 execution(s); recomputed stages: views; 3 identical, 0 changed (explained), 0 unexplained, 0 failed, 0 unverified; 0 index row(s) refreshed
agentprov derive: new working corpus …/corpora/demo-views.partial
```

**TriG.** PROV-O TriG is written on demand into a directory outside every corpus; it is never part of a corpus:

```text
$ agentprov derive --corpus corpora/demo --out corpora/demo-trig --trig trig
…
agentprov derive: 3 TriG file(s) written to …/trig
…
notice: TriG listing sha256:d1e7c273384b71ff1da606d2807facc1c3387dc8d27bea3189dff29ec7d9d6b4 (prov 3.2.2, rdflib 7.6.0); TriG is not part of the corpus (AD-10 row 3)
```

| Option | Use |
|---|---|
| `--stages` | layers to add: `sem`, `prov`, `validation`, `views` |
| `--views VIEW` | add a view (`transcript-v1`) |
| `--semantics-profile ID@N` | the semantics profile for an added SEM layer |
| `--prov-spec SPEC` | `agentprov-prov/0.1`, or `adprov-v2.3-compat` for the frozen regression oracle (AgentDojo-PROV v1 sources only) |
| `--trig DIR` | also write PROV-O TriG into `DIR` |
| `--dry-run` | derive and compare in a private temporary tree; write nothing |

`--out` must name a directory that does not exist:

```text
$ agentprov derive --corpus corpora/demo --out corpora/demo
agentprov: error [corpus.derive.out_exists]: --out names a directory that exists; a new corpus version needs a new directory
```

## validate

`validate` checks stored outputs. With `--corpus` it re-runs the tiers over every execution of a corpus (sealed,
working or `.partial`) and compares the results with the stored validation results; it never writes into the corpus.
Without `--corpus` it validates AER files given as arguments (tier 2).

```text
$ agentprov validate --corpus corpora/demo --strict
agentprov validate: units=3 plan=aer,sem,prov,linkage workers=12
validate: finished in 8.4s (exit 0)
  units    3 of 3: ok 3
tier-4 round-trip cache: misses 3, stored 3
validated 3 execution(s) of demo-agentdojo (sealed) in release mode, tiers aer,sem,prov,linkage: 3 passed, 0 failed; linkage resolved 3/3 (100.00%); stored results reproduced 3, differ 0
```

The tiers:

| Tier | Checks |
|---|---|
| `aer` | the AER validator: schema, references, locators, accounting, seal |
| `sem` | the SEM validator |
| `prov` | PROV structure, per-bundle PROV-CONSTRAINTS, the W3C PROV round trip (tier 4) and the profile rules |
| `linkage` | every core statement resolves, through `apv:sourcePointer`, to the AER field that justifies it |
| `shacl` | SHACL shapes: **not implemented in this build** (installing the `shacl` extra changes nothing) |
| `regression` | the compat oracle, where it applies |

`--tiers LIST` picks tiers (default `aer,sem,prov,linkage`). A check that cannot run is reported as **skipped, never as
passed**:

- `--strict` makes a skipped check fail;
- `--release` implies `--strict`, uses the release-mode validator and runs **every applicable tier**, including
  `shacl`. The `shacl` tier is not implemented in this build, so it is always skipped, and `validate --release` exits
  1 even when every execution passes. The summary says so:

```text
$ agentprov validate --corpus corpora/demo --release --report validate-report.json
agentprov validate: units=3 plan=aer,sem,prov,linkage workers=12
validate: finished in 7.0s (exit 1)
  units    3 of 3: ok 3
tier-4 round-trip cache (audit): audited 3
validated 3 execution(s) of demo-agentdojo (sealed) in release mode, tiers aer,sem,prov,linkage: 3 passed, 0 failed; linkage resolved 3/3 (100.00%); stored results reproduced 3, differ 0; skipped, not passed: tier shacl (not implemented in this build); a skipped tier fails --strict and --release (exit 1)
```

Until the `shacl` tier exists, `validate --corpus DIR --strict` (the four default tiers, nothing skipped) is the
strongest check that can pass; the report (`--report`) lists `"skipped_tiers": ["shacl"]` for a release run.

| Option | Use |
|---|---|
| `--report PATH` | write the full report (JSON) outside the corpus; `-` for stdout |
| `--sample N`, `--seed S` | validate a seeded sample of N executions |
| `--jobs N` | worker processes for the sem, prov and linkage tiers |
| `--no-validation-cache` | always run the tier-4 round trip. `--release` never reads the cache; it recomputes every round trip and audits the entries it finds |
| `--card CARD.md` | lint a corpus card (datasheet source) with the claims library |
| `--store DIR` | file mode: the raw store, so that locators can be checked |

**The tier-4 cache.** The W3C PROV round trip is the most expensive check. Its results are cached under
`$AGENTPROV_HOME/cache/tier4`, keyed by the PROV document's digest and the validator's versions, so `validate` and
`recompute` reuse them (`hits 3` above). A corrupt entry counts as a miss. The cache keeps the most recently used
entries up to 2 GiB, shared by every command on the machine. A large corpus needs more, and a miss costs about four
times the run time of a hit, so on a machine with room raise the cap with
`agentprov settings set compute.validation_cache_gib 32` (D-894; for example, 32 GiB on one development machine).

- **Where the cap applies:** every command that uses the cache: `validate`, `derive`, `recompute`, `verify --level
  rederive` and `import`.
- **What it changes:** it only bounds how much is kept after a run. It never changes a result, because every entry the
  cache serves is a hint the check confirms (D-550).
- **Unset:** the cache keeps its built-in 2 GiB; the setting is how a machine gets more.
- **Desktop app:** there is no field for it in Settings › Compute. Set it with the CLI, and read it back with
  `agentprov settings get compute.validation_cache_gib`.

[Chapter 10](10-troubleshooting.md#workers-and-the-tier-4-cache) has the measured costs, and how far `--jobs` helps.

## verify

`verify` checks integrity, read-only, at three levels:

| Level | What it checks |
|---|---|
| `checksums` | every file against `checksums.sha256`, and no file outside it (closed world) |
| `chain` (default) | the manifest, digests, index, register and counts; AER seals; raw objects and archive-member CRC-32s; SEM and PROV inputs; facets; and that rule catalogues come from the package, not the corpus copy |
| `rederive` | `chain`, plus a byte-identical re-derivation from the stored raw objects |

```text
$ agentprov verify --corpus corpora/demo
agentprov verify: units=1 mode=tree plan=level chain
verify: finished in 140ms (exit 0)
  units    1 of 1: ok 1
agentprov verify: level chain: passed; 0 failed, 0 unverified or tombstoned
root digest sha256:2d5372e2db9b555f0c2c552206363b8694808fe124457b875a1e9091429dcba3
```

```text
$ agentprov verify --corpus corpora/demo --level rederive
agentprov verify: units=1 mode=tree plan=level rederive
…
agentprov verify: level rederive: passed; 0 failed, 0 unverified or tombstoned
root digest sha256:2d5372e2db9b555f0c2c552206363b8694808fe124457b875a1e9091429dcba3
```

A working tree has no `checksums.sha256` yet, so its checks pass "with unverified checks":

```text
$ agentprov verify --corpus corpora/demo.partial
…
agentprov verify: level chain: passed with unverified checks; 0 failed, 1 unverified or tombstoned
  unverified: checksums.absent at checksums.sha256: a working tree has no checksums.sha256 (it is written at sealing)
```

**Release mode and root digests.** A corpus that verifies against itself proves only that it is self-consistent: a
forged corpus can carry its own matching checksums. The **root digest** printed at sealing anchors it. Publish the
root digest somewhere outside the corpus (the paper, the release notes, the deposit page); a recipient then runs:

```text
$ agentprov verify --corpus corpora/demo --release --root-digest sha256:2d5372e2db9b555f0c2c552206363b8694808fe124457b875a1e9091429dcba3
…
agentprov verify: level chain (release mode): passed; 0 failed, 0 unverified or tombstoned
root digest sha256:2d5372e2db9b555f0c2c552206363b8694808fe124457b875a1e9091429dcba3
```

`--release` without `--root-digest` is a usage error (exit 2). In release mode an unverified check fails, and sampling
is not allowed. For a deposit, give one `--root-digest` per corpus in it.

| Option | Use |
|---|---|
| `--level checksums\|chain\|rederive` | the level |
| `--root-digest sha256:HEX` | the externally published root digest (repeatable) |
| `--release` | release mode |
| `--sample N`, `--seed S` | check a seeded sample of N executions (not with `--release`) |
| `--against-pins` | also compare every git origin with the in-package profile pins (reads the fetch cache; `--allow-network` fetches a missing listing) |
| `--jobs N`, `--no-validation-cache` | for `rederive` |

`verify` also takes a deposit directory or a single `.meta.zip`, read without extraction
([chapter 5](05-package-and-deposit.md#verifying-a-deposit)).

## Common errors

| Message | Cause and fix |
|---|---|
| `[corpus.derive.out_exists]` (exit 4) | `--out` must be a new directory |
| `unexplained_change` (exit 1) | bytes changed with no version change: a defect; report it with the `--show-diff` output |
| `[corpus.derive.version_drift]` (exit 4) | the corpus was built by another version; recompute it at its building commit, or re-import |
| `validate --release` exits 1 with all executions passed | the `shacl` tier is not implemented in this build and is always skipped; the summary ends `skipped, not passed: tier shacl …`. Use `--strict` |
| `verify --release: give --root-digest sha256:...` (exit 2) | add the published root digest |
