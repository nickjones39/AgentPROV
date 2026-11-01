"""``atomic_write_bytes`` with the Windows rename retry (review UC-30), for small state files that other processes read.

Windows refuses to rename over a file another process has open (``WinError 5``, a ``PermissionError``). The job manager,
the GUI, ``jobs list``, ``settings`` and ``prices`` readers hold such a file for microseconds, so the write is retried
for up to about a second. Elsewhere the first error is raised at once. :mod:`agentprov.io.atomic` itself is unchanged
(it is in the ``aer`` stage scope); this module is outside every stage scope.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Final

__all__ = ["REPLACE_PAUSE_S", "REPLACE_RETRIES", "atomic_write_bytes_retrying"]

REPLACE_RETRIES: Final = 50
REPLACE_PAUSE_S: Final = 0.02


def _windows() -> bool:
    return os.name == "nt"


def atomic_write_bytes_retrying(path: Path | str, data: bytes, *, mode: int | None = None,
                                windows: Callable[[], bool] | None = None) -> None:
    """:func:`agentprov.io.atomic.atomic_write_bytes`, retried on a Windows ``PermissionError`` (``windows``: the
    platform test, which the job manager's tests patch)."""
    from agentprov.io import atomic

    windows = windows or _windows
    for attempt in range(REPLACE_RETRIES):
        try:
            if mode is None:
                atomic.atomic_write_bytes(path, data)
            else:
                atomic.atomic_write_bytes(path, data, mode=mode)
            return
        except PermissionError:
            if not windows() or attempt == REPLACE_RETRIES - 1:
                raise
            time.sleep(REPLACE_PAUSE_S)
