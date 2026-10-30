"""The sealed snapshot origin of an archive input follows every derived object to the root of its chain (H.2.3; D-33,
D-202, D-380, D-381; core review B, 10p's control-arena seal).

A log inside an ``.eval`` that is itself a member of a tar.zst, of a nested zip or of a split zip has a ``member`` origin
whose container has only ``member`` origins too. Going up one container level found no ``hf``/``split`` origin, and the
seal refused with ``package.refused.pin``. Synthetic digests only.
"""

from __future__ import annotations

from typing import Any

import pytest

from agentprov.corpus.manifest import ManifestError, snapshot_origin_from_pin
from agentprov.corpus.package import snapshot_object_origins

REV = "c" * 40


def _h(n: int) -> str:
    return f"{n:064x}"


def _member(container: str, label: str = "m") -> dict[str, Any]:
    return {"kind": "member", "container": container, "label": label, "method": 8, "crc32": "00000000", "size": 1}


def _hf(path: str) -> dict[str, Any]:
    return {"kind": "hf", "dataset": "owner/name", "revision": REV, "path": path}


def _pin(file: str) -> dict[str, Any]:
    return {"kind": "hf", "repo": "owner/name", "revision": REV, "gated": False, "file": file}


def _sealed(primaries: set[str], by_sha: dict[str, list[dict[str, Any]]], pin: dict[str, Any], *,
            several: bool = False) -> dict[str, Any]:
    return snapshot_origin_from_pin(pin, snapshot_object_origins(primaries, by_sha, pin, several=several))


def test_a_log_two_archive_levels_below_a_tar_zst_input_reaches_its_hf_origin() -> None:
    tar, ev1, ev2 = _h(1), _h(2), _h(3)
    logs = [_h(10), _h(11), _h(12)]
    by_sha = {
        tar: [_hf("runs.tar.zst")],
        ev1: [_member(tar, "a.eval")], ev2: [_member(tar, "b.eval")],
        logs[0]: [_member(ev1, "header.json")], logs[1]: [_member(ev1, "samples/1.json")],
        logs[2]: [_member(ev2, "header.json")],
    }  # fmt: skip
    assert _sealed(set(logs), by_sha, _pin("runs.tar.zst")) == {
        "dataset": "owner/name", "gated": False, "kind": "hf", "path": "runs.tar.zst", "revision": REV}


def test_a_log_in_an_eval_in_a_nested_zip_of_a_split_zip_reaches_the_split_descriptor() -> None:
    parts = [{"file": f"logs/z.zip.{i:03d}", "sha256": "sha256:" + _h(90 + i), "size": 1} for i in (1, 2)]
    pin = {"kind": "hf", "repo": "owner/name", "revision": REV, "gated": False, "archive": "split-zip",
           "file": "logs/z.zip", "parts": parts}
    descriptor, nested, ev, log = _h(1), _h(2), _h(3), _h(4)
    by_sha = {
        descriptor: [{"kind": "split", "archive": "zip", "label": "logs/z.zip", "parts": [_h(91), _h(92)]}],
        nested: [_member(descriptor, "logs/inner.zip")],
        ev: [_member(nested, "a.eval")],
        log: [_member(ev, "header.json")],
    }
    origin = _sealed({log}, by_sha, pin)
    assert origin["kind"] == "hf" and origin["revision"] == REV


def test_one_level_containers_still_seal() -> None:
    zip_, log = _h(1), _h(2)
    by_sha = {zip_: [_hf("a.zip")], log: [_member(zip_)]}
    assert _sealed({log}, by_sha, _pin("a.zip"))["path"] == "a.zip"


def test_a_byte_duplicate_eval_in_two_snapshots_archives_keeps_only_the_pinned_root() -> None:
    """One ``.eval`` stored once, a member of the archive of each of two snapshots (same revision, other files)."""
    a, b, ev, log = _h(1), _h(2), _h(3), _h(4)
    by_sha = {a: [_hf("a.tar.zst")], b: [_hf("b.zip")], ev: [_member(a, "x.eval"), _member(b, "x.eval")],
              log: [_member(ev, "header.json")]}
    assert _sealed({log}, by_sha, _pin("a.tar.zst"), several=True)["path"] == "a.tar.zst"
    assert _sealed({log}, by_sha, _pin("b.zip"), several=True)["path"] == "b.zip"
    with pytest.raises(ManifestError):  # one snapshot reaching two pinned files is still refused
        _sealed({log}, by_sha, _pin("a.tar.zst"))


def test_a_carved_blob_reaches_its_source_objects_origin() -> None:
    zip_, log, blob = _h(1), _h(2), _h(3)
    by_sha = {zip_: [_hf("a.zip")], log: [_member(zip_)],
              blob: [{"kind": "carved", "from": "sha256:" + log, "loc": {"p": "/x"}, "transform": "base64"}]}
    assert _sealed({blob}, by_sha, _pin("a.zip"))["path"] == "a.zip"


def test_a_member_cycle_ends_and_an_unrooted_chain_is_refused() -> None:
    x, y = _h(1), _h(2)
    by_sha = {x: [_member(y)], y: [_member(x)]}
    assert snapshot_object_origins({x}, by_sha, _pin("a.zip"), several=False) == []
    with pytest.raises(ManifestError, match="pinned file"):
        _sealed({x}, by_sha, _pin("a.zip"))


def test_a_root_origin_is_listed_once_however_many_chains_reach_it() -> None:
    root = _h(1)
    by_sha: dict[str, list[dict[str, Any]]] = {root: [_hf("a.zip")]}
    logs = set()
    for i in range(20):
        ev, log = _h(100 + i), _h(200 + i)
        by_sha[ev], by_sha[log] = [_member(root, f"{i}.eval")], [_member(ev, "header.json")]
        logs.add(log)
    assert snapshot_object_origins(logs, by_sha, _pin("a.zip"), several=False) == [_hf("a.zip")]
