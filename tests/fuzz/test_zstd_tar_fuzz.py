"""K.11.1 over the zstd tar reader (D-240): mutated tar bytes, mutated zstd frames and hand-made frame headers give a typed
outcome only.

Every input either opens and yields members whose labels are valid and whose bytes match their size and CRC, or fails
with a G.3.9 ``ingest.*`` code (F-1). Inputs and limits are small (F-2); nothing is written (F-3, the module ``fs_guard``).
"""

from __future__ import annotations

import io
import struct
import zlib

from format_support import tar_bytes, zstd_stream
from fuzz_support import budget, byte_mutations, outcome
from hypothesis import given
from hypothesis import strategies as st

from agentprov.ingest.archives import iter_zip_members, open_archive
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.names import logical_name
from agentprov.ingest.streams import iter_zstd_bounded

LIMITS = IngestLimits().replace(max_tar_stream_bytes=1 << 20, max_member_bytes=1 << 16, max_total_bytes=1 << 18,
                                max_members=64, max_zstd_frames=8, zstd_window_log_max=20)  # fmt: skip
TAR = tar_bytes([("runs", None), ("runs/" + "n" * 120 + ".json", b'{"a": 1}'), ("runs/b.json", b"[]"),
                 ("runs/qwen3.6:27b/c.json", b"{}")])  # fmt: skip
TZST = zstd_stream(TAR, window_log=16, frames=2)


def _read_all(data: bytes) -> list[tuple[str | None, str, int]]:
    archive = open_archive(io.BytesIO(data), LIMITS, release=False, depth=1)
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
def test_mutated_tar_bytes_in_zstd_give_a_typed_outcome(mutated: bytes) -> None:
    kind, _ = outcome(lambda: _read_all(zstd_stream(mutated, window_log=16)))
    assert kind in ("ok", "ingest")


@budget(200)
@given(byte_mutations(TZST, max_ops=3))
def test_mutated_zstd_bytes_give_a_typed_outcome(mutated: bytes) -> None:
    kind, _ = outcome(lambda: _read_all(mutated))
    assert kind in ("ok", "ingest")


@budget(200)
@given(st.binary(min_size=0, max_size=14), st.binary(max_size=64))
def test_arbitrary_frame_headers_give_a_typed_outcome(header: bytes, tail: bytes) -> None:
    data = struct.pack("<I", 0xFD2FB528) + header + tail
    kind, _ = outcome(lambda: sum(len(c) for c in iter_zstd_bounded(data, LIMITS, max_bytes=LIMITS.max_tar_stream_bytes)))
    assert kind in ("ok", "ingest")


def test_the_seed_itself_reads_cleanly() -> None:
    assert [d for _l, d, _s in _read_all(TZST)] == ["selected"] * 3
