"""Local input trees and live staging directories, opened safely (docs/architecture G.3.6; SEC-10).

``--input DIR``, a live session's staging directory (G.6.3) and a downloaded deposit tree (G.5.7) are untrusted. This module
never follows a symlink below the user-given root, and never decides anything from a path string:

* :func:`open_root` resolves the user-given root once (``os.path.realpath``), records it, and (with the ``native``
  mechanism) opens it as a directory descriptor. Everything below it is addressed relative to descriptors (``dir_fd``).
* :func:`discover` walks the tree iteratively with ``os.scandir`` on directory descriptors, using
  ``follow_symlinks=False`` everywhere. A symlink, a special file or a hardlinked file is not listed: it becomes a
  :class:`PathRejection` with its ``ingest.path.*`` code. ``.DS_Store`` and AppleDouble ``._*`` files are skipped.
* :func:`open_evidence` opens one file by label, component by component, with ``O_NOFOLLOW`` (and ``O_NOFOLLOW_ANY`` where
  the platform has it, which refuses a link in **any** component). It then ``fstat``s the descriptor and requires a regular
  file (``S_ISREG``) with ``st_nlink == 1`` (unless hardlinks are allowed, never for a staging directory), and returns a
  binary file object over that descriptor. ``O_NONBLOCK`` keeps a FIFO from hanging the importer.

**Two no-follow mechanisms, one decision.** :func:`_probe` feature-tests the host once and selects:

``native``           ``O_NOFOLLOW`` (``O_NOFOLLOW_ANY`` where it exists) and a ``dir_fd`` component walk, as above;
``verify_identity``  for hosts without ``O_NOFOLLOW`` or ``dir_fd`` (Windows): ``os.lstat`` every component and the leaf,
                     reject a symbolic link or (where ``st_file_attributes`` exists) a reparse point, open with
                     ``O_RDONLY | O_BINARY``, then ``fstat`` the descriptor and require a regular file and the same
                     ``(st_dev, st_ino)`` as the pre-open ``lstat``. A mismatch is a link or a race.

``ingest.path.unsupported_platform`` is raised only when neither mechanism is available. The selection is exposed as the
``nofollow`` host capability (``agentprov.host``) and every open of evidence or store objects goes through
:func:`open_evidence`: no other module names ``O_NOFOLLOW`` (a static test enforces it).

String-prefix and lexical checks are never used to decide containment. Labels are validated with
:func:`agentprov.ingest.names.logical_name` in its non-portable mode (POSIX names such as ``a:b`` are legitimate in a local
tree). The checks done by :func:`discover` are advisory (the tree can change); :func:`open_evidence` is authoritative.
"""

from __future__ import annotations

import errno
import functools
import os
import stat
import unicodedata
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from typing import IO, Any, Final

from agentprov.errors import IngestError, IngestSafetyError
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.names import collision_key, logical_name



#: Limits for re-opening bytes that were already admitted under their own limits (the raw store, a worker's store input):
#: reading must not impose a smaller cap than writing did.
STORED_OBJECT_LIMITS: Final = IngestLimits().replace(max_artefact_bytes=1 << 62)

NATIVE: Final = "native"
VERIFY_IDENTITY: Final = "verify_identity"


@dataclass(frozen=True, slots=True)
class _Primitives:
    """The host primitives this module relies on, read once by :func:`_probe` (the only platform-dependent code here)."""

    mechanism: str  # NATIVE | VERIFY_IDENTITY
    how: str  # how the mechanism was decided (recorded in the host capabilities)
    root_flags: int  # opening the already-resolved root (no O_NOFOLLOW: the root may be a user-given symlink)
    dir_flags: int
    file_flags: int
    nonblocking: bool  # O_NONBLOCK present: a FIFO cannot hang open(); otherwise the lstat pre-check is the only guard


