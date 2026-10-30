"""Archive gate, functional behaviour (G.3.5; K.5.6). Hostile inputs live in tests/security/test_archives.py."""

from __future__ import annotations

import io
import struct
import warnings
import zipfile

import pytest

from agentprov.envinfo import InterpreterUnpatchedError, InterpreterUnpatchedWarning
from agentprov.errors import IngestError
from agentprov.ingest.archives import iter_zip_members, open_archive, open_zip, zip_precheck
from agentprov.ingest.limits import IngestLimits

LIMITS = IngestLimits()


def make_zip(members, method=zipfile.ZIP_DEFLATED) -> io.BytesIO:
    buf = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with zipfile.ZipFile(buf, "w") as z:
            for name, data in members:
                info = zipfile.ZipInfo(name)
                info.filename = info.orig_filename.split("\0", 1)[0]  # ZipInfo rewrites os.sep to "/" on some hosts
                info.compress_type = method
                z.writestr(info, data)
    buf.seek(0)
    return buf


def decisions(fp, limits=LIMITS, include=None):
    with open_zip(fp, limits, release=False) as z:
        return [(m.label, m.disposition, m.code) for m in iter_zip_members(z, include)]


def test_selects_and_streams_regular_members():
    fp = make_zip([("a.json", b'{"x":1}'), ("dir/b.json", b"[]"), ("empty", b"")])
    with open_zip(fp, release=False) as z:
        members = list(iter_zip_members(z))
        assert [(m.label, m.disposition) for m in members] == [
            ("a.json", "selected"),
            ("dir/b.json", "selected"),
            ("empty", "selected"),
        ]
        assert [b"".join(m.iter_chunks()) for m in members] == [b'{"x":1}', b"[]", b""]
        assert z.advisory is None and z.findings == ()


def test_directories_are_skipped():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.mkdir("d")
        z.writestr("d/f", b"1")
    assert decisions(buf) == [("d/f", "selected", None)]


def test_streaming_respects_chunk_size_and_is_exact():
    payload = bytes(range(256)) * 400
    fp = make_zip([("big", payload)])
    with open_zip(fp, release=False) as z:
        (member,) = iter_zip_members(z)
        chunks = list(z.stream_member(member, 1000))
        assert max(map(len, chunks)) <= 1000
        assert b"".join(chunks) == payload


def test_all_allowed_methods_stream():
    for method in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED, zipfile.ZIP_ZSTANDARD):
        fp = make_zip([("m", b"payload" * 50)], method)
        with open_zip(fp, release=False) as z:
            (member,) = iter_zip_members(z)
            assert member.disposition == "selected" and member.method == method
            assert z.read_member(member) == b"payload" * 50


def test_unselected_members_are_not_selected_and_never_opened(monkeypatch):
    fp = make_zip([("keep.json", b"1"), ("skip.bin", b"2")])
    with open_zip(fp, release=False) as z:
        monkeypatch.setattr(zipfile.ZipFile, "open", lambda *a, **k: pytest.fail("decompressed"))
        got = [(m.label, m.disposition) for m in iter_zip_members(z, lambda label: label.endswith(".json"))]
    assert got == [("keep.json", "selected"), ("skip.bin", "not_selected")]


def test_only_selected_members_can_be_streamed():
    fp = make_zip([("a", b"1")])
    with open_zip(fp, release=False) as z:
        (member,) = iter_zip_members(z, lambda label: False)
        with pytest.raises(ValueError):
            list(z.stream_member(member))


def test_member_json_has_no_raw_name():
    fp = make_zip([("a", b"1")])
    with open_zip(fp, release=False) as z:
        (member,) = iter_zip_members(z)
        assert member.to_json() == {
            "label": "a",
            "method": zipfile.ZIP_DEFLATED,
            "crc32": zipfile.crc32(b"1"),
            "size": 1,
            "disposition": "selected",
        }


@pytest.mark.parametrize("delta", [-1, 0, 1])
def test_member_count_cap(delta):
    n = 6
    fp = make_zip([(f"f{i}", b"x") for i in range(n)])
    limits = LIMITS.replace(max_members=n + delta)
    if delta < 0:
        with pytest.raises(IngestError) as info:
            open_zip(fp, limits, release=False)
        assert info.value.code == "ingest.archive.members"
    else:
        assert len(decisions(fp, limits)) == n


