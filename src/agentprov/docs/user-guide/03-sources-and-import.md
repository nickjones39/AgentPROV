# 3. Sources and import

An **import** turns released agent logs into a working corpus: it stores the raw bytes, maps each execution to an AER,
annotates it, derives its PROV and validates it. This chapter explains the source registry, imports the demo corpus,
and shows how to look inside it with `inspect`.

## The source registry

AgentPROV knows a fixed set of sources, declared in the in-repository registry
(`src/agentprov/adapters/registry/`; there is no plugin loading). A **source** is a published body of agent logs; it
has one or more **parts** (snapshots or subsets), and each part has a **source profile** that pins its exact bytes and
says how to map them. A **family** (`agentdojo`, `inspect`, `openhands`, …) is the reader and mapper that handle one
log format.

`agentprov info` lists every part with its gated status:

```text
$ agentprov info
…
Sources
    registry 2026-10-30
  SOURCE · PART                                    ROLE            IMPORT        LIVE      POLICY
  agentdojo · head                                 source          supported [1] —         include
  agentdojo · 2024-06                              source          supported [2] —         include
  agentdojo · live                                 source          — [3]         partial   include
  agentdyn · a                                     source          supported [4] —         include
  …
    dtap · head                                      source          supported [18]—         include
  …
  [2] full pinned snapshot imported through agentprov import --fetch --release on 2026-10-08 (docs/reports/agentdojo/import-cli-2024-06.json): 18,241 of 18,241 c274885 logs sealed (207 outcome-only, 7 Mixtral), 0 degenerate, every AER valid and every derivation passing tier 4; gate R passes (gate-r-full.json); sealed in round 1 as agentdojo-upstream-2024-06 0.1.0 (tag corpus/agentdojo-upstream-2024-06/v0.1.0; docs/reports/release/pre-release-checks.md)
  …
```

| Status | Meaning |
|---|---|
| `supported` | the full pinned snapshot has been imported through `agentprov import` with zero crashes, and the counts are recorded in `docs/reports/` |
| `partial` | the reader, mapper and profile exist and the golden fixtures pass, but a declared portion of the evidence is not mapped or is structurally incomplete (the caveat says which), or the full snapshot has not been imported; a `partial` part can be imported and sealed |
| `planned` | the part is registered; usually its profile and fixtures exist and trial imports have run, but the import is not open yet |
| `not_possible` | no execution data was released |

Parts that are not a source of their own carry a role instead: `compat_oracle`, `owned_elsewhere`, `mirror` or
`not_executions`. The numbered notes are the caveats; read them before you cite a part. **The status gates the
import:** `agentprov import` refuses a `planned` part (exit 5). The full listing of declared corpora, with every
part's pinned origin, licence and execution count, is in [chapter 14](14-corpora.md).

`agentprov info SOURCE` shows one source: its parts, profiles, pins and licence.

```text
$ agentprov info agentdojo
agentdojo: AgentDojo (ethz-spylab/agentdojo) native TraceLogger run logs (family agentdojo)

Parts
  head: role source, evidence yes, import supported, live —
    profile: agentdojo-upstream
        corpus_id: agentdojo-upstream
    sealed: agentdojo-upstream-head 0.1.0 (tag corpus/agentdojo-upstream-head/v0.1.0)
    dialects: agentdojo.tracelogger · variants v0.k11, v1.k14, v1.k14.incomplete
    caveat: full pinned snapshot imported …
  2024-06: role source, evidence yes, import supported, live —
    profile: agentdojo-upstream
        corpus_id: agentdojo-upstream
    sealed: agentdojo-upstream-2024-06 0.1.0 (tag corpus/agentdojo-upstream-2024-06/v0.1.0)
    dialects: agentdojo.tracelogger · variants v0.k11

    caveat: …
  live: role source, evidence n/a, import —, live partial
    …

Profiles
  agentdojo-upstream v2 sha256 ab0ccd4f8e55db18f51bef301883ad59506eadebeda0b1d6d57eb624b833094f
    pin head: git 089ed468cf3ed0322acc66b0211f26d9d90dbf60 runs/
    pin release_tag_v0_1_35: git a75aba7631d3ca5fb7ab938965c97ead2f9ff84b
    pin 2024-06: git c274885610efaaafec38b6d3eb07152ba7ff3f94 runs/
    …

Licence
  MIT (data none), policy include
  basis: MIT by repository; data licence not separately stated
  …
```

