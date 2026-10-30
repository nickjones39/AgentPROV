"""ZIP archives, zips stored as byte parts, and compressed tars, without extraction (docs/architecture G.3.5; A2; AD-12).

Nothing here ever writes a member to the filesystem: members are streamed as byte chunks to the caller (the raw store),
member names are labels (:mod:`agentprov.ingest.names`), and the central directory is trusted only after a size check.
An uncompressed tar is refused (``ingest.archive.format``, exit 5 at the CLI). Compressed single streams are deferred
(:mod:`agentprov.ingest.streams`), except a compressed tar: a zstd tar (D-240) or a gzip tar (D-57; at the top level
since D-247), at any level up to ``max_archive_depth``.

**Compressed tar (D-57, D-240).** :class:`OpenedTar` reads it with its own 512-byte header parser; ``tarfile``
is never used, because it buffers a GNU long-name header of any declared size before a caller can check it (obs-G1).
The decompressed stream comes from :func:`agentprov.ingest.streams.iter_decompressed` (gzip or zstd), bounded by
``max_tar_stream_bytes`` (D-241) and ``max_ratio``; it is decoded twice, once per pass, and never held.
Pass 1, at open, walks the whole decompressed stream and checks
the structure: every header checksum, the ``ustar`` magic, octal sizes only, typeflags ``0``/NUL (file), ``5``
(directory), ``1``/``2``/``3``/``4``/``6`` (link or special: rejected member), ``L`` (GNU long name, at most
``max_name_bytes`` held; a longer one is skipped unread and its entry rejected ``ingest.name.invalid``); any other
typeflag (pax ``g``, ``K``, sparse, ...) rejects the archive, as do a header after the end-of-archive blocks, a
truncated stream and a gzip trailer or zstd checksum mismatch. A pax ``x`` header (D-248) is read as data, bounded by
``max_pax_header_bytes``, through a closed key allowlist: ``path`` and ``size`` apply to the next entry (the name through
``logical_name``, the size through the member gate), ``mtime``/``atime``/``ctime``/``uid``/``gid``/``uname``/``gname``
and ``SCHILY.xattr.*``/``LIBARCHIVE.xattr.*`` are ignored, any other key refuses the archive. Pass 2 streams the members through the same gate as zip
members. A tar member is recorded with method 0 (no member-level compression inside the tar) and the CRC-32 computed while
streaming: a tar declares no CRC, so its integrity rests on the header checksums, the codec's own check (gzip trailer;
zstd content checksum when the frame carries one) and re-expansion.

**Zip stored as byte parts (D-243).** :func:`open_split_zip` takes the parts' handles and declared sizes in the
**declared order** (never an order derived from names), checks the declaration (``ingest.archive.parts``), and runs the
unchanged sequence below on the logical bytes through :class:`agentprov.ingest.parts.PartsView`. This is a byte split
(``split -b``), not a PKWARE multi-disk archive, which the pre-check keeps refusing.

The order (G.3.5), all inside a T1 worker:

1. :func:`zip_precheck`: locate the EOCD (and the ZIP64 EOCD through its locator) with ``struct`` only, mirroring what
   ``zipfile`` will read, and reject a central directory over ``max_cd_bytes`` or beyond the file *before*
   ``zipfile.ZipFile`` is called (it allocates about 11x the CD size).
2. :func:`open_zip` opens with ``warnings`` turned into errors, then rejects more than ``max_members`` entries whatever
   the EOCD claims, rejects a non-zero smallest ``header_offset`` (prefix: polyglot or self-extractor; CPython adds the
   detected prefix length to every offset), and records bytes after the EOCD comment as a finding.
3. The overlap check reads each 30-byte local header and requires every member's data to end before the next header
   (or the central directory).
4. :func:`iter_zip_members` gates each member: non-regular, encrypted, method, name, collision, size, ratio, total,
   selection. A structural defect rejects the **whole archive** (an exception from steps 1-3); a member-level defect
   rejects **that member only** (a :class:`ZipMember` with ``disposition="rejected"`` and its code).
5. :meth:`OpenedZip.stream_member` streams a selected member with ``ZipFile.open`` (which stops at the declared size and
   checks the CRC) and compares the byte count with the declared size.

Opening an archive first calls :func:`agentprov.envinfo.require_patched_for_archive`; its advisory (or ``None``) is on
``OpenedZip.advisory`` for the caller to record (G.3.8).
"""

from __future__ import annotations

import stat
import struct
import warnings
import zipfile
import zlib
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from typing import IO, Any, Final, Literal, cast

from agentprov.envinfo import InterpreterAdvisory, require_patched_for_archive
from agentprov.errors import IngestError, IngestFinding
from agentprov.ingest.limits import IngestLimits, NestedRaises, depth_limit
from agentprov.ingest.names import collision_key, logical_name
from agentprov.ingest.parts import PartsView, check_split_declaration
from agentprov.ingest.streams import SNIFF_BYTES, Codec, iter_decompressed, sniff_container

_zstd: Any
try:  # method 93 needs Python >= 3.14; the core requires it, but stay importable
    from compression import zstd as _zstd
except ImportError:  # pragma: no cover
    _zstd = None

Disposition = Literal["selected", "not_selected", "rejected"]

