"""The GUI's job manager: a client of ``agentprov jobs`` (D-704; design §4; D-392). No Qt.

Jobs are the core's (:mod:`agentprov.jobs`): ``$AGENTPROV_HOME/jobs/<job_id>/`` with ``job.json``, the CLI's
progress, log and summary files, ``stdout.txt``/``stderr.txt`` and ``ended.json``, which the job's supervisor writes
with the real exit code. The GUI **starts** a job with ``agentprov jobs start … -- ARGV`` and **controls** it with
``jobs stop|kill|drain|prune`` of the configured checkout's CLI (one implementation; D-700). It **reads** job state
from the files through the read-only :mod:`agentprov.jobs.record` (the D-391 allowlist), so a job started from a
terminal shows up here too. The rules a spawn must pass (one writer per corpus, one job per slot) are the CLI's; a
refusal comes back as :class:`SpawnRefused` with the CLI's code.

The GUI never holds a job's lock and never deletes one; a stale lock is reported with the ``--break-stale-lock``
action (a separate, confirmed job).
"""

from __future__ import annotations

import calendar
import contextlib
import json
import logging
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import psutil
from agentprov.errors import IngestError
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads

from agentprov_gui import platform_limits
from agentprov_gui.jobs.commands import JobSpec

__all__ = [
    "ENV_ALLOWLIST",
    "JOB_FORMAT",
    "USER_BIN_DIRS",
    "CliLocator",
    "Job",
    "JobManager",
    "SpawnRefused",
    "allowlisted_env",
    "atomic_write_json",
    "bundled_program",
    "installed_program",
    "is_cli_launcher",
    "new_job_id",
    "read_json",
    "set_cli_choice",
    "set_installed_program",
]

JOB_FORMAT: Final = "agentprov-gui-job/0.1"
#: the commands that find the repository from their cwd (M.4), started in the checkout: the core's
#: ``agentprov.jobs.tiers.REPO_COMMANDS``, copied because D-391 keeps that module out of the GUI's imports (a test pins
#: the two equal)
REPO_COMMANDS: Final = frozenset({"run", "backends", "migrate", "estimate"})
ENV_ALLOWLIST: Final = ("PATH", "HOME", "LANG", "TZ", "AGENTPROV_HOME", "AGENTPROV_UPSTREAM_CACHE",
                        "AGENTPROV_BASELINE_CORPUS", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "SystemRoot", "TMPDIR",
                        "AGENTPROV_JOB_CPU_BUDGET", "AGENTPROV_JOB_MEM_GIB_BUDGET", "AGENTPROV_SUITE_QUEUE_DIR")
#: allowlist entries the core and ``tools/`` read as paths relative to their own cwd (a job directory, the checkout).
#: ``HOME`` is only made absolute (it is what ``~`` means); the Windows names are left as the OS gave them.
_PATH_ENV: Final = ("AGENTPROV_HOME", "AGENTPROV_UPSTREAM_CACHE", "AGENTPROV_BASELINE_CORPUS",
                    "AGENTPROV_SUITE_QUEUE_DIR", "TMPDIR", "HOME")
_LIMITS: Final = IngestLimits()
_SMALL: Final = 4 * 1024 * 1024
_log = logging.getLogger("agentprov_gui.jobs.manager")


def _start_cwd() -> str | None:
    try:
        return os.getcwd()
    except OSError:
        return None


#: the GUI process's cwd at start: what a relative path variable meant in the shell that started the GUI (GR-50)
_START_CWD: str | None = _start_cwd()


