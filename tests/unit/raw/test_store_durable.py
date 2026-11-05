"""D-1068 P7: ``RawObjectStore(durable=False)`` skips the two ``fsync`` calls of a put and nothing else.

Stores that are removed when the command ends (T1 inputs, the trees of ``recompute --dry-run`` and ``verify --level
rederive``) need no power-loss durability. The same bytes, mode, address, idempotence and digest checks hold either way.
"""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path

import pytest

import agentprov.raw.store as store_mod
from agentprov.raw.store import DigestCollisionError, RawObjectStore, transient_stores


@pytest.fixture
def syncs(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    seen: list[str] = []
    real_fsync = os.fsync

    def fsync(fd: int) -> None:
        seen.append("file")
        real_fsync(fd)

    def fsync_dir(path: Path) -> None:  # recorded only (the real one calls os.fsync on the directory)
        seen.append("dir")

    monkeypatch.setattr(store_mod.os, "fsync", fsync)
    monkeypatch.setattr(store_mod, "_fsync_dir", fsync_dir)
    return seen


@pytest.mark.parametrize("durable", [True, False])
def test_a_put_is_the_same_with_or_without_fsync(tmp_path: Path, syncs: list[str], durable: bool) -> None:
    store = RawObjectStore(tmp_path / "raw", durable=durable)
    data = b"some bytes"
    first = store.put(data, ext="json")
    again = store.put(data, ext="jsonl")
    assert first.created and not again.created and first.path == again.path
    assert first.sha256 == hashlib.sha256(data).hexdigest() and store.read_bytes(first.sha256) == data
    assert stat.S_IMODE(first.path.stat().st_mode) == 0o444 and list(store.tmp_dir.iterdir()) == []
    assert syncs.count("file") == (2 if durable else 0) and syncs.count("dir") == (1 if durable else 0)


def test_digest_checks_hold_without_fsync(tmp_path: Path) -> None:
    store = RawObjectStore(tmp_path / "raw", durable=False)
    put = store.put(b"original", ext="bin")
    put.path.chmod(0o644)
    put.path.write_bytes(b"tampered")
    with pytest.raises(DigestCollisionError):
        store.put(b"original", ext="bin")


def test_transient_stores_sets_the_default_only_inside(tmp_path: Path, syncs: list[str]) -> None:
    assert RawObjectStore(tmp_path / "a").durable
    with transient_stores():
        inside = RawObjectStore(tmp_path / "b")
        explicit = RawObjectStore(tmp_path / "c", durable=True)
    after = RawObjectStore(tmp_path / "d")
    assert not inside.durable and explicit.durable and after.durable
    inside.put(b"x")  # the store keeps what it was built with, wherever it is used
    assert syncs == []