def _missing_native(host: Any) -> list[str]:
    missing = [name for name in ("O_NOFOLLOW", "O_DIRECTORY", "O_RDONLY") if getattr(host, name, None) is None]
    supports_dir_fd = getattr(host, "supports_dir_fd", ())
    supports_fd = getattr(host, "supports_fd", ())
    for func_name in ("open", "stat"):
        func = getattr(host, func_name, None)
        if func is None or func not in supports_dir_fd:
            missing.append(f"dir_fd:{func_name}")
    scandir = getattr(host, "scandir", None)
    if scandir is None or scandir not in supports_fd:
        missing.append("scandir(fd)")
    return missing


def _missing_verify(host: Any) -> list[str]:
    missing = [name for name in ("O_RDONLY",) if getattr(host, name, None) is None]
    missing += [f for f in ("open", "lstat", "fstat", "scandir") if getattr(host, f, None) is None]
    return missing


def _select(host: Any = os) -> tuple[_Primitives | None, str]:
    """The mechanism for ``host`` and how it was decided; ``(None, reason)`` when neither mechanism is available."""
    missing_native = _missing_native(host)
    cloexec = getattr(host, "O_CLOEXEC", 0)
    binary = getattr(host, "O_BINARY", 0)
    nonblock = getattr(host, "O_NONBLOCK", 0)
    if not missing_native:
        # O_NOFOLLOW_ANY is a superset of O_NOFOLLOW and the host rejects the two combined (observed: EINVAL), so it
        # replaces it.
        nofollow = getattr(host, "O_NOFOLLOW_ANY", None) or host.O_NOFOLLOW
        base = host.O_RDONLY | nofollow | cloexec | binary
        root = host.O_RDONLY | host.O_DIRECTORY | cloexec | binary
        how = "O_NOFOLLOW, O_DIRECTORY, dir_fd in open and stat, and scandir(fd) are all present"
        return _Primitives(NATIVE, how, root, base | host.O_DIRECTORY, base | nonblock, bool(nonblock)), ""
    missing_verify = _missing_verify(host)
    if missing_verify:
        return None, (
            "this host lacks primitives required to open input trees safely: "
            + ", ".join(missing_native)
            + "; the lstat-and-verify fallback also lacks: "
            + ", ".join(missing_verify)
        )
    base = host.O_RDONLY | cloexec | binary
    how = (
        "host lacks " + ", ".join(missing_native) + "; per-component lstat plus a post-open fstat identity check is used"
    )
    return _Primitives(VERIFY_IDENTITY, how, 0, 0, base | nonblock, bool(nonblock)), ""


def _probe(host: Any = os) -> _Primitives:
    """Feature-test the host and select the no-follow mechanism. Read every platform-dependent name with ``getattr``;
    never branch on the platform.

    ``native`` needs ``O_NOFOLLOW``, ``O_DIRECTORY``, ``dir_fd`` support in ``os.open``/``os.stat`` and ``os.scandir`` on a
    descriptor. Without any of them, ``verify_identity`` needs only ``os.lstat``, ``os.fstat``, ``os.scandir`` and
    ``os.open``. If neither is available the call fails closed with ``ingest.path.unsupported_platform`` (an
    :class:`IngestSafetyError`; no path is opened). Optional hardening, treated as absent-means-skip because the
    per-component walk (or per-component lstat) already refuses a link in every component: ``O_NOFOLLOW_ANY``,
    ``O_CLOEXEC`` (Python opens descriptors non-inheritable anyway), ``O_NONBLOCK`` (FIFO safety; the pre-open ``lstat``
    also refuses non-regular files) and ``O_BINARY``.
    """
    prim, reason = _select(host)
    if prim is None:
        raise IngestSafetyError("ingest.path.unsupported_platform", reason)
    return prim


def describe_mechanism(host: Any = os) -> tuple[str, str]:
    """``(mechanism, how decided)`` for the host capability record; ``("none", reason)`` when neither is available."""
    prim, reason = _select(host)
    return ("none", reason) if prim is None else (prim.mechanism, prim.how)


