# G5 clean-machine tests on the Mac Studio: automated VMs (design note)

Status: **approved by the user, 2026-10-28, as proposed (D-860..D-867), including the per-run clone deletion of §3.** Nothing
has been downloaded or installed. Each download in §6 needs its own typed yes.

Goal (the user, 2026-10-28: "yes we can do this automated"): remove the "not tested on a clean machine" label of the
G5 bundles with one command per platform that creates a fresh VM from a pinned image, runs the test plan of
`g5-cross-platform.md` §3, collects the results and a screenshot, and destroys the VM.

## 0. Scope change: no macOS VMs (the user, 2026-10-28)

The user, relayed by the orchestrator: "we do not need to test macos since we are doing that with this machine, just
test for linux and windows".
- **Dropped:** the macOS target. No Tart, no macOS image downloads (§6 rows 5–7) and no macOS clean-machine run. §5's
  macOS part (D-866) and Tart's row in §1 stay below only as the record of what was approved first.
- **The macOS bundle's evidence** is this Mac Studio's own runs: `build_bundle.py`'s checks and `--smoke` start, plus a
  start with the real `cocoa` platform plugin that opens the mini corpus.
- **Still in scope:** Linux arm64; Linux x86_64 while it stays practical under emulation; Windows 11 ARM64.
- **Not tested here any more:** the first launch of the ad hoc signed `.app` on another Mac. §5 expected that macOS 15
  and later no longer let Control-click › Open bypass Gatekeeper, which would make D-657's "right-click › Open" wording
  out of date. That point goes to the orchestrator as an open question; it is not verified.

## 1. Tools (D-860)

| Platform | Tool, version | Guests | Why |
|---|---|---|---|
| macOS arm64 | **Tart 2.41.1** (Apple Virtualization framework; headless; SSH) | macOS 27.0 (this Mac's major) and macOS 15.7.7 (the bundle's `LSMinimumSystemVersion` 15.0) | prebuilt vanilla images pinned by OCI digest; clones are APFS copy-on-write, so a fresh VM takes seconds |
| Linux arm64 | **Lima 2.2.1** (`vz` backend) | Ubuntu 24.04 cloud image (glibc 2.39) | images pinned by sha256 in Lima's own templates; cloud-init; also **builds** the Linux arm64 bundle natively |
| Linux x86_64 | Lima 2.2.1 with **QEMU** (emulated, no hardware help) | Ubuntu 22.04 amd64 cloud image (glibc 2.35) | the only way to reach x86_64 on Apple silicon; slow, so steps 1–3 only, plus a one-off bundle build |
| Windows 11 ARM64 | **UTM 5.0.8** (QEMU backend) + `utmctl` | Windows 11 ARM64 26H2 from the user's ISO, unattended | builds the `win_arm64` bundle inside (PySide6 6.12.0 publishes `win_arm64` wheels, PyPI check of 2026-10-22) |

**Facts found while checking (data, to confirm at download):**
- **Tart has moved and relicensed.** The repository is now `openai/tart` (GitHub redirects from `cirruslabs/tart`);
  the current tap is `openai/tools/tart` (2.41.1). The old `cirruslabs/cli` tap is stale at 2.32.1, so it is not used.
  The licence changed on 2026-06-05 from the Fair Source licence (a 100-core cap for organisations) to
  **FSL-1.1-ALv2**: any use except a "Competing Use" (offering Tart, or something like it, as a commercial product) is
  allowed, and the licence lists internal use and **non-commercial research** as permitted. Each release turns into
  Apache-2.0 two years after it is published. This project's use is non-commercial research. The images are still
  published as `ghcr.io/cirruslabs/macos-*-vanilla`.
- **Apple's macOS licence** allows up to two extra macOS instances in VMs on Apple hardware the user owns, so the driver
  never runs more than two macOS guests at once.
