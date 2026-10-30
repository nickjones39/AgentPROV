"""SEC-05/06/07: a zstd tar is read by the bounded tar framing parser; zstd frames are checked before decoding (D-240, D-241).

Frame headers are checked with ``struct`` before a decoder exists: skippable frames, dictionaries, windows over
``2**zstd_window_log_max`` and declared content sizes over the cap are refused without allocating. Output is bounded by
``max_tar_stream_bytes`` and ``max_ratio`` as it grows. Nothing is extracted (``cwd_guard``).
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import tracemalloc
import zlib
from compression import zstd

import pytest
from format_support import frame_header, reframe, tar_bytes, tzst, zip_bytes, zstd_stream

from agentprov.errors import IngestError
from agentprov.ingest import archives, streams
from agentprov.ingest.archives import OpenedTar, iter_zip_members, open_archive
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.streams import iter_zstd_bounded, parse_zstd_frame_header

LIMITS = IngestLimits()
LONG = "results/gemini_cli/cell_07/" + "r" * 90 + "/transcript.jsonl"  # > 100 B: a GNU L header


def decisions(data: bytes, limits: IngestLimits = LIMITS, depth: int = 1, include=None):
    archive = open_archive(io.BytesIO(data), limits, release=False, depth=depth)
    assert isinstance(archive, OpenedTar) and archive.codec == "zstd"
    out = []
    for m in iter_zip_members(archive, include, limits):
        content = archive.read_member(m) if m.disposition == "selected" else None
        out.append((m.label, m.disposition, m.code, content))
    return out


def code_of(data: bytes, limits: IngestLimits = LIMITS, depth: int = 1) -> str:
    with pytest.raises(IngestError) as err:
        archive = open_archive(io.BytesIO(data), limits, release=False, depth=depth)
        list(iter_zip_members(archive, None, limits))
    return err.value.code


@pytest.fixture(autouse=True)
def _cwd(cwd_guard):
    return cwd_guard


# ------------------------------------------------------------------------------------------------ benign shapes
def test_a_top_level_tar_zst_is_read_with_long_names_and_member_crcs():
    entries = [("results", None), (LONG, b'{"type": "tool_use"}\n'), ("results/verdict.json", b'{"ok": true}')]
    got = decisions(tzst(entries))
    assert [(label, d) for label, d, _c, _b in got] == [(LONG, "selected"), ("results/verdict.json", "selected")]
    assert got[0][3] == b'{"type": "tool_use"}\n'


@pytest.mark.parametrize("frames", [1, 3])
@pytest.mark.parametrize("level", [1, 19])
def test_frames_levels_and_checksums_give_the_same_members(frames, level):
    entries = [(f"r/{i}.json", os.urandom(200) + b"x" * 5000) for i in range(6)]
    data = zstd_stream(tar_bytes(entries), level=level, frames=frames)
    assert [(lbl, c) for lbl, _d, _code, c in decisions(data)] == entries


def test_a_tar_zst_member_of_a_zip_is_read_at_level_2_and_a_tar_gz_at_level_1_since_d247():
    inner = tzst([("a.json", b"[]")])
    assert decisions(inner, depth=2)[0][:2] == ("a.json", "selected")
    import gzip

    archive = open_archive(io.BytesIO(gzip.compress(tar_bytes([("a.json", b"[]")]), mtime=0)), LIMITS, release=False)
    assert isinstance(archive, OpenedTar) and archive.codec == "gzip"


def test_a_zstd_stream_that_is_not_a_tar_stays_deferred_and_an_uncompressed_tar_stays_refused():
    assert code_of(zstd_stream(b'{"k": 1}\n' * 100)) == "ingest.stream.codec"
    assert code_of(tar_bytes([("a.json", b"1")])) == "ingest.archive.format"


def test_selection_skips_unselected_members_without_holding_them():
    entries = [("keep.json", b"k"), ("skip.bin", os.urandom(1 << 20))]
    got = decisions(tzst(entries), include=lambda label: label.endswith(".json"))
    assert [(lbl, d) for lbl, d, _c, _b in got] == [("keep.json", "selected"), ("skip.bin", "not_selected")]


# ------------------------------------------------------------------------------------------- frame header gate
@pytest.fixture
def no_decoder(monkeypatch):
    def fail(*a, **k):
        raise AssertionError("a decoder was created for a frame the header gate must refuse")

    monkeypatch.setattr(zstd, "ZstdDecompressor", fail)
    monkeypatch.setattr(streams._zstd, "ZstdDecompressor", fail)


@pytest.mark.parametrize(
    ("header", "code"),
    [
        (frame_header(window_exponent=18), "ingest.stream.memory"),  # 2**28 > 2**27
        (frame_header(window_exponent=17, mantissa=1), "ingest.stream.memory"),  # 2**27 + 2**24
        (frame_header(window_exponent=31), "ingest.stream.memory"),
        (frame_header(dictionary_id=7), "ingest.stream.codec"),
        (frame_header(content_size=(16 << 30) + 1), "ingest.stream.size"),
        (frame_header(reserved=True), "ingest.archive.format"),
        (frame_header(single=True, content_size=(1 << 27) + 1), "ingest.stream.memory"),  # window = content size
    ],
)
def test_the_header_gate_refuses_before_any_decoder_exists(header, code, no_decoder):
    data = header + bytes(64)
    assert code_of(data) == code
    with pytest.raises(IngestError) as err:
        list(iter_zstd_bounded(data, LIMITS, max_bytes=LIMITS.max_tar_stream_bytes))
    assert err.value.code == code


SKIPPABLE = b"\x50\x2a\x4d\x18" + (8).to_bytes(4, "little") + bytes(8)


def test_a_skippable_frame_is_refused_and_a_stream_that_starts_with_one_is_no_zstd_stream():
    with pytest.raises(IngestError) as err:
        list(iter_zstd_bounded(SKIPPABLE + tzst([("a.json", b"1")]), LIMITS))
    assert err.value.code == "ingest.stream.codec"
    assert code_of(SKIPPABLE + tzst([("a.json", b"1")])) == "ingest.archive.format"  # magic sniff: not an archive
    assert code_of(tzst([("a.json", b"1")]) + SKIPPABLE) == "ingest.stream.codec"  # met while walking the stream


def test_window_limit_minus_one_and_at_the_limit_decode():
    """K.5.6 limit probes: 2**26 and 2**27 decode, 2**27 + 2**24 is refused (above)."""
    payload = tar_bytes([("a.json", b"1" * 4000)])
    for window_log in (LIMITS.zstd_window_log_max - 1, LIMITS.zstd_window_log_max):
        data = zstd_stream(payload, window_log=window_log)
        assert parse_zstd_frame_header(data[:18]).window_size == 1 << window_log
        assert decisions(data)[0][3] == b"1" * 4000
    tighter = LIMITS.replace(zstd_window_log_max=LIMITS.zstd_window_log_max - 1)
    assert code_of(zstd_stream(payload, window_log=LIMITS.zstd_window_log_max), tighter) == "ingest.stream.memory"


def test_too_many_frames_are_refused():
    data = zstd_stream(tar_bytes([("a.json", b"1" * 20000)]), frames=4)
    assert decisions(data, LIMITS.replace(max_zstd_frames=4))[0][1] == "selected"
    assert code_of(data, LIMITS.replace(max_zstd_frames=3)) == "ingest.stream.codec"


# ----------------------------------------------------------------------------------------------- stream bounds
def test_sec06_a_zstd_ratio_bomb_stops_early():
    bomb = zstd_stream(tar_bytes([("a.json", bytes(64 << 20))]), level=19)  # ~64 MiB of zeros, ratio in the thousands
    assert len(bomb) < 64 << 10
    assert code_of(bomb) == "ingest.stream.ratio"


@pytest.mark.parametrize(("delta", "ok"), [(-1, False), (0, True), (1, True)])
def test_max_tar_stream_bytes_probes(delta, ok):
    """K.5.6: the whole decompressed stream (headers, padding, end blocks) counts against max_tar_stream_bytes."""
    raw = tar_bytes([("a.json", os.urandom(6000))])
    limits = LIMITS.replace(max_tar_stream_bytes=len(raw) + delta)
    if ok:
        assert decisions(zstd_stream(raw), limits)[0][1] == "selected"
    else:
        assert code_of(zstd_stream(raw), limits) == "ingest.stream.size"


def test_max_stream_bytes_no_longer_bounds_a_tar_stream():
    """D-241: the tar path uses max_tar_stream_bytes; max_stream_bytes stays the cap of deferred single streams."""
    data = tzst([("a.json", os.urandom(8000))])
    assert decisions(data, LIMITS.replace(max_stream_bytes=1024))[0][1] == "selected"


def test_truncation_corruption_trailing_data_and_checksum_have_codes():
    data = tzst([("a.json", os.urandom(4000))], checksum=True)
    assert code_of(data[:-7]) in ("ingest.stream.truncated", "ingest.archive.crc")
    assert code_of(data[: len(data) // 2]) == "ingest.stream.truncated"
    assert code_of(data + b"junk") == "ingest.archive.format"
    assert code_of(data + b"\x28\xb5") == "ingest.stream.truncated"  # a frame magic cut short
    flipped = bytearray(data)
    flipped[-1] ^= 0xFF  # the content checksum
    assert code_of(bytes(flipped)) == "ingest.archive.crc"


def test_a_declared_content_size_is_never_preallocated(tmp_path):
    """CVE-2026-15310 shape: a frame declares 1 GiB and carries 1 KiB; peak RSS of a fresh process stays small."""
    real = zstd_stream(tar_bytes([("a.json", b"x" * 512)]), checksum=False)
    lie = reframe(real, frame_header(window_exponent=13, content_size=1 << 30))
    script = (
        "import io,resource,sys\n"
        "from agentprov.errors import IngestError\n"
        "from agentprov.ingest.streams import iter_zstd_bounded\n"
        "from agentprov.ingest.limits import IngestLimits\n"
        "data=sys.stdin.buffer.read()\n"
        "base=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss\n"
        "try:\n  list(iter_zstd_bounded(data, IngestLimits(), max_bytes=IngestLimits().max_tar_stream_bytes)); code='ok'\n"
        "except IngestError as e: code=e.code\n"
        "peak=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss\n"
        "scale=1 if sys.platform=='darwin' else 1024\n"
        "print(code, (peak-base)*scale)\n"
    )
    out = subprocess.run([sys.executable, "-I", "-B", "-c", script], input=lie, capture_output=True, check=True, cwd=tmp_path)
    code, grew = out.stdout.decode().split()
    assert code in ("ingest.archive.format", "ingest.stream.truncated")  # the content size does not match
    assert int(grew) < 64 << 20, grew


# --------------------------------------------------------------------------------------------- obs-G1 and memory
def test_sec05_a_long_name_header_declaring_256_mib_is_never_buffered_in_a_zstd_tar():
    from test_nested_tar import END, body, header

    declared = 256 << 20
    raw = header(b"././@LongLink", b"L", declared) + bytes(declared) + header(b"short.json", b"0", 1) + body(b"1") + END
    data = zstd_stream(raw, level=3)
    assert code_of(data) == "ingest.stream.ratio"
    roomy = LIMITS.replace(max_ratio=1 << 20)
    tracemalloc.start()
    try:
        archive = open_archive(io.BytesIO(data), roomy, release=False)
        result = [(m.label, m.disposition, m.code) for m in iter_zip_members(archive, None, roomy)]
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert result == [(None, "rejected", "ingest.name.invalid")]
    assert peak < 16 << 20, peak


def test_tar_structure_rules_are_the_d57_rules():
    """A pax global header, a member after the end blocks and a bad checksum reject a zstd tar exactly as a gzip tar."""
    from test_nested_tar import END, body, header

    assert code_of(zstd_stream(header(b"g", b"g", 0) + header(b"a.json", b"0", 1) + body(b"1") + END)) == "ingest.archive.format"
    good = tar_bytes([("a.json", b"1")])
    assert code_of(zstd_stream(good + tar_bytes([("b.json", b"2")]))) == "ingest.archive.format"
    bad = bytearray(good)
    bad[0] ^= 1
    assert code_of(zstd_stream(bytes(bad))) == "ingest.archive.format"


def test_members_carry_method_0_and_the_streamed_crc():
    archive = open_archive(io.BytesIO(tzst([("a.json", b"abc")])), LIMITS, release=False)
    (member,) = list(iter_zip_members(archive, None, LIMITS))
    assert (member.method, member.crc32) == (0, zlib.crc32(b"abc"))
    assert archives.TarMember is type(member)


def test_a_nested_eval_zip_inside_a_tar_zst_is_a_member_like_any_other():
    eval_zip = zip_bytes([("header.json", b"{}"), ("samples/1_epoch_1.json", b"{}")])
    got = decisions(tzst([("logs/run.eval", eval_zip)]))
    assert got[0][:2] == ("logs/run.eval", "selected") and got[0][3] == eval_zip


def test_expand_reads_a_top_level_tar_zst_and_its_nested_eval_at_level_2(tmp_path):
    """D-240 end to end: a stored tar.zst container (control-arena shape) is expanded in a T1 worker; its .eval member
    is stored and expanded in turn; rows are identical for 1 and 3 workers; nothing reaches the filesystem."""
    from agentprov.io.workers import WorkerPool
    from agentprov.raw.members import ContainerSpec, Selection, expand_containers
    from agentprov.raw.store import RawObjectStore

    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    store = RawObjectStore(sandbox / "raw")
    eval_zip = zip_bytes([("header.json", b"{}"), ("samples/1_epoch_1.json", b'{"id": 1}')])
    data = tzst([("logs", None), ("logs/" + "e" * 110 + ".eval", eval_zip), ("logs/notes.md", b"n")])
    sha = store.put(data, ext="bin").sha256
    selections = (Selection(nested=("logs/*.eval",)), Selection(include=("samples/*.json",)))
    runs = [expand_containers(store, [ContainerSpec(sha, "snap", "batch.tar.zst", selections)],
                              pool=WorkerPool(workers=w, store_root=store.objects_dir)) for w in (1, 3)]  # fmt: skip
    first, second = runs
    assert [r.to_json() for r in first.rows] == [r.to_json() for r in second.rows] and first.events == []
    top = [(r.disposition, r.method) for r in first.rows if r.container == sha]
    assert top == [("selected", 0), ("not_selected", 0)]
    level2 = [(r.label, r.disposition) for r in first.rows if r.container != sha]
    assert level2 == [("header.json", "not_selected"), ("samples/1_epoch_1.json", "selected")]
    assert all(p == "raw" or p.startswith("raw/") for p in (str(q.relative_to(sandbox)) for q in sandbox.rglob("*")))


@pytest.mark.slow
def test_reading_many_large_members_keeps_memory_flat(tmp_path):
    """D-245 regression: pass 2 once grew by one member size per member (a growing bytearray's abandoned regions stayed
    resident on macOS: 643 MiB after 16 x 32 MiB). The peak must stay near a few member sizes, whatever the count."""
    path = tmp_path / "many.tar.zst"
    path.write_bytes(tzst([(f"r/{i}.bin", os.urandom(16 << 20)) for i in range(24)], level=1))
    script = (
        "import resource,sys\n"
        "from agentprov.ingest.archives import iter_zip_members, open_archive\n"
        "from agentprov.ingest.limits import IngestLimits\n"
        "L=IngestLimits()\n"
        "f=open(sys.argv[1],'rb'); a=open_archive(f,L,release=False)\n"
        "base=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss\n"
        "n=sum(len(a.read_member(m)) for m in iter_zip_members(a,None,L))\n"
        "scale=1 if sys.platform=='darwin' else 1024\n"
        "print(n, (resource.getrusage(resource.RUSAGE_SELF).ru_maxrss-base)*scale)\n"
    )
    out = subprocess.run([sys.executable, "-I", "-B", "-c", script, str(path)], capture_output=True, check=True, cwd=tmp_path)
    total, grew = map(int, out.stdout.split())
    assert total == 24 << 24
    assert grew < 8 * (16 << 20), grew  # 24 members read; growth stays below 8 member sizes
