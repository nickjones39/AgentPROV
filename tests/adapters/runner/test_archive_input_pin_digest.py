"""CB-20 (regen item 58): an archive input is stored only if its bytes still hash to the verified pin digest.

The CLI checks the downloaded file against its pin and then builds an :class:`ArchiveTree` from the path; the pipeline
reopens the file to copy it into the raw store. Bytes swapped in between (same size, other content) must be refused by
the store (``raw.object.mismatch``) before the object is published and before its pinned origin is recorded. The same
holds for each part of a split archive input (D-249). Synthetic zips only; no network.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest

from agentprov.adapters.runner.importer import ArchiveTree, import_source
from agentprov.corpus.writer import CorpusWriter
from agentprov.raw.origins import Origin
from agentprov.raw.store import ObjectMismatchError

DOI = "10.5281/zenodo.7"


def _zip(text: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as archive:
        archive.writestr("deposit/README.txt", text)
    return buf.getvalue()


def _pair() -> tuple[bytes, bytes]:
    good, bad = _zip(b"GOOD-content\n"), _zip(b"EVIL-content\n")
    assert len(good) == len(bad) and good != bad
    return good, bad


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _origins(corpus: Path) -> list[dict[str, Any]]:
    path = corpus.with_name(corpus.name + ".partial") / "raw" / "origins.jsonl"
    return [json.loads(line) for line in path.read_text("utf-8").splitlines()] if path.exists() else []


def _stored(corpus: Path) -> set[str]:
    objects = corpus.with_name(corpus.name + ".partial") / "raw" / "objects"
    return {p.stem for p in objects.rglob("*") if p.is_file()} if objects.exists() else set()


def _import(tree: ArchiveTree, pin: dict[str, Any], corpus: Path) -> Any:
    with CorpusWriter(corpus) as writer:
        return import_source("foobench", tree, corpus=writer, profile_id="foobench", part="fixture", pin=pin,
                             in_process=True)  # fmt: skip


def test_an_archive_input_swapped_after_verification_is_refused_before_it_is_stored(tmp_path):
    good, bad = _pair()
    path = tmp_path / "in" / "deposit.zip"
    path.parent.mkdir()
    path.write_bytes(good)
    pin = {"role": "fixture", "kind": "zenodo", "doi": DOI, "record": 7, "file": "deposit.zip", "sha256": _sha(good),
           "bytes": len(good)}  # fmt: skip
    tree = ArchiveTree(path, pin=pin, sha256=pin["sha256"], size=pin["bytes"])  # the verified values
    path.write_bytes(bad)  # the race: other bytes of the same size before the copy into the raw store
    corpus = tmp_path / "c"
    with pytest.raises(ObjectMismatchError) as caught:
        _import(tree, pin, corpus)
    assert caught.value.code == "raw.object.mismatch"
    assert not [o for o in _origins(corpus) if o["origin"]["kind"] == "zenodo"]
    assert _sha(bad) not in _stored(corpus)


def test_a_split_part_swapped_after_verification_is_refused_before_it_is_stored(tmp_path):
    good, bad = _pair()
    root = tmp_path / "in"
    root.mkdir()
    half = len(good) // 2
    chunks = [good[:half], good[half:]]
    paths = []
    for k, chunk in enumerate(chunks):
        paths.append(root / f"deposit.zip.part-{k:04d}")
        paths[-1].write_bytes(chunk)
    pin = {"role": "fixture", "kind": "zenodo", "doi": DOI, "record": 7, "file": "deposit.zip", "archive": "split-zip",
           "parts": [{"file": p.name, "bytes": len(c), "sha256": _sha(c)} for p, c in zip(paths, chunks, strict=True)]}
    tree = ArchiveTree.split([(p, _sha(c), len(c)) for p, c in zip(paths, chunks, strict=True)], pin=pin)
    paths[1].write_bytes(bad[half:])  # the second part is swapped after it was checked
    corpus = tmp_path / "c"
    with pytest.raises(ObjectMismatchError):
        _import(tree, pin, corpus)
    swapped = _sha(bad[half:])
    assert swapped not in _stored(corpus)
    assert not [o for o in _origins(corpus) if o["sha256"] == "sha256:" + swapped]


def test_add_object_checks_the_expected_digest_and_size_before_the_origin_is_recorded(tmp_path):
    good, bad = _pair()
    origin = Origin.zenodo(DOI, "deposit.zip")
    corpus = tmp_path / "c"
    with CorpusWriter(corpus) as writer:
        for data in (bad, io.BytesIO(bad)):
            with pytest.raises(ObjectMismatchError):
                writer.add_object(data, origin, ext="zip", expected_sha256=_sha(good), expected_size=len(good))
        with pytest.raises(ObjectMismatchError):
            writer.add_object(good, origin, ext="zip", expected_sha256=_sha(good), expected_size=len(good) + 1)
        assert writer.origins.count(_sha(bad)) == 0 and not writer.store.has(_sha(bad))
        put = writer.add_object(io.BytesIO(good), origin, ext="zip", expected_sha256=_sha(good), expected_size=len(good))
        assert put.sha256 == _sha(good) and writer.origins.count(put.sha256) == 1
