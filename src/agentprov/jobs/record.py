"""Job records, read-only (D-704; GUI design §4; D-392): what ``agentprov jobs`` and the GUI read about a job.

A job directory ``$AGENTPROV_HOME/jobs/<job_id>/`` (mode 0700 on POSIX) holds ``job.json`` (written by
:mod:`agentprov.jobs.manager` and, for the pids, by the job's supervisor; no secret, no environment values),
``progress.jsonl``, ``log.jsonl`` and ``summary.json`` (written by the job's CLI), ``stdout.txt`` and ``stderr.txt``,
``control.json`` (D-394, only when the CLI accepts ``--control-file``) and ``ended.json`` (written by the supervisor
when the job ends, with its real exit code).

This module never writes, signals or spawns: the GUI imports it (design §2.2 allowlist, D-391), while every change
goes through the CLI. The state of a job is computed from its files and, while no ``ended.json`` exists, from the
supervisor's process identity ``(pid, create_time)``: a pid alone is reused by the OS.
"""

from __future__ import annotations

import calendar
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from agentprov.errors import IngestError
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads

__all__ = [
    "JOB_FORMAT",
    "OUTCOMES",
    "Job",
    "batches_dir",
    "jobs_dir",
    "list_jobs",
    "load_job",
    "read_json",
    "same_process",
    "tail_bytes",
    "valid_pid",
]

JOB_FORMAT: Final = "agentprov-job-record/0.1"  # not agentprov-job/0.1, the T1 worker protocol (G.4.6)
#: The outcome of an exit code, as the CLI's summary names it (N.1.3).
OUTCOMES: Final[Mapping[int, str]] = {0: "ok", 1: "failures", 2: "usage", 3: "environment", 4: "refused",
                                      5: "unsupported", 70: "internal", 130: "interrupted"}
_LIMITS: Final = IngestLimits()
_SMALL: Final = 4 * 1024 * 1024
#: The largest pid a process can have (the bound ``agentprov.io.atomic`` uses).
_MAX_PID: Final = 2**32 - 1 if os.name == "nt" else 2**31 - 1


def jobs_dir(home: Path) -> Path:
    """``$AGENTPROV_HOME/jobs`` (D-704; the GUI's old ``gui/jobs`` is not migrated)."""
    return Path(os.path.abspath(Path(home).expanduser())) / "jobs"


def batches_dir(home: Path) -> Path:
    return Path(os.path.abspath(Path(home).expanduser())) / "batches"


def read_json(path: Path, limit: int = _SMALL) -> dict[str, Any] | None:
    """A small JSON document written by AgentPROV, parsed strictly; ``None`` when absent or unusable."""
    try:
        with open(path, "rb") as fh:
            data = fh.read(limit + 1)
    except OSError:
        return None
    if len(data) > limit:
        return None
    try:
        value = strict_json_loads(data.rstrip(b"\n"), _LIMITS)
    except IngestError:
        return None
    return value if isinstance(value, dict) else None


def valid_pid(pid: object) -> int | None:
    """``pid`` when a process could have it, else ``None`` (psutil raises on <= 0, GR-41)."""
    return pid if isinstance(pid, int) and not isinstance(pid, bool) and 0 < pid <= _MAX_PID else None


def same_process(pid: int | None, create_time: object) -> bool:
    """Whether ``pid`` is still the process created at ``create_time`` (and not a zombie)."""
    import psutil

    if pid is None or not isinstance(create_time, int | float) or isinstance(create_time, bool):
        return False
    try:
        proc = psutil.Process(pid)
        return bool(abs(proc.create_time() - float(create_time)) < 0.01 and proc.status() != psutil.STATUS_ZOMBIE)
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, ValueError):
        return False