_EOCD_SIG: Final = b"PK\x05\x06"
_EOCD64_SIG: Final = b"PK\x06\x06"
_LOC64_SIG: Final = b"PK\x06\x07"
_LOCAL_SIG: Final = b"PK\x03\x04"
_EOCD_SIZE: Final = 22
_EOCD_STRUCT: Final = struct.Struct("<4s4H2LH")
_LOC64_SIZE: Final = 20
_LOC64_STRUCT: Final = struct.Struct("<4sLQL")
_EOCD64_SIZE: Final = 56
_EOCD64_STRUCT: Final = struct.Struct("<4sQ2H2L4Q")
_LOCAL_HEADER_SIZE: Final = 30
_MAX_COMMENT: Final = 0xFFFF
_CHUNK: Final = 64 * 1024
_FLAG_ENCRYPTED: Final = 0x1
_FLAG_STRONG_ENCRYPTION: Final = 0x40
_TAR_MAGIC_OFFSET: Final = 257


def _format(reason: str) -> IngestError:
    return IngestError("ingest.archive.format", reason)


def _read_exact(fp: IO[bytes], offset: int, size: int, what: str) -> bytes:
    fp.seek(offset)
    data = fp.read(size)
    if len(data) != size:
        raise _format(f"truncated {what}")
    return data


@dataclass(frozen=True, slots=True)
class ZipPrecheck:
    """What the size pre-check learned without calling ``zipfile`` (G.3.5 step 1)."""

    file_size: int
    eocd_offset: int
    end_offset: int  # start of the ZIP64 EOCD when present, else of the classic EOCD
    cd_offset: int
    cd_size: int
    entries: int  # as claimed by the EOCD; never trusted
    zip64: bool
    comment_len: int
    trailing_bytes: int  # bytes after the EOCD comment


def zip_precheck(fp: IO[bytes], limits: IngestLimits | None = None, *, max_size: int | None = None) -> ZipPrecheck:
    """Size check before ``zipfile.ZipFile`` is called (G.3.5 step 1; obs-G8; SR-11.2).

    Mirrors ``zipfile``'s own end-record search so that the numbers checked are the numbers it will use: the classic EOCD
    at ``size - 22`` when it has no comment, else the last EOCD signature in the final 65,557 bytes; then the ZIP64 EOCD
    through its locator. Raises ``ingest.archive.cd`` for a central directory over ``max_cd_bytes`` or extending beyond
    the file, ``ingest.archive.format`` for anything that is not a readable zip end record. The size bound is
    ``max_artefact_bytes``, or ``max_size`` for the logical bytes of a split archive (``max_split_bytes``, D-243).
    """
    limits = limits or IngestLimits()
    bound = limits.max_artefact_bytes if max_size is None else max_size
    fp.seek(0, 2)
    size = fp.tell()
    if size > bound:
        raise IngestError("ingest.size.file", f"archive of {size} bytes exceeds the limit", limit=bound)
    if size < _EOCD_SIZE:
        raise _format("too small to be a zip file")

    tail = _read_exact(fp, size - _EOCD_SIZE, _EOCD_SIZE, "end record")
    if tail[:4] == _EOCD_SIG and tail[-2:] == b"\x00\x00":
        eocd_offset, record = size - _EOCD_SIZE, tail
    else:
        window_start = max(size - _MAX_COMMENT - _EOCD_SIZE, 0)
        fp.seek(window_start)
        window = fp.read(_MAX_COMMENT + _EOCD_SIZE)
        found = window.rfind(_EOCD_SIG)
        if found < 0:
            raise _format("no end of central directory record")
        record = window[found : found + _EOCD_SIZE]
        if len(record) != _EOCD_SIZE:
            raise _format("truncated end record")
        eocd_offset = window_start + found

    _, disk, disk_cd, entries_disk, entries, cd_size, cd_offset, comment_len = _EOCD_STRUCT.unpack(record)
    # G.3.5, D-243: a PKWARE multi-disk archive is refused. 0xFFFF means "see the ZIP64 record" (checked below).
    if any(v not in (0, 0xFFFF) for v in (disk, disk_cd)) or entries_disk != entries:
        raise _format("multi-disk zip files are not supported")
    end_offset = eocd_offset
    zip64 = False

    locator_at = eocd_offset - _LOC64_SIZE
    if locator_at >= 0:
        sig, disk_no, reloff, disks = _LOC64_STRUCT.unpack(_read_exact(fp, locator_at, _LOC64_SIZE, "zip64 locator"))
        if sig == _LOC64_SIG:
            if disk_no != 0 or disks > 1:
                raise _format("multi-disk zip files are not supported")
            record_at = locator_at - _EOCD64_SIZE
            if record_at < 0 or reloff > record_at:
                raise _format("corrupt zip64 locator")
            extra = record_at - reloff
            data = _read_exact(fp, reloff, _EOCD64_SIZE, "zip64 end record")
            if not data.startswith(_EOCD64_SIG) and reloff != record_at:
                extra = 0
                data = _read_exact(fp, record_at, _EOCD64_SIZE, "zip64 end record")
            if not data.startswith(_EOCD64_SIG):
                raise _format("zip64 end record not found")
            _, rec_size, _v1, _v2, disk64, disk64_cd, entries_disk64, entries, cd_size, cd_offset = _EOCD64_STRUCT.unpack(data)
            if disk64 != 0 or disk64_cd != 0 or entries_disk64 != entries:
                raise _format("multi-disk zip files are not supported")
            if cd_offset + cd_size != reloff or rec_size + 12 != _EOCD64_SIZE + extra:
                raise _format("corrupt zip64 end record")
            end_offset = record_at - extra
            zip64 = True

    if cd_size > limits.max_cd_bytes:
        raise IngestError(
            "ingest.archive.cd",
            f"central directory of {cd_size} bytes exceeds the limit",
            offset=cd_offset,
            limit=limits.max_cd_bytes,
        )
    if cd_offset + cd_size > end_offset or end_offset - cd_size < 0:
        raise IngestError("ingest.archive.cd", "central directory extends beyond the file", offset=cd_offset)
    trailing = max(size - (eocd_offset + _EOCD_SIZE + comment_len), 0)
    return ZipPrecheck(size, eocd_offset, end_offset, cd_offset, cd_size, entries, zip64, comment_len, trailing)


