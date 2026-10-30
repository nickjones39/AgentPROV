"""SEC-06 (K.12.8): v0.1 decompresses only zip members (methods 8 and 93) and compressed tars (D-57, D-240).

Single streams are stored inert. A top-level bzip2 or xz stream is never decompressed; a top-level zstd or gzip stream has at
most its first tar block decoded (zstd after its frame header checks), to tell a ``tar.zst`` (D-240) or ``tar.gz`` (D-247)
from a deferred single stream.
"""

from __future__ import annotations

import bz2
import gzip
import io
import lzma
import struct
import time
import warnings
import zipfile
import zlib
from compression import zstd

import pytest

from agentprov.errors import IngestError
from agentprov.ingest.archives import iter_zip_members, open_archive, open_zip
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.streams import open_compressed_bounded, sniff_codec, sniff_container

LIMITS = IngestLimits()
PAYLOAD = b'{"k": "v"}\n' * 100


def one_member_zip(data: bytes, method: int, name: str = "m") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        info = zipfile.ZipInfo(name)
        info.filename = info.orig_filename.split("\0", 1)[0]  # ZipInfo rewrites os.sep to "/" on some hosts
        info.compress_type = method
        z.writestr(info, data)
    return buf.getvalue()


def first_member(data: bytes, limits: IngestLimits = LIMITS):
    z = open_zip(io.BytesIO(data), limits, release=False)
    return z, next(iter(iter_zip_members(z)))


# ------------------------------------------------------------------------------------ single streams: inert
STREAMS = {
    "gzip": gzip.compress(PAYLOAD),
    "bzip2": bz2.compress(PAYLOAD),
    "xz": lzma.compress(PAYLOAD),
    "zstd": zstd.compress(PAYLOAD),
}


@pytest.fixture
def no_decompression(monkeypatch):
    def fail(*a, **k):
        raise AssertionError("a single stream was decompressed")

    monkeypatch.setattr(gzip, "decompress", fail)
    monkeypatch.setattr(gzip, "GzipFile", fail)
    monkeypatch.setattr(bz2, "BZ2Decompressor", fail)
    monkeypatch.setattr(lzma, "LZMADecompressor", fail)
    monkeypatch.setattr(zstd, "ZstdDecompressor", fail)
    monkeypatch.setattr(zlib, "decompressobj", fail)


@pytest.mark.parametrize("codec", sorted(set(STREAMS) - {"zstd", "gzip"}))
def test_sec06_a_single_stream_is_recognised_by_magic_and_never_decompressed(codec, no_decompression):
    data = STREAMS[codec]
    assert sniff_codec(data[:8]) == codec and sniff_container(data[:8]) == codec
    for opener in (
        lambda fp: open_archive(fp, release=False),
        lambda fp: open_compressed_bounded(fp, release=False),
    ):
        with pytest.raises(IngestError) as info:
            opener(io.BytesIO(data))
        assert info.value.code == "ingest.stream.codec"


def test_sec06_a_zstd_single_stream_is_sniffed_for_a_tar_and_stays_deferred(monkeypatch):
    """D-240: the first block is decoded (bounded) to look for a tar header; JSON in zstd stays a deferred stream."""
    decoded: list[int] = []
    real = zstd.ZstdDecompressor

    class Counting:
        def __init__(self, *args, **kwargs):
            self._inner = real(*args, **kwargs)

        def __getattr__(self, name):
            return getattr(self._inner, name)

        def decompress(self, data, max_length=-1):
            out = self._inner.decompress(data, max_length)
            decoded.append(len(out))
            return out

    monkeypatch.setattr(zstd, "ZstdDecompressor", Counting)
    data = zstd.compress(PAYLOAD * 1000)
    with pytest.raises(IngestError) as info:
        open_archive(io.BytesIO(data), release=False)
    assert info.value.code == "ingest.stream.codec"
    assert 0 < sum(decoded) <= 512  # at most one tar block was decoded
    with pytest.raises(IngestError) as info:
        open_compressed_bounded(io.BytesIO(data), release=False)
    assert info.value.code == "ingest.stream.codec"


def test_sec06_a_gzip_bomb_as_a_single_stream_costs_one_block(monkeypatch):
    """D-247: a top-level gzip is sniffed for a tar header (at most one 512-byte block decoded) and stays deferred."""
    bomb = gzip.compress(bytes(64 * 1024 * 1024), 9)
    decoded: list[int] = []
    real = zlib.decompressobj

    class Counting:
        def __init__(self, *args, **kwargs):
            self._inner = real(*args, **kwargs)

        def __getattr__(self, name):
            return getattr(self._inner, name)

        def decompress(self, data, max_length=0):
            out = self._inner.decompress(data, max_length)
            decoded.append(len(out))
            return out

    monkeypatch.setattr(zlib, "decompressobj", Counting)
    with pytest.raises(IngestError) as info:
        open_archive(io.BytesIO(bomb), release=False)
    assert info.value.code == "ingest.stream.codec"
    assert sum(decoded) <= 512
    with pytest.raises(IngestError) as info:
        open_compressed_bounded(io.BytesIO(STREAMS["gzip"]), release=False)
    assert info.value.code == "ingest.stream.codec"


# ------------------------------------------------------------------------------------ zip members
def test_sec06_deflate_member_bomb_is_stopped_by_the_ratio_gate(monkeypatch):
    data = one_member_zip(bytes(16 * 1024 * 1024), zipfile.ZIP_DEFLATED)
    monkeypatch.setattr(zlib, "decompressobj", lambda *a, **k: pytest.fail("decompressed"))
    z, member = first_member(data)
    assert (member.disposition, member.code) == ("rejected", "ingest.archive.ratio")
    z.close()