def utc_seconds(stamp: object) -> int | None:
    """A ``%Y-%m-%dT%H:%M:%SZ`` time as epoch seconds, or ``None``."""
    if not isinstance(stamp, str):
        return None
    try:
        return calendar.timegm(time.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ"))
    except (ValueError, OverflowError):
        return None


@dataclass(slots=True)
class Job:
    """One job as its files describe it. ``state``: ``running``, ``ended`` or ``unobserved`` (its supervisor is gone
    and no ``ended.json`` was written: killed from outside, or the machine restarted)."""

    job_id: str
    directory: Path
    record: dict[str, Any]
    state: str = "running"
    exit_code: int | None = None
    outcome: str | None = None
    ended_how: str | None = None

    @property
    def pid(self) -> int | None:
        """The job's CLI process (what a graceful stop signals)."""
        return valid_pid(self.record.get("pid"))

    @property
    def supervisor_pid(self) -> int | None:
        return valid_pid(self.record.get("supervisor_pid"))

    @property
    def argv(self) -> list[str]:
        argv = self.record.get("argv")
        return [str(a) for a in argv] if isinstance(argv, list) else []

    @property
    def subcommand_argv(self) -> list[str]:
        sub = self.record.get("subcommand_argv")
        return [str(a) for a in sub] if isinstance(sub, list) else []

    @property
    def command(self) -> str:
        return str(self.record.get("command", ""))

    @property
    def writes(self) -> list[str]:
        w = self.record.get("writes")
        return [str(x) for x in w] if isinstance(w, list) else []

    def file(self, name: str) -> Path:
        return self.directory / name

    @property
    def meta(self) -> dict[str, Any]:
        """The facts recorded with ``--meta`` (scalars only)."""
        extra = self.record.get("extra")
        return {k: v for k, v in extra.items() if isinstance(v, str | int | float | bool)} if isinstance(extra, dict) \
            else {}

    def to_json(self) -> dict[str, Any]:
        r = self.record
        return {"job_id": self.job_id, "state": self.state, "exit_code": self.exit_code, "outcome": self.outcome,
                "ended_how": self.ended_how, "command": self.command, "label": r.get("label"), "tier": r.get("tier"),
                "created": r.get("created"), "writes": self.writes, "reads": r.get("reads") or [],
                "batch_id": r.get("batch_id"), "slot": r.get("slot"), "control_file": bool(r.get("control_file")),
                "subcommand_argv": self.subcommand_argv, "pid": self.pid, "directory": str(self.directory),
                "meta": self.meta}


def observe(job: Job) -> Job:
    """Fill ``job``'s state from its files and its supervisor's identity. Writes nothing."""
    ended = read_json(job.file("ended.json"))
    if ended is not None:
        job.state = "ended" if ended.get("how") != "unobserved" else "unobserved"
        code = ended.get("exit_code")
        job.exit_code = code if isinstance(code, int) and not isinstance(code, bool) else None
        job.outcome = str(ended["outcome"]) if ended.get("outcome") is not None else None
        job.ended_how = str(ended.get("how"))
        return job
    if same_process(job.supervisor_pid, job.record.get("supervisor_create_time")) or (
            job.record.get("supervisor_pid") is None and job.record.get("state") == "starting"
            and (utc_seconds(job.record.get("created")) or 0) > time.time() - 60):
        job.state = "running"  # the supervisor waits for the CLI (or is being started)
        return job
    summary = read_json(job.file("summary.json"))
    code = summary.get("exit_code") if summary is not None else None
    if isinstance(code, int) and not isinstance(code, bool):
        job.state, job.exit_code, job.ended_how = "ended", code, "summary"
        job.outcome = str(summary.get("outcome")) if summary and summary.get("outcome") else OUTCOMES.get(code)
    else:
        job.state, job.exit_code, job.outcome, job.ended_how = "unobserved", None, None, "unobserved"
    return job


def load_job(directory: Path) -> Job | None:
    record = read_json(directory / "job.json")
    if record is None or record.get("format") != JOB_FORMAT or record.get("job_id") != directory.name:
        return None
    return observe(Job(directory.name, directory, record))


def list_jobs(home: Path) -> list[Job]:
    """Every job of ``home``, newest first (job ids are UUIDv7, so they sort by time)."""
    root = jobs_dir(home)
    if not root.is_dir():
        return []
    out = [j for d in sorted(root.iterdir(), reverse=True) if d.is_dir() and (j := load_job(d)) is not None]
    return out


def tail_bytes(path: Path, limit: int = 64 * 1024) -> bytes:
    """The last ``limit`` bytes of a file (``stdout.txt`` and ``stderr.txt`` are read at most this much)."""
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - limit))
            return fh.read(limit)
    except OSError:
        return b""
