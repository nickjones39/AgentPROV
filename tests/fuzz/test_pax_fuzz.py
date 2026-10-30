"""K.11.1 over pax ``x`` headers (D-248): mutated pax records and mutated pax tars give a typed outcome only (F-1, F-2, F-3).

The seed is a pax tar with ``path``, ``size``, ``mtime`` and an extended attribute; every mutation either reads with
valid labels and CRC-checked bytes or fails with a G.3.9 code.
"""

from __future__ import annotations

import gzip
import io
import tarfile
import zlib

from fuzz_support import budget, byte_mutations, outcome
from hypothesis import given

from agentprov.ingest.archives import iter_zip_members, open_archive
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.names import logical_name

LIMITS = IngestLimits().replace(max_tar_stream_bytes=1 << 20, max_member_bytes=1 << 16, max_total_bytes=1 << 18,
                                max_members=64, max_pax_header_bytes=4096)  # fmt: skip


def _seed() -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.PAX_FORMAT) as tf:
        for name, data in [("runs/été.json", b'{"a": 1}'), ("runs/" + "n" * 120 + ".json", b"[]")]:
            info = tarfile.TarInfo(name)
            info.size, info.mtime = len(data), 1760000000
            info.pax_headers = {"LIBARCHIVE.xattr.com.apple.provenance": "AQIA2Q0="}
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


PAX = _seed()


def _read_all(data: bytes) -> list[tuple[str | None, str]]:
    archive = open_archive(io.BytesIO(gzip.compress(data, mtime=0)), LIMITS, release=False, depth=1)
    out = []
    for member in iter_zip_members(archive, None, LIMITS):
        if member.disposition == "selected":
            content = archive.read_member(member)
            assert len(content) == member.file_size and zlib.crc32(content) == member.crc32
            assert member.label is not None and logical_name(member.label, LIMITS) == member.label
        out.append((member.label, member.disposition))
    return out


@budget(300)
@given(byte_mutations(PAX, max_ops=4))
def test_mutated_pax_tars_give_a_typed_outcome(mutated: bytes) -> None:
    kind, _ = outcome(lambda: _read_all(mutated))
    assert kind in ("ok", "ingest")


def test_the_seed_itself_reads_cleanly() -> None:
    assert [d for _l, d in _read_all(PAX)] == ["selected", "selected"]
