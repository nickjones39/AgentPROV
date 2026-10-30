"""Raw object store: addressing, write protocol, idempotence, caps, protocol conformance (G.3.1; K.5.7(1); C.19(13))."""

from __future__ import annotations

import hashlib
import io
import os
import stat
import threading

import pytest

from agentprov.aer.locators import RawStore
from agentprov.errors import IngestError
from agentprov.host import detect_host
from agentprov.ingest.limits import IngestLimits
from agentprov.raw.store import (
    EXTENSIONS,
    DigestCollisionError,
    LimitedField,
    ObjectCorruptError,
    ObjectMismatchError,
    RawObjectStore,
    RawStoreError,
    ext_for_label,
    ext_for_media,
    limit_field_for,
    put_stream,
    violation_detail,
)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


needs_posix_permissions = pytest.mark.skipif(
    not detect_host(probe=False).caps.posix_permissions,
    reason="chmod bits do not read back on this host (a probed capability; access is governed by ACLs)",
)

@pytest.fixture
def store(tmp_path):
    return RawObjectStore(tmp_path / "raw")


def test_put_stores_bytes_at_the_content_address_with_mode_0444(store):
    data = b'{"a": 1}\n'
    result = store.put(data, ext="json")
    assert result.sha256 == sha(data) and result.size == len(data) and result.created
    expected = store.objects_dir / sha(data)[:2] / f"{sha(data)}.json"
    assert result.path == expected and expected.read_bytes() == data
    assert stat.S_IMODE(os.stat(expected).st_mode) == 0o444
    assert not os.stat(expected).st_mode & 0o111  # no exec bits


@needs_posix_permissions
def test_tmp_dir_is_private_and_empty_after_writes(store):
    store.put(b"x" * 10)
    assert stat.S_IMODE(os.stat(store.tmp_dir).st_mode) == 0o700
    assert list(store.tmp_dir.iterdir()) == []


@needs_posix_permissions
def test_tmp_dir_mode_is_tightened_when_it_pre_exists_loose(tmp_path):
    (tmp_path / "raw" / "tmp").mkdir(parents=True)
    os.chmod(tmp_path / "raw" / "tmp", 0o777)
    RawObjectStore(tmp_path / "raw")
    assert stat.S_IMODE(os.stat(tmp_path / "raw" / "tmp").st_mode) == 0o700


def test_put_is_idempotent_and_never_rewrites_the_object(store):
    first = store.put(b"same", ext="json")
    inode = os.stat(first.path).st_ino
    again = store.put(b"same", ext="jsonl")  # a different extension: informative only, first writer wins
    assert not again.created and again.path == first.path
    assert os.stat(first.path).st_ino == inode
    assert sorted(p.name for p in first.path.parent.iterdir()) == [first.path.name]


def test_store_satisfies_the_aer_rawstore_protocol(store):
    assert isinstance(store, RawStore)
    put = store.put(b"hello")
    assert store.has(put.sha256) is True
    assert store.size(put.sha256) == 5
    assert store.read_bytes(put.sha256) == b"hello"
    missing = sha(b"missing")
    assert store.has(missing) is False
    with pytest.raises(KeyError):
        store.size(missing)
    with pytest.raises(KeyError):
        store.read_bytes(missing)


@pytest.mark.parametrize("bad", ["", "zz", "A" * 64, "../" * 21 + "x", "a" * 63, "a" * 65, "sha256:" + "a" * 64, "ab/" + "c" * 60])
def test_malformed_digests_are_absent_and_never_become_paths(store, bad):
    assert store.has(bad) is False
    with pytest.raises(KeyError):
        store.size(bad)
    with pytest.raises(KeyError):
        store.read_bytes(bad)
    with pytest.raises(KeyError):
        store.open(bad)
    with pytest.raises(ValueError):
        store.path_for(bad)


def test_put_stream_hashes_while_copying_in_small_chunks(store):
    data = os.urandom(300_001)
    result = store.put_stream(io.BytesIO(data), chunk_size=1000)
    assert result.sha256 == sha(data) and store.read_bytes(result.sha256) == data


def test_module_level_put_stream_is_the_same_operation(store):
    result = put_stream(store, io.BytesIO(b"abc"), ext="csv")
    assert result.path.name == f"{sha(b'abc')}.csv"


def test_put_chunks_accepts_any_iterable_including_the_empty_object(store):
    result = store.put_chunks(iter([b"ab", b"", b"cd"]))
    assert result.sha256 == sha(b"abcd")
    empty = store.put(b"")
    assert empty.size == 0 and store.read_bytes(empty.sha256) == b""


