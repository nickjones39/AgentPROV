"""T1 job ``zip_local``: a partial read of a zip whose central directory cannot be used, for the decoded scan (D-453).

The ``expand`` job reads a zip through its central directory, so a zip cut before it (Inspect ``.eval`` logs truncated at
a size cap, phase 10p) or with a damaged one is rejected whole. :mod:`agentprov.corpus.withhold_scan` then runs this job,
which never relies on the central directory: it walks the **local file headers** from offset 0, in order.

* A stored entry (method 0) whose size the header gives is read by that size, and its bytes are what the cut left of it.
* A deflated entry (method 8) is streamed through zlib up to the end of its deflate stream or the end of the object,
  whichever comes first; the decoded bytes are what any reader of that entry recovers.
* An encrypted entry, another method, and a stored entry of unknown size (general-purpose flag bit 3 with sizes 0) are
  **not read**: a row with a closed code, which keeps the archive unscanned.
* A deflate stream that breaks (invalid data) gives what it decoded so far; nothing after the break in that entry decodes
  in any reader, and the walk goes on with the next local header.
* A local header with an empty name is not an entry. After each entry, and on any bytes that are not a local header,
  the walk resyncs to the next ``PK 03 04``; the bytes
  in between are raw-scanned as stored by the caller anyway (data descriptors, the central directory, an end record).

Every entry is bounded by ``max_member_bytes``, the decode by ``max_ratio`` against the compressed bytes consumed, the
whole walk by ``max_total_bytes`` and ``max_members`` (:class:`agentprov.ingest.limits.IngestLimits`); a limit stops the
walk with its ``ingest.archive.*`` code. Nothing is stored or extracted: decoded entries go back to the parent as member
frames (header ``{index, label, size, truncated}``), read in memory up to the member bound, exactly as ``expand`` sends
selected members. Labels are labels, never paths.

Frames, in archive order: per entry either a member header and its ``DATA`` frames, or ``{"row": {index, label, code}}``
for an entry that was not read. The counters are ``entries``, ``read``, ``not_read``, ``truncated`` and ``resyncs``.
"""

from __future__ import annotations

import struct
import zlib
from typing import IO, TYPE_CHECKING, Any, Final

from agentprov.errors import IngestError
from agentprov.ingest.limits import IngestLimits

if TYPE_CHECKING:
    from agentprov.io.workers import JobContext

__all__ = ["LOCAL_HEADER", "job_zip_local"]

LOCAL_HEADER: Final = b"PK\x03\x04"
_FIXED: Final = struct.Struct("<4sHHHHHIIIHH")  # signature .. extra length: 30 bytes
_CHUNK: Final = 1 << 20
#: A decode below this many bytes is never refused for its ratio (a short text compresses far beyond any ratio).
_RATIO_FLOOR: Final = 64 * 1024


def _label(raw: bytes, flags: int) -> str:
    """The entry name as a label: UTF-8 when flag bit 11 says so (or it decodes), else code page 437, as zipfile reads it."""
    if flags & 0x800:
        return raw.decode("utf-8", errors="replace")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp437")


def _next_header(handle: IO[bytes], start: int, end: int) -> int | None:
    """The offset of the next local header at or after ``start``, or ``None``."""
    pos = start
    carry = b""
    while pos < end:
        handle.seek(pos)
        chunk = handle.read(min(_CHUNK, end - pos))
        if not chunk:
            return None
        window = carry + chunk
        found = window.find(LOCAL_HEADER)
        if found >= 0:
            return pos - len(carry) + found
        carry = window[-(len(LOCAL_HEADER) - 1):]
        pos += len(chunk)
    return None