@dataclass(frozen=True, slots=True)
class ZipMember:
    """The gate's decision for one non-directory member (G.3.5 step 4).

    ``raw_name`` is the name as recorded, which is **data**: show it only through ``quote.escape_untrusted``. ``label`` is
    the validated NFC logical name, or ``None`` when the name was rejected. ``code`` is set when ``disposition`` is
    ``rejected``.
    """

    index: int
    raw_name: str
    label: str | None
    method: int
    crc32: int
    file_size: int
    compress_size: int
    disposition: Disposition
    code: str | None = None
    detail: str | None = None
    _info: zipfile.ZipInfo = field(repr=False, compare=False, default=None)  # type: ignore[assignment]
    _archive: OpenedZip = field(repr=False, compare=False, default=None)  # type: ignore[assignment]

    def to_json(self) -> dict[str, Any]:
        """The ``raw/members.jsonl`` member fields (no raw name, which is data)."""
        out: dict[str, Any] = {
            "label": self.label,
            "method": self.method,
            "crc32": self.crc32,
            "size": self.file_size,
            "disposition": self.disposition,
        }
        if self.code is not None:
            out["code"] = self.code
        return out

    def iter_chunks(self, chunk_size: int = _CHUNK) -> Iterator[bytes]:
        """Stream a selected member's bytes (see :meth:`OpenedZip.stream_member`)."""
        return self._archive.stream_member(self, chunk_size)


class OpenedZip:
    """An opened zip container: the ``ZipFile``, the pre-check, findings and the interpreter advisory."""

    def __init__(
        self,
        zf: zipfile.ZipFile,
        precheck: ZipPrecheck,
        findings: tuple[IngestFinding, ...],
        advisory: InterpreterAdvisory | None,
        limits: IngestLimits,
        depth: int,
    ) -> None:
        self._zf = zf
        self.precheck = precheck
        self.findings = findings
        self.advisory = advisory
        self.limits = limits
        self.depth = depth

    def __enter__(self) -> OpenedZip:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._zf.close()

    def stream_member(self, member: ZipMember, chunk_size: int = _CHUNK) -> Iterator[bytes]:
        """Yield a selected member's bytes in chunks of at most ``chunk_size``; nothing touches the filesystem.

        The stream stops at the declared size, the CRC is checked at the end (``ingest.archive.crc``), and the byte count
        must equal the declared size (``ingest.archive.size``). Nothing beyond the declared size is ever read, so a lying
        header cannot enlarge the allocation.
        """
        if member.disposition != "selected":
            raise ValueError("only selected members can be streamed")
        info = member._info
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error")
                src = self._zf.open(info)
        except zipfile.BadZipFile as exc:
            raise _member_error(exc) from None
        except (NotImplementedError, RuntimeError, Warning, ValueError, UnicodeDecodeError) as exc:
            raise _member_error(exc) from None
        total = 0
        with src:
            while True:
                try:
                    chunk = src.read(chunk_size)
                except IngestError:
                    raise
                except Exception as exc:  # noqa: BLE001 - every decoder failure maps to a closed code
                    raise _member_error(exc) from None
                if not chunk:
                    break
                total += len(chunk)
                if total > member.file_size:
                    raise IngestError("ingest.archive.size", "member longer than its declared size")
                yield chunk
        if total != member.file_size:
            raise IngestError("ingest.archive.size", "member shorter than its declared size")

    def read_member(self, member: ZipMember) -> bytes:
        """The whole selected member in memory (bounded by ``max_member_bytes``)."""
        return b"".join(self.stream_member(member))


def _member_error(exc: BaseException) -> IngestError:
    """Map a ``zipfile`` or decoder failure on one member to a closed code (no source text in the message)."""
    if isinstance(exc, IngestError):
        return exc
    text = str(exc)
    if isinstance(exc, zipfile.BadZipFile):
        if "CRC" in text:
            return IngestError("ingest.archive.crc", "CRC-32 mismatch")
        if "Overlapped" in text:
            return IngestError("ingest.archive.overlap", "overlapped member data")
        return IngestError("ingest.archive.format", "inconsistent member header")
    if isinstance(exc, EOFError):
        return IngestError("ingest.stream.truncated", "truncated compressed member")
    if isinstance(exc, NotImplementedError):
        return IngestError("ingest.archive.method", "compression method not supported by this interpreter")
    if isinstance(exc, RuntimeError):
        return IngestError("ingest.archive.encrypted", "encrypted member")
    if isinstance(exc, zlib.error):
        return IngestError("ingest.archive.format", "corrupt deflate stream")
    if _zstd is not None and isinstance(exc, _zstd.ZstdError):
        if "memory" in text.lower() or "window" in text.lower():
            return IngestError("ingest.stream.memory", "zstd frame needs more memory than the window limit allows")
        return IngestError("ingest.archive.format", "corrupt zstd frame")
    return IngestError("ingest.archive.format", "unreadable member")


