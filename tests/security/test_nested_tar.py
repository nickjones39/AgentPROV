"""SEC-05/07/08/09/10: a gzip tar nested in a zip is read by a bounded framing parser, never by ``tarfile`` (D-57, D-90).

Benign archives are written at test time with ``tarfile`` (writing is trusted code); hostile headers are built by hand.
Nothing is extracted: the reader yields bytes, and the working directory stays empty (``fs_guard``).
"""

from __future__ import annotations

import gzip
import io
import sys
import tarfile
import tracemalloc
import zipfile
import zlib

import pytest

from agentprov.errors import IngestError
from agentprov.ingest.archives import OpenedTar, iter_zip_members, open_archive
from agentprov.ingest.limits import IngestLimits

LIMITS = IngestLimits()
LONG = "runs/agentdojo_banking_pdef/transformers_pi_detector/" + "x" * 80 + "/user_task_0.json"  # > 100 B: an L header


def tar_bytes(entries, fmt=tarfile.GNU_FORMAT) -> bytes:
    """``entries``: (name, data) for files, (name, None) for directories, (name, ("sym"|"hard"|"fifo", target))."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=fmt) as tf:
        for name, data in entries:
            info = tarfile.TarInfo(name)
            info.mtime = 0
            if data is None:
                info.type = tarfile.DIRTYPE
                tf.addfile(info)
            elif isinstance(data, tuple):
                kind, target = data
                info.type = {"sym": tarfile.SYMTYPE, "hard": tarfile.LNKTYPE, "fifo": tarfile.FIFOTYPE}[kind]
                info.linkname = target
                tf.addfile(info)
            else:
                info.size = len(data)
                tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def tgz(entries, fmt=tarfile.GNU_FORMAT) -> bytes:
    return gzip.compress(tar_bytes(entries, fmt), mtime=0)


def header(name: bytes, typeflag: bytes, size: int, *, magic=b"ustar  \x00", size_field: bytes | None = None) -> bytes:
    """A hand-built 512-byte header with a correct checksum (GNU magic by default)."""
    h = bytearray(512)
    h[0 : len(name)] = name
    h[100:108] = b"0000644\x00"
    h[124:136] = size_field if size_field is not None else f"{size:011o}\x00".encode()
    h[136:148] = b"00000000000\x00"
    h[156:157] = typeflag
    h[257:265] = magic
    h[148:156] = b" " * 8
    h[148:156] = f"{sum(h):06o}\x00 ".encode()
    return bytes(h)


def body(data: bytes) -> bytes:
    return data + bytes(-len(data) % 512)


END = bytes(1024)


def opened(data: bytes, limits: IngestLimits = LIMITS) -> OpenedTar:
    archive = open_archive(io.BytesIO(data), limits, release=False, depth=2)
    assert isinstance(archive, OpenedTar)
    return archive


def code_of(data: bytes, limits: IngestLimits = LIMITS, depth: int = 2) -> str:
    with pytest.raises(IngestError) as err:
        archive = open_archive(io.BytesIO(data), limits, release=False, depth=depth)
        list(iter_zip_members(archive, None, limits))
    return err.value.code


def decisions(data: bytes, include=None, limits: IngestLimits = LIMITS):
    archive = opened(data, limits)
    return [(m.label, m.disposition, m.code) for m in iter_zip_members(archive, include, limits)]


# ------------------------------------------------------------------------------------------------- the supported case
def test_sec07_a_nested_gnu_tar_with_long_names_is_read_member_by_member():
    files = {LONG: b'{"messages": []}\n', "runs/a.json": b"[1]", "runs/b/c.json": b"{}"}
    data = tgz([("runs", None), ("runs/b", None), *files.items()])
    assert b"././@LongLink" in gzip.decompress(data)  # the deposit's L headers are exercised
    archive = opened(data)
    members = list(iter_zip_members(archive, None, LIMITS))
    assert [(m.label, m.disposition, m.method) for m in members] == [(n, "selected", 0) for n in files]
    for m in members:
        content = archive.read_member(m)
        assert content == files[m.label] and m.crc32 == zlib.crc32(content) and m.file_size == len(content)


def test_sec07_selection_applies_and_unselected_members_carry_their_streamed_crc():
    data = tgz([("keep/a.json", b"a"), ("drop/b.txt", b"bb")])
    archive = opened(data)
    out = list(iter_zip_members(archive, lambda label: label.startswith("keep/"), LIMITS))
    assert [(m.label, m.disposition) for m in out] == [("keep/a.json", "selected"), ("drop/b.txt", "not_selected")]
    assert out[1].crc32 == zlib.crc32(b"bb")
    with pytest.raises(ValueError):
        archive.read_member(out[1])


def test_sec07_posix_ustar_prefix_names_are_joined():
    name = "p" * 90 + "/" + "q" * 60 + ".json"  # longer than 100 B: tarfile splits it into prefix and name (USTAR)
    data = tgz([(name, b"1")], fmt=tarfile.USTAR_FORMAT)
    assert decisions(data) == [(name, "selected", None)]


# ------------------------------------------------------------------------------------------------- scope
def test_sec07_a_gzip_tar_at_the_top_level_is_read_since_d247():
    """D-247: a declared deposit pin's top-level tar.gz (AgentOps-Bench, D-192) is read like the level-2 one."""
    archive = open_archive(io.BytesIO(tgz([("a.json", b"1")])), LIMITS, release=False, depth=1)
    assert isinstance(archive, OpenedTar) and [m.label for m in iter_zip_members(archive, None, LIMITS)] == ["a.json"]


