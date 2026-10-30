"""SEC-05 (nested), SEC-07, SEC-08 (K.12.1): hostile zip archives. Malicious bytes are built at run time.

Archives are never extracted: ``fs_guard`` here is a working directory that must stay empty plus patched
``extract``/``extractall``.
"""

from __future__ import annotations

import io
import os
import stat
import struct
import unicodedata
import warnings
import zipfile

import pytest

from agentprov.envinfo import InterpreterUnpatchedError
from agentprov.errors import IngestError
from agentprov.ingest.archives import iter_zip_members, open_archive, open_zip, zip_precheck
from agentprov.ingest.limits import IngestLimits

LIMITS = IngestLimits()


# ---------------------------------------------------------------------------------------------- builders
def make_zip(members, method=zipfile.ZIP_DEFLATED, attrs=None) -> bytes:
    buf = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with zipfile.ZipFile(buf, "w") as z:
            for name, data in members:
                info = zipfile.ZipInfo(name)
                info.filename = info.orig_filename.split("\0", 1)[0]  # ZipInfo rewrites os.sep to "/" on some hosts
                info.compress_type = method
                if attrs and name in attrs:
                    info.external_attr = attrs[name]
                z.writestr(info, data)
    return buf.getvalue()


def eocd_offset(data: bytes) -> int:
    return data.rfind(b"PK\x05\x06")


def cd_entry_offsets(data: bytes) -> list[int]:
    eocd = eocd_offset(data)
    entries, cd_size, cd_off = struct.unpack_from("<HLL", data, eocd + 10)
    out, pos = [], cd_off
    while pos < cd_off + cd_size:
        out.append(pos)
        n, m, k = struct.unpack_from("<HHH", data, pos + 28)
        pos += 46 + n + m + k
    return out


_CD_FIELDS = {"flags": (8, "<H"), "method": (10, "<H"), "crc": (16, "<L"), "csize": (20, "<L"), "usize": (24, "<L"),
              "ext_attr": (38, "<L"), "offset": (42, "<L")}
_LOCAL_FIELDS = {"flags": (6, "<H"), "method": (8, "<H"), "crc": (14, "<L"), "csize": (18, "<L"), "usize": (22, "<L")}


def patch_cd(data: bytes, index: int, **fields: int) -> bytes:
    buf = bytearray(data)
    base = cd_entry_offsets(data)[index]
    for name, value in fields.items():
        off, fmt = _CD_FIELDS[name]
        struct.pack_into(fmt, buf, base + off, value)
    return bytes(buf)


def patch_local(data: bytes, index: int, **fields: int) -> bytes:
    buf = bytearray(data)
    cd = cd_entry_offsets(data)[index]
    base = struct.unpack_from("<L", data, cd + 42)[0]
    for name, value in fields.items():
        off, fmt = _LOCAL_FIELDS[name]
        struct.pack_into(fmt, buf, base + off, value)
    return bytes(buf)


def crafted_cd(n: int, name_len: int = 4, header_offset: int = 0) -> bytes:
    """A central directory of ``n`` valid-looking entries (all pointing at ``header_offset``)."""
    out = []
    for i in range(n):
        name = f"{i:0{name_len}d}".encode()[-name_len:].ljust(name_len, b"x")
        out.append(struct.pack("<4s6H3L5H2L", b"PK\x01\x02", 20, 20, 0, 0, 0, 0, 0, 0, 0, len(name), 0, 0, 0, 0, 0,
                               header_offset) + name)
    return b"".join(out)


def eocd(entries: int, cd_size: int, cd_off: int, comment: bytes = b"") -> bytes:
    return struct.pack("<4s4H2LH", b"PK\x05\x06", 0, 0, min(entries, 0xFFFF), min(entries, 0xFFFF), cd_size, cd_off,
                       len(comment)) + comment


def decisions(data: bytes, limits: IngestLimits = LIMITS, include=None):
    with open_zip(io.BytesIO(data), limits, release=False) as z:
        return [(m.label, m.disposition, m.code) for m in iter_zip_members(z, include)]


