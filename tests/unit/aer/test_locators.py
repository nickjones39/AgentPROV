"""C.9: locator forms and resolution against digest-checked raw bytes."""

from __future__ import annotations

import json
from typing import Any

import pytest
from aer_support import ARTEFACT_BYTES, ARTEFACT_SHA, MemoryStore, example_records, example_store

from agentprov.aer.locators import (
    BlobDigestError,
    BlobMissingError,
    LocatorError,
    LocatorResolver,
    RawStore,
    pointer_exists,
    pointer_get,
    resolve,
)

HEADER = example_records()[0]
JSONL = b'{"a":1}\n{"b":[10,20]}\n\n{"c":3}\n'
LINES_SHA = None


def with_jsonl() -> tuple[dict[str, Any], MemoryStore]:
    store = example_store()
    sha = store.put(JSONL)
    header = json.loads(json.dumps(HEADER))
    header["artifacts"].append(
        {"id": "a1", "role": "supporting", "prov_primary": "unknown", "sha256": sha, "bytes": len(JSONL), "media": "x",
         "origin": {"kind": "capture", "session": "0190a6e0-1d5c-7a3b-8c4d-123456789abc"}}
    )
    return header, store


def test_store_protocol_is_runtime_checkable() -> None:
    assert isinstance(example_store(), RawStore)
    assert not isinstance(object(), RawStore)


def test_json_pointer_and_whole_artefact_forms() -> None:
    store = example_store()
    assert resolve({"a": "a0", "p": "/messages/3/i"}, header=HEADER, store=store) == 3
    assert resolve({"a": "a0", "p": ""}, header=HEADER, store=store) == json.loads(ARTEFACT_BYTES)
    assert resolve({"a": "a0"}, header=HEADER, store=store) == ARTEFACT_BYTES


def test_origin_pointer_needs_no_store_bytes() -> None:
    assert resolve({"a": "a0", "o": "/url"}, header=HEADER, store=MemoryStore()) == "https://example.invalid/a.json"


def test_line_form_is_zero_based_and_lf_split() -> None:
    header, store = with_jsonl()
    r = LocatorResolver(header, store)
    assert r.resolve({"a": "a1", "line": 0}) == {"a": 1}
    assert r.resolve({"a": "a1", "line": 1, "p": "/b/1"}) == 20
    assert r.resolve({"a": "a1", "line": 3}) == {"c": 3}
    for bad_line in (2, 4, 9, -1):  # blank line, past the end (the trailing empty piece), beyond, negative
        with pytest.raises(LocatorError):
            r.resolve({"a": "a1", "line": bad_line})


def test_byte_range_with_slice_relative_pointer() -> None:
    start = ARTEFACT_BYTES.index(b'{"i":5}')
    loc = {"a": "a0", "bytes": [start, start + 7], "p": "/i"}
    assert resolve(loc, header=HEADER, store=example_store()) == 5
    for bad in ([0, 0], [5, 3], [0, 10**9], [-1, 4], "x", [1]):
        with pytest.raises(LocatorError):
            resolve({"a": "a0", "bytes": bad}, header=HEADER, store=example_store())


def test_blob_form() -> None:
    store = example_store()
    sha = store.put(b'{"x": [1, 2]}')
    assert resolve({"blob": "sha256:" + sha}, header=HEADER, store=store) == b'{"x": [1, 2]}'
    assert resolve({"blob": "sha256:" + sha, "p": "/x/1"}, header=HEADER, store=store) == 2


@pytest.mark.parametrize(
    "loc",
    [
        {"a": "a9", "p": ""},  # artefact not listed
        {"a": "a0", "p": "/messages/99"},
        {"a": "a0", "p": "/messages/01"},
        {"a": "a0", "p": "/nope"},
        {"a": "a0", "p": "/meta/k/x"},  # descends into a scalar
        {"a": "a0", "o": "/missing"},
        {"p": ""},
        {"blob": "sha256:" + "0" * 64},
        {"blob": "nonsense"},
    ],
)
def test_unresolvable_locators_fail(loc: dict[str, Any]) -> None:
    with pytest.raises(LocatorError):
        resolve(loc, header=HEADER, store=example_store())