def open_zip(
    fp: IO[bytes],
    limits: IngestLimits | None = None,
    *,
    release: bool,
    depth: int = 1,
    max_depth: int | None = None,
) -> OpenedZip:
    """Open a zip container without extracting anything (G.3.5 steps 1-3).

    ``depth`` is the nesting level of this container (the top-level container is 1); a level above ``max_archive_depth``
    raises ``ingest.archive.depth`` and is never opened. ``max_depth`` is the allowance a declared nested-archive pattern
    grants (D-382; :func:`agentprov.ingest.limits.depth_limit`: never below the global value, never above
    ``NESTED_MAX_DEPTH``). The interpreter guard runs first (G.3.8): below the floor,
    release mode raises :class:`~agentprov.envinfo.InterpreterUnpatchedError` before ``fp`` is read, and dev mode warns
    and puts the advisory on the result. A structural defect raises :class:`~agentprov.errors.IngestError` and rejects the
    whole archive.
    """
    return _open_zip(fp, limits or IngestLimits(), depth, require_patched_for_archive(release=release), max_depth=max_depth)


def open_split_zip(
    parts: Sequence[IO[bytes]],
    sizes: Sequence[int],
    limits: IngestLimits | None = None,
    *,
    release: bool,
    depth: int = 1,
    max_depth: int | None = None,
) -> OpenedZip:
    """Open a zip stored as byte parts, in the declared order, as one logical zip (D-243; G.3.5 unchanged).

    ``parts`` are binary handles positioned anywhere (the caller opened each one by its pinned digest); ``sizes`` are the
    declared byte sizes, in the same order. The interpreter guard runs first (G.3.8). The declaration is checked
    (``ingest.archive.parts``: at least two and at most ``max_split_parts`` parts, none empty, each handle exactly its
    declared size, the logical size at most ``max_split_bytes``), the logical bytes must start with a zip local header
    (``ingest.archive.format``), and then the pre-check, open, prefix, member-count and overlap checks of
    :func:`open_zip` run on the logical bytes, with ``max_split_bytes`` as the size bound. The handles stay the caller's.
    """
    advisory = require_patched_for_archive(release=release)  # before any part is read (G.3.8)
    limits = limits or IngestLimits()
    check_split_declaration(parts, sizes, limits)
    view = PartsView(parts, sizes)
    if sniff_container(view.read(SNIFF_BYTES)) != "zip":
        raise _format("the parts do not start with a zip local header")
    return _open_zip(cast(IO[bytes], view), limits, depth, advisory, max_size=limits.max_split_bytes, max_depth=max_depth)


def _open_zip(
    fp: IO[bytes],
    limits: IngestLimits,
    depth: int,
    advisory: InterpreterAdvisory | None,
    *,
    max_size: int | None = None,
    max_depth: int | None = None,
) -> OpenedZip:
    allowed = depth_limit(limits, max_depth)
    if depth > allowed:
        raise IngestError("ingest.archive.depth", f"archive nesting level {depth} exceeds the limit", limit=allowed)

    precheck = zip_precheck(fp, limits, max_size=max_size)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error")  # "Overlapped entries" and "Duplicate name" become errors
            zf = zipfile.ZipFile(fp)
    except zipfile.BadZipFile:
        raise _format("not a readable zip file") from None
    except UnicodeDecodeError:
        # zipfile decodes every UTF-8-flagged name while it reads the central directory, before any member gate: one
        # undecodable name refuses the whole archive (fail-closed; G.3.5's recorded deviation, pre-round review D #3).
        raise _format("a member name flagged UTF-8 is not valid UTF-8 (the whole archive is refused)") from None
    except (zipfile.LargeZipFile, NotImplementedError, Warning, ValueError, OSError, EOFError, struct.error,
            OverflowError):
        raise _format("unreadable zip structure") from None

    try:
        infos = zf.infolist()
        if any(info.volume != 0 for info in infos):  # a member on another disk (G.3.5, D-243)
            raise _format("multi-disk zip files are not supported")
        if len(infos) > limits.max_members:
            raise IngestError(
                "ingest.archive.members",
                f"{len(infos)} entries exceed the limit",
                limit=limits.max_members,
            )
        findings: list[IngestFinding] = []
        if infos and min(i.header_offset for i in infos) != 0:
            raise IngestError("ingest.archive.prefix", "data before the first local header (polyglot or self-extractor)")
        if precheck.trailing_bytes:
            findings.append(
                IngestFinding(
                    "ingest.archive.trailing",
                    "warning",
                    offset=precheck.eocd_offset,
                    detail=f"{precheck.trailing_bytes} bytes after the end record",
                )
            )
        _check_overlap(fp, zf, infos)
    except BaseException:
        zf.close()
        raise
    return OpenedZip(zf, precheck, tuple(findings), advisory, limits, depth)


def _check_overlap(fp: IO[bytes], zf: zipfile.ZipFile, infos: list[zipfile.ZipInfo]) -> None:
    """G.3.5 step 3: every member's data ends before the next local header (or the central directory)."""
    order = sorted(range(len(infos)), key=lambda i: infos[i].header_offset)
    for pos, i in enumerate(order):
        info = infos[i]
        limit = infos[order[pos + 1]].header_offset if pos + 1 < len(order) else zf.start_dir
        fp.seek(info.header_offset)
        header = fp.read(_LOCAL_HEADER_SIZE)
        if len(header) != _LOCAL_HEADER_SIZE or header[:4] != _LOCAL_SIG:
            raise _format("bad local file header")
        name_len, extra_len = struct.unpack("<HH", header[26:30])
        end = info.header_offset + _LOCAL_HEADER_SIZE + name_len + extra_len + info.compress_size
        if end > limit:
            raise IngestError("ingest.archive.overlap", "member data overlaps the next entry", offset=info.header_offset)


