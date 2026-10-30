"""Container and codec sniffing (G.3.1 step 2, G.3.4). Decompression is deferred in v0.1."""

from __future__ import annotations

import io

import pytest

from agentprov.envinfo import InterpreterUnpatchedError
from agentprov.errors import IngestError
from agentprov.ingest.streams import (
    deferred_codec_finding,
    open_compressed_bounded,
    sniff_codec,
    sniff_container,
)

MAGIC = {
    "gzip": b"\x1f\x8b\x08\x00",
    "bzip2": b"BZh91AY&",
    "xz": b"\xfd7zXZ\x00\x00",
    "zstd": b"\x28\xb5\x2f\xfd\x00",
}


@pytest.mark.parametrize(("codec", "head"), MAGIC.items())
def test_codec_by_magic_only(codec, head):
    assert sniff_codec(head) == codec
    assert sniff_container(head) == codec


def test_zip_and_document():
    assert sniff_container(b"PK\x03\x04rest") == "zip"
    assert sniff_container(b'{"a":1}') == "document"
    assert sniff_container(b"") == "document"
    assert sniff_codec(b"PK\x03\x04") is None


def test_deferred_finding_is_a_register_code():
    finding = deferred_codec_finding("gzip")
    assert finding.code == "ingest.stream.codec" and "deferred" in (finding.detail or "")


def test_open_compressed_bounded_refuses_every_codec():
    for head in MAGIC.values():
        with pytest.raises(IngestError) as info:
            open_compressed_bounded(io.BytesIO(head))
        assert info.value.code == "ingest.stream.codec"


def test_guard_runs_before_the_deferred_refusal(monkeypatch):
    monkeypatch.setattr("sys.version_info", (3, 14, 7, "final", 0))
    with pytest.raises(InterpreterUnpatchedError):
        open_compressed_bounded(io.BytesIO(MAGIC["gzip"]), release=True)