def test_sec07_a_gzip_stream_without_a_tar_stays_deferred_at_level_2():
    assert code_of(gzip.compress(b'{"not": "a tar"}' * 100), depth=2) == "ingest.stream.codec"


def test_sec07_an_uncompressed_tar_is_still_refused():
    assert code_of(tar_bytes([("a.json", b"1")]), depth=2) == "ingest.archive.format"


def test_sec07_a_tar_beyond_the_depth_limit_is_never_opened():
    assert code_of(tgz([("a.json", b"1")]), depth=3) == "ingest.archive.depth"


# ------------------------------------------------------------------------------------------------- obs-G1: long names
def test_sec05_a_long_name_header_declaring_256_mib_is_never_buffered():
    """obs-G1 (tarfile held 555 MiB for this shape): the payload is skipped in chunks and the entry it names is rejected."""
    declared = 256 << 20
    raw = header(b"././@LongLink", b"L", declared) + bytes(declared) + header(b"short.json", b"0", 1) + body(b"1") + END
    data = gzip.compress(raw, compresslevel=9, mtime=0)
    assert code_of(data) == "ingest.stream.ratio"  # with the default ratio cap the stream is a bomb (~1000:1)
    roomy = LIMITS.replace(max_ratio=5000)
    tracemalloc.start()
    try:
        result = decisions(data, limits=roomy)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert result == [(None, "rejected", "ingest.name.invalid")]
    assert peak < 16 << 20, peak  # O(chunk), not O(declared size)


def test_sec09_a_long_name_at_the_limit_is_read_and_validated():
    name = ("d/" * 200 + "f.json").encode()[:LIMITS.max_name_bytes]
    raw = header(b"././@LongLink", b"L", len(name) + 1) + body(name + b"\x00") + header(b"x", b"0", 1) + body(b"1") + END
    (decision,) = decisions(gzip.compress(raw, mtime=0))
    assert decision[1] in ("selected", "rejected")  # validated by logical_name like any other name, never truncated


def test_sec05_two_long_name_headers_in_a_row_reject_the_archive():
    raw = header(b"././@LongLink", b"L", 2) + body(b"a\x00") + header(b"././@LongLink", b"L", 2) + body(b"b\x00") + END
    assert code_of(gzip.compress(raw, mtime=0)) == "ingest.archive.format"