def test_sec06_zstd_member_bomb_is_stopped_by_the_ratio_gate(monkeypatch):
    data = one_member_zip(bytes(16 * 1024 * 1024), zipfile.ZIP_ZSTANDARD)
    assert len(data) < 5000
    monkeypatch.setattr(zstd, "ZstdDecompressor", lambda *a, **k: pytest.fail("decompressed"))
    z, member = first_member(data)
    assert (member.disposition, member.code) == ("rejected", "ingest.archive.ratio")
    z.close()


def patch_sizes(data: bytes, usize: int) -> bytes:
    """Make both the central and the local header claim ``usize`` for the first member."""
    buf = bytearray(data)
    cd = buf.rfind(b"PK\x01\x02")
    struct.pack_into("<L", buf, cd + 24, usize)
    local = struct.unpack_from("<L", buf, cd + 42)[0]
    struct.pack_into("<L", buf, local + 22, usize)
    return bytes(buf)


@pytest.mark.parametrize("method", [zipfile.ZIP_DEFLATED, zipfile.ZIP_ZSTANDARD])
def test_sec06_declared_size_lie_is_bounded_for_both_codecs(method):
    data = patch_sizes(one_member_zip(bytes(20 * 1024 * 1024), method), 1000)
    z, member = first_member(data)
    assert member.disposition == "selected"
    total = 0
    start = time.monotonic()
    with pytest.raises(IngestError) as info:
        for chunk in member.iter_chunks():
            total += len(chunk)
    assert info.value.code in {"ingest.archive.crc", "ingest.archive.size"}
    assert total <= 1000 and time.monotonic() - start < 5
    z.close()


def test_sec06_zstd_frame_with_an_oversized_window_is_rejected_with_the_memory_code():
    options = {zstd.CompressionParameter.window_log: LIMITS.zstd_window_log_max + 1}
    size = 2 ** (LIMITS.zstd_window_log_max + 1) - 2**20  # content larger than the permitted 128 MiB window
    frame = zstd.compress(bytes(size), options=options)
    # Build a zip entry around the raw frame so the container itself is valid.
    data = bytearray(one_member_zip(b"x" * 10, zipfile.ZIP_STORED))
    name_at = data.find(b"x" * 10)
    local = data.rfind(b"PK\x03\x04", 0, name_at)
    body = bytes(data[:name_at]) + frame
    cd_old = data.rfind(b"PK\x01\x02")
    cd = bytearray(data[cd_old:-22])
    struct.pack_into("<H", cd, 10, 93)
    struct.pack_into("<L", cd, 16, zlib.crc32(bytes(size)))
    struct.pack_into("<L", cd, 20, len(frame))
    struct.pack_into("<L", cd, 24, size)
    body = bytearray(body)
    struct.pack_into("<H", body, local + 8, 93)
    struct.pack_into("<L", body, local + 14, zlib.crc32(bytes(size)))
    struct.pack_into("<L", body, local + 18, len(frame))
    struct.pack_into("<L", body, local + 22, size)
    end = struct.pack("<4s4H2LH", b"PK\x05\x06", 0, 0, 1, 1, len(cd), len(body), 0)
    z, member = first_member(bytes(body) + bytes(cd) + end, LIMITS.replace(max_member_bytes=size + 1, max_ratio=10**9))
    assert member.disposition == "selected" and member.method == 93
    with pytest.raises(IngestError) as info:
        b"".join(member.iter_chunks())
    assert info.value.code == "ingest.stream.memory"
    z.close()


@pytest.mark.parametrize("method", [zipfile.ZIP_DEFLATED, zipfile.ZIP_ZSTANDARD])
def test_sec06_truncated_compressed_member_is_a_typed_error(method):
    data = bytearray(one_member_zip(bytes(range(256)) * 200, method))
    cd = data.rfind(b"PK\x01\x02")
    csize = struct.unpack_from("<L", data, cd + 20)[0]
    half = csize // 2
    struct.pack_into("<L", data, cd + 20, half)  # the central directory now claims half of the compressed bytes
    local = struct.unpack_from("<L", data, cd + 42)[0]
    struct.pack_into("<L", data, local + 18, half)
    z, member = first_member(bytes(data))
    with pytest.raises(IngestError) as info:
        b"".join(member.iter_chunks())
    assert info.value.code in {"ingest.stream.truncated", "ingest.archive.format", "ingest.archive.size", "ingest.archive.crc"}
    z.close()


def test_sec06_corrupt_compressed_bytes_never_raise_untyped_exceptions():
    for method in (zipfile.ZIP_DEFLATED, zipfile.ZIP_ZSTANDARD):
        data = bytearray(one_member_zip(bytes(range(256)) * 50, method))
        at = data.find(b"PK\x01\x02")
        for pos in range(30 + 1 + 8, min(at, 30 + 60)):
            mutated = bytearray(data)
            mutated[pos] ^= 0xA5
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    z, member = first_member(bytes(mutated))
                    if member.disposition == "selected":
                        b"".join(member.iter_chunks())
                    z.close()
            except IngestError:
                pass


def test_sec06_zip_member_decompression_never_allocates_beyond_the_declared_size():
    # A deflate stream that expands to 40 MiB under a header that declares 1 KiB: read in 64 KiB chunks, at most 1 KiB taken.
    data = patch_sizes(one_member_zip(bytes(40 * 1024 * 1024), zipfile.ZIP_DEFLATED), 1024)
    z, member = first_member(data)
    seen = []
    with pytest.raises(IngestError):
        for chunk in member.iter_chunks(65536):
            seen.append(len(chunk))
    assert sum(seen) <= 1024
    z.close()
