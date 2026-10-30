# 11. CLI reference

<!-- BEGIN generated: cli (tools/gen_user_guide_cli.py --write) -->

Commands in this reference (subcommands indented):

- [`agentprov`](#agentprov)
- [`agentprov info`](#agentprov-info) (alias sources)
- [`agentprov validate`](#agentprov-validate)
- [`agentprov import`](#agentprov-import) (alias convert)
- [`agentprov fetch`](#agentprov-fetch)
- [`agentprov run`](#agentprov-run)
- [`agentprov models`](#agentprov-models)
- [`agentprov backends`](#agentprov-backends)
  - [`agentprov backends build`](#agentprov-backends-build)
- [`agentprov migrate`](#agentprov-migrate)
  - [`agentprov migrate verify-baseline`](#agentprov-migrate-verify-baseline)
  - [`agentprov migrate gate-a`](#agentprov-migrate-gate-a)
  - [`agentprov migrate gate-b`](#agentprov-migrate-gate-b)
  - [`agentprov migrate gate-d`](#agentprov-migrate-gate-d)
  - [`agentprov migrate gate-e`](#agentprov-migrate-gate-e)
  - [`agentprov migrate gate`](#agentprov-migrate-gate)
- [`agentprov render`](#agentprov-render)
- [`agentprov inspect`](#agentprov-inspect)
- [`agentprov purge`](#agentprov-purge)
- [`agentprov stats`](#agentprov-stats)
- [`agentprov package`](#agentprov-package)
- [`agentprov derive`](#agentprov-derive)
- [`agentprov recompute`](#agentprov-recompute)
- [`agentprov verify`](#agentprov-verify)
- [`agentprov settings`](#agentprov-settings)
  - [`agentprov settings list`](#agentprov-settings-list)
  - [`agentprov settings get`](#agentprov-settings-get)
  - [`agentprov settings set`](#agentprov-settings-set)
  - [`agentprov settings unset`](#agentprov-settings-unset)
- [`agentprov keys`](#agentprov-keys)
  - [`agentprov keys status`](#agentprov-keys-status)
  - [`agentprov keys list`](#agentprov-keys-list)
  - [`agentprov keys set`](#agentprov-keys-set)
  - [`agentprov keys delete`](#agentprov-keys-delete)
- [`agentprov prices`](#agentprov-prices)
  - [`agentprov prices list`](#agentprov-prices-list)
  - [`agentprov prices get`](#agentprov-prices-get)
  - [`agentprov prices set`](#agentprov-prices-set)
  - [`agentprov prices unset`](#agentprov-prices-unset)
  - [`agentprov prices refresh`](#agentprov-prices-refresh)
- [`agentprov estimate`](#agentprov-estimate)
- [`agentprov jobs`](#agentprov-jobs)
  - [`agentprov jobs start`](#agentprov-jobs-start)
  - [`agentprov jobs list`](#agentprov-jobs-list)
  - [`agentprov jobs show`](#agentprov-jobs-show)
  - [`agentprov jobs follow`](#agentprov-jobs-follow)
  - [`agentprov jobs stop`](#agentprov-jobs-stop)
  - [`agentprov jobs drain`](#agentprov-jobs-drain)
  - [`agentprov jobs resume`](#agentprov-jobs-resume)
  - [`agentprov jobs kill`](#agentprov-jobs-kill)
  - [`agentprov jobs prune`](#agentprov-jobs-prune)
- [`agentprov batch`](#agentprov-batch)
  - [`agentprov batch create`](#agentprov-batch-create)
  - [`agentprov batch start`](#agentprov-batch-start)
  - [`agentprov batch resume`](#agentprov-batch-resume)
  - [`agentprov batch run`](#agentprov-batch-run)
  - [`agentprov batch stop`](#agentprov-batch-stop)
  - [`agentprov batch list`](#agentprov-batch-list)
  - [`agentprov batch show`](#agentprov-batch-show)
- [`agentprov devrun`](#agentprov-devrun)
  - [`agentprov devrun plan`](#agentprov-devrun-plan)
  - [`agentprov devrun start`](#agentprov-devrun-start)
  - [`agentprov devrun list`](#agentprov-devrun-list)
  - [`agentprov devrun prune`](#agentprov-devrun-prune)

## agentprov

```text
usage: agentprov [-h] [--version] [-v] [-q] [--log-format {text,json}] [--log-file PATH]
                 [--log-content] [--progress {off,summary,status,steps,trace}]
                 [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                 [--progress-interval SECONDS] [--progress-max-bytes N] [--control-file PATH]
                 [--show-content] [--content-chars N] [--json] [--summary-json PATH]
                 [--max-listed N] [--no-colour] [--break-stale-lock]
                 COMMAND ...

AgentPROV: execution provenance for LLM-agent security research.

positional arguments:
  COMMAND
    info (sources)      versions, the source registry, installed extras and tools, host and
                        isolation grade
    validate            validate AER files (tier 2) or a corpus's stored outputs (tiers aer, sem,
                        prov, linkage)
    import (convert)    ingest released artefacts into a working corpus (store, map, seal, derive,
                        validate)
    fetch               fetch pinned upstream bytes into the verified cache (needs --allow-
                        network)
    run                 live capture through a backend worker (scripted or real model; --dry-run
                        prints the plan)
    models              list the models a local server serves (and one model's observed identity),
                        or an API provider's list
    backends            backend environments (build)
    migrate             baseline migration gates G0, A, B, D and E (J.3)
    render              draw selected executions' PROV graphs (needs the render extra and Graphviz
                        dot)
    inspect             look at one execution, artefact or corpus (read-only; content hidden
                        unless --show-content)
    purge               remove a leaked object from a working corpus or the fetch cache, leaving a
                        tombstone (irreversible)
    stats               generic statistics over corpora: counts, PROV statements, unknowns, field-
                        group coverage
    package             seal a working corpus (DIR.partial -> DIR), or build an offline deposit
                        draft from sealed corpora
    derive              add missing derived layers (SEM, PROV, validation, views, compat, TriG) as
                        a new corpus version
    recompute           re-derive a corpus from its raw objects or stored AERs and compare bytes
                        (H.8.4)
    verify              verify a corpus or a deposit: checksums, the raw -> AER -> SEM -> PROV
                        digest chain, or a re-derivation
    settings            list, get, set or unset the shared user settings
    keys                endpoint keys in the OS keychain (names only are ever shown)
    prices              list, set or refresh the model prices the estimate uses
    estimate            the cost and time of a live run before it starts (p50/p90; no model call)
    jobs                start, list, follow, stop or prune detached jobs
    batch               ordered job lists that run as one job
    devrun              dev runs: a few samples of every part, imported and checked

options:
  -h, --help            show this help message and exit

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

## agentprov info

Alias: `sources`.

```text
usage: agentprov info [-h] [--version] [-v] [-q] [--log-format {text,json}] [--log-file PATH]
                      [--log-content] [--progress {off,summary,status,steps,trace}]
                      [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                      [--progress-interval SECONDS] [--progress-max-bytes N] [--control-file PATH]
                      [--show-content] [--content-chars N] [--json] [--summary-json PATH]
                      [--max-listed N] [--no-colour] [--break-stale-lock] [--source SOURCE]
                      [--matrix | --must-not-claim] [--format {text,markdown,json}]
                      [SOURCE]

Show versions, the source registry (per part, gated statuses), installation and host (N.2.9).

positional arguments:
  SOURCE                a registered source id: parts, profiles, pins, licence

options:
  -h, --help            show this help message and exit
  --source SOURCE       same as SOURCE
  --matrix              the compatibility matrix (needs the claims library; deferred)
  --must-not-claim      the must-not-claim items (need the claims library; deferred)
  --format {text,markdown,json}
                        payload format (default text)

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

## agentprov validate

```text
usage: agentprov validate [-h] [--version] [-v] [-q] [--log-format {text,json}] [--log-file PATH]
                          [--log-content] [--progress {off,summary,status,steps,trace}]
                          [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                          [--progress-interval SECONDS] [--progress-max-bytes N]
                          [--control-file PATH] [--show-content] [--content-chars N] [--json]
                          [--summary-json PATH] [--max-listed N] [--no-colour]
                          [--break-stale-lock] [--aer PATH] [--store DIR] [--corpus DIR]
                          [--tiers LIST] [--prov-spec SPEC] [--strict | --release] [--report PATH]
                          [--sample N] [--seed S] [--card CARD.md] [--jobs N] [--in-process]
                          [--no-validation-cache] [--dry-run]
                          [FILE ...]

Validate AgentPROV Execution Record files (tier 2), or re-run the tiers aer, sem, prov and linkage
over a corpus's stored outputs, read-only (--corpus; N.2.5). Checks that cannot run are reported
as skipped, never as passed.

positional arguments:
  FILE                  files to validate (type detected by suffix: .aer.jsonl)

options:
  -h, --help            show this help message and exit
  --aer PATH            an AER file, whatever its suffix (repeatable)
  --store DIR           raw store directory (objects/<h0h1>/<sha256>); without it locator checks
                        are skipped
  --corpus DIR          validate a corpus's stored outputs, read-only (sealed, working or
                        .partial)
  --tiers LIST          comma list from aer,sem,prov,linkage,shacl,regression (default
                        aer,sem,prov,linkage)
  --prov-spec SPEC      corpus mode: the PROV spec (agentprov-prov/0.1)
  --strict              a skipped check fails
  --release             implies --strict, release-mode validator, every applicable tier
  --report PATH         corpus mode: write the report to PATH (outside the corpus; - = stdout)
  --sample N            corpus mode: validate a seeded sample of N executions
  --seed S              sampling seed
  --card CARD.md        lint a corpus card with the claims library (N.2.5(7))
  --jobs N              corpus mode: worker processes for tiers sem, prov and linkage (0 = host
                        default)
  --in-process          corpus mode: run every tier in this process (no workers; allowed with
                        --release, AD-10 row 17)
  --no-validation-cache
                        corpus mode: always run the tier-4 PROV-O round trip; neither read nor
                        write the round-trip cache under $AGENTPROV_HOME/cache/tier4 (D-550).
                        --release never reads it either: it recomputes every round trip and audits
                        the entries it finds
  --dry-run             accepted (file validation never writes)

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

## agentprov import

Alias: `convert`.

```text
usage: agentprov import [-h] [--version] [-v] [-q] [--log-format {text,json}] [--log-file PATH]
                        [--log-content] [--progress {off,summary,status,steps,trace}]
                        [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                        [--progress-interval SECONDS] [--progress-max-bytes N]
                        [--control-file PATH] [--show-content] [--content-chars N] [--json]
                        [--summary-json PATH] [--max-listed N] [--no-colour] [--break-stale-lock]
                        [--corpus DIR] [--input PATH] [--fetch] [--allow-network]
                        [--cache-dir DIR] [--verify-against-pin] [--i-consent-to-large-download]
                        [--context ROLE=PATH] [--no-context ROLE] [--profile ID] [--pin ROLE]
                        [--snapshot ID] [--spec SPEC.toml] [--corpus-id ID] [--suite S]
                        [--attack A] [--pipeline P] [--variant V] [--select KEY=VALUE[,VALUE...]]
                        [--limit N] [--sample N] [--sample-mode {first,spread,random}] [--seed S]
                        [--until {raw,aer,sem,prov,validation}] [--prov-spec SPEC]
                        [--retry-failed] [--release] [--skip-prov-conformance] [--jobs N]
                        [--in-process] [--size-hints DIR] [--allow-hardlinks]
                        [--no-validation-cache] [--dry-run] [--artefacts] [--max-file-bytes N]
                        [--max-json-depth N]
                        [SOURCE]

Ingest released artefacts into DIR.partial (N.2.2): raw store, AER, PROV and validation.

positional arguments:
  SOURCE                registry source id or alias; optional with --spec

options:
  -h, --help            show this help message and exit
  --corpus DIR          the working corpus directory (written as DIR.partial)

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead

origin:
  --input PATH          local origin: a directory or one file, read in place
  --fetch               read the profile's pin from the verified fetch cache (offline unless
                        --allow-network)
  --allow-network       with --fetch: fetch the pin when the cache lacks it (otherwise refused:
                        raw.fetch.not_cached)
  --cache-dir DIR       fetch cache (default $AGENTPROV_UPSTREAM_CACHE, else
                        $AGENTPROV_HOME/cache)
  --verify-against-pin  record the pinned origin for --input files the pin vouches for
  --i-consent-to-large-download
                        with --fetch of a download pin: consent to a download of 100 MiB or more
                        (U-07)
  --context ROLE=PATH   a local copy of a declared context pin (checked against the pin); default:
                        the fetch cache
  --no-context ROLE     map without a declared context role (its per-unit artefacts are then
                        absent; a notice, and the role is recorded in the snapshot's
                        context_skipped)

profile and snapshot:
  --profile ID          import profile (default: the registry's profile for the part)
  --pin ROLE            profile pin role, e.g. 2024-06 or release
  --snapshot ID         snapshot id inside the corpus (default: the registry part)
  --spec SPEC.toml      committed corpus spec (deferred in this build)
  --corpus-id ID        corpus id (default: the registry's corpus id for the part)

selection:
  --suite S
  --attack A
  --pipeline P
  --variant V
  --select KEY=VALUE[,VALUE...]
                        AER-header filter (repeatable)
  --limit N             map at most N new units (0 maps nothing)
  --sample N            dev runs: a deterministic sample of N executions, chosen before mapping
                        (D-529; partial corpus)
  --sample-mode {first,spread,random}
                        with --sample: first N by key (default), round-robin over the reader's
                        arms, or seeded random
  --seed S              with --sample-mode random: the seed (recorded in the manifest)

stages:
  --until {raw,aer,sem,prov,validation}
                        stop after this stage (default: validation)
  --prov-spec SPEC      PROV spec (repeatable; default agentprov-prov/0.1)

mode:
  --retry-failed        re-process units whose row has status failed
  --release             release mode: strict checks, no filters, no --limit, no --in-process
  --skip-prov-conformance
                        dev mode only, not advisable: skip the W3C PROV conformance check (tier
                        4); the corpus is marked unvalidated until a full recompute --out NEW, and
                        cannot be sealed (G2c-5)
  --jobs N              worker processes (0 = host default; default 0)
  --in-process          debugging only: run expand, map and prov in this process
  --size-hints DIR      a previous version of this corpus (read-only): its stored PROV sizes set
                        each prov job's memory charge, so more jobs run at once (D-554; timing
                        only, never outputs)
  --allow-hardlinks     accept st_nlink > 1 files in an --input tree
  --no-validation-cache
                        do not store the tier-4 round trips in $AGENTPROV_HOME/cache/tier4 (D-550)
  --dry-run             run every in-memory stage; write nothing
  --artefacts           with --dry-run: scan the mapped executions for source-data artefacts and
                        print the per-class table (D.15.4)

tier-1 overrides:
  --max-file-bytes N
  --max-json-depth N
```

## agentprov fetch

```text
usage: agentprov fetch [-h] [--version] [-v] [-q] [--log-format {text,json}] [--log-file PATH]
                       [--log-content] [--progress {off,summary,status,steps,trace}]
                       [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                       [--progress-interval SECONDS] [--progress-max-bytes N]
                       [--control-file PATH] [--show-content] [--content-chars N] [--json]
                       [--summary-json PATH] [--max-listed N] [--no-colour] [--break-stale-lock]
                       [--corpus DIR] [--profile ID] [--only sha256:HEX] [--pin ROLE] [--history]
                       [--path PREFIX] [--cache-dir DIR] [--allow-network]
                       [--i-consent-to-large-download] [--dry-run]

Populate the verified, extraction-free fetch cache from in-package pins (N.2.2; G.7.5).

options:
  -h, --help            show this help message and exit

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead

what to fetch (exactly one):
  --corpus DIR          fetch the objects of DIR/raw/REFERENCES.json (the corpus is never written)
  --profile ID          fetch the pins of a shipped source profile

selection:
  --only sha256:HEX     with --corpus: only this object (repeatable)
  --pin ROLE            with --profile: a pin role (repeatable; default: the primary pins)
  --history             with --profile: fetch the blobless full history of the git pins and
                        compute the introducing-commit index (D.6.16)
  --path PREFIX         with --profile: a path prefix inside a git pin (repeatable)

network and cache:
  --cache-dir DIR       cache directory (default $AGENTPROV_UPSTREAM_CACHE, else
                        $AGENTPROV_HOME/cache)
  --allow-network       permit the network access fetching needs (required unless --dry-run)
  --i-consent-to-large-download
                        consent to a download of 100 MiB or more (U-07)
  --dry-run             print the plan; no network and no writes
```

## agentprov run

```text
usage: agentprov run [-h] [--version] [-v] [-q] [--log-format {text,json}] [--log-file PATH]
                     [--log-content] [--progress {off,summary,status,steps,trace}]
                     [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                     [--progress-interval SECONDS] [--progress-max-bytes N] [--control-file PATH]
                     [--show-content] [--content-chars N] [--json] [--summary-json PATH]
                     [--max-listed N] [--no-colour] [--break-stale-lock] [--corpus DIR]
                     [--campaign NAME | --corpus-id ID] [--plan PLAN.toml] [--spec SPEC.toml]
                     [--suite S[,S...]] [--benchmark-version V] [--user-tasks SPEC]
                     [--attack A[,A...]] [--injection-tasks SPEC]
                     [--benign {include,exclude,only}] [--defence NAME] [--task NAME]
                     [--task-param KEY=VALUE] [--samples limit:N|ID[,ID...]] [--epochs N]
                     [--message-limit N] [--token-limit N] [--time-limit SECONDS]
                     [--max-connections N] [--cell-size N] [--judge ROLE=MODEL]
                     [--model SHORTHAND] [--endpoint NAME] [--model-id ID]
                     [--defence-endpoint NAME] [--llm-script SCRIPT.json]
                     [--llm-element {native,gateway_compat}] [--model-display-name NAME]
                     [--temperature T] [--reasoning-effort LEVEL] [--max-tokens N|harness-default]
                     [--temperature-policy {as-benchmark,inject}] [--allow-text-tool-calls]
                     [--base-url URL] [--accept-served-model ID] [--allow-lan-endpoint]
                     [--no-hash-weights] [--repeats N] [--max-attempts N] [--retry-inconsistent]
                     [--allow-mixed-config] [--limit N] [--canary N] [--preflight-only]
                     [--dry-run] [--plan-json] [--catalogue] [--keep-staging]
                     [--cell-timeout SECONDS] [--jobs N] [--start-stagger SECONDS]
                     [--env-file PATH] [--env-stdin] [--keychain] [--allow-custom-endpoint]
                     [--skip-prov-conformance] [--i-consent-to-api-costs]
                     [--i-consent-to-local-run] [--containment {sandbox-exec,dedicated-user,vm}]
                     [--autodojo-cache PATH] [--autodojo-variant K] [--allow-network]
                     [--max-calls N] [--max-cost-usd USD] [--price-in USD_PER_MTOK]
                     [--price-out USD_PER_MTOK] [--preset NAME] [--m5ultra] [--model-dir PATH]
                     [--model-size-gb GB] [--active-params-b B] [--context-tokens N]
                     [--kv-gb-per-trace GB] [--server-max-concurrency N] [--tune-jobs N[,N...]]
                     [--tune-out DIR]
                     SOURCE

Execute a live backend and capture raw evidence (N.2.1, N.2.1b). Needs a built backend environment
('agentprov backends build'); real-model runs also need .env, --containment and consent.

positional arguments:
  SOURCE                live source: agentdojo, agentdyn, agentharm or autodojo

options:
  -h, --help            show this help message and exit
  --corpus DIR          working corpus directory
  --campaign NAME       corpus id <source>-live-<NAME>
  --corpus-id ID

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead

cells (exclusive with --plan):
  --plan PLAN.toml      committed run plan
  --spec SPEC.toml      corpus spec with [live]
  --suite S[,S...]
  --benchmark-version V
  --user-tasks SPEC
  --attack A[,A...]
  --injection-tasks SPEC
  --benign {include,exclude,only}
  --defence, --defense NAME

Inspect plans (an inspect-<benchmark> backend; D-663; exclusive with the cell options):
  --task NAME           Inspect task (the catalogue lists them), e.g. inspect_evals/agentharm
  --task-param KEY=VALUE
                        a task parameter the catalogue declares (repeatable; VALUE as a TOML
                        scalar or a string)
  --samples limit:N|ID[,ID...]
                        the samples: the first N of the split, or ids
  --epochs N
  --message-limit N     per sample (mandatory for Inspect, D-667)
  --token-limit N       per sample (mandatory for Inspect, D-667)
  --time-limit SECONDS  per sample (mandatory for Inspect, D-667)
  --max-connections N   concurrent model calls of one cell
  --cell-size N         samples per cell (one Inspect eval per cell)
  --judge ROLE=MODEL    the model of a judge role of the task's scorer (repeatable; every role is
                        required, D-667); judges use the agent's endpoint and key

model (one of: --model, --endpoint with --model-id, --llm-script):
  --model SHORTHAND     endpoint shorthand from endpoints.toml
  --endpoint NAME       explicit endpoint (deepseek, openai, openrouter, anthropic, local, ollama,
                        omlx, lmstudio, mlx_lm, llamacpp, vllm)
  --model-id ID
  --defence-endpoint NAME
                        the endpoint (endpoints.toml shorthand) a defence calls for its own model
                        or embedding calls (D-675; MELON's embeddings); only its key enters the
                        worker
  --llm-script SCRIPT.json
                        scripted transport: no network, no keys (test_only)
  --llm-element {native,gateway_compat}
  --model-display-name NAME
  --temperature T
  --reasoning-effort LEVEL
  --max-tokens N|harness-default
                        Anthropic endpoints (required there): the reply's token cap, stated (N) or
                        the harness default 16000 (harness-default, recorded as a harness policy);
                        AgentDojo's own 1024 is never used silently (D-656)
  --temperature-policy {as-benchmark,inject}
  --allow-text-tool-calls
                        run an endpoint that returns text-encoded tool calls

local model servers (D-691..D-694):
  --base-url URL        a local endpoint's base URL (loopback; overrides .env and the registry
                        default; recorded)
  --accept-served-model ID
                        a served model id that may differ from the requested one (repeatable;
                        recorded; A12)
  --allow-lan-endpoint  allow a local endpoint on a literal private LAN address (D-698): prompts
                        and replies leave this machine over plain http; keyless; recorded
  --no-hash-weights     record a local model's weight files by size only (weights_hashed false)

control:
  --repeats N
  --max-attempts N
  --retry-inconsistent
  --allow-mixed-config
  --limit N
  --canary N            canary cells (default 10; 0 disables)
  --preflight-only      run the endpoint preflight probes and exit
  --dry-run             resolve and print the plan; run nothing
  --plan-json           with --dry-run: print the expanded plan, one row per cell, as one JSON
                        document on stdout (D-651; names and counts only)
  --catalogue           print the suites, user and injection tasks and attacks the backend offers
                        for --benchmark-version as one JSON document on stdout (D-652); no model
                        call, nothing written
  --keep-staging        keep each session's staging directory after it is stored (inspection;
                        K.8.5 live_artefacts)
  --cell-timeout SECONDS
                        per-cell wall clock before the worker is killed and the session sealed
                        aborted (default 1800)
  --jobs N              concurrent traces (>= 1; default 1, or computed with a local preset)
  --start-stagger SECONDS
                        spread the first cell start of each worker

environment and consent:
  --env-file PATH
  --env-stdin           read the endpoint variables as one JSON object from stdin (D-395; for a
                        GUI with a keychain); exclusive with --env-file, and the default .env is
                        not read
  --keychain            read the selected endpoint's key from the OS keychain (agentprov keys;
                        D-702); exclusive with --env-file and --env-stdin, and the default .env is
                        not read
  --allow-custom-endpoint
  --skip-prov-conformance
                        not advisable: skip the W3C PROV conformance check (tier 4) of each
                        session; the corpus is marked unvalidated until a full recompute --out
                        NEW, and cannot be sealed (G2c-5)
  --i-consent-to-api-costs
  --i-consent-to-local-run
                        consent for a run against a local model server (D-726); not consent for an
                        API endpoint
  --containment {sandbox-exec,dedicated-user,vm}
  --autodojo-cache PATH
                        AutoDojo attack cache copied from the pinned fork (verified against its
                        tree; D.11.3 rule 5)
  --autodojo-variant K  the cache's variant index (integer >= 0)
  --allow-network       let T0 fetch the pinned AutoDojo commit into the fetch cache to verify
                        --autodojo-cache

API caps (D-725: required for an API endpoint, optional otherwise):
  --max-calls N         billed model calls of the corpus at most, preflight probes included; a
                        cell starts only if its worst case fits
  --max-cost-usd USD    spend of the corpus at most (an upper bound priced from the recorded
                        usage); needs --price-in and --price-out
  --price-in USD_PER_MTOK
                        USD per million input-side tokens (the highest of input, cache write and
                        cached)
  --price-out USD_PER_MTOK
                        USD per million output tokens

local models and presets (N.2.1a):
  --preset NAME         host preset from package data (v0.1: m5ultra)
  --m5ultra             shorthand for --preset m5ultra
  --model-dir PATH      read the model's config.json and weight sizes (untrusted input)
  --model-size-gb GB    weight size, decimal gigabytes
  --active-params-b B   active parameters, billions
  --context-tokens N
  --kv-gb-per-trace GB
  --server-max-concurrency N
                        the local server's concurrent-request limit
  --tune-jobs N[,N...]  the concurrency sweep (N.2.1a(4), D-820): the same cell sample at each
                        --jobs value, one working corpus per value, and a report recommending the
                        smallest N within 90 % of the peak traces per hour with no timeouts (a
                        local endpoint only)
  --tune-out DIR        the sweep's folder (default $AGENTPROV_HOME/calibration/tune-jobs-<UTC
                        stamp>)
```

## agentprov models

```text
usage: agentprov models [-h] [--version] [-v] [-q] [--log-format {text,json}] [--log-file PATH]
                        [--log-content] [--progress {off,summary,status,steps,trace}]
                        [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                        [--progress-interval SECONDS] [--progress-max-bytes N]
                        [--control-file PATH] [--show-content] [--content-chars N] [--json]
                        [--summary-json PATH] [--max-listed N] [--no-colour] [--break-stale-lock]
                        [--endpoint NAME] [--base-url URL] [--model-id ID] [--model-dir PATH]
                        [--no-hash-weights] [--find-folders] [--allow-lan-endpoint]
                        [--allow-network] [--refresh-if-stale] [--keychain] [--env-file PATH]
                        [--env-stdin] [--format {text,json}]

Local model servers (loopback only; read-only, no inference): the models each local endpoint of
endpoints.toml serves, or one server's, and with --model-id the identity record a live run records
(D-691). API providers (D-730): the dated cached model list; --allow-network fetches it now (no
tokens, no cost).

options:
  -h, --help            show this help message and exit
  --endpoint NAME       an endpoint shorthand: local (ollama, omlx, lmstudio, mlx_lm, llamacpp,
                        vllm) or an API provider (openrouter, anthropic, openai, deepseek, gemini,
                        llama, qwen, glm)
  --base-url URL        a loopback base URL (overrides the endpoint's; the server kind is
                        fingerprinted)
  --model-id ID         show the observed identity of this served model
  --model-dir PATH      the model's directory or file, where the server does not name it (oMLX,
                        llama.cpp); hashed, never parsed
  --no-hash-weights     record weight files by size only (weights_hashed false)
  --find-folders        with --model-id: list the folders on this machine that may hold the
                        model's files (oMLX, the Hugging Face cache, LM Studio; names only,
                        nothing opened, no server contacted; D-828)
  --allow-lan-endpoint  allow --base-url on a literal private LAN address (D-698; data leaves this
                        machine)
  --format {text,json}  payload format (default text)

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead

API providers (D-730..D-735):
  --allow-network       fetch the provider's model list now (R2; the provider's registry host
                        only) and cache it
  --refresh-if-stale    fetch only when the setting models.auto_refresh is on and the cached list
                        is older than 24 h; otherwise show the cache
  --keychain            read the endpoint's key from the OS keychain (D-702): an API provider's,
                        or a local server's optional key (D-827); exclusive with --env-file/--env-
                        stdin
  --env-file PATH       read the endpoint's key variable from this .env file
  --env-stdin           read the endpoint variables as one JSON object from stdin (D-395)
```

## agentprov backends

```text
usage: agentprov backends [-h] [--version] [-v] [-q] [--log-format {text,json}] [--log-file PATH]
                          [--log-content] [--progress {off,summary,status,steps,trace}]
                          [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                          [--progress-interval SECONDS] [--progress-max-bytes N]
                          [--control-file PATH] [--show-content] [--content-chars N] [--json]
                          [--summary-json PATH] [--max-listed N] [--no-colour]
                          [--break-stale-lock]
                          ACTION ...

Backend environments for live runs (N.2.10).

positional arguments:
  ACTION
    build               build $AGENTPROV_HOME/envs/<backend>-<commit8>/ with uv sync --locked
                        --no-config

options:
  -h, --help            show this help message and exit

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

### agentprov backends build

```text
usage: agentprov backends build [-h] [--version] [-v] [-q] [--log-format {text,json}]
                                [--log-file PATH] [--log-content]
                                [--progress {off,summary,status,steps,trace}]
                                [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                                [--progress-interval SECONDS] [--progress-max-bytes N]
                                [--control-file PATH] [--show-content] [--content-chars N]
                                [--json] [--summary-json PATH] [--max-listed N] [--no-colour]
                                [--break-stale-lock] [--offline-check] [--allow-network]
                                [--defence-assets ID[,ID...]] [--defence-source DIR]
                                [--env-file PATH] [--dry-run]
                                BACKEND

Build a backend environment from backends/<backend>/ (N.2.10). Without --allow-network the sync
runs offline from the uv cache.

positional arguments:
  BACKEND               agentdojo, autodojo, agentdyn, inspect-agentharm

options:
  -h, --help            show this help message and exit
  --offline-check       verify an existing build; no network, no writes
  --allow-network       let uv download packages (otherwise --offline)
  --defence-assets ID[,ID...]
                        also provision these registry defences' pinned code from the fetch cache
                        into the environment (D-670;
                        backends/shared/src/agentprov_backend/defences.toml)
  --defence-source DIR  read --defence-assets' pinned code from this local tree instead of the
                        fetch cache; each file is accepted only by its pinned sha256 and git blob
                        id (no network)
  --env-file PATH       the .env file (not read by the agentdojo build)
  --dry-run             print the plan; run and write nothing

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

## agentprov migrate

```text
usage: agentprov migrate [-h] [--version] [-v] [-q] [--log-format {text,json}] [--log-file PATH]
                         [--log-content] [--progress {off,summary,status,steps,trace}]
                         [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                         [--progress-interval SECONDS] [--progress-max-bytes N]
                         [--control-file PATH] [--show-content] [--content-chars N] [--json]
                         [--summary-json PATH] [--max-listed N] [--no-colour] [--break-stale-lock]
                         GATE-COMMAND ...

Run the baseline migration gates (N.2.14; J.3.0). Implemented: verify-baseline (G0), gate-a,
gate-b, gate-d, gate-e.

positional arguments:
  GATE-COMMAND
    verify-baseline     gate G0: verify the old repository, its corpora and the baseline
                        environment against the lock
    gate-a              gate A: v1 -> AER -> v1 view, A1 (JCS) and A2 (bytes), from the AER alone
    gate-b              gate B: adprov-v2.3-compat graph bytes (B1 from the view, B2 from the
                        source)
    gate-d              gate D: SEM and agentprov-prov/0.1 re-derived from stored AERs and
                        validated in every D8 tier (release mode)
    gate-e              gate E: the semantic diff of the compat graphs against agentprov-prov/0.1,
                        from semdiff-map.toml
    gate                run one gate by name: G0, A, B, D or E

options:
  -h, --help            show this help message and exit

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

### agentprov migrate verify-baseline

```text
usage: agentprov migrate verify-baseline [-h] [--version] [-v] [-q] [--log-format {text,json}]
                                         [--log-file PATH] [--log-content]
                                         [--progress {off,summary,status,steps,trace}]
                                         [--progress-format {auto,tty,plain,jsonl}]
                                         [--progress-file PATH] [--progress-interval SECONDS]
                                         [--progress-max-bytes N] [--control-file PATH]
                                         [--show-content] [--content-chars N] [--json]
                                         [--summary-json PATH] [--max-listed N] [--no-colour]
                                         [--break-stale-lock] [--scope {golden,full}]
                                         [--workers N] [--release] [--report PATH]
                                         [--reports-dir DIR] [--config FILE] [--in-process]

gate G0: verify the old repository, its corpora and the baseline environment against the lock

options:
  -h, --help            show this help message and exit
  --scope {golden,full}
                        golden: the golden set (CI); full: the baseline trees (local). Default:
                        golden (G0: full)
  --workers N           worker processes for mapping (0 = host default; default 8 or [run] workers
                        of the config)
  --release             release mode: params.strict true, skipped checks fail, T1 isolation grade
                        must be watchdog or better
  --report PATH         write the gate report to PATH (atomic); default <reports-
                        dir>/<gate>/<date>-<commit>.json
  --reports-dir DIR     reports directory (default $AGENTPROV_HOME/migration/reports); predecessor
                        reports are looked up here and in the repository's migration/reports
  --config FILE         migration config (default migration/local.toml when it exists)
  --in-process          debugging only: map in this process (refused with --release)

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

### agentprov migrate gate-a

```text
usage: agentprov migrate gate-a [-h] [--version] [-v] [-q] [--log-format {text,json}]
                                [--log-file PATH] [--log-content]
                                [--progress {off,summary,status,steps,trace}]
                                [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                                [--progress-interval SECONDS] [--progress-max-bytes N]
                                [--control-file PATH] [--show-content] [--content-chars N]
                                [--json] [--summary-json PATH] [--max-listed N] [--no-colour]
                                [--break-stale-lock] [--scope {golden,full}] [--workers N]
                                [--release] [--report PATH] [--reports-dir DIR] [--config FILE]
                                [--in-process]

gate A: v1 -> AER -> v1 view, A1 (JCS) and A2 (bytes), from the AER alone

options:
  -h, --help            show this help message and exit
  --scope {golden,full}
                        golden: the golden set (CI); full: the baseline trees (local). Default:
                        golden (G0: full)
  --workers N           worker processes for mapping (0 = host default; default 8 or [run] workers
                        of the config)
  --release             release mode: params.strict true, skipped checks fail, T1 isolation grade
                        must be watchdog or better
  --report PATH         write the gate report to PATH (atomic); default <reports-
                        dir>/<gate>/<date>-<commit>.json
  --reports-dir DIR     reports directory (default $AGENTPROV_HOME/migration/reports); predecessor
                        reports are looked up here and in the repository's migration/reports
  --config FILE         migration config (default migration/local.toml when it exists)
  --in-process          debugging only: map in this process (refused with --release)

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

### agentprov migrate gate-b

```text
usage: agentprov migrate gate-b [-h] [--version] [-v] [-q] [--log-format {text,json}]
                                [--log-file PATH] [--log-content]
                                [--progress {off,summary,status,steps,trace}]
                                [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                                [--progress-interval SECONDS] [--progress-max-bytes N]
                                [--control-file PATH] [--show-content] [--content-chars N]
                                [--json] [--summary-json PATH] [--max-listed N] [--no-colour]
                                [--break-stale-lock] [--scope {golden,full}] [--workers N]
                                [--release] [--report PATH] [--reports-dir DIR] [--config FILE]
                                [--in-process]

gate B: adprov-v2.3-compat graph bytes (B1 from the view, B2 from the source)

options:
  -h, --help            show this help message and exit
  --scope {golden,full}
                        golden: the golden set (CI); full: the baseline trees (local). Default:
                        golden (G0: full)
  --workers N           worker processes for mapping (0 = host default; default 8 or [run] workers
                        of the config)
  --release             release mode: params.strict true, skipped checks fail, T1 isolation grade
                        must be watchdog or better
  --report PATH         write the gate report to PATH (atomic); default <reports-
                        dir>/<gate>/<date>-<commit>.json
  --reports-dir DIR     reports directory (default $AGENTPROV_HOME/migration/reports); predecessor
                        reports are looked up here and in the repository's migration/reports
  --config FILE         migration config (default migration/local.toml when it exists)
  --in-process          debugging only: map in this process (refused with --release)

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

### agentprov migrate gate-d

```text
usage: agentprov migrate gate-d [-h] [--version] [-v] [-q] [--log-format {text,json}]
                                [--log-file PATH] [--log-content]
                                [--progress {off,summary,status,steps,trace}]
                                [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                                [--progress-interval SECONDS] [--progress-max-bytes N]
                                [--control-file PATH] [--show-content] [--content-chars N]
                                [--json] [--summary-json PATH] [--max-listed N] [--no-colour]
                                [--break-stale-lock] [--scope {golden,full}] [--workers N]
                                [--release] [--report PATH] [--reports-dir DIR] [--config FILE]
                                [--in-process] [--corpus DIR] [--limit N] [--accept-gap TREE]

gate D: SEM and agentprov-prov/0.1 re-derived from stored AERs and validated in every D8 tier
(release mode)

options:
  -h, --help            show this help message and exit
  --scope {golden,full}
                        golden: the golden set (CI); full: the baseline trees (local). Default:
                        golden (G0: full)
  --workers N           worker processes for mapping (0 = host default; default 8 or [run] workers
                        of the config)
  --release             release mode: params.strict true, skipped checks fail, T1 isolation grade
                        must be watchdog or better
  --report PATH         write the gate report to PATH (atomic); default <reports-
                        dir>/<gate>/<date>-<commit>.json
  --reports-dir DIR     reports directory (default $AGENTPROV_HOME/migration/reports); predecessor
                        reports are looked up here and in the repository's migration/reports
  --config FILE         migration config (default migration/local.toml when it exists)
  --in-process          debugging only: map in this process (refused with --release)
  --corpus DIR          gate D, full scope: a corpus of stored AERs (read-only); once per tree
  --limit N             gate D: check N evenly spaced executions per corpus (scope sample)
  --accept-gap TREE     gate D, full scope: record that this tree has no stored AERs (the report
                        says so)

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

### agentprov migrate gate-e

```text
usage: agentprov migrate gate-e [-h] [--version] [-v] [-q] [--log-format {text,json}]
                                [--log-file PATH] [--log-content]
                                [--progress {off,summary,status,steps,trace}]
                                [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                                [--progress-interval SECONDS] [--progress-max-bytes N]
                                [--control-file PATH] [--show-content] [--content-chars N]
                                [--json] [--summary-json PATH] [--max-listed N] [--no-colour]
                                [--break-stale-lock] [--scope {golden,full}] [--workers N]
                                [--release] [--report PATH] [--reports-dir DIR] [--config FILE]
                                [--in-process] [--semdiff-dir DIR]

gate E: the semantic diff of the compat graphs against agentprov-prov/0.1, from semdiff-map.toml

options:
  -h, --help            show this help message and exit
  --scope {golden,full}
                        golden: the golden set (CI); full: the baseline trees (local). Default:
                        golden (G0: full)
  --workers N           worker processes for mapping (0 = host default; default 8 or [run] workers
                        of the config)
  --release             release mode: params.strict true, skipped checks fail, T1 isolation grade
                        must be watchdog or better
  --report PATH         write the gate report to PATH (atomic); default <reports-
                        dir>/<gate>/<date>-<commit>.json
  --reports-dir DIR     reports directory (default $AGENTPROV_HOME/migration/reports); predecessor
                        reports are looked up here and in the repository's migration/reports
  --config FILE         migration config (default migration/local.toml when it exists)
  --in-process          debugging only: map in this process (refused with --release)
  --semdiff-dir DIR     gate E: where semdiff-<tree>.{json,md} go (default
                        $AGENTPROV_HOME/migration/semdiff)

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

### agentprov migrate gate

```text
usage: agentprov migrate gate [-h] [--version] [-v] [-q] [--log-format {text,json}]
                              [--log-file PATH] [--log-content]
                              [--progress {off,summary,status,steps,trace}]
                              [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                              [--progress-interval SECONDS] [--progress-max-bytes N]
                              [--control-file PATH] [--show-content] [--content-chars N] [--json]
                              [--summary-json PATH] [--max-listed N] [--no-colour]
                              [--break-stale-lock] [--scope {golden,full}] [--workers N]
                              [--release] [--report PATH] [--reports-dir DIR] [--config FILE]
                              [--in-process] [--corpus DIR] [--limit N] [--accept-gap TREE]
                              [--semdiff-dir DIR]
                              GATE

run one gate by name: G0, A, B, D or E

positional arguments:
  GATE                  G0, A, B, D or E

options:
  -h, --help            show this help message and exit
  --scope {golden,full}
                        golden: the golden set (CI); full: the baseline trees (local). Default:
                        golden (G0: full)
  --workers N           worker processes for mapping (0 = host default; default 8 or [run] workers
                        of the config)
  --release             release mode: params.strict true, skipped checks fail, T1 isolation grade
                        must be watchdog or better
  --report PATH         write the gate report to PATH (atomic); default <reports-
                        dir>/<gate>/<date>-<commit>.json
  --reports-dir DIR     reports directory (default $AGENTPROV_HOME/migration/reports); predecessor
                        reports are looked up here and in the repository's migration/reports
  --config FILE         migration config (default migration/local.toml when it exists)
  --in-process          debugging only: map in this process (refused with --release)
  --corpus DIR          gate D, full scope: a corpus of stored AERs (read-only); once per tree
  --limit N             gate D: check N evenly spaced executions per corpus (scope sample)
  --accept-gap TREE     gate D, full scope: record that this tree has no stored AERs (the report
                        says so)
  --semdiff-dir DIR     gate E: where semdiff-<tree>.{json,md} go (default
                        $AGENTPROV_HOME/migration/semdiff)

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

## agentprov render

```text
usage: agentprov render [-h] [--version] [-v] [-q] [--log-format {text,json}] [--log-file PATH]
                        [--log-content] [--progress {off,summary,status,steps,trace}]
                        [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                        [--progress-interval SECONDS] [--progress-max-bytes N]
                        [--control-file PATH] [--show-content] [--content-chars N] [--json]
                        [--summary-json PATH] [--max-listed N] [--no-colour] [--break-stale-lock]
                        --corpus DIR [--ex ID [ID ...]] [--select KEY=VALUE[,VALUE...]]
                        [--limit N] [--bundle {core,all}] [--format LIST] [--direction {LR,TB}]
                        [--out DIR] [--max-edges N] [--jobs N] [--dry-run]

Render the agentprov-prov/0.1 PROV graph of selected executions to DOT and images (N.2.13).
Nothing is rendered unless asked; renders go to <corpus>-rendered/ (or --out), never into a
corpus. Needs the render extra (uv sync --frozen --group docs --extra render) and the Graphviz dot
binary, except with --format dot. --show-content adds attribute values (escaped, one line,
--content-chars long) to the node labels; without it labels hold only ids, types and rule ids.

options:
  -h, --help            show this help message and exit
  --corpus DIR          the corpus to read (sealed, working, or DIR.partial)

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead

selection (--ex ID..., --select with --limit N, or --limit N; there is no render-all):
  --ex ID [ID ...]      execution ids to render
  --select KEY=VALUE[,VALUE...]
                        AER-header filter, as for import --select (repeatable)
  --limit N             render at most the first N selected executions (required with --select)

drawing and output:
  --bundle {core,all}   core (default): the core bundle only; all: also the inference and
                        assessment bundles
  --format LIST         comma list from svg,png,pdf,dot (default svg); the .dot text is always
                        written
  --direction {LR,TB}   rank direction (default LR)
  --out DIR             output directory (default <corpus>-rendered); never inside a corpus
  --max-edges N         image layout limit: a graph with more edges gets its .dot text but no
                        image (default 800; 0 = no limit, dot still times out at 120 s)
  --jobs N              parallel dot processes (0 = the host default worker count; default 0)
  --dry-run             select and build the DOT text in memory; write and run nothing

Notation: entities are ovals, activities boxes, agents houses (W3C PROV colours). Border and line
style show the evidence class: solid thick = Observed, dashed = Derived, dotted = Inferred, thin
grey = no class. With --bundle all, purple marks the inference bundles and brown the assessment
bundles; untrusted integrity is salmon, unknown integrity or role is grey, sinks are dark red and
endorsers light blue. Examples: agentprov render --corpus C --ex ex_... | agentprov render
--corpus C --select attack=important_instructions --limit 20 --format svg,png | agentprov render
--corpus C --ex ex_... --bundle all --show-content
```

## agentprov inspect

```text
usage: agentprov inspect [-h] [--version] [-v] [-q] [--log-format {text,json}] [--log-file PATH]
                         [--log-content] [--progress {off,summary,status,steps,trace}]
                         [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                         [--progress-interval SECONDS] [--progress-max-bytes N]
                         [--control-file PATH] [--show-content] [--content-chars N] [--json]
                         [--summary-json PATH] [--max-listed N] [--no-colour] [--break-stale-lock]
                         [--corpus DIR]
                         [--view {summary,records,transcript,transcript-v1,timeline,evidence,sem,prov,raw,detect}]
                         [--record ID] [--bundle {core,inference,assessment,toplevel,all}]
                         [--max-chars N] [--format {text,json}]
                         TARGET

Look at an execution id (with --corpus), an .aer.jsonl / .sem.jsonl / PROV-JSON file, a raw file
(--view detect) or a corpus root (N.2.8). Read-only. Without --show-content only structure is
printed: ids, kinds, locators, digests, lengths, rule ids and labels; with it, content is printed
through quote_untrusted (escaped, fenced, truncated at --max-chars).

positional arguments:
  TARGET                an execution id, a file, or a corpus root

options:
  -h, --help            show this help message and exit
  --corpus DIR          the corpus (sealed, working or DIR.partial) for an execution id or the raw
                        store
  --view {summary,records,transcript,transcript-v1,timeline,evidence,sem,prov,raw,detect}
                        what to show (default summary)
  --record ID           one record (records, evidence, timeline, sem, raw)
  --bundle {core,inference,assessment,toplevel,all}
                        prov view: which bundles (default core)
  --max-chars N         with --show-content: characters per value (default 500)
  --format {text,json}  payload format (default text)

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

## agentprov purge

```text
usage: agentprov purge [-h] [--version] [-v] [-q] [--log-format {text,json}] [--log-file PATH]
                       [--log-content] [--progress {off,summary,status,steps,trace}]
                       [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                       [--progress-interval SECONDS] [--progress-max-bytes N]
                       [--control-file PATH] [--show-content] [--content-chars N] [--json]
                       [--summary-json PATH] [--max-listed N] [--no-colour] [--break-stale-lock]
                       --reason {secret,personal_data} (--corpus DIR | --cache) [--cache-dir DIR]
                       [--yes] [--dry-run]
                       sha256:HEX

Delete one object (by sha256) from a working corpus's raw store, or one downloaded file from the
fetch cache, and write a tombstone beside the store's records (N.2.15; G.9.6). Executions that
cite the object get the register code release.withheld. A sealed corpus is never modified (exit
4). Purging is irreversible: it asks for confirmation on a terminal, and refuses (exit 4) without
--yes when not interactive.

positional arguments:
  sha256:HEX            the object to remove

options:
  -h, --help            show this help message and exit
  --reason {secret,personal_data}
                        why the object is removed
  --corpus DIR          the working corpus (DIR.partial) whose raw store holds the object
  --cache               remove a downloaded file from the fetch cache instead
  --cache-dir DIR       with --cache: the fetch cache (default $AGENTPROV_UPSTREAM_CACHE, else
                        $AGENTPROV_HOME/cache)
  --yes                 confirm the irreversible removal without asking (needed when not
                        interactive)
  --dry-run             print what would be removed; write nothing, take no lock

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

## agentprov stats

```text
usage: agentprov stats [-h] [--version] [-v] [-q] [--log-format {text,json}] [--log-file PATH]
                       [--log-content] [--progress {off,summary,status,steps,trace}]
                       [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                       [--progress-interval SECONDS] [--progress-max-bytes N]
                       [--control-file PATH] [--show-content] [--content-chars N] [--json]
                       [--summary-json PATH] [--max-listed N] [--no-colour] [--break-stale-lock]
                       --corpus DIR [--tables LIST] [--artefacts] [--per-execution]
                       [--prov-spec {agentprov-prov/0.1,adprov-v2.3-compat}]
                       [--select KEY=VALUE[,VALUE...]] [--format {text,csv,json,markdown}]
                       [--out PATH]

Compute the generic tables of N.2.12 over each corpus separately (never pooled): counts per
source, status and unit; PROV statements by evidence class, bundle and rule; unknown-reason
proportions per field-group pointer; and the per-source information-loss table (field-group
coverage, R-57). Reads the corpus read-only; writes only to stdout or --out (outside every
corpus). Only aggregates are printed.

options:
  -h, --help            show this help message and exit
  --corpus DIR          a corpus to read (sealed, working, or DIR.partial); repeatable, one table
                        set per corpus
  --tables LIST         comma list from counts,statements,unknowns,field_groups (default: all
                        four)
  --artefacts           also scan every selected execution with the shared artefact layer (D.15.4
                        table)
  --per-execution       with the statements table, also give it at execution grain
                        (statements_by_execution; O.3.5)
  --prov-spec {agentprov-prov/0.1,adprov-v2.3-compat}
                        the provenance spec whose PROV files the statements table counts (default
                        agentprov-prov/0.1)
  --select KEY=VALUE[,VALUE...]
                        index-row filter (repeatable; keys: source_id, profile, unit, status,
                        mode, completeness, execution_observed, adapter, snapshot, issue,
                        facet.<name>, cell.<member> (suite, task_id, attack_id, attack_target_id,
                        defense_id, ...), outcome.<claim>=true|false|none)
  --format {text,csv,json,markdown}
                        payload format (default text)
  --out PATH            write the payload to PATH (atomic; never inside a corpus)

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead

Examples: agentprov stats --corpus C | agentprov stats --corpus C1 --corpus C2 --tables
field_groups --format csv --out fg.csv | agentprov stats --corpus C --select unit=agent_execution
--format json | agentprov stats --corpus C --artefacts --tables counts
```

## agentprov package

```text
usage: agentprov package [-h] [--version] [-v] [-q] [--log-format {text,json}] [--log-file PATH]
                         [--log-content] [--progress {off,summary,status,steps,trace}]
                         [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                         [--progress-interval SECONDS] [--progress-max-bytes N]
                         [--control-file PATH] [--show-content] [--content-chars N] [--json]
                         [--summary-json PATH] [--max-listed N] [--no-colour] [--break-stale-lock]
                         --corpus DIR [--corpus-version X.Y.Z] [--spec PATH]
                         [--licence-file NAME=PATH] [--release-date YYYY-MM-DD] [--deposit OUT]
                         [--index OUT] [--part RECEIPT] [--metadata release.toml]
                         [--max-archive-bytes N] [--allow-mixed-licence-classes] [--dry-run]

Seal a working corpus (N.2.11): write rules/, schemas/, LICENSES/, DATASHEET.md, CHANGELOG.md, the
full corpus.json and checksums.sha256, then swap DIR.partial to DIR and print the root digest.
With --deposit OUT, build a deposit draft (deterministic archives, DEPOSIT-MANIFEST.json, deposit-
metadata.json) from one or more sealed corpora. With --index OUT, build the index-only umbrella
deposit of a collection (COLLECTION-INDEX.json, datasheet copies, no archives) from the part
records' draft receipts and their sealed corpora. Nothing is uploaded or published.

options:
  -h, --help            show this help message and exit
  --corpus DIR          the corpus directory (seal mode: once, its working tree is DIR.partial;
                        deposit and index modes: a sealed corpus, repeatable)
  --corpus-version X.Y.Z
                        seal mode (required there): the version to seal (the spec's)
  --spec PATH           corpora/<id>/corpus-spec.toml (CARD.md and CHANGES.toml beside it)
  --licence-file NAME=PATH
                        an upstream licence file the spec names that the corpus does not store
                        (repeatable)
  --release-date YYYY-MM-DD
                        release.created (else SOURCE_DATE_EPOCH, else null)
  --deposit OUT         build a deposit draft directory OUT from sealed corpora (H.10)
  --index OUT           build the index-only umbrella deposit OUT of a collection (H.10.7; D-947):
                        no archives, nothing uploaded
  --part RECEIPT        index mode: a part record's draft receipt (DIR.zenodo-TARGET-draft-
                        receipt.json, status complete), its deposit directory DIR beside it;
                        repeatable
  --metadata release.toml
                        deposit and index modes: title, creators, keywords, preamble, DOIs
                        (H.10.2)
  --max-archive-bytes N
                        deposit mode: split archives on shard boundaries at N bytes (default and
                        maximum 2^31-1, no ZIP64)
  --allow-mixed-licence-classes
                        deposit mode: admit corpora of different licence classes in one deposit
                        (recorded; never -nc)
  --dry-run             compute and check everything, write nothing

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

## agentprov derive

```text
usage: agentprov derive [-h] [--version] [-v] [-q] [--log-format {text,json}] [--log-file PATH]
                        [--log-content] [--progress {off,summary,status,steps,trace}]
                        [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                        [--progress-interval SECONDS] [--progress-max-bytes N]
                        [--control-file PATH] [--show-content] [--content-chars N] [--json]
                        [--summary-json PATH] [--max-listed N] [--no-colour] [--break-stale-lock]
                        [--corpus SRC] [--out NEW] [--prov-spec SPEC] [--jobs N] [--in-process]
                        [--link-raw] [--dry-run] [--no-reuse] [--skip-prov-conformance]
                        [--no-validation-cache] [--stages S[,S...]] [--views VIEW]
                        [--semantics-profile ID@N] [--trig DIR]

Add missing derived layers of SRC into a new working corpus NEW.partial (N.2.3); SRC is never
written.

options:
  -h, --help            show this help message and exit
  --corpus SRC          the source corpus (sealed, working or .partial); read only
  --out NEW             the new corpus directory (written as NEW.partial; must not exist)
  --prov-spec SPEC      provenance spec (agentprov-prov/0.1; adprov-v2.3-compat writes the
                        regression oracle, R-55)
  --jobs N              worker processes (0 = host default)
  --in-process          debugging only: run the T1 jobs in this process
  --link-raw            hard-link raw objects into NEW instead of copying them (D-32)
  --dry-run             derive and compare in a private temporary tree; write nothing
  --no-reuse            recompute every execution (--out reuses unchanged outputs by default;
                        --dry-run never reuses)
  --skip-prov-conformance
                        dev mode only, not advisable: a recomputed validation skips the W3C PROV
                        conformance check (tier 4); NEW is marked unvalidated and cannot be sealed
                        (G2c-5)
  --no-validation-cache
                        always run the tier-4 PROV-O round trip; neither read nor write
                        $AGENTPROV_HOME/cache/tier4 (D-550)
  --stages S[,S...]     layers to add: sem,prov,validation,views
  --views VIEW          add a view (transcript-v1)
  --semantics-profile ID@N
                        semantics profile for an added sem layer (repeatable; default: the
                        source's)
  --trig DIR            write PROV-O TriG (on demand; never part of a corpus) into DIR

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

## agentprov recompute

```text
usage: agentprov recompute [-h] [--version] [-v] [-q] [--log-format {text,json}] [--log-file PATH]
                           [--log-content] [--progress {off,summary,status,steps,trace}]
                           [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                           [--progress-interval SECONDS] [--progress-max-bytes N]
                           [--control-file PATH] [--show-content] [--content-chars N] [--json]
                           [--summary-json PATH] [--max-listed N] [--no-colour]
                           [--break-stale-lock] [--corpus SRC] [--out NEW] [--prov-spec SPEC]
                           [--jobs N] [--in-process] [--link-raw] [--dry-run] [--no-reuse]
                           [--skip-prov-conformance] [--no-validation-cache] [--stages S[,S...]]
                           [--show-diff N] [--strict]

Re-run the derivation stages of SRC into NEW.partial (or in memory with --dry-run) and compare.

options:
  -h, --help            show this help message and exit
  --corpus SRC          the source corpus (sealed, working or .partial); read only
  --out NEW             the new corpus directory (written as NEW.partial; must not exist)
  --prov-spec SPEC      provenance spec (agentprov-prov/0.1; adprov-v2.3-compat writes the
                        regression oracle, R-55)
  --jobs N              worker processes (0 = host default)
  --in-process          debugging only: run the T1 jobs in this process
  --link-raw            hard-link raw objects into NEW instead of copying them (D-32)
  --dry-run             derive and compare in a private temporary tree; write nothing
  --no-reuse            recompute every execution (--out reuses unchanged outputs by default;
                        --dry-run never reuses)
  --skip-prov-conformance
                        dev mode only, not advisable: a recomputed validation skips the W3C PROV
                        conformance check (tier 4); NEW is marked unvalidated and cannot be sealed
                        (G2c-5)
  --no-validation-cache
                        always run the tier-4 PROV-O round trip; neither read nor write
                        $AGENTPROV_HOME/cache/tier4 (D-550)
  --stages S[,S...]     stages to re-run: expand,aer,sem,prov,validation,views (default: every
                        stage the source has)
  --show-diff N         show the first differences of N changed executions
  --strict              exit 1 when an execution is unverified

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

## agentprov verify

```text
usage: agentprov verify [-h] [--version] [-v] [-q] [--log-format {text,json}] [--log-file PATH]
                        [--log-content] [--progress {off,summary,status,steps,trace}]
                        [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                        [--progress-interval SECONDS] [--progress-max-bytes N]
                        [--control-file PATH] [--show-content] [--content-chars N] [--json]
                        [--summary-json PATH] [--max-listed N] [--no-colour] [--break-stale-lock]
                        --corpus PATH [--level {checksums,chain,rederive}]
                        [--root-digest sha256:HEX] [--against-pins] [--allow-network]
                        [--cache-dir DIR] [--sample N] [--seed S] [--release] [--jobs N]
                        [--in-process] [--no-validation-cache]

Verify corpus integrity (N.2.6; H.5.5) read-only: a corpus tree, a deposit directory or a lone
meta archive (archive mode, never extracted). Levels: checksums (closed world), chain (the
default: manifest, digests, index, register and counts, AER seals, raw objects and member CRC-32s,
SEM/PROV inputs, facets, catalogue authority), rederive (chain plus a byte-identical re-derivation
from the stored raw objects).

options:
  -h, --help            show this help message and exit
  --corpus PATH         a corpus directory, a deposit directory or a .meta.zip
  --level {checksums,chain,rederive}
                        verification level (default chain)
  --root-digest sha256:HEX
                        a root digest published outside the corpus (D-39; repeatable; with
                        --release required, and for a deposit one per corpus; D-620, D-641)
  --against-pins        compare every git origin with the in-package profile pins
  --allow-network       --against-pins: fetch a pinned tree listing not in the cache
  --cache-dir DIR       --against-pins: the fetch cache (default $AGENTPROV_HOME/cache)
  --sample N            check a seeded sample of N executions (N.1.7)
  --seed S              the sampling seed (with --sample)
  --release             release mode: unverified fails; no sampling; needs --root-digest
  --jobs N              rederive: worker processes (0 = host default)
  --in-process          rederive: run the T1 jobs in this process (debugging only)
  --no-validation-cache
                        rederive: always run the tier-4 PROV-O round trip; neither read nor write
                        the round-trip cache (D-550). With --release the cache is never read; it
                        is audited

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

## agentprov settings

```text
usage: agentprov settings [-h] [--version] [-v] [-q] [--log-format {text,json}] [--log-file PATH]
                          [--log-content] [--progress {off,summary,status,steps,trace}]
                          [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                          [--progress-interval SECONDS] [--progress-max-bytes N]
                          [--control-file PATH] [--show-content] [--content-chars N] [--json]
                          [--summary-json PATH] [--max-listed N] [--no-colour]
                          [--break-stale-lock]
                          ACTION ...

``agentprov settings``: the user settings the CLI and the GUI share (D-703; reverse CLI parity
D-700).

positional arguments:
  ACTION
    list                the stored settings (or the schema)
    get                 one setting (nothing when unset)
    set                 store one setting (checked against the schema)
    unset               remove one setting

options:
  -h, --help            show this help message and exit

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

### agentprov settings list

```text
usage: agentprov settings list [-h] [--version] [-v] [-q] [--log-format {text,json}]
                               [--log-file PATH] [--log-content]
                               [--progress {off,summary,status,steps,trace}]
                               [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                               [--progress-interval SECONDS] [--progress-max-bytes N]
                               [--control-file PATH] [--show-content] [--content-chars N] [--json]
                               [--summary-json PATH] [--max-listed N] [--no-colour]
                               [--break-stale-lock] [--prefix P] [--schema] [--format {text,json}]

options:
  -h, --help            show this help message and exit
  --prefix P            only keys starting with P
  --schema              list the key patterns, types and bounds instead
  --format {text,json}

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

### agentprov settings get

```text
usage: agentprov settings get [-h] [--version] [-v] [-q] [--log-format {text,json}]
                              [--log-file PATH] [--log-content]
                              [--progress {off,summary,status,steps,trace}]
                              [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                              [--progress-interval SECONDS] [--progress-max-bytes N]
                              [--control-file PATH] [--show-content] [--content-chars N] [--json]
                              [--summary-json PATH] [--max-listed N] [--no-colour]
                              [--break-stale-lock] [--format {text,json}]
                              KEY

positional arguments:
  KEY

options:
  -h, --help            show this help message and exit
  --format {text,json}

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

### agentprov settings set

```text
usage: agentprov settings set [-h] [--version] [-v] [-q] [--log-format {text,json}]
                              [--log-file PATH] [--log-content]
                              [--progress {off,summary,status,steps,trace}]
                              [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                              [--progress-interval SECONDS] [--progress-max-bytes N]
                              [--control-file PATH] [--show-content] [--content-chars N] [--json]
                              [--summary-json PATH] [--max-listed N] [--no-colour]
                              [--break-stale-lock]
                              KEY VALUE

positional arguments:
  KEY
  VALUE                 lists: comma or space separated; booleans: true or false

options:
  -h, --help            show this help message and exit

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

### agentprov settings unset

```text
usage: agentprov settings unset [-h] [--version] [-v] [-q] [--log-format {text,json}]
                                [--log-file PATH] [--log-content]
                                [--progress {off,summary,status,steps,trace}]
                                [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                                [--progress-interval SECONDS] [--progress-max-bytes N]
                                [--control-file PATH] [--show-content] [--content-chars N]
                                [--json] [--summary-json PATH] [--max-listed N] [--no-colour]
                                [--break-stale-lock]
                                KEY

positional arguments:
  KEY

options:
  -h, --help            show this help message and exit

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

## agentprov keys

```text
usage: agentprov keys [-h] [--version] [-v] [-q] [--log-format {text,json}] [--log-file PATH]
                      [--log-content] [--progress {off,summary,status,steps,trace}]
                      [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                      [--progress-interval SECONDS] [--progress-max-bytes N] [--control-file PATH]
                      [--show-content] [--content-chars N] [--json] [--summary-json PATH]
                      [--max-listed N] [--no-colour] [--break-stale-lock]
                      ACTION ...

``agentprov keys``: endpoint keys in the OS keychain (D-702; D-395, D-655; reverse CLI parity
D-700).

positional arguments:
  ACTION
    status              whether a secure keychain is available
    list                the endpoints' key variables and whether each is stored
    set                 store a key (prompted without echo, or one line on stdin)
    delete              remove a stored key

options:
  -h, --help            show this help message and exit

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

### agentprov keys status

```text
usage: agentprov keys status [-h] [--version] [-v] [-q] [--log-format {text,json}]
                             [--log-file PATH] [--log-content]
                             [--progress {off,summary,status,steps,trace}]
                             [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                             [--progress-interval SECONDS] [--progress-max-bytes N]
                             [--control-file PATH] [--show-content] [--content-chars N] [--json]
                             [--summary-json PATH] [--max-listed N] [--no-colour]
                             [--break-stale-lock] [--format {text,json}]

options:
  -h, --help            show this help message and exit
  --format {text,json}

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

### agentprov keys list

```text
usage: agentprov keys list [-h] [--version] [-v] [-q] [--log-format {text,json}] [--log-file PATH]
                           [--log-content] [--progress {off,summary,status,steps,trace}]
                           [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                           [--progress-interval SECONDS] [--progress-max-bytes N]
                           [--control-file PATH] [--show-content] [--content-chars N] [--json]
                           [--summary-json PATH] [--max-listed N] [--no-colour]
                           [--break-stale-lock] [--format {text,json}]

options:
  -h, --help            show this help message and exit
  --format {text,json}

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

### agentprov keys set

```text
usage: agentprov keys set [-h] [--version] [-v] [-q] [--log-format {text,json}] [--log-file PATH]
                          [--log-content] [--progress {off,summary,status,steps,trace}]
                          [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                          [--progress-interval SECONDS] [--progress-max-bytes N]
                          [--control-file PATH] [--show-content] [--content-chars N] [--json]
                          [--summary-json PATH] [--max-listed N] [--no-colour]
                          [--break-stale-lock] [--stdin]
                          NAME

positional arguments:
  NAME                  a key variable of endpoints.toml, e.g. OPENROUTER_API_KEY, or
                        ZENODO_SANDBOX_TOKEN / ZENODO_TOKEN

options:
  -h, --help            show this help message and exit
  --stdin               read the value as one line from stdin (never from argv)

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

### agentprov keys delete

```text
usage: agentprov keys delete [-h] [--version] [-v] [-q] [--log-format {text,json}]
                             [--log-file PATH] [--log-content]
                             [--progress {off,summary,status,steps,trace}]
                             [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                             [--progress-interval SECONDS] [--progress-max-bytes N]
                             [--control-file PATH] [--show-content] [--content-chars N] [--json]
                             [--summary-json PATH] [--max-listed N] [--no-colour]
                             [--break-stale-lock] [--yes]
                             NAME

positional arguments:
  NAME

options:
  -h, --help            show this help message and exit
  --yes                 confirm without asking (needed when not interactive)

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

## agentprov prices

```text
usage: agentprov prices [-h] [--version] [-v] [-q] [--log-format {text,json}] [--log-file PATH]
                        [--log-content] [--progress {off,summary,status,steps,trace}]
                        [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                        [--progress-interval SECONDS] [--progress-max-bytes N]
                        [--control-file PATH] [--show-content] [--content-chars N] [--json]
                        [--summary-json PATH] [--max-listed N] [--no-colour] [--break-stale-lock]
                        ACTION ...

``agentprov prices``: the model prices the estimate reads (D-701; D-650; reverse CLI parity
D-700).

positional arguments:
  ACTION
    list                the price sources and every priced model per endpoint
    get                 the price one estimate would use (nothing when unpriced)
    set                 store a per-model override (USD per million tokens)
    unset               remove an override
    refresh             fetch OpenRouter's model list into a dated snapshot (network; confirm
                        first)

options:
  -h, --help            show this help message and exit

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

### agentprov prices list

```text
usage: agentprov prices list [-h] [--version] [-v] [-q] [--log-format {text,json}]
                             [--log-file PATH] [--log-content]
                             [--progress {off,summary,status,steps,trace}]
                             [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                             [--progress-interval SECONDS] [--progress-max-bytes N]
                             [--control-file PATH] [--show-content] [--content-chars N] [--json]
                             [--summary-json PATH] [--max-listed N] [--no-colour]
                             [--break-stale-lock] [--endpoint NAME] [--format {text,json}]

options:
  -h, --help            show this help message and exit
  --endpoint NAME       only this endpoint of endpoints.toml
  --format {text,json}

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

### agentprov prices get

```text
usage: agentprov prices get [-h] [--version] [-v] [-q] [--log-format {text,json}]
                            [--log-file PATH] [--log-content]
                            [--progress {off,summary,status,steps,trace}]
                            [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                            [--progress-interval SECONDS] [--progress-max-bytes N]
                            [--control-file PATH] [--show-content] [--content-chars N] [--json]
                            [--summary-json PATH] [--max-listed N] [--no-colour]
                            [--break-stale-lock] [--format {text,json}]
                            ENDPOINT MODEL

positional arguments:
  ENDPOINT
  MODEL

options:
  -h, --help            show this help message and exit
  --format {text,json}

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

### agentprov prices set

```text
usage: agentprov prices set [-h] [--version] [-v] [-q] [--log-format {text,json}]
                            [--log-file PATH] [--log-content]
                            [--progress {off,summary,status,steps,trace}]
                            [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                            [--progress-interval SECONDS] [--progress-max-bytes N]
                            [--control-file PATH] [--show-content] [--content-chars N] [--json]
                            [--summary-json PATH] [--max-listed N] [--no-colour]
                            [--break-stale-lock] --input USD --output USD [--cached-input USD]
                            [--cache-write USD] [--as-of YYYY-MM-DD]
                            ENDPOINT MODEL

positional arguments:
  ENDPOINT
  MODEL

options:
  -h, --help            show this help message and exit
  --input USD           input tokens (uncached)
  --output USD          output tokens (reasoning included)
  --cached-input USD    cache reads (default: the input price)
  --cache-write USD     5-minute cache writes (default: the input price)
  --as-of YYYY-MM-DD    the date of the price (default: today)

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

### agentprov prices unset

```text
usage: agentprov prices unset [-h] [--version] [-v] [-q] [--log-format {text,json}]
                              [--log-file PATH] [--log-content]
                              [--progress {off,summary,status,steps,trace}]
                              [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                              [--progress-interval SECONDS] [--progress-max-bytes N]
                              [--control-file PATH] [--show-content] [--content-chars N] [--json]
                              [--summary-json PATH] [--max-listed N] [--no-colour]
                              [--break-stale-lock]
                              ENDPOINT MODEL

positional arguments:
  ENDPOINT
  MODEL

options:
  -h, --help            show this help message and exit

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

### agentprov prices refresh

```text
usage: agentprov prices refresh [-h] [--version] [-v] [-q] [--log-format {text,json}]
                                [--log-file PATH] [--log-content]
                                [--progress {off,summary,status,steps,trace}]
                                [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                                [--progress-interval SECONDS] [--progress-max-bytes N]
                                [--control-file PATH] [--show-content] [--content-chars N]
                                [--json] [--summary-json PATH] [--max-listed N] [--no-colour]
                                [--break-stale-lock] [--allow-network | --from-file RESPONSE.json]
                                [--fetched YYYY-MM-DD]

options:
  -h, --help            show this help message and exit
  --allow-network       required to fetch (one public URL, no key)
  --from-file RESPONSE.json
                        import a saved /api/v1/models response instead
  --fetched YYYY-MM-DD  with --from-file: the date it was fetched (default: today)

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

## agentprov estimate

```text
usage: agentprov estimate [-h] [--version] [-v] [-q] [--log-format {text,json}] [--log-file PATH]
                          [--log-content] [--progress {off,summary,status,steps,trace}]
                          [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                          [--progress-interval SECONDS] [--progress-max-bytes N]
                          [--control-file PATH] [--show-content] [--content-chars N] [--json]
                          [--summary-json PATH] [--max-listed N] [--no-colour]
                          [--break-stale-lock] [--corpus DIR] [--campaign NAME | --corpus-id ID]
                          [--plan PLAN.toml] [--spec SPEC.toml] [--suite S[,S...]]
                          [--benchmark-version V] [--user-tasks SPEC] [--attack A[,A...]]
                          [--injection-tasks SPEC] [--benign {include,exclude,only}]
                          [--defence NAME] [--task NAME] [--task-param KEY=VALUE]
                          [--samples limit:N|ID[,ID...]] [--epochs N] [--message-limit N]
                          [--token-limit N] [--time-limit SECONDS] [--max-connections N]
                          [--cell-size N] [--judge ROLE=MODEL] [--model SHORTHAND]
                          [--endpoint NAME] [--model-id ID] [--defence-endpoint NAME]
                          [--llm-script SCRIPT.json] [--llm-element {native,gateway_compat}]
                          [--model-display-name NAME] [--temperature T] [--reasoning-effort LEVEL]
                          [--max-tokens N|harness-default]
                          [--temperature-policy {as-benchmark,inject}] [--allow-text-tool-calls]
                          [--base-url URL] [--accept-served-model ID] [--allow-lan-endpoint]
                          [--no-hash-weights] [--repeats N] [--max-attempts N]
                          [--retry-inconsistent] [--allow-mixed-config] [--limit N] [--canary N]
                          [--cell-timeout SECONDS] [--jobs N] [--start-stagger SECONDS]
                          [--env-file PATH] [--env-stdin] [--keychain] [--allow-custom-endpoint]
                          [--containment {sandbox-exec,dedicated-user,vm}] [--autodojo-cache PATH]
                          [--autodojo-variant K] [--allow-network] [--max-calls N]
                          [--max-cost-usd USD] [--price-in USD_PER_MTOK]
                          [--price-out USD_PER_MTOK] [--stats-corpus DIR] [--format {text,json}]
                          SOURCE

``agentprov estimate``: the cost and time of a live run before it starts (D-701; design §8.3 as
amended by D-650,

positional arguments:
  SOURCE                live source: agentdojo, agentdyn, agentharm or autodojo

options:
  -h, --help            show this help message and exit
  --corpus DIR          working corpus directory
  --campaign NAME       corpus id <source>-live-<NAME>
  --corpus-id ID

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead

cells (exclusive with --plan):
  --plan PLAN.toml      committed run plan
  --spec SPEC.toml      corpus spec with [live]
  --suite S[,S...]
  --benchmark-version V
  --user-tasks SPEC
  --attack A[,A...]
  --injection-tasks SPEC
  --benign {include,exclude,only}
  --defence, --defense NAME

Inspect plans (an inspect-<benchmark> backend; D-663; exclusive with the cell options):
  --task NAME           Inspect task (the catalogue lists them), e.g. inspect_evals/agentharm
  --task-param KEY=VALUE
                        a task parameter the catalogue declares (repeatable; VALUE as a TOML
                        scalar or a string)
  --samples limit:N|ID[,ID...]
                        the samples: the first N of the split, or ids
  --epochs N
  --message-limit N     per sample (mandatory for Inspect, D-667)
  --token-limit N       per sample (mandatory for Inspect, D-667)
  --time-limit SECONDS  per sample (mandatory for Inspect, D-667)
  --max-connections N   concurrent model calls of one cell
  --cell-size N         samples per cell (one Inspect eval per cell)
  --judge ROLE=MODEL    the model of a judge role of the task's scorer (repeatable; every role is
                        required, D-667); judges use the agent's endpoint and key

model (one of: --model, --endpoint with --model-id, --llm-script):
  --model SHORTHAND     endpoint shorthand from endpoints.toml
  --endpoint NAME       explicit endpoint (deepseek, openai, openrouter, anthropic, local, ollama,
                        omlx, lmstudio, mlx_lm, llamacpp, vllm)
  --model-id ID
  --defence-endpoint NAME
                        the endpoint (endpoints.toml shorthand) a defence calls for its own model
                        or embedding calls (D-675; MELON's embeddings); only its key enters the
                        worker
  --llm-script SCRIPT.json
                        scripted transport: no network, no keys (test_only)
  --llm-element {native,gateway_compat}
  --model-display-name NAME
  --temperature T
  --reasoning-effort LEVEL
  --max-tokens N|harness-default
                        Anthropic endpoints (required there): the reply's token cap, stated (N) or
                        the harness default 16000 (harness-default, recorded as a harness policy);
                        AgentDojo's own 1024 is never used silently (D-656)
  --temperature-policy {as-benchmark,inject}
  --allow-text-tool-calls
                        run an endpoint that returns text-encoded tool calls

local model servers (D-691..D-694):
  --base-url URL        a local endpoint's base URL (loopback; overrides .env and the registry
                        default; recorded)
  --accept-served-model ID
                        a served model id that may differ from the requested one (repeatable;
                        recorded; A12)
  --allow-lan-endpoint  allow a local endpoint on a literal private LAN address (D-698): prompts
                        and replies leave this machine over plain http; keyless; recorded
  --no-hash-weights     record a local model's weight files by size only (weights_hashed false)

control:
  --repeats N
  --max-attempts N
  --retry-inconsistent
  --allow-mixed-config
  --limit N
  --canary N            canary cells (default 10; 0 disables)
  --cell-timeout SECONDS
                        per-cell wall clock before the worker is killed and the session sealed
                        aborted (default 1800)
  --jobs N              concurrent traces (>= 1; default 1, or computed with a local preset)
  --start-stagger SECONDS
                        spread the first cell start of each worker

environment and consent:
  --env-file PATH
  --env-stdin           read the endpoint variables as one JSON object from stdin (D-395; for a
                        GUI with a keychain); exclusive with --env-file, and the default .env is
                        not read
  --keychain            read the selected endpoint's key from the OS keychain (agentprov keys;
                        D-702); exclusive with --env-file and --env-stdin, and the default .env is
                        not read
  --allow-custom-endpoint
  --containment {sandbox-exec,dedicated-user,vm}
  --autodojo-cache PATH
                        AutoDojo attack cache copied from the pinned fork (verified against its
                        tree; D.11.3 rule 5)
  --autodojo-variant K  the cache's variant index (integer >= 0)
  --allow-network       let T0 fetch the pinned AutoDojo commit into the fetch cache to verify
                        --autodojo-cache

API caps (D-725: required for an API endpoint, optional otherwise):
  --max-calls N         billed model calls of the corpus at most, preflight probes included; a
                        cell starts only if its worst case fits
  --max-cost-usd USD    spend of the corpus at most (an upper bound priced from the recorded
                        usage); needs --price-in and --price-out
  --price-in USD_PER_MTOK
                        USD per million input-side tokens (the highest of input, cache write and
                        cached)
  --price-out USD_PER_MTOK
                        USD per million output tokens

estimate:
  --stats-corpus DIR    measure calls, tokens and time in this stored corpus (a sample of its AER
                        files, counts only; repeatable, at most 16)
  --format {text,json}  json: one agentprov-estimate/0.1 document on stdout
```

## agentprov jobs

```text
usage: agentprov jobs [-h] [--version] [-v] [-q] [--log-format {text,json}] [--log-file PATH]
                      [--log-content] [--progress {off,summary,status,steps,trace}]
                      [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                      [--progress-interval SECONDS] [--progress-max-bytes N] [--control-file PATH]
                      [--show-content] [--content-chars N] [--json] [--summary-json PATH]
                      [--max-listed N] [--no-colour] [--break-stale-lock]
                      ACTION ...

``agentprov jobs``: detached jobs that outlive the command that started them (D-704; GUI design
§4; reverse CLI

positional arguments:
  ACTION
    start               start ARGV (after --) as a detached job
    list                the jobs, newest first
    show                one job, with the tails of its output
    follow              print a job's progress (or log) lines until it ends
    stop                a graceful stop (SIGTERM to the job's CLI)
    drain               finish the units in flight, start no new ones (needs --with-control-file)
    resume              start the job's request again (the CLI's resume rules decide what is
                        redone)
    kill                force kill the job's whole process tree
    prune               delete old ended jobs (lists them without --yes)

options:
  -h, --help            show this help message and exit

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

### agentprov jobs start

```text
usage: agentprov jobs start [-h] [--version] [-v] [-q] [--log-format {text,json}]
                            [--log-file PATH] [--log-content]
                            [--progress {off,summary,status,steps,trace}]
                            [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                            [--progress-interval SECONDS] [--progress-max-bytes N]
                            [--control-file PATH] [--show-content] [--content-chars N] [--json]
                            [--summary-json PATH] [--max-listed N] [--no-colour]
                            [--break-stale-lock] [--label TEXT] [--writes DIR] [--reads DIR]
                            [--slot {network,backends}] [--with-control-file] [--queue-cpu N]
                            [--progress-level {status,steps}] [--tool tools/NAME.py] [--note TEXT]
                            [--meta KEY=VALUE] [--format {text,json}]
                            ...

positional arguments:
  -- ARGV               the agentprov arguments of the job

options:
  -h, --help            show this help message and exit
  --label TEXT          a label shown in lists
  --writes DIR          a corpus the job writes (one writer per corpus; repeatable)
  --reads DIR           a corpus the job reads (repeatable)
  --slot {network,backends}
                        a global slot (one job at a time)
  --with-control-file   give the job a control file (drain, D-394)
  --queue-cpu N         run through the machine-wide job queue reserving N CPUs
  --progress-level {status,steps}
  --tool tools/NAME.py  run one repository tool of this checkout instead of agentprov (ARGV are
                        its arguments)
  --note TEXT           a note recorded with the job
  --meta KEY=VALUE      a fact recorded with the job (KEY [a-z_][a-z0-9_]*; VALUE a JSON scalar or
                        text; repeatable)
  --format {text,json}

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

### agentprov jobs list

```text
usage: agentprov jobs list [-h] [--version] [-v] [-q] [--log-format {text,json}] [--log-file PATH]
                           [--log-content] [--progress {off,summary,status,steps,trace}]
                           [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                           [--progress-interval SECONDS] [--progress-max-bytes N]
                           [--control-file PATH] [--show-content] [--content-chars N] [--json]
                           [--summary-json PATH] [--max-listed N] [--no-colour]
                           [--break-stale-lock] [--state {running,ended,all}]
                           [--format {text,json}]

options:
  -h, --help            show this help message and exit
  --state {running,ended,all}
  --format {text,json}

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

### agentprov jobs show

```text
usage: agentprov jobs show [-h] [--version] [-v] [-q] [--log-format {text,json}] [--log-file PATH]
                           [--log-content] [--progress {off,summary,status,steps,trace}]
                           [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                           [--progress-interval SECONDS] [--progress-max-bytes N]
                           [--control-file PATH] [--show-content] [--content-chars N] [--json]
                           [--summary-json PATH] [--max-listed N] [--no-colour]
                           [--break-stale-lock] [--format {text,json}]
                           ID

positional arguments:
  ID

options:
  -h, --help            show this help message and exit
  --format {text,json}

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

### agentprov jobs follow

```text
usage: agentprov jobs follow [-h] [--version] [-v] [-q] [--log-format {text,json}]
                             [--log-file PATH] [--log-content]
                             [--progress {off,summary,status,steps,trace}]
                             [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                             [--progress-interval SECONDS] [--progress-max-bytes N]
                             [--control-file PATH] [--show-content] [--content-chars N] [--json]
                             [--summary-json PATH] [--max-listed N] [--no-colour]
                             [--break-stale-lock] [--timeout S] [--log]
                             ID

positional arguments:
  ID

options:
  -h, --help            show this help message and exit
  --timeout S           stop following after S seconds (0: never)
  --log                 the job's log records (log.jsonl) instead of its progress

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

### agentprov jobs stop

```text
usage: agentprov jobs stop [-h] [--version] [-v] [-q] [--log-format {text,json}] [--log-file PATH]
                           [--log-content] [--progress {off,summary,status,steps,trace}]
                           [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                           [--progress-interval SECONDS] [--progress-max-bytes N]
                           [--control-file PATH] [--show-content] [--content-chars N] [--json]
                           [--summary-json PATH] [--max-listed N] [--no-colour]
                           [--break-stale-lock]
                           ID

positional arguments:
  ID

options:
  -h, --help            show this help message and exit

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

### agentprov jobs drain

```text
usage: agentprov jobs drain [-h] [--version] [-v] [-q] [--log-format {text,json}]
                            [--log-file PATH] [--log-content]
                            [--progress {off,summary,status,steps,trace}]
                            [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                            [--progress-interval SECONDS] [--progress-max-bytes N]
                            [--control-file PATH] [--show-content] [--content-chars N] [--json]
                            [--summary-json PATH] [--max-listed N] [--no-colour]
                            [--break-stale-lock]
                            ID

positional arguments:
  ID

options:
  -h, --help            show this help message and exit

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

### agentprov jobs resume

```text
usage: agentprov jobs resume [-h] [--version] [-v] [-q] [--log-format {text,json}]
                             [--log-file PATH] [--log-content]
                             [--progress {off,summary,status,steps,trace}]
                             [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                             [--progress-interval SECONDS] [--progress-max-bytes N]
                             [--control-file PATH] [--show-content] [--content-chars N] [--json]
                             [--summary-json PATH] [--max-listed N] [--no-colour]
                             [--break-stale-lock] [--format {text,json}]
                             ID

positional arguments:
  ID

options:
  -h, --help            show this help message and exit
  --format {text,json}

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

### agentprov jobs kill

```text
usage: agentprov jobs kill [-h] [--version] [-v] [-q] [--log-format {text,json}] [--log-file PATH]
                           [--log-content] [--progress {off,summary,status,steps,trace}]
                           [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                           [--progress-interval SECONDS] [--progress-max-bytes N]
                           [--control-file PATH] [--show-content] [--content-chars N] [--json]
                           [--summary-json PATH] [--max-listed N] [--no-colour]
                           [--break-stale-lock] [--yes]
                           ID

positional arguments:
  ID

options:
  -h, --help            show this help message and exit
  --yes                 confirm (a forced kill can leave a stale lock)

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

### agentprov jobs prune

```text
usage: agentprov jobs prune [-h] [--version] [-v] [-q] [--log-format {text,json}]
                            [--log-file PATH] [--log-content]
                            [--progress {off,summary,status,steps,trace}]
                            [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                            [--progress-interval SECONDS] [--progress-max-bytes N]
                            [--control-file PATH] [--show-content] [--content-chars N] [--json]
                            [--summary-json PATH] [--max-listed N] [--no-colour]
                            [--break-stale-lock] [--keep N] [--max-age-days D] [--yes]
                            [--format {text,json}]

options:
  -h, --help            show this help message and exit
  --keep N              keep the newest N ended jobs (default: the setting jobs.retention, else
                        200)
  --max-age-days D      and none older than D days (default: the setting jobs.retention_days, else
                        90)
  --yes                 delete them
  --format {text,json}

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

## agentprov batch

```text
usage: agentprov batch [-h] [--version] [-v] [-q] [--log-format {text,json}] [--log-file PATH]
                       [--log-content] [--progress {off,summary,status,steps,trace}]
                       [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                       [--progress-interval SECONDS] [--progress-max-bytes N]
                       [--control-file PATH] [--show-content] [--content-chars N] [--json]
                       [--summary-json PATH] [--max-listed N] [--no-colour] [--break-stale-lock]
                       ACTION ...

``agentprov batch``: ordered job lists that run as one job (D-704; GUI design §4.4; user decision
2026-10-22).

positional arguments:
  ACTION
    create              create a batch from a step list (not started)
    start               start the batch's driver job
    resume              start a new driver for a batch whose driver ended
    run                 advance the batch in the foreground until it is done (the driver)
    stop                stop the driver (the steps it started keep running)
    list                the batches, newest first
    show                one batch and its steps

options:
  -h, --help            show this help message and exit

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

### agentprov batch create

```text
usage: agentprov batch create [-h] [--version] [-v] [-q] [--log-format {text,json}]
                              [--log-file PATH] [--log-content]
                              [--progress {off,summary,status,steps,trace}]
                              [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                              [--progress-interval SECONDS] [--progress-max-bytes N]
                              [--control-file PATH] [--show-content] [--content-chars N] [--json]
                              [--summary-json PATH] [--max-listed N] [--no-colour]
                              [--break-stale-lock] [--stdin] [--label TEXT] [--concurrency N]
                              [--continue-on-failure | --no-continue-on-failure]
                              [--format {text,json}]
                              [SPEC.json]

positional arguments:
  SPEC.json             the step list (a file)

options:
  -h, --help            show this help message and exit
  --stdin               read the step list from stdin instead
  --label TEXT
  --concurrency N       steps at a time (1 to 16)
  --continue-on-failure, --no-continue-on-failure
                        go on after a step ends with exit 4 or 70 (default: the setting
                        jobs.continue_on_failure)
  --format {text,json}

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

### agentprov batch start

```text
usage: agentprov batch start [-h] [--version] [-v] [-q] [--log-format {text,json}]
                             [--log-file PATH] [--log-content]
                             [--progress {off,summary,status,steps,trace}]
                             [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                             [--progress-interval SECONDS] [--progress-max-bytes N]
                             [--control-file PATH] [--show-content] [--content-chars N] [--json]
                             [--summary-json PATH] [--max-listed N] [--no-colour]
                             [--break-stale-lock] [--confirm-r2] [--format {text,json}]
                             ID

positional arguments:
  ID

options:
  -h, --help            show this help message and exit
  --confirm-r2          confirm the batch's R2 steps (network, downloads, paid calls) for this
                        driver
  --format {text,json}

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

### agentprov batch resume

```text
usage: agentprov batch resume [-h] [--version] [-v] [-q] [--log-format {text,json}]
                              [--log-file PATH] [--log-content]
                              [--progress {off,summary,status,steps,trace}]
                              [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                              [--progress-interval SECONDS] [--progress-max-bytes N]
                              [--control-file PATH] [--show-content] [--content-chars N] [--json]
                              [--summary-json PATH] [--max-listed N] [--no-colour]
                              [--break-stale-lock] [--confirm-r2] [--format {text,json}]
                              ID

positional arguments:
  ID

options:
  -h, --help            show this help message and exit
  --confirm-r2          confirm the batch's R2 steps (network, downloads, paid calls) for this
                        driver
  --format {text,json}

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

### agentprov batch run

```text
usage: agentprov batch run [-h] [--version] [-v] [-q] [--log-format {text,json}] [--log-file PATH]
                           [--log-content] [--progress {off,summary,status,steps,trace}]
                           [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                           [--progress-interval SECONDS] [--progress-max-bytes N]
                           [--control-file PATH] [--show-content] [--content-chars N] [--json]
                           [--summary-json PATH] [--max-listed N] [--no-colour]
                           [--break-stale-lock] [--confirm-r2] [--interval S]
                           ID

positional arguments:
  ID

options:
  -h, --help            show this help message and exit
  --confirm-r2          confirm the batch's R2 steps (network, downloads, paid calls) for this
                        driver
  --interval S          seconds between ticks

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

### agentprov batch stop

```text
usage: agentprov batch stop [-h] [--version] [-v] [-q] [--log-format {text,json}]
                            [--log-file PATH] [--log-content]
                            [--progress {off,summary,status,steps,trace}]
                            [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                            [--progress-interval SECONDS] [--progress-max-bytes N]
                            [--control-file PATH] [--show-content] [--content-chars N] [--json]
                            [--summary-json PATH] [--max-listed N] [--no-colour]
                            [--break-stale-lock] [--steps]
                            ID

positional arguments:
  ID

options:
  -h, --help            show this help message and exit
  --steps               also stop the running steps (one SIGTERM each)

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

### agentprov batch list

```text
usage: agentprov batch list [-h] [--version] [-v] [-q] [--log-format {text,json}]
                            [--log-file PATH] [--log-content]
                            [--progress {off,summary,status,steps,trace}]
                            [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                            [--progress-interval SECONDS] [--progress-max-bytes N]
                            [--control-file PATH] [--show-content] [--content-chars N] [--json]
                            [--summary-json PATH] [--max-listed N] [--no-colour]
                            [--break-stale-lock] [--format {text,json}]

options:
  -h, --help            show this help message and exit
  --format {text,json}

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

### agentprov batch show

```text
usage: agentprov batch show [-h] [--version] [-v] [-q] [--log-format {text,json}]
                            [--log-file PATH] [--log-content]
                            [--progress {off,summary,status,steps,trace}]
                            [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                            [--progress-interval SECONDS] [--progress-max-bytes N]
                            [--control-file PATH] [--show-content] [--content-chars N] [--json]
                            [--summary-json PATH] [--max-listed N] [--no-colour]
                            [--break-stale-lock] [--format {text,json}]
                            ID

positional arguments:
  ID

options:
  -h, --help            show this help message and exit
  --format {text,json}

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

## agentprov devrun

```text
usage: agentprov devrun [-h] [--version] [-v] [-q] [--log-format {text,json}] [--log-file PATH]
                        [--log-content] [--progress {off,summary,status,steps,trace}]
                        [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                        [--progress-interval SECONDS] [--progress-max-bytes N]
                        [--control-file PATH] [--show-content] [--content-chars N] [--json]
                        [--summary-json PATH] [--max-listed N] [--no-colour] [--break-stale-lock]
                        ACTION ...

``agentprov devrun``: a quick end-to-end check before a full import (D-705; GUI design §19; D-544,
D-529).

positional arguments:
  ACTION
    plan                the parts and steps a start would run
    start               create a run folder and start its batch
    list                the runs, newest first
    prune               delete old run folders (lists them without --yes)

options:
  -h, --help            show this help message and exit

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

### agentprov devrun plan

```text
usage: agentprov devrun plan [-h] [--version] [-v] [-q] [--log-format {text,json}]
                             [--log-file PATH] [--log-content]
                             [--progress {off,summary,status,steps,trace}]
                             [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                             [--progress-interval SECONDS] [--progress-max-bytes N]
                             [--control-file PATH] [--show-content] [--content-chars N] [--json]
                             [--summary-json PATH] [--max-listed N] [--no-colour]
                             [--break-stale-lock] [--format {text,json}]

options:
  -h, --help            show this help message and exit
  --format {text,json}

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

### agentprov devrun start

```text
usage: agentprov devrun start [-h] [--version] [-v] [-q] [--log-format {text,json}]
                              [--log-file PATH] [--log-content]
                              [--progress {off,summary,status,steps,trace}]
                              [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                              [--progress-interval SECONDS] [--progress-max-bytes N]
                              [--control-file PATH] [--show-content] [--content-chars N] [--json]
                              [--summary-json PATH] [--max-listed N] [--no-colour]
                              [--break-stale-lock] [--confirm-r2] [--format {text,json}]

options:
  -h, --help            show this help message and exit
  --confirm-r2          confirm the imports' fetch-cache reads (R2)
  --format {text,json}

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

### agentprov devrun list

```text
usage: agentprov devrun list [-h] [--version] [-v] [-q] [--log-format {text,json}]
                             [--log-file PATH] [--log-content]
                             [--progress {off,summary,status,steps,trace}]
                             [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                             [--progress-interval SECONDS] [--progress-max-bytes N]
                             [--control-file PATH] [--show-content] [--content-chars N] [--json]
                             [--summary-json PATH] [--max-listed N] [--no-colour]
                             [--break-stale-lock] [--format {text,json}]

options:
  -h, --help            show this help message and exit
  --format {text,json}

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

### agentprov devrun prune

```text
usage: agentprov devrun prune [-h] [--version] [-v] [-q] [--log-format {text,json}]
                              [--log-file PATH] [--log-content]
                              [--progress {off,summary,status,steps,trace}]
                              [--progress-format {auto,tty,plain,jsonl}] [--progress-file PATH]
                              [--progress-interval SECONDS] [--progress-max-bytes N]
                              [--control-file PATH] [--show-content] [--content-chars N] [--json]
                              [--summary-json PATH] [--max-listed N] [--no-colour]
                              [--break-stale-lock] [--keep N] [--yes]

options:
  -h, --help            show this help message and exit
  --keep N              keep the newest N (default devrun.keep)
  --yes                 delete them

global options:
  --version             show versions and exit
  -v, --verbose         log DEBUG (repeatable)
  -q, --quiet           log WARNING and above; implies --progress off
  --log-format {text,json}
                        stderr log format (default text)
  --log-file PATH       also log to PATH (DEBUG, JSON lines)
  --log-content         permit escaped content excerpts in DEBUG logs
  --progress {off,summary,status,steps,trace}
                        live feedback level on stderr (default: status on a terminal, else
                        summary; env AGENTPROV_PROGRESS)
  --progress-format {auto,tty,plain,jsonl}
                        feedback rendering (default auto: tty on an interactive terminal, else
                        plain)
  --progress-file PATH  also append feedback events as agentprov-progress/0.2 JSON lines to PATH
                        (never below status)
  --progress-interval SECONDS
                        heartbeat interval of --progress-file (default 2, minimum 1)
  --progress-max-bytes N
                        rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64
                        KiB)
  --control-file PATH   writers: poll PATH for an agentprov-control/0.1 request (drain or stop;
                        D-394)
  --show-content        add escaped content excerpts at steps and trace
  --content-chars N     excerpt length for --show-content (default 200, max 2000)
  --json                summary document to stdout
  --summary-json PATH   write the summary document to PATH (atomic)
  --max-listed N        cap on failures[] entries in the summary (default 100)
  --no-colour, --no-color
                        no ANSI colour
  --break-stale-lock    writers only: remove a lock whose pid is dead
```

<!-- END generated: cli -->