@functools.cache
def _prim() -> _Primitives:
    return _probe()


@dataclass(frozen=True, slots=True)
class DiscoveredFile:
    """A regular, singly-linked file below the root. ``label`` is its ``/``-joined relative path (data, not a path)."""

    label: str
    size: int


@dataclass(frozen=True, slots=True)
class PathRejection:
    """A ``register.jsonl`` row (stage ``ingest``) for something that must not be ingested. ``label`` is data."""

    label: str
    code: str
    detail: str


@dataclass(frozen=True, slots=True)
class Discovery:
    """Result of :func:`discover`, in deterministic (label) order."""

    root: str  # the root, resolved once and recorded
    files: tuple[DiscoveredFile, ...]
    rejected: tuple[PathRejection, ...]
    skipped: tuple[str, ...]  # `.DS_Store` and `._*` labels


class RootHandle:
    """A resolved root directory: its ``path`` and, with the ``native`` mechanism, an open descriptor (``fd``, else -1).

    Close it, or use it as a context manager. Pass the handle itself (not ``fd``) to :func:`open_evidence`.
    """

    def __init__(self, path: str, fd: int = -1) -> None:
        self.path = path
        self.fd = fd

    def close(self) -> None:
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1

    def __enter__(self) -> RootHandle:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def open_root(root: str | os.PathLike[str]) -> RootHandle:
    """Resolve the user-given ``root`` once (it may itself be a symlink) and open the resolved directory."""
    prim = _prim()
    resolved = os.path.realpath(os.fspath(root))
    if prim.mechanism == NATIVE:
        return RootHandle(resolved, os.open(resolved, prim.root_flags))
    if not stat.S_ISDIR(os.stat(resolved).st_mode):
        raise NotADirectoryError(errno.ENOTDIR, os.strerror(errno.ENOTDIR), resolved)
    return RootHandle(resolved)


def _symlink_error() -> IngestError:
    return IngestError("ingest.path.symlink", "symbolic link in input tree")


def _lstat(path: str) -> os.stat_result:
    return os.lstat(path)


def _is_link(st: os.stat_result) -> bool:
    """A symbolic link, or where the host reports ``st_file_attributes``, any reparse point (a junction, a mount point)."""
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def _plain_part(name: str) -> str:
    """A label component as a single child name on this host (verify_identity only).

    The label already passed :func:`logical_name`. A host whose path syntax has an alternate separator also gives ``:``
    a meaning (a drive, a stream), so there a component carrying any of these is refused, found by feature test.
    """
    syntax = {c for c in (os.sep, os.altsep) if c}
    if os.altsep is not None:
        syntax.add(":")
    if name in (os.curdir, os.pardir) or any(c in name for c in syntax) or os.path.splitdrive(name)[0]:
        raise IngestError("ingest.archive.traversal", "label component is not a plain name on this host")
    return name


def _open_at(dir_fd: int, name: str, *, directory: bool) -> int:
    """Open one path component relative to ``dir_fd`` without following links; classify failures (``native`` only)."""
    prim = _prim()
    try:
        return os.open(name, prim.dir_flags if directory else prim.file_flags, dir_fd=dir_fd)
    except FileNotFoundError:
        raise
    except OSError:
        st = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
        if stat.S_ISLNK(st.st_mode):
            raise _symlink_error() from None
        if not directory and not stat.S_ISREG(st.st_mode):
            raise IngestError("ingest.path.special", "special file in input tree") from None
        raise


def _verify_dir(parent: str, name: str) -> str:
    """verify_identity: the path of the child directory ``name`` of ``parent`` after an ``lstat`` (no link, a directory)."""
    child = os.path.join(parent, _plain_part(name))
    st = _lstat(child)
    if _is_link(st):
        raise _symlink_error()
    if not stat.S_ISDIR(st.st_mode):
        raise NotADirectoryError(errno.ENOTDIR, os.strerror(errno.ENOTDIR), name)
    return child