def allowlisted_env(environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """The :data:`ENV_ALLOWLIST` part of ``environ`` (default ``os.environ``): every GUI subprocess gets this, never the
    GUI's whole environment (design §4.2, S8; no ``*_API_KEY``, no ``UV_*``, no ``GIT_*``).

    A path-valued entry (:data:`_PATH_ENV`) is ``~``-expanded and made absolute against the GUI's start cwd, since the
    child's cwd is elsewhere (GR-50): a relative ``AGENTPROV_SUITE_QUEUE_DIR`` would give each queued job a private
    queue. An empty value stays (the core treats it as unset); a relative one is dropped, with a log line, when the
    start cwd is unknown."""
    source = os.environ if environ is None else environ
    env = {k: source[k] for k in ENV_ALLOWLIST if k in source}
    for name in _PATH_ENV:
        value = env.get(name)
        if not value:
            continue
        if name != "HOME":
            value = os.path.expanduser(value)
        if not os.path.isabs(value):
            if _START_CWD is None:
                _log.warning("dropped %s from the child environment: a relative path and no start cwd", name)
                del env[name]
                continue
            value = os.path.join(_START_CWD, value)
        env[name] = os.path.normpath(value)
    return env


class SpawnRefused(Exception):
    """A spawn the GUI refuses before it starts (single writer, global slot, missing CLI). ``reason`` is plain text the
    GUI wrote; it may contain a path the user chose (shown escaped)."""

    def __init__(self, reason: str, code: str) -> None:
        super().__init__(reason)
        self.reason, self.code = reason, code


def new_job_id() -> str:
    """A UUIDv7 (time-ordered) as the job id."""
    return str(uuid.uuid7())


def atomic_write_json(path: Path, obj: Mapping[str, Any]) -> None:
    data = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), indent=None).encode("utf-8")
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data + b"\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def read_json(path: Path, limit: int = _SMALL) -> dict[str, Any] | None:
    """A small JSON document written by the GUI or the CLI, parsed strictly; ``None`` when absent or unusable."""
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


# ----------------------------------------------------------------------------------------------- the CLI
#: where ``pip install --user``, ``pipx`` and Homebrew's Python put ``agentprov`` on macOS and Linux: an app started from
#: the Finder or a desktop menu gets a short PATH without them (D-1030)
USER_BIN_DIRS: Final = ("~/.local/bin", "/opt/homebrew/bin", "/usr/local/bin")
#: Settings › General's "agentprov program" (:func:`set_installed_program`); ``None``: look on PATH
_installed_setting: Path | None = None
#: Settings › General's "agentprov to run" (:func:`set_cli_choice`, D-1130): ``auto`` or ``bundled``
CLI_CHOICES: Final = ("auto", "bundled")
_cli_choice: str = "auto"
#: what the bundle's own agentprov cannot do (no checkout: ``backends/``, ``tools/``, a ``.venv``), said before a start
NEEDS_CHECKOUT: Final = ("Live runs need an AgentPROV checkout (its backends/ projects): set the checkout in Settings › "
                         "General. The app's own copy of agentprov cannot run them.")


def set_installed_program(program: Path | None) -> None:
    """The ``agentprov`` program Settings › General names, used when no checkout is set (D-1030)."""
    global _installed_setting
    _installed_setting = program


def set_cli_choice(choice: str) -> None:
    """Settings › General's "agentprov to run" (D-1130): ``auto`` (the checkout, else an installed agentprov, else the
    app's own) or ``bundled`` (always the app's own, when this app is a bundle)."""
    global _cli_choice
    _cli_choice = choice if choice in CLI_CHOICES else "auto"


def bundled_program(*, frozen: bool | None = None, executable: str | None = None) -> tuple[str, ...]:
    """The bundle's own agentprov (D-1130): this app's executable with ``--cli`` (``agentprov.cli.frozen``), when the
    app is a frozen bundle; empty otherwise (a checkout's or a package's app has no bundled CLI)."""
    if not (bool(getattr(sys, "frozen", False)) if frozen is None else frozen):
        return ()
    exe = Path(os.path.abspath(sys.executable if executable is None else executable))
    return (str(exe), "--cli") if exe.is_file() else ()


