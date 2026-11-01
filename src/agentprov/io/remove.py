"""Deleting files of AgentPROV's own stores on every host (D-1011, CI round 7).

The raw store makes every object read-only (``0444``). POSIX deletes such a file when its directory is writable; Windows
refuses (``WinError 5``, a ``PermissionError``), so a scratch tree, a purged object or a withhold scan's store stayed
behind there. On Windows a refused file is deleted with ``FILE_DISPOSITION_FLAG_IGNORE_READONLY_ATTRIBUTE`` (Windows 10
1809 and later), which leaves the read-only attribute alone: a scratch tree hard-links the source corpus's objects, and
that attribute belongs to the file, so clearing it would make the source's object writable too. Only where that call
is refused is the bit cleared and the removal retried. On POSIX the first attempt succeeds and nothing changes. This
module is outside every stage scope.
"""

from __future__ import annotations

import os
import shutil
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
        os.chmod(path, 0o600)
        os.unlink(path)


def rmtree(path: str | os.PathLike[str] | Path, *, ignore_errors: bool = False) -> None:
    """``shutil.rmtree`` that deletes read-only files as :func:`unlink` does; ``ignore_errors`` skips what still fails
    and goes on with the rest, as ``shutil.rmtree(..., ignore_errors=True)`` does."""

    def retry(function: Callable[[str], object], name: str, _exc: BaseException) -> None:
        try:
            if function in (os.unlink, os.remove):
                unlink(name)
            else:
                os.chmod(name, 0o700)
                function(name)
        except OSError:
            if not ignore_errors:
                raise

    shutil.rmtree(path, onexc=retry)
