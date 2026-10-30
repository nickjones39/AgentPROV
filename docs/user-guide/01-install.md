# 1. Installing AgentPROV

AgentPROV is a Python project managed with [uv](https://docs.astral.sh/uv/). The core (`agentprov`) and the desktop
app (`agentprov-gui`) run on Python 3.14. Each live backend is a separate uv project on Python 3.12, with its own
lockfile, so benchmark code never shares an environment with the core.

## Requirements

| Component | Requirement |
|---|---|
| uv | 0.12.22 or later (the repository's `required-version`) |
| Core (`agentprov`) | CPython ≥ 3.14 (`requires-python = ">=3.14"`). Release-mode imports of archives and compressed streams need **3.14.8 or later**: below that, `--release`, `package` and the deposit builder refuse, and dev mode records an `interpreter_advisory` |
| Live backends | CPython 3.12.14 (pinned in each backend's `.python-version`), installed by `agentprov backends build` into `$AGENTPROV_HOME/envs/` (chapter 7) |
| Desktop app | Python ≥ 3.14 and PySide6, in the separate `gui/` project (chapter 8) |
| Graph drawing | the `render` extra and the Graphviz `dot` program (optional) |
| Git | needed by `fetch`, `package` (it records the producer commit) and the backend builds |

**Platforms.** AgentPROV has been developed and used on macOS on Apple silicon. The test suite last ran on Linux
(x86_64 and arm64) and Windows in GitHub Actions on 2026-10-08, against early code, and CI has not run since (D-431:
manual dispatch only). In the clean-machine tests of the desktop bundles (G5), bundles built from `main` pass on clean
Ubuntu 24.04 (aarch64) and Windows 11 ARM64 machines, and under emulation on Ubuntu 22.04 x86_64 and Windows x86_64;
Windows has no live runs in v0.1 (D-867). Treat other platforms as untested; cross-platform use is not guaranteed.
AgentPROV probes the host instead of branching on the operating system, and reports the isolation it can give its
worker processes (see `Host` below). Windows has no CPU limit for workers and assigns the Job Object after the process
starts ([G.4.12](https://github.com/nickjones39/AgentPROV/blob/main/docs/architecture/G_security.md)).

## Installing the core

From a checkout of the repository:

```bash
uv python install 3.14.8      # a managed interpreter at the release floor (a download, once)
uv sync --frozen --group docs # the core environment (.venv), the dev tools and the docs group
uv run agentprov --version
```

Any CPython 3.14.8 or later works; `uv python install` is only needed when none is installed. The backends' Python 3.12
is installed the same way (`uv python install 3.12`) before `agentprov backends build` (chapter 7).

```text
agentprov 0.1.0
formats: aer/0.2 sem/0.1 capture/0.1 agentprov-prov/0.1 apv 0.2.0 agentprov-corpus/0.2
python 3.14.8 (interpreter_advisory: none)
```

If `--version` reports a Python below 3.14.8 with an `interpreter_advisory`, uv picked another interpreter; see
[Troubleshooting](10-troubleshooting.md#the-wrong-python).

## Checking the installation: `agentprov info`

`agentprov info` (alias `sources`) prints the versions, the source registry (chapter 3), the installation and the
host. The last two sections look like this (for example, on one development machine):

```text
Installation
  python            3.14.8 (CPython)
  interpreter_advisory  none
  extras            live: no, render: yes, shacl: no, zenodo: yes
  tools             git: yes, uv: yes, dot: yes  (versions are not probed)
  AGENTPROV_HOME    <home>/.agentprov
  cache             <home>/.agentprov/cache
  backend envs      none built

Host
  os / arch         darwin 27.0.0 / arm64 (machine arm64)
  cpus / memory     12 / 32.0 GiB
  rlimits           core, cpu, fsize, nofile, as  (hasattr(resource, RLIMIT_*) and getrlimit() answers)
  rlimit_as_enforced False  (child could not set RLIMIT_AS (rejected by the OS))
  rss_sampler       libproc  (libproc returned a plausible RSS for this process)
  tree_kill         killpg  (os.killpg exists; workers start in their own session)
  hard_memory_cap   none  (RLIMIT_AS not enforced and no Job Object)
  isolation grade   watchdog; calibration ok
```

On macOS the kernel does not enforce `RLIMIT_AS`, so worker memory is capped by a watchdog that samples each worker's
resident memory and stops it over its cap (`isolation grade watchdog`). `agentprov info --format json` prints the same
information as one JSON document.

## Optional extras

| Extra | What it adds | Install |
|---|---|---|
| `render` | `pydot`, for `agentprov render`. Images also need Graphviz `dot` on the `PATH` | `uv sync --frozen --group docs --extra render` |
| `shacl` | `pyshacl`, reserved for the SHACL tier of `agentprov validate`, which is not implemented in this build | `uv sync --frozen --group docs --extra shacl` |
| `live` | `python-dotenv`, to read `.env` at the live CLI entry | `uv sync --frozen --group docs --extra live` |
| `zenodo` | `agentprov-zenodo`, the draft-only Zenodo uploader (`python -I -m agentprov_zenodo`; [chapter 5](05-package-and-deposit.md#creating-an-unpublished-zenodo-draft), D-880) | already in a checkout's `dev` group; `uv sync --frozen --group docs --extra zenodo` only with `--no-dev` |

Extras combine: `uv sync --frozen --group docs --extra render --extra shacl`.

**The `zenodo` extra** is the only one a checkout already has: the default `dev` group installs `agentprov-zenodo` too,
because the desktop app runs the uploader from the checkout's environment. It is a separate distribution (`zenodo/` in
the repository, like `capture/`), and the `agentprov` package never imports it, so the core stays offline for releases.
`agentprov info` lists it among the extras (`zenodo: yes` when it is installed).

**Dependency groups.** Besides the default `dev` group (the test and lint tools), the repository has a `docs` group:
MkDocs and Material for MkDocs, which build this guide as a website (`uv sync --frozen --group docs`, then
`uv run --group docs mkdocs serve`). It is not installed by default.

**`uv sync` is exact.** It makes `.venv` match the command line, so a later plain `uv sync` *removes* the `docs` group
and every extra you do not name again. Name them every time (`uv sync --frozen --group docs --extra render`), or use
`uv run --group docs …`, which installs the group before it runs the command.

A command that needs a missing extra says so and exits 3, for example:

```text
$ agentprov render --corpus corpora/demo --ex ex_37evkqmflf2sqxvs7cc6sbgx6c
agentprov: error [render.extra_missing]: the render extra (pydot) is not installed; run: uv sync --frozen --group docs --extra render
```

`validate --release` runs every applicable tier, including `shacl`, which this build does not implement yet: it is
skipped and the command exits 1 (see [chapter 4](04-derive-recompute-validate-verify.md#validate)).

## Where AgentPROV keeps its data: `AGENTPROV_HOME`

Corpora, the fetch cache, backend environments and staging directories live under `AGENTPROV_HOME`, which defaults to
`~/.agentprov`. They are never inside the repository, and they are never committed.

| Path | What it holds |
|---|---|
| `corpora/` | the conventional place for corpora (any directory works: every command takes `--corpus DIR`) |
| `cache/` | the verified, extraction-free fetch cache: `git/` (bare object stores of pinned commits), `zenodo/`, `hf/`, `url/`, `git-history/` (`agentprov fetch --history`), `model-digests.jsonl`, and `acquisitions.jsonl`, one line per real download. `$AGENTPROV_UPSTREAM_CACHE` points elsewhere |
| `cache/tier4/` | the cache of W3C PROV round-trip results (`--no-validation-cache` bypasses it) |
| `envs/` | backend environments built by `agentprov backends build`, one directory per environment id |
| `staging/`, `t2home/` | per-session staging and the private home directory of live workers |
| `dev-runs/` | the desktop app's dev runs (scratch corpora) |
| `jobs/` | detached jobs (`agentprov jobs`) |
| `calibration/` | `agentprov run --tune-jobs` sweeps |
| `tmp/` | private trees of dry runs and `verify --level rederive` |
| `models-cache/` | dated provider model lists (`agentprov models`) |
| `settings.json` | shared CLI and GUI settings (`agentprov settings`); never a key |

A full collection of corpora is large (tens of GB) and changes many files. On macOS, give `AGENTPROV_HOME` its own
volume ([chapter 10](10-troubleshooting.md#agentprov_home-on-its-own-volume-macos)).

Set `AGENTPROV_HOME` to try things without touching your real data. The examples in this guide ran with a temporary
`AGENTPROV_HOME`.

## Next

[Chapter 2](02-concepts.md) explains what AgentPROV builds; [chapter 3](03-sources-and-import.md) imports the demo
corpus.