- **Windows 11 ARM in UTM:** Microsoft names Parallels Desktop as the authorised way to run Windows 11 on Apple
  silicon; UTM is not named. The licence and the choice of VM product stay **the user's** (D-750). This note proposes
  UTM because it is free and scriptable, and does nothing on Windows until the user decides.

**Rejected:**
- Tart for Linux as well. It cannot run x86_64 guests, and Lima pins the Ubuntu images by digest in its own templates.
- UTM for macOS and Linux. Tart and Lima are command-line first, with clone and delete commands and no GUI state to
  manage.
- Parallels for Windows: paid, and `prlctl` would need a licence of its own. It is the user's alternative if they want
  the Microsoft-authorised product, and the driver keeps the Windows platform behind one interface, so it could be added.
- GitHub runners: billing still fails (D-431), and runners cannot answer the clean-machine question for macOS.

## 2. Pins and layout (D-861)

Everything lives in `gui/tools/clean_machine/`:
- `pins.toml`: every image by digest, plus the tool versions it was tested with.
- `driver.py`: one subcommand per platform.
- `guest/`: the scripts each guest runs (POSIX shell for macOS and Linux, PowerShell for Windows), and the Windows
  `autounattend.xml` template.

VMs, base images, caches and results live under `~/.agentprov/vms/`, never in Git.

| Pin | Value |
|---|---|
| macOS 27.0 | `ghcr.io/cirruslabs/macos-golden-gate-vanilla@sha256:b78a521145ebef24e9916c0b3999e165bb12b587d11524c5fa3ba4fe7bf79bb9` (30.9 GB download, 35.7 GB disk, uploaded 2026-09-21) |
| macOS 15.7.7 | `ghcr.io/cirruslabs/macos-sequoia-vanilla@sha256:57a83b1b52f928f5b11b0963927178fd6c4cac52c315279f227c27cc5ab81587` (23.7 GB download, 50 GB disk) |
| Ubuntu 24.04 arm64 | `noble/release-20260926/ubuntu-24.04-server-cloudimg-arm64.img`, `sha256:1d6bffe6…cefc55` (620 MB) |
| Ubuntu 22.04 amd64 | `jammy/release-20260926/ubuntu-22.04-server-cloudimg-amd64.img`, `sha256:0c9811a8…b210e` (736 MB) |
| Windows 11 ARM64 | the ISO the user downloads; its sha256 is recorded at first use and checked against Microsoft's published hash for the chosen language |
| UTM guest tools | `utm-guest-tools-0.1.271.iso` (127 MB; virtio drivers for ARM64 and the SPICE agent) |

macOS 26 (Tahoe, 24 GB) is left out, because 15 and 27 bracket it. It can be added by one line in `pins.toml`.

## 3. Lifecycle, levels and results (D-862, D-863)

`uv run --project gui python gui/tools/clean_machine/driver.py {linux-arm64|linux-x86_64|macos-27|macos-15|windows}
--bundle PATH [--level V|W] [--checkout REF]` runs one fixed sequence:

1. **Create** a VM named `agentprov-g5-<platform>-<UTC time>` from a local base, which is the pinned image plus its
   recorded one-time preparation (§5). Each VM gets 4 CPUs and 8 GB of RAM (Linux) or 6 CPUs and 12 GB (macOS,
   Windows).
2. **Copy in** the bundle, the three-execution mini corpus (built with the GUI tests' own `seal_support` helper, never
   a real corpus) and, for level W, a `git archive` of the checkout at `--checkout` (default `HEAD`). No `.env`, no key
   and no host directory is mounted into the guest. Files go in by `scp`/`limactl copy` only.
3. **Run** the §3 steps in the guest. Each step writes one JSON line with its number, level, exit code, pass/fail,
   duration, and evidence (the last 2 KB of stderr, `ended.json` states, the probe verdict, the `validate` exit).
