"""``fs_guard``: snapshot a directory tree and fail if anything in it changed (docs/architecture K.3.2; MN N.1.6, G2).

Used for "a dry run writes nothing", "a consumer never writes into a corpus" and "``derive``/``recompute`` leave the
source corpus unchanged" (PLAN rule 4). A snapshot records, for every entry below the root (the root included), without
following a link:

* its kind (``dir``, ``file``, ``link``, ``other``), permission bits, inode and device, and modification time (ns);
* for a file, its size and sha256; for a link, its target text (the link is never followed).

Directory modification times are recorded too, so a file that was created and deleted again is still caught. Access
times are not (reading changes them), and neither are ``ctime`` and the link count (a ``recompute --link-raw`` hard link
to a source object changes them but no byte or name of the source, D-32).

    with fs_guard.unchanged(corpus_root):
        run_the_command()

raises :class:`FsGuardError` (an ``AssertionError``) listing at most 20 changed labels when the tree differs afterwards.
Labels are escaped before they are shown (R-42): a tree under test may hold names taken from fixtures.
"""

from __future__ import annotations

import hashlib
import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.paths import open_evidence
from agentprov.ingest.quote import escape_untrusted

__all__ = ["Entry", "FsGuardError", "TreeSnapshot", "assert_unchanged", "diff", "snapshot", "unchanged"]

_CHUNK: Final = 1 << 20
#: The guard hashes whole trees (raw stores included): no artefact size cap, only the no-follow open.
_LIMITS: Final = IngestLimits(max_artefact_bytes=1 << 50)
_SHOWN: Final = 20


class FsGuardError(AssertionError):
    """A guarded tree changed."""


@dataclass(frozen=True, slots=True)
class Entry:
    """One entry of a snapshot (see the module docstring for what is compared)."""

    kind: str  # dir | file | link | other
    mode: int
    inode: int
    device: int
    mtime_ns: int
    size: int | None = None
    sha256: str | None = None
    target: str | None = None


@dataclass(frozen=True, slots=True)
class TreeSnapshot:
    """Every entry below ``root`` by ``/``-joined label (``""`` is the root itself)."""

    root: Path
    entries: dict[str, Entry]


def _hash(path: str) -> str:
    digest = hashlib.sha256()
    parent, name = os.path.split(path)
    with open_evidence(parent, name, _LIMITS, allow_hardlinks=True) as stream:  # the one no-follow opener (D-7, G.3.10)
        while chunk := stream.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _entry(path: str) -> Entry:
    st = os.lstat(path)
    common = (stat.S_IMODE(st.st_mode), st.st_ino, st.st_dev, st.st_mtime_ns)
    if stat.S_ISLNK(st.st_mode):
        return Entry("link", *common, target=os.readlink(path))
    if stat.S_ISDIR(st.st_mode):
        return Entry("dir", *common)
    if stat.S_ISREG(st.st_mode):
        return Entry("file", *common, size=st.st_size, sha256=_hash(path))
    return Entry("other", *common)


def _walk(root: str) -> Iterator[tuple[str, str]]:
    """``(label, path)`` of every entry below ``root``, iteratively, never descending through a link."""
    pending: list[tuple[str, str]] = [("", root)]
    while pending:
        label, path = pending.pop()
        yield label, path
        st = os.lstat(path)
        if stat.S_ISDIR(st.st_mode):
            with os.scandir(path) as it:
                names = sorted(e.name for e in it)
            for name in reversed(names):
                pending.append((f"{label}/{name}" if label else name, os.path.join(path, name)))


def snapshot(root: str | os.PathLike[str]) -> TreeSnapshot:
    """Snapshot the tree at ``root`` (which must exist). Nothing is written; no link is followed."""
    resolved = os.path.realpath(root)
    return TreeSnapshot(Path(resolved), {label: _entry(path) for label, path in _walk(resolved)})


def diff(before: TreeSnapshot, after: TreeSnapshot) -> list[str]:
    """Human-readable differences (``added``, ``removed``, ``changed <fields>``), sorted by label; ``[]`` when equal."""
    out: list[str] = []
    for label in sorted(before.entries.keys() | after.entries.keys()):
        old, new = before.entries.get(label), after.entries.get(label)
        shown = escape_untrusted(label or ".", max_chars=120)
        if old is None:
            out.append(f"added {shown}")
        elif new is None:
            out.append(f"removed {shown}")
        elif old != new:
            fields = [name for name in Entry.__slots__ if getattr(old, name) != getattr(new, name)]
            out.append(f"changed {shown} ({', '.join(fields)})")
    return out


def assert_unchanged(before: TreeSnapshot, after: TreeSnapshot) -> None:
    """Raise :class:`FsGuardError` when the two snapshots differ."""
    changes = diff(before, after)
    if changes:
        more = f"\n... and {len(changes) - _SHOWN} more" if len(changes) > _SHOWN else ""
        raise FsGuardError(f"{len(changes)} change(s) under the guarded tree:\n" + "\n".join(changes[:_SHOWN]) + more)


@contextmanager
def unchanged(root: str | os.PathLike[str]) -> Iterator[TreeSnapshot]:
    """Snapshot ``root``, run the block, snapshot again and fail on any difference. Yields the first snapshot."""
    before = snapshot(root)
    yield before
    assert_unchanged(before, snapshot(root))
