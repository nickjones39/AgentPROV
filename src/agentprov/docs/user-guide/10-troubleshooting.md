# 10. Troubleshooting

## Exit codes

Every `agentprov` command ends with one of these exit codes (`src/agentprov/cli/common.py`, `EXIT_CODES`; specification
[N.1.3](https://github.com/nickjones39/AgentPROV/blob/main/docs/architecture/MN_repo_cli.md)):

| Code | Outcome | Meaning |
|---|---|---|
| 0 | ok | the command did what was asked |
| 1 | failures | it ran, but something failed: an execution failed validation, a verification check failed, an unexplained change was found, or (in strict and release modes) a check was skipped |
| 2 | usage | the command line is wrong or incomplete (a missing option, a conflicting choice, a path that cannot work) |
| 3 | environment | something outside the command is missing: an extra, a tool, a backend environment |
| 4 | refused | a guard refused a precondition: a sealed corpus, an unpinned input, an uncommitted checkout, a missing release scan, a held lock |
| 5 | unsupported | the source, part or capability is not supported on this build (for example a `planned` part) |
| 70 | internal | an unexpected error: a bug. Rerun with `-v` for the traceback frames, and report it |
| 130 | interrupted | stopped by Ctrl-C (or SIGHUP, SIGTERM); in-flight work was sealed or rolled back |

Errors name a code in brackets, such as `[corpus.sealed]`, which you can search for in the source and the
specification. `--json` (or `--summary-json PATH`) prints a summary document with the exit code, the outcome and, for a
refusal, its code and reason.

## Common refusals and their fixes

| Message | Exit | Fix |
|---|---|---|
| `[raw.origin.local] --input needs --verify-against-pin` | 4 | add `--verify-against-pin`, or use `--fetch` ([chapter 3](03-sources-and-import.md#pins-why-an-import-needs-one)) |
| `[raw.fetch.not_cached] … is not in the fetch cache and the network is not allowed` | 4 | fill the cache with `agentprov fetch --profile ID --pin ROLE --allow-network` (a download), or point `--cache-dir` at a cache that holds the pin |
| `source … has several importable parts (…); name one with --snapshot or --pin` | 2 | add `--snapshot` |
| `cannot import '…': planned (part …)` | 5 | the part is not open for import on this build; read its caveat in `agentprov info` |
| `[corpus.sealed] refusing to write inside a sealed corpus` | 4 | a sealed corpus is never changed; write a new version with `derive --out` or `recompute --out` |
| `[corpus.derive.out_exists]` | 4 | `--out` must name a new directory |
| `[corpus.derive.version_drift]` | 4 | the corpus was built by another version; recompute it at its building commit, or re-import |
| `[package.refused.git] … the producer commit must be known and its tree clean` | 4 | commit or stash your changes before sealing |
| `no corpus spec at '…'; name it with --spec` | 2 | give `--spec corpora/<id>/corpus-spec.toml` |
| `corpora/datasheet-statements.toml is missing beside the corpora directory` | 2 | put the spec in `<dir>/<id>/` with `datasheet-statements.toml` in `<dir>/` |
| `[release.refused.scan_missing]` | 4 | run `uv run python tools/release_scan.py DIR` and triage every finding |
| `[cli.refused.unconfirmed]` | 4 | `purge` needs `--yes` when it cannot ask |
| `verify --release: give --root-digest sha256:...` | 2 | add the externally published root digest |
| `[render.extra_missing]` | 3 | `uv sync --frozen --group docs --extra render` |
| `validate --release` exits 1 but reports 0 failed | 1 | the summary ends `skipped, not passed: tier shacl (not implemented in this build)`: release validation cannot pass until that tier exists; use `--strict` |
| `--summary-json: the directory '…' does not exist` | 2 | create the directory first; output paths are checked before the command starts |

**Corpora must live outside Git working trees.** A writer refuses to create a corpus inside a git work tree unless
the path is git-ignored, so a corpus can never be committed by accident. Use `~/.agentprov/corpora` or another
directory outside your checkout.

## Stale locks

Only one writer may work on a corpus at a time. A writer holds `DIR.partial/.agentprov.lock`, which records its process
id, host and command. If the writer died without cleaning up (a crash, a power cut), the next writer refuses:

```text
agentprov: error [io.lock_held]: stale lock present (dead pid on this host); use --break-stale-lock
```

If you are sure no other process is writing the corpus, run the same command again with the global option before the
command name:

```bash
agentprov --break-stale-lock import agentdojo --snapshot 2024-06 --fetch --corpus corpora/demo
```

`--break-stale-lock` removes a lock only when its process is dead and on this host. A live lock, a lock from another
host and an unreadable lock file are never removed (`lock held by another writer`). A sealed corpus never carries a
lock; `verify` reports a leftover one as `corpus.tree.lock`.

**Interrupted imports.** Ctrl-C seals or rolls back the in-flight units and exits 130. The snapshot is then marked
`incomplete`, and `package`, `derive` and `recompute` refuse the corpus until you run the same import again, which
resumes where it stopped.

## The wrong Python

`agentprov --version` shows the interpreter. If it is not 3.14.8 or later:

- If a conda environment is active (`CONDA_PREFIX` is set), uv treats it like an active virtual environment and may
  build `.venv` on conda's Python. Deactivate it, or name the interpreter: `uv sync --python 3.14.8`.
- `uv python install 3.14.8` installs a managed interpreter (a download).
- Below 3.14.8, dev mode works but records an `interpreter_advisory`; release mode refuses archive and stream
  ingestion (exit 3), and `package` refuses a corpus whose manifest records an advisory (exit 4). There is no override.

## Backend environments

Backend environments live in `$AGENTPROV_HOME/envs/<id>` and are built by `agentprov backends build BACKEND`.

- **Check an environment** without changing it: `agentprov backends build agentdojo --offline-check`. It verifies the
  build marker, the lockfile, every installed file, the guarded modules and the backend's identity.
- **Rebuild it** after the backend's lockfile, `backends/shared` or the sandbox profile changed: run
  `agentprov backends build agentdojo` again. It syncs offline from the uv cache; `--allow-network` lets uv download
  missing packages (ask yourself whether you want that first). `--dry-run` shows the environment id, the lock digest
  and whether the network would be used.
- A run whose environment is missing or out of date stops with exit 3 and names the build command.
- Do not edit an environment by hand: every installed file is hashed, and a changed file fails the identity check.

## Live runs

Run live commands from inside the repository checkout: `run`, `backends build` and `migrate` find the backend projects
(`backends/…`) from the current directory, and outside it they exit 3 with `[backend.repository_missing]: this command
needs the AgentPROV repository checkout`. The corpus you give them must still be **outside** the checkout.

| You see | Exit | Because, and the fix |
|---|---|---|
| `[backend.unavailable]` … "run 'agentprov backends build X'" | 3 | the backend environment is not built, or its marker is missing: build it (offline from the uv cache), then `--offline-check` |
| `[adapter.identity_mismatch]`, "the marker's lock_sha256 differs from backends/<b>/uv.lock" | 3 | a git-pinned environment (`autodojo`, `agentdyn`) whose lock changed since it was built: rebuild. A version-pinned one (`agentdojo`) gets a new id instead ([chapter 7](07-live-runs.md#what-an-environment-id-means)) |
| `--offline-check` fails after an update | 3 | the code in `backends/shared`, the sandbox profile or a lock changed: rebuild the environment |
| the environment is "being built" or "in use" | 4 | a build and a run exclude each other on one environment; wait for the other to finish |
| a worker's `hello` ends with `PermissionError` on a `.env.example` file (AgentDyn) | 3 | the environment predates the identity fix: rebuild it |
| `cli.refused.api_caps` | 4 | an API endpoint needs `--max-calls`, `--max-cost-usd`, `--price-in` and `--price-out` |
| `--max-cost-usd needs --price-in and --price-out` / `--price-in and --price-out price --max-cost-usd` | 2 | the two go together |
| `cli.refused.consent` | 4 | no consent flag and no terminal; `--i-consent-to-local-run` is for local servers only |
| `cli.refused.containment` | 4 | `--containment` is required; `sandbox-exec` needs macOS and a passed probe from the build |
| `cli.environment.credential` | 3 | no key in the keychain or `.env`: `agentprov keys set NAME` |
| `cli.environment.live_extra` | 3 | `--env-file` needs `uv sync --frozen --group docs --extra live` |
| `cli.refused.endpoint` | 4 | a refused base URL (not https, a user name in the URL, a host outside `endpoints.toml`, or a LAN address without `--allow-lan-endpoint`); `--allow-custom-endpoint` for a custom host |
| `run.local.unreachable`, `run.local.model_not_served` | 3 | the server is down, or does not serve that model id (the message lists the served ids) |
| `run.local.wrong_server`, `run.local.remote_model` | 4 | another kind of server on that port; or a cloud model listed by a local server |
| `cli.refused.local_tool_prompt` | 4 | LM Studio serves the model without native tool use; `--allow-text-tool-calls` accepts it |
| `cli.refused.preflight` (A9, A4) | 4 | the probe found no evidence that the system message reached the model, or text-encoded tool calls: read the message; `--allow-text-tool-calls` lifts A4 |
| `cli.environment.preflight` | 3 | the endpoint is not reachable |
| `cli.refused.mixed_config` | 4 | the corpus holds sessions of another configuration (or scripted and real sessions): use a new corpus, or `--allow-mixed-config` for a different configuration digest |
| `cannot run 'X': defence …` | 5 | see [Defences](07-live-runs.md#defences): the backend, the suite or the registry |
| `--attack autodojo needs --autodojo-cache and --autodojo-variant` | 2 | give both; `cli.environment.autodojo_cache_blob` or `_commit` (3) mean the file is not in the pinned fork tree, or the pinned commit is not cached |
| `[inspect].limits: missing key(s) message_limit` | 2 | an Inspect plan needs `--message-limit`, `--token-limit` and `--time-limit` |
| `package.unsupported.live` | 5 | live corpora cannot be sealed in this build |

**A run that stopped.** The summary names why. A *canary stop* (A3, A4, A6, A11, A12, A14), a *cap stop* (`cap_reached`,
`cap_bound_exceeded`) and a *config stop* ("a cell's setup refused this configuration") all exit 1 and **resume by
re-running the same command** once the cause is fixed or the cap raised; there is no `--resume`. `--max-attempts` (3) is
counted across invocations, so a cell that keeps failing stops being retried. Ctrl-C seals in-flight sessions `aborted`
and exits 130; press it twice and the run exits at once, leaving sessions in the staging directory, unledgered.
`--break-stale-lock` ([above](#stale-locks)) clears the lock of a run that died.

**Known behaviour that surprises people:**

- A LAN endpoint (`--allow-lan-endpoint`) is classed `api`, not `local`: only a loopback address counts as local. It
  needs the caps and `--i-consent-to-api-costs`, and `--i-consent-to-local-run` is refused for it.

## Feedback, logs and memory

- `--progress off|summary|status|steps|trace` sets the live feedback on stderr; `-q` turns it off. `--progress-file
  PATH` also writes the events as JSON lines (`agentprov-progress/0.2`).
- `-v` logs DEBUG; `--log-file PATH` also logs to a file. Logs never contain content unless you add `--log-content`.
- Each worker job runs under a memory cap (2 GiB for parsing and mapping, 4 GiB for SEM, PROV and validation, never
  above 16 GiB). A job over its cap is stopped and recorded as `worker.limit.rss`, never silently dropped; its sealed
  AER is kept.
- `--jobs N` sets the number of worker processes (0 = the host default). Output is byte-identical for every N, so lower
  it freely on a busy machine.

## Heavy jobs on a shared machine: the job queue

Several imports, rehearsals and test suites on one machine compete for its CPUs and memory. The checkout's
`tools/suite_queue.py` runs each heavy job when it fits; the desktop app uses it too (Settings › Compute, *Run heavy jobs
through the shared job queue*), except on Windows. Run it from a checkout with `uv run python tools/suite_queue.py`:

```bash
uv run python tools/suite_queue.py --status                        # what runs, what waits and why
uv run python tools/suite_queue.py --class import --label demo -- uv run agentprov import SOURCE --input DIR --corpus OUT --jobs 8
```

- **Classes and slots.** A job is a `suite` (the full test suite, one at a time), an `import` or a `rehearsal`
  (`recompute`, `derive`, `verify` and other corpus work in scratch). The slots per class follow the CPU budget: 1
  suite, max(2, ⌊budget / 5⌋) imports and max(2, ⌊budget / 8⌋) rehearsals. For example, on one development machine with
  36 cores (budget 34) that is 1, 6 and 4; on a 12-core machine 1, 2 and 2. `AGENTPROV_QUEUE_SLOTS=import=8,rehearsal=4`
  overrides them.
- **The budget.** By default it is the number of CPUs minus 2 and 75 % of the memory (`AGENTPROV_JOB_CPU_BUDGET`,
  `AGENTPROV_JOB_MEM_GIB_BUDGET`, or Settings › Compute). A job starts when its reservation fits beside the running
  ones, in first-come order.
- **What a job reserves.** An import or rehearsal reserves the `--jobs` (or `--workers`) value on its own command line,
  with 4 GiB per worker: `--cpu` follows `--jobs`. `--jobs 0`, or no `--jobs`, means the host default (min(CPUs, ⌊0.75 ×
  RAM / 4 GiB⌋), for example 36 on one development machine), which is more than the budget, so the job is clamped to the
  budget and runs alone. To share the machine, give `--jobs 8` to `16`. Output is byte-identical for every `--jobs`
  value.
- **A suite beside imports.** A suite run with `pytest -n N` reserves ⌈0.8 × min(N, 10) + 0.5 × max(0, N − 10)⌉ CPUs: 8
  for `-n 10`, 15 for `-n 24`. While a suite waits or runs, imports and rehearsals together keep within the rest of the
  budget (19 of 34 beside a `-n 24` suite, so two 8-CPU imports run next to it). An import that has waited an hour for
  that room goes next, and no new suite starts before it. Queue a suite without `--cpu`.

**Release scans.** `tools/release_scan.py`, and the withholding scan at sealing, read a corpus's stored archives in
parallel, up to the host default at once (D-890). On 72 test archives the scan took 45 s with one reader, 14 s with 4,
7 s with 16 and 10 s with 36. The tool has no `--jobs`, so queued without `--cpu` it reserves the host default and runs
alone, which is what it uses.

**A job wrapped in a script must pass `--cpu` itself.** The queue reads `--jobs` only from the command line it is given.
If that command is a script (`bash my-batch.sh`, `uv run python my_batch.py`) that starts `agentprov … --jobs 8` inside,
the queue sees no `--jobs`, reserves the host default and runs the script alone: on a busy machine it waits until
nothing else runs and then blocks every other job. Give the queue the real figure:

```bash
uv run python tools/suite_queue.py --class import --cpu 8 --label my-batch -- bash my-batch.sh
```

(`--cpu N` also sets the memory to N × 4 GiB; `--mem-gib G` overrides that.)

## Workers and the tier-4 cache

**How far `--jobs` helps.** Output is byte-identical for every `--jobs` value; only the time changes. Two changes of
2026-10-28 let more workers pay off:
- **`validate --jobs N` overlaps its batches (D-893).** The parent reads and stages the next 256-row batch while the
  workers check the current one, instead of leaving them idle. Rows are still recorded in order. On a 3,243-execution
  corpus `--jobs 8` went from 43.5 s to 31.5 s and `--jobs 16` from 46.7 s to 37.0 s.
- **`derive` and `recompute` batches follow the worker count (D-895).** Each batch is 64 units per worker, between 256
  and 1024, unless you set a batch size. Each batch starts its workers anew, and a start costs about a second of system
  time, so larger batches mean fewer starts. On the same corpus `recompute --dry-run --jobs 16` went from 79.7 s to
  64.1 s, about the time of `--jobs 8`.

Past about 8 workers, the parent process sets the pace. It seals each AER, validates it, and writes and fsyncs each
object on one core, so `--jobs 16` is no faster than `--jobs 8`. For example, on one development machine, 8 workers is a
good default for corpus work, and it leaves room in the [queue](#heavy-jobs-on-a-shared-machine-the-job-queue) for other
jobs.

**The tier-4 cache is shared.** The W3C PROV round-trip cache (`$AGENTPROV_HOME/cache/tier4`, [chapter
4](04-derive-recompute-validate-verify.md#validate)) is one store for every command and session on the machine. It
keeps the most recently used entries up to its cap: 2 GiB unless `compute.validation_cache_gib` is set (D-894). A miss
costs about four times a hit. On the 3,243-execution corpus, `recompute --dry-run --jobs 3` took 105.7 s with a warm
cache and 400.9 s with `--no-validation-cache`. Under the 2 GiB cap, one large corpus (18,241 executions) can push a
smaller corpus's entries out, so the next run on the smaller corpus starts cold. Measured: 1,705 CPU-seconds, where a
warm run spends about 330.

On a machine with disk to spare, raise the cap once:

```bash
agentprov settings set compute.validation_cache_gib 32    # GiB, 1 to 4096; for example, on one development machine
```

The cap only limits what is kept, so it never changes a result. It applies to `validate`, `derive`, `recompute`,
`verify --level rederive` and `import`. A machine with little disk to spare keeps the default.

## `AGENTPROV_HOME` on its own volume (macOS)

Imports, derives, recomputes and the test suite write, rename and remove very many small files under
`AGENTPROV_HOME`. macOS records every change in its FSEvents log and may index the new files in Spotlight. On the
project's first machine, after weeks of uptime and corpus churn, the `fseventsd` process grew to 9.8 GiB of memory;
swap filled, and an import was killed. A separate volume avoids that: FSEvents logging and Spotlight indexing can be
turned off for that volume alone, and the rest of the disk keeps them.

The setup used, for example, on one development machine (2026-10-28):

1. **Make an APFS volume** in the startup disk's container. It shares the container's free space, so nothing is
   repartitioned. `diskutil list` names the container (the `synthesized` disk, for example `disk3`):

   ```bash
   diskutil apfs addVolume <container> APFS AgentPROV
   diskutil info AgentPROV            # note the "Volume UUID"
   ```

2. **Turn off FSEvents logging and Spotlight indexing** on it, while it is mounted at `/Volumes/AgentPROV`:

   ```bash
   sudo mkdir -p /Volumes/AgentPROV/.fseventsd
   sudo touch /Volumes/AgentPROV/.fseventsd/no_log
   sudo mdutil -i off /Volumes/AgentPROV
   ```

3. **Copy the data**, keeping its layout, with no AgentPROV process running (no import, job, run or desktop app):
   `ditto ~/.agentprov /Volumes/AgentPROV`. Move the old folder aside, keep it until the copy is checked, and leave an
   empty `~/.agentprov` as the mount point.

4. **Mount the volume at the same path.** Edit `/etc/fstab` with `sudo vifs` (the only supported way) and add one line,
   with the UUID from step 1 and your home folder's absolute path (fstab does not expand `~`):

   ```text
   UUID=<volume UUID> <your home folder>/.agentprov apfs rw
   ```

   Then restart. Keeping the path is what makes the move invisible: `AGENTPROV_HOME` keeps its default, and the backend
   environments, git worktrees and virtual environments under it, which record absolute paths, keep working.

5. **Check it.**
   - `mount` lists the volume on `~/.agentprov`, and `agentprov info` shows `AGENTPROV_HOME    <home>/.agentprov`.
   - `sudo ls ~/.agentprov/.fseventsd` lists `no_log`.
   - Spotlight: `mdutil -s ~/.agentprov` answers "unknown indexing state" for a volume mounted under the home folder,
     so it proves nothing. Probe instead: create a file with a unique name on the volume, wait a minute, and run
     `mdfind -name <that name>`. It must find nothing. Remove the probe file afterwards.
   - `agentprov verify --corpus DIR --level chain` on each corpus you moved.

**Dry runs on the volume.** `derive --dry-run` and `recompute --dry-run`, and `verify --level rederive`, build a private
tree and hard-link the corpus's raw objects into it. A hard link works only within one volume, so the tree is made under
`$AGENTPROV_HOME/tmp` when the corpus is on the `AGENTPROV_HOME` volume (D-891), and the objects are linked, not copied
and hashed again. A corpus kept on a third volume falls back to the system temporary directory and the copy, with the
notice "hard links are not possible here". On the project's corpora the time saved is small (the copy was 49 MB to 223
MB); the change keeps a dry run's writes on the `AGENTPROV_HOME` volume.

**Restart between long series.** Even with the volume set up, restart the machine before a long series (a full
re-import of the collection, the full test suite several times, a capture campaign), so that it starts with daemons
such as `fseventsd` fresh and with swap empty.
