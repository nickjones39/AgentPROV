"""Atomic file and directory writes, the single-writer lock and the stale-temporary sweep.

Docs: MN M.1.2 (``io/atomic.py``), N.1.9 guards G6 (one writer) and G9 (atomicity), N.1.10, HL H.1.5.

* ``atomic_write_bytes`` / ``atomic_write_text``: write beside the target as ``<name>.tmp-<pid>``, ``fsync`` the
  file, ``os.replace`` it over the target, ``fsync`` the directory. A reader (or a resume after a kill) sees the
  old file or the whole new one, never a truncated one (baseline CAP-16, ``transcript.atomic_write_text``).
* ``atomic_swap_dir``: ``DIR.partial/`` to ``DIR/`` with a refusal (exit 4) when ``DIR`` already exists.
* ``LockFile``: ``<corpus>.partial/.agentprov.lock`` created with ``O_CREAT|O_EXCL`` (no ``fcntl``/``msvcrt``) holding ``{pid, host, command,
  started}``; a live lock refuses; a stale lock (dead pid, same host) is removed only on request.
* ``sweep_stale_tmp``: leftover ``*.tmp-<pid>`` files of dead pids are removed at start (G9).

Host independence: no ``sys.platform`` branches. Files are opened with ``O_BINARY`` where it exists and
written as bytes, so output is identical everywhere (never ``os.linesep`` or a locale encoding); directory
``fsync`` is skipped where directories cannot be opened; process liveness uses the one private probe
``_pid_alive_native`` and fails safe.

Nothing here depends on the clock for any *output* that is hashed: the lock file's ``started`` value is a
transient diagnostic, never part of a corpus.
"""

from __future__ import annotations

import contextlib
import errno
import json
import os
import re
import platform
import stat
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Final

from agentprov.errors import AgentProvError

__all__ = [
    "DestinationExistsError",
    "LockFile",
    "LockHeldError",
    "LockInfo",
    "atomic_swap_dir",
    "atomic_write_bytes",
    "atomic_write_text",
    "pid_alive",
    "suffixed",
    "sweep_stale_tmp",
    "tmp_path_for",
]

TMP_INFIX: Final = ".tmp-"
LOCK_NAME: Final = ".agentprov.lock"
_TMP_RE = re.compile(r"\.tmp-([0-9]{1,19})\Z")  # ASCII digits, no trailing newline, never a 4,301-digit int()
#: The largest pid the OS calls can take (``pid_t`` is a C ``int``; Windows pids are a ``DWORD``).
_MAX_PID: Final = 2**32 - 1 if os.name == "nt" else 2**31 - 1


class DestinationExistsError(AgentProvError):
    """The destination of an atomic directory swap already exists (guard refusal, exit 4; N.2.11 step 4)."""

    code = "io.destination_exists"
    exit_code = 4


class LockHeldError(AgentProvError):
    """A live (or unverifiable) lock is held: one writer per tree (guard G6, exit 4)."""

    code = "io.lock_held"
    exit_code = 4


def suffixed(path: Path, suffix: str) -> Path:
    """``path`` with ``suffix`` appended to its *name*.

    ``Path.with_suffix`` would replace a dotted tail (``a.b`` + ``.json`` -> ``a.json``), merging two traces'
    files (baseline CAP-16).
    """
    return path.with_name(path.name + suffix)


def tmp_path_for(path: Path, pid: int | None = None) -> Path:
    """The sibling temporary name used while writing ``path``: ``<name>.tmp-<pid>``."""
    return path.with_name(f"{path.name}{TMP_INFIX}{os.getpid() if pid is None else pid}")


def _pid_alive_native(pid: int) -> bool | None:
    """Platform probe behind :func:`pid_alive`: ``True``/``False``, or ``None`` when liveness cannot be decided.

    ``os.kill(pid, 0)`` is a harmless existence probe where signals exist, but on a host without POSIX signals
    (``os.name == "nt"``) it would *terminate* the process, so there the Win32 API is asked through ``ctypes``
    when that is available. Any host where neither probe works answers ``None``.
    """
    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except OSError as exc:
            return False if exc.errno == errno.ESRCH else None
        return True
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            last_error = getattr(ctypes, "get_last_error", lambda: 0)()  # exists on Windows only
            return None if last_error == 5 else False  # 5: access denied, so the process exists but its state is unknown
        try:
            code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return None
            return code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    except ImportError, AttributeError, OSError:
        return None


def pid_alive(pid: int) -> bool:
    """Whether ``pid`` is a live process on this host.

    Fails safe: when liveness cannot be determined the process is reported alive, so a lock is never broken
    and a temporary file never swept on a guess.
    """
    if pid <= 0:
        return False
    if pid > _MAX_PID:  # no process can have it, but the probe would raise OverflowError: undecided, so alive
        return True
    return _pid_alive_native(pid) is not False