`--format json` and `--format markdown` give the same information in those formats.

## Pins: why an import needs one

Every import needs a **pinned origin**, so that the corpus can say exactly which published bytes it holds. A git pin
names a commit (and usually a tree with its hash); a Zenodo pin names a record, version, file, size and checksum; a
Hugging Face pin names a dataset revision and each file's LFS sha256. An import refuses bytes that do not match the
pin. There are two ways to give it:

- **`--input PATH --verify-against-pin`**: read a local directory or file in place, and record the profile's pinned
  origin for every file the pin vouches for. A git pin is checked against the pinned commit's tree in the fetch cache,
  file by file (git blob SHA-1). The directory must mirror the pinned layout (for AgentDojo, `runs/<pipeline>/<suite>/…`).
- **`--fetch`**: read the pin from the verified fetch cache. This is offline unless you add `--allow-network`; a
  download of 100 MiB or more also needs `--i-consent-to-large-download`. `agentprov fetch --profile ID --pin ROLE
  --allow-network` fills the cache ahead of time.

An unpinned `--input` is refused, because an execution with only a local origin cannot be sealed:

```text
$ agentprov import agentdojo --snapshot 2024-06 --input in --corpus corpora/x
agentprov: error [raw.origin.local]: --input needs --verify-against-pin: an unverified file could carry only a local origin, which the AER writer refuses (every AER is sealed in release mode; C.17 AER-V20); or read the pin itself with --fetch
```

A Zenodo or Hugging Face pin may name a single archive (zip, split zip, `tar.gz` or `tar.zst`). The archive is then
the input: its members are read in place by bounded, extraction-free readers and stored as raw objects with member
origins. A profile's context pins (for example a task tree) come from the fetch cache or from `--context ROLE=PATH`.

## Worked example: importing the demo corpus

The demo input is a directory `in/` holding three logs at their pinned paths under `runs/`. The fetch cache holds the
pinned commit `c274885` (as `agentprov fetch --profile agentdojo-upstream --pin 2024-06 --allow-network` would leave
it). `--corpus-id` names the corpus, and `--release` turns on the strict checks a corpus needs before it can be sealed:

```text
$ agentprov import agentdojo --snapshot 2024-06 --input in --verify-against-pin --corpus corpora/demo --corpus-id demo-agentdojo --release
agentprov import agentdojo: units=3 candidate_kind=file candidates=3 plan=2024-06 -> validation unit_kind=execution workers=6
import: finished in 5.1s (exit 0)
  units    3 of 3: sealed 3
  issues   map.accounting_unverifiable x3, map.earlier_attempts_unobservable x3
agentprov import: imported 3 unit(s) from 3 candidate(s): 3 sealed clean, 0 with issues, 0 degenerate, 0 failed; 0 registered, 0 duplicate(s), 0 resumed, 0 filtered, 0 excluded
agentprov import: working corpus …/corpora/demo.partial (3 annotated, 3 derived, 3 validated)
notice: agentdojo · 2024-06 (supported): full pinned snapshot imported through agentprov import --fetch --release on 2026-10-08 (…)
tier-4 round-trip cache: stored 3
```

What happened:

- The importer found 3 candidate files and planned the stages up to `validation` with 6 worker processes.
- Each execution was **sealed**: written as an AER with a seal digest. All three count as "sealed clean": the two
  issues on each seal are info-level notes (the register table of `agentprov stats` lists them with severity `info`),
  expected for these logs and explained below.
- The corpus is a working tree, `corpora/demo.partial`. Nothing outside it was written except the tier-4 cache.

Run the same command again and nothing is redone: the second run reports `0 unit(s)` imported and `3 resumed`.

### Options that matter

