# G5 clean-machine test: Linux arm64

Status (2026-10-28): **all nine steps pass from main.** The bundle built from main `18c71eb0` in a clean Ubuntu 24.04 arm64
VM passed steps 1–9 in a second clean VM (run `linux-arm64-20261028T095427Z`), so the label is lifted for that one
package (below). Earlier runs on the branch are kept in the tables.

## The "not tested on a clean machine" label

**Lifted for one artefact** (D-863: every applicable step passed on a run from main, 2026-10-28):

| | |
|---|---|
| Package | `AgentPROV-linux-aarch64.tar.gz`, `sha256:9cb011da3b47129a1bfffbaaca50890f849851be4022f0104bc6c58b625a85d7` |
| Built | from main `18c71eb0` by `driver.py build linux-arm64` in a clean Ubuntu 24.04 VM (CPython 3.14.8, needs glibc 2.38, 174.8 MB) |
| Tested | run `linux-arm64-20261028T095427Z`, level W, checkout `18c71eb0`: steps 1–9 pass; the screenshot shows the Viewer with 3 executions |

This package is the one to release for Linux aarch64 (the VM build stands in for the `ubuntu-24.04-arm` leg of
`bundles.yml`, D-865). The label stays on:
- Linux aarch64 bundles built any other way (for example by `bundles.yml`), which are other bytes;
- Linux x86_64 (not run);
- Windows (not run yet);
- distributions other than Ubuntu 24.04, and desktops other than X11 (Xvfb here; Wayland is not tested).

Proposed wording for the guide's platform table (`docs/user-guide/08-desktop-app.md`), for the orchestrator to place:
"Linux aarch64: `.tar.gz` built in a clean Ubuntu 24.04 VM; **tested on a clean Ubuntu 24.04 machine** (G5 clean-machine
run, package sha256 `9cb011da…85d7`); needs glibc 2.39 or newer and the X11 libraries `libxcb-cursor0 libxcb-icccm4
libxcb-keysyms1 libxkbcommon-x11-0 libegl1 libfontconfig1`. Linux x86_64: **not tested on a clean machine**."

## Setup

| Item | Value |
|---|---|
| Tool | Lima 2.2.1, `vz`, plain mode, no mounts, no port forwards, no host SSH keys (D-860, D-865) |
| Image | `ubuntu-24.04-server-cloudimg-arm64.img`, release-20260926, `sha256:1d6bffe6…cefc55` |
| Guest | Ubuntu 24.04.5 LTS, kernel 6.8.0-142-generic, glibc 2.39, 4 CPUs, 8 GiB |
| Base packages | the `prerequisites` and `harness` lists in `gui/tools/clean_machine/pins.toml`, versions in the base record |
| Bundle | `AgentPROV-linux-aarch64.tar.gz`, `sha256:d31dc443…9738`, 173 MB unpacked, built in a fresh clone of the base from commit `add78023` with uv 0.13.5 and `build_bundle.py --glibc-floor 2.39` (needs glibc 2.38) |
| Corpus | the GUI tests' three-execution mini corpus (`seal_support.working_corpus`) |

## Runs

| Run (UTC) | Step 1 `--smoke` | Step 2 window, 3 executions | Step 3 preview helper |
|---|---|---|---|
| 2026-10-28 04:07 | pass | **fail**: Qt's `xcb` plugin did not load | pass |
| 2026-10-28 05:22 | pass | pass: window found, no stderr, 3 executions on the screenshot | pass |
| 2026-10-28 05:52 | pass | pass: as above, on the CPython 3.14.8 bundle (`sha256:9b29fa16…6219`, commit `09b87d4d`) | pass |
| 2026-10-28 09:54 | pass | pass: the bundle from main (`sha256:9cb011da…85d7`, `18c71eb0`) | pass |

**The first step 2 failure** was a missing prerequisite, as D-865 intends a short list to show. `ldd` of
`libqxcb.so` found `libxcb-icccm.so.4` and `libxcb-keysyms.so.1` missing. Qt's own message named `libxcb-cursor0`,
which was installed, so the message misleads. The prerequisite list grew by `libxcb-icccm4` and `libxcb-keysyms1`, the
base was rebuilt, and the second run passed. The build's own smoke checks run offscreen, so they cannot catch this.

**The Linux prerequisites a desktop user needs** on top of a server install, for the guide:
`libxcb-cursor0 libxcb-icccm4 libxcb-keysyms1 libxkbcommon-x11-0 libegl1 libfontconfig1` and one font
(`fonts-dejavu-core`). A desktop Ubuntu install already has them.

