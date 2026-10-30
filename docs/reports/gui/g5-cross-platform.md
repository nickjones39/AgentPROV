# G5 cross-platform bundles: macOS, Windows and Linux (design note)

Status: **decided, 2026-10-22 (D-750).** The user decided that v0.1's G5 ships desktop bundles for macOS, Windows
and Linux, built on the hosts below and released **untested** off macOS (relayed by the orchestrator). Nothing here has
been downloaded, built or run on Windows or Linux. Every download it lists needs the user's typed yes first.

## Decisions (D-750, user, 2026-10-22)

- **Targets:** macOS arm64 only (no Intel Macs), on this Mac. Linux x86_64 (`ubuntu-22.04`), Linux aarch64
  (`ubuntu-24.04-arm`) and Windows x86_64 (`windows-latest`) on GitHub runners through `.github/workflows/bundles.yml`
  (manual dispatch only). Windows ARM64 later, if a Windows ARM runner is available to the repository and PySide6
  publishes `win_arm64` wheels (both checked later with a yes); meanwhile the x86_64 bundle runs under emulation.
- **No dispatch** while private-repository Actions billing fails: the builds start once the repository is public or
  the user fixes billing.
- **Released untested:** a build proves the build-time checks of §2.7 plus an automated `--smoke` start of the GUI and
  of the preview helper (the bundle's only helper: keys run through the checkout's CLI, D-702). Every non-macOS bundle
  is labelled "not tested on a clean machine" in the release notes and the guide. Windows is unsigned; Linux ships a
  `.tar.gz`.
- **Now:** P-3, P-4, P-7 (§5). **Deferred to the Mac Studio:** P-1, P-2, P-5, P-6, the UTM VMs and the two-level
  clean-machine test of §3, which removes the "untested" label. A first implementation of P-1, P-2, P-5 and P-6 is
  held on branch `gui-g5-held` (tested, not for merge).
- **The user's own:** the Windows licence, the VM product question (UTM is not among the products Microsoft names for
  Windows 11 ARM on Apple silicon, as far as I know), and publishing the repository or fixing billing.
- **Containment record:** a declared containment is recorded as `producer.sandbox = {"kind": "dedicated_user" | "vm",
  "declared_by": "operator"}` with no profile digest, against `{"kind": "sandbox_exec", "declared_by": "probe",
  "profile_sha256": …}` for the probed one (HL H.2.7). Nothing reads it as enforced; no recorded format changes.

