"""K.5.1 item 11 (C.11.5): ``$blob`` references, ``seal.blobs`` and the raw store."""

from __future__ import annotations

from typing import Any

from aer_support import MemoryStore, codes_of, edit, example_records, example_store, seal_record
from aer_support import make_registry

from agentprov.aer.validate import validate_records

PAYLOAD = b'{"wire":"request"}'


def build(blob: dict[str, Any]) -> tuple[list[dict[str, Any]], MemoryStore]:
    store = example_store()
    store.put(PAYLOAD)
    recs = edit(example_records(), "mc0", request=blob, unk=None)
    return recs, store


def good_blob(store_digest: str) -> dict[str, Any]:
    return {"$blob": "sha256:" + store_digest, "bytes": len(PAYLOAD), "media": "application/json"}


def validate(recs: list[dict[str, Any]], store: MemoryStore | None, *, seal: dict[str, Any] | None = None) -> list[str]:
    full = [*recs, seal if seal is not None else seal_record(recs)]
    return codes_of(validate_records(full, store=store, catalogues=make_registry()))


def test_a_resolving_blob_is_valid_and_listed_in_seal_blobs() -> None:
    store = example_store()
    digest = store.put(PAYLOAD)
    recs, store = build(good_blob(digest))
    assert seal_record(recs)["blobs"] == ["sha256:" + digest]
    assert validate(recs, store) == []


def test_blobs_missing_from_the_seal_or_extra_in_it_are_aer_blob_ref() -> None:
    store = example_store()
    digest = store.put(PAYLOAD)
    recs, store = build(good_blob(digest))
    seal = seal_record(recs)
    without = {k: v for k, v in seal.items() if k != "blobs"}
    assert "aer.blob.ref" in validate(recs, store, seal=without)
    extra = {**seal, "blobs": sorted([*seal["blobs"], "sha256:" + "f" * 64])}
    assert "aer.blob.ref" in validate(recs, store, seal=extra)
    unsorted = {**seal, "blobs": ["sha256:" + "f" * 64, *seal["blobs"]]}
    assert "aer.blob.ref" in validate(recs, store, seal=unsorted)
    bogus = {**seal_record(example_records())}
    bogus["blobs"] = ["sha256:" + "e" * 64]
    assert "aer.blob.ref" in validate(example_records(), store, seal=bogus)


def test_malformed_references_are_aer_blob_ref() -> None:
    for blob in (
        {"$blob": "sha256:xyz", "bytes": 3},
        {"$blob": "sha256:" + "A" * 64, "bytes": 3},
        {"$blob": "md5:" + "a" * 32, "bytes": 3},
        {"$blob": "sha256:" + "a" * 64},  # bytes is required
        {"$blob": "sha256:" + "a" * 64, "bytes": -1},
        {"$blob": "sha256:" + "a" * 64, "bytes": 1, "extra": 1},
    ):
        recs = edit(example_records(), "mc0", request=blob, unk=None)
        assert "aer.blob.ref" in codes_of(validate_records([*recs, seal_record(recs)], store=None, catalogues=make_registry())), blob


def test_a_missing_blob_is_aer_blob_missing_and_a_wrong_size_is_aer_blob_digest() -> None:
    store = example_store()
    recs, _ = build(good_blob("c" * 64))
    assert "aer.blob.missing" in validate(recs, store)
    digest = store.put(PAYLOAD)
    wrong = good_blob(digest)
    wrong["bytes"] += 5
    recs, store = build(wrong)
    store.put(PAYLOAD)
    assert "aer.blob.digest" in validate(recs, store)


def test_blobs_inside_open_json_content_and_parts_are_collected() -> None:
    store = example_store()
    digest = store.put(PAYLOAD)
    blob = good_blob(digest)
    recs = edit(example_records(), "m3", parts=[{"t": "blob", "data": blob, "media": "application/json"}])
    recs = edit(recs, "te0", returned={"nested": [blob]})
    assert seal_record(recs)["blobs"] == ["sha256:" + digest]
    assert validate(recs, store) == []


def test_without_a_store_blob_checks_are_reported_as_skipped() -> None:
    store = example_store()
    digest = store.put(PAYLOAD)
    recs, _ = build(good_blob(digest))
    report = validate_records([*recs, seal_record(recs)], store=None, catalogues=make_registry())
    assert report.ok and report.skipped and not report.passed
