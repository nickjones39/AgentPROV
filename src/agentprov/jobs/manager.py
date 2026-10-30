"""The job manager (D-704; GUI design §4, D-392, moved from the GUI): detached ``agentprov`` jobs that outlive the
process that started them. Used by ``agentprov jobs`` and ``agentprov batch`` only; the GUI calls those commands.

**Spawn** (§4.2): an argv list, never a shell; an environment allowlist (no ``*_API_KEY``, no ``UV_*``); stdin
``/dev/null``. The job runs under a small **supervisor** (:mod:`agentprov.jobs.supervisor`), started in a new session
(POSIX ``start_new_session``; Windows ``DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_BREAKAWAY_FROM_JOB``,
retried without the breakaway when the caller's job object forbids it, G5 P-2). It
starts the job's CLI with stdout and stderr redirected to files, waits for it, and writes ``ended.json`` with the
real exit code. Identity is ``(pid, create_time)`` for both processes: a pid alone is reused by the OS.

**What a job runs** is ``agentprov`` itself, in this interpreter, or one repository tool: ``--tool tools/<name>.py``
names a regular file inside this checkout's ``tools/`` (no ``..``, no absolute path, no symlink, resolved inside), run
with this interpreter. Nothing else can be started.

**Rules checked before a spawn** (§4.4): one writer per corpus tree (a running job that writes it, or an
``.agentprov.lock``); one global slot each for network fetches and backend builds.

**Stop** (§4.5): one ``SIGTERM`` to the job's CLI (it flushes, seals aborted live sessions and exits 130). **Kill**:
``SIGKILL`` to every process group of the job's tree, after the identity check. **Drain** (D-394): ``control.json``,
only for a job started with ``--control-file``. A job never holds or deletes a corpus lock.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import tomllib
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Final

from agentprov.errors import AgentProvError
from agentprov.jobs.record import JOB_FORMAT, Job, jobs_dir, list_jobs, load_job, read_json, same_process
from agentprov.jobs.tiers import REPO_COMMANDS, split_index, tier_of_argv

__all__ = ["ENV_ALLOWLIST", "JobManager", "JobRequest", "SpawnRefused", "allowlisted_env", "atomic_write_json",
           "checkout_root", "new_job_id", "on_windows", "queue_available", "resolve_tool"]

ENV_ALLOWLIST: Final = ("PATH", "HOME", "LANG", "TZ", "AGENTPROV_HOME", "AGENTPROV_UPSTREAM_CACHE",
                        "AGENTPROV_BASELINE_CORPUS", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "SystemRoot", "TMPDIR",
                        "AGENTPROV_JOB_CPU_BUDGET", "AGENTPROV_JOB_MEM_GIB_BUDGET", "AGENTPROV_SUITE_QUEUE_DIR",
                        "AGENTPROV_NO_KEYCHAIN")
#: allowlist entries read as paths relative to their own cwd; ``HOME`` is only made absolute.
_PATH_ENV: Final = ("AGENTPROV_HOME", "AGENTPROV_UPSTREAM_CACHE", "AGENTPROV_BASELINE_CORPUS",
                    "AGENTPROV_SUITE_QUEUE_DIR", "TMPDIR", "HOME")
START_WAIT_S: Final = 15.0
#: Windows process-creation flags of a detached supervisor
_DETACHED_PROCESS, _CREATE_NEW_PROCESS_GROUP, _CREATE_BREAKAWAY_FROM_JOB = 0x00000008, 0x00000200, 0x01000000
PROGRESS_LEVELS: Final = ("status", "steps")


class SpawnRefused(AgentProvError):
    """A spawn refused before it starts (single writer, global slot, the tool rule). Exit 4."""

    code = "jobs.refused"
    exit_code = 4

    def __init__(self, message: str, code: str) -> None:
        super().__init__(message, code=code)


def on_windows() -> bool:
    """Whether this host is Windows (one place, so tests can take the Windows paths on any host)."""
    return os.name == "nt"


def queue_available(root: Path | None) -> bool:
    """Whether jobs can go through the machine-wide job queue: ``tools/suite_queue.py`` of a repository checkout, on
    macOS or Linux (it locks with ``fcntl``; Windows has no queue in v0.1, G5 note §2.6)."""
    return not on_windows() and root is not None and (root / "tools" / "suite_queue.py").is_file()


def new_job_id() -> str:
    """A UUIDv7 (time-ordered) as the job id."""
    return str(uuid.uuid7())


#: Windows refuses to rename over a file another process has open (``WinError 5``), and the manager, the GUI and
#: ``jobs list`` read ``job.json`` while the supervisor rewrites it. A reader holds the file for microseconds, so the
#: write is retried for up to about a second (G5 clean-machine run, Windows x64: every supervisor crashed on this race).
_REPLACE_RETRIES: Final = 50
_REPLACE_PAUSE_S: Final = 0.02


def atomic_write_json(path: Path, obj: Mapping[str, Any]) -> None:
    from agentprov.io.atomic import atomic_write_bytes

    data = json.dumps(dict(obj), sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
    for attempt in range(_REPLACE_RETRIES):
        try:
            atomic_write_bytes(path, data)
            return
        except PermissionError:
            if not on_windows() or attempt == _REPLACE_RETRIES - 1:
                raise
            time.sleep(_REPLACE_PAUSE_S)


def allowlisted_env(environ: Mapping[str, str], start_cwd: str | None) -> dict[str, str]:
    """The :data:`ENV_ALLOWLIST` part of ``environ``. A path entry is ``~``-expanded and made absolute against
    ``start_cwd`` (the job's cwd is elsewhere, GR-50); a relative one without a start cwd is dropped."""
    env = {k: environ[k] for k in ENV_ALLOWLIST if k in environ}
    for name in _PATH_ENV:
        value = env.get(name)
        if not value:
            continue
        if name != "HOME":
            value = os.path.expanduser(value)
        if not os.path.isabs(value):
            if start_cwd is None:
                del env[name]
                continue
            value = os.path.join(start_cwd, value)
        env[name] = os.path.normpath(value)
    return env


def checkout_root() -> Path | None:
    """The repository checkout this ``agentprov`` runs from (an editable install), or ``None`` (a wheel)."""
    here = Path(__file__).resolve()
    for candidate in here.parents:
        pyproject = candidate / "pyproject.toml"
        try:
            if pyproject.is_file() and (tomllib.loads(pyproject.read_text(encoding="utf-8")).get("project") or {}).get(
                    "name") == "agentprov":
                return candidate
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
            continue
    return None


def resolve_tool(root: Path | None, name: str) -> Path:
    """``tools/<...>.py`` of the checkout ``root`` as a resolved regular file, or :class:`SpawnRefused`.

    Refused: no checkout; an absolute path or a drive; a ``..`` part; not under ``tools/``; not ``.py``; a symlink
    (the file or a directory on its way); a resolved path outside ``tools/``; anything that is not a regular file."""
    if root is None:
        raise SpawnRefused("--tool needs a repository checkout (this agentprov is not an editable install)",
                           "jobs.tool.no_checkout")
    parts = Path(name).parts
    if (os.path.isabs(name) or not parts or parts[0] != "tools" or ".." in parts or "\\" in name or ":" in name
            or not name.endswith(".py")):
        raise SpawnRefused("--tool names a file tools/<name>.py of this checkout", "jobs.tool.path")
    tools = (root / "tools").resolve()
    walk = root
    for part in parts:
        walk = walk / part
        if walk.is_symlink():
            raise SpawnRefused("--tool: a symlink is never followed", "jobs.tool.symlink")
    target = walk.resolve()
    if not target.is_relative_to(tools) or not target.is_file():
        raise SpawnRefused("--tool names a file tools/<name>.py of this checkout", "jobs.tool.path")
    return target


@dataclass(frozen=True, slots=True)
class JobRequest:
    """What ``jobs start`` (or a batch step) asks for. ``argv`` is the subcommand argv (or the tool's arguments)."""

    argv: tuple[str, ...]
    label: str = ""
    writes: tuple[str, ...] = ()
    reads: tuple[str, ...] = ()
    slot: str | None = None
    notes: tuple[str, ...] = ()
    control_file: bool = False
    queue_cpu: int | None = None
    progress_level: str = "status"
    tool: str | None = None
    batch_id: str | None = None
    conformance_skipped: bool = False
    extra: Mapping[str, str | int | float | bool] = field(default_factory=dict)

    @property
    def command(self) -> str:
        return f"tool:{self.tool}" if self.tool else " ".join(self.argv[: split_index(self.argv)]) if self.argv else ""

    @property
    def tier(self) -> str:
        return tier_of_argv(self.argv, "R1" if self.tool else None)

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> JobRequest:
        """The request a recorded job was started with (``jobs resume``)."""
        def strs(key: str) -> tuple[str, ...]:
            value = record.get(key)
            return tuple(str(v) for v in value) if isinstance(value, list) else ()

        cpu = record.get("queue_cpu")
        extra = record.get("extra")
        return cls(strs("subcommand_argv"), str(record.get("label") or ""), strs("writes"), strs("reads"),
                   record.get("slot") if isinstance(record.get("slot"), str) else None, strs("notes"),
                   bool(record.get("control_file")), cpu if isinstance(cpu, int) and not isinstance(cpu, bool) else None,
                   str(record.get("progress_level") or "status"),
                   record.get("tool") if isinstance(record.get("tool"), str) else None,
                   record.get("batch_id") if isinstance(record.get("batch_id"), str) else None,
                   bool(record.get("conformance_skipped")),
                   {k: v for k, v in extra.items() if isinstance(v, str | int | float | bool)}
                   if isinstance(extra, dict) else {})


def _norm(path: str) -> str:
    """A corpus path normalised for the single-writer rule (``DIR`` and ``DIR.partial`` are one tree)."""
    p = Path(path).expanduser()
    with contextlib.suppress(OSError):
        p = p.resolve()
    name = p.name[: -len(".partial")] if p.name.endswith(".partial") else p.name
    return str(p.with_name(name))


class JobManager:
    def __init__(self, home: Path, *, environ: Mapping[str, str] | None = None, start_cwd: str | None = None,
                 root: Path | None = None) -> None:
        self.home = Path(os.path.abspath(Path(home).expanduser()))
        self.jobs_dir = jobs_dir(self.home)
        self.environ = dict(os.environ if environ is None else environ)
        if start_cwd is None:
            with contextlib.suppress(OSError):
                start_cwd = os.getcwd()
        self.start_cwd = start_cwd
        self.root = root if root is not None else checkout_root()

    # ------------------------------------------------------------------------------------------ environment
    def child_env(self) -> dict[str, str]:
        """The allowlisted environment, the home, and the job queue's budget from ``agentprov settings``
        (``compute.cpu_budget``, ``compute.mem_gib_budget``) unless the environment sets it already."""
        env = allowlisted_env(self.environ, self.start_cwd)
        env["AGENTPROV_HOME"] = str(self.home)
        from agentprov import settings

        try:
            stored = settings.items("compute.", home=self.home)
        except settings.SettingsError:
            stored = {}
        for key, var in (("compute.cpu_budget", "AGENTPROV_JOB_CPU_BUDGET"),
                         ("compute.mem_gib_budget", "AGENTPROV_JOB_MEM_GIB_BUDGET")):
            if key in stored and var not in env:
                env[var] = str(stored[key])
        return env

    def program(self) -> list[str]:
        """This interpreter's ``agentprov``, isolated (``-I``: no cwd on the path, no ``PYTHON*`` variables)."""
        return [sys.executable, "-I", "-m", "agentprov"]

    def full_argv(self, req: JobRequest, directory: Path) -> list[str]:
        """The program, the subcommand words, the job's global options and the rest (GUI design Appendix A)."""
        prefix: list[str] = []
        if req.queue_cpu is not None:
            if on_windows():
                raise SpawnRefused("--queue-cpu: the machine-wide job queue (tools/suite_queue.py) runs on macOS and "
                                   "Linux only", "jobs.queue.unavailable")
            if self.root is None or not queue_available(self.root):
                raise SpawnRefused("--queue-cpu needs tools/suite_queue.py of a repository checkout",
                                   "jobs.queue.unavailable")
            prefix = [sys.executable, str(self.root / "tools" / "suite_queue.py"), "--class", "import", "--cpu",
                      str(req.queue_cpu), "--label", f"job-{directory.name[:13]}", "--no-session-status", "--"]
        if req.tool is not None:
            tool = resolve_tool(self.root, req.tool)
            return [*prefix, sys.executable, str(tool), "-C", str(self.root), *req.argv]  # its own dir on the path
        split = split_index(req.argv)
        argv = [*prefix, *self.program(), *req.argv[:split],
                "--progress", "steps" if req.progress_level == "steps" else "status", "--progress-format", "plain",
                "--progress-file", str(directory / "progress.jsonl"), "--log-file", str(directory / "log.jsonl"),
                "--summary-json", str(directory / "summary.json"), "--no-colour"]
        if req.control_file:
            argv += ["--control-file", str(directory / "control.json")]
        return argv + list(req.argv[split:])

    def job_cwd(self, req: JobRequest, directory: Path) -> Path:
        if req.tool is not None and self.root is not None:
            return self.root
        if req.argv[:1] and req.argv[0] in REPO_COMMANDS and self.root is not None:
            return self.root
        return directory

    # ------------------------------------------------------------------------------------------ rules
    def check(self, req: JobRequest) -> None:
        """Raise :class:`SpawnRefused` when a rule forbids starting ``req`` now."""
        if not req.argv and req.tool is None:
            raise SpawnRefused("no command to run", "jobs.argv.empty")
        if req.argv[:1] == ("jobs",) or req.argv[:2] == ("batch", "start"):
            raise SpawnRefused("a job does not start jobs (batch run is the batch driver's own job)",
                               "jobs.argv.recursive")
        if req.progress_level not in PROGRESS_LEVELS:
            raise SpawnRefused("--progress-level is status or steps", "jobs.progress_level")
        running = [j for j in list_jobs(self.home) if j.state == "running"]
        for target in req.writes:
            key = _norm(target)
            for job in running:
                if key in {_norm(w) for w in job.writes}:
                    raise SpawnRefused(f"another job ({job.command}) is writing that corpus; one writer per corpus",
                                       "jobs.writer.busy")
            if (Path(key + ".partial") / ".agentprov.lock").exists():
                raise SpawnRefused("that corpus has a writer's lock; wait for its job, or remove a stale lock with "
                                   "--break-stale-lock", "jobs.writer.locked")
        if req.slot is not None:
            for job in running:
                if job.record.get("slot") == req.slot:
                    raise SpawnRefused(f"only one {req.slot} job runs at a time", "jobs.slot.busy")

    # ------------------------------------------------------------------------------------------ spawn
    def spawn(self, req: JobRequest, *, wait_s: float = START_WAIT_S, job_id: str | None = None) -> Job:
        """Start ``req`` under its supervisor; returns once the supervisor recorded the CLI's pid (or the job ended).
        ``job_id``: an id chosen beforehand (``batch start`` records its driver before the driver starts). On Windows an
        ``agentprov`` job always gets a control file: there is no SIGTERM, so it is the only graceful stop (G5 P-2)."""
        if on_windows() and req.tool is None and not req.control_file:
            req = replace(req, control_file=True)
        self.check(req)
        job_id = job_id or new_job_id()
        directory = self.jobs_dir / job_id
        directory.mkdir(parents=True, exist_ok=False)
        try:
            if os.name == "posix":
                os.chmod(directory, 0o700)
                os.chmod(self.jobs_dir, 0o700)
            argv = self.full_argv(req, directory)
            env = {**self.child_env(), "AGENTPROV_JOB_ID": job_id}  # a batch driver knows which job it is
            record: dict[str, Any] = {
                "format": JOB_FORMAT, "job_id": job_id, "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "state": "starting", "argv": argv, "cwd": str(self.job_cwd(req, directory)), "env_names": sorted(env),
                "command": req.command, "subcommand_argv": list(req.argv), "tier": req.tier, "label": req.label,
                "writes": list(req.writes), "reads": list(req.reads), "slot": req.slot, "notes": list(req.notes),
                "control_file": req.control_file, "queue_cpu": req.queue_cpu, "progress_level": req.progress_level,
                "tool": req.tool, "batch_id": req.batch_id, "conformance_skipped": req.conformance_skipped,
                "extra": dict(req.extra), "platform": sys.platform, "pid": None, "pid_create_time": None,
                "supervisor_pid": None, "supervisor_create_time": None,
            }  # fmt: skip
            atomic_write_json(directory / "job.json", record)
            with open(directory / "supervisor.txt", "wb") as err:
                supervisor = self._start_supervisor(directory, env, err)
        except (OSError, ValueError) as exc:
            shutil.rmtree(directory, ignore_errors=True)
            raise SpawnRefused(f"the job could not be started ({type(exc).__name__})", "jobs.spawn.failed") from None
        except SpawnRefused:
            shutil.rmtree(directory, ignore_errors=True)
            raise
        deadline = time.monotonic() + wait_s
        while time.monotonic() < deadline:
            rec = read_json(directory / "job.json") or {}
            if rec.get("pid") is not None or (directory / "ended.json").exists() or supervisor.poll() is not None:
                break
            time.sleep(0.02)
        job = load_job(directory)
        assert job is not None
        return job

    # ------------------------------------------------------------------------------------------ control
    @staticmethod
    def _start_supervisor(directory: Path, env: Mapping[str, str], err: Any) -> subprocess.Popen[bytes]:
        """The detached supervisor: a new session (POSIX) or a new process group outside the caller's job object
        (Windows). When the caller's job object forbids breakaway (access denied: some terminals and CI runners), it
        starts without it and says so in ``supervisor.txt``: ending that job object may then end this job too (G5
        P-2)."""
        argv = [sys.executable, "-I", "-m", "agentprov.jobs.supervisor", str(directory)]
        common: dict[str, Any] = {"cwd": directory, "env": dict(env), "stdin": subprocess.DEVNULL,
                                  "stdout": subprocess.DEVNULL, "stderr": err, "close_fds": True}
        if not on_windows():
            return subprocess.Popen(argv, start_new_session=True, **common)  # noqa: S603 - this package's module
        flags = _DETACHED_PROCESS | _CREATE_NEW_PROCESS_GROUP
        try:
            return subprocess.Popen(argv, creationflags=flags | _CREATE_BREAKAWAY_FROM_JOB, **common)  # noqa: S603
        except PermissionError:
            err.write(b"agentprov jobs: started without CREATE_BREAKAWAY_FROM_JOB (the parent's job object forbids "
                      b"it); ending the parent's job may end this job too\n")
            err.flush()
            return subprocess.Popen(argv, creationflags=flags, **common)  # noqa: S603

    def stop(self, job: Job) -> bool:
        """The graceful stop: the D-394 control file's ``stop`` for a job that has one, else one SIGTERM to the job's
        CLI (POSIX). On Windows without a control file only :meth:`kill` exists."""
        if self.request(job, "stop"):
            return True
        if on_windows() or job.pid is None or not same_process(job.pid, job.record.get("pid_create_time")):
            return False
        os.kill(job.pid, signal.SIGTERM)
        return True

    def kill(self, job: Job) -> bool:
        """SIGKILL to every process group of the job's tree (the supervisor's), or TerminateProcess. The tree is
        snapshotted before any signal; a snapshotted process is killed by itself only while its identity holds."""
        import psutil

        leader_pid = job.supervisor_pid
        if leader_pid is None or not same_process(leader_pid, job.record.get("supervisor_create_time")):
            return False
        try:
            leader = psutil.Process(leader_pid)
            tree = [leader, *leader.children(recursive=True)]
        except psutil.Error:
            return False
        if not on_windows():
            groups: set[int] = set()
            for proc in tree:
                with contextlib.suppress(ProcessLookupError, PermissionError):
                    groups.add(os.getpgid(proc.pid))
            groups.discard(os.getpgid(0))  # never this process's own group
            for pgid in groups:
                with contextlib.suppress(ProcessLookupError, PermissionError):
                    os.killpg(pgid, signal.SIGKILL)
        for proc in tree:
            with contextlib.suppress(psutil.Error):
                proc.kill()
        with contextlib.suppress(psutil.Error):
            psutil.wait_procs(tree, timeout=5)  # the tree is gone (or a zombie) before the kill is recorded
        if not job.file("ended.json").exists():  # the supervisor died with the job: record the kill here
            atomic_write_json(job.file("ended.json"), {"exit_code": None, "outcome": "killed", "how": "killed",
                                                       "observed": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        return True

    def request(self, job: Job, request: str) -> bool:
        """D-394: ``control.json`` (``drain`` or ``stop``) for a job started with ``--control-file``."""
        if request not in ("drain", "stop") or not job.record.get("control_file") or job.state != "running":
            return False
        atomic_write_json(job.file("control.json"), {"format": "agentprov-control/0.1", "request": request,
                                                     "issued": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                                     "nonce": os.urandom(8).hex()})
        return True

    def resume(self, job: Job) -> Job:
        """Start ``job``'s request again (the CLI's own resume rules decide what is redone)."""
        return self.spawn(JobRequest.from_record(job.record))

    def prune_candidates(self, keep: int = 200, max_age_days: int = 90) -> list[Job]:
        """Ended jobs beyond the newest ``keep`` or older than ``max_age_days`` (GUI design §4.1)."""
        ended = [j for j in list_jobs(self.home) if j.state != "running"]
        cutoff = time.time() - max_age_days * 86400
        old = [j for j in ended if _mtime(j) < cutoff]
        return sorted({j.job_id: j for j in [*ended[keep:], *old]}.values(), key=lambda j: j.job_id)

    def delete(self, jobs: Iterable[Job]) -> int:
        """Delete ended job directories (only directly under the jobs directory). Returns how many."""
        n = 0
        for job in jobs:
            if job.state == "running" or job.directory.parent != self.jobs_dir or job.directory.is_symlink():
                continue
            shutil.rmtree(job.directory, ignore_errors=True)
            n += 1
        return n


def _mtime(job: Job) -> float:
    try:
        return job.file("job.json").stat().st_mtime
    except OSError:
        return 0.0


def find(home: Path, job_id: str) -> Job | None:
    """The job ``job_id`` (an exact id, or a unique prefix of at least 8 characters)."""
    jobs = list_jobs(home)
    exact = [j for j in jobs if j.job_id == job_id]
    if exact:
        return exact[0]
    hits = [j for j in jobs if len(job_id) >= 8 and j.job_id.startswith(job_id)]
    return hits[0] if len(hits) == 1 else None


def words_of(argv: Sequence[str]) -> str:
    return " ".join(argv[: split_index(argv)])