def installed_program(program: Path | None = None, environ: Mapping[str, str] | None = None) -> Path | None:
    """The ``agentprov`` that ``pip install agentprov`` installed (D-1030): ``program`` when given (``None`` when it is
    not a file: the named one is never swapped for another), else the first on ``PATH``, then in :data:`USER_BIN_DIRS`.
    The app's own executable is never taken: Windows matches ``agentprov.exe`` to ``AgentPROV.exe``. Nor is the
    Terminal launcher Install Command Line Tool… writes (:func:`is_cli_launcher`, D-1130): it runs this app's own
    agentprov, so it is not a separately installed one (the bundled CLI is :func:`bundled_program`)."""
    if program is not None:
        program = Path(os.path.abspath(program.expanduser()))
        ok = program.is_file() and os.access(program, os.X_OK) and not is_cli_launcher(program)
        return program if ok else None
    path = (os.environ if environ is None else environ).get("PATH", "")
    dirs = [*path.split(os.pathsep), *(() if os.name == "nt" else (os.path.expanduser(d) for d in USER_BIN_DIRS))]
    own = os.path.realpath(sys.executable) if getattr(sys, "frozen", False) else None
    for found in (shutil.which("agentprov", path=d) for d in dirs if d):
        if found is not None and os.path.realpath(found) != own and not is_cli_launcher(Path(found)):
            return Path(os.path.abspath(found))
    return None


#: the second line of the Terminal launcher ``agentprov launcher install`` writes (``agentprov.cli.launcher.MARKER``,
#: mirrored here because the GUI never imports the CLI, D-391; a test pins the two)
LAUNCHER_MARKER: Final = "agentprov-launcher/1"


def is_cli_launcher(path: Path) -> bool:
    """Whether ``path`` is the Terminal launcher of Install Command Line Tool… (D-1130): a regular file, not a link, of
    at most 64 KiB whose second line is ``# agentprov-launcher/1`` (``rem`` on Windows)."""
    try:
        st = path.lstat()
        if not stat.S_ISREG(st.st_mode) or st.st_size > 64 * 1024:
            return False
        with path.open("rb") as fh:
            lines = fh.read(4096).decode("utf-8", "replace").splitlines()
    except OSError:
        return False
    return len(lines) >= 2 and lines[1].strip() in (f"# {LAUNCHER_MARKER}", f"rem {LAUNCHER_MARKER}")


