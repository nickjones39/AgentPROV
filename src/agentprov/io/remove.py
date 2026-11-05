"""Deleting files of AgentPROV's own stores on every host (D-1011, CI round 7).

The raw store makes every object read-only (``0444``). POSIX deletes such a file when its directory is writable; Windows
refuses (``WinError 5``, a ``PermissionError``), so a scratch tree, a purged object or a withhold scan's store stayed
behind there. On Windows a refused file is deleted with ``FILE_DISPOSITION_FLAG_IGNORE_READONLY_ATTRIBUTE`` (Windows 10
1809 and later), which leaves the read-only attribute alone: a scratch tree hard-links the source corpus's objects, and
that attribute belongs to the file, so clearing it would make the source's object writable too. Only where that call
is refused, and only for a file without its write bit, is the bit cleared and the removal retried; when the retry
fails too the mode is put back. On POSIX the first attempt succeeds and nothing changes, except in a directory without its
owner's write bit (a sealed corpus, :mod:`agentprov.corpus.protect`): :func:`rmtree` gives that directory, which it is
removing anyway, the bit back before it retries. This module is outside every stage scope.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import stat
import sys
from collections.abc import Callable
from pathlib import Path

__all__ = ["rmtree", "unlink"]

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _KERNEL32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                      wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    _KERNEL32.CreateFileW.restype = wintypes.HANDLE
    _KERNEL32.SetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
    _KERNEL32.SetFileInformationByHandle.restype = wintypes.BOOL
    _KERNEL32.CloseHandle.argtypes = [wintypes.HANDLE]
    _KERNEL32.CloseHandle.restype = wintypes.BOOL
    _INVALID_HANDLE = wintypes.HANDLE(-1).value
    _DELETE = 0x00010000
    _SHARE_ALL = 0x7  # read, write, delete
    _OPEN_EXISTING = 3
    _OPEN_REPARSE_POINT = 0x00200000  # a link itself, never its target
    _FILE_DISPOSITION_INFO_EX = 21
    _DELETE_POSIX_IGNORING_READ_ONLY = 0x1 | 0x2 | 0x10  # DELETE, POSIX_SEMANTICS, IGNORE_READONLY_ATTRIBUTE

    class _DispositionEx(ctypes.Structure):
        _fields_ = [("Flags", wintypes.DWORD)]

    def _delete_ignoring_read_only(path: str) -> bool:
        handle = _KERNEL32.CreateFileW(os.path.abspath(path), _DELETE, _SHARE_ALL, None, _OPEN_EXISTING,
                                       _OPEN_REPARSE_POINT, None)
        if handle in (None, _INVALID_HANDLE):
            return False
        try:
            info = _DispositionEx(_DELETE_POSIX_IGNORING_READ_ONLY)
            return bool(_KERNEL32.SetFileInformationByHandle(handle, _FILE_DISPOSITION_INFO_EX, ctypes.byref(info),
                                                             ctypes.sizeof(info)))
        finally:
            _KERNEL32.CloseHandle(handle)

else:

    def _delete_ignoring_read_only(path: str) -> bool:
        return False


def unlink(path: str | os.PathLike[str]) -> None:
    """``os.unlink`` of a file the host may refuse to delete because it is read-only (see the module docstring)."""
    try:
        os.unlink(path)
    except PermissionError:
        if _delete_ignoring_read_only(os.fspath(path)):
            return
        mode = os.lstat(path).st_mode
        if stat.S_ISLNK(mode) or mode & stat.S_IWUSR:
            raise  # not the read-only bit: clearing it would not help, and the inode may be shared
        os.chmod(path, 0o600)
        try:
            os.unlink(path)
        except OSError:
            with contextlib.suppress(OSError):
                os.chmod(path, stat.S_IMODE(mode))  # still there: a hard-linked source object stays read-only
            raise


def rmtree(path: str | os.PathLike[str] | Path, *, ignore_errors: bool = False) -> None:
    """``shutil.rmtree`` that deletes read-only files as :func:`unlink` does; ``ignore_errors`` skips what still fails
    and goes on with the rest, as ``shutil.rmtree(..., ignore_errors=True)`` does."""

    def retry(function: Callable[..., object], name: str, exc: BaseException) -> None:
        """Retries only a refused file deletion or a refused removal of a read-only directory (never a link's); any
        other failure (a symlink root, a directory that cannot be opened) is shutil.rmtree's own and stays so."""
        try:
            if function in (os.unlink, os.remove, os.rmdir) and isinstance(exc, PermissionError):
                _open_parent(name, top)
            if function in (os.unlink, os.remove):
                unlink(name)
            elif function is os.rmdir and isinstance(exc, PermissionError) and _real_directory(name):
                os.chmod(name, 0o700)
                os.rmdir(name)
            else:
                raise exc
        except OSError:
            if not ignore_errors:
                raise

    top = os.path.abspath(path)
    shutil.rmtree(path, onexc=retry)


def _open_parent(name: str, top: str) -> None:
    """POSIX: an entry of a directory without its owner's write bit (a sealed corpus is read-only,
    :mod:`agentprov.corpus.protect`) is removed only once the directory has it. Only a directory of the tree being
    removed (``top`` or below) is changed, never one above it; nor is a file's own mode (it may be a hard link shared
    with another tree)."""
    parent = os.path.dirname(os.path.abspath(name))
    if sys.platform == "win32" or os.path.commonpath([top, parent]) != top or not _real_directory(parent):
        return
    mode = stat.S_IMODE(os.lstat(parent).st_mode)
    if not mode & stat.S_IWUSR:
        os.chmod(parent, mode | stat.S_IRWXU)


def _real_directory(name: str) -> bool:
    try:
        return stat.S_ISDIR(os.lstat(name).st_mode) and not os.path.isjunction(name)
    except OSError:
        return False
