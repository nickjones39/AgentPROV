"""Container and codec sniffing, and the bounded decoders behind the tar reader (docs/architecture G.3.1 step 2, G.3.4).

Decompression of single compressed streams (gzip, bzip2, xz, zstd outside a zip) is **deferred in v0.1** (AD-10 row 16;
R-45): no v0.1 normative importer needs it. T0 recognises such a stream by magic bytes only, stores it as an inert raw
object, and records ``ingest.stream.codec`` (detail ``deferred``) in ``register.jsonl``. Decompression happens inside
zip members (methods 8 and 93, :mod:`agentprov.ingest.archives`) and for a **tar** carried in a compressed stream, which
the bounded tar reader of :mod:`agentprov.ingest.archives` drives through the two decoders here:

* :func:`iter_gzip_bounded` (D-57): one gzip member; a gzip tar is read only as a member of a zip (level 2).
* :func:`iter_zstd_bounded` (D-240): zstd frames, each header parsed with ``struct`` before the decoder sees it, so a
  skippable frame, a dictionary, a window over ``2**zstd_window_log_max`` and a declared content size over the cap are
  refused before anything is allocated; a zstd tar is read at the top level and as a member of a zip.

Both bound the output by the caller's cap (``max_tar_stream_bytes`` for a tar, D-241) and by ``max_ratio`` past
``ratio_floor_bytes``, checked as it grows, and never hold more than one output chunk. A gzip or zstd stream that does
not hold a tar stays deferred.

:func:`open_compressed_bounded` is the stable entry point a later release fills in (G.3.4 "Precondition for enabling
them"). It already honours the interpreter guard (G.3.8): it calls
:func:`agentprov.envinfo.require_patched_for_archive` first, so release mode below the floor refuses before any object is
opened, and then refuses with ``ingest.stream.codec`` because single streams are deferred.
"""

from __future__ import annotations

import io
import struct
import zlib
from collections.abc import Iterator
from dataclasses import dataclass
from typing import IO, Any, Final, Literal

from agentprov.envinfo import InterpreterAdvisory, require_patched_for_archive
from agentprov.errors import IngestError, IngestFinding
from agentprov.ingest.limits import IngestLimits

_zstd: Any
try:  # the core requires Python >= 3.14, which has compression.zstd (PEP 784); stay importable
    from compression import zstd as _zstd
except ImportError:  # pragma: no cover
    _zstd = None

ContainerKind = Literal["zip", "gzip", "bzip2", "xz", "zstd", "document"]
Codec = Literal["gzip", "bzip2", "xz", "zstd"]

SNIFF_BYTES: Final = 8

_ZIP_MAGIC: Final = b"PK\x03\x04"
_CODEC_MAGIC: Final[tuple[tuple[bytes, Codec], ...]] = (
    (b"\x1f\x8b", "gzip"),
    (b"BZh", "bzip2"),
    (b"\xfd7zXZ\x00", "xz"),
    (b"\x28\xb5\x2f\xfd", "zstd"),
)


def sniff_codec(head: bytes) -> Codec | None:
    """The single-stream codec named by the magic bytes at the start of ``head`` (G.3.4), or ``None``."""
    for magic, codec in _CODEC_MAGIC:
        if head.startswith(magic):
            return codec
    return None


def sniff_container(head: bytes) -> ContainerKind:
    """Choose the container handling from the first 8 bytes only (G.3.1 step 2).

    ``zip`` is ``PK 03 04`` at offset 0; a compressed stream is its codec name; anything else is ``document``. Nothing else
    is parsed: dialect sniffing, which reads JSON keys, runs in T1.
    """
    if head.startswith(_ZIP_MAGIC):
        return "zip"
    codec = sniff_codec(head)
    return codec if codec is not None else "document"


def _open_source(source: bytes | IO[bytes]) -> tuple[IO[bytes], int]:
    """A binary handle on ``source`` and the number of compressed bytes from its current position to the end."""
    if isinstance(source, bytes):
        return io.BytesIO(source), len(source)
    start = source.tell()
    size = source.seek(0, io.SEEK_END) - start
    source.seek(start)
    return source, size


