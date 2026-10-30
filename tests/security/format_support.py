"""Builders shared by the ``tar.zst``, split-zip and streamed-JSON suites (D-240-D-243): trusted writers of test data.

Benign archives are written with ``tarfile``/``zipfile`` and ``compression.zstd`` (writing is trusted code); hostile zstd
frame headers are built by hand from RFC 8878 sec. 3.1.1.
"""

from __future__ import annotations

import io
import struct
import tarfile
import zipfile
from collections.abc import Sequence
from compression import zstd

ZSTD_MAGIC = struct.pack("<I", 0xFD2FB528)


def tar_bytes(entries: Sequence[tuple[str, bytes | None]], fmt: int = tarfile.GNU_FORMAT) -> bytes:
    """``entries``: (name, data) for files, (name, None) for directories."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=fmt) as tf:
        for name, data in entries:
            info = tarfile.TarInfo(name)
            info.mtime = 0
            if data is None:
                info.type = tarfile.DIRTYPE
                tf.addfile(info)
            else:
                info.size = len(data)
                tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def zstd_stream(data: bytes, *, level: int = 3, window_log: int | None = None, checksum: bool = True,
                frames: int = 1) -> bytes:  # fmt: skip
    """``data`` as ``frames`` zstd frames written in streaming mode (no pledged size, so a window descriptor is present)."""
    options: dict[zstd.CompressionParameter, int] = {zstd.CompressionParameter.compression_level: level,
                                                     zstd.CompressionParameter.checksum_flag: int(checksum)}
    if window_log is not None:
        options[zstd.CompressionParameter.window_log] = window_log
    out = bytearray()
    step = max(1, -(-len(data) // frames))
    for i in range(frames):
        piece = data[i * step : (i + 1) * step]
        comp = zstd.ZstdCompressor(options=options)
        out += comp.compress(piece, zstd.ZstdCompressor.CONTINUE)
        out += comp.flush(zstd.ZstdCompressor.FLUSH_FRAME)
    return bytes(out)


def tzst(entries: Sequence[tuple[str, bytes | None]], **kwargs: int | bool) -> bytes:
    return zstd_stream(tar_bytes(entries), **kwargs)  # type: ignore[arg-type]


def frame_header(*, window_exponent: int = 13, mantissa: int = 0, dictionary_id: int | None = None,
                 content_size: int | None = None, single: bool = False, checksum: bool = False,
                 reserved: bool = False) -> bytes:  # fmt: skip
    """A hand-built zstd frame header (magic, descriptor, window descriptor, dictionary id, content size)."""
    did = b"" if dictionary_id is None else struct.pack("<I", dictionary_id)
    did_flag = 0 if dictionary_id is None else 3
    if content_size is None:
        fcs, fcs_flag = b"", 0
    else:
        fcs, fcs_flag = struct.pack("<Q", content_size), 3
    descriptor = (fcs_flag << 6) | (int(single) << 5) | (int(reserved) << 3) | (int(checksum) << 2) | did_flag
    window = b"" if single else bytes([(window_exponent << 3) | mantissa])
    return ZSTD_MAGIC + bytes([descriptor]) + window + did + fcs


def reframe(frame: bytes, header: bytes) -> bytes:
    """``frame`` with its header replaced by ``header`` (the blocks are kept)."""
    descriptor = frame[4]
    fcs_flag, single, did_flag = descriptor >> 6, (descriptor >> 5) & 1, descriptor & 3
    size = 5 + (0 if single else 1) + (0, 1, 2, 4)[did_flag] + (1 if single else 0, 2, 4, 8)[fcs_flag]
    return header + frame[size:]


def zip_bytes(members: Sequence[tuple[str, bytes]], method: int = zipfile.ZIP_DEFLATED) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", method) as z:
        for name, data in members:
            info = zipfile.ZipInfo(name, (2020, 1, 1, 0, 0, 0))
            info.compress_type = method
            z.writestr(info, data)
    return buf.getvalue()


def split(data: bytes, size: int) -> list[bytes]:
    """``data`` cut into byte parts of ``size`` (the last one shorter), as ``split -b`` does."""
    return [data[i : i + size] for i in range(0, len(data), size)]