def archive_code(data: bytes, limits: IngestLimits = LIMITS) -> str:
    with pytest.raises(IngestError) as info:
        open_zip(io.BytesIO(data), limits, release=False)
    return info.value.code


@pytest.fixture
def fs_guard(tmp_path, monkeypatch):
    """Nothing may be extracted or created: extraction calls are patched out and the cwd must stay empty."""
    monkeypatch.chdir(tmp_path)
    for name in ("extract", "extractall"):
        monkeypatch.setattr(zipfile.ZipFile, name, lambda *a, **k: pytest.fail("archive extracted"))
    yield tmp_path
    assert list(tmp_path.iterdir()) == []


@pytest.fixture
def no_zipfile(monkeypatch):
    def fail(*a, **k):
        raise AssertionError("zipfile.ZipFile was called before the size check")

    monkeypatch.setattr(zipfile, "ZipFile", fail)


# ---------------------------------------------------------------------------------------------- SEC-07: size
def test_sec07_cd_over_the_default_limit_is_rejected_before_zipfile(no_zipfile):
    cd_size = LIMITS.max_cd_bytes + 1
    data = bytes(cd_size) + eocd(0, cd_size, 0)
    assert archive_code(data) == "ingest.archive.cd"


@pytest.mark.parametrize("delta", [-1, 0, 1])
def test_sec07_cd_size_cap_probed_at_the_limit(delta):
    data = make_zip([(f"member-{i}", b"x") for i in range(5)])
    cd_size = zip_precheck(io.BytesIO(data)).cd_size
    limits = LIMITS.replace(max_cd_bytes=cd_size + delta)
    if delta < 0:
        assert archive_code(data, limits) == "ingest.archive.cd"
    else:
        assert len(decisions(data, limits)) == 5


def test_sec07_cd_beyond_the_file_is_rejected_before_zipfile(no_zipfile):
    body = bytes(100)
    assert archive_code(body + eocd(1, 5000, 10)) == "ingest.archive.cd"
    assert archive_code(body + eocd(1, 50, 80)) == "ingest.archive.cd"  # starts inside the file, ends past the record


def test_sec07_200k_entries_with_realistic_names_are_rejected_before_zipfile(no_zipfile):
    entries = 200_000
    cd = crafted_cd(entries, name_len=130)
    assert len(cd) > LIMITS.max_cd_bytes
    assert archive_code(cd + eocd(entries, len(cd), 0)) == "ingest.archive.cd"


def test_sec07_entries_over_max_members_with_short_names_are_rejected_after_open():
    entries = LIMITS.max_members + 1
    cd = crafted_cd(entries)
    assert len(cd) < LIMITS.max_cd_bytes
    assert archive_code(cd + eocd(entries, len(cd), 0)) == "ingest.archive.members"


def test_sec07_lying_eocd_count_does_not_hide_extra_entries():
    data = make_zip([(f"m{i}", b"x") for i in range(6)])
    eocd_at = eocd_offset(data)
    lie = bytearray(data)
    struct.pack_into("<HH", lie, eocd_at + 8, 1, 1)  # EOCD claims one entry
    assert len(decisions(bytes(lie))) == 6
    assert archive_code(bytes(lie), LIMITS.replace(max_members=5)) == "ingest.archive.members"


@pytest.mark.parametrize("delta", [-1, 0, 1])
def test_sec07_member_count_cap(delta):
    n = 7
    data = make_zip([(f"m{i}", b"x") for i in range(n)])
    limits = LIMITS.replace(max_members=n + delta)
    if delta < 0:
        assert archive_code(data, limits) == "ingest.archive.members"
    else:
        assert len(decisions(data, limits)) == n


