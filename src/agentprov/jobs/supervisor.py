"""A job's supervisor (D-704): ``python -I -m agentprov.jobs.supervisor JOB_DIR``, started detached by
:class:`agentprov.jobs.manager.JobManager`.

It starts the job's argv (from ``job.json``) in the job's cwd, with stdin ``/dev/null`` and stdout and stderr to
``stdout.txt`` and ``stderr.txt``, records both pids with their create times in ``job.json``, waits, and writes
``ended.json`` with the real exit code. A ``SIGTERM`` to the supervisor is passed on to the job (the graceful stop);
the supervisor itself never ends before the job. No Qt, no network; the environment is the one the manager gave it.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from agentprov.jobs.record import JOB_FORMAT, OUTCOMES, read_json


def _create_time(pid: int) -> float | None:
    import psutil

    try:
        return float(psutil.Process(pid).create_time())
    except psutil.Error:
        return None


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def supervise(directory: Path) -> int:
    from agentprov.jobs.manager import atomic_write_json

    record = read_json(directory / "job.json")
    if record is None or record.get("format") != JOB_FORMAT or not isinstance(record.get("argv"), list):
        return 2
    argv = [str(a) for a in record["argv"]]
    cwd = str(record.get("cwd") or directory)
    record.update(supervisor_pid=os.getpid(), supervisor_create_time=_create_time(os.getpid()))
    atomic_write_json(directory / "job.json", record)
    child: subprocess.Popen[bytes] | None = None

    def forward(signum: int, _frame: Any) -> None:
        if child is not None and child.poll() is None:
            child.send_signal(signum)

    signal.signal(signal.SIGTERM, forward)
    try:
        with open(directory / "stdout.txt", "wb") as out, open(directory / "stderr.txt", "wb") as err:
            child = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.DEVNULL, stdout=out, stderr=err,  # noqa: S603
                                     close_fds=True)
    except (OSError, ValueError) as exc:
        atomic_write_json(directory / "ended.json", {"exit_code": None, "outcome": "not_started", "how": "spawn_failed",
                                                     "error": type(exc).__name__, "observed": _now()})
        record["state"] = "ended"
        atomic_write_json(directory / "job.json", record)
        return 1
    record.update(state="running", pid=child.pid, pid_create_time=_create_time(child.pid))
    atomic_write_json(directory / "job.json", record)
    while True:
        try:
            code = child.wait()
            break
        except InterruptedError:  # pragma: no cover - PEP 475 retries; kept for clarity
            continue
    outcome = OUTCOMES.get(code, "signal" if code < 0 else "internal")
    summary = read_json(directory / "summary.json")
    if summary is not None and summary.get("exit_code") == code and isinstance(summary.get("outcome"), str):
        outcome = summary["outcome"]
    atomic_write_json(directory / "ended.json", {"exit_code": code, "outcome": outcome, "how": "waited",
                                                 "observed": _now()})
    record["state"] = "ended"
    atomic_write_json(directory / "job.json", record)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        return 2
    return supervise(Path(args[0]))


if __name__ == "__main__":
    raise SystemExit(main())