def _same_identity(a: os.stat_result, b: os.stat_result) -> bool:
    """Whether two stats describe one file: ``(st_dev, st_ino)``; where the host gives no file id (both zero) the size and
    modification time stand in, so a swap is still noticed."""
    if a.st_ino == 0 and a.st_dev == 0 and b.st_ino == 0 and b.st_dev == 0:
        return (a.st_size, a.st_mtime_ns) == (b.st_size, b.st_mtime_ns)
    return (a.st_dev, a.st_ino) == (b.st_dev, b.st_ino)


def open_evidence(
    root: RootHandle | int | str | os.PathLike[str],
    label: str,
    limits: IngestLimits | None = None,
    *,
    allow_hardlinks: bool = False,
    staging: bool = False,
) -> IO[bytes]:
    """Open the file ``label`` below the directory ``root``, read-only, without following a link (G.3.6).

    ``root`` is a :class:`RootHandle` (preferred), a directory path (resolved once and released afterwards), or a bare
    descriptor (``native`` mechanism only). ``label`` is a ``/``-joined relative name; it is validated as a label (no
    ``..``, no absolute form, no controls) and then checked one component at a time, so a symlink in *any* component gives
    ``ingest.path.symlink``. The file must be regular (``ingest.path.special`` otherwise, without blocking on a FIFO) with
    ``st_nlink == 1`` (``ingest.path.hardlink`` unless ``allow_hardlinks``, which is refused for ``staging``), within
    ``max_artefact_bytes`` (``ingest.size.file``). Returns a buffered binary reader that owns the descriptor. Under
    ``verify_identity`` a file that is not the one the pre-open ``lstat`` saw gives ``ingest.path.symlink``.
    """
    limits = limits or IngestLimits()
    prim = _prim()
    if staging and allow_hardlinks:
        raise ValueError("hardlinks are never allowed for a staging directory")
    if isinstance(root, int):
        if prim.mechanism != NATIVE:
            raise ValueError("a bare descriptor needs the native no-follow mechanism; pass the RootHandle")
        handle = RootHandle("", root)
    elif isinstance(root, RootHandle):
        handle = root
    else:
        with open_root(root) as opened:
            return open_evidence(opened, label, limits, allow_hardlinks=allow_hardlinks, staging=staging)
    name = logical_name(label, limits, portable=False)
    parts = name.split("/")
    if prim.mechanism == NATIVE:
        fd = _open_native(handle.fd, parts)
        pre = None
    else:
        fd, pre = _open_verified(handle.path, parts, prim)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise IngestError("ingest.path.special", "special file in input tree")
        if pre is not None and not _same_identity(pre, st):
            raise _symlink_error()
        if st.st_nlink != 1 and not allow_hardlinks:
            raise IngestError("ingest.path.hardlink", f"file has {st.st_nlink} hard links")
        if st.st_size > limits.max_artefact_bytes:
            raise IngestError(
                "ingest.size.file", f"file of {st.st_size} bytes exceeds the limit", limit=limits.max_artefact_bytes
            )
        if prim.nonblocking:
            os.set_blocking(fd, True)
        return os.fdopen(fd, "rb")
    except BaseException:
        os.close(fd)
        raise


def _open_native(root_fd: int, parts: list[str]) -> int:
    current = root_fd
    opened: list[int] = []
    try:
        for part in parts[:-1]:
            current = _open_at(current, part, directory=True)
            opened.append(current)
        # Refuse a special file by lstat before opening it (a device can have side effects on open); the fstat in the
        # caller is the authoritative check.
        pre = os.stat(parts[-1], dir_fd=current, follow_symlinks=False)
        if stat.S_ISLNK(pre.st_mode):
            raise _symlink_error()
        if not stat.S_ISREG(pre.st_mode):
            raise IngestError("ingest.path.special", "special file in input tree")
        return _open_at(current, parts[-1], directory=False)
    finally:
        for d in opened:
            os.close(d)


