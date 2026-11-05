"""P3: the ``checksums`` level hashes a tree on several threads, opening each file relative to a kept descriptor of its
directory (H.5.5; G.3.6). The findings, the order of the callbacks and every refusal must be those of the per-label
walk (``open_evidence`` from the root, one file after the other), under both no-follow mechanisms."""

from __future__ import annotations

import hashlib
import os
import types
import zlib
from pathlib import Path
from typing import IO, Any

import pytest

from agentprov.corpus import integrity
from agentprov.corpus.integrity import (
    ChecksumReport,
    TreeSource,
    verify_checksum_source,
    write_checksums,
)
from agentprov.corpus.layout import CorpusLayout
from agentprov.ingest import paths
from agentprov.ingest.paths import STORED_OBJECT_LIMITS, open_evidence

EXECUTIONS = [f"ex_{chr(ord('a') + i)}uz2oys57hugtsueixylme4fl5" for i in range(6)]


def _verify_host() -> types.SimpleNamespace:
    """A host without the native primitives: forces the verify_identity mechanism (no directory descriptors)."""
    host = types.SimpleNamespace(
        O_RDONLY=os.O_RDONLY, open=os.open, lstat=os.lstat, fstat=os.fstat, scandir=os.scandir,
        supports_dir_fd=frozenset(), supports_fd=frozenset(),
    )  # fmt: skip
    for name in ("O_BINARY", "O_CLOEXEC", "O_NONBLOCK"):
        if hasattr(os, name):
            setattr(host, name, getattr(os, name))
    return host


