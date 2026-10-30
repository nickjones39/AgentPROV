# G5 clean-machine test: Linux x86_64 (under emulation)

Status (2026-10-29): **all nine steps pass from main, under emulation.** The bundle built from main `0c87b657` in a
clean Ubuntu 22.04 x86_64 guest passed steps 1–9 in a second clean guest (run `linux-x86_64-20261028T135035Z`). The Mac
Studio has no x86_64 hardware, so QEMU emulates the whole machine (the user's choice, 2026-10-29). The label is lifted
for that one package, **with the wording "tested under emulation"** (below). The branch run is kept below.

## Setup

| Item | Value |
|---|---|
| Tool | Lima 2.2.1 with `vmType: qemu`, QEMU 11.1.2 and `lima-additional-guestagents` 2.2.1 (installed with the user's yes); plain mode, no mounts, no port forwards, no host SSH keys |
| Image | `ubuntu-22.04-server-cloudimg-amd64.img`, release-20261020, `sha256:2099e63d…488b` (Ubuntu's published SHA256SUMS) |
| Guest | Ubuntu 22.04.5 LTS, kernel 5.15.0-198, glibc 2.35 (the x86_64 floor), `x86_64` (emulated), 8 CPUs, 12 GiB |
| Base packages | the same prerequisite and harness lists as Linux arm64 (`pins.toml`) |
| Bundle | `AgentPROV-linux-x86_64.tar.gz`, `sha256:fefde06b1d99782bd01555fccf5e2fbfa2ac5cf27bb0fb65cd4db6953c10d88c`, 181.8 MB unpacked, an x86-64 ELF, CPython 3.14.8, needs glibc 2.35; built in a fresh clone of the base from commit `0e48166a` with `build_bundle.py --glibc-floor 2.35` |

## Run `linux-x86_64-20261028T120312Z`

| Step | Result |
|---|---|
| 1 `--smoke` | pass |
| 2 `xcb` window, mini corpus | pass: no missing libraries; the Viewer and the status bar show 3 executions |
| 3 `--preview-helper` | pass |
| 4 `uv sync --locked` (core, gui), `agentprov info` | pass; CPython 3.14.8 |
| 5 `keys`: no Secret Service, then gnome-keyring | pass |
| 6 `jobs`: info, stop, kill | pass |
| 7 `backends build agentdojo` | pass: marker complete, sandbox probe `not_applicable` |
| 8 scripted dev run, `validate` | pass |
| 9 Run Live containment (P-4) | pass: `dedicated-user`, `vm` |

The whole job (base, emulated build and level-W run) took about 25 minutes on the Mac Studio, much less than the
1–3 h estimated in the design note. The bundle's bytes do not depend on emulation; only the timings do.

## The label

**Lifted for one artefact, under emulation** (D-863: every step passed on a run from main, 2026-10-29):

| | |
|---|---|
| Package | `AgentPROV-linux-x86_64.tar.gz`, `sha256:8e57c020e103567a9984f47d58fcdc10af60f2e3c8d2a8dd6c56c1329bf0de29` |
| Built | from main `0c87b657` by `driver.py build linux-x86_64` in a clean Ubuntu 22.04 x86_64 guest under QEMU (CPython 3.14.8, an x86-64 ELF, needs glibc 2.35, 181.8 MB) |
| Tested | run `linux-x86_64-20261028T135035Z`, level W, checkout `0c87b657`: steps 1–9 pass |

It stays on Linux x86_64 bundles built any other way (for example by `bundles.yml`), and native x86_64 hardware is not
covered. Proposed wording for the guide's Linux x86_64 row, for the orchestrator to place: "Linux x86_64: `.tar.gz`
built in a clean Ubuntu 22.04 VM; **tested on a clean Ubuntu 22.04 x86_64 machine under emulation** (QEMU on Apple
silicon; package sha256 `8e57c020…de29`); needs glibc 2.35 or newer and the same X11 libraries as aarch64."