4. **Collect** the step lines, the screenshot (PNG), the guest's OS version and build, and the bundle's sha256.
5. **Destroy** the VM, even on failure or Ctrl-C (`finally`), and only after the results are copied out.
   **This deletes the per-run clone the driver itself created**, identified by the name prefix and a marker file the
   driver writes into it. It never deletes a base image, a pulled image or a cache. Those follow the project rule:
   list, ask, move to the Trash. `--keep` leaves the clone for inspection. *This needs the user's yes, because the
   project rule otherwise forbids deleting.* The user approved it on 2026-10-28.

**Results:**
- `bundle-report.json` gains a `clean_machine` list: one entry per platform run, with the step lines, the image digest,
  the tool versions and the run's UTC time.
- Screenshots and full logs go to `~/.agentprov/vms/results/<run>/`.
- A short report per platform goes in `docs/reports/gui/g5-clean-machine/<platform>.md` (no images, no account
  paths).
- **A platform loses its "untested" label only when all of its applicable §3 steps pass on a run from main.**

**Machine load:** each run goes through `tools/suite_queue.py` with its VM's CPU count, so it waits behind the wave-2
imports instead of competing with them. At most one Windows VM, two macOS VMs and two Linux VMs run at once.

## 4. Step 2, the one GUI-level check (D-864)

Step 2 ("window shows; the Viewer lists 3 executions") cannot be read from outside the GUI without accessibility
permissions on every OS. Proposal: a test-only flag `--probe-report FILE` in `gui/src/agentprov_gui/app.py`. It opens
the given corpus with the real platform plugin, waits for the executions table to load (at most 60 s), then writes
`{"platform_plugin": …, "window_visible": …, "executions": N}` and quits. It reads nothing else and writes only `FILE`.

The flag reads the Viewer's row count, which the GUI tabs work (`claude/gui-viewer-tabs-416834`, D-840..D-845) is
restructuring. So the flag is written **after the tabs land on main**. Until then, step 2 passes only partly: the
process stays up for 15 s, the guest's window list shows an AgentPROV window, and the user counts the rows on the
screenshot.

Screenshots:
- Linux: `xwd` under Xvfb.
- macOS: `screencapture` over SSH. This needs the Screen Recording permission for `sshd-keygen-wrapper`, which is one
  of the user's one-time prompts in the base image (§5).
- Windows: a PowerShell `CopyFromScreen`, run in the auto-logged-in session by a scheduled task.

## 5. Per platform (D-865, D-866, D-867)

### Linux (D-865), first

- **arm64:** Ubuntu 24.04 is the floor, because PySide6's `manylinux_2_39_aarch64` wheels need glibc 2.39. *The brief's
  "Ubuntu 22.04 (glibc 2.35 floor)" applies to x86_64 only:* a 22.04 arm64 guest cannot run any PySide6 6.12 build. It
  is not tested, and the guide states 24.04 (glibc 2.39) as the arm64 minimum.
- **Bundle:** the arm64 bundle is built in a 24.04 VM with `build_bundle.py --glibc-floor 2.39`. This replaces the
  GitHub `ubuntu-24.04-arm` leg for now.
- **Prerequisites:** the cloud image has no X libraries. The test installs only a recorded minimal set (Qt's `xcb`
  dependencies such as `libxcb-cursor0`, `libxkbcommon-x11-0`, `libegl1`, `libfontconfig1`, plus Xvfb and `x11-apps`
  for the screenshot). That set becomes the guide's prerequisite list. If the set is incomplete, step 2 fails, which is
  the point.
- **Base image:** one local base per image (cloud image plus the package set), so each run starts offline and in
  seconds. Lima 2's `limactl clone` makes the per-run copy.
- **Step 5 runs twice:**
  - with `gnome-keyring` under `dbus-run-session` and an unlocked test collection: allowed;
  - without a Secret Service: the P-1 message.
- **x86_64:** a Ubuntu 22.04 guest under QEMU emulation runs steps 1–3. It first builds the x86_64 bundle once
  (estimated 1–3 h, overnight, through the queue). The report says "built and tested under emulation". The bundle's
  bytes do not depend on emulation; only the timings do.

