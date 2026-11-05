"""A verified bundle archive, unpacked into a new directory and nowhere else (D-1065).

``agentprov.ingest``'s archive readers never write a member to disk, drop file modes and reject links, which is right for
evidence and wrong for an application: a bundle needs its files on disk, the executable bits of a Linux bundle, and the
relative links of a macOS ``.app``. So this module has its own small extractor, which runs only on an archive whose
sha256 has been checked against the release's ``SHA256SUMS`` (:mod:`.verify`), and still treats it as untrusted:

* every member name is relative, ``/``-separated, without ``..``, a drive, a backslash, a control character or a
  Windows-reserved character, and lies below the one expected top folder (``AgentPROV.app`` or ``AgentPROV``); no name
  twice, compared case-insensitively (macOS and Windows file systems are);
* only directories, regular files and (``.tar.gz`` only) symbolic links; no hard link, device or FIFO; no setuid,
  setgid or sticky bit (a file keeps only whether it is executable);
* at most :data:`MAX_MEMBERS` members and :data:`MAX_TOTAL_BYTES` unpacked, counted while writing;
* every file is created with ``O_EXCL`` below a directory this module just made; links are made last, so no file is
  ever written through one, and every link must be relative and resolve (``os.path.realpath``, chains included) inside
  the top folder, or the whole directory is removed and the archive refused.

A ``.dmg`` (macOS) is attached read-only with ``hdiutil`` at a private mount point, its ``AgentPROV.app`` checked by the
same tree rules, copied with ``ditto`` (which keeps the code signature and extended attributes), checked again, and the
image detached. :func:`check_archive` runs the member checks without writing anything (``update download``).
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import tarfile  # SEC-11 allowlist: only after the archive's sha256 is checked; never extract()/extractall()
import zipfile
from collections.abc import Callable, Iterator
from functools import partial
from pathlib import Path
from typing import Any, Final

from agentprov.update.releases import UpdateError

__all__ = ["MAX_MEMBERS", "MAX_TOTAL_BYTES", "TOP", "check_archive", "unpack", "validate_tree"]

MAX_MEMBERS: Final = 200_000
MAX_TOTAL_BYTES: Final = 4 * 1024 * 1024 * 1024
#: the bundle's top folder per platform family (gui/tools/build_bundle.py bundle_path)
TOP: Final = {"macos": "AgentPROV.app", "linux": "AgentPROV", "windows": "AgentPROV"}
_BAD_CHARS: Final = re.compile(r'[\x00-\x1f\x7f<>:"|?*\\]')
_CHUNK: Final = 1024 * 1024


def _refuse(message: str) -> UpdateError:
    return UpdateError(message, code="update.archive")


def _family(label: str) -> str:
    family = label.split("-", 1)[0]
    if family not in TOP:
        raise UpdateError("not a bundle platform", code="update.platform")
    return family


def _parts(name: str, top: str) -> tuple[str, ...]:
    """A member name as path parts, checked (module docstring)."""
    if not name or len(name) > 1024 or name.startswith("/") or re.match(r"[A-Za-z]:", name):
        raise _refuse("an archive member has an absolute or empty name")
    parts = tuple(p for p in name.split("/") if p not in ("", "."))
    if not parts or any(p == ".." for p in parts):
        raise _refuse("an archive member's name leaves the archive ('..')")
    if any(_BAD_CHARS.search(p) or p != p.strip() or p.rstrip(".") == "" for p in parts):
        raise _refuse("an archive member's name has a character a file name may not have")
    if parts[0] != top:
        raise _refuse(f"an archive member lies outside the bundle folder {top}")
    return parts


class _Entry:
    __slots__ = ("kind", "link", "mode", "parts", "read", "size")

    def __init__(self, parts: tuple[str, ...], kind: str, size: int = 0, mode: int = 0o644, link: str | None = None,
                 read: Callable[[], Any] | None = None) -> None:
        self.parts, self.kind, self.size, self.mode, self.link, self.read = parts, kind, size, mode, link, read


def _tar_entries(archive: Path, top: str) -> Iterator[_Entry]:
    with tarfile.open(archive, mode="r:gz") as tf:
        for m in tf:
            parts = _parts(m.name, top)
            if m.isdir():
                yield _Entry(parts, "dir")
            elif m.isreg():
                yield _Entry(parts, "file", m.size, 0o755 if m.mode & 0o111 else 0o644,
                             read=partial(tf.extractfile, m))
            elif m.issym():
                yield _Entry(parts, "link", link=m.linkname)
            else:
                raise _refuse("an archive member is a hard link, device or FIFO")


def _zip_entries(archive: Path, top: str) -> Iterator[_Entry]:
    with zipfile.ZipFile(archive) as zf:
        infos = zf.infolist()
        if len(infos) > MAX_MEMBERS:
            raise _refuse("the archive has too many members")
        for info in infos:
            parts = _parts(info.filename, top)
            kind = stat.S_IFMT(info.external_attr >> 16)
            if kind == stat.S_IFLNK or kind not in (0, stat.S_IFREG, stat.S_IFDIR):
                raise _refuse("an archive member is a link or a special file")
            if info.flag_bits & 0x1:
                raise _refuse("an archive member is encrypted")
            if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                raise _refuse("an archive member uses an unexpected compression method")
            if info.is_dir():
                yield _Entry(parts, "dir")
            else:
                yield _Entry(parts, "file", info.file_size, 0o755 if (info.external_attr >> 16) & 0o111 else 0o644,
                             read=partial(zf.open, info))


def _entries(archive: Path, label: str) -> Iterator[_Entry]:
    family = _family(label)
    name = archive.name
    if family == "linux" and name.endswith(".tar.gz"):
        return _tar_entries(archive, TOP[family])
    if family == "windows" and name.endswith(".zip"):
        return _zip_entries(archive, TOP[family])
    raise _refuse("the archive is not this platform's bundle format")


def _walk(entries: Iterator[_Entry], dest: Path | None) -> tuple[dict[tuple[str, ...], str], int]:
    """Check every entry (and with ``dest``, write it); the links, for the caller to make last, and the count."""
    seen: dict[str, str] = {}
    links: dict[tuple[str, ...], str] = {}
    count = total = 0
    try:
        for e in entries:
            count += 1
            if count > MAX_MEMBERS:
                raise _refuse("the archive has too many members")
            key = "/".join(e.parts).casefold()
            if key in seen and not (e.kind == "dir" and seen[key] == "dir"):
                raise _refuse("the archive names a member twice")
            seen[key] = e.kind
            if any(e.parts[:i] in links for i in range(1, len(e.parts))):
                raise _refuse("an archive member lies below a link")
            if e.kind == "link":
                target = e.link or ""
                if not target or target.startswith("/") or "\\" in target or "\x00" in target or len(target) > 1024:
                    raise _refuse("an archive link is absolute or empty")
                links[e.parts] = target
                continue
            if e.kind == "file":
                total += e.size
                if total > MAX_TOTAL_BYTES:
                    raise _refuse("the archive unpacks to more than 4 GiB")
            if dest is None:
                continue
            path = dest.joinpath(*e.parts)
            if e.kind == "dir":
                path.mkdir(parents=True, exist_ok=True)
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), e.mode)
            written = 0
            with os.fdopen(fd, "wb") as out:
                assert e.read is not None
                src = e.read()
                try:
                    while chunk := src.read(_CHUNK):
                        written += len(chunk)
                        if written > e.size:
                            raise _refuse("an archive member is longer than it declares")
                        out.write(chunk)
                finally:
                    src.close()
            if written != e.size:
                raise _refuse("an archive member is shorter than it declares")
            os.chmod(path, e.mode)
    except (tarfile.TarError, zipfile.BadZipFile, EOFError, OSError, ValueError) as exc:
        raise _refuse(f"the archive cannot be read ({type(exc).__name__})") from None
    return links, count


def check_archive(archive: Path, label: str) -> int:
    """The member checks of :func:`unpack` with nothing written (a ``.dmg`` is checked when it is installed); the
    member count."""
    if _family(label) == "macos":
        if not archive.name.endswith(".dmg"):
            raise _refuse("the archive is not this platform's bundle format")
        return 0
    return _walk(_entries(archive, label), None)[1]


def _inside(path: str, root: str) -> bool:
    return path == root or path.startswith(root + os.sep)


def validate_tree(top: Path) -> int:
    """The tree rules on files on disk: directories, regular files without setuid/setgid/sticky bits, and relative
    links that resolve inside ``top``; the file count."""
    root = os.path.realpath(top)
    if top.is_symlink() or not top.is_dir():
        raise _refuse("the bundle folder is missing or a link")
    count = total = 0
    stack = [str(top)]
    while stack:
        current = stack.pop()
        with os.scandir(current) as it:
            for entry in it:
                count += 1
                if count > MAX_MEMBERS:
                    raise _refuse("the bundle has too many files")
                st = entry.stat(follow_symlinks=False)
                if stat.S_ISLNK(st.st_mode):
                    target = os.readlink(entry.path)
                    if os.path.isabs(target) or not _inside(os.path.realpath(entry.path), root):
                        raise _refuse("a link in the bundle points outside it")
                elif stat.S_ISDIR(st.st_mode):
                    stack.append(entry.path)
                elif stat.S_ISREG(st.st_mode):
                    if st.st_mode & (stat.S_ISUID | stat.S_ISGID | stat.S_ISVTX):
                        raise _refuse("a file in the bundle has a setuid, setgid or sticky bit")
                    total += st.st_size
                    if total > MAX_TOTAL_BYTES:
                        raise _refuse("the bundle is larger than 4 GiB")
                else:
                    raise _refuse("the bundle holds a device, FIFO or socket")
    return count


def _run(argv: list[str], run: Callable[..., Any], what: str) -> None:
    done = run(argv, capture_output=True, timeout=600, check=False)
    if done.returncode != 0:
        raise _refuse(f"{what} failed (exit {done.returncode})")


def _unpack_dmg(archive: Path, dest: Path, run: Callable[..., Any]) -> Path:
    mount = dest / ".mnt"
    mount.mkdir()
    _run(["hdiutil", "attach", "-readonly", "-nobrowse", "-noautoopen", "-mountpoint", str(mount), str(archive)],
         run, "hdiutil attach")
    try:
        app = mount / TOP["macos"]
        validate_tree(app)
        _run(["ditto", str(app), str(dest / TOP["macos"])], run, "ditto")
    finally:
        done = run(["hdiutil", "detach", "-quiet", str(mount)], capture_output=True, timeout=120, check=False)
        if done.returncode != 0:
            run(["hdiutil", "detach", "-force", "-quiet", str(mount)], capture_output=True, timeout=120, check=False)
        try:
            mount.rmdir()
        except OSError:
            pass
    return dest / TOP["macos"]


def unpack(archive: Path, dest: Path, label: str, *, run: Callable[..., Any] | None = None) -> Path:
    """Unpack ``archive`` into the new directory ``dest`` (it must not exist); the bundle folder in it. On any refusal
    ``dest`` is removed."""
    family = _family(label)
    dest.mkdir()  # FileExistsError when it exists: never into a directory with content
    try:
        if family == "macos":
            if not archive.name.endswith(".dmg"):
                raise _refuse("the archive is not this platform's bundle format")
            top = _unpack_dmg(archive, dest, run if run is not None else subprocess.run)
        else:
            links = _walk(_entries(archive, label), dest)[0]
            for parts, target in links.items():  # last: nothing was written through a link
                path = dest.joinpath(*parts)
                path.parent.mkdir(parents=True, exist_ok=True)
                os.symlink(target, path)
            top = dest / TOP[family]
        validate_tree(top)
        return top
    except BaseException:
        shutil.rmtree(dest, ignore_errors=True)
        raise
