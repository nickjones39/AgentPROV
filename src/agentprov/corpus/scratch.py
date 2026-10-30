"""Private temporary trees on the filesystem of a corpus (perf round 2, item 1a).

A dry run (``derive``/``recompute --dry-run``) and ``verify --level rederive`` write a whole corpus tree into a
temporary directory and hard-link the source's raw objects into it (D-32). A hard link works only within one
filesystem, and ``$AGENTPROV_HOME`` may be a volume of its own (the Mac Studio's, 2026-10-28), so a tree in the
system temporary directory made every raw object be copied and re-hashed instead.

:func:`scratch_tree` creates the directory on the source's filesystem when it can: under ``$AGENTPROV_HOME/tmp``
(default ``~/.agentprov``) or in the system temporary directory, whichever has the source's ``st_dev``. Neither is
inside a corpus. When neither does (a corpus on a third volume), it falls back to the system temporary directory and
the copy path of D-32 applies, with its notice. Where the tree lies changes no output byte.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

__all__ = ["scratch_tree"]


def _home_tmp() -> Path:
    home = Path(os.environ.get("AGENTPROV_HOME") or Path.home() / ".agentprov").expanduser()
    return home / "tmp"


def scratch_tree(prefix: str, near: str | os.PathLike[str]) -> Path:
    """A new private (0700) directory on the filesystem of ``near`` if ``$AGENTPROV_HOME/tmp`` or the system temporary
    directory is on it (in that order), else in the system temporary directory. The caller removes it."""
    try:
        device = os.stat(near).st_dev
    except OSError:
        device = None
    if device is not None:
        for candidate in (_home_tmp(), Path(tempfile.gettempdir())):
            try:
                candidate.mkdir(mode=0o700, parents=True, exist_ok=True)
                if os.stat(candidate).st_dev == device:
                    return Path(tempfile.mkdtemp(prefix=prefix, dir=candidate))
            except OSError:
                continue
    return Path(tempfile.mkdtemp(prefix=prefix))