@pytest.fixture(params=["native", "verify_identity"])
def mechanism(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> str:
    if request.param == "native":
        if paths.describe_mechanism()[0] != "native":
            pytest.skip("this host has no native no-follow primitives")
    else:
        monkeypatch.setattr(paths, "_prim", lambda: paths._probe(_verify_host()))
    return str(request.param)


def _corpus(root: Path) -> Path:
    """A sealed tree with files in many directories: raw objects in several shards, AERs in several shards."""
    layout = CorpusLayout(root)
    files: dict[str, bytes] = {
        "corpus.json": b'{"format": "agentprov-corpus/0.1", "sealed": true}',
        "executions.jsonl": b"", "register.jsonl": b"", "derivation.json": b"{}\n", "DATASHEET.md": b"# d\n",
        "raw/origins.jsonl": b"", "raw/members.jsonl": b"", "rules/corpus-spec.toml": b"",
    }  # fmt: skip
    for i in range(40):
        data = f'{{"object":{i}}}'.encode() * (1 + i * 997)  # some above one read chunk once doubled below
        sha = hashlib.sha256(data).hexdigest()
        files[f"raw/objects/{sha[:2]}/{sha}.json"] = data
    big = os.urandom(3 << 20)  # more than one read chunk (1 MiB)
    sha = hashlib.sha256(big).hexdigest()
    files[f"raw/objects/{sha[:2]}/{sha}.bin"] = big
    for ex in EXECUTIONS:
        files[layout.aer_relpath(ex)] = f"aer {ex}\n".encode()
    for label, data in files.items():
        path = root.joinpath(*label.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    write_checksums(root)
    return root


def _labels(root: Path, prefix: str) -> list[str]:
    """The ``/``-joined labels of the files below ``prefix`` (``as_posix``: on Windows ``str`` joins with ``\\``)."""
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*")
                  if p.is_file() and p.relative_to(root).as_posix().startswith(prefix))


class _PerLabel(TreeSource):
    """The ``checksums`` level before P3: every label opened from the root (``open_evidence``), one after the other."""

    hash_files = None  # type: ignore[assignment]  # no parallel hashing: the level falls back to open() per label

    def open(self, path: str) -> IO[bytes]:
        root: Any = self._handle if self._handle is not None else self.root
        return open_evidence(root, path, STORED_OBJECT_LIMITS, allow_hardlinks=True)


def _report(source_type: type[TreeSource], root: Path, *, threads: int | None = None,
            crc: bool = False) -> tuple[ChecksumReport, list[tuple[str, str, int]], dict[str, str]]:
    matched: list[tuple[str, str, int]] = []
    crcs: dict[str, str] = {}
    with source_type(root) as source:
        report = verify_checksum_source(
            source, threads=threads, on_match=lambda p, d, s: matched.append((p, d, s)),
            crc32_of=(lambda p: p.startswith("raw/objects/")) if crc else None,
            on_crc32=lambda p, c: crcs.__setitem__(p, c))
    return report, matched, crcs


def _open_fds() -> int:
    return len(os.listdir("/dev/fd")) if os.path.isdir("/dev/fd") else 0


# ------------------------------------------------------------------------------------------------ damage
def _replace_shard_with_link(root: Path, tmp: Path) -> None:
    label = _labels(root, "raw/objects/")[0]
    shard = (root / label).parent
    copy = tmp / "outside-shard"
    copy.mkdir()
    for f in shard.iterdir():
        (copy / f.name).write_bytes(f.read_bytes())  # the same bytes: following the link would pass
    for f in shard.iterdir():
        f.unlink()
    shard.rmdir()
    os.symlink(copy, shard, target_is_directory=True)


def _replace_file_with_link(root: Path, tmp: Path) -> None:
    target = root / _labels(root, "aer/")[0]
    outside = tmp / "outside.aer"
    outside.write_bytes(target.read_bytes())
    target.unlink()
    os.symlink(outside, target)


def _replace_objects_dir_with_file(root: Path, tmp: Path) -> None:
    objects = root / "raw" / "objects"
    os.rename(objects, tmp / "objects-moved")
    objects.write_bytes(b"not a directory\n")


def _fifo_for_file(root: Path, tmp: Path) -> None:
    if not hasattr(os, "mkfifo"):
        pytest.skip("os.mkfifo is POSIX only")
    target = root / _labels(root, "raw/objects/")[3]
    target.unlink()
    os.mkfifo(target)


def _directory_for_file(root: Path, tmp: Path) -> None:
    target = root / _labels(root, "aer/")[1]
    target.unlink()
    target.mkdir()
    (target / "x").write_bytes(b"")


def _unreadable_file(root: Path, tmp: Path) -> None:
    if os.name != "posix" or os.geteuid() == 0:
        pytest.skip("a mode-000 file is unreadable only on POSIX (Windows' chmod sets the read-only attribute alone), "
                    "and root reads it")
    os.chmod(root / _labels(root, "raw/objects/")[5], 0)


def _missing_shard(root: Path, tmp: Path) -> None:
    shard = (root / _labels(root, "raw/objects/")[7]).parent
    os.rename(shard, tmp / "gone-shard")


def _tampered(root: Path, tmp: Path) -> None:
    (root / _labels(root, "raw/objects/")[2]).write_bytes(b"tampered")
    (root / _labels(root, "aer/")[2]).write_bytes(b"tampered\n")


def _hard_link(root: Path, tmp: Path) -> None:
    os.link(root / "DATASHEET.md", tmp / "a-hard-link")  # hard links are admitted (D-32)


DAMAGES = {
    "none": lambda root, tmp: None,
    "tampered": _tampered,
    "shard_is_a_link": _replace_shard_with_link,
    "file_is_a_link": _replace_file_with_link,
    "objects_is_a_file": _replace_objects_dir_with_file,
    "fifo": _fifo_for_file,
    "directory_for_a_file": _directory_for_file,
    "unreadable": _unreadable_file,
    "missing_shard": _missing_shard,
    "hard_link": _hard_link,
}


@pytest.mark.parametrize("damage", sorted(DAMAGES))
def test_the_parallel_level_reports_exactly_what_the_per_label_walk_reports(tmp_path, mechanism, damage):
    root = _corpus(tmp_path / "c")
    DAMAGES[damage](root, tmp_path)
    try:
        expected, expected_matched, _ = _report(_PerLabel, root)
        before = _open_fds()
        for threads in (1, 2, 8):
            got, got_matched, _ = _report(TreeSource, root, threads=threads)
            assert got == expected, (damage, threads)
            assert got_matched == expected_matched  # every callback, in the listed order
        assert _open_fds() == before  # no directory descriptor is left open
    finally:
        for p in root.rglob("*"):
            if not p.is_symlink():
                os.chmod(p, 0o700 if p.is_dir() else 0o600)
    if damage == "none":
        assert expected.ok and expected.matched == expected.listed > 40
    elif damage != "hard_link":
        assert not expected.ok


def test_the_refusals_are_the_per_label_codes(tmp_path, mechanism):
    root = _corpus(tmp_path / "c")
    _replace_shard_with_link(root, tmp_path)
    _replace_file_with_link(root, tmp_path)
    _fifo_for_file(root, tmp_path)
    report, _, _ = _report(TreeSource, root, threads=4)
    unreadable = {f.path: f.detail for f in report.findings if f.code == "checksums.unreadable"}
    assert set(unreadable.values()) == {"ingest.path.symlink", "ingest.path.special"}
    assert sum(1 for d in unreadable.values() if d == "ingest.path.symlink") >= 2  # the link and its shard's files


def test_the_crc32_is_computed_in_the_same_read_for_the_files_named(tmp_path, mechanism):
    root = _corpus(tmp_path / "c")
    _report_, _matched, crcs = _report(TreeSource, root, threads=4, crc=True)
    objects = _labels(root, "raw/objects/")
    assert sorted(crcs) == objects
    for label in objects:
        assert crcs[label] == f"{zlib.crc32((root / label).read_bytes()):08x}"
    assert _report(TreeSource, root, threads=4)[2] == {}  # none asked for, none computed


def test_the_thread_count_is_bounded_by_the_host_and_changes_nothing(tmp_path, monkeypatch):
    assert 1 <= integrity.hash_threads() <= integrity.MAX_HASH_THREADS
    monkeypatch.setattr(os, "cpu_count", lambda: None)
    assert integrity.hash_threads() == 1
    monkeypatch.setattr(os, "cpu_count", lambda: 512)
    assert integrity.hash_threads() == integrity.MAX_HASH_THREADS


def test_open_keeps_one_directory_descriptor_and_refuses_a_link_in_any_component(tmp_path, mechanism):
    root = _corpus(tmp_path / "c")
    labels = _labels(root, "raw/objects/") + _labels(root, "aer/")
    before = _open_fds()
    with TreeSource(root) as source:
        for label in labels:
            with source.open(label) as stream:
                assert stream.read() == (root / label).read_bytes()
        held = _open_fds() - before
        assert held <= 2  # the root's descriptor and (native) the last directory's
    assert _open_fds() == before
    _replace_shard_with_link(root, tmp_path)
    linked = next(lab for lab in labels if (root / lab).parent.is_symlink())
    with TreeSource(root) as source, pytest.raises(Exception) as refused:
        source.open(linked)
    assert getattr(refused.value, "code", None) == "ingest.path.symlink"


def test_the_level_reads_nothing_outside_the_tree_and_writes_nothing(tmp_path, mechanism):
    from agentprov.testing import fs_guard

    root = _corpus(tmp_path / "c")
    with fs_guard.unchanged(root):
        report, _, _ = _report(TreeSource, root, threads=8)
    assert report.ok