@pytest.mark.parametrize("delta", [-1, 0, 1])
def test_member_size_cap(delta):
    size = 100
    fp = make_zip([("m", b"q" * size), ("small", b"1")], zipfile.ZIP_STORED)
    limits = LIMITS.replace(max_member_bytes=size + delta)
    got = dict((label, code) for label, _, code in decisions(fp, limits))
    assert got["m"] == ("ingest.archive.size" if delta < 0 else None)
    assert got["small"] is None  # a member-level defect rejects that member only


@pytest.mark.parametrize("delta", [-1, 0, 1])
def test_total_size_cap_counts_selected_members(delta):
    fp = make_zip([(f"m{i}", b"q" * 100) for i in range(3)], zipfile.ZIP_STORED)
    limits = LIMITS.replace(max_total_bytes=300 + delta)
    codes = [code for _, _, code in decisions(fp, limits)]
    assert codes == [None, None, "ingest.archive.size" if delta < 0 else None]


def test_unselected_members_do_not_count_towards_the_total():
    fp = make_zip([("a.json", b"q" * 100), ("junk.bin", b"q" * 5000)], zipfile.ZIP_STORED)
    limits = LIMITS.replace(max_total_bytes=100)
    assert [(label, d) for label, d, _ in decisions(fp, limits, lambda n: n.endswith(".json"))] == [
        ("a.json", "selected"),
        ("junk.bin", "not_selected"),
    ]


def test_ratio_floor_boundary():
    n = 100_000
    fp = make_zip([("z", bytes(n))])
    assert decisions(fp, LIMITS.replace(ratio_floor_bytes=n))[0][2] is None  # not larger than the floor: unchecked
    assert decisions(fp, LIMITS.replace(ratio_floor_bytes=n - 1))[0][2] == "ingest.archive.ratio"


def test_ratio_boundary_uses_strictly_greater():
    n = 100_000
    fp = make_zip([("z", bytes(n))])
    with open_zip(fp, release=False) as z:
        (member,) = iter_zip_members(z)
        ratio = member.file_size / member.compress_size
    floor = n - 1
    assert decisions(fp, LIMITS.replace(ratio_floor_bytes=floor, max_ratio=ratio))[0][2] is None
    assert decisions(fp, LIMITS.replace(ratio_floor_bytes=floor, max_ratio=ratio * 0.999))[0][2] == "ingest.archive.ratio"


def test_nested_depth_is_checked_when_opening():
    inner = make_zip([("x", b"1")]).getvalue()
    outer = make_zip([("inner.zip", inner)], zipfile.ZIP_STORED)
    with open_zip(outer, release=False, depth=1) as z:
        (member,) = iter_zip_members(z)
        nested = io.BytesIO(z.read_member(member))
    with open_zip(nested, release=False, depth=LIMITS.max_archive_depth):
        pass
    with pytest.raises(IngestError) as info:
        open_zip(nested, release=False, depth=LIMITS.max_archive_depth + 1)
    assert info.value.code == "ingest.archive.depth"


def test_open_archive_dispatches_by_magic():
    assert open_archive(make_zip([("a", b"1")]), release=False).depth == 1
    for head, code in [
        (b"\x1f\x8b\x08" + bytes(20), "ingest.stream.codec"),
        (b"BZh9" + bytes(20), "ingest.stream.codec"),
        (b"\xfd7zXZ\x00" + bytes(20), "ingest.stream.codec"),
        (b"\x28\xb5\x2f\xfd" + bytes(20), "ingest.stream.truncated"),  # D-240: a zstd stream is sniffed for a tar
        (b"plain text, not an archive", "ingest.archive.format"),
        (b"", "ingest.archive.format"),
    ]:
        with pytest.raises(IngestError) as info:
            open_archive(io.BytesIO(head), release=False)
        assert info.value.code == code


def test_tar_is_refused_with_exit_code_5():
    block = bytearray(512)
    block[257:262] = b"ustar"
    with pytest.raises(IngestError) as info:
        open_archive(io.BytesIO(bytes(block) * 3), release=False)
    assert info.value.code == "ingest.archive.format" and info.value.exit_code == 5


def test_not_a_zip_is_a_format_error():
    for data in (b"PK\x03\x04" + bytes(40), b"x" * 10):
        with pytest.raises(IngestError) as info:
            open_zip(io.BytesIO(data), release=False)
        assert info.value.code == "ingest.archive.format"


def test_precheck_reports_the_end_record():
    fp = make_zip([("a", b"1"), ("b", b"2")])
    pre = zip_precheck(fp)
    assert (pre.entries, pre.zip64, pre.trailing_bytes, pre.comment_len) == (2, False, 0, 0)
    assert pre.cd_offset + pre.cd_size == pre.end_offset == pre.eocd_offset