@dataclass(frozen=True, slots=True)
class CliLocator:
    """Which ``agentprov`` a job runs: the configured checkout's ``.venv`` CLI, else ``uv run --locked --project``.
    ``python`` is the interpreter resolved the same way (GR-19): the job queue wrapper and the checkout's tools run with
    it, never with a ``.venv`` path the ``uv run`` fallback does not have. Empty: no interpreter is known.

    Without a checkout it is the ``agentprov`` installed with ``pip install agentprov`` (:func:`installed_program`,
    D-1030), with no interpreter: the checkout's tools and the job queue need a checkout. Without either, in a frozen
    bundle, it is the bundle's own agentprov (:func:`bundled_program`, D-1130: ``AgentPROV --cli``), which a bundle
    update updates with the app; Settings › General can choose it always (``bundled``). It has no checkout either, so
    live runs, the job queue and the checkout's tools are not available with it (:data:`NEEDS_CHECKOUT`)."""

    checkout: Path | None
    program: tuple[str, ...] = ()
    python: tuple[str, ...] = ()
    bundled: bool = False

    @classmethod
    def for_checkout(cls, checkout: Path | None) -> CliLocator:
        own = bundled_program()
        if _cli_choice == "bundled" and own:
            return cls(None, own, (), True)
        if checkout is None:
            found = installed_program(_installed_setting)
            if found is not None:
                return cls(None, (str(found),))
            return cls(None, own, (), bool(own))
        checkout = Path(os.path.abspath(checkout.expanduser()))  # the child's cwd is its job directory (GR-51)
        venv = checkout / ".venv"
        exe = venv / ("Scripts/agentprov.exe" if os.name == "nt" else "bin/agentprov")
        if exe.is_file():
            return cls(checkout, (str(exe),), (str(venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")),))
        uv = shutil.which("uv")
        if uv is not None and (checkout / "pyproject.toml").is_file():
            run = (uv, "run", "--locked", "--project", str(checkout))
            return cls(checkout, (*run, "agentprov"), (*run, "python"))
        return cls(checkout, ())

    @property
    def available(self) -> bool:
        return bool(self.program)

    @property
    def kind(self) -> str:
        """``bundled`` (the app's own, updated with the app), ``checkout``, ``installed`` or ``none``."""
        if not self.program:
            return "none"
        return "bundled" if self.bundled else "checkout" if self.checkout is not None else "installed"

    def describe(self) -> str:
        """Which CLI this is, in words for Settings › General (paths are the user's own; shown escaped)."""
        if self.bundled:
            return ("the app's own agentprov (bundled; updated with the app; live runs, the job queue and the "
                    "checkout's tools need a checkout)")
        if not self.program:
            return ("none: the checkout has no .venv/bin/agentprov, and uv run cannot run it there" if self.checkout
                    is not None else "none: no checkout is set and no agentprov program was found (pip install agentprov)")
        if self.checkout is not None:
            return f"the checkout's CLI ({'uv run' if len(self.program) > 1 else self.program[0]})"
        return f"the installed agentprov ({self.program[0]})"

    def cwd_for(self, argv: Sequence[str]) -> str | None:
        """The working directory of a short call of ``agentprov ARGV``: the checkout for a command that finds the
        repository from its cwd (``run``, ``backends``, ``migrate``, and ``estimate``, which plans through ``run``'s dry
        run: :data:`agentprov.jobs.tiers.REPO_COMMANDS`, M.4),
        as the core's job manager starts such a job; ``None`` (the GUI's own cwd) for every other command. An app
        opened from the Finder runs with cwd ``/``, where ``run --catalogue`` exited 3 with
        ``backend.repository_missing`` and Run Live showed no suites or attacks."""
        if self.checkout is None or not argv or argv[0] not in REPO_COMMANDS:
            return None
        return str(self.checkout)


# ----------------------------------------------------------------------------------------------- jobs
@dataclass(slots=True)
class Job:
    """A job as ``agentprov jobs`` records it (:mod:`agentprov.jobs.record`). ``record`` is ``job.json`` with the
    ``--meta`` facts merged in (a fact never replaces a recorded field); ``stale_lock`` is the GUI's own read."""

    job_id: str
    directory: Path
    record: dict[str, Any]
    state: str = "running"  # running | ended | unobserved
    exit_code: int | None = None
    outcome: str | None = None
    ended_how: str | None = None
    stale_lock: str | None = None  # a corpus path whose lock names this job's (or its CLI child's) dead pid

    @classmethod
    def of(cls, core: Any) -> Job:
        record = {**core.meta, **{k: v for k, v in core.record.items() if v is not None or k not in core.meta}}
        return cls(core.job_id, core.directory, record, core.state, core.exit_code, core.outcome, core.ended_how)

    @property
    def pid(self) -> int | None:
        return _valid_pid(self.record.get("pid"))

    @property
    def argv(self) -> list[str]:
        argv = self.record.get("argv")
        return [str(a) for a in argv] if isinstance(argv, list) else []

    @property
    def command(self) -> str:
        return str(self.record.get("command", ""))

    @property
    def writes(self) -> list[str]:
        w = self.record.get("writes")
        return [str(x) for x in w] if isinstance(w, list) else []

    def file(self, name: str) -> Path:
        return self.directory / name


#: The largest pid a process can have; the core's ``agentprov.io.atomic`` bound (``agentprov.io`` is not allowlisted).
_MAX_PID = 2**32 - 1 if os.name == "nt" else 2**31 - 1


def _valid_pid(pid: object) -> int | None:
    """``pid`` when a process could have it, else ``None``: unknown, never this job's (psutil raises on <= 0, GR-41)."""
    return pid if isinstance(pid, int) and not isinstance(pid, bool) and 0 < pid <= _MAX_PID else None


def _pid_alive(pid: int) -> bool:
    """Whether ``pid`` is alive by the core's ``pid_alive`` rule (``agentprov.io.atomic``, GR-49): an unreaped zombie
    and a pid we may not signal count as alive, and an undecidable probe fails safe as alive."""
    try:
        return bool(psutil.pid_exists(pid))
    except (psutil.Error, OSError):
        return True


def _utc_seconds(stamp: object) -> int | None:
    if not isinstance(stamp, str):
        return None
    try:
        return calendar.timegm(time.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ"))
    except (ValueError, OverflowError):
        return None


def _norm(path: str) -> str:
    """A corpus path normalised for the single-writer rule (``DIR`` and ``DIR.partial`` are one tree)."""
    p = Path(path).expanduser()
    with contextlib.suppress(OSError):
        p = p.resolve()
    name = p.name[: -len(".partial")] if p.name.endswith(".partial") else p.name
    return str(p.with_name(name))


#: ``agentprov: error [jobs.writer.busy]: …``: the CLI's refusal code
_ERROR_CODE = re.compile(r"\[([a-z0-9_.]+)\]")


class JobManager:
    """The GUI's side of ``agentprov jobs`` (D-704): every spawn, stop, kill, drain and prune is a short call of the
    configured checkout's CLI; job state is read from the job files through :mod:`agentprov.jobs.record`."""

    def __init__(self, home: Path, cli: CliLocator, *, environ: Mapping[str, str] | None = None) -> None:
        from agentprov.jobs.record import jobs_dir

        self.home = Path(os.path.abspath(home.expanduser()))  # the child's cwd is its job directory (GR-21)
        self.jobs_dir = jobs_dir(self.home)
        self.cli = cli
        self.environ = dict(os.environ if environ is None else environ)
        self.jobs: dict[str, Job] = {}
        #: Run Live's last good ``run --catalogue`` per (CLI program..., source), for this process only: a reopened
        #: Run Live shows it at once while the 2-second call checks it again (never written to disk)
        self.catalogue_cache: dict[tuple[str, ...], Any] = {}

    # ------------------------------------------------------------------------------------------ the CLI
    def child_env(self) -> dict[str, str]:
        env = allowlisted_env(self.environ)
        env["AGENTPROV_HOME"] = str(self.home)  # the queue budgets are the core's (compute.*_budget; D-704)
        return env

    def call(self, argv: Sequence[str], *, stdin: bytes | None = None, timeout: float | None = 120
             ) -> tuple[int, bytes, bytes]:
        """``agentprov ARGV`` of the configured checkout: exit code, stdout (bounded), stderr tail."""
        if not self.cli.available:
            return 127, b"", b"no CLI"
        try:
            done = subprocess.run(  # noqa: S603 - the configured CLI and a fixed argv
                [*self.cli.program, *argv[:2], "--progress", "off", "--no-colour", *argv[2:]], input=stdin,
                capture_output=True, timeout=timeout, check=False, env=self.child_env(),
                stdin=None if stdin is not None else subprocess.DEVNULL, cwd=self.cli.cwd_for(argv))
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:  # ValueError: a NUL or a lone surrogate
            return 124, b"", type(exc).__name__.encode()
        return done.returncode, done.stdout[: 64 * 1024 * 1024], done.stderr[-8192:]

    @staticmethod
    def _refusal(code: int, err: bytes) -> SpawnRefused:
        text = err.decode("utf-8", "replace").strip()
        lines = [x for x in text.splitlines() if x.strip() and not x.startswith("INFO ")]
        reason = lines[-1] if lines else f"exit {code}"
        m = _ERROR_CODE.search(reason)
        shown = reason[m.end():].lstrip(": ").strip() if m else reason  # "agentprov: error [code]: why" -> "why"
        return SpawnRefused((shown or reason)[:400], m.group(1) if m else f"jobs.exit_{code}")

    # ------------------------------------------------------------------------------------------ spawn
    def spawn(self, spec: JobSpec, *, control_file: bool = False, batch_id: str | None = None,
              extra_record: Mapping[str, Any] | None = None) -> Job:
        """``agentprov jobs start … -- ARGV``. A repository tool (``spec.extra["tool"]``) runs as ``--tool``."""
        if not self.cli.available:
            raise SpawnRefused("No AgentPROV checkout with a CLI is configured (Settings › General).", "gui.cli.missing")
        if "--env-stdin" in spec.argv or "--env-file" in spec.argv:  # S7: refused (D-702: keys come from --keychain)
            raise SpawnRefused("The GUI never passes keys: a live run reads them with --keychain.", "gui.keys.refused")
        # D-1064: where the CLI refuses the job queue, a job's CPU reservation stays a recorded fact
        queue = self.cli.checkout is not None and platform_limits.current().get("job_queue") is None
        argv = job_start_argv(spec, control_file=control_file, batch_id=batch_id, extra_record=extra_record,
                              queue=queue)
        code, out, err = self.call(argv, timeout=60)
        if code in (124, 127) and not out:  # GR-18: the CLI itself could not be run (the reason names no path)
            raise SpawnRefused(f"The job could not be started ({err.decode('ascii', 'replace')[:40]}). Check the "
                               "checkout in Settings › General.", "gui.spawn.failed")
        if code != 0:
            raise self._refusal(code, err)
        try:
            job_id = str(json.loads(out)["job_id"])
        except (ValueError, KeyError, TypeError):
            raise SpawnRefused("agentprov jobs start gave no job id", "gui.spawn.failed") from None
        from agentprov.jobs.record import load_job

        core = load_job(self.jobs_dir / job_id)
        if core is None:
            raise SpawnRefused("the started job cannot be read", "gui.spawn.failed")
        job = Job.of(core)
        self.jobs[job_id] = job
        return job

    # ------------------------------------------------------------------------------------------ observe
    def load_all(self) -> list[Job]:
        return self.refresh()

    def refresh(self) -> list[Job]:
        """Every job of the home, newest first, read from its files (re-attach: jobs started elsewhere included)."""
        from agentprov.jobs.record import list_jobs

        fresh: dict[str, Job] = {}
        for core in list_jobs(self.home):
            job = Job.of(core)
            old = self.jobs.get(job.job_id)
            if old is not None:
                job.record.update({k: v for k, v in old.record.items() if k not in job.record})  # GUI-side notes
            if job.state == "unobserved":
                job.stale_lock = self._stale_lock(job)
            fresh[job.job_id] = job
        self.jobs = fresh
        return list(fresh.values())

    def _stale_lock(self, job: Job) -> str | None:
        """A write target whose stale lock names this job's pid, or a dead pid taken since the job was created.

        Stale is the core's rule (``LockFile._is_stale``, GR-49): a well-formed lock record on this host whose pid no
        live process has. A dead lock started at or after this job's creation is this job's (or a dead later
        writer's): the ``--break-stale-lock`` action is safe for both. The lock is never removed here."""
        created = _utc_seconds(job.record.get("created"))
        for target in job.writes:
            lock = Path(_norm(target) + ".partial") / ".agentprov.lock"
            info = read_json(lock, 64 * 1024)
            if info is None:
                continue
            pid, started = _valid_pid(info.get("pid")), _utc_seconds(info.get("started"))
            if pid is None:
                continue
            if (not isinstance(info.get("command"), str) or not isinstance(info.get("started"), str)
                    or info.get("host") != platform.node() or _pid_alive(pid)):
                continue
            if pid == job.pid or (created is not None and started is not None and started >= created):
                return target
        return None

    # ------------------------------------------------------------------------------------------ control
    def stop(self, job: Job) -> bool:
        """``agentprov jobs stop`` (the control file's stop when the job has one, else one SIGTERM)."""
        return self.call(["jobs", "stop", job.job_id], timeout=30)[0] == 0

    def kill(self, job: Job) -> bool:
        """``agentprov jobs kill --yes`` after the GUI's confirmation: the whole process tree."""
        return self.call(["jobs", "kill", job.job_id, "--yes"], timeout=30)[0] == 0

    def request(self, job: Job, request: str) -> bool:
        """D-394: ``drain`` (``agentprov jobs drain``) or ``stop``, only for a job with a control file."""
        if request not in ("drain", "stop") or not job.record.get("control_file"):
            return False
        return self.call(["jobs", request, job.job_id], timeout=30)[0] == 0

    def resume_spec_argv(self, job: Job) -> list[str]:
        sub = job.record.get("subcommand_argv")
        return [str(a) for a in sub] if isinstance(sub, list) else []

    def retention_candidates(self, keep: int = 200, max_age_days: int = 90) -> list[Job]:
        """``agentprov jobs prune`` without ``--yes``: the ended jobs it would delete (shown for confirmation)."""
        self._prune_args = ["--keep", str(keep), "--max-age-days", str(max_age_days)]
        code, out, _err = self.call(["jobs", "prune", *self._prune_args, "--format", "json"])
        if code != 0:
            return []
        try:
            ids = [str(j["job_id"]) for j in json.loads(out)["jobs"]]
        except (ValueError, KeyError, TypeError):
            return []
        known = {j.job_id: j for j in self.refresh()}
        return [known[i] for i in ids if i in known]

    def delete(self, jobs: Iterable[Job]) -> None:
        """``agentprov jobs prune … --yes`` with the arguments of the confirmed listing."""
        if list(jobs):
            self.call(["jobs", "prune", *getattr(self, "_prune_args", []), "--yes"])
            self.refresh()


def job_start_argv(spec: JobSpec, *, control_file: bool = False, batch_id: str | None = None,
                   extra_record: Mapping[str, Any] | None = None, queue: bool = True) -> list[str]:
    """``jobs start`` for ``spec``: its corpora, slot, notes and facts as options, then ``--`` and its argv. ``queue``:
    a ``queue_cpu`` extra runs through the machine-wide job queue (only with a configured checkout, as before D-704);
    otherwise it is recorded as a fact (a resumed dev-run job keeps it)."""
    extra = dict(spec.extra or {})
    argv = ["jobs", "start", "--format", "json"]
    if spec.label:
        argv += ["--label", spec.label]
    for w in spec.writes:
        argv += ["--writes", w]
    for r in spec.reads:
        argv += ["--reads", r]
    if spec.slot:
        argv += ["--slot", spec.slot]
    if control_file:
        argv.append("--with-control-file")
    cpu = extra.pop("queue_cpu", None)
    if isinstance(cpu, int) and not isinstance(cpu, bool):
        if queue:
            argv += ["--queue-cpu", str(cpu)]
        else:
            extra["queue_cpu"] = cpu
    if extra.pop("progress_level", None) == "steps":
        argv += ["--progress-level", "steps"]
    tool = extra.pop("tool", None)
    if isinstance(tool, str):
        argv += ["--tool", tool]
    for note in spec.notes:
        argv += ["--note", note]
    facts: dict[str, Any] = {k: v for k, v in extra.items() if isinstance(v, str | int | float | bool)}
    facts.update({k: v for k, v in (extra_record or {}).items() if isinstance(v, str | int | float | bool)})
    if spec.conformance_skipped:
        facts["conformance_skipped"] = True
    if spec.release:
        facts["release"] = True
    if batch_id:
        facts["gui_batch_id"] = batch_id
    for key, value in sorted(facts.items()):
        if re.fullmatch(r"[a-z_][a-z0-9_]{0,39}", key):
            argv += ["--meta", f"{key}={json.dumps(value) if not isinstance(value, str) else value}"]
    return [*argv, "--", *spec.argv]


def tail_bytes(path: Path, limit: int = 64 * 1024) -> bytes:
    """The last ``limit`` bytes of a file (stdout.txt, stderr.txt are read at most this much; design §4.1)."""
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - limit))
            return fh.read(limit)
    except OSError:
        return b""


def parse_help_options(text: str) -> frozenset[str]:
    """Long option names in a ``--help`` text (capability detection: ``--control-file``, ``--skip-prov-conformance``)."""
    import re

    return frozenset(re.findall(r"(?<![\w-])(--[a-z][a-z0-9-]+)", text))


def cli_options(cli: CliLocator, words: Sequence[str], timeout: float = 60) -> frozenset[str]:
    """The options ``agentprov <words> --help`` lists (an R0 subprocess; empty when it cannot run)."""
    if not cli.available:
        return frozenset()
    try:
        done = subprocess.run(  # noqa: S603 - fixed argv
            [*cli.program, *words, "--help"], capture_output=True, timeout=timeout, check=False,
            stdin=subprocess.DEVNULL, env=allowlisted_env(),
        )  # fmt: skip
    except (OSError, subprocess.TimeoutExpired):
        return frozenset()
    return parse_help_options(done.stdout.decode("utf-8", "replace"))