#: ``os.open`` flags every writer needs: binary mode where the OS distinguishes it (``O_BINARY``, absent
#: elsewhere), so bytes are never newline-translated, and close-on-exec where available.
_OPEN_EXTRA = getattr(os, "O_BINARY", 0) | getattr(os, "O_CLOEXEC", 0)


def _fsync_dir(directory: Path) -> None:
    """Persist a directory entry change; a host that cannot open or sync directories skips it (feature test)."""
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:  # pragma: no cover - e.g. Windows
        return
    try:
        os.fsync(fd)
    except OSError:  # pragma: no cover - some filesystems refuse directory fsync
        pass
    finally:
        os.close(fd)


def atomic_write_bytes(path: Path | str, data: bytes, *, mode: int | None = None) -> None:
    """Write ``data`` to ``path`` atomically: temporary sibling, ``fsync``, rename, directory ``fsync``.

    ``mode`` sets the permission bits of the new file (default: ``0o666`` filtered by the umask, like ``open``).
    On any failure the temporary file is removed and the target is left untouched.
    """
    target = Path(path)
    tmp = tmp_path_for(target)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | _OPEN_EXTRA
    fd = os.open(tmp, flags, 0o666 if mode is None else mode)
    try:
        try:
            view = memoryview(data)
            while view:
                written = os.write(fd, view)
                view = view[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
        if mode is not None:
            os.chmod(tmp, mode)  # path-based: portable (os.fchmod does not exist everywhere)
        os.replace(tmp, target)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            tmp.unlink()
        raise
    _fsync_dir(target.parent)


def atomic_write_text(
    path: Path | str, text: str, *, encoding: str = "utf-8", mode: int | None = None
) -> None:
    """:func:`atomic_write_bytes` of ``text`` encoded without newline translation."""
    atomic_write_bytes(path, text.encode(encoding), mode=mode)


def atomic_swap_dir(src: Path | str, dst: Path | str) -> None:
    """Rename the working tree ``src`` (``DIR.partial``) to ``dst`` (``DIR``).

    ``dst`` must not exist (:class:`DestinationExistsError`, exit 4); ``src`` must be a directory. The rename is
    a single ``rename(2)`` on one filesystem, so a crash leaves either the working tree or the finished one.
    A race that creates an *empty* ``dst`` between the check and the rename is outside the guarantee (POSIX
    ``rename`` replaces an empty directory); writers hold the tree lock (:class:`LockFile`).
    """
    source, dest = Path(src), Path(dst)
    if not source.is_dir() or source.is_symlink():
        raise NotADirectoryError("swap source is not a directory")
    if os.path.lexists(dest):
        raise DestinationExistsError("swap destination already exists")
    try:
        os.rename(source, dest)
    except FileExistsError as exc:
        raise DestinationExistsError("swap destination already exists") from exc
    except OSError as exc:
        if exc.errno in (errno.EEXIST, errno.ENOTEMPTY):
            raise DestinationExistsError("swap destination already exists") from exc
        raise
    _fsync_dir(dest.parent)
    if source.parent != dest.parent:
        _fsync_dir(source.parent)


class LockInfo:
    """The content of a lock file: ``{pid, host, command, started}`` (N.1.9 G6)."""

    __slots__ = ("command", "host", "pid", "started")

    def __init__(self, pid: int, host: str, command: str, started: str) -> None:
        self.pid = pid
        self.host = host
        self.command = command
        self.started = started

    def to_dict(self) -> dict[str, object]:
        return {"command": self.command, "host": self.host, "pid": self.pid, "started": self.started}

    @classmethod
    def parse(cls, raw: bytes) -> LockInfo | None:
        """Parse lock bytes; ``None`` when they are not a well-formed lock record."""
        try:
            doc = json.loads(raw.decode("utf-8"))
        except UnicodeDecodeError, ValueError:
            return None
        if not isinstance(doc, dict):
            return None
        pid, host, command, started = (doc.get(k) for k in ("pid", "host", "command", "started"))
        if (
            not isinstance(pid, int)
            or isinstance(pid, bool)
            or not isinstance(host, str)
            or not isinstance(command, str)
            or not isinstance(started, str)
        ):
            return None
        return cls(pid, host, command, started)


#: The suffix of a lock's break token (see :meth:`LockFile._break`).
BREAK_SUFFIX: Final = ".break"


class LockFile:
    """Exclusive single-writer lock, created with ``O_EXCL`` (guard G6).

    * A live lock (or one held on another host, which cannot be verified) raises :class:`LockHeldError`.
    * A stale lock (same host, dead pid) raises too, unless ``break_stale=True`` (``--break-stale-lock``), in
      which case it is removed and re-created.
    * An unparseable lock file is treated as held (never silently deleted).

    Use as a context manager, or call :meth:`acquire` / :meth:`release`. The lock is removed on release only if
    it still names this process.
    """

    def __init__(
        self,
        path: Path | str,
        *,
        command: str = "",
        break_stale: bool = False,
        host: str | None = None,
        pid: int | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.path = Path(path)
        self.command = command
        self.break_stale = break_stale
        self._host = platform.node() if host is None else host
        self._pid = os.getpid() if pid is None else pid
        self._clock = clock or (lambda: datetime.now(UTC))
        self._held = False

    @property
    def held(self) -> bool:
        return self._held

    def read(self) -> LockInfo | None:
        """The current lock record on disk, or ``None`` when absent or malformed."""
        try:
            return LockInfo.parse(self.path.read_bytes())
        except FileNotFoundError:
            return None

    def _is_stale(self, info: LockInfo | None) -> bool:
        return info is not None and info.host == self._host and not pid_alive(info.pid)

    def acquire(self) -> None:
        if self._held:
            raise LockHeldError("lock already held by this object")
        for _attempt in range(2):
            try:
                fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _OPEN_EXTRA, 0o644)
            except FileExistsError:
                info = self.read()
                if self._is_stale(info) and self.break_stale:
                    self._break(info)
                    continue
                if self._is_stale(info):
                    raise LockHeldError(
                        "stale lock present (dead pid on this host); use --break-stale-lock"
                    ) from None
                raise LockHeldError("lock held by another writer") from None
            record = LockInfo(
                self._pid, self._host, self.command, self._clock().strftime("%Y-%m-%dT%H:%M:%SZ")
            )
            payload = json.dumps(record.to_dict(), sort_keys=True).encode("utf-8") + b"\n"
            try:
                os.write(fd, payload)
                os.fsync(fd)
            except BaseException:
                os.close(fd)
                with contextlib.suppress(FileNotFoundError):
                    self.path.unlink()
                raise
            os.close(fd)
            self._held = True
            return
        raise LockHeldError("lock could not be acquired")  # pragma: no cover - lost a break/recreate race

    @property
    def break_token(self) -> Path:
        """The sibling ``<lock>.break``: held (``O_EXCL``) by the one process breaking a stale lock."""
        return self.path.with_name(self.path.name + BREAK_SUFFIX)

    def _break(self, seen: LockInfo | None) -> None:
        """Remove the stale lock ``seen`` atomically with respect to other breakers (pre-round review D #6).

        Reading the record and unlinking the path were two steps: a second breaker could unlink the live lock a first
        one had just created, and both then held it. Breakers now take the break token with ``O_EXCL`` first and then
        unlink only if the path still holds the same dead record. Only a breaker removes a dead owner's record and only
        one breaker runs at a time, so the record cannot change between that check and the unlink. A token left by a
        breaker that died within those few system calls is never broken automatically: the lock is refused and the
        message names the token.
        """
        try:
            fd = os.open(self.break_token, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _OPEN_EXTRA, 0o644)
        except FileExistsError:
            raise LockHeldError(
                f"another process is breaking this stale lock (if none is, remove {self.break_token.name})"
            ) from None
        try:
            with contextlib.suppress(OSError):
                os.write(fd, f"{self._pid} {self._host}\n".encode())
            os.close(fd)
            now = self.read()
            if now is not None and seen is not None and now.to_dict() == seen.to_dict():  # still the same dead record
                with contextlib.suppress(FileNotFoundError):
                    self.path.unlink()
        finally:
            with contextlib.suppress(FileNotFoundError):
                self.break_token.unlink()

    def release(self) -> None:
        if not self._held:
            return
        self._held = False
        info = self.read()
        if info is not None and info.pid == self._pid and info.host == self._host:
            with contextlib.suppress(FileNotFoundError):
                self.path.unlink()

    def __enter__(self) -> LockFile:
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.release()


def _walk_files(root: Path, recursive: bool) -> Iterator[Path]:
    """Regular files under ``root`` in sorted order; symbolic links are never followed or yielded."""
    try:
        entries = sorted(os.scandir(root), key=lambda e: e.name)
    except FileNotFoundError:
        return
    for entry in entries:
        try:
            st = entry.stat(follow_symlinks=False)
        except OSError:
            continue
        if stat.S_ISREG(st.st_mode):
            yield Path(entry.path)
        elif recursive and stat.S_ISDIR(st.st_mode):
            yield from _walk_files(Path(entry.path), recursive)


def sweep_stale_tmp(directory: Path | str, *, recursive: bool = False, dry_run: bool = False) -> list[Path]:
    """Remove leftover ``*.tmp-<pid>`` regular files whose pid is dead; return them (sorted).

    Files of a live pid (including this process) are kept. ``dry_run=True`` removes nothing and returns what
    would be removed (N.1.6: dry runs write nothing). The pid test is host-local; run the sweep from the one
    host that writes the tree (guard G6).
    """
    removed: list[Path] = []
    for file in _walk_files(Path(directory), recursive):
        match = _TMP_RE.search(file.name)
        if match is None or pid_alive(int(match.group(1))):
            continue
        if not dry_run:
            with contextlib.suppress(FileNotFoundError):
                file.unlink()
        removed.append(file)
    return removed