**PyPI facts (read-only lookup with the user's yes, 2026-10-22).** PySide6 6.12.1 is not published; the newest is
6.12.0, so the pending bump waits. Its wheels are tagged `macosx_14_0_universal2`, `manylinux_2_34_x86_64`,
`manylinux_2_39_aarch64`, `win_amd64` and `win_arm64`. So the Linux floors are glibc 2.34 (x86_64; `ubuntu-22.04`'s
2.35 meets it) and 2.39 (aarch64; `ubuntu-24.04-arm` meets it, `ubuntu-22.04-arm` would not), and Windows ARM64 wheels
exist: what remains of that check is whether a Windows ARM runner is available to the repository. The tags are those
of the `PySide6` release; `pyside6-essentials` is released with it.

## 0. What a bundle is (unchanged by this note)

- **One-folder PyInstaller builds of the GUI** (design §13). A frozen bundle contains the GUI and the core library
  **for reading**. Without a configured checkout the GUI is viewer-only.
- **Writes and runs go through a checkout's CLI** (D-391/D-392: the GUI is a CLI client; D-700 is the reverse CLI-parity rule). The checkout runs from its own
  `.venv` (`Scripts\agentprov.exe` on Windows, `bin/agentprov` elsewhere) or through `uv run --locked --project`.
- **"Starts on a clean machine" therefore has two levels.**
  - **V (viewer):** the bundle alone opens a corpus.
  - **W (writes):** a checkout is also present, with its own downloads (uv, Python 3.14, the locked dependencies; for
    live runs, a backend environment on Python 3.12).

## 1. Targets and build hosts

PyInstaller does not cross-build: each bundle is built on its own OS and architecture.

| Target | v0.1 | Minimum OS (to confirm at build time from the wheel tags) | Recommended build host |
|---|---|---|---|
| macOS arm64 | **yes** | macOS 15: the bundle's `Info.plist` declares `LSMinimumSystemVersion` 15.0 (the spec) | this M2 Max (done today; D-657 ad hoc signing) |
| macOS x86_64 / universal2 | no (proposed) | — | would need an x86_64 or universal2 Python; Intel Macs are not a stated target |
| Windows x86_64 | **yes** | Windows 10 (22H2) or 11 x64; Python 3.14 and Qt 6 both need 10 or later | GitHub `windows-latest`, once the repository is public |
| Windows ARM64 | later (proposed) | Windows 11 ARM64 | depends on PySide6 `win_arm64` wheels (unverified; read-only PyPI check needs a yes). Meanwhile the x86_64 bundle runs under Windows 11's x64 emulation |
| Linux x86_64 | **yes** | glibc of the build image: build on Ubuntu 22.04 for a glibc 2.35 floor. PySide6 wheels need manylinux_2_28 (glibc 2.28) at least | GitHub `ubuntu-22.04`, once public |
| Linux aarch64 | **yes** | the glibc of `ubuntu-24.04-arm` (2.39) unless the declared floor is met by an older image | GitHub `ubuntu-24.04-arm` (D-750); a UTM VM later on the Mac Studio |

**The three routes compared.**
- **(a) Local VMs on this M2 Max (UTM).**
  - **ARM guests (Linux aarch64, Windows 11 ARM64)** run virtualised at near-native speed. 32 GB RAM allows one 8 GB
    guest beside the round. Building them is feasible.
  - **x86_64 guests are emulated (QEMU without hardware help).** That is many times slower than native: a PySide6
    install and a PyInstaller build would take hours, and the GUI start is not a meaningful timing. Not recommended for
    building. Usable at most for one slow "does it start" check.
  - **Windows 11 ARM licence.** Microsoft names specific virtualisation products as supported for Windows 11 ARM on
    Apple silicon; UTM is not among them as far as I know. A Windows licence is needed in any case. **The user decides
    this; the note proposes no way around it.**
- **(b) GitHub Actions.**
  - Standard hosted runners are free for public repositories: `ubuntu-22.04`, `ubuntu-22.04-arm`/`ubuntu-24.04-arm`,
    `windows-latest` and `macos-latest` (arm64).
  - Private-repo runs are blocked: the account's Actions billing is failing (D-431 note, 2026-10-22). If billing is
    fixed instead of publishing, private runs cost minutes, with Windows billed at a multiple of Linux.
  - The core `ci.yml` matrix already names `ubuntu-latest`, `ubuntu-24.04-arm`, `macos-latest` and `windows-latest`.
    It has no GUI job, and whether its Windows and Linux legs pass on current main is unknown: no run since billing
    failed. A `gui-bundle` workflow (manual dispatch) would be new.
- **(c) Another machine.** A Windows x86_64 PC or a Linux x86_64 box the user owns builds natively at full speed, with
  no emulation and no licence question beyond the machine's own. If one is available, it is the fastest route to
  Windows x86_64 before the repository is public.

**Recommendation** (as proposed; D-750 chose GitHub runners for every non-macOS target):
- **macOS arm64:** this Mac.
- **Linux aarch64:** a local UTM Ubuntu 22.04 ARM VM, after the round. It is the only non-macOS target buildable
  before the repository is public without new hardware.
- **Linux x86_64:** GitHub `ubuntu-22.04` after publication, or (c).
- **Windows x86_64:** GitHub `windows-latest` after publication, or (c). If the user licenses Windows 11 ARM in a
  supported VM, the x86_64 bundle can be smoke-tested there under emulation, but not built for release.
- **Windows ARM64:** later, after the wheel check.

## 2. Platform differences the bundles must handle

### 2.1 The native chrome (PyObjC)
- `platform/macos.py` (D-440, D-449) is used only when `sys.platform == "darwin"` and Qt's `cocoa` plugin is active.
  The PyObjC dependencies carry `sys_platform == 'darwin'` markers, so they are absent elsewhere.
- **Windows and Linux show the Qt chrome:** a Qt toolbar, menu bar, sidebar and Qt dialogs. Settings › Experimental's
  "Native macOS toolbar" is excluded from parity (D-700) and should be hidden off macOS (P-6).
- **Linux Wayland versus X11:** Qt picks `wayland` or `xcb`. The bundle must ship both platform plugins and the `xcb`
  plugin's system dependencies (`libxcb-cursor0` on Ubuntu) are documented as a prerequisite, not bundled.

### 2.2 Keys (keyring, D-702, D-655)
- The helper allows exactly one backend per OS: macOS Keychain; Windows Credential Manager (`WinVaultKeyring`); Linux
  Secret Service, then KWallet (`keys/helper.py ALLOWED`).
- **Windows and Linux dependencies are already locked:** keyring's `pywin32-ctypes` (Windows) and `secretstorage`
  plus `jeepney` (Linux) are in both `uv.lock` files under their `sys_platform` markers.
- **Linux without a Secret Service** (headless, a minimal desktop, no gnome-keyring or KWallet daemon, or a locked
  collection): `backend()` finds nothing, `keys status` reports `allowed: false`, Settings › Keys disables Store, and
  `run --keychain` refuses. The fallback is the user's key order (keychain first, then `.env`) and `--env-file` or
  `--env-stdin`.
  - **P-1:** a clear message names the missing service and the fallback (it is generic today).
  - **KWallet:** keyring's KWallet backend needs `dbus-python`, which is not a keyring dependency and is not in the lock,
    so KWallet is effectively unavailable. P-1 either documents that or drops it from `ALLOWED`.

### 2.3 Live-run containment (AD-13(b), G.4.10)
- `sandbox-exec` exists only on macOS. Elsewhere the feasibility probe records `not_applicable` and
  `--containment sandbox-exec` is refused.
- On Linux and Windows a real-model run needs `--containment dedicated-user` or `vm`, which are **operator
  declarations**: AgentPROV records them (`declared_by: operator`) and enforces nothing.
- No enforced containment exists off macOS in v0.1. Linux namespaces, bubblewrap or a Windows AppContainer would be
  new security work; they are not proposed here.
- **Today Run Live offers `sandbox-exec` on every OS** and the CLI refuses it later. **P-4:** offer only
  `dedicated-user` and `vm` off macOS, with a line saying they are the operator's declarations and enforce nothing.
  The scripted transport needs no containment and is unaffected.

### 2.4 Jobs, the supervisor and the preview helper
- **Detaching** (D-704): POSIX `start_new_session`; Windows `DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP |
  CREATE_BREAKAWAY_FROM_JOB`.
  - Breakaway fails with "access denied" when the parent runs inside a job object that forbids it. Some terminals and
    CI runners do that. **P-2:** retry without `CREATE_BREAKAWAY_FROM_JOB`, recording it in `job.json`.
- **Stop:** POSIX sends one SIGTERM. Windows has no SIGTERM delivery: `os.kill(pid, SIGTERM)` there is
  TerminateProcess. So on Windows a graceful stop exists only through the D-394 control file (`--with-control-file`),
  and `jobs stop` without one is refused ("not done").
  - **P-2:** the GUI passes `--with-control-file` for every job on Windows, so Stop is always the graceful one.
  - The supervisor's SIGTERM handler is inert on Windows; it is harmless.
- **Kill:** psutil's process tree, then `proc.kill()` (TerminateProcess); POSIX also kills process groups. P-2 adds a
  Windows unit test with fake psutil processes.
- **Identity:** `(pid, create_time)` through psutil, the same on every OS. The PID ceiling is already per OS.
- **The preview helper:** `python -I -m agentprov_gui.preview` runs at `BELOW_NORMAL_PRIORITY_CLASS` on Windows (psutil)
  and `nice(10)` elsewhere. It exits on EOF of its stdin. Windows has no SIGPIPE, so EOF is the only signal, which is
  what it uses. In a frozen bundle it is the bundle executable with `--preview-helper` (already smoke-tested on macOS).
- **Graphviz `dot`:** the GUI kills its process group on POSIX and the process on Windows. `dot` comes from winget or
  apt and is not bundled (EPL-1.0).

### 2.5 Paths and AGENTPROV_HOME
- `AGENTPROV_HOME` defaults to `~/.agentprov` on every OS (`Path.home()`, so `C:\Users\<name>\.agentprov` on
  Windows). That is consistent but not the Windows convention (`%LOCALAPPDATA%`). **Proposal: keep `~/.agentprov`** for
  v0.1, because a single documented location matters more and changing it touches every runbook.
- **Windows path length:** corpora nest deeply (`<corpus>/aer/…`, raw store fan-out, staging). Paths over 260
  characters fail unless long paths are enabled. **P-5:** a start-up check that warns when
  `LongPathsEnabled` is off. Enabling it is the user's own system setting; the GUI never changes it.
- Atomic writes use `os.replace`; locks are in `io/locks.py`. Both already have Windows paths
  (`ci.yml`'s Windows leg exists for this), not yet re-checked on current main.

### 2.6 The job queue (`tools/suite_queue.py`)
- It imports `fcntl` at module level, so on Windows any queued job (`jobs start --queue-cpu`, dev runs, the GUI's
  "Run heavy jobs through the queue", on by default) **fails at start**.
- The queue is a development tool of this checkout (shared-machine scheduling), not a product feature.
- **P-3:** one helper decides "queue available" (POSIX and the tool present). `jobs start --queue-cpu` refuses with
  a clear reason on Windows (exit 4, `jobs.queue.unavailable`), and `devrun` and the GUI do not queue there.
  Compute's queue rows say why they are off. Porting the queue to `msvcrt` locking is not proposed for v0.1.

### 2.7 `build_bundle.py` per OS
| Check | macOS | Windows | Linux |
|---|---|---|---|
| Layout | `AgentPROV.app` | `AgentPROV\AgentPROV.exe` + `_internal\` | `AgentPROV/AgentPROV` + `_internal/` |
| Excluded Qt modules | frameworks + `.so` | `Qt6*.dll`, `.pyd` | `libQt6*.so*`, `.so` |
| LGPL texts + `THIRD_PARTY_NOTICES.md` | `Contents/Resources` | `_internal` | `_internal` |
| Qt dynamic (relinkable) | frameworks are files | `Qt6*.dll` are files | `libQt6*.so.6` are files |
| SDK / ABI floor | `LC_BUILD_VERSION` (D-441) | PE subsystem version (report only) | highest `GLIBC_x.y` symbol needed (report; fail above the declared floor) |
| Signature | ad hoc (D-657) | **unsigned** (design §13's Authenticode needs a certificate that is not bought: proposal amends it) | none (tarball checksum) |
| Package | the `.app` (zip for transfer) | zip of the folder; Inno Setup installer later | `.tar.gz` of the folder; AppImage later |
| Smoke | `--smoke` offscreen, `--preview-helper` EOF | same | same, plus `xcb` plugin present |

- **P-7** makes these per-OS checks unit-testable on any host: each check takes the layout and a file tree, and the
  tests use fixture trees (fake `Qt6WebEngineCore.dll`, a missing `LGPL-3.0.txt`, a `.so` with too new a glibc symbol
  in a fake symbol table).
- **Windows unsigned:** SmartScreen shows "Windows protected your PC" for an unsigned download. The user clicks
  "More info", then "Run anyway", once. The release notes and the README say so, as D-657 does for Gatekeeper.
- **Linux tarball before AppImage:** an AppImage needs `appimagetool` (a download) and FUSE on the target
  (`libfuse2`, absent by default on newer Ubuntu). A tarball needs neither. Proposal: tarball for v0.1, AppImage
  optional later.

## 3. Test plan: "starts on a clean machine"

"Clean" means a fresh OS image with only the stated prerequisites. Each OS runs the steps below in order and records
results in `bundle-report.json` next to the bundle (the file `build_bundle.py` writes).

| # | Step | Level | Pass |
|---|---|---|---|
| 1 | `AgentPROV --smoke` (offscreen) | V | exit 0 |
| 2 | Start with the real platform plugin (cocoa / windows / xcb or wayland); open a small corpus copied onto the machine (the GUI tests' three-execution mini corpus; no corpus is bundled) | V | window shows; the Viewer lists 3 executions |
| 3 | `--preview-helper` with stdin closed | V | exits 0 within 5 s |
| 4 | Install uv; clone the checkout; `uv sync --locked` (core + gui) | W | `agentprov info` runs |
| 5 | `agentprov keys status`, then `keys set`/`delete` of a dummy test variable name (never a real key) | W | allowed on macOS and Windows; on Linux with Secret Service; on Linux without one, the P-1 message |
| 6 | `agentprov jobs start -- info`; `jobs stop` with a control file; `jobs kill --yes` of a sleeping tool job | W | `ended.json`: `exited`, `stopped`, `killed` |
| 7 | Build one backend env (`agentprov backends build agentdojo`, offline after its downloads) | W | marker written; sandbox probe `passed` on macOS, `not_applicable` elsewhere |
| 8 | One scripted dev run: Runs › Live Dev Run with the scripted transport (`--llm-script`, no model call, no key) | W | a working corpus that `validate` passes; no network beyond step 4/7's downloads |
| 9 | Run Live with a real-model transport selected | W | the containment list matches §2.3 (P-4); nothing is started |

Notes:
- **Step 8** replaces the import-based dev run. That one reads the fetch cache (R2) and would need upstream downloads
  per OS.
- **Steps 1–3** need only the bundle. Steps 4–9 need the checkout and are where Windows and Linux differences show.
- The GUI's offscreen test suite (`uv run --project gui pytest`) should also run once per OS, in its own job. CI has
  no GUI job today.

## 4. Downloads and costs (each needs the user's typed yes)

| Item | For | Size (approx.) | Licence or cost note |
|---|---|---|---|
| UTM | local ARM VMs | ~ 0.3 GB | Apache-2.0; free |
| Ubuntu 22.04 LTS ARM64 server or desktop image | Linux aarch64 VM | 1–4 GB | free |
| Windows 11 ARM64 image | Windows ARM VM (optional) | ~ 10 GB | **needs a Windows licence; the supported-VM question for UTM is the user's to settle** |
| uv (installer) | every OS | ~ 30 MB | MIT/Apache-2.0 |
| CPython 3.14 (uv's python-build-standalone) | every OS | ~ 40 MB each | PSF |
| CPython 3.12 (backend env) | live runs | ~ 40 MB each | PSF |
| Core + GUI locked dependencies (PySide6 ~ 0.4–0.6 GB per OS, PyInstaller, psutil, keyring, …) | every OS | ~ 0.7 GB per OS | PySide6/Qt LGPLv3 (notices shipped); PyInstaller GPL with bootloader exception |
| AgentDojo backend env (agentdojo 0.1.35 + deps) | step 7–8 | ~ 0.3 GB | MIT |
| PySide6 6.12.1 check (read-only PyPI lookup) | the pending bump | — | then the bump itself is another download |
| Graphviz (`dot`) | graph layout, optional | 50–100 MB | EPL-1.0; system package, not bundled |
| `appimagetool`, Inno Setup | later packaging only | small | not needed for v0.1 as proposed |
| GitHub Actions minutes | after publication: free | — | private: billing must be fixed; Windows minutes cost a multiple |

**The user's own steps:**
- making the repository public (CLAUDE.md: never without instruction), or fixing Actions billing;
- any Windows licence;
- approving UTM and images;
- on Windows, enabling long paths if wanted (P-5 only warns);
- on Linux, installing a Secret Service if keychain storage is wanted.

## 5. Order and effort

**Now, during the round** (light, class 0, targeted tests at `-n 2` one at a time; branch from the train base, not
`gui-train3`):
- P-1 keyring backend detection and the Linux message (0.5 day)
- P-2 Windows jobs: control file by default, breakaway fallback, kill tests (0.5–1 day)
- P-3 queue availability helper; refuse `--queue-cpu` on Windows (0.5 day)
- P-4 Run Live containment list per OS (0.25 day)
- P-5 Windows long-path warning (0.25 day)
- P-6 hide the native-toolbar setting off macOS (small)
- P-7 per-OS `build_bundle.py` checks, unit-tested with fixture trees (1 day)

Then the PySide6 6.12.1 lookup, with a yes.

**After the round, before publication** (needs yeses):
- UTM plus the Ubuntu ARM image: build and test Linux aarch64 (steps 1–9), about 1 day.
- The macOS rebuild after train 3 and the Viewer land (the orchestrator's signal).

**After publication** (or with fixed billing, or machine (c)):
- a `gui-bundle` manual-dispatch workflow for `windows-latest`, `ubuntu-22.04` and `ubuntu-22.04-arm`, uploading
  artefacts; steps 1–3 in the workflow, steps 4–9 once per OS by hand or in a second job (1–2 days);
- the first Windows run will surface the unknowns: the core's Windows leg on current main, path lengths, breakaway.

**Effort total:** about 3–4 days of build work plus first-run fixes per new OS. Windows is the largest unknown.