@pytest.mark.parametrize("delta", [-1, 0])
def test_size_cap_accepts_up_to_the_limit(tmp_path, delta):
    limit = 1000
    s = RawObjectStore(tmp_path / "raw", limits=IngestLimits().replace(max_artefact_bytes=limit))
    assert s.put_stream(io.BytesIO(b"x" * (limit + delta))).size == limit + delta


def test_size_cap_rejects_limit_plus_one_before_publishing_and_leaves_nothing(tmp_path):
    limit = 1000
    s = RawObjectStore(tmp_path / "raw", limits=IngestLimits().replace(max_artefact_bytes=limit))
    with pytest.raises(IngestError) as exc:
        s.put_stream(io.BytesIO(b"x" * (limit + 1)), chunk_size=100)
    assert exc.value.code == "ingest.size.file" and exc.value.limit == limit
    assert list(s.digests()) == [] and list(s.tmp_dir.iterdir()) == []


def test_declared_size_over_the_cap_refuses_without_reading(tmp_path):
    s = RawObjectStore(tmp_path / "raw", limits=IngestLimits().replace(max_artefact_bytes=10))

    class Boom(io.BytesIO):
        def read(self, *a):  # pragma: no cover - must not be called
            raise AssertionError("the stream must not be read")

    with pytest.raises(IngestError) as exc:
        s.put_stream(Boom(), declared_size=11)
    assert exc.value.code == "ingest.size.file"


def test_per_call_cap_overrides_the_default(store):
    with pytest.raises(IngestError):
        store.put(b"12345", max_bytes=4)
    assert store.put(b"1234", max_bytes=4).size == 4


def test_expected_digest_size_and_crc_are_checked_before_publishing(store):
    data = b"payload"
    import zlib

    store.put(data, expected_sha256=sha(data), expected_size=len(data), expected_crc32=zlib.crc32(data))
    for kwargs in ({"expected_sha256": sha(b"other")}, {"expected_size": 3}, {"expected_crc32": 1}):
        with pytest.raises(ObjectMismatchError):
            store.put(b"different", **kwargs)
    assert not store.has(sha(b"different")) and list(store.tmp_dir.iterdir()) == []


def test_failure_while_streaming_leaves_no_object_and_no_temporary_file(store):
    def chunks():
        yield b"partial"
        raise OSError("source went away")

    with pytest.raises(OSError):
        store.put_chunks(chunks())
    assert list(store.digests()) == [] and list(store.tmp_dir.iterdir()) == []


def test_existing_object_with_wrong_bytes_is_never_overwritten(store):
    put = store.put(b"genuine")
    os.chmod(put.path, 0o644)
    put.path.write_bytes(b"tampered!")
    os.chmod(put.path, 0o444)
    with pytest.raises(DigestCollisionError) as exc:
        store.put(b"genuine")
    assert exc.value.code == "raw.digest.collision"
    assert put.path.read_bytes() == b"tampered!"  # untouched: the store reports, it does not repair


def test_verify_and_verify_on_read_detect_corruption(tmp_path):
    s = RawObjectStore(tmp_path / "raw", verify_on_read=True)
    put = s.put(b"genuine")
    assert s.verify(put.sha256) == 7 and s.read_bytes(put.sha256) == b"genuine"
    os.chmod(put.path, 0o644)
    put.path.write_bytes(b"genuinX")
    with pytest.raises(ObjectCorruptError):
        s.verify(put.sha256)
    with pytest.raises(ObjectCorruptError):
        s.read_bytes(put.sha256)
    lax = RawObjectStore(tmp_path / "raw", create=False)  # no verification unless asked for
    assert lax.read_bytes(put.sha256) == b"genuinX"


def test_two_objects_with_one_digest_are_reported_not_guessed(store):
    put = store.put(b"dup", ext="json")
    twin = put.path.with_suffix(".bin")
    twin.write_bytes(b"dup")
    with pytest.raises(RawStoreError) as exc:
        store.has(put.sha256)
    assert exc.value.code == "raw.object.ambiguous"


def test_open_returns_a_read_only_handle(store):
    put = store.put(b"data")
    with store.open(put.sha256) as fp:
        assert fp.read() == b"data"
        assert not fp.writable()


def test_digests_are_sorted_across_shards(store):
    shas = sorted(store.put(bytes([i]) * 3).sha256 for i in range(20))
    assert list(store.digests()) == shas


def test_opening_a_missing_store_read_only_does_not_create_anything(tmp_path):
    with pytest.raises(RawStoreError) as exc:
        RawObjectStore(tmp_path / "nowhere", create=False)
    assert exc.value.code == "raw.store.missing" and not (tmp_path / "nowhere").exists()


def test_a_read_only_store_cannot_be_written(tmp_path):
    RawObjectStore(tmp_path / "raw")
    (tmp_path / "raw" / "tmp").rmdir()
    ro = RawObjectStore(tmp_path / "raw", create=False)
    with pytest.raises(RawStoreError) as exc:
        ro.put(b"x")
    assert exc.value.code == "raw.store.read_only"