def test_interpreter_guard_runs_first_and_propagates_the_advisory(monkeypatch):
    class Unreadable(io.BytesIO):
        def read(self, *a):
            raise AssertionError("opened before the guard ran")

        seek = read

    monkeypatch.setattr("sys.version_info", (3, 14, 7, "final", 0))
    with pytest.raises(InterpreterUnpatchedError) as info:
        open_zip(Unreadable(), release=True)
    assert info.value.exit_code == 3
    fp = make_zip([("a", b"1")])
    with pytest.warns(InterpreterUnpatchedWarning):
        z = open_zip(fp, release=False)
    assert z.advisory is not None and z.advisory.python_version == "3.14.7"
    z.close()
    monkeypatch.setattr("sys.version_info", (3, 14, 8, "final", 0))
    with open_zip(fp, release=True) as z:
        assert z.advisory is None


def test_crc_field_matches_zipfile():
    fp = make_zip([("a", b"hello")], zipfile.ZIP_STORED)
    data = fp.getvalue()
    assert struct.pack("<L", zipfile.crc32(b"hello")) in data


def test_an_empty_archive_is_valid_and_has_no_members():
    with open_zip(io.BytesIO(b"PK\x05\x06" + bytes(18)), release=False) as z:
        assert list(iter_zip_members(z)) == []


# ---- pre-round review D #2: PKWARE multi-disk markers -------------------------------------------------------------
def _one_member_zip() -> bytearray:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("a.json", b"{}")
    return bytearray(buf.getvalue())


def _eocd_patch(field_offset: int, fmt: str, *values: int) -> bytes:
    data = _one_member_zip()
    struct.pack_into(fmt, data, data.rfind(b"PK\x05\x06") + field_offset, *values)
    return bytes(data)


def _cd_volume_patch(volume: int) -> bytes:
    data = _one_member_zip()
    struct.pack_into("<H", data, data.find(b"PK\x01\x02") + 34, volume)
    return bytes(data)


@pytest.mark.parametrize("data", [
    pytest.param(_eocd_patch(4, "<HH", 1, 1), id="eocd-disk-1"),
    pytest.param(_eocd_patch(6, "<H", 2), id="eocd-cd-disk-2"),
    pytest.param(_eocd_patch(8, "<H", 0), id="eocd-entries-on-disk-0-of-1"),
    pytest.param(_cd_volume_patch(3), id="member-on-disk-3"),
])
def test_a_classic_multi_disk_zip_is_refused(data: bytes) -> None:
    """G.3.5 / D-243: "a PKWARE multi-disk archive stays refused by the pre-check". The classic EOCD's disk fields and a
    central-directory record's disk number were ignored (only the ZIP64 locator path refused)."""
    with pytest.raises(IngestError) as exc:
        with open_zip(io.BytesIO(data), release=False):
            pass
    assert exc.value.code == "ingest.archive.format" and "multi-disk" in str(exc.value)


def test_a_single_disk_zip_still_opens() -> None:
    with open_zip(io.BytesIO(bytes(_one_member_zip())), release=False) as opened:
        assert [m.label for m in iter_zip_members(opened)] == ["a.json"]


def test_an_undecodable_utf8_flagged_name_refuses_the_archive_with_a_precise_reason() -> None:
    """Pre-round review D #3: zipfile decodes every UTF-8-flagged name at open, so one bad name refuses the whole archive
    (G.3.5's recorded deviation). The reason now names the defect instead of "unreadable zip structure"."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("good.json", b"{}")
        z.writestr("bad.json", b"{}")
    data = bytearray(buf.getvalue())
    for sig, name_at, flag_at in ((b"PK\x01\x02", 46, 8), (b"PK\x03\x04", 30, 6)):
        pos = 0
        while (pos := data.find(sig, pos)) >= 0:
            if data[pos + name_at:pos + name_at + 3] == b"bad":
                data[pos + name_at:pos + name_at + 3] = b"\xff\xfe\xfd"
                struct.pack_into("<H", data, pos + flag_at, struct.unpack_from("<H", data, pos + flag_at)[0] | 0x800)
            pos += 4
    with pytest.raises(IngestError) as exc:
        with open_zip(io.BytesIO(bytes(data)), release=False):
            pass
    assert exc.value.code == "ingest.archive.format" and "not valid UTF-8" in str(exc.value)
