# G5 clean-machine test: Windows x86_64 (under Windows 11 ARM64's x64 emulation)

Status (2026-10-29): **every applicable step passes from main, under emulation.** The bundle built from main `0c87b657`
passed steps 1–6 and 9 in a second clean clone (run `windows-x64-20261028T140349Z`); steps 7–8 are not applicable (the
user's decision, D-867: live runs need macOS or Linux in v0.1). The Mac Studio has no x86_64 hardware, so the x64 bundle
is built and tested inside the Windows 11 ARM64 base, under Windows' own x64 emulation (the user's choice, 2026-10-29).
The label is lifted for that one package, **with the wording "tested under emulation"** (below). The branch runs are kept
below.

## Setup

| Item | Value |
|---|---|
| Guest | the Windows 11 ARM64 base of `windows-arm64.md` (Windows 11 Pro 10.0.26300, unactivated), per-run clones |
| x64 tooling | `uv-x86_64-pc-windows-msvc.zip` 0.13.5 (pinned), so uv installs x64 interpreters: CPython 3.14.8 x64 for the core and GUI, CPython 3.12 x64 for the AgentDojo backend |
| Bundle | `AgentPROV-windows-amd64.zip`, `sha256:351fa55f28d261eebad0391671b5878ab3bee60fe47bb19283fde6f8dd21aea0`, built from `0d4c9a31`; `AgentPROV.exe` and `python314.dll` are PE32+ x86-64 |

## Runs

| Run (UTC) | Checkout | Steps 1–5, 9 | Step 6 | Step 7 | Step 8 |
|---|---|---|---|---|---|
| 11:52 | `bfe11bfd` | pass | **fail**: both job supervisors crashed (below) | pass | fail: `worker_died` |
| 12:41 | `0d4c9a31` | pass | pass | pass | fail: `worker_died` |
| 12:49 | `3b7e6084` | pass | pass | pass | fail: `worker_died` |
| 12:55 | `5191be91` | pass | pass | pass | fail: `worker_died`; every backend import works |

**Step 7 passes on x64**, unlike ARM64: `torch`, `cryptography` and `cachebox` have `win_amd64` wheels, and the
environment builds with its marker complete and the sandbox probe `not_applicable`.

## Two bugs found and fixed (the user's yes, 2026-10-29; commit `0d4c9a31`)

1. **Job records on Windows:** `os.replace` onto `job.json` fails with `WinError 5` while another process has the file
   open, and the manager reads `job.json` every 20 ms while a job starts. Under emulation every supervisor crashed;
   natively one ARM64 run in four. `jobs.manager.atomic_write_json` now retries for up to about a second on Windows
   only (class 0; tests in `tests/jobs/test_jobs_windows_paths.py`).
2. **Package name:** `build_bundle.py` named the package from `platform.machine()`, which names the emulating host
   (`ARM64`) for an x64 Python, so the x64 bundle came out as `AgentPROV-windows-arm64.zip`. Windows and Linux packages
   are now named from `sysconfig.get_platform()` (test in `gui/tests/test_g5_bundle_layouts.py`).

## Step 8's worker dies on Windows x64 (not applicable for v0.1)

The scripted cell (`run agentdojo --suite banking --user-tasks user_task_1 --benign only --llm-script`) ends
`inconclusive`; the session ledger's note is `worker_died`. The backend environment's own interpreter imports
`agentdojo`, `agentdojo.agent_pipeline` and `agentprov_backend.worker` without error (`numpy` and `torch` are not in the
environment), and the protocol channel is binary, so line endings are not the cause. The worker's traceback, if any,
is lost: the campaign drops the `WorkerDied` reason (only the note is kept) and deletes the worker's staging folder,
with its `worker.stderr.log`, even with `--keep-staging`.

The user decided (2026-10-29, D-867) to treat steps 7–8 on Windows x64 as not applicable for v0.1, as on ARM64; the
harness records them with `applicable: false` (`-LiveRuns` still runs them, for diagnosis). Logging why a worker died
and keeping its log under `--keep-staging` is a separate task the orchestrator tracks; G5 does not change
`cli/live/campaign.py`.

## The label

**Lifted for one artefact, under emulation** (D-863 with D-867: steps 1–6 and 9 passed on a run from main, 2026-10-29):

| | |
|---|---|
| Package | `AgentPROV-windows-amd64.zip`, `sha256:5c17b05160c93da3bcfbe9daa827541bcc24d43de0efe92da5cb57d095c514be` |
| Built | from main `0c87b657` by `driver.py build windows-x64` with the x64 uv, in a clean Windows 11 ARM64 clone under its x64 emulation (CPython 3.14.8 x64; `AgentPROV.exe` and `python314.dll` are PE32+ x86-64; 106.0 MB; unsigned) |
| Tested | run `windows-x64-20261028T140349Z`, level W, checkout `0c87b657`: steps 1–6 and 9 pass, 7–8 not applicable |

It stays on Windows x64 bundles built any other way and on native x86_64 hardware, which this test does not cover.
Proposed wording for the guide's Windows x86_64 row, for the orchestrator to place: "Windows x86_64: one folder (zip),
unsigned (SmartScreen: More info, then Run anyway); **tested under emulation** (Windows 11 on ARM's x64 emulation, a
clean machine; package sha256 `5c17b051…14be`), not on x86_64 hardware. Live runs (`agentprov run`) are not available on
Windows in v0.1; use macOS or Linux."