def _inflate(handle: IO[bytes], start: int, end: int, limits: IngestLimits) -> tuple[bytes, int, str]:
    """Decode the deflate stream at ``start``: ``(decoded bytes, compressed bytes consumed, how it ended)``, the last
    ``"end"`` (the stream's own end), ``"cut"`` (the object ends first) or ``"broken"`` (invalid deflate data: nothing
    after it in this entry decodes in any reader). Raises :class:`IngestError` past the member bound or the ratio."""
    decoder = zlib.decompressobj(-15)
    out = bytearray()
    pos = start
    consumed = 0
    while pos < end and not decoder.eof:
        handle.seek(pos)
        chunk = handle.read(min(_CHUNK, end - pos))
        if not chunk:
            break
        try:
            piece = decoder.decompress(chunk, limits.max_member_bytes + 1 - len(out))
        except zlib.error:
            return bytes(out), consumed, "broken"
        used = len(chunk) - len(decoder.unused_data)
        if decoder.unconsumed_tail:
            used -= len(decoder.unconsumed_tail)
        out += piece
        consumed += used
        pos += used
        if len(out) > limits.max_member_bytes:
            raise IngestError("ingest.archive.size", "a decoded entry exceeds the member bound")
        if len(out) > _RATIO_FLOOR and len(out) > limits.max_ratio * max(consumed, 1):
            raise IngestError("ingest.archive.ratio", "a decoded entry exceeds the compression-ratio limit")
        if used == 0 and not decoder.eof:
            break  # nothing more can be decoded from what is there
    return bytes(out), consumed, "end" if decoder.eof else "cut"


def job_zip_local(ctx: JobContext) -> dict[str, Any]:
    """T1 job ``zip_local`` (D-453; see the module docstring). Params: ``limits`` (an :class:`IngestLimits` record).
    Input 0 is the zip, opened by digest and re-hashed (G.4.5)."""
    limits = IngestLimits(**ctx.params["limits"])
    counters = {"entries": 0, "read": 0, "not_read": 0, "truncated": 0, "resyncs": 0}
    total = 0
    with ctx.open_input(0) as handle:
        handle.seek(0, 2)
        end = handle.tell()
        pos: int | None = 0
        while pos is not None and pos + _FIXED.size <= end:
            handle.seek(pos)
            fixed = handle.read(_FIXED.size)
            if len(fixed) < _FIXED.size or not fixed.startswith(LOCAL_HEADER):
                counters["resyncs"] += 1
                pos = _next_header(handle, pos + 1, end)
                continue
            _sig, _version, flags, method, _time, _date, _crc, csize, usize, nlen, elen = _FIXED.unpack(fixed)
            if nlen == 0:  # every entry has a name: four signature bytes alone do not make one
                counters["resyncs"] += 1
                pos = _next_header(handle, pos + 1, end)
                continue
            name_at = pos + _FIXED.size
            handle.seek(name_at)
            raw_name = handle.read(nlen)
            if len(raw_name) < nlen:
                break  # the cut falls inside the header: no entry content follows
            data_at = name_at + nlen + elen
            if data_at > end:
                break
            index = counters["entries"]
            counters["entries"] += 1
            if counters["entries"] > limits.max_members:
                raise IngestError("ingest.archive.members", "more local headers than the member bound")
            label = _label(raw_name, flags)
            sized = not flags & 0x08
            code = None
            if flags & 0x01:
                code = "ingest.archive.encrypted"
            elif method not in (0, 8):
                code = "ingest.archive.method"
            elif method == 0 and not sized:
                code = "ingest.archive.format"  # a stored entry of unknown length cannot be delimited
            if code is not None:
                counters["not_read"] += 1
                ctx.emit({"row": {"index": index, "label": label, "code": code}})
                pos = data_at + csize if sized and csize else _next_header(handle, data_at, end)
                continue
            if method == 0:
                if usize > limits.max_member_bytes:
                    raise IngestError("ingest.archive.size", "a stored entry exceeds the member bound")
                handle.seek(data_at)
                content = handle.read(min(csize, end - data_at))
                ended = "cut" if len(content) < csize else "end"
                consumed = len(content)
            else:
                content, consumed, ended = _inflate(handle, data_at, end, limits)
            truncated = ended != "end"
            total += len(content)
            if total > limits.max_total_bytes:
                raise IngestError("ingest.archive.size", "the decoded entries exceed the archive bound")
            counters["read"] += 1
            counters["truncated"] += int(truncated)
            ctx.member({"index": index, "label": label, "size": len(content), "truncated": truncated})
            ctx.data(content)
            if ended == "cut":
                break  # content past a cut does not exist
            nxt = data_at + max(consumed, 1)
            pos = nxt if nxt + 4 <= end and _peek(handle, nxt) == LOCAL_HEADER else _next_header(handle, nxt, end)
    return counters


def _peek(handle: IO[bytes], pos: int) -> bytes:
    handle.seek(pos)
    return handle.read(4)