def _open_verified(root_path: str, parts: list[str], prim: _Primitives) -> tuple[int, os.stat_result]:
    """verify_identity: ``lstat`` every component and the leaf, open the leaf, and return the descriptor with the leaf's
    pre-open stat (the caller compares it with ``fstat``)."""
    current = root_path
    for part in parts[:-1]:
        current = _verify_dir(current, part)
    leaf = os.path.join(current, _plain_part(parts[-1]))
    pre = _lstat(leaf)
    if _is_link(pre):
        raise _symlink_error()
    if not stat.S_ISREG(pre.st_mode):
        raise IngestError("ingest.path.special", "special file in input tree")
    return os.open(leaf, prim.file_flags), pre


def _is_apple_junk(name: str) -> bool:
    return name == ".DS_Store" or name.startswith("._")


class _OpenDir:
    """A directory descriptor of the ``native`` walk, shared by the subdirectories still pending below it."""

    __slots__ = ("fd", "owned", "refs")

    def __init__(self, fd: int, owned: bool) -> None:
        self.fd, self.owned, self.refs = fd, owned, 1

    def release(self) -> None:
        self.refs -= 1
        if self.refs == 0 and self.owned:
            os.close(self.fd)


#: Running out of descriptors or memory is the walk's failure, never a property of the entry being opened.
_RESOURCE_ERRNOS: Final = frozenset({errno.EMFILE, errno.ENFILE, errno.ENOMEM})


def _same_entry(ref: int | str, raw: str, nfc: str) -> bool:
    """Whether the NFC spelling ``nfc`` of a directory entry ``raw`` names the same file (a normalisation-insensitive
    file system such as APFS). Neither name is followed if it is a link."""
    try:
        if isinstance(ref, int):
            a = os.stat(raw, dir_fd=ref, follow_symlinks=False)
            b = os.stat(nfc, dir_fd=ref, follow_symlinks=False)
        else:
            a, b = _lstat(os.path.join(ref, raw)), _lstat(os.path.join(ref, nfc))
    except OSError:
        return False
    return os.path.samestat(a, b)