def _check_output(total: int, size: int, cap: int, limits: IngestLimits) -> None:
    """The output bounds of every decoder here: the caller's cap, then ``max_ratio`` past ``ratio_floor_bytes``."""
    if total > cap:
        raise IngestError("ingest.stream.size", "decompressed stream exceeds its limit", limit=cap)
    if total > limits.ratio_floor_bytes and total > limits.max_ratio * max(size, 1):
        raise IngestError("ingest.stream.ratio", "decompression ratio exceeds max_ratio", limit=limits.max_ratio)


def iter_gzip_bounded(
    source: bytes | IO[bytes], limits: IngestLimits, chunk: int = 1 << 20, *, max_bytes: int | None = None
) -> Iterator[bytes]:
    """Decompress exactly one gzip member from ``source`` in chunks of at most ``chunk`` bytes (D-57; G.3.4 bounds).

    ``source`` is the compressed bytes or a binary handle positioned at the stream's start (read in ``chunk``-sized
    pieces, never whole, D-58). The output is bounded by ``max_bytes`` (default ``max_stream_bytes``; the tar reader
    passes ``max_tar_stream_bytes``, D-241) (``ingest.stream.size``) and, once past
    ``ratio_floor_bytes``, by ``max_ratio`` against the compressed size (``ingest.stream.ratio``), checked as it grows, so
    a bomb is stopped early. The gzip trailer (CRC-32 and length of the whole stream) is checked by ``zlib``
    (``ingest.archive.crc``). A stream that ends early is ``ingest.stream.truncated``; bytes after the member (a second
    member, or anything else) and a corrupt stream are ``ingest.archive.format``. Never more than ``chunk`` output bytes
    are held at once.
    """
    stream, size = _open_source(source)
    cap = limits.max_stream_bytes if max_bytes is None else max_bytes
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    read, total = 0, 0
    while not decoder.eof:
        if decoder.unconsumed_tail:
            feed = decoder.unconsumed_tail
        else:
            feed = stream.read(min(chunk, size - read)) if read < size else b""
            if not feed:
                raise IngestError("ingest.stream.truncated", "the gzip stream ends before its trailer")
            read += len(feed)
        try:
            out = decoder.decompress(feed, chunk)
        except zlib.error as exc:
            if "check" in str(exc):
                raise IngestError("ingest.archive.crc", "gzip trailer CRC-32 or length mismatch") from None
            raise IngestError("ingest.archive.format", "corrupt gzip stream") from None
        total += len(out)
        _check_output(total, size, cap, limits)
        if out:
            yield out
    if decoder.unused_data or read < size:
        raise IngestError("ingest.archive.format", "data after the gzip member")


# --------------------------------------------------------------------------------------------------------------
# zstd (D-240)
# --------------------------------------------------------------------------------------------------------------

_ZSTD_FRAME_MAGIC: Final = 0xFD2FB528
_ZSTD_MAGIC_BYTES: Final = b"\x28\xb5\x2f\xfd"
_ZSTD_SKIPPABLE_MASK: Final = 0xFFFFFFF0
_ZSTD_SKIPPABLE_MAGIC: Final = 0x184D2A50
_ZSTD_HEADER_MAX: Final = 18  # magic 4 + descriptor 1 + window 1 + dictionary id 4 + content size 8 (RFC 8878 sec. 3.1.1)
_ZSTD_DID_BYTES: Final = (0, 1, 2, 4)


@dataclass(frozen=True, slots=True)
class ZstdFrameHeader:
    """What a zstd frame header declares (RFC 8878 sec. 3.1.1.1), parsed with ``struct`` only.

    ``window_size`` is the window the decoder must allocate, computed as libzstd does: from the window descriptor, or the
    content size of a single-segment frame. ``content_size`` is ``None`` when the frame does not declare it.
    """

    header_size: int
    window_size: int
    content_size: int | None
    dictionary_id: int
    checksum: bool