def test_sec07_zip64_end_record_is_read_and_checked():
    cd = crafted_cd(70_000)
    zip64 = struct.pack("<4sQ2H2L4Q", b"PK\x06\x06", 44, 45, 45, 0, 0, 70_000, 70_000, len(cd), 0)
    locator = struct.pack("<4sLQL", b"PK\x06\x07", 0, len(cd), 1)
    classic = struct.pack("<4s4H2LH", b"PK\x05\x06", 0, 0, 0xFFFF, 0xFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0)
    data = cd + zip64 + locator + classic
    pre = zip_precheck(io.BytesIO(data))
    assert (pre.zip64, pre.entries, pre.cd_size, pre.cd_offset) == (True, 70_000, len(cd), 0)
    assert pre.end_offset == len(cd)
    over = LIMITS.replace(max_cd_bytes=len(cd) - 1)
    with pytest.raises(IngestError) as info:
        zip_precheck(io.BytesIO(data), over)
    assert info.value.code == "ingest.archive.cd"


def test_sec07_inconsistent_zip64_record_is_a_format_error():
    cd = crafted_cd(3)
    zip64 = struct.pack("<4sQ2H2L4Q", b"PK\x06\x06", 44, 45, 45, 0, 0, 3, 3, 10**15, 0)  # lying 64-bit CD size
    locator = struct.pack("<4sLQL", b"PK\x06\x07", 0, len(cd), 1)
    classic = struct.pack("<4s4H2LH", b"PK\x05\x06", 0, 0, 0xFFFF, 0xFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0)
    with pytest.raises(IngestError) as info:
        zip_precheck(io.BytesIO(cd + zip64 + locator + classic))
    assert info.value.code == "ingest.archive.format"


def test_sec07_file_size_cap_on_the_container():
    data = make_zip([("a", b"1")])
    assert archive_code(data, LIMITS.replace(max_artefact_bytes=len(data) - 1)) == "ingest.size.file"
    assert len(decisions(data, LIMITS.replace(max_artefact_bytes=len(data)))) == 1


# ---------------------------------------------------------------------------------------------- SEC-07: structure
def test_sec07_prefix_polyglot_is_rejected():
    data = make_zip([("a", b"1")])
    assert archive_code(b"#!/bin/sh\necho self-extractor\n" + data) == "ingest.archive.prefix"
    assert archive_code(b"MZ" + bytes(60) + data) == "ingest.archive.prefix"


