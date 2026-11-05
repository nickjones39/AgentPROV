"""Sealed corpora are read-only on disk (user approval 2026-11-05).

A sealed corpus is never rewritten (H.1.5(3)), but nothing stopped the operating system writing into it: macOS Finder
creates a ``.DS_Store`` in every folder it opens, and 53 such files made ``verify --level chain`` fail with
``corpus.tree.stray`` on every sealed corpus. ``agentprov package`` therefore removes write permission from the sealed
tree once it is in place (:func:`protect`), which also makes the immutability of a sealed corpus a property of the file
system rather than a convention:

* POSIX: the ``w`` bits of user, group and other are cleared on every file and directory, directories bottom-up and the
  corpus directory last. Nothing can then be created, renamed or deleted in the tree, and no file can be rewritten.
* Windows: the read-only attribute is set on files only. A directory's read-only attribute does not stop anything being
  created in it there (Explorer reads it as "customised folder"), so directories are left alone.

Symbolic links are never followed or changed (a sealed tree has none: the closed world refuses them). A file that
already has no write bit, such as a raw object (``0444`` since the store wrote it, and possibly a hard link shared with
another corpus, D-32), is left untouched. Permissions are not part of any digest: ``checksums.sha256``, the root digest
and every archive entry (fixed ``external_attr``) are computed from bytes and labels only.

:func:`lift` is the deliberate way back for the owner (the shell equivalent is ``chmod -R u+w DIR``): it gives the owner
write permission on every directory and on every file except the stored raw objects, which keep the raw store's
read-only mode. Nothing in AgentPROV writes into a sealed corpus, so nothing here lifts the protection; copies made from
a sealed corpus (``derive``/``recompute --out``, ``verify --level rederive``, ``package --deposit``) write new files and
are writable. :func:`agentprov.io.remove.rmtree` deletes a protected tree. This module is outside every stage scope.
"""

from __future__ import annotations

import os
import stat

__all__ = ["is_protected", "lift", "protect"]

_WRITE_BITS = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
_WINDOWS = os.name == "nt"


def _mode(path: str) -> int | None:
    """The permission bits of ``path`` itself, or ``None`` for a link (never followed or changed) or a vanished entry."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(st.st_mode) or os.path.isjunction(path):
        return None
    return stat.S_IMODE(st.st_mode)


def _clear_write(path: str) -> None:
    mode = _mode(path)
    if mode is not None and mode & _WRITE_BITS:
        os.chmod(path, mode & ~_WRITE_BITS)


def protect(root: str | os.PathLike[str]) -> None:
    """Remove write permission from the tree at ``root`` (see the module docstring): every file, then (POSIX only) every
    directory bottom-up, ``root`` last. Raises ``OSError`` when a change is refused."""
    top = os.fspath(root)
    for directory, _dirs, files in os.walk(top, topdown=False, followlinks=False):
        for name in files:
            _clear_write(os.path.join(directory, name))
        if not _WINDOWS:
            _clear_write(directory)  # its entries were done first; os.walk yields `top` last


def lift(root: str | os.PathLike[str]) -> None:
    """Give the owner write permission back on the tree at ``root``: every directory and every file except the stored
    raw objects under ``raw/objects/`` (read-only by the raw store's contract, and possibly shared by hard link)."""
    top = os.fspath(root)
    objects = os.path.join(top, "raw", "objects")
    for directory, _dirs, files in os.walk(top, topdown=True, followlinks=False):
        mode = _mode(directory)
        if not _WINDOWS and mode is not None and not mode & stat.S_IWUSR:
            os.chmod(directory, mode | stat.S_IWUSR)
        if os.path.commonpath([objects, directory]) == objects:
            continue
        for name in files:
            path = os.path.join(directory, name)
            mode = _mode(path)
            if mode is not None and not mode & stat.S_IWUSR:
                os.chmod(path, mode | stat.S_IWUSR)


def is_protected(root: str | os.PathLike[str]) -> bool:
    """Whether no file below ``root`` and (POSIX) no directory, ``root`` included, has a write bit; links are skipped."""
    top = os.fspath(root)
    for directory, _dirs, files in os.walk(top, followlinks=False):
        paths = [os.path.join(directory, name) for name in files]
        for path in paths if _WINDOWS else [directory, *paths]:
            mode = _mode(path)
            if mode is not None and mode & _WRITE_BITS:
                return False
    return True