def _iter_tree(
    handle: RootHandle, limits: IngestLimits, allow_hardlinks: bool
) -> Iterator[DiscoveredFile | PathRejection | str]:
    """Iterative walk (no recursion). Yields files, rejections and skipped labels (a bare ``str``).

    ``native``: directories are descriptors and ``os.scandir`` runs on them. A subdirectory is opened (relative to its
    parent's descriptor) only when the walk descends into it, and a parent stays open only while subdirectories of it
    are pending, so the open descriptors grow with the depth of the tree, never its width. ``verify_identity``:
    directories are paths and every entry is ``lstat``-ed (a ``DirEntry`` on some hosts carries no link count or file
    id, so it is not trusted).
    """
    verify = _prim().mechanism != NATIVE
    # verify_identity: (the directory's path, "", label prefix); native: (the parent, the entry name, label prefix),
    # with "" as the name of the root itself.
    pending: list[tuple[str | _OpenDir, str, str]] = [(handle.path if verify else _OpenDir(handle.fd, False), "", "")]
    try:
        while pending:
            where, name, prefix = pending.pop()
            here: _OpenDir | None = None
            if isinstance(where, str):
                ref: int | str = where
            elif not name:
                here = where
                ref = here.fd
            else:
                try:
                    child = _open_at(where.fd, name, directory=True)
                except IngestError as exc:
                    yield PathRejection(prefix[:-1], exc.code, "directory changed during discovery")
                    continue
                except OSError as exc:
                    if exc.errno in _RESOURCE_ERRNOS:
                        raise
                    yield PathRejection(prefix[:-1], "ingest.path.special", "directory could not be opened")
                    continue
                finally:
                    where.release()
                here = _OpenDir(child, True)
                ref = child
            try:
                with os.scandir(ref) as it:
                    entries = sorted(it, key=lambda e: e.name)
                # D-1 (pre-round review): siblings whose names collide on a case- or normalisation-insensitive file
                # system are all rejected, as archive members are (G.3.6); the NFC name is the label
                keys = Counter(collision_key(unicodedata.normalize("NFC", e.name)) for e in entries
                               if not _is_apple_junk(e.name))
                for entry in entries:
                    nfc = unicodedata.normalize("NFC", entry.name)
                    label = prefix + nfc
                    if not _is_apple_junk(entry.name) and keys[collision_key(nfc)] > 1:
                        yield PathRejection(label, "ingest.path.duplicate", "names collide (case or normalisation)")
                        continue
                    if nfc != entry.name and not _same_entry(ref, entry.name, nfc):
                        # the NFC label would open another file, or none (a normalisation-sensitive file system)
                        yield PathRejection(label, "ingest.name.invalid", "name not in NFC, and its NFC form is not it")
                        continue
                    st: os.stat_result | None = None
                    if verify:
                        try:
                            st = _lstat(os.path.join(str(ref), entry.name))
                        except OSError:
                            yield PathRejection(label, "ingest.path.special", "entry could not be examined")
                            continue
                        is_link = _is_link(st)
                        is_dir = stat.S_ISDIR(st.st_mode) and not is_link
                    else:
                        is_link = entry.is_symlink()
                        is_dir = entry.is_dir(follow_symlinks=False)
                    if not is_dir and _is_apple_junk(entry.name):
                        yield label
                        continue
                    try:
                        logical_name(label, limits, portable=False)
                    except IngestError as exc:
                        yield PathRejection(label, exc.code, "label rejected")
                        continue
                    if is_link:
                        yield PathRejection(label, "ingest.path.symlink", "symbolic link")
                    elif is_dir:
                        if here is None:
                            pending.append((os.path.join(str(ref), entry.name), "", label + "/"))
                        else:
                            here.refs += 1
                            pending.append((here, entry.name, label + "/"))
                    else:
                        st = st or entry.stat(follow_symlinks=False)
                        if not stat.S_ISREG(st.st_mode):
                            yield PathRejection(label, "ingest.path.special", "not a regular file")
                        elif st.st_nlink != 1 and not allow_hardlinks:
                            yield PathRejection(label, "ingest.path.hardlink", f"{st.st_nlink} hard links")
                        else:
                            yield DiscoveredFile(label, st.st_size)
            finally:
                if here is not None:
                    here.release()
    finally:
        for where, name, _prefix in pending:  # an exception or an early close must not leak descriptors
            if isinstance(where, _OpenDir) and name:
                where.release()


def discover(
    root: str | os.PathLike[str] | RootHandle,
    limits: IngestLimits | None = None,
    *,
    allow_hardlinks: bool = False,
) -> Discovery:
    """List the regular files below ``root`` and the entries that must not be ingested (G.3.6).

    No symlink is followed and nothing is read. The result is sorted by label, so it is deterministic. ``root`` may be a
    path (resolved once and closed afterwards) or an :class:`RootHandle`.
    """
    limits = limits or IngestLimits()
    _prim()
    handle = root if isinstance(root, RootHandle) else open_root(root)
    files: list[DiscoveredFile] = []
    rejected: list[PathRejection] = []
    skipped: list[str] = []
    try:
        for item in _iter_tree(handle, limits, allow_hardlinks):
            if isinstance(item, DiscoveredFile):
                files.append(item)
            elif isinstance(item, PathRejection):
                rejected.append(item)
            else:
                skipped.append(item)
    finally:
        if not isinstance(root, RootHandle):
            handle.close()
    return Discovery(
        handle.path,
        tuple(sorted(files, key=lambda f: f.label)),
        tuple(sorted(rejected, key=lambda r: r.label)),
        tuple(sorted(skipped)),
    )