def iter_zip_members(
    archive: OpenedZip | OpenedTar,
    include: Callable[[str], bool] | None = None,
    limits: IngestLimits | None = None,
    raised: Callable[[str], NestedRaises | None] | None = None,
) -> Iterator[ZipMember]:
    """Gate every non-directory member and yield its decision, in central-directory order (G.3.5 step 4).

    ``include(label)`` decides selection from the validated NFC label; ``None`` selects everything. A caller that expands
    nested archives passes a predicate for the profile's include patterns *and* its nested-archive patterns. A member
    that matches neither is ``not_selected``: it is never decompressed.

    Order of the member-level checks: non-regular (``ingest.archive.link``), encrypted, method, name
    (``ingest.name.invalid`` / ``ingest.archive.traversal``), collision (``ingest.archive.duplicate``; every member that
    shares a collision key), ``max_member_bytes`` and ratio (``ingest.archive.size`` / ``ingest.archive.ratio``), then
    selection, then the running total of **selected** members against ``max_total_bytes`` (a member that would exceed it is
    rejected with ``ingest.archive.size`` and not counted).

    ``raised(label)`` gives the raises of a declared nested-archive pattern the label matches (D-382), or ``None``: such a
    member is gated against the raised ``max_member_bytes`` and ``max_ratio`` instead of the global ones (every other
    check is unchanged). A tar holds a selected member whole (D-57), so a tar ignores the size raise: a member above the
    global bound stays ``ingest.archive.size``.
    """
    limits = limits or archive.limits
    if isinstance(archive, OpenedTar):
        yield from archive.iter_members(include, limits)
        return
    members = [(i, info) for i, info in enumerate(archive._zf.infolist()) if not info.orig_filename.endswith("/")]

    labels: dict[int, str] = {}
    name_errors: dict[int, IngestError] = {}
    groups: dict[str, int] = {}
    for i, info in members:
        try:
            valid = logical_name(info.orig_filename, limits)
        except IngestError as exc:
            name_errors[i] = exc
            continue
        labels[i] = valid
        key = collision_key(valid)
        groups[key] = groups.get(key, 0) + 1

    total = 0
    for i, info in members:
        label = labels.get(i)
        raises = raised(label) if raised is not None and label is not None else None
        max_member = limits.max_member_bytes if raises is None else raises.member_bytes(limits)
        max_ratio = limits.max_ratio if raises is None else raises.ratio(limits)
        mode_type = stat.S_IFMT(info.external_attr >> 16)
        if mode_type and mode_type != stat.S_IFREG:
            code, detail = "ingest.archive.link", "non-regular member (symlink or special file)"
        elif info.flag_bits & (_FLAG_ENCRYPTED | _FLAG_STRONG_ENCRYPTION):
            code, detail = "ingest.archive.encrypted", "encrypted member"
        elif info.compress_type not in limits.zip_methods:
            code, detail = "ingest.archive.method", f"compression method {info.compress_type} not allowed"
        elif i in name_errors:
            code, detail = name_errors[i].code, "member name rejected"
        elif groups[collision_key(labels[i])] > 1:
            code, detail = "ingest.archive.duplicate", "name collides with another member"
        elif info.file_size > max_member:
            code, detail = "ingest.archive.size", "member exceeds max_member_bytes"
        elif (
            info.file_size > limits.ratio_floor_bytes
            and info.file_size / max(info.compress_size, 1) > max_ratio
        ):
            code, detail = "ingest.archive.ratio", "compression ratio exceeds max_ratio"
        elif include is not None and not include(labels[i]):
            yield _member(archive, i, info, label, "not_selected")
            continue
        elif total + info.file_size > limits.max_total_bytes:
            code, detail = "ingest.archive.size", "selected members exceed max_total_bytes"
        else:
            total += info.file_size
            yield _member(archive, i, info, label, "selected")
            continue
        yield _member(archive, i, info, label, "rejected", code, detail)


def _member(
    archive: OpenedZip,
    index: int,
    info: zipfile.ZipInfo,
    label: str | None,
    disposition: Disposition,
    code: str | None = None,
    detail: str | None = None,
) -> ZipMember:
    return ZipMember(
        index,
        info.orig_filename,
        label,
        info.compress_type,
        info.CRC,
        info.file_size,
        info.compress_size,
        disposition,
        code,
        detail,
        info,
        archive,
    )


