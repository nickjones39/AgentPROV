"""The G5 §3 steps inside a Linux guest (D-862, D-865). Runs as the guest's own user with the guest's ``python3``
(stdlib only); it is the harness, not part of what is tested.

    python3 linux_steps.py --bundle AgentPROV-linux-*.tar.gz --corpus mini.tar.gz --out DIR [--level V]

Each step appends one JSON line to ``DIR/steps.jsonl``; step 2 leaves ``DIR/screenshot.xwd`` (the host converts it).
Nothing here reads a key or the network.
"""

# ruff: noqa: S603, S607 - the harness runs the bundle and fixed guest tools (Xvfb, xwd, ldd) found on the guest PATH

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import signal
import subprocess
import tarfile
import time
from pathlib import Path

DISPLAY = ":99"
TAIL = 2048


def _tail(text: str | bytes | None) -> str:
    if isinstance(text, bytes):
        text = text.decode("utf-8", "replace")
    return (text or "")[-TAIL:]


class Steps:
    def __init__(self, out: Path) -> None:
        self.out = out
        self.file = out / "steps.jsonl"

    def record(self, step: int, level: str, passed: bool, started: float, **evidence: object) -> None:
        line = {"step": step, "level": level, "pass": passed, "seconds": round(time.monotonic() - started, 2),
                **evidence}
        with open(self.file, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(line, sort_keys=True) + "\n")


def _unpack(archive: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as tf:
        tf.extractall(dest, filter="tar")  # the guest's own copy of a file the host built


def _missing_libraries(bundle: Path) -> list[str]:
    """``ldd`` of the xcb platform plugin: the shared libraries the guest lacks (the prerequisite list's evidence)."""
    plugins = sorted(bundle.rglob("libqxcb.so"))
    if not plugins:
        return ["libqxcb.so itself"]
    done = subprocess.run(["ldd", str(plugins[0])], capture_output=True, text=True, check=False)
    return sorted({line.split("=>")[0].strip() for line in done.stdout.splitlines() if "not found" in line})


def _windows() -> str:
    done = subprocess.run(["xwininfo", "-root", "-tree"], capture_output=True, text=True, check=False,
                          env={**os.environ, "DISPLAY": DISPLAY})
    return done.stdout


def step1(steps: Steps, exe: Path) -> None:
    t = time.monotonic()
    done = subprocess.run([str(exe), "--smoke"], capture_output=True, text=True, check=False, timeout=120,
                          env={**os.environ, "QT_QPA_PLATFORM": "offscreen"})
    steps.record(1, "V", done.returncode == 0, t, exit=done.returncode, stderr_tail=_tail(done.stderr))


def step2(steps: Steps, exe: Path, corpus: Path, bundle: Path) -> None:
    t = time.monotonic()
    missing = _missing_libraries(bundle)
    xvfb = subprocess.Popen(["Xvfb", DISPLAY, "-screen", "0", "1440x900x24", "-nolisten", "tcp"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    log = steps.out / "step2-gui.stderr"
    found, alive, code = False, False, None
    try:
        time.sleep(2)
        with open(log, "wb") as err:
            gui = subprocess.Popen([str(exe), str(corpus)], stdout=subprocess.DEVNULL, stderr=err,
                                   env={**os.environ, "DISPLAY": DISPLAY, "QT_QPA_PLATFORM": "xcb"})
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline and gui.poll() is None:
                if '"AgentPROV' in _windows():
                    found = True
                    break
                time.sleep(1)
            if found:
                time.sleep(10)  # the executions table loads in the background
            alive = gui.poll() is None
            with open(steps.out / "screenshot.xwd", "wb") as shot:
                subprocess.run(["xwd", "-root", "-silent"], stdout=shot, check=False, timeout=30,
                               env={**os.environ, "DISPLAY": DISPLAY})
            if alive:
                gui.send_signal(signal.SIGTERM)
            try:
                code = gui.wait(timeout=15)
            except subprocess.TimeoutExpired:
                gui.kill()
                code = gui.wait()
    finally:
        xvfb.terminate()
        xvfb.wait(timeout=15)
    steps.record(2, "V", found and alive, t, platform_plugin="xcb", window_found=found, alive_after_load=alive,
                 exit_after_sigterm=code, missing_libraries=missing, executions="count on the screenshot (D-864)",
                 stderr_tail=_tail(log.read_bytes() if log.is_file() else b""))


def step3(steps: Steps, exe: Path, home: Path) -> None:
    t = time.monotonic()
    home.mkdir(parents=True, exist_ok=True)
    try:
        done = subprocess.run([str(exe), "--preview-helper", str(home)], stdin=subprocess.DEVNULL,
                              capture_output=True, check=False, timeout=5)
        steps.record(3, "V", done.returncode == 0, t, exit=done.returncode, stderr_tail=_tail(done.stderr))
    except subprocess.TimeoutExpired:
        steps.record(3, "V", False, t, exit=None, error="did not exit within 5 s")


def guest_facts(out: Path) -> None:
    release = Path("/etc/os-release").read_text(encoding="utf-8") if Path("/etc/os-release").is_file() else ""
    facts = {"os_release": dict(line.split("=", 1) for line in release.splitlines() if "=" in line),
             "kernel": platform.release(), "machine": platform.machine(), "glibc": platform.libc_ver()[1],
             "fonts": len(subprocess.run(["fc-list"], capture_output=True, text=True, check=False).stdout.splitlines())
             if shutil.which("fc-list") else 0}
    (out / "guest.json").write_text(json.dumps(facts, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", type=Path, required=True)
    ap.add_argument("--corpus", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--level", choices=("V",), default="V")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    work = Path.home() / "g5"
    _unpack(args.bundle, work / "bundle")
    _unpack(args.corpus, work / "corpora")
    bundle = work / "bundle" / "AgentPROV"
    exe = bundle / "AgentPROV"
    corpus = next(p for p in (work / "corpora").iterdir() if p.name.endswith(".partial"))
    guest_facts(args.out)
    steps = Steps(args.out)
    step1(steps, exe)
    step2(steps, exe, corpus.with_name(corpus.name.removesuffix(".partial")), bundle)
    step3(steps, exe, work / "preview-home")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