def parse_zstd_frame_header(head: bytes) -> ZstdFrameHeader:
    """Parse the zstd frame header at the start of ``head`` (at most 18 bytes are looked at).

    Raises ``ingest.stream.codec`` for a skippable frame, ``ingest.archive.format`` for a bad magic or a set reserved bit,
    ``ingest.stream.truncated`` when ``head`` ends inside the header. Limits are applied by the caller.
    """
    if len(head) < 4:
        raise IngestError("ingest.stream.truncated", "the zstd stream ends inside a frame header")
    (magic,) = struct.unpack_from("<I", head)
    if magic & _ZSTD_SKIPPABLE_MASK == _ZSTD_SKIPPABLE_MAGIC:
        raise IngestError("ingest.stream.codec", "zstd skippable frame (its payload cannot be verified)")
    if magic != _ZSTD_FRAME_MAGIC:
        raise IngestError("ingest.archive.format", "not a zstd frame (or data after the last frame)")
    if len(head) < 5:
        raise IngestError("ingest.stream.truncated", "the zstd stream ends inside a frame header")
    descriptor = head[4]
    fcs_flag, single, reserved = descriptor >> 6, (descriptor >> 5) & 1, (descriptor >> 3) & 1
    checksum, did_flag = bool((descriptor >> 2) & 1), descriptor & 3
    if reserved:
        raise IngestError("ingest.archive.format", "zstd frame header reserved bit set")
    did_size = _ZSTD_DID_BYTES[did_flag]
    fcs_size = (1 if single else 0, 2, 4, 8)[fcs_flag]
    header_size = 5 + (0 if single else 1) + did_size + fcs_size
    if len(head) < header_size:
        raise IngestError("ingest.stream.truncated", "the zstd stream ends inside a frame header")
    pos = 5
    window = 0
    if not single:
        exponent, mantissa = head[pos] >> 3, head[pos] & 7
        base = 1 << (10 + exponent)
        window = base + (base >> 3) * mantissa
        pos += 1
    dictionary_id = int.from_bytes(head[pos : pos + did_size], "little")
    pos += did_size
    content_size: int | None = None
    if fcs_size:
        content_size = int.from_bytes(head[pos : pos + fcs_size], "little") + (256 if fcs_size == 2 else 0)
    if single:
        window = content_size if content_size is not None else 0
    return ZstdFrameHeader(header_size, window, content_size, dictionary_id, checksum)


def _zstd_error(exc: BaseException) -> IngestError:
    """Map a libzstd failure to a closed code (the message carries no source text)."""
    text = str(exc).lower()
    if "checksum" in text:
        return IngestError("ingest.archive.crc", "zstd content checksum mismatch")
    if "memory" in text or "window" in text:
        return IngestError("ingest.stream.memory", "zstd frame needs more memory than the window limit allows")
    if "dictionary" in text:
        return IngestError("ingest.stream.codec", "zstd frame needs a dictionary")
    return IngestError("ingest.archive.format", "corrupt zstd frame")


