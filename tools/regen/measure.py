"""Run one command and record its wall time, exit status and peak memory (regeneration-round rehearsal).

Usage: python -I tools/regen/measure.py --label NAME --record FILE.jsonl -- COMMAND [ARG ...]

The command's stdout and stderr go to ``<record dir>/<label>.out`` and ``<label>.err``. Memory is sampled once a second
from ``ps`` over the command's whole process tree (the CLI and its T1 workers): the peak of the tree's summed RSS and
the peak RSS of any single process. One JSON line is appended to the record file. Stdlib only; reads no corpus byte.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def _tree_rss(root: int) -> tuple[int, int, int]:
    """(sum of RSS in KiB over root and its descendants, largest single RSS in KiB, process count)."""
    out = subprocess.run(["ps", "-Ao", "pid=,ppid=,rss="], capture_output=True, text=True, check=False).stdout
    children: dict[int, list[int]] = {}
    rss: dict[int, int] = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) != 3:
            continue
        pid, ppid, kib = (int(p) for p in parts)
        children.setdefault(ppid, []).append(pid)
        rss[pid] = kib
    stack, seen = [root], []
    while stack:
        pid = stack.pop()
        if pid in rss:
            seen.append(pid)
        stack.extend(children.get(pid, []))
    values = [rss[p] for p in seen]
    return sum(values), max(values, default=0), len(values)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--record", required=True, type=Path)
    ap.add_argument("command", nargs=argparse.REMAINDER)
    args = ap.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        ap.error("no command")
    args.record.parent.mkdir(parents=True, exist_ok=True)
    out_path = args.record.parent / f"{args.label}.out"
    err_path = args.record.parent / f"{args.label}.err"
    load_start = os.getloadavg()
    start = time.monotonic()
    peak_tree = peak_single = peak_procs = 0
    with out_path.open("wb") as out, err_path.open("wb") as err:
        proc = subprocess.Popen(command, stdout=out, stderr=err)
        while proc.poll() is None:
            tree, single, procs = _tree_rss(proc.pid)
            peak_tree, peak_single, peak_procs = max(peak_tree, tree), max(peak_single, single), max(peak_procs, procs)
            time.sleep(1.0)
    wall = time.monotonic() - start
    row = {
        "label": args.label,
        "command": command,
        "exit": proc.returncode,
        "wall_s": round(wall, 1),
        "peak_tree_rss_mib": round(peak_tree / 1024, 1),
        "peak_process_rss_mib": round(peak_single / 1024, 1),
        "peak_processes": peak_procs,
        "load_start": [round(x, 1) for x in load_start],
        "load_end": [round(x, 1) for x in os.getloadavg()],
        "started": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - wall)),
    }
    with args.record.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")
    print(json.dumps(row, sort_keys=True))
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
