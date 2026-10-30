"""Windows host checks (G5 note §2.5, P-5). Read-only: the GUI never changes a system setting.

Corpora nest deeply (``<corpus>/aer/…``, the raw store's fan-out, staging), and a path longer than 260 characters fails
on Windows unless long paths are enabled (``HKLM\\SYSTEM\\CurrentControlSet\\Control\\FileSystem\\LongPathsEnabled``).
:func:`long_path_warning` reads that value and returns a warning for the System page when it is off; enabling it is
the user's own system setting.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Final

__all__ = ["LONG_PATHS_WARNING", "long_path_warning", "long_paths_enabled"]

LONG_PATHS_WARNING: Final = ("Windows long paths are off (LongPathsEnabled = 0): a corpus path over 260 characters "
                             "will fail. Keep AGENTPROV_HOME and corpus folders short, or enable long paths in "
                             "Windows (an administrator setting; the GUI never changes it).")


def long_paths_enabled() -> bool | None:
    """The registry value, or ``None`` when it cannot be read (or this is not Windows)."""
    if sys.platform != "win32":
        return None
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\FileSystem") as key:
            value, _kind = winreg.QueryValueEx(key, "LongPathsEnabled")
    except OSError:
        return None
    return bool(value == 1)


def long_path_warning(read: Callable[[], bool | None] = long_paths_enabled) -> str | None:
    """:data:`LONG_PATHS_WARNING` when long paths are known to be off; nothing when on or unknown."""
    return LONG_PATHS_WARNING if read() is False else None