def test_sec05_a_dangling_long_name_header_rejects_the_archive():
    raw = header(b"././@LongLink", b"L", 2) + body(b"a\x00") + END
    assert code_of(gzip.compress(raw, mtime=0)) == "ingest.archive.format"


# ------------------------------------------------------------------------------------------------- refused structure
@pytest.mark.parametrize("typeflag", [b"x", b"g", b"K", b"S", b"V", b"M", b"7", b"Z"])
def test_sec05_pax_gnu_extensions_sparse_and_unknown_types_reject_the_archive(typeflag):
    """``x`` here is a pax header with no entry after it (D-248 reads an ``x`` header only in front of an entry)."""
    raw = header(b"a.json", typeflag, 0) + END
    assert code_of(gzip.compress(raw, mtime=0)) == "ingest.archive.format"


def test_sec05_a_pax_tar_written_by_tarfile_is_read_with_its_pax_path():
    """D-248: tarfile writes an ``x`` header for a non-ASCII name; its ``path`` is the member's label."""
    data = tgz([("\u00e9t\u00e9.json", b"1")], fmt=tarfile.PAX_FORMAT)
    assert b"PaxHeader" in gzip.decompress(data)
    assert decisions(data) == [("\u00e9t\u00e9.json", "selected", None)]


@pytest.mark.parametrize(
    "raw",
    [
        header(b"a", b"0", 0, size_field=b"\x80" + bytes(11)) + END,  # base-256 size
        header(b"a", b"0", 0, size_field=b"0000000009\x00\x00") + END,  # not octal
        header(b"a", b"0", 1)[:148] + b"0000000\x00" + header(b"a", b"0", 1)[156:] + body(b"1") + END,  # checksum
        header(b"a", b"0", 1, magic=b"ustar\x0001") + body(b"1") + END,  # unknown magic/version
        header(b"a", b"0", 1) + body(b"1") + bytes(512) + header(b"b", b"0", 1) + body(b"2") + END,  # lone zero block
        header(b"a", b"0", 1) + body(b"1") + END + header(b"hidden", b"0", 1) + body(b"2"),  # after the end
        header(b"d", b"5", 4) + body(b"data") + END,  # a directory with a payload
    ],
    ids=["base256", "not-octal", "checksum", "magic", "lone-zero", "after-end", "dir-payload"],
)
def test_sec05_structural_defects_reject_the_whole_archive(raw):
    assert code_of(gzip.compress(raw, mtime=0)) == "ingest.archive.format"


def test_sec06_a_truncated_stream_or_tar_and_a_corrupt_trailer_are_typed():
    good = tgz([("a.json", b"1" * 4000)])
    assert code_of(good[:-12]) == "ingest.stream.truncated"
    trailer = bytearray(good)
    trailer[-8] ^= 0xFF  # CRC-32 of the gzip trailer
    assert code_of(bytes(trailer)) == "ingest.archive.crc"
    assert code_of(good + b"\x1f\x8b junk") == "ingest.archive.format"  # bytes after the gzip member
    short = gzip.compress(header(b"a", b"0", 4000) + b"1" * 100, mtime=0)  # the tar ends inside the member
    assert code_of(short) == "ingest.stream.truncated"


def test_sec06_a_ratio_bomb_and_the_stream_cap_are_enforced_while_decompressing():
    bomb = tgz([("a.json", bytes(64 << 20))])  # ~64 MiB of zeros: ~1000:1
    assert code_of(bomb) == "ingest.stream.ratio"
    # D-241: a tar stream is bounded by max_tar_stream_bytes (max_stream_bytes stays for deferred single streams)
    assert code_of(tgz([("a.json", b"1" * 4096)]), LIMITS.replace(max_tar_stream_bytes=4096)) == "ingest.stream.size"
    assert opened(tgz([("a.json", b"1" * 4096)]), LIMITS.replace(max_stream_bytes=4096)).codec == "gzip"


