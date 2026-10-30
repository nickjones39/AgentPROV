"""K.11.1 over the nested ``tar.gz`` reader (D-57): mutated tar bytes and mutated gzip bytes give a typed outcome only.

Every input either opens and yields members whose labels are valid and whose bytes match their size and CRC, or fails
with a G.3.9 ``ingest.*`` code (F-1). Inputs are bounded (F-2); nothing is written (F-3, the module ``fs_guard``).
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

LIMITS = IngestLimits().replace(max_stream_bytes=1 << 20, max_member_bytes=1 << 16, max_total_bytes=1 << 18,
                                max_members=64)  # fmt: skip


def _seed() -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.GNU_FORMAT) as tf:
        for name, data in [("runs", None), ("runs/" + "n" * 120 + ".json", b'{"a": 1}'), ("runs/b.json", b"[]"),
                           ("runs/qwen3.6:27b/c.json", b"{}")]:  # fmt: skip
            info = tarfile.TarInfo(name)
            info.mtime = 0
            if data is None:
                info.type = tarfile.DIRTYPE
                tf.addfile(info)
            else:
                info.size = len(data)
                tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


TAR = _seed()
TGZ = gzip.compress(TAR, mtime=0)


def _read_all(data: bytes) -> list[tuple[str | None, str, int]]:
    archive = open_archive(io.BytesIO(data), LIMITS, release=False, depth=2)
    out = []
    for member in iter_zip_members(archive, None, LIMITS):
        if member.disposition == "selected":
            content = archive.read_member(member)
            assert len(content) == member.file_size <= LIMITS.max_member_bytes
            assert zlib.crc32(content) == member.crc32
            assert member.label is not None and logical_name(member.label, LIMITS) == member.label
        out.append((member.label, member.disposition, member.file_size))
    return out


@budget(150)
@given(byte_mutations(TAR, max_ops=4))
def test_mutated_tar_bytes_give_a_typed_outcome(mutated: bytes) -> None:
    kind, _ = outcome(lambda: _read_all(gzip.compress(mutated, mtime=0)))
    assert kind in ("ok", "ingest")


@budget(150)
@given(byte_mutations(TGZ, max_ops=3))
def test_mutated_gzip_bytes_give_a_typed_outcome(mutated: bytes) -> None:
    kind, _ = outcome(lambda: _read_all(mutated))
    assert kind in ("ok", "ingest")


def test_the_seed_itself_reads_cleanly() -> None:
    assert [d for _l, d, _s in _read_all(TGZ)] == ["selected"] * 3