### macOS (D-866), dropped by the scope change of §0

- **Base image:** a local base per pin: the vanilla image plus one change, the Screen Recording grant for SSH
  screenshots, which the user clicks once in the VM window. The base is recorded in `pins.toml` as "vanilla plus
  TCC grant".
- **Quarantine:** the `.app` is copied in with `com.apple.quarantine` set (`0083;<time>;Safari;`), so Gatekeeper
  treats it as a downloaded app.
- **Gatekeeper is recorded automatically:**
  - `spctl --assess -vv`, expected `rejected` for an ad hoc signature;
  - a first `open` attempt, with the system-policy log line it produces.
- **Manual Gatekeeper check (once per macOS version and bundle):** on macOS 15 and later, Control-click › Open no longer
  bypasses Gatekeeper. The user must go to System Settings › Privacy & Security › **Open Anyway**. The user does this
  once in the VM window and the screenshot is kept. If it is confirmed, the D-657 wording ("right-click › Open") in the
  build log, the README and the guide is out of date, and a correction is routed through the orchestrator.
- **Automated runs:** after the spctl and first-`open` records, the automated runs remove the quarantine attribute and
  go on with steps 1–9.
- **Step 7:** the sandbox probe is expected to return `passed`.

### Windows (D-867), last

- **The user's part:**
  1. downloads the Windows 11 ARM64 ISO from Microsoft (26H2, their language);
  2. accepts Microsoft's licence;
  3. supplies a product key, or chooses to run unactivated within Microsoft's terms;
  4. decides the UTM-versus-Parallels question.
- **Unattended base install (about 45–60 min, once):**
  - The driver writes `autounattend.xml` onto a small ISO with `hdiutil makehybrid` (no download). It creates one local
    test account `agentprov` with a password the driver generates and keeps under `~/.agentprov/vms/windows/` (a test
    value for this VM only), auto-login and BypassNRO.
  - It loads the ARM64 virtio drivers from the guest-tools ISO in the windowsPE pass.
  - At first logon it installs the guest tools and enables OpenSSH Server. `Add-WindowsCapability` downloads that from
    Windows Update, inside the VM. It also installs the driver's public key.
  - `utmctl` then stops the VM, and this becomes the base. Each test run uses a `utmctl clone` of it.
- **LongPathsEnabled stays off** in the base, so P-5's warning is tested. One variant run turns it on to check that the
  warning disappears.
- **Steps 4–9:** run in the clone with uv, Python 3.14 (Windows aarch64) and Python 3.12 for the backend. The
  `win_arm64` bundle is built in the clone.
- **x86_64 bundle:** testing it under Windows' x64 emulation needs an x86_64 bundle, which only a runner or this guest
  under emulation can build. Optional, after arm64.

## 6. Downloads (each its own typed yes, in this order)

