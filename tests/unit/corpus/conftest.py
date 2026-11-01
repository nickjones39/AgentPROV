"""Makes the sibling helper modules ``raw_support`` and ``facet_support`` importable (pytest runs with
``--import-mode=importlib``)."""

from __future__ import annotations

import sys
from pathlib import Path

for _here in (str(Path(__file__).resolve().parents[1] / "raw"), str(Path(__file__).resolve().parent)):
    if _here not in sys.path:
        sys.path.insert(0, _here)


import os  # noqa: E402

import pytest  # noqa: E402


@pytest.fixture
def windows_read_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """Windows refuses to delete a read-only file (WinError 5, Access is denied); POSIX deletes it when the directory is
    writable. This makes ``os.unlink`` refuse a file without its owner's write bit, as Windows does (CI round 7)."""
    real = os.unlink

    def unlink(path, *, dir_fd=None):  # type: ignore[no-untyped-def]
        if not os.stat(path, dir_fd=dir_fd, follow_symlinks=False).st_mode & 0o200:
            raise PermissionError(13, "Access is denied", os.fsdecode(path))
        return real(path, dir_fd=dir_fd)

    monkeypatch.setattr(os, "unlink", unlink)