def test_missing_object_and_digest_mismatch_have_their_own_codes() -> None:
    with pytest.raises(BlobMissingError) as missing:
        resolve({"a": "a0", "p": ""}, header=HEADER, store=MemoryStore())
    assert missing.value.code == "aer.blob.missing"
    corrupt = MemoryStore({ARTEFACT_SHA: b"tampered"})
    with pytest.raises(BlobDigestError) as digest:
        resolve({"a": "a0", "p": ""}, header=HEADER, store=corrupt)
    assert digest.value.code == "aer.blob.digest"
    wrong_size = json.loads(json.dumps(HEADER))
    wrong_size["artifacts"][0]["bytes"] += 1
    with pytest.raises(BlobDigestError):
        resolve({"a": "a0", "p": ""}, header=wrong_size, store=example_store())


def test_unparseable_artefacts_fail_with_a_locator_error() -> None:
    store = MemoryStore()
    bad = b'{"a": 1, "a": 2}'  # duplicate member: the strict loader rejects it
    sha = store.put(bad)
    header = json.loads(json.dumps(HEADER))
    header["artifacts"][0].update({"sha256": sha, "bytes": len(bad)})
    with pytest.raises(LocatorError):
        resolve({"a": "a0", "p": ""}, header=header, store=store)


def test_pointer_helpers() -> None:
    doc = {"a": [1, {"b/c": 2, "d~e": 3}]}
    assert pointer_get(doc, "/a/1/b~1c") == 2 and pointer_get(doc, "/a/1/d~0e") == 3 and pointer_get(doc, "") == doc
    assert pointer_exists(doc, "/a/0") and not pointer_exists(doc, "/a/2") and not pointer_exists(doc, "a")
    assert not pointer_exists(doc, "/a/-")


# ------------------------------------------------------------------------------------------------ RH-1 (D-710)
def _with_doc(data: bytes) -> tuple[dict[str, Any], MemoryStore]:
    store = example_store()
    sha = store.put(data)
    header = json.loads(json.dumps(HEADER))
    header["artifacts"].append(
        {"id": "a1", "role": "supporting", "prov_primary": "unknown", "sha256": sha, "bytes": len(data), "media": "x",
         "origin": {"kind": "capture", "session": "0190a6e0-1d5c-7a3b-8c4d-123456789abc"}}
    )
    return header, store


def test_finite_documents_parse_as_under_the_strict_profile() -> None:
    from agentprov.ingest.loaders import PROFILE_PYTHON_JSON, strict_json_loads

    for data in (ARTEFACT_BYTES, b'{"x": [1, 2.5, -0.0, 1e300, "NaN", {"$float": "x"}], "y": null}', b"[]", b'"s"'):
        assert strict_json_loads(data, profile=PROFILE_PYTHON_JSON) == strict_json_loads(data)


def test_a_document_with_a_non_finite_number_resolves_and_never_yields_a_number() -> None:
    """D-710: a NaN elsewhere in the document no longer makes every locator into it dangle; a locator pointing at the
    non-finite value gets the ``{"$float": ...}`` object (C.11.3), never a float."""
    header, store = _with_doc(b'{"eval": {"task": "t"}, "results": {"m": NaN, "n": [Infinity, -Infinity]}}')
    r = LocatorResolver(header, store)
    assert r.resolve({"a": "a1", "p": "/eval/task"}) == "t"
    assert r.resolve({"a": "a1", "p": "/results/m"}) == {"$float": "NaN"}
    assert r.resolve({"a": "a1", "p": "/results/n"}) == [{"$float": "Infinity"}, {"$float": "-Infinity"}]


def test_strictness_is_otherwise_unchanged() -> None:
    for bad in (b'{"a": 1, "a": 2}', b'{"a": nan}', b"{'a': 1}"):
        header, store = _with_doc(bad)
        with pytest.raises(LocatorError):
            LocatorResolver(header, store).resolve({"a": "a1", "p": "/a"})