| # | Item | Size | Licence | For |
|---|---|---|---|---|
| 1 | Lima 2.2.1 (`brew install lima`) | ~ 30 MB | Apache-2.0 | Linux arm64 |
| 2 | Ubuntu 24.04 arm64 cloud image (fetched by Lima, digest-checked) | 620 MB | Ubuntu (free) | Linux arm64 |
| 3 | Guest packages for the Linux base (Xvfb, Qt `xcb` libraries, gnome-keyring), from Ubuntu's mirrors | ~ 0.2 GB | Ubuntu archive | Linux base |
| 4 | Level W inside the guest: uv, CPython 3.14 and 3.12, locked core and GUI dependencies, AgentDojo backend | ~ 1 GB per run | MIT/Apache, PSF, LGPLv3 (Qt), MIT | steps 4, 7 (one Linux run first; later runs again, because the guest is fresh) |
| 5 | Tart 2.41.1 + softnet (`brew install openai/tools/tart`) | ~ 25 MB | FSL-1.1-ALv2 (see §1) | macOS (dropped, §0) |
| 6 | macOS 27.0 vanilla image | 30.9 GB | Apple SLA (image by Cirrus Labs) | macOS (dropped, §0) |
| 7 | macOS 15.7.7 vanilla image | 23.7 GB | Apple SLA | macOS (dropped, §0) |
| 8 | QEMU (`brew install qemu`) and `lima-additional-guestagents` (Lima 2 ships non-native guest agents separately) | ~ 0.6 GB with dependencies | GPL-2.0, Apache-2.0 | Linux x86_64 only |
| 9 | Ubuntu 22.04 amd64 cloud image | 736 MB | Ubuntu | Linux x86_64 only |
| 10 | UTM 5.0.8 (`brew install --cask utm`, brings `utmctl`) | 304 MB | Apache-2.0 | Windows |
| 11 | UTM guest tools 0.1.271 ISO | 127 MB | mixed open source (virtio drivers, SPICE) | Windows |
| 12 | **The user's own:** Windows 11 ARM64 26H2 ISO from Microsoft | several GB (shown by Microsoft) | Microsoft licence, product key | Windows |

Disk: 1.7 TB is free; all images plus bases come to about 200 GB at most.

## 7. What the user does by hand

- The typed yeses for §6, and for the clone-deletion rule in §3.
- ~~macOS: once per pin, grant Screen Recording in the base VM's window, and click Open Anyway once per macOS version
  and bundle (about 2 min each).~~ Dropped (§0).
- Windows: §5's four items, then nothing until the screenshots.
- Look at each platform's screenshot and report.

## 8. Timing (estimates, to be replaced by measured values)

| Platform | One-time base | V run (steps 1–3) | W run (steps 1–9) |
|---|---|---|---|
| Linux arm64 | 10 min | 3 min | 20 min (mostly step 4's downloads) |
| Linux x86_64 (emulated) | 30 min + 1–3 h bundle build | 15–30 min | not run |
| ~~macOS 27 / 15~~ (dropped, §0) | — | — | — |
| Windows 11 ARM | 45–60 min unattended | 10 min | 40 min |

## 9. Order, and the P-fixes

1. Linux arm64: install Lima, build the base, run steps 1–3 against a bundle built in the VM; then level W.
2. ~~macOS: install Tart, pull the 27.0 image, run steps 1–3 against the MacBook bundle; then 15.7.7; then level
   W.~~ Dropped (§0): this Mac Studio's own `build_bundle.py` run and a real `cocoa` start are the macOS evidence.
3. **The P-fixes, ported from `gui-g5-held` (`7d151af0`) with tests, never merged.** The held branch predates P-3,
   P-4 and P-7 on main, so only these parts are ported:
   - P-1: `keys/__init__.py`, `cli/keys.py`, `live/keychain.py`, `ui/livepanes.py`;
   - P-2: `jobs/manager.py`, plus Windows job tests;
   - P-5: a new `platform/windows.py`, plus `ui/system.py`;
   - P-6: `ui/dialogs.py`.
   The tabs branch plans `ui/viewer.py`, `ui/mainwindow.py`, `ui/safe.py`, `gui/tools/screenshots.py` and chapter 8,
   so there is no overlap today. Its file list is re-checked before each edit. `app.py` (D-864) waits for the tabs to
   land.
4. Windows, once the user has done their four items.
5. Final runs on bundles rebuilt from main after the tabs and the P-fixes land. Then the label wording, through the
   orchestrator.

## Downstream effects

- Class 0 only: `gui/`, `gui/tools/`, docs, and `src/agentprov/{keys,cli,jobs}` (P-1, P-2), which are outside every
  stage digest as far as is known. D-451 widened the digests to each stage's import closure, so this is checked
  again before the port.
- No AER, PROV or corpus bytes change.
- No compat-gate impact.
- The D-657 Gatekeeper wording may need a correction (§5).
