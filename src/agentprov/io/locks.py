"""Advisory locks for shared state outside a corpus: the fetch cache, backend environments and live staging (N.1.9 G6a).

A corpus has its own single-writer lock (:class:`agentprov.io.atomic.LockFile`, guard G6). The state that several
commands share outside any corpus had none, so two processes could write one bare repository of the fetch cache at
once, rebuild a backend environment under a running campaign, or leave no way to tell a live staging directory from an
orphan. This module adds two advisory primitives on top of the same ``O_EXCL`` lock record ``{pid, host, command,
started}``:

* :class:`ResourceLock`, exclusive: ``fetch`` (and ``import --fetch``, ``verify --against-pins``) around a write to the
  fetch cache, ``purge --cache``, and ``backends build``.
* :class:`ResourceUse`, shared: one registration file per process in a directory. ``run`` registers as a user of its
  backend environment and of live staging; ``backends build`` refuses while the environment has a live user, and a user
  refuses while the build lock is held.

Both are **bounded**: they never wait, and a lock never outlives its process. A record whose pid is dead on this host is
removed and the operation goes ahead, because every protected operation is idempotent and resumable (a half-fetched bare
repository is fetched again, a half-built environment has no marker and is rebuilt, temporary names carry the pid). A
live holder, a holder on another host (which cannot be checked) and an unparseable record all refuse at once with
:class:`ResourceBusyError` (exit 4), whose message names the resource, the holder's pid, command and start time, and
what to do. Liveness is :func:`agentprov.io.atomic.pid_alive`, which fails safe (an undecidable pid counts as alive).

Writers register first and check second (a user writes its registration, then checks the build lock; the build takes
its lock, then lists the users), so of two racing processes at least one sees the other. No ``fcntl``/``msvcrt``: the
same files work on every host (D-7). Nothing here is part of a corpus or of any stage's code digest.
"""

from __future__ import annotations

import contextlib
import json
import os
import platform
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Final

from agentprov.io.atomic import LockFile, LockHeldError, LockInfo, pid_alive

__all__ = [
    "LOCKS_DIR",
    "ResourceBusyError",
    "ResourceLock",
    "ResourceUse",
    "backend_build_lock",
    "backend_use",
    "backend_build",
    "fetch_cache_lock",
    "held",
    "staging_use",
]

#: Locks of ``$AGENTPROV_HOME`` state live here, never inside the directories they protect (``envs/`` is listed by
#: ``info``, staging directories are scanned as evidence).
LOCKS_DIR: Final = "locks"
FETCH_CACHE_LOCK: Final = ".agentprov.lock"
_USER_NAME = re.compile(r"\A([0-9]{1,10})@([A-Za-z0-9._-]{0,255})\.json\Z")


class ResourceBusyError(LockHeldError):
    """Shared state is in use by another process (N.1.9 G6a). Exit 4, like the corpus lock."""

    code = "io.resource_busy"
    exit_code = 4


def _holder(info: LockInfo | None) -> str:
    if info is None:
        return "an unreadable lock record"
    command = f", command {info.command!r}" if info.command else ""
    return f"pid {info.pid} on {info.host}{command}, since {info.started}"


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class ResourceLock:
    """An exclusive advisory lock on one piece of shared state. Use as a context manager.

    ``what`` names the resource in messages (``"the fetch cache"``). A dead holder on this host is removed (see the
    module docstring); a live, foreign or unreadable one raises :class:`ResourceBusyError`. Re-entrant use is a bug.
    """

    def __init__(self, path: Path | str, *, what: str, command: str = "", host: str | None = None,
                 pid: int | None = None) -> None:
        self.path = Path(path)
        self.what = what
        self._host = platform.node() if host is None else host
        self._lock = LockFile(self.path, command=command, break_stale=True, host=self._host, pid=pid)

    def holder(self) -> LockInfo | None:
        """The live holder, or ``None`` when free (a dead same-host holder counts as free)."""
        info = self._lock.read()
        if info is None:
            return None if not self.path.exists() else LockInfo(-1, "?", "", "?")
        if info.host == self._host and not pid_alive(info.pid):
            return None
        return info

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._lock.acquire()
        except LockHeldError:
            info = self._lock.read()
            raise ResourceBusyError(
                f"{self.what} is in use by {_holder(info)}; wait for that command to finish and run this one again"
                + (f" (if no such process exists, remove {self.path})" if info is None or info.host != self._host else "")
            ) from None

    def release(self) -> None:
        self._lock.release()

    def __enter__(self) -> ResourceLock:
        self.acquire()
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:
        self.release()