Step 2's execution count is read from the screenshot until the `--probe-report` flag (D-864) is written: the status
bar reads "mini: 3 executions" and the Viewer lists three rows. Screenshots, step lines and each level-W command's
output are in `$AGENTPROV_HOME/vms/results/linux-arm64-<run>/`.

## Level W (steps 4–9)

Three runs, each from a fresh clone with the user's download yes (design §6 row 4). Each downloaded uv's CPython, the
locked core and GUI dependencies and the AgentDojo backend in the guest, and took under a minute in all.

| Step | 06:23 run (`c7a1a240`) | 07:13 run (`4bbb1a11`) | 09:54 run, main (`18c71eb0`) |
|---|---|---|---|
| 4 `uv sync --locked` (core, gui), `agentprov info` | pass | pass | pass |
| 5 `keys status`; `set`/`list`/`delete` of a dummy value | **fail** (harness) | pass | pass |
| 6 `jobs start -- info`, `jobs stop`, `jobs kill --yes` | pass | pass | pass |
| 7 `backends build agentdojo` | pass | pass | pass |
| 8 scripted dev run, then `validate` | pass | pass | pass |
| 9 Run Live containment off macOS (P-4) | pass | pass | pass |

- **Step 5** has two variants. Without a Secret Service, `keys status` exits 4 with `allowed: false` and the P-1
  reason ("there is no D-Bus session … keys then come from .env, --env-file or --env-stdin"). With gnome-keyring
  unlocked in `dbus-run-session`, status is `allowed: true` (backend `Keyring`); `set ANTHROPIC_API_KEY --stdin` of a
  fixed dummy text, `list` (stored), `delete --yes` and `list` (not stored) all exit 0. The first run's failure was the
  harness: it asked `keys list` for the names before any Secret Service existed, and `keys list` rightly refused.
- **Step 6** `ended.json`: `info` is `ok`/`waited`; the stopped sleeper is exit 130, `interrupted`/`waited` (on Linux a
  stop is one SIGTERM, G5 note §2.4; the control-file stop is Windows' path, P-2); the killed one is `killed`/`killed`.
  The sleeper (`tools/g5_sleeper.py`, the jobs tests' own) is written into the guest's copy of the checkout.
- **Step 7:** `agentdojo-db3901f1`, marker `complete`, sandbox probe `not_applicable`.
- **Step 8:** `run agentdojo --suite banking --user-tasks user_task_1 --benign only --llm-script` (the live tests'
  one-call scenario): 1 cell attempted, conclusive and derived; `validate` exits 0. Network is not blocked in the guest;
  the scripted transport makes no model call.
- **Step 9** reads `runspec.containment_choices()` from the checkout's GUI package: `dedicated-user` and `vm`, each
  labelled "declared by you, not enforced or checked by AgentPROV". It does not drive the Run Live dialog.

## Findings for the orchestrator: two unpinned interpreters (fixed on main)

- **Core environment:** CPython **3.14.9**. The root `.python-version` says `3.14`, so a clean machine takes the
  newest 3.14, not the 3.14.8 release floor.
- **AgentDojo backend:** built with Ubuntu's **system CPython 3.12.3**. `backends/agentdojo` has no `.python-version`,
  so `uv sync` takes an installed interpreter that satisfies `==3.12.*`; this Mac's environments use uv's 3.12.14. The
  marker records the version, so nothing is hidden, but the interpreter varies by machine.

Both are fixed on main by `00e3fbc9`'s train: the root `.python-version` is 3.14.8 and every backend project pins
3.12.14. `gui/.python-version` stays, because `uv --project gui` reads only the project's own pin.

## Finding: the bundle froze CPython 3.15.1, not 3.14 (fixed in `09b87d4d`)

The guest build ran `uv sync --locked --project gui` from the checkout root, as `.github/workflows/bundles.yml` does.
uv downloaded CPython 3.15.1 (`pyinstaller.log`: "Python: 3.15.1"). `gui/pyproject.toml` says `>=3.14` and the root
`.python-version` (3.14) is not used for `--project gui`. The host's GUI environments are 3.14 because they were
created earlier. A CI runner without a 3.14 interpreter would likely do the same, although the workflow step is
labelled "Python 3.14". The bundle report did not record the interpreter version.

**Fix** (the orchestrator's call, agreed by the user): `gui/.python-version` pins 3.14.8, the workflow passes
`--python 3.14.8`, and `build_bundle.py` refuses any interpreter but CPython 3.14.x and writes `"python"` into
`bundle-report.json`. The rebuilt bundle reports `cpython 3.14.8` (glibc 2.38 needed, 174.7 MB) and passed steps 1–3.
