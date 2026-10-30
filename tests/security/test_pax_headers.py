"""SEC-05/08: pax ``x`` extended headers are read as data through a closed key allowlist (D-248; phase 10i's D-192).

``path`` and ``size`` apply to the next entry, under the names guard and the member gate; timestamps, owners and
extended attributes (``SCHILY.xattr.*``, ``LIBARCHIVE.xattr.*``, macOS ``com.apple.provenance``) are ignored; every other
key, a global ``g`` header, a malformed record and a header over ``max_pax_header_bytes`` refuse the archive. ``tarfile``
is only the trusted writer of benign inputs here.
"""

from __future__ import annotations

import gzip
import io
import tarfile

import pytest
from test_nested_tar import END, body, header

from agentprov.errors import IngestError
from agentprov.ingest.archives import OpenedTar, iter_zip_members, open_archive
from agentprov.ingest.limits import IngestLimits

LIMITS = IngestLimits()


def record(key: bytes, value: bytes) -> bytes:
    """One pax record ``"<len> <key>=<value>\\n"`` with its self-including length."""
    rest = b" " + key + b"=" + value + b"\n"
    n = len(rest) + 1
    while len(str(n).encode()) + len(rest) != n:
        n += 1
    return str(n).encode() + rest


def pax(records: bytes, name: bytes = b"PaxHeader/x") -> bytes:
    return header(name, b"x", len(records), magic=b"ustar\x0000") + body(records)


def entry(name: bytes, data: bytes) -> bytes:
    return header(name, b"0", len(data), magic=b"ustar\x0000") + body(data)


def decisions(raw: bytes, limits: IngestLimits = LIMITS, depth: int = 1):
    archive = open_archive(io.BytesIO(gzip.compress(raw, mtime=0)), limits, release=False, depth=depth)
    assert isinstance(archive, OpenedTar)
    return [(m.label, m.disposition, m.code, archive.read_member(m) if m.disposition == "selected" else None)
            for m in iter_zip_members(archive, None, limits)]  # fmt: skip


def code_of(raw: bytes, limits: IngestLimits = LIMITS) -> str:
    with pytest.raises(IngestError) as err:
        decisions(raw, limits)
    return err.value.code


@pytest.fixture(autouse=True)
def _cwd(cwd_guard):
    return cwd_guard


def test_the_agentops_shape_mtime_and_macos_provenance_xattrs_are_ignored():
    """D-192: bsdtar on macOS writes an ``x`` header with ``mtime`` and ``LIBARCHIVE.xattr.com.apple.provenance``."""
    recs = record(b"mtime", b"1760000000.123456") + record(b"LIBARCHIVE.xattr.com.apple.provenance", b"AQIA2Q0=") \
        + record(b"SCHILY.xattr.com.apple.provenance", b"\x01\x02\x00\xd9")  # fmt: skip
    raw = pax(recs) + entry(b"runs/agentops/r1.json", b'{"ok": 1}') + END
    assert decisions(raw) == [("runs/agentops/r1.json", "selected", None, b'{"ok": 1}')]


def test_path_replaces_the_header_name_and_goes_through_the_names_guard():
    long = ("runs/" + "é" * 120 + "/r.json").encode()
    assert decisions(pax(record(b"path", long)) + entry(b"truncated", b"1") + END)[0][:2] == (long.decode(), "selected")
    for hostile, code in ((b"../etc/passwd", "ingest.archive.traversal"), (b"/abs.json", "ingest.archive.traversal"),
                          (b"a\x1bb.json", "ingest.name.invalid"), (b"\xff\xfe.json", "ingest.name.invalid")):  # fmt: skip
        assert decisions(pax(record(b"path", hostile)) + entry(b"ok.json", b"1") + END)[0][:3] == (None, "rejected", code)


def test_a_path_over_max_name_bytes_rejects_that_entry_only():
    too_long = b"d/" * 600 + b"x.json"
    raw = pax(record(b"path", too_long)) + entry(b"x", b"1") + entry(b"ok.json", b"2") + END
    assert [(lbl, d, c) for lbl, d, c, _b in decisions(raw)] == [(None, "rejected", "ingest.name.invalid"),
                                                                  ("ok.json", "selected", None)]


def test_size_overrides_the_header_size_and_the_member_gate_applies():
    data = b"x" * 3000
    raw = pax(record(b"size", b"3000")) + header(b"a.json", b"0", 0, magic=b"ustar\x0000") + body(data) + END
    assert decisions(raw)[0][3] == data
    small = LIMITS.replace(max_member_bytes=2999)
    assert decisions(raw, small)[0][:3] == ("a.json", "rejected", "ingest.archive.size")


@pytest.mark.parametrize("key", [b"linkpath", b"hdrcharset", b"GNU.sparse.size", b"SCHILY.fflags", b"comment", b"charset"])
def test_keys_outside_the_allowlist_refuse_the_archive(key):
    assert code_of(pax(record(key, b"v")) + entry(b"a.json", b"1") + END) == "ingest.archive.format"


@pytest.mark.parametrize("records", [
    b"5 a=b\n",                       # length too short for its record
    b"99 path=a.json\n",              # length beyond the header
    b"x path=a.json\n",               # not a number
    b"14 path=a.json",                # no LF
    b"10 noequal\n",                  # no '='
    b"9 =value\n",                    # empty key
    record(b"path", b"a") + record(b"path", b"b"),  # duplicate key
    record(b"size", b"-1"), record(b"size", b"1e3"), record(b"size", b"9" * 21),
])  # fmt: skip
def test_malformed_records_refuse_the_archive(records):
    assert code_of(pax(records) + entry(b"a.json", b"1") + END) == "ingest.archive.format"


def test_structure_rules_around_pax_headers():
    one = pax(record(b"mtime", b"1"))
    assert code_of(one + one + entry(b"a.json", b"1") + END) == "ingest.archive.format"  # two in a row
    assert code_of(one + END) == "ingest.archive.format"  # no entry after it
    assert code_of(one + header(b"././@LongLink", b"L", 6) + body(b"a.json") + entry(b"x", b"1") + END) == "ingest.archive.format"
    assert code_of(header(b"g", b"g", 0, magic=b"ustar\x0000") + entry(b"a.json", b"1") + END) == "ingest.archive.format"


def test_a_pax_header_over_the_limit_is_refused_without_buffering():
    big = record(b"SCHILY.xattr.user.big", b"v" * (70 * 1024))
    assert code_of(pax(big) + entry(b"a.json", b"1") + END) == "ingest.archive.format"
    roomy = LIMITS.replace(max_pax_header_bytes=128 * 1024)
    assert decisions(pax(big) + entry(b"a.json", b"1") + END, roomy)[0][:2] == ("a.json", "selected")


def test_a_pax_tar_written_by_tarfile_round_trips_names_and_bytes():
    entries = [("r/été/" + "n" * 120 + ".json", b'{"a": 1}'), ("r/plain.json", b"[]")]
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.PAX_FORMAT) as tf:
        for name, data in entries:
            info = tarfile.TarInfo(name)
            info.size, info.mtime = len(data), 0
            info.pax_headers = {"SCHILY.xattr.com.apple.provenance": "\x01\x02"}
            tf.addfile(info, io.BytesIO(data))
    got = decisions(buf.getvalue())
    assert [(lbl, b) for lbl, _d, _c, b in got] == entries