def open_archive(
    fp: IO[bytes],
    limits: IngestLimits | None = None,
    *,
    release: bool,
    depth: int = 1,
    max_depth: int | None = None,
) -> OpenedZip | OpenedTar:
    """Open ``fp`` as a zip container or a compressed tar, refusing everything else with a closed code.

    Zip is opened (:func:`open_zip`). A zstd stream whose first header is a ``ustar`` tar header is opened as
    :class:`OpenedTar` at any level (D-240); a zstd frame header that is refused (skippable, dictionary, window, declared
    size) raises its own code here. A gzip stream whose first header is a ``ustar`` header is opened as :class:`OpenedTar`
    at any level too (D-57 at level 2; D-247 at level 1, for the archive inputs of declared deposit pins). Every other
    compressed single stream is deferred (``ingest.stream.codec``). An uncompressed tar is refused with ``ingest.archive.format``
    (exit 5 at the CLI). Anything else is not an archive (``ingest.archive.format``). ``max_depth`` is a declared
    nested-archive allowance (D-382), as for :func:`open_zip`.
    """
    advisory = require_patched_for_archive(release=release)  # before the object is read at all (G.3.8)
    limits = limits or IngestLimits()
    fp.seek(0)
    kind = sniff_container(fp.read(SNIFF_BYTES))
    if kind == "zip":
        return _open_zip(fp, limits, depth, advisory, max_depth=max_depth)
    if kind in ("zstd", "gzip") and _holds_tar(fp, kind, limits):
        allowed = depth_limit(limits, max_depth)
        if depth > allowed:
            raise IngestError("ingest.archive.depth", f"archive nesting level {depth} exceeds the limit", limit=allowed)
        return OpenedTar(fp, limits, depth, advisory, codec=kind)
    if kind != "document":
        raise IngestError(
            "ingest.stream.codec", f"{kind} stream is deferred in v0.1; it is stored inert, never decompressed"
        )
    fp.seek(_TAR_MAGIC_OFFSET)
    if fp.read(5) == b"ustar":
        raise _format("tar archives are refused in v0.1")
    raise _format("not a supported archive")


# --------------------------------------------------------------------------------------------------------------
# A compressed tar: gzip nested in a zip (D-57), zstd at any level (D-240)
# --------------------------------------------------------------------------------------------------------------

_TAR_BLOCK: Final = 512
_TAR_ZERO: Final = bytes(_TAR_BLOCK)
_TAR_MAGICS: Final = ((b"ustar\x00", b"00", True), (b"ustar ", b" \x00", False))  # (magic, version, POSIX prefix field)
_TAR_FILE: Final = frozenset({"0", "\x00"})
_TAR_DIR: Final = "5"
_TAR_LONGNAME: Final = "L"
_TAR_PAX: Final = "x"
#: pax keys applied to the next entry (D-248); every other key outside the ignored ones refuses the archive.
_PAX_APPLIED: Final = frozenset({b"path", b"size"})
_PAX_IGNORED: Final = frozenset({b"mtime", b"atime", b"ctime", b"uid", b"gid", b"uname", b"gname"})
_PAX_IGNORED_PREFIXES: Final = (b"SCHILY.xattr.", b"LIBARCHIVE.xattr.")
_TAR_NONREGULAR: Final = frozenset({"1", "2", "3", "4", "6"})  # hard link, symlink, char, block, FIFO
_OCTAL: Final = frozenset(b"01234567")


def _holds_tar(fp: IO[bytes], codec: Codec, limits: IngestLimits) -> bool:
    """Whether the first decompressed block of a gzip or zstd stream is a ``ustar`` header.

    A gzip decoding failure means "not a tar" (D-57: the stream stays deferred). A zstd failure raises its code: the frame
    header is checked before any allocation, so a refused window, dictionary or declared size is reported as such.
    """
    head = bytearray()
    fp.seek(0)
    try:
        for chunk in iter_decompressed(fp, codec, limits, chunk=_TAR_BLOCK, max_bytes=limits.max_tar_stream_bytes):
            head += chunk
            if len(head) >= _TAR_BLOCK:
                break
    except IngestError:
        if codec == "zstd":
            raise
        return False
    finally:
        fp.seek(0)
    return len(head) >= _TAR_BLOCK and bytes(head[_TAR_MAGIC_OFFSET : _TAR_MAGIC_OFFSET + 5]) == b"ustar"


class _BlockReader:
    """Exact reads over the chunks of a bounded decoder; holds the current chunk and, for a read, its result.

    A read of ``n`` bytes collects whole chunks in a list and joins them once (as the zip path does), instead of growing
    one buffer by repeated reallocation: on macOS the abandoned large regions of a growing ``bytearray`` stay resident, and
    a job reading many large members grew by one member size per member (measured, D-245).
    """

    def __init__(self, chunks: Iterator[bytes]) -> None:
        self._chunks = chunks
        self._buf = b""
        self._pos = 0

    def _next(self) -> bool:
        chunk = next(self._chunks, None)
        if chunk is None:
            return False
        self._buf, self._pos = chunk, 0
        return True

    def read(self, n: int) -> bytes:
        available = len(self._buf) - self._pos
        if n <= available:
            out = self._buf[self._pos : self._pos + n]
            self._pos += n
            return out
        parts = [self._buf[self._pos :]] if available else []
        need = n - available
        self._buf, self._pos = b"", 0
        while need:
            if not self._next():
                raise IngestError("ingest.stream.truncated", "the tar stream ends inside a header or member")
            take = min(need, len(self._buf))
            parts.append(self._buf if take == len(self._buf) else self._buf[:take])
            self._pos = take
            need -= take
        return b"".join(parts)

    def skip(self, n: int, *, crc: int | None = None) -> int:
        """Consume ``n`` bytes without holding them; returns the running CRC-32 when ``crc`` is given."""
        value = 0 if crc is None else crc
        while n:
            if self._pos >= len(self._buf) and not self._next():
                raise IngestError("ingest.stream.truncated", "the tar stream ends inside a member")
            take = min(n, len(self._buf) - self._pos)
            if crc is not None:
                value = zlib.crc32(memoryview(self._buf)[self._pos : self._pos + take], value)
            self._pos += take
            n -= take
        return value

    def rest_is_zero(self) -> bool:
        while True:
            if self._buf[self._pos :].strip(b"\x00"):
                return False
            if not self._next():
                return True


