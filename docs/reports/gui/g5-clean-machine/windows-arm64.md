# G5 clean-machine test: Windows 11 ARM64

Status (2026-10-28): **every applicable step passes from main.** The bundle built from main `38729b27` in a clean
Windows 11 ARM64 VM passed steps 1–6 and 9 in a second clean VM (run `windows-arm64-20261028T113033Z`); steps 7–8 are
not applicable on Windows ARM64 for v0.1 (the user's decision, D-867). The label is lifted for that one package (below).
The earlier runs on the branch are described as they happened.

## Setup

| Item | Value |
|---|---|
| Tool | UTM 5.0.8 (QEMU backend), driven by AppleScript/JXA (D-867); `windows.py` |
| Image | the user's download of `Windows11_Client_arm64_en-us_26300_9457.iso` from Microsoft's Windows 11 for Arm page, `sha256:8992f2d2…623e9c` (Microsoft's published hash) |
| Guest | Windows 11 Pro 10.0.26300 ARM64, **unactivated** (the user's choice: "run unactivated within Microsoft's terms"; licence status 5), 6 CPUs, 12 GiB, 64 GiB NVMe, `virtio-ramfb` display (1024×768), LongPathsEnabled 0 |
| Base | unattended install from `autounattend.xml` on a small ISO: no product key, one local test account `agentprov` (generated password, kept under `$AGENTPROV_HOME/vms/windows/`, mode 0600), auto-logon, first logon installs UTM guest tools 0.1.271 and shuts down. The user ticked "TPM 2.0 Device" once in UTM |
| Bundle | `AgentPROV-windows-arm64.zip`, `sha256:614678b0…3f29`, 89.8 MB unpacked, CPython 3.14.8, unsigned; built in a fresh clone from commit `4c6b4547`; all `build_bundle.py` checks pass, including its own offscreen smoke start |
| Corpus | the GUI tests' three-execution mini corpus |

The steps run in a second fresh clone as the auto-logged-on user (a scheduled task with `/IT`), so the window, the
screenshot and the user's Credential Manager are real. UTM's guest agent carries commands and files; no OpenSSH.
Each clone is deleted afterwards only when its UTM notes carry this run's marker (D-862).

## Run `windows-arm64-20261028T103633Z` (checkout `99602e4e`)

| Step | Result |
|---|---|
| 1 `AgentPROV.exe --smoke` (offscreen) | pass |
| 2 start with the `windows` platform plugin, open the mini corpus | pass: window "AgentPROV — mini", alive after load; the toolbar reads "3 executions" (only one row fits at 1024×768) |
| 3 `--preview-helper` with stdin at EOF | pass, 0.16 s |
| 4 `uv sync --locked` (core, gui), `agentprov info` | pass; CPython 3.14.8 for both |
| 5 `keys status`; `set`/`list`/`delete` of a dummy value | pass: `allowed: true`, backend `WinVaultKeyring`; `ANTHROPIC_API_KEY` stored (fixed dummy text) then deleted |
| 6 `jobs start -- info`; `jobs stop`; `jobs kill --yes` | **partial**: `info` ended `ok`/`waited`; the sleeper tool job ended `killed`/`killed`; the graceful stop was not exercised (below) |
| 7 `backends build agentdojo` | **fail**: `uv sync --locked failed for backends/agentdojo` (exit 3) |
| 8 scripted dev run, `validate` | fail: needs step 7 (and a harness quoting bug, fixed since) |
| 9 Run Live containment (P-4) | pass: `dedicated-user` and `vm`, each "declared by you, not enforced or checked by AgentPROV" |

Earlier runs on this branch failed on the harness, not on AgentPROV: UTM's pull needs an existing host file; PowerShell's
`Start-Process -PassThru` reports no exit code unless the process handle is cached; the first base idled in the firmware
because the scripted VM had no display and nobody answered the ISO's "Press any key to boot from CD or DVD" prompt.

## Runs after the decisions

| Run (UTC) | Checkout | Steps 1–5, 9 | Step 6 | Steps 7–8 |
|---|---|---|---|---|
| 10:53 | `06caf906` | pass | **fail**: the sleeper job was already `unobserved` (no pid) when `jobs start` returned, so `kill` found nothing running | not applicable |
| 11:02 | `01a8ed1a` | pass | pass: `info` `ok`/`waited`, sleeper `killed`/`killed`; both `supervisor.txt` empty (breakaway worked, no P-2 fallback) | not applicable |
| 11:30 | main `38729b27` | pass | pass | not applicable |

**Open (intermittent):** in one of four Windows runs the tool job's supervisor exited at once after `jobs start`
(`state: unobserved`, `pid: null`). That run kept no job folder, so the cause is unknown; the harness now copies
`C:\g5\home\jobs` into the results for the next occurrence. It may be a real detach race on Windows (P-2's area) or
an effect of the scheduled-task session; it needs more runs before a fix.

## Finding: the AgentDojo backend cannot be installed on Windows ARM64

`backends/agentdojo/uv.lock` has packages with no Windows ARM64 wheel:
- `torch` 2.14.1: wheels for `win_amd64` only and **no sdist**, so it cannot be installed at all;
- `cryptography` 50.0.2 and `cachebox` 5.2.3: Windows x86 wheels and an sdist only, so they would need a compiler (MSVC,
  and Rust for `cryptography`) in the guest.

Live runs are therefore not available on Windows ARM64 in v0.1 (the live tests already skip on Windows: "the backend
environment is POSIX-only in v0.1"). The user guide does not say this yet. Windows x86_64 is a separate question
(`torch` has a `win_amd64` wheel) and is not run.

## Finding: Windows' graceful stop needs a long-running agentprov job

On Windows a graceful `jobs stop` exists only through the D-394 control file of an **agentprov** job (P-2); a tool job
can only be killed. The harness tried `jobs start -- jobs follow <sleeper>` as a long-running agentprov job, which the
jobs manager rightly refuses (`jobs.argv.recursive`: a job does not start jobs). Without the backend (step 7) there is
no offline agentprov command that runs long enough to stop. The control-file path itself is covered by
`tests/jobs/test_jobs_windows_paths.py`.

## Decisions (the user, 2026-10-28; recorded on D-867)

1. **Steps 7–8 are not applicable on Windows ARM64 for v0.1.** Live runs need macOS or Linux; the guide must say so.
   The harness records 7 and 8 with `applicable: false` and the reason, and the run counts steps 1–6 and 9.
2. **Step 6 on Windows passes on `info` and `kill`.** The graceful stop stays covered by
   `tests/jobs/test_jobs_windows_paths.py`; the harness no longer tries a job that starts a job.

## The label

**Lifted for one artefact** (D-863 with D-867: steps 1–6 and 9 passed on a run from main, 2026-10-28):

| | |
|---|---|
| Package | `AgentPROV-windows-arm64.zip`, `sha256:269a75f75315a8be223248d654755104d62023bc5b4482f7a4ddebe976dfbc08` |
| Built | from main `38729b27` by `driver.py build windows-arm64` in a clean Windows 11 ARM64 VM (CPython 3.14.8, 89.9 MB, unsigned) |
| Tested | run `windows-arm64-20261028T113033Z`, level W, checkout `38729b27`: steps 1–6 and 9 pass, 7–8 not applicable; the window "AgentPROV — mini" shows "3 executions" |

The label stays on Windows bundles built any other way, on Windows x86_64 (not run), and on Windows versions other than
Windows 11 ARM64 26H2 (10.0.26300). Live runs remain unavailable on Windows ARM64 in v0.1.

Proposed wording for the guide's Windows ARM64 row, for the orchestrator to place: "Windows ARM64: one folder (zip),
unsigned (SmartScreen: More info, then Run anyway); **tested on a clean Windows 11 ARM64 machine** (G5 clean-machine run
from main, package sha256 `269a75f7…bc08`). Live runs (`agentprov run`) are not available on Windows ARM64 in v0.1: the
AgentDojo backend cannot be installed there; use macOS or Linux."