def test_closed_extension_map():
    assert EXTENSIONS == {"json", "jsonl", "zip", "csv", "eval", "bin"}
    assert ext_for_media("application/json") == "json"
    assert ext_for_media("application/zip; charset=binary") == "zip"
    assert ext_for_media("text/csv") == "csv" and ext_for_media("image/png") == "bin" and ext_for_media(None) == "bin"
    assert [ext_for_label(n) for n in ("a.JSON", "b.jsonl", "c.zip", "d.csv", "e.eval", "f.txt", "noext")] == [
        "json", "jsonl", "zip", "csv", "eval", "bin", "bin"
    ]


def test_extension_outside_the_closed_map_is_a_programming_error(store):
    with pytest.raises(ValueError):
        store.put(b"x", ext="exe")
    with pytest.raises(ValueError):
        store.path_for(sha(b"x"), "../x")


def test_concurrent_identical_puts_publish_one_object(store):
    results = []

    def run():
        results.append(store.put(b"racing" * 1000))

    threads = [threading.Thread(target=run) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len({r.sha256 for r in results}) == 1 and sum(r.created for r in results) == 1
    assert len(list(store.digests())) == 1 and list(store.tmp_dir.iterdir()) == []


def test_stale_temporary_files_of_dead_processes_are_swept_on_open(tmp_path):
    s = RawObjectStore(tmp_path / "raw")
    stale = s.tmp_dir / "abc.tmp-2147483646"
    stale.write_bytes(b"leftover")
    live = s.tmp_dir / f"def.tmp-{os.getpid()}"
    live.write_bytes(b"mine")
    RawObjectStore(tmp_path / "raw")
    assert not stale.exists() and live.exists()


def test_limit_field_and_violation_detail_are_generated_text_within_200_characters():
    limits = IngestLimits().replace(max_cd_bytes=1234)
    assert limit_field_for("ingest.archive.cd", limits) == LimitedField("max_cd_bytes", 1234)
    assert limit_field_for("ingest.archive.crc", limits) is None
    assert limit_field_for("ingest.archive.size", limits, field="max_total_bytes").field == "max_total_bytes"
    assert limit_field_for("ingest.archive.method", limits).value == [0, 8, 93]
    detail = violation_detail(container="c" * 64, sha256="a" * 64, size=5, limit=LimitedField("max_cd_bytes", 1234), reason="x")
    assert detail == f"container={'c' * 64}; sha256={'a' * 64}; size=5; limit=max_cd_bytes:1234; x" and len(detail) <= 200
    assert len(violation_detail(reason="y" * 500)) == 200


# ---- purged objects are never stored again (G.9.6; D-46; F-12C-05; D-61) ------------------------------------------


def _tombstone(store, *digests: str) -> None:
    rows = sorted(f'{{"date":"2026-10-12","reason":"secret","sha256":"sha256:{d}"}}\n' for d in digests)
    (store.root / "tombstones.jsonl").write_text("".join(rows))


def test_a_tombstoned_digest_is_never_published_by_any_put(store):
    leaked, other = b"credential-shaped bytes", b"fine"
    _tombstone(store, sha(leaked))
    for put in (lambda: store.put(leaked, ext="json"), lambda: store.put_stream(io.BytesIO(leaked), ext="json"),
                lambda: store.put_chunks([leaked[:5], leaked[5:]], ext="json")):  # fmt: skip
        result = put()
        assert result.tombstoned and not result.created and result.sha256 == sha(leaked)
        assert not store.has(sha(leaked)) and not result.path.exists()
    assert list(store.tmp_dir.iterdir()) == []  # the temporary copy is discarded
    assert store.put(other, ext="json").created  # every other digest is unaffected


def test_a_tombstone_written_after_the_store_was_opened_is_honoured(store):
    leaked = b"later purged"
    assert store.tombstoned() == frozenset()
    _tombstone(store, sha(leaked))
    assert store.put(leaked).tombstoned


@pytest.mark.parametrize("content", ['{"sha256": "abc"}\n', "not json\n", '{"sha256": "sha256:' + "g" * 64 + '"}\n', "[1]\n"])
def test_a_damaged_tombstone_file_fails_closed(store, content):
    (store.root / "tombstones.jsonl").write_text(content)
    with pytest.raises(RawStoreError) as err:
        store.put(b"anything")
    assert err.value.code == "raw.store.tombstones_invalid"


def test_a_symlinked_tombstone_file_is_refused(store, tmp_path):
    target = tmp_path / "elsewhere.jsonl"
    target.write_text("")
    os.symlink(target, store.root / "tombstones.jsonl")
    with pytest.raises(RawStoreError):
        store.put(b"anything")