def _tar_octal(field: bytes) -> int:
    """An octal tar number; base-256 (high bit set) and anything but octal digits are refused."""
    if field and field[0] & 0x80:
        raise _format("base-256 tar number")
    digits = field.split(b"\x00", 1)[0].strip(b" ")
    if not digits:
        return 0
    if len(digits) > 11 or not _OCTAL.issuperset(digits):
        raise _format("malformed tar number")
    return int(digits, 8)


def _padded(size: int) -> int:
    return (size + _TAR_BLOCK - 1) // _TAR_BLOCK * _TAR_BLOCK


@dataclass(frozen=True, slots=True)
class _TarEntry:
    """One non-directory tar entry: its ordinal among entries, typeflag, recorded name (data) and declared size."""

    index: int
    typeflag: str
    raw_name: bytes
    size: int
    name_too_long: bool


class _Payload:
    """The payload of the entry just yielded by :func:`_walk_tar`: read it, CRC it, or let the walker skip it."""

    def __init__(self, reader: _BlockReader, size: int) -> None:
        self._reader, self._size, self.done = reader, size, False

    def read(self) -> bytes:
        data = self._reader.read(self._size)
        self._reader.skip(_padded(self._size) - self._size)
        self.done = True
        return data

    def crc(self) -> int:
        value = self._reader.skip(self._size, crc=0)
        self._reader.skip(_padded(self._size) - self._size)
        self.done = True
        return value

    def finish(self) -> None:
        if not self.done:
            self._reader.skip(_padded(self._size))
            self.done = True


def _parse_pax(data: bytes) -> dict[bytes, bytes]:
    """The records of one pax ``x`` header (``"<len> <key>=<value>\\n"``), parsed as data and checked strictly (D-248).

    The length is decimal and must cover the record exactly, the record ends with LF, the key is ASCII and non-empty and
    appears once; any defect refuses the archive. Values stay bytes; only the allowlisted keys are ever interpreted.
    """
    records: dict[bytes, bytes] = {}
    pos = 0
    while pos < len(data):
        space = data.find(b" ", pos, pos + 21)
        digits = data[pos:space] if space > pos else b""
        if not digits or not digits.isdigit() or not digits.isascii():
            raise _format("malformed pax record length")
        length = int(digits)
        if length < len(digits) + 4 or pos + length > len(data):
            raise _format("pax record length out of range")
        record = data[space + 1 : pos + length]
        equals = record.find(b"=")
        if not record.endswith(b"\n") or equals <= 0 or not record[:equals].isascii():
            raise _format("malformed pax record")
        key = record[:equals]
        if key in records:
            raise _format("duplicate pax key")
        records[key] = record[equals + 1 : -1]
        pos += length
    return records


def _pax_overrides(records: dict[bytes, bytes]) -> tuple[bytes | None, int | None]:
    """The ``path`` and ``size`` of a pax header (closed allowlist; ignored keys dropped; anything else refuses)."""
    for key in records:
        if key not in _PAX_APPLIED and key not in _PAX_IGNORED and not key.startswith(_PAX_IGNORED_PREFIXES):
            raise _format("unsupported pax key")
    size: int | None = None
    if b"size" in records:
        value = records[b"size"]
        if not value or len(value) > 20 or not value.isdigit() or not value.isascii():
            raise _format("malformed pax size")
        size = int(value)
    return records.get(b"path"), size


def _walk_tar(fp: IO[bytes], limits: IngestLimits, codec: Codec) -> Iterator[tuple[_TarEntry, _Payload]]:
    """Walk the headers of a compressed tar from the start of ``fp`` (both passes); a structural defect rejects it."""
    fp.seek(0)
    reader = _BlockReader(iter_decompressed(fp, codec, limits, max_bytes=limits.max_tar_stream_bytes))
    pending: bytes | None = None  # a GNU long name for the next entry
    pending_too_long = False
    pax: tuple[bytes | None, int | None] | None = None  # a pax header's path and size for the next entry (D-248)
    index = 0
    while True:
        header = reader.read(_TAR_BLOCK)
        if header == _TAR_ZERO:
            if reader.read(_TAR_BLOCK) != _TAR_ZERO:
                raise _format("a single zero block inside the tar")
            if pending is not None or pending_too_long or pax is not None:
                raise _format("a long-name or pax header without its entry")
            if not reader.rest_is_zero():
                raise _format("data after the end of the tar")
            return
        stored = _tar_octal(header[148:156])
        if stored != sum(header[:148]) + 8 * 0x20 + sum(header[156:]):
            raise _format("tar header checksum mismatch")
        magic = next((m for m in _TAR_MAGICS if header[257:263] == m[0] and header[263:265] == m[1]), None)
        if magic is None:
            raise _format("not a ustar header")
        typeflag = chr(header[156])
        size = _tar_octal(header[124:136])
        if typeflag == _TAR_PAX:
            if pax is not None or pending is not None or pending_too_long:
                raise _format("a pax header after another pax or long-name header")
            if size > limits.max_pax_header_bytes:  # never buffered beyond the declared bound
                raise IngestError("ingest.archive.format", "pax header exceeds max_pax_header_bytes",
                                  limit=limits.max_pax_header_bytes)  # fmt: skip
            pax = _pax_overrides(_parse_pax(reader.read(_padded(size))[:size]))
            continue
        if typeflag == _TAR_LONGNAME:
            if pending is not None or pending_too_long or pax is not None:
                raise _format("two long-name headers in a row, or a long name after a pax header")
            if size > limits.max_name_bytes + 1:  # never buffered (obs-G1): the entry it names is rejected
                reader.skip(_padded(size))
                pending_too_long = True
            else:
                pending = reader.read(_padded(size))[:size].split(b"\x00", 1)[0]
            continue
        if typeflag not in _TAR_FILE and typeflag != _TAR_DIR and typeflag not in _TAR_NONREGULAR:
            raise _format("unsupported tar header type (pax, GNU extension or sparse)")
        name = header[0:100].split(b"\x00", 1)[0]
        prefix = header[345:500].split(b"\x00", 1)[0] if magic[2] else b""
        raw_name = pending if pending is not None else (prefix + b"/" + name if prefix else name)
        too_long = pending_too_long
        if pax is not None:
            pax_path, pax_size = pax
            if pax_path is not None:
                raw_name, too_long = pax_path, len(pax_path) > limits.max_name_bytes
            if pax_size is not None:
                size = pax_size
        pending, pending_too_long, pax = None, False, None
        if typeflag == _TAR_DIR or typeflag in _TAR_NONREGULAR:
            if size and typeflag != "1":  # a hard link may repeat its target's size; nothing follows it either way
                raise _format("a directory, link or special entry with a payload")
            size = 0
        if typeflag == _TAR_DIR:
            index += 1
            continue
        if index >= limits.max_members:
            raise IngestError("ingest.archive.members", "the tar has more entries than the limit", limit=limits.max_members)
        payload = _Payload(reader, size)
        yield _TarEntry(index, typeflag, raw_name, size, too_long), payload
        payload.finish()
        index += 1