class ResourceUse:
    """A shared registration of this process as a user of some state: ``<directory>/<pid>@<host>.json``.

    ``exclusive`` is the :class:`ResourceLock` of whoever must not run at the same time (a build); entering registers
    first, then refuses with :class:`ResourceBusyError` if that lock has a live holder. :meth:`live_users` lists the
    registrations of live processes and removes those of dead ones on this host.
    """

    def __init__(self, directory: Path | str, *, what: str, command: str = "", exclusive: ResourceLock | None = None,
                 host: str | None = None, pid: int | None = None) -> None:
        self.directory = Path(directory)
        self.what = what
        self.command = command
        self.exclusive = exclusive
        self._host = platform.node() if host is None else host
        self._pid = os.getpid() if pid is None else pid
        self._path = self.directory / f"{self._pid}@{_safe_host(self._host)}.json"
        self._held = False

    def live_users(self) -> list[LockInfo]:
        """The registrations of live processes, sorted by pid (dead same-host ones are removed on the way)."""
        users: list[LockInfo] = []
        try:
            names = sorted(os.listdir(self.directory))
        except FileNotFoundError:
            return users
        for name in names:
            if _USER_NAME.fullmatch(name) is None:
                continue
            path = self.directory / name
            try:
                info = LockInfo.parse(path.read_bytes())
            except FileNotFoundError:
                continue
            if info is None:
                users.append(LockInfo(-1, "?", "", "?"))  # unreadable: counted as live, never deleted on a guess
            elif info.host == self._host and not pid_alive(info.pid):
                with contextlib.suppress(FileNotFoundError):
                    path.unlink()
            else:
                users.append(info)
        return sorted(users, key=lambda u: u.pid)

    def acquire(self) -> None:
        if self._held:
            raise ResourceBusyError("this process already registered as a user")
        self.directory.mkdir(parents=True, exist_ok=True)
        record = LockInfo(self._pid, self._host, self.command, _now())
        tmp = self._path.with_name(self._path.name + f".tmp-{self._pid}")
        tmp.write_bytes(json.dumps(record.to_dict(), sort_keys=True).encode("utf-8") + b"\n")
        os.replace(tmp, self._path)
        self._held = True
        if self.exclusive is not None:
            holder = self.exclusive.holder()
            if holder is not None:
                self.release()
                raise ResourceBusyError(
                    f"{self.exclusive.what} is held by {_holder(holder)}, so {self.what} cannot be used now; wait for "
                    "that command to finish and run this one again"
                )

    def release(self) -> None:
        if not self._held:
            return
        self._held = False
        with contextlib.suppress(FileNotFoundError):
            self._path.unlink()

    def __enter__(self) -> ResourceUse:
        self.acquire()
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:
        self.release()


def _safe_host(host: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", host)[:255]


# ------------------------------------------------------------------------------------------------ the shared state
def fetch_cache_lock(cache: Path | str, *, command: str = "") -> ResourceLock:
    """The write lock of a fetch cache: ``<cache>/.agentprov.lock`` (the cache may be shared by several homes)."""
    return ResourceLock(Path(cache) / FETCH_CACHE_LOCK, what=f"the fetch cache {Path(cache).name!r}", command=command)


def backend_build_lock(home: Path | str, env_name: str, *, command: str = "backends build") -> ResourceLock:
    """The build lock of one backend environment: ``$AGENTPROV_HOME/locks/envs/<env_name>.lock``."""
    return ResourceLock(Path(home) / LOCKS_DIR / "envs" / f"{env_name}.lock",
                        what=f"the backend environment {env_name} (being built)", command=command)


def backend_use(home: Path | str, env_name: str, *, command: str = "run") -> ResourceUse:
    """A run's registration as a user of a backend environment; refuses while the environment is being built."""
    return ResourceUse(Path(home) / LOCKS_DIR / "envs" / f"{env_name}.users", what=f"the backend environment {env_name}",
                       command=command, exclusive=backend_build_lock(home, env_name))


@contextlib.contextmanager
def backend_build(home: Path | str, env_name: str) -> Iterator[ResourceLock]:
    """Hold the build lock of a backend environment, refusing (:class:`ResourceBusyError`) while a run uses it."""
    with backend_build_lock(home, env_name) as lock:
        users = backend_use(home, env_name).live_users()
        if users:
            raise ResourceBusyError(
                f"the backend environment {env_name} is in use by {_holder(users[0])}"
                + (f" and {len(users) - 1} other process(es)" if len(users) > 1 else "")
                + "; a rebuild would replace it under a running campaign. Wait for the run to finish and build again"
            )
        yield lock


def staging_use(home: Path | str, *, command: str = "") -> ResourceUse:
    """A registration as a user of live staging (``$AGENTPROV_HOME/staging``, ``t2home``): a staging directory is an
    orphan only when no live user is registered, so a cleanup can refuse while one is."""
    return ResourceUse(Path(home) / LOCKS_DIR / "staging", what="live staging", command=command)


@contextlib.contextmanager
def held(*locks: ResourceLock | ResourceUse) -> Iterator[None]:
    """Enter ``locks`` in order and release them in reverse, also when one refuses."""
    with contextlib.ExitStack() as stack:
        for lock in locks:
            stack.enter_context(lock)
        yield