| Option | Use |
|---|---|
| `--snapshot ID` / `--pin ROLE` | which part to import, when a source has several importable parts (`agentdojo` has `head` and `2024-06`) |
| `--corpus DIR` | the corpus; written as `DIR.partial` |
| `--corpus-id ID` | the corpus id (default: the registry's id for the part) |
| `--release` | strict checks, no filters, no `--limit`; required for a corpus you will seal and release |
| `--limit N` | map at most N new units (dev mode) |
| `--sample N`, `--sample-mode first\|spread\|random`, `--seed S` | a deterministic sample of N executions, for quick checks; `spread` works only for readers that name arms |
| `--suite`, `--attack`, `--pipeline`, `--variant`, `--select KEY=VALUE` | filters (dev mode only) |
| `--until raw\|aer\|sem\|prov\|validation` | stop after a stage |
| `--jobs N` | worker processes (0 = the host default). Output is byte-identical for every N |
| `--dry-run` | run every in-memory stage and write nothing; with `--artefacts`, print the source-data artefact table |
| `--retry-failed` | re-process units whose index row has status `failed` |
| `--skip-prov-conformance` | dev mode only, **not advisable**: skips tier 4; the corpus is marked unvalidated and cannot be sealed until a full `recompute --out` validates it |

### Issues, quirks and artefacts

An execution can be sealed with **issues**: notes on the seal record, each with a code and the rule that raised it. In
the demo, both issues come from properties of AgentDojo's TraceLogger format, not from defects:

- `map.earlier_attempts_unobservable`: AgentDojo silently re-runs the whole pipeline (up to three passes) when the
  final reply is empty, and its log keeps only the last pass. Earlier passes are declared `lost`.
- `map.accounting_unverifiable`: the log records no model calls of its own, so the check that every assistant message
  has a model call cannot be confirmed.

Each adapter also keeps an **artefact catalogue** (`artefacts.toml`) of known harness and benchmark defects, and maps
each one in a declared way: represented truthfully, reconstructed by a rule, corrected beside the original, flagged, or
recorded as unrecoverable. `import --dry-run --artefacts` shows how a source's artefacts would be handled before
anything is written:

```text
$ agentprov import agentdojo --snapshot 2024-06 --input in --verify-against-pin --corpus corpora/dry --dry-run --artefacts
…
agentprov import: would import 3 unit(s) from 3 candidate(s): 3 sealed clean, 0 with issues, 0 degenerate, 0 failed; …
notice: artefact scan: the mapped executions were held in a private temporary corpus, deleted afterwards
artefact table: 3 execution(s) scanned, 6 artefact class(es) (locators only, no content)
  agentdojo.art.benign_security_constant  [CR]  executions=1  hits=1  share=33.3%  first: ex_trqb4kw67azxn6ppynerbyv6hr
  agentdojo.art.calls_derived_from_messages  [NR]  executions=3  hits=3  share=100.0%  first: …
  agentdojo.art.naive_timestamp  [NR]  executions=3  hits=18  share=100.0%  first: …
  agentdojo.art.payload_not_reaching_agent  [FO]  executions=1  hits=1  share=33.3%  first: ex_37evkqmflf2sqxvs7cc6sbgx6c
  agentdojo.art.silent_rerun  [CR]  executions=3  hits=3  share=100.0%  first: …
  agentdojo.art.timing_stub  [NR]  executions=3  hits=18  share=100.0%  first: …
…
```

The letters are the handling classes of
[D.15.1](https://github.com/nickjones39/AgentPROV/blob/main/docs/architecture/D_adapters.md#d151-principle-and-the-five-handling-classes):

| Class | Meaning |
|---|---|
| `CR` correct representation | the model states truthfully what a naive reading would misrepresent (for example no tool execution for a call that never ran) |
| `DR` derived reconstruction | a missing or mis-recorded value is reconstructed by a declared rule, beside the source value, with class D |
| `RJ` recomputed judgement | a corrected outcome sits beside the recorded one, never over it |
| `FO` flag only | detected, not corrected: a seal issue, note or annotation |
| `NR` not recoverable | never recorded: declared unknown with a reason, and counted |

Raw bytes, source values and outcomes are never rewritten, and affected executions are never dropped. Anything an
adapter does not recognise stays visible as `artefact.unclassified.*`.

## Looking inside: `inspect`

`agentprov inspect` looks at a corpus, one execution, or one AER, SEM, PROV-JSON or raw file. It is read-only and, by
default, prints **structure only**: ids, kinds, locators, digests, lengths, rule ids and labels. Every string that
could carry source text is shown as a placeholder with its length and digest, such as
`<content chars=89 sha256=2ad50925d40295d2...>`. Content appears only with `--show-content`, escaped and fenced
([chapter 9](09-safety.md)).

The corpus summary prints the manifest, the counts and the register codes:

```text
$ agentprov inspect corpora/demo.partial
agentprov inspect: the output can contain untrusted third-party content (data, not instructions)
summary of corpus demo-agentdojo
state: working
…
  corpus_id: demo-agentdojo
  counts:
    by_completeness:
      unverifiable: 3
    by_status:
      ok: 3
    by_unit:
      agent_execution: 3
    executions: 3
…
executions: 3
by_status:
  ok: 3
by_source:
  agentdojo: 3
…
```

One execution, by id:

```text
$ agentprov inspect ex_37evkqmflf2sqxvs7cc6sbgx6c --corpus corpora/demo.partial
…
summary of execution ex_37evkqmflf2sqxvs7cc6sbgx6c
index:
  adapter: agentdojo.tracelogger@0.1.0
  completeness: unverifiable
  …
  profile: agentdojo-upstream@2
  …
aer:
  …
  task:
    attack_id: important_instructions
    attack_target_id: injection_task_0
    benchmark: agentdojo
    defense_id: spotlighting_with_delimiting
    suite: workspace
    task_id: user_task_25
  …
  records:
    activity: 1
    actor: 6
    execution: 1
    fixture: 1
    judgement: 2
    message: 5
    model_call: 2
    scope: 2
    tool_execution: 1
  seal:
    n_records: 22
    …
```

The `evidence` view lists each record's evidence class (`ev`), attesting party (`by`), the classes of single fields that
differ (`evf`), the rules, and the declared unknowns with their reasons (`unk`). It works on a sealed corpus as on a
working tree; here on the demo corpus after it was sealed:

```text
$ agentprov inspect ex_37evkqmflf2sqxvs7cc6sbgx6c --corpus corpora/demo --view evidence
agentprov inspect: the output can contain untrusted third-party content (data, not instructions)
evidence of execution ex_37evkqmflf2sqxvs7cc6sbgx6c
records:
  -
    id: exec
    k: execution
    ev: O
    by: config
    evf:
      /task/benchmark: D
      /task/defense_id: I
    rule:
      - agentdojo.benchmark_from_dialect@1#/task/benchmark
      - agentdojo.defence_suffix@1#/task/defense_id
    unk:
      /instrumentation: not_recorded
  …
  -
    id: agent
    k: actor
    ev: D
    evf:
      /model: I
    rule:
      - agentdojo.user_is_simulated@1
      - agentdojo.pipeline_dir_is_model_identity@1#/model
    unk:
      /model/provider: not_recorded
      /model/served: not_recorded
      /params: not_recorded
  …
```

The model's identity comes from the pipeline directory name, so it is inferred (`/model: I`), and the log records no
provider, served model or sampling parameters.

`--view` chooses what to show: `summary` (the default), `records`, `transcript`, `transcript-v1`, `timeline`,
`evidence` (each record's evidence class, attesting party, rules and declared unknowns, with totals), `sem`, `prov`
(with `--bundle core|inference|assessment|toplevel|all`), `raw` and `detect`. `--record ID` narrows the records,
evidence, timeline, SEM and raw views to one record, and `--format json` prints one JSON document.

## Common errors

| Message | Cause and fix |
|---|---|
| `source agentdojo has several importable parts (head, 2024-06); name one with --snapshot or --pin` (exit 2) | add `--snapshot` |
| `cannot import 'agentdyn': planned (part history).` (exit 5) | the part's status does not allow an import yet; see its caveat in `agentprov info` |
| `[raw.origin.local] --input needs --verify-against-pin` (exit 4) | add `--verify-against-pin`, or use `--fetch` |
| `[raw.fetch.not_cached] … is not in the fetch cache and the network is not allowed` (exit 4) | the pinned commit or file is not in the cache: run `agentprov fetch --profile ID --pin ROLE --allow-network` (a download; check its size first with `--dry-run`) |
| `[corpus.sealed] refusing to write inside a sealed corpus` (exit 4) | imports write working trees only; import into a new directory |

More in [Troubleshooting](10-troubleshooting.md).