def iter_zstd_bounded(
    source: bytes | IO[bytes], limits: IngestLimits, chunk: int = 1 << 20, *, max_bytes: int | None = None
) -> Iterator[bytes]:
    """Decompress a zstd stream (one or more frames) from ``source`` in chunks of at most ``chunk`` bytes (D-240).

    ``source`` is the compressed bytes or a binary handle positioned at the stream's start, read ``chunk`` bytes at a
    time. Before each frame is decoded its header is parsed (:func:`parse_zstd_frame_header`): a skippable frame, a
    dictionary id, more than ``max_zstd_frames`` frames (``ingest.stream.codec``), a window over
    ``2**zstd_window_log_max`` (``ingest.stream.memory``) and a declared content size over the cap
    (``ingest.stream.size``) are refused before any allocation. Each frame gets a fresh decoder with ``window_log_max``
    set (never reused after an error); output is bounded by ``max_bytes`` (default ``max_stream_bytes``) and by
    ``max_ratio`` past ``ratio_floor_bytes``, checked as it grows. Input that ends inside a frame is
    ``ingest.stream.truncated``; bytes after the last frame that do not start a frame, and corrupt data, are
    ``ingest.archive.format``; a content checksum mismatch is ``ingest.archive.crc``.
    """
    if _zstd is None:  # pragma: no cover - the core requires Python >= 3.14
        raise IngestError("ingest.archive.method", "zstd is not supported by this interpreter")
    stream, size = _open_source(source)
    cap = limits.max_stream_bytes if max_bytes is None else max_bytes
    window_cap = 1 << limits.zstd_window_log_max
    options = {_zstd.DecompressionParameter.window_log_max: limits.zstd_window_log_max}
    read, total, frames = 0, 0, 0
    pending = b""

    def more() -> bytes:
        nonlocal read
        data = stream.read(min(chunk, size - read)) if read < size else b""
        read += len(data)
        return data

    while True:
        while len(pending) < _ZSTD_HEADER_MAX and (data := more()):
            pending += data
        if not pending:
            if frames == 0:
                raise IngestError("ingest.stream.truncated", "empty zstd stream")
            return
        if frames and len(pending) < 4 and not _ZSTD_MAGIC_BYTES.startswith(pending):
            raise IngestError("ingest.archive.format", "data after the last zstd frame")
        header = parse_zstd_frame_header(pending[:_ZSTD_HEADER_MAX])
        frames += 1
        if frames > limits.max_zstd_frames:
            raise IngestError("ingest.stream.codec", "too many zstd frames", limit=limits.max_zstd_frames)
        if header.dictionary_id:
            raise IngestError("ingest.stream.codec", "zstd frame needs a dictionary (dictionaries are not supported)")
        if header.window_size > window_cap:
            raise IngestError("ingest.stream.memory", "zstd window exceeds 2**zstd_window_log_max", limit=window_cap)
        if header.content_size is not None and total + header.content_size > cap:
            raise IngestError("ingest.stream.size", "declared zstd content size exceeds its limit", limit=cap)
        decoder = _zstd.ZstdDecompressor(options=options)
        feed, pending = pending, b""
        while not decoder.eof:
            if decoder.needs_input and not feed:
                feed = more()
                if not feed:
                    raise IngestError("ingest.stream.truncated", "the zstd stream ends inside a frame")
            try:
                out = decoder.decompress(feed, chunk)
            except _zstd.ZstdError as exc:
                raise _zstd_error(exc) from None
            feed = b""
            total += len(out)
            _check_output(total, size, cap, limits)
            if out:
                yield out
        pending = decoder.unused_data


def iter_decompressed(
    source: bytes | IO[bytes], codec: Codec, limits: IngestLimits, chunk: int = 1 << 20, *, max_bytes: int | None = None
) -> Iterator[bytes]:
    """The bounded decoder for ``codec`` (gzip or zstd; every other codec stays deferred, ``ingest.stream.codec``)."""
    if codec == "gzip":
        return iter_gzip_bounded(source, limits, chunk, max_bytes=max_bytes)
    if codec == "zstd":
        return iter_zstd_bounded(source, limits, chunk, max_bytes=max_bytes)
    raise IngestError("ingest.stream.codec", f"{codec} stream is deferred in v0.1; it is stored inert, never decompressed")


def deferred_codec_finding(codec: Codec) -> IngestFinding:
    """The ``register.jsonl`` finding for a stored-inert compressed stream (G.3.4)."""
    return IngestFinding("ingest.stream.codec", "warning", detail=f"{codec} stream stored inert; deferred")


def open_compressed_bounded(
    fp: IO[bytes], limits: IngestLimits | None = None, *, release: bool = False
) -> tuple[IO[bytes], InterpreterAdvisory | None]:
    """Deferred in v0.1: always raises ``ingest.stream.codec``.

    Calls the interpreter guard first. In release mode below the floor it raises
    :class:`~agentprov.envinfo.InterpreterUnpatchedError` (exit 3) before ``fp`` is touched. In dev mode it warns, and the
    advisory it returns would be handed back to the caller together with the stream once a codec is enabled.
    """
    require_patched_for_archive(release=release)
    del fp, limits
    raise IngestError(
        "ingest.stream.codec", "compressed single streams are deferred in v0.1 and are stored inert, never decompressed"
    )
