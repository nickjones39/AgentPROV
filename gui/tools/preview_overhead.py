"""G4 live-preview overhead (build log deviation 33): one scripted ``agentprov run`` per call. With ``--preview`` the
GUI's live preview helper (``python -I -m agentprov_gui.preview HOME``) watches every session the run starts, as the
dashboard does. Prints one JSON summary line; exits 1 when the run failed or wrote no cell.

Measured: the run's wall time (process start to exit), each cell's duration (its session's start and end progress
events; the live AER records no run duration) and, with ``--preview``, the helper's CPU time (user + system), its wall
time and the deltas it sent.

The 2026-10-24 series (build log, G4 "Overhead measured"): six runs in the order a b b a a b (a without the preview,
b with it), each

    python gui/tools/preview_overhead.py [--preview] --label run<i>-<a|b> --work DIR --repo . -- agentdojo \\
        --llm-script gui/tools/preview_overhead_script.json --suite banking --benign only --repeats 3 --jobs 2

through ``tools/suite_queue.py --class import --cpu 3``. Corpora and logs go under ``--work``, outside the repository.
The script makes 14 read-only banking tool calls and then replies, so each cell has 15 model calls.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

import psutil


def _sessions(progress: Path, offset: int) -> tuple[list[str], int]:
    """Session ids of the ``session`` start events appended to ``progress`` after ``offset``."""
    if not progress.exists():
        return [], offset
    with open(progress, "rb") as fh:
        fh.seek(offset)
        chunk = fh.read()
    complete = chunk[: chunk.rfind(b"\n") + 1]
    found = []
    for line in complete.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("event") == "session" and event.get("phase") == "start" and isinstance(event.get("session"), str):
            found.append(event["session"])
    return found, offset + len(complete)


def _cell_seconds(progress: Path) -> list[float]:
    """Each cell's duration: its session's end event minus its start event."""
    starts: dict[str, float] = {}
    cells = []
    for line in progress.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if event.get("event") != "session":
            continue
        t = dt.datetime.fromisoformat(event["ts"].replace("Z", "+00:00")).timestamp()
        if event.get("phase") == "start":
            starts[event["session"]] = t
        elif event.get("phase") == "end" and event["session"] in starts:
            cells.append(t - starts.pop(event["session"]))
    return sorted(cells)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--preview", action="store_true", help="run the live preview helper beside the run")
    ap.add_argument("--label", required=True, help="the run's campaign and file names (lower case)")
    ap.add_argument("--work", type=Path, required=True, help="where the corpus, progress and log files go")
    ap.add_argument("--repo", type=Path, required=True, help="the checkout (its .venv and gui/.venv are used)")
    ap.add_argument("run_args", nargs=argparse.REMAINDER, help="-- SOURCE and agentprov run options")
    a = ap.parse_args(argv)
    home = Path(os.environ.get("AGENTPROV_HOME", Path.home() / ".agentprov"))
    progress = a.work / f"{a.label}.progress.jsonl"
    command = [str(a.repo / ".venv" / "bin" / "agentprov"), "run", *[x for x in a.run_args if x != "--"],
               "--corpus", str(a.work / "corpora" / a.label), "--campaign", a.label, "--progress", "status",
               "--progress-format", "jsonl", "--progress-file", str(progress),
               "--log-file", str(a.work / f"{a.label}.log")]
    helper = None
    deltas = [0]
    if a.preview:
        helper = subprocess.Popen([str(a.repo / "gui" / ".venv" / "bin" / "python"), "-I", "-m",  # noqa: S603
                                   "agentprov_gui.preview", str(home)],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        out_pipe = helper.stdout

        def drain() -> None:
            assert out_pipe is not None
            for _ in out_pipe:
                deltas[0] += 1

        threading.Thread(target=drain, daemon=True).start()
    started = time.perf_counter()
    run = subprocess.Popen(command, cwd=a.repo, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # noqa: S603
    offset, watched = 0, set()
    while True:
        done = run.poll() is not None
        if helper is not None and helper.stdin is not None:
            new, offset = _sessions(progress, offset)
            for session in new:
                if session not in watched:
                    watched.add(session)
                    helper.stdin.write(json.dumps({"watch": session}).encode() + b"\n")
                    helper.stdin.flush()
        if done:
            break
        time.sleep(0.1)
    out: dict[str, Any] = {"label": a.label, "preview": a.preview, "exit": run.returncode,
                           "run_wall_s": round(time.perf_counter() - started, 3)}
    if helper is not None and helper.stdin is not None:
        time.sleep(0.6)  # one more 250 ms poll round for the last lines
        proc = psutil.Process(helper.pid)
        cpu = proc.cpu_times()
        wall = time.time() - proc.create_time()
        helper.stdin.close()
        helper.wait(timeout=10)
        out.update({"helper_cpu_s": round(cpu.user + cpu.system, 3), "helper_wall_s": round(wall, 3),
                    "helper_cpu_pct_of_core": round(100 * (cpu.user + cpu.system) / wall, 3),
                    "sessions_watched": len(watched), "deltas": deltas[0]})
    cells = _cell_seconds(progress) if progress.exists() else []
    out.update({"cells": len(cells), "cell_s_median": round(cells[len(cells) // 2], 3) if cells else None,
                "cell_s_mean": round(sum(cells) / len(cells), 3) if cells else None, "cell_s_sum": round(sum(cells), 3)})
    print(json.dumps(out), flush=True)
    return 0 if run.returncode == 0 and cells else 1


if __name__ == "__main__":
    raise SystemExit(main())
