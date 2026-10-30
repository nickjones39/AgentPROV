"""Content-addressed, immutable raw store (docs/architecture G.3.1, G.4.5, HL H.1.3, K.5.7(1); MN M.1.2).

Every byte string that enters a corpus (primary artefacts, blobs, capture logs, native logs, archive members) is one
object at ``<root>/objects/<h0h1>/<sha256>.<ext>``, mode ``0444``. The address is the sha256 of the bytes; the extension
is informative only (a closed map, :data:`EXTENSIONS`) and the first writer's extension wins.

Write protocol (G.3.1 step 1, after landscape/secure_ingestion.md section 8.2):

1. the bytes are streamed into a private temporary file in ``<root>/tmp`` (mode ``0700``, same filesystem), hashed while
   they are copied, and counted against the size cap (``max_artefact_bytes``; ``ingest.size.file``);
2. the file is ``fsync``-ed and made read-only (``0444``);
3. it is published with ``os.link``, which is atomic and fails when the target exists, so an object is never
   overwritten; on ``FileExistsError`` (or when the digest is already stored) the existing bytes are re-hashed and a
   mismatch fails loudly (``raw.digest.collision``);
4. the temporary name is removed and the shard directory is ``fsync``-ed.

Nothing in this module overwrites, renames over, edits or deletes a published object. A host whose filesystem cannot
hard-link refuses (``raw.store.link_failed``, exit 3) rather than falling back to a non-atomic publish.

:class:`RawObjectStore` satisfies the :class:`agentprov.aer.locators.RawStore` protocol exactly (``has``, ``size``,
``read_bytes``; ``KeyError`` when the object is absent, also for a malformed digest, which is never turned into a path).
The class is deliberately not named ``RawStore``, which is that protocol.

Host independence (DECISIONS D-7): no ``sys.platform`` branch; binary I/O only. Every read of a stored object goes through
``agentprov.ingest.paths.open_evidence``, the one no-follow opener (it picks its mechanism by feature test).
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import stat
import zlib
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import IO, Final

from agentprov.errors import AgentProvError, IngestError
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import iter_jsonl
from agentprov.ingest.paths import STORED_OBJECT_LIMITS, open_evidence
from agentprov.io.atomic import _fsync_dir, sweep_stale_tmp, tmp_path_for
from agentprov.io.canonical import is_sha256_hex

__all__ = [
    "EXTENSIONS",
    "MEDIA_TYPE_EXTENSIONS",
    "DigestCollisionError",
    "LimitedField",
    "ObjectCorruptError",
    "ObjectMismatchError",
    "PutResult",
    "RawObjectStore",
    "RawStoreError",
    "ext_for_label",
    "ext_for_media",
    "limit_field_for",
    "put_stream",
    "violation_detail",
]

#: The closed set of object extensions (HL H.1.3(3)); informative only, the address is the sha256.
EXTENSIONS: Final = frozenset({"json", "jsonl", "zip", "csv", "eval", "bin"})
#: Media type to extension. ``eval`` (an Inspect archive) is chosen explicitly by the reader that recognised it.
MEDIA_TYPE_EXTENSIONS: Final = MappingProxyType(
    {
        "application/json": "json",
        "application/jsonl": "jsonl",
        "application/x-ndjson": "jsonl",
        "application/zip": "zip",
        "text/csv": "csv",
    }
)
_LABEL_SUFFIXES: Final = MappingProxyType(
    {".json": "json", ".jsonl": "jsonl", ".zip": "zip", ".csv": "csv", ".eval": "eval"}
)

_OPEN_FLAGS: Final = getattr(os, "O_BINARY", 0) | getattr(os, "O_CLOEXEC", 0)
_CHUNK: Final = 1 << 20


class RawStoreError(AgentProvError):
    """Base of the raw-store errors; ``raw.*`` codes (HL H.6.3, K.5.7)."""

    code = "raw.store.error"
    exit_code = 1


class DigestCollisionError(RawStoreError):
    """Bytes already stored at this digest do not hash to it (store corruption or tampering): ``raw.digest.collision``."""

    code = "raw.digest.collision"


class ObjectCorruptError(RawStoreError):
    """A stored object failed its digest check on read or on :meth:`RawObjectStore.verify`."""

    code = "raw.object.corrupt"


class ObjectMismatchError(RawStoreError):
    """The streamed bytes differ from what the caller expected (digest, size or CRC-32); nothing was published."""

    code = "raw.object.mismatch"


@dataclass(frozen=True, slots=True)
class PutResult:
    """The outcome of a put: ``created`` is false when the digest was already stored (idempotent put).

    ``tombstoned`` is true when the digest is listed in the store's ``tombstones.jsonl`` (a purged object, G.9.6, D-46):
    nothing was written, ``path`` is where the object would have been, and the caller must not expect to read it.
    """

    sha256: str
    size: int
    path: Path
    created: bool
    tombstoned: bool = False


def ext_for_media(media_type: str | None) -> str:
    """The extension for a media type (HL H.1.3(3)); ``bin`` for anything not in the closed map."""
    if media_type is None:
        return "bin"
    return MEDIA_TYPE_EXTENSIONS.get(media_type.split(";", 1)[0].strip().lower(), "bin")


def ext_for_label(label: str) -> str:
    """The extension for an archive member label, from its (case-folded) suffix; ``bin`` otherwise.

    The label is only inspected, never used as a path.
    """
    lowered = label.lower()
    for suffix, ext in _LABEL_SUFFIXES.items():
        if lowered.endswith(suffix):
            return ext
    return "bin"


# --------------------------------------------------------------------------------------------------------------
# Register-row text for resource and safety violations (G.3.9): sha256 when computable, size, effective limit
# --------------------------------------------------------------------------------------------------------------

#: The :class:`IngestLimits` field that bounds each closed code; ``ingest.archive.size`` is decided by the caller
#: (member versus total), and the codes without a numeric limit are absent.
_LIMIT_FIELDS: Final = MappingProxyType(
    {
        "ingest.size.file": "max_artefact_bytes",
        "ingest.size.record": "max_jsonl_line_bytes",
        "ingest.archive.cd": "max_cd_bytes",
        "ingest.archive.members": "max_members",
        "ingest.archive.ratio": "max_ratio",
        "ingest.archive.depth": "max_archive_depth",
        "ingest.archive.method": "zip_methods",
        "ingest.archive.size": "max_member_bytes",
        "ingest.name.invalid": "max_name_bytes",
    }
)


@dataclass(frozen=True, slots=True)
class LimitedField:
    """An effective limit: the :class:`IngestLimits` field name and its value."""

    field: str
    value: int | float | list[int]


def limit_field_for(code: str, limits: IngestLimits, *, field: str | None = None) -> LimitedField | None:
    """The effective limit behind ``code`` (``None`` when the code has no numeric limit).

    ``field`` overrides the table, for ``ingest.archive.size`` raised against ``max_total_bytes``.
    """
    name = field or _LIMIT_FIELDS.get(code)
    if name is None:
        return None
    value = limits.to_json()[name]
    return LimitedField(name, value)


def violation_detail(
    *,
    sha256: str | None = None,
    size: int | None = None,
    limit: LimitedField | None = None,
    container: str | None = None,
    reason: str | None = None,
) -> str:
    """The generated ``register.jsonl`` ``detail`` of an ``ingest.*`` row (HL H.6.2: at most 200 characters, never source text).

    Format: ``;``-separated ``key=value`` items in the fixed order ``container``, ``sha256``, ``size``, ``limit``,
    ``reason``. Every value is a digest, an integer, a field name or a fixed phrase chosen by the caller.
    """
    parts: list[str] = []
    if container is not None:
        parts.append(f"container={container}")
    if sha256 is not None:
        parts.append(f"sha256={sha256}")
    if size is not None:
        parts.append(f"size={size}")
    if limit is not None:
        value = ",".join(map(str, limit.value)) if isinstance(limit.value, list) else str(limit.value)
        parts.append(f"limit={limit.field}:{value}")
    if reason is not None:
        parts.append(reason)
    text = "; ".join(parts)
    return text if len(text) <= 200 else text[:197] + "..."


# --------------------------------------------------------------------------------------------------------------
# The store
# --------------------------------------------------------------------------------------------------------------


def _is_real_dir(path: Path) -> bool:
    try:
        return stat.S_ISDIR(os.lstat(path).st_mode)
    except OSError:
        return False


#: The purge tombstones of a store, beside ``objects/`` (HL H.1.2; written by ``agentprov purge``, D-46). The fetch cache
#: keeps its own at ``<cache>/tombstones.jsonl``.
TOMBSTONES_NAME: Final = "tombstones.jsonl"


def read_tombstones(root: Path, limits: IngestLimits | None = None) -> frozenset[str]:
    """The digests listed in ``root/tombstones.jsonl`` (empty when there is none); strict and fail-closed.

    A file that is not a regular, non-linked file of ``{"sha256": "sha256:<hex>", ...}`` JSONL rows raises
    ``raw.store.tombstones_invalid``, so a damaged file can never re-admit a purged object.
    """
    limits = limits or IngestLimits()
    if not os.path.lexists(root / TOMBSTONES_NAME):
        return frozenset()
    digests: set[str] = set()
    try:
        with open_evidence(root, TOMBSTONES_NAME, limits) as handle:
            for _line, _offset, row in iter_jsonl(handle, limits):
                digest = row.get("sha256") if isinstance(row, dict) else None
                if not isinstance(digest, str) or not digest.startswith("sha256:") or not is_sha256_hex(digest[7:]):
                    raise RawStoreError("a tombstone row needs sha256:<hex>", code="raw.store.tombstones_invalid")
                digests.add(digest[7:])
    except IngestError as exc:
        raise RawStoreError(f"{TOMBSTONES_NAME} cannot be read safely ({exc.code})",
                            code="raw.store.tombstones_invalid") from None  # fmt: skip
    return frozenset(digests)


class RawObjectStore:
    """The raw store of one corpus (or one fetch cache), rooted at ``root`` (``<corpus>/raw``).

    ``root/objects`` holds the objects and ``root/tmp`` (mode ``0700``) the temporary files of in-flight writes; the
    ``tmp`` directory must be empty when a corpus is sealed (phase 11). ``create=False`` opens an existing store
    read-only: no directory is created or modified. ``verify_on_read`` makes :meth:`read_bytes` re-hash what it reads.
    """

    def __init__(
        self,
        root: str | os.PathLike[str],
        *,
        limits: IngestLimits | None = None,
        create: bool = True,
        verify_on_read: bool = False,
    ) -> None:
        self.root = Path(root)
        self.limits = limits or IngestLimits()
        self.verify_on_read = verify_on_read
        self.objects_dir = self.root / "objects"
        self.tmp_dir = self.root / "tmp"
        self._tombstones: tuple[tuple[int, int, int], frozenset[str]] | None = None
        if create:
            self.root.mkdir(parents=True, exist_ok=True)
            self._ensure_dir(self.root, 0o755)
            self._ensure_dir(self.objects_dir, 0o755)
            self._ensure_dir(self.tmp_dir, 0o700)
            os.chmod(self.tmp_dir, 0o700)  # G.3.8(5): private even if it pre-existed with looser bits
            sweep_stale_tmp(self.tmp_dir)
        elif not _is_real_dir(self.objects_dir):
            raise RawStoreError(f"no raw object store at {self.objects_dir.name}", code="raw.store.missing")

    @staticmethod
    def _ensure_dir(path: Path, mode: int) -> None:
        try:
            os.mkdir(path, mode)
        except FileExistsError:
            pass
        if not _is_real_dir(path):
            raise RawStoreError("raw store directory is not a real directory", code="raw.store.not_directory")

    # ----------------------------------------------------------------------------------------- addressing
    def path_for(self, sha256: str, ext: str = "bin") -> Path:
        """The object path for a digest and extension (no I/O). ``ValueError`` for a malformed digest or extension."""
        if not is_sha256_hex(sha256):
            raise ValueError("not a sha256 hex digest")
        if ext not in EXTENSIONS:
            raise ValueError("extension is not in the closed map")
        return self.objects_dir / sha256[:2] / f"{sha256}.{ext}"

    def _find(self, sha256: str) -> Path | None:
        """The unique stored object for ``sha256`` whatever its extension; ``None`` if absent."""
        if not is_sha256_hex(sha256):
            return None
        shard = self.objects_dir / sha256[:2]
        prefix = sha256 + "."
        try:
            shard_mode = os.lstat(shard).st_mode
        except FileNotFoundError:
            return None
        if not stat.S_ISDIR(shard_mode):  # a symlinked or replaced shard directory is never followed
            raise RawStoreError("raw store shard is not a real directory", code="raw.store.not_directory")
        try:
            with os.scandir(shard) as it:
                names = sorted(e.name for e in it if e.name.startswith(prefix))
        except FileNotFoundError:
            return None
        if not names:
            return None
        if len(names) > 1:
            raise RawStoreError("several stored objects share one digest", code="raw.object.ambiguous")
        path = shard / names[0]
        mode = os.lstat(path).st_mode
        if not stat.S_ISREG(mode):
            raise RawStoreError("stored object is not a regular file", code="raw.object.invalid")
        return path

    # ----------------------------------------------------------------------------------------- RawStore protocol
    def has(self, sha256: str) -> bool:
        """Whether an object with this digest is stored."""
        return self._find(sha256) is not None

    def size(self, sha256: str) -> int:
        """Byte length of the stored object; ``KeyError`` when absent."""
        path = self._find(sha256)
        if path is None:
            raise KeyError(sha256)
        return os.lstat(path).st_size

    def read_bytes(self, sha256: str) -> bytes:
        """The stored bytes; ``KeyError`` when absent. Re-hashed first when the store was built with ``verify_on_read``."""
        path = self._find(sha256)
        if path is None:
            raise KeyError(sha256)
        with self._open(path) as handle:
            data = handle.read()
        if self.verify_on_read and hashlib.sha256(data).hexdigest() != sha256:
            raise ObjectCorruptError("stored object failed its digest check")
        return data

    # ----------------------------------------------------------------------------------------- reading
    @staticmethod
    def _open(path: Path) -> IO[bytes]:
        """Open ``<objects>/<shard>/<name>`` through the one no-follow opener (a link or special file is refused)."""
        try:
            return open_evidence(
                path.parent.parent, f"{path.parent.name}/{path.name}", STORED_OBJECT_LIMITS, allow_hardlinks=True
            )
        except IngestError as exc:
            if exc.code in ("ingest.path.symlink", "ingest.path.special"):
                raise RawStoreError("stored object is not a regular file", code="raw.object.invalid") from None
            raise

    def open(self, sha256: str) -> IO[bytes]:
        """A read-only binary handle on a stored object (no-follow, regular files only); ``KeyError`` when absent."""
        path = self._find(sha256)
        if path is None:
            raise KeyError(sha256)
        return self._open(path)

    def verify(self, sha256: str) -> int:
        """Stream the object through sha256; return its size. ``KeyError`` if absent, :class:`ObjectCorruptError` on mismatch."""
        hasher = hashlib.sha256()
        total = 0
        with self.open(sha256) as handle:
            while chunk := handle.read(_CHUNK):
                hasher.update(chunk)
                total += len(chunk)
        if hasher.hexdigest() != sha256:
            raise ObjectCorruptError("stored object failed its digest check")
        return total

    def digests(self) -> Iterator[str]:
        """Every stored digest, sorted bytewise (diagnostics and the corpus raw-set computation)."""
        try:
            with os.scandir(self.objects_dir) as it:
                shards = sorted(e.name for e in it if len(e.name) == 2 and e.is_dir(follow_symlinks=False))
        except FileNotFoundError:
            return
        for shard in shards:
            with os.scandir(self.objects_dir / shard) as it:
                stems = sorted(
                    e.name.split(".", 1)[0] for e in it if is_sha256_hex(e.name.split(".", 1)[0])
                )
            yield from stems

    # ----------------------------------------------------------------------------------------- writing
    def put(
        self,
        data: bytes,
        *,
        ext: str = "bin",
        max_bytes: int | None = None,
        expected_sha256: str | None = None,
        expected_size: int | None = None,
        expected_crc32: int | None = None,
    ) -> PutResult:
        """Store ``data`` (idempotent). See :meth:`put_chunks` for the arguments."""
        return self.put_chunks(
            (data,),
            ext=ext,
            max_bytes=max_bytes,
            declared_size=len(data),
            expected_sha256=expected_sha256,
            expected_size=expected_size,
            expected_crc32=expected_crc32,
        )

    def put_stream(
        self,
        fp: IO[bytes],
        *,
        ext: str = "bin",
        chunk_size: int = _CHUNK,
        max_bytes: int | None = None,
        declared_size: int | None = None,
        expected_sha256: str | None = None,
        expected_size: int | None = None,
        expected_crc32: int | None = None,
    ) -> PutResult:
        """Store the bytes of the binary stream ``fp`` (``agentprov.raw.store.put_stream`` of G.3.1)."""
        return self.put_chunks(
            iter(lambda: fp.read(chunk_size), b""),
            ext=ext,
            max_bytes=max_bytes,
            declared_size=declared_size,
            expected_sha256=expected_sha256,
            expected_size=expected_size,
            expected_crc32=expected_crc32,
        )

    def put_chunks(
        self,
        chunks: Iterable[bytes],
        *,
        ext: str = "bin",
        max_bytes: int | None = None,
        declared_size: int | None = None,
        expected_sha256: str | None = None,
        expected_size: int | None = None,
        expected_crc32: int | None = None,
    ) -> PutResult:
        """Hash while copying, enforce the size cap, then publish atomically (G.3.1 step 1).

        * ``max_bytes`` defaults to ``limits.max_artefact_bytes``. ``declared_size`` (for example an ``fstat`` size)
          above the cap refuses before anything is written. Both raise ``IngestError("ingest.size.file")`` and publish
          nothing; no temporary file survives.
        * ``expected_sha256`` / ``expected_size`` / ``expected_crc32`` are checked before publishing; a difference
          raises :class:`ObjectMismatchError` and nothing is published.
        * The result's ``created`` is false when the digest was already stored; the existing bytes are re-hashed and
          :class:`DigestCollisionError` is raised if they do not hash to their address. An existing object keeps its
          extension.
        * A digest listed in :meth:`tombstoned` is not published (``tombstoned=True``; D-46): a re-import after
          ``agentprov purge`` cannot write the purged bytes back.
        """
        if ext not in EXTENSIONS:
            raise ValueError("extension is not in the closed map")
        limit = self.limits.max_artefact_bytes if max_bytes is None else max_bytes
        if declared_size is not None and declared_size > limit:
            raise IngestError("ingest.size.file", f"object of {declared_size} bytes exceeds the limit", limit=limit)
        if not self.tmp_dir.is_dir():
            raise RawStoreError("raw store is not writable (opened with create=False)", code="raw.store.read_only")
        tmp = self._new_tmp_path()
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _OPEN_FLAGS, 0o600)
        hasher = hashlib.sha256()
        crc = 0
        total = 0
        try:
            with os.fdopen(fd, "wb") as out:
                for chunk in chunks:
                    total += len(chunk)
                    if total > limit:
                        raise IngestError(
                            "ingest.size.file", f"object exceeds the limit (at least {total} bytes)", limit=limit
                        )
                    hasher.update(chunk)
                    crc = zlib.crc32(chunk, crc)
                    out.write(chunk)
                out.flush()
                os.fsync(out.fileno())
            digest = hasher.hexdigest()
            if expected_sha256 is not None and digest != expected_sha256:
                raise ObjectMismatchError("streamed bytes do not hash to the expected digest")
            if expected_size is not None and total != expected_size:
                raise ObjectMismatchError("streamed byte count differs from the expected size")
            if expected_crc32 is not None and crc != expected_crc32:
                raise ObjectMismatchError("streamed bytes do not match the expected CRC-32")
            if digest in self.tombstoned():  # a purged object is never written back (G.9.6, D-46; F-12C-05)
                return PutResult(digest, total, self.path_for(digest, ext), False, tombstoned=True)
            existing = self._find(digest)
            if existing is not None:
                self._require_intact(existing, digest)
                return PutResult(digest, total, existing, False)
            target = self.path_for(digest, ext)
            self._ensure_dir(target.parent, 0o755)
            os.chmod(tmp, 0o444)
            created = self._publish(tmp, target, digest)
            return PutResult(digest, total, target, created)
        finally:
            self._discard(tmp)

    def tombstoned(self) -> frozenset[str]:
        """The digests a purge removed from this store (``root/tombstones.jsonl``); they are never stored again (D-46).

        Read strictly and fail closed: a tombstone file that is not a regular file of ``{"sha256": "sha256:<hex>", ...}``
        rows raises ``raw.store.tombstones_invalid``, so a damaged file can never re-admit a purged object. Re-read when
        the file changes (``agentprov purge`` writes it atomically under the corpus lock).
        """
        try:
            st = os.lstat(self.root / TOMBSTONES_NAME)
        except FileNotFoundError:
            return frozenset()
        key = (st.st_ino, st.st_size, st.st_mtime_ns)
        if self._tombstones is None or self._tombstones[0] != key:
            self._tombstones = (key, read_tombstones(self.root, self.limits))
        return self._tombstones[1]

    def _new_tmp_path(self) -> Path:
        # Same naming as io.atomic (``<name>.tmp-<pid>``), so the stale-temporary sweep applies to it.
        return tmp_path_for(self.tmp_dir / os.urandom(12).hex())

    @staticmethod
    def _discard(tmp: Path) -> None:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            return
        except PermissionError:
            # A host that cannot unlink a read-only name; the temporary name is private, so make it writable and retry.
            with contextlib.suppress(OSError):
                os.chmod(tmp, 0o600)
            with contextlib.suppress(OSError):
                os.unlink(tmp)

    def _publish(self, tmp: Path, target: Path, digest: str) -> bool:
        try:
            os.link(tmp, target)
        except FileExistsError:
            self._require_intact(target, digest)
            return False
        except OSError as exc:
            raise RawStoreError(
                f"cannot publish a raw object: hard links are unavailable here ({exc.strerror})",
                code="raw.store.link_failed",
                exit_code=3,
            ) from None
        self._discard(tmp)
        if os.stat(target).st_mode & 0o222:
            os.chmod(target, 0o444)  # a host where the discard had to make the shared name writable
        _fsync_dir(target.parent)
        return True

    def _require_intact(self, path: Path, digest: str) -> None:
        hasher = hashlib.sha256()
        with self._open(path) as handle:
            while chunk := handle.read(_CHUNK):
                hasher.update(chunk)
        if hasher.hexdigest() != digest:
            raise DigestCollisionError("existing object at this digest does not hash to it; refusing to overwrite")


def put_stream(
    store: RawObjectStore,
    fp: IO[bytes],
    *,
    ext: str = "bin",
    max_bytes: int | None = None,
    declared_size: int | None = None,
    expected_sha256: str | None = None,
    expected_size: int | None = None,
    expected_crc32: int | None = None,
) -> PutResult:
    """``agentprov.raw.store.put_stream`` (G.3.1): stream ``fp`` into ``store``; see :meth:`RawObjectStore.put_chunks`."""
    return store.put_stream(
        fp,
        ext=ext,
        max_bytes=max_bytes,
        declared_size=declared_size,
        expected_sha256=expected_sha256,
        expected_size=expected_size,
        expected_crc32=expected_crc32,
    )