# ------------------------------------------------------------------------------------------------- member-level gate
def test_sec10_links_and_special_files_are_rejected_members():
    data = tgz([("a.json", b"1"), ("ln", ("sym", "/etc/passwd")), ("hl", ("hard", "a.json")), ("pipe", ("fifo", ""))])
    assert decisions(data) == [("a.json", "selected", None), ("ln", "rejected", "ingest.archive.link"),
                               ("hl", "rejected", "ingest.archive.link"), ("pipe", "rejected", "ingest.archive.link")]


@pytest.mark.parametrize(("name", "code"), [("../x.json", "ingest.archive.traversal"), ("/etc/x", "ingest.archive.traversal"),
                                            ("C:/x", "ingest.archive.traversal"), ("a/CON", "ingest.name.invalid"),
                                            ("a\x1bb", "ingest.name.invalid")])  # fmt: skip
def test_sec08_hostile_names_are_rejected_members_and_never_paths(name, code):
    raw = header(name.encode(), b"0", 1) + body(b"1") + header(b"ok.json", b"0", 1) + body(b"2") + END
    assert decisions(gzip.compress(raw, mtime=0)) == [(None, "rejected", code), ("ok.json", "selected", None)]


def test_sec09_undecodable_names_are_rejected_members():
    raw = header(b"bad\xff.json", b"0", 1) + body(b"1") + END
    assert decisions(gzip.compress(raw, mtime=0)) == [(None, "rejected", "ingest.name.invalid")]


def test_sec09_colliding_names_reject_every_member_that_shares_a_key():
    data = tgz([("Run.json", b"1"), ("run.json", b"2"), ("other.json", b"3")])
    assert decisions(data) == [("Run.json", "rejected", "ingest.archive.duplicate"),
                               ("run.json", "rejected", "ingest.archive.duplicate"), ("other.json", "selected", None)]


def test_sec09_a_colon_inside_a_component_is_a_label():
    assert decisions(tgz([("qwen3.6:27b/run.json", b"1")])) == [("qwen3.6:27b/run.json", "selected", None)]


def test_sec07_member_total_and_count_caps():
    data = tgz([("a.json", b"1" * 100), ("b.json", b"2" * 100), ("c.json", b"3" * 100)])
    assert decisions(data, limits=LIMITS.replace(max_member_bytes=99))[0] == ("a.json", "rejected", "ingest.archive.size")
    assert [d[1] for d in decisions(data, limits=LIMITS.replace(max_member_bytes=100))] == ["selected"] * 3
    assert [d[1:] for d in decisions(data, limits=LIMITS.replace(max_total_bytes=200))] == [
        ("selected", None), ("selected", None), ("rejected", "ingest.archive.size")]
    assert code_of(data, LIMITS.replace(max_members=2)) == "ingest.archive.members"
    assert len(decisions(data, limits=LIMITS.replace(max_members=3))) == 3


def test_sec11_tarfile_is_never_imported_by_the_reader():
    for name in [m for m in sys.modules if m == "tarfile"]:
        del sys.modules[name]
    archive = opened(tgz([("a.json", b"1")]))  # the test's own tarfile import was before; re-check after a fresh read
    list(iter_zip_members(archive, None, LIMITS))
    assert "tarfile" not in sys.modules
    import agentprov.ingest.archives as archives

    assert "tarfile" not in archives.__dict__


def test_sec07_the_same_tar_inside_a_zip_reads_identically_twice():
    data = tgz([(LONG, b"x" * 3000), ("b.json", b"y")])
    outer = io.BytesIO()
    with zipfile.ZipFile(outer, "w", zipfile.ZIP_STORED) as z:
        z.writestr("data/traces.tar.gz", data)
    first = [(m.label, m.crc32, m.file_size) for m in iter_zip_members(opened(data), None, LIMITS)]
    second = [(m.label, m.crc32, m.file_size) for m in iter_zip_members(opened(data), None, LIMITS)]
    assert first == second and len(first) == 2