def _obs_g8_prepended() -> bytes:
    """The exact obs-G8 case (``investigation/spec/G_evidence/g_zip_precheck.py``, "data prepended"): ten empty
    ``ZIP_STORED`` members named ``f"{i:07x}"``, with the 10 bytes ``#!/bin/sh\\n`` prepended and no offset rebased."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        for i in range(10):
            z.writestr(f"{i:07x}", b"")
    return b"#!/bin/sh\n" + buf.getvalue()


def test_sec07_obs_g8_exact_reproduction_is_accepted_by_zipfile_and_rejected_by_the_post_open_prefix_check():
    """G.3.5 step 3, D-47 item 2. CPython detects the prefix and adds its length to every offset, so ``zipfile`` reads
    all ten members (obs-G8: ``ZipFile(): n=10``). The struct pre-check passes, because the stated central directory lies
    inside the file; the post-open check (smallest ``header_offset`` must be 0) is what rejects the archive."""
    data = _obs_g8_prepended()
    with zipfile.ZipFile(io.BytesIO(data)) as zf:  # the control: zipfile accepts it
        infos = zf.infolist()
        assert [i.filename for i in infos] == [f"{i:07x}" for i in range(10)]
        assert min(i.header_offset for i in infos) == 10 and all(zf.read(i) == b"" for i in infos)
    pre = zip_precheck(io.BytesIO(data), LIMITS)
    assert (pre.entries, pre.trailing_bytes, pre.zip64) == (10, 0, False)
    assert archive_code(data) == "ingest.archive.prefix"
    with pytest.raises(IngestError) as err:
        open_zip(io.BytesIO(data), release=False)
    assert err.value.code == "ingest.archive.prefix" and "#!/bin/sh" not in str(err.value)
    with open_zip(io.BytesIO(data[10:]), release=False) as z:  # the same archive without the prefix opens
        assert len(list(iter_zip_members(z))) == 10


def test_sec07_trailing_data_is_recorded_not_rejected():
    data = make_zip([("a", b"1")])
    with open_zip(io.BytesIO(data + b"trailing garbage"), release=False) as z:
        assert [(f.code, f.severity) for f in z.findings] == [("ingest.archive.trailing", "warning")]
        assert z.precheck.trailing_bytes == len(b"trailing garbage")
        (member,) = iter_zip_members(z)
        assert z.read_member(member) == b"1"
    with open_zip(io.BytesIO(data), release=False) as z:
        assert z.findings == ()


def test_sec07_archive_comment_is_not_trailing_data():
    data = make_zip([("a", b"1")])
    commented = data[:-2] + struct.pack("<H", 5) + b"hello"
    with open_zip(io.BytesIO(commented), release=False) as z:
        assert z.findings == ()


def test_sec07_full_overlap_two_entries_one_local_header():
    data = make_zip([("a", b"1" * 50), ("b", b"2" * 50)])
    first_offset = struct.unpack_from("<L", data, cd_entry_offsets(data)[0] + 42)[0]
    assert archive_code(patch_cd(data, 1, offset=first_offset)) == "ingest.archive.overlap"


def test_sec07_partial_overlap_member_data_runs_into_the_next_entry():
    data = make_zip([("a", b"1" * 50), ("b", b"2" * 50)], zipfile.ZIP_STORED)
    assert archive_code(patch_cd(data, 0, csize=70, usize=70)) == "ingest.archive.overlap"


def test_sec07_local_header_extra_field_length_is_counted_in_the_overlap_check():
    # The first member's local header claims a long extra field, so its data would start inside the next entry.
    data = make_zip([("a", b"1" * 10), ("b", b"2" * 10)], zipfile.ZIP_STORED)
    cd0 = cd_entry_offsets(data)[0]
    local0 = struct.unpack_from("<L", data, cd0 + 42)[0]
    forged = bytearray(data)
    struct.pack_into("<H", forged, local0 + 28, 60)
    assert archive_code(bytes(forged)) == "ingest.archive.overlap"


def test_sec07_bad_local_header_signature_rejects_the_archive():
    data = bytearray(make_zip([("a", b"1")]))
    data[0:4] = b"XXXX"
    assert archive_code(bytes(data)) in {"ingest.archive.format", "ingest.archive.prefix"}


# ---------------------------------------------------------------------------------------------- SEC-07: member gate
def test_sec07_encrypted_member_is_rejected_alone():
    data = make_zip([("secret", b"x"), ("ok", b"y")])
    assert decisions(patch_cd(data, 0, flags=0x1)) == [
        ("secret", "rejected", "ingest.archive.encrypted"),
        ("ok", "selected", None),
    ]
    assert decisions(patch_cd(data, 0, flags=0x41))[0][2] == "ingest.archive.encrypted"  # strong encryption bit


@pytest.mark.parametrize("method", [1, 6, 9, 12, 14, 95, 98, 99])
def test_sec07_methods_outside_the_allowed_set(method):
    data = make_zip([("m", b"x"), ("ok", b"y")], zipfile.ZIP_STORED)
    assert decisions(patch_cd(data, 0, method=method)) == [
        ("m", "rejected", "ingest.archive.method"),
        ("ok", "selected", None),
    ]


@pytest.mark.parametrize("method", sorted(LIMITS.zip_methods))
def test_sec07_allowed_methods_are_accepted(method):
    assert decisions(make_zip([("m", b"x" * 40)], method)) == [("m", "selected", None)]


def test_sec07_crc_mismatch_rejects_that_member_when_streamed():
    data = bytearray(make_zip([("bad", b"abcdefgh"), ("good", b"12345678")], zipfile.ZIP_STORED))
    at = bytes(data).find(b"abcdefgh")
    data[at] ^= 0xFF
    with open_zip(io.BytesIO(bytes(data)), release=False) as z:
        bad, good = list(iter_zip_members(z))
        with pytest.raises(IngestError) as info:
            b"".join(bad.iter_chunks())
        assert info.value.code == "ingest.archive.crc"
        assert b"".join(good.iter_chunks()) == b"12345678"  # the other member is unharmed


def test_sec07_declared_size_smaller_than_the_data_stops_at_the_declared_size_and_fails_the_crc():
    data = patch_cd(make_zip([("m", b"A" * 1000)], zipfile.ZIP_STORED), 0, usize=10, csize=10)
    with open_zip(io.BytesIO(data), release=False) as z:
        (member,) = iter_zip_members(z)
        got = bytearray()
        with pytest.raises(IngestError) as info:
            for chunk in member.iter_chunks():
                got += chunk
        assert info.value.code == "ingest.archive.crc"
        assert len(got) <= 10  # nothing beyond the declared size was ever read


def test_sec07_declared_size_larger_than_the_data_is_a_size_mismatch():
    data = patch_local(patch_cd(make_zip([("m", b"A" * 100)]), 0, usize=5000), 0, usize=5000)
    with open_zip(io.BytesIO(data), release=False) as z:
        (member,) = iter_zip_members(z)
        with pytest.raises(IngestError) as info:
            b"".join(member.iter_chunks())
        assert info.value.code in {"ingest.archive.size", "ingest.stream.truncated", "ingest.archive.crc"}


def test_sec07_whole_archive_versus_per_member_dispositions():
    data = make_zip([("bad.link", b"t"), ("a/ok.json", b"{}"), ("b/ok.json", b"[]")],
                    attrs={"bad.link": (stat.S_IFLNK | 0o777) << 16})
    got = decisions(data)
    assert got[0] == ("bad.link", "rejected", "ingest.archive.link")
    assert [d for _, d, _ in got[1:]] == ["selected", "selected"]  # per-member: the others are still stored
    assert archive_code(b"x" + data) == "ingest.archive.prefix"  # structural: nothing is stored


def test_sec07_not_selected_members_are_never_decompressed(monkeypatch):
    data = make_zip([("keep.json", b"{}"), ("noise.bin", b"z" * 5000), ("also.noise", b"z")])
    with open_zip(io.BytesIO(data), release=False) as z:
        monkeypatch.setattr(zipfile.ZipFile, "open", lambda *a, **k: pytest.fail("a member was decompressed"))
        got = [(m.label, m.disposition) for m in iter_zip_members(z, lambda label: label.endswith(".json"))]
    assert got == [("keep.json", "selected"), ("noise.bin", "not_selected"), ("also.noise", "not_selected")]


def test_sec07_many_selected_megabytes_beyond_a_small_job_cap_are_accepted_when_within_member_and_total_limits():
    # R-40 scaled down: the member and total caps (not an output cap) are what bound the selected bytes.
    limits = LIMITS.replace(max_member_bytes=4096, max_total_bytes=4096 * 8)
    data = make_zip([(f"m{i}", os.urandom(4096)) for i in range(8)], zipfile.ZIP_STORED)
    assert [d for _, d, _ in decisions(data, limits)] == ["selected"] * 8
    assert decisions(data, limits.replace(max_total_bytes=4096 * 8 - 1))[-1] == ("m7", "rejected", "ingest.archive.size")


def test_sec07_tar_is_refused_with_exit_5_and_never_opened():
    block = bytearray(512)
    block[:8] = b"file.txt"
    block[257:263] = b"ustar\x00"
    with pytest.raises(IngestError) as info:
        open_archive(io.BytesIO(bytes(block) + bytes(1024)), release=False)
    assert (info.value.code, info.value.exit_code) == ("ingest.archive.format", 5)


# ---------------------------------------------------------------------------------------------- SEC-07: bombs
def test_sec07_deflate_zip_bomb_is_stopped_by_the_ratio_before_any_decompression(monkeypatch):
    data = make_zip([("bomb", bytes(8 * 1024 * 1024))])
    assert len(data) < 20_000
    monkeypatch.setattr(zipfile.ZipFile, "open", lambda *a, **k: pytest.fail("bomb was decompressed"))
    assert decisions(data) == [("bomb", "rejected", "ingest.archive.ratio")]


def test_sec07_ratio_is_not_applied_below_the_floor():
    assert decisions(make_zip([("small-zeros", bytes(LIMITS.ratio_floor_bytes))])) == [("small-zeros", "selected", None)]
    assert decisions(make_zip([("big-zeros", bytes(LIMITS.ratio_floor_bytes + 1))]))[0][2] == "ingest.archive.ratio"


def test_sec07_declared_size_lie_cannot_inflate_the_allocation():
    # The header claims 100 bytes; the deflate stream really expands to 8 MiB. Only the declared size is read.
    data = make_zip([("liar", bytes(8 * 1024 * 1024))])
    lied = patch_local(patch_cd(data, 0, usize=100), 0, usize=100)
    with open_zip(io.BytesIO(lied), release=False) as z:
        (member,) = iter_zip_members(z)
        total = 0
        with pytest.raises(IngestError):
            for chunk in member.iter_chunks():
                total += len(chunk)
        assert total <= 100


def test_sec07_member_size_cap_on_declared_size_before_any_read(monkeypatch):
    data = make_zip([("big", b"q" * 5000)], zipfile.ZIP_STORED)
    limits = LIMITS.replace(max_member_bytes=4999)
    monkeypatch.setattr(zipfile.ZipFile, "open", lambda *a, **k: pytest.fail("opened"))
    assert decisions(data, limits) == [("big", "rejected", "ingest.archive.size")]


# ---------------------------------------------------------------------------------------------- SEC-07: links
@pytest.mark.parametrize("mode", [stat.S_IFLNK, stat.S_IFCHR, stat.S_IFBLK, stat.S_IFIFO, stat.S_IFSOCK, stat.S_IFDIR])
def test_sec07_non_regular_unix_modes_are_rejected(mode):
    data = make_zip([("x", b"target")], attrs={"x": (mode | 0o777) << 16})
    assert decisions(data) == [("x", "rejected", "ingest.archive.link")]


def test_sec07_regular_unix_mode_and_no_type_bits_are_regular():
    data = make_zip([("r", b"1"), ("n", b"2")], attrs={"r": (stat.S_IFREG | 0o644) << 16, "n": 0o644 << 16})
    assert [d for _, d, _ in decisions(data)] == ["selected", "selected"]


# ---------------------------------------------------------------------------------------------- SEC-08: traversal labels
@pytest.mark.parametrize(
    "name", ["../../x", "..", "a/../../b", "/etc/passwd", "//server/share", "C:\\x", "c:/x", "a\\b", "..\\..\\x"]
)
def test_sec08_traversal_names_are_labels_that_are_rejected_and_never_opened(name, fs_guard):
    got = decisions(make_zip([(name, b"payload"), ("fine.json", b"{}")]))
    assert got[0][1:] == ("rejected", "ingest.archive.traversal")
    assert got[1] == ("fine.json", "selected", None)


def test_sec08_nothing_is_written_when_selected_members_are_streamed(fs_guard):
    data = make_zip([("a/b/c.json", b"{}"), ("../../escape", b"x"), ("/abs", b"y")])
    with open_zip(io.BytesIO(data), release=False) as z:
        for member in iter_zip_members(z):
            if member.disposition == "selected":
                assert b"".join(member.iter_chunks()) == b"{}"
    assert not os.path.exists("a") and not os.path.exists(os.path.join("..", "..", "escape"))


def test_sec08_member_to_json_never_exposes_the_raw_name():
    with open_zip(io.BytesIO(make_zip([("../x", b"1")])), release=False) as z:
        (member,) = iter_zip_members(z)
        assert member.label is None and "../x" not in str(member.to_json())


# ---------------------------------------------------------------------------------------------- names and duplicates
def test_sec07_duplicate_names_and_collisions_reject_every_colliding_member():
    nfc, nfd = "caf" + chr(0xE9) + ".json", "cafe" + chr(0x301) + ".json"
    assert unicodedata.normalize("NFC", nfd) == nfc
    for pair in ([("a.json", b"1"), ("a.json", b"2")], [("A.json", b"1"), ("a.JSON", b"2")], [(nfc, b"1"), (nfd, b"2")]):
        got = decisions(make_zip([*pair, ("other.json", b"3")]))
        assert [c for _, _, c in got] == ["ingest.archive.duplicate", "ingest.archive.duplicate", None]


def test_sec07_hostile_names_are_rejected_with_name_codes():
    names = ["a" + chr(0x1B) + "[2J", "bidi" + chr(0x202E) + "gnp.json", "x" + chr(0) + "y", "CON", "trail.", "a" * 300]
    got = decisions(make_zip([(n, b"1") for n in names if chr(0) not in n] + [("ok", b"1")]))
    codes = [c for _, _, c in got]
    assert codes[0] == "ingest.name.invalid" and codes[2:5] == ["ingest.name.invalid"] * 3
    assert codes[1] is None  # a bidi override is a label: accepted, always displayed escaped (G.3.6 lists C0/C1 only)
    assert codes[-1] is None


# ---------------------------------------------------------------------------------------------- SEC-05: nesting
def test_sec05_nested_archive_depth_three_is_never_opened():
    level3 = make_zip([("leaf.json", b"{}")])
    level2 = make_zip([("level3.zip", level3)], zipfile.ZIP_STORED)
    level1 = make_zip([("level2.zip", level2)], zipfile.ZIP_STORED)
    opened = []
    data = level1
    for depth in (1, 2, 3):
        if depth <= LIMITS.max_archive_depth:
            with open_zip(io.BytesIO(data), release=False, depth=depth) as z:
                (member,) = iter_zip_members(z, lambda label: label.endswith(".zip"))
                data = z.read_member(member)
                opened.append(depth)
        else:
            with pytest.raises(IngestError) as info:
                open_zip(io.BytesIO(data), release=False, depth=depth)
            assert info.value.code == "ingest.archive.depth"
    assert opened == [1, 2]


def test_sec05_an_undeclared_nested_archive_is_not_expanded(monkeypatch):
    inner = make_zip([("x", b"1")])
    outer = make_zip([("data.json", b"{}"), ("hidden.zip", inner)], zipfile.ZIP_STORED)
    with open_zip(io.BytesIO(outer), release=False) as z:
        monkeypatch.setattr(zipfile.ZipFile, "open", lambda *a, **k: pytest.fail("a not-selected member was read"))
        got = [(m.label, m.disposition) for m in iter_zip_members(z, lambda label: label.endswith(".json"))]
    assert got == [("data.json", "selected"), ("hidden.zip", "not_selected")]


def test_sec05_a_nested_archive_bomb_is_bounded_by_the_member_and_ratio_gates():
    inner = make_zip([("zeros", bytes(4 * 1024 * 1024))])
    outer = make_zip([("inner.zip", inner * 3)], zipfile.ZIP_DEFLATED)
    got = decisions(outer, include=lambda label: label.endswith(".zip"))
    assert got[0][1] in {"selected", "rejected"}  # the outer layer is judged on its own declared sizes only
    inner_code = decisions(inner)[0][2]
    assert inner_code == "ingest.archive.ratio"


# ---------------------------------------------------------------------------------------------- guard
def test_sec07_interpreter_guard_refuses_before_the_object_is_opened_in_release_mode(monkeypatch):
    class Unreadable(io.BytesIO):
        def read(self, *a):
            raise AssertionError("opened")

        seek = read

    monkeypatch.setattr("sys.version_info", (3, 14, 7, "final", 0))
    with pytest.raises(InterpreterUnpatchedError):
        open_zip(Unreadable(), release=True)
    with pytest.raises(InterpreterUnpatchedError):
        open_archive(Unreadable(make_zip([("a", b"1")])), release=True)