@dataclass(frozen=True, slots=True)
class TarMember(ZipMember):
    """A gate decision for one tar entry; a selected member carries its bytes (read in stream order)."""

    _content: bytes | None = field(repr=False, compare=False, default=None)


class OpenedTar:
    """An opened compressed tar (D-57, D-240): the caller's handle, the codec, the checked entry table, findings, advisory."""

    def __init__(
        self,
        fp: IO[bytes],
        limits: IngestLimits,
        depth: int,
        advisory: InterpreterAdvisory | None,
        *,
        codec: Codec = "gzip",
    ) -> None:
        if codec not in ("gzip", "zstd"):
            raise ValueError("a tar is read from a gzip or zstd stream only")
        self._fp = fp
        self.codec: Codec = codec
        self.limits = limits
        self.depth = depth
        self.advisory = advisory
        self.findings: tuple[IngestFinding, ...] = ()
        self._labels: dict[int, str] = {}
        self._name_codes: dict[int, str] = {}
        groups: dict[str, int] = {}
        for entry, _payload in _walk_tar(fp, limits, codec):  # pass 1: the whole structure, before any member is emitted
            code: str | None = None
            if entry.name_too_long:
                code = "ingest.name.invalid"
            else:
                try:
                    label = logical_name(entry.raw_name.decode("utf-8"), limits)
                except UnicodeDecodeError:
                    code = "ingest.name.invalid"
                except IngestError as exc:
                    code = exc.code
            if code is not None:
                self._name_codes[entry.index] = code
                continue
            self._labels[entry.index] = label
            key = collision_key(label)
            groups[key] = groups.get(key, 0) + 1
        self._groups = groups

    def __enter__(self) -> OpenedTar:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        """The handle belongs to the caller (as for :func:`open_zip`); nothing is held after this."""
        self._groups.clear()

    def iter_members(self, include: Callable[[str], bool] | None, limits: IngestLimits) -> Iterator[TarMember]:
        """Pass 2: gate every entry in stream order (same order of checks as :func:`iter_zip_members`)."""
        total = 0
        for entry, payload in _walk_tar(self._fp, self.limits, self.codec):
            label = self._labels.get(entry.index)
            code: str | None = None
            detail = ""
            if entry.typeflag in _TAR_NONREGULAR:
                code, detail = "ingest.archive.link", "non-regular member (link or special file)"
            elif entry.index in self._name_codes:
                code, detail = self._name_codes[entry.index], "member name rejected"
            elif label is not None and self._groups[collision_key(label)] > 1:
                code, detail = "ingest.archive.duplicate", "name collides with another member"
            elif entry.size > limits.max_member_bytes:
                code, detail = "ingest.archive.size", "member exceeds max_member_bytes"
            elif include is not None and label is not None and not include(label):
                yield self._member(entry, label, payload.crc(), "not_selected")
                continue
            elif total + entry.size > limits.max_total_bytes:
                code, detail = "ingest.archive.size", "selected members exceed max_total_bytes"
            else:
                content = payload.read()
                total += entry.size
                yield self._member(entry, label, zlib.crc32(content), "selected", content=content)
                continue
            yield self._member(entry, label if code != "ingest.name.invalid" else None, payload.crc(), "rejected",
                               code, detail)  # fmt: skip

    def _member(self, entry: _TarEntry, label: str | None, crc: int, disposition: Disposition,
                code: str | None = None, detail: str | None = None, *, content: bytes | None = None) -> TarMember:
        name = entry.raw_name.decode("utf-8", "replace")
        return TarMember(entry.index, name, label, 0, crc, entry.size, entry.size, disposition, code, detail,
                         None, None, content)  # type: ignore[arg-type]

    def read_member(self, member: ZipMember) -> bytes:
        """The selected member's bytes, read during :meth:`iter_members` (bounded by ``max_member_bytes``)."""
        if not isinstance(member, TarMember) or member.disposition != "selected" or member._content is None:
            raise ValueError("only selected tar members carry bytes")
        return member._content
