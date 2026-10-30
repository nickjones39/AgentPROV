"""Properties of the D-240-D-243 readers: each one is the existing reader seen through a new framing.

* Streamed JSON (D-242): for any document and any declared set of its top-level arrays, the stream reader accepts it and
  the envelope plus the elements reassemble exactly what ``strict_json_loads`` returns (key order, types, ``-0.0``).
* Split zip (D-243): for any member set and any cut points, the parts in order read exactly the unsplit zip.
* Compressed tar (D-240): a tar read from zstd (any level, any number of frames) yields exactly the members, CRCs and bytes
  read from gzip (D-57).
"""

from __future__ import annotations

import gzip
import io
import json
import math
import zipfile
from typing import Any

from format_support import tar_bytes, zip_bytes, zstd_stream
from hypothesis import given, settings
from hypothesis import strategies as st

from agentprov.ingest.archives import iter_zip_members, open_archive, open_split_zip, open_zip
from agentprov.ingest.jsonstream import open_json_stream
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads

S = settings(max_examples=200, deadline=None, derandomize=True)
LIMITS = IngestLimits()

SCALARS = st.one_of(st.none(), st.booleans(), st.integers(-(2**70), 2**70),
                    st.floats(allow_nan=False, allow_infinity=False), st.text(max_size=12))  # fmt: skip
VALUES = st.recursive(SCALARS, lambda c: st.lists(c, max_size=4) | st.dictionaries(st.text(max_size=6), c, max_size=4),
                      max_leaves=10)  # fmt: skip
KEYS = st.sampled_from(["messages", "events", "a/b", "~x", "[,]", "é"])


def same(a: Any, b: Any) -> bool:
    if isinstance(a, dict) and isinstance(b, dict):
        return list(a) == list(b) and all(same(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b, strict=True))
    if isinstance(a, float) and isinstance(b, float):
        return a == b and math.copysign(1, a) == math.copysign(1, b)
    return type(a) is type(b) and a == b


def _pointer(key: str) -> str:
    return "/" + key.replace("~", "~0").replace("/", "~1")


@S
@given(st.dictionaries(KEYS, st.lists(VALUES, max_size=5) | VALUES, min_size=1, max_size=4), st.data(),
       st.sampled_from([None, 0, 2]), st.booleans())  # fmt: skip
def test_streamed_json_reassembles_the_whole_document_value(doc: dict, data, indent, ascii_only) -> None:
    raw = json.dumps(doc, indent=indent, ensure_ascii=ascii_only).encode()
    array_keys = [k for k, v in doc.items() if isinstance(v, list)]
    chosen = data.draw(st.lists(st.sampled_from(array_keys), unique=True, min_size=1)) if array_keys else []
    whole = strict_json_loads(raw)
    if not chosen:
        return
    stream = open_json_stream(raw, LIMITS, arrays=[_pointer(k) for k in chosen])
    rebuilt = dict(stream.envelope)
    items = list(stream)
    for key in chosen:
        assert rebuilt[key] == []
        rebuilt[key] = [i.value for i in items if i.pointer == _pointer(key)]
        assert stream.counts[_pointer(key)] == len(doc[key])
    assert same(rebuilt, whole)
    assert [i.index for i in items if i.pointer == _pointer(chosen[0])] == list(range(len(doc[chosen[0]])))


@S
@given(st.lists(VALUES, max_size=8), st.sampled_from([None, 1]))
def test_a_streamed_top_level_array_yields_exactly_its_elements(values: list, indent) -> None:
    raw = json.dumps(values, indent=indent).encode()
    stream = open_json_stream(raw, LIMITS, arrays=[""])
    assert stream.envelope == [] and same([i.value for i in stream], strict_json_loads(raw))


MEMBERS = st.lists(st.tuples(st.from_regex(r"[a-z]{1,8}(/[a-z0-9_]{1,8}){0,2}\.json", fullmatch=True),
                             st.binary(max_size=3000)), min_size=1, max_size=6, unique_by=lambda m: m[0])  # fmt: skip


@S
@given(MEMBERS, st.sampled_from([zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED]), st.lists(st.integers(1, 1 << 15), min_size=1, max_size=8))
def test_a_split_zip_in_order_is_the_unsplit_zip(members, method, points) -> None:
    data = zip_bytes(members, method)
    cuts = sorted({p % len(data) for p in points} - {0})
    parts = [data[a:b] for a, b in zip([0, *cuts], [*cuts, len(data)], strict=True)]
    if len(parts) < 2:
        parts = [data[:1], data[1:]]
    with open_zip(io.BytesIO(data), LIMITS, release=False) as whole:
        expected = [(m.label, m.crc32, whole.read_member(m)) for m in iter_zip_members(whole, None, LIMITS)]
    with open_split_zip([io.BytesIO(p) for p in parts], [len(p) for p in parts], LIMITS, release=False) as z:
        got = [(m.label, m.crc32, z.read_member(m)) for m in iter_zip_members(z, None, LIMITS)]
    assert got == expected


@S
@given(MEMBERS, st.sampled_from([1, 3, 19]), st.integers(1, 4))
def test_a_zstd_tar_reads_exactly_as_the_same_tar_in_gzip(members, level, frames) -> None:
    raw = tar_bytes(members)

    def read(data: bytes, depth: int) -> list[tuple[str | None, str, int, bytes | None]]:
        archive = open_archive(io.BytesIO(data), LIMITS, release=False, depth=depth)
        return [(m.label, m.disposition, m.crc32, archive.read_member(m) if m.disposition == "selected" else None)
                for m in iter_zip_members(archive, None, LIMITS)]  # fmt: skip

    assert read(zstd_stream(raw, level=level, frames=frames), 1) == read(gzip.compress(raw, mtime=0), 2)


@S
@given(st.binary(max_size=5000), st.sampled_from([None, 10, 17, 22]), st.booleans(), st.booleans())
def test_the_frame_header_parser_agrees_with_libzstd(payload, window_log, pledged, checksum) -> None:
    """Content size and dictionary id as libzstd reads them (``get_frame_info``); the header size as libzstd skips it."""
    from compression import zstd

    from agentprov.ingest.streams import parse_zstd_frame_header

    options = {zstd.CompressionParameter.checksum_flag: int(checksum)}
    if window_log is not None:
        options[zstd.CompressionParameter.window_log] = window_log
    comp = zstd.ZstdCompressor(options=options)
    if pledged:
        frame = comp.compress(payload, zstd.ZstdCompressor.FLUSH_FRAME)
    else:
        frame = comp.compress(payload, zstd.ZstdCompressor.CONTINUE) + comp.flush(zstd.ZstdCompressor.FLUSH_FRAME)
    header = parse_zstd_frame_header(frame[:18])
    info = zstd.get_frame_info(frame)
    assert header.content_size == info.decompressed_size and header.dictionary_id == info.dictionary_id
    assert header.checksum == checksum
    assert header.window_size > 0 or header.content_size == 0
    if window_log is not None and not pledged:
        assert header.window_size == 1 << window_log
